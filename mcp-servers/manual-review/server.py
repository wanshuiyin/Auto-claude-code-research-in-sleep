#!/usr/bin/env python3
"""Manual Review MCP Server for ARIS.

A human-in-the-loop reviewer bridge: when the pipeline needs cross-model
review, this server opens a browser page (or writes a file on headless Linux)
where the user can copy the prompt to any model and paste the response back.

Zero API cost. Works with any text-capable model (ChatGPT web, DeepSeek,
Kimi, local models, etc.).
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- stdio setup (deferred to main() to allow safe import for testing) ---
_stdio_initialized = False


def _init_stdio():
    global _stdio_initialized
    if _stdio_initialized:
        return
    sys.stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)
    _stdio_initialized = True

# --- Configuration ---
SERVER_NAME = os.environ.get("MANUAL_REVIEW_SERVER_NAME", "manual-review")
DEFAULT_TIMEOUT_SEC = int(os.environ.get("MANUAL_REVIEW_TIMEOUT_SEC", "86400"))
MODE = os.environ.get("MANUAL_REVIEW_MODE", "browser")  # "browser" or "file"
AUTO_OPEN = os.environ.get("MANUAL_REVIEW_AUTO_OPEN", "true").lower() in {"1", "true", "yes"}
PENDING_DIR = Path(os.environ.get("MANUAL_REVIEW_PENDING_DIR", ".aris/pending_review"))
DEBUG_LOG_RAW = os.environ.get("MANUAL_REVIEW_DEBUG_LOG", "").strip()
DEBUG_LOG = Path(DEBUG_LOG_RAW).expanduser() if DEBUG_LOG_RAW else None
DEFAULT_PORT = int(os.environ.get("MANUAL_REVIEW_PORT", "17900"))
MAX_PORT_ATTEMPTS = 10

# File-mode stability: require content unchanged across two reads with this gap
FILE_STABLE_INTERVAL_SEC = 3
FILE_POLL_INTERVAL_SEC = 2

# --- MCP Protocol ---
_use_ndjson = False

# --- Thread storage (in-memory, lives as long as the MCP server process) ---
_threads: dict[str, list[dict[str, str]]] = {}

# --- UI HTML (loaded once) ---
_UI_HTML: str | None = None


def debug_log(message: str) -> None:
    if DEBUG_LOG is None:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{utc_now()}] {message}\n")
    except OSError:
        pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_ui_html() -> str:
    global _UI_HTML
    if _UI_HTML is None:
        ui_path = Path(__file__).parent / "ui.html"
        _UI_HTML = ui_path.read_text(encoding="utf-8")
    return _UI_HTML


# --- MCP stdio transport ---

_send_lock = threading.Lock()


def send_response(response: dict[str, Any]) -> None:
    global _use_ndjson
    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    debug_log(f"SEND {payload.decode('utf-8', errors='replace')[:200]}")
    with _send_lock:
        if _use_ndjson:
            sys.stdout.write(payload + b"\n")
        else:
            header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
            sys.stdout.write(header + payload)
        sys.stdout.flush()


def read_message() -> dict[str, Any] | None:
    global _use_ndjson
    line = sys.stdin.readline()
    if not line:
        return None
    line_text = line.decode("utf-8").rstrip("\r\n")
    if line_text.lower().startswith("content-length:"):
        try:
            content_length = int(line_text.split(":", 1)[1].strip())
        except ValueError:
            return None
        while True:
            header_line = sys.stdin.readline()
            if not header_line:
                return None
            if header_line in {b"\r\n", b"\n"}:
                break
        body = sys.stdin.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None
    if line_text.startswith("{") or line_text.startswith("["):
        _use_ndjson = True
        try:
            return json.loads(line_text)
        except json.JSONDecodeError:
            return None
    return None


# --- Thread management ---

def create_thread() -> str:
    thread_id = uuid.uuid4().hex[:12]
    _threads[thread_id] = []
    return thread_id


def append_exchange(thread_id: str, role: str, content: str) -> None:
    if thread_id not in _threads:
        _threads[thread_id] = []
    _threads[thread_id].append({"role": role, "content": content})


def get_history(thread_id: str) -> list[dict[str, str]]:
    return _threads.get(thread_id, [])


# --- Pending state file ---

def _pending_dir_for(thread_id: str) -> Path:
    """Per-thread pending directory to avoid clobbering in concurrent calls."""
    return PENDING_DIR / thread_id


def write_pending_state(url: str | None, thread_id: str, prompt_file: str | None) -> None:
    pdir = _pending_dir_for(thread_id)
    state = {
        "status": "waiting",
        "url": url,
        "prompt_file": prompt_file,
        "response_file": str(pdir / "response.md") if prompt_file else None,
        "thread_id": thread_id,
        "created_at": utc_now(),
    }
    pdir.mkdir(parents=True, exist_ok=True)
    state_path = pdir / "pending_review.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also write a top-level pointer for easy discovery
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (PENDING_DIR / "pending_review.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_pending_state(thread_id: str | None = None) -> None:
    # Clear per-thread dir
    if thread_id:
        pdir = _pending_dir_for(thread_id)
        if pdir.exists():
            import shutil
            shutil.rmtree(pdir, ignore_errors=True)
    # Clear top-level pointer
    top_state = PENDING_DIR / "pending_review.json"
    if top_state.exists():
        top_state.unlink()



# --- Browser mode: HTTP server ---

class _ReviewSession:
    """Holds state for one review interaction."""
    def __init__(self, prompt: str, config: dict, thread_id: str, history: list):
        self.prompt = prompt
        self.config = config
        self.thread_id = thread_id
        self.history = history
        self.response: str | None = None
        self.done = threading.Event()


_current_session: _ReviewSession | None = None
_active_server: socketserver.TCPServer | None = None
_active_server_lock = threading.Lock()
_auth_token: str | None = None


def _generate_token() -> str:
    """Generate a one-shot auth token for this review session."""
    return uuid.uuid4().hex[:16]


def _check_token(handler) -> bool:
    """Validate auth token from query string or header. Returns True if valid."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    token_values = params.get("token", [])
    if token_values and token_values[0] == _auth_token:
        return True
    header_token = handler.headers.get("X-Review-Token", "")
    if header_token == _auth_token:
        return True
    return False


def _check_origin(handler) -> bool:
    """Defense-in-depth: reject browser requests with suspicious cross-site headers.
    Token auth is still required; this is an additional layer."""
    origin = handler.headers.get("Origin", "")
    if origin:
        expected = f"http://127.0.0.1:{handler.server.server_address[1]}"
        if origin != expected:
            return False
    sec_fetch_site = handler.headers.get("Sec-Fetch-Site", "")
    if sec_fetch_site and sec_fetch_site not in {"same-origin", "none"}:
        return False
    return True


class _ReviewHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        debug_log(f"HTTP {format % args}")

    def _get_clean_path(self) -> str:
        from urllib.parse import urlparse
        return urlparse(self.path).path

    def do_GET(self):
        path = self._get_clean_path()
        if path == "/":
            if not _check_token(self):
                self.send_error(403, "Invalid or missing token")
                return
            if not _check_origin(self):
                self.send_error(403, "Cross-origin request blocked")
                return
            html = load_ui_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif path == "/api/context":
            if not _check_token(self):
                self.send_error(403, "Invalid or missing token")
                return
            if not _check_origin(self):
                self.send_error(403, "Cross-origin request blocked")
                return
            session = _current_session
            ctx = {
                "prompt": session.prompt if session else "",
                "config": session.config if session else {},
                "threadId": session.thread_id if session else "",
                "history": session.history if session else [],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(ctx, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        path = self._get_clean_path()
        if path == "/api/submit":
            if not _check_token(self):
                self.send_error(403, "Invalid or missing token")
                return
            if not _check_origin(self):
                self.send_error(403, "Cross-origin request blocked")
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            response_text = data.get("response", "").strip()
            if not response_text:
                self.send_error(400, "Empty response")
                return
            session = _current_session
            if session:
                session.response = response_text
                session.done.set()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_error(403, "CORS not allowed")


def wait_for_browser_response(prompt: str, config: dict, thread_id: str, history: list) -> tuple[str | None, str | None]:
    global _current_session, _active_server, _auth_token

    # Cleanup any leftover server from a previous interrupted call
    with _active_server_lock:
        if _active_server is not None:
            try:
                _active_server.shutdown()
                _active_server.server_close()
            except Exception:
                pass
            _active_server = None
        _current_session = _ReviewSession(prompt, config, thread_id, history)
        _auth_token = _generate_token()

    # Try fixed port, increment on conflict
    server = None
    port = DEFAULT_PORT
    for attempt in range(MAX_PORT_ATTEMPTS):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            srv = socketserver.TCPServer(("127.0.0.1", port), _ReviewHandler)
            server = srv
            break
        except OSError:
            port += 1
    if server is None:
        _current_session = None
        return None, f"Could not bind to any port in range {DEFAULT_PORT}-{DEFAULT_PORT + MAX_PORT_ATTEMPTS - 1}"

    with _active_server_lock:
        _active_server = server

    url = f"http://127.0.0.1:{port}?token={_auth_token}"

    write_pending_state(url=url, thread_id=thread_id, prompt_file=None)
    debug_log(f"HTTP server started on {url}")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if AUTO_OPEN:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # Poll with short intervals so we can be cancelled if a new request arrives
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if _current_session.done.wait(timeout=1.0):
            break
        if _pending_call_cancelled.is_set():
            break

    server.shutdown()
    server.server_close()
    with _active_server_lock:
        _active_server = None
    clear_pending_state(thread_id)

    if not _current_session.done.is_set():
        _current_session = None
        return None, f"Timed out after {DEFAULT_TIMEOUT_SEC}s waiting for manual review response"

    response = _current_session.response
    _current_session = None
    return response, None


# --- File mode: prompt.md / response.md ---

def wait_for_file_response(prompt: str, config: dict, thread_id: str, history: list) -> tuple[str | None, str | None]:
    pdir = _pending_dir_for(thread_id)
    pdir.mkdir(parents=True, exist_ok=True)
    prompt_path = pdir / "prompt.md"
    response_path = pdir / "response.md"

    # Clean up any stale response file
    if response_path.exists():
        response_path.unlink()

    # Write prompt
    header = f"<!-- thread: {thread_id} | config: {json.dumps(config)} -->\n\n"
    if history:
        header += "## Previous Exchanges\n\n"
        for i, ex in enumerate(history):
            header += f"### {'Prompt' if ex['role'] == 'user' else 'Response'} (Round {i // 2 + 1})\n\n"
            header += ex["content"][:500] + ("..." if len(ex["content"]) > 500 else "") + "\n\n"
        header += "---\n\n## Current Prompt\n\n"
    prompt_path.write_text(header + prompt, encoding="utf-8")

    write_pending_state(url=None, thread_id=thread_id, prompt_file=str(prompt_path))
    debug_log(f"File mode: prompt written to {prompt_path}, waiting for {response_path}")

    # Poll for response file with stability check
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SEC
    prev_content: str | None = None

    while time.monotonic() < deadline:
        if _pending_call_cancelled.is_set():
            clear_pending_state(thread_id)
            return None, "Manual review request was cancelled"

        time.sleep(FILE_POLL_INTERVAL_SEC)

        if _pending_call_cancelled.is_set():
            clear_pending_state(thread_id)
            return None, "Manual review request was cancelled"

        if not response_path.exists():
            prev_content = None
            continue
        try:
            content = response_path.read_text(encoding="utf-8").strip()
        except OSError:
            prev_content = None
            continue
        if not content:
            prev_content = None
            continue
        # Stability check: content must be non-empty and unchanged across two reads
        if content == prev_content:
            clear_pending_state(thread_id)
            return content, None
        prev_content = content
        time.sleep(FILE_STABLE_INTERVAL_SEC)

        if _pending_call_cancelled.is_set():
            clear_pending_state(thread_id)
            return None, "Manual review request was cancelled"

        # Re-read after stability interval
        try:
            content2 = response_path.read_text(encoding="utf-8").strip()
        except OSError:
            prev_content = None
            continue
        if content2 == content and content2:
            clear_pending_state(thread_id)
            return content2, None
        prev_content = content2

    clear_pending_state(thread_id)
    return None, f"Timed out after {DEFAULT_TIMEOUT_SEC}s waiting for {response_path}"



# --- Unified dispatch ---

def do_review(prompt: str, config: dict, thread_id: str, history: list) -> tuple[str | None, str | None]:
    if MODE == "file":
        return wait_for_file_response(prompt, config, thread_id, history)
    return wait_for_browser_response(prompt, config, thread_id, history)


# --- MCP tool handlers ---

def tool_success(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        },
    }


def tool_error(request_id: Any, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
            "isError": True,
        },
    }


def handle_review(args: dict, request_id: Any) -> dict[str, Any]:
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return tool_error(request_id, "prompt is required")
    config = args.get("config", {})
    if not isinstance(config, dict):
        config = {}

    thread_id = create_thread()
    append_exchange(thread_id, "user", prompt)

    response, error = do_review(prompt, config, thread_id, [])
    if error:
        return tool_error(request_id, error)

    append_exchange(thread_id, "assistant", response)
    return tool_success(request_id, {"threadId": thread_id, "content": response})


def handle_review_reply(args: dict, request_id: Any) -> dict[str, Any]:
    thread_id = str(args.get("threadId", "")).strip()
    if not thread_id:
        return tool_error(request_id, "threadId is required")
    if thread_id not in _threads:
        return tool_error(request_id, f"Unknown threadId: {thread_id}")

    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return tool_error(request_id, "prompt is required")
    config = args.get("config", {})
    if not isinstance(config, dict):
        config = {}

    history = get_history(thread_id)
    append_exchange(thread_id, "user", prompt)

    response, error = do_review(prompt, config, thread_id, history)
    if error:
        return tool_error(request_id, error)

    append_exchange(thread_id, "assistant", response)
    return tool_success(request_id, {"threadId": thread_id, "content": response})


# --- MCP request router ---

def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if request_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method in {"resources/list", "resources/templates/list"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}

    if method in {"notifications/initialized", "initialized"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "review",
                        "description": "Start a new manual review session. Opens a browser page where the user copies the prompt to any AI model and pastes the response back.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "The full review prompt to show the user"},
                                "config": {"type": "object", "description": "Config hints (e.g. model_reasoning_effort)"},
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_reply",
                        "description": "Continue a review conversation in an existing thread. Shows previous exchanges for context.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "threadId": {"type": "string", "description": "Thread ID from a previous review call"},
                                "prompt": {"type": "string", "description": "Follow-up prompt"},
                                "config": {"type": "object", "description": "Config hints"},
                            },
                            "required": ["threadId", "prompt"],
                        },
                    },
                ],
            },
        }

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            return tool_error(request_id, "tool arguments must be an object")
        if name == "review":
            return handle_review(args, request_id)
        if name == "review_reply":
            return handle_review_reply(args, request_id)
        return tool_error(request_id, f"unknown tool: {name}")

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


# --- Main loop (non-blocking) ---

# Pending blocking tool call state
_pending_call_thread: threading.Thread | None = None
_pending_call_cancelled = threading.Event()


def _cancel_pending_call():
    """Cancel any in-progress review call so the port is freed."""
    global _pending_call_thread, _current_session, _active_server
    _pending_call_cancelled.set()
    if _current_session is not None:
        _current_session.done.set()  # unblock the wait
    with _active_server_lock:
        if _active_server is not None:
            try:
                _active_server.shutdown()
                _active_server.server_close()  # actually release the socket/port
            except Exception:
                pass
            _active_server = None
    if _pending_call_thread is not None:
        _pending_call_thread.join(timeout=3)
        _pending_call_thread = None
    # Note: do NOT clear _pending_call_cancelled here.
    # The main loop clears it right before starting the next worker thread.
    # Clearing too early would let the old worker miss the cancel signal.


def _run_blocking_tool(handler, args, request_id):
    """Run a blocking tool handler in background, send response when done."""
    global _pending_call_thread
    response = handler(args, request_id)
    if not _pending_call_cancelled.is_set():
        send_response(response)
    _pending_call_thread = None


def main() -> int:
    global _pending_call_thread
    _init_stdio()
    debug_log(f"Server starting: mode={MODE}, timeout={DEFAULT_TIMEOUT_SEC}s")
    while True:
        request = read_message()
        if request is None:
            return 0

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # For tool calls that block (review, review_reply), run in background
        if method == "tools/call":
            name = params.get("name", "")
            if name in ("review", "review_reply"):
                # Cancel any previous pending call
                if _pending_call_thread is not None and _pending_call_thread.is_alive():
                    _cancel_pending_call()

                args = params.get("arguments", {})
                if not isinstance(args, dict):
                    send_response(tool_error(request_id, "tool arguments must be an object"))
                    continue

                handler = handle_review if name == "review" else handle_review_reply
                _pending_call_cancelled.clear()
                _pending_call_thread = threading.Thread(
                    target=_run_blocking_tool,
                    args=(handler, args, request_id),
                    daemon=True,
                )
                _pending_call_thread.start()
                continue

        # Non-blocking requests handled synchronously
        response = handle_request(request)
        if response is not None:
            send_response(response)


if __name__ == "__main__":
    raise SystemExit(main())
