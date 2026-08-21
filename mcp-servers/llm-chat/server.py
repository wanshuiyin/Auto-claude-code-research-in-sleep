#!/usr/bin/env python3
"""Generic LLM Chat MCP Server - Supports any OpenAI-compatible API

Environment Variables:
    LLM_API_KEY         - API key (required)
    LLM_BASE_URL        - API base URL (default: https://api.openai.com/v1)
    LLM_MODEL           - Model name (default: gpt-4o)
    LLM_FALLBACK_MODEL  - Fallback model on 504 timeout (default: gpt-4o)
    LLM_SERVER_NAME     - Server name for MCP (default: llm-chat)
    LLM_REVIEW_FALLBACK_ENABLED
                        - Expose review/review_reply tools when true (default: false)

Supported Providers (examples):
    OpenAI:      LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o
    DeepSeek:    LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-chat
    Kimi:        LLM_BASE_URL=https://api.moonshot.cn/v1 LLM_MODEL=moonshot-v1-32k
    MiniMax:     LLM_BASE_URL=https://api.minimax.io/v1 LLM_MODEL=MiniMax-M3
"""

import datetime
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
import httpx

_stdio_initialized = False


def _init_stdio():
    """Rebind stdio to raw unbuffered binary streams for MCP framing.

    Deferred into a function (called at the top of main()) so that merely
    IMPORTING this module has no stdio side effects. os.fdopen(fileno) defaults
    to closefd=True and thus seizes ownership of the fd; doing that at import
    time under a test harness that captures stdio (pytest fd-capture) closes the
    harness's capture fd and corrupts capture for every subsequent test. Real
    server launch (python server.py) still calls this first via main(), so
    runtime behavior is unchanged. Idempotent."""
    global _stdio_initialized
    if _stdio_initialized:
        return
    # Force unbuffered stdout/stdin
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'wb', buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', buffering=0)
    _stdio_initialized = True

# Configuration from environment
API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gpt-4o")
SERVER_NAME = os.environ.get("LLM_SERVER_NAME", "llm-chat")
REVIEW_FALLBACK_ENABLED = os.environ.get(
    "LLM_REVIEW_FALLBACK_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}

# Debug logging
DEBUG_LOG = os.path.join(tempfile.gettempdir(), f"{SERVER_NAME}-mcp-debug.log")

def debug_log(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{datetime.datetime.now()}: {msg}\n")
            f.flush()
    except Exception:
        pass

def log_error(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{datetime.datetime.now()}: ERROR: {msg}\n")
    except Exception:
        pass

debug_log(f"=== {SERVER_NAME} MCP Server Starting (v2.2) ===")
debug_log(f"BASE_URL: {BASE_URL}")
debug_log(f"MODEL: {DEFAULT_MODEL}")
debug_log(f"FALLBACK_MODEL: {FALLBACK_MODEL}")
debug_log(f"REVIEW_FALLBACK_ENABLED: {REVIEW_FALLBACK_ENABLED}")
debug_log(f"API_KEY set: {bool(API_KEY)}")

_use_ndjson = False
_review_threads = {}

def send_response(response):
    global _use_ndjson
    json_str = json.dumps(response, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')

    if _use_ndjson:
        output = json_bytes + b'\n'
    else:
        header = f"Content-Length: {len(json_bytes)}\r\n\r\n".encode('utf-8')
        output = header + json_bytes

    sys.stdout.write(output)
    sys.stdout.flush()

def _call_llm_detailed(messages, model=None):
    """Call LLM Chat Completions API and return content, error, actual model."""
    if not API_KEY:
        return None, "LLM_API_KEY environment variable not set", None

    use_model = model or DEFAULT_MODEL
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    # Try: original model → retry same model → fallback model.
    # This retrying behavior is intentionally legacy-chat-only. Verdict-bearing
    # review/review_reply calls use _call_llm_review_once below so ambiguous
    # failures can never duplicate a paid review or produce conflicting verdicts.
    for attempt in range(3):
        current_model = use_model if attempt < 2 else FALLBACK_MODEL
        payload = {
            "model": current_model,
            "messages": messages,
            "max_tokens": 4096
        }

        debug_log(f"Calling LLM API (attempt {attempt + 1}): model={current_model}")

        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(url, headers=headers, json=payload)

                if response.status_code == 504:
                    debug_log(f"504 Gateway Timeout on attempt {attempt + 1} with model {current_model}")
                    if attempt < 2:
                        continue  # retry or fallback

                if response.status_code != 200:
                    error_msg = f"API error {response.status_code}: {response.text[:500]}"
                    debug_log(f"API error: {error_msg}")
                    return None, error_msg, None

                data = response.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    return None, f"Unexpected API response structure: {e}", None

                # Prefer the model identity reported by the provider. If absent,
                # use the exact model id sent in this successful request.
                actual_model = str(data.get("model") or current_model).strip()

                if current_model != use_model:
                    fallback_note = f"\n\n[Note: Used fallback model {current_model} after 504 timeout with {use_model}]"
                    content = fallback_note + "\n" + content
                    debug_log(f"API success with fallback model {actual_model}, response length: {len(content)}")
                elif attempt > 0:
                    debug_log(f"API success on retry (attempt {attempt + 1}), response length: {len(content)}")
                else:
                    debug_log(f"API success, response length: {len(content)}")
                return content, None, actual_model
        except Exception as e:
            debug_log(f"API exception on attempt {attempt + 1}: {str(e)}")
            if attempt == 2:
                return None, str(e), None

    return None, "All attempts failed with 504 Gateway Timeout", None

def call_llm(messages, model=None):
    """Backward-compatible two-value wrapper for the existing chat tool."""
    content, error, _actual_model = _call_llm_detailed(messages, model)
    return content, error


def _call_llm_review_once(messages, model=None):
    """Single-attempt, fail-closed call for verdict-bearing reviewer tools.

    Once the HTTP request is dispatched, a timeout, 504, malformed response, or
    transport exception is ambiguous: the remote reviewer may already have run.
    Never retry or switch to FALLBACK_MODEL here. Surface the error so the
    orchestrator/gate records REVIEW_UNAVAILABLE instead of issuing a duplicate
    paid review with a potentially conflicting verdict.
    """
    if not API_KEY:
        return None, "LLM_API_KEY environment variable not set", None

    use_model = model or DEFAULT_MODEL
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": use_model,
        "messages": messages,
        "max_tokens": 4096
    }

    debug_log(f"Calling verdict-bearing LLM review once: model={use_model}")
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                error_msg = f"API error {response.status_code}: {response.text[:500]}"
                debug_log(f"Review API error (no retry): {error_msg}")
                return None, error_msg, None

            try:
                data = response.json()
            except Exception as exc:
                error_msg = f"Invalid API JSON response: {exc}"
                debug_log(f"Review API parse error (no retry): {error_msg}")
                return None, error_msg, None

            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                error_msg = f"Unexpected API response structure: {exc}"
                debug_log(f"Review API structure error (no retry): {error_msg}")
                return None, error_msg, None

            actual_model = str(data.get("model") or use_model).strip()
            debug_log(
                f"Verdict-bearing API success: model={actual_model}, "
                f"response length={len(content)}"
            )
            return content, None, actual_model
    except Exception as exc:
        debug_log(f"Review API exception (no retry): {str(exc)}")
        return None, str(exc), None


# Coarse model families used only by the opt-in verdict-bearing review tools.
_FAMILY = [
    ("anthropic", ("claude", "opus", "sonnet", "haiku", "anthropic")),
    ("openai", ("gpt", "codex", "chatgpt", "o1", "o3", "o4", "openai")),
    ("google", ("gemini", "google", "palm", "bard")),
    ("deepseek", ("deepseek",)),
    ("zhipu", ("glm", "zhipu")),
    ("minimax", ("minimax", "abab")),
    ("moonshot", ("kimi", "moonshot")),
    ("qwen", ("qwen", "tongyi")),
    ("xiaomi", ("mimo", "xiaomi")),
    ("bytedance", ("doubao", "bytedance", "volcengine")),
    ("xai", ("grok",)),
    ("meta", ("llama",)),
    ("mistral", ("mistral", "mixtral")),
]
_SHORT = {"o1", "o3", "o4"}

def model_family(name):
    """Map a model id to a coarse family; collisions fail closed.

    Match family needles at token boundaries, mirroring review_gate.py, so a
    provider prefix such as ``ollama/deepseek-r1`` does not accidentally match
    the ``llama`` model family inside ``ollama``.
    """
    n = str(name or "").strip().lower()
    matched = set()
    for family, needles in _FAMILY:
        for needle in needles:
            suffix = "" if needle in _SHORT else r"[0-9.]*"
            pattern = rf"(^|[^a-z0-9]){re.escape(needle)}{suffix}([^a-z0-9]|$)"
            if re.search(pattern, n):
                matched.add(family)
                break
    return next(iter(matched)) if len(matched) == 1 else "unknown"

def _cross_family_error(executor_model, reviewer_model):
    executor_family = model_family(executor_model)
    reviewer_family = model_family(reviewer_model)
    if executor_family == "unknown":
        return (f"Cannot verify HTTP reviewer independence: executor_model is "
                f"missing or unrecognized ({executor_model!r})")
    if reviewer_family == "unknown":
        return f"Cannot verify HTTP reviewer model family: {reviewer_model!r}"
    if executor_family == reviewer_family:
        return (f"HTTP reviewer must use a different model family: "
                f"executor={executor_model} ({executor_family}), "
                f"reviewer={reviewer_model} ({reviewer_family})")
    return None

def _tool_success(request_id, payload):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
        }
    }

def _tool_error(request_id, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
            "isError": True
        }
    }

def _read_review_files(paths):
    """Read explicit primary artifacts that will be sent to the HTTP endpoint."""
    if paths is None:
        return ""
    if not isinstance(paths, list):
        raise ValueError("files must be an array of file paths")

    sections = []
    for raw_path in paths:
        path = Path(str(raw_path)).expanduser()
        if not path.is_file():
            raise ValueError(f"review file not found or not a regular file: {path}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ValueError(f"cannot read review file {path}: {exc}") from exc
        sections.append(
            f"\n\n--- ARIS PRIMARY ARTIFACT: {path} ---\n{text}"
            f"\n--- END ARIS PRIMARY ARTIFACT: {path} ---"
        )
    return "".join(sections)

def _review_user_content(prompt, files):
    return prompt + _read_review_files(files)

def _review_messages(history, prompt, system=""):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages

def _handle_review(arguments, request_id):
    prompt = str(arguments.get("prompt", "")).strip()
    executor_model = str(arguments.get("executor_model", "")).strip()
    model = str(arguments.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    system = str(arguments.get("system", "")).strip()
    files = arguments.get("files", [])

    if not prompt:
        return _tool_error(request_id, "prompt is required")
    if not executor_model:
        return _tool_error(request_id, "executor_model is required for cross-family review")

    try:
        user_content = _review_user_content(prompt, files)
    except ValueError as exc:
        return _tool_error(request_id, str(exc))

    content, error, actual_model = _call_llm_review_once(
        _review_messages([], user_content, system), model
    )
    if error:
        return _tool_error(request_id, error)

    independence_error = _cross_family_error(executor_model, actual_model)
    if independence_error:
        return _tool_error(request_id, independence_error)

    thread_id = uuid.uuid4().hex[:12]
    _review_threads[thread_id] = {
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": content},
        ],
        "model": model,
        "system": system,
        "executor_model": executor_model,
    }
    return _tool_success(request_id, {
        "threadId": thread_id,
        "content": content,
        "reviewer_model": actual_model,
        "reviewer_family": model_family(actual_model),
        "executor_model": executor_model,
        "executor_family": model_family(executor_model),
        "family_relation": "different",
        "independence_verified": "unverified",
    })

def _handle_review_reply(arguments, request_id):
    thread_id = str(arguments.get("threadId", "")).strip()
    prompt = str(arguments.get("prompt", "")).strip()
    if not thread_id:
        return _tool_error(request_id, "threadId is required")
    if thread_id not in _review_threads:
        return _tool_error(request_id, f"Unknown threadId: {thread_id}")
    if not prompt:
        return _tool_error(request_id, "prompt is required")

    thread = _review_threads[thread_id]
    executor_model = str(arguments.get("executor_model", thread["executor_model"])).strip()
    if executor_model != thread["executor_model"]:
        return _tool_error(request_id, "executor_model cannot change within a review thread")
    model = str(arguments.get("model", thread["model"])).strip() or thread["model"]
    if model != thread["model"]:
        return _tool_error(request_id, "reviewer model cannot change within a review thread")
    system = str(arguments.get("system", thread["system"])).strip()
    files = arguments.get("files", [])

    try:
        user_content = _review_user_content(prompt, files)
    except ValueError as exc:
        return _tool_error(request_id, str(exc))

    history = list(thread["messages"])
    content, error, actual_model = _call_llm_review_once(
        _review_messages(history, user_content, system), model
    )
    if error:
        return _tool_error(request_id, error)

    independence_error = _cross_family_error(executor_model, actual_model)
    if independence_error:
        return _tool_error(request_id, independence_error)

    thread["messages"].extend([
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": content},
    ])
    return _tool_success(request_id, {
        "threadId": thread_id,
        "content": content,
        "reviewer_model": actual_model,
        "reviewer_family": model_family(actual_model),
        "executor_model": executor_model,
        "executor_family": model_family(executor_model),
        "family_relation": "different",
        "independence_verified": "unverified",
    })

def _review_tool_definitions():
    common = {
        "prompt": {"type": "string", "description": "The substantive ARIS review prompt"},
        "executor_model": {
            "type": "string",
            "description": "Actual executor model id; required to enforce cross-family review"
        },
        "model": {"type": "string", "description": f"Reviewer model (default: {DEFAULT_MODEL})"},
        "system": {"type": "string", "description": "Optional reviewer system prompt"},
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Local primary-artifact paths to send verbatim to the HTTP reviewer"
        },
    }
    return [
        {
            "name": "review",
            "description": "Start an independent HTTP reviewer thread.",
            "inputSchema": {
                "type": "object",
                "properties": dict(common),
                "required": ["prompt", "executor_model"]
            }
        },
        {
            "name": "review_reply",
            "description": "Continue an HTTP reviewer thread with prior message history.",
            "inputSchema": {
                "type": "object",
                "properties": dict(common, threadId={
                    "type": "string",
                    "description": "threadId returned by review"
                }),
                "required": ["threadId", "prompt"]
            }
        }
    ]

def handle_request(request):
    """Handle a JSON-RPC request"""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    debug_log(f"Handling method: {method}, id: {request_id}")

    # Handle notifications (no id, no response needed)
    if request_id is None:
        if method == "notifications/initialized":
            debug_log("Client initialized successfully")
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": "2.2.0"
                }
            }
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    elif method == "tools/list":
        tools = [{
            "name": "chat",
            "description": f"Send a message to {DEFAULT_MODEL} and get a response. Use this for research reviews, code analysis, and general AI tasks.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send"
                    },
                    "model": {
                        "type": "string",
                        "description": f"Model to use (default: {DEFAULT_MODEL})"
                    },
                    "system": {
                        "type": "string",
                        "description": "Optional system prompt"
                    }
                },
                "required": ["prompt"]
            }
        }]
        if REVIEW_FALLBACK_ENABLED:
            tools.extend(_review_tool_definitions())
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools}
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "chat":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model", DEFAULT_MODEL)
            system = arguments.get("system", "")

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            debug_log(f"Tool call: chat, prompt length: {len(prompt)}")
            content, error = call_llm(messages, model)

            if error:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {error}"}],
                        "isError": True
                    }
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": content}]
                }
            }

        if tool_name == "review":
            if not REVIEW_FALLBACK_ENABLED:
                return _tool_error(
                    request_id,
                    "HTTP reviewer fallback is disabled. Set "
                    "LLM_REVIEW_FALLBACK_ENABLED=true and restart the MCP server."
                )
            return _handle_review(arguments, request_id)

        if tool_name == "review_reply":
            if not REVIEW_FALLBACK_ENABLED:
                return _tool_error(
                    request_id,
                    "HTTP reviewer fallback is disabled. Set "
                    "LLM_REVIEW_FALLBACK_ENABLED=true and restart the MCP server."
                )
            return _handle_review_reply(arguments, request_id)

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }

def read_message():
    """Read a single JSON-RPC message from stdin."""
    global _use_ndjson

    line = sys.stdin.readline()
    if not line:
        return None

    line = line.decode('utf-8').rstrip('\r\n')

    if line.lower().startswith("content-length:"):
        try:
            content_length = int(line.split(":", 1)[1].strip())
        except ValueError:
            return None

        while True:
            hdr = sys.stdin.readline()
            if not hdr:
                return None
            hdr = hdr.decode('utf-8').rstrip('\r\n')
            if hdr == "":
                break

        body = sys.stdin.read(content_length)
        try:
            return json.loads(body.decode('utf-8'))
        except Exception:
            return None

    elif line.startswith("{") or line.startswith("["):
        _use_ndjson = True
        try:
            return json.loads(line)
        except Exception:
            return None

    return None

def main():
    """Main loop - read JSON-RPC messages from stdin"""
    _init_stdio()
    debug_log("Entering main loop")

    while True:
        try:
            request = read_message()
            if request is None:
                debug_log("EOF, exiting")
                break

            response = handle_request(request)
            if response:
                send_response(response)

        except Exception as e:
            log_error(f"Exception: {e}")

    debug_log("=== Server Exiting ===")

if __name__ == "__main__":
    main()
