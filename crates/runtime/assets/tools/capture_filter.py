#!/usr/bin/env python3
"""Anti-self-poisoning capture filter for ARIS memory (research-wiki / meta-optimize).

When ARIS captures durable knowledge — a research-wiki idea/claim, a meta-optimize
SKILL.md proposal — it must NOT store *operational noise* that hardens into a
self-cited falsehood. Hermes learned this the hard way: its self-improvement loop
poisoned itself with negative tool-capability claims that "harden into refusals
the agent cites against itself for months after the actual problem was fixed"
(background_review.py). ARIS's research-wiki "failed ideas → anti-repeat memory"
is the GOOD inverse; this filter is the missing blocklist for the BAD kind.

This is a CHEAP, DETERMINISTIC pre-filter for the UNAMBIGUOUS classes — error
output and explicitly-broken-tool phrasing. The judgment-y classes (a single-run
narrative that isn't a class-level rule; an intentional one-off) are prose
guidance in shared-references/capture-antipatterns.md, not regex.

Asymmetry (acceptance-gate.md): this filter may REJECT a capture same-model (it
is a mechanical safety screen, low risk) — but anything that PASSES and would
become a load-bearing skill/claim still goes to the cross-model jury. Same-model
is fine to reject; must-be-cross-model to accept.

Deliberately conservative — anchored so it does NOT flag legitimate RESEARCH
findings ("the model can't generalize to OOD", "the method fails on long
sequences"). It targets ARIS's OWN TOOLING being declared broken, and raw error
output. False negatives are fine (the jury still judges); a false reject just
sends a real insight to manual review.
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import List

# Raw error / environment-failure output — unambiguous; these are transient
# operational state, never a durable research fact.
_ENV_FAILURE = [
    (re.compile(r"\bcommand not found\b", re.I), "env_failure"),
    (re.compile(r"\bNo such file or directory\b", re.I), "env_failure"),
    (re.compile(r"\bNo module named\b", re.I), "env_failure"),
    (re.compile(r"\bModuleNotFoundError\b"), "env_failure"),
    (re.compile(r"\bImportError\b"), "env_failure"),
    (re.compile(r"\bPermission denied\b", re.I), "env_failure"),
    (re.compile(r"\bconnection (refused|timed out|reset)\b", re.I), "transient_error"),
    (re.compile(r"\b(rate limit|429|quota exceeded|503|502|temporarily unavailable)\b", re.I), "transient_error"),
    (re.compile(r"\bCUDA out of memory\b|\bOOM\b", re.I), "transient_error"),
]

# Negative tool-capability claims about ARIS's OWN infrastructure. Anchored on
# ARIS-INFRA-QUALIFIED nouns ONLY — bare model names (codex/gemini/oracle/gpt-5)
# and generic infra words (the api/server/gpu/tool/cli/reviewer) are deliberately
# NOT here, because they appear in legitimate research findings ("Gemini cannot
# solve task T", "the GPU cannot fit the batch", "the API does not expose
# gradients"). Flagging those would suppress real research notes — the failure
# this filter must avoid. So we require a qualifier (mcp/cli/reviewer/-pro/-review)
# or an unambiguous ARIS tool name.
_TOOL = (r"(?:"
         r"codex[ -](?:mcp|cli|reviewer)|"
         r"oracle[ -](?:mcp|pro|reviewer)|"
         r"gemini[ -](?:mcp|cli|review|reviewer)|"
         r"manual[ -]review|"
         # "claude code" dropped — too broad: research notes may benchmark Claude
         # Code as a coding agent ("Claude Code cannot solve this SWE-bench task"),
         # which is a finding, not an ARIS-infra complaint.
         r"mcp server|reviewer mcp|the reviewer backend|"
         r"wandb"
         r")")
_NEG_CLAIM = [
    (re.compile(_TOOL + r"\s+(?:can'?t|cannot|is unable to|does(?:n'?t| not))\s+", re.I), "negative_tool_claim"),
    (re.compile(_TOOL + r"\s+(?:is|are|was|were)\s+(?:broken|down|useless|unusable|buggy)\b", re.I), "negative_tool_claim"),
    (re.compile(_TOOL + r"\s+always\s+(?:fails|crashes|hangs|errors)\b", re.I), "negative_tool_claim"),
    (re.compile(r"\b(?:don'?t|do not|never)\s+use\s+(?:the\s+|a\s+)?" + _TOOL, re.I), "negative_tool_claim"),
]

_ALL = _ENV_FAILURE + _NEG_CLAIM


def screen(text: str) -> List[str]:
    """Return de-duplicated anti-pattern reason codes found in `text` (empty = clean).

    reason ∈ {env_failure, transient_error, negative_tool_claim}.
    """
    if not text:
        return []
    found: List[str] = []
    for rx, reason in _ALL:
        if reason not in found and rx.search(text):
            found.append(reason)
    return found


def reason_detail(reason: str) -> str:
    return {
        "env_failure": "looks like an environment-specific failure (missing binary/module/path "
                       "/permission) — transient state, not a durable fact. Store HOW TO FIX or "
                       "the missing config, never 'X failed'.",
        "transient_error": "looks like a transient error (rate limit / OOM / network) that "
                           "self-resolves — do not capture it as a durable rule.",
        "negative_tool_claim": "looks like a negative capability claim about ARIS's own tooling "
                              "('X can't / is broken'). These harden into self-cited refusals long "
                              "after the real problem is fixed. Store the fix / the workaround, not "
                              "'X can't do Y'.",
    }.get(reason, reason)


__all__ = ["screen", "reason_detail"]


def main() -> int:
    ap = argparse.ArgumentParser(description="ARIS anti-self-poisoning capture filter.")
    ap.add_argument("path", help="file to screen, or - for stdin")
    a = ap.parse_args()
    text = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()
    reasons = screen(text)
    if reasons:
        print(f"DO-NOT-CAPTURE: {', '.join(reasons)}", file=sys.stderr)
        for r in reasons:
            print(f"  - {r}: {reason_detail(r)}", file=sys.stderr)
        return 1
    print("ok to capture (mechanical screen clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
