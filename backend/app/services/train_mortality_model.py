"""
ThermoGuard — Mortality Risk Model Training
==============================================
Trains an XGBoost regressor to predict a "relative mortality/hospitalization
risk multiplier" from WBGT, heatwave duration, and vulnerability score.

IMPORTANT — HONESTY NOTE FOR YOUR REPORT/PRESENTATION:
This training data is SYNTHETIC — generated from published heat-mortality
relationship patterns found in NCDC/IJMR heatwave studies (mortality rises
non-linearly above ~30°C WBGT, and compounds with consecutive hot days and
higher vulnerability). We do NOT claim this is real hospital record data.
State this openly if asked — it's a scientifically-grounded illustrative
model, appropriate for an MVP, with real epidemiological data integration
listed as a clear next step.

Why synthetic data is a legitimate MVP choice: real ward-level hospital
mortality datasets linked to daily weather are not freely/publicly
downloadable in a ready-to-use form in the time available for a hackathon
prototype. Using a synthetic dataset built from published relationship
SHAPES (not invented numbers) lets us demonstrate the correct ML pipeline
architecture, ready to be retrained on real data the moment it's available.
"""

import numpy as np
import xgboost as xgb
import joblib
import os

np.random.seed(42)

N_SAMPLES = 5000


def generate_synthetic_training_data(n=N_SAMPLES):
    """
    Generates synthetic (WBGT, duration_days, vulnerability_score) -> 
    mortality_risk_multiplier training data, following published patterns:
    - Below ~28°C WBGT: baseline risk (multiplier ~1.0x)
    - 28-32°C WBGT: risk rises moderately
    - Above 32°C WBGT: risk rises sharply (non-linear, matches real heatwave
      mortality studies showing accelerating danger, not a straight line)
    - Longer consecutive heatwave duration compounds risk (documented in
      heat-mortality literature — day 4 of a heatwave is deadlier than day 1
      at the same temperature, due to cumulative physiological strain)
    - Higher vulnerability score amplifies the effect
    """
    wbgt = np.random.uniform(20, 40, n)
    duration_days = np.random.randint(1, 8, n)
    vulnerability = np.random.uniform(0, 100, n)

    # Base non-linear WBGT -> risk relationship (sigmoid-like acceleration above 30C)
    # IMPORTANT: clip to 0 BEFORE the fractional power, not after — raising a
    # negative number to a non-integer power (2.2) is mathematically undefined
    # and produces NaN, which is what caused the earlier XGBoost training error.
    base_risk = 1.0 + np.maximum(0, wbgt - 28) ** 2.2 * 0.015

    # Duration compounding effect (each extra day adds ~8% more risk)
    duration_multiplier = 1.0 + (duration_days - 1) * 0.08

    # Vulnerability amplification (0-100 scale -> 0% to +40% extra risk)
    vulnerability_multiplier = 1.0 + (vulnerability / 100) * 0.4

    # Combine with small random noise to simulate real-world variability
    mortality_risk_multiplier = (
        base_risk * duration_multiplier * vulnerability_multiplier
        + np.random.normal(0, 0.05, n)
    )
    mortality_risk_multiplier = np.clip(mortality_risk_multiplier, 1.0, 8.0)

    X = np.column_stack([wbgt, duration_days, vulnerability])
    y = mortality_risk_multiplier
    return X, y


def train_and_save_model(output_path="mortality_model.joblib"):
    X, y = generate_synthetic_training_data()

    # Simple train/test split
    split = int(len(X) * 0.85)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = xgb.XGBRegressor(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.08,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Quick validation check
    predictions = model.predict(X_test)
    mae = np.mean(np.abs(predictions - y_test))
    print(f"Model trained. Mean Absolute Error on test set: {mae:.3f} "
          f"(multiplier scale, e.g. 0.1 means predictions are off by ~0.1x on average)")

    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")
    return model


if __name__ == "__main__":
    train_and_save_model()