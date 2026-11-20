"""
gen_vellum.py — bake static/textures/vellum.jpg (dev-only; numpy + Pillow).

A leaf of vellum for the manuscript surfaces: warm ivory ground, soft
mottled clouding (the calfskin's uneven translucency), faint horizontal
fibre streaks, and a gentle darkening toward the edges. Tuned SUBTLE —
it sits under ink at full opacity, so the tooth must whisper, not shout.

Re-runnable: tweak the constants and re-bake, then cache-bust the
template URL (?v=N).
"""

import numpy as np
from PIL import Image, ImageFilter

W = H = 1024

BASE = np.array([0xF3, 0xEA, 0xD2], dtype=float)   # warm ivory, a touch lighter than --surface
CLOUD_STRENGTH = 7.0      # mottled translucency (luma +/-)
FIBRE_STRENGTH = 2.6      # horizontal fibre streaks
GRAIN_STRENGTH = 2.2      # per-pixel tooth
EDGE_DARKEN = 8.0         # vignette toward the leaf's edges
WARM_DRIFT = 4.0          # slow red/yellow drift so it never reads flat-grey


def fbm(shape, octaves=4, base_scale=8, rng=None, axis_stretch=(1, 1)):
    """Cheap fractal noise: upscaled random grids summed across octaves."""
    rng = rng or np.random.default_rng(7)
    out = np.zeros(shape, dtype=float)
    amp = 1.0
    for o in range(octaves):
        gw = max(2, int(base_scale * (2 ** o) * axis_stretch[0]))
        gh = max(2, int(base_scale * (2 ** o) * axis_stretch[1]))
        grid = rng.standard_normal((gh, gw))
        img = Image.fromarray(((grid - grid.min()) / (np.ptp(grid) + 1e-9) * 255).astype(np.uint8))
        img = img.resize((shape[1], shape[0]), Image.BICUBIC)
        out += (np.asarray(img, dtype=float) / 255.0 - 0.5) * amp
        amp *= 0.55
    return out / np.abs(out).max()


def main():
    rng = np.random.default_rng(7)

    cloud = fbm((H, W), octaves=4, base_scale=3, rng=rng)
    cloud = np.asarray(Image.fromarray(((cloud + 1) * 127).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(6)), dtype=float) / 127 - 1

    # fibres: noise stretched hard along x (the scrape of the lunellum)
    fibre = fbm((H, W), octaves=3, base_scale=2, rng=rng, axis_stretch=(24, 1))

    grain = rng.standard_normal((H, W)) * 0.5

    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = (xx / W - 0.5) * 2, (yy / H - 0.5) * 2
    edge = np.clip(np.sqrt(cx**2 + cy**2) - 0.62, 0, 1) ** 1.6

    luma = (cloud * CLOUD_STRENGTH + fibre * FIBRE_STRENGTH
            + grain * GRAIN_STRENGTH - edge * EDGE_DARKEN)

    warm = fbm((H, W), octaves=2, base_scale=2, rng=np.random.default_rng(13))
    warm = np.asarray(Image.fromarray(((warm + 1) * 127).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(10)), dtype=float) / 127 - 1

    img = np.zeros((H, W, 3), dtype=float)
    img[..., 0] = BASE[0] + luma + warm * WARM_DRIFT          # R drifts warmest
    img[..., 1] = BASE[1] + luma + warm * (WARM_DRIFT * 0.55)
    img[..., 2] = BASE[2] + luma - warm * (WARM_DRIFT * 0.35) # B falls as warmth rises

    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    out.save("static/textures/vellum.jpg", quality=82)
    print("baked static/textures/vellum.jpg", out.size)


if __name__ == "__main__":
    main()
