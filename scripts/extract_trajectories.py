#!/usr/bin/env python3
"""Extract metrics and normalized events from mini-swe-agent *.traj.json files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.models import Condition
from rfm.trajectory_extraction import extract_trajectories


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="One trajectory file or one mini_run directory")
    inputs.add_argument(
        "--input-root",
        type=Path,
        help="Root containing <configuration>/mini_run directories",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output root; each condition is written to its own subdirectory",
    )
    parser.add_argument(
        "--condition",
        choices=[condition.value for condition in Condition],
        help="Condition shared by all selected trajectories",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        help="Optional SWE-bench JSONL used to compute developer-patch overlap",
    )
    parser.add_argument("--configuration-id", help="Configuration name for --input mode")
    parser.add_argument("--agent-id", help="Pinned agent identifier used in normalized runs")
    parser.add_argument("--model-id", help="Pinned model identifier used in normalized runs")
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--manifest", type=Path, help="Optional experiment manifest for run IDs")
    parser.add_argument(
        "--evaluations",
        type=Path,
        help=(
            "Optional result root containing SWE-bench report.json files, or normalized "
            "JSON/JSONL evaluator results"
        ),
    )
    parser.add_argument(
        "--normalized-runs",
        type=Path,
        help="Optional base root for condition/runs directories; defaults to OUTPUT",
    )
    args = parser.parse_args()
    if args.input_root and args.condition:
        parser.error("--condition is inferred from configuration names with --input-root")
    if args.input_root and args.configuration_id:
        parser.error("--configuration-id cannot be used with --input-root")
    summary = extract_trajectories(
        args.input or args.input_root,
        args.output,
        condition=args.condition,
        tasks_path=args.tasks,
        auto_configurations=args.input_root is not None,
        configuration_id=args.configuration_id,
        agent_id=args.agent_id,
        model_id=args.model_id,
        repetition=args.repetition,
        manifest_path=args.manifest,
        evaluations_path=args.evaluations,
        normalized_runs_dir=args.normalized_runs,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
