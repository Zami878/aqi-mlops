"""python -m aqi.models leaderboard [--check]

Trains every model on the pre-holdout period and scores it on the holdout. With --check, exits
non-zero unless the main model beats the persistence baseline (used as a CI step).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqi.data import fetch
from aqi.models import train


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqi.models")
    p.add_argument("cmd", choices=["leaderboard"])
    p.add_argument("--data", type=Path, default=fetch.DEFAULT_PATH)
    p.add_argument("--report", type=Path, default=Path("reports/leaderboard.json"))
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)

    board = train.leaderboard(fetch.load(args.data))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(board, indent=2))
    print(json.dumps(board, indent=2))

    if args.check:
        main_mae = board["scores"][train.MAIN_MODEL]["mae"]
        base_mae = board["scores"]["persistence"]["mae"]
        if main_mae >= base_mae:
            print(f"FAIL: {train.MAIN_MODEL} MAE {main_mae} does not beat persistence {base_mae}")
            return 1
        print(f"OK: {train.MAIN_MODEL} MAE {main_mae} < persistence {base_mae}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
