"""Tests for manual-review MCP server.

Covers:
1. MCP protocol (initialize, tools/list, tool call format)
2. Browser mode (HTTP server + submit flow)
3. File mode (prompt.md / response.md exchange with stability check + cross-model warning)
4. Thread management (review + review_reply continuity)
5. Error handling (empty response, missing threadId, timeout)
6. Cancellation (notifications/cancelled, per-call state)
7. Concurrency (fail-fast on second review)
"""

import importlib.util
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

# Set env BEFORE loading the server: server.py reads MANUAL_REVIEW_AUTO_OPEN
# and MANUAL_REVIEW_TIMEOUT_SEC at import time into module constants, so these
# must be in place before exec_module (the old per-test `import server` ran
# after this block; loading once at module level does not).
os.environ["MANUAL_REVIEW_AUTO_OPEN"] = "false"   # no browser popup in tests
os.environ["MANUAL_REVIEW_TIMEOUT_SEC"] = "10"

# Load the server by explicit path under a UNIQUE module name. A bare
# `import server` is unsafe here: every mcp-server is named server.py, and
# sibling test modules (e.g. test_minimax_chat_server) do
# `sys.path.insert(0, <their-server-dir>)` at collection time — so by the time
# these tests run, a bare `import server` can resolve to the wrong server and
# fail with AttributeError. spec_from_file_location sidesteps sys.path entirely.
SERVER_DIR = Path(__file__).parent.parent / "mcp-servers" / "manual-review"
_SRV_SPEC = importlib.util.spec_from_file_location(
    "manual_review_server", SERVER_DIR / "server.py")
assert _SRV_SPEC and _SRV_SPEC.loader
srv = importlib.util.module_from_spec(_SRV_SPEC)
_SRV_SPEC.loader.exec_module(srv)


def _send_jsonrpc(proc, method, params=None, req_id=1):
    """Send a JSON-RPC message to the server process via stdin."""
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params
    payload = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
    proc.stdin.write(header + payload)
    proc.stdin.flush()


def _send_notification(proc, method, params=None):
    """Send a JSON-RPC notification (no id field) to the server process."""
    msg = {"jsonrpc": "2.0", "method": method}
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


_next_test_port = 27900


def _start_server(**extra_env):
    """Start the MCP server as a subprocess with a unique port."""
    global _next_test_port
    port = _next_test_port
    _next_test_port += 1
    env = {
        **os.environ,
        "MANUAL_REVIEW_AUTO_OPEN": "false",
        "MANUAL_REVIEW_TIMEOUT_SEC": "10",
        "MANUAL_REVIEW_PORT": str(port),
        **extra_env,
    }
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_DIR / "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return proc


# ============================================================
# Test 1: Module import
# ============================================================
def test_import():
    assert hasattr(srv, "handle_request")
    assert hasattr(srv, "create_thread")
    assert hasattr(srv, "do_review")
    assert hasattr(srv, "_PendingCall")
    assert hasattr(srv, "_cancel_active_call")


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
        assert r.get("protocolVersion") == "2024-11-05"
        assert r.get("serverInfo", {}).get("name") == "manual-review"
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
        assert "review" in names, f"missing 'review': {names}"
        assert "review_reply" in names, f"missing 'review_reply': {names}"
        review_tool = next(t for t in tools if t["name"] == "review")
        required = review_tool["inputSchema"].get("required", [])
        assert "prompt" in required, "'prompt' not required"
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ============================================================
# Test 4: Thread management
# ============================================================
def test_thread_management():
    tid = srv.create_thread()
    assert tid and len(tid) == 12, f"bad thread id: {tid}"
    srv.append_exchange(tid, "user", "hello")
    srv.append_exchange(tid, "assistant", "world")
    history = srv.get_history(tid)
    assert len(history) == 2, f"expected 2 entries, got {len(history)}"
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "world"


import socketserver


# ============================================================
# Test 5: Browser mode — HTTP server + submit flow
# ============================================================
def test_browser_mode_http():

    prompt = "Test review prompt for unit testing"
    config = {"model_reasoning_effort": "xhigh"}
    thread_id = srv.create_thread()

    srv._current_session = srv._ReviewSession(prompt, config, thread_id, [])
    srv._auth_token = "test_token_123_test_token_123"  # full uuid hex
    server = socketserver.TCPServer(("127.0.0.1", 0), srv._ReviewHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    token = srv._auth_token

    try:
        # GET / returns HTML
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/?token={token}")
        html = resp.read().decode("utf-8")
        assert "Manual Review" in html

        # GET / without token → 403
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert exc.value.code == 403

        # GET / with bad Origin → 403
        req_origin = urllib.request.Request(
            f"http://127.0.0.1:{port}/?token={token}",
            headers={"Origin": "http://evil.com"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc2:
            urllib.request.urlopen(req_origin)
        assert exc2.value.code == 403

        # GET / with cross-site Sec-Fetch-Site → 403
        req_fetch = urllib.request.Request(
            f"http://127.0.0.1:{port}/?token={token}",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc3:
            urllib.request.urlopen(req_fetch)
        assert exc3.value.code == 403

        # OPTIONS → 403
        req_options = urllib.request.Request(
            f"http://127.0.0.1:{port}/?token={token}", method="OPTIONS",
        )
        with pytest.raises(urllib.error.HTTPError) as exc4:
            urllib.request.urlopen(req_options)
        assert exc4.value.code == 403

        # GET /api/context with valid token + same-origin → 200
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/context?token={token}",
        )
        ctx = json.loads(resp.read().decode("utf-8"))
        assert ctx.get("prompt") == prompt
        assert ctx.get("config", {}).get("model_reasoning_effort") == "xhigh"
        # Response headers must NOT contain Access-Control-Allow-Origin
        assert "Access-Control-Allow-Origin" not in str(resp.headers)

        # POST /api/submit with valid token → 200
        submit_data = json.dumps({"response": "This is the review response"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit?token={token}",
            data=submit_data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode("utf-8"))
        assert result.get("ok")
        assert srv._current_session.response == "This is the review response"

        # POST empty → 400
        submit_empty = json.dumps({"response": ""}).encode("utf-8")
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/submit?token={token}",
            data=submit_empty,
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc5:
            urllib.request.urlopen(req2)
        assert exc5.value.code == 400

    finally:
        server.shutdown()
        srv._current_session = None


# ============================================================
# Test 6: File mode — prompt + response + cross-model warning
# ============================================================
def test_file_mode():

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
            cancel_evt = threading.Event()

            result_holder = [None, None]

            def run_file_review():
                r, e = srv.wait_for_file_response(
                    prompt, config, thread_id, [], cancel_evt, "test cancel",
                )
                result_holder[0] = r
                result_holder[1] = e

            t = threading.Thread(target=run_file_review, daemon=True)
            t.start()

            # Wait for prompt.md
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
            assert "Cross-Model Warning" in content, "missing cross-model warning"
            assert "do NOT paste this prompt into any Claude product" in content, \
                "missing Claude-specific warning"
            assert "File mode test prompt" in content, f"wrong content: {content[:200]}"

            # Simulate user writing response
            response_path = prompt_path.parent / "response.md"
            response_path.write_text("This is the file mode response", encoding="utf-8")

            t.join(timeout=6)
            assert not t.is_alive(), "timed out"
            assert result_holder[1] is None, f"error: {result_holder[1]}"
            assert result_holder[0] == "This is the file mode response"

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 7: File mode — empty file rejected
# ============================================================
def test_file_mode_empty_rejected():

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
            cancel_evt = threading.Event()
            result_holder = [None, None]

            def run():
                r, e = srv.wait_for_file_response(
                    "test", {}, thread_id, [], cancel_evt, "test cancel",
                )
                result_holder[0] = r
                result_holder[1] = e

            t = threading.Thread(target=run, daemon=True)
            t.start()

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

            # Empty file first
            response_path = prompt_path.parent / "response.md"
            response_path.write_text("", encoding="utf-8")
            time.sleep(3)

            # Then real content
            response_path.write_text("Real response after empty", encoding="utf-8")

            t.join(timeout=5)
            assert not t.is_alive(), "thread still alive"
            assert result_holder[0] == "Real response after empty", \
                f"unexpected: {result_holder}"

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv.FILE_STABLE_INTERVAL_SEC = original_stable
            srv.FILE_POLL_INTERVAL_SEC = original_poll


# ============================================================
# Test 8: review rejects empty prompt
# ============================================================
def test_review_missing_prompt():
    resp = srv.handle_review({"prompt": ""}, 99, threading.Event(), "")
    assert resp["result"].get("isError") is True, f"unexpected: {resp}"


# ============================================================
# Test 9: review_reply rejects unknown threadId
# ============================================================
def test_review_reply_unknown_thread():
    resp = srv.handle_review_reply(
        {"threadId": "nonexistent", "prompt": "hi"}, 100, threading.Event(), "",
    )
    assert resp["result"].get("isError") is True, f"unexpected: {resp}"


# ============================================================
# Test 10: Pending state file
# ============================================================
def test_pending_state():

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        try:
            srv.write_pending_state("http://127.0.0.1:9999", "test123", None)
            state_path = Path(tmpdir) / "pending_review.json"
            assert state_path.exists()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state["url"] == "http://127.0.0.1:9999"
            assert state["thread_id"] == "test123"

            srv.clear_pending_state(thread_id="test123")
            assert not state_path.exists()
        finally:
            srv.PENDING_DIR = original_dir


# ============================================================
# Test 11: File mode cancellation via _PendingCall
# ============================================================
def test_file_mode_cancelled():

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = srv.PENDING_DIR
        srv.PENDING_DIR = Path(tmpdir)
        original_mode = srv.MODE
        srv.MODE = "file"
        original_timeout = srv.DEFAULT_TIMEOUT_SEC
        srv.DEFAULT_TIMEOUT_SEC = 60

        try:
            thread_id = srv.create_thread()
            done = threading.Event()

            pending = srv._PendingCall(99)
            srv._pending_call = pending

            def run():
                srv.wait_for_file_response(
                    "cancel test", {}, thread_id, [],
                    pending.cancel_event, pending.cancel_reason,
                )
                done.set()

            t = threading.Thread(target=run, daemon=True)
            pending.thread = t
            t.start()

            # Give time to write prompt.md
            time.sleep(1.0)

            # Cancel via the real _cancel_active_call path
            srv._cancel_active_call(99, "test cancellation")

            assert done.wait(timeout=5), "file-mode call did not exit after cancel"
            assert not t.is_alive()

        finally:
            srv.PENDING_DIR = original_dir
            srv.MODE = original_mode
            srv.DEFAULT_TIMEOUT_SEC = original_timeout
            srv._pending_call = None


# ============================================================
# Test 12: MCP cancellation notification cleans up (subprocess)
# ============================================================
def test_mcp_cancel_notification_cleans_browser_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        pending_dir = Path(tmpdir) / "pending_review"
        proc = _start_server(
            MANUAL_REVIEW_TIMEOUT_SEC="30",
            MANUAL_REVIEW_PENDING_DIR=str(pending_dir),
        )
        try:
            _send_jsonrpc(proc, "initialize", {}, req_id=1)
            _read_response(proc)

            # Start a review call (request id=2)
            _send_jsonrpc(proc, "tools/call", {
                "name": "review",
                "arguments": {"prompt": "test cancel notification", "config": {}},
            }, req_id=2)

            # Wait for pending state to appear
            deadline = time.monotonic() + 5
            top_state = pending_dir / "pending_review.json"
            while time.monotonic() < deadline:
                if top_state.exists():
                    break
                time.sleep(0.2)
            assert top_state.exists(), "pending_review.json not created"

            # Send cancellation notification
            _send_notification(proc, "notifications/cancelled", {
                "requestId": 2,
                "reason": "test cancel",
            })

            # Pending state should be cleaned up promptly
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not top_state.exists():
                    break
                time.sleep(0.2)
            assert not top_state.exists(), "pending state not cleaned after cancel"

            # Server should still be alive and accept a new request
            _send_jsonrpc(proc, "tools/call", {
                "name": "review",
                "arguments": {"prompt": "second call after cancel", "config": {}},
            }, req_id=3)

            # New pending state should appear
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if top_state.exists():
                    break
                time.sleep(0.2)
            assert top_state.exists(), "pending state not created for new request"
            new_state = json.loads(top_state.read_text(encoding="utf-8"))
            assert new_state.get("status") == "waiting"

        finally:
            proc.terminate()
            proc.wait(timeout=3)


# ============================================================
# Test 13: Second review rejected while first is pending
# ============================================================
def test_second_review_rejected_while_first_pending():
    with tempfile.TemporaryDirectory() as tmpdir:
        pending_dir = Path(tmpdir) / "pending_review"
        proc = _start_server(
            MANUAL_REVIEW_TIMEOUT_SEC="30",
            MANUAL_REVIEW_PENDING_DIR=str(pending_dir),
        )
        try:
            _send_jsonrpc(proc, "initialize", {}, req_id=1)
            _read_response(proc)

            # First review (id=2)
            _send_jsonrpc(proc, "tools/call", {
                "name": "review",
                "arguments": {"prompt": "first review", "config": {}},
            }, req_id=2)

            # Wait for pending state
            top_state = pending_dir / "pending_review.json"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if top_state.exists():
                    break
                time.sleep(0.2)
            assert top_state.exists()
            state_data = json.loads(top_state.read_text(encoding="utf-8"))
            url = state_data["url"]
            assert url, "no URL in pending state"

            # Extract token
            from urllib.parse import urlparse, parse_qs
            token = parse_qs(urlparse(url).query).get("token", [""])[0]
            port = urlparse(url).port

            # Second review (id=3) — should be rejected
            _send_jsonrpc(proc, "tools/call", {
                "name": "review",
                "arguments": {"prompt": "second review", "config": {}},
            }, req_id=3)

            resp2 = _read_response(proc, timeout=5)
            assert resp2 is not None, "no response for second review"
            result2_text = resp2["result"]["content"][0]["text"]
            result2 = json.loads(result2_text)
            assert "error" in result2, f"expected error, got: {result2}"
            assert "already in progress" in result2["error"].lower(), \
                f"wrong error: {result2['error']}"

            # First review should still be alive — submit via HTTP
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/context?token={token}",
            )
            ctx = json.loads(resp.read().decode("utf-8"))
            assert ctx.get("prompt") == "first review"

            # Submit response for first review
            submit_data = json.dumps({"response": "First review done"}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/submit?token={token}",
                data=submit_data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req)

            # First review should complete normally
            resp1 = _read_response(proc, timeout=5)
            assert resp1 is not None, "no response for first review"
            content1 = json.loads(resp1["result"]["content"][0]["text"])
            assert content1.get("threadId")
            assert content1.get("content") == "First review done"

        finally:
            proc.terminate()
            proc.wait(timeout=3)


# ============================================================
# Test 14: Cancellation with mismatched requestId is ignored
# ============================================================
def test_cancel_wrong_request_id_ignored():
    with tempfile.TemporaryDirectory() as tmpdir:
        pending_dir = Path(tmpdir) / "pending_review"
        proc = _start_server(
            MANUAL_REVIEW_TIMEOUT_SEC="30",
            MANUAL_REVIEW_PENDING_DIR=str(pending_dir),
        )
        try:
            _send_jsonrpc(proc, "initialize", {}, req_id=1)
            _read_response(proc)

            # Start review (id=2)
            _send_jsonrpc(proc, "tools/call", {
                "name": "review",
                "arguments": {"prompt": "test wrong id cancel", "config": {}},
            }, req_id=2)

            # Wait for pending state
            top_state = pending_dir / "pending_review.json"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if top_state.exists():
                    break
                time.sleep(0.2)
            assert top_state.exists()

            # Cancel with wrong requestId (999 ≠ 2) — should be ignored
            _send_notification(proc, "notifications/cancelled", {
                "requestId": 999,
                "reason": "wrong id",
            })

            # Pending state should still exist (cancel ignored)
            time.sleep(1.0)
            assert top_state.exists(), "pending state wrongly removed"

            # Proper cancel
            _send_notification(proc, "notifications/cancelled", {
                "requestId": 2,
                "reason": "correct id",
            })

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not top_state.exists():
                    break
                time.sleep(0.2)
            assert not top_state.exists(), "pending state not cleaned"

        finally:
            proc.terminate()
            proc.wait(timeout=3)


# ============================================================
# Test 15: Cancellation stress test (repeat to expose races)
# ============================================================
def test_cancel_stress_10_iterations():
    """Repeatedly start review, cancel, start new review — exposes races."""
    for i in range(10):
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_dir = Path(tmpdir) / "pending_review"
            proc = _start_server(
                MANUAL_REVIEW_TIMEOUT_SEC="30",
                MANUAL_REVIEW_PENDING_DIR=str(pending_dir),
            )
            try:
                _send_jsonrpc(proc, "initialize", {}, req_id=1)
                _read_response(proc)

                # Start review (id=2)
                _send_jsonrpc(proc, "tools/call", {
                    "name": "review",
                    "arguments": {"prompt": f"stress test {i}", "config": {}},
                }, req_id=2)

                # Wait for pending state
                top_state = pending_dir / "pending_review.json"
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if top_state.exists():
                        break
                    time.sleep(0.2)
                assert top_state.exists(), f"stress iter {i}: pending not created"

                # Cancel
                _send_notification(proc, "notifications/cancelled", {
                    "requestId": 2, "reason": "stress",
                })

                # Wait for cleanup
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if not top_state.exists():
                        break
                    time.sleep(0.2)
                assert not top_state.exists(), f"stress iter {i}: pending not cleaned"

                # Second review must work (server still alive)
                _send_jsonrpc(proc, "tools/call", {
                    "name": "review",
                    "arguments": {"prompt": f"after cancel {i}", "config": {}},
                }, req_id=3)

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if top_state.exists():
                        break
                    time.sleep(0.2)
                assert top_state.exists(), f"stress iter {i}: second review failed"

            finally:
                proc.terminate()
                proc.wait(timeout=3)


# ============================================================
# Run all tests (script-mode compatibility)
# ============================================================
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
