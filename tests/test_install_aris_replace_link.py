#!/usr/bin/env python3
"""Regression test for install_aris.sh --replace-link.

The original implementation rewrote CONFLICT plan rows with
`sed "s|^CONFLICT|$n|UPDATE_TARGET|$n|"`, which is doubly broken: `|` is both
the sed delimiter and the plan-field separator (so sed errors out, silenced by
`2>/dev/null || true`), and the pattern matched the name against field 2 (kind)
instead of field 3 (name). Net effect: --replace-link never converted anything
and the installer aborted telling the user to pass the flag they already passed.

The fix converts via awk with a string compare on field 3, restricted to
symlink conflicts (`$4 ~ /^symlink_to:/`), and strips the `symlink_to:` prefix
so the converted row passes the apply step's S11 revalidation (which compares
field 4 against the symlink's canonicalized current target).

Covers:
  conflict without --replace-link            -> abort (exit 1), conflict reported
  conflict with    --replace-link NAME       -> exit 0, symlink re-pointed to expected target
  real-path conflict with --replace-link     -> still aborts (only symlink conflicts convert)
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris.sh"

# Two real skills from the live repo: the conflict symlink points CONFLICT_NAME
# at WRONG_TARGET_NAME's directory (inside aris-repo, so S2 allows replacement).
CONFLICT_NAME = "arxiv"
WRONG_TARGET_NAME = "deepxiv"


class ReplaceLinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aris-replace-link-"))
        self.project = self.tmp / "project"
        self.skills_dir = self.project / ".claude" / "skills"
        self.skills_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *extra_args, quiet=True):
        # --quiet silences log() entirely (by design), so tests asserting on the
        # abort MESSAGE run without it; the conflict abort happens at plan stage,
        # before any interactive prompt, and stdin is closed anyway.
        args = ["--no-doc"] + (["--quiet"] if quiet else [])
        return subprocess.run(
            [
                "bash",
                str(INSTALL_SCRIPT),
                str(self.project),
                "--aris-repo",
                str(REPO_ROOT),
                *args,
                *extra_args,
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )

    def _make_foreign_symlink(self):
        link = self.skills_dir / CONFLICT_NAME
        os.symlink(str(REPO_ROOT / "skills" / WRONG_TARGET_NAME), link)
        return link

    def test_conflict_without_replace_link_aborts(self):
        link = self._make_foreign_symlink()
        result = self._run(quiet=False)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("--replace-link", combined,
                      "abort message must point the user at --replace-link")
        self.assertIn(CONFLICT_NAME, combined,
                      "conflict report must name the conflicting entry")
        self.assertEqual(
            os.readlink(link),
            str(REPO_ROOT / "skills" / WRONG_TARGET_NAME),
            "aborted install must not touch the conflicting symlink",
        )

    def test_replace_link_converts_symlink_conflict_and_applies(self):
        link = self._make_foreign_symlink()
        result = self._run("--replace-link", CONFLICT_NAME)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(link.is_symlink(), "entry must still be a symlink after replacement")
        self.assertEqual(
            os.readlink(link),
            str(REPO_ROOT / "skills" / CONFLICT_NAME),
            "--replace-link must re-point the symlink to the expected upstream target",
        )
        manifest = self.project / ".aris" / "installed-skills.txt"
        self.assertTrue(manifest.is_file(), "successful install must write the manifest")
        self.assertIn(CONFLICT_NAME, manifest.read_text(),
                      "replaced entry must be recorded as managed")

    def test_replace_link_ignores_real_path_conflict(self):
        real_dir = self.skills_dir / CONFLICT_NAME
        real_dir.mkdir()
        (real_dir / "SKILL.md").write_text("user-owned skill, not a symlink\n")
        result = self._run("--replace-link", CONFLICT_NAME)
        self.assertEqual(
            result.returncode, 1,
            msg="real-path conflicts must NOT be converted by --replace-link:\n"
            + result.stdout + result.stderr,
        )
        self.assertTrue(real_dir.is_dir() and not real_dir.is_symlink(),
                        "user-owned real directory must be left untouched")
        self.assertTrue((real_dir / "SKILL.md").is_file(),
                        "user-owned file must survive the aborted install")


if __name__ == "__main__":
    unittest.main()
