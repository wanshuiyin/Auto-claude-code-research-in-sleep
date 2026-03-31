# Research Brief

## Problem Statement

I want strong research ideas on **generalizable machine unlearning**, not just marginal improvements on a fixed benchmark. The central question is: **how can we forget a target subset or concept while maintaining utility, and have that forgetting behavior transfer beyond the exact setting used during method design?**

Current machine unlearning work often overfits to a narrow protocol: one model family, one dataset, one deletion type, one utility metric, and one post-hoc evaluation recipe. A method may look effective because it is tuned to a specific deletion distribution or benchmark artifact, not because it captures a transferable principle of forgetting. I want ideas that explicitly address this gap.

I care about at least one of the following forms of generalization:

1. **Cross-architecture generalization**: the unlearning objective or mechanism works across model families, not only on one backbone.
2. **Cross-dataset or domain generalization**: forgetting remains effective when the evaluation distribution shifts.
3. **Deletion-request generalization**: the method handles unseen forget sets, concepts, classes, users, or data slices without re-designing the whole procedure.
4. **Metric generalization**: gains are visible across utility, privacy, and residual-memory metrics rather than one cherry-picked score.

I am especially interested in ideas that expose whether current methods are learning a reusable forgetting rule versus merely memorizing a benchmark-specific edit pattern.

## Background

- **Field**: machine learning security / privacy / trustworthy ML
- **Sub-area**: machine unlearning, robust generalization, transferable model editing, data deletion
- **Key papers I've read**:
  - General machine unlearning baselines such as exact retraining, fine-tuning-based approximate unlearning, and influence-based approximations
  - Evaluation-focused unlearning papers that compare retain/forget tradeoffs
  - Related work on model editing, concept erasure, domain generalization, invariance, and meta-learning
- **What I already tried**:
  - Standard forget/retain objectives on one benchmark
  - Comparing approximate unlearning to retraining on a single architecture
  - Measuring utility drop plus a small set of forgetting metrics
- **What didn't work**:
  - Methods that look good only on one architecture or one forget-set construction
  - Simple loss reweighting that improves one metric while failing transfer
  - Claims of forgetting that collapse under stronger membership-inference or relearning tests

## Constraints

- **Compute**: assume a realistic academic budget, roughly `4x A100` or equivalent and `150-300 GPU-hours`
- **Timeline**: `6-10 weeks` to get to a credible workshop or conference submission draft
- **Target venue**: `ICLR`, `NeurIPS`, `ICML`, or a strong workshop at one of these venues

## What I'm Looking For

- [x] New research direction from scratch
- [x] Improvement on existing method: generalizable unlearning
- [x] Diagnostic study / analysis paper
- [x] Other: benchmark/evaluation protocol ideas that make "generalizable unlearning" measurable and falsifiable

## Domain Knowledge

- I suspect the main bottleneck is **problem formulation and evaluation**, not only optimization.
- Many current methods may succeed by exploiting shortcuts in the forget-set construction or by degrading representations in a way that does not transfer.
- A good idea may involve:
  - invariant or causal views of what should be removed
  - meta-unlearning across many deletion tasks
  - representation-level forgetting objectives that transfer across architectures
  - train-once, adapt-many mechanisms for unseen deletion requests
  - stress tests that separate true forgetting from surface-level output suppression
- Useful neighboring areas:
  - domain generalization
  - invariant risk minimization and distribution shift
  - model editing and concept erasure
  - continual learning and parameter isolation
  - knowledge distillation / teacher-student transfer for forgetting objectives

## Non-Goals

- Purely legal, governance, or policy framing without technical novelty
- LLM-only product features or alignment-only framing unless the idea clearly generalizes to machine unlearning
- A paper that is only "we tuned another forget-vs-retain loss and got a small gain"
- Methods that require full retraining per deletion request unless there is a strong conceptual reason
- Benchmark gaming via weak forgetting metrics

## Existing Results (if any)

- I have baseline retain/forget results on at least one standard setup, but not a convincing cross-setting study.
- I do **not** yet have a principled benchmark for generalization across deletion requests, architectures, or domains.
- Negative result so far: approximate unlearning methods often look competitive in-distribution but become much less convincing under stronger transfer or relearning tests.

## Success Criteria For Idea Discovery

Please optimize for ideas that satisfy most of the following:

1. **Actually novel** relative to recent unlearning and model-editing literature.
2. **Testable within my compute budget**.
3. **Has a crisp core claim** that can be falsified.
4. **Includes a strong evaluation protocol**, not only a method.
5. **Can plausibly yield a top-venue-style contribution**, not just a small engineering tweak.

## Preferred Output Shape

When generating and ranking ideas, prioritize the following buckets:

1. **Method ideas**:
   - examples: meta-unlearning, invariant forgetting objectives, architecture-agnostic forgetting signals, transfer-aware regularizers
2. **Evaluation / benchmark ideas**:
   - examples: held-out deletion-task splits, architecture-transfer benchmarks, stronger residual-memory tests, relearning stress tests
3. **Theory / mechanistic ideas**:
   - examples: what properties make an unlearning rule transferable, when approximate forgetting can generalize, what representation factors should be erased

For each top idea, I want:

- a one-sentence thesis
- what exact gap it addresses
- why it might generalize
- what minimal experiment would quickly kill it or validate it
- the closest existing papers and the expected differentiation

## Seed Directions To Explore

These are not requirements; they are prompts to search around:

- **Task-family view of unlearning**: train over many deletion tasks and learn a policy that generalizes to new forget requests.
- **Representation-space forgetting**: erase transferable latent factors instead of dataset-specific token/class signatures.
- **Counterfactual evaluation**: benchmark whether forgotten information can be recovered by lightweight relearning or transfer probes.
- **Teacher-student unlearning transfer**: distill forgetting behavior from exact retraining or a stronger teacher into a reusable unlearning mechanism.
- **Cross-backbone unlearning signals**: identify architecture-agnostic signatures of successful forgetting.
- **Domain-shift stress tests**: forgetting on source domain, evaluation on shifted target domain.

## What To Avoid In The Final Ideas

- Incremental variants that only change one loss coefficient
- Ideas whose only novelty is combining two standard penalties
- Methods that depend on unrealistic access assumptions without acknowledging it
- Claims of "generalization" that only mean multiple random seeds on one benchmark
