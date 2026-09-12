from __future__ import annotations

import math
import os
import json
import random
import sys
import copy
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
    world_boss_spawn_time,
    world_duration,
    world_target_health,
)


WIDTH, HEIGHT = 1280, 720
PLAY_TOP = int(HEIGHT * 0.70)
FPS = 60
WORLD_DURATION = 120.0
MAX_WORLD = 10
FINAL_CHALLENGE_WORLDS = (9, 10)

BG = (3, 5, 15)
PANEL = (10, 15, 31)
PANEL_RAISED = (17, 25, 48)
GRID = (34, 48, 77)
UI_RIM = (65, 94, 132)
WHITE = (241, 248, 255)
MUTED = (151, 174, 205)
CYAN = (36, 226, 255)
BLUE = (52, 105, 255)
RED = (235, 78, 89)
DARK_RED = (112, 39, 47)
GREEN = (86, 255, 181)
YELLOW = (255, 221, 77)
ORANGE = (255, 126, 56)
PURPLE = (184, 79, 255)
MAGENTA = (255, 48, 187)
GLASS_TINT = (8, 14, 34, 226)
GLASS_RIM = (173, 235, 255, 76)
STEP_OFF = (22, 31, 52)
STEP_DIM = (43, 73, 105)
RARITY_COLORS = {"普通": WHITE, "罕见": PURPLE, "稀有": YELLOW}

CURSOR_TRAIL_MAX_AGE = 0.42
CURSOR_TRAIL_CAP = 30
CURSOR_PARTICLE_CAP = 140
CURSOR_PALETTE = (CYAN, (96, 255, 255), BLUE, PURPLE, WHITE)
CROSSHAIR_PRESETS = (
    {"key": "classic", "name": "经典环形", "palette": CURSOR_PALETTE},
    {"key": "osu", "name": "OSU 流光", "palette": (CYAN, WHITE, (96, 255, 255), BLUE)},
    {"key": "neon", "name": "霓虹十字", "palette": (PURPLE, CYAN, (255, 96, 220), WHITE)},
    {"key": "void", "name": "虚空三角", "palette": (PURPLE, BLUE, (120, 80, 255), WHITE)},
    {"key": "hex", "name": "六边形脉冲", "palette": (ORANGE, YELLOW, (255, 220, 120), WHITE)},
)
CROSSHAIR_BOX = 72
CROSSHAIR_SUPERSAMPLE = 2
DEATH_PARTICLE_CAP = 360
BLOOD_STAIN_CAP = 96
SHAKE_STRENGTH_CAP = 18.0
GLOW_LEVEL_SCALES = (2, 4, 8)
NORMAL_ENEMY_SPRITE_SIZE = 40
NORMAL_ENEMY_FRAME_COUNT = 4
NORMAL_ENEMY_DIRECTION_COUNT = 16
NORMAL_ENEMY_ANIMATION_FPS = 7.0
ELITE_SPRITE_SIZE = 64
ELITE_KINDS = ("guardian", "archon", "hunter")
ELITE_NAMES = {
    "guardian": "棱镜守卫",
    "archon": "链接执政官",
    "hunter": "过载猎手",
}
ELITE_COLORS = {
    "guardian": CYAN,
    "archon": (70, 235, 255),
    "hunter": ORANGE,
}
BOSS_SPRITE_SIZES = {"small": 72, "medium": 88, "big": 112}
PLAYER_BODY_STEP_DEGREES = 90.0
PLAYER_BODY_TURN_THRESHOLD = PLAYER_BODY_STEP_DEGREES / 2
ESCORT_RING_SPECS = (
    (100_000, 50.0, 12),
    (8_000_000, 70.0, 16),
    (100_000_000, 92.0, 20),
)
BLOOD_STAIN_VARIANT_COUNT = 15
BLOOD_STAIN_ROTATION_COUNT = 4
KILL_CHANNEL_IDS = (3, 4, 5, 8)
BOSS_KILL_CHANNEL_ID = 7
BOSS_KILL_VOLUME_BOOST = 1.20
KILL_TAIL_DUCKING = 1.20
KILL_SOUND_FADE_IN_MS = 8
RANK_CHANNEL_ID = 9
RANK_SOUND_SEGMENTS = {
    "Overkill": (0.00, 3.85),
    "S": (4.15, 6.75),
    "A": (8.65, 11.20),
    "B": (12.60, 15.10),
    "C": (16.14, 18.86),
    "D": (19.25, 21.10),
}
OVERKILL_STUTTER_RANGE = (0.055, 0.255)
OVERKILL_STUTTER_GAP = 0.06
OVERKILL_STUTTER_COUNT = 4
SETTLEMENT_SLOWMO_DURATION = 1.0
SETTLEMENT_SLOWMO_SCALE = 0.25
SETTLEMENT_PANEL_DURATION = 0.45
SETTLEMENT_PANEL_Y = 90
SETTLEMENT_FIRST_ROW_DELAY = 0.35
SETTLEMENT_ROW_INTERVAL = 0.55
SETTLEMENT_SCORE_DELAY = 0.55
SETTLEMENT_RANK_DROP_DURATION = 0.38
SETTLEMENT_BUTTON_DELAY = 0.75
SETTLEMENT_RANK_IMPACT_SCALE = 1.18
SETTLEMENT_SCORE_IMPACT_VOLUME_BOOST = 1.25
SETTLEMENT_RANK_THRESHOLDS = (
    ("Overkill", 92, (255, 55, 70)),
    ("S", 78, YELLOW),
    ("A", 60, GREEN),
    ("B", 38, BLUE),
    ("C", 20, MUTED),
    ("D", 0, (116, 88, 96)),
)
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
    CHALLENGE_CHOICE = auto()


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
class EliteShield:
    angle: float
    hp: float
    max_hp: float
    orbit_radius: float = 27.0
    radius: float = 10.0

    def world_position(self, owner: pygame.Vector2) -> pygame.Vector2:
        return owner + pygame.Vector2(0, -self.orbit_radius).rotate(self.angle)


@dataclass
class Enemy:
    position: pygame.Vector2
    hp: float
    max_hp: float
    speed: float
    radius: int
    elite: bool = False
    elite_kind: str | None = None
    shoot_timer: float = 2.5
    animation_time: float = 0.0
    heading_degrees: float = 180.0
    shields: list[EliteShield] = field(default_factory=list)
    elite_state: str = "approach"
    state_timer: float = 0.0
    vulnerable_timer: float = 0.0
    disabled_timer: float = 0.0
    linked_target_ids: set[int] = field(default_factory=set)
    charge_direction: pygame.Vector2 = field(default_factory=pygame.Vector2)

    def update(self, dt: float, player: pygame.Vector2, speed_multiplier: float = 1.0) -> None:
        if self.disabled_timer > 0:
            self.disabled_timer = max(0.0, self.disabled_timer - dt)
            self.animation_time += dt
            return
        direction = pygame.Vector2(0, 1) if self.position.y < HEIGHT * 0.48 else normalized(player - self.position)
        if direction.length_squared():
            self.heading_degrees = math.degrees(math.atan2(-direction.x, -direction.y))
        self.animation_time += dt
        self.position += direction * self.speed * max(0.0, speed_multiplier) * dt


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
class DeathParticle:
    position: pygame.Vector2
    velocity: pygame.Vector2
    life: float
    max_life: float
    radius: float
    color: tuple[int, int, int] = (245, 248, 255)


@dataclass
class BloodStain:
    position: pygame.Vector2
    points: tuple[pygame.Vector2, ...]
    droplets: tuple[tuple[pygame.Vector2, float], ...]
    life: float
    max_life: float
    color: tuple[int, int, int] = (73, 190, 67)
    sprite: pygame.Surface | None = None


@dataclass
class SettlementRow:
    key: str
    label: str
    value_text: str
    detail_text: str
    magnitude: float
    color: tuple[int, int, int]


@dataclass
class SettlementState:
    phase: str
    timer: float
    row_index: int
    rows: list[SettlementRow]
    score: int
    rank: str
    panel_y: float
    pop_timer: float


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
    variant: str = "standard"
    phase: int = 1
    rage_stacks: int = 0
    pattern_index: int = 0
    roam_direction: pygame.Vector2 = field(
        default_factory=lambda: pygame.Vector2(1.0, 0.35).normalize()
    )

    @property
    def effective_speed(self) -> float:
        return self.speed * (1.0 + 0.05 * self.rage_stacks)

    def update(self, dt: float, player: pygame.Vector2) -> bool:
        if self.kind != "big":
            self.position.y += self.effective_speed * dt
            return False
        if self.variant != "standard" and self.phase == 1:
            self.position += self.roam_direction * self.effective_speed * dt
            min_x = self.radius + 10
            max_x = WIDTH - self.radius - 10
            min_y = self.radius + 10
            max_y = PLAY_TOP - self.radius - 20
            if self.position.x <= min_x or self.position.x >= max_x:
                self.position.x = max(min_x, min(max_x, self.position.x))
                self.roam_direction.x *= -1
            if self.position.y <= min_y or self.position.y >= max_y:
                self.position.y = max(min_y, min(max_y, self.position.y))
                self.roam_direction.y *= -1
            return False
        if self.windup_remaining is not None:
            self.position += normalized(player - self.position) * self.effective_speed * self.windup_move_factor * dt
            self.windup_remaining -= dt
            if self.windup_remaining <= 0:
                hit_player = self.position.distance_to(player) <= self.attack_range
                self.windup_remaining = None
                return hit_player
            return False
        if self.position.distance_to(player) <= self.attack_range:
            self.windup_remaining = self.windup_duration
        else:
            self.position += normalized(player - self.position) * self.effective_speed * dt
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


@dataclass
class ChallengeCheckpoint:
    run_state: dict[str, object]
    rng_state: object


class Game:
    _audio_cache: tuple[object, ...] | None = None
    _player_body_sprite_cache: tuple[pygame.Surface, ...] | None = None
    _player_gun_sprite_cache: pygame.Surface | None = None
    _normal_enemy_sprite_cache: tuple[tuple[pygame.Surface, ...], ...] | None = None
    _elite_sprite_cache: dict[str, tuple[pygame.Surface, ...]] | None = None
    _boss_sprite_cache: dict[str, tuple[pygame.Surface, ...]] | None = None
    _blood_stain_sprite_cache: tuple[pygame.Surface, ...] | None = None

    def __init__(self, show_main_menu: bool = False) -> None:
        os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_WARP", "0")
        pygame.mixer.pre_init(44100, -16, 2, 256)
        pygame.init()
        pygame.display.set_caption("火力过载 - 十世界终局挑战")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.normal_enemy_sprites = self.load_normal_enemy_sprites()
        self.elite_sprites = self.load_elite_sprites()
        self.boss_sprites = self.load_boss_sprites()
        self.font_tiny = load_font(16)
        self.font_small = load_font(20)
        self.font = load_font(26)
        self.font_large = load_font(42, True)
        self.font_huge = load_font(68, True)
        mono_path = pygame.font.match_font(["cascadiamono", "consolas", "microsoftyahei"])
        self.font_numeric = pygame.font.Font(mono_path, 22)
        self.font_numeric_large = pygame.font.Font(mono_path, 42)
        self.rng = random.Random()
        self.audio_rng = random.Random()
        self.cursor_rng = random.Random()
        self.visual_rng = random.Random()
        self.running = True
        self.mouse_sensitivity = 1.0
        self.aim_position = pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        self.crosshair_preset = "classic"
        self.mouse_sensitivity_editing = False
        self.sensitivity_input_text = ""
        self.dev_panel_open = False
        self.dev_editing_field: str | None = None
        self.dev_input_text = ""
        self.sprite_calibration_open = False
        self.sprite_calibration_editing: str | None = None
        self.sprite_calibration_input = ""
        self.player_center_offset = pygame.Vector2()
        self.gun_center_offset = pygame.Vector2()
        self.cursor_time = 0.0
        self.cursor_phase = 0.0
        self.cursor_trail: list[tuple[float, pygame.Vector2]] = []
        self.cursor_particles: list[CursorParticle] = []
        self.cursor_spawn_timer = 0.0
        self.last_cursor_pos: pygame.Vector2 | None = None
        self.cursor_glow_small_surface = pygame.Surface((WIDTH // 4, HEIGHT // 4))
        self.cursor_glow_surface = pygame.Surface((WIDTH, HEIGHT))
        self.shake_intensity = 0.7
        self.glow_brightness = 0.4
        self.glow_spread = 0.55
        self.glow_opacity = 0.6
        self.glow_feather = 0.7
        self.shake_strength = 0.0
        self.shake_timer = 0.0
        self.shake_duration = 0.0
        self.kill_combo = 0
        self.kill_combo_timer = 0.0
        self.blood_stains: list[BloodStain] = []
        self.death_particles: list[DeathParticle] = []
        self.settlement: SettlementState | None = None
        self.settlement_particles: list[DeathParticle] = []
        self.settlement_rank_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}
        self.total_damage_dealt = 0.0
        self.world_boss_gold = 0
        self.world_interest = 0
        self.challenge_checkpoint: ChallengeCheckpoint | None = None
        self.population_basis = 1
        self.challenge_world_growth_bonus = 0
        self.challenge_shop_population_bonus = 0
        self.challenge_shop_card_credits: dict[int, int] = {}
        self.visual_effect_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.glow_source_surface = pygame.Surface((WIDTH, HEIGHT))
        self.glow_cache = tuple(
            (
                pygame.Surface((WIDTH // scale, HEIGHT // scale)),
                pygame.Surface((WIDTH // scale, HEIGHT // scale)),
                pygame.Surface((WIDTH, HEIGHT)),
            )
            for scale in GLOW_LEVEL_SCALES
        )
        self.sfx_volume = 0.7
        self.bgm_volume = 0.4
        self.effect_volumes = {
            "shot": 1.0,
            "enemy_hit": 1.0,
            "kill": 1.0,
            "gate_hit": 1.0,
            "gate_collect": 1.0,
            "settlement": 1.0,
        }
        self.audio_available = False
        self.shot_sound: pygame.mixer.Sound | None = None
        self.kill_sounds: tuple[pygame.mixer.Sound, ...] = ()
        self.kill_channels: tuple[pygame.mixer.Channel, ...] = ()
        self.boss_kill_channel: pygame.mixer.Channel | None = None
        self.kill_channel_cursor = 0
        self.enemy_hit_sound: pygame.mixer.Sound | None = None
        self.gate_hit_sound: pygame.mixer.Sound | None = None
        self.gate_collect_sound: pygame.mixer.Sound | None = None
        self.settlement_slam_sound: pygame.mixer.Sound | None = None
        self.settlement_score_sound: pygame.mixer.Sound | None = None
        self.rank_sounds: dict[str, pygame.mixer.Sound] = {}
        self.rank_channel: pygame.mixer.Channel | None = None
        self.settlement_channel: pygame.mixer.Channel | None = None
        self.bgm_tracks: tuple[pygame.mixer.Sound, ...] = ()
        self.bgm_channels: tuple[pygame.mixer.Channel, ...] = ()
        self.bgm_track_index = 0
        self.bgm_elapsed = 0.0
        self.initialize_audio()
        self.reset_run()
        if show_main_menu:
            self.mode = Mode.MAIN_MENU
            self.sync_mouse_mode()

    @classmethod
    def load_player_sprites(cls) -> tuple[tuple[pygame.Surface, ...], pygame.Surface]:
        if cls._player_body_sprite_cache is None:
            # A single orthographic hull keeps the dorsal turret silhouette and
            # mount point consistent in every direction.  Rotate it with aiming
            # instead of switching between perspective-painted hull variants.
            top_down = pygame.image.load(
                asset_path("assets/player/falcon_body_00.png")
            ).convert_alpha()
            cls._player_body_sprite_cache = tuple(
                pygame.transform.rotate(top_down, -PLAYER_BODY_STEP_DEGREES * step)
                for step in range(round(360 / PLAYER_BODY_STEP_DEGREES))
            )
        if cls._player_gun_sprite_cache is None:
            cls._player_gun_sprite_cache = pygame.image.load(
                asset_path("assets/player/falcon_gun.png")
            ).convert_alpha()
        return cls._player_body_sprite_cache, cls._player_gun_sprite_cache

    @classmethod
    def load_normal_enemy_sprites(cls) -> tuple[tuple[pygame.Surface, ...], ...]:
        """Load native pixel frames once and cache directional sprites."""
        if cls._normal_enemy_sprite_cache is not None:
            return cls._normal_enemy_sprite_cache

        animation_frames: list[tuple[pygame.Surface, ...]] = []
        angle_step = 360.0 / NORMAL_ENEMY_DIRECTION_COUNT
        for frame_index in range(NORMAL_ENEMY_FRAME_COUNT):
            source = pygame.image.load(
                asset_path(f"assets/enemies/pulse_sac/pulse_sac_{frame_index:02}.png")
            ).convert_alpha()
            scaled = pygame.transform.scale(
                source,
                (NORMAL_ENEMY_SPRITE_SIZE, NORMAL_ENEMY_SPRITE_SIZE),
            )
            animation_frames.append(
                tuple(
                    pygame.transform.rotate(scaled, direction_index * angle_step)
                    for direction_index in range(NORMAL_ENEMY_DIRECTION_COUNT)
                )
            )
        cls._normal_enemy_sprite_cache = tuple(animation_frames)
        return cls._normal_enemy_sprite_cache

    @classmethod
    def load_elite_sprites(cls) -> dict[str, tuple[pygame.Surface, ...]]:
        if cls._elite_sprite_cache is not None:
            return cls._elite_sprite_cache
        sprites: dict[str, tuple[pygame.Surface, ...]] = {}
        for kind in ELITE_KINDS:
            frames = []
            for frame_index in range(4):
                source = pygame.image.load(
                    asset_path(f"assets/enemies/elites/{kind}/{kind}_{frame_index:02}.png")
                ).convert_alpha()
                frames.append(
                    pygame.transform.scale(source, (ELITE_SPRITE_SIZE, ELITE_SPRITE_SIZE))
                )
            sprites[kind] = tuple(frames)
        cls._elite_sprite_cache = sprites
        return cls._elite_sprite_cache

    @classmethod
    def load_boss_sprites(cls) -> dict[str, tuple[pygame.Surface, ...]]:
        if cls._boss_sprite_cache is not None:
            return cls._boss_sprite_cache
        sprites: dict[str, tuple[pygame.Surface, ...]] = {}
        for kind, size in BOSS_SPRITE_SIZES.items():
            frames = []
            for frame_index in range(4):
                source = pygame.image.load(
                    asset_path(f"assets/bosses/{kind}/{kind}_{frame_index:02}.png")
                ).convert_alpha()
                frames.append(pygame.transform.scale(source, (size, size)))
            sprites[kind] = tuple(frames)
        cls._boss_sprite_cache = sprites
        return cls._boss_sprite_cache

    @classmethod
    def load_blood_stain_sprites(cls) -> tuple[pygame.Surface, ...]:
        if cls._blood_stain_sprite_cache is not None:
            return cls._blood_stain_sprite_cache
        sprites: list[pygame.Surface] = []
        for variant in range(BLOOD_STAIN_VARIANT_COUNT):
            source = pygame.image.load(
                asset_path(f"assets/effects/blood_splats/blood_splats_{variant:02}.png")
            ).convert_alpha()
            base = pygame.transform.scale(source, (128, 128))
            sprites.extend(
                pygame.transform.rotate(base, rotation * 360.0 / BLOOD_STAIN_ROTATION_COUNT)
                for rotation in range(BLOOD_STAIN_ROTATION_COUNT)
            )
        cls._blood_stain_sprite_cache = tuple(sprites)
        return cls._blood_stain_sprite_cache

    def initialize_audio(self) -> None:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(44100, -16, 2, 256)
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            pygame.mixer.set_reserved(10)
            if Game._audio_cache is None:
                rank_sheet = pygame.mixer.Sound(asset_path("SFX/Ranks.mp3"))
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
                    self.split_rank_sounds(rank_sheet),
                )
            (
                self.shot_sound,
                self.bgm_tracks,
                self.kill_sounds,
                self.enemy_hit_sound,
                self.gate_hit_sound,
                self.gate_collect_sound,
                self.rank_sounds,
            ) = Game._audio_cache
            self.settlement_slam_sound = self.synth_impact_sound(150.0, 55.0, 0.18, 0.9)
            self.settlement_score_sound = self.synth_impact_sound(105.0, 36.0, 0.55, 1.0)
            self.shot_channel = pygame.mixer.Channel(2)
            self.kill_channels = tuple(pygame.mixer.Channel(channel_id) for channel_id in KILL_CHANNEL_IDS)
            self.boss_kill_channel = pygame.mixer.Channel(BOSS_KILL_CHANNEL_ID)
            self.settlement_channel = pygame.mixer.Channel(6)
            self.rank_channel = pygame.mixer.Channel(RANK_CHANNEL_ID)
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
        for channel in self.kill_channels:
            channel.set_volume(self.effective_sfx_volume("kill"))
        if self.boss_kill_channel is not None:
            self.boss_kill_channel.set_volume(
                min(1.0, self.effective_sfx_volume("kill") * BOSS_KILL_VOLUME_BOOST)
            )
        if self.settlement_channel is not None:
            self.settlement_channel.set_volume(self.effective_sfx_volume("settlement"))
        if self.rank_channel is not None:
            self.rank_channel.set_volume(self.effective_sfx_volume("settlement"))
        for channel in self.bgm_channels:
            channel.set_volume(self.bgm_volume)

    @staticmethod
    def synth_impact_sound(
        start_freq: float,
        end_freq: float,
        duration: float,
        gain: float,
    ) -> pygame.mixer.Sound | None:
        try:
            import numpy as np

            rate = 44100
            count = int(rate * duration)
            t = np.linspace(0.0, duration, count, endpoint=False)
            freq = np.linspace(start_freq, end_freq, count)
            phase = 2.0 * np.pi * np.cumsum(freq) / rate
            noise = np.random.default_rng(7).uniform(-0.5, 0.5, count)
            envelope = np.exp(-t * 16.0)
            wave = (np.sin(phase) + noise * np.exp(-t * 60.0)) * envelope
            wave *= gain * (32767 * 0.6) / max(1e-9, float(np.max(np.abs(wave))))
            stereo = np.repeat(wave[:, None].astype(np.int16), 2, axis=1)
            return pygame.mixer.Sound(buffer=stereo.tobytes())
        except (ImportError, ValueError, pygame.error):
            return None

    @staticmethod
    def split_rank_sounds(rank_sheet: pygame.mixer.Sound) -> dict[str, pygame.mixer.Sound]:
        mixer_init = pygame.mixer.get_init()
        if mixer_init is None:
            return {}
        frequency, sample_format, channels = mixer_init
        frame_size = max(1, abs(sample_format) // 8) * channels
        raw = rank_sheet.get_raw()
        sounds: dict[str, pygame.mixer.Sound] = {}

        def clip_bytes(start: float, end: float) -> bytes:
            start_byte = round(start * frequency) * frame_size
            end_byte = min(len(raw), round(end * frequency) * frame_size)
            return raw[start_byte:end_byte]

        for rank, (start, end) in RANK_SOUND_SEGMENTS.items():
            sounds[rank] = pygame.mixer.Sound(buffer=clip_bytes(start, end))

        onset = clip_bytes(*OVERKILL_STUTTER_RANGE)
        silence = bytes(round(OVERKILL_STUTTER_GAP * frequency) * frame_size)
        full_overkill = clip_bytes(*RANK_SOUND_SEGMENTS["Overkill"])
        sounds["Overkill"] = pygame.mixer.Sound(
            buffer=(onset + silence) * OVERKILL_STUTTER_COUNT + full_overkill
        )
        return sounds

    def play_settlement_impact(self, big: bool = False) -> None:
        if not self.audio_available or self.settlement_channel is None:
            return
        sound = self.settlement_score_sound if big else self.settlement_slam_sound
        if sound is None:
            return
        volume = self.effective_sfx_volume("settlement")
        if big:
            volume = min(1.0, volume * SETTLEMENT_SCORE_IMPACT_VOLUME_BOOST)
        self.settlement_channel.set_volume(volume)
        self.settlement_channel.play(sound)

    def play_settlement_rank_sound(self) -> None:
        if self.settlement is None or not self.audio_available or self.rank_channel is None:
            return
        sound = self.rank_sounds.get(self.settlement.rank)
        if sound is None:
            return
        self.rank_channel.set_volume(self.effective_sfx_volume("settlement"))
        self.rank_channel.play(sound)

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
            player_center = data.get("player_center_offset")
            gun_center = data.get("gun_center_offset")
            if isinstance(player_center, list) and len(player_center) == 2:
                self.player_center_offset.update(
                    max(-32.0, min(32.0, float(player_center[0]))),
                    max(-32.0, min(32.0, float(player_center[1]))),
                )
            if isinstance(gun_center, list) and len(gun_center) == 2:
                self.gun_center_offset.update(
                    max(-32.0, min(32.0, float(gun_center[0]))),
                    max(-32.0, min(32.0, float(gun_center[1]))),
                )
            crosshair = data.get("crosshair_preset")
            if isinstance(crosshair, str) and any(
                preset["key"] == crosshair for preset in CROSSHAIR_PRESETS
            ):
                self.crosshair_preset = crosshair
            self.shake_intensity = max(
                0.0, min(1.0, float(data.get("shake_intensity", self.shake_intensity)))
            )
            legacy_glow = data.get("glow_intensity")
            if legacy_glow is not None and "glow_opacity" not in data:
                self.glow_opacity = max(0.0, min(1.0, float(legacy_glow)))
            self.glow_brightness = max(
                0.0, min(1.0, float(data.get("glow_brightness", self.glow_brightness)))
            )
            self.glow_spread = max(
                0.0, min(1.0, float(data.get("glow_spread", self.glow_spread)))
            )
            self.glow_opacity = max(
                0.0, min(1.0, float(data.get("glow_opacity", self.glow_opacity)))
            )
            self.glow_feather = max(
                0.0, min(1.0, float(data.get("glow_feather", self.glow_feather)))
            )
        except (TypeError, ValueError):
            return

    def save_settings(self) -> None:
        data = {
            "bgm_volume": self.bgm_volume,
            "sfx_volume": self.sfx_volume,
            "effect_volumes": dict(self.effect_volumes),
            "mouse_sensitivity": self.mouse_sensitivity,
            "player_center_offset": list(self.player_center_offset),
            "gun_center_offset": list(self.gun_center_offset),
            "crosshair_preset": self.crosshair_preset,
            "shake_intensity": self.shake_intensity,
            "glow_brightness": self.glow_brightness,
            "glow_spread": self.glow_spread,
            "glow_opacity": self.glow_opacity,
            "glow_feather": self.glow_feather,
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
        if not self.audio_available or not self.kill_sounds or not self.kill_channels:
            return
        channel_count = len(self.kill_channels)
        selected_index = self.kill_channel_cursor
        for offset in range(channel_count):
            candidate_index = (self.kill_channel_cursor + offset) % channel_count
            if not self.kill_channels[candidate_index].get_busy():
                selected_index = candidate_index
                break
        selected = self.kill_channels[selected_index]
        self.kill_channel_cursor = (selected_index + 1) % channel_count

        volume = self.effective_sfx_volume("kill")
        for channel in self.kill_channels:
            if channel is not selected and channel.get_busy():
                channel.set_volume(volume * KILL_TAIL_DUCKING)
        selected.set_volume(volume)
        selected.play(
            self.audio_rng.choice(self.kill_sounds),
            fade_ms=KILL_SOUND_FADE_IN_MS,
        )

    def play_boss_kill_sound(self) -> None:
        if (
            not self.audio_available
            or not self.kill_sounds
            or self.boss_kill_channel is None
        ):
            return
        volume = min(1.0, self.effective_sfx_volume("kill") * BOSS_KILL_VOLUME_BOOST)
        self.boss_kill_channel.set_volume(volume)
        self.boss_kill_channel.play(
            self.audio_rng.choice(self.kill_sounds),
            fade_ms=KILL_SOUND_FADE_IN_MS,
        )

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
        self.challenge_checkpoint = None
        self.challenge_world_growth_bonus = 0
        self.challenge_shop_population_bonus = 0
        self.challenge_shop_card_credits = {}
        self.start_world()

    def starting_population_value(self, world: int | None = None) -> int:
        previous_world = self.world
        if world is not None:
            self.world = world
        try:
            value = round(
                self.apply_stat(
                    self.default_population,
                    "starting_population",
                    TARGET_PLAYER,
                )
            )
            value += sum(
                5 for owned in self.equipped_cards if owned.enhancement == "population"
            )
            return max(1, value)
        finally:
            self.world = previous_world

    def population_growth_between_worlds(self, from_world: int, to_world: int) -> int:
        return max(
            0,
            self.starting_population_value(to_world)
            - self.starting_population_value(from_world),
        )

    def start_world(
        self,
        carried_population: int | None = None,
        population_bonus: int = 0,
    ) -> None:
        self.mode = Mode.PLAYING
        self.player = pygame.Vector2(WIDTH / 2, HEIGHT - 90)
        self.player_radius = 22.5
        self.player_body_heading = 0.0
        self.population_basis = self.starting_population_value()
        self.population = (
            self.population_basis
            if carried_population is None
            else max(1, carried_population + population_bonus)
        )
        self.population_peak = self.population
        self.elapsed = 0.0
        self.enemy_timer = 1.0
        self.elite_timer = 6.0 if self.world == 9 else 18.0
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
        self.big_spawned = self.world in FINAL_CHALLENGE_WORLDS
        self.bullets: list[Bullet] = []
        self.enemy_bullets: list[EnemyBullet] = []
        self.enemies: list[Enemy] = []
        self.gates: list[Gate] = []
        self.bosses: list[Boss] = []
        self.temp_damage_bonus = 0.0
        self.temp_fire_rate_bonus = 0.0
        self.temp_buff_timer = 0.0
        if self.world in FINAL_CHALLENGE_WORLDS:
            boss_title = "终局统帅" if self.world == 9 else "吞门者"
            self.message = f"世界 {self.world}/{MAX_WORLD}：{boss_title}已登场，90秒内击杀"
        else:
            self.message = (
                f"世界 {self.world}/{MAX_WORLD}："
                "120秒内击杀90秒出现的大Boss"
            )
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
        self.shake_strength = 0.0
        self.shake_timer = 0.0
        self.shake_duration = 0.0
        self.kill_combo = 0
        self.kill_combo_timer = 0.0
        self.blood_stains = []
        self.death_particles = []
        self.settlement = None
        self.settlement_particles = []
        self.total_damage_dealt = 0.0
        self.world_boss_gold = 0
        self.world_interest = 0
        if self.world == 9:
            self.spawn_boss("big", "commander")
        elif self.world == 10:
            self.spawn_boss("big", "devourer")
        self.sync_mouse_mode()

    def save_challenge_checkpoint(self) -> None:
        fields = (
            "run_id",
            "balance_log_error",
            "world",
            "gold",
            "total_kills",
            "rapid_reload_kills",
            "equipped_cards",
            "overload_cards",
            "effect_runtime",
            "attribute_purchases",
            "default_population",
            "default_damage",
            "default_fire_rate",
            "shop_round",
            "population",
            "population_basis",
        )
        state = {name: copy.deepcopy(getattr(self, name)) for name in fields}
        self.challenge_checkpoint = ChallengeCheckpoint(state, self.rng.getstate())

    def start_final_challenge(self) -> None:
        if self.world != 8:
            return
        self.save_challenge_checkpoint()
        carried_population = self.population
        growth_bonus = self.population_growth_between_worlds(8, 9)
        self.world = 9
        self.start_world(carried_population, growth_bonus)

    def retry_final_challenge(self) -> bool:
        if self.challenge_checkpoint is None:
            return False
        for name, value in self.challenge_checkpoint.run_state.items():
            setattr(self, name, copy.deepcopy(value))
        self.rng.setstate(self.challenge_checkpoint.rng_state)
        self.challenge_world_growth_bonus = 0
        self.challenge_shop_population_bonus = 0
        self.challenge_shop_card_credits = {}
        carried_population = self.population
        growth_bonus = self.population_growth_between_worlds(8, 9)
        self.world = 9
        self.death_reason = ""
        self.start_world(carried_population, growth_bonus)
        return True

    def continue_from_shop(self) -> None:
        carried_population = self.population if self.world == 9 else None
        population_bonus = 0
        if self.world == 9:
            population_bonus = (
                self.challenge_world_growth_bonus
                + self.challenge_shop_population_bonus
            )
        self.world += 1
        self.start_world(carried_population, population_bonus)
        self.challenge_world_growth_bonus = 0
        self.challenge_shop_population_bonus = 0
        self.challenge_shop_card_credits = {}

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

    def crosshair_preset_name(self) -> str:
        for preset in CROSSHAIR_PRESETS:
            if preset["key"] == self.crosshair_preset:
                return preset["name"]
        return CROSSHAIR_PRESETS[0]["name"]

    def crosshair_palette(self) -> tuple[tuple[int, int, int], ...]:
        for preset in CROSSHAIR_PRESETS:
            if preset["key"] == self.crosshair_preset:
                return preset["palette"]
        return CURSOR_PALETTE

    def cycle_crosshair_preset(self, direction: int) -> None:
        keys = [preset["key"] for preset in CROSSHAIR_PRESETS]
        try:
            index = keys.index(self.crosshair_preset)
        except ValueError:
            index = 0
        self.crosshair_preset = keys[(index + direction) % len(keys)]

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

    def toggle_sprite_calibration(self) -> None:
        self.sprite_calibration_open = not self.sprite_calibration_open
        self.sprite_calibration_editing = None
        self.sprite_calibration_input = ""
        if self.sprite_calibration_open:
            self._disable_relative_mouse()
            pygame.mouse.set_visible(True)
        else:
            self.sync_mouse_mode()

    @staticmethod
    def sprite_calibration_specs() -> tuple[tuple[str, str, float, float, float], ...]:
        return (
            ("player_center_x", "机体中心 X", -32.0, 32.0, 1.0),
            ("player_center_y", "机体中心 Y", -32.0, 32.0, 1.0),
            ("gun_center_x", "枪管中心 X", -32.0, 32.0, 1.0),
            ("gun_center_y", "枪管中心 Y", -32.0, 32.0, 1.0),
        )

    def sprite_calibration_value(self, key: str) -> float:
        values = {
            "player_center_x": self.player_center_offset.x,
            "player_center_y": self.player_center_offset.y,
            "gun_center_x": self.gun_center_offset.x,
            "gun_center_y": self.gun_center_offset.y,
        }
        return values[key]

    def set_sprite_calibration_value(self, key: str, value: float) -> None:
        if key == "player_center_x":
            self.player_center_offset.x = value
        elif key == "player_center_y":
            self.player_center_offset.y = value
        elif key == "gun_center_x":
            self.gun_center_offset.x = value
        elif key == "gun_center_y":
            self.gun_center_offset.y = value

    @staticmethod
    def sprite_calibration_panel_rect() -> pygame.Rect:
        return pygame.Rect(18, 92, 420, 440)

    @staticmethod
    def sprite_calibration_value_rect(index: int) -> pygame.Rect:
        return pygame.Rect(202, 190 + index * 58, 116, 40)

    @staticmethod
    def sprite_calibration_button_rect(index: int, direction: int) -> pygame.Rect:
        return pygame.Rect(330 if direction < 0 else 378, 190 + index * 58, 40, 40)

    @staticmethod
    def sprite_calibration_reset_rect() -> pygame.Rect:
        return pygame.Rect(38, 468, 360, 42)

    def commit_sprite_calibration_edit(self) -> None:
        if self.sprite_calibration_editing is None:
            return
        key = self.sprite_calibration_editing
        _, _, minimum, maximum, _ = next(
            spec for spec in self.sprite_calibration_specs() if spec[0] == key
        )
        try:
            value = float(self.sprite_calibration_input.strip())
        except ValueError:
            value = self.sprite_calibration_value(key)
        self.set_sprite_calibration_value(key, max(minimum, min(maximum, value)))
        self.sprite_calibration_editing = None
        self.sprite_calibration_input = ""

    def handle_sprite_calibration_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_F2):
                self.toggle_sprite_calibration()
                return
            if self.sprite_calibration_editing is None:
                return
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.commit_sprite_calibration_edit()
            elif event.key == pygame.K_BACKSPACE:
                self.sprite_calibration_input = self.sprite_calibration_input[:-1]
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                if not self.sprite_calibration_input:
                    self.sprite_calibration_input = "-"
            else:
                char = self._digit_key_char(event.key)
                if char is not None and not (char == "." and "." in self.sprite_calibration_input):
                    self.sprite_calibration_input += char
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        specs = self.sprite_calibration_specs()
        value_rects = [self.sprite_calibration_value_rect(index) for index in range(len(specs))]
        if self.sprite_calibration_editing is not None and not any(
            rect.collidepoint(event.pos) for rect in value_rects
        ):
            self.commit_sprite_calibration_edit()
        for index, spec in enumerate(specs):
            key, _, minimum, maximum, step = spec
            if self.sprite_calibration_value_rect(index).collidepoint(event.pos):
                self.sprite_calibration_editing = key
                self.sprite_calibration_input = f"{self.sprite_calibration_value(key):g}"
                return
            for direction in (-1, 1):
                if self.sprite_calibration_button_rect(index, direction).collidepoint(event.pos):
                    value = self.sprite_calibration_value(key) + direction * step
                    self.set_sprite_calibration_value(key, max(minimum, min(maximum, value)))
                    return
        if self.sprite_calibration_reset_rect().collidepoint(event.pos):
            self.player_center_offset.update()
            self.gun_center_offset.update()

    def dev_field_specs(self) -> tuple[tuple[str, str, bool, float, float, float, str], ...]:
        return (
            ("gold", "金币", True, 0, 999_999_999, 100, "int"),
            ("population", "人口 / 血量", True, 1, 999_999_999, 100, "int"),
            ("default_population", "初始人口", True, 1, 999, 1, "int"),
            ("default_damage", "基础伤害", False, 0.0, 9_999.0, 1.0, "float"),
            ("default_fire_rate", "基础射速", False, 0.0, 9_999.0, 1.0, "float"),
            ("world", "世界", True, 1, MAX_WORLD, 1, "int"),
            (
                "elapsed",
                "关卡秒数",
                False,
                0.0,
                world_duration(self.world),
                5.0,
                "float",
            ),
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
        if self.world == 8:
            self.mode = Mode.CHALLENGE_CHOICE
            self.sync_mouse_mode()
        elif self.world >= MAX_WORLD:
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
            self.world = min(MAX_WORLD, self.world + 1)
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
            ("结束本世界 → 下一阶段", GREEN, 0, 0),
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

    def draw_sprite_calibration_panel(self) -> None:
        panel = self.sprite_calibration_panel_rect()
        self.draw_ui_panel(panel, fill=PANEL, rim=CYAN, radius=8, glass=True)
        self.draw_neon_line((panel.x + 14, panel.y + 1), (panel.right - 14, panel.y + 1), CYAN, 2, 10)
        self.blit_text("玩家挂点校准", (panel.x + 20, panel.y + 20), WHITE, self.font)
        self.blit_text("F2 / Esc 关闭 · 数值单位：像素", (panel.x + 20, panel.y + 54), MUTED, self.font_tiny)
        self.blit_text("枪管坐标跟随机体旋转", (panel.x + 20, panel.y + 78), YELLOW, self.font_tiny)

        for index, spec in enumerate(self.sprite_calibration_specs()):
            key, label, _, _, _ = spec
            value_rect = self.sprite_calibration_value_rect(index)
            self.blit_text(label, (panel.x + 20, value_rect.y + 10), WHITE, self.font_small)
            self.draw_ui_panel(value_rect, fill=PANEL_RAISED, rim=YELLOW if self.sprite_calibration_editing == key else GRID, radius=5)
            value = self.sprite_calibration_input if self.sprite_calibration_editing == key else f"{self.sprite_calibration_value(key):.0f}"
            rendered = self.font_numeric.render(value, True, WHITE)
            self.screen.blit(rendered, rendered.get_rect(center=value_rect.center))
            for direction, symbol in ((-1, "−"), (1, "+")):
                button = self.sprite_calibration_button_rect(index, direction)
                self.draw_ui_panel(button, fill=PANEL_RAISED, rim=CYAN, radius=5)
                glyph = self.font.render(symbol, True, CYAN)
                self.screen.blit(glyph, glyph.get_rect(center=button.center))

        reset = self.sprite_calibration_reset_rect()
        self.draw_ui_panel(reset, fill=(22, 31, 52), rim=PURPLE, radius=5)
        label = self.font_small.render("重置全部偏移", True, WHITE)
        self.screen.blit(label, label.get_rect(center=reset.center))

    def draw_sprite_calibration_guides(self) -> None:
        markers = (
            (self.player, YELLOW),
            (self.player_art_position(), CYAN),
            (self.gun_mount_position(), MAGENTA),
        )
        for center, color in markers:
            x, y = round(center.x), round(center.y)
            pygame.draw.line(self.screen, color, (x - 9, y), (x + 9, y), 1)
            pygame.draw.line(self.screen, color, (x, y - 9), (x, y + 9), 1)
            pygame.draw.circle(self.screen, color, (x, y), 3, 1)

    def update_cursor_effects(self, dt: float, position: pygame.Vector2) -> None:
        self.cursor_time += dt
        self.cursor_phase += dt
        if (
            not self.cursor_trail
            or position.distance_squared_to(self.cursor_trail[-1][1]) >= 4.0
        ):
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
        if speed >= 18.0 and self.cursor_spawn_timer <= 0:
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
        color = self.cursor_rng.choice(self.crosshair_palette())
        return CursorParticle(position.copy(), velocity, life, life, size, color)

    def _cursor_color(self, age_fraction: float) -> tuple[int, int, int]:
        palette = self.crosshair_palette()
        phase = (self.cursor_phase * 0.9 + age_fraction * 0.35) % 1.0
        segment = phase * (len(palette) - 1)
        index = int(segment)
        fraction = segment - index
        first = palette[index]
        second = palette[min(index + 1, len(palette) - 1)]
        return tuple(
            round(first[channel] * (1 - fraction) + second[channel] * fraction)
            for channel in range(3)
        )

    def draw_cursor_effects(self) -> None:
        position = self.current_mouse_position()
        glow_scale = 4
        glow = self.cursor_glow_small_surface
        glow.fill((0, 0, 0))
        if len(self.cursor_trail) >= 2:
            for index in range(len(self.cursor_trail) - 1):
                timestamp, point = self.cursor_trail[index]
                age = min(1.0, max(0.0, self.cursor_time - timestamp) / CURSOR_TRAIL_MAX_AGE)
                strength = (1.0 - age) ** 2
                color = self._cursor_color(age)
                px = round(point.x / glow_scale)
                py = round(point.y / glow_scale)
                radius = max(1, round((1.0 + (1.0 - age) * 4.5) / glow_scale))
                shade = tuple(round(channel * strength) for channel in color)
                outer_shade = tuple(round(channel * strength * 0.38) for channel in color)
                pygame.draw.circle(glow, outer_shade, (px, py), max(2, round(radius * 2.0)))
                pygame.draw.circle(glow, shade, (px, py), radius)
        for particle in self.cursor_particles:
            remaining = max(0.0, particle.life / particle.max_life)
            radius = max(1, round((particle.size * (0.35 + 0.65 * remaining)) / glow_scale))
            shade = tuple(round(channel * remaining) for channel in particle.color)
            head = (round(particle.position.x / glow_scale), round(particle.position.y / glow_scale))
            tail = (
                round((particle.position.x - particle.velocity.x * 0.06) / glow_scale),
                round((particle.position.y - particle.velocity.y * 0.06) / glow_scale),
            )
            pygame.draw.line(glow, shade, tail, head, max(1, radius))
            pygame.draw.circle(glow, shade, head, radius)
        pygame.transform.smoothscale(
            glow,
            self.cursor_glow_surface.get_size(),
            self.cursor_glow_surface,
        )
        self.screen.blit(self.cursor_glow_surface, (0, 0), special_flags=pygame.BLEND_ADD)
        self._draw_crosshair(position)

    def _draw_crosshair(self, position: pygame.Vector2) -> None:
        sprite = self._render_crosshair_sprite()
        self.screen.blit(
            sprite,
            sprite.get_rect(center=(round(position.x), round(position.y))),
        )

    def _render_crosshair_sprite(self, draw_scale: float = 1.0) -> pygame.Surface:
        size = CROSSHAIR_BOX * CROSSHAIR_SUPERSAMPLE
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        self._draw_crosshair_preset(
            surface,
            pygame.Vector2(size / 2, size / 2),
            self.crosshair_preset,
            self.cursor_phase,
            scale=CROSSHAIR_SUPERSAMPLE * draw_scale,
        )
        return pygame.transform.smoothscale(surface, (CROSSHAIR_BOX, CROSSHAIR_BOX))

    def _draw_crosshair_preset(
        self,
        surface: pygame.Surface,
        position: pygame.Vector2,
        preset_key: str,
        phase: float,
        scale: float = 1.0,
    ) -> None:
        x, y = round(position[0]), round(position[1])
        if preset_key == "osu":
            self._draw_osu_crosshair(surface, x, y, phase, scale)
        elif preset_key == "neon":
            self._draw_neon_crosshair(surface, x, y, phase, scale)
        elif preset_key == "void":
            self._draw_void_crosshair(surface, x, y, phase, scale)
        elif preset_key == "hex":
            self._draw_hex_crosshair(surface, x, y, phase, scale)
        else:
            self._draw_classic_crosshair(surface, x, y, phase, scale)

    def _draw_classic_crosshair(
        self, surface: pygame.Surface, x: int, y: int, phase: float, scale: float
    ) -> None:
        pygame.draw.circle(surface, WHITE, (x, y), max(1, round(8 * scale)), max(1, round(2 * scale)))
        pygame.draw.circle(surface, CYAN, (x, y), max(1, round(2 * scale)))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            start = (x + round(dx * 11 * scale), y + round(dy * 11 * scale))
            end = (x + round(dx * 18 * scale), y + round(dy * 18 * scale))
            pygame.draw.line(surface, CYAN, start, end, max(1, round(2 * scale)))
        spin = phase * 2.4
        rect = pygame.Rect(0, 0, max(1, round(34 * scale)), max(1, round(34 * scale)))
        rect.center = (x, y)
        pygame.draw.arc(surface, WHITE, rect, spin, spin + math.pi * 0.72, max(1, round(2 * scale)))
        pygame.draw.arc(surface, WHITE, rect, spin + math.pi, spin + math.pi * 1.72, max(1, round(2 * scale)))

    def _draw_osu_crosshair(
        self, surface: pygame.Surface, x: int, y: int, phase: float, scale: float
    ) -> None:
        palette = self.crosshair_palette()
        core = palette[0]
        accent = palette[1]
        spin = phase * 3.4
        counter = phase * 2.2
        pulse = 1.0 + 0.12 * math.sin(phase * 5.0)
        pygame.draw.circle(surface, core, (x, y), max(1, round(4 * scale * pulse)))
        pygame.draw.circle(surface, WHITE, (x, y), max(1, round(2 * scale)))
        outer = pygame.Rect(0, 0, max(1, round(28 * scale)), max(1, round(28 * scale)))
        outer.center = (x, y)
        for offset in (0.0, math.pi * 2 / 3, math.pi * 4 / 3):
            start_angle = spin + offset
            pygame.draw.arc(
                surface, accent, outer, start_angle, start_angle + math.pi * 0.8, max(1, round(2 * scale))
            )
        inner = pygame.Rect(0, 0, max(1, round(18 * scale)), max(1, round(18 * scale)))
        inner.center = (x, y)
        pygame.draw.arc(surface, core, inner, counter, counter + math.pi * 1.4, max(1, round(2 * scale)))
        for angle in (spin, spin + math.pi * 0.5, spin + math.pi, spin + math.pi * 1.5):
            start = (x + round(math.cos(angle) * 10 * scale), y + round(math.sin(angle) * 10 * scale))
            end = (x + round(math.cos(angle) * 14 * scale), y + round(math.sin(angle) * 14 * scale))
            pygame.draw.line(surface, accent, start, end, max(1, round(scale)))

    def _draw_neon_crosshair(
        self, surface: pygame.Surface, x: int, y: int, phase: float, scale: float
    ) -> None:
        cyan = (64, 215, 255)
        pink = (255, 96, 220)
        breathe = 0.5 + 0.5 * math.sin(phase * 3.8)
        reach = 14 + breathe * 15
        half = max(1, round(6 * scale))
        diamond = []
        spin = phase * 2.0
        for index in range(4):
            angle = spin + index * math.pi / 2
            diamond.append((x + round(math.cos(angle) * half), y + round(math.sin(angle) * half)))
        pygame.draw.polygon(surface, WHITE, diamond)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for start_off, end_off, width, color in (
                (10, 14, 3, cyan),
                (14, reach * 0.68, 2, pink),
                (reach * 0.68, reach, 1, WHITE),
            ):
                start = (x + round(dx * start_off * scale), y + round(dy * start_off * scale))
                end = (x + round(dx * end_off * scale), y + round(dy * end_off * scale))
                pygame.draw.line(surface, color, start, end, max(1, round(width * scale)))
            tip = (x + round(dx * reach * scale), y + round(dy * reach * scale))
            pygame.draw.circle(surface, cyan, tip, max(1, round((2.5 + breathe) * scale)))

    def _draw_void_crosshair(
        self, surface: pygame.Surface, x: int, y: int, phase: float, scale: float
    ) -> None:
        pulse = 1.0 + 0.08 * math.sin(phase * 3.2)
        layers = (
            (phase * 1.6, 18 * scale * pulse, PURPLE),
            (-phase * 1.15, 12 * scale, BLUE),
            (phase * 0.7, 6 * scale, WHITE),
        )
        for rotation, radius, color in layers:
            points = []
            for index in range(3):
                angle = rotation + index * math.tau / 3
                points.append((x + round(math.cos(angle) * radius), y + round(math.sin(angle) * radius)))
            pygame.draw.polygon(surface, color, points, max(1, round(2 * scale)))
        pygame.draw.circle(surface, WHITE, (x, y), max(1, round(2 * scale)))

    def _draw_hex_crosshair(
        self, surface: pygame.Surface, x: int, y: int, phase: float, scale: float
    ) -> None:
        pulse = 1.0 + 0.10 * math.sin(phase * 4.2)
        outer_points = []
        for index in range(6):
            angle = math.pi / 6 + index * math.tau / 6
            radius = 16 * scale * pulse
            outer_points.append((x + round(math.cos(angle) * radius), y + round(math.sin(angle) * radius)))
        pygame.draw.polygon(surface, ORANGE, outer_points, max(1, round(2 * scale)))
        inner_points = []
        rotation = phase * 1.4
        for index in range(6):
            angle = rotation + math.pi / 6 + index * math.tau / 6
            radius = 10 * scale
            inner_points.append((x + round(math.cos(angle) * radius), y + round(math.sin(angle) * radius)))
        pygame.draw.polygon(surface, YELLOW, inner_points, max(1, round(2 * scale)))
        pygame.draw.circle(surface, YELLOW, (x, y), max(1, round(3 * scale)))
        for point in outer_points:
            pygame.draw.circle(surface, WHITE, point, max(1, round(scale)))

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

    def spawn_enemy(self, elite: bool = False, elite_kind: str | None = None) -> None:
        target = TARGET_ELITE if elite else TARGET_NORMAL
        if elite:
            if elite_kind is not None and elite_kind not in ELITE_KINDS:
                raise ValueError(f"unknown elite kind: {elite_kind}")
            elite_kind = elite_kind or self.rng.choice(ELITE_KINDS)
            base_speed = {"guardian": 72.0, "archon": 66.0, "hunter": 88.0}[elite_kind]
            speed, radius = base_speed * (1 + 0.04 * (self.world - 1)), 23
        else:
            speed, radius = self.rng.uniform(60, 74) * (1 + 0.04 * (self.world - 1)), 16
        hp = self.current_dps() if elite else world_target_health(self.world, "normal")
        speed = max(0.0, self.apply_stat(speed, "move_speed", target))
        hp = max(1.0, self.apply_stat(hp, "health", target))
        shields = (
            [EliteShield(angle, hp * 0.18, hp * 0.18) for angle in (0.0, 120.0, 240.0)]
            if elite_kind == "guardian"
            else []
        )
        state = "cooldown" if elite_kind == "hunter" else "approach"
        state_timer = self.rng.uniform(0.8, 1.2) if elite_kind == "hunter" else 0.0
        self.enemies.append(
            Enemy(
                pygame.Vector2(self.rng.randint(35, WIDTH - 35), -30),
                hp,
                hp,
                speed,
                radius,
                elite=elite,
                elite_kind=elite_kind,
                animation_time=self.rng.random() / NORMAL_ENEMY_ANIMATION_FPS,
                shields=shields,
                elite_state=state,
                state_timer=state_timer,
            )
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

    def spawn_boss(self, kind: str, variant: str = "standard") -> None:
        data = {
            "small": (54.0, 4, 34),
            "medium": (46.0, 6, 42),
            "big": (90.0 + self.world * 5.0, 8, 54),
        }
        speed, reward, radius = data[kind]
        if variant == "commander":
            reward, radius = 30, 64
        elif variant == "devourer":
            reward, radius = 50, 72
        speed = max(0.0, self.apply_stat(speed, "move_speed", TARGET_BOSS, {"boss_kind": kind}))
        hp = max(1.0, self.apply_stat(world_target_health(self.world, kind), "health", TARGET_BOSS, {"boss_kind": kind}))
        windup = max(0.0, self.apply_stat(2.0, "boss_windup", TARGET_BOSS))
        self.bosses.append(
            Boss(
                pygame.Vector2(
                    self.rng.randint(radius + 10, WIDTH - radius - 10),
                    radius + 10 if variant != "standard" else -radius,
                ),
                kind,
                hp,
                hp,
                speed,
                reward,
                radius,
                175.0,
                windup,
                windup_move_factor=boss_windup_move_factor(self.world),
                variant=variant,
                roam_direction=(
                    normalized(
                        pygame.Vector2(
                            self.rng.choice((-1.0, 1.0)),
                            self.rng.uniform(0.25, 0.55),
                        )
                    )
                    if variant != "standard"
                    else pygame.Vector2(1.0, 0.35).normalize()
                ),
            )
        )
        self.message = f"{self.boss_name(kind, variant)}出现！"
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

        if self.sprite_calibration_open:
            self.handle_sprite_calibration_event(event)
            return

        if self.settlement is not None:
            if self.settlement.phase == "button":
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_KP_ENTER,
                    pygame.K_SPACE,
                ):
                    self.finish_settlement()
                    return
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.settlement_button_rect().collidepoint(event.pos):
                        self.finish_settlement()
                        return
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == Mode.CHALLENGE_CHOICE:
                if self.challenge_choice_rect("restart").collidepoint(event.pos):
                    self.reset_run()
                elif self.challenge_choice_rect("continue").collidepoint(event.pos):
                    self.start_final_challenge()
                return
            if (
                self.mode == Mode.GAME_OVER
                and self.challenge_checkpoint is not None
                and self.world >= 9
            ):
                if self.challenge_failure_rect("retry").collidepoint(event.pos):
                    self.retry_final_challenge()
                elif self.challenge_failure_rect("new").collidepoint(event.pos):
                    self.reset_run()
                return
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
                if self.settings_crosshair_button_rect(-1).collidepoint(event.pos):
                    self.cycle_crosshair_preset(-1)
                    return
                if self.settings_crosshair_button_rect(1).collidepoint(event.pos):
                    self.cycle_crosshair_preset(1)
                    return
                for index, (kind, _) in enumerate(self.settings_volume_rows()):
                    for direction in (-1, 1):
                        if self.settings_volume_button_rect(index, direction).collidepoint(event.pos):
                            self.adjust_volume(kind, direction)
                            self.preview_volume(kind)
                            return
                for index, (kind, _) in enumerate(self.settings_visual_rows()):
                    for direction in (-1, 1):
                        if self.settings_visual_button_rect(index, direction).collidepoint(event.pos):
                            self.adjust_visual_effect(kind, direction)
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
        if event.key == pygame.K_F2:
            self.toggle_sprite_calibration()
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
        elif self.mode == Mode.CHALLENGE_CHOICE:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.start_final_challenge()
            elif event.key == pygame.K_r:
                self.reset_run()
        elif self.mode == Mode.GAME_OVER and event.key == pygame.K_r:
            if not (self.world >= 9 and self.retry_final_challenge()):
                self.reset_run()
        elif self.mode == Mode.GAME_OVER and event.key == pygame.K_n:
            self.reset_run()
        elif self.mode == Mode.VICTORY and event.key == pygame.K_r:
            self.reset_run()
        elif self.mode == Mode.SHOP and event.key == pygame.K_RETURN:
            self.continue_from_shop()

    def update(self, dt: float) -> None:
        if self.dev_panel_open:
            return
        self.update_audio(dt)
        self.update_visual_effects(dt)
        if self.mode != Mode.PLAYING:
            self.cursor_phase += dt
            return
        if self.settlement is not None:
            self.update_settlement(dt)
            return
        self._update_world(dt)

    def _update_world(self, dt: float) -> None:
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
        elif self.elapsed >= world_duration(self.world):
            self.end_game(
                f"{round(world_duration(self.world))}秒截止，"
                "大Boss发动强制秒杀"
            )

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
        firing = pygame.mouse.get_pressed()[0] and not self.sprite_calibration_open
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
            elite_interval = self.apply_stat(
                base_elite_interval,
                "elite_spawn_interval",
                TARGET_PLAYER,
            )
            commander = next(
                (boss for boss in self.bosses if boss.variant == "commander"),
                None,
            )
            if commander is not None and commander.phase >= 2:
                elite_interval *= 0.5
            self.elite_timer = max(3.0, elite_interval)
        if self.gate_timer <= 0 and not any(g.kind == "number" for g in self.gates):
            self.spawn_number_gate()
            self.gate_timer = self.rng.uniform(8.0, 11.0)
        if self.special_spawned < 3 and self.elapsed >= self.special_times[self.special_spawned]:
            self.spawn_special_gate()
        if (
            self.world < 9
            and not self.small_spawned
            and self.elapsed >= self.small_boss_time
        ):
            self.small_spawned = True
            self.spawn_boss("small")
        if self.world < 9 and not self.medium_spawned and self.elapsed >= 60:
            self.medium_spawned = True
            self.spawn_boss("medium")
        if not self.big_spawned and self.elapsed >= world_boss_spawn_time(self.world):
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

    @staticmethod
    def colliding_guardian_shield(enemy: Enemy, bullet: Bullet) -> EliteShield | None:
        if enemy.elite_kind != "guardian":
            return None
        for shield in enemy.shields:
            if shield.hp <= 0 or id(shield) in bullet.hit_ids:
                continue
            if bullet.position.distance_to(shield.world_position(enemy.position)) <= shield.radius + bullet.radius:
                return shield
        return None

    def elite_mechanism_damage_multiplier(self, enemy: Enemy) -> float:
        if enemy.elite_kind == "archon":
            living_ids = {id(candidate) for candidate in self.enemies if candidate.hp > 0}
            link_count = sum(target_id in living_ids for target_id in enemy.linked_target_ids)
            return max(0.70, 1.0 - 0.10 * link_count)
        if enemy.elite_kind == "hunter" and enemy.elite_state == "overheat":
            return 1.50
        if enemy.elite_kind == "guardian" and enemy.vulnerable_timer > 0:
            return 1.35
        return 1.0

    def damage_guardian_shield(self, bullet: Bullet, enemy: Enemy, shield: EliteShield) -> bool:
        damage = bullet.damage * self.apply_stat(1.0, "damage_taken", TARGET_ELITE)
        shield.hp -= damage
        self.total_damage_dealt += damage
        self.play_effect_sound(self.enemy_hit_sound, "enemy_hit")
        self.apply_on_hit_effects(TARGET_ELITE, shield.world_position(enemy.position), damage, shield)
        self.dispatch_effect_event("on_hit", TARGET_ELITE)
        if shield.hp <= 0 and not any(module.hp > 0 for module in enemy.shields):
            enemy.vulnerable_timer = max(enemy.vulnerable_timer, 1.5)
        return self.apply_hit(bullet, shield)

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
                    if boss.variant == "commander" and any(
                        enemy.elite for enemy in self.enemies
                    ):
                        damage *= 0.40
                    boss.hp -= damage
                    self.total_damage_dealt += damage
                    self.play_effect_sound(self.enemy_hit_sound, "enemy_hit")
                    self.apply_on_hit_effects(TARGET_BOSS, boss.position, damage, boss)
                    self.dispatch_effect_event("on_hit", TARGET_BOSS)
                    remove = self.apply_hit(bullet, boss)
                    break
            if not remove:
                for enemy in self.enemies:
                    if id(enemy) in bullet.hit_ids:
                        continue
                    shield = self.colliding_guardian_shield(enemy, bullet)
                    if shield is not None:
                        remove = self.damage_guardian_shield(bullet, enemy, shield)
                        break
                    if bullet.position.distance_to(enemy.position) <= enemy.radius + bullet.radius:
                        target = TARGET_ELITE if enemy.elite else TARGET_NORMAL
                        damage = bullet.damage * self.apply_stat(1.0, "damage_taken", target)
                        if enemy.elite:
                            damage *= self.elite_mechanism_damage_multiplier(enemy)
                        enemy.hp -= damage
                        self.total_damage_dealt += damage
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
                    self.total_damage_dealt += gate_damage
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
                    applied_damage = splash_damage
                    if enemy.elite:
                        applied_damage *= self.elite_mechanism_damage_multiplier(enemy)
                    enemy.hp -= applied_damage
                    self.total_damage_dealt += applied_damage

    def splash(self, center: pygame.Vector2, damage: float, source: object, radius: float = 95.0) -> None:
        for enemy in self.enemies:
            if enemy is not source and enemy.position.distance_to(center) <= radius:
                applied_damage = damage
                if enemy.elite:
                    applied_damage *= self.elite_mechanism_damage_multiplier(enemy)
                enemy.hp -= applied_damage
                self.total_damage_dealt += applied_damage

    def register_kill(
        self,
        elite: bool = False,
        position: pygame.Vector2 | None = None,
        radius: int = 16,
    ) -> None:
        self.total_kills += 1
        self.rapid_reload_kills += 1
        self.play_kill_sound()
        if position is not None:
            self.spawn_death_effects(position, radius, 1.75 if elite else 1.0, danger=elite)
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

    def refresh_archon_links(self) -> set[int]:
        linked: set[int] = set()
        normal_enemies = [enemy for enemy in self.enemies if not enemy.elite and enemy.hp > 0]
        for archon in self.enemies:
            if archon.hp <= 0 or archon.elite_kind != "archon":
                continue
            nearby = sorted(
                (
                    enemy
                    for enemy in normal_enemies
                    if enemy.position.distance_to(archon.position) <= 190.0
                ),
                key=lambda enemy: enemy.position.distance_squared_to(archon.position),
            )[:3]
            archon.linked_target_ids = {id(enemy) for enemy in nearby}
            linked.update(archon.linked_target_ids)
        return linked

    def update_hunter(self, enemy: Enemy, dt: float) -> None:
        if enemy.disabled_timer > 0:
            enemy.disabled_timer = max(0.0, enemy.disabled_timer - dt)
            enemy.animation_time += dt
            return
        enemy.state_timer = max(0.0, enemy.state_timer - dt)
        low_health = enemy.hp <= enemy.max_hp * 0.35
        if enemy.elite_state == "cooldown":
            enemy.update(dt, self.player, 0.72)
            if enemy.position.y > 70 and enemy.state_timer <= 0:
                enemy.elite_state = "lock"
                enemy.state_timer = 0.52 if low_health else 0.78
                enemy.charge_direction = normalized(self.player - enemy.position)
        elif enemy.elite_state == "lock":
            enemy.animation_time += dt
            if enemy.charge_direction.length_squared():
                enemy.heading_degrees = math.degrees(
                    math.atan2(-enemy.charge_direction.x, -enemy.charge_direction.y)
                )
            if enemy.state_timer <= 0:
                enemy.elite_state = "charge"
                enemy.state_timer = 0.48
        elif enemy.elite_state == "charge":
            enemy.animation_time += dt
            enemy.position += enemy.charge_direction * (390.0 + self.world * 12.0) * dt
            if enemy.state_timer <= 0:
                enemy.elite_state = "overheat"
                enemy.state_timer = 0.90
        else:
            enemy.animation_time += dt
            if enemy.state_timer <= 0:
                enemy.elite_state = "cooldown"
                enemy.state_timer = 0.70 if low_health else 1.45

    def handle_elite_death(self, enemy: Enemy) -> None:
        if enemy.elite_kind == "archon":
            for candidate in self.enemies:
                if not candidate.elite and candidate.hp > 0 and candidate.position.distance_to(enemy.position) <= 190.0:
                    candidate.disabled_timer = max(candidate.disabled_timer, 1.25)
        elif enemy.elite_kind == "hunter":
            for candidate in self.enemies:
                if not candidate.elite and candidate.hp > 0 and candidate.position.distance_to(enemy.position) <= 120.0:
                    candidate.hp = 0

    def update_enemies(self, dt: float) -> None:
        linked_enemy_ids = self.refresh_archon_links()
        for enemy in self.enemies[:]:
            if enemy.hp <= 0:
                self.enemies.remove(enemy)
                if enemy.elite:
                    self.handle_elite_death(enemy)
                self.register_kill(enemy.elite, enemy.position, enemy.radius)
                if enemy.elite:
                    self.population += round(self.apply_stat(4.0, "elite_kill_population", TARGET_PLAYER))
                continue
            enemy.vulnerable_timer = max(0.0, enemy.vulnerable_timer - dt)
            if enemy.elite_kind == "guardian":
                for shield in enemy.shields:
                    shield.angle = (shield.angle + 76.0 * dt) % 360.0
            if enemy.elite_kind == "hunter":
                self.update_hunter(enemy, dt)
            else:
                speed_multiplier = 1.18 if id(enemy) in linked_enemy_ids else 1.0
                enemy.update(dt, self.player, speed_multiplier)
            if enemy.elite_kind in {"guardian", "archon"} and enemy.position.y > 50:
                enemy.shoot_timer -= dt
                if enemy.shoot_timer <= 0:
                    direction = normalized(self.player - enemy.position)
                    speed = 190.0 + self.world * 5.0
                    self.enemy_bullets.append(
                        EnemyBullet(enemy.position.copy(), direction * speed, population_loss_ratio=0.03)
                    )
                    interval = (2.8, 3.6) if enemy.elite_kind == "guardian" else (3.4, 4.3)
                    enemy.shoot_timer = self.rng.uniform(*interval)
            if enemy.position.distance_to(self.player) <= enemy.radius + self.player_radius:
                loss_ratio = 0.12 if enemy.elite else 0.02
                target = TARGET_ELITE if enemy.elite else TARGET_NORMAL
                contact_chance = self.contact_avoid_chance(target)
                if contact_chance and self.rng.random() < contact_chance:
                    loss = 0
                else:
                    loss = self.lose_population_ratio(loss_ratio)
                self.enemies.remove(enemy)
                enemy_name = ELITE_NAMES.get(enemy.elite_kind, "精英") if enemy.elite else "怪物"
                self.message = f"{enemy_name}突破：人口 -{loss}（{loss_ratio:.0%}）"
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
                devourer = next(
                    (
                        boss
                        for boss in self.bosses
                        if boss.variant == "devourer" and boss.hp > 0
                    ),
                    None,
                )
                if devourer is not None:
                    before = devourer.hp
                    devourer.hp = min(
                        devourer.max_hp,
                        devourer.hp + devourer.max_hp * 0.03,
                    )
                    devourer.rage_stacks = min(5, devourer.rage_stacks + 1)
                    healed = max(0, round(devourer.hp - before))
                    self.message = (
                        f"吞门者吞噬门：回复 {format_number(healed)}，"
                        f"狂暴 {devourer.rage_stacks}/5"
                    )
                    self.message_timer = 2.5
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
            if boss.phase == 1 and boss.hp <= boss.max_hp * 0.50:
                boss.phase = 2
                if boss.variant == "commander":
                    self.spawn_enemy(True)
                    self.elite_timer = min(self.elite_timer, 3.0)
                    self.message = "终局统帅进入第二阶段：精英增援加速"
                elif boss.variant == "devourer":
                    self.message = "吞门者进入第二阶段：环形弹幕启动"
                if boss.variant != "standard":
                    self.message_timer = 3.0
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
                self.message = f"{self.boss_name(boss.kind, boss.variant)}逃走了"
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
        if (
            boss.variant == "devourer"
            and boss.phase >= 2
            and boss.pattern_index % 2 == 1
        ):
            for index in range(16):
                angle = index * (360.0 / 16) + boss.pattern_index * 11.25
                self.enemy_bullets.append(
                    EnemyBullet(
                        boss.position.copy(),
                        pygame.Vector2(0, -speed).rotate(angle),
                        population_loss_ratio=0.03,
                        source="吞门者环形弹幕",
                    )
                )
            boss.pattern_index += 1
            interval = self.boss_shot_interval(boss.kind)
            interval *= 0.92 ** boss.rage_stacks
            boss.shoot_timer = interval * self.rng.uniform(0.90, 1.10)
            return
        direction = normalized(self.player - boss.position)
        center = (bullet_count - 1) / 2
        for index in range(bullet_count):
            angle = (index - center) * angle_step
            self.enemy_bullets.append(
                EnemyBullet(
                    boss.position.copy(),
                    direction.rotate(angle) * speed,
                    population_loss_ratio=loss_ratio,
                    source=f"{self.boss_name(boss.kind, boss.variant)}弹幕",
                )
            )
        interval = self.boss_shot_interval(boss.kind)
        if boss.variant == "devourer":
            boss.pattern_index += 1
            interval *= 0.92 ** boss.rage_stacks
        boss.shoot_timer = interval * self.rng.uniform(0.90, 1.10)

    def kill_boss(self, boss: Boss) -> None:
        if boss.kind == "big":
            self.log_world_completion()
        self.play_boss_kill_sound()
        impact = {"small": 2.3, "medium": 3.0, "big": 4.0}[boss.kind]
        self.spawn_death_effects(boss.position, boss.radius, impact)
        gold_before = self.gold
        base_reward = boss_gold_reward(boss.reward, self.gold)
        self.gold += round(self.apply_stat(base_reward, "boss_gold_reward", TARGET_PLAYER))
        self.dispatch_effect_event("on_boss_kill", TARGET_BOSS)
        reward = self.gold - gold_before
        self.world_boss_gold += reward
        self.bosses.remove(boss)
        self.message = f"击杀{self.boss_name(boss.kind, boss.variant)}：金币 +{reward}"
        self.message_timer = 3.0
        if boss.kind == "big":
            self.world_interest = self.dispatch_effect_event("on_world_complete")["gold"]
            if self.world_interest:
                self.message += f"，利息 +{self.world_interest}"
            self.begin_settlement()

    @staticmethod
    def boss_name(kind: str, variant: str = "standard") -> str:
        if variant == "commander":
            return "终局统帅"
        if variant == "devourer":
            return "吞门者"
        return {"small": "小Boss", "medium": "中Boss", "big": "大Boss"}[kind]

    def enter_shop(self) -> None:
        self.mode = Mode.SHOP
        self.shop_round += 1
        if self.world == 9:
            self.challenge_world_growth_bonus = self.population_growth_between_worlds(
                9, 10
            )
            self.challenge_shop_population_bonus = 0
            self.challenge_shop_card_credits = {}
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
        before_population = (
            self.starting_population_value(10) if self.world == 9 else 0
        )
        gained = OwnedCard(
            card.key,
            "overload",
            self.world,
            acquired_shop_round=self.shop_round,
        )
        self.overload_cards.append(gained)
        if self.world == 9:
            credit = max(
                0,
                self.starting_population_value(10) - before_population,
            )
            if credit:
                self.challenge_shop_card_credits[gained.instance_id] = credit
                self.challenge_shop_population_bonus += credit
        self.dispatch_effect_event("on_card_purchase", TARGET_PLAYER)
        index = next(index for index, candidate in enumerate(self.shop_offers) if candidate is offer)
        self.shop_offers.pop(index)
        self.fill_shop()
        self.shop_message(f"交换成功：获得过载牌 {card.name}")
        return True

    def remove_owned_card(self, owned: OwnedCard, collection: list[OwnedCard]) -> None:
        is_new_challenge_card = owned.instance_id in self.challenge_shop_card_credits
        growth_before = (
            self.population_growth_between_worlds(9, 10)
            if self.world == 9 and not is_new_challenge_card
            else 0
        )
        credit = self.challenge_shop_card_credits.pop(owned.instance_id, 0)
        self.challenge_shop_population_bonus = max(
            0,
            self.challenge_shop_population_bonus - credit,
        )
        collection.remove(owned)
        if self.world == 9 and not is_new_challenge_card:
            growth_after = self.population_growth_between_worlds(9, 10)
            self.challenge_world_growth_bonus = max(
                0,
                self.challenge_world_growth_bonus + growth_after - growth_before,
            )
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
                    before_population = (
                        self.starting_population_value(10)
                        if self.world == 9
                        else 0
                    )
                    owned = OwnedCard(
                        card.key,
                        offer.enhancement,
                        self.world,
                        wholesale_purchase,
                        self.wholesale_sale_price(card.rarity)
                        if wholesale_purchase
                        else None,
                        acquired_shop_round=self.shop_round,
                    )
                    self.equipped_cards.append(owned)
                    if self.world == 9:
                        credit = max(
                            0,
                            self.starting_population_value(10) - before_population,
                        )
                        if credit:
                            self.challenge_shop_card_credits[owned.instance_id] = credit
                            self.challenge_shop_population_bonus += credit
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
                        if self.world == 9:
                            self.challenge_shop_population_bonus += 2
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
            self.continue_from_shop()

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
        if self.settlement is not None:
            return
        self.mode = Mode.GAME_OVER
        self.death_reason = reason
        self.sync_mouse_mode()

    def abandon_run_to_main_menu(self) -> None:
        self.mode = Mode.MAIN_MENU
        self.sync_mouse_mode()

    def spawn_death_effects(
        self,
        position: pygame.Vector2,
        radius: int,
        impact: float,
        danger: bool | None = None,
    ) -> None:
        self.kill_combo = self.kill_combo + 1 if self.kill_combo_timer > 0 else 1
        self.kill_combo_timer = 0.28
        combo_scale = min(2.35, 1.0 + (self.kill_combo - 1) * 0.22)
        strength = min(SHAKE_STRENGTH_CAP, 2.3 * impact * combo_scale)
        self.shake_strength = min(
            SHAKE_STRENGTH_CAP,
            max(strength, self.shake_strength + strength * 0.32),
        )
        duration = min(0.30, 0.10 + impact * 0.035 + min(0.08, self.kill_combo * 0.012))
        self.shake_timer = max(self.shake_timer, duration)
        self.shake_duration = max(self.shake_duration, self.shake_timer)

        point_count = 12 + min(8, radius // 8)
        stain_scale = radius * self.visual_rng.uniform(1.15, 1.55)
        points = []
        for index in range(point_count):
            angle = math.tau * index / point_count
            distance = stain_scale * self.visual_rng.uniform(0.58, 1.12)
            points.append(pygame.Vector2(math.cos(angle), math.sin(angle)) * distance)
        droplets = tuple(
            (
                pygame.Vector2(1, 0).rotate(self.visual_rng.uniform(0, 360))
                * self.visual_rng.uniform(stain_scale * 0.75, stain_scale * 1.75),
                self.visual_rng.uniform(max(1.5, radius * 0.08), max(2.5, radius * 0.22)),
            )
            for _ in range(3 + min(6, radius // 9))
        )
        stain_life = self.visual_rng.uniform(5.0, 7.0)
        is_danger = impact > 1.1 if danger is None else danger
        effect_color = RED
        source_sprite = self.load_blood_stain_sprites()[
            self.visual_rng.randrange(BLOOD_STAIN_VARIANT_COUNT * BLOOD_STAIN_ROTATION_COUNT)
        ]
        blood_sprite = source_sprite.copy()
        size_scale = self.visual_rng.uniform(0.55, 0.90) * max(1.0, radius / 16.0)
        blood_sprite = pygame.transform.scale(
            blood_sprite,
            (max(16, round(128 * size_scale)), max(16, round(128 * size_scale))),
        )
        self.blood_stains.append(
            BloodStain(
                position.copy(),
                tuple(points),
                droplets,
                stain_life,
                stain_life,
                effect_color,
                blood_sprite,
            )
        )
        if len(self.blood_stains) > BLOOD_STAIN_CAP:
            del self.blood_stains[:-BLOOD_STAIN_CAP]

        particle_count = min(38, 8 + round(radius * 0.30 + impact * 3))
        for _ in range(particle_count):
            angle = self.visual_rng.uniform(0, math.tau)
            speed = self.visual_rng.uniform(85.0, 185.0) * min(1.45, 0.85 + impact * 0.15)
            life = self.visual_rng.uniform(0.18, 0.42)
            self.death_particles.append(
                DeathParticle(
                    position.copy(),
                    pygame.Vector2(math.cos(angle), math.sin(angle)) * speed,
                    life,
                    life,
                    self.visual_rng.uniform(1.2, 3.2),
                    (255, 132, 148),
                )
            )
        if len(self.death_particles) > DEATH_PARTICLE_CAP:
            del self.death_particles[:-DEATH_PARTICLE_CAP]

    def update_visual_effects(self, dt: float) -> None:
        self.kill_combo_timer = max(0.0, self.kill_combo_timer - dt)
        if self.kill_combo_timer <= 0:
            self.kill_combo = 0
        self.shake_timer = max(0.0, self.shake_timer - dt)
        if self.shake_timer <= 0:
            self.shake_strength = 0.0
            self.shake_duration = 0.0

        for stain in self.blood_stains:
            stain.life -= dt
        self.blood_stains = [stain for stain in self.blood_stains if stain.life > 0]

        drag = max(0.0, 1.0 - dt * 5.5)
        for particle in self.death_particles:
            particle.position += particle.velocity * dt
            particle.velocity *= drag
            particle.life -= dt
        self.death_particles = [particle for particle in self.death_particles if particle.life > 0]

    def begin_settlement(self) -> None:
        dps = self.current_dps()
        score = self.settlement_score(
            self.elapsed,
            dps,
            self.population,
            self.population_peak,
            self.world,
        )
        rank = self.rank_for_score(score)[0]
        gold_total = self.world_boss_gold + self.world_interest
        rows = [
            SettlementRow(
                "gold",
                "Boss 赏金",
                f"+{gold_total}",
                f"击杀赏金 {self.world_boss_gold} + 利息 {self.world_interest}"
                if self.world_interest
                else f"击杀赏金 {self.world_boss_gold}",
                float(gold_total),
                YELLOW,
            ),
            SettlementRow(
                "population",
                "结束时的人口",
                f"{self.population}",
                "守住的人口规模",
                float(self.population),
                CYAN,
            ),
            SettlementRow(
                "dps",
                "DPS",
                format_number(round(dps)),
                "结算时的理论秒伤",
                float(dps),
                PURPLE,
            ),
            SettlementRow(
                "damage",
                "总共造成的伤害",
                format_number(round(self.total_damage_dealt)),
                "本世界累计输出",
                float(self.total_damage_dealt),
                WHITE,
            ),
        ]
        self.settlement = SettlementState(
            "slowmo",
            0.0,
            0,
            rows,
            score,
            rank,
            -HEIGHT,
            999.0,
        )

    @staticmethod
    def settlement_score(
        clear_time: float,
        dps: float,
        end_population: int,
        peak_population: int,
        world: int,
    ) -> int:
        boss_spawn_time = world_boss_spawn_time(world)
        kill_window = max(1.0, world_duration(world) - boss_spawn_time)
        time_bonus = 40.0 * max(
            0.0,
            min(
                1.0,
                1.0 - max(0.0, clear_time - boss_spawn_time) / kill_window,
            ),
        )
        retention = max(0.0, min(1.0, end_population / max(1, peak_population)))
        population_score = 30.0 * retention
        firepower_score = 30.0 * min(1.0, dps / max(1, world_dps_threshold(world)) / 2.0)
        return round(time_bonus + population_score + firepower_score)

    @staticmethod
    def rank_for_score(score: int) -> tuple[str, tuple[int, int, int]]:
        for rank, threshold, color in SETTLEMENT_RANK_THRESHOLDS:
            if score >= threshold:
                return rank, color
        return "C", MUTED

    def settlement_rank_color(self) -> tuple[int, int, int]:
        return self.rank_for_score(self.settlement.score)[1] if self.settlement else MUTED

    def settlement_rank_sprite(self) -> pygame.Surface:
        assert self.settlement is not None
        color = self.settlement_rank_color()
        key = (self.settlement.rank, color)
        cached = self.settlement_rank_cache.get(key)
        if cached is not None:
            return cached

        text = self.font_huge.render(self.settlement.rank, True, color)
        padding = 38
        size = (text.get_width() + padding * 2, text.get_height() + padding * 2)
        source = pygame.Surface(size, pygame.SRCALPHA)
        source.blit(text, text.get_rect(center=(size[0] // 2, size[1] // 2)))
        wide_glow = pygame.transform.gaussian_blur(source, 13)
        tight_glow = pygame.transform.gaussian_blur(source, 5)
        wide_glow.set_alpha(155)
        tight_glow.set_alpha(215)
        sprite = pygame.Surface(size, pygame.SRCALPHA)
        sprite.blit(wide_glow, (0, 0))
        sprite.blit(tight_glow, (0, 0))
        sprite.blit(text, text.get_rect(center=(size[0] // 2, size[1] // 2)))
        self.settlement_rank_cache[key] = sprite
        return sprite

    def settlement_shown_rows(self) -> int:
        if self.settlement is None or self.settlement.phase in ("slowmo", "panel"):
            return 0
        if self.settlement.phase == "rows":
            return self.settlement.row_index
        return len(self.settlement.rows)

    @staticmethod
    def settlement_panel_rect() -> pygame.Rect:
        return pygame.Rect(140, SETTLEMENT_PANEL_Y, WIDTH - 280, HEIGHT - 180)

    @staticmethod
    def settlement_row_position(index: int) -> tuple[int, int]:
        return (188, SETTLEMENT_PANEL_Y + 100 + index * 64)

    @staticmethod
    def settlement_score_center() -> tuple[int, int]:
        return (WIDTH // 2, SETTLEMENT_PANEL_Y + 360)

    def settlement_row_impact_position(
        self,
        index: int,
        row: SettlementRow,
    ) -> pygame.Vector2:
        _, y = self.settlement_row_position(index)
        width, height = self.font_large.size(row.value_text)
        right = self.settlement_panel_rect().right - 56
        return pygame.Vector2(right - width * 1.25 / 2, y + height * 1.25 + 4)

    def settlement_rank_impact_position(self) -> pygame.Vector2:
        center = pygame.Vector2(self.settlement_score_center())
        rank = self.settlement.rank if self.settlement else "S"
        height = self.font_huge.size(rank)[1] * SETTLEMENT_RANK_IMPACT_SCALE
        return pygame.Vector2(center.x, center.y + height / 2 + 6)

    @staticmethod
    def settlement_button_rect() -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 - 190, SETTLEMENT_PANEL_Y + 480, 380, 52)

    def update_settlement(self, dt: float) -> None:
        settlement = self.settlement
        assert settlement is not None
        settlement.timer += dt
        settlement.pop_timer += dt
        self.cursor_phase += dt
        for particle in self.settlement_particles:
            particle.velocity.y += 460.0 * dt
            particle.position += particle.velocity * dt
            particle.velocity *= max(0.0, 1.0 - dt * 3.2)
            particle.life -= dt
        self.settlement_particles = [p for p in self.settlement_particles if p.life > 0]

        if settlement.phase == "slowmo":
            self._update_world(dt * SETTLEMENT_SLOWMO_SCALE)
            if settlement.timer >= SETTLEMENT_SLOWMO_DURATION:
                settlement.phase = "panel"
                settlement.timer = 0.0
                settlement.panel_y = -HEIGHT
                self._disable_relative_mouse()
                pygame.mouse.set_visible(True)
            return
        if settlement.phase == "panel":
            progress = min(1.0, settlement.timer / SETTLEMENT_PANEL_DURATION)
            eased = 1.0 - (1.0 - progress) ** 3
            settlement.panel_y = round(-HEIGHT + (SETTLEMENT_PANEL_Y + HEIGHT) * eased)
            if progress >= 1.0:
                settlement.phase = "rows"
                settlement.timer = -SETTLEMENT_FIRST_ROW_DELAY
                settlement.pop_timer = 0.0
                self.slam_settlement_impact(
                    pygame.Vector2(WIDTH // 2, SETTLEMENT_PANEL_Y + 30),
                    6.0,
                )
            return
        if settlement.phase == "rows":
            if settlement.timer >= 0.0:
                settlement.row_index += 1
                settlement.timer = -SETTLEMENT_ROW_INTERVAL
                settlement.pop_timer = 0.0
                row = settlement.rows[settlement.row_index - 1]
                impact = self.settlement_row_impact_position(settlement.row_index - 1, row)
                self.slam_settlement_impact(impact, row.magnitude)
                if settlement.row_index >= len(settlement.rows):
                    settlement.phase = "score"
                    settlement.timer = 0.0
            return
        if settlement.phase == "score":
            if settlement.timer >= SETTLEMENT_SCORE_DELAY:
                settlement.phase = "rank_drop"
                settlement.timer = 0.0
                settlement.pop_timer = 0.0
            return
        if settlement.phase == "rank_drop":
            if settlement.timer >= SETTLEMENT_RANK_DROP_DURATION:
                settlement.phase = "rank"
                settlement.timer = 0.0
                settlement.pop_timer = 0.0
                self.slam_settlement_impact(
                    self.settlement_rank_impact_position(),
                    SHAKE_STRENGTH_CAP,
                    big=True,
                )
                self.play_settlement_rank_sound()
            return
        if settlement.phase == "rank":
            if settlement.timer >= SETTLEMENT_BUTTON_DELAY:
                settlement.phase = "button"
                settlement.timer = 0.0
            return

    def slam_settlement_impact(
        self,
        position: pygame.Vector2,
        magnitude: float,
        big: bool = False,
    ) -> None:
        strength = (
            SHAKE_STRENGTH_CAP
            if big
            else min(SHAKE_STRENGTH_CAP, 5.5 + 2.6 * math.log10(max(1.0, magnitude)))
        )
        self.shake_strength = strength
        self.shake_duration = 0.55 if big else 0.35
        self.shake_timer = self.shake_duration
        self.play_settlement_impact(big)
        self.spawn_settlement_sparks(
            position,
            120 if big else 34,
            390.0 if big else 230.0,
            big=big,
        )

    def spawn_settlement_sparks(
        self,
        position: pygame.Vector2,
        count: int,
        speed: float,
        big: bool = False,
    ) -> None:
        for _ in range(count):
            if big and self.visual_rng.random() < 0.82:
                angle = self.visual_rng.uniform(math.pi + 0.12, math.tau - 0.12)
            else:
                angle = self.visual_rng.uniform(0, math.tau)
            velocity = (
                pygame.Vector2(math.cos(angle), math.sin(angle))
                * self.visual_rng.uniform(speed * 0.5, speed)
            )
            life = self.visual_rng.uniform(0.55, 0.95) if big else self.visual_rng.uniform(0.35, 0.65)
            self.settlement_particles.append(
                DeathParticle(
                    position.copy(),
                    velocity,
                    life,
                    life,
                    self.visual_rng.uniform(2.4, 5.8) if big else self.visual_rng.uniform(1.8, 3.8),
                )
            )
        if len(self.settlement_particles) > DEATH_PARTICLE_CAP:
            del self.settlement_particles[:-DEATH_PARTICLE_CAP]

    def finish_settlement(self) -> None:
        self.settlement = None
        self.settlement_particles = []
        if self.world == 8:
            self.mode = Mode.CHALLENGE_CHOICE
            self.sync_mouse_mode()
        elif self.world >= MAX_WORLD:
            self.mode = Mode.VICTORY
            self.sync_mouse_mode()
        else:
            self.enter_shop()

    def draw_settlement(self) -> None:
        settlement = self.settlement
        assert settlement is not None
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 7, 12, 165))
        self.screen.blit(shade, (0, 0))

        if settlement.phase == "slowmo":
            banner = self.font_large.render(f"世界 {self.world} 通关！", True, GREEN)
            banner.set_alpha(round(255 * min(1.0, settlement.timer / 0.5)))
            self.screen.blit(banner, banner.get_rect(center=(WIDTH // 2, 110)))
            return

        panel = self.settlement_panel_rect()
        panel.y = settlement.panel_y
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=16)
        pygame.draw.rect(self.screen, CYAN, panel, 3, border_radius=16)
        self.blit_text(
            f"世界 {self.world}/{MAX_WORLD} 通关结算",
            (panel.x + 40, panel.y + 22),
            WHITE,
            self.font_large,
        )

        shown = self.settlement_shown_rows()
        for index, row in enumerate(settlement.rows):
            if index >= shown:
                continue
            x, y = self.settlement_row_position(index)
            pop = 1.0
            if index == shown - 1 and settlement.pop_timer < 0.22:
                pop = 1.0 + 0.25 * (0.22 - settlement.pop_timer) / 0.22
            label = self.font.render(row.label, True, WHITE)
            label = pygame.transform.rotozoom(label, 0, pop)
            self.screen.blit(label, (x, y))
            if row.detail_text:
                self.blit_text(row.detail_text, (x, y + 38), MUTED, self.font_small)
            value = self.font_large.render(row.value_text, True, row.color)
            value = pygame.transform.rotozoom(value, 0, pop)
            self.screen.blit(value, value.get_rect(topright=(panel.right - 56, y)))

        if settlement.phase in ("rank_drop", "rank", "button"):
            center = pygame.Vector2(self.settlement_score_center())
            pop = 1.0
            if settlement.phase == "rank_drop":
                progress = min(1.0, settlement.timer / SETTLEMENT_RANK_DROP_DURATION)
                center.y -= 360 * (1.0 - progress) ** 3
                pop = 1.0 + 0.28 * (1.0 - progress)
            elif settlement.phase == "rank" and settlement.pop_timer < 0.35:
                pop = 1.0 + (SETTLEMENT_RANK_IMPACT_SCALE - 1.0) * (
                    0.35 - settlement.pop_timer
                ) / 0.35
            rank_text = self.settlement_rank_sprite()
            rank_text = pygame.transform.rotozoom(rank_text, 0, pop)
            self.screen.blit(rank_text, rank_text.get_rect(center=center))
            if settlement.phase != "rank_drop":
                score_text = self.font_large.render(f"总分 {settlement.score}", True, WHITE)
                self.screen.blit(score_text, score_text.get_rect(center=(center.x, center.y + 62)))
            if settlement.phase == "button":
                if self.world == 8:
                    label = "选择终局挑战"
                elif self.world >= MAX_WORLD:
                    label = "查看最终战绩"
                else:
                    label = "进入世界商店"
                self.draw_menu_button(self.settlement_button_rect(), label, GREEN)

        layer = self.visual_effect_layer
        layer.fill((0, 0, 0, 0))
        rank_color = self.settlement_rank_color()
        if settlement.phase in ("rank", "button") and settlement.pop_timer < 0.65:
            impact = self.settlement_rank_impact_position()
            progress = min(1.0, settlement.pop_timer / 0.65)
            ring_alpha = round(230 * (1.0 - progress) ** 2)
            ring_width = max(2, round(8 * (1.0 - progress)))
            ring = pygame.Rect(0, 0, round(80 + 420 * progress), round(20 + 90 * progress))
            ring.center = impact
            pygame.draw.ellipse(layer, (*rank_color, ring_alpha), ring, ring_width)
            if progress < 0.28:
                flash = 1.0 - progress / 0.28
                pygame.draw.circle(
                    layer,
                    (*rank_color, round(175 * flash)),
                    impact,
                    round(54 * flash + 12),
                )
        for particle in self.settlement_particles:
            alpha = round(255 * max(0.0, particle.life / particle.max_life))
            radius = max(1, round(particle.radius))
            tail = particle.position - particle.velocity * 0.045
            pygame.draw.line(
                layer,
                (*rank_color, round(alpha * 0.68)),
                tail,
                particle.position,
                max(1, radius),
            )
            pygame.draw.circle(
                layer,
                (*rank_color, round(alpha * 0.38)),
                particle.position,
                radius * 2,
            )
            pygame.draw.circle(
                layer,
                (250, 252, 255, alpha),
                particle.position,
                radius,
            )
        self.screen.blit(layer, (0, 0))

    def draw_blood_stains(self) -> None:
        if not self.blood_stains:
            return
        layer = self.visual_effect_layer
        layer.fill((0, 0, 0, 0))
        for stain in self.blood_stains:
            fade = min(1.0, stain.life / 1.5)
            alpha = round(185 * fade)
            if stain.sprite is not None:
                stain.sprite.set_alpha(round(255 * min(1.0, stain.life / stain.max_life) ** 0.72))
                self.screen.blit(stain.sprite, stain.sprite.get_rect(center=stain.position))
                continue
            base = stain.color
            dark = tuple(round(channel * 0.42) for channel in base)
            middle = tuple(min(255, round(channel * 1.08)) for channel in base)
            bright = tuple(min(255, round(channel * 1.34 + 12)) for channel in base)
            points = [stain.position + point for point in stain.points]
            pygame.draw.polygon(layer, (*dark, alpha), points)
            outer_points = [stain.position + point * 1.18 for point in stain.points]
            middle_points = [stain.position + point * 1.10 for point in stain.points]
            pygame.draw.polygon(layer, (*base, round(alpha * 0.14)), outer_points, 6)
            pygame.draw.polygon(layer, (*middle, round(alpha * 0.24)), middle_points, 4)
            pygame.draw.polygon(layer, (*bright, round(alpha * 0.63)), points, 4)
            for offset, drop_radius in stain.droplets:
                center = stain.position + offset
                radius = max(1, round(drop_radius))
                pygame.draw.circle(
                    layer,
                    (*dark, round(alpha * 0.90)),
                    center,
                    radius,
                )
                pygame.draw.circle(
                    layer,
                    (*base, round(alpha * 0.18)),
                    center,
                    radius + 2,
                    2,
                )
                pygame.draw.circle(
                    layer,
                    (*bright, round(alpha * 0.38)),
                    center,
                    radius,
                    1,
                )
        self.screen.blit(layer, (0, 0))

    def draw_death_particles(self) -> None:
        if not self.death_particles:
            return
        layer = self.visual_effect_layer
        layer.fill((0, 0, 0, 0))
        for particle in self.death_particles:
            alpha = round(255 * max(0.0, particle.life / particle.max_life))
            pygame.draw.circle(
                layer,
                (*particle.color, alpha),
                particle.position,
                max(1, round(particle.radius)),
            )
        self.screen.blit(layer, (0, 0))

    def apply_glow(self) -> None:
        if self.glow_brightness <= 0 or self.glow_opacity <= 0:
            return
        spread = self.glow_spread
        weights = (
            0.62 - 0.28 * spread,
            0.24 + 0.02 * spread,
            0.04 + 0.26 * spread,
        )
        threshold = round(46 - self.glow_feather * 28)
        blur_base = 1 + round(self.glow_feather * 2)
        intensity = self.glow_brightness * self.glow_opacity * 2.75
        self.glow_source_surface.blit(self.screen, (0, 0))

        for index, (small, blurred, large) in enumerate(self.glow_cache):
            pygame.transform.smoothscale(self.glow_source_surface, small.get_size(), small)
            small.fill((threshold, threshold, threshold), special_flags=pygame.BLEND_RGB_SUB)
            if index == 0:
                blurred.blit(small, (0, 0))
            else:
                pygame.transform.box_blur(
                    small,
                    blur_base + index,
                    dest_surface=blurred,
                )
            pygame.transform.smoothscale(blurred, (WIDTH, HEIGHT), large)

            strength = intensity * weights[index]
            while strength >= 1.0:
                self.screen.blit(large, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                strength -= 1.0
            if strength > 0:
                multiplier = round(255 * strength)
                large.fill(
                    (multiplier, multiplier, multiplier),
                    special_flags=pygame.BLEND_RGB_MULT,
                )
                self.screen.blit(large, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def apply_screen_shake(self) -> None:
        if self.shake_timer <= 0 or self.shake_intensity <= 0:
            return
        fade = self.shake_timer / max(0.001, self.shake_duration)
        magnitude = self.shake_strength * self.shake_intensity * fade
        offset = (
            round(self.visual_rng.uniform(-magnitude, magnitude)),
            round(self.visual_rng.uniform(-magnitude, magnitude)),
        )
        frame = self.screen.copy()
        self.screen.fill(BG)
        self.screen.blit(frame, offset)

    def draw(self) -> None:
        self.screen.fill(BG)
        if self.mode == Mode.MAIN_MENU:
            self.draw_main_menu()
        elif self.mode == Mode.TUTORIAL:
            self.draw_tutorial()
        elif self.mode == Mode.SETTINGS:
            self.draw_settings()
        elif self.mode == Mode.CHALLENGE_CHOICE:
            self.draw_challenge_choice()
        elif self.mode == Mode.SHOP:
            self.draw_shop()
            self.apply_glow()
        else:
            self.draw_arena()
            self.draw_blood_stains()
            self.draw_gates()
            self.draw_enemies()
            self.draw_bosses()
            self.draw_death_particles()
            self.draw_bullets()
            self.draw_enemy_bullets()
            self.draw_player()
            if self.sprite_calibration_open:
                self.draw_sprite_calibration_guides()
            self.apply_glow()
            if self.mode == Mode.PLAYING and (
                self.settlement is None or self.settlement.phase == "slowmo"
            ):
                self.draw_cursor_effects()
            self.draw_hud()
            if self.settlement is not None:
                self.draw_settlement()
            if self.mode == Mode.PAUSED:
                self.draw_pause_menu()
            elif self.mode == Mode.GAME_OVER:
                if self.challenge_checkpoint is not None and self.world >= 9:
                    self.draw_overlay("终局挑战失败", self.death_reason)
                    self.draw_challenge_failure_actions()
                else:
                    self.draw_overlay("防线失守", f"{self.death_reason} | 按 R 重开")
            elif self.mode == Mode.VICTORY:
                self.draw_overlay(
                    "十世界通关",
                    f"最终人口 {format_number(self.population)} | "
                    f"金币 {self.gold} | 按 R 再来一局",
                )
        if self.dev_panel_open:
            self.draw_dev_panel()
        elif self.sprite_calibration_open:
            self.draw_sprite_calibration_panel()
        self.apply_screen_shake()
        pygame.display.flip()

    @staticmethod
    def main_menu_button_rect(index: int) -> pygame.Rect:
        return pygame.Rect(72, 330 + index * 66, 318, 52)

    @staticmethod
    def menu_back_rect() -> pygame.Rect:
        return pygame.Rect(55, 625, 150, 52)

    @staticmethod
    def challenge_choice_rect(action: str) -> pygame.Rect:
        x = WIDTH // 2 - 370 if action == "restart" else WIDTH // 2 + 30
        return pygame.Rect(x, 505, 340, 68)

    @staticmethod
    def challenge_failure_rect(action: str) -> pygame.Rect:
        x = WIDTH // 2 - 330 if action == "retry" else WIDTH // 2 + 20
        return pygame.Rect(x, 455, 310, 62)

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
            ("settlement", "结算音效"),
        )

    @staticmethod
    def settings_volume_button_rect(index: int, direction: int) -> pygame.Rect:
        column_x = 55 if index < 4 else 650
        return pygame.Rect(
            column_x + (330 if direction < 0 else 480),
            Game.settings_audio_y(index) + 5,
            42,
            38,
        )

    @staticmethod
    def settings_audio_y(index: int) -> int:
        return 376 + (index % 4) * 55

    @staticmethod
    def settings_visual_rows() -> tuple[tuple[str, str], ...]:
        return (
            ("shake", "屏幕震动"),
            ("glow_brightness", "辉光亮度"),
            ("glow_spread", "辉光扩散"),
            ("glow_opacity", "辉光透明度"),
            ("glow_feather", "辉光羽化"),
        )

    @staticmethod
    def settings_visual_y(index: int) -> int:
        return 245 + (index // 3) * 47

    @staticmethod
    def settings_visual_x(index: int) -> int:
        return 35 + (index % 3) * 410

    @staticmethod
    def settings_visual_button_rect(index: int, direction: int) -> pygame.Rect:
        column_x = Game.settings_visual_x(index)
        return pygame.Rect(
            column_x + (220 if direction < 0 else 340),
            Game.settings_visual_y(index) + 4,
            36,
            38,
        )

    def visual_effect_value(self, kind: str) -> float:
        return {
            "shake": self.shake_intensity,
            "glow_brightness": self.glow_brightness,
            "glow_spread": self.glow_spread,
            "glow_opacity": self.glow_opacity,
            "glow_feather": self.glow_feather,
        }[kind]

    def adjust_visual_effect(self, kind: str, direction: int) -> None:
        value = round(max(0.0, min(1.0, self.visual_effect_value(kind) + direction * 0.1)), 1)
        if kind == "shake":
            self.shake_intensity = value
        elif kind == "glow_brightness":
            self.glow_brightness = value
        elif kind == "glow_spread":
            self.glow_spread = value
        elif kind == "glow_opacity":
            self.glow_opacity = value
        else:
            self.glow_feather = value

    @staticmethod
    def settings_mouse_sensitivity_button_rect(direction: int) -> pygame.Rect:
        return pygame.Rect(810 if direction < 0 else 1055, 108, 48, 38)

    @staticmethod
    def settings_mouse_sensitivity_value_rect() -> pygame.Rect:
        return pygame.Rect(885, 108, 150, 38)

    @staticmethod
    def settings_crosshair_button_rect(direction: int) -> pygame.Rect:
        return pygame.Rect(810 if direction < 0 else 1055, 165, 48, 42)

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
        self.screen.fill(BG)
        field = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(self.cursor_phase * 2.4)
        for radius, alpha in ((520, 12), (330, 18), (170, 24)):
            pygame.draw.circle(field, (*CYAN, alpha), (1090, 165), radius)
        for radius, alpha in ((460, 10), (280, 17), (120, 26)):
            pygame.draw.circle(field, (*MAGENTA, alpha), (900, 620), radius)
        # Alpha-composite the large light fields. Additive blending in pygame
        # applies the RGB values independently from alpha and turns these
        # intentionally soft blooms into opaque cyan/magenta discs.
        self.screen.blit(field, (0, 0))
        for y in range(0, HEIGHT, 36):
            pygame.draw.line(self.screen, (11, 20, 43), (0, y), (WIDTH, y), 1)
        for x in range(-HEIGHT, WIDTH, 72):
            pygame.draw.line(self.screen, (10, 18, 38), (x, HEIGHT), (x + HEIGHT, 0), 1)
        horizon_y = 574
        self.draw_neon_line((0, horizon_y), (WIDTH, horizon_y), CYAN, 1, 18)
        scan_y = int((self.cursor_phase * 95) % HEIGHT)
        pygame.draw.line(self.screen, (*WHITE,), (0, scan_y), (WIDTH, scan_y), 1)
        scan = pygame.Surface((WIDTH, 46), pygame.SRCALPHA)
        scan.fill((36, 226, 255, int(5 + pulse * 7)))
        self.screen.blit(scan, (0, scan_y - 23))

    def draw_neon_line(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: tuple[int, int, int],
        width: int = 2,
        glow: int = 12,
    ) -> None:
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for extra, alpha in ((glow, 14), (max(2, glow // 2), 30)):
            pygame.draw.line(layer, (*color, alpha), start, end, width + extra)
        self.screen.blit(layer, (0, 0))
        pygame.draw.line(self.screen, color, start, end, width)

    def draw_corner_brackets(
        self,
        rect: pygame.Rect,
        color: tuple[int, int, int],
        length: int = 16,
        width: int = 2,
    ) -> None:
        for x, y, sx, sy in (
            (rect.left, rect.top, 1, 1),
            (rect.right, rect.top, -1, 1),
            (rect.left, rect.bottom, 1, -1),
            (rect.right, rect.bottom, -1, -1),
        ):
            pygame.draw.line(self.screen, color, (x, y), (x + sx * length, y), width)
            pygame.draw.line(self.screen, color, (x, y), (x, y + sy * length), width)

    def draw_section_title(self, title: str, position: tuple[int, int], color: tuple[int, int, int] = CYAN) -> None:
        x, y = position
        self.draw_neon_line((x, y + 31), (x + 170, y + 31), color, 1, 8)
        self.blit_text(title, (x, y), WHITE, self.font_small)

    def draw_ui_panel(
        self,
        rect: pygame.Rect,
        *,
        fill: tuple[int, int, int] = PANEL,
        rim: tuple[int, int, int] = UI_RIM,
        radius: int = 8,
        glass: bool = False,
    ) -> None:
        shadow = pygame.Surface((rect.width + 28, rect.height + 30), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 120), (14, 16, rect.width, rect.height), border_radius=radius + 2)
        self.screen.blit(shadow, (rect.x - 14, rect.y - 8))
        if glass:
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(layer, GLASS_TINT, layer.get_rect(), border_radius=radius)
            pygame.draw.line(layer, GLASS_RIM, (radius, 1), (rect.width - radius, 1), 2)
            self.screen.blit(layer, rect.topleft)
        else:
            pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen, rim, rect, 1, border_radius=radius)
        self.draw_corner_brackets(rect, rim, min(14, max(7, rect.height // 3)), 1)

    def draw_step_row(
        self,
        rect: pygame.Rect,
        *,
        active_index: int | None = None,
        progress: float | None = None,
        danger_from: int = 12,
        labels: bool = False,
    ) -> None:
        gap = 5
        step_width = (rect.width - gap * 15) // 16
        for index in range(16):
            x = rect.x + index * (step_width + gap)
            key = pygame.Rect(x, rect.y, step_width, rect.height)
            reached = progress is not None and index <= round(max(0.0, min(1.0, progress)) * 15)
            color = STEP_DIM if reached else STEP_OFF
            if index >= danger_from:
                color = RED if reached else DARK_RED
            if active_index == index:
                color = CYAN
            pygame.draw.rect(self.screen, color, key, border_radius=4)
            highlight = tuple(min(255, channel + 34) for channel in color)
            pygame.draw.line(self.screen, highlight, (x + 4, rect.y + 2), (x + step_width - 4, rect.y + 2), 1)
            if labels:
                number_color = WHITE if reached or active_index == index else MUTED
                number = self.font_tiny.render(str(index + 1), True, number_color)
                self.screen.blit(number, number.get_rect(center=(key.centerx, key.bottom + 13)))

    def draw_value_stepper(
        self,
        value: str,
        minus: pygame.Rect,
        plus: pygame.Rect,
        *,
        editing: bool = False,
    ) -> None:
        value_rect = pygame.Rect(minus.right + 16, minus.y, plus.left - minus.right - 32, minus.height)
        self.draw_ui_panel(value_rect, fill=(12, 17, 20), rim=CYAN if editing else GRID, radius=6)
        rendered = self.font_numeric.render(value, True, CYAN)
        self.screen.blit(rendered, rendered.get_rect(center=value_rect.center))
        for button, symbol in ((minus, "-"), (plus, "+")):
            hovered = button.collidepoint(pygame.mouse.get_pos())
            self.draw_ui_panel(button, fill=PANEL_RAISED if hovered else PANEL, rim=CYAN if hovered else GRID, radius=6)
            glyph = self.font.render(symbol, True, WHITE)
            self.screen.blit(glyph, glyph.get_rect(center=button.center))

    def draw_menu_button(self, rect: pygame.Rect, text: str, color: tuple[int, int, int] = CYAN) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        pressed = hovered and pygame.mouse.get_pressed(num_buttons=3)[0]
        primary = color in (GREEN, RED, OVERLOAD, MAGENTA)
        fill = tuple(max(0, channel // 7) for channel in color) if primary else PANEL_RAISED if hovered else PANEL
        draw_rect = rect.move(0, 1 if pressed else 0)
        if hovered:
            glow = pygame.Surface((draw_rect.width + 28, draw_rect.height + 28), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, 38), (14, 14, draw_rect.width, draw_rect.height), border_radius=12)
            self.screen.blit(glow, (draw_rect.x - 14, draw_rect.y - 14))
        self.draw_ui_panel(draw_rect, fill=fill, rim=color if hovered or primary else UI_RIM, radius=6)
        pygame.draw.rect(self.screen, color, (draw_rect.x, draw_rect.y, 5, draw_rect.height), border_radius=3)
        label_color = WHITE
        label = self.font_small.render(text, True, label_color)
        self.screen.blit(label, label.get_rect(midleft=(draw_rect.x + 20, draw_rect.centery)))
        state = self.font_tiny.render("ACT" if primary else "SEL", True, label_color if hovered else MUTED)
        self.screen.blit(state, state.get_rect(midright=(draw_rect.right - 16, draw_rect.centery)))

    def draw_reactor_core(self, center: pygame.Vector2) -> None:
        """Draw the animated menu reactor with local supersampling."""
        scale = 2
        size = 448
        local_center = pygame.Vector2(size / 2, size / 2)
        reactor = pygame.Surface((size * scale, size * scale), pygame.SRCALPHA)
        phase = self.cursor_phase * 1.8

        def scaled_point(point: pygame.Vector2) -> tuple[int, int]:
            return round(point.x * scale), round(point.y * scale)

        for radius, color, width in ((178, CYAN, 2), (132, MAGENTA, 2), (82, WHITE, 1)):
            arc_rect = pygame.Rect(
                round((local_center.x - radius) * scale),
                round((local_center.y - radius) * scale),
                radius * 2 * scale,
                radius * 2 * scale,
            )
            for start, stop in (
                (phase, phase + math.pi * 1.35),
                (phase + math.pi, phase + math.pi * 1.7),
            ):
                pygame.draw.arc(reactor, (*color, 34), arc_rect, start, stop, max(8, width * 5) * scale)
                pygame.draw.arc(reactor, (*color, 84), arc_rect, start, stop, max(4, width * 2) * scale)
                pygame.draw.arc(reactor, (*color, 255), arc_rect, start, stop, width * scale)

        for index in range(12):
            angle = phase * (1 if index % 2 else -0.55) + index * math.tau / 12
            direction = pygame.Vector2(math.cos(angle), math.sin(angle))
            outer = local_center + direction * 205
            inner = local_center + direction * (188 if index % 3 else 172)
            color = CYAN if index % 2 else MAGENTA
            pygame.draw.line(reactor, (*color, 42), scaled_point(inner), scaled_point(outer), 7 * scale)
            pygame.draw.line(reactor, (*color, 108), scaled_point(inner), scaled_point(outer), 3 * scale)
            pygame.draw.line(reactor, (*color, 255), scaled_point(inner), scaled_point(outer), scale)

        core_center = scaled_point(local_center)
        pygame.draw.circle(reactor, (8, 13, 30, 255), core_center, 58 * scale)
        pygame.draw.circle(reactor, (*WHITE, 44), core_center, 62 * scale, 8 * scale)
        pygame.draw.circle(reactor, (*WHITE, 255), core_center, 58 * scale, 2 * scale)
        pygame.draw.circle(reactor, (*CYAN, 40), core_center, 48 * scale, 8 * scale)
        pygame.draw.circle(reactor, (*CYAN, 255), core_center, 44 * scale, 2 * scale)

        reactor = pygame.transform.smoothscale(reactor, (size, size))
        self.screen.blit(reactor, reactor.get_rect(center=(round(center.x), round(center.y))))

        core_label = self.font_tiny.render("CORE", True, WHITE)
        online_label = self.font_tiny.render("ONLINE", True, GREEN)
        core_ink = core_label.get_bounding_rect()
        online_ink = online_label.get_bounding_rect()
        gap = 3
        block_height = core_ink.height + gap + online_ink.height
        ink_top = round(center.y - block_height / 2)
        self.screen.blit(
            core_label,
            (round(center.x - core_ink.centerx), ink_top - core_ink.top),
        )
        self.screen.blit(
            online_label,
            (
                round(center.x - online_ink.centerx),
                ink_top + core_ink.height + gap - online_ink.top,
            ),
        )

    def draw_main_menu(self) -> None:
        self.draw_menu_background()
        self.blit_text("FIREPOWER", (70, 54), CYAN, self.font_small)
        self.blit_text("火力过载", (68, 86), WHITE, self.font_huge)
        self.blit_text("PHOTON OVERDRIVE", (72, 168), MAGENTA, self.font_large)
        self.blit_text("在十个世界中校准火力、构筑卡组、击穿终局。", (74, 224), MUTED, self.font_small)

        self.draw_reactor_core(pygame.Vector2(918, 260))
        self.blit_text("十世界作战协议", (760, 491), WHITE, self.font_small)
        self.blit_text("火力演算 / 人口增幅 / 卡组编译", (760, 525), MUTED, self.font_tiny)

        for index, (label, color) in enumerate((("启动作战", MAGENTA), ("战术简报", CYAN), ("系统校准", PURPLE))):
            self.draw_menu_button(self.main_menu_button_rect(index), label, color)
        self.blit_text("ENTER / SPACE  立即接入", (74, 548), CYAN, self.font_tiny)
        self.draw_step_row(
            pygame.Rect(72, 610, 1136, 28),
            active_index=int(self.cursor_phase * 5) % 16,
            labels=True,
        )
        self.blit_text("WORLD SEQUENCE", (72, 672), MUTED, self.font_tiny)
        self.blit_text("CAMPAIGN 01-08", (468, 672), WHITE, self.font_tiny)
        self.blit_text("ENDGAME 09-10", (1028, 672), MAGENTA, self.font_tiny)

    def draw_challenge_choice(self) -> None:
        self.draw_menu_background()
        title = self.font_huge.render("世界8通关", True, GREEN)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 155)))
        self.blit_text(
            "主线已经完成。可立即开启新局，或带着当前构筑挑战两个终局Boss。",
            (WIDTH // 2 - 385, 245),
            WHITE,
            self.font,
        )
        stats = (
            f"继承人口 {format_number(self.population)}",
            f"金币 {self.gold}",
            f"参考DPS {format_number(self.current_dps())}",
        )
        for index, value in enumerate(stats):
            self.blit_text(value, (WIDTH // 2 - 300 + index * 220, 330), YELLOW, self.font_small)
        self.blit_text(
            "世界9、10各限时90秒；失败后可从世界9严格还原重试。",
            (WIDTH // 2 - 300, 400),
            MUTED,
            self.font_small,
        )
        self.draw_menu_button(
            self.challenge_choice_rect("restart"),
            "重新开始世界1（R）",
            CYAN,
        )
        self.draw_menu_button(
            self.challenge_choice_rect("continue"),
            "继续挑战世界9（Enter）",
            OVERLOAD,
        )

    def draw_challenge_failure_actions(self) -> None:
        self.draw_menu_button(
            self.challenge_failure_rect("retry"),
            "从世界9重试（R）",
            OVERLOAD,
        )
        self.draw_menu_button(
            self.challenge_failure_rect("new"),
            "开始全新一局（N）",
            CYAN,
        )

    def draw_tutorial(self) -> None:
        self.draw_menu_background()
        self.blit_text("战术简报", (55, 36), WHITE, self.font_large)
        self.blit_text(
            "先保持移动，再读威胁层级；人口、火力与卡组共同决定生存窗口。",
            (58, 105),
            CYAN,
            self.font_small,
        )
        sections = (
            ("移动与射击", "WASD移动；鼠标瞄准；按住左键自动射击。\n人口既是生命，也是子弹伤害倍率。"),
            ("敌人与Boss", "普通怪接触会损失人口，精英和Boss还会发射弹幕。\n小Boss约25秒、中Boss 60秒、大Boss 90秒出现。"),
            ("门的玩法", "射击数字门改变门上的人口数；解锁特殊门获得临时增益。\n移动到门内吃门。穿透不能穿门，反弹子弹会从门上弹回。"),
            (
                "商店与构筑",
                "击杀Boss获得金币；世界1～7及世界9结束后进入商店。\n最多携带5张卡。左键购买/出售，右键查看卡牌详情。",
            ),
            ("战术终端", "Esc查看当前DPS、暴击和音量；R可在暂停菜单重新开始。\nF1开启开发者终端，用于快速验证构筑与战斗反馈。"),
            (
                "胜利条件",
                "前8个世界完成主线；之后可挑战世界9、10终局Boss。\n主线限时120秒，终局Boss世界限时90秒。",
            ),
        )
        for index, (heading, body) in enumerate(sections):
            y = 150 + index * 73
            color = CYAN if index < 4 else MAGENTA
            key = pygame.Rect(56, y, 44, 44)
            self.draw_ui_panel(key, fill=tuple(channel // 6 for channel in color), rim=color, radius=3)
            number = self.font_numeric.render(f"{index + 1:02}", True, WHITE)
            self.screen.blit(number, number.get_rect(center=key.center))
            self.blit_text(heading, (122, y - 1), WHITE, self.font_small)
            self.blit_text(body.replace("\n", "  "), (122, y + 27), MUTED, self.font_tiny)
            self.draw_neon_line((122, y + 55), (1215, y + 55), color, 1, 5)
        self.draw_menu_button(self.menu_back_rect(), "返回主终端", CYAN)

    def draw_settings(self) -> None:
        self.draw_menu_background()
        self.blit_text("系统校准", (55, 34), WHITE, self.font_large)
        self.blit_text("所有参数即时写入作战终端；点击灵敏度数值可精确输入", (58, 82), CYAN, self.font_small)

        sensitivity_rect = pygame.Rect(270, 103, 850, 48)
        self.draw_ui_panel(sensitivity_rect, fill=PANEL, rim=CYAN, glass=True)
        self.blit_text("鼠标灵敏度", (sensitivity_rect.x + 22, sensitivity_rect.y + 13), WHITE, self.font_small)
        sensitivity_minus = self.settings_mouse_sensitivity_button_rect(-1)
        sensitivity_plus = self.settings_mouse_sensitivity_button_rect(1)
        self.draw_ui_panel(sensitivity_minus, fill=PANEL_RAISED, rim=GRID, radius=6)
        self.draw_ui_panel(sensitivity_plus, fill=PANEL_RAISED, rim=GRID, radius=6)
        self.blit_text("-", (sensitivity_minus.x + 17, sensitivity_minus.y + 5), WHITE, self.font)
        self.blit_text("+", (sensitivity_plus.x + 13, sensitivity_plus.y + 5), WHITE, self.font)
        value_rect = self.settings_mouse_sensitivity_value_rect()
        self.draw_ui_panel(value_rect, fill=(12, 17, 20), rim=CYAN if self.mouse_sensitivity_editing else GRID, radius=6)
        if self.mouse_sensitivity_editing:
            text = self.sensitivity_input_text + "|"
        else:
            text = f"{self.mouse_sensitivity:g}"
        sensitivity = self.font.render(text, True, CYAN)
        self.screen.blit(sensitivity, sensitivity.get_rect(center=value_rect.center))

        crosshair_rect = pygame.Rect(270, 160, 850, 52)
        self.draw_ui_panel(crosshair_rect, fill=PANEL, rim=PURPLE, glass=True)
        self.blit_text("准星预设", (crosshair_rect.x + 22, crosshair_rect.y + 13), WHITE, self.font_small)
        crosshair_minus = self.settings_crosshair_button_rect(-1)
        crosshair_plus = self.settings_crosshair_button_rect(1)
        self.draw_ui_panel(crosshair_minus, fill=PANEL_RAISED, rim=GRID, radius=6)
        self.draw_ui_panel(crosshair_plus, fill=PANEL_RAISED, rim=GRID, radius=6)
        self.blit_text("<", (crosshair_minus.x + 17, crosshair_minus.y + 5), WHITE, self.font)
        self.blit_text(">", (crosshair_plus.x + 14, crosshair_plus.y + 5), WHITE, self.font)
        preview = self._render_crosshair_sprite(0.55)
        self.screen.blit(preview, preview.get_rect(center=(930, crosshair_rect.centery)))
        preset_name = self.font_small.render(self.crosshair_preset_name(), True, CYAN)
        self.screen.blit(preset_name, (crosshair_rect.x + 128, crosshair_rect.y + 13))

        self.draw_section_title("视觉增幅矩阵", (58, 214), MAGENTA)
        for index, (kind, label) in enumerate(self.settings_visual_rows()):
            y = self.settings_visual_y(index)
            x = self.settings_visual_x(index)
            rect = pygame.Rect(x, y, 390, 45)
            color = (CYAN, MAGENTA, PURPLE, CYAN, MAGENTA)[index]
            self.draw_ui_panel(rect, fill=PANEL, rim=color, radius=5, glass=True)
            self.blit_text(label, (rect.x + 14, rect.y + 9), WHITE, self.font_small)
            minus = self.settings_visual_button_rect(index, -1)
            plus = self.settings_visual_button_rect(index, 1)
            self.draw_ui_panel(minus, fill=PANEL_RAISED, rim=GRID, radius=6)
            self.draw_ui_panel(plus, fill=PANEL_RAISED, rim=GRID, radius=6)
            self.blit_text("-", (minus.x + 14, minus.y + 3), WHITE, self.font)
            self.blit_text("+", (plus.x + 10, plus.y + 3), WHITE, self.font)
            value = self.font.render(f"{self.visual_effect_value(kind):.0%}", True, CYAN)
            self.screen.blit(value, value.get_rect(center=(rect.x + 298, rect.centery)))
            meter = pygame.Rect(rect.x + 118, rect.bottom - 5, 190, 2)
            pygame.draw.rect(self.screen, GRID, meter)
            meter.width = round(meter.width * self.visual_effect_value(kind))
            self.draw_neon_line(meter.topleft, meter.topright, color, 2, 5)

        self.draw_section_title("声音通道", (58, 346), CYAN)
        for index, (kind, label) in enumerate(self.settings_volume_rows()):
            y = self.settings_audio_y(index)
            x = 55 if index < 4 else 650
            rect = pygame.Rect(x, y, 575, 48)
            color = CYAN if index < 4 else PURPLE
            self.draw_ui_panel(rect, fill=PANEL, rim=color, radius=5, glass=True)
            self.blit_text(label, (rect.x + 18, rect.y + 12), WHITE, self.font_small)
            minus = self.settings_volume_button_rect(index, -1)
            plus = self.settings_volume_button_rect(index, 1)
            self.draw_ui_panel(minus, fill=PANEL_RAISED, rim=GRID, radius=6)
            self.draw_ui_panel(plus, fill=PANEL_RAISED, rim=GRID, radius=6)
            self.blit_text("-", (minus.x + 14, minus.y + 3), WHITE, self.font)
            self.blit_text("+", (plus.x + 10, plus.y + 3), WHITE, self.font)
            value = self.font.render(f"{self.volume_value(kind):.0%}", True, CYAN)
            self.screen.blit(value, value.get_rect(center=(rect.right - 150, rect.centery)))
            meter = pygame.Rect(rect.x + 180, rect.bottom - 5, 235, 2)
            pygame.draw.rect(self.screen, GRID, meter)
            meter.width = round(meter.width * self.volume_value(kind))
            self.draw_neon_line(meter.topleft, meter.topright, color, 2, 4)
        self.draw_menu_button(self.menu_back_rect(), "返回主终端", CYAN)

    def draw_arena(self) -> None:
        arena_light = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(arena_light, (*CYAN, 13), (WIDTH - 140, 170), 380)
        pygame.draw.circle(arena_light, (*MAGENTA, 11), (120, PLAY_TOP - 70), 310)
        pygame.draw.rect(arena_light, (16, 26, 57, 208), (0, PLAY_TOP, WIDTH, HEIGHT - PLAY_TOP))
        self.screen.blit(arena_light, (0, 0))

        # A restrained technical grid keeps trajectories legible while the
        # edge rails and scanner accents carry the high-energy identity.
        for x in range(0, WIDTH, 80):
            pygame.draw.line(self.screen, GRID, (x, 64), (x, HEIGHT), 1)
        for y in range(64, HEIGHT, 80):
            pygame.draw.line(self.screen, GRID, (0, y), (WIDTH, y), 1)
        self.draw_neon_line((0, PLAY_TOP), (WIDTH, PLAY_TOP), CYAN, 2, 12)
        pygame.draw.line(self.screen, MAGENTA, (0, 66), (188, 66), 2)
        pygame.draw.line(self.screen, CYAN, (WIDTH - 188, PLAY_TOP - 1), (WIDTH, PLAY_TOP - 1), 3)

        scan_x = int((self.cursor_phase * 72) % WIDTH)
        scan = pygame.Surface((72, PLAY_TOP - 64), pygame.SRCALPHA)
        for offset, alpha in ((0, 0), (18, 5), (36, 9), (54, 5), (71, 0)):
            pygame.draw.line(scan, (*CYAN, alpha), (offset, 0), (offset, scan.get_height()))
        self.screen.blit(scan, (scan_x - 36, 64))

        self.blit_text("实体投送区 / ENTITY INGRESS", (18, 76), MUTED, self.font_tiny)
        self.blit_text("机动甲板 / MANEUVER DECK", (18, PLAY_TOP + 12), MUTED, self.font_tiny)
        self.blit_text("LIVE FIRESPACE", (WIDTH - 154, 76), MAGENTA, self.font_tiny)

    def gun_mount_position(self) -> pygame.Vector2:
        """Return the top-turret pivot in the aircraft's local coordinate space."""
        return self.player + self.gun_center_offset.rotate(-self.player_body_heading)

    def player_art_position(self) -> pygame.Vector2:
        """Keep the baked hull pivot and logical player center coincident."""
        return self.player + self.player_center_offset.rotate(-self.player_body_heading)

    def escort_ring_counts(self) -> tuple[int, int, int]:
        population = max(0, self.population)
        counts: list[int] = []
        lower_bound = 0
        for upper_bound, _, capacity in ESCORT_RING_SPECS:
            progress = (population - lower_bound) / max(1, upper_bound - lower_bound)
            counts.append(max(0, min(capacity, math.ceil(progress * capacity))))
            lower_bound = upper_bound
        return tuple(counts)

    def draw_escort_turret(self, position: pygame.Vector2, direction: pygame.Vector2) -> None:
        forward = normalized(direction)
        if not forward.length_squared():
            forward = pygame.Vector2(1, 0)
        side = pygame.Vector2(-forward.y, forward.x)
        nose = position + forward * 7
        shoulder = position + forward * 2
        rear = position - forward * 5
        hull = (
            nose,
            rear + side * 4,
            rear - side * 4,
        )
        pygame.draw.polygon(self.screen, (18, 35, 57), hull)
        pygame.draw.polygon(self.screen, CYAN, hull, 1)
        pygame.draw.line(self.screen, WHITE, shoulder, nose, 2)
        pygame.draw.circle(self.screen, (42, 137, 172), position, 3)
        pygame.draw.circle(self.screen, WHITE, position, 1)

    def draw_player(self) -> None:
        aim = self.aim_direction()
        aim_heading = math.degrees(math.atan2(aim.y, aim.x)) % 360.0
        heading_delta = (aim_heading - self.player_body_heading + 180.0) % 360.0 - 180.0
        if abs(heading_delta) > PLAYER_BODY_TURN_THRESHOLD:
            self.player_body_heading = (
                self.player_body_heading
                + math.copysign(PLAYER_BODY_STEP_DEGREES, heading_delta)
            ) % 360.0
        body_sprites, gun_sprite = self.load_player_sprites()
        body_step = round(self.player_body_heading / PLAYER_BODY_STEP_DEGREES) % len(body_sprites)
        body_sprite = body_sprites[body_step]
        self.screen.blit(
            body_sprite,
            body_sprite.get_rect(center=self.player_art_position()),
        )
        rotated_gun = pygame.transform.rotate(gun_sprite, -aim_heading)
        self.screen.blit(
            rotated_gun,
            rotated_gun.get_rect(center=self.gun_mount_position()),
        )
        ring_counts = self.escort_ring_counts()
        for ring_index, ((_, radius, _), visible) in enumerate(
            zip(ESCORT_RING_SPECS, ring_counts)
        ):
            if visible <= 0:
                continue
            phase = ring_index * math.pi / max(1, visible)
            for index in range(visible):
                angle = phase + index * math.tau / visible
                escort = self.player + pygame.Vector2(
                    math.cos(angle) * radius,
                    math.sin(angle) * radius,
                )
                self.draw_escort_turret(escort, aim)

    def draw_bullets(self) -> None:
        for bullet in self.bullets:
            pygame.draw.circle(self.screen, YELLOW, bullet.position, bullet.radius)

    def draw_enemy_bullets(self) -> None:
        for bullet in self.enemy_bullets:
            pygame.draw.circle(self.screen, RED, bullet.position, bullet.radius)
            pygame.draw.circle(self.screen, ORANGE, bullet.position, bullet.radius, 2)

    def draw_guardian_shields(self, enemy: Enemy) -> None:
        for shield in enemy.shields:
            if shield.hp <= 0:
                continue
            center = shield.world_position(enemy.position)
            radial = normalized(center - enemy.position)
            tangent = pygame.Vector2(-radial.y, radial.x)
            points = (
                center + tangent * 11 - radial * 5,
                center + tangent * 11 + radial * 5,
                center - tangent * 11 + radial * 5,
                center - tangent * 11 - radial * 5,
            )
            pygame.draw.polygon(self.screen, (225, 238, 247), points)
            pygame.draw.polygon(self.screen, CYAN, points, 2)
            ratio = max(0.0, min(1.0, shield.hp / shield.max_hp))
            pygame.draw.line(
                self.screen,
                (26, 46, 65),
                center - tangent * 7,
                center + tangent * 7,
                2,
            )
            pygame.draw.line(
                self.screen,
                CYAN,
                center - tangent * 7,
                center - tangent * 7 + tangent * 14 * ratio,
                2,
            )

    def draw_enemies(self) -> None:
        enemies_by_id = {id(enemy): enemy for enemy in self.enemies}
        for enemy in self.enemies:
            if enemy.elite_kind == "archon":
                for target_id in enemy.linked_target_ids:
                    target = enemies_by_id.get(target_id)
                    if target is not None and target.hp > 0:
                        pygame.draw.line(self.screen, (29, 99, 125), enemy.position, target.position, 5)
                        pygame.draw.line(self.screen, CYAN, enemy.position, target.position, 2)
            elif enemy.elite_kind == "hunter" and enemy.elite_state == "lock":
                end = enemy.position + enemy.charge_direction * 430.0
                pygame.draw.line(self.screen, DARK_RED, enemy.position, end, 6)
                pygame.draw.line(self.screen, RED, enemy.position, end, 2)
                pygame.draw.circle(self.screen, WHITE, end, 5, 2)

        for enemy in self.enemies:
            if enemy.elite:
                kind = enemy.elite_kind or "guardian"
                if kind == "guardian":
                    sprite = self.elite_sprites[kind][3]
                elif kind == "archon":
                    sprite = self.elite_sprites[kind][1 if enemy.linked_target_ids else 0]
                else:
                    frame = {"charge": 1, "overheat": 2}.get(enemy.elite_state, 0)
                    sprite = self.elite_sprites[kind][frame]
                    sprite = pygame.transform.rotate(sprite, enemy.heading_degrees - 180.0)
                self.screen.blit(sprite, sprite.get_rect(center=enemy.position))
                if kind == "guardian":
                    self.draw_guardian_shields(enemy)
                color = ELITE_COLORS[kind]
                if enemy.position.y > 50:
                    label = self.font_tiny.render(ELITE_NAMES[kind], True, color)
                    self.screen.blit(label, label.get_rect(center=(enemy.position.x, enemy.position.y - 48)))
                self.draw_health_bar(enemy.position, 45, enemy.hp, enemy.max_hp, color, 72)
                continue

            frame_index = int(enemy.animation_time * NORMAL_ENEMY_ANIMATION_FPS) % len(
                self.normal_enemy_sprites
            )
            directions = self.normal_enemy_sprites[frame_index]
            direction_index = round(
                enemy.heading_degrees / (360.0 / len(directions))
            ) % len(directions)
            sprite = directions[direction_index]
            self.screen.blit(sprite, sprite.get_rect(center=enemy.position))

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
            base_color = colors[boss.kind]
            if boss.variant == "commander":
                base_color = ORANGE
            elif boss.variant == "devourer":
                base_color = PURPLE
            color = YELLOW if boss.windup_remaining is not None else base_color

            # Worlds 1–8 use the authored boss sprite sets.  Keep the
            # procedural commander/devourer silhouettes for their later-world
            # variants so this art pass does not alter their mechanics.
            if boss.variant == "standard":
                sprite_frames = self.boss_sprites[boss.kind]
                if boss.windup_remaining is not None:
                    frame_index = 1  # telegraph / charging state
                elif boss.phase >= 2 or boss.hp <= boss.max_hp * 0.5:
                    frame_index = 2  # damaged / enraged state
                else:
                    frame_index = 0  # normal state
                sprite = sprite_frames[frame_index]
                self.screen.blit(sprite, sprite.get_rect(center=boss.position))
                if boss.kind == "big":
                    pygame.draw.circle(self.screen, DARK_RED, boss.position, round(boss.attack_range), 2)
                sprite_size = BOSS_SPRITE_SIZES[boss.kind]
                self.draw_health_bar(
                    boss.position,
                    max(boss.radius + 16, sprite_size // 2 + 12),
                    boss.hp,
                    boss.max_hp,
                    color,
                    max(boss.radius * 3, sprite_size - 8),
                )
                text = self.font_tiny.render(
                    self.boss_name(boss.kind, boss.variant), True, WHITE
                )
                label_pos = boss.position + pygame.Vector2(0, -(sprite_size / 2 + 17))
                self.screen.blit(text, text.get_rect(center=label_pos))
                if boss.windup_remaining is not None:
                    self.blit_text(f"100%斩杀 {max(0, boss.windup_remaining):.1f}", boss.position + pygame.Vector2(-62, sprite_size / 2 + 18), YELLOW, self.font_small)
                    danger = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                    pygame.draw.circle(danger, (255, 40, 50, 45), boss.position, round(boss.attack_range))
                    pygame.draw.circle(danger, (255, 80, 50, 180), boss.position, round(boss.attack_range), 5)
                    self.screen.blit(danger, (0, 0))
                continue

            pygame.draw.circle(self.screen, color, boss.position, boss.radius)
            pygame.draw.circle(self.screen, WHITE, boss.position, boss.radius, 3)
            if boss.variant == "commander":
                pygame.draw.rect(
                    self.screen,
                    WHITE,
                    pygame.Rect(
                        round(boss.position.x - boss.radius * 0.55),
                        round(boss.position.y - boss.radius * 0.55),
                        round(boss.radius * 1.1),
                        round(boss.radius * 1.1),
                    ),
                    4,
                )
                if any(enemy.elite for enemy in self.enemies):
                    pygame.draw.circle(
                        self.screen,
                        CYAN,
                        boss.position,
                        boss.radius + 10,
                        5,
                    )
            elif boss.variant == "devourer":
                for angle in range(0, 360, 120):
                    direction = pygame.Vector2(0, -boss.radius * 0.78).rotate(
                        angle + self.cursor_phase * 45
                    )
                    tip = boss.position + direction
                    pygame.draw.circle(self.screen, YELLOW, tip, 7)
            if boss.kind == "big":
                pygame.draw.circle(self.screen, DARK_RED, boss.position, round(boss.attack_range), 2)
            self.draw_health_bar(boss.position, boss.radius + 16, boss.hp, boss.max_hp, color, boss.radius * 3)
            text = self.font_tiny.render(
                self.boss_name(boss.kind, boss.variant), True, WHITE
            )
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
        glass = pygame.Surface((WIDTH, 64), pygame.SRCALPHA)
        glass.fill(GLASS_TINT)
        pygame.draw.line(glass, GLASS_RIM, (0, 1), (WIDTH, 1), 2)
        self.screen.blit(glass, (0, 0))
        self.draw_neon_line((0, 63), (WIDTH, 63), CYAN, 1, 10)

        self.blit_text("人口", (18, 8), MUTED, self.font_tiny)
        self.blit_text(format_number(self.population), (18, 28), CYAN, self.font_numeric)
        pygame.draw.rect(self.screen, CYAN, (0, 0, 5, 64))
        self.blit_text("金币", (150, 8), MUTED, self.font_tiny)
        self.blit_text(str(self.gold), (150, 28), YELLOW, self.font_numeric)
        self.blit_text("世界", (250, 8), MUTED, self.font_tiny)
        self.blit_text(f"{self.world:02}/{MAX_WORLD:02}", (250, 28), WHITE, self.font_numeric)
        remaining = max(0, math.ceil(world_duration(self.world) - self.elapsed))
        self.blit_text("剩余", (358, 8), MUTED, self.font_tiny)
        self.blit_text(f"{remaining:03}s", (358, 28), RED if remaining <= 30 else WHITE, self.font_numeric)
        self.blit_text("伤害 / 射速", (478, 8), MUTED, self.font_tiny)
        self.blit_text(f"{self.current_damage():.1f} / {self.current_fire_rate():.1f}", (478, 28), WHITE, self.font_numeric)
        self.blit_text("目标 DPS", (680, 8), MUTED, self.font_tiny)
        self.blit_text(format_number(world_dps_threshold(self.world)), (680, 28), YELLOW, self.font_numeric)
        final_boss = next((boss for boss in self.bosses if boss.kind == "big"), None)
        if self.world == 9 and final_boss is not None:
            shield = "护盾开" if any(enemy.elite for enemy in self.enemies) else "护盾关"
            next_event = f"统帅 P{final_boss.phase} {shield}"
        elif self.world == 10 and final_boss is not None:
            next_event = f"吞门者 P{final_boss.phase} 狂暴{final_boss.rage_stacks}/5"
        else:
            next_event = (
                "小Boss 25~30s"
                if self.elapsed < 25
                else "中Boss 60s"
                if self.elapsed < 60
                else "大Boss 90s"
                if self.elapsed < 90
                else "击杀大Boss！"
            )
        self.blit_text("下一威胁", (925, 8), MUTED, self.font_tiny)
        threat_color = RED if remaining <= 30 or (final_boss and final_boss.windup_remaining is not None) else WHITE
        self.blit_text(next_event, (925, 30), threat_color, self.font_tiny)
        if threat_color == RED:
            self.draw_neon_line((917, 7), (917, 55), RED, 2, 8)
        progress = self.elapsed / max(1.0, world_duration(self.world))
        self.draw_step_row(pygame.Rect(1105, 17, 158, 10), progress=progress, danger_from=12)
        self.blit_text("PATTERN", (1105, 36), MUTED, self.font_tiny)
        if self.message_timer > 0:
            surface = self.font_small.render(self.message, True, YELLOW)
            rect = surface.get_rect(center=(WIDTH // 2, HEIGHT - 18)).inflate(20, 10)
            self.draw_ui_panel(rect, fill=(8, 10, 20), rim=YELLOW, radius=4, glass=True)
            self.screen.blit(surface, surface.get_rect(center=rect.center))

    def draw_shop(self) -> None:
        self.draw_menu_background()
        self.blit_text(f"世界 {self.world:02} · 装备编译器", (50, 30), WHITE, self.font_large)
        self.blit_text(f"金币 {self.gold}", (1035, 48), YELLOW, self.font)
        self.blit_text("选择模块写入构筑；强化率 15% · 过载信号概率 5%", (55, 105), CYAN, self.font_small)
        enhance_names = {"population": "+5人口", "fire_rate": "+10%射速", "damage": "+1基础伤害"}
        for index, offer in enumerate(self.shop_offers):
            rect = self.card_rect(index)
            if offer.is_overload:
                self.draw_ui_panel(rect, fill=(42, 8, 28), rim=MAGENTA, radius=7, glass=True)
                self.draw_neon_line((rect.left, rect.top), (rect.right, rect.top), MAGENTA, 3, 14)
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
            self.draw_ui_panel(rect, fill=PANEL, rim=color, radius=7, glass=True)
            self.draw_neon_line((rect.left, rect.top), (rect.right, rect.top), color, 2, 10)
            self.blit_text(card.rarity, (rect.x + 18, rect.y + 16), color, self.font_small)
            price = self.card_purchase_price(card)
            self.blit_text(f"{price} 金币", (rect.right - 88, rect.y + 16), YELLOW, self.font_tiny)
            if offer.enhancement:
                self.blit_text(f"强化：{enhance_names[offer.enhancement]}", (rect.x + 18, rect.y + 48), GREEN, self.font_tiny)
            name = self.font.render(card.name, True, WHITE)
            self.screen.blit(name, name.get_rect(center=(rect.centerx, rect.y + 92)))
            self.draw_wrapped(card.description, pygame.Rect(rect.x + 18, rect.y + 125, rect.width - 36, 75), MUTED)
            self.blit_text("点击购买", (rect.x + 78, rect.bottom - 35), CYAN, self.font_small)

        self.blit_text("永久核心升级（可重复写入）", (910, 105), MUTED, self.font_small)
        attrs = (
            ("默认人口 +2", "population"),
            ("基础伤害 +1", "damage"),
            ("默认射速 +0.8", "fire_rate"),
        )
        for index, (label, key) in enumerate(attrs):
            rect = self.attribute_rect(index)
            price = attribute_price(self.attribute_purchases[key])
            self.draw_ui_panel(rect, fill=PANEL, rim=CYAN, radius=6, glass=True)
            self.blit_text(label, (rect.x + 16, rect.y + 13), WHITE, self.font_small)
            self.blit_text(f"等级 {self.attribute_purchases[key]} | {price} 金币", (rect.x + 16, rect.y + 44), YELLOW, self.font_tiny)

        collection = self.visible_card_collection()
        slot_count = 2 if self.card_page == "overload" else 5
        page_name = "过载卡槽 2槽" if self.card_page == "overload" else "普通卡槽 5槽"
        self.blit_text(f"{page_name}（拖动出售，右键查看详情）", (55, 445), MUTED, self.font_small)
        for index in range(slot_count):
            rect = self.slot_rect(index)
            self.draw_ui_panel(rect, fill=PANEL, rim=GRID, radius=5, glass=True)
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
        self.draw_ui_panel(page_button, fill=PANEL_RAISED, rim=MAGENTA if self.card_page == "normal" else BLUE, radius=5, glass=True)
        page_label = "查看过载卡槽" if self.card_page == "normal" else "查看普通卡槽"
        self.blit_text(page_label, (page_button.x + 20, page_button.y + 12), WHITE, self.font_small)
        sell_rect = self.shop_sell_rect()
        self.draw_ui_panel(sell_rect, fill=(38, 10, 24), rim=RED, radius=5, glass=True)
        sell_label = "将卡牌拖到这里出售（过载牌固定 20 金币）"
        self.blit_text(sell_label, (sell_rect.x + 70, sell_rect.y + 12), WHITE, self.font_small)

        refresh = pygame.Rect(910, 495, 150, 52)
        next_rect = pygame.Rect(1080, 495, 145, 52)
        self.draw_ui_panel(refresh, fill=(9, 18, 48), rim=BLUE, radius=5, glass=True)
        self.draw_ui_panel(next_rect, fill=(8, 42, 37), rim=GREEN, radius=5, glass=True)
        charged = max(0, round(self.apply_stat(self.refresh_cost, "refresh_cost", TARGET_PLAYER)))
        self.blit_text(f"刷新 {charged}金", (refresh.x + 25, refresh.y + 13), WHITE, self.font_small)
        next_label = "挑战世界10" if self.world == 9 else "下一世界"
        self.blit_text(next_label, (next_rect.x + 15, next_rect.y + 13), WHITE, self.font_small)
        if self.world == 9:
            next_population = (
                self.population
                + self.challenge_world_growth_bonus
                + self.challenge_shop_population_bonus
            )
            summary = (
                f"世界10继承：人口 {format_number(next_population)} | "
                f"伤害 {self.default_damage:.1f} | 射速 {self.default_fire_rate:.1f}"
            )
        else:
            summary = (
                f"下世界基础：人口 {self.default_population} | "
                f"伤害 {self.default_damage:.1f} | 射速 {self.default_fire_rate:.1f}"
            )
        self.blit_text(summary, (910, 575), MUTED, self.font_tiny)
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
        overlay.fill((2, 3, 13, 218))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(260, 230, 760, 270)
        self.draw_ui_panel(panel, fill=PANEL, rim=MAGENTA if "失败" in title_text else CYAN, radius=6, glass=True)
        self.draw_neon_line((panel.left, panel.top), (panel.right, panel.top), MAGENTA if "失败" in title_text else CYAN, 3, 18)
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
        overlay.fill((2, 3, 13, 218))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(WIDTH // 2 - 270, 55, 540, 610)
        self.draw_ui_panel(panel, fill=PANEL, rim=CYAN, radius=7, glass=True)
        self.draw_neon_line((panel.left, panel.top), (panel.right, panel.top), MAGENTA, 3, 18)

        title = self.font_large.render("作战链路暂停", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 110)))
        self.draw_section_title("当前火力遥测", (panel.x + 45, 158), MAGENTA)

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

        self.draw_section_title("音频通道", (panel.x + 45, 363), CYAN)
        for kind, label, value in (
            ("sfx", "枪声音效", self.sfx_volume),
            ("bgm", "背景音乐", self.bgm_volume),
        ):
            y = 414 if kind == "sfx" else 464
            self.blit_text(label, (panel.x + 55, y + 6), WHITE, self.font_small)
            minus = self.pause_volume_button_rect(kind, -1)
            plus = self.pause_volume_button_rect(kind, 1)
            self.draw_ui_panel(minus, fill=PANEL_RAISED, rim=CYAN, radius=4)
            self.draw_ui_panel(plus, fill=PANEL_RAISED, rim=CYAN, radius=4)
            self.blit_text("-", (minus.x + 15, minus.y + 3), WHITE, self.font)
            self.blit_text("+", (plus.x + 12, plus.y + 3), WHITE, self.font)
            volume = self.font_small.render(f"{value:.0%}", True, CYAN)
            self.screen.blit(volume, volume.get_rect(center=(WIDTH // 2 + 91, y + 19)))

        self.blit_text("ESC  恢复作战链路", (panel.x + 175, 525), WHITE, self.font_small)
        self.blit_text("F1  开发者诊断终端", (panel.x + 45, 498), CYAN, self.font_small)
        restart = self.pause_restart_rect()
        self.draw_ui_panel(restart, fill=(46, 8, 24), rim=RED, radius=5, glass=True)
        restart_label = self.font.render("重新开始  R", True, WHITE)
        self.screen.blit(restart_label, restart_label.get_rect(center=restart.center))

        main_menu = self.pause_main_menu_rect()
        self.draw_ui_panel(main_menu, fill=PANEL_RAISED, rim=PURPLE, radius=5, glass=True)
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
