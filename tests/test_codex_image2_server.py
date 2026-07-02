"""Unit tests for the experimental codex-image2 MCP bridge."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "mcp-servers" / "codex-image2" / "server.py"
# server.py defers its stdio rebind into _init_stdio() (called from main()), so
# a plain import has no stdio side effects and is safe under pytest fd-capture.
SPEC = importlib.util.spec_from_file_location("codex_image2_server", SERVER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


PNG_BYTES = MODULE.PNG_SIGNATURE + b"fake-png-payload"

SAMPLE_IMAGE_STDOUT = """
< {
<   "method": "item/completed",
<   "params": {
<     "item": {
<       "type": "imageGeneration",
<       "id": "ig_test",
<       "status": "completed",
<       "revisedPrompt": "blue circle",
<       "result": "iVBORw0KGgpmYWtlLXBuZy1wYXlsb2Fk"
<     },
<     "threadId": "thread-123",
<     "turnId": "turn-123"
<   }
< }
< {
<   "method": "item/completed",
<   "params": {
<     "item": {
<       "type": "agentMessage",
<       "id": "msg-1",
<       "text": "",
<       "phase": "final_answer",
<       "memoryCitation": null
<     },
<     "threadId": "thread-123",
<     "turnId": "turn-123"
<   }
< }
"""

SAMPLE_NATIVE_UNAVAILABLE_STDOUT = """
< {
<   "method": "item/completed",
<   "params": {
<     "item": {
<       "type": "agentMessage",
<       "id": "msg-1",
<       "text": "NATIVE_IMAGE_UNAVAILABLE",
<       "phase": "final_answer"
<     },
<     "threadId": "thread-123",
<     "turnId": "turn-123"
<   }
< }
"""

SAMPLE_WITH_COMMAND = """
< {
<   "method": "item/completed",
<   "params": {
<     "item": {
<       "type": "commandExecution",
<       "id": "cmd-1",
<       "command": "python3 make_png.py",
<       "cwd": "/tmp",
<       "processId": null,
<       "source": "model",
<       "status": "completed",
<       "commandActions": [],
<       "aggregatedOutput": "",
<       "exitCode": 0,
<       "durationMs": 12
<     },
<     "threadId": "thread-123",
<     "turnId": "turn-123"
<   }
< }
"""

SAMPLE_BAD_IMAGE_STDOUT = """
< {
<   "method": "item/completed",
<   "params": {
<     "item": {
<       "type": "imageGeneration",
<       "id": "ig_test",
<       "status": "completed",
<       "revisedPrompt": "blue circle",
<       "result": "aGVsbG8="
<     },
<     "threadId": "thread-123",
<     "turnId": "turn-123"
<   }
< }
"""


class _FakePopen:
    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid


class CodexImage2ServerTests(unittest.TestCase):
    def test_parse_debug_json_messages(self) -> None:
        messages = MODULE.parse_debug_json_messages(SAMPLE_IMAGE_STDOUT)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["params"]["item"]["type"], "imageGeneration")

    def test_extract_run_summary(self) -> None:
        messages = MODULE.parse_debug_json_messages(SAMPLE_IMAGE_STDOUT + SAMPLE_WITH_COMMAND)
        summary = MODULE.extract_run_summary(messages)
        self.assertEqual(summary["threadId"], "thread-123")
        self.assertEqual(len(summary["imageItems"]), 1)
        self.assertEqual(len(summary["commandItems"]), 1)

    def test_build_bridge_prompt_includes_references(self) -> None:
        prompt = MODULE.build_bridge_prompt(
            "Draw a workflow.",
            system="Academic style only.",
            reference_image_paths=["/tmp/ref1.png", "/tmp/ref2.png"],
        )
        self.assertIn("Academic style only.", prompt)
        self.assertIn("/tmp/ref1.png", prompt)
        self.assertIn("Draw a workflow.", prompt)
        self.assertIn("native image generation", prompt)

    def test_materialize_generated_image_from_saved_path_validates_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            source_path = temp_root / "source.png"
            source_path.write_bytes(PNG_BYTES)
            output_path = temp_root / "out.png"
            image_item = {
                "type": "imageGeneration",
                "revisedPrompt": "blue circle",
                "savedPath": str(source_path),
            }
            generated_path, source_saved_path, revised_prompt, error = MODULE.materialize_generated_image(
                image_item,
                output_path,
            )
            self.assertEqual(generated_path, output_path)
            self.assertEqual(source_saved_path, str(source_path))
            self.assertEqual(revised_prompt, "blue circle")
            self.assertIsNone(error)
            self.assertEqual(output_path.read_bytes(), PNG_BYTES)

    def test_materialize_generated_image_rejects_non_png_base64(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"
            image_item = {
                "type": "imageGeneration",
                "revisedPrompt": "blue circle",
                "result": "aGVsbG8=",
            }
            generated_path, source_saved_path, revised_prompt, error = MODULE.materialize_generated_image(
                image_item,
                output_path,
            )
            self.assertIsNone(generated_path)
            self.assertIsNone(source_saved_path)
            self.assertIsNone(revised_prompt)
            self.assertIn("PNG", error or "")

    def test_validate_output_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            outside = Path(tmpdir) / "outside.png"
            cwd.mkdir()
            error = MODULE.validate_output_path(outside.resolve(), cwd=cwd.resolve())
            self.assertIn("outputPath must stay under", error or "")

    def test_run_codex_image_returns_error_when_codex_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value=None):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                )
            self.assertIsNone(payload)
            self.assertIn("Codex CLI not found", error or "")

    def test_run_codex_image_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value="codex"), mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd=["codex"], timeout=5),
            ):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                    timeout_sec=5,
                )
            self.assertIsNone(payload)
            self.assertIn("timed out", error or "")

    def test_run_codex_image_surfaces_native_unavailable(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=SAMPLE_NATIVE_UNAVAILABLE_STDOUT,
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value="codex"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                )
            self.assertIsNone(payload)
            self.assertIn("native image generation is unavailable", error or "")

    def test_run_codex_image_rejects_command_execution(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=SAMPLE_WITH_COMMAND,
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value="codex"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                )
            self.assertIsNone(payload)
            self.assertIn("shell-based image creation", error or "")

    def test_run_codex_image_rejects_malformed_image_payload(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=SAMPLE_BAD_IMAGE_STDOUT,
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value="codex"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                )
            self.assertIsNone(payload)
            self.assertIn("PNG", error or "")

    def test_run_codex_image_accepts_valid_png_result(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=SAMPLE_IMAGE_STDOUT,
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            output_path = cwd / "figures" / "ai_generated" / "out.png"
            cwd.mkdir()
            with mock.patch.object(MODULE, "find_codex_bin", return_value="codex"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                payload, error = MODULE.run_codex_image(
                    "Draw a workflow.",
                    cwd=cwd,
                    output_path=output_path,
                )
            self.assertIsNone(error)
            self.assertEqual(payload["outputPath"], str(output_path.resolve()))
            self.assertEqual(output_path.read_bytes(), PNG_BYTES)

    def test_start_async_generate_rejects_output_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            cwd.mkdir()
            with mock.patch.object(MODULE.subprocess, "Popen", return_value=_FakePopen()):
                payload, error = MODULE.start_async_generate(
                    "Draw a workflow.",
                    cwd=str(cwd),
                    output_path=str(Path(tmpdir) / "escape.png"),
                )
            self.assertIsNone(payload)
            self.assertIn("outputPath must stay under", error or "")

    def test_start_async_generate_persists_timeout_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "workspace"
            jobs_dir = Path(tmpdir) / "jobs"
            cwd.mkdir()
            with mock.patch.object(MODULE, "JOBS_DIR", jobs_dir), mock.patch.object(
                MODULE.subprocess,
                "Popen",
                return_value=_FakePopen(pid=4321),
            ):
                payload, error = MODULE.start_async_generate(
                    "Draw a workflow.",
                    cwd=str(cwd),
                    timeout_seconds=45,
                )
            self.assertIsNone(error)
            self.assertEqual(payload["status"], "queued")
            job_file = jobs_dir / f"{payload['jobId']}.json"
            job = json.loads(job_file.read_text(encoding="utf-8"))
            self.assertEqual(job["request"]["timeoutSec"], 45)
            self.assertIsNotNone(job["expiresAt"])

    def test_get_generate_status_marks_stale_job_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir) / "jobs"
            jobs_dir.mkdir()
            job_id = "stale-job"
            job_path = jobs_dir / f"{job_id}.json"
            job = {
                "jobId": job_id,
                "status": "running",
                "createdAt": MODULE.utc_now(),
                "startedAt": MODULE.utc_now(),
                "completedAt": None,
                "updatedAt": MODULE.utc_now(),
                "expiresAt": "2000-01-01T00:00:00Z",
                "workerPid": 123,
                "error": None,
                "result": None,
                "request": {
                    "prompt": "sensitive prompt",
                    "cwd": "/tmp/workspace",
                    "outputPath": "/tmp/workspace/figures/ai_generated/out.png",
                    "timeoutSec": 5,
                },
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            with mock.patch.object(MODULE, "JOBS_DIR", jobs_dir):
                payload, error = MODULE.get_generate_status(job_id)
            self.assertIsNone(error)
            self.assertEqual(payload["status"], "failed")
            stored = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertNotIn("prompt", stored["request"])
            self.assertIn("deadline", stored["error"])

    def test_get_generate_status_marks_exited_worker_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir) / "jobs"
            jobs_dir.mkdir()
            job_id = "dead-worker"
            job_path = jobs_dir / f"{job_id}.json"
            job = {
                "jobId": job_id,
                "status": "running",
                "createdAt": MODULE.utc_now(),
                "startedAt": MODULE.utc_now(),
                "completedAt": None,
                "updatedAt": MODULE.utc_now(),
                "expiresAt": "2999-01-01T00:00:00Z",
                "workerPid": 321,
                "error": None,
                "result": None,
                "request": {
                    "prompt": "sensitive prompt",
                    "cwd": "/tmp/workspace",
                    "outputPath": "/tmp/workspace/figures/ai_generated/out.png",
                    "timeoutSec": 5,
                },
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            with mock.patch.object(MODULE, "JOBS_DIR", jobs_dir), mock.patch.object(
                MODULE,
                "classify_worker_state",
                return_value="exited",
            ):
                payload, error = MODULE.get_generate_status(job_id)
            self.assertIsNone(error)
            self.assertEqual(payload["status"], "failed")
            self.assertIn("exited before writing", payload["error"])


if __name__ == "__main__":
    unittest.main()
