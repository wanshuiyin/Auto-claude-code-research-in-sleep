# Idea Discovery Report

**Direction**: generalizable machine unlearning across architectures, datasets, and deletion requests  
**Date**: 2026-03-31  
**Pipeline**: research-lit -> idea-creator -> novelty-check -> research-review -> research-refine-pipeline  
**Status**: SELECTED_AND_REFINED

## Selected Idea

Chosen direction: **Unlearning Under Distribution Shift**.

- Refined proposal: `refine-logs/FINAL_PROPOSAL.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Review summary: `refine-logs/REVIEW_SUMMARY.md`

## Executive Summary

The strongest opportunity is not another per-benchmark unlearning loss. The central unresolved question is when an unlearning rule that works in-distribution should remain valid after a source-to-target distribution shift. After ranking the candidate directions, the selected path is now a **theory-plus-diagnostic paper** on unlearning under distribution shift.

## Literature Landscape

### Current clusters

1. **Approximate unlearning algorithms**
   - Fine-tuning and ascent-style methods remain the default family.
   - More recent variants include meta-learning and robust optimization directions such as LTU (ECCV 2024), ILU (ICML 2025), DMM / Datamodel Matching (ICLR 2025), and MUDMAN (NeurIPS 2025 workshop).

2. **Evaluation and robustness papers**
   - `MU-Bench` broadens task/modality coverage and standardizes deleted samples and trained models.
   - `MUSE` expands LM evaluation to six dimensions, including privacy leakage, scalability, and sequential requests.
   - `Are We Really Unlearning?` and `Do Unlearning Methods Remove Information from Language Model Weights?` show strong residual-memory and recoverability failures.
   - `Towards LLM Unlearning Resilient to Relearning Attacks` studies robustness to relearning.

3. **Theory / mechanistic work**
   - `Why Fine-Tuning Struggles with Forgetting in Machine Unlearning?` explains why naive FT can keep hidden forget information even when direct forget loss looks good.
   - Representation-erasure work such as `LEACE` provides adjacent tools, but not a full generalizable unlearning story.

### What is still missing

1. **Transfer is not operationalized as the main claim.**
   - Existing "generalization" claims are usually about robustness to one downstream fine-tuning setting or about broad task coverage, not transfer of the unlearning rule itself across held-out settings.

2. **Benchmarks still allow protocol overfitting.**
   - Current benchmarks standardize datasets and metrics, but they do not enforce train/test separation over deletion-request families, architectures, or domain shifts in the way domain generalization benchmarks do.

3. **Methods are usually tied to one model family or one deletion construction.**
   - Most methods are weight-space procedures specialized to a single backbone and a single forget setting.

4. **We lack a mechanistic criterion for transferability.**
   - Current theory explains why forgetting can fail in one model, but not when a forgetting rule should transfer across architectures or deletion environments.

## Ranked Ideas

### 1. GURU-Bench: Generalization Under Realistic Unlearning
**Type**: benchmark / evaluation  
**Status**: RECOMMENDED

- **One-sentence thesis**: Build the first unlearning benchmark whose main object is not forget accuracy on a fixed protocol, but transfer to held-out architectures, datasets, deletion-request families, and recoverability tests.
- **Exact gap addressed**: `MU-Bench` standardizes task/modality coverage and `MUSE` broadens evaluation, but neither creates a train/test split over **unlearning environments** that can distinguish reusable forgetting rules from benchmark-specific edits.
- **Why it should generalize**: The benchmark explicitly treats deletion requests, architectures, and domains as environments; a method only scores well if its forgetting behavior transfers beyond the conditions used to design it.
- **Minimal kill experiment**: Take 4-6 representative existing methods, train/tune them on one architecture and deletion family, then test on held-out architecture + shifted deletion family. If rankings remain essentially unchanged and every method transfers smoothly, the benchmark adds limited value; if rankings collapse or invert, the benchmark exposes a real blind spot.
- **Closest prior work and differentiation**:
  - `MU-Bench` (2024): broad multitask multimodal coverage, but not held-out transfer splits over unlearning environments.
  - `MUSE` (2024): six-way LM evaluation including privacy/scalability/sequentiality, but still not a generalization benchmark over architectures/datasets/deletion families.
  - `Are We Really Unlearning?` (ICLR 2025), `Do Unlearning Methods Remove Information from Language Model Weights?` (ICLR 2025): stronger failure tests, but not a unified transfer protocol.
- **Why reviewers may care**: It changes what counts as evidence for machine unlearning and can immediately re-rank existing methods.
- **Likely reviewer objection**: "This is only a benchmark paper."  
  Response path: make the benchmark claim sharper by showing that current conclusions are unstable under transfer and by introducing at least one new metric, such as minimum recoverability budget under shift.

### 2. Cross-Model Forgetting Subspaces
**Type**: method  
**Status**: STRONG_METHOD_CANDIDATE

- **One-sentence thesis**: Learn a shared representation-level forgetting subspace from multiple backbones so that unlearning acts on transferable latent factors rather than model-specific parameters.
- **Exact gap addressed**: Current methods mostly operate in weight space or on single-model activations; they do not learn a deletion mechanism designed to port across architectures.
- **Why it should generalize**: If the deleted information corresponds to latent factors that recur across models, then erasing aligned subspaces plus a small model-specific adapter should transfer better than learning per-model parameter edits.
- **Minimal kill experiment**: Learn the forgetting subspace on two architectures and test on a held-out third architecture for the same deletion family. If cross-model performance collapses to the level of naive FT/RMU-style baselines, the shared-subspace thesis is weak.
- **Closest prior work and differentiation**:
  - `LEACE` (NeurIPS 2023): concept erasure with linear guarantees, but not trained for machine unlearning transfer across architectures or deletion families.
  - `RMU` and follow-up representation-misdirection papers: strong LLM unlearning baselines, but still model-specific and not designed as cross-architecture transferable operators.
  - `ILU` (ICML 2025): injects invariance for robustness to downstream fine-tuning, not for cross-architecture / cross-dataset transferable deletion rules.
- **Why reviewers may care**: It gives a concrete mechanism for architecture-agnostic forgetting instead of treating transfer as pure evaluation.
- **Likely reviewer objection**: "Shared latent factors may not align across heterogeneous backbones."  
  Response path: start with related families (ResNet/ViT or Llama/Mistral-style dense decoders), and make alignment diagnostics part of the paper.

### 3. Oracle-to-Operator Unlearning
**Type**: method  
**Status**: HIGH_UPSIDE_HIGH_RISK

- **One-sentence thesis**: Distill many exact or high-quality retraining outcomes into a deletion-conditioned operator that predicts reusable unlearning updates for unseen deletion requests.
- **Exact gap addressed**: Existing methods optimize one request at a time; they do not explicitly learn from a family of retraining solutions to produce a reusable deletion rule.
- **Why it should generalize**: The operator is trained on a task family of deletion requests and learns the mapping from forget-set statistics to a good update, which should transfer better than hand-designed optimization heuristics.
- **Minimal kill experiment**: Generate retraining targets for small-scale deletion tasks, train the operator on one family, and test on unseen forget sets. If it does not beat simple approximate baselines on held-out requests with the same compute budget, the idea is not worth scaling.
- **Closest prior work and differentiation**:
  - `Learning to Unlearn for Robust Machine Unlearning` (ECCV 2024): meta-learning for better forgetting/remembering tradeoff, but not clearly framed as transfer across unseen deletion families, architectures, and teacher targets.
  - `MUDMAN` (2025 workshop): meta-unlearning components for robust LLM unlearning, primarily around irreversibility.
  - `Datamodel Matching` (ICLR 2025): predicts retrained outputs via attribution, but not a train-once deletion-conditioned operator designed for held-out transfer across environments.
- **Why reviewers may care**: It turns retraining from a gold-standard evaluator into a supervision source for a reusable algorithm.
- **Likely reviewer objection**: "This may just be a complicated approximation to retraining with limited practical range."  
  Response path: keep the operator small, compare against DMM/LTU-style baselines, and show transfer to unseen deletion families.

### 4. Transferability Theory for Unlearning Rules
**Type**: theory / mechanistic  
**Status**: STRONG_BACKUP

- **One-sentence thesis**: Characterize when an unlearning rule transfers by relating success to the stability of forget-relevant gradient or representation subspaces across deletion environments.
- **Exact gap addressed**: Existing theory mostly explains why forgetting fails inside one setup; it does not tell us when a rule learned in one environment should transfer to another.
- **Why it should generalize**: The criterion is explicitly about cross-environment invariance; if the forget signal is stable while nuisance retain directions vary, transfer is plausible, and if not, benchmark overfitting is expected.
- **Minimal kill experiment**: In a linear or NTK-style setting, derive the criterion; empirically measure subspace alignment across deletion environments and test whether it predicts transfer of actual unlearning methods. If the alignment score does not correlate with transfer, the theory is not informative.
- **Closest prior work and differentiation**:
  - `Why Fine-Tuning Struggles with Forgetting in Machine Unlearning?` (ICLR 2025): explains hidden forget retention within a linear setting, but not transfer across environments.
  - `ILU` (ICML 2025): uses invariance as a method prior, but does not provide a general transferability criterion for unlearning rules.
  - `LEACE` (NeurIPS 2023): theory for linear concept erasure, not machine-unlearning transferability.
- **Why reviewers may care**: It provides a falsifiable mechanism for when generalizable unlearning is possible versus structurally doomed.
- **Likely reviewer objection**: "The theory may be too stylized to matter for modern models."  
  Response path: make the theory predictive, not decorative, via an empirical correlation section.

### 5. Recoverability-Under-Shift Evaluation
**Type**: evaluation / analysis  
**Status**: USEFUL_IF_SCOPED_AS_PART_OF_IDEA_1

- **One-sentence thesis**: Replace single-point forget metrics with a recoverability curve measuring how much shifted relearning or probing effort is needed to restore forgotten information.
- **Exact gap addressed**: Existing work shows residual knowledge and relearning vulnerabilities, but usually under one attack family; there is no standardized notion of recoverability budget under domain shift.
- **Why it should generalize**: A true forgetting rule should remain hard to recover even when the attacker uses related-but-shifted data or a different probing route.
- **Minimal kill experiment**: Compare direct forget metrics with recoverability curves under matched and shifted relearning data. If the recoverability ranking is almost identical to standard forget accuracy and reveals no new failures, the contribution is too narrow alone.
- **Closest prior work and differentiation**:
  - `Are We Really Unlearning?` (ICLR 2025): residual knowledge via perturbation neighborhoods.
  - `Do Unlearning Methods Remove Information from Language Model Weights?` (ICLR 2025): adversarial evaluation of whether information remains in weights.
  - `Towards LLM Unlearning Resilient to Relearning Attacks` (ICML 2025): defenses against relearning attacks.
- **Why reviewers may care**: It yields a stronger, attack-relevant metric that can be attached to either a benchmark or a method paper.
- **Likely reviewer objection**: "This is a metric paper unless tied to a broader benchmark or method."  
  Response path: package it inside Idea 1 or use it as the decisive evaluation axis for Idea 2 or 3.

## Novelty Check Summary

### Overall verdict

- **Idea 1** novelty: **HIGH**
  - The closest work standardizes breadth (`MU-Bench`) or evaluation dimensions (`MUSE`) but does not directly benchmark **transfer of unlearning rules across held-out environments**.
- **Idea 2** novelty: **MEDIUM-HIGH**
  - Adjacent to representation erasure and RMU-style activation methods, but differentiated if framed explicitly as **cross-architecture transferable unlearning** with aligned latent spaces.
- **Idea 3** novelty: **MEDIUM**
  - Significant overlap risk with LTU, MUDMAN, and DMM. It remains viable only if the paper is explicitly about **train-once transfer across deletion families / architectures**, not just "meta-learning improves unlearning."
- **Idea 4** novelty: **HIGH**
  - Theoretical overlap exists with FT-failure analyses and invariance-motivated methods, but a transferability criterion for unlearning rules appears open.
- **Idea 5** novelty: **MEDIUM-HIGH**
  - Strong overlap with recent residual-memory and relearning papers unless positioned as part of a broader transfer benchmark.

## Recommended Order

1. **Idea 1: GURU-Bench**
   - Best combination of novelty, feasibility, clear falsifiability, and alignment with your brief that problem formulation/evaluation is the bottleneck.
2. **Idea 2: Cross-Model Forgetting Subspaces**
   - Best method paper if you want a technical mechanism rather than a benchmark-first contribution.
3. **Idea 4: Transferability Theory**
   - Strong companion or backup paper, especially if the benchmark reveals clear failure regimes.
4. **Idea 3: Oracle-to-Operator Unlearning**
   - High-upside but more overlap and implementation risk.
5. **Idea 5: Recoverability-Under-Shift**
   - Best used as a metric block inside Idea 1 or 2, not as a standalone main paper.

## Eliminated / Deprioritized Directions

| Idea | Reason |
|------|--------|
| "Just add IRM/invariance to standard unlearning" | Too close to ILU unless expanded to multi-architecture, multi-dataset transfer with a stronger evaluation story. |
| "General meta-unlearning" | Too close to LTU / MUDMAN unless explicitly centered on held-out deletion-family transfer. |
| "Only stronger relearning attack paper" | Strong recent overlap with residual-knowledge and relearning literature. |
| "Another retain-vs-forget loss tweak" | Fails your novelty and top-venue criteria. |

## Downloaded Papers

Saved to `papers/`:

- `papers/2402.08787.pdf` — *Rethinking Machine Unlearning for Large Language Models*
- `papers/2407.06460.pdf` — *MUSE: Machine Unlearning Six-Way Evaluation for Language Models*
- `papers/2410.23232.pdf` — *Attribute-to-Delete: Machine Unlearning via Datamodel Matching*
- `papers/2502.05374.pdf` — *Towards LLM Unlearning Resilient to Relearning Attacks: A Sharpness-Aware Minimization Perspective and Beyond*
- `papers/2506.12484.pdf` — *Robust LLM Unlearning with MUDMAN: Meta-Unlearning with Disruption Masking And Normalization*

## Sources Used

- MU-Bench (2024): https://openreview.net/forum?id=FCfY1wYkn9&noteId=bJsWbr3FiO
- MUSE (2024): https://arxiv.org/abs/2407.06460
- Rethinking Machine Unlearning for LLMs (2024): https://arxiv.org/abs/2402.08787
- Learning to Unlearn for Robust Machine Unlearning (ECCV 2024): https://doi.org/10.1007/978-3-031-72943-0_12
- Why Fine-Tuning Struggles with Forgetting in Machine Unlearning? (ICLR 2025): https://openreview.net/forum?id=CGfWyU28Pd
- Datamodel Matching / Attribute-to-Delete (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/hash/7c799b09cc40973ceaa47da50131dc63-Abstract-Conference.html
- Are We Really Unlearning? (ICLR 2025): https://openreview.net/pdf?id=HsjHGNYv2O
- Do Unlearning Methods Remove Information from Language Model Weights? (ICLR 2025): https://openreview.net/forum?id=uDjuCpQH5N
- Invariance Makes LLM Unlearning Resilient Even to Unanticipated Downstream Fine-Tuning (ICML 2025): https://proceedings.mlr.press/v267/wang25en.html
- Towards LLM Unlearning Resilient to Relearning Attacks (ICML 2025): https://arxiv.org/abs/2502.05374
- LEACE (NeurIPS 2023): https://openreview.net/forum?id=awIpKpwTwF&noteId=Ju4XcafMir
- MUDMAN (2025): https://arxiv.org/abs/2506.12484

## Next Step

The idea-selection stage is complete.

Recommended execution path:

1. implement source-target shift splits and diagnostic extraction
2. reproduce 3 strong local unlearning baselines plus retrain oracle
3. validate the shift-robustness theory with the plan in `refine-logs/EXPERIMENT_PLAN.md`
