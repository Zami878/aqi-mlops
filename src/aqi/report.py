"""python -m aqi.report  ->  site/index.html

Static pipeline dashboard published to GitHub Pages by CI. Everything on it is read from the
repo: the data snapshot, the registry champion and the reports written by the pipeline.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

import pandas as pd

from aqi.data import cpcb, fetch
from aqi.models import features, train
from aqi.models.registry import Registry

REPO = os.getenv("GITHUB_REPOSITORY", "Zami878/aqi-mlops")
CPCB_COLORS = {
    "Good": "#00b050",
    "Satisfactory": "#92d050",
    "Moderate": "#e6c000",
    "Poor": "#ff9900",
    "Very Poor": "#ff0000",
    "Severe": "#9e1e1e",
}
DECISIONS = {
    "healthy": ("good", "✓", "Healthy: champion keeps serving"),
    "retrain": ("warning", "↻", "Retrain: candidate sent to the gate"),
    "blocked_sensor_fault": ("critical", "⚠", "Blocked: sensor fault, no retraining"),
}
EVENT_LABELS = {
    "monitor": "Monitor check",
    "promoted": "Model promoted",
    "rejected": "Candidate rejected",
    "blocked": "Retrain blocked",
    "skipped": "Retrain skipped",
    "rollback": "Rollback",
}


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def esc(x) -> str:
    return html.escape(str(x))


# ---------------------------------------------------------------- charts (inline SVG)
W, H = 880, 300
PAD_L, PAD_R, PAD_T, PAD_B = 44, 110, 14, 30


def line_chart(dates: list[str], actual: list[float], pred: list[float]) -> str:
    n = len(dates)
    y_max = max(100, (int(max(actual + pred) / 100) + 1) * 100)
    pw, ph = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(i):
        return PAD_L + pw * i / (n - 1)

    def y(v):
        return PAD_T + ph * (1 - v / y_max)

    grid = []
    for v in range(0, y_max + 1, 100):
        grid.append(
            f'<line x1="{PAD_L}" x2="{PAD_L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
            f'<text x="{PAD_L - 8}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">{v}</text>'
        )
    ticks = []
    for i in range(0, n, max(1, n // 6)):
        label = pd.Timestamp(dates[i]).strftime("%d %b")
        ticks.append(
            f'<text x="{x(i):.1f}" y="{H - 8}" class="tick" text-anchor="middle">{label}</text>'
        )

    def path(vals):
        return "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))

    end_a, end_p = y(actual[-1]), y(pred[-1])
    if abs(end_a - end_p) < 16:  # keep the two end labels from colliding
        mid = (end_a + end_p) / 2
        end_a, end_p = (mid - 8, mid + 8) if actual[-1] >= pred[-1] else (mid + 8, mid - 8)
    data = json.dumps({"d": dates, "a": actual, "p": pred})
    return f"""
<div class="chart" data-series='{esc(data)}'>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Observed AQI and next-day forecast">
  {"".join(grid)}{"".join(ticks)}
  <path d="{path(actual)}" class="ln s1"/>
  <path d="{path(pred)}" class="ln s2"/>
  <text x="{PAD_L + pw + 8}" y="{end_a + 4:.1f}" class="dl">Observed</text>
  <text x="{PAD_L + pw + 8}" y="{end_p + 4:.1f}" class="dl">Forecast</text>
  <line class="xh" y1="{PAD_T}" y2="{PAD_T + ph}" x1="-10" x2="-10"/>
  <circle class="dot s1f" r="4" cx="-10" cy="-10"/><circle class="dot s2f" r="4" cx="-10" cy="-10"/>
  <rect class="hit" x="{PAD_L}" y="{PAD_T}" width="{pw}" height="{ph}"
        data-x0="{PAD_L}" data-pw="{pw}" data-pt="{PAD_T}" data-ph="{ph}" data-ymax="{y_max}"/>
</svg><div class="tip" hidden></div></div>"""


def bar_chart(items: list[tuple[str, float]], fmt: str, ref: float | None = None,
              ref_label: str = "", highlight: str | None = None) -> str:  # fmt: skip
    bw, row, lab = 320, 34, 130
    vmax = max([v for _, v in items] + ([ref] if ref else [])) * 1.15
    hgt = row * len(items) + (26 if ref else 6)
    out = [f'<svg viewBox="0 0 {lab + bw + 70} {hgt}" role="img" class="bars">']
    if ref:  # drawn first so bars and value labels sit on top of the reference line
        rx = lab + bw * ref / vmax
        out.append(
            f'<line x1="{rx:.1f}" x2="{rx:.1f}" y1="0" y2="{hgt - 20}" class="ref"/>'
            f'<text x="{rx:.1f}" y="{hgt - 6}" class="tick" text-anchor="middle">'
            f"{esc(ref_label)}</text>"
        )
    for i, (name, v) in enumerate(items):
        yy = i * row + 4
        w = max(2, bw * v / vmax)
        cls = "bar hl" if name == highlight else "bar"
        out.append(
            f'<g class="bh"><title>{esc(name)}: {v:{fmt}}</title>'
            f'<text x="{lab - 10}" y="{yy + 17}" class="lab" text-anchor="end">{esc(name)}</text>'
            f'<rect x="{lab}" y="{yy + 4}" width="{w:.1f}" height="20" rx="4" class="{cls}"/>'
            f'<text x="{lab + w + 8:.1f}" y="{yy + 18}" class="val halo">{v:{fmt}}</text></g>'
        )
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- page
def build(home: Path = Path(".")) -> str:
    df = fetch.load(home / fetch.DEFAULT_PATH)
    reg = Registry(home / "registry")
    model, meta = reg.load_champion()
    mon = _read(home / "reports/monitor.json") or {}
    gate = _read(home / "reports/gate.json") or {}
    board = _read(home / "reports/leaderboard.json") or {}
    events = []
    ev_path = home / "reports/events.jsonl"
    if ev_path.exists():
        events = [json.loads(line) for line in ev_path.read_text().splitlines() if line.strip()]

    frame = features.build(df)
    last = frame.iloc[[-1]]
    fc = round(float(train.predict(model, last)[0]), 1)
    fc_cat = cpcb.category(fc)
    for_date = (last.index[0] + pd.Timedelta(days=1)).strftime("%a %d %b %Y")

    # one-day-ahead forecasts on days the champion never trained on
    unseen = features.training_frame(df)
    unseen = unseen[unseen.index > pd.Timestamp(meta["train_end"])]
    preds = train.predict(model, unseen)
    target_dates = [str((d + pd.Timedelta(days=1)).date()) for d in unseen.index]
    actual = [round(float(v), 1) for v in unseen[features.TARGET]]
    pred = [round(float(v), 1) for v in preds]
    unseen_mae = train.metrics(actual, pred)["mae"]
    unseen_pers = train.metrics(actual, unseen["aqi_lag0"])["mae"]

    decision = mon.get("decision", "healthy")
    d_cls, d_icon, d_text = DECISIONS.get(decision, ("warning", "?", decision))
    reasons = mon.get("reasons") or []
    warnings = mon.get("drift_warnings") or []

    lb = board.get("scores", {})
    lb_items = [
        (n, lb[n]["mae"]) for n in ("persistence", "ridge", "hgb") if n in lb
    ]  # fmt: skip
    names = {"persistence": "Persistence", "ridge": "Ridge", "hgb": "Gradient boosting"}
    lb_items = [(names[n], v) for n, v in lb_items]
    psi_items = sorted(mon.get("psi", {}).items(), key=lambda kv: -kv[1])

    checks = gate.get("checks") or {}
    check_rows = "".join(
        f'<tr><td>{esc(k.replace("_", " "))}</td><td class="{"ok" if v else "bad"}">'
        f"{'✓ pass' if v else '✗ fail'}</td></tr>"
        for k, v in checks.items()
    )
    sc = gate.get("scores") or {}
    score_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{s['mae']}</td><td>{s['rmse']}</td></tr>"
        for k, s in sc.items()
        if s
    )
    ev_rows = "".join(
        f"<tr><td>{esc(e['time'].replace('T', ' ').rstrip('Z'))}</td>"
        f"<td>{esc(EVENT_LABELS.get(e['event'], e['event']))}</td>"
        f"<td>{esc(e.get('decision') or e.get('champion') or '')}</td>"
        f"<td class='muted'>{esc('; '.join(e.get('reasons') or []) if isinstance(e.get('reasons'), list) else '')}</td></tr>"  # noqa: E501
        for e in reversed(events[-12:])
    )
    history = reg.history()
    run_url = f"https://github.com/{REPO}/actions"
    sha = os.getenv("GITHUB_SHA", "local")[:7]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delhi AQI pipeline dashboard (PB-3)</title>
<style>{CSS}</style></head>
<body><div class="viz-root">
<header>
  <div><h1>Delhi AQI: CI/CD/CT pipeline</h1>
  <p class="sub">PB-3 · Next-day CPCB AQI for New Delhi, retrained and promoted automatically.
  Data through {esc(str(df.index.max().date()))}.</p></div>
  <nav><a href="{run_url}">Pipeline runs ↗</a>
  <a href="https://github.com/{REPO}">Repository ↗</a></nav>
</header>

<section class="tiles">
  <div class="tile hero">
    <div class="k">Forecast for {esc(for_date)}</div>
    <div class="big">{fc:.0f}</div>
    <div class="cat"><span class="sw" style="background:{CPCB_COLORS[fc_cat]}"></span>{esc(fc_cat)}
      <span class="muted">· CPCB AQI</span></div>
  </div>
  <div class="tile"><div class="k">Champion model</div>
    <div class="mid">{esc(meta["version"])}</div>
    <div class="muted">Gradient boosting · trained to {esc(meta["train_end"])}</div></div>
  <div class="tile"><div class="k">Error on unseen days (MAE)</div>
    <div class="mid">{unseen_mae}</div>
    <div class="muted">vs {unseen_pers} for persistence · {len(actual)} days</div></div>
  <div class="tile"><div class="k">Latest monitor decision</div>
    <div class="status {d_cls}"><span class="ic">{d_icon}</span>{esc(d_text)}</div>
    <div class="muted">{esc("; ".join(reasons) or "No retrain trigger fired")}</div></div>
</section>

<section class="card">
  <h2>Observed AQI vs the champion's next-day forecast</h2>
  <p class="muted">Only days after the champion's training window, so every forecast here is
  out-of-sample. Hover for values.</p>
  <div class="legend"><span><i class="s1b"></i>Observed AQI</span>
    <span><i class="s2b"></i>Forecast made the day before</span></div>
  {line_chart(target_dates, actual, pred)}
</section>

<div class="two">
<section class="card">
  <h2>Model leaderboard</h2>
  <p class="muted">MAE on the {esc(board.get("holdout_start", ""))} to
  {esc(board.get("holdout_end", ""))} holdout, time-ordered split. Lower is better.</p>
  {bar_chart(lb_items, ".1f", highlight="Gradient boosting")}
</section>
<section class="card">
  <h2>Drift vs the same days in past years</h2>
  <p class="muted">PSI per feature, last 30 days. Above 0.25 is a warning on the Grafana
  dashboard; it does not trigger retraining by itself.</p>
  {bar_chart(psi_items, ".2f", ref=0.25, ref_label="0.25 warning")}
  <p class="muted small">Warnings now: {esc(", ".join(warnings) or "none")}</p>
</section>
</div>

<div class="two">
<section class="card">
  <h2>Latest promotion gate</h2>
  <p class="muted">Action: <b>{esc(gate.get("action", "n/a"))}</b>
  · holdout {esc(gate.get("holdout_start", ""))} to {esc(gate.get("holdout_end", ""))}</p>
  <table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>{check_rows}</tbody></table>
  <table><thead><tr><th>Model</th><th>MAE</th><th>RMSE</th></tr></thead>
  <tbody>{score_rows}</tbody></table>
  <p class="muted small">Rollback history: {esc(", ".join(history) or "none yet")}</p>
</section>
<section class="card">
  <h2>Pipeline events</h2>
  <table><thead><tr><th>Time (UTC)</th><th>Event</th><th>Result</th><th>Why</th></tr></thead>
  <tbody>{ev_rows}</tbody></table>
</section>
</div>

<footer class="muted small">Pollutants: CAMS model via Open-Meteo for a central-Delhi grid point
(modelled, not CPCB station readings); AQI computed with CPCB breakpoints, ozone excluded
(see README). Built by CI from commit {esc(sha)}.</footer>
</div>
<script>{JS}</script>
</body></html>"""


ASSETS = Path(__file__).parent / "report_assets"
CSS = (ASSETS / "dashboard.css").read_text()
JS = (ASSETS / "dashboard.js").read_text()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqi.report")
    p.add_argument("--out", type=Path, default=Path("site/index.html"))
    args = p.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build())
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
