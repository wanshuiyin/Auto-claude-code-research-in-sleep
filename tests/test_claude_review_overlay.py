#!/usr/bin/env python3
"""
Forbidden-token scan for the generated claude-review overlay pack.

The overlay replaces the codex-mirror's same-family reviewer with Claude via
the claude-review MCP. A leftover Codex token means the generator's rules went
stale against the mirror source (the failure mode that shipped half-converted
overlays before): a user following the overlay would call a tool that doesn't
exist or pin an OpenAI model on a Claude server.

Run: python3 tests/test_claude_review_overlay.py   (also pytest-compatible)
"""
import os
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PACK = os.path.join(REPO, "skills", "skills-codex-claude-review")

FORBIDDEN = [
    "mcp__codex__",           # codex MCP tools
    "spawn_agent",            # codex-native reviewer spawn
    "send_input",             # codex-native follow-up
    "gpt-5.6-sol",            # OpenAI model pin (any case)
    "gpt-5.5",                # incl. old default; gpt-5.5-pro Oracle refs are fine -> checked below
    "model_reasoning_effort", # OpenAI effort knob
    "reasoning_effort",       # spawn-form effort knob
]
# Oracle Pro is a legitimate cross-reference in overlay prose
ALLOWED_SUBSTRINGS = ["gpt-5.5-pro", "GPT-5.5 Pro"]


def check_pack(pack=PACK):
    problems = []
    if not os.path.isdir(pack):
        return problems
    for dirpath, _dirnames, filenames in os.walk(pack):
        for fn in filenames:
            if fn != "SKILL.md":   # pack READMEs legitimately describe the upstream mechanics
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, REPO)
            for i, line in enumerate(open(path, encoding="utf-8"), 1):
                probe = line
                for ok in ALLOWED_SUBSTRINGS:
                    probe = probe.replace(ok, "")
                low = probe.lower()
                for tok in FORBIDDEN:
                    if tok.lower() in low:
                        problems.append(f"{rel}:{i}: forbidden token {tok!r}: {line.strip()[:100]}")
    return problems


def test_overlay_has_no_codex_tokens():
    problems = check_pack()
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    ps = check_pack()
    if ps:
        print("\n".join(ps))
        print(f"\n{len(ps)} forbidden tokens in the overlay pack")
        sys.exit(1)
    print("ok: overlay pack is fully converted")
