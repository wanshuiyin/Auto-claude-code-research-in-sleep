---
name: "monitor-experiment"
description: "Monitor experiment execution status, progress, logs, and produced outputs. Use for questions like \"is it done\" or \"what has finished\". Do not use for training-quality diagnosis from metrics dashboards; use `training-check` then."
---

# Monitor Experiment Results

Monitor: $ARGUMENTS

## Routing Boundaries

- Use this skill for run status, progress, logs, completion state, and collecting outputs.
- Use `training-check` instead when the user wants to detect divergence, NaNs, unstable loss, or other quality issues during training.
- This skill is about process state; it is not the default metrics-analysis skill.

## Workflow

### Step 1: Check What's Running
```bash
ssh <server> "screen -ls"
```

### Step 2: Collect Output from Each Screen
For each screen session, capture the last N lines:
```bash
ssh <server> "screen -S <name> -X hardcopy /tmp/screen_<name>.txt && tail -50 /tmp/screen_<name>.txt"
```

If hardcopy fails, check for log files or tee output.

### Step 3: Check for JSON Result Files
```bash
ssh <server> "ls -lt <results_dir>/*.json 2>/dev/null | head -20"
```

If JSON results exist, fetch and parse them:
```bash
ssh <server> "cat <results_dir>/<latest>.json"
```

### Step 4: Summarize Results

Present results in a comparison table:
```
| Experiment | Metric | Delta vs Baseline | Status |
|-----------|--------|-------------------|--------|
| Baseline  | X.XX   | —                 | done   |
| Method A  | X.XX   | +Y.Y              | done   |
```

### Step 5: Interpret
- Compare against known baselines
- Flag unexpected results (negative delta, NaN, divergence)
- Suggest next steps based on findings

### Step 6: Feishu Notification (if configured)

After results are collected, check `~/.codex/feishu.json`:
- Send `experiment_done` notification: results summary table, delta vs baseline
- If config absent or mode `"off"`: skip entirely (no-op)

## Key Rules
- Always show raw numbers before interpretation
- Compare against the correct baseline (same config)
- Note if experiments are still running (check progress bars, iteration counts)
- If results look wrong, check training logs for errors before concluding
