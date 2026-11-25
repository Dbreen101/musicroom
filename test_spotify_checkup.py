"""Whole tracks, or only previews — and if previews, exactly why.

On 25 Nov 2026 a fellow was given Daithí's Spotify key, signed in, and still heard 30-second
previews; the app could not say why. Three things must all be true, and Spotify answers the
same empty way when any is not: the key's owner has listed the person (a key in development
mode), the account is Premium, and a Spotify app is open on a computer under the SAME account.
`SpotifyClient.checkup()` asks Spotify one thing after another and names the first that fails.
No network here: Spotify is a stand-in.

Run:  ./venv/bin/python test_spotify_checkup.py
"""
import os, sys
PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ); os.chdir(PROJ)
import spotify
import spotify_remote
from spotify import SpotifyClient, SCOPES, KEY_NO_PREMIUM, CHECKUP_WORDS

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

class Box(dict):
    def set(self, k, v): self[k] = v
world = {}
def client(connected=True, scopes=SCOPES, key=True):
    c = SpotifyClient.__new__(SpotifyClient)
    c.s = Box({spotify.KEY_SCOPES: scopes, spotify.KEY_CLIENT_ID: "abc" if key else ""})
    c.is_connected = lambda: connected
    c.scopes = lambda: set(scopes.split())
    asked = []
    def call(method, path, params=None, body=None, timeout=8, _retry=True):
        asked.append(path)
        return world[path]
    c._player_call = call
    c.asked = asked
    return c
ME = {"id": "kyle", "display_name": "Kyle", "product": "premium"}
MAC = {"id": "d1", "name": "Kyle's MacBook", "type": "Computer"}
PHONE = {"id": "d2", "name": "Kyle's iPhone", "type": "Smartphone"}
NOT_LISTED = (403, {"raw": "User not registered in the Developer Dashboard"})

world.update({"/me": (200, ME), "/me/player/devices": (200, {"devices": [PHONE, MAC]})})
c = client(); r = c.checkup(app_there=True)
chk(r == {"step": "ready", "ok": True, "name": "Kyle", "product": "premium", "devices": ["Kyle's MacBook"]},
    "listed, Premium, the Spotify app open on a computer: ready, and it names the computer (never the phone)")
chk(c.s.get(spotify.KEY_USER_NAME) == "Kyle", "a sign-in that had no name yet learns it")

chk(client(key=False).checkup()["step"] == "no_key", "no key in the app")
c = client(connected=False)
chk(c.checkup()["step"] == "signed_out" and not c.asked, "not signed in: said without asking Spotify anything")

world["/me"] = NOT_LISTED
c = client(); r = c.checkup()
chk(r["step"] == "unlisted" and r["ok"] is False and c.asked == ["/me"],
    "signed in but not on the key's list (Spotify answers 403): named as that, the first thing asked")
world["/me"] = (403, {"error": {"status": 403, "message": "User not registered in the Developer Dashboard"}})
chk(client().checkup()["step"] == "unlisted", "…whichever way Spotify words its refusal")
world["/me"] = (403, {"error": {"status": 403, "message": "Insufficient client scope"}})
chk(client().checkup()["step"] == "reconnect", "a sign-in without the permission is told to sign in again")
world["/me"] = (200, ME)
chk(client(scopes="user-library-read user-read-private").checkup()["step"] == "reconnect", "…so is one from before the deck could play")

world["/me"] = (200, dict(ME, product="free"))
c = client(); r = c.checkup()
chk(r["step"] == "free" and r["product"] == "free" and "/me/player/devices" not in c.asked, "a free account is named as that")
world["/me"] = (200, ME)
c = client(); c.s.set(KEY_NO_PREMIUM, "1"); c.checkup()
chk(c.s.get(KEY_NO_PREMIUM) == "", "someone who has Premium now is no longer marked as without it")

world["/me/player/devices"] = (200, {"devices": [PHONE]})
chk(client().checkup(app_there=False)["step"] == "no_app", "no Spotify app on this computer")
chk(client().checkup(app_there=True)["step"] == "no_device", "the app is here but none is open for this account (a phone doesn't count)")
chk(client().checkup()["step"] == "no_device", "…and when it can't be told whether the app is here")
world["/me/player/devices"] = NOT_LISTED
chk(client().checkup()["step"] == "unlisted", "refused at the second question for not being listed: still named as that")
for status, step in ((0, "network"), (429, "busy"), (401, "signed_out")):
    world["/me"] = (status, {})
    chk(client().checkup()["step"] == step, f"Spotify answering {status}: {step}")
world["/me"] = (200, ME)

steps = "no_key signed_out network busy unlisted reconnect free no_app no_device ready".split()
chk(all(s in CHECKUP_WORDS and CHECKUP_WORDS[s][0] for s in steps), "every answer has words for the person")
chk("EMAIL" in CHECKUP_WORDS["unlisted"][1] and "User Management" in CHECKUP_WORDS["unlisted"][1], "not listed: the words say who must do what, and where")

# the deck: with nowhere to play, it asks which of these it is instead of always saying "open Spotify"
class C:
    def __init__(self, step): self.step = step
    def checkup(self): return {"step": self.step}
r = spotify_remote.SpotifyRemote(lambda: None, launcher=lambda: False, sleep=lambda s: None, local_names={"x"})
chk([r._why_no_device(C(s)) for s in ("unlisted", "free", "signed_out", "no_device", "no_app", "network")]
    == ["unlisted", "premium", "signin", "no_device", "no_device", "no_device"], "the deck's reason follows what Spotify said")
chk(r._why_no_device(object()) == "no_device", "a client that can't be asked: as before")
chk(r._reason(type("X", (), {"_why": staticmethod(lambda d: "User not registered in the Developer Dashboard")})(), 403, {}) == "unlisted",
    "a play refused for not being listed is named as that")
chk(spotify_remote.spotify_app_here() in (True, False, None), "asking whether the Spotify app is here never fails")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
