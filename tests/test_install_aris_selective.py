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
