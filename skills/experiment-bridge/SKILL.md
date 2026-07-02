---
name: experiment-bridge
description: "Workflow 1.5: Bridge between idea discovery and auto review. Reads EXPERIMENT_PLAN.md, implements experiment code, deploys to GPU, collects initial results. Use when user says \"实现实验\", \"implement experiments\", \"bridge\", \"从计划到跑实验\", \"deploy the plan\", or has an experiment plan ready to execute."
argument-hint: [experiment-plan-path-or-topic]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Workflow 1.5: Experiment Bridge

Implement and deploy experiments from plan: **$ARGUMENTS**

## Overview

This skill bridges Workflow 1 (idea discovery + method refinement) and Workflow 2 (auto review loop). It takes the experiment plan and turns it into running experiments with initial results.

```
Workflow 1 output:                    This skill:                                    Workflow 2 input:
refine-logs/EXPERIMENT_PLAN.md   →   implement → GPT-5.5 review → deploy → collect → initial results ready
refine-logs/EXPERIMENT_TRACKER.md     code        (cross-model)    /run-experiment     for /auto-review-loop
refine-logs/FINAL_PROPOSAL.md
```

## Constants

- **CODE_REVIEW = true** — GPT-5.5 xhigh reviews experiment code before deployment. Catches logic bugs before wasting GPU hours. Set `false` to skip.
- **AUTO_DEPLOY = true** — Automatically deploy experiments after implementation + review. Set `false` to manually inspect code before deploying.
- **SANITY_FIRST = true** — Run the sanity-stage experiment first (smallest, fastest) before launching the rest. Catches setup bugs early.
- **MAX_PARALLEL_RUNS = 4** — Maximum number of experiments to deploy in parallel (limited by available GPUs).
- **BASE_REPO = false** — GitHub repo URL to use as base codebase. When set, clone the repo first and implement experiments on top of it. When `false` (default), write code from scratch or reuse existing project files.
- **COMPACT = false** — When `true`, (1) read `idea-stage/IDEA_CANDIDATES.md` instead of full `idea-stage/IDEA_REPORT.md` if available, (2) append experiment results to `EXPERIMENT_LOG.md` after collection.

> Override: `/experiment-bridge "EXPERIMENT_PLAN.md" — compact: true, base repo: https://github.com/org/project`

## Inputs

This skill expects one or more of:

1. **`refine-logs/EXPERIMENT_PLAN.md`** (best) — claim-driven experiment roadmap from `/experiment-plan`
2. **`refine-logs/EXPERIMENT_TRACKER.md`** — run-by-run execution table
3. **`refine-logs/FINAL_PROPOSAL.md`** — method description for implementation context
4. **`idea-stage/IDEA_CANDIDATES.md`** — compact idea summary (preferred when `COMPACT: true`) *(fall back to `./IDEA_CANDIDATES.md` if not found)*
5. **`idea-stage/IDEA_REPORT.md`** — full brainstorm output *(fall back to `./IDEA_REPORT.md` if not found)*

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

**Research-contract fallback**: if `idea-stage/docs/research_contract.md` does
not exist yet (idea selected outside `/idea-discovery`, or an older run),
create it now from `templates/RESEARCH_CONTRACT_TEMPLATE.md` using the selected
idea + claims from the experiment plan. Downstream `/result-to-claim` and
`/ablation-planner` read this file as the claims source, and session recovery
(`docs/SESSION_RECOVERY_GUIDE.md`) depends on it existing.

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

Before deploying, send the experiment code to GPT-5.5 xhigh for review:

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

If sanity fails → **auto-debug before giving up**. Budget: up to **2 patch
attempts** on the same failure, then up to **2 clean reimplements** (4 total):

1. **Read the error** — parse traceback, stderr, and log files. (The same
   read-the-primary-artifact discipline applies to surprising REVIEWER verdicts:
   see `shared-references/review-tracing.md` § *Debugging With Traces*.)
2. **Diagnose** — classify the failure:
   - OOM → reduce batch size or enable gradient checkpointing
   - ImportError → install missing package
   - FileNotFoundError → fix path or download data
   - CUDA error → check GPU availability, reduce model size
   - NaN/divergence → reduce learning rate, check data preprocessing
3. **Fix and re-run** — apply the fix, re-run sanity
4. **Attempt 2+ still failing? → Call in Codex rescue** (if Codex plugin installed):
   Before the next retry, invoke `/codex:rescue` to get a second opinion on the root cause. Codex independently reads the code and error logs — it may spot issues Claude missed (wrong tensor shapes, subtle import shadowing, config mismatches, etc.). Apply its suggested fix, then re-run.
   - If `/codex:rescue` is not available (plugin not installed), continue with Claude's own diagnosis
5. **Both patch attempts failed on the same failure? → Discard and reimplement cleanly**
   (up to 2 reimplements). Rewriting the failing script from `EXPERIMENT_PLAN.md` / the
   research contract is a PEER move to another patch, not a last resort — a third patch
   on top of two wrong ones is usually worse than a clean rebuild. Delete ONLY the
   attempt's own code/scaffolding (scripts this phase generated); the plan,
   `EXPERIMENT_TRACKER.md`, user-authored project source, collected data, and results
   are never deletable (see `shared-references/external-cadence.md` § *Let a broken
   attempt restart, not just patch*).
6. **Budget exhausted (2 patches + 2 reimplements), or two reimplements failed the SAME
   way?** → stop, report the failure with all attempted fixes and error logs. Two clean
   reimplements failing identically usually means the plan or the environment is wrong —
   say so explicitly in the report, because that (not the broken build itself) is what
   needs the human. Do not proceed with broken code.

> Never give up on the first failure. Most experiment crashes are fixable without human intervention.

### Phase 4: Deploy Full Experiments

Deploy experiments following the plan's milestone order. **Route by job count**:

**Small batch (≤5 jobs per milestone)** → use `/run-experiment` directly:
```
/run-experiment [experiment commands]
```

**Large batch (≥10 jobs, multi-seed sweeps, or phase dependencies)** → use `/experiment-queue` for proper orchestration:
```
/experiment-queue [grid spec or manifest]
```

Auto-routing rule: if any milestone in `EXPERIMENT_PLAN.md` declares ≥10 jobs (e.g., `seeds: [42, 200, 201, ...]` × `N: [64, 128, 256]` × `n: [50K, 150K, 500K, 652K]` = 36 jobs) or declares teacher→student phase dependencies, route that milestone to `/experiment-queue`. Otherwise use `/run-experiment`.

`/experiment-queue` adds: OOM-aware retry with backoff, stale-screen cleanup, wave-transition race prevention, phase dependency enforcement, crash-safe state persistence in `queue_state.json`. See `skills/experiment-queue/SKILL.md` for the manifest YAML format.

For each milestone:
1. Deploy experiments in parallel (up to MAX_PARALLEL_RUNS for `/run-experiment`, or `max_parallel` from manifest for `/experiment-queue`)
2. Use `/monitor-experiment` to track progress (reads from queue_state.json if `/experiment-queue` is active)
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
2. **Training quality check** — if W&B data is available (CLAUDE.md has `wandb: true` and `wandb_project`), invoke `/training-check` to detect NaN, loss divergence, plateaus, or overfitting. If W&B is not configured, skip silently.
3. **Update `refine-logs/EXPERIMENT_TRACKER.md`** — fill in Status and Notes columns
4. **Check success criteria** from EXPERIMENT_PLAN.md — did each experiment meet its bar?
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

This structured log survives session recovery — downstream skills read it instead of parsing screen output.

### Phase 5.6: Auto Ablation Planning

After main experiments (M2) complete with positive results, invoke `/ablation-planner` to design ablation studies:

- Read the main results and method description
- Generate a claim-driven ablation plan: which components to remove, what to compare, expected outcomes
- Append ablation blocks to `refine-logs/EXPERIMENT_PLAN.md` and `refine-logs/EXPERIMENT_TRACKER.md`
- If main results are negative or inconclusive, skip ablation planning and note in the summary

If `/ablation-planner` is not available, skip silently — the existing EXPERIMENT_PLAN.md ablation blocks (if any) remain unchanged.

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
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

## Key Rules

- **CRITICAL — Evaluation must use dataset ground truth.** When writing evaluation scripts, ALWAYS compare model predictions against the dataset's actual ground truth labels/targets — NEVER use another model's output as ground truth. Double-check: (1) ground truth comes from the dataset split, not from a baseline/backbone model, (2) evaluation metrics are computed against the same ground truth for all methods, (3) if the task has official eval scripts, use those.
- **Follow the plan.** Do not invent experiments not in EXPERIMENT_PLAN.md. If you think something is missing, note it but don't add it.
- **Sanity first.** Never deploy a full suite without verifying the sanity stage passes.
- **Reuse existing code.** Scan the project before writing new scripts. Extend, don't duplicate.
- **Save everything as JSON/CSV.** The auto-review-loop needs parseable results, not just terminal output.
- **Update the tracker.** `EXPERIMENT_TRACKER.md` should reflect real status after each run completes.
- **Don't wait forever.** If an experiment exceeds 2x its estimated time, flag it and move on to the next milestone.
- **Budget awareness.** Track GPU-hours against the plan's budget. Warn if approaching the limit.
- **Vast.ai lifecycle.** If using vast.ai instances, destroy them after all experiments complete and results are downloaded. Running instances cost money every second — don't leave them idle. Use `/vast-gpu destroy` or `/vast-gpu destroy-all` when done.
- **Modal lifecycle.** If using `gpu: modal`, no cleanup is needed — Modal auto-scales to zero after each run. But always show cost estimates before running and verify the spending limit is set at https://modal.com/settings (NEVER through CLI).

## Composing with Other Skills

```
/idea-discovery "direction"          ← Workflow 1: find + refine + plan
/experiment-bridge                   ← you are here (Workflow 1.5: implement + deploy)
/auto-review-loop "topic"            ← Workflow 2: review + iterate
/paper-writing "NARRATIVE_REPORT.md" ← Workflow 3: write the paper

Or use /research-pipeline for the full end-to-end flow (includes this bridge).
```
