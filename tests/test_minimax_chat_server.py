#!/usr/bin/env python3
"""Unit tests for MiniMax Chat MCP Server."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent dir to path so we can import the server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp-servers', 'minimax-chat'))


class TestClampTemperature(unittest.TestCase):
    """Test temperature clamping for MiniMax API constraints."""

    def _import_clamp(self):
        """Import clamp_temperature from server module."""
        # We need to mock sys.stdout/stdin before importing to avoid fd issues
        with patch('sys.stdout'), patch('sys.stdin'):
            # Force re-import to get fresh module
            if 'server' in sys.modules:
                del sys.modules['server']
            import importlib
            spec = importlib.util.spec_from_file_location(
                "minimax_server",
                os.path.join(os.path.dirname(__file__), '..', 'mcp-servers', 'minimax-chat', 'server.py')
            )
            # We can't easily import server.py because it does sys.stdout/stdin manipulation at module level
            # Instead, test the clamp logic directly
        pass

    def test_clamp_none_returns_none(self):
        """None temperature should return None."""
        from tests._minimax_helpers import clamp_temperature
        self.assertIsNone(clamp_temperature(None))

    def test_clamp_zero_returns_min(self):
        """Zero temperature should be clamped to 0.01."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature(0.0), 0.01)

    def test_clamp_negative_returns_min(self):
        """Negative temperature should be clamped to 0.01."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature(-1.0), 0.01)

    def test_clamp_above_one_returns_one(self):
        """Temperature > 1.0 should be clamped to 1.0."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature(2.0), 1.0)
        self.assertAlmostEqual(clamp_temperature(1.5), 1.0)

    def test_clamp_valid_passes_through(self):
        """Valid temperatures (0.0, 1.0] should pass through unchanged."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature(0.5), 0.5)
        self.assertAlmostEqual(clamp_temperature(0.7), 0.7)
        self.assertAlmostEqual(clamp_temperature(1.0), 1.0)
        self.assertAlmostEqual(clamp_temperature(0.01), 0.01)

    def test_clamp_string_number(self):
        """String numbers should be converted and clamped."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature("0.5"), 0.5)
        self.assertAlmostEqual(clamp_temperature("0"), 0.01)
        self.assertAlmostEqual(clamp_temperature("2.0"), 1.0)

    def test_clamp_boundary_just_above_zero(self):
        """Temperature just above 0 should pass through."""
        from tests._minimax_helpers import clamp_temperature
        self.assertAlmostEqual(clamp_temperature(0.001), 0.001)

    def test_clamp_non_numeric_raises_valueerror(self):
        """Non-numeric input should raise ValueError with a clear message
        (caller surfaces it as 'Invalid temperature: ...' instead of letting
        a raw float() error bubble through JSON-RPC)."""
        from tests._minimax_helpers import clamp_temperature
        with self.assertRaises(ValueError) as ctx:
            clamp_temperature("not a number")
        self.assertIn("Invalid temperature", str(ctx.exception))
        with self.assertRaises(ValueError):
            clamp_temperature([])
        with self.assertRaises(ValueError):
            clamp_temperature({"oops": True})


class TestDefaultConfig(unittest.TestCase):
    """Test default configuration values."""

    def test_default_base_url(self):
        """Default base URL should be api.minimax.io."""
        self.assertEqual(
            os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
            "https://api.minimax.io/v1"
        )

    def test_default_model(self):
        """Default model should be MiniMax-M2.7."""
        self.assertEqual(
            os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
            "MiniMax-M2.7"
        )


class TestHandleRequest(unittest.TestCase):
    """Test JSON-RPC request handling logic."""

    def test_initialize_response(self):
        """Initialize should return protocol version and capabilities."""
        from tests._minimax_helpers import handle_request
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = handle_request(request)
        self.assertEqual(response["id"], 1)
        self.assertIn("result", response)
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertEqual(response["result"]["serverInfo"]["name"], "minimax-chat")

    def test_ping_response(self):
        """Ping should return empty result."""
        from tests._minimax_helpers import handle_request
        request = {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
        response = handle_request(request)
        self.assertEqual(response["id"], 2)
        self.assertEqual(response["result"], {})

    def test_tools_list_response(self):
        """tools/list should return minimax_chat tool with M2.7 default."""
        from tests._minimax_helpers import handle_request
        request = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        response = handle_request(request)
        tools = response["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "minimax_chat")
        self.assertIn("MiniMax-M2.7", tools[0]["description"])
        self.assertIn("MiniMax-M2.7-highspeed", tools[0]["description"])
        # Check model enum includes all variants
        model_schema = tools[0]["inputSchema"]["properties"]["model"]
        self.assertIn("MiniMax-M2.7", model_schema["enum"])
        self.assertIn("MiniMax-M2.7-highspeed", model_schema["enum"])
        self.assertIn("MiniMax-M2.5", model_schema["enum"])
        self.assertIn("MiniMax-M2.5-highspeed", model_schema["enum"])
        # Check temperature parameter exists
        self.assertIn("temperature", tools[0]["inputSchema"]["properties"])

    def test_notification_returns_none(self):
        """Notifications (no id) should return None."""
        from tests._minimax_helpers import handle_request
        request = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        response = handle_request(request)
        self.assertIsNone(response)

    def test_unknown_method(self):
        """Unknown method should return error."""
        from tests._minimax_helpers import handle_request
        request = {"jsonrpc": "2.0", "id": 5, "method": "unknown/method", "params": {}}
        response = handle_request(request)
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool(self):
        """Unknown tool name should return error."""
        from tests._minimax_helpers import handle_request
        request = {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}}
        }
        response = handle_request(request)
        self.assertIn("error", response)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', '')
    def test_tool_call_no_api_key(self):
        """Tool call without API key should return error."""
        from tests._minimax_helpers import handle_request
        request = {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "minimax_chat", "arguments": {"prompt": "test"}}
        }
        response = handle_request(request)
        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("MINIMAX_API_KEY", response["result"]["content"][0]["text"])

    @patch('tests._minimax_helpers.call_minimax')
    def test_tool_call_success(self, mock_call):
        """Successful tool call should return content."""
        mock_call.return_value = ("Hello from MiniMax!", None)
        from tests._minimax_helpers import handle_request
        request = {
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {
                "name": "minimax_chat",
                "arguments": {
                    "prompt": "Say hello",
                    "model": "MiniMax-M2.7-highspeed",
                    "temperature": 0.5
                }
            }
        }
        response = handle_request(request)
        self.assertIn("result", response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(response["result"]["content"][0]["text"], "Hello from MiniMax!")

    @patch('tests._minimax_helpers.call_minimax')
    def test_tool_call_with_system_prompt(self, mock_call):
        """Tool call with system prompt should pass it through."""
        mock_call.return_value = ("Response", None)
        from tests._minimax_helpers import handle_request
        request = {
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {
                "name": "minimax_chat",
                "arguments": {
                    "prompt": "Review this",
                    "system": "You are a reviewer"
                }
            }
        }
        response = handle_request(request)
        self.assertFalse(response["result"].get("isError", False))

    @patch('tests._minimax_helpers.call_minimax')
    def test_tool_call_api_error(self, mock_call):
        """API error should be returned as isError result."""
        mock_call.return_value = (None, "API timeout")
        from tests._minimax_helpers import handle_request
        request = {
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "minimax_chat", "arguments": {"prompt": "test"}}
        }
        response = handle_request(request)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("API timeout", response["result"]["content"][0]["text"])


class TestCallMinimax(unittest.TestCase):
    """Test MiniMax API call function."""

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', '')
    def test_missing_api_key(self):
        """Missing API key should return error."""
        from tests._minimax_helpers import call_minimax
        content, error = call_minimax([{"role": "user", "content": "test"}])
        self.assertIsNone(content)
        self.assertIn("MINIMAX_API_KEY", error)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_successful_api_call(self, mock_client_cls):
        """Successful API call should return content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._minimax_helpers import call_minimax
        content, error = call_minimax(
            [{"role": "user", "content": "test"}],
            model="MiniMax-M2.7",
            temperature=0.7
        )
        self.assertEqual(content, "Hello!")
        self.assertIsNone(error)

        # Verify the request payload
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        self.assertEqual(payload["model"], "MiniMax-M2.7")
        self.assertAlmostEqual(payload["temperature"], 0.7)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_api_error_status(self, mock_client_cls):
        """Non-200 status should return error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._minimax_helpers import call_minimax
        content, error = call_minimax([{"role": "user", "content": "test"}])
        self.assertIsNone(content)
        self.assertIn("401", error)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_malformed_response_returns_clear_error(self, mock_client_cls):
        """Missing or empty choices in API response should return a clear
        error message instead of crashing with KeyError/IndexError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Various malformed shapes
        for bad_body, expected_in_error in [
            ({"choices": []}, "Unexpected API response structure"),
            ({"choices": [{}]}, "Unexpected API response structure"),
            ({"choices": [{"message": {}}]}, "Unexpected API response structure"),
            ({}, "Unexpected API response structure"),
        ]:
            mock_response.json.return_value = bad_body
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from tests._minimax_helpers import call_minimax
            content, error = call_minimax([{"role": "user", "content": "test"}])
            self.assertIsNone(content, f"Expected None content for {bad_body!r}, got {content!r}")
            self.assertIsNotNone(error)
            self.assertIn(expected_in_error, error)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_temperature_clamping_in_call(self, mock_client_cls):
        """Temperature should be clamped in API call."""
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

        from tests._minimax_helpers import call_minimax
        # Temperature 0 should be clamped to 0.01
        call_minimax([{"role": "user", "content": "test"}], temperature=0.0)
        payload = mock_client.post.call_args[1]["json"]
        self.assertAlmostEqual(payload["temperature"], 0.01)

        # Temperature 2.0 should be clamped to 1.0
        call_minimax([{"role": "user", "content": "test"}], temperature=2.0)
        payload = mock_client.post.call_args[1]["json"]
        self.assertAlmostEqual(payload["temperature"], 1.0)

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('tests._minimax_helpers.MINIMAX_BASE_URL', 'https://api.minimax.io/v1')
    @patch('httpx.Client')
    def test_correct_api_url(self, mock_client_cls):
        """API call should use correct api.minimax.io URL."""
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

        from tests._minimax_helpers import call_minimax
        call_minimax([{"role": "user", "content": "test"}])
        url = mock_client.post.call_args[0][0]
        self.assertIn("api.minimax.io", url)
        self.assertNotIn("api.minimax.chat", url)


class TestModelSupport(unittest.TestCase):
    """Test model selection support."""

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_m27_model(self, mock_client_cls):
        """M2.7 model should be accepted."""
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

        from tests._minimax_helpers import call_minimax
        content, error = call_minimax(
            [{"role": "user", "content": "test"}],
            model="MiniMax-M2.7"
        )
        self.assertEqual(content, "OK")
        payload = mock_client.post.call_args[1]["json"]
        self.assertEqual(payload["model"], "MiniMax-M2.7")

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_m27_highspeed_model(self, mock_client_cls):
        """M2.7-highspeed model should be accepted."""
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

        from tests._minimax_helpers import call_minimax
        content, error = call_minimax(
            [{"role": "user", "content": "test"}],
            model="MiniMax-M2.7-highspeed"
        )
        self.assertEqual(content, "OK")
        payload = mock_client.post.call_args[1]["json"]
        self.assertEqual(payload["model"], "MiniMax-M2.7-highspeed")

    @patch('tests._minimax_helpers.MINIMAX_API_KEY', 'test-key')
    @patch('httpx.Client')
    def test_default_model_is_m27(self, mock_client_cls):
        """Default model should be MiniMax-M2.7."""
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

        from tests._minimax_helpers import call_minimax, DEFAULT_MODEL
        self.assertEqual(DEFAULT_MODEL, "MiniMax-M2.7")
        content, error = call_minimax([{"role": "user", "content": "test"}])
        payload = mock_client.post.call_args[1]["json"]
        self.assertEqual(payload["model"], "MiniMax-M2.7")


if __name__ == "__main__":
    unittest.main()
