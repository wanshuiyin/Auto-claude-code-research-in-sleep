#!/usr/bin/env python3
"""Regression test for install_aris.sh #431: Copilot reviewer profiles.

The profiles under <aris-repo>/.github/agents/ serve only auto-review-loop's
Copilot backend, and .github/ is the user's namespace. So:
  - they are deployed only while auto-review-loop is installed
  - --no-agent-profiles switches them off and is remembered in .aris/
  - --agent-profiles undoes that
  - a re-run cleans up links this installer created earlier when the
    condition no longer holds (migration for installs made before #431),
    never touching files it did not create
  - dry-run writes nothing, including the remembered choice
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris.sh"
PROFILE = "aris-reviewer-openai.agent.md"


class AgentProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aris-431-"))
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.agents_dir = self.project / ".github" / "agents"
        self.link = self.agents_dir / PROFILE
        self.ownership = self.project / ".aris" / "installed-agent-profiles.txt"
        self.opt_out = self.project / ".aris" / "agent-profiles-opt-out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *extra_args):
        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT), str(self.project), "--aris-repo", str(REPO_ROOT),
             "--quiet", "--no-doc", *extra_args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result

    def test_not_deployed_without_auto_review_loop(self):
        self._run("--skills", "paper-write")
        self.assertFalse(self.agents_dir.exists())
        self.assertFalse(self.ownership.exists())

    def test_deployed_with_auto_review_loop(self):
        self._run("--skills", "auto-review-loop")
        self.assertTrue(self.link.is_symlink())
        self.assertEqual(os.readlink(self.link), str(REPO_ROOT / ".github" / "agents" / PROFILE))
        self.assertIn(PROFILE, self.ownership.read_text().splitlines())

    def test_opt_out_is_remembered_and_reversible(self):
        self._run("--skills", "auto-review-loop")
        self.assertTrue(self.link.is_symlink())

        self._run("--no-agent-profiles")
        self.assertFalse(self.link.is_symlink())
        self.assertTrue(self.opt_out.exists())

        self._run()  # plain reconcile must not bring them back
        self.assertFalse(self.link.is_symlink())

        self._run("--agent-profiles")
        self.assertTrue(self.link.is_symlink())
        self.assertFalse(self.opt_out.exists())

    def test_rerun_cleans_up_links_from_before_431(self):
        self._run("--skills", "paper-write")
        # what the pre-#431 installer left behind: our links + ownership record
        self.agents_dir.mkdir(parents=True)
        os.symlink(str(REPO_ROOT / ".github" / "agents" / PROFILE), str(self.link))
        self.ownership.write_text(PROFILE + "\n")
        # and a file the user wrote themselves
        mine = self.agents_dir / "my-own.agent.md"
        mine.write_text("---\nmodel: whatever\n---\n")

        self._run()
        self.assertFalse(self.link.is_symlink())
        self.assertFalse(self.ownership.exists())
        self.assertTrue(mine.is_file())

    def test_dry_run_writes_nothing(self):
        self._run("--skills", "auto-review-loop")
        self._run("--dry-run", "--no-agent-profiles")
        self.assertTrue(self.link.is_symlink())
        self.assertTrue(self.ownership.exists())
        self.assertFalse(self.opt_out.exists())


if __name__ == "__main__":
    unittest.main()
