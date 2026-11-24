"""structures.py — the listener's own arrangement of tags and genres.

A structure is a saved mind-map of tag/genre nodes. The ROOM renders it
(records gather at the centroid of their matching nodes), the USB export
turns each node into a playlist. Positions/colours/links are entirely the
user's — this is an arranging TOOL, never an arrangement.

    GET/POST          /api/structures
    GET/PATCH/DELETE  /api/structure/<sid>
    POST              /api/structure/<sid>/nodes, /api/structure/<sid>/links
    PATCH/DELETE      /api/structure/node/<nid>, /api/structure/link/<lid>

app.py calls register(...) with the database helpers it already has.
"""
import json as _json

from flask import jsonify, request


def register(app, query, query_one, execute):
    def _structure_payload(sid):
        s = query_one("SELECT * FROM structures WHERE id=?", (sid,))
        if not s:
            return None
        s = dict(s)
        try:
            s["filters"] = _json.loads(s["filters"]) if s.get("filters") else None
        except Exception:
            s["filters"] = None
        nodes = query("""
            SELECT n.id, n.kind, n.ref_id, n.x, n.y, n.colour, n.group_name,
                   CASE n.kind WHEN 'tag' THEN (SELECT name FROM tags WHERE id=n.ref_id)
                               ELSE (SELECT name FROM genres WHERE id=n.ref_id) END AS name,
                   CASE n.kind WHEN 'tag'
                        THEN (SELECT COUNT(*) FROM track_tags WHERE tag_id=n.ref_id)
                        ELSE (SELECT COUNT(*) FROM track_genres WHERE genre_id=n.ref_id) END AS n_tracks
            FROM structure_nodes n WHERE n.structure_id=? ORDER BY n.id
        """, (sid,))
        links = query("SELECT id, from_node_id, to_node_id, label FROM structure_links WHERE structure_id=?", (sid,))
        return {"structure": dict(s), "nodes": [dict(n) for n in nodes],
                "links": [dict(l) for l in links]}


    @app.route("/api/structures")
    def api_structures():
        rows = query("""SELECT s.id, s.name, COUNT(n.id) AS node_count
                        FROM structures s LEFT JOIN structure_nodes n ON n.structure_id=s.id
                        GROUP BY s.id ORDER BY s.name""")
        return jsonify([dict(r) for r in rows])


    @app.route("/api/structures", methods=["POST"])
    def api_structures_create():
        d = request.get_json() or {}
        name = (d.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        filters = d.get("filters")          # the working set this structure was born from
        sid = execute("INSERT INTO structures (name, filters) VALUES (?,?)",
                      (name, _json.dumps(filters) if filters else None))
        return jsonify({"ok": True, "id": sid})


    @app.route("/api/structure/<int:sid>")
    def api_structure(sid):
        p = _structure_payload(sid)
        return (jsonify(p), 200) if p else (jsonify({"error": "not found"}), 404)


    @app.route("/api/structure/<int:sid>", methods=["PATCH"])
    def api_structure_patch(sid):
        d = request.get_json() or {}
        ups, vals = [], []
        if "name" in d:
            name = (d.get("name") or "").strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            ups.append("name=?"); vals.append(name)
        if "filters" in d:                  # set (dict) or clear (null/{}) the bound filters
            f = d.get("filters")
            ups.append("filters=?"); vals.append(_json.dumps(f) if f else None)
        if not ups:
            return jsonify({"error": "nothing to update"}), 400
        vals.append(sid)
        execute(f"UPDATE structures SET {', '.join(ups)} WHERE id=?", vals)
        return jsonify({"ok": True})


    @app.route("/api/structure/<int:sid>", methods=["DELETE"])
    def api_structure_delete(sid):
        execute("DELETE FROM structures WHERE id=?", (sid,))
        return jsonify({"ok": True})


    @app.route("/api/structure/<int:sid>/nodes", methods=["POST"])
    def api_structure_add_node(sid):
        """Add a tag/genre node by NAME — finds or creates the tag/genre, so the
        user can invent their system (energy 1–6, black/white/grey…) as they place it."""
        d = request.get_json() or {}
        kind = d.get("kind") if d.get("kind") in ("tag", "genre") else "tag"
        name = (d.get("name") or "").strip().lower()
        if not name:
            return jsonify({"error": "name required"}), 400
        if not query_one("SELECT 1 FROM structures WHERE id=?", (sid,)):
            return jsonify({"error": "structure not found"}), 404
        table = "tags" if kind == "tag" else "genres"
        ref = query_one(f"SELECT id FROM {table} WHERE LOWER(name)=?", (name,))
        ref_id = ref["id"] if ref else execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
        execute("""INSERT OR IGNORE INTO structure_nodes (structure_id, kind, ref_id, x, y, colour)
                   VALUES (?,?,?,?,?,?)""",
                (sid, kind, ref_id, float(d.get("x") or 0), float(d.get("y") or 0),
                 (d.get("colour") or "").strip() or None))
        node = query_one("SELECT id FROM structure_nodes WHERE structure_id=? AND kind=? AND ref_id=?",
                         (sid, kind, ref_id))
        return jsonify({"ok": True, "id": node["id"], "ref_id": ref_id})


    @app.route("/api/structure/node/<int:nid>", methods=["PATCH"])
    def api_structure_node_patch(nid):
        d = request.get_json() or {}
        ups, vals = [], []
        for k in ("x", "y"):
            if k in d:
                ups.append(f"{k}=?"); vals.append(float(d[k]))
        if "colour" in d:
            ups.append("colour=?"); vals.append((d["colour"] or "").strip() or None)
        if "group_name" in d:
            ups.append("group_name=?"); vals.append((d["group_name"] or "").strip().lower() or None)
        if not ups:
            return jsonify({"error": "nothing to update"}), 400
        vals.append(nid)
        execute(f"UPDATE structure_nodes SET {', '.join(ups)} WHERE id=?", vals)
        return jsonify({"ok": True})


    @app.route("/api/structure/node/<int:nid>", methods=["DELETE"])
    def api_structure_node_delete(nid):
        execute("DELETE FROM structure_links WHERE from_node_id=? OR to_node_id=?", (nid, nid))
        execute("DELETE FROM structure_nodes WHERE id=?", (nid,))
        return jsonify({"ok": True})


    @app.route("/api/structure/<int:sid>/links", methods=["POST"])
    def api_structure_add_link(sid):
        d = request.get_json() or {}
        a, b = d.get("from_node_id"), d.get("to_node_id")
        if not a or not b or a == b:
            return jsonify({"error": "two different nodes required"}), 400
        lid = execute("INSERT INTO structure_links (structure_id, from_node_id, to_node_id, label) VALUES (?,?,?,?)",
                      (sid, a, b, (d.get("label") or "").strip() or None))
        return jsonify({"ok": True, "id": lid})


    @app.route("/api/structure/link/<int:lid>", methods=["PATCH"])
    def api_structure_link_patch(lid):
        execute("UPDATE structure_links SET label=? WHERE id=?",
                (((request.get_json() or {}).get("label") or "").strip() or None, lid))
        return jsonify({"ok": True})


    @app.route("/api/structure/link/<int:lid>", methods=["DELETE"])
    def api_structure_link_delete(lid):
        execute("DELETE FROM structure_links WHERE id=?", (lid,))
        return jsonify({"ok": True})
