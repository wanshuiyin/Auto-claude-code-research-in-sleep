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
  "model": "gpt-5.4",
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
  "model": "gpt-5.4",
  "duration_ms": 142000,
  "status": "ok"
}
```

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

## Privacy

`.aris/traces/` is project-local and should not be committed. Use `--- trace: off` for strict confidentiality projects.
