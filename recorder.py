"""Recorder — capture the laptop's audio OUTPUT into a WAV, to sample into the
Music Room (a YouTube tab, any app). System-audio capture can't happen in the
WebView (WKWebView's screen-capture is video-only), so it runs here in the Flask
process with sounddevice (PortAudio) + soundfile.

The user routes their output through a loopback device (BlackHole) via a
Multi-Output Device so they still HEAR it; we record that loopback's INPUT.
sounddevice is an optional dependency — if it's absent the recorder degrades to
"unavailable" rather than crashing the app (e.g. on a machine without it).

Realtime-safe: the PortAudio callback only copies the block into a queue and
updates a level meter; a writer thread drains the queue to disk, so disk I/O
never stalls the audio thread (matches the app's known buffer-underrun caution —
and we record to local SSD, never the external drive).
"""
import os
import queue
import threading
import time

# input device names that mean "the system's own output looped back"
_LOOPBACK_HINTS = ("blackhole", "loopback", "soundflower", "aggregate", "multi-output")


def available():
    """(ok, error) — is the capture stack importable on this machine?"""
    try:
        import sounddevice  # noqa: F401
        import soundfile    # noqa: F401
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def list_devices():
    """Input devices, flagging the loopback one(s) and a best default index."""
    ok, err = available()
    if not ok:
        return {"available": False, "error": err, "devices": [], "loopback_index": None}
    import sounddevice as sd
    devices, loopback_index = [], None
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = d["name"]
        is_loop = any(h in name.lower() for h in _LOOPBACK_HINTS)
        devices.append({
            "index": i, "name": name,
            "channels": d["max_input_channels"],
            "samplerate": int(d.get("default_samplerate") or 48000),
            "loopback": is_loop,
        })
        if is_loop and loopback_index is None:
            loopback_index = i
    return {"available": True, "devices": devices, "loopback_index": loopback_index}


class _Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = False
        self._stream = None
        self._file = None
        self._q = None
        self._writer = None
        self._stop = None
        self.path = None
        self.started_at = 0.0
        self.level = 0.0          # 0..1 RMS, updated per audio block
        self.device_name = None

    def start(self, dest_dir, device_index=None):
        with self.lock:
            if self.active:
                return {"ok": False, "error": "already recording"}
            ok, err = available()
            if not ok:
                return {"ok": False, "error": "Recording needs the 'sounddevice' package (" + (err or "") + ")."}
            import sounddevice as sd
            import soundfile as sf
            import numpy as np

            if device_index is None:
                device_index = list_devices().get("loopback_index")
            if device_index is None:
                return {"ok": False, "error": "No loopback input found — install BlackHole and a Multi-Output Device."}

            try:
                d = sd.query_devices(int(device_index))
            except Exception as e:
                return {"ok": False, "error": f"device {device_index}: {e}"}
            samplerate = int(d.get("default_samplerate") or 48000)
            channels = min(2, d.get("max_input_channels", 2)) or 2

            os.makedirs(dest_dir, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d %H-%M-%S")
            path = os.path.join(dest_dir, f"Sample {stamp}.wav")

            try:
                self._file = sf.SoundFile(path, mode="x", samplerate=samplerate,
                                          channels=channels, subtype="PCM_24")
            except Exception as e:
                return {"ok": False, "error": f"could not open file: {e}"}

            self._q = queue.Queue()
            self._stop = threading.Event()
            self.level = 0.0

            def _cb(indata, frames, t, status):
                self._q.put(indata.copy())
                try:
                    self.level = float(np.sqrt(np.mean(indata ** 2)))
                except Exception:
                    pass

            def _drain():
                while not self._stop.is_set() or not self._q.empty():
                    try:
                        self._file.write(self._q.get(timeout=0.2))
                    except queue.Empty:
                        pass
                    except Exception:
                        break

            try:
                self._stream = sd.InputStream(samplerate=samplerate, device=int(device_index),
                                              channels=channels, dtype="float32", callback=_cb)
                self._writer = threading.Thread(target=_drain, daemon=True)
                self._writer.start()
                self._stream.start()
            except Exception as e:
                self._stop.set()
                try:
                    self._file.close()
                    os.remove(path)
                except Exception:
                    pass
                return {"ok": False, "error": f"could not start capture: {e}"}

            self.active = True
            self.path = path
            self.started_at = time.time()
            self.device_name = d["name"]
            return {"ok": True, "device": d["name"], "samplerate": samplerate, "channels": channels}

    def status(self):
        return {
            "recording": self.active,
            "elapsed": round(time.time() - self.started_at, 1) if self.active else 0.0,
            "level": round(self.level, 4),
            "device": self.device_name,
        }

    def stop(self):
        with self.lock:
            if not self.active:
                return {"ok": False, "error": "not recording"}
            self.active = False
            duration = round(time.time() - self.started_at, 2)
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
            try:
                self._stop.set()
                if self._writer:
                    self._writer.join(timeout=3)
            except Exception:
                pass
            try:
                self._file.flush(); self._file.close()
            except Exception:
                pass
            path = self.path
            self.path = None
            self.level = 0.0
            return {"ok": True, "path": path, "duration": duration}

    def cancel(self):
        r = self.stop()
        p = r.get("path")
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass
        return {"ok": True}


recorder = _Recorder()
