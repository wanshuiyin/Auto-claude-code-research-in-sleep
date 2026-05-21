#!/usr/bin/env python3
"""Tests for tools/loop_budget.py — iteration-budget guard for auto-review-loop skills."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "loop_budget.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("loop_budget", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LoopBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="loop-budget-"))
        os.environ["ARIS_USAGE_DIR"] = str(self.tmp)
        # Reset budget env to defaults known by tests.
        for k in (
            "CLAUDE_LOOP_MAX_ITERATIONS", "CLAUDE_LOOP_WINDOW_HOURS",
            "CODEX_LOOP_MAX_ITERATIONS", "CODEX_LOOP_WINDOW_HOURS",
            "CLAUDE_LOOP_WARN_AT",
        ):
            os.environ.pop(k, None)
        self.mod = _load_module()

    def tearDown(self):
        os.environ.pop("ARIS_USAGE_DIR", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_script_exists_and_is_python3(self):
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} must exist")
        # Smoke test: import succeeds and module exposes `usage_path`.
        self.assertTrue(hasattr(self.mod, "usage_path"))


if __name__ == "__main__":
    unittest.main()
