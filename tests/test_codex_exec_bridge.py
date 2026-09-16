#!/usr/bin/env python3
"""mcp-servers/codex-exec: the `codex` MCP server over `codex exec`.

codex-cli 0.154.0 removed `codex mcp-server`; this bridge stands in for it
under the same server key, so `mcp__codex__codex` / `mcp__codex__codex-reply`
keep working unchanged. These tests pin:

  - the MCP surface: tool names, argument schemas, result shape
    `{structuredContent:{threadId, content}, content:[{type:text}]}`
  - argv construction: prompt on stdin, `-c key=value` in TOML, dotted keys
  - failure shape: `isError:true` with the raw codex error text (ARIS's
    capability fallback keys on that text)
  - codex-reply re-applies the model/config/sandbox/cwd the thread was
    created with (`codex exec resume` alone would drop them)
  - a silent child still gets progress, and ping / cancel are honoured
    while it runs

A fake `codex` on CODEX_BIN stands in for the real CLI.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER = REPO_ROOT / "mcp-servers" / "codex-exec" / "server.py"

FAKE_CODEX = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys, time
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    with open(os.environ["FAKE_CODEX_LOG"], "a") as fh:
        fh.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "prompt": prompt}) + "\\n")
    def emit(o):
        sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
    tid = argv[argv.index("resume") + 1] if "resume" in argv else "thread-" + str(abs(hash(prompt)) % 10000)
    emit({"type": "thread.started", "thread_id": tid})
    emit({"type": "turn.started"})
    if "FAILTHEN" in prompt:
        emit({"type": "turn.failed", "error": {"message": "terminal failure"}})
        emit({"type": "turn.completed", "usage": {}})
        sys.exit(0)
    if "FAIL" in prompt:
        emit({"type": "error", "message": "The 'gpt-nope' model is not supported when using Codex with a ChatGPT account."})
        emit({"type": "turn.failed", "error": {"message": "The 'gpt-nope' model is not supported when using Codex with a ChatGPT account."}})
        sys.exit(0)
    if "CRASH" in prompt:
        sys.stderr.write("boom: something went wrong\\n")
        sys.exit(3)
    if "EOF" in prompt:
        sys.exit(0)
    if "SLOW" in prompt:
        time.sleep(float(os.environ.get("FAKE_CODEX_SLEEP", "3")))
    if "RECOVER" in prompt:
        emit({"type": "item.completed", "item": {"id": "i0", "type": "error", "message": "transient"}})
    emit({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "first"}})
    emit({"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": "echo:" + prompt.strip()}})
    emit({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
    """
)


def load_module():
    spec = importlib.util.spec_from_file_location("codex_exec_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ArgvTests(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_toml_values(self):
        self.assertEqual(self.m.toml_value("ultra"), '"ultra"')
        self.assertEqual(self.m.toml_value(True), "true")
        self.assertEqual(self.m.toml_value(3), "3")
        self.assertEqual(self.m.toml_value(["a", "b"]), '["a", "b"]')

    def test_config_flattens_to_dotted_keys(self):
        flags = self.m.config_flags({"model_reasoning_effort": "ultra", "features": {"x": True}})
        self.assertEqual(flags, ["-c", 'model_reasoning_effort="ultra"', "-c", "features.x=true"])

    def test_new_thread_argv(self):
        argv = self.m.build_argv({"model": "gpt-6-astra", "sandbox": "read-only", "cwd": "/w",
                                  "config": {"model_reasoning_effort": "xhigh"}})
        self.assertEqual(argv[1:], ["exec", "--skip-git-repo-check", "--json", "--cd", "/w", "--sandbox", "read-only",
                                    "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="xhigh"', "-"])

    def test_resume_argv_reapplies_settings_without_cd(self):
        argv = self.m.build_argv({"model": "gpt-5.5", "sandbox": "read-only", "cwd": "/w",
                                  "config": {"model_reasoning_effort": "low"}}, resume_thread="t1")
        self.assertEqual(argv[1:], ["exec", "resume", "t1", "--skip-git-repo-check", "--json",
                                    "-c", 'sandbox_mode="read-only"', "-m", "gpt-5.5",
                                    "-c", 'model_reasoning_effort="low"', "-"])
        self.assertNotIn("--cd", argv)


class BridgeProcess:
    """Drives the server over newline-delimited JSON-RPC."""

    def __init__(self, env, cwd=None):
        self.proc = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1, env=env, cwd=cwd)
        self.notifications = []

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def recv(self, want_id, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == want_id and ("result" in msg or "error" in msg):
                return msg
            self.notifications.append(msg)
        raise AssertionError(f"no response for id={want_id}; notifications={self.notifications[-3:]}")

    def call(self, rid, name, arguments, meta=None):
        params = {"name": name, "arguments": arguments}
        if meta:
            params["_meta"] = meta
        self.send({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": params})
        return self.recv(rid)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-exec-"))
        fake = self.tmp / "codex"
        fake.write_text(FAKE_CODEX)
        fake.chmod(0o755)
        self.log = self.tmp / "fake.log"
        self.env = dict(os.environ)
        self.env.update({
            "CODEX_BIN": str(fake),
            "CODEX_EXEC_STATE_DIR": str(self.tmp / "state"),
            "CODEX_EXEC_PROGRESS_INTERVAL_SEC": "0.5",
            "FAKE_CODEX_LOG": str(self.log),
        })
        self.bridge = BridgeProcess(self.env, cwd=str(self.tmp))
        self.bridge.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.init = self.bridge.recv(1)
        self.bridge.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def tearDown(self):
        self.bridge.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()]

    def test_handshake_and_tool_surface(self):
        self.assertEqual(self.init["result"]["protocolVersion"], "2025-06-18")
        self.bridge.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"]: t for t in self.bridge.recv(2)["result"]["tools"]}
        self.assertEqual(set(tools), {"codex", "codex-reply"})
        self.assertEqual(set(tools["codex"]["inputSchema"]["properties"]), {"prompt", "model", "config", "sandbox", "cwd"})
        self.assertEqual(tools["codex"]["inputSchema"]["required"], ["prompt"])
        self.assertEqual(set(tools["codex-reply"]["inputSchema"]["properties"]), {"prompt", "threadId", "conversationId"})
        self.assertEqual(tools["codex"]["inputSchema"]["properties"]["sandbox"]["enum"],
                         ["read-only", "workspace-write", "danger-full-access"])

    def test_call_result_shape_and_prompt_on_stdin(self):
        r = self.bridge.call(3, "codex", {"prompt": "hello there", "model": "gpt-6-astra", "sandbox": "read-only",
                                          "config": {"model_reasoning_effort": "ultra"}})
        result = r["result"]
        self.assertNotIn("isError", result)
        self.assertEqual(result["content"], [{"type": "text", "text": "echo:hello there"}])
        self.assertEqual(result["structuredContent"]["content"], "echo:hello there")
        self.assertTrue(result["structuredContent"]["threadId"].startswith("thread-"))
        call = self.fake_calls()[0]
        self.assertEqual(call["prompt"], "hello there")
        self.assertEqual(call["argv"], ["exec", "--skip-git-repo-check", "--json", "--sandbox", "read-only",
                                        "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="ultra"', "-"])
        self.assertTrue(any(n.get("method") == "codex/event" for n in self.bridge.notifications))

    def test_failure_keeps_raw_error_text(self):
        r = self.bridge.call(4, "codex", {"prompt": "please FAIL", "model": "gpt-nope"})
        result = r["result"]
        self.assertTrue(result["isError"])
        self.assertIn("'gpt-nope' model is not supported", result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["content"], result["content"][0]["text"])

    def test_intermediate_error_then_completion_is_success(self):
        r = self.bridge.call(5, "codex", {"prompt": "RECOVER please"})
        self.assertNotIn("isError", r["result"])
        self.assertEqual(r["result"]["structuredContent"]["content"], "echo:RECOVER please")

    def test_crash_without_completion_reports_status_and_stderr(self):
        r = self.bridge.call(6, "codex", {"prompt": "CRASH now"})
        self.assertTrue(r["result"]["isError"])
        text = r["result"]["content"][0]["text"]
        self.assertIn("status 3", text)
        self.assertIn("boom", text)

    def test_stream_ending_without_completion_is_an_error(self):
        r = self.bridge.call(14, "codex", {"prompt": "EOF early"})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("status 0 before completing", r["result"]["content"][0]["text"])

    def test_terminal_failure_is_not_cleared_by_a_later_completion(self):
        r = self.bridge.call(15, "codex", {"prompt": "FAILTHEN"})
        self.assertTrue(r["result"]["isError"])
        self.assertEqual(r["result"]["content"][0]["text"], "terminal failure")

    def test_request_arriving_mid_call_is_answered_afterwards(self):
        self.env["FAKE_CODEX_SLEEP"] = "2"
        self.bridge.close()
        self.bridge = BridgeProcess(self.env, cwd=str(self.tmp))
        self.bridge.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.bridge.recv(1)
        self.bridge.send({"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                          "params": {"name": "codex", "arguments": {"prompt": "SLOW"}}})
        time.sleep(0.8)
        self.bridge.send({"jsonrpc": "2.0", "id": 17, "method": "tools/list"})
        done = self.bridge.recv(16)
        self.assertEqual(done["result"]["structuredContent"]["content"], "echo:SLOW")
        listing = self.bridge.recv(17, timeout=5)   # must not be stranded once the call has returned
        self.assertEqual([tool["name"] for tool in listing["result"]["tools"]], ["codex", "codex-reply"])

    def test_reply_reapplies_thread_settings(self):
        work = self.tmp / "work"
        work.mkdir()
        first = self.bridge.call(7, "codex", {"prompt": "start", "model": "gpt-5.5", "sandbox": "read-only",
                                              "cwd": str(work), "config": {"model_reasoning_effort": "low"}})
        tid = first["result"]["structuredContent"]["threadId"]
        record = self.tmp / "state" / "threads" / (tid + ".json")
        self.assertTrue(record.is_file(), "one settings file per thread")
        self.assertEqual(json.loads(record.read_text())["model"], "gpt-5.5")
        second = self.bridge.call(8, "codex-reply", {"threadId": tid, "prompt": "continue"})
        self.assertEqual(second["result"]["structuredContent"]["threadId"], tid)
        self.assertEqual(second["result"]["structuredContent"]["content"], "echo:continue")
        reply = self.fake_calls()[1]
        self.assertEqual(reply["argv"], ["exec", "resume", tid, "--skip-git-repo-check", "--json",
                                         "-c", 'sandbox_mode="read-only"', "-m", "gpt-5.5",
                                         "-c", 'model_reasoning_effort="low"', "-"])
        self.assertEqual(Path(reply["cwd"]).resolve(), work.resolve())

    def test_reply_accepts_deprecated_conversation_id(self):
        first = self.bridge.call(9, "codex", {"prompt": "start"})
        tid = first["result"]["structuredContent"]["threadId"]
        r = self.bridge.call(10, "codex-reply", {"conversationId": tid, "prompt": "again"})
        self.assertEqual(r["result"]["structuredContent"]["threadId"], tid)

    def test_silent_child_gets_progress_and_answers_ping(self):
        self.env["FAKE_CODEX_SLEEP"] = "2"
        self.bridge.close()
        self.bridge = BridgeProcess(self.env, cwd=str(self.tmp))
        self.bridge.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.bridge.recv(1)
        self.bridge.send({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                          "params": {"_meta": {"progressToken": "p11"}, "name": "codex", "arguments": {"prompt": "SLOW"}}})
        time.sleep(0.8)
        self.bridge.send({"jsonrpc": "2.0", "id": 12, "method": "ping"})
        pong = self.bridge.recv(12, timeout=5)
        self.assertEqual(pong["result"], {})
        done = self.bridge.recv(11)
        self.assertEqual(done["result"]["structuredContent"]["content"], "echo:SLOW")
        progress = [n for n in self.bridge.notifications if n.get("method") == "notifications/progress"]
        self.assertTrue(progress, "expected timer-driven progress while the child was silent")
        self.assertEqual(progress[0]["params"]["progressToken"], "p11")

    def test_cancel_terminates_child(self):
        self.env["FAKE_CODEX_SLEEP"] = "20"
        self.bridge.close()
        self.bridge = BridgeProcess(self.env, cwd=str(self.tmp))
        self.bridge.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.bridge.recv(1)
        self.bridge.send({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                          "params": {"name": "codex", "arguments": {"prompt": "SLOW"}}})
        time.sleep(0.8)
        started = time.time()
        self.bridge.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 13}})
        r = self.bridge.recv(13, timeout=10)
        self.assertLess(time.time() - started, 8)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("cancelled", r["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
