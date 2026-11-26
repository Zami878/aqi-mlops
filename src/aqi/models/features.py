"""Feature building for next-day AQI.

Row t holds only information known at the end of day t; the target is the AQI of day t+1.
Nothing here looks at values after day t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

POLLUTANT_COLS = ["pm2_5", "pm10", "no2", "so2", "co", "o3"]
WEATHER_COLS = ["temp", "humidity", "wind", "precip"]

FEATURES = [
    "aqi_lag0",
    "aqi_lag1",
    "aqi_lag2",
    "aqi_lag6",
    "aqi_roll3",
    "aqi_roll7",
    "pm2_5_diff1",
    *POLLUTANT_COLS,
    *WEATHER_COLS,
    "doy_sin",
    "doy_cos",
    "dow",
]

TARGET = "aqi_next"


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Return a frame with FEATURES and TARGET. TARGET is NaN on the last row."""
    out = pd.DataFrame(index=df.index)
    aqi = df["aqi"]
    out["aqi_lag0"] = aqi
    out["aqi_lag1"] = aqi.shift(1)
    out["aqi_lag2"] = aqi.shift(2)
    out["aqi_lag6"] = aqi.shift(6)
    out["aqi_roll3"] = aqi.rolling(3, min_periods=2).mean()
    out["aqi_roll7"] = aqi.rolling(7, min_periods=4).mean()
    out["pm2_5_diff1"] = df["pm2_5"].diff()
    for col in POLLUTANT_COLS + WEATHER_COLS:
        out[col] = df[col]
    doy = df.index.day_of_year
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["dow"] = df.index.day_of_week
    out[TARGET] = aqi.shift(-1)
    return out


def training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that have a target (drops the last day and any day whose next-day AQI is missing)."""
    return build(df).dropna(subset=[TARGET, "aqi_lag0"])


def time_split(frame: pd.DataFrame, holdout_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on everything before the last `holdout_days` rows, test on those rows. No shuffling."""
    if len(frame) <= holdout_days:
        raise ValueError(f"need more than {holdout_days} rows, got {len(frame)}")
    return frame.iloc[:-holdout_days], frame.iloc[-holdout_days:]
