#!/usr/bin/env python3
"""
Reviewer-pin lint: every fresh Codex reviewer call block in a SKILL.md must pin
BOTH the model and a reasoning effort at or above the review floor.

Why: the catalog default effort for gpt-5.6-sol is `low`, and an unpinned model
silently runs whatever ~/.codex/config.toml says — so an unpinned call block
defeats the routing contract (skills/shared-references/reviewer-routing.md).

Scope (deliberately narrow, so prose can't false-positive):
- fenced code blocks whose first non-blank line starts with `mcp__codex__codex:`
  (fresh threads — `codex-reply` blocks are exempt: replies inherit the thread)
- fenced code blocks whose first non-blank line starts with `spawn_agent:`
  (codex-native mirror fresh reviewer agents)

Run: python3 tests/test_reviewer_pins.py   (also pytest-compatible)
"""
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FLOOR = {"xhigh", "max", "ultra"}
MODEL_RE = re.compile(r"^\s*(?:- )?`?[\"']?model[\"']?`?:\s*(?:[\"'`]?gpt-|REVIEWER_MODEL)", re.M)
EFFORT_RE = re.compile(r"(?:model_)?reasoning_effort[\"'`]?:\s*[\"'`]?([a-z]+)")

# Generated/derived packs are validated by their own generators, and the
# llm-chat pack intentionally strips Codex pins.
EXCLUDED_DIRS = ("skills-codex-claude-review", "skills-codex-gemini-review",
                 "auto-review-loop-llm", "auto-review-loop-minimax")


def _fenced_blocks(text):
    blocks, cur, infence = [], [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            if infence:
                blocks.append("\n".join(cur))
                cur = []
            infence = not infence
            continue
        if infence:
            cur.append(line)
    return blocks


def _first_token(block):
    for line in block.split("\n"):
        if line.strip():
            return line.strip()
    return ""


def check_repo(root=REPO):
    problems = []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(root, "skills")):
        if any(x in dirpath for x in EXCLUDED_DIRS):
            continue
        for fn in filenames:
            if fn != "SKILL.md":
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            for block in _fenced_blocks(open(path, encoding="utf-8").read()):
                head = _first_token(block)
                fresh = head.startswith("mcp__codex__codex:") or head.startswith("spawn_agent:")
                if not fresh:
                    continue
                if not MODEL_RE.search(block):
                    problems.append(f"{rel}: fresh reviewer block lacks a model pin ({head})")
                m = EFFORT_RE.search(block)
                if m is None:
                    problems.append(f"{rel}: fresh reviewer block lacks an effort pin ({head})")
                elif m.group(1) not in FLOOR:
                    problems.append(f"{rel}: effort '{m.group(1)}' below review floor ({head})")
    return problems


def test_all_fresh_reviewer_blocks_pin_model_and_floor_effort():
    problems = check_repo()
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    ps = check_repo()
    if ps:
        print("\n".join(ps))
        print(f"\n{len(ps)} unpinned/below-floor reviewer blocks")
        sys.exit(1)
    print("ok: all fresh reviewer blocks pin model + floor effort")
