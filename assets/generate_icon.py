from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "line_tracker.ico"
PREVIEW_PATH = ROOT / "line_tracker_preview.png"

CANVAS_SIZE = 1024
ICON_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def draw_background(canvas: Image.Image) -> None:
    width, height = canvas.size
    base = Image.new("RGBA", canvas.size, "#10171f")
    base_draw = ImageDraw.Draw(base)

    # Layered rounded cards for a polished app-icon look.
    base_draw.rounded_rectangle((36, 36, width - 36, height - 36), radius=220, fill="#152029")
    base_draw.rounded_rectangle((60, 60, width - 60, height - 60), radius=196, fill="#1a2630")
    base_draw.rounded_rectangle((84, 84, width - 84, height - 84), radius=172, fill="#1e2d37")

    vignette = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse((160, 84, width - 84, height - 48), fill=(118, 246, 214, 34))
    vignette_draw.ellipse((84, 324, width - 220, height - 120), fill=(110, 195, 255, 24))
    vignette = vignette.filter(ImageFilter.GaussianBlur(60))

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle((66, 66, width - 66, height - 66), radius=188, outline=(123, 239, 214, 255), width=16)
    glow = glow.filter(ImageFilter.GaussianBlur(14))

    canvas.alpha_composite(base)
    canvas.alpha_composite(vignette)
    canvas.alpha_composite(glow)


def draw_bars(canvas: Image.Image) -> None:
    draw = ImageDraw.Draw(canvas)
    left = 208
    bottom = 760
    bar_width = 92
    gap = 42
    heights = [150, 250, 360, 500]
    fills = ["#2a3c44", "#4db59f", "#7fe3cb", "#b5fff0"]

    for index, (height, fill) in enumerate(zip(heights, fills)):
        x0 = left + index * (bar_width + gap)
        y0 = bottom - height
        x1 = x0 + bar_width
        draw.rounded_rectangle((x0, y0, x1, bottom), radius=28, fill=fill)


def draw_chart_line(canvas: Image.Image) -> None:
    line_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(line_layer)
    points = [
        (212, 680),
        (346, 590),
        (480, 514),
        (614, 420),
        (770, 274),
    ]

    draw.line(points, fill="#f6fbff", width=32, joint="curve")
    draw.line(points, fill="#8cefd4", width=18, joint="curve")

    for point in points[:-1]:
        x, y = point
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill="#f6fbff")
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill="#79e0c3")

    end_x, end_y = points[-1]
    draw.ellipse((end_x - 40, end_y - 40, end_x + 40, end_y + 40), fill="#ff6c8c")
    draw.ellipse((end_x - 18, end_y - 18, end_x + 18, end_y + 18), fill="#fff1f5")

    line_layer = line_layer.filter(ImageFilter.GaussianBlur(0.3))
    canvas.alpha_composite(line_layer)


def draw_badge(canvas: Image.Image) -> None:
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)

    draw.rounded_rectangle((700, 650, 884, 834), radius=56, fill="#ff8758")
    draw.rounded_rectangle((716, 666, 868, 818), radius=48, fill="#ff996a")
    draw.rounded_rectangle((742, 726, 842, 758), radius=16, fill="#fff7ef")
    draw.rounded_rectangle((776, 692, 808, 792), radius=16, fill="#fff7ef")

    shadow = badge.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(badge)


def build_icon() -> Image.Image:
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw_background(canvas)
    draw_bars(canvas)
    draw_chart_line(canvas)
    draw_badge(canvas)

    mask = rounded_mask(canvas.size, 220)
    alpha = ImageChops.multiply(canvas.getchannel("A"), mask)
    canvas.putalpha(alpha)
    return canvas


def main() -> None:
    image = build_icon()
    image.save(PREVIEW_PATH)
    image.save(ICON_PATH, sizes=ICON_SIZES)
    print(f"Wrote {ICON_PATH}")
    print(f"Wrote {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
