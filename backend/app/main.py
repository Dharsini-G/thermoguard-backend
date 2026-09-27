"""
ThermoGuard — FastAPI Backend
================================
Exposes ward risk data as REST endpoints for the dashboard to consume.

Run with:  uvicorn app.main:app --reload
Then open: http://127.0.0.1:8000/docs  for interactive API docs.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from collections import defaultdict
import time
import httpx

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.models.database import get_db, WardDB, RiskReadingDB, init_db
from app.services.ingestion import load_districts_from_csv, fetch_all_current_batch, fetch_forecast_weather
from app.services.mortality_predictor import predict_mortality_risk_multiplier
from app.services.vulnerability import calculate_vulnerability_index
from app.core.thermal_index import compute_thermal_index, WeatherInput

_cache = {"data": None, "timestamp": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern startup/shutdown context manager replacing deprecated @app.on_event."""
    init_db()
    yield


app = FastAPI(
    title="ThermoGuard API",
    description="Human Thermal Stress Index & Heat-Risk Early Warning System",
    lifespan=lifespan,
)

# Allow the React dashboard to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten before public production deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ThermoGuard API is running", "docs": "/docs"}


@app.get("/wards")
def list_wards(db: Session = Depends(get_db)):
    """Returns all monitored wards with static info + vulnerability data."""
    wards = db.query(WardDB).all()
    return [
        {
            "ward_id": w.ward_id,
            "ward_name": w.ward_name,
            "city": w.city,
            "lat": w.lat,
            "lon": w.lon,
            "elderly_pct": w.elderly_pct,
            "outdoor_worker_pct": w.outdoor_worker_pct,
            "slum_housing_pct": w.slum_housing_pct,
            "cooling_access_pct": w.cooling_access_pct,
        }
        for w in wards
    ]


@app.get("/wards/risk")
def get_live_risk(db: Session = Depends(get_db)):
    """
    Loads districts, fetches live weather batch, computes risk scores,
    persists a snapshot in the database, and caches the HTTP response for 5 minutes.
    """
    # 1. Return cached response if under 5 minutes old
    if _cache["data"] and (time.time() - _cache["timestamp"] < 300):
        return _cache["data"]

    districts = load_districts_from_csv()

    # 2. Fetch external weather data with fallback for rate limits
    try:
        snapshots = fetch_all_current_batch(districts)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            # Fall back to stale cache if available
            if _cache["data"]:
                return _cache["data"]
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Open-Meteo weather service rate limit exceeded. Please try again in a few minutes.",
            )
        raise exc

    snapshot_by_id = {s.ward_id: s for s in snapshots}
    results = []

    for ward in districts:
        snap = snapshot_by_id.get(ward.ward_id)
        if snap is None:
            continue

        weather_input = WeatherInput(
            temp_c=snap.temp_c,
            rh_pct=snap.rh_pct,
            wind_ms=snap.wind_ms,
            solar_wm2=snap.solar_wm2,
        )
        thermal = compute_thermal_index(weather_input)

        vuln_score = round(calculate_vulnerability_index(ward.ward_id) * 100, 1)
        final_score = round(0.65 * thermal.risk_score_0_100 + 0.35 * vuln_score, 1)

        mortality_multiplier = predict_mortality_risk_multiplier(
            wbgt_c=thermal.wbgt_c, duration_days=1, vulnerability_score=vuln_score
        )

        if final_score < 35:
            alert_level = "Safe"
        elif final_score < 55:
            alert_level = "Caution"
        elif final_score < 75:
            alert_level = "Danger"
        else:
            alert_level = "Extreme Danger"

        record = RiskReadingDB(
            ward_id=ward.ward_id,
            timestamp=datetime.now(timezone.utc),
            temp_c=snap.temp_c,
            rh_pct=snap.rh_pct,
            wind_ms=snap.wind_ms,
            solar_wm2=snap.solar_wm2,
            wbgt_c=thermal.wbgt_c,
            heat_index_c=thermal.heat_index_c,
            utci_approx_c=thermal.utci_approx_c,
            vulnerability_index=vuln_score,
            final_risk_score=final_score,
            alert_level=alert_level,
        )
        db.add(record)

        results.append({
            "ward_id": ward.ward_id,
            "ward_name": ward.ward_name,
            "city": ward.city,
            "lat": ward.lat,
            "lon": ward.lon,
            "timestamp": snap.timestamp,
            "temp_c": snap.temp_c,
            "rh_pct": snap.rh_pct,
            "wbgt_c": thermal.wbgt_c,
            "heat_index_c": thermal.heat_index_c,
            "vulnerability_index": vuln_score,
            "final_risk_score": final_score,
            "alert_level": alert_level,
            "mortality_risk_multiplier": mortality_multiplier,
        })

    db.commit()

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wards": results,
    }
    _cache["data"] = result
    _cache["timestamp"] = time.time()
    return result


@app.get("/wards/{ward_id}/forecast")
def get_ward_forecast(ward_id: str, days: int = 5):
    """
    Fetches hourly forecast weather for a ward and summarizes each day
    by its worst (highest-risk) hour.
    """
    districts = load_districts_from_csv()
    ward = next((w for w in districts if w.ward_id == ward_id), None)
    if ward is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{ward_id}' not found.",
        )

    vuln_score = round(calculate_vulnerability_index(ward.ward_id) * 100, 1)

    try:
        with httpx.Client() as client:
            hourly_snapshots = fetch_forecast_weather(ward, client, days=days)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Open-Meteo rate limit exceeded. Please wait a moment before trying again.",
            )
        raise exc

    by_day = defaultdict(list)
    for snap in hourly_snapshots:
        day_key = snap.timestamp.split("T")[0]
        by_day[day_key].append(snap)

    daily_summary = []
    for day_key, snaps in sorted(by_day.items()):
        worst_hour = None
        worst_score = -1

        for snap in snaps:
            weather_input = WeatherInput(
                temp_c=snap.temp_c,
                rh_pct=snap.rh_pct,
                wind_ms=snap.wind_ms,
                solar_wm2=snap.solar_wm2,
            )
            thermal = compute_thermal_index(weather_input)
            final_score = round(0.65 * thermal.risk_score_0_100 + 0.35 * vuln_score, 1)

            if final_score > worst_score:
                worst_score = final_score
                worst_hour = {
                    "time": snap.timestamp,
                    "temp_c": snap.temp_c,
                    "rh_pct": snap.rh_pct,
                    "wbgt_c": thermal.wbgt_c,
                    "final_risk_score": final_score,
                }

        if worst_score < 35:
            alert_level = "Safe"
        elif worst_score < 55:
            alert_level = "Caution"
        elif worst_score < 75:
            alert_level = "Danger"
        else:
            alert_level = "Extreme Danger"

        daily_summary.append({
            "date": day_key,
            "worst_hour": worst_hour,
            "day_alert_level": alert_level,
        })

    return {
        "ward_id": ward.ward_id,
        "ward_name": ward.ward_name,
        "vulnerability_index": vuln_score,
        "forecast_days": daily_summary,
    }


@app.get("/wards/{ward_id}/history")
def get_ward_history(ward_id: str, db: Session = Depends(get_db)):
    """Returns historical risk readings for a specific ward."""
    readings = (
        db.query(RiskReadingDB)
        .filter(RiskReadingDB.ward_id == ward_id)
        .order_by(RiskReadingDB.timestamp.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "temp_c": r.temp_c,
            "wbgt_c": r.wbgt_c,
            "final_risk_score": r.final_risk_score,
            "alert_level": r.alert_level,
        }
        for r in readings
    ]
