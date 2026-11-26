"""Signing in to the rooms server (gr_signin.py): an email and a password (kept
only as a hash), the limit on laptops and on laptops taking music at once, the
record of sign-ins, two-factor (optional for sellers, required for the master),
codes by email (asleep without a mail server), the account rules, and that no
password, code or sign-in ever reaches the activity log.
A fresh database, no network, no sound. Run:  ./venv/bin/python test_gr_signin.py"""
import os
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_signin_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")
os.environ.pop("MR_SMTP_HOST", None)

import gr_server
import gr_master
import gr_signin

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
client = gr_server.app.test_client()
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def sql(q, *p):
    with closing(gr_server.db()) as c:
        return c.execute(q, p).fetchall()
def run(q, *p):
    with closing(gr_server.db()) as c:
        c.execute(q, p); c.commit()
def signup(name, fp, **more):
    gr_master._rate.clear()
    return client.post("/api/signup", json=dict({"name": name, "fingerprint": fp, "agreed": True, "device_name": "laptop"}, **more))
def login(email, password, fp, **more):
    return client.post("/api/login", json=dict({"email": email, "password": password, "fingerprint": fp, "device_name": "laptop"}, **more))
def now_code(secret, shift=0): return gr_signin.totp(secret, int(time.time() // 30) + shift)
PW = "correct-horse-battery"

# ── an email and a password at sign-up ──
r = signup("Aoife", "mac-a", email="Aoife@Example.ie", password=PW)
d = r.get_json()
chk(r.status_code == 200 and d["token"], "a new account is made with an email and a password, and the laptop is signed in")
aoife = d["token"]
row = sql("SELECT * FROM gr_accounts WHERE name='Aoife'")[0]
chk(row["email"] == "Aoife@Example.ie" and row["email_fold"] == "aoife@example.ie", "the email is kept as written, and compared in small letters")
chk(row["password_hash"].startswith("scrypt:") and PW not in row["password_hash"], "the password is kept only as a salted scrypt hash")
me = client.get("/api/me", headers=hdr(aoife)).get_json()
chk(me["signin"]["has_password"] and me["signin"]["email"] == "Aoife@Example.ie" and not me["signin"]["email_verified"]
    and "password_hash" not in str(me), "the account knows it has a password; nothing secret is in its own page")
chk(signup("Other", "mac-o", email="aoife@example.IE", password=PW).status_code == 409, "one account per email, whatever the capitals")
chk(signup("Short", "mac-s", email="s@example.ie", password="too-short").status_code == 400, "a password under ten characters is refused")
chk(signup("Same", "mac-s", email="same@example.ie", password="same@example.ie").status_code == 400, "a password can't be the email itself")
chk(signup("Bad", "mac-b", email="not-an-email", password=PW).status_code == 400, "an email has to look like one")
chk(signup("Half", "mac-h", email="half@example.ie").status_code == 400, "an email with no password is refused")
r = signup("Old App", "mac-old")
chk(r.status_code == 200, "an older app, with no place for them, can still make an account while the rule is off")
old_app = r.get_json()
gr_signin.set_rules_here({"need_password": True})
r = signup("Old App Two", "mac-old2")
chk(r.status_code == 400 and r.get_json().get("need_password"), "with the rule on, a new account must have an email and a password")
gr_signin.set_rules_here({"need_password": False})

# ── signing in with them ──
gr_master._rate.clear()
r = login("aoife@example.ie", PW, "mac-a")
chk(r.status_code == 200 and r.get_json()["token"] == aoife, "the same laptop signs in again and keeps its sign-in")
r = login("AOIFE@example.ie", PW, "mac-a2")
chk(r.status_code == 200 and r.get_json()["token"] != aoife, "a second laptop signs in with the email and password")
aoife2 = r.get_json()["token"]
a, b = login("aoife@example.ie", "wrong-password-1", "mac-x"), login("nobody@example.ie", "wrong-password-1", "mac-x")
chk(a.status_code == b.status_code == 403 and a.get_json()["error"] == b.get_json()["error"],
    "a wrong password and an unknown email are refused in the same words")
chk(client.post("/api/join", json={"invite_code": row["invite_code"], "fingerprint": "mac-x"}).status_code == 403,
    "an account with a password is no longer opened by its account code")
chk(client.post("/api/join", json={"invite_code": old_app["invite_code"], "fingerprint": "mac-old"}).status_code == 200,
    "an account from before passwords still signs in with its code")
gr_master._rate.clear()
tries = [login("aoife@example.ie", f"wrong-password-{i}", "mac-x").status_code for i in range(gr_signin.RULES["login_tries"] + 1)]
chk(tries[:-1] == [403] * gr_signin.RULES["login_tries"] and tries[-1] == 429, "wrong passwords for one email are counted, then there is a wait")
chk(login("aoife@example.ie", PW, "mac-a").status_code == 429, "…even for the right password, until the wait is over")
gr_master._rate.clear()

# ── laptops: how many, and how many at once ──
chk(login("aoife@example.ie", PW, "mac-a3").status_code == 403, f"a third laptop is refused (the limit is {gr_server.MAX_DEVICES})")
sec = client.get("/api/me/security", headers=hdr(aoife)).get_json()
chk(len(sec["devices"]) == 2 and [x["this"] for x in sec["devices"]] == [True, False] and sec["limits"] == {"devices": 2, "at_once": 1},
    "the account sees its laptops, which one this is, and the limits")
chk(any(s["new"] and s["ok"] for s in sec["signins"]) and any(not s["ok"] and s["note"] == "devices full" for s in sec["signins"])
    and any(s["note"] == "wrong password" for s in sec["signins"]), "sign-ins are written down: new laptops, refusals, wrong passwords")
chk(sql("SELECT COUNT(*) FROM gr_events WHERE kind='new_device'")[0][0] >= 1, "a new laptop is noted in the activity log")
other = [x for x in sec["devices"] if not x["this"]][0]["id"]
chk(client.post(f"/api/me/devices/{other}/out", headers=hdr(aoife)).get_json()["out"]
    and client.get("/api/me", headers=hdr(aoife2)).status_code == 401, "a laptop can be signed out from another; its sign-in stops working")
chk(login("aoife@example.ie", PW, "mac-a3").status_code == 200, "which makes room for another laptop")
aoife3 = login("aoife@example.ie", PW, "mac-a3").get_json()["token"]
gr_signin.set_rules_here({"devices": 3})
chk(login("aoife@example.ie", PW, "mac-a4").status_code == 200, "the limit is a rule: raised to three, a third laptop signs in")
gr_signin.set_rules_here({"devices": 2})
run("DELETE FROM gr_devices WHERE fingerprint='mac-a4'")
gr_server.make_invite("Seller", kind="artist", handle="seller")
music = TMP / "music"; music.mkdir()
import audio_fixture
audio_fixture.make_flac(music / "one.flac", seed=1, seconds=1, title="One", artist="Seller")
audio_fixture.make_flac(music / "two.flac", seed=2, seconds=1, title="Two", artist="Seller")
gr_server.add_folder(str(music), owner="seller")
run("UPDATE gr_accounts SET plan='c' WHERE name='Aoife'")
t1, t2 = [r["id"] for r in sql("SELECT id FROM gr_tracks ORDER BY id")]
r = client.post("/api/borrow", json={"track_id": t1}, headers=hdr(aoife))
chk(r.status_code == 200, "one laptop borrows a record")
b1 = r.get_json()["borrow_id"]
r = client.post("/api/borrow", json={"track_id": t2}, headers=hdr(aoife3))
chk(r.status_code == 409 and r.get_json().get("in_use"), "the account's other laptop is refused while the first has just been taking music")
chk(client.post("/api/borrow", json={"track_id": t2}, headers=hdr(aoife)).status_code == 200, "the first laptop carries on")
chk(client.get("/api/me", headers=hdr(aoife3)).status_code == 200, "…and the other laptop still works for everything else")
run("UPDATE gr_devices SET used_at=? WHERE fingerprint='mac-a'", time.time() - gr_signin.RULES["at_once_window_s"] - 1)
chk(client.get(f"/api/download/{b1}", headers=hdr(aoife3)).status_code == 200,
    "once the first has been quiet for the window, the other may take music")
gr_signin.set_rules_here({"at_once": 2})
chk(client.post("/api/borrow", json={"track_id": t1}, headers=hdr(aoife)).status_code == 200, "that limit is a rule too")
gr_signin.set_rules_here({"at_once": 1})

# ── changing a password; an older account setting one ──
r = client.post("/api/me/password", json={"old": "not-the-password", "new": "another-good-password"}, headers=hdr(aoife))
chk(r.status_code == 403, "changing a password needs the one it has now")
r = client.post("/api/me/password", json={"old": PW, "new": "another-good-password"}, headers=hdr(aoife))
chk(r.status_code == 200 and r.get_json()["signed_out"] == 1 and client.get("/api/me", headers=hdr(aoife3)).status_code == 401,
    "changed: the account's other laptops are signed out")
gr_master._rate.clear()
chk(login("aoife@example.ie", PW, "mac-a").status_code == 403 and login("aoife@example.ie", "another-good-password", "mac-a").status_code == 200,
    "the old password is dead and the new one works")
old_tok = old_app["token"]
chk(client.post("/api/me/password", json={"new": PW}, headers=hdr(old_tok)).status_code == 400, "an older account needs an email with its first password")
chk(client.post("/api/me/password", json={"new": PW, "email": "aoife@example.ie"}, headers=hdr(old_tok)).status_code == 409, "…one nobody else has")
r = client.post("/api/me/password", json={"new": PW, "email": "old@example.ie"}, headers=hdr(old_tok))
chk(r.status_code == 200 and r.get_json()["has_password"] and client.get("/api/me", headers=hdr(old_tok)).status_code == 200,
    "an older account sets an email and a password, and stays signed in")
chk(client.post("/api/me/email", json={"email": "new@example.ie"}, headers=hdr(old_tok)).status_code == 403
    and client.post("/api/me/email", json={"email": "new@example.ie", "password": PW}, headers=hdr(old_tok)).status_code == 200,
    "changing the email needs the password")

# ── two-factor: who may, switching it on, signing in with it ──
chk(client.post("/api/me/2fa/start", headers=hdr(aoife)).status_code == 403, "two-factor is not offered to a listener")
seller = client.post("/api/join", json={"invite_code": sql("SELECT invite_code FROM gr_accounts WHERE handle='seller'")[0][0],
                                         "fingerprint": "mac-seller"}).get_json()["token"]
seller2 = client.post("/api/join", json={"invite_code": sql("SELECT invite_code FROM gr_accounts WHERE handle='seller'")[0][0],
                                          "fingerprint": "mac-seller-2"}).get_json()["token"]
r = client.post("/api/me/2fa/start", headers=hdr(seller))
key = r.get_json()["key"]
chk(r.status_code == 200 and len(key) == 32 and r.get_json()["link"].startswith("otpauth://totp/"), "a seller is given a key for their authenticator app")
chk(gr_signin.totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59 // 30) == "287082", "the six numbers are the standard ones (RFC 6238's own example)")
chk(not client.get("/api/me", headers=hdr(seller)).get_json()["signin"]["two_factor"]["on"], "nothing is on until a code comes back")
chk(client.post("/api/me/2fa/confirm", json={"code": "000000"}, headers=hdr(seller)).status_code == 403, "a wrong code switches nothing on")
r = client.post("/api/me/2fa/confirm", json={"code": now_code(key)}, headers=hdr(seller))
chk(r.status_code == 200 and r.get_json()["two_factor"]["on"] and r.get_json()["signed_out"] == 1
    and client.get("/api/me", headers=hdr(seller2)).status_code == 401, "the right code switches it on, and signs the account's other laptops out")
code_s = sql("SELECT invite_code FROM gr_accounts WHERE handle='seller'")[0][0]
gr_master._rate.clear()
r = client.post("/api/join", json={"invite_code": code_s, "fingerprint": "mac-seller-2"})
chk(r.status_code == 401 and r.get_json().get("need_2fa"), "a new laptop is asked for the six numbers")
chk(client.post("/api/join", json={"invite_code": code_s, "fingerprint": "mac-seller-2", "otp": "123456"}).status_code == 403, "wrong numbers are refused")
chk(client.post("/api/join", json={"invite_code": code_s, "fingerprint": "mac-seller-2", "otp": now_code(key)}).status_code == 403,
    "numbers already used once are refused (the ones that switched it on)")
r = client.post("/api/join", json={"invite_code": code_s, "fingerprint": "mac-seller-2", "otp": now_code(key, 1)})
chk(r.status_code == 200, "the next numbers sign the laptop in")
chk(client.post("/api/join", json={"invite_code": code_s, "fingerprint": "mac-seller"}).status_code == 200,
    "a laptop that is already signed in is not asked again")
chk(client.post("/api/me/2fa/off", json={"code": "111111"}, headers=hdr(seller)).status_code == 403, "switching it off needs a code")
gr_signin.set_rules_here({"maker_2fa": "required"})
run("UPDATE gr_accounts SET totp_last=0 WHERE handle='seller'")
chk(client.post("/api/me/2fa/off", json={"code": now_code(key)}, headers=hdr(seller)).status_code == 403, "required by the rules, it can't be switched off")
gr_server.make_invite("Bare Seller", kind="label", handle="bare")
bare = client.post("/api/join", json={"invite_code": sql("SELECT invite_code FROM gr_accounts WHERE handle='bare'")[0][0],
                                       "fingerprint": "mac-bare"}).get_json()["token"]
import io
r = client.post("/api/my/records", data={"rights": "1", "audio": (io.BytesIO(b"x"), "x.wav")}, headers=hdr(bare), content_type="multipart/form-data")
chk(r.status_code == 403 and r.get_json().get("need_2fa") == "setup", "required of sellers: one without it can't put a record up")
gr_signin.set_rules_here({"maker_2fa": "optional"})
run("UPDATE gr_accounts SET totp_last=0 WHERE handle='seller'")
chk(client.post("/api/me/2fa/off", json={"code": now_code(key)}, headers=hdr(seller)).status_code == 200
    and not client.get("/api/me", headers=hdr(seller)).get_json()["signin"]["two_factor"]["on"], "optional again: a code switches it off")

# ── the master must have two-factor ──
gr_master.make_master("Daithí", handle="daithi")
mcode = sql("SELECT invite_code FROM gr_accounts WHERE handle='daithi'")[0][0]
gr_master._rate.clear()
master = client.post("/api/join", json={"invite_code": mcode, "fingerprint": "mac-master"}).get_json()["token"]
r = client.get("/api/master/overview", headers=hdr(master))
chk(r.status_code == 403 and r.get_json().get("need_2fa") == "setup", "the master's page is shut until the master sets up two-factor")
chk(client.get("/api/master/rules", headers=hdr(master)).status_code == 403 and client.get("/api/master/applications", headers=hdr(master)).status_code == 403
    and client.get("/api/master/sim", headers=hdr(master)).status_code == 403, "…every part of it")
chk(client.get("/api/me", headers=hdr(master)).get_json()["signin"]["two_factor"]["missing"], "the account is told it is missing")
mkey = client.post("/api/me/2fa/start", headers=hdr(master)).get_json()["key"]
client.post("/api/me/2fa/confirm", json={"code": now_code(mkey)}, headers=hdr(master))
chk(client.get("/api/master/overview", headers=hdr(master)).status_code == 200, "set up, the master's page opens")
run("UPDATE gr_accounts SET totp_last=0 WHERE handle='daithi'")
chk(client.post("/api/me/2fa/off", json={"code": now_code(mkey)}, headers=hdr(master)).status_code == 403, "the master can't switch it off")
chk(client.post("/api/join", json={"invite_code": mcode, "fingerprint": "mac-thief"}).status_code == 401,
    "the master's code alone signs no new laptop in")
chk(client.get("/api/master/rules", headers=hdr(aoife)).status_code == 403 and client.get("/api/master/signins", headers=hdr(seller)).status_code == 403,
    "nobody else reads the rules or the sign-ins")
r = client.post("/api/master/rules", json={"rules": {"devices": 4, "maker_2fa": "required"}}, headers=hdr(master))
chk(r.status_code == 200 and r.get_json()["rules"]["devices"] == 4 and r.get_json()["rules"]["maker_2fa"] == "required", "the master changes the rules")
chk(client.post("/api/master/rules", json={"rules": {"devices": 0}}, headers=hdr(master)).status_code == 400
    and client.post("/api/master/rules", json={"rules": {"nonsense": 1}}, headers=hdr(master)).status_code == 400, "…within bounds, and only real ones")
client.post("/api/master/rules", json={"rules": {"devices": 2, "maker_2fa": "optional"}}, headers=hdr(master))
aid = sql("SELECT id FROM gr_accounts WHERE name='Aoife'")[0][0]
r = client.post(f"/api/master/accounts/{aid}/password", headers=hdr(master))
temp = r.get_json()["password"]
gr_master._rate.clear()
chk(r.status_code == 200 and client.get("/api/me", headers=hdr(aoife)).status_code == 401 and login("aoife@example.ie", temp, "mac-a").status_code == 200,
    "a forgotten password: the master makes a new one to pass on; the account's laptops are signed out")
sid = sql("SELECT id FROM gr_accounts WHERE handle='seller'")[0][0]
client.post("/api/me/2fa/confirm", json={"code": now_code(client.post("/api/me/2fa/start", headers=hdr(seller)).get_json()["key"])}, headers=hdr(seller))
chk(client.post(f"/api/master/accounts/{sid}/two-factor", headers=hdr(master)).status_code == 200
    and not sql("SELECT totp_secret FROM gr_accounts WHERE id=?", sid)[0][0], "a lost authenticator: the master takes two-factor off that account")
said = client.get("/api/master/signins", headers=hdr(master)).get_json()["signins"]
chk(len(said) > 10 and {"at", "name", "device", "from", "how", "new", "ok"} <= set(said[0]), "the master reads every sign-in")
gr_signin.two_factor_off(*[__import__("sqlite3").connect(os.environ["MR_GR_DB"])], sql("SELECT id FROM gr_accounts WHERE handle='daithi'")[0][0])
chk(client.get("/api/master/overview", headers=hdr(master)).status_code == 403, "from Terminal the master's own two-factor can be taken off (and the page shuts again)")
gr_signin.set_rules_here({"master_2fa": "off"})

# ── codes by email: asleep without a mail server, working with one ──
aoife = login("aoife@example.ie", temp, "mac-a").get_json()["token"]
chk(client.post("/api/me/email/verify", headers=hdr(aoife)).status_code == 409, "with no mail server, no code is sent and none is asked")
gr_signin.set_rules_here({"email_check": True})
chk(login("aoife@example.ie", temp, "mac-new-1").status_code == 200, "the rule on but no mail server: sign-in on a new laptop still works")
run("DELETE FROM gr_devices WHERE fingerprint='mac-new-1'")
sent = []
os.environ["MR_SMTP_HOST"] = "mail.example.invalid"
gr_signin.send_mail = lambda to, subject, body: sent.append((to, body)) or True
r = login("aoife@example.ie", temp, "mac-new-2")
chk(r.status_code == 401 and r.get_json().get("need_email_code") and sent and sent[-1][0] == "Aoife@Example.ie",
    "with a mail server and the rule on, a new laptop is sent a code at the account's email")
the_code = sent[-1][1].split()[0]
chk(the_code not in str(sql("SELECT code_hash FROM gr_email_codes")[0][0]), "only the code's hash is kept")
chk(login("aoife@example.ie", temp, "mac-new-2", email_code="000000").status_code == 403, "a wrong code is refused")
chk(login("aoife@example.ie", temp, "mac-elsewhere", email_code=the_code).status_code in (401, 403), "the code is for the laptop that asked")
r = login("aoife@example.ie", temp, "mac-new-2", email_code=the_code)
chk(r.status_code == 200 and sql("SELECT email_verified_at FROM gr_accounts WHERE name='Aoife'")[0][0], "the right code signs the laptop in, and proves the email")
chk(login("aoife@example.ie", temp, "mac-a").status_code == 200 and len(sent) == 1, "a laptop the account already uses is not asked")
gr_signin.set_rules_here({"email_check": False})
os.environ.pop("MR_SMTP_HOST")

# ── nothing secret in the logs, and no cookies ──
everything = " ".join(str(tuple(r)) for t in ("gr_events", "gr_signins") for r in sql(f"SELECT * FROM {t}"))
tokens = [r[0] for r in sql("SELECT token FROM gr_devices")]
chk(not any(s in everything for s in [PW, temp, "another-good-password", key, mkey, the_code] + tokens),
    "no password, sign-in, authenticator key or emailed code is in the activity log or the sign-in record")
r = login("aoife@example.ie", temp, "mac-a")
chk("Set-Cookie" not in r.headers, "the server sets no cookie: a laptop's sign-in travels only in the request's own header")

# ── a database from before all this ──
os.environ["MR_GR_DB"] = str(TMP / "older.db")
with closing(gr_server.db()) as c:
    c.executescript("""
        CREATE TABLE gr_tracks(id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, title TEXT, artist TEXT,
            album TEXT, duration_s REAL, format TEXT, size_bytes INTEGER, price_cents INTEGER NOT NULL, added_at TEXT NOT NULL);
        CREATE TABLE gr_accounts(id INTEGER PRIMARY KEY, name TEXT NOT NULL, invite_code TEXT NOT NULL UNIQUE,
            wallet_cents INTEGER NOT NULL, sub_month TEXT, created_at TEXT NOT NULL);
        CREATE TABLE gr_devices(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, name TEXT, fingerprint TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE gr_borrows(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, track_id INTEGER NOT NULL, key_hex TEXT NOT NULL,
            nonce_hex TEXT NOT NULL, month TEXT NOT NULL, borrowed_at TEXT NOT NULL, returned_at TEXT);
        INSERT INTO gr_accounts(name, invite_code, wallet_cents, created_at) VALUES('Before', 'gr-old-code', 2000, '2026-10-21T10:00:00');
        INSERT INTO gr_devices(account_id, name, fingerprint, token, created_at) VALUES(1, 'laptop', 'mac-before', 'tok-before', '2026-10-21T10:00:00');
    """)
    c.commit()
with closing(gr_server.db()) as c:
    gr_server.init_db(c)
gr_master._rate.clear()
chk(client.get("/api/me", headers=hdr("tok-before")).status_code == 200, "an account from an older database is still signed in on its laptop")
chk(client.post("/api/join", json={"invite_code": "gr-old-code", "fingerprint": "mac-before"}).get_json()["token"] == "tok-before",
    "…and its code still signs it in")
chk(client.post("/api/me/password", json={"new": PW, "email": "before@example.ie"}, headers=hdr("tok-before")).status_code == 200
    and login("before@example.ie", PW, "mac-before").status_code == 200, "…and it can move to an email and a password")

print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
