"""Identify a task's source repository from only its issue description."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rfm.io import dump_json, read_jsonl, write_jsonl
from rfm.swebench import SWEBenchTask, load_swebench

DIAGNOSTIC_VERSION = "repository-origin-v1"
RECOGNITION_BASES = {"explicit", "technical_inference", "exact_recognition", "unknown"}

SYSTEM_PROMPT = """You are given only a software issue description taken from a public
software project.

Without accessing a repository, external tools, the Internet, tests, or additional
context, identify the GitHub repository from which the issue most likely originated.
Use the canonical owner/repository form. If you recognize the exact public issue or its
corresponding pull request, provide its number; otherwise use null. Do not guess numbers.
If the repository cannot be identified reliably, use null.

Return only one valid JSON object with exactly these fields:
{
  "predicted_repository": null,
  "alternative_repositories": [],
  "predicted_issue_number": null,
  "predicted_pull_request_number": null,
  "recognition_basis": "unknown",
  "confidence": 0.0
}

alternative_repositories must contain at most two owner/repository strings.
recognition_basis must be one of: explicit, technical_inference, exact_recognition,
unknown. Use explicit when the project or repository is named in the issue,
technical_inference when the answer is inferred from APIs or terminology, and
exact_recognition only when you recognize the particular public issue rather than merely
the project. confidence must be between 0 and 1."""


def issue_only_user_prompt(problem_statement: str) -> str:
    """Render the only task-specific text sent to the model."""

    issue = problem_statement.strip()
    if not issue:
        raise ValueError("problem_statement cannot be empty")
    return f"<issue>\n{issue}\n</issue>"


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible chat-completions client using the standard library."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> None:
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.model = model
        self.api_key = api_key
        self.endpoint = _chat_completions_endpoint(base_url)
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete(self, problem_statement: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": issue_only_user_prompt(problem_statement)},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Request failed: {exc.reason}") from exc
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Response does not contain choices[0].message.content") from exc
        if not isinstance(content, str):
            raise ValueError("Response message content must be text")
        try:
            return parse_repository_diagnostic(content)
        except ValueError as exc:
            preview = re.sub(r"\s+", " ", content).strip()[:500]
            raise ValueError(f"{exc}; response preview: {preview!r}") from exc


def parse_repository_diagnostic(content: str) -> dict[str, Any]:
    """Parse and validate one model diagnostic response."""

    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model response does not contain a JSON object") from None
        try:
            raw = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid model JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Model response must be a JSON object")

    repository = _optional_repository(raw.get("predicted_repository"), "predicted_repository")
    alternatives = _repository_list(raw.get("alternative_repositories"))
    alternatives = [value for value in alternatives if value != repository]
    issue_number = _optional_positive_integer(
        raw.get("predicted_issue_number"), "predicted_issue_number"
    )
    pull_request_number = _optional_positive_integer(
        raw.get("predicted_pull_request_number"), "predicted_pull_request_number"
    )
    recognition_basis = _optional_text(raw.get("recognition_basis"), "recognition_basis")
    if recognition_basis not in RECOGNITION_BASES:
        raise ValueError(f"Unsupported recognition_basis: {recognition_basis}")
    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return {
        "predicted_repository": repository,
        "alternative_repositories": alternatives,
        "predicted_issue_number": issue_number,
        "predicted_pull_request_number": pull_request_number,
        "recognition_basis": recognition_basis,
        "confidence": confidence,
    }


def run_issue_only_diagnostic(
    input_path: str | Path,
    tasks_dir: str | Path,
    output_path: str | Path,
    *,
    model: str,
    complete: Callable[[str], dict[str, Any]],
    workers: int = 1,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20260929,
    force: bool = False,
    retries: int = 2,
    summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run diagnostics for constructed task IDs and write resumable JSONL output."""

    if workers < 1:
        raise ValueError("workers must be at least 1")
    if retries < 0:
        raise ValueError("retries cannot be negative")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    if sample is not None and sample < 1:
        raise ValueError("sample must be positive")
    if limit is not None and sample is not None:
        raise ValueError("limit and sample are mutually exclusive")

    selected_ids = {
        path.stem
        for path in Path(tasks_dir).glob("*.json")
        if path.name != "construction-summary.json"
    }
    if not selected_ids:
        raise ValueError(f"No constructed task JSON files found in {tasks_dir}")
    tasks = [task for task in load_swebench(input_path) if task.instance_id in selected_ids]
    missing = selected_ids - {task.instance_id for task in tasks}
    if missing:
        raise ValueError(f"Constructed tasks missing from SWE-bench input: {sorted(missing)[:3]}")
    if limit is not None:
        tasks = tasks[:limit]
    elif sample is not None:
        tasks = random.Random(seed).sample(tasks, min(sample, len(tasks)))

    output = Path(output_path)
    existing = {} if force else _existing_results(output, model)
    pending = [task for task in tasks if task.instance_id not in existing]
    completed: dict[str, dict[str, Any]] = dict(existing)
    failures: list[dict[str, Any]] = []
    started = time.monotonic()

    def execute(task: SWEBenchTask) -> tuple[dict[str, Any], float]:
        task_started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                diagnostic = parse_repository_diagnostic(
                    json.dumps(complete(task.problem_statement))
                )
                expected_pull_request = int(task.instance_id.rsplit("-", 1)[-1])
                predicted_pull_request = diagnostic["predicted_pull_request_number"]
                return (
                    {
                        "instance_id": task.instance_id,
                        "model": model,
                        "diagnostic_version": DIAGNOSTIC_VERSION,
                        **diagnostic,
                        "repository_match": _same_repository(
                            diagnostic["predicted_repository"], task.repo
                        ),
                        "repository_name_explicit_in_issue": _repository_named_in_issue(
                            task.repo, task.problem_statement
                        ),
                        "pull_request_match": (
                            None
                            if predicted_pull_request is None
                            else predicted_pull_request == expected_pull_request
                        ),
                    },
                    time.monotonic() - task_started,
                )
            except Exception as exc:  # noqa: BLE001 - failure is recorded per task
                last_error = exc
                if attempt < retries:
                    time.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise last_error

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(execute, task): task for task in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                row, seconds = future.result()
                completed[task.instance_id] = row
                outcome = "completed"
            except Exception as exc:  # noqa: BLE001 - preserve other task results
                seconds = None
                failures.append({"instance_id": task.instance_id, "error": str(exc)})
                outcome = "failed"
            _write_selected_results(output, tasks, completed)
            duration = "-" if seconds is None else f"{seconds:.1f}s"
            print(
                f"[{index}/{len(pending)}] {task.instance_id}: {outcome}; {duration}",
                file=sys.stderr,
                flush=True,
            )

    selected_completed = [task.instance_id for task in tasks if task.instance_id in completed]
    summary = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "selected": len(tasks),
        "completed": len(selected_completed),
        "skipped_existing": len(tasks) - len(pending),
        "failures": failures,
        "sample_seed": seed if sample is not None else None,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "output": str(output.resolve()),
        "model": model,
    }
    summary_target = (
        Path(summary_path)
        if summary_path is not None
        else output.with_name(f"{output.stem}-summary.json")
    )
    dump_json(summary_target, summary)
    return summary


def default_base_url() -> str:
    return (
        os.environ.get("GLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://open.bigmodel.cn/api/paas/v4"
    )


def api_key_from_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Environment variable {name} is not set")
    return value


def _chat_completions_endpoint(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/chat/completions") else f"{value}/chat/completions"


def _repository_list(raw: Any) -> list[str]:
    if not isinstance(raw, list) or len(raw) > 2:
        raise ValueError("alternative_repositories must contain at most two repositories")
    values: list[str] = []
    for item in raw:
        value = _optional_repository(item, "alternative_repositories")
        if value is None:
            raise ValueError("alternative_repositories cannot contain null")
        if value not in values:
            values.append(value)
    return values


def _optional_repository(raw: Any, field: str) -> str | None:
    value = _optional_text(raw, field)
    if value is None:
        return None
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.I).strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError(f"{field} must use owner/repository form")
    return value


def _optional_positive_integer(raw: Any, field: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError(f"{field} must be a positive integer or null")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a positive integer or null") from exc
    if value < 1:
        raise ValueError(f"{field} must be a positive integer or null")
    return value


def _optional_text(raw: Any, field: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be text or null")
    return raw.strip() or None


def _existing_results(path: Path, model: str) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        instance_id = str(row.get("instance_id") or "").strip()
        if not instance_id:
            raise ValueError(f"Existing diagnostic row lacks instance_id: {path}")
        if row.get("model") != model or row.get("diagnostic_version") != DIAGNOSTIC_VERSION:
            continue
        parse_repository_diagnostic(json.dumps(row))
        rows[instance_id] = row
    return rows


def _write_selected_results(
    output: Path,
    tasks: list[SWEBenchTask],
    completed: dict[str, dict[str, Any]],
) -> None:
    rows = [completed[task.instance_id] for task in tasks if task.instance_id in completed]
    write_jsonl(output, rows)


def _same_repository(predicted: str | None, expected: str) -> bool:
    return predicted is not None and predicted.casefold() == expected.casefold()


def _repository_named_in_issue(repository: str, problem_statement: str) -> bool:
    owner, name = repository.casefold().split("/", 1)
    issue = problem_statement.casefold().replace("\\", "/")
    if repository.casefold() in issue or f"github.com/{owner}/{name}" in issue:
        return True
    return re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", issue) is not None
