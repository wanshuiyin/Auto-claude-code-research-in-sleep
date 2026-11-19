"""Regression coverage for sub-skill invocation ⇒ `Skill` grant (issue #284).

Issue #284's root cause was structural: `/idea-creator` told the executor to run
`/novelty-check` and others, but `allowed-tools` withheld the `Skill` tool, so the
model could not comply and improvised a shallow substitute. A one-off patch to
that one skill does not stop the next one from shipping the same way, so the
invariant lives in `check_skills_inventory.py` and is exercised here.

The detector must stay narrow. Most "`/skill`" strings in a body are not
invocations — they are provenance notes, "use X instead" disambiguations, or
instructions addressed to the human. Flagging those would train maintainers to
ignore the check, which is worse than not having it.
"""

import pytest

from tools.check_skills_inventory import (
    SKILLS_ROOT,
    allowed_tools,
    base_tool,
    declared_invocations,
)

FRONTMATTER = "---\nname: example\ndescription: example\n---\n\n"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # ── imperative, executor-addressed: these ARE invocations ──
        (
            "2. If ablation studies are incomplete → trigger `/ablation-planner`\n",
            ["ablation-planner"],
        ),
        ("13. Hand off to /paper-write for LaTeX generation\n", ["paper-write"]),
        ("Then run `/monitor-experiment` to check progress.\n", ["monitor-experiment"]),
        ("Handoff to `/paper-writing` once claims are gated.\n", ["paper-writing"]),
        # ── provenance / description: not invocations ──
        ("Figures come from `/paper-figure` in `figures/`.\n", []),
        ("Upstream (`/research-lit`, `/novelty-check`) may mention papers.\n", []),
        # ── addressed to the human: not the executor's call ──
        ("If no plan exists, ask the user to run `/paper-plan` first.\n", []),
        ("Remind the user to run `/vast-gpu destroy` to stop billing.\n", []),
        ("A human must then invoke `/meta-apply` to land them.\n", []),
        ("The user can manually invoke `/research-review` on the source MD.\n", []),
        # ── negations / redirection: not invocations ──
        ("For statistical plots use `/paper-figure` instead.\n", []),
        ("Do not auto-trigger `/idea-creator`; the user decides.\n", []),
        ("Call directly (do not invoke `/render-html` as a sub-skill).\n", []),
        # ── table rows describe artifact ownership, not calls ──
        ("| `/kill-argument` | `KILL_ARGUMENT.md` | full gate |\n", []),
        # ── unrecognised verb: no match, not a miss ──
        ("Consider `/paper-slides` for deck generation.\n", []),
    ],
)
def test_declared_invocations_narrowing(body, expected):
    assert declared_invocations(FRONTMATTER + body) == expected


def test_frontmatter_arguments_do_not_count_as_body_invocations():
    """A `trigger /x` line inside frontmatter is metadata, not an instruction."""
    text = "---\nname: example\ntrigger: /does-not-exist\n---\n\nBody without calls.\n"
    assert declared_invocations(text) == []


def test_every_declared_sub_skill_invocation_holds_the_skill_grant():
    """Repository-wide invariant.

    Any body that imperatively runs another ARIS skill must be granted `Skill`,
    otherwise the executor improvises — the #284 failure mode.
    """
    inventory = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
    violations = []
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        invoked = [name for name in declared_invocations(text) if name in inventory]
        if not invoked:
            continue
        granted = {base_tool(rule) for rule in allowed_tools(text)}
        if "Skill" not in granted:
            violations.append(f"{skill_file.parent.name} -> {invoked}")
    assert violations == [], (
        "skills instruct the executor to run sub-skills without granting `Skill` "
        f"(issue #284): {violations}"
    )
