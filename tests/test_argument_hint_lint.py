#!/usr/bin/env python3
"""
argument-hint lint: the frontmatter value must be a same-line YAML STRING —
never a flow sequence/mapping, block collection, or anchored/tagged node.

Why: `argument-hint: [foo]` parses as a one-element LIST. Claude Code happens
to render the accident by concatenation, but strict loaders — GitHub Copilot
CLI ≥ 1.0.65 — validate `argument-hint` as a string and silently DROP the
whole skill (#358, fixed repo-wide in #359). This guard keeps the class from
creeping back in via new or upstream-synced skills.

Design (stdlib-only — CI installs no YAML parser): this is a CANONICAL-SYNTAX
lint, not a YAML parser. The repo convention it enforces: a top-level
`argument-hint` key must carry a non-empty same-line scalar that is quoted
whenever it isn't a plain word — so an empty right-hand side (block
sequence/map follows on the next lines), a bare `[`/`{` flow collection, or a
`&anchor`/`*alias`/`!tag` node property all FAIL with a fix-it message.
Block scalars (`key: |` / `key: >`) elsewhere in the frontmatter are skipped
so their indented content (which may contain `argument-hint:` or `---` as
text) neither false-positives nor terminates the fence scan early.

Known non-goal: a multi-line double-quoted scalar whose continuation line
begins with `argument-hint:` would false-positive — no such frontmatter
exists in this repo, and a line-based lint cannot see quote state without a
real parser.

Run: python3 tests/test_argument_hint_lint.py   (also pytest-compatible)
"""
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# top-level key, tolerating quoted keys and space before the colon
HINT_RE = re.compile(r"""^(?:"argument-hint"|'argument-hint'|argument-hint)\s*:\s*(.*?)\s*$""")
# any top-level key that opens a block scalar (its indented body is not YAML keys)
BLOCK_SCALAR_RE = re.compile(r"""^\S[^:]*:\s*[|>][+-]?\d*\s*(?:#.*)?$""")


def _frontmatter_lines(text):
    """Lines between the opening --- and the CLOSING fence (a column-0 ---).

    An indented `---` inside a block scalar is content, not a fence."""
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        return []
    body = text.split("\n")
    for i in range(1, len(body)):
        if body[i].rstrip("\r") == "---":
            return body[1:i]
    return []


def _violations_in_frontmatter(lines):
    problems = []
    in_block_scalar = False
    for line in lines:
        if in_block_scalar:
            if line.strip() == "" or line[:1] in (" ", "\t"):
                continue            # still inside the block scalar's body
            in_block_scalar = False
        m = HINT_RE.match(line)
        if m is None:
            if BLOCK_SCALAR_RE.match(line):
                in_block_scalar = True
            continue
        value = m.group(1)
        if not value.startswith(('"', "'")):
            # strip a trailing YAML comment from UNQUOTED values (in YAML a
            # comment needs preceding whitespace; a plain scalar cannot
            # contain " #", so the split is safe) — otherwise
            # `argument-hint: null  # todo` would classify as a plain string
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if value == "" or value.startswith("#"):
            problems.append(
                "argument-hint has no same-line value (a null / block "
                "sequence/map on the following lines is not a string) — "
                'write argument-hint: "[your-hint]"'
            )
        elif value.startswith(("[", "{")):
            problems.append(
                f"argument-hint is a bare YAML flow sequence/mapping "
                f'({value!r}) — quote it: argument-hint: "{value}"'
            )
        elif value.startswith(("&", "*", "!")):
            problems.append(
                f"argument-hint carries a YAML anchor/alias/tag ({value!r}) "
                "— use a plain quoted string"
            )
        elif re.fullmatch(r"[|>][+-]?\d*", value):
            problems.append(
                f"argument-hint opens a block scalar ({value!r}) — the hint "
                'must be a same-line string: argument-hint: "[your-hint]"'
            )
        elif value.lower() in ("null", "~", "true", "false", "yes", "no", "on", "off") \
                or re.fullmatch(r"[+-]?\d+(\.\d+)?", value):
            problems.append(
                f"argument-hint YAML-types as null/bool/number ({value!r}), "
                f'not a string — quote it: argument-hint: "{value}"'
            )
    return problems


def check_repo(root=REPO):
    skills_root = os.path.join(root, "skills")
    if not os.path.isdir(skills_root):
        raise SystemExit(f"FATAL: no skills/ directory under {root} — wrong root?")
    problems = []
    for dirpath, _dirnames, filenames in os.walk(skills_root):
        for fn in filenames:
            if fn != "SKILL.md":
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            with open(path, encoding="utf-8") as fh:
                lines = _frontmatter_lines(fh.read())
            problems.extend(f"{rel}: {p}" for p in _violations_in_frontmatter(lines))
    return problems


def test_argument_hint_values_are_strings():
    problems = check_repo()
    assert not problems, "\n".join(problems)


def _mk(tmp_path, frontmatter):
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
    return str(tmp_path)


BAD_FRONTMATTERS = [
    "name: demo\nargument-hint: [paper-dir | pdf]",           # bare flow sequence
    "name: demo\nargument-hint: {a: b}",                      # bare flow mapping
    "name: demo\nargument-hint:\n  - paper-dir",              # block sequence
    "name: demo\nargument-hint:\n  [paper-dir]",              # next-line flow seq
    "name: demo\nargument-hint:\n  key: value",               # block mapping
    "name: demo\nargument-hint : [paper-dir]",                # space before colon
    'name: demo\n"argument-hint": [paper-dir]',               # quoted key
    "name: demo\nargument-hint: &hint [paper-dir]",           # anchored node
    "name: demo\nargument-hint:  # to fill in later",         # comment-only = null
    "name: demo\nargument-hint: |\n  multi\n  line",          # block scalar
    "name: demo\nargument-hint: >-\n  folded",                # folded block scalar
    "name: demo\nargument-hint: null",                        # YAML null
    "name: demo\nargument-hint: ~",                           # YAML null (tilde)
    "name: demo\nargument-hint: true",                        # YAML bool
    "name: demo\nargument-hint: 123",                         # YAML int
    "name: demo\nargument-hint: | # comment",                 # block scalar + comment
    "name: demo\nargument-hint: null  # todo",                # null + comment
    "name: demo\nargument-hint: [x]  # comment",              # flow seq + comment
]

GOOD_FRONTMATTERS = [
    'name: demo\nargument-hint: "[paper-dir | pdf]"',         # the canonical fix
    "name: demo\nargument-hint: paper-dir",                   # plain scalar
    "name: demo\nargument-hint: 'quoted single'",             # single-quoted
    # block-scalar description whose BODY mentions the bad form and an
    # indented --- : must neither false-positive nor end the fence early
    'name: demo\ndescription: |\n  says argument-hint: [x]\n  ---\n  more\nargument-hint: "[ok]"',
]


def test_lint_catches_each_regression_shape(tmp_path):
    for i, fm in enumerate(BAD_FRONTMATTERS):
        root = _mk(tmp_path, fm)
        assert check_repo(root), f"lint missed BAD_FRONTMATTERS[{i}]: {fm!r}"


def test_lint_accepts_legitimate_forms(tmp_path):
    for i, fm in enumerate(GOOD_FRONTMATTERS):
        root = _mk(tmp_path, fm)
        assert not check_repo(root), f"lint wrongly flags GOOD_FRONTMATTERS[{i}]: {fm!r}"


if __name__ == "__main__":
    ps = check_repo()
    if ps:
        print("\n".join(ps))
        print(f"\n{len(ps)} non-string argument-hint values")
        sys.exit(1)
    print("ok: every argument-hint is a same-line string")
