# Generalizable Machine Unlearning Workspace

This workspace now covers two stages:

1. idea discovery on generalizable machine unlearning
2. a lightweight implementation scaffold for the selected proposal:
   "When Does Unlearning Survive Distribution Shift?"

## Main Files

- `RESEARCH_BRIEF.md`: original idea-discovery input
- `CLAUDE.md`: project context and pipeline status for session recovery
- `docs/research_contract.md`: active idea contract for implementation
- `refine-logs/FINAL_PROPOSAL.md`: selected proposal
- `refine-logs/EXPERIMENT_PLAN.md`: claim-driven experiment plan
- `configs/`: canonical model, shift, forget-set, and run definitions
- `scripts/`: starter CLIs for `R001-R009`
- `tests/`: config validation tests

## Recommended Next Step

The project is past Workflow 1. The next practical step is to start implementation against the committed run matrix.

Useful local commands:

```bash
cd /Users/yuenc2/Desktop/Auto-claude-code-research-in-sleep/examples/generalizable-machine-unlearning
python3 scripts/validate_run_configs.py
python3 scripts/render_run_summary.py
python3 scripts/run_vision_experiment.py --run-id R001 --write-stub
python3 scripts/run_vision_experiment.py --run-id R004 --write-stub
python3 scripts/run_diagnostics.py --run-id R008 --write-stub
python3 scripts/run_synthetic_sweep.py --run-id R009 --write-stub
python3 -m unittest discover -s tests
```

## Why This Scope

The brief and proposal are tuned to avoid weak "yet another unlearning loss" ideas. They push the project toward:

- domain-shift robustness rather than only in-distribution forgetting
- mechanistic predictors such as FSS, RFE, and LR
- tracker-friendly runs with named shift families and forget-set constructions
- a paper that explains when local unlearning should be trusted out of distribution
