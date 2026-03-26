#!/usr/bin/env python3
"""Generate Claude-review overrides for the upstream Codex-native skills."""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "skills" / "skills-codex"
DEST_ROOT = REPO_ROOT / "skills" / "skills-codex-claude-review"

TARGET_SKILLS = [
    "research-review",
    "novelty-check",
    "research-refine",
    "auto-review-loop",
    "paper-plan",
    "paper-figure",
    "paper-write",
    "auto-paper-improvement-loop",
]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
SPAWN_BLOCK_RE = re.compile(r"```(?:yaml|text)?\nspawn_agent:\n([\s\S]*?)```")
SEND_BLOCK_RE = re.compile(r"```(?:yaml|text)?\nsend_input:\n([\s\S]*?)```")

OVERRIDE_NOTE = (
    "> Override for Codex users who want **Claude Code**, not a second Codex agent, "
    "to act as the reviewer. Install this package **after** `skills/skills-codex/*`."
)

REVIEWER_LINE = (
    "- **REVIEWER_MODEL = `claude-review`** — Claude reviewer invoked through the "
    "local `claude-review` MCP bridge. Set `CLAUDE_REVIEW_MODEL` if you need a "
    "specific Claude model override."
)

PREREQ_BLOCK = """## Prerequisites

- Install the base Codex-native skills first: copy `skills/skills-codex/*` into `~/.codex/skills/`.
- Then install this overlay package: copy `skills/skills-codex-claude-review/*` into `~/.codex/skills/` and allow it to overwrite the same skill names.
- Register the local reviewer bridge:
  ```bash
  codex mcp add claude-review -- python3 ~/.codex/mcp-servers/claude-review/server.py
  ```
- This gives Codex access to `mcp__claude-review__review_start`, `mcp__claude-review__review_reply_start`, and `mcp__claude-review__review_status`.
""".strip()


def extract_field(frontmatter: str, field: str) -> str:
    pattern = re.compile(rf"^{re.escape(field)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(frontmatter)
    if not match:
        return ""
    value = match.group(1).strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            value = value[1:-1]
    return value


def build_frontmatter(name: str, description: str) -> str:
    safe_desc = description.replace('"', '\\"')
    return f'---\nname: "{name}"\ndescription: "{safe_desc}"\n---\n\n'


def normalize_description(text: str) -> str:
    text = text or "Claude-review override for a Codex-native ARIS skill."
    text = text.replace("GPT using a secondary Codex agent", "Claude via claude-review MCP")
    text = text.replace("using a secondary Codex agent", "using Claude Code via claude-review MCP")
    text = text.replace("via GPT-5.4 xhigh review", "via Claude review through claude-review MCP")
    return text


def rewrite_spawn_block(match: re.Match[str]) -> str:
    lines = match.group(1).splitlines()
    out = ["```", "mcp__claude-review__review_start:"]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("model:") or stripped.startswith("reasoning_effort:"):
            continue
        if stripped.startswith("message:"):
            out.append(line.replace("message:", "prompt:", 1))
            continue
        out.append(line)
    out.append("```")
    return "\n".join(out)


def rewrite_send_block(match: re.Match[str]) -> str:
    lines = match.group(1).splitlines()
    out = ["```", "mcp__claude-review__review_reply_start:"]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("model:") or stripped.startswith("reasoning_effort:"):
            continue
        if stripped.startswith("id:"):
            out.append(line.replace("id:", "threadId:", 1))
            continue
        if stripped.startswith("message:"):
            out.append(line.replace("message:", "prompt:", 1))
            continue
        out.append(line)
    out.append("```")
    return "\n".join(out)


def append_async_notes(text: str) -> str:
    note = (
        "After this start call, immediately save the returned `jobId` and poll "
        "`mcp__claude-review__review_status` with a bounded `waitSeconds` until "
        "`done=true`. Treat the completed status payload's `response` as the "
        "reviewer output, and save the completed `threadId` for any follow-up round."
    )

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        if note in block:
            return block
        return f"{block}\n\n{note}"

    return re.sub(
        r"```(?:yaml|text)?\n(?:mcp__claude-review__review_start:|mcp__claude-review__review_reply_start:)[\s\S]*?```",
        repl,
        text,
    )


def transform_body(text: str) -> str:
    text = text.replace("secondary Codex agent", "Claude reviewer via `claude-review` MCP")
    text = text.replace("via a Claude reviewer via `claude-review` MCP (xhigh reasoning)", "via `claude-review` MCP (high-rigor review)")
    text = text.replace("secondary Codex agent (xhigh reasoning)", "Claude reviewer via `claude-review` MCP")
    text = text.replace("GPT-5.4 xhigh", "Claude review")
    text = text.replace("Send the full paper text to GPT-5.4 xhigh:", "Send the full paper text to Claude through `claude-review`:")
    text = text.replace("Send the complete outline to GPT-5.4 xhigh for feedback:", "Send the complete outline to Claude for feedback:")
    text = text.replace("Call REVIEWER_MODEL via `spawn_agent` (`spawn_agent`) with xhigh reasoning:", "Call REVIEWER_MODEL via `mcp__claude-review__review_start` with high-rigor review:")
    text = text.replace("Send a detailed prompt with xhigh reasoning:", "Send a detailed prompt with high-rigor review:")
    text = text.replace("Use `send_input` with the returned agent id to continue the conversation:", "Use `mcp__claude-review__review_reply_start` with the saved completed `threadId`, then poll `mcp__claude-review__review_status` with the returned `jobId` until `done=true` to continue the conversation:")
    text = text.replace("If this is round 2+, use `send_input` with the saved agent id to maintain continuity.", "If this is round 2+, use `mcp__claude-review__review_reply_start` with the saved completed `threadId`, then poll `mcp__claude-review__review_status` with the returned `jobId` until `done=true` to maintain continuity.")
    text = text.replace("Save the agent id for Round 2.", "Save the returned `jobId`, poll `mcp__claude-review__review_status` until `done=true`, then save the completed `threadId` for Round 2.")
    text = text.replace("Save agent id from first call, use `send_input` for subsequent rounds", "Save the completed `threadId` from the first `mcp__claude-review__review_status` result, then use `mcp__claude-review__review_reply_start` plus `mcp__claude-review__review_status` for subsequent rounds")
    text = text.replace("Document the agent id for potential future resumption", "Document the completed `threadId` for potential future resumption")
    text = text.replace("Use `send_input` with the saved agent id:", "Use `mcp__claude-review__review_reply_start` with the saved completed `threadId`:")
    text = text.replace("use `send_input` for Round 2 to maintain conversation context", "use `mcp__claude-review__review_reply_start` plus `mcp__claude-review__review_status` for Round 2 to maintain conversation context")
    text = text.replace("Save the agent id for Round 2.", "Save the completed `threadId` for Round 2.")
    text = text.replace("**CRITICAL: Save the `agent_id`** from this call for all later rounds.", "**CRITICAL: Save the returned `jobId`**, poll `mcp__claude-review__review_status` until `done=true`, then save the completed `threadId` from the status result for all later rounds.")
    text = text.replace("- **ALWAYS use `reasoning_effort: xhigh`** for all Codex review calls.", "- **Always ask the Claude reviewer for strict, high-rigor feedback** in every review round.")
    text = text.replace("- **Save `agent_id` from Phase 2** and use `send_input` for later rounds.", "- **Save the completed `threadId` from Phase 2** and use `mcp__claude-review__review_reply_start` plus `mcp__claude-review__review_status` for later rounds.")
    text = text.replace("- **Use `send_input`** for Round 2 to maintain conversation context", "- **Use `mcp__claude-review__review_reply_start` plus `mcp__claude-review__review_status`** for Round 2 to maintain conversation context")
    text = text.replace("GPT-5.4 responses", "Claude reviewer responses")
    text = text.replace("`agent_id`", "`thread_id`")
    text = text.replace('"agent_id"', '"thread_id"')
    text = text.replace("ALWAYS use `reasoning_effort: xhigh` for reviews", "Always ask the Claude reviewer for strict, high-rigor feedback.")
    text = text.replace("ALWAYS use `reasoning_effort: xhigh` for maximum reasoning depth", "Always ask the Claude reviewer for strict, high-rigor feedback.")
    text = text.replace("mcp__codex__codex", "mcp__claude-review__review_start")
    text = text.replace("mcp__codex__codex-reply", "mcp__claude-review__review_reply_start")
    text = re.sub(r"^-\s+\*{0,2}REVIEWER_MODEL.*$", REVIEWER_LINE, text, flags=re.MULTILINE)
    text = re.sub(
        r"## Prerequisites\n\n(?:- .*\n)+",
        PREREQ_BLOCK + "\n\n",
        text,
        count=1,
    )
    text = SPAWN_BLOCK_RE.sub(rewrite_spawn_block, text)
    text = SEND_BLOCK_RE.sub(rewrite_send_block, text)
    text = text.replace(
        "```\nreasoning_effort: xhigh\n```",
        "```\nmcp__claude-review__review_start:\n  prompt: |\n    [Full novelty briefing + prior work list + specific novelty questions]\n```",
    )
    return append_async_notes(text)


def generate_one(skill_name: str) -> None:
    skill_path = SRC_ROOT / skill_name / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(f"Missing frontmatter: {skill_path}")

    frontmatter = match.group(1)
    body = content[match.end():].lstrip("\n")
    name = extract_field(frontmatter, "name") or skill_name
    description = normalize_description(extract_field(frontmatter, "description"))

    output = build_frontmatter(name, description)
    output += OVERRIDE_NOTE + "\n\n"
    output += transform_body(body).rstrip() + "\n"

    target_dir = DEST_ROOT / skill_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "SKILL.md").write_text(output, encoding="utf-8")


def main() -> None:
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    for skill_name in TARGET_SKILLS:
        generate_one(skill_name)


if __name__ == "__main__":
    main()
