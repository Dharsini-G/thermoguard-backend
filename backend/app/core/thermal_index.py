"""
UshnaRaksha Core Engine — Human Thermal Stress Index (HTSI)
=============================================================
Computes WBGT (Wet-Bulb Globe Temperature), NWS Heat Index, and a
UTCI-approximation from standard meteorological inputs, then derives
a categorical + numeric physiological risk score.

All formulas here use PUBLICLY PUBLISHED equations (no proprietary /
paid API required) so the engine works entirely off free data sources
like Open-Meteo or IMD's public feeds.

References:
- WBGT (outdoor, no direct sensor): Australian Bureau of Meteorology
  approximation using Tw (natural wet bulb, approximated via psychrometric
  relations), Tg (black globe, approximated), Td (dry bulb).
- Simplified outdoor WBGT approximation (Liljegren et al. / ACSM-style):
      WBGT ≈ 0.7*Tw + 0.2*Tg + 0.1*Td
  Since we don't have direct Tw/Tg sensors, we derive Tw from T & RH via
  the Stull (2011) empirical formula, and approximate Tg from T + solar
  radiation loading.
- NWS Heat Index: Rothfusz regression (NOAA).
- UTCI: full UTCI is a 6th-order polynomial with ~100 terms; for an MVP
  we use a validated simplified UTCI approximation (Błażejczyk et al.)
  good enough for hackathon-grade demo accuracy. This is clearly labeled
  as an approximation, not the full UTCI polynomial, and documented as
  a known limitation / future improvement.
"""

import math
from dataclasses import dataclass
from enum import Enum


class RiskCategory(str, Enum):
    SAFE = "Safe"
    CAUTION = "Caution"
    DANGER = "Danger"
    EXTREME = "Extreme Danger"


@dataclass
class WeatherInput:
    temp_c: float          # dry-bulb air temperature, °C
    rh_pct: float           # relative humidity, %
    wind_ms: float           # wind speed, m/s
    solar_wm2: float = 0.0    # solar radiation, W/m^2 (0 if unknown / nighttime)


@dataclass
class ThermalIndexResult:
    temp_c: float
    rh_pct: float
    wet_bulb_c: float
    wbgt_c: float
    heat_index_c: float
    utci_approx_c: float
    risk_category: RiskCategory
    risk_score_0_100: float


def stull_wet_bulb(temp_c: float, rh_pct: float) -> float:
    """
    Stull (2011) empirical wet-bulb temperature approximation.
    Valid roughly for -20C to 50C, 5% to 99% RH — covers Indian heatwave range.
    """
    t = temp_c
    rh = rh_pct
    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return tw


def approx_globe_temp(temp_c: float, solar_wm2: float, wind_ms: float) -> float:
    """
    Approximate black globe temperature from air temp + solar loading + wind cooling.
    Simplified from Liljegren (2008) globe-temp model — good enough for MVP;
    swap in full radiative model later if higher accuracy is needed.
    """
    wind = max(wind_ms, 0.2)  # avoid div-by-zero / unrealistic stagnant air
    solar_gain = (solar_wm2 / 1000.0) * 8.0     # empirical scaling, W/m2 -> deg C gain
    wind_cooling = math.sqrt(wind) * 1.1
    tg = temp_c + solar_gain - wind_cooling
    return tg


def compute_wbgt(w: WeatherInput) -> tuple[float, float]:
    """Returns (wet_bulb_c, wbgt_c)."""
    tw = stull_wet_bulb(w.temp_c, w.rh_pct)
    tg = approx_globe_temp(w.temp_c, w.solar_wm2, w.wind_ms)
    wbgt = 0.7 * tw + 0.2 * tg + 0.1 * w.temp_c
    return tw, wbgt


def compute_heat_index_c(temp_c: float, rh_pct: float) -> float:
    """
    NOAA Rothfusz regression Heat Index, computed in Fahrenheit internally
    (per the official published formula) and converted back to Celsius.
    """
    t_f = temp_c * 9 / 5 + 32
    rh = rh_pct

    hi_f = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t_f ** 2
        - 0.05481717 * rh ** 2
        + 0.00122874 * t_f ** 2 * rh
        + 0.00085282 * t_f * rh ** 2
        - 0.00000199 * t_f ** 2 * rh ** 2
    )

    # NOAA low-temp/low-humidity simple formula fallback for edge cases
    simple_hi_f = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
    if (simple_hi_f + t_f) / 2 < 80:
        hi_f = simple_hi_f

    hi_c = (hi_f - 32) * 5 / 9
    return hi_c


def compute_utci_approx(temp_c: float, rh_pct: float, wind_ms: float) -> float:
    """
    Simplified UTCI approximation (not the full 6th-order polynomial).
    Based on Błażejczyk-style simplification combining temp, vapour pressure,
    and wind chill/cooling effect. Documented as an MVP approximation.
    """
    # Approximate water vapour pressure (hPa) from RH & temp (Magnus formula)
    es = 6.105 * math.exp((17.27 * temp_c) / (237.7 + temp_c))
    e = es * (rh_pct / 100.0)

    utci = (
        temp_c
        + 0.607 * e / 10.0        # humidity adds to perceived heat
        - 0.789 * math.sqrt(max(wind_ms, 0.1))  # wind cools perceived temp
        + 1.5
    )
    return utci


def classify_risk(wbgt_c: float) -> tuple[RiskCategory, float]:
    """
    Classify WBGT into risk category using thresholds adapted from
    ACSM / Indian Labour Bureau heat-stress occupational guidance,
    then map to a continuous 0-100 score for GIS choropleth shading.
    """
    if wbgt_c < 27.0:
        category = RiskCategory.SAFE
        score = max(0.0, (wbgt_c / 27.0) * 25.0)
    elif wbgt_c < 30.0:
        category = RiskCategory.CAUTION
        score = 25 + ((wbgt_c - 27.0) / 3.0) * 25.0
    elif wbgt_c < 33.0:
        category = RiskCategory.DANGER
        score = 50 + ((wbgt_c - 30.0) / 3.0) * 25.0
    else:
        category = RiskCategory.EXTREME
        score = min(100.0, 75 + ((wbgt_c - 33.0) / 5.0) * 25.0)

    return category, round(score, 1)


def compute_thermal_index(w: WeatherInput) -> ThermalIndexResult:
    """Main entry point: raw weather -> full HTSI result."""
    tw, wbgt = compute_wbgt(w)
    hi = compute_heat_index_c(w.temp_c, w.rh_pct)
    utci = compute_utci_approx(w.temp_c, w.rh_pct, w.wind_ms)
    category, score = classify_risk(wbgt)

    return ThermalIndexResult(
        temp_c=w.temp_c,
        rh_pct=w.rh_pct,
        wet_bulb_c=round(tw, 2),
        wbgt_c=round(wbgt, 2),
        heat_index_c=round(hi, 2),
        utci_approx_c=round(utci, 2),
        risk_category=category,
        risk_score_0_100=score,
    )


if __name__ == "__main__":
    # Quick self-test with realistic Indian heatwave scenarios
    scenarios = [
        ("Nagpur April - dry heat", WeatherInput(temp_c=44.0, rh_pct=18, wind_ms=3.0, solar_wm2=850)),
        ("Chennai May - humid heat", WeatherInput(temp_c=38.0, rh_pct=75, wind_ms=2.0, solar_wm2=700)),
        ("Delhi June - extreme", WeatherInput(temp_c=47.0, rh_pct=25, wind_ms=1.5, solar_wm2=900)),
        ("Mumbai monsoon-onset - humid", WeatherInput(temp_c=34.0, rh_pct=85, wind_ms=4.0, solar_wm2=500)),
        ("Coimbatore mild evening", WeatherInput(temp_c=29.0, rh_pct=60, wind_ms=2.5, solar_wm2=100)),
    ]

    print(f"{'Scenario':<30}{'Temp':>6}{'RH':>5}{'WBGT':>7}{'HI':>7}{'UTCI':>7}{'Risk':>10}{'Score':>7}")
    for name, w in scenarios:
        r = compute_thermal_index(w)
        print(
            f"{name:<30}{r.temp_c:>6.1f}{r.rh_pct:>5.0f}"
            f"{r.wbgt_c:>7.1f}{r.heat_index_c:>7.1f}{r.utci_approx_c:>7.1f}"
            f"{r.risk_category.value:>10}{r.risk_score_0_100:>7.1f}"
        )
