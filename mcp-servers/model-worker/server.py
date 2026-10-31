#!/usr/bin/env python3
"""File-author MCP over native CLI sessions. No shell or inherited MCP tools.

The allowed roots restrict admission to work directories. Native CLI permissions
restrict available tools; neither constitutes an OS filesystem sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SERVER_NAME = "model-worker"
STATE_DIR = (
    Path(
        os.environ.get(
            "MODEL_WORKER_STATE_DIR", str(Path.home() / ".codex/state/model-worker")
        )
    )
    .expanduser()
    .resolve()
)
BACKENDS = {"antigravity", "grok", "claude-code"}
EFFORTS = {
    "antigravity": {"low", "medium", "high", "xhigh", "max"},
    "grok": {"low", "medium", "high", "xhigh"},
    "claude-code": {"low", "medium", "high", "max"},
}
DEFAULT_EFFORT = {"antigravity": "high", "grok": "xhigh", "claude-code": "high"}
_stdout_lock = threading.Lock()
_helpers: dict[str, Any] = {}


def helper(name: str) -> Any:
    """Reuse parsers from private module instances; reviewer defaults stay intact."""
    if name not in _helpers:
        path = Path(__file__).resolve().parent.parent / name / "server.py"
        spec = importlib.util.spec_from_file_location(
            "model_worker_" + name.replace("-", "_"), path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load CLI parser")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _helpers[name] = module
    return _helpers[name]


def send_message(message: dict[str, Any]) -> None:
    with _stdout_lock:
        sys.stdout.write(
            json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()


def error_response(request_id: Any, message: str, code: int = -32602) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def validate_cwd(value: Any) -> str:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("cwd must be an absolute existing directory")
    cwd = Path(value).resolve()
    if not cwd.is_dir():
        raise ValueError("cwd must be an absolute existing directory")
    try:
        roots = json.loads(os.environ.get("MODEL_WORKER_ALLOWED_ROOTS", "[]"))
    except ValueError:
        raise ValueError(
            "MODEL_WORKER_ALLOWED_ROOTS must be a JSON array of absolute directories"
        ) from None
    if (
        not isinstance(roots, list)
        or not roots
        or any(
            not isinstance(p, str) or not Path(p).is_absolute() or not Path(p).is_dir()
            for p in roots
        )
    ):
        raise ValueError(
            "MODEL_WORKER_ALLOWED_ROOTS must contain existing absolute directories"
        )
    if not any(cwd.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError("cwd is outside MODEL_WORKER_ALLOWED_ROOTS")
    if cwd.is_relative_to(STATE_DIR) or STATE_DIR.is_relative_to(cwd):
        raise ValueError("worker state must not overlap cwd")
    return str(cwd)


def normalize_options(args: dict[str, Any]) -> dict[str, Any]:
    if set(args) - {"prompt", "cwd", "backend", "model", "effort", "timeout_sec"}:
        raise ValueError("unsupported worker arguments")
    backend, model = args.get("backend"), args.get("model")
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError("backend must be antigravity, grok or claude-code")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a nonempty string")
    effort = args.get("effort", DEFAULT_EFFORT[backend])
    if not isinstance(effort, str) or effort not in EFFORTS[backend]:
        raise ValueError("unsupported effort for " + backend)
    timeout = args.get("timeout_sec", 3600)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout_sec must be a positive finite number")
    return {
        "backend": backend,
        "model": model,
        "effort": effort,
        "cwd": validate_cwd(args.get("cwd")),
        "timeout_sec": timeout,
    }


def thread_file(thread_id: Any) -> Path:
    try:
        if not isinstance(thread_id, str) or str(uuid.UUID(thread_id)) != thread_id:
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError("threadId must be a canonical UUID") from None
    return STATE_DIR / "threads" / (thread_id + ".json")


def remember_thread(thread_id: str, options: dict[str, Any]) -> None:
    path = thread_file(thread_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="thread-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(options, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def recall_thread(thread_id: Any) -> dict[str, Any]:
    path = thread_file(thread_id)
    if path.is_symlink():
        raise ValueError("invalid saved worker settings")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("unknown worker thread; start with worker") from None
    if not isinstance(data, dict):
        raise ValueError("invalid saved worker settings")  # noqa: TRY004 - MCP invalid-params contract
    return normalize_options(data)


def claude_environment() -> dict[str, str]:
    """Load only provider authentication at child-exec time, never into state."""
    env = os.environ.copy()
    explicit = os.environ.get("MODEL_WORKER_CLAUDE_SETTINGS")
    path = (
        Path(explicit).expanduser()
        if explicit
        else Path.home() / ".claude/settings.json"
    )
    if not path.is_file() and not explicit:
        return env
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        provider = settings.get("env", {})
        if not isinstance(provider, dict):
            raise TypeError
        for key in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_CUSTOM_HEADERS",
        ):
            if key in provider:
                if not isinstance(provider[key], str):
                    raise ValueError
                env[key] = provider[key]
    except (OSError, ValueError, TypeError, AttributeError):
        raise ValueError("could not load Claude provider settings") from None
    return env


def build_argv(
    opts: dict[str, Any], prompt_path: Path, log_path: Path, thread_id: str | None
) -> list[str]:
    backend = opts["backend"]
    if backend == "antigravity":
        argv = [
            os.environ.get("AGY_BIN", "agy"),
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--model",
            opts["model"],
            "--agent",
            "aris-model-worker",
            "--sandbox",
            "--mode",
            "accept-edits",
            "--disable-slash-commands",
            "--print-timeout",
            f"{opts['timeout_sec']:g}s",
            "--log-file",
            str(log_path),
        ]
        if thread_id:
            argv += ["--conversation", thread_id]
        effort_flag = "--effort"
    elif backend == "grok":
        argv = [
            os.environ.get("GROK_BIN", "grok"),
            "--prompt-file",
            str(prompt_path),
            "--output-format",
            "streaming-messages-json",
            "--resume" if thread_id else "--session-id",
            thread_id or str(uuid.uuid4()),
            "--model",
            opts["model"],
            "--cwd",
            opts["cwd"],
            "--sandbox",
            "workspace",
            "--tools",
            "read_file,grep,list_dir,write,search_replace",
            "--permission-mode",
            "dontAsk",
            "--no-plan",
            "--no-subagents",
            "--disable-web-search",
            "--allow",
            "Read",
            "--allow",
            "Grep",
            "--allow",
            "Edit(./**)",
            "--deny",
            "MCPTool",
        ]
        effort_flag = "--reasoning-effort"
    else:
        argv = [
            os.environ.get("CLAUDE_BIN", "claude"),
            "-p",
            "--output-format",
            "json",
            "--restricted",
            "--bare",
            "--disable-slash-commands",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--tools",
            "Read,Glob,Grep,Edit,Write",
            "--allowedTools",
            "Read,Glob,Grep,Edit,Write",
            "--model",
            opts["model"],
        ]
        argv += [
            "--resume" if thread_id else "--session-id",
            thread_id or str(uuid.uuid4()),
        ]
        effort_flag = "--effort"
    if opts["effort"] is not None:
        argv += [effort_flag, opts["effort"]]
    return argv


def execute(
    argv: list[str],
    opts: dict[str, Any],
    prompt_path: Path,
    request_id: Any,
    token: Any,
    inbox: queue.Queue,
    deferred: list,
) -> tuple[str, int | None, str | None, str]:
    """Single child per server, with responsive ping/cancel and process-group cleanup."""
    env = (
        claude_environment() if opts["backend"] == "claude-code" else os.environ.copy()
    )
    try:
        with prompt_path.open("rb") as stream:
            proc = subprocess.Popen(
                argv,
                cwd=opts["cwd"],
                env=env,
                stdin=stream if opts["backend"] != "grok" else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=(os.name == "posix"),
            )
    except OSError as exc:
        return "", None, "could not start " + opts["backend"] + " CLI: " + str(exc), ""
    # communicate drains both pipes; control stays in this thread for MCP service.
    output: list[bytes] = []
    diagnostics: list[bytes] = []

    def collect() -> None:
        stdout, stderr = proc.communicate()
        output.append(stdout)
        diagnostics.append(stderr)

    collector = threading.Thread(target=collect, daemon=True)
    collector.start()
    started, last_progress, count = time.monotonic(), time.monotonic(), 0
    failure, stopped_at = None, None
    while collector.is_alive():
        try:
            msg = inbox.get(timeout=0.05)
        except queue.Empty:
            msg = {}
        method = msg.get("method")
        if method == "ping" and msg.get("id") is not None:
            send_message({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        elif (
            method == "notifications/cancelled"
            and msg.get("params", {}).get("requestId") == request_id
        ):
            failure = failure or "cancelled by client; no automatic retry"
        elif msg.get("__eof__"):
            failure = failure or "MCP client disconnected; no automatic retry"
            deferred.append(msg)
        elif msg:
            deferred.append(msg)
        now = time.monotonic()
        if now - started >= opts["timeout_sec"]:
            failure = (
                failure
                or f"{opts['backend']} timed out after {opts['timeout_sec']:g}s; no automatic retry"
            )
        if failure:
            try:
                force = stopped_at is not None and now - stopped_at >= 2
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
                elif force:
                    proc.kill()
                else:
                    proc.terminate()
                stopped_at = stopped_at or now
            except ProcessLookupError:
                pass
        if token is not None and now - last_progress >= 15:
            count += 1
            send_message(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/progress",
                    "params": {
                        "progressToken": token,
                        "progress": count,
                        "message": f"working ({int(now - started)}s)",
                    },
                }
            )
            last_progress = now
    collector.join()
    stderr_tail = (
        diagnostics[0].decode("utf-8", errors="replace")[-2000:] if diagnostics else ""
    )
    # SDK diagnostics can include a credential value. Never return those values.
    for key, value in env.items():
        if value and any(
            secret in key for secret in ("API_KEY", "AUTH_TOKEN", "CUSTOM_HEADERS")
        ):
            stderr_tail = stderr_tail.replace(value, "[redacted]")
    if diagnostics and any(
        marker in diagnostics[0].lower()
        for marker in (b"unknown tool", b"unrecognized tool")
    ):
        failure = (
            failure
            or "CLI reported an unknown tool; file-only configuration was not accepted"
        )
    return (
        (output[0].decode("utf-8", errors="replace") if output else ""),
        proc.returncode,
        failure,
        stderr_tail,
    )


def parse_outcome(backend: str, raw: str, log_path: Path, cwd: str) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "threadId": None,
        "content": "",
        "model": None,
        "modelSource": None,
        "effort": None,
        "effortSource": None,
        "status": None,
        "error": None,
    }
    if backend == "claude-code":
        parser = helper("claude-review")
        result, error = parser.parse_claude_json(raw)
        if error or not result:
            outcome["error"] = error or "missing terminal result"
            return outcome
        outcome.update(
            threadId=result.get("session_id"),
            content=result.get("result"),
            status=result.get("stop_reason"),
        )
        outcome["model"], outcome["modelSource"], outcome["reportedModels"] = (
            parser.reported_model(result)
        )
        if "permission_denials" in result:
            outcome["permissionDenials"] = result["permission_denials"]
        if (
            result.get("type") != "result"
            or result.get("is_error")
            or result.get("subtype") != "success"
            or outcome["status"] != "end_turn"
        ):
            outcome["error"] = "Claude CLI did not complete a successful end_turn"
    else:
        completed, failed, seen_id = False, False, None
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if backend == "antigravity":
                kind = event.get("event")
                if kind == "init":
                    native = event.get("conversation_id")
                    outcome["model"] = (event.get("init") or {}).get("model")
                    outcome["modelSource"] = "cli_init" if outcome["model"] else None
                elif kind == "result":
                    result = event.get("result") or {}
                    native = result.get("conversation_id")
                    outcome.update(
                        content=result.get("response"), status=result.get("status")
                    )
                    completed = (
                        bool(native)
                        and outcome["status"] == "SUCCESS"
                        and not result.get("error")
                    )
                    failed = failed or not completed
                elif kind == "error":
                    failed = True
                    native = None
                else:
                    native = None
            else:
                kind, native = event.get("type"), event.get("session_id")
                if kind == "assistant":
                    model = (event.get("message") or {}).get("model")
                    if model:
                        outcome.update(model=model, modelSource="cli_assistant")
                elif kind == "result":
                    outcome.update(
                        content=event.get("result"), status=event.get("stop_reason")
                    )
                    models = list((event.get("modelUsage") or {}).keys())
                    if len(models) == 1:
                        outcome.update(model=models[0], modelSource="cli_model_usage")
                    completed = (
                        bool(native)
                        and event.get("subtype") == "success"
                        and not event.get("is_error")
                        and outcome["status"] == "end_turn"
                    )
                    failed = failed or not completed
                elif kind == "error":
                    failed = True
            if native:
                failed = failed or (seen_id is not None and native != seen_id)
                seen_id = native
                outcome["threadId"] = native
        if backend == "antigravity":
            outcome["selectedModelLabel"], outcome["effort"] = helper(
                "antigravity-exec"
            ).selected_variant(log_path)
            if outcome["effort"]:
                outcome["effortSource"] = "cli_selected_model_variant"
        elif outcome["threadId"]:
            outcome["effort"] = helper("grok-exec").runtime_effort(
                outcome["threadId"], cwd
            )
            if outcome["effort"]:
                outcome["effortSource"] = "native_session_summary"
        if failed or not completed:
            outcome["error"] = (
                backend + " CLI did not complete a successful terminal result"
            )
    if not isinstance(outcome["content"], str) or not outcome["content"].strip():
        outcome["error"] = outcome["error"] or "CLI returned an empty final response"
    return outcome


TOOLS = [
    {
        "name": "worker",
        "description": "Start a file-author native CLI session with file read/write tools. No shell or inherited MCP tools. Returns threadId for worker_reply; CLI completion is not artifact acceptance.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string"},
                "cwd": {"type": "string"},
                "backend": {"type": "string", "enum": sorted(BACKENDS)},
                "model": {"type": "string"},
                "effort": {"type": "string"},
                "timeout_sec": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["prompt", "cwd", "backend", "model"],
        },
    },
    {
        "name": "worker_reply",
        "description": "Revise files in a bridge-created native session. Preserves backend, model, effort, cwd, timeout and tools, including after bridge restart.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "threadId": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["threadId", "prompt"],
        },
    },
]


def handle_call(
    request: dict[str, Any], inbox: queue.Queue, deferred: list
) -> dict[str, Any]:
    request_id = request.get("id")
    params = request.get("params") or {}
    args = params.get("arguments") or {}
    try:
        if (
            not isinstance(args, dict)
            or not isinstance(args.get("prompt"), str)
            or not args["prompt"].strip()
        ):
            raise ValueError("prompt must be a nonempty string")
        if params.get("name") == "worker":
            opts, thread_id = normalize_options(args), None
        elif params.get("name") == "worker_reply":
            if set(args) != {"prompt", "threadId"}:
                raise ValueError("worker_reply accepts only threadId and prompt")
            thread_id = args["threadId"]
            opts = recall_thread(thread_id)
        else:
            return error_response(request_id, "unknown tool", -32601)
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="call-", dir=STATE_DIR) as temporary:
            prompt_path, log_path = (
                Path(temporary) / "prompt",
                Path(temporary) / "cli.log",
            )
            prompt = args["prompt"]
            if opts["backend"] == "antigravity":
                prompt = (
                    json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
                )
            prompt_path.write_text(prompt, encoding="utf-8")
            prompt_path.chmod(0o600)
            argv = build_argv(opts, prompt_path, log_path, thread_id)
            expected_id = thread_id
            if "--session-id" in argv:
                expected_id = argv[argv.index("--session-id") + 1]
            raw, code, failure, diagnostics = execute(
                argv,
                opts,
                prompt_path,
                request_id,
                (params.get("_meta") or {}).get("progressToken"),
                inbox,
                deferred,
            )
            outcome = parse_outcome(opts["backend"], raw, log_path, opts["cwd"])
        outcome["error"] = (
            failure
            or (
                f"{opts['backend']} CLI exited with status {code}"
                if code != 0
                else None
            )
            or outcome["error"]
        )
        if outcome["error"] and diagnostics.strip():
            outcome["error"] += "\n" + diagnostics.strip()
        if outcome["effort"] is not None and outcome["effort"] != opts["effort"]:
            outcome["error"] = (
                outcome["error"] or "CLI reported a different effort than requested"
            )
        if (
            opts["backend"] == "antigravity"
            and outcome["model"] is not None
            and outcome["model"] != opts["model"]
        ):
            outcome["error"] = (
                outcome["error"]
                or "Antigravity CLI reported a different model than requested"
            )
        returned_id = outcome["threadId"]
        if returned_id:
            try:
                thread_file(returned_id)
                valid_id = True
            except ValueError:
                valid_id = False
                outcome["error"] = "CLI did not return a valid native session UUID"
            if valid_id and expected_id and expected_id != returned_id:
                outcome["error"] = "CLI returned a different native session ID"
            elif valid_id:
                remember_thread(returned_id, opts)
        elif not outcome["error"]:
            outcome["error"] = "CLI did not return a native session ID"
        outcome.update(
            backend=opts["backend"],
            requestedModel=opts["model"],
            requestedEffort=opts["effort"],
            cwd=opts["cwd"],
            exitCode=code,
        )
        message = outcome["error"] or outcome["content"]
        if isinstance(returned_id, str):
            message = "threadId: " + returned_id + "\n\n" + message
        result = {
            "content": [{"type": "text", "text": message}],
            "structuredContent": outcome,
        }
        if outcome["error"]:
            result["isError"] = True
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except ValueError as exc:
        return error_response(request_id, str(exc))


def handle_request(
    request: dict[str, Any], inbox: queue.Queue, deferred: list
) -> dict[str, Any] | None:
    request_id, method = request.get("id"), request.get("method")
    if request_id is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": (request.get("params") or {}).get(
                "protocolVersion", "2025-06-18"
            ),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        return handle_call(request, inbox, deferred)
    else:
        return error_response(request_id, "method not found", -32601)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    inbox: queue.Queue = queue.Queue()
    deferred: list = []

    def read() -> None:
        for line in sys.stdin:
            try:
                message = json.loads(line)
                if isinstance(message, dict):
                    inbox.put(message)
            except ValueError:
                pass
        inbox.put({"__eof__": True})

    threading.Thread(target=read, daemon=True).start()
    while True:
        request = deferred.pop(0) if deferred else inbox.get()
        if request.get("__eof__"):
            return
        try:
            response = handle_request(request, inbox, deferred)
        except Exception:  # noqa: BLE001 - isolate requests at the JSON-RPC protocol boundary
            response = error_response(
                request.get("id"), "internal worker error", -32603
            )
        if response is not None:
            send_message(response)


if __name__ == "__main__":
    main()
