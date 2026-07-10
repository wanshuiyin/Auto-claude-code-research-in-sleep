#!/usr/bin/env python3
"""Convert Codex-native skills to llm-chat MCP compatible versions.

Reads skills from a source directory, replaces all mcp__codex__codex and
mcp__codex__codex-reply references with mcp__llm-chat__chat, removes
Codex-specific parameters, and writes the converted files to a target
directory. Works on Windows, macOS, and Linux.

Usage:
    # Convert all skills to ~/.claude/skills/
    python convert_skills_to_llm_chat.py

    # Custom source and target
    python convert_skills_to_llm_chat.py --source ./skills --target ./skills-llm-chat

    # Preview changes without writing files
    python convert_skills_to_llm_chat.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


# ── Codex → llm-chat text replacements ──────────────────────────────────

# Tool name replacements
REPLACEMENTS_TEXT: list[tuple[str, str]] = [
    # Tool names
    ("mcp__codex__codex-reply", "mcp__llm-chat__chat"),
    ("mcp__codex__codex", "mcp__llm-chat__chat"),
    # Description text
    ("Always pin `model: gpt-5.6-sol` + `config: {\"model_reasoning_effort\": \"ultra\"}` (deep-audit tier).",
     "Ask the LLM reviewer for its strictest, deepest review (deep-audit tier)."),
    ("for new review threads\n  (`model: gpt-5.6-sol`, `config: {\"model_reasoning_effort\": \"ultra\"}`).",
     "for new review threads."),
    ("`model: gpt-5.6-sol`, `reasoning: ultra`", "the configured `LLM_MODEL`, deepest available reasoning"),
    ("- **ALWAYS use `config: {\"model_reasoning_effort\": \"xhigh\"}`** for all Codex review calls.",
     "- **Always ask the LLM reviewer for strict, high-rigor feedback** in every review round."),
    ("ALWAYS pin `model: gpt-5.6-sol` + `config: {\"model_reasoning_effort\": \"ultra\"}` for reviews (deep-audit tier; capability fallback per `reviewer-routing.md`, never below `xhigh`)",
     "ALWAYS ask the LLM reviewer for strict, maximum-depth review"),
    ("Always use `model_reasoning_effort: \"xhigh\"` for maximum analysis depth.",
     "Always ask the LLM reviewer for maximum analysis depth."),
    ("(`gpt-5.6-sol` via Codex MCP)", "(via llm-chat MCP)"),
    ("override the default reviewer (`gpt-5.6-sol`)", "override the default reviewer"),
    ("via GPT-5.6-Sol xhigh review", "via llm-chat MCP review"),
    ("via GPT-5.6-Sol ultra review", "via llm-chat MCP review"),
    ("GPT-5.6-Sol xhigh", "LLM reviewer"),
    ("GPT-5.6-Sol ultra", "LLM reviewer"),
    ("via GPT-5.5 xhigh review", "via llm-chat MCP review"),
    ("GPT-5.5 xhigh", "LLM reviewer"),
    ("a second Codex agent", "an LLM via llm-chat MCP"),
    ("secondary Codex agent", "LLM reviewer via llm-chat MCP"),
    ("Codex agent", "LLM reviewer"),
    ("- ALWAYS use `config: {\"model_reasoning_effort\": \"xhigh\"}` for maximum reasoning depth",
     "- ALWAYS ask the LLM reviewer for maximum reasoning depth"),
    ("pin `model: gpt-5.6-sol` + `config: {\"model_reasoning_effort\": \"xhigh\"}` per `../shared-references/reviewer-routing.md`",
     "ask for strict, high-rigor review"),
    ("pin `model: gpt-5.6-sol` + `config: {\"model_reasoning_effort\": \"ultra\"}` (deep-audit tier)",
     "ask for strict, maximum-depth review"),
    ("with `model: gpt-5.6-sol`, `config: {model_reasoning_effort: xhigh}`, `sandbox: read-only`, fresh thread",
     "with a fresh thread"),
    ("with `model: gpt-5.6-sol`, `config: {model_reasoning_effort: ultra}`, `sandbox: read-only`, fresh thread",
     "with a fresh thread"),
    ("model_reasoning_effort: \"ultra\"", "# (reasoning effort not supported by llm-chat)"),
    ("model_reasoning_effort: \"xhigh\"", "# (reasoning effort not supported by llm-chat)"),
    ("model_reasoning_effort: ultra", "# (reasoning effort not supported by llm-chat)"),
    ("model_reasoning_effort: xhigh", "# (reasoning effort not supported by llm-chat)"),
    ("reasoning_effort: ultra", "# (reasoning effort not supported by llm-chat)"),
    ("reasoning_effort: xhigh", "# (reasoning effort not supported by llm-chat)"),
    ("reasoning_effort: high", "# (reasoning effort not supported by llm-chat)"),
]

# Regex patterns for structural changes
CONFIG_LINE_RE = re.compile(
    r'^(\s*)(?:- )?`?config`?:\s*\{[^}]*model_reasoning_effort[^}]*\}`?\s*$',
    re.MULTILINE,
)
MODEL_LINE_RE = re.compile(
    r'^(\s*)(?:- )?`?"?model"?`?:\s*(?:["\'`]?gpt-[^\s"\'`]+["\'`]?|REVIEWER_MODEL)\s*$',
    re.MULTILINE,
)
THREAD_ID_LINE_RE = re.compile(
    r'^(\s*)threadId:\s*\S+.*$',
    re.MULTILINE,
)
APPROVAL_POLICY_LINE_RE = re.compile(
    r'^(\s*)approval-policy:\s*\S+.*$',
    re.MULTILINE,
)
SANDBOX_LINE_RE = re.compile(
    r'^(\s*)sandbox:\s*\S+.*$',
    re.MULTILINE,
)
BASE_INSTRUCTIONS_LINE_RE = re.compile(
    r'^(\s*)base-instructions:\s*["\'].*$',
    re.MULTILINE,
)
DEVELOPER_INSTRUCTIONS_LINE_RE = re.compile(
    r'^(\s*)developer-instructions:\s*["\'].*$',
    re.MULTILINE,
)
# Match "prompt:" as a parameter name under mcp tool blocks
PROMPT_PARAM_RE = re.compile(
    r'^(\s*)prompt:\s*\|',
    re.MULTILINE,
)


def convert_content(text: str) -> str:
    """Apply all Codex → llm-chat conversions to skill content."""

    # 1. Simple text replacements
    for old, new in REPLACEMENTS_TEXT:
        text = text.replace(old, new)

    # 1b. Deduplicate mcp tool names in allowed-tools / tool references
    text = re.sub(
        r'(mcp__llm-chat__chat),\s*mcp__llm-chat__chat',
        r'\1',
        text,
    )

    # 2. Remove Codex-specific parameter lines
    for pattern in (
        CONFIG_LINE_RE,
        MODEL_LINE_RE,
        THREAD_ID_LINE_RE,
        APPROVAL_POLICY_LINE_RE,
        SANDBOX_LINE_RE,
        BASE_INSTRUCTIONS_LINE_RE,
        DEVELOPER_INSTRUCTIONS_LINE_RE,
    ):
        text = pattern.sub('', text)

    # 3. Rename "prompt:" → "prompt:" (llm-chat uses "prompt" too based on auto-review-loop-llm)
    #    Actually llm-chat MCP accepts "prompt" as the main parameter, so no rename needed.
    #    The auto-review-loop-llm reference skill uses "prompt:" parameter name.

    # 4. Add conversion note after YAML frontmatter if not already present
    note = (
        "\n> **llm-chat conversion**: This skill has been auto-converted from Codex to "
        "use `mcp__llm-chat__chat`. Multi-turn conversations are handled as single-turn "
        "calls with manual context inclusion.\n"
    )
    if "llm-chat conversion" not in text:
        # Insert after frontmatter
        fm_end = text.find("---", text.find("---") + 3)
        if fm_end != -1:
            fm_end = text.find("\n", fm_end + 3)
            if fm_end != -1:
                text = text[:fm_end + 1] + note + text[fm_end + 1:]

    # 5. Clean up multiple blank lines from removed lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def convert_file(src: Path, dst: Path) -> bool:
    """Convert a single SKILL.md file. Returns True if changes were made."""
    content = src.read_text(encoding="utf-8")
    converted = convert_content(content)

    if converted == content:
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(converted, encoding="utf-8")
    return True


def find_skills(source_dir: Path) -> list[Path]:
    """Find all SKILL.md files under source_dir, excluding known variant dirs."""
    skills = []
    exclude_dirs = {
        "skills-codex",
        "skills-codex-claude-review",
        "skills-codex-gemini-review",
    }
    for skill_md in sorted(source_dir.rglob("SKILL.md")):
        # Skip variant skill directories
        parts = skill_md.relative_to(source_dir).parts
        if any(d in parts for d in exclude_dirs):
            continue
        # Skip skills that already use llm-chat
        content = skill_md.read_text(encoding="utf-8")
        if "mcp__llm-chat__chat" in content and "mcp__codex__codex" not in content:
            continue
        # Only include files that reference codex
        if "mcp__codex__codex" not in content:
            continue
        skills.append(skill_md)
    return skills


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Codex-native skills to llm-chat MCP compatible versions."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source directory containing skill folders (default: repo skills/)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Target directory for converted skills (default: source, in-place)",
    )
    parser.add_argument(
        "--force-in-place",
        action="store_true",
        help="Allow in-place conversion of the repo's canonical skills/ tree (dangerous)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )
    args = parser.parse_args()

    # Default source: skills/ in the same repo as this script
    repo_root = Path(__file__).resolve().parents[1]
    source_dir = args.source or repo_root / "skills"
    target_dir = args.target or source_dir  # in-place by default

    # Refuse to rewrite the repo's canonical skill tree in place — that destroys
    # the Codex-native sources (this exact accident has happened). Convert INTO
    # a separate --target, or pass --force-in-place if you really mean it.
    canonical = (repo_root / "skills").resolve()
    tgt = target_dir.resolve()
    if (tgt == canonical or canonical in tgt.parents) \
            and not args.dry_run and not args.force_in_place:
        print("Error: refusing to convert the repo's canonical skills/ tree in place.")
        print("Pass --target <dir> (recommended) or --force-in-place to override.")
        sys.exit(1)

    if not source_dir.exists():
        print(f"Error: source directory not found: {source_dir}")
        sys.exit(1)

    skills = find_skills(source_dir)
    if not skills:
        print("No Codex-based skills found to convert.")
        return

    print(f"Found {len(skills)} skill(s) to convert:\n")

    converted = 0
    for skill_path in skills:
        rel = skill_path.relative_to(source_dir)
        dst = target_dir / rel

        if args.dry_run:
            content = skill_path.read_text(encoding="utf-8")
            new_content = convert_content(content)
            has_changes = content != new_content
            status = "would convert" if has_changes else "no changes"
            print(f"  [DRY-RUN] {rel} — {status}")
            if has_changes:
                converted += 1
        else:
            if convert_file(skill_path, dst):
                print(f"  Converted: {rel}")
                converted += 1
            else:
                print(f"  No changes: {rel}")

    print(f"\nDone: {converted}/{len(skills)} skill(s) converted.")
    if args.dry_run:
        print("(dry-run mode — no files were written)")


if __name__ == "__main__":
    main()
