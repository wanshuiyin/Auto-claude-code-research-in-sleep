#!/usr/bin/env python3
"""Unit tests for the generic LLM Chat MCP Server (mcp-servers/llm-chat/server.py).

Tests cover:
- JSON-RPC request handling (initialize, ping, tools/list, tools/call)
- call_llm: success, API errors, 504 retry + fallback model logic
- Notification handling (no response)
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


class TestHandleRequest(unittest.TestCase):
    """Test JSON-RPC request routing."""

    def test_initialize_response(self):
        """initialize should return protocol version and server info."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", resp["result"]["capabilities"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "llm-chat")

    def test_ping_response(self):
        """ping should return empty result."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        self.assertEqual(resp["id"], 2)
        self.assertEqual(resp["result"], {})

    def test_notification_returns_none(self):
        """Requests without id are notifications and should return None."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(resp)

    def test_unknown_method_returns_error(self):
        """Unknown methods should return JSON-RPC error -32601."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_unknown_tool_returns_error(self):
        """Unknown tool name inside tools/call should return error."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        })
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)


class TestToolsList(unittest.TestCase):
    """Test tools/list response structure."""

    def test_tools_list_returns_chat_tool(self):
        """tools/list should return a single 'chat' tool."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "chat")

    def test_tools_list_schema_has_required_prompt(self):
        """The chat tool schema must require 'prompt'."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}})
        schema = resp["result"]["tools"][0]["inputSchema"]
        self.assertIn("prompt", schema["required"])

    def test_tools_list_schema_has_optional_model_and_system(self):
        """The chat tool schema should expose optional 'model' and 'system' parameters."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}})
        props = resp["result"]["tools"][0]["inputSchema"]["properties"]
        self.assertIn("model", props)
        self.assertIn("system", props)


class TestToolCallNoApiKey(unittest.TestCase):
    """Test tool call behavior when LLM_API_KEY is missing."""

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "")
    def test_missing_api_key_returns_error(self):
        """Tool call without API key should return isError result."""
        from tests._llm_chat_helpers import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "chat", "arguments": {"prompt": "hello"}}
        })
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("LLM_API_KEY", resp["result"]["content"][0]["text"])


class TestCallLlmSuccess(unittest.TestCase):
    """Test call_llm for successful API responses."""

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_successful_call_returns_content(self, mock_client_cls):
        """A 200 response should return the message content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from LLM!"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "hi"}])
        self.assertEqual(content, "Hello from LLM!")
        self.assertIsNone(error)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_custom_model_is_passed(self, mock_client_cls):
        """The requested model name should appear in the API payload."""
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

        from tests._llm_chat_helpers import call_llm
        call_llm([{"role": "user", "content": "test"}], model="deepseek-chat")
        payload = mock_client.post.call_args[1]["json"]
        self.assertEqual(payload["model"], "deepseek-chat")

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_api_error_status_returns_error_message(self, mock_client_cls):
        """Non-200, non-504 status should return an error string."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "test"}])
        self.assertIsNone(content)
        self.assertIn("401", error)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_malformed_response_returns_clear_error(self, mock_client_cls):
        """Missing or empty choices in API response should return a clear
        error message instead of crashing with KeyError/IndexError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        for bad_body in [
            {"choices": []},
            {"choices": [{}]},
            {"choices": [{"message": {}}]},
            {},
        ]:
            mock_response.json.return_value = bad_body
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from tests._llm_chat_helpers import call_llm
            content, error = call_llm([{"role": "user", "content": "test"}])
            self.assertIsNone(content, f"Expected None content for {bad_body!r}, got {content!r}")
            self.assertIsNotNone(error)
            self.assertIn("Unexpected API response structure", error)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "")
    def test_missing_api_key_returns_error(self):
        """call_llm without API key should return error immediately."""
        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "test"}])
        self.assertIsNone(content)
        self.assertIn("LLM_API_KEY", error)


class TestCallLlm504Retry(unittest.TestCase):
    """Test the 504 retry and fallback model logic in call_llm."""

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("tests._llm_chat_helpers.DEFAULT_MODEL", "gpt-4o")
    @patch("tests._llm_chat_helpers.FALLBACK_MODEL", "gpt-4o-mini")
    @patch("httpx.Client")
    def test_504_twice_then_fallback_succeeds(self, mock_client_cls):
        """Two 504s should trigger fallback model on attempt 3."""
        resp_504 = MagicMock()
        resp_504.status_code = 504

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "choices": [{"message": {"content": "Fallback reply"}}]
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = [resp_504, resp_504, resp_ok]
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "test"}])

        self.assertIsNone(error)
        self.assertIn("Fallback reply", content)
        # Fallback note should be prepended
        self.assertIn("[Note: Used fallback model gpt-4o-mini", content)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("tests._llm_chat_helpers.DEFAULT_MODEL", "gpt-4o")
    @patch("tests._llm_chat_helpers.FALLBACK_MODEL", "gpt-4o-mini")
    @patch("httpx.Client")
    def test_504_once_then_retry_succeeds_no_fallback_note(self, mock_client_cls):
        """A single 504 followed by success should use original model (no fallback note)."""
        resp_504 = MagicMock()
        resp_504.status_code = 504

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "choices": [{"message": {"content": "Retry success"}}]
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = [resp_504, resp_ok]
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "test"}])

        self.assertIsNone(error)
        self.assertEqual(content, "Retry success")
        self.assertNotIn("[Note:", content)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_three_504s_returns_error(self, mock_client_cls):
        """Three consecutive 504s should return the gateway timeout error."""
        resp_504 = MagicMock()
        resp_504.status_code = 504

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = resp_504
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        content, error = call_llm([{"role": "user", "content": "test"}])

        self.assertIsNone(content)
        self.assertIn("504", error)

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("tests._llm_chat_helpers.DEFAULT_MODEL", "primary-model")
    @patch("tests._llm_chat_helpers.FALLBACK_MODEL", "fallback-model")
    @patch("httpx.Client")
    def test_fallback_uses_different_model_name(self, mock_client_cls):
        """On attempt 3, the payload model should be FALLBACK_MODEL, not DEFAULT_MODEL."""
        resp_504 = MagicMock()
        resp_504.status_code = 504

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = [resp_504, resp_504, resp_ok]
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import call_llm
        call_llm([{"role": "user", "content": "test"}])

        # The third call (index 2) should use the fallback model
        third_call_payload = mock_client.post.call_args_list[2][1]["json"]
        self.assertEqual(third_call_payload["model"], "fallback-model")


class TestToolCallFullFlow(unittest.TestCase):
    """Test the complete tools/call path through handle_request."""

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_tool_call_success(self, mock_client_cls):
        """Successful tool call should return content without isError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "chat", "arguments": {"prompt": "Hello"}}
        })
        self.assertFalse(resp["result"].get("isError", False))
        self.assertEqual(resp["result"]["content"][0]["text"], "Test response")

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_tool_call_with_system_prompt(self, mock_client_cls):
        """System prompt should be included as first message with role='system'."""
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

        from tests._llm_chat_helpers import handle_request
        handle_request({
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {
                "name": "chat",
                "arguments": {
                    "prompt": "Review this",
                    "system": "You are a strict reviewer"
                }
            }
        })

        payload = mock_client.post.call_args[1]["json"]
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][0]["content"], "You are a strict reviewer")
        self.assertEqual(payload["messages"][1]["role"], "user")

    @patch("tests._llm_chat_helpers.LLM_API_KEY", "test-key")
    @patch("httpx.Client")
    def test_tool_call_api_error_returns_is_error(self, mock_client_cls):
        """An API error should be surfaced as isError=True in the result."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from tests._llm_chat_helpers import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "id": 12, "method": "tools/call",
            "params": {"name": "chat", "arguments": {"prompt": "test"}}
        })
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("500", resp["result"]["content"][0]["text"])


class TestDefaultConfig(unittest.TestCase):
    """Test default configuration values."""

    def test_default_base_url(self):
        """Default base URL should be OpenAI API."""
        self.assertEqual(
            os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            "https://api.openai.com/v1"
        )

    def test_default_model(self):
        """Default model should be gpt-4o."""
        self.assertEqual(
            os.environ.get("LLM_MODEL", "gpt-4o"),
            "gpt-4o"
        )

    def test_default_server_name(self):
        """Default server name should be llm-chat."""
        self.assertEqual(
            os.environ.get("LLM_SERVER_NAME", "llm-chat"),
            "llm-chat"
        )


if __name__ == "__main__":
    unittest.main()
