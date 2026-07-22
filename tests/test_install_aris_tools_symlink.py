#!/usr/bin/env python3
"""Regression test for install_aris.sh #174: project-local .aris/tools symlink.

Covers:
  install: fresh project gets `.aris/tools -> <repo>/tools`
  install: idempotent on rerun
  install: warns and leaves alone if `.aris/tools` already exists with
           a different target / as a non-symlink path
  uninstall: removes the managed symlink
  uninstall: preserves non-managed `.aris/tools` (different target / real dir)
  dry-run: prints planned action without writing anything
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris.sh"
LEAF_AGENT_SOURCE = REPO_ROOT / "agents" / "aris-fanout-leaf.md"


@unittest.skipIf(os.name == "nt", "Bash installer lifecycle requires POSIX symlink semantics")
class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aris-174-"))
        self.project = self.tmp / "project"
        self.project.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *extra_args):
        result = subprocess.run(
            [
                "bash",
                str(INSTALL_SCRIPT),
                str(self.project),
                "--aris-repo",
                str(REPO_ROOT),
                "--quiet",
                "--no-doc",
                *extra_args,
            ],
            capture_output=True,
            text=True,
        )
        return result

    # ─── install behaviour ────────────────────────────────────────────────

    def test_install_creates_tools_symlink(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        link = self.project / ".aris" / "tools"
        self.assertTrue(link.is_symlink(), f"expected {link} to be a symlink")
        self.assertEqual(
            os.readlink(link),
            str(REPO_ROOT / "tools"),
            "managed symlink must point to the canonical aris-repo tools dir",
        )

    def test_install_dry_run_does_not_create_symlink(self):
        # Run without --quiet so log() output reaches stdout for assertion
        result = subprocess.run(
            [
                "bash",
                str(INSTALL_SCRIPT),
                str(self.project),
                "--aris-repo",
                str(REPO_ROOT),
                "--no-doc",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        link = self.project / ".aris" / "tools"
        self.assertFalse(link.exists(), "dry-run must not create the symlink")
        self.assertIn(".aris/tools", result.stdout, "dry-run output must mention .aris/tools")

    def test_install_is_idempotent(self):
        # Run twice; second run should be a no-op for the tools symlink
        self._run()
        result = self._run()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        link = self.project / ".aris" / "tools"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(REPO_ROOT / "tools"))

    def test_install_does_not_replace_existing_dir(self):
        # User already has a real .aris/tools dir; installer must leave it alone
        (self.project / ".aris").mkdir()
        existing_dir = self.project / ".aris" / "tools"
        existing_dir.mkdir()
        marker = existing_dir / "user_file.txt"
        marker.write_text("user content")

        result = self._run()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse((self.project / ".aris" / "tools").is_symlink())
        self.assertTrue(marker.exists(), "user-created content must be preserved")
        self.assertEqual(marker.read_text(), "user content")

    def test_install_does_not_replace_different_symlink(self):
        # User already has .aris/tools pointing somewhere else
        (self.project / ".aris").mkdir()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        os.symlink(str(elsewhere), str(self.project / ".aris" / "tools"))

        result = self._run()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            os.readlink(self.project / ".aris" / "tools"),
            str(elsewhere),
            "non-managed symlink must be preserved",
        )

    def test_install_leaf_agent_is_idempotent_symlink(self):
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"

        first = self._run()
        second = self._run()

        self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)
        self.assertTrue(target.is_symlink(), "POSIX installer must match skill symlink mode")
        self.assertEqual(Path(os.readlink(target)), LEAF_AGENT_SOURCE)

    def test_install_leaf_agent_preserves_conflict(self):
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        target.parent.mkdir(parents=True)
        user_content = "---\nname: aris-fanout-leaf\n---\nuser-owned\n"
        target.write_text(user_content, encoding="utf-8")

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFLICT", result.stdout + result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), user_content)
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())
        self.assertFalse((self.project / ".claude" / "skills" / "idea-creator").exists())

    def test_uninstall_preserves_preexisting_matching_leaf_symlink(self):
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(LEAF_AGENT_SOURCE)

        install = self._run()
        self.assertEqual(install.returncode, 0, msg=install.stdout + install.stderr)
        self.assertFalse((self.project / ".aris" / "installed-agents.txt").exists())

        result = self._run("--uninstall")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(target)), LEAF_AGENT_SOURCE)

    def test_uninstall_preserves_foreign_leaf_symlink(self):
        install = self._run()
        self.assertEqual(install.returncode, 0, msg=install.stdout + install.stderr)
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        target.unlink()
        foreign_source = self.tmp / "foreign-agent.md"
        foreign_source.write_text("foreign\n", encoding="utf-8")
        target.symlink_to(foreign_source)

        result = self._run("--uninstall")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(target)), foreign_source)

    def test_uninstall_preserves_leaf_under_linked_agents_parent(self):
        install = self._run()
        self.assertEqual(install.returncode, 0, msg=install.stdout + install.stderr)
        agents_dir = self.project / ".claude" / "agents"
        target = agents_dir / "aris-fanout-leaf.md"
        target.unlink()
        agents_dir.rmdir()
        external_agents = self.tmp / "external-agents"
        external_agents.mkdir()
        external_target = external_agents / "aris-fanout-leaf.md"
        external_target.symlink_to(LEAF_AGENT_SOURCE)
        agents_dir.symlink_to(external_agents, target_is_directory=True)

        result = self._run("--uninstall")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(external_target.is_symlink())
        self.assertEqual(Path(os.readlink(external_target)), LEAF_AGENT_SOURCE)

    # ─── uninstall behaviour ──────────────────────────────────────────────

    def test_uninstall_removes_managed_symlink(self):
        self._run()  # install
        self.assertTrue((self.project / ".aris" / "tools").is_symlink())
        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse(
            (self.project / ".aris" / "tools").exists(),
            "uninstall must remove the managed symlink",
        )
        self.assertFalse(
            (self.project / ".claude" / "agents" / "aris-fanout-leaf.md").exists(),
            "uninstall must remove the managed POSIX leaf symlink",
        )

    def test_uninstall_preserves_non_managed_dir(self):
        # First install, then replace tools symlink with a user dir, then uninstall
        self._run()
        link = self.project / ".aris" / "tools"
        link.unlink()
        link.mkdir()
        marker = link / "preserved.txt"
        marker.write_text("preserved")

        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(link.is_dir(), "user-created dir must be preserved by uninstall")
        self.assertEqual(marker.read_text(), "preserved")

    def test_uninstall_preserves_non_managed_symlink(self):
        # Install creates managed symlink, user replaces with custom symlink, uninstall must skip
        self._run()
        link = self.project / ".aris" / "tools"
        link.unlink()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        os.symlink(str(elsewhere), str(link))

        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(link.is_symlink(), "user-created symlink must be preserved")
        self.assertEqual(os.readlink(link), str(elsewhere))


if __name__ == "__main__":
    unittest.main()
