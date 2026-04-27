---
name: rebuttal
description: "Workflow 4: Submission rebuttal pipeline. Parses external reviews, enforces coverage and grounding, drafts a safe text-only rebuttal under venue limits, and manages follow-up rounds. Use when user says \"rebuttal\", \"reply to reviewers\", \"ICML rebuttal\", \"OpenReview response\", or wants to answer external reviews safely."
argument-hint: [paper-path-or-review-bundle]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill
---

# Workflow 4: Rebuttal

Prepare and maintain a grounded, venue-compliant rebuttal for: **$ARGUMENTS**

## Scope

This skill is optimized for:
- ICML-style **text-only rebuttal**
- strict **character limits**
- **multiple reviewers**
- **follow-up rounds** after the initial rebuttal
- safe drafting with **no fabrication**, **no overpromise**, and **full issue coverage**

This skill does **not**:
- run new experiments automatically
- generate new theorem claims automatically
- edit or upload a revised PDF
- submit to OpenReview / CMT / HotCRP

If the user already has new results, derivations, or approved commitments, the skill can incorporate them as **user-confirmed evidence**.

## Lifecycle Position

```text
Workflow 1:   idea-discovery
Workflow 1.5: experiment-bridge
Workflow 2:   auto-review-loop (pre-submission)
Workflow 3:   paper-writing
Workflow 4:   rebuttal (post-submission external reviews)
```

## Constants

- **VENUE = `ICML`** — Default venue. Override if needed.
- **RESPONSE_MODE = `TEXT_ONLY`** — v1 default.
- **REVIEWER_MODEL = `gpt-5.4`** — Used via Codex MCP for internal stress-testing.
- **REVIEWER_BACKEND = `codex`** — Default: Codex xhigh stress tester. Use `--reviewer: oracle-pro` only when explicitly requested; if Oracle is unavailable, warn and fall back to Codex xhigh. See `../shared-references/reviewer-routing.md`.
- **MAX_INTERNAL_DRAFT_ROUNDS = 2** — draft → lint → revise.
- **MAX_STRESS_TEST_ROUNDS = 1** — One Codex MCP critique round.
- **MAX_FOLLOWUP_ROUNDS = 3** — per reviewer thread.
- **AUTO_EXPERIMENT = false** — When `true`, automatically invoke `/experiment-bridge` to run supplementary experiments when the strategy plan identifies reviewer concerns that require new empirical evidence. When `false` (default), pause and present the evidence gap to the user for manual handling.
- **QUICK_MODE = false** — When `true`, only run Phase 0-3 (parse reviews, atomize concerns, build strategy). Outputs `ISSUE_BOARD.md` + `STRATEGY_PLAN.md` and stops — no drafting, no stress test. Useful for quickly understanding what reviewers want before deciding how to respond.
- **REBUTTAL_DIR = `rebuttal/`**

> Override: `/rebuttal "paper/" — venue: NeurIPS, character limit: 5000`

## Required Inputs

1. **Paper source** — PDF, LaTeX directory, or narrative summary
2. **Raw reviews** — pasted text, markdown, or PDF with reviewer IDs
3. **Venue rules** — venue name, character/word limit, text-only or revised PDF allowed
4. **Current stage** — initial rebuttal or follow-up round

If venue rules or limit are missing, **stop and ask** before drafting.

## Safety Model

Three hard gates — if any fails, do NOT finalize:

1. **Provenance gate** — every factual statement maps to: `paper`, `review`, `user_confirmed_result`, `user_confirmed_derivation`, or `future_work`. No source = blocked.
2. **Commitment gate** — every promise maps to: `already_done`, `approved_for_rebuttal`, or `future_work_only`. Not approved = blocked.
3. **Coverage gate** — every reviewer concern ends in: `answered`, `deferred_intentionally`, or `needs_user_input`. No issue disappears.

## Workflow

### Phase 0: Resume or Initialize

1. If `rebuttal/REBUTTAL_STATE.md` exists → resume from recorded phase
2. Otherwise → create `rebuttal/`, initialize all output documents
3. Load paper, reviews, venue rules, any user-confirmed evidence

### Phase 1: Validate Inputs and Normalize Reviews

1. Validate venue rules are explicit
2. Normalize all reviewer text into `rebuttal/REVIEWS_RAW.md` (verbatim)
3. Record metadata in `rebuttal/REBUTTAL_STATE.md`
4. If ambiguous, pause and ask

### Phase 2: Atomize and Classify Reviewer Concerns

Create `rebuttal/ISSUE_BOARD.md`.

For each atomic concern:
- `issue_id` (e.g., R1-C2)
- `reviewer`, `round`, `raw_anchor` (short quote)
- `issue_type`: assumptions / theorem_rigor / novelty / empirical_support / baseline_comparison / complexity / practical_significance / clarity / reproducibility / other
- `severity`: critical / major / minor
- `reviewer_stance`: positive / swing / negative / unknown
- `response_mode`: direct_clarification / grounded_evidence / nearest_work_delta / assumption_hierarchy / narrow_concession / future_work_boundary
- `status`: open / answered / deferred / needs_user_input

### Phase 3: Build Strategy Plan

Create `rebuttal/STRATEGY_PLAN.md`.

1. Identify 2-4 **global themes** resolving shared concerns
2. Choose **response mode** per issue
3. Build **character budget** (10-15% opener, 75-80% per-reviewer, 5-10% closing)
4. Identify **blocked claims** (ungrounded or unapproved)
5. If unresolved blockers → pause and present to user

**QUICK_MODE exit**: If `QUICK_MODE = true`, stop here. Present `ISSUE_BOARD.md` + `STRATEGY_PLAN.md` to the user and summarize: how many issues per reviewer, shared vs unique concerns, recommended priorities, and evidence gaps. The user can then decide to continue with full rebuttal (`/rebuttal — quick mode: false`) or write manually.

### Phase 3.5: Evidence Sprint (when AUTO_EXPERIMENT = true)

**Skip entirely if `AUTO_EXPERIMENT` is `false` — instead, pause and present the evidence gaps to the user.**

If the strategy plan identifies issues that require new empirical evidence (tagged `response_mode: grounded_evidence` with `evidence_source: needs_experiment`):

1. Generate a mini experiment plan from the reviewer concerns:
   - What to run (ablation, baseline comparison, scale-up, condition check)
   - Success criterion (what result would satisfy the reviewer)
   - Estimated GPU-hours

2. Invoke `/experiment-bridge` with the mini plan:
   ```
   /experiment-bridge "rebuttal/REBUTTAL_EXPERIMENT_PLAN.md"
   ```

3. Wait for results, then update `ISSUE_BOARD.md`:
   - Tag completed experiments as `user_confirmed_result`
   - Update evidence source for relevant issue cards

4. If experiments fail or are inconclusive:
   - Switch response mode to `narrow_concession` or `future_work_boundary`
   - Do NOT fabricate positive results

5. Save experiment results to `rebuttal/REBUTTAL_EXPERIMENTS.md` for provenance tracking.

**Time guard**: If estimated GPU-hours exceed rebuttal deadline, skip and flag for manual handling.

### Phase 4: Draft Initial Rebuttal

Create `rebuttal/REBUTTAL_DRAFT_v1.md`.

Structure:
1. **Short opener** — thank reviewers + 2-4 global resolutions
2. **Per-reviewer numbered responses** — answer → evidence → implication
3. **Short closing** — resolved / remaining / acceptance case

Default reply pattern per issue:
- Sentence 1: direct answer
- Sentence 2-4: grounded evidence
- Last sentence: implication for the paper

Heuristics from 5 successful rebuttals:
- Evidence > assertion
- Global narrative first, per-reviewer detail second
- Concrete numbers for counter-intuitive points
- Name closest prior work + exact delta for novelty disputes
- Concede narrowly when reviewer is right
- For theory: separate core vs technical assumptions
- Answer friendly reviewers too

Hard rules:
- NEVER invent experiments, numbers, derivations, citations, or links
- NEVER promise what user hasn't approved
- If no strong evidence exists, say less not more

Also generate `rebuttal/PASTE_READY.txt` (plain text, exact character count).

Also generate `rebuttal/REVISION_PLAN.md` — the **overall revision checklist**.

This document is the single source of truth for every paper revision promised (explicitly or implicitly) in the rebuttal draft. It exists so the author can track follow-through after the rebuttal is submitted, and so the commitment gate in Phase 5 has a concrete artifact to validate against.

Structure:

1. **Header**
   - Paper title, venue, character limit, rebuttal round
   - Links back to `ISSUE_BOARD.md`, `STRATEGY_PLAN.md`, `REBUTTAL_DRAFT_v1.md`

2. **Overall checklist** — a single flat GitHub-style checklist covering **every** revision item, so the author can tick items off as they land in the camera-ready / revised PDF:

   ```markdown
   ## Overall Checklist

   - [ ] (R1-C2) Add assumption hierarchy table to Section 3.1 — commitment: `approved_for_rebuttal` — owner: author — status: pending
   - [ ] (R2-C1) Clarify novelty delta vs. Smith'24 in Section 2 related work — commitment: `already_done` — status: verify wording
   - [ ] (R3-C4) Add runtime breakdown figure to Appendix B — commitment: `future_work_only` — status: deferred, note in camera-ready
   - ...
   ```

   Checklist items must be **atomic** (one paper edit per line) and each must reference its `issue_id` so it maps back to `ISSUE_BOARD.md`.

3. **Grouped view** — the same items regrouped by (a) paper section/location and (b) severity, so the author can plan the revision pass efficiently.

4. **Commitment summary** — counts of `already_done` / `approved_for_rebuttal` / `future_work_only`, plus any `needs_user_input` items that are blocking.

5. **Out-of-scope log** — reviewer concerns that will **not** trigger a paper revision (e.g. `deferred_intentionally`, `narrow_concession` with no edit), with a one-line reason each. This keeps the checklist honest: nothing silently disappears.

Rules for `REVISION_PLAN.md`:
- Every checklist item must map to at least one `issue_id` from `ISSUE_BOARD.md`.
- Every promise in `REBUTTAL_DRAFT_v1.md` that implies a paper edit must appear as a checklist item — if it is not in the plan, it is a commitment-gate violation.
- Never add items that are not backed by the draft or by user-confirmed evidence.
- On rerun / follow-up rounds, update checkbox state in place rather than regenerating from scratch.

### Phase 5: Safety Validation

Run all lints:
1. **Coverage** — every issue maps to draft anchor
2. **Provenance** — every factual sentence has source
3. **Commitment** — promises are approved AND every paper-edit promise in the draft appears as a checklist item in `REVISION_PLAN.md` (and vice versa — no orphan items in the plan)
4. **Tone** — flag aggressive/submissive/evasive phrases
5. **Consistency** — no contradictions across reviewer replies
6. **Limit** — exact character count, compress if over (redundancy → friendly → opener → wording, never drop critical answers)

### Phase 6: Codex Reviewer Stress Test

```
spawn_agent:
  reasoning_effort: xhigh
  message: |
    Stress-test this rebuttal draft:
    [raw reviews + issue board + draft + venue rules]

    1. Unanswered or weakly answered concerns?
    2. Unsupported factual statements?
    3. Risky or unapproved promises?
    4. Tone problems?
    5. Paragraph most likely to backfire with meta-reviewer?
    6. Minimal grounded fixes only. Do NOT invent evidence.

    Verdict: safe to submit / needs revision
```

Save full response to `rebuttal/MCP_STRESS_TEST.md`. If hard safety blocker → revise before finalizing.

### Phase 7: Finalize — Two Versions

Produce **two outputs** for different purposes:

1. **`rebuttal/PASTE_READY.txt`** — the strict version
   - Plain text, exact character count, fits venue limit
   - Ready to paste directly into OpenReview / CMT / HotCRP
   - No markdown formatting, no extras

2. **`rebuttal/REBUTTAL_DRAFT_rich.md`** — the extended version
   - Same structure but with **more detail**: fuller explanations, additional evidence, optional paragraphs
   - Marked with `[OPTIONAL — cut if over limit]` for sections that exceed the strict version
   - Author can read this to understand the full reasoning, then manually decide what to keep/cut/rewrite
   - Useful for follow-up rounds — the extra material is pre-written

3. Update `rebuttal/REBUTTAL_STATE.md`
4. Refresh `rebuttal/REVISION_PLAN.md` so the overall checklist matches the final draft (add items, mark `already_done` as checked, carry forward any `pending` items)
5. Present to user:
   - `PASTE_READY.txt` character count vs venue limit
   - `REBUTTAL_DRAFT_rich.md` for review and manual editing
   - `REVISION_PLAN.md` checklist — counts of pending / approved / deferred
   - Remaining risks + lines needing manual approval

### Phase 8: Follow-Up Rounds

When new reviewer comments arrive:

1. Append verbatim to `rebuttal/FOLLOWUP_LOG.md`
2. Link to existing issues or create new ones
3. Draft **delta reply only** (not full rewrite)
4. Update `rebuttal/REVISION_PLAN.md` in place — add any new checklist items introduced by the follow-up, tick off items the author has already completed, and keep existing items' status current
5. Re-run safety lints
6. Use Codex MCP reply for continuity if useful
7. Rules: escalate technically not rhetorically; concede if reviewer is correct; stop arguing if reviewer is immovable and no new evidence exists

## Key Rules

- **Large file handling**: If Write fails, retry with Bash heredoc silently.
- **Never fabricate.** No invented evidence, numbers, derivations, citations, or links.
- **Never overpromise.** Only promise what user explicitly approved.
- **Full coverage.** Every reviewer concern tracked and accounted for.
- **Preserve raw records.** Reviews and MCP outputs stored verbatim.
- **Global + per-reviewer structure.** Shared concerns in opener.
- **Answer friendly reviewers too.** Reinforce supportive framing.
- **Meta-reviewer closing.** Summarize resolved/remaining/why accept.
- **Evidence > rhetoric.** Derivations and numbers over prose.
- **Concede selectively.** Narrow honest concessions > broad denials.
- **Don't waste space on unwinnable arguments.** Answer once, move on.
- **Respect the limit.** Character budget is a hard constraint.
- **Resume cleanly.** Continue from REBUTTAL_STATE.md on rerun.
- **Anti-hallucination citations.** Any reference added must go through DBLP → CrossRef → [VERIFY].

## Review Tracing

After each `spawn_agent` or `send_input` reviewer call, save the trace following `../shared-references/review-tracing.md`. Write files directly to `.aris/traces/rebuttal/<date>_run<NN>/`. Respect the `--- trace:` parameter when present (default: `full`).
