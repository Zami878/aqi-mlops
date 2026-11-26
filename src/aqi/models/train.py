"""Model definitions, training and evaluation.

Main model: gradient-boosted trees (HistGradientBoostingRegressor). It trains in seconds on a
CI runner, handles missing values natively and captures non-linear weather x pollutant effects.
It predicts the day-over-day *change* in AQI and adds it to today's value; on this data that
beat predicting the level directly at 90, 180 and 365-day holdouts.
Baselines: persistence (tomorrow = today) and Ridge regression.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from aqi.models.features import FEATURES, TARGET, time_split, training_frame

HOLDOUT_DAYS = 90


class Persistence:
    """Tomorrow's AQI = today's AQI."""

    def fit(self, X: pd.DataFrame, y: pd.Series) -> Persistence:
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["aqi_lag0"].to_numpy()


class DeltaHGB:
    """Gradient-boosted trees on the next-day change in AQI."""

    def __init__(self, **params):
        self.model = HistGradientBoostingRegressor(**params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> DeltaHGB:
        self.model.fit(X, y - X["aqi_lag0"])
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X) + X["aqi_lag0"].to_numpy()


def make_model(name: str):
    if name == "persistence":
        return Persistence()
    if name == "ridge":
        return make_pipeline(SimpleImputer(), StandardScaler(), Ridge(alpha=1.0))
    if name == "hgb":
        return DeltaHGB(
            max_iter=200, learning_rate=0.03, max_leaf_nodes=7, min_samples_leaf=40,
            l2_regularization=1.0, random_state=0,
        )  # fmt: skip
    raise ValueError(f"unknown model {name!r}")


MODEL_NAMES = ["persistence", "ridge", "hgb"]
MAIN_MODEL = "hgb"


def predict(model, X: pd.DataFrame) -> np.ndarray:
    return np.clip(model.predict(X[FEATURES]), 0, 500)


def metrics(y_true, y_pred) -> dict:
    err = np.asarray(y_pred) - np.asarray(y_true)
    return {
        "mae": round(float(np.mean(np.abs(err))), 2),
        "rmse": round(float(np.sqrt(np.mean(err**2))), 2),
        "n": int(len(err)),
    }


def fit(name: str, train: pd.DataFrame):
    return make_model(name).fit(train[FEATURES], train[TARGET])


def leaderboard(df: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS) -> dict:
    """Train every model on the pre-holdout period and score it on the holdout."""
    train, test = time_split(training_frame(df), holdout_days)
    scores = {}
    for name in MODEL_NAMES:
        model = fit(name, train)
        scores[name] = metrics(test[TARGET], predict(model, test))
    return {
        "train_start": str(train.index.min().date()),
        "train_end": str(train.index.max().date()),
        "holdout_start": str(test.index.min().date()),
        "holdout_end": str(test.index.max().date()),
        "scores": scores,
    }
