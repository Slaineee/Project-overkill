from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

MAIN_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = MAIN_DIR.parent
sys.path.insert(0, str(MAIN_DIR))

import pygame

from main import BG, Enemy, Game, NORMAL_ENEMY_ANIMATION_FPS


def render() -> Path:
    game = Game()
    game.enemies = []
    columns, rows = 13, 8
    for row in range(rows):
        for column in range(columns):
            x = 705 + column * 40 + (row % 2) * 16
            y = 112 + row * 43
            game.enemies.append(
                Enemy(
                    pygame.Vector2(x, y),
                    20,
                    20,
                    65,
                    16,
                    animation_time=((row * 3 + column) % 4) / NORMAL_ENEMY_ANIMATION_FPS,
                    heading_degrees=180 + (column % 3 - 1) * 22.5,
                )
            )

    game.screen.fill(BG)
    game.draw_arena()
    for x, y in ((735, 145), (875, 190), (1000, 250), (820, 335), (1120, 410), (950, 460)):
        game.spawn_death_effects(pygame.Vector2(x, y), 16, 1.0)
    game.draw_blood_stains()
    game.draw_enemies()
    game.draw_hud()
    output = PROJECT_DIR / "concepts" / "脉冲囊-40px群体预览.png"
    pygame.image.save(game.screen, output)
    blood_output = PROJECT_DIR / "concepts" / "脉冲囊-40px-红色血迹预览.png"
    pygame.image.save(game.screen, blood_output)
    pygame.quit()
    return output


if __name__ == "__main__":
    print(render())
