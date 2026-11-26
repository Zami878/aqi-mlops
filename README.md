# AQI MLOps Pipeline (PB-3)

[![CI/CD](https://github.com/Zami878/aqi-mlops/actions/workflows/ci.yml/badge.svg)](https://github.com/Zami878/aqi-mlops/actions/workflows/ci.yml)
[![Continuous training](https://github.com/Zami878/aqi-mlops/actions/workflows/ct.yml/badge.svg)](https://github.com/Zami878/aqi-mlops/actions/workflows/ct.yml)

Design and Implement an AI-Enabled Automated Pipeline for Air Quality Index Prediction, Model Monitoring, and Intelligent Retraining.

The CI/CD/CT pipeline is the product; a next-day AQI model for **New Delhi** is the payload it ships.

**Live dashboard:** https://zami878.github.io/aqi-mlops/ (rebuilt by CI on every release)

## Pipeline

```
                 ┌──────────────────────── CI/CD (ci.yml: every push / PR) ───────────────────────┐
 commit ──► lint + tests ──► data gate ──► model gate ──► build image ──► smoke test ──► push :sha
                                                                                          │
                       dashboard (Pages) ◄── release :latest ◄── pull + verify image ◄────┘

                 ┌──────────────────── CT (ct.yml: daily 08:00 IST / manual) ─────────────────────┐
 fetch Delhi data ──► validate ──► monitor ──► decision ─┬─ healthy ─────────► keep champion
                                                         ├─ sensor fault ────► block retraining
                                                         └─ retrain ──► candidate ──► promotion gate
                                                                                   ├─ pass ► promote ─► commit ─► CI/CD
                                                                                   └─ fail ► discard, champion stays
 rollback.yml (manual): restore previous champion, or point :latest at an earlier image
```

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push, PR, after CT | ruff + pytest; data validation gate; model must beat persistence; Docker build + smoke test; on `main`: push `:sha` to GHCR, pull and re-test it, tag `:latest`, publish dashboard |
| `ct.yml` | daily cron, manual | fetch data, validate, monitor, retrain + gate, commit results, trigger CI/CD. Manual inputs: `force`, `simulate_fault` |
| `rollback.yml` | manual | `model`: previous champion back + redeploy; `image`: verified retag of an earlier image as `:latest` |

## Design decisions

- **Data.** Daily pollutants (PM2.5, PM10, NO2, SO2, CO, O3) from the CAMS atmospheric-composition model via the Open-Meteo API, plus daily weather, for a central-Delhi grid point from 2022-08-05. These are *modelled* concentrations, not CPCB station readings. No API key is needed, so CI can fetch without secrets.
- **Target.** CPCB National AQI (sub-index breakpoints, 24 h / 8 h averaging periods, three-pollutant rule). **Ozone is left out of the target.** On this data, modelled O3 set the AQI on 58% of days and put the monsoon-month average above 200, which disagrees with Delhi's observed clean monsoon. O3 stays in as a model feature. A CPCB station feed can replace the source behind the same columns.
- **No look-ahead.** Features for day *t* use only data up to day *t*; the target is day *t+1*. A unit test changes future rows and checks that past features stay identical. Splits are time-ordered; nothing is shuffled.
- **Model.** Gradient-boosted trees (`HistGradientBoostingRegressor`) predicting the next-day *change* in AQI. It trains in seconds on a CI runner, so automated retraining is cheap. Baselines: persistence (tomorrow = today) and Ridge.
- **Promotion gate.** A candidate is trained on everything before the last 90 days and must beat **both** persistence **and** the current champion on those 90 days. A tie keeps the champion. Only `src/aqi/retrain` can change `registry/champion.json`.
- **Retrain triggers.** (1) *Lost skill*: on the last 30 days the champion has not seen, it is no better than persistence on the same days. (2) *Model age* > 180 days of training-data lag. A first rule that compared recent error with the holdout error fired almost every winter because Delhi's error is seasonal; comparing against persistence on the same days cancels that out.
- **Sensor faults block retraining.** Flat-lined readings, impossible values or missing days in the recent window stop the retrain before drift is even considered, so a broken feed can't push a model trained on bad data.
- **Drift is a warning, not a trigger.** PSI is computed against the same calendar days in earlier years (season-matched). Backtested on this data, 30-day feature PSI crossed 0.25 in almost every month from ordinary weather variation, so it is shown on the dashboards and alerts but does not retrain on its own.

## Status

| Stage | Owner | Module | State |
|---|---|---|---|
| CI: lint + unit tests | Keshav Sharma | `.github/workflows/ci.yml` | done |
| Data: ingestion, CPCB AQI, validation gate | Shivam Kumar | `src/aqi/data` | done |
| Training: features, models, registry, model gate | Rachit Sharma | `src/aqi/models` | done |
| Observability: metrics, Prometheus rules, Grafana dashboard | Sidharth Rohilla | `src/aqi/monitor`, `src/aqi/serve`, `deploy/` | done (configs checked in CI; Grafana stack runs locally via compose) |
| CD: image build, smoke test, GHCR release, Pages | Keshav Sharma | `Dockerfile`, `ci.yml` | done |
| CT: monitor, sensor-fault block, retrain + gate | Keshav Sharma | `src/aqi/retrain`, `ct.yml` | done (gate promote/reject paths covered by CI tests; no promotion on GitHub yet because the champion is still healthy) |
| Rollback | Keshav Sharma | `rollback.yml` | image rollback run in Actions; model rollback needs a second champion first |

A stage is marked **done** only once it runs green in GitHub Actions.

## Run it locally

```bash
python -m venv .venv && . .venv/bin/activate
make install       # editable install with dev tools
make test          # ruff + pytest
make leaderboard   # train all models on the time-ordered split, check main model beats persistence
make monitor       # drift / skill / sensor-fault check -> reports/monitor.json
make retrain       # monitor -> (if needed) candidate -> promotion gate
make up            # API + Prometheus + Grafana (+ simulated traffic) via docker compose
```

`make up` serves the API on :8000, Prometheus on :9090 and Grafana on :3000. The Grafana dashboard *AQI MLOps pipeline (Delhi)* is provisioned automatically, with anonymous view access. If those ports are taken: `GRAFANA_PORT=13000 PROMETHEUS_PORT=19090 make up`.

API: `GET /forecast`, `/model`, `/monitor`, `/metrics`, `/health`, `/version`.

Demo of the sensor-fault block: `python -m aqi.monitor --simulate-fault` (in-memory, simulated stuck PM2.5 reading; nothing is saved), or run the CT workflow with `simulate_fault` ticked.

## Team

| Member | Batch | Module |
|---|---|---|
| Keshav Sharma | B1 | CI/CD, Docker, deployment, promotion gate, rollback, integration |
| Shivam Kumar | B1 | Data stage |
| Rachit Sharma | B2 | Training stage |
| Sidharth Rohilla | B2 | Observability |
