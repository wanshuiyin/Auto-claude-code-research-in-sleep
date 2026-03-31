# Research Proposal: When Does Unlearning Survive Distribution Shift?

**Final Verdict**: READY  
**Date**: 2026-03-31  
**Selected Direction**: distribution-shift robustness theory for machine unlearning

## Problem Anchor

- **Bottom-line problem**: current machine unlearning methods can look effective in-distribution yet fail once evaluation moves to a shifted target distribution, and we do not know when this failure is structural versus accidental.
- **Must-solve bottleneck**: there is no mechanistic criterion that predicts whether an approximate unlearning rule learned or tuned on a source distribution will remain valid on a shifted target distribution.
- **Non-goals**:
  - proposing a large new unlearning system
  - claiming exact unlearning without retraining
  - benchmarking every modern LLM unlearning method
  - treating multiple random seeds on one setup as "generalization"
- **Constraints**:
  - realistic academic budget: roughly 150-300 GPU-hours
  - 6-10 week paper timeline
  - top-venue standard: one sharp claim plus a compact validation story
- **Success condition**: a reviewer should be able to say, "this paper tells me when local unlearning should survive domain shift, gives me a measurable predictor before I trust a method out-of-domain, and explains failures better than raw in-distribution forget accuracy alone."

## Technical Gap

Recent work has improved individual parts of the unlearning story, but not the distribution-shift question itself.

- `MUSE` and `MU-Bench` improve evaluation coverage, yet they do not provide a theory of why an unlearning rule that works on one source distribution should or should not survive target shift.
- `Why Fine-Tuning Struggles with Forgetting in Machine Unlearning?` explains within-environment failure of naive fine-tuning, but not source-to-target shift.
- `ILU` brings invariance into LLM unlearning and improves robustness to downstream fine-tuning, but it is a method prior, not a general criterion for unlearning under distribution shift.
- representation-erasure work such as `LEACE` shows how targeted latent removal can be formalized, but not when such removal should remain effective after domain shift.

The missing piece is a theory that connects shift robustness to a small number of measurable structural properties.

## Method Thesis

- **One-sentence thesis**: approximate unlearning survives distribution shift only when the forget-relevant update subspace is stable from source to target and sufficiently disentangled from target retain-relevant directions; these quantities can be estimated in practice and used to predict when local unlearning is trustworthy out of distribution.
- **Why this is the smallest adequate intervention**: instead of inventing another unlearning optimizer, the paper explains the shift-robustness bottleneck itself and adds only a lightweight diagnostic layer on top of existing methods.
- **Why this route is timely**: current literature already shows residual knowledge, relearning failures, and benchmark sensitivity; a shift-robustness criterion is the missing bridge between those observations and a reusable scientific principle.

## Contribution Focus

- **Dominant contribution**: a theory of unlearning under distribution shift for path-oblivious local unlearning rules, grounded in source-target forget-subspace stability and target retain-forget entanglement.
- **Optional supporting contribution**: a practical diagnostic score, the `Shift-Robustness Index`, plus a minimal source-projector unlearning rule as a constructive sanity check.
- **Explicit non-contributions**:
  - not a claim that all unlearning methods reduce to one theorem
  - not a full benchmark paper
  - not a universal impossibility result
  - not a new large-scale LLM unlearning recipe

## Proposed Method

### Complexity Budget

- **Frozen / reused backbone**: standard pretrained vision classifiers and existing approximate unlearning baselines.
- **New trainable components**: none required for the main claim.
- **Tempting additions intentionally not used**:
  - large meta-learners over deletion tasks
  - heavyweight attribution models
  - a broad multimodal benchmark
  - a central LLM-only story

### System Overview

We define a **shift environment pair** as:

`(e_s, e_t)` where source and target share the unlearning objective but differ in distribution.

For each source-target pair:

1. train or load a baseline model on the source domain
2. define aligned retain and forget partitions on source and target domains
3. extract local forget and retain signals at a common interface layer
4. summarize those signals as low-rank source and target subspaces
5. quantify how source and target domains differ geometrically
6. test whether those quantities predict out-of-distribution unlearning behavior

### Core Mechanism

#### 1. Transfer object

We focus on **path-oblivious local unlearning rules**:

- fine-tuning style updates
- ascent/descent mixtures
- projection-style representation edits
- other updates determined by local gradients, activations, or a small neighborhood around the starting model

This excludes exact retraining from the main theorem, which remains the oracle reference.

#### 2. Structural quantities

At a chosen representation or gradient interface, define:

- **Forget Subspace Stability (FSS)**:
  how well the principal forget directions align from source to target under domain shift
- **Retain-Forget Entanglement (RFE)**:
  how much the transferred forget directions overlap with target retain-relevant directions
- **Linearization Residual (LR)**:
  how poorly the local linear view approximates the effect of update steps in that environment

#### 3. Main theoretical claim

In a linearized or NTK-style regime, the **OOD unlearning gap** of a local unlearning rule from source to target can be upper-bounded by terms that increase with:

- forget-subspace misalignment
- retain-forget entanglement
- local nonlinearity / curvature residual

The constructive implication is:

- if FSS is high, RFE is low, and LR is small, transfer should succeed
- if FSS is low or RFE is high, in-distribution success should not be expected to survive target shift

#### 4. Practical diagnostic

We instantiate a pre-deployment score:

`Shift-Robustness Index = + FSS - lambda * RFE - mu * LR`

The paper does not need this exact algebraic form to be sacred; the key claim is that a small set of measurable structural quantities predicts OOD unlearning substantially better than naive in-distribution forget metrics.

### Minimal Constructive Sanity Check

To avoid a purely post-hoc theory paper, we include one simple constructive operator:

- estimate a source forget projector at a shared interface layer
- apply that projector or its gradient-space analogue on the shifted target domain
- test whether OOD success occurs exactly when the diagnostic predicts it should

This operator is intentionally simple. Its purpose is to operationalize the theorem, not to become a bloated new method.

## Why This Proposal Should Hold Under Shift

The proposal treats failure as a property of source-target geometry rather than of one benchmark or one optimizer. That makes the claim naturally portable across:

- **datasets / domains**: do forget-relevant directions survive source-to-target shift?
- **subpopulations**: do forget directions learned on one slice remain valid on another slice?
- **nuisance changes**: do covariate shifts change retain-forget entanglement enough to break local unlearning?

If the answer is "no," the theory predicts OOD failure. If the answer is "yes," a reusable forgetting rule becomes plausible under shift.

## Positioning Relative to Prior Work

- **vs. MUSE / MU-Bench**: those works ask how to evaluate more aspects of unlearning; this paper asks what structural conditions make unlearning survive distribution shift in the first place.
- **vs. FT-failure theory**: existing theory explains hidden retention within one setup; this work explains source-to-target robustness.
- **vs. ILU**: invariance is used here as an explanatory lens, not as the main contribution.
- **vs. LEACE / representation erasure**: those works provide erasure tools; this paper explains when erasure directions should transfer.
- **vs. meta-unlearning papers**: those papers try to learn better unlearning policies; this paper asks when any such learned policy should be expected to transfer.

## Minimal Claim-Driven Validation

### Claim 1
**Claim**: OOD robustness of local unlearning is predicted by FSS, RFE, and LR better than by standard in-distribution forget accuracy alone.

- **Necessary evidence**:
  - OOD failures actually occur across source-target shift pairs
  - the structural quantities correlate with those failures
  - the correlation survives across more than one baseline family

### Claim 2
**Claim**: when the diagnostic predicts shift robustness, a simple source-derived forgetting operator can work on shifted target domains; when it predicts non-robustness, the operator should fail.

- **Necessary evidence**:
  - a constructive rule succeeds in high-index settings
  - the same rule fails in low-index settings
  - abstaining based on the index is better than blindly applying local unlearning under shift

## Experimental Scope

### Primary empirical setting

Use vision classification first because it provides:

- manageable compute
- accessible representation geometry
- natural controllable domain shifts without excessive engineering

Recommended primary grid:

- **Primary model**: ResNet-18
- **Primary dataset**: CIFAR-100
- **Source domain**: clean CIFAR-100
- **Target shift families**:
  - `Noise shift`: Gaussian noise, shot noise, impulse noise from CIFAR-100-C, severity 3
  - `Blur shift`: defocus blur, glass blur, motion blur from CIFAR-100-C, severity 3
  - `Digital shift`: contrast, pixelate, JPEG compression from CIFAR-100-C, severity 3
- **Deletion units**:
  - `F_random`: random 5-class forget set
  - `F_cluster`: one semantically coherent 5-class superclass cluster
  - `F_entangled`: partial-slice deletion from sibling classes that remain in the retain set
- **Secondary robustness checks**:
  - severity sweep from 1 to 5 for the best shift family
  - one second backbone only after the main source-to-target story is established

### Optional secondary setting

One small LM appendix sanity check, only if time remains:

- compact MUSE-style or TOFU-style setting on a smaller model
- goal is not breadth, only to show the diagnostic is not vision-specific

## Risks and Mitigations

- **Risk**: the theory is too broad and becomes vacuous.  
  **Mitigation**: restrict the formal claim to path-oblivious local rules and define transfer gap precisely.

- **Risk**: empirical correlations are weak.  
  **Mitigation**: include controlled synthetic and linearized experiments where the theorem should hold most clearly.

- **Risk**: the paper feels like "metric engineering."  
  **Mitigation**: make the mechanistic theorem primary and use the score only as an operationalization.

- **Risk**: too many transfer axes create a benchmark paper by accident.  
  **Mitigation**: center the main result on source-to-target domain shift; treat architecture variation as a robustness check, not the headline axis.

## Final Recommendation

This is viable as a focused theory-plus-diagnostic paper if it stays disciplined:

- one dominant claim: OOD unlearning depends on source-target structural stability and disentanglement
- one supporting artifact: a practical diagnostic and abstention rule
- one compact empirical story: source-target shift matrices plus mechanistic correlation

That is sharp enough to justify a real paper and distinct enough from current unlearning literature.
