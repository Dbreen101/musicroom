"""Record shopping's one play through the deck (seinnteoir_player.py): a
streamed record marked `once` is played straight away after the record playing,
the cue carries on after it, and it leaves the cue the moment the deck moves
off it — by its end, next, back, or picking another — and never comes back
from a saved cue. No network, no sound. Run:  ./venv/bin/python test_deck_once.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["MUSICROOM_DATA"] = _tmp.name
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.pop("MR_GREEN_ROOM", None)

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import seinnteoir_player as sp
sp._QUEUE_FILE = None
E = lambda t, once=False: {"kind": "embed", "url": f"https://soundcloud.com/a/{t}", "source": "soundcloud", "title": t, "once": once}
titles = lambda p: [q["title"] for q in p.queue]

p = sp.SeinnteoirPlayer()
p.set_queue([E("a"), E("b"), E("c")], 0, True)
p.add([E("shop", True)], play_now=True)
chk(titles(p) == ["a", "shop", "b", "c"] and p.idx == 1, "a one-play goes straight after the record playing, and plays now")
qid = p.queue[1]["qid"]
p.embed_report(qid, ended=True)
chk(titles(p) == ["a", "b", "c"] and p.queue[p.idx]["title"] == "b", "when it ends it leaves the cue, and the cue carries on")

p.add([E("shop2", True)], play_now=True)
p.next()
chk("shop2" not in titles(p) and p.queue[p.idx]["title"] == "c", "next: it leaves")

p.add([E("shop3", True)], play_now=True)
p.prev()
chk("shop3" not in titles(p) and p.queue[p.idx]["title"] == "c", "back: it leaves, and the one before plays")

p.add([E("shop4", True)], play_now=True)
at = titles(p).index("shop4")
p.play_at(0)
chk("shop4" not in titles(p) and p.queue[p.idx]["title"] == "a", "picking another record: it leaves")
p.add([E("shop5", True)], play_now=True)
p.play_at(len(p.queue) - 1)                 # the last one, after it
chk("shop5" not in titles(p) and p.queue[p.idx]["title"] == "c", "…also when the one picked comes after it")

p.add([E("shop6", True)], play_now=True)
p.add([E("shop7", True)], play_now=True)
chk("shop6" not in titles(p) and "shop7" in titles(p), "a second one-play takes the place of the first")

p2 = sp.SeinnteoirPlayer()
p2.set_queue([E("solo", True)], 0, True)
p2.next()
chk(p2.queue == [] and p2.idx == -1, "alone in the cue: it ends and the cue is empty")

f = os.path.join(_tmp.name, "q.json")
sp._QUEUE_FILE = f
p3 = sp.SeinnteoirPlayer(); p3.set_queue([E("x"), E("y", True), E("z")], 1, False)
p4 = sp.SeinnteoirPlayer()
chk(titles(p4) == ["x", "z"], "a saved cue comes back without it")
sp._QUEUE_FILE = None

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
