from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
MAINLINE_SKILLS = REPO_ROOT / "skills"
CODEX_SKILLS = MAINLINE_SKILLS / "skills-codex"
MAINLINE_FANOUT = MAINLINE_SKILLS / "shared-references" / "fan-out-pattern.md"
CODEX_FANOUT = CODEX_SKILLS / "shared-references" / "fan-out-pattern.md"
LEAF_AGENT = REPO_ROOT / "agents" / "aris-fanout-leaf.md"

EXPECTED_CONTRACT = {
    "ARIS_FANOUT_AGENT_TYPE": "aris-fanout-leaf",
    "ARIS_FANOUT_MAX_SHARDS": "8",
    "ARIS_FANOUT_MAX_CONCURRENCY": "4",
    "ARIS_FANOUT_SHARD_MAX_TURNS": "8",
    "ARIS_FANOUT_ALLOW_RECURSION": "false",
    "ARIS_FANOUT_REQUIRE_COVERAGE_RECEIPT": "true",
}
FANOUT_SKILLS = {"idea-creator", "research-lit", "proof-checker"}
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
FORBIDDEN_LEAF_TOOLS = {
    "Agent",
    "Workflow",
    "Skill",
    "SendMessage",
    "Write",
    "Edit",
    "Bash",
    "PowerShell",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_whitespace(text: str) -> str:
    without_blockquotes = re.sub(r"(?m)^\s*>\s?", "", text)
    return re.sub(r"\s+", " ", without_blockquotes).strip()


def frontmatter(text: str) -> str:
    match = re.match(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n", text, re.DOTALL)
    assert match is not None, "expected YAML frontmatter"
    return match.group("frontmatter")


def scalar_field(text: str, name: str) -> str:
    matches = re.findall(
        rf"(?m)^\s*{re.escape(name)}\s*:\s*(?P<value>[^#\n]+?)\s*(?:#.*)?$",
        text,
    )
    assert len(matches) == 1, f"expected exactly one parseable {name!r} field"
    return matches[0].strip().strip("`\"'")


def bounded_contract(text: str) -> dict[str, str]:
    yaml_blocks = re.findall(r"(?ms)^```ya?ml\s*\n(?P<body>.*?)^```\s*$", text)
    candidates = [
        block
        for block in yaml_blocks
        if re.search(r"(?m)^\s*ARIS_FANOUT_AGENT_TYPE\s*:", block)
    ]
    assert len(candidates) == 1, (
        "expected one YAML fenced block containing the bounded fan-out constants"
    )
    return {name: scalar_field(candidates[0], name) for name in EXPECTED_CONTRACT}


def tool_list(frontmatter_text: str) -> set[str]:
    tools = scalar_field(frontmatter_text, "tools")
    return {
        tool.strip().strip("[]`\"'")
        for tool in tools.split(",")
        if tool.strip().strip("[]`\"'")
    }


def agent_grants(skill_text: str) -> list[str]:
    tools_match = re.search(r"(?m)^\s*allowed-tools\s*:\s*(?P<tools>.+)$", frontmatter(skill_text))
    if tools_match is None:
        return []
    tools = [tool.strip() for tool in tools_match.group("tools").split(",")]
    return [tool for tool in tools if tool == "Agent" or tool.startswith("Agent(")]


def assert_skill_uses_bounded_contract(text: str, *, requires_leaf_type: bool) -> None:
    if requires_leaf_type:
        assert EXPECTED_CONTRACT["ARIS_FANOUT_AGENT_TYPE"] in text, (
            "skill must select the bounded leaf type"
        )

    required_limits = {
        "max_shards": EXPECTED_CONTRACT["ARIS_FANOUT_MAX_SHARDS"],
        "max_concurrency": EXPECTED_CONTRACT["ARIS_FANOUT_MAX_CONCURRENCY"],
        "max_turns": EXPECTED_CONTRACT["ARIS_FANOUT_SHARD_MAX_TURNS"],
    }
    for name, expected in required_limits.items():
        assert re.search(
            rf"(?im)\b{re.escape(name)}\b\s*(?:=|:)\s*`?{re.escape(expected)}`?\b",
            text,
        ), f"skill must state {name} = {expected}"

    assert re.search(r"(?i)sequential[-\s]+fallback", text), (
        "skill must document the sequential fallback"
    )
    assert re.search(r"(?i)coverage[-_\s]+receipt", text), (
        "skill must require a coverage receipt"
    )


def test_mainline_and_codex_fanout_references_define_the_same_parseable_bounds() -> None:
    mainline_contract = bounded_contract(read(MAINLINE_FANOUT))
    codex_contract = bounded_contract(read(CODEX_FANOUT))

    assert mainline_contract == EXPECTED_CONTRACT
    assert codex_contract == EXPECTED_CONTRACT


def test_leaf_agent_is_read_only_and_matches_the_shared_turn_cap() -> None:
    assert LEAF_AGENT.is_file(), "bounded fan-out must use a dedicated leaf agent"

    leaf_frontmatter = frontmatter(read(LEAF_AGENT))
    assert scalar_field(leaf_frontmatter, "name") == EXPECTED_CONTRACT["ARIS_FANOUT_AGENT_TYPE"]
    assert scalar_field(leaf_frontmatter, "maxTurns") == EXPECTED_CONTRACT["ARIS_FANOUT_SHARD_MAX_TURNS"]

    tools = tool_list(leaf_frontmatter)
    assert tools, "leaf agent must declare an explicit read-only tools list"
    assert tools <= READ_ONLY_TOOLS, "leaf agent tools must be restricted to read-only inspection"
    assert not tools.intersection(FORBIDDEN_LEAF_TOOLS)


def test_only_the_three_fanout_skills_grant_agent_and_reference_the_leaf_contract() -> None:
    skills_with_agent_grants = {
        skill_file.parent.name
        for skill_file in MAINLINE_SKILLS.glob("*/SKILL.md")
        if agent_grants(read(skill_file))
    }
    assert skills_with_agent_grants == FANOUT_SKILLS

    expected_grant = f"Agent({EXPECTED_CONTRACT['ARIS_FANOUT_AGENT_TYPE']})"
    for skill_name in FANOUT_SKILLS:
        text = read(MAINLINE_SKILLS / skill_name / "SKILL.md")
        assert agent_grants(text) == [expected_grant]
        assert_skill_uses_bounded_contract(text, requires_leaf_type=True)


def test_codex_fanout_skill_mirrors_preserve_the_bounded_dispatch_semantics() -> None:
    for skill_name in FANOUT_SKILLS:
        text = read(CODEX_SKILLS / skill_name / "SKILL.md")
        assert_skill_uses_bounded_contract(text, requires_leaf_type=False)
        assert re.search(r"(?im)\brecursion\b\s*(?:=|:)\s*`?false`?\b", text), (
            f"{skill_name} Codex mirror must request non-recursive delegation"
        )


def test_codex_mirrors_disclose_prompt_only_worker_limits() -> None:
    for skill_name in FANOUT_SKILLS:
        text = read(CODEX_SKILLS / skill_name / "SKILL.md")
        normalized = normalize_whitespace(text).lower()
        assert "Stock Codex enforcement: prompt-only" in text
        assert "per-child tool allowlist" in text
        assert "recursion flag" in text
        assert "child turn-cap parameter" in text
        assert "does not provide the same hard" in normalized
        assert "executor still enforces" in normalized
        assert "unsafe-host action: sequential fallback" not in normalized

    reference = normalize_whitespace(read(CODEX_FANOUT)).lower()
    assert "prompt-only conventions" in reference
    assert "does not provide the same hard" in reference
    assert "parent/executor still enforces" in reference
    assert "if the host cannot guarantee those restrictions" not in reference


def test_research_lit_freezes_leaf_readable_evidence_before_dispatch() -> None:
    for skill_root in (MAINLINE_SKILLS, CODEX_SKILLS):
        text = read(skill_root / "research-lit" / "SKILL.md")
        normalized = normalize_whitespace(text).lower()
        assert ".aris/verify-papers/research-lit-evidence/" in text
        for field in (
            "paper_id",
            "verification_status",
            "abstract",
            "source_excerpt",
            "local_pdf_path",
            "local_note_paths",
            "evidence_status",
        ):
            assert f"`{field}`" in text
        assert "identity fields or remote urls alone are not sufficient" in normalized
        assert "UNPROCESSABLE_NO_LOCAL_EVIDENCE" in text


def test_proof_checker_receipts_cover_source_units_not_discovered_obligations() -> None:
    for skill_root in (MAINLINE_SKILLS, CODEX_SKILLS):
        text = read(skill_root / "proof-checker" / "SKILL.md")
        normalized = normalize_whitespace(text).lower()
        assert "source-unit IDs" in text
        assert "after extraction" in normalized
        assert "source-unit execution coverage only" in normalized
        assert "does not prove that every relevant obligation was discovered" in normalized
        assert "section/theorem/obligation ID" not in text

    for reference_file in (MAINLINE_FANOUT, CODEX_FANOUT):
        text = read(reference_file)
        normalized = normalize_whitespace(text).lower().replace("**", "")
        assert "post-extraction obligation id" in normalized
        assert "discovered obligations are not planned coverage units" in normalized
        assert "pre-existing canonical id assigned upstream, e.g. `mc-17`" not in normalized


def test_fanout_references_match_current_idea_creator_phase_three() -> None:
    for reference_file in (MAINLINE_FANOUT, CODEX_FANOUT):
        text = read(reference_file)
        normalized = normalize_whitespace(text).lower()
        assert "Known gap — idea-creator" not in text
        assert "quick novelty check + feasibility gating" not in text
        assert "phase 3 performs mechanical deduplication" in normalized
        assert "every feasible non-duplicate candidate reaches the phase-4 jury" in normalized
