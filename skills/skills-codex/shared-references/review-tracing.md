# Review Tracing Protocol

## Purpose

Save full prompt/response pairs for every reviewer call, enabling:

- reviewer-independence audit
- reproducibility across follow-up reviewer turns
- meta-optimization from real review traces

## When to Trace

Trace every Codex reviewer call that serves a critique, scoring, claim-verification, experiment-audit, or patch-gating function.

This includes:

- `spawn_agent` reviewer calls
- `send_input` reviewer continuations
- optional overlay reviewer routes
- adversarial reviewer calls used for stress tests

Do not trace purely informational agent calls that are not acting as reviewers.

## How to Trace

After each reviewer call, save the trace using `save_trace.sh`,
resolved through the canonical helper chain (see
`integration-contract.md` §2 — failure policy C, "forensic helper").
A Codex-side SKILL must NOT hard-code `tools/save_trace.sh`; instead
it resolves `$TRACE_HELPER` via the chain and either invokes the
helper or writes trace artifacts directly per the schemas below. If
the resolver returns the empty string, write the four files inline
— do not silently skip unless `--- trace: off` was requested.

## Trace Directory

```text
.aris/traces/<skill-name>/<YYYY-MM-DD>_run<NN>/
  run.meta.json
  001-<purpose>.request.json
  001-<purpose>.response.md
  001-<purpose>.meta.json
  002-<purpose>.request.json
  ...
```

## File Schemas

`run.meta.json`:

```json
{
  "skill": "auto-review-loop",
  "run_id": "2026-04-15_run01",
  "started_at": "2026-04-15T14:30:00+08:00",
  "executor": "codex",
  "executor_model": "gpt-5.6-sol",
  "executor_family": "openai",
  "review_independence": "same-family",
  "acceptance_status": "provisional",
  "project_dir": "/path/to/project"
}
```

`NNN-<purpose>.request.json`:

```json
{
  "call_number": 1,
  "purpose": "round-1-review",
  "timestamp": "2026-04-15T14:31:00+08:00",
  "tool": "spawn_agent",
  "model": "gpt-5.6-sol",
  "reasoning_effort": "xhigh",
  "files_referenced": ["paper/sections/3_method.tex", "results/table1.csv"],
  "prompt": "<full prompt text>"
}
```

`NNN-<purpose>.response.md` stores the full reviewer response verbatim.

`NNN-<purpose>.meta.json`:

```json
{
  "call_number": 1,
  "purpose": "round-1-review",
  "timestamp": "2026-04-15T14:33:00+08:00",
  "agent_id": "019d8fe0-b25d-...",
  "model": "gpt-5.6-sol",
  "reviewer_family": "openai",
  "review_independence": "same-family",
  "acceptance_status": "provisional",
  "duration_ms": 142000,
  "status": "ok"
}
```

For a Claude/Gemini overlay write `review_independence: cross-family` and
`acceptance_status: accepted`. For a deterministic verifier write
`review_independence: deterministic` and `acceptance_status: accepted`. These
fields describe the reviewer route; they do not rewrite the substantive verdict.

## Configuration

Respect inline parameter `--- trace: off | meta | full`:

- `full` default: save full prompt and full response
- `meta`: save metadata only
- `off`: disable tracing

## Events

After writing a trace, append a compact event to `.aris/meta/events.jsonl`:

```json
{"event":"review_trace","skill":"auto-review-loop","purpose":"round-1-review","agent_id":"...","trace_path":".aris/traces/auto-review-loop/2026-04-15_run01/","status":"ok"}
```

## Debugging With Traces

Traces are not only audit evidence — they are the **first place to look when a
verdict is surprising**: a score regresses round-to-round, two reviewer agents
disagree, or a claim check contradicts an earlier round. Before re-invoking the
reviewer for "a better answer", read the raw transcript and find the moment its
judgment actually changed:

```bash
skill=auto-review-loop run=2026-04-15_run01
diff ".aris/traces/$skill/$run/002-round-2.response.md" \
     ".aris/traces/$skill/$run/003-round-3.response.md"
grep -En 'however|but|concern|missing|cannot' \
     ".aris/traces/$skill/$run/003-round-3.response.md"
```

The paragraph where the assessment changed **is** the causal explanation for the
divergence — cite it, don't guess. Re-running the reviewer without reading the
trace is tuning by vibe: you get a new opinion, not an explanation. Same muscle
as reading a stack trace before retrying a failed run — the trace is just
written in English, and most of it is the reviewer talking to itself.

## Privacy

`.aris/traces/` is project-local and should not be committed. Use `--- trace: off` for strict confidentiality projects.
