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
CODEX_README = CODEX_ROOT / "README.md"
CODEX_README_CN = CODEX_ROOT / "README_CN.md"

FORBIDDEN_CODEX_REVIEWER_STRINGS = (
    "mcp__codex__codex",
    "codex-reply",
)


def skill_names(root: Path) -> set[str]:
    return {path.parent.name for path in root.glob("*/SKILL.md")}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def catalog_names() -> set[str]:
    text = read(CATALOG)
    return set(re.findall(r"\[`/([^`]+)`\]\(\.\./skills/[^)]+/SKILL\.md\)", text))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


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
    codex_readme = read(CODEX_README)
    codex_readme_cn = read(CODEX_README_CN)
    codex_readme_cn_count = re.search(r"`(?P<count>\d+)`[^\n]*skill", codex_readme_cn)

    expected_count = len(main)
    require(
        f"**{expected_count} skills**" in catalog_text,
        f"{CATALOG.relative_to(REPO_ROOT)} does not report {expected_count} skills",
        failures,
    )
    require(
        f"all `{expected_count}` mainline skills" in codex_readme,
        f"{CODEX_README.relative_to(REPO_ROOT)} does not report {expected_count} mainline skills",
        failures,
    )
    require(
        codex_readme_cn_count is not None and int(codex_readme_cn_count.group("count")) == expected_count,
        f"{CODEX_README_CN.relative_to(REPO_ROOT)} does not report {expected_count} mainline skills",
        failures,
    )

    for skill_file in sorted(CODEX_ROOT.glob("*/SKILL.md")):
        text = read(skill_file)
        for forbidden in FORBIDDEN_CODEX_REVIEWER_STRINGS:
            if forbidden in text:
                failures.append(f"{skill_file.relative_to(REPO_ROOT)} contains forbidden reviewer string: {forbidden}")

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
