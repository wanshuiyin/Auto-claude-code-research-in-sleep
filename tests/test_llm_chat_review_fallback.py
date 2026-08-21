#!/usr/bin/env python3
"""Tests for opt-in ARIS HTTP reviewer fallback in llm-chat MCP."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp-servers" / "llm-chat" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("llm_chat_review_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._review_threads.clear()
    return module


def tool_names(module):
    resp = module.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    return [tool["name"] for tool in resp["result"]["tools"]]


def parse_tool_payload(resp):
    return json.loads(resp["result"]["content"][0]["text"])


def mock_http_response(content, model, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.text = content if status_code != 200 else ""
    response.json.return_value = {
        "model": model,
        "choices": [{"message": {"content": content}}],
    }
    return response


def mock_client_with(*responses):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    if len(responses) > 1:
        client.post.side_effect = list(responses)
    else:
        client.post.return_value = responses[0]
    return client


def test_review_tools_are_opt_in():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = False
    assert tool_names(server) == ["chat"]

    server.REVIEW_FALLBACK_ENABLED = True
    assert tool_names(server) == ["chat", "review", "review_reply"]


def test_review_returns_identity_and_thread_for_cross_family_model():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    response = mock_http_response("Strict review", "gemini-2.5-pro")
    client = mock_client_with(response)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review this artifact.",
                        "executor_model": "claude-sonnet-4-5",
                        "model": "gemini-2.5-pro",
                    },
                },
            }
        )

    assert not resp["result"].get("isError", False)
    payload = parse_tool_payload(resp)
    assert payload["content"] == "Strict review"
    assert payload["reviewer_model"] == "gemini-2.5-pro"
    assert payload["reviewer_family"] == "google"
    assert payload["executor_family"] == "anthropic"
    assert payload["family_relation"] == "different"
    assert payload["independence_verified"] == "unverified"
    assert payload["threadId"] in server._review_threads


def test_review_rejects_same_family():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    response = mock_http_response("Looks good", "glm-5")
    client = mock_client_with(response)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review.",
                        "executor_model": "shangtang-glm",
                        "model": "glm-5",
                    },
                },
            }
        )

    assert resp["result"]["isError"] is True
    assert "different model family" in parse_tool_payload(resp)["error"]


def test_review_rejects_unknown_executor_family():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    response = mock_http_response("Review", "gpt-5.5")
    client = mock_client_with(response)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review.",
                        "executor_model": "mystery-model-xyz",
                    },
                },
            }
        )

    assert resp["result"]["isError"] is True
    assert "executor_model" in parse_tool_payload(resp)["error"]


def test_review_reply_preserves_thread_history_and_model():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    first = mock_http_response("Round one", "gemini-2.5-pro")
    second = mock_http_response("Round two", "gemini-2.5-pro")
    client = mock_client_with(first, second)

    with patch.object(server.httpx, "Client", return_value=client):
        initial = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Initial review.",
                        "executor_model": "claude-opus-4-1",
                        "model": "gemini-2.5-pro",
                    },
                },
            }
        )
        thread_id = parse_tool_payload(initial)["threadId"]

        reply = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "review_reply",
                    "arguments": {
                        "threadId": thread_id,
                        "prompt": "Re-check the revision.",
                    },
                },
            }
        )

    assert not reply["result"].get("isError", False)
    payload = parse_tool_payload(reply)
    assert payload["threadId"] == thread_id
    assert payload["content"] == "Round two"
    assert payload["independence_verified"] == "unverified"

    second_payload = client.post.call_args_list[1].kwargs["json"]
    messages = second_payload["messages"]
    assert messages == [
        {"role": "user", "content": "Initial review."},
        {"role": "assistant", "content": "Round one"},
        {"role": "user", "content": "Re-check the revision."},
    ]
    assert second_payload["model"] == "gemini-2.5-pro"


def test_review_reply_rejects_identity_changes():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    first = mock_http_response("Round one", "gemini-2.5-pro")
    client = mock_client_with(first)

    with patch.object(server.httpx, "Client", return_value=client):
        initial = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 61,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Initial review.",
                        "executor_model": "claude-opus-4-1",
                        "model": "gemini-2.5-pro",
                    },
                },
            }
        )
        thread_id = parse_tool_payload(initial)["threadId"]

        changed_executor = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 62,
                "method": "tools/call",
                "params": {
                    "name": "review_reply",
                    "arguments": {
                        "threadId": thread_id,
                        "prompt": "Continue.",
                        "executor_model": "gpt-5.5",
                    },
                },
            }
        )
        changed_model = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 63,
                "method": "tools/call",
                "params": {
                    "name": "review_reply",
                    "arguments": {
                        "threadId": thread_id,
                        "prompt": "Continue.",
                        "model": "gpt-5.5",
                    },
                },
            }
        )

    assert changed_executor["result"]["isError"] is True
    assert "executor_model cannot change" in parse_tool_payload(changed_executor)["error"]
    assert changed_model["result"]["isError"] is True
    assert "reviewer model cannot change" in parse_tool_payload(changed_model)["error"]
    assert client.post.call_count == 1


def test_review_504_is_single_attempt_fail_closed():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"
    server.DEFAULT_MODEL = "gpt-5.5"
    server.FALLBACK_MODEL = "gemini-2.5-pro"

    timeout = MagicMock(status_code=504, text="Gateway Timeout")
    client = mock_client_with(timeout)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review.",
                        "executor_model": "claude-sonnet-4-5",
                    },
                },
            }
        )

    assert resp["result"]["isError"] is True
    assert "API error 504" in parse_tool_payload(resp)["error"]
    assert client.post.call_count == 1
    assert server._review_threads == {}
    assert client.post.call_args.kwargs["json"]["model"] == "gpt-5.5"


def test_review_timeout_is_single_attempt_fail_closed():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.side_effect = server.httpx.ReadTimeout("ambiguous timeout")

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 71,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review.",
                        "executor_model": "claude-sonnet-4-5",
                        "model": "gemini-2.5-pro",
                    },
                },
            }
        )

    assert resp["result"]["isError"] is True
    assert "ambiguous timeout" in parse_tool_payload(resp)["error"]
    assert client.post.call_count == 1
    assert server._review_threads == {}


def test_review_reply_failure_does_not_mutate_thread_history():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    first = mock_http_response("Round one", "gemini-2.5-pro")
    timeout = MagicMock(status_code=504, text="Gateway Timeout")
    client = mock_client_with(first, timeout)

    with patch.object(server.httpx, "Client", return_value=client):
        initial = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 72,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Initial review.",
                        "executor_model": "claude-opus-4-1",
                        "model": "gemini-2.5-pro",
                    },
                },
            }
        )
        thread_id = parse_tool_payload(initial)["threadId"]
        before = list(server._review_threads[thread_id]["messages"])
        reply = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 73,
                "method": "tools/call",
                "params": {
                    "name": "review_reply",
                    "arguments": {
                        "threadId": thread_id,
                        "prompt": "Re-check.",
                    },
                },
            }
        )

    assert reply["result"]["isError"] is True
    assert client.post.call_count == 2
    assert server._review_threads[thread_id]["messages"] == before


def test_legacy_chat_keeps_retry_and_fallback_behavior():
    server = load_server()
    server.API_KEY = "test-key"
    server.FALLBACK_MODEL = "gemini-2.5-pro"

    timeout_1 = MagicMock(status_code=504)
    timeout_2 = MagicMock(status_code=504)
    success = mock_http_response("Fallback chat", "gemini-2.5-pro")
    client = mock_client_with(timeout_1, timeout_2, success)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 74,
                "method": "tools/call",
                "params": {
                    "name": "chat",
                    "arguments": {
                        "prompt": "Chat.",
                        "model": "gpt-5.5",
                    },
                },
            }
        )

    assert not resp["result"].get("isError", False)
    assert client.post.call_count == 3
    assert "Used fallback model gemini-2.5-pro" in resp["result"]["content"][0]["text"]


def test_model_family_uses_boundaries_for_ollama_wrapper():
    server = load_server()
    assert server.model_family("ollama/deepseek-r1") == "deepseek"
    assert server.model_family("meta/llama-3.3") == "meta"
    assert server.model_family("claude-gpt-4") == "unknown"


def test_review_rejects_provider_reported_same_family_alias():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    response = mock_http_response("Review", "claude-sonnet-4-5")
    client = mock_client_with(response)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review.",
                        "executor_model": "claude-opus-4-1",
                        "model": "gemini-alias",
                    },
                },
            }
        )

    assert resp["result"]["isError"] is True
    assert "different model family" in parse_tool_payload(resp)["error"]


def test_review_sends_primary_files_verbatim(tmp_path):
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    server.API_KEY = "test-key"

    artifact = tmp_path / "paper.md"
    artifact.write_text("PRIMARY_EVIDENCE=42\n", encoding="utf-8")
    response = mock_http_response("Reviewed evidence", "gemini-2.5-pro")
    client = mock_client_with(response)

    with patch.object(server.httpx, "Client", return_value=client):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {
                        "prompt": "Review the attached primary artifact.",
                        "executor_model": "claude-sonnet-4-5",
                        "model": "gemini-2.5-pro",
                        "files": [str(artifact)],
                    },
                },
            }
        )

    assert not resp["result"].get("isError", False)
    api_payload = client.post.call_args.kwargs["json"]
    user_content = api_payload["messages"][-1]["content"]
    assert "PRIMARY_EVIDENCE=42" in user_content
    assert f"ARIS PRIMARY ARTIFACT: {artifact}" in user_content


def test_disabled_review_call_fails_with_opt_in_instruction():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = False

    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "review",
                "arguments": {
                    "prompt": "Review.",
                    "executor_model": "claude-sonnet-4-5",
                },
            },
        }
    )
    assert resp["result"]["isError"] is True
    assert "LLM_REVIEW_FALLBACK_ENABLED=true" in parse_tool_payload(resp)["error"]
