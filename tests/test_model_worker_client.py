"""The fallback client exercises the same MCP server across separate processes."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.test_model_worker import FAKE_CLI

CLIENT = Path(__file__).resolve().parents[1] / "mcp-servers/model-worker/client.py"


def load_client():
    spec = importlib.util.spec_from_file_location("model_worker_client", CLIENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "input.txt").write_text("verified fact")
    native = tmp_path / "native"
    native.mkdir()
    fake = tmp_path / "fake-cli"
    fake.write_text(FAKE_CLI)
    fake.chmod(0o700)
    for key, value in {
        "AGY_BIN": str(fake),
        "MODEL_WORKER_ALLOWED_ROOTS": json.dumps([str(work)]),
        "MODEL_WORKER_STATE_DIR": str(tmp_path / "state"),
        "FAKE_NATIVE_STATE": str(native),
    }.items():
        monkeypatch.setenv(key, value)
    return {
        "cwd": str(work),
        "backend": "antigravity",
        "model": "gemini-actual",
        "prompt": "WRITE",
    }


def test_local_client_write_then_resume_across_server_restart(tmp_path, monkeypatch):
    args = configure(tmp_path, monkeypatch)
    client = load_client()
    listed = client.call("tools/list", {}, local=True)
    assert {t["name"] for t in listed["tools"]} == {"worker", "worker_reply"}
    first = client.call("worker", args, local=True)
    assert not first.get("isError"), first
    tid = first["structuredContent"]["threadId"]
    second = client.call(
        "worker_reply", {"threadId": tid, "prompt": "REVISE"}, local=True
    )
    assert not second.get("isError"), second
    assert second["structuredContent"]["threadId"] == tid
    assert (
        Path(args["cwd"]) / "answer.txt"
    ).read_text() == "verified fact first revised"


def test_client_cli_preserves_tool_failure_and_exits_nonzero(tmp_path, monkeypatch):
    args = configure(tmp_path, monkeypatch)
    args["prompt"] = "CRASH"
    packet = tmp_path / "input.json"
    packet.write_text(json.dumps(args))
    result = subprocess.run(
        [sys.executable, str(CLIENT), "--local", "worker", "--input", str(packet)],
        capture_output=True,
        check=False,
        text=True,
        env=os.environ.copy(),
        timeout=10,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["isError"] is True
