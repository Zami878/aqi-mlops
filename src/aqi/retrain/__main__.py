"""python -m aqi.retrain {run [--force], rollback}

run: monitor -> (if retrain is warranted, or --force) train candidate -> gate -> promote/discard.
     A sensor fault blocks retraining even with --force.
rollback: restore the previous champion.
Writes reports/gate.json and appends to reports/events.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqi import events
from aqi.data import fetch
from aqi.models import features, train
from aqi.models.registry import Registry, file_sha256
from aqi.monitor import decide
from aqi.monitor.__main__ import run as monitor_run


def run(data: Path, registry: Registry, report: Path, force: bool = False) -> dict:
    df = fetch.load(data)
    mon = monitor_run(df, registry)
    if mon["decision"] == decide.BLOCKED:
        out = {"action": "blocked", "reasons": mon["reasons"]}
    elif mon["decision"] != decide.RETRAIN and not force:
        out = {"action": "skipped", "reasons": ["monitor decision: healthy"]}
    else:
        from aqi.retrain import gate

        res = gate.evaluate(df, registry)
        model = res.pop("candidate_model")
        meta = {
            "model": train.MAIN_MODEL,
            "features": features.FEATURES,
            "train_start": res["train_start"],
            "train_end": res["train_end"],
            "holdout_start": res["holdout_start"],
            "holdout_end": res["holdout_end"],
            "holdout": res["scores"]["candidate"],
            "persistence_holdout": res["scores"]["persistence"],
            "data_sha256": file_sha256(data),
            "trigger": mon["reasons"] or ["forced"],
        }
        version = registry.register(model, meta)
        if res["promote"]:
            registry.set_champion(version)
            action = "promoted"
        else:
            registry.discard(version)
            action = "rejected"
        out = {"action": action, "candidate_version": version, **res}
        out["trigger"] = meta["trigger"]

    out["monitor_decision"] = mon["decision"]
    out["champion_after"] = registry.champion_version()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, indent=2))
    events.log(
        out["action"],
        champion=out["champion_after"],
        candidate=out.get("candidate_version"),
        reasons=out.get("trigger") or out.get("reasons"),
        checks=out.get("checks"),
    )
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqi.retrain")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--force", action="store_true", help="retrain even if monitor says healthy")
    sub.add_parser("rollback")
    p.add_argument("--data", type=Path, default=fetch.DEFAULT_PATH)
    p.add_argument("--registry", type=Path, default=Path("registry"))
    p.add_argument("--report", type=Path, default=Path("reports/gate.json"))
    args = p.parse_args(argv)
    registry = Registry(args.registry)

    if args.cmd == "rollback":
        old, new = registry.rollback()
        events.log("rollback", champion=new, previous=old)
        print(f"rolled back: {old} -> {new}")
        return 0

    out = run(args.data, registry, args.report, force=args.force)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
