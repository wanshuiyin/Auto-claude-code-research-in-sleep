# Reviewer Routing

## Default Reviewer Contract

All reviewer-heavy Codex base skills use the same default contract:

- executor: current Codex main agent
- reviewer: second Codex reviewer, model `gpt-5.6-sol` (GPT-5.6-Sol)
- reasoning effort: **two tiers** (since 2026-07-10; `ultra`/`max` need codex-cli ≥ 0.144.1) —
  **deep-audit** skills use `ultra` (`proof-checker`, `kill-argument` core threads, `research-review`,
  `experiment-audit`, `paper-claim-audit`, `result-to-claim`, `meta-apply`); **every other**
  reviewer call uses `xhigh` (multi-round loops and per-item fan-outs stay `xhigh` — a
  follow-up `send_input` cannot change model/effort, and per-item `ultra` multiplies cost)
- round 1: `spawn_agent`
- follow-up rounds: `send_input`

This is the base default for `skills/skills-codex/`. No ARIS `— effort:` level or unrelated parameter changes the tier (ARIS `— effort: max` ≠ `reasoning_effort: max` — pipeline workload vs reviewer reasoning are different axes).

**Capability fallback (first spawn of each tier only):** if `spawn_agent` errors explicitly on the effort enum (older codex-cli — applies only to the deep tier's `ultra`; `xhigh` predates 0.144.1), retry `reasoning_effort: xhigh`; if it errors explicitly on the model being unknown/unavailable to this account, retry `model: gpt-5.5` + `xhigh`. NEVER downgrade on timeout / rate-limit / auth / transport / server / context-length errors (risk of double-running). Never run a verdict-bearing review below `xhigh`; if no allowed pair works, report `REVIEW_UNAVAILABLE` — never substitute the executor's own judgment.

> ⚠️ **Same-family by default — provisional, never accepted.** The executor here
> is Codex (GPT family) and the reviewer is a fresh Codex agent from the same
> family. Its substantive PASS/WARN/FAIL may drive revisions, terminate a loop,
> and advance a resumable phase, but every positive result records:
>
> ```yaml
> review_independence: same-family
> acceptance_status: provisional
> ```
>
> It must never be described as cross-model acceptance. Install the
> **`skills-codex-claude-review`** or **`skills-codex-gemini-review`** overlay
> for `review_independence: cross-family` and `acceptance_status: accepted`.
> A deterministic verifier may also record accepted. `oracle-pro` is GPT family,
> so it remains provisional for a Codex executor.

## Default Pattern

Single-round review:

```text
spawn_agent:
  model: gpt-5.6-sol
  reasoning_effort: xhigh   # deep-audit skills: ultra (see tier table above)
  message: |
    [role + task]
    Read the listed files directly.
```

Multi-round review:

```text
spawn_agent:
  model: gpt-5.6-sol
  reasoning_effort: xhigh   # deep-audit skills: ultra (see tier table above)
  message: |
    [initial review prompt]
```

Save the returned reviewer id, then continue with:

```text
send_input:
  target: <saved reviewer id>
  message: |
    [follow-up materials only]
```

## Oracle Pro Override

When the user explicitly passes `--reviewer: oracle-pro`, switch only the reviewer route:

- default reviewer remains Codex at the call's declared tier (deep-audit: ultra / regular: xhigh) if no reviewer is specified
- `oracle-pro` is optional, not the base default

Routing rule:

```text
If reviewer is omitted or reviewer=codex:
  use spawn_agent / send_input with the Codex reviewer at the call's declared tier

If reviewer=oracle-pro:
  check Oracle MCP availability
  if available:
    call mcp__oracle__consult with model gpt-5.5-pro
  if unavailable:
    print a clear warning
    fall back to the default Codex reviewer at the call's declared tier
```

## Invariants

- Base skills do not use the legacy Codex MCP thread path as the default reviewer route.
- Reviewer independence still applies: pass file paths and task framing, not executor summaries.
- Overlay packages may replace only the reviewer route.
- Overlay packages do not change executor semantics.
- Every trace and audit artifact records `review_independence` and
  `acceptance_status`; missing metadata is treated as provisional.
- If `spawn_agent` is unavailable or fails, emit `BLOCKED` /
  `REVIEW_UNAVAILABLE`; never fabricate a provisional PASS.
- Do not wrap verdict-bearing skills in `/loop`, cron, or wall-clock retries.
  Schedule only external-world waits, then invoke the reviewer once after the
  artifact changes. See `external-cadence.md`.
- Browser-based Oracle review is acceptable for one-shot stress tests, not ideal for tight multi-round loops.

## Skills That Commonly Benefit From `oracle-pro`

- `research-review`
- `auto-review-loop`
- `experiment-audit`
- `proof-checker`
- `rebuttal`
- `idea-creator`
- `research-lit`
