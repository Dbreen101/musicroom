"""
reanalyse_bands.py
==================
Re-runs ONLY the perceptual 6-band fingerprint (v19) on every file with
has_analysis=1. Does not touch BPM, key, loudness, etc.

Why a separate script: the original analyser used per-bin mean of raw FFT
magnitudes which made every track read as ~85% bass. The new fingerprint
uses A-weighted band loudness in absolute dB plus a vocal_score; existing
tracks need to be recomputed once to populate the new columns.

Usage:
    python reanalyse_bands.py            # process all has_analysis=1 files
    python reanalyse_bands.py --limit 20 # quick smoke test
    python reanalyse_bands.py --missing  # only files that lack the new columns
"""

import os, sys, sqlite3, argparse, time
import numpy as np
import librosa

from importer import (
    _compute_band_fingerprint,
    _load_via_ffmpeg,
)

BASE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(BASE, "library.db")


def resolve_path(stored_path):
    """Match app.py's _resolve_audio_path — try the stored path, fall back to
    other mounted /Volumes/*."""
    if os.path.exists(stored_path):
        return stored_path
    if stored_path.startswith("/Volumes/"):
        parts = stored_path.split("/", 3)
        if len(parts) >= 4:
            rel = parts[3]
            try:
                for vol in os.listdir("/Volumes"):
                    cand = os.path.join("/Volumes", vol, rel)
                    if os.path.exists(cand):
                        return cand
            except OSError:
                pass
    return None


def analyse_one(path):
    try:
        y, sr = librosa.load(path, mono=True, sr=22050, duration=120)
    except Exception:
        y, sr = _load_via_ffmpeg(path)
    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    return _compute_band_fingerprint(stft, freqs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process at most N files")
    ap.add_argument("--missing", action="store_true",
                    help="only files where band_presence IS NULL")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where = "WHERE has_analysis = 1"
    if args.missing:
        where += " AND band_presence IS NULL"
    sql = f"SELECT id, file_path FROM files {where} ORDER BY id ASC"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = c.execute(sql).fetchall()
    total = len(rows)
    print(f"Re-analysing {total} files (perceptual bands + vocal_score)")
    if not total:
        return

    start = time.time()
    done = 0
    skipped = 0
    for i, r in enumerate(rows, 1):
        path = resolve_path(r["file_path"])
        if not path:
            skipped += 1
            continue
        try:
            bands = analyse_one(path)
        except Exception as e:
            print(f"  [{i}/{total}] FAIL {os.path.basename(r['file_path'])}: {e}", flush=True)
            skipped += 1
            continue

        c.execute("""
            UPDATE files SET
                band_sub        = ?,
                band_bass       = ?,
                band_lowmid     = ?,
                band_body       = ?,
                band_presence   = ?,
                band_brilliance = ?
            WHERE id = ?
        """, (
            bands.get("band_sub"),
            bands.get("band_bass"),
            bands.get("band_lowmid"),
            bands.get("band_body"),
            bands.get("band_presence"),
            bands.get("band_brilliance"),
            r["id"],
        ))
        done += 1
        if done % 25 == 0:
            conn.commit()
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  [{i}/{total}] {os.path.basename(r['file_path'])[:60]} "
                  f"presence={bands.get('band_presence')} "
                  f"· {rate:.1f}/s eta {int(eta)}s", flush=True)

    conn.commit()
    conn.close()
    print(f"\nDone. {done} updated, {skipped} skipped, {time.time()-start:.0f}s elapsed.")


if __name__ == "__main__":
    main()
