#!/usr/bin/env python3
"""Starter CLI for tracker-aligned vision experiments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.experiment_config import artifact_dir, get_run, load_all


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a vision run from the GMU run matrix.")
    parser.add_argument("--run-id", required=True, help="Run ID such as R001 or R004.")
    parser.add_argument("--seed", type=int, default=0, help="Seed to stamp into the stub metadata.")
    parser.add_argument(
        "--write-stub",
        action="store_true",
        help="Create an artifact directory with run metadata and a TODO note.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = load_all()
    run = get_run(args.run_id)
    if run["kind"] != "vision":
        print(f"{args.run_id} is not a vision run.")
        return 1

    method = specs["methods"][run["method"]]
    shift = specs["shift_families"][run["target_family"]]
    forget_set = specs["forget_sets"][run["forget_set"]]

    print(f"Run: {run['run_id']} ({run['milestone']})")
    print(f"Method: {method['display_name']}")
    print(f"Model: {specs['setup']['primary_model']['display_name']}")
    print(f"Dataset: {specs['setup']['primary_dataset']['display_name']}")
    print(f"Source domain: {run['source_domain']}")
    print(f"Target family: {shift['display_name']}")
    print(f"Forget set: {forget_set['display_name']}")
    print(f"Metrics: retain_acc, forget_gap, ood_unlearning_gap")

    if not args.write_stub:
        return 0

    out_dir = artifact_dir(run["run_id"])
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "run": run,
        "seed": args.seed,
        "method_notes": method["notes"],
        "shift": shift,
        "forget_set": forget_set,
    }

    (out_dir / "run_spec.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "TODO.md").write_text(
        "\n".join(
            [
                f"# {run['run_id']} TODO",
                "",
                "1. Wire the real dataset loader and corruption pipeline.",
                "2. Implement the baseline method.",
                "3. Save metrics to metrics.json.",
                "4. Record tracker status changes after the run completes.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote stub artifacts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
