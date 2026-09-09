import os
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from cards import CARD_BY_KEY, TARGET_BOSS, TARGET_ELITE, TARGET_NORMAL, TARGET_PLAYER, Card, CardEffect, EffectTargets
from main import Boss, Bullet, EnemyBullet, Game, Gate, Mode, OwnedCard, ShopOffer


class GameplayTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_big_boss_attack_can_be_dodged(self) -> None:
        boss = Boss(pygame.Vector2(100, 100), "big", 100, 100, 100, 8, 54, 175, 1.0)
        player = pygame.Vector2(200, 100)
        self.assertFalse(boss.update(0.01, player))
        self.assertIsNotNone(boss.windup_remaining)
        player.update(500, 500)
        self.assertFalse(boss.update(1.1, player))
        self.assertIsNone(boss.windup_remaining)
        self.assertGreater(boss.position.x, 100)

    def test_pause_menu_restart_button_starts_a_new_run(self) -> None:
        game = Game()
        game.world = 4
        game.gold = 20
        game.population = 100
        game.mode = Mode.PAUSED
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.pause_restart_rect().center,
            )
        )
        self.assertEqual(game.mode, Mode.PLAYING)
        self.assertEqual(game.world, 1)
        self.assertEqual(game.gold, 0)
        self.assertEqual(game.population, 1)

    def test_pause_menu_r_key_restarts_and_stats_draw(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("critical_chance", "", 1)]
        game.mode = Mode.PAUSED
        game.draw_pause_menu()
        game.world = 3
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        self.assertEqual(game.mode, Mode.PLAYING)
        self.assertEqual(game.world, 1)

    def test_pause_menu_changes_sfx_and_bgm_volume_independently(self) -> None:
        game = Game()
        game.mode = Mode.PAUSED
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.pause_volume_button_rect("sfx", -1).center,
            )
        )
        self.assertEqual(game.sfx_volume, 0.6)
        self.assertEqual(game.bgm_volume, 0.4)

    def test_shot_sound_duration_tracks_fire_interval_without_pitch_resampling(self) -> None:
        game = Game()
        game.audio_available = True
        game.shot_sound = MagicMock()
        game.shot_channel = MagicMock()
        game.play_shot_sound(8.0)
        game.shot_channel.play.assert_called_once_with(game.shot_sound, maxtime=125)
        game.shot_channel.reset_mock()
        game.play_shot_sound(20.0)
        game.shot_channel.play.assert_called_once_with(game.shot_sound, maxtime=50)

    def test_enemy_kill_plays_one_of_two_random_sounds(self) -> None:
        game = Game()
        sounds = (MagicMock(), MagicMock())
        game.audio_available = True
        game.kill_sounds = sounds
        game.kill_channel = MagicMock()
        game.audio_rng = MagicMock()
        game.audio_rng.choice.return_value = sounds[1]
        game.register_kill()
        game.audio_rng.choice.assert_called_once_with(sounds)
        game.kill_channel.play.assert_called_once_with(sounds[1])

    def test_enemy_and_gate_hits_play_distinct_effects(self) -> None:
        game = Game()
        game.play_effect_sound = MagicMock()
        game.spawn_enemy()
        enemy = game.enemies[0]
        enemy.position.update(300, 300)
        game.bullets = [Bullet(enemy.position.copy(), pygame.Vector2(), 1, 1)]
        game.update_bullets(0)
        game.play_effect_sound.assert_called_with(game.enemy_hit_sound, "enemy_hit")

        game.play_effect_sound.reset_mock()
        gate = Gate(pygame.Vector2(500, 300), "number", value=1)
        game.gates = [gate]
        game.bullets = [Bullet(gate.position.copy(), pygame.Vector2(), 1, 1)]
        game.update_bullets(0)
        game.play_effect_sound.assert_called_with(game.gate_hit_sound, "gate_hit")

    def test_collecting_gate_plays_midi_style_chime(self) -> None:
        game = Game()
        game.play_effect_sound = MagicMock()
        game.gates = [Gate(game.player.copy(), "number", value=1)]
        game.update_gates(0)
        game.play_effect_sound.assert_called_once_with(game.gate_collect_sound, "gate_collect")

    def test_main_menu_navigates_to_tutorial_settings_and_game(self) -> None:
        game = Game(show_main_menu=True)
        self.assertEqual(game.mode, Mode.MAIN_MENU)
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.main_menu_button_rect(1).center,
            )
        )
        self.assertEqual(game.mode, Mode.TUTORIAL)
        game.draw()
        game.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=game.menu_back_rect().center)
        )
        self.assertEqual(game.mode, Mode.MAIN_MENU)

        game.world = 4
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.main_menu_button_rect(0).center,
            )
        )
        self.assertEqual(game.mode, Mode.PLAYING)
        self.assertEqual(game.world, 1)

    def test_settings_adjust_every_audio_category_independently(self) -> None:
        game = Game(show_main_menu=True)
        game.mode = Mode.SETTINGS
        game.preview_volume = MagicMock()
        initial_bgm = game.bgm_volume
        for index, (kind, _) in enumerate(game.settings_volume_rows()):
            before = game.volume_value(kind)
            game.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=game.settings_volume_button_rect(index, -1).center,
                )
            )
            self.assertAlmostEqual(game.volume_value(kind), before - 0.1)
        self.assertAlmostEqual(game.bgm_volume, initial_bgm - 0.1)
        self.assertAlmostEqual(game.effective_sfx_volume("shot"), 0.6 * 0.9)
        self.assertEqual(game.preview_volume.call_count, len(game.settings_volume_rows()))

    def test_bgm_crossfades_at_analyzed_beat_boundary(self) -> None:
        game = Game()
        old_channel = MagicMock()
        new_channel = MagicMock()
        tracks = (MagicMock(), MagicMock())
        game.audio_available = True
        game.bgm_channels = (old_channel, new_channel)
        game.bgm_tracks = tracks
        game.bgm_track_index = 0
        game.bgm_elapsed = 86.89
        game.update_audio(0.02)
        old_channel.fadeout.assert_called_once_with(405)
        new_channel.play.assert_called_once_with(tracks[1], fade_ms=405)
        self.assertEqual(game.bgm_track_index, 1)
        self.assertEqual(game.bgm_elapsed, 0.0)

    def test_custom_card_uses_generic_effect_block(self) -> None:
        effect = CardEffect(
            EffectTargets(player=True),
            "passive",
            "modify_stat",
            "base_damage",
            "add_flat",
            "add",
            "",
            0,
            {"value": 7.5},
        )
        custom = Card(
            "custom_damage_card",
            "自定义伤害卡",
            "基础伤害 +7.5",
            "普通",
            3,
            "damage",
            (effect,),
        )
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            self.assertEqual(game.current_base_damage(), 17.5)

    def test_card_key_alone_does_not_activate_a_rule(self) -> None:
        custom = Card(
            "phase_move",
            "同名无效果卡",
            "只验证键名不会被当作效果。",
            "普通",
            3,
            "custom",
            (),
        )
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            self.assertFalse(game.has_rule("moving_counts_as_still"))

    def test_combined_enemy_targets_apply_selectively(self) -> None:
        effect = CardEffect(
            EffectTargets(enemies=(TARGET_NORMAL, TARGET_BOSS)),
            "passive",
            "modify_stat",
            "damage_taken",
            "add_percent",
            "add",
            "",
            0,
            {"value": 0.5},
        )
        custom = Card("combined_targets", "组合目标", "小怪与Boss增伤。", "普通", 3, "damage", (effect,))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            self.assertEqual(game.apply_stat(1.0, "damage_taken", TARGET_NORMAL), 1.5)
            self.assertEqual(game.apply_stat(1.0, "damage_taken", TARGET_BOSS), 1.5)
            self.assertEqual(game.apply_stat(1.0, "damage_taken", 4), 1.0)

    def test_multi_effect_card_dispatches_event_resources(self) -> None:
        effects = tuple(
            CardEffect(
                EffectTargets(player=True),
                "on_boss_kill",
                "grant_resource",
                stat,
                "add_flat",
                "independent",
                "",
                0,
                {"value": value},
            )
            for stat, value in (("gold", 3), ("population", 5))
        )
        custom = Card("boss_rewards", "Boss奖励", "Boss奖励测试。", "普通", 3, "economy", effects)
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.gold = 10
            game.population = 20
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            changes = game.dispatch_effect_event("on_boss_kill", TARGET_BOSS)
            self.assertEqual(changes, {"gold": 3, "population": 5})
            self.assertEqual((game.gold, game.population), (13, 25))

    def test_periodic_resource_effect_uses_runtime_interval(self) -> None:
        effect = CardEffect(
            EffectTargets(player=True),
            "interval",
            "periodic_resource",
            "population",
            "add_flat",
            "independent",
            "",
            0,
            {"value": 2, "interval": 1.0},
        )
        custom = Card("periodic_population", "定时人口", "每秒增加人口。", "普通", 3, "survival", (effect,))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.population = 10
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            game.reset_world_effect_runtime()
            game.update_effect_runtime(0.5)
            self.assertEqual(game.population, 10)
            game.update_effect_runtime(0.5)
            self.assertEqual(game.population, 12)

    def test_event_chance_cooldown_and_stack_cap_are_interpreted(self) -> None:
        reward = CardEffect(
            EffectTargets(player=True),
            "on_enemy_kill",
            "grant_resource",
            "gold",
            "add_flat",
            "independent",
            "",
            0,
            {"value": 2, "chance": 1.0, "cooldown": 5.0},
        )
        stacking = CardEffect(
            EffectTargets(player=True),
            "on_enemy_kill",
            "modify_stat",
            "fire_rate",
            "add_percent",
            "add",
            "",
            0,
            {"value": 0.0, "stacks_per_trigger": 2, "value_per_stack": 0.1, "max_stacks": 3},
        )
        custom = Card("event_runtime", "事件运行时", "事件运行时测试。", "普通", 3, "utility", (reward, stacking))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            game.dispatch_effect_event("on_enemy_kill", TARGET_NORMAL)
            game.dispatch_effect_event("on_enemy_kill", TARGET_NORMAL)
            self.assertEqual(game.gold, 2)
            self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.3)
            game.update_effect_runtime(5.0)
            game.dispatch_effect_event("on_enemy_kill", TARGET_NORMAL)
            self.assertEqual(game.gold, 4)

    def test_zero_fire_rate_stops_firing_without_crashing(self) -> None:
        game = Game()
        game.default_fire_rate = 0
        with patch("pygame.key.get_pressed", return_value=defaultdict(int)), patch(
            "pygame.mouse.get_pressed", return_value=(True, False, False)
        ):
            game.update_player(0.1)
        self.assertFalse(game.bullets)

    def test_volley_scales_special_gate_damage_per_projectile(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("double_shot", "", 1)]
        with patch("pygame.key.get_pressed", return_value=defaultdict(int)), patch(
            "pygame.mouse.get_pressed", return_value=(True, False, False)
        ), patch("pygame.mouse.get_pos", return_value=(game.player.x, game.player.y - 100)):
            game.update_player(0.1)
        self.assertEqual(len(game.bullets), 2)
        expected = game.current_damage() * 0.65
        self.assertTrue(all(bullet.special_gate_damage == expected for bullet in game.bullets))

    def test_later_world_big_boss_moves_faster_during_windup(self) -> None:
        player = pygame.Vector2(200, 100)
        early = Boss(
            pygame.Vector2(100, 100), "big", 100, 100, 100, 8, 54,
            windup_duration=2.0, windup_remaining=1.0, windup_move_factor=0.10,
        )
        late = Boss(
            pygame.Vector2(100, 100), "big", 100, 100, 100, 8, 54,
            windup_duration=2.0, windup_remaining=1.0, windup_move_factor=0.50,
        )
        early.update(0.5, player)
        late.update(0.5, player)
        self.assertAlmostEqual(early.position.x, 105)
        self.assertAlmostEqual(late.position.x, 125)

    def test_big_boss_attack_hits_inside_range(self) -> None:
        boss = Boss(pygame.Vector2(100, 100), "big", 100, 100, 100, 8, 54, 175, 1.0)
        player = pygame.Vector2(200, 100)
        boss.update(0.01, player)
        self.assertTrue(boss.update(1.1, player))

    def test_elite_fires_slow_projectile(self) -> None:
        game = Game()
        game.population = 20
        game.spawn_enemy(elite=True)
        elite = game.enemies[0]
        elite.position.update(640, 200)
        elite.shoot_timer = 0
        game.update_enemies(0.01)
        self.assertEqual(len(game.enemy_bullets), 1)
        bullet = game.enemy_bullets[0]
        bullet.position.update(game.player)
        bullet.velocity.update(0, 0)
        game.update_enemy_bullets(0)
        self.assertEqual(game.population, 19)

    def test_bosses_fire_fan_patterns(self) -> None:
        game = Game()
        game.bosses = [
            Boss(pygame.Vector2(300, 200), "small", 100, 100, 0, 4, 34, shoot_timer=0),
            Boss(pygame.Vector2(640, 200), "medium", 100, 100, 0, 6, 42, shoot_timer=0),
            Boss(pygame.Vector2(980, 200), "big", 100, 100, 0, 8, 54, shoot_timer=0),
        ]
        game.update_bosses(0.01)
        self.assertEqual(len(game.enemy_bullets), 3 + 5 + 7)
        self.assertEqual(
            [bullet.population_loss_ratio for bullet in game.enemy_bullets].count(0.05),
            7,
        )

    def test_boss_fire_rate_increases_by_world(self) -> None:
        game = Game()
        world_one_interval = game.boss_shot_interval("big")
        game.world = 8
        self.assertLess(game.boss_shot_interval("big"), world_one_interval)

    def test_enemy_bullet_leaves_screen(self) -> None:
        game = Game()
        game.enemy_bullets = [EnemyBullet(pygame.Vector2(-30, -30), pygame.Vector2())]
        game.update_enemy_bullets(0)
        self.assertFalse(game.enemy_bullets)

    def test_enemy_damage_uses_population_percentage(self) -> None:
        game = Game()
        game.population = 100
        game.enemy_bullets = [EnemyBullet(game.player.copy(), pygame.Vector2(), population_loss_ratio=0.05)]
        game.update_enemy_bullets(0)
        self.assertEqual(game.population, 95)

    def test_population_below_two_ends_game_on_hit(self) -> None:
        game = Game()
        game.population = 2
        game.lose_population_ratio(0.02)
        self.assertEqual(game.population, 0)
        self.assertEqual(game.mode.name, "GAME_OVER")

    def test_big_boss_attack_executes_at_full_population_threshold(self) -> None:
        game = Game()
        game.population = 100
        game.population_peak = 100
        self.assertTrue(game.execute_player(1.0))
        self.assertEqual(game.population, 0)
        self.assertEqual(game.mode.name, "GAME_OVER")

    def test_elite_execution_kills_at_half_health_after_hit(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("execute", "", 1)]
        game.spawn_enemy(elite=True)
        elite = game.enemies[0]
        elite.position.update(300, 300)
        elite.hp = elite.max_hp * 0.60
        damage = elite.max_hp * 0.10
        game.bullets = [Bullet(elite.position.copy(), pygame.Vector2(), damage, damage)]
        game.update_bullets(0)
        self.assertEqual(elite.hp, 0)

    def test_base_damage_and_damage_bonuses_use_separate_additive_zones(self) -> None:
        game = Game()
        game.population = 2
        game.equipped_cards = [
            OwnedCard("damage", "", 1),
            OwnedCard("low_population", "", 1),
            OwnedCard("runner", "", 1),
        ]
        base_damage = 10 + float(CARD_BY_KEY["damage"].effects[0].parameters["value"])
        self.assertEqual(game.current_base_damage(), base_damage)
        low_bonus = float(CARD_BY_KEY["low_population"].effects[0].parameters["value"])
        self.assertAlmostEqual(game.current_damage(moving=True), 2 * base_damage * (1 + low_bonus + 0.12))

    def test_fire_rate_bonuses_are_additive(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("fire_rate", "", 1),
            OwnedCard("overclock", "", 1),
        ]
        self.assertAlmostEqual(game.current_fire_rate(), 8 * (1 + 0.10 + 0.25))

    def test_fire_rate_correction_is_added_after_percentage_bonuses(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("fire_rate", "", 1),
            OwnedCard("match_tr", "", 1),
        ]
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.10 + 2)

    def test_gate_damage_does_not_use_linear_combat_population(self) -> None:
        game = Game()
        game.population = 20
        self.assertEqual(game.current_damage(), 200)
        self.assertEqual(game.current_gate_damage(), 10)

    def test_spawned_targets_use_fixed_world_health(self) -> None:
        game = Game()
        game.population = 100
        game.spawn_enemy()
        game.spawn_enemy(elite=True)
        game.spawn_special_gate()
        game.spawn_boss("big")
        self.assertEqual(game.enemies[0].max_hp, 20)
        self.assertEqual(game.enemies[1].max_hp, game.current_dps())
        self.assertEqual(game.gates[0].max_hp, 21_093.75)
        self.assertEqual(game.bosses[0].max_hp, 675_000)

    def test_elite_health_targets_one_second_of_current_dps(self) -> None:
        game = Game()
        game.population = 100
        expected_dps = game.current_dps()
        game.spawn_enemy(elite=True)
        self.assertEqual(game.enemies[0].max_hp, expected_dps)

    def test_critical_card_uses_expected_dps_multiplier(self) -> None:
        game = Game()
        game.population = 10
        game.equipped_cards = [OwnedCard("critical_focus", "", 1)]
        self.assertEqual(game.critical_chance(), 0.50)
        self.assertEqual(game.critical_damage_multiplier(), 1.50)
        self.assertEqual(game.expected_critical_multiplier(), 1.25)
        self.assertAlmostEqual(game.current_dps(), 10 * 10 * 8 * 1.25)

    def test_critical_defaults_to_zero_chance_and_one_hundred_fifty_percent_damage(self) -> None:
        game = Game()
        self.assertEqual(game.critical_chance(), 0.0)
        self.assertEqual(game.critical_damage_multiplier(), 1.5)
        self.assertEqual(game.expected_critical_multiplier(), 1.0)

    def test_critical_cards_stack_chance_and_damage(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("critical_focus", "", 1),
            OwnedCard("critical_chance", "", 1),
            OwnedCard("critical_power", "", 1),
        ]
        self.assertEqual(game.critical_chance(), 0.75)
        self.assertEqual(game.critical_damage_multiplier(), 2.50)
        self.assertAlmostEqual(game.expected_critical_multiplier(), 2.125)

    def test_recruit_signal_changes_special_gate_probabilities(self) -> None:
        game = Game()
        self.assertIsNone(game.special_gate_weights())
        game.equipped_cards = [OwnedCard("recruit_gate_bias", "", 1)]
        self.assertEqual(game.special_gate_weights(), (0.15, 0.15, 0.70))

    def test_vampire_grants_population_on_every_kill(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("vampire", "", 1)]
        game.population = 10
        game.register_kill()
        game.register_kill()
        self.assertEqual(game.population, 12)

    def test_rapid_reload_gains_two_percent_fire_rate_per_fifteen_kills(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("kill_shot", "", 1)]
        for _ in range(30):
            game.register_kill()
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.04)

    def test_calm_aim_ramps_and_movement_clears_bonus(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("still_shot", "", 1)]
        game.still_time = 1.0
        self.assertAlmostEqual(game.calm_aim_bonus(), 0.40)
        game.still_time = 3.0
        self.assertAlmostEqual(game.calm_aim_bonus(), 0.60)
        game.still_time = 0.0
        self.assertEqual(game.calm_aim_bonus(), 0)

    def test_calm_aim_bonus_caps_at_five_hundred_percent(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("still_shot", "", 1)]
        game.still_time = 60.0
        self.assertEqual(game.calm_aim_bonus(), 5.0)
        game.still_time = 120.0
        self.assertEqual(game.calm_aim_bonus(), 5.0)

    def test_phase_move_preserves_calm_aim_while_moving(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("still_shot", "", 1),
            OwnedCard("phase_move", "", 1),
        ]
        game.still_time = 1.0
        game.update_still_time(0.5, moving=True)
        self.assertEqual(game.still_time, 1.5)
        self.assertAlmostEqual(game.calm_aim_bonus(), 0.40)

    def test_pierce_cards_stack_to_six_extra_targets(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("pierce", "", 1),
            OwnedCard("pierce_plus", "", 1),
        ]
        self.assertEqual(game.current_pierces(), 6)

    def test_ricochet_cards_use_the_highest_tier(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("ricochet_1", "", 1),
            OwnedCard("ricochet_3", "", 1),
        ]
        self.assertEqual(game.current_bounces(), 3)

    def test_bullet_bounces_at_screen_edge_then_disappears(self) -> None:
        game = Game()
        bullet = Bullet(pygame.Vector2(4, 200), pygame.Vector2(-100, 0), 10, 10, bounces=1)
        game.bullets = [bullet]
        game.update_bullets(0)
        self.assertIn(bullet, game.bullets)
        self.assertEqual(bullet.bounces, 0)
        self.assertGreater(bullet.velocity.x, 0)
        bullet.position.x = 1280
        game.update_bullets(0)
        self.assertNotIn(bullet, game.bullets)

    def test_piercing_bullet_cannot_pierce_gate_but_can_ricochet(self) -> None:
        game = Game()
        gate = Gate(pygame.Vector2(200, 200), "special", hp=100, max_hp=100, buff="damage")
        bullet = Bullet(
            gate.position.copy(),
            pygame.Vector2(0, 100),
            damage=10,
            gate_damage=10,
            pierces=3,
            bounces=1,
        )
        game.gates = [gate]
        game.bullets = [bullet]
        game.update_bullets(0)
        self.assertEqual(gate.hp, 90)
        self.assertIn(bullet, game.bullets)
        self.assertEqual(bullet.pierces, 3)
        self.assertEqual(bullet.bounces, 0)
        self.assertLess(bullet.velocity.y, 0)

    def test_wholesale_license_discounts_cards_to_zero(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("card_deal", "", 1)]
        self.assertEqual(game.card_purchase_price(CARD_BY_KEY["damage"]), 0)
        self.assertEqual(game.card_purchase_price(CARD_BY_KEY["critical_focus"]), 2)

    def test_wholesale_purchased_cards_use_restricted_sale_prices(self) -> None:
        game = Game()
        self.assertEqual(game.card_sale_price(OwnedCard("damage", "", 1, True)), 0)
        self.assertEqual(game.card_sale_price(OwnedCard("critical_focus", "", 1, True)), 1)
        self.assertEqual(game.card_sale_price(OwnedCard("composure", "", 1, True)), 2)
        self.assertEqual(game.card_sale_price(OwnedCard("damage", "", 1)), 1)

    def test_heavy_caliber_uses_corrected_base_damage(self) -> None:
        effects = {effect.stat: effect for effect in CARD_BY_KEY["heavy_ca"].effects}
        self.assertEqual(effects["base_damage"].parameters["value"], 64.0)
        self.assertEqual(effects["fire_rate"].parameters["value"], -0.99)
        self.assertEqual(effects["gate_damage"].parameters["value"], 1.0)
        self.assertEqual(effects["fire_rate_correction"].parameters["value"], 0.1)

    def test_each_shop_slot_independently_can_roll_overload(self) -> None:
        game = Game()
        game.shop_offers = []
        game.rng.random = MagicMock(return_value=0.0)
        game.fill_shop()
        self.assertEqual(len(game.shop_offers), 3)
        self.assertTrue(all(offer.is_overload for offer in game.shop_offers))
        self.assertTrue(all(offer.card is None for offer in game.shop_offers))
        self.assertEqual(game.rng.random.call_count, 3)

    def test_overload_exchange_reveals_identity_only_at_completion(self) -> None:
        game = Game()
        game.shop_round = 1
        owned = OwnedCard("composure", "", 1)
        offer = ShopOffer(overload_category="damage")
        game.equipped_cards = [owned]
        game.shop_offers = [offer]
        game.fill_shop = MagicMock()
        game.draw_overload_card = MagicMock(return_value=CARD_BY_KEY["damage"])

        self.assertTrue(game.exchange_for_overload(owned, offer))

        self.assertFalse(game.equipped_cards)
        self.assertEqual([card.key for card in game.overload_cards], ["damage"])
        self.assertEqual(game.overload_cards[0].enhancement, "overload")
        self.assertEqual(game.overload_cards[0].acquired_shop_round, 1)
        game.draw_overload_card.assert_called_once_with("damage")

    def test_overload_exchange_uses_wholesale_actual_sale_value(self) -> None:
        game = Game()
        owned = OwnedCard("critical_focus", "", 1, True, 1)
        offer = ShopOffer(overload_category="damage")
        game.equipped_cards = [owned]
        game.shop_offers = [offer]

        self.assertTrue(game.exchange_for_overload(owned, offer))

        self.assertEqual(game.shop_offers[0].exchange_value, 1)
        self.assertFalse(game.overload_cards)

    def test_overload_exchange_accumulates_and_discards_value_above_five(self) -> None:
        game = Game()
        common = OwnedCard("damage", "", 1)
        rare = OwnedCard("composure", "", 1)
        offer = ShopOffer(overload_category="damage")
        game.equipped_cards = [common, rare]
        game.shop_offers = [offer]
        game.fill_shop = MagicMock()
        game.draw_overload_card = MagicMock(return_value=CARD_BY_KEY["damage"])

        self.assertTrue(game.exchange_for_overload(common, offer))
        self.assertEqual(game.shop_offers[0].exchange_value, 1)
        game.draw_overload_card.assert_not_called()

        self.assertTrue(game.exchange_for_overload(rare, game.shop_offers[0]))
        self.assertEqual(len(game.overload_cards), 1)
        self.assertFalse(game.equipped_cards)
        game.draw_overload_card.assert_called_once_with("damage")

    def test_full_overload_slots_block_exchange_without_consuming_card(self) -> None:
        game = Game()
        owned = OwnedCard("damage", "", 1)
        game.equipped_cards = [owned]
        game.overload_cards = [
            OwnedCard("fire_rate", "overload", 1),
            OwnedCard("recruit", "overload", 1),
        ]
        offer = ShopOffer(overload_category="damage")
        game.shop_offers = [offer]

        self.assertFalse(game.exchange_for_overload(owned, offer))
        self.assertIn(owned, game.equipped_cards)
        self.assertEqual(offer.exchange_value, 0)

    def test_overload_sale_is_locked_until_next_shop_and_pays_twenty(self) -> None:
        game = Game()
        game.shop_round = 2
        owned = OwnedCard("damage", "overload", 1, acquired_shop_round=2)
        game.overload_cards = [owned]

        self.assertFalse(game.sell_owned_card(owned, "overload"))
        self.assertEqual(game.gold, 0)
        self.assertIn(owned, game.overload_cards)

        game.shop_round = 3
        self.assertTrue(game.sell_owned_card(owned, "overload"))
        self.assertEqual(game.gold, 20)
        self.assertFalse(game.overload_cards)

    def test_overload_duplicate_stacks_with_owned_normal_card(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("damage", "", 1)]
        game.overload_cards = [OwnedCard("damage", "overload", 1)]
        bonus = float(CARD_BY_KEY["damage"].effects[0].parameters["value"])
        self.assertEqual(game.current_base_damage(), 10 + bonus * 2)

    def test_duplicate_overload_growth_uses_each_cards_acquired_world(self) -> None:
        game = Game()
        game.world = 5
        game.population = 10
        game.equipped_cards = [OwnedCard("growth_recovery", "", 1)]
        game.overload_cards = [OwnedCard("growth_recovery", "overload", 4)]
        effect = next(
            effect
            for effect in CARD_BY_KEY["growth_recovery"].effects
            if effect.trigger == "on_elite_kill"
        )
        per_world = float(effect.parameters["per_world"])

        game.dispatch_effect_event("on_elite_kill", TARGET_NORMAL)

        expected = 10 + round(4 * per_world) + round(1 * per_world)
        self.assertEqual(game.population, expected)

    def test_card_is_sold_only_after_dragging_to_sale_area(self) -> None:
        game = Game()
        game.mode = Mode.SHOP
        owned = OwnedCard("damage", "", 1)
        game.equipped_cards = [owned]

        game.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=game.slot_rect(0).center)
        )
        self.assertIn(owned, game.equipped_cards)
        game.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=game.shop_sell_rect().center)
        )
        self.assertNotIn(owned, game.equipped_cards)
        self.assertEqual(game.gold, 1)

    def test_shop_button_switches_between_normal_and_overload_slots(self) -> None:
        game = Game()
        game.mode = Mode.SHOP
        self.assertEqual(game.card_page, "normal")
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.shop_page_button_rect().center,
            )
        )
        self.assertEqual(game.card_page, "overload")

    def test_population_fire_scales_slowly_and_caps_at_fifty_percent(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("population_fire", "", 1)]
        game.population = 50
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.001)
        game.population = 25_000
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.50)
        game.population = 1_000_000
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.50)

    def test_composure_charges_and_lingers_after_firing(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("composure", "", 1)]
        game.update_composure(0.15)
        self.assertEqual(game.composure_damage_bonus, 1.0)
        self.assertEqual(game.composure_gate_bonus, 3.0)
        game.update_composure(0.30)
        self.assertEqual(game.composure_damage_bonus, 2.0)
        self.assertEqual(game.composure_gate_bonus, 5.0)
        game.trigger_composure_release()
        game.update_composure(0.49)
        self.assertEqual(game.composure_damage_bonus, 2.0)
        game.update_composure(0.01)
        self.assertEqual(game.composure_damage_bonus, 0)
        self.assertEqual(game.composure_gate_bonus, 0)

    def test_composure_gate_bonus_does_not_repeat_normal_damage_bonus(self) -> None:
        game = Game()
        gate = Gate(pygame.Vector2(200, 200), "special", hp=100, max_hp=100, buff="damage")
        game.gates = [gate]
        game.bullets = [
            Bullet(
                gate.position.copy(),
                pygame.Vector2(),
                damage=20,
                gate_damage=4.3,
                gate_target_bonus=3.0,
                special_gate_damage=10,
            )
        ]
        game.update_bullets(0)
        self.assertEqual(gate.hp, 60)

    def test_theoretical_dps_includes_full_volley_multiplier(self) -> None:
        game = Game()
        game.population = 2
        game.equipped_cards = [OwnedCard("shotgun", "", 1)]
        self.assertEqual(game.current_volley_multiplier(), 1.9)
        self.assertAlmostEqual(game.current_dps(), 2 * 10 * 8 * 1.9)

    def test_elite_hunt_grants_gold_at_twenty_percent_chance(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_hunt", "", 1)]
        game.rng.random = MagicMock(return_value=0.1)
        before = game.gold
        changes = game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertEqual(changes["gold"], 1)
        self.assertEqual(game.gold, before + 1)

    def test_elite_hunt_increases_elite_spawn_frequency(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_hunt", "", 1)]
        base = max(8.0, 18.0 - (game.world - 1) * 1.45)
        self.assertAlmostEqual(
            game.apply_stat(base, "elite_spawn_interval", TARGET_PLAYER),
            base * 0.6667,
            places=3,
        )

    def test_elite_contact_avoid_chance_blocks_elite_breakthrough(self) -> None:
        effect = CardEffect(
            EffectTargets(enemies=(TARGET_ELITE,)),
            "passive",
            "modify_stat",
            "elite_contact_avoid_chance",
            "add_flat",
            "add",
            "",
            0,
            {"value": 1.0},
        )
        custom = Card("elite_dodge", "精英闪避", "精英突破必闪。", "普通", 3, "survival", (effect,))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            game.population = 100
            game.spawn_enemy(elite=True)
            elite = game.enemies[0]
            elite.position.update(game.player.x, game.player.y)
            game.rng.random = MagicMock(return_value=0.0)
            game.update_enemies(0.01)
            self.assertEqual(game.population, 100)
            self.assertFalse(game.enemies)

    def test_projectile_avoid_chance_dodges_enemy_bullet(self) -> None:
        effect = CardEffect(
            EffectTargets(player=True),
            "passive",
            "modify_stat",
            "projectile_avoid_chance",
            "add_flat",
            "add",
            "",
            0,
            {"value": 1.0},
        )
        custom = Card("bullet_dodge", "弹丸闪避", "弹丸必闪。", "普通", 3, "survival", (effect,))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            game.population = 100
            game.enemy_bullets = [EnemyBullet(game.player.copy(), pygame.Vector2(), population_loss_ratio=0.05)]
            game.rng.random = MagicMock(return_value=0.0)
            game.update_enemy_bullets(0)
            self.assertEqual(game.population, 100)
            self.assertFalse(game.enemy_bullets)

    def test_boss_contact_avoid_chance_interface(self) -> None:
        effect = CardEffect(
            EffectTargets(enemies=(TARGET_BOSS,)),
            "passive",
            "modify_stat",
            "boss_contact_avoid_chance",
            "add_flat",
            "add",
            "",
            0,
            {"value": 0.4},
        )
        custom = Card("boss_dodge", "Boss闪避", "Boss接触免伤。", "普通", 3, "survival", (effect,))
        with patch.dict(CARD_BY_KEY, {custom.key: custom}):
            game = Game()
            game.equipped_cards = [OwnedCard(custom.key, "", 1)]
            self.assertEqual(game.contact_avoid_chance(TARGET_BOSS), 0.4)

    def test_elite_adrenaline_refreshes_fire_rate_bonus_without_stacking(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_adrenaline", "", 1)]
        game.rng.random = MagicMock(return_value=0.5)
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.5)
        game.update_effect_runtime(4.0)
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        game.update_effect_runtime(4.0)
        self.assertAlmostEqual(game.current_fire_rate(), 8 * 1.5)

    def test_elite_adrenaline_shows_trigger_message(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_adrenaline", "", 1)]
        game.rng.random = MagicMock(return_value=0.5)
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertIn("嗜血扳机", game.message)
        self.assertGreater(game.message_timer, 0)

    def test_elite_adrenaline_no_message_when_chance_fails(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_adrenaline", "", 1)]
        game.rng.random = MagicMock(return_value=0.9)
        game.message = ""
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertEqual(game.message, "")

    def test_elite_harvest_grants_population_per_elite_kill(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_harvest", "", 1)]
        game.population = 100
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertEqual(game.population, 110)

    def test_elite_decree_stacks_damage_per_elite_kill(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_decree", "", 1)]
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertAlmostEqual(game.current_damage_bonus(), 0.02)
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertAlmostEqual(game.current_damage_bonus(), 0.04)

    def test_elite_decree_executes_elite_below_threshold(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_decree", "", 1)]
        game.spawn_enemy(elite=True)
        elite = game.enemies[0]
        elite.position.update(300, 300)
        elite.hp = elite.max_hp * 0.55
        damage = elite.max_hp * 0.05
        game.bullets = [Bullet(elite.position.copy(), pygame.Vector2(), damage, damage)]
        game.update_bullets(0)
        self.assertEqual(elite.hp, 0)

    def test_elite_decree_grants_gold_on_elite_kill(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_decree", "", 1)]
        before = game.gold
        game.dispatch_effect_event("on_elite_kill", TARGET_ELITE)
        self.assertEqual(game.gold, before + 4)

    def test_elite_bait_doubles_elite_spawn_frequency(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_bait", "", 1)]
        base = max(8.0, 18.0 - (game.world - 1) * 1.45)
        self.assertAlmostEqual(
            game.apply_stat(base, "elite_spawn_interval", TARGET_PLAYER),
            base * 0.5,
            places=3,
        )

    def test_elite_armor_adds_elite_contact_avoid_chance(self) -> None:
        game = Game()
        game.equipped_cards = [OwnedCard("elite_armor", "", 1)]
        self.assertEqual(game.contact_avoid_chance(TARGET_ELITE), 0.25)

    def test_elite_spawn_frequency_stacks_multiplicatively(self) -> None:
        game = Game()
        game.equipped_cards = [
            OwnedCard("elite_hunt", "", 1),
            OwnedCard("elite_bait", "", 1),
        ]
        base = max(8.0, 18.0 - (game.world - 1) * 1.45)
        self.assertAlmostEqual(
            game.apply_stat(base, "elite_spawn_interval", TARGET_PLAYER),
            base * 0.6667 * 0.5,
            places=3,
        )

    def test_recruit_gate_gains_multiplier_after_unlock(self) -> None:
        gate = Gate(pygame.Vector2(), "special", hp=100, max_hp=100, buff="population")
        gate.take_special_damage(100)
        self.assertEqual(gate.recruit_multiplier, 1.1)
        gate.take_special_damage(100)
        self.assertAlmostEqual(gate.recruit_multiplier, 1.2)
        gate.take_special_damage(200)
        self.assertAlmostEqual(gate.recruit_multiplier, 1.4)

    def test_recruit_gate_uses_tiered_exponential_step_costs(self) -> None:
        gate = Gate(pygame.Vector2(), "special", hp=0, max_hp=100, buff="population")
        gate.recruit_progress = 400
        self.assertEqual(gate.recruit_multiplier, 1.5)
        self.assertEqual(gate.recruit_progress_fraction, 0)
        gate.recruit_progress += 1_000
        self.assertEqual(gate.recruit_multiplier, 2.0)
        gate.recruit_progress += 400
        self.assertEqual(gate.recruit_multiplier, 2.1)
        gate.recruit_progress += 800
        self.assertEqual(gate.recruit_multiplier, 2.2)

    def test_recruit_gate_multiplies_current_population(self) -> None:
        game = Game()
        game.population = 100
        game.apply_special_buff("population", 1.4)
        self.assertEqual(game.population, 140)

    def test_special_gate_uses_combat_damage(self) -> None:
        game = Game()
        gate = Gate(pygame.Vector2(200, 200), "special", hp=225, max_hp=225, buff="damage")
        game.gates = [gate]
        game.bullets = [Bullet(gate.position.copy(), pygame.Vector2(), 200, 10)]
        game.update_bullets(0)
        self.assertEqual(gate.hp, 25)

    def test_special_gate_always_consumes_piercing_bullet_once(self) -> None:
        game = Game()
        gate = Gate(pygame.Vector2(200, 200), "special", hp=0, max_hp=100, buff="population")
        game.gates = [gate]
        game.bullets = [Bullet(gate.position.copy(), pygame.Vector2(), 10, 10, pierces=3)]
        game.update_bullets(0)
        self.assertFalse(game.bullets)
        self.assertEqual(gate.recruit_progress, 10)
        game.update_bullets(0)
        self.assertEqual(gate.recruit_progress, 10)

if __name__ == "__main__":
    unittest.main()
