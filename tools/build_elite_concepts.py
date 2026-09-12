from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


CANVAS = (1536, 1024)
PREVIEW = (1280, 720)
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


@dataclass(frozen=True)
class EliteStyle:
    key: str
    title: str
    subtitle: str
    accent: tuple[int, int, int]
    states: tuple[str, str, str, str]


STYLES = (
    EliteStyle(
        "guardian",
        "棱镜守卫",
        "冷白折光圣盾 / PRISM GUARDIAN",
        (86, 221, 255),
        ("常态", "盾环转位", "单盾破损", "核心易伤"),
    ),
    EliteStyle(
        "archon",
        "链接执政官",
        "青蓝神经中枢 / LINK ARCHON",
        (36, 226, 255),
        ("无连接", "三目标链接", "插槽失效", "断网脉冲"),
    ),
    EliteStyle(
        "hunter",
        "过载猎手",
        "赤热四推进猎杀体 / OVERLOAD HUNTER",
        (255, 93, 54),
        ("橙色蓄力", "红色冲锋", "过热易伤", "死亡冲击"),
    ),
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def fit_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGB")
    target_ratio = size[0] / size[1]
    ratio = image.width / image.height
    if ratio > target_ratio:
        crop_w = round(image.height * target_ratio)
        left = (image.width - crop_w) // 2
        image = image.crop((left, 0, left + crop_w, image.height))
    elif ratio < target_ratio:
        crop_h = round(image.width / target_ratio)
        top = (image.height - crop_h) // 2
        image = image.crop((0, top, image.width, top + crop_h))
    return image.resize(size, Image.Resampling.LANCZOS)


def largest_center_component(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    candidates = np.argwhere(mask)
    if not len(candidates):
        raise ValueError("No foreground pixels detected in sprite cell")
    center = np.array([height / 2.0, width / 2.0])
    seed_y, seed_x = candidates[np.argmin(np.sum((candidates - center) ** 2, axis=1))]
    visited = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque([(int(seed_y), int(seed_x))])
    visited[seed_y, seed_x] = True
    while queue:
        y, x = queue.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if not (dx or dy):
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
    return visited


def extract_sprite(sheet: Image.Image, index: int, size: int = 64) -> Image.Image:
    left = round(sheet.width * index / 4)
    right = round(sheet.width * (index + 1) / 4)
    cell = sheet.crop((left, 0, right, sheet.height)).convert("RGB")
    rgb = np.asarray(cell).astype(np.int16)
    hi = rgb.max(axis=2)
    lo = rgb.min(axis=2)
    saturation = hi - lo
    luminance = rgb.mean(axis=2)

    # Generated sprite strips occasionally contain a baked neutral checkerboard.
    # Saturated colors plus very light/dark chassis pixels isolate the subject.
    raw_mask = (saturation > 24) | (luminance < 102) | (luminance > 238)
    mask_image = Image.fromarray(np.uint8(raw_mask) * 255, "L")
    bridged = mask_image.filter(ImageFilter.MaxFilter(5))
    component = largest_center_component(np.asarray(bridged) > 0)
    component_image = Image.fromarray(np.uint8(component) * 255, "L").filter(ImageFilter.MinFilter(3))
    bbox = component_image.getbbox()
    if bbox is None:
        raise ValueError("Unable to find sprite bounds")

    pad = 8
    bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(cell.width, bbox[2] + pad),
        min(cell.height, bbox[3] + pad),
    )
    rgba = cell.convert("RGBA")
    rgba.putalpha(component_image)
    rgba = rgba.crop(bbox)
    scale = min((size - 2) / rgba.width, (size - 2) / rgba.height)
    resized = rgba.resize(
        (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))),
        Image.Resampling.NEAREST,
    )
    result = Image.new("RGBA", (size, size))
    result.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return result


def draw_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], accent: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=10, fill=(4, 9, 22, 235), outline=(*accent, 210), width=2)
    x0, y0, x1, _ = box
    draw.line((x0 + 16, y0 + 8, x1 - 16, y0 + 8), fill=(*accent, 180), width=2)


def annotate_concept(source: Path, output: Path, style: EliteStyle) -> None:
    base = fit_canvas(Image.open(source), CANVAS).convert("RGBA")
    overlay = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(overlay)
    draw_panel(draw, (24, 22, 650, 118), style.accent)
    draw.text((48, 32), style.title, font=font(44, True), fill=(241, 248, 255, 255))
    draw.text((50, 83), style.subtitle, font=font(18), fill=(*style.accent, 255))

    draw_panel(draw, (270, 958, 1512, 1008), style.accent)
    label_font = font(18)
    label_width = (1512 - 270) // 4
    for i, label in enumerate(style.states):
        x = 270 + i * label_width
        draw.text((x + 24, 973), f"{i + 1:02d}  {label}", font=label_font, fill=(215, 232, 247, 255))
    Image.alpha_composite(base, overlay).convert("RGB").save(output, quality=95)


def draw_health_bar(draw: ImageDraw.ImageDraw, center: tuple[int, int], accent: tuple[int, int, int]) -> None:
    x, y = center
    draw.rounded_rectangle((x - 46, y + 39, x + 46, y + 46), radius=3, fill=(2, 5, 12, 230), outline=(230, 242, 255, 220))
    draw.rounded_rectangle((x - 43, y + 41, x + 34, y + 44), radius=1, fill=(*accent, 255))


def make_preview(background: Path, sheet_path: Path, output: Path, style: EliteStyle) -> None:
    base = fit_canvas(Image.open(background), PREVIEW).convert("RGBA")
    sheet = Image.open(sheet_path)
    sprites = [extract_sprite(sheet, i) for i in range(4)]
    draw = ImageDraw.Draw(base, "RGBA")

    # Main 64px combat-scale read, placed at the boundary of the horde.
    main_center = (650, 285)
    base.alpha_composite(sprites[0], (main_center[0] - 32, main_center[1] - 32))
    draw_health_bar(draw, main_center, style.accent)

    if style.key == "archon":
        for target in ((720, 250), (746, 320), (704, 364)):
            draw.line((main_center[0], main_center[1], target[0], target[1]), fill=(*style.accent, 210), width=2)
            draw.ellipse((target[0] - 3, target[1] - 3, target[0] + 3, target[1] + 3), fill=(*style.accent, 255))
    elif style.key == "hunter":
        draw.line((main_center[0], main_center[1] + 36, main_center[0], 470), fill=(255, 79, 59, 150), width=2)
        draw.polygon(((644, 464), (656, 464), (650, 476)), fill=(255, 230, 220, 220))
    else:
        draw.arc((602, 237, 698, 333), 205, 330, fill=(*style.accent, 180), width=2)

    # Deterministic title and state comparison panel.
    draw_panel(draw, (18, 74, 498, 136), style.accent)
    draw.text((34, 82), style.title, font=font(28, True), fill=(241, 248, 255, 255))
    draw.text((180, 92), style.subtitle.split(" / ")[0], font=font(17), fill=(*style.accent, 255))

    panel = (728, 524, 1262, 704)
    draw_panel(draw, panel, style.accent)
    draw.text((748, 536), "64px 精英状态识别", font=font(18, True), fill=(241, 248, 255, 255))
    centers = (788, 918, 1048, 1178)
    for x, sprite, label in zip(centers, sprites, style.states):
        display = sprite.resize((72, 72), Image.Resampling.NEAREST)
        base.alpha_composite(display, (x - 36, 565))
        bounds = draw.textbbox((0, 0), label, font=font(15))
        width = bounds[2] - bounds[0]
        draw.text((x - width // 2, 653), label, font=font(15), fill=(210, 226, 242, 255))

    base.convert("RGB").save(output, quality=95)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build elite concept boards and combat-scale previews.")
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
    names = {
        "guardian": "棱镜守卫",
        "archon": "链接执政官",
        "hunter": "过载猎手",
    }
    for style in STYLES:
        concept = getattr(args, f"{style.key}_concept")
        sprites = getattr(args, f"{style.key}_sprites")
        stem = names[style.key]
        annotate_concept(concept, args.output_dir / f"{stem}-概念设定板.png", style)
        make_preview(args.background, sprites, args.output_dir / f"{stem}-像素战斗预览.png", style)
        if args.asset_dir is not None:
            target = args.asset_dir / style.key
            target.mkdir(parents=True, exist_ok=True)
            sheet = Image.open(sprites)
            for index in range(4):
                extract_sprite(sheet, index).save(target / f"{style.key}_{index:02}.png")


if __name__ == "__main__":
    main()
