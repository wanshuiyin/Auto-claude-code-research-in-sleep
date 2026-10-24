#!/usr/bin/env python3
"""Regression tests for the real llm-chat request/model migration.

These tests load ``mcp-servers/llm-chat/server.py`` directly and mock only the
HTTP boundary. The copied implementation in ``tests/_llm_chat_helpers.py`` is
intentionally not used here.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp-servers" / "llm-chat" / "server.py"

BASE_ENV = {
    "LLM_API_KEY": "test-key",
    "LLM_BASE_URL": "https://api.openai.com/v1",
}


def load_server(extra_env=None, *, omit=()):
    """Load the real server under an isolated LLM_* environment."""
    env = dict(BASE_ENV)
    env.update(extra_env or {})
    for key in omit:
        env.pop(key, None)
    with patch.dict(os.environ, env, clear=True):
        spec = importlib.util.spec_from_file_location(
            "llm_chat_request_compatibility_server", SERVER_PATH
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    module._review_threads.clear()
    return module


def mock_http_response(
    content="review text",
    *,
    model="gpt-6.1-sol",
    finish_reason="stop",
    status_code=200,
):
    response = MagicMock()
    response.status_code = status_code
    response.text = content if status_code != 200 else ""
    response.json.return_value = {
        "model": model,
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    return response


def mock_client(*responses):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    if len(responses) > 1:
        client.post.side_effect = list(responses)
    else:
        client.post.return_value = responses[0]
    return client


def call_chat(server, *, model=None, prompt="hello"):
    arguments = {"prompt": prompt}
    if model is not None:
        arguments["model"] = model
    return server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "chat", "arguments": arguments},
        }
    )


def call_review(server, *, model=None, executor_model="claude-sonnet-4-5"):
    arguments = {
        "prompt": "Review this artifact.",
        "executor_model": executor_model,
    }
    if model is not None:
        arguments["model"] = model
    return server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "review", "arguments": arguments},
        }
    )


def chat_error_text(response):
    assert response["result"]["isError"] is True
    return response["result"]["content"][0]["text"]


def review_error_text(response):
    assert response["result"]["isError"] is True
    return json.loads(response["result"]["content"][0]["text"])["error"]


def sent_payload(client):
    assert client.post.call_count == 1
    return client.post.call_args.kwargs["json"]


# ---------------------------------------------------------------------------
# Model configuration and fallback inheritance
# ---------------------------------------------------------------------------


def test_default_model_and_fallback_when_both_unset():
    server = load_server(omit=("LLM_MODEL", "LLM_FALLBACK_MODEL"))
    assert server.DEFAULT_MODEL == "gpt-6.1-sol"
    assert server.FALLBACK_MODEL == "gpt-6.1-sol"


def test_configured_model_is_honored_by_default_and_inherited_fallback():
    server = load_server(
        {"LLM_MODEL": "deepseek-chat"}, omit=("LLM_FALLBACK_MODEL",)
    )
    assert server.DEFAULT_MODEL == "deepseek-chat"
    assert server.FALLBACK_MODEL == "deepseek-chat"


def test_explicit_fallback_model_override_wins():
    server = load_server(
        {
            "LLM_MODEL": "gpt-6.1-sol",
            "LLM_FALLBACK_MODEL": "gpt-6-astra",
        }
    )
    assert server.DEFAULT_MODEL == "gpt-6.1-sol"
    assert server.FALLBACK_MODEL == "gpt-6-astra"


def test_existing_configured_model_override_reaches_request():
    server = load_server({"LLM_MODEL": "deepseek-chat"})
    client = mock_client(mock_http_response("ok", model="deepseek-chat"))

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server)

    assert "result" in response and "isError" not in response["result"]
    assert sent_payload(client)["model"] == "deepseek-chat"


# ---------------------------------------------------------------------------
# Token-budget field selection
# ---------------------------------------------------------------------------


def test_official_openai_chat_uses_max_completion_tokens():
    server = load_server()

    client = mock_client(mock_http_response("ok"))
    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server)

    assert response["result"]["content"][0]["text"] == "ok"
    payload = sent_payload(client)
    assert payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in payload


def test_official_openai_review_uses_max_completion_tokens():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True

    client = mock_client(mock_http_response("Strict review", model="gpt-6-astra"))
    with patch.object(server.httpx, "Client", return_value=client):
        response = call_review(server, model="gpt-6-astra")

    assert not response["result"].get("isError", False)
    payload = sent_payload(client)
    assert payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in payload


def test_third_party_chat_uses_max_tokens():
    server = load_server({"LLM_BASE_URL": "https://api.deepseek.com/v1"})

    client = mock_client(mock_http_response("ok", model="deepseek-chat"))
    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server, model="deepseek-chat")

    assert response["result"]["content"][0]["text"] == "ok"
    payload = sent_payload(client)
    assert payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in payload


def test_third_party_review_uses_max_tokens():
    server = load_server({"LLM_BASE_URL": "https://api.deepseek.com/v1"})
    server.REVIEW_FALLBACK_ENABLED = True

    client = mock_client(mock_http_response("Strict review", model="deepseek-reasoner"))
    with patch.object(server.httpx, "Client", return_value=client):
        response = call_review(server, model="deepseek-reasoner")

    assert not response["result"].get("isError", False)
    payload = sent_payload(client)
    assert payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in payload


def test_token_field_override_can_force_max_tokens_on_official_host():
    server = load_server({"LLM_MAX_TOKENS_FIELD": "max_tokens"})
    server.REVIEW_FALLBACK_ENABLED = True

    chat_client = mock_client(mock_http_response("ok"))
    with patch.object(server.httpx, "Client", return_value=chat_client):
        call_chat(server)
    assert sent_payload(chat_client)["max_tokens"] == 4096

    review_client = mock_client(mock_http_response("Strict review", model="gemini-2.5-pro"))
    with patch.object(server.httpx, "Client", return_value=review_client):
        call_review(server, model="gemini-2.5-pro")
    review_payload = sent_payload(review_client)
    assert review_payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in review_payload


def test_token_field_override_can_force_max_completion_tokens_on_third_party():
    server = load_server(
        {
            "LLM_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_MAX_TOKENS_FIELD": "max_completion_tokens",
        }
    )
    server.REVIEW_FALLBACK_ENABLED = True

    chat_client = mock_client(mock_http_response("ok", model="deepseek-chat"))
    with patch.object(server.httpx, "Client", return_value=chat_client):
        call_chat(server, model="deepseek-chat")
    assert sent_payload(chat_client)["max_completion_tokens"] == 4096

    review_client = mock_client(mock_http_response("Strict review", model="deepseek-reasoner"))
    with patch.object(server.httpx, "Client", return_value=review_client):
        call_review(server, model="deepseek-reasoner")
    review_payload = sent_payload(review_client)
    assert review_payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in review_payload


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com.evil.example/v1",
        "https://notapi.openai.com/v1",
        "https://example.com/api.openai.com/v1",
    ],
)
def test_hostname_check_does_not_use_substring_matching(base_url):
    server = load_server({"LLM_BASE_URL": base_url})

    client = mock_client(mock_http_response("ok"))
    with patch.object(server.httpx, "Client", return_value=client):
        call_chat(server)

    payload = sent_payload(client)
    assert payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in payload


def test_invalid_token_field_fails_before_chat_dispatch():
    server = load_server({"LLM_MAX_TOKENS_FIELD": "max_output_tokens"})
    client = mock_client(mock_http_response("should not be used"))

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server)

    message = chat_error_text(response)
    assert "Invalid LLM_MAX_TOKENS_FIELD" in message
    assert "max_completion_tokens" in message
    client.post.assert_not_called()


def test_invalid_token_field_fails_before_review_dispatch_and_creates_no_thread():
    server = load_server({"LLM_MAX_TOKENS_FIELD": "max_output_tokens"})
    server.REVIEW_FALLBACK_ENABLED = True
    client = mock_client(mock_http_response("should not be used", model="gemini-2.5-pro"))

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_review(server, model="gemini-2.5-pro")

    assert "Invalid LLM_MAX_TOKENS_FIELD" in review_error_text(response)
    client.post.assert_not_called()
    assert server._review_threads == {}


# ---------------------------------------------------------------------------
# Blank / non-text / truncated responses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ("", "empty text content"),
        ("   \n\t", "empty text content"),
        (None, "non-text content"),
    ],
)
def test_legacy_chat_rejects_blank_or_non_text_without_retry(content, expected_error):
    server = load_server()
    client = mock_client(mock_http_response(content))

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server)

    message = chat_error_text(response)
    assert expected_error in message
    assert "budget" in message
    assert client.post.call_count == 1


def test_legacy_chat_accepts_nonempty_partial_text_at_length_limit():
    server = load_server()
    client = mock_client(
        mock_http_response("partial legacy answer", finish_reason="length")
    )

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_chat(server)

    assert "isError" not in response["result"]
    assert response["result"]["content"][0]["text"] == "partial legacy answer"
    assert client.post.call_count == 1


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ("", "empty text content"),
        ("  ", "empty text content"),
        (None, "non-text content"),
    ],
)
def test_strict_review_rejects_blank_content_single_attempt_no_thread(
    content, expected_error
):
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    client = mock_client(mock_http_response(content, model="gemini-2.5-pro"))

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_review(server, model="gemini-2.5-pro")

    message = review_error_text(response)
    assert expected_error in message
    assert "budget" in message
    assert client.post.call_count == 1
    assert server._review_threads == {}


def test_strict_review_rejects_length_limited_partial_verdict():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    client = mock_client(
        mock_http_response(
            "Verdict: PARTIAL", model="gemini-2.5-pro", finish_reason="length"
        )
    )

    with patch.object(server.httpx, "Client", return_value=client):
        response = call_review(server, model="gemini-2.5-pro")

    message = review_error_text(response)
    assert "truncated" in message
    assert "partial review verdict" in message
    assert "budget" in message
    assert client.post.call_count == 1
    assert server._review_threads == {}


def test_strict_review_structure_error_is_single_attempt_no_thread():
    server = load_server()
    server.REVIEW_FALLBACK_ENABLED = True
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    response.json.return_value = {"choices": []}
    client = mock_client(response)

    with patch.object(server.httpx, "Client", return_value=client):
        review = call_review(server, model="gemini-2.5-pro")

    assert "Unexpected API response structure" in review_error_text(review)
    assert client.post.call_count == 1
    assert server._review_threads == {}
