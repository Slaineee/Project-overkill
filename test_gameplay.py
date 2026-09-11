import os
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from cards import CARD_BY_KEY, TARGET_BOSS, TARGET_ELITE, TARGET_NORMAL, TARGET_PLAYER, Card, CardEffect, EffectTargets
from main import (
    BOSS_KILL_VOLUME_BOOST,
    CROSSHAIR_PRESETS,
    KILL_SOUND_FADE_IN_MS,
    KILL_TAIL_DUCKING,
    PLAY_TOP,
    SETTLEMENT_BUTTON_DELAY,
    SETTLEMENT_RANK_DROP_DURATION,
    SETTLEMENT_SCORE_IMPACT_VOLUME_BOOST,
    SETTLEMENT_SCORE_DELAY,
    BloodStain,
    Boss,
    Bullet,
    EnemyBullet,
    Game,
    Gate,
    Mode,
    OwnedCard,
    ShopOffer,
)


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
        game.kill_channels = tuple(MagicMock() for _ in range(4))
        for channel in game.kill_channels:
            channel.get_busy.return_value = False
        game.audio_rng = MagicMock()
        game.audio_rng.choice.return_value = sounds[1]
        game.register_kill()
        game.audio_rng.choice.assert_called_once_with(sounds)
        game.kill_channels[0].play.assert_called_once_with(
            sounds[1],
            fade_ms=KILL_SOUND_FADE_IN_MS,
        )

    def test_kill_sound_uses_idle_voice_without_cutting_busy_tail(self) -> None:
        game = Game()
        game.audio_available = True
        game.kill_sounds = (MagicMock(),)
        game.kill_channels = tuple(MagicMock() for _ in range(4))
        game.kill_channels[0].get_busy.return_value = True
        for channel in game.kill_channels[1:]:
            channel.get_busy.return_value = False

        game.play_kill_sound()

        game.kill_channels[0].play.assert_not_called()
        game.kill_channels[0].set_volume.assert_called_with(
            game.effective_sfx_volume("kill") * KILL_TAIL_DUCKING
        )
        game.kill_channels[1].play.assert_called_once()

    def test_full_kill_voice_pool_recycles_next_voice_and_ducks_tails(self) -> None:
        game = Game()
        game.audio_available = True
        game.kill_sounds = (MagicMock(),)
        game.kill_channels = tuple(MagicMock() for _ in range(4))
        for channel in game.kill_channels:
            channel.get_busy.return_value = True
        game.kill_channel_cursor = 2

        game.play_kill_sound()

        selected = game.kill_channels[2]
        selected.play.assert_called_once()
        selected.set_volume.assert_called_with(game.effective_sfx_volume("kill"))
        self.assertEqual(game.kill_channel_cursor, 3)
        for index, channel in enumerate(game.kill_channels):
            if index != 2:
                channel.set_volume.assert_called_with(
                    game.effective_sfx_volume("kill") * KILL_TAIL_DUCKING
                )

    def test_boss_kill_uses_independent_boosted_channel(self) -> None:
        game = Game()
        game.audio_available = True
        game.kill_sounds = (MagicMock(),)
        game.boss_kill_channel = MagicMock()
        game.kill_channels = tuple(MagicMock() for _ in range(4))

        game.play_boss_kill_sound()

        expected_volume = min(
            1.0,
            game.effective_sfx_volume("kill") * BOSS_KILL_VOLUME_BOOST,
        )
        game.boss_kill_channel.set_volume.assert_called_once_with(expected_volume)
        game.boss_kill_channel.play.assert_called_once_with(
            game.kill_sounds[0],
            fade_ms=KILL_SOUND_FADE_IN_MS,
        )
        for channel in game.kill_channels:
            channel.play.assert_not_called()

    def test_killing_boss_does_not_use_normal_kill_pool(self) -> None:
        game = Game()
        boss = Boss(pygame.Vector2(640, 400), "small", 100, 100, 60, 100, 54)
        game.bosses.append(boss)
        game.play_boss_kill_sound = MagicMock()
        game.play_kill_sound = MagicMock()

        game.kill_boss(boss)

        game.play_boss_kill_sound.assert_called_once_with()
        game.play_kill_sound.assert_not_called()

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

    def test_settings_adjust_shake_and_glow_independently(self) -> None:
        game = Game(show_main_menu=True)
        game.mode = Mode.SETTINGS
        rows = dict(game.settings_visual_rows())
        self.assertEqual(
            set(rows),
            {"shake", "glow_brightness", "glow_spread", "glow_opacity", "glow_feather"},
        )
        original_shake = game.shake_intensity
        original_brightness = game.glow_brightness
        original_spread = game.glow_spread
        original_opacity = game.glow_opacity
        original_feather = game.glow_feather

        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settings_visual_button_rect(0, -1).center,
            )
        )
        self.assertAlmostEqual(game.shake_intensity, original_shake - 0.1)
        self.assertAlmostEqual(game.glow_brightness, original_brightness)

        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settings_visual_button_rect(1, 1).center,
            )
        )
        self.assertAlmostEqual(game.glow_brightness, round(original_brightness + 0.1, 1))

        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settings_visual_button_rect(2, -1).center,
            )
        )
        self.assertAlmostEqual(game.glow_spread, round(original_spread - 0.1, 1))

        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settings_visual_button_rect(3, 1).center,
            )
        )
        self.assertAlmostEqual(game.glow_opacity, round(original_opacity + 0.1, 1))

        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settings_visual_button_rect(4, 1).center,
            )
        )
        self.assertAlmostEqual(game.glow_feather, round(original_feather + 0.1, 1))

    def test_settings_cycles_through_all_crosshair_presets(self) -> None:
        game = Game(show_main_menu=True)
        game.mode = Mode.SETTINGS
        keys = [preset["key"] for preset in CROSSHAIR_PRESETS]

        for expected in keys[1:] + keys[:1]:
            game.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=game.settings_crosshair_button_rect(1).center,
                )
            )
            self.assertEqual(game.crosshair_preset, expected)

    def test_all_crosshair_presets_render_and_animate_in_settings(self) -> None:
        game = Game(show_main_menu=True)
        for preset in CROSSHAIR_PRESETS:
            game.crosshair_preset = preset["key"]
            sprite = game._render_crosshair_sprite()
            self.assertGreater(sprite.get_bounding_rect(min_alpha=1).width, 0)

        game.mode = Mode.SETTINGS
        phase = game.cursor_phase
        game.update(0.25)
        self.assertGreater(game.cursor_phase, phase)

    def test_stationary_cursor_does_not_emit_trail_particles(self) -> None:
        game = Game()
        position = pygame.Vector2(400, 300)
        game.update_cursor_effects(1 / 60, position)
        game.update_cursor_effects(1 / 60, position)
        self.assertEqual(len(game.cursor_trail), 1)
        self.assertFalse(game.cursor_particles)

    def test_death_effects_scale_by_enemy_class_and_multi_kill_cap(self) -> None:
        game = Game()
        position = pygame.Vector2(400, 300)

        game.spawn_death_effects(position, 16, 1.0)
        normal_strength = game.shake_strength
        normal_stain_radius = max(point.length() for point in game.blood_stains[-1].points)

        game.shake_strength = 0
        game.shake_timer = 0
        game.shake_duration = 0
        game.kill_combo = 0
        game.kill_combo_timer = 0
        game.spawn_death_effects(position, 27, 1.75)
        elite_strength = game.shake_strength

        game.shake_strength = 0
        game.shake_timer = 0
        game.shake_duration = 0
        game.kill_combo = 0
        game.kill_combo_timer = 0
        game.spawn_death_effects(position, 54, 4.0)
        boss_strength = game.shake_strength
        boss_stain_radius = max(point.length() for point in game.blood_stains[-1].points)

        self.assertLess(normal_strength, elite_strength)
        self.assertLess(elite_strength, boss_strength)
        self.assertGreater(boss_stain_radius, normal_stain_radius)

        first_strength = game.shake_strength
        for _ in range(30):
            game.spawn_death_effects(position, 16, 1.0)
        self.assertGreater(game.shake_strength, first_strength)
        self.assertLessEqual(game.shake_strength, 18.0)

    def test_death_particles_expire_before_blood_stains_fade(self) -> None:
        game = Game()
        game.spawn_death_effects(pygame.Vector2(400, 300), 16, 1.0)
        self.assertTrue(game.death_particles)
        self.assertTrue(game.blood_stains)

        game.update_visual_effects(0.5)
        self.assertFalse(game.death_particles)
        self.assertTrue(game.blood_stains)

        game.update_visual_effects(7.0)
        self.assertFalse(game.blood_stains)

    def test_blood_stain_keeps_a_feathered_bright_edge(self) -> None:
        game = Game()
        game.screen.fill((15, 18, 27))
        game.blood_stains = [
            BloodStain(
                pygame.Vector2(400, 300),
                (
                    pygame.Vector2(-24, -20),
                    pygame.Vector2(24, -20),
                    pygame.Vector2(24, 20),
                    pygame.Vector2(-24, 20),
                ),
                (),
                6.0,
                6.0,
            )
        ]

        game.draw_blood_stains()

        self.assertGreater(game.screen.get_at((376, 300)).r, game.screen.get_at((374, 300)).r)
        self.assertGreater(game.screen.get_at((374, 300)).r, game.screen.get_at((370, 300)).r)
        self.assertGreater(game.screen.get_at((370, 300)).r, 15)

    def test_glow_brightens_nearby_pixels_without_lifting_dark_background(self) -> None:
        game = Game()
        game.glow_brightness = 1.0
        game.glow_opacity = 1.0
        game.screen.fill((24, 24, 24))
        unchanged = game.screen.get_at((640, 360))
        game.apply_glow()
        self.assertEqual(game.screen.get_at((640, 360)), unchanged)

        game.screen.fill((24, 24, 24))
        pygame.draw.rect(game.screen, (40, 210, 245), (300, 240, 240, 180))
        before = game.screen.get_at((298, 330)).r
        game.apply_glow()
        self.assertGreater(game.screen.get_at((298, 330)).r, before)

    def test_glow_includes_dim_grid_lines(self) -> None:
        game = Game()
        game.glow_brightness = 1.0
        game.glow_opacity = 1.0
        game.glow_feather = 1.0
        game.screen.fill((15, 18, 27))
        pygame.draw.line(game.screen, (35, 41, 57), (320, 100), (320, 620))
        before = game.screen.get_at((324, 360))

        game.apply_glow()

        after = game.screen.get_at((324, 360))
        self.assertGreater(sum(after[:3]), sum(before[:3]))

    def test_glow_does_not_retain_previous_frame(self) -> None:
        game = Game()
        game.glow_brightness = 1.0
        game.glow_opacity = 1.0
        game.screen.fill((15, 18, 27))
        game.apply_glow()
        background_glow = game.screen.get_at((300, 360))[:3]

        game.screen.fill((15, 18, 27))
        pygame.draw.circle(game.screen, (74, 222, 128), (300, 360), 24)
        game.apply_glow()

        game.screen.fill((15, 18, 27))
        pygame.draw.circle(game.screen, (74, 222, 128), (700, 360), 24)
        game.apply_glow()

        self.assertEqual(game.screen.get_at((300, 360))[:3], background_glow)

    def test_glow_brightness_and_opacity_scale_effect(self) -> None:
        game = Game()
        game.glow_spread = 0.5
        game.screen.fill((24, 24, 24))
        pygame.draw.rect(game.screen, (40, 210, 245), (300, 240, 240, 180))
        game.glow_brightness = 0.1
        game.glow_opacity = 1.0
        game.apply_glow()
        faint = game.screen.get_at((298, 330)).r
        game.screen.fill((24, 24, 24))
        pygame.draw.rect(game.screen, (40, 210, 245), (300, 240, 240, 180))
        game.glow_brightness = 1.0
        game.apply_glow()
        strong = game.screen.get_at((298, 330)).r
        self.assertGreater(strong, faint)

        game.screen.fill((24, 24, 24))
        pygame.draw.rect(game.screen, (40, 210, 245), (300, 240, 240, 180))
        plain = game.screen.get_at((298, 330)).r
        game.glow_opacity = 0.0
        game.apply_glow()
        self.assertEqual(game.screen.get_at((298, 330)).r, plain)

    def test_shop_applies_edge_glow(self) -> None:
        game = Game()
        game.mode = Mode.SHOP
        game.apply_glow = MagicMock()
        game.draw()
        game.apply_glow.assert_called_once_with()

    def test_big_boss_kill_starts_settlement_slowmo(self) -> None:
        game = Game()
        game.log_world_completion = MagicMock()
        game.enter_shop = MagicMock()
        boss = Boss(pygame.Vector2(640, 400), "big", 100, 100, 60, 100, 54)
        game.bosses.append(boss)
        game.kill_boss(boss)
        self.assertIsNotNone(game.settlement)
        self.assertEqual(game.settlement.phase, "slowmo")
        self.assertEqual(game.mode, Mode.PLAYING)
        self.assertFalse(game.enter_shop.called)
        self.assertEqual(game.settlement.rows[0].key, "gold")
        self.assertEqual(game.settlement.rows[-1].key, "damage")

    def test_settlement_panel_starts_without_rows(self) -> None:
        game = Game()
        game.begin_settlement()
        self.assertEqual(game.settlement_shown_rows(), 0)
        game.settlement.phase = "panel"
        self.assertEqual(game.settlement_shown_rows(), 0)
        game.settlement.phase = "rows"
        game.settlement.row_index = 2
        self.assertEqual(game.settlement_shown_rows(), 2)
        game.settlement.phase = "button"
        self.assertEqual(game.settlement_shown_rows(), 4)

    def test_settlement_slowmo_scales_world_time(self) -> None:
        game = Game()
        game.begin_settlement()
        base = game.elapsed
        game.update(0.4)
        self.assertAlmostEqual(game.elapsed, base + 0.4 * 0.25, places=3)

    def test_end_game_is_suppressed_during_settlement(self) -> None:
        game = Game()
        game.begin_settlement()
        game.population = 0
        game.end_game("人口降为0")
        self.assertEqual(game.mode, Mode.PLAYING)

    def test_settlement_scoring_and_ranks(self) -> None:
        self.assertEqual(Game.rank_for_score(92)[0], "Overkill")
        self.assertEqual(Game.rank_for_score(92)[1], (255, 55, 70))
        self.assertEqual(Game.rank_for_score(78)[0], "S")
        self.assertEqual(Game.rank_for_score(60)[0], "A")
        self.assertEqual(Game.rank_for_score(38)[0], "B")
        self.assertEqual(Game.rank_for_score(37)[0], "C")
        self.assertEqual(Game.rank_for_score(19)[0], "D")
        fast_clear = Game.settlement_score(95, 90_000, 100, 100, 1)
        slow_clear = Game.settlement_score(110, 45_000, 60, 100, 1)
        self.assertGreater(fast_clear, slow_clear)
        self.assertEqual(Game.rank_for_score(fast_clear)[0], "Overkill")

    def test_settlement_rank_drops_once_after_score_delay(self) -> None:
        game = Game()
        game.begin_settlement()
        settlement = game.settlement
        settlement.phase = "rows"
        settlement.row_index = len(settlement.rows) - 1
        settlement.timer = 0.0
        game.slam_settlement_impact = MagicMock(wraps=game.slam_settlement_impact)

        game.update_settlement(0.0)
        self.assertEqual(settlement.phase, "score")
        game.slam_settlement_impact.reset_mock()
        game.settlement_particles.clear()

        game.update_settlement(SETTLEMENT_SCORE_DELAY)
        self.assertEqual(settlement.phase, "rank_drop")
        game.slam_settlement_impact.assert_not_called()

        game.play_settlement_rank_sound = MagicMock()
        game.update_settlement(SETTLEMENT_RANK_DROP_DURATION)
        self.assertEqual(settlement.phase, "rank")
        game.slam_settlement_impact.assert_called_once()
        self.assertTrue(game.slam_settlement_impact.call_args.kwargs["big"])
        game.play_settlement_rank_sound.assert_called_once_with()
        self.assertEqual(len(game.settlement_particles), 120)

        game.update_settlement(SETTLEMENT_BUTTON_DELAY)
        self.assertEqual(settlement.phase, "button")
        game.slam_settlement_impact.assert_called_once()

    def test_settlement_sparks_start_below_text_and_burst_upward(self) -> None:
        game = Game()
        game.begin_settlement()
        game.visual_rng.seed(7)
        impact = game.settlement_rank_impact_position()

        game.slam_settlement_impact(impact, 1.0, big=True)

        self.assertEqual(len(game.settlement_particles), 120)
        self.assertTrue(all(particle.position == impact for particle in game.settlement_particles))
        self.assertGreater(sum(particle.velocity.y < 0 for particle in game.settlement_particles), 80)
        self.assertGreater(max(particle.radius for particle in game.settlement_particles), 5.0)
        center = pygame.Vector2(game.settlement_score_center())
        self.assertEqual(impact.x, center.x)
        self.assertGreater(impact.y, center.y)

    def test_all_settlement_ranks_render_with_outer_glow(self) -> None:
        game = Game()
        game.begin_settlement()
        for score in (92, 78, 60, 38, 20, 0):
            rank, _ = game.rank_for_score(score)
            game.settlement.score = score
            game.settlement.rank = rank
            sprite = game.settlement_rank_sprite()
            sharp = game.font_huge.render(rank, True, game.settlement_rank_color())
            glow_bounds = sprite.get_bounding_rect(min_alpha=1)
            self.assertGreater(glow_bounds.width, sharp.get_width())
            self.assertGreater(glow_bounds.height, sharp.get_height())

    def test_rank_sheet_is_split_into_all_six_callouts(self) -> None:
        game = Game()
        self.assertEqual(set(game.rank_sounds), {"Overkill", "S", "A", "B", "C", "D"})
        self.assertGreater(game.rank_sounds["Overkill"].get_length(), 4.8)
        self.assertGreater(game.rank_sounds["Overkill"].get_length(), game.rank_sounds["S"].get_length())

    def test_rank_callout_uses_independent_channel(self) -> None:
        game = Game()
        game.begin_settlement()
        game.audio_available = True
        game.settlement.rank = "A"
        game.rank_sounds = {"A": MagicMock()}
        game.rank_channel = MagicMock()
        game.settlement_channel = MagicMock()

        game.play_settlement_rank_sound()

        game.rank_channel.play.assert_called_once_with(game.rank_sounds["A"])
        game.settlement_channel.play.assert_not_called()

    def test_rank_impact_sound_gets_volume_boost(self) -> None:
        game = Game()
        game.audio_available = True
        game.settlement_score_sound = MagicMock()
        game.settlement_channel = MagicMock()

        game.play_settlement_impact(big=True)

        expected = min(
            1.0,
            game.effective_sfx_volume("settlement") * SETTLEMENT_SCORE_IMPACT_VOLUME_BOOST,
        )
        game.settlement_channel.set_volume.assert_called_once_with(expected)
        game.settlement_channel.play.assert_called_once_with(game.settlement_score_sound)

    def test_settlement_progresses_to_button_and_enters_shop(self) -> None:
        game = Game()
        game.begin_settlement()
        for _ in range(360):
            game.update(1 / 60)
        self.assertEqual(game.settlement.phase, "button")
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertIsNone(game.settlement)
        self.assertEqual(game.mode, Mode.SHOP)

    def test_settlement_button_click_finishes(self) -> None:
        game = Game()
        game.begin_settlement()
        game.settlement.phase = "button"
        game.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=game.settlement_button_rect().center,
            )
        )
        self.assertIsNone(game.settlement)
        self.assertEqual(game.mode, Mode.SHOP)

    def test_settlement_shake_scales_with_magnitude(self) -> None:
        game = Game()
        game.slam_settlement_impact(pygame.Vector2(500, 300), 10)
        small = game.shake_strength
        game.slam_settlement_impact(pygame.Vector2(500, 300), 10_000_000)
        self.assertGreater(game.shake_strength, small)
        self.assertLessEqual(game.shake_strength, 18.0)
        game.slam_settlement_impact(pygame.Vector2(500, 300), 1, big=True)
        self.assertEqual(game.shake_strength, 18.0)

    def test_total_damage_dealt_tracks_bullet_hits(self) -> None:
        game = Game()
        game.spawn_enemy()
        enemy = game.enemies[-1]
        enemy.position = pygame.Vector2(640, 400)
        game.bullets.append(Bullet(pygame.Vector2(640, 400), pygame.Vector2(0, 0), 100.0, 100.0))
        game.update_bullets(0.016)
        self.assertGreaterEqual(game.total_damage_dealt, 100.0)

    def test_settings_include_settlement_volume(self) -> None:
        rows = dict(Game.settings_volume_rows())
        self.assertIn("settlement", rows)


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
        self.assertAlmostEqual(game.current_fire_rate(), 8 * (1 + 0.10 + 0.30))

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
        self.assertEqual(game.population, 30)

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

    def test_world_eight_settlement_opens_final_challenge_choice(self) -> None:
        game = Game()
        game.world = 8
        game.begin_settlement()
        game.finish_settlement()
        self.assertEqual(game.mode, Mode.CHALLENGE_CHOICE)
        self.assertIsNone(game.challenge_checkpoint)

    def test_final_challenge_starts_world_nine_without_shop_and_carries_population(self) -> None:
        game = Game()
        game.world = 8
        game.population = 123
        game.rng.seed(7)
        game.start_final_challenge()
        self.assertEqual(game.mode, Mode.PLAYING)
        self.assertEqual(game.world, 9)
        self.assertEqual(game.population, 123)
        self.assertIsNotNone(game.challenge_checkpoint)
        self.assertEqual(len(game.bosses), 1)
        self.assertEqual(game.bosses[0].variant, "commander")
        self.assertGreater(game.bosses[0].position.y, 0)
        self.assertTrue(game.big_spawned)

    def test_final_world_timeline_skips_small_and_medium_bosses(self) -> None:
        game = Game()
        game.world = 9
        game.start_world(carried_population=100)
        game.elapsed = 75
        game.small_spawned = False
        game.medium_spawned = False
        game.update_timeline(0)
        self.assertFalse(game.small_spawned)
        self.assertFalse(game.medium_spawned)
        self.assertEqual([boss.variant for boss in game.bosses], ["commander"])

    def test_final_world_times_out_at_ninety_seconds(self) -> None:
        game = Game()
        game.world = 9
        game.start_world(carried_population=100)
        game.elapsed = 90
        game._update_world(0)
        self.assertEqual(game.mode, Mode.GAME_OVER)
        self.assertIn("90秒截止", game.death_reason)

    def test_world_nine_shop_population_upgrades_feed_world_ten(self) -> None:
        game = Game()
        game.world = 9
        game.population = 75
        game.gold = 1_000
        game.enter_shop()

        game.handle_shop_click(game.attribute_rect(0).center)
        card = CARD_BY_KEY["critical_chance"]
        game.shop_offers = [ShopOffer(card, "population")]
        game.handle_shop_click(game.card_rect(0).center)
        self.assertEqual(game.challenge_shop_population_bonus, 7)

        game.continue_from_shop()
        self.assertEqual(game.world, 10)
        self.assertEqual(game.population, 82)
        self.assertEqual(game.bosses[0].variant, "devourer")

    def test_selling_card_bought_in_world_nine_shop_reverses_population_credit(self) -> None:
        game = Game()
        game.world = 9
        game.population = 75
        game.gold = 1_000
        game.enter_shop()
        card = CARD_BY_KEY["critical_chance"]
        game.shop_offers = [ShopOffer(card, "population")]
        game.handle_shop_click(game.card_rect(0).center)
        owned = game.equipped_cards[-1]
        self.assertEqual(game.challenge_shop_population_bonus, 5)
        game.sell_owned_card(owned, "normal")
        self.assertEqual(game.challenge_shop_population_bonus, 0)

    def test_commander_shield_reduces_damage_while_elite_lives(self) -> None:
        game = Game()
        game.world = 9
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        boss.position.update(640, 200)
        game.spawn_enemy(elite=True)
        before = boss.hp
        game.bullets = [
            Bullet(boss.position.copy(), pygame.Vector2(), 100, 100)
        ]
        game.update_bullets(0)
        self.assertEqual(before - boss.hp, 40)

    def test_commander_half_health_starts_phase_two_and_spawns_elite(self) -> None:
        game = Game()
        game.world = 9
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        game.enemies.clear()
        boss.hp = boss.max_hp * 0.5
        game.update_bosses(0)
        self.assertEqual(boss.phase, 2)
        self.assertEqual(sum(enemy.elite for enemy in game.enemies), 1)
        self.assertLessEqual(game.elite_timer, 3.0)

    def test_final_boss_phase_one_roams_only_above_player_area(self) -> None:
        game = Game()
        game.world = 9
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        boss.position.update(640, 220)
        boss.roam_direction.update(1, 0)
        start = boss.position.copy()
        for _ in range(300):
            boss.update(1 / 60, game.player)
            self.assertLessEqual(boss.position.y, PLAY_TOP - boss.radius - 20)
        self.assertNotEqual(boss.position, start)

    def test_final_boss_invades_player_area_only_after_phase_change(self) -> None:
        game = Game()
        game.world = 10
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        upper_limit = PLAY_TOP - boss.radius - 20
        boss.position.update(game.player.x, upper_limit)
        boss.roam_direction.update(0, 1)
        boss.update(1.0, game.player)
        self.assertEqual(boss.position.y, upper_limit)

        boss.phase = 2
        boss.update(1.0, game.player)
        self.assertGreater(boss.position.y, upper_limit)

    def test_devourer_absorbs_missed_gates_and_caps_rage(self) -> None:
        game = Game()
        game.world = 10
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        boss.hp -= boss.max_hp * 0.20
        before = boss.hp
        for _ in range(7):
            gate = Gate(pygame.Vector2(300, 800), "number", value=10)
            game.gates = [gate]
            game.update_gates(0)
        self.assertGreater(boss.hp, before)
        self.assertEqual(boss.rage_stacks, 5)

    def test_devourer_phase_two_alternates_to_sixteen_way_ring(self) -> None:
        game = Game()
        game.world = 10
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        boss.position.update(640, 200)
        boss.phase = 2
        boss.pattern_index = 1
        boss.shoot_timer = 0
        game.enemy_bullets.clear()
        game.update_boss_shooting(boss, 0)
        self.assertEqual(len(game.enemy_bullets), 16)
        self.assertTrue(
            all(bullet.population_loss_ratio == 0.03 for bullet in game.enemy_bullets)
        )

    def test_final_boss_variants_keep_big_boss_card_context(self) -> None:
        game = Game()
        game.world = 10
        game.equipped_cards = [OwnedCard("decapitate", "", 8)]
        game.start_world(carried_population=100)
        boss = game.bosses[0]
        boss.position.update(640, 200)
        expected_multiplier = game.apply_stat(
            1.0,
            "damage_taken",
            TARGET_BOSS,
            {"boss_kind": "big"},
        )
        before = boss.hp
        game.bullets = [
            Bullet(boss.position.copy(), pygame.Vector2(), 100, 100)
        ]
        game.update_bullets(0)
        self.assertEqual(before - boss.hp, 100 * expected_multiplier)

    def test_final_challenge_retry_strictly_restores_world_eight_checkpoint(self) -> None:
        game = Game()
        game.world = 8
        game.population = 200
        game.gold = 50
        game.rng.seed(1234)
        game.start_final_challenge()
        first_boss_x = game.bosses[0].position.x

        game.world = 10
        game.population = 3
        game.gold = 0
        game.equipped_cards.append(OwnedCard("critical_chance", "", 9))
        self.assertTrue(game.retry_final_challenge())

        self.assertEqual(game.world, 9)
        self.assertEqual(game.population, 200)
        self.assertEqual(game.gold, 50)
        self.assertFalse(game.equipped_cards)
        self.assertEqual(game.bosses[0].position.x, first_boss_x)

    def test_world_nine_enters_shop_and_world_ten_finishes_run(self) -> None:
        game = Game()
        game.world = 9
        game.begin_settlement()
        game.finish_settlement()
        self.assertEqual(game.mode, Mode.SHOP)
        game.world = 10
        game.begin_settlement()
        game.finish_settlement()
        self.assertEqual(game.mode, Mode.VICTORY)

    def test_final_challenge_choice_bosses_and_failure_actions_render(self) -> None:
        game = Game()
        game.world = 8
        game.population = 100
        game.mode = Mode.CHALLENGE_CHOICE
        game.draw()

        game.start_final_challenge()
        game.draw()
        game.world = 10
        game.start_world(carried_population=game.population)
        game.bosses[0].phase = 2
        game.bosses[0].rage_stacks = 5
        game.draw()

        game.end_game("测试终局失败")
        game.draw()

if __name__ == "__main__":
    unittest.main()
