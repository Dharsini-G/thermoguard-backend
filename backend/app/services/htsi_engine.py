import math
from app.services.vulnerability import calculate_vulnerability_index

def compute_wbgt(temp_c: float, rh_pct: float, wind_ms: float, solar_wm2: float) -> float:
    """Calculates Outdoor Wet-Bulb Globe Temperature (WBGT)."""
    tw = (temp_c * math.atan(0.151977 * math.pow(rh_pct + 8.313659, 0.5)) +
          math.atan(temp_c + rh_pct) - math.atan(rh_pct - 1.676331) +
          0.00391838 * math.pow(rh_pct, 1.5) * math.atan(0.023101 * rh_pct) - 4.686035)
    
    tg = temp_c + (solar_wm2 / (15.0 + 5.0 * max(wind_ms, 0.1)))
    wbgt = (0.7 * tw) + (0.2 * tg) + (0.1 * temp_c)
    return round(wbgt, 2)

def evaluate_ward_health_risk(ward_id: str, temp_c: float, rh_pct: float, wind_ms: float, solar_wm2: float):
    wbgt = compute_wbgt(temp_c, rh_pct, wind_ms, solar_wm2)
    vuln_score = calculate_vulnerability_index(ward_id)
    
    physical_risk = max(0.0, min(100.0, ((wbgt - 20.0) / (38.0 - 20.0)) * 100.0))
    final_score = round((0.65 * physical_risk) + (0.35 * (vuln_score * 100.0)), 1)
    
    if final_score < 35.0:
        level, alert = "SAFE", "Low Heat Stress. Normal activity permitted."
    elif final_score < 55.0:
        level, alert = "CAUTION", "Moderate Risk. Provide hydration stations for outdoor labor."
    elif final_score < 75.0:
        level, alert = "DANGER", "High Risk! Restrict heavy labor (12PM-4PM). Open cooling centers."
    else:
        level, alert = "EXTREME DANGER", "Severe Hazard! Issue Red Alert & trigger hospital surge capacity."
        
    return {
        "ward_id": ward_id,
        "wbgt_c": wbgt,
        "vulnerability_index": vuln_score,
        "final_risk_score": final_score,
        "alert_level": level,
        "advisory": alert
    }