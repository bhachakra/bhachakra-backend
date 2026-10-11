"""
Bhachakra house (bhava) module.

Computes house cusps for a chart under multiple house systems:
- Placidus, Equal: standard Western systems, computed directly by Swiss Ephemeris.
- Whole Sign: each house is the entire sign it falls in - the traditional
  Vedic default, and what NorthIndianChart.tsx already assumes.
- Sripati: the traditional Vedic house system, computed by hand since Swiss
  Ephemeris has no native Sripati mode.

A note on what "cusp" means here, since Vedic and Western convention differ:
Vedic tradition distinguishes Bhava Madhya (the sensitive MIDDLE point of a
house - what most Jyotish texts and software call "the cusp") from Bhava
Sandhi (the boundary between houses). This module returns Bhava Madhya for
Sripati, which is why houses 1/4/7/10 come out exactly equal to the
Ascendant/IC/Descendant/MC - the standard convention (see e.g.
https://en.wikipedia.org/wiki/Bh%C4%81va, and astro.com's house-system
reference, which independently describe the same construction: trisect
each quadrant per Porphyry, and those trisection points are the cusps).
Western house systems (Placidus, Equal) instead report the house START
(boundary) - the standard Western convention, and what Swiss Ephemeris
itself returns directly.
"""
import swisseph as swe
from dataclasses import dataclass
from typing import Optional

from engine import AYANAMSAS, ZODIAC_SIGNS, _sign_and_nakshatra

HOUSE_SYSTEMS = {
    "placidus": "P",
    "equal": "A",
    "whole_sign": "W",   # Swiss Ephemeris supports this natively
    "sripati": None,     # no native Sripati mode - computed directly below
}


@dataclass
class HouseCusp:
    house: int  # 1-12
    longitude: float
    latitude: float  # always 0.0 - a cusp is defined to lie exactly on the ecliptic
    sign: str
    sign_degree: float
    nakshatra: Optional[str]
    nakshatra_pada: Optional[int]
    right_ascension: float
    declination: float
    azimuth: float
    altitude: float


def _arc_forward(start: float, end: float) -> float:
    """Angular distance from start to end going in the direction of increasing
    longitude (the direction houses 1->2->3->4 proceed), always 0-360."""
    return (end - start) % 360


def _porphyry_cusps(asc: float, mc: float) -> list:
    """
    Standard Porphyry construction: each of the 4 quadrants (Asc->IC->Desc->
    MC->Asc) is trisected equally in ecliptic longitude. These 12 points are
    also exactly what Sripati uses as its Bhava Madhya cusps - see module
    docstring. Returns 12 longitudes, index 0 = house 1.
    """
    ic = (mc + 180) % 360
    desc = (asc + 180) % 360

    def trisect(start, end):
        arc = _arc_forward(start, end)
        return [(start + arc / 3) % 360, (start + 2 * arc / 3) % 360]

    c2, c3 = trisect(asc, ic)
    c5, c6 = trisect(ic, desc)
    c8, c9 = trisect(desc, mc)
    c11, c12 = trisect(mc, asc)

    return [asc, c2, c3, ic, c5, c6, desc, c8, c9, mc, c11, c12]


def _raw_cusp_longitudes(jd_ut: float, lat: float, lon: float, house_system: str, flags: int,
                          subtract_value: Optional[float] = None) -> list:
    """
    The shared cusp-longitude computation, parameterized by `flags` and an
    optional post-hoc subtraction - used twice by get_house_cusps() below:
    once for the "display" longitudes (whatever zodiac/ayanamsha was
    requested) and once purely tropically (flags=0, no subtraction), which
    the RA/Dec/Alt/Az transform needs regardless of display zodiac (see
    get_house_cusps docstring for why).
    """
    hsys_code = HOUSE_SYSTEMS.get(house_system)
    if hsys_code:
        # NOTE: this pyswisseph version returns `cusps` as a 0-indexed,
        # 12-element array (cusps[0] = house 1 ... cusps[11] = house 12) -
        # NOT the 1-indexed 13-element array some older docs describe.
        cusps, _ = swe.houses_ex(jd_ut, lat, lon, hsys_code.encode(), flags=flags)
        longitudes = list(cusps)
    else:
        _, ascmc = swe.houses_ex(jd_ut, lat, lon, b'A', flags=flags)
        longitudes = _porphyry_cusps(ascmc[0], ascmc[1])

    if subtract_value is not None:
        longitudes = [(l - subtract_value) % 360 for l in longitudes]
    return longitudes


def _equatorial_and_horizon(tropical_lon_deg: float, jd_ut: float, lat: float, lon: float) -> tuple:
    """
    Ecliptic (tropical_lon, latitude=0) -> equatorial (RA, Dec) -> horizon
    (azimuth, altitude). MUST be fed a TROPICAL longitude - the
    ecliptic<->equatorial rotation is defined relative to the true equinox,
    so a sidereal-shifted longitude would rotate the point to the wrong
    physical direction in the sky. Validated against engine.py's
    FLG_EQUATORIAL output for the Sun (agreed to 4 decimal places), and
    against the Ascendant/Descendant, which must compute to ~0 deg altitude
    by definition (they're the ecliptic points on the horizon) - confirmed.
    """
    eps_data, _ = swe.calc_ut(jd_ut, swe.ECL_NUT, 0)
    eps_true = eps_data[0]
    ra, dec, _ = swe.cotrans((tropical_lon_deg, 0.0, 1.0), -eps_true)

    geopos = (lon, lat, 0)
    # distance doesn't meaningfully affect alt/az for an effectively-infinite
    # point like this (verified: varying it from 1e-6 to 1e8 changed nothing)
    azimuth, true_alt, _apparent_alt = swe.azalt(jd_ut, swe.EQU2HOR, geopos, 0, 0, (ra, dec, 1.0))
    return ra, dec, azimuth, true_alt


def get_house_cusps(
    jd_ut: float,
    lat: float,
    lon: float,
    house_system: str = "whole_sign",
    zodiac: str = "sidereal",
    ayanamsa: str = "lahiri",
    custom_ayanamsa_value: Optional[float] = None,
) -> list:
    """Returns 12 HouseCusp objects (house 1-12) under the requested system."""
    if house_system not in HOUSE_SYSTEMS:
        raise ValueError(f"Unknown house_system '{house_system}'. Choose one of: {list(HOUSE_SYSTEMS)}")

    use_custom = zodiac == "sidereal" and ayanamsa == "custom"
    if use_custom and custom_ayanamsa_value is None:
        raise ValueError("custom_ayanamsa_value is required when ayanamsa='custom'")

    flags = 0
    if zodiac == "sidereal" and not use_custom:
        swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
        flags = swe.FLG_SIDEREAL

    # Display longitudes: whatever zodiac/ayanamsha was requested (used for
    # the longitude/sign/nakshatra shown to the user)
    display_longitudes = _raw_cusp_longitudes(
        jd_ut, lat, lon, house_system, flags,
        subtract_value=custom_ayanamsa_value if use_custom else None,
    )
    # Tropical longitudes: always the true/tropical frame, regardless of
    # display zodiac - required for a correct RA/Dec/Alt/Az transform (see
    # _equatorial_and_horizon docstring)
    tropical_longitudes = _raw_cusp_longitudes(jd_ut, lat, lon, house_system, flags=0)

    result = []
    for i in range(12):
        display_lon = display_longitudes[i]
        sign, sign_deg, nak, pada = _sign_and_nakshatra(display_lon, want_nakshatra=True)
        ra, dec, az, alt = _equatorial_and_horizon(tropical_longitudes[i], jd_ut, lat, lon)
        result.append(HouseCusp(
            house=i + 1,
            longitude=round(display_lon, 4),
            latitude=0.0,
            sign=sign,
            sign_degree=round(sign_deg, 2),
            nakshatra=nak,
            nakshatra_pada=pada,
            right_ascension=round(ra, 4),
            declination=round(dec, 4),
            azimuth=round(az, 4),
            altitude=round(alt, 4),
        ))
    return result
