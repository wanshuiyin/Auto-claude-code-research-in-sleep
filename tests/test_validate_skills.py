from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "validate_skills.py"


class ValidateSkillsTests(unittest.TestCase):
    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def write_skill(self, root: Path, directory_name: str, content: str) -> None:
        skill_dir = root / directory_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

    def test_repository_skills_validate(self) -> None:
        result = self.run_validator(REPO_ROOT / "skills")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated", result.stdout)

    def test_missing_allowed_tools_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "skills"
            self.write_skill(
                root,
                "demo-skill",
                """
                ---
                name: demo-skill
                description: Demo skill. Use when checking validator behavior.
                ---

                # Demo
                """,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required field 'allowed-tools'", result.stderr)

    def test_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "skills"
            self.write_skill(
                root,
                "demo-skill",
                """
                ---
                name: different-name
                description: Demo skill. Use when checking validator behavior.
                allowed-tools: Read
                ---

                # Demo
                """,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match directory", result.stderr)

    def test_global_mcp_wildcard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "skills"
            self.write_skill(
                root,
                "demo-skill",
                """
                ---
                name: demo-skill
                description: Demo skill. Use when checking validator behavior.
                allowed-tools: Read, mcp__*__*
                ---

                # Demo
                """,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MCP server wildcard is not allowed", result.stderr)


if __name__ == "__main__":
    unittest.main()
