# Findings

> **Cross-stage discovery log.** Records what you learn during experiments — both research insights about your method/claims and engineering lessons from debugging. Read on every session recovery, so keep entries concise.
>
> **Why this file exists:** Experiments produce discoveries that are critical for future decisions but don't belong in formal experiment reports. Without a central log, these get lost between sessions — and the next session repeats the same mistakes or misses important signals.

---

# Research Findings

> Method-level insights: what works, what doesn't, and why. These directly inform your claims, experiment design, and paper narrative.

## [YYYY-MM-DD] Topic
- Finding
- Evidence (wandb run, metric, dataset)

## [YYYY-MM-DD] Example: Attention module ineffective on small datasets
- Our proposed attention mechanism shows no improvement on CIFAR-10 (acc 93.1 vs baseline 93.0) but +2.3% on ImageNet
- Hypothesis: the module needs sufficient spatial diversity to capture meaningful patterns; small-resolution inputs don't provide this
- Implication: restrict claims to medium/large-scale datasets

## [YYYY-MM-DD] Example: Loss combination causes gradient explosion
- Combining L_contrastive + L_distill with equal weight → gradient norm >1000 after epoch 5
- Root cause: L_contrastive scale is ~10x larger than L_distill; needs rebalancing or gradient clipping
- Decision: weight ratio 0.1:1.0, gradient norm stable at ~5.0 after fix

## [YYYY-MM-DD] Example: Key decision — dropped multi-scale approach
- Multi-scale variant adds 40% compute but only +0.3% accuracy over single-scale
- Not worth the complexity; claim reframed around efficiency rather than raw performance

---

# Engineering Findings

> Infrastructure, environment, and debugging lessons. Prevents re-debugging the same issues in future sessions.

## [YYYY-MM-DD] Topic
- Problem and root cause
- Fix applied

## [YYYY-MM-DD] Example: OOM with gradient accumulation
- OOM on batch_size=32 with 4x GPU — gradient accumulation was doubling peak memory
- Fix: enabled gradient checkpointing; batch_size=32 now fits in 24GB

## [YYYY-MM-DD] Example: Baseline reproduction gap
- Paper reports 95.5 on dataset-X; we get 93.2 with their official code
- Root cause: different data preprocessing (center crop vs resize-then-crop)
- Decision: use our preprocessing for fair comparison, document in paper

## [YYYY-MM-DD] Example: WandB logging breaks DDP
- wandb.log() inside DDP forward pass causes hanging on multi-GPU
- Fix: wrap in `if dist.get_rank() == 0` guard
