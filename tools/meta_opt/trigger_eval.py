#!/usr/bin/env python3
"""trigger_eval.py — measure whether a skill's `description` actually triggers.

ARIS's known pain: with 80+ skills installed, Claude Code sometimes fails to
invoke the right skill for a query it should handle — and until now the only
lever (the frontmatter `description`) was tuned by pure judgment, with zero
measurement. This tool turns trigger behavior into a number.

MEASURE-ONLY BY DESIGN. It never rewrites a description. Its report is
EVIDENCE for a /meta-optimize proposal (which lands only via the human-gated
/meta-apply) — "a loop can drive, never acquit" applies to description tuning
too.

How it works (adapted from Anthropic's Claude Science `skill-creator`
run_eval.py — Apache-2.0; ported off its host.* runtime onto plain `claude -p`):
- For each (skill, query), run `claude -p <query> --output-format stream-json
  --max-turns 1 --permission-mode plan --disallowed-tools Bash Write Edit …`
  as a subprocess FROM A NEUTRAL TEMP CWD. The user-level ~/.claude/skills
  corpus is loaded as usual, so the measurement happens under the REALISTIC
  long installed list — the exact condition under which omission happens (an
  isolated one-skill sandbox would trivially inflate trigger rates).
- Parse the stream for the first assistant turn's tool_use blocks. A `Skill`
  tool call with input.skill == target counts as a TRIGGER; a Skill call for a
  different skill is a CONFUSION (recorded by name — the confusion matrix is
  the interesting part for the long-list problem); no Skill call is a MISS.
  Reading the target's SKILL.md via the Read tool counts as a trigger too
  (secondary signal).
- SAFETY: `--permission-mode plan` blocks every side-effecting tool (Bash,
  Write, Edit, …) from executing, so a probed skill's own commands (e.g.
  check-gpu's ssh, vast-gpu's rentals) do NOT run — we observe only which tool
  the model REACHED FOR. The read-only tools we score on (a `Skill` load, a
  `Read` of a SKILL.md) may execute, and both are side-effect-free.
  `--disallowed-tools` denies the stateful tools explicitly as belt-and-braces,
  and `--no-session-persistence` avoids leaving session artifacts. This is a
  measurement, not a sandbox — it does not stop the user's own SessionStart
  hooks (their normal per-session behavior), it stops the PROBED WORK.

Query-set methodology (see trigger_evals.sample.json): queries must PARAPHRASE
user intent, never quote the description's own trigger phrases verbatim — a
query containing the literal trigger string is trivially positive and measures
nothing. Optional negative queries (expect: none) measure false-triggering.

Usage:
  python3 tools/meta_opt/trigger_eval.py --eval-file tools/meta_opt/trigger_evals.sample.json \\
      [--skills check-gpu,research-lit] [--samples 2] [--model haiku] \\
      [--out .aris/meta/trigger_report.json] [--timeout 120]

Exit code: 0 on completed run (regardless of rates), 2 on setup error.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------- pure logic

def parse_stream_tool_uses(stream_text: str):
    """Extract (tool_name, tool_input) pairs from `claude -p` stream-json output.

    Each line is a JSON event; assistant events carry message.content lists in
    which tool_use blocks appear. Malformed lines are skipped (the stream can
    interleave non-JSON stderr noise when things go wrong).
    """
    uses = []
    for line in stream_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append((block.get("name") or "", block.get("input") or {}))
    return uses


def classify(tool_uses, target_skill: str):
    """Classify one probe run: ('trigger'|'confusion'|'miss', detail).

    Trigger: a Skill call for the target (exact id, or a `plugin:target`
    namespaced form — the latter tagged in detail so a namespaced match is
    never silently indistinguishable from an exact one), or a Read of the
    target's SKILL.md.
    Confusion: the FIRST Skill call named a different skill (detail = its name).
    Miss: no skill engagement at all.
    """
    for name, inp in tool_uses:
        if name == "Skill":
            invoked = (inp.get("skill") or "").strip()
            if invoked == target_skill:
                return "trigger", invoked
            # plugin-namespaced form "plugin:skill": a trigger only if the tail
            # equals the target AND the target itself is bare (not namespaced),
            # surfaced distinctly so a human can spot a plugin/bare collision.
            if ":" in invoked and invoked.split(":")[-1] == target_skill \
                    and ":" not in target_skill:
                return "trigger", f"{invoked} (namespaced→{target_skill})"
            return "confusion", invoked
        if name == "Read":
            path = str(inp.get("file_path") or "")
            if f"/skills/{target_skill}/SKILL.md" in path:
                return "trigger", path
    return "miss", ""


def aggregate(records):
    """records: list of {skill, query, outcome, detail} → per-skill summary."""
    out = {}
    for r in records:
        s = out.setdefault(r["skill"], {
            "probes": 0, "triggers": 0, "misses": 0, "errors": 0,
            "confusions": {}, "queries": {},
        })
        s["probes"] += 1
        q = s["queries"].setdefault(r["query"], {"trigger": 0, "confusion": 0,
                                                 "miss": 0, "error": 0})
        q[r["outcome"]] += 1
        if r["outcome"] == "trigger":
            s["triggers"] += 1
        elif r["outcome"] == "miss":
            s["misses"] += 1
        elif r["outcome"] == "error":
            s["errors"] += 1
        elif r["outcome"] == "confusion":
            s["confusions"][r["detail"]] = s["confusions"].get(r["detail"], 0) + 1
    for s in out.values():
        graded = s["probes"] - s["errors"]
        s["trigger_rate"] = round(s["triggers"] / graded, 3) if graded else None
    return out


# ------------------------------------------------------------------- probing

# Stateful tools that must never execute during a probe (belt-and-braces on top
# of --permission-mode plan, which already blocks side-effecting tools).
_DENY_TOOLS = ["Bash", "Write", "Edit", "NotebookEdit", "WebFetch"]


# `--max-turns 1` deliberately caps the probe at one turn, so the CLI ends with
# result subtype `error_max_turns` and a NONZERO exit — that is the EXPECTED,
# successful termination for a probe, NOT a failure. Only other errors (auth,
# startup/hook failure, execution error) count as a real error.
_EXPECTED_TERMINATION = "error_max_turns"


def _stream_real_error(stream_text: str) -> bool:
    """True iff the stream carries a genuine terminal error — an `is_error`
    result whose subtype is NOT the expected max-turns cap. Auth/hook failures
    that still emit JSON are caught here so they are graded `error`, never a
    `miss` that would silently corrupt the trigger rate."""
    for line in stream_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result" and ev.get("is_error") \
                and ev.get("subtype") != _EXPECTED_TERMINATION:
            return True
    return False


def _stream_has_assistant(stream_text: str) -> bool:
    """True iff the model produced at least one assistant turn — i.e. the probe
    ran far enough to be gradeable (even if it then hit the max-turns cap)."""
    for line in stream_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            if json.loads(line).get("type") == "assistant":
                return True
        except json.JSONDecodeError:
            continue
    return False


def run_probe(query: str, model: str | None, timeout: int, cwd: str) -> str:
    """One `claude -p` probe; returns raw stream-json text. Raises RuntimeError
    on a REAL failure (genuine error event, or nonzero exit with no assistant
    turn at all) so the caller records `error` rather than a rate-corrupting
    `miss`. The expected max-turns termination (nonzero exit + assistant turn
    present) is a normal, gradeable result."""
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
           "--max-turns", "1", "--permission-mode", "plan",
           "--no-session-persistence", "--disallowed-tools", *_DENY_TOOLS]
    if model:
        cmd += ["--model", model]
    # Allow nesting claude -p inside a Claude Code session (same pattern as the
    # Apache-2.0 source): the CLAUDECODE guard is for interactive terminals.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(cmd, input=query, capture_output=True, text=True,
                            env=env, timeout=timeout, cwd=cwd)
    if _stream_real_error(result.stdout):
        raise RuntimeError("claude -p stream carried a terminal error result event")
    if _stream_has_assistant(result.stdout):
        return result.stdout                       # gradeable (max-turns cap is fine)
    if result.returncode != 0:                     # no assistant turn AND failed = real
        raise RuntimeError(f"claude -p exited {result.returncode} with no assistant "
                           f"turn: {result.stderr.strip()[:300]}")
    return result.stdout                            # clean, no tool call → graded miss


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure skill-description trigger rates.")
    ap.add_argument("--eval-file", required=True,
                    help='JSON: {"<skill>": ["query", ...], ...}')
    ap.add_argument("--skills", default="",
                    help="comma-separated subset of skills to probe (default: all in file)")
    ap.add_argument("--samples", type=int, default=3,
                    help="probes per query (trigger behavior is stochastic; the "
                         "default 3 matches the upstream eval — samples=1 is too "
                         "noisy to act on)")
    ap.add_argument("--model", default=None,
                    help="model override for probes (default: claude CLI default). "
                         "NB: trigger behavior is model-dependent — compare like with like.")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", default=".aris/meta/trigger_report.json")
    args = ap.parse_args(argv)

    try:
        evals = json.loads(Path(args.eval_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read eval file: {e}", file=sys.stderr)
        return 2
    subset = {s.strip() for s in args.skills.split(",") if s.strip()}
    targets = {k: v for k, v in evals.items()
               if (not subset or k in subset) and not k.startswith("_")}
    if not targets:
        print("ERROR: no skills selected", file=sys.stderr)
        return 2

    records = []
    # Neutral cwd: no project-level .claude/, so probes see exactly the
    # user-level installed corpus — the realistic long list.
    with tempfile.TemporaryDirectory(prefix="trigger-eval-") as neutral_cwd:
        for skill, queries in targets.items():
            for query in queries:
                for _ in range(args.samples):
                    try:
                        stream = run_probe(query, args.model, args.timeout, neutral_cwd)
                        outcome, detail = classify(parse_stream_tool_uses(stream), skill)
                    except (RuntimeError, subprocess.TimeoutExpired) as e:
                        outcome, detail = "error", str(e)[:200]
                    records.append({"skill": skill, "query": query,
                                    "outcome": outcome, "detail": detail})
                    print(f"  [{outcome:9}] {skill} ← {query[:60]!r}"
                          + (f" → {detail}" if outcome == "confusion" else ""))

    summary = aggregate(records)
    report = {"model": args.model or "cli-default", "samples": args.samples,
              "skills": summary, "records": records}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nskill                          rate   probes  confusions")
    for name, s in sorted(summary.items()):
        conf = ", ".join(f"{k}×{v}" for k, v in
                         sorted(s["confusions"].items(), key=lambda kv: -kv[1])) or "-"
        rate = "n/a " if s["trigger_rate"] is None else f"{s['trigger_rate']:.2f}"
        print(f"{name:30} {rate}   {s['probes']:4}    {conf}")
    print(f"\nreport → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
