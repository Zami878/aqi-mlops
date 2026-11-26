"""Monitoring and retrain-gate tests on simulated data."""

import json

import numpy as np
import pandas as pd
import pytest

from aqi import events
from aqi.data import fetch
from aqi.models import train
from aqi.models.registry import Registry
from aqi.monitor import decide, drift
from aqi.retrain import __main__ as retrain_cli
from tests.test_data import simulated_daily

CLEAN_VAL = {"errors": [], "faults": [], "end": "2024-03-01"}
META = {"train_end": "2024-01-01", "holdout": {"mae": 20.0}}


@pytest.fixture(autouse=True)
def _isolated_events(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DEFAULT_PATH", tmp_path / "events.jsonl")


def test_psi_is_small_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    ref = pd.Series(rng.normal(100, 10, 1000))
    assert drift.psi(ref, pd.Series(rng.normal(100, 10, 300))) < 0.1
    assert drift.psi(ref, pd.Series(rng.normal(160, 10, 300))) > 1.0


def test_seasonal_reference_matches_calendar_days_and_wraps_year_end():
    idx = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    history = pd.DataFrame({"x": 0}, index=idx)
    window = history.loc["2024-12-17":"2025-01-15"].reindex(
        pd.date_range("2024-12-17", "2025-01-15")
    )
    ref = drift.seasonal_reference(history, window)
    assert set(ref.index.month) == {12, 1}


def test_sensor_fault_blocks_retraining():
    val = {**CLEAN_VAL, "faults": ["pm2_5: flat-lined for 6 consecutive days"]}
    perf = {"n": 30, "mae": 99.0, "persistence_mae": 10.0}  # would otherwise retrain
    assert decide.decide(val, {}, perf, META)["decision"] == decide.BLOCKED


def test_lost_skill_triggers_retrain():
    perf = {"n": 30, "mae": 40.0, "persistence_mae": 35.0}
    out = decide.decide(CLEAN_VAL, {}, perf, META)
    assert out["decision"] == decide.RETRAIN
    assert "lost skill" in out["reasons"][0]


def test_healthy_when_model_beats_persistence_and_drift_is_only_a_warning():
    perf = {"n": 30, "mae": 30.0, "persistence_mae": 35.0}
    out = decide.decide(CLEAN_VAL, {"temp": 0.9, "aqi": 0.01}, perf, META)
    assert out["decision"] == decide.HEALTHY
    assert out["drift_warnings"] == ["temp"]


def test_old_model_triggers_retrain():
    perf = {"n": 30, "mae": 30.0, "persistence_mae": 35.0}
    val = {**CLEAN_VAL, "end": "2024-12-01"}
    assert decide.decide(val, {}, perf, META)["decision"] == decide.RETRAIN


@pytest.fixture
def seasonal_csv(tmp_path):
    """400 days of simulated, autocorrelated, seasonal AQI the model can learn."""
    rng = np.random.default_rng(1)
    df = simulated_daily(400, seed=1)
    t = np.arange(400)
    base = 150 + 80 * np.sin(2 * np.pi * t / 365)
    noise = np.cumsum(rng.normal(0, 5, 400)) * 0.3
    df["pm2_5"] = np.clip(base / 2 + noise, 5, None)
    df = fetch.add_aqi(df)
    path = tmp_path / "data.csv"
    fetch.save(df, path)
    return path


def test_bootstrap_promotes_through_gate_then_skips_when_healthy(tmp_path, seasonal_csv):
    reg = Registry(tmp_path / "registry")
    report = tmp_path / "gate.json"
    out = retrain_cli.run(seasonal_csv, reg, report)
    assert out["action"] == "promoted" and reg.champion_version() == "v1"
    assert json.loads(report.read_text())["checks"]["beats_persistence"]

    # same data again with --force: identical candidate cannot beat the champion -> rejected
    out = retrain_cli.run(seasonal_csv, reg, report, force=True)
    assert out["action"] == "rejected"
    assert out["checks"]["beats_champion"] is False
    assert reg.champion_version() == "v1" and reg.versions() == ["v1"]


def test_worse_candidate_is_never_promoted(tmp_path, seasonal_csv, monkeypatch):
    reg = Registry(tmp_path / "registry")
    retrain_cli.run(seasonal_csv, reg, tmp_path / "gate.json")
    # simulated bad candidate: replace the main model with one that always predicts 0
    monkeypatch.setattr(train, "fit", lambda name, tr: _Const())
    out = retrain_cli.run(seasonal_csv, reg, tmp_path / "gate.json", force=True)
    assert out["action"] == "rejected"
    assert reg.champion_version() == "v1"


def test_forced_retrain_is_still_blocked_by_sensor_fault(tmp_path, seasonal_csv):
    df = fetch.load(seasonal_csv)
    df.iloc[-6:, df.columns.get_loc("pm2_5")] = 77.7  # simulated stuck sensor
    fetch.save(df, seasonal_csv)
    reg = Registry(tmp_path / "registry")
    out = retrain_cli.run(seasonal_csv, reg, tmp_path / "gate.json", force=True)
    assert out["action"] == "blocked"
    assert reg.champion_version() is None


class _Const:
    def predict(self, X):
        return np.zeros(len(X))
