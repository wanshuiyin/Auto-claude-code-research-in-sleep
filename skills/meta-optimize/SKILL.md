---
name: meta-optimize
description: "Analyze ARIS usage logs and propose optimizations to SKILL.md files, reviewer prompts, and workflow defaults. Outer-loop harness optimization inspired by Meta-Harness (Lee et al., 2026). Use when user says \"优化技能\", \"meta optimize\", \"improve skills\", \"分析使用记录\", or wants to optimize ARIS's own harness components based on accumulated experience."
argument-hint: [target-skill-or-all]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, mcp__codex__codex, mcp__codex__codex-reply
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
| Artifact schemas | What fields go in EXPERIMENT_LOG.md, IDEA_REPORT.md | Cautious |
| MCP bridge config | Which reviewer model, routing rules | No (infra) |

**Not optimized**: The research artifacts themselves (papers, code, experiments). That's what the regular workflows do.

## Prerequisites

1. **Logging must be active.** Copy `templates/claude-hooks/meta_logging.json` into your project's `.claude/settings.json` (or merge the hooks section).
2. **Sufficient data.** At least 5 complete workflow runs logged in `.aris/meta/events.jsonl`. The skill will check and warn if insufficient.

## Workflow

### Step 0: Check Data Availability

```bash
EVENTS_FILE=".aris/meta/events.jsonl"
if [ ! -f "$EVENTS_FILE" ]; then
    echo "ERROR: No event log found at $EVENTS_FILE"
    echo "Enable logging first: copy templates/claude-hooks/meta_logging.json into .claude/settings.json"
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

Present findings as a structured summary table.

### Step 2: Identify Optimization Targets

Based on Step 1, rank optimization opportunities by expected impact:

```markdown
## Optimization Opportunities (ranked)

| # | Target | Signal | Proposed Change | Expected Impact |
|---|--------|--------|-----------------|-----------------|
| 1 | auto-review-loop default threshold | Users override to 7/10 in 60% of runs | Change default from 6/10 to 7/10 | Fewer manual overrides |
| 2 | experiment-bridge retry count | 40% of runs hit max retries on OOM | Add OOM-specific recovery (reduce batch size) | Fewer failed experiments |
| 3 | paper-write de-AI patterns | Users manually fix "delve" in 80% of runs | Add "delve" to default watchword list | Fewer manual edits |
```

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

Send each patch to GPT-5.4 xhigh for adversarial review:

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
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
- **Minimal patches.** Change one thing at a time. Don't rewrite entire skills.
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
{"ts":"...","session":"...","event":"codex_call","tool":"mcp__codex__codex","input_summary":"review..."}
{"ts":"...","session":"...","event":"tool_failure","tool":"Bash","input_summary":"python train.py"}
{"ts":"...","session":"...","event":"slash_command","command":"/auto-review-loop","args":""}
{"ts":"...","session":"...","event":"user_prompt","prompt_preview":"change difficulty to hard"}
{"ts":"...","session":"...","event":"session_start","source":"startup","model":"claude-opus-4-6"}
{"ts":"...","session":"...","event":"session_end"}
```

## Triggering

This skill is NOT part of the standard W1→W1.5→W2→W3→W4 pipeline. It is a **maintenance workflow** invoked periodically:

- **Passive logging**: Hooks record events automatically (zero user effort)
- **Manual trigger**: User runs `/meta-optimize` when they want to check for improvements
- **Session-end hint**: After sufficient data accumulates (≥5 workflow runs), the system may suggest running `/meta-optimize`

## Acknowledgements

Inspired by [Meta-Harness](https://arxiv.org/abs/2603.28052) (Lee et al., 2026) — end-to-end optimization of model harnesses via filesystem-based experience access and agentic code search.
