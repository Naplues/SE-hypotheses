import hashlib
import json
from pathlib import Path

from pytest import MonkeyPatch

from rfm import construction
from rfm.construction import construct_hypotheses, parse_patch


def _snapshot(root: Path, commit: str, instance_id: str = "owner__repo-1") -> Path:
    snapshot = root / instance_id
    (snapshot / "src").mkdir(parents=True)
    (snapshot / "src" / "gold.py").write_text("def gold():\n    return 1\n", encoding="utf-8")
    (snapshot / "src" / "wrong.py").write_text("def wrong():\n    return 0\n", encoding="utf-8")
    archive = root.parent / "archive.tar.gz"
    archive.write_bytes(b"test archive")
    metadata = root / ".metadata"
    metadata.mkdir(exist_ok=True)
    (metadata / f"{instance_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": instance_id,
                "repo": "owner/repo",
                "base_commit": commit,
                "archive_path": str(archive),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "snapshot_dir": str(snapshot),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot


def _fake_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

prompt = sys.stdin.read()
instance_id = re.search(r"<instance_id>(.*?)</instance_id>", prompt).group(1)
if "<developer_patch>" in prompt:
    assert sys.argv[sys.argv.index("--tools") + 1] == ""
    result = {
        "instance_id": instance_id,
        "status": "ok",
        "skip_reason": "N/A",
        "files": ["src/gold.py"],
        "symbols": ["gold"],
        "cause": "the operation is incorrect",
        "repair": "correct the operation",
        "evidence": [{"file": "src/gold.py", "symbol": "gold", "reason": "patched"}],
    }
else:
    assert sys.argv[sys.argv.index("--tools") + 1] == ""
    result = {
        "instance_id": instance_id,
        "status": "ok",
        "skip_reason": "",
        "wrong_location_file": "src/wrong.py",
        "wrong_location_symbol": "wrong",
        "wrong_location_why_plausible": "nearby logic",
        "wrong_location_why_incorrect": "the patch changes gold.py",
        "wrong_cause": "stale cache",
        "wrong_cause_keyword": "cache",
        "wrong_cause_why_plausible": "similar symptoms",
        "wrong_cause_why_incorrect": "no cache is involved",
        "wrong_repair": "special-case the failing input",
        "wrong_repair_keyword": "special-case",
        "wrong_repair_why_plausible": "it suppresses the reported symptom",
        "wrong_repair_why_incorrect": "it leaves the faulty operation unchanged",
    }
print(json.dumps({"structured_output": result, "session_id": "s1", "total_cost_usd": 0.01}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_skipping_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

result = {
    "instance_id": "owner__repo-1",
    "status": "skip",
    "skip_reason": "repository evidence is insufficient",
    "files": [],
    "symbols": [],
    "cause": "",
    "repair": "",
    "evidence": [],
}
print(json.dumps({"structured_output": result}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_hypothesis_skipping_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

prompt = sys.stdin.read()
if "<developer_patch>" in prompt:
    result = {
        "instance_id": "owner__repo-1",
        "status": "ok",
        "skip_reason": "",
        "files": ["src/gold.py"],
        "symbols": ["gold"],
        "cause": "incorrect operation",
        "repair": "correct the operation",
        "evidence": [{"file": "src/gold.py", "symbol": "gold", "reason": "patched"}],
    }
else:
    result = {
        "instance_id": "owner__repo-1",
        "status": "skip",
        "skip_reason": "no plausible wrong location exists",
        "wrong_location": [],
        "wrong_cause": [],
        "wrong_repair": [],
    }
print(json.dumps({"structured_output": result}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_max_turns_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

print(json.dumps({
    "type": "result",
    "subtype": "error_max_turns",
    "terminal_reason": "max_turns",
}), file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_hypothesis_failure_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

prompt = sys.stdin.read()
if "<developer_patch>" not in prompt:
    print("permanent hypothesis failure", file=sys.stderr)
    raise SystemExit(1)
result = {
    "instance_id": "owner__repo-1",
    "status": "ok",
    "skip_reason": "",
    "files": ["src/gold.py"],
    "symbols": ["gold"],
    "cause": "incorrect operation",
    "repair": "correct the operation",
    "evidence": [{"file": "src/gold.py", "symbol": "gold", "reason": "patched"}],
}
print(json.dumps({"structured_output": result}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_checkpoint_resume_claude(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)

prompt = sys.stdin.read()
if "<developer_patch>" in prompt:
    print("ground truth should have been loaded from checkpoint", file=sys.stderr)
    raise SystemExit(1)
result = {
    "instance_id": "owner__repo-1",
    "status": "ok",
    "skip_reason": "",
    "wrong_location": [{
        "id": "wl1", "files": ["src/wrong.py"], "symbols": ["wrong"],
        "why_plausible": "nearby logic", "why_incorrect": "gold.py is patched"
    }],
    "wrong_cause": [{
        "id": "wc1", "cause": "stale cache", "keywords": ["cache"],
        "why_plausible": "similar symptoms", "why_incorrect": "no cache is involved"
    }],
    "wrong_repair": [{
        "id": "wr1", "repair": "special-case the input", "keywords": ["special-case"],
        "why_plausible": "it suppresses the symptom", "why_incorrect": "mechanism remains"
    }],
}
print(json.dumps({"structured_output": result}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_two_prompt_construction(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, commit)
    source = tmp_path / "swebench.jsonl"
    record = {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": commit,
        "problem_statement": "The function returns the wrong value.",
        "patch": (
            "diff --git a/src/gold.py b/src/gold.py\n"
            "--- a/src/gold.py\n+++ b/src/gold.py\n"
            "@@ -1,2 +1,2 @@ def gold():\n"
        ),
        "test_patch": "diff --git a/tests/test_gold.py b/tests/test_gold.py\n",
        "FAIL_TO_PASS": json.dumps(["tests/test_gold.py::test_gold"]),
        "PASS_TO_PASS": json.dumps([]),
    }
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")
    fake = tmp_path / "fake-claude"
    _fake_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    summary = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )
    assert summary["completed"] == ["owner__repo-1"]
    assert summary["claude_timeout_seconds"] == 600
    assert summary["claude_max_turns"] == 4
    assert summary["claude_transient_retries"] == 1
    assert summary["timing"]["task_seconds"]["count"] == 1
    assert summary["timing"]["ground_truth_seconds"]["count"] == 1
    assert summary["timing"]["hypothesis_seconds"]["count"] == 1
    assert summary["timing"]["tasks"][0]["outcome"] == "completed"
    result = json.loads((tmp_path / "output" / "owner__repo-1.json").read_text(encoding="utf-8"))
    assert result["ground_truth"]["files"] == ["src/gold.py"]
    assert result["hypotheses"]["wrong_location"][0]["id"] == "wl1"
    assert result["hypotheses"]["wrong_repair"][0]["id"] == "wr1"
    assert result["schema_version"] == 3
    assert result["generated_by"] == {
        "model": "claude-test",
        "claude_code_version": "9.9.9 fake",
    }
    assert "evidence" not in result["ground_truth"]
    ground_prompt = (
        tmp_path / "workspace" / "prompts" / "owner__repo-1.ground-truth.txt"
    ).read_text(encoding="utf-8")
    assert '"src/gold.py"' in ground_prompt
    assert "tests/test_gold.py" in ground_prompt
    assert "<pass_to_pass>" not in ground_prompt
    assert "Repository tools are unavailable" in ground_prompt
    assert "<base_commit_source_context>" in ground_prompt
    assert "return 1" in ground_prompt
    hypothesis_prompt = (
        tmp_path / "workspace" / "prompts" / "owner__repo-1.hypotheses.txt"
    ).read_text(encoding="utf-8")
    assert "<public_task_context>" in hypothesis_prompt
    assert "<private_ground_truth>" in hypothesis_prompt
    assert "Use the private ground truth only to" in hypothesis_prompt
    assert "alternative valid repair" in hypothesis_prompt
    assert '"evidence"' not in hypothesis_prompt
    assert "<wrong_location_candidates>" in hypothesis_prompt
    assert "src/wrong.py" in hypothesis_prompt
    assert record["patch"] not in hypothesis_prompt
    assert set(result) == {
        "schema_version",
        "instance_id",
        "ground_truth",
        "hypotheses",
        "generated_by",
    }


def test_patch_parser_extracts_hunk_context() -> None:
    parsed = parse_patch(
        "diff --git a/src/collect_repos_info.py b/src/collect_repos_info.py\n"
        "@@ -1 +1 @@ def repaired():\n"
    )
    assert parsed["touched_files"] == ["src/collect_repos_info.py"]
    assert parsed["hunk_headers"]["src/collect_repos_info.py"] == ["def repaired():"]


def test_unextractable_task_is_skipped(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, commit)
    source = tmp_path / "swebench.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": commit,
                "problem_statement": "Ambiguous failure.",
                "patch": "diff --git a/src/gold.py b/src/gold.py\n",
                "test_patch": "",
                "FAIL_TO_PASS": "[]",
                "PASS_TO_PASS": "[]",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake = tmp_path / "fake-claude"
    _fake_skipping_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    summary = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )

    assert summary["completed"] == []
    assert summary["failures"] == []
    assert summary["skipped"] == [
        {
            "instance_id": "owner__repo-1",
            "reason": "ground_truth: repository evidence is insufficient",
        }
    ]
    assert summary["timing"]["tasks"][0]["outcome"] == "skipped"
    assert summary["timing"]["ground_truth_seconds"]["count"] == 1
    assert summary["timing"]["hypothesis_seconds"]["count"] == 0
    assert not (tmp_path / "output" / "owner__repo-1.json").exists()


def test_task_without_valid_hypotheses_is_skipped(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, commit)
    source = tmp_path / "swebench.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": commit,
                "problem_statement": "The function returns the wrong value.",
                "patch": "diff --git a/src/gold.py b/src/gold.py\n",
                "test_patch": "",
                "FAIL_TO_PASS": "[]",
                "PASS_TO_PASS": "[]",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake = tmp_path / "fake-claude"
    _fake_hypothesis_skipping_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    summary = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )

    assert summary["failures"] == []
    assert summary["skipped"][0]["reason"] == ("hypotheses: no plausible wrong location exists")
    assert summary["timing"]["tasks"][0]["outcome"] == "skipped"
    assert summary["timing"]["hypothesis_seconds"]["count"] == 1


def test_max_turns_is_skipped_without_retry(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, commit)
    source = tmp_path / "swebench.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": commit,
                "problem_statement": "The function returns the wrong value.",
                "patch": "diff --git a/src/gold.py b/src/gold.py\n",
                "test_patch": "",
                "FAIL_TO_PASS": "[]",
                "PASS_TO_PASS": "[]",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake = tmp_path / "fake-claude"
    _fake_max_turns_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    summary = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )

    assert summary["failures"] == []
    assert summary["skipped"] == [
        {"instance_id": "owner__repo-1", "reason": "ground_truth: max_turns"}
    ]
    assert summary["timing"]["tasks"][0]["outcome"] == "skipped"
    state = tmp_path / "output" / ".construction-state" / "owner__repo-1.json"
    assert state.exists()

    _fake_claude(fake)
    repeated = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )
    assert repeated["completed"] == []
    assert repeated["skipped"] == [
        {
            "instance_id": "owner__repo-1",
            "reason": "previous_skipped: ground_truth: max_turns",
        }
    ]
    assert repeated["timing"]["task_seconds"]["count"] == 0

    retried = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
        force=True,
    )
    assert retried["completed"] == ["owner__repo-1"]
    assert not state.exists()

    (tmp_path / "output" / "owner__repo-1.json").unlink()
    state.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "outcome": "failed",
                "reason": "hypotheses: timed out",
            }
        ),
        encoding="utf-8",
    )
    failed_only = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
        retry_failed=True,
    )
    assert failed_only["completed"] == ["owner__repo-1"]
    assert failed_only["retry_failed"] is True
    assert not state.exists()

    # `not_failed` is only a --retry-failed selection result. It must not
    # become a persistent skip that blocks a later normal run.
    (tmp_path / "output" / "owner__repo-1.json").unlink()
    (tmp_path / "output" / "construction-summary.json").write_text(
        json.dumps(
            {
                "skipped": [
                    {
                        "instance_id": "owner__repo-1",
                        "reason": "previous_skipped: not_failed",
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    after_filtered_run = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )
    assert after_filtered_run["completed"] == ["owner__repo-1"]
    assert not state.exists()

    (tmp_path / "output" / "owner__repo-1.json").unlink()
    state.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "outcome": "skipped",
                "reason": "previous_skipped: not_failed",
            }
        ),
        encoding="utf-8",
    )
    after_legacy_state = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )
    assert after_legacy_state["completed"] == ["owner__repo-1"]
    assert not state.exists()


def test_constructs_tasks_with_parallel_workers(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    instance_ids = ["owner__repo-1", "owner__repo-2"]
    for instance_id in instance_ids:
        _snapshot(snapshots, commit, instance_id)
    source = tmp_path / "swebench.jsonl"
    records = [
        {
            "instance_id": instance_id,
            "repo": "owner/repo",
            "base_commit": commit,
            "problem_statement": "The function returns the wrong value.",
            "patch": "diff --git a/src/gold.py b/src/gold.py\n",
            "test_patch": "",
            "FAIL_TO_PASS": "[]",
            "PASS_TO_PASS": "[]",
        }
        for instance_id in instance_ids
    ]
    source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    fake = tmp_path / "fake-claude"
    _fake_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    summary = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
        workers=2,
    )

    assert set(summary["completed"]) == set(instance_ids)
    assert summary["workers"] == 2
    assert summary["timing"]["task_seconds"]["count"] == 2
    assert all(
        (tmp_path / "output" / f"{instance_id}.json").exists() for instance_id in instance_ids
    )


def test_failed_hypothesis_stage_resumes_from_ground_checkpoint(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    commit = "a" * 40
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, commit)
    source = tmp_path / "swebench.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": commit,
                "problem_statement": "The function returns the wrong value.",
                "patch": (
                    "diff --git a/src/gold.py b/src/gold.py\n"
                    "--- a/src/gold.py\n+++ b/src/gold.py\n"
                    "@@ -1,2 +1,2 @@ def gold():\n"
                ),
                "test_patch": "",
                "FAIL_TO_PASS": "[]",
                "PASS_TO_PASS": "[]",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake = tmp_path / "fake-claude"
    _fake_hypothesis_failure_claude(fake)
    monkeypatch.setattr(construction, "CLAUDE_COMMAND", str(fake))

    failed = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
    )
    assert failed["failures"][0]["stage"] == "hypotheses"
    checkpoint = tmp_path / "workspace" / "checkpoints" / "owner__repo-1.ground-truth.json"
    assert checkpoint.exists()

    _fake_checkpoint_resume_claude(fake)
    resumed = construct_hypotheses(
        source,
        tmp_path / "workspace",
        tmp_path / "output",
        model="claude-test",
        snapshots_dir=snapshots,
        retry_failed=True,
    )
    assert resumed["completed"] == ["owner__repo-1"]
    assert resumed["timing"]["tasks"][0]["ground_truth_cached"] is True
    assert resumed["timing"]["tasks"][0]["ground_truth_seconds"] is not None


def test_claude_code_retries_transient_connection_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    fake = tmp_path / "fake-claude"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

if "--version" in sys.argv:
    print("9.9.9 fake")
    raise SystemExit(0)
marker = pathlib.Path(__file__).with_suffix(".attempted")
if not marker.exists():
    marker.write_text("1")
    print("API Error: ENOTFOUND", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({"structured_output": {"value": "ok"}}))
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr(construction, "sleep", lambda _: None)
    client = construction.ClaudeCode(
        command=str(fake),
        model="claude-test",
        max_turns=4,
        max_budget_usd=None,
        timeout_seconds=10,
        transient_retries=1,
    )

    result = client.generate("prompt", {"type": "object"}, tmp_path, tools="")

    assert result == {"value": "ok"}
    assert fake.with_suffix(".attempted").exists()
