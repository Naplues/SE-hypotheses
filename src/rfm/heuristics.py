"""Minimal deterministic construction of patch-guided hypotheses."""

from __future__ import annotations

import ast
import json
import keyword
import re
import shlex
import sys
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from rfm.io import dump_json
from rfm.models import normalize_path
from rfm.swebench import SOURCE_SUFFIXES, SWEBenchTask, load_swebench, parse_patch, safe_slug

HEURISTIC_VERSION = "5"

CAUSE_TYPES = (
    "condition",
    "state",
    "type",
    "validation",
    "exception",
    "cache",
    "lifecycle",
    "computation",
)

CAUSE_LABELS = {
    "condition": "an incorrect condition or boundary decision",
    "state": "incorrect state or data flow",
    "type": "incorrect type conversion or normalization",
    "validation": "missing or incorrect input validation",
    "exception": "incorrect exception handling",
    "cache": "stale or incorrectly reused cached data",
    "lifecycle": "an incorrect initialization or execution order",
    "computation": "an incorrect computation or transformation",
}

GROUND_REPAIRS = {
    "condition": "correct the condition or boundary decision",
    "state": "correct the affected state or data flow",
    "type": "correct the type conversion or normalization",
    "validation": "add or correct the required input validation",
    "exception": "correct how the exception is raised, caught, or propagated",
    "cache": "correct how cached data is invalidated or reused",
    "lifecycle": "correct the initialization or execution order",
    "computation": "correct the affected computation or transformation",
}

WRONG_REPAIRS = {
    "condition": "Add a boundary check before the operation.",
    "state": "Reset or update the relevant state before the operation.",
    "type": "Convert the affected value to the expected type before it is used.",
    "validation": "Add input validation before the operation.",
    "exception": "Catch and handle the exception during the operation.",
    "cache": "Reset or disable the relevant cache before the operation.",
    "lifecycle": "Change the initialization or execution order.",
    "computation": "Adjust the computation used to produce the result.",
}

REPAIR_KEYWORDS = {
    "condition": "boundary check",
    "state": "reset state",
    "type": "type conversion",
    "validation": "input validation",
    "exception": "handle exception",
    "cache": "reset cache",
    "lifecycle": "initialization order",
    "computation": "adjust computation",
}

# Ordered from specific symptoms to the general wrong-result case. The first
# matching row is the only row used, which keeps selection deterministic.
SYMPTOM_RULES = (
    (r"\b(typeerror|incompatible\s+(?:type|input)|wrong\s+type)\b", ("type", "validation")),
    (r"\b(stale|cached|cache|repeated|previous\s+(?:value|result))\b", ("cache", "state")),
    (
        r"\b(none|null|empty|boundary|out[- ]of[- ]range|zero[- ]length)\b",
        ("validation", "condition"),
    ),
    (
        r"\b(__init__|initialize|initialization|startup|start[- ]up|shutdown|load(?:ing)?)\b",
        ("lifecycle", "state"),
    ),
    (
        r"\b(exception|crash(?:es|ed)?|traceback|raises?|uncaught|\w+error)\b",
        ("validation", "exception", "type"),
    ),
    (
        r"\b(wrong|incorrect|unexpected|invalid)\b.{0,30}\b(result|value|output|return)|"
        r"\b(result|value|output|return)\b.{0,30}\b(wrong|incorrect|unexpected|invalid)\b",
        ("state", "computation", "cache"),
    ),
)

STOPWORDS = {
    "about",
    "after",
    "against",
    "all",
    "also",
    "and",
    "any",
    "are",
    "before",
    "being",
    "because",
    "but",
    "can",
    "class",
    "code",
    "current",
    "data",
    "description",
    "does",
    "empty",
    "error",
    "failure",
    "file",
    "from",
    "function",
    "have",
    "incorrect",
    "input",
    "inputs",
    "into",
    "invalid",
    "issue",
    "last",
    "line",
    "list",
    "many",
    "may",
    "method",
    "missing",
    "none",
    "object",
    "objects",
    "only",
    "other",
    "output",
    "result",
    "return",
    "self",
    "should",
    "that",
    "the",
    "their",
    "there",
    "this",
    "unexpected",
    "value",
    "when",
    "which",
    "with",
    "would",
    "wrong",
}

# These tokens can occur in both an issue and almost any nearby implementation,
# but do not establish a meaningful location relation by themselves.
WEAK_LOCATION_IDENTIFIERS = {
    "another",
    "attributeerror",
    "condition",
    "default",
    "exception",
    "failed",
    "functions",
    "information",
    "instance",
    "isinstance",
    "keyerror",
    "models",
    "parameters",
    "python",
    "returns",
    "typeerror",
    "valueerror",
}


class HeuristicSkip(Exception):
    """Expected omission when the four-rule construction is not supported."""


@dataclass(frozen=True)
class Definition:
    name: str
    line: int
    identifiers: frozenset[str]
    members: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LocationChoice:
    file: str
    symbol: str
    priority: str
    shared_identifier: str


def construct_heuristic_hypotheses(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    snapshots_dir: str | Path = "data/repository-snapshots",
    instance_ids: list[str] | None = None,
    instance_ids_file: str | Path | None = None,
    limit: int | None = None,
    workers: int = 1,
    force: bool = False,
    fail_fast: bool = False,
) -> dict[str, Any]:
    """Construct CH, WLH, WCH, and WRH without invoking a language model."""

    if workers < 1:
        raise ValueError("workers must be positive")
    if workers > 1 and fail_fast:
        raise ValueError("fail_fast requires workers=1")
    tasks = _selected_tasks(input_path, instance_ids, instance_ids_file, limit)
    output_root = Path(output_dir).resolve()
    snapshot_root = Path(snapshots_dir).resolve()
    summary_path = output_root / "construction-summary.json"
    completed: list[str] = []
    skipped: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    audits: list[dict[str, Any]] = []
    started = perf_counter()

    pending: list[SWEBenchTask] = []
    for task in tasks:
        target = output_root / f"{safe_slug(task.instance_id)}.json"
        if target.exists():
            if not force and _is_current_output(target):
                skipped.append({"instance_id": task.instance_id, "reason": "output_exists"})
                continue
            target.unlink()
        pending.append(task)

    def current_summary() -> dict[str, Any]:
        durations = [float(item["seconds"]) for item in audits]
        return {
            "method": "patch-guided-heuristic",
            "heuristic_version": HEURISTIC_VERSION,
            "selected": len(tasks),
            "completed": completed,
            "skipped": skipped,
            "failures": failures,
            "output_dir": str(output_root),
            "snapshots_dir": str(snapshot_root),
            "workers": workers,
            "rules": {
                "ground_cause_types": dict(
                    sorted(Counter(item["ground_cause_type"] for item in audits).items())
                ),
                "wrong_cause_types": dict(
                    sorted(Counter(item["wrong_cause_type"] for item in audits).items())
                ),
                "wrong_location_priorities": dict(
                    sorted(Counter(item["location_priority"] for item in audits).items())
                ),
                "filters": ["existence", "incorrectness", "plausibility", "isolation"],
            },
            "timing": {
                "wall_seconds": round(perf_counter() - started, 3),
                "task_seconds": _stats(durations),
            },
        }

    def record(result: dict[str, Any]) -> None:
        instance_id = result["instance_id"]
        outcome = result["outcome"]
        if outcome == "completed":
            completed.append(instance_id)
            audits.append(result["audit"])
        elif outcome == "skipped":
            skipped.append({"instance_id": instance_id, "reason": result["reason"]})
        else:
            failures.append({"instance_id": instance_id, "error": result["error"]})
        finished = len(completed) + len(skipped) + len(failures)
        print(
            f"[{finished}/{len(tasks)}] {instance_id}: {outcome}; {result['seconds']:.3f}s",
            file=sys.stderr,
            flush=True,
        )
        dump_json(summary_path, current_summary())
        if fail_fast and outcome == "failed":
            raise ValueError(result["error"])

    if workers == 1:
        for result in (_construct_one(task, snapshot_root, output_root) for task in pending):
            record(result)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(
                lambda task: _construct_one(task, snapshot_root, output_root), pending
            ):
                record(result)

    summary = current_summary()
    dump_json(summary_path, summary)
    return summary


def construct_task(task: SWEBenchTask, repository: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply Ground Truth -> WLH -> WCH/WRH -> Filter to one task."""

    patch_evidence = parse_patch(task.patch)
    touched_files = list(patch_evidence["touched_files"])
    ground_files = [path for path in touched_files if _is_source(path) and not _is_test_path(path)]
    if not ground_files:
        raise HeuristicSkip("ground truth: developer patch has no non-test source file")

    symbols_by_file = _ground_symbols_by_file(repository, ground_files, task.patch)
    ground_symbols = list(
        dict.fromkeys(symbol for file_name in ground_files for symbol in symbols_by_file[file_name])
    )

    cause_type = _classify_patch(task.patch, task.problem_statement)
    if cause_type is None:
        raise HeuristicSkip("ground truth: patch repair mechanism is not reliable")
    primary_file = next(
        (file_name for file_name in ground_files if symbols_by_file[file_name]), ground_files[0]
    )
    primary_symbols = symbols_by_file[primary_file]
    if primary_symbols:
        ground_location = f"{primary_symbols[0]} in {primary_file}"
    else:
        ground_location = primary_file
    repair = f"Update {ground_location} to {GROUND_REPAIRS[cause_type]}."

    issue_identifiers = _identifiers(task.problem_statement)
    if not issue_identifiers:
        raise HeuristicSkip("plausibility: issue contains no usable repository identifier")
    wrong_location = _select_wrong_location(
        repository,
        ground_files,
        symbols_by_file,
        touched_files,
        issue_identifiers,
    )
    compatible_causes = _symptom_causes(task.problem_statement)
    if not compatible_causes:
        raise HeuristicSkip("plausibility: issue symptom has no supported alternative mechanism")
    wrong_cause_type = next(
        (candidate for candidate in compatible_causes if candidate != cause_type), None
    )
    if wrong_cause_type is None:
        raise HeuristicSkip(
            "incorrectness: no symptom-compatible mechanism differs from ground truth"
        )

    wrong_cause = (
        f"The failure is likely caused by {CAUSE_LABELS[wrong_cause_type]} "
        f"involving {wrong_location.shared_identifier}."
    )
    wrong_repair = WRONG_REPAIRS[wrong_cause_type]
    payload = {
        "schema_version": 4,
        "instance_id": task.instance_id,
        "ground_truth": {
            "files": ground_files,
            "symbols": ground_symbols,
            "cause_type": cause_type,
            "repair": repair,
        },
        "hypotheses": {
            "wrong_location": [
                {
                    "id": "wl1",
                    "files": [wrong_location.file],
                    "symbols": [wrong_location.symbol],
                    "why_plausible": (
                        f"{wrong_location.symbol} in {wrong_location.file} shares the issue "
                        f"identifier {wrong_location.shared_identifier} and is related by "
                        f"{wrong_location.priority}."
                    ),
                    "why_incorrect": (f"The developer patch instead changes {ground_location}."),
                }
            ],
            "wrong_cause": [
                {
                    "id": "wc1",
                    "cause_type": wrong_cause_type,
                    "cause": wrong_cause,
                    "keywords": [wrong_cause_type, wrong_location.shared_identifier],
                    "why_plausible": (
                        f"The reported symptom is compatible with {CAUSE_LABELS[wrong_cause_type]}."
                    ),
                    "why_incorrect": (
                        f"The developer patch indicates {cause_type}, not {wrong_cause_type}."
                    ),
                }
            ],
            "wrong_repair": [
                {
                    "id": "wr1",
                    "repair": wrong_repair,
                    "keywords": [REPAIR_KEYWORDS[wrong_cause_type]],
                    "why_plausible": (
                        f"This repair follows from the alternative {wrong_cause_type} mechanism."
                    ),
                    "why_incorrect": (
                        f"It does not implement the developer patch's {cause_type} repair."
                    ),
                }
            ],
        },
        "generated_by": {
            "method": "patch-guided-heuristic",
            "version": HEURISTIC_VERSION,
        },
    }
    _apply_four_filters(
        repository=repository,
        payload=payload,
        symbols_by_file=symbols_by_file,
        issue_identifiers=issue_identifiers,
        compatible_causes=compatible_causes,
        shared_identifier=wrong_location.shared_identifier,
    )
    return payload, {
        "ground_cause_type": cause_type,
        "wrong_cause_type": wrong_cause_type,
        "location_priority": wrong_location.priority,
    }


def _construct_one(task: SWEBenchTask, snapshot_root: Path, output_root: Path) -> dict[str, Any]:
    started = perf_counter()
    try:
        repository = _snapshot_path(task, snapshot_root)
        payload, audit = construct_task(task, repository)
        dump_json(output_root / f"{safe_slug(task.instance_id)}.json", payload)
        seconds = perf_counter() - started
        return {
            "instance_id": task.instance_id,
            "outcome": "completed",
            "seconds": seconds,
            "audit": {**audit, "seconds": round(seconds, 3)},
        }
    except HeuristicSkip as exc:
        return {
            "instance_id": task.instance_id,
            "outcome": "skipped",
            "reason": str(exc),
            "seconds": perf_counter() - started,
        }
    except (OSError, ValueError, SyntaxError) as exc:
        return {
            "instance_id": task.instance_id,
            "outcome": "failed",
            "error": str(exc),
            "seconds": perf_counter() - started,
        }


def _selected_tasks(
    input_path: str | Path,
    instance_ids: list[str] | None,
    instance_ids_file: str | Path | None,
    limit: int | None,
) -> list[SWEBenchTask]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    selected = list(instance_ids or [])
    if instance_ids_file:
        selected.extend(
            line.strip()
            for line in Path(instance_ids_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if len(selected) != len(set(selected)):
        raise ValueError("Selected instance ids contain duplicates")
    tasks = load_swebench(input_path)
    if selected:
        by_id = {task.instance_id: task for task in tasks}
        missing = sorted(set(selected) - set(by_id))
        if missing:
            raise ValueError(f"Unknown instance ids: {missing}")
        tasks = [by_id[instance_id] for instance_id in selected]
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks:
        raise ValueError("No SWE-bench tasks selected")
    return tasks


def _snapshot_path(task: SWEBenchTask, root: Path) -> Path:
    slug = safe_slug(task.instance_id)
    repository = root / slug
    manifest_path = root / ".metadata" / f"{slug}.json"
    if not repository.is_dir():
        raise ValueError(f"Snapshot is missing for {task.instance_id}: {repository}")
    if not manifest_path.is_file():
        raise ValueError(f"Snapshot metadata is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "instance_id": task.instance_id,
        "repo": task.repo,
        "base_commit": task.base_commit,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Snapshot metadata mismatch for {key}: expected {value!r}, "
                f"found {manifest.get(key)!r}"
            )
    return repository


def _is_current_output(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(raw, dict):
        return False
    generated = raw.get("generated_by", {})
    return bool(
        raw.get("schema_version") == 4
        and isinstance(generated, dict)
        and generated.get("method") == "patch-guided-heuristic"
        and generated.get("version") == HEURISTIC_VERSION
    )


def _classify_patch(patch: str, issue: str) -> str | None:
    """Classify a developer patch using eight ordered, inspectable rules."""

    added, removed = _patch_lines(patch)
    changed = "\n".join([*added, *removed]).casefold()
    issue_lower = issue.casefold()
    if not changed:
        return None
    if re.search(r"\b(cache|cached|cache_clear|invalidate)\b", changed):
        return "cache"
    if re.search(
        r"\b(__init__|initialize|initialise|startup|shutdown|setup|teardown|before|after)\b",
        changed,
    ) and re.search(r"\b(init|start|load|order|setup|shutdown|lifecycle)\b", issue_lower):
        return "lifecycle"
    if re.search(r"\b(try|except|raise|exception)\b|\b\w+error\b", changed):
        return "exception"
    if re.search(
        r"\b(isinstance|issubclass|cast|convert|str|int|float|bytes|list|tuple|set|dict)\s*\(",
        changed,
    ):
        return "type"
    added_guards = sum(bool(re.match(r"(?:el)?if\b|assert\b", line)) for line in added)
    removed_guards = sum(bool(re.match(r"(?:el)?if\b|assert\b", line)) for line in removed)
    boundary_issue = re.search(
        r"\b(none|null|empty|missing|invalid|boundary|input|out[- ]of[- ]range)\b",
        issue_lower,
    )
    if boundary_issue and added_guards > removed_guards:
        return "validation"
    if re.search(r"^(?:el)?if\b|\b(?:==|!=|<=|>=|\bis\b|\bin\b)", changed, re.MULTILINE):
        return "condition"
    if any(
        re.search(r"(?<![=!<>])=(?!=)|\.(?:append|extend|pop|remove|update|add)\s*\(", line)
        for line in added
        if not line.startswith(("def ", "class "))
    ):
        return "state"
    if any(
        line.startswith("return ") or re.search(r"\s(?:\+|-|\*|/|%|//|\*\*)\s", line)
        for line in [*added, *removed]
    ):
        return "computation"
    return None


def _symptom_causes(issue: str) -> tuple[str, ...]:
    lower = issue.casefold()
    for pattern, causes in SYMPTOM_RULES:
        if re.search(pattern, lower):
            return causes
    return ()


def _select_wrong_location(
    repository: Path,
    ground_files: list[str],
    symbols_by_file: dict[str, list[str]],
    touched_files: list[str],
    issue_identifiers: set[str],
) -> LocationChoice:
    """Choose the first valid location using the three stated priorities."""

    # 1. Another related function or class in the same file.
    for file_name in ground_files:
        excluded_symbols = set(symbols_by_file[file_name])
        excluded_terms = {symbol.casefold() for symbol in excluded_symbols}
        for definition in _definitions(repository / file_name):
            if definition.name.startswith("__") and definition.name.endswith("__"):
                continue
            shared = _best_shared_identifier(definition.identifiers, issue_identifiers)
            contains_ground = bool(excluded_terms & definition.members)
            if definition.name not in excluded_symbols and not contains_ground and shared:
                return LocationChoice(file_name, definition.name, "same_file", shared)

    excluded_files = {normalize_path(path) for path in touched_files}

    # 2. A related file in the same directory or package.
    for path in _nearby_source_files(repository, ground_files):
        relative = path.relative_to(repository).as_posix()
        if normalize_path(relative) in excluded_files or _is_test_path(relative):
            continue
        match = _related_definition(path, issue_identifiers)
        if match:
            definition, shared = match
            return LocationChoice(relative, definition.name, "same_module", shared)

    # 3. A file with a direct import/call relation to the true file.
    ground_text = "\n".join(_read_small(repository / file_name) for file_name in ground_files)
    ground_terms = _identifiers(ground_text)
    ground_stems = {Path(file_name).stem.casefold() for file_name in ground_files}
    ground_symbols = {
        symbol.casefold() for symbols in symbols_by_file.values() for symbol in symbols
    }
    for path in _all_source_files(repository):
        relative = path.relative_to(repository).as_posix()
        if normalize_path(relative) in excluded_files or _is_test_path(relative):
            continue
        text = _read_small(path)
        terms = _identifiers(text)
        definitions = _definitions(path)
        related = (
            path.stem.casefold() in ground_terms
            or bool(ground_stems & terms)
            or bool(ground_symbols & terms)
            or any(definition.name.casefold() in ground_terms for definition in definitions)
        )
        if not related:
            continue
        match = _related_definition(path, issue_identifiers, definitions)
        if match:
            definition, shared = match
            return LocationChoice(relative, definition.name, "import_or_call", shared)
    raise HeuristicSkip("plausibility: no related incorrect location shares an issue identifier")


def _nearby_source_files(repository: Path, ground_files: list[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for file_name in ground_files:
        source = (repository / file_name).resolve()
        for directory in (source.parent, source.parent.parent):
            if not directory.is_relative_to(repository) or not directory.is_dir():
                continue
            candidates = sorted(path for path in directory.iterdir() if path.is_file())
            if directory == source.parent:
                for child in sorted(path for path in directory.iterdir() if path.is_dir()):
                    candidates.extend(sorted(path for path in child.iterdir() if path.is_file()))
            for path in candidates:
                if path not in seen and _is_source(path.as_posix()):
                    seen.add(path)
                    result.append(path)
    return result


def _all_source_files(repository: Path) -> list[Path]:
    return sorted(
        path
        for path in repository.rglob("*")
        if path.is_file() and _is_source(path.as_posix()) and path.stat().st_size <= 1_000_000
    )


def _related_definition(
    path: Path,
    issue_identifiers: set[str],
    definitions: list[Definition] | None = None,
) -> tuple[Definition, str] | None:
    definitions = definitions if definitions is not None else _definitions(path)
    file_shared = _identifiers(path.stem) & issue_identifiers
    for definition in definitions:
        if definition.name.startswith("__") and definition.name.endswith("__"):
            continue
        shared = _best_shared_identifier(definition.identifiers, issue_identifiers)
        if shared:
            return definition, shared
    if file_shared and definitions:
        shared = _best_shared_identifier(file_shared, issue_identifiers)
        if shared:
            return definitions[0], shared
    return None


def _best_shared_identifier(left: set[str] | frozenset[str], right: set[str]) -> str:
    candidates = [
        value
        for value in left & right
        if not (value.startswith("__") and value.endswith("__"))
        and value not in WEAK_LOCATION_IDENTIFIERS
        and ("_" in value or "." in value or len(value) >= 8)
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda value: ("_" in value or "." in value, len(value), value))


def _definitions(path: Path) -> list[Definition]:
    text = _read_small(path)
    if not text:
        return []
    if path.suffix.casefold() == ".py":
        tree = _parse_python(path)
        if tree is None:
            return []
        lines = text.splitlines()
        result: list[Definition] = []
        nodes = sorted(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            key=lambda node: node.lineno,
        )
        for node in nodes:
            end = int(getattr(node, "end_lineno", node.lineno))
            body = "\n".join(lines[node.lineno - 1 : end])
            result.append(
                Definition(
                    name=node.name,
                    line=node.lineno,
                    identifiers=frozenset({node.name.casefold(), *_identifiers(body)}),
                    members=frozenset(
                        child.name.casefold()
                        for child in ast.walk(node)
                        if child is not node
                        and isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                    ),
                )
            )
        return result

    result = []
    pattern = re.compile(
        r"\b(?:class|interface|struct|enum|def|function|fn)\s+([A-Za-z_]\w*)|"
        r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if not match:
            continue
        name = match.group(1) or match.group(2)
        if name in {"if", "for", "while", "switch", "catch"}:
            continue
        result.append(
            Definition(
                name=name,
                line=line_number,
                identifiers=frozenset({name.casefold(), *_identifiers(line)}),
            )
        )
    return result


def _apply_four_filters(
    *,
    repository: Path,
    payload: dict[str, Any],
    symbols_by_file: dict[str, list[str]],
    issue_identifiers: set[str],
    compatible_causes: tuple[str, ...],
    shared_identifier: str,
) -> None:
    ground = payload["ground_truth"]
    location = payload["hypotheses"]["wrong_location"][0]
    cause = payload["hypotheses"]["wrong_cause"][0]
    repair = payload["hypotheses"]["wrong_repair"][0]

    # 1. Existence.
    wrong_file = location["files"][0]
    wrong_symbol = location["symbols"][0]
    if not (repository / wrong_file).is_file():
        raise HeuristicSkip("existence: wrong-location file does not exist")
    known_symbols = {definition.name for definition in _definitions(repository / wrong_file)}
    if wrong_symbol not in known_symbols:
        raise HeuristicSkip("existence: wrong-location symbol does not exist")
    if shared_identifier not in issue_identifiers:
        raise HeuristicSkip("existence: selected identifier is not present in the issue")
    if ground["cause_type"] not in CAUSE_TYPES or cause["cause_type"] not in CAUSE_TYPES:
        raise HeuristicSkip("existence: cause type is outside the eight supported categories")

    # 2. Incorrectness.
    ground_pairs = {
        (normalize_path(file_name), symbol)
        for file_name, symbols in symbols_by_file.items()
        for symbol in symbols
    }
    if (normalize_path(wrong_file), wrong_symbol) in ground_pairs:
        raise HeuristicSkip("incorrectness: wrong location overlaps ground truth")
    if cause["cause_type"] == ground["cause_type"]:
        raise HeuristicSkip("incorrectness: wrong cause equals ground-truth cause")
    if repair["repair"] == ground["repair"]:
        raise HeuristicSkip("incorrectness: wrong repair equals developer repair")

    # 3. Plausibility.
    if cause["cause_type"] not in compatible_causes:
        raise HeuristicSkip("plausibility: wrong cause is incompatible with the symptom")
    if shared_identifier not in _identifiers(_read_small(repository / wrong_file)):
        raise HeuristicSkip("plausibility: wrong location does not share the issue identifier")

    # 4. Isolation. Metadata used for trajectory analysis is allowed, but each
    # rendered hypothesis has exactly one semantic variable.
    review_fields = {"why_plausible", "why_incorrect"}
    if set(location) != {"id", "files", "symbols", *review_fields}:
        raise HeuristicSkip("isolation: WLH contains fields other than location")
    if set(cause) != {"id", "cause_type", "cause", "keywords", *review_fields}:
        raise HeuristicSkip("isolation: WCH contains fields other than cause")
    if set(repair) != {"id", "repair", "keywords", *review_fields}:
        raise HeuristicSkip("isolation: WRH contains fields other than repair")


def _ground_symbols_by_file(repository: Path, files: list[str], patch: str) -> dict[str, list[str]]:
    hunk_lines = _diff_old_lines(patch)
    result: dict[str, list[str]] = {}
    for file_name in files:
        symbols: list[str] = []
        path = repository / file_name
        if path.suffix.casefold() == ".py" and path.is_file():
            symbols.extend(_python_symbols_at_lines(path, hunk_lines.get(file_name, [])))
        result[file_name] = list(dict.fromkeys(symbols))
    return result


def _diff_old_lines(patch: str) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = shlex.split(line[len("diff --git ") :])
            current = parts[0][2:] if len(parts) == 2 and parts[0].startswith("a/") else None
            if current:
                result.setdefault(current, [])
        elif line.startswith("@@") and current:
            match = re.match(r"^@@+ -(\d+)", line)
            if match:
                result[current].append(int(match.group(1)))
    return result


def _python_symbols_at_lines(path: Path, lines: list[int]) -> list[str]:
    if not lines:
        return []
    tree = _parse_python(path)
    if tree is None:
        return []
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    result: list[str] = []
    for line in lines:
        containing = [
            node
            for node in nodes
            if node.lineno <= line <= int(getattr(node, "end_lineno", node.lineno))
        ]
        if containing:
            node = min(
                containing,
                key=lambda item: int(getattr(item, "end_lineno", item.lineno)) - item.lineno,
            )
            result.append(node.name)
    return result


def _parse_python(path: Path) -> ast.AST | None:
    text = _read_small(path)
    if not text:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(text)
    except SyntaxError:
        return None


def _patch_lines(patch: str) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:].strip())
    return added, removed


def _identifiers(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text)
        if token.casefold() not in STOPWORDS and not keyword.iskeyword(token)
    }


def _is_source(path: str) -> bool:
    return Path(path).suffix.casefold() in SOURCE_SUFFIXES


def _is_test_path(path: str) -> bool:
    candidate = Path(path)
    parts = {part.casefold() for part in candidate.parts}
    name = candidate.name.casefold()
    return bool(
        {"test", "tests", "testing", "docs", "doc", "examples"} & parts
        or name.startswith(("test_", "tests_"))
        or name.endswith(("_test.py", "_tests.py"))
    )


def _read_small(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 1_000_000:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 3),
        "median": round(median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }
