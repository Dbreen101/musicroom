"""Getting a picture ready to send to the rooms server.

The rooms server reads four kinds of picture (JPEG, PNG, WebP, GIF) and nothing over
40 million dots: that is its guard, and it stays. But a photo that comes off a phone is
often a HEIC, can be bigger than that, and is often stored on its side with a note
saying which way is up. So the APP — on the computer of the person who chose the file —
turns such a picture into one the server takes, before it is sent:

- a kind the server can't read (HEIC / HEIF, TIFF, BMP, AVIF…) becomes a JPEG. On a Mac
  the Mac's own picture tool does it (`sips`, part of macOS: nothing to install). Where
  there is no such tool the person is told, in words, what the picture is and what to do;
- a picture that is too big is made smaller (the server keeps 1800 to 2400 dots a side);
- a picture stored on its side is turned the right way up (not for an artist's work,
  which is kept as it was sent).

A picture that is already fine goes through untouched, byte for byte.

    data, filename, mime = mr_pictures.sendable(data, filename)

No Flask, no database.
"""

import io
import os
import subprocess
import sys
import tempfile

READ = ("JPEG", "PNG", "WEBP", "GIF")      # what the rooms server reads (gr_server._open_picture)
MAX_PIXELS = 36_000_000                    # the server refuses over 40 million
MAX_BYTES = 20 * 1024 * 1024               # the server refuses a picture over 25 MB
LONG_SIDE = 4096                           # a picture made smaller is this long at most
SIPS = "/usr/bin/sips"
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


class NotAPicture(Exception):
    """The file can't be made into a picture the server takes. Its words are for the person."""


def kind_of(data):
    """A plain name for what the file is, from its first bytes: 'HEIC', 'TIFF', 'BMP',
    'AVIF', one of READ, or ''."""
    head = bytes(data[:32])
    if head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "AVIF"
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"):
            return "HEIC"
        return ""
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if head[:2] == b"BM":
        return "BMP"
    return ""


def _open(data):
    """The picture, opened as the server would open it — or None."""
    import warnings

    from PIL import Image
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)   # (a big one is made smaller below)
            return Image.open(io.BytesIO(data), formats=list(READ))
    except Exception:
        return None


def _with_the_macs_tool(data, kind):
    """A JPEG of a picture the Mac can read, made by macOS's own `sips`. → bytes or None."""
    if sys.platform != "darwin" or not os.path.exists(SIPS) or kind in READ:
        return None
    ext = {"HEIC": ".heic", "TIFF": ".tiff", "BMP": ".bmp", "AVIF": ".avif"}.get(kind, ".img")
    try:
        with tempfile.TemporaryDirectory(prefix="mr_picture_") as tmp:
            src, out = os.path.join(tmp, "in" + ext), os.path.join(tmp, "out.jpg")
            with open(src, "wb") as f:
                f.write(data)
            # (no size given: sips would make a small picture BIGGER to reach it. One too big is made smaller after)
            r = subprocess.run([SIPS, "-s", "format", "jpeg", "-s", "formatOptions", "92", src, "--out", out],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
            if r.returncode != 0 or not os.path.exists(out):
                return None
            with open(out, "rb") as f:
                made = f.read()
        return made if kind_of(made) == "JPEG" else None
    except Exception:
        return None


def _words_for(kind):
    if kind == "HEIC":
        return ("That picture is a HEIC (the kind an iPhone takes), and this computer can't change it. "
                "Save it as a JPEG or a PNG first, then add it.")
    if kind in READ:
        return "That picture is too big, or damaged. Save a smaller copy as a JPEG, then add it."
    if kind:
        return f"That picture is a {kind}. Save it as a JPEG or a PNG first, then add it."
    return "That file isn't a picture the Music Room can read. Use a JPEG, PNG, WebP or GIF."


def _name(filename, fmt):
    base = os.path.splitext(os.path.basename(filename or "") or "picture")[0] or "picture"
    return base + _EXT[fmt]


def sendable(data, filename="", turn=True):
    """→ (data, filename, mime) ready for the rooms server. Untouched when it is already
    fine. Raises NotAPicture, with words for the person, when it can't be made so.

    `turn=False` leaves a picture stored on its side as it is (an artist's work is kept
    as sent)."""
    from PIL import Image, ImageOps

    data = bytes(data or b"")
    if not data:
        raise NotAPicture("That file is empty.")
    img = _open(data)
    if img is None:
        kind = kind_of(data)
        made = _with_the_macs_tool(data, kind)
        if not made:
            raise NotAPicture(_words_for(kind))
        data, filename = made, _name(filename, "JPEG")
        img = _open(data)
        if img is None:
            raise NotAPicture(_words_for(kind))
    fmt = img.format
    try:
        big = img.width * img.height > MAX_PIXELS or len(data) > MAX_BYTES
        try:
            on_its_side = turn and img.getexif().get(0x0112, 1) in (2, 3, 4, 5, 6, 7, 8)
        except Exception:
            on_its_side = False
        if not big and not on_its_side:
            return data, (filename or _name("", fmt)), _MIME[fmt]
        if getattr(img, "is_animated", False) and not big:
            return data, (filename or _name("", fmt)), _MIME[fmt]
        if big and fmt == "JPEG":
            img.draft("RGB", (LONG_SIDE, LONG_SIDE))        # (read it small: little memory for a huge photo)
        if turn:
            img = ImageOps.exif_transpose(img)
        alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if alpha else "RGB")
        if big:
            img.thumbnail((LONG_SIDE, LONG_SIDE))
        out = io.BytesIO()
        if alpha:
            img.save(out, "PNG", optimize=True)
            return out.getvalue(), _name(filename, "PNG"), "image/png"
        img.save(out, "JPEG", quality=92)
        return out.getvalue(), _name(filename, "JPEG"), "image/jpeg"
    except NotAPicture:
        raise
    except Exception:
        # (a picture so big the picture library won't open it, or one that is broken inside)
        raise NotAPicture("That picture is too big, or damaged. Save a smaller copy as a JPEG, then add it.")
