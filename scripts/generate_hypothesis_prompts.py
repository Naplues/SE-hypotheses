#!/usr/bin/env python3
"""Generate hypothesis prompt files and four derived SWE-bench datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.datasets import build_hypothesis_datasets
from rfm.prompts import generate_hypothesis_prompts

DEFAULT_INPUT = Path("data/heuristic-hypotheses")
DEFAULT_OUTPUT = Path("data/heuristic-prompts")
DEFAULT_SOURCE = Path("data/swebench_verified_test.jsonl")
DEFAULT_DATASETS_OUTPUT = Path("data/heuristic-datasets")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--datasets-output", type=Path, default=DEFAULT_DATASETS_OUTPUT)
    args = parser.parse_args()

    prompt_summary = generate_hypothesis_prompts(args.input, args.output)
    dataset_summary = build_hypothesis_datasets(args.source, args.output, args.datasets_output)
    summary = {
        "prompts": prompt_summary,
        "datasets": dataset_summary["datasets"],
        "datasets_output_dir": dataset_summary["output_dir"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
