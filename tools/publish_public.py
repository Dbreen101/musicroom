#!/usr/bin/env python3
"""
tools/publish_public.py — make the PUBLIC copy of the Music Room's code.

David, 2026-11-20: the code goes open (AGPL-3.0) in a new, clean GitHub repo;
this private repo stays as it is, with the business documents, the thesis, the
notes for Claude and the whole history. This tool copies the code across —
everything git tracks here EXCEPT the private things listed in PRIVATE — into a
local clone of the public repo, and makes one commit there.

    python3 tools/publish_public.py --check            what would go, what is left out, any warnings
    python3 tools/publish_public.py -m "what changed"  copy it across and commit (not pushed)
    python3 tools/publish_public.py -m "…" --push      …and push to GitHub

It refuses to run when the public repo has changes this copy hasn't taken in
yet (a pull request David merged on GitHub): take those in first with
tools/take_public.sh, so publishing never undoes someone's work.

The public repo's clone: MR_PUBLIC_REPO (default ~/Projects/musicroom).
"""
import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PUBLIC = Path(os.environ.get("MR_PUBLIC_REPO", Path.home() / "Projects" / "musicroom"))

# never published: business, the residency's private papers, notes for Claude, tester paperwork,
# pictures of David's own library, one-off scripts for his own machine
PRIVATE = [
    "CLAUDE.md", "BUSINESS.md", "HANDOFF.md", "HANDOFF_PROMPT.md", "TODO.md", "VISION.md",
    "P1_GAP_AUDIT.md", "P1_JULY7_PLAN.md", "P1_MUST_HAVES.md",
    "research/*", ".claude/*",
    "docs/greenroom-*", "docs/interview-*", "docs/CONTEXT_FOR_PRESENTATION*", "docs/PRICING_GR.md",
    "docs/GR1_PLAN.md", "docs/P1_TESTERS.md", "docs/DATA_TRACKING.md", "docs/OMO_BRIEF.md", "docs/SERVER_SCALING*", "tools/make_server_scaling.py",
    "docs/*.pages", "docs/*.pdf", "docs/reference/*",
    "tools/google_sheet_endpoint.gs", "tools/pull_feedback.py", "tools/ingest_feedback.py", "tools/preflight.sh",
    "telemetry_server/*", "native/Tester guide.txt",
    "rekey_all.py", "remove_ableton_tracks.py", "reset_itunes_artwork.py", "generate_research_library.py",
    "make_usb.py", "tools/publish_never.txt", "docs/commit-map-*", "tools/setup_gr_library.sh",
]
# a published file must not hold any of these (it stops, and says where). The words that are
# private in themselves (an email address, people's names, this Mac's home folder) are kept in
# tools/publish_never.txt — one "pattern<TAB>what it is" a line — which is itself never published.
NEVER = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"), "a secret key"),
    (re.compile(r"script\.google\.com/macros/s/"), "a private web address"),
]
_private_words = HERE / "tools" / "publish_never.txt"
if _private_words.is_file():
    for _line in _private_words.read_text(encoding="utf-8").splitlines():
        if _line.strip() and not _line.startswith("#") and "\t" in _line:
            _pat, _what = _line.split("\t", 1)
            NEVER.append((re.compile(_pat), _what.strip()))
TEXT = {".py", ".js", ".css", ".html", ".md", ".txt", ".json", ".sh", ".command", ".spec", ".svg", ".gs", ".yml", ".yaml", ".toml", ""}


def git(*a, cwd=HERE, check=True):
    return subprocess.run(["git", *a], cwd=cwd, check=check, capture_output=True, text=True).stdout


def account_email():
    """(owner, address): the GitHub account that owns the public repo, and that account's own
    private commit address (id+login@users.noreply.github.com) — ASKED OF GITHUB, never typed
    in or guessed from a name. A guessed address once put a stranger's account on every commit
    (a name-only noreply address belongs to whoever owns that name). (None, why) if it can't be told."""
    url = git("remote", "get-url", "origin", cwd=PUBLIC, check=False).strip()
    m = re.search(r"github\.com[:/]([^/]+)/", url)
    if not m:
        return None, f"can't tell the public repo's owner from its address ({url or 'none'})"
    owner = m.group(1)
    r = subprocess.run(["gh", "api", "user", "--jq", '"\\(.id)+\\(.login)"'],
                       capture_output=True, text=True)
    who = r.stdout.strip()
    if r.returncode != 0 or "+" not in who:
        return None, "GitHub didn't say which account this Mac is signed in as (gh auth status)"
    login = who.split("+", 1)[1]
    if login.lower() != owner.lower():
        return None, f"this Mac is signed in to GitHub as {login}, but the public repo belongs to {owner}"
    return owner, f"{who}@users.noreply.github.com"


def author_name():
    """The name that goes on every commit: the one HE gave (git config musicroom.authorname in
    this repo) — never taken from the Mac's user name or a login. '' if it was never said."""
    return git("config", "--get", "musicroom.authorname", cwd=HERE, check=False).strip()


def identity_problems(*repos):
    """Every repo given must commit as the owner's own account and under his own name, and nothing else."""
    owner, address = account_email()
    if not owner:
        return [address]
    out = []
    name = author_name()
    if not name:
        out.append("no name is set for commits.\n"
                   f"      Fix:  git -C '{HERE}' config musicroom.authorname 'Your Name'")
    for repo in repos:
        mine = git("config", "--get", "user.email", cwd=repo, check=False).strip()
        if mine != address:
            out.append(f"{repo} commits as <{mine or 'nobody'}>, not your GitHub account's <{address}>.\n"
                       f"      Fix:  git -C '{repo}' config user.email '{address}'")
        named = git("config", "--get", "user.name", cwd=repo, check=False).strip()
        if name and named != name:
            out.append(f"{repo} commits under the name “{named or 'nobody'}”, not “{name}”.\n"
                       f"      Fix:  git -C '{repo}' config user.name '{name}'")
    return out


def private(path):
    return any(fnmatch.fnmatch(path, pat) for pat in PRIVATE)


def chosen():
    files = [f for f in git("ls-files", "-z").split("\0") if f]
    keep = [f for f in files if not private(f) and (HERE / f).is_file()]
    left = [f for f in files if private(f)]
    return keep, left


def scan(files):
    found = []
    for f in files:
        p = HERE / f
        if p.suffix.lower() not in TEXT or p.stat().st_size > 3_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for rx, what in NEVER:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                found.append(f"{f}:{line}: {what}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-m", "--message")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--check-identity", action="store_true",
                    help="only check that both repos commit as your own GitHub account")
    a = ap.parse_args()

    if a.check_identity:
        wrong = identity_problems(HERE, PUBLIC)
        for w in wrong:
            print("STOP — " + w)
        return 1 if wrong else 0

    keep, left = chosen()
    problems = scan(keep)
    if a.check or not a.message:
        print(f"{len(keep)} files would be published; {len(left)} stay private:")
        for f in left:
            print("   private  " + f)
        if problems:
            print("\nSTOP — these would be published and shouldn't be:")
            for p in problems:
                print("   " + p)
        else:
            print("\nNothing private found in what would be published.")
        return 1 if problems else 0
    if problems:
        print("Not published — these shouldn't go out:\n   " + "\n   ".join(problems))
        return 1
    if not (PUBLIC / ".git").is_dir():
        print(f"No clone of the public repo at {PUBLIC} (set MR_PUBLIC_REPO).")
        return 1
    if git("status", "--porcelain", cwd=PUBLIC).strip():
        print(f"The public clone at {PUBLIC} has changes of its own. Commit or clear them first.")
        return 1
    wrong = identity_problems(PUBLIC)
    if wrong:
        print("Not published — " + "\n".join(wrong))
        return 1
    # has the public repo moved on since this copy last published? (a merged pull request)
    git("fetch", "--quiet", "origin", cwd=PUBLIC, check=False)
    last = git("config", "--get", "musicroom.publichead", check=False).strip()
    remote = git("rev-parse", "--verify", "-q", "origin/main", cwd=PUBLIC, check=False).strip()
    if last and remote and remote != last:
        print("The public repo has changes this copy hasn't taken in (a merged pull request?).\n"
              "Take them in first:  tools/take_public.sh <pull request number>   (or: tools/take_public.sh --sync)")
        return 1
    if remote:
        git("checkout", "--quiet", "main", cwd=PUBLIC, check=False)
        git("reset", "--quiet", "--hard", "origin/main", cwd=PUBLIC)

    # the public tree becomes exactly what is chosen here
    for item in PUBLIC.iterdir():
        if item.name == ".git":
            continue
        shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
    for f in keep:
        dst = PUBLIC / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / f, dst)
    git("add", "-A", cwd=PUBLIC)                      # (the public clone holds nothing but what was chosen)
    if not git("status", "--porcelain", cwd=PUBLIC).strip():
        print("Nothing has changed since the last publish.")
        return 0
    src = git("rev-parse", "--short", "HEAD").strip()
    git("commit", "--quiet", "-m", f"{a.message}\n\n(published from the working copy at {src})", cwd=PUBLIC)
    head = git("rev-parse", "HEAD", cwd=PUBLIC).strip()
    print(f"Committed in {PUBLIC}: {git('log', '--oneline', '-1', cwd=PUBLIC).strip()}")
    # and the commit itself, before anything leaves this Mac
    _, address = account_email()
    made = set(git("log", "-1", "--format=%ae%n%ce", cwd=PUBLIC).split())
    names = set(git("log", "-1", "--format=%an%n%cn", cwd=PUBLIC).splitlines())
    if made != {address} or names != {author_name()}:
        git("reset", "--quiet", "--soft", "HEAD~1", cwd=PUBLIC, check=False)
        print(f"Not published — the commit was made as {sorted(names)} {sorted(made)}, "
              f"not {author_name()} <{address}>. It was undone.")
        return 1
    if a.push:
        r = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PUBLIC, capture_output=True, text=True)
        if r.returncode != 0:
            print("The push didn't go:\n" + r.stderr)
            return 1
        git("config", "musicroom.publichead", head)
        print("Pushed to GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
