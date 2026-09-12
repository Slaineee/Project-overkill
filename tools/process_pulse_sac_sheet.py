from __future__ import annotations

import argparse
import colorsys
import math
from pathlib import Path

from PIL import Image, ImageFilter


FRAME_COUNT = 4
OUTPUT_SIZE = 512


def foreground_mask(image: Image.Image) -> Image.Image:
    """Separate the green/dark sprite from a baked neutral checkerboard."""
    rgb = image.convert("RGB")
    mask = Image.new("L", rgb.size)
    values: list[int] = []
    source_pixels = (
        rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    )
    for red, green, blue in source_pixels:
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        saturation = 0.0 if maximum == 0 else (maximum - minimum) / maximum
        hue = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)[0]
        is_green = saturation > 0.16 and 0.19 <= hue <= 0.48
        is_dark_structure = maximum < 92
        values.append(255 if is_green or is_dark_structure else 0)
    mask.putdata(values)
    mask = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(7))

    # Fill enclosed highlight holes while keeping the outside transparent.
    pixels = mask.load()
    width, height = mask.size
    outside = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        stack.extend(((0, y), (width - 1, y)))
    while stack:
        x, y = stack.pop()
        index = y * width + x
        if outside[index] or pixels[x, y] >= 128:
            continue
        outside[index] = 1
        if x:
            stack.append((x - 1, y))
        if x + 1 < width:
            stack.append((x + 1, y))
        if y:
            stack.append((x, y - 1))
        if y + 1 < height:
            stack.append((x, y + 1))
    for y in range(height):
        for x in range(width):
            if not outside[y * width + x]:
                pixels[x, y] = 255
    # Pull the matte inward before feathering so the generated checkerboard
    # cannot leave a pale fringe after the 512 -> 32 px runtime reduction.
    return mask.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.GaussianBlur(1.0))


def slice_sheet(source: Path, output_dir: Path) -> None:
    sheet = Image.open(source).convert("RGB")
    cell_width = sheet.width // FRAME_COUNT
    cells: list[tuple[Image.Image, Image.Image, tuple[int, int, int, int]]] = []
    max_extent = 0
    for index in range(FRAME_COUNT):
        left = index * cell_width
        right = sheet.width if index == FRAME_COUNT - 1 else (index + 1) * cell_width
        cell = sheet.crop((left, 0, right, sheet.height))
        mask = foreground_mask(cell)
        bounds = mask.getbbox()
        if bounds is None:
            raise RuntimeError(f"no sprite found in frame {index}")
        max_extent = max(max_extent, bounds[2] - bounds[0], bounds[3] - bounds[1])
        cells.append((cell, mask, bounds))

    common_side = math.ceil(max_extent * 1.10)
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, (cell, mask, bounds) in enumerate(cells):
        center_x = (bounds[0] + bounds[2]) // 2
        center_y = (bounds[1] + bounds[3]) // 2
        left = center_x - common_side // 2
        top = center_y - common_side // 2
        crop_box = (left, top, left + common_side, top + common_side)
        rgba = cell.convert("RGBA")
        rgba.putalpha(mask)
        frame = rgba.crop(crop_box).resize(
            (OUTPUT_SIZE, OUTPUT_SIZE),
            Image.Resampling.LANCZOS,
        )
        frame.save(output_dir / f"pulse_sac_{index:02}.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    slice_sheet(args.source, args.output_dir)


if __name__ == "__main__":
    main()
