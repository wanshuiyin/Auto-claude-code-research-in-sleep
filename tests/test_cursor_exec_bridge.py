"""验证 Cursor 桥接的真实 stdio 接线、只读保护、会话固定设置和失败语义。"""

import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "mcp-servers/cursor-exec/server.py"
FAKE = r"""#!/usr/bin/env python3
import json,os,sys,time,signal,uuid
from pathlib import Path
a=sys.argv[1:]
def arg(k):return a[a.index(k)+1]
prompt=sys.stdin.read()
model=arg('--model') if '--model' in a else ''
tid=arg('--resume') if '--resume' in a else str(uuid.uuid4())
policy=Path('.cursor/cli.json')
with open(os.environ['FAKE_CURSOR_LOG'],'a') as f:
 f.write(json.dumps({'argv':a,'prompt':prompt,'cwd':os.getcwd(),'policy':policy.read_text() if policy.exists() else None})+'\n')
def emit(o):print(json.dumps(o),flush=True)
if model=='bad-model':
 sys.stderr.write('Cannot use this model: bad-model. Available models: '+'auto, '*500+'\n')
 sys.exit(1)
if prompt.startswith('ORPHAN_'):
 pid=os.fork()
 if pid==0:
  if prompt=='ORPHAN_STDERR':os.close(1)
  if prompt=='ORPHAN_IGNORE':signal.signal(signal.SIGTERM,signal.SIG_IGN)
  Path(os.environ['FAKE_CURSOR_LOG']+'.pid').write_text(str(os.getpid()))
  time.sleep(8) # finite fallback even when the bridge fails cleanup
  os._exit(0)
 while not Path(os.environ['FAKE_CURSOR_LOG']+'.pid').exists():time.sleep(0.01)
 sys.exit(0)
if prompt in ['NOID','NOID_FAIL']:
 emit({'type':'system','subtype':'init','model':'Fake Model'})
 emit({'type':'result','subtype':'error' if prompt=='NOID_FAIL' else 'success','is_error':prompt=='NOID_FAIL','result':'provider unavailable' if prompt=='NOID_FAIL' else 'echo:NOID'})
 sys.exit(1 if prompt=='NOID_FAIL' else 0)
if prompt=='OTHERID':tid=str(uuid.uuid4())
emit({'type':'system','subtype':'init','apiKeySource':'login','cwd':os.getcwd(),'session_id':tid,'model':'Fake Model','permissionMode':'default'})
emit({'type':'user','message':{'role':'user','content':[{'type':'text','text':prompt[:20]}]},'session_id':tid})
if prompt=='SLOW':
 signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
 time.sleep(30)
if prompt=='EOF':sys.exit(0)
for word in ['The',' user','wants']:
 emit({'type':'thinking','subtype':'delta','text':word,'session_id':tid})
emit({'type':'thinking','subtype':'completed','session_id':tid})
if prompt in ['FAIL','FAILTHEN']:
 emit({'type':'result','subtype':'error','is_error':True,'result':'provider unavailable','session_id':tid})
 if prompt=='FAIL':sys.exit(1)
emit({'type':'assistant','message':{'role':'assistant','content':[{'type':'text','text':'echo:'+prompt[:20]}]},'session_id':tid})
emit({'type':'result','subtype':'success','is_error':False,'result':'' if prompt=='EMPTY' else 'echo:'+prompt,'session_id':tid})
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
        for i, msg in enumerate(self.notifications):
            if msg.get("id") == rid:
                return self.notifications.pop(i)
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
        self.tmp = tempfile.TemporaryDirectory(prefix="cursor-exec-test-")
        self.root = Path(self.tmp.name).resolve()
        fake = self.root / "cursor-agent"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.state = self.root / "state"
        self.env = dict(
            os.environ,
            CURSOR_AGENT_BIN=str(fake),
            CURSOR_EXEC_STATE_DIR=str(self.state),
            CURSOR_EXEC_PROGRESS_INTERVAL_SEC="0.05",
            CURSOR_EXEC_TIMEOUT_SEC="5",
            FAKE_CURSOR_LOG=str(self.log),
        )
        self.env.pop("CURSOR_EXEC_MODEL", None)
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
            self.client.recv(1)["result"]["serverInfo"]["name"], "cursor-exec"
        )
        self.client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            {t["name"] for t in self.client.recv(2)["result"]["tools"]},
            {"cursor", "cursor-reply"},
        )
        work = self.root / "work"
        work.mkdir()
        r = self.client.call(3, "cursor", {"prompt": "hello", "cwd": str(work)})[
            "result"
        ]
        self.assertNotIn("isError", r)
        self.assertEqual(r["content"][0]["text"], "echo:hello")
        s = r["structuredContent"]
        self.assertEqual(s["model"], "Fake Model")
        self.assertEqual(s["requestedModel"], "")
        self.assertEqual(s["content"], "echo:hello")
        self.assertTrue(uuid.UUID(s["threadId"]))

    def test_read_only_invocation_contract(self):
        work = self.root / "work"
        work.mkdir()
        self.client.call(1, "cursor", {"prompt": "hello", "cwd": str(work)})
        call = self.calls()[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "ask")
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
        self.assertEqual(argv[argv.index("--workspace") + 1], str(work))
        self.assertIn("-p", argv)
        self.assertIn("--trust", argv)
        # 没有请求模型时不传 --model，由 cursor-agent 自己的默认值决定
        self.assertNotIn("--model", argv)
        for forbidden in ["--force", "-f", "--yolo", "--approve-mcps", "--api-key"]:
            self.assertNotIn(forbidden, argv)
        # 子进程在私有 guard 目录运行，被评审的项目目录里不会出现桥接写的文件
        self.assertEqual(call["cwd"], str((self.state / "guard").resolve()))
        self.assertEqual(os.listdir(work), [])
        deny = json.loads(call["policy"])["permissions"]["deny"]
        for rule in ["Write(**)", "Shell(**)", "Mcp(*:*)"]:
            self.assertIn(rule, deny)

    def test_guard_policy_is_restored_before_every_call(self):
        self.client.call(1, "cursor", {"prompt": "one"})
        policy = self.state / "guard" / ".cursor" / "cli.json"
        policy.write_text('{"permissions":{"allow":["Shell(**)"],"deny":[]}}')
        self.client.call(2, "cursor", {"prompt": "two"})
        first, second = self.calls()
        self.assertEqual(first["policy"], second["policy"])
        self.assertEqual(os.listdir(policy.parent), ["cli.json"])
        self.assertIn("Write(**)", json.loads(second["policy"])["permissions"]["deny"])

    def test_resume_keeps_settings_after_server_restart(self):
        work = self.root / "work"
        work.mkdir()
        tid = self.client.call(
            1, "cursor", {"prompt": "first", "model": "fake-model", "cwd": str(work)}
        )["result"]["structuredContent"]["threadId"]
        self.client.close()
        self.env["CURSOR_EXEC_MODEL"] = "other-model"
        self.client = Client(self.env, self.root)
        r = self.client.call(2, "cursor-reply", {"threadId": tid, "prompt": "second"})[
            "result"
        ]
        self.assertNotIn("isError", r)
        self.assertEqual(r["structuredContent"]["threadId"], tid)
        self.assertEqual(r["structuredContent"]["requestedModel"], "fake-model")
        first, second = self.calls()
        for key in ["--model", "--workspace"]:
            self.assertEqual(
                first["argv"][first["argv"].index(key) + 1],
                second["argv"][second["argv"].index(key) + 1],
            )
        self.assertEqual(second["argv"][second["argv"].index("--resume") + 1], tid)
        self.assertNotIn("--resume", first["argv"])
        self.assertEqual(second["cwd"], first["cwd"])

    def test_failed_or_incomplete_turns_never_succeed(self):
        for i, prompt in enumerate(["FAIL", "FAILTHEN", "EOF", "EXIT3", "EMPTY"], 1):
            with self.subTest(prompt=prompt):
                r = self.client.call(i, "cursor", {"prompt": prompt})["result"]
                self.assertTrue(r["isError"])
                self.assertTrue(r["content"][0]["text"])

    def test_bad_model_surfaces_the_cli_reason(self):
        r = self.client.call(1, "cursor", {"prompt": "x", "model": "bad-model"})[
            "result"
        ]
        self.assertTrue(r["isError"])
        text = r["content"][0]["text"]
        self.assertIn("Cannot use this model: bad-model", text)
        self.assertLess(len(text), 1100)

    def test_missing_binary_is_a_clean_tool_error(self):
        self.client.close()
        self.env["CURSOR_AGENT_BIN"] = str(self.root / "no-such-binary")
        self.client = Client(self.env, self.root)
        r = self.client.call(1, "cursor", {"prompt": "x"})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("could not start", r["content"][0]["text"])

    def test_unknown_thread_and_changed_reply_settings_rejected(self):
        for args in [
            {"threadId": "../escape", "prompt": "x"},
            {"threadId": "00000000-0000-0000-0000-000000000000", "prompt": "x"},
            {
                "threadId": "00000000-0000-0000-0000-000000000000",
                "prompt": "x",
                "model": "other",
            },
        ]:
            self.assertEqual(
                self.client.call(1, "cursor-reply", args)["error"]["code"], -32602
            )
        for args in [
            {"prompt": "x", "sandbox": "off"},
            {"prompt": "x", "cwd": "/no/dir"},
        ]:
            self.assertEqual(
                self.client.call(2, "cursor", args)["error"]["code"], -32602
            )
        self.assertFalse(self.log.exists())

    def test_reply_with_a_different_session_id_is_an_error(self):
        tid = self.client.call(1, "cursor", {"prompt": "first"})["result"][
            "structuredContent"
        ]["threadId"]
        r = self.client.call(2, "cursor-reply", {"threadId": tid, "prompt": "OTHERID"})[
            "result"
        ]
        self.assertTrue(r["isError"])
        self.assertIn("different session id", r["content"][0]["text"])

    def test_long_prompt_goes_over_stdin_and_thinking_deltas_stay_local(self):
        prompt = "数据\n" * 40000
        r = self.client.call(1, "cursor", {"prompt": prompt})["result"]
        self.assertNotIn("isError", r)
        call = self.calls()[0]
        self.assertEqual(call["prompt"], prompt)
        self.assertFalse(any(prompt[:50] in part for part in call["argv"]))
        events = [
            n["params"]["msg"]
            for n in self.client.notifications
            if n.get("method") == "cursor/event"
        ]
        kinds = {(e["type"], e.get("subtype")) for e in events}
        self.assertIn(("assistant", None), kinds)
        self.assertIn(("thinking", "completed"), kinds)
        self.assertNotIn(("thinking", "delta"), kinds)

    def test_ping_progress_and_cancel_while_child_runs(self):
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "cursor",
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
                    "params": {"name": "cursor", "arguments": {"prompt": prompt}},
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
            "isError", self.client.call(32, "cursor", {"prompt": "after"})["result"]
        )
        self.assertEqual([c["prompt"] for c in self.calls()], ["SLOW", "after"])

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_exited_launcher_descendants_are_cleaned_up(self):
        for prompt in ["ORPHAN_STDERR", "ORPHAN_STDOUT", "ORPHAN_IGNORE"]:
            with self.subTest(prompt=prompt):
                self.client.close()
                pidfile = Path(str(self.log) + ".pid")
                pidfile.unlink(missing_ok=True)
                self.env["CURSOR_EXEC_TIMEOUT_SEC"] = "0.5"
                self.client = Client(self.env, self.root)
                pid = None
                cleaned = False
                try:
                    started = time.monotonic()
                    result = self.client.call(1, "cursor", {"prompt": prompt})["result"]
                    self.assertLess(time.monotonic() - started, 4)
                    self.assertTrue(result.get("isError"), result)
                    pid = int(pidfile.read_text())
                    deadline = time.monotonic() + 1
                    while True:
                        state = subprocess.run(
                            ["ps", "-o", "stat=", "-p", str(pid)],
                            check=False,
                            capture_output=True,
                            text=True,
                        ).stdout.strip()
                        if not state or state.startswith("Z"):
                            cleaned = True
                            break
                        self.assertLess(
                            time.monotonic(), deadline, "descendant remains alive"
                        )
                        time.sleep(0.02)
                finally:
                    if pid is None and pidfile.exists():
                        pid = int(pidfile.read_text())
                    if pid is not None and not cleaned:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_reply_requires_a_session_id_observed_in_this_turn(self):
        tid = self.client.call(1, "cursor", {"prompt": "first"})["result"][
            "structuredContent"
        ]["threadId"]
        result = self.client.call(
            2, "cursor-reply", {"threadId": tid, "prompt": "NOID"}
        )["result"]
        self.assertTrue(result.get("isError"), result)
        self.assertIn("session", result["content"][0]["text"].lower())
        failed = self.client.call(
            3, "cursor-reply", {"threadId": tid, "prompt": "NOID_FAIL"}
        )["result"]
        self.assertTrue(failed["isError"])
        self.assertIn("provider unavailable", failed["content"][0]["text"])
        self.assertEqual(failed["structuredContent"]["threadId"], tid)

    def test_timeout_and_host_disconnect_stop_child(self):
        self.client.close()
        self.env["CURSOR_EXEC_TIMEOUT_SEC"] = "0.15"
        self.client = Client(self.env, self.root)
        r = self.client.call(1, "cursor", {"prompt": "SLOW"})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("timed out", r["content"][0]["text"])
        self.client.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "cursor", "arguments": {"prompt": "SLOW"}},
            }
        )
        self.client.stdin.close()
        r = self.client.recv(2)["result"]
        self.assertTrue(r["isError"])
        self.client.proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
