#!/usr/bin/env python3
"""Cursor CLI (cursor-agent) 的 MCP 桥接，派生自同仓库 grok-exec/server.py。

保留 NDJSON、会话续接、进度/ping/取消与 {threadId, content} 契约。
cursor-agent 没有只读沙箱或工具白名单参数，只读保护由桥接写入的私有
权限策略（.cursor/cli.json 的 deny 规则）实施，见 README。
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

SERVER_NAME = "cursor-exec"
SERVER_VERSION = "1.0.0"
CURSOR_BIN = os.environ.get("CURSOR_AGENT_BIN", "cursor-agent")
STATE_DIR = Path(
    os.environ.get(
        "CURSOR_EXEC_STATE_DIR", str(Path.home() / ".codex" / "state" / SERVER_NAME)
    )
)
THREADS_DIR = STATE_DIR / "threads"
# cursor-agent 子进程的工作目录。里面只有一份 deny 策略，评审的项目目录通过
# --workspace 传入，因此桥接不会向被评审的项目写任何文件。
GUARD_DIR = STATE_DIR / "guard"
GUARD_POLICY = {
    "permissions": {"allow": [], "deny": ["Write(**)", "Shell(**)", "Mcp(*:*)"]}
}
PROGRESS_INTERVAL_SEC = float(os.environ.get("CURSOR_EXEC_PROGRESS_INTERVAL_SEC", "15"))
DEBUG_LOG = os.environ.get("CURSOR_EXEC_DEBUG_LOG", "")

# 空字符串表示不传 --model，由 cursor-agent 自己的默认模型决定。
DEFAULT_MODEL = os.environ.get("CURSOR_EXEC_MODEL", "")
TIMEOUT_SEC = float(os.environ.get("CURSOR_EXEC_TIMEOUT_SEC", "3600"))

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
    # cursor-agent 对未知的 --resume ID 不报错，而是静默新建一个空会话，
    # 所以续接只允许桥接自己记录过的会话。
    try:
        data = json.loads(thread_file(thread_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not data or not isinstance(data, dict):
        raise ValueError("unknown bridge thread; create it with cursor first")
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
    allowed = {"prompt", "model", "cwd"}
    unknown = set(args) - allowed
    if unknown:
        raise ValueError("unsupported arguments: " + ", ".join(sorted(unknown)))
    opts = {
        "model": args.get("model", DEFAULT_MODEL),
        "cwd": args.get("cwd", os.getcwd()),
    }
    if any(not isinstance(opts[k], str) for k in ("model", "cwd")):
        raise ValueError("model and cwd must be strings")
    opts["model"] = opts["model"].strip()
    if opts["model"].startswith("-"):
        raise ValueError("model must be a model id, not an option")
    opts["cwd"] = str(Path(opts["cwd"]).expanduser().resolve())
    if not Path(opts["cwd"]).is_dir():
        raise ValueError("cwd must be an existing directory")
    return opts


def write_guard_policy() -> None:
    # 每次调用都重写，避免旧文件或被改动的文件削弱保护。
    policy_dir = GUARD_DIR / ".cursor"
    for directory in (STATE_DIR, GUARD_DIR, policy_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = policy_dir / "cli.json"
    # 每个进程用自己的临时文件再原子替换：多个桥接进程共用同一个 guard 目录，
    # cursor-agent 不会读到写了一半的策略
    descriptor, temporary = tempfile.mkstemp(dir=policy_dir, suffix=".tmp")
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(GUARD_POLICY, stream)
    os.replace(temporary, path)


def build_argv(opts: dict[str, Any], resume_id: str | None = None) -> list[str]:
    # 提示通过 stdin 传入，避免 argv 长度限制和 shell 插值。不传 --force、
    # --yolo、--approve-mcps。--mode ask 只是辅助层：实测它单独不能阻止写入。
    argv = [
        CURSOR_BIN,
        "-p",
        "--output-format",
        "stream-json",
        "--mode",
        "ask",
        "--trust",
        "--workspace",
        opts["cwd"],
    ]
    if opts["model"]:
        argv += ["--model", opts["model"]]
    if resume_id:
        argv += ["--resume", resume_id]
    return argv


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


def run_cursor(
    argv: list[str],
    prompt: str,
    request_id: Any,
    progress_token: Any,
    inbox: queue.Queue[dict[str, Any]],
    deferred: list[dict[str, Any]],
    cwd: str | None = None,
) -> CallOutcome:
    """Run cursor-agent headlessly, streaming events and answering pings meanwhile."""
    outcome = CallOutcome()
    debug_log("EXEC " + " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
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

    def feed_stdin() -> None:
        if proc.stdin is None:
            return
        try:
            proc.stdin.write(prompt.encode("utf-8"))
        except OSError:
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()
    threading.Thread(target=feed_stdin, daemon=True).start()

    def terminate_child(force: bool = False) -> None:
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

    streams_drained = threading.Event()

    def ticker() -> None:
        # pings and cancellations are answered within a second; progress goes
        # out every PROGRESS_INTERVAL_SEC so a silent reasoning phase still
        # looks alive to the host
        last_progress = time.monotonic()
        stopped_at = None
        while True:
            service_inbox()
            if time.monotonic() - started >= TIMEOUT_SEC and not outcome.cancelled:
                outcome.cancelled = True
                outcome.cancel_reason = (
                    f"cursor timed out after {TIMEOUT_SEC:g}s; no automatic retry"
                )
                terminate_child()
            if outcome.cancelled:
                if stopped_at is None:
                    stopped_at = time.monotonic()
                elif time.monotonic() - stopped_at >= 2:
                    terminate_child(force=True)
            if (
                not outcome.cancelled
                and time.monotonic() - last_progress >= PROGRESS_INTERVAL_SEC
            ):
                progress("working")
                last_progress = time.monotonic()

            # Keep the group leader unreaped until both output pipes reach EOF.
            # Its PID then still identifies our group if a launcher exits first.
            if streams_drained.is_set():
                if outcome.cancelled:
                    terminate_child(force=True)
                try:
                    proc.wait(timeout=0.05)
                    return
                except subprocess.TimeoutExpired:
                    continue
            delay = min(1.0, PROGRESS_INTERVAL_SEC)
            if not outcome.cancelled:
                delay = min(delay, max(0.0, TIMEOUT_SEC - (time.monotonic() - started)))
            streams_drained.wait(delay)

    ticker_thread = threading.Thread(target=ticker, daemon=True)
    ticker_thread.start()

    assert proc.stdout is not None  # Popen was given stdout=PIPE.
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
                outcome.model = event.get("model") or outcome.model
            elif etype == "result":
                outcome.thread_id = event.get("session_id") or outcome.thread_id
                if event.get("is_error") or event.get("subtype") != "success":
                    outcome.failed = True
                    outcome.error = str(
                        event.get("result")
                        or event.get("errors")
                        or "cursor turn failed"
                    )
                else:
                    outcome.completed = True
                    outcome.last_message = event.get("result")
            if etype == "thinking" and event.get("subtype") == "delta":
                # 逐 token 的思考增量不转发；心跳由 ticker 负责
                continue
            send_message(
                {
                    "jsonrpc": "2.0",
                    "method": "cursor/event",
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
    finally:
        stderr_thread.join()
        streams_drained.set()
        ticker_thread.join()

    if outcome.cancelled:
        outcome.error = outcome.cancel_reason
    elif outcome.failed:
        pass  # terminal failure: the cursor error text stands
    elif proc.returncode != 0:
        # 取开头：未知模型时 stderr 先给出原因，后面是很长的可用模型列表
        outcome.error = (
            "cursor-agent exited with status "
            + str(proc.returncode)
            + ": "
            + b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()[:1000]
        )
    elif (
        outcome.completed
        and isinstance(outcome.last_message, str)
        and outcome.last_message.strip()
    ):
        outcome.error = None
    elif not outcome.error:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
        head = stderr_text[:1000] if stderr_text else ""
        outcome.error = (
            f"cursor-agent exited with status {proc.returncode} before completing the turn"
            + (f"\n{head}" if head else "")
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
    result["structuredContent"]["model"] = outcome.model
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


# ─── MCP surface ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "cursor",
        "description": "Start a read-only Cursor CLI (cursor-agent) session in the given cwd. Returns the native threadId for cursor-reply.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string"},
                "model": {
                    "type": "string",
                    "default": DEFAULT_MODEL,
                    "description": "Model id from `cursor-agent --list-models`; effort is part of the id. Empty uses the CLI default.",
                },
                "cwd": {"type": "string"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "cursor-reply",
        "description": "Continue a bridge-created Cursor session, preserving its model and cwd.",
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

    resume_id = None
    try:
        if name == "cursor":
            opts = normalize_options(args)
        elif name == "cursor-reply":
            if set(args) - {"prompt", "threadId"}:
                raise ValueError("cursor-reply cannot change thread settings")
            resume_id = args.get("threadId")
            if not isinstance(resume_id, str):
                raise ValueError("threadId is required")
            opts = normalize_options(recall_thread(resume_id))
        else:
            return error_response(request_id, -32601, f"unknown tool: {name}")
    except ValueError as exc:
        return error_response(request_id, -32602, str(exc))

    write_guard_policy()
    outcome = run_cursor(
        build_argv(opts, resume_id),
        prompt,
        request_id,
        progress_token,
        inbox,
        deferred,
        cwd=str(GUARD_DIR),
    )
    if resume_id and not outcome.thread_id:
        if not outcome.error:
            outcome.error = "cursor did not return a session id"
        outcome.thread_id = resume_id  # Correlate the error with the requested thread.
    elif outcome.thread_id and resume_id and outcome.thread_id != resume_id:
        outcome.error = "cursor returned a different session id"
    elif outcome.thread_id and not resume_id:
        try:
            remember_thread(outcome.thread_id, opts)
        except ValueError:
            outcome.error = "cursor returned an invalid session id"
    elif not outcome.thread_id and not outcome.error:
        outcome.error = "cursor did not return a session id"
    result = tool_result(request_id, outcome)
    result["result"]["structuredContent"]["requestedModel"] = opts["model"]
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
    if shutil.which(CURSOR_BIN) is None:
        debug_log(f"{CURSOR_BIN} not on PATH")
    inbox: queue.Queue[dict[str, Any]] = queue.Queue()
    deferred: list[dict[str, Any]] = []
    # Track calls from receipt to dispatch so cancellation can withdraw a queued
    # call even while a different Cursor process owns the execution slot.
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
                cancelled.error = "cancelled before Cursor started"
                send_message(tool_result(rid, cancelled))
                continue
        try:
            response = handle_request(request, inbox, deferred)
        except Exception:  # noqa: BLE001
            debug_log(traceback.format_exc())
            response = error_response(
                request.get("id"), -32603, "internal error; see CURSOR_EXEC_DEBUG_LOG"
            )
        if response is not None:
            send_message(response)


if __name__ == "__main__":
    main()
