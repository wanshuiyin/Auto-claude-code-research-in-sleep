#!/usr/bin/env python3
"""Helpers for loading and validating the GMU implementation scaffold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"


def _load_json(name: str) -> Any:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_all() -> Dict[str, Any]:
    return {
        "setup": _load_json("setup.json"),
        "methods": _load_json("methods.json"),
        "shift_families": _load_json("shift_families.json"),
        "forget_sets": _load_json("forget_sets.json"),
        "run_matrix": _load_json("run_matrix.json"),
    }


def get_run(run_id: str) -> Dict[str, Any]:
    specs = load_all()
    for run in specs["run_matrix"]:
        if run["run_id"] == run_id:
            return run
    raise KeyError(f"Unknown run_id: {run_id}")


def validate_configs() -> List[str]:
    specs = load_all()
    issues: List[str] = []
    seen_run_ids = set()

    for run in specs["run_matrix"]:
        run_id = run["run_id"]
        if run_id in seen_run_ids:
            issues.append(f"duplicate run id: {run_id}")
        seen_run_ids.add(run_id)

        if run["kind"] == "vision":
            method = run.get("method")
            if method not in specs["methods"]:
                issues.append(f"{run_id}: unknown method {method}")

            forget_set = run.get("forget_set")
            if forget_set not in specs["forget_sets"]:
                issues.append(f"{run_id}: unknown forget set {forget_set}")

            target_family = run.get("target_family")
            if target_family not in specs["shift_families"]:
                issues.append(f"{run_id}: unknown shift family {target_family}")

            if run.get("model") != specs["setup"]["primary_model"]["key"]:
                issues.append(f"{run_id}: expected primary model key")

            if run.get("dataset") != specs["setup"]["primary_dataset"]["key"]:
                issues.append(f"{run_id}: expected primary dataset key")

        if run["kind"] == "diagnostic":
            target_families = run.get("target_family", [])
            if not isinstance(target_families, list):
                issues.append(f"{run_id}: diagnostic run should use a list of shift families")
            else:
                for family in target_families:
                    if family not in specs["shift_families"]:
                        issues.append(f"{run_id}: unknown diagnostic shift family {family}")

        if run["kind"] == "synthetic":
            if run.get("dataset") != "synthetic_linear":
                issues.append(f"{run_id}: synthetic run must use synthetic_linear dataset")

    return issues


def artifact_dir(run_id: str) -> Path:
    return ROOT / "artifacts" / run_id
