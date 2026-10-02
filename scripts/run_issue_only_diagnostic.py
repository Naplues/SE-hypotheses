#!/usr/bin/env python3
"""Identify each task's source repository from only its issue description."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.issue_only import (
    OpenAICompatibleClient,
    api_key_from_environment,
    default_base_url,
    run_issue_only_diagnostic,
)

DEFAULT_INPUT = Path("data/swebench_verified_test.jsonl")
DEFAULT_TASKS = Path("data/heuristic-hypotheses")
DEFAULT_OUTPUT = Path("data/issue-only-diagnostics/glm-4.6-repository-origin.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="SWE-bench JSONL")
    parser.add_argument(
        "--tasks",
        type=Path,
        default=DEFAULT_TASKS,
        help="Constructed task directory selecting the 272 instance IDs",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSONL")
    parser.add_argument("--model", default="glm-4.6", help="Model name sent to the API")
    parser.add_argument("--base-url", default=default_base_url(), help="OpenAI-compatible API URL")
    parser.add_argument(
        "--api-key-env",
        default="GLM_API_KEY",
        help="Environment variable containing the API key",
    )
    parser.add_argument("--workers", type=int, default=4, help="Concurrent API requests")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--limit", type=int, help="Diagnose the first N selected tasks")
    selection.add_argument("--sample", type=int, help="Diagnose a random sample of N tasks")
    parser.add_argument("--seed", type=int, default=20260929, help="Random sample seed")
    parser.add_argument("--retries", type=int, default=2, help="Retries after a failed response")
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout in seconds")
    parser.add_argument("--max-tokens", type=int, default=2000, help="Maximum response tokens")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--force", action="store_true", help="Replace existing results")
    args = parser.parse_args()

    client = OpenAICompatibleClient(
        model=args.model,
        api_key=api_key_from_environment(args.api_key_env),
        base_url=args.base_url,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    summary = run_issue_only_diagnostic(
        args.input,
        args.tasks,
        args.output,
        model=args.model,
        complete=client.complete,
        workers=args.workers,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        force=args.force,
        retries=args.retries,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
