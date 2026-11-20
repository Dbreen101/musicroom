#!/usr/bin/env python3
"""
Generate Music Room's native macOS app icon.

Visual: a vellum manuscript medallion floating on a tile of the
forest-floor texture — same Book-of-Kells-in-an-Irish-forest mood as the
rest of the app. The centre carries the illuminated "M" of the nav logo:
oxblood letter on warm parchment, gilded inner ring, a faint gold
illumination glow behind it.

Output:
  native/AppIcon.iconset/      full Apple-style iconset (16…1024 + @2x)
  native/AppIcon.icns          baked .icns ready to drop in BUNDLE(icon=…)

Run:
  venv/bin/python native/gen_icon.py
"""
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NATIVE_DIR  = Path(__file__).resolve().parent
PROJECT_DIR = NATIVE_DIR.parent
TEXTURE     = PROJECT_DIR / "static" / "textures" / "forest_floor.jpg"

ICONSET_DIR = NATIVE_DIR / "AppIcon.iconset"
ICNS_PATH   = NATIVE_DIR / "AppIcon.icns"

# Master size — macOS squircle masks apply to the whole canvas, so we
# leave ~5% padding so the medallion sits comfortably inside the rounded
# square the OS draws around app icons.
SIZE     = 1024
PADDING  = int(SIZE * 0.06)

# Palette — pulled from style.css :root so the icon sits in the app's voice.
VELLUM       = (244, 233, 201)   # parchment medallion fill
VELLUM_RIM   = (218, 197, 142)   # subtle inner shadow at the medallion edge
GOLD         = (168, 130, 44)    # --gold
GOLD_BRIGHT  = (220, 180, 90)
OXBLOOD      = (156, 59, 44)     # --oxblood
INK          = (46, 39, 24)
GROUND_DARK  = (47, 42, 28)      # fallback ground colour if no texture

# Serif fonts that look right for the illuminated "M". Hoefler is ideal;
# fall back gracefully on Macs that don't ship it (rare but possible).
SERIF_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Hoefler Text.ttc",
    "/System/Library/Fonts/Supplemental/Baskerville.ttc",
    "/System/Library/Fonts/Times.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]


def _serif(size_px: int) -> ImageFont.FreeTypeFont:
    for path in SERIF_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size_px)
            except (OSError, ValueError):
                continue
    # Final fallback — PIL's default raster bitmap; ugly but won't crash.
    return ImageFont.load_default()


def _ground_layer(size: int) -> Image.Image:
    """A square crop of the forest floor texture for the icon background."""
    if not TEXTURE.exists():
        return Image.new("RGB", (size, size), GROUND_DARK)
    tex = Image.open(TEXTURE).convert("RGB")
    # Centre-crop to square, then resize to icon size.
    w, h = tex.size
    s = min(w, h)
    tex = tex.crop(((w - s) // 2, (h - s) // 2,
                    (w - s) // 2 + s, (h - s) // 2 + s))
    return tex.resize((size, size), Image.LANCZOS)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    """A soft-edged rounded-square alpha mask for the medallion."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _glow(size: int, radius: int, color: tuple, opacity: int) -> Image.Image:
    """A soft glow blob, e.g. behind the letter to suggest illumination."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = size // 2
    d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
              fill=(*color, opacity))
    return layer.filter(ImageFilter.GaussianBlur(radius // 3))


def make_icon() -> Image.Image:
    # 1. forest-floor ground tile
    base = _ground_layer(SIZE).convert("RGBA")

    # 2. medallion — vellum rounded-square sitting on the ground
    medallion_size = SIZE - 2 * PADDING
    medallion_radius = int(medallion_size * 0.22)
    medallion = Image.new("RGBA", (medallion_size, medallion_size), VELLUM)

    # Add a subtle inner rim by drawing a slightly-smaller rectangle inset
    rim_inset = int(medallion_size * 0.04)
    rim = Image.new("RGBA", (medallion_size, medallion_size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle(
        (rim_inset, rim_inset, medallion_size - rim_inset, medallion_size - rim_inset),
        radius=medallion_radius - rim_inset // 2,
        outline=(*VELLUM_RIM, 180), width=max(2, medallion_size // 220),
    )
    medallion = Image.alpha_composite(medallion, rim)

    # Gold inner ring — Book-of-Kells illumination border
    gold_inset = int(medallion_size * 0.085)
    gold = Image.new("RGBA", (medallion_size, medallion_size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gold)
    gd.rounded_rectangle(
        (gold_inset, gold_inset,
         medallion_size - gold_inset, medallion_size - gold_inset),
        radius=int((medallion_radius - gold_inset // 2) * 0.95),
        outline=(*GOLD, 220), width=max(3, medallion_size // 160),
    )
    medallion = Image.alpha_composite(medallion, gold)

    # Gentle gold glow behind where the letter will sit
    glow = _glow(medallion_size, medallion_size // 3, GOLD_BRIGHT, 70)
    medallion = Image.alpha_composite(medallion, glow)

    # 3. the illuminated "M"
    # Hoefler Text "M" sits big and confident in the centre.
    letter_size = int(medallion_size * 0.78)
    font = _serif(letter_size)
    letter_layer = Image.new("RGBA", (medallion_size, medallion_size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(letter_layer)

    # Compute centred position from the actual bbox (Hoefler's M has
    # slightly asymmetric vertical metrics).
    bbox = ld.textbbox((0, 0), "M", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (medallion_size - tw) // 2 - bbox[0]
    ty = (medallion_size - th) // 2 - bbox[1] - int(medallion_size * 0.02)

    # Faint oxblood shadow → the illuminated-letter offset the rest of the
    # app uses on its drop-caps.
    ld.text((tx + max(3, medallion_size // 220), ty + max(3, medallion_size // 220)),
            "M", font=font, fill=(*OXBLOOD, 80))
    # Gold serif behind …
    ld.text((tx - 1, ty - 1), "M", font=font, fill=(*GOLD, 200))
    # … and the oxblood letter on top.
    ld.text((tx, ty), "M", font=font, fill=(*OXBLOOD, 255))

    medallion = Image.alpha_composite(medallion, letter_layer)

    # 4. composite medallion onto the ground with a soft drop shadow
    shadow = Image.new("RGBA", (medallion_size + 60, medallion_size + 60), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((30, 36, medallion_size + 30, medallion_size + 36),
                         radius=medallion_radius, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    base.alpha_composite(shadow, (PADDING - 30, PADDING - 30))
    base.alpha_composite(medallion, (PADDING, PADDING))

    return base.convert("RGB")


# The Apple-style iconset macOS expects.
ICONSET = [
    ("icon_16x16.png",       16),
    ("icon_16x16@2x.png",    32),
    ("icon_32x32.png",       32),
    ("icon_32x32@2x.png",    64),
    ("icon_128x128.png",    128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png",    256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png",    512),
    ("icon_512x512@2x.png",1024),
]


def main():
    print(f"Building Music Room icon at {SIZE}x{SIZE}…")
    master = make_icon()
    master_path = NATIVE_DIR / "AppIcon_1024.png"
    master.save(master_path, "PNG")
    print(f"  master → {master_path.relative_to(PROJECT_DIR)}")

    ICONSET_DIR.mkdir(exist_ok=True)
    for name, size in ICONSET:
        img = master.resize((size, size), Image.LANCZOS)
        img.save(ICONSET_DIR / name, "PNG", optimize=True)
    print(f"  iconset → {ICONSET_DIR.relative_to(PROJECT_DIR)} ({len(ICONSET)} sizes)")

    # iconutil is the macOS-supplied tool that combines an iconset into
    # a single .icns. PyInstaller / Finder both like .icns better than
    # loose PNGs.
    res = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_PATH)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print("iconutil failed:")
        print(res.stderr)
        return 1
    kb = ICNS_PATH.stat().st_size // 1024
    print(f"  ✓ {ICNS_PATH.relative_to(PROJECT_DIR)} ({kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
