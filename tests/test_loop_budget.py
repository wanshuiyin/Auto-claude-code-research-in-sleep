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

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env={**os.environ},
        )

    def test_record_creates_state_dir_and_file(self):
        out = self._run("record", "--side", "claude", "--skill", "auto-review-loop")
        self.assertEqual(out.returncode, 0, out.stderr)
        state_file = self.tmp / "loop-usage.jsonl"
        self.assertTrue(state_file.exists())
        lines = state_file.read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["side"], "claude")
        self.assertEqual(rec["skill"], "auto-review-loop")
        # ts must parse as ISO-8601 UTC with Z suffix.
        self.assertTrue(rec["ts"].endswith("Z"))
        datetime.strptime(rec["ts"], "%Y-%m-%dT%H:%M:%SZ")

    def test_record_appends_subsequent_calls(self):
        self._run("record", "--side", "claude", "--skill", "auto-review-loop")
        self._run("record", "--side", "codex", "--skill", "auto-review-loop-llm")
        lines = (self.tmp / "loop-usage.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["side"], "claude")
        self.assertEqual(json.loads(lines[1])["side"], "codex")

    def test_record_rejects_unknown_side(self):
        out = self._run("record", "--side", "bogus", "--skill", "x")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("bogus", out.stderr)

    def _write_records(self, recs):
        """Write a list of dicts to the state file directly."""
        path = self.tmp / "loop-usage.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    @staticmethod
    def _iso(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_check_empty_state_is_under_budget(self):
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stderr)

    def test_check_exits_2_when_at_cap(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "3"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("STOP", out.stderr)

    def test_check_under_cap_when_one_short(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "3"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_check_only_counts_matching_side(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "2"
        os.environ["CODEX_LOOP_MAX_ITERATIONS"] = "2"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "x"},
        ])
        # Claude side: 1/2, ok. Codex side: 2/2, over.
        self.assertEqual(self._run("check", "--side", "claude").returncode, 0)
        self.assertEqual(self._run("check", "--side", "codex").returncode, 2)

    def test_check_ignores_records_older_than_window(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "2"
        os.environ["CLAUDE_LOOP_WINDOW_HOURS"] = "5"
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=6)
        self._write_records([
            {"ts": self._iso(old), "side": "claude", "skill": "x"},
            {"ts": self._iso(old), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        # Only 1 record falls within the 5h window; cap=2 → under.
        self.assertEqual(self._run("check", "--side", "claude").returncode, 0)

    def test_check_warns_at_threshold(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "5"
        os.environ["CLAUDE_LOOP_WARN_AT"] = "0.8"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"} for _ in range(4)
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("warning", out.stderr.lower())
        self.assertIn("80%", out.stderr)

    def test_check_reports_reset_time_when_over_cap(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "1"
        os.environ["CLAUDE_LOOP_WINDOW_HOURS"] = "5"
        ref = datetime.now(timezone.utc) - timedelta(hours=1)
        self._write_records([{"ts": self._iso(ref), "side": "claude", "skill": "x"}])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 2, out.stderr)
        # Reset should be approx ref + 5h, i.e. ~4 hours from now.
        # We just assert the message includes a "Next slot frees at" timestamp.
        self.assertIn("Next slot frees at", out.stderr)

    def test_check_skips_unparseable_lines_without_crashing(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "5"
        now = datetime.now(timezone.utc)
        path = self.tmp / "loop-usage.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write("this is not json\n")
            fh.write(json.dumps({"ts": self._iso(now), "side": "claude", "skill": "x"}) + "\n")
            fh.write("\n")  # blank line
            fh.write('{"ts": "garbage", "side": "claude"}\n')  # bad ts
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        # Should count only the one valid line.
        self.assertIn("1/5", out.stderr)

    def test_check_handles_missing_state_file(self):
        # Setup left ARIS_USAGE_DIR pointing at a freshly-made empty dir.
        out = self._run("check", "--side", "codex")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stderr)

    def test_status_prints_both_sides_and_exits_zero(self):
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "y"},
            {"ts": self._iso(now), "side": "codex", "skill": "y"},
        ])
        out = self._run("status")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("claude", out.stdout)
        self.assertIn("codex", out.stdout)
        self.assertIn("1/", out.stdout)
        self.assertIn("2/", out.stdout)

    def test_status_with_no_state_shows_zero(self):
        out = self._run("status")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stdout)

    def test_aris_usage_dir_override_isolated_per_test(self):
        # setUp pointed ARIS_USAGE_DIR at self.tmp; nothing should leak from $HOME.
        self._run("record", "--side", "claude", "--skill", "x")
        self.assertTrue((self.tmp / "loop-usage.jsonl").exists())
        # And ~/.aris/usage/loop-usage.jsonl should NOT have been touched by this test.


if __name__ == "__main__":
    unittest.main()
