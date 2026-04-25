---
name: "auto-review-loop-minimax"
description: "Provider-specific research review loop for MiniMax. Use only when the user explicitly requests MiniMax-backed review. Do not use as the default auto-review skill; use `auto-review-loop` otherwise."
---

# Auto Review Loop (MiniMax Version): Autonomous Research Improvement

Autonomously iterate: review → implement fixes → re-review, until the external reviewer gives a positive assessment or MAX_ROUNDS is reached.

## Context: $ARGUMENTS

## Routing Boundaries

- Use this skill only when the user explicitly asks for MiniMax as the review backend.
- Default auto-review requests should route to `auto-review-loop`.
- Do not route generic review-loop requests here just because MiniMax is configured.

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 6/10, or verdict contains "accept", "sufficient", "ready for submission"
- REVIEW_DOC: `review-stage/AUTO_REVIEW.md` (cumulative log) *(fall back to `./AUTO_REVIEW.md` for legacy projects)*
- REVIEWER_MODEL = `MiniMax-M2.7` — Model used via MiniMax API

## API Configuration

This skill uses MiniMax API for external review. Two methods are supported:

### Method 1: MCP Tool (Primary)

If `mcp__minimax-chat__minimax_chat` is available, use it:

```
mcp__minimax-chat__minimax_chat:
  message: |
    [Review prompt content]
  model: "MiniMax-M2.7"
  system: "You are a senior machine learning researcher..."
```

### Method 2: curl (Fallback)

If MCP is not available, use curl directly:

```bash
curl -s "https://api.minimax.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "MiniMax-M2.7",
    "messages": [
      {"role": "system", "content": "You are a senior ML researcher..."},
      {"role": "user", "content": "[Review prompt]"}
    ],
    "max_tokens": 4096
  }'
```

**API Key**: Read from `~/.codex/settings.json` under `env.MINIMAX_API_KEY`, or from environment variable.

**Why MiniMax instead of a secondary Codex agent?** Codex CLI uses OpenAI's Responses API (`/v1/responses`) which is not supported by third-party providers. See: https://github.com/openai/codex/discussions/7782

## State Persistence (Compact Recovery)

Long-running loops may hit the context window limit, triggering automatic compaction. To survive this, persist state to `review-stage/REVIEW_STATE.json` after each round:

```json
{
  "round": 2,
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

1. **Check for `review-stage/REVIEW_STATE.json`** *(fall back to `./REVIEW_STATE.json` if not found — legacy path)*:
   - If neither path exists: **fresh start** (normal case)
   - If it exists AND `status` is `"completed"`: **fresh start** (previous loop finished normally)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is older than 24 hours: **fresh start** (stale state from a killed/abandoned run — delete the file and start over)
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is within 24 hours: **resume**
     - Read the state file to recover `round`, `last_score`, `pending_experiments`
     - Read `review-stage/AUTO_REVIEW.md` to restore full context of prior rounds *(fall back to `./AUTO_REVIEW.md`)*
     - If `pending_experiments` is non-empty, check if they have completed (e.g., check screen sessions)
     - Resume from the next round (round = saved round + 1)
     - Log: "Recovered from context compaction. Resuming at Round N."
2. Read project narrative documents, memory files, and any prior review documents
3. Read recent experiment results (check output directories, logs)
4. Identify current weaknesses and open TODOs from prior reviews
5. Initialize round counter = 1 (unless recovered from state file)
6. Create/update `review-stage/AUTO_REVIEW.md` with header and timestamp

### Loop (repeat up to MAX_ROUNDS)

#### Phase A: Review

Send comprehensive context to the external reviewer.

**Check MCP availability first**, then use appropriate method:

**If MCP available (Primary):**
```
Use mcp__minimax-chat__minimax_chat tool with:
- system: "You are a senior machine learning researcher serving as a reviewer for top-tier conferences like NeurIPS, ICML, and ICLR. Provide rigorous, constructive feedback."
- prompt: [Full review prompt with context]
- model: "MiniMax-M2.7"
```

**If MCP NOT available (Fallback):**
```bash
curl -s "https://api.minimax.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "MiniMax-M2.7",
    "messages": [
      {
        "role": "system",
        "content": "You are a senior machine learning researcher serving as a reviewer for top-tier conferences like NeurIPS, ICML, and ICLR. Provide rigorous, constructive feedback."
      },
      {
        "role": "user",
        "content": "[Round N/MAX_ROUNDS of autonomous review loop]\n\n[Full research context: claims, methods, results, known weaknesses]\n[Changes since last round, if any]\n[For round 2+: Summary of previous review feedback and what was addressed]\n\nPlease act as a senior ML reviewer (NeurIPS/ICML level).\n\n1. Score this work 1-10 for a top venue\n2. List remaining critical weaknesses (ranked by severity)\n3. For each weakness, specify the MINIMUM fix (experiment, analysis, or reframing)\n4. State clearly: is this READY for submission? Yes/No/Almost\n\nBe brutally honest. If the work is ready, say so clearly."
      }
    ],
    "max_tokens": 4096
  }'
```

**Note**: Each round is a standalone API call. For round 2+, include the summary of previous reviews and changes in the prompt itself.

#### Phase B: Parse Assessment

**CRITICAL: Save the FULL raw response** from the external reviewer verbatim (store in a variable for Phase E). Do NOT discard or summarize — the raw text is the primary record.

Then extract structured fields:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

**STOP CONDITION**: If score >= 6 AND verdict contains "ready" or "almost" → stop loop, document final state.

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

### Actions Taken
- [what was implemented/changed]

### Results
- [experiment outcomes, if any]

### Status
- [continuing to round N+1 / stopping]
```

**Write `review-stage/REVIEW_STATE.json`** with current round, score, verdict, and any pending experiments.

Increment round counter → back to Phase A.

### Termination

When loop ends (positive assessment or max rounds):

1. Update `review-stage/REVIEW_STATE.json` with `"status": "completed"`
2. Write final summary to `review-stage/AUTO_REVIEW.md`
3. Update project notes with conclusions
4. If stopped at max rounds without positive assessment:
   - List remaining blockers
   - Estimate effort needed for each
   - Suggest whether to continue manually or pivot

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- Be honest — include negative results and failed experiments
- Do NOT hide weaknesses to game a positive score
- Implement fixes BEFORE re-reviewing (don't just promise to fix)
- If an experiment takes > 30 minutes, launch it and continue with other fixes while waiting
- Document EVERYTHING — the review log should be self-contained
- Update project notes after each round, not just at the end
- For round 2+, always include previous review context in the prompt
- Prefer MCP tool over curl when available (more reliable)

## Prompt Template for Round 2+

**MCP Method (Primary):**
```
mcp__minimax-chat__minimax_chat:
  model: "MiniMax-M2.7"
  system: "You are a senior machine learning researcher serving as a reviewer for top-tier conferences like NeurIPS, ICML, and ICLR. Provide rigorous, constructive feedback."
  message: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    ## Previous Review Summary (Round N-1)
    - Previous Score: X/10
    - Previous Verdict: [ready/almost/not ready]
    - Previous Key Weaknesses: [list]

    ## Changes Since Last Review
    1. [Action 1]: [result]
    2. [Action 2]: [result]
    3. [Action 3]: [result]

    ## Updated Results
    [paste updated metrics/tables]

    ## Current Research Context
    [brief summary of claims, methods, current state]

    Please re-score and re-assess:
    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix
    4. State clearly: is this READY for submission? Yes/No/Almost

    Be brutally honest. If the work is ready, say so clearly.
```

**curl Fallback:**
```bash
curl -s "https://api.minimax.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "MiniMax-M2.7",
    "messages": [
      {
        "role": "system",
        "content": "You are a senior machine learning researcher serving as a reviewer for top-tier conferences like NeurIPS, ICML, and ICLR. Provide rigorous, constructive feedback."
      },
      {
        "role": "user",
        "content": "[Round N/MAX_ROUNDS of autonomous review loop]\n\n## Previous Review Summary (Round N-1)\n- Previous Score: X/10\n- Previous Verdict: [ready/almost/not ready]\n- Previous Key Weaknesses: [list]\n\n## Changes Since Last Review\n1. [Action 1]: [result]\n2. [Action 2]: [result]\n3. [Action 3]: [result]\n\n## Updated Results\n[paste updated metrics/tables]\n\n## Current Research Context\n[brief summary of claims, methods, current state]\n\nPlease re-score and re-assess:\n1. Score this work 1-10 for a top venue\n2. List remaining critical weaknesses (ranked by severity)\n3. For each weakness, specify the MINIMUM fix\n4. State clearly: is this READY for submission? Yes/No/Almost\n\nBe brutally honest. If the work is ready, say so clearly."
      }
    ],
    "max_tokens": 4096
  }'
```


## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting
