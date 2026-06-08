from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_SKILLS = REPO_ROOT / "skills"


def read_skill(name: str) -> str:
    return (MAIN_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def test_mainline_large_payload_skills_prefer_path_only_codex_prompts() -> None:
    checks = {
        "idea-creator": [
            "idea-stage/codex_brainstorm_bundle.md",
            "Read the idea-generation bundle at <absolute path",
            "idea-stage/codex_triage_bundle.md",
        ],
        "research-review": [
            "RESEARCH_REVIEW_REQUEST.md",
            "Read the review brief at <absolute path",
            "RESEARCH_REVIEW_ROUND_2.md",
            "Read the updated review brief at <absolute path",
        ],
        "research-refine": [
            "refine-logs/codex_round_1_review_bundle.md",
            "Read the review bundle at <absolute path",
            "refine-logs/codex_round_N_review_bundle.md",
            "Read the re-evaluation bundle at <absolute path",
        ],
        "grant-proposal": [
            "grant-proposal/codex_panel_review_bundle_round_1.md",
            "Read the grant review bundle at <absolute path",
            "grant-proposal/codex_panel_review_bundle_round_N.md",
        ],
        "novelty-check": [
            "NOVELTY_DOSSIER.md",
            "Read the novelty dossier at <absolute path",
        ],
    }

    for skill, needles in checks.items():
        text = read_skill(skill)
        for needle in needles:
            assert needle in text, f"{skill}: missing path-only prompt guidance: {needle}"


def test_mainline_large_payload_skills_remove_inline_paste_placeholders() -> None:
    forbidden = {
        "idea-creator": [
            "[paste landscape map from Phase 1]",
            "[paste gaps from Phase 1]",
            "[paste all candidates with their prior_work / so_what / effort_note notes]",
        ],
        "research-review": [
            "[Full research context + specific questions]",
        ],
        "research-refine": [
            "[Paste the FULL proposal from Phase 1]",
            "[Paste the FULL revised proposal]",
        ],
        "grant-proposal": [
            "[PASTE FULL PROPOSAL TEXT]",
        ],
    }

    for skill, needles in forbidden.items():
        text = read_skill(skill)
        for needle in needles:
            assert needle not in text, f"{skill}: still contains inline large-payload placeholder: {needle}"
