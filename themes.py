"""Themes — the app's skin as a small set of colour tokens.

A theme is {"id", "name", "scheme": "dark"|"light", "vars": {token: value}}.
The tokens are the CSS custom properties the stylesheets already read
(style.css / explore-theme.css / gr.css / the room's chrome), so a theme
restyles every page by redefining them on :root — no page knows it was
themed. Built-in themes live here; people's own themes are stored in
settings (ui_themes_custom) and arrive as JSON files, like a skin.

How to make one: export the current theme from the theme menu, change the
values, import it back. Any token can be left out — the built-in dark
values stand in. See docs/THEMES.md.
"""

TOKENS = [
    # the page (style.css / explore-theme.css)
    "bg", "bg-floor", "surface", "surface2", "border", "border2", "text", "muted", "muted2",
    "accent", "accent-dim", "gold", "gold-soft", "well", "oxblood", "lapis", "ochre",
    "danger", "warning", "red",
    # surfaces the desk theme used to hard-code
    "sheet", "nav-bg", "pill-ink", "shadow",
    # the room's chrome (room3d.html)
    "ink",
    # the Green Room pages (gr.css)
    "gr-bg", "gr-surface", "gr-line", "gr-ink", "gr-muted", "gr-faint", "gr-accent", "gr-accent-ink",
    # the Map in Explore, when it is wearing the skin that follows the app (explore_map.js). A theme that
    # leaves these out gets a map worked out from its page and its text; the built-in two leave them out.
    "map-sea", "map-land", "map-line", "map-text",
]

DARK = {
    "id": "dark", "name": "Ink", "scheme": "dark",
    "vars": {
        # the working document, turned over: ink paper, paper ink (the deck's dark slides)
        "bg": "#161513", "bg-floor": "#111010", "surface": "#1c1b19", "surface2": "#232220",
        "border": "rgba(242,239,232,.18)", "border2": "rgba(242,239,232,.32)",
        "text": "#f2efe8", "muted": "#9b968a", "muted2": "#6e6a61",
        "accent": "#f2efe8", "accent-dim": "rgba(242,239,232,.08)", "gold": "#f2efe8",
        "gold-soft": "#c9c4b8", "well": "#f2efe8", "oxblood": "#e8554a", "lapis": "#8fa3c9",
        "ochre": "#c9c4b8", "danger": "#e8554a", "warning": "#e8554a", "red": "#e8554a",
        "sheet": "#161513", "nav-bg": "rgba(22,21,19,.94)", "pill-ink": "#161513",
        "shadow": "rgba(0,0,0,.5)",
        "ink": "#f2efe8",
        "gr-bg": "#161513", "gr-surface": "rgba(242,239,232,.04)", "gr-line": "rgba(242,239,232,.18)",
        "gr-ink": "#f2efe8", "gr-muted": "#9b968a", "gr-faint": "#6e6a61",
        "gr-accent": "#f2efe8", "gr-accent-ink": "#161513",
    },
}

LIGHT = {
    "id": "light", "name": "Paper", "scheme": "light",
    "vars": {
        # the working document: paper, ink, a muted grey, hairlines, one red
        "bg": "#f2efe8", "bg-floor": "#e9e5db", "surface": "#f7f5f0", "surface2": "#e9e5db",
        "border": "#c8c3b6", "border2": "#a9a497",
        "text": "#161513", "muted": "#6e6a61", "muted2": "#837e72",
        "accent": "#161513", "accent-dim": "rgba(22,21,19,.06)", "gold": "#161513",
        "gold-soft": "#4a4842", "well": "#161513", "oxblood": "#c9412f", "lapis": "#293e70",
        "ochre": "#4a4842", "danger": "#c9412f", "warning": "#c9412f", "red": "#c9412f",
        "sheet": "#f2efe8", "nav-bg": "rgba(242,239,232,.94)", "pill-ink": "#f2efe8",
        "shadow": "rgba(22,21,19,.14)",
        "ink": "#161513",
        "gr-bg": "#f2efe8", "gr-surface": "rgba(22,21,19,.035)", "gr-line": "#c8c3b6",
        "gr-ink": "#161513", "gr-muted": "#6e6a61", "gr-faint": "#837e72",
        "gr-accent": "#161513", "gr-accent-ink": "#f2efe8",
    },
}

BUILT_IN = [DARK, LIGHT]


def css_for(theme):
    """The <style> text that applies a theme. :root:root out-specifies the
    stylesheets' own :root blocks wherever this lands in the head."""
    if not theme or theme.get("id") == "dark":
        return ""     # dark is what the stylesheets already say
    base = dict(DARK["vars"])
    base.update(theme.get("vars") or {})
    body = "".join(f"--{k}:{v};" for k, v in base.items() if v)
    scheme = theme.get("scheme") or "dark"
    # on :root AND body: pages that set their own tokens on <body> (Explore's
    # immersive mode) still follow the theme
    return f"<style id=\"mr-theme\">:root:root,:root:root body{{{body}color-scheme:{scheme};}}</style>"


def validate(obj):
    """A theme file people import: {name, scheme?, vars{}}. Returns (theme, error)."""
    if not isinstance(obj, dict):
        return None, "a theme is a JSON object"
    name = "".join(c for c in str(obj.get("name") or "") if c not in "<>\"'&`").strip()[:60]
    if not name:
        return None, "the theme needs a name"
    raw = obj.get("vars")
    if not isinstance(raw, dict) or not raw:
        return None, "the theme needs a 'vars' object of colours"
    vars_ = {}
    for k, v in raw.items():
        k = str(k).strip().lstrip("-")
        if k not in TOKENS:
            continue
        v = str(v).strip()
        if not v or len(v) > 80 or any(c in v for c in "<>{};"):
            continue
        vars_[k] = v
    if not vars_:
        return None, f"none of the colours were ones I know — the tokens are: {', '.join(TOKENS)}"
    import re
    import mr_text
    ident = mr_text.slug(name, "theme")
    scheme = obj.get("scheme") if obj.get("scheme") in ("light", "dark") else None
    if not scheme:
        # guess from the background: light if it's bright
        bg = vars_.get("bg", "")
        m = re.match(r"#([0-9a-f]{6})$", bg.lower())
        if m:
            r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
            scheme = "light" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "dark"
        else:
            scheme = "dark"
    return {"id": "custom-" + ident, "name": name, "scheme": scheme, "vars": vars_,
            "author": str(obj.get("author") or "")[:80]}, None
