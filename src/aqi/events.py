"""Append-only pipeline event log (reports/events.jsonl), read by the dashboard."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = Path("reports/events.jsonl")


def log(event: str, path: Path | None = None, **details) -> dict:
    path = path or DEFAULT_PATH
    entry = {
        "time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "run": os.getenv("GITHUB_RUN_ID", "local"),
        **details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read(path: Path | None = None, limit: int | None = None) -> list[dict]:
    path = path or DEFAULT_PATH
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows[-limit:] if limit else rows
