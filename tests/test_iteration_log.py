"""Tests for iteration_log.py — stall detection → forced structural pivot (B)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import iteration_log as il  # noqa: E402


class TestIterationLog(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.run = "demo-run"

    def _path(self):
        return Path(self.root) / ".aris" / "runs" / f"{self.run}.iterations.jsonl"

    def test_findings_reset_stale(self):
        r = il.note(self.root, self.run, "lit", 3)
        self.assertEqual(r["stale_count"], 0)
        self.assertEqual(r["pivot"], "none")

    def test_stall_ladder(self):
        self.assertEqual(il.note(self.root, self.run, "p", 0)["pivot"], "none")        # stale 1
        r2 = il.note(self.root, self.run, "p", 0)                                       # stale 2
        self.assertEqual((r2["stale_count"], r2["pivot"]), (2, "structural"))
        r3 = il.note(self.root, self.run, "p", 0)                                       # stale 3
        self.assertEqual(r3["pivot"], "structural")
        r4 = il.note(self.root, self.run, "p", 0)                                       # stale 4
        self.assertEqual((r4["stale_count"], r4["pivot"]), (4, "human"))

    def test_findings_break_the_stall(self):
        il.note(self.root, self.run, "p", 0)
        il.note(self.root, self.run, "p", 0)        # stale 2 → structural
        r = il.note(self.root, self.run, "p", 5)    # progress resets
        self.assertEqual((r["stale_count"], r["pivot"]), (0, "none"))

    def test_sidecar_path_and_append_only(self):
        il.note(self.root, self.run, "p", 1)
        il.note(self.root, self.run, "p", 0)
        p = self._path()
        self.assertTrue(p.is_file())
        lines = [l for l in p.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)  # append-only: one line per note
        self.assertEqual(json.loads(lines[0])["new_findings"], 1)

    def test_does_not_touch_run_state(self):
        # B must not write run_state.py's <run_id>.json — only the .iterations.jsonl sidecar
        il.note(self.root, self.run, "p", 0)
        self.assertFalse((Path(self.root) / ".aris" / "runs" / f"{self.run}.json").exists())

    def test_tolerates_garbled_line(self):
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"stale_count": 1}\nGARBAGE NOT JSON\n')
        r = il.note(self.root, self.run, "p", 0)   # last good stale was 1 → now 2
        self.assertEqual(r["stale_count"], 2)

    def test_show(self):
        il.note(self.root, self.run, "p", 2)
        self.assertIn('"new_findings": 2', il.show(self.root, self.run))
        self.assertEqual(il.show(self.root, "no-such-run"), "")

    def test_invalid_run_id_rejected(self):
        # path-escape / separators must be rejected like run_state.py
        for bad in ("../escape", "a/b", "..", ".", "a b", "a;rm -rf x", "", "x/../y"):
            with self.assertRaises(ValueError):
                il.note(self.root, bad, "p", 0)

    def test_direction_field_recorded(self):
        il.note(self.root, self.run, "p", 0, direction="reframe as graph problem")
        line = [l for l in self._path().read_text().splitlines() if l.strip()][-1]
        self.assertEqual(json.loads(line)["direction"], "reframe as graph problem")
        # omitted direction → field absent (not null)
        il.note(self.root, self.run, "p", 1)
        last = json.loads([l for l in self._path().read_text().splitlines() if l.strip()][-1])
        self.assertNotIn("direction", last)


if __name__ == "__main__":
    unittest.main()
