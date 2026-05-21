# Loop Usage Monitor — Design Spec

**Date:** 2026-05-21
**Status:** Approved, ready for implementation plan
**Scope:** Prevent the `auto-review-loop*` skills from burning through Claude.ai / ChatGPT subscription quota when running unattended.

## Problem

The user runs auto-review-loop skills with Claude Opus 4.7 as executor (via Claude OAuth subscription) and Codex GPT-5.5 as reviewer (via Codex OAuth subscription, per PR #231). Neither Anthropic nor OpenAI exposes a "remaining subscription quota" API, so a runaway loop can exhaust the 5-hour window with no warning. The user wants a guardrail that stops the loop before it hits the real subscription cap — especially on the Claude side, where executor turns are heavy.

## Non-goals

- Not a true rate limiter — skill instructions are advisory; this is a budget tool the loop is *told* to consult.
- Not a token accountant in v1 — counts iterations only.
- Not protection against interactive (non-loop) Claude/Codex use on the same machine.
- No auto-resume after the window resets. User restarts the loop manually.

## Components

```
tools/loop_budget.py                                       ← new
tests/test_loop_budget.py                                  ← new
skills/shared-references/loop-budget-resolution.md         ← new (resolver doc for skills)
skills/shared-references/integration-contract.md           ← edited: add Policy A row
skills/auto-review-loop/SKILL.md                           ← edited: resolver + pre-iter check + post-call record
skills/auto-review-loop-llm/SKILL.md                       ← edited: same
skills/auto-review-loop-minimax/SKILL.md                   ← edited: same
~/.aris/usage/loop-usage.jsonl                             ← new (auto-created at first record)
```

No daemon, no provider API calls. **No edit to `install_aris.sh`** — that installer already symlinks `.aris/tools → <repo>/tools` as a directory (per `S12`), so any file added to `tools/` becomes resolvable in downstream projects automatically.

## `tools/loop_budget.py` — interface

Three subcommands. Single Python file, stdlib-only (no third-party deps).

### `check --side {claude|codex}`

- Reads `~/.aris/usage/loop-usage.jsonl`.
- Filters records whose `ts` is within the rolling window for that side (`CLAUDE_LOOP_WINDOW_HOURS` or `CODEX_LOOP_WINDOW_HOURS`).
- Counts records matching `--side`.
- Compares to the per-side cap (`CLAUDE_LOOP_MAX_ITERATIONS` / `CODEX_LOOP_MAX_ITERATIONS`).
- Exit codes:
  - `0` — under budget. Prints a one-line status to stderr (`[budget] claude 7/15 in 5h window, ok`).
  - `2` — at or over budget. Prints stop reason + next-window-reset time, computed as `oldest_in_window_ts + window_hours`, formatted as local time.
  - `1` — bad arguments / unreadable state file.
- At ≥ `CLAUDE_LOOP_WARN_AT` (default `0.8`) utilization, still exits `0` but prints `[budget warning] claude 12/15 (80%), 3 iterations until cap`.

### `record --side {claude|codex} --skill <skill-name>`

- Appends one JSON line: `{"ts": "<utc-iso8601-Z>", "side": "...", "skill": "..."}`.
- Creates `~/.aris/usage/` and the JSONL file if missing.
- Exit `0` on success, `1` on I/O error.

### `status`

- Human-readable summary of current usage per side.
- Example:
  ```
  claude: 12/15 in 5h window (80%) — next slot frees at 14:03 local
  codex:   7/30 in 5h window (23%) — plenty of headroom
  ```
- Exit `0` always.

## State file: `~/.aris/usage/loop-usage.jsonl`

- Append-only JSON Lines.
- One record per `record` call.
- No rotation in v1 — file grows unbounded but at ≤ ~100 lines/day it's negligible. Rotation can be added later if needed.
- No file locking in v1 — only one loop runs at a time on a single machine.
- Schema:
  ```json
  {"ts": "2026-05-21T14:03:11Z", "side": "claude", "skill": "auto-review-loop"}
  ```
  `ts` is UTC ISO-8601 with `Z` suffix. `side` ∈ `{"claude", "codex"}`. `skill` is free-form, used only for `status` output / debugging.

## Configuration (environment variables)

| Variable                         | Default | Meaning                                              |
|----------------------------------|---------|------------------------------------------------------|
| `CLAUDE_LOOP_MAX_ITERATIONS`     | `15`    | Cap on Claude (executor) iterations per window       |
| `CLAUDE_LOOP_WINDOW_HOURS`       | `5`     | Rolling window length for Claude                     |
| `CODEX_LOOP_MAX_ITERATIONS`      | `30`    | Cap on Codex (reviewer) iterations per window        |
| `CODEX_LOOP_WINDOW_HOURS`        | `5`     | Rolling window length for Codex                      |
| `CLAUDE_LOOP_WARN_AT`            | `0.8`   | Utilization fraction at which `check` emits warning  |
| `ARIS_USAGE_DIR`                 | `~/.aris/usage` | Override state directory (mainly for tests)   |

Rationale for defaults: Claude cap is intentionally lower because executor turns are heavy (long tool-use chains, large contexts inflate the per-message quota burn). Codex cap is roomier because the reviewer is one short turn per iteration. Both are conservative starting points for a $100 subscription; user is expected to tune after observing `status` output for a week.

## Skill integration

### Helper-resolution policy

`loop_budget.py` is invoked from three SKILL.md files, so per `skills/shared-references/integration-contract.md` it is in-scope for the per-helper policy table and must use the standard resolution chain (`.aris/tools/` → `tools/` → `$ARIS_REPO/tools/`), not hardcoded repo-root paths. Policy assignment: **Policy A (gate)** — the tool's exit code IS the gate; if it cannot be resolved, the loop must refuse to run rather than proceed unmonitored.

The implementation must:

1. Place the script at `tools/loop_budget.py`. Because `install_aris.sh` symlinks `.aris/tools → tools` (rule `S12`), the first resolver layer auto-resolves in downstream projects with no installer change.
2. Add a row to the per-helper policy table in `skills/shared-references/integration-contract.md` classifying it as Policy A with the rationale "Exit code is the gate for subscription quota; unresolved means the loop cannot enforce its budget."
3. Add a dedicated resolver doc at `skills/shared-references/loop-budget-resolution.md` (mirroring `wiki-helper-resolution.md` / `review-tracing.md`) so the three loop skills reference one place instead of duplicating the resolver block.

### Skill patch

Each of the three loop skills has a per-iteration step. The patch adds two surrounding hooks. The skill resolves the helper via the standard chain, then uses it via the resolved env var:

> **Before each iteration:**
> 1. `python3 "$LOOP_BUDGET_SCRIPT" check --side claude` — if exit code is non-zero, stop the loop and print the message the tool produced. Do not call the executor.
> 2. `python3 "$LOOP_BUDGET_SCRIPT" check --side codex` — same, before the reviewer call.
>
> **After each successful call:**
> 3. After a successful executor turn: `python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill <this-skill-name>`.
> 4. After a successful reviewer turn: `python3 "$LOOP_BUDGET_SCRIPT" record --side codex --skill <this-skill-name>`.
>
> **Unresolved-helper fallback (Policy A):**
> If `LOOP_BUDGET_SCRIPT` is empty, the skill MUST refuse to start the loop with `ERROR: loop_budget.py not resolved; rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/.` and exit. Loops never run unmonitored.

`auto-review-loop-llm` and `auto-review-loop-minimax` use different reviewer backends but still consume Codex-side budget if (and only if) the reviewer is configured to use the codex-cli backend. **For v1 we always record `--side codex` after a reviewer turn regardless of backend**, on the rationale that the user explicitly stated the Codex OAuth reviewer is the target. If a future user runs `auto-review-loop-llm` against a different API-key backend, they can disable codex budget enforcement by setting `CODEX_LOOP_MAX_ITERATIONS=999999`.

## Edge cases (v1 punts)

| Case                                        | v1 behavior                                                                                       |
|---------------------------------------------|---------------------------------------------------------------------------------------------------|
| Claude used outside loop skills             | Not counted. User compensates by setting `CLAUDE_LOOP_MAX_ITERATIONS` below true subscription cap. |
| System clock skew or sleep                  | Rolling window uses local wall clock; ordering is preserved across sleep.                          |
| Concurrent loops on same machine            | Not supported in v1 (no file locking). Documented limitation.                                      |
| State file corruption                       | `check` treats unparseable lines as if they don't exist and logs a warning to stderr.              |
| State file missing                          | Treated as zero usage. First `record` creates it.                                                  |
| Skill instruction ignored by Claude         | Trust-the-skill model. Same risk as the rest of the repo. Not solved by this design.               |

## Testing

Required tests in `tests/test_loop_budget.py` (new file):

1. `record` creates state dir + file when neither exists.
2. `check` returns exit 0 on empty state.
3. `check` returns exit 2 when N records within window equals the cap, exit 0 at N-1.
4. `check` only counts records matching `--side`.
5. `check` ignores records older than `window_hours`.
6. `check` emits warning to stderr when utilization ≥ `CLAUDE_LOOP_WARN_AT` but stays under cap.
7. `check` next-window-reset time matches `oldest_in_window_ts + window_hours`.
8. `status` exits 0 and prints both sides.
9. Corrupted JSONL lines are skipped without crashing.
10. `ARIS_USAGE_DIR` override is honored.
11. Helper-resolution failure path: a smoke test in `tests/` (or extension of an existing integration test) verifies that when `LOOP_BUDGET_SCRIPT` is unset, the loop skill template's pre-iteration guard exits with the documented error rather than proceeding.

Skill-integration is otherwise verified manually (running one of the three loops) — no automated test.

## Open questions

None at design time. v2 directions noted below for context, not part of this spec:

- Token-count budget mode (read `~/.claude/projects/.../*.jsonl` and `~/.codex/sessions/...` for actual token totals).
- Auto-resume after window resets (sleep + retry).
- Hook-level enforcement via Claude Code `settings.json` hooks so non-loop usage is also counted.

## Acceptance criteria

- `tools/loop_budget.py check/record/status` work as specified above, exits documented codes, passes all tests in §Testing.
- Running any of the three loop skills consults the budget tool before each iteration and records after each call.
- With defaults, the loop stops cleanly at 15 Claude iterations / 30 Codex iterations per 5h window and prints a next-reset timestamp.
- No third-party Python dependencies introduced.
