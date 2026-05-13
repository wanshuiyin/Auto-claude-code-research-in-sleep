"""Unit tests for parse_claude_json and run_claude_review in the claude-review MCP bridge.

parse_claude_json tests cover the JSON-shape change between claude CLI 1.x
(NDJSON of dicts) and 2.x (single JSON array of events under --output-format json),
plus defensive cases for pretty-printed arrays and arrays missing the terminal
result event.

run_claude_review tests cover the end-to-end mapping from a parsed result event
into the (threadId, response, model, duration_ms, stop_reason) dict the MCP
bridge surfaces to its caller.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


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

    def test_noisy_stdout_with_compact_array_line_recovers(self) -> None:
        """Wrapper banner + compact JSON-array line on the next line still recovers result.

        Defends against Codex adversarial review finding: CLI wrappers (nvm,
        asdf, mise, future claude --debug) may print non-JSON banners to
        stdout before/after the JSON. Whole-stdout json.loads fails; the
        per-line fallback must scan list payloads too, not only dicts.
        """
        events = [_system_init_event(), _assistant_event(), _result_event("recovered", "sess-noisy")]
        stdout = (
            "warning: nvm couldn't find xyz\n"
            + json.dumps(events) + "\n"
        )
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["result"], "recovered")
        self.assertEqual(payload["session_id"], "sess-noisy")

    def test_noisy_stdout_with_array_line_no_result_falls_through(self) -> None:
        """Noisy stdout + JSON-array line that has no result event continues scanning earlier lines."""
        events_no_result = [_system_init_event(), _assistant_event()]
        stdout = (
            "warning: banner\n"
            + json.dumps(events_no_result) + "\n"
        )
        payload, err = MODULE.parse_claude_json(stdout)
        self.assertIsNone(payload)
        self.assertEqual(err, "Claude CLI did not return JSON output")


def _completed_process(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


class RunClaudeReviewTests(unittest.TestCase):
    """End-to-end mapping from a CLI result event into the MCP bridge dict.

    Mocks subprocess.run + find_claude_bin so tests don't depend on a local
    claude CLI install. Locks the contract that downstream MCP callers
    consume: threadId / response / model / duration_ms / stop_reason.
    """

    def test_cli_2x_array_maps_all_result_fields(self) -> None:
        """Happy path: CLI 2.x JSON-array stdout -> all five downstream fields populated."""
        events = [
            _system_init_event(),
            _assistant_event(),
            _result_event("review body text", "sess-abc"),
        ]
        events[-1]["model"] = "claude-opus-4-7"
        events[-1]["duration_ms"] = 8765
        events[-1]["stop_reason"] = "end_turn"
        stdout = json.dumps(events)

        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"), \
             mock.patch.object(MODULE.subprocess, "run", return_value=_completed_process(stdout)) as run:
            payload, err = MODULE.run_claude_review("hello prompt")

        self.assertIsNone(err)
        self.assertEqual(payload, {
            "threadId": "sess-abc",
            "response": "review body text",
            "model": "claude-opus-4-7",
            "duration_ms": 8765,
            "stop_reason": "end_turn",
        })
        # also verify subprocess actually called with the expected --output-format json shape
        called_cmd = run.call_args.args[0]
        self.assertIn("--output-format", called_cmd)
        self.assertEqual(called_cmd[called_cmd.index("--output-format") + 1], "json")

    def test_legacy_ndjson_stdout_maps_correctly_end_to_end(self) -> None:
        """CLI 1.x NDJSON path -> downstream consumer still gets correct fields."""
        result = _result_event("legacy review", "sess-legacy")
        result["model"] = "claude-sonnet-4-6"
        result["duration_ms"] = 4321
        stdout = "\n".join([
            json.dumps(_system_init_event()),
            json.dumps(_assistant_event()),
            json.dumps(result),
        ]) + "\n"

        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"), \
             mock.patch.object(MODULE.subprocess, "run", return_value=_completed_process(stdout)):
            payload, err = MODULE.run_claude_review("hello")

        self.assertIsNone(err)
        assert payload is not None
        self.assertEqual(payload["threadId"], "sess-legacy")
        self.assertEqual(payload["response"], "legacy review")
        self.assertEqual(payload["model"], "claude-sonnet-4-6")
        self.assertEqual(payload["duration_ms"], 4321)

    def test_array_without_result_event_surfaces_clear_error(self) -> None:
        """Maintainer's fail-fast requirement holds end-to-end (no silent empty review)."""
        stdout = json.dumps([_system_init_event(), _rate_limit_event()])

        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"), \
             mock.patch.object(MODULE.subprocess, "run", return_value=_completed_process(stdout)):
            payload, err = MODULE.run_claude_review("hello")

        self.assertIsNone(payload)
        assert err is not None
        self.assertIn("JSON array without a 'result' event", err)

    def test_claude_binary_missing_returns_clear_error(self) -> None:
        """If no claude CLI is on PATH, surface the FileNotFoundError message, not a crash."""
        with mock.patch.object(MODULE, "find_claude_bin", return_value=None):
            payload, err = MODULE.run_claude_review("hello")
        self.assertIsNone(payload)
        assert err is not None
        self.assertIn("Claude CLI not found", err)

    def test_error_result_with_errors_list_surfaces_specific_message(self) -> None:
        """CLI 2.x error result: payload.get('errors') list -> specific message in returned err.

        Reproduces the budget-exceeded shape observed against claude CLI 2.1.140:
        result event has subtype="error_max_budget_usd", is_error=true, and the
        diagnostic lives in an `errors` list — there is no `result`/`error` field.
        Without explicit handling, run_claude_review degrades to the generic
        "Claude review failed", losing the actionable message.

        Note: subprocess returncode is 0 here — claude CLI exits cleanly even
        for these error result events. We rely on payload.get("is_error") to
        trigger the error branch.
        """
        error_event = {
            "type": "result",
            "subtype": "error_max_budget_usd",
            "is_error": True,
            "errors": ["Reached maximum budget ($0.01)"],
            # deliberately no `result` / `error` / `session_id` — matches real CLI shape
        }
        stdout = json.dumps([error_event])

        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"), \
             mock.patch.object(MODULE.subprocess, "run", return_value=_completed_process(stdout, returncode=0)):
            payload, err = MODULE.run_claude_review("hello")

        self.assertIsNone(payload)
        assert err is not None
        self.assertIn("Reached maximum budget", err)
        self.assertNotEqual(err.strip(), "Claude review failed")

    def test_error_result_multiple_errors_joined(self) -> None:
        """Multiple entries in the errors list are joined with '; '."""
        error_event = {
            "type": "result",
            "is_error": True,
            "errors": ["First problem", "Second problem"],
        }
        stdout = json.dumps([error_event])

        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"), \
             mock.patch.object(MODULE.subprocess, "run", return_value=_completed_process(stdout, returncode=0)):
            payload, err = MODULE.run_claude_review("hello")

        self.assertIsNone(payload)
        assert err is not None
        self.assertIn("First problem", err)
        self.assertIn("Second problem", err)
        self.assertIn(";", err)


if __name__ == "__main__":
    unittest.main()
