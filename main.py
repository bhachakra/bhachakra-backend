"""
Bhachakra FastAPI backend.
Exposes REST endpoints over engine.py / panchanga.py / dasha.py.
"""
import swisseph as swe
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional

from engine import get_planet_position, get_planet_full_position, to_julian_day, PLANETS, ZODIAC_SIGNS
from panchanga import get_panchanga
from dasha import get_current_mahadasha, get_antardashas, DashaPeriod
from geocode import search_location, reverse_geocode
from houses import get_house_cusps, HOUSE_SYSTEMS
from aspects import compute_aspects, AspectPoint, DEFAULT_ORB, ASPECTING_BODIES
from pydantic import BaseModel
from supabase import Client
from vargas import compute_varga, VARGA_NAMES
from strength import compute_all as compute_strength, VIMSOPAKA_SCHEMES
from auth import get_current_user_id, get_supabase_client

app = FastAPI(title="Bhachakra API")

# Allow the Expo web dev server (and later, deployed frontend) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this once you have a real frontend domain
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default location: Mumbai
DEFAULT_LAT = 19.0760
DEFAULT_LON = 72.8777


def get_ascendant_sign(
    jd_ut: float, lat: float, lon: float, zodiac: str = "sidereal",
    ayanamsa: str = "lahiri", custom_ayanamsa_value: Optional[float] = None,
) -> tuple:
    """Returns (sign_number 1-12, exact_longitude 0-360)."""
    use_custom = zodiac == "sidereal" and ayanamsa == "custom"
    if use_custom and custom_ayanamsa_value is None:
        raise ValueError("custom_ayanamsa_value is required when ayanamsa='custom'")

    flags = 0
    if zodiac == "sidereal" and not use_custom:
        from engine import AYANAMSAS
        swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
        flags = swe.FLG_SIDEREAL
    # 'A' = Equal house system. The Ascendant itself doesn't depend on which
    # house system code is passed here (only the OTHER 11 cusps do), so any
    # valid code would return the same ascendant_longitude below.
    cusps, ascmc = swe.houses_ex(jd_ut, lat, lon, b'A', flags=flags)
    ascendant_longitude = ascmc[0]
    if use_custom:
        # houses_ex was computed tropically above (flags left at 0), so
        # apply the same manual ayanamsa subtraction used for planets
        ascendant_longitude = (ascendant_longitude - custom_ayanamsa_value) % 360
    sign_index = int(ascendant_longitude // 30)
    return sign_index + 1, ascendant_longitude  # sign is 1-indexed, 1 = Aries


PLANET_ABBR = {
    "sun": "Su", "moon": "Mo", "mercury": "Me", "venus": "Ve", "mars": "Ma",
    "jupiter": "Ju", "saturn": "Sa", "uranus": "Ur", "neptune": "Ne",
    "pluto": "Pl", "rahu": "Ra", "ketu": "Ke",
}

PLANET_SYMBOL = {
    "sun": "☉", "moon": "☽", "mercury": "☿", "venus": "♀", "mars": "♂",
    "jupiter": "♃", "saturn": "♄", "uranus": "♅", "neptune": "♆",
    "pluto": "♇", "rahu": "☊", "ketu": "☋",
}


@app.get("/positions")
def positions(
    date: str = Query(..., description="ISO date, e.g. 2026-07-25"),
    time: str = Query("12:00:00", description="Time in HH:MM:SS, UTC"),
    lat: float = Query(DEFAULT_LAT),
    lon: float = Query(DEFAULT_LON),
    zodiac: str = Query("sidereal", pattern="^(sidereal|tropical)$"),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(
        None, description="Degrees to subtract from tropical longitude; required when ayanamsa='custom'"
    ),
    varga: str = Query("d1", description="Divisional chart: d1, d2, d3, d4, d7, d9, d10, d12, d16, d20, d24, d27, d30, d40, d45, d60"),
):
    """
    Full planetary position snapshot for a given date/time/location -
    what the North Indian chart (and eventually other views) needs.
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")
    varga = varga.lower()
    if varga not in VARGA_NAMES:
        raise HTTPException(400, f"Unknown varga '{varga}'")

    dt_str = f"{date}T{time}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)

    bodies = list(PLANETS.keys()) + ["rahu", "ketu"]
    result_planets = []
    for body in bodies:
        pos = get_planet_position(jd, body, zodiac=zodiac, ayanamsa=ayanamsa,
                                   custom_ayanamsa_value=custom_ayanamsa_value)
        sign_index = ZODIAC_SIGNS.index(pos.sign) + 1  # 1-indexed
        d1_sign, d1_deg = sign_index, pos.sign_deg
        if varga != "d1":
            v = compute_varga(sign_index, pos.sign_deg, varga)
            sign_index, vdeg = v.sign, v.sign_degree
        else:
            vdeg = pos.sign_deg
        result_planets.append({
            "name": body,
            "abbr": PLANET_ABBR[body],
            "symbol": PLANET_SYMBOL[body],
            "sign": sign_index,
            "sign_name": ZODIAC_SIGNS[sign_index - 1],
            "longitude": round(pos.longitude, 4),  # always the real D1 longitude
            "sign_degree": round(vdeg, 2),
            "nakshatra": pos.nakshatra,
            "nakshatra_pada": pos.nakshatra_pada,
            "retrograde": pos.retrograde,
            "speed": round(pos.speed_long, 4),  # deg/day, for the stationary mark
            "d1_sign": d1_sign,
        })

    ascendant_sign, ascendant_longitude = get_ascendant_sign(jd, lat, lon, zodiac, ayanamsa, custom_ayanamsa_value)
    if varga != "d1":
        asc_v = compute_varga(ascendant_sign, ascendant_longitude % 30, varga)
        ascendant_sign = asc_v.sign

    return {
        "date": date,
        "time": time,
        "lat": lat,
        "lon": lon,
        "zodiac": zodiac,
        "ayanamsa": ayanamsa,
        "varga": varga,
        "custom_ayanamsa_value": custom_ayanamsa_value,
        "ascendant_sign": ascendant_sign,
        "ascendant_longitude": round(ascendant_longitude, 4),
        "planets": result_planets,
    }


@app.get("/panchanga")
def panchanga(
    date: str = Query(...),
    time: str = Query("12:00:00"),
    ayanamsa: str = Query("lahiri"),
    # Optional location: when given, vara is counted from sunrise there and
    # sunrise/sunset are returned. Without it, the old midnight-based vara.
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
):
    dt_str = f"{date}T{time}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)
    p = get_panchanga(jd, ayanamsa=ayanamsa, lat=lat, lon=lon)
    return {
        "date": date,
        "vara": p.vara,
        "tithi_number": p.tithi_number,
        "tithi_name": p.tithi_name,
        "paksha": p.paksha,
        "nakshatra": p.nakshatra,
        "nakshatra_pada": p.nakshatra_pada,
        "yoga": p.yoga,
        "karana": p.karana,
        "vara_basis": p.vara_basis,
        "sunrise": p.sunrise.isoformat().replace("+00:00", "Z") if p.sunrise else None,
        "sunset": p.sunset.isoformat().replace("+00:00", "Z") if p.sunset else None,
    }


@app.get("/dasha")
def dasha(
    date: str = Query(..., description="Birth/chart date, ISO, e.g. 1988-02-13"),
    time: str = Query("12:00:00", description="Birth/chart time HH:MM:SS, UTC"),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(None),
    on: Optional[str] = Query(None, description="ISO datetime (UTC) to mark as 'current'; defaults to now"),
):
    """
    Vimshottari dasha timeline for a chart moment (treated as the birth
    moment): all 9 mahadashas, each with its 9 antardashas, plus which
    mahadasha / antardasha / pratyantardasha is running on `on` (default now).
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")

    birth = datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=timezone.utc)
    jd = to_julian_day(birth)
    moon = get_planet_position(jd, "moon", zodiac="sidereal", ayanamsa=ayanamsa,
                               custom_ayanamsa_value=custom_ayanamsa_value)
    if on:
        now = datetime.fromisoformat(on.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    def pack(p: DashaPeriod):
        return {
            "lord": p.lord.lower(),
            "start": p.start.isoformat(),
            "end": p.end.isoformat(),
            "current": p.start <= now < p.end,
        }

    mahas = get_current_mahadasha(jd, moon.longitude, birth)
    out = []
    current = {"mahadasha": None, "antardasha": None, "pratyantardasha": None}
    for m in mahas:
        item = pack(m)
        antars = get_antardashas(m)
        item["antardashas"] = [pack(a) for a in antars]
        out.append(item)
        if item["current"]:
            current["mahadasha"] = pack(m)
            for a in antars:
                if a.start <= now < a.end:
                    current["antardasha"] = pack(a)
                    for pr in get_antardashas(a):
                        if pr.start <= now < pr.end:
                            current["pratyantardasha"] = pack(pr)
                            break
                    break

    return {
        "birth": birth.isoformat(),
        "on": now.isoformat(),
        "moon_longitude": round(moon.longitude, 4),
        "moon_nakshatra": moon.nakshatra,
        "mahadashas": out,
        "current": current,
    }


@app.get("/strength")
def strength_endpoint(
    date: str = Query(..., description="ISO date, e.g. 1988-02-12"),
    time: str = Query("12:00:00", description="Time in HH:MM:SS, UTC"),
    lat: float = Query(DEFAULT_LAT),
    lon: float = Query(DEFAULT_LON),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(None),
    scheme: str = Query("shodasavarga", description="Vimsopaka scheme: shadvarga, saptavarga, dasavarga, shodasavarga"),
):
    """
    Planetary strengths for the chart moment (sidereal, seven grahas):
    Ashtakavarga (BAV per planet + SAV), Vimsopaka Bala (chosen varga scheme)
    and Shadbala (six-fold strength, in virupas and rupas vs. the required minimum).
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")
    if scheme not in VIMSOPAKA_SCHEMES:
        raise HTTPException(400, f"Unknown scheme '{scheme}'")
    dt = datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)
    return compute_strength(jd, lat, lon, ayanamsa, custom_ayanamsa_value, scheme)


@app.get("/positions/detailed")
def positions_detailed(
    date: str = Query(..., description="ISO date, e.g. 2026-07-25"),
    time: str = Query("12:00:00"),
    lat: float = Query(DEFAULT_LAT),
    lon: float = Query(DEFAULT_LON),
    elevation: float = Query(0),
    zodiac: str = Query("sidereal", pattern="^(sidereal|tropical)$"),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(
        None, description="Degrees to subtract from tropical longitude; required when ayanamsa='custom'"
    ),
):
    """
    Full research-grade data table: longitude, latitude, distance, speed,
    declination, right ascension, altitude, azimuth - for every planet + nodes.
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")

    dt_str = f"{date}T{time}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)

    bodies = list(PLANETS.keys()) + ["rahu", "ketu"]
    rows = []
    for body in bodies:
        data = get_planet_full_position(jd, body, lat, lon, elevation, zodiac, ayanamsa,
                                         custom_ayanamsa_value=custom_ayanamsa_value)
        data["abbr"] = PLANET_ABBR[body]
        rows.append(data)

    return {
        "date": date,
        "time": time,
        "lat": lat,
        "lon": lon,
        "zodiac": zodiac,
        "planets": rows,
    }


@app.get("/houses")
def houses(
    date: str = Query(..., description="ISO date, e.g. 2026-07-25"),
    time: str = Query("12:00:00"),
    lat: float = Query(DEFAULT_LAT),
    lon: float = Query(DEFAULT_LON),
    zodiac: str = Query("sidereal", pattern="^(sidereal|tropical)$"),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(
        None, description="Degrees to subtract from tropical longitude; required when ayanamsa='custom'"
    ),
    house_system: str = Query("whole_sign", pattern="^(placidus|equal|whole_sign|sripati)$"),
):
    """
    House (bhava) cusps for the same date/time/location/ayanamsha used
    everywhere else. house_system picks the calculation method:
    - whole_sign: each house = one full sign (traditional Vedic default)
    - sripati: traditional Vedic Porphyry-based system (see houses.py for
      the Bhava Madhya vs Bhava Sandhi convention notes)
    - placidus / equal: standard Western systems
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")

    dt_str = f"{date}T{time}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)

    cusps = get_house_cusps(
        jd, lat, lon, house_system=house_system, zodiac=zodiac, ayanamsa=ayanamsa,
        custom_ayanamsa_value=custom_ayanamsa_value,
    )

    return {
        "date": date,
        "time": time,
        "lat": lat,
        "lon": lon,
        "zodiac": zodiac,
        "ayanamsa": ayanamsa,
        "house_system": house_system,
        "houses": [
            {
                "house": c.house,
                "longitude": c.longitude,
                "latitude": c.latitude,
                "sign": c.sign,
                "sign_degree": c.sign_degree,
                "nakshatra": c.nakshatra,
                "nakshatra_pada": c.nakshatra_pada,
                "right_ascension": c.right_ascension,
                "declination": c.declination,
                "azimuth": c.azimuth,
                "altitude": c.altitude,
            }
            for c in cusps
        ],
    }


@app.get("/aspects")
def aspects(
    date: str = Query(..., description="ISO date, e.g. 2026-07-25"),
    time: str = Query("12:00:00"),
    lat: float = Query(DEFAULT_LAT),
    lon: float = Query(DEFAULT_LON),
    zodiac: str = Query("sidereal", pattern="^(sidereal|tropical)$"),
    ayanamsa: str = Query("lahiri"),
    custom_ayanamsa_value: Optional[float] = Query(
        None, description="Degrees to subtract from tropical longitude; required when ayanamsa='custom'"
    ),
    house_system: str = Query("whole_sign", pattern="^(placidus|equal|whole_sign|sripati)$"),
    aspect_system: str = Query("western", pattern="^(western|vedic)$"),
    orb_sun: float = Query(DEFAULT_ORB),
    orb_moon: float = Query(DEFAULT_ORB),
    orb_mercury: float = Query(DEFAULT_ORB),
    orb_venus: float = Query(DEFAULT_ORB),
    orb_mars: float = Query(DEFAULT_ORB),
    orb_jupiter: float = Query(DEFAULT_ORB),
    orb_saturn: float = Query(DEFAULT_ORB),
    orb_uranus: float = Query(DEFAULT_ORB),
    orb_neptune: float = Query(DEFAULT_ORB),
    orb_pluto: float = Query(DEFAULT_ORB),
    orb_rahu: float = Query(DEFAULT_ORB),
    orb_ketu: float = Query(DEFAULT_ORB),
):
    """
    Aspects between planets, and between planets and house cusps.
    aspect_system="western": the 5 Ptolemaic aspects, mutual, orb-based.
    aspect_system="vedic": Parashari graha drishti, directional, orb-based
    (see aspects.py for the exact convention used, including the
    documented Rahu/Ketu assumption).
    Each planet's orb only applies when THAT planet is doing the aspecting -
    house cusps have no orb of their own, matching standard practice.
    """
    if ayanamsa == "custom" and custom_ayanamsa_value is None:
        raise HTTPException(400, "custom_ayanamsa_value is required when ayanamsa='custom'")

    dt_str = f"{date}T{time}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    jd = to_julian_day(dt)

    orbs = {
        "sun": orb_sun, "moon": orb_moon, "mercury": orb_mercury, "venus": orb_venus,
        "mars": orb_mars, "jupiter": orb_jupiter, "saturn": orb_saturn, "uranus": orb_uranus,
        "neptune": orb_neptune, "pluto": orb_pluto, "rahu": orb_rahu, "ketu": orb_ketu,
    }

    points = []
    for body in list(PLANETS.keys()) + ["rahu", "ketu"]:
        pos = get_planet_position(jd, body, zodiac=zodiac, ayanamsa=ayanamsa,
                                   custom_ayanamsa_value=custom_ayanamsa_value)
        points.append(AspectPoint(name=body, kind="planet", longitude=pos.longitude, label=PLANET_ABBR[body],
                                   speed=pos.speed_long))

    cusps = get_house_cusps(jd, lat, lon, house_system=house_system, zodiac=zodiac, ayanamsa=ayanamsa,
                             custom_ayanamsa_value=custom_ayanamsa_value)
    for c in cusps:
        points.append(AspectPoint(name=f"house_{c.house}", kind="house", longitude=c.longitude,
                                   label=f"House {c.house}"))

    result_aspects = compute_aspects(points, orbs, system=aspect_system)

    return {
        "date": date,
        "time": time,
        "aspect_system": aspect_system,
        "house_system": house_system,
        "aspects": [
            {
                "from": a.from_name,
                "from_label": a.from_label,
                "to": a.to_name,
                "to_label": a.to_label,
                "to_kind": a.to_kind,
                "aspect_type": a.aspect_type,
                "symbol": a.symbol,
                "exact_angle": a.exact_angle,
                "orb_used": a.orb_used,
                "applying": a.applying,
            }
            for a in result_aspects
        ],
    }


@app.get("/reverse-geocode")
def reverse_geocode_endpoint(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """
    Approximate place name for a lat/lon - the mirror of /geocode. Tries
    live reverse geocoding first, falls back to nearest-city-by-distance
    in the offline dataset. The offline result includes distance_km so the
    frontend can judge whether "near X" is still a fair thing to say for
    genuinely remote coordinates (open ocean, polar regions, etc.).
    """
    return reverse_geocode(lat, lon)


@app.get("/geocode")
def geocode(
    query: str = Query(..., min_length=2, description="Place name to search, e.g. 'Mumbai' or 'Pune'"),
    limit: int = Query(10, ge=1, le=25),
):
    """
    Location search for birth-chart lat/lon lookups. Tries live geocoding
    first (worldwide coverage); transparently falls back to a bundled
    offline city database if there's no internet or the live call fails.
    The response includes which source actually answered, so the frontend
    can show a small "offline results" indicator if it wants to.
    """
    return search_location(query, limit=limit)


class SavedChartIn(BaseModel):
    """Matches ChartsContext.tsx's existing addSavedChart() payload shape
    exactly, so the frontend rewrite only needs to change WHERE this data
    goes (this endpoint instead of AsyncStorage), not its shape."""
    name: str
    dateTimeIso: str
    lat: float
    lon: float
    locationName: str


@app.get("/charts")
def list_charts(user_id: str = Depends(get_current_user_id), db: Client = Depends(get_supabase_client)):
    """
    All of the logged-in user's saved charts, newest first. Row Level
    Security on the saved_charts table means this query physically cannot
    return another user's rows, even if this code had a bug - the
    database itself enforces the boundary, not just this endpoint's logic.
    """
    result = db.table("saved_charts").select("*").order("created_at", desc=True).execute()
    return result.data


@app.post("/charts")
def save_chart(chart: SavedChartIn, user_id: str = Depends(get_current_user_id), db: Client = Depends(get_supabase_client)):
    """Saves a new chart for the logged-in user."""
    result = db.table("saved_charts").insert({
        "user_id": user_id,
        "name": chart.name,
        "date_time_iso": chart.dateTimeIso,
        "lat": chart.lat,
        "lon": chart.lon,
        "location_name": chart.locationName,
    }).execute()
    return result.data[0]


@app.delete("/charts/{chart_id}")
def delete_chart(chart_id: str, user_id: str = Depends(get_current_user_id), db: Client = Depends(get_supabase_client)):
    """
    Deletes one saved chart. No need to manually check chart_id belongs to
    this user before deleting - the RLS delete policy already restricts
    this to rows where user_id matches the caller, so attempting to
    delete someone else's chart id simply deletes zero rows rather than
    needing a manual ownership check here.
    """
    db.table("saved_charts").delete().eq("id", chart_id).execute()
    return {"status": "deleted"}


@app.get("/health")
def health():
    return {"status": "ok"}
