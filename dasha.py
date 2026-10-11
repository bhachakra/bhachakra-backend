"""
Bhachakra dasha module.
Computes Vimshottari dasha periods - the most widely used Vedic
planetary time-period system, based on Moon's nakshatra at a given moment.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from engine import get_planet_position, to_julian_day, NAKSHATRAS

# Vimshottari dasha: 120-year cycle split among 9 planets (grahas),
# each nakshatra ruled by one planet in a fixed repeating sequence.
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}

# The 27 nakshatras cycle through these 9 lords repeatedly (27 / 9 = 3 full cycles)
DASHA_LORD_SEQUENCE = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
]

TOTAL_CYCLE_YEARS = sum(DASHA_YEARS.values())  # 120
YEAR_DAYS = 365.2425  # Gregorian mean year, standard convention for dasha math


@dataclass
class DashaPeriod:
    lord: str
    start: datetime
    end: datetime
    level: str  # "mahadasha" or "antardasha"


def _nakshatra_lord(nakshatra_index: int) -> str:
    return DASHA_LORD_SEQUENCE[nakshatra_index % 9]


def get_current_mahadasha(jd_ut: float, birth_moon_longitude: float = None,
                            reference_dt: datetime = None) -> list:
    """
    Compute the full Vimshottari mahadasha sequence starting from a given
    Moon longitude (typically at birth). Returns all 9 mahadasha periods
    across the 120-year cycle starting at reference_dt.

    If birth_moon_longitude is None, uses the Moon position at jd_ut itself
    (useful for a generic "dasha starting today" demo, not real birth-chart use).
    """
    if reference_dt is None:
        raise ValueError("reference_dt (start date, e.g. birth datetime) is required")

    if birth_moon_longitude is None:
        moon = get_planet_position(jd_ut, "moon", zodiac="sidereal")
        birth_moon_longitude = moon.longitude

    nak_span = 360 / 27  # 13°20'
    nak_index = int(birth_moon_longitude // nak_span)
    position_in_nak = (birth_moon_longitude % nak_span) / nak_span  # 0.0-1.0, how far through

    starting_lord_index = nak_index % 9
    starting_lord = DASHA_LORD_SEQUENCE[starting_lord_index]

    # Balance of the starting dasha already "used up" at birth
    full_dasha_years = DASHA_YEARS[starting_lord]
    elapsed_years = position_in_nak * full_dasha_years
    remaining_years = full_dasha_years - elapsed_years

    periods = []
    cursor = reference_dt
    # first (partial) dasha
    end = cursor + timedelta(days=remaining_years * YEAR_DAYS)
    periods.append(DashaPeriod(starting_lord, cursor, end, "mahadasha"))
    cursor = end

    # remaining 8 dashas in sequence, full length, until 120-year cycle completes
    idx = (starting_lord_index + 1) % 9
    for _ in range(8):
        lord = DASHA_LORD_SEQUENCE[idx]
        years = DASHA_YEARS[lord]
        end = cursor + timedelta(days=years * YEAR_DAYS)
        periods.append(DashaPeriod(lord, cursor, end, "mahadasha"))
        cursor = end
        idx = (idx + 1) % 9

    return periods


def get_antardashas(mahadasha: DashaPeriod) -> list:
    """
    Sub-periods within a mahadasha, proportional to each planet's dasha years
    within the 120-year cycle. Same 9-planet sequence, starting with the
    mahadasha's own lord.
    """
    maha_years = DASHA_YEARS[mahadasha.lord]
    maha_days = (mahadasha.end - mahadasha.start).days

    start_idx = DASHA_LORD_SEQUENCE.index(mahadasha.lord)
    periods = []
    cursor = mahadasha.start
    for i in range(9):
        lord = DASHA_LORD_SEQUENCE[(start_idx + i) % 9]
        # proportional share of this antardasha within the mahadasha
        share_days = maha_days * (DASHA_YEARS[lord] / TOTAL_CYCLE_YEARS)
        end = cursor + timedelta(days=share_days)
        periods.append(DashaPeriod(lord, cursor, end, "antardasha"))
        cursor = end

    return periods


def get_dasha_at_date(jd_ut_birth: float, target_dt: datetime,
                        birth_moon_longitude: float = None,
                        birth_dt: datetime = None) -> dict:
    """
    Convenience function: given a birth JD + Moon longitude, find which
    mahadasha and antardasha are active at target_dt.
    """
    mahadashas = get_current_mahadasha(jd_ut_birth, birth_moon_longitude, birth_dt)
    for maha in mahadashas:
        if maha.start <= target_dt < maha.end:
            antardashas = get_antardashas(maha)
            for antar in antardashas:
                if antar.start <= target_dt < antar.end:
                    return {"mahadasha": maha, "antardasha": antar}
            return {"mahadasha": maha, "antardasha": None}
    return {"mahadasha": None, "antardasha": None}


if __name__ == "__main__":
    from datetime import timezone
    # Example: birth on Jan 1, 2000, using Moon position at that moment
    birth_dt = datetime(2000, 1, 1, 6, 0, tzinfo=timezone.utc)
    birth_jd = to_julian_day(birth_dt)
    moon = get_planet_position(birth_jd, "moon", zodiac="sidereal")
    print(f"Birth Moon: {moon.longitude:.4f} ({moon.sign}, {moon.nakshatra})")

    mahadashas = get_current_mahadasha(birth_jd, moon.longitude, birth_dt)
    print("\nMahadasha sequence from birth:")
    for m in mahadashas:
        print(f"  {m.lord:8s} {m.start.date()} -> {m.end.date()}")

    today = datetime(2026, 7, 25, tzinfo=timezone.utc)
    result = get_dasha_at_date(birth_jd, today, moon.longitude, birth_dt)
    print(f"\nActive on {today.date()}:")
    print(f"  Mahadasha: {result['mahadasha'].lord}")
    print(f"  Antardasha: {result['antardasha'].lord}")
