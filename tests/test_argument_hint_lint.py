#!/usr/bin/env python3
"""
argument-hint lint: the frontmatter value must be a YAML STRING, never a bare
flow sequence/mapping.

Why: `argument-hint: [foo]` parses as a one-element LIST. Claude Code happens
to render the accident by concatenation, but strict loaders — GitHub Copilot
CLI ≥ 1.0.65 — validate `argument-hint` as a string and silently DROP the
whole skill (#358, fixed repo-wide in #359). This guard keeps the class from
creeping back in via new or upstream-synced skills.

Rule enforced (stdlib-only — CI installs no YAML parser): a value starting
with `[` or `{` must be wrapped in quotes, e.g. `argument-hint: "[paper-dir]"`.
Plain scalars (`argument-hint: paper-dir`) are fine.

Run: python3 tests/test_argument_hint_lint.py   (also pytest-compatible)
"""
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

HINT_RE = re.compile(r"^argument-hint:\s*(.*?)\s*$")


def _frontmatter_lines(text):
    """Lines between the opening --- and the next --- (YAML frontmatter)."""
    if not text.startswith("---"):
        return []
    body = text.split("\n")
    for i in range(1, len(body)):
        if body[i].strip() == "---":
            return body[1:i]
    return []


def check_repo(root=REPO):
    problems = []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(root, "skills")):
        for fn in filenames:
            if fn != "SKILL.md":
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for line in _frontmatter_lines(text):
                m = HINT_RE.match(line)
                if m is None:
                    continue
                value = m.group(1)
                if value.startswith(("[", "{")):
                    problems.append(
                        f"{rel}: argument-hint is a bare YAML flow "
                        f"sequence/mapping ({value!r}) — quote it: "
                        f'argument-hint: "{value}"'
                    )
    return problems


def test_argument_hint_values_are_strings():
    problems = check_repo()
    assert not problems, "\n".join(problems)


def test_lint_catches_a_bare_bracket_regression(tmp_path):
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\nargument-hint: [paper-dir | pdf]\n---\nbody\n",
        encoding="utf-8",
    )
    assert check_repo(str(tmp_path)), "lint failed to flag a bare-bracket hint"
    (skill / "SKILL.md").write_text(
        '---\nname: demo\nargument-hint: "[paper-dir | pdf]"\n---\nbody\n',
        encoding="utf-8",
    )
    assert not check_repo(str(tmp_path)), "lint wrongly flags the quoted form"


if __name__ == "__main__":
    ps = check_repo()
    if ps:
        print("\n".join(ps))
        print(f"\n{len(ps)} array-shaped argument-hint values")
        sys.exit(1)
    print("ok: every argument-hint is a string")
