"""Regression tests for Claude-review overlay frontmatter generation."""

from __future__ import annotations

import json
from pathlib import Path

from tools.generate_codex_claude_review_overrides import (
    FRONTMATTER_RE,
    TARGET_SKILLS,
    build_frontmatter,
    extract_field,
    normalize_description,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILLS = REPO_ROOT / "skills" / "skills-codex"
CLAUDE_OVERLAY = REPO_ROOT / "skills" / "skills-codex-claude-review"


def _frontmatter_value(text: str, field: str) -> str:
    match = FRONTMATTER_RE.match(text)
    assert match is not None
    line = next(
        line for line in match.group(1).splitlines()
        if line.startswith(f"{field}:")
    )
    return line.split(":", 1)[1].strip()


def test_generator_emits_parseable_string_frontmatter() -> None:
    """Legacy double-escaped descriptions must not return on regeneration."""
    for skill in TARGET_SKILLS:
        source = (CODEX_SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        source_match = FRONTMATTER_RE.match(source)
        assert source_match is not None
        description = normalize_description(
            extract_field(source_match.group(1), "description")
        )
        generated = build_frontmatter(skill, description)

        assert isinstance(json.loads(_frontmatter_value(generated, "name")), str)
        assert isinstance(json.loads(_frontmatter_value(generated, "description")), str)


def test_checked_in_claude_overlay_frontmatter_is_parseable() -> None:
    for skill in TARGET_SKILLS:
        text = (CLAUDE_OVERLAY / skill / "SKILL.md").read_text(encoding="utf-8")
        assert isinstance(json.loads(_frontmatter_value(text, "name")), str)
        assert isinstance(json.loads(_frontmatter_value(text, "description")), str)
