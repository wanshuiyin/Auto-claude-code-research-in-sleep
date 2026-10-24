# Reviewer Routing

## Default Reviewer Contract

Resolve invocation directives, `.aris/reviewer.json`, then the host default via
[reviewer-backends.md](reviewer-backends.md). That shared contract governs the
selectable routes and their session/completion rules. The default below applies
when no override is selected.

All reviewer-heavy Codex base skills use the same default contract:

- executor: current Codex main agent
- reviewer: second Codex reviewer, model `gpt-6-astra` (GPT-6-Astra)
- reasoning effort: **two tiers** (since 2026-07-10; `ultra`/`max` need codex-cli ≥ 0.144.1) —
  **deep-audit** skills use `ultra` (`proof-checker`, `kill-argument` core threads, `research-review`,
  `experiment-audit`, `paper-claim-audit`, `result-to-claim`, `meta-apply`); **every other**
  reviewer call uses `xhigh` (multi-round loops and per-item fan-outs stay `xhigh` — a
  follow-up `send_input` cannot change model/effort, and per-item `ultra` multiplies cost)
- round 1: `spawn_agent`
- follow-up rounds: `send_input`

This is the base default for `skills/skills-codex/`. No ARIS `— effort:` level or unrelated parameter changes the tier (ARIS `— effort: max` ≠ `reasoning_effort: max` — pipeline workload vs reviewer reasoning are different axes).

**Capability fallback (first spawn of each tier only):** if `spawn_agent` errors explicitly on the effort enum (older codex-cli — applies only to the deep tier's `ultra`; `xhigh` predates 0.144.1), retry `reasoning_effort: xhigh`; if it errors explicitly on the model being unknown/unavailable to this account, retry `model: gpt-6.1-sol` + `xhigh`, then `model: gpt-5.6-sol` + `xhigh`, then `model: gpt-5.5` + `xhigh`. When a complete host model list is available, skip every unlisted model in this fallback chain, including `gpt-6.1-sol`; without a complete host model list, use the same explicit capability-error test. Any GPT-to-GPT model change here remains same-family provisional, never accepted. NEVER downgrade on timeout / rate-limit / auth / transport / server / context-length errors (risk of double-running). Never run a verdict-bearing review below `xhigh`; if no allowed pair works, report `REVIEW_UNAVAILABLE` — never substitute the executor's own judgment.

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
> It must never be described as cross-model acceptance. To select another
> reviewer, use the complete pack's `antigravity`, `grok`, or `claude-code` route
> under [reviewer-backends.md](reviewer-backends.md); a partial overlay is not
> required. Acceptance still requires a completed, in-scope, positive review
> with known different actual model families. A deterministic verifier can
> accept only what it actually checks. `oracle-pro` is GPT family, so it remains
> provisional for a Codex executor.

## Selectable external reviewers

The complete Codex pack supports `— reviewer: antigravity` (alias `gemini`),
`grok`, and `claude-code` (aliases `claude` and `claude-review`), selected once
per review session by invocation → project configuration → host default.
[reviewer-backends.md](reviewer-backends.md) defines first-call/reply parameters,
actual model/effort evidence, success checks and the local resolver. Antigravity
and Grok use their own saved thread ids; local Claude Code replies repeat
cwd/tools and any explicit model override. They do not use native Codex ids.

These are formal reviewer routes at existing review steps. They preserve the
review task, primary evidence, fresh-context requirements and verdict schema.
Antigravity defaults to `gemini-4-argon-high` / `high`, Grok to `grok-4.7` /
`xhigh`, and Claude Code uses the CLI's configured provider without an effort
argument. Antigravity can return Claude; Claude Code can return DeepSeek.
Derive families from actual returned model identities, not route names.
Completed same-family positive review remains provisional; known cross-family
positive review can be accepted only after successful completion within the
required scope. Unknown identity, errors and incomplete scope remain
unavailable/provisional. A trace classification does not replace the skill's
substantive audit or submission gate.

The old partial overlays remain for existing installations and receive no new
workflow features. Their installation does not automatically confer acceptance.
The legacy `agy` route still means **gemini-review MCP**, not the separate
Antigravity MCP. Preserve the legacy Oracle and main-pack Copilot contracts below.

## Default Pattern

These examples apply when the resolved backend is `codex`. Other selections use
their transport parameters from [reviewer-backends.md](reviewer-backends.md).

Single-round review:

```text
spawn_agent:
  model: gpt-6-astra
  reasoning_effort: xhigh   # deep-audit skills: ultra (see tier table above)
  message: |
    [role + task]
    Read the listed files directly.
```

Multi-round review:

```text
spawn_agent:
  model: gpt-6-astra
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

When invocation or project selection resolves to `oracle-pro`, switch only the reviewer route:

- default reviewer remains Codex at the call's declared tier (deep-audit: ultra / regular: xhigh) if no invocation or project override is selected
- `oracle-pro` is optional, not the base default

Routing rule:

```text
If the resolved backend is codex:
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
- Reviewer selection changes only the review transport; executor semantics and
  the skill's evidence/verdict requirements stay in force. Legacy overlays are
  retained for existing installations, not required for new route selection.
- Every per-call trace and audit artifact records `review_independence` and
  `acceptance_status`; missing metadata is treated as provisional.
- When the selected route is `codex`, if `spawn_agent` is unavailable or fails, emit `BLOCKED` /
  `REVIEW_UNAVAILABLE`; never fabricate a provisional PASS.
- Do not wrap verdict-bearing skills in `/loop`, cron, or wall-clock retries.
  Schedule only external-world waits, then invoke the reviewer once after the
  artifact changes. See `external-cadence.md`.
- Browser-based Oracle review is acceptable for one-shot stress tests, not ideal for tight multi-round loops.

## Copilot CLI reviewer behavior in the main skill set

After invocation/project selection, the main
`skills/shared-references/reviewer-routing.md` defaults `/auto-review-loop` to Copilot CLI's native complementary `rubber-duck`
subagent when a host-session marker binds. Its stop gate requires revalidated
native lifecycle/model/response evidence and a known cross-family pair. The
older `--reviewer: copilot` custom-agent subprocess remains an explicit
compatibility drive mode and still needs a Codex/manual finalizer.

**This routing applies to the main skills at `skills/`, not this Codex-mirror
pack.** Here `spawn_agent` remains the native reviewer. See the main
[`reviewer-routing.md`](../../../skills/shared-references/reviewer-routing.md#copilot-cli-native-rubber-duck-default-for-auto-review-loop)
for the Copilot contract.

## Skills That Commonly Benefit From `oracle-pro`

- `research-review`
- `auto-review-loop`
- `experiment-audit`
- `proof-checker`
- `rebuttal`
- `idea-creator`
- `research-lit`
