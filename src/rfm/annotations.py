"""Load adjudicated trajectory labels used by confirmatory RQ analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rfm.io import read_csv


def load_annotations(path: str | Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in read_csv(path):
        run_id = str(row.get("run_id", "")).strip()
        if not run_id or run_id in result:
            raise ValueError(f"Missing or duplicate annotation run_id: {run_id!r}")
        anchored = _label(row.get("anchored"), f"{run_id}.anchored")
        contradicted = _label(row.get("contradiction_seen"), f"{run_id}.contradiction_seen")
        recovered = _label(row.get("recovered"), f"{run_id}.recovered")
        persistent = _optional_label(row.get("persistent"), f"{run_id}.persistent")
        if recovered and not (anchored and contradicted):
            raise ValueError(f"{run_id}: recovered requires anchored and contradiction_seen")
        result[run_id] = {
            "anchored": anchored,
            "contradiction_seen": contradicted,
            "recovered": recovered,
            "persistent": persistent,
            "contradiction_step": _optional_int(row.get("contradiction_step"), run_id),
            "recovery_step": _optional_int(row.get("recovery_step"), run_id),
        }
    return result


def _label(value: Any, location: str) -> bool:
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{location} must be yes or no")


def _optional_label(value: Any, location: str) -> bool | None:
    return None if str(value or "").strip() == "" else _label(value, location)


def _optional_int(value: Any, run_id: str) -> int | None:
    if str(value or "").strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{run_id} annotation step must be an integer") from exc
