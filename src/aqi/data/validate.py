"""Data validation gate.

Two levels:
- errors: the dataset is unusable (schema, duplicate/unsorted dates, values outside physical
  limits, too many gaps). CI fails on any error.
- sensor faults: patterns in the recent window that look like a broken feed rather than real
  change (a stuck/flat-lined reading, negative or impossible values, a block of missing days).
  The monitor uses these to *block* retraining, so a faulty feed is never mistaken for drift.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

REQUIRED = ["pm2_5", "pm10", "no2", "so2", "co", "o3", "temp", "humidity", "wind", "precip", "aqi"]

# Physical plausibility limits (inclusive). CO in mg/m3, everything else ug/m3 or natural units.
LIMITS = {
    "pm2_5": (0, 1000),
    "pm10": (0, 2000),
    "no2": (0, 1000),
    "so2": (0, 2000),
    "co": (0, 50),
    "o3": (0, 1000),
    "temp": (-10, 55),
    "humidity": (0, 100),
    "wind": (0, 150),
    "precip": (0, 500),
    "aqi": (0, 500),
}

MAX_MISSING_FRACTION = 0.05
MAX_GAP_DAYS = 3
FLATLINE_DAYS = 4  # same value this many days in a row = stuck sensor
FLATLINE_COLUMNS = ["pm2_5", "pm10", "no2", "co"]


@dataclass
class Report:
    rows: int = 0
    start: str | None = None
    end: str | None = None
    errors: list[str] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok}


def _flatlines(s: pd.Series) -> int:
    """Longest run of identical consecutive non-null values."""
    s = s.dropna()
    if s.empty:
        return 0
    run_id = (s != s.shift()).cumsum()
    return int(s.groupby(run_id).size().max())


def find_faults(df: pd.DataFrame) -> list[str]:
    """Sensor-fault patterns in `df` (normally the most recent window)."""
    faults = []
    for col in FLATLINE_COLUMNS:
        if col in df:
            run = _flatlines(df[col])
            if run >= FLATLINE_DAYS:
                faults.append(f"{col}: flat-lined for {run} consecutive days")
    for col, (lo, hi) in LIMITS.items():
        if col in df:
            bad = int(((df[col] < lo) | (df[col] > hi)).sum())
            if bad:
                faults.append(f"{col}: {bad} values outside [{lo}, {hi}]")
    if "aqi" in df:
        missing = int(df["aqi"].isna().sum())
        if missing > MAX_GAP_DAYS:
            faults.append(f"aqi: {missing} missing days in window")
    return faults


def check_freshness(end: date, today: date, max_age_days: int) -> str | None:
    """Return a validation error when the newest available data is too old."""
    age = (today - end).days
    if age > max_age_days:
        return f"data is stale: newest day {end} is {age} days old (max {max_age_days})"
    return None


def validate(
    df: pd.DataFrame,
    recent_days: int = 30,
    max_age_days: int | None = None,
    today: date | None = None,
) -> Report:
    rep = Report(rows=len(df))
    if df.empty:
        rep.errors.append("dataset is empty")
        return rep
    rep.start, rep.end = str(df.index.min().date()), str(df.index.max().date())

    missing_cols = [c for c in REQUIRED if c not in df.columns]
    if missing_cols:
        rep.errors.append(f"missing columns: {missing_cols}")
        return rep

    if df.index.has_duplicates:
        rep.errors.append(f"{int(df.index.duplicated().sum())} duplicate dates")
    if not df.index.is_monotonic_increasing:
        rep.errors.append("dates are not sorted")

    gaps = df.index.to_series().diff().dt.days.dropna()
    if (gaps > MAX_GAP_DAYS).any():
        rep.errors.append(f"gap of {int(gaps.max())} days (max allowed {MAX_GAP_DAYS})")

    for col in REQUIRED:
        frac = float(df[col].isna().mean())
        if frac > MAX_MISSING_FRACTION:
            rep.errors.append(f"{col}: {frac:.1%} missing (max {MAX_MISSING_FRACTION:.0%})")
        lo, hi = LIMITS[col]
        bad = int(((df[col] < lo) | (df[col] > hi)).sum())
        if bad:
            rep.errors.append(f"{col}: {bad} values outside [{lo}, {hi}]")

    rep.faults = find_faults(df.tail(recent_days))
    if max_age_days is not None:
        newest = df.index.max()
        if not pd.isna(newest):
            freshness_error = check_freshness(
                newest.date(), today if today is not None else date.today(), max_age_days
            )
            if freshness_error is not None:
                rep.errors.append(freshness_error)
    return rep
