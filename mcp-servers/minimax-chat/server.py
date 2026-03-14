#!/usr/bin/env python3
"""MiniMax Chat MCP Server - A robust MCP server that calls MiniMax Chat Completions API"""

import json
import os
import sys
import httpx

# Force unbuffered stdout/stdin
sys.stdout = os.fdopen(sys.stdout.fileno(), 'wb', buffering=0)
sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', buffering=0)

# Debug logging
DEBUG_LOG = "/tmp/minimax-mcp-debug.log"

def debug_log(msg):
    """Write debug message to log file"""
    try:
        with open(DEBUG_LOG, "a") as f:
            import datetime
            f.write(f"{datetime.datetime.now()}: {msg}\n")
            f.flush()
    except:
        pass

debug_log("=== MCP Server Starting (v2.0) ===")
debug_log(f"MINIMAX_API_KEY set: {bool(os.environ.get('MINIMAX_API_KEY'))}")
debug_log(f"MINIMAX_BASE_URL: {os.environ.get('MINIMAX_BASE_URL', 'not set')}")
debug_log(f"MINIMAX_MODEL: {os.environ.get('MINIMAX_MODEL', 'not set')}")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
DEFAULT_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")

def log_error(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            import datetime
            f.write(f"{datetime.datetime.now()}: ERROR: {msg}\n")
    except:
        pass

# Global flag for output format
_use_ndjson = False

def send_response(response):
    """Send a JSON-RPC response using binary stdout"""
    global _use_ndjson
    json_str = json.dumps(response, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')

    if _use_ndjson:
        # NDJSON format: just the JSON followed by newline
        output = json_bytes + b'\n'
    else:
        # Standard MCP format: Content-Length header + body
        header = f"Content-Length: {len(json_bytes)}\r\n\r\n".encode('utf-8')
        output = header + json_bytes

    sys.stdout.write(output)
    sys.stdout.flush()
    debug_log(f"Sent response ({'NDJSON' if _use_ndjson else 'MCP'}): {json_str[:200]}...")

def send_notification(method, params=None):
    """Send a JSON-RPC notification"""
    notification = {
        "jsonrpc": "2.0",
        "method": method
    }
    if params:
        notification["params"] = params
    send_response(notification)

def call_minimax(messages, model=None):
    """Call MiniMax Chat Completions API"""
    if not MINIMAX_API_KEY:
        return None, "MINIMAX_API_KEY environment variable not set"

    url = f"{MINIMAX_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINIMAX_API_KEY}"
    }
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": 4096
    }

    debug_log(f"Calling MiniMax API: {url}")

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
        debug_log(f"Notification received: {method}")
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
                    "description": "Send a message to MiniMax M2.5 model and get a response. Use this for research reviews, code analysis, and general AI tasks.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The prompt to send to MiniMax"
                            },
                            "model": {
                                "type": "string",
                                "description": "Model to use (default: MiniMax-M2.5)",
                                "default": "MiniMax-M2.5"
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

        if tool_name == "minimax_chat":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model", DEFAULT_MODEL)
            system = arguments.get("system", "")

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            debug_log(f"Tool call: minimax_chat, prompt length: {len(prompt)}")
            content, error = call_minimax(messages, model)

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
        debug_log(f"Unknown method: {method}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }

def read_message():
    """Read a single JSON-RPC message from stdin. Returns None on EOF.

    Supports two formats:
    1. Standard MCP: Content-Length: N\\r\\n\\r\\n{json}
    2. NDJSON/Line-delimited: {json}\\n
    """
    content_length = None
    first_line = None

    # Read first line to determine format
    line = sys.stdin.readline()
    if not line:  # EOF
        return None

    line = line.decode('utf-8').rstrip('\r\n')
    debug_log(f"First line: '{line[:100]}...'")

    # Check if it's a Content-Length header or direct JSON
    if line.lower().startswith("content-length:"):
        # Standard MCP format
        try:
            content_length = int(line.split(":", 1)[1].strip())
            debug_log(f"Content-Length: {content_length}")
        except ValueError:
            log_error(f"Invalid Content-Length: {line}")
            return None

        # Read remaining headers until blank line
        while True:
            hdr = sys.stdin.readline()
            if not hdr:
                return None
            hdr = hdr.decode('utf-8').rstrip('\r\n')
            if hdr == "":
                break
            debug_log(f"Header: '{hdr}'")

    elif line.startswith("{") or line.startswith("["):
        # NDJSON format - the line IS the JSON
        global _use_ndjson
        _use_ndjson = True
        debug_log("Detected NDJSON format (line-delimited JSON)")
        try:
            request = json.loads(line)
            debug_log(f"Parsed NDJSON request: {json.dumps(request)[:200]}")
            return request
        except json.JSONDecodeError as e:
            log_error(f"JSON decode error in NDJSON: {e}")
            return None

    else:
        log_error(f"Unexpected line format: {line[:100]}")
        return None

    if content_length is None:
        log_error("Missing Content-Length header")
        return None

    # Read the body (for standard MCP format)
    body = sys.stdin.read(content_length)
    if len(body) < content_length:
        log_error(f"Incomplete body: expected {content_length}, got {len(body)}")
        return None

    try:
        request = json.loads(body.decode('utf-8'))
        debug_log(f"Parsed request: {json.dumps(request)[:200]}")
        return request
    except json.JSONDecodeError as e:
        log_error(f"JSON decode error: {e}")
        return None

def main():
    """Main loop - read JSON-RPC messages from stdin"""
    debug_log("Entering main loop")

    while True:
        try:
            request = read_message()
            if request is None:
                debug_log("Received EOF, exiting gracefully")
                break

            debug_log(f"Processing: {request.get('method', 'unknown')}")

            response = handle_request(request)
            if response:
                send_response(response)

        except Exception as e:
            log_error(f"Exception in main loop: {e}")
            debug_log(f"Exception: {e}")
            # Try to send error response
            try:
                send_response({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {e}"}
                })
            except:
                pass

    debug_log("=== MCP Server Exiting ===")

if __name__ == "__main__":
    main()
