from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    REPO_ROOT / "skills" / "web-debug-search" / "SKILL.md",
    REPO_ROOT / "skills" / "skills-codex" / "web-debug-search" / "SKILL.md",
)


def test_web_debug_search_mirrors_are_present_and_triggerable() -> None:
    texts = [path.read_text(encoding="utf-8") for path in SKILLS]
    for text in texts:
        assert "name: web-debug-search" in text
        assert "WebSearch" in text and "WebFetch" in text
        assert "GitHub Issues" in text and "Discussions" in text


def test_web_debug_search_preserves_match_and_version_boundaries() -> None:
    text = SKILLS[0].read_text(encoding="utf-8")
    for marker in ("[EXACT]", "[NORMALIZED]", "[COMPATIBILITY]", "[CONTEXTUAL]"):
        assert marker in text
    assert "compatibility table" in text
    assert "Do not invent a" in text


def test_web_debug_search_is_discovery_only() -> None:
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        assert "not paper-citation evidence" in text
        assert "must not be added" in text
        assert "Evidence boundary" in text


def test_web_debug_search_documents_failure_paths() -> None:
    text = SKILLS[0].read_text(encoding="utf-8")
    for marker in (
        "BLOCKED: web search unavailable",
        "no exact match",
        "unverified",
        "unavailable",
        "unresolved",
    ):
        assert marker in text
