#!/usr/bin/env python3
"""Starter CLI for FSS/RFE/LR extraction and downstream diagnostic studies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.experiment_config import artifact_dir, get_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a diagnostic run from the GMU run matrix.")
    parser.add_argument("--run-id", required=True, help="Run ID such as R008, R010, or R011.")
    parser.add_argument("--write-stub", action="store_true", help="Create artifact skeleton files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run = get_run(args.run_id)
    if run["kind"] not in {"diagnostic", "policy"}:
        print(f"{args.run_id} is not a diagnostic/policy run.")
        return 1

    print(f"Run: {run['run_id']} ({run['milestone']})")
    print(f"Kind: {run['kind']}")
    print(f"Targets: {', '.join(run['target_family'])}")
    print("Primary outputs: FSS, RFE, LR, predictor comparison tables, choose/abstain analysis")

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
                "1. Load completed source-target results.",
                "2. Extract interface-layer summaries.",
                "3. Compute FSS, RFE, and LR.",
                "4. Save predictor tables and plots.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote stub artifacts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
