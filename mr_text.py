"""Names as plain letters — for making addresses, and for comparing, searching and sorting.

An accent comes off and its letter STAYS:

    Daithí → daithi      Seán Ó Briain → sean o briain      Róisín → roisin
    Björk  → bjork       Søren → soren     Łukasz → lukasz    Straße → strasse

Until 2026-11-21 an accented letter was simply thrown away wherever a name was made into an
address or compared: Róisín Murphy's room was "r-is-n-murphy", Seán's "se-n", a name that
began with Ó sorted after Z, and a search for "roisin" found nothing. Everything that turns a
name into plain letters goes through here now (the rooms server and the app both).
"""
import re
import unicodedata

# letters that are their own letter (no accent to take off) but have a plain spelling
_LETTERS = str.maketrans({
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ð": "d", "þ": "th",
    "ł": "l", "ı": "i", "ħ": "h", "ŋ": "n", "ĸ": "k", "ſ": "s",
})


def fold(text) -> str:
    """Lower case, accents off, the letters kept. Everything else is left as it is."""
    s = str(text or "")
    if s.isascii():
        return s.lower()
    s = unicodedata.normalize("NFKD", s.lower().translate(_LETTERS))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def words(text) -> str:
    """fold(), with anything that is not a letter or a digit (in any alphabet) as one space —
    for comparing two names or titles."""
    return re.sub(r"[\W_]+", " ", fold(text)).strip()


def squeeze(text) -> str:
    """words() with no spaces at all — 'the same but for spacing and punctuation'."""
    return words(text).replace(" ", "")


def slug(text, empty="room") -> str:
    """A name as an address: a–z, 0–9 and hyphens. A name with no Latin letters or digits at
    all has no such address — `empty` stands in, and its owner can set their own."""
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-") or empty


def holds(hay, query) -> bool:
    """Does `hay` hold every word of `query`, in any order, whatever the accents?"""
    h = fold(hay)
    return all(w in h for w in fold(query).split())

