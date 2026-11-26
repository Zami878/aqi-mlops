"""Promotion gate: the only path by which a model becomes champion.

A candidate is trained on everything before the last HOLDOUT_DAYS and compared on that holdout
against (a) the persistence baseline and (b) the current champion, and must beat both
(a tie keeps the current champion). The champion was trained on
data ending at least HOLDOUT_DAYS before its own promotion, so it has not seen this holdout
either. The candidate is promoted only if every check passes; otherwise it is discarded and the
champion keeps serving.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aqi.models import features, train
from aqi.models.registry import Registry


def evaluate(df: pd.DataFrame, registry: Registry, holdout_days: int = train.HOLDOUT_DAYS) -> dict:
    frame = features.training_frame(df)
    tr, te = features.time_split(frame, holdout_days)
    y = te[features.TARGET]

    candidate = train.fit(train.MAIN_MODEL, tr)
    cand_pred = train.predict(candidate, te)
    cand = train.metrics(y, cand_pred)
    persistence = train.metrics(y, te["aqi_lag0"])

    champ_model, champ_meta = registry.load_champion()
    champ = train.metrics(y, train.predict(champ_model, te)) if champ_model is not None else None

    checks = {
        "predictions_finite": bool(np.isfinite(cand_pred).all()),
        "beats_persistence": cand["mae"] < persistence["mae"],
        "beats_champion": champ is None or cand["mae"] < champ["mae"],
    }
    return {
        "candidate_model": candidate,
        "promote": all(checks.values()),
        "checks": checks,
        "holdout_start": str(te.index.min().date()),
        "holdout_end": str(te.index.max().date()),
        "train_start": str(tr.index.min().date()),
        "train_end": str(tr.index.max().date()),
        "scores": {
            "candidate": cand,
            "champion": champ,
            "persistence": persistence,
        },
        "champion_version": champ_meta["version"] if champ_meta else None,
    }
