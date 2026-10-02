from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rfm.prompts import generate_hypothesis_prompts, render_task_prompts


def _task() -> dict[str, object]:
    return {
        "instance_id": "owner__repo-1",
        "ground_truth": {
            "files": ["src/gold.py"],
            "symbols": ["gold"],
            "cause_type": "state",
            "repair": "Use the correct value.",
        },
        "hypotheses": {
            "wrong_location": [
                {
                    "id": "wl1",
                    "files": ["src/wrong.py"],
                    "symbols": ["wrong"],
                    "why_plausible": "Nearby related code.",
                    "why_incorrect": "The patch changes another symbol.",
                }
            ],
            "wrong_cause": [
                {
                    "id": "wc1",
                    "cause": "The cache is stale.",
                    "keywords": ["cache"],
                    "why_plausible": "The symptom resembles stale data.",
                    "why_incorrect": "The patch changes state propagation.",
                }
            ],
            "wrong_repair": [
                {
                    "id": "wr1",
                    "repair": "Clear the cache.",
                    "keywords": ["clear"],
                    "why_plausible": "It follows from the cache hypothesis.",
                    "why_incorrect": "It does not implement the developer repair.",
                }
            ],
        },
        "generated_by": {"model": "test"},
    }


def test_render_task_prompts_exposes_only_selected_hypothesis_fields() -> None:
    prompts = render_task_prompts(_task())

    assert set(prompts) == {"CH", "WLH", "WCH", "WRH"}
    assert all(
        prompt.startswith(
            "The following issue analysis was provided by a developer familiar with the codebase."
        )
        for prompt in prompts.values()
    )
    assert all("<developer_hypothesis>" in prompt for prompt in prompts.values())
    assert "src/gold.py" in prompts["CH"]
    assert "state" in prompts["CH"]
    assert "The defect is likely located in wrong in src/wrong.py." in prompts["WLH"]
    assert "The cache is stale." in prompts["WCH"]
    assert "Clear the cache." in prompts["WRH"]
    combined = "\n".join(prompts.values())
    assert "why_plausible" not in combined
    assert "why_incorrect" not in combined
    assert "wl1" not in combined
    assert "wrong_location" not in combined


def test_generate_hypothesis_prompts_groups_outputs_and_skips_ambiguous_tasks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tasks"
    source.mkdir()
    (source / "valid.json").write_text(json.dumps(_task()), encoding="utf-8")
    ambiguous = _task()
    ambiguous["instance_id"] = "owner__repo-2"
    ambiguous["hypotheses"]["wrong_cause"].append(  # type: ignore[index]
        {"cause": "A second cause."}
    )
    (source / "ambiguous.json").write_text(json.dumps(ambiguous), encoding="utf-8")

    output = tmp_path / "prompts"
    summary = generate_hypothesis_prompts(source, output)

    assert summary["selected"] == 2
    assert summary["completed"] == ["owner__repo-1"]
    assert summary["skipped"][0]["instance_id"] == "owner__repo-2"
    for condition in ("CH", "WLH", "WCH", "WRH"):
        assert (output / condition / "owner__repo-1.txt").is_file()
        assert not (output / condition / "owner__repo-2.txt").exists()


def test_generate_cli_also_builds_four_datasets(tmp_path: Path) -> None:
    constructed = tmp_path / "constructed"
    constructed.mkdir()
    (constructed / "owner__repo-1.json").write_text(json.dumps(_task()), encoding="utf-8")
    source = tmp_path / "swebench.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "problem_statement": "Original issue.",
                "repo": "owner/repo",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    datasets = tmp_path / "datasets"
    project = Path(__file__).resolve().parents[1]

    process = subprocess.run(
        [
            sys.executable,
            str(project / "scripts" / "generate_hypothesis_prompts.py"),
            "--input",
            str(constructed),
            "--output",
            str(prompts),
            "--source",
            str(source),
            "--datasets-output",
            str(datasets),
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = json.loads(process.stdout)

    assert summary["prompts"]["completed"] == ["owner__repo-1"]
    for condition in ("CH", "WLH", "WCH", "WRH"):
        assert (prompts / condition / "owner__repo-1.txt").is_file()
        target = datasets / f"swebench_verified_test_{condition}.jsonl"
        assert target.is_file()
        assert summary["datasets"][condition]["tasks"] == 1
        row = json.loads(target.read_text(encoding="utf-8"))
        assert row["problem_statement"].startswith("Original issue.\n\n")
