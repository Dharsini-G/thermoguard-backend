from app.services.ingestion import fetch_all_current
from app.services.htsi_engine import evaluate_ward_health_risk

def run_pipeline():
    print("=" * 90)
    print("        USHNARAKSHA: LIVE WEATHER TO WARD-LEVEL MORTALITY & HEALTH RISK PIPELINE         ")
    print("=" * 90)
    
    # Ingest live data matching your WeatherSnapshot dataclass
    snapshots = fetch_all_current()
    
    print("\n--- Hyper-Local Ward Thermal Risk & Actionable Advisories ---")
    for s in snapshots:
        risk = evaluate_ward_health_risk(
            ward_id=s.ward_id,
            temp_c=s.temp_c,
            rh_pct=s.rh_pct,
            wind_ms=s.wind_ms,
            solar_wm2=s.solar_wm2
        )
        
        print(f"\nWard ID: {s.ward_id} ({s.timestamp})")
        print(f"  Live Met Data    : Temp={s.temp_c:.1f}°C | RH={s.rh_pct:.0f}% | Wind={s.wind_ms:.1f}m/s | Solar={s.solar_wm2:.0f}W/m²")
        print(f"  Calculated WBGT  : {risk['wbgt_c']}°C")
        print(f"  Vulnerability    : {risk['vulnerability_index']}")
        print(f"  FINAL RISK SCORE : [{risk['final_risk_score']} / 100] ---> ALERT LEVEL: {risk['alert_level']}")
        print(f"  Action Advisory  : {risk['advisory']}")

if __name__ == "__main__":
    run_pipeline()