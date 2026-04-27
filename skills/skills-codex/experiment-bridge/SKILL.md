---
name: experiment-bridge
description: "Workflow 1.5: Bridge between idea discovery and auto review. Reads EXPERIMENT_PLAN.md, implements experiment code, deploys to GPU, collects initial results. Use when user says \"实现实验\", \"implement experiments\", \"bridge\", \"从计划到跑实验\", \"deploy the plan\", or has an experiment plan ready to execute."
---

# Workflow 1.5: Experiment Bridge

Implement and deploy experiments from plan: **$ARGUMENTS**

## Overview

This skill bridges Workflow 1 (idea discovery + method refinement) and Workflow 2 (auto review loop). It takes the experiment plan and turns it into running experiments with initial results.

```
Workflow 1 output:                    This skill:                        Workflow 2 input:
refine-logs/EXPERIMENT_PLAN.md   →   implement → deploy → collect   →   initial results ready
refine-logs/EXPERIMENT_TRACKER.md     code        /run-experiment        for /auto-review-loop
refine-logs/FINAL_PROPOSAL.md
```

## Constants

- **AUTO_DEPLOY = true** — Automatically deploy experiments after implementation. Set `false` to review code before deploying.
- **CODE_REVIEW = true** — Secondary Codex reviewer with xhigh reasoning reviews experiment code before deployment. Catches logic bugs before wasting GPU hours. Set `false` to skip.
- **SANITY_FIRST = true** — Run the sanity-stage experiment first (smallest, fastest) before launching the rest. Catches setup bugs early.
- **MAX_PARALLEL_RUNS = 4** — Maximum number of experiments to deploy in parallel (limited by available GPUs).
- **BASE_REPO = false** — GitHub repo URL to use as a base codebase. When set, clone it first and implement experiments on top of it.
- **COMPACT = false** — When `true`, prefer `idea-stage/IDEA_CANDIDATES.md` over the full `idea-stage/IDEA_REPORT.md`, and append completed runs to `EXPERIMENT_LOG.md`.
- **BACKENDS = local | ssh | vast | modal** — Preserve the Claude mainline backend lifecycle. Vast.ai and Modal routes are first-class when configured; do not silently fall back to local execution if the user requested either backend.
- **RESCUE_ON_FAILURE = true** — If sanity or deployment fails, run a Codex-native rescue / second opinion review before abandoning the experiment plan.

> Override: `/experiment-bridge "EXPERIMENT_PLAN.md" — compact: true, base repo: https://github.com/org/project`

## Inputs

This skill expects one or more of:

1. **`refine-logs/EXPERIMENT_PLAN.md`** (best) — claim-driven experiment roadmap from `/experiment-plan`
2. **`refine-logs/EXPERIMENT_TRACKER.md`** — run-by-run execution table
3. **`refine-logs/FINAL_PROPOSAL.md`** — method description for implementation context
4. **`idea-stage/IDEA_CANDIDATES.md`** — compact idea summary (preferred when `COMPACT = true`) *(fall back to `./IDEA_CANDIDATES.md` if not found)*
5. **`idea-stage/IDEA_REPORT.md`** — fallback if refine-logs don't exist *(fall back to `./IDEA_REPORT.md` if not found)*

If none exist, ask the user what experiments to implement.

## Workflow

### Phase 1: Parse the Experiment Plan

Read `EXPERIMENT_PLAN.md` and extract:

1. **Run order and milestones** — which experiments run first (sanity → baseline → main → ablation → polish)
2. **For each experiment block:**
   - Dataset / split / task
   - Compared systems and variants
   - Metrics to compute
   - Setup details (backbone, hyperparameters, seeds)
   - Success criterion
   - Priority (MUST-RUN vs NICE-TO-HAVE)
3. **Compute budget** — total estimated GPU-hours
4. **Method details** from `FINAL_PROPOSAL.md` — what exactly to implement

Present a brief summary:

```
📋 Experiment plan loaded:
- Milestones: [N] (sanity → baseline → main → ablation)
- Must-run experiments: [N]
- Nice-to-have: [N]
- Estimated GPU-hours: [X]

Proceeding to implementation.
```

### Phase 2: Implement Experiment Code

**If `BASE_REPO` is set** — clone the repo first:

```bash
git clone <BASE_REPO> base_repo/
```

For each milestone (in order), write the experiment scripts:

1. **Check existing code** — scan the project (or cloned `base_repo/`) for existing experiment scripts, model code, and data loaders. Reuse as much as possible.

2. **Implement missing pieces:**
   - Training scripts with proper argparse (all hyperparameters configurable)
   - Evaluation scripts computing the specified metrics
   - Data loading / preprocessing if needed
   - Baseline implementations if not already present
   - Fixed random seeds for reproducibility
   - Results saved to JSON/CSV for later analysis
   - Proper logging (wandb if configured in AGENTS.md)

3. **Follow the plan's run order** — implement sanity-stage experiments first, then baselines, then main method, then ablations.

4. **Self-review before deploying:**
   - Are all hyperparameters from EXPERIMENT_PLAN.md reflected in argparse?
   - Is the random seed fixed and controllable?
   - Are results saved in a parseable format (JSON/CSV)?
   - Does the code match FINAL_PROPOSAL.md's method description?
   - **CRITICAL**: does evaluation compare predictions against dataset ground truth, never another model's output?

### Phase 2.5: Cross-Model Code Review (when CODE_REVIEW = true)

Skip this step if `CODE_REVIEW` is `false`.

Before deploying, send the experiment code to a secondary Codex reviewer with xhigh reasoning:

```text
spawn_agent:
  reasoning_effort: xhigh
  message: |
    Review the following experiment implementation for correctness.

    ## Experiment Plan
    [paste key sections from EXPERIMENT_PLAN.md]

    ## Method Description
    [paste from FINAL_PROPOSAL.md]

    ## Implementation
    [paste the experiment scripts or exact file paths plus relevant snippets]

    Check for:
    1. Does the code correctly implement the method described in the proposal?
    2. Are all hyperparameters from the plan reflected in the code?
    3. Are there logic bugs: wrong loss, wrong data split, missing eval, leakage, metric mismatch?
    4. Is the evaluation metric computed against ground truth, not another model's output?
    5. Are seeds, result paths, logging, and failure handling sufficient for reproducible experiments?

    Output:
    - BLOCKING issues that must be fixed before deployment
    - NON-BLOCKING issues that can wait
    - Suggested patches or checks
```

If BLOCKING issues are found, fix them and re-run this review once before Phase 3. Save the reviewer response and any fixes in `refine-logs/EXPERIMENT_CODE_REVIEW.md`. If reviewer delegation is unavailable, run the same checklist locally and mark the review `[local-only]`.

### Phase 3: Sanity Check (if SANITY_FIRST = true)

Before deploying the full experiment suite, run the sanity-stage experiment:

```
/run-experiment [sanity experiment command]
```

Wait for completion. Verify:
- Training loop runs without errors
- Metrics are computed and saved correctly
- GPU memory usage is within bounds
- Output format matches expectations

If sanity fails → fix the code, re-run. Do not proceed to full deployment with broken code.

If the same sanity failure repeats, trigger a second opinion: summarize the plan, code diff, command, logs, backend, and failure, then ask a fresh Codex reviewer agent for a rescue diagnosis. Apply only concrete fixes grounded in the logs.

### Phase 4: Deploy Full Experiments

Deploy experiments following the plan's milestone order. Route by job count and dependencies:

```
/run-experiment [experiment commands]
```

For large batches (≥10 jobs), multi-seed sweeps, or teacher→student phase dependencies, use the queue scheduler:

```
/experiment-queue [grid spec or manifest]
```

Auto-routing rule: if any milestone in `EXPERIMENT_PLAN.md` declares ≥10 jobs or declares phase dependencies, route that milestone to `/experiment-queue`; otherwise use `/run-experiment`. `/experiment-queue` adds OOM-aware retry with backoff, stale-screen cleanup, wave-transition race prevention, phase dependency enforcement, and crash-safe state persistence in `queue_state.json`.

For each milestone:
1. Deploy experiments in parallel (up to MAX_PARALLEL_RUNS for `/run-experiment`, or `max_parallel` from the queue manifest for `/experiment-queue`)
2. Use `/monitor-experiment` to track progress; if `/experiment-queue` is active, monitor `queue_state.json`
3. Collect results as experiments complete

Backend lifecycle rules:
- **Vast.ai**: record instance id, SSH endpoint, mounted data/checkpoints, estimated hourly cost, and cleanup policy. If `auto_destroy` is configured, write the exact cleanup command before launch.
- **Modal**: verify app/function, image/dependencies, secrets, volumes, and output persistence before launch.
- **Local/SSH**: verify GPU availability, environment activation, log path, and result path before launching.
- If a backend is unreachable or misconfigured, stop with a configuration issue instead of silently switching backend.

**🚦 Checkpoint (if AUTO_DEPLOY = false):**

```
🔧 Code implementation complete. Ready to deploy:

Milestone 0 (sanity): [status — passed/pending]
Milestone 1 (baseline): [N experiments, ~X GPU-hours]
Milestone 2 (main method): [N experiments, ~X GPU-hours]
Milestone 3 (ablations): [N experiments, ~X GPU-hours]

Total estimated: ~X GPU-hours on [N] GPUs

Deploy now? Or review the code first?
```

### Phase 5: Collect Initial Results

As experiments complete:

1. **Parse output files** (JSON/CSV/logs) for key metrics
2. **Training quality check** — if W&B data is available, invoke `/training-check` to detect NaN, loss divergence, plateaus, or overfitting. If W&B is not configured, skip silently.
3. **Update `refine-logs/EXPERIMENT_TRACKER.md`** — fill in Status and Notes columns
4. **Check success criteria** from EXPERIMENT_PLAN.md — did each experiment meet its bar?
5. **Write initial results summary:**

```markdown
# Initial Experiment Results

**Date**: [today]
**Plan**: refine-logs/EXPERIMENT_PLAN.md

## Results by Milestone

### M0: Sanity — PASSED
- [result]

### M1: Baselines
| Run | System | Key Metric | Status |
|-----|--------|-----------|--------|
| R001 | baseline_1 | X.XX | DONE |

### M2: Main Method
| Run | System | Key Metric | Status |
|-----|--------|-----------|--------|
| R003 | our_method | X.XX | DONE |

### M3: Ablations
...

## Summary
- [X/Y] must-run experiments completed
- Main result: [positive/negative/inconclusive]
- Ready for /auto-review-loop: [YES/NO]

## Next Step
→ /auto-review-loop "[topic]"
```

### Phase 5.5: Write Compact Log (when COMPACT = true)

**Skip entirely if `COMPACT` is `false`.**

Append each completed experiment to `EXPERIMENT_LOG.md`:

```markdown
## [Run ID] — [timestamp]
- **System**: [method name]
- **Config**: [key hyperparameters]
- **Result**: [primary metric = X.XX]
- **Verdict**: [positive / negative / inconclusive]
- **Reproduce**: `python train.py --config configs/run_id.yaml --seed 42`
```

### Phase 5.6: Auto Ablation Planning

After main experiments (M2) complete with positive results, invoke `/ablation-planner` to design ablation studies:

- Read the main results and method description
- Generate a claim-driven ablation plan: which components to remove, what to compare, and expected outcomes
- Append ablation blocks to `refine-logs/EXPERIMENT_PLAN.md` and `refine-logs/EXPERIMENT_TRACKER.md`
- If main results are negative or inconclusive, skip ablation planning and note that in the summary

If `/ablation-planner` is unavailable, skip silently.

### Phase 6: Handoff

Present final status:

```
🔬 Experiment bridge complete:
- Implemented: [N] experiment scripts
- Deployed: [N] experiments on [M] GPUs
- Completed: [X/Y] must-run, [A/B] nice-to-have
- Main result: [one sentence]

Results: refine-logs/EXPERIMENT_RESULTS.md
Tracker: refine-logs/EXPERIMENT_TRACKER.md

Ready for Workflow 2:
→ /auto-review-loop "[topic]"
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **CRITICAL — Evaluation must use dataset ground truth.** Always compare model predictions against the dataset's actual labels/targets, never another model's output. If the task has official eval scripts, prefer them.
- **Follow the plan.** Do not invent experiments not in EXPERIMENT_PLAN.md. If you think something is missing, note it but don't add it.
- **Sanity first.** Never deploy a full suite without verifying the sanity stage passes.
- **Reuse existing code.** Scan the project before writing new scripts. Extend, don't duplicate.
- **Save everything as JSON/CSV.** The auto-review-loop needs parseable results, not just terminal output.
- **Update the tracker.** `EXPERIMENT_TRACKER.md` should reflect real status after each run completes.
- **Don't wait forever.** If an experiment exceeds 2x its estimated time, flag it and move on to the next milestone.
- **Budget awareness.** Track GPU-hours against the plan's budget. Warn if approaching the limit.

## Composing with Other Skills

```
/idea-discovery "direction"          ← Workflow 1: find + refine + plan
/experiment-bridge                   ← you are here (Workflow 1.5: implement + deploy)
/auto-review-loop "topic"            ← Workflow 2: review + iterate
/paper-writing "NARRATIVE_REPORT.md" ← Workflow 3: write the paper

Or use /research-pipeline for the full end-to-end flow (includes this bridge).
```
