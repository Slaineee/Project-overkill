from __future__ import annotations

import math


def shot_damage(
    population: int,
    base_damage: float,
    damage_bonus: float = 0.0,
) -> float:
    """Return one projectile's damage using additive damage bonuses."""
    raw_damage = max(0, population) * max(0.0, base_damage)
    return raw_damage * max(0.0, 1.0 + damage_bonus)


def gate_shot_damage(
    population: int,
    base_damage: float,
    damage_bonus: float = 0.0,
) -> float:
    """Keep gate economy on the original soft-capped population curve."""
    population = max(0, population)
    effective_population = (
        float(population)
        if population <= 100
        else 100.0 + (population - 100) ** 0.7
    )
    raw_damage = max(0.0, base_damage) * (0.4 + 0.03 * effective_population)
    return raw_damage * max(0.0, 1.0 + damage_bonus)


def scaled_health(base_health: float, world_level: int, growth: float = 1.18) -> float:
    return base_health * growth ** max(0, world_level - 1)


def scaled_speed(base_speed: float, boss_kills: int) -> float:
    kills = max(0, boss_kills)
    return base_speed * (1.0 + 0.8 * kills / (kills + 10))


def elite_population_loss(population: int, world_level: int) -> int:
    fixed_loss = math.ceil(10 * 1.18 ** max(0, world_level - 1))
    percentage_loss = math.ceil(max(0, population) * 0.12)
    return max(fixed_loss, percentage_loss)


def gate_steps(damage: float, durability_per_step: float = 10.0) -> int:
    if damage <= 0 or durability_per_step <= 0:
        return 0
    return max(1, int(damage / durability_per_step))


def gate_initial_value(current_damage: float, multiplier: float) -> int:
    """Scale a gate's starting debt with the player's current shot output."""
    if current_damage <= 0:
        return -1
    return -max(1, math.ceil(current_damage * multiplier))


def boss_gold_reward(base_reward: int, current_gold: int) -> int:
    return max(0, base_reward) + max(0, current_gold) // 5


def attribute_price(purchases: int, base_price: int = 4) -> int:
    return math.ceil(base_price * 1.45 ** max(0, purchases))


WORLD_MULTIPLIERS = (1.0, 1.25, 1.5, 1.8, 2.2, 2.7, 3.3, 4.0)


def world_multiplier(world: int) -> float:
    index = min(8, max(1, world)) - 1
    return WORLD_MULTIPLIERS[index]


WORLD_DPS_THRESHOLDS = (
    45_000,
    80_000,
    300_000,
    450_000,
    1_000_000,
    2_000_000,
    4_000_000,
    8_000_000,
)

WORLD_TARGET_HEALTH = (
    {"normal": 20, "elite": 600, "special": 21_093.75, "small": 84_375, "medium": 168_750, "big": 675_000},
    {"normal": 30, "elite": 900, "special": 37_500, "small": 150_000, "medium": 300_000, "big": 1_200_000},
    {"normal": 200, "elite": 6_000, "special": 140_625, "small": 562_500, "medium": 1_125_000, "big": 4_500_000},
    {"normal": 400, "elite": 12_000, "special": 210_937.5, "small": 843_750, "medium": 1_687_500, "big": 6_750_000},
    {"normal": 600, "elite": 18_000, "special": 468_750, "small": 1_875_000, "medium": 3_750_000, "big": 15_000_000},
    {"normal": 1_000, "elite": 30_000, "special": 937_500, "small": 3_750_000, "medium": 7_500_000, "big": 30_000_000},
    {"normal": 1_800, "elite": 54_000, "special": 1_875_000, "small": 7_500_000, "medium": 15_000_000, "big": 60_000_000},
    {"normal": 3_000, "elite": 90_000, "special": 3_750_000, "small": 15_000_000, "medium": 30_000_000, "big": 120_000_000},
)


def world_dps_threshold(world: int) -> int:
    index = min(8, max(1, world)) - 1
    return WORLD_DPS_THRESHOLDS[index]


def world_target_health(world: int, target: str) -> float:
    index = min(8, max(1, world)) - 1
    try:
        return float(WORLD_TARGET_HEALTH[index][target])
    except KeyError as error:
        raise ValueError(f"unknown target type: {target}") from error


def boss_windup_move_factor(world: int) -> float:
    """Scale windup movement from 10% in world 1 to 50% in world 8."""
    clamped_world = min(8, max(1, world))
    return 0.10 + (clamped_world - 1) * (0.40 / 7)


def execution_ready(current: float, maximum: float, threshold: float) -> bool:
    """Return whether a living target is within an execution threshold."""
    if maximum <= 0 or current <= 0:
        return False
    return current / maximum <= max(0.0, min(1.0, threshold))


def format_number(value: float) -> str:
    absolute = abs(value)
    if absolute < 10_000:
        return f"{int(value):,}"
    if absolute < 100_000_000:
        return f"{value / 10_000:.1f}w"
    return f"{value:.2e}"
