"""The app's half of the credits trial (gr_sim_app.py): it takes up the Spotify
key the master gives this person (never replacing a key someone typed in
themselves), and the master's app reads the shop's playlist into whole records.
A stand-in for Spotify; no network. Run:  ./venv/bin/python test_gr_sim_app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gr_sim_app as A

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def sid(n): return (f"{n:0>22}")[-22:]

# ── the Spotify key ──
SET = {}
class SP:
    gone = 0
    def disconnect(self): SP.gone += 1
A._D.update(get_setting=lambda k, d="": SET.get(k, d), set_setting=lambda k, v: SET.__setitem__(k, v), spotify=lambda: SP(), is_gr=True)
K1, K2 = "a" * 32, "b" * 32
A.adopt_key({"spotify_client_id": K1})
chk(SET["spotify_client_id"] == K1 and SET["spotify_client_id_from"] == "server" and SP.gone == 0, "a key given by the master is taken up")
A.adopt_key({"spotify_client_id": K2})
chk(SET["spotify_client_id"] == K2 and SP.gone == 1, "a different key: the old sign-in goes (it belonged to the old key)")
A.adopt_key({"spotify_client_id": ""})
chk(SET["spotify_client_id"] == "" and SET["spotify_client_id_from"] == "" and SP.gone == 2, "the key taken away: the app lets it go")
SET.update(spotify_client_id="c" * 32, spotify_client_id_from="")
A.adopt_key({"spotify_client_id": K1}); A.adopt_key({"spotify_client_id": ""})
chk(SET["spotify_client_id"] == "c" * 32 and SP.gone == 2, "a key someone typed in themselves is never replaced")

# ── reading the playlist into records ──
X, Y, V = {"id": sid("ax"), "name": "Moss Fen"}, {"id": sid("ay"), "name": "The Lantern"}, {"id": sid("av"), "name": "Various Artists"}
def tr(n, alb, artists): return {"id": sid(f"t{n}"), "type": "track", "name": f"T{n}", "track_number": n, "disc_number": 1, "duration_ms": 1000, "artists": artists, "album": alb}
ALB = {"id": sid("ra"), "name": "Low Field", "album_type": "album", "total_tracks": 3, "release_date": "2019", "artists": [X],
       "images": [{"url": "https://i.scdn.co/image/big", "width": 1200}, {"url": "https://i.scdn.co/image/mid", "width": 640}]}
SGL = {"id": sid("rb"), "name": "Hum", "album_type": "single", "total_tracks": 1, "release_date": "2021", "artists": [X], "images": []}
CMP = {"id": sid("rc"), "name": "Night Comp", "album_type": "compilation", "total_tracks": 20, "release_date": "2020", "artists": [V], "images": []}
OLD = {"id": sid("rd"), "name": "Known", "album_type": "album", "total_tracks": 2, "release_date": "2010", "artists": [Y], "images": []}
playlist = [tr(1, ALB, [X]), tr(2, ALB, [X]), tr(11, SGL, [X]), tr(21, CMP, [Y]), tr(31, OLD, [Y]), {"id": "episode", "type": "episode"}]
class FakeSP:
    calls = []
    def _api_get(self, path, params=None):
        FakeSP.calls.append(path)
        if path.endswith(f"/{sid('pl')}"): return {"name": "Green Room shop"}
        if "/items" in path:
            off = params["offset"]
            page = playlist[off:off + 3]
            return {"items": [{"item": x} for x in page], "next": "more" if off + 3 < len(playlist) else None}
        if path == f"/albums/{ALB['id']}/tracks":
            return {"items": [{"id": sid(f"t{n}"), "name": f"T{n}", "track_number": n, "disc_number": 1, "duration_ms": 1, "artists": [X]} for n in (1, 2, 3)], "next": None}
        if path == f"/albums/{SGL['id']}/tracks":
            return {"error": "nope", "status": 500}
        return {"error": "?", "status": 404}
sp = FakeSP()
tracks, name, why = A.read_playlist(sp, sid("pl"))
chk(len(tracks) == 5 and name == "Green Room shop" and why == "", "the playlist is read page by page; anything that isn't a track is passed over")
recs = A.records_from(sp, tracks, {OLD["id"]})
by = {r["key"]: r for r in recs}
chk(set(by) == {ALB["id"], SGL["id"], f"{CMP['id']}:{sid('t21')}"}, "one record per album or single; a compilation track alone; records already there are skipped")
chk([t["name"] for t in by[ALB["id"]]["tracks"]] == ["T1", "T2", "T3"] and by[ALB["id"]]["kind"] == "album", "an album comes whole, even the track not on the playlist")
chk(by[ALB["id"]]["image"] == "https://i.scdn.co/image/mid", "its cover: the biggest picture up to 800 wide")
chk(len(by[SGL["id"]]["tracks"]) == 1 and by[SGL["id"]]["kind"] == "single", "when Spotify won't give a record's tracks, the playlist's own are kept")
c = by[f"{CMP['id']}:{sid('t21')}"]
chk(c["kind"] == "compilation" and c["total_tracks"] == 1 and c["artists"][0]["name"] == "The Lantern", "a compilation track belongs to its own artist, not 'Various Artists'")
chk(not any("/albums/" + CMP["id"] in p for p in FakeSP.calls), "a compilation is never opened out")
class NoSP:
    def _api_get(self, path, params=None): return {"error": "Forbidden", "status": 403}
t2, _n, why = A.read_playlist(NoSP(), sid("pl"))
chk(t2 == [] and "must be one you made" in why, "a playlist Spotify won't let us read says why in plain words")

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
