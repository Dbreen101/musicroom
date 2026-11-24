"""The app updating itself — what it accepts, and what it refuses to put in."""
import os, plistlib, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app_update as U

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
tmp = tempfile.mkdtemp()

chk(U.where()["can"] is False and "code" in U.where()["why"], "run from the code, it does not try to replace itself")
chk(U.start("2026.11.23", tmp) is False and U.state()["step"] == "error", "…and a start says why instead of fetching")
chk(U.start("../../x; rm", tmp) is False and "version" in U.state()["error"], "a version that isn't a version is refused")
chk(U.asset_name().startswith("Music.Room.GR.") and U.asset_name().endswith(".zip"), "it knows which download is this computer's")
chk(U.PAGE == "https://github.com/Dbreen101/musicroom/releases/latest", "the page it falls back to is the project's own")

if sys.platform == "darwin":
    def fake(bundle_id, version, name="Music Room GR.app"):
        d = tempfile.mkdtemp(dir=tmp); app = os.path.join(d, name)
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
            plistlib.dump({"CFBundleIdentifier": bundle_id, "CFBundleShortVersionString": version}, fh)
        open(os.path.join(app, "Contents", "MacOS", "music-room"), "w").write("#!/bin/sh\n")
        z = os.path.join(d, "app.zip")
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, z], check=True)
        return z
    def unpack(z, version):
        try:
            return U._unpack(z, tempfile.mkdtemp(dir=tmp), version), ""
        except Exception as e:
            return None, str(e)
    got, why = unpack(fake(U.BUNDLE_ID, "2026.11.23"), "2026.11.23")
    chk(got and got.endswith(".app") and os.path.isfile(os.path.join(got, "Contents", "MacOS", "music-room")), "the right app at the right version is accepted")
    got, why = unpack(fake("com.someone.else", "2026.11.23"), "2026.11.23")
    chk(got is None and "isn't the Music Room GR app" in why, "another app in the download is refused")
    got, why = unpack(fake(U.BUNDLE_ID, "2026.11.20"), "2026.11.23")
    chk(got is None and "version" in why, "another version than the one asked for is refused")

    # the swap itself: the old app is replaced, kept until the new one is in, and put back if it can't be
    def swap(new_exists=True):
        d = tempfile.mkdtemp(dir=tmp); old = os.path.join(d, "Music Room GR.app"); os.makedirs(old)
        open(os.path.join(old, "which"), "w").write("old")
        work = os.path.join(d, "update"); new = os.path.join(work, "new", "Music Room GR.app")
        if new_exists:
            os.makedirs(new); open(os.path.join(new, "which"), "w").write("new")
        else:
            os.makedirs(os.path.dirname(new))
        sh = os.path.join(d, "swap.sh"); open(sh, "w").write(U._MAC)
        subprocess.run(["/bin/sh", sh, "999999", old, new, work, "no"], check=False, timeout=60)
        return open(os.path.join(old, "which")).read(), os.path.exists(old + ".before-update"), os.path.exists(work)
    chk(swap() == ("new", False, False), "the swap puts the new app where the old one was and clears up after itself")
    chk(swap(new_exists=False)[0] == "old", "…and with nothing to put in, the old app is back where it was")

    big = os.path.join(tmp, "f.bin"); open(big, "wb").write(b"x" * 300000)
    try:
        U._download(big, os.path.join(tmp, "out.bin"), 300001, ""); ok = False
    except RuntimeError:
        ok = True
    chk(ok and not os.path.exists(os.path.join(tmp, "out.bin")), "a download of the wrong size is thrown away")
    try:
        U._download(big, os.path.join(tmp, "out.bin"), 300000, "00" * 32); ok = False
    except RuntimeError:
        ok = True
    chk(ok, "a download that doesn't match the release's fingerprint is thrown away")

# ── nothing left behind after an update ──
data = tempfile.mkdtemp(dir=tmp)
apps = tempfile.mkdtemp(dir=tmp); mine = os.path.join(apps, "Music Room GR.app"); os.makedirs(mine)
left = mine + ".before-update"; os.makedirs(os.path.join(left, "Contents"))
os.makedirs(os.path.join(data, "update", "new")); open(os.path.join(data, "update", "app.zip"), "w").write("half a download")
os.makedirs(os.path.join(data, "update-helper")); open(os.path.join(data, "update-helper", "swap.sh"), "w").write("#")
keep = os.path.join(data, "library.db"); open(keep, "w").write("the person's records")
real_where, real_run = U.where, U.subprocess.run
U.where = lambda: {"can": True, "why": "", "app": mine}
U._set(step="idle")
gone = U.tidy(data)
chk(not os.path.exists(left) and not os.path.exists(os.path.join(data, "update")) and not os.path.exists(os.path.join(data, "update-helper")),
    "an old app left by a cut-short update, a half download and the helper are cleared away")
chk(os.path.isdir(mine) and open(keep).read() == "the person's records" and len(gone) == 3, "…and the running app and the person's own things are not touched")
os.makedirs(os.path.join(data, "update")); U._set(step="downloading")
chk(U.tidy(data) == [] and os.path.isdir(os.path.join(data, "update")), "nothing is cleared while an update is under way")
U._set(step="idle")

if sys.platform == "darwin":
    other = os.path.join(tempfile.mkdtemp(dir=tmp), "Music Room GR-2.app"); os.makedirs(other)
    stranger = os.path.join(tempfile.mkdtemp(dir=tmp), "Someone Else.app"); os.makedirs(stranger)
    class R:                                             # what Spotlight would answer
        returncode = 0
        stdout = "\n".join([mine, other, mine + ".before-update", "/Users/x/.Trash/Music Room GR.app", "/private/var/folders/AppTranslocation/1/d/Music Room GR.app"])
    asked = []
    def fake_run(cmd, **k):
        asked.append(cmd)
        if cmd[0].endswith("mdfind"):
            return R
        if cmd[0].endswith("osascript"):                 # "Finder, move this to the Bin"
            os.rmdir(cmd[-1]); return type("X", (), {"returncode": 0, "stdout": ""})
        return real_run(cmd, **k)
    U.subprocess.run = fake_run
    chk(U.other_copies() == [other], "other copies: found by what the app is; never this app, the Bin, or what an update is clearing")
    chk(U.BUNDLE_ID in asked[0][1], "…asked of Spotlight by the app's own id, not by its name")
    out = U.bin_copies([other, stranger])
    chk(out == {"binned": [other], "left": []} and not os.path.exists(other) and os.path.isdir(stranger) and os.path.isdir(mine),
        "only a copy it found itself goes to the Bin — never a path handed to it, never the running app")
    U.where = real_where
    chk(U.other_copies() == [], "run from the code, it names no copies at all")
    U.subprocess.run = real_run
U.where = real_where

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
