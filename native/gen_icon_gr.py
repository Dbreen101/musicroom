#!/usr/bin/env python3
"""
The Green Room app's icon: the GR wordmark, as the front door sets it.

"The Music Room." in Instrument Serif (the app's display face, bundled in
static/fonts/instrumentserif), ink on paper, three lines, set tight
(letter-spacing -.035em, line-height .92 — the values of .lg-side__wordmark in
static/css/ui.css). Paper #f2efe8, ink #161513: the light look's two tones.
Nothing else is on it.

Output (the old P1 icon — AppIcon.* — is left as it is):
  native/AppIcon-GR.iconset/   the Apple iconset (16…1024 + @2x)
  native/AppIcon-GR.icns       for the Mac apps
  native/AppIcon-GR_1024.png   the Windows build makes its .ico from this

Run:  venv/bin/python native/gen_icon_gr.py
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NATIVE = Path(__file__).resolve().parent
FONT = NATIVE.parent / "static" / "fonts" / "instrumentserif" / "instrumentserif.woff2"
ICONSET = NATIVE / "AppIcon-GR.iconset"
ICNS = NATIVE / "AppIcon-GR.icns"
PNG = NATIVE / "AppIcon-GR_1024.png"

PAPER = (242, 239, 232)
INK = (22, 21, 19)
RULE = (200, 195, 182)

SIZE = 1024
S = 4                      # drawn 4x larger, then scaled down (smooth edges)
BODY = 824                 # Apple's icon grid: an 824 tile on a 1024 canvas
RADIUS = 185
LINES = ["The", "Music", "Room."]
TRACK = -0.035             # em
LEADING = 0.92             # em


def line_width(font, text, px):
    return font.getlength(text) + TRACK * px * (len(text) - 1)


def draw_line(d, font, text, x, y, px):
    # each letter where the whole line's layout puts it (kerning kept), pulled in by the tracking
    for i, ch in enumerate(text):
        d.text((x + font.getlength(text[:i]) + TRACK * px * i, y), ch, font=font, fill=INK, anchor="ls")


def render():
    big = SIZE * S
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    off = (SIZE - BODY) // 2 * S
    tile = (off, off, off + BODY * S, off + BODY * S)
    d.rounded_rectangle(tile, radius=RADIUS * S, fill=PAPER, outline=RULE, width=2 * S)

    # set the wordmark on its own sheet, then fit what was actually drawn inside even margins
    px = 300 * S
    font = ImageFont.truetype(str(FONT), px)
    step = LEADING * px
    sheet = Image.new("RGBA", (int(px * 4), int(px * 4)), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheet)
    for i, t in enumerate(LINES):
        draw_line(sd, font, t, px * 0.2, px * 1.2 + i * step, px)
    words = sheet.crop(sheet.getbbox())
    room = int(BODY * (1 - 2 * 0.17)) * S
    k = min(room / words.width, room / words.height)
    words = words.resize((int(words.width * k), int(words.height * k)), Image.LANCZOS)
    x = off + (BODY * S - words.width) // 2
    y = off + (BODY * S - words.height) // 2
    img.alpha_composite(words, (x, y))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    master = render()
    master.save(PNG)
    ICONSET.mkdir(exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            n = base * scale
            name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
            master.resize((n, n), Image.LANCZOS).save(ICONSET / name)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)], check=True)
    print(f"wrote {PNG.name}, {ICONSET.name}/, {ICNS.name}")


if __name__ == "__main__":
    main()
