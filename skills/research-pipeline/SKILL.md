---
name: research-pipeline
description: "Full research pipeline: Workflow 1 (idea discovery) → Workflow 1.5 (experiment bridge) → Workflow 2 (auto review loop) → Workflow 3 (paper writing, optional). Goes from a broad research direction all the way to a polished PDF. Use when user says \"全流程\", \"full pipeline\", \"从找idea到投稿\", \"end-to-end research\", or wants the complete autonomous research lifecycle."
argument-hint: [research-direction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Full Research Pipeline: Idea → Experiments → Submission

End-to-end autonomous research workflow for: **$ARGUMENTS**

## Constants

- **AUTO_PROCEED = true** — When `true`, Gate 1 auto-selects the top-ranked idea (highest pilot signal + novelty confirmed) and continues to implementation. When `false`, always waits for explicit user confirmation before proceeding.
- **ARXIV_DOWNLOAD = false** — When `true`, `/research-lit` downloads the top relevant arXiv PDFs during literature survey. When `false` (default), only fetches metadata via arXiv API. Passed through to `/idea-discovery` → `/research-lit`.
- **HUMAN_CHECKPOINT = false** — When `true`, the auto-review loops (Stage 3) pause after each round's review to let you see the score and provide custom modification instructions before fixes are implemented. When `false` (default), loops run fully autonomously. Passed through to `/auto-review-loop`.
- **REVIEWER_DIFFICULTY = medium** — How adversarial the reviewer is. `medium` (default): standard MCP review. `hard`: adds reviewer memory + debate protocol. `nightmare`: GPT reads repo directly via `codex exec` + memory + debate. Passed through to `/auto-review-loop`.
- **CODE_REVIEW = true** — GPT-5.4 xhigh reviews experiment code before deployment. Catches logic bugs before wasting GPU hours. Set `false` to skip. Passed through to `/experiment-bridge`.
- **BASE_REPO = false** — GitHub repo URL to use as base codebase. When set, `/experiment-bridge` clones the repo first and implements experiments on top of it. When `false` (default), writes code from scratch or reuses existing project files. Passed through to `/experiment-bridge`.
- **COMPACT = false** — When `true`, generates compact summary files for short-context models and session recovery. Passed through to `/idea-discovery` and `/experiment-bridge`.
- **AUTO_WRITE = false** — When `true`, automatically invoke Workflow 3 (`/paper-writing`) after Stage 4. Requires `VENUE` to be set. When `false` (default), Stage 4 generates `NARRATIVE_REPORT.md` and stops — user invokes `/paper-writing` manually.
- **VENUE = ICLR** — Target venue for paper writing (Stage 5). Only used when `AUTO_WRITE=true`. Options: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_CONF`, `IEEE_JOURNAL`.
- **RENDER_HTML = true** — When `true` (default), auto-render `NARRATIVE_REPORT.md` to HTML at Stage 4 completion via `/render-html`. Uses `--no-review` (this is an internal handoff doc to `/paper-writing`, not a reviewer-facing final artifact — the upstream Stage 3 auto-review loop already cross-model-reviewed the claims). Set `false` to skip, or pass `— render html: false`. **Non-blocking**: if `/render-html` fails or Codex MCP is unavailable, log the failure and continue — the HTML view is a nice-to-have, not a Stage 4 prerequisite.

> 💡 Override via argument, e.g., `/research-pipeline "topic" — AUTO_PROCEED: false, human checkpoint: true, difficulty: nightmare, code review: false, base repo: https://github.com/org/project, auto_write: true, venue: NeurIPS`.

## Overview

This skill chains the entire research lifecycle into a single pipeline:

```
/idea-discovery → /experiment-bridge → /auto-review-loop → /paper-writing (optional)
├── Workflow 1 ──┤├── Workflow 1.5 ──┤├── Workflow 2 ───┤ ├── Workflow 3 ──┤
```

It orchestrates up to four major workflows in sequence. Workflow 3 (paper writing) is optional and controlled by `AUTO_WRITE`.

## Pipeline

### Stage 1: Idea Discovery (Workflow 1)

If `RESEARCH_BRIEF.md` exists in the project root, it will be automatically loaded as detailed context (replaces one-line prompt). See `templates/RESEARCH_BRIEF_TEMPLATE.md`.

Invoke the idea discovery pipeline:

```
/idea-discovery "$ARGUMENTS"
```

This internally runs: `/research-lit` → `/idea-creator` → `/novelty-check` → `/research-review`

**Output:** `idea-stage/IDEA_REPORT.md` with ranked, validated, pilot-tested ideas.

**🚦 Gate 1 — Human Checkpoint:**

After `idea-stage/IDEA_REPORT.md` is generated, **pause and present the top ideas to the user**:

```
📋 Idea Discovery complete. Top ideas:

1. [Idea 1 title] — Pilot: POSITIVE (+X%), Novelty: CONFIRMED
2. [Idea 2 title] — Pilot: WEAK POSITIVE (+Y%), Novelty: CONFIRMED
3. [Idea 3 title] — Pilot: NEGATIVE, eliminated

Recommended: Idea 1. Shall I proceed with implementation?
```

**If AUTO_PROCEED=false:** Wait for user confirmation before continuing. The user may:
- **Approve the idea** → proceed to Stage 2. `/experiment-bridge` reads `refine-logs/EXPERIMENT_PLAN.md` already generated by `/idea-discovery`.
- **Request changes** (e.g., "combine Idea 1 and 3", "focus more on X") → update the idea prompt with user feedback, re-run `/idea-discovery` with refined constraints, and present again.
- **Reject all ideas** → collect feedback on what's missing, re-run Stage 1 with adjusted research direction. Repeat until the user commits to an idea.
- **Stop here** → save current state to `idea-stage/IDEA_REPORT.md` for future reference.

**If AUTO_PROCEED=true:** Present the top ideas, wait 10 seconds for user input. If no response, auto-select the #1 ranked idea (highest pilot signal + novelty confirmed) and proceed to Stage 2. Log: `"AUTO_PROCEED: selected Idea 1 — [title]"`.

> ⚠️ **This gate waits for user confirmation when AUTO_PROCEED=false.** When `true`, it auto-proceeds after presenting results. The rest of the pipeline (Stages 2-3) is expensive (GPU time + multiple review rounds), so set `AUTO_PROCEED=false` if you want a final review checkpoint before committing GPU resources.

### Stage 2: Experiment Bridge (Workflow 1.5)

Once the user confirms which idea to pursue, delegate implementation and deployment to `/experiment-bridge`:

```
/experiment-bridge "$CHOSEN_IDEA_TITLE" — code review: $CODE_REVIEW, base repo: $BASE_REPO, compact: $COMPACT
```

> 💡 **Queue routing is automatic**: `/experiment-bridge` Phase 4 routes each milestone by job count — ≤5 jobs → `/run-experiment`, ≥10 jobs or teacher→student phase dependencies → `/experiment-queue` (with OOM retry, wave gating, crash-safe state). No manual override is needed.

**What this does (fully autonomous):**
1. Parses `refine-logs/EXPERIMENT_PLAN.md` — extracts milestones, run order, compute budget
2. Implements experiment code — extends pilot to full scale, follows existing codebase conventions
3. **Cross-model code review** — GPT-5.4 xhigh reviews the implementation for logic bugs, incorrect metrics, and ground-truth misuse before any GPU time is spent
4. **Sanity check** — runs the smallest experiment first to verify the environment; auto-debugs failures (up to 3 attempts, with `/codex:rescue` fallback)
5. Deploys full experiments — auto-routes by job count (≤5 → `/run-experiment`, ≥10 → `/experiment-queue` with OOM retry, wave gating, crash-safe state)
6. Collects initial results — parses outputs, updates `refine-logs/EXPERIMENT_TRACKER.md`, runs `/training-check` if W&B is configured
7. Auto-plans ablations via `/ablation-planner` if main results are positive

**Output:**
- `refine-logs/EXPERIMENT_RESULTS.md` — structured results by milestone
- `refine-logs/EXPERIMENT_TRACKER.md` — updated run-by-run status
- `EXPERIMENT_LOG.md` (when `COMPACT=true`) — session-recovery-friendly log

**Monitor progress** (while experiments run):

```
/monitor-experiment [server]
```

Wait for `/experiment-bridge` to complete and report its handoff summary before proceeding.

### Stage 3: Auto Review Loop (Workflow 2)

Once initial results are in, start the autonomous improvement loop:

```
/auto-review-loop "$ARGUMENTS — [chosen idea title], difficulty: $REVIEWER_DIFFICULTY"
```

**What this does (up to 4 rounds):**
1. GPT-5.4 xhigh reviews the work (score, weaknesses, minimum fixes)
2. Claude Code implements fixes (code changes, new experiments, reframing)
3. Deploy fixes, collect new results
4. Re-review → repeat until score ≥ 6/10 or 4 rounds reached

**Output:** `review-stage/AUTO_REVIEW.md` with full review history and final assessment.

### Stage 4: Research Summary & Writing Handoff

After the auto-review loop completes, prepare the handoff for paper writing.

**Step 1:** Write a final research status report (same as before).

**Step 2:** Generate `NARRATIVE_REPORT.md` from:
- `IDEA_REPORT.md` (chosen idea, hypothesis, novelty justification)
- Implementation details from the repo
- Experiment configs and final results
- `AUTO_REVIEW.md` (review history, weaknesses fixed, remaining limitations)

The narrative report must contain:
- Problem statement and core claim
- Method summary
- Key quantitative results with evidence for each claim
- Figure/table inventory (which exist, which need manual creation)
- Limitations and remaining follow-up items

**Output:** `NARRATIVE_REPORT.md` + research pipeline report.

```markdown
# Research Pipeline Report

**Direction**: $ARGUMENTS
**Chosen Idea**: [title]
**Date**: [start] → [end]
**Pipeline**: idea-discovery → experiment-bridge → auto-review-loop

## Journey Summary
- Ideas generated: X → filtered to Y → piloted Z → chose 1
- Implementation: [brief description of what was built]
- Experiments: [number of GPU experiments, total compute time]
- Review rounds: N/4, final score: X/10

## Writing Handoff
- NARRATIVE_REPORT.md: ✅ generated
- Venue: [VENUE or "not set — run /paper-writing manually"]
- Manual figures needed: [list or "none"]

## Remaining TODOs (if any)
- [items flagged by reviewer that weren't addressed]
```

### Stage 5: Paper Writing (Workflow 3 — Optional)

**Skip this stage if `AUTO_WRITE=false` (default).** Present the `/paper-writing` command for manual use:

```
📝 Research complete. To write the paper:
/paper-writing "NARRATIVE_REPORT.md" — venue: ICLR
```

**If `AUTO_WRITE=true`:**

🚦 **Gate 2 — Writing Checkpoint:**

```
📝 Research pipeline complete. Ready for Workflow 3.

- Venue: [VENUE]
- Input: NARRATIVE_REPORT.md
- Manual figures required: [list or none]
- Next step: /paper-writing "NARRATIVE_REPORT.md — venue: [VENUE]"

Proceeding with paper writing...
```

Checks before proceeding:
- If `VENUE` is missing → stop and ask. Do NOT silently use a default venue.
- If manual figures are required → pause and list them. Wait for user to add them.

Then invoke:

```
/paper-writing "NARRATIVE_REPORT.md" — venue: $VENUE
```

This delegates to Workflow 3 which handles its own phases:
`/paper-plan → /paper-figure → /paper-write → /paper-compile → /auto-paper-improvement-loop`

When Workflow 3 finishes, update the pipeline report with:
- Paper writing completion status
- Final PDF path (`paper/main.pdf`)
- Improvement scores (round 0 → round N)
- Remaining issues

**Output:** `paper/` directory with LaTeX source, compiled PDF, and `PAPER_IMPROVEMENT_LOG.md`.

## Render HTML view (auto, when `RENDER_HTML = true`)

After Stage 4 finalizes `NARRATIVE_REPORT.md` (before paper writing branches), invoke `/render-html` on the narrative report:

```
/render-html "NARRATIVE_REPORT.md" --no-review
```

`--no-review` is intentional: this is an internal handoff doc, not reviewer-facing — the claims it summarizes were already cross-model-reviewed in Stage 3's `/auto-review-loop`. Output: `NARRATIVE_REPORT.html` next to the MD, with embedded source SHA256.

**Non-blocking**: if `/render-html` fails (helper missing, file write error, etc.), log the failure and continue Stage 4 — the HTML view is a convenience artifact, not a pipeline prerequisite.

Skip this step if `RENDER_HTML = false`.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Human checkpoint after Stage 1 is controlled by AUTO_PROCEED.** When `false`, do not proceed without user confirmation. When `true`, auto-select the top idea after presenting results.
- **Stages 2-3 can run autonomously** once the user confirms the idea. This is the "sleep and wake up to results" part.
- **If Stage 3 ends at round 4 without positive assessment**, stop and report remaining issues. Do not loop forever.
- **Budget awareness**: Track total GPU-hours across the pipeline. Flag if approaching user-defined limits.
- **Documentation**: Every stage updates its own output file. The full history should be self-contained.
- **Fail gracefully**: If any stage fails (no good ideas, experiments crash, review loop stuck), report clearly and suggest alternatives rather than forcing forward.

## Typical Timeline

| Stage | Duration | Can sleep? |
|-------|----------|------------|
| 1. Idea Discovery | 30-60 min | Yes if AUTO_PROCEED=true |
| 2. Experiment Bridge | 30-120 min (implement + review + deploy + collect) | Yes ✅ |
| 3. Auto Review | 1-4 hours (depends on experiments) | Yes ✅ |

**Sweet spot**: Run Stage 1 in the evening, launch Stage 2-3 before bed, wake up to a reviewed paper.
