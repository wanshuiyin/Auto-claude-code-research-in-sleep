# ARIS Toy Project

This is a minimal, runnable ARIS workspace inside the repo. It demonstrates the file layout from the project guides and uses a tiny synthetic research question:

> Can a structure-aware summary solve a binary sequence task that a bag-of-counts summary cannot?

The toy task labels a binary sequence as positive when the first and last bit match. A count-only baseline only sees how many ones appear in the sequence, so it loses the boundary structure. A structure-aware method that uses boundary information solves the task exactly.

## What Is Included

- `CLAUDE.md` with `## Pipeline Status` and state-persistence rules
- `RESEARCH_BRIEF.md` as workflow-1 input
- `docs/research_contract.md` as the active-idea context
- `refine-logs/EXPERIMENT_PLAN.md` and `refine-logs/EXPERIMENT_TRACKER.md`
- `findings.md` and `EXPERIMENT_LOG.md`
- `NARRATIVE_REPORT.md` as workflow-3 input
- `scripts/run_toy_experiment.py` as the actual zero-dependency experiment
- `tests/test_run_toy_experiment.py` as a small regression test

## Quick Start

From the repo root:

```bash
cd examples/toy-project
python3 scripts/run_toy_experiment.py
python3 -m unittest discover -s tests
```

## Suggested ARIS Flow

Inside this directory:

```text
/idea-discovery "RESEARCH_BRIEF.md"
/experiment-plan "docs/research_contract.md"
/paper-writing "NARRATIVE_REPORT.md"
```

You can also use the project as a reference for how to organize a real workspace around the conventions in [docs/PROJECT_FILES_GUIDE.md](../../docs/PROJECT_FILES_GUIDE.md) and [docs/SESSION_RECOVERY_GUIDE.md](../../docs/SESSION_RECOVERY_GUIDE.md).
