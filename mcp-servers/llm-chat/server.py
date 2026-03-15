#!/usr/bin/env python3
"""Generic LLM Chat MCP Server - Supports any OpenAI-compatible API

Environment Variables:
    LLM_API_KEY      - API key (required)
    LLM_BASE_URL     - API base URL (default: https://api.openai.com/v1)
    LLM_MODEL        - Model name (default: gpt-4o)
    LLM_SERVER_NAME  - Server name for MCP (default: llm-chat)

Supported Providers (examples):
    OpenAI:      LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o
    DeepSeek:    LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-chat
    Kimi:        LLM_BASE_URL=https://api.moonshot.cn/v1 LLM_MODEL=moonshot-v1-32k
    MiniMax:     LLM_BASE_URL=https://api.minimax.chat/v1 LLM_MODEL=MiniMax-M2.5
"""

import json
import os
import sys
import httpx

# Force unbuffered stdout/stdin
sys.stdout = os.fdopen(sys.stdout.fileno(), 'wb', buffering=0)
sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', buffering=0)

# Configuration from environment
API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
SERVER_NAME = os.environ.get("LLM_SERVER_NAME", "llm-chat")

# Debug logging
DEBUG_LOG = f"/tmp/{SERVER_NAME}-mcp-debug.log"

def debug_log(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            import datetime
            f.write(f"{datetime.datetime.now()}: {msg}\n")
            f.flush()
    except:
        pass

def log_error(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            import datetime
            f.write(f"{datetime.datetime.now()}: ERROR: {msg}\n")
    except:
        pass

debug_log(f"=== {SERVER_NAME} MCP Server Starting (v2.0) ===")
debug_log(f"BASE_URL: {BASE_URL}")
debug_log(f"MODEL: {DEFAULT_MODEL}")
debug_log(f"API_KEY set: {bool(API_KEY)}")

_use_ndjson = False

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

def call_llm(messages, model=None):
    """Call LLM Chat Completions API"""
    if not API_KEY:
        return None, "LLM_API_KEY environment variable not set"

    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": 4096
    }

    debug_log(f"Calling LLM API: {url}")

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                error_msg = f"API error {response.status_code}: {response.text[:500]}"
                debug_log(f"API error: {error_msg}")
                return None, error_msg
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            debug_log(f"API success, response length: {len(content)}")
            return content, None
    except Exception as e:
        debug_log(f"API exception: {str(e)}")
        return None, str(e)

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
        except:
            return None

    elif line.startswith("{") or line.startswith("["):
        _use_ndjson = True
        try:
            return json.loads(line)
        except:
            return None

    return None

def main():
    """Main loop - read JSON-RPC messages from stdin"""
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
