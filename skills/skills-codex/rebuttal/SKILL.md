---
name: "rebuttal"
description: "Submission rebuttal pipeline for reviewer responses under venue constraints. Use when the user needs to draft or manage a rebuttal to external reviews. Do not use for generic research critique or ordinary paper revision; use `research-review` or `paper-write` then."
---

# Workflow 4: Rebuttal

Prepare and maintain a grounded, venue-compliant rebuttal for: **$ARGUMENTS**

## Routing Boundaries

- Use this skill when the user is responding to external reviews and needs a venue-constrained rebuttal.
- Use `research-review` when the task is to critique the work itself rather than write the response to reviewers.
- Use `paper-write` when the task is ordinary revision of paper content rather than rebuttal drafting.

## Scope

This skill is optimized for:

- ICML-style **text-only rebuttal**
- strict **character limits**
- **multiple reviewers**
- **follow-up rounds** after the initial rebuttal
- safe drafting with **no fabrication**, **no overpromise**, and **full issue coverage**

This skill does **not**:

- run new experiments automatically unless `AUTO_EXPERIMENT = true`
- generate new theorem claims automatically
- edit or upload a revised PDF
- submit to OpenReview / CMT / HotCRP

## Lifecycle Position

```text
Workflow 1:   idea-discovery
Workflow 1.5: experiment-bridge
Workflow 2:   auto-review-loop (pre-submission)
Workflow 3:   paper-writing
Workflow 4:   rebuttal (post-submission external reviews)
```

## Constants

- **VENUE = `ICML`** — Default venue
- **RESPONSE_MODE = `TEXT_ONLY`** — v1 default
- **REVIEWER_MODEL = `gpt-5.4`** — Used via a secondary Codex agent for internal stress-testing
- **MAX_INTERNAL_DRAFT_ROUNDS = 2**
- **MAX_STRESS_TEST_ROUNDS = 1**
- **MAX_FOLLOWUP_ROUNDS = 3**
- **AUTO_EXPERIMENT = false** — When `true`, invoke `/experiment-bridge` for reviewer concerns that require new evidence
- **QUICK_MODE = false** — When `true`, only run Phase 0-3 and stop after strategy
- **REBUTTAL_DIR = `rebuttal/`**

> Override: `/rebuttal "paper/" — venue: NeurIPS, character limit: 5000`

## Required Inputs

1. **Paper source** — PDF, LaTeX directory, or narrative summary
2. **Raw reviews** — pasted text, markdown, or PDF with reviewer IDs
3. **Venue rules** — venue name, character/word limit, text-only or revised PDF allowed
4. **Current stage** — initial rebuttal or follow-up round

If venue rules or limit are missing, stop and ask before drafting.

## Safety Model

Three hard gates. If any fails, do not finalize:

1. **Provenance gate** — every factual statement maps to a known source
2. **Commitment gate** — every promise maps to already-done / approved-for-rebuttal / future-work-only
3. **Coverage gate** — every reviewer concern ends in answered / deferred intentionally / needs user input

## Workflow

### Phase 0: Resume or Initialize

1. If `rebuttal/REBUTTAL_STATE.md` exists, resume from the recorded phase
2. Otherwise, create `rebuttal/` and initialize the output documents
3. Load the paper, reviews, venue rules, and any user-confirmed evidence

### Phase 1: Validate Inputs and Normalize Reviews

1. Validate that venue rules are explicit
2. Normalize all reviewer text into `rebuttal/REVIEWS_RAW.md` verbatim
3. Record metadata in `rebuttal/REBUTTAL_STATE.md`
4. If ambiguous, pause and ask

### Phase 2: Atomize and Classify Reviewer Concerns

Create `rebuttal/ISSUE_BOARD.md`.

For each atomic concern, record:

- `issue_id`
- `reviewer`, `round`, `raw_anchor`
- `issue_type`
- `severity`
- `reviewer_stance`
- `response_mode`
- `status`

### Phase 3: Build Strategy Plan

Create `rebuttal/STRATEGY_PLAN.md`.

1. Identify 2-4 global themes resolving shared concerns
2. Choose a response mode per issue
3. Build the character budget
4. Identify blocked claims
5. If unresolved blockers exist, pause and present them to the user

**QUICK_MODE exit**: if `QUICK_MODE = true`, stop here and present `ISSUE_BOARD.md` + `STRATEGY_PLAN.md`.

### Phase 3.5: Evidence Sprint (when AUTO_EXPERIMENT = true)

**Skip entirely if `AUTO_EXPERIMENT` is `false`.**

If the strategy plan identifies issues that require new empirical evidence:

1. Generate a mini experiment plan from the reviewer concerns
2. Invoke `/experiment-bridge "rebuttal/REBUTTAL_EXPERIMENT_PLAN.md"`
3. Wait for results, then update `ISSUE_BOARD.md`
4. If experiments fail or are inconclusive, switch to `narrow_concession` or `future_work_boundary`
5. Save experiment results to `rebuttal/REBUTTAL_EXPERIMENTS.md`

### Phase 4: Draft Initial Rebuttal

Create `rebuttal/REBUTTAL_DRAFT_v1.md`.

Structure:

1. Short opener
2. Per-reviewer numbered responses
3. Short closing

Also generate `rebuttal/PASTE_READY.txt` with exact character count.

### Phase 5: Safety Validation

Run all lints:

1. Coverage
2. Provenance
3. Commitment
4. Tone
5. Consistency
6. Limit

### Phase 6: Stress Test

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    Stress-test this rebuttal draft:
    [raw reviews + issue board + draft + venue rules]

    1. Unanswered or weakly answered concerns?
    2. Unsupported factual statements?
    3. Risky or unapproved promises?
    4. Tone problems?
    5. Paragraph most likely to backfire with a meta-reviewer?
    6. Minimal grounded fixes only. Do not invent evidence.

    Verdict: safe to submit / needs revision
```

Save the full response to `rebuttal/MCP_STRESS_TEST.md`. If a hard safety blocker remains, revise before finalizing.

### Phase 7: Finalize — Two Versions

Produce:

1. **`rebuttal/PASTE_READY.txt`** — strict version, ready to paste
2. **`rebuttal/REBUTTAL_DRAFT_rich.md`** — extended version with optional sections marked
3. Update `rebuttal/REBUTTAL_STATE.md`
4. Present the remaining risks and any lines needing manual approval

### Phase 8: Follow-Up Rounds

When new reviewer comments arrive:

1. Append them to `rebuttal/FOLLOWUP_LOG.md`
2. Link to existing issues or create new ones
3. Draft the delta reply only
4. Re-run safety lints
5. If continuity helps, reuse the same reviewer agent via `send_input`
6. Escalate technically, not rhetorically

## Key Rules

- Never fabricate evidence, numbers, derivations, citations, or links
- Never overpromise. Only promise what the user explicitly approved.
- Every reviewer concern must be tracked and accounted for
- Preserve raw records
- Shared concerns go in the opener; reviewer-specific details go in the per-reviewer sections
- Answer friendly reviewers too
- Respect the hard character limit
