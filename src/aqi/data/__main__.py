"""python -m aqi.data {fetch,validate}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqi.data import fetch, validate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqi.data")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download Delhi data and write the daily CSV")
    f.add_argument("--out", type=Path, default=fetch.DEFAULT_PATH)
    v = sub.add_parser("validate", help="run the validation gate")
    v.add_argument("--path", type=Path, default=fetch.DEFAULT_PATH)
    v.add_argument("--report", type=Path, default=Path("reports/validation.json"))
    v.add_argument("--max-age-days", type=int, default=None)
    args = p.parse_args(argv)

    if args.cmd == "fetch":
        df = fetch.fetch()
        path = fetch.save(df, args.out)
        span = f"{df.index.min().date()} .. {df.index.max().date()}"
        print(f"wrote {len(df)} days ({span}) to {path}")
        return 0

    rep = validate.validate(fetch.load(args.path), max_age_days=args.max_age_days)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(rep.to_dict(), indent=2))
    print(json.dumps(rep.to_dict(), indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
