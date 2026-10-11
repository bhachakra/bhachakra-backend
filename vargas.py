"""
Bhachakra varga (divisional chart) module.

Computes the sign placement of a D1 (Rasi) position within any of the 16
classical Shodashavarga divisional charts (D1-D60). Each varga divides
every 30-degree zodiac sign into N smaller parts and maps each part to a
resulting sign via a fixed classical rule.

CONFIDENCE NOTE (read before trusting a varga for real decisions):
The rules below were checked in two tiers:

  VERIFIED this session against jagannathhora.com's divisional-chart guides
  (cross-checked against independent recollection first, then confirmed):
  D1, D2, D3, D9, D12, D16, D20, D24, D30.

  STANDARD-CONVENTION, not independently re-verified this session:
  D4, D7, D10, D27, D40, D45, D60. These follow the same well-documented
  odd/even or movable/fixed/dual patterns confirmed above, and are widely
  consistent across classical software (Jagannatha Hora, Parashara's Light,
  etc.), but treat them as a documented default rather than settled fact -
  the same posture aspects.py already takes with the Rahu/Ketu drishti
  convention. If a specific varga result surprises you, cross-check that
  one chart against another source before relying on it.

D30 (Trimsamsa) resolves each of the five planetary rulers to whichever of
that planet's two own signs matches the D1 sign's odd/even parity (e.g.
Mars -> Aries for an odd D1 sign, Mars -> Scorpio for an even one). This
is the standard convention but the source page only spelled out the
degree ranges and rulers explicitly, not this sign-resolution step.

"sign_degree" returned for a varga is NOT a physically meaningful degree
the way it is in D1 - it's the planet's proportional position within its
divisional part, rescaled to 0-30, purely so the existing chart/table UI
(which expects a 0-30 degree per planet) has something sensible to show
and so multiple planets sharing a division still sort in the right order.
"""
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

MOVABLE = {0, 3, 6, 9}    # Aries, Cancer, Libra, Capricorn (0-indexed)
FIXED = {1, 4, 7, 10}     # Taurus, Leo, Scorpio, Aquarius
DUAL = {2, 5, 8, 11}      # Gemini, Virgo, Sagittarius, Pisces
ODD = {0, 2, 4, 6, 8, 10}   # Aries, Gemini, Leo, Libra, Sagittarius, Aquarius
EVEN = {1, 3, 5, 7, 9, 11}  # Taurus, Cancer, Virgo, Scorpio, Capricorn, Pisces
FIRE = {0, 4, 8}
EARTH = {1, 5, 9}
AIR = {2, 6, 10}
WATER = {3, 7, 11}


@dataclass
class VargaResult:
    sign: int          # 1-indexed, 1 = Aries
    sign_degree: float  # 0-30, proportional position within the division (see module docstring)


def _element_category(sign0: int) -> str:
    if sign0 in MOVABLE:
        return "movable"
    if sign0 in FIXED:
        return "fixed"
    return "dual"


# --- Equal-division varga start-sign rules (each returns the 0-indexed
# resulting sign directly, given the D1 sign (0-indexed) and which part
# (0-indexed) the position falls into) ---

def _navamsa_sign(sign0: int, part: int) -> int:
    # VERIFIED. Movable: start from itself. Fixed: 9th from itself. Dual: 5th from itself.
    cat = _element_category(sign0)
    base = {"movable": sign0, "fixed": (sign0 + 8) % 12, "dual": (sign0 + 4) % 12}[cat]
    return (base + part) % 12


def _drekkana_sign(sign0: int, part: int) -> int:
    # VERIFIED. 1st part = same sign, 2nd = 5th from it, 3rd = 9th from it (offset 4 per part).
    return (sign0 + part * 4) % 12


def _chaturthamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION (not re-verified this session). Kendra (1-4-7-10) pattern
    # from the sign itself, offset 3 signs per part.
    return (sign0 + part * 3) % 12


def _saptamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Odd sign: start from itself. Even sign: start from the 7th from it.
    base = sign0 if sign0 in ODD else (sign0 + 6) % 12
    return (base + part) % 12


def _dasamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Odd sign: start from itself. Even sign: start from the 9th from it.
    base = sign0 if sign0 in ODD else (sign0 + 8) % 12
    return (base + part) % 12


def _dwadasamsa_sign(sign0: int, part: int) -> int:
    # VERIFIED. 12 consecutive signs starting from the sign itself, no odd/even distinction.
    return (sign0 + part) % 12


def _shodasamsa_sign(sign0: int, part: int) -> int:
    # VERIFIED. Movable start Aries, fixed start Leo, dual start Sagittarius.
    cat = _element_category(sign0)
    base = {"movable": 0, "fixed": 4, "dual": 8}[cat]
    return (base + part) % 12


def _vimsamsa_sign(sign0: int, part: int) -> int:
    # VERIFIED. Movable start Aries, fixed start Sagittarius, dual start Leo.
    cat = _element_category(sign0)
    base = {"movable": 0, "fixed": 8, "dual": 4}[cat]
    return (base + part) % 12


def _chaturvimsamsa_sign(sign0: int, part: int) -> int:
    # VERIFIED. Odd sign start Leo, even sign start Cancer.
    base = 4 if sign0 in ODD else 3
    return (base + part) % 12


def _bhamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Fire start Aries, earth start Cancer, air start Libra, water start Capricorn.
    if sign0 in FIRE:
        base = 0
    elif sign0 in EARTH:
        base = 3
    elif sign0 in AIR:
        base = 6
    else:
        base = 9
    return (base + part) % 12


def _khavedamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Odd sign start Aries, even sign start Libra.
    base = 0 if sign0 in ODD else 6
    return (base + part) % 12


def _akshavedamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Movable start Aries, fixed start Leo, dual start Sagittarius
    # (same triplicity pattern as D16 - some sources instead use D20's movable/fixed/dual
    # assignment for D45; this is a genuine point of classical disagreement).
    cat = _element_category(sign0)
    base = {"movable": 0, "fixed": 4, "dual": 8}[cat]
    return (base + part) % 12


def _shashtiamsa_sign(sign0: int, part: int) -> int:
    # STANDARD CONVENTION. Starts from the sign itself and cycles through all 12
    # signs repeatedly (60 parts / 12 signs = 5 full cycles per D1 sign).
    return (sign0 + part) % 12


# num_parts, start-sign function
_EQUAL_DIVISION_VARGAS: Dict[str, Tuple[int, Callable[[int, int], int]]] = {
    "d3": (3, _drekkana_sign),
    "d4": (4, _chaturthamsa_sign),
    "d7": (7, _saptamsa_sign),
    "d9": (9, _navamsa_sign),
    "d10": (10, _dasamsa_sign),
    "d12": (12, _dwadasamsa_sign),
    "d16": (16, _shodasamsa_sign),
    "d20": (20, _vimsamsa_sign),
    "d24": (24, _chaturvimsamsa_sign),
    "d27": (27, _bhamsa_sign),
    "d40": (40, _khavedamsa_sign),
    "d45": (45, _akshavedamsa_sign),
    "d60": (60, _shashtiamsa_sign),
}

VARGA_NAMES: Dict[str, str] = {
    "d1": "Rasi", "d2": "Hora", "d3": "Drekkana", "d4": "Chaturthamsa",
    "d7": "Saptamsa", "d9": "Navamsa", "d10": "Dasamsa", "d12": "Dwadasamsa",
    "d16": "Shodasamsa", "d20": "Vimsamsa", "d24": "Chaturvimsamsa",
    "d27": "Bhamsa", "d30": "Trimsamsa", "d40": "Khavedamsa",
    "d45": "Akshavedamsa", "d60": "Shashtiamsa",
}


def _hora(sign0: int, degree: float) -> VargaResult:
    # VERIFIED (D2). Odd sign: 0-15deg = Sun's hora (Leo), 15-30 = Moon's hora (Cancer).
    # Even sign: reversed. Every planet in the D2 lands in one of only two signs -
    # that's the correct classical presentation, not a simplification.
    first_half = degree < 15
    if sign0 in ODD:
        varga_sign0 = 4 if first_half else 3   # Leo, then Cancer
    else:
        varga_sign0 = 3 if first_half else 4   # Cancer, then Leo
    span_start = 0.0 if first_half else 15.0
    frac = (degree - span_start) / 15.0
    return VargaResult(sign=varga_sign0 + 1, sign_degree=frac * 30)


# (start_degree, end_degree, resulting-sign-for-ODD-D1-sign, resulting-sign-for-EVEN-D1-sign)
_TRIMSAMSA_ODD_RANGES = [
    (0.0, 5.0, 0),    # Mars -> Aries
    (5.0, 10.0, 10),  # Saturn -> Aquarius
    (10.0, 18.0, 8),  # Jupiter -> Sagittarius
    (18.0, 25.0, 2),  # Mercury -> Gemini
    (25.0, 30.0, 6),  # Venus -> Libra
]
_TRIMSAMSA_EVEN_RANGES = [
    (0.0, 5.0, 1),    # Venus -> Taurus
    (5.0, 12.0, 5),   # Mercury -> Virgo
    (12.0, 20.0, 11), # Jupiter -> Pisces
    (20.0, 25.0, 9),  # Saturn -> Capricorn
    (25.0, 30.0, 7),  # Mars -> Scorpio
]


def _trimsamsa(sign0: int, degree: float) -> VargaResult:
    # VERIFIED degree ranges and rulers (D30). Sign resolution (which of the ruler's
    # two own signs) follows the odd/even-parity convention - see module docstring.
    ranges = _TRIMSAMSA_ODD_RANGES if sign0 in ODD else _TRIMSAMSA_EVEN_RANGES
    for start, end, varga_sign0 in ranges:
        if start <= degree < end:
            frac = (degree - start) / (end - start)
            return VargaResult(sign=varga_sign0 + 1, sign_degree=frac * 30)
    # degree == 30.0 edge case (shouldn't normally occur - degree is clamped below 30
    # by compute_varga) falls into the last range of the table
    start, end, varga_sign0 = ranges[-1]
    return VargaResult(sign=varga_sign0 + 1, sign_degree=30.0)


def compute_varga(sign_1indexed: int, sign_degree: float, varga: str) -> VargaResult:
    """
    Map a D1 (sign, sign_degree) position into the given varga.
    sign_1indexed: 1-12 (1 = Aries). sign_degree: 0-30, degrees into that sign.
    varga: "d1", "d2", "d3", "d4", "d7", "d9", "d10", "d12", "d16", "d20",
           "d24", "d27", "d30", "d40", "d45", or "d60".
    """
    varga = varga.lower()
    if varga not in VARGA_NAMES:
        raise ValueError(f"Unknown varga '{varga}'. Choose one of: {list(VARGA_NAMES)}")

    sign0 = sign_1indexed - 1
    # Clamp strictly below 30 so the division-boundary math above (which uses
    # half-open ranges) never falls through un-handled at exactly 30.0
    degree = min(max(sign_degree, 0.0), 29.999999)

    if varga == "d1":
        return VargaResult(sign=sign_1indexed, sign_degree=sign_degree)
    if varga == "d2":
        return _hora(sign0, degree)
    if varga == "d30":
        return _trimsamsa(sign0, degree)

    num_parts, start_fn = _EQUAL_DIVISION_VARGAS[varga]
    part_size = 30.0 / num_parts
    part_index = min(int(degree // part_size), num_parts - 1)
    frac = (degree - part_index * part_size) / part_size
    varga_sign0 = start_fn(sign0, part_index)
    return VargaResult(sign=varga_sign0 + 1, sign_degree=frac * 30)
