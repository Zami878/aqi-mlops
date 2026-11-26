"""Prediction API for next-day Delhi AQI.

Loads the champion from the registry and the latest data snapshot at startup, and exposes
pipeline state (model, monitor decision, drift) as Prometheus metrics for Grafana.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from aqi import __version__
from aqi.data import cpcb, fetch
from aqi.models import features, train
from aqi.models.registry import Registry

HOME = Path(os.getenv("AQI_HOME", "."))

REQUESTS = Counter("aqi_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram("aqi_request_seconds", "Request latency", ["path"])
FORECAST = Gauge("aqi_forecast", "Next-day AQI forecast from the champion model")
OBSERVED = Gauge("aqi_latest_observed", "AQI of the latest day in the data")
MODEL_INFO = Gauge("aqi_model_info", "Champion model", ["version", "model", "train_end"])
HOLDOUT_MAE = Gauge("aqi_holdout_mae", "MAE on the promotion holdout", ["model"])
RECENT_MAE = Gauge("aqi_recent_mae", "MAE on recent days the champion has not seen", ["model"])
PSI = Gauge("aqi_drift_psi", "Population Stability Index vs same calendar days", ["feature"])
DECISION = Gauge("aqi_monitor_decision", "Latest monitor decision (1 = current)", ["decision"])
FAULTS = Gauge("aqi_data_faults", "Sensor-fault patterns in the recent window")
EVENTS = Gauge("aqi_pipeline_events", "Pipeline events so far", ["event"])

state: dict = {}


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def load_state(home: Path = HOME) -> dict:
    registry = Registry(home / "registry")
    model, meta = registry.load_champion()
    df = fetch.load(home / fetch.DEFAULT_PATH)
    frame = features.build(df)
    st = {
        "model": model,
        "meta": meta,
        "df": df,
        "frame": frame,
        "monitor": _read_json(home / "reports/monitor.json"),
        "gate": _read_json(home / "reports/gate.json"),
        "events": [
            json.loads(line)
            for line in (home / "reports/events.jsonl").read_text().splitlines()
            if line.strip()
        ]
        if (home / "reports/events.jsonl").exists()
        else [],
    }
    st["forecast"] = _forecast(st)
    _export_metrics(st)
    return st


def _forecast(st: dict) -> dict | None:
    if st["model"] is None:
        return None
    last = st["frame"].iloc[[-1]]
    value = round(float(train.predict(st["model"], last)[0]), 1)
    based_on = last.index[0].date()
    return {
        "city": "Delhi",
        "for_date": str(based_on + timedelta(days=1)),
        "aqi": value,
        "category": cpcb.category(value),
        "based_on": str(based_on),
        "latest_observed_aqi": float(st["df"]["aqi"].iloc[-1]),
        "model_version": st["meta"]["version"],
    }


def _export_metrics(st: dict) -> None:
    fc, meta, mon = st["forecast"], st["meta"], st["monitor"]
    if fc:
        FORECAST.set(fc["aqi"])
        OBSERVED.set(fc["latest_observed_aqi"])
    if meta:
        MODEL_INFO.clear()
        MODEL_INFO.labels(meta["version"], meta["model"], meta["train_end"]).set(1)
        HOLDOUT_MAE.labels("champion").set(meta["holdout"]["mae"])
        HOLDOUT_MAE.labels("persistence").set(meta["persistence_holdout"]["mae"])
    if mon:
        for feat, value in mon["psi"].items():
            PSI.labels(feat).set(value)
        for d in ("healthy", "retrain", "blocked_sensor_fault"):
            DECISION.labels(d).set(1 if mon["decision"] == d else 0)
        FAULTS.set(len(mon["validation"]["faults"]))
        perf = mon["performance"]
        if perf["mae"] is not None:
            RECENT_MAE.labels("champion").set(perf["mae"])
            RECENT_MAE.labels("persistence").set(perf["persistence_mae"])
    for ev in ("promoted", "rejected", "blocked", "rollback"):
        EVENTS.labels(ev).set(sum(e["event"] == ev for e in st["events"]))


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.update(load_state())
    yield


app = FastAPI(title="Delhi AQI prediction API", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    LATENCY.labels(path).observe(time.perf_counter() - start)
    REQUESTS.labels(path, str(response.status_code)).inc()
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    # CI bakes GIT_SHA into the image, so a running container traces back to its commit.
    return {"version": __version__, "git_sha": os.getenv("GIT_SHA", "unknown")}


@app.get("/forecast")
def forecast() -> dict:
    if not state.get("forecast"):
        raise HTTPException(503, "no champion model in the registry")
    return state["forecast"]


@app.get("/model")
def model() -> dict:
    if not state.get("meta"):
        raise HTTPException(503, "no champion model in the registry")
    return state["meta"]


@app.get("/monitor")
def monitor() -> dict:
    if not state.get("monitor"):
        raise HTTPException(404, "no monitor report yet")
    return state["monitor"]


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
