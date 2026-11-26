"""Prediction API. Only health/version for now; /predict arrives with the training stage."""

import os

from fastapi import FastAPI

from aqi import __version__

app = FastAPI(title="AQI prediction API", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    # CI bakes GIT_SHA into the image, so a running container traces back to its commit.
    return {"version": __version__, "git_sha": os.getenv("GIT_SHA", "unknown")}
