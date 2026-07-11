# Resumable Runs

A long ARIS workflow (`/research-pipeline`, `/paper-writing`, `/idea-discovery`)
can fail mid-run — a rate limit, a crash, an overnight timeout. Today there is no
record of *which phase finished*, so a resume restarts from scratch (this is the
live complaint in issue #272: "the survey run failed — can it continue from the
last task?"). `tools/run_state.py` fixes that: a run is an **ordered list of
phases with status**, persisted at `<root>/.aris/runs/<run_id>.json`.

## The one idea that makes this ARIS, not just "reopen the session"

Resumption is not "reopen the id" — it is **resolve FORWARD to where progress
that can be TRUSTED actually landed.** And "trusted" is where ARIS's invariant
lives. The phase-status enum splits execution from acceptance:

| status | meaning | who sets it | gate class |
|--------|---------|-------------|-----------|
| `pending` | not started | `start` | — |
| `running` | in progress | executor (`set`) | — |
| `failed` | executor errored | executor (`set`) | — |
| **`done`** | executor finished writing the artifact | executor (`set`) | **EXECUTION-completeness — safe same-model self-report** |
| **`accepted`** | a cross-model reviewer **or** a deterministic verifier returned a positive verdict | **`accept` only** — requires a recorded verdict id + reviewer, AND the phase already `done` (use `--force` for a purely-deterministic phase with no executor step) | **QUALITY/correctness — cross-model (or a deterministic check)** |
| `skipped` | the phase does not apply to this run (e.g. `paper-writing` when `AUTO_WRITE=false`) | executor (`set`) | terminal — a deterministic config decision, not a quality verdict |

**Resume walks forward to the first phase that is NOT terminal ({`accepted`, `skipped`})** — never
the first non-`done`. So a phase the executor self-considered "done" but that
crashed *before its cross-model audit* is **re-validated** on resume, never
silently skipped. This is `acceptance-gate.md` made operational: **a loop can
DRIVE resume, it cannot ACQUIT a phase past itself.**

The split is enforced in code, not just docs: `set_status()` may only write
`running/done/failed`; only `accept()` writes `accepted`, and it **requires** a
non-empty `verdict_id` + `reviewer` — you cannot mark a phase accepted without
recording who acquitted it. (A `done`-but-never-`accepted` phase is therefore
*structurally* visible as an unmet acceptance obligation.)

## Who may call `accept`

Only:
- a **cross-model reviewer** verdict (codex/gemini, per `reviewer-independence.md`)
  — `reviewer="codex-gpt-5.6-sol"`, `verdict_id=<thread/trace id>`; or
- a **deterministic verifier** — `verify_papers.py`, a passing test suite, a
  compile that exits 0, a file-exists check for a purely mechanical phase.
  Record it as `reviewer="deterministic:verify_papers.py"` so the audit trail
  shows acceptance was not a model self-report (per `fan-out-pattern.md`: a
  deterministic verifier is a valid jury; a process is not a model family).

The **executor (Claude) must never call `accept` on its own self-report.** Marking
your own phase done is fine (`set done`); acquitting it is not. `accept` records
the `reviewer` and warns loudly if it looks like the executor's own family
(a `claude*` reviewer ≈ self-acquittal). Record `verdict_id` as a **durable
handle** — the reviewer thread/trace id, or the path/sha of the verifier's report
(e.g. `.aris/audit-verifier-report.json`) — not just a label, so the acceptance
is auditable later.

**Concurrency:** one orchestrator per run (single-writer contract). Mutations are
load-modify-save under a best-effort `flock` with atomic temp-file replace, so a
stray concurrent resumer can't corrupt the JSON — but a `/loop`/cron resumer must
not deliberately double-run a run (per `external-cadence.md`, the scheduler
triggers resume, it does not own the verdict).

## Helper API / CLI

```
from run_state import start_run, set_status, accept, resume_point
start_run(root, run_id, phases)                 # phases: ["W1","W1.5","W2","W3"]
set_status(root, run_id, phase, "running"|"done"|"failed", artifact=path)
accept(root, run_id, phase, verdict_id, reviewer)   # the ONLY path to `accepted`
resume_point(root, run_id)  # -> first NON-TERMINAL phase ({accepted,skipped} skipped), or None
```

```
python3 tools/run_state.py start  <root> <run_id> --phases "W1,W1.5,W2,W3"
python3 tools/run_state.py set    <root> <run_id> W1 done --artifact idea-stage/IDEA_REPORT.md
python3 tools/run_state.py accept <root> <run_id> W1 --verdict-id codex:019e... --reviewer codex-gpt-5.6-sol
python3 tools/run_state.py resume <root> <run_id>   # prints the resume-target phase name on stdout
python3 tools/run_state.py status <root> <run_id>
```

## Integration pattern for a workflow skill

1. **At run start** (or `— resume <run_id>`): if resuming, `resume_point` gives
   the phase to start at; else `start_run` with the phase list.
2. **Per phase:** `set running` → do the work → `set done --artifact <path>`.
3. **At the phase's gate:** run the phase's existing cross-model audit / jury (or
   deterministic verifier). **Only on a positive verdict** call
   `accept --verdict-id <id> --reviewer <name>`. A failed/ambiguous verdict leaves
   the phase `done` (unaccepted) → it will be re-validated on the next resume.
4. **Resume** therefore re-runs `running`/`failed` phases and **re-audits**
   `done`-but-unaccepted phases, and skips only terminal (`accepted`/`skipped`) ones.

## Cross-references
- `acceptance-gate.md` — the source rule (`done` = execution-completeness, safe
  same-model; `accepted` = quality/correctness, must be cross-model or
  deterministic). This file is that rule applied to multi-phase resume.
- `external-cadence.md` — `/loop` / `/schedule` may *trigger* a resume (fire-control)
  but the acceptance status is owned by the gate, not the scheduler.
- `reviewer-independence.md` — the `accept` verdict comes from a fresh cross-model
  thread (paths only), and its id is recorded for audit.

> Shape inspired by NousResearch/hermes-agent's resume-resolves-forward insight
> (`hermes_state.py` resolve_resume_session_id). ARIS's increment: Hermes's phase
> is execution-driven only ("the agent finished → resumable"); ARIS adds the
> `accepted` gate so resume cannot carry a self-judged-but-unverified phase forward.
