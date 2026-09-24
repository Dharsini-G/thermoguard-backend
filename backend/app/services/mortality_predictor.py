"""
ThermoGuard — Mortality Risk Predictor
==========================================
Loads the trained XGBoost model and provides a simple function to predict
mortality/hospitalization risk multiplier for use in the live API.
"""

import os
import joblib
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), "mortality_model.joblib")

_model = None  # lazy-loaded singleton so we don't reload the file every request


def _get_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Mortality model not found at {MODEL_PATH}. "
                f"Run train_mortality_model.py first."
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def predict_mortality_risk_multiplier(wbgt_c: float, duration_days: int, vulnerability_score: float) -> float:
    """
    Returns a predicted mortality/hospitalization risk multiplier.
    A value of 1.0 = baseline normal-day risk.
    A value of 2.5 = 2.5x the normal baseline mortality/hospitalization risk.

    duration_days = how many consecutive days this ward has been at
    Danger-or-above WBGT (pass 1 if unknown/first day).
    """
    model = _get_model()
    X = np.array([[wbgt_c, duration_days, vulnerability_score]])
    prediction = model.predict(X)[0]
    return round(float(prediction), 2)


if __name__ == "__main__":
    # Quick sanity check with realistic scenarios
    print("Scenario -> Predicted mortality risk multiplier")
    print(f"Mild day (WBGT 26, day 1, low vuln 20)   -> "
          f"{predict_mortality_risk_multiplier(26, 1, 20)}x")
    print(f"Danger (WBGT 32, day 1, mid vuln 50)      -> "
          f"{predict_mortality_risk_multiplier(32, 1, 50)}x")
    print(f"Extreme, prolonged (WBGT 36, day 5, high vuln 80) -> "
          f"{predict_mortality_risk_multiplier(36, 5, 80)}x")
