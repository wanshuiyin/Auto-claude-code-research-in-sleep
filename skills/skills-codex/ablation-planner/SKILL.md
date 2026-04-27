---
name: ablation-planner
description: "Use when main results pass result-to-claim (`claim_supported = yes` or `partial`) and ablation studies are needed for paper submission. A secondary Codex agent designs ablations from a reviewer's perspective; the local executor reviews feasibility and implements."
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Ablation Planner

Systematically design ablation studies that answer the questions reviewers will ask. The reviewer agent leads the design; the local executor reviews feasibility and implements.

## Context: $ARGUMENTS

## When to Use

- Main results pass `/result-to-claim` with `claim_supported = yes` or `partial`
- The user explicitly requests ablation planning
- `/auto-review-loop` identifies missing ablations

## Workflow

### Step 1: Prepare Context

Read available project files to build the full picture:

- Method description and components (from `docs/research_contract.md`, project notes, or method docs)
- Current experiment results (from `EXPERIMENT_LOG.md`, `EXPERIMENT_TRACKER.md`, or W&B)
- Confirmed and intended claims (from `/result-to-claim` output or project notes)
- Available compute resources (from server notes, run configs, or user-provided budget)

### Step 2: Codex Designs Ablations

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    You are a rigorous ML reviewer planning ablation studies.
    Given this method and results, design ablations that:

    1. Isolate the contribution of each novel component
    2. Answer questions reviewers will definitely ask
    3. Test sensitivity to key hyperparameters
    4. Compare against natural alternative design choices

    Method: [description from project files]
    Components: [list of removable or replaceable components]
    Current results: [key metrics from experiments]
    Claims: [what we claim and current evidence]

    For each ablation, specify:
    - name: what to change (for example, "remove module X", "replace Y with Z")
    - what_it_tests: the specific question this answers
    - expected_if_component_matters: what we predict if the component is important
    - priority: 1 (must-run) to 5 (nice-to-have)

    Also provide:
    - coverage_assessment: what reviewer questions these ablations answer
    - unnecessary_ablations: experiments that seem useful but will not add insight
    - suggested_order: run order optimized for maximum early information
    - estimated_compute: total GPU-hours estimate
```

If delegation is unavailable, generate the same plan locally and mark it `[pending external review]`.

### Step 3: Parse Ablation Plan

Normalize the response into a structured format:

```markdown
## Ablation Plan

### Component Ablations (highest priority)
| # | Name | What It Tests | Expected If Matters | Priority |
|---|------|---------------|---------------------|----------|
| 1 | remove module X | contribution of X | performance drops on metric Y | 1 |
| 2 | replace X with simpler Z | value of learned vs fixed | drops, especially on dataset A | 2 |

### Hyperparameter Sensitivity
| # | Parameter | Values to Test | What It Tests | Priority |
|---|-----------|----------------|---------------|----------|
| 3 | lambda | [0.01, 0.1, 1.0] | sensitivity to regularization | 3 |

### Design Choice Comparisons
| # | Name | What It Tests | Priority |
|---|------|---------------|----------|
| 4 | joint vs separate matching | whether joint adds value | 4 |

### Coverage Assessment
[What reviewer questions these ablations answer]

### Unnecessary Ablations
[Experiments that seem useful but will not add insight - skip these]

### Run Order
[Optimized for maximum early information]

### Estimated Compute
[Total GPU-hours]
```

### Step 4: CC Reviews Feasibility

Before running anything, the local executor checks:

- Compute budget - Can you afford all ablations with available GPUs?
- Code changes - Which ablations need code modifications vs config-only changes?
- Dependencies - Which ablations can run in parallel?
- Cuts - If budget is tight, propose removing lower-priority ablations and ask the reviewer agent to re-prioritize when possible

### Step 5: Implement and Run

1. Create configs or scripts for each ablation (config-only changes first)
2. Smoke test each ablation before the full run
3. Run in the suggested order, using descriptive names (for example, `ablation-no-module-X`)
4. Track results in `EXPERIMENT_LOG.md`
5. After all ablations complete, update `findings.md` with insights

## Rules

- **The reviewer agent leads the design.** Do not pre-filter or bias the ablation list before external review sees it. The reviewer thinks like a reviewer; the local executor thinks like an engineer.
- Every ablation must have a clear `what_it_tests` and `expected_if_component_matters`. No "just try it" experiments.
- Config-only ablations take priority over those needing code changes (faster, less error-prone).
- If total compute exceeds budget, propose cuts and ask for re-prioritization - do not silently drop ablations.
- Component ablations (remove or replace) take priority over hyperparameter sweeps.
- Do not generate ablations for components identical to the baseline (no-op ablations).
- Record all ablation results in `EXPERIMENT_LOG.md`, including negative results (for example, component removal had no effect).
