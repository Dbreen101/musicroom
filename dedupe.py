"""Byte-identical duplicate collapsing — the SAFETY-CRITICAL decision logic,
isolated from the Flask app so it can be unit-tested in full (see
test_dedupe_safety.py). Dependencies are injected (hash / trash / isfile) so the
exact shipping logic runs in tests against throwaway files.

Invariants this guarantees:
  * Only files that EXIST on disk are ever considered (a stale stored hash can
    never resurrect a since-deleted file and let it be "kept").
  * The keeper is re-verified present before anything is removed.
  * A DB row is retired ONLY when not deleting files, or the trash genuinely
    succeeded — a failed trash leaves the file AND its row untouched.
  * Therefore a track can never be left without its file by this code.
"""
import os
from collections import defaultdict


def _norm(p):
    return os.path.normpath(p or "")


def run_dedupe(conn, groups, delete_files, *, file_hash, trash, isfile, on_checked=None):
    """Collapse byte-identical files within each spectrum group.

    conn         sqlite connection whose `files` table is updated in place
    groups       list of groups; each a list of dict-like file rows with keys
                 id, track_id, file_path, content_hash, is_primary
    delete_files when True, redundant copies are moved to the Trash via `trash`
    file_hash    (path) -> sha256 hex (or falsy)
    trash        (path) -> (ok: bool, err)
    isfile       (path) -> bool   (os.path.isfile that never raises)
    on_checked   optional () callback per file examined (progress)

    Returns {"removed": int, "trashed": int}.
    """
    removed = trashed = 0
    for g in groups:
        by_hash = defaultdict(list)
        for f in g:
            if on_checked:
                on_checked()
            # Only files that ACTUALLY EXIST right now are candidates. This is
            # the fix for the bug that grouped a gone file by its stale stored
            # hash, kept it, and trashed the surviving copy.
            if not (f["file_path"] and isfile(f["file_path"])):
                continue
            h = f["content_hash"]
            if not h:
                h = file_hash(f["file_path"])
                if h:
                    conn.execute(
                        "UPDATE files SET content_hash=?, hashed_at=datetime('now') WHERE id=?",
                        (h, f["id"]),
                    )
                    conn.commit()
            if h:
                by_hash[h].append(f)

        for identical in by_hash.values():
            if len(identical) < 2:
                continue
            # Prefer the organised-library copy, then the existing primary, then
            # lowest id. Every file here is confirmed present, so the keeper is real.
            identical.sort(key=lambda f: (
                0 if "Music Room Library" in (f["file_path"] or "") else 1,
                0 if f["is_primary"] else 1,
                f["id"],
            ))
            keep, rest = identical[0], identical[1:]
            keep_path = _norm(keep["file_path"])
            if not isfile(keep["file_path"]):
                continue   # paranoia: never keep a missing file
            conn.execute("UPDATE files SET is_primary=0 WHERE track_id=?", (keep["track_id"],))
            conn.execute("UPDATE files SET is_primary=1 WHERE id=?", (keep["id"],))
            for x in rest:
                if _norm(x["file_path"]) == keep_path:
                    continue                     # same path as keeper — never touch
                if delete_files:
                    ok, _err = trash(x["file_path"] or "")
                    if not ok:
                        # Could not move to Trash — leave the file AND its row
                        # alone. Never hard-delete, never mark removed-when-present.
                        continue
                    trashed += 1
                conn.execute(
                    "UPDATE files SET is_deleted=1, is_primary=0, updated_at=datetime('now') WHERE id=?",
                    (x["id"],),
                )
                removed += 1
            conn.commit()
    return {"removed": removed, "trashed": trashed}
