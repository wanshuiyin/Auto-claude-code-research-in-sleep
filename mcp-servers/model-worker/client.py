#!/usr/bin/env python3
"""Call model-worker over MCP stdio, including before a host reloads its tools."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


def call(
    tool: str,
    arguments: dict,
    *,
    config: Path | None = None,
    local: bool = False,
    timeout: float = 3660,
) -> dict:
    env = dict(os.environ)
    cwd = None
    if local:
        command = [sys.executable, str(Path(__file__).with_name("server.py"))]
    else:
        try:
            import tomllib
        except ImportError:
            raise RuntimeError(
                "Reading Codex config requires Python 3.11+; use --local with explicit environment on older Python"
            ) from None
        settings = tomllib.loads(
            (config or Path.home() / ".codex/config.toml").read_text()
        )
        server = settings["mcp_servers"]["model-worker"]
        if server.get("enabled") is False:
            raise RuntimeError("model-worker is disabled in the Codex config")
        command = [server["command"], *server.get("args", [])]
        env.update(server.get("env", {}))
        cwd = server.get("cwd")
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
        cwd=cwd,
    )
    messages: queue.Queue = queue.Queue()
    errors: list[str] = []

    def reader() -> None:
        try:
            for line in proc.stdout:
                messages.put(json.loads(line))
        except (ValueError, OSError) as exc:
            messages.put(exc)
        finally:
            messages.put(None)

    def drain_errors() -> None:
        for line in proc.stderr:
            errors.append(line)
            if len(errors) > 20:
                del errors[0]

    threads = [
        threading.Thread(target=reader, daemon=True),
        threading.Thread(target=drain_errors, daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout

    def send(value: dict) -> None:
        proc.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def receive(request_id: int) -> dict:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("model-worker client timed out; no automatic retry")
            try:
                item = messages.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(
                    "model-worker client timed out; no automatic retry"
                ) from None
            if isinstance(item, Exception):
                raise item
            if item is None:
                raise RuntimeError(
                    "model-worker exited before replying: " + "".join(errors)[-1000:]
                )
            if item.get("id") == request_id:
                if "error" in item:
                    raise RuntimeError(json.dumps(item["error"], ensure_ascii=False))
                return item["result"]

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "aris-model-worker-client",
                        "version": "1.0",
                    },
                },
            }
        )
        receive(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        method = "tools/list" if tool == "tools/list" else "tools/call"
        params = (
            {} if method == "tools/list" else {"name": tool, "arguments": arguments}
        )
        send({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
        return receive(2)
    finally:
        # EOF lets the server cancel its own CLI process group on interruption.
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for thread in threads:
            thread.join(timeout=1)
        proc.stdout.close()
        proc.stderr.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=["tools/list", "worker", "worker_reply"])
    parser.add_argument("--input", type=Path, help="JSON arguments; defaults to stdin")
    route = parser.add_mutually_exclusive_group()
    route.add_argument(
        "--config", type=Path, help="Codex config containing model-worker"
    )
    route.add_argument(
        "--local",
        action="store_true",
        help="Use adjacent server.py and current environment",
    )
    parser.add_argument("--timeout", type=float, default=3660)
    args = parser.parse_args()
    try:
        arguments = (
            {}
            if args.tool == "tools/list"
            else json.loads(args.input.read_text() if args.input else sys.stdin.read())
        )
        if not isinstance(arguments, dict):
            parser.error("tool arguments must be a JSON object")
        if args.timeout <= 0:
            parser.error("timeout must be positive")
        result = call(
            args.tool,
            arguments,
            config=args.config,
            local=args.local,
            timeout=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("isError") else 0
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
