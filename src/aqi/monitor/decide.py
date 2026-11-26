"""Turn validation, drift and performance results into one decision.

Order matters: a sensor fault blocks retraining *before* anything else is considered, so a
broken feed can never trigger a retrain on bad data.

Retrain triggers:
- lost skill: on the last 30 days the champion has not seen, its MAE is no better than the
  persistence baseline on the *same* days. Comparing against persistence on the same window
  cancels out Delhi's seasonal swings in error; comparing against the original holdout MAE
  did not, and flagged nearly every winter in a backtest.
- model age: fallback so a model never goes stale silently.

Feature drift (PSI) is reported as a warning only. In a backtest on this data, 30-day feature
PSI exceeded 0.25 in almost every month because of ordinary year-to-year weather variation, so
on its own it is too noisy to trigger retraining.
"""

from __future__ import annotations

from datetime import date

PSI_WARN = 0.25  # common rule of thumb: >0.25 = significant shift
MIN_PERF_DAYS = 14
MAX_MODEL_AGE_DAYS = 180  # training data ends >=90 days before promotion (holdout), so ~90 in use

HEALTHY, RETRAIN, BLOCKED = "healthy", "retrain", "blocked_sensor_fault"


def decide(validation: dict, drift: dict, perf: dict, champion_meta: dict | None) -> dict:
    warnings = sorted(f for f, v in drift.items() if v == v and v >= PSI_WARN)
    base = {"drift_warnings": warnings}

    if validation["errors"] or validation["faults"]:
        return {**base, "decision": BLOCKED, "reasons": validation["errors"] + validation["faults"]}
    if champion_meta is None:
        return {**base, "decision": RETRAIN, "reasons": ["no champion model yet (bootstrap)"]}

    reasons = []
    if perf["n"] >= MIN_PERF_DAYS and perf["mae"] >= perf["persistence_mae"]:
        reasons.append(
            f"lost skill: recent MAE {perf['mae']} >= persistence MAE {perf['persistence_mae']} "
            f"over {perf['n']} unseen days"
        )
    data_end = date.fromisoformat(validation["end"])
    age = (data_end - date.fromisoformat(champion_meta["train_end"])).days
    if age > MAX_MODEL_AGE_DAYS:
        reasons.append(f"model age: training data ends {age} days back (max {MAX_MODEL_AGE_DAYS})")

    return {**base, "decision": RETRAIN if reasons else HEALTHY, "reasons": reasons}
