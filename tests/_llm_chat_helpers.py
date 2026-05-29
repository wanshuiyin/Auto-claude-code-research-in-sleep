"""
Helper module that extracts testable functions from llm-chat/server.py
without triggering the module-level sys.stdout/stdin manipulation.
"""

import os
import httpx
import tempfile

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gpt-4o")
SERVER_NAME = os.environ.get("LLM_SERVER_NAME", "llm-chat")

DEBUG_LOG = os.path.join(tempfile.gettempdir(), f"{SERVER_NAME}-mcp-debug.log")


def debug_log(msg):
    pass


def log_error(msg):
    pass


def call_llm(messages, model=None):
    """Call LLM Chat Completions API with 504 retry and fallback"""
    if not LLM_API_KEY:
        return None, "LLM_API_KEY environment variable not set"

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
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    return None, f"Unexpected API response structure: {e}"
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
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [{
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
            }
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
