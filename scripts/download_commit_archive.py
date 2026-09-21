#!/usr/bin/env python3
"""Download exact source snapshots for selected SWE-bench tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rfm.io import dump_json
from rfm.snapshots import download_commit_snapshot, load_snapshot_spec, load_snapshot_specs

DEFAULT_INPUT = Path("data/swebench_verified_test.jsonl")
DEFAULT_CACHE = Path("data/repo-archives")
DEFAULT_OUTPUT = Path("data/repository-snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--instance-id", help="Download one SWE-bench task")
    selection.add_argument("--all", action="store_true", help="Download every task")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="SWE-bench JSONL")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="Archive cache")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Snapshot root")
    parser.add_argument("--force", action="store_true", help="Replace cached archive and snapshot")
    args = parser.parse_args()

    if args.instance_id:
        spec = load_snapshot_spec(args.input, args.instance_id)
        result = download_commit_snapshot(
            spec,
            args.cache_dir,
            args.output,
            force=args.force,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    specs = load_snapshot_specs(args.input)
    completed: list[str] = []
    skipped: list[str] = []
    failures: list[dict[str, str]] = []
    for index, spec in enumerate(specs, start=1):
        print(f"[{index}/{len(specs)}] {spec.instance_id}", file=sys.stderr, flush=True)
        try:
            result = download_commit_snapshot(
                spec,
                args.cache_dir,
                args.output,
                force=args.force,
            )
            target = completed if result["status"] == "completed" else skipped
            target.append(spec.instance_id)
        except (OSError, ValueError) as exc:
            failures.append({"instance_id": spec.instance_id, "error": str(exc)})
            print(f"  failed: {exc}", file=sys.stderr, flush=True)

    summary = {
        "selected": len(specs),
        "completed": completed,
        "skipped": skipped,
        "failures": failures,
        "cache_dir": str(args.cache_dir.resolve()),
        "output_dir": str(args.output.resolve()),
    }
    dump_json(args.output / "download-summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
