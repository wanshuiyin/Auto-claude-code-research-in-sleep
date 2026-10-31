"""Model-worker contract tests; fake native CLIs perform real local file writes."""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "mcp-servers/model-worker/server.py"

FAKE_CLI = r"""#!/usr/bin/env python3
import json, os, pathlib, signal, sys, time, uuid
args=sys.argv[1:]
def value(flag): return args[args.index(flag)+1]
backend = 'antigravity' if '--agent' in args else 'grok' if '--prompt-file' in args else 'claude-code'
if backend == 'antigravity':
    assert value('--agent') == 'aris-model-worker'
    assert value('--mode') == 'accept-edits' and '--sandbox' in args
    prompt=json.loads(sys.stdin.read())['message']['content']
    session=value('--conversation') if '--conversation' in args else str(uuid.uuid4())
    pathlib.Path(value('--log-file')).write_text('Propagating selected model override to backend: label="Gemini Fake (High)"')
elif backend == 'grok':
    assert value('--sandbox') == 'workspace'
    assert value('--tools') == 'read_file,grep,list_dir,write,search_replace'
    assert 'Edit(./**)' in args and 'MCPTool' in args
    assert '--no-subagents' in args and '--disable-web-search' in args
    prompt=pathlib.Path(value('--prompt-file')).read_text()
    session=value('--resume') if '--resume' in args else value('--session-id')
else:
    assert '--restricted' in args and '--bare' in args
    assert value('--setting-sources') == ''
    assert json.loads(value('--mcp-config')) == {'mcpServers':{}}
    assert value('--permission-mode') == 'dontAsk' and value('--permission-prompts') == 'none'
    assert value('--tools') == value('--allowedTools') == 'Read,Glob,Grep,Edit,Write'
    prompt=sys.stdin.read()
    session=value('--resume') if '--resume' in args else value('--session-id')
native=pathlib.Path(os.environ['FAKE_NATIVE_STATE']) / (session+'.json')
resume='--resume' in args or '--conversation' in args
if resume:
    previous=json.loads(native.read_text())
    assert previous['cwd'] == os.getcwd() and previous['backend'] == backend
native.write_text(json.dumps({'cwd':os.getcwd(), 'backend':backend, 'argv':args}))
if prompt == 'SLOW':
    pathlib.Path('started').write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)
if prompt == 'ORPHAN_PIPE':
    import subprocess
    child=subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])
    pathlib.Path('started').write_text(str(child.pid))
    time.sleep(0.1)
    sys.exit(0)
if prompt == 'UNKNOWN_TOOL': print('warning: unknown tool bogus', file=sys.stderr)
if prompt == 'SECRET_ERROR':
    print('API failed: '+os.environ.get('ANTHROPIC_AUTH_TOKEN',''), file=sys.stderr)
    sys.exit(8)
if prompt == 'CRASH': sys.exit(7)
if prompt == 'WRITE': pathlib.Path('answer.txt').write_text(pathlib.Path('input.txt').read_text()+' first')
if prompt == 'REVISE': pathlib.Path('answer.txt').write_text(pathlib.Path('answer.txt').read_text()+' revised')
content='' if prompt == 'EMPTY' else 'files revised' if resume else 'files written'
if prompt == 'REPLACE_SESSION': session=str(uuid.uuid4())
if prompt == 'INVALID_SESSION': session='not-a-uuid'
terminal_session=None if prompt == 'MISSING_TERMINAL_SESSION' else session
if backend == 'antigravity':
    print(json.dumps({'event':'init','conversation_id':session,'init':{'model':'wrong-model' if prompt == 'MODEL_MISMATCH' else value('--model')}}))
    if prompt == 'ERROR_THEN_SUCCESS': print(json.dumps({'event':'error','error':'failed'}))
    print(json.dumps({'event':'result','result':{'conversation_id':terminal_session,'response':content,'status':'ERROR' if prompt == 'FAIL' else 'SUCCESS'}}))
elif backend == 'grok':
    print(json.dumps({'type':'system','subtype':'init','session_id':session}))
    if prompt == 'ERROR_THEN_SUCCESS': print(json.dumps({'type':'error','message':'failed'}))
    print(json.dumps({'type':'result','subtype':'error' if prompt == 'FAIL' else 'success','session_id':terminal_session,'result':content,'stop_reason':'max_tokens' if prompt == 'TRUNCATED' else 'end_turn','modelUsage':{'grok-actual':{}}}))
else:
    print(json.dumps({'type':'result','subtype':'error' if prompt == 'FAIL' else 'success','is_error':prompt=='FAIL','session_id':terminal_session,'result':content,'stop_reason':'max_tokens' if prompt == 'TRUNCATED' else 'end_turn','modelUsage':{'deepseek-actual':{}}}))
"""


class Bridge:
    def __init__(self, env):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.messages = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self.messages.put(json.loads(line))

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def receive(self, request_id, timeout=8):
        deadline = time.monotonic() + timeout
        while True:
            message = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if message.get("id") == request_id:
                return message

    def call(self, name, args, request_id=1):
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
        )
        return self.receive(request_id)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)
        self.reader.join(timeout=1)
        stderr = self.proc.stderr.read()
        self.proc.stdout.close()
        self.proc.stderr.close()
        if self.proc.returncode or stderr:
            raise AssertionError(f"bridge exit={self.proc.returncode}, stderr={stderr}")


class ModelWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / "work"
        self.work.mkdir()
        (self.work / "input.txt").write_text("source")
        (self.root / "native").mkdir()
        binary = self.root / "fake-cli"
        binary.write_text(FAKE_CLI)
        binary.chmod(0o700)
        self.env = {
            **os.environ,
            "AGY_BIN": str(binary),
            "GROK_BIN": str(binary),
            "CLAUDE_BIN": str(binary),
            "MODEL_WORKER_STATE_DIR": str(self.root / "state"),
            "MODEL_WORKER_ALLOWED_ROOTS": json.dumps([str(self.work)]),
            "FAKE_NATIVE_STATE": str(self.root / "native"),
            "GROK_HOME": str(self.root / "grok"),
        }
        # Avoid reading the developer's real settings in all mocked tests.
        settings = self.root / "settings.json"
        settings.write_text('{"env":{}}')
        self.env["MODEL_WORKER_CLAUDE_SETTINGS"] = str(settings)

    def bridge(self):
        bridge = Bridge(self.env)
        self.addCleanup(bridge.close)
        return bridge

    def args(self, backend="claude-code", **changes):
        return {
            "prompt": "WRITE",
            "backend": backend,
            "model": "requested-alias",
            "cwd": str(self.work),
            **changes,
        }

    def test_each_backend_writes_and_resumes_after_server_restart(self):
        for backend, actual in (
            ("antigravity", "requested-alias"),
            ("grok", "grok-actual"),
            ("claude-code", "deepseek-actual"),
        ):
            with self.subTest(backend=backend):
                bridge = Bridge(self.env)
                try:
                    result = bridge.call("worker", self.args(backend, effort="high"))[
                        "result"
                    ]
                finally:
                    bridge.close()
                self.assertFalse(result.get("isError"), result)
                data = result["structuredContent"]
                self.assertEqual(data["model"], actual)
                self.assertEqual(data["requestedModel"], "requested-alias")
                self.assertEqual((self.work / "answer.txt").read_text(), "source first")
                if backend == "antigravity":
                    self.assertEqual(data["effort"], "high")
                    self.assertEqual(data["effortSource"], "cli_selected_model_variant")
                else:
                    self.assertIsNone(data["effort"])
                with (
                    self.root / "state/threads" / (data["threadId"] + ".json")
                ).open() as stream:
                    settings = json.load(stream)
                self.assertEqual(settings["backend"], backend)
                self.assertNotIn("prompt", settings)
                bridge = Bridge(self.env)
                try:
                    result = bridge.call(
                        "worker_reply",
                        {"threadId": data["threadId"], "prompt": "REVISE"},
                    )["result"]
                finally:
                    bridge.close()
                self.assertFalse(result.get("isError"), result)
                self.assertEqual(
                    result["structuredContent"]["threadId"], data["threadId"]
                )
                self.assertEqual(
                    (self.work / "answer.txt").read_text(), "source first revised"
                )

    def test_invalid_arguments_do_not_launch_cli(self):
        bridge = self.bridge()
        for changes in (
            {"cwd": "."},
            {"cwd": str(self.root)},
            {"backend": "gemini"},
            {"backend": "grok", "effort": "max"},
            {"timeout_sec": True},
            {"timeout_sec": 0},
            {"prompt": ""},
            {"tools": "Bash"},
            {"model": ""},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    bridge.call("worker", self.args(**changes))["error"]["code"], -32602
                )
        self.assertEqual(list((self.root / "native").iterdir()), [])

    def test_reply_cannot_mutate_settings_or_escape_saved_cwd(self):
        bridge = self.bridge()
        data = bridge.call("worker", self.args())["result"]["structuredContent"]
        bad = bridge.call(
            "worker_reply",
            {"threadId": data["threadId"], "prompt": "REVISE", "model": "other"},
        )
        self.assertEqual(bad["error"]["code"], -32602)
        self.assertEqual(
            bridge.call("worker_reply", {"threadId": "../../bad", "prompt": "REVISE"})[
                "error"
            ]["code"],
            -32602,
        )
        replaced = bridge.call(
            "worker_reply", {"threadId": data["threadId"], "prompt": "REPLACE_SESSION"}
        )["result"]
        self.assertTrue(replaced["isError"])
        self.assertIn(
            "different native session", replaced["structuredContent"]["error"]
        )
        self.assertEqual(len(list((self.root / "state/threads").glob("*.json"))), 1)
        invalid = bridge.call("worker", self.args(prompt="INVALID_SESSION"))["result"]
        self.assertTrue(invalid["isError"])
        self.assertIn(
            "valid native session UUID", invalid["structuredContent"]["error"]
        )

    def test_state_must_be_outside_work_directory(self):
        self.env["MODEL_WORKER_STATE_DIR"] = str(self.work / "state")
        self.assertIn(
            "overlap", self.bridge().call("worker", self.args())["error"]["message"]
        )

    def test_failures_empty_results_and_truncation_are_errors(self):
        bridge = self.bridge()
        for backend in ("antigravity", "grok", "claude-code"):
            for prompt in (
                ("CRASH", "FAIL", "EMPTY", "UNKNOWN_TOOL", "MISSING_TERMINAL_SESSION")
                + (() if backend == "antigravity" else ("TRUNCATED", "REPLACE_SESSION"))
                + (() if backend == "claude-code" else ("ERROR_THEN_SUCCESS",))
            ):
                with self.subTest(backend=backend, prompt=prompt):
                    result = bridge.call("worker", self.args(backend, prompt=prompt))[
                        "result"
                    ]
                    self.assertTrue(result["isError"], result)
                    self.assertTrue(result["structuredContent"]["error"])

    def test_known_effort_and_antigravity_model_mismatches_are_errors(self):
        bridge = self.bridge()
        effort = bridge.call("worker", self.args("antigravity", effort="max"))["result"]
        self.assertTrue(effort["isError"])
        self.assertEqual(effort["structuredContent"]["requestedEffort"], "max")
        self.assertEqual(effort["structuredContent"]["effort"], "high")
        self.assertIn("different effort", effort["structuredContent"]["error"])
        model = bridge.call(
            "worker", self.args("antigravity", prompt="MODEL_MISMATCH")
        )["result"]
        self.assertTrue(model["isError"])
        self.assertIn("different model", model["structuredContent"]["error"])

    def test_ping_cancel_and_timeout_force_cleanup(self):
        bridge = self.bridge()
        bridge.send(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "worker", "arguments": self.args(prompt="SLOW")},
            }
        )
        deadline = time.monotonic() + 5
        while not (self.work / "started").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.work / "started").exists())
        pid = int((self.work / "started").read_text())
        bridge.send({"jsonrpc": "2.0", "id": 10, "method": "ping"})
        self.assertEqual(bridge.receive(10)["result"], {})
        bridge.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 9},
            }
        )
        result = bridge.receive(9)["result"]
        self.assertIn("cancelled", result["structuredContent"]["error"])
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        result = bridge.call("worker", self.args(prompt="SLOW", timeout_sec=0.1))[
            "result"
        ]
        self.assertIn("timed out", result["structuredContent"]["error"])
        pid = int((self.work / "started").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_default_effort_is_frozen_and_secret_settings_not_persisted(self):
        settings = Path(self.env["MODEL_WORKER_CLAUDE_SETTINGS"])
        settings.write_text(
            json.dumps(
                {
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": "private-provider-token",
                        "UNSAFE_SETTING": "not-copied",
                    }
                }
            )
        )
        result = self.bridge().call("worker", self.args())["result"]
        self.assertEqual(result["structuredContent"]["requestedEffort"], "high")
        self.assertIsNone(result["structuredContent"]["effort"])
        state = next((self.root / "state/threads").glob("*.json")).read_text()
        self.assertNotIn("private-provider-token", state)
        native = json.loads(next((self.root / "native").glob("*.json")).read_text())
        self.assertEqual(native["argv"][native["argv"].index("--effort") + 1], "high")
        self.assertNotIn("private-provider-token", json.dumps(result))
        failure = self.bridge().call("worker", self.args(prompt="SECRET_ERROR"))[
            "result"
        ]
        self.assertIn("[redacted]", json.dumps(failure))
        self.assertNotIn("private-provider-token", json.dumps(failure))

    def test_timeout_kills_descendants_after_leader_exits(self):
        started = time.monotonic()
        result = self.bridge().call(
            "worker", self.args(prompt="ORPHAN_PIPE", timeout_sec=0.3)
        )["result"]
        self.assertTrue(result["isError"])
        self.assertIn("timed out", result["structuredContent"]["error"])
        self.assertLess(time.monotonic() - started, 5)

    def test_existing_reviewer_defaults_are_unchanged(self):
        for directory, expected in (
            ("grok-exec", "read-only"),
            ("claude-review", "plan"),
            ("antigravity-exec", "aris-antigravity-review"),
        ):
            spec = importlib.util.spec_from_file_location(
                "test_" + directory.replace("-", "_"),
                REPO / "mcp-servers" / directory / "server.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if directory == "grok-exec":
                self.assertEqual(module.normalize_options({})["sandbox"], expected)
                self.assertEqual(module.READ_TOOLS, "read_file,grep,list_dir")
            elif directory == "antigravity-exec":
                self.assertEqual(module.AGENT, expected)
            else:
                with patch.object(module, "find_claude_bin", return_value="claude"):
                    command = module.build_command("review")
                self.assertEqual(
                    command[command.index("--permission-mode") + 1], expected
                )


if __name__ == "__main__":
    unittest.main()
