---
name: "auto-review-loop"
description: "Autonomous multi-round research review loop. Repeatedly reviews using a secondary Codex agent, implements fixes, and re-reviews until positive assessment or max rounds reached. Use when user says \"auto review loop\", \"review until it passes\", or wants autonomous iterative improvement."
---

# Auto Review Loop: Autonomous Research Improvement

> **Codex assurance:** every base reviewer result records
> `review_independence: same-family` and `acceptance_status: provisional` in its
> trace/state artifact. A positive provisional verdict may drive fixes and stop
> the loop, but is never cross-family accepted. Reviewer failure emits BLOCKED.

Autonomously iterate: review → implement fixes → re-review, until the external reviewer gives a positive assessment or MAX_ROUNDS is reached.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 6/10 AND verdict ∈ {"ready", "almost"} — both must hold, matching the operative STOP CONDITION below. Verdict vocabulary is {"ready", "almost", "not ready"}. (Earlier wording used "or" + a stale verdict set; the AND form is authoritative.)
- REVIEW_DOC: `review-stage/AUTO_REVIEW.md` (cumulative log) *(fall back to `./AUTO_REVIEW.md` for legacy projects)*
- **OUTPUT_DIR = `review-stage/`** — All review-stage outputs go here. Create the directory if it doesn't exist.
- REVIEWER_MODEL = `gpt-5.6-sol` — Model used via a secondary Codex agent. Must be an OpenAI model (e.g., `gpt-5.6-sol`, `o3`, `gpt-4o`)
- **REVIEWER_BACKEND = `codex`** — Default: Codex reviewer agent at xhigh reasoning. Override with `--reviewer: oracle-pro` only when the user explicitly requests Oracle; if Oracle is unavailable, warn and fall back to Codex xhigh. **Same-family note:** this default reviewer is a second Codex/GPT agent — valid for Type-A completeness/drive review, but not a cross-family Type-B verdict; install a `skills-codex-claude-review` / `skills-codex-gemini-review` overlay for a cross-family acquittal (see `shared-references/reviewer-routing.md`).
- **HUMAN_CHECKPOINT = false** — When `true`, pause after each round's review (Phase B) and present the score + weaknesses to the user. Wait for user input before proceeding to Phase C. The user can: approve the suggested fixes, provide custom modification instructions, skip specific fixes, or stop the loop early. When `false` (default), the loop runs fully autonomously.
- **COMPACT = false** — When `true`, (1) read `EXPERIMENT_LOG.md` and `findings.md` instead of parsing full logs on session recovery, (2) append key findings to `findings.md` after each round.
- **REVIEWER_DIFFICULTY = medium** — Controls adversarial depth: `medium` uses normal Codex xhigh review through `spawn_agent` / `send_input`; `hard` adds Reviewer Memory and Debate Protocol; `nightmare` adds direct repository-reading adversarial verification by an independent reviewer.
- **RENDER_HTML = true** — When `true` (default), auto-render `review-stage/AUTO_REVIEW.md` to HTML on loop termination via `/render-html`. Uses `--no-review` because the loop already performed a traced same-family provisional review. Set `false` to skip.

> 💡 Override: `/auto-review-loop "topic" — compact: true, human checkpoint: true, difficulty: hard`

## Claude-Aligned Reviewer Memory and Debate

Maintain `review-stage/REVIEWER_MEMORY.md` in all difficulty modes. Phase B.5 appends the reviewer's raw response and memory update regardless of `REVIEWER_DIFFICULTY`.

- Before each reviewer call, prepend the full `REVIEWER_MEMORY.md` contents under `## Your Reviewer Memory (persistent across rounds)`.
- Tell the reviewer to check whether prior suspicions were genuinely addressed or merely sidestepped.
- Require a `Memory update` section in the reviewer response.
- After Phase B, copy the `Memory update` into `REVIEWER_MEMORY.md` before writing `REVIEW_STATE.json`.
- For `difficulty: hard` and `difficulty: nightmare`, additionally use the **Debate Protocol** after a critical review.
- In `nightmare`, launch an additional fresh adversarial reviewer with direct repository/file-reading instructions. It should read `NARRATIVE_REPORT.md` or `review-stage/AUTO_REVIEW.md` for the author's claims, then verify those claims against code, logs, result files, and paper drafts instead of trusting executor summaries.

## Instructions

In hard and nightmare modes, the reviewer must actively look for omissions, unsupported claims, cherry-picked evidence, metric mistakes, and weaknesses the executor may have downplayed.

For `difficulty: hard` and `nightmare`, use the **Debate Protocol** after a critical review:

1. Codex writes a concise rebuttal with evidence, not spin.
2. Send the rebuttal to the same reviewer via `send_input`.
3. The reviewer rules which objections are resolved, unresolved, or newly discovered.
4. Only mark a concern resolved when the reviewer accepts the rebuttal.

## State Persistence (Compact Recovery)

Long-running loops may hit the context window limit, triggering automatic compaction. To survive this, persist state to `review-stage/REVIEW_STATE.json` after each round:

```json
{
  "run_id": "run_20260713_a1b2c3d4",
  "round": 2,
  "agent_id": "019cd392-...",
  "status": "in_progress",
  "last_score": 5.0,
  "last_verdict": "not ready",
  "pending_experiments": ["screen_name_1"],
  "timestamp": "2026-03-13T21:00:00"
}
```

- **`run_id`** — Globally unique per invocation. Generated on fresh start as `run_<YYYYMMDD>_<8-char-hex>` (e.g., `run_20260713_a1b2c3d4`). Preserved across round writes. On resume, read from state file unchanged. This binds all round state and acquittal receipts to one run.

**Write this file at the end of every Phase E** (after documenting the round). Overwrite each time — only the latest round's state matters. The `run_id` field MUST persist unchanged across overwrites within the same run.

**On completion** (positive assessment or max rounds), set `"status": "completed"` so future invocations don't accidentally resume a finished loop.

### Append-Only Acquittal Receipt

In addition to the overwritable state file, maintain an **append-only** acquittal log at `review-stage/ACQUITTAL_LOG.jsonl`. Each line is a standalone JSON object recording an acquitting positive verdict:

```jsonl
{"run_id":"run_20260713_a1b2c3d4","round":3,"backend":"codex","effort":"xhigh","verdict":"ready","score":7.5,"trace_id":"trace_20260713_run03","timestamp":"2026-07-13T14:22:00Z"}
```

**Rules (non-negotiable):**

| Rule | Detail |
|------|--------|
| **Append-only** | Never delete, never truncate, never overwrite lines. Only `>>`. |
| **When to write** | At the end of Phase E, immediately after a positive verdict (score >= 6 AND verdict ∈ {"ready", "almost"}). |
| **`run_id` binding** | Every acquittal line carries the current `run_id`. Only entries whose `run_id` matches the current run are valid acquittals for stop decisions. |
| **Trace linkage** | `trace_id` MUST reference a trace artifact in `.aris/traces/`. |
| **No overwrite** | `REVIEW_STATE.json` is overwritten each round. `ACQUITTAL_LOG.jsonl` is NEVER overwritten — it is the permanent, cumulative record.

## Workflow

### Initialization

1. **Check for `review-stage/REVIEW_STATE.json`** *(fall back to `./REVIEW_STATE.json` if not found — legacy path)*:
   - If neither path exists: **fresh start** (normal case, identical to behavior before this feature existed)
     - **Generate `run_id`**: `run_<YYYYMMDD>_<8-char-hex>` (e.g., `run_20260713_a1b2c3d4`). This run_id persists across all round writes and binds acquittal receipts to this invocation.
   - If it exists AND `status` is `"completed"`: **fresh start** (previous loop finished normally — but its `ACQUITTAL_LOG.jsonl` entries are retained as an audit trail with their own `run_id`, and are NOT valid for the current run's stop gate)
     - **Generate a new `run_id`** for this invocation.
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is older than 24 hours: **fresh start** (stale state from a killed/abandoned run — delete the file and start over)
     - **Generate a new `run_id`** for this invocation.
   - If it exists AND `status` is `"in_progress"` AND `timestamp` is within 24 hours: **resume**
     - Read the state file to recover `run_id`, `round`, `agent_id`, `last_score`, `pending_experiments`
     - **Legacy backward compat**: if `run_id` is absent from the state file (pre-run_id era), generate a new `run_id` and log: "No run_id in legacy state file; assigned run_<...> for this resume."
     - Read `review-stage/AUTO_REVIEW.md` to restore full context of prior rounds *(fall back to `./AUTO_REVIEW.md`)*
     - If `pending_experiments` is non-empty, check if they have completed (e.g., check screen sessions)
     - Resume from the next round (round = saved round + 1)
     - Log: "Recovered from context compaction. Resuming at Round N."
2. Read project narrative documents, memory files, and any prior review documents. When `COMPACT = true` and compact files exist, prefer `findings.md` + `EXPERIMENT_LOG.md` over full raw logs.
3. Read recent experiment results (check output directories, logs)
4. Identify current weaknesses and open TODOs from prior reviews
5. Initialize round counter = 1 (unless recovered from state file)
6. Create/update `review-stage/AUTO_REVIEW.md` with header and timestamp

### Loop (repeat up to MAX_ROUNDS)

#### Phase A: Review

**Route by REVIEWER_DIFFICULTY:**

##### Medium (default) — Codex Review

Send comprehensive context to the external reviewer:

```
spawn_agent:
  model: gpt-5.6-sol
  reasoning_effort: xhigh
  message: |
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
```

If this is round 2+, use `send_input` with the saved agent id to maintain continuity.

##### Hard — Codex Review + Reviewer Memory

Use the same `spawn_agent` / `send_input` route as medium, but prepend the full `review-stage/REVIEWER_MEMORY.md` contents under `## Your Reviewer Memory (persistent across rounds)` and require a `Memory update` section in the reviewer response.

##### Nightmare — Independent Repository Review

Use everything in hard mode, then ask an additional fresh adversarial reviewer to verify claims against repository files, logs, result files, and paper drafts instead of trusting executor summaries. Preserve the fresh review as a separate raw response and trace. That reviewer is fresh, so it does not inherit the scope limits from the medium/hard prompt — repeat the block from [`review-scope-limits.md`](../shared-references/review-scope-limits.md) in its prompt. This is the mode with the widest repository access and the one most likely to propose defensive scaffolding.

#### Phase B: Parse Assessment

**CRITICAL: Save the FULL raw response** from the external reviewer verbatim (store in a variable for Phase E). Do NOT discard or summarize — the raw text is the primary record.

Then extract structured fields:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

#### Phase B.5: Reviewer Memory Update

After parsing the assessment, update `review-stage/REVIEWER_MEMORY.md`. Copilot backend depends on this file for round-to-round continuity (every round is a fresh process), so the update runs regardless of `REVIEWER_DIFFICULTY`:

## Your Reviewer Memory (persistent across rounds)

Pass this file back to the reviewer in the next round so it can track its own suspicions.

```markdown
# Reviewer Memory

## Round 1 — Score: X/10
- **Suspicion**: [what the reviewer flagged]
- **Unresolved**: [concerns not yet addressed]
- **Patterns**: [recurring issues the reviewer noticed]

## Round 2 — Score: X/10
- **Previous suspicions addressed?**: [yes/no for each, with reviewer judgment]
- **New suspicions**: [...]
- **Unresolved**: [carried forward + new]
```

Rules:
- Append each round; never delete prior rounds.
- If the reviewer response includes a `Memory update` section, copy it verbatim.
- If the score REGRESSES round-to-round, don't just write a new memory line:
  diff the two rounds' raw `.response.md` files in `.aris/traces/` first and
  find the exact criterion that flipped (see `shared-references/review-tracing.md`
  § *Debugging With Traces*). The memory file is a summary; the trace is evidence.
- This file is passed back to the reviewer in the next round's Phase A.

#### Phase B.5.1: Stop-Evaluation Gate

**STOP CONDITION**: If score >= 6 AND verdict ∈ {"ready", "almost"} (exact match — "not ready" does NOT qualify), decide to stop and continue through Phase E. **Do not write a receipt here**; Phase E is the single append site.

This evaluation runs AFTER Phase B.5 so the terminal-round memory is always appended to REVIEWER_MEMORY.md before exit.

#### Phase B.6: Debate Protocol (hard + nightmare only)

Skip entirely if `REVIEWER_DIFFICULTY = medium`.

After parsing the review, Codex writes a structured rebuttal for up to three high-impact weaknesses:

```markdown
### Rebuttal to Weakness #1: [title]
- **Accept / Partially Accept / Reject**
- **Argument**: [why this criticism is valid, invalid, already addressed, or out of scope]
- **Evidence**: [specific code, result file, log, prior-round fix, or paper section]
```

Send the rebuttal to the same reviewer via `send_input`:

```text
send_input:
  target: [saved reviewer id]
  message: |
    Please rule on the author's rebuttal below.
    For each contested weakness, decide: accepted / partially accepted / rejected.
    If rejected, state the minimum evidence or change required.

    [paste rebuttal + evidence]
```

Record a `### Debate Transcript (hard + nightmare only)` section in `review-stage/AUTO_REVIEW.md`. Only mark a weakness resolved if the reviewer accepts the rebuttal.

### Debate Transcript (hard + nightmare only)

In the round log, preserve the rebuttal, reviewer ruling, accepted objections, rejected objections, and any required follow-up evidence.

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

After parsing the score, check if `~/.codex/feishu.json` exists and mode is not `"off"`:
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
- **Training quality check** — if W&B is configured, invoke `/training-check` to verify training was healthy (no NaN, no divergence, no plateau). If W&B is not available, skip silently.

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

**Write `review-stage/REVIEW_STATE.json`** with current `run_id`, round, agent id, score, verdict, and any pending experiments. The `run_id` field MUST persist unchanged from initialization; do NOT regenerate it per round.

**If score >= 6 AND verdict ∈ {"ready", "almost"}:** append an acquittal line to `review-stage/ACQUITTAL_LOG.jsonl`:
```
{"run_id":"<current-run_id>","round":<N>,"backend":"codex","effort":"xhigh","verdict":"<ready|almost>","score":<score>,"trace_id":"<skill>/<YYYY-MM-DD>_run<NN>","timestamp":"<ISO8601>"}
```
Use `>>` (append), never `>`. The `trace_id` must be the actual trace directory relative to `.aris/traces/` (for example `auto-review-loop/2026-07-13_run01`), not a fabricated `trace_...` identifier.

**Append to `findings.md`** (when `COMPACT = true`): one-line entry per key finding this round.

```markdown
- [Round N] [positive/negative/unexpected]: [one-sentence finding] (metric: X.XX → Y.YY)
```

Increment round counter → back to Phase A.

#### Review Tracing

## Review Tracing

After every `spawn_agent`, `send_input`, `oracle-pro`, or nightmare adversarial verification call, save a trace following `../shared-references/review-tracing.md`. Include prompt summary, reviewer route, saved agent id, raw response path, score/verdict, accepted fixes, rejected rebuttals, and the `Reviewer Memory` update if present.

### Termination

When loop ends (positive assessment or max rounds):

1. Update `review-stage/REVIEW_STATE.json` with `"status": "completed"`
2. Write final summary to `review-stage/AUTO_REVIEW.md`
3. Update project notes with conclusions
4. **Write method/pipeline description** to `review-stage/AUTO_REVIEW.md` under a `## Method Description` section — a concise 1-2 paragraph summary of the final method, architecture, and data flow. This serves as direct input for `/paper-illustration`.
5. **Generate claims from results** — invoke `/result-to-claim` to convert experiment results from `review-stage/AUTO_REVIEW.md` into structured paper claims. Output: `CLAIMS_FROM_RESULTS.md`. If `/result-to-claim` is not installed, skip this step (no `CLAIMS_FROM_RESULTS.md` is produced; `/paper-plan` extracts claims from the narrative as before) — but NEVER fabricate the file or its verdict. If it ran but its output starts with `verdict: REVIEW_UNAVAILABLE`, keep that file AS-IS (do not overwrite or paraphrase it) and record in `AUTO_REVIEW.md` that claims are UNADJUDICATED — downstream paper stages must not treat them as validated.
6. If stopped at max rounds without positive assessment:
   - List remaining blockers
   - Estimate effort needed for each
   - Suggest whether to continue manually or pivot
7. **Feishu notification** (if configured): Send `pipeline_done` with final score progression table
8. **Render HTML view** (if `RENDER_HTML = true`, default): invoke `/render-html` on the cumulative review log:
   ```
   /render-html "review-stage/AUTO_REVIEW.md" --no-review --state review-stage/REVIEW_STATE.json
   ```
   Pass `--state` explicitly when `REVIEW_STATE.json` exists (the helper does not auto-discover the sidecar). HTML lands at `review-stage/AUTO_REVIEW.html` with embedded source SHA256. **Non-blocking**: if `/render-html` fails, log the error and continue — the HTML is a convenience, not a termination prerequisite.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- ALWAYS use `reasoning_effort: xhigh` for maximum reasoning depth
- Save agent id from first call, use `send_input` for subsequent rounds
- Be honest — include negative results and failed experiments
- Do NOT hide weaknesses to game a positive score
- Implement fixes BEFORE re-reviewing (don't just promise to fix)
- If an experiment takes > 30 minutes, launch it and continue with other fixes while waiting
- Document EVERYTHING — the review log should be self-contained
- Update project notes after each round, not just at the end

## Prompt Template for Round 2+

```
send_input:
  target: [saved from round 1]
  # inherits the agent's model/effort — do not re-send
  message: |
    [Round N update]

    Since your last review these files changed — read them yourself; do not
    take my word for what changed or whether it worked:
    - Changed files: <paths>
    - Raw diff: <path, or the `git diff` range>
    - Updated raw results: <result-file paths> (verbatim files, not a pasted table)

    Please re-score and re-assess. Are the remaining concerns addressed?
    Same format: Score, Verdict, Remaining Weaknesses, Minimum Fixes.

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
```

## Acquittal Gate Test Specifications

The following test cases validate the `run_id` + append-only acquittal receipt mechanism.

### Test 1: Fresh Start — Codex Acquits

**Setup:** Delete `review-stage/REVIEW_STATE.json` and `review-stage/ACQUITTAL_LOG.jsonl`. Run review.

**Action:** Codex round 1 returns score=7, verdict="ready".

**Expected:** Phase E writes acquittal line to `ACQUITTAL_LOG.jsonl` with current `run_id`. Loop stops.

### Test 2: Stale Completed State — Old Run's Acquittal Does NOT Satisfy New Run

**Setup:** Run 1 (run_id=`run_20260713_aaaaaaaa`) completes with `status: "completed"` and writes acquittal: `{"run_id":"run_20260713_aaaaaaaa","backend":"codex","verdict":"ready","score":7}` to `ACQUITTAL_LOG.jsonl`. Then a fresh-start invocation generates run_id=`run_20260713_bbbbbbbb`.

**Action:** Run 2 round 1 returns score=5, verdict="not ready". Continue to round 2, score=8, verdict="ready".

**Expected:** Run 2's acquittal line has `run_id=run_20260713_bbbbbbbb`. The old acquittal with `run_id=run_20260713_aaaaaaaa` is an audit artifact only. The stop gate for run 2 uses the current-run acquittal.

### Test 3: Legacy State File — No run_id Field

**Setup:** Create a `REVIEW_STATE.json` with `status: "in_progress"`, a fresh timestamp, but NO `run_id` field. Resume.

**Expected:** Initialization detects missing `run_id` and generates one. Log: "No run_id in legacy state file; assigned run_<...> for this resume."

### Test 4: Append-Only Integrity

**Setup:** Run 1 reaches a positive verdict, appends one receipt, and stops. Start Run 2 with a new `run_id`; it also reaches a positive verdict and appends one receipt.

**Action:** After the loop, inspect `ACQUITTAL_LOG.jsonl`.

**Expected:** File contains exactly 2 lines with different run IDs. Run 1's line remains unchanged after Run 2 appends; a stopped loop cannot continue to a later positive round.
