#!/usr/bin/env python3
"""Regression checks for the shared Codex -> HTTP reviewer fallback contract."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTING = (
    REPO_ROOT / "skills" / "shared-references" / "reviewer-routing.md"
).read_text(encoding="utf-8")


def test_http_fallback_is_explicit_opt_in_and_pre_dispatch_only():
    assert "Optional HTTP API fallback for Codex pre-dispatch failures" in ROUTING
    assert "LLM_REVIEW_FALLBACK_ENABLED=true" in ROUTING
    assert "pre-dispatch-only" in ROUTING
    assert "mcp__llm-chat__review" in ROUTING
    assert "mcp__llm-chat__review_reply" in ROUTING
    assert "Codex-exec\nnightmare-mode behavior is unchanged" in ROUTING


def test_http_fallback_keeps_ambiguous_codex_failures_closed():
    assert "MUST NOT run merely because a dispatched Codex call timed out" in ROUTING
    assert "risks double-running and conflicting verdicts" in ROUTING
    assert "NEVER downgrade on" in ROUTING


def test_http_fallback_requires_primary_artifacts_and_cross_family_identity():
    assert "Pass primary artifacts, not executor-written summaries" in ROUTING
    assert "actual reviewer model" in ROUTING
    assert "same-family identity is `REVIEW_UNAVAILABLE`" in ROUTING


def test_http_fallback_preserves_multi_round_and_rebuttal_continuity():
    assert "hard-mode rebuttal ruling in the same round" in ROUTING
    assert "review_reply` carries the prior user/reviewer exchanges" in ROUTING


def test_auto_review_loop_relabels_the_backend_that_actually_ran():
    assert "REVIEWER_BACKEND=llm-chat" in ROUTING
    assert "round_backend=llm-chat" in ROUTING
    assert "round_requires_external_acquittal=false" in ROUTING
    assert "review_gate.py --round-backend llm-chat" in ROUTING
