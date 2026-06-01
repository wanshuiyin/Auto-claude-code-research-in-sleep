#!/usr/bin/env python3
"""Integration tests for MiniMax Chat MCP Server.

These tests verify end-to-end behavior including:
- MCP server initialization flow
- Full tool call lifecycle
- API URL correctness
- Temperature clamping in real payloads

Set MINIMAX_API_KEY environment variable to run live API tests.
Tests marked with @unittest.skipUnless will be skipped without the API key.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")


class TestMCPInitializationFlow(unittest.TestCase):
    """Test the full MCP initialization handshake."""

    def test_full_init_handshake(self):
        """Simulate the complete MCP init → notification → tools/list flow."""
        from _minimax_helpers import handle_request

        # Step 1: Initialize
        init_resp = handle_request({
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        })
        self.assertEqual(init_resp["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "minimax-chat")

        # Step 2: Notification (no response expected)
        notif_resp = handle_request({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        self.assertIsNone(notif_resp)

        # Step 3: List tools
        tools_resp = handle_request({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list", "params": {}
        })
        tools = tools_resp["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "minimax_chat")

        # Verify M3 + M2.7 models are listed
        model_enum = tools[0]["inputSchema"]["properties"]["model"]["enum"]
        self.assertIn("MiniMax-M3", model_enum)
        self.assertIn("MiniMax-M2.7", model_enum)
        self.assertIn("MiniMax-M2.7-highspeed", model_enum)
        # Older M2.5 variants have been removed
        self.assertNotIn("MiniMax-M2.5", model_enum)

    def test_ping_during_session(self):
        """Ping should work at any point during the session."""
        from _minimax_helpers import handle_request

        ping_resp = handle_request({
            "jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}
        })
        self.assertEqual(ping_resp["result"], {})


class TestEndToEndToolCall(unittest.TestCase):
    """Test full tool call lifecycle with mocked API."""

    @patch('_minimax_helpers.MINIMAX_API_KEY', 'test-integration-key')
    @patch('httpx.Client')
    def test_chat_with_system_and_temperature(self, mock_client_cls):
        """Full tool call with system prompt, custom model, and temperature."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Integration test response"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from _minimax_helpers import handle_request

        response = handle_request({
            "jsonrpc": "2.0", "id": 10,
            "method": "tools/call",
            "params": {
                "name": "minimax_chat",
                "arguments": {
                    "prompt": "Review this ML paper",
                    "system": "You are a senior ML reviewer for NeurIPS",
                    "model": "MiniMax-M2.7-highspeed",
                    "temperature": 0.3
                }
            }
        })

        # Verify response
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(
            response["result"]["content"][0]["text"],
            "Integration test response"
        )

        # Verify API call details
        call_args = mock_client.post.call_args
        url = call_args[0][0]
        self.assertIn("api.minimax.io", url)
        self.assertEqual(url, "https://api.minimax.io/v1/chat/completions")

        payload = call_args[1]["json"]
        self.assertEqual(payload["model"], "MiniMax-M2.7-highspeed")
        self.assertAlmostEqual(payload["temperature"], 0.3)
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")

    @patch('_minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_temperature_zero_clamped_in_full_flow(self, mock_client_cls):
        """Temperature=0 should be clamped to 0.01 in the full tool call flow."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from _minimax_helpers import handle_request

        handle_request({
            "jsonrpc": "2.0", "id": 11,
            "method": "tools/call",
            "params": {
                "name": "minimax_chat",
                "arguments": {"prompt": "test", "temperature": 0}
            }
        })

        payload = mock_client.post.call_args[1]["json"]
        self.assertAlmostEqual(payload["temperature"], 0.01)


@unittest.skipUnless(MINIMAX_API_KEY, "MINIMAX_API_KEY not set — skipping live API tests")
class TestLiveAPI(unittest.TestCase):
    """Live integration tests against MiniMax API.

    Only run when MINIMAX_API_KEY is set in the environment.
    """

    def test_live_m3_chat(self):
        """Live test: send a simple prompt to MiniMax-M3 (default)."""
        from _minimax_helpers import call_minimax
        # Temporarily set the API key
        import _minimax_helpers
        original_key = _minimax_helpers.MINIMAX_API_KEY
        _minimax_helpers.MINIMAX_API_KEY = MINIMAX_API_KEY
        try:
            content, error = call_minimax(
                [{"role": "user", "content": "Say 'hello' and nothing else."}],
                model="MiniMax-M3",
                temperature=0.1
            )
            self.assertIsNone(error, f"API returned error: {error}")
            self.assertIsNotNone(content)
            self.assertIn("hello", content.lower())
        finally:
            _minimax_helpers.MINIMAX_API_KEY = original_key

    def test_live_m27_chat(self):
        """Live test: send a simple prompt to MiniMax-M2.7."""
        from _minimax_helpers import call_minimax
        # Temporarily set the API key
        import _minimax_helpers
        original_key = _minimax_helpers.MINIMAX_API_KEY
        _minimax_helpers.MINIMAX_API_KEY = MINIMAX_API_KEY
        try:
            content, error = call_minimax(
                [{"role": "user", "content": "Say 'hello' and nothing else."}],
                model="MiniMax-M2.7",
                temperature=0.1
            )
            self.assertIsNone(error, f"API returned error: {error}")
            self.assertIsNotNone(content)
            self.assertIn("hello", content.lower())
        finally:
            _minimax_helpers.MINIMAX_API_KEY = original_key

    def test_live_m27_highspeed_chat(self):
        """Live test: send a simple prompt to MiniMax-M2.7-highspeed."""
        from _minimax_helpers import call_minimax
        import _minimax_helpers
        original_key = _minimax_helpers.MINIMAX_API_KEY
        _minimax_helpers.MINIMAX_API_KEY = MINIMAX_API_KEY
        try:
            content, error = call_minimax(
                [{"role": "user", "content": "What is 2+2? Reply with just the number."}],
                model="MiniMax-M2.7-highspeed",
                temperature=0.1
            )
            self.assertIsNone(error, f"API returned error: {error}")
            self.assertIsNotNone(content)
            self.assertIn("4", content)
        finally:
            _minimax_helpers.MINIMAX_API_KEY = original_key

    def test_live_api_url_is_correct(self):
        """Live test: verify api.minimax.io endpoint works."""
        import httpx
        # Just verify the endpoint is reachable (will fail auth but that's OK)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.minimax.io/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={"model": "MiniMax-M3", "messages": []}
                )
                # Should get 401 (no auth) or 400 (bad request), NOT connection error
                self.assertIn(resp.status_code, [400, 401, 403, 422])
        except httpx.ConnectError:
            self.fail("Could not connect to api.minimax.io — endpoint may be wrong")


if __name__ == "__main__":
    unittest.main()
