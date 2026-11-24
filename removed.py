"""removed.py — "Remove from Music Room", and changing your mind.

A record removed from the Music Room is never deleted: its files are parked
in the Removed folder, named '<track_id>_<original>'. These routes list what
is parked and bring it back (un-delete the track, move the file into
Library/Restored, relink it, put it back in The Well).

    GET  /api/removed           what is parked, by track
    POST /api/removed/restore   {track_ids: [...]} → brought back
    GET  /removed               the page

app.py calls register(...) with the database helpers it already has.
"""
import os
import shutil

from flask import jsonify, render_template, request


def register(app, query, query_one, execute, _removed_dir, get_library_dest):
    def _all_removed_dirs():
        """Folders 'Remove from Music Room' parks files in: the real one + legacy."""
        return [str(_removed_dir()),
                "/Volumes/EXTERNAL HARD DRIVE 1/Music Room/Removed from Music Room"]

    def _scan_removed():
        """{track_id: [ {path, name} ]} for files parked by Remove-from-Music-Room
        (named '<track_id>_<original>' or '<track_id>_<n>_<original>')."""
        out = {}
        for d in _all_removed_dirs():
            if not os.path.isdir(d):
                continue
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                full = os.path.join(d, name)
                if not os.path.isfile(full):
                    continue
                i = name.find("_")
                if i <= 0 or not name[:i].isdigit():
                    continue
                out.setdefault(int(name[:i]), []).append({"path": full, "name": name})
        return out


    @app.route("/api/removed")
    def api_removed_list():
        """Tracks parked by 'Remove from Music Room' — so the user can restore any."""
        found = _scan_removed()
        out = []
        for tid, files in found.items():
            t = query_one("SELECT id,title,artist_name FROM tracks WHERE id=?", (tid,))
            nm = files[0]["name"]
            pre = f"{tid}_"
            if nm.startswith(pre):                      # drop the "<id>_" parking prefix for display
                nm = nm[len(pre):]
            out.append({"track_id": tid,
                        "title": (t["title"] if t else None) or nm,
                        "artist": (t["artist_name"] if t else "") or "",
                        "n_files": len(files)})
        out.sort(key=lambda r: ((r["artist"] or "").lower(), (r["title"] or "").lower()))
        return jsonify({"count": len(out), "removed": out})


    @app.route("/api/removed/restore", methods=["POST"])
    def api_removed_restore():
        """Bring removed tracks back: un-delete the track, relink its file rows to the
        parked files, re-add to The Well. The file stays where it is (it plays from
        there) — no deletion, no risky move."""
        d = request.get_json() or {}
        tids = [int(x) for x in (d.get("track_ids") or [])]
        found = _scan_removed()
        well = query_one("SELECT id FROM places WHERE is_well=1")
        lib = get_library_dest()
        restored_dir = os.path.join(lib, "Restored") if lib else None

        def _unpark(parked_path, parked_name, tid):
            """Move a parked file OUT of the Removed folder (into Library/Restored,
            with its '<id>_' prefix stripped) so it no longer reads as removed.
            Returns the new path; falls back to leaving it in place if the move
            fails (never loses the file)."""
            clean = parked_name
            if clean.startswith(f"{tid}_"):
                clean = clean[len(f"{tid}_"):]
            if not restored_dir:
                return parked_path
            try:
                os.makedirs(restored_dir, exist_ok=True)
                dest = os.path.join(restored_dir, clean); stem, ext = os.path.splitext(clean); c = 1
                while os.path.exists(dest):
                    dest = os.path.join(restored_dir, f"{stem} ({c}){ext}"); c += 1
                shutil.move(parked_path, dest)
                return dest
            except Exception:
                return parked_path

        restored = []
        for tid in tids:
            files = found.get(tid) or []
            if not files:
                continue
            execute("UPDATE tracks SET is_deleted=0, deleted_at=NULL WHERE id=?", (tid,))
            rows = query("SELECT id, file_path FROM files WHERE track_id=?", (tid,))
            used = set()
            for fr in rows:
                base = os.path.basename(fr["file_path"] or "")
                m = next((f for f in files if f["path"] not in used and base and f["name"].endswith(base)), None)
                if not m and len(files) == 1 and len(rows) == 1:
                    m = files[0]
                if m:
                    newpath = _unpark(m["path"], m["name"], tid)
                    execute("UPDATE files SET file_path=?, is_deleted=0, deleted_at=NULL, updated_at=datetime('now') WHERE id=?",
                            (newpath, fr["id"]))
                    used.add(m["path"])
            if not rows:   # track had no file rows left — recreate from the parked files
                for f in files:
                    execute("INSERT INTO files (track_id, file_path, is_primary, is_deleted) VALUES (?,?,0,0)",
                            (tid, _unpark(f["path"], f["name"], tid)))
            if not query_one("SELECT 1 FROM files WHERE track_id=? AND is_primary=1 AND is_deleted=0", (tid,)):
                nf = query_one("SELECT id FROM files WHERE track_id=? AND is_deleted=0 ORDER BY id LIMIT 1", (tid,))
                if nf:
                    execute("UPDATE files SET is_primary=1 WHERE id=?", (nf["id"],))
            if well:
                execute("INSERT OR IGNORE INTO place_tracks (place_id, track_id, added_at) VALUES (?,?,datetime('now'))",
                        (well["id"], tid))
            restored.append(tid)
        return jsonify({"ok": True, "restored": restored, "count": len(restored)})


    @app.route("/removed")
    def removed_page():
        """Page listing files removed from Music Room, with restore."""
        return render_template("removed.html")
