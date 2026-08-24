#!/usr/bin/env python3
"""Review-gate coverage for the llm-chat HTTP fallback backend."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "review_gate.py"
SPEC = importlib.util.spec_from_file_location("http_fallback_review_gate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review_gate
SPEC.loader.exec_module(review_gate)


def test_llm_chat_positive_cross_family_verdict_stops() -> None:
    transition = review_gate.evaluate_transition(
        round_backend="llm-chat",
        score=8,
        verdict="ready",
        executor_model="shangtang-glm",
        reviewer_model="gemini-2.5-pro",
    )

    assert transition.decision == "stop"
    assert transition.next_backend is None
    assert transition.requires_external_acquittal is False
    assert transition.identity_assurance == "caller_declared"


def test_llm_chat_same_family_verdict_fails_closed() -> None:
    transition = review_gate.evaluate_transition(
        round_backend="llm-chat",
        score=8,
        verdict="ready",
        executor_model="shangtang-glm",
        reviewer_model="zhipu-glm",
    )

    assert transition.decision == "review_unavailable"
    assert transition.identity_assurance == "failed"


def test_llm_chat_unknown_family_verdict_fails_closed() -> None:
    transition = review_gate.evaluate_transition(
        round_backend="llm-chat",
        score=8,
        verdict="ready",
        executor_model="shangtang-glm",
        reviewer_model="mystery-reviewer",
    )

    assert transition.decision == "review_unavailable"


def test_llm_chat_negative_verdict_continues_on_same_backend() -> None:
    transition = review_gate.evaluate_transition(
        round_backend="llm-chat",
        score=5,
        verdict="not ready",
        executor_model="shangtang-glm",
        reviewer_model="gemini-2.5-pro",
    )

    assert transition.decision == "continue"
    assert transition.next_backend == "llm-chat"


def test_llm_chat_is_not_implicitly_allowed_as_copilot_finalizer() -> None:
    transition = review_gate.evaluate_transition(
        round_backend="llm-chat",
        score=8,
        verdict="ready",
        requires_external_acquittal=True,
        executor_model="claude-sonnet-4-5",
        reviewer_model="gemini-2.5-pro",
    )

    assert transition.decision == "review_unavailable"


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("shangtang-glm", "zhipu"),
        ("GLM-5", "zhipu"),
        ("MiniMax-M2.7", "minimax"),
        ("kimi-k2.5", "moonshot"),
        ("qwen3.6-plus", "qwen"),
        ("mimo-v2.5-pro", "xiaomi"),
        ("doubao-pro-4k", "bytedance"),
        ("grok-4", "xai"),
        ("llama-4", "meta"),
        ("mistral-large", "mistral"),
    ],
)
def test_review_gate_recognizes_http_provider_families(model: str, family: str) -> None:
    assert review_gate.derive_model_family(model) == family


def test_review_gate_parser_accepts_llm_chat_backend() -> None:
    action = next(
        action for action in review_gate.build_parser()._actions
        if action.dest == "round_backend"
    )
    assert "llm-chat" in action.choices
