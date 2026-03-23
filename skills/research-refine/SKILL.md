---
name: research-refine
description: 'Turn a vague research direction into a problem-anchored, elegant, frontier-aware, implementation-oriented method plan via iterative GPT-5.4 review. Use when the user says "refine my approach", "帮我细化方案", "decompose this problem", "打磨idea", "refine research plan", "细化研究方案", or wants a concrete research method that stays simple, focused, and top-venue ready instead of a vague or overbuilt idea.'
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Research Refine: Problem-Anchored, Elegant, Frontier-Aware Plan Refinement

Refine and concretize: **$ARGUMENTS**

## Overview

Use this skill when the research problem is already visible but the technical route is still fuzzy. The goal is not to produce a bloated proposal or a benchmark shopping list. The goal is to turn a vague direction into a **problem -> focused method -> minimal validation** document that is concrete enough to implement, elegant enough to feel paper-worthy, and current enough to resonate in the foundation-model era.

Four principles dominate this skill:

1. **Do not lose the original problem.** Freeze an immutable **Problem Anchor** and reuse it in every round.
2. **The smallest adequate mechanism wins.** Prefer the minimal intervention that directly fixes the bottleneck.
3. **One paper, one dominant contribution.** Prefer one sharp thesis plus at most one supporting contribution.
4. **Modern leverage is a prior, not a decoration.** When LLM / VLM / Diffusion / RL / distillation / inference-time scaling naturally fit the bottleneck, use them concretely. Do not bolt them on as buzzwords.

```
User input (PROBLEM + vague APPROACH)
  -> Phase 0 (Claude): Freeze Problem Anchor
  -> Phase 1 (Claude): Scan grounding papers -> identify technical gap -> choose the sharpest route -> write focused proposal
  -> Phase 2 (Codex/GPT-5.4): Review for fidelity, specificity, contribution quality, and frontier leverage
  -> Phase 3 (Claude): Anchor check + simplicity check -> revise method -> rewrite full proposal
  -> Phase 4 (Codex, same thread): Re-evaluate revised proposal
  -> Repeat Phase 3-4 until OVERALL SCORE >= 9 or MAX_ROUNDS reached
  -> Phase 5: Save full history to refine-logs/
  -> Optional handoff: /experiment-plan for a detailed execution-ready experiment roadmap
```

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Reviewer model used via Codex MCP.
- **MAX_ROUNDS = 5** — Maximum review-revise rounds.
- **SCORE_THRESHOLD = 9** — Minimum overall score to stop.
- **OUTPUT_DIR = `refine-logs/`** — Directory for round files and final report.
- **MAX_LOCAL_PAPERS = 15** — Maximum local papers/notes to scan for grounding.
- **MAX_CORE_EXPERIMENTS = 3** — Default cap for core validation blocks inside this skill.
- **MAX_PRIMARY_CLAIMS = 2** — Soft cap for paper-level claims. Prefer one dominant claim plus one supporting claim.
- **MAX_NEW_TRAINABLE_COMPONENTS = 2** — Soft cap for genuinely new trainable pieces. Exceed only if the paper breaks otherwise.

> Override via argument if needed, e.g. `/research-refine "problem | approach" -- max rounds: 3, threshold: 9`.

## State Persistence (Checkpoint Recovery)

Long-running refinement sessions may fail mid-way (e.g., API timeout, context compaction, or session interruption). To avoid losing completed work, persist state to `refine-logs/REFINE_STATE.json` after each phase boundary:

```json
{
  "phase": "review",
  "round": 1,
  "threadId": "019cd392-...",
  "last_score": 6.5,
  "last_verdict": "REVISE",
  "status": "in_progress",
  "timestamp": "2026-03-22T20:00:00"
}
```

**Field definitions:**

| Field | Values | Meaning |
|-------|--------|---------|
| `phase` | `"anchor"` / `"proposal"` / `"review"` / `"refine"` / `"done"` | Last **completed** phase |
| `round` | 0–MAX_ROUNDS | Current round number |
| `threadId` | string or null | Reviewer thread ID for `codex-reply` continuity |
| `last_score` | number or null | Most recent overall score from reviewer |
| `last_verdict` | string or null | Most recent verdict (READY / REVISE / RETHINK) |
| `status` | `"in_progress"` / `"completed"` | Loop status |
| `timestamp` | ISO 8601 | When state was last written |

**Write rules:**
- **Write after each phase completes** (not before). Overwrite each time — only the latest state matters.
- **On completion** (Phase 5 finished), set `"status": "completed"`.

## Output Structure

```
refine-logs/
├── REFINE_STATE.json
├── round-0-initial-proposal.md
├── round-1-review.md
├── round-1-refinement.md
├── round-2-review.md
├── round-2-refinement.md
├── ...
├── REVIEW_SUMMARY.md
├── FINAL_PROPOSAL.md
├── REFINEMENT_REPORT.md
└── score-history.md
```

Every `round-N-refinement.md` must contain a **full anchored proposal**, not just incremental fixes.

## Workflow

### Initialization (Checkpoint Recovery)

Before starting any phase, check whether a previous run left a checkpoint:

1. **Check for `refine-logs/REFINE_STATE.json`**:
   - If it **does not exist** → **fresh start** (proceed to Phase 0 normally)
   - If it exists AND `status` is `"completed"` → **fresh start** (delete state file, previous run finished)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is **older than 24 hours** → **fresh start** (stale state from a killed/abandoned run — delete the file)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is **within 24 hours** → **resume**

2. **On resume**, read the state file and recover context:
   - Read all existing `refine-logs/round-*.md` files to restore prior work
   - Read `refine-logs/score-history.md` if it exists
   - Recover `threadId` for reviewer thread continuity
   - Log to the user: `"Checkpoint found. Resuming after phase: {phase}, round: {round}."`
   - **Jump to the next phase** based on the saved `phase` value:

   | Saved `phase` | What was completed | Resume from |
   |---------------|-------------------|-------------|
   | `"anchor"` | Phase 0 done | Phase 1 (read anchor from round-0 context) |
   | `"proposal"` | Phase 1 done | Phase 2 (read `round-0-initial-proposal.md`) |
   | `"review"` | Phase 2 or 4 done | Phase 3 (read latest `round-N-review.md`) |
   | `"refine"` | Phase 3 done | Phase 4 (read latest `round-N-refinement.md`) |

3. **On fresh start**, ensure `refine-logs/` directory exists and proceed to Phase 0.

### Phase 0: Freeze the Problem Anchor

Before proposing anything, extract the user's immutable bottom-line problem. This anchor must be copied verbatim into every proposal and every refinement round.

Write:

- **Bottom-line problem**: What technical problem must be solved?
- **Must-solve bottleneck**: What specific weakness in current methods is unacceptable?
- **Non-goals**: What is explicitly *not* the goal of this project?
- **Constraints**: Compute, data, time, tooling, venue, deployment limits.
- **Success condition**: What evidence would make the user say "yes, this method addresses the actual problem"?

If later reviewer feedback would change the problem being solved, mark that as **drift** and push back or adapt carefully.

**Checkpoint:** Write `refine-logs/REFINE_STATE.json` with `{"phase": "anchor", "round": 0, "threadId": null, "last_score": null, "last_verdict": null, "status": "in_progress", "timestamp": "<now>"}`.

### Phase 1: Build the Initial Proposal

#### Step 1.1: Scan Grounding Material

Check `papers/` and `literature/` first. Read only the relevant parts needed to answer:

- What mechanism do current methods use?
- Where exactly do they fail for this problem?
- Which recent LLM / VLM / Diffusion / RL era techniques are actually relevant here?
- What training objectives, representations, or interfaces are reusable?
- What details distinguish a real method from a renamed high-level idea?

If local material is insufficient, search recent top-venue/arXiv work online. Focus on **method sections, training setup, and failure modes**, not just abstracts.

#### Step 1.2: Identify the Technical Gap

Do not stop at generic research questions. Make the gap operational:

1. **Current pipeline failure point**: where does the baseline break?
2. **Why naive fixes are insufficient**: larger context, more data, prompting, memory bank, or stacking more modules.
3. **Smallest adequate intervention**: what is the least additional mechanism that could plausibly fix the bottleneck?
4. **Frontier-native alternative**: is there a more current route using foundation-model-era primitives that better matches the bottleneck?
5. **Core technical claim**: what exact mechanism claim could survive top-venue scrutiny?
6. **Required evidence**: what minimum proof is needed to defend that claim?

#### Step 1.3: Choose the Sharpest Route

Before locking the method, compare two candidate routes if both are plausible:

- **Route A: Elegant minimal route** — the smallest mechanism that directly targets the bottleneck.
- **Route B: Frontier-native route** — a more modern route that uses LLM / VLM / Diffusion / RL / distillation / inference-time scaling *only if* it gives a cleaner or stronger story.

Then decide:

- Which route is more likely to become a strong paper under the stated constraints?
- Which route has the cleaner novelty story relative to the closest work?
- Which route avoids contribution sprawl?

If both routes are weak, rethink the framing instead of combining them into a larger system by default.

#### Step 1.4: Concretize the Method First

The proposal must answer "how would we actually build this?" Prefer method detail over broad experimentation and prefer reuse over invention.

Cover:

1. **One-sentence method thesis**: the single strongest mechanism claim.
2. **Contribution focus**: one dominant contribution and at most one supporting contribution.
3. **Complexity budget**: what is frozen or reused, what is new, and what tempting additions are intentionally excluded.
4. **System graph**: modules, data flow, inputs, outputs.
5. **Representation design**: what latent, embedding, plan token, reward signal, memory state, or alignment space is used?
6. **Training recipe**: data source, supervision, pseudo-labeling, negatives, curriculum, losses, weighting, stagewise vs joint training.
7. **Inference path**: how the trained components are used at test time and what signals flow where.
8. **Why the mechanism stays small**: why a larger stack is unnecessary.
9. **Exact role of any frontier primitive**: if you use an LLM / VLM / Diffusion / RL component, specify whether it acts as planner, teacher, critic, reward model, generator prior, search controller, or distillation source.
10. **Failure handling**: what could go wrong and what fallback or diagnostic exists?
11. **Novelty and elegance argument**: why this is more than naming a module and why the paper still looks focused.

If the method is still only described as "add a module" or "use a planner," it is not concrete enough.

#### Step 1.5: Design Minimal Claim-Driven Validation

Experiments exist to validate the method, not to dominate the document.

For each core claim, define the **smallest strong experiment** that can validate it:

- the claim being tested
- the necessary baseline or ablation
- the decisive metric
- the expected directional outcome

Additional rules:

- Ensure one experiment block directly supports the **Problem Anchor**.
- If complexity risk exists, include one **simplification or deletion check**.
- If a frontier primitive is central, include one **necessity check** showing why that choice matters.
- Default to **1-3 core experiment blocks** and leave the full execution roadmap to `/experiment-plan`.

#### Step 1.6: Write the Initial Proposal

Save to `refine-logs/round-0-initial-proposal.md`.

Use this structure:

```markdown
# Research Proposal: [Title]

## Problem Anchor
- Bottom-line problem:
- Must-solve bottleneck:
- Non-goals:
- Constraints:
- Success condition:

## Technical Gap
[Why current methods fail, why naive bigger systems are not enough, and what mechanism is missing]

## Method Thesis
- One-sentence thesis:
- Why this is the smallest adequate intervention:
- Why this route is timely in the foundation-model era:

## Contribution Focus
- Dominant contribution:
- Optional supporting contribution:
- Explicit non-contributions:

## Proposed Method
### Complexity Budget
- Frozen / reused backbone:
- New trainable components:
- Tempting additions intentionally not used:

### System Overview
[Step-by-step pipeline or ASCII graph]

### Core Mechanism
- Input / output:
- Architecture or policy:
- Training signal / loss:
- Why this is the main novelty:

### Optional Supporting Component
- Only include if truly necessary:
- Input / output:
- Training signal / loss:
- Why it does not create contribution sprawl:

### Modern Primitive Usage
- Which LLM / VLM / Diffusion / RL-era primitive is used:
- Exact role in the pipeline:
- Why it is more natural than an old-school alternative:

### Integration into Base Generator / Downstream Pipeline
[Where the new method attaches, what is frozen, what is trainable, inference order]

### Training Plan
[Stagewise or joint training, losses, data construction, pseudo-labels, schedules]

### Failure Modes and Diagnostics
- [Failure mode]:
- [How to detect]:
- [Fallback or mitigation]:

### Novelty and Elegance Argument
[Closest work, exact difference, why this is a focused mechanism-level contribution rather than a module pile-up]

## Claim-Driven Validation Sketch
### Claim 1: [Main claim]
- Minimal experiment:
- Baselines / ablations:
- Metric:
- Expected evidence:

### Claim 2: [Optional]
- Minimal experiment:
- Baselines / ablations:
- Metric:
- Expected evidence:

## Experiment Handoff Inputs
- Must-prove claims:
- Must-run ablations:
- Critical datasets / metrics:
- Highest-risk assumptions:

## Compute & Timeline Estimate
- Estimated GPU-hours:
- Data / annotation cost:
- Timeline:
```

**Checkpoint:** Update `refine-logs/REFINE_STATE.json` with `{"phase": "proposal", "round": 0, ...}`.

### Phase 2: External Method Review (Round 1)

Send the full proposal to GPT-5.4 for an **elegance-first, frontier-aware, method-first** review. The reviewer should spend most of the critique budget on the method itself, not on expanding the experiment menu.

```
mcp__codex__codex:
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are a senior ML reviewer for a top venue (NeurIPS/ICML/ICLR).
    This is an early-stage, method-first research proposal.

    Your job is NOT to reward extra modules, contribution sprawl, or a giant benchmark checklist.
    Your job IS to stress-test whether the proposed method:
    (1) still solves the original anchored problem,
    (2) is concrete enough to implement,
    (3) presents a focused, elegant contribution,
    (4) uses foundation-model-era techniques appropriately when they are the natural fit.

    Review principles:
    - Prefer the smallest adequate mechanism over a larger system.
    - Penalize parallel contributions that make the paper feel unfocused.
    - If a modern LLM / VLM / Diffusion / RL route would clearly produce a better paper, say so concretely.
    - If the proposal is already modern enough, do NOT force trendy components.
    - Do not ask for extra experiments unless they are needed to prove the core claims.

    Read the Problem Anchor first. If your suggested fix would change the problem being solved,
    call that out explicitly as drift instead of treating it as a normal revision request.

    === PROPOSAL ===
    [Paste the FULL proposal from Phase 1]
    === END PROPOSAL ===

    Score these 7 dimensions from 1-10:

    1. **Problem Fidelity**: Does the method still attack the original bottleneck, or has it drifted into solving something easier or different?

    2. **Method Specificity**: Are the interfaces, representations, losses, training stages, and inference path concrete enough that an engineer could start implementing?

    3. **Contribution Quality**: Is there one dominant mechanism-level contribution with real novelty, good parsimony, and no obvious contribution sprawl?

    4. **Frontier Leverage**: Does the proposal use current foundation-model-era primitives appropriately when they are the right tool, instead of defaulting to old-school module stacking?

    5. **Feasibility**: Can this method be trained and integrated with the stated resources and data assumptions?

    6. **Validation Focus**: Are the proposed experiments minimal but sufficient to validate the core claims? Is there unnecessary experimental bloat?

    7. **Venue Readiness**: If executed well, would the contribution feel sharp and timely enough for a top venue?

    **OVERALL SCORE** (1-10): Weighted toward Problem Fidelity, Method Specificity, Contribution Quality, and Frontier Leverage.
    Use this weighting: Problem Fidelity 15%, Method Specificity 25%, Contribution Quality 25%, Frontier Leverage 15%, Feasibility 10%, Validation Focus 5%, Venue Readiness 5%.

    For each dimension scoring < 7, provide:
    - The specific weakness
    - A concrete fix at the method level (interface / loss / training recipe / integration point / deletion of unnecessary parts)
    - Priority: CRITICAL / IMPORTANT / MINOR

    Then add:
    - **Simplification Opportunities**: 1-3 concrete ways to delete, merge, or reuse components while preserving the main claim. Write "NONE" if already tight.
    - **Modernization Opportunities**: 1-3 concrete ways to replace old-school pieces with more natural foundation-model-era primitives if genuinely better. Write "NONE" if already modern enough.
    - **Drift Warning**: "NONE" if the proposal still solves the anchored problem; otherwise explain the drift clearly.
    - **Verdict**: READY / REVISE / RETHINK

    Verdict rule:
    - READY: overall score >= 9, no meaningful drift, one focused dominant contribution, and no obvious complexity bloat remains
    - REVISE: the direction is promising but not yet at READY bar
    - RETHINK: the core mechanism or framing is still fundamentally off
```

**CRITICAL: Save the `threadId`** from this call for all later rounds.

**CRITICAL: Save the FULL raw response** verbatim.

Save review to `refine-logs/round-1-review.md` with the raw response in a `<details>` block.

**Checkpoint:** Update `refine-logs/REFINE_STATE.json` with `{"phase": "review", "round": 1, "threadId": "<saved>", "last_score": <parsed>, "last_verdict": "<parsed>", ...}`.

### Phase 3: Parse Feedback and Revise the Method

#### Step 3.1: Parse the Review

Extract:

- **Problem Fidelity**
- **Method Specificity**
- **Contribution Quality**
- **Frontier Leverage**
- **Feasibility**
- **Validation Focus**
- **Venue Readiness**
- **Overall score**
- **Verdict**
- **Drift Warning**
- **Simplification Opportunities**
- **Modernization Opportunities**
- **Action items** ranked by priority

Update `refine-logs/score-history.md`:

```markdown
# Score Evolution

| Round | Problem Fidelity | Method Specificity | Contribution Quality | Frontier Leverage | Feasibility | Validation Focus | Venue Readiness | Overall | Verdict |
|-------|------------------|--------------------|----------------------|-------------------|-------------|------------------|-----------------|---------|---------|
| 1     | X                | X                  | X                    | X                 | X           | X                | X               | X       | REVISE  |
```

**STOP CONDITION**: If overall score >= SCORE_THRESHOLD, verdict is READY, and there is no unresolved drift warning, skip to Phase 5.

#### Step 3.2: Revise With an Anchor Check and a Simplicity Check

Before changing anything:

1. Copy the **Problem Anchor verbatim**.
2. Write an **Anchor Check**:
   - What is the original bottleneck?
   - Does the current method still solve it?
   - Which reviewer suggestions would cause drift if followed blindly?
3. Write a **Simplicity Check**:
   - What is the dominant contribution now?
   - What components can be removed, merged, or kept frozen?
   - Which reviewer suggestions add unnecessary complexity?
   - If a frontier primitive is central, is its role still crisp and justified?

Then process reviewer feedback:

- If **valid**: sharpen the mechanism, simplify if possible, or modernize if the paper really improves.
- If **debatable**: revise, but explain your reasoning with evidence.
- If **wrong, drifting, or over-complicating**: push back with evidence from local papers and the Problem Anchor.

Bias the revisions toward:

- a sharper central contribution
- fewer moving parts
- cleaner reuse of strong existing backbones
- more natural foundation-model-era leverage when it improves the paper
- leaner, claim-driven experiments

Do **not** add multiple parallel contributions just to chase score. If the reviewer requests another module, first ask whether the same gain can come from a better interface, distillation signal, reward model, or inference policy on top of an existing backbone.

Save to `refine-logs/round-N-refinement.md`:

```markdown
# Round N Refinement

## Problem Anchor
[Copy verbatim from round 0]

## Anchor Check
- Original bottleneck:
- Why the revised method still addresses it:
- Reviewer suggestions rejected as drift:

## Simplicity Check
- Dominant contribution after revision:
- Components removed or merged:
- Reviewer suggestions rejected as unnecessary complexity:
- Why the remaining mechanism is still the smallest adequate route:

## Changes Made

### 1. [Method section changed]
- Reviewer said:
- Action:
- Reasoning:
- Impact on core method:

### 2. [Novelty / modernity / feasibility / validation change]
- Reviewer said:
- Action:
- Reasoning:
- Impact on core method:

## Revised Proposal
[Full updated proposal from Problem Anchor through Claim-Driven Validation Sketch]
```

**Checkpoint:** Update `refine-logs/REFINE_STATE.json` with `{"phase": "refine", "round": N, ...}`.

### Phase 4: Re-evaluation (Round 2+)

Send the revised proposal back to GPT-5.4 in the **same thread**:

```
mcp__codex__codex-reply:
  threadId: [saved from Phase 2]
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N re-evaluation]

    I revised the proposal based on your feedback.
    First, check whether the original Problem Anchor is still preserved.
    Second, judge whether the method is now more concrete, more focused, and more current.

    Key changes:
    1. [Method change 1]
    2. [Method change 2]
    3. [Simplification / modernization / pushback if any]

    === REVISED PROPOSAL ===
    [Paste the FULL revised proposal]
    === END REVISED PROPOSAL ===

    Please:
    - Re-score the same 7 dimensions and overall
    - State whether the Problem Anchor is preserved or drifted
    - State whether the dominant contribution is now sharper or still too broad
    - State whether the method is simpler or still overbuilt
    - State whether the frontier leverage is now appropriate or still old-school / forced
    - Focus new critiques on missing mechanism, weak training signal, weak integration point, pseudo-novelty, or unnecessary complexity
    - Use the same verdict rule: READY only if overall score >= 9 and no blocking issue remains

    Same output format: 7 scores, overall score, verdict, drift warning, simplification opportunities, modernization opportunities, remaining action items.
```

Save review to `refine-logs/round-N-review.md`.

**Checkpoint:** Update `refine-logs/REFINE_STATE.json` with `{"phase": "review", "round": N, "threadId": "<saved>", "last_score": <parsed>, "last_verdict": "<parsed>", ...}`.

Then return to Phase 3 until:

- **Overall score >= SCORE_THRESHOLD** and verdict is READY and no unresolved drift
- or **MAX_ROUNDS reached**

### Phase 5: Final Report and Logs

#### Step 5.1: Write `refine-logs/REVIEW_SUMMARY.md`

This file is the high-level round-by-round review record. It should answer: each round was trying to solve what, what changed, what got resolved, and what remained.

```markdown
# Review Summary

**Problem**: [user's problem]
**Initial Approach**: [user's vague approach]
**Date**: [today]
**Rounds**: N / MAX_ROUNDS
**Final Score**: X / 10
**Final Verdict**: [READY / REVISE / RETHINK]

## Problem Anchor
[Verbatim anchor used across all rounds]

## Round-by-Round Resolution Log

| Round | Main Reviewer Concerns | What This Round Simplified / Modernized | Solved? | Remaining Risk |
|-------|-------------------------|------------------------------------------|---------|----------------|
| 1     | [top issues from review] | [main method changes]                    | [yes / partial / no] | [if any] |
| 2     | ...                     | ...                                      | ...     | ...            |

## Overall Evolution
- [How the method became more concrete]
- [How the dominant contribution became more focused]
- [How unnecessary complexity was removed]
- [How modern technical leverage improved or stayed intentionally minimal]
- [How drift was avoided or corrected]

## Final Status
- Anchor status: [preserved / corrected / unresolved]
- Focus status: [tight / slightly broad / still diffuse]
- Modernity status: [appropriately frontier-aware / intentionally conservative / still old-school]
- Strongest parts of final method:
- Remaining weaknesses:
```

#### Step 5.2: Write `refine-logs/FINAL_PROPOSAL.md`

This file is the clean final version document. It should contain only the final proposal itself, without review chatter, round history, or raw reviewer output.

```markdown
# Research Proposal: [Title]

[Paste the final refined proposal only]
```

If the final verdict is not READY, still write the best current final version here.

#### Step 5.3: Write `refine-logs/REFINEMENT_REPORT.md`

```markdown
# Refinement Report

**Problem**: [user's problem]
**Initial Approach**: [user's vague approach]
**Date**: [today]
**Rounds**: N / MAX_ROUNDS
**Final Score**: X / 10
**Final Verdict**: [READY / REVISE / RETHINK]

## Problem Anchor
[Verbatim anchor used across all rounds]

## Output Files
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Final proposal: `refine-logs/FINAL_PROPOSAL.md`

## Score Evolution

| Round | Problem Fidelity | Method Specificity | Contribution Quality | Frontier Leverage | Feasibility | Validation Focus | Venue Readiness | Overall | Verdict |
|-------|------------------|--------------------|----------------------|-------------------|-------------|------------------|-----------------|---------|---------|
| 1     | ...              | ...                | ...                  | ...               | ...         | ...              | ...             | ...     | ...     |

## Round-by-Round Review Record

| Round | Main Reviewer Concerns | What Was Changed | Result |
|-------|-------------------------|------------------|--------|
| 1     | [top issues]            | [main fixes]     | [resolved / partial / unresolved] |
| 2     | ...                     | ...              | ...    |

## Final Proposal Snapshot
- Canonical clean version lives in `refine-logs/FINAL_PROPOSAL.md`
- Summarize the final thesis in 3-5 bullets here

## Method Evolution Highlights
1. [Most important simplification or focusing move]
2. [Most important mechanism upgrade]
3. [Most important modernization or justification for staying simple]

## Pushback / Drift Log
| Round | Reviewer Said | Author Response | Outcome |
|-------|---------------|-----------------|---------|
| 1     | [criticism]   | [pushback + anchor / evidence] | [accepted / rejected] |

## Remaining Weaknesses
[Honest unresolved issues]

## Raw Reviewer Responses

<details>
<summary>Round 1 Review</summary>

[Full verbatim response from GPT-5.4]

</details>

...

## Next Steps
- If READY: proceed to `/experiment-plan` for a full experiment roadmap, then `/run-experiment`
- If REVISE: manually address the remaining mechanism weaknesses, then re-run `/research-refine`
- If RETHINK: revisit the core mechanism, possibly with `/idea-creator`
```

#### Step 5.4: Finalize `score-history.md`

Ensure it contains the complete score evolution table using the new dimensions.

#### Step 5.5: Present a Brief Summary to the User

```
Refinement complete after N rounds.

Final score: X/10 (Verdict: READY / REVISE / RETHINK)

Anchor status:
- [preserved / drift corrected / unresolved concern]

Focus status:
- [tight / slightly broad / still diffuse]

Modernity status:
- [appropriately frontier-aware / intentionally conservative / still old-school]

Key method upgrades:
- [method change 1]
- [method change 2]

Remaining concerns:
- [if any]

Review summary: refine-logs/REVIEW_SUMMARY.md
Full report: refine-logs/REFINEMENT_REPORT.md
Final proposal: refine-logs/FINAL_PROPOSAL.md
Suggested next step: /experiment-plan
```

**Checkpoint:** Update `refine-logs/REFINE_STATE.json` with `{"phase": "done", "status": "completed", ...}`.

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Anchor first, every round.** Always carry forward the same Problem Anchor.
- **One paper, one dominant contribution.** Avoid multiple parallel contributions unless the paper truly needs them.
- **The smallest adequate mechanism wins.** Bigger is not automatically better.
- **Prefer reuse over invention.** Start from strong existing backbones and add only what the bottleneck requires.
- **Modern techniques are a prior, not a decoration.** Use LLM / VLM / Diffusion / RL-era components when they sharpen the method, not when they only make the proposal sound trendy.
- **Minimal experiments.** Inside this skill, experiments only need to prove the core claims.
- **Review the mechanism, not the parts count.** A long module list is not novelty.
- **Pushback is encouraged.** If reviewer feedback causes drift or unnecessary complexity, argue back with evidence.
- **ALWAYS use `config: {"model_reasoning_effort": "xhigh"}`** for all Codex review calls.
- **Save `threadId` from Phase 2** and use `mcp__codex__codex-reply` for later rounds.
- **Do not fabricate results.** Only describe expected evidence and planned experiments.
- **Be specific about compute and data assumptions.** Vague "we'll train a model" is not enough.
- **Document everything.** Save every raw review, every anchor check, every simplicity check, and every major method change.

## Composing with Other Skills

This skill sits between idea discovery and execution:

```
/research-refine-pipeline              -> one-shot refine + experiment planning
/idea-creator "direction"       -> candidate ideas
/research-refine "PROBLEM: ... | APPROACH: ..."  <- you are here
/experiment-plan                -> detailed experiment roadmap
/run-experiment                 -> execute the chosen method
/auto-review-loop               -> iterate on results and paper
```

Typical flow:

1. `/idea-creator` or local reading gives you a problem and a vague method direction
2. `/research-refine` turns that into an anchored, elegant, frontier-aware method plan
3. `/experiment-plan` turns the final proposal into a detailed claim-driven experiment roadmap
4. `/research-refine-pipeline` is the one-shot wrapper when the user wants both stages in a single request
5. `/run-experiment` executes the chosen runs
6. Later loops operate on results, not just ideas

This skill also works standalone if you already know the problem and just need the method to become concrete.
