from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_SKILLS = REPO_ROOT / "skills"
CODEX_SKILLS = REPO_ROOT / "skills" / "skills-codex"
CLAUDE_OVERLAY = REPO_ROOT / "skills" / "skills-codex-claude-review"
GEMINI_OVERLAY = REPO_ROOT / "skills" / "skills-codex-gemini-review"


def skill_names(root: Path) -> set[str]:
    return {path.parent.name for path in root.glob("*/SKILL.md")}


def read(path: Path) -> str:
    return path.read_text()


def has_spawn_agent_block(text: str) -> bool:
    return re.search(r"(?m)^\s*spawn_agent:", text) is not None


def has_send_input_block(text: str) -> bool:
    return re.search(r"(?m)^\s*send_input:", text) is not None


def test_codex_skill_set_matches_mainline() -> None:
    main_names = skill_names(MAIN_SKILLS)
    codex_names = skill_names(CODEX_SKILLS)
    assert len(main_names) == 67
    assert main_names == codex_names


def test_codex_reviewer_contract_partition() -> None:
    codex_names = skill_names(CODEX_SKILLS)
    single_round: set[str] = set()
    multi_round: set[str] = set()
    non_reviewer: set[str] = set()

    for name in codex_names:
        text = read(CODEX_SKILLS / name / "SKILL.md")
        spawn = has_spawn_agent_block(text)
        send = has_send_input_block(text)
        if spawn and send:
            multi_round.add(name)
        elif spawn:
            single_round.add(name)
        else:
            non_reviewer.add(name)

    assert multi_round
    assert single_round
    assert non_reviewer
    assert single_round.isdisjoint(multi_round)
    assert (single_round | multi_round | non_reviewer) == codex_names

    for name in multi_round:
        text = read(CODEX_SKILLS / name / "SKILL.md")
        assert has_spawn_agent_block(text)
        assert has_send_input_block(text)
        assert re.search(r"(?m)^\s*(target|id|agent_id):\s*\[saved", text) is not None
        assert "saved" in text or "same reviewer" in text or "same agent" in text

    for name in non_reviewer:
        text = read(CODEX_SKILLS / name / "SKILL.md")
        assert not has_spawn_agent_block(text)
        assert not has_send_input_block(text)


def test_overlay_boundaries_are_exact() -> None:
    expected_claude = {
        "auto-paper-improvement-loop",
        "auto-review-loop",
        "novelty-check",
        "paper-figure",
        "paper-plan",
        "paper-write",
        "research-refine",
        "research-review",
    }
    expected_gemini = {
        "auto-paper-improvement-loop",
        "auto-review-loop",
        "grant-proposal",
        "idea-creator",
        "idea-discovery",
        "idea-discovery-robot",
        "novelty-check",
        "paper-figure",
        "paper-plan",
        "paper-poster",
        "paper-slides",
        "paper-write",
        "paper-writing",
        "research-refine",
        "research-review",
    }
    assert skill_names(CLAUDE_OVERLAY) == expected_claude
    assert skill_names(GEMINI_OVERLAY) == expected_gemini


def test_non_degrading_skill_rules_are_documented() -> None:
    checks = {
        "comm-lit-review": "Do not silently downgrade",
        "research-lit": "stop and ask the user to configure",
        "paper-poster": "Do not silently degrade",
        "pixel-art": "Do not silently downgrade",
    }
    for name, needle in checks.items():
        text = read(CODEX_SKILLS / name / "SKILL.md")
        assert needle in text


def test_codex_skill_helper_commands_use_installed_aris_repo() -> None:
    bad_command_patterns = [
        r"python3 tools/",
        r"python tools/",
        r"bash tools/",
        r"sh tools/",
        r"find tools/",
        r"relative to the current project",
        r"relative to the project root",
    ]
    allowed_bundled_mentions = {
        "experiment-queue",
    }
    allowed_claude_style_fallbacks = {
        "alphaxiv",
        "arxiv",
        "deepxiv",
        "exa-search",
        "figure-spec",
        "research-lit",
        "research-wiki",
        "semantic-scholar",
    }

    failures: list[str] = []
    for skill_file in CODEX_SKILLS.glob("*/SKILL.md"):
        skill_name = skill_file.parent.name
        if skill_name in allowed_bundled_mentions or skill_name in allowed_claude_style_fallbacks:
            continue
        text = read(skill_file)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(re.search(pattern, line) for pattern in bad_command_patterns):
                failures.append(f"{skill_file.relative_to(REPO_ROOT)}:{line_no}: {line}")

    assert not failures, "Codex skills must not assume helper scripts exist in the user project:\n" + "\n".join(failures)


def test_codex_shared_reference_links_exist() -> None:
    failures: list[str] = []
    pattern = re.compile(r"\.\./shared-references/([A-Za-z0-9._-]+\.md)")

    for skill_file in CODEX_SKILLS.glob("*/SKILL.md"):
        text = read(skill_file)
        for ref_name in pattern.findall(text):
            if not (CODEX_SKILLS / "shared-references" / ref_name).exists():
                failures.append(f"{skill_file.relative_to(REPO_ROOT)} -> shared-references/{ref_name}")

    assert not failures, "Codex skill shared-reference links must resolve inside skills-codex:\n" + "\n".join(failures)


def test_codex_high_risk_skills_preserve_claude_semantics() -> None:
    required_terms = {
        "auto-review-loop": [
            "REVIEWER_DIFFICULTY",
            "Reviewer Memory",
            "Debate Protocol",
            "nightmare",
            "Review Tracing",
            "oracle-pro",
            "Phase B.5",
            "Phase B.6",
            "Debate Transcript",
        ],
        "research-pipeline": [
            "REVIEWER_DIFFICULTY",
            "Reviewer Memory",
            "Debate Protocol",
            "nightmare",
            "Review Tracing",
            "AUTO_WRITE",
            "NARRATIVE_REPORT.md",
            "experiment-queue",
            "Stage 6: Paper Writing",
        ],
        "experiment-bridge": [
            "Vast.ai",
            "Modal",
            "rescue",
            "second opinion",
            "CODE_REVIEW",
            "Cross-Model Code Review",
        ],
        "run-experiment": [
            "Vast.ai",
            "Modal",
            "hourly cost",
            "rescue",
        ],
        "monitor-experiment": [
            "Vast.ai",
            "Modal",
            "W&B dashboard links",
            "cost",
        ],
        "research-review": [
            "Review Tracing",
            "oracle-pro",
        ],
        "research-lit": [
            "semantic-scholar",
            "Semantic Scholar API search",
            "semantic_scholar_fetch.py",
        ],
        "arxiv": [
            "Update Research Wiki",
            "integration-contract.md",
            "export ARIS_REPO",
        ],
        "rebuttal": [
            "Review Tracing",
            "oracle-pro",
        ],
    }

    failures: list[str] = []
    for skill, terms in required_terms.items():
        text = read(CODEX_SKILLS / skill / "SKILL.md")
        for term in terms:
            if term not in text:
                failures.append(f"{skill}: missing {term}")

    assert not failures, "High-risk Codex skills must preserve Claude semantics:\n" + "\n".join(failures)


def test_codex_medium_risk_skills_preserve_claude_semantics() -> None:
    required_terms = {
        "idea-creator": [
            "Load Research Wiki",
            "query_pack.md",
            "Write Ideas to Research Wiki",
            "review-tracing.md",
        ],
        "idea-discovery": [
            "Load Research Brief",
            "RESEARCH_BRIEF.md",
            "Research Brief",
        ],
        "paper-writing": [
            "Architecture & Illustration Generation",
            "Submission pre-flight checklist",
            "Invoking the three audits",
            "Running the verifier",
            "Optional hardening",
            "assurance-contract.md",
        ],
        "deepxiv": [
            "Semantic Scholar",
            "integration-contract.md",
        ],
        "comm-lit-review": [
            "Source Selection",
            "Retrieval Order",
            "Graceful degradation rules",
            "IEEE Xplore",
            "ScienceDirect",
            "ACM Digital Library",
        ],
        "mermaid-diagram": [
            "Score Breakdown Guide",
            "CRITICAL - any failure = score <= 6",
            "any failure = score <= 7",
        ],
    }

    failures: list[str] = []
    for skill, terms in required_terms.items():
        text = read(CODEX_SKILLS / skill / "SKILL.md")
        for term in terms:
            if term not in text:
                failures.append(f"{skill}: missing {term}")

    assert not failures, "Medium-risk Codex skills must preserve Claude semantics:\n" + "\n".join(failures)


def test_codex_optional_helpers_are_guarded() -> None:
    checks = {
        "research-lit": [
            'if [ -n "$DEEPXIV_SCRIPT" ]; then',
            '[ -n "$EXA_SCRIPT" ] && python3 "$EXA_SCRIPT"',
            'echo "DeepXiv unavailable',
            'echo "Exa unavailable',
        ],
        "deepxiv": [
            '[ -n "$SCRIPT" ] && python3 "$SCRIPT"',
            "fall back to raw `deepxiv` commands",
        ],
    }
    for skill, needles in checks.items():
        text = read(CODEX_SKILLS / skill / "SKILL.md")
        for needle in needles:
            assert needle in text


def test_codex_training_check_defaults_to_interactive_watch() -> None:
    text = read(CODEX_SKILLS / "training-check" / "SKILL.md")
    assert "interactive watch" in text
    assert "交互式训练监控模式" in text
    assert "every 30 minutes" in text
    assert "current terminal" in text
    assert "If the context contains `stop_command`, run `stop_command` first." in text
    assert "Optional Background Mode" not in text
    assert "codex-training-check" not in text
    assert "codex_training_check.py" not in text
    assert "CronCreate" not in text
    assert "tmux loop" not in text
    assert "codex exec" not in text


def test_codex_skill_instructions_use_codex_paths() -> None:
    auto_paper = read(CODEX_SKILLS / "auto-paper-improvement-loop" / "SKILL.md")
    paper_writing = read(CODEX_SKILLS / "paper-writing" / "SKILL.md")
    figure_spec = read(CODEX_SKILLS / "figure-spec" / "SKILL.md")
    meta_optimize = read(CODEX_SKILLS / "meta-optimize" / "SKILL.md")

    assert "~/.codex/feishu.json" in auto_paper
    assert "~/.claude/feishu.json" not in auto_paper
    assert ".aris/installed-skills-codex.txt" in paper_writing
    assert ".agents/skills/paper-writing" in paper_writing
    assert "~/.claude/skills/paper-writing/SKILL.md" not in paper_writing
    assert "~/.claude/settings.json" not in paper_writing
    assert 'python3 "$FIGURE_RENDERER"' in figure_spec
    assert '[ -n "$FIGURE_RENDERER" ] ||' in figure_spec
    assert "figure_renderer.py not found" in figure_spec
    assert "Codex-compatible event logger" in meta_optimize
    assert ".claude/settings.json" not in meta_optimize
    assert "templates/claude-hooks/meta_logging.json" not in meta_optimize


def test_codex_experiment_queue_points_to_bundled_helpers() -> None:
    text = read(CODEX_SKILLS / "experiment-queue" / "SKILL.md")

    assert "tools/experiment_queue/queue_manager.py" in text
    assert "tools/experiment_queue/build_manifest.py" in text
    assert "tools/queue_manager.py" not in text
    assert "tools/build_manifest.py" not in text
    assert ".aris/installed-skills-codex.txt" in text
