from pathlib import Path
from collections import deque

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def quantize_rgba(image: Image.Image, colors: int) -> Image.Image:
    alpha = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    rgb = image.convert("RGB").quantize(
        colors=colors, method=Image.Quantize.MEDIANCUT
    ).convert("RGB")
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def pixelate(path: Path, size: int, colors: int) -> None:
    source = Image.open(path).convert("RGBA")
    if source.size == (size, size):
        return
    alpha = source.resize((size, size), Image.Resampling.LANCZOS).getchannel("A")
    alpha = alpha.point(lambda value: 255 if value >= 96 else 0)
    rgb = source.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    rgb = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    result.save(path, optimize=True)


def build_player() -> None:
    target = ROOT / "assets/player"
    target.mkdir(parents=True, exist_ok=True)
    source = Image.open(target / "source/falcon_body_sheet_v2.png").convert("RGBA")

    # The generator rendered a checkerboard. Flood-fill only edge-connected neutral
    # pixels so enclosed white armor remains untouched, then convert it to alpha.
    pixels = source.load()
    width, height = source.size
    outside = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        queue.extend(((0, y), (width - 1, y)))

    def is_checker(x: int, y: int) -> bool:
        red, green, blue, _ = pixels[x, y]
        return max(red, green, blue) - min(red, green, blue) <= 18 and 75 <= max(red, green, blue) <= 250

    while queue:
        x, y = queue.popleft()
        offset = y * width + x
        if outside[offset] or not is_checker(x, y):
            continue
        outside[offset] = 1
        if x:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))
    alpha = Image.new("L", source.size, 255)
    alpha.putdata([0 if value else 255 for value in outside])
    source.putalpha(alpha)

    # Detect the four complete silhouettes by transparent gaps. Fixed-width cells
    # clip the diagonal shoulder pods because their visual bounds are wider.
    alpha = source.getchannel("A")
    occupied_columns = [alpha.crop((x, 0, x + 1, height)).getbbox() is not None for x in range(width)]
    column_runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for x, occupied in enumerate((*occupied_columns, False)):
        if occupied and run_start is None:
            run_start = x
        elif not occupied and run_start is not None:
            if x - run_start > 80:
                column_runs.append((run_start, x))
            run_start = None
    if len(column_runs) != 4:
        raise RuntimeError(f"expected four player components, found {len(column_runs)}")
    components: list[Image.Image] = []
    for left, right in column_runs:
        component = source.crop((left, 0, right, height))
        bounds = component.getchannel("A").getbbox()
        if bounds is None:
            raise RuntimeError("empty player component")
        components.append(component.crop(bounds))
    # The generated hulls included a large circular nose port.  The player weapon
    # is now a dorsal turret, so seal that port with a compact armor fairing on
    # each authored angle instead of leaving a misleading second gun muzzle.
    nose_port_fairings = (
        ((47, 28), (53, 27), (57, 31), (56, 35), (52, 38), (47, 35)),
        ((46, 41), (53, 39), (57, 43), (57, 47), (53, 51), (47, 49)),
        ((47, 44), (53, 42), (57, 46), (57, 50), (53, 53), (48, 51)),
    )
    for index, component in enumerate(components[:3]):
        bounds = component.getchannel("A").getbbox()
        if bounds is None:
            raise RuntimeError(f"no player body found in source cell {index}")
        component = component.crop(bounds).transpose(Image.Transpose.ROTATE_90)
        component.thumbnail((50, 50), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.alpha_composite(component, ((64 - component.width) // 2, (64 - component.height) // 2))
        fairing = nose_port_fairings[index]
        draw = ImageDraw.Draw(canvas)
        draw.polygon(fairing, fill=(241, 248, 255, 255))
        draw.line((*fairing[:3],), fill=(213, 232, 238, 255), width=1)
        draw.line((*fairing[3:], fairing[0]), fill=(31, 49, 70, 255), width=1)
        output = quantize_rgba(canvas, 15)
        if index == 0:
            # The user-selected dorsal mount is pixel (22, 32) in the authored
            # top-down hull. Bake that point into the exact center of a square
            # canvas so every 90-degree rotation shares one immutable pivot.
            pivoted = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
            pivoted.alpha_composite(output, (48 - 22, 48 - 32))
            output = pivoted
        output.save(target / f"falcon_body_{index:02}.png", optimize=True)

    gun = components[3]
    bounds = gun.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("no player gun found in source cell")
    gun = gun.crop(bounds)
    gun.thumbnail((39, 13), Image.Resampling.NEAREST)
    gun_canvas = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    # Anchor the gun's rear pivot exactly on the canvas center.  draw_player()
    # centers this canvas on the aircraft's weapon port, so the gun stays seated
    # in that port while rotating instead of orbiting a couple of pixels around it.
    gun_canvas.alpha_composite(gun, (40, 40 - gun.height // 2))
    quantize_rgba(gun_canvas, 15).save(target / "falcon_gun.png", optimize=True)


def build_pulse_sacs() -> None:
    target = ROOT / "assets/enemies/pulse_sac"
    target.mkdir(parents=True, exist_ok=True)
    strip = Image.open(target / "source/pulse_sac_pixel_strip_v2.png").convert("RGBA")
    cell_edges = [round(index * strip.width / 4) for index in range(5)]
    frames: list[Image.Image] = []
    max_side = 0
    for index in range(4):
        cell = strip.crop((cell_edges[index], 0, cell_edges[index + 1], strip.height))
        alpha = cell.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        bounds = alpha.getbbox()
        if bounds is None:
            raise RuntimeError(f"no sprite found in approved frame {index}")
        cell.putalpha(alpha)
        cropped = cell.crop(bounds)
        frames.append(cropped)
        max_side = max(max_side, cropped.width, cropped.height)

    for index, frame in enumerate(frames):
        square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))
        square.alpha_composite(
            frame,
            ((max_side - frame.width) // 2, (max_side - frame.height) // 2),
        )
        output = square.resize((40, 40), Image.Resampling.NEAREST)
        quantize_rgba(output, 15).save(target / f"pulse_sac_{index:02}.png", optimize=True)


def main() -> None:
    build_pulse_sacs()
    for path in sorted((ROOT / "assets/effects/blood_splats").glob("blood_splats_*.png")):
        pixelate(path, 32, 8)
    build_player()


if __name__ == "__main__":
    main()
