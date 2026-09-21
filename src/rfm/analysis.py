"""Analyze completed RFM runs and produce RQ1-RQ3 report data."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rfm.annotations import load_annotations
from rfm.behavior import extract_behavior
from rfm.events import load_events
from rfm.io import dump_json, write_csv
from rfm.models import MISLEADING_CONDITIONS, Condition, load_tasks
from rfm.statistics import (
    exact_mcnemar,
    holm_adjust,
    median,
    paired_risk_difference,
    wilcoxon_signed_rank,
    wilson_interval,
)

NUMERIC_METRICS = ("tokens_total", "tool_calls", "runtime_seconds", "steps")


@dataclass(frozen=True)
class Run:
    run_id: str
    block_id: str
    instance_id: str
    agent_id: str
    model_id: str
    repetition: int
    condition: Condition
    hypothesis_id: str | None
    directory: Path


def analyze_results(
    tasks_dir: str | Path,
    runs_dir: str | Path,
    output_dir: str | Path,
    *,
    annotations_path: str | Path | None = None,
    use_proxies: bool = False,
    seed: int = 0,
) -> dict[str, Any]:
    if bool(annotations_path) == bool(use_proxies):
        raise ValueError("Choose exactly one of annotations_path or use_proxies")
    tasks = load_tasks(tasks_dir)
    runs = discover_runs(runs_dir)
    _validate_blocks(runs)
    annotations = load_annotations(annotations_path) if annotations_path else {}
    rows = [_run_row(run, tasks, annotations, use_proxies) for run in runs]
    synthetic_values = {bool(row["synthetic"]) for row in rows}
    if len(synthetic_values) > 1:
        raise ValueError("Synthetic and real runs cannot be combined")
    report = {
        "run_count": len(rows),
        "block_count": len({row["block_id"] for row in rows}),
        "synthetic": synthetic_values == {True},
        "behavior_labels": "automatic_proxy" if use_proxies else "human_adjudication",
        "rq1": _rq1(rows, seed),
        "rq2": _rq2(rows),
        "rq3": _rq3(rows),
    }
    output = Path(output_dir).resolve()
    write_csv(output / "run-table.csv", rows)
    dump_json(output / "report.json", report)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def discover_runs(directory: str | Path) -> list[Run]:
    root = Path(directory).resolve()
    paths = sorted(root.glob("*/run.json"))
    if not paths:
        raise ValueError(f"No run.json files found in {root}")
    runs: list[Run] = []
    seen: set[str] = set()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        run_id = _text(raw.get("run_id", path.parent.name), f"{path}.run_id")
        if run_id in seen:
            raise ValueError(f"Duplicate run_id: {run_id}")
        seen.add(run_id)
        instance_id = _text(raw.get("instance_id"), f"{run_id}.instance_id")
        agent_id = _text(raw.get("agent_id"), f"{run_id}.agent_id")
        model_id = _text(raw.get("model_id"), f"{run_id}.model_id")
        repetition = int(raw.get("repetition", 1))
        condition = Condition(raw.get("condition"))
        block_id = str(raw.get("block_id") or f"{instance_id}|{agent_id}|{model_id}|r{repetition}")
        for required in ("result.json", "trajectory.jsonl"):
            if not (path.parent / required).exists():
                raise ValueError(f"Missing {required} for {run_id}")
        runs.append(
            Run(
                run_id=run_id,
                block_id=block_id,
                instance_id=instance_id,
                agent_id=agent_id,
                model_id=model_id,
                repetition=repetition,
                condition=condition,
                hypothesis_id=str(raw["hypothesis_id"]) if raw.get("hypothesis_id") else None,
                directory=path.parent,
            )
        )
    return runs


def _run_row(
    run: Run,
    tasks: dict[str, dict[str, Any]],
    annotations: dict[str, dict[str, Any]],
    use_proxies: bool,
) -> dict[str, Any]:
    if run.instance_id not in tasks:
        raise ValueError(f"No constructed task for run {run.run_id}: {run.instance_id}")
    result = json.loads((run.directory / "result.json").read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"result.json must be an object for {run.run_id}")
    events = load_events(run.directory / "trajectory.jsonl")
    behavior = extract_behavior(
        run.condition,
        tasks[run.instance_id],
        events,
        hypothesis_id=run.hypothesis_id,
    )
    row: dict[str, Any] = {
        "run_id": run.run_id,
        "block_id": run.block_id,
        "instance_id": run.instance_id,
        "agent_id": run.agent_id,
        "model_id": run.model_id,
        "repetition": run.repetition,
        "condition": run.condition.value,
        "status": result.get("status", "completed"),
        "resolved": _boolean(result.get("resolved", False), f"{run.run_id}.resolved"),
        "synthetic": _boolean(result.get("synthetic", False), f"{run.run_id}.synthetic"),
        "tokens_total": _first_number(
            result.get("tokens_total"),
            sum((event.tokens_input or 0) + (event.tokens_output or 0) for event in events),
        ),
        "tool_calls": _first_number(
            result.get("tool_calls"),
            sum(event.event_type == "tool_call" for event in events),
        ),
        "runtime_seconds": _number(result.get("runtime_seconds")),
        "steps": _first_number(result.get("steps"), len(events)),
        **behavior.to_dict(),
    }
    if run.condition not in MISLEADING_CONDITIONS:
        row.update(
            anchored=None,
            contradiction_seen=None,
            recovered=None,
            persistent=None,
            contradiction_step=None,
            recovery_step=None,
        )
    elif use_proxies:
        row.update(
            anchored=behavior.anchoring_proxy,
            contradiction_seen=behavior.recovery_proxy,
            recovered=behavior.recovery_proxy,
            persistent=False,
            contradiction_step=behavior.first_gold_step,
            recovery_step=behavior.first_gold_step,
        )
    else:
        if run.run_id not in annotations:
            raise ValueError(f"Missing annotation for {run.run_id}")
        row.update(annotations[run.run_id])
    return row


def _validate_blocks(runs: list[Run]) -> None:
    required = set(Condition)
    by_block: dict[str, list[Condition]] = {}
    for run in runs:
        by_block.setdefault(run.block_id, []).append(run.condition)
    invalid = {
        block: [condition.value for condition in values]
        for block, values in by_block.items()
        if set(values) != required or len(values) != len(required)
    }
    if invalid:
        raise ValueError(f"Incomplete or duplicated condition blocks: {invalid}")


def _rq1(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    rates = {
        condition.value: _rate(
            sum(bool(row["resolved"]) for row in rows if row["condition"] == condition.value),
            sum(row["condition"] == condition.value for row in rows),
        )
        for condition in Condition
    }
    by_block = {(row["block_id"], row["condition"]): row for row in rows}
    comparisons: list[dict[str, Any]] = []
    for condition in Condition:
        if condition is Condition.ORIGINAL:
            continue
        pairs = [
            (
                by_block[(block, Condition.ORIGINAL.value)],
                by_block[(block, condition.value)],
            )
            for block in sorted({row["block_id"] for row in rows})
        ]
        left = [bool(a["resolved"]) for a, _ in pairs]
        right = [bool(b["resolved"]) for _, b in pairs]
        comparison: dict[str, Any] = {
            "condition": condition.value,
            "paired_n": len(pairs),
            "mcnemar": exact_mcnemar(left, right),
            "paired_risk_difference": paired_risk_difference(
                left, right, seed=seed + len(comparisons)
            ),
            "efficiency": {},
        }
        for metric in NUMERIC_METRICS:
            usable = [
                (float(a[metric]), float(b[metric]))
                for a, b in pairs
                if a[metric] is not None and b[metric] is not None
            ]
            if usable:
                test = wilcoxon_signed_rank([a for a, _ in usable], [b for _, b in usable])
                test["median_paired_difference"] = median([b - a for a, b in usable])
                comparison["efficiency"][metric] = test
        comparisons.append(comparison)
    _adjust_p_values(comparisons)
    return {"resolve_rates": rates, "paired_comparisons": comparisons}


def _rq2(rows: list[dict[str, Any]]) -> dict[str, Any]:
    misleading = _misleading(rows)
    by_condition = {
        condition.value: _rate(
            sum(bool(row["anchored"]) for row in misleading if row["condition"] == condition.value),
            sum(row["condition"] == condition.value for row in misleading),
        )
        for condition in MISLEADING_CONDITIONS
    }
    return {
        "anchoring_rate": _rate(sum(bool(row["anchored"]) for row in misleading), len(misleading)),
        "by_condition": by_condition,
    }


def _rq3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in _misleading(rows) if row["anchored"] and row["contradiction_seen"]]
    persistence = [row for row in eligible if row["persistent"] is not None]
    latencies = [
        float(row["recovery_step"]) - float(row["contradiction_step"])
        for row in eligible
        if row["recovered"]
        and row["recovery_step"] is not None
        and row["contradiction_step"] is not None
    ]
    return {
        "eligible": len(eligible),
        "recovery_rate": _rate(sum(bool(row["recovered"]) for row in eligible), len(eligible)),
        "persistence_rate": (
            _rate(sum(bool(row["persistent"]) for row in persistence), len(persistence))
            if persistence
            else None
        ),
        "median_recovery_latency_steps": median(latencies) if latencies else None,
    }


def _adjust_p_values(comparisons: list[dict[str, Any]]) -> None:
    adjusted = holm_adjust([item["mcnemar"]["p_value"] for item in comparisons])
    for item, value in zip(comparisons, adjusted, strict=True):
        item["mcnemar"]["p_holm"] = value
    for metric in NUMERIC_METRICS:
        selected = [item for item in comparisons if metric in item["efficiency"]]
        values = holm_adjust([item["efficiency"][metric]["p_value"] for item in selected])
        for item, value in zip(selected, values, strict=True):
            item["efficiency"][metric]["p_holm"] = value


def _rate(successes: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "ci95_low": None if math.isnan(low) else low,
        "ci95_high": None if math.isnan(high) else high,
    }


def _misleading(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = {condition.value for condition in MISLEADING_CONDITIONS}
    return [row for row in rows if row["condition"] in values]


def _number(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def _first_number(value: Any, fallback: int | float) -> float:
    parsed = _number(value)
    return float(fallback) if parsed is None else parsed


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{location} must be true or false")
    return value


def _text(value: Any, location: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{location} cannot be empty")
    return text


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# RFM experiment report", "", "## RQ1 — Repair effectiveness", ""]
    lines.extend(
        [
            "| Condition | Resolved | Total | Rate | 95% CI |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for condition, value in report["rq1"]["resolve_rates"].items():
        rate = "NA" if value["rate"] is None else f"{value['rate']:.3f}"
        interval = (
            "NA"
            if value["ci95_low"] is None
            else f"[{value['ci95_low']:.3f}, {value['ci95_high']:.3f}]"
        )
        lines.append(
            f"| {condition} | {value['successes']} | {value['total']} | {rate} | {interval} |"
        )
    rq2 = report["rq2"]["anchoring_rate"]
    rq3 = report["rq3"]["recovery_rate"]
    lines.extend(
        [
            "",
            "## RQ2 — Anchoring",
            "",
            f"Anchored runs: {rq2['successes']}/{rq2['total']}.",
            "",
            "## RQ3 — Recovery",
            "",
            f"Recovered eligible runs: {rq3['successes']}/{rq3['total']}.",
            "",
            "Full paired tests, effect sizes, and corrected p-values are in `report.json`.",
            "",
        ]
    )
    return "\n".join(lines)
