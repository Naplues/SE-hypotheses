"""Build SWE-bench dataset variants with developer hypotheses appended."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rfm.io import read_jsonl
from rfm.prompts import CONDITIONS, INTRODUCTION


def build_hypothesis_datasets(
    source: str | Path,
    prompts_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    source_path = Path(source)
    prompt_root = Path(prompts_dir)
    output_root = Path(output_dir)
    tasks = list(read_jsonl(source_path))
    if not tasks:
        raise ValueError(f"No SWE-bench tasks found in {source_path}")

    task_by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for index, task in enumerate(tasks, start=1):
        instance_id = _text(task.get("instance_id"), f"line {index}.instance_id")
        if instance_id in task_by_id:
            raise ValueError(f"Duplicate SWE-bench instance_id: {instance_id}")
        _text(task.get("problem_statement"), f"{instance_id}.problem_statement")
        task_by_id[instance_id] = task
        ordered_ids.append(instance_id)

    prompts_by_condition = {
        condition: _load_prompts(prompt_root / condition, condition, task_by_id)
        for condition in CONDITIONS
    }
    rows_by_condition: dict[str, list[dict[str, Any]]] = {}
    for condition in CONDITIONS:
        prompts = prompts_by_condition[condition]
        rows: list[dict[str, Any]] = []
        for instance_id in ordered_ids:
            prompt = prompts.get(instance_id)
            if prompt is None:
                continue
            original = task_by_id[instance_id]
            updated = dict(original)
            updated["problem_statement"] = f"{original['problem_statement']}\n\n{prompt}"
            rows.append(updated)
        rows_by_condition[condition] = rows

    datasets: dict[str, dict[str, Any]] = {}
    for condition in CONDITIONS:
        target = output_root / f"swebench_verified_test_{condition}.jsonl"
        _write_jsonl(target, rows_by_condition[condition])
        datasets[condition] = {"tasks": len(rows_by_condition[condition]), "output": str(target)}

    return {
        "source": str(source_path),
        "prompts_dir": str(prompt_root),
        "output_dir": str(output_root),
        "datasets": datasets,
    }


def _load_prompts(
    directory: Path,
    condition: str,
    task_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    if not directory.is_dir():
        raise ValueError(f"Missing {condition} prompt directory: {directory}")
    paths = sorted(directory.glob("*.txt"))
    if not paths:
        raise ValueError(f"No {condition} prompt files found in {directory}")

    prompts: dict[str, str] = {}
    for path in paths:
        instance_id = path.stem
        if instance_id in prompts:
            raise ValueError(f"Duplicate {condition} prompt for {instance_id}")
        if instance_id not in task_by_id:
            raise ValueError(f"Unknown {condition} prompt instance_id: {instance_id}")
        prompt = path.read_text(encoding="utf-8").strip()
        _validate_prompt(prompt, condition, instance_id)
        prompts[instance_id] = prompt
    return prompts


def _validate_prompt(prompt: str, condition: str, instance_id: str) -> None:
    if not prompt:
        raise ValueError(f"Empty {condition} prompt for {instance_id}")
    if not prompt.startswith(INTRODUCTION):
        raise ValueError(f"Invalid {condition} prompt introduction for {instance_id}")
    if prompt.count("<developer_hypothesis>") != 1 or prompt.count("</developer_hypothesis>") != 1:
        raise ValueError(f"Invalid {condition} developer_hypothesis block for {instance_id}")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _text(raw: Any, location: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{location} cannot be empty")
    return value
