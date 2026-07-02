---
name: auto-review-loop
description: Autonomous multi-round research review loop. Repeatedly reviews via external reviewer backend (Codex or manual), implements fixes, and re-reviews until positive assessment or max rounds reached. Use when user says "auto review loop", "review until it passes", or wants autonomous iterative improvement.
argument-hint: [topic-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Skill, mcp__codex__codex, mcp__codex__codex-reply, mcp__manual_review__review, mcp__manual_review__review_reply
---

# Auto Review Loop: Autonomous Research Improvement

> 🔒 **Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`.** It
> already loops internally (review → fix → re-review) and the reviewer carries
> round-to-round memory in one `threadId` (`codex-reply`). An external timer
> re-enters from the top each tick — fresh `threadId`, reviewer memory reset —
> firing the verdict on wall-clock time instead of on artifact change: zero new
> signal, full token cost. If you want to schedule something, schedule the
> *external wait that precedes it* (experiments done → then run this once). See
> [`shared-references/external-cadence.md`](../shared-references/external-cadence.md).

Autonomously iterate: review → implement fixes → re-review, until the external reviewer gives a positive assessment or MAX_ROUNDS is reached.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 6/10 **AND** verdict ∈ {"ready", "almost"} — **both** must hold. This matches the operative Phase-E STOP CONDITION exactly; the verdict vocabulary is {"ready", "almost", "not ready"} (a high score with a "not ready" verdict does NOT stop the loop). Earlier wording here used `or` and a stale verdict set ("accept"/"sufficient"/"ready for submission") — that was an internal inconsistency; the `AND` form is authoritative.
- REVIEW_DOC: `review-stage/AUTO_REVIEW.md` (cumulative log) *(fall back to `./AUTO_REVIEW.md` for legacy projects)*
- REVIEWER_MODEL = `gpt-5.5` — Default model for the Codex backend. Must be an OpenAI model (e.g., `gpt-5.5`, `o3`, `gpt-4o`). Manual backend uses whatever model the user chooses.
- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for Oracle MCP, or `— reviewer: manual` for Manual Review MCP. If manual-review MCP is unavailable, stop and print the install command; do not fall back to Codex. See `shared-references/reviewer-routing.md`.
- **OUTPUT_DIR = `review-stage/`** — All review-stage outputs go here. Create the directory if it doesn't exist.
- **HUMAN_CHECKPOINT = false** — When `true`, pause after each round's review (Phase B) and present the score + weaknesses to the user. Wait for user input before proceeding to Phase C. The user can: approve the suggested fixes, provide custom modification instructions, skip specific fixes, or stop the loop early. When `false` (default), the loop runs fully autonomously.
- **COMPACT = false** — When `true`, (1) read `EXPERIMENT_LOG.md` and `findings.md` instead of parsing full logs on session recovery, (2) append key findings to `findings.md` after each round.
- **REVIEWER_DIFFICULTY = medium** — Controls how adversarial the reviewer is. Three levels:
  - `medium` (default): Current behavior — MCP-based review, the executor controls what context the reviewer sees.
  - `hard`: Adds **Reviewer Memory** (the reviewer tracks its own suspicions across rounds) + **Debate Protocol** (the executor can rebut, the reviewer rules).
  - `nightmare`: Everything in `hard` + **Codex exec reviewer reads the repo directly** via `codex exec` (the executor cannot filter what the reviewer sees) + **Adversarial Verification** (the reviewer independently checks if code matches claims).
- **RENDER_HTML = true** — When `true` (default), auto-render `review-stage/AUTO_REVIEW.md` to HTML on loop termination via `/render-html`. Uses `--no-review` (the loop itself IS the cross-model review; the HTML is a structural conversion). Set `false` to skip, or pass `— render html: false`.

> ⚠️ **Nightmare + Manual incompatibility**: If `REVIEWER_BACKEND = manual` and `REVIEWER_DIFFICULTY = nightmare`, STOP with:
> "difficulty: nightmare requires Codex CLI / codex exec and is not compatible with --reviewer: manual. Use difficulty: hard, or switch reviewer to codex."

> 💡 Override: `/auto-review-loop "topic" — compact: true, human checkpoint: true, difficulty: hard`

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

Prompt fidelity: the manual prompt must be exactly the same text that Codex would receive.
Review tracing applies equally to both backends.

## State Persistence (Compact Recovery)

Long-running loops may hit the context window limit, triggering automatic compaction. To survive this, persist state to `review-stage/REVIEW_STATE.json` after each round:

```json
{
  "round": 2,
  "threadId": "019cd392-...",
  "status": "in_progress",
  "difficulty": "medium",
  "last_score": 5.0,
  "last_verdict": "not ready",
  "pending_experiments": ["screen_name_1"],
  "timestamp": "2026-03-13T21:00:00"
}
```

**Write this file at the end of every Phase E** (after documenting the round). Overwrite each time — only the latest state matters.

**On completion** (positive assessment or max rounds), set `"status": "completed"` so future invocations don't accidentally resume a finished loop.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

## Workflow

### Initialization

1. **Check for `review-stage/REVIEW_STATE.json`** *(fall back to `./REVIEW_STATE.json` if not found — legacy path)*:
   - If neither path exists: **fresh start** (normal case, identical to behavior before this feature existed)
   - If it exists AND `status` is `"completed"`: **fresh start** (previous loop finished normally)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is older than 24 hours: **fresh start** (stale state from a killed/abandoned run — delete the file and start over)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is within 24 hours: **resume**
     - Read the state file to recover `round`, `threadId`, `last_score`, `pending_experiments`
     - Read `review-stage/AUTO_REVIEW.md` to restore full context of prior rounds *(fall back to `./AUTO_REVIEW.md`)*
     - If `pending_experiments` is non-empty, check if they have completed (e.g., check screen sessions)
     - Resume from the next round (round = saved round + 1)
     - Log: "Recovered from context compaction. Resuming at Round N."
2. Read project narrative documents, memory files, and any prior review documents. **When `COMPACT = true` and compact files exist**: read `findings.md` + `EXPERIMENT_LOG.md` instead of full `review-stage/AUTO_REVIEW.md` and raw logs — saves context window.
3. Read recent experiment results (check output directories, logs)
4. Identify current weaknesses and open TODOs from prior reviews
5. Initialize round counter = 1 (unless recovered from state file)
6. Create/update `review-stage/AUTO_REVIEW.md` with header and timestamp

### Loop (repeat up to MAX_ROUNDS)

#### Phase A: Review

**Route by REVIEWER_DIFFICULTY:**

##### Medium (default) — MCP Review

Send comprehensive context to the external reviewer using the selected backend.

*For codex backend:*

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    Review the work directly from its artifacts — executor notes are not
    evidence, so read the files yourself rather than trusting my framing:
    - Claims / paper draft: <path>
    - Methods / code under review: <path(s)>
    - Raw results (verbatim files, not a summary): <path(s)>
    - Changed since last round: <changed-file paths> — read the diff, not my description

    Please act as a senior ML reviewer (NeurIPS/ICML level). Start from the
    assumption that the work is broken somewhere — your job is to find where.
    Be adversarial. Trust nothing the author tells you — verify everything
    yourself.

    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix (experiment, analysis, or reframing)
    4. State clearly: is this READY for submission? Yes/No/Almost

    Be brutally honest. If, after genuinely trying to break it, the work holds
    up and is ready, say so clearly.
```

*For manual backend:* use `mcp__manual_review__review` with the `prompt` text above and `config: {"model_reasoning_effort": "xhigh"}`. Save the returned `threadId`.

If this is round 2+, use `mcp__codex__codex-reply` (codex) or `mcp__manual_review__review_reply` (manual) with the saved threadId.

##### Hard — MCP Review + Reviewer Memory

Same as medium, but **prepend Reviewer Memory** to the prompt. Use the selected backend.

*For codex backend:*

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    ## Your Reviewer Memory (persistent across rounds)
    [Paste full contents of REVIEWER_MEMORY.md here]

    IMPORTANT: You have memory from prior rounds. Check whether your
    previous suspicions were genuinely addressed or merely sidestepped.
    The author (Claude) controls what context you see — be skeptical
    of convenient omissions.

    Review directly from the artifacts (paths below) — read the files yourself:
    - Claims / methods / code: <path(s)>
    - Raw results: <path(s)>
    - Changed since last round: <changed-file paths> (read the raw diff)

    Please act as a senior ML reviewer (NeurIPS/ICML level).
    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix
    4. State clearly: is this READY for submission? Yes/No/Almost
    5. **Memory update**: List any new suspicions, unresolved concerns,
       or patterns you want to track in future rounds.

    Be brutally honest. Actively look for things the author might be hiding.
```

##### Nightmare — Codex Exec (GPT reads repo directly)

**Do NOT use MCP.** Instead, let GPT access the repo autonomously via `codex exec`:

```bash
codex exec "$(cat <<'PROMPT'
You are an adversarial senior ML reviewer (NeurIPS/ICML level).
This is Round N/MAX_ROUNDS of an autonomous review loop.

## Your Reviewer Memory (persistent across rounds)
[Paste full contents of REVIEWER_MEMORY.md]

## Instructions
You have FULL READ ACCESS to this repository. The author (Claude) does NOT
control what you see — explore freely. Your job is to find problems the
author might hide or downplay.

DO THE FOLLOWING:
1. Read the experiment code, results files (JSON/CSV), and logs YOURSELF
2. Verify that reported numbers match what's actually in the output files
3. Check if evaluation metrics are computed correctly (ground truth, not model output)
4. Look for cherry-picked results, missing ablations, or suspicious hyperparameter choices
5. Read NARRATIVE_REPORT.md or review-stage/AUTO_REVIEW.md for the author's claims — then verify each against code

OUTPUT FORMAT:
- Score: X/10
- Verdict: ready / almost / not ready
- Verified claims: [which claims you independently confirmed]
- Unverified/false claims: [which claims don't match the code or results]
- Weaknesses (ranked): [with MINIMUM fix for each]
- Memory update: [new suspicions and patterns to track next round]

Be adversarial. Trust nothing the author tells you — verify everything yourself.
PROMPT
)" --skip-git-repo-check 2>&1
```

**Key difference**: In nightmare mode, GPT independently reads code, result files, and logs. Claude cannot filter or curate what GPT sees. This is the closest analog to a real hostile reviewer who reads your actual paper + supplementary materials.

#### Phase B: Parse Assessment

**CRITICAL: Save the FULL raw response** from the external reviewer verbatim (store in a variable for Phase E). Do NOT discard or summarize — the raw text is the primary record.

Then extract structured fields:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

**STOP CONDITION**: If score >= 6 AND verdict ∈ {"ready", "almost"} (exact match — "not ready" does NOT qualify) → stop loop, document final state.

#### Phase B.5: Reviewer Memory Update (hard + nightmare only)

**Skip entirely if `REVIEWER_DIFFICULTY = medium`.**

After parsing the assessment, update `REVIEWER_MEMORY.md` in the project root:

```markdown
# Reviewer Memory

## Round 1 — Score: X/10
- **Suspicion**: [what the reviewer flagged]
- **Unresolved**: [concerns not yet addressed]
- **Patterns**: [recurring issues the reviewer noticed]

## Round 2 — Score: X/10
- **Previous suspicions addressed?**: [yes/no for each, with reviewer's judgment]
- **New suspicions**: [...]
- **Unresolved**: [carried forward + new]
```

**Rules**:
- Append each round, never delete prior rounds (audit trail)
- If the reviewer's response includes a "Memory update" section, copy it verbatim
- This file is passed back to the reviewer in the next round's Phase A — it is the reviewer's persistent memory
- **If the score REGRESSES round-to-round**, don't just write a new memory line:
  diff the two rounds' raw `.response.md` files in `.aris/traces/` first and find
  the exact criterion that flipped (see `shared-references/review-tracing.md`
  § *Debugging With Traces*). The memory file is a summary; the trace is evidence.

#### Phase B.6: Debate Protocol (hard + nightmare only)

**Skip entirely if `REVIEWER_DIFFICULTY = medium`.**

After parsing the review, the executor gets a chance to **rebut**:

**Step 1 — Executor Rebuttal:**

For each weakness the reviewer identified, the executor writes a structured response:

```markdown
### Rebuttal to Weakness #1: [title]
- **Accept / Partially Accept / Reject**
- **Argument**: [why this criticism is invalid, already addressed, or based on a misunderstanding]
- **Evidence**: [point to specific code, results, or prior round fixes]
```

Rules for the executor's rebuttal:
- Must be honest — do NOT fabricate evidence or misrepresent results
- Can point out factual errors in the review (reviewer misread code, wrong metric, etc.)
- Can argue a weakness is out of scope or would require unreasonable effort
- Maximum 3 rebuttals per round (pick the most impactful to contest)

**Step 2 — Reviewer Rules on Rebuttal:**

Send the executor's rebuttal back to the reviewer for a ruling:

*Hard mode — use the selected backend for the rebuttal step:*

*For codex:*
```
mcp__codex__codex-reply:
  threadId: [saved]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    The author rebuts your review:
```

*For manual:* use `mcp__manual_review__review_reply` with the same `threadId` and prompt.

The prompt content:

```
    The author rebuts your review:

    [paste executor's rebuttal]

    For each rebuttal, rule:
    - SUSTAINED (author's argument is valid, withdraw this weakness)
    - OVERRULED (your original criticism stands, explain why)
    - PARTIALLY SUSTAINED (revise the weakness to a narrower scope)

    Then update your score if any weaknesses were withdrawn.
```

*Nightmare mode (codex exec):*
```bash
codex exec "$(cat <<'PROMPT'
You are the same adversarial reviewer. The author rebuts your review:

[paste executor's rebuttal]

VERIFY the author's evidence claims yourself — read the files they reference.
Do NOT take their word for it.

For each rebuttal, rule:
- SUSTAINED (verified and valid)
- OVERRULED (evidence doesn't check out or argument is weak)
- PARTIALLY SUSTAINED (partially valid, narrow the weakness)

Update your score. Update your memory.
PROMPT
)" --skip-git-repo-check 2>&1
```

**Step 3 — Update score and action items** based on the ruling:
- SUSTAINED weaknesses: remove from action items
- OVERRULED: keep as-is
- PARTIALLY SUSTAINED: revise scope

Append the full debate transcript to `review-stage/AUTO_REVIEW.md` under the round's entry.

#### Human Checkpoint (if enabled)

**Skip this step entirely if `HUMAN_CHECKPOINT = false`.**

When `HUMAN_CHECKPOINT = true`, present the review results and wait for user input:

```
📋 Round N/MAX_ROUNDS review complete.

Score: X/10 — [verdict]
Top weaknesses:
1. [weakness 1]
2. [weakness 2]
3. [weakness 3]

Suggested fixes:
1. [fix 1]
2. [fix 2]
3. [fix 3]

Options:
- Reply "go" or "continue" → implement all suggested fixes
- Reply with custom instructions → implement your modifications instead
- Reply "skip 2" → skip fix #2, implement the rest
- Reply "stop" → end the loop, document current state
```

Wait for the user's response. Parse their input:
- **Approval** ("go", "continue", "ok", "proceed"): proceed to Phase C with all suggested fixes
- **Custom instructions** (any other text): treat as additional/replacement guidance for Phase C. Merge with reviewer suggestions where appropriate
- **Skip specific fixes** ("skip 1,3"): remove those fixes from the action list
- **Stop** ("stop", "enough", "done"): terminate the loop, jump to Termination

#### Feishu Notification (if configured)

After parsing the score, check if `~/.claude/feishu.json` exists and mode is not `"off"`:
- Send a `review_scored` notification: "Round N: X/10 — [verdict]" with top 3 weaknesses
- If **interactive** mode and verdict is "almost": send as checkpoint, wait for user reply on whether to continue or stop
- If config absent or mode off: skip entirely (no-op)

#### Phase C: Implement Fixes (if not stopping)

For each action item (highest priority first):

1. **Code changes**: Write/modify experiment scripts, model code, analysis scripts
2. **Run experiments**: Deploy to GPU server via SSH + screen/tmux
3. **Analysis**: Run evaluation, collect results, update figures/tables
4. **Documentation**: Update project notes and review document

Prioritization rules:
- Skip fixes requiring excessive compute (flag for manual follow-up)
- Skip fixes requiring external data/models not available
- Prefer reframing/analysis over new experiments when both address the concern
- Always implement metric additions (cheap, high impact)

#### Phase D: Wait for Results

If experiments were launched:
- Monitor remote sessions for completion
- Collect results from output files and logs
- **Training quality check** — if W&B is configured, invoke `/training-check` to verify training was healthy (no NaN, no divergence, no plateau). If W&B not available, skip silently. Flag any quality issues in the next review round.

#### Phase E: Document Round

Append to `review-stage/AUTO_REVIEW.md`:

```markdown
## Round N (timestamp)

### Assessment (Summary)
- Score: X/10
- Verdict: [ready/almost/not ready]
- Key criticisms: [bullet list]

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

[Paste the COMPLETE raw response from the external reviewer here — verbatim, unedited.
This is the authoritative record. Do NOT truncate or paraphrase.]

</details>

### Debate Transcript (hard + nightmare only)

<details>
<summary>Click to expand debate</summary>

**Executor Rebuttal:**
[paste rebuttal]

**Reviewer Ruling:**
[paste ruling — SUSTAINED / OVERRULED / PARTIALLY SUSTAINED for each]

**Score adjustment**: X/10 → Y/10

</details>

### Actions Taken
- [what was implemented/changed]

### Results
- [experiment outcomes, if any]

### Status
- [continuing to round N+1 / stopping]
- Difficulty: [medium/hard/nightmare]
```

**Write `review-stage/REVIEW_STATE.json`** with current round, threadId, score, verdict, and any pending experiments.

**Append to `findings.md`** (when `COMPACT = true`): one-line entry per key finding this round:

```markdown
- [Round N] [positive/negative/unexpected]: [one-sentence finding] (metric: X.XX → Y.YY)
```

Increment round counter → back to Phase A.

### Termination

When loop ends (positive assessment or max rounds):

1. Update `review-stage/REVIEW_STATE.json` with `"status": "completed"`
2. Write final summary to `review-stage/AUTO_REVIEW.md`
3. Update project notes with conclusions
4. **Write method/pipeline description** to `review-stage/AUTO_REVIEW.md` under a `## Method Description` section — a concise 1-2 paragraph description of the final method, its architecture, and data flow. This serves as input for `/paper-illustration` in Workflow 3 (so it can generate architecture diagrams automatically).
5. **Generate claims from results** — invoke `/result-to-claim` to convert experiment results from `review-stage/AUTO_REVIEW.md` into structured paper claims. Output: `CLAIMS_FROM_RESULTS.md`. This bridges Workflow 2 → Workflow 3 so `/paper-plan` can directly use validated claims instead of extracting them from scratch. If `/result-to-claim` is not available, skip silently.
6. If stopped at max rounds without positive assessment:
   - List remaining blockers
   - Estimate effort needed for each
   - Suggest whether to continue manually or pivot
7. **Feishu notification** (if configured): Send `pipeline_done` with final score progression table
8. **Render HTML view** (if `RENDER_HTML = true`, default): invoke `/render-html` on the cumulative review log:
   ```
   /render-html "review-stage/AUTO_REVIEW.md" --no-review --state review-stage/REVIEW_STATE.json
   ```
   Pass `--state` explicitly (the helper does not auto-discover the sidecar). Drop the `--state` flag if `REVIEW_STATE.json` doesn't exist. HTML lands at `review-stage/AUTO_REVIEW.html` with embedded source SHA256. **Non-blocking**: if `/render-html` fails, log the error and continue — the HTML is a convenience, not a termination prerequisite. Skip if `RENDER_HTML = false`.

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- ALWAYS use `config: {"model_reasoning_effort": "xhigh"}` for maximum reasoning depth
- Save threadId from first call; use the appropriate reply tool (`mcp__codex__codex-reply` or `mcp__manual_review__review_reply`) for subsequent rounds per the Reviewer Calling Convention
- **Anti-hallucination citations**: When adding references during fixes, NEVER fabricate BibTeX. Use the same DBLP → CrossRef → `[VERIFY]` chain as `/paper-write`: (1) `curl -s "https://dblp.org/search/publ/api?q=TITLE&format=json"` → get key → `curl -s "https://dblp.org/rec/{key}.bib"`, (2) if not found, `curl -sLH "Accept: application/x-bibtex" "https://doi.org/{doi}"`, (3) if both fail, mark with `% [VERIFY]`. Do NOT generate BibTeX from memory.
- Be honest — include negative results and failed experiments
- Do NOT hide weaknesses to game a positive score
- Implement fixes BEFORE re-reviewing (don't just promise to fix)
- **Exhaust before surrendering** — before marking any reviewer concern as "cannot address": (1) try at least 2 different solution paths, (2) for experiment issues, adjust hyperparameters or try an alternative baseline, (3) for theory issues, provide a weaker version of the result or an alternative argument, (4) only then concede narrowly and bound the damage. Never give up on the first attempt.
- If an experiment takes > 30 minutes, launch it and continue with other fixes while waiting
- Document EVERYTHING — the review log should be self-contained
- Update project notes after each round, not just at the end

## Prompt Template for Round 2+

Use the selected backend. *For codex:* `mcp__codex__codex-reply` with the saved threadId. *For manual:* `mcp__manual_review__review_reply` with the saved threadId.

```
[For codex:] mcp__codex__codex-reply:
  threadId: [saved from round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N update]

    Since your last review these files changed — read them yourself; do not
    take my word for what changed or whether it worked:
    - Changed files: <paths>
    - Raw diff: <path, or the `git diff` range>
    - Updated raw results: <result-file paths> (verbatim files, not a pasted table)

    Please re-score and re-assess. Are the remaining concerns addressed?
    Same format: Score, Verdict, Remaining Weaknesses, Minimum Fixes.
```

## Review Tracing

After each reviewer call (`mcp__codex__codex`, `mcp__codex__codex-reply`, `mcp__manual_review__review`, or `mcp__manual_review__review_reply`), save the trace following `shared-references/review-tracing.md` (Policy C — forensic; never silently skip). Use `save_trace.sh` (resolved per the chain in `shared-references/integration-contract.md` §2) or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
