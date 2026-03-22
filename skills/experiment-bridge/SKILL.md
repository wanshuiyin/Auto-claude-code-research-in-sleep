---
name: experiment-bridge
description: "Workflow 1.5: Bridge between idea discovery and auto review. Reads EXPERIMENT_PLAN.md, implements experiment code, deploys to GPU, collects initial results. Use when user says \"实现实验\", \"implement experiments\", \"bridge\", \"从计划到跑实验\", \"deploy the plan\", or has an experiment plan ready to execute."
argument-hint: [experiment-plan-path-or-topic]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Workflow 1.5: Experiment Bridge

Implement and deploy experiments from plan: **$ARGUMENTS**

## Overview

This skill bridges Workflow 1 (idea discovery + method refinement) and Workflow 2 (auto review loop). It takes the experiment plan and turns it into running experiments with initial results.

```
Workflow 1 output:                    This skill:                                    Workflow 2 input:
refine-logs/EXPERIMENT_PLAN.md   →   implement → GPT-5.4 review → deploy → collect → initial results ready
refine-logs/EXPERIMENT_TRACKER.md     code        (cross-model)    /run-experiment     for /auto-review-loop
refine-logs/FINAL_PROPOSAL.md
```

## Constants

- **CODE_REVIEW = true** — GPT-5.4 xhigh reviews experiment code before deployment. Catches logic bugs before wasting GPU hours. Set `false` to skip.
- **AUTO_DEPLOY = true** — Automatically deploy experiments after implementation + review. Set `false` to manually inspect code before deploying.
- **SANITY_FIRST = true** — Run the sanity-stage experiment first (smallest, fastest) before launching the rest. Catches setup bugs early.
- **MAX_PARALLEL_RUNS = 4** — Maximum number of experiments to deploy in parallel (limited by available GPUs).
- **BASE_REPO = false** — GitHub repo URL to use as base codebase. When set, clone the repo first and implement experiments on top of it. When `false` (default), write code from scratch or reuse existing project files.

> Override: `/experiment-bridge "EXPERIMENT_PLAN.md" — base repo: https://github.com/org/project`

## Inputs

This skill expects one or more of:

1. **`refine-logs/EXPERIMENT_PLAN.md`** (best) — claim-driven experiment roadmap from `/experiment-plan`
2. **`refine-logs/EXPERIMENT_TRACKER.md`** — run-by-run execution table
3. **`refine-logs/FINAL_PROPOSAL.md`** — method description for implementation context
4. **`IDEA_REPORT.md`** — fallback if refine-logs don't exist

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
# Read the repo's README, understand its structure, find entry points
# Implement experiments by modifying/extending this codebase
```

For each milestone (in order), write the experiment scripts:

1. **Check existing code** — scan the project (or cloned `base_repo/`) for existing experiment scripts, model code, data loaders. Reuse as much as possible.

2. **Implement missing pieces:**
   - Training scripts with proper argparse (all hyperparameters configurable)
   - Evaluation scripts computing the specified metrics
   - Data loading / preprocessing if needed
   - Baseline implementations if not already present
   - Fixed random seeds for reproducibility
   - Results saved to JSON/CSV for later analysis
   - Proper logging (wandb if configured in CLAUDE.md)

3. **Follow the plan's run order** — implement sanity-stage experiments first, then baselines, then main method, then ablations.

4. **Self-review before deploying:**
   - Are all hyperparameters from EXPERIMENT_PLAN.md reflected in argparse?
   - Is the random seed fixed and controllable?
   - Are results saved in a parseable format (JSON/CSV)?
   - Does the code match FINAL_PROPOSAL.md's method description?

### Phase 2.5: Cross-Model Code Review (when CODE_REVIEW = true)

**Skip this step if `CODE_REVIEW` is `false`.**

Before deploying, send the experiment code to GPT-5.4 xhigh for review:

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Review the following experiment implementation for correctness.

    ## Experiment Plan:
    [paste key sections from EXPERIMENT_PLAN.md]

    ## Method Description:
    [paste from FINAL_PROPOSAL.md]

    ## Implementation:
    [paste the experiment scripts]

    Check for:
    1. Does the code correctly implement the method described in the proposal?
    2. Are all hyperparameters from the plan reflected in the code?
    3. Are there any logic bugs (wrong loss function, incorrect data split, missing eval)?
    4. Is the evaluation metric computed correctly?
    5. **CRITICAL: Does evaluation use the dataset's actual ground truth labels — NOT another model's output as ground truth?** This is a common and severe bug.
    6. Any potential issues (OOM risk, numerical instability, missing seeds)?

    For each issue found, specify: CRITICAL / MAJOR / MINOR and the exact fix.
```

**On review results:**
- **No CRITICAL issues** → proceed to Phase 3
- **CRITICAL issues found** → fix them, then re-submit for review (max 2 rounds)
- **Codex MCP unavailable** → skip silently, proceed to Phase 3 (graceful degradation)

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

### Phase 4: Deploy Full Experiments

Deploy experiments following the plan's milestone order:

```
/run-experiment [experiment commands]
```

For each milestone:
1. Deploy experiments in parallel (up to MAX_PARALLEL_RUNS)
2. Use `/monitor-experiment` to track progress
3. Collect results as experiments complete

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
2. **Update `refine-logs/EXPERIMENT_TRACKER.md`** — fill in Status and Notes columns
3. **Check success criteria** from EXPERIMENT_PLAN.md — did each experiment meet its bar?
4. **Write initial results summary:**

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

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **CRITICAL — Evaluation must use dataset ground truth.** When writing evaluation scripts, ALWAYS compare model predictions against the dataset's actual ground truth labels/targets — NEVER use another model's output as ground truth. Double-check: (1) ground truth comes from the dataset split, not from a baseline/backbone model, (2) evaluation metrics are computed against the same ground truth for all methods, (3) if the task has official eval scripts, use those.
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
