from __future__ import annotations

import math
import os
import json
import random
import sys
from itertools import count
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import pygame

from balance_log import append_world_balance_log, create_run_id
from cards import (
    CARDS,
    CARD_BY_KEY,
    CATEGORY_SPECS,
    TARGET_BOSS,
    TARGET_ELITE,
    TARGET_GATE,
    TARGET_NORMAL,
    TARGET_PLAYER,
    Card,
    CardEffect,
)
from logic import (
    attribute_price,
    boss_windup_move_factor,
    boss_gold_reward,
    execution_ready,
    format_number,
    gate_initial_value,
    gate_shot_damage,
    gate_steps,
    shot_damage,
    world_dps_threshold,
    world_target_health,
)


WIDTH, HEIGHT = 1280, 720
PLAY_TOP = int(HEIGHT * 0.70)
FPS = 60
WORLD_DURATION = 120.0

BG = (15, 18, 27)
PANEL = (27, 32, 46)
GRID = (35, 41, 57)
WHITE = (235, 239, 247)
MUTED = (150, 160, 180)
CYAN = (64, 215, 255)
BLUE = (71, 114, 255)
RED = (242, 77, 93)
DARK_RED = (112, 34, 45)
GREEN = (74, 222, 128)
YELLOW = (255, 207, 77)
ORANGE = (255, 136, 66)
PURPLE = (186, 104, 255)
RARITY_COLORS = {"普通": WHITE, "罕见": PURPLE, "稀有": YELLOW}

CURSOR_TRAIL_MAX_AGE = 0.42
CURSOR_TRAIL_CAP = 30
CURSOR_PARTICLE_CAP = 140
CURSOR_PALETTE = (CYAN, (96, 255, 255), BLUE, PURPLE, WHITE)
OVERLOAD = (255, 55, 70)
OVERLOAD_CHANCE = 0.05
OVERLOAD_EXCHANGE_COST = 5
OVERLOAD_SALE_PRICE = 20
_owned_card_ids = count(1)


def asset_path(relative_path: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / relative_path


def settings_path() -> Path:
    if getattr(sys, "_MEIPASS", None):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "settings.json"


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    path = pygame.font.match_font(["microsoftyahei", "simhei", "arial"], bold=bold)
    return pygame.font.Font(path, size)


def normalized(vector: pygame.Vector2) -> pygame.Vector2:
    return vector.normalize() if vector.length_squared() else pygame.Vector2()


class Mode(Enum):
    MAIN_MENU = auto()
    TUTORIAL = auto()
    SETTINGS = auto()
    PLAYING = auto()
    SHOP = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    VICTORY = auto()


@dataclass
class Bullet:
    position: pygame.Vector2
    velocity: pygame.Vector2
    damage: float
    gate_damage: float
    pierces: int = 0
    bounces: int = 0
    gate_target_bonus: float = 0.0
    special_gate_damage: float | None = None
    radius: int = 5
    hit_ids: set[int] = field(default_factory=set)
    previous_position: pygame.Vector2 = field(init=False)

    def __post_init__(self) -> None:
        self.previous_position = self.position.copy()

    def update(self, dt: float) -> None:
        self.previous_position = self.position.copy()
        self.position += self.velocity * dt

    def on_screen(self) -> bool:
        return -20 <= self.position.x <= WIDTH + 20 and -20 <= self.position.y <= HEIGHT + 20


@dataclass
class Enemy:
    position: pygame.Vector2
    hp: float
    max_hp: float
    speed: float
    radius: int
    elite: bool = False
    shoot_timer: float = 2.5

    def update(self, dt: float, player: pygame.Vector2) -> None:
        direction = pygame.Vector2(0, 1) if self.position.y < HEIGHT * 0.48 else normalized(player - self.position)
        self.position += direction * self.speed * dt


@dataclass
class EnemyBullet:
    position: pygame.Vector2
    velocity: pygame.Vector2
    radius: int = 7
    population_loss_ratio: float = 0.03
    source: str = "精英弹丸"

    def update(self, dt: float) -> None:
        self.position += self.velocity * dt

    def on_screen(self) -> bool:
        return -20 <= self.position.x <= WIDTH + 20 and -20 <= self.position.y <= HEIGHT + 20


@dataclass
class CursorParticle:
    position: pygame.Vector2
    velocity: pygame.Vector2
    life: float
    max_life: float
    size: float
    color: tuple[int, int, int]


@dataclass
class Gate:
    position: pygame.Vector2
    kind: str
    value: int = 0
    hp: float = 0
    max_hp: float = 0
    buff: str = ""
    recruit_progress: float = 0.0
    speed: float = 48.0
    width: int = 136
    height: int = 58

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            round(self.position.x - self.width / 2),
            round(self.position.y - self.height / 2),
            self.width,
            self.height,
        )

    @property
    def unlocked(self) -> bool:
        return self.kind == "number" or self.hp <= 0

    @property
    def recruit_multiplier(self) -> float:
        multiplier, _, _ = self.recruit_state()
        return multiplier

    def recruit_step_cost(self, multiplier: float) -> float:
        if multiplier < 1.5 - 1e-9:
            return self.max_hp
        if multiplier < 2.0 - 1e-9:
            return self.max_hp * 2
        exponential_step = max(0, round((multiplier - 2.0) * 10))
        return self.max_hp * 4 * (2 ** exponential_step)

    def recruit_state(self) -> tuple[float, float, float]:
        if self.buff != "population" or self.max_hp <= 0:
            return 1.0, 0.0, 1.0
        multiplier = 1.1
        remaining = self.recruit_progress
        for _ in range(100):
            cost = self.recruit_step_cost(multiplier)
            if remaining + 1e-9 < cost:
                return multiplier, remaining, cost
            remaining -= cost
            multiplier = round(multiplier + 0.1, 1)
        return multiplier, remaining, self.recruit_step_cost(multiplier)

    @property
    def recruit_progress_fraction(self) -> float:
        _, progress, cost = self.recruit_state()
        return min(1.0, progress / cost) if cost > 0 else 0.0

    def take_special_damage(self, damage: float) -> None:
        damage = max(0.0, damage)
        if self.hp > 0:
            self.hp -= damage
            if self.hp <= 0:
                if self.buff == "population":
                    self.recruit_progress += -self.hp
                self.hp = 0
        elif self.buff == "population":
            self.recruit_progress += damage


@dataclass
class Boss:
    position: pygame.Vector2
    kind: str
    hp: float
    max_hp: float
    speed: float
    reward: int
    radius: int
    attack_range: float = 175.0
    windup_duration: float = 2.0
    windup_remaining: float | None = None
    shoot_timer: float = 1.5
    windup_move_factor: float = 0.10

    def update(self, dt: float, player: pygame.Vector2) -> bool:
        if self.kind != "big":
            self.position.y += self.speed * dt
            return False
        if self.windup_remaining is not None:
            self.position += normalized(player - self.position) * self.speed * self.windup_move_factor * dt
            self.windup_remaining -= dt
            if self.windup_remaining <= 0:
                hit_player = self.position.distance_to(player) <= self.attack_range
                self.windup_remaining = None
                return hit_player
            return False
        if self.position.distance_to(player) <= self.attack_range:
            self.windup_remaining = self.windup_duration
        else:
            self.position += normalized(player - self.position) * self.speed * dt
        return False


@dataclass(frozen=True)
class OwnedCard:
    key: str
    enhancement: str
    acquired_world: int
    wholesale_purchase: bool = False
    wholesale_sale_price: int | None = None
    acquired_shop_round: int = 0
    instance_id: int = field(default_factory=lambda: next(_owned_card_ids))


@dataclass
class EffectRuntime:
    triggers: int = 0
    stacks: float = 0.0
    remaining: float = 0.0
    interval_remaining: float = 0.0
    cooldown_remaining: float = 0.0


@dataclass(frozen=True)
class ShopOffer:
    card: Card | None = None
    enhancement: str = ""
    overload_category: str = ""
    exchange_value: int = 0

    @property
    def is_overload(self) -> bool:
        return bool(self.overload_category)


class Game:
    _audio_cache: tuple[object, ...] | None = None

    def __init__(self, show_main_menu: bool = False) -> None:
        os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_WARP", "0")
        pygame.mixer.pre_init(44100, -16, 2, 256)
        pygame.init()
        pygame.display.set_caption("双线火力 - 八世界原型")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_tiny = load_font(16)
        self.font_small = load_font(20)
        self.font = load_font(26)
        self.font_large = load_font(42, True)
        self.font_huge = load_font(68, True)
        self.rng = random.Random()
        self.audio_rng = random.Random()
        self.cursor_rng = random.Random()
        self.running = True
        self.mouse_sensitivity = 1.0
        self.aim_position = pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        self.mouse_sensitivity_editing = False
        self.sensitivity_input_text = ""
        self.dev_panel_open = False
        self.dev_editing_field: str | None = None
        self.dev_input_text = ""
        self.cursor_time = 0.0
        self.cursor_phase = 0.0
        self.cursor_trail: list[tuple[float, pygame.Vector2]] = []
        self.cursor_particles: list[CursorParticle] = []
        self.cursor_spawn_timer = 0.0
        self.last_cursor_pos: pygame.Vector2 | None = None
        self.sfx_volume = 0.7
        self.bgm_volume = 0.4
        self.effect_volumes = {
            "shot": 1.0,
            "enemy_hit": 1.0,
            "kill": 1.0,
            "gate_hit": 1.0,
            "gate_collect": 1.0,
        }
        self.audio_available = False
        self.shot_sound: pygame.mixer.Sound | None = None
        self.kill_sounds: tuple[pygame.mixer.Sound, ...] = ()
        self.enemy_hit_sound: pygame.mixer.Sound | None = None
        self.gate_hit_sound: pygame.mixer.Sound | None = None
        self.gate_collect_sound: pygame.mixer.Sound | None = None
        self.bgm_tracks: tuple[pygame.mixer.Sound, ...] = ()
        self.bgm_channels: tuple[pygame.mixer.Channel, ...] = ()
        self.bgm_track_index = 0
        self.bgm_elapsed = 0.0
        self.initialize_audio()
        self.reset_run()
        if show_main_menu:
            self.mode = Mode.MAIN_MENU
            self.sync_mouse_mode()

    def initialize_audio(self) -> None:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(44100, -16, 2, 256)
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            pygame.mixer.set_reserved(4)
            if Game._audio_cache is None:
                Game._audio_cache = (
                    pygame.mixer.Sound(asset_path("SFX/shot1.mp3")),
                    (
                        pygame.mixer.Sound(asset_path("BGM/Neon Pixel Dash.mp3")),
                        pygame.mixer.Sound(asset_path("BGM/Neon Pixel Dash_1.mp3")),
                    ),
                    (
                        pygame.mixer.Sound(asset_path("SFX/kill1.mp3")),
                        pygame.mixer.Sound(asset_path("SFX/kill2.mp3")),
                    ),
                    pygame.mixer.Sound(asset_path("SFX/enemy_hit.wav")),
                    pygame.mixer.Sound(asset_path("SFX/gate_hit.wav")),
                    pygame.mixer.Sound(asset_path("SFX/gate_collect.wav")),
                )
            (
                self.shot_sound,
                self.bgm_tracks,
                self.kill_sounds,
                self.enemy_hit_sound,
                self.gate_hit_sound,
                self.gate_collect_sound,
            ) = Game._audio_cache
            self.shot_channel = pygame.mixer.Channel(2)
            self.kill_channel = pygame.mixer.Channel(3)
            self.bgm_channels = (pygame.mixer.Channel(0), pygame.mixer.Channel(1))
            self.audio_available = True
            self.apply_audio_volumes()
            self.bgm_channels[0].play(self.bgm_tracks[0])
        except (FileNotFoundError, pygame.error):
            self.audio_available = False

    def apply_audio_volumes(self) -> None:
        if not self.audio_available:
            return
        self.shot_channel.set_volume(self.effective_sfx_volume("shot"))
        self.kill_channel.set_volume(self.effective_sfx_volume("kill"))
        for channel in self.bgm_channels:
            channel.set_volume(self.bgm_volume)

    def effective_sfx_volume(self, kind: str) -> float:
        return self.sfx_volume * self.effect_volumes[kind]

    def volume_value(self, kind: str) -> float:
        if kind == "bgm":
            return self.bgm_volume
        if kind == "sfx":
            return self.sfx_volume
        return self.effect_volumes[kind]

    def adjust_volume(self, kind: str, direction: int) -> None:
        value = max(0.0, min(1.0, self.volume_value(kind) + direction * 0.1))
        value = round(value, 1)
        if kind == "bgm":
            self.bgm_volume = value
        elif kind == "sfx":
            self.sfx_volume = value
        else:
            self.effect_volumes[kind] = value
        self.apply_audio_volumes()

    def load_settings(self) -> None:
        try:
            data = json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        try:
            self.bgm_volume = max(0.0, min(1.0, float(data.get("bgm_volume", self.bgm_volume))))
            self.sfx_volume = max(0.0, min(1.0, float(data.get("sfx_volume", self.sfx_volume))))
            effects = data.get("effect_volumes")
            if isinstance(effects, dict):
                for key in self.effect_volumes:
                    if key in effects:
                        self.effect_volumes[key] = max(
                            0.0, min(1.0, float(effects[key]))
                        )
            self.mouse_sensitivity = max(
                0.1, min(5.0, float(data.get("mouse_sensitivity", self.mouse_sensitivity)))
            )
        except (TypeError, ValueError):
            return

    def save_settings(self) -> None:
        data = {
            "bgm_volume": self.bgm_volume,
            "sfx_volume": self.sfx_volume,
            "effect_volumes": dict(self.effect_volumes),
            "mouse_sensitivity": self.mouse_sensitivity,
        }
        try:
            settings_path().parent.mkdir(parents=True, exist_ok=True)
            settings_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def play_shot_sound(self, fire_rate: float) -> None:
        if not self.audio_available or self.shot_sound is None:
            return
        interval_ms = max(10, round(1000.0 / max(0.000001, fire_rate)))
        self.shot_channel.play(self.shot_sound, maxtime=interval_ms)

    def play_effect_sound(self, sound: pygame.mixer.Sound | None, kind: str) -> None:
        if not self.audio_available or sound is None:
            return
        channel = pygame.mixer.find_channel()
        if channel is not None:
            channel.set_volume(self.effective_sfx_volume(kind))
            channel.play(sound)

    def play_kill_sound(self) -> None:
        if not self.audio_available or not self.kill_sounds:
            return
        self.kill_channel.set_volume(self.effective_sfx_volume("kill"))
        self.kill_channel.play(self.audio_rng.choice(self.kill_sounds))

    def update_audio(self, dt: float) -> None:
        if not self.audio_available or not self.bgm_tracks:
            return
        self.bgm_elapsed += dt
        # Both tracks are 148 BPM. These beat-aligned points precede their fade-out tails.
        transition_times = (86.90, 101.35)
        if self.bgm_elapsed < transition_times[self.bgm_track_index]:
            return
        old_channel = self.bgm_channels[self.bgm_track_index % 2]
        self.bgm_track_index = (self.bgm_track_index + 1) % len(self.bgm_tracks)
        new_channel = self.bgm_channels[self.bgm_track_index % 2]
        crossfade_ms = 405
        old_channel.fadeout(crossfade_ms)
        new_channel.set_volume(self.bgm_volume)
        new_channel.play(self.bgm_tracks[self.bgm_track_index], fade_ms=crossfade_ms)
        self.bgm_elapsed = 0.0

    def reset_run(self) -> None:
        self.run_id = create_run_id()
        self.balance_log_error = ""
        self.world = 1
        self.gold = 0
        self.total_kills = 0
        self.rapid_reload_kills = 0
        self.equipped_cards: list[OwnedCard] = []
        self.overload_cards: list[OwnedCard] = []
        self.effect_runtime: dict[tuple[int, int], EffectRuntime] = {}
        self.attribute_purchases = {"population": 0, "damage": 0, "fire_rate": 0}
        self.default_population = 1
        self.default_damage = 10.0
        self.default_fire_rate = 8.0
        self.shop_offers: list[ShopOffer] = []
        self.refresh_cost = 0
        self.detail_card: OwnedCard | None = None
        self.shop_round = 0
        self.card_page = "normal"
        self.dragging_card: OwnedCard | None = None
        self.dragging_from = ""
        self.death_reason = ""
        self.start_world()

    def start_world(self) -> None:
        self.mode = Mode.PLAYING
        self.player = pygame.Vector2(WIDTH / 2, HEIGHT - 90)
        self.player_radius = 22
        self.population = round(self.apply_stat(self.default_population, "starting_population", TARGET_PLAYER))
        self.population += sum(5 for owned in self.equipped_cards if owned.enhancement == "population")
        self.population_peak = self.population
        self.elapsed = 0.0
        self.enemy_timer = 1.0
        self.elite_timer = 18.0
        self.gate_timer = 2.0
        self.fire_timer = 0.0
        self.shot_streak = 0.0
        self.still_time = 0.0
        self.composure_idle_time = 0.0
        self.composure_release_timer = 0.0
        self.composure_damage_bonus = 0.0
        self.composure_gate_bonus = 0.0
        self.rage_timer = 0.0
        self.medicine_timer = 30.0
        self.special_times = [15.0, 48.0, 76.0]
        self.special_spawned = 0
        self.small_boss_time = self.rng.uniform(25.0, 30.0)
        self.small_spawned = False
        self.medium_spawned = False
        self.big_spawned = False
        self.bullets: list[Bullet] = []
        self.enemy_bullets: list[EnemyBullet] = []
        self.enemies: list[Enemy] = []
        self.gates: list[Gate] = []
        self.bosses: list[Boss] = []
        self.temp_damage_bonus = 0.0
        self.temp_fire_rate_bonus = 0.0
        self.temp_buff_timer = 0.0
        self.message = f"世界 {self.world}/8：120秒内击杀90秒出现的大Boss"
        self.message_timer = 5.0
        self.world_start_kills = self.total_kills
        self.reset_world_effect_runtime()
        self.dispatch_effect_event("on_world_start")
        self.world_start_snapshot = self.combat_snapshot()
        self.aim_position = pygame.Vector2(self.player.x, self.player.y - 170)
        self.cursor_time = 0.0
        self.cursor_phase = 0.0
        self.cursor_trail = []
        self.cursor_particles = []
        self.cursor_spawn_timer = 0.0
        self.last_cursor_pos = None
        self.sync_mouse_mode()

    def iter_effects(
        self,
        *,
        action: str | None = None,
        stat: str | None = None,
        target: int | None = None,
        trigger: str | None = None,
    ):
        for owned in self.all_owned_cards():
            for index, effect in enumerate(CARD_BY_KEY[owned.key].effects):
                if action is not None and effect.action != action:
                    continue
                if stat is not None and effect.stat != stat:
                    continue
                if target is not None and not effect.targets.includes(target):
                    continue
                if trigger is not None and effect.trigger != trigger:
                    continue
                yield owned, index, effect

    def effect_state(self, owned: OwnedCard, index: int) -> EffectRuntime:
        return self.effect_runtime.setdefault((owned.instance_id, index), EffectRuntime())

    def all_owned_cards(self) -> tuple[OwnedCard, ...]:
        return tuple(self.equipped_cards) + tuple(self.overload_cards)

    def owned_card(self, key: str) -> OwnedCard | None:
        return next((owned for owned in self.all_owned_cards() if owned.key == key), None)

    def growth_level(self, card: str | OwnedCard) -> int:
        owned = card if isinstance(card, OwnedCard) else self.owned_card(card)
        return max(1, self.world - owned.acquired_world) if owned else 0

    def state_value(self, name: str) -> float:
        return float({"population": self.population, "gold": self.gold, "kills": self.total_kills}.get(name, 0.0))

    def effect_condition_met(self, effect: CardEffect, context: dict[str, object]) -> bool:
        boss_kind = effect.parameters.get("boss_kind")
        if boss_kind is not None and context.get("boss_kind") != boss_kind:
            return False
        condition_stat = effect.parameters.get("condition_stat")
        if not isinstance(condition_stat, str):
            return True
        left = self.state_value(condition_stat)
        right = float(effect.parameters.get("condition_value", 0.0))
        comparison = effect.parameters.get("comparison", "greater_equal")
        return {
            "less": left < right,
            "less_equal": left <= right,
            "equal": left == right,
            "greater_equal": left >= right,
            "greater": left > right,
        }.get(str(comparison), False)

    def effect_value(
        self,
        owned: OwnedCard,
        index: int,
        effect: CardEffect,
        context: dict[str, object],
    ) -> float | None:
        if not self.effect_condition_met(effect, context):
            return None
        trigger = effect.trigger
        elapsed = 0.0
        if trigger == "while_moving" and not context.get("moving", False):
            return None
        if trigger == "while_still":
            elapsed = self.still_time
        elif trigger == "while_firing":
            elapsed = self.shot_streak
        elif trigger == "while_not_firing":
            if context.get("exclude_composure", False):
                return None
            elapsed = self.composure_idle_time
        elif trigger == "interval" and effect.action in {"modify_stat", "growth_modifier"}:
            if self.effect_state(owned, index).remaining <= 0:
                return None
        elif trigger.startswith("on_") and effect.action in {"modify_stat", "growth_modifier"}:
            state = self.effect_state(owned, index)
            if "duration" in effect.parameters and state.remaining <= 0:
                return None
            if not {"triggers_per_stack", "stacks_per_trigger", "duration"}.intersection(effect.parameters):
                return None

        value = float(effect.parameters.get("value", 0.0))
        if effect.action == "growth_modifier":
            value *= self.growth_level(owned)
        if "scale_stat" in effect.parameters:
            step = max(0.000001, float(effect.parameters.get("step", 1.0)))
            steps = math.floor(self.state_value(str(effect.parameters["scale_stat"])) / step)
            value += steps * float(effect.parameters.get("value_per_step", 0.0))
        if "triggers_per_stack" in effect.parameters:
            triggers_per_stack = max(1, int(effect.parameters["triggers_per_stack"]))
            stacks = self.effect_state(owned, index).triggers // triggers_per_stack
            if "max_stacks" in effect.parameters:
                stacks = min(stacks, float(effect.parameters["max_stacks"]))
            value += stacks * float(effect.parameters.get("value_per_stack", 0.0))
        if "stacks_per_trigger" in effect.parameters:
            stacks = self.effect_state(owned, index).stacks
            if "max_stacks" in effect.parameters:
                stacks = min(stacks, float(effect.parameters["max_stacks"]))
            value += stacks * float(effect.parameters.get("value_per_stack", 0.0))
        if trigger == "while_firing":
            value += elapsed * float(effect.parameters.get("value_per_second", 0.0))
        if trigger in {"while_still", "while_not_firing"}:
            delay = max(0.0, float(effect.parameters.get("delay", 0.0)))
            if elapsed < delay:
                return None
            value += float(effect.parameters.get("initial_value", 0.0))
            interval = max(0.000001, float(effect.parameters.get("interval", 1.0)))
            value += math.floor((elapsed - delay + 1e-9) / interval) * float(
                effect.parameters.get("value_per_interval", 0.0)
            )
        if "cap" in effect.parameters:
            cap = abs(float(effect.parameters["cap"]))
            value = max(-cap, min(cap, value))
        return value

    def effect_values(
        self,
        stat: str,
        target: int,
        context: dict[str, object] | None = None,
        actions: set[str] | None = None,
        include_triggers: set[str] | None = None,
        exclude_triggers: set[str] | None = None,
    ) -> list[tuple[CardEffect, float]]:
        context = context or {}
        actions = actions or {"modify_stat", "growth_modifier"}
        entries: list[tuple[CardEffect, float]] = []
        for owned, index, effect in self.iter_effects(stat=stat, target=target):
            if effect.action not in actions:
                continue
            if include_triggers is not None and effect.trigger not in include_triggers:
                continue
            if exclude_triggers is not None and effect.trigger in exclude_triggers:
                continue
            value = self.effect_value(owned, index, effect, context)
            if value is not None:
                entries.append((effect, value))

        grouped: dict[str, tuple[CardEffect, float]] = {}
        ungrouped: list[tuple[CardEffect, float]] = []
        for entry in entries:
            effect, _ = entry
            if effect.exclusive_group:
                previous = grouped.get(effect.exclusive_group)
                if previous is None or effect.priority > previous[0].priority:
                    grouped[effect.exclusive_group] = entry
            else:
                ungrouped.append(entry)
        entries = ungrouped + list(grouped.values())

        highest = [entry for entry in entries if entry[0].stacking == "highest"]
        lowest = [entry for entry in entries if entry[0].stacking == "lowest"]
        replace_entries = [entry for entry in entries if entry[0].stacking == "replace"]
        entries = [entry for entry in entries if entry[0].stacking not in {"highest", "lowest", "replace"}]
        if highest:
            entries.append(max(highest, key=lambda entry: entry[1]))
        if lowest:
            entries.append(min(lowest, key=lambda entry: entry[1]))
        if replace_entries:
            entries.append(max(replace_entries, key=lambda entry: entry[0].priority))
        return sorted(entries, key=lambda entry: entry[0].priority)

    def apply_stat(
        self,
        base: float,
        stat: str,
        target: int,
        context: dict[str, object] | None = None,
        actions: set[str] | None = None,
        include_triggers: set[str] | None = None,
        exclude_triggers: set[str] | None = None,
    ) -> float:
        result = float(base)
        base_reference = float(base)
        for effect, value in self.effect_values(
            stat,
            target,
            context,
            actions,
            include_triggers,
            exclude_triggers,
        ):
            if effect.operator == "add_flat":
                result += value
            elif effect.operator == "add_percent":
                if effect.stacking == "multiply":
                    result *= 1.0 + value
                else:
                    result += base_reference * value
            elif effect.operator == "multiply":
                result *= value
            elif effect.operator == "set":
                result = value
            elif effect.operator == "minimum":
                result = max(result, value)
            elif effect.operator == "maximum":
                result = min(result, value)
        return result

    def has_rule(self, stat: str, target: int = TARGET_PLAYER) -> bool:
        return any(
            bool(effect.parameters.get("enabled", True))
            for _, _, effect in self.iter_effects(action="set_rule", stat=stat, target=target)
        )

    def has_stat_effect(self, stat: str, target: int = TARGET_PLAYER) -> bool:
        return any(True for _ in self.iter_effects(stat=stat, target=target))

    def apply_resource_effect(self, owned: OwnedCard, effect: CardEffect) -> int:
        if not effect.targets.player or effect.stat not in {"gold", "population"}:
            return 0
        current = self.gold if effect.stat == "gold" else self.population
        value = float(effect.parameters.get("value", 0.0))
        value += self.growth_level(owned) * float(effect.parameters.get("per_world", 0.0))
        if effect.operator == "add_percent":
            amount = math.floor(current * value)
        else:
            amount = round(value)
        if "cap" in effect.parameters:
            cap = abs(round(float(effect.parameters["cap"])))
            amount = max(-cap, min(cap, amount))
        if effect.operator == "set":
            amount -= current
        if effect.stat == "gold":
            self.gold += amount
        else:
            self.population += amount
        return amount

    def effect_event_ready(
        self,
        owned: OwnedCard,
        index: int,
        effect: CardEffect,
        event_target: int | None = None,
    ) -> bool:
        trigger_target = effect.parameters.get("trigger_target")
        if trigger_target is not None and event_target is not None and int(trigger_target) != event_target:
            return False
        if not self.effect_condition_met(effect, {}):
            return False
        state = self.effect_state(owned, index)
        if state.cooldown_remaining > 0:
            return False
        chance = max(0.0, min(1.0, float(effect.parameters.get("chance", 1.0))))
        if self.rng.random() >= chance:
            return False
        state.cooldown_remaining = max(0.0, float(effect.parameters.get("cooldown", 0.0)))
        return True

    def dispatch_effect_event(self, trigger: str, event_target: int | None = None) -> dict[str, int]:
        changes = {"gold": 0, "population": 0}
        for owned, index, effect in self.iter_effects(trigger=trigger):
            if effect.action not in {"grant_resource", "modify_stat", "growth_modifier"}:
                continue
            if not self.effect_event_ready(owned, index, effect, event_target):
                continue
            message = effect.parameters.get("message")
            if isinstance(message, str) and message:
                self.message = message
                self.message_timer = 2.0
            if effect.action == "grant_resource":
                changes[effect.stat] += self.apply_resource_effect(owned, effect)
            elif effect.action in {"modify_stat", "growth_modifier"}:
                state = self.effect_state(owned, index)
                state.triggers += 1
                state.stacks += float(effect.parameters.get("stacks_per_trigger", 0.0))
                if "duration" in effect.parameters:
                    state.remaining = max(state.remaining, float(effect.parameters["duration"]))
        return changes

    def reset_world_effect_runtime(self) -> None:
        for owned, index, effect in self.iter_effects():
            state = self.effect_state(owned, index)
            state.remaining = 0.0
            if bool(effect.parameters.get("clear_on_world", False)):
                state.triggers = 0
                state.stacks = 0.0
            if effect.trigger == "interval":
                state.interval_remaining = float(effect.parameters["interval"])

    def update_effect_runtime(self, dt: float) -> None:
        for state in self.effect_runtime.values():
            state.remaining = max(0.0, state.remaining - dt)
            state.cooldown_remaining = max(0.0, state.cooldown_remaining - dt)
        for owned, index, effect in self.iter_effects(trigger="interval"):
            state = self.effect_state(owned, index)
            interval = max(0.001, float(effect.parameters["interval"]))
            if state.interval_remaining <= 0:
                state.interval_remaining = interval
            state.interval_remaining -= dt
            if state.interval_remaining <= 0:
                if not self.effect_event_ready(owned, index, effect):
                    state.interval_remaining += interval
                    continue
                if effect.action == "periodic_resource":
                    self.apply_resource_effect(owned, effect)
                elif effect.action in {"modify_stat", "growth_modifier"}:
                    state.triggers += 1
                    state.stacks += float(effect.parameters.get("stacks_per_trigger", 0.0))
                    state.remaining = max(
                        state.remaining,
                        float(effect.parameters.get("duration", interval)),
                    )
                state.interval_remaining += interval

    def clear_movement_effect_stacks(self) -> None:
        for owned, index, effect in self.iter_effects():
            if bool(effect.parameters.get("clear_on_move", False)):
                state = self.effect_state(owned, index)
                state.triggers = 0
                state.stacks = 0.0

    def enhancement_count(self, enhancement: str) -> int:
        return sum(1 for owned in self.equipped_cards if owned.enhancement == enhancement)

    def current_move_speed(self) -> float:
        return max(0.0, self.apply_stat(320.0, "move_speed", TARGET_PLAYER))

    def current_fire_rate(self) -> float:
        rate = self.apply_stat(self.default_fire_rate, "fire_rate", TARGET_PLAYER)
        rate += self.default_fire_rate * (
            self.temp_fire_rate_bonus + self.enhancement_count("fire_rate") * 0.10
        )
        rate += self.apply_stat(0.0, "fire_rate_correction", TARGET_PLAYER)
        return max(0.0, rate)

    def volley_profile(self) -> tuple[int, float, float]:
        patterns = list(self.iter_effects(action="projectile_pattern", target=TARGET_PLAYER))
        if patterns:
            _, _, effect = max(patterns, key=lambda item: item[2].priority)
            return (
                max(1, int(effect.parameters["count"])),
                float(effect.parameters["spread"]),
                float(effect.parameters["damage_scale"]),
            )
        return 1, 0.0, 1.0

    def current_volley_multiplier(self) -> float:
        projectiles, _, damage_scale = self.volley_profile()
        return projectiles * damage_scale

    def critical_chance(self) -> float:
        return max(0.0, min(1.0, self.apply_stat(0.0, "critical_chance", TARGET_PLAYER)))

    def critical_damage_multiplier(self) -> float:
        return max(1.0, self.apply_stat(1.5, "critical_multiplier", TARGET_PLAYER))

    def expected_critical_multiplier(self) -> float:
        chance = self.critical_chance()
        return 1.0 + chance * (self.critical_damage_multiplier() - 1.0)

    def roll_critical_multiplier(self) -> float:
        if self.rng.random() < self.critical_chance():
            return self.critical_damage_multiplier()
        return 1.0

    def calm_aim_bonus(self) -> float:
        multiplier = self.apply_stat(
            1.0,
            "damage_dealt",
            TARGET_PLAYER,
            include_triggers={"while_still"},
        )
        return multiplier - 1.0

    def update_still_time(self, dt: float, moving: bool) -> None:
        if moving and not self.has_rule("moving_counts_as_still"):
            self.still_time = 0.0
        else:
            self.still_time += dt

    def current_pierces(self) -> int:
        return max(0, round(self.apply_stat(0.0, "projectile_pierce", TARGET_PLAYER)))

    def current_bounces(self) -> int:
        return max(0, round(self.apply_stat(0.0, "projectile_bounces", TARGET_PLAYER)))

    @staticmethod
    def _disable_relative_mouse() -> None:
        try:
            pygame.mouse.set_relative_mode(False)
        except pygame.error:
            pass

    def sync_mouse_mode(self) -> None:
        """Hide the OS cursor in game and enable raw relative mouse mode."""
        if self.mode == Mode.PLAYING:
            try:
                pygame.mouse.set_relative_mode(True)
                if self.aim_position.x == 0 and self.aim_position.y == 0:
                    self.aim_position = self.player + pygame.Vector2(0, -170)
                pygame.mouse.get_rel()
            except pygame.error:
                self._disable_relative_mouse()
                pygame.mouse.set_visible(False)
            return
        self._disable_relative_mouse()
        pygame.mouse.set_visible(True)

    def current_mouse_position(self) -> pygame.Vector2:
        if self.mode == Mode.PLAYING and pygame.mouse.get_relative_mode():
            return self.aim_position.copy()
        return pygame.Vector2(pygame.mouse.get_pos())

    def aim_direction(self) -> pygame.Vector2:
        return normalized(self.current_mouse_position() - self.player)

    def adjust_mouse_sensitivity(self, direction: int) -> None:
        self.mouse_sensitivity = round(
            max(0.1, min(5.0, self.mouse_sensitivity + direction * 0.1)), 1
        )

    def begin_mouse_sensitivity_edit(self) -> None:
        self.mouse_sensitivity_editing = True
        self.sensitivity_input_text = f"{self.mouse_sensitivity:g}"

    def commit_mouse_sensitivity(self) -> None:
        try:
            value = float(self.sensitivity_input_text.strip())
        except ValueError:
            value = self.mouse_sensitivity
        self.mouse_sensitivity = round(max(0.1, min(5.0, value)), 1)
        self.mouse_sensitivity_editing = False
        self.sensitivity_input_text = ""

    @staticmethod
    def _digit_key_char(key: int) -> str | None:
        if pygame.K_0 <= key <= pygame.K_9:
            return chr(key)
        if pygame.K_KP0 <= key <= pygame.K_KP9:
            return str(key - pygame.K_KP0)
        if key in (pygame.K_PERIOD, pygame.K_KP_PERIOD):
            return "."
        return None

    def toggle_dev_panel(self) -> None:
        self.dev_panel_open = not self.dev_panel_open
        self.dev_editing_field = None
        self.dev_input_text = ""
        if self.dev_panel_open:
            self._disable_relative_mouse()
            pygame.mouse.set_visible(True)
        else:
            self.sync_mouse_mode()

    def dev_field_specs(self) -> tuple[tuple[str, str, bool, float, float, float, str], ...]:
        return (
            ("gold", "金币", True, 0, 999_999_999, 100, "int"),
            ("population", "人口 / 血量", True, 1, 999_999_999, 100, "int"),
            ("default_population", "初始人口", True, 1, 999, 1, "int"),
            ("default_damage", "基础伤害", False, 0.0, 9_999.0, 1.0, "float"),
            ("default_fire_rate", "基础射速", False, 0.0, 9_999.0, 1.0, "float"),
            ("world", "世界", True, 1, 8, 1, "int"),
            ("elapsed", "关卡秒数", False, 0.0, WORLD_DURATION, 5.0, "float"),
        )

    def dev_value(self, key: str) -> float:
        return float(
            {
                "gold": self.gold,
                "population": self.population,
                "default_population": self.default_population,
                "default_damage": self.default_damage,
                "default_fire_rate": self.default_fire_rate,
                "world": self.world,
                "elapsed": self.elapsed,
            }[key]
        )

    def dev_set_value(self, key: str, value: float) -> None:
        if key == "gold":
            self.gold = int(round(value))
        elif key == "population":
            self.population = int(round(value))
            self.population_peak = max(self.population_peak, self.population)
        elif key == "default_population":
            self.default_population = int(round(value))
        elif key == "default_damage":
            self.default_damage = round(value, 2)
        elif key == "default_fire_rate":
            self.default_fire_rate = round(value, 2)
        elif key == "world":
            self.world = int(round(value))
        elif key == "elapsed":
            self.elapsed = round(value, 2)

    def dev_format_value(self, key: str, value: float, kind: str) -> str:
        if kind == "int":
            return f"{int(round(value)):,}"
        return f"{value:.1f}"

    def dev_raw_value_text(self, key: str) -> str:
        return f"{self.dev_value(key):g}"

    def dev_begin_edit(self, key: str) -> None:
        self.dev_editing_field = key
        self.dev_input_text = self.dev_raw_value_text(key)

    def dev_commit_edit(self) -> None:
        if self.dev_editing_field is None:
            return
        key = self.dev_editing_field
        spec = next(spec for spec in self.dev_field_specs() if spec[0] == key)
        _, _, is_int, minimum, maximum, _, _ = spec
        try:
            value = float(self.dev_input_text.strip())
        except ValueError:
            value = self.dev_value(key)
        if is_int:
            value = round(value)
        value = max(minimum, min(maximum, value))
        self.dev_set_value(key, value)
        self.dev_editing_field = None
        self.dev_input_text = ""

    def dev_step_value(self, key: str, direction: int) -> None:
        spec = next(spec for spec in self.dev_field_specs() if spec[0] == key)
        _, _, is_int, minimum, maximum, step, _ = spec
        value = self.dev_value(key) + direction * step
        if is_int:
            value = round(value)
        value = max(minimum, min(maximum, value))
        self.dev_set_value(key, value)

    def dev_skip_to_shop(self) -> None:
        if self.world >= 8:
            self.mode = Mode.VICTORY
            self.sync_mouse_mode()
        else:
            self.enter_shop()

    def dev_clear_enemies(self) -> None:
        self.enemies.clear()
        self.bosses.clear()
        self.gates.clear()
        self.enemy_bullets.clear()

    @staticmethod
    def dev_panel_rect() -> pygame.Rect:
        return pygame.Rect(160, 30, 960, 690)

    @staticmethod
    def dev_field_value_rect(index: int) -> pygame.Rect:
        return pygame.Rect(460, 128 + index * 58, 260, 42)

    @staticmethod
    def dev_field_button_rect(index: int, direction: int) -> pygame.Rect:
        return pygame.Rect(740 if direction < 0 else 800, 128 + index * 58, 46, 42)

    @staticmethod
    def dev_action_button_rect(row: int, column: int) -> pygame.Rect:
        widths = (300, 210, 160, 150) if row == 0 else (200, 200, 180, 240)
        x = 220
        gap = 20
        for index in range(column):
            x += widths[index] + gap
        return pygame.Rect(x, 522 + row * 66, widths[column], 52)

    def handle_dev_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_F1):
                self.toggle_dev_panel()
                return
            if self.dev_editing_field is not None:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.dev_commit_edit()
                elif event.key == pygame.K_BACKSPACE:
                    self.dev_input_text = self.dev_input_text[:-1]
                else:
                    char = self._digit_key_char(event.key)
                    if char is not None:
                        if char == "." and "." in self.dev_input_text:
                            return
                        self.dev_input_text += char
                return
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        specs = self.dev_field_specs()
        value_rects = [self.dev_field_value_rect(index) for index in range(len(specs))]
        if self.dev_editing_field is not None and not any(
            rect.collidepoint(event.pos) for rect in value_rects
        ):
            self.dev_commit_edit()

        for index, spec in enumerate(specs):
            if self.dev_field_value_rect(index).collidepoint(event.pos):
                self.dev_begin_edit(spec[0])
                return
            if self.dev_field_button_rect(index, -1).collidepoint(event.pos):
                self.dev_step_value(spec[0], -1)
                return
            if self.dev_field_button_rect(index, 1).collidepoint(event.pos):
                self.dev_step_value(spec[0], 1)
                return

        if self.dev_action_button_rect(0, 0).collidepoint(event.pos):
            self.dev_skip_to_shop()
        elif self.dev_action_button_rect(0, 1).collidepoint(event.pos):
            self.dev_clear_enemies()
        elif self.dev_action_button_rect(0, 2).collidepoint(event.pos):
            self.gold += 10_000
        elif self.dev_action_button_rect(0, 3).collidepoint(event.pos):
            self.population += 10_000
            self.population_peak = max(self.population_peak, self.population)
        elif self.dev_action_button_rect(1, 0).collidepoint(event.pos):
            self.default_damage += 100.0
        elif self.dev_action_button_rect(1, 1).collidepoint(event.pos):
            self.default_fire_rate += 10.0
        elif self.dev_action_button_rect(1, 2).collidepoint(event.pos):
            self.world = min(8, self.world + 1)
        elif self.dev_action_button_rect(1, 3).collidepoint(event.pos):
            self.toggle_dev_panel()

    def draw_dev_panel(self) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 7, 12, 215))
        self.screen.blit(shade, (0, 0))

        panel = self.dev_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=16)
        pygame.draw.rect(self.screen, CYAN, panel, 3, border_radius=16)

        self.blit_text("开发者测试面板", (panel.x + 40, panel.y + 22), WHITE, self.font_large)
        self.blit_text("点击数值可直接输入，± 按钮步进调整；F1 / Esc 关闭", (panel.x + 40, panel.y + 70), MUTED, self.font_small)

        for index, spec in enumerate(self.dev_field_specs()):
            key, label, _, _, _, _, kind = spec
            y = 128 + index * 58
            self.blit_text(label, (panel.x + 40, y + 8), WHITE, self.font_small)
            value_rect = self.dev_field_value_rect(index)
            pygame.draw.rect(self.screen, GRID, value_rect, border_radius=8)
            if self.dev_editing_field == key:
                pygame.draw.rect(self.screen, YELLOW, value_rect, 2, border_radius=8)
                display = self.dev_input_text + ("_" if (pygame.time.get_ticks() // 500) % 2 == 0 else "")
            else:
                display = self.dev_format_value(key, self.dev_value(key), kind)
            value_surface = self.font_small.render(display, True, WHITE)
            self.screen.blit(value_surface, (value_rect.x + 12, value_rect.y + 9))
            for direction in (-1, 1):
                button_rect = self.dev_field_button_rect(index, direction)
                pygame.draw.rect(self.screen, GRID, button_rect, border_radius=8)
                pygame.draw.rect(self.screen, MUTED, button_rect, 2, border_radius=8)
                text = "-" if direction < 0 else "+"
                label_surface = self.font.render(text, True, CYAN)
                self.screen.blit(label_surface, label_surface.get_rect(center=button_rect.center))

        action_specs = (
            ("结束本世界 → 商店", GREEN, 0, 0),
            ("清空场上敌人", BLUE, 0, 1),
            ("金币 +10,000", YELLOW, 0, 2),
            ("人口 +10,000", CYAN, 0, 3),
            ("伤害 +100", ORANGE, 1, 0),
            ("射速 +10", PURPLE, 1, 1),
            ("世界 +1", WHITE, 1, 2),
            ("关闭面板", RED, 1, 3),
        )
        for text, color, row, column in action_specs:
            rect = self.dev_action_button_rect(row, column)
            pygame.draw.rect(self.screen, GRID, rect, border_radius=10)
            pygame.draw.rect(self.screen, color, rect, 2, border_radius=10)
            label_surface = self.font_small.render(text, True, color)
            self.screen.blit(label_surface, label_surface.get_rect(center=rect.center))

        readout = (
            f"当前伤害 {self.current_damage():.1f}  |  "
            f"当前射速 {self.current_fire_rate():.1f}/s  |  "
            f"理论DPS {format_number(self.current_dps())}"
        )
        self.blit_text(readout, (panel.x + 40, panel.bottom - 46), CYAN, self.font_small)

    def update_cursor_effects(self, dt: float, position: pygame.Vector2) -> None:
        self.cursor_time += dt
        self.cursor_phase += dt
        self.cursor_trail.append((self.cursor_time, position.copy()))
        while len(self.cursor_trail) > CURSOR_TRAIL_CAP:
            self.cursor_trail.pop(0)
        while self.cursor_trail and self.cursor_time - self.cursor_trail[0][0] > CURSOR_TRAIL_MAX_AGE:
            self.cursor_trail.pop(0)

        speed = 0.0
        if self.last_cursor_pos is not None and dt > 0:
            speed = position.distance_to(self.last_cursor_pos) / dt
        self.last_cursor_pos = position.copy()

        self.cursor_spawn_timer -= dt
        if self.cursor_spawn_timer <= 0:
            count = 1 if speed < 120 else 2 if speed < 360 else 4
            for _ in range(count):
                if len(self.cursor_particles) < CURSOR_PARTICLE_CAP:
                    self.cursor_particles.append(self._make_cursor_spark(position))
            self.cursor_spawn_timer = 0.035 if speed >= 360 else 0.06

        for particle in self.cursor_particles:
            particle.life -= dt
            particle.velocity *= 1.0 - min(0.9, dt * 5.0)
            particle.position += particle.velocity * dt
        self.cursor_particles = [p for p in self.cursor_particles if p.life > 0]

    def _make_cursor_spark(self, position: pygame.Vector2) -> CursorParticle:
        angle = self.cursor_rng.uniform(0.0, math.tau)
        speed = self.cursor_rng.uniform(35.0, 230.0)
        velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        life = self.cursor_rng.uniform(0.16, 0.52)
        size = self.cursor_rng.uniform(1.4, 3.6)
        color = self.cursor_rng.choice(CURSOR_PALETTE)
        return CursorParticle(position.copy(), velocity, life, life, size, color)

    def _cursor_color(self, age_fraction: float) -> tuple[int, int, int]:
        phase = (self.cursor_phase * 0.9 + age_fraction * 0.35) % 1.0
        segment = phase * (len(CURSOR_PALETTE) - 1)
        index = int(segment)
        fraction = segment - index
        first = CURSOR_PALETTE[index]
        second = CURSOR_PALETTE[min(index + 1, len(CURSOR_PALETTE) - 1)]
        return tuple(
            round(first[channel] * (1 - fraction) + second[channel] * fraction)
            for channel in range(3)
        )

    def draw_cursor_effects(self) -> None:
        position = self.current_mouse_position()
        glow = pygame.Surface((WIDTH, HEIGHT))
        glow.fill((0, 0, 0))
        if len(self.cursor_trail) >= 2:
            for index in range(len(self.cursor_trail) - 1):
                timestamp, point = self.cursor_trail[index]
                age = min(1.0, max(0.0, self.cursor_time - timestamp) / CURSOR_TRAIL_MAX_AGE)
                strength = (1.0 - age) ** 2
                radius = 1.0 + (1.0 - age) * 4.5
                color = self._cursor_color(age)
                shade = tuple(round(channel * strength) for channel in color)
                pygame.draw.circle(glow, shade, (round(point.x), round(point.y)), max(1, round(radius)))
        for particle in self.cursor_particles:
            remaining = max(0.0, particle.life / particle.max_life)
            radius = max(1, round(particle.size * (0.35 + 0.65 * remaining)))
            shade = tuple(round(channel * remaining) for channel in particle.color)
            pygame.draw.circle(
                glow, shade, (round(particle.position.x), round(particle.position.y)), radius
            )
        self.screen.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
        self._draw_crosshair(position)

    def _draw_crosshair(self, position: pygame.Vector2) -> None:
        center = (round(position.x), round(position.y))
        pygame.draw.circle(self.screen, WHITE, center, 8, 2)
        pygame.draw.circle(self.screen, CYAN, center, 2)
        for axis in (
            pygame.Vector2(1, 0),
            pygame.Vector2(-1, 0),
            pygame.Vector2(0, 1),
            pygame.Vector2(0, -1),
        ):
            start = position + axis * 11
            end = position + axis * 18
            pygame.draw.line(
                self.screen, CYAN, (round(start.x), round(start.y)), (round(end.x), round(end.y)), 2
            )
        spin = self.cursor_phase * 2.4
        arc_rect = pygame.Rect(0, 0, 34, 34)
        arc_rect.center = center
        pygame.draw.arc(self.screen, WHITE, arc_rect, spin, spin + math.pi * 0.72, 2)
        pygame.draw.arc(self.screen, WHITE, arc_rect, spin + math.pi, spin + math.pi * 1.72, 2)

    def card_purchase_price(self, card: Card) -> int:
        return max(0, round(self.apply_stat(card.price, "card_price", TARGET_PLAYER)))

    def card_sale_price(self, owned: OwnedCard) -> int:
        card = CARD_BY_KEY[owned.key]
        if owned.wholesale_purchase:
            if owned.wholesale_sale_price is not None:
                return owned.wholesale_sale_price
            return {"普通": 0, "罕见": 1, "稀有": 2}[card.rarity]
        return max(0, round(self.apply_stat(card.price // 2, "card_sale_price", TARGET_PLAYER)))

    def wholesale_sale_price(self, rarity: str) -> int:
        stat = {
            "普通": "wholesale_common_sale",
            "罕见": "wholesale_uncommon_sale",
            "稀有": "wholesale_rare_sale",
        }[rarity]
        return max(0, round(self.apply_stat(0.0, stat, TARGET_PLAYER)))

    def current_base_damage(self) -> float:
        return self.apply_stat(self.default_damage, "base_damage", TARGET_PLAYER) + self.enhancement_count("damage")

    def current_damage_bonus(
        self,
        moving: bool = False,
        extra_bonus: float = 0.0,
        include_composure: bool = True,
    ) -> float:
        context = {
            "moving": moving,
            "exclude_composure": not include_composure,
        }
        multiplier = self.apply_stat(1.0, "damage_dealt", TARGET_PLAYER, context)
        return multiplier - 1.0 + self.temp_damage_bonus + extra_bonus

    def current_damage(self, moving: bool = False, extra_bonus: float = 0.0) -> float:
        bonus = self.current_damage_bonus(moving, extra_bonus)
        return shot_damage(self.population, self.current_base_damage(), bonus)

    def current_gate_damage(self, moving: bool = False, extra_bonus: float = 0.0) -> float:
        bonus = self.current_damage_bonus(moving, extra_bonus, include_composure=False)
        return gate_shot_damage(self.population, self.current_base_damage(), bonus)

    def current_dps(self) -> float:
        return (
            self.current_damage()
            * self.current_fire_rate()
            * self.current_volley_multiplier()
            * self.expected_critical_multiplier()
        )

    def combat_snapshot(self) -> dict[str, float | int]:
        return {
            "population": self.population,
            "base_damage": self.current_base_damage(),
            "shot_damage": self.current_damage(),
            "fire_rate": self.current_fire_rate(),
            "volley_multiplier": self.current_volley_multiplier(),
            "dps": self.current_dps(),
        }

    def log_world_completion(self) -> None:
        start = self.world_start_snapshot
        final = self.combat_snapshot()
        start_dps = float(start["dps"])
        cards = ";".join(
            f"{owned.key}{'+' + owned.enhancement if owned.enhancement else ''}"
            for owned in self.all_owned_cards()
        )
        record = {
            "logged_at": create_run_id(),
            "run_id": self.run_id,
            "world": self.world,
            "elapsed_seconds": round(self.elapsed, 3),
            "start_population": start["population"],
            "final_population": final["population"],
            "start_base_damage": round(float(start["base_damage"]), 4),
            "final_base_damage": round(float(final["base_damage"]), 4),
            "start_shot_damage": round(float(start["shot_damage"]), 4),
            "final_shot_damage": round(float(final["shot_damage"]), 4),
            "start_fire_rate": round(float(start["fire_rate"]), 4),
            "final_fire_rate": round(float(final["fire_rate"]), 4),
            "start_volley_multiplier": start["volley_multiplier"],
            "final_volley_multiplier": final["volley_multiplier"],
            "start_dps": round(start_dps, 4),
            "final_dps": round(float(final["dps"]), 4),
            "dps_growth": round(float(final["dps"]) / start_dps, 4) if start_dps > 0 else 0,
            "gold_before_reward": self.gold,
            "enemy_kills": self.total_kills - self.world_start_kills,
            "cards": cards,
        }
        try:
            append_world_balance_log(record)
        except OSError as error:
            self.balance_log_error = str(error)

    def spawn_enemy(self, elite: bool = False) -> None:
        target = TARGET_ELITE if elite else TARGET_NORMAL
        if elite:
            speed, radius = 88 * (1 + 0.04 * (self.world - 1)), 27
        else:
            speed, radius = self.rng.uniform(60, 74) * (1 + 0.04 * (self.world - 1)), 16
        hp = self.current_dps() if elite else world_target_health(self.world, "normal")
        speed = max(0.0, self.apply_stat(speed, "move_speed", target))
        hp = max(1.0, self.apply_stat(hp, "health", target))
        self.enemies.append(
            Enemy(pygame.Vector2(self.rng.randint(35, WIDTH - 35), -30), hp, hp, speed, radius, elite)
        )

    def spawn_number_gate(self) -> None:
        initial = gate_initial_value(self.current_gate_damage(), self.rng.uniform(1.1, 1.8))
        self.gates.append(Gate(pygame.Vector2(self.gate_spawn_x(), -40), "number", initial))

    def spawn_special_gate(self) -> None:
        buffs = ("damage", "fire_rate", "population")
        weights = self.special_gate_weights()
        if weights:
            buff = self.rng.choices(buffs, weights=weights, k=1)[0]
        else:
            buff = self.rng.choice(buffs)
        hp = max(1.0, self.apply_stat(world_target_health(self.world, "special"), "health", TARGET_GATE))
        self.gates.append(
            Gate(pygame.Vector2(self.gate_spawn_x(), -130), "special", hp=hp, max_hp=hp, buff=buff)
        )
        self.special_spawned += 1

    def special_gate_weights(self) -> tuple[float, float, float] | None:
        if not any(True for _ in self.iter_effects(action="change_weight", target=TARGET_GATE)):
            return None
        weights = (
            max(0.0, self.apply_stat(0.0, "damage_gate_weight", TARGET_GATE, actions={"change_weight"})),
            max(0.0, self.apply_stat(0.0, "fire_rate_gate_weight", TARGET_GATE, actions={"change_weight"})),
            max(0.0, self.apply_stat(0.0, "population_gate_weight", TARGET_GATE, actions={"change_weight"})),
        )
        return weights if sum(weights) > 0 else None

    def gate_spawn_x(self) -> int:
        active_x = [gate.position.x for gate in self.gates if gate.position.y < HEIGHT]
        candidates = [self.rng.randint(100, WIDTH - 100) for _ in range(20)]
        if not active_x:
            return candidates[0]
        return round(max(candidates, key=lambda x: min(abs(x - other) for other in active_x)))

    def spawn_boss(self, kind: str) -> None:
        data = {
            "small": (54.0, 4, 34),
            "medium": (46.0, 6, 42),
            "big": (90.0 + self.world * 5.0, 8, 54),
        }
        speed, reward, radius = data[kind]
        speed = max(0.0, self.apply_stat(speed, "move_speed", TARGET_BOSS, {"boss_kind": kind}))
        hp = max(1.0, self.apply_stat(world_target_health(self.world, kind), "health", TARGET_BOSS, {"boss_kind": kind}))
        windup = max(0.0, self.apply_stat(2.0, "boss_windup", TARGET_BOSS))
        self.bosses.append(
            Boss(
                pygame.Vector2(self.rng.randint(radius + 10, WIDTH - radius - 10), -radius),
                kind,
                hp,
                hp,
                speed,
                reward,
                radius,
                175.0,
                windup,
                windup_move_factor=boss_windup_move_factor(self.world),
            )
        )
        names = {"small": "小Boss", "medium": "中Boss", "big": "大Boss"}
        self.message = f"{names[kind]}出现！"
        self.message_timer = 2.5

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return

        if self.mouse_sensitivity_editing:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.mouse_sensitivity_editing = False
                    self.sensitivity_input_text = ""
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.commit_mouse_sensitivity()
                elif event.key == pygame.K_BACKSPACE:
                    self.sensitivity_input_text = self.sensitivity_input_text[:-1]
                else:
                    char = self._digit_key_char(event.key)
                    if char is not None:
                        if char == ".":
                            if not self.sensitivity_input_text:
                                self.sensitivity_input_text = "0."
                            elif "." not in self.sensitivity_input_text:
                                self.sensitivity_input_text += "."
                        else:
                            self.sensitivity_input_text += char
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.settings_mouse_sensitivity_value_rect().collidepoint(event.pos):
                    self.commit_mouse_sensitivity()
                else:
                    return

        if self.dev_panel_open:
            self.handle_dev_event(event)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == Mode.MAIN_MENU:
                for index, destination in enumerate((Mode.PLAYING, Mode.TUTORIAL, Mode.SETTINGS)):
                    if self.main_menu_button_rect(index).collidepoint(event.pos):
                        if destination == Mode.PLAYING:
                            self.reset_run()
                        else:
                            self.mode = destination
                        return
                return
            if self.mode == Mode.TUTORIAL:
                if self.menu_back_rect().collidepoint(event.pos):
                    self.mode = Mode.MAIN_MENU
                return
            if self.mode == Mode.SETTINGS:
                if self.menu_back_rect().collidepoint(event.pos):
                    self.mode = Mode.MAIN_MENU
                    return
                if self.settings_mouse_sensitivity_button_rect(-1).collidepoint(event.pos):
                    self.adjust_mouse_sensitivity(-1)
                    return
                if self.settings_mouse_sensitivity_button_rect(1).collidepoint(event.pos):
                    self.adjust_mouse_sensitivity(1)
                    return
                if self.settings_mouse_sensitivity_value_rect().collidepoint(event.pos):
                    self.begin_mouse_sensitivity_edit()
                    return
                for index, (kind, _) in enumerate(self.settings_volume_rows()):
                    for direction in (-1, 1):
                        if self.settings_volume_button_rect(index, direction).collidepoint(event.pos):
                            self.adjust_volume(kind, direction)
                            self.preview_volume(kind)
                            return
                return
        if event.type == pygame.MOUSEBUTTONDOWN and self.mode == Mode.PAUSED:
            if event.button == 1:
                if self.pause_main_menu_rect().collidepoint(event.pos):
                    self.abandon_run_to_main_menu()
                elif self.pause_restart_rect().collidepoint(event.pos):
                    self.reset_run()
                else:
                    for kind in ("sfx", "bgm"):
                        for direction in (-1, 1):
                            if self.pause_volume_button_rect(kind, direction).collidepoint(event.pos):
                                self.adjust_volume(kind, direction)
                                return
            return
        if self.mode == Mode.SHOP and event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.handle_shop_mouse_down(event.pos)
            elif event.button == 3:
                self.handle_shop_detail(event.pos)
            return
        if self.mode == Mode.SHOP and event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.handle_shop_mouse_up(event.pos)
            return
        if event.type != pygame.KEYDOWN:
            return
        if self.mode == Mode.SETTINGS:
            char = self._digit_key_char(event.key)
            if char is not None:
                self.begin_mouse_sensitivity_edit()
                self.sensitivity_input_text = "0." if char == "." else char
                return
        if event.key == pygame.K_F1:
            self.toggle_dev_panel()
            return
        if event.key == pygame.K_ESCAPE:
            if self.mode in (Mode.TUTORIAL, Mode.SETTINGS):
                self.mode = Mode.MAIN_MENU
            elif self.mode == Mode.PLAYING:
                self.mode = Mode.PAUSED
                self.sync_mouse_mode()
            elif self.mode == Mode.PAUSED:
                self.mode = Mode.PLAYING
                self.sync_mouse_mode()
        elif self.mode == Mode.MAIN_MENU and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.reset_run()
        elif self.mode == Mode.PAUSED and event.key == pygame.K_r:
            self.reset_run()
        elif self.mode in (Mode.GAME_OVER, Mode.VICTORY) and event.key == pygame.K_r:
            self.reset_run()
        elif self.mode == Mode.SHOP and event.key == pygame.K_RETURN:
            self.world += 1
            self.start_world()

    def update(self, dt: float) -> None:
        if self.dev_panel_open:
            return
        self.update_audio(dt)
        if self.mode != Mode.PLAYING:
            return
        self.elapsed += dt
        self.population_peak = max(self.population_peak, self.population)
        self.message_timer = max(0.0, self.message_timer - dt)
        self.rage_timer = max(0.0, self.rage_timer - dt)
        if self.temp_buff_timer > 0:
            self.temp_buff_timer -= dt
            if self.temp_buff_timer <= 0:
                self.temp_damage_bonus = 0.0
                self.temp_fire_rate_bonus = 0.0
        self.update_effect_runtime(dt)
        self.update_composure(dt)
        self.update_player(dt)
        self.update_cursor_effects(dt, self.current_mouse_position())
        self.update_timeline(dt)
        self.update_bullets(dt)
        self.update_enemies(dt)
        if self.mode != Mode.PLAYING:
            return
        self.update_enemy_bullets(dt)
        if self.mode != Mode.PLAYING:
            return
        self.update_gates(dt)
        if self.population <= 0:
            self.end_game("人口降为0，防线崩溃")
            return
        self.update_bosses(dt)
        if self.mode != Mode.PLAYING:
            return
        if self.population <= 0:
            self.end_game("人口降为0，防线崩溃")
        elif self.elapsed >= WORLD_DURATION:
            self.end_game("120秒截止，大Boss发动强制秒杀")

    def update_player(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        movement = pygame.Vector2(
            int(keys[pygame.K_d]) - int(keys[pygame.K_a]),
            int(keys[pygame.K_s]) - int(keys[pygame.K_w]),
        )
        moving = movement.length_squared() > 0
        if moving:
            self.clear_movement_effect_stacks()
        self.player += normalized(movement) * self.current_move_speed() * dt
        self.player.x = max(self.player_radius, min(WIDTH - self.player_radius, self.player.x))
        self.player.y = max(PLAY_TOP + self.player_radius, min(HEIGHT - self.player_radius, self.player.y))
        self.update_still_time(dt, moving)
        if pygame.mouse.get_relative_mode():
            rel = pygame.mouse.get_rel()
            self.aim_position += pygame.Vector2(rel[0], rel[1]) * self.mouse_sensitivity
            self.aim_position.x = max(0, min(WIDTH, self.aim_position.x))
            self.aim_position.y = max(0, min(HEIGHT, self.aim_position.y))

        self.fire_timer -= dt
        firing = pygame.mouse.get_pressed()[0]
        ramp_limits = [
            abs(float(effect.parameters.get("cap", 0.0)))
            / max(0.001, abs(float(effect.parameters.get("value_per_second", 0.0))))
            for _, _, effect in self.iter_effects(trigger="while_firing", stat="fire_rate")
            if float(effect.parameters.get("value_per_second", 0.0)) != 0
        ]
        streak_limit = max(ramp_limits, default=0.0)
        self.shot_streak = (
            min(streak_limit, self.shot_streak + dt)
            if firing
            else max(0.0, self.shot_streak - dt * 2)
        )
        fire_rate = self.current_fire_rate()
        if firing and self.fire_timer <= 0 and fire_rate > 0:
            direction = self.aim_direction()
            if direction.length_squared():
                self.dispatch_effect_event("on_shot", TARGET_PLAYER)
                fire_rate = max(0.000001, self.current_fire_rate())
                extra_damage_bonus = 0.0
                damage = self.current_damage(moving, extra_damage_bonus)
                gate_damage = self.current_gate_damage(moving, extra_damage_bonus)
                special_gate_damage = shot_damage(
                    self.population,
                    self.current_base_damage(),
                    self.current_damage_bonus(moving, extra_damage_bonus, include_composure=False),
                )
                critical_multiplier = self.roll_critical_multiplier()
                damage *= critical_multiplier
                gate_damage *= critical_multiplier
                special_gate_damage *= critical_multiplier
                gate_target_bonus = self.composure_gate_bonus
                speed = max(0.0, self.apply_stat(880.0, "bullet_speed", TARGET_PLAYER))
                pierces = self.current_pierces()
                bounces = self.current_bounces()
                projectiles, spread, damage_scale = self.volley_profile()
                center = (projectiles - 1) / 2
                angles = tuple((index - center) * spread for index in range(projectiles))
                for angle in angles:
                    self.bullets.append(
                        Bullet(
                            self.player.copy(),
                            direction.rotate(angle) * speed,
                            damage * damage_scale,
                            gate_damage * damage_scale,
                            pierces,
                            bounces,
                            gate_target_bonus,
                            special_gate_damage * damage_scale,
                        )
                    )
                self.trigger_composure_release()
                self.play_shot_sound(fire_rate)
                self.fire_timer = 1.0 / fire_rate

    def update_composure(self, dt: float) -> None:
        effects = list(self.iter_effects(action="modify_stat", trigger="while_not_firing"))
        if not effects:
            self.composure_idle_time = 0.0
            self.composure_release_timer = 0.0
            self.composure_damage_bonus = 0.0
            self.composure_gate_bonus = 0.0
            return
        if self.composure_release_timer > 0:
            self.composure_release_timer -= dt
            if self.composure_release_timer <= 1e-9:
                self.composure_release_timer = 0.0
                self.composure_idle_time = 0.0
                self.composure_damage_bonus = 0.0
                self.composure_gate_bonus = 0.0
            return
        self.composure_idle_time += dt
        self.composure_damage_bonus = self.apply_stat(
            1.0,
            "damage_dealt",
            TARGET_PLAYER,
            include_triggers={"while_not_firing"},
        ) - 1.0
        self.composure_gate_bonus = self.apply_stat(
            1.0,
            "gate_damage",
            TARGET_GATE,
            include_triggers={"while_not_firing"},
        ) - 1.0

    def trigger_composure_release(self) -> None:
        effects = list(self.iter_effects(action="modify_stat", trigger="while_not_firing"))
        if not effects:
            return
        active = self.composure_damage_bonus != 0 or self.composure_gate_bonus != 0
        if active and self.composure_release_timer <= 0:
            self.composure_release_timer = max(float(effect.parameters.get("linger", 0.0)) for _, _, effect in effects)
        elif not active:
            self.composure_idle_time = 0.0

    def update_timeline(self, dt: float) -> None:
        self.enemy_timer -= dt
        self.elite_timer -= dt
        self.gate_timer -= dt
        interval = max(0.28, 1.30 - (self.world - 1) * 0.145)
        if self.enemy_timer <= 0 and len(self.enemies) < 160:
            self.spawn_enemy()
            self.enemy_timer = interval
        if self.elite_timer <= 0:
            self.spawn_enemy(True)
            base_elite_interval = max(8.0, 18.0 - (self.world - 1) * 1.45)
            self.elite_timer = max(3.0, self.apply_stat(base_elite_interval, "elite_spawn_interval", TARGET_PLAYER))
        if self.gate_timer <= 0 and not any(g.kind == "number" for g in self.gates):
            self.spawn_number_gate()
            self.gate_timer = self.rng.uniform(8.0, 11.0)
        if self.special_spawned < 3 and self.elapsed >= self.special_times[self.special_spawned]:
            self.spawn_special_gate()
        if not self.small_spawned and self.elapsed >= self.small_boss_time:
            self.small_spawned = True
            self.spawn_boss("small")
        if not self.medium_spawned and self.elapsed >= 60:
            self.medium_spawned = True
            self.spawn_boss("medium")
        if not self.big_spawned and self.elapsed >= 90:
            self.big_spawned = True
            self.spawn_boss("big")

    def apply_hit(self, bullet: Bullet, target: object) -> bool:
        target_id = id(target)
        if target_id in bullet.hit_ids:
            return False
        bullet.hit_ids.add(target_id)
        if bullet.pierces > 0:
            bullet.pierces -= 1
            return False
        return True

    @staticmethod
    def bounce_off_screen_edge(bullet: Bullet) -> bool:
        hit_x = bullet.position.x <= bullet.radius or bullet.position.x >= WIDTH - bullet.radius
        hit_y = bullet.position.y <= bullet.radius or bullet.position.y >= HEIGHT - bullet.radius
        if not hit_x and not hit_y:
            return False
        if bullet.bounces <= 0:
            return True
        if hit_x:
            bullet.position.x = max(bullet.radius, min(WIDTH - bullet.radius, bullet.position.x))
            bullet.velocity.x *= -1
        if hit_y:
            bullet.position.y = max(bullet.radius, min(HEIGHT - bullet.radius, bullet.position.y))
            bullet.velocity.y *= -1
        bullet.bounces -= 1
        return False

    @staticmethod
    def bounce_off_gate(bullet: Bullet, gate: Gate) -> None:
        rect = gate.rect
        previous = bullet.previous_position
        if previous.x <= rect.left or previous.x >= rect.right:
            bullet.velocity.x *= -1
        else:
            bullet.velocity.y *= -1
        bullet.position = previous.copy()
        bullet.bounces -= 1

    def update_bullets(self, dt: float) -> None:
        for bullet in self.bullets:
            bullet.update(dt)
        for bullet in self.bullets[:]:
            if self.bounce_off_screen_edge(bullet):
                self.bullets.remove(bullet)
                continue
            remove = False
            for boss in self.bosses:
                if id(boss) not in bullet.hit_ids and bullet.position.distance_to(boss.position) <= boss.radius + bullet.radius:
                    damage = bullet.damage * self.apply_stat(
                        1.0,
                        "damage_taken",
                        TARGET_BOSS,
                        {"boss_kind": boss.kind},
                    )
                    boss.hp -= damage
                    self.play_effect_sound(self.enemy_hit_sound, "enemy_hit")
                    self.apply_on_hit_effects(TARGET_BOSS, boss.position, damage, boss)
                    self.dispatch_effect_event("on_hit", TARGET_BOSS)
                    remove = self.apply_hit(bullet, boss)
                    break
            if not remove:
                for enemy in self.enemies:
                    if id(enemy) in bullet.hit_ids:
                        continue
                    if bullet.position.distance_to(enemy.position) <= enemy.radius + bullet.radius:
                        target = TARGET_ELITE if enemy.elite else TARGET_NORMAL
                        damage = bullet.damage * self.apply_stat(1.0, "damage_taken", target)
                        enemy.hp -= damage
                        self.play_effect_sound(self.enemy_hit_sound, "enemy_hit")
                        for owned, index, effect in self.iter_effects(
                            action="execute",
                            target=target,
                            trigger="on_hit",
                        ):
                            threshold = float(effect.parameters["threshold"])
                            if execution_ready(enemy.hp, enemy.max_hp, threshold) and self.effect_event_ready(
                                owned, index, effect, target
                            ):
                                enemy.hp = 0
                                break
                        self.apply_on_hit_effects(target, enemy.position, damage, enemy)
                        self.dispatch_effect_event("on_hit", target)
                        remove = self.apply_hit(bullet, enemy)
                        break
            if not remove:
                for gate in self.gates:
                    if id(gate) in bullet.hit_ids or not gate.rect.collidepoint(bullet.position):
                        continue
                    passive_gate_multiplier = self.apply_stat(
                        1.0,
                        "gate_damage",
                        TARGET_GATE,
                        exclude_triggers={"while_not_firing"},
                    )
                    gate_damage = bullet.gate_damage * (passive_gate_multiplier + bullet.gate_target_bonus)
                    self.play_effect_sound(self.gate_hit_sound, "gate_hit")
                    if gate.kind == "number":
                        gate.value += gate_steps(gate_damage)
                    else:
                        special_gate_damage = (
                            bullet.special_gate_damage
                            if bullet.special_gate_damage is not None
                            else bullet.damage
                        )
                        gate.take_special_damage(special_gate_damage * (passive_gate_multiplier + bullet.gate_target_bonus))
                    bullet.hit_ids.add(id(gate))
                    if bullet.bounces > 0:
                        self.bounce_off_gate(bullet, gate)
                    else:
                        remove = True
                    break
            if remove and bullet in self.bullets:
                self.bullets.remove(bullet)

    def apply_on_hit_effects(
        self,
        hit_target: int,
        center: pygame.Vector2,
        damage: float,
        source: object,
    ) -> None:
        for owned, index, effect in self.iter_effects(action="splash_damage", trigger="on_hit"):
            trigger_target = effect.parameters.get("trigger_target")
            if trigger_target is not None and int(trigger_target) != hit_target:
                continue
            if trigger_target is None and not effect.targets.includes(hit_target):
                continue
            if not self.effect_event_ready(owned, index, effect, hit_target):
                continue
            splash_damage = damage * float(effect.parameters.get("value", 0.0))
            radius = float(effect.parameters.get("radius", 0.0))
            global_effect = bool(effect.parameters.get("global_effect", False))
            for enemy in self.enemies:
                target = TARGET_ELITE if enemy.elite else TARGET_NORMAL
                if enemy is source or not effect.targets.includes(target):
                    continue
                if global_effect or enemy.position.distance_to(center) <= radius:
                    enemy.hp -= splash_damage

    def splash(self, center: pygame.Vector2, damage: float, source: object, radius: float = 95.0) -> None:
        for enemy in self.enemies:
            if enemy is not source and enemy.position.distance_to(center) <= radius:
                enemy.hp -= damage

    def register_kill(self, elite: bool = False) -> None:
        self.total_kills += 1
        self.rapid_reload_kills += 1
        self.play_kill_sound()
        target = TARGET_ELITE if elite else TARGET_NORMAL
        self.dispatch_effect_event("on_enemy_kill", target)
        if elite:
            self.dispatch_effect_event("on_elite_kill", TARGET_ELITE)

    def lose_population(self, amount: int) -> int:
        before = self.population
        reduction = max(
            0.0,
            min(0.95, self.apply_stat(0.0, "population_loss_reduction", TARGET_PLAYER)),
        )
        if reduction:
            amount = max(1, math.ceil(amount * (1.0 - reduction)))
        self.population -= amount
        self.dispatch_effect_event("on_population_loss", TARGET_PLAYER)
        self.dispatch_effect_event("on_damage_taken", TARGET_PLAYER)
        if self.population < 2:
            self.population = 0
            self.end_game("人口低于2，防线崩溃")
        return before - self.population

    def lose_population_ratio(self, ratio: float) -> int:
        amount = max(1, math.ceil(max(0, self.population) * max(0.0, ratio)))
        return self.lose_population(amount)

    def contact_avoid_chance(self, target: int) -> float:
        stat = {
            TARGET_NORMAL: "contact_avoid_chance",
            TARGET_ELITE: "elite_contact_avoid_chance",
            TARGET_BOSS: "boss_contact_avoid_chance",
        }[target]
        return max(0.0, min(1.0, self.apply_stat(0.0, stat, target)))

    def update_enemies(self, dt: float) -> None:
        for enemy in self.enemies[:]:
            if enemy.hp <= 0:
                self.enemies.remove(enemy)
                self.register_kill(enemy.elite)
                if enemy.elite:
                    self.population += round(self.apply_stat(4.0, "elite_kill_population", TARGET_PLAYER))
                continue
            enemy.update(dt, self.player)
            if enemy.elite and enemy.position.y > 50:
                enemy.shoot_timer -= dt
                if enemy.shoot_timer <= 0:
                    direction = normalized(self.player - enemy.position)
                    speed = 190.0 + self.world * 5.0
                    self.enemy_bullets.append(
                        EnemyBullet(enemy.position.copy(), direction * speed, population_loss_ratio=0.03)
                    )
                    enemy.shoot_timer = self.rng.uniform(2.8, 4.0)
            if enemy.position.distance_to(self.player) <= enemy.radius + self.player_radius:
                loss_ratio = 0.12 if enemy.elite else 0.02
                target = TARGET_ELITE if enemy.elite else TARGET_NORMAL
                contact_chance = self.contact_avoid_chance(target)
                if contact_chance and self.rng.random() < contact_chance:
                    loss = 0
                else:
                    loss = self.lose_population_ratio(loss_ratio)
                self.enemies.remove(enemy)
                self.message = f"{'精英' if enemy.elite else '怪物'}突破：人口 -{loss}（{loss_ratio:.0%}）"
                self.message_timer = 1.5

    def update_enemy_bullets(self, dt: float) -> None:
        for bullet in self.enemy_bullets[:]:
            bullet.update(dt)
            if not bullet.on_screen():
                self.enemy_bullets.remove(bullet)
            elif bullet.position.distance_to(self.player) <= bullet.radius + self.player_radius:
                avoid_chance = max(
                    0.0,
                    min(1.0, self.apply_stat(0.0, "projectile_avoid_chance", TARGET_PLAYER)),
                )
                if avoid_chance and self.rng.random() < avoid_chance:
                    self.enemy_bullets.remove(bullet)
                    self.message = "闪避了弹丸"
                    self.message_timer = 0.8
                else:
                    loss = self.lose_population_ratio(bullet.population_loss_ratio)
                    self.enemy_bullets.remove(bullet)
                    self.message = f"被{bullet.source}击中：人口 -{loss}（{bullet.population_loss_ratio:.0%}）"
                    self.message_timer = 1.5

    def update_gates(self, dt: float) -> None:
        player_rect = pygame.Rect(0, 0, self.player_radius * 2, self.player_radius * 2)
        player_rect.center = (round(self.player.x), round(self.player.y))
        for gate in self.gates[:]:
            gate.position.y += gate.speed * dt
            if gate.unlocked and gate.rect.colliderect(player_rect):
                self.play_effect_sound(self.gate_collect_sound, "gate_collect")
                if gate.kind == "number":
                    value = gate.value
                    if value > 0:
                        value = math.ceil(self.apply_stat(value, "number_gate_reward", TARGET_GATE))
                    before = self.population
                    self.population = max(0, self.population + value)
                    self.message = f"数字门结算：人口 {self.population - before:+d}"
                else:
                    self.gold += 1
                    event_changes = self.dispatch_effect_event("on_gate_collect", TARGET_GATE)
                    self.apply_special_buff(gate.buff, gate.recruit_multiplier, 1 + event_changes["gold"])
                self.message_timer = 2.5
                self.gates.remove(gate)
            elif gate.rect.top > HEIGHT:
                self.gates.remove(gate)

    def apply_special_buff(self, buff: str, recruit_multiplier: float = 1.1, reward: int = 1) -> None:
        if buff == "damage":
            self.temp_damage_bonus = 0.35
            self.temp_buff_timer = 15.0
            text = "伤害 +35%，持续15秒"
        elif buff == "fire_rate":
            self.temp_fire_rate_bonus = 0.50
            self.temp_buff_timer = 12.0
            text = "射速 +50%，持续12秒"
        else:
            before = self.population
            self.population = math.ceil(self.population * recruit_multiplier)
            text = f"人口 ×{recruit_multiplier:.1f}（+{self.population - before}）"
        self.message = f"特殊门：{text}，金币 +{reward}"

    def update_bosses(self, dt: float) -> None:
        for boss in self.bosses[:]:
            if boss.hp <= 0:
                self.kill_boss(boss)
                if self.mode != Mode.PLAYING:
                    return
                continue
            was_winding_up = boss.windup_remaining is not None
            if boss.update(dt, self.player):
                self.execute_player(1.0)
                return
            self.update_boss_shooting(boss, dt)
            if was_winding_up and boss.windup_remaining is None:
                self.message = "闪避成功：大Boss范围攻击落空"
                self.message_timer = 2.0
            if boss.kind != "big" and boss.position.y - boss.radius > HEIGHT:
                self.bosses.remove(boss)
                self.message = f"{self.boss_name(boss.kind)}逃走了"
                self.message_timer = 1.8

    def execute_player(self, threshold: float) -> bool:
        self.population_peak = max(self.population_peak, self.population)
        if not execution_ready(self.population, self.population_peak, threshold):
            return False
        self.population = 0
        self.end_game(f"大Boss蓄力命中，触发{threshold:.0%}人口斩杀")
        return True

    def boss_shot_interval(self, kind: str) -> float:
        base_interval = {"small": 3.2, "medium": 2.6, "big": 2.0}[kind]
        return base_interval / (1.0 + 0.12 * (self.world - 1))

    def update_boss_shooting(self, boss: Boss, dt: float) -> None:
        if boss.position.y <= 50:
            return
        boss.shoot_timer -= dt
        if boss.shoot_timer > 0:
            return
        bullet_count, angle_step, speed, loss_ratio = {
            "small": (3, 14, 175.0, 0.02),
            "medium": (5, 12, 190.0, 0.03),
            "big": (7, 10, 205.0, 0.05),
        }[boss.kind]
        direction = normalized(self.player - boss.position)
        center = (bullet_count - 1) / 2
        for index in range(bullet_count):
            angle = (index - center) * angle_step
            self.enemy_bullets.append(
                EnemyBullet(
                    boss.position.copy(),
                    direction.rotate(angle) * speed,
                    population_loss_ratio=loss_ratio,
                    source=f"{self.boss_name(boss.kind)}弹幕",
                )
            )
        interval = self.boss_shot_interval(boss.kind)
        boss.shoot_timer = interval * self.rng.uniform(0.90, 1.10)

    def kill_boss(self, boss: Boss) -> None:
        if boss.kind == "big":
            self.log_world_completion()
        self.play_kill_sound()
        gold_before = self.gold
        base_reward = boss_gold_reward(boss.reward, self.gold)
        self.gold += round(self.apply_stat(base_reward, "boss_gold_reward", TARGET_PLAYER))
        self.dispatch_effect_event("on_boss_kill", TARGET_BOSS)
        reward = self.gold - gold_before
        self.bosses.remove(boss)
        self.message = f"击杀{self.boss_name(boss.kind)}：金币 +{reward}"
        self.message_timer = 3.0
        if boss.kind == "big":
            interest = self.dispatch_effect_event("on_world_complete")["gold"]
            if interest:
                self.message += f"，利息 +{interest}"
            if self.world >= 8:
                self.mode = Mode.VICTORY
                self.sync_mouse_mode()
            else:
                self.enter_shop()

    @staticmethod
    def boss_name(kind: str) -> str:
        return {"small": "小Boss", "medium": "中Boss", "big": "大Boss"}[kind]

    def enter_shop(self) -> None:
        self.mode = Mode.SHOP
        self.shop_round += 1
        self.refresh_cost = 0
        self.detail_card = None
        self.card_page = "normal"
        self.dragging_card = None
        self.dragging_from = ""
        self.message_timer = 0.0
        self.sync_mouse_mode()
        self.roll_shop()

    def roll_shop(self) -> None:
        self.shop_offers = []
        self.fill_shop()

    def fill_shop(self) -> None:
        excluded = {owned.key for owned in self.equipped_cards} | {
            offer.card.key for offer in self.shop_offers if offer.card is not None
        }
        available = [card for card in CARDS if card.key not in excluded]
        rarity_weights = {
            "普通": max(55, 85 - (self.world - 1) * 5),
            "罕见": 14 + (self.world - 1) * 3,
            "稀有": 1 + (self.world - 1) * 2,
        }
        while len(self.shop_offers) < 3:
            if self.rng.random() < OVERLOAD_CHANCE:
                categories = sorted({card.category for card in CARDS})
                self.shop_offers.append(ShopOffer(overload_category=self.rng.choice(categories)))
                continue
            pool = [card for card in available if card.key not in {offer.card.key for offer in self.shop_offers if offer.card}]
            if not pool:
                break
            pool_weights = []
            for card in pool:
                rarity_count = sum(1 for candidate in pool if candidate.rarity == card.rarity)
                pool_weights.append(rarity_weights[card.rarity] / max(1, rarity_count))
            card = self.rng.choices(pool, weights=pool_weights, k=1)[0]
            enhancement = self.rng.choice(("population", "fire_rate", "damage")) if self.rng.random() < 0.15 else ""
            self.shop_offers.append(ShopOffer(card, enhancement))

    def draw_overload_card(self, category: str) -> Card:
        category_cards = [card for card in CARDS if card.category == category]
        rarities = sorted({card.rarity for card in category_cards})
        rarity = self.rng.choice(rarities)
        return self.rng.choice([card for card in category_cards if card.rarity == rarity])

    def exchange_for_overload(self, owned: OwnedCard, offer: ShopOffer) -> bool:
        if owned not in self.equipped_cards or not offer.is_overload:
            return False
        if len(self.overload_cards) >= 2:
            self.shop_message("过载卡槽已满，无法交换")
            return False
        value = self.card_sale_price(owned)
        self.dispatch_effect_event("on_card_sale", TARGET_PLAYER)
        self.remove_owned_card(owned, self.equipped_cards)
        total = min(OVERLOAD_EXCHANGE_COST, offer.exchange_value + value)
        if total < OVERLOAD_EXCHANGE_COST:
            index = next(index for index, candidate in enumerate(self.shop_offers) if candidate is offer)
            self.shop_offers[index] = ShopOffer(
                overload_category=offer.overload_category,
                exchange_value=total,
            )
            self.shop_message(f"过载交换进度 {total}/{OVERLOAD_EXCHANGE_COST}")
            return True
        card = self.draw_overload_card(offer.overload_category)
        self.overload_cards.append(
            OwnedCard(card.key, "overload", self.world, acquired_shop_round=self.shop_round)
        )
        self.dispatch_effect_event("on_card_purchase", TARGET_PLAYER)
        index = next(index for index, candidate in enumerate(self.shop_offers) if candidate is offer)
        self.shop_offers.pop(index)
        self.fill_shop()
        self.shop_message(f"交换成功：获得过载牌 {card.name}")
        return True

    def remove_owned_card(self, owned: OwnedCard, collection: list[OwnedCard]) -> None:
        collection.remove(owned)
        for runtime_key in [key for key in self.effect_runtime if key[0] == owned.instance_id]:
            del self.effect_runtime[runtime_key]

    def sell_owned_card(self, owned: OwnedCard, source: str) -> bool:
        collection = self.overload_cards if source == "overload" else self.equipped_cards
        if owned not in collection:
            return False
        if source == "overload" and owned.acquired_shop_round >= self.shop_round:
            self.shop_message("新获得的过载牌要到下次商店才能出售")
            return False
        card = CARD_BY_KEY[owned.key]
        sale_price = OVERLOAD_SALE_PRICE if source == "overload" else self.card_sale_price(owned)
        self.gold += sale_price
        self.dispatch_effect_event("on_card_sale", TARGET_PLAYER)
        self.remove_owned_card(owned, collection)
        self.shop_message(f"卖出{card.name}，金币 +{sale_price}")
        return True

    def card_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(55 + index * 280, 155, 250, 245)

    def attribute_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(910, 150 + index * 105, 315, 82)

    def slot_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(55 + index * 165, 485, 150, 125)

    @staticmethod
    def shop_page_button_rect() -> pygame.Rect:
        return pygame.Rect(55, 635, 190, 48)

    @staticmethod
    def shop_sell_rect() -> pygame.Rect:
        return pygame.Rect(275, 635, 570, 48)

    def visible_card_collection(self) -> list[OwnedCard]:
        return self.overload_cards if self.card_page == "overload" else self.equipped_cards

    def handle_shop_mouse_down(self, position: tuple[int, int]) -> None:
        self.detail_card = None
        if self.shop_page_button_rect().collidepoint(position):
            self.card_page = "overload" if self.card_page == "normal" else "normal"
            return
        for index, owned in enumerate(self.visible_card_collection()):
            if self.slot_rect(index).collidepoint(position):
                self.dragging_card = owned
                self.dragging_from = self.card_page
                return
        self.handle_shop_click(position)

    def handle_shop_mouse_up(self, position: tuple[int, int]) -> None:
        owned = self.dragging_card
        source = self.dragging_from
        self.dragging_card = None
        self.dragging_from = ""
        if owned is None:
            return
        if self.shop_sell_rect().collidepoint(position):
            self.sell_owned_card(owned, source)
            return
        if source != "normal":
            return
        for index, offer in enumerate(self.shop_offers):
            if offer.is_overload and self.card_rect(index).collidepoint(position):
                self.exchange_for_overload(owned, offer)
                return

    def handle_shop_click(self, position: tuple[int, int]) -> None:
        self.detail_card = None
        for index, offer in enumerate(self.shop_offers):
            if self.card_rect(index).collidepoint(position):
                if offer.is_overload or offer.card is None:
                    return
                card = offer.card
                price = self.card_purchase_price(card)
                if len(self.equipped_cards) >= 5:
                    self.shop_message("卡槽已满，请先出售一张卡")
                elif self.gold < price:
                    self.shop_message("金币不足")
                else:
                    self.gold -= price
                    wholesale_purchase = self.has_stat_effect("wholesale_common_sale")
                    self.equipped_cards.append(
                        OwnedCard(
                            card.key,
                            offer.enhancement,
                            self.world,
                            wholesale_purchase,
                            self.wholesale_sale_price(card.rarity) if wholesale_purchase else None,
                        )
                    )
                    self.dispatch_effect_event("on_card_purchase", TARGET_PLAYER)
                    self.shop_offers.remove(offer)
                    self.fill_shop()
                return
        for index, key in enumerate(("population", "damage", "fire_rate")):
            if self.attribute_rect(index).collidepoint(position):
                price = attribute_price(self.attribute_purchases[key])
                if self.gold < price:
                    self.shop_message("金币不足")
                else:
                    self.gold -= price
                    self.attribute_purchases[key] += 1
                    if key == "population":
                        self.default_population += 2
                    elif key == "damage":
                        self.default_damage += 1.0
                    else:
                        self.default_fire_rate += 0.8
                return
        refresh_rect = pygame.Rect(910, 495, 150, 52)
        if refresh_rect.collidepoint(position):
            charged = max(0, round(self.apply_stat(self.refresh_cost, "refresh_cost", TARGET_PLAYER)))
            if self.gold < charged:
                self.shop_message("刷新金币不足")
            else:
                self.gold -= charged
                self.refresh_cost = 2 if self.refresh_cost == 0 else self.refresh_cost + 1
                self.roll_shop()
            return
        if pygame.Rect(1080, 495, 145, 52).collidepoint(position):
            self.world += 1
            self.start_world()

    def handle_shop_detail(self, position: tuple[int, int]) -> None:
        for index, owned in enumerate(self.visible_card_collection()):
            if self.slot_rect(index).collidepoint(position):
                self.detail_card = None if self.detail_card == owned else owned
                return
        self.detail_card = None

    def shop_message(self, text: str) -> None:
        self.message = text
        self.message_timer = 3.0

    def end_game(self, reason: str) -> None:
        self.mode = Mode.GAME_OVER
        self.death_reason = reason
        self.sync_mouse_mode()

    def abandon_run_to_main_menu(self) -> None:
        self.mode = Mode.MAIN_MENU
        self.sync_mouse_mode()

    def draw(self) -> None:
        self.screen.fill(BG)
        if self.mode == Mode.MAIN_MENU:
            self.draw_main_menu()
        elif self.mode == Mode.TUTORIAL:
            self.draw_tutorial()
        elif self.mode == Mode.SETTINGS:
            self.draw_settings()
        elif self.mode == Mode.SHOP:
            self.draw_shop()
        else:
            self.draw_arena()
            self.draw_gates()
            self.draw_enemies()
            self.draw_bosses()
            self.draw_bullets()
            self.draw_enemy_bullets()
            self.draw_player()
            if self.mode == Mode.PLAYING:
                self.draw_cursor_effects()
            self.draw_hud()
            if self.mode == Mode.PAUSED:
                self.draw_pause_menu()
            elif self.mode == Mode.GAME_OVER:
                self.draw_overlay("防线失守", f"{self.death_reason} | 按 R 重开")
            elif self.mode == Mode.VICTORY:
                self.draw_overlay("八世界通关", f"最终金币 {self.gold} | 按 R 再来一局")
        if self.dev_panel_open:
            self.draw_dev_panel()
        pygame.display.flip()

    @staticmethod
    def main_menu_button_rect(index: int) -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 - 170, 340 + index * 82, 340, 60)

    @staticmethod
    def menu_back_rect() -> pygame.Rect:
        return pygame.Rect(55, 625, 150, 52)

    @staticmethod
    def settings_volume_rows() -> tuple[tuple[str, str], ...]:
        return (
            ("bgm", "背景音乐"),
            ("sfx", "音效总音量"),
            ("shot", "枪声"),
            ("enemy_hit", "敌人命中"),
            ("kill", "敌人击杀"),
            ("gate_hit", "门命中"),
            ("gate_collect", "吃门提示"),
        )

    @staticmethod
    def settings_volume_button_rect(index: int, direction: int) -> pygame.Rect:
        return pygame.Rect(810 if direction < 0 else 1055, Game.settings_audio_y(index) + 7, 48, 42)

    @staticmethod
    def settings_audio_y(index: int) -> int:
        return 250 + index * 42

    @staticmethod
    def settings_mouse_sensitivity_button_rect(direction: int) -> pygame.Rect:
        return pygame.Rect(810 if direction < 0 else 1055, 152, 48, 42)

    @staticmethod
    def settings_mouse_sensitivity_value_rect() -> pygame.Rect:
        return pygame.Rect(885, 152, 150, 42)

    def preview_volume(self, kind: str) -> None:
        if kind == "bgm":
            return
        if kind in ("sfx", "shot"):
            self.play_shot_sound(self.default_fire_rate)
        elif kind == "kill":
            self.play_kill_sound()
        elif kind == "enemy_hit":
            self.play_effect_sound(self.enemy_hit_sound, kind)
        elif kind == "gate_hit":
            self.play_effect_sound(self.gate_hit_sound, kind)
        elif kind == "gate_collect":
            self.play_effect_sound(self.gate_collect_sound, kind)

    def draw_menu_background(self) -> None:
        self.screen.fill((7, 10, 19))
        for index in range(18):
            x = (index * 149 + 37) % WIDTH
            y = (index * 83 + 31) % HEIGHT
            pygame.draw.circle(self.screen, (24, 71, 100), (x, y), 2 + index % 3)
        for offset in range(-300, WIDTH + 400, 170):
            pygame.draw.line(self.screen, (13, 42, 61), (offset, HEIGHT), (offset + 430, 0), 2)
        glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(glow, (32, 180, 255, 24), (WIDTH // 2, 250), 280)
        self.screen.blit(glow, (0, 0))

    def draw_menu_button(self, rect: pygame.Rect, text: str, color: tuple[int, int, int] = CYAN) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        fill = tuple(min(255, value + (18 if hovered else 0)) for value in PANEL)
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, color, rect, 3 if hovered else 2, border_radius=10)
        label = self.font.render(text, True, WHITE)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw_main_menu(self) -> None:
        self.draw_menu_background()
        accent = pygame.Rect(WIDTH // 2 - 255, 118, 510, 5)
        pygame.draw.rect(self.screen, CYAN, accent)
        title = self.font_huge.render("双线火力", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 205)))
        subtitle = self.font.render("八世界生存构筑测试版", True, YELLOW)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 276)))
        for index, (label, color) in enumerate((("开始游戏", GREEN), ("简易教学", CYAN), ("设置", PURPLE))):
            self.draw_menu_button(self.main_menu_button_rect(index), label, color)
        self.blit_text("Enter / Space 快速开始", (WIDTH // 2 - 112, 620), MUTED, self.font_tiny)

    def draw_tutorial(self) -> None:
        self.draw_menu_background()
        self.blit_text("测试员简易教学", (55, 40), WHITE, self.font_large)
        self.blit_text("目标：撑过每个世界并在120秒前击杀90秒出现的大Boss", (58, 105), YELLOW, self.font_small)
        sections = (
            ("移动与射击", "WASD移动；鼠标瞄准；按住左键自动射击。\n人口既是生命，也是子弹伤害倍率。"),
            ("敌人与Boss", "普通怪接触会损失人口，精英和Boss还会发射弹幕。\n小Boss约25秒、中Boss 60秒、大Boss 90秒出现。"),
            ("门的玩法", "射击数字门改变门上的人口数；解锁特殊门获得临时增益。\n移动到门内吃门。穿透不能穿门，反弹子弹会从门上弹回。"),
            ("商店与构筑", "击杀Boss获得金币；世界结束后购买卡牌或永久属性。\n最多携带5张卡。左键购买/出售，右键查看卡牌详情。"),
            ("测试提示", "Esc查看当前DPS、暴击和总音量；R可在暂停菜单重新开始。\n关注异常DPS、卡牌联动、碰撞和音频反馈。"),
            ("胜利条件", "依次击败8个世界的大Boss。人口低于2或120秒未完成则失败。"),
        )
        for index, (heading, body) in enumerate(sections):
            column = index % 2
            row = index // 2
            rect = pygame.Rect(55 + column * 610, 155 + row * 145, 570, 120)
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
            pygame.draw.rect(self.screen, CYAN if column == 0 else PURPLE, rect, 2, border_radius=10)
            self.blit_text(heading, (rect.x + 20, rect.y + 14), YELLOW, self.font_small)
            for line_index, line in enumerate(body.split("\n")):
                self.blit_text(line, (rect.x + 20, rect.y + 50 + line_index * 27), WHITE, self.font_tiny)
        self.draw_menu_button(self.menu_back_rect(), "返回", CYAN)

    def draw_settings(self) -> None:
        self.draw_menu_background()
        self.blit_text("设置", (55, 40), WHITE, self.font_large)
        self.blit_text("鼠标灵敏度范围 0.1–5.0，点击数字后可直接键盘输入", (58, 105), MUTED, self.font_small)

        sensitivity_rect = pygame.Rect(270, 145, 850, 52)
        pygame.draw.rect(self.screen, PANEL, sensitivity_rect, border_radius=8)
        self.blit_text("鼠标灵敏度", (sensitivity_rect.x + 22, sensitivity_rect.y + 13), WHITE, self.font_small)
        sensitivity_minus = self.settings_mouse_sensitivity_button_rect(-1)
        sensitivity_plus = self.settings_mouse_sensitivity_button_rect(1)
        pygame.draw.rect(self.screen, GRID, sensitivity_minus, border_radius=7)
        pygame.draw.rect(self.screen, GRID, sensitivity_plus, border_radius=7)
        self.blit_text("-", (sensitivity_minus.x + 17, sensitivity_minus.y + 5), WHITE, self.font)
        self.blit_text("+", (sensitivity_plus.x + 13, sensitivity_plus.y + 5), WHITE, self.font)
        value_rect = self.settings_mouse_sensitivity_value_rect()
        pygame.draw.rect(self.screen, (14, 20, 32), value_rect, border_radius=7)
        if self.mouse_sensitivity_editing:
            pygame.draw.rect(self.screen, CYAN, value_rect, 2, border_radius=7)
            text = self.sensitivity_input_text + "|"
        else:
            text = f"{self.mouse_sensitivity:g}"
        sensitivity = self.font.render(text, True, CYAN)
        self.screen.blit(sensitivity, sensitivity.get_rect(center=value_rect.center))

        self.blit_text("声音", (58, 225), WHITE, self.font_small)
        for index, (kind, label) in enumerate(self.settings_volume_rows()):
            y = self.settings_audio_y(index)
            rect = pygame.Rect(270, y, 850, 52)
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
            self.blit_text(label, (rect.x + 22, rect.y + 13), WHITE, self.font_small)
            minus = self.settings_volume_button_rect(index, -1)
            plus = self.settings_volume_button_rect(index, 1)
            pygame.draw.rect(self.screen, GRID, minus, border_radius=7)
            pygame.draw.rect(self.screen, GRID, plus, border_radius=7)
            self.blit_text("-", (minus.x + 17, minus.y + 5), WHITE, self.font)
            self.blit_text("+", (plus.x + 13, plus.y + 5), WHITE, self.font)
            value = self.font.render(f"{self.volume_value(kind):.0%}", True, CYAN)
            self.screen.blit(value, value.get_rect(center=(955, rect.centery)))
        self.draw_menu_button(self.menu_back_rect(), "返回", CYAN)

    def draw_arena(self) -> None:
        pygame.draw.rect(self.screen, PANEL, (0, PLAY_TOP, WIDTH, HEIGHT - PLAY_TOP))
        pygame.draw.line(self.screen, CYAN, (0, PLAY_TOP), (WIDTH, PLAY_TOP), 2)
        for x in range(0, WIDTH, 80):
            pygame.draw.line(self.screen, GRID, (x, 64), (x, HEIGHT), 1)
        for y in range(64, HEIGHT, 80):
            pygame.draw.line(self.screen, GRID, (0, y), (WIDTH, y), 1)
        self.blit_text("全宽随机生成区", (18, 73), MUTED, self.font_small)
        self.blit_text("玩家活动区域", (18, PLAY_TOP + 8), MUTED, self.font_small)

    def draw_player(self) -> None:
        pygame.draw.circle(self.screen, CYAN, self.player, self.player_radius)
        aim = self.aim_direction()
        pygame.draw.line(self.screen, WHITE, self.player, self.player + aim * 34, 6)
        visible = min(12, max(1, math.ceil(self.population / 5)))
        for index in range(visible):
            angle = index * math.tau / visible
            pygame.draw.circle(self.screen, (42, 137, 172), self.player + pygame.Vector2(math.cos(angle), math.sin(angle)) * 36, 5)

    def draw_bullets(self) -> None:
        for bullet in self.bullets:
            pygame.draw.circle(self.screen, YELLOW, bullet.position, bullet.radius)

    def draw_enemy_bullets(self) -> None:
        for bullet in self.enemy_bullets:
            pygame.draw.circle(self.screen, RED, bullet.position, bullet.radius)
            pygame.draw.circle(self.screen, ORANGE, bullet.position, bullet.radius, 2)

    def draw_enemies(self) -> None:
        for enemy in self.enemies:
            color = PURPLE if enemy.elite else GREEN
            pygame.draw.circle(self.screen, color, enemy.position, enemy.radius)
            if enemy.elite:
                pygame.draw.circle(self.screen, WHITE, enemy.position, enemy.radius, 3)
                self.draw_health_bar(enemy.position, enemy.radius + 12, enemy.hp, enemy.max_hp, PURPLE, 58)

    def draw_gates(self) -> None:
        buff_names = {"damage": "伤害门", "fire_rate": "射速门", "population": "征召门"}
        for gate in self.gates:
            if gate.kind == "number":
                color = GREEN if gate.value >= 0 else RED
                label = f"{gate.value:+d}"
            else:
                color = YELLOW if gate.unlocked else BLUE
                if gate.unlocked and gate.buff == "population":
                    label = f"征召门 ×{gate.recruit_multiplier:.1f}"
                else:
                    label = buff_names[gate.buff] if gate.unlocked else f"{buff_names[gate.buff]} {max(0, int(gate.hp))}"
            pygame.draw.rect(self.screen, color, gate.rect, 4, border_radius=8)
            surface = self.font.render(label, True, color)
            self.screen.blit(surface, surface.get_rect(center=gate.rect.center))
            if gate.kind == "special" and gate.hp > 0:
                self.draw_health_bar(gate.position, -gate.height // 2 + 8, gate.hp, gate.max_hp, BLUE, gate.width)
            elif gate.kind == "special" and gate.buff == "population":
                self.draw_health_bar(
                    gate.position,
                    -gate.height // 2 + 8,
                    gate.recruit_progress_fraction,
                    1.0,
                    GREEN,
                    gate.width,
                )

    def draw_bosses(self) -> None:
        colors = {"small": ORANGE, "medium": PURPLE, "big": RED}
        for boss in self.bosses:
            color = YELLOW if boss.windup_remaining is not None else colors[boss.kind]
            pygame.draw.circle(self.screen, color, boss.position, boss.radius)
            pygame.draw.circle(self.screen, WHITE, boss.position, boss.radius, 3)
            if boss.kind == "big":
                pygame.draw.circle(self.screen, DARK_RED, boss.position, round(boss.attack_range), 2)
            self.draw_health_bar(boss.position, boss.radius + 16, boss.hp, boss.max_hp, color, boss.radius * 3)
            text = self.font_tiny.render(self.boss_name(boss.kind), True, WHITE)
            self.screen.blit(text, text.get_rect(center=boss.position))
            if boss.windup_remaining is not None:
                self.blit_text(f"100%斩杀 {max(0, boss.windup_remaining):.1f}", boss.position + pygame.Vector2(-62, 67), YELLOW, self.font_small)
                danger = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                pygame.draw.circle(danger, (255, 40, 50, 45), boss.position, round(boss.attack_range))
                pygame.draw.circle(danger, (255, 80, 50, 180), boss.position, round(boss.attack_range), 5)
                self.screen.blit(danger, (0, 0))

    def draw_health_bar(self, position: pygame.Vector2, offset: int, hp: float, maximum: float, color: tuple[int, int, int], width: int) -> None:
        rect = pygame.Rect(round(position.x - width / 2), round(position.y - offset), width, 8)
        pygame.draw.rect(self.screen, (45, 48, 58), rect, border_radius=4)
        fill = rect.copy()
        fill.width = max(0, round(width * max(0, hp) / maximum))
        pygame.draw.rect(self.screen, color, fill, border_radius=4)

    def draw_hud(self) -> None:
        pygame.draw.rect(self.screen, (10, 12, 19), (0, 0, WIDTH, 64))
        self.blit_text(f"人口 {format_number(self.population)}", (18, 15), CYAN, self.font)
        self.blit_text(f"金币 {self.gold}", (180, 15), YELLOW, self.font)
        self.blit_text(f"世界 {self.world}/8", (310, 15), WHITE, self.font)
        remaining = max(0, math.ceil(WORLD_DURATION - self.elapsed))
        self.blit_text(f"截止 {remaining}s", (445, 15), RED if remaining <= 30 else WHITE, self.font)
        self.blit_text(f"伤害 {self.current_damage():.1f}  射速 {self.current_fire_rate():.1f}/s", (610, 18), MUTED, self.font_small)
        self.blit_text(f"参考DPS {format_number(world_dps_threshold(self.world))}", (825, 18), YELLOW, self.font_small)
        next_event = "小Boss 25~30s" if self.elapsed < 25 else "中Boss 60s" if self.elapsed < 60 else "大Boss 90s" if self.elapsed < 90 else "击杀大Boss！"
        self.blit_text(next_event, (1010, 18), YELLOW, self.font_small)
        if self.message_timer > 0:
            surface = self.font_small.render(self.message, True, YELLOW)
            rect = surface.get_rect(center=(WIDTH // 2, HEIGHT - 18)).inflate(20, 10)
            pygame.draw.rect(self.screen, (8, 10, 16), rect, border_radius=8)
            self.screen.blit(surface, surface.get_rect(center=rect.center))

    def draw_shop(self) -> None:
        self.screen.fill((12, 15, 24))
        self.blit_text(f"世界 {self.world} 通关商店", (50, 35), WHITE, self.font_large)
        self.blit_text(f"金币 {self.gold}", (1035, 48), YELLOW, self.font)
        self.blit_text("普通强化率15%；每个商品位独立有5%概率出现过载牌", (55, 115), MUTED, self.font_small)
        enhance_names = {"population": "+5人口", "fire_rate": "+10%射速", "damage": "+1基础伤害"}
        for index, offer in enumerate(self.shop_offers):
            rect = self.card_rect(index)
            if offer.is_overload:
                pygame.draw.rect(self.screen, (74, 18, 27), rect, border_radius=12)
                pygame.draw.rect(self.screen, OVERLOAD, rect, 4, border_radius=12)
                self.blit_text("过载", (rect.x + 18, rect.y + 16), OVERLOAD, self.font_small)
                category = CATEGORY_SPECS.get(offer.overload_category, offer.overload_category)
                label = self.font_large.render(category, True, WHITE)
                self.screen.blit(label, label.get_rect(center=(rect.centerx, rect.y + 100)))
                self.blit_text("真实卡牌将在交换成功时揭示", (rect.x + 18, rect.y + 145), MUTED, self.font_tiny)
                self.blit_text(
                    f"拖入普通卡牌  {offer.exchange_value}/{OVERLOAD_EXCHANGE_COST}",
                    (rect.x + 18, rect.bottom - 42),
                    YELLOW,
                    self.font_small,
                )
                continue
            card = offer.card
            if card is None:
                continue
            color = RARITY_COLORS[card.rarity]
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=12)
            pygame.draw.rect(self.screen, color, rect, 3, border_radius=12)
            self.blit_text(card.rarity, (rect.x + 18, rect.y + 16), color, self.font_small)
            price = self.card_purchase_price(card)
            self.blit_text(f"{price} 金币", (rect.right - 88, rect.y + 16), YELLOW, self.font_tiny)
            if offer.enhancement:
                self.blit_text(f"强化：{enhance_names[offer.enhancement]}", (rect.x + 18, rect.y + 48), GREEN, self.font_tiny)
            name = self.font.render(card.name, True, WHITE)
            self.screen.blit(name, name.get_rect(center=(rect.centerx, rect.y + 92)))
            self.draw_wrapped(card.description, pygame.Rect(rect.x + 18, rect.y + 125, rect.width - 36, 75), MUTED)
            self.blit_text("点击购买", (rect.x + 78, rect.bottom - 35), CYAN, self.font_small)

        self.blit_text("永久默认属性（可重复购买）", (910, 105), MUTED, self.font_small)
        attrs = (
            ("默认人口 +2", "population"),
            ("基础伤害 +1", "damage"),
            ("默认射速 +0.8", "fire_rate"),
        )
        for index, (label, key) in enumerate(attrs):
            rect = self.attribute_rect(index)
            price = attribute_price(self.attribute_purchases[key])
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
            pygame.draw.rect(self.screen, CYAN, rect, 2, border_radius=10)
            self.blit_text(label, (rect.x + 16, rect.y + 13), WHITE, self.font_small)
            self.blit_text(f"等级 {self.attribute_purchases[key]} | {price} 金币", (rect.x + 16, rect.y + 44), YELLOW, self.font_tiny)

        collection = self.visible_card_collection()
        slot_count = 2 if self.card_page == "overload" else 5
        page_name = "过载卡槽 2槽" if self.card_page == "overload" else "普通卡槽 5槽"
        self.blit_text(f"{page_name}（拖动出售，右键查看详情）", (55, 445), MUTED, self.font_small)
        for index in range(slot_count):
            rect = self.slot_rect(index)
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
            if index < len(collection):
                owned = collection[index]
                card = CARD_BY_KEY[owned.key]
                card_color = OVERLOAD if self.card_page == "overload" else RARITY_COLORS[card.rarity]
                pygame.draw.rect(self.screen, card_color, rect, 3 if self.card_page == "overload" else 2, border_radius=8)
                self.blit_text(card.name, (rect.x + 10, rect.y + 20), WHITE, self.font_tiny)
                if owned.enhancement and owned.enhancement != "overload":
                    self.blit_text(f"强化 {enhance_names[owned.enhancement]}", (rect.x + 10, rect.y + 48), GREEN, self.font_tiny)
                if self.card_page == "overload":
                    sale_text = "下次商店可售" if owned.acquired_shop_round >= self.shop_round else "卖出 +20"
                else:
                    sale_text = f"交换值/卖价 {self.card_sale_price(owned)}"
                self.blit_text(sale_text, (rect.x + 10, rect.y + 82), YELLOW, self.font_tiny)
            else:
                self.blit_text("空过载槽" if self.card_page == "overload" else "空卡槽", (rect.x + 35, rect.y + 50), MUTED, self.font_tiny)

        page_button = self.shop_page_button_rect()
        pygame.draw.rect(self.screen, OVERLOAD if self.card_page == "normal" else BLUE, page_button, border_radius=8)
        page_label = "查看过载卡槽" if self.card_page == "normal" else "查看普通卡槽"
        self.blit_text(page_label, (page_button.x + 20, page_button.y + 12), WHITE, self.font_small)
        sell_rect = self.shop_sell_rect()
        pygame.draw.rect(self.screen, (55, 22, 28), sell_rect, border_radius=8)
        pygame.draw.rect(self.screen, RED, sell_rect, 2, border_radius=8)
        sell_label = "将卡牌拖到这里出售（过载牌固定 20 金币）"
        self.blit_text(sell_label, (sell_rect.x + 70, sell_rect.y + 12), WHITE, self.font_small)

        refresh = pygame.Rect(910, 495, 150, 52)
        next_rect = pygame.Rect(1080, 495, 145, 52)
        pygame.draw.rect(self.screen, BLUE, refresh, border_radius=8)
        pygame.draw.rect(self.screen, GREEN, next_rect, border_radius=8)
        charged = max(0, round(self.apply_stat(self.refresh_cost, "refresh_cost", TARGET_PLAYER)))
        self.blit_text(f"刷新 {charged}金", (refresh.x + 25, refresh.y + 13), WHITE, self.font_small)
        self.blit_text("下一世界", (next_rect.x + 25, next_rect.y + 13), BG, self.font_small)
        self.blit_text(
            f"下世界基础：人口 {self.default_population} | 伤害 {self.default_damage:.1f} | 射速 {self.default_fire_rate:.1f}",
            (910, 575),
            MUTED,
            self.font_tiny,
        )
        if self.message_timer > 0:
            self.blit_text(self.message, (910, 610), YELLOW, self.font_tiny)
        if self.detail_card:
            self.draw_card_detail(self.detail_card)
        elif self.dragging_card:
            card = CARD_BY_KEY[self.dragging_card.key]
            position = pygame.Vector2(pygame.mouse.get_pos())
            ghost = pygame.Rect(round(position.x - 75), round(position.y - 35), 150, 70)
            color = OVERLOAD if self.dragging_from == "overload" else RARITY_COLORS[card.rarity]
            pygame.draw.rect(self.screen, PANEL, ghost, border_radius=8)
            pygame.draw.rect(self.screen, color, ghost, 3, border_radius=8)
            name = self.font_tiny.render(card.name, True, WHITE)
            self.screen.blit(name, name.get_rect(center=ghost.center))

    def draw_card_detail(self, owned: OwnedCard) -> None:
        card = CARD_BY_KEY[owned.key]
        enhance_names = {"population": "每个世界初始人口额外 +5", "fire_rate": "射速增益 +10%", "damage": "基础伤害 +1"}
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        rect = pygame.Rect(350, 190, 580, 310)
        color = OVERLOAD if owned.enhancement == "overload" else RARITY_COLORS[card.rarity]
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=14)
        pygame.draw.rect(self.screen, color, rect, 4, border_radius=14)
        self.blit_text(f"{card.name}  [{card.rarity}]", (rect.x + 35, rect.y + 30), color, self.font_large)
        self.blit_text("卡牌功效", (rect.x + 35, rect.y + 105), MUTED, self.font_small)
        self.draw_wrapped(card.description, pygame.Rect(rect.x + 35, rect.y + 140, rect.width - 70, 70), WHITE)
        enhancement = "过载牌（独立卡槽）" if owned.enhancement == "overload" else enhance_names.get(owned.enhancement, "无附加强化")
        enhancement_color = OVERLOAD if owned.enhancement == "overload" else GREEN if owned.enhancement else MUTED
        self.blit_text(f"附加效果：{enhancement}", (rect.x + 35, rect.y + 220), enhancement_color, self.font_small)
        if card.category == "growth":
            self.blit_text(f"当前成长层数：{self.growth_level(owned)}", (rect.x + 35, rect.y + 255), YELLOW, self.font_small)
        self.blit_text("右键卡槽或空白处关闭", (rect.right - 220, rect.bottom - 30), MUTED, self.font_tiny)

    def draw_wrapped(self, text: str, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
        line = ""
        y = rect.y
        for char in text:
            candidate = line + char
            if self.font_small.size(candidate)[0] > rect.width:
                self.blit_text(line, (rect.x, y), color, self.font_small)
                line = char
                y += 28
            else:
                line = candidate
        if line:
            self.blit_text(line, (rect.x, y), color, self.font_small)

    def draw_overlay(self, title_text: str, detail: str) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 7, 12, 205))
        self.screen.blit(overlay, (0, 0))
        title = self.font_huge.render(title_text, True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 45)))
        subtitle = self.font.render(detail, True, YELLOW)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 55)))

    @staticmethod
    def pause_restart_rect() -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 - 260, 575, 250, 58)

    @staticmethod
    def pause_main_menu_rect() -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 + 10, 575, 250, 58)

    @staticmethod
    def pause_volume_button_rect(kind: str, direction: int) -> pygame.Rect:
        y = 414 if kind == "sfx" else 464
        x = WIDTH // 2 + (-5 if direction < 0 else 145)
        return pygame.Rect(x, y, 42, 38)

    def draw_pause_menu(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 7, 12, 215))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(WIDTH // 2 - 270, 55, 540, 610)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=16)
        pygame.draw.rect(self.screen, CYAN, panel, 3, border_radius=16)

        title = self.font_large.render("游戏暂停", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 110)))
        self.blit_text("当前局内属性", (panel.x + 45, 165), MUTED, self.font_small)

        stats = (
            ("理论 DPS", format_number(self.current_dps()), YELLOW),
            ("暴击率", f"{self.critical_chance():.1%}", CYAN),
            ("暴击伤害", f"{self.critical_damage_multiplier():.0%}", ORANGE),
        )
        for index, (label, value, color) in enumerate(stats):
            y = 205 + index * 55
            self.blit_text(label, (panel.x + 55, y), MUTED, self.font)
            value_surface = self.font.render(value, True, color)
            self.screen.blit(value_surface, value_surface.get_rect(topright=(panel.right - 55, y)))

        self.blit_text("音量", (panel.x + 45, 370), MUTED, self.font_small)
        for kind, label, value in (
            ("sfx", "枪声音效", self.sfx_volume),
            ("bgm", "背景音乐", self.bgm_volume),
        ):
            y = 414 if kind == "sfx" else 464
            self.blit_text(label, (panel.x + 55, y + 6), WHITE, self.font_small)
            minus = self.pause_volume_button_rect(kind, -1)
            plus = self.pause_volume_button_rect(kind, 1)
            pygame.draw.rect(self.screen, GRID, minus, border_radius=7)
            pygame.draw.rect(self.screen, GRID, plus, border_radius=7)
            self.blit_text("-", (minus.x + 15, minus.y + 3), WHITE, self.font)
            self.blit_text("+", (plus.x + 12, plus.y + 3), WHITE, self.font)
            volume = self.font_small.render(f"{value:.0%}", True, CYAN)
            self.screen.blit(volume, volume.get_rect(center=(WIDTH // 2 + 91, y + 19)))

        self.blit_text("Esc 继续游戏", (panel.x + 175, 525), WHITE, self.font_small)
        self.blit_text("F1 开发者测试面板", (panel.x + 45, 498), CYAN, self.font_small)
        restart = self.pause_restart_rect()
        pygame.draw.rect(self.screen, RED, restart, border_radius=10)
        restart_label = self.font.render("重新开始  R", True, WHITE)
        self.screen.blit(restart_label, restart_label.get_rect(center=restart.center))

        main_menu = self.pause_main_menu_rect()
        pygame.draw.rect(self.screen, GRID, main_menu, border_radius=10)
        pygame.draw.rect(self.screen, MUTED, main_menu, 2, border_radius=10)
        main_menu_label = self.font.render("返回主菜单", True, WHITE)
        self.screen.blit(main_menu_label, main_menu_label.get_rect(center=main_menu.center))

    def blit_text(self, text: str, position: tuple[int, int] | pygame.Vector2, color: tuple[int, int, int], font: pygame.font.Font) -> None:
        self.screen.blit(font.render(text, True, color), position)

    def run(self) -> None:
        self.load_settings()
        self.apply_audio_volumes()
        try:
            while self.running:
                dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
                for event in pygame.event.get():
                    self.handle_event(event)
                self.update(dt)
                self.draw()
        finally:
            self.save_settings()
            self._disable_relative_mouse()
            pygame.mouse.set_visible(True)
            pygame.quit()


if __name__ == "__main__":
    Game(show_main_menu=True).run()
