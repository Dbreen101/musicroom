"""Where the sound goes (sound_out.py) — the list of outputs, the Bluetooth
speakers the Mac knows, connecting one, and the routes the deck calls.
Nothing real is switched or connected: Bluetooth and the output change are
stand-ins; the one real thing read is the Mac's own list of outputs.
Run:  ./venv/bin/python test_sound_out.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sound_out as so

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ── the Mac's own list (read only) ──
if so.MAC:
    outs = so.outputs()
    chk(isinstance(outs, list) and all(set(o) == {"uid", "name", "kind", "current"} for o in outs), "outputs: uid, name, kind, current — nothing else leaks out")
    chk(sum(1 for o in outs if o["current"]) <= 1, "at most one output is the current one")
    cur = so.current()
    if cur:
        chk(so.set_output(cur["uid"]) == (True, "") and so.current()["uid"] == cur["uid"], "choosing the output that is already chosen changes nothing")
    chk(so.set_output("no-such-speaker") == (False, "gone"), "a speaker that isn't there: 'gone'")
    ranks = [so._KINDS.get(k, ("", 4))[1] for k in ("bltn", "blue", "airp", "usb ", "grup", "virt")]
    chk(ranks == sorted(ranks), "real speakers sort ahead of groups and virtual devices")

# ── the Bluetooth speakers this Mac knows (a stand-in for system_profiler) ──
FAKE = {"SPBluetoothDataType": [{
    "controller_properties": {"controller_state": "attrib_on"},
    "device_connected": [{"Desk Speaker": {"device_address": "AA:BB:CC:00:11:22", "device_minorType": "Speaker"}}],
    "device_not_connected": [
        {"Kitchen Speaker": {"device_address": "AA:BB:CC:00:11:33", "device_minorType": "Speaker"}},
        {"Big Headphones": {"device_address": "aa-bb-cc-00-11-44", "device_minorType": "Headphones"}},
        {"A Keyboard": {"device_address": "AA:BB:CC:00:11:55", "device_minorType": "Keyboard"}},
        {"No Type": {"device_address": "AA:BB:CC:00:11:66"}},
        {"Odd Address": {"device_address": "$(rm -rf)", "device_minorType": "Speaker"}},
    ]}]}
calls = []
def run(): calls.append(1); return json.dumps(FAKE)
so.MAC = True
so._paired.update(at=0.0, rows=None)
rows = so.paired_bluetooth(_run=run)
chk([r["name"] for r in rows] == ["Big Headphones", "Desk Speaker", "Kitchen Speaker"], "only sound devices are listed (no keyboard, no untyped device), by name")
chk(next(r for r in rows if r["name"] == "Desk Speaker")["connected"] is True and not rows[0]["connected"], "connected or not is carried")
chk(all(so._ADDR.match(r["address"]) for r in rows), "an address that isn't an address never gets through")
so.paired_bluetooth(_run=run)
chk(len(calls) == 1, "asked once, then remembered for a while")
so.paired_bluetooth(force=True, _run=run)
chk(len(calls) == 2, "…unless a fresh look is asked for")
OFF = {"SPBluetoothDataType": [{"controller_properties": {"controller_state": "attrib_off"}}]}
chk(so.paired_bluetooth(force=True, _run=lambda: json.dumps(OFF)) is None, "Bluetooth switched off: no list")
chk(so.paired_bluetooth(force=True, _run=lambda: "not json") is None, "an answer that can't be read: no list, no crash")

# ── connecting one (the child process and the Mac's outputs are stand-ins) ──
world = {"outs": [{"uid": "BuiltInSpeakerDevice", "name": "Laptop Speakers", "kind": "this computer", "current": True}], "set": []}
so.outputs = lambda: [dict(o) for o in world["outs"]]
def fake_set(uid):
    world["set"].append(uid)
    for o in world["outs"]: o["current"] = (o["uid"] == uid)
    return (True, "")
so.set_output = fake_set
KIT = "AA:BB:CC:00:11:33"
chk(so.connect_bluetooth("nonsense") == (False, "bad"), "a bad address is refused before anything runs")
spawned = []
chk(so.connect_bluetooth(KIT, _spawn=lambda cmd: (spawned.append(cmd), 4)[1], _sleep=lambda s: None) == (False, "failed") and len(spawned) == 1, "the speaker won't connect: 'failed'")
chk(spawned[0][-2:] == ["--bt-connect", KIT] and spawned[0][0] == sys.executable, "the connection runs in its own process, given only the address")
chk(so.connect_bluetooth(KIT, wait=0.05, _spawn=lambda cmd: 0, _sleep=lambda s: None) == (False, "slow") and not world["set"], "connected but never offered as an output: 'slow', nothing switched")
looks = {"n": 0}
def appear(s):
    looks["n"] += 1
    if looks["n"] == 3: world["outs"].append({"uid": "aa-bb-cc-00-11-33:output", "name": "Kitchen Speaker", "kind": "Bluetooth", "current": False})
chk(so.connect_bluetooth(KIT, wait=5, _spawn=lambda cmd: 0, _sleep=appear) == (True, ""), "it connects, turns up as an output a moment later…")
chk(world["set"] == ["aa-bb-cc-00-11-33:output"] and so.current()["name"] == "Kitchen Speaker", "…and becomes where the sound goes")
spawned.clear(); world["set"].clear(); world["outs"][0]["current"] = True; world["outs"][1]["current"] = False
chk(so.connect_bluetooth(KIT, _spawn=lambda cmd: (spawned.append(cmd), 0)[1]) == (True, "") and not spawned and world["set"], "already connected: no second connection, it is simply chosen")
chk(so._output_for("AA:BB:CC:00:11:33")["name"] == "Kitchen Speaker" and so._output_for("11:22:33:44:55:66") is None, "a speaker is matched to its output by its address")
chk(so._output_for("11:22:33:44:55:66", "Kitchen Speaker")["name"] == "Kitchen Speaker", "…or, failing that, by its exact name over Bluetooth")
chk(so._bt_connect_main("nonsense") == 2, "the child process refuses a bad address without touching Bluetooth")
sys.frozen = True
try: chk(so._connect_cmd(KIT) == [sys.executable, "--mr-bt-connect", KIT], "the packaged app re-invokes itself to connect")
finally: del sys.frozen

# ── the routes the deck calls ──
from flask import Flask
app = Flask(__name__)
events = []
so.register(app, track=lambda n, d: events.append((n, d)))
so._ca = True                                             # "CoreAudio is there" for the supported flag
c = app.test_client()
so._paired.update(at=0.0, rows=None)
real_pb = so.paired_bluetooth
so.paired_bluetooth = lambda force=False, _run=None: real_pb(force=force, _run=lambda: json.dumps(FAKE))
world["outs"] = [{"uid": "BuiltInSpeakerDevice", "name": "Laptop Speakers", "kind": "this computer", "current": True},
                 {"uid": "aa-bb-cc-00-11-22:output", "name": "Desk Speaker", "kind": "Bluetooth", "current": False}]
d = c.get("/api/sound/outputs").get_json()
chk(d["supported"] and len(d["outputs"]) == 2 and "bluetooth" not in d, "the plain list: outputs only (quick)")
d = c.get("/api/sound/outputs?paired=1").get_json()
chk([b["name"] for b in d["bluetooth"]] == ["Big Headphones", "Kitchen Speaker"], "with Bluetooth: only speakers not connected yet (one already an output is left out)")
r = c.post("/api/sound/output", json={"uid": "aa-bb-cc-00-11-22:output"})
chk(r.status_code == 200 and r.get_json()["ok"] and next(o for o in r.get_json()["outputs"] if o["current"])["name"] == "Desk Speaker", "choosing a speaker answers with the new list")
chk(events == [("sound_out", {"kind": "Bluetooth"})], "the trial log notes the kind of speaker chosen, never its name")
so.set_output = lambda uid: (False, "gone")
r = c.post("/api/sound/output", json={"uid": "nope"})
chk(r.status_code == 409 and r.get_json()["why"] == "gone", "a speaker that has gone: said plainly")
r = c.post("/api/sound/bluetooth/connect", json={"address": "nonsense"})
chk(r.status_code == 409 and r.get_json()["why"] == "bad" and "bluetooth" in r.get_json(), "a failed connection answers with the reason and the lists")
opened = []
so.open_settings = lambda which="sound": (opened.append(which), True)[1]
chk(c.post("/api/sound/settings", json={"pane": "bluetooth"}).get_json()["ok"] and opened == ["bluetooth"], "the Mac's own settings can be opened from the list")
chk(set(so._PANES) == {"sound", "bluetooth"}, "…and only those two")

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
