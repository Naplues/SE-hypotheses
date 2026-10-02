"""SWE-bench task loading and patch-guided repository helpers."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rfm.io import read_jsonl

SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
}


@dataclass(frozen=True)
class SWEBenchTask:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str
    test_patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]


def load_swebench(path: str | Path) -> list[SWEBenchTask]:
    """Load and validate construction fields from a SWE-bench JSONL file."""

    required = {
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
        "patch",
        "test_patch",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
    }
    tasks: list[SWEBenchTask] = []
    seen: set[str] = set()
    for line, raw in enumerate(read_jsonl(path), start=1):
        missing = sorted(required - set(raw))
        if missing:
            raise ValueError(f"SWE-bench line {line} is missing fields: {missing}")
        instance_id = _required_text(raw["instance_id"], f"line {line}.instance_id")
        if instance_id in seen:
            raise ValueError(f"Duplicate SWE-bench instance_id: {instance_id}")
        seen.add(instance_id)
        base_commit = _required_text(raw["base_commit"], f"{instance_id}.base_commit")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", base_commit):
            raise ValueError(f"Invalid base_commit for {instance_id}")
        tasks.append(
            SWEBenchTask(
                instance_id=instance_id,
                repo=_required_text(raw["repo"], f"{instance_id}.repo"),
                base_commit=base_commit,
                problem_statement=_required_text(
                    raw["problem_statement"], f"{instance_id}.problem_statement"
                ),
                patch=str(raw["patch"]),
                test_patch=str(raw["test_patch"]),
                fail_to_pass=_test_list(raw["FAIL_TO_PASS"], instance_id),
                pass_to_pass=_test_list(raw["PASS_TO_PASS"], instance_id),
            )
        )
    return tasks


def parse_patch(patch: str) -> dict[str, Any]:
    """Extract changed files and hunk symbols from a Git patch."""

    files: dict[str, list[str]] = {}
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = shlex.split(line[len("diff --git ") :])
            if len(parts) != 2:
                raise ValueError(f"Invalid Git diff header: {line!r}")
            current = _strip_diff_prefix(parts[1])
            files.setdefault(current, [])
        elif line.startswith("rename from ") and current is not None:
            previous = line[len("rename from ") :].strip()
            headers = files.pop(current)
            current = previous
            files.setdefault(current, []).extend(headers)
        elif line.startswith("@@") and current is not None:
            match = re.match(r"^@@+ .*? @@+\s*(.*)$", line)
            header = match.group(1).strip() if match else ""
            if header and header not in files[current]:
                files[current].append(header)
    if not files:
        raise ValueError("Developer patch contains no parseable changed files")
    return {"touched_files": list(files), "hunk_headers": files}


def safe_slug(value: str) -> str:
    """Convert an identifier to a safe local filename component."""

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not slug:
        raise ValueError(f"Cannot create a filename from {value!r}")
    return slug


def _test_list(raw: Any, instance_id: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid test list for {instance_id}: {exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Test list for {instance_id} must be an array of strings")
    return tuple(value)


def _required_text(raw: Any, location: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{location} cannot be empty")
    return value


def _strip_diff_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path
