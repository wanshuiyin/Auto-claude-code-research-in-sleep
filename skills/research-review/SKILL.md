---
name: research-review
description: Get a deep critical review of research from an external reviewer backend (Codex or manual). Use when user says "review my research", "help me review", "get external review", or wants critical feedback on research ideas, papers, or experimental results.
argument-hint: [topic-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, mcp__codex__codex, mcp__codex__codex-reply, mcp__manual_review__review, mcp__manual_review__review_reply
---

# Research Review via External Reviewer Backend (xhigh reasoning)

> 🔒 **Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`.** It is
> verdict-bearing — it produces a cross-model review verdict, multi-round with
> reviewer thread continuity. An external timer re-fires the verdict on
> wall-clock time and breaks the reviewer's round-to-round memory: zero new
> signal, full token cost. Schedule the *external wait that precedes it* (work
> ready → then review once), not the verdict. See
> [`shared-references/external-cadence.md`](../shared-references/external-cadence.md).

Get a multi-round critical review of research work from the selected external reviewer backend with maximum reasoning depth.

## Constants

- REVIEWER_MODEL = `gpt-5.5` — Default model for the Codex backend. Must be an OpenAI model (e.g., `gpt-5.5`, `o3`, `gpt-4o`). Manual backend uses whatever model the user chooses.
- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for Oracle MCP, or `— reviewer: manual` for Manual Review MCP. If manual-review MCP is unavailable, stop and print the install command; do not fall back to Codex. See `shared-references/reviewer-routing.md`.

## Reviewer Calling Convention

When calling the reviewer, branch on REVIEWER_BACKEND:

**If REVIEWER_BACKEND = `codex`:**
  Use `mcp__codex__codex` for new review threads.
  Use `mcp__codex__codex-reply` for follow-up rounds (reuse threadId).

**If REVIEWER_BACKEND = `manual`:**
  Use `mcp__manual_review__review` for new review threads with:
    prompt: [exact same prompt that would go to Codex]
    config: {"model_reasoning_effort": "xhigh"}
  Save the returned `threadId`.
  Use `mcp__manual_review__review_reply` for follow-up rounds with:
    threadId: [saved manual-review threadId]
    prompt: [follow-up prompt]
    config: {"model_reasoning_effort": "xhigh"}

Content fidelity: the manual reviewer should see the same substantive review
brief Codex would read. If the manual UI supports file upload / attachment,
reuse the same brief file; otherwise paste the brief contents inline because
remote web UIs cannot read your local filesystem paths. Review tracing applies
equally to both backends.

## Context: $ARGUMENTS

## Prerequisites

- **Codex MCP Server** configured in Claude Code:
  ```bash
  claude mcp add codex -s user -- codex mcp-server
  ```
- This gives Claude Code access to `mcp__codex__codex` and `mcp__codex__codex-reply` tools

## Workflow

### Step 1: Gather Research Context
Before calling the external reviewer, compile a comprehensive briefing:
1. Read project narrative documents (e.g., STORY.md, README.md, paper drafts)
2. Read any memory/notes files for key findings and experiment history
3. Identify: core claims, methodology, key results, known weaknesses

### Step 2: Initial Review (Round 1)
Send a detailed prompt with xhigh reasoning, using the selected backend. For
the `codex` backend, keep the MCP payload short: write the full briefing to
`RESEARCH_REVIEW_REQUEST.md`, then point Codex at that file.

*For codex backend:*

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Read the review brief at <absolute path to RESEARCH_REVIEW_REQUEST.md>.
    Executor notes are not evidence beyond the files they cite, so verify the
    referenced artifacts before judging.
    Please act as a senior ML reviewer (NeurIPS/ICML level). Identify:
    1. Logical gaps or unjustified claims
    2. Missing experiments that would strengthen the story
    3. Narrative weaknesses
    4. Whether the contribution is sufficient for a top venue
    Please be brutally honest.
```

The review brief should contain the full research context, the specific
questions, and the primary artifact / raw-result paths the reviewer should
inspect.

*For manual backend:* use `mcp__manual_review__review` with the same brief
contents. If the manual-review UI supports attachments, attach
`RESEARCH_REVIEW_REQUEST.md`; otherwise paste the brief inline. Save the
returned `threadId`.

### Step 3: Iterative Dialogue (Rounds 2-N)
For `codex` backend: use `mcp__codex__codex-reply` with the returned `threadId`.
For `manual` backend: use `mcp__manual_review__review_reply` with the same `threadId`.
Use the appropriate tool to continue the conversation. For Codex follow-up
rounds, write an updated brief such as `RESEARCH_REVIEW_ROUND_2.md` and send
only the path:

```text
mcp__codex__codex-reply:
  threadId: [saved reviewer threadId from Step 2]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Read the updated review brief at <absolute path to
    RESEARCH_REVIEW_ROUND_2.md>.
    Focus on unresolved weaknesses and whether the revision actually fixed them.
```

For manual follow-up rounds, attach that same updated brief if possible;
otherwise paste it inline.

For each round:
1. **Respond** to criticisms with evidence/counterarguments
2. **Ask targeted follow-ups** on the most actionable points
3. **Request specific deliverables**: experiment designs, paper outlines, claims matrices

Key follow-up patterns:
- "If we reframe X as Y, does that change your assessment?"
- "What's the minimum experiment to satisfy concern Z?"
- "Please design the minimal additional experiment package (highest acceptance lift per GPU week)"
- "Please write a mock NeurIPS/ICML review with scores"
- "Give me a results-to-claims matrix for possible experimental outcomes"

### Step 4: Convergence
Stop iterating when:
- Both sides agree on the core claims and their evidence requirements
- A concrete experiment plan is established
- The narrative structure is settled

### Step 5: Document Everything
Save the full interaction and conclusions to a review document in the project root:
- Round-by-round summary of criticisms and responses
- Final consensus on claims, narrative, and experiments
- Claims matrix (what claims are allowed under each possible outcome)
- Prioritized TODO list with estimated compute costs
- Paper outline if discussed

Update project memory/notes with key review conclusions.

> **Composed mode** — if invoked with `— composed: <canonical-report-path>` (an
> orchestrator like `/idea-discovery` passes this), do **not** write a standalone review
> `.md` in the project root. The raw conversation is already persisted to `.aris/traces/…`
> (see *Review Tracing* below — that audit copy is kept in every mode); fold the review
> *conclusions* (consensus, claims matrix, prioritized TODOs) into the orchestrator's
> canonical report and cite the trace path there. **Default (no `— composed:` directive):
> behave exactly as above — write the standalone review document.** Never infer composed
> mode from a report file merely existing. Full rules:
> [`shared-references/output-composition.md`](../shared-references/output-composition.md).

## Key Rules

- ALWAYS use `config: {"model_reasoning_effort": "xhigh"}` for reviews
- Put comprehensive context in the review brief. Codex can read local files
  when you pass an absolute path; manual reviewers usually cannot, so attach or
  paste the same brief there.
- Be honest about weaknesses — hiding them leads to worse feedback
- Push back on criticisms you disagree with, but accept valid ones
- Focus on ACTIONABLE feedback — "what experiment would fix this?"
- Document the threadId for potential future resumption
- The review document should be self-contained (readable without the conversation)

## Prompt Templates

### For initial review:
"I'm going to present a complete ML research project for your critical review. Please act as a senior ML reviewer (NeurIPS/ICML level)..."

### For experiment design:
"Please design the minimal additional experiment package that gives the highest acceptance lift per GPU week. Our compute: [describe]. Be very specific about configurations."

### For paper structure:
"Please turn this into a concrete paper outline with section-by-section claims and figure plan."

### For claims matrix:
"Please give me a results-to-claims matrix: what claim is allowed under each possible outcome of experiments X and Y?"

### For mock review:
"Please write a mock NeurIPS review with: Summary, Strengths, Weaknesses, Questions for Authors, Score, Confidence, and What Would Move Toward Accept."

## Review Tracing

After each reviewer call (`mcp__codex__codex`, `mcp__codex__codex-reply`, `mcp__manual_review__review`, or `mcp__manual_review__review_reply`), save the trace following `shared-references/review-tracing.md` (Policy C — forensic; never silently skip). Use `save_trace.sh` (resolved per the chain in `shared-references/integration-contract.md` §2) or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
