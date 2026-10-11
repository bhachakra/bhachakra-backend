"""
Bhachakra aspects module.

Computes aspects (angular relationships) between planets, and between
planets and house (Bhava) cusps, under two selectable systems:

- western: the standard 5 Ptolemaic aspects - conjunction (0 deg), sextile
  (60), square (90), trine (120), opposition (180) - each checked against a
  configurable ORB of allowance around the exact angle. Mutual/symmetric:
  if planet A aspects planet B, B aspects A back with the same aspect type.
  For planet-planet pairs, the allowed orb is the average ("moiety") of
  both planets' configured orbs - the standard convention. For planet-house
  pairs, only the planet's own orb applies (a house cusp has no orb of its
  own - it's a target, not an aspecting body).

- vedic: Parashari graha drishti (Brihat Parashara Hora Shastra ch. 26).
  Every planet aspects the 7th house/point counted forward from itself.
  Mars additionally aspects the 4th and 8th; Jupiter the 5th and 9th;
  Saturn the 3rd and 10th. Rahu/Ketu are given Jupiter's 5th/9th special
  aspects here, following the common modern Parashari convention used by
  most current software - the classical texts genuinely disagree on this
  specific point, so treat it as a documented default, not settled fact.
  UNLIKE Western aspects, Vedic drishti is directional/one-way: the target
  point is always counted FORWARD in zodiacal order from the aspecting
  planet, and Mars aspecting Saturn does not imply Saturn aspects Mars back
  (unless Saturn's own aspect rules independently reach Mars's position).

There is no standardized symbol set for Vedic special aspects the way
Western astrology has ☌ ⚹ □ △ ☍ - professional Vedic software (Jagannatha
Hora etc.) labels these by house number instead (e.g. "7th", "4th"). This
module does the same rather than inventing iconography that would look
authoritative but isn't an actual convention.
"""
from dataclasses import dataclass
from typing import Optional

DEFAULT_ORB = 6.0

# (aspect name, exact angle, symbol) - the 5 major Ptolemaic aspects
WESTERN_ASPECTS = [
    ("conjunction", 0, "\u260c"),
    ("sextile", 60, "\u26b9"),
    ("square", 90, "\u25a1"),
    ("trine", 120, "\u25b3"),
    ("opposition", 180, "\u260d"),
]

VEDIC_SPECIAL_HOUSES = {
    "mars": [4, 7, 8],
    "jupiter": [5, 7, 9],
    "saturn": [3, 7, 10],
    "rahu": [5, 7, 9],
    "ketu": [5, 7, 9],
}
VEDIC_DEFAULT_HOUSES = [7]

ASPECTING_BODIES = ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                     "saturn", "uranus", "neptune", "pluto", "rahu", "ketu"]


@dataclass
class AspectPoint:
    name: str      # e.g. "sun", "house_7" - stable identifier
    kind: str       # "planet" | "house"
    longitude: float
    label: str       # display label, e.g. "Su" or "House 7"
    speed: float = 0.0  # degrees/day; only meaningful when kind == "planet"


@dataclass
class Aspect:
    from_name: str
    from_label: str
    to_name: str
    to_label: str
    to_kind: str      # "planet" | "house"
    aspect_type: str    # western: "conjunction" etc.; vedic: "7th" etc.
    symbol: str
    exact_angle: float
    orb_used: float       # how far the actual separation is from exact_angle
    # True = applying (orb closing, aspect getting more exact), False =
    # separating (orb opening), None = not applicable. Deliberately None for
    # any planet-house aspect: "applying/separating" isn't a standard concept
    # for house cusps, which move at an entirely different rate (dominated by
    # Earth's rotation, ~360deg/day) than planetary orbital motion.
    applying: Optional[bool] = None


def _angular_separation(a: float, b: float) -> float:
    """Smallest angular distance between two longitudes, always 0-180."""
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


# Small forward time-step (days) used to numerically detect whether an
# aspect's orb is shrinking or growing, rather than hand-deriving direction
# rules for every combination of faster/slower/retrograde planets - this
# sidesteps that whole class of sign errors by just measuring the actual
# instantaneous trend.
_DT_DAYS = 0.01


def _western_orb_at(lon1, speed1, lon2, speed2, exact_angle, dt):
    l1 = (lon1 + speed1 * dt) % 360
    l2 = (lon2 + speed2 * dt) % 360
    return abs(_angular_separation(l1, l2) - exact_angle)


def _applying_western(lon1, speed1, lon2, speed2, exact_angle) -> Optional[bool]:
    current = _western_orb_at(lon1, speed1, lon2, speed2, exact_angle, 0.0)
    future = _western_orb_at(lon1, speed1, lon2, speed2, exact_angle, _DT_DAYS)
    if future < current - 1e-9:
        return True
    if future > current + 1e-9:
        return False
    return None


def _vedic_orb_at(p1_lon, p1_speed, offset, target_lon, target_speed, dt):
    # The Vedic aspect's target POINT is rigidly attached to p1 (it's always
    # "p1's longitude + a fixed forward offset"), so it moves at p1's speed -
    # the offset itself never changes with time, only p1's base position does
    target_point = (p1_lon + p1_speed * dt + offset) % 360
    actual = (target_lon + target_speed * dt) % 360
    return _angular_separation(target_point, actual)


def _applying_vedic(p1_lon, p1_speed, offset, target_lon, target_speed) -> Optional[bool]:
    current = _vedic_orb_at(p1_lon, p1_speed, offset, target_lon, target_speed, 0.0)
    future = _vedic_orb_at(p1_lon, p1_speed, offset, target_lon, target_speed, _DT_DAYS)
    if future < current - 1e-9:
        return True
    if future > current + 1e-9:
        return False
    return None


def _closest_western_match(separation: float, allowed_orb: float):
    """Returns the tightest-fitting aspect within orb, or None."""
    best = None
    for name, angle, symbol in WESTERN_ASPECTS:
        diff = abs(separation - angle)
        if diff <= allowed_orb and (best is None or diff < best[3]):
            best = (name, angle, symbol, diff)
    return best


def compute_western_aspects(points: list, orbs: dict) -> list:
    results = []
    planets = [p for p in points if p.kind == "planet"]
    houses = [p for p in points if p.kind == "house"]

    for i, p1 in enumerate(planets):
        for p2 in planets[i + 1:]:
            sep = _angular_separation(p1.longitude, p2.longitude)
            orb1 = orbs.get(p1.name, DEFAULT_ORB)
            orb2 = orbs.get(p2.name, DEFAULT_ORB)
            allowed_orb = (orb1 + orb2) / 2  # moiety convention
            match = _closest_western_match(sep, allowed_orb)
            if match:
                name, angle, symbol, diff = match
                applying = _applying_western(p1.longitude, p1.speed, p2.longitude, p2.speed, angle)
                results.append(Aspect(p1.name, p1.label, p2.name, p2.label, "planet",
                                       name, symbol, angle, round(diff, 3), applying))

        for h in houses:
            sep = _angular_separation(p1.longitude, h.longitude)
            orb = orbs.get(p1.name, DEFAULT_ORB)
            match = _closest_western_match(sep, orb)
            if match:
                name, angle, symbol, diff = match
                results.append(Aspect(p1.name, p1.label, h.name, h.label, "house",
                                       name, symbol, angle, round(diff, 3), None))
    return results


def compute_vedic_aspects(points: list, orbs: dict) -> list:
    results = []
    planets = [p for p in points if p.kind == "planet"]

    for p1 in planets:
        special_houses = VEDIC_SPECIAL_HOUSES.get(p1.name, VEDIC_DEFAULT_HOUSES)
        orb = orbs.get(p1.name, DEFAULT_ORB)
        for house_num in special_houses:
            exact_angle = (house_num - 1) * 30
            target_lon = (p1.longitude + exact_angle) % 360
            for target in points:
                if target.name == p1.name:
                    continue
                sep = _angular_separation(target.longitude, target_lon)
                if sep <= orb:
                    applying = None
                    if target.kind == "planet":
                        applying = _applying_vedic(p1.longitude, p1.speed, exact_angle, target.longitude, target.speed)
                    results.append(Aspect(
                        p1.name, p1.label, target.name, target.label, target.kind,
                        f"{house_num}th", "\u2192", float(exact_angle), round(sep, 3), applying,
                    ))
    return results


def compute_aspects(points: list, orbs: dict, system: str = "western") -> list:
    if system == "vedic":
        return compute_vedic_aspects(points, orbs)
    if system == "western":
        return compute_western_aspects(points, orbs)
    raise ValueError(f"Unknown aspect system '{system}'. Choose 'western' or 'vedic'.")
