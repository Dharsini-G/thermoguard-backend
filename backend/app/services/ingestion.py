"""
UshnaRaksha Ingestion Layer — Weather Data Fetcher
=====================================================
Pulls current + 5-day forecast weather (temp, RH, wind, solar radiation)
from Open-Meteo — a completely FREE, no-API-key-required weather API.
https://open-meteo.com/

This feeds directly into thermal_index.py's compute_thermal_index().
"""

import httpx
import csv
import os
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


@dataclass
class Ward:
    """A ward/zone we're monitoring. Lat/lon = centroid of the ward."""
    ward_id: str
    ward_name: str
    city: str
    lat: float
    lon: float


@dataclass
class WeatherSnapshot:
    ward_id: str
    timestamp: str
    temp_c: float
    rh_pct: float
    wind_ms: float
    solar_wm2: float


# --- Sample wards for demo (replace with real ward centroids later) ---
DEMO_WARDS: List[Ward] = [
    Ward("CHN-01", "Chennai - T.Nagar", "Chennai", 13.0418, 80.2341),
    Ward("CHN-02", "Chennai - Perambur", "Chennai", 13.1143, 80.2329),
    Ward("DEL-01", "Delhi - Najafgarh", "Delhi", 28.6092, 76.9800),
    Ward("NAG-01", "Nagpur - Sitabuldi", "Nagpur", 21.1466, 79.0849),
    Ward("MUM-01", "Mumbai - Dharavi", "Mumbai", 19.0410, 72.8570),
]


def fetch_current_weather(ward: Ward, client: httpx.Client) -> WeatherSnapshot:
    """Fetch current weather for a single ward from Open-Meteo (free, no key)."""
    params = {
        "latitude": ward.lat,
        "longitude": ward.lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
        "timezone": "Asia/Kolkata",
    }
    resp = client.get(OPEN_METEO_BASE, params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    current = data["current"]

    return WeatherSnapshot(
        ward_id=ward.ward_id,
        timestamp=current["time"],
        temp_c=current["temperature_2m"],
        rh_pct=current["relative_humidity_2m"],
        wind_ms=current["wind_speed_10m"] / 3.6,  # Open-Meteo returns km/h -> convert to m/s
        solar_wm2=current.get("shortwave_radiation", 0.0) or 0.0,
    )


def fetch_forecast_weather(ward: Ward, client: httpx.Client, days: int = 5) -> List[WeatherSnapshot]:
    """Fetch hourly forecast for the next N days (used for the 3-5 day early warning)."""
    params = {
        "latitude": ward.lat,
        "longitude": ward.lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
        "forecast_days": days,
        "timezone": "Asia/Kolkata",
    }
    resp = client.get(OPEN_METEO_BASE, params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    hourly = data["hourly"]

    snapshots = []
    for i, t in enumerate(hourly["time"]):
        snapshots.append(WeatherSnapshot(
            ward_id=ward.ward_id,
            timestamp=t,
            temp_c=hourly["temperature_2m"][i],
            rh_pct=hourly["relative_humidity_2m"][i],
            wind_ms=hourly["wind_speed_10m"][i] / 3.6,
            solar_wm2=hourly["shortwave_radiation"][i] or 0.0,
        ))
    return snapshots


def fetch_all_current(wards: List[Ward] = DEMO_WARDS) -> List[WeatherSnapshot]:
    """Fetch current weather for all monitored wards in one batch."""
    results = []
    with httpx.Client() as client:
        for ward in wards:
            snap = fetch_current_weather(ward, client)
            results.append(snap)
    return results


# ---------------------------------------------------------------------------
# DISTRICT-LEVEL SCALING
# ---------------------------------------------------------------------------
# The 5 DEMO_WARDS above are just a minimal starter set. To cover India at
# district level (or, later, real ward level), load locations from a CSV
# instead. Point it at data/india_districts.csv (60 starter districts,
# one per state/UT) or swap in the full 766-district file later —
# no code changes needed either way.

DISTRICTS_CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "india_districts.csv"
)


def load_districts_from_csv(path: str = DISTRICTS_CSV_PATH) -> List[Ward]:
    """Load district/ward locations from a CSV with columns:
    district_id, district_name, state, lat, lon
    """
    wards = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wards.append(Ward(
                ward_id=row["district_id"],
                ward_name=row["district_name"],
                city=row["state"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
            ))
    return wards


def fetch_all_current_batch(wards: List[Ward]) -> List[WeatherSnapshot]:
    """
    Fetch current weather for MANY locations in a SINGLE API call, using
    Open-Meteo's multi-location support (comma-separated lat/lon lists).
    This is what makes scaling to 60, 200, or 766 districts still cheap
    and fast — one HTTP request regardless of how many locations.
    """
    if not wards:
        return []

    lat_str = ",".join(str(w.lat) for w in wards)
    lon_str = ",".join(str(w.lon) for w in wards)

    params = {
        "latitude": lat_str,
        "longitude": lon_str,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
        "timezone": "Asia/Kolkata",
    }

    with httpx.Client() as client:
        resp = client.get(OPEN_METEO_BASE, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    # When multiple locations are requested, Open-Meteo returns a JSON array
    # (one object per location, in the SAME ORDER as the input lat/lon lists).
    if isinstance(data, dict):
        data = [data]  # normalize single-location response to a list too

    results = []
    for ward, loc_data in zip(wards, data):
        current = loc_data["current"]
        results.append(WeatherSnapshot(
            ward_id=ward.ward_id,
            timestamp=current["time"],
            temp_c=current["temperature_2m"],
            rh_pct=current["relative_humidity_2m"],
            wind_ms=current["wind_speed_10m"] / 3.6,
            solar_wm2=current.get("shortwave_radiation", 0.0) or 0.0,
        ))
    return results


if __name__ == "__main__":
    districts = load_districts_from_csv()
    print(f"Loaded {len(districts)} districts from CSV. Fetching live weather "
          f"for all of them in ONE batch API call at {datetime.now()}...\n")
    snapshots = fetch_all_current_batch(districts)
    for s in snapshots:
        print(f"{s.ward_id:<8}{s.timestamp:<20}temp={s.temp_c:>5.1f}C  "
              f"RH={s.rh_pct:>4.0f}%  wind={s.wind_ms:>4.1f}m/s  solar={s.solar_wm2:>5.0f}W/m2")
