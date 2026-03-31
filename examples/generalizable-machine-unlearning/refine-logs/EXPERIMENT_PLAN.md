# Experiment Plan

**Problem**: determine when approximate machine unlearning remains valid under source-to-target distribution shift  
**Method Thesis**: local unlearning survives distribution shift when forget-relevant subspaces are stable from source to target and weakly entangled with target retain-relevant directions; these quantities can be measured and used to predict when to trust local unlearning out of distribution  
**Date**: 2026-03-31

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|-------|----------------|-----------------------------|---------------|
| C1 | OOD unlearning failure is structural, not just noisy benchmark variance | source-target gaps appear consistently across shifted domains and methods | B1 |
| C2 | FSS/RFE/LR predict OOD robustness better than direct forget metrics | strong correlation and ranking power across source-target pairs | B2, B3 |
| C3 | The diagnostic is actionable | index-based choose/abstain policy beats blind local unlearning under shift | B4 |

## Paper Storyline

- **Main paper must prove**:
  - current local unlearning does not survive domain shift uniformly
  - transfer is predicted by a small set of mechanistic quantities
  - those quantities support a useful deployment decision
- **Appendix can support**:
  - a small LM sanity check
  - extra baseline families
  - more dataset combinations
- **Experiments intentionally cut**:
  - full multimodal benchmarking
  - scaling to large LLMs as a core result
  - proposing and tuning a heavy new unlearning algorithm

## Experiment Blocks

### Block 1: OOD Unlearning Phenomenon

- **Claim tested**: C1
- **Why this block exists**: the paper needs an empirical OOD failure to explain
- **Dataset / split / task**:
  - CIFAR-100 classification
  - source: clean CIFAR-100
  - targets:
    - `T_noise`: Gaussian/shot/impulse noise, severity 3
    - `T_blur`: defocus/glass/motion blur, severity 3
    - `T_digital`: contrast/pixelate/JPEG, severity 3
  - deletion units:
    - `F_random`: random 5-class forget set
    - `F_cluster`: one 5-class superclass cluster
    - `F_entangled`: partial-slice deletion from sibling classes that remain in retain
- **Compared systems**:
  - retrain oracle
  - retain-only fine-tuning
  - gradient-ascent plus retain fine-tuning
  - one stronger teacher/distillation or bad-teacher baseline
- **Metrics**:
  - forget efficacy versus retrain oracle
  - retain accuracy
  - OOD unlearning gap
  - relearning budget on a lightweight recovery protocol
- **Setup details**:
  - backbone: start with ResNet-18 as the primary model to isolate shift effects
  - 3 seeds for final tables, 1 seed for early screening
  - source-tuned settings evaluated on `T_noise`, `T_blur`, and `T_digital`
  - architecture variation optional after the main story is established
- **Success criterion**: method rankings or gaps change materially under target shift
- **Failure interpretation**: if OOD behavior is uniformly stable, the theory paper weakens because there is little to explain
- **Table / figure target**: source-target shift matrix heatmap plus oracle-gap table
- **Priority**: MUST-RUN

### Block 2: Controlled Theory Validation

- **Claim tested**: C2
- **Why this block exists**: the theorem must hold clearly in a regime where its assumptions are most valid
- **Dataset / split / task**:
  - synthetic linear data with controllable forget/retain overlap
  - optionally logistic regression on shallow image features
- **Compared systems**:
  - local projection-style unlearning
  - fine-tuning-style update
  - retrain oracle
- **Metrics**:
  - OOD unlearning gap
  - FSS
  - RFE
  - LR
- **Setup details**:
  - create synthetic source-target shifts with controllable forget-direction drift and retain overlap
  - derive expected monotonic relationship between structural quantities and OOD failure
- **Success criterion**: the predicted relationships hold cleanly in the controlled setting
- **Failure interpretation**: if the theorem does not explain even the controlled regime, the formal story is too weak
- **Table / figure target**: phase diagram of transfer success versus alignment and entanglement
- **Priority**: MUST-RUN

### Block 3: Mechanistic Prediction in Real Models

- **Claim tested**: C2
- **Why this block exists**: the theory must matter beyond the toy setting
- **Dataset / split / task**:
  - same primary vision shift setups as Block 1
- **Compared systems**:
  - local unlearning baselines from Block 1
  - diagnostic using the Shift-Robustness Index
  - naive predictor using in-distribution forget score only
- **Metrics**:
  - correlation between the index and OOD unlearning gap
  - AUROC / ranking accuracy for predicting successful OOD unlearning
  - partial correlations controlling for baseline accuracy
- **Setup details**:
  - compute interface-layer representations and/or gradient summaries
  - estimate FSS and RFE by low-rank PCA / canonical angles
  - estimate LR via local perturbation residual or one-step linearization error
- **Success criterion**: the index predicts OOD robustness substantially better than direct forget accuracy
- **Failure interpretation**: if correlations are weak, the theory may be too abstract or the interface layer is poorly chosen
- **Table / figure target**: scatter plots and a predictor comparison table
- **Priority**: MUST-RUN

### Block 4: Actionability via Choose-or-Abstain

- **Claim tested**: C3
- **Why this block exists**: the paper should change practice, not only explain past failures
- **Dataset / split / task**:
  - source-target shift pairs from Block 1
- **Compared systems**:
  - always apply local unlearning
  - index-based choose/abstain policy
  - always retrain oracle cost baseline
- **Metrics**:
  - utility-forgetting tradeoff under a compute budget
  - number of bad transfers avoided
  - average cost per acceptable unlearning result
- **Setup details**:
  - define a decision threshold on the index using source validation environments
  - abstention means "do not trust local unlearning; escalate to retraining or target-specific tuning"
- **Success criterion**: the policy reduces catastrophic OOD failures with modest abstention cost
- **Failure interpretation**: if actionability is absent, the paper risks becoming a descriptive analysis only
- **Table / figure target**: risk-cost frontier
- **Priority**: MUST-RUN

### Block 5: Small LM Sanity Check

- **Claim tested**: external validity of C2
- **Why this block exists**: show the mechanism is not obviously vision-only
- **Dataset / split / task**:
  - compact MUSE-style or TOFU-style subset on a small LM
- **Compared systems**:
  - one or two feasible local baselines
  - shift-robustness diagnostic
- **Metrics**:
  - OOD unlearning gap
  - index correlation
- **Setup details**:
  - keep this intentionally small
  - run only if Blocks 1-4 are successful
- **Success criterion**: same directional trend as vision
- **Failure interpretation**: omit from main paper if noisy or compute-heavy
- **Table / figure target**: appendix sanity-check table
- **Priority**: NICE-TO-HAVE

## Run Order and Milestones

| Milestone | Goal | Runs | Decision Gate | Cost | Risk |
|-----------|------|------|---------------|------|------|
| M0 | sanity-check clean-source pipeline | retrain oracle plus 2 local baselines on clean CIFAR-100 | metrics match oracle directionally | 10-15 GPUh | metric bugs |
| M1 | establish OOD phenomenon on named shifts | runs across `T_noise`, `T_blur`, `T_digital` and `F_random` / `F_cluster` | rank changes or clear oracle-gap instability under shift visible | 40-60 GPUh | shift effect too small |
| M2 | validate theorem in controlled setting | synthetic plus shallow-model sweeps | monotonic relation holds | 10-20 GPUh | theorem too weak |
| M3 | real-model mechanistic prediction | full index extraction across the 3 shift families | index beats naive predictors | 35-55 GPUh | noisy measurements |
| M4 | actionability study | choose/abstain decision runs on the 3 shift families | risk-cost frontier improves over always-local | 20-30 GPUh | threshold unstable |
| M5 | robustness extension | severity sweep or second backbone on the strongest shift family | same qualitative story holds | 20-35 GPUh | limited lift |
| M6 | optional appendix extension | second dataset or small LM sanity check | same directional trend | 25-50 GPUh | compute creep |

## Compute and Data Budget

- **Total estimated GPU-hours**: 150-240 GPUh without LM appendix; 180-290 GPUh with appendix
- **Data preparation needs**:
  - CIFAR-100-C loader or generated corruption pipeline
  - forget-set construction script for `F_random`, `F_cluster`, `F_entangled`
  - interface-layer extraction pipeline
- **Human evaluation needs**: none in the core plan
- **Biggest bottleneck**: reproducible source-target shift matrices with meaningful forget semantics

## Risks and Mitigations

- **Risk**: shift matrices are noisy rather than structurally different  
  **Mitigation**: use retrain oracle gaps and consistent source-target splits, not raw absolute scores alone

- **Risk**: FSS/RFE depend too much on the chosen layer  
  **Mitigation**: pre-register one primary layer and one robustness check layer

- **Risk**: theory works only in synthetic settings  
  **Mitigation**: make the main empirical claim predictive rather than exact, and keep theorem scope honest

- **Risk**: too many baselines slow progress  
  **Mitigation**: start with 3 strong baseline families plus retrain oracle

## First Three Runs to Launch

1. `R001-R003`: ResNet-18 on clean CIFAR-100 with `F_random`, comparing retrain oracle, retain-only FT, and ascent-style local unlearning
2. `R004-R006`: evaluate the same three systems on `T_noise` with `F_random`
3. `R007-R009`: repeat target evaluation on `T_blur` with `F_cluster`, then extract diagnostics to verify FSS/RFE move in the expected direction

## Final Checklist

- [ ] Main OOD failure table is covered
- [ ] Mechanistic quantities are defined before large experiments
- [ ] Theory is validated in a controlled regime
- [ ] Prediction beats naive forget metrics
- [ ] Choose/abstain policy is evaluated under shift
- [ ] Nice-to-have LM runs are separated from the core paper
