#!/usr/bin/env python3
"""Starter CLI for the controlled synthetic overlap sweep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.experiment_config import artifact_dir, get_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the synthetic theory-validation sweep.")
    parser.add_argument("--run-id", default="R009", help="Synthetic run ID. Defaults to R009.")
    parser.add_argument("--write-stub", action="store_true", help="Create artifact skeleton files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run = get_run(args.run_id)
    if run["kind"] != "synthetic":
        print(f"{args.run_id} is not a synthetic run.")
        return 1

    print(f"Run: {run['run_id']} ({run['milestone']})")
    print("Goal: validate the monotonic FSS/RFE relationship in a controlled linear regime.")
    print("Suggested grid: overlap drift x retain-forget entanglement x local residual strength")

    if not args.write_stub:
        return 0

    out_dir = artifact_dir(run["run_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run_spec.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    (out_dir / "TODO.md").write_text(
        "\n".join(
            [
                f"# {run['run_id']} TODO",
                "",
                "1. Build the synthetic linear data generator.",
                "2. Sweep overlap and entanglement parameters.",
                "3. Measure OOD gap, FSS, RFE, and LR.",
                "4. Save the phase diagram inputs.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote stub artifacts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
