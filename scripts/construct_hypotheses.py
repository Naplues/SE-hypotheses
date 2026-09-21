#!/usr/bin/env python3
"""Construct ground truth and misleading hypotheses for SWE-bench tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.construction import construct_hypotheses

DEFAULT_INPUT = Path("data/swebench_verified_test.jsonl")
DEFAULT_WORKSPACE = Path("data/construction-workspace")
DEFAULT_OUTPUT = Path("data/constructed-hypotheses")
DEFAULT_SNAPSHOTS = Path("data/repository-snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model", required=True, help="Pinned Claude model identifier")
    parser.add_argument("--input", default=DEFAULT_INPUT, type=Path, help="SWE-bench JSONL")
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE,
        type=Path,
        help="Private repository and prompt workspace",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help="Constructed task output directory",
    )
    parser.add_argument(
        "--snapshots",
        default=DEFAULT_SNAPSHOTS,
        type=Path,
        help="Downloaded commit snapshot root",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--all",
        action="store_true",
        help="Process every task in the SWE-bench JSONL",
    )
    selection.add_argument(
        "--instance-id",
        action="append",
        help="Instance to process; repeat to select multiple instances",
    )
    selection.add_argument(
        "--instance-ids-file",
        type=Path,
        help="Text file containing one instance ID per line",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N selected tasks")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent Claude Code subprocesses",
    )
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        help="Maximum cost for each of the two Claude calls per task",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing task outputs")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry only tasks recorded as failed while preserving completed outputs",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failure")
    args = parser.parse_args()

    summary = construct_hypotheses(
        args.input,
        args.workspace,
        args.output,
        model=args.model,
        snapshots_dir=args.snapshots,
        instance_ids=[] if args.all else args.instance_id,
        instance_ids_file=args.instance_ids_file,
        limit=args.limit,
        max_budget_usd=args.max_budget_usd,
        workers=args.workers,
        retry_failed=args.retry_failed,
        force=args.force,
        fail_fast=args.fail_fast,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
