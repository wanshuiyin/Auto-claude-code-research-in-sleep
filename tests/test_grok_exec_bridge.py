"""验证 Grok 桥接的真实 stdio 接线、会话固定设置和失败语义。"""

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

SERVER = Path(__file__).resolve().parents[1] / "mcp-servers/grok-exec/server.py"
FAKE = r"""#!/usr/bin/env python3
import json,os,sys,time,signal
from pathlib import Path
from urllib.parse import quote
a=sys.argv[1:]
def arg(k):return a[a.index(k)+1]
prompt=Path(arg('--prompt-file')).read_text()
tid=arg('--resume') if '--resume' in a else arg('--session-id')
with open(os.environ['FAKE_GROK_LOG'],'a') as f:
 f.write(json.dumps({'argv':a,'prompt':prompt,'cwd':os.getcwd()})+'\n')
def emit(o):print(json.dumps(o),flush=True)
effort='high' if prompt=='WRONG_EFFORT' else arg('--reasoning-effort')
p=Path(os.environ['GROK_HOME'])/'sessions'/quote(os.getcwd(),safe='')/tid
p.mkdir(parents=True,exist_ok=True)
(p/'summary.json').write_text(json.dumps({'reasoning_effort':effort}))
emit({'type':'system','subtype':'init','session_id':tid,'model':arg('--model')})
if prompt=='SLOW':
 signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
 time.sleep(30)
if prompt=='EOF':sys.exit(0)
if prompt in ['FAIL','FAILTHEN']:
 emit({'type':'result','subtype':'error','is_error':True,'result':'provider unavailable','session_id':tid})
 if prompt=='FAIL':sys.exit(1)
emit({'type':'assistant','message':{'model':'grok-4.7-build'}})
emit({'type':'result','subtype':'success','is_error':False,'result':'' if prompt=='EMPTY' else 'echo:'+prompt,'session_id':tid,'stop_reason':'max_tokens' if prompt=='TRUNC' else 'end_turn','modelUsage':{'grok-4.7-build':{}}})
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
        self.tmp = tempfile.TemporaryDirectory(prefix="grok-exec-test-")
        self.root = Path(self.tmp.name).resolve()
        fake = self.root / "grok"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.env = dict(
            os.environ,
            GROK_BIN=str(fake),
            GROK_EXEC_STATE_DIR=str(self.root / "state"),
            GROK_EXEC_PROGRESS_INTERVAL_SEC="0.05",
            GROK_EXEC_TIMEOUT_SEC="5",
            GROK_HOME=str(self.root / "grok-home"),
            FAKE_GROK_LOG=str(self.log),
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
            self.client.recv(1)["result"]["serverInfo"]["name"], "grok-exec"
        )
        self.client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            {t["name"] for t in self.client.recv(2)["result"]["tools"]},
            {"grok", "grok-reply"},
        )
        r = self.client.call(3, "grok", {"prompt": "hello"})["result"]
        self.assertNotIn("isError", r)
        self.assertEqual(r["content"][0]["text"], "echo:hello")
        s = r["structuredContent"]
        self.assertEqual(s["effort"], "xhigh")
        self.assertEqual(s["model"], "grok-4.7-build")
        self.assertEqual(s["requestedModel"], "grok-4.7")
        self.assertEqual(s["content"], "echo:hello")

    def test_resume_keeps_settings_after_server_restart(self):
        work = self.root / "work"
        work.mkdir()
        tid = self.client.call(
            1,
            "grok",
            {
                "prompt": "first",
                "model": "grok-4.7",
                "effort": "xhigh",
                "tools": "",
                "sandbox": "read-only",
                "max_turns": 7,
                "cwd": str(work),
            },
        )["result"]["structuredContent"]["threadId"]
        self.client.close()
        self.env["GROK_EXEC_EFFORT"] = "low"
        self.client = Client(self.env, self.root)
        r = self.client.call(2, "grok-reply", {"threadId": tid, "prompt": "second"})[
            "result"
        ]
        self.assertNotIn("isError", r)
        self.assertEqual(r["structuredContent"]["threadId"], tid)
        first, second = self.calls()
        self.assertEqual(second["cwd"], str(work))
        for key in [
            "--model",
            "--reasoning-effort",
            "--sandbox",
            "--tools",
            "--max-turns",
            "--cwd",
        ]:
            self.assertEqual(
                first["argv"][first["argv"].index(key) + 1],
                second["argv"][second["argv"].index(key) + 1],
            )
        self.assertEqual(second["argv"][second["argv"].index("--resume") + 1], tid)

    def test_failed_or_incomplete_turns_never_succeed(self):
        for i, prompt in enumerate(
            ["FAIL", "FAILTHEN", "TRUNC", "EOF", "EXIT3", "EMPTY", "WRONG_EFFORT"], 1
        ):
            with self.subTest(prompt=prompt):
                r = self.client.call(i, "grok", {"prompt": prompt})["result"]
                self.assertTrue(r["isError"])
                self.assertTrue(r["content"][0]["text"])

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
                self.client.call(1, "grok-reply", args)["error"]["code"], -32602
            )
        self.assertFalse(self.log.exists())

    def test_long_prompt_file_and_no_unrequested_tool_access(self):
        prompt = "数据\n" * 40000
        r = self.client.call(1, "grok", {"prompt": prompt, "tools": ""})["result"]
        self.assertNotIn("isError", r)
        call = self.calls()[0]
        self.assertEqual(call["prompt"], prompt)
        self.assertNotIn(prompt, call["argv"])
        self.assertIn("--no-subagents", call["argv"])
        self.assertIn("MCPTool", call["argv"])
        self.assertFalse(list((self.root / "state").glob("prompt-*")))

    def test_ping_progress_and_cancel_while_child_runs(self):
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "grok",
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
                    "params": {"name": "grok", "arguments": {"prompt": prompt}},
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
            "isError", self.client.call(32, "grok", {"prompt": "after"})["result"]
        )
        self.assertEqual([c["prompt"] for c in self.calls()], ["SLOW", "after"])

    def test_timeout_and_host_disconnect_stop_child(self):
        self.client.close()
        self.env["GROK_EXEC_TIMEOUT_SEC"] = "0.15"
        self.client = Client(self.env, self.root)
        r = self.client.call(1, "grok", {"prompt": "SLOW"})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("timed out", r["content"][0]["text"])
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "grok", "arguments": {"prompt": "SLOW"}},
            }
        )
        self.client.stdin.close()
        r = self.client.recv(2)["result"]
        self.assertTrue(r["isError"])
        self.client.proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
