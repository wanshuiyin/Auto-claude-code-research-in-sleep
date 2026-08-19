#!/usr/bin/env python3
"""Generic LLM Chat MCP Server - Supports any OpenAI-compatible API.

Environment Variables:
    LLM_API_KEY         - API key (required)
    LLM_BASE_URL        - API base URL (default: https://api.openai.com/v1)
    LLM_MODEL           - Model name (default: gpt-4o)
    LLM_FALLBACK_MODEL  - Fallback model on 504 timeout (default: gpt-4o)
    LLM_SERVER_NAME     - Server name for MCP (default: llm-chat)
    LLM_REVIEW_FALLBACK_ENABLED
                        - Expose review/review_reply tools when true. Default false.

The optional review tools are intended as a fail-closed HTTP reviewer transport
for ARIS. They preserve multi-round context and return the actual model used so
the caller can enforce cross-model review. The ordinary ``chat`` tool remains
backward compatible and is always available.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import tempfile
import uuid

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
    runtime behavior is unchanged. Idempotent.
    """
    global _stdio_initialized
    if _stdio_initialized:
        return
    sys.stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)
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
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now()}: {msg}\n")
            f.flush()
    except Exception:
        pass


def log_error(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
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
_review_threads: dict[str, dict] = {}


def send_response(response):
    global _use_ndjson
    json_str = json.dumps(response, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")

    if _use_ndjson:
        output = json_bytes + b"\n"
    else:
        header = f"Content-Length: {len(json_bytes)}\r\n\r\n".encode("utf-8")
        output = header + json_bytes

    sys.stdout.write(output)
    sys.stdout.flush()


def _call_llm_detailed(messages, model=None):
    """Call Chat Completions and return (content, error, actual_model).

    The legacy ``call_llm`` wrapper below intentionally keeps its original
    two-value return contract.
    """
    if not API_KEY:
        return None, "LLM_API_KEY environment variable not set", None

    use_model = model or DEFAULT_MODEL
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    # Existing behavior: original model -> retry same model -> fallback model.
    for attempt in range(3):
        current_model = use_model if attempt < 2 else FALLBACK_MODEL
        payload = {
            "model": current_model,
            "messages": messages,
            "max_tokens": 4096,
        }

        debug_log(
            f"Calling LLM API (attempt {attempt + 1}): model={current_model}"
        )

        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(url, headers=headers, json=payload)

                if response.status_code == 504:
                    debug_log(
                        "504 Gateway Timeout on attempt "
                        f"{attempt + 1} with model {current_model}"
                    )
                    if attempt < 2:
                        continue

                if response.status_code != 200:
                    error_msg = (
                        f"API error {response.status_code}: {response.text[:500]}"
                    )
                    debug_log(f"API error: {error_msg}")
                    return None, error_msg, None

                data = response.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    return (
                        None,
                        f"Unexpected API response structure: {e}",
                        None,
                    )

                # Prefer provider-reported model identity when present, but fall
                # back to the exact model id sent in the request.
                actual_model = str(data.get("model") or current_model).strip()

                if current_model != use_model:
                    fallback_note = (
                        "\n\n[Note: Used fallback model "
                        f"{current_model} after 504 timeout with {use_model}]"
                    )
                    content = fallback_note + "\n" + content
                    debug_log(
                        "API success with fallback model "
                        f"{actual_model}, response length: {len(content)}"
                    )
                elif attempt > 0:
                    debug_log(
                        "API success on retry "
                        f"(attempt {attempt + 1}), response length: {len(content)}"
                    )
                else:
                    debug_log(
                        f"API success, response length: {len(content)}"
                    )
                return content, None, actual_model
        except Exception as e:
            debug_log(
                f"API exception on attempt {attempt + 1}: {str(e)}"
            )
            if attempt == 2:
                return None, str(e), None

    return None, "All attempts failed with 504 Gateway Timeout", None


def call_llm(messages, model=None):
    """Backward-compatible two-value Chat Completions API wrapper."""
    content, error, _actual_model = _call_llm_detailed(messages, model)
    return content, error


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
    """Map a model id to a coarse family, failing closed on collisions."""
    n = str(name or "").strip().lower()
    tokens = set(re.split(r"[^a-z0-9.]+", n))
    matched = set()
    for family, needles in _FAMILY:
        if any(
            (needle in tokens) if needle in _SHORT else (needle in n)
            for needle in needles
        ):
            matched.add(family)
    return next(iter(matched)) if len(matched) == 1 else "unknown"


def _cross_family_error(executor_model, reviewer_model):
    executor_family = model_family(executor_model)
    reviewer_family = model_family(reviewer_model)
    if executor_family == "unknown":
        return (
            "Cannot verify HTTP reviewer independence: executor_model is "
            f"missing or unrecognized ({executor_model!r})"
        )
    if reviewer_family == "unknown":
        return (
            "Cannot verify HTTP reviewer model family: "
            f"{reviewer_model!r}"
        )
    if executor_family == reviewer_family:
        return (
            "HTTP reviewer must use a different model family: "
            f"executor={executor_model} ({executor_family}), "
            f"reviewer={reviewer_model} ({reviewer_family})"
        )
    return None


def _tool_success(request_id, payload):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False),
                }
            ]
        },
    }


def _tool_error(request_id, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"error": message}, ensure_ascii=False
                    ),
                }
            ],
            "isError": True,
        },
    }


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

    if not prompt:
        return _tool_error(request_id, "prompt is required")
    if not executor_model:
        return _tool_error(
            request_id,
            "executor_model is required for cross-family review",
        )

    messages = _review_messages([], prompt, system)
    content, error, actual_model = _call_llm_detailed(messages, model)
    if error:
        return _tool_error(request_id, error)

    independence_error = _cross_family_error(
        executor_model, actual_model
    )
    if independence_error:
        return _tool_error(request_id, independence_error)

    thread_id = uuid.uuid4().hex[:12]
    _review_threads[thread_id] = {
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": content},
        ],
        "model": model,
        "system": system,
        "executor_model": executor_model,
    }
    return _tool_success(
        request_id,
        {
            "threadId": thread_id,
            "content": content,
            "reviewer_model": actual_model,
            "reviewer_family": model_family(actual_model),
            "executor_model": executor_model,
            "executor_family": model_family(executor_model),
            "independence_verified": True,
        },
    )


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
    executor_model = str(
        arguments.get("executor_model", thread["executor_model"])
    ).strip()
    model = str(arguments.get("model", thread["model"])).strip() or thread["model"]
    system = str(arguments.get("system", thread["system"])).strip()
    if not executor_model:
        return _tool_error(
            request_id,
            "executor_model is required for cross-family review",
        )

    history = list(thread["messages"])
    messages = _review_messages(history, prompt, system)
    content, error, actual_model = _call_llm_detailed(messages, model)
    if error:
        return _tool_error(request_id, error)

    independence_error = _cross_family_error(
        executor_model, actual_model
    )
    if independence_error:
        return _tool_error(request_id, independence_error)

    thread["messages"].extend(
        [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": content},
        ]
    )
    return _tool_success(
        request_id,
        {
            "threadId": thread_id,
            "content": content,
            "reviewer_model": actual_model,
            "reviewer_family": model_family(actual_model),
            "executor_model": executor_model,
            "executor_family": model_family(executor_model),
            "independence_verified": True,
        },
    )


def _chat_tool_definition():
    return {
        "name": "chat",
        "description": (
            f"Send a message to {DEFAULT_MODEL} and get a response. "
            "Use this for research reviews, code analysis, and general AI tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt to send",
                },
                "model": {
                    "type": "string",
                    "description": f"Model to use (default: {DEFAULT_MODEL})",
                },
                "system": {
                    "type": "string",
                    "description": "Optional system prompt",
                },
            },
            "required": ["prompt"],
        },
    }


def _review_tool_definitions():
    common_properties = {
        "prompt": {
            "type": "string",
            "description": "The substantive ARIS review prompt",
        },
        "executor_model": {
            "type": "string",
            "description": (
                "Actual executor model id; required to enforce cross-family "
                "review"
            ),
        },
        "model": {
            "type": "string",
            "description": f"Reviewer model (default: {DEFAULT_MODEL})",
        },
        "system": {
            "type": "string",
            "description": "Optional reviewer system prompt",
        },
    }
    return [
        {
            "name": "review",
            "description": (
                "Start an HTTP reviewer thread. Returns the actual reviewer "
                "model and fails closed unless it is from a different family "
                "than executor_model."
            ),
            "inputSchema": {
                "type": "object",
                "properties": dict(common_properties),
                "required": ["prompt", "executor_model"],
            },
        },
        {
            "name": "review_reply",
            "description": (
                "Continue an HTTP reviewer thread with full prior message "
                "history."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **common_properties,
                    "threadId": {
                        "type": "string",
                        "description": "threadId returned by review",
                    },
                },
                "required": ["threadId", "prompt"],
            },
        },
    ]


def handle_request(request):
    """Handle a JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    debug_log(f"Handling method: {method}, id: {request_id}")

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
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": "2.2.0",
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        tools = [_chat_tool_definition()]
        if REVIEW_FALLBACK_ENABLED:
            tools.extend(_review_tool_definitions())
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools},
        }

    if method == "tools/call":
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
                        "content": [
                            {"type": "text", "text": f"Error: {error}"}
                        ],
                        "isError": True,
                    },
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": content}]
                },
            }

        if tool_name == "review":
            if not REVIEW_FALLBACK_ENABLED:
                return _tool_error(
                    request_id,
                    "HTTP reviewer fallback is disabled. Set "
                    "LLM_REVIEW_FALLBACK_ENABLED=true and restart the MCP "
                    "server.",
                )
            return _handle_review(arguments, request_id)

        if tool_name == "review_reply":
            if not REVIEW_FALLBACK_ENABLED:
                return _tool_error(
                    request_id,
                    "HTTP reviewer fallback is disabled. Set "
                    "LLM_REVIEW_FALLBACK_ENABLED=true and restart the MCP "
                    "server.",
                )
            return _handle_review_reply(arguments, request_id)

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}",
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32601,
            "message": f"Unknown method: {method}",
        },
    }


def read_message():
    """Read a single JSON-RPC message from stdin."""
    global _use_ndjson

    line = sys.stdin.readline()
    if not line:
        return None

    line = line.decode("utf-8").rstrip("\r\n")

    if line.lower().startswith("content-length:"):
        try:
            content_length = int(line.split(":", 1)[1].strip())
        except ValueError:
            return None

        while True:
            hdr = sys.stdin.readline()
            if not hdr:
                return None
            hdr = hdr.decode("utf-8").rstrip("\r\n")
            if hdr == "":
                break

        body = sys.stdin.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    if line.startswith("{") or line.startswith("["):
        _use_ndjson = True
        try:
            return json.loads(line)
        except Exception:
            return None

    return None


def main():
    """Main loop - read JSON-RPC messages from stdin."""
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
