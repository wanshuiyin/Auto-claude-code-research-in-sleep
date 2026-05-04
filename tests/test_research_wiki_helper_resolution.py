#!/usr/bin/env python3
"""Regression test for the research-wiki helper resolution chain.

Covers the bug that left a real user's research-wiki/ empty for a week:
caller skills hard-coded `python3 tools/research_wiki.py`, which silently
fails when <project>/tools/ is not on disk (the post-install_aris.sh
default — install_aris.sh creates .aris/tools symlink, not tools/).

The fix is a 3-layer resolution chain documented in
skills/shared-references/wiki-helper-resolution.md. This test runs the
chain in three concrete scenarios and asserts the helper is reachable
in each.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "tools" / "research_wiki.py"

# The shared resolution chain, copied verbatim from
# skills/shared-references/wiki-helper-resolution.md so this test fails
# when the prose drifts.
#
# Note: no `set -eu` here. Real SKILL bash blocks do not enable strict
# mode, and `set -e` would actually make the chain BROKEN: bash's
# `${X:-$(awk ...)}` substitution propagates the awk exit code to
# `set -e` even when wrapped in `2>/dev/null`, and awk exits 2 when
# its input file is missing — which is the common case (no manifest
# yet). The chain is set-eu-unsafe by design; running it without
# strict mode is the documented contract.
RESOLUTION_CHAIN = r'''
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
WIKI_SCRIPT=".aris/tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || WIKI_SCRIPT="tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
[ -f "$WIKI_SCRIPT" ] || exit 42
printf '%s\n' "$WIKI_SCRIPT"
python3 "$WIKI_SCRIPT" init research-wiki || exit 1
test -f research-wiki/query_pack.md || exit 1
test -f research-wiki/log.md || exit 1
test -f research-wiki/graph/edges.jsonl || exit 1
'''


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=path, check=True,
    )


def _run_chain(cwd: Path, env_overrides: dict | None = None):
    env = os.environ.copy()
    env.pop("ARIS_REPO", None)
    if env_overrides:
        env.update(env_overrides)
    # Use `bash -c` (not `-lc`); SKILL bash blocks execute in non-login
    # shells and `bash -l` triggers reading of the user's profile, which
    # may exit non-zero under `set -eu` on dev machines (it does on
    # macOS with miniforge in PATH) and would mask the chain's real
    # exit code.
    return subprocess.run(
        ["bash", "-c", RESOLUTION_CHAIN],
        cwd=cwd, env=env, text=True, capture_output=True,
    )


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aris-wiki-chain-"))
        self.project = self.tmp / "project"
        self.project.mkdir()
        _git_init(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Layer 1: .aris/tools/ symlink (post-install_aris.sh default)
    # ------------------------------------------------------------------
    def test_layer1_symlink(self):
        """Helper at .aris/tools/research_wiki.py -> <repo>/tools/."""
        (self.project / ".aris").mkdir()
        (self.project / ".aris" / "tools").symlink_to(REPO_ROOT / "tools")

        result = _run_chain(self.project)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[0],
            ".aris/tools/research_wiki.py",
        )
        self.assertTrue((self.project / "research-wiki" / "query_pack.md").exists())

    # ------------------------------------------------------------------
    # Layer 2: tools/research_wiki.py (manual-copy workaround — preserves
    # the temporary fix a real user is currently using)
    # ------------------------------------------------------------------
    def test_layer2_manual_copy(self):
        """User manually copied helper to <project>/tools/research_wiki.py."""
        (self.project / "tools").mkdir()
        shutil.copy(HELPER, self.project / "tools" / "research_wiki.py")

        result = _run_chain(self.project)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[0],
            "tools/research_wiki.py",
        )
        self.assertTrue((self.project / "research-wiki" / "query_pack.md").exists())

    def test_layer2_manual_copy_from_subdir(self):
        """Manual copy + user invokes from a git-subdir cwd (paper/, etc.).

        Verifies the `cd "$(git rev-parse --show-toplevel)"` preamble.
        """
        (self.project / "tools").mkdir()
        shutil.copy(HELPER, self.project / "tools" / "research_wiki.py")
        (self.project / "paper").mkdir()

        result = _run_chain(self.project / "paper")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[0],
            "tools/research_wiki.py",
        )
        # research-wiki/ should be created at project root, not in paper/
        self.assertTrue((self.project / "research-wiki" / "query_pack.md").exists())
        self.assertFalse((self.project / "paper" / "research-wiki").exists())

    # ------------------------------------------------------------------
    # Layer 3a: $ARIS_REPO env var
    # ------------------------------------------------------------------
    def test_layer3_aris_repo_env(self):
        """ARIS_REPO env var points at the repo; no .aris/tools, no tools/."""
        result = _run_chain(
            self.project,
            env_overrides={"ARIS_REPO": str(REPO_ROOT)},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[0],
            f"{REPO_ROOT}/tools/research_wiki.py",
        )
        self.assertTrue((self.project / "research-wiki" / "query_pack.md").exists())

    # ------------------------------------------------------------------
    # Layer 3b: ARIS_REPO auto-resolved from install manifest
    # ------------------------------------------------------------------
    def test_layer3_manifest_repo_root(self):
        """ARIS_REPO unset; install manifest contains repo_root field."""
        (self.project / ".aris").mkdir()
        manifest = self.project / ".aris" / "installed-skills.txt"
        manifest.write_text(f"repo_root\t{REPO_ROOT}\n")

        result = _run_chain(self.project)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[0],
            f"{REPO_ROOT}/tools/research_wiki.py",
        )

    # ------------------------------------------------------------------
    # Helper-missing case: chain exits 42 (test harness sentinel)
    # ------------------------------------------------------------------
    def test_helper_missing(self):
        """No symlink, no tools/, no ARIS_REPO, no manifest → chain fails."""
        result = _run_chain(self.project)
        self.assertEqual(
            result.returncode, 42,
            msg="chain should fail explicitly when no helper found "
                f"(stdout={result.stdout!r} stderr={result.stderr!r})",
        )

    # ------------------------------------------------------------------
    # Static gate: no CC-side SKILL still hard-codes the path
    # ------------------------------------------------------------------
    def test_no_hardcoded_invocations(self):
        """Regression: no CC-side SKILL.md should run `python3 tools/research_wiki.py`."""
        skills_dir = REPO_ROOT / "skills"
        offenders = []
        for path in skills_dir.rglob("SKILL.md"):
            # Skip Codex mirror — it has its own resolution chain.
            if "skills-codex" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                # Allow `tools/research_wiki.py` in non-bash prose
                # (the chain itself, doc explanations, etc.) by requiring
                # a shell-invocation prefix.
                stripped = line.strip()
                if stripped.startswith("python3 tools/research_wiki.py"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
                if stripped.startswith("[ -n \"$WIKI_SCRIPT\" ] && python3 tools/research_wiki.py"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
        self.assertEqual(
            offenders, [],
            msg="CC-side SKILL.md still hard-codes 'python3 tools/research_wiki.py' "
                "instead of using `python3 \"$WIKI_SCRIPT\"` after the resolution "
                "chain. See skills/shared-references/wiki-helper-resolution.md.\n"
                + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
