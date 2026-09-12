from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from build_elite_concepts import CANVAS, PREVIEW, draw_panel, fit_canvas, font


@dataclass(frozen=True)
class BossStyle:
    key: str
    title: str
    subtitle: str
    accent: tuple[int, int, int]
    states: tuple[str, str, str, str]
    sprite_size: int


STYLES = (
    BossStyle(
        "small",
        "赏金逃逸者",
        "高价值装甲运钞体 / BOUNTY COURIER",
        (255, 190, 45),
        ("装甲接近", "货舱受损", "高速逃逸", "赏金解体"),
        72,
    ),
    BossStyle(
        "medium",
        "移动金库",
        "道中火力检测器 / MOBILE VAULT",
        (255, 174, 38),
        ("金库完整", "外甲受损", "核心暴露", "经济结算"),
        88,
    ),
    BossStyle(
        "big",
        "界门裁决者",
        "世界 1—8 共用守门人 / WORLD GATE SENTINEL",
        (184, 79, 255),
        ("世界巡弋", "斩杀蓄力", "锁柱错位", "分层解体"),
        112,
    ),
)


def connected_from_center(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    points = np.argwhere(mask)
    if not len(points):
        raise ValueError("No sprite foreground detected")
    center = np.array([height / 2.0, width / 2.0])
    sy, sx = points[np.argmin(np.sum((points - center) ** 2, axis=1))]
    component = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque([(int(sy), int(sx))])
    component[sy, sx] = True
    while queue:
        y, x = queue.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if not (dx or dy):
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not component[ny, nx]:
                    component[ny, nx] = True
                    queue.append((ny, nx))
    return component


def fill_enclosed_holes(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    outside = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        if not mask[0, x]:
            outside[0, x] = True
            queue.append((0, x))
        if not mask[height - 1, x]:
            outside[height - 1, x] = True
            queue.append((height - 1, x))
    for y in range(height):
        if not mask[y, 0]:
            outside[y, 0] = True
            queue.append((y, 0))
        if not mask[y, width - 1]:
            outside[y, width - 1] = True
            queue.append((y, width - 1))
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                queue.append((ny, nx))
    return mask | ~outside


def extract_sprite(sheet: Image.Image, index: int, size: int) -> Image.Image:
    left = round(sheet.width * index / 4)
    right = round(sheet.width * (index + 1) / 4)
    cell = sheet.crop((left, 0, right, sheet.height)).convert("RGB")
    rgb = np.asarray(cell).astype(np.int16)
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    saturation = high - low
    luminance = rgb.mean(axis=2)
    corner_luminance = float(np.mean((luminance[:20, :20], luminance[:20, -20:])))
    if corner_luminance < 45:
        raw = (luminance > 18) | (saturation > 16)
    else:
        raw = (saturation > 24) | (luminance < 102) | (luminance > 238)
    bridged = Image.fromarray(np.uint8(raw) * 255, "L").filter(ImageFilter.MaxFilter(5))
    component = connected_from_center(np.asarray(bridged) > 0)
    component = fill_enclosed_holes(component)
    alpha = Image.fromarray(np.uint8(component) * 255, "L").filter(ImageFilter.MinFilter(3))
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("Unable to determine sprite bounds")
    pad = 8
    bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(cell.width, bbox[2] + pad),
        min(cell.height, bbox[3] + pad),
    )
    rgba = cell.convert("RGBA")
    rgba.putalpha(alpha)
    rgba = rgba.crop(bbox)
    scale = min((size - 2) / rgba.width, (size - 2) / rgba.height)
    rgba = rgba.resize(
        (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))),
        Image.Resampling.NEAREST,
    )
    output = Image.new("RGBA", (size, size))
    output.alpha_composite(rgba, ((size - rgba.width) // 2, (size - rgba.height) // 2))
    return output


def annotate_concept(source: Path, output: Path, style: BossStyle) -> None:
    base = fit_canvas(Image.open(source), CANVAS).convert("RGBA")
    overlay = Image.new("RGBA", CANVAS)
    draw = ImageDraw.Draw(overlay)
    draw_panel(draw, (24, 22, 760, 118), style.accent)
    draw.text((48, 32), style.title, font=font(44, True), fill=(241, 248, 255, 255))
    draw.text((50, 83), style.subtitle, font=font(18), fill=(*style.accent, 255))
    draw_panel(draw, (270, 958, 1512, 1008), style.accent)
    width = (1512 - 270) // 4
    for index, label in enumerate(style.states):
        draw.text(
            (270 + index * width + 24, 973),
            f"{index + 1:02d}  {label}",
            font=font(18),
            fill=(215, 232, 247, 255),
        )
    Image.alpha_composite(base, overlay).convert("RGB").save(output, quality=95)


def make_preview(background: Path, sheet_path: Path, output: Path, style: BossStyle) -> None:
    base = fit_canvas(Image.open(background), PREVIEW).convert("RGBA")
    sheet = Image.open(sheet_path)
    sprites = [extract_sprite(sheet, index, style.sprite_size) for index in range(4)]
    draw = ImageDraw.Draw(base, "RGBA")

    center = (620, 275)
    sprite = sprites[0]
    base.alpha_composite(sprite, (center[0] - sprite.width // 2, center[1] - sprite.height // 2))
    bar_width = style.sprite_size + 30
    draw.rounded_rectangle(
        (center[0] - bar_width // 2, center[1] + style.sprite_size // 2 + 7,
         center[0] + bar_width // 2, center[1] + style.sprite_size // 2 + 15),
        radius=3,
        fill=(2, 5, 12, 235),
        outline=(241, 248, 255, 220),
    )
    draw.line(
        (center[0] - bar_width // 2 + 4, center[1] + style.sprite_size // 2 + 11,
         center[0] + bar_width // 2 - 10, center[1] + style.sprite_size // 2 + 11),
        fill=(*style.accent, 255),
        width=3,
    )
    if style.key == "big":
        radius = 175
        draw.ellipse(
            (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
            outline=(235, 78, 89, 150),
            width=2,
        )

    draw_panel(draw, (18, 74, 600, 136), style.accent)
    draw.text((34, 82), style.title, font=font(28, True), fill=(241, 248, 255, 255))
    draw.text((220, 92), style.subtitle.split(" / ")[0], font=font(17), fill=(*style.accent, 255))

    draw_panel(draw, (666, 514, 1262, 704), style.accent)
    draw.text(
        (686, 528),
        f"实战尺寸 {style.sprite_size}px · 状态识别",
        font=font(18, True),
        fill=(241, 248, 255, 255),
    )
    centers = (732, 880, 1028, 1176)
    for x, state, label in zip(centers, sprites, style.states):
        base.alpha_composite(state, (x - state.width // 2, 562 + (112 - state.height) // 2))
        bounds = draw.textbbox((0, 0), label, font=font(15))
        draw.text(
            (x - (bounds[2] - bounds[0]) // 2, 663),
            label,
            font=font(15),
            fill=(210, 226, 242, 255),
        )
    base.convert("RGB").save(output, quality=95)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for style in STYLES:
        parser.add_argument(f"--{style.key}-concept", type=Path, required=True)
        parser.add_argument(f"--{style.key}-sprites", type=Path, required=True)
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for style in STYLES:
        annotate_concept(
            getattr(args, f"{style.key}_concept"),
            args.output_dir / f"{style.title}-概念设定板.png",
            style,
        )
        make_preview(
            args.background,
            getattr(args, f"{style.key}_sprites"),
            args.output_dir / f"{style.title}-像素战斗预览.png",
            style,
        )
        if args.asset_dir is not None:
            target = args.asset_dir / style.key
            target.mkdir(parents=True, exist_ok=True)
            sheet = Image.open(getattr(args, f"{style.key}_sprites"))
            for index in range(4):
                extract_sprite(sheet, index, style.sprite_size).save(
                    target / f"{style.key}_{index:02}.png"
                )


if __name__ == "__main__":
    main()
