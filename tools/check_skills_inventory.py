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


def allowed_tools(text: str) -> list[str]:
    """Tokens on the frontmatter `allowed-tools:` line (empty if absent)."""
    match = re.search(r"^allowed-tools:\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return []
    return [tok.strip() for tok in match.group(1).split(",") if tok.strip()]


def frontmatter_split(text: str) -> str:
    """Return the body after a leading YAML frontmatter block (whole text if
    no frontmatter). Anchors on the opening `---` fence and the first closing
    `---` fence, so `---` horizontal rules later in the body are not mistaken
    for the frontmatter boundary."""
    match = re.match(r"^---\n.*?\n---\n", text, flags=re.DOTALL)
    return text[match.end():] if match else text


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
    require(en_h2 == 16, f"README.md has {en_h2} numbered H2 sections; expected 16 (Phase A)", failures)
    require(cn_h2 == 16, f"README_CN.md has {cn_h2} numbered H2 sections; expected 16 (Phase A)", failures)

    # Agent-grant hygiene (WB2): `Agent` in allowed-tools is the Tier-2
    # fan-out capability gate. Per shared-references/fan-out-pattern.md it is
    # granted ONLY to skills that actually fan out, and such skills MUST cite
    # the convention doc in their body. A grant without that citation is a
    # vestigial/boilerplate grant and fails the drift check.
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        text = read(skill_file)
        if "Agent" not in allowed_tools(text):
            continue
        if "fan-out-pattern.md" not in frontmatter_split(text):
            rel = skill_file.relative_to(REPO_ROOT)
            failures.append(
                f"{rel} grants `Agent` in allowed-tools but its body does not "
                f"cite fan-out-pattern.md — vestigial grant or undocumented "
                f"fan-out (see shared-references/fan-out-pattern.md)"
            )

    # Watchdog 'loop' task type ⇔ its documented trigger (A2). Mirrors the Agent-grant⇒cite
    # rule above: a feature with no documented trigger is dead weight, a documented trigger
    # for a missing feature is a broken pointer. The loop type is a shipped feature, so BOTH
    # must be present.
    watchdog_py = read(REPO_ROOT / "tools" / "watchdog.py")
    ext_cadence = read(SKILLS_ROOT / "shared-references" / "external-cadence.md")
    tool_loop = bool(re.search(r"def check_loop\b", watchdog_py)) and bool(re.search(r'==\s*"loop"', watchdog_py))
    doc_loop = bool(re.search(r'"type"\s*:\s*"loop"', ext_cadence))
    require(tool_loop, "tools/watchdog.py must implement the loop-liveness check_loop (A2)", failures)
    require(doc_loop, "external-cadence.md must document registering a watchdog 'loop' task — its trigger (A2)", failures)

    # iteration_log.py (stall→pivot, B) must exist AND be both documented (the ladder with
    # both thresholds) and actually wired into a heartbeat consumer — else it is dead code.
    # Same dead-code guard as the Agent-grant⇒cite rule above.
    extc = read(SKILLS_ROOT / "shared-references" / "external-cadence.md")
    rp = read(SKILLS_ROOT / "research-pipeline" / "SKILL.md")
    tool_stall = (REPO_ROOT / "tools" / "iteration_log.py").is_file()
    doc_ladder = bool(re.search(r"forced structural pivot", extc, re.IGNORECASE)) and \
        bool(re.search(r"stale_count`?\s*>=\s*2", extc)) and bool(re.search(r"stale_count`?\s*>=\s*4", extc))
    # Prove the wiring is real (not a prose mention): resolver chain + note invocation +
    # both pivot branches handled in research-pipeline.
    wired = ('iteration_log.py' in rp and 'ITER_LOG' in rp
             and re.search(r'"\$ITER_LOG"\s+note', rp) is not None
             and 'pivot' in rp and 'structural' in rp and 'human' in rp)
    require(tool_stall, "tools/iteration_log.py (stall→pivot, B) must exist", failures)
    require(doc_ladder, "external-cadence.md must document the stall ladder with both thresholds (>=2 structural, >=4 human) (B)", failures)
    require(wired, "research-pipeline/SKILL.md must actually wire iteration_log.py (resolver + `$ITER_LOG note` + pivot handling) — not just mention it (B)", failures)

    # research_wiki.py add_claim (claim layer) ⇔ its documented birth trigger in
    # /proof-checker. add_claim is a writer; without a skill that calls it, the claim
    # layer is dead code (the exact orphan-writer trap). Same dead-code guard as above:
    # the writer and its single birth point must BOTH be present.
    rwiki = read(REPO_ROOT / "tools" / "research_wiki.py")
    pchk = read(SKILLS_ROOT / "proof-checker" / "SKILL.md")
    tool_claim = bool(re.search(r"def add_claim\b", rwiki)) and bool(re.search(r'add_parser\("add_claim"', rwiki))
    # Prove the trigger is real (anchored to the actual command line, not a prose
    # mention or comment): proof-checker must literally invoke the resolved helper.
    born = re.search(r'python3\s+"\$WIKI_SCRIPT"\s+add_claim\b', pchk) is not None
    require(tool_claim, "tools/research_wiki.py must implement the add_claim claim-layer writer + its CLI", failures)
    require(born, "proof-checker/SKILL.md must invoke `add_claim` as the claim birth point — not just mention it (else add_claim is an orphan writer)", failures)

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
