#!/usr/bin/env python3
"""Grok CLI 的 MCP 桥接，派生自同仓库 codex-exec/server.py。

保留 NDJSON、会话续接、进度/ping/取消与 {threadId, content} 契约。
使用 Grok 原生参数与 Messages 流，不把 Grok 冒充 Codex reviewer。
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

SERVER_NAME = "grok-exec"
SERVER_VERSION = "1.0.0"
GROK_BIN = os.environ.get("GROK_BIN", "grok")
STATE_DIR = Path(
    os.environ.get(
        "GROK_EXEC_STATE_DIR", str(Path.home() / ".codex" / "state" / SERVER_NAME)
    )
)
THREADS_DIR = STATE_DIR / "threads"
PROGRESS_INTERVAL_SEC = float(os.environ.get("GROK_EXEC_PROGRESS_INTERVAL_SEC", "15"))
DEBUG_LOG = os.environ.get("GROK_EXEC_DEBUG_LOG", "")

DEFAULT_MODEL = os.environ.get("GROK_EXEC_MODEL", "grok-4.7")
DEFAULT_EFFORT = os.environ.get("GROK_EXEC_EFFORT", "xhigh")
TIMEOUT_SEC = float(os.environ.get("GROK_EXEC_TIMEOUT_SEC", "3600"))
SANDBOX_MODES = ["read-only", "workspace", "strict", "off"]
EFFORTS = ["low", "medium", "high", "xhigh"]
READ_TOOLS = "read_file,grep,list_dir"

_stdout_lock = threading.Lock()
_mcp_stdout: BinaryIO
_mcp_stdin: BinaryIO


# ─── stdio framing (same as mcp-servers/claude-review) ───────────────────────


def _configure_stdio_for_mcp() -> None:
    global _mcp_stdout, _mcp_stdin
    _mcp_stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    _mcp_stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)


def debug_log(message: str) -> None:
    if not DEBUG_LOG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError:
        pass


def send_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    debug_log(
        "SEND id=" + str(message.get("id")) + " method=" + str(message.get("method"))
    )
    with _stdout_lock:
        _mcp_stdout.write(payload + b"\n")
        _mcp_stdout.flush()


def read_message() -> dict[str, Any] | None:
    """One JSON-RPC message per line (MCP stdio transport). None on EOF, {} on a blank/garbled line."""
    line = _mcp_stdin.readline()
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


# ─── thread memory: what each thread was created with ────────────────────────


def thread_file(thread_id: str) -> Path:
    try:
        if str(uuid.UUID(thread_id)) != thread_id.lower():
            raise ValueError("threadId must be a UUID")
    except (ValueError, TypeError, AttributeError):
        raise ValueError("threadId must be a UUID") from None
    return THREADS_DIR / (thread_id + ".json")


def recall_thread(thread_id: str) -> dict[str, Any]:
    try:
        data = json.loads(thread_file(thread_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("unknown bridge thread; create it with grok first") from None
    if not isinstance(data, dict):
        raise ValueError("invalid saved thread settings")
    return data


def remember_thread(thread_id: str, opts: dict[str, Any]) -> None:
    THREADS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = thread_file(thread_id)
    temporary = path.with_suffix(".tmp")
    with os.fdopen(
        os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(opts, stream, ensure_ascii=False)
    temporary.replace(path)


def normalize_options(args: dict[str, Any]) -> dict[str, Any]:
    allowed = {"prompt", "model", "effort", "cwd", "sandbox", "tools", "max_turns"}
    unknown = set(args) - allowed
    if unknown:
        raise ValueError("unsupported arguments: " + ", ".join(sorted(unknown)))
    opts = {
        "model": args.get("model", DEFAULT_MODEL),
        "effort": args.get("effort", DEFAULT_EFFORT),
        "cwd": args.get("cwd", os.getcwd()),
        "sandbox": args.get("sandbox", "read-only"),
        "tools": args.get("tools", READ_TOOLS),
        "max_turns": args.get("max_turns", 50),
    }
    if any(
        not isinstance(opts[k], str)
        for k in ("model", "effort", "cwd", "sandbox", "tools")
    ):
        raise ValueError("model, effort, cwd, sandbox and tools must be strings")
    if not opts["model"].strip() or opts["effort"] not in EFFORTS:
        raise ValueError("model is required; effort must be low, medium, high or xhigh")
    if opts["sandbox"] not in SANDBOX_MODES:
        raise ValueError(
            "use a native Grok sandbox: read-only, workspace, strict or off"
        )
    if (
        isinstance(opts["max_turns"], bool)
        or not isinstance(opts["max_turns"], int)
        or opts["max_turns"] < 1
    ):
        raise ValueError("max_turns must be a positive integer")
    opts["cwd"] = str(Path(opts["cwd"]).expanduser().resolve())
    if not Path(opts["cwd"]).is_dir():
        raise ValueError("cwd must be an existing directory")
    return opts


def build_argv(
    opts: dict[str, Any], prompt_path: str, thread_id: str, resume: bool = False
) -> list[str]:
    # 提示通过私有临时文件传入，避免 argv 长度限制和 shell 插值。
    return [
        GROK_BIN,
        "--prompt-file",
        prompt_path,
        "--output-format",
        "streaming-messages-json",
        "--resume" if resume else "--session-id",
        thread_id,
        "--model",
        opts["model"],
        "--reasoning-effort",
        opts["effort"],
        "--cwd",
        opts["cwd"],
        "--sandbox",
        opts["sandbox"],
        "--tools",
        opts["tools"],
        "--max-turns",
        str(opts["max_turns"]),
        "--permission-mode",
        "dontAsk",
        "--no-plan",
        "--no-subagents",
        "--disable-web-search",
        "--allow",
        "Read",
        "--allow",
        "Grep",
        "--deny",
        "MCPTool",
    ]


def runtime_effort(thread_id: str, cwd: str) -> str | None:
    # 只取本次会话摘要中的实际 effort，不读取认证文件，不用请求值冒充实测值。
    home = Path(os.environ.get("GROK_HOME", str(Path.home() / ".grok")))
    path = home / "sessions" / quote(cwd, safe="") / thread_id / "summary.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("reasoning_effort")
        return value if isinstance(value, str) else None
    except (OSError, ValueError):
        return None


# ─── running one call ────────────────────────────────────────────────────────


class CallOutcome:
    def __init__(self) -> None:
        self.thread_id: str | None = None
        self.last_message: str | None = None
        self.error: str | None = None
        self.completed = False  # 已收到完整 result
        self.failed = False  # 失败为终态，后续事件不能把它洗成成功
        self.cancelled = False
        self.cancel_reason: str | None = None
        self.model: str | None = None
        self.actual_effort: str | None = None
        self.stop_reason: str | None = None


def run_grok(
    argv: list[str],
    request_id: Any,
    progress_token: Any,
    inbox: queue.Queue[dict[str, Any]],
    deferred: list[dict[str, Any]],
    cwd: str | None = None,
) -> CallOutcome:
    """Run Grok headlessly, streaming events and answering pings meanwhile."""
    outcome = CallOutcome()
    debug_log("EXEC " + " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd or None,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        outcome.error = f"could not start {argv[0]}: {exc}"
        return outcome

    stderr_chunks: list[bytes] = []

    def drain_stderr() -> None:
        if proc.stderr is None:
            return
        stderr_chunks.extend(iter(proc.stderr.readline, b""))

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    def terminate_child(force: bool = False) -> None:
        if proc.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
            elif force:
                proc.kill()
            else:
                proc.terminate()
        except ProcessLookupError:
            pass

    started = time.monotonic()
    progress_count = 0

    def progress(kind: str) -> None:
        nonlocal progress_count
        if progress_token is None:
            return
        progress_count += 1
        send_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": progress_token,
                    "progress": progress_count,
                    "message": f"{kind} ({int(time.monotonic() - started)}s)",
                },
            }
        )

    def service_inbox() -> None:
        """Answer pings and honor a cancellation while the child runs."""
        while True:
            try:
                msg = inbox.get_nowait()
            except queue.Empty:
                return
            method = msg.get("method", "")
            if method == "ping" and msg.get("id") is not None:
                send_message({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
            elif (
                method == "notifications/cancelled"
                and msg.get("params", {}).get("requestId") == request_id
            ):
                outcome.cancelled = True
                outcome.cancel_reason = "cancelled by client"
                terminate_child()
            elif msg.get("__eof__"):
                outcome.cancelled = True
                outcome.cancel_reason = "MCP client disconnected"
                terminate_child()
                deferred.append(msg)
            else:
                deferred.append(msg)

    stop_ticker = threading.Event()

    def ticker() -> None:
        # pings and cancellations are answered within a second; progress goes
        # out every PROGRESS_INTERVAL_SEC so a silent reasoning phase still
        # looks alive to the host
        last_progress = time.monotonic()
        stopped_at = None
        while not stop_ticker.wait(min(1.0, PROGRESS_INTERVAL_SEC)):
            service_inbox()
            if time.monotonic() - started >= TIMEOUT_SEC and not outcome.cancelled:
                outcome.cancelled = True
                outcome.cancel_reason = (
                    f"grok timed out after {TIMEOUT_SEC:g}s; no automatic retry"
                )
                terminate_child()
            if outcome.cancelled:
                if stopped_at is None:
                    stopped_at = time.monotonic()
                elif time.monotonic() - stopped_at >= 2:
                    terminate_child(force=True)
            if time.monotonic() - last_progress >= PROGRESS_INTERVAL_SEC:
                progress("working")
                last_progress = time.monotonic()

    ticker_thread = threading.Thread(target=ticker, daemon=True)
    ticker_thread.start()

    if proc.stdout is None:
        terminate_child(force=True)
        proc.wait()
        raise RuntimeError("Grok stdout pipe was not created")
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            etype = event.get("type", "")
            if etype == "system" and event.get("subtype") == "init":
                outcome.thread_id = event.get("session_id") or outcome.thread_id
            elif etype == "assistant":
                message = event.get("message") or {}
                if message.get("model"):
                    outcome.model = message["model"]
            elif etype == "result":
                outcome.thread_id = event.get("session_id") or outcome.thread_id
                outcome.stop_reason = event.get("stop_reason")
                models = list((event.get("modelUsage") or {}).keys())
                if len(models) == 1:
                    outcome.model = models[0]
                if event.get("is_error") or event.get("subtype") != "success":
                    outcome.failed = True
                    outcome.error = str(
                        event.get("result") or event.get("errors") or "grok turn failed"
                    )
                elif outcome.stop_reason != "end_turn":
                    outcome.failed = True
                    outcome.error = "incomplete grok turn: " + str(outcome.stop_reason)
                else:
                    outcome.completed = True
                    outcome.last_message = event.get("result")
            elif etype == "error":
                outcome.failed = True
                outcome.error = str(event.get("message") or "grok CLI error")
            send_message(
                {
                    "jsonrpc": "2.0",
                    "method": "grok/event",
                    "params": {
                        "_meta": {
                            "requestId": request_id,
                            "threadId": outcome.thread_id,
                        },
                        "msg": event,
                    },
                }
            )
            progress(etype)
            service_inbox()
    finally:
        proc.wait()
        stop_ticker.set()
        ticker_thread.join()  # nothing may touch the inbox after we hand control back
        stderr_thread.join()

    if outcome.cancelled:
        outcome.error = outcome.cancel_reason
    elif outcome.failed:
        pass  # terminal failure: the grok error text stands
    elif proc.returncode != 0:
        outcome.error = (
            "grok exited with status "
            + str(proc.returncode)
            + ": "
            + b"".join(stderr_chunks).decode("utf-8", errors="replace")[-2000:]
        )
    elif (
        outcome.completed
        and isinstance(outcome.last_message, str)
        and outcome.last_message.strip()
    ):
        outcome.error = None
    elif not outcome.error:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
        tail = stderr_text[-2000:] if stderr_text else ""
        outcome.error = (
            f"grok exited with status {proc.returncode} before completing the turn"
            + (f"\n{tail}" if tail else "")
        )
    return outcome


def tool_result(request_id: Any, outcome: CallOutcome) -> dict[str, Any]:
    if outcome.error:
        text = outcome.error
        result: dict[str, Any] = {
            "isError": True,
            "content": [{"type": "text", "text": text}],
            "structuredContent": {"threadId": outcome.thread_id, "content": text},
        }
    else:
        text = outcome.last_message or ""
        result = {
            "structuredContent": {"threadId": outcome.thread_id, "content": text},
            "content": [{"type": "text", "text": text}],
        }
    result["structuredContent"].update(
        {
            "model": outcome.model,
            "effort": outcome.actual_effort,
            "stopReason": outcome.stop_reason,
        }
    )
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


# ─── MCP surface ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "grok",
        "description": "Start a Grok CLI session; defaults to grok-4.7, xhigh and read-only tools. Returns the native threadId for grok-reply.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string"},
                "model": {"type": "string", "default": DEFAULT_MODEL},
                "effort": {
                    "type": "string",
                    "enum": EFFORTS,
                    "default": DEFAULT_EFFORT,
                },
                "cwd": {"type": "string"},
                "sandbox": {
                    "type": "string",
                    "enum": SANDBOX_MODES,
                    "default": "read-only",
                },
                "tools": {
                    "type": "string",
                    "default": READ_TOOLS,
                    "description": "Native Grok tool IDs, comma-separated. Empty string means no built-in tools.",
                },
                "max_turns": {"type": "integer", "minimum": 1, "default": 50},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "grok-reply",
        "description": "Continue a bridge-created Grok session, preserving its model, effort, cwd, sandbox, tools and turn limit.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string"},
                "threadId": {"type": "string"},
            },
            "required": ["prompt", "threadId"],
        },
    },
]


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_call(
    request: dict[str, Any],
    inbox: queue.Queue[dict[str, Any]],
    deferred: list[dict[str, Any]],
) -> dict[str, Any]:
    request_id = request.get("id")
    params = request.get("params") or {}
    name = params.get("name")
    args = params.get("arguments") or {}
    progress_token = (params.get("_meta") or {}).get("progressToken")
    prompt = args.get("prompt")
    if not isinstance(prompt, str):
        return error_response(request_id, -32602, "prompt is required")

    try:
        if name == "grok":
            opts = normalize_options(args)
            thread_id = str(uuid.uuid4())
        elif name == "grok-reply":
            if set(args) - {"prompt", "threadId"}:
                raise ValueError("grok-reply cannot change thread settings")
            thread_id = args.get("threadId")
            if not isinstance(thread_id, str):
                raise ValueError("threadId is required")
            opts = normalize_options(recall_thread(thread_id))
        else:
            return error_response(request_id, -32601, f"unknown tool: {name}")
    except ValueError as exc:
        return error_response(request_id, -32602, str(exc))

    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="prompt-", dir=STATE_DIR) as temporary:
        prompt_path = Path(temporary) / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_path.chmod(0o600)
        argv = build_argv(
            opts, str(prompt_path), thread_id, resume=(name == "grok-reply")
        )
        outcome = run_grok(
            argv, request_id, progress_token, inbox, deferred, cwd=opts["cwd"]
        )
    if outcome.thread_id and outcome.thread_id != thread_id:
        outcome.error = "grok returned a different session id"
    elif outcome.thread_id:
        remember_thread(thread_id, opts)
        outcome.actual_effort = runtime_effort(thread_id, opts["cwd"])
        if (
            outcome.actual_effort is not None
            and outcome.actual_effort != opts["effort"]
        ):
            outcome.error = (
                "grok actual reasoning effort differs from the requested effort"
            )
    elif not outcome.error:
        outcome.error = "grok did not return a session id"
    result = tool_result(request_id, outcome)
    result["result"]["structuredContent"].update(
        {"requestedModel": opts["model"], "requestedEffort": opts["effort"]}
    )
    return result


def handle_request(
    request: dict[str, Any],
    inbox: queue.Queue[dict[str, Any]],
    deferred: list[dict[str, Any]],
) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}
    debug_log(f"REQUEST id={request_id!r} method={method}")

    if request_id is None:
        return None  # notifications need no reply

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion") or "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        return handle_call(request, inbox, deferred)
    return error_response(request_id, -32601, f"method not found: {method}")


def main() -> None:
    _configure_stdio_for_mcp()
    if shutil.which(GROK_BIN) is None:
        debug_log(f"{GROK_BIN} not on PATH")
    inbox: queue.Queue[dict[str, Any]] = queue.Queue()
    deferred: list[dict[str, Any]] = []

    # Track calls from receipt to dispatch so cancellation can withdraw a queued
    # call even while a different Grok process owns the execution slot.
    pending_calls: set[Any] = set()
    pending_lock = threading.Lock()

    def reader() -> None:
        while True:
            msg = read_message()
            with pending_lock:
                if msg is None:
                    pending_calls.clear()
                    inbox.put({"__eof__": True})
                    return
                if msg.get("method") == "tools/call":
                    pending_calls.add(msg.get("id"))
                elif msg.get("method") == "notifications/cancelled":
                    pending_calls.discard(msg.get("params", {}).get("requestId"))
            if msg:
                inbox.put(msg)

    threading.Thread(target=reader, daemon=True).start()
    debug_log(f"=== {SERVER_NAME} starting ===")
    while True:
        request = deferred.pop(0) if deferred else inbox.get()
        if request.get("__eof__"):
            break
        if request.get("method") == "tools/call":
            rid = request.get("id")
            with pending_lock:
                queued = rid in pending_calls
                pending_calls.discard(rid)
            if not queued:
                cancelled = CallOutcome()
                cancelled.error = "cancelled before Grok started"
                send_message(tool_result(rid, cancelled))
                continue
        try:
            response = handle_request(request, inbox, deferred)
        except Exception:
            debug_log(traceback.format_exc())
            response = error_response(
                request.get("id"), -32603, "internal error; see GROK_EXEC_DEBUG_LOG"
            )
        if response is not None:
            send_message(response)


if __name__ == "__main__":
    main()
