"""Real audio files made on the spot, so a test needs nobody's own library."""
import numpy as np
import soundfile as sf
from mutagen.flac import FLAC


def make_flac(path, seed=0, seconds=12, title="Test Song", artist="Test Artist"):
    rng = np.random.default_rng(seed)
    t = np.arange(int(44100 * seconds)) / 44100
    wave = 0.3 * np.sin(2 * np.pi * (220 + 30 * seed) * t) + 0.05 * rng.standard_normal(t.size)
    sf.write(path, np.column_stack([wave, wave]).astype("float32"), 44100, subtype="PCM_16")
    tags = FLAC(path)
    tags["title"], tags["artist"] = f"{title} {seed}", artist
    tags.save()
    return path
