"""Tests for the watchdog `loop` task type (A2 — loop-liveness, detect-only).

Covers: conditional register (loop vs session-backed), mtime-primary liveness
(OK/STALE), startup grace (PENDING→MISSING), COMPLETED detection (JSON status +
run_state phases), unparseable-JSON safety, and the detect-only invariant
(check_loop performs no subprocess/spawn).
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import watchdog  # noqa: E402


def _mk(base):
    status = Path(base) / "status"
    status.mkdir(parents=True, exist_ok=True)
    return status


class TestLoopRegister(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_register_loop_requires_fields(self):
        # missing stale_after_seconds → exits
        with self.assertRaises(SystemExit):
            watchdog.register_task(self.tmp, json.dumps(
                {"name": "r1", "type": "loop", "state_file": "/x/y.json"}))

    def test_register_loop_normalizes_and_stamps(self):
        sf = Path(self.tmp) / "rel_state.json"
        sf.write_text("{}")
        watchdog.register_task(self.tmp, json.dumps(
            {"name": "loop1", "type": "loop", "state_file": str(sf), "stale_after_seconds": 100}))
        tasks = json.loads((Path(self.tmp) / "tasks.json").read_text())
        t = next(x for x in tasks if x["name"] == "loop1")
        self.assertEqual(t["type"], "loop")
        self.assertTrue(os.path.isabs(t["state_file"]))
        self.assertIn("registered_epoch", t)
        self.assertEqual(t["stale_after_seconds"], 100)

    def test_training_still_requires_session_backcompat(self):
        # training without session → exits (back-compat with conditional-required)
        with self.assertRaises(SystemExit):
            watchdog.register_task(self.tmp, json.dumps({"name": "t1", "type": "training"}))
        # with session → fine
        watchdog.register_task(self.tmp, json.dumps(
            {"name": "t1", "type": "training", "session": "t1"}))
        tasks = json.loads((Path(self.tmp) / "tasks.json").read_text())
        self.assertEqual(tasks[0]["type"], "training")
        self.assertEqual(tasks[0]["session_type"], "screen")


class TestCheckLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.status = _mk(self.tmp)

    def _read(self, name):
        return json.loads((self.status / f"{name}.json").read_text())

    def _alerts(self):
        a = Path(self.tmp) / "alerts.log"
        return a.read_text() if a.exists() else ""

    def test_fresh_mtime_ok(self):
        sf = Path(self.tmp) / "s.json"; sf.write_text('{"updated":"x"}')
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": time.time()}, self.status)
        self.assertEqual(self._read("L")["status"], "OK")
        self.assertNotIn("L:", self._alerts())

    def test_old_mtime_stale(self):
        sf = Path(self.tmp) / "s.json"; sf.write_text('{"updated":"x"}')
        old = time.time() - 500
        os.utime(sf, (old, old))
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": time.time() - 600}, self.status)
        self.assertEqual(self._read("L")["status"], "STALE")
        self.assertIn("STALE", self._alerts())

    def test_absent_within_grace_pending(self):
        sf = Path(self.tmp) / "nope.json"
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": time.time()}, self.status)
        self.assertEqual(self._read("L")["status"], "PENDING")
        self.assertEqual(self._alerts(), "")  # PENDING is not an anomaly

    def test_absent_past_grace_missing(self):
        sf = Path(self.tmp) / "nope.json"
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": time.time() - 500}, self.status)
        self.assertEqual(self._read("L")["status"], "MISSING")
        self.assertIn("MISSING", self._alerts())

    def test_missing_epoch_failsafe_missing_not_pending(self):
        # codex round-2 bug fix: absent registered_epoch must NOT yield infinite PENDING
        sf = Path(self.tmp) / "nope.json"
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100}, self.status)
        self.assertEqual(self._read("L")["status"], "MISSING")

    def test_completed_status_suppresses_stale(self):
        sf = Path(self.tmp) / "s.json"; sf.write_text('{"status":"completed"}')
        old = time.time() - 9999
        os.utime(sf, (old, old))
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": old}, self.status)
        self.assertEqual(self._read("L")["status"], "COMPLETED")

    def test_runstate_all_phases_accepted_completed(self):
        sf = Path(self.tmp) / "s.json"
        sf.write_text(json.dumps({"phases": [{"status": "accepted"}, {"status": "skipped"}]}))
        old = time.time() - 9999
        os.utime(sf, (old, old))
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": old}, self.status)
        self.assertEqual(self._read("L")["status"], "COMPLETED")

    def test_unparseable_json_fresh_is_ok_not_stale(self):
        sf = Path(self.tmp) / "s.json"; sf.write_text("not json {{{")
        watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                             "stale_after_seconds": 100, "registered_epoch": time.time()}, self.status)
        self.assertEqual(self._read("L")["status"], "OK")  # bad JSON never STALE on its own

    def test_detect_only_no_subprocess(self):
        # check_loop must never shell out; break subprocess.run and assert it still works.
        sf = Path(self.tmp) / "s.json"; sf.write_text("{}")
        orig = watchdog.subprocess.run
        watchdog.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("check_loop shelled out"))
        try:
            watchdog.check_loop({"name": "L", "type": "loop", "state_file": str(sf),
                                 "stale_after_seconds": 100, "registered_epoch": time.time()}, self.status)
            self.assertEqual(self._read("L")["status"], "OK")
        finally:
            watchdog.subprocess.run = orig


if __name__ == "__main__":
    unittest.main()
