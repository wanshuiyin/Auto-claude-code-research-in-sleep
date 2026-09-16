# Experiment Log

> **Complete record of all experiments run in this project.** Every experiment gets an entry — successful or not. This is the authoritative source for "what did we actually run and what happened?"
>
> **How it differs from EXPERIMENT_TRACKER.md:** The tracker (in `refine-logs/`) is an execution checklist (TODO → RUNNING → DONE). This log is a permanent record with full results, configs, and reproduction commands. The tracker tells you what's left to do; the log tells you what was done and what it showed.
>
> **Update rule:** Write an entry immediately after each experiment completes. Do not batch entries or wait until "later."

## Experiment: [Descriptive Name]

**Date**: YYYY-MM-DD
**Idea**: [Which idea from IDEA_CANDIDATES.md]
**Goal**: [What this experiment tests — link to claim if applicable]

### Setup
- **Method**: [Brief description of the approach]
- **Dataset**: [Name, split, size]
- **Baseline**: [What you compare against]
- **Hardware**: [Server, GPUs, time taken]
- **Config**: [Path to config file or key hyperparameters]

### Results

| Method | Dataset | Metric-1 | Metric-2 | Notes |
|--------|---------|----------|----------|-------|
| Baseline | [dataset] | [number] | [number] | [reproduced / from paper] |
| Ours | [dataset] | [number] | [number] | [seeds, std if applicable] |

### Verdict
- **Supports claim?** [Yes / Partially / No]
- **Key takeaway**: [One sentence — what did we learn?]

### Reproduction
```bash
# Command to reproduce this experiment
python train.py --config configs/exp01.yaml --seed 42
```

### WandB
- Run URL: [link]
- Run ID: [id]

---

## Experiment: [Next Experiment Name]

...
