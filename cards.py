from __future__ import annotations

import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


ParameterValue: TypeAlias = int | float | bool | str

TARGET_PLAYER = 0
TARGET_NORMAL = 2
TARGET_ELITE = 4
TARGET_BOSS = 8
TARGET_GATE = 21
ENEMY_TARGETS = (TARGET_NORMAL, TARGET_ELITE, TARGET_BOSS)

TARGET_NAMES = {
    TARGET_PLAYER: "玩家",
    TARGET_NORMAL: "小怪",
    TARGET_ELITE: "精英",
    TARGET_BOSS: "Boss",
    TARGET_GATE: "门",
}

CATEGORY_SPECS = {
    "damage": "伤害",
    "fire_control": "火控",
    "survival": "生存",
    "economy": "经济",
    "gate": "门",
    "growth": "成长",
    "utility": "功能",
    "custom": "自定义",
}

TRIGGER_SPECS = {
    "passive": "持续生效",
    "on_shot": "发射时",
    "on_hit": "命中时",
    "on_enemy_kill": "击杀小怪或精英时",
    "on_elite_kill": "击杀精英时",
    "on_boss_kill": "击杀Boss时",
    "on_population_loss": "损失人口时",
    "on_damage_taken": "受到伤害时",
    "on_gate_collect": "拾取门时",
    "on_world_start": "世界开始时",
    "on_world_complete": "世界通关时",
    "on_card_purchase": "购买卡牌时",
    "on_card_sale": "出售卡牌时",
    "interval": "按时间间隔",
    "while_moving": "移动期间",
    "while_still": "静止期间",
    "while_firing": "持续射击期间",
    "while_not_firing": "停火蓄力期间",
}

OPERATOR_SPECS = {
    "add_flat": "固定加减",
    "add_percent": "百分比加减",
    "multiply": "乘算",
    "set": "直接设置",
    "minimum": "设置下限",
    "maximum": "设置上限",
}

STACKING_SPECS = {
    "add": "相加",
    "multiply": "相乘",
    "highest": "取最高",
    "lowest": "取最低",
    "replace": "按优先级替换",
    "independent": "分别触发",
}

STAT_SPECS = {
    "base_damage": "基础伤害",
    "damage_dealt": "玩家造成伤害",
    "damage_taken": "目标受到伤害",
    "health": "目标生命值",
    "fire_rate": "射速",
    "fire_rate_correction": "射速补正",
    "move_speed": "移动速度",
    "bullet_speed": "子弹速度",
    "critical_chance": "暴击率",
    "critical_multiplier": "暴击倍率",
    "projectile_pierce": "子弹穿透",
    "projectile_bounces": "子弹反弹次数",
    "population_loss_reduction": "人口损失减免",
    "contact_avoid_chance": "接触免伤概率",
    "elite_contact_avoid_chance": "精英突破免伤概率",
    "projectile_avoid_chance": "弹丸免伤概率",
    "boss_contact_avoid_chance": "Boss接触免伤概率",
    "elite_spawn_interval": "精英刷新间隔",
    "starting_population": "世界初始人口",
    "elite_kill_population": "精英击杀人口",
    "boss_windup": "Boss蓄力时间",
    "gate_damage": "门伤害",
    "number_gate_reward": "数字门正收益",
    "gold": "金币",
    "population": "人口",
    "boss_gold_reward": "Boss金币奖励",
    "card_price": "购卡价格",
    "card_sale_price": "普通卡牌卖价",
    "refresh_cost": "刷新费用",
    "wholesale_common_sale": "批发普通卡卖价",
    "wholesale_uncommon_sale": "批发罕见卡卖价",
    "wholesale_rare_sale": "批发稀有卡卖价",
    "damage_gate_weight": "伤害门权重",
    "fire_rate_gate_weight": "射速门权重",
    "population_gate_weight": "征召门权重",
    "projectile_pattern": "子弹齐射模式",
    "splash_damage": "溅射伤害",
    "execute_threshold": "处决阈值",
    "moving_counts_as_still": "移动视为静止",
}

STAT_TARGETS = {
    "base_damage": (TARGET_PLAYER,),
    "damage_dealt": (TARGET_PLAYER,),
    "damage_taken": ENEMY_TARGETS,
    "health": (*ENEMY_TARGETS, TARGET_GATE),
    "fire_rate": (TARGET_PLAYER,),
    "fire_rate_correction": (TARGET_PLAYER,),
    "move_speed": (TARGET_PLAYER, *ENEMY_TARGETS),
    "bullet_speed": (TARGET_PLAYER,),
    "critical_chance": (TARGET_PLAYER,),
    "critical_multiplier": (TARGET_PLAYER,),
    "projectile_pierce": (TARGET_PLAYER,),
    "projectile_bounces": (TARGET_PLAYER,),
    "population_loss_reduction": (TARGET_PLAYER,),
    "contact_avoid_chance": (TARGET_NORMAL,),
    "elite_contact_avoid_chance": (TARGET_ELITE,),
    "projectile_avoid_chance": (TARGET_PLAYER,),
    "boss_contact_avoid_chance": (TARGET_BOSS,),
    "elite_spawn_interval": (TARGET_PLAYER,),
    "starting_population": (TARGET_PLAYER,),
    "elite_kill_population": (TARGET_PLAYER,),
    "boss_windup": (TARGET_BOSS,),
    "gate_damage": (TARGET_GATE,),
    "number_gate_reward": (TARGET_GATE,),
    "gold": (TARGET_PLAYER,),
    "population": (TARGET_PLAYER,),
    "boss_gold_reward": (TARGET_PLAYER,),
    "card_price": (TARGET_PLAYER,),
    "card_sale_price": (TARGET_PLAYER,),
    "refresh_cost": (TARGET_PLAYER,),
    "wholesale_common_sale": (TARGET_PLAYER,),
    "wholesale_uncommon_sale": (TARGET_PLAYER,),
    "wholesale_rare_sale": (TARGET_PLAYER,),
    "damage_gate_weight": (TARGET_GATE,),
    "fire_rate_gate_weight": (TARGET_GATE,),
    "population_gate_weight": (TARGET_GATE,),
    "projectile_pattern": (TARGET_PLAYER,),
    "splash_damage": (TARGET_NORMAL, TARGET_ELITE),
    "execute_threshold": (TARGET_NORMAL, TARGET_ELITE),
    "moving_counts_as_still": (TARGET_PLAYER,),
}

ACTION_SPECS = {
    "modify_stat": "修改属性",
    "grant_resource": "给予资源",
    "periodic_resource": "定时给予资源",
    "projectile_pattern": "改变射击模式",
    "splash_damage": "造成溅射伤害",
    "execute": "处决目标",
    "change_weight": "修改生成权重",
    "growth_modifier": "跨世界成长",
    "set_rule": "设置规则",
}

ACTION_STATS = {
    "modify_stat": tuple(
        key
        for key in STAT_SPECS
        if key
        not in {
            "gold",
            "population",
            "damage_gate_weight",
            "fire_rate_gate_weight",
            "population_gate_weight",
            "projectile_pattern",
            "splash_damage",
            "execute_threshold",
            "moving_counts_as_still",
        }
    ),
    "grant_resource": ("gold", "population"),
    "periodic_resource": ("gold", "population"),
    "projectile_pattern": ("projectile_pattern",),
    "splash_damage": ("splash_damage",),
    "execute": ("execute_threshold",),
    "change_weight": ("damage_gate_weight", "fire_rate_gate_weight", "population_gate_weight"),
    "growth_modifier": (
        "base_damage",
        "damage_dealt",
        "damage_taken",
        "fire_rate",
        "starting_population",
        "elite_kill_population",
        "gate_damage",
    ),
    "set_rule": ("moving_counts_as_still",),
}

EVENT_TRIGGERS = (
    "on_shot",
    "on_hit",
    "on_enemy_kill",
    "on_elite_kill",
    "on_boss_kill",
    "on_population_loss",
    "on_damage_taken",
    "on_gate_collect",
    "on_world_start",
    "on_world_complete",
    "on_card_purchase",
    "on_card_sale",
)

ACTION_TRIGGERS = {
    "modify_stat": (
        "passive",
        "while_moving",
        "while_still",
        "while_firing",
        "while_not_firing",
        "interval",
        *EVENT_TRIGGERS,
    ),
    "grant_resource": EVENT_TRIGGERS,
    "periodic_resource": ("interval",),
    "projectile_pattern": ("passive",),
    "splash_damage": ("on_hit",),
    "execute": ("on_hit",),
    "change_weight": ("passive",),
    "growth_modifier": ("passive",),
    "set_rule": ("passive",),
}

ACTION_PARAMETER_DEFAULTS: dict[str, dict[str, ParameterValue]] = {
    "modify_stat": {"value": 0.0},
    "grant_resource": {"value": 0},
    "periodic_resource": {"value": 1, "interval": 30.0},
    "projectile_pattern": {"count": 2, "spread": 10.0, "damage_scale": 0.65},
    "splash_damage": {"value": 0.25, "radius": 95.0},
    "execute": {"threshold": 0.5},
    "change_weight": {"value": 1.0},
    "growth_modifier": {"value": 0.05},
    "set_rule": {"enabled": True},
}

RARITIES = ("普通", "罕见", "稀有")
KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
PARAMETER_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
NUMERIC_RUNTIME_PARAMETERS = {
    "value",
    "chance",
    "duration",
    "interval",
    "cooldown",
    "threshold",
    "cap",
    "condition_value",
    "step",
    "value_per_step",
    "value_per_second",
    "triggers_per_stack",
    "value_per_stack",
    "stacks_per_trigger",
    "max_stacks",
    "delay",
    "initial_value",
    "value_per_interval",
    "per_world",
    "linger",
    "radius",
    "trigger_target",
    "count",
    "spread",
    "damage_scale",
}
BOOLEAN_RUNTIME_PARAMETERS = {"clear_on_move", "clear_on_world", "global_effect", "enabled"}
TEXT_RUNTIME_PARAMETERS = {"condition_stat", "comparison", "scale_stat", "boss_kind", "message"}


@dataclass(frozen=True)
class EffectTargets:
    player: bool = False
    enemies: tuple[int, ...] = ()
    gate: bool = False

    def includes(self, target: int) -> bool:
        if target == TARGET_PLAYER:
            return self.player
        if target == TARGET_GATE:
            return self.gate
        return target in self.enemies


@dataclass(frozen=True)
class CardEffect:
    targets: EffectTargets
    trigger: str
    action: str
    stat: str
    operator: str
    stacking: str
    exclusive_group: str
    priority: int
    parameters: dict[str, ParameterValue]


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    description: str
    rarity: str
    price: int
    category: str
    effects: tuple[CardEffect, ...]


def default_cards_path() -> Path:
    override = os.environ.get("DOUBLE_FRONT_CARDS")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).resolve().parent / "data" / "cards.json"
        if external.exists():
            return external
    return Path(__file__).resolve().parent / "data" / "cards.json"


def action_defaults(action: str) -> dict[str, ParameterValue]:
    try:
        return dict(ACTION_PARAMETER_DEFAULTS[action])
    except KeyError as error:
        raise ValueError(f"unknown effect action: {action}") from error


def _targets(*enemies: int, player: bool = False, gate: bool = False) -> EffectTargets:
    return EffectTargets(player, tuple(enemies), gate)


def _effect(
    targets: EffectTargets,
    trigger: str,
    action: str,
    stat: str,
    operator: str = "add_flat",
    stacking: str = "add",
    exclusive_group: str = "",
    priority: int = 0,
    **parameters: ParameterValue,
) -> CardEffect:
    return CardEffect(targets, trigger, action, stat, operator, stacking, exclusive_group, priority, parameters)


def migrate_legacy_effect(effect: str, p: dict[str, ParameterValue]) -> tuple[str, tuple[CardEffect, ...]]:
    player = _targets(player=True)
    gate = _targets(gate=True)
    normal = _targets(TARGET_NORMAL)
    elite = _targets(TARGET_ELITE)
    boss = _targets(TARGET_BOSS)
    enemies = _targets(TARGET_NORMAL, TARGET_ELITE)

    if effect == "none":
        return "custom", ()
    if effect == "damage":
        return "damage", (_effect(player, "passive", "modify_stat", "base_damage", value=p["amount"]),)
    if effect == "fire_rate":
        return "fire_control", (_effect(player, "passive", "modify_stat", "fire_rate", "add_percent", value=p["bonus"]),)
    if effect == "move_speed":
        return "survival", (_effect(player, "passive", "modify_stat", "move_speed", "add_percent", value=p["bonus"]),)
    if effect == "armor":
        return "survival", (_effect(player, "passive", "modify_stat", "population_loss_reduction", value=p["reduction"]),)
    if effect == "recruit":
        return "survival", (_effect(player, "passive", "modify_stat", "starting_population", value=p["amount"]),)
    if effect == "low_population":
        return "damage", (
            _effect(
                player,
                "passive",
                "modify_stat",
                "damage_dealt",
                "add_percent",
                value=p["bonus"],
                condition_stat="population",
                comparison="less",
                condition_value=p["threshold"],
            ),
        )
    if effect == "high_population":
        return "fire_control", (
            _effect(
                player,
                "passive",
                "modify_stat",
                "fire_rate",
                "add_percent",
                value=p["bonus"],
                condition_stat="population",
                comparison="greater_equal",
                condition_value=p["threshold"],
            ),
        )
    if effect == "fast_bullet":
        return "fire_control", (_effect(player, "passive", "modify_stat", "bullet_speed", "add_percent", value=p["bonus"]),)
    if effect == "ramp_fire":
        return "fire_control", (
            _effect(
                player,
                "while_firing",
                "modify_stat",
                "fire_rate",
                "add_percent",
                value=0.0,
                value_per_second=p["bonus_per_second"],
                cap=p["max_bonus"],
            ),
        )
    if effect == "warning":
        return "utility", (_effect(boss, "passive", "modify_stat", "boss_windup", value=p["seconds"]),)
    if effect == "gate_damage":
        return "gate", (_effect(gate, "passive", "modify_stat", "gate_damage", "add_percent", value=p["bonus"]),)
    if effect == "soft_contact":
        return "survival", (_effect(normal, "passive", "modify_stat", "contact_avoid_chance", value=p["chance"]),)
    if effect == "elite_damage":
        return "damage", (_effect(elite, "passive", "modify_stat", "damage_taken", "add_percent", value=p["bonus"]),)
    if effect == "runner":
        return "damage", (_effect(player, "while_moving", "modify_stat", "damage_dealt", "add_percent", value=p["bonus"]),)
    if effect == "population_fire":
        return "fire_control", (
            _effect(
                player,
                "passive",
                "modify_stat",
                "fire_rate",
                "add_percent",
                value=0.0,
                scale_stat="population",
                step=p["population_step"],
                value_per_step=p["bonus_per_step"],
                cap=p["max_bonus"],
            ),
        )
    if effect == "loss_rage":
        return "damage", (
            _effect(
                player,
                "on_population_loss",
                "modify_stat",
                "damage_dealt",
                "add_percent",
                value=p["bonus"],
                duration=p["duration"],
            ),
        )
    if effect == "medicine":
        return "survival", (
            _effect(player, "interval", "periodic_resource", "population", value=p["amount"], interval=p["interval"]),
        )
    if effect == "kill_shot":
        return "fire_control", (
            _effect(
                player,
                "on_enemy_kill",
                "modify_stat",
                "fire_rate",
                "add_percent",
                value=0.0,
                triggers_per_stack=p["kills_per_stack"],
                value_per_stack=p["bonus_per_stack"],
            ),
        )
    if effect == "boss_damage":
        return "damage", (_effect(boss, "passive", "modify_stat", "damage_taken", "add_percent", value=p["bonus"]),)
    if effect == "vampire":
        return "survival", (_effect(player, "on_enemy_kill", "grant_resource", "population", value=p["amount"]),)
    if effect == "rich_damage":
        return "damage", (
            _effect(
                player,
                "passive",
                "modify_stat",
                "damage_dealt",
                "add_percent",
                value=0.0,
                scale_stat="gold",
                step=p["gold_step"],
                value_per_step=p["bonus_per_step"],
            ),
        )
    if effect == "still_shot":
        return "damage", (
            _effect(
                player,
                "while_still",
                "modify_stat",
                "damage_dealt",
                "add_percent",
                value=0.0,
                delay=p["delay"],
                initial_value=p["initial_bonus"],
                interval=p["interval"],
                value_per_interval=p["bonus_per_interval"],
            ),
        )
    if effect == "splash":
        return "fire_control", (
            _effect(enemies, "on_hit", "splash_damage", "splash_damage", value=p["damage_ratio"], radius=p["radius"]),
        )
    if effect == "overclock":
        return "fire_control", (
            _effect(player, "passive", "modify_stat", "fire_rate", "add_percent", value=p["fire_rate_bonus"]),
            _effect(player, "passive", "modify_stat", "damage_dealt", "add_percent", value=-float(p["damage_penalty"])),
        )
    if effect == "gate_master":
        return "gate", (_effect(gate, "passive", "modify_stat", "number_gate_reward", "add_percent", value=p["bonus"]),)
    if effect == "execute":
        return "damage", (_effect(elite, "on_hit", "execute", "execute_threshold", threshold=p["threshold"]),)
    if effect == "pierce":
        return "fire_control", (_effect(player, "passive", "modify_stat", "projectile_pierce", value=p["count"]),)
    if effect == "decapitate":
        return "damage", (
            _effect(boss, "passive", "modify_stat", "damage_taken", "add_percent", value=p["bonus"], boss_kind="big"),
        )
    if effect == "resonance":
        return "damage", (
            _effect(enemies, "on_hit", "splash_damage", "splash_damage", value=p["damage_ratio"], radius=0.0, global_effect=True, trigger_target=TARGET_BOSS),
        )
    if effect == "dividend":
        return "economy", (
            _effect(player, "on_boss_kill", "grant_resource", "gold", value=p["gold"]),
            _effect(player, "on_boss_kill", "grant_resource", "population", value=p["population"]),
        )
    if effect == "growth_damage":
        return "growth", (_effect(player, "passive", "growth_modifier", "base_damage", value=p["per_world"]),)
    if effect == "growth_fire":
        return "growth", (_effect(player, "passive", "growth_modifier", "fire_rate", "add_percent", value=p["per_world"]),)
    if effect == "growth_population":
        return "growth", (_effect(player, "passive", "growth_modifier", "starting_population", value=p["per_world"]),)
    if effect == "growth_boss":
        return "growth", (_effect(boss, "passive", "growth_modifier", "damage_taken", "add_percent", value=p["per_world"]),)
    if effect == "growth_gate":
        return "growth", (_effect(gate, "passive", "growth_modifier", "gate_damage", "add_percent", value=p["per_world"]),)
    if effect == "growth_arsenal":
        return "growth", (
            _effect(player, "passive", "growth_modifier", "damage_dealt", "add_percent", value=p["damage_per_world"]),
            _effect(player, "passive", "growth_modifier", "fire_rate", "add_percent", value=p["fire_rate_per_world"]),
        )
    if effect == "growth_recovery":
        return "growth", (
            _effect(player, "passive", "growth_modifier", "starting_population", value=p["population_per_world"]),
            _effect(player, "on_elite_kill", "grant_resource", "population", value=0, per_world=p["elite_per_world"]),
        )
    if effect == "growth_core":
        return "growth", (
            _effect(player, "passive", "growth_modifier", "damage_dealt", "add_percent", value=p["damage_per_world"]),
            _effect(player, "passive", "growth_modifier", "fire_rate", "add_percent", value=p["fire_rate_per_world"]),
            _effect(player, "passive", "growth_modifier", "starting_population", value=p["population_per_world"]),
        )
    if effect == "boss_bounty":
        return "economy", (_effect(player, "on_boss_kill", "grant_resource", "gold", value=p["gold"]),)
    if effect == "special_profit":
        return "economy", (_effect(player, "on_gate_collect", "grant_resource", "gold", value=p["gold"]),)
    if effect == "saving":
        return "economy", (
            _effect(player, "on_world_complete", "grant_resource", "gold", "add_percent", value=p["rate"], cap=p["max_gold"]),
        )
    if effect == "refresh_deal":
        return "economy", (_effect(player, "passive", "modify_stat", "refresh_cost", value=-float(p["discount"])),)
    if effect == "card_deal":
        return "economy", (
            _effect(player, "passive", "modify_stat", "card_price", value=-float(p["discount"])),
            _effect(player, "passive", "modify_stat", "wholesale_common_sale", "set", stacking="replace", value=p["common_sale"]),
            _effect(player, "passive", "modify_stat", "wholesale_uncommon_sale", "set", stacking="replace", value=p["uncommon_sale"]),
            _effect(player, "passive", "modify_stat", "wholesale_rare_sale", "set", stacking="replace", value=p["rare_sale"]),
        )
    if effect in {"double_shot", "triple_shot", "shotgun"}:
        priority = {"double_shot": 1, "triple_shot": 2, "shotgun": 3}[effect]
        return "fire_control", (
            _effect(
                player,
                "passive",
                "projectile_pattern",
                "projectile_pattern",
                stacking="replace",
                exclusive_group="volley",
                priority=priority,
                count=p["projectiles"],
                spread=p["spread"],
                damage_scale=p["damage_scale"],
            ),
        )
    if effect == "recruit_gate_bias":
        return "gate", (
            _effect(gate, "passive", "change_weight", "damage_gate_weight", value=p["damage_weight"]),
            _effect(gate, "passive", "change_weight", "fire_rate_gate_weight", value=p["fire_rate_weight"]),
            _effect(gate, "passive", "change_weight", "population_gate_weight", value=p["population_weight"]),
        )
    if effect == "critical_focus":
        return "damage", (_effect(player, "passive", "modify_stat", "critical_chance", value=p["chance"]),)
    if effect == "composure":
        shared = {
            "delay": p["charge_interval"],
            "interval": p["charge_interval"],
            "linger": p["linger"],
        }
        return "damage", (
            _effect(
                player,
                "while_not_firing",
                "modify_stat",
                "damage_dealt",
                "add_percent",
                value=0.0,
                initial_value=p["initial_damage_bonus"],
                value_per_interval=p["damage_bonus_per_level"],
                **shared,
            ),
            _effect(
                gate,
                "while_not_firing",
                "modify_stat",
                "gate_damage",
                "add_percent",
                value=0.0,
                initial_value=p["initial_gate_bonus"],
                value_per_interval=p["gate_bonus_per_level"],
                **shared,
            ),
        )
    if effect == "phase_move":
        return "utility", (_effect(player, "passive", "set_rule", "moving_counts_as_still", "set", enabled=True),)
    if effect == "critical_chance":
        return "damage", (_effect(player, "passive", "modify_stat", "critical_chance", value=p["chance"]),)
    if effect == "critical_power":
        return "damage", (_effect(player, "passive", "modify_stat", "critical_multiplier", value=p["damage_bonus"]),)
    if effect == "pierce_plus":
        return "fire_control", (_effect(player, "passive", "modify_stat", "projectile_pierce", value=p["count"]),)
    raise ValueError(f"unknown legacy card effect: {effect}")


def validate_effect(effect: CardEffect, card_key: str, index: int) -> None:
    location = f"effect {index} of {card_key}"
    if effect.trigger not in TRIGGER_SPECS:
        raise ValueError(f"unknown trigger in {location}: {effect.trigger}")
    if effect.action not in ACTION_SPECS:
        raise ValueError(f"unknown action in {location}: {effect.action}")
    if effect.trigger not in ACTION_TRIGGERS[effect.action]:
        raise ValueError(f"trigger {effect.trigger} is not valid for action {effect.action} in {location}")
    if effect.stat not in ACTION_STATS[effect.action]:
        raise ValueError(f"stat {effect.stat} is not valid for action {effect.action} in {location}")
    if effect.operator not in OPERATOR_SPECS:
        raise ValueError(f"unknown operator in {location}: {effect.operator}")
    if effect.stacking not in STACKING_SPECS:
        raise ValueError(f"unknown stacking rule in {location}: {effect.stacking}")
    if isinstance(effect.priority, bool) or not isinstance(effect.priority, int):
        raise ValueError(f"priority must be an integer in {location}")
    if not effect.targets.player and not effect.targets.gate and not effect.targets.enemies:
        raise ValueError(f"{location} must have at least one target")
    if any(target not in ENEMY_TARGETS for target in effect.targets.enemies):
        raise ValueError(f"invalid enemy target in {location}")
    if len(set(effect.targets.enemies)) != len(effect.targets.enemies):
        raise ValueError(f"duplicate enemy target in {location}")
    selected_targets = {
        *effect.targets.enemies,
        *([TARGET_PLAYER] if effect.targets.player else []),
        *([TARGET_GATE] if effect.targets.gate else []),
    }
    unsupported_targets = selected_targets - set(STAT_TARGETS[effect.stat])
    if unsupported_targets:
        names = ", ".join(TARGET_NAMES[target] for target in sorted(unsupported_targets))
        raise ValueError(f"stat {effect.stat} does not support targets {names} in {location}")

    required = set(ACTION_PARAMETER_DEFAULTS[effect.action])
    missing = required - set(effect.parameters)
    if missing:
        raise ValueError(f"missing parameters in {location}: {', '.join(sorted(missing))}")
    for key, value in effect.parameters.items():
        if not PARAMETER_KEY_PATTERN.fullmatch(key):
            raise ValueError(f"invalid parameter key in {location}: {key!r}")
        if key in NUMERIC_RUNTIME_PARAMETERS and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError(f"runtime parameter {key} must be numeric in {location}")
        if key in BOOLEAN_RUNTIME_PARAMETERS and not isinstance(value, bool):
            raise ValueError(f"runtime parameter {key} must be boolean in {location}")
        if key in TEXT_RUNTIME_PARAMETERS and not isinstance(value, str):
            raise ValueError(f"runtime parameter {key} must be text in {location}")
        if isinstance(value, str) or isinstance(value, bool):
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"parameter {key} must be a finite number, boolean or text in {location}")
    if "chance" in effect.parameters and not 0 <= float(effect.parameters["chance"]) <= 1:
        raise ValueError(f"chance must be from 0 to 1 in {location}")
    for key in ("cooldown", "duration", "max_stacks", "stacks_per_trigger", "delay", "linger", "radius"):
        if key in effect.parameters and float(effect.parameters[key]) < 0:
            raise ValueError(f"{key} must be non-negative in {location}")
    for key in ("interval", "step", "triggers_per_stack"):
        if key in effect.parameters and float(effect.parameters[key]) <= 0:
            raise ValueError(f"{key} must be positive in {location}")
    if "trigger_target" in effect.parameters and int(effect.parameters["trigger_target"]) not in TARGET_NAMES:
        raise ValueError(f"trigger_target is invalid in {location}")
    if "trigger_target" in effect.parameters and int(effect.parameters["trigger_target"]) != effect.parameters["trigger_target"]:
        raise ValueError(f"trigger_target must be an integer in {location}")
    if effect.parameters.get("comparison") not in {None, "less", "less_equal", "equal", "greater_equal", "greater"}:
        raise ValueError(f"comparison is invalid in {location}")
    if effect.parameters.get("condition_stat") not in {None, "population", "gold", "kills"}:
        raise ValueError(f"condition_stat is invalid in {location}")
    if effect.parameters.get("scale_stat") not in {None, "population", "gold", "kills"}:
        raise ValueError(f"scale_stat is invalid in {location}")
    if effect.parameters.get("boss_kind") not in {None, "small", "medium", "big"}:
        raise ValueError(f"boss_kind is invalid in {location}")
    if effect.action == "periodic_resource" and float(effect.parameters["interval"]) <= 0:
        raise ValueError(f"interval must be positive in {location}")
    if effect.trigger == "interval" and (
        "interval" not in effect.parameters or float(effect.parameters["interval"]) <= 0
    ):
        raise ValueError(f"interval trigger requires a positive interval in {location}")
    if effect.action == "modify_stat" and effect.trigger in EVENT_TRIGGERS and not (
        "duration" in effect.parameters
        or "triggers_per_stack" in effect.parameters
        or "stacks_per_trigger" in effect.parameters
    ):
        raise ValueError(f"event stat modifier requires duration or triggers_per_stack in {location}")
    if effect.action == "projectile_pattern":
        count = effect.parameters["count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 64:
            raise ValueError(f"projectile count must be an integer from 1 to 64 in {location}")
    if effect.action == "execute" and not 0 <= float(effect.parameters["threshold"]) <= 1:
        raise ValueError(f"execute threshold must be from 0 to 1 in {location}")


def validate_card(card: Card, index: int | None = None) -> None:
    location = f" at index {index}" if index is not None else ""
    if not KEY_PATTERN.fullmatch(card.key):
        raise ValueError(f"invalid card key{location}: {card.key!r}")
    if not card.name.strip() or not card.description.strip():
        raise ValueError(f"card{location} must have a name and description")
    if card.rarity not in RARITIES:
        raise ValueError(f"invalid rarity for {card.key}: {card.rarity}")
    if isinstance(card.price, bool) or not isinstance(card.price, int) or card.price < 0:
        raise ValueError(f"price must be a non-negative integer for {card.key}")
    if card.category not in CATEGORY_SPECS:
        raise ValueError(f"unknown category for {card.key}: {card.category}")
    for effect_index, effect in enumerate(card.effects):
        validate_effect(effect, card.key, effect_index)


def _load_targets(record: object, location: str) -> EffectTargets:
    if not isinstance(record, dict):
        raise ValueError(f"targets must be an object in {location}")
    enemies = record.get("enemies", [])
    if not isinstance(enemies, list):
        raise ValueError(f"target enemies must be an array in {location}")
    return EffectTargets(bool(record.get("player", False)), tuple(enemies), bool(record.get("gate", False)))


def _load_effect(record: object, card_key: str, index: int) -> CardEffect:
    if not isinstance(record, dict):
        raise ValueError(f"effect {index} of {card_key} must be an object")
    location = f"effect {index} of {card_key}"
    try:
        effect = CardEffect(
            targets=_load_targets(record["targets"], location),
            trigger=str(record["trigger"]),
            action=str(record["action"]),
            stat=str(record["stat"]),
            operator=str(record.get("operator", "add_flat")),
            stacking=str(record.get("stacking", "add")),
            exclusive_group=str(record.get("exclusive_group", "")),
            priority=record.get("priority", 0),
            parameters=dict(record["parameters"]),
        )
    except KeyError as error:
        raise ValueError(f"{location} is missing {error.args[0]}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"{location} contains invalid values") from error
    validate_effect(effect, card_key, index)
    return effect


def load_cards(path: Path | None = None) -> tuple[Card, ...]:
    source = path or default_cards_path()
    with source.open("r", encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list):
        raise ValueError("cards.json must contain a JSON array")

    cards: list[Card] = []
    keys: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"card at index {index} must be an object")
        try:
            if "effects" in record:
                category = str(record["category"])
                effects = tuple(_load_effect(item, str(record["key"]), effect_index) for effect_index, item in enumerate(record["effects"]))
            else:
                category, effects = migrate_legacy_effect(str(record["effect"]), dict(record["parameters"]))
            card = Card(
                key=str(record["key"]).strip(),
                name=str(record["name"]).strip(),
                description=str(record["description"]).strip(),
                rarity=str(record["rarity"]),
                price=record["price"],
                category=category,
                effects=effects,
            )
        except KeyError as error:
            raise ValueError(f"card at index {index} is missing {error.args[0]}") from error
        except (TypeError, ValueError) as error:
            raise ValueError(f"card at index {index} contains invalid values: {error}") from error
        validate_card(card, index)
        if card.key in keys:
            raise ValueError(f"duplicate card key: {card.key}")
        keys.add(card.key)
        cards.append(card)
    return tuple(cards)


def _effect_record(effect: CardEffect) -> dict[str, object]:
    return {
        "targets": {
            "player": effect.targets.player,
            "enemies": list(effect.targets.enemies),
            "gate": effect.targets.gate,
        },
        "trigger": effect.trigger,
        "action": effect.action,
        "stat": effect.stat,
        "operator": effect.operator,
        "stacking": effect.stacking,
        "exclusive_group": effect.exclusive_group,
        "priority": effect.priority,
        "parameters": effect.parameters,
    }


def save_cards(cards: list[Card] | tuple[Card, ...], path: Path | None = None) -> None:
    destination = path or default_cards_path()
    keys: set[str] = set()
    records = []
    for index, card in enumerate(cards):
        validate_card(card, index)
        if card.key in keys:
            raise ValueError(f"duplicate card key: {card.key}")
        keys.add(card.key)
        records.append(
            {
                "key": card.key,
                "name": card.name,
                "description": card.description,
                "rarity": card.rarity,
                "price": card.price,
                "category": card.category,
                "effects": [_effect_record(effect) for effect in card.effects],
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(destination)


CARDS = load_cards()
CARD_BY_KEY = {card.key: card for card in CARDS}
