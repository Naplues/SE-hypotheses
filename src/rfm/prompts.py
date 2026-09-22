"""Render compact developer-hypothesis prompts from constructed tasks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

INTRODUCTION = (
    "The following issue analysis was provided by a developer familiar with the codebase."
)
CONDITIONS = ("CH", "WLH", "WCH", "WRH")


def generate_hypothesis_prompts(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source_root = Path(input_dir)
    target_root = Path(output_dir)
    paths = sorted(
        path for path in source_root.glob("*.json") if path.name != "construction-summary.json"
    )
    if not paths:
        raise ValueError(f"No constructed task JSON files found in {source_root}")

    completed: list[str] = []
    skipped: list[dict[str, str]] = []
    for path in paths:
        instance_id = path.stem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            instance_id = _text(raw.get("instance_id"), "instance_id")
            prompts = render_task_prompts(raw)
            filename = f"{_safe_slug(instance_id)}.txt"
            for condition, prompt in prompts.items():
                _write_text(target_root / condition / filename, prompt)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            skipped.append({"instance_id": instance_id, "reason": str(exc)})
            continue
        completed.append(instance_id)

    return {
        "selected": len(paths),
        "completed": completed,
        "skipped": skipped,
        "output_dir": str(target_root),
    }


def render_task_prompts(task: dict[str, Any]) -> dict[str, str]:
    instance_id = _text(task.get("instance_id"), "instance_id")
    ground = _mapping(task.get("ground_truth"), f"{instance_id}.ground_truth")
    hypotheses = _mapping(task.get("hypotheses"), f"{instance_id}.hypotheses")

    ground_files = _strings(ground.get("files"), f"{instance_id}.ground_truth.files", True)
    ground_symbols = _strings(ground.get("symbols", []), f"{instance_id}.ground_truth.symbols")
    ground_cause = _text(ground.get("cause"), f"{instance_id}.ground_truth.cause")
    ground_repair = _text(ground.get("repair"), f"{instance_id}.ground_truth.repair")

    wrong_location = _single_candidate(hypotheses, "wrong_location", instance_id)
    wrong_cause = _single_candidate(hypotheses, "wrong_cause", instance_id)
    wrong_repair = _single_candidate(hypotheses, "wrong_repair", instance_id)

    location_files = _strings(
        wrong_location.get("files"), f"{instance_id}.wrong_location.files", True
    )
    location_symbols = _strings(
        wrong_location.get("symbols", []), f"{instance_id}.wrong_location.symbols"
    )

    blocks = {
        "CH": _sections(
            ("Suspected defect files", _bullets(ground_files)),
            ("Suspected symbols", _bullets(ground_symbols)),
            ("Suspected root cause", ground_cause),
            ("Suggested repair strategy", ground_repair),
        ),
        "WLH": _sections(
            ("Suspected defect files", _bullets(location_files)),
            ("Suspected symbols", _bullets(location_symbols)),
        ),
        "WCH": _sections(
            (
                "Suspected root cause",
                _text(wrong_cause.get("cause"), f"{instance_id}.wrong_cause.cause"),
            )
        ),
        "WRH": _sections(
            (
                "Suggested repair strategy",
                _text(wrong_repair.get("repair"), f"{instance_id}.wrong_repair.repair"),
            )
        ),
    }
    return {condition: _wrap(blocks[condition]) for condition in CONDITIONS}


def _single_candidate(
    hypotheses: dict[str, Any], category: str, instance_id: str
) -> dict[str, Any]:
    values = hypotheses.get(category)
    if not isinstance(values, list) or len(values) != 1:
        count = len(values) if isinstance(values, list) else 0
        raise ValueError(f"{instance_id}.{category} requires exactly one candidate; found {count}")
    return _mapping(values[0], f"{instance_id}.{category}[0]")


def _wrap(block: str) -> str:
    if "<developer_hypothesis>" in block or "</developer_hypothesis>" in block:
        raise ValueError("Hypothesis content contains a reserved XML tag")
    return f"{INTRODUCTION}\n\n<developer_hypothesis>\n{block}\n</developer_hypothesis>\n"


def _sections(*sections: tuple[str, str]) -> str:
    return "\n\n".join(f"{title}:\n{body}" for title, body in sections if body)


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def _mapping(raw: Any, location: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{location} must be an object")
    return raw


def _text(raw: Any, location: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{location} cannot be empty")
    return value


def _strings(raw: Any, location: str, required: bool = False) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
        raise ValueError(f"{location} must be an array of strings")
    values = [value.strip() for value in raw if value.strip()]
    if required and not values:
        raise ValueError(f"{location} cannot be empty")
    return values


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not slug:
        raise ValueError(f"Cannot create a filename from {value!r}")
    return slug


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
