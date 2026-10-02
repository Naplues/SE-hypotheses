"""Extract reproducible metrics and normalized events from mini-swe-agent trajectories."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rfm.io import dump_json, object_sha256, read_jsonl, write_csv
from rfm.models import Condition, normalize_path
from rfm.swebench import SWEBenchTask, load_swebench, parse_patch

MAX_TRAJECTORY_BYTES = 64 * 1024 * 1024
MAX_JSON_NODES = 1_000_000
MAX_JSON_DEPTH = 128

_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:/testbed/|\./)?"
    r"((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+"
    r"\.(?:py|pyx|pxd|c|cc|cpp|cxx|h|hpp|java|js|jsx|ts|tsx|go|rs|rb|php|"
    r"scala|kt|kts|swift|sh|rst|md|toml|cfg|ini|yaml|yml|json))"
)
_DIFF_FILE_PATTERN = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
_HYPOTHESIS_PATTERN = re.compile(
    r"<developer_hypothesis>\s*(.*?)\s*</developer_hypothesis>",
    re.IGNORECASE | re.DOTALL,
)
_TEST_COMMAND_PATTERN = re.compile(
    r"(?:^|[\s;&|])(?:python\s+-m\s+)?"
    r"(?:pytest|py\.test|nosetests|unittest|tox|nox)(?:\s|$)|"
    r"(?:^|[\s;&|])python\s+setup\.py\s+test(?:\s|$)|"
    r"(?:^|[\s;&|])(?:python\s+)?(?:runtests|run_tests)\.py(?:\s|$)",
    re.IGNORECASE,
)
_READ_COMMAND_PATTERN = re.compile(
    r"(?:^|[\s;&|])(?:rg|grep|find|ls|cat|head|tail|less|sed\s+-n|git\s+(?:log|show|"
    r"status|diff))(?:\s|$)",
    re.IGNORECASE,
)
_EDIT_COMMAND_PATTERN = re.compile(
    r"(?:apply_patch|sed\s+-i|perl\s+-pi|write_text\s*\(|"
    r"open\s*\([^\n]{0,160}['\"](?:w|a)[+b]?['\"]|"
    r"(?:^|[;&|]\s*|\n)\s*(?:cat|printf|echo)\b[^\n]*>{1,2})",
    re.IGNORECASE,
)
_ERROR_OUTPUT_PATTERN = re.compile(
    r"(?:^|\n)(?:FAILED\b|FAIL\s+|ERROR\b)|\b(?:\d+)\s+failed\b|"
    r"Traceback \(most recent call last\)",
    re.IGNORECASE,
)
_TIMEOUT_PATTERN = re.compile(r"timed?\s*out|timeout", re.IGNORECASE)
_CONFIG_CONDITIONS = {
    "ORIG": Condition.ORIGINAL.value,
    # Keep compatibility with the existing experiment directory typo.
    "ORGI": Condition.ORIGINAL.value,
    "CH": Condition.CORRECT.value,
    "WLH": Condition.WRONG_LOCATION.value,
    "WCH": Condition.WRONG_CAUSE.value,
    "WRH": Condition.WRONG_REPAIR.value,
}

_CONDITION_OUTPUTS = {
    Condition.ORIGINAL.value: "ORIG",
    Condition.CORRECT.value: "CH",
    Condition.WRONG_LOCATION.value: "WLH",
    Condition.WRONG_CAUSE.value: "WCH",
    Condition.WRONG_REPAIR.value: "WRH",
}

# One row per trajectory. Every column is either used by the RQ analysis,
# required for pairing/provenance, or a compact quality-control diagnostic.
FEATURE_FIELDS = (
    "source_file",
    "instance_id",
    "repo",
    "condition",
    "configuration_id",
    "run_id",
    "block_id",
    "agent_id",
    "model_id",
    "repetition",
    "hypothesis_id",
    "status",
    "submitted",
    "evaluator_resolved",
    "elapsed_seconds",
    "time_to_first_successful_edit_seconds",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "recorded_cost",
    "steps",
    "tool_calls",
    "search_read_calls",
    "edit_calls",
    "test_calls",
    "test_calls_with_failures",
    "developer_hypothesis_present",
    "modified_file_count",
    "modified_files",
    "patch_added_lines",
    "patch_deleted_lines",
    "gold_file_precision",
    "gold_file_recall",
    "gold_added_line_recall",
    "gold_removed_line_recall",
    "submitted_added_line_precision",
)


@dataclass(frozen=True)
class TrajectorySource:
    path: Path
    source_file: str
    configuration_id: str | None
    condition: str | None


def extract_trajectories(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    condition: str | None = None,
    tasks_path: str | Path | None = None,
    auto_configurations: bool = False,
    configuration_id: str | None = None,
    agent_id: str | None = None,
    model_id: str | None = None,
    repetition: int = 1,
    manifest_path: str | Path | None = None,
    evaluations_path: str | Path | None = None,
    normalized_runs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Extract one feature row and a normalized event stream per trajectory."""

    if condition is not None:
        condition = Condition(condition).value
    source = Path(input_path).resolve()
    sources = _trajectory_sources(
        source,
        auto_configurations=auto_configurations,
        configuration_id=configuration_id,
        condition=condition,
    )
    tasks = _tasks_by_id(tasks_path) if tasks_path else {}
    manifest = list(read_jsonl(manifest_path)) if manifest_path else []
    evaluations = _load_evaluations(evaluations_path)
    output = Path(output_dir).resolve()
    normalized_root = Path(normalized_runs_dir).resolve() if normalized_runs_dir else output
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    records_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failures_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    selected_by_group: Counter[str] = Counter()

    seen_run_ids: set[str] = set()
    for selected in sources:
        path = selected.path
        source_file = selected.source_file
        group = _output_group(selected.configuration_id, selected.condition)
        try:
            raw = _load_strict_json(path)
            record, events = extract_trajectory(
                raw,
                source_file=source_file,
                condition=selected.condition,
                task=tasks.get(str(raw.get("instance_id", ""))),
            )
            record["configuration_id"] = selected.configuration_id
            group = _output_group(selected.configuration_id, str(record["condition"]))
            identity = _run_identity(
                record,
                manifest,
                agent_override=agent_id,
                model_override=model_id,
                repetition=repetition,
            )
            if identity["run_id"] in seen_run_ids:
                raise ValueError(f"Duplicate run identity: {identity['run_id']}")
            seen_run_ids.add(identity["run_id"])
            record.update(identity)
            resolved = _evaluation_for(record, evaluations)
            record["evaluator_resolved"] = resolved
            record["steps"] = len(events)
            _write_normalized_run(normalized_root / group / "runs", record, events)
            feature_record = _feature_record(record)
            records.append(feature_record)
            records_by_group[group].append(feature_record)
        except (OSError, TypeError, ValueError) as exc:
            failure = {"source_file": source_file, "error": str(exc)}
            failures.append(failure)
            failures_by_group[group].append(failure)
        selected_by_group[group] += 1

    records.sort(key=lambda item: (str(item["instance_id"]), str(item["source_file"])))
    condition_outputs: dict[str, str] = {}
    for group in sorted(selected_by_group):
        group_output = output / group
        group_records = sorted(
            records_by_group[group],
            key=lambda item: (str(item["instance_id"]), str(item["source_file"])),
        )
        dump_json(
            group_output / "trajectory-features.json",
            {"schema_version": 2, "records": group_records},
        )
        write_csv(
            group_output / "trajectory-features.csv",
            [_csv_row(record) for record in group_records],
        )
        group_summary = _extraction_summary(
            group_records,
            selected=selected_by_group[group],
            failures=failures_by_group[group],
            output_dir=group_output,
            normalized_runs_dir=normalized_root / group / "runs",
        )
        dump_json(group_output / "extraction-summary.json", group_summary)
        condition_outputs[group] = str(group_output)

    summary = _extraction_summary(
        records,
        selected=len(sources),
        failures=failures,
        output_dir=output,
        normalized_runs_dir=normalized_root,
    )
    summary["condition_outputs"] = condition_outputs
    dump_json(output / "extraction-summary.json", summary)
    return summary


def _extraction_summary(
    records: list[dict[str, Any]],
    *,
    selected: int,
    failures: list[dict[str, str]],
    output_dir: Path,
    normalized_runs_dir: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "selected": selected,
        "completed": len(records),
        "failures": failures,
        "output_dir": str(output_dir),
        "normalized_runs_dir": str(normalized_runs_dir),
        "configurations": dict(
            sorted(Counter(str(record.get("configuration_id")) for record in records).items())
        ),
        "conditions": dict(
            sorted(Counter(str(record.get("condition")) for record in records).items())
        ),
        "statuses": dict(sorted(Counter(str(record.get("status")) for record in records).items())),
        "evaluations": {
            "resolved": sum(record.get("evaluator_resolved") is True for record in records),
            "unresolved": sum(record.get("evaluator_resolved") is False for record in records),
            "missing": sum(record.get("evaluator_resolved") is None for record in records),
        },
    }


def extract_trajectory(
    raw: dict[str, Any],
    *,
    source_file: str,
    condition: str | None = None,
    task: SWEBenchTask | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract a feature row and normalized events from one parsed trajectory."""

    info = _object(raw.get("info"), "info")
    messages = raw.get("messages")
    if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
        raise ValueError("messages must be an array of objects")
    instance_id = _required_text(raw.get("instance_id"), "instance_id")
    trajectory_format = _required_text(raw.get("trajectory_format"), "trajectory_format")
    if not trajectory_format.startswith("mini-swe-agent-"):
        raise ValueError(f"unsupported trajectory_format: {trajectory_format}")

    config = _object(info.get("config", {}), "info.config")
    model_config = _object(config.get("model", {}), "info.config.model")
    tool_results = {
        str(message.get("tool_call_id")): message
        for message in messages
        if message.get("role") == "tool" and message.get("tool_call_id")
    }
    timestamps = [
        float(extra["timestamp"])
        for message in messages
        if isinstance((extra := message.get("extra")), dict)
        and isinstance(extra.get("timestamp"), (int, float))
    ]
    started = min(timestamps) if timestamps else None
    ended = max(timestamps) if timestamps else None

    user_text = "\n".join(
        str(message.get("content") or "") for message in messages if message.get("role") == "user"
    )
    hypothesis_match = _HYPOTHESIS_PATTERN.search(user_text)
    hypothesis = hypothesis_match.group(1).strip() if hypothesis_match else ""
    inferred_condition = condition or (Condition.ORIGINAL.value if not hypothesis else "unknown")
    calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    step = 0
    usage_totals = Counter()
    for message in messages:
        if message.get("role") != "assistant":
            continue
        usage = _usage(message)
        usage_totals.update(usage)
        thought = str(message.get("reasoning_content") or message.get("content") or "")
        step += 1
        events.append(
            {
                "step": step,
                "event_type": "reasoning" if thought else "message",
                "timestamp": _timestamp(message),
                "text": thought or None,
            }
        )
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = _object(tool_call.get("function", {}), "tool_call.function")
            arguments = _tool_arguments(function.get("arguments"))
            command = str(arguments.get("command") or arguments.get("cmd") or "")
            result = tool_results.get(str(tool_call.get("id")))
            output_text = str(result.get("content") or "") if result else ""
            result_extra = _object(result.get("extra", {}), "tool_result.extra") if result else {}
            returncode = result_extra.get("returncode")
            timestamp = _timestamp(message)
            command_kind = _command_kind(command)
            files = _paths_from_command(command)
            modified = _modified_paths(command, files) if command_kind == "edit" else []
            call = {
                "timestamp": timestamp,
                "command": command,
                "kind": command_kind,
                "returncode": returncode,
                "output": output_text,
                "files": files,
                "modified": modified,
                "timed_out": _timed_out(returncode, output_text, result_extra),
            }
            calls.append(call)
            step += 1
            events.append(
                {
                    "step": step,
                    "event_type": {
                        "test": "test",
                        "edit": "file_write",
                        "read": "file_read",
                    }.get(command_kind, "shell"),
                    "timestamp": timestamp,
                    "tool_output": output_text or None,
                    "command": command or None,
                    "files_accessed": files,
                    "files_modified": modified,
                }
            )

    submission = _submission(info, messages)
    patch = _patch_metrics(submission)
    if submission:
        step += 1
        events.append(
            {
                "step": step,
                "event_type": "patch",
                "text": submission,
                "files_modified": patch["modified_files"],
            }
        )

    successful_edit_times = [
        call["timestamp"]
        for call in calls
        if call["kind"] == "edit" and call["timestamp"] is not None and not _call_failed(call)
    ]
    first_edit = min(successful_edit_times, default=None)
    elapsed = ended - started if started is not None and ended is not None else None
    time_to_first_edit = (
        first_edit - started if first_edit is not None and started is not None else None
    )
    test_calls = [call for call in calls if call["kind"] == "test"]
    test_failure_calls = [
        call for call in test_calls if _ERROR_OUTPUT_PATTERN.search(call["output"])
    ]
    model_stats = _object(info.get("model_stats", {}), "info.model_stats")
    record: dict[str, Any] = {
        "source_file": source_file,
        "instance_id": instance_id,
        "repo": task.repo if task else None,
        "base_commit": task.base_commit if task else None,
        "condition": inferred_condition,
        "mini_version": info.get("mini_version"),
        "model_name": model_config.get("model_name"),
        "status": _run_status(info, bool(submission)),
        "submitted": bool(submission),
        "evaluator_resolved": None,
        "tool_calls": len(calls),
        "search_read_calls": sum(call["kind"] == "read" for call in calls),
        "edit_calls": sum(call["kind"] == "edit" for call in calls),
        "test_calls": len(test_calls),
        "test_calls_with_failures": len(test_failure_calls),
        "prompt_tokens": usage_totals["prompt_tokens"],
        "completion_tokens": usage_totals["completion_tokens"],
        "total_tokens": usage_totals["total_tokens"],
        "recorded_cost": model_stats.get("instance_cost"),
        "elapsed_seconds": _rounded(elapsed),
        "time_to_first_successful_edit_seconds": _rounded(time_to_first_edit),
        "developer_hypothesis_present": bool(hypothesis),
        **patch,
    }
    if task:
        record.update(_gold_overlap(submission, task))
    else:
        record.update(_empty_gold_overlap())
    return record, events


def _trajectory_paths(source: Path) -> list[Path]:
    if not source.exists():
        raise ValueError(f"Input does not exist: {source}")
    if source.is_symlink():
        raise ValueError(f"Input symlinks are not supported: {source}")
    paths = [source] if source.is_file() else sorted(source.rglob("*.traj.json"))
    if not paths:
        raise ValueError(f"No *.traj.json files found in {source}")
    return paths


def _trajectory_sources(
    source: Path,
    *,
    auto_configurations: bool,
    configuration_id: str | None,
    condition: str | None,
) -> list[TrajectorySource]:
    if not auto_configurations:
        inferred_configuration = configuration_id
        if inferred_configuration is None and source.is_dir() and source.name == "mini_run":
            inferred_configuration = source.parent.name
        return [
            TrajectorySource(
                path=path,
                source_file=path.name if source.is_file() else path.relative_to(source).as_posix(),
                configuration_id=inferred_configuration,
                condition=condition,
            )
            for path in _trajectory_paths(source)
        ]
    if condition is not None or configuration_id is not None:
        raise ValueError(
            "condition and configuration_id must not be supplied with auto configuration mode"
        )
    if not source.is_dir():
        raise ValueError("Auto configuration mode requires an input root directory")
    selected: list[TrajectorySource] = []
    for mini_run in sorted(source.glob("*/mini_run")):
        if not mini_run.is_dir():
            continue
        config = mini_run.parent.name
        parsed_condition = _condition_from_configuration(config)
        for path in _trajectory_paths(mini_run):
            selected.append(
                TrajectorySource(
                    path=path,
                    source_file=path.relative_to(source).as_posix(),
                    configuration_id=config,
                    condition=parsed_condition,
                )
            )
    if not selected:
        raise ValueError(f"No result/<configuration>/mini_run/*.traj.json files found in {source}")
    return selected


def _condition_from_configuration(configuration_id: str) -> str:
    suffix = configuration_id.rsplit("_", 1)[-1].upper()
    try:
        return _CONFIG_CONDITIONS[suffix]
    except KeyError as exc:
        raise ValueError(
            f"Cannot infer condition from configuration {configuration_id!r}; "
            f"expected suffix in {sorted(_CONFIG_CONDITIONS)}"
        ) from exc


def _output_group(configuration_id: str | None, condition: str | None) -> str:
    if configuration_id and "_" in configuration_id:
        suffix = configuration_id.rsplit("_", 1)[-1].upper()
        if suffix in _CONFIG_CONDITIONS:
            return suffix
    return _CONDITION_OUTPUTS.get(str(condition), "UNKNOWN")


def _load_strict_json(path: Path) -> dict[str, Any]:
    stat = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Trajectory must be a regular non-symlink file: {path.name}")
    if stat.st_nlink != 1:
        raise ValueError(f"Trajectory must not be hard-linked: {path.name}")
    if stat.st_size > MAX_TRAJECTORY_BYTES:
        raise ValueError(f"Trajectory exceeds {MAX_TRAJECTORY_BYTES} bytes: {path.name}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON numeric constant: {value}")

    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Trajectory root must be an object")
    _validate_json_bounds(raw)
    return raw


def _validate_json_bounds(root: Any) -> None:
    stack = [(root, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError(f"Trajectory exceeds {MAX_JSON_NODES} JSON nodes")
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"Trajectory exceeds JSON depth {MAX_JSON_DEPTH}")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _tasks_by_id(path: str | Path) -> dict[str, SWEBenchTask]:
    return {task.instance_id: task for task in load_swebench(path)}


def _run_identity(
    record: dict[str, Any],
    manifest: list[dict[str, Any]],
    *,
    agent_override: str | None,
    model_override: str | None,
    repetition: int,
) -> dict[str, Any]:
    if repetition < 1:
        raise ValueError("repetition must be positive")
    configuration = str(record.get("configuration_id") or "unclassified")
    model_group = configuration.rsplit("_", 1)[0] if "_" in configuration else configuration
    mini_version = str(record.get("mini_version") or "unknown")
    agent_id = agent_override or f"mini-swe-agent@{mini_version}"
    model_id = model_override or str(record.get("model_name") or model_group or "unknown")
    condition = str(record.get("condition") or "")
    instance_id = str(record["instance_id"])
    if manifest:
        candidates = [
            item
            for item in manifest
            if str(item.get("instance_id")) == instance_id
            and str(item.get("condition")) == condition
            and int(item.get("repetition", 1)) == repetition
        ]
        exact = [
            item
            for item in candidates
            if str(item.get("agent_id")) == agent_id and str(item.get("model_id")) == model_id
        ]
        if len(exact) == 1:
            selected = exact[0]
        elif len(candidates) == 1:
            selected = candidates[0]
        else:
            raise ValueError(
                f"Manifest match for {instance_id}/{configuration}/{condition} is not unique; "
                "use --agent-id and --model-id matching the manifest"
            )
        return {
            "run_id": _required_text(selected.get("run_id"), "manifest.run_id"),
            "block_id": _required_text(selected.get("block_id"), "manifest.block_id"),
            "agent_id": _required_text(selected.get("agent_id"), "manifest.agent_id"),
            "model_id": _required_text(selected.get("model_id"), "manifest.model_id"),
            "repetition": int(selected.get("repetition", repetition)),
            "hypothesis_id": selected.get("hypothesis_id"),
            "repo": selected.get("repo") or record.get("repo"),
            "base_commit": selected.get("base_commit") or record.get("base_commit"),
        }
    block_key = f"{instance_id}|{agent_id}|{model_id}|r{repetition}"
    run_key = f"{block_key}|{condition}"
    return {
        "run_id": f"run-{object_sha256(run_key)[:20]}",
        "block_id": f"block-{object_sha256(block_key)[:16]}",
        "agent_id": agent_id,
        "model_id": model_id,
        "repetition": repetition,
        "hypothesis_id": None,
        "repo": record.get("repo"),
        "base_commit": record.get("base_commit"),
    }


def _load_evaluations(path: str | Path | None) -> list[dict[str, Any]] | None:
    if path is None:
        return None
    source = Path(path)
    if source.is_dir():
        rows = _load_swebench_evaluation_reports(source)
    elif source.suffix.casefold() == ".jsonl":
        rows = list(read_jsonl(source))
    else:
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and isinstance(raw.get("records"), list):
            rows = raw["records"]
        elif isinstance(raw, dict):
            rows = []
            for key, value in raw.items():
                if isinstance(value, bool):
                    rows.append({"run_id": key, "resolved": value})
                elif isinstance(value, dict):
                    rows.append({"run_id": key, **value})
        else:
            raise ValueError(f"Unsupported evaluation result structure: {source}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Evaluation records must be JSON objects: {source}")
    for row in rows:
        if not isinstance(row.get("resolved"), bool):
            raise ValueError("Each evaluation record requires boolean resolved")
    return rows


def _load_swebench_evaluation_reports(source: Path) -> list[dict[str, Any]]:
    paths = sorted(source.glob("*/logs/run_evaluation/**/report.json"))
    if (source / "logs" / "run_evaluation").is_dir():
        paths.extend(sorted((source / "logs" / "run_evaluation").rglob("report.json")))
    paths = list(dict.fromkeys(paths))
    if not paths:
        raise ValueError(f"No SWE-bench evaluation report.json files found in {source}")

    outcomes: dict[tuple[str, str], bool] = {}
    for path in paths:
        configuration_id = _evaluation_configuration(source, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw:
            raise ValueError(f"Evaluation report must be a non-empty object: {path}")
        for instance_id, result in raw.items():
            if not isinstance(result, dict) or not isinstance(result.get("resolved"), bool):
                raise ValueError(
                    f"Evaluation result for {instance_id!r} requires boolean resolved: {path}"
                )
            key = (str(instance_id), configuration_id)
            resolved = bool(result["resolved"])
            if key in outcomes and outcomes[key] != resolved:
                raise ValueError(
                    f"Conflicting evaluation results for {instance_id}/{configuration_id}"
                )
            outcomes[key] = resolved
    return [
        {
            "instance_id": instance_id,
            "configuration_id": configuration_id,
            "resolved": resolved,
        }
        for (instance_id, configuration_id), resolved in sorted(outcomes.items())
    ]


def _evaluation_configuration(source: Path, report: Path) -> str:
    parts = report.relative_to(source).parts
    try:
        logs_index = parts.index("logs")
    except ValueError as exc:
        raise ValueError(
            f"Cannot infer configuration from evaluation report path: {report}"
        ) from exc
    return source.name if logs_index == 0 else parts[logs_index - 1]


def _evaluation_for(
    record: dict[str, Any], evaluations: list[dict[str, Any]] | None
) -> bool | None:
    if evaluations is None:
        return None
    run_matches = [row for row in evaluations if row.get("run_id") == record.get("run_id")]
    if len(run_matches) == 1:
        return bool(run_matches[0]["resolved"])
    if len(run_matches) > 1:
        raise ValueError(f"Multiple evaluation results for run {record.get('run_id')}")
    compound_matches = [
        row
        for row in evaluations
        if row.get("instance_id") == record.get("instance_id")
        and row.get("configuration_id") == record.get("configuration_id")
    ]
    if len(compound_matches) == 1:
        return bool(compound_matches[0]["resolved"])
    if len(compound_matches) > 1:
        raise ValueError(
            "Multiple evaluation results for "
            f"{record.get('instance_id')}/{record.get('configuration_id')}"
        )
    if record.get("configuration_id") is not None:
        return None
    instance_matches = [
        row for row in evaluations if row.get("instance_id") == record.get("instance_id")
    ]
    if len(instance_matches) == 1:
        return bool(instance_matches[0]["resolved"])
    if len(instance_matches) > 1 and record.get("configuration_id") is None:
        raise ValueError(f"Multiple evaluation results for {record.get('instance_id')}")
    return None


def _write_normalized_run(
    root: Path,
    record: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    directory = root / _run_directory_name(record)
    run = {
        "schema_version": 2,
        "run_id": record["run_id"],
        "block_id": record["block_id"],
        "instance_id": record["instance_id"],
        "configuration_id": record.get("configuration_id"),
        "agent_id": record["agent_id"],
        "model_id": record["model_id"],
        "repetition": record["repetition"],
        "condition": record["condition"],
        "hypothesis_id": record.get("hypothesis_id"),
        "repo": record.get("repo"),
        "base_commit": record.get("base_commit"),
    }
    run = {key: value for key, value in run.items() if value is not None}
    result = {
        "schema_version": 2,
        "status": record["status"],
        "resolved": record.get("evaluator_resolved"),
        "submitted": record["submitted"],
        "tokens_input": record["prompt_tokens"],
        "tokens_output": record["completion_tokens"],
        "tokens_total": record["total_tokens"],
        "recorded_cost": record["recorded_cost"],
        "tool_calls": record["tool_calls"],
        "runtime_seconds": record["elapsed_seconds"],
        "steps": record["steps"],
        "edit_operations": record["edit_calls"],
        "test_executions": record["test_calls"],
        "test_failures": record["test_calls_with_failures"],
        "modified_file_count": record["modified_file_count"],
        "patch_added_lines": record["patch_added_lines"],
        "patch_deleted_lines": record["patch_deleted_lines"],
    }
    dump_json(directory / "run.json", run)
    dump_json(directory / "result.json", result)
    _write_jsonl(directory / "trajectory.jsonl", events)


def _run_directory_name(record: dict[str, Any]) -> str:
    instance_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record["instance_id"]))
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record["run_id"]))
    return f"{instance_id}__{run_id}"


def _tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


def _usage(message: dict[str, Any]) -> dict[str, int]:
    extra = message.get("extra")
    response = extra.get("response") if isinstance(extra, dict) else None
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return {}
    result = {
        key: int(usage[key])
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if isinstance(usage.get(key), (int, float))
    }
    if "total_tokens" not in result and (
        "prompt_tokens" in result or "completion_tokens" in result
    ):
        result["total_tokens"] = result.get("prompt_tokens", 0) + result.get(
            "completion_tokens", 0
        )
    return result


def _timestamp(message: dict[str, Any]) -> float | None:
    extra = message.get("extra")
    value = extra.get("timestamp") if isinstance(extra, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _submission(info: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    value = info.get("submission")
    if isinstance(value, str) and value.strip():
        return value.strip()
    for message in reversed(messages):
        if message.get("role") != "exit":
            continue
        extra = message.get("extra")
        candidate = extra.get("submission") if isinstance(extra, dict) else None
        candidate = candidate or message.get("content")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _run_status(info: dict[str, Any], submitted: bool) -> str:
    if submitted:
        return "completed_submitted"
    text = " ".join(
        str(info.get(key) or "")
        for key in ("exit_status", "terminal_reason", "error", "exception")
    ).casefold()
    if re.search(r"timed?\s*out|timeout|wall.?time", text):
        return "agent_timeout"
    if re.search(r"max(?:imum)?[ _-]?(?:steps?|turns?)|step.?limit", text):
        return "max_steps"
    if re.search(r"error|exception|failed", text):
        return "agent_error"
    return "completed_no_patch"


def _command_kind(command: str) -> str:
    if _TEST_COMMAND_PATTERN.search(command):
        return "test"
    if _EDIT_COMMAND_PATTERN.search(command):
        return "edit"
    if _READ_COMMAND_PATTERN.search(command):
        return "read"
    return "shell"


def _paths_from_command(command: str) -> list[str]:
    return list(dict.fromkeys(normalize_path(match) for match in _PATH_PATTERN.findall(command)))


def _modified_paths(command: str, candidates: list[str]) -> list[str]:
    explicit = re.findall(r"\b(?:p|path|filename)\s*=\s*['\"]([^'\"]+)['\"]", command)
    normalized = [normalize_path(value.removeprefix("/testbed/")) for value in explicit]
    values = [*normalized, *candidates]
    return list(
        dict.fromkeys(
            value
            for value in values
            if not value.startswith(("/tmp/", "tmp/")) and Path(value).name not in {"patch.txt"}
        )
    )


def _timed_out(returncode: Any, output: str, extra: dict[str, Any]) -> bool:
    exception = "\n".join(
        str(extra.get(key) or "") for key in ("exception", "exception_info", "exception_type")
    )
    return returncode == -1 or bool(_TIMEOUT_PATTERN.search(f"{exception}\n{output}"))


def _call_failed(call: dict[str, Any]) -> bool:
    if call["timed_out"] or call["returncode"] not in (None, 0):
        return True
    output = call["output"]
    return "Traceback (most recent call last)" in output or "<exception>" in output


def _patch_metrics(patch: str) -> dict[str, Any]:
    files = list(
        dict.fromkeys(
            normalize_path(right)
            for left, right in _DIFF_FILE_PATTERN.findall(patch)
            if right != "/dev/null"
        )
    )
    added = sum(line.startswith("+") and not line.startswith("+++") for line in patch.splitlines())
    deleted = sum(
        line.startswith("-") and not line.startswith("---") for line in patch.splitlines()
    )
    return {
        "modified_file_count": len(files),
        "modified_files": files,
        "patch_added_lines": added,
        "patch_deleted_lines": deleted,
    }


def _gold_overlap(submission: str, task: SWEBenchTask) -> dict[str, Any]:
    submitted_files = set(_patch_metrics(submission)["modified_files"])
    gold_files = {normalize_path(path) for path in parse_patch(task.patch)["touched_files"]}
    overlap = submitted_files & gold_files
    submitted_added, submitted_removed = _changed_lines(submission)
    gold_added, gold_removed = _changed_lines(task.patch)
    return {
        "gold_file_precision": _ratio(len(overlap), len(submitted_files)),
        "gold_file_recall": _ratio(len(overlap), len(gold_files)),
        "gold_added_line_recall": _ratio(len(submitted_added & gold_added), len(gold_added)),
        "gold_removed_line_recall": _ratio(
            len(submitted_removed & gold_removed), len(gold_removed)
        ),
        "submitted_added_line_precision": _ratio(
            len(submitted_added & gold_added), len(submitted_added)
        ),
    }


def _empty_gold_overlap() -> dict[str, Any]:
    return {
        "gold_file_precision": None,
        "gold_file_recall": None,
        "gold_added_line_recall": None,
        "gold_removed_line_recall": None,
        "submitted_added_line_precision": None,
    }


def _changed_lines(patch: str) -> tuple[set[str], set[str]]:
    added: set[str] = set()
    removed: set[str] = set()
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+") and line[1:].strip():
            added.add(" ".join(line[1:].split()))
        elif line.startswith("-") and line[1:].strip():
            removed.add(" ".join(line[1:].split()))
    return added, removed


def _csv_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ";".join(str(item) for item in value) if isinstance(value, list) else value
        for key, value in record.items()
    }


def _feature_record(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in FEATURE_FIELDS}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _rounded(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    return value


def _required_text(value: Any, location: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{location} cannot be empty")
    return text
