"""Minimal shared data validation for constructed tasks and experiment runs."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any


class Condition(str, Enum):
    ORIGINAL = "original"
    CORRECT = "correct"
    WRONG_LOCATION = "wrong_location"
    WRONG_CAUSE = "wrong_cause"
    WRONG_REPAIR = "wrong_repair"


MISLEADING_CONDITIONS = (
    Condition.WRONG_LOCATION,
    Condition.WRONG_CAUSE,
    Condition.WRONG_REPAIR,
)


def load_tasks(directory: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(directory)
    paths = sorted(path for path in root.glob("*.json") if path.name != "construction-summary.json")
    if not paths:
        raise ValueError(f"No constructed task JSON files found in {root}")
    tasks: dict[str, dict[str, Any]] = {}
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Task must be a JSON object: {path}")
        instance_id = _text(raw.get("instance_id"), f"{path}.instance_id")
        if instance_id in tasks:
            raise ValueError(f"Duplicate instance_id: {instance_id}")
        ground = raw.get("ground_truth")
        hypotheses = raw.get("hypotheses")
        if not isinstance(ground, dict) or not isinstance(hypotheses, dict):
            raise ValueError(f"{instance_id} requires ground_truth and hypotheses objects")
        _strings(ground.get("files"), f"{instance_id}.ground_truth.files", required=True)
        _strings(ground.get("symbols", []), f"{instance_id}.ground_truth.symbols")
        _text(ground.get("cause"), f"{instance_id}.ground_truth.cause")
        _text(ground.get("repair"), f"{instance_id}.ground_truth.repair")
        for condition in MISLEADING_CONDITIONS:
            values = hypotheses.get(condition.value)
            if not isinstance(values, list) or not values:
                raise ValueError(f"{instance_id}.hypotheses.{condition.value} is required")
        tasks[instance_id] = raw
    return tasks


def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip().casefold()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _text(raw: Any, location: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{location} cannot be empty")
    return value


def _strings(raw: Any, location: str, required: bool = False) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{location} must be an array of strings")
    values = [item.strip() for item in raw if item.strip()]
    if required and not values:
        raise ValueError(f"{location} cannot be empty")
    return values
