"""验证 Antigravity 桥接的真实 stdio 接线、会话固定设置和失败语义。"""

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

SERVER = Path(__file__).resolve().parents[1] / "mcp-servers/antigravity-exec/server.py"
FAKE = r"""#!/usr/bin/env python3
import json,os,sys,time,signal,uuid
from pathlib import Path
a=sys.argv[1:]
def arg(k):return a[a.index(k)+1]
prompt=json.loads(sys.stdin.readline())['message']['content']
tid=arg('--conversation') if '--conversation' in a else str(uuid.uuid4())
with open(os.environ['FAKE_AGY_LOG'],'a') as f:
 f.write(json.dumps({'argv':a,'prompt':prompt,'cwd':os.getcwd()})+'\n')
def emit(o):print(json.dumps(o),flush=True)
effort='Low' if prompt=='WRONG_EFFORT' else arg('--effort').title()
if prompt!='NO_METADATA':
 Path(arg('--log-file')).write_text('Propagating selected model override to backend: label="Gemini 3.8 Flash ('+effort+')"\n')
model='wrong-model' if prompt=='WRONG_MODEL' else arg('--model')
emit({'event':'init','conversation_id':tid,'init':{'model':model,'agent':arg('--agent')}})
if prompt=='SLOW':
 signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
 time.sleep(30)
if prompt=='EOF':sys.exit(0)
if prompt in ['FAIL','FAILTHEN']:
 emit({'event':'result','result':{'conversation_id':tid,'status':'ERROR','error':'provider unavailable'}})
 if prompt=='FAIL':sys.exit(1)
emit({'event':'result','result':{'conversation_id':str(uuid.uuid4()) if prompt=='WRONG_ID' else tid,'status':'WAITING' if prompt=='TRUNC' else 'SUCCESS','response':'' if prompt=='EMPTY' else 'echo:'+prompt}})
sys.exit(3 if prompt=='EXIT3' else 0)
"""


class Client:
    def __init__(self, env, cwd):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if (
            self.proc.stdin is None
            or self.proc.stdout is None
            or self.proc.stderr is None
        ):
            self.proc.kill()
            self.proc.wait()
            raise RuntimeError("test subprocess pipes were not created")
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self.stderr = self.proc.stderr
        self.queue = queue.Queue()
        self.notifications = []

        def reader():
            for line in self.stdout:
                self.queue.put(json.loads(line))

        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()

    def send(self, obj):
        self.stdin.write(json.dumps(obj) + "\n")
        self.stdin.flush()

    def recv(self, rid):
        while True:
            msg = self.queue.get(timeout=5)
            if msg.get("id") == rid:
                return msg
            self.notifications.append(msg)

    def call(self, rid, name, args):
        self.send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
        )
        return self.recv(rid)

    def close(self):
        if not self.stdin.closed:
            self.stdin.close()
        try:
            self.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self.reader.join(timeout=1)
        self.stdout.close()
        self.stderr.close()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="antigravity-exec-test-")
        self.root = Path(self.tmp.name).resolve()
        fake = self.root / "antigravity"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.env = dict(
            os.environ,
            AGY_BIN=str(fake),
            AGY_EXEC_STATE_DIR=str(self.root / "state"),
            AGY_EXEC_PROGRESS_INTERVAL_SEC="0.05",
            AGY_EXEC_TIMEOUT_SEC="5",
            FAKE_AGY_LOG=str(self.log),
        )
        self.client = Client(self.env, self.root)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def calls(self):
        return [json.loads(s) for s in self.log.read_text().splitlines()]

    def test_mcp_surface_and_real_response(self):
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(
            self.client.recv(1)["result"]["serverInfo"]["name"], "antigravity-exec"
        )
        self.client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            {t["name"] for t in self.client.recv(2)["result"]["tools"]},
            {"antigravity", "antigravity-reply"},
        )
        r = self.client.call(3, "antigravity", {"prompt": "hello"})["result"]
        self.assertNotIn("isError", r)
        self.assertIn("echo:hello", r["content"][0]["text"])
        s = r["structuredContent"]
        self.assertEqual(s["effort"], "high")
        self.assertEqual(s["model"], "gemini-3.8-flash-high")
        self.assertEqual(s["requestedModel"], "gemini-3.8-flash-high")
        self.assertEqual(s["content"], "echo:hello")

    def test_resume_keeps_settings_after_server_restart(self):
        work = self.root / "work"
        work.mkdir()
        tid = self.client.call(
            1,
            "antigravity",
            {
                "prompt": "first",
                "model": "gemini-3.8-flash-high",
                "effort": "high",
                "cwd": str(work),
            },
        )["result"]["structuredContent"]["threadId"]
        self.client.close()
        self.env["AGY_EXEC_EFFORT"] = "low"
        self.client = Client(self.env, self.root)
        r = self.client.call(
            2, "antigravity-reply", {"threadId": tid, "prompt": "second"}
        )["result"]
        self.assertNotIn("isError", r)
        self.assertEqual(r["structuredContent"]["threadId"], tid)
        first, second = self.calls()
        self.assertEqual(second["cwd"], str(work))
        for key in [
            "--model",
            "--effort",
            "--agent",
        ]:
            self.assertEqual(
                first["argv"][first["argv"].index(key) + 1],
                second["argv"][second["argv"].index(key) + 1],
            )
        self.assertEqual(
            second["argv"][second["argv"].index("--conversation") + 1], tid
        )

    def test_failed_or_incomplete_turns_never_succeed(self):
        for i, prompt in enumerate(
            [
                "FAIL",
                "FAILTHEN",
                "TRUNC",
                "EOF",
                "EXIT3",
                "EMPTY",
                "WRONG_EFFORT",
                "WRONG_MODEL",
                "WRONG_ID",
            ],
            1,
        ):
            with self.subTest(prompt=prompt):
                r = self.client.call(i, "antigravity", {"prompt": prompt})["result"]
                self.assertTrue(r["isError"])
                self.assertTrue(r["content"][0]["text"])

    def test_missing_effort_metadata_is_not_filled_from_request(self):
        r = self.client.call(1, "antigravity", {"prompt": "NO_METADATA"})["result"]
        self.assertNotIn("isError", r)
        self.assertIsNone(r["structuredContent"]["effort"])

    def test_unknown_thread_and_changed_reply_settings_rejected(self):
        for args in [
            {"threadId": "../escape", "prompt": "x"},
            {"threadId": "00000000-0000-0000-0000-000000000000", "prompt": "x"},
            {
                "threadId": "00000000-0000-0000-0000-000000000000",
                "prompt": "x",
                "effort": "low",
            },
        ]:
            self.assertEqual(
                self.client.call(1, "antigravity-reply", args)["error"]["code"], -32602
            )
        self.assertFalse(self.log.exists())

    def test_stdin_prompt_and_permission_flags(self):
        prompt = "数据\n" * 40000
        r = self.client.call(1, "antigravity", {"prompt": prompt})["result"]
        self.assertNotIn("isError", r)
        call = self.calls()[0]
        self.assertEqual(call["prompt"], prompt)
        self.assertNotIn(prompt, call["argv"])
        self.assertIn("--sandbox", call["argv"])
        self.assertIn("aris-antigravity-review", call["argv"])
        self.assertNotIn("--dangerously-skip-permissions", call["argv"])
        self.assertFalse(list((self.root / "state").glob("prompt-*")))

    def test_ping_progress_and_cancel_while_child_runs(self):
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "antigravity",
                    "arguments": {"prompt": "SLOW"},
                    "_meta": {"progressToken": "p"},
                },
            }
        )
        while True:
            msg = self.client.queue.get(timeout=3)
            if msg.get("method") == "notifications/progress":
                break
        self.client.send({"jsonrpc": "2.0", "id": 11, "method": "ping"})
        self.assertEqual(self.client.recv(11)["result"], {})
        self.client.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 10},
            }
        )
        r = self.client.recv(10)["result"]
        self.assertTrue(r["isError"])
        self.assertIn("cancelled", r["content"][0]["text"])

    def test_cancel_queued_request_never_launches(self):
        def start(rid, prompt):
            self.client.send(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "method": "tools/call",
                    "params": {"name": "antigravity", "arguments": {"prompt": prompt}},
                }
            )

        start(10, "SLOW")
        deadline = time.monotonic() + 3
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        start(20, "QUEUED")
        self.client.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 20},
            }
        )
        # A ping proves B and its cancellation were consumed while A still runs.
        self.client.send({"jsonrpc": "2.0", "id": 30, "method": "ping"})
        self.assertEqual(self.client.recv(30)["result"], {})
        self.assertEqual([c["prompt"] for c in self.calls()], ["SLOW"])
        self.client.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 10},
            }
        )
        self.assertTrue(self.client.recv(10)["result"]["isError"])
        cancelled = self.client.recv(20)["result"]
        self.assertTrue(cancelled.get("isError"), cancelled)
        self.assertIn("cancel", cancelled["content"][0]["text"].lower())
        self.client.send({"jsonrpc": "2.0", "id": 31, "method": "ping"})
        self.assertEqual(self.client.recv(31)["result"], {})
        self.assertNotIn(
            "isError", self.client.call(32, "antigravity", {"prompt": "after"})["result"]
        )
        self.assertEqual([c["prompt"] for c in self.calls()], ["SLOW", "after"])

    def test_timeout_and_host_disconnect_stop_child(self):
        self.client.close()
        self.env["AGY_EXEC_TIMEOUT_SEC"] = "0.15"
        self.client = Client(self.env, self.root)
        r = self.client.call(1, "antigravity", {"prompt": "SLOW"})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("timed out", r["content"][0]["text"])
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "antigravity", "arguments": {"prompt": "SLOW"}},
            }
        )
        self.client.stdin.close()
        r = self.client.recv(2)["result"]
        self.assertTrue(r["isError"])
        self.client.proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
