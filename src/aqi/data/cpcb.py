"""CPCB National AQI (India) from daily pollutant concentrations.

Breakpoints follow the CPCB National Air Quality Index (2014). Units: ug/m3, except CO in mg/m3.
PM2.5, PM10, NO2 and SO2 use 24-hour averages; CO and O3 use the day's maximum 8-hour average.
Above the top breakpoint ("Severe") the index is extrapolated linearly and capped at 500.

The overall AQI is the maximum sub-index, and is only reported when at least three pollutants
are available and one of them is PM2.5 or PM10 (CPCB rule).
"""

from __future__ import annotations

import math

# (concentration_low, concentration_high, index_low, index_high)
_BANDS: dict[str, list[tuple[float, float, int, int]]] = {
    "pm2_5": [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200), (90, 120, 201, 300),
              (120, 250, 301, 400), (250, 380, 401, 500)],
    "pm10": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 250, 101, 200), (250, 350, 201, 300),
             (350, 430, 301, 400), (430, 510, 401, 500)],
    "no2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 180, 101, 200), (180, 280, 201, 300),
            (280, 400, 301, 400), (400, 520, 401, 500)],
    "so2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 380, 101, 200), (380, 800, 201, 300),
            (800, 1600, 301, 400), (1600, 2400, 401, 500)],
    "co": [(0, 1.0, 0, 50), (1.0, 2.0, 51, 100), (2.0, 10, 101, 200), (10, 17, 201, 300),
           (17, 34, 301, 400), (34, 51, 401, 500)],
    "o3": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 168, 101, 200), (168, 208, 201, 300),
           (208, 748, 301, 400), (748, 1028, 401, 500)],
}  # fmt: skip

POLLUTANTS = tuple(_BANDS)

CATEGORIES = [
    (50, "Good"),
    (100, "Satisfactory"),
    (200, "Moderate"),
    (300, "Poor"),
    (400, "Very Poor"),
    (500, "Severe"),
]


def sub_index(pollutant: str, conc: float | None) -> float | None:
    """Sub-index for one pollutant, or None if the concentration is missing or negative."""
    if conc is None or (isinstance(conc, float) and math.isnan(conc)) or conc < 0:
        return None
    for c_lo, c_hi, i_lo, i_hi in _BANDS[pollutant]:
        if conc <= c_hi:
            return i_lo + (i_hi - i_lo) * (conc - c_lo) / (c_hi - c_lo)
    c_lo, c_hi, i_lo, i_hi = _BANDS[pollutant][-1]
    return min(500.0, i_lo + (i_hi - i_lo) * (conc - c_lo) / (c_hi - c_lo))


def aqi(
    concentrations: dict[str, float | None], pollutants: tuple[str, ...] = POLLUTANTS
) -> float | None:
    """Overall AQI from a {pollutant: concentration} dict, or None if CPCB rules aren't met."""
    subs = {p: sub_index(p, concentrations.get(p)) for p in pollutants}
    present = {p: s for p, s in subs.items() if s is not None}
    if len(present) < 3 or not ({"pm2_5", "pm10"} & present.keys()):
        return None
    return round(max(present.values()), 1)


def category(value: float | None) -> str | None:
    if value is None:
        return None
    for upper, name in CATEGORIES:
        if value <= upper:
            return name
    return "Severe"
