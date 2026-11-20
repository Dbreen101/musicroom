"""
geo_map.py — normalise the messy country values in artist_profiles into canonical
countries with a centroid, for the place map (VISION §4.15).

culture.py already enriches artists with a `country` from MusicBrainz/Wikidata, but
the raw values are a mix of ISO-2 codes ("GB"), ISO-3 ("GBR"), full names
("United Kingdom"), historical/oddball values ("Roman Empire", "XW" = MusicBrainz
"worldwide") and the odd city ("Jerusalem"). This maps them all to a single
{code, name, lat, lon} so tracks cluster correctly on the map. Values we can't place
return None and are counted as "unplaced" rather than guessed — never fabricate a place.

Centroids are approximate visual centres (lat, lon) — good for a label/marker; the
true-size country SHAPES come from the equal-area world geometry on the front end.
"""

# code → (display name, lat, lon)
COUNTRY = {
    "GB": ("United Kingdom", 54.0, -2.4),
    "US": ("United States", 39.5, -98.35),
    "IE": ("Ireland", 53.2, -8.0),
    "DE": ("Germany", 51.1, 10.4),
    "FR": ("France", 46.6, 2.4),
    "NL": ("Netherlands", 52.2, 5.5),
    "BE": ("Belgium", 50.6, 4.7),
    "IT": ("Italy", 42.8, 12.6),
    "ES": ("Spain", 40.2, -3.6),
    "PT": ("Portugal", 39.6, -8.0),
    "SE": ("Sweden", 62.0, 15.0),
    "NO": ("Norway", 64.5, 11.5),
    "FI": ("Finland", 64.5, 26.0),
    "DK": ("Denmark", 56.0, 9.5),
    "IS": ("Iceland", 64.9, -18.6),
    "AT": ("Austria", 47.6, 14.1),
    "CH": ("Switzerland", 46.8, 8.2),
    "PL": ("Poland", 52.1, 19.4),
    "CZ": ("Czechia", 49.8, 15.5),
    "SK": ("Slovakia", 48.7, 19.5),
    "HU": ("Hungary", 47.2, 19.4),
    "RO": ("Romania", 45.9, 24.9),
    "BG": ("Bulgaria", 42.7, 25.3),
    "GR": ("Greece", 39.1, 22.9),
    "HR": ("Croatia", 45.1, 15.5),
    "RS": ("Serbia", 44.0, 21.0),
    "SI": ("Slovenia", 46.1, 14.8),
    "UA": ("Ukraine", 49.0, 31.4),
    "RU": ("Russia", 61.5, 90.0),
    "BY": ("Belarus", 53.7, 27.9),
    "LT": ("Lithuania", 55.2, 23.9),
    "LV": ("Latvia", 56.9, 24.9),
    "EE": ("Estonia", 58.6, 25.0),
    "TR": ("Turkey", 39.0, 35.2),
    "IL": ("Israel", 31.5, 34.9),
    "LB": ("Lebanon", 33.9, 35.9),
    "SY": ("Syria", 35.0, 38.5),
    "EG": ("Egypt", 26.8, 30.8),
    "MA": ("Morocco", 31.8, -7.1),
    "TN": ("Tunisia", 34.1, 9.6),
    "DZ": ("Algeria", 28.0, 2.6),
    "NG": ("Nigeria", 9.1, 8.7),
    "GH": ("Ghana", 7.9, -1.0),
    "ML": ("Mali", 17.6, -3.5),
    "GN": ("Guinea", 9.9, -11.0),
    "SN": ("Senegal", 14.5, -14.5),
    "CV": ("Cape Verde", 16.0, -24.0),
    "CI": ("Côte d'Ivoire", 7.5, -5.5),
    "CD": ("DR Congo", -2.9, 23.6),
    "CG": ("Congo", -0.8, 15.2),
    "AO": ("Angola", -11.2, 17.9),
    "ZA": ("South Africa", -29.0, 24.0),
    "ZW": ("Zimbabwe", -19.0, 29.8),
    "TZ": ("Tanzania", -6.4, 34.9),
    "KE": ("Kenya", 0.2, 37.9),
    "ET": ("Ethiopia", 9.1, 40.5),
    "UG": ("Uganda", 1.4, 32.3),
    "CM": ("Cameroon", 5.7, 12.7),
    "JM": ("Jamaica", 18.1, -77.3),
    "BB": ("Barbados", 13.2, -59.5),
    "TT": ("Trinidad & Tobago", 10.5, -61.3),
    "CU": ("Cuba", 21.5, -79.5),
    "HT": ("Haiti", 19.0, -72.3),
    "DO": ("Dominican Republic", 18.7, -70.2),
    "MX": ("Mexico", 23.6, -102.5),
    "BR": ("Brazil", -10.8, -52.9),
    "AR": ("Argentina", -38.4, -65.2),
    "CL": ("Chile", -35.7, -71.4),
    "CO": ("Colombia", 4.1, -73.1),
    "PE": ("Peru", -9.2, -75.0),
    "VE": ("Venezuela", 7.1, -66.1),
    "EC": ("Ecuador", -1.4, -78.2),
    "PY": ("Paraguay", -23.4, -58.4),
    "UY": ("Uruguay", -32.8, -56.0),
    "BO": ("Bolivia", -16.7, -64.7),
    "CA": ("Canada", 56.1, -106.3),
    "AU": ("Australia", -25.7, 134.5),
    "NZ": ("New Zealand", -41.5, 172.8),
    "JP": ("Japan", 36.2, 138.3),
    "CN": ("China", 35.9, 104.2),
    "KR": ("South Korea", 36.5, 127.8),
    "IN": ("India", 22.6, 79.6),
    "PK": ("Pakistan", 30.4, 69.3),
    "ID": ("Indonesia", -2.5, 118.0),
    "TH": ("Thailand", 15.1, 101.0),
    "VN": ("Vietnam", 16.2, 107.8),
    "PH": ("Philippines", 12.9, 121.8),
    "MY": ("Malaysia", 4.2, 109.4),
    "SG": ("Singapore", 1.35, 103.8),
    "TW": ("Taiwan", 23.8, 121.0),
    "IR": ("Iran", 32.4, 53.7),
    "SA": ("Saudi Arabia", 24.0, 45.1),
    "AE": ("United Arab Emirates", 24.0, 54.0),
    "LU": ("Luxembourg", 49.8, 6.1),
    "MT": ("Malta", 35.9, 14.4),
    "CY": ("Cyprus", 35.1, 33.4),
    "GE": ("Georgia", 42.3, 43.4),
    "AM": ("Armenia", 40.3, 45.0),
    "AZ": ("Azerbaijan", 40.3, 47.7),
}

# anything that maps to a code above. Keys are lowercased.
_ALIASES = {
    # ISO-3 → ISO-2 for the ones likely to appear
    "gbr": "GB", "usa": "US", "irl": "IE", "deu": "DE", "fra": "FR", "nld": "NL",
    "bel": "BE", "ita": "IT", "esp": "ES", "prt": "PT", "swe": "SE", "nor": "NO",
    "fin": "FI", "dnk": "DK", "aut": "AT", "che": "CH", "rus": "RU", "ukr": "UA",
    "can": "CA", "aus": "AU", "nzl": "NZ", "jpn": "JP", "bra": "BR", "zaf": "ZA",
    "cpv": "CV", "cod": "CD", "jam": "JM",
    # full names + variants
    "united kingdom": "GB", "great britain": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "uk": "GB",
    "united kingdom of great britain and ireland": "GB",
    "united kingdom of great britain and northern ireland": "GB",
    "united states": "US", "united states of america": "US", "america": "US",
    "ireland": "IE", "republic of ireland": "IE",
    "germany": "DE", "france": "FR", "netherlands": "NL",
    "kingdom of the netherlands": "NL", "holland": "NL",
    "belgium": "BE", "italy": "IT", "spain": "ES", "portugal": "PT",
    "sweden": "SE", "norway": "NO", "finland": "FI", "denmark": "DK",
    "iceland": "IS", "austria": "AT", "switzerland": "CH", "poland": "PL",
    "czechia": "CZ", "czech republic": "CZ", "slovakia": "SK", "hungary": "HU",
    "romania": "RO", "bulgaria": "BG", "greece": "GR", "croatia": "HR",
    "serbia": "RS", "slovenia": "SI", "ukraine": "UA", "russia": "RU",
    "russian federation": "RU", "belarus": "BY", "lithuania": "LT", "latvia": "LV",
    "estonia": "EE", "turkey": "TR", "türkiye": "TR", "israel": "IL",
    "jerusalem": "IL", "lebanon": "LB", "syria": "SY", "egypt": "EG",
    "morocco": "MA", "tunisia": "TN", "algeria": "DZ", "nigeria": "NG",
    "ghana": "GH", "mali": "ML", "guinea": "GN", "senegal": "SN",
    "cape verde": "CV", "cabo verde": "CV", "côte d'ivoire": "CI",
    "cote d'ivoire": "CI", "ivory coast": "CI",
    "democratic republic of the congo": "CD", "dr congo": "CD", "congo-kinshasa": "CD",
    "zaire": "CD", "congo": "CG", "republic of the congo": "CG", "angola": "AO",
    "south africa": "ZA", "zimbabwe": "ZW", "tanzania": "TZ", "kenya": "KE",
    "ethiopia": "ET", "uganda": "UG", "cameroon": "CM", "jamaica": "JM",
    "trinidad and tobago": "TT", "trinidad & tobago": "TT", "cuba": "CU",
    "barbados": "BB",
    "haiti": "HT", "dominican republic": "DO", "mexico": "MX", "brazil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
    "venezuela": "VE", "ecuador": "EC", "paraguay": "PY", "uruguay": "UY",
    "bolivia": "BO", "canada": "CA", "australia": "AU", "new zealand": "NZ",
    "japan": "JP", "china": "CN", "south korea": "KR", "korea": "KR",
    "india": "IN", "pakistan": "PK", "indonesia": "ID", "thailand": "TH",
    "vietnam": "VN", "viet nam": "VN", "philippines": "PH", "malaysia": "MY",
    "singapore": "SG", "taiwan": "TW", "iran": "IR", "saudi arabia": "SA",
    "united arab emirates": "AE", "luxembourg": "LU", "malta": "MT",
    "cyprus": "CY", "georgia": "GE", "armenia": "AM", "azerbaijan": "AZ",
    # historical / fuzzy — best-effort, clearly approximate
    "roman empire": "IT", "kingdom of italy": "IT", "weimar republic": "DE",
    "soviet union": "RU", "ussr": "RU", "yugoslavia": "RS",
    "east germany": "DE", "west germany": "DE",
}

# values that explicitly mean "no country" — never placed
_NON_COUNTRY = {"xw", "xe", "xc", "", "unknown", "[worldwide]", "worldwide", "various"}


def normalize(raw):
    """Return the ISO-2 code for a raw country value, or None if it can't be placed."""
    if not raw:
        return None
    s = str(raw).strip()
    low = s.lower()
    if low in _NON_COUNTRY:
        return None
    up = s.upper()
    if up in COUNTRY:                 # already an ISO-2 we know
        return up
    if low in _ALIASES:               # a name / ISO-3 / variant
        return _ALIASES[low]
    if up in _ALIASES:                # ISO-3 given uppercase
        return _ALIASES[up.lower()] if up.lower() in _ALIASES else None
    return None


def country_info(code):
    """(name, lat, lon) for an ISO-2 code, or None."""
    return COUNTRY.get(code)


def known_codes():
    return set(COUNTRY.keys())
