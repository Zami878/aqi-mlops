"""File-based model registry.

registry/
  models/<version>/model.joblib   the fitted model
  models/<version>/meta.json      training window, holdout metrics, data hash
  champion.json                   {"champion": version, "history": [older champions, newest first]}

Only src/aqi/retrain promotes or rolls back. Nothing else writes champion.json.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import joblib

DEFAULT_ROOT = Path("registry")
KEEP_VERSIONS = 6


class Registry:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.models = self.root / "models"
        self.pointer = self.root / "champion.json"

    # ---- read -------------------------------------------------------------
    def _state(self) -> dict:
        if self.pointer.exists():
            return json.loads(self.pointer.read_text())
        return {"champion": None, "history": []}

    def champion_version(self) -> str | None:
        return self._state()["champion"]

    def history(self) -> list[str]:
        return self._state()["history"]

    def versions(self) -> list[str]:
        if not self.models.exists():
            return []
        return sorted((p.name for p in self.models.iterdir() if p.is_dir()), key=_version_num)

    def meta(self, version: str) -> dict:
        return json.loads((self.models / version / "meta.json").read_text())

    def load(self, version: str):
        return joblib.load(self.models / version / "model.joblib")

    def load_champion(self):
        version = self.champion_version()
        if version is None:
            return None, None
        return self.load(version), self.meta(version)

    # ---- write ------------------------------------------------------------
    def register(self, model, meta: dict) -> str:
        """Store a candidate. Does NOT make it champion."""
        versions = self.versions()
        version = f"v{_version_num(versions[-1]) + 1}" if versions else "v1"
        path = self.models / version
        path.mkdir(parents=True)
        joblib.dump(model, path / "model.joblib")
        meta = {**meta, "version": version, "registered_at": _now()}
        (path / "meta.json").write_text(json.dumps(meta, indent=2))
        return version

    def _write_state(self, state: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.pointer.write_text(json.dumps(state, indent=2))

    def set_champion(self, version: str) -> None:
        state = self._state()
        if state["champion"]:
            state["history"].insert(0, state["champion"])
        state["champion"] = version
        state["updated_at"] = _now()
        self._write_state(state)
        self._prune(state)

    def rollback(self) -> tuple[str, str]:
        """Restore the previous champion. Returns (from_version, to_version)."""
        state = self._state()
        if not state["history"]:
            raise RuntimeError("no previous champion to roll back to")
        current = state["champion"]
        state["champion"] = state["history"].pop(0)
        state["updated_at"] = _now()
        self._write_state(state)
        return current, state["champion"]

    def _prune(self, state: dict) -> None:
        keep = {state["champion"], *state["history"][: KEEP_VERSIONS - 1]}
        state["history"] = [v for v in state["history"] if v in keep]
        self._write_state(state)
        for v in self.versions():
            if v not in keep:
                shutil.rmtree(self.models / v)

    def discard(self, version: str) -> None:
        """Remove a rejected candidate."""
        if version not in {self.champion_version(), *self.history()}:
            shutil.rmtree(self.models / version, ignore_errors=True)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _version_num(v: str) -> int:
    return int(v.lstrip("v"))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
