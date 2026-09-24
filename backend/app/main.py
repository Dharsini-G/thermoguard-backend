"""
ThermoGuard — FastAPI Backend
================================
Exposes ward risk data as REST endpoints for the dashboard to consume.

Run with:  uvicorn app.main:app --reload
Then open: http://127.0.0.1:8000/docs  for interactive API docs.
"""
from app.services.alerts import check_and_send_alerts
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
from app.services.mortality_predictor import predict_mortality_risk_multiplier
from app.models.database import get_db, WardDB, RiskReadingDB, init_db
from app.services.ingestion import load_districts_from_csv, fetch_all_current_batch, fetch_forecast_weather
import httpx
from collections import defaultdict
from app.services.vulnerability import calculate_vulnerability_index
from app.core.thermal_index import compute_thermal_index, WeatherInput

app = FastAPI(title="ThermoGuard API", description="Human Thermal Stress Index & Heat-Risk Early Warning System")

# Allow the React dashboard (running on a different port/domain) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real frontend URL before public deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"status": "ThermoGuard API is running", "docs": "/docs"}


@app.get("/wards")
def list_wards(db: Session = Depends(get_db)):
    """Returns all monitored wards with their static info + vulnerability data."""
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
    THE MAIN ENDPOINT for the dashboard.
    Loads all districts from the CSV, fetches live weather for ALL of them
    in a single batched API call, computes HTSI + vulnerability-adjusted
    risk for each, stores a snapshot in the DB, and returns the full
    result as JSON.
    """
    districts = load_districts_from_csv()
    snapshots = fetch_all_current_batch(districts)
    snapshot_by_id = {s.ward_id: s for s in snapshots}

    results = []
    for ward in districts:
        snap = snapshot_by_id.get(ward.ward_id)
        if snap is None:
            continue

        weather_input = WeatherInput(
            temp_c=snap.temp_c, rh_pct=snap.rh_pct,
            wind_ms=snap.wind_ms, solar_wm2=snap.solar_wm2,
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
            timestamp=datetime.utcnow(),
            temp_c=snap.temp_c, rh_pct=snap.rh_pct,
            wind_ms=snap.wind_ms, solar_wm2=snap.solar_wm2,
            wbgt_c=thermal.wbgt_c, heat_index_c=thermal.heat_index_c,
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

    alerts_sent = check_and_send_alerts(results)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "wards": results,
        "alerts_sent": alerts_sent
    }


@app.get("/wards/{ward_id}/forecast")
def get_ward_forecast(ward_id: str, days: int = 5):
    """
    THE 3-5 DAY EARLY WARNING ENDPOINT.
    Fetches hourly forecast weather for this ward N days ahead, runs EVERY
    hour through the exact same HTSI engine used for live data, then
    summarizes each day down to its single worst (highest-risk) hour.
    This is what lets us say "Day 3 from now will hit Danger level at 2 PM."
    """
    districts = load_districts_from_csv()
    ward = next((w for w in districts if w.ward_id == ward_id), None)
    if ward is None:
        return {"error": f"Ward '{ward_id}' not found."}

    vuln_score = round(calculate_vulnerability_index(ward.ward_id) * 100, 1)

    with httpx.Client() as client:
        hourly_snapshots = fetch_forecast_weather(ward, client, days=days)

    # Group hourly readings by calendar day, e.g. "2026-09-15"
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
                temp_c=snap.temp_c, rh_pct=snap.rh_pct,
                wind_ms=snap.wind_ms, solar_wm2=snap.solar_wm2,
            )
            thermal = compute_thermal_index(weather_input)
            final_score = round(0.65 * thermal.risk_score_0_100 + 0.35 * vuln_score, 1)
            mortality_multiplier = predict_mortality_risk_multiplier(
    wbgt_c=thermal.wbgt_c, duration_days=1, vulnerability_score=vuln_score
)

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
    """Returns historical risk readings for a specific ward (for trend charts)."""
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
