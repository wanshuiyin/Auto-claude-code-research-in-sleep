# Research Contract: When Does Unlearning Survive Distribution Shift?

## Selected Idea

- **Description**: study when approximate local unlearning rules remain valid under source-to-target distribution shift, and predict transfer success using forget-subspace stability, retain-forget entanglement, and linearization residual.
- **Source**: `refine-logs/FINAL_PROPOSAL.md`
- **Selection rationale**: this is the sharpest idea from discovery because it has a crisp failure mode, a tractable primary setting, and an evaluation story that is stronger than another local-loss variant.

## Core Claims

1. Out-of-distribution unlearning failure is structural rather than just noisy benchmark variance.
2. FSS, RFE, and LR predict OOD unlearning robustness better than naive in-distribution forget scores.
3. The diagnostic is actionable: it supports a choose-or-abstain policy that avoids bad transfers at modest cost.

## Method Summary

The paper focuses on path-oblivious local unlearning rules under source-to-target domain shift. Instead of proposing a large new system, it asks when a source-derived local update should be expected to survive target shift. The main quantities are geometric: how stable forget-relevant directions are from source to target, how entangled those transferred directions are with target retain-relevant directions, and how trustworthy a local linear approximation remains.

Empirically, the primary setting is ResNet-18 on CIFAR-100 with clean source data and CIFAR-100-C target shifts. The work compares retrain oracle, retain-only fine-tuning, and ascent-style local unlearning before moving to diagnostic extraction and controlled synthetic validation.

## Experiment Design

- **Datasets**: CIFAR-100, CIFAR-100-C, and synthetic linear data
- **Baselines**: retrain oracle, retain-only fine-tuning, ascent-style local unlearning
- **Metrics**: retain accuracy, forget gap, OOD unlearning gap, relearning budget, FSS, RFE, LR
- **Key hyperparameters**:
  - model: ResNet-18
  - source domain: clean CIFAR-100
  - target families: `T_noise`, `T_blur`, `T_digital`
  - forget sets: `F_random`, `F_cluster`, `F_entangled`
- **Compute budget**: roughly 150-240 GPU-hours for the main paper story

## Baselines

| Method | Dataset | Metric | Score | Source |
|--------|---------|--------|-------|--------|
| Retrain oracle | clean CIFAR-100 + `F_random` | retain acc / forget gap | pending | planned `R001` |
| Retain-only fine-tuning | clean CIFAR-100 + `F_random` | retain acc / forget gap | pending | planned `R002` |
| Ascent-style local unlearning | clean CIFAR-100 + `F_random` | retain acc / forget gap | pending | planned `R003` |

## Current Results

| Method | Dataset | Metric | Score | Notes |
|--------|---------|--------|-------|-------|
| none | none | none | pending | implementation scaffold only |

## Key Decisions

- Keep the main story on one primary backbone and one primary dataset first.
- Treat architecture variation as a robustness check, not the headline result.
- Use named shift families and named forget-set types so the run matrix stays stable across sessions.
- Separate theory validation (`R009`) from real-model diagnostics (`R008` and `R010`) to keep the claim structure readable.

## Status

- [x] Idea selected
- [x] Experiment plan frozen
- [x] Implementation scaffold created
- [ ] Baseline reproduced
- [ ] Main shift runs launched
- [ ] Diagnostics extracted
- [ ] Choose-or-abstain study complete
- [ ] Paper draft
