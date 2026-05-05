from __future__ import annotations
"""Weather enrichment for outdoor runs.

Parses GPS coordinates from Fitbit TCX files and fetches historical weather
from the Open-Meteo API (free, no API key required).
"""

import xml.etree.ElementTree as ET
from datetime import datetime

import requests


# TCX namespace used by Fitbit/Garmin
_TCX_NS = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}

# Open-Meteo historical weather API
_OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


def parse_tcx_first_point(tcx_xml: str) -> tuple[float, float] | None:
    """Parse TCX XML and return (latitude, longitude) of the first GPS trackpoint.

    Returns None if no GPS data is found in the file.
    """
    try:
        root = ET.fromstring(tcx_xml)
    except ET.ParseError:
        return None

    # Find first Trackpoint with a Position element
    for tp in root.iter("{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Trackpoint"):
        pos = tp.find(
            "tcx:Position", _TCX_NS
        ) or tp.find(
            "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Position"
        )
        if pos is None:
            continue

        lat_el = pos.find(
            "tcx:LatitudeDegrees", _TCX_NS
        ) or pos.find(
            "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}LatitudeDegrees"
        )
        lon_el = pos.find(
            "tcx:LongitudeDegrees", _TCX_NS
        ) or pos.find(
            "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}LongitudeDegrees"
        )

        if lat_el is not None and lon_el is not None:
            try:
                lat_text = (lat_el.text or "").strip()
                lon_text = (lon_el.text or "").strip()
                if lat_text and lon_text:
                    return (float(lat_text), float(lon_text))
            except (TypeError, ValueError):
                continue

    return None


# WMO Weather interpretation codes → precipitation type
_WMO_PRECIP = {
    0: None, 1: None, 2: None, 3: None,  # Clear / partly cloudy
    45: None, 48: None,  # Fog
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    56: "Freezing Drizzle", 57: "Freezing Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy Rain",
    66: "Freezing Rain", 67: "Freezing Rain",
    71: "Snow", 73: "Snow", 75: "Heavy Snow",
    77: "Snow Grains",
    80: "Rain Showers", 81: "Rain Showers", 82: "Heavy Rain Showers",
    85: "Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ Hail", 99: "Thunderstorm w/ Hail",
}


def _cloud_to_sky(cloud_cover_pct: float) -> str:
    """Convert cloud cover percentage to sky condition label."""
    if cloud_cover_pct < 20:
        return "Sunny"
    elif cloud_cover_pct < 50:
        return "Partly Cloudy"
    elif cloud_cover_pct < 80:
        return "Mostly Cloudy"
    else:
        return "Overcast"


def weather_icon(sky_condition: str, precip_type: str | None = None) -> str:
    """Return a weather emoji icon based on sky condition and precipitation."""
    if precip_type:
        p = precip_type.lower()
        if "thunder" in p:
            return "⛈️"
        if "snow" in p or "sleet" in p:
            return "🌨️"
        if "freezing" in p:
            return "🌨️"
        if "drizzle" in p:
            return "🌦️"
        if "rain" in p or "shower" in p:
            return "🌧️"
    sky = (sky_condition or "").lower()
    if "sunny" in sky or "clear" in sky:
        return "☀️"
    if "partly" in sky:
        return "⛅"
    if "mostly" in sky:
        return "🌥️"
    if "overcast" in sky:
        return "☁️"
    return "🌡️"


def reverse_geocode(lat: float, lon: float) -> str | None:
    """Reverse geocode lat/lon to a city name via OpenStreetMap Nominatim.

    Returns "City, ST" string or None on failure.
    """
    _US_STATES = {
        "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
        "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
        "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
        "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
        "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
        "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
        "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
        "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
        "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
        "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
        "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
        "Wisconsin": "WI", "Wyoming": "WY",
    }
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers={"User-Agent": "fitbit-training-tool/1.0"},
            timeout=5,
        )
        resp.raise_for_status()
        addr = resp.json().get("address", {})
        city = (addr.get("city") or addr.get("town") or addr.get("village")
                or addr.get("hamlet") or addr.get("suburb") or "")
        state = addr.get("state", "")
        state_abbr = _US_STATES.get(state, state)
        if city:
            return f"{city}, {state_abbr}" if state_abbr else city
    except Exception:
        pass
    return None


def fetch_run_weather(
    lat: float, lon: float,
    run_date: str,
    start_hour: int, end_hour: int,
) -> dict | None:
    """Fetch historical weather from Open-Meteo for a run's location and time window.

    Args:
        lat: Latitude of the run.
        lon: Longitude of the run.
        run_date: Date string (YYYY-MM-DD).
        start_hour: Start hour in UTC (0-23) of the run.
        end_hour: End hour in UTC (0-23) of the run (inclusive).

    Returns:
        Dict with avg_temp_f, total_precip_in, precip_type, sky_condition,
        cloud_cover_pct, raw_hourly, latitude, longitude. Returns None on error.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "start_date": run_date,
        "end_date": run_date,
        "hourly": "temperature_2m,precipitation,cloudcover,weathercode",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "timezone": "UTC",
    }

    try:
        resp = requests.get(_OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [!] Weather API error for {run_date}: {e}")
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precips = hourly.get("precipitation", [])
    clouds = hourly.get("cloudcover", [])
    codes = hourly.get("weathercode", [])

    if not times:
        return None

    # Filter to the run's time window
    run_temps = []
    run_precips = []
    run_clouds = []
    run_codes = []

    for i, t in enumerate(times):
        hour = int(t.split("T")[1].split(":")[0]) if "T" in t else i
        if start_hour <= hour <= end_hour:
            if i < len(temps) and temps[i] is not None:
                run_temps.append(temps[i])
            if i < len(precips) and precips[i] is not None:
                run_precips.append(precips[i])
            if i < len(clouds) and clouds[i] is not None:
                run_clouds.append(clouds[i])
            if i < len(codes) and codes[i] is not None:
                run_codes.append(codes[i])

    # Fall back to all-day data if time window filter yielded nothing
    if not run_temps:
        run_temps = [t for t in temps if t is not None]
        run_precips = [p for p in precips if p is not None]
        run_clouds = [c for c in clouds if c is not None]
        run_codes = [c for c in codes if c is not None]

    if not run_temps:
        return None

    avg_temp = sum(run_temps) / len(run_temps)
    total_precip = sum(run_precips) if run_precips else 0.0
    avg_cloud = sum(run_clouds) / len(run_clouds) if run_clouds else 0.0

    # Determine precipitation type from worst weather code during the run
    precip_type = None
    if run_codes:
        worst_code = max(run_codes)
        precip_type = _WMO_PRECIP.get(worst_code)

    return {
        "latitude": lat,
        "longitude": lon,
        "avg_temp_f": round(avg_temp, 1),
        "total_precip_in": round(total_precip, 3),
        "precip_type": precip_type,
        "sky_condition": _cloud_to_sky(avg_cloud),
        "cloud_cover_pct": round(avg_cloud, 1),
        "raw_hourly": {
            "temps": run_temps,
            "precips": run_precips,
            "clouds": run_clouds,
            "codes": run_codes,
        },
    }
