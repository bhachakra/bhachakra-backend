"""
Bhachakra panchanga module.
Computes the five "limbs" of the Vedic day: tithi, vara, nakshatra, yoga, karana.
Built on top of engine.py's Sun/Moon position data, plus Swiss Ephemeris
sunrise/sunset when a location is given (the Vedic day - and so the vara -
runs from one sunrise to the next, not midnight to midnight).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import swisseph as swe
from engine import get_planet_position, to_julian_day, NAKSHATRAS

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima/Amavasya",
]

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana",
    "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda",
    "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
    "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma",
    "Indra", "Vaidhriti",
]

KARANA_NAMES_FIXED = ["Shakuni", "Chatushpada", "Naga", "Kimstughna"]
KARANA_NAMES_REPEATING = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]

VARA_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@dataclass
class Panchanga:
    date: str
    vara: str
    tithi_number: int          # 1-30 (1-15 Shukla, 16-30 Krishna)
    tithi_name: str
    paksha: str                  # "Shukla" or "Krishna"
    nakshatra: str
    nakshatra_pada: int
    yoga: str
    karana: str
    sun_longitude: float
    moon_longitude: float
    # Set only when a location was given and the Sun actually rises/sets there
    # that day (it may not, near the poles). UTC.
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    # "sunrise": vara counted from the last sunrise (traditional);
    # "civil": fallback - weekday of the UTC calendar date (no location given,
    # or no sunrise that day)
    vara_basis: str = "civil"


# ---- sunrise / sunset ---------------------------------------------------------
# Standard sunrise: upper limb of the Sun on the horizon, with atmospheric
# refraction - the same convention most printed panchangs use. To use the
# centre of the disc instead, add swe.BIT_DISC_CENTER to the flags below.
_RISE = swe.CALC_RISE
_SET = swe.CALC_SET


def _next_event(jd_start: float, lat: float, lon: float, rsmi: int) -> Optional[float]:
    """Julian day (UT) of the next sunrise or sunset after jd_start, or None."""
    geopos = (lon, lat, 0.0)
    try:
        # pyswisseph >= 2.10: rise_trans(tjdut, body, rsmi, geopos, atpress, attemp, flags)
        res, tret = swe.rise_trans(jd_start, swe.SUN, rsmi, geopos, 0.0, 0.0, swe.FLG_SWIEPH)
    except TypeError:
        # older pyswisseph: rise_trans(tjdut, body, starname, epheflag, rsmi, geopos, atpress, attemp)
        res, tret = swe.rise_trans(jd_start, swe.SUN, "", swe.FLG_SWIEPH, rsmi, geopos, 0.0, 0.0)
    if res != 0:  # -2: Sun stays above/below the horizon (polar day/night)
        return None
    return tret[0]


def _vedic_day(jd_ut: float, lat: float, lon: float) -> Optional[Tuple[float, float]]:
    """(sunrise, sunset) of the Vedic day that contains jd_ut: the last sunrise
    at or before that moment, and the sunset after it."""
    first = _next_event(jd_ut - 1.5, lat, lon, _RISE)  # always <= jd_ut
    if first is None:
        return None
    second = _next_event(first + 0.01, lat, lon, _RISE)
    sunrise = second if second is not None and second <= jd_ut else first
    sunset = _next_event(sunrise + 0.01, lat, lon, _SET)
    if sunset is None:
        return None
    return sunrise, sunset


def _jd_to_utc(jd: float) -> datetime:
    y, m, d, h = swe.revjul(jd)
    # whole seconds: keeps the ISO strings simple for every JS engine to parse
    return (datetime(y, m, d, tzinfo=timezone.utc) + timedelta(hours=h)).replace(microsecond=0)


def get_panchanga(
    jd_ut: float,
    ayanamsa: str = "lahiri",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Panchanga:
    sun = get_planet_position(jd_ut, "sun", zodiac="sidereal", ayanamsa=ayanamsa)
    moon = get_planet_position(jd_ut, "moon", zodiac="sidereal", ayanamsa=ayanamsa)

    # --- Tithi: angular distance Moon-Sun, divided into 30 slices of 12 deg each
    diff = (moon.longitude - sun.longitude) % 360
    tithi_index = int(diff // 12)  # 0-29
    tithi_number = tithi_index + 1
    paksha = "Shukla" if tithi_index < 15 else "Krishna"
    tithi_in_paksha = tithi_index % 15
    tithi_name = TITHI_NAMES[tithi_in_paksha] if tithi_in_paksha < 14 else (
        "Purnima" if paksha == "Shukla" else "Amavasya"
    )

    # --- Nakshatra: already computed by engine for Moon
    nakshatra = moon.nakshatra
    pada = moon.nakshatra_pada

    # --- Yoga: sum of Sun + Moon longitudes, divided into 27 slices
    yoga_sum = (sun.longitude + moon.longitude) % 360
    yoga_index = int(yoga_sum // (360 / 27))
    yoga = YOGA_NAMES[yoga_index]

    # --- Karana: half-tithi, 60 slices of 6 deg each, cycling through 7 repeating
    #     + 4 fixed karanas at specific points in the lunar month
    karana_index = int(diff // 6)  # 0-59
    if karana_index == 0:
        karana = KARANA_NAMES_FIXED[3]   # Kimstughna - first half of Pratipada Shukla
    elif karana_index >= 57:
        karana = KARANA_NAMES_FIXED[karana_index - 57]  # last 3 karanas are fixed
    else:
        karana = KARANA_NAMES_REPEATING[(karana_index - 1) % 7]

    # --- Vara: the weekday of the Vedic day, which begins at sunrise. With a
    #     location, it is the weekday on which the last sunrise fell (in local
    #     mean time, longitude / 15 hours from UT) - so 02:00 on a Monday is
    #     still Sunday's vara until the Sun rises. Without one, fall back to the
    #     UTC calendar weekday. int(jd + 1.5) % 7 gives Sunday = 0.
    sunrise_dt = sunset_dt = None
    vara_basis = "civil"
    day = _vedic_day(jd_ut, lat, lon) if lat is not None and lon is not None else None
    if day is not None:
        sunrise_jd, sunset_jd = day
        vara_index = int(sunrise_jd + lon / 360.0 + 1.5) % 7
        sunrise_dt, sunset_dt = _jd_to_utc(sunrise_jd), _jd_to_utc(sunset_jd)
        vara_basis = "sunrise"
    else:
        vara_index = int(jd_ut + 1.5) % 7
    vara = VARA_NAMES[vara_index]

    return Panchanga(
        date=str(jd_ut),
        vara=vara,
        tithi_number=tithi_number,
        tithi_name=tithi_name,
        paksha=paksha,
        nakshatra=nakshatra,
        nakshatra_pada=pada,
        yoga=yoga,
        karana=karana,
        sun_longitude=sun.longitude,
        moon_longitude=moon.longitude,
        sunrise=sunrise_dt,
        sunset=sunset_dt,
        vara_basis=vara_basis,
    )


if __name__ == "__main__":
    from datetime import timezone
    dt = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    jd = to_julian_day(dt)
    p = get_panchanga(jd)
    print(f"Date: {dt.date()}")
    print(f"Vara: {p.vara}")
    print(f"Tithi: {p.tithi_name} ({p.paksha} paksha, #{p.tithi_number})")
    print(f"Nakshatra: {p.nakshatra} pada {p.nakshatra_pada}")
    print(f"Yoga: {p.yoga}")
    print(f"Karana: {p.karana}")
