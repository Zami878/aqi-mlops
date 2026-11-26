"""API tests. They run against the committed data snapshot and registry champion."""

import pytest
from fastapi.testclient import TestClient

from aqi import __version__
from aqi.serve.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the lifespan, which loads the champion
        yield c


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_reports_package_and_sha(client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    assert client.get("/version").json() == {"version": __version__, "git_sha": "abc123"}


def test_forecast_is_next_day_and_in_range(client):
    body = client.get("/forecast").json()
    assert 0 <= body["aqi"] <= 500
    assert body["for_date"] > body["based_on"]
    assert body["category"] in {
        "Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe",
    }  # fmt: skip
    assert body["model_version"].startswith("v")


def test_model_endpoint_returns_champion_meta(client):
    meta = client.get("/model").json()
    assert meta["holdout"]["mae"] < meta["persistence_holdout"]["mae"]


def test_metrics_expose_pipeline_state(client):
    client.get("/forecast")
    text = client.get("/metrics").text
    for name in ("aqi_forecast", "aqi_model_info", "aqi_requests_total", "aqi_drift_psi"):
        assert name in text


def test_dashboard_page_builds_from_repo_state():
    from aqi import report

    page = report.build()
    assert "Delhi AQI" in page and "<svg" in page
    assert "Model leaderboard" in page and "Latest promotion gate" in page
