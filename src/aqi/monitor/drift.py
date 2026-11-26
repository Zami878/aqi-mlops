"""Drift and performance checks for the champion model.

Delhi's AQI is strongly seasonal, so comparing the last 30 days against the whole training set
would flag "drift" every winter. The reference is therefore season-matched: training-period days
covering the same calendar days in earlier years.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aqi.models import features, train

MONITORED = ["aqi", "pm2_5", "pm10", "no2", "co", "temp", "humidity", "wind"]
WINDOW_DAYS = 30
SEASON_MARGIN_DAYS = 0  # reference = the same calendar days in earlier years
PSI_BINS = 5  # 30 current samples -> ~6 per bin; more bins makes PSI mostly noise


def psi(reference: pd.Series, current: pd.Series, bins: int = PSI_BINS) -> float:
    """Population Stability Index of `current` against `reference` (quantile bins of reference).

    Counts get +0.5 smoothing so an empty bin in a small window doesn't dominate the score.
    """
    ref, cur = reference.dropna().to_numpy(), current.dropna().to_numpy()
    if len(ref) < bins or len(cur) == 0:
        return float("nan")
    inner = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1))[1:-1])
    n_bins = len(inner) + 1  # values below/above the reference range fall in the end bins
    ref_counts = np.bincount(np.digitize(ref, inner), minlength=n_bins) + 0.5
    cur_counts = np.bincount(np.digitize(cur, inner), minlength=n_bins) + 0.5
    ref_frac, cur_frac = ref_counts / ref_counts.sum(), cur_counts / cur_counts.sum()
    return round(float(np.sum((cur_frac - ref_frac) * np.log(cur_frac / ref_frac))), 4)


def seasonal_reference(history: pd.DataFrame, window: pd.DataFrame) -> pd.DataFrame:
    """Rows of `history` in the same part of the year as `window` (+- margin, wraps at year end)."""
    center = window.index[len(window) // 2].day_of_year
    half_width = len(window) // 2 + SEASON_MARGIN_DAYS
    dist = np.abs(history.index.day_of_year - center)
    dist = np.minimum(dist, 365 - dist)  # circular distance across 31 Dec / 1 Jan
    return history[dist <= half_width]


def drift(df: pd.DataFrame, train_end: str) -> dict[str, float]:
    window = df.tail(WINDOW_DAYS)
    history = df[df.index <= pd.Timestamp(train_end)]
    ref = seasonal_reference(history, window)
    return {col: psi(ref[col], window[col]) for col in MONITORED}


def performance(df: pd.DataFrame, model, train_end: str) -> dict:
    """Champion error on recent days it was not trained on (last WINDOW_DAYS, after train_end)."""
    frame = features.training_frame(df)
    frame = frame[frame.index > pd.Timestamp(train_end)].tail(WINDOW_DAYS)
    if frame.empty:
        return {"n": 0, "mae": None, "persistence_mae": None}
    m = train.metrics(frame[features.TARGET], train.predict(model, frame))
    p = train.metrics(frame[features.TARGET], frame["aqi_lag0"])
    return {"n": m["n"], "mae": m["mae"], "persistence_mae": p["mae"]}
