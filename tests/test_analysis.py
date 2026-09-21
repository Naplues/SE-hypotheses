import json
from pathlib import Path

from rfm.analysis import analyze_results


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    tasks = tmp_path / "tasks"
    runs = tmp_path / "runs"
    tasks.mkdir()
    task = {
        "instance_id": "owner__repo-1",
        "ground_truth": {
            "files": ["src/gold.py"],
            "symbols": ["gold"],
            "cause": "real cause",
            "repair": "real repair",
        },
        "hypotheses": {
            "wrong_location": [
                {
                    "id": "wl1",
                    "files": ["src/wrong.py"],
                    "symbols": ["wrong"],
                    "why_plausible": "plausible",
                    "why_incorrect": "incorrect",
                }
            ],
            "wrong_cause": [
                {
                    "id": "wc1",
                    "cause": "cache",
                    "keywords": ["cache"],
                    "why_plausible": "plausible",
                    "why_incorrect": "incorrect",
                }
            ],
            "wrong_repair": [
                {
                    "id": "wr1",
                    "repair": "add a guard clause",
                    "keywords": ["guard clause"],
                    "why_plausible": "plausible",
                    "why_incorrect": "incorrect",
                }
            ],
        },
    }
    (tasks / "owner__repo-1.json").write_text(json.dumps(task), encoding="utf-8")

    resolved = {
        "original": True,
        "correct": True,
        "wrong_location": False,
        "wrong_cause": True,
        "wrong_repair": False,
    }
    for condition, outcome in resolved.items():
        run_id = f"run-{condition}"
        directory = runs / run_id
        directory.mkdir(parents=True)
        run = {
            "run_id": run_id,
            "instance_id": "owner__repo-1",
            "agent_id": "agent",
            "model_id": "model",
            "repetition": 1,
            "condition": condition,
        }
        (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
        result = {
            "resolved": outcome,
            "runtime_seconds": 2,
            "tokens_total": 20,
            "tool_calls": 3,
            "steps": 3,
        }
        (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
        events = []
        if condition == "wrong_location":
            events.extend(
                [
                    {"step": 1, "event_type": "file_read", "files_accessed": ["src/wrong.py"]},
                    {"step": 2, "event_type": "patch", "files_modified": ["src/wrong.py"]},
                ]
            )
        elif condition == "wrong_cause":
            events.extend(
                [
                    {"step": 1, "event_type": "reasoning", "text": "inspect cache"},
                    {"step": 2, "event_type": "reasoning", "text": "cache may be stale"},
                ]
            )
        elif condition == "wrong_repair":
            events.extend(
                [
                    {"step": 1, "event_type": "reasoning", "text": "add a guard clause"},
                    {"step": 2, "event_type": "patch", "text": "implement guard clause"},
                ]
            )
        else:
            events.extend(
                [
                    {"step": 1, "event_type": "reasoning", "text": "inspect issue"},
                    {"step": 2, "event_type": "reasoning", "text": "find defect"},
                ]
            )
        events.append({"step": 3, "event_type": "file_read", "files_accessed": ["src/gold.py"]})
        (directory / "trajectory.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
    return tasks, runs


def test_analyzes_existing_results_with_proxies(tmp_path: Path) -> None:
    tasks, runs = _write_fixture(tmp_path)
    output = tmp_path / "analysis"
    report = analyze_results(tasks, runs, output, use_proxies=True, seed=7)
    assert report["run_count"] == 5
    assert report["rq1"]["resolve_rates"]["wrong_location"]["rate"] == 0.0
    assert report["rq2"]["anchoring_rate"]["total"] == 3
    assert report["rq2"]["by_condition"]["wrong_repair"]["rate"] == 1.0
    assert report["rq3"]["recovery_rate"]["successes"] == 3
    assert (output / "run-table.csv").exists()
    assert (output / "report.json").exists()
    assert (output / "report.md").exists()


def test_uses_human_annotations_for_confirmatory_report(tmp_path: Path) -> None:
    tasks, runs = _write_fixture(tmp_path)
    annotations = tmp_path / "annotations.csv"
    annotations.write_text(
        "run_id,anchored,contradiction_seen,recovered,persistent,contradiction_step,recovery_step\n"
        "run-wrong_location,yes,yes,no,yes,2,\n"
        "run-wrong_cause,yes,yes,yes,no,2,3\n"
        "run-wrong_repair,yes,yes,no,yes,2,\n",
        encoding="utf-8",
    )
    report = analyze_results(
        tasks,
        runs,
        tmp_path / "analysis",
        annotations_path=annotations,
    )
    assert report["behavior_labels"] == "human_adjudication"
    assert report["rq3"]["recovery_rate"]["rate"] == 1 / 3
    assert report["rq3"]["median_recovery_latency_steps"] == 1.0
