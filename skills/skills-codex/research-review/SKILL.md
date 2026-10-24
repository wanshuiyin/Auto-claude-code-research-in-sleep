---
name: "research-review"
description: "Get a deep critical review of research from a fresh Codex agent or a selected Gemini, Grok, or Claude Code reviewer. Use when user says \"review my research\", \"help me review\", \"get external review\", or wants critical feedback on research ideas, papers, or experimental results."
---

# Research Review with a Selectable Reviewer

> **Codex assurance:** the fresh base reviewer is same-family. Record
> `review_independence: same-family` and `acceptance_status: provisional` in
> traces and deliverables. A selected reviewer can record cross-family accepted
> only after a completed, in-scope positive review with actual different model
> families; an unavailable reviewer is BLOCKED, never a fabricated PASS.

Get a multi-round critical review of research work from an external LLM with maximum reasoning depth.

## Constants

- REVIEWER_MODEL = `gpt-6-astra` — Model used via a secondary Codex agent, reasoning effort `ultra` (deep-audit tier). Must be an OpenAI model (e.g., `gpt-6-astra`, `gpt-6.1-sol`)
- **REVIEWER_BACKEND = `codex`** — Default: a fresh Codex reviewer at the deep-audit tier (`ultra`). Resolve `— reviewer:`, project `.aris/reviewer.json`, then this default using `reviewer_route.py` (`--host codex --tier deep`), per [reviewer-backends.md](../shared-references/reviewer-backends.md). Gemini/Antigravity, Grok, and Claude Code use that contract at every call below; legacy `oracle-pro` rules remain in `reviewer-routing.md`.

## Context: $ARGUMENTS

## Prerequisites

- The selected review tool must be available. Native Codex uses authorized `spawn_agent` and `send_input`; MCP routes use their own first/reply tools.
- If the selected reviewer is unavailable, record `REVIEW_UNAVAILABLE`. The executor reviewing itself does not satisfy the fresh-reviewer requirement.

## Workflow

### Step 1: Gather Research Context
Before calling the external reviewer, compile a comprehensive briefing:
1. Read project narrative documents (e.g., STORY.md, README.md, paper drafts)
2. Read any memory/notes files for key findings and experiment history
3. Identify: core claims, methodology, key results, known weaknesses

### Step 2: Initial Review (Round 1)
Save the resolved route and its session id/cwd. Send the following substantive
prompt through the selected first-call tool, with primary artifact paths inside
the review workspace. The native Codex example uses ultra reasoning:

```
spawn_agent:
  model: gpt-6-astra
  reasoning_effort: ultra
  message: |
    [Original research question, author claims, specific questions, and primary
    artifact/raw-result paths. Read those files to check the claims yourself.]
    Please act as a senior ML reviewer (NeurIPS/ICML level). Start from the
    assumption that the work is broken somewhere — your job is to find where.
    Be adversarial. Trust nothing the author tells you — verify everything
    yourself. Identify:
    1. Logical gaps or unjustified claims
    2. Missing experiments that would strengthen the story
    3. Narrative weaknesses
    4. Whether the contribution is sufficient for a top venue

    === SCOPE LIMITS (these bound what you PROPOSE, never what you look for) ===
    Report anything that is actually wrong here — including a rare-looking case, if
    this repo actually produces it. Then keep the fix in scope:
    1. This is a RESEARCH-WORKFLOW tool, not a security paper. Verification is
       welcome; over-defense is not. Assume a cooperating operator on their own
       machine — a malicious local user is NOT in the threat model.
    2. Do NOT propose SHA / hash / content-fingerprint / digest-binding schemes.
       Reporting a real defect in hashing code that already exists is fine.
    3. NO speculative machinery: do not add feature flags, migration frameworks,
       compat layers, wrappers, pins, or similar mechanisms unless evidence shows
       a current repo defect they fix or an explicit existing invariant they must
       preserve. "Load-bearing", "compatibility", and "not scaffolding" are labels,
       not evidence. Point to the failing path/artifact or invariant, and check the
       proposal's factual premises, such as whether a named package version exists.
    4. NO corner-case obsession: exotic encodings, symlink races, RTL text and
       millisecond races are out of scope unless you can show the case arises here.
    5. Where a rubric or checklist is genuinely needed, do not over-mechanize
       judgement. A clear sentence a human reads beats a scored table nobody
       maintains.
    Exception: code that runs remote commands, starts a network service, or installs
    an MCP server runs on the user's machine with their credentials — trust-boundary
    findings there are in scope and the default is strict.
    Say plainly when something is correct. Do not manufacture findings.
    Be brutally honest. If, after genuinely trying to break it, the work
    holds up and is ready, say so clearly.
```

### Step 3: Iterative Dialogue (Rounds 2-N)
Use the selected continuation tool with the saved session id. Preserve its
model and cwd; for native Codex this is `send_input`:

```text
send_input:
  target: [saved reviewer id from Step 2]
  message: |
    Please continue the review using the revised materials below.

    Revised files:
    - /absolute/path/to/file1
    - /absolute/path/to/file2

    Focus on unresolved weaknesses and whether the revision actually fixed them.
```

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

If `— composed: <canonical-report-path>` is explicitly present, fold consensus,
claims matrix, TODOs, and trace links into that report instead of writing a
standalone review document. Without the directive, write the standalone review
as documented; never infer composed mode from an existing file. `— standalone`
always wins. See
[`output-composition.md`](../shared-references/output-composition.md).

### Step 6: Review Tracing

Save a trace for every reviewer call following `../shared-references/review-tracing.md`. Record the resolved route, session id/cwd, requested and actual reported model/effort, prompt, raw response, decisions, and action items. Check successful completion and required file coverage before assigning a verdict. Record model-family independence and acceptance using `reviewer-backends.md`; agreement alone does not establish cross-family acceptance.

## Key Rules

- For the default Codex route, use `model: gpt-6-astra` + `reasoning_effort: ultra` (deep-audit tier; capability fallback per `reviewer-routing.md`, never below `xhigh`). Other selected routes use their resolved model/effort.
- Provide comprehensive context and primary files in Round 1; require artifact-grounded verification. An unreadable file is missing evidence.
- Be honest about weaknesses — hiding them leads to worse feedback
- Push back on criticisms you disagree with, but accept valid ones
- Focus on ACTIONABLE feedback — "what experiment would fix this?"
- Document the agent id for potential future resumption
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
