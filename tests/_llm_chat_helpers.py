"""
Helper module that extracts testable functions from llm-chat/server.py
without triggering the module-level sys.stdout/stdin manipulation.
"""

import os
import httpx
import subprocess
import tempfile

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL_OVERRIDE = os.environ.get("LLM_MODEL", "")
DEFAULT_MODEL = MODEL_OVERRIDE or "gpt-4o"
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gpt-4o")
SERVER_NAME = os.environ.get("LLM_SERVER_NAME", "llm-chat")
BACKEND = os.environ.get("LLM_BACKEND", "api").strip().lower()
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_WORKDIR = os.environ.get("CODEX_WORKDIR", os.getcwd())
CODEX_TIMEOUT_SECS = int(os.environ.get("CODEX_TIMEOUT_SECS", "600"))
CODEX_DISABLE_PLUGINS = os.environ.get("CODEX_DISABLE_PLUGINS", "1").strip().lower() not in ("0", "false", "no")

DEBUG_LOG = os.path.join(tempfile.gettempdir(), f"{SERVER_NAME}-mcp-debug.log")


def debug_log(msg):
    pass


def log_error(msg):
    pass


def resolve_backend():
    if BACKEND in ("auto", ""):
        return "api" if LLM_API_KEY else "codex-cli"
    if BACKEND in ("codex", "codex-cli", "codex_cli"):
        return "codex-cli"
    return BACKEND


def messages_to_prompt(messages):
    chunks = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        content = str(message.get("content", ""))
        chunks.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(chunks).strip()


def call_codex_cli(messages, model=None):
    use_model = model or MODEL_OVERRIDE
    prompt = messages_to_prompt(messages)
    if not prompt:
        return None, "Prompt is empty"

    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as output_file:
        output_path = output_file.name

    cmd = [
        CODEX_BIN,
        "exec",
        "-C",
        CODEX_WORKDIR,
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
        "--sandbox",
        "read-only",
        "--output-last-message",
        output_path,
        "-",
    ]
    if use_model:
        cmd[2:2] = ["-m", use_model]
    if CODEX_DISABLE_PLUGINS:
        cmd[2:2] = ["--disable", "plugins"]

    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=CODEX_TIMEOUT_SECS,
            cwd=CODEX_WORKDIR if os.path.isdir(CODEX_WORKDIR) else None,
        )

        content = ""
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except FileNotFoundError:
            content = ""

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            if not stderr:
                stderr = f"codex exec exited with status {completed.returncode}"
            return None, stderr[:1000]

        if not content:
            content = (completed.stdout or "").strip()

        if not content:
            return None, "codex exec completed but returned no final message"

        return content, None
    except FileNotFoundError:
        return None, f"Codex CLI not found: {CODEX_BIN}"
    except subprocess.TimeoutExpired:
        return None, f"codex exec timed out after {CODEX_TIMEOUT_SECS}s"
    except Exception as e:
        return None, str(e)
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass


def call_llm(messages, model=None):
    """Call LLM Chat Completions API with 504 retry and fallback"""
    backend = resolve_backend()
    if backend == "codex-cli":
        return call_codex_cli(messages, model)
    if backend != "api":
        return None, f"Unsupported LLM_BACKEND: {BACKEND}"

    if not LLM_API_KEY:
        return None, "LLM_API_KEY environment variable not set. Set LLM_BACKEND=codex-cli to use an OAuth-authenticated local Codex CLI instead."

    use_model = model or DEFAULT_MODEL
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }

    # Try: original model → retry same model → fallback model
    for attempt in range(3):
        current_model = use_model if attempt < 2 else FALLBACK_MODEL
        payload = {
            "model": current_model,
            "messages": messages,
            "max_tokens": 4096
        }

        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(url, headers=headers, json=payload)

                if response.status_code == 504:
                    if attempt < 2:
                        continue  # retry or fallback

                if response.status_code != 200:
                    error_msg = f"API error {response.status_code}: {response.text[:500]}"
                    return None, error_msg

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if current_model != use_model:
                    fallback_note = f"\n\n[Note: Used fallback model {current_model} after 504 timeout with {use_model}]"
                    content = fallback_note + "\n" + content
                return content, None
        except Exception as e:
            if attempt == 2:
                return None, str(e)

    return None, "All attempts failed with 504 Gateway Timeout"


def handle_request(request):
    """Handle a JSON-RPC request"""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    if request_id is None:
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
                    "version": "2.0.0"
                }
            }
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    elif method == "tools/list":
        backend = resolve_backend()
        model_label = MODEL_OVERRIDE or ("Codex config default" if backend == "codex-cli" else DEFAULT_MODEL)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [{
                    "name": "chat",
                    "description": f"Send a message to {model_label} via {backend} and get a response. Use this for research reviews, code analysis, and general AI tasks.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The prompt to send"
                            },
                            "model": {
                                "type": "string",
                                "description": f"Model to use (default: {model_label})"
                            },
                            "system": {
                                "type": "string",
                                "description": "Optional system prompt"
                            }
                        },
                        "required": ["prompt"]
                    }
                }]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "chat":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model")
            system = arguments.get("system", "")

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

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
