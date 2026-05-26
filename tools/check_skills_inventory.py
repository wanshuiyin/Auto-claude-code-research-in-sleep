#!/usr/bin/env python3
"""Check ARIS skill inventory drift across mainline, Codex mirror, and docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
CODEX_ROOT = SKILLS_ROOT / "skills-codex"
CATALOG = REPO_ROOT / "docs" / "SKILLS_CATALOG.md"
README = REPO_ROOT / "README.md"
README_CN = REPO_ROOT / "README_CN.md"
AGENT_GUIDE = REPO_ROOT / "AGENT_GUIDE.md"
ARIS_INTRO = REPO_ROOT / "docs" / "ARIS_INTRO.md"
ARIS_INTRO_HTML = REPO_ROOT / "docs" / "ARIS_INTRO.html"
CODEX_README = CODEX_ROOT / "README.md"
CODEX_README_CN = CODEX_ROOT / "README_CN.md"
BOM = b"\xef\xbb\xbf"

FORBIDDEN_CODEX_REVIEWER_STRINGS = (
    "mcp__codex__codex",
    "codex-reply",
    "reviewer-continuation",
    "threadId",
)

# Phase A (issue #240): cross-language anchor IDs that MUST exist as
# explicit `<a id="..."></a>` in both README.md and README_CN.md so that
# cross-language hyperlinks resolve identically. Adding a new numbered
# section means adding it to both READMEs AND extending this list.
REQUIRED_README_ANCHORS = (
    "contents",
    "more-than-just-a-prompt",
    "whats-new",
    "quick-start",
    "features",
    "score-progression",
    "community-showcase",
    "awesome-community-skills",
    "workflows",
    "skills-catalog",
    "setup",
    "customization",
    "alternative-model-combinations",
    "community",
    "citation",
    "star-history",
    "acknowledgements",
    "license",
    "prerequisites",
    "install-skills",
    "gpu-server-setup",
    "alt-a-glm--gpt",
    "-optional-gpt-54-pro-via-oracle",
    "-research-wiki--persistent-research-memory",
)


def skill_names(root: Path) -> set[str]:
    return {path.parent.name for path in root.glob("*/SKILL.md")}


def readme_anchors(text: str) -> set[str]:
    return set(re.findall(r'<a id="([^"]+)"></a>', text))


def numbered_h2_count(text: str) -> int:
    return len(re.findall(r"^## \d+\.\s", text, flags=re.MULTILINE))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def catalog_names() -> set[str]:
    text = read(CATALOG)
    return set(re.findall(r"\[`/([^`]+)`\]\(\.\./skills/[^)]+/SKILL\.md\)", text))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def require_count(path: Path, text: str, pattern: str, expected_count: int, failures: list[str]) -> None:
    match = re.search(pattern, text)
    rel = path.relative_to(REPO_ROOT)
    if match is None:
        failures.append(f"{rel} is missing live count pattern: {pattern}")
        return
    actual = int(match.group("count"))
    if actual != expected_count:
        failures.append(f"{rel} reports {actual} skills; expected {expected_count}")


def check_inventory() -> list[str]:
    failures: list[str] = []
    main = skill_names(SKILLS_ROOT)
    codex = skill_names(CODEX_ROOT)
    catalog = catalog_names()

    missing_codex = sorted(main - codex)
    extra_codex = sorted(codex - main)
    missing_catalog = sorted(main - catalog)
    extra_catalog = sorted(catalog - main)

    require(not missing_codex, f"missing Codex mirrors: {', '.join(missing_codex)}", failures)
    require(not extra_codex, f"unexpected Codex-only skills: {', '.join(extra_codex)}", failures)
    require(not missing_catalog, f"missing catalog entries: {', '.join(missing_catalog)}", failures)
    require(not extra_catalog, f"catalog entries without mainline skills: {', '.join(extra_catalog)}", failures)

    catalog_text = read(CATALOG)
    readme = read(README)
    readme_cn = read(README_CN)
    agent_guide = read(AGENT_GUIDE)
    aris_intro = read(ARIS_INTRO)
    aris_intro_html = read(ARIS_INTRO_HTML)
    codex_readme = read(CODEX_README)
    codex_readme_cn = read(CODEX_README_CN)

    expected_count = len(main)
    count_checks = [
        (CATALOG, catalog_text, r"\*\*(?P<count>\d+) skills\*\*"),
        (README, readme, r"📊\s+\*\*(?P<count>\d+) composable skills\*\*"),
        (README, readme, r"ARIS ships \*\*(?P<count>\d+)\+ skills\*\*"),
        (README_CN, readme_cn, r"📊\s+\*\*(?P<count>\d+) 个可组合 skill\*\*"),
        (README_CN, readme_cn, r"ARIS 现有 \*\*(?P<count>\d+)\+ 个 skill\*\*"),
        (AGENT_GUIDE, agent_guide, r"Full catalog.*?\*\*(?P<count>\d+) skills\*\*"),
        (ARIS_INTRO, aris_intro, r"collection of \*\*(?P<count>\d+) composable Claude Code skills\*\*"),
        (ARIS_INTRO, aris_intro, r"## The (?P<count>\d+) Skills"),
        (ARIS_INTRO, aris_intro, r"一组 (?P<count>\d+) 个可组合的 Claude Code skills"),
        (ARIS_INTRO_HTML, aris_intro_html, r"collection of <strong>(?P<count>\d+) composable Claude Code skills</strong>"),
        (ARIS_INTRO_HTML, aris_intro_html, r'id="the-(?P<count>\d+)-skills"'),
        (ARIS_INTRO_HTML, aris_intro_html, r"一组 (?P<count>\d+) 个可组合的 Claude Code skills"),
        (CODEX_README, codex_readme, r"all `(?P<count>\d+)` mainline skills"),
        (CODEX_README_CN, codex_readme_cn, r"`(?P<count>\d+)`[^\n]*skill"),
    ]
    for path, text, pattern in count_checks:
        require_count(path, text, pattern, expected_count, failures)

    for skill_file in sorted(CODEX_ROOT.glob("*/SKILL.md")):
        if skill_file.read_bytes().startswith(BOM):
            failures.append(f"{skill_file.relative_to(REPO_ROOT)} starts with UTF-8 BOM before frontmatter")
        text = read(skill_file)
        for forbidden in FORBIDDEN_CODEX_REVIEWER_STRINGS:
            if forbidden in text:
                failures.append(f"{skill_file.relative_to(REPO_ROOT)} contains forbidden reviewer string: {forbidden}")

    # README parity (EN ↔ CN) — Phase A invariant from #240
    en_anchors = readme_anchors(readme)
    cn_anchors = readme_anchors(readme_cn)
    for required in REQUIRED_README_ANCHORS:
        if required not in en_anchors:
            failures.append(f"README.md missing required anchor: <a id=\"{required}\"></a>")
        if required not in cn_anchors:
            failures.append(f"README_CN.md missing required anchor: <a id=\"{required}\"></a>")

    en_h2 = numbered_h2_count(readme)
    cn_h2 = numbered_h2_count(readme_cn)
    require(en_h2 == 17, f"README.md has {en_h2} numbered H2 sections; expected 17 (Phase A)", failures)
    require(cn_h2 == 17, f"README_CN.md has {cn_h2} numbered H2 sections; expected 17 (Phase A)", failures)

    return failures


def main() -> int:
    failures = check_inventory()
    if failures:
        print("ARIS skill inventory drift detected:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("ARIS skill inventory is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
