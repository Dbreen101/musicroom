"""Accurate musical-key detection from free tech.

The previous method took the single loudest pitch-class as the tonic and guessed
major/minor from one third — unreliable (bass notes, percussion and tuning all
throw it). This uses the standard **Krumhansl–Schmuckler** key-finding:
correlate a **tuning-corrected, percussion-removed** chroma against all 24
major/minor key profiles and take the best fit — so the whole pitch pattern
decides the key, not the loudest note.

If **Essentia** is installed, its `KeyExtractor` with the **'edma'** profile is
used instead — it's purpose-built for electronic dance music and is the most
accurate free detector available. No extra install is required for the K–S path
(librosa + numpy only).

Public:
    detect_key(y, sr)      -> {"key_note","key_scale","confidence","method"}
    detect_key_file(path)  -> same (loads the file itself)
"""
import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl–Kessler key profiles: perceived stability of each scale degree
# relative to the tonic (index 0). The classic, well-validated weights.
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _ks_best(chroma):
    """Return (correlation, tonic_index, mode, gap_to_second) for a 12-d chroma."""
    c = chroma - chroma.mean()
    cn = np.linalg.norm(c) + 1e-9
    scores = []
    for mode, prof in (("major", _KK_MAJOR), ("minor", _KK_MINOR)):
        p = prof - prof.mean()
        pn = np.linalg.norm(p) + 1e-9
        for tonic in range(12):
            r = np.roll(c, -tonic)          # bring candidate tonic to index 0
            corr = float(np.dot(r, p) / (cn * pn))
            scores.append((corr, tonic, mode))
    scores.sort(key=lambda s: -s[0])
    best = scores[0]
    gap = best[0] - scores[1][0] if len(scores) > 1 else 0.0
    return best[0], best[1], best[2], gap


def _essentia_key(y, sr):
    from essentia.standard import KeyExtractor, Resample
    audio = np.asarray(y, dtype=np.float32)
    if int(sr) != 44100:
        audio = Resample(inputSampleRate=int(sr), outputSampleRate=44100)(audio)
    key, scale, strength = KeyExtractor(profileType="edma")(audio)
    if not key:
        return None
    return {"key_note": key, "key_scale": scale,
            "confidence": round(float(strength), 3), "method": "essentia-edma"}


def detect_key(y, sr):
    """Detect musical key from already-loaded mono audio (numpy float, any sr)."""
    try:
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=0)
        if y.size == 0:
            return {"key_note": None, "key_scale": None, "confidence": 0.0, "method": "empty"}

        # Best available: Essentia's edma profile, when installed.
        try:
            ess = _essentia_key(y, sr)
            if ess:
                return ess
        except Exception:
            pass

        # Reliable fallback: Krumhansl–Schmuckler on tuning-corrected harmonic chroma.
        import librosa
        try:
            tuning = float(librosa.estimate_tuning(y=y, sr=sr))
        except Exception:
            tuning = 0.0
        try:
            y_h = librosa.effects.harmonic(y, margin=3.0)    # drop drums → cleaner key
        except Exception:
            y_h = y
        chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, tuning=tuning)
        vec = np.mean(chroma, axis=1)
        if not np.any(vec > 0):
            return {"key_note": None, "key_scale": None, "confidence": 0.0, "method": "krumhansl"}
        corr, tonic, mode, gap = _ks_best(vec)
        # Confidence blends the fit (corr → [0,1]) with how clear the winner is.
        conf = 0.7 * max(0.0, min(1.0, (corr + 1.0) / 2.0)) + 0.3 * max(0.0, min(1.0, gap * 4))
        return {"key_note": NOTE_NAMES[tonic], "key_scale": mode,
                "confidence": round(conf, 3), "method": "krumhansl"}
    except Exception:
        return {"key_note": None, "key_scale": None, "confidence": 0.0, "method": "error"}


def _load_via_ffmpeg(path, sr=22050, duration=120):
    """Decode to float32 mono PCM via ffmpeg — fallback for files librosa's
    libsndfile/audioread backends choke on (some FLACs raise CoreAudio
    'bad data' on macOS even though ffmpeg reads them cleanly)."""
    import subprocess, numpy as np
    from mr_ffmpeg import ffmpeg_path
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found (bundled, PATH, or Homebrew)")
    cmd = [ffmpeg, "-i", path, "-t", str(duration), "-ar", str(sr),
           "-ac", "1", "-f", "f32le", "-", "-loglevel", "error"]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode(errors='replace')[:200]}")
    return np.frombuffer(proc.stdout, dtype="float32"), sr


def detect_key_file(path, sr=22050, duration=120):
    import librosa
    try:
        y, _sr = librosa.load(path, mono=True, sr=sr, duration=duration)
    except Exception:
        # libsndfile/audioread failed — ffmpeg handles many such files cleanly.
        y, _sr = _load_via_ffmpeg(path, sr=sr, duration=duration)
    return detect_key(y, _sr)
