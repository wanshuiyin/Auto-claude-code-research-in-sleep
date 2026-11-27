#!/usr/bin/env python3
"""Unit tests for tools/watchdog.py.

Covers task registration/unregistration, session liveness checks,
GPU/download monitoring logic, status writing, and summary generation
— all without spawning real processes or touching the filesystem outside
of a temporary directory.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make the tools/ directory importable as a module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import watchdog


class TestGetPaths(unittest.TestCase):
    """Test that get_paths returns correct sub-paths."""

    def test_paths_structure(self):
        base = "/tmp/aris-test"
        paths = watchdog.get_paths(base)
        # Compare resolved Path objects so the test passes on both Unix and Windows
        self.assertEqual(paths["base"], Path(base))
        self.assertTrue(str(paths["pid"]).endswith("watchdog.pid"))
        self.assertTrue(str(paths["tasks"]).endswith("tasks.json"))
        # alerts.log path ends differ by OS separator — use suffix check on the name only
        self.assertEqual(paths["alerts"].name, "alerts.log")
        self.assertEqual(paths["status"].name, "status")


class TestRegisterTask(unittest.TestCase):
    """Test task registration via register_task()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_register_training_task(self):
        task = json.dumps({
            "name": "exp01",
            "type": "training",
            "session": "exp01",
            "session_type": "screen",
            "gpus": [0, 1],
        })
        watchdog.register_task(self.tmpdir, task)

        tasks_path = Path(self.tmpdir) / "tasks.json"
        self.assertTrue(tasks_path.exists())
        tasks = json.loads(tasks_path.read_text())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "exp01")
        self.assertEqual(tasks[0]["type"], "training")
        self.assertIn("registered_at", tasks[0])

    def test_register_download_task(self):
        task = json.dumps({
            "name": "dl01",
            "type": "download",
            "session": "dl01",
            "session_type": "tmux",
            "target_path": "/data/imagenet",
        })
        watchdog.register_task(self.tmpdir, task)

        tasks_path = Path(self.tmpdir) / "tasks.json"
        tasks = json.loads(tasks_path.read_text())
        self.assertEqual(tasks[0]["type"], "download")
        self.assertEqual(tasks[0]["target_path"], "/data/imagenet")

    def test_register_defaults_session_type_to_screen(self):
        task = json.dumps({
            "name": "exp02",
            "type": "training",
            "session": "exp02",
        })
        watchdog.register_task(self.tmpdir, task)

        tasks = json.loads((Path(self.tmpdir) / "tasks.json").read_text())
        self.assertEqual(tasks[0]["session_type"], "screen")

    def test_register_deduplicates_by_name(self):
        for i in range(3):
            task = json.dumps({
                "name": "exp01",
                "type": "training",
                "session": f"session_{i}",
            })
            watchdog.register_task(self.tmpdir, task)

        tasks = json.loads((Path(self.tmpdir) / "tasks.json").read_text())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["session"], "session_2")

    def test_register_missing_required_field_exits(self):
        task = json.dumps({"name": "bad", "type": "training"})  # missing 'session'
        with self.assertRaises(SystemExit):
            watchdog.register_task(self.tmpdir, task)

    def test_register_invalid_type_exits(self):
        task = json.dumps({"name": "bad", "type": "invalid", "session": "s"})
        with self.assertRaises(SystemExit):
            watchdog.register_task(self.tmpdir, task)

    def test_register_multiple_tasks(self):
        for name in ("a", "b", "c"):
            watchdog.register_task(
                self.tmpdir,
                json.dumps({"name": name, "type": "training", "session": name}),
            )
        tasks = json.loads((Path(self.tmpdir) / "tasks.json").read_text())
        self.assertEqual(len(tasks), 3)
        names = {t["name"] for t in tasks}
        self.assertEqual(names, {"a", "b", "c"})


class TestUnregisterTask(unittest.TestCase):
    """Test task removal via unregister_task()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for name in ("keep", "remove"):
            watchdog.register_task(
                self.tmpdir,
                json.dumps({"name": name, "type": "training", "session": name}),
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unregister_removes_task(self):
        watchdog.unregister_task(self.tmpdir, "remove")
        tasks = json.loads((Path(self.tmpdir) / "tasks.json").read_text())
        names = [t["name"] for t in tasks]
        self.assertNotIn("remove", names)
        self.assertIn("keep", names)

    def test_unregister_removes_status_file(self):
        status_dir = Path(self.tmpdir) / "status"
        status_dir.mkdir(exist_ok=True)
        status_file = status_dir / "remove.json"
        status_file.write_text(json.dumps({"status": "OK"}))

        watchdog.unregister_task(self.tmpdir, "remove")
        self.assertFalse(status_file.exists())

    def test_unregister_nonexistent_task_is_safe(self):
        watchdog.unregister_task(self.tmpdir, "ghost")
        tasks = json.loads((Path(self.tmpdir) / "tasks.json").read_text())
        self.assertEqual(len(tasks), 2)

    def test_unregister_no_tasks_file_is_safe(self):
        import shutil
        shutil.rmtree(self.tmpdir)
        os.makedirs(self.tmpdir)
        watchdog.unregister_task(self.tmpdir, "anything")  # should not raise


def screen_list(*names):
    """`screen -list` output with one detached session per name."""
    rows = "".join(f"\t{100 + i}.{n}\t(11/27/26 07:46:22)\t(Detached)\n" for i, n in enumerate(names))
    return f"There is a screen on:\n{rows}{len(names)} Socket in /run/screen/S-user.\n"


class TestSessionAlive(unittest.TestCase):
    """Test session_alive() for tmux and screen."""

    @patch('watchdog.subprocess.run')
    def test_tmux_alive(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(watchdog.session_alive("my-session", "tmux"))
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("tmux", args)
        self.assertIn("has-session", args)

    @patch('watchdog.subprocess.run')
    def test_tmux_dead(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(watchdog.session_alive("dead-session", "tmux"))

    @patch('watchdog.subprocess.run')
    def test_screen_alive(self, mock_run):
        mock_run.return_value = MagicMock(stdout=screen_list("my-screen"), returncode=0)
        self.assertTrue(watchdog.session_alive("my-screen", "screen"))
        args = mock_run.call_args[0][0]
        self.assertIn("screen", args)

    @patch('watchdog.subprocess.run')
    def test_screen_dead(self, mock_run):
        mock_run.return_value = MagicMock(stdout="other-session\t(Detached)\n", returncode=0)
        self.assertFalse(watchdog.session_alive("my-screen", "screen"))

    @patch('watchdog.subprocess.run')
    def test_default_session_type_is_screen(self, mock_run):
        mock_run.return_value = MagicMock(stdout=screen_list("exp01"), returncode=0)
        result = watchdog.session_alive("exp01")
        self.assertTrue(result)
        # screen -list should have been called
        args = mock_run.call_args[0][0]
        self.assertIn("screen", args)

    @patch('watchdog.subprocess.run')
    def test_tmux_target_is_the_exact_session_name(self, mock_run):
        # Without the "=" prefix tmux resolves "exp1" to a live "exp10".
        mock_run.return_value = MagicMock(returncode=0)
        watchdog.session_alive("exp1", "tmux")
        self.assertEqual(mock_run.call_args[0][0][-2:], ["-t", "=exp1"])

    @patch('watchdog.subprocess.run')
    def test_screen_name_must_match_the_whole_session_name(self, mock_run):
        mock_run.return_value = MagicMock(stdout=screen_list("exp10"), returncode=0)
        self.assertFalse(watchdog.session_alive("exp1", "screen"))
        self.assertFalse(watchdog.session_alive("exp", "screen"))
        self.assertTrue(watchdog.session_alive("exp10", "screen"))


class TestSessionAliveTimeout(unittest.TestCase):
    """A wedged tmux server or screen must not freeze the monitoring loop."""

    def test_session_checks_are_bounded(self):
        for session_type in ("tmux", "screen"):
            with patch('watchdog.subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                watchdog.session_alive("exp01", session_type)
                self.assertIsNotNone(
                    mock_run.call_args.kwargs.get("timeout"),
                    f"{session_type} liveness check has no timeout",
                )

    def test_hung_session_check_is_reported_as_error(self):
        """One loop iteration: a timed-out check becomes an ERROR status and
        an alerts.log line instead of blocking the daemon."""
        import subprocess
        base = tempfile.mkdtemp()
        paths = watchdog.get_paths(base)
        paths["base"].mkdir(parents=True, exist_ok=True)
        paths["tasks"].write_text(json.dumps([
            {"name": "exp01", "type": "training", "session": "exp01", "session_type": "tmux"},
        ]))

        def run(cmd, **kwargs):
            if "timeout" not in kwargs:
                # Unbounded call on a wedged tmux server: would block forever.
                raise AssertionError("session check would hang: no timeout")
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        class StopLoop(Exception):
            pass

        with patch('watchdog.subprocess.run', side_effect=run), \
             patch('watchdog.time.sleep', side_effect=StopLoop), \
             patch('watchdog.signal.signal'):
            with self.assertRaises(StopLoop):
                watchdog.run_watchdog(base, 60)

        status = json.loads((paths["status"] / "exp01.json").read_text())
        self.assertEqual(status["status"], "ERROR")
        self.assertIn("timed out", status["msg"])
        self.assertIn("exp01: ERROR", paths["alerts"].read_text())


class TestGetGpuUtil(unittest.TestCase):
    """Test get_gpu_util() parsing."""

    @patch('watchdog.subprocess.run')
    def test_returns_list_of_ints(self, mock_run):
        mock_run.return_value = MagicMock(stdout="85\n92\n0\n78\n", returncode=0)
        result = watchdog.get_gpu_util()
        self.assertEqual(result, [85, 92, 0, 78])

    @patch('watchdog.subprocess.run')
    def test_nvidia_smi_missing_returns_empty(self, mock_run):
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
        result = watchdog.get_gpu_util()
        self.assertEqual(result, [])

    @patch('watchdog.subprocess.run')
    def test_timeout_returns_empty(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 10)
        result = watchdog.get_gpu_util()
        self.assertEqual(result, [])

    @patch('watchdog.subprocess.run')
    def test_single_gpu(self, mock_run):
        mock_run.return_value = MagicMock(stdout="42\n", returncode=0)
        self.assertEqual(watchdog.get_gpu_util(), [42])


class TestGetPathSize(unittest.TestCase):
    """Test get_path_size() using du."""

    @patch('watchdog.subprocess.run')
    def test_returns_size_in_bytes(self, mock_run):
        mock_run.return_value = MagicMock(stdout="1234567\t/path/to/file\n", returncode=0)
        self.assertEqual(watchdog.get_path_size("/path/to/file"), 1234567)

    @patch('watchdog.subprocess.run')
    def test_exception_returns_zero(self, mock_run):
        mock_run.side_effect = Exception("du failed")
        self.assertEqual(watchdog.get_path_size("/missing"), 0)

    @patch('watchdog.subprocess.run')
    def test_timeout_returns_zero(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("du", 30)
        self.assertEqual(watchdog.get_path_size("/slow"), 0)


class TestWriteStatus(unittest.TestCase):
    """Test write_status() and alert logging."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.status_dir = Path(self.tmpdir) / "status"
        self.status_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_json_status_file(self):
        status_file = self.status_dir / "exp01.json"
        data = {"status": "OK", "task": "exp01", "type": "training", "ts": "2026-01-01T00:00:00"}
        watchdog.write_status(status_file, data)
        saved = json.loads(status_file.read_text())
        self.assertEqual(saved["status"], "OK")
        self.assertEqual(saved["task"], "exp01")

    def test_anomaly_appends_to_alerts_log(self):
        for bad_status in ("DEAD", "STALLED", "IDLE", "ERROR"):
            status_file = self.status_dir / f"task_{bad_status}.json"
            data = {
                "status": bad_status,
                "task": f"task_{bad_status}",
                "msg": "something went wrong",
                "ts": "2026-01-01T00:00:00",
            }
            watchdog.write_status(status_file, data)

        alerts = (Path(self.tmpdir) / "alerts.log").read_text()
        for bad_status in ("DEAD", "STALLED", "IDLE", "ERROR"):
            self.assertIn(bad_status, alerts)

    def test_ok_status_does_not_write_alerts(self):
        status_file = self.status_dir / "ok_task.json"
        watchdog.write_status(status_file, {"status": "OK", "task": "ok_task", "ts": "t"})
        alerts_path = Path(self.tmpdir) / "alerts.log"
        self.assertFalse(alerts_path.exists())

    def test_returns_data(self):
        status_file = self.status_dir / "ret.json"
        data = {"status": "OK", "task": "ret", "ts": "t"}
        result = watchdog.write_status(status_file, data)
        self.assertEqual(result, data)


class TestWriteSummary(unittest.TestCase):
    """Test write_summary() aggregation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.status_dir = Path(self.tmpdir) / "status"
        self.status_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_task_status(self, name, data):
        (self.status_dir / f"{name}.json").write_text(json.dumps(data))

    def test_empty_status_dir_writes_no_tasks(self):
        summary = watchdog.write_summary(self.status_dir)
        self.assertEqual(summary, "no tasks")

    def test_ok_tasks_appear_in_summary(self):
        self._write_task_status("exp01", {
            "task": "exp01", "type": "training", "status": "OK", "gpu_util": [85]
        })
        summary = watchdog.write_summary(self.status_dir)
        self.assertIn("exp01", summary)
        self.assertIn("OK", summary)

    def test_slow_download_shows_speed(self):
        self._write_task_status("dl01", {
            "task": "dl01", "type": "download", "status": "SLOW", "speed_mbps": 0.5
        })
        summary = watchdog.write_summary(self.status_dir)
        self.assertIn("SLOW", summary)
        self.assertIn("speed=", summary)
        self.assertIn("0.5", summary)

    def test_idle_training_shows_gpu(self):
        self._write_task_status("exp02", {
            "task": "exp02", "type": "training", "status": "IDLE",
            "gpu_util": {"0": 1, "1": 0}
        })
        summary = watchdog.write_summary(self.status_dir)
        self.assertIn("IDLE", summary)
        self.assertIn("gpu=", summary)

    def test_dead_shows_message(self):
        self._write_task_status("dead_task", {
            "task": "dead_task", "type": "training", "status": "DEAD",
            "msg": "screen session gone"
        })
        summary = watchdog.write_summary(self.status_dir)
        self.assertIn("DEAD", summary)
        self.assertIn("screen session gone", summary)

    def test_multiple_tasks_each_on_own_line(self):
        for name in ("a", "b", "c"):
            self._write_task_status(name, {
                "task": name, "type": "training", "status": "OK"
            })
        summary = watchdog.write_summary(self.status_dir)
        lines = [l for l in summary.splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)

    def test_summary_txt_written_to_disk(self):
        self._write_task_status("exp01", {
            "task": "exp01", "type": "training", "status": "OK"
        })
        watchdog.write_summary(self.status_dir)
        summary_txt = self.status_dir / "summary.txt"
        self.assertTrue(summary_txt.exists())
        self.assertIn("exp01", summary_txt.read_text())

    def test_corrupt_status_file_is_skipped(self):
        (self.status_dir / "broken.json").write_text("not json{{{")
        self._write_task_status("good", {"task": "good", "type": "training", "status": "OK"})
        summary = watchdog.write_summary(self.status_dir)
        self.assertIn("good", summary)
        self.assertNotIn("broken", summary)


class TestCheckTraining(unittest.TestCase):
    """Test check_training() task monitoring."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.status_dir = Path(self.tmpdir) / "status"
        self.status_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('watchdog.session_alive', return_value=False)
    def test_dead_session_writes_dead_status(self, _mock):
        task = {"name": "exp01", "type": "training", "session": "exp01", "session_type": "screen"}
        result = watchdog.check_training(task, self.status_dir)
        self.assertEqual(result["status"], "DEAD")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_gpu_util', return_value=[85, 92])
    def test_active_gpus_writes_ok(self, _gpu, _sess):
        task = {"name": "exp01", "type": "training", "session": "exp01",
                "session_type": "screen", "gpus": [0, 1]}
        result = watchdog.check_training(task, self.status_dir)
        self.assertEqual(result["status"], "OK")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_gpu_util', return_value=[1, 2])
    def test_idle_gpus_writes_idle(self, _gpu, _sess):
        task = {"name": "exp01", "type": "training", "session": "exp01",
                "session_type": "screen", "gpus": [0, 1]}
        result = watchdog.check_training(task, self.status_dir)
        self.assertEqual(result["status"], "IDLE")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_gpu_util', return_value=[])
    def test_no_gpu_data_writes_ok(self, _gpu, _sess):
        """When nvidia-smi returns nothing, task is still OK (no info = no alarm)."""
        task = {"name": "exp01", "type": "training", "session": "exp01",
                "session_type": "screen", "gpus": [0, 1]}
        result = watchdog.check_training(task, self.status_dir)
        self.assertEqual(result["status"], "OK")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_gpu_util', return_value=[1, 0])
    def test_no_gpus_configured_writes_ok(self, _gpu, _sess):
        """If task has no 'gpus' field, no GPU check is done."""
        task = {"name": "exp01", "type": "training", "session": "exp01", "session_type": "screen"}
        result = watchdog.check_training(task, self.status_dir)
        self.assertEqual(result["status"], "OK")


class TestCheckDownload(unittest.TestCase):
    """Test check_download() task monitoring."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.status_dir = Path(self.tmpdir) / "status"
        self.status_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('watchdog.session_alive', return_value=False)
    def test_dead_session_writes_dead(self, _mock):
        task = {"name": "dl01", "type": "download", "session": "dl01",
                "session_type": "tmux", "target_path": "/data/file"}
        result = watchdog.check_download(task, self.status_dir, interval=60)
        self.assertEqual(result["status"], "DEAD")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_path_size', return_value=1024 * 1024 * 100)  # 100 MB
    def test_growing_file_writes_ok(self, _size, _sess):
        """File growing well above slow threshold → OK."""
        task = {"name": "dl01", "type": "download", "session": "dl01",
                "session_type": "tmux", "target_path": "/data/file"}
        # Previous status: smaller size
        (self.status_dir / "dl01.json").write_text(json.dumps({"size": 0}))
        result = watchdog.check_download(task, self.status_dir, interval=1)
        self.assertEqual(result["status"], "OK")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_path_size', return_value=500)
    def test_stalled_file_writes_stalled(self, _size, _sess):
        """Same size as last check → STALLED."""
        task = {"name": "dl01", "type": "download", "session": "dl01",
                "session_type": "tmux", "target_path": "/data/file"}
        (self.status_dir / "dl01.json").write_text(json.dumps({"size": 500}))
        result = watchdog.check_download(task, self.status_dir, interval=60)
        self.assertEqual(result["status"], "STALLED")

    @patch('watchdog.session_alive', return_value=True)
    @patch('watchdog.get_path_size', return_value=60 * 1024)  # 60 KB/s over 60s = 1 KB/s — SLOW
    def test_slow_download_writes_slow(self, _size, _sess):
        task = {"name": "dl01", "type": "download", "session": "dl01",
                "session_type": "tmux", "target_path": "/data/file"}
        (self.status_dir / "dl01.json").write_text(json.dumps({"size": 0}))
        result = watchdog.check_download(task, self.status_dir, interval=60)
        self.assertEqual(result["status"], "SLOW")

    @patch('watchdog.session_alive', return_value=True)
    def test_no_target_path_writes_ok(self, _sess):
        """When no target_path is given, liveness is enough for OK."""
        task = {"name": "dl01", "type": "download", "session": "dl01", "session_type": "tmux"}
        result = watchdog.check_download(task, self.status_dir, interval=60)
        self.assertEqual(result["status"], "OK")


if __name__ == "__main__":
    unittest.main()
