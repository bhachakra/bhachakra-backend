"""
Bhachakra - Krishnamurti Paddhati (KP).

Everything the KP screen shows, for one moment and place:

  cusps        the 12 Placidus cusps (KP's house system), sidereal with the
               KP ayanamsa, each with its sign lord, star lord, sub lord and
               sub-sub lord
  planets      the same lords for every planet, plus the house it occupies
               counted by cusp (not by sign)
  significators
               by planet - which houses each planet signifies, in KP's four
               levels; and by house - which planets signify each house
  ruling planets
               day lord, Lagna sign/star/sub lord and Moon sign/star/sub lord
               at the moment (KP's "RP"), used to judge and time a question

How the subs work: each nakshatra (13°20') is split into 9 subs, one for each
Vimshottari lord, in the dasha order starting from the nakshatra's own lord,
each sub as long as that lord's dasha years out of 120. A sub is split again
the same way into 9 sub-subs. (Over the whole zodiac this gives KP's familiar
table of 249 numbered sub divisions.)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import swisseph as swe

from engine import NAKSHATRAS, ZODIAC_SIGNS
from panchanga import _vedic_day

# KP ayanamsas available in Swiss Ephemeris
KP_AYANAMSAS = {
    "kp": swe.SIDM_KRISHNAMURTI,  # KP (Krishnamurti), the original
    "kp_new": getattr(swe, "SIDM_KRISHNAMURTI_VP291", swe.SIDM_KRISHNAMURTI),  # "KP New" (Krishnamurti-Senthilathiban)
}

# Vimshottari order and years - the basis of star and sub lords
DASHA_ORDER = ["ketu", "venus", "sun", "moon", "mars", "rahu", "jupiter", "saturn", "mercury"]
DASHA_YEARS = {"ketu": 7, "venus": 20, "sun": 6, "moon": 10, "mars": 7, "rahu": 18, "jupiter": 16, "saturn": 19, "mercury": 17}

# Lord of each sign, Aries..Pisces
SIGN_LORDS = ["mars", "venus", "mercury", "moon", "sun", "mercury", "venus", "mars", "jupiter", "saturn", "saturn", "jupiter"]

# Lord of each weekday, Sunday..Saturday
DAY_LORDS = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn"]

# The nine KP grahas, in the usual listing order
GRAHAS = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]
OUTER = {"uranus": swe.URANUS, "neptune": swe.NEPTUNE, "pluto": swe.PLUTO}
BODIES = {
    "sun": swe.SUN, "moon": swe.MOON, "mars": swe.MARS, "mercury": swe.MERCURY,
    "jupiter": swe.JUPITER, "venus": swe.VENUS, "saturn": swe.SATURN,
}

NAK_SPAN = 40.0 / 3.0  # 13°20'


def _divide(start: float, span: float, first_lord: str, lon: float):
    """Which of the 9 Vimshottari divisions of [start, start+span) holds lon,
    starting from first_lord. Returns (lord, division_start, division_span)."""
    i0 = DASHA_ORDER.index(first_lord)
    pos = start
    for k in range(9):
        lord = DASHA_ORDER[(i0 + k) % 9]
        length = span * DASHA_YEARS[lord] / 120.0
        if lon < pos + length or k == 8:
            return lord, pos, length
        pos += length
    raise AssertionError("unreachable")


@dataclass
class Lords:
    sign: str
    star: str
    sub: str
    subsub: str


def kp_lords(longitude: float) -> Lords:
    """Sign, star, sub and sub-sub lord of a sidereal longitude."""
    lon = longitude % 360.0
    sign_lord = SIGN_LORDS[int(lon // 30)]
    n = min(int(lon // NAK_SPAN), 26)
    star_lord = DASHA_ORDER[n % 9]
    sub_lord, sub_start, sub_span = _divide(n * NAK_SPAN, NAK_SPAN, star_lord, lon)
    subsub_lord, _, _ = _divide(sub_start, sub_span, sub_lord, lon)
    return Lords(sign_lord, star_lord, sub_lord, subsub_lord)


def _point(longitude: float) -> dict:
    lon = longitude % 360.0
    n = min(int(lon // NAK_SPAN), 26)
    lords = kp_lords(lon)
    return {
        "longitude": round(lon, 4),
        "sign": int(lon // 30) + 1,  # 1-12
        "sign_name": ZODIAC_SIGNS[int(lon // 30)],
        "sign_degree": round(lon % 30, 4),
        "nakshatra": NAKSHATRAS[n],
        "nakshatra_pada": int((lon % NAK_SPAN) // (NAK_SPAN / 4)) + 1,
        "sign_lord": lords.sign,
        "star_lord": lords.star,
        "sub_lord": lords.sub,
        "subsub_lord": lords.subsub,
    }


def house_of(longitude: float, cusps: List[float]) -> int:
    """House (1-12) a longitude falls in, counted by Placidus cusp: house h
    runs from cusp h up to cusp h+1."""
    lon = longitude % 360.0
    for h in range(12):
        start, end = cusps[h], cusps[(h + 1) % 12]
        if (lon - start) % 360.0 < (end - start) % 360.0:
            return h + 1
    return 12  # only reachable through rounding at a cusp


def _placidus_cusps(jd_ut: float, lat: float, lon: float) -> List[float]:
    # KP uses Placidus. Near the poles Placidus has no solution; Swiss
    # Ephemeris then falls back to Porphyry by itself.
    cusps, _ascmc = swe.houses_ex(jd_ut, lat, lon, b"P", swe.FLG_SIDEREAL)
    cusps = list(cusps)
    if len(cusps) == 13:  # older pyswisseph: 1-indexed, cusps[0] unused
        cusps = cusps[1:]
    return [c % 360.0 for c in cusps[:12]]


def _significations(
    planet_houses: Dict[str, int], planet_star: Dict[str, str], planet_sign_lord: Dict[str, str], cusps_signs: List[int]
):
    """KP significators.

    Ownership: a planet owns the houses whose CUSP falls in one of its signs.
    Rahu and Ketu own no sign; as KP has it, they act for the lord of the sign
    they sit in, so they take on that planet's ownership.

    By planet, four levels (strongest first):
      A  houses occupied by the planet's star lord
      B  the house the planet occupies
      C  houses owned by the planet's star lord
      D  houses the planet owns
    By house, the matching four levels:
      1  planets in the star of the occupants of the house
      2  the occupants
      3  planets in the star of the owner of the house
      4  the owner
    """
    owns: Dict[str, List[int]] = {g: [] for g in GRAHAS}
    owner_of_house: Dict[int, str] = {}
    for h, sign in enumerate(cusps_signs, start=1):
        lord = SIGN_LORDS[sign - 1]
        owner_of_house[h] = lord
        owns[lord].append(h)
    for node in ("rahu", "ketu"):
        owns[node] = list(owns[planet_sign_lord[node]])

    by_planet = {}
    for g in GRAHAS:
        star = planet_star[g]
        a = [planet_houses[star]]
        b = [planet_houses[g]]
        c = sorted(set(owns[star]))
        d = sorted(set(owns[g]))
        every = sorted(set(a + b + c + d))
        by_planet[g] = {"A": a, "B": b, "C": c, "D": d, "all": every}

    occupants = {h: [g for g in GRAHAS if planet_houses[g] == h] for h in range(1, 13)}
    in_star_of = lambda lords: [g for g in GRAHAS if planet_star[g] in lords]  # noqa: E731
    by_house = {}
    for h in range(1, 13):
        occ = occupants[h]
        owner = owner_of_house[h]
        by_house[h] = {
            "L1": in_star_of(occ),
            "L2": occ,
            "L3": in_star_of([owner]),
            "L4": [owner],
            "owner": owner,
        }
    return by_planet, by_house


def ruling_planets(jd_ut: float, lat: float, lon: float, asc_lon: float, moon_lon: float, node_sign_lords: Dict[str, str]) -> dict:
    """KP Ruling Planets for the moment. The day runs sunrise to sunrise at the
    place (falls back to the civil weekday where the Sun doesn't rise or set)."""
    day = _vedic_day(jd_ut, lat, lon)
    if day:
        weekday = int(day[0] + lon / 360.0 + 1.5) % 7
        basis = "sunrise"
    else:
        weekday = int(jd_ut + 1.5) % 7
        basis = "civil"
    asc = kp_lords(asc_lon)
    moon = kp_lords(moon_lon)
    rp = {
        "day_lord": DAY_LORDS[weekday],
        "day_basis": basis,
        "lagna_sign_lord": asc.sign,
        "lagna_star_lord": asc.star,
        "lagna_sub_lord": asc.sub,
        "moon_sign_lord": moon.sign,
        "moon_star_lord": moon.star,
        "moon_sub_lord": moon.sub,
    }
    # Strongest first, as KP usually ranks them; each planet listed once
    order = [asc.star, asc.sign, moon.star, moon.sign, DAY_LORDS[weekday], asc.sub, moon.sub]
    seen: List[str] = []
    for p in order:
        if p not in seen:
            seen.append(p)
    rp["ranked"] = seen
    # Rahu / Ketu stand in for the lord of the sign they occupy - so they
    # count as ruling planets when that lord is one
    rp["nodes"] = [n for n in ("rahu", "ketu") if node_sign_lords[n] in seen]
    return rp


def get_kp(jd_ut: float, lat: float, lon: float, ayanamsa: str = "kp", nodes: str = "mean") -> dict:
    """The whole KP picture for one moment and place."""
    if ayanamsa not in KP_AYANAMSAS:
        raise ValueError(f"Unknown KP ayanamsa '{ayanamsa}'. Choose one of: {list(KP_AYANAMSAS)}")
    swe.set_sid_mode(KP_AYANAMSAS[ayanamsa], 0, 0)
    ayan_value = swe.get_ayanamsa_ut(jd_ut)

    cusp_lons = _placidus_cusps(jd_ut, lat, lon)
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL

    raw = {}
    for key, body in {**BODIES, **OUTER}.items():
        pos, _ = swe.calc_ut(jd_ut, body, flags)
        raw[key] = (pos[0] % 360.0, pos[3])
    node_body = swe.MEAN_NODE if nodes == "mean" else swe.TRUE_NODE
    npos, _ = swe.calc_ut(jd_ut, node_body, flags)
    raw["rahu"] = (npos[0] % 360.0, npos[3])
    raw["ketu"] = ((npos[0] + 180.0) % 360.0, npos[3])

    planets = []
    for key in GRAHAS + list(OUTER):
        lon_p, speed = raw[key]
        p = _point(lon_p)
        p.update({
            "key": key,
            "speed": round(speed, 4),
            # Rahu/Ketu always move backwards - not shown as "retrograde"
            "retrograde": speed < 0 and key not in ("rahu", "ketu"),
            "house": house_of(lon_p, cusp_lons),
            "outer": key in OUTER,  # Uranus/Neptune/Pluto: shown, but not used in significators or RP
        })
        planets.append(p)

    cusps = []
    for h, c in enumerate(cusp_lons, start=1):
        cp = _point(c)
        cp["house"] = h
        cusps.append(cp)

    by_key = {p["key"]: p for p in planets}
    by_planet, by_house = _significations(
        planet_houses={g: by_key[g]["house"] for g in GRAHAS},
        planet_star={g: by_key[g]["star_lord"] for g in GRAHAS},
        planet_sign_lord={g: by_key[g]["sign_lord"] for g in GRAHAS},
        cusps_signs=[c["sign"] for c in cusps],
    )
    rp = ruling_planets(
        jd_ut, lat, lon, cusp_lons[0], by_key["moon"]["longitude"],
        {n: by_key[n]["sign_lord"] for n in ("rahu", "ketu")},
    )

    return {
        "ayanamsa": ayanamsa,
        "ayanamsa_value": round(ayan_value, 6),
        "nodes": nodes,
        "house_system": "placidus",
        "ascendant": cusps[0],
        "cusps": cusps,
        "planets": planets,
        "significators": {"by_planet": by_planet, "by_house": {str(h): v for h, v in by_house.items()}},
        "ruling_planets": rp,
    }
