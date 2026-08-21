# Integration guards for the proof-orchestrator skill and its Codex mirror.

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN = REPO_ROOT / "skills"
CODEX = MAIN / "skills-codex"

PROOF_SUITE = {"proof-orchestrator"}
REMOVED_CHECKER = "proof-checker" + "-v2"
INTERNALIZED_REFERENCES = {
    "proof-audit-rubric.md",
    "deepseek-routing.md",
    "audit-output-contract.md",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_proof_suite_is_mirrored() -> None:
    for name in PROOF_SUITE:
        assert (MAIN / name / "SKILL.md").is_file()
        assert (CODEX / name / "SKILL.md").is_file()


def test_retired_checker_is_not_shipped() -> None:
    assert not (MAIN / REMOVED_CHECKER).exists()
    assert not (CODEX / REMOVED_CHECKER).exists()


def test_existing_paper_workflows_keep_the_original_proof_checker() -> None:
    for name in ("paper-writing", "auto-paper-improvement-loop", "resubmit-pipeline"):
        text = read(MAIN / name / "SKILL.md")
        assert "/proof-checker" in text
        assert REMOVED_CHECKER not in text


def test_optional_deepseek_audit_is_internalized() -> None:
    for root in (MAIN, CODEX):
        skill_root = root / "proof-orchestrator"
        skill = read(skill_root / "SKILL.md")
        assert "user explicitly requests DeepSeek review" in skill
        assert "Existing paper workflows continue to use ARIS's canonical `/proof-checker`" in skill
        assert "Optional DeepSeek Audit" in skill
        for reference in INTERNALIZED_REFERENCES:
            assert (skill_root / "references" / reference).is_file()

        routing = read(skill_root / "references" / "deepseek-routing.md")
        output = read(skill_root / "references" / "audit-output-contract.md")
        assert "mcp__llm_chat__chat" in routing
        assert '"audit_skill": "proof-orchestrator"' in output
        assert '"audit_mode": "deepseek-second-opinion"' in output


def test_proof_suite_uses_aris_reviewer_routing() -> None:
    forbidden = ("deepseek-agent", "opencode", "CODEX_HOME", ".codex/skills")
    for root in (MAIN, CODEX):
        combined = "\n".join(
            read(path)
            for name in PROOF_SUITE
            for path in (root / name).rglob("*.md")
        )
        assert not any(term in combined for term in forbidden)
