"""Render the PWA PNG icons (same artwork as client/public/icons/icon.svg).

Also renders the Android launcher icons and splash screens.

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



# ---- Android (Capacitor project in client/android) ---------------------------
ANDROID_RES = Path(__file__).resolve().parents[1] / "client" / "android" / "app" / "src" / "main" / "res"
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
BG = (11, 15, 23)


def render_foreground(size: int) -> Image.Image:
    """Adaptive-icon foreground: pointer only, inside the 66/108 safe zone."""
    full = render(512, rounded=False)
    art = full.crop((110, 90, 400, 440))  # pointer bounding box with margin
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    target = int(size * 0.55)
    art.thumbnail((target, target), Image.Resampling.LANCZOS)
    # drop the dark background of the crop: keep only bright (gradient) pixels
    px = art.load()
    for y in range(art.height):
        for x in range(art.width):
            r, g, b, a = px[x, y]
            if r + g + b < 120:
                px[x, y] = (0, 0, 0, 0)
    canvas.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return canvas


def android() -> None:
    if not ANDROID_RES.exists():
        return
    for name, scale in DENSITIES.items():
        d = ANDROID_RES / f"mipmap-{name}"
        d.mkdir(exist_ok=True)
        legacy = round(48 * scale)
        render(legacy).save(d / "ic_launcher.png")
        round_icon = render(legacy, rounded=False)
        mask = Image.new("L", round_icon.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, legacy - 1, legacy - 1), fill=255)
        round_icon.putalpha(mask)
        round_icon.save(d / "ic_launcher_round.png")
        render_foreground(round(108 * scale)).save(d / "ic_launcher_foreground.png")

    values = ANDROID_RES / "values" / "ic_launcher_background.xml"
    values.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        '    <color name="ic_launcher_background">#0B0F17</color>\n</resources>\n',
        encoding="utf-8",
    )

    # Splash screens: replace every existing splash.png with the PadLink logo.
    logo = render(512)
    for splash in ANDROID_RES.glob("drawable*/splash.png"):
        with Image.open(splash) as old:
            w, h = old.size
        img = Image.new("RGB", (w, h), BG)
        side = int(min(w, h) * 0.35)
        icon = logo.resize((side, side), Image.Resampling.LANCZOS)
        img.paste(icon, ((w - side) // 2, (h - side) // 2), icon)
        img.save(splash)
    print(f"Android icons/splash written to {ANDROID_RES}")


# ---- iOS (Capacitor project in client/ios) -----------------------------------
IOS_ASSETS = Path(__file__).resolve().parents[1] / "client" / "ios" / "App" / "App" / "Assets.xcassets"


def ios() -> None:
    if not IOS_ASSETS.exists():
        return
    # App Store icon: 1024x1024, opaque, square (iOS applies the rounded mask itself).
    render(1024, rounded=False).convert("RGB").save(IOS_ASSETS / "AppIcon.appiconset" / "AppIcon-512@2x.png")
    logo = render(512)
    for splash in (IOS_ASSETS / "Splash.imageset").glob("*.png"):
        with Image.open(splash) as old:
            w, h = old.size
        img = Image.new("RGB", (w, h), BG)
        side = int(min(w, h) * 0.2)
        icon = logo.resize((side, side), Image.Resampling.LANCZOS)
        img.paste(icon, ((w - side) // 2, (h - side) // 2), icon)
        img.save(splash)
    print(f"iOS icon/splash written to {IOS_ASSETS}")


# ---- Windows desktop app (server/kursor/assets) -------------------------------
DESKTOP_ASSETS = Path(__file__).resolve().parents[1] / "server" / "kursor" / "assets"


def desktop() -> None:
    DESKTOP_ASSETS.mkdir(parents=True, exist_ok=True)
    big = render(256)
    big.save(DESKTOP_ASSETS / "kursor.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    tray = render(64)
    tray.save(DESKTOP_ASSETS / "tray.png")
    active = tray.copy()
    ImageDraw.Draw(active).ellipse((38, 38, 63, 63), fill=(16, 185, 129, 255), outline=(11, 15, 23, 255), width=3)
    active.save(DESKTOP_ASSETS / "tray-active.png")
    print(f"Desktop icons written to {DESKTOP_ASSETS}")


if __name__ == "__main__":
    main()
    android()
    ios()
    desktop()
