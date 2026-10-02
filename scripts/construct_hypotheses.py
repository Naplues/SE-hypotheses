#!/usr/bin/env python3
"""Construct ground truth and misleading hypotheses for SWE-bench tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.heuristics import construct_heuristic_hypotheses

DEFAULT_INPUT = Path("data/swebench_verified_test.jsonl")
DEFAULT_HEURISTIC_OUTPUT = Path("data/heuristic-hypotheses")
DEFAULT_SNAPSHOTS = Path("data/repository-snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, type=Path, help="SWE-bench JSONL")
    parser.add_argument(
        "--output",
        default=DEFAULT_HEURISTIC_OUTPUT,
        type=Path,
        help="Output directory",
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
        help="Number of concurrent task workers",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing task outputs")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failure")
    args = parser.parse_args()

    selection_args = {
        "instance_ids": [] if args.all else args.instance_id,
        "instance_ids_file": args.instance_ids_file,
        "limit": args.limit,
    }
    summary = construct_heuristic_hypotheses(
        args.input,
        args.output,
        snapshots_dir=args.snapshots,
        workers=args.workers,
        force=args.force,
        fail_fast=args.fail_fast,
        **selection_args,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
