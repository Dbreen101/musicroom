"""
Reader mode — server-side readability extraction, stdlib only.

Fetches an article page and returns {title, byline, image_url, published, source,
body_html} where body_html is a CLEAN, re-built, allowlisted fragment (the words,
the headings, blockquotes, lists and inline images — nav/ads/cookie-bars stripped)
that the app renders in its own typography. This is the same thing Safari Reader /
Firefox Reader / Pocket / Instapaper do: reformatting an article the user already
opened, for reading. We keep the title, byline, source and a link to the original;
we don't redistribute, and we don't try to defeat paywalls.

Security: the returned body_html is built from scratch from an ALLOWLIST (tags +
attributes), every text node is escaped, every URL is absolutised + scheme-checked.
Nothing from the source markup is passed through verbatim — so it is safe to
inject into the page. No new dependencies (html.parser + re + the feeds._get
fetch helper).
"""
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import feeds

# block / inline tags we keep in the cleaned article
KEEP = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol", "li",
        "figure", "figcaption", "img", "a", "em", "strong", "b", "i", "u",
        "br", "hr", "pre", "code", "sub", "sup", "mark"}
# whole subtrees to discard
DROP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript",
        "iframe", "svg", "button", "select", "input", "textarea", "head", "link",
        "meta", "picture", "source", "video", "audio", "object", "embed", "ins",
        "label", "dialog", "template"}
VOID = {"img", "br", "hr", "meta", "link", "input", "source", "col", "area", "base", "wbr", "embed"}
# class/id substrings that mark non-article chrome
JUNK = re.compile(
    r"(nav|navbar|menu|share|social|comment|promo|advert|sponsor|newsletter|related|"
    r"recirc|sidebar|cookie|paywall|subscri|footer|masthead|breadcrumb|byline|"
    r"author[-_]?bio|metadata|pagination|widget|popup|modal|banner|hidden|"
    r"visually[-_]?hidden|sr[-_]?only|skip[-_]?link|disqus|outbrain|taboola)", re.I)
# class/id substrings that mark the real article body (scoring bonus)
CONTENT = re.compile(
    r"(article[-_]?(body|content|text)|entry[-_]?content|post[-_]?(content|body)|"
    r"story[-_]?body|rich[-_]?text|prose|content[-_]?body|c-content|main[-_]?content)", re.I)


MAX_DEPTH = 200   # cap nesting so the recursive prune/serialize can't blow the stack


class _Node:
    __slots__ = ("tag", "attrs", "children", "text", "parent", "depth")

    def __init__(self, tag, attrs=None, parent=None, depth=0):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.text = ""
        self.parent = parent
        self.depth = depth


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, attrs, self.cur, self.cur.depth + 1)
        self.cur.children.append(n)
        # past the depth cap, keep appending but stop descending → the tree stays
        # shallow (pathologically deep pages flatten instead of overflowing).
        if tag not in VOID and n.depth < MAX_DEPTH:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        if data.strip():
            t = _Node("#text", parent=self.cur)
            t.text = data
            self.cur.children.append(t)


def _cls(node):
    return (node.attrs.get("class", "") or "") + " " + (node.attrs.get("id", "") or "")


def _prune(node):
    """Drop DROP tags + JUNK-class subtrees in place."""
    kept = []
    for c in node.children:
        if c.tag == "#text":
            kept.append(c); continue
        if c.tag in DROP:
            continue
        if c.tag not in ("#text",) and JUNK.search(_cls(c)):
            continue
        _prune(c)
        kept.append(c)
    node.children = kept


def _p_text_len(node):
    """Total <p> text length under a node — the readability density signal."""
    total = 0
    for c in node.children:
        if c.tag == "p":
            total += len(_all_text(c))
        else:
            total += _p_text_len(c)
    return total


def _all_text(node):
    if node.tag == "#text":
        return node.text
    return "".join(_all_text(c) for c in node.children)


def _best_container(root):
    """Pick the node with the most paragraph text (bonus for an article-ish class)."""
    best, best_score = root, -1
    stack = [root]
    while stack:
        n = stack.pop()
        if n.tag in ("div", "article", "section", "main", "#root"):
            score = _p_text_len(n)
            if CONTENT.search(_cls(n)) or n.tag == "article":
                score = int(score * 1.6)
            if score > best_score:
                best, best_score = n, score
        stack.extend(c for c in n.children if c.tag != "#text")
    return best


def _safe_url(base, href, schemes=("http", "https")):
    u = feeds._abs(base, (href or "").strip())
    try:
        if urlsplit(u).scheme.lower() in schemes:
            return u
    except Exception:
        pass
    return ""


def _serialize(node, base, out):
    """Emit an allowlisted, escaped, absolutised HTML fragment."""
    for c in node.children:
        if c.tag == "#text":
            out.append(escape(c.text))
        elif c.tag == "img":
            src = _safe_url(base, c.attrs.get("src") or c.attrs.get("data-src", ""))
            if src:
                alt = escape(c.attrs.get("alt", "") or "")
                out.append(f'<img src="{escape(src)}" alt="{alt}" loading="lazy">')
        elif c.tag == "a":
            href = _safe_url(base, c.attrs.get("href", ""))
            inner = []
            _serialize(c, base, inner)
            body = "".join(inner).strip()
            if body:
                if href:
                    out.append(f'<a href="{escape(href)}" target="_blank" rel="noopener noreferrer">{body}</a>')
                else:
                    out.append(body)
        elif c.tag in ("br", "hr"):
            out.append(f"<{c.tag}>")
        elif c.tag in KEEP:
            inner = []
            _serialize(c, base, inner)
            body = "".join(inner).strip()
            if body or c.tag in ("img",):
                out.append(f"<{c.tag}>{body}</{c.tag}>")
        else:                                   # unknown tag → unwrap (keep its children)
            _serialize(c, base, out)


# ── metadata (OpenGraph + JSON-LD Article + <title>) ─────────────────────────
_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_META_KEY = re.compile(r"""(?:property|name)\s*=\s*["']([^"']+)["']""", re.I)
_META_CONTENT = re.compile(r"""content\s*=\s*["']([^"']*)["']""", re.I)


def _meta(html, *names):
    """First <meta> matching any of `names` (in priority order), content value.
    Splits into individual tags FIRST so the per-tag regexes run on bounded
    input — no catastrophic backtracking on a malformed/unterminated tag."""
    tags = _META_TAG.findall(html)
    for nm in names:
        nl = nm.lower()
        for tag in tags:
            k = _META_KEY.search(tag)
            if k and k.group(1).strip().lower() == nl:
                c = _META_CONTENT.search(tag)
                if c:
                    return _unescape(c.group(1).strip())
    return ""


def _jsonld(html):
    """First Article-ish JSON-LD block → {headline, author, image, datePublished}."""
    import json
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                         html, re.I | re.S):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else
                    (data.get("@graph") if isinstance(data, dict) and isinstance(data.get("@graph"), list) else [data])):
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type") or ""
            t = " ".join(t) if isinstance(t, list) else str(t)
            if "Article" in t or "BlogPosting" in t or "NewsArticle" in t:
                au = obj.get("author")
                if isinstance(au, list):
                    au = au[0] if au else None
                author = (au.get("name") if isinstance(au, dict) else au) or ""
                img = obj.get("image")
                if isinstance(img, dict):
                    img = img.get("url", "")
                elif isinstance(img, list):
                    img = (img[0].get("url") if isinstance(img[0], dict) else img[0]) if img else ""
                # coerce to str — JSON-LD values are sometimes numbers/objects
                def _s(v):
                    return v if isinstance(v, str) else (str(v) if v not in (None, "", [], {}) else "")
                return {"headline": _s(obj.get("headline") or obj.get("name")),
                        "author": _s(author), "image": _s(img),
                        "published": _s(obj.get("datePublished"))}
    return {}


def _unescape(s):
    from html import unescape
    return unescape(s)


def extract(url):
    """Fetch + extract. Returns {ok, url, title, byline, image_url, published,
    source, body_html} or {ok:False, url, error}."""
    try:
        raw = feeds._get(url, timeout=15)
        if isinstance(raw, (bytes, bytearray)) and len(raw) > 5_000_000:   # cap a runaway page
            raw = raw[:5_000_000]
        html = raw.decode("utf-8", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    except Exception as e:
        # A hard 4xx (bot-block, gone, forbidden) will NEVER succeed on retry —
        # it must cache as a permanent miss, or the item keeps offering a
        # reading view it can't deliver, forever. Only genuinely temporary
        # failures (network blips, 5xx, 429) stay transient.
        import urllib.error
        if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429:
            return {"ok": False, "url": url,
                    "error": "this site doesn’t let the reading view in — it opens in the browser instead"}
        return {"ok": False, "url": url, "transient": True, "error": "couldn’t fetch the page"}

    ld = _jsonld(html)
    title = _meta(html, "og:title", "twitter:title") or ld.get("headline") or ""
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = _unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""
    image = _meta(html, "og:image", "twitter:image") or ld.get("image") or ""
    byline = ld.get("author") or _meta(html, "author", "article:author", "twitter:creator") or ""
    source = _meta(html, "og:site_name") or urlsplit(url).hostname or ""
    published = _meta(html, "article:published_time") or ld.get("published") or ""

    try:
        tree = _Tree()
        tree.feed(html)
        _prune(tree.root)
        container = _best_container(tree.root)
        parts = []
        _serialize(container, url, parts)
        body = "".join(parts)
    except Exception:
        body = ""

    # too thin → tell the caller to fall back to "open in browser"
    if len(re.sub(r"<[^>]+>", "", body)) < 200:
        return {"ok": False, "url": url, "title": title, "image_url": image,
                "error": "couldn’t pull a clean reading view from this page"}

    if image:
        image = _safe_url(url, image)
    return {"ok": True, "url": url, "title": title.strip(), "byline": (byline or "").strip(),
            "image_url": image, "published": (published or "")[:10], "source": source,
            "body_html": body}
