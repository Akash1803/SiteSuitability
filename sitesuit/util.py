"""Small shared rules (kept pure so they are unit-tested)."""
import re

ACRE_M2 = 4046.8564224
SQFT_PER_M2 = 10.7639
HA_TO_ACRE = 2.4710538
GOVT = "அரசு"          # A-register government_priority value for government land


def utm_epsg(lon):
    """Tamil Nadu spans UTM 43N (west of 78E) and 44N."""
    return 32643 if lon < 78.0 else 32644


def _code(x, n):
    s = str(x).strip()
    s = s[:-2] if s.endswith(".0") else s
    return s.zfill(n) if s.isdigit() else s.zfill(n)


def vcode(d, t, v):
    """'37_12_063'; village codes can carry a letter ('16A')"""
    return f"{_code(d, 2)}_{_code(t, 2)}_{_code(v, 3)}"


def split_vcode(vc):
    """-> (district int, taluk int, village int or text) for portal queries"""
    d, t, v = vc.split("_")
    return int(d), int(t), (int(v) if v.isdigit() else v)


def safe_sub(v):
    """Subdivision text as typed: only a trailing '.0' of a true number is dropped ('2E4' stays '2E4')."""
    s = "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s if s not in ("", "nan", "None") else "-"


def child_of(child, parent):
    """'1A2' is a child of '1A' and of '1'; '10' is NOT a child of '1' (a number is never cut in half)."""
    if child == parent or parent in ("", "-") or child in ("", "-") or not child.startswith(parent):
        return False
    return not (parent[-1].isdigit() and child[len(parent)].isdigit())


def survey_sort_key(s):
    m = re.match(r"(\d+)(.*)", str(s))
    return (int(m.group(1)), m.group(2)) if m else (10 ** 9, str(s))


def norm_name(s):
    """Village-name key for matching TNReginet / revenue names: lower case letters only, common spelling variants folded."""
    s = re.sub(r"[^a-z]", "", str(s).lower())
    for a, b in (("ee", "i"), ("oo", "u"), ("th", "t"), ("dh", "d"), ("kk", "k"), ("pp", "p"), ("tt", "t"), ("zh", "l"), ("aa", "a"), ("v", "w")):
        s = s.replace(a, b)
    return s


def glv_pick(listed, record_m2, govt, layout_max_m2=500):
    """Rate for a subdivision that has no GLV entry of its own.
    listed: list of (rate, unit, classification, date) for the survey's entries (unit 'Acre' or 'Square Feet').
    Returns (match_text, rate, unit, classification, date) or None when the survey has nothing usable."""
    if govt:
        return ("Govt / poramboke land - value 0 (as TNReginet quotes for govt land)", 0.0, "Acre", "Govt. Others", "")
    sq = sorted([x for x in listed if x[1] == "Square Feet" and x[0] > 0], key=lambda x: x[0])
    ac = sorted([x for x in listed if x[1] == "Acre" and x[0] > 0], key=lambda x: x[0])
    if sq and (not ac or record_m2 <= layout_max_m2):
        r = sq[0]
        return ("Layout plot - lowest residential rate listed in the survey applied (subdivision not listed)", r[0], "Square Feet", r[2], r[3])
    if ac:
        r = ac[0]
        return ("Survey rate - lowest acre rate listed in the survey applied (subdivision not listed)", r[0], "Acre", r[2], r[3])
    return None
