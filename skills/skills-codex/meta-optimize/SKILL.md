---
name: meta-optimize
description: "Analyze ARIS usage logs and propose optimizations to SKILL.md files, reviewer prompts, and workflow defaults. Outer-loop harness optimization inspired by Meta-Harness (Lee et al., 2026). Use when user says \"优化技能\", \"meta optimize\", \"improve skills\", \"分析使用记录\", or wants to optimize ARIS's own harness components based on accumulated experience."
argument-hint: [target-skill-or-all]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# Meta-Optimize: Outer-Loop Harness Optimization for ARIS

Analyze accumulated usage logs and propose optimizations for: **$ARGUMENTS**

## Context

ARIS is a **research harness** — a system of skills, bridges, workflows, and artifact contracts that wraps around LLMs to orchestrate research. This skill implements a prototype **outer loop** that observes how the harness is used and proposes improvements to the harness itself (not to the research artifacts it produces).

Inspired by Meta-Harness (Lee et al., 2026): the key insight is that harness design matters as much as model weights, and harness engineering can be partially automated by logging execution traces and using them to guide improvements.

## What This Skill Optimizes (Harness Components)

| Component | Example | Optimizable? |
|-----------|---------|:---:|
| SKILL.md prompts | Reviewer instructions, quality gates, step descriptions | Yes |
| Default parameters | `difficulty: medium`, `MAX_ROUNDS: 4`, `threshold: 6/10` | Yes |
| Convergence rules | When to stop the review loop, retry counts | Yes |
| Workflow ordering | Skill chain sequence within a workflow | Yes |
| Artifact schemas | What fields go in EXPERIMENT_LOG.md, idea-stage/IDEA_REPORT.md | Cautious |
| MCP bridge config | Which reviewer model, routing rules | No (infra) |

**Not optimized**: The research artifacts themselves (papers, code, experiments). That's what the regular workflows do.

## Prerequisites

1. **Logging must be active.** Codex mirror installs do not create Claude Code hooks. Provide `.aris/meta/events.jsonl` from a Codex-compatible event logger, an external wrapper, or a manually exported trace log before running this skill.
2. **Sufficient data.** At least 5 complete workflow runs logged in `.aris/meta/events.jsonl`. The skill will check and warn if insufficient.

## Workflow

### Step 0: Check Data Availability

```bash
EVENTS_FILE=".aris/meta/events.jsonl"
if [ ! -f "$EVENTS_FILE" ]; then
    echo "ERROR: No event log found at $EVENTS_FILE"
    echo "Enable Codex-compatible logging first: create .aris/meta/events.jsonl from your Codex wrapper, external event logger, or exported trace log."
    exit 1
fi

EVENT_COUNT=$(wc -l < "$EVENTS_FILE")
SKILL_INVOCATIONS=$(grep -c '"skill_invoke"' "$EVENTS_FILE" || echo 0)
SESSIONS=$(grep -c '"session_start"' "$EVENTS_FILE" || echo 0)

echo "📊 Event log: $EVENT_COUNT events, $SKILL_INVOCATIONS skill invocations, $SESSIONS sessions"

if [ "$SKILL_INVOCATIONS" -lt 5 ]; then
    echo "⚠️  Insufficient data (<5 skill invocations). Continue using ARIS normally and re-run later."
    exit 0
fi
```

### Step 1: Analyze Usage Patterns

Read `.aris/meta/events.jsonl` and compute:

**Frequency analysis:**
- Which skills are invoked most often?
- Which slash commands do users type most?
- What parameter overrides are most common? (These suggest bad defaults.)

**Failure analysis:**
- Which tools fail most often? In which skills?
- What error patterns repeat? (OOM, import, compilation, timeout)
- How many auto-debug retries per workflow run?

**Convergence analysis (for auto-review-loop):**
- Average rounds to reach threshold
- Score trajectory shape (fast improvement? plateau? oscillation?)
- Which review round catches the most critical issues?
- Do users override difficulty mid-run?

**Human intervention analysis:**
- Where do users interrupt with manual prompts during workflows?
- What manual corrections do users make most? (These indicate skill gaps.)

**Model-delta analysis (harness diet):**
- Has the session model or the pinned reviewer model changed since a skill's
  SKILL.md was last touched? A model bump is a **trigger to re-read, not
  evidence by itself**: a deletion proposal must cite TARGET-SPECIFIC evidence
  (a capability-specific release note, or repeated post-bump event-log behavior
  showing the scaffold is unused). **Never deletion candidates**: privilege
  boundaries, acceptance/review gates, corpus/provenance rules, output
  contracts, safety checks. The diet targets model-compensation scaffolding
  only — a capability the new model has natively is pure overhead. A harness
  that only ever grows is a harness nobody is re-reading.

**Trigger-rate analysis (measured, not from the event log):** the log shows
which skills were USED, not which were WANTED-but-omitted. Mainline ships
`tools/meta_opt/trigger_eval.py`, which measures Claude Code's skill triggering
via `claude -p` probes (trigger / confusion / miss). It is Claude-Code-specific
— there is no equivalent `codex` skill-selection probe yet, so for a Codex
executor treat trigger-rate as a mainline signal, not a step you run here.
Measure-only regardless: a low rate is INPUT to a proposal, never a self-applied
rewrite; the confusion matrix (which sibling a query lands on) points at
disambiguation, not "make it pushier".

Present findings as a structured summary table.

### Step 1.5: Name the Current Bottleneck

Synthesize the Step-1 analyses into **one sentence naming the single
most-limiting pipeline stage right now** — e.g. "planning", "verification
quality", "experiment execution reliability", "writing polish" — with evidence.
The bottleneck always moves: coding → planning → verification → taste. Step 2's
ranked table should read as sub-fixes for this one named constraint.

Append the verdict to the append-only ledger `.aris/meta/bottleneck_log.jsonl`
(never edit or delete prior lines — succession history is the point):

```bash
mkdir -p .aris/meta
# json.dumps, NOT hand-interpolated shell strings: bottleneck/evidence are
# natural language — a stray quote must not break the JSONL (or the shell).
python3 - <<'PY'
import json, datetime
entry = {
    "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "cycle": 3,
    "bottleneck": "verification quality",
    "evidence": "review rounds plateau at 6/10 while tool failures are rare",
    "top_patch_ids": ["P1", "P2"],
}
with open(".aris/meta/bottleneck_log.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
```

On the next run, read the last line first and open the report by stating
whether that bottleneck was resolved and what it has moved to.

### Step 2: Identify Optimization Targets

Based on Step 1, rank optimization opportunities by expected impact:

```markdown
## Optimization Opportunities (ranked)

| # | Target | Signal | Proposed Change | Expected Impact |
|---|--------|--------|-----------------|-----------------|
| 1 | auto-review-loop default threshold | Users override to 7/10 in 60% of runs | Change default from 6/10 to 7/10 | Fewer manual overrides |
| 2 | experiment-bridge retry count | 40% of runs hit max retries on OOM | Add OOM-specific recovery (reduce batch size) | Fewer failed experiments |
| 3 | paper-write de-AI patterns | Users manually fix "delve" in 80% of runs | Add "delve" to default watchword list | Fewer manual edits |
| 4 | experiment-bridge Phase-2 hand-holding steps | Model bump; scaffold untouched for 2 generations; zero failures in the guarded steps | **DELETE steps N–M — the new model does this unprompted** | Smaller harness, less drift surface |
```

The Proposed-Change column is explicitly allowed to be a **deletion** — "DELETE
step N, new model does this for free" is a first-class optimization.

If `$ARGUMENTS` specifies a target skill, focus analysis on that skill only.
If `$ARGUMENTS` is empty or "all", analyze all skills with sufficient data.

### Step 3: Generate Patch Proposals

For each optimization target, generate a concrete diff:

```diff
--- a/skills/auto-review-loop/SKILL.md
+++ b/skills/auto-review-loop/SKILL.md
@@ -15,7 +15,7 @@
 ## Constants
 
-- **SCORE_THRESHOLD = 6** — Minimum review score to accept.
+- **SCORE_THRESHOLD = 7** — Minimum review score to accept. (Raised based on usage data: 60% of users overrode to 7+.)
```

**Rules for patch generation:**
- One patch per optimization target
- Each patch must include a comment explaining WHY (with data from the log)
- Patches must be minimal — change only what the data supports
- Never change artifact schemas or MCP bridge config in v1
- Never change behavior that would break existing user workflows

### Step 4: Cross-Model Review of Patches

Send each patch to GPT-5.5 xhigh for adversarial review:

```text
spawn_agent:
  model: gpt-5.5
  reasoning_effort: xhigh
  message: |
    You are reviewing a proposed optimization to an ARIS SKILL.md file.
    
    ## Original Skill (relevant section)
    [paste original]
    
    ## Proposed Patch
    [paste diff]
    
    ## Evidence from Usage Log
    [paste summary stats]
    
    Review this patch:
    1. Does the evidence support the change?
    2. Could this change hurt other use cases?
    3. Is the change minimal and safe?
    4. Score 1-10: should this be applied?
    
    If score < 7, explain what additional evidence would be needed.
```

### Step 5: Present Results

Output a structured report:

```markdown
# ARIS Meta-Optimization Report

**Date**: [today]
**Data**: [N] events, [M] skill invocations, [K] sessions
**Target**: [skill name or "all"]

## Current Bottleneck

**[one-phrase name]** — [one-line evidence]. Prior cycle's bottleneck: [name —
resolved by <patch ids> / unresolved / first recorded cycle]. (Ledger:
`.aris/meta/bottleneck_log.jsonl`)

## Proposed Changes

### Change 1: [title]
- **Target**: [skill/file:line]
- **Signal**: [what the data shows]
- **Patch**: [diff]
- **Reviewer Score**: [X/10]
- **Reviewer Notes**: [summary]
- **Status**: ✅ Recommended / ⚠️ Needs more data / ❌ Rejected

### Change 2: ...

## Changes NOT Made (insufficient evidence)
- [pattern observed but too few samples]

## Recommendations
- [ ] Apply Change 1 (reviewer approved)
- [ ] Collect more data for Change 3 (need N more runs)
- [ ] Consider manual review of Change 2

## Next Steps
Run `/meta-optimize apply 1` to apply a specific change, or
`/meta-optimize apply all` to apply all recommended changes.
```

### Step 6: Apply Changes (if user approves)

If user runs `/meta-optimize apply [N]`:
1. Back up original SKILL.md to `.aris/meta/backups/`
2. Apply the patch
3. Log the change to `.aris/meta/optimizations.jsonl`
4. Remind user to test the changed skill on their next run

**Never auto-apply without user approval.**

## Key Rules

- **Log-driven, not speculative.** Every proposed change must cite specific data from the event log. No "I think this would be better."
- **Minimal patches.** Change one thing at a time. Don't rewrite entire skills — the one sanctioned large edit is a scaffolding **deletion** backed by TARGET-SPECIFIC model-delta evidence (capability-specific release note, or repeated post-bump event-log behavior; a model-name change alone is never sufficient). Privilege boundaries, acceptance gates, corpus/provenance rules, output contracts, and safety checks are never deletion candidates. Deletions go through the same review + approval gates.
- **Reviewer-gated.** Every patch goes through cross-model review before recommendation.
- **Reversible.** Always back up before applying. Always log what changed.
- **User-approved.** Never auto-apply. Present, explain, let the user decide.
- **Honest about uncertainty.** If the data is insufficient, say so. Don't optimize on noise.
- **Portable.** Optimizations should improve the skill for all users, not just one user's style. If a change seems user-specific, flag it.

## Event Schema Reference

The log at `.aris/meta/events.jsonl` contains JSONL records with these shapes:

```jsonl
{"ts":"...","session":"...","event":"skill_invoke","skill":"auto-review-loop","args":"difficulty: hard"}
{"ts":"...","session":"...","event":"PostToolUse","tool":"Bash","input_summary":"pdflatex main.tex"}
{"ts":"...","session":"...","event":"spawn_agent","tool":"spawn_agent","input_summary":"review..."}
{"ts":"...","session":"...","event":"tool_failure","tool":"Bash","input_summary":"python train.py"}
{"ts":"...","session":"...","event":"slash_command","command":"/auto-review-loop","args":""}
{"ts":"...","session":"...","event":"user_prompt","prompt_preview":"change difficulty to hard"}
{"ts":"...","session":"...","event":"session_start","source":"startup","model":"claude-opus-4-6"}
{"ts":"...","session":"...","event":"session_end"}
```

## Triggering

This skill is NOT part of the standard W1→W1.5→W2→W3→W4 pipeline. It is a **maintenance workflow** with three trigger mechanisms:

1. **Passive logging** (always on): Claude Code hooks record events to `.aris/meta/events.jsonl` automatically during normal usage. Zero user effort.

2. **Automatic readiness check** (SessionEnd hook): When a Claude Code session ends, `check_ready.sh` counts skill invocations since the last `/meta-optimize` run. If ≥5 new invocations have accumulated, it prints a reminder:
   ```
   📊 ARIS has logged 8 skill runs since last optimization. Run /meta-optimize to check for improvement opportunities.
   ```
   This is a **suggestion only** — it does not auto-run optimization.

3. **Manual trigger**: User runs `/meta-optimize` when they see the reminder or whenever they want.

**After each `/meta-optimize` run**, the skill writes the current timestamp to `.aris/meta/.last_optimize` so the readiness check only counts new invocations.

## Acknowledgements

Inspired by [Meta-Harness](https://arxiv.org/abs/2603.28052) (Lee et al., 2026) — end-to-end optimization of model harnesses via filesystem-based experience access and agentic code search.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

## Review Tracing

After each reviewer agent call, save the trace following `shared-references/review-tracing.md` (Policy C — forensic; never silently skip). Use `save_trace.sh` (resolved per the chain in `shared-references/integration-contract.md` §2) or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
