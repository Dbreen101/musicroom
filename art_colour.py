"""
art_colour.py — a representative dominant colour for a piece of album art.

Pillow only (already a dependency). The Music Room stores no visual colour for
covers — colour_code is empty and brightness_score is an AUDIO metric — so to
let the user sort the grid by album-art colour we extract one here: the colour
that best stands for the cover. A muddy average is useless (everything goes
grey-brown), so we quantize to a small palette and score each cluster by how
much of the cover it covers AND how chromatic it is — a vivid accent beats a
flat background, while a genuinely greyscale cover still resolves to grey.

Returns a "#rrggbb" string, or None if the image can't be read.
"""

import colorsys
from PIL import Image


def dominant_colour(path, palette=12):
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((72, 72))                      # small = fast; detail doesn't matter
        q = im.quantize(colors=palette, method=Image.MEDIANCUT)
        pal = q.getpalette()                        # flat [r,g,b, r,g,b, ...]
        counts = q.getcolors()                      # [(count, palette_index), ...]
        if not counts:
            return None
        total = sum(c for c, _ in counts) or 1
        best, best_score = None, -1.0
        for count, idx in counts:
            r, g, b = pal[idx * 3], pal[idx * 3 + 1], pal[idx * 3 + 2]
            h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            freq = count / total
            # frequency leads (the dominant area), chroma boosts (so a vivid
            # accent isn't lost to a flat wall), and we gently avoid pure
            # black/white winning outright.
            mid = max(0.2, 1.0 - abs(l - 0.5) * 1.2)
            score = freq * (0.35 + s * 1.6) * mid
            if score > best_score:
                best_score, best = score, (r, g, b)
        if best is None:
            return None
        return "#%02x%02x%02x" % best
    except Exception:
        return None
