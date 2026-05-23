"""Tests for manual-review MCP server.

Covers:
1. MCP protocol (initialize, tools/list, tool call format)
2. Browser mode (HTTP server + submit flow)
3. File mode (prompt.md / response.md exchange with stability check)
4. Thread management (review + review_reply continuity)
5. Error handling (empty response, missing threadId, timeout)
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

# Add the server directory to path for import
SERVER_DIR = Path(__file__).parent.parent / "mcp-servers" / "manual-review"
sys.path.insert(0, str(SERVER_DIR))

# Prevent auto-open browser during tests
os.environ["MANUAL_REVIEW_AUTO_OPEN"] = "false"
os.environ["MANUAL_REVIEW_TIMEOUT_SEC"] = "10"


def _send_jsonrpc(proc, method, params=None, req_id=1):
    """Send a JSON-RPC message to the server process via stdin."""
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params
    payload = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
    proc.stdin.write(header + payload)
    proc.stdin.flush()


def _read_response(proc, timeout=5):
    """Read a JSON-RPC response from the server process stdout."""
    import select
    deadline = time.monotonic() + timeout
    header = b""
    while time.monotonic() < deadline:
        byte = proc.stdout.read(1)
        if not byte:
            break
        header += byte
        if header.endswith(b"\r\n\r\n"):
            break
    content_length = 0
    for line in header.decode("utf-8").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
    if content_length == 0:
        return None
    body = proc.stdout.read(content_length)
    return json.loads(body.decode("utf-8"))


def _start_server():
    """Start the MCP server as a subprocess."""
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_DIR / "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "MANUAL_REVIEW_AUTO_OPEN": "false", "MANUAL_REVIEW_TIMEOUT_SEC": "10"},
    )
    return proc


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  PASS: {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  FAIL: {name} — {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailures:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        return self.failed == 0


# ============================================================
# Test 1: Module import
# ============================================================
def test_import(results):
    try:
        import server as srv
        assert hasattr(srv, "handle_request")
        assert hasattr(srv, "create_thread")
        assert hasattr(srv, "do_review")
        results.ok("module imports cleanly")
    except Exception as e:
        results.fail("module imports cleanly", str(e))


# ============================================================
# Test 2: MCP protocol — initialize
# ============================================================
def test_initialize(results):
    proc = _start_server()
    try:
        _send_jsonrpc(proc, "initialize", {}, req_id=1)
        resp = _read_response(proc)
        if resp is None:
            results.fail("initialize", "no response")
            return
        r = resp.get("result", {})
        if r.get("protocolVersion") != "2024-11-05":
            results.fail("initialize", f"wrong protocol: {r.get('protocolVersion')}")
        elif r.get("serverInfo", {}).get("name") != "manual-review":
            results.fail("initialize", f"wrong server name: {r.get('serverInfo')}")
        else:
            results.ok("initialize returns correct protocol and server info")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ============================================================
# Test 3: MCP protocol — tools/list
# ============================================================
def test_tools_list(results):
    proc = _start_server()
    try:
        _send_jsonrpc(proc, "initialize", {}, req_id=1)
        _read_response(proc)
        _send_jsonrpc(proc, "tools/list", {}, req_id=2)
        resp = _read_response(proc)
        if resp is None:
            results.fail("tools/list", "no response")
            return
        tools = resp.get("result", {}).get("tools", [])
        names = [t["name"] for t in tools]
        if "review" not in names:
            results.fail("tools/list", f"missing 'review' tool: {names}")
        elif "review_reply" not in names:
            results.fail("tools/list", f"missing 'review_reply' tool: {names}")
        else:
            # Verify schemas
            review_tool = next(t for t in tools if t["name"] == "review")
            required = review_tool["inputSchema"].get("required", [])
            if "prompt" not in required:
                results.fail("tools/list", "'prompt' not required in review schema")
            else:
                results.ok("tools/list returns both tools with correct schemas")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ============================================================
# Test 4: Thread management
# ============================================================
def test_thread_management(results):
    import server as srv
    tid = srv.create_thread()
    if not tid or len(tid) != 12:
        results.fail("thread creation", f"bad thread id: {tid}")
        return
    srv.append_exchange(tid, "user", "hello")
    srv.append_exchange(tid, "assistant", "world")
    history = srv.get_history(tid)
    if len(history) != 2:
        results.fail("thread management", f"expected 2 entries, got {len(history)}")
    elif history[0]["role"] != "user" or history[1]["content"] != "world":
        results.fail("thread management", f"wrong content: {history}")
    else:
        results.ok("thread creation and history tracking")


# ============================================================
# Test 5: Browser mode — HTTP server serves UI and accepts submit
# ============================================================
def test_browser_mode_http(results):
    import server as srv

    # Simulate a review call in a thread
    prompt = "Test review prompt for unit testing"
    config = {"model_reasoning_effort": "xhigh"}
    thread_id = srv.create_thread()

    # Start the HTTP server in background (same as wait_for_browser_response but manual)
    srv._current_session = srv._ReviewSession(prompt, config, thread_id, [])
    server = socketserver.TCPServer(("127.0.0.1", 0), srv._ReviewHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Test GET / returns HTML
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        html = resp.read().decode("utf-8")
        if "Manual Review" not in html:
            results.fail("HTTP serves UI", f"unexpected HTML content")
            return
        results.ok("HTTP GET / serves ui.html")

        # Test GET /api/context returns correct JSON
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context")
        ctx = json.loads(resp.read().decode("utf-8"))
        if ctx.get("prompt") != prompt:
            results.fail("HTTP /api/context", f"wrong prompt: {ctx.get('prompt')[:50]}")
            return
        if ctx.get("config", {}).get("model_reasoning_effort") != "xhigh":
            results.fail("HTTP /api/context", f"wrong config: {ctx.get('config')}")
            return
        results.ok("HTTP GET /api/context returns correct data")

        # Test POST /api/submit
        submit_data = json.dumps({"response": "This is the review response"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit",
            data=submit_data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            results.fail("HTTP POST /api/submit", f"not ok: {result}")
            return
        # Verify the session captured the response
        if srv._current_session.response != "This is the review response":
            results.fail("HTTP POST /api/submit", "response not captured in session")
            return
        results.ok("HTTP POST /api/submit captures response correctly")

        # Test POST with empty response is rejected
        submit_empty = json.dumps({"response": ""}).encode("utf-8")
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit",
            data=submit_empty,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req2)
            results.fail("HTTP rejects empty response", "should have returned 400")
        except urllib.error.HTTPError as e:
            if e.code == 400:
                results.ok("HTTP POST /api/submit rejects empty response")
            else:
                results.fail("HTTP rejects empty response", f"wrong status: {e.code}")

    finally:
        server.shutdown()
        srv._current_session = None


import socketserver


# ============================================================
# Test 6: File mode — prompt write + response read with stability
# ============================================================
def test_file_mode(results):
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
        # Override pending dir
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        original_mode = srv.MODE
        srv.MODE = "file"
        original_timeout = srv.DEFAULT_TIMEOUT_SEC
        srv.DEFAULT_TIMEOUT_SEC = 8
        original_stable = srv.FILE_STABLE_INTERVAL_SEC
        srv.FILE_STABLE_INTERVAL_SEC = 1
        original_poll = srv.FILE_POLL_INTERVAL_SEC
        srv.FILE_POLL_INTERVAL_SEC = 1

        try:
            prompt = "File mode test prompt"
            config = {"model_reasoning_effort": "xhigh"}
            thread_id = srv.create_thread()

            # Start file mode in background thread
            result_holder = [None, None]

            def run_file_review():
                r, e = srv.wait_for_file_response(prompt, config, thread_id, [])
                result_holder[0] = r
                result_holder[1] = e

            t = threading.Thread(target=run_file_review, daemon=True)
            t.start()

            # Wait for prompt file to appear
            prompt_path = Path(tmpdir) / "prompt.md"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not prompt_path.exists():
                time.sleep(0.2)

            if not prompt_path.exists():
                results.fail("file mode writes prompt", "prompt.md not created")
                return

            content = prompt_path.read_text(encoding="utf-8")
            if "File mode test prompt" not in content:
                results.fail("file mode writes prompt", f"wrong content: {content[:100]}")
                return
            results.ok("file mode writes prompt.md correctly")

            # Simulate user writing response (with stability requirement)
            response_path = Path(tmpdir) / "response.md"
            response_path.write_text("This is the file mode response", encoding="utf-8")

            # Wait for the thread to complete
            t.join(timeout=6)
            if t.is_alive():
                results.fail("file mode reads response", "timed out waiting for file read")
                return

            if result_holder[1] is not None:
                results.fail("file mode reads response", f"error: {result_holder[1]}")
                return
            if result_holder[0] != "This is the file mode response":
                results.fail("file mode reads response", f"wrong: {result_holder[0]}")
                return
            results.ok("file mode reads response.md with stability check")

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 7: File mode — empty file is NOT accepted
# ============================================================
def test_file_mode_empty_rejected(results):
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        original_mode = srv.MODE
        srv.MODE = "file"
        original_timeout = srv.DEFAULT_TIMEOUT_SEC
        srv.DEFAULT_TIMEOUT_SEC = 5
        original_stable = srv.FILE_STABLE_INTERVAL_SEC
        srv.FILE_STABLE_INTERVAL_SEC = 1
        original_poll = srv.FILE_POLL_INTERVAL_SEC
        srv.FILE_POLL_INTERVAL_SEC = 1

        try:
            thread_id = srv.create_thread()
            result_holder = [None, None]

            def run():
                r, e = srv.wait_for_file_response("test", {}, thread_id, [])
                result_holder[0] = r
                result_holder[1] = e

            t = threading.Thread(target=run, daemon=True)
            t.start()

            # Wait for prompt to be written
            time.sleep(1.5)

            # Create empty response file (simulating user creating file first)
            response_path = Path(tmpdir) / "response.md"
            response_path.write_text("", encoding="utf-8")

            # Wait a bit — server should NOT accept empty file
            time.sleep(3)

            # Now write actual content
            response_path.write_text("Real response after empty", encoding="utf-8")

            t.join(timeout=5)
            if t.is_alive():
                # Timeout means it correctly ignored the empty file but may have timed out
                results.fail("file mode rejects empty", "thread still alive")
                return

            if result_holder[0] == "Real response after empty":
                results.ok("file mode ignores empty file, accepts non-empty content")
            elif result_holder[1] and "Timed out" in result_holder[1]:
                results.fail("file mode rejects empty", "timed out before reading real content")
            else:
                results.fail("file mode rejects empty", f"unexpected: {result_holder}")

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 8: handle_request — review tool call with missing prompt
# ============================================================
def test_review_missing_prompt(results):
    import server as srv
    resp = srv.handle_request({
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "review", "arguments": {"prompt": ""}},
    })
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    if "error" in data and "required" in data["error"]:
        results.ok("review rejects empty prompt")
    else:
        results.fail("review rejects empty prompt", f"unexpected: {data}")


# ============================================================
# Test 9: handle_request — review_reply with unknown threadId
# ============================================================
def test_review_reply_unknown_thread(results):
    import server as srv
    resp = srv.handle_request({
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {"name": "review_reply", "arguments": {"threadId": "nonexistent", "prompt": "hi"}},
    })
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    if "error" in data and "Unknown" in data["error"]:
        results.ok("review_reply rejects unknown threadId")
    else:
        results.fail("review_reply rejects unknown threadId", f"unexpected: {data}")


# ============================================================
# Test 10: Pending state file creation and cleanup
# ============================================================
def test_pending_state(results):
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        try:
            srv.write_pending_state("http://127.0.0.1:9999", "test123", None)
            state_path = Path(tmpdir) / "pending_review.json"
            if not state_path.exists():
                results.fail("pending state write", "file not created")
                return
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["url"] != "http://127.0.0.1:9999" or state["thread_id"] != "test123":
                results.fail("pending state write", f"wrong content: {state}")
                return
            results.ok("pending state file written correctly")

            srv.clear_pending_state()
            if state_path.exists():
                results.fail("pending state cleanup", "file not removed")
            else:
                results.ok("pending state cleanup works")
        finally:
            srv.PENDING_DIR = original_dir


# ============================================================
# Run all tests
# ============================================================
if __name__ == "__main__":
    print("Manual Review MCP Server — Test Suite")
    print("=" * 50)

    results = TestResults()

    print("\n[Module Import]")
    test_import(results)

    print("\n[MCP Protocol]")
    test_initialize(results)
    test_tools_list(results)

    print("\n[Thread Management]")
    test_thread_management(results)

    print("\n[Browser Mode — HTTP]")
    test_browser_mode_http(results)

    print("\n[File Mode]")
    test_file_mode(results)
    test_file_mode_empty_rejected(results)

    print("\n[Error Handling]")
    test_review_missing_prompt(results)
    test_review_reply_unknown_thread(results)

    print("\n[State Management]")
    test_pending_state(results)

    success = results.summary()
    sys.exit(0 if success else 1)
