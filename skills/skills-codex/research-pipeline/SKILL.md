---
name: "research-pipeline"
description: "Full research pipeline: Workflow 1 (idea discovery) \u2192 implementation \u2192 Workflow 2 (auto review loop). Goes from a broad research direction all the way to a submission-ready paper. Use when user says \\\"\u5168\u6d41\u7a0b\\\", \\\"full pipeline\\\", \\\"\u4ece\u627eidea\u5230\u6295\u7a3f\\\", \\\"end-to-end research\\\", or wants the complete autonomous research lifecycle."
---

# Full Research Pipeline: Idea → Experiments → Submission

End-to-end autonomous research workflow for: **$ARGUMENTS**

## Constants

- **AUTO_PROCEED = true** — When `true`, Gate 1 auto-selects the top-ranked idea (highest pilot signal + novelty confirmed) and continues to implementation. When `false`, always waits for explicit user confirmation before proceeding.
- **ARXIV_DOWNLOAD = false** — When `true`, `/research-lit` downloads the top relevant arXiv PDFs during literature survey. When `false` (default), only fetches metadata via arXiv API. Passed through to `/idea-discovery` → `/research-lit`.
- **HUMAN_CHECKPOINT = false** — When `true`, the auto-review loops (Stage 4) pause after each round's review to let you see the score and provide custom modification instructions before fixes are implemented. When `false` (default), loops run fully autonomously. Passed through to `/auto-review-loop`.
- **REVIEWER_DIFFICULTY = medium** — Passed through to `/auto-review-loop`. `medium` uses Codex xhigh review; `hard` adds Reviewer Memory and Debate Protocol; `nightmare` adds direct repository-reading adversarial verification.
- **AUTO_WRITE = false** — When `true`, automatically invoke Workflow 3 (`/paper-writing`) after Stage 5. Requires `VENUE` to be set. When `false` (default), Stage 5 generates `NARRATIVE_REPORT.md` and stops so the user can invoke `/paper-writing` manually.
- **VENUE = ICLR** — Target venue for paper writing when `AUTO_WRITE=true`. Options: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_CONF`, `IEEE_JOURNAL`.

> 💡 Override via argument, e.g., `/research-pipeline "topic" — AUTO_PROCEED: false, human checkpoint: true, difficulty: nightmare, auto_write: true, venue: NeurIPS`.

## Overview

This skill chains the entire research lifecycle into a single pipeline:

```
/idea-discovery → implement → /run-experiment → /auto-review-loop → /paper-writing (optional)
├── Workflow 1 ──┤            ├────────── Workflow 2 ──────────────┤ ├── Workflow 3 ──┤
```

It orchestrates up to three major workflows plus the implementation bridge between them. Workflow 3 is optional and controlled by `AUTO_WRITE`.

## Pipeline

### Stage 1: Idea Discovery (Workflow 1)

If `RESEARCH_BRIEF.md` exists in the project root, it will be loaded by `/idea-discovery` as detailed context and used as the primary brief for the pipeline. The one-line `$ARGUMENTS` still sets the high-level direction.

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
- **Approve an idea** → proceed to Stage 2.
- **Pick a different idea** → proceed with their choice.
- **Request changes** (e.g., "combine Idea 1 and 3", "focus more on X") → update the idea prompt with user feedback, re-run `/idea-discovery` with refined constraints, and present again.
- **Reject all ideas** → collect feedback on what's missing, re-run Stage 1 with adjusted research direction. Repeat until the user commits to an idea.
- **Stop here** → save current state to `idea-stage/IDEA_REPORT.md` for future reference.

**If AUTO_PROCEED=true:** Present the top ideas, wait 10 seconds for user input. If no response, auto-select the #1 ranked idea (highest pilot signal + novelty confirmed) and proceed to Stage 2. Log: `"AUTO_PROCEED: selected Idea 1 — [title]"`.

> ⚠️ **This gate waits for user confirmation when AUTO_PROCEED=false.** When `true`, it auto-selects the top idea after presenting results. The rest of the pipeline (Stages 2-4) is expensive (GPU time + multiple review rounds), so set `AUTO_PROCEED=false` if you want to manually choose which idea to pursue.

### Stage 2: Implementation

Once the user confirms which idea to pursue:

1. **Read the idea details** from `idea-stage/IDEA_REPORT.md` (hypothesis, experimental design, pilot code) *(fall back to `./IDEA_REPORT.md` if not found)*

2. **Implement the full experiment**:
   - Extend pilot code to full scale (multi-seed, full dataset, proper baselines)
   - Add proper evaluation metrics and logging (wandb if configured)
   - Write clean, reproducible experiment scripts
   - Follow existing codebase conventions

3. **Code review**: Before deploying, do a self-review:
   - Are all hyperparameters configurable via argparse?
   - Is the random seed fixed and controllable?
   - Are results saved to JSON/CSV for later analysis?
   - Is there proper logging for debugging?

### Stage 3: Deploy Experiments (Workflow 2 — Part 1)

Deploy the full-scale experiments. Route by job count:

**Small batch (≤5 jobs)** — direct deployment:
```
/run-experiment [experiment command]
```

**Large batch (≥10 jobs, multi-seed sweeps, teacher→student chains)** — queue scheduler:
```
/experiment-queue [grid spec or manifest]
```

`experiment-bridge` auto-routes based on milestone job count. For pipeline runs with multi-seed sweeps from the start, allow an explicit `batch: queue` override to force `/experiment-queue` for all milestones.

**What this does:**
- Check GPU availability on configured servers
- Sync code to remote server
- Launch experiments in screen sessions with proper CUDA_VISIBLE_DEVICES
- For `/experiment-queue`: also OOM retry, stale-screen cleanup, phase dependencies, and crash-safe state
- Verify experiments started successfully

**Monitor progress:**

```
/monitor-experiment [server]
```

Wait for experiments to complete. Collect results.

### Stage 4: Auto Review Loop (Workflow 2 — Part 2)

Once initial results are in, start the autonomous improvement loop:

```
/auto-review-loop "$ARGUMENTS — [chosen idea title]"
```

Pass `REVIEWER_DIFFICULTY` through unchanged. For `hard` and `nightmare`, the downstream loop must preserve Reviewer Memory, Debate Protocol, Review Tracing, and any saved reviewer `agent_id` across rounds.

**What this does (up to 4 rounds):**
1. GPT-5.4 xhigh reviews the work (score, weaknesses, minimum fixes)
2. Codex implements fixes (code changes, new experiments, reframing)
3. Deploy fixes, collect new results
4. Re-review → repeat until score ≥ 6/10 or 4 rounds reached

**Output:** `review-stage/AUTO_REVIEW.md` with full review history and final assessment.

### Stage 5: Research Summary & Writing Handoff

After the auto-review loop completes, prepare the handoff for paper writing.

**Step 1:** Write the final research status report.

**Step 2:** Generate `NARRATIVE_REPORT.md` from:
- `idea-stage/IDEA_REPORT.md` (chosen idea, hypothesis, novelty justification)
- implementation details from the repo
- experiment configs and final results
- `review-stage/AUTO_REVIEW.md` (review history, weaknesses fixed, remaining limitations)

The narrative report must contain:
- problem statement and core claim
- method summary
- key quantitative results with evidence for each claim
- figure/table inventory (which exist, which need manual creation)
- limitations and remaining follow-up items

**Output:** `NARRATIVE_REPORT.md` + research pipeline report.

```markdown
# Research Pipeline Report

**Direction**: $ARGUMENTS
**Chosen Idea**: [title]
**Date**: [start] → [end]
**Pipeline**: idea-discovery → implement → run-experiment → auto-review-loop

## Journey Summary
- Ideas generated: X → filtered to Y → piloted Z → chose 1
- Implementation: [brief description of what was built]
- Experiments: [number of GPU experiments, total compute time]
- Review rounds: N/4, final score: X/10

## Writing Handoff
- NARRATIVE_REPORT.md: generated
- Venue: [VENUE or "not set — run /paper-writing manually"]
- Manual figures needed: [list or "none"]

## Remaining TODOs (if any)
- [items flagged by reviewer that weren't addressed]
```

### Stage 6: Paper Writing (Workflow 3 — Optional)

Skip this stage if `AUTO_WRITE=false` (default). Present the manual command:

```
/paper-writing "NARRATIVE_REPORT.md" — venue: ICLR
```

If `AUTO_WRITE=true`, stop and ask if `VENUE` is missing. Do not silently use a default venue. If manual figures are required, pause and list them before invoking paper writing.

When ready, invoke:

```
/paper-writing "NARRATIVE_REPORT.md" — venue: $VENUE
```

Workflow 3 handles its own phases: `/paper-plan → /paper-figure → /paper-write → /paper-compile → /auto-paper-improvement-loop`. When it finishes, update the pipeline report with final PDF path, improvement scores, and remaining issues.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Human checkpoint after Stage 1 is controlled by AUTO_PROCEED.** When `false`, do not proceed without user confirmation. When `true`, auto-select the top idea after presenting results.
- **Stages 2-4 can run autonomously** once the user confirms the idea. This is the "sleep and wake up to results" part.
- **If Stage 4 ends at round 4 without positive assessment**, stop and report remaining issues. Do not loop forever.
- **Budget awareness**: Track total GPU-hours across the pipeline. Flag if approaching user-defined limits.
- **Documentation**: Every stage updates its own output file. The full history should be self-contained.
- **Fail gracefully**: If any stage fails (no good ideas, experiments crash, review loop stuck), report clearly and suggest alternatives rather than forcing forward.

## Typical Timeline

| Stage | Duration | Can sleep? |
|-------|----------|------------|
| 1. Idea Discovery | 30-60 min | Yes if AUTO_PROCEED=true |
| 2. Implementation | 15-60 min | Yes (autonomous after Gate 1) |
| 3. Deploy | 5 min + experiment time | Yes ✅ |
| 4. Auto Review | 1-4 hours (depends on experiments) | Yes ✅ |

**Sweet spot**: Run Stage 1-2 in the evening, launch Stage 3-4 before bed, wake up to a reviewed paper.
