---
name: "idea-discovery"
description: "Workflow 1: Full idea discovery pipeline. Orchestrates research-lit \u2192 idea-creator \u2192 novelty-check \u2192 research-review to go from a broad research direction to validated, pilot-tested ideas. Use when user says \\\"\u627eidea\u5168\u6d41\u7a0b\\\", \\\"idea discovery pipeline\\\", \\\"\u4ece\u96f6\u5f00\u59cb\u627e\u65b9\u5411\\\", or wants the complete idea exploration workflow."
---

> Override for Codex users who want **Gemini**, not a second Codex agent, to act as the reviewer. Install this package **after** `skills/skills-codex/*`.

# Workflow 1: Idea Discovery Pipeline

> **Gemini overlay assurance:** `review_independence: cross-family` and `acceptance_status: accepted`.

Orchestrate a complete idea discovery workflow for: **$ARGUMENTS**

## Overview

This skill chains sub-skills into a single automated pipeline:

```
/research-lit → /idea-creator → /novelty-check → /research-review → /research-refine-pipeline
  (survey)      (brainstorm)    (verify novel)    (critical feedback)  (refine method + plan experiments)
```

Each phase builds on the previous one's output. The final deliverables are a validated `idea-stage/IDEA_REPORT.md` with ranked ideas, plus a refined proposal (`refine-logs/FINAL_PROPOSAL.md`) and experiment plan (`refine-logs/EXPERIMENT_PLAN.md`) for the top idea.

## Constants

- **PILOT_MAX_HOURS = 2** — Skip any pilot experiment estimated to take > 2 hours per GPU. Flag as "needs manual pilot" in the report.
- **PILOT_TIMEOUT_HOURS = 3** — Hard timeout: kill any running pilot that exceeds 3 hours. Collect partial results if available.
- **MAX_PILOT_IDEAS = 3** — Run pilots for at most 3 top ideas in parallel. Additional ideas are validated on paper only.
- **MAX_TOTAL_GPU_HOURS = 8** — Total GPU budget across all pilots. If exceeded, skip remaining pilots and note in report.
- **AUTO_PROCEED = true** — When `true`, checkpoints are informational: report the selected option and continue in the same turn. Set to `false` to ask for explicit user confirmation and end the turn at each selection checkpoint.
- **OUTPUT_DIR = `idea-stage/`** — All idea-stage outputs go here. Create the directory if it doesn't exist.
- **REVIEWER_MODEL = `gemini-review`** — Gemini reviewer invoked through the local `gemini-review` MCP bridge. Passed to the reviewer-aware sub-skills installed by this overlay.
- **ARXIV_DOWNLOAD = false** — When `true`, `/research-lit` downloads the top relevant arXiv PDFs during Phase 1. When `false` (default), only fetches metadata. Passed through to `/research-lit`.

> 💡 These are defaults. Override by telling the skill, e.g., `/idea-discovery "topic" — pilot budget: 4h per idea, 20h total` or `/idea-discovery "topic" — arxiv download: true`.

## Checkpoint execution rule

Resolve `AUTO_PROCEED` once from `$ARGUMENTS` before Phase 1 and keep that mode
for the entire workflow.

- **`AUTO_PROCEED=true` is non-blocking.** A checkpoint is a progress update,
  not a question. State the result and the automatically selected next action,
  then continue executing in the **same turn**. Do not ask for confirmation,
  request user input, sleep, wait for silence, or end the turn at a checkpoint.
- **`AUTO_PROCEED=false` is blocking.** Present the options, ask the user, and
  end the turn. Resume only after an explicit reply.

Never implement auto-proceed as “ask, then continue if there is no response.”
Once a turn ends, silence cannot resume the workflow. The user can still
interrupt a non-blocking run at any time.

This rule governs only `AUTO_PROCEED`-controlled selection checkpoints. If the
user explicitly enables a Feishu **interactive** gate, that external approval
or reply is an intentional blocking exception; wait for that user-controlled
gate rather than treating it as a silence timeout. Feishu off/push-only modes
remain non-blocking under `AUTO_PROCEED=true`.

## Pipeline

### Phase 1: Literature Survey

Invoke `/research-lit` to map the research landscape:

```
/research-lit "$ARGUMENTS"
```

**What this does:**
- Search arXiv, Google Scholar, Semantic Scholar for recent papers
- Build a landscape map: sub-directions, approaches, open problems
- Identify structural gaps and recurring limitations
- Output a literature summary (saved to working notes)

**🚦 Checkpoint:** Present the landscape summary to the user.

**When `AUTO_PROCEED=true` (non-blocking):** report the selected direction and
continue immediately in the same turn, without a question:

```
📚 Literature survey complete. Here's what I found:
- [key findings, gaps, open problems]

AUTO_PROCEED: selected [top-ranked direction]. Continuing to Phase 2.
```

**When `AUTO_PROCEED=false` (blocking):** present the same findings, ask
`Does this match your understanding? Should I adjust the scope before generating ideas?`,
then end the turn.

- **User approves** → proceed to Phase 2 with the best direction.
- **User requests changes** (e.g., "focus more on X", "ignore Y", "too broad") → refine the search with updated queries, re-run `/research-lit` with adjusted scope, and present again. Repeat until the user is satisfied.

### Phase 2: Idea Generation + Filtering + Pilots

Invoke `/idea-creator` with the landscape context:

```
/idea-creator "$ARGUMENTS"
```

**What this does:**
- Brainstorm 8-12 concrete ideas via the Gemini-backed `/idea-creator` overlay
- Filter by feasibility, compute cost, quick novelty search
- Deep validate top ideas (full novelty check + devil's advocate)
- Run parallel pilot experiments on available GPUs (top 2-3 ideas)
- Rank by empirical signal
- Output `idea-stage/IDEA_REPORT.md`

**🚦 Checkpoint:** Present `idea-stage/IDEA_REPORT.md` ranked ideas to the user.

**When `AUTO_PROCEED=true` (non-blocking):** report the automatic selection and
continue immediately in the same turn, without a question:

```
💡 Generated X ideas, filtered to Y, piloted Z. Top results:

1. [Idea 1] — Pilot: POSITIVE (+X%)
2. [Idea 2] — Pilot: WEAK POSITIVE (+Y%)
3. [Idea 3] — Pilot: NEGATIVE, eliminated

AUTO_PROCEED: selected [top-ranked idea(s)]. Continuing to Phase 3.
```

**When `AUTO_PROCEED=false` (blocking):** present the same ranking, ask
`Which ideas should I validate further? Or should I regenerate with different constraints?`,
then end the turn.

- **User picks ideas** → proceed to Phase 3 with the selected ideas.
- **User unhappy with all ideas** → collect feedback ("what's missing?", "what direction do you prefer?"), update the prompt with user's constraints, and re-run Phase 2 (idea generation). Repeat until the user selects at least 1 idea.
- **User wants to adjust scope** → go back to Phase 1 with refined direction.

### Phase 3: Deep Novelty Verification

For each top idea (positive pilot signal), run a thorough novelty check:

```
/novelty-check "[top idea 1 description]"
/novelty-check "[top idea 2 description]"
```

**What this does:**
- Multi-source literature search (arXiv, Scholar, Semantic Scholar)
- Cross-verify with the Gemini-backed `/novelty-check` overlay
- Check for concurrent work (last 3-6 months)
- Identify closest existing work and differentiation points

**Update `idea-stage/IDEA_REPORT.md`** with deep novelty results. Eliminate any idea that turns out to be already published.

### Phase 4: External Critical Review

For the surviving top idea(s), get a sharp outside read — strongest case, named risks, and the cheapest discriminating next experiment; the core hypothesis is not up for rewriting:

```
/research-review "[top idea with hypothesis + pilot results]"
```

**What this does:**
- Gemini acts as a senior reviewer (NeurIPS/ICML level) via the local `gemini-review` MCP bridge
- Scores the idea, identifies weaknesses, suggests minimum viable improvements
- Provides concrete feedback on experimental design

**Update `idea-stage/IDEA_REPORT.md`** with reviewer feedback and revised plan.

### Phase 4.5: Method Refinement + Experiment Planning

After review, refine the top idea into a concrete proposal and plan experiments:

```
/research-refine-pipeline "[top idea description + pilot results + reviewer feedback]"
```

**What this does:**
- Freeze a **Problem Anchor** to prevent scope drift
- Refine the method via Gemini review — reviewer risks choose the next tests, they do not add components; the score is advisory, and preserving the core hypothesis outranks pleasing the reviewer
- Generate a claim-driven experiment roadmap with ablations, budgets, and run order
- Output: `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md`, `refine-logs/EXPERIMENT_TRACKER.md`

**🚦 Checkpoint:** Present the refined proposal summary.

**When `AUTO_PROCEED=true` (non-blocking):** report that the proposal was
selected and continue immediately in the same turn, without a question:

```
🔬 Method refined and experiment plan ready:
- Problem anchor: [anchored problem]
- Method thesis: [one sentence]
- Dominant contribution: [what's new]
- Must-run experiments: [N blocks]
- First 3 runs to launch: [list]

AUTO_PROCEED: accepted the top proposal. Continuing to Final Report.
```

**When `AUTO_PROCEED=false` (blocking):** present the same summary, ask
`Proceed to implementation? Or adjust the proposal?`, then end the turn.

- **User approves** → proceed to Final Report.
- **User requests changes** → pass feedback to `/research-refine` for another round.
- **Lite mode:** If the pilot was inconclusive, still produce the smallest discriminating next-experiment plan — a reviewer score alone never downgrades an idea.

### Phase 5: Final Report

Finalize `idea-stage/IDEA_REPORT.md` with all accumulated information:

```markdown
# Idea Discovery Report

**Direction**: $ARGUMENTS
**Date**: [today]
**Pipeline**: research-lit → idea-creator → novelty-check → research-review → research-refine-pipeline

## Executive Summary
[2-3 sentences: best idea, key evidence, recommended next step]

## Literature Landscape
[from Phase 1]

## Ranked Ideas
[from Phase 2, updated with Phase 3-4 results]

### 🏆 Idea 1: [title] — RECOMMENDED
- Pilot: POSITIVE (+X%)
- Novelty: CONFIRMED (closest: [paper], differentiation: [what's different])
- Reviewer score: X/10
- Next step: implement full experiment → /auto-review-loop

### Idea 2: [title] — BACKUP
...

## Eliminated Ideas
[ideas killed at each phase, with reasons]

## Refined Proposal
- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Tracker: `refine-logs/EXPERIMENT_TRACKER.md`

## Next Steps
- [ ] /run-experiment to deploy experiments from the plan
- [ ] /auto-review-loop to iterate until submission-ready
- [ ] Or invoke /research-pipeline for the complete end-to-end flow
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Don't skip phases.** Each phase filters and validates — skipping leads to wasted effort later.
- **Checkpoint between phases.** Briefly summarize what was found. With `AUTO_PROCEED=true`, state the selected next action and keep executing in the same turn; with `false`, ask and end the turn.
- **Let pilots kill, not vibes.** A cheap pilot that says no beats a month of implementation that says no — but the kill needs empirical signal or a named published paper, not taste. Talking yourself out of ideas on paper is how pipelines end up with nothing to run.
- **Empirical signal > theoretical appeal.** An idea with a positive pilot outranks a "sounds great" idea without evidence.
- **Document everything.** Dead ends are just as valuable as successes for future reference.
- **Be honest with the reviewer.** Include negative results and failed pilots in the review prompt.
- **Feishu notifications are optional.** If `~/.codex/feishu.json` exists, send `checkpoint` at each phase transition and `pipeline_done` at final report. If absent/off, skip silently.

## Composing with Workflow 2

After this pipeline produces a validated top idea:

```
/idea-discovery "direction"         ← you are here (Workflow 1, includes method refinement + experiment planning)
/run-experiment                     ← deploy experiments from the plan
/auto-review-loop "top idea"        ← Workflow 2: iterate until submission-ready

Or use /research-pipeline for the full end-to-end flow.
```
