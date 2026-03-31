# Toy Project Instructions

This directory is a tiny, local-first ARIS workspace used to demonstrate the repo's workflow conventions on a synthetic experiment.

## Project Constraints

- Keep the experiment zero-dependency unless there is a clear reason not to.
- Prefer exact enumeration over stochastic training when the task is small enough.
- Preserve the file layout so new sessions can recover state from disk.

## Pipeline Status

stage: implementation
idea: "boundary-aware summaries solve a binary sequence task that count-only summaries cannot"
contract: docs/research_contract.md
current_branch: main
baseline: "count-only optimum reaches 57.03% at length 8 and trends toward chance as length grows"
training_status: not running; use exhaustive enumeration via python3 scripts/run_toy_experiment.py
active_tasks:
  - "none"
next: "run the toy experiment, inspect EXPERIMENT_LOG.md, then use NARRATIVE_REPORT.md as input to /paper-writing"

## State Persistence Rules

Pipeline Status update triggers:
- Stage transitions, idea selection, baseline confirmed, implementation changes, experiment completion
- User says "save", "record", "new session", or "wrap up"
- Before any long pause or handoff

On new session or post-compaction recovery:
1. Read `## Pipeline Status`
2. Read `docs/research_contract.md`
3. Read recent entries in `findings.md`
4. Read `EXPERIMENT_LOG.md` if experiment context is needed
5. Resume work without asking for unnecessary confirmation
