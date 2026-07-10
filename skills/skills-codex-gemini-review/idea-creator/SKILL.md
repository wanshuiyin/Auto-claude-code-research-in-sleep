---
name: "idea-creator"
description: "Generate and rank research ideas given a broad direction. Use when user says \"\u627eidea\", \"brainstorm ideas\", \"generate research ideas\", \"what can we work on\", or wants to explore a research area for publishable directions."
---

> Override for Codex users who want **Gemini**, not a second Codex agent, to act as the reviewer. Install this package **after** `skills/skills-codex/*`.

# Research Idea Creator

> **Gemini overlay assurance:** `review_independence: cross-family` and `acceptance_status: accepted`.

Generate publishable research ideas for: $ARGUMENTS

## Overview

Given a broad research direction from the user, systematically generate, validate, and rank concrete research ideas. Standalone, Phase 1's landscape survey is **inline** (WebSearch — it does not invoke `/research-lit`); Phases 4-5 invoke `/novelty-check`, `/run-experiment`, and `/monitor-experiment` for validation and pilots. For the full sub-skill pipeline (`/research-lit` → idea generation → `/novelty-check` → `/research-review`), run `/idea-discovery` (Workflow 1), which orchestrates this skill.

## Constants

- **PILOT_MAX_HOURS = 2** — Skip any pilot estimated to take > 2 hours per GPU. Flag as "needs manual pilot".
- **PILOT_TIMEOUT_HOURS = 3** — Hard timeout: kill pilots exceeding 3 hours. Collect partial results if available.
- **MAX_PILOT_IDEAS = 3** — Pilot at most 3 ideas in parallel. Additional ideas are validated on paper only.
- **MAX_TOTAL_GPU_HOURS = 8** — Total GPU budget for all pilots combined.
- **REVIEWER_MODEL = `gemini-review`** — Gemini reviewer invoked through the local `gemini-review` MCP bridge for brainstorming and critique. Set `GEMINI_REVIEW_MODEL` if you need a specific Gemini model override.

- **OUTPUT_DIR = `idea-stage/`** — Directory for idea output files.

> 💡 Override via argument, e.g., `/idea-creator "topic" — pilot budget: 4h per idea, 20h total`.

## Workflow

### Phase 1: Landscape Survey (5-10 min)

Map the research area to understand what exists and where the gaps are.

1. **Scan local paper library first**: Check `papers/` and `literature/` in the project directory for existing PDFs. Read first 3 pages of relevant papers to build a baseline understanding before searching online. This avoids re-discovering what the user already knows.

2. **Search recent literature** using WebSearch:
   - Top venues in the last 2 years (NeurIPS, ICML, ICLR, ACL, EMNLP, etc.)
   - Recent arXiv preprints (last 6 months)
   - Use 5+ different query formulations
   - Read abstracts and introductions of the top 10-15 papers

2. **Build a landscape map**:
   - Group papers by sub-direction / approach
   - Identify what has been tried and what hasn't
   - Note recurring limitations mentioned in "Future Work" sections
   - Flag any open problems explicitly stated by multiple papers

3. **Identify structural gaps**:
   - Methods that work in domain A but haven't been tried in domain B
   - Contradictory findings between papers (opportunity for resolution)
   - Assumptions that everyone makes but nobody has tested
   - Scaling regimes that haven't been explored
   - Diagnostic questions that nobody has asked

### Phase 2: Idea Generation (brainstorm with external LLM)

Use the local `gemini-review` MCP bridge for divergent thinking:

```
mcp__gemini-review__review_start:
  prompt: |
    You are a senior ML researcher brainstorming research ideas.

    Research direction: [user's direction]

    Here is the current landscape:
    [paste landscape map from Phase 1]

    Key gaps identified:
    [paste gaps from Phase 1]

    Generate 8-12 concrete research ideas. For each idea:
    1. One-sentence summary
    2. Core hypothesis (what you expect to find and why)
    3. Minimum viable experiment (what's the cheapest way to test this?)
    4. Expected contribution type: empirical finding / new method / theoretical result / diagnostic
    5. Risk level: LOW (likely works) / MEDIUM (50-50) / HIGH (speculative)
    6. Estimated effort: days / weeks / months

    Prioritize ideas that are:
    - Testable with moderate compute (8x RTX 3090 or less)
    - Likely to produce a clear positive OR negative result (both are publishable)
    - Not "apply X to Y" unless the application reveals genuinely surprising insights
    - Differentiated from the 10-15 papers above

    Be creative but grounded. A great idea is one where the answer matters regardless of which way it goes.
```

After this start call, immediately save the returned `jobId` and poll `mcp__gemini-review__review_status` with a bounded `waitSeconds` until `done=true`. Treat the completed status payload's `response` as the brainstorm output, and save the completed `threadId` for follow-up critique in Phase 4.

### Phase 3: Mechanical consolidation + objective feasibility gate

> This phase does NOT judge idea quality, novelty, or impact — those are the
> job of the Phase-4 cross-model reviewer (a different model family). Dropping
> ideas here on a same-family novelty or impact call would pre-filter the
> reviewer's input with same-family judgment — the opposite of why ARIS uses a
> cross-model reviewer at all. Phase 3 only (a) clusters near-duplicate ideas
> and (b) drops ideas that are OBJECTIVELY out of budget; everything else
> passes through ANNOTATED, not eliminated.

1. **Objective feasibility gate (safe to gate here)**: drop an idea ONLY on a
   mechanical, budget-based fact — estimated compute > 1 week of available GPU
   time, OR a dataset that is provably unavailable. Do NOT drop on
   "implementation looks complex" — annotate complexity instead.

2. **Novelty signal — ANNOTATE, do not eliminate**: do 2-3 targeted searches
   and attach a `prior_work` note (what looks related, with links). This is
   input for the Phase-4 reviewer, not a filter; full `/novelty-check` runs in
   Phase 4. Do NOT drop an idea here because it "might already be done."

3. **Impact signal — ANNOTATE, do not eliminate**: attach a one-line `so_what`
   note (why the result would matter either way). Do NOT drop on a same-family
   "a reviewer wouldn't care" call — that is exactly what the Phase-4
   cross-model reviewer is for.

Every feasible, non-duplicate idea — with its `prior_work` and `so_what`
annotations — proceeds to Phase 4, where the cross-model reviewer does the
quality/novelty narrowing.

### Phase 4: Deep Validation (for top ideas)

For each surviving idea, run a deeper evaluation:

1. **Novelty check**: Use the `/novelty-check` workflow (multi-source search + Gemini cross-verification) for each idea

2. **Critical review**: Use `mcp__gemini-review__review_reply_start` with the saved completed `threadId`:
   ```
   mcp__gemini-review__review_reply_start:
     threadId: [saved completed threadId from Phase 2]
     prompt: |
       Here are our top ideas after filtering:
       [paste surviving ideas with novelty check results]

       For each, play devil's advocate:
       - What's the strongest objection a reviewer would raise?
       - What's the most likely failure mode?
       - How would you rank these for a top venue submission?
       - Which 2-3 would you actually work on?
   ```

   After this start call, immediately save the returned `jobId` and poll `mcp__gemini-review__review_status` with a bounded `waitSeconds` until `done=true`. Treat the completed status payload's `response` as the follow-up critique.

3. **Combine rankings**: Merge your assessment with Gemini's ranking. Select top 2-3 ideas for pilot experiments.

### Phase 5: Parallel Pilot Experiments (for top 2-3 ideas)

Before committing to a full research effort, run cheap pilot experiments to get empirical signal. This is the key differentiator from paper-only validation.

1. **Design pilots**: For each top idea, define the minimal experiment that would give a positive or negative signal:
   - Single seed, small scale (e.g., small dataset subset, fewer epochs)
   - Target: 30 min - PILOT_MAX_HOURS per pilot on 1 GPU
   - **Estimate GPU-hours BEFORE launching.** If estimated time > PILOT_MAX_HOURS, reduce scale (fewer epochs, smaller subset) or flag as "needs manual pilot"
   - Clear success metric defined upfront (e.g., "if metric improves by > 1%, signal is positive")

2. **Deploy in parallel**: Use `/run-experiment` to launch pilots on different GPUs simultaneously:
   ```
   GPU 0: Pilot for Idea 1
   GPU 1: Pilot for Idea 2
   GPU 2: Pilot for Idea 3
   ```
   Use `run_in_background: true` to launch all at once.

3. **Collect results**: Use `/monitor-experiment` to check progress. If any pilot exceeds PILOT_TIMEOUT_HOURS, kill it and collect partial results. Once all pilots complete (or timeout), compare:
   - Which ideas showed positive signal?
   - Which showed null/negative results? (eliminate or deprioritize)
   - Any surprising findings that suggest a pivot?
   - Total GPU-hours consumed (track against MAX_TOTAL_GPU_HOURS budget)

4. **Re-rank based on empirical evidence**: Update the idea ranking using pilot results. An idea with strong pilot signal jumps ahead of a theoretically appealing but untested idea.

Note: Skip this phase if the ideas are purely theoretical or if no GPU is available. Flag skipped ideas as "needs pilot validation" in the report.

### Phase 6: Output — Ranked Idea Report

Write a structured report to `idea-stage/IDEA_REPORT.md`:

**Lead every recommended idea with its method, in plain language.** Before any hypothesis, novelty score, or claim, state in 2–4 concrete steps what we actually build / train / run — no jargon, no claim-IDs. The reader must understand *what we do* before *what we claim*; claims (hypothesis, validation, expected outcome) come after and read as the method's acceptance criteria.

```markdown
# Research Idea Report

**Direction**: [user's research direction]
**Generated**: [date]
**Ideas evaluated**: X generated → Y survived filtering → Z piloted → W recommended

## Landscape Summary
[3-5 paragraphs on the current state of the field]

## Recommended Ideas (ranked)

### Idea 1: [title]
- **Method (what we actually do)**: [2–4 concrete steps in plain language — what we build / train / run. No jargon, no claim-IDs, no hypothesis yet. Lead with this so the reader grasps the approach first.]
- **Hypothesis**: [one sentence]
- **Minimum experiment**: [concrete description]
- **Expected outcome**: [what success/failure looks like]
- **Novelty**: X/10 — closest work: [paper]
- **Feasibility**: [compute, data, implementation estimates]
- **Risk**: LOW/MEDIUM/HIGH
- **Contribution type**: empirical / method / theory / diagnostic
- **Pilot result**: [POSITIVE: metric +X% / NEGATIVE: no signal / SKIPPED: needs GPU]
- **Reviewer's likely objection**: [strongest counterargument]
- **Why we should do this**: [1-2 sentences]

### Idea 2: [title]
...

## Eliminated Ideas (for reference)
| Idea | Reason eliminated |
|------|-------------------|
| ... | Already done by [paper] |
| ... | Requires > 1 week GPU time |
| ... | Result wouldn't be interesting either way |

## Pilot Experiment Results
| Idea | GPU | Time | Key Metric | Signal |
|------|-----|------|------------|--------|
| Idea 1 | GPU 0 | 45 min | +2.3% CE | POSITIVE |
| Idea 2 | GPU 1 | 30 min | -0.1% CE | NEGATIVE |
| Idea 3 | GPU 2 | 1.5 hr | +0.8% CE | WEAK POSITIVE |

## Suggested Execution Order
1. Start with Idea 1 (positive pilot signal, lowest risk)
2. Idea 3 as backup (weak signal, may need larger scale to confirm)
3. Idea 2 eliminated by pilot — negative result documented

## Next Steps
- [ ] Scale up Idea 1 to full experiment (multi-seed, full dataset)
- [ ] If confirmed, invoke /auto-review-loop for full iteration
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- The user provides a DIRECTION, not an idea. Your job is to generate the ideas.
- Quantity first, quality second: brainstorm broadly, then filter ruthlessly.
- A good negative result is just as publishable as a positive one. Prioritize ideas where the answer matters regardless of direction.
- Don't fall in love with any idea before validating it. Be willing to kill ideas.
- Always estimate compute cost. An idea that needs 1000 GPU-hours is not actionable for most researchers.
- "Apply X to Y" is the lowest form of research idea. Push for deeper questions.
- Include eliminated ideas in the report — they save future time by documenting dead ends.
- **If the user's direction is too broad (e.g., "NLP", "computer vision", "reinforcement learning"), STOP and ask them to narrow it.** A good direction is 1-2 sentences specifying the problem, domain, and constraint — e.g., "factorized gap in discrete diffusion LMs" or "sample efficiency of offline RL with image observations". Without sufficient specificity, generated ideas will be too vague to run experiments on.

## Composing with Other Skills

After this skill produces the ranked report:
```
/idea-creator "direction"     → ranked ideas
/novelty-check "top idea"     → deep novelty verification (already done in Phase 4, but user can re-run)
/research-review "top idea"   → external critical feedback
implement                     → write code
/run-experiment               → deploy to GPU
/auto-review-loop             → iterate until submission-ready
```
