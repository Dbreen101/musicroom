#!/usr/bin/env python3
"""
Generate organic Irish-forest-floor background textures for Music Room.

Dev-only — produces static assets the app then ships. The app itself does
NOT depend on numpy/Pillow at runtime; this just bakes the images once.

Output:
  static/textures/forest_floor.jpg   full-colour mottled forest floor (default
                                      / menu background — earth tones blended,
                                      grainy, biased to a mid luminance so dark
                                      ink text stays legible on top)
  static/textures/grain.png          neutral semi-transparent grain + soft
                                      mottle overlay — lay it over any solid
                                      place colour to make that colour textured
                                      in the same grainy way (per-place themes)

Run:  venv/bin/python gen_textures.py
"""
import os
import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "textures")
os.makedirs(OUT, exist_ok=True)

W, H = 1920, 1200


def smooth_field(h, w, cells, rng):
    """A random low-res grid upsampled smoothly to (h, w) — value noise."""
    g = (rng.random((cells, cells)) * 255).astype(np.uint8)
    im = Image.fromarray(g, mode="L").resize((w, h), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0


def fractal(h, w, rng, base_cells=3, octaves=5, persistence=0.55):
    """Sum of value-noise octaves → soft organic blobs, normalised 0..1."""
    out = np.zeros((h, w), np.float32)
    amp, tot, cells = 1.0, 0.0, base_cells
    for _ in range(octaves):
        out += amp * smooth_field(h, w, cells, rng)
        tot += amp
        amp *= persistence
        cells = max(2, cells * 2)
    out /= tot
    out -= out.min()
    out /= (out.max() + 1e-6)
    return out


def palette_map(n, stops):
    """Map a 0..1 field through colour stops [(pos, (r,g,b)), ...]."""
    pos = np.array([p for p, _ in stops], dtype=np.float32)
    chans = []
    for i in range(3):
        cv = np.array([c[i] for _, c in stops], dtype=np.float32)
        chans.append(np.interp(n, pos, cv))
    return np.stack(chans, axis=-1)


def vignette(h, w, strength=0.10):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h / 2, w / 2
    d = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    d /= d.max()
    return 1.0 - strength * (d ** 2)


def make_forest_floor(seed=7):
    rng = np.random.default_rng(seed)

    # Damp Irish forest floor: deep wet moss → peat → oak bark → bracken
    # → dried leaf-litter. Weighted toward the shadowy half so the floor
    # reads as rich earth, not tan. Sheets/cards hold the readable text now,
    # so the floor itself can go richer.
    stops = [
        (0.00, (32, 40, 24)),     # very dark wet moss
        (0.18, (48, 50, 30)),     # deep moss + leaf
        (0.38, (66, 58, 36)),     # peat
        (0.60, (94, 76, 46)),     # oak bark / damp brown
        (0.82, (124, 102, 60)),   # bracken
        (1.00, (152, 132, 90)),   # dried leaf-litter (the highlight)
    ]

    # Assign colour at a SMALL (leaf-sized) scale so the floor reads as dense
    # mixed leaf-litter, not big cloud-like colour regions. A high base
    # frequency is the key — low-freq fields always look like haze/cloud.
    base = fractal(H, W, rng, base_cells=34, octaves=4, persistence=0.52)
    rgb = palette_map(base, stops)

    # Only the faintest large-scale damp/dry drift — kept tiny so it never
    # reads as light/dark clouds.
    shade = fractal(H, W, rng, base_cells=5, octaves=3, persistence=0.5)
    rgb *= (0.96 + 0.06 * shade)[..., None]

    # Extra green-brown flecks at a couple of scales (moss specks, twigs).
    for cells, gw, ww in [(60, 14.0, 8.0), (120, 9.0, 5.0)]:
        fleck = fractal(H, W, rng, base_cells=cells, octaves=2, persistence=0.5) - 0.5
        rgb[..., 1] += fleck * gw        # green wobble
        rgb[..., 0] += fleck * ww        # warm wobble

    # Fine grain — the tactile "grainy" feel.
    grain = rng.normal(0.0, 10.0, (H, W, 1)).astype(np.float32)
    rgb += grain

    # Richer damp earth — content lives on parchment leaves now so the floor
    # itself can sit lower. Target mean luma ~108.
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    rgb += (108.0 - luma.mean())

    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    img = Image.fromarray(rgb, mode="RGB")
    path = os.path.join(OUT, "forest_floor.jpg")
    img.save(path, "JPEG", quality=86, optimize=True)
    print(f"  wrote {path}  ({os.path.getsize(path)//1024} KB, mean luma {luma.mean():.0f})")


def make_grain(seed=11, size=1280):
    """Neutral tintable overlay: soft mottle + grain as RGBA. Dark grains
    darken, light grains lighten whatever solid colour sits beneath — so a
    place painted in its own colour still reads as organic + grainy."""
    rng = np.random.default_rng(seed)
    mottle = fractal(size, size, rng, base_cells=3, octaves=5, persistence=0.55)
    mottle = (mottle - 0.5) * 2.0                      # -1..1, low freq
    grain = rng.normal(0.0, 1.0, (size, size))         # high freq
    field = np.clip(0.65 * mottle + 0.45 * grain, -1, 1)

    rgba = np.zeros((size, size, 4), np.float32)
    dark = field < 0
    # dark earth vs warm light, alpha scales with magnitude (kept subtle)
    rgba[..., 0] = np.where(dark, 38, 236)
    rgba[..., 1] = np.where(dark, 30, 226)
    rgba[..., 2] = np.where(dark, 20, 198)
    rgba[..., 3] = np.clip(np.abs(field) * 70.0, 0, 64)

    img = Image.fromarray(rgba.astype(np.uint8), mode="RGBA")
    path = os.path.join(OUT, "grain.png")
    img.save(path, "PNG", optimize=True)
    print(f"  wrote {path}  ({os.path.getsize(path)//1024} KB)")


if __name__ == "__main__":
    print("Generating Music Room textures…")
    make_forest_floor()
    print("Done.")
