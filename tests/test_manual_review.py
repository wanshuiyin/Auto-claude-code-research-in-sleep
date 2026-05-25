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
import urllib.error
from pathlib import Path

import pytest

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


# ============================================================
# Test 1: Module import
# ============================================================
def test_import():
    import server as srv
    assert hasattr(srv, "handle_request")
    assert hasattr(srv, "create_thread")
    assert hasattr(srv, "do_review")


# ============================================================
# Test 2: MCP protocol — initialize
# ============================================================
def test_initialize():
    proc = _start_server()
    try:
        _send_jsonrpc(proc, "initialize", {}, req_id=1)
        resp = _read_response(proc)
        assert resp is not None, "no response"
        r = resp.get("result", {})
        assert r.get("protocolVersion") == "2024-11-05", f"wrong protocol: {r.get('protocolVersion')}"
        assert r.get("serverInfo", {}).get("name") == "manual-review", f"wrong server name: {r.get('serverInfo')}"
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ============================================================
# Test 3: MCP protocol — tools/list
# ============================================================
def test_tools_list():
    proc = _start_server()
    try:
        _send_jsonrpc(proc, "initialize", {}, req_id=1)
        _read_response(proc)
        _send_jsonrpc(proc, "tools/list", {}, req_id=2)
        resp = _read_response(proc)
        assert resp is not None, "no response"
        tools = resp.get("result", {}).get("tools", [])
        names = [t["name"] for t in tools]
        assert "review" in names, f"missing 'review' tool: {names}"
        assert "review_reply" in names, f"missing 'review_reply' tool: {names}"
        # Verify schemas
        review_tool = next(t for t in tools if t["name"] == "review")
        required = review_tool["inputSchema"].get("required", [])
        assert "prompt" in required, "'prompt' not required in review schema"
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ============================================================
# Test 4: Thread management
# ============================================================
def test_thread_management():
    import server as srv
    tid = srv.create_thread()
    assert tid and len(tid) == 12, f"bad thread id: {tid}"
    srv.append_exchange(tid, "user", "hello")
    srv.append_exchange(tid, "assistant", "world")
    history = srv.get_history(tid)
    assert len(history) == 2, f"expected 2 entries, got {len(history)}"
    assert history[0]["role"] == "user", f"wrong role: {history[0]}"
    assert history[1]["content"] == "world", f"wrong content: {history[1]}"


import socketserver


# ============================================================
# Test 5: Browser mode — HTTP server serves UI and accepts submit
# ============================================================
def test_browser_mode_http():
    import server as srv

    prompt = "Test review prompt for unit testing"
    config = {"model_reasoning_effort": "xhigh"}
    thread_id = srv.create_thread()

    srv._current_session = srv._ReviewSession(prompt, config, thread_id, [])
    srv._auth_token = "test_token_123"
    server = socketserver.TCPServer(("127.0.0.1", 0), srv._ReviewHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    token = srv._auth_token

    try:
        # Test GET / returns HTML
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/?token={token}")
        html = resp.read().decode("utf-8")
        assert "Manual Review" in html, f"unexpected HTML content"

        # Test GET / without token is rejected (403)
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert exc_info.value.code == 403, f"wrong status: {exc_info.value.code}"

        # Test GET /api/context returns correct JSON
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context?token={token}")
        ctx = json.loads(resp.read().decode("utf-8"))
        assert ctx.get("prompt") == prompt, f"wrong prompt: {ctx.get('prompt')[:50]}"
        assert ctx.get("config", {}).get("model_reasoning_effort") == "xhigh", f"wrong config: {ctx.get('config')}"

        # Test POST /api/submit
        submit_data = json.dumps({"response": "This is the review response"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit?token={token}",
            data=submit_data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode("utf-8"))
        assert result.get("ok"), f"not ok: {result}"
        assert srv._current_session.response == "This is the review response", "response not captured in session"

        # Test POST with empty response is rejected (400)
        submit_empty = json.dumps({"response": ""}).encode("utf-8")
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit?token={token}",
            data=submit_empty,
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info2:
            urllib.request.urlopen(req2)
        assert exc_info2.value.code == 400, f"wrong status: {exc_info2.value.code}"

    finally:
        server.shutdown()
        srv._current_session = None


# ============================================================
# Test 6: File mode — prompt write + response read with stability
# ============================================================
def test_file_mode():
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
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

            result_holder = [None, None]

            def run_file_review():
                r, e = srv.wait_for_file_response(prompt, config, thread_id, [])
                result_holder[0] = r
                result_holder[1] = e

            t = threading.Thread(target=run_file_review, daemon=True)
            t.start()

            # Wait for prompt file to appear (now in per-thread subdir)
            deadline = time.monotonic() + 5
            prompt_path = None
            while time.monotonic() < deadline:
                for p in Path(tmpdir).rglob("prompt.md"):
                    prompt_path = p
                    break
                if prompt_path:
                    break
                time.sleep(0.2)

            assert prompt_path is not None, "prompt.md not created"

            content = prompt_path.read_text(encoding="utf-8")
            assert "File mode test prompt" in content, f"wrong content: {content[:100]}"

            # Simulate user writing response
            response_path = prompt_path.parent / "response.md"
            response_path.write_text("This is the file mode response", encoding="utf-8")

            t.join(timeout=6)
            assert not t.is_alive(), "timed out waiting for file read"
            assert result_holder[1] is None, f"error: {result_holder[1]}"
            assert result_holder[0] == "This is the file mode response", f"wrong: {result_holder[0]}"

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 7: File mode — empty file is NOT accepted
# ============================================================
def test_file_mode_empty_rejected():
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

            # Wait for prompt file to appear (now in per-thread subdir)
            deadline = time.monotonic() + 5
            prompt_path = None
            while time.monotonic() < deadline:
                for p in Path(tmpdir).rglob("prompt.md"):
                    prompt_path = p
                    break
                if prompt_path:
                    break
                time.sleep(0.2)

            assert prompt_path is not None, "prompt.md not created"

            # Create empty response file
            response_path = prompt_path.parent / "response.md"
            response_path.write_text("", encoding="utf-8")

            # Wait a bit — server should NOT accept empty file
            time.sleep(3)

            # Now write actual content
            response_path.write_text("Real response after empty", encoding="utf-8")

            t.join(timeout=5)
            assert not t.is_alive(), "thread still alive"
            assert result_holder[0] == "Real response after empty", \
                f"expected 'Real response after empty', got: {result_holder}"

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 8: handle_request — review tool call with missing prompt
# ============================================================
def test_review_missing_prompt():
    import server as srv
    resp = srv.handle_request({
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "review", "arguments": {"prompt": ""}},
    })
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert "error" in data and "required" in data["error"], f"unexpected: {data}"


# ============================================================
# Test 9: handle_request — review_reply with unknown threadId
# ============================================================
def test_review_reply_unknown_thread():
    import server as srv
    resp = srv.handle_request({
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {"name": "review_reply", "arguments": {"threadId": "nonexistent", "prompt": "hi"}},
    })
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert "error" in data and "Unknown" in data["error"], f"unexpected: {data}"


# ============================================================
# Test 10: Pending state file creation and cleanup
# ============================================================
def test_pending_state():
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        try:
            srv.write_pending_state("http://127.0.0.1:9999", "test123", None)
            # Top-level pointer is written besides per-thread dir
            state_path = Path(tmpdir) / "pending_review.json"
            assert state_path.exists(), "pending_review.json not created"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state["url"] == "http://127.0.0.1:9999", f"wrong url: {state}"
            assert state["thread_id"] == "test123", f"wrong thread_id: {state}"

            srv.clear_pending_state(thread_id="test123")
            assert not state_path.exists(), "pending_review.json not removed"
        finally:
            srv.PENDING_DIR = original_dir


# ============================================================
# Test 11: File mode cancellation (real _cancel_pending_call path)
# ============================================================
def test_file_mode_cancelled():
    import server as srv

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        original_mode = srv.MODE
        srv.MODE = "file"
        original_timeout = srv.DEFAULT_TIMEOUT_SEC
        srv.DEFAULT_TIMEOUT_SEC = 60  # Long timeout, but should be cancelled quickly

        try:
            thread_id = srv.create_thread()
            done = threading.Event()

            def run():
                srv.wait_for_file_response("cancel test", {}, thread_id, [])
                done.set()

            t = threading.Thread(target=run, daemon=True)
            srv._pending_call_thread = t
            t.start()

            # Give the thread time to write prompt.md and start polling
            time.sleep(1.0)

            # Use the real _cancel_pending_call path (not just setting the event)
            success = srv._cancel_pending_call()

            # Thread should exit quickly after cancellation
            assert done.wait(timeout=5), "old file-mode call did not exit after _cancel_pending_call()"
            assert not t.is_alive()
            assert success

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv._pending_call_thread = None
            srv._pending_call_cancelled.clear()


# ============================================================
# Run all tests (script-mode compatibility)
# ============================================================
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
