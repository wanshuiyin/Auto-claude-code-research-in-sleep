#!/usr/bin/env python3
"""codex-exec — the `codex` MCP server, implemented over `codex exec`.

codex-cli 0.154.0 removed the `codex mcp-server` entry point that every ARIS
reviewer call was registered against. This server speaks the same MCP
contract that entry point spoke — tools named `codex` and `codex-reply`,
results shaped `{threadId, content}` — and runs each call as a `codex exec`
subprocess, so the skills that invoke `mcp__codex__codex` do not change.

Register it under the same server key the skills expect:

    claude mcp add codex --scope user -- python3 /path/to/aris/mcp-servers/codex-exec/server.py

Differences from the removed entry point, all deliberate:
  * `codex` accepts prompt, model, config, sandbox, cwd. The old
    approval-policy / base-instructions / developer-instructions /
    compact-prompt arguments are not offered because `codex exec` has no
    way to honor them (ARIS never passed them).
  * `codex-reply` re-applies the model, config, sandbox and working
    directory the thread was created with — `codex exec resume` alone
    falls back to config.toml defaults and the caller's cwd, and ARIS's
    routing contract relies on a continued thread keeping its reviewer
    model and effort.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

SERVER_NAME = "codex-exec"
SERVER_VERSION = "1.0.0"
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
STATE_DIR = Path(os.environ.get("CODEX_EXEC_STATE_DIR", str(Path.home() / ".codex" / "state" / SERVER_NAME)))
THREADS_DIR = STATE_DIR / "threads"
PROGRESS_INTERVAL_SEC = float(os.environ.get("CODEX_EXEC_PROGRESS_INTERVAL_SEC", "15"))
DEBUG_LOG = os.environ.get("CODEX_EXEC_DEBUG_LOG", "")

SANDBOX_MODES = ["read-only", "workspace-write", "danger-full-access"]

_stdout_lock = threading.Lock()


# ─── stdio framing (same as mcp-servers/claude-review) ───────────────────────

def _configure_stdio_for_mcp() -> None:
    sys.stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)


def debug_log(message: str) -> None:
    if not DEBUG_LOG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError:
        pass


def send_message(message: Dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    debug_log("SEND " + payload.decode("utf-8", errors="replace")[:2000])
    with _stdout_lock:
        sys.stdout.write(payload + b"\n")
        sys.stdout.flush()


def read_message() -> Optional[Dict[str, Any]]:
    """One JSON-RPC message per line (MCP stdio transport). None on EOF, {} on a blank/garbled line."""
    line = sys.stdin.readline()
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
    return THREADS_DIR / (thread_id + ".json")


def recall_thread(thread_id: str) -> Dict[str, Any]:
    try:
        with thread_file(thread_id).open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_thread(thread_id: str, opts: Dict[str, Any]) -> None:
    # one file per thread, written once by the server that created it — two
    # host sessions running their own bridge never touch the same file
    try:
        THREADS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = thread_file(thread_id + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(opts, fh)
        tmp.replace(thread_file(thread_id))
    except OSError:
        pass


# ─── argv construction ───────────────────────────────────────────────────────

def toml_value(value: Any) -> str:
    """Render a JSON value as the TOML literal `codex -c key=value` expects."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise ValueError(f"unsupported config value: {value!r}")


def config_flags(config: Optional[Dict[str, Any]], prefix: str = "") -> List[str]:
    """Flatten a config object into `-c dotted.key=value` pairs."""
    flags: List[str] = []
    for key, value in (config or {}).items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            flags.extend(config_flags(value, dotted + "."))
        else:
            flags.extend(["-c", f"{dotted}={toml_value(value)}"])
    return flags


def build_argv(args: Dict[str, Any], resume_thread: Optional[str] = None) -> List[str]:
    argv = [CODEX_BIN, "exec"]
    if resume_thread:
        argv += ["resume", resume_thread]
    argv += ["--skip-git-repo-check", "--json"]
    if resume_thread:
        # `resume` has no --sandbox/--cd; the sandbox comes back through config
        # and the working directory through the subprocess cwd (see run_codex)
        if args.get("sandbox"):
            argv += ["-c", f"sandbox_mode={toml_value(str(args['sandbox']))}"]
    else:
        if args.get("cwd"):
            argv += ["--cd", str(args["cwd"])]
        if args.get("sandbox"):
            argv += ["--sandbox", str(args["sandbox"])]
    if args.get("model"):
        argv += ["-m", str(args["model"])]
    argv += config_flags(args.get("config"))
    argv.append("-")  # prompt comes on stdin: no argv length limit, no shell quoting
    return argv


# ─── running one call ────────────────────────────────────────────────────────

class CallOutcome:
    def __init__(self) -> None:
        self.thread_id: Optional[str] = None
        self.last_message: Optional[str] = None
        self.error: Optional[str] = None
        self.completed = False   # turn.completed seen
        self.failed = False      # turn.failed seen — terminal, never cleared
        self.cancelled = False


def run_codex(argv: List[str], prompt: str, request_id: Any, progress_token: Any,
              inbox: "queue.Queue[Dict[str, Any]]", deferred: List[Dict[str, Any]],
              cwd: Optional[str] = None) -> CallOutcome:
    """Run codex exec, streaming events as notifications and answering pings meanwhile."""
    outcome = CallOutcome()
    debug_log("EXEC " + " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd or None,
        )
    except OSError as exc:
        outcome.error = f"could not start {argv[0]}: {exc}"
        return outcome

    stderr_chunks: List[bytes] = []

    def drain_stderr() -> None:
        assert proc.stderr is not None
        for chunk in iter(proc.stderr.readline, b""):
            stderr_chunks.append(chunk)

    def feed_stdin() -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(prompt.encode("utf-8"))
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()
    threading.Thread(target=feed_stdin, daemon=True).start()

    started = time.monotonic()
    progress_count = 0

    def progress(kind: str) -> None:
        nonlocal progress_count
        if progress_token is None:
            return
        progress_count += 1
        send_message({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {
                "progressToken": progress_token,
                "progress": progress_count,
                "message": f"{kind} ({int(time.monotonic() - started)}s)",
            },
        })

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
            elif method == "notifications/cancelled" and msg.get("params", {}).get("requestId") == request_id:
                outcome.cancelled = True
                proc.terminate()
            else:
                deferred.append(msg)

    stop_ticker = threading.Event()

    def ticker() -> None:
        # pings and cancellations are answered within a second; progress goes
        # out every PROGRESS_INTERVAL_SEC so a silent reasoning phase still
        # looks alive to the host
        last_progress = time.monotonic()
        while not stop_ticker.wait(min(1.0, PROGRESS_INTERVAL_SEC)):
            service_inbox()
            if time.monotonic() - last_progress >= PROGRESS_INTERVAL_SEC:
                progress("working")
                last_progress = time.monotonic()

    ticker_thread = threading.Thread(target=ticker, daemon=True)
    ticker_thread.start()

    assert proc.stdout is not None
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = event.get("type", "")
            if etype == "thread.started":
                outcome.thread_id = event.get("thread_id") or outcome.thread_id
            elif etype == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    outcome.last_message = item.get("text", "")
            elif etype == "turn.completed":
                outcome.completed = True
            elif etype == "turn.failed":
                outcome.failed = True
                outcome.error = (event.get("error") or {}).get("message") or outcome.error or "turn failed"
            elif etype == "error" and not outcome.failed:
                # remembered in case the stream ends here; cleared if the turn still completes
                outcome.error = event.get("message") or outcome.error
            send_message({
                "jsonrpc": "2.0",
                "method": "codex/event",
                "params": {"_meta": {"requestId": request_id, "threadId": outcome.thread_id}, "msg": event},
            })
            progress(etype)
            service_inbox()
    finally:
        stop_ticker.set()
        proc.wait()
        ticker_thread.join()   # nothing may touch the inbox after we hand control back
        stderr_thread.join()

    if outcome.cancelled:
        outcome.error = "cancelled by client"
    elif outcome.failed:
        pass  # terminal failure: the codex error text stands
    elif outcome.completed:
        outcome.error = None  # an intermediate error the turn recovered from is not a failure
    elif not outcome.error:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
        tail = stderr_text[-2000:] if stderr_text else ""
        outcome.error = f"codex exec exited with status {proc.returncode} before completing the turn" + (
            f"\n{tail}" if tail else ""
        )
    return outcome


def tool_result(request_id: Any, outcome: CallOutcome) -> Dict[str, Any]:
    if outcome.error:
        text = outcome.error
        result: Dict[str, Any] = {
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
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


# ─── MCP surface ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "codex",
        "description": "Run a Codex session. Accepts configuration parameters matching the Codex Config struct.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The *initial user prompt* to start the Codex conversation."},
                "model": {"type": "string", "description": "Optional override for the model name (e.g. 'gpt-6-astra', 'gpt-5.5')."},
                "config": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Individual config settings that will override what is in CODEX_HOME/config.toml (e.g. {\"model_reasoning_effort\": \"xhigh\"}).",
                },
                "sandbox": {"type": "string", "enum": SANDBOX_MODES, "description": "Sandbox mode: `read-only`, `workspace-write`, or `danger-full-access`."},
                "cwd": {"type": "string", "description": "Working directory for the session. If relative, it is resolved against the server process's current working directory."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex-reply",
        "description": "Continue a Codex conversation by providing the thread id and prompt. The thread keeps the model and config it was created with.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The *next user prompt* to continue the Codex conversation."},
                "threadId": {"type": "string", "description": "The thread id for this Codex session."},
                "conversationId": {"type": "string", "description": "DEPRECATED: use threadId instead."},
            },
            "required": ["prompt"],
        },
    },
]


def error_response(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_call(request: Dict[str, Any], inbox: "queue.Queue[Dict[str, Any]]",
                deferred: List[Dict[str, Any]]) -> Dict[str, Any]:
    request_id = request.get("id")
    params = request.get("params") or {}
    name = params.get("name")
    args = params.get("arguments") or {}
    progress_token = (params.get("_meta") or {}).get("progressToken")
    prompt = args.get("prompt")
    if not isinstance(prompt, str):
        return error_response(request_id, -32602, "prompt is required")

    if name == "codex":
        try:
            argv = build_argv(args)
        except ValueError as exc:
            return error_response(request_id, -32602, str(exc))
        outcome = run_codex(argv, prompt, request_id, progress_token, inbox, deferred)
        if outcome.thread_id:
            remember_thread(outcome.thread_id, {
                "model": args.get("model"),
                "config": args.get("config"),
                "sandbox": args.get("sandbox"),
                "cwd": os.path.abspath(str(args["cwd"])) if args.get("cwd") else os.getcwd(),
            })
        return tool_result(request_id, outcome)

    if name == "codex-reply":
        thread_id = args.get("threadId") or args.get("conversationId")
        if not thread_id:
            return error_response(request_id, -32602, "threadId is required")
        remembered = recall_thread(thread_id)
        argv = build_argv(remembered, resume_thread=thread_id)
        outcome = run_codex(argv, prompt, request_id, progress_token, inbox, deferred,
                            cwd=remembered.get("cwd"))
        outcome.thread_id = outcome.thread_id or thread_id
        return tool_result(request_id, outcome)

    return error_response(request_id, -32601, f"unknown tool: {name}")


def handle_request(request: Dict[str, Any], inbox: "queue.Queue[Dict[str, Any]]",
                   deferred: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
    if shutil.which(CODEX_BIN) is None:
        debug_log(f"{CODEX_BIN} not on PATH")
    inbox: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    deferred: List[Dict[str, Any]] = []

    def reader() -> None:
        while True:
            msg = read_message()
            if msg is None:
                inbox.put({"__eof__": True})
                return
            if msg:
                inbox.put(msg)

    threading.Thread(target=reader, daemon=True).start()
    debug_log(f"=== {SERVER_NAME} starting ===")
    while True:
        request = deferred.pop(0) if deferred else inbox.get()
        if request.get("__eof__"):
            break
        try:
            response = handle_request(request, inbox, deferred)
        except Exception:
            debug_log(traceback.format_exc())
            response = error_response(request.get("id"), -32603, "internal error; see CODEX_EXEC_DEBUG_LOG")
        if response is not None:
            send_message(response)


if __name__ == "__main__":
    main()
