#!/usr/bin/env python3
"""Analyze completed agent results and trajectories for RQ1-RQ3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.analysis import analyze_results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    labels = parser.add_mutually_exclusive_group(required=True)
    labels.add_argument("--annotations", type=Path)
    labels.add_argument(
        "--use-proxies",
        action="store_true",
        help="Pipeline checks only; do not use proxy labels for paper claims",
    )
    args = parser.parse_args()
    report = analyze_results(
        args.tasks,
        args.runs,
        args.output,
        annotations_path=args.annotations,
        use_proxies=args.use_proxies,
        seed=args.seed,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
