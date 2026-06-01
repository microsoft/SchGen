import re
from difflib import SequenceMatcher

_SPLIT_RE = re.compile(r"[\s_\-\/\.\(\)\[\]]+")

def _normalize_pin_text(s: str) -> str:
    """Lowercase; strip common wrappers; keep only alnum; remove common prefixes."""
    if s is None:
        return ""
    s = str(s).strip().lower()

    # common prefixes seen in KiCad libs / exports
    for pref in ("pin_", "pin", "p_", "pad_", "pad"):
        if s.startswith(pref):
            s = s[len(pref):].lstrip("_- ")
            break

    # some libs use n<name> as an alias (your code already checks this)
    # here we normalize it too, but only if it looks like a prefix not "n1" as a number
    if s.startswith("n") and len(s) >= 2 and s[1].isalpha():
        s = s[1:]

    # collapse to alnum only for robust substring comparisons
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _tokens(s: str) -> list[str]:
    """Tokenize before aggressive normalization, for PB1-PWM1 -> ['pb1','pwm1'] etc."""
    if s is None:
        return []
    s0 = str(s).strip().lower()
    parts = [p for p in _SPLIT_RE.split(s0) if p]
    # also strip common prefixes in tokens
    out = []
    for p in parts:
        if p.startswith("pin_"):
            p = p[4:]
        elif p.startswith("pin"):
            p = p[3:]
        out.append(p)
    return out


def _power_family_key(n: str) -> str | None:
    """
    Very loose grouping: if you want VCC ~ VSS ~ VDD etc to still match sometimes.
    If you DON'T want VCC matching VSS, remove/adjust this.
    """
    n = _normalize_pin_text(n)
    if not n:
        return None

    power_markers = (
        "vcc", "vdd", "vss", "vee", "gnd", "vin", "vout", "vbat", "vbatt", "avdd", "dvdd",
        "vref", "ref", "vcore", "vdda", "vssa"
    )
    for m in power_markers:
        if m in n:
            return "power"
    return None


def _pin_match_score(query: str, cand_name: str, cand_num: str | None) -> float:
    """
    Higher score is better. Designed to be tolerant:
    - exact / normalized exact
    - token exact (PB1-PWM1 -> PB1)
    - substring both ways (OUT <-> VOUT)
    - similarity ratio fallback
    - optional power-family boost
    """
    q_raw = str(query or "")
    c_raw = str(cand_name or "")

    qn = _normalize_pin_text(q_raw)
    cn = _normalize_pin_text(c_raw)
    if not qn or not cn:
        return 0.0

    # 1) strongest: exact normalized
    if qn == cn:
        return 100.0

    # 2) token match: any token equals the other normalized form
    qt = [_normalize_pin_text(t) for t in _tokens(q_raw)]
    ct = [_normalize_pin_text(t) for t in _tokens(c_raw)]
    qt = [t for t in qt if t]
    ct = [t for t in ct if t]
    if qn in ct or cn in qt:
        return 95.0

    # 3) handle "PB1-PWM1" wanting "PB1": compare first token too
    if qt and ct and (qt[0] == cn or ct[0] == qn or qt[0] == ct[0]):
        return 92.0

    # 4) substring both ways
    if qn in cn or cn in qn:
        # longer overlap => higher
        overlap = min(len(qn), len(cn)) / max(len(qn), len(cn))
        return 85.0 + 10.0 * overlap

    # 5) optional: pin number exact match
    if cand_num is not None:
        if str(cand_num).strip() == str(query).strip():
            return 80.0

    # 6) optional power-family boost (VERY loose)
    if _power_family_key(q_raw) and _power_family_key(c_raw):
        base = 70.0
    else:
        base = 0.0

    # 7) similarity ratio fallback (difflib)
    ratio = SequenceMatcher(None, qn, cn).ratio()  # 0..1
    return base + 70.0 * ratio


def find_best_pin_instance(symbol, pin_name: str, min_score: float = 75.0):
    """
    Scan all pins and return the best fuzzy match (or None if below threshold).
    Expects symbol.pin to be iterable over pins with .name and .number.
    """
    best = None
    best_score = -1.0

    for p in symbol.pin:
        # Some pin objects may not have both fields; be defensive
        p_name = getattr(p, "name", "")
        p_num = getattr(p, "number", None)

        s = _pin_match_score(pin_name, p_name, p_num)
        # also allow matching against the pin number as a "name"
        if p_num is not None:
            s = max(s, _pin_match_score(pin_name, str(p_num), p_num))

        if s > best_score:
            best_score = s
            best = p
    print(f"Pin match '{pin_name}' -> '{getattr(best, 'name', None)}' (score {best_score:.1f})")
    if best_score >= min_score:
        return best
    return None