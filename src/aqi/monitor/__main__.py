"""python -m aqi.monitor [--simulate-fault]

Validates the latest data, measures drift and recent error for the champion, and writes the
decision to reports/monitor.json. --simulate-fault injects a stuck PM2.5 sensor into the last
6 days (in memory only, labelled "simulated") to demonstrate that the gate blocks retraining.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from aqi import events
from aqi.data import fetch, validate
from aqi.models.registry import Registry
from aqi.monitor import decide, drift


def run(df: pd.DataFrame, registry: Registry, simulated: bool = False) -> dict:
    val = validate.validate(df).to_dict()
    model, meta = registry.load_champion()
    if model is not None:
        psi = drift.drift(df, meta["train_end"])
        perf = drift.performance(df, model, meta["train_end"])
    else:
        psi, perf = {}, {"n": 0, "mae": None, "persistence_mae": None}
    result = decide.decide(val, psi, perf, meta)
    return {
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "simulated": simulated,
        "data_end": val["end"],
        "champion": meta["version"] if meta else None,
        "validation": val,
        "psi": psi,
        "performance": perf,
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqi.monitor")
    p.add_argument("--data", type=Path, default=fetch.DEFAULT_PATH)
    p.add_argument("--registry", type=Path, default=Path("registry"))
    p.add_argument("--report", type=Path, default=Path("reports/monitor.json"))
    p.add_argument("--simulate-fault", action="store_true")
    args = p.parse_args(argv)

    df = fetch.load(args.data)
    if args.simulate_fault:
        df.iloc[-6:, df.columns.get_loc("pm2_5")] = df["pm2_5"].iloc[-7]
    report = run(df, Registry(args.registry), simulated=args.simulate_fault)

    if not args.simulate_fault:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
        events.log("monitor", decision=report["decision"], reasons=report["reasons"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
