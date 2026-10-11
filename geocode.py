"""
Bhachakra geocoding module.

Location search for birth-chart lat/lon lookups. Tries a live geocoding API
(OpenStreetMap Nominatim) first, for worldwide coverage down to small towns
and specific addresses. Falls back to a bundled offline city database
(via the geonamescache package - ~34,000 cities worldwide, population 15,000+)
whenever the live call fails for any reason: no internet, timeout, rate
limiting, or a bad response. The frontend never needs to know which path
answered - both return the same shape.
"""
import geonamescache
import httpx

_gc = geonamescache.GeonamesCache()
_countries = _gc.get_countries()          # {countrycode: {name, ...}}
_cities = list(_gc.get_cities().values())  # loaded once at import time, ~34k entries

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_TIMEOUT_SECONDS = 3.0
# Nominatim's usage policy requires a descriptive User-Agent and asks for no
# more than ~1 request/second. This app is used interactively by one person
# at a time, so the rate stays naturally well under that on its own.
NOMINATIM_HEADERS = {"User-Agent": "Bhachakra/1.0 (personal astrology ephemeris app)"}

# Successful live lookups are cached for the life of the process, so
# re-searching the same city doesn't hit the network (or the offline
# fallback) again.
_live_cache: dict[str, list[dict]] = {}


def _matches_query(city: dict, query_lower: str) -> bool:
    if query_lower in city["name"].lower():
        return True
    return any(query_lower in alt.lower() for alt in city.get("alternatenames", []))


def _search_offline(query: str, limit: int) -> list[dict]:
    query_lower = query.strip().lower()
    if not query_lower:
        return []

    matches = [c for c in _cities if _matches_query(c, query_lower)]
    # Most populous first, so e.g. searching "Paris" surfaces Paris, France
    # ahead of smaller same-named towns elsewhere in the world.
    matches.sort(key=lambda c: c.get("population", 0), reverse=True)

    results = []
    for c in matches[:limit]:
        country_name = _countries.get(c["countrycode"], {}).get("name", c["countrycode"])
        results.append({
            "name": c["name"],
            "display_name": f"{c['name']}, {country_name}",
            "lat": float(c["latitude"]),
            "lon": float(c["longitude"]),
            "country": country_name,
        })
    return results


def _search_live(query: str, limit: int) -> list[dict] | None:
    """Returns None on ANY failure - that's the caller's signal to fall back."""
    if query in _live_cache:
        return _live_cache[query]

    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 1},
            headers=NOMINATIM_HEADERS,
            timeout=NOMINATIM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        # ValueError covers a non-JSON response body; httpx.HTTPError covers
        # no internet, timeout, DNS failure, and non-2xx status codes
        return None

    results = []
    for item in data:
        try:
            results.append({
                "name": item.get("name") or item.get("display_name", "").split(",")[0].strip(),
                "display_name": item.get("display_name", ""),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "country": item.get("address", {}).get("country"),
            })
        except (KeyError, ValueError):
            continue  # skip any malformed individual result rather than failing the whole search

    _live_cache[query] = results
    return results


def search_location(query: str, limit: int = 10) -> dict:
    """
    Returns {"results": [...], "source": "live" | "offline"}.
    Each result: {name, display_name, lat, lon, country}.
    """
    live_results = _search_live(query, limit)
    if live_results is not None:
        return {"results": live_results, "source": "live"}

    return {"results": _search_offline(query, limit), "source": "offline"}


# --- Reverse geocoding: lat/lon -> approximate place name ---

_reverse_live_cache: dict[tuple[float, float], dict | None] = {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0  # Earth radius, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _reverse_offline(lat: float, lon: float) -> dict | None:
    """Nearest city in the bundled dataset by great-circle distance - always
    returns SOME answer (there's no such thing as "no nearby city" globally),
    but the result may be very far away in genuinely remote locations
    (mid-ocean, polar regions), so the distance is included for the caller
    to judge whether "approximate" is still a fair word to use."""
    if not _cities:
        return None
    nearest = min(_cities, key=lambda c: _haversine_km(lat, lon, float(c["latitude"]), float(c["longitude"])))
    distance_km = _haversine_km(lat, lon, float(nearest["latitude"]), float(nearest["longitude"]))
    country_name = _countries.get(nearest["countrycode"], {}).get("name", nearest["countrycode"])
    return {
        "name": nearest["name"],
        "display_name": f"near {nearest['name']}, {country_name}",
        "country": country_name,
        "distance_km": round(distance_km, 1),
    }


def _reverse_live(lat: float, lon: float) -> dict | None:
    """Returns None on ANY failure - caller falls back to offline. Distinct
    from a successful-but-empty result, which Nominatim itself may return
    for genuinely remote coordinates (open ocean etc.) - that case is
    treated as a real (if sparse) answer, not a failure to fall back from."""
    key = (round(lat, 3), round(lon, 3))  # 3 decimals (~110m) is plenty for a rounded-to-arcminute UI anyway
    if key in _reverse_live_cache:
        return _reverse_live_cache[key]

    try:
        response = httpx.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1},
            headers=NOMINATIM_HEADERS,
            timeout=NOMINATIM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        item = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not item or "error" in item:
        result = None
    else:
        address = item.get("address", {})
        # Prefer the most specific reasonable place name available, falling
        # back through progressively broader fields
        place_name = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("county") or address.get("state") or item.get("display_name", "").split(",")[0]
        )
        result = {
            "name": place_name,
            "display_name": item.get("display_name", place_name),
            "country": address.get("country"),
            "distance_km": None,  # live result is the actual containing place, not a nearest-point estimate
        }

    _reverse_live_cache[key] = result
    return result


def reverse_geocode(lat: float, lon: float) -> dict:
    """Returns {"result": {...} | None, "source": "live" | "offline"}."""
    live_result = _reverse_live(lat, lon)
    if live_result is not None:
        return {"result": live_result, "source": "live"}

    return {"result": _reverse_offline(lat, lon), "source": "offline"}
