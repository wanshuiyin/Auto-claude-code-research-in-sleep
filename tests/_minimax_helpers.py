"""
Helper module that extracts testable functions from minimax-chat/server.py
without triggering the module-level sys.stdout/stdin manipulation.
"""

import os
import httpx
import tempfile

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
DEFAULT_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")

DEBUG_LOG = os.path.join(tempfile.gettempdir(), "minimax-mcp-debug.log")


def debug_log(msg):
    pass


def log_error(msg):
    pass


def clamp_temperature(temp):
    """Clamp temperature to MiniMax's allowed range (0.0, 1.0]."""
    if temp is None:
        return None
    try:
        temp = float(temp)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid temperature: {temp!r} ({e})")
    if temp <= 0.0:
        return 0.01
    if temp > 1.0:
        return 1.0
    return temp


def call_minimax(messages, model=None, temperature=0.7):
    """Call MiniMax Chat Completions API"""
    if not MINIMAX_API_KEY:
        return None, "MINIMAX_API_KEY environment variable not set"

    url = f"{MINIMAX_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINIMAX_API_KEY}"
    }
    clamped_temp = clamp_temperature(temperature)
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": clamped_temp
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                error_msg = f"API error {response.status_code}: {response.text[:500]}"
                return None, error_msg
            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                return None, f"Unexpected API response structure: {e}"
            return content, None
    except Exception as e:
        return None, str(e)


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
                    "name": "minimax-chat",
                    "version": "2.0.0"
                }
            }
        }

    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {}
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [{
                    "name": "minimax_chat",
                    "description": "Send a message to MiniMax model and get a response. Use this for research reviews, code analysis, and general AI tasks. Supports MiniMax-M2.7 (default, 204K context) and MiniMax-M2.7-highspeed.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The prompt to send to MiniMax"
                            },
                            "model": {
                                "type": "string",
                                "description": "Model to use: MiniMax-M2.7 (default, 204K context) or MiniMax-M2.7-highspeed (faster, 204K context)",
                                "default": "MiniMax-M2.7",
                                "enum": ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"]
                            },
                            "system": {
                                "type": "string",
                                "description": "Optional system prompt"
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Sampling temperature (0.01-1.0). Default: 0.7",
                                "default": 0.7
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

        if tool_name == "minimax_chat":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model", DEFAULT_MODEL)
            system = arguments.get("system", "")
            temperature = arguments.get("temperature", 0.7)

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            content, error = call_minimax(messages, model, temperature)

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
