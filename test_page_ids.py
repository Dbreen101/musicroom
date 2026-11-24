"""No page gives two things the same id. (On 2026-11-24 a new filter on Explore was given the id
of the panel that shows a music room: every click on a room lit the filter and the room never
appeared.) Jinja's either/or branches may repeat an id — only one of them reaches the page — so
those are counted per branch. Run:  ./venv/bin/python test_page_ids.py"""
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

ID = re.compile(r'\bid="([A-Za-z0-9_-]+)"')
BRANCH = re.compile(r"{%-?\s*(if|elif|else|endif)\b[^%]*%}")

def doubles(text):
    """ids written twice where both can reach the page at once (not in sibling if/else branches)."""
    seen, out = collections.defaultdict(set), set()
    path, n = [0], 0                     # which branch of which if we are in
    pos = 0
    for m in list(BRANCH.finditer(text)) + [None]:
        chunk = text[pos:m.start()] if m else text[pos:]
        for i in ID.findall(chunk):
            here = tuple(path)
            # a clash unless the two sit in different branches of the same if
            for other in seen[i]:
                k = 0
                while k < min(len(here), len(other)) and here[k] == other[k]:
                    k += 1
                same_if = k < min(len(here), len(other)) and here[k][0] == other[k][0] and here[k][1] != other[k][1]
                if not same_if:
                    out.add(i)
            seen[i].add(here)
        if not m:
            break
        pos = m.end()
        word = m.group(1)
        if word == "if":
            n += 1; path.append((n, 0))
        elif word in ("elif", "else") and len(path) > 1:
            path[-1] = (path[-1][0], path[-1][1] + 1)
        elif word == "endif" and len(path) > 1:
            path.pop()
    return sorted(out)

chk(doubles('<a id="x"></a><b id="x"></b>') == ["x"], "the check catches an id written twice")
chk(doubles('{% if a %}<a id="x"></a>{% else %}<b id="x"></b>{% endif %}') == [], "…and lets an either/or pair through")
for name in ("explore3d.html", "public_room.html", "my_room.html", "login.html", "master.html", "intro.html", "settings.html"):
    d = doubles((ROOT / "templates" / name).read_text(encoding="utf-8"))
    chk(not d, f"{name}: no id is used twice" + (f" — {', '.join(d)}" if d else ""))

print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
