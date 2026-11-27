# PB-3 AQI MLOps: project guide and review prep

Nov 27, 2026

## The project in plain words

PB-3 is an automated pipeline that tests, ships, watches and retrains a model predicting **tomorrow's CPCB AQI for New Delhi**. The pipeline is the product; the model is only the payload it carries.

**The problem.** A deployed AQI model gets worse over time: sensors break, seasons change (winter smog, clean monsoon), pollution sources shift. Most AQI papers stop at an accurate notebook. Nobody tests, deploys, monitors or retrains the model automatically. That is the research gap we close.

**Why it is a DevOps project.** It runs three automated loops in GitHub Actions:

- **CI (continuous integration):** every push is linted, unit-tested, and the data and model pass quality gates before an image is built.
- **CD (continuous delivery):** the Docker image is built, smoke-tested, pushed to GHCR, re-verified, released as `:latest`, and the dashboard is republished.
- **CT (continuous training):** every day the pipeline fetches new Delhi data, validates it, monitors the live model, and retrains and promotes a new one only if it is provably better.

Repo: [github.com/Zami878/aqi-mlops](https://github.com/Zami878/aqi-mlops). Live dashboard: [zami878.github.io/aqi-mlops](https://zami878.github.io/aqi-mlops/).

## What the repo does, stage by stage

Every stage below runs green in GitHub Actions. Three workflows drive it: `ci.yml` (every push and PR), `ct.yml` (daily 08:00 IST or manual) and `rollback.yml` (manual).

| Stage | Owner | Code | What it does |
| --- | --- | --- | --- |
| Data: fetch | Shivam Kumar | `src/aqi/data/fetch.py` | Downloads daily PM2.5, PM10, NO2, SO2, CO, O3 (CAMS model via Open-Meteo) plus weather for a central-Delhi point, from 2022-08-05. No API key. |
| Data: CPCB AQI | Shivam Kumar | `src/aqi/data/cpcb.py` | Computes the CPCB National AQI: sub-index per pollutant, AQI = highest sub-index, at least three pollutants with one of PM2.5/PM10. O3 left out of the target. |
| Data: validation gate | Shivam Kumar | `src/aqi/data/validate.py` | **Errors** (fail CI): wrong schema, duplicate or unsorted dates, values outside physical limits, more than 5% missing. **Sensor faults** (block retraining): same value 4+ days in a row on PM2.5/PM10/NO2/CO, impossible values, a gap over 3 days. |
| Training | Rachit Sharma | `src/aqi/models` | 20 features (AQI lags 0/1/2/6, 3- and 7-day rolling means, pollutants, weather, day-of-year, weekday). Gradient-boosted trees predict tomorrow's AQI change. Baselines: persistence and Ridge. Model registry in `registry/`. |
| Monitoring | Sidharth Rohilla | `src/aqi/monitor` | Season-matched PSI drift per feature (warning at 0.25), model MAE vs persistence on the last 30 unseen days, and the decision: healthy, retrain, or blocked by a sensor fault. |
| Serving + metrics | Sidharth / Keshav | `src/aqi/serve`, `deploy/` | FastAPI: `/forecast`, `/model`, `/monitor`, `/metrics`, `/health`, `/version`. Prometheus scrapes `/metrics`; Grafana shows them; alert rules in `deploy/prometheus`. |
| CI | Keshav Sharma | `ci.yml` | ruff lint + pytest, data gate, model gate (must beat persistence), Prometheus rules + Grafana JSON checked. |
| CD | Keshav Sharma | `Dockerfile`, `ci.yml` | Build image, smoke test, push `:sha` to GHCR, pull that exact image and re-test, tag `:latest`, publish dashboard to GitHub Pages. |
| CT + promotion gate | Keshav Sharma | `src/aqi/retrain`, `ct.yml` | Daily: fetch, validate, monitor, retrain if needed. A candidate is promoted only if it beats **both** persistence and the current champion on the last 90 days. Results are committed and CI/CD is triggered. |
| Rollback | Keshav Sharma | `rollback.yml` | Restores the previous champion model, or points `:latest` back at an earlier verified image. |

**Current state (from `registry/` and `reports/`, last CT run 2026-11-26):** champion model **v3**. On the 90-day holdout (2026-08-27 to 2026-11-24) it scored MAE **46.96**, against persistence **51.36**, Ridge **49.53** and the old champion v1 **47.34**. A model rollback v2 → v1 and an image rollback have both run in Actions.

## What the dashboards show

There are two dashboards. The **public Pages dashboard** is a static report that CI rebuilds on every release. **Grafana** is the live operations view, running locally with `make up`.

### 1. Live Pages dashboard ([zami878.github.io/aqi-mlops](https://zami878.github.io/aqi-mlops/))

Built by `src/aqi/report.py` and published by the last CI job.

| Section | What it shows | What to say about it |
| --- | --- | --- |
| Observed AQI vs forecast | Delhi's real AQI line against the champion's next-day forecast | The model follows the winter rise and the monsoon drop |
| Model leaderboard | MAE/RMSE of persistence, Ridge and the gradient-boosted model on the 90-day holdout | Our model must beat "tomorrow = today" or CI fails |
| Drift vs same days in past years | PSI per feature, season-matched | Drift is a warning only; ordinary weather swings push PSI over 0.25 most months |
| Latest promotion gate | Candidate vs champion vs persistence, and the decision | Shows the gate is a hard rule, not a judgement call |
| Pipeline events | Log of monitor runs, promotions, rejections, rollbacks with run IDs | Every change is traceable to a GitHub Actions run |

### 2. Grafana: "AQI MLOps pipeline (Delhi)" (`localhost:3000` after `make up`)

Prometheus scrapes the API's `/metrics`; the dashboard is provisioned automatically from `deploy/grafana`.

| Row | Panels |
| --- | --- |
| Forecast | Next-day AQI forecast, latest observed AQI, champion model version, monitor decision |
| Model quality | Holdout MAE at promotion, recent MAE on unseen days, drift PSI per feature |
| Pipeline | Sensor faults (last 30 days), promotions, rejected candidates, rollbacks |
| Serving | Requests per second by endpoint, latency p50/p95. The traffic is **simulated** by a load generator container. |

**Alert rules** (`deploy/prometheus/alerts.yml`):

- `AqiApiDown`: API not reachable for 1 minute
- `AqiSensorFault`: any sensor fault in the recent data
- `AqiRetrainNeeded`: monitor decision is "retrain"
- `AqiModelLostSkill`: champion's recent MAE is no better than persistence
- `AqiHighLatency`: p95 latency above 0.5 s for 5 minutes

## What to present to the teacher

Lead with the pipeline, prove it with real Actions runs, then show the model's numbers last. The model is the payload, not the result.

**Suggested order (about 10 minutes):**

1. **Problem and gap (1 min).** AQI models decay after deployment; papers don't automate testing, deployment, monitoring or retraining.
2. **Pipeline diagram (2 min).** The CI → CD → CT loop from the README. Say who owns which stage.
3. **CI/CD live (2 min).** Open the Actions tab and show a green `CI/CD` run: lint + tests, data gate, model gate, build, smoke test, GHCR push, verify, `:latest`, Pages.
4. **CT live (2 min).** Show a `Continuous training` run and its job summary: data through date, monitor decision, gate result.
5. **Safety rails (2 min).** Run CT with `simulate_fault` ticked: the stuck-sensor fault blocks retraining. Then show the rollback runs (model v2 → v1, image rollback).
6. **Dashboards (1 min).** Pages dashboard (leaderboard, gate, events), then Grafana if you have `make up` running.
7. **Model numbers last (30 s).** Champion v3: holdout MAE 46.96 vs persistence 51.36.

**Before the review, check:**

- [ ] Latest `CI/CD` and `Continuous training` runs are green
- [ ] Pages dashboard loads
- [ ] `make up` works on the demo laptop; if ports clash use `GRAFANA_PORT=13000 PROMETHEUS_PORT=19090 make up`
- [ ] Everyone has read their module and the cross-questions below

**Be honest about one thing:** the v2 and v3 promotions in Actions were runs with `force` ticked (`reports/gate.json` shows trigger "forced"). Force skips the *monitor's* "do we need to retrain?" check, but the promotion gate itself still ran and v3 still had to beat both persistence and v1. The daily monitor has reported "healthy", so no unforced retrain has fired yet.

## How to present each step

For each step: what to have open, what to click, and what to say. Open every link in its own browser tab before the review starts, so nothing loads in front of the teacher.

### 1. Problem and gap (1 min)

**Show:** your PPT's research-gap slide.

**Say:**

> "Most AQI papers train a model, report its accuracy and stop. But a deployed model gets worse: sensors break, the season changes from monsoon to winter smog, pollution sources change. No paper we reviewed tests, deploys, monitors and retrains the model automatically, or checks whether bad data is a broken sensor before retraining on it. Our project builds that automation. The pipeline is the product; the model is just what it carries."

**Keep it short.** The teacher pressed on gaps last time, so say the gap in one sentence and move on. The demo proves it.

### 2. Pipeline diagram (2 min)

**Show:** the repo home page, [github.com/Zami878/aqi-mlops](https://github.com/Zami878/aqi-mlops), scrolled to the **Pipeline** diagram (or the same diagram on your PPT).

**Point at each line as you say it:**

> "There are three loops. **CI/CD** runs on every push: lint and tests, a data gate, a model gate, then build the Docker image, smoke-test it, push it, re-test the pushed image and release it. **CT** runs every morning at 08:00 IST: fetch new Delhi data, validate it, monitor the live model, and retrain only if needed. A new model is promoted only if it passes the promotion gate; then CT triggers CI/CD to redeploy. **Rollback** is a manual workflow to undo a model or an image."

**Then the owners table (README → Status):**

> "Shivam owns the data stage, Rachit the training stage, Sidharth observability, and I own CI/CD, the CT loop, the gate and rollback."

### 3. CI/CD live (2 min)

**Show:** [Actions tab](https://github.com/Zami878/aqi-mlops/actions) → filter by **CI/CD** → open a green run, e.g. [run 45912962332](https://github.com/Zami878/aqi-mlops/actions/runs/45912962332). The run page draws the jobs as a graph.

**Walk the graph left to right:**

1. **Lint + unit tests**: "ruff and pytest. A failing test stops everything after it."
2. **Data validation gate**: "the committed Delhi data is checked; any error fails the build."
3. **Model quality gate**: "the model must beat persistence, tomorrow = today, on a time-ordered holdout. If it doesn't, CI is red." Click it and show the job summary table.
4. **Prometheus rules + Grafana check**: "even the monitoring config is tested: promtool checks the alert rules, and every Grafana panel must have a query."
5. **Build image + smoke test**: "Docker image built, started, and every API endpoint hit."
6. **Push image to GHCR** → **Verify pushed image, then release as :latest**: "we pull back the exact image we pushed and test it again. Only then does it become `:latest`."
7. **Build dashboard**: "the public dashboard is rebuilt from the new results."

**Line to land:** "No human builds or deploys anything. A commit goes in; a tested image and a dashboard come out."

### 4. CT live (2 min)

**Show:** Actions → **Continuous training** → [run 45904277268](https://github.com/Zami878/aqi-mlops/actions/runs/45904277268) → scroll to the **job summary** at the bottom of the run page.

**Read the summary out:**

> "Data through 2026-11-25. The monitor decision was *healthy*. Drift warnings on CO, humidity, NO2, temperature and wind: shown, but drift alone doesn't retrain. This run had *force* ticked, so it trained a candidate anyway. The gate checks all passed: finite predictions, beats persistence, beats the champion. So v3 became the champion."

**Then click the job** and show the step list: fetch → validate → monitor → retrain + gate → commit → trigger CI/CD.

> "After the gate, CT commits the new data, model registry and reports to the repo, and triggers CI/CD, which you just saw rebuild and redeploy."

**Say "force" out loud.** If you hide it and the teacher spots "forced" in the summary, it looks bad. Explain it: force skips the monitor's "is retraining needed?" check, never the gate.

### 5. Safety rails (2 min)

**Sensor-fault block.** The same CT run (45904277268) had `simulate_fault` ticked. Open the job and expand the step **Demo: simulated stuck sensor (not saved)**. The log ends with `retraining correctly blocked`.

> "Here we injected a fake stuck PM2.5 sensor: the same reading for the last 6 days, in memory only, labelled simulated. The validation gate flagged it as a sensor fault and the decision became *blocked_sensor_fault*. A broken sensor can never trigger retraining, even with force on."

**Rollback.** Actions → **Rollback**:

- [run 45903895261](https://github.com/Zami878/aqi-mlops/actions/runs/45903895261), job **Roll back champion model**: "the champion went from v2 back to v1, then CI/CD redeployed it."
- [run 45900832254](https://github.com/Zami878/aqi-mlops/actions/runs/45900832254), job **Point :latest at an earlier image**: "`:latest` pointed back at an earlier image, after that image was verified."

> "Rollback is the only manual step, and on purpose: a human decides to undo. But even that is a workflow with a log, not someone copying files."

**Don't trigger a new CT run live.** It takes minutes, commits to `main` and triggers CI/CD. Show the recorded runs. If the teacher insists, start it from Actions → Continuous training → **Run workflow** with `simulate_fault` ticked and come back to it at the end.

### 6. Dashboards (1 min)

**Pages dashboard:** [zami878.github.io/aqi-mlops](https://zami878.github.io/aqi-mlops/). Scroll and point:

- **Observed vs forecast chart**: "real Delhi AQI against our next-day forecast."
- **Leaderboard**: "our model against persistence and Ridge on the same 90 days."
- **Latest promotion gate**: "why v3 was promoted."
- **Pipeline events**: "every monitor run, promotion and rollback, each with its Actions run ID."

**Grafana (only if `make up` is already running):** [localhost:3000](http://localhost:3000), dashboard *AQI MLOps pipeline (Delhi)*.

> "This is the live operations view. Prometheus scrapes the API's /metrics. Top row: forecast, champion version, monitor decision. Then model quality and drift, pipeline counters, and serving latency. The traffic here is simulated by a load generator."

Start `make up` at least 5 minutes before the review; don't start it live.

### 7. Model numbers last (30 s)

**Show:** the leaderboard on the Pages dashboard.

> "The champion, v3, has a holdout MAE of 46.96 against 51.36 for persistence, about 9% lower, and 49.53 for Ridge. It's a simple gradient-boosted model on purpose: it trains in seconds, so the pipeline can retrain it every day if it needs to."

**End with:** "The number we care about isn't the MAE. It's that no model reaches production without beating persistence and the current champion, and every step to get there is automated and logged."

## Presenting from another laptop (e.g. Sidharth's)

**Steps 1 to 5 and the Pages dashboard need only a browser.** Everything runs in GitHub Actions and on GitHub Pages, so any laptop with internet works. Open the links from the "How to present each step" section. Nothing to install.

**Grafana (step 6) needs Docker on that laptop.** Set it up the day before, not at the review:

1. Install **Git** and **Docker Desktop** (Windows/macOS) or Docker Engine (Linux). Start Docker.
2. Get the code:
   ```bash
   git clone https://github.com/Zami878/aqi-mlops.git
   cd aqi-mlops
   ```
3. Start the stack from the released image (no build, no Python needed):
   ```bash
   make up-release
   ```
   No `make` (e.g. Windows)? Run the same thing directly. In Git Bash:
   ```bash
   AQI_IMAGE=ghcr.io/zami878/aqi-mlops:latest docker compose -f deploy/docker-compose.yml up -d --no-build
   ```
   In PowerShell:
   ```powershell
   $env:AQI_IMAGE="ghcr.io/zami878/aqi-mlops:latest"; docker compose -f deploy/docker-compose.yml up -d --no-build
   ```
4. Open http://localhost:3000 (Grafana) and http://localhost:8000/forecast (API). Wait about a minute for the graphs to fill.
5. Port already in use? Add `GRAFANA_PORT=13000 PROMETHEUS_PORT=19090` before the command and open http://localhost:13000.
6. Stop it afterwards: `make down` (or `docker compose -f deploy/docker-compose.yml down`).

The image on GHCR is public, so no GitHub login is needed to pull it.

**To also run tests or the monitor locally** (optional, needs Python 3.11+):

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
make install
make test
python -m aqi.monitor --simulate-fault
```

## Cross-questions with answers

Each answer is based on what the repo actually does. Anyone can be asked any question, but each person should know their own section cold.

### Whole project (everyone)

**What is the research gap?** AQI papers stop at an accurate model in a notebook. None of them automatically test, deploy, monitor and retrain it, or separate a broken sensor from real change before retraining. We automate that whole loop.

**Why is this a DevOps project and not an ML project?** The deliverable is the CI/CD/CT pipeline. The model is deliberately simple and trains in seconds, so the pipeline can retrain it cheaply and often.

**What happens end to end when new data arrives?** CT fetches it, the validation gate checks it, the monitor decides healthy / retrain / blocked, a candidate is trained if needed, the gate decides promote or discard, results are committed, and CI/CD rebuilds, tests and redeploys.

**Is anything manual?** Only rollback, and that's deliberate, because a human decides to undo. Even rollback is a workflow, not someone copying files.

### Data stage (Shivam)

**Where does the data come from?** Daily pollutant concentrations from the CAMS atmospheric-composition model via the Open-Meteo API, plus daily weather, for a central-Delhi grid point from 2022-08-05. These are modelled values, not CPCB station readings.

**Why not CPCB station data?** Open-Meteo needs no API key, so CI can fetch it without secrets, and it has continuous history. A CPCB station feed can replace it behind the same columns without changing the pipeline.

**How is AQI calculated?** Each pollutant gets a CPCB sub-index from 0 to 500 using its breakpoints. The AQI is the highest sub-index. It needs at least three pollutants, one of them PM2.5 or PM10. PM uses 24-hour averages; CO and O3 use 8-hour averages.

**Why is ozone left out of the target?** On this modelled data, O3 set the AQI on 58% of days and pushed the monsoon average above 200. That contradicts Delhi's observed clean monsoon. O3 is still used as a model input.

**What does the validation gate check?** Errors that fail CI: wrong schema, duplicate or unsorted dates, values outside physical limits, more than 5% missing. Sensor faults that block retraining: the same reading 4+ days in a row on PM2.5, PM10, NO2 or CO, impossible values, or a gap longer than 3 days.

**How do you tell a broken sensor from real pollution change?** The gate runs first. A stuck, missing or impossible reading is a sensor fault, so retraining is blocked, even when the run is forced. Only data that passes is checked for drift and skill.

**Can you show it?** Yes: `python -m aqi.monitor --simulate-fault`, or run CT with `simulate_fault` ticked. It injects a simulated stuck PM2.5 reading in memory and the decision becomes `blocked_sensor_fault`.

### Training stage (Rachit)

**Which algorithm and why?** `HistGradientBoostingRegressor` (gradient-boosted trees). It handles mixed features and missing values and trains in seconds on a CI runner, so automated retraining is cheap.

**What does it predict?** Tomorrow's AQI change, added to today's AQI. Predicting the change makes it beat persistence rather than copy it.

**What are the features?** 20 in total: AQI today and 1, 2 and 6 days back; 3- and 7-day rolling means; PM2.5 day-on-day change; the six pollutants; temperature, humidity, wind and rain; day-of-year (sine/cosine); day of week.

**How do you avoid data leakage?** Features for day t use only data up to day t; the target is day t+1. A unit test changes future rows and checks that past features stay identical. Splits are time-ordered; nothing is shuffled.

**What are the baselines?** Persistence (tomorrow = today) and Ridge regression. On the 90-day holdout: persistence MAE 51.36, Ridge 49.53, our model 46.96.

**Why is MAE around 47 — isn't that high?** Delhi AQI swings by hundreds between seasons, and day-to-day jumps are hard to predict. The point is that it reliably beats the honest baseline, and the pipeline enforces that.

### Observability (Sidharth)

**What do you monitor?** Service health (request rate, p50/p95 latency, API up), input drift (PSI per feature), model skill (MAE vs persistence on the last 30 unseen days), and pipeline events (sensor faults, promotions, rejections, rollbacks).

**How do you detect drift?** Population Stability Index per feature, comparing the last 30 days with the **same calendar days in earlier years**. Season-matching stops winter from always looking like drift.

**Why is drift only a warning?** In a backtest on this data, 30-day PSI crossed 0.25 almost every month just from normal weather variation. Retraining on that would be noise. So drift shows on the dashboards and alerts but never retrains on its own.

**Then what triggers retraining?** Two rules: (1) lost skill: on the last 30 unseen days the champion is no better than persistence; (2) model age: training data more than 180 days old.

**Why compare against persistence and not the original error?** Delhi's error is seasonal. A rule comparing recent error with the holdout error fired almost every winter. Comparing against persistence on the same days cancels that out.

**What alerts exist?** `AqiApiDown`, `AqiSensorFault`, `AqiRetrainNeeded`, `AqiModelLostSkill`, `AqiHighLatency` (p95 > 0.5 s for 5 min).

**Why Prometheus and Grafana?** The standard open-source pair: Prometheus scrapes `/metrics` and evaluates alert rules, Grafana draws the panels, and both run in one `docker compose`. CI checks the rules with `promtool` and checks every Grafana panel has a query.

**Is the traffic on the Grafana dashboard real?** No, it is simulated by a load generator container, and the dashboard labels it that way.

### CI/CD, CT and integration (Keshav)

**What runs on every push?** Ruff lint, pytest, the data validation gate, the model gate (must beat persistence), Prometheus and Grafana config checks, then Docker build and smoke test.

**How do you know the deployed image works?** It is tested twice: the freshly built image is smoke-tested, then the exact image pushed to GHCR is pulled back and tested again before it is tagged `:latest`.

**What is the promotion gate?** A candidate trained on everything before the last 90 days must beat **both** persistence **and** the current champion on those 90 days. A tie keeps the champion. Only `src/aqi/retrain` can change `registry/champion.json`.

**Has a promotion actually happened?** Yes, in Actions: v2, and then v3. Both were runs with `force` ticked to demonstrate the loop. Force skips the monitor's "is retraining needed?" check, not the gate. v3 beat v1 (46.96 vs 47.34) and persistence (51.36).

**How do you roll back?** `rollback.yml`: either restore the previous champion model and redeploy, or point `:latest` at an earlier verified image. Both have run in Actions (model v2 → v1).

**Where are secrets kept?** No secrets are needed for data. The GHCR push uses the built-in `GITHUB_TOKEN`; anything else goes in GitHub Actions secrets or `.env`, never in the repo.

**Why GitHub Actions and not Jenkins?** It lives with the code, needs no server to maintain, has free runners, and integrates with GHCR and Pages.

## Where the Nov 17 briefs differ from the code

The PDF briefs in `docs/` were the week-1 plan. The concepts still hold, but these points changed. Answer from the right-hand column.

| Topic | Brief said (plan) | Repo does (now) |
| --- | --- | --- |
| Status | Nothing built yet | Every stage built and green in Actions |
| Data source | Kaggle "Air Quality Data in India 2015–2020", CPCB stations, replayed week by week | CAMS model data via Open-Meteo, central-Delhi point, from 2022-08-05, fetched daily |
| AQI target | All pollutants incl. O3 | O3 left out of the target, kept as a feature |
| Gate thresholds | "Tuned in week 2" | Stuck = 4+ identical days; gap > 3 days; > 5% missing; fixed physical limits |
| Drift test | KS test or PSI | PSI only, season-matched, warning at 0.25 |
| What drift does | Drift alert triggers retraining | Drift is a warning only; retrain = lost skill vs persistence, or model age > 180 days |
| Alert thresholds | "Set in week 3" | Set: see the alert rules in the dashboards section |
| Who decides retraining | Rachit's decision rules | `src/aqi/monitor/decide.py` + the gate in `src/aqi/retrain`, run by `ct.yml` |
| Live data | Future work | Daily automated fetch already runs in CT |
