"""
Bhachakra core ephemeris engine.
Thin, well-tested wrapper around pyswisseph (Swiss Ephemeris).

Everything else in the app (panchanga, dashas, houses, aspects) is built
on top of the position data this module returns - keep this module the
single source of truth for "where is X, in frame Y, on date Z".
"""
import swisseph as swe
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Body identifiers
# ---------------------------------------------------------------------------
PLANETS = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}

# Planets for which heliocentric/geocentric ORBITAL nodes make sense
# (Sun has none; Moon's "node" is the lunar node, handled separately)
NODE_CAPABLE_PLANETS = {
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}

AYANAMSAS = {
    "lahiri": swe.SIDM_LAHIRI,
    "raman": swe.SIDM_RAMAN,
    "krishnamurti": swe.SIDM_KRISHNAMURTI,
    "fagan_bradley": swe.SIDM_FAGAN_BRADLEY,
}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]


@dataclass
class BodyPosition:
    name: str
    longitude: float          # ecliptic longitude, degrees 0-360
    latitude: float
    distance: float            # AU
    speed_long: float          # deg/day (negative = retrograde)
    retrograde: bool
    sign: str
    sign_deg: float             # degrees into the sign (0-30)
    nakshatra: Optional[str] = None
    nakshatra_pada: Optional[int] = None


@dataclass
class NodePosition:
    body: str
    frame: str          # "geo" or "helio"
    ascending_longitude: float
    descending_longitude: float
    sign_asc: str
    sign_desc: str
    asc_sign_degree: float = 0.0
    desc_sign_degree: float = 0.0
    asc_nakshatra: Optional[str] = None
    asc_nakshatra_pada: Optional[int] = None
    desc_nakshatra: Optional[str] = None
    desc_nakshatra_pada: Optional[int] = None


def to_julian_day(dt: datetime, calendar: str = "gregorian") -> float:
    """
    Convert a Python datetime (assumed UTC) to Julian Day (UT).
    calendar: "gregorian" or "julian" - matters for dates before 1582-10-15.
    Supports negative years (BCE) via astronomical year numbering
    (e.g. 1 BCE = year 0, 2 BCE = year -1).
    """
    cal_flag = swe.GREG_CAL if calendar == "gregorian" else swe.JUL_CAL
    hour = dt.hour + dt.minute / 60 + dt.second / 3600
    return swe.julday(dt.year, dt.month, dt.day, hour, cal_flag)


def _sign_and_nakshatra(longitude: float, want_nakshatra: bool = False):
    longitude = longitude % 360
    sign_index = int(longitude // 30)
    sign_deg = longitude % 30
    sign = ZODIAC_SIGNS[sign_index]
    nak_name, pada = None, None
    if want_nakshatra:
        nak_span = 360 / 27          # 13°20'
        pada_span = nak_span / 4      # 3°20'
        nak_index = int(longitude // nak_span)
        nak_name = NAKSHATRAS[nak_index]
        pada = int((longitude % nak_span) // pada_span) + 1
    return sign, sign_deg, nak_name, pada


def get_planet_position(
    jd_ut: float,
    body: str,
    frame: str = "geo",          # "geo" or "helio"
    zodiac: str = "tropical",    # "tropical" or "sidereal"
    ayanamsa: str = "lahiri",
    node_type: str = "true",     # for moon only: "true" or "mean"
    custom_ayanamsa_value: Optional[float] = None,
) -> BodyPosition:
    """
    Get a single body's position for a given Julian Day (UT).

    ayanamsa="custom" is handled separately from the built-in Swiss Ephemeris
    ayanamsas: Swiss Ephemeris only knows fixed constants (Lahiri, Raman, ...),
    so a custom ayanamsa can't be set via swe.set_sid_mode(). Instead we always
    compute the body in the TROPICAL frame, then manually subtract
    custom_ayanamsa_value (degrees) from the longitude - which is exactly what
    an ayanamsa is: a tropical-to-sidereal offset.
    """
    use_custom = zodiac == "sidereal" and ayanamsa == "custom"
    if use_custom and custom_ayanamsa_value is None:
        raise ValueError("custom_ayanamsa_value is required when ayanamsa='custom'")

    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    if frame == "helio":
        flags |= swe.FLG_HELCTR
    if zodiac == "sidereal" and not use_custom:
        swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
        flags |= swe.FLG_SIDEREAL
    # use_custom deliberately leaves flags tropical - offset applied below

    if body == "rahu":
        planet_id = swe.TRUE_NODE if node_type == "true" else swe.MEAN_NODE
    elif body == "ketu":
        # Ketu = Rahu + 180 deg, not a separate SE body
        rahu_id = swe.TRUE_NODE if node_type == "true" else swe.MEAN_NODE
        xx, _ = swe.calc_ut(jd_ut, rahu_id, flags)
        lon = (xx[0] + 180) % 360
        if use_custom:
            lon = (lon - custom_ayanamsa_value) % 360
        sign, sign_deg, nak, pada = _sign_and_nakshatra(lon, want_nakshatra=True)
        return BodyPosition("ketu", lon, -xx[1], xx[2], xx[3], xx[3] < 0,
                             sign, sign_deg, nak, pada)
    else:
        planet_id = PLANETS[body]

    xx, ret_flags = swe.calc_ut(jd_ut, planet_id, flags)
    lon, lat, dist, speed_lon = xx[0], xx[1], xx[2], xx[3]
    if use_custom:
        lon = (lon - custom_ayanamsa_value) % 360
    sign, sign_deg, nak, pada = _sign_and_nakshatra(lon, want_nakshatra=True)
    return BodyPosition(
        name=body, longitude=lon, latitude=lat, distance=dist,
        speed_long=speed_lon, retrograde=speed_lon < 0,
        sign=sign, sign_deg=sign_deg, nakshatra=nak, nakshatra_pada=pada,
    )


def get_planetary_nodes(
    jd_ut: float,
    body: str,
    frame: str = "helio",       # "geo" or "helio"
    zodiac: str = "tropical",
    ayanamsa: str = "lahiri",
    method: str = "mean",       # "mean" or "osculating"
    custom_ayanamsa_value: Optional[float] = None,
) -> NodePosition:
    """Get ascending/descending orbital nodes for Mercury-Pluto."""
    if body not in NODE_CAPABLE_PLANETS:
        raise ValueError(f"{body} has no defined orbital node (only Mercury-Pluto)")

    use_custom = zodiac == "sidereal" and ayanamsa == "custom"
    if use_custom and custom_ayanamsa_value is None:
        raise ValueError("custom_ayanamsa_value is required when ayanamsa='custom'")

    planet_id = NODE_CAPABLE_PLANETS[body]
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    if frame == "helio":
        flags |= swe.FLG_HELCTR
    if zodiac == "sidereal" and not use_custom:
        swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
        flags |= swe.FLG_SIDEREAL
    # use_custom deliberately leaves flags tropical - manual offset applied
    # below, same convention as get_planet_position's custom-ayanamsha handling

    method_flag = swe.NODBIT_MEAN if method == "mean" else swe.NODBIT_OSCU
    xnasc, xndsc, _xperi, _xaphe = swe.nod_aps(jd_ut, planet_id, method_flag, flags)

    asc_lon, desc_lon = xnasc[0], xndsc[0]
    if use_custom:
        asc_lon = (asc_lon - custom_ayanamsa_value) % 360
        desc_lon = (desc_lon - custom_ayanamsa_value) % 360

    sign_asc, asc_deg, asc_nak, asc_pada = _sign_and_nakshatra(asc_lon, want_nakshatra=True)
    sign_desc, desc_deg, desc_nak, desc_pada = _sign_and_nakshatra(desc_lon, want_nakshatra=True)

    return NodePosition(
        body=body, frame=frame,
        ascending_longitude=asc_lon, descending_longitude=desc_lon,
        sign_asc=sign_asc, sign_desc=sign_desc,
        asc_sign_degree=asc_deg, desc_sign_degree=desc_deg,
        asc_nakshatra=asc_nak, asc_nakshatra_pada=asc_pada,
        desc_nakshatra=desc_nak, desc_nakshatra_pada=desc_pada,
    )


def get_planet_full_position(
    jd_ut: float,
    body: str,
    lat: float,
    lon: float,
    elevation: float = 0,
    zodiac: str = "sidereal",
    ayanamsa: str = "lahiri",
    custom_ayanamsa_value: Optional[float] = None,
) -> dict:
    """
    Extended position data for a research/data-table view: ecliptic
    longitude/latitude, distance, speed, equatorial declination/right
    ascension, and horizon altitude/azimuth as seen from a given location.
    """
    base = get_planet_position(jd_ut, body, zodiac=zodiac, ayanamsa=ayanamsa,
                                custom_ayanamsa_value=custom_ayanamsa_value)

    # Equatorial coordinates (right ascension, declination) - needed for
    # declination and as input to the horizon (altitude/azimuth) transform
    flags_eq = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_EQUATORIAL
    if body == "rahu":
        eq_id = swe.TRUE_NODE
    elif body == "ketu":
        # Ketu = Rahu's equatorial position + 180 deg right ascension is NOT
        # simply additive in equatorial coords, so approximate via ecliptic
        # opposite point converted through the same call as Rahu, then flip.
        eq_id = swe.TRUE_NODE
    else:
        eq_id = PLANETS[body]

    xx_eq, _ = swe.calc_ut(jd_ut, eq_id, flags_eq)
    right_ascension, declination = xx_eq[0], xx_eq[1]
    if body == "ketu":
        right_ascension = (right_ascension + 180) % 360
        declination = -declination

    # Horizon coordinates (altitude/azimuth) as seen from the given location
    geopos = (lon, lat, elevation)
    azimuth, true_alt, apparent_alt = swe.azalt(
        jd_ut, swe.EQU2HOR, geopos, 0, 0, (right_ascension, declination, base.distance)
    )

    return {
        "name": body,
        "longitude": round(base.longitude, 4),
        "latitude": round(base.latitude, 4),
        "distance_au": round(base.distance, 6),
        "speed_deg_per_day": round(base.speed_long, 4),
        "retrograde": base.retrograde,
        "sign": base.sign,
        "sign_degree": round(base.sign_deg, 2),
        "nakshatra": base.nakshatra,
        "nakshatra_pada": base.nakshatra_pada,
        "right_ascension": round(right_ascension, 4),
        "declination": round(declination, 4),
        "azimuth": round(azimuth, 4),
        "altitude": round(true_alt, 4),
    }


if __name__ == "__main__":
    # quick manual sanity check
    swe.set_ephe_path(None)  # uses built-in Moshier if no data files present
    dt = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    jd = to_julian_day(dt)
    print(f"JD for {dt}: {jd}")

    for body in ["sun", "moon", "mars", "jupiter"]:
        pos = get_planet_position(jd, body, zodiac="sidereal")
        print(f"{body:10s} sidereal lon={pos.longitude:.4f} "
              f"sign={pos.sign} {pos.sign_deg:.2f}° "
              f"nakshatra={pos.nakshatra} pada={pos.nakshatra_pada} "
              f"retro={pos.retrograde}")

    rahu = get_planet_position(jd, "rahu", zodiac="sidereal")
    ketu = get_planet_position(jd, "ketu", zodiac="sidereal")
    print(f"{'rahu':10s} sidereal lon={rahu.longitude:.4f} sign={rahu.sign}")
    print(f"{'ketu':10s} sidereal lon={ketu.longitude:.4f} sign={ketu.sign}")

    node = get_planetary_nodes(jd, "mercury", frame="helio")
    print(f"Mercury helio node: asc={node.ascending_longitude:.4f} "
          f"({node.sign_asc}) desc={node.descending_longitude:.4f} ({node.sign_desc})")

    node_geo = get_planetary_nodes(jd, "mercury", frame="geo")
    print(f"Mercury geo node: asc={node_geo.ascending_longitude:.4f} "
          f"({node_geo.sign_asc}) desc={node_geo.descending_longitude:.4f} ({node_geo.sign_desc})")
