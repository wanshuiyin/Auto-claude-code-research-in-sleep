---
name: training-check
description: "Check live training quality using WandB or similar metrics to catch NaNs, divergence, stalled learning, or idle GPUs. Use only when training is already running and quality monitoring is needed. Do not use for generic run-status checks or log collection; use `monitor-experiment` then."
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Training Check

Periodically read WandB metrics during training to catch problems early. Do not wait until training finishes to discover it was a waste of GPU time.

## Routing Boundaries

- Use this skill only after a training job is already running and metric-based health checks are needed.
- Use `monitor-experiment` for process health, session status, output collection, or \"is it done\" questions.
- This skill checks training quality, not paper-level result interpretation.

## Context: $ARGUMENTS

## Constants

- **WANDB_RUN** - Read from project notes or pass as `entity/project/run_id`.
- **CHECK_INTERVAL** - Starts at 10 minutes, then gradually increases if consistently healthy: 10 min -> 20 min -> 30 min -> 60 min (cap).
- **REVIEWER_MODEL = `gpt-5.4`** - Used via a secondary Codex agent for ambiguous cases only.

## When to Use

- After training is confirmed running (session alive, loss decreasing for the first few steps)
- When the user wants recurring health checks during training
- **This skill checks training QUALITY, not process HEALTH.** Process health (session alive, GPU utilization) belongs to watchdog-style monitoring.

## Workflow

### Step 1: Read WandB Metrics

```python
import wandb
api = wandb.Api()
run = api.run("<entity>/<project>/<run_id>")
history = run.history()
```

If WandB is unreachable (API error, network issue), fall back to reading the log file directly via SSH:

```bash
ssh server "tail -100 /path/to/training.log"
```

Check these signals:

- **Loss trend** - Is training loss decreasing over the last N steps?
- **Eval metrics** - Are evaluation metrics improving (or at least not degrading)?
- **NaN / Inf** - Any NaN or Inf values in loss or gradients?
- **Spikes** - Sudden large jumps in loss (>10x normal variance)?
- **Learning rate** - Is the schedule behaving as expected?
- **Gradient norm** - Exploding or vanishing?

### Step 2: Judgment

| Signal | Judgment | Action |
|--------|----------|--------|
| NaN/Inf in loss | **Clearly bad** | Stop training, investigate |
| Loss diverging (increasing for >N steps) | **Clearly bad** | Stop training, investigate |
| Eval metrics significantly worse than baseline | **Clearly bad** | Stop training, investigate |
| Loss decreasing, metrics improving | **Clearly fine** | Continue, increase check interval |
| Loss flat but not diverging | **Unsure** | -> Step 3 (secondary review) |
| Metrics noisy, can't tell trend | **Unsure** | -> Step 3 (secondary review) |
| Slightly worse than baseline but still early | **Unsure** | -> Step 3 (secondary review) |

### Step 3: Secondary Codex Judgment (only when unsure)

Only escalate when the signal is ambiguous. For clearly good or clearly bad signals, act directly.

```text
spawn_agent:
  model: REVIEWER_MODEL
  reasoning_effort: high
  message: |
    TRAINING HEALTH CHECK - need your judgment on ambiguous metrics.

    Run: <entity>/<project>/<run_id>
    Current epoch/step: X / Y total
    Training loss (last 10 checkpoints): [values]
    Eval metrics (last 3 evals): [values]
    Baseline reference: [numbers from paper/reproduction]

    What I'm unsure about: [specific concern]

    Please respond with exactly one of:
    - STOP: clearly problematic, should kill training
    - CONTINUE: looks fine, check again next interval
    - WAIT: not enough data to judge, check again sooner
```

If delegation is unavailable, make a local judgment using the same rubric and mark the decision `[pending external review]`. In ambiguous cases with no hard failure, prefer `WAIT` over `STOP`.

### Step 4: Act

| Decision | Action |
|----------|--------|
| **Stop** | Kill the training session. Save the WandB run URL, key metrics, and reason for stopping. Log to project notes for debugging. |
| **Continue** | Do nothing. Re-run at the next interval (increase interval if consistently healthy). |
| **Wait** | Do nothing but keep the current short interval (do not increase). |

## Integration with Watchdog

`training-check` and watchdog-style monitoring operate at different levels:

| Layer | Tool | What it checks | Frequency |
|-------|------|----------------|-----------|
| Process health | watchdog | Session alive? GPU active? | Every 60s (continuous) |
| Training quality | training-check | Loss trend? Metrics improving? | Every 10-60 min (periodic) |

Use both together:

- Watchdog catches crashes and idle GPUs immediately
- `training-check` catches subtle quality issues (loss plateau, metric degradation)

## Rules

- Do not stop training on the first sign of noise - some loss spikes are normal. Look at **trends over multiple checkpoints**.
- When stopping training, always save the WandB run URL and key metrics as evidence.
- If both WandB and log files are unreachable, report the connectivity issue and try again next interval. Do not assume training is broken.
- Gradually increase check interval when healthy (10 -> 20 -> 30 -> 60 min). Reset to 10 min after any anomaly.
- This skill is meant to be automated via a recurring scheduler. If the user wants ongoing monitoring, set up the best local mechanism available instead of waiting for manual reruns.

## Recurring Setup Example

```text
After training is confirmed stable:
  Create a recurring job (cron, task scheduler, tmux loop, etc.)
  that runs `/training-check <entity>/<project>/<run_id>` every 10 minutes.
```

As the check interval increases, update the old recurring job to match the new interval.
