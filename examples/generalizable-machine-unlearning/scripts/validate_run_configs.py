#!/usr/bin/env python3
"""Validate the GMU experiment scaffold configs."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.experiment_config import validate_configs


def main() -> int:
    issues = validate_configs()
    if issues:
        print("Config validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Config validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
