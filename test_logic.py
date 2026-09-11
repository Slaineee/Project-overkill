import unittest

from cards import CARDS
from logic import (
    attribute_price,
    boss_windup_move_factor,
    boss_gold_reward,
    elite_population_loss,
    execution_ready,
    format_number,
    gate_initial_value,
    gate_shot_damage,
    gate_steps,
    scaled_health,
    scaled_speed,
    shot_damage,
    world_dps_threshold,
    world_boss_spawn_time,
    world_duration,
    world_multiplier,
    world_target_health,
)


class LogicTests(unittest.TestCase):
    def test_expanded_card_pool(self) -> None:
        counts = {rarity: sum(card.rarity == rarity for card in CARDS) for rarity in ("普通", "罕见", "稀有")}
        self.assertGreater(len(CARDS), 0)
        self.assertEqual(sum(counts.values()), len(CARDS))
        self.assertEqual(len({card.key for card in CARDS}), len(CARDS))

    def test_shot_damage_scales_linearly_with_population(self) -> None:
        self.assertEqual(shot_damage(0, 10), 0)
        self.assertEqual(shot_damage(1, 10), 10)
        self.assertEqual(shot_damage(20, 10), 200)

    def test_damage_bonuses_are_additive(self) -> None:
        self.assertEqual(shot_damage(20, 10, 0.12 + 0.15), 254)

    def test_gate_damage_keeps_original_population_curve(self) -> None:
        self.assertAlmostEqual(gate_shot_damage(1, 10), 4.3)
        self.assertEqual(gate_shot_damage(20, 10), 10)
        self.assertEqual(gate_shot_damage(100, 10), 34)
        self.assertLess(gate_shot_damage(200, 10), 50)

    def test_world_scaling(self) -> None:
        self.assertEqual(scaled_health(100, 1), 100)
        self.assertAlmostEqual(scaled_health(100, 2), 118)
        self.assertLess(scaled_speed(100, 1000), 180)

    def test_worlds_use_fixed_dps_thresholds_and_health(self) -> None:
        self.assertEqual(world_dps_threshold(1), 45_000)
        self.assertEqual(world_dps_threshold(5), 1_000_000)
        self.assertEqual(world_dps_threshold(8), 8_000_000)
        self.assertEqual(world_dps_threshold(9), 300_000_000)
        self.assertEqual(world_dps_threshold(10), 900_000_000)
        self.assertEqual(world_target_health(1, "big"), 675_000)
        self.assertEqual(world_target_health(8, "big"), 120_000_000)
        self.assertEqual(world_target_health(9, "big"), 18_000_000_000)
        self.assertEqual(world_target_health(10, "big"), 72_000_000_000)
        self.assertEqual(world_target_health(9, "normal"), 5_000)
        self.assertEqual(world_target_health(10, "elite"), 240_000)
        for world in range(1, 11):
            big_health = world_target_health(world, "big")
            self.assertEqual(world_target_health(world, "small"), big_health / 8)
            self.assertEqual(world_target_health(world, "medium"), big_health / 4)
            self.assertEqual(world_target_health(world, "special"), big_health / 32)

    def test_boss_windup_movement_pressure_scales_by_world(self) -> None:
        self.assertAlmostEqual(boss_windup_move_factor(1), 0.10)
        self.assertAlmostEqual(boss_windup_move_factor(8), 0.50)
        self.assertAlmostEqual(boss_windup_move_factor(9), 0.55)
        self.assertAlmostEqual(boss_windup_move_factor(10), 0.60)
        self.assertAlmostEqual(boss_windup_move_factor(4), 0.10 + 3 * 0.40 / 7)

    def test_final_world_timing(self) -> None:
        self.assertEqual(world_duration(8), 120.0)
        self.assertEqual(world_duration(9), 90.0)
        self.assertEqual(world_duration(10), 90.0)
        self.assertEqual(world_boss_spawn_time(8), 90.0)
        self.assertEqual(world_boss_spawn_time(9), 0.0)

    def test_execution_uses_current_health_percentage(self) -> None:
        self.assertTrue(execution_ready(50, 100, 0.50))
        self.assertFalse(execution_ready(51, 100, 0.50))
        self.assertTrue(execution_ready(100, 100, 1.0))

    def test_elite_loss_uses_larger_value(self) -> None:
        self.assertEqual(elite_population_loss(20, 1), 10)
        self.assertEqual(elite_population_loss(1000, 1), 120)

    def test_gate_damage_becomes_steps(self) -> None:
        self.assertEqual(gate_steps(0), 0)
        self.assertEqual(gate_steps(5), 1)
        self.assertEqual(gate_steps(25), 2)

    def test_gate_initial_value_scales_with_current_damage(self) -> None:
        self.assertEqual(gate_initial_value(10, 1.1), -11)
        self.assertEqual(gate_initial_value(20, 1.5), -30)
        self.assertEqual(gate_initial_value(0, 1.5), -1)

    def test_number_format(self) -> None:
        self.assertEqual(format_number(9999), "9,999")
        self.assertEqual(format_number(12500), "1.2w")
        self.assertEqual(format_number(100_000_000), "1.00e+08")

    def test_boss_gold_scales_with_current_wallet(self) -> None:
        self.assertEqual(boss_gold_reward(4, 0), 4)
        self.assertEqual(boss_gold_reward(6, 14), 8)
        self.assertEqual(boss_gold_reward(8, 25), 13)

    def test_attribute_price_increases_per_purchase(self) -> None:
        self.assertEqual(attribute_price(0), 4)
        self.assertEqual(attribute_price(1), 6)
        self.assertEqual(attribute_price(2), 9)

    def test_world_multiplier_is_bounded(self) -> None:
        self.assertEqual(world_multiplier(1), 1.0)
        self.assertEqual(world_multiplier(8), 4.0)
        self.assertEqual(world_multiplier(9), 5.0)
        self.assertEqual(world_multiplier(99), 6.25)


if __name__ == "__main__":
    unittest.main()
