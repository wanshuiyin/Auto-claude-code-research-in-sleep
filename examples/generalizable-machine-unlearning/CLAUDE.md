# Project Instructions

This workspace is for discovering research ideas on generalizable machine unlearning.

## Research Priorities

- Prefer ideas with a clear evaluation story, not only a training trick.
- Penalize methods that require full retraining for each deletion request.
- Favor problem formulations that can transfer across architectures, datasets, or deletion distributions.
- Treat "generalizable" as a concrete claim that must be operationalized and stress-tested.

## Pipeline Status

stage: implementation
idea: "unlearning under distribution shift"
contract: docs/research_contract.md
current_branch: main
baseline: "not started"
training_status: not running
active_tasks:
  - "selected proposal frozen in FINAL_PROPOSAL.md and docs/research_contract.md"
  - "implementation scaffold added for R001-R009 with config-driven run specs"
next: "wire actual training and evaluation code into scripts/run_vision_experiment.py, then launch R001-R003"

## State Persistence Rules

Pipeline Status update triggers:
- Stage transitions, idea selection, baseline confirmed, experiment completion
- User says "save", "record", "new session", or "wrap up"
- Before any long pause or handoff

On new session or post-compaction recovery:
1. Read `## Pipeline Status`
2. Read `docs/research_contract.md`
3. Read `refine-logs/EXPERIMENT_PLAN.md`
4. Read `refine-logs/EXPERIMENT_TRACKER.md`
5. Resume work without unnecessary confirmation
