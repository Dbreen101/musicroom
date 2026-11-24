"""sound_out.py — where this computer's sound goes, and the speakers it could go to.

Daithí, 2026-11-14: "connect to bluetooth and wifi devices such as speakers
directly from in the app like the spotify app."

Everything the app plays comes out of the Mac's ONE chosen sound output: the
deck's own files (pygame), a SoundCloud player in the page, and Spotify when
it plays on this computer. So "pick a speaker" here means what it means in the
Mac's own Sound menu: choose that output, and all of it follows.

  outputs()            what the Mac can play through right now (built-in,
                       wired, a connected Bluetooth speaker, an AirPlay one
                       when the Mac lists it), the current one marked
  set_output(uid)      choose one
  paired_bluetooth()   Bluetooth speakers / headphones this Mac already knows
                       but isn't connected to (asked of Apple's own
                       system_profiler — a second or two, cached)
  connect_bluetooth()  connect one of those, wait for it to turn up as an
                       output, and choose it
  open_settings()      the Mac's own Sound / Bluetooth settings, for what
                       can't be done from here (pairing something new; AirPlay
                       speakers the Mac doesn't list as outputs)

CoreAudio is reached through ctypes (no extra dependency). The Bluetooth
connection runs in a short-lived CHILD process (`python sound_out.py
--bt-connect <address>`, or the packaged app re-invoked with
`--mr-bt-connect`): macOS asks permission for Bluetooth the first time, and a
process that asks without being allowed to can be stopped by the system — that
must never be the app itself.

Nothing here runs unless someone opens the speaker list or picks from it.
On anything that isn't a Mac every call answers "not supported" and the deck
hides the control.

Routes (register(app)): GET /api/sound/outputs[?paired=1] · POST
/api/sound/output {uid} · POST /api/sound/bluetooth/connect {address} · POST
/api/sound/settings {pane}.
"""
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time

MAC = sys.platform == "darwin"

# ── CoreAudio, read through ctypes ───────────────────────────────────────────
_ca = _cf = None
_lock = threading.Lock()


def _fcc(s):
    return struct.unpack(">I", s.encode("ascii"))[0]


_SYS = 1                                    # kAudioObjectSystemObject
_GLOBAL, _OUTPUT, _MAIN = _fcc("glob"), _fcc("outp"), 0


def _load():
    """Load CoreAudio once. False where there is none (not a Mac)."""
    global _ca, _cf
    if _ca is not None:
        return bool(_ca)
    if not MAC:
        _ca = False
        return False
    try:
        import ctypes
        import ctypes.util

        class Addr(ctypes.Structure):
            _fields_ = [("sel", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("elem", ctypes.c_uint32)]

        ca = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
        cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        P, U32 = ctypes.POINTER, ctypes.c_uint32
        ca.AudioObjectGetPropertyDataSize.argtypes = [U32, P(Addr), U32, ctypes.c_void_p, P(U32)]
        ca.AudioObjectGetPropertyData.argtypes = [U32, P(Addr), U32, ctypes.c_void_p, P(U32), ctypes.c_void_p]
        ca.AudioObjectSetPropertyData.argtypes = [U32, P(Addr), U32, ctypes.c_void_p, U32, ctypes.c_void_p]
        for f in (ca.AudioObjectGetPropertyDataSize, ca.AudioObjectGetPropertyData, ca.AudioObjectSetPropertyData):
            f.restype = ctypes.c_int32
        cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, U32]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        ca._Addr, ca._ct = Addr, ctypes
        _ca, _cf = ca, cf
        return True
    except Exception:
        _ca = False
        return False


def _u32(obj, sel, scope=_GLOBAL):
    ct = _ca._ct
    a = _ca._Addr(_fcc(sel), scope, _MAIN)
    v, n = ct.c_uint32(0), ct.c_uint32(4)
    return v.value if _ca.AudioObjectGetPropertyData(obj, ct.byref(a), 0, None, ct.byref(n), ct.byref(v)) == 0 else None


def _size(obj, sel, scope=_GLOBAL):
    ct = _ca._ct
    a = _ca._Addr(_fcc(sel), scope, _MAIN)
    n = ct.c_uint32(0)
    return n.value if _ca.AudioObjectGetPropertyDataSize(obj, ct.byref(a), 0, None, ct.byref(n)) == 0 else 0


def _str(obj, sel, scope=_GLOBAL):
    ct = _ca._ct
    a = _ca._Addr(_fcc(sel), scope, _MAIN)
    v, n = ct.c_void_p(0), ct.c_uint32(ct.sizeof(ct.c_void_p))
    if _ca.AudioObjectGetPropertyData(obj, ct.byref(a), 0, None, ct.byref(n), ct.byref(v)) != 0 or not v.value:
        return ""
    buf = ct.create_string_buffer(1024)
    ok = _cf.CFStringGetCString(v, buf, 1024, 0x08000100)          # UTF-8
    _cf.CFRelease(v)
    return buf.value.decode("utf-8", "replace") if ok else ""


def _device_ids():
    ct = _ca._ct
    n = _size(_SYS, "dev#")
    if not n:
        return []
    ids = (ct.c_uint32 * (n // 4))()
    a = _ca._Addr(_fcc("dev#"), _GLOBAL, _MAIN)
    nn = ct.c_uint32(n)
    if _ca.AudioObjectGetPropertyData(_SYS, ct.byref(a), 0, None, ct.byref(nn), ct.byref(ids)) != 0:
        return []
    return list(ids)[: nn.value // 4]


# what a transport is called on the list, and where it sorts
_KINDS = {
    "bltn": ("this computer", 0), "blue": ("Bluetooth", 1), "blea": ("Bluetooth", 1), "airp": ("AirPlay", 2),
    "usb ": ("USB", 3), "hdmi": ("screen", 3), "dprt": ("screen", 3), "thun": ("Thunderbolt", 3), "1394": ("FireWire", 3),
    "avb ": ("network", 3), "pci ": ("sound card", 3), "ccwd": ("continuity", 3),
    "grup": ("group", 8), "aggr": ("group", 8), "virt": ("virtual", 9),
}


def outputs():
    """Every output the Mac could play through right now:
    [{uid, name, kind, current}] — real speakers first, groups and virtual
    devices last. [] where it can't be read."""
    if not _load():
        return []
    with _lock:
        cur = _u32(_SYS, "dOut")
        rows = []
        for d in _device_ids():
            if not _size(d, "stm#", _OUTPUT):                       # no output streams: a microphone
                continue
            if _u32(d, "dflt", _OUTPUT) == 0:                       # can't be the Mac's output (Teams, Zoom…)
                continue
            if _u32(d, "hidn") == 1:
                continue
            uid, name = _str(d, "uid "), _str(d, "lnam")
            if not uid or not name:
                continue
            tr = _u32(d, "tran")
            code = struct.pack(">I", tr).decode("ascii", "replace") if tr else ""
            kind, rank = _KINDS.get(code, ("", 4))
            rows.append({"uid": uid, "name": name, "kind": kind, "current": d == cur, "_rank": rank, "_id": d})
    rows.sort(key=lambda r: (r["_rank"], r["name"].lower()))
    for r in rows:
        r.pop("_rank", None); r.pop("_id", None)
    return rows


def current():
    """The current output: {uid, name, kind} or None."""
    return next((o for o in outputs() if o["current"]), None)


def set_output(uid):
    """Choose an output by its uid. (ok, why) — why ∈ '' | unsupported | gone | refused."""
    if not _load():
        return False, "unsupported"
    with _lock:
        dev = next((d for d in _device_ids() if _str(d, "uid ") == uid), None)
        if dev is None:
            return False, "gone"
        if _u32(_SYS, "dOut") == dev:
            return True, ""
        ct = _ca._ct
        a = _ca._Addr(_fcc("dOut"), _GLOBAL, _MAIN)
        v = ct.c_uint32(dev)
        err = _ca.AudioObjectSetPropertyData(_SYS, ct.byref(a), 0, None, 4, ct.byref(v))
    return (True, "") if err == 0 else (False, "refused")


# ── Bluetooth speakers the Mac already knows ─────────────────────────────────
_ADDR = re.compile(r"^[0-9A-Fa-f]{2}([-:][0-9A-Fa-f]{2}){5}$")
_AUDIO_TYPES = ("speaker", "headphone", "headset", "audio", "hi-fi", "hifi", "loudspeaker", "car")
_paired = {"at": 0.0, "rows": None}


def _norm(addr):
    return re.sub(r"[^0-9a-f]", "", (addr or "").lower())


def paired_bluetooth(force=False, _run=None):
    """Bluetooth sound devices this Mac is paired with: [{name, address, type,
    connected}]. Asked of system_profiler (Apple's own tool; no permission
    needed), cached for 30 seconds. None when Bluetooth is off or can't be read."""
    if not MAC:
        return None
    now = time.time()
    if not force and _paired["rows"] is not None and now - _paired["at"] < 30:
        return _paired["rows"]
    try:
        raw = (_run or (lambda: subprocess.run(["/usr/sbin/system_profiler", "SPBluetoothDataType", "-json"],
                                                capture_output=True, text=True, timeout=12).stdout))()
        d = (json.loads(raw).get("SPBluetoothDataType") or [{}])[0]
    except Exception:
        return None
    if "off" in str((d.get("controller_properties") or {}).get("controller_state") or "").lower():
        _paired.update(at=now, rows=None)
        return None
    rows = []
    for key, connected in (("device_connected", True), ("device_not_connected", False)):
        for entry in d.get(key) or []:
            for name, p in (entry or {}).items():
                kind = str((p or {}).get("device_minorType") or "")
                addr = str((p or {}).get("device_address") or "")
                if not _ADDR.match(addr) or not any(t in kind.lower() for t in _AUDIO_TYPES):
                    continue
                rows.append({"name": name, "address": addr, "type": kind.lower(), "connected": connected})
    rows.sort(key=lambda r: r["name"].lower())
    _paired.update(at=now, rows=rows)
    return rows


def _output_for(address, name=""):
    """The output that belongs to a Bluetooth address (its uid carries the
    address), else one of that exact name over Bluetooth."""
    want = _norm(address)
    outs = outputs()
    return (next((o for o in outs if want and want in _norm(o["uid"])), None)
            or next((o for o in outs if name and o["kind"] == "Bluetooth" and o["name"] == name), None))


def _connect_cmd(address):
    if getattr(sys, "frozen", False):                    # the packaged app re-invokes itself (native/launcher.py)
        return [sys.executable, "--mr-bt-connect", address]
    return [sys.executable, os.path.abspath(__file__), "--bt-connect", address]


def connect_bluetooth(address, name="", wait=14.0, _spawn=None, _sleep=time.sleep):
    """Connect a paired Bluetooth speaker, wait for the Mac to offer it as an
    output, and choose it. (ok, why) — why ∈ '' | unsupported | bad | failed |
    slow (connected, but it never turned up as an output) | refused."""
    if not MAC:
        return False, "unsupported"
    if not _ADDR.match(address or ""):
        return False, "bad"
    out = _output_for(address, name)
    if not out:
        try:
            rc = (_spawn or (lambda cmd: subprocess.run(cmd, capture_output=True, timeout=25).returncode))(_connect_cmd(address))
        except Exception:
            rc = -1
        if rc != 0:
            return False, "failed"
        end = time.time() + wait
        while time.time() < end and not out:
            _sleep(0.5)
            out = _output_for(address, name)
    _paired["at"] = 0.0                                   # its "connected" has changed
    if not out:
        return False, "slow"
    ok, why = set_output(out["uid"])
    return ok, ("" if ok else why or "refused")


def _bt_connect_main(address):
    """The child process: ask IOBluetooth to connect. Exit 0 = connected."""
    if not _ADDR.match(address or ""):
        return 2
    try:
        import objc
        ns = {}
        objc.loadBundle("IOBluetooth", ns, bundle_path="/System/Library/Frameworks/IOBluetooth.framework")
        Dev = objc.lookUpClass("IOBluetoothDevice")
        dev = Dev.deviceWithAddressString_(address.replace(":", "-"))
        if dev is None:
            return 3
        if dev.isConnected():
            return 0
        rc = dev.openConnection()                         # waits until it is connected, or isn't
        return 0 if (rc == 0 or dev.isConnected()) else 4
    except Exception:
        return 5


_PANES = {"sound": "x-apple.systempreferences:com.apple.Sound-Settings.extension",
          "bluetooth": "x-apple.systempreferences:com.apple.BluetoothSettings"}


def open_settings(which="sound"):
    """Open the Mac's own Sound or Bluetooth settings."""
    if not MAC or which not in _PANES:
        return False
    try:
        subprocess.Popen(["/usr/bin/open", _PANES[which]])
        return True
    except Exception:
        return False


# ── routes ───────────────────────────────────────────────────────────────────
def register(app, track=None):
    """Add /api/sound/* to the app. `track(name, data)` logs a trial event."""
    from flask import jsonify, request

    def _state(with_paired=False):
        outs = outputs()
        out = {"supported": bool(MAC and _ca), "outputs": outs}
        if with_paired:
            rows = paired_bluetooth()
            here = {_norm(o["uid"]) for o in outs}
            out["bluetooth"] = None if rows is None else [
                r for r in rows if not r["connected"] and not any(_norm(r["address"]) in u for u in here)]
        return out

    @app.route("/api/sound/outputs")
    def api_sound_outputs():
        return jsonify(_state(request.args.get("paired") == "1"))

    @app.route("/api/sound/output", methods=["POST"])
    def api_sound_output():
        uid = str((request.get_json(silent=True) or {}).get("uid") or "")
        ok, why = set_output(uid)
        if ok and track:
            cur = current() or {}
            try: track("sound_out", {"kind": cur.get("kind") or ""})
            except Exception: pass
        return jsonify({"ok": ok, "why": why, **_state()}), (200 if ok else 409)

    @app.route("/api/sound/bluetooth/connect", methods=["POST"])
    def api_sound_bt_connect():
        d = request.get_json(silent=True) or {}
        ok, why = connect_bluetooth(str(d.get("address") or ""), str(d.get("name") or ""))
        if ok and track:
            try: track("sound_out", {"kind": "Bluetooth", "connected": True})
            except Exception: pass
        return jsonify({"ok": ok, "why": why, **_state(True)}), (200 if ok else 409)

    @app.route("/api/sound/settings", methods=["POST"])
    def api_sound_settings():
        which = str((request.get_json(silent=True) or {}).get("pane") or "sound")
        return jsonify({"ok": open_settings(which)})


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--bt-connect":
        sys.exit(_bt_connect_main(sys.argv[2]))
    for o in outputs():
        print(("* " if o["current"] else "  ") + o["name"] + ("  · " + o["kind"] if o["kind"] else ""))
