"""Training stage tests on simulated data."""

import numpy as np
import pandas as pd
import pytest

from aqi.models import features, train
from aqi.models.registry import Registry
from tests.test_data import simulated_daily


def test_features_do_not_use_future_values():
    df = simulated_daily(80)
    before = features.build(df)
    changed = df.copy()
    changed.iloc[50:] = changed.iloc[50:] * 3  # change everything from day 50 on
    after = features.build(changed)
    cols = features.FEATURES
    # rows up to day 49 must be identical: nothing in them may depend on day >= 50
    pd.testing.assert_frame_equal(before.iloc[:50][cols], after.iloc[:50][cols])
    # the target of day 49 is day 50's AQI, so it does change
    assert before[features.TARGET].iloc[49] != after[features.TARGET].iloc[49]


def test_target_is_next_day_aqi():
    df = simulated_daily(20)
    frame = features.build(df)
    assert frame[features.TARGET].iloc[3] == df["aqi"].iloc[4]
    assert np.isnan(frame[features.TARGET].iloc[-1])


def test_time_split_is_ordered_and_disjoint():
    frame = features.training_frame(simulated_daily(100))
    tr, te = features.time_split(frame, 20)
    assert len(te) == 20
    assert tr.index.max() < te.index.min()


def test_leaderboard_scores_all_models():
    board = train.leaderboard(simulated_daily(200), holdout_days=30)
    assert set(board["scores"]) == set(train.MODEL_NAMES)
    assert board["train_end"] < board["holdout_start"]
    for s in board["scores"].values():
        assert s["n"] == 30 and s["mae"] >= 0


def test_predictions_are_clipped_to_aqi_range():
    frame = features.training_frame(simulated_daily(120))
    model = train.fit("ridge", frame)
    preds = train.predict(model, frame)
    assert preds.min() >= 0 and preds.max() <= 500


def test_registry_promote_and_rollback(tmp_path):
    reg = Registry(tmp_path)
    assert reg.champion_version() is None
    v1 = reg.register(train.Persistence(), {"note": "first"})
    reg.set_champion(v1)
    v2 = reg.register(train.Persistence(), {"note": "second"})
    reg.set_champion(v2)
    assert (v1, v2) == ("v1", "v2")
    assert reg.champion_version() == "v2" and reg.history() == ["v1"]
    assert reg.rollback() == ("v2", "v1")
    assert reg.champion_version() == "v1"
    model, meta = reg.load_champion()
    assert meta["note"] == "first"
    with pytest.raises(RuntimeError):
        reg.rollback()


def test_registry_discards_rejected_and_prunes_old(tmp_path):
    reg = Registry(tmp_path)
    for _ in range(9):
        reg.set_champion(reg.register(train.Persistence(), {}))
    assert len(reg.versions()) == 6  # KEEP_VERSIONS
    rejected = reg.register(train.Persistence(), {})
    reg.discard(rejected)
    assert rejected not in reg.versions()
