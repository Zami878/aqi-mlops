"""Download daily pollutant and weather data for Delhi and compute the CPCB AQI.

Source: Open-Meteo (no API key).
- Pollutants: CAMS atmospheric-composition model via the Open-Meteo Air Quality API. These are
  modelled concentrations for a central-Delhi grid point, not CPCB station measurements.
- Weather: Open-Meteo Historical Forecast API.

The AQI target leaves out ozone. On this data the modelled O3 sets the AQI on 58% of days and
pushes the monsoon-month average above 200, which disagrees with Delhi's observed clean monsoon.
O3 is still kept as a model feature. A CPCB station feed can replace this source behind the same
columns.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from aqi.data import cpcb

LAT, LON = 28.6139, 77.2090  # New Delhi
TZ = "Asia/Kolkata"
START = date(2022, 8, 5)  # first full day the CAMS series has values for this point

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

_HOURLY = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "sulphur_dioxide": "so2",
    "carbon_monoxide": "co",
    "ozone": "o3",
}
_DAILY_WX = {
    "temperature_2m_mean": "temp",
    "relative_humidity_2m_mean": "humidity",
    "wind_speed_10m_mean": "wind",
    "precipitation_sum": "precip",
}

# Pollutants that enter the AQI target (see module docstring for why O3 is left out).
TARGET_POLLUTANTS = ("pm2_5", "pm10", "no2", "so2", "co")

DEFAULT_PATH = Path("data/delhi_daily.csv")


def _get(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=60) as resp:
        return json.load(resp)


def daily_pollutants(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly concentrations to CPCB daily averaging periods.

    24h mean for PM2.5, PM10, NO2, SO2; max of the 8h rolling mean for CO and O3.
    CO is converted from ug/m3 to mg/m3. Days with fewer than 16 hourly values are dropped.
    """
    hourly = hourly.copy()
    hourly["co"] = hourly["co"] / 1000.0
    day = hourly.index.floor("D")
    out = hourly[["pm2_5", "pm10", "no2", "so2"]].groupby(day).mean()
    for col in ("co", "o3"):
        out[col] = hourly[col].rolling(8, min_periods=6).mean().groupby(day).max()
    counts = hourly["pm2_5"].groupby(day).count()
    out = out[counts >= 16]
    out.index.name = "date"
    return out


def add_aqi(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    records = df[list(TARGET_POLLUTANTS)].to_dict("records")
    df["aqi"] = [cpcb.aqi(r, TARGET_POLLUTANTS) for r in records]
    return df


def fetch(start: date = START, end: date | None = None) -> pd.DataFrame:
    """Fetch [start, end] (inclusive). `end` defaults to yesterday so every day is complete."""
    end = end or date.today() - timedelta(days=1)
    common = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TZ,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    aq = _get(AQ_URL, {**common, "hourly": ",".join(_HOURLY)})["hourly"]
    hourly = pd.DataFrame(aq).rename(columns=_HOURLY)
    hourly.index = pd.to_datetime(hourly.pop("time"))
    daily = daily_pollutants(hourly)

    wx = _get(WX_URL, {**common, "daily": ",".join(_DAILY_WX)})["daily"]
    weather = pd.DataFrame(wx).rename(columns=_DAILY_WX)
    weather.index = pd.to_datetime(weather.pop("time"))
    weather.index.name = "date"

    df = add_aqi(daily.join(weather, how="inner"))
    return df.round(3)


def save(df: pd.DataFrame, path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, date_format="%Y-%m-%d")
    return path


def load(path: Path = DEFAULT_PATH) -> pd.DataFrame:
    return pd.read_csv(path, index_col="date", parse_dates=["date"])
