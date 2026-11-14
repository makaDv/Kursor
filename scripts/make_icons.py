"""Render the PWA PNG icons (same artwork as client/public/icons/icon.svg).

Usage: server/.venv/Scripts/python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "client" / "public" / "icons"
POINTER = [(150, 112), (150, 392), (222, 322), (270, 420), (318, 398), (270, 302), (370, 302)]


def render(size: int, rounded: bool = True) -> Image.Image:
    scale = 4  # supersample for smooth edges
    big = 512 * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg = (11, 15, 23, 255)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=112 * scale, fill=bg)
    else:
        draw.rectangle((0, 0, big, big), fill=bg)

    # Diagonal indigo -> cyan gradient masked by the pointer shape.
    grad = Image.new("RGBA", (big, big))
    gd = ImageDraw.Draw(grad)
    a, b = (99, 102, 241), (6, 182, 212)
    for i in range(0, 2 * big, scale):
        t = i / (2 * big)
        color = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)) + (255,)
        gd.line([(i, 0), (0, i)], fill=color, width=scale * 2)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).polygon([(x * scale, y * scale) for x, y in POINTER], fill=255)
    img.paste(grad, (0, 0), mask)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(192).save(OUT / "icon-192.png")
    render(512, rounded=False).save(OUT / "icon-512.png")  # maskable: full bleed
    render(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    print(f"Icons written to {OUT}")


if __name__ == "__main__":
    main()
