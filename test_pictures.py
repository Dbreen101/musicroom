"""A picture is made ready for the rooms server on the computer of the person who chose it.

On 25 Nov 2026 a photo AirDropped from a phone could not be added to Daithí's public
room: an iPhone photo is a HEIC, and the rooms server reads JPEG / PNG / WebP / GIF only
(its guard, which stays). So the app changes it first (mr_pictures). This proves:
- a picture that is already fine goes through untouched, byte for byte;
- a HEIC becomes a JPEG of the same size (on a Mac, with the Mac's own tool);
- a picture stored on its side is turned upright (but not an artist's work);
- one too big for the server is made smaller, and keeps its see-through parts;
- what can't be changed is refused in words a person can act on;
- everything it hands on is something the server's own guard opens.

Run:  ./venv/bin/python test_pictures.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ); os.chdir(PROJ)
TMP = tempfile.mkdtemp(prefix="mr_pictures_")
os.environ.setdefault("MR_GR_DB", os.path.join(TMP, "gr.db"))
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

from PIL import Image
import mr_pictures as P
import gr_server

def made(fmt, size=(600, 400), mode="RGB", **kw):
    im = Image.new(mode, size, (200, 60, 40, 120) if mode == "RGBA" else (200, 60, 40))
    im.paste((20, 20, 20, 255) if mode == "RGBA" else (20, 20, 20), (0, 0, size[0] // 4, size[1] // 4))
    b = io.BytesIO(); im.save(b, fmt, **kw); return b.getvalue()
def opened(data): return Image.open(io.BytesIO(data))
def server_reads(data):
    try: gr_server._open_picture(data); return True
    except Exception: return False

# ── already fine: untouched ──
for fmt, mime in (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp"), ("GIF", "image/gif")):
    d = made(fmt)
    out, name, m = P.sendable(d, "cover." + fmt.lower())
    chk(out == d and m == mime and name == "cover." + fmt.lower() and P.kind_of(d) == fmt,
        f"a {fmt} that is already fine goes through untouched")

# ── a phone's HEIC ──
jpg = made("JPEG", (1200, 800), quality=90)
heic = None
if sys.platform == "darwin" and os.path.exists(P.SIPS):
    a, b = os.path.join(TMP, "a.jpg"), os.path.join(TMP, "a.heic")
    open(a, "wb").write(jpg)
    subprocess.run([P.SIPS, "-s", "format", "heic", a, "--out", b], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    heic = open(b, "rb").read() if os.path.exists(b) else None
if heic:
    chk(P.kind_of(heic) == "HEIC" and not server_reads(heic), "(a HEIC is what the rooms server refuses — the bug)")
    out, name, m = P.sendable(heic, "IMG_0042.HEIC")
    im = opened(out)
    chk(im.format == "JPEG" and m == "image/jpeg" and name == "IMG_0042.jpg", "a HEIC becomes a JPEG, named as one")
    chk(im.size == (1200, 800), "at the size it was (not blown up)")
    chk(server_reads(out), "and the rooms server reads it")
    out, name, m = P.sendable(heic, "work.heic", turn=False)
    chk(opened(out).format == "JPEG", "an artist's work in HEIC is changed too (the server could not keep it otherwise)")
    real = P.SIPS; P.SIPS = "/nowhere/sips"
    try:
        P.sendable(heic, "IMG_0042.HEIC"); chk(False, "with no tool to change it, a HEIC is refused in words")
    except P.NotAPicture as e:
        chk("HEIC" in str(e) and "JPEG" in str(e), f"with no tool to change it, a HEIC is refused in words ({str(e)[:50]}…)")
    P.SIPS = real
else:
    print("  SKIP  (no Mac picture tool here: the HEIC checks are passed over)")
fake_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
real = P.SIPS; P.SIPS = "/nowhere/sips"
try:
    P.sendable(fake_heic, "x.heic"); chk(False, "a HEIC on a computer that can't change it says what it is and what to do")
except P.NotAPicture as e:
    chk("HEIC" in str(e) and "iPhone" in str(e), "a HEIC on a computer that can't change it says what it is and what to do")
P.SIPS = real

# ── stored on its side ──
side = Image.new("RGB", (600, 400), (10, 120, 200)); ex = side.getexif(); ex[0x0112] = 6
b = io.BytesIO(); side.save(b, "JPEG", exif=ex); side = b.getvalue()
out, name, m = P.sendable(side, "photo.jpg")
im = opened(out)
chk(im.size == (400, 600) and im.getexif().get(0x0112, 1) == 1, "a photo stored on its side is turned the right way up")
out2, _, _ = P.sendable(side, "work.jpg", turn=False)
chk(out2 == side, "but an artist's work is left exactly as sent")

# ── too big for the server ──
huge = made("JPEG", (7600, 5600), quality=60)                 # 42.6 million dots
chk(not server_reads(huge), "(a picture of over 40 million dots is what the rooms server refuses)")
out, name, m = P.sendable(huge, "huge.jpeg")
im = opened(out)
chk(max(im.size) <= P.LONG_SIDE and abs(im.size[0] / im.size[1] - 7600 / 5600) < 0.01 and server_reads(out),
    f"it is made smaller, in the same shape, and the server reads it ({im.size[0]}×{im.size[1]})")
glass = made("PNG", (7000, 5400), mode="RGBA")
out, name, m = P.sendable(glass, "glass.png")
im = opened(out)
chk(im.format == "PNG" and im.mode == "RGBA" and name == "glass.png" and max(im.size) <= P.LONG_SIDE and server_reads(out),
    "a see-through picture made smaller is still see-through")

# ── not a picture ──
for data, words in ((b"", "empty"), (b"just some words, not a picture at all", "isn't a picture"), (jpg[:300], "damaged")):
    try:
        P.sendable(data, "thing.jpg"); chk(False, f"refused in words: {words}")
    except P.NotAPicture as e:
        chk(words in str(e), f"refused in words: “{str(e)[:60]}”")
chk(P.kind_of(b"II*\x00" + b"\x00" * 20) == "TIFF" and P.kind_of(b"BM" + b"\x00" * 20) == "BMP"
    and P.kind_of(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 20) == "AVIF" and P.kind_of(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 20) == "",
    "other kinds are named by their first bytes (a film is not called a picture)")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
