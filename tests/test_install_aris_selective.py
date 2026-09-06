#!/usr/bin/env python3
"""Selective install / new-skill confirmation for install_aris.sh (#366).

Covers:
  fresh:      --quiet with no selection flags installs everything (legacy)
  fresh:      --skills subset installs the subset + catalog `requires` deps,
              records unselected skills in .aris/skills-declined.txt
  fresh:      --groups installs a whole group; unknown names die
  fresh:      an excluded hard dep is NOT auto-included (warning instead)
  reconcile:  new upstream skill — --skip-new skips without declining,
              --add-new installs, a declined skill is never re-added
  reconcile:  --exclude removes an installed skill and declines it,
              --skills re-enables a declined skill
  flags:      --all conflicts with --groups/--skills; --list-groups prints
  pointer:    $HOME/.aris/repo is written on successful install

All runs use a synthetic aris-repo fixture and an overridden $HOME so the
real global pointer is never touched.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris.sh"

CATALOG = """\
group\tg1\tGroup One\tfirst group
group\tg2\tGroup Two\tsecond group
skill\talpha\tg1\t-
skill\tbeta\tg1\talpha
skill\tgamma\tg1\t-
skill\tdelta\tg2\t-
"""


@unittest.skipIf(os.name == "nt", "Bash selective installer tests require POSIX symlinks")
class SelectiveInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aris-358-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.tmp / "arisrepo"
        (self.repo / "tools").mkdir(parents=True)
        for name in ("alpha", "beta", "gamma", "delta"):
            self._add_upstream_skill(name)
        (self.repo / "skills" / "shared-references").mkdir()
        (self.repo / "skills" / "shared-references" / "ref.md").write_text("ref\n")
        (self.repo / "tools" / "skill-groups.tsv").write_text(CATALOG)
        self.project = self.tmp / "project"
        (self.project / ".claude").mkdir(parents=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add_upstream_skill(self, name):
        d = self.repo / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {name}\n")

    def _add_fanout_skill(self, name):
        self._add_upstream_skill(name)
        catalog = self.repo / "tools" / "skill-groups.tsv"
        existing = catalog.read_text(encoding="utf-8")
        catalog.write_text(existing + f"skill\t{name}\tg1\t-\n", encoding="utf-8")
        source = self.repo / "agents" / "aris-fanout-leaf.md"
        source.parent.mkdir(exist_ok=True)
        if not source.exists():
            source.write_text("---\nname: aris-fanout-leaf\n---\n", encoding="utf-8")
        return source

    def _run(self, *extra_args, check=True):
        result = subprocess.run(
            [
                "bash",
                str(INSTALL_SCRIPT),
                str(self.project),
                "--aris-repo",
                str(self.repo),
                "--quiet",
                "--no-doc",
                *extra_args,
            ],
            capture_output=True,
            text=True,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
        if check:
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        return result

    def _installed(self):
        skills = self.project / ".claude" / "skills"
        if not skills.is_dir():
            return set()
        return {p.name for p in skills.iterdir()} - {"shared-references"}

    def _declined(self):
        f = self.project / ".aris" / "skills-declined.txt"
        if not f.is_file():
            return set()
        return set(f.read_text().split())

    # ─── fresh install ─────────────────────────────────────────────────────

    def test_quiet_fresh_install_defaults_to_all(self):
        self._run()
        self.assertEqual(self._installed(), {"alpha", "beta", "gamma", "delta"})
        self.assertEqual(self._declined(), set())

    def test_skills_subset_pulls_deps_and_declines_rest(self):
        self._run("--skills", "beta")
        # beta requires alpha (catalog), so alpha is auto-included
        self.assertEqual(self._installed(), {"alpha", "beta"})
        self.assertEqual(self._declined(), {"gamma", "delta"})

    def test_groups_selection(self):
        self._run("--groups", "g2")
        self.assertEqual(self._installed(), {"delta"})
        self.assertEqual(self._declined(), {"alpha", "beta", "gamma"})

    def test_excluded_dep_is_not_auto_included(self):
        result = self._run("--skills", "beta", "--exclude", "alpha")
        self.assertEqual(self._installed(), {"beta"})
        self.assertIn("requires 'alpha'", result.stdout + result.stderr)
        self.assertIn("alpha", self._declined())

    def test_unknown_group_dies(self):
        result = self._run("--groups", "nope", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown group", result.stderr)

    def test_unknown_skill_dies(self):
        result = self._run("--skills", "nope", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown skill", result.stderr)

    # ─── reconcile: new upstream skills ────────────────────────────────────

    def test_new_skill_skipped_quietly_not_declined(self):
        self._run("--skills", "alpha")
        self._add_upstream_skill("epsilon")
        result = self._run("--skip-new")
        self.assertNotIn("epsilon", self._installed())
        self.assertNotIn("epsilon", self._declined())
        # skipped-new must stay visible even under --quiet (goes to stderr)
        self.assertIn("epsilon", result.stderr)

    def test_new_skill_added_with_add_new(self):
        self._run("--skills", "alpha")
        self._add_upstream_skill("epsilon")
        self._run("--add-new")
        self.assertIn("epsilon", self._installed())

    def test_declined_skill_never_re_added(self):
        self._run("--skills", "alpha")  # declines beta/gamma/delta
        self._run("--add-new")
        self.assertEqual(self._installed(), {"alpha"})

    # ─── reconcile: exclude / re-enable ────────────────────────────────────

    def test_exclude_removes_and_declines(self):
        self._run()
        self._run("--exclude", "gamma")
        self.assertNotIn("gamma", self._installed())
        self.assertIn("gamma", self._declined())

    def test_skills_flag_re_enables_declined(self):
        self._run("--skills", "alpha")
        self.assertIn("gamma", self._declined())
        self._run("--skills", "gamma")
        self.assertIn("gamma", self._installed())
        self.assertNotIn("gamma", self._declined())

    # ─── flags & pointer ───────────────────────────────────────────────────

    def test_all_conflicts_with_selection_flags(self):
        result = self._run("--all", "--skills", "alpha", check=False)
        self.assertEqual(result.returncode, 2)

    def test_list_groups_prints_catalog(self):
        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT), str(self.project), "--aris-repo",
             str(self.repo), "--list-groups"],
            capture_output=True,
            text=True,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Group One", result.stdout)
        self.assertIn("delta", result.stdout)

    def test_global_pointer_written(self):
        self._run()
        pointer = self.home / ".aris" / "repo"
        self.assertTrue(pointer.is_file(), "installer must write ~/.aris/repo")
        self.assertEqual(pointer.read_text().strip(), str(self.repo))

    def test_dry_run_writes_nothing(self):
        self._run("--dry-run")
        self.assertEqual(self._installed(), set())
        self.assertFalse((self.home / ".aris" / "repo").exists())
        self.assertFalse((self.project / ".aris" / "skills-declined.txt").exists())

    # ─── bounded fan-out leaf selection ─────────────────────────────────────

    def test_non_fanout_selection_preserves_leaf_target_conflict(self):
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        target.parent.mkdir(parents=True)
        target.write_text("user-owned\n", encoding="utf-8")

        self._run("--skills", "alpha")

        self.assertEqual(target.read_text(encoding="utf-8"), "user-owned\n")
        self.assertEqual(self._installed(), {"alpha"})

    def test_non_fanout_selection_ignores_available_fanout_leaf_paths(self):
        self._add_upstream_skill("idea-creator")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(CATALOG + "skill\tidea-creator\tg1\t-\n", encoding="utf-8")
        agents_dir = self.project / ".claude" / "agents"
        linked_agents = self.tmp / "linked-agents"
        linked_agents.mkdir()
        user_leaf = linked_agents / "aris-fanout-leaf.md"
        user_leaf.write_text("user-owned\n", encoding="utf-8")
        agents_dir.symlink_to(linked_agents, target_is_directory=True)

        self._run("--skills", "alpha")

        self.assertTrue(agents_dir.is_symlink())
        self.assertEqual(user_leaf.read_text(encoding="utf-8"), "user-owned\n")
        self.assertEqual(self._installed(), {"alpha"})

    def test_fanout_selection_requires_leaf_source_before_mutation(self):
        self._add_upstream_skill("idea-creator")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(CATALOG + "skill\tidea-creator\tg1\t-\n", encoding="utf-8")

        result = self._run("--skills", "idea-creator", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bounded fan-out leaf agent not found", result.stderr)
        self.assertFalse((self.project / ".claude" / "skills" / "idea-creator").exists())
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())

    def test_fanout_selection_installs_leaf_symlink(self):
        self._add_upstream_skill("idea-creator")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(CATALOG + "skill\tidea-creator\tg1\t-\n", encoding="utf-8")
        source = self.repo / "agents" / "aris-fanout-leaf.md"
        source.parent.mkdir()
        source.write_text("---\nname: aris-fanout-leaf\n---\n", encoding="utf-8")

        self._run("--skills", "idea-creator")

        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.resolve(), source.resolve())

    def test_fanout_selection_rejects_linked_agents_parent_before_install(self):
        self._add_upstream_skill("idea-creator")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(CATALOG + "skill\tidea-creator\tg1\t-\n", encoding="utf-8")
        source = self.repo / "agents" / "aris-fanout-leaf.md"
        source.parent.mkdir()
        source.write_text("---\nname: aris-fanout-leaf\n---\n", encoding="utf-8")
        agents_dir = self.project / ".claude" / "agents"
        linked_agents = self.tmp / "linked-agents"
        linked_agents.mkdir()
        agents_dir.symlink_to(linked_agents, target_is_directory=True)

        result = self._run("--skills", "idea-creator", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to install the bounded fan-out leaf", result.stderr)
        self.assertFalse((self.project / ".claude" / "skills" / "idea-creator").exists())
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())
        self.assertFalse((self.project / ".aris" / "tools").exists())
        self.assertFalse((linked_agents / "aris-fanout-leaf.md").exists())

    def test_fanout_install_records_leaf_ownership(self):
        source = self._add_fanout_skill("idea-creator")

        self._run("--skills", "idea-creator")

        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        ownership = self.project / ".aris" / "installed-agents.txt"
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.resolve(), source.resolve())
        self.assertTrue(ownership.is_file())
        ownership_text = ownership.read_text(encoding="utf-8").replace("\\", "/")
        self.assertIn("agents/aris-fanout-leaf.md", ownership_text)
        self.assertIn(".claude/agents/aris-fanout-leaf.md", ownership_text)

    def test_reconcile_removes_owned_leaf_after_last_fanout_skill(self):
        self._add_fanout_skill("idea-creator")
        self._add_fanout_skill("research-lit")
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        ownership = self.project / ".aris" / "installed-agents.txt"

        self._run("--skills", "idea-creator,research-lit")
        self._run("--exclude", "idea-creator")

        self.assertTrue(target.is_symlink())
        self.assertTrue(ownership.is_file())
        self.assertEqual(self._installed(), {"research-lit"})

        self._run("--skills", "alpha", "--exclude", "research-lit")

        self.assertFalse(target.exists())
        self.assertFalse(target.is_symlink())
        self.assertFalse(ownership.exists())
        self.assertEqual(self._installed(), {"alpha"})

    def test_skill_apply_failure_rolls_back_new_owned_leaf(self):
        self._add_fanout_skill("idea-creator")
        skills_path = self.project / ".claude" / "skills"
        skills_path.write_text("user-owned\n", encoding="utf-8")

        result = self._run("--skills", "idea-creator", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skills_path.read_text(encoding="utf-8"), "user-owned\n")
        self.assertFalse((self.project / ".claude" / "agents" / "aris-fanout-leaf.md").exists())
        self.assertFalse((self.project / ".aris" / "installed-agents.txt").exists())
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())
        self.assertEqual(list((self.project / ".aris").glob("installed-skills.txt.tmp.*")), [])

    def test_failed_reconcile_restores_existing_agent_ownership_record(self):
        self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        ownership = self.project / ".aris" / "installed-agents.txt"
        original_ownership = ownership.read_bytes()
        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        target.unlink()
        skills_dir = self.project / ".claude" / "skills"
        for child in skills_dir.iterdir():
            child.unlink()
        skills_dir.rmdir()
        skills_dir.write_text("user-owned\n", encoding="utf-8")

        result = self._run(check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(ownership.read_bytes(), original_ownership)
        self.assertFalse(target.exists())

    def test_agent_ownership_accepts_same_project_through_path_alias(self):
        self._add_fanout_skill("idea-creator")
        project_alias = self.tmp / "project-alias"
        project_alias.symlink_to(self.project, target_is_directory=True)
        self._run("--skills", "idea-creator")

        original_project = self.project
        self.project = project_alias
        try:
            self._run("--skills", "idea-creator")
        finally:
            self.project = original_project

        target = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        self.assertTrue(target.is_symlink())
        self.assertTrue((self.project / ".aris" / "installed-agents.txt").is_file())

    def test_repo_alias_reconcile_reuses_existing_fanout_links(self):
        self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        skill = self.project / ".claude" / "skills" / "idea-creator"
        leaf = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        tools = self.project / ".aris" / "tools"
        original_targets = (skill.readlink(), leaf.readlink(), tools.readlink())
        original_inodes = (skill.lstat().st_ino, leaf.lstat().st_ino, tools.lstat().st_ino)
        repo_alias = self.tmp / "repo-alias"
        repo_alias.symlink_to(self.repo, target_is_directory=True)

        original_repo = self.repo
        self.repo = repo_alias
        try:
            self._run("--reconcile", "--skills", "idea-creator")
        finally:
            self.repo = original_repo

        self.assertEqual((skill.readlink(), leaf.readlink(), tools.readlink()), original_targets)
        self.assertEqual(
            (skill.lstat().st_ino, leaf.lstat().st_ino, tools.lstat().st_ino),
            original_inodes,
        )
        self.assertTrue((self.project / ".aris" / "installed-agents.txt").is_file())

    def test_repo_alias_direct_uninstall_removes_managed_links(self):
        self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        repo_alias = self.tmp / "repo-alias"
        repo_alias.symlink_to(self.repo, target_is_directory=True)

        original_repo = self.repo
        self.repo = repo_alias
        try:
            self._run("--uninstall")
        finally:
            self.repo = original_repo

        self.assertFalse((self.project / ".claude" / "skills" / "idea-creator").exists())
        self.assertFalse((self.project / ".claude" / "agents" / "aris-fanout-leaf.md").exists())
        self.assertFalse((self.project / ".aris" / "tools").exists())
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())
        self.assertFalse((self.project / ".aris" / "installed-agents.txt").exists())
        self.assertTrue((self.project / ".aris" / "installed-skills.txt.prev").is_file())

    def test_uninstall_removes_owned_leaf_with_missing_source(self):
        source = self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        leaf = self.project / ".claude" / "agents" / "aris-fanout-leaf.md"
        source.unlink()
        self.assertTrue(leaf.is_symlink())
        self.assertFalse(leaf.exists())

        self._run("--uninstall")

        self.assertFalse(leaf.is_symlink())
        self.assertFalse((self.project / ".aris" / "installed-agents.txt").exists())

    def test_reconcile_removes_owned_dangling_skill_link(self):
        self._run("--skills", "alpha,beta")
        skill = self.project / ".claude" / "skills" / "alpha"
        (self.repo / "skills" / "alpha" / "SKILL.md").unlink()
        (self.repo / "skills" / "alpha").rmdir()
        self.assertTrue(skill.is_symlink())
        self.assertFalse(skill.exists())

        self._run("--reconcile")

        self.assertFalse(skill.is_symlink())
        manifest = (self.project / ".aris" / "installed-skills.txt").read_text(encoding="utf-8")
        self.assertNotIn("\talpha\t", manifest)

    def test_agent_ownership_missing_project_root_reports_conflict(self):
        self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        ownership = self.project / ".aris" / "installed-agents.txt"
        missing_project = self.tmp / "missing-project"
        lines = ownership.read_text(encoding="utf-8").splitlines()
        ownership.write_text(
            "\n".join(
                f"project_root\t{missing_project}"
                if line.startswith("project_root\t")
                else line
                for line in lines
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run("--skills", "idea-creator", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("belongs to a different project", result.stderr)

    def test_agent_ownership_manifest_cannot_be_copied_between_projects(self):
        self._add_fanout_skill("idea-creator")
        self._run("--skills", "idea-creator")
        source_ownership = self.project / ".aris" / "installed-agents.txt"
        second_project = self.tmp / "second-project"
        (second_project / ".aris").mkdir(parents=True)
        copied_ownership = second_project / ".aris" / "installed-agents.txt"
        copied_ownership.write_bytes(source_ownership.read_bytes())
        second_target = second_project / ".claude" / "agents" / "aris-fanout-leaf.md"
        second_target.parent.mkdir(parents=True)
        second_target.symlink_to(self.repo / "agents" / "aris-fanout-leaf.md")
        original_project = self.project
        self.project = second_project
        try:
            result = self._run("--skills", "alpha", check=False)
        finally:
            self.project = original_project

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(second_target.is_symlink())
        self.assertFalse((second_project / ".aris" / "installed-skills.txt").exists())

    def test_from_old_handles_real_skill_named_aris(self):
        self._add_upstream_skill("aris")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(
            catalog.read_text(encoding="utf-8") + "skill\taris\tg1\t-\n",
            encoding="utf-8",
        )
        legacy = self.project / ".claude" / "skills" / "aris"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(self.repo / "skills", target_is_directory=True)

        self._run("--from-old", "--skills", "aris")

        self.assertTrue(legacy.is_symlink())
        self.assertEqual(legacy.resolve(), (self.repo / "skills" / "aris").resolve())
        self.assertEqual(self._installed(), {"aris"})

    def test_from_old_real_aris_dry_run_is_nonmutating(self):
        self._add_upstream_skill("aris")
        catalog = self.repo / "tools" / "skill-groups.tsv"
        catalog.write_text(
            catalog.read_text(encoding="utf-8") + "skill\taris\tg1\t-\n",
            encoding="utf-8",
        )
        legacy = self.project / ".claude" / "skills" / "aris"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(self.repo / "skills", target_is_directory=True)

        result = self._run("--from-old", "--skills", "aris", "--dry-run", check=False)

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(legacy.is_symlink())
        self.assertEqual(legacy.resolve(), (self.repo / "skills").resolve())
        self.assertFalse((self.project / ".aris" / "installed-skills.txt").exists())

    # ─── interactive menu (needs a pty via expect) ─────────────────────────

    @unittest.skipUnless(
        Path("/usr/bin/expect").exists(), "expect not available for pty test"
    )
    def test_interactive_group_menu_edit_mode(self):
        """Fresh TTY install, no selection flags → per-group Y/n/e menu.

        ARIS_NO_PICKER=1 forces the classic prompts (the default interactive
        UI is the curses checkbox picker, covered by test_skill_picker.py).
        Group g1: 'e' (edit) then keep alpha, drop beta, keep gamma.
        Group g2: 'n' (skip whole group).
        """
        script = self.tmp / "menu.exp"
        script.write_text(
            "set timeout 30\n"
            "set env(ARIS_NO_PICKER) 1\n"
            f"spawn bash {INSTALL_SCRIPT} {self.project} "
            f"--aris-repo {self.repo} --no-doc\n"
            'expect "Install group \'g1\'*\\[Y/n/e\\]" { send "e\\r" }\n'
            'expect "install alpha*\\[Y/n\\]" { send "\\r" }\n'
            'expect "install beta*\\[Y/n\\]" { send "n\\r" }\n'
            'expect "install gamma*\\[Y/n\\]" { send "\\r" }\n'
            'expect "Install group \'g2\'*\\[Y/n/e\\]" { send "n\\r" }\n'
            'expect "Apply these*changes?" { send "y\\r" }\n'
            "expect eof\n"
        )
        result = subprocess.run(
            ["/usr/bin/expect", str(script)],
            capture_output=True,
            text=True,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(self._installed(), {"alpha", "gamma"})
        self.assertEqual(self._declined(), {"beta", "delta"})


if __name__ == "__main__":
    unittest.main()
