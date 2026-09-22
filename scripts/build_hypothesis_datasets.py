#!/usr/bin/env python3
"""Build four SWE-bench JSONL variants from generated hypothesis prompts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rfm.datasets import build_hypothesis_datasets

DEFAULT_SOURCE = Path("data/swebench_verified_test.jsonl")
DEFAULT_PROMPTS = Path("data/hypothesis-prompts")
DEFAULT_OUTPUT = Path("data/hypothesis-datasets")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = build_hypothesis_datasets(args.source, args.prompts, args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
