"""Data stage tests. All frames here are small simulated fixtures, not real Delhi data."""

import numpy as np
import pandas as pd
import pytest

from aqi.data import cpcb, fetch, validate


@pytest.mark.parametrize(
    "pollutant, conc, expected",
    [
        ("pm2_5", 0, 0),
        ("pm2_5", 30, 50),
        ("pm2_5", 60, 100),
        ("pm2_5", 250, 400),
        ("pm10", 100, 100),
        ("co", 2.0, 100),
        ("no2", 180, 200),
    ],
)
def test_sub_index_breakpoints(pollutant, conc, expected):
    assert cpcb.sub_index(pollutant, conc) == pytest.approx(expected)


def test_sub_index_caps_at_500_and_rejects_bad_values():
    assert cpcb.sub_index("pm2_5", 10_000) == 500
    assert cpcb.sub_index("pm2_5", -1) is None
    assert cpcb.sub_index("pm2_5", float("nan")) is None


def test_aqi_is_max_sub_index():
    value = cpcb.aqi({"pm2_5": 60, "pm10": 50, "no2": 40})  # sub-indices 100, 50, 50
    assert value == 100


def test_aqi_needs_three_pollutants_including_pm():
    assert cpcb.aqi({"pm2_5": 60, "pm10": 50}) is None
    assert cpcb.aqi({"no2": 40, "so2": 40, "co": 1.0}) is None


def test_category():
    assert cpcb.category(45) == "Good"
    assert cpcb.category(150) == "Moderate"
    assert cpcb.category(450) == "Severe"


def test_daily_pollutants_uses_cpcb_averaging():
    idx = pd.date_range("2024-01-01", periods=48, freq="h")
    hourly = pd.DataFrame(
        {
            "pm2_5": 50.0,
            "pm10": 100.0,
            "no2": 40.0,
            "so2": 10.0,
            "co": np.r_[np.full(40, 1000.0), np.full(8, 3000.0)],  # ug/m3
            "o3": 80.0,
        },
        index=idx,
    )
    daily = fetch.daily_pollutants(hourly)
    assert len(daily) == 2
    assert daily["pm2_5"].tolist() == [50.0, 50.0]
    # CO converted to mg/m3, and day 2 takes the max 8h mean (last 8 hours at 3 mg/m3)
    assert daily["co"].iloc[0] == pytest.approx(1.0)
    assert daily["co"].iloc[1] == pytest.approx(3.0)


def simulated_daily(n=60, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", name="date")
    df = pd.DataFrame(
        {
            "pm2_5": rng.uniform(20, 200, n),
            "pm10": rng.uniform(50, 400, n),
            "no2": rng.uniform(10, 80, n),
            "so2": rng.uniform(5, 40, n),
            "co": rng.uniform(0.5, 3, n),
            "o3": rng.uniform(30, 150, n),
            "temp": rng.uniform(5, 40, n),
            "humidity": rng.uniform(20, 90, n),
            "wind": rng.uniform(1, 20, n),
            "precip": rng.uniform(0, 5, n),
        },
        index=idx,
    )
    return fetch.add_aqi(df)


def test_validate_passes_clean_data():
    rep = validate.validate(simulated_daily())
    assert rep.ok, rep.errors
    assert rep.faults == []


def test_validate_flags_duplicates_and_out_of_range():
    df = simulated_daily()
    df.iloc[5, df.columns.get_loc("humidity")] = 140
    df = pd.concat([df, df.iloc[[10]]]).sort_index()
    rep = validate.validate(df)
    assert not rep.ok
    assert any("duplicate" in e for e in rep.errors)
    assert any("humidity" in e for e in rep.errors)


def test_validate_flags_large_gap():
    df = simulated_daily().drop(pd.date_range("2024-01-10", "2024-01-20"))
    assert any("gap" in e for e in validate.validate(df).errors)


def test_stuck_sensor_is_a_fault_not_an_error():
    df = simulated_daily()
    df.iloc[-6:, df.columns.get_loc("pm2_5")] = 88.8  # simulated stuck sensor
    rep = validate.validate(df)
    assert rep.ok
    assert any("pm2_5: flat-lined" in f for f in rep.faults)
