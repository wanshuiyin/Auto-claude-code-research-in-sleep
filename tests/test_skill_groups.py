#!/usr/bin/env python3
"""Catalog integrity for tools/skill-groups.tsv (#366 selective install).

The catalog is the single source of truth for the selective-install feature
in all four installers. Drift between skills/ and the catalog silently
degrades UX (uncataloged skills fall into the interactive "ungrouped"
bucket), so completeness is enforced here.
"""
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "tools" / "skill-groups.tsv"
SKILLS_DIR = REPO_ROOT / "skills"
# Not skills: support dir + codex mirror trees (mirror reuses mainline names).
NON_SKILL_DIRS = {"shared-references"}


def parse_catalog():
    groups, skills = {}, {}
    for line in CATALOG.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if fields[0] == "group":
            assert len(fields) == 4, f"malformed group record: {line!r}"
            groups[fields[1]] = (fields[2], fields[3])
        elif fields[0] == "skill":
            assert len(fields) == 5, f"malformed skill record (need 5 fields): {line!r}"
            assert fields[4].strip(), f"empty short-description: {fields[1]}"
            assert fields[1] not in skills, f"duplicate skill record: {fields[1]}"
            skills[fields[1]] = (fields[2], fields[3])
        else:
            raise AssertionError(f"unknown record type: {line!r}")
    return groups, skills


def upstream_skills():
    return {
        p.name
        for p in SKILLS_DIR.iterdir()
        if (p / "SKILL.md").is_file()
        and p.name not in NON_SKILL_DIRS
        and not p.name.startswith("skills-codex")
    }


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.groups, self.skills = parse_catalog()

    def test_every_upstream_skill_is_cataloged(self):
        missing = upstream_skills() - set(self.skills)
        self.assertFalse(
            missing,
            f"skills missing from tools/skill-groups.tsv: {sorted(missing)} — "
            "new skills must be assigned to a group",
        )

    def test_no_stale_catalog_entries(self):
        stale = set(self.skills) - upstream_skills()
        self.assertFalse(
            stale, f"catalog lists skills that no longer exist: {sorted(stale)}"
        )

    def test_skill_groups_exist(self):
        for name, (group, _) in self.skills.items():
            self.assertIn(group, self.groups, f"{name}: unknown group '{group}'")

    def test_requires_reference_cataloged_skills(self):
        for name, (_, requires) in self.skills.items():
            if requires == "-":
                continue
            for dep in requires.split(","):
                self.assertIn(
                    dep, self.skills, f"{name}: requires unknown skill '{dep}'"
                )
                self.assertNotEqual(dep, name, f"{name}: requires itself")

    def test_every_group_is_nonempty(self):
        used = {group for group, _ in self.skills.values()}
        empty = set(self.groups) - used
        self.assertFalse(empty, f"groups with no skills: {sorted(empty)}")


if __name__ == "__main__":
    unittest.main()
