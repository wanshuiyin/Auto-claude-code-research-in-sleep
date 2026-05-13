#!/usr/bin/env python3
"""Claude review MCP server for Codex-first ARIS workflows.

This server exposes a narrow review-only interface over Claude Code CLI so
Codex can remain the executor while Claude acts as the external reviewer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _configure_stdio_for_mcp() -> None:
    """Re-bind sys.stdout/sys.stdin as raw binary streams for the MCP protocol.

    Called from main() rather than module import so that unit tests can
    safely `importlib.exec_module(server.py)` without globally clobbering
    the test process's text-mode stdio (which breaks subsequent print()
    calls with TypeError).
    """
    sys.stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)


SERVER_NAME = os.environ.get("CLAUDE_REVIEW_SERVER_NAME", "claude-review")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DEFAULT_MODEL = os.environ.get("CLAUDE_REVIEW_MODEL", "")
DEFAULT_SYSTEM = os.environ.get("CLAUDE_REVIEW_SYSTEM", "")
DEFAULT_TOOLS = os.environ.get("CLAUDE_REVIEW_TOOLS", "")
DEFAULT_TIMEOUT_SEC = int(os.environ.get("CLAUDE_REVIEW_TIMEOUT_SEC", "600"))
DEBUG_LOG = Path(os.environ.get("CLAUDE_REVIEW_DEBUG_LOG", f"/tmp/{SERVER_NAME}-mcp-debug.log"))
STATE_DIR = Path(
    os.environ.get(
        "CLAUDE_REVIEW_STATE_DIR",
        str(Path.home() / ".codex" / "state" / SERVER_NAME),
    )
)
JOBS_DIR = STATE_DIR / "jobs"

_use_ndjson = False
TERMINAL_JOB_STATES = {"completed", "failed"}


def debug_log(message: str) -> None:
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{message}\n")
    except OSError:
        pass


def send_response(response: dict[str, Any]) -> None:
    global _use_ndjson

    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    debug_log(f"SEND {payload.decode('utf-8', errors='replace')}")
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


def find_claude_bin() -> str | None:
    if Path(CLAUDE_BIN).is_file():
        return CLAUDE_BIN
    return shutil.which(CLAUDE_BIN)


def parse_claude_json(raw_stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = raw_stdout.strip()
    if not stripped:
        return None, "Claude CLI returned empty output"

    # CLI 2.x: try whole stdout as a single JSON value first.
    # Handles both compact one-line arrays and pretty-printed multi-line arrays.
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        return payload, None
    if isinstance(payload, list):
        # claude CLI 2.x emits a JSON array of event objects under --output-format json
        # (system init -> assistant -> rate_limit_event -> result). Only the terminal
        # "result" event carries the fields run_claude_review consumes downstream
        # (result text, session_id, duration_ms, stop_reason). Falling back to any
        # other dict (e.g. rate_limit_event) would surface as a "successful parse"
        # producing an empty review — strictly worse than a clear error.
        for item in reversed(payload):
            if isinstance(item, dict) and item.get("type") == "result":
                return item, None
        return None, "Claude CLI returned a JSON array without a 'result' event"

    # Legacy CLI 1.x: NDJSON stream of dicts, walk lines in reverse for the
    # last useful payload. Same array-vs-dict policy as above so a CLI 2.x
    # JSON-array line surrounded by non-JSON noise (wrapper warnings, nvm/asdf
    # banners, future CLI debug prints) still surfaces the result event
    # instead of being silently dropped.
    for candidate in reversed(stripped.splitlines()):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            line_payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(line_payload, dict):
            return line_payload, None
        if isinstance(line_payload, list):
            for item in reversed(line_payload):
                if isinstance(item, dict) and item.get("type") == "result":
                    return item, None
            # fall through: this line was an array without a result event,
            # but earlier lines might still carry one — keep scanning.

    return None, "Claude CLI did not return JSON output"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def job_state_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def is_pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") or {}
    return {
        "jobId": job.get("jobId"),
        "status": job.get("status"),
        "done": job.get("status") in TERMINAL_JOB_STATES,
        "threadId": result.get("threadId"),
        "response": result.get("response"),
        "model": result.get("model"),
        "duration_ms": result.get("duration_ms"),
        "stop_reason": result.get("stop_reason"),
        "error": job.get("error"),
        "createdAt": job.get("createdAt"),
        "startedAt": job.get("startedAt"),
        "completedAt": job.get("completedAt"),
        "updatedAt": job.get("updatedAt"),
        "resumeHint": "Call review_status with this jobId until done=true.",
    }


def build_command(
    prompt: str,
    *,
    session_id: str | None = None,
    model: str | None = None,
    system: str | None = None,
    tools: str | None = None,
) -> list[str]:
    bin_path = find_claude_bin()
    if not bin_path:
        raise FileNotFoundError(f"Claude CLI not found: {CLAUDE_BIN}")

    cmd = [bin_path, "-p", prompt, "--output-format", "json", "--permission-mode", "plan"]

    if session_id:
        cmd.extend(["--resume", session_id])

    selected_model = model or DEFAULT_MODEL
    if selected_model:
        cmd.extend(["--model", selected_model])

    selected_system = system or DEFAULT_SYSTEM
    if selected_system:
        cmd.extend(["--system-prompt", selected_system])

    selected_tools = DEFAULT_TOOLS if tools is None else tools
    cmd.extend(["--tools", selected_tools])
    return cmd


def run_claude_review(
    prompt: str,
    *,
    session_id: str | None = None,
    model: str | None = None,
    system: str | None = None,
    tools: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        cmd = build_command(
            prompt,
            session_id=session_id,
            model=model,
            system=system,
            tools=tools,
        )
    except FileNotFoundError as exc:
        return None, str(exc)

    debug_log(f"RUN {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=DEFAULT_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"Claude review timed out after {DEFAULT_TIMEOUT_SEC} seconds"

    payload, parse_error = parse_claude_json(result.stdout)
    if parse_error:
        stderr = result.stderr.strip()
        message = parse_error if not stderr else f"{parse_error}. stderr: {stderr}"
        return None, message

    if payload is None:
        return None, "Failed to parse Claude CLI output"
    if result.returncode != 0 or payload.get("is_error"):
        # Claude CLI 2.x emits structured error events without `result` / `error`
        # fields — the diagnostic text lives in an `errors` list (e.g.
        # subtype="error_max_budget_usd", errors=["Reached maximum budget ..."]).
        # Surface it explicitly; otherwise the user sees only the generic
        # "Claude review failed" and loses the actionable message.
        errors_list = payload.get("errors")
        errors_text = "; ".join(str(e) for e in errors_list) if isinstance(errors_list, list) and errors_list else ""
        message = str(
            payload.get("result")
            or payload.get("error")
            or errors_text
            or result.stderr.strip()
            or "Claude review failed"
        )
        return None, message

    thread_id = payload.get("session_id")
    response_text = str(payload.get("result", "")).strip()
    model_name = payload.get("model", "") or model or DEFAULT_MODEL
    return {
        "threadId": thread_id,
        "response": response_text,
        "model": model_name,
        "duration_ms": payload.get("duration_ms"),
        "stop_reason": payload.get("stop_reason"),
    }, None


def start_async_review(
    prompt: str,
    *,
    session_id: str | None = None,
    model: str | None = None,
    system: str | None = None,
    tools: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    job_id = uuid.uuid4().hex
    created_at = utc_now()
    job = {
        "jobId": job_id,
        "status": "queued",
        "createdAt": created_at,
        "startedAt": None,
        "completedAt": None,
        "updatedAt": created_at,
        "error": None,
        "result": None,
        "workerPid": None,
        "request": {
            "prompt": prompt,
            "threadId": session_id,
            "model": model,
            "system": system,
            "tools": tools,
        },
    }

    job_path = job_state_path(job_id)
    write_json(job_path, job)

    try:
        worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--run-job", job_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        job["status"] = "failed"
        job["completedAt"] = utc_now()
        job["updatedAt"] = job["completedAt"]
        job["error"] = f"Failed to launch background review worker: {exc}"
        write_json(job_path, job)
        return None, job["error"]

    job["workerPid"] = worker.pid
    job["updatedAt"] = utc_now()
    write_json(job_path, job)
    debug_log(f"JOB_START job_id={job_id} worker_pid={worker.pid}")
    return serialize_job(job), None


def get_review_status(job_id: str, *, wait_seconds: int = 0) -> tuple[dict[str, Any] | None, str | None]:
    job_path = job_state_path(job_id)
    if not job_path.exists():
        return None, f"Unknown jobId: {job_id}"

    deadline = time.monotonic() + max(wait_seconds, 0)
    while True:
        job = read_json(job_path)
        if job.get("status") in {"queued", "running"} and not is_pid_alive(job.get("workerPid")):
            job["status"] = "failed"
            job["error"] = "Background review worker exited before writing a final result"
            job["completedAt"] = utc_now()
            job["updatedAt"] = job["completedAt"]
            write_json(job_path, job)
        if job.get("status") in TERMINAL_JOB_STATES:
            return serialize_job(job), None
        if time.monotonic() >= deadline:
            return serialize_job(job), None
        time.sleep(min(0.5, max(deadline - time.monotonic(), 0.0)))


def run_async_job(job_id: str) -> int:
    job_path = job_state_path(job_id)
    if not job_path.exists():
        debug_log(f"JOB_MISSING job_id={job_id}")
        return 1

    job = read_json(job_path)
    job["status"] = "running"
    job["startedAt"] = utc_now()
    job["updatedAt"] = job["startedAt"]
    job["workerPid"] = os.getpid()
    write_json(job_path, job)
    debug_log(f"JOB_RUNNING job_id={job_id} worker_pid={os.getpid()}")

    request = job.get("request") or {}
    try:
        payload, error = run_claude_review(
            str(request.get("prompt", "")),
            session_id=request.get("threadId"),
            model=request.get("model"),
            system=request.get("system"),
            tools=request.get("tools"),
        )
    except Exception as exc:
        payload = None
        error = f"Background review crashed: {exc}"
        debug_log(traceback.format_exc())

    finished_at = utc_now()
    job = read_json(job_path)
    job["updatedAt"] = finished_at
    job["completedAt"] = finished_at
    if error:
        job["status"] = "failed"
        job["error"] = error
        job["result"] = None
        debug_log(f"JOB_FAILED job_id={job_id} error={error}")
        write_json(job_path, job)
        return 1

    job["status"] = "completed"
    job["error"] = None
    job["result"] = payload
    debug_log(f"JOB_COMPLETED job_id={job_id} thread_id={(payload or {}).get('threadId')}")
    write_json(job_path, job)
    return 0


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


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})
    debug_log(f"REQUEST id={request_id!r} method={method} params={json.dumps(params, ensure_ascii=False)}")

    if request_id is None:
        if method in {"notifications/initialized", "initialized"}:
            return None
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}

    if method == "resources/templates/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resourceTemplates": []}}

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
                        "description": "Run a fresh Claude Code review and return JSON containing threadId and response.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "Reviewer prompt"},
                                "system": {"type": "string", "description": "Optional system prompt"},
                                "model": {"type": "string", "description": "Optional Claude model override"},
                                "tools": {"type": "string", "description": "Optional Claude tools override, empty string disables tools"},
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_reply",
                        "description": "Continue a previous Claude Code review session using threadId/session_id.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "threadId": {"type": "string", "description": "Claude session id from a previous review call"},
                                "thread_id": {"type": "string", "description": "Alias of threadId"},
                                "prompt": {"type": "string", "description": "Follow-up reviewer prompt"},
                                "system": {"type": "string", "description": "Optional system prompt override"},
                                "model": {"type": "string", "description": "Optional Claude model override"},
                                "tools": {"type": "string", "description": "Optional Claude tools override, empty string disables tools"},
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_start",
                        "description": "Start a background Claude Code review job and return a resumable jobId immediately.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "Reviewer prompt"},
                                "system": {"type": "string", "description": "Optional system prompt"},
                                "model": {"type": "string", "description": "Optional Claude model override"},
                                "tools": {"type": "string", "description": "Optional Claude tools override, empty string disables tools"},
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_reply_start",
                        "description": "Start a background follow-up review job in an existing Claude thread and return a resumable jobId immediately.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "threadId": {"type": "string", "description": "Claude session id from a previous review call"},
                                "thread_id": {"type": "string", "description": "Alias of threadId"},
                                "prompt": {"type": "string", "description": "Follow-up reviewer prompt"},
                                "system": {"type": "string", "description": "Optional system prompt override"},
                                "model": {"type": "string", "description": "Optional Claude model override"},
                                "tools": {"type": "string", "description": "Optional Claude tools override, empty string disables tools"},
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_status",
                        "description": "Check whether a background review job has finished and fetch the final result when available.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "jobId": {"type": "string", "description": "Background review job id"},
                                "job_id": {"type": "string", "description": "Alias of jobId"},
                                "waitSeconds": {"type": "integer", "description": "Optional bounded wait before returning status"},
                            },
                            "required": ["jobId"],
                        },
                    },
                ]
            },
        }

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}

        if name == "review":
            payload, error = run_claude_review(
                str(args.get("prompt", "")),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_reply":
            thread_id = args.get("threadId") or args.get("thread_id")
            if not thread_id:
                return tool_error(request_id, "threadId or thread_id is required")
            payload, error = run_claude_review(
                str(args.get("prompt", "")),
                session_id=str(thread_id),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_start":
            payload, error = start_async_review(
                str(args.get("prompt", "")),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_reply_start":
            thread_id = args.get("threadId") or args.get("thread_id")
            if not thread_id:
                return tool_error(request_id, "threadId or thread_id is required")
            payload, error = start_async_review(
                str(args.get("prompt", "")),
                session_id=str(thread_id),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_status":
            job_id = args.get("jobId") or args.get("job_id")
            if not job_id:
                return tool_error(request_id, "jobId or job_id is required")
            wait_seconds_raw = args.get("waitSeconds", 0)
            try:
                wait_seconds = int(wait_seconds_raw)
            except (TypeError, ValueError):
                return tool_error(request_id, "waitSeconds must be an integer")
            payload, error = get_review_status(str(job_id), wait_seconds=max(wait_seconds, 0))
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    _configure_stdio_for_mcp()

    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        raise SystemExit(run_async_job(sys.argv[2]))

    debug_log(f"=== {SERVER_NAME} starting ===")
    while True:
        try:
            request = read_message()
            if request is None:
                debug_log("EOF")
                break
            response = handle_request(request)
            if response is not None:
                send_response(response)
        except Exception:
            debug_log(traceback.format_exc())
            break


if __name__ == "__main__":
    main()
