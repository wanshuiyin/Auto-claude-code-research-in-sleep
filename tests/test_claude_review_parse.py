"""Unit tests for parse_claude_json in the claude-review MCP bridge.

Covers the JSON-shape change between claude CLI 1.x (NDJSON of dicts) and
2.x (single JSON array of events under --output-format json), plus defensive
cases for pretty-printed arrays and arrays missing the terminal result event.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "mcp-servers" / "claude-review" / "server.py"
SPEC = importlib.util.spec_from_file_location("claude_review_server", SERVER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _result_event(text: str = "OK", session_id: str = "sess-123") -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "session_id": session_id,
        "duration_ms": 1234,
        "stop_reason": "end_turn",
        "model": "claude-opus-4-7",
    }


def _system_init_event() -> dict:
    return {"type": "system", "subtype": "init", "session_id": "sess-123"}


def _assistant_event() -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}}


def _rate_limit_event() -> dict:
    return {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}


class ParseClaudeJsonTests(unittest.TestCase):
    """Cases enumerated in PR #220 review by @wanshuiyin."""

    def test_cli_2x_single_line_array(self) -> None:
        """CLI 2.x default: compact single-line JSON array with terminal result event."""
        events = [_system_init_event(), _assistant_event(), _rate_limit_event(), _result_event("OK")]
        stdout = json.dumps(events)
        self.assertEqual(stdout.count("\n"), 0)  # confirm single-line
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "result")
        self.assertEqual(payload["result"], "OK")
        self.assertEqual(payload["session_id"], "sess-123")

    def test_pretty_printed_multiline_array(self) -> None:
        """Defensive: multi-line pretty-printed JSON array (potential future CLI shape)."""
        events = [_system_init_event(), _assistant_event(), _result_event("hello world", "sess-456")]
        stdout = json.dumps(events, indent=2)
        self.assertGreater(stdout.count("\n"), 1)  # confirm multi-line
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["result"], "hello world")
        self.assertEqual(payload["session_id"], "sess-456")

    def test_legacy_ndjson_dicts(self) -> None:
        """CLI 1.x backward compat: NDJSON stream of dicts, last dict wins."""
        lines = [
            json.dumps(_system_init_event()),
            json.dumps(_assistant_event()),
            json.dumps(_result_event("legacy ok", "sess-789")),
        ]
        stdout = "\n".join(lines) + "\n"
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["result"], "legacy ok")
        self.assertEqual(payload["session_id"], "sess-789")

    def test_empty_stdout(self) -> None:
        for raw in ("", "   ", "\n\n", "\t\n  "):
            with self.subTest(raw=repr(raw)):
                payload, err = MODULE.parse_claude_json(raw)
                self.assertIsNone(payload)
                self.assertEqual(err, "Claude CLI returned empty output")

    def test_array_without_result_event_returns_error(self) -> None:
        """Array of events with no type=='result' entry must NOT silently return another dict."""
        events = [_system_init_event(), _assistant_event(), _rate_limit_event()]
        stdout = json.dumps(events)
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(payload)
        self.assertEqual(err, "Claude CLI returned a JSON array without a 'result' event")

    def test_array_only_system_init_returns_error(self) -> None:
        """Array containing only the system/init event must error, not silently return init dict."""
        stdout = json.dumps([_system_init_event()])
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(payload)
        self.assertEqual(err, "Claude CLI returned a JSON array without a 'result' event")

    def test_garbage_stdout(self) -> None:
        """Non-JSON stdout falls through to the legacy 'did not return JSON output' error."""
        payload, err = MODULE.parse_claude_json("hello world\nthis is not json\n")
        self.assertIsNone(payload)
        self.assertEqual(err, "Claude CLI did not return JSON output")


if __name__ == "__main__":
    unittest.main()
