from __future__ import annotations

import json
from pathlib import Path

import pytest

from rfm.datasets import build_hypothesis_datasets
from rfm.io import read_jsonl
from rfm.prompts import CONDITIONS, INTRODUCTION


def _prompt(condition: str, instance_id: str) -> str:
    return (
        f"{INTRODUCTION}\n\n"
        "<developer_hypothesis>\n"
        f"{condition} hypothesis for {instance_id}.\n"
        "</developer_hypothesis>\n"
    )


def _write_source(path: Path) -> list[dict[str, object]]:
    rows = [
        {
            "instance_id": f"owner__repo-{index}",
            "repo": "owner/repo",
            "base_commit": str(index) * 40,
            "problem_statement": f"Original issue {index}.",
            "patch": f"patch-{index}",
            "test_patch": f"test-patch-{index}",
            "FAIL_TO_PASS": [f"test_{index}"],
            "PASS_TO_PASS": [],
        }
        for index in (1, 2, 3)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return rows


def test_builds_four_filtered_datasets_and_only_changes_problem_statement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    original_rows = _write_source(source)
    original_bytes = source.read_bytes()
    prompt_root = tmp_path / "prompts"
    selected = {
        "CH": ["owner__repo-1", "owner__repo-3"],
        "WLH": ["owner__repo-2"],
        "WCH": ["owner__repo-3", "owner__repo-1"],
        "WRH": ["owner__repo-2", "owner__repo-3"],
    }
    for condition, instance_ids in selected.items():
        directory = prompt_root / condition
        directory.mkdir(parents=True)
        for instance_id in instance_ids:
            (directory / f"{instance_id}.txt").write_text(
                _prompt(condition, instance_id), encoding="utf-8"
            )

    output = tmp_path / "output"
    summary = build_hypothesis_datasets(source, prompt_root, output)

    assert source.read_bytes() == original_bytes
    original_by_id = {row["instance_id"]: row for row in original_rows}
    for condition in CONDITIONS:
        rows = list(read_jsonl(output / f"swebench_verified_test_{condition}.jsonl"))
        expected_ids = [
            row["instance_id"] for row in original_rows if row["instance_id"] in selected[condition]
        ]
        assert [row["instance_id"] for row in rows] == expected_ids
        assert summary["datasets"][condition]["tasks"] == len(expected_ids)
        for row in rows:
            original = original_by_id[row["instance_id"]]
            assert row["problem_statement"] == (
                f"{original['problem_statement']}\n\n"
                f"{_prompt(condition, str(row['instance_id'])).strip()}"
            )
            assert {key: value for key, value in row.items() if key != "problem_statement"} == {
                key: value for key, value in original.items() if key != "problem_statement"
            }


def test_rejects_prompt_for_unknown_instance(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source)
    prompt_root = tmp_path / "prompts"
    for condition in CONDITIONS:
        directory = prompt_root / condition
        directory.mkdir(parents=True)
        instance_id = "unknown" if condition == "WRH" else "owner__repo-1"
        (directory / f"{instance_id}.txt").write_text(
            _prompt(condition, instance_id), encoding="utf-8"
        )

    with pytest.raises(ValueError, match="Unknown WRH prompt instance_id: unknown"):
        build_hypothesis_datasets(source, prompt_root, tmp_path / "output")
    assert not (tmp_path / "output").exists()
