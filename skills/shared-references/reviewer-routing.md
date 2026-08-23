# Reviewer Routing (ARIS-Cursor Edition)

> **This file replaces the upstream `reviewer-routing.md`.** Upstream routed all
> reviews through external LLM APIs (legacy Codex MCP / Oracle / Gemini /
> manual-review). This edition routes reviews through **Cursor Task subagents running Cursor's
> built-in models** — zero API keys, zero CLI, works on a Cursor subscription alone.
> Everything else in the ARIS review contract (independence, tracing, verdict
> schema, stop conditions) is unchanged.

## Default backend: Cursor Task subagent (NEVER changes without explicit user request)

Every reviewer call launches a **Cursor Task subagent** with a model from a
**different model family than the executor** (the model driving the main chat).

### Call convention

**Fresh review thread** (replaces `mcp__codex__codex` / `mcp__llm-chat__chat` / `codex exec`):

```
Task(
  subagent_type: "generalPurpose",
  description: "ARIS reviewer — <skill> R<round>",
  model: "<REVIEWER_MODEL — see model table>",
  prompt: "<the EXACT review prompt text the SKILL.md specifies — unmodified>"
)
```

**Follow-up in the same review thread** (replaces `mcp__codex__codex-reply(threadId)`):

```
Task(
  resume: "<REVIEWER_AGENT_ID saved from the previous call>",
  prompt: "<follow-up prompt — e.g. round-2 re-review, debate ruling>"
)
```

- The subagent id returned by the first Task call **is the threadId**. Persist it
  as `reviewer_agent_id` wherever the skill says to save `threadId`
  (e.g. `review-stage/REVIEW_STATE.json`).
- Do **not** pass `model` when resuming — the thread keeps its original model.
- If a resume fails (expired/unavailable), fall back to a **fresh** reviewer call and
  prepend the skill's reviewer-memory file (`REVIEWER_MEMORY.md`) if one exists.
  Record `fallback_reason: "resume_unavailable"` in the trace.

### Thread freshness vs continuity

Preserve each SKILL.md's own choice:

| Pattern | When the SKILL.md says | Cursor primitive |
|---|---|---|
| Fresh thread | `mcp__codex__codex` (audit-chain skills: experiment-audit, paper-claim-audit, citation-audit, kill-argument, result-to-claim, render-html gate...) | new `Task(...)` — never resume |
| Continuity | `codex-reply` with saved threadId (auto-review-loop rounds, proof-checker Phase 3, debate rulings) | `Task(resume: ...)` |

### Repo access (a free upgrade)

The reviewer subagent has its own Read/Grep/Glob/Shell tools and **reads the
repository directly** — the executor cannot filter what it sees. This is the
upstream "nightmare mode" (`codex exec` repo-direct review) as the **default**.
Consequently:

- Pass **file paths only**, never summaries (unchanged — see `reviewer-independence.md`).
- `difficulty: medium | hard | nightmare` now differ only in **reviewer memory +
  debate protocol** (hard/nightmare add them), not in repo access.
- Where a skill says "nightmare requires codex exec / is Codex-only", read it as:
  nightmare is **natively supported** by the subagent backend.

## Model table

**Cross-family rule (mandatory, unchanged):** executor and reviewer must be
different model families. Same-family review is a non-feature; never pass
`model: "inherit"` for a reviewer.

| Executor family (main chat) | Default reviewer slug | Alternates (in preference order) |
|---|---|---|
| Claude (fable/opus/sonnet) | `gpt-5.6-sol-max-fast` | `kimi-k3-max`, `glm-5.2-max`, `cursor-grok-4.5-high-fast` |
| GPT / composer | `claude-opus-5-thinking-max` | `kimi-k3-max`, `glm-5.2-max` |
| Other (grok/glm/kimi executor) | `gpt-5.6-sol-max-fast` | `claude-opus-5-thinking-max` |

- The upstream default reviewer was `gpt-5.6-sol` via Codex — `gpt-5.6-sol-max-fast`
  is the same model family at max reasoning, so verdict calibration carries over.
- **Check the live list**: the set of available subagent model slugs is provided in
  the session (`<available_subagent_models>`). If a slug above is missing, pick the
  nearest same-family `-max`/`thinking` slug from the live list, and record the
  substitution in the trace (`fallback_reason: "slug_unavailable"`).
- User override: `— reviewer-model: <slug>` on any skill invocation pins the
  reviewer model explicitly (must still be cross-family, unless the user also
  passes `— allow-same-family: true`, which downgrades the run's
  `review_independence` to `same-family` and `acceptance_status` to `provisional`).

### Effort tiers (maps upstream `model_reasoning_effort`)

Upstream ran regular reviews at `xhigh` and deep-audits at `ultra`. Cursor's
`-max` / `thinking-max` slugs already run at maximum reasoning, so **both tiers
use the max slugs above** — the tier difference survives as prompt-level depth:

| Tier | Upstream | Cursor edition |
|---|---|---|
| Deep-audit (`/proof-checker`, `/kill-argument` attack·defense·adjudication, `/research-review`, `/experiment-audit`, `/paper-claim-audit`, `/result-to-claim`, `/meta-apply`) | `ultra` | max slug + instruct the reviewer: "verify every claim against the artifacts yourself; do not sample — be exhaustive" |
| Regular (everything else, incl. ALL rounds of `/auto-review-loop`) | `xhigh` | max slug, standard skill prompt |

**Never run a verdict-bearing review on a non-max slug.** If only non-max slugs
are available, emit `REVIEW_UNAVAILABLE` rather than a substantive verdict.

## Failure semantics (unchanged from upstream)

- Retry transport-level failures (Task tool errors) once; on repeated failure emit
  **`REVIEW_UNAVAILABLE`** (or `ERROR` for a mandatory audit gate) — **never** a
  substantive verdict, never a silent skip.
- **NEVER downgrade the reviewer model on timeout/capacity errors** — a blind
  downgrade risks double-running a review that may have gone through.
- Trace every attempt including failures (see `review-tracing.md`); the trace
  records the model that actually ran, not the target.

## Tracing

`review-tracing.md` applies to every reviewer subagent call. In trace files use:

- `"tool": "cursor-task-subagent"`
- `"model": "<the slug that actually ran>"`
- `"thread_id": "<REVIEWER_AGENT_ID>"`

## Optional legacy backends

If the user has these installed and **explicitly** passes the flag, the original
upstream routes remain valid: `— reviewer: codex` (legacy Codex MCP), `— reviewer:
oracle-pro` (Oracle MCP), `— reviewer: agy` (gemini-review MCP), `— reviewer:
manual` (manual-review MCP). Their contracts are documented in the
[upstream reviewer-routing contract](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/reviewer-routing.md).
Without an explicit flag, the **Cursor Task subagent is the only backend** —
do not probe for MCP servers.

## Skill-side rewrite cheatsheet

When a SKILL.md in this pack still shows upstream call blocks, translate on the fly:

| Upstream text | Execute as |
|---|---|
| `mcp__codex__codex: model: gpt-5.6-sol, config: {...}, prompt: P` | `Task(subagent_type:"generalPurpose", model:<reviewer slug>, prompt:P)` |
| `mcp__codex__codex-reply: threadId: T, prompt: P` | `Task(resume:T, prompt:P)` |
| `mcp__llm-chat__chat` / `mcp__manual_review__review(_reply)` / `mcp__oracle__consult` / `mcp__gemini_review__review` | same mapping as above (fresh vs resume) |
| `codex exec "<PROMPT>"` (nightmare) | `Task(subagent_type:"generalPurpose", model:<reviewer slug>, prompt:PROMPT + "You have full read access to this repository — explore freely.")` |
| `config: {"model_reasoning_effort": "xhigh"/"ultra"}` | drop — the max slug covers it (deep-audit adds the exhaustiveness instruction) |
| "save threadId" | save the subagent agent id as `reviewer_agent_id` |
