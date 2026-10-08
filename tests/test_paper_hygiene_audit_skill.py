"""Contract tests for skills/paper-hygiene-audit/SKILL.md, its Codex mirror,
and the references/checks.md page each of them ships.

The SKILL documents a deterministic helper (scripts/paper_hygiene_scan.py); these
tests keep the two from drifting: every check id, reason code, CLI flag, lens,
and policy key the SKILL names must exist in the helper, and the mirror must
keep the Codex reviewer contract (fresh spawn_agent, same-family provisional).

Run: python3 tests/test_paper_hygiene_audit_skill.py   (also pytest-compatible)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "skills" / "paper-hygiene-audit" / "scripts" / "paper_hygiene_scan.py"
SHIM = REPO_ROOT / "tools" / "paper_hygiene_scan.py"
sys.path.insert(0, str(SCANNER.parent))
import paper_hygiene_scan as t  # noqa: E402

MAIN = REPO_ROOT / "skills" / "paper-hygiene-audit" / "SKILL.md"
MIRROR = REPO_ROOT / "skills" / "skills-codex" / "paper-hygiene-audit" / "SKILL.md"
BOTH = (MAIN, MIRROR)
REFS = tuple(p.parent / "references" / "checks.md" for p in BOTH)
ALL_DOCS = BOTH + REFS
CHECK_ID_RE = re.compile(r"\b(?:XREF|ENG|PROC|ANON|META|TEXT|PAGE|TPL|ENDM|SUPP|NUM|CONFIG|CITE|FORM|ALLOW|LOG|BUILD|"
                         r"APPX|FRAME|LENS|FIX)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "missing frontmatter"
    out = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def fenced_blocks(text: str):
    blocks, cur, lang, infence = [], [], "", False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            if infence:
                blocks.append((lang, "\n".join(cur)))
                cur = []
            else:
                lang = line.strip()[3:].strip()
            infence = not infence
            continue
        if infence:
            cur.append(line)
    return blocks


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = re.search(r"^#{2,3} ", text[start + len(heading):], re.M)
    return text[start:start + len(heading) + (nxt.start() if nxt else len(text))]


def reviewer_prompts(text: str) -> list:
    """Every reviewer block's prompt body, in document order (Tier B first)."""
    out = []
    for _lang, body in fenced_blocks(text):
        first = body.strip().split("\n", 1)[0]
        if first.startswith(("mcp__codex__codex:", "spawn_agent:")):
            marker = re.search(r"^\s*(?:prompt|message): \|\n", body, re.M)
            assert marker, "reviewer block has no prompt/message body"
            out.append(body[marker.end():])
    return out


def reviewer_prompt(text: str) -> str:
    prompts = reviewer_prompts(text)
    if not prompts:
        raise AssertionError("no reviewer block")
    return prompts[0]


def scanner_options(command: str) -> set:
    parser = t.build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    return set(sub.choices[command]._option_string_actions)


def test_both_files_exist_with_matching_frontmatter():
    main, mirror = frontmatter(read(MAIN)), frontmatter(read(MIRROR))
    assert main["name"] == mirror["name"] == "paper-hygiene-audit"
    assert main["argument-hint"] == mirror["argument-hint"]
    assert main["argument-hint"].startswith('"[') and main["argument-hint"].endswith('"')
    for fm in (main, mirror):
        assert fm["description"].startswith('"') and fm["description"].endswith('"')
        assert len(fm["description"]) <= 500  # a trigger line, not the manual


@pytest.mark.parametrize("trigger", ["工程性描述", "检查问号", "终稿检查", "终稿复检", "查工程细节",
                                     "submission hygiene", "paper hygiene", "check for ??"])
def test_description_carries_bilingual_triggers(trigger):
    for path in BOTH:
        assert trigger in frontmatter(read(path))["description"], (path.name, trigger)


def test_allowed_tools_follow_the_mainline_and_mirror_conventions():
    main_tools = frontmatter(read(MAIN))["allowed-tools"]
    mirror_tools = frontmatter(read(MIRROR))["allowed-tools"]
    assert "mcp__codex__codex" in main_tools and "Skill" in main_tools
    assert "mcp__codex__codex" not in mirror_tools and "Skill" not in mirror_tools
    assert "Agent" not in main_tools.split(", ")


def test_mainline_keeps_the_audit_contract():
    text = read(MAIN)
    for needle in (
        "../shared-references/external-cadence.md",
        "Failure policy A",
        "NEVER `mcp__codex__codex-reply`",
        '"model_reasoning_effort": "xhigh"',
        "model: gpt-6-astra",
        "Fix the leak, not the detector",
        "never rebuilds, repacks, or edits",
        "Always emit, never block",
        "The executor never acquits",
        "## Final Re-check (`— recheck`)",
        "## Submission Artifact Emission",
        "### Verdict decision table",
        "### `audited_input_hashes` scope",
        "review_response.md",
        "upload_ready",
        "references/checks.md",
    ):
        assert needle in text, needle


def test_mirror_keeps_the_codex_reviewer_contract():
    text = read(MIRROR)
    assert re.search(r"(?m)^\s*spawn_agent:", text)
    assert not re.search(r"(?m)^\s*send_input:", text)
    for needle in ("model: gpt-6-astra", "reasoning_effort: xhigh", "same-family", "provisional",
                   "reviewer_unavailable", "--review-status unavailable", "Executor — Codex",
                   ".aris/installed-skills-codex.txt", "upload_ready", "references/checks.md"):
        assert needle in text, needle
    for banned in ("mcp__codex__codex", "codex-reply", "threadId", "reviewer-continuation", "python3 tools/",
                   "bash tools/", ".aris/tools", ".aris/installed-skills.txt", "~/.claude/", "--thread-id",
                   "fresh cross-family", "cross-model reviewer"):
        assert banned not in text, banned
    assert not MIRROR.read_bytes().startswith(b"\xef\xbb\xbf")


def test_reviewer_prompt_is_identical_in_both_trees():
    assert reviewer_prompt(read(MAIN)) == reviewer_prompt(read(MIRROR))


def test_reviewer_prompt_names_only_lenses_the_scanner_enables():
    prompt = reviewer_prompt(read(MAIN))
    task_b = prompt.split("Task B", 1)[1].split("Rules:", 1)[0]
    named = re.findall(r"^\s{6}([a-z][a-z-]+)\s{2,}", task_b, re.M)
    assert set(named) == set(t.CORE_LENSES) - {"triage"}
    for lens in named:
        assert t._LENS_CHECK[lens] in t.CHECKS
    for ruling in ("leak", "necessary", "false_positive", "uncertain"):
        assert ruling in prompt


def test_every_check_id_named_in_the_docs_exists_in_the_scanner():
    for path in ALL_DOCS:
        unknown = sorted({cid for cid in CHECK_ID_RE.findall(read(path)) if cid not in t.CHECKS})
        assert not unknown, (str(path.relative_to(REPO_ROOT)), unknown)


def test_references_ship_in_both_trees_and_differ_only_in_review_provenance():
    main, mirror = (read(p) for p in REFS)
    diff = [(a, b) for a, b in zip(main.splitlines(), mirror.splitlines()) if a != b]
    assert len(main.splitlines()) == len(mirror.splitlines()) and len(diff) <= 2
    for _a, b in diff:
        assert "cross-family-review:thread" not in b


def _decision_rows(text: str):
    table = section(text, "### Verdict decision table")
    rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| Input state")]
    return [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]


def test_decision_tables_use_the_scanner_vocabulary():
    for path in BOTH:
        rows = _decision_rows(read(path))
        verdicts = {r[1].strip("`") for r in rows}
        assert verdicts == set(t.VERDICTS), (path.name, verdicts)
        codes = set()
        for r in rows:
            codes |= set(re.findall(r"`([a-z_]+)`", r[2]))
        assert codes <= set(t.REASON_CODES), (path.name, sorted(codes - set(t.REASON_CODES)))
        assert set(t.REASON_PRIORITY) <= codes, (path.name, sorted(set(t.REASON_PRIORITY) - codes))
        assert "pdf_text_empty" in codes
        order = [c for c in re.findall(r"`([a-z_]+)`", next(r[2] for r in rows if r[1] == "`FAIL`"))
                 if c in t.REASON_PRIORITY]
        assert order == list(t.REASON_PRIORITY), path.name


def _command_segments(body: str):
    """(subcommand, text) for every `"$HYGIENE_SCANNER" <cmd>` call in a block,
    with its backslash-continued lines (several calls may share one block)."""
    out, cur, cmd = [], [], None
    for line in body.split("\n"):
        m = re.search(r'"\$HYGIENE_SCANNER" ([a-z-]+)', line)
        if m:
            if cmd:
                out.append((cmd, "\n".join(cur)))
            cmd, cur = m.group(1), [line]
        elif cmd and cur and cur[-1].rstrip().endswith("\\"):
            cur.append(line)
        elif cmd:
            out.append((cmd, "\n".join(cur)))
            cmd, cur = None, []
    if cmd:
        out.append((cmd, "\n".join(cur)))
    return out


def test_scanner_flags_used_in_the_skills_exist():
    cmds = ("scan", "finalize", "status", "repack", "edits", "apply", "restore")
    opts = {cmd: scanner_options(cmd) for cmd in cmds}
    for path in BOTH:
        text = read(path)
        seen = set()
        for _lang, body in fenced_blocks(text):
            for cmd, seg in _command_segments(body):
                seen.add(cmd)
                flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", seg.split("#", 1)[0] if "#" in seg else seg))
                assert flags <= opts[cmd], (path.name, cmd, sorted(flags - opts[cmd]))
        assert {"scan", "finalize", "status", "apply", "restore"} <= seen, (path.name, sorted(seen))
        flag_table = section(text, "### Step 1: Collect Inputs")
        documented = set(re.findall(r"`(--[a-z][a-z-]*)", flag_table))
        assert documented <= opts["scan"], (path.name, sorted(documented - opts["scan"]))
        for flag in ("--src", "--out"):
            assert flag in opts["repack"]
        for flag in ("--run-mode", "--baseline", "--fix-round", "--review-status", "--work-dir"):
            assert flag in text, (path.name, flag)


def test_json_examples_parse_and_match_the_helper():
    for path in REFS:
        blocks = [body for lang, body in fenced_blocks(read(path)) if lang == "json"]
        policy = next(json.loads(b) for b in blocks if '"venue"' in b)
        assert set(policy) <= t.POLICY_KEYS
        table = section(read(path), "`policy.json` holds")
        assert set(re.findall(r"^\| `([a-z_]+)`", table, re.M)) | {
            k for row in re.findall(r"^\| (`[a-z_]+`(?:, `[a-z_]+`)+) \|", table, re.M)
            for k in re.findall(r"`([a-z_]+)`", row)} == t.POLICY_KEYS
    for path in BOTH:
        blocks = [body for lang, body in fenced_blocks(read(path)) if lang == "json"]
        artifact = next(json.loads(b) for b in blocks if '"audit_skill"' in b)
        assert artifact["audit_skill"] == t.SKILL_NAME
        for key in ("verdict", "reason_code", "summary", "audited_input_hashes", "trace_path", "executor_model",
                    "executor_family", "reviewer_model", "reviewer_family", "review_independence",
                    "acceptance_status", "reviewer_reasoning", "generated_at", "details"):
            assert key in artifact, (path.name, key)
        assert "thread_id" in artifact or "agent_id" in artifact
        assert all(not k.startswith(("/", "paper/")) for k in artifact["audited_input_hashes"])
        assert {"upload_ready", "recheck_required"} <= set(artifact["details"])


def test_allow_list_example_parses_with_typed_provenance():
    for path in REFS:
        block = next(body for _lang, body in fenced_blocks(read(path))
                     if body.startswith("# .aris/paper-hygiene/allow.tsv"))
        entries, issues = t.parse_allow(block)
        assert len(entries) == 2 and not issues, (str(path), issues)
    mirror_block = next(body for _lang, body in fenced_blocks(read(REFS[1]))
                        if body.startswith("# .aris/paper-hygiene/allow.tsv"))
    assert all(e["approved_by"].startswith("human:") for e in t.parse_allow(mirror_block)[0])


def test_every_reviewer_prompt_is_identical_in_both_trees():
    main, mirror = reviewer_prompts(read(MAIN)), reviewer_prompts(read(MIRROR))
    # Tier B and the supplementary batch; no reviewer judges the fix loop's edits (the whitelist does)
    assert len(main) == len(mirror) == 2
    assert main == mirror
    for path in BOTH:
        text = read(path)
        assert "change_review" not in text and "FIX-MEANING" not in text and "roll back" not in text.lower()


def test_the_skill_states_its_position_and_the_whitelist_names_every_fix_class():
    for path in BOTH:
        text = read(path)
        head = text.split("## Why This Exists", 1)[0]
        assert "a detector and a final re-checker" in head and "fix plan" in head, path.name
        table = section(text, "**The whitelist**")
        classes = re.findall(r"^\| `([a-z-]+)` \|", table, re.M)
        assert classes == list(t.FIX_CLASSES), (path.name, classes)
        for needle in ("apply", "--undo", "restore", "FIX_PLAN.md", "best_round", "never spend a round that only",
                       "subsequence"):
            assert needle in text, (path.name, needle)
    whitelist = section(read(MAIN), "**The whitelist**")
    for line in t.META_PREAMBLE_LINES:  # the metadata lines the script queues are the ones the SKILL names
        assert line.split("{")[0] in whitelist, line


def test_the_batch_prompt_checks_every_category_and_lists_checked_members():
    prompt = reviewer_prompts(read(MAIN))[1]
    named = re.findall(r"^\s{6}([a-z]+)\s{2,}", prompt, re.M)
    assert named == list(t.SUPP_CHECKLIST)
    assert "members_checked" in prompt and "supp_batches" in prompt


def test_the_rewrite_rules_are_in_the_skill_and_in_every_rewriting_prompt():
    for path in BOTH:
        text = read(path)
        edit = section(text, "**How the fix plan words a fix**")
        for needle in ("Keep every ordering", "relative expression", "never a plain deletion",
                       "Cut the fragment, not the sentence", "Add nothing", "connective", "never reword it away",
                       "never turned into a sentence"):
            assert needle in edit, (path.name, needle)
    tier_b, batch = reviewer_prompts(read(MAIN))[:2]
    for needle in ("relative expression (after, before,", "never propose\n        deleting such a sentence",
                   "never add a fact", "orphaned connective", "keep its\n        subject and tense",
                   "deleted with its note, never turned\n        into a sentence", "venue_policy"):
        assert needle in tier_b, needle
    assert "add\n    nothing" in batch or "add nothing" in batch
    assert "new_evidence" in tier_b and "prior_rulings" in tier_b and "carried_findings" in tier_b


def test_the_fix_log_row_format_in_the_skill_parses():
    for path in BOTH:
        text = read(path)
        header = re.search(r"^\s*(\| round \| id \| group \| class \| where \| before \| after \|)\s*$", text, re.M)
        assert header, path.name
        assert t.FIX_LOG_HEADER.startswith(header.group(1).strip())
        rows = t.parse_fix_log(t.FIX_LOG_HEADER + "| 1 | A1-001 | G-007 | delete | a.tex | x y | x |\n")
        assert rows == [{"round": 1, "id": "A1-001", "group": "G-007", "class": "delete", "where": "a.tex",
                         "before": "x y", "after": "x"}]


NEVER_QUEUED = ("PROC-TIME", "PROC-REVISION", "PROC-REVIEW", "PROC-DATESEED", "PROC-REGLABEL", "PROC-PENDING",
                "ENG-FW", "ENG-HASH", "ENG-FILENAME", "ENG-PRECISION", "ENG-DENY", "ANON-CODENAME", "SUPP-NAME",
                "SUPP-PROCFILE", "SUPP-PATH", "SUPP-RUNTIME", "TEXT-NOSPACE", "TEXT-GLUE", "TEXT-MATHGLYPH",
                "TEXT-T3FONT", "META-FIGURE", "PAGE-FILL")


def test_the_plan_rules_name_every_check_the_loop_never_fixes():
    for path in BOTH:
        line = read(path).split("Everything else is in the fix plan, never in the queue", 1)[1].split("\n", 1)[0]
        # the one way such a check reaches the queue: the whole sentence or clause it is, as delete-sentence
        head, rest = line.split(":", 1)
        assert "delete-sentence" in head, path.name
        for cid in NEVER_QUEUED:
            assert cid in rest, (path.name, cid)
        assert "LENS-*" in rest and "renames" in rest and "single-key" in rest
    for cid in NEVER_QUEUED:  # whatever the level and the ruling, the script never queues them
        f = {"check": cid, "family": t.CHECKS[cid]["family"], "severity": t.BLOCK, "certainty": t.DEFINITE,
             "ruling": "leak", "match": "x", "location": {}}
        assert t._fix_class(f) is None, cid
        assert t._fix_class(dict(f, certainty=t.CANDIDATE)) is None, cid


def test_the_skill_documents_the_draft_edits_and_the_pure_leak_units_with_their_exclusions():
    for path in BOTH:
        text = read(path)
        step5 = section(text, "### Step 5")
        # the script drafts the round's edits; the executor reviews them and never alters one
        assert "edits --from-queue" in step5 and "never alter one" in step5 and "unwritten" in step5, path.name
        assert "several deletions left as a skeleton" in step5, path.name
        assert "--from-queue" in scanner_options("edits")
        units = text.split("**Pure-leak sentences and clauses.**", 1)[1].split("\n\n", 1)[0]
        for needle in ("number", "\\ref", "result or conclusion word", "skeleton_result_words", "end matter",
                       "table", "caption", "equation", "only, not, no, never, except, unless, without",
                       "registration, amendment, revision, or version word", "delete-sentence",
                       "details.pure_leak_units", "details.narration_raised", "keep the re-run or the fix"):
            assert needle in units, (path.name, needle)
        limits = section(text, "## Known Limitations")
        assert "nothing generates them from the queue" not in limits, path.name
        assert "even pure narration whose fix is deleting the sentence" not in limits, path.name
    assert "only definite hits count" in read(MIRROR)
    assert "skeleton_result_words" in t.POLICY_KEYS


def test_the_warn_row_names_every_warn_reason_in_order():
    for path in BOTH:
        rows = _decision_rows(read(path))
        warn = next(r for r in rows if r[1] == "`WARN`")
        assert re.findall(r"`([a-z_]+)`", warn[2]) == list(t.WARN_REASONS), path.name


def test_tables_are_well_formed():
    for path in ALL_DOCS:
        lines = read(path).splitlines()
        for i, line in enumerate(lines[:-1]):
            nxt = lines[i + 1]
            if line.strip().startswith("|") and set(nxt.strip()) <= {"|", "-", ":", " "} and "-" in nxt:
                header = len(re.split(r"(?<!\\)\|", line.strip().strip("|")))
                sep = len(nxt.strip().strip("|").split("|"))
                assert header == sep, f"{path.name}:{i + 1} header {header} cells vs separator {sep}"
                for j in range(i + 2, len(lines)):
                    if not lines[j].strip().startswith("|"):
                        break
                    cells = len(re.split(r"(?<!\\)\|", lines[j].strip().strip("|")))
                    assert cells == header, f"{path.name}:{j + 1} has {cells} cells, header has {header}"


def test_the_scanner_lives_in_the_skill_and_the_tools_entry_forwards_to_it():
    # Phase 3 layout (integration-contract §2, layer 0): the canonical copy is in the skill's own
    # scripts/, and tools/ keeps a small os.execv shim for the legacy resolver layers
    assert SCANNER.is_file() and SHIM.is_file()
    shim = SHIM.read_text(encoding="utf-8")
    assert "os.execv" in shim and '"paper-hygiene-audit" / "scripts" / "paper_hygiene_scan.py"' in shim
    assert len(shim.splitlines()) < 100
    direct = subprocess.run([sys.executable, str(SCANNER), "list-checks"], capture_output=True, text=True)
    via_shim = subprocess.run([sys.executable, str(SHIM), "list-checks"], capture_output=True, text=True)
    assert direct.returncode == via_shim.returncode == 0, (direct.stderr, via_shim.stderr)
    assert via_shim.stdout == direct.stdout and json.loads(direct.stdout)


def test_the_scanner_finds_the_shared_helpers_from_its_skill_folder(tmp_path):
    # run from an unrelated directory, with no PYTHONPATH, ARIS_REPO, or ~/.aris/repo pointer:
    # threat_scan and provenance still come from the repository's tools/
    probe = ("import importlib.util, json, sys\n"
             "spec = importlib.util.spec_from_file_location('phs', sys.argv[1])\n"
             "m = importlib.util.module_from_spec(spec)\n"
             "spec.loader.exec_module(m)\n"
             "print(json.dumps([m._invisible_set()[1], m._model_family('gpt-6-astra')[1]]))\n")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ARIS_REPO")}
    env["HOME"] = str(tmp_path)
    out = subprocess.run([sys.executable, "-c", probe, str(SCANNER)], cwd=str(tmp_path), env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, None]


def test_step_0_tries_the_skill_folder_first_in_both_trees():
    main = MAIN.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    assert (main.index('"$CLAUDE_SKILL_DIR/scripts/paper_hygiene_scan.py"')
            < main.index('".aris/tools/paper_hygiene_scan.py"'))
    assert (mirror.index('"$ARIS_REPO/skills/paper-hygiene-audit/scripts/paper_hygiene_scan.py"')
            < mirror.index('"$ARIS_REPO/tools/paper_hygiene_scan.py"'))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
