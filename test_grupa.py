"""Grúpa + streamed records — link recognition (streams.py), the queue's
'embed' kind and the deck driving the listener's own Spotify
(seinnteoir_player.py + a stand-in for spotify_remote.py), the AI-made marks
(ai_flags.py) and the grúpa routes on a fresh database.
No network, no sound, no real Spotify. Run:  ./venv/bin/python test_grupa.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_tmp = tempfile.TemporaryDirectory()
os.environ["MUSICROOM_DATA"] = _tmp.name            # a fresh data dir — David's library stays out
os.environ["SDL_AUDIODRIVER"] = "dummy"             # the mixer opens on nothing: silent
os.environ.pop("MR_GREEN_ROOM", None)

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ─── links ───
import streams
P = streams.parse
p = P("https://open.spotify.com/intl-de/track/0VjIjW4GlUZAMYd2vXMi3b?si=abc")
chk(p and p["source"] == "spotify" and p["type"] == "track" and p["url"] == "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b", "spotify track: tidied, tracking dropped")
chk(P("spotify:album:1DFixLWuPkv3KT3TnV35m3")["url"] == "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3", "spotify uri → link")
chk(P("https://open.spotify.com/user/x/playlist/37i9dQZF1DXcBWIGoYBM5M")["type"] == "playlist", "spotify old playlist form")
APPLE = "https://music.apple.com/ie/album/some-album/1440833098?i=1440833100&uo=4"
chk(P(APPLE) is None and P("https://music.apple.com/us/playlist/todays-hits/pl.f4d1") is None, "Apple Music is switched off: its links are not streams")
streams.ENABLED = ("spotify", "soundcloud", "apple"); p = P(APPLE); streams.ENABLED = ("spotify", "soundcloud")
chk(p["source"] == "apple" and p["type"] == "track" and p["url"].endswith("/1440833098?i=1440833100"), "…and one word brings the recogniser back")
chk(streams.by_ids_of("soundcloud", "https://soundcloud.com/Forss/flickermood") == "forss" and streams.by_ids_of("spotify", "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b") == "", "who a link is by, as far as the link says")
chk(P("https://soundcloud.com/forss/flickermood?utm_source=x")["url"] == "https://soundcloud.com/forss/flickermood", "soundcloud track tidied")
chk(P("https://soundcloud.com/forss/sets/soulhack")["type"] == "playlist", "soundcloud set = playlist")
chk(P("https://soundcloud.com/forss")["type"] == "artist", "soundcloud profile = artist")
chk(P("https://soundcloud.com/discover") is None and P("https://daithi.bandcamp.com/") is None and P("") is None, "other links are not streams")
chk(P("https://on.soundcloud.com/abc").get("short") is True, "share-sheet short link flagged")

# ─── the queue ───
import seinnteoir_player as sp
sp._QUEUE_FILE = None
pl = sp.SeinnteoirPlayer()
E = lambda u, t: {"kind": "embed", "url": u, "source": "soundcloud", "title": t}
pl.set_queue([E("https://soundcloud.com/a/one", "one"), E("https://soundcloud.com/a/two", "two"), {"kind": "embed", "url": "javascript:x"}], 0, True)
st = pl.get_state()
chk(len(st["queue"]) == 2 and st["playing"] and st["queue"][0]["kind"] == "embed" and st["queue"][0]["qid"], "streamed items queue; a non-web link is refused")
qid = st["queue"][0]["qid"]
chk(pl.embed_report(qid, position=12.5, duration=200) and abs(pl.get_state()["position"] - 12.5) < 1 and pl.get_state()["duration"] == 200, "the page's clock is taken")
pl.pause(); a = pl.get_state()["playing"]; pl.play()
chk(a is False and pl.get_state()["playing"] is True, "pause / play keep time without the mixer")
seq = pl.get_state()["embed_seq"]; pl.seek(40)
chk(pl.get_state()["embed_seq"] == seq + 1 and pl.get_state()["position"] >= 40, "a seek bumps the command counter")
chk(pl.embed_report("someone-else", ended=True) is False and pl.get_state()["idx"] == 0, "a stale report can't move the cue")
chk(pl.embed_report(qid, ended=True) and pl.get_state()["idx"] == 1, "'ended' moves the cue on")
pl.move(1, 0)
chk([q["title"] for q in pl.get_state()["queue"]] == ["two", "one"] and pl.get_state()["idx"] == 0, "move by position keeps the playing record current")
pl.clear()

# ─── the deck driving the listener's own Spotify (a stand-in, no network) ───
from spotify_remote import uri_of
chk(uri_of("https://open.spotify.com/intl-de/track/AAA?si=x") == ("one", "spotify:track:AAA") and uri_of("https://open.spotify.com/playlist/PPP")[0] == "many" and uri_of("https://soundcloud.com/a/b") == (None, None), "a Spotify link → what to tell Spotify to play")

class FakeSpotify:
    """Plays what it is told and keeps time, like the listener's Spotify would."""
    def __init__(self):
        self.ok, self.why, self.log = True, "", []
        self.uri = self.ctx = ""; self.playing = False; self.pos = 0.0; self.at = time.time(); self.dur = 4.5
        self.device_name = "Test Mac"; self.nothing = True
        self.title = "Guest Song"; self.deaf = False; self.other_id = False; self.by = "a1"
    def ready(self): return self.ok
    def can_see(self): return True
    def can_take(self, item): return item.get("kind") == "embed" and item.get("source") == "spotify" and self.ok
    def _now(self): return self.pos + (time.time() - self.at if self.playing else 0)
    def play(self, item, start=0.0):
        self.log.append(("play", item["title"], round(start, 1)))
        if self.why: return False, self.why
        how, uri = uri_of(item["url"])
        if self.deaf:                               # says yes, then carries on with what it had (the real Spotify can)
            self.pos, self.at, self.playing, self.nothing = 0.0, time.time(), True, False
            return True, ""
        self.uri, self.ctx = (uri, "") if how == "one" else ("spotify:track:inner", uri)
        if uri.startswith("spotify:artist:"): self.ctx, self.by = "", "zz," + uri.rsplit(":", 1)[1]   # the real Spotify names no context for an artist
        if self.other_id: self.uri = "spotify:track:REGIONALCOPY"      # the same recording under another id
        self.title = item["title"]
        self.pos, self.at, self.playing, self.nothing = start, time.time(), True, False
        return True, ""
    def pause(self): self.log.append(("pause",)); self.pos = self._now(); self.playing = False; return True
    def resume(self): self.log.append(("resume",)); self.at = time.time(); self.playing = True; return True
    def next(self): self.log.append(("next",)); return True
    def previous(self): self.log.append(("prev",)); return True
    def seek(self, s): self.log.append(("seek", round(s, 1))); self.pos = s; self.at = time.time(); return True
    def volume(self, v): self.log.append(("vol", round(v, 2))); return True
    def state(self):
        if self.nothing: return {"playing": False, "nothing": True}
        p = self._now()
        if self.playing and p >= self.dur: self.playing, self.pos, p = False, 0.0, 0.0     # a lone track ends: stopped, back at 0
        return {"playing": self.playing, "nothing": False, "uri": self.uri, "context_uri": self.ctx, "position": p, "duration": self.dur,
                "title": self.title, "artist": "Guest", "artist_ids": self.by, "image_url": "", "url": "https://open.spotify.com/track/GUEST",
                "device": "Test Mac", "kind": "track"}

def wait(cond, t=6.0):
    end = time.time() + t
    while time.time() < end:
        if cond(): return True
        time.sleep(0.05)
    return False

S = lambda i, t: {"kind": "embed", "source": "spotify", "stream_type": "track", "url": f"https://open.spotify.com/track/{i}", "title": t}
f = FakeSpotify(); pl = sp.SeinnteoirPlayer(); pl.set_remote(f)
pl.set_queue([S("AAA", "one"), S("BBB", "two"), E("https://soundcloud.com/a/c", "cloud")], 0, True)
st = pl.get_state()
chk(st["embed_via"] == "remote" and st["buffering"], "a Spotify record goes to the listener's Spotify; the deck says it is starting")
chk(wait(lambda: ("play", "one", 0.0) in f.log and not pl.get_state()["buffering"]), "the play wish reaches Spotify")
chk(wait(lambda: pl.get_state()["duration"] == 4.5, 4), "Spotify's own length is taken")
chk(wait(lambda: pl.get_state()["idx"] == 1, 9) and ("play", "two", 0.0) in f.log, "a breath before the end, the next Spotify record is started")
chk(f.uri == "spotify:track:BBB" and f._now() < 1.0, "…so Spotify never plays on by itself")
f.dur = 200.0; chk(wait(lambda: pl.get_state()["duration"] == 200.0, 5), "a longer record: its length follows")
pl.pause(); chk(wait(lambda: ("pause",) in f.log and not f.playing, 2) and not pl.get_state()["playing"], "pause on the deck pauses Spotify")
n = len(f.log); pl.play(); chk(wait(lambda: ("resume",) in f.log[n:] and f.playing, 2) and pl.get_state()["playing"], "play picks it up where it rested, no restart")
time.sleep(1.7); f.pause(); chk(wait(lambda: not pl.get_state()["playing"], 5), "paused in Spotify itself → the deck shows paused")
pl.play(); wait(lambda: f.playing, 2)
n = len(f.log); pl.seek(1.0); chk(wait(lambda: ("seek", 1.0) in f.log[n:], 2) and not any(c[0] == "play" for c in f.log[n:]), "a seek moves within it, doesn't restart it")
pl.seek(198.6)
chk(wait(lambda: pl.get_state()["idx"] == 2, 6), "the Spotify record ends → the cue moves on to the SoundCloud one")
chk(pl.get_state()["embed_via"] == "page" and wait(lambda: not f.playing, 2), "…which plays in the page, and Spotify is quiet")
pl.clear()
f2 = FakeSpotify(); f2.why = "no_device"; p2 = sp.SeinnteoirPlayer(); p2.set_remote(f2)
p2.set_queue([S("AAA", "one")], 0, True); seq = p2.get_state()["embed_seq"]
chk(wait(lambda: p2.get_state()["embed_via"] == "page", 3) and p2.get_state()["remote"]["note"] == "no_device" and p2.get_state()["embed_seq"] > seq, "Spotify not open → the page's player takes it, and says why")
f3 = FakeSpotify(); f3.ok = False; p3 = sp.SeinnteoirPlayer(); p3.set_remote(f3)
p3.set_queue([S("AAA", "one")], 0, True); time.sleep(0.5)
chk(p3.get_state()["embed_via"] == "page" and not f3.log, "no playback permission → Spotify is never asked")
f4 = FakeSpotify(); p4 = sp.SeinnteoirPlayer(); p4.set_remote(f4)
f4.nothing = False; f4.uri = "spotify:track:GUEST"; f4.playing = True; f4.dur = 200; f4.at = time.time()
p4.get_state()
chk(wait(lambda: (p4.get_state().get("guest") or {}).get("title") == "Guest Song", 4), "the deck at rest shows what the listener's Spotify is playing")
p4.guest_control("toggle"); chk(p4.get_state()["guest"]["playing"] is False and wait(lambda: ("pause",) in f4.log, 2), "its play key pauses Spotify")
time.sleep(1.8); chk((p4.get_state().get("guest") or {}).get("playing") is False, "…and it stays on the deck, paused, to be picked up again")
p4.guest_control("toggle"); chk(wait(lambda: ("resume",) in f4.log and f4.playing, 2), "play resumes it")
p4.guest_control("next"); chk(wait(lambda: ("next",) in f4.log, 2), "next skips in Spotify")
p4.set_queue([E("https://soundcloud.com/a/c", "cloud")], 0, True)
chk(p4.get_state().get("guest") is None and wait(lambda: not f4.playing, 2), "starting something on the deck quiets the listener's Spotify")
f5 = FakeSpotify(); f5.dur = 200; p5 = sp.SeinnteoirPlayer(); p5.set_remote(f5)
p5.set_queue([S("AAA", "one"), S("BBB", "two")], 0, True); wait(lambda: f5.playing, 2); time.sleep(1.8)
f5.uri = "spotify:track:OTHER"; f5.ctx = "spotify:playlist:theirs"
chk(wait(lambda: not p5.get_state()["playing"], 5) and p5.get_state()["idx"] == 0, "the listener picks something else in Spotify → the deck rests on its record, doesn't fight")
chk(wait(lambda: (p5.get_state().get("guest") or {}).get("playing") is True, 6), "…and the deck then shows what they picked, as their own listening")
n = len(f5.log); p5.play(); chk(wait(lambda: any(c[0] == "play" and c[1] == "one" for c in f5.log[n:]), 3), "play on the deck brings its record back (a fresh start, not a resume of theirs)")
f8 = FakeSpotify(); p8 = sp.SeinnteoirPlayer(); p8.set_remote(f8)
f8.nothing = False; f8.uri = "spotify:track:THEIRS"; f8.playing = True; f8.dur = 200; f8.at = time.time()
p8.set_queue([E("https://soundcloud.com/a/c", "cloud")], 0, True)       # their Spotify is playing, not yet noticed by the deck
chk(wait(lambda: not f8.playing, 3), "a Spotify the deck hadn't noticed yet is still quieted when the deck starts something")
p8.clear()
f7 = FakeSpotify(); f7.dur = 200; p7 = sp.SeinnteoirPlayer(); p7.set_remote(f7)
p7.set_queue([S("AAA", "one"), S("BBB", "two"), S("CCC", "three")], 0, True); wait(lambda: f7.playing, 2); time.sleep(1.5)
f7.deaf = True; p7.next()
chk(wait(lambda: p7.get_state()["idx"] == 2, 9) and (p7.get_state().get("last_error") or {}).get("reason") == "Spotify wouldn't play this one",
    "Spotify says yes but stays on another record → the deck does not mistake it for its own; it says so and moves on")
f7.deaf = False; f7.other_id = True; p7.play_at(1); time.sleep(4.5)
st7 = p7.get_state()
chk(st7["idx"] == 1 and st7["playing"] and st7["last_error"]["title"] == "two" and f7.uri == "spotify:track:REGIONALCOPY",
    "the same recording under another id (a regional copy) is still recognised as the deck's own")
p7.clear()
f9 = FakeSpotify(); f9.dur = 200; p9 = sp.SeinnteoirPlayer(); p9.set_remote(f9)
MANY = lambda kind, i, t: {"kind": "embed", "source": "spotify", "stream_type": kind, "url": f"https://open.spotify.com/{kind}/{i}", "title": t}
p9.set_queue([MANY("album", "ALB", "An Album"), MANY("artist", "ART", "An Artist")], 0, True); wait(lambda: f9.playing, 2); time.sleep(4.6)
s9 = p9.get_state()
chk(s9["idx"] == 0 and s9["playing"] and s9["remote"]["title"] == "An Album" and f9.ctx == "spotify:album:ALB", "an album plays as an album, and the deck is told which of its tracks is on")
p9.next(); wait(lambda: f9.ctx == "" and f9.playing and "ART" in f9.by, 3); time.sleep(4.6)
s9 = p9.get_state()
chk(s9["idx"] == 1 and s9["playing"] and not (s9.get("last_error") or {}).get("reason"), "an artist plays too — Spotify names no context for one, so it is known by who the tracks are by")
p9.clear()
f6 = FakeSpotify(); p6 = sp.SeinnteoirPlayer(); p6.set_remote(f6)
f6.nothing = False; f6.uri = "spotify:track:GUEST"; f6.playing = True; f6.dur = 200; f6.at = time.time()
_st = f6.state; f6.state = lambda: dict(_st(), device_type="Smartphone", device="Phone")
p6.get_state(); wait(lambda: p6.get_state().get("guest"), 4)
p6.set_queue([E("https://soundcloud.com/a/c", "cloud")], 0, True); time.sleep(0.8)
chk(f6.playing and ("pause",) not in f6.log, "…but never their phone: a Spotify playing somewhere else is left alone")
for x in (p2, p3, p4, p5, p6): x.clear()

# the remote itself: a record from the deck sounds from THIS computer
from spotify_remote import SpotifyRemote
class FakeClient:
    def __init__(self): self.calls, self.devs = [], []
    def can_control(self): return True
    def can_see_playing(self): return True
    def player_devices(self): return self.devs
    def player_play(self, **kw):
        self.calls.append(kw)
        return (204, {}) if kw.get("device_id") in [d["id"] for d in self.devs] else (404, {"error": {"reason": "NO_ACTIVE_DEVICE"}})
    @staticmethod
    def _why(d): return ((d.get("error") or {}).get("reason") or "")
fc = FakeClient(); launched = []
rm = SpotifyRemote(lambda: fc, launcher=lambda: launched.append(1) or False, sleep=lambda s: None, local_names={"my mac"})
it = S("AAA", "one")
chk(rm.can_take(it) and not rm.can_take(E("https://soundcloud.com/a/b", "x")), "the remote takes Spotify records only")
PHONE = {"id": "phone", "type": "Smartphone", "is_active": True, "name": "iPhone"}
fc.devs = [PHONE]
chk(rm.play(it) == (False, "no_device") and launched, "only a phone is open → not played there; it tries to open Spotify here, then says so")
fc.devs = [PHONE, {"id": "work", "type": "Computer", "is_active": True, "name": "Work PC"}, {"id": "mac", "type": "Computer", "is_active": False, "name": "My Mac"}]
chk(rm.play(it, 12.0) == (True, "") and fc.calls[-1] == {"device_id": "mac", "uris": ["spotify:track:AAA"], "position_ms": 12000}, "this computer's own Spotify is chosen, and the record starts where the deck says")
fc.devs = [{"id": "work", "type": "Computer", "is_active": False, "name": "Work PC"}]
chk(rm.play(S("BBB", "two")) == (True, "") and fc.calls[-1]["device_id"] == "work", "the remembered Spotify has closed → it looks again")
chk(rm.play({"kind": "embed", "source": "spotify", "url": "https://open.spotify.com/playlist/PPP", "title": "pl"})[0] and fc.calls[-1].get("context_uri") == "spotify:playlist:PPP", "a playlist is played as a playlist")
# what is actually sent to Spotify: a single track must say where in its list to start,
# or the real Spotify answers yes and replays whatever it had (found 2026-11-14)
import spotify as _sp
sent = []
class _C(_sp.SpotifyClient):
    def _player_call(self, method, path, params=None, body=None, **k): sent.append((method, path, params, body)); return 204, {}
_c = _C(None)
_c.player_play(uris=["spotify:track:AAA"], position_ms=12000, device_id="mac")
_c.player_play(context_uri="spotify:album:XYZ", device_id="mac")
_c.player_play()
chk(sent[0][3] == {"uris": ["spotify:track:AAA"], "offset": {"position": 0}, "position_ms": 12000} and sent[1][3] == {"context_uri": "spotify:album:XYZ"} and sent[2][3] is None,
    "a single track is sent with its place in the list (Spotify ignores it otherwise); an album as it is; a resume with nothing")

# ─── the routes, on a fresh database ───
import schema, migrate
schema.create_database(); migrate.run_migration()
import app as mr
import ai_flags
LISTED = "0" * 21 + "A"                              # a made-up artist id "on the public list"
ai_flags.LIST_URL = ""                               # never fetch in a test
ai_flags._FILE = str(Path(_tmp.name) / "ai_list.txt")
Path(ai_flags._FILE).write_text(f"---\nhttps://open.spotify.com/artist/{LISTED}\n")
c = mr.app.test_client()
import sqlite3
from mr_paths import DB_PATH
audio = Path(_tmp.name) / "a.mp3"; audio.write_bytes(b"x" * 64)
audio2 = Path(_tmp.name) / "b.mp3"; audio2.write_bytes(b"y" * 64)
db = sqlite3.connect(DB_PATH)
db.execute("INSERT INTO tracks (id, title, artist_name, label) VALUES (1, 'Owned One', 'Someone', 'Good Label')")
db.execute("INSERT INTO tracks (id, title, artist_name, label) VALUES (2, 'Owned Two', 'Someone', 'Good Label')")
db.execute("INSERT INTO files (id, track_id, file_path, is_primary) VALUES (11, 1, ?, 1)", (str(audio),))
db.execute("INSERT INTO files (id, track_id, file_path, is_primary) VALUES (12, 2, ?, 1)", (str(audio2),))
db.commit(); db.close()

chk(c.get("/api/grupa").get_json()["grupa"] == [], "no grúpa to begin with")
chk(c.post("/api/grupa", json={"name": " "}).status_code == 400, "a grúpa needs a name")
g = c.post("/api/grupa", json={"name": "For the bus", "description": "what it is"}).get_json()["id"]
g2 = c.post("/api/grupa", json={"name": "Inner"}).get_json()["id"]
add = lambda gid, body: c.post(f"/api/grupa/{gid}/items", json=body)
r = add(g, {"kind": "track", "ref_id": 1, "note": "why"}).get_json()["item"]
chk(r["title"] == "Owned One" and r["note"] == "why" and r["playable"], "a record goes in, with its note")
chk(add(g, {"kind": "track", "ref_id": 999}).status_code == 404, "a record that isn't there is refused")
r = add(g, {"url": "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b?si=z", "title": "Streamed", "subtitle": "Her"}).get_json()["item"]
chk(r["kind"] == "stream" and r["source"] == "spotify" and r["url"].endswith("0VjIjW4GlUZAMYd2vXMi3b") and r["playable"], "a described stream link goes in without a lookup")
r = add(g, {"kind": "label", "ref_key": "Good Label"}).get_json()["item"]
chk(r["count"] == 2 and r["playable"], "a label counts its records in the room")
r = add(g, {"kind": "label", "ref_key": "Nobody Records"}).get_json()["item"]
chk(r["count"] == 0 and not r["playable"], "a label not in the room still goes in, by name")
chk(add(g, {"kind": "room", "ref_key": "@someone", "title": "Someone"}).get_json()["item"]["href"] == "/rooms/someone", "another music room goes in")
add(g2, {"kind": "track", "ref_id": 2}); add(g2, {"kind": "grupa", "ref_id": g})
chk(add(g, {"kind": "grupa", "ref_id": g2}).status_code == 201 and add(g, {"kind": "grupa", "ref_id": g}).status_code == 400, "a grúpa holds another, never itself")
d = c.get(f"/api/grupa/{g}").get_json()
chk(d["grupa"]["description"] == "what it is" and len(d["items"]) == 6, "it reads back whole")
q = c.get(f"/api/grupa/{g}/queue").get_json()
kinds = [("embed" if i.get("kind") == "embed" else i["file_id"]) for i in q["items"]]
chk(kinds == [11, "embed", 11, 12, 12], "one cue: record · stream · the label's records · the inner grúpa (no loop)")
ids = [i["id"] for i in d["items"]]
chk(q["starts"][str(ids[1])] == 1 and q["starts"][str(ids[2])] == 2, "each element knows where it starts in the cue")
c.post(f"/api/grupa/{g}/order", json={"ids": list(reversed(ids))})
chk([i["id"] for i in c.get(f"/api/grupa/{g}").get_json()["items"]] == list(reversed(ids)), "reordering holds")
c.patch(f"/api/grupa/item/{ids[0]}", json={"note": "changed my mind"})
c.patch(f"/api/grupa/{g}", json={"name": "Renamed"})
d = c.get(f"/api/grupa/{g}").get_json()
chk(d["grupa"]["name"] == "Renamed" and [i for i in d["items"] if i["id"] == ids[0]][0]["note"] == "changed my mind", "name and notes can change")
res = c.get(f"/api/grupa/search?gid={g}&q=owned").get_json()["results"]
chk([r["title"] for r in res if r["kind"] == "track"] == ["Owned One", "Owned Two"] and any(r.get("free") for r in res), "search finds records, and offers the name as a label or artist")
res = c.get(f"/api/grupa/search?gid={g}&q=two+good+some").get_json()["results"]
chk([r["title"] for r in res if r["kind"] == "track"] == ["Owned Two"], "…by any words in any order, across title, artist and label")
# names with fadas: found with or without them, and a name typed in goes in as it was typed
_db = sqlite3.connect(DB_PATH)
_db.execute("INSERT INTO tracks (id, title, artist_name, label) VALUES (90, 'Overpowered', 'Róisín Murphy', 'Ceol Órga')")
_db.commit(); _db.close()
for typed in ("roisin", "Róisín", "ROISIN murphy", "orga ceol"):
    res = c.get("/api/grupa/search", query_string={"gid": g, "q": typed}).get_json()["results"]
    chk([r["title"] for r in res if r["kind"] == "track"] == ["Overpowered"], f"…“{typed}” finds Róisín Murphy's record")
res = c.get("/api/grupa/search", query_string={"gid": g, "q": "roisin murphy"}).get_json()["results"]
chk(not any(r.get("free") and r["kind"] == "artist" for r in res) and any(r["kind"] == "artist" and r["title"] == "Róisín Murphy" for r in res),
    "…and offers her as the artist she is, not a second one without fadas")
res = c.get("/api/grupa/search", query_string={"gid": g, "q": "Siobhán Ní Bhriain"}).get_json()["results"]
chk([r["title"] for r in res if r.get("free")] == ["Siobhán Ní Bhriain", "Siobhán Ní Bhriain"], "…a name nobody has yet goes in as it was typed, fadas and all")
_db = sqlite3.connect(DB_PATH); _db.execute("DELETE FROM tracks WHERE id=90"); _db.commit(); _db.close()
res = c.get(f"/api/grupa/search?gid={g}&q=owned").get_json()["results"]
tr = {r["title"]: r for r in res if r["kind"] == "track"}
chk(tr["Owned One"]["have"] is True and tr["Owned Two"]["have"] is False and "image" in tr["Owned One"] and "album" in tr["Owned One"], "…each row says whether it is already in this grúpa, and carries its cover and album")
# Spotify's own matching is loose: keep what holds the words typed, fall back only when nothing does
import spotify as _spx
found = {"tracks": [{"title": "Flatline", "artist": "Loraine James, Miho Hatori", "album": "Detached"},
                    {"title": "Flatline", "artist": "Loraine James, Miho Hatori", "album": "Flatline (single)"},
                    {"title": "Lorraine", "artist": "Jimmy MacCarthy", "album": "x"}, {"title": "Rosie", "artist": "Bernie Heaney", "album": "y"}],
         "albums": [{"title": "Detached From The Rest Of You", "artist": "Loraine James"}, {"title": "Lorraine", "artist": "Someone"}],
         "artists": [{"title": "Loraine James"}, {"title": "James Lorraine Band"}]}
tidy = [(r["type"], r["title"]) for r in _spx.tidy_search("loraine james", found)]
chk(tidy == [("artist", "Loraine James"), ("track", "Flatline"), ("album", "Detached From The Rest Of You")], "a Spotify search keeps what holds the words: the artist by that name first, a track once, no near-misses")
loose = _spx.tidy_search("lorraine jamez", found)
chk(len(loose) >= 3 and all(r.get("loose") for r in loose), "…and a misspelling still gets Spotify's own guesses")
found2 = {"tracks": [{"title": "Archangel", "artist": "Burial", "album": "Untrue"}, {"title": "Untrue", "artist": "Burial", "album": "Untrue"}],
          "albums": [{"title": "Untrue", "artist": "Burial"}], "artists": [{"title": "Burial"}, {"title": "Madra Salach"}]}
chk([(r["type"], r["title"]) for r in _spx.tidy_search("untrue burial", found2)] == [("track", "Untrue"), ("album", "Untrue"), ("track", "Archangel")],
    "what was typed in full comes first (the track and the album by that name), and nothing that merely came along")
chk(_spx.holds(["sig", "ros"], "Sigur Rós") and _spx.fold("Ágætis byrjun") == "agaetis byrjun" and _spx._image([{"url": "big", "width": 640}, {"url": "mid", "width": 300}, {"url": "small", "width": 64}], 64) == "small", "words match as they are typed, accents aside; covers are picked at list size")
db = sqlite3.connect(DB_PATH); db.execute("UPDATE tracks SET is_deleted=1 WHERE id=1"); db.commit(); db.close()
it = [i for i in c.get(f"/api/grupa/{g}").get_json()["items"] if i["id"] == ids[0]][0]
chk(it["gone"] and it["title"] == "Owned One", "a record that leaves the room keeps its name here, marked gone")
c.delete(f"/api/grupa/item/{ids[1]}")
chk(len(c.get(f"/api/grupa/{g}").get_json()["items"]) == 5, "an element comes out")
# the records in hand in My Room → a grúpa, in one go
g3 = c.post("/api/grupa", json={"name": "From the room"}).get_json()["id"]
r = c.post(f"/api/grupa/{g3}/tracks", json={"ids": [2, 2, 999, 1]}).get_json()
chk(r["added"] == 1 and [i["title"] for i in c.get(f"/api/grupa/{g3}").get_json()["items"]] == ["Owned Two"], "many records go in at once; gone ones and repeats are left out")
# AI-made: on the public list → shown, never cued; the listener can lift it, or mark their own
SP = lambda i: f"https://open.spotify.com/track/{i}"
a1 = add(g3, {"url": SP("AI1"), "title": "Made by a machine", "subtitle": "Bot", "by_ids": f"zzz,{LISTED}", "duration_sec": 201}).get_json()["item"]
a2 = add(g3, {"url": SP("OK1"), "title": "Made by a person", "subtitle": "Her", "by_ids": "1" * 22}).get_json()["item"]
a3 = add(g3, {"url": "https://soundcloud.com/someone/a-track", "title": "Cloud", "subtitle": "Someone"}).get_json()["item"]
chk(a1["ai"] == "list" and not a1["playable"] and a2["ai"] is None and a2["playable"] and a1["duration_sec"] == 201, "a stream by an artist on the public list is marked AI-made")
q3 = c.get(f"/api/grupa/{g3}/queue").get_json()["items"]
chk([i.get("title") for i in q3] == ["Owned Two", "Made by a person", "Cloud"], "…and is left out of the cue")
chk(c.post(f"/api/grupa/item/{a1['id']}/ai", json={"ai": False}).get_json()["item"]["ai"] is None and len(c.get(f"/api/grupa/{g3}/queue").get_json()["items"]) == 4, "the listener can lift a mark they think is wrong")
chk(c.post(f"/api/grupa/item/{a3['id']}/ai", json={"ai": True}).get_json()["item"]["ai"] == "mine" and a3["by_ids"] == "someone", "…or mark a stream themselves (it hangs on who it is by)")
a4 = add(g3, {"url": "https://soundcloud.com/someone/another", "title": "Cloud two"}).get_json()["item"]
chk(a4["ai"] == "mine" and len(c.get(f"/api/grupa/{g3}/queue").get_json()["items"]) == 3, "their other tracks are covered too")
chk(c.get("/api/ai-list").get_json()["count"] == 1, "the app says what list it checks")
chk(c.get("/api/spotify/search?q=anything").get_json() == {"results": [], "connected": False} and c.post("/api/spotify/control", json={"action": "toggle"}).status_code == 409, "not signed in to Spotify: no search, no control")
st = c.get("/api/spotify/status").get_json()
chk(st["redirect_uri"] == "http://127.0.0.1:5177/api/spotify/callback" and "register_uri" not in st and not st["can_control"], "one sign-in address, port and all, for every copy (Spotify's page refuses one without a port)")
# a copy on another port opens the registered port just for Spotify's answer
import socket, urllib.request
sk = socket.socket(); sk.bind(("127.0.0.1", 0)); free = sk.getsockname()[1]; sk.close()
chk(mr._spotify_callback_listener(free) is True, "a copy on another port listens on the registered one for the answer")
page = urllib.request.urlopen(f"http://127.0.0.1:{free}/api/spotify/callback?error=access_denied", timeout=5).read().decode()
chk("access_denied" in page and "Go back to the Music Room" in page, "…Spotify's answer is taken there (here: the listener said no)")
time.sleep(0.6)
try:
    urllib.request.urlopen(f"http://127.0.0.1:{free}/api/spotify/callback", timeout=2); closed = False
except Exception:
    closed = True
chk(closed and mr._spotify_cb["server"] is None, "…and the port is let go after the one answer")
# "add all" from an opened Spotify playlist: many described tracks in one go
g4 = c.post("/api/grupa", json={"name": "From a playlist"}).get_json()["id"]
T = lambda n, **k: dict({"url": f"https://open.spotify.com/track/{str(n) * 22}?si=x", "title": f"Track {n}", "subtitle": "Some Band",
                         "image": "https://i.scdn.co/image/x", "by_ids": "1" * 22, "duration_sec": 200 + n}, **k)
r = c.post(f"/api/grupa/{g4}/streams", json={"items": [T(1), T(2), T(3)]}).get_json()
its = c.get(f"/api/grupa/{g4}").get_json()["items"]
chk(r["added"] == 3 and r["already"] == 0 and [i["title"] for i in its] == ["Track 1", "Track 2", "Track 3"], "a playlist's tracks go in together, in the playlist's order")
chk(its[0]["url"] == "https://open.spotify.com/track/" + "1" * 22 and its[0]["by_ids"] == "1" * 22 and its[0]["duration_sec"] == 201 and its[0]["playable"], "…tidied, with who they are by and how long they run, ready to play")
r = c.post(f"/api/grupa/{g4}/streams", json={"items": [T(2), T(4), T(4), {"url": "https://example.com/x", "title": "Not a stream"}, T(5, title=""), "junk"]}).get_json()
chk(r["added"] == 1 and r["already"] == 2 and len(c.get(f"/api/grupa/{g4}").get_json()["items"]) == 4, "what is already there isn't added twice; what isn't a stream is left out")
chk(c.post("/api/grupa/99999/streams", json={"items": [T(1)]}).status_code == 404, "…and not into a grúpa that isn't there")
chk(c.post("/api/grupa/from-spotify", json={"playlist_id": "x"}).status_code in (404, 405), "'Open out' is gone")
c.delete(f"/api/grupa/{g4}")
c.delete(f"/api/grupa/{g3}")
c.delete(f"/api/grupa/{g}")
chk(c.get(f"/api/grupa/{g}").status_code == 404 and c.get(f"/api/grupa/{g2}").get_json()["items"][1]["gone"], "deleting a grúpa leaves the others, marked")
r = c.post("/api/seinnteoir/queue", json={"autoplay": False, "items": q["items"]}).get_json()
chk(r["count"] == 5, "the deck takes the mixed cue")
chk(c.post("/api/seinnteoir/embed", json={"qid": "x", "ended": True}).get_json() == {"ok": False}, "a report for nothing current is ignored")
chk(c.get("/grupa").status_code == 200 and c.get(f"/grupa/{g2}").status_code == 200, "both pages serve")

# ─── 2026-11-15: a grúpa's cover, the look they share, "add to a grúpa" for several, public ───
import grupa as G
chk(G.clean_hex("#ABC") == "#aabbcc" and G.clean_hex("34557E") == "#34557e" and G.clean_hex("red") == "" and G.clean_hex(None) == "",
    "a colour is kept only as #rrggbb")
chk(G.ink_for("#161513") == "#f2efe8" and G.ink_for("#f2efe8") == "#161513" and G.ink_for("") == "",
    "words are set in ink on a light ground, in paper on a dark one")
chk(G.clean_font("Fraunces") == "Fraunces" and G.clean_font("Comic Sans") == "" and G.clean_font("x'; drop") == "",
    "a typeface is one the app carries, or nothing")
d = c.get("/api/grupa").get_json()
chk(d["look"] == {"font": "Instrument Serif", "bg": ""} and "Instrument Serif" in d["fonts"] and len(d["swatches"]) >= 6,
    "the shared look starts as the app's serif on the page's own paper; the list says what can be chosen")
gc = c.post("/api/grupa", json={"name": "Covers"}).get_json()["id"]
card = next(x for x in c.get("/api/grupa").get_json()["grupa"] if x["id"] == gc)
chk(card["cover"] == {"kind": "text", "own": False, "font": "Instrument Serif", "bg": "", "ink": ""} and card["is_public"] is False,
    "a new grúpa wears its name in the shared look, and is private")
c.post("/api/grupa/look", json={"font": "IBM Plex Mono", "bg": "#161513"})
card = next(x for x in c.get("/api/grupa").get_json()["grupa"] if x["id"] == gc)
chk(card["cover"]["font"] == "IBM Plex Mono" and card["cover"]["bg"] == "#161513" and card["cover"]["ink"] == "#f2efe8",
    "changing the shared look changes every grúpa that has none of its own")
r = c.patch(f"/api/grupa/{gc}", json={"cover": {"kind": "text", "font": "Fraunces", "bg": "#34557E"}}).get_json()
chk(r["grupa"]["cover"] == {"kind": "text", "own": True, "font": "Fraunces", "bg": "#34557e", "ink": "#f2efe8"},
    "a grúpa can have a look of its own")
c.post("/api/grupa/look", json={"font": "Bagnard", "bg": ""})
chk(c.get(f"/api/grupa/{gc}").get_json()["grupa"]["cover"]["font"] == "Fraunces", "…which the shared look no longer touches")
c.patch(f"/api/grupa/{gc}", json={"cover": {"kind": "text", "font": "Nonsense", "bg": "javascript:alert(1)"}})
own = c.get(f"/api/grupa/{gc}").get_json()
chk(own["cover_own"]["font"] == "" and own["cover_own"]["bg"] == "" and own["grupa"]["cover"]["font"] == "Bagnard",
    "a typeface or colour it doesn't know is dropped, not stored")
# a picture: only from something in it that has one
db = sqlite3.connect(DB_PATH)
art = Path(_tmp.name) / "cover.jpg"
from PIL import Image
Image.new("RGB", (64, 64), "#b4673f").save(art, "JPEG")          # a real (tiny) picture, so a small copy can be made of it
db.execute("UPDATE tracks SET artwork_path=?, is_deleted=0 WHERE id=1", (str(art),)); db.commit(); db.close()   # (an earlier check had taken record 1 away)
i1 = c.post(f"/api/grupa/{gc}/items", json={"kind": "track", "ref_id": 1}).get_json()["item"]["id"]
i2 = c.post(f"/api/grupa/{gc}/items", json={"kind": "track", "ref_id": 2}).get_json()["item"]["id"]
i3 = c.post(f"/api/grupa/{gc}/items", json={"url": "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b", "title": "S", "subtitle": "A", "image": "https://i.scdn.co/image/abc"}).get_json()["item"]["id"]
one = c.get(f"/api/grupa/{gc}").get_json()
chk([x["item"] for x in one["cover_choices"]] == [i1, i3], "the pictures it could wear: one for each thing in it that has one")
chk(c.patch(f"/api/grupa/{gc}", json={"cover": {"kind": "item", "item": i2}}).status_code == 400, "something with no picture can't be the cover")
r = c.patch(f"/api/grupa/{gc}", json={"cover": {"kind": "item", "item": i1}}).get_json()
chk(r["grupa"]["cover"] == {"kind": "image", "image": "/api/artwork/1?s=384", "item": i1}, "a record's cover becomes the grúpa's picture")
c.delete(f"/api/grupa/item/{i1}")
chk(c.get(f"/api/grupa/{gc}").get_json()["grupa"]["cover"]["kind"] == "text", "the picture goes with the record: back to its name")
c.patch(f"/api/grupa/{gc}", json={"cover": {"kind": "shared"}})
chk(c.get(f"/api/grupa/{gc}").get_json()["grupa"]["cover"]["own"] is False, "…and it can go back to the shared look")
c.post("/api/grupa/look", json={"font": "", "bg": ""})

# "add to a grúpa": which ones already hold the thing, and taking it out again
ga = c.post("/api/grupa", json={"name": "A"}).get_json()["id"]
gb = c.post("/api/grupa", json={"name": "B"}).get_json()["id"]
c.post(f"/api/grupa/{ga}/items", json={"kind": "track", "ref_id": 2})
URL = "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
has = lambda q: {x["id"] for x in c.get("/api/grupa?" + q).get_json()["grupa"] if x["has"]}
chk({gc, ga} <= has("track=2") and gb not in has("track=2") and gc not in has("track=1"), "the window is told which grúpaí already hold a record")
chk(has("url=" + URL + "%3Fsi%3Dxyz") == {gc}, "…or a link (tracking on it or not)")
c.post(f"/api/grupa/{gb}/items", json={"kind": "room", "ref_key": "someone", "title": "Someone"})
chk(has("room=someone") == {gb}, "…or a music room")
c.post(f"/api/grupa/{ga}/remove", json={"kind": "track", "ref_id": 2})
c.post(f"/api/grupa/{gc}/remove", json={"url": URL})
c.post(f"/api/grupa/{gb}/remove", json={"kind": "room", "ref_key": "someone"})
chk(gc in has("track=2") and ga not in has("track=2") and gc not in has("url=" + URL) and has("room=someone") == set(), "unticking takes it out of that grúpa only")
r = c.post(f"/api/grupa/{ga}/items", json={"url": "https://example.org/a-piece", "title": "A piece", "subtitle": "A magazine", "image": "https://example.org/p.jpg"}).get_json()["item"]
chk(r["kind"] == "link" and r["title"] == "A piece" and r["subtitle"] == "A magazine" and r["image"] == "https://example.org/p.jpg",
    "a link that arrives described (from Explore) is kept as described, with no look-up")

# public: off until asked; what goes up is words, links and small covers
sent, gone = [], []
import green_room as GRM
real_pub, real_unpub = GRM.grupa_publish, GRM.grupa_unpublish
GRM.grupa_publish = lambda payload: (sent.append(payload), {"id": 1, "updated_at": "now", "count": len(payload["items"])})[1]
GRM.grupa_unpublish = lambda local_id: (gone.append(local_id), {"private": True})[1]
r = c.post(f"/api/grupa/{gc}/public", json={"on": True}).get_json()
chk(r["is_public"] is True and r["public_error"].startswith("Sign in first") and not sent, "a public grúpa needs a signed-in room: said plainly, nothing sent")
db = sqlite3.connect(DB_PATH)
db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_token', 't')")
db.execute("UPDATE tracks SET gr_track_id=77 WHERE id=1"); db.execute("UPDATE tracks SET is_own_work=1 WHERE id=2"); db.commit(); db.close()
c.post(f"/api/grupa/{gc}/items", json={"kind": "track", "ref_id": 1, "note": "the opener"})
c.post(f"/api/grupa/{gc}/items", json={"url": URL, "title": "S", "subtitle": "A", "image": "https://i.scdn.co/image/abc"})
c.post(f"/api/grupa/{gc}/items", json={"kind": "label", "ref_key": "Good Label"})
r = c.post(f"/api/grupa/{gc}/public", json={"on": True}).get_json()
chk(r == {"ok": True, "is_public": True, "public_error": ""} and len(sent) == 1, "signed in, it goes up at once")
pay = sent[-1]
where = {i["title"]: i["where"] for i in pay["items"]}
chk(pay["local_id"] == gc and pay["name"] == "Covers" and where == {"Owned Two": "own", "Owned One": "campus", "S": "stream", "Good Label": "name"},
    "each thing says where it can be heard: this person's own work, the rooms server, a stream, a name")
flat = repr({k: v for k, v in pay.items() if k != "art"})
chk(str(audio) not in flat and str(audio2) not in flat and "file_path" not in flat and _tmp.name not in flat, "no file path goes up, anywhere in it")
one = next(i for i in pay["items"] if i["title"] == "Owned One")
chk(one["note"] == "the opener" and one["server_track_id"] == 77 and one.get("art") in pay["art"], "a record goes up with its note, where it lives, and a small copy of its cover")
n0 = len(sent)
c.patch(f"/api/grupa/{gc}", json={"description": "what it is"})
db = sqlite3.connect(DB_PATH); dirty = db.execute("SELECT public_dirty FROM grupa WHERE id=?", (gc,)).fetchone()[0]; db.close()
mr._grupa_public_flush()
chk(dirty == 1 and len(sent) == n0 + 1 and sent[-1]["description"] == "what it is", "a change to a public grúpa is sent again, off the request")
mr._grupa_public_flush()
chk(len(sent) == n0 + 1, "…and only when something changed")
def boom(payload): raise GRM.GRError(GRM.GRUPA_OLD_SERVER)
GRM.grupa_publish = boom
r = c.post(f"/api/grupa/bulk", json={"ids": [ga, gb], "action": "public"}).get_json()
cards = {x["id"]: x for x in c.get("/api/grupa").get_json()["grupa"]}
chk(r["n"] == 2 and "needs one restart" in r["public_error"] and cards[ga]["is_public"] and "needs one restart" in cards[ga]["public_error"],
    "several at once; a rooms server from before grúpaí is named as the reason, and they stay marked to go up")
r = c.post(f"/api/grupa/bulk", json={"ids": [ga, gb], "action": "private"}).get_json()
cards = {x["id"]: x for x in c.get("/api/grupa").get_json()["grupa"]}
chk(not cards[ga]["is_public"] and not cards[gb]["is_public"] and set(gone) >= {ga, gb}, "…and made private again together")
GRM.grupa_unpublish = lambda local_id: (_ for _ in ()).throw(GRM.GRError("the Green Room server can't be reached"))
c.post(f"/api/grupa/{gc}/public", json={"on": False})
import json as _j
def setting(key):
    db = sqlite3.connect(DB_PATH); row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone(); db.close()
    return row[0] if row else ""
chk(gc in _j.loads(setting("grupa_unpublish_pending") or "[]"), "taking one down with the server away is remembered")
GRM.grupa_unpublish = lambda local_id: (gone.append(("later", local_id)), {"private": True})[1]
mr._grupa_public_flush()
chk(("later", gc) in gone and _j.loads(setting("grupa_unpublish_pending") or "[]") == [], "…and done the next time it is there")
r = c.post("/api/grupa/bulk", json={"ids": [ga, gb, 99999], "action": "delete"}).get_json()
left = {x["id"] for x in c.get("/api/grupa").get_json()["grupa"]}
chk(r["n"] == 2 and ga not in left and gb not in left and gc in left, "several deleted at once; the others are left alone")
chk(c.post("/api/grupa/bulk", json={"ids": [gc], "action": "explode"}).status_code == 400, "an action it doesn't know is refused")
GRM.grupa_publish, GRM.grupa_unpublish = real_pub, real_unpub
db = sqlite3.connect(DB_PATH); db.execute("DELETE FROM settings WHERE key='gr_token'"); db.commit(); db.close()

# the deck's Spotify mark: bring Spotify forward — or, with no app, open the record's page
import spotify_remote as SR
runs = []
class _R:
    def __init__(self, code): self.returncode = code
def fake_run(code_for_app):
    def run(cmd, **k): runs.append(cmd); return _R(code_for_app if cmd[:2] == ["open", "-a"] else 0)
    return run
if sys.platform == "darwin":
    chk(SR.show_app(URL, _run=fake_run(0)) == "app" and runs == [["open", "-a", "Spotify"]], "the Spotify mark brings the app forward and touches nothing else")
    runs.clear()
    chk(SR.show_app(URL, _run=fake_run(1)) == "web" and runs[-1] == ["open", URL], "no Spotify app here: the record's own page opens instead")
    runs.clear()
    chk(SR.show_app("https://evil.example/x", _run=fake_run(1)) == "" and runs == [["open", "-a", "Spotify"]], "…and only a Spotify page, never some other address")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
sys.stdout.flush()
os._exit(1 if fails else 0)
