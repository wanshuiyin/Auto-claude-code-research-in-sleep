---
name: auto-review-loop
description: Autonomous multi-round research review loop. Repeatedly reviews via Codex MCP, implements fixes, and re-reviews until positive assessment or max rounds reached. Use when user says "auto review loop", "review until it passes", or wants autonomous iterative improvement.
argument-hint: [topic-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Auto Review Loop: Autonomous Research Improvement

Autonomously iterate: review → implement fixes → re-review, until the external reviewer gives a positive assessment or MAX_ROUNDS is reached.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 6/10, or verdict contains "accept", "sufficient", "ready for submission"
- REVIEW_DOC: `AUTO_REVIEW.md` in project root (cumulative log)
- REVIEWER_MODEL = `gpt-5.4` — Model used via Codex MCP. Must be an OpenAI model (e.g., `gpt-5.4`, `o3`, `gpt-4o`)
- **HUMAN_CHECKPOINT = false** — When `true`, pause after each round's review (Phase B) and present the score + weaknesses to the user. Wait for user input before proceeding to Phase C. The user can: approve the suggested fixes, provide custom modification instructions, skip specific fixes, or stop the loop early. When `false` (default), the loop runs fully autonomously.

> 💡 Override: `/auto-review-loop "topic" — human checkpoint: true`

## State Persistence (Compact Recovery)

Long-running loops may hit the context window limit, triggering automatic compaction. To survive this, persist state to `REVIEW_STATE.json` after each round:

```json
{
  "round": 2,
  "threadId": "019cd392-...",
  "status": "in_progress",
  "last_score": 5.0,
  "last_verdict": "not ready",
  "pending_experiments": ["screen_name_1"],
  "timestamp": "2026-03-13T21:00:00"
}
```

**Write this file at the end of every Phase E** (after documenting the round). Overwrite each time — only the latest state matters.

**On completion** (positive assessment or max rounds), set `"status": "completed"` so future invocations don't accidentally resume a finished loop.

## Workflow

### Initialization

1. **Check for `REVIEW_STATE.json`** in project root:
   - If it does not exist: **fresh start** (normal case, identical to behavior before this feature existed)
   - If it exists AND `status` is `"completed"`: **fresh start** (previous loop finished normally)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is older than 24 hours: **fresh start** (stale state from a killed/abandoned run — delete the file and start over)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is within 24 hours: **resume**
     - Read the state file to recover `round`, `threadId`, `last_score`, `pending_experiments`
     - Read `AUTO_REVIEW.md` to restore full context of prior rounds
     - If `pending_experiments` is non-empty, check if they have completed (e.g., check screen sessions)
     - Resume from the next round (round = saved round + 1)
     - Log: "Recovered from context compaction. Resuming at Round N."
2. Read project narrative documents, memory files, and any prior review documents
3. Read recent experiment results (check output directories, logs)
4. Identify current weaknesses and open TODOs from prior reviews
5. Initialize round counter = 1 (unless recovered from state file)
6. Create/update `AUTO_REVIEW.md` with header and timestamp

### Loop (repeat up to MAX_ROUNDS)

#### Phase A: Review

Send comprehensive context to the external reviewer:

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    [Full research context: claims, methods, results, known weaknesses]
    [Changes since last round, if any]

    Please act as a senior ML reviewer (NeurIPS/ICML level).

    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix (experiment, analysis, or reframing)
    4. State clearly: is this READY for submission? Yes/No/Almost

    Be brutally honest. If the work is ready, say so clearly.
```

If this is round 2+, use `mcp__codex__codex-reply` with the saved threadId to maintain conversation context.

#### Phase B: Parse Assessment

**CRITICAL: Save the FULL raw response** from the external reviewer verbatim (store in a variable for Phase E). Do NOT discard or summarize — the raw text is the primary record.

Then extract structured fields:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

**STOP CONDITION**: If score >= 6 AND verdict contains "ready" or "almost" → stop loop, document final state.

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

#### Phase E: Document Round

Append to `AUTO_REVIEW.md`:

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

### Actions Taken
- [what was implemented/changed]

### Results
- [experiment outcomes, if any]

### Status
- [continuing to round N+1 / stopping]
```

**Write `REVIEW_STATE.json`** with current round, threadId, score, verdict, and any pending experiments.

Increment round counter → back to Phase A.

### Termination

When loop ends (positive assessment or max rounds):

1. Update `REVIEW_STATE.json` with `"status": "completed"`
2. Write final summary to `AUTO_REVIEW.md`
3. Update project notes with conclusions
4. If stopped at max rounds without positive assessment:
   - List remaining blockers
   - Estimate effort needed for each
   - Suggest whether to continue manually or pivot
5. **Feishu notification** (if configured): Send `pipeline_done` with final score progression table

## Key Rules

- ALWAYS use `config: {"model_reasoning_effort": "xhigh"}` for maximum reasoning depth
- Save threadId from first call, use `mcp__codex__codex-reply` for subsequent rounds
- Be honest — include negative results and failed experiments
- Do NOT hide weaknesses to game a positive score
- Implement fixes BEFORE re-reviewing (don't just promise to fix)
- If an experiment takes > 30 minutes, launch it and continue with other fixes while waiting
- Document EVERYTHING — the review log should be self-contained
- Update project notes after each round, not just at the end

## Prompt Template for Round 2+

```
mcp__codex__codex-reply:
  threadId: [saved from round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N update]

    Since your last review, we have:
    1. [Action 1]: [result]
    2. [Action 2]: [result]
    3. [Action 3]: [result]

    Updated results table:
    [paste metrics]

    Please re-score and re-assess. Are the remaining concerns addressed?
    Same format: Score, Verdict, Remaining Weaknesses, Minimum Fixes.
```
