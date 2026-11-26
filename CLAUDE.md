# AQI MLOps Pipeline (PB-3)

College DevOps project: an automated CI/CD/CT pipeline for AQI prediction, monitoring and retraining. The pipeline is the product; the ML model is the payload. Prefer simple models and strong automation.

Team and ownership:
- data stage (src/aqi/data): Shivam Kumar
- training stage (src/aqi/models, retrain workflow): Rachit Sharma
- observability (src/aqi/monitor, deploy/): Sidharth Rohilla
- CI/CD and integration (.github/workflows, Dockerfile, src/aqi/serve, src/aqi/retrain): Keshav Sharma

## Commands
- make test: ruff + pytest
- make build: build the Docker image
- make up: API + Prometheus + Grafana via docker compose
- make monitor / make retrain: run those stages locally

## Rules
- Never invent metrics, results, test counts or citations. Numbers in the README or slides must come from a command run in this repo.
- Synthetic data is always labelled "simulated".
- Time-ordered splits only. No random train/test split, no feature that uses future values.
- Every new stage gets a test and a CI step. Don't mark a stage "done" in the README status table unless it runs in CI.
- A model is promoted only through the gate in src/aqi/retrain. No manual copying of model files.
- No secrets in the repo. Use GitHub Actions secrets and .env (see .env.example).
- Small commits, one module per commit, under the current git user only. Ask before pushing, force-pushing or deleting anything.
- Keep dependencies minimal; ask before adding a heavy one.

## Status
Update the status table in README.md whenever a stage changes state.
