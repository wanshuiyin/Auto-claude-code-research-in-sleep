---
name: "idea-discovery"
description: "Workflow 1: Full idea discovery pipeline to go from a broad research direction to validated, pilot-tested ideas. Use when user says \"找idea全流程\", \"idea discovery pipeline\", \"从零开始找方向\", or wants the complete idea exploration workflow."
---

# Workflow 1: Idea Discovery Pipeline

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
- **REVIEWER_MODEL = `gpt-5.6-sol`** — Model used via a secondary Codex agent. Must be an OpenAI model (e.g., `gpt-5.6-sol`, `o3`, `gpt-4o`). Passed to sub-skills.
- **ARXIV_DOWNLOAD = false** — When `true`, `/research-lit` downloads the top relevant arXiv PDFs during Phase 1. When `false` (default), only fetches metadata. Passed through to `/research-lit`.
- **COMPACT = false** — When `true`, generate compact summary files for short-context sessions and downstream skills. Writes `idea-stage/IDEA_CANDIDATES.md`.
- **OUTPUT_DIR = `idea-stage/`** — All idea-stage outputs go here. Create the directory if it doesn't exist.
- **REF_PAPER = false** — Reference paper to base ideas on. Accepts a local PDF path, arXiv URL, or paper URL. When set, summarize it first and use it as idea-generation context.
- **RENDER_HTML = true** — When `true` (default), auto-render `idea-stage/IDEA_REPORT.md` to HTML at workflow end via `/render-html`. Uses `--no-review` because the source already received novelty + same-family provisional review. Set `false` to skip.
- **RESUMABLE = true** — Record stage evidence under `.aris/runs/<run_id>.json` and require a deterministic evidence gate before declaring the final report complete.

> 💡 These are defaults. Override by telling the skill, e.g., `/idea-discovery "topic" — ref paper: https://arxiv.org/abs/2406.04329` or `/idea-discovery "topic" — compact: true`.

## Checkpoint execution rule

Resolve `AUTO_PROCEED` once from `$ARGUMENTS` before Phase 0 and keep that mode
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

## Per-stage evidence gate (`RESUMABLE = true`)

Resolve `run_state.py` and `idea_discovery_gate.py` from the Codex manifest
using the same resolver pattern as `/research-pipeline`. If either helper is
unavailable, the final report is `BLOCKED`; do not silently continue without a
state record.

For a new run, derive `<run_id>` from the direction slug and date, then start
this ordered state record with `--executor <actual-Codex-model>
--provisional-advances` (for example, `codex-gpt-5.6-sol`):

```text
research-lit,idea-creator,novelty-check,research-review,research-refine-pipeline
```

For each phase, mark `running` on entry and `done --artifact <path>` only after
its artifact is present. Use these artifact locators so the final gate can
check the canonical report rather than scattered scratch files:

| Phase | Artifact locator |
|---|---|
| `research-lit` | `idea-stage/IDEA_REPORT.md#literature-landscape` |
| `idea-creator` | `idea-stage/IDEA_REPORT.md#ranked-ideas` |
| `novelty-check` | `idea-stage/IDEA_REPORT.md#novelty-verification` |
| `research-review` | `idea-stage/IDEA_REPORT.md#external-critical-review` |
| `research-refine-pipeline` | `refine-logs/FINAL_PROPOSAL.md` |

`novelty-check` and `research-review` are **reviewer-bearing phases**. A
`done` status or a heading alone is not review evidence. After each phase has
folded substantive findings into its anchored report section, first record it
`done`, then, only after the secondary Codex reviewer actually returns a
positive, identity-bearing verdict, record its honest same-family receipt using the
actual reviewer model and durable agent/trace id:

```text
python3 <resolved-run_state.py> mark-provisional . <run_id> novelty-check --verdict-id "<agent-or-trace-id>" --reviewer "<actual-Codex-reviewer-model>"
python3 <resolved-run_state.py> mark-provisional . <run_id> research-review --verdict-id "<agent-or-trace-id>" --reviewer "<actual-Codex-reviewer-model>"
```

Never invent either value and never mark a phase provisional without the
positive verdict required by the run-state contract. For `novelty-check`,
**both PROCEED and PROCEED WITH CAUTION are positive verdicts** — caution is
guidance for the pilot, not a rejection; only ABANDON is negative. A negative verdict does not grant a review receipt.
Leave the phase `done` and the final gate `BLOCKED`,
select a surviving or new idea, then re-run that reviewer-bearing phase. Do the
same if the reviewer is unavailable, returns no valid identity/response, or its
output was not folded into the report. `--provisional-advances` is required
because these same-family receipts are explicitly provisional, not
cross-family acceptance.

If a reviewer overlay actually returns a recognized **different-family** model
(for example Claude reviewing a Codex run), use `accept` with that overlay's
real model and trace id instead. Do not mislabel a cross-family receipt as
provisional; the evidence gate validates either honest route from the recorded
families.

At the end of Phase 5, run:

```text
python3 <resolved-idea_discovery_gate.py> . <run_id> --report idea-stage/IDEA_REPORT.md
```

The gate writes its result to `gates.idea-discovery-evidence` in the run state.
On `PASS`, it has validated (but never created) the two review receipts, all
required artifacts, and non-empty anchored report sections. Per-phase
acceptance or provisional status stays with the reviewer route that produced
the receipt. On a non-zero exit, the gate writes explicit
`BLOCKED: <stage> evidence missing` lines to the report; do not present the
workflow as complete. On `— resume <run_id>`, start from the first non-terminal
phase and re-run the gate before finalizing.

## Pipeline

### Phase 0: Load Research Brief (if available)

Before starting any other phase, check for a detailed research brief in the project:

1. Look for `RESEARCH_BRIEF.md` in the project root or a path passed in `$ARGUMENTS`.
2. If found, read it and extract:
   - problem statement and context
   - constraints: compute, data, timeline, venue
   - what the user already tried and what did not work
   - domain knowledge and non-goals
   - existing results, if any
3. Use this as the primary context for all subsequent phases; it replaces the one-line prompt when more specific.
4. If both `RESEARCH_BRIEF.md` and one-line `$ARGUMENTS` exist, merge them: the brief has priority for details, and the argument sets the direction.

If no brief exists, proceed normally with `$ARGUMENTS` as the research direction.

Recommended template:

```markdown
# Research Brief

## Problem Statement
[What problem are we trying to solve?]

## Context
[Relevant field, current approach, why this matters]

## Constraints
- Compute:
- Data:
- Timeline:
- Target venue:

## What We Already Tried
- [attempt] -> [outcome]

## Non-Goals
- [what not to pursue]
```

### Phase 0.5: Reference Paper Summary (when REF_PAPER is set)

**Skip entirely if `REF_PAPER` is `false`.**

Summarize the reference paper before searching the literature:

1. **If arXiv URL** — invoke `/arxiv "ARXIV_ID" — download` to fetch the PDF, then read the first 5 pages.
2. **If local PDF path** — read the PDF directly, focusing on the title, abstract, introduction, and method overview.
3. **If other URL** — fetch the content and extract the method, results, and limitations.
4. **Generate `idea-stage/REF_PAPER_SUMMARY.md`** using this template:

```markdown
# Reference Paper Summary

## What They Did
[2-3 sentences: core method and contribution]

## Key Results
[Main quantitative findings]

## Limitations & Open Questions
[Acknowledged weaknesses, missing experiments, future work]

## Potential Improvement Directions
[Concrete ways to extend, challenge, or improve the paper]

## Codebase
[If `base repo` is set: link to the repo and identify relevant entry points]
```

Use `idea-stage/REF_PAPER_SUMMARY.md` as additional context in both Phase 1 and Phase 2.

### Phase 1: Literature Survey

Invoke `/research-lit` to map the research landscape:

```
/research-lit "$ARGUMENTS" — composed: idea-stage/IDEA_REPORT.md
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

Invoke `/idea-creator` with the landscape context and `idea-stage/REF_PAPER_SUMMARY.md` if available:

```
/idea-creator "$ARGUMENTS" — composed: idea-stage/IDEA_REPORT.md
```

**What this does:**
- If `idea-stage/REF_PAPER_SUMMARY.md` exists, include it as context so ideas explicitly build on, improve, or extend the reference paper
- Brainstorm 8-12 concrete ideas via GPT-5.6-Sol xhigh
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
- Cross-verify with GPT-5.6-Sol xhigh
- Check for concurrent work (last 3-6 months)
- Identify closest existing work and differentiation points

**Update `idea-stage/IDEA_REPORT.md`** with deep novelty results. Eliminate any idea that turns out to be already published.

### Phase 4: External Critical Review

For the surviving top idea(s), get a sharp outside read — strongest case, named risks, and the cheapest discriminating next experiment; the core hypothesis is not up for rewriting:

```
/research-review "[top idea with hypothesis + pilot results]" — composed: idea-stage/IDEA_REPORT.md
```

**What this does:**
- GPT-5.6-Sol xhigh acts as a senior reviewer (NeurIPS/ICML level)
- Scores the idea, identifies weaknesses, suggests minimum viable improvements
- Provides concrete feedback on experimental design

**Update `idea-stage/IDEA_REPORT.md`** with reviewer feedback and revised plan.

`idea-stage/IDEA_REPORT.md` is this pipeline's one canonical deliverable. The
explicit `— composed:` signal makes each sub-skill return/fold unique findings
instead of scattering `LIT_LANDSCAPE.md`, `RESEARCH_REVIEW.md`, or duplicate
manifests. Without that signal, every sub-skill remains standalone. See
[`output-composition.md`](../shared-references/output-composition.md).

### Phase 4.5: Method Refinement + Experiment Planning

After review, refine the top idea into a concrete proposal and plan experiments:

```
/research-refine-pipeline "[top idea description + pilot results + reviewer feedback]"
```

**What this does:**
- Freeze a **Problem Anchor** to prevent scope drift
- Refine the method via GPT-5.6-Sol review — reviewer risks choose the next tests, they do not add components; the score is advisory, and preserving the core hypothesis outranks pleasing the reviewer
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

## Novelty Verification
[from Phase 3]

## External Critical Review
[from Phase 4]

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

Before presenting this report as complete, run the per-stage evidence gate
above. A `BLOCKED` gate result is part of the report, not a warning to omit.

### Phase 5.5: Write Compact Files (when COMPACT = true)

**Skip entirely if `COMPACT` is `false`.**

Write `idea-stage/IDEA_CANDIDATES.md` — a lean summary of the top 3-5 surviving ideas:

```markdown
# Idea Candidates

| # | Idea | Pilot Signal | Novelty | Reviewer Score | Status |
|---|------|-------------|---------|---------------|--------|
| 1 | [title] | +X% | Confirmed | X/10 | RECOMMENDED |
| 2 | [title] | +Y% | Confirmed | X/10 | BACKUP |
| 3 | [title] | Negative | — | — | ELIMINATED |

## Active Idea: #1 — [title]
- Hypothesis: [one sentence]
- Key evidence: [pilot result]
- Next step: /experiment-bridge or /research-refine
```

### Phase 5.6: Instantiate the Research Contract (always — NOT gated on COMPACT)

When Phase 4 ends with a RECOMMENDED idea, create `idea-stage/docs/research_contract.md`
from `templates/RESEARCH_CONTRACT_TEMPLATE.md` (repo root or `$ARIS_REPO/templates/`),
filling in: the selected idea + selection rationale, core claims, minimum
convincing evidence, and the next-step pointer. Skip only when the run produced
no RECOMMENDED idea. `/experiment-bridge` implements against this contract;
`/result-to-claim` + `/ablation-planner` read it as the claims source; session
recovery reloads the ACTIVE idea from it instead of the full idea pool.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Render HTML view (auto, when `RENDER_HTML = true`)

After finalizing `idea-stage/IDEA_REPORT.md` (and the optional `IDEA_CANDIDATES.md`), invoke `/render-html` on the report so the user has a single-file HTML view for tablet / phone reading:

```
/render-html "idea-stage/IDEA_REPORT.md" --no-review
```

`--no-review` is intentional: source MD already received this skill's novelty + same-family provisional review. HTML render is a structural conversion, not a new claim-audit gate.

**Non-blocking**: if `/render-html` fails (helper missing, secondary Codex agent unavailable, file write error), log the failure and continue. Skip entirely if `RENDER_HTML = false`.

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
