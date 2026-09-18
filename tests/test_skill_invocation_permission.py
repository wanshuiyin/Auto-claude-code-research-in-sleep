#!/usr/bin/env python3
"""Skill-grant hygiene (#284): a SKILL.md whose body instructs invoking another
skill must grant `Skill` in `allowed-tools`.

Why: `allowed-tools` is the capability gate. A body that says "Run
`/novelty-check`" while the gate omits `Skill` cannot perform the step it was
told to perform, so the executor re-implements it inline — the failure mode
diagnosed in #284 and fixed for `/idea-creator` in 07ca667. That fix covered the
one skill the issue reported; this guard keeps the class closed when new skills
land or upstream syncs bring one in.

Design: pattern-based, not prompt understanding. A call is a bare imperative
(`run` / `invoke` / `call` / `delegate to` / `rerun`) within a few characters of
the `` `/skill-name` `` reference — the idiom this repo uses for
executor-directed calls. Descriptive forms ("it invokes `/x`", "can be invoked
by `/x`", "called automatically by `/x`") and routing advice ("use `/y`
instead") do not match, by construction. Explicit exclusions, each protecting a
real line already in this tree:

  * fenced blocks — text a skill EMITS, e.g. the report templates in
    paper-compile / experiment-queue carrying "Next Steps: Run
    `/analyze-results`" for the reader;
  * self-references — a skill re-running itself (research-refine);
  * an immediately preceding negation — "do not invoke `/render-html` as a
    sub-skill" (interview-cheatsheet);
  * human-directed wording — "ask the user to run `/paper-plan`"
    (paper-write), "That human action is the landing gate" (meta-optimize);
  * boundary/relationship sections ("When NOT to Use", "What This Skill Is —
    and Is NOT", "Recommended Follow-up") — these describe how skills relate
    rather than instructing a step.

Known non-goal: a genuine step written inside a boundary/relationship section
would be skipped, and a paraphrase that never names the skill ("call the novelty
skill") is invisible to a regex. No such case exists in the current tree.

Scope: mainline `skills/*/SKILL.md` only — the Codex mirrors grant no `Skill` by
design (Codex-side fan-out is expressed through `spawn_agent`), so scanning them
would report dozens of false positives.

Run: python3 tests/test_skill_invocation_permission.py   (also pytest-compatible)
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.check_skills_inventory import skill_invocation_permission_drift  # noqa: E402

SKILLS_ROOT = REPO_ROOT / "skills"

# (skill name, allowed-tools line or None, body)
UNGRANTED_INVOCATIONS = [
    ("alpha", "allowed-tools: Bash(*), Read", "Run `/novelty-check` on the draft\n"),
    # a passing mention of the user must NOT suppress the finding
    ("beta", "allowed-tools: Read",
     "After writing the report, invoke `/render-html` on it so the user has a "
     "readable view.\n"),
    # wrapped across lines, and wrapped in a markdown link
    ("gamma", "allowed-tools: Read",
     "Run\n[`/integrity-forensics`](../integrity-forensics/SKILL.md) after all "
     "microedits\n"),
    ("delta", "allowed-tools: Bash(*), Grep",
     "| Proof gap | Delegate to `/kill-argument` and merge the findings |\n"),
    ("epsilon", None, "Then rerun `/result-to-claim` first\n"),  # no frontmatter line at all
]

ACCEPTED = [
    ("granted", "allowed-tools: Bash(*), Read, Skill", "Run `/novelty-check` on the draft\n"),
    ("scoped", "allowed-tools: Read, Skill(novelty-check)", "Run `/novelty-check`\n"),
    ("negated", "allowed-tools: Read",
     "Call directly (do not invoke `/render-html` as a sub-skill; call its script)\n"),
    ("human-asked", "allowed-tools: Read",
     "If no PAPER_PLAN.md exists, ask the user to run `/paper-plan` first.\n"),
    ("human-gate", "allowed-tools: Read, Write, Edit",
     "  invoke `/meta-apply` to land them. That human action is the landing gate.\n"),
    ("routing", "allowed-tools: Read", "**Not for:** statistical plots — use `/paper-figure`\n"),
    ("descriptive", "allowed-tools: Read",
     "It can be invoked by `/auto-paper-improvement-loop` Step 5.5\n"),
    ("self-reference", "allowed-tools: Read", "Re-run `/self-reference` for a second pass\n"),
    ("emitted-template", "allowed-tools: Read",
     "Report:\n\n```\n## Next Steps\n- Run `/analyze-results` on output JSONs\n```\n"),
    ("scope-section", "allowed-tools: Read",
     "## When NOT to Use\n\n- Complete redesign needed — re-run `/paper-slides`, not polish.\n"),
    ("name-not-a-verb", "allowed-tools: Read",
     "Source of truth for `/run-experiment` and `/monitor-experiment`.\n"),
]


def make_skill(tmp_path: Path, name: str, tools_line: str | None, body: str) -> Path:
    skill = tmp_path / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nname: {name}\ndescription: demo\n"
    if tools_line:
        frontmatter += f"{tools_line}\n"
    (skill / "SKILL.md").write_text(f"{frontmatter}---\n\n{body}", encoding="utf-8")
    return tmp_path


def test_ungranted_invocations_are_flagged(tmp_path):
    for i, (name, tools, body) in enumerate(UNGRANTED_INVOCATIONS):
        root = make_skill(tmp_path / f"case{i}", name, tools, body)
        found = skill_invocation_permission_drift(root / "skills")
        assert len(found) == 1, f"missed or double-reported case {name}: {found}"
        assert f"skills/{name}/SKILL.md" in found[0]


def test_legitimate_forms_are_accepted(tmp_path):
    for i, (name, tools, body) in enumerate(ACCEPTED):
        root = make_skill(tmp_path / f"ok{i}", name, tools, body)
        found = skill_invocation_permission_drift(root / "skills")
        assert not found, f"false positive on case {name}: {found}"


def test_mainline_skills_are_clean():
    drift = skill_invocation_permission_drift(SKILLS_ROOT)
    assert not drift, "\n".join(drift)


if __name__ == "__main__":
    drift = skill_invocation_permission_drift(SKILLS_ROOT)
    if drift:
        print("\n".join(drift))
        print(f"\n{len(drift)} ungranted sub-skill invocation(s)")
        sys.exit(1)
    print("ok: every skill that instructs a sub-skill invocation grants `Skill`")
