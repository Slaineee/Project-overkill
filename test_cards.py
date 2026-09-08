import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from card_editor import CardEditor, editor_cards_path
from cards import (
    ACTION_SPECS,
    ACTION_STATS,
    CARDS,
    TARGET_BOSS,
    TARGET_ELITE,
    TARGET_NORMAL,
    Card,
    CardEffect,
    EffectTargets,
    load_cards,
    save_cards,
    validate_card,
)


def make_effect(
    value: float = 2.0,
    *,
    parameters: dict[str, object] | None = None,
) -> CardEffect:
    return CardEffect(
        targets=EffectTargets(player=True),
        trigger="passive",
        action="modify_stat",
        stat="base_damage",
        operator="add_flat",
        stacking="add",
        exclusive_group="",
        priority=0,
        parameters={"value": value, **(parameters or {})},
    )


def make_card(key: str, effects: tuple[CardEffect, ...]) -> Card:
    return Card(key, "测试卡", "用于验证通用卡牌结构。", "普通", 4, "damage", effects)


class CardDataTests(unittest.TestCase):
    def test_every_card_uses_generic_effect_blocks(self) -> None:
        for card in CARDS:
            with self.subTest(card=card.key):
                validate_card(card)
                for effect in card.effects:
                    self.assertIn(effect.action, ACTION_SPECS)

    def test_editor_exposes_new_projectile_and_fire_rate_stats(self) -> None:
        editable_stats = ACTION_STATS["modify_stat"]
        self.assertIn("projectile_bounces", editable_stats)
        self.assertIn("fire_rate_correction", editable_stats)

    def test_effect_targets_support_enemy_combinations(self) -> None:
        targets = EffectTargets(enemies=(TARGET_NORMAL, TARGET_ELITE, TARGET_BOSS))
        self.assertTrue(targets.includes(TARGET_NORMAL))
        self.assertTrue(targets.includes(TARGET_ELITE))
        self.assertTrue(targets.includes(TARGET_BOSS))

    def test_save_format_round_trips_multi_effect_card(self) -> None:
        custom = make_card(
            "test_multi_effect",
            (
                make_effect(7.5),
                CardEffect(
                    EffectTargets(player=True),
                    "on_boss_kill",
                    "grant_resource",
                    "gold",
                    "add_flat",
                    "independent",
                    "",
                    0,
                    {"value": 3},
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.json"
            save_cards([custom], path)
            loaded = load_cards(path)
        self.assertEqual(loaded, (custom,))

    def test_duplicate_keys_are_rejected_before_saving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.json"
            with self.assertRaisesRegex(ValueError, "duplicate card key"):
                save_cards([CARDS[0], CARDS[0]], path)

    def test_invalid_parameters_are_rejected(self) -> None:
        invalid_number = make_card("invalid_number", (make_effect(math.inf),))
        invalid_custom = make_card("invalid_custom", (make_effect(parameters={"invalid-key": 1}),))
        with self.assertRaisesRegex(ValueError, "finite number"):
            validate_card(invalid_number)
        with self.assertRaisesRegex(ValueError, "invalid parameter key"):
            validate_card(invalid_custom)

    def test_custom_parameters_are_preserved(self) -> None:
        effect = make_effect(
            parameters={
                "custom_integer": 8,
                "custom_ratio": -0.25,
                "custom_toggle": True,
                "custom_text": "population",
            }
        )
        custom = make_card("custom_parameters", (effect,))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.json"
            save_cards([custom], path)
            loaded = load_cards(path)
        self.assertEqual(loaded, (custom,))

    def test_projectile_count_must_be_an_integer(self) -> None:
        effect = CardEffect(
            EffectTargets(player=True),
            "passive",
            "projectile_pattern",
            "projectile_pattern",
            "set",
            "replace",
            "volley",
            1,
            {"count": 2.5, "spread": 10.0, "damage_scale": 0.5},
        )
        with self.assertRaisesRegex(ValueError, "projectile count"):
            validate_card(make_card("fractional_projectiles", (effect,)))

    def test_editor_parses_each_parameter_type(self) -> None:
        self.assertEqual(CardEditor.parse_parameter("2.5", "小数"), 2.5)
        self.assertEqual(CardEditor.parse_parameter("4", "整数"), 4)
        self.assertIs(CardEditor.parse_parameter("是", "布尔"), True)
        self.assertEqual(CardEditor.parse_parameter("population", "文本"), "population")

    def test_packaged_editor_honors_shared_path_override(self) -> None:
        expected = Path(tempfile.gettempdir()) / "shared-cards.json"
        with patch.dict(os.environ, {"DOUBLE_FRONT_CARDS": str(expected)}), patch.object(
            sys, "frozen", True, create=True
        ):
            self.assertEqual(editor_cards_path(), expected.resolve())


if __name__ == "__main__":
    unittest.main()
