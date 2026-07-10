# Reviewer Routing

## Default Reviewer Contract

All reviewer-heavy Codex base skills use the same default contract:

- executor: current Codex main agent
- reviewer: second Codex reviewer
- reasoning effort: `xhigh`
- round 1: `spawn_agent`
- follow-up rounds: `send_input`

This is the base default for `skills/skills-codex/`. No effort level or unrelated parameter changes it.

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
  model: gpt-5.5
  reasoning_effort: xhigh
  message: |
    [role + task]
    Read the listed files directly.
```

Multi-round review:

```text
spawn_agent:
  model: gpt-5.5
  reasoning_effort: xhigh
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

- default reviewer remains Codex xhigh if no reviewer is specified
- `oracle-pro` is optional, not the base default

Routing rule:

```text
If reviewer is omitted or reviewer=codex:
  use spawn_agent / send_input with Codex reviewer at xhigh

If reviewer=oracle-pro:
  check Oracle MCP availability
  if available:
    call mcp__oracle__consult with model gpt-5.5-pro
  if unavailable:
    print a clear warning
    fall back to the default Codex xhigh reviewer
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
