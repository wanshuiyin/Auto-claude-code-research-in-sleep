"""Static contract guards for non-blocking AUTO_PROCEED checkpoints."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SKILLS = (
    REPO_ROOT / "skills" / "research-pipeline" / "SKILL.md",
    REPO_ROOT / "skills" / "skills-codex" / "research-pipeline" / "SKILL.md",
)
IDEA_SKILLS = (
    REPO_ROOT / "skills" / "idea-discovery" / "SKILL.md",
    REPO_ROOT / "skills" / "skills-codex" / "idea-discovery" / "SKILL.md",
    REPO_ROOT
    / "skills"
    / "skills-codex-gemini-review"
    / "idea-discovery"
    / "SKILL.md",
)
AUTO_PROCEED_SKILLS = PIPELINE_SKILLS + IDEA_SKILLS

TRUE_BRANCH = re.compile(
    r"\*\*(?:If|When) `AUTO_PROCEED=true` \(non-blocking\):\*\*"
    r"(?P<body>.*?)"
    r"(?=\*\*(?:If|When) `AUTO_PROCEED=false` \(blocking\):\*\*)",
    re.DOTALL,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_all_auto_proceed_variants_define_same_turn_checkpoint_semantics() -> None:
    for path in AUTO_PROCEED_SKILLS:
        text = read(path)
        assert "## Checkpoint execution rule" in text, path
        assert "`AUTO_PROCEED=true` is non-blocking" in text, path
        assert "continue executing in the **same turn**" in text, path
        assert "Do not ask for confirmation" in text, path
        assert "wait for silence" in text, path
        assert "or end the turn at a checkpoint" in text, path
        assert "`AUTO_PROCEED=false` is blocking" in text, path
        assert "Resume only after an explicit reply" in text, path
        assert "Feishu **interactive** gate" in text, path
        assert "intentional blocking exception" in text, path


def test_auto_proceed_branches_report_a_choice_without_asking() -> None:
    expected_branches = {**{path: 1 for path in PIPELINE_SKILLS}, **{path: 3 for path in IDEA_SKILLS}}
    for path, expected in expected_branches.items():
        branches = [match.group("body") for match in TRUE_BRANCH.finditer(read(path))]
        assert len(branches) == expected, path
        for branch in branches:
            assert "AUTO_PROCEED:" in branch, path
            assert "?" not in branch, path
            assert "same turn" in branch, path


def test_silence_timeout_antipattern_is_absent() -> None:
    forbidden = (
        "wait 10 seconds",
        "(If no response, I'll proceed",
        "or no response + AUTO_PROCEED=true",
        "**pause and present the top ideas",
    )
    for path in AUTO_PROCEED_SKILLS:
        text = read(path)
        for phrase in forbidden:
            assert phrase not in text, f"{path}: stale AUTO_PROCEED instruction: {phrase}"


def test_research_pipeline_passes_resolved_mode_to_nested_workflows() -> None:
    idea_invocation = '/idea-discovery "$ARGUMENTS" — AUTO_PROCEED: $AUTO_PROCEED'
    paper_invocations = (
        '/paper-writing "NARRATIVE_REPORT.md" — venue: <VENUE>, AUTO_PROCEED: $AUTO_PROCEED',
        '/paper-writing "NARRATIVE_REPORT.md" — venue: [VENUE], AUTO_PROCEED: $AUTO_PROCEED',
        '/paper-writing "NARRATIVE_REPORT.md" — venue: $VENUE, AUTO_PROCEED: $AUTO_PROCEED',
    )
    for path in PIPELINE_SKILLS:
        text = read(path)
        assert idea_invocation in text, path
        for invocation in paper_invocations:
            assert invocation in text, (path, invocation)
        assert '/paper-writing "NARRATIVE_REPORT.md — venue: [VENUE]' not in text, path


def test_user_docs_match_same_turn_auto_proceed_contract() -> None:
    docs = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "CUSTOMIZATION.md",
        REPO_ROOT / "docs" / "CUSTOMIZATION_CN.md",
    )
    stale_phrases = (
        "if user doesn't respond",
        "用户不回复时自动",
        "Each phase presents results and waits for your feedback",
    )
    for path in docs:
        text = read(path)
        assert "same turn" in text or "同一轮" in text, path
        for phrase in stale_phrases:
            assert phrase not in text, f"{path}: stale AUTO_PROCEED wording: {phrase}"
