# Experiment Plan

> **Template for Workflow 1.5 (`/experiment-bridge`).** Fill in, save as `refine-logs/EXPERIMENT_PLAN.md`, then run `/experiment-bridge`.

**Problem**: [What problem does your method solve?]
**Method Thesis**: [One-sentence description of your approach]

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|-------|----------------|----------------------------|---------------|
| C1: [Main claim] | [Why] | [Evidence needed] | B1, B2 |
| C2: [Supporting claim] | [Why] | [Evidence needed] | B3 |

## Experiment Blocks

### Block 1: Main Result
- **Claim tested**: C1
- **Dataset / split / task**: [e.g., ImageNet val]
- **Compared systems**: [Your method vs. Baseline A vs. Baseline B]
- **Metrics**: [Primary: accuracy/PPL. Secondary: throughput]
- **Setup details**: [Backbone, optimizer, lr, epochs, seeds]
- **Success criterion**: [e.g., "> 2% accuracy over baseline"]
- **Failure interpretation**: [If negative, what does it mean?]
- **Priority**: MUST-RUN

### Block 2: Ablation Study
- **Claim tested**: C1 (novelty isolation)
- **Compared systems**: [Full method, -component A, -component B]
- **Success criterion**: [Each component contributes > 0.5%]
- **Priority**: MUST-RUN

### Block 3: [Additional Experiment]
- **Priority**: NICE-TO-HAVE

## Run Order

| Milestone | Goal | Runs | Decision Gate | Cost |
|-----------|------|------|---------------|------|
| M0: Sanity | Pipeline works | 1 quick run | Loss decreases? | ~0.5h |
| M1: Baselines | Reproduce baselines | Block 3 | Numbers match? | ~4h |
| M2: Main | Full method | Block 1 | Meets criterion? | ~8h |
| M3: Ablation | Components | Block 2 | Each matters? | ~6h |

## Compute Budget
- **Total estimated GPU-hours**: ~18h
- **Hardware**: [e.g., 4x RTX 3090]
- **Biggest bottleneck**: [e.g., baseline reproduction]

## Risks
- **Risk**: [What could go wrong] → **Mitigation**: [How to handle it]
