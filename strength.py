"""
Bhachakra planetary-strength module: Ashtakavarga, Vimsopaka Bala, Shadbala.

All three use the seven classical grahas (Sun..Saturn) in the SIDEREAL zodiac.
Rahu / Ketu take no part.

HOW MUCH TO TRUST EACH PART
---------------------------
* Ashtakavarga - the benefic-point tables are the classical Parashari ones.
  They are self-checking: every planet's BAV must total 48/49/39/54/56/52/39
  bindus (SAV 337) whatever the chart. `compute_ashtakavarga` asserts this.
* Vimsopaka - weights are the BPHS schemes; dignity is own / adhimitra / mitra /
  sama / shatru / adhishatru from the compound (natural + temporal)
  friendship. Exaltation gets no special score (BPHS table has none).
* Shadbala - classical Parashari formulas. Several components have genuine
  convention differences between authors/software; these are listed in the
  `notes` the API returns and marked CONVENTION below. Expect small differences
  (typically a few virupas per planet) against Jagannatha Hora. Yuddha
  (planetary war) bala is not applied.
"""
import math
from typing import Dict, List, Optional, Tuple

import swisseph as swe

from engine import get_planet_position, AYANAMSAS
from vargas import compute_varga

GRAHAS = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn"]
SWE_ID = {
    "sun": swe.SUN, "moon": swe.MOON, "mars": swe.MARS, "mercury": swe.MERCURY,
    "jupiter": swe.JUPITER, "venus": swe.VENUS, "saturn": swe.SATURN,
}

# sign index 0..11 -> ruling planet
SIGN_LORD = ["mars", "venus", "mercury", "moon", "sun", "mercury",
             "venus", "mars", "jupiter", "saturn", "saturn", "jupiter"]

# ----------------------------------------------------------------------------
# Natural friendships (BPHS)
# ----------------------------------------------------------------------------
NAT_FRIENDS = {
    "sun": {"moon", "mars", "jupiter"},
    "moon": {"sun", "mercury"},
    "mars": {"sun", "moon", "jupiter"},
    "mercury": {"sun", "venus"},
    "jupiter": {"sun", "moon", "mars"},
    "venus": {"mercury", "saturn"},
    "saturn": {"mercury", "venus"},
}
NAT_ENEMIES = {
    "sun": {"venus", "saturn"},
    "moon": set(),
    "mars": {"mercury"},
    "mercury": {"moon"},
    "jupiter": {"mercury", "venus"},
    "venus": {"sun", "moon"},
    "saturn": {"sun", "moon", "mars"},
}

# Moolatrikona: planet -> (sign index, from degree, to degree)
MOOLATRIKONA = {
    "sun": (4, 0, 20), "moon": (1, 3, 30), "mars": (0, 0, 12), "mercury": (5, 15, 20),
    "jupiter": (8, 0, 10), "venus": (6, 0, 15), "saturn": (10, 0, 20),
}
# Exaltation point, absolute sidereal longitude (degrees)
EXALT_LON = {"sun": 10.0, "moon": 33.0, "mars": 298.0, "mercury": 165.0,
             "jupiter": 95.0, "venus": 357.0, "saturn": 200.0}

# ----------------------------------------------------------------------------
# ASHTAKAVARGA (BPHS benefic-house tables). Per target planet: contributor ->
# houses counted from the contributor's sign (1 = same sign) that get a bindu.
# ----------------------------------------------------------------------------
_L = "lagna"
BAV_TABLE: Dict[str, Dict[str, List[int]]] = {
    "sun": {
        "sun": [1, 2, 4, 7, 8, 9, 10, 11], "moon": [3, 6, 10, 11], "mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "mercury": [3, 5, 6, 9, 10, 11, 12], "jupiter": [5, 6, 9, 11], "venus": [6, 7, 12],
        "saturn": [1, 2, 4, 7, 8, 9, 10, 11], _L: [3, 4, 6, 10, 11, 12],
    },
    "moon": {
        "sun": [3, 6, 7, 8, 10, 11], "moon": [1, 3, 6, 7, 10, 11], "mars": [2, 3, 5, 6, 9, 10, 11],
        "mercury": [1, 3, 4, 5, 7, 8, 10, 11], "jupiter": [1, 4, 7, 8, 10, 11, 12],
        "venus": [3, 4, 5, 7, 9, 10, 11], "saturn": [3, 5, 6, 11], _L: [3, 6, 10, 11],
    },
    "mars": {
        "sun": [3, 5, 6, 10, 11], "moon": [3, 6, 11], "mars": [1, 2, 4, 7, 8, 10, 11],
        "mercury": [3, 5, 6, 11], "jupiter": [6, 10, 11, 12], "venus": [6, 8, 11, 12],
        "saturn": [1, 4, 7, 8, 9, 10, 11], _L: [1, 3, 6, 10, 11],
    },
    "mercury": {
        "sun": [5, 6, 9, 11, 12], "moon": [2, 4, 6, 8, 10, 11], "mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "mercury": [1, 3, 5, 6, 9, 10, 11, 12], "jupiter": [6, 8, 11, 12],
        "venus": [1, 2, 3, 4, 5, 8, 9, 11], "saturn": [1, 2, 4, 7, 8, 9, 10, 11], _L: [1, 2, 4, 6, 8, 10, 11],
    },
    "jupiter": {
        "sun": [1, 2, 3, 4, 7, 8, 9, 10, 11], "moon": [2, 5, 7, 9, 11], "mars": [1, 2, 4, 7, 8, 10, 11],
        "mercury": [1, 2, 4, 5, 6, 9, 10, 11], "jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
        "venus": [2, 5, 6, 9, 10, 11], "saturn": [3, 5, 6, 12], _L: [1, 2, 4, 5, 6, 7, 9, 10, 11],
    },
    "venus": {
        "sun": [8, 11, 12], "moon": [1, 2, 3, 4, 5, 8, 9, 11, 12], "mars": [3, 5, 6, 9, 11, 12],
        "mercury": [3, 5, 6, 9, 11], "jupiter": [5, 8, 9, 10, 11], "venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "saturn": [3, 4, 5, 8, 9, 10, 11], _L: [1, 2, 3, 4, 5, 8, 9, 11],
    },
    "saturn": {
        "sun": [1, 2, 4, 7, 8, 10, 11], "moon": [3, 6, 11], "mars": [3, 5, 6, 10, 11, 12],
        "mercury": [6, 8, 9, 10, 11, 12], "jupiter": [5, 6, 11, 12], "venus": [6, 11, 12],
        "saturn": [3, 5, 6, 11], _L: [1, 3, 4, 6, 10, 11],
    },
}
BAV_TOTALS = {"sun": 48, "moon": 49, "mars": 39, "mercury": 54, "jupiter": 56, "venus": 52, "saturn": 39}

# ----------------------------------------------------------------------------
# VIMSOPAKA weights (each scheme sums to 20)
# ----------------------------------------------------------------------------
VIMSOPAKA_SCHEMES: Dict[str, Dict[str, float]] = {
    "shadvarga": {"d1": 6, "d2": 2, "d3": 4, "d9": 5, "d12": 2, "d30": 1},
    "saptavarga": {"d1": 5, "d2": 2, "d3": 3, "d7": 2.5, "d9": 4.5, "d12": 2, "d30": 1},
    "dasavarga": {"d1": 3, "d2": 1.5, "d3": 1.5, "d7": 1.5, "d9": 1.5, "d10": 1.5,
                  "d12": 1.5, "d16": 1.5, "d30": 1.5, "d60": 5},
    "shodasavarga": {"d1": 3.5, "d2": 1, "d3": 1, "d4": 0.5, "d7": 0.5, "d9": 3, "d10": 0.5,
                     "d12": 0.5, "d16": 2, "d20": 0.5, "d24": 0.5, "d27": 0.5, "d30": 1,
                     "d40": 0.5, "d45": 0.5, "d60": 4},
}
VIMSOPAKA_POINTS = {"own": 20, "adhimitra": 18, "mitra": 15, "sama": 10, "shatru": 7, "adhishatru": 5}

# Saptavargaja (Sthana bala) points per dignity, over D1 D2 D3 D7 D9 D12 D30
SAPTAVARGAJA_VARGAS = ["d1", "d2", "d3", "d7", "d9", "d12", "d30"]
SAPTAVARGAJA_POINTS = {"moolatrikona": 45, "own": 30, "adhimitra": 20, "mitra": 15,
                       "sama": 10, "shatru": 4, "adhishatru": 2}

NAISARGIKA = {"sun": 60.0, "moon": 51.43, "venus": 42.86, "jupiter": 34.29,
              "mercury": 25.71, "mars": 17.14, "saturn": 8.57}
REQUIRED_RUPAS = {"sun": 6.5, "moon": 6.0, "mars": 5.0, "mercury": 7.0,
                  "jupiter": 6.5, "venus": 5.5, "saturn": 5.0}

WEEKDAY_LORD = ["moon", "mars", "mercury", "jupiter", "venus", "saturn", "sun"]  # Monday = 0
HORA_SEQ = ["sun", "venus", "mercury", "moon", "saturn", "jupiter", "mars"]


# ----------------------------------------------------------------------------
# Relationships and dignity
# ----------------------------------------------------------------------------
def _compound_relation(planet: str, other: str, d1_signs: Dict[str, int]) -> str:
    """Panchadha maitri of `planet` towards `other` (the lord of the sign it occupies)."""
    if other in NAT_FRIENDS[planet]:
        nat = 1
    elif other in NAT_ENEMIES[planet]:
        nat = -1
    else:
        nat = 0
    house_of_other = (d1_signs[other] - d1_signs[planet]) % 12 + 1
    temp = 1 if house_of_other in (2, 3, 4, 10, 11, 12) else -1
    total = nat + temp
    return {2: "adhimitra", 1: "mitra", 0: "sama", -1: "shatru", -2: "adhishatru"}[total]


def dignity_in_sign(planet: str, sign0: int, d1_signs: Dict[str, int],
                    degree: Optional[float] = None) -> str:
    """own / moolatrikona(D1 only, when degree given) / adhimitra ... adhishatru"""
    lord = SIGN_LORD[sign0]
    if lord == planet:
        if degree is not None:
            m_sign, lo, hi = MOOLATRIKONA[planet]
            if sign0 == m_sign and lo <= degree < hi:
                return "moolatrikona"
        return "own"
    return _compound_relation(planet, lord, d1_signs)


# ----------------------------------------------------------------------------
# Chart data
# ----------------------------------------------------------------------------
def _sidereal_asc_mc(jd: float, lat: float, lon: float, ayanamsa: str,
                     custom: Optional[float]) -> Tuple[float, float]:
    use_custom = ayanamsa == "custom"
    flags = 0
    if not use_custom:
        swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
        flags = swe.FLG_SIDEREAL
    _cusps, ascmc = swe.houses_ex(jd, lat, lon, b"A", flags=flags)
    asc, mc = ascmc[0], ascmc[1]
    if use_custom:
        asc = (asc - custom) % 360
        mc = (mc - custom) % 360
    return asc % 360, mc % 360


def _angle_diff(a: float, b: float) -> float:
    d = abs((a - b) % 360)
    return d if d <= 180 else 360 - d


def load_chart(jd: float, lat: float, lon: float, ayanamsa: str, custom: Optional[float]) -> dict:
    planets = {}
    for g in GRAHAS:
        p = get_planet_position(jd, g, zodiac="sidereal", ayanamsa=ayanamsa, custom_ayanamsa_value=custom)
        sign0 = int(p.longitude // 30)
        planets[g] = {
            "longitude": p.longitude, "sign0": sign0, "degree": p.longitude % 30,
            "speed": p.speed_long, "retrograde": p.retrograde,
        }
    asc, mc = _sidereal_asc_mc(jd, lat, lon, ayanamsa, custom)
    return {"planets": planets, "asc": asc, "mc": mc, "asc_sign0": int(asc // 30)}


def _varga_sign0(chart: dict, planet: str, varga: str) -> int:
    p = chart["planets"][planet]
    if varga == "d1":
        return p["sign0"]
    return compute_varga(p["sign0"] + 1, p["degree"], varga).sign - 1


# ----------------------------------------------------------------------------
# ASHTAKAVARGA
# ----------------------------------------------------------------------------
def compute_ashtakavarga(chart: dict) -> dict:
    ref_signs = {g: chart["planets"][g]["sign0"] for g in GRAHAS}
    ref_signs[_L] = chart["asc_sign0"]
    bav: Dict[str, List[int]] = {}
    for target in GRAHAS:
        row = [0] * 12
        for contributor, houses in BAV_TABLE[target].items():
            base = ref_signs[contributor]
            for h in houses:
                row[(base + h - 1) % 12] += 1
        assert sum(row) == BAV_TOTALS[target], f"BAV total mismatch for {target}"
        bav[target] = row
    sav = [sum(bav[g][s] for g in GRAHAS) for s in range(12)]
    assert sum(sav) == 337
    return {
        "lagna_sign": chart["asc_sign0"] + 1,
        "planet_signs": {g: ref_signs[g] + 1 for g in GRAHAS},
        "bav": bav,
        "sav": sav,
    }


# ----------------------------------------------------------------------------
# VIMSOPAKA
# ----------------------------------------------------------------------------
def compute_vimsopaka(chart: dict, scheme: str = "shodasavarga") -> dict:
    weights = VIMSOPAKA_SCHEMES[scheme]
    d1_signs = {g: chart["planets"][g]["sign0"] for g in GRAHAS}
    out = {}
    for g in GRAHAS:
        total = 0.0
        detail = []
        for varga, w in weights.items():
            s0 = _varga_sign0(chart, g, varga)
            rel = dignity_in_sign(g, s0, d1_signs)
            pts = VIMSOPAKA_POINTS[rel]
            total += w * pts / 20.0
            detail.append({"varga": varga, "sign": s0 + 1, "weight": w, "relation": rel, "points": pts})
        out[g] = {"score": round(total, 2), "detail": detail}
    return {"scheme": scheme, "max": 20, "planets": out}


# ----------------------------------------------------------------------------
# SHADBALA helpers
# ----------------------------------------------------------------------------
def _rise_set(jd_start: float, lat: float, lon: float, kind: int) -> Optional[float]:
    try:
        res, tret = swe.rise_trans(jd_start, swe.SUN, kind, (lon, lat, 0.0), 0.0, 0.0, swe.FLG_SWIEPH)
        if res < 0:
            return None
        return tret[0]
    except Exception:
        return None


def _vedic_day(jd: float, lat: float, lon: float) -> dict:
    """Sunrise-to-sunrise day containing jd: sunrise, sunset, next sunrise, weekday index (Mon=0)."""
    r = _rise_set(jd - 1.2, lat, lon, swe.CALC_RISE)
    if r is None:
        r = jd - 0.25  # polar fallback
        nxt, ss = r + 1.0, r + 0.5
    else:
        nxt = None
        for _ in range(4):
            nxt = _rise_set(r + 0.3, lat, lon, swe.CALC_RISE)
            if nxt is None:
                nxt = r + 1.0
                break
            if nxt > jd:
                break
            r = nxt
        ss = _rise_set(r, lat, lon, swe.CALC_SET)
        if ss is None:
            ss = r + 0.5
    local = r + lon / 360.0
    wd = int(math.floor(local + 0.5)) % 7
    return {"sunrise": r, "sunset": ss, "next_sunrise": nxt, "weekday": wd}


def _hora_lord_at(jd_event: float, lat: float, lon: float) -> str:
    """Lord of the hora running at an instant (sunrise-to-sunrise day split into 24 equal horas)."""
    d = _vedic_day(jd_event, lat, lon)
    idx = min(23, max(0, int((jd_event - d["sunrise"]) / (d["next_sunrise"] - d["sunrise"]) * 24)))
    return HORA_SEQ[(HORA_SEQ.index(WEEKDAY_LORD[d["weekday"]]) + idx) % 7]


def _last_ingress(jd: float, sun_sid_lon: float, target: float, ayanamsa: str, custom: Optional[float]) -> float:
    """JD when the sidereal Sun last crossed `target` degrees (a multiple of 30)."""
    since = (sun_sid_lon - target) % 360
    est = jd - since / 0.9856

    def f(t: float) -> float:
        lon_t = get_planet_position(t, "sun", zodiac="sidereal", ayanamsa=ayanamsa,
                                     custom_ayanamsa_value=custom).longitude
        return ((lon_t - target + 180) % 360) - 180

    lo, hi = est - 6, est + 6
    if f(lo) > 0 or f(hi) < 0:
        return est
    for _ in range(40):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _equatorial_declination(jd: float, planet: str) -> float:
    xx, _ = swe.calc_ut(jd, SWE_ID[planet], swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
    return xx[1]


def _drishti_value(d: float, planet: str) -> float:
    """Aspect strength (virupas, 0-60) a planet casts on a point `d` degrees ahead of it."""
    d = d % 360
    if d < 30:
        v = 0.0
    elif d < 60:
        v = (d - 30) / 2
    elif d < 90:
        v = (d - 60) + 15
    elif d < 120:
        v = (120 - d) / 2 + 30
    elif d < 150:
        v = 150 - d
    elif d < 180:
        v = (d - 150) * 2
    elif d < 300:
        v = (300 - d) / 2
    else:
        v = 0.0
    # special full aspects
    if planet == "mars" and (90 <= d < 120 or 210 <= d < 240):
        v += 15
    if planet == "jupiter" and (120 <= d < 150 or 240 <= d < 270):
        v += 30
    if planet == "saturn" and (60 <= d < 90 or 270 <= d < 300):
        v += 45
    return v


# ----------------------------------------------------------------------------
# SHADBALA
# ----------------------------------------------------------------------------
def compute_shadbala(jd: float, chart: dict, lat: float, lon: float,
                     ayanamsa: str, custom: Optional[float]) -> dict:
    P = chart["planets"]
    d1_signs = {g: P[g]["sign0"] for g in GRAHAS}
    asc_sign0 = chart["asc_sign0"]

    # --- shared time/day facts ---
    day = _vedic_day(jd, lat, lon)
    sr0, ss, sr1 = day["sunrise"], day["sunset"], day["next_sunrise"]
    weekday_lord = WEEKDAY_LORD[day["weekday"]]
    is_day = jd < ss
    midday = (sr0 + ss) / 2
    dn_hours = abs(((jd - midday + 0.5) % 1.0) - 0.5) * 24.0  # hours from nearest local noon (0..12)
    hora_idx = min(23, max(0, int((jd - sr0) / (sr1 - sr0) * 24)))
    hora_lord = HORA_SEQ[(HORA_SEQ.index(weekday_lord) + hora_idx) % 7]
    if is_day:
        part = min(2, int((jd - sr0) / ((ss - sr0) / 3)))
        tribhaga_lord = ["mercury", "sun", "saturn"][part]
    else:
        part = min(2, int((jd - ss) / ((sr1 - ss) / 3)))
        tribhaga_lord = ["moon", "venus", "mars"][part]
    sun_sid = P["sun"]["longitude"]
    year_start = _last_ingress(jd, sun_sid, 0.0, ayanamsa, custom)
    month_start = _last_ingress(jd, sun_sid, math.floor(sun_sid / 30) * 30.0, ayanamsa, custom)
    abda_lord = _hora_lord_at(year_start, lat, lon)   # BPHS: hora lord at Mesha sankranti
    masa_lord = _hora_lord_at(month_start, lat, lon)  # BPHS: hora lord at the month's sankranti

    elong = (P["moon"]["longitude"] - P["sun"]["longitude"]) % 360
    elong_fold = elong if elong <= 180 else 360 - elong
    paksha_benefic = elong_fold / 3.0
    moon_is_benefic = elong_fold > 90
    benefics = {"jupiter", "venus", "mercury"} | ({"moon"} if moon_is_benefic else set())

    sun_geo_trop, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
    sun_geo_trop = sun_geo_trop[0]

    asc, mc = chart["asc"], chart["mc"]
    dig_peak = {"jupiter": asc, "mercury": asc, "sun": mc, "mars": mc,
                "saturn": (asc + 180) % 360, "moon": (mc + 180) % 360, "venus": (mc + 180) % 360}

    out = {}
    for g in GRAHAS:
        p = P[g]
        comp = {}

        # ---------- Sthana bala ----------
        deb_point = (EXALT_LON[g] + 180) % 360
        uchcha = _angle_diff(p["longitude"], deb_point) / 3.0

        sapta = 0.0
        for v in SAPTAVARGAJA_VARGAS:
            s0 = _varga_sign0(chart, g, v)
            rel = dignity_in_sign(g, s0, d1_signs, p["degree"] if v == "d1" else None)
            sapta += SAPTAVARGAJA_POINTS[rel]

        s_rasi = p["sign0"]
        s_nav = _varga_sign0(chart, g, "d9")
        even = lambda s: s % 2 == 1  # sign0 odd index = even-numbered sign (Taurus=index1)
        want_even = g in ("moon", "venus")
        ojayugma = (15.0 if even(s_rasi) == want_even else 0.0) + (15.0 if even(s_nav) == want_even else 0.0)

        house = (p["sign0"] - asc_sign0) % 12 + 1
        kendra = 60.0 if house in (1, 4, 7, 10) else 30.0 if house in (2, 5, 8, 11) else 15.0

        dr_part = int(p["degree"] // 10)  # 0,1,2
        dr_ok = {"sun": 0, "mars": 0, "jupiter": 0, "mercury": 1, "saturn": 1, "moon": 2, "venus": 2}[g]
        drekkana = 15.0 if dr_part == dr_ok else 0.0

        sthana = uchcha + sapta + ojayugma + kendra + drekkana
        comp["sthana"] = {"total": sthana, "uchcha": uchcha, "saptavargaja": sapta,
                          "ojayugma": ojayugma, "kendra": kendra, "drekkana": drekkana}

        # ---------- Dig bala ----------
        weak = (dig_peak[g] + 180) % 360
        dig = _angle_diff(p["longitude"], weak) / 3.0
        comp["dig"] = dig

        # ---------- Kala bala ----------
        diurnal = g in ("sun", "jupiter", "venus")
        if g == "mercury":
            nathonnata = 60.0
        elif diurnal:
            nathonnata = 60.0 * (1 - dn_hours / 12.0)
        else:
            nathonnata = 60.0 * dn_hours / 12.0

        paksha = paksha_benefic if g in benefics or g == "moon" else 60.0 - paksha_benefic
        if g == "moon":
            paksha = paksha_benefic  # the Moon always gets the waxing-strength value
        paksha_counted = paksha

        tribhaga = 60.0 if (g == "jupiter" or g == tribhaga_lord) else 0.0
        abda = 15.0 if g == abda_lord else 0.0
        masa = 30.0 if g == masa_lord else 0.0
        vara = 45.0 if g == weekday_lord else 0.0
        hora = 60.0 if g == hora_lord else 0.0

        dec = _equatorial_declination(jd, g)
        if g in ("moon", "saturn"):
            ayana = (23.45 - dec) / 46.9 * 60.0
        elif g == "mercury":
            ayana = (23.45 + abs(dec)) / 46.9 * 60.0   # Mercury: declination always added
        else:
            ayana = (23.45 + dec) / 46.9 * 60.0
        ayana = max(0.0, min(60.0, ayana))
        ayana_counted = ayana

        kala = nathonnata + paksha_counted + tribhaga + abda + masa + vara + hora + ayana_counted
        comp["kala"] = {"total": kala, "nathonnata": nathonnata, "paksha": paksha_counted,
                        "tribhaga": tribhaga, "abda": abda, "masa": masa, "vara": vara,
                        "hora": hora, "ayana": ayana_counted}

        # ---------- Cheshta bala ----------
        if g == "sun":
            cheshta = ayana_counted      # CONVENTION: Sun's Cheshta = its Ayana bala
        elif g == "moon":
            cheshta = paksha_benefic     # CONVENTION: Moon's Cheshta = its Paksha bala
        else:
            helio, _ = swe.calc_ut(jd, SWE_ID[g], swe.FLG_SWIEPH | swe.FLG_HELCTR)
            kendra_ang = _angle_diff(sun_geo_trop, helio[0])
            cheshta = kendra_ang / 3.0   # approximation of Cheshta kendra / 3 (see module docstring)
        comp["cheshta"] = cheshta

        comp["naisargika"] = NAISARGIKA[g]

        # ---------- Drik bala ----------
        drik = 0.0
        for a in GRAHAS:
            if a == g:
                continue
            val = _drishti_value(P[g]["longitude"] - P[a]["longitude"], a)
            drik += (val if a in benefics else -val) / 4.0
        comp["drik"] = drik

        total = sthana + dig + kala + cheshta + NAISARGIKA[g] + drik
        out[g] = {
            "components": {
                "sthana": round(sthana, 2), "dig": round(dig, 2), "kala": round(kala, 2),
                "cheshta": round(cheshta, 2), "naisargika": round(NAISARGIKA[g], 2), "drik": round(drik, 2),
            },
            "sthana_detail": {k: round(v, 2) for k, v in comp["sthana"].items() if k != "total"},
            "kala_detail": {k: round(v, 2) for k, v in comp["kala"].items() if k != "total"},
            "total_virupas": round(total, 2),
            "total_rupas": round(total / 60.0, 2),
            "required_rupas": REQUIRED_RUPAS[g],
            "ratio": round(total / 60.0 / REQUIRED_RUPAS[g], 2),
            "strong": total / 60.0 >= REQUIRED_RUPAS[g],
        }
    return {
        "planets": out,
        "facts": {"weekday_lord": weekday_lord, "hora_lord": hora_lord, "tribhaga_lord": tribhaga_lord,
                  "abda_lord": abda_lord, "masa_lord": masa_lord, "is_day": is_day,
                  "moon_benefic": moon_is_benefic},
        "notes": [
            "Paksha and Ayana bala are NOT doubled for the Moon / Sun (some authors double them).",
            "Mercury's Ayana bala always adds the declination's magnitude.",
            "Sun's Cheshta bala = its Ayana bala; Moon's Cheshta bala = its Paksha bala.",
            "Cheshta bala for Mars-Saturn is a geometric approximation of Cheshta kendra / 3.",
            "Abda / Masa lords = hora lord at the last Mesha sankranti / solar-month ingress.",
            "Yuddha (planetary war) bala is not applied.",
        ],
    }


# ----------------------------------------------------------------------------
def compute_all(jd: float, lat: float, lon: float, ayanamsa: str = "lahiri",
                custom: Optional[float] = None, scheme: str = "shodasavarga") -> dict:
    chart = load_chart(jd, lat, lon, ayanamsa, custom)
    return {
        "ashtakavarga": compute_ashtakavarga(chart),
        "vimsopaka": compute_vimsopaka(chart, scheme),
        "shadbala": compute_shadbala(jd, chart, lat, lon, ayanamsa, custom),
    }
