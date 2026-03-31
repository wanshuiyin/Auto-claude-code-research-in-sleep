# Idea Candidates

| # | Idea | Bucket | Novelty | Feasibility | Status |
|---|------|--------|---------|-------------|--------|
| 1 | GURU-Bench: held-out transfer benchmark for unlearning rules | Benchmark | High | High | RECOMMENDED |
| 2 | Cross-model forgetting subspaces | Method | Medium-High | Medium | STRONG METHOD |
| 3 | Transferability theory for unlearning rules | Theory | High | Medium | BACKUP / COMPANION |
| 4 | Oracle-to-operator unlearning | Method | Medium | Medium-Low | HIGH UPSIDE / HIGH RISK |
| 5 | Recoverability-under-shift metric | Evaluation | Medium-High | High | BETTER AS SUBMODULE |

## Active Shortlist

### #1 GURU-Bench
- **Hypothesis**: Current unlearning methods are overfitting fixed protocols, and their ranking will change substantially under held-out architecture, dataset, and deletion-family transfer.
- **Key evidence to look for first**: rank instability of existing methods once evaluated on train/test splits over unlearning environments.
- **Why it is strong**: it matches the brief's claim that formulation and evaluation are the bottleneck.

### #2 Cross-model forgetting subspaces
- **Hypothesis**: forgetting becomes more transferable when the intervention targets aligned latent factors instead of model-specific parameter updates.
- **Key evidence to look for first**: a shared latent erasure rule beats per-model baselines on a held-out architecture.
- **Why it is strong**: it is the cleanest method direction with a real transfer mechanism.

### #3 Transferability theory
- **Hypothesis**: cross-environment stability of forget-relevant subspaces predicts whether an unlearning rule will transfer.
- **Key evidence to look for first**: subspace-stability measures correlate with empirical transfer success.
- **Why it is strong**: it gives a mechanism for why transfer fails, not just another scorecard.

## Recommendation

Choose `#1` if you want the safest high-impact paper.  
Choose `#2` if you want the strongest method paper.  
Choose `#1 + #3` if you want benchmark plus mechanistic depth.
