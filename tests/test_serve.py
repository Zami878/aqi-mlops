from fastapi.testclient import TestClient

from aqi import __version__
from aqi.serve.app import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_reports_package_and_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    resp = client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": __version__, "git_sha": "abc123"}
