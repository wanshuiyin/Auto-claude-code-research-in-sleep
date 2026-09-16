"""The artifact-grounded review path must be able to open its artifacts.

`auto-review-loop` and `research-review` stopped pasting evidence into the
reviewer prompt and now hand over artifact paths ("read the files yourself").
The claude-review bridge, meanwhile, runs Claude with `--tools ""` by default,
which is correct for the prompt-only reviews it was built for but leaves an
artifact-grounded reviewer with no tool to open what the prompt points at — it
answers from the executor's framing, the one thing artifact-grounded review
exists to prevent.

The fix is per-call, not a new global default: blocks that pass paths opt into
read-only tools, prompt-only blocks stay tool-free. These tests pin both halves.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from tools.generate_codex_claude_review_overrides import (
    ARTIFACT_REVIEW_TOOLS,
    REVIEW_CALL_BLOCK_RE,
    TOOLS_KEY_RE,
    is_artifact_grounded,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = REPO_ROOT / "skills" / "skills-codex-claude-review"
SERVER_PATH = REPO_ROOT / "mcp-servers" / "claude-review" / "server.py"

SPEC = importlib.util.spec_from_file_location("claude_review_server", SERVER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# Which overlay skills hand the reviewer artifact paths, and how many review
# calls in each do so. A base-skill edit that adds or removes artifact-grounded
# review prompts should land here deliberately, not silently.
EXPECTED_ARTIFACT_BLOCKS = {
    "auto-review-loop": 2,      # round-1 artifact review + round-2 changed-files reply
    "research-review": 1,       # "Revised files:" follow-up round
}

# Read-only means read-only: a reviewer never edits the work it reviews.
WRITE_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "Task")


def _review_blocks() -> list[tuple[str, str]]:
    """Every claude-review call block in the overlay, as (skill, block)."""
    blocks = []
    for skill_file in sorted(OVERLAY.rglob("SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        for match in REVIEW_CALL_BLOCK_RE.finditer(text):
            blocks.append((skill_file.parent.name, match.group(0)))
    return blocks


class OverlayOptInTests(unittest.TestCase):
    def test_overlay_has_review_blocks_to_check(self) -> None:
        """Guard against a regex/layout change silently emptying every case below."""
        self.assertGreater(len(_review_blocks()), 5)

    def test_tools_opt_in_tracks_artifact_grounded_prompts(self) -> None:
        for skill, block in _review_blocks():
            header = block.splitlines()[1]
            with self.subTest(skill=skill, header=header, prompt=block[:200]):
                self.assertEqual(
                    bool(TOOLS_KEY_RE.search(block)),
                    is_artifact_grounded(block),
                    "a review block must request tools exactly when its prompt "
                    "hands the reviewer artifact paths",
                )

    def test_opt_in_blocks_request_the_readonly_preset(self) -> None:
        for skill, block in _review_blocks():
            if not TOOLS_KEY_RE.search(block):
                continue
            with self.subTest(skill=skill):
                self.assertIn(f'tools: "{ARTIFACT_REVIEW_TOOLS}"', block)

    def test_expected_skills_opt_in(self) -> None:
        counts: dict[str, int] = {}
        for skill, block in _review_blocks():
            if TOOLS_KEY_RE.search(block):
                counts[skill] = counts.get(skill, 0) + 1
        self.assertEqual(
            counts,
            EXPECTED_ARTIFACT_BLOCKS,
            "artifact-grounded review blocks changed; regenerate the overlay "
            "(python tools/generate_codex_claude_review_overrides.py) and update "
            "EXPECTED_ARTIFACT_BLOCKS if the change is intended",
        )


class ReadOnlyPresetTests(unittest.TestCase):
    def test_preset_is_readonly(self) -> None:
        granted = ARTIFACT_REVIEW_TOOLS.split(",")
        self.assertEqual(granted, ["Read", "Grep", "Glob"])
        for tool in WRITE_TOOLS:
            self.assertNotIn(tool, granted)


class BridgeDefaultTests(unittest.TestCase):
    """The bridge default must not move: prompt-only reviews stay tool-free."""

    def _cmd(self, **kwargs) -> list[str]:
        with mock.patch.object(MODULE, "find_claude_bin", return_value="/fake/claude"):
            return MODULE.build_command("review this", **kwargs)

    def test_default_disables_all_tools(self) -> None:
        # DEFAULT_TOOLS is read from CLAUDE_REVIEW_TOOLS at import; pin the
        # fallback so a developer who sets that variable does not fail here.
        with mock.patch.object(MODULE, "DEFAULT_TOOLS", ""):
            cmd = self._cmd()
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")

    def test_explicit_readonly_tools_are_forwarded(self) -> None:
        cmd = self._cmd(tools=ARTIFACT_REVIEW_TOOLS)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")

    def test_explicit_empty_string_still_disables_tools(self) -> None:
        """`tools: ""` is an explicit prompt-only request, not "unset"."""
        cmd = self._cmd(tools="")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")

    def test_reviewer_stays_in_plan_permission_mode(self) -> None:
        """Read-only tools plus plan mode: the reviewer cannot write either way."""
        cmd = self._cmd(tools=ARTIFACT_REVIEW_TOOLS)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "plan")

    def test_tools_are_resent_on_every_resumed_call(self) -> None:
        """Each reply is a fresh `--resume` process, so the opt-in cannot be
        inherited from the round that opened the thread."""
        cmd = self._cmd(session_id="sess-1", tools=ARTIFACT_REVIEW_TOOLS)
        self.assertIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")


class GeneratorDriftTests(unittest.TestCase):
    def test_checked_in_overlay_matches_generator_output(self) -> None:
        """The overlay is generated; hand-edits to SKILL.md would be lost."""
        from tools import generate_codex_claude_review_overrides as gen

        for skill in gen.TARGET_SKILLS:
            source = (gen.SRC_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            match = gen.FRONTMATTER_RE.match(source)
            assert match is not None
            body = source[match.end():].lstrip("\n")
            name = gen.extract_field(match.group(1), "name") or skill
            description = gen.normalize_description(
                gen.extract_field(match.group(1), "description")
            )
            expected = gen.build_frontmatter(name, description)
            expected += gen.OVERRIDE_NOTE + "\n\n"
            expected += gen.transform_body(body).rstrip() + "\n"

            actual = (gen.DEST_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill):
                self.assertEqual(
                    actual,
                    expected,
                    f"{skill} overlay is stale; run "
                    "python tools/generate_codex_claude_review_overrides.py",
                )


if __name__ == "__main__":
    unittest.main()
