#!/usr/bin/env python3
"""Opt-in web search via Parallel's Unified MCP server (Python stdlib only).

    python3 tools/parallel_search.py search "transformer attention mechanisms" --max 5

Anonymous calls use the server's default Fast search. PARALLEL_API_KEY, when
set, is used explicitly; authentication errors never retry anonymously.
--max and --max-chars cap displayed results locally, not server search effort.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

ENDPOINT = "https://mcp.parallel.ai/mcp"
USER_AGENT = "Auto-claude-code-research-in-sleep/parallel-search"
PROTOCOL = "2025-03-26"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward credentials or turn an MCP POST into a GET.
        return None


def _read_sse_result(response: Any, request_id: int) -> dict[str, Any]:
    line = bytearray()
    data: list[str] = []
    previous_cr = False
    while True:
        chunk = response.read1(4096)
        if not chunk:
            raise RuntimeError("MCP stream ended before the response")
        for byte in chunk:
            if previous_cr and byte == 10:
                previous_cr = False
                continue
            previous_cr = byte == 13
            if byte not in (10, 13):
                line.append(byte)
                continue
            text = line.decode("utf-8")
            line.clear()
            if text.startswith("data:"):
                data.append(text[5:].removeprefix(" "))
            elif not text and data:
                candidate = json.loads("\n".join(data))
                data = []
                if isinstance(candidate, dict) and candidate.get("id") == request_id:
                    return candidate


def _decode_response(response: Any, request_id: int) -> dict[str, Any]:
    """Read JSON or SSE, splitting protocol lines on CR/LF only."""
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
    if content_type == "application/json":
        message = json.load(response)
    elif content_type == "text/event-stream":
        message = _read_sse_result(response, request_id)
    else:
        raise RuntimeError("Unexpected MCP response content type")
    if not isinstance(message, dict) or message.get("id") != request_id:
        raise RuntimeError("Invalid MCP response ID")
    if "error" in message:
        raise RuntimeError(f"MCP request failed (code {message['error'].get('code', 'unknown')})")
    if not isinstance(message.get("result"), dict):
        raise RuntimeError("Invalid MCP result")
    return message["result"]


class _Client:
    def __init__(self):
        self.headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if "PARALLEL_API_KEY" in os.environ:
            key = os.environ["PARALLEL_API_KEY"].strip()
            if not key or any(ord(c) < 32 or ord(c) == 127 for c in key):
                raise ValueError("PARALLEL_API_KEY is set but empty or invalid")
            self.headers["Authorization"] = f"Bearer {key}"
        self.opener = urllib.request.build_opener(_NoRedirect())
        self.request_id = 0

    def request(self, method: str, params: dict | None = None, *, notification=False):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            payload["id"] = self.request_id
        request = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode(), headers=self.headers, method="POST",
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.headers["Mcp-Session-Id"] = session
                if notification:
                    return None
                return _decode_response(response, self.request_id)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Parallel HTTP {exc.code} during {method}; no provider fallback") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError(f"Parallel connection failed during {method}; no provider fallback") from None

    def close(self):
        if "Mcp-Session-Id" not in self.headers:
            return
        request = urllib.request.Request(ENDPOINT, headers=self.headers, method="DELETE")
        try:
            with self.opener.open(request, timeout=15):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 405):
                print(f"Warning: Parallel session cleanup HTTP {exc.code}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError):
            print("Warning: Parallel session cleanup connection failed", file=sys.stderr)


def search(query: str, max_results: int = 10, max_chars: int = 4000, *, offline=False,
           disabled=False) -> dict[str, Any]:
    """Return source URLs and excerpts without changing any provider settings."""
    if offline or disabled or any(
        os.getenv(name, "").lower().strip() in ("1", "true", "yes", "on")
        for name in ("ARIS_SEARCH_OFFLINE", "ARIS_SEARCH_DISABLED")
    ):
        raise RuntimeError("Web search is disabled/offline; no request sent")
    if not query.strip():
        raise ValueError("Search query must not be empty")
    if not 1 <= max_results <= 100 or not 1 <= max_chars <= 100000:
        raise ValueError("--max must be 1..100 and --max-chars must be 1..100000")
    client = _Client()
    try:
        initialized = client.request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "aris-parallel-search", "version": "1.0"},
        })
        if initialized.get("protocolVersion") != PROTOCOL:
            raise RuntimeError("Unsupported MCP protocol version")
        client.headers["MCP-Protocol-Version"] = PROTOCOL
        client.request("notifications/initialized", notification=True)
        cursor = None
        seen = set()
        while True:
            discovery = client.request("tools/list", {"cursor": cursor} if cursor else {})
            if any(tool.get("name") == "web_search" for tool in discovery.get("tools", [])):
                break
            cursor = discovery.get("nextCursor")
            if not cursor or cursor in seen:
                raise RuntimeError("Parallel MCP does not expose web_search")
            seen.add(cursor)
        result = client.request("tools/call", {
            "name": "web_search",
            "arguments": {"objective": query, "search_queries": [query]},
        })
        if result.get("isError"):
            raise RuntimeError("Parallel web_search failed; no provider fallback")
        payload = result.get("structuredContent")
        if payload is None:
            texts = [item["text"] for item in result.get("content", []) if item.get("type") == "text"]
            payload = json.loads("\n".join(texts))
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise RuntimeError("Invalid Parallel search results")
        data = []
        for item in payload["results"][:max_results]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                raise RuntimeError("Invalid Parallel source URL")
            excerpts = item.get("excerpts", [])
            if not isinstance(excerpts, list) or not all(isinstance(s, str) for s in excerpts):
                raise RuntimeError("Invalid Parallel excerpts")
            remaining = max_chars
            passages = []
            for passage in excerpts:
                if remaining <= 0:
                    break
                passages.append(passage[:remaining])
                remaining -= len(passages[-1])
            data.append({"title": item.get("title") or "No Title", "url": item["url"],
                         "excerpts": passages})
        output = {"mode": "search", "provider": "parallel", "query": query,
                  "returned": len(data), "data": data}
        for name in ("warnings", "search_id", "session_id"):
            if name in payload:
                output[name] = payload[name]
        return output
    finally:
        client.close()


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("search", help="Search the web via Parallel Unified MCP")
    cmd.add_argument("query")
    cmd.add_argument("--max", type=int, default=10, metavar="N", help="Local result cap, 1..100 (default: 10)")
    cmd.add_argument("--max-chars", type=int, default=4000, metavar="N", help="Local excerpt character cap per result, 1..100000 (default: 4000)")
    cmd.add_argument("--offline", action="store_true", help="Block network search")
    cmd.add_argument("--disabled", action="store_true", help="Block network search")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = search(args.query, args.max, args.max_chars, offline=args.offline, disabled=args.disabled)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Protocol bodies can include untrusted text. Do not print them or credentials.
        message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) and not isinstance(exc, json.JSONDecodeError) else "Invalid Parallel response"
        key = os.getenv("PARALLEL_API_KEY", "").strip()
        if key:
            message = message.replace(key, "[redacted]")
        print(f"Error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
