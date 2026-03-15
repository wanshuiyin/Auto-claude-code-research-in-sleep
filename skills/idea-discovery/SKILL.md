---
name: idea-discovery
description: "Workflow 1: Full idea discovery pipeline. Orchestrates research-lit → idea-creator → novelty-check → research-review to go from a broad research direction to validated, pilot-tested ideas. Use when user says \"找idea全流程\", \"idea discovery pipeline\", \"从零开始找方向\", or wants the complete idea exploration workflow."
argument-hint: [research-direction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Workflow 1: Idea Discovery Pipeline

Orchestrate a complete idea discovery workflow for: **$ARGUMENTS**

## Overview

This skill chains four sub-skills into a single automated pipeline:

```
/research-lit → /idea-creator → /novelty-check → /research-review
  (survey)      (brainstorm)    (verify novel)    (critical feedback)
```

Each phase builds on the previous one's output. The final deliverable is a validated `IDEA_REPORT.md` with ranked ideas, pilot results, and a suggested execution plan.

## Constants

- **PILOT_MAX_HOURS = 2** — Skip any pilot experiment estimated to take > 2 hours per GPU. Flag as "needs manual pilot" in the report.
- **PILOT_TIMEOUT_HOURS = 3** — Hard timeout: kill any running pilot that exceeds 3 hours. Collect partial results if available.
- **MAX_PILOT_IDEAS = 3** — Run pilots for at most 3 top ideas in parallel. Additional ideas are validated on paper only.
- **MAX_TOTAL_GPU_HOURS = 8** — Total GPU budget across all pilots. If exceeded, skip remaining pilots and note in report.
- **AUTO_PROCEED = true** — If user doesn't respond at a checkpoint, automatically proceed with the best option after presenting results. Set to `false` to always wait for explicit user confirmation.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP. Must be an OpenAI model (e.g., `gpt-5.4`, `o3`, `gpt-4o`). Passed to sub-skills.
- **ARXIV_DOWNLOAD = false** — When `true`, `/research-lit` downloads the top relevant arXiv PDFs during Phase 1. When `false` (default), only fetches metadata. Passed through to `/research-lit`.

> 💡 These are defaults. Override by telling the skill, e.g., `/idea-discovery "topic" — pilot budget: 4h per idea, 20h total` or `/idea-discovery "topic" — arxiv download: true`.

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

**🚦 Checkpoint:** Present the landscape summary to the user. Ask:

```
📚 Literature survey complete. Here's what I found:
- [key findings, gaps, open problems]

Does this match your understanding? Should I adjust the scope before generating ideas?
(If no response, I'll proceed with the top-ranked direction.)
```

- **User approves** (or no response + AUTO_PROCEED=true) → proceed to Phase 2 with best direction.
- **User requests changes** (e.g., "focus more on X", "ignore Y", "too broad") → refine the search with updated queries, re-run `/research-lit` with adjusted scope, and present again. Repeat until the user is satisfied.

### Phase 2: Idea Generation + Filtering + Pilots

Invoke `/idea-creator` with the landscape context:

```
/idea-creator "$ARGUMENTS"
```

**What this does:**
- Brainstorm 8-12 concrete ideas via GPT-5.4 xhigh
- Filter by feasibility, compute cost, quick novelty search
- Deep validate top ideas (full novelty check + devil's advocate)
- Run parallel pilot experiments on available GPUs (top 2-3 ideas)
- Rank by empirical signal
- Output `IDEA_REPORT.md`

**🚦 Checkpoint:** Present `IDEA_REPORT.md` ranked ideas to the user. Ask:

```
💡 Generated X ideas, filtered to Y, piloted Z. Top results:

1. [Idea 1] — Pilot: POSITIVE (+X%)
2. [Idea 2] — Pilot: WEAK POSITIVE (+Y%)
3. [Idea 3] — Pilot: NEGATIVE, eliminated

Which ideas should I validate further? Or should I regenerate with different constraints?
(If no response, I'll proceed with the top-ranked ideas.)
```

- **User picks ideas** (or no response + AUTO_PROCEED=true) → proceed to Phase 3 with top-ranked ideas.
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
- Cross-verify with GPT-5.4 xhigh
- Check for concurrent work (last 3-6 months)
- Identify closest existing work and differentiation points

**Update `IDEA_REPORT.md`** with deep novelty results. Eliminate any idea that turns out to be already published.

### Phase 4: External Critical Review

For the surviving top idea(s), get brutal feedback:

```
/research-review "[top idea with hypothesis + pilot results]"
```

**What this does:**
- GPT-5.4 xhigh acts as a senior reviewer (NeurIPS/ICML level)
- Scores the idea, identifies weaknesses, suggests minimum viable improvements
- Provides concrete feedback on experimental design

**Update `IDEA_REPORT.md`** with reviewer feedback and revised plan.

### Phase 5: Final Report

Finalize `IDEA_REPORT.md` with all accumulated information:

```markdown
# Idea Discovery Report

**Direction**: $ARGUMENTS
**Date**: [today]
**Pipeline**: research-lit → idea-creator → novelty-check → research-review

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

## Next Steps
- [ ] Implement Idea 1
- [ ] /run-experiment to deploy full-scale experiments
- [ ] /auto-review-loop to iterate until submission-ready
- [ ] Or invoke /research-pipeline for the complete end-to-end flow
```

## Key Rules

- **Don't skip phases.** Each phase filters and validates — skipping leads to wasted effort later.
- **Checkpoint between phases.** Briefly summarize what was found before moving on.
- **Kill ideas early.** It's better to kill 10 bad ideas in Phase 3 than to implement one and fail.
- **Empirical signal > theoretical appeal.** An idea with a positive pilot outranks a "sounds great" idea without evidence.
- **Document everything.** Dead ends are just as valuable as successes for future reference.
- **Be honest with the reviewer.** Include negative results and failed pilots in the review prompt.
- **Feishu notifications are optional.** If `~/.claude/feishu.json` exists, send `checkpoint` at each phase transition and `pipeline_done` at final report. If absent/off, skip silently.

## Composing with Workflow 2

After this pipeline produces a validated top idea:

```
/idea-discovery "direction"         ← you are here (Workflow 1)
implement                           ← write code for the top idea
/run-experiment                     ← deploy full-scale experiments
/auto-review-loop "top idea"        ← Workflow 2: iterate until submission-ready

Or use /research-pipeline for the full end-to-end flow.
```
