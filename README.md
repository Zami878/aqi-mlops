# AQI MLOps Pipeline (PB-3)

Design and Implement an AI-Enabled Automated Pipeline for Air Quality Index Prediction, Model Monitoring, and Intelligent Retraining.

The CI/CD/CT pipeline is the product; the AQI model for **Delhi** is the payload it ships.

## Pipeline

```
commit → lint → test → build image → smoke test → push to GHCR → deploy
   ↑                                                               ↓
   └── promotion gate ← retrain ← drift decision ← monitor ←───────┘
```

## Status

| Stage | Owner | Module | State |
|---|---|---|---|
| CI: lint + test | Keshav Sharma | `.github/workflows/ci.yml` | in progress |
| CI: Docker build + smoke test + GHCR push | Keshav Sharma | `Dockerfile`, `src/aqi/serve` | in progress |
| Data: ingestion, validation gate, CPCB AQI | Shivam Kumar | `src/aqi/data` | not started |
| Training: features, models, registry | Rachit Sharma | `src/aqi/models` | not started |
| Observability: metrics, Prometheus, Grafana, drift | Sidharth Rohilla | `src/aqi/monitor`, `deploy/` | not started |
| CT: retrain trigger, promotion gate, rollback | Keshav Sharma | `src/aqi/retrain` | not started |

A stage is marked **done** only once it runs in CI.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
make install   # editable install with dev tools
make test      # ruff + pytest
make run       # build the image and serve on http://localhost:8000
```

Endpoints: `GET /health`, `GET /version` (reports the git SHA the image was built from).

## Team

| Member | Batch | Module |
|---|---|---|
| Keshav Sharma | B1 | CI/CD, Docker, deployment, promotion gate, integration |
| Shivam Kumar | B1 | Data stage |
| Rachit Sharma | B2 | Training stage |
| Sidharth Rohilla | B2 | Observability |
