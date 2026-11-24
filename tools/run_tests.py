"""tools/run_tests.py — run every test_*.py (or the ones named), side by side.

    venv/bin/python tools/run_tests.py                       all of them
    venv/bin/python tools/run_tests.py test_gr_server test_plugins
    venv/bin/python tools/run_tests.py --jobs 1              one at a time

Each test makes its own throwaway data and needs no network. A test passes when
it exits 0; the output of any that didn't is printed after the list.
"""
import argparse
import concurrent.futures as cf
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(path):
    started = time.time()
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([sys.executable, path.name], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        ok, out = p.returncode == 0, p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        ok, out = False, f"still running after {e.timeout}s"
    return path.stem, ok, time.time() - started, out


def main():
    ap = argparse.ArgumentParser(description="Run the Music Room's tests.")
    ap.add_argument("tests", nargs="*", help="test names (test_gr_server or test_gr_server.py); all when none")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    args = ap.parse_args()

    if args.tests:
        paths = [ROOT / (t if t.endswith(".py") else t + ".py") for t in args.tests]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            sys.exit(f"No such test: {', '.join(missing)}")
    else:
        paths = sorted(ROOT.glob("test_*.py"))

    failed = []
    with cf.ThreadPoolExecutor(max(1, args.jobs)) as pool:
        for name, ok, secs, out in pool.map(run, paths):
            print(f"  {'pass' if ok else 'FAIL'}  {name}  ({secs:.1f}s)", flush=True)
            if not ok:
                failed.append((name, out))

    for name, out in failed:
        print(f"\n── {name} ──\n{out.rstrip()}")
    print(f"\n{len(paths) - len(failed)} of {len(paths)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
