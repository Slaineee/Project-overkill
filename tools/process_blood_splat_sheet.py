from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageFilter


COLUMNS = 5
ROWS = 3
OUTPUT_SIZE = 256


def extract_red_foreground(cell: Image.Image, source_has_alpha: bool) -> Image.Image:
    if source_has_alpha:
        return cell.convert("RGBA")

    output: list[tuple[int, int, int, int]] = []
    rgb = cell.convert("RGB")
    source_pixels = (
        rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    )
    for red, green, blue in source_pixels:
        redness = red - max(green, blue)
        amount = max(0.0, min(1.0, (redness - 2.0) / 75.0))
        amount = amount * amount * (3.0 - 2.0 * amount)
        if amount <= 0.0:
            output.append((0, 0, 0, 0))
            continue
        edge_red = (140, 22, 40)
        center_red = (112, 18, 36)
        color = tuple(
            round(edge + (center - edge) * amount)
            for edge, center in zip(edge_red, center_red)
        )
        output.append((*color, round(255 * amount)))

    extracted = Image.new("RGBA", cell.size)
    extracted.putdata(output)
    extracted.putalpha(extracted.getchannel("A").filter(ImageFilter.GaussianBlur(7.5)))
    return extracted


def slice_sheet(source: Path, output_dir: Path) -> None:
    source_image = Image.open(source)
    source_has_alpha = source_image.mode == "RGBA" and source_image.getchannel("A").getextrema()[0] < 255
    sheet = source_image.convert("RGBA")
    transparent_sheet = extract_red_foreground(sheet, source_has_alpha)
    source_dir = output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    transparent_sheet.save(source_dir / "blood_splats_sheet_flat_transparent.png", optimize=True)
    cell_width = sheet.width // COLUMNS
    cell_height = sheet.height // ROWS
    output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(COLUMNS * ROWS):
        row, column = divmod(index, COLUMNS)
        cell = transparent_sheet.crop(
            (column * cell_width, row * cell_height, (column + 1) * cell_width, (row + 1) * cell_height)
        )
        rgba = cell.convert("RGBA")
        mask = rgba.getchannel("A")
        bounds = mask.getbbox()
        if bounds is None:
            raise RuntimeError(f"no red splash found in cell {index}")
        side = math.ceil(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * 1.18)
        center_x = (bounds[0] + bounds[2]) // 2
        center_y = (bounds[1] + bounds[3]) // 2
        left = center_x - side // 2
        top = center_y - side // 2
        rgba.putalpha(mask)
        rgba.crop((left, top, left + side, top + side)).resize(
            (OUTPUT_SIZE, OUTPUT_SIZE), Image.Resampling.LANCZOS
        ).save(output_dir / f"blood_splats_{index:02}.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    slice_sheet(args.source, args.output_dir)


if __name__ == "__main__":
    main()
