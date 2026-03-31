#!/usr/bin/env python3
"""Print a concise summary of the run matrix."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.experiment_config import load_all


def main() -> int:
    specs = load_all()
    methods = specs["methods"]
    shifts = specs["shift_families"]

    print(f"{'Run':<5} {'Kind':<10} {'Method / Target':<42} {'Forget':<12} {'Priority':<6}")
    for run in specs["run_matrix"]:
        method = run["method"]
        if method in methods:
            left = methods[method]["display_name"]
        else:
            left = run["kind"]

        target = run["target_family"]
        if isinstance(target, list):
            target_text = ",".join(target)
        else:
            target_text = shifts[target]["display_name"] if target in shifts else str(target)

        summary = f"{left} @ {target_text}"
        print(
            f"{run['run_id']:<5} {run['kind']:<10} {summary[:42]:<42} "
            f"{str(run['forget_set']):<12} {run['priority']:<6}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
