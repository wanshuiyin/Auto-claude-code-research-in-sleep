# Pipeline Summary

**Problem**: current unlearning methods often succeed only in-distribution, and there is no criterion for when their behavior should survive source-to-target distribution shift  
**Final Method Thesis**: local unlearning survives shift when forget-relevant subspaces are stable from source to target and weakly entangled with target retain-relevant directions  
**Final Verdict**: READY  
**Date**: 2026-03-31

## Final Deliverables

- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`

## Contribution Snapshot

- **Dominant contribution**: theory plus diagnostic for unlearning under distribution shift
- **Optional supporting contribution**: minimal source-projector constructive sanity check
- **Explicitly rejected complexity**: no large new unlearning model, no benchmark sprawl, no heavy LLM-centric core

## Must-Prove Claims

- OOD failure of local unlearning is governed by source-target geometry, not just benchmark noise
- Forget Subspace Stability and Retain-Forget Entanglement predict OOD robustness better than direct forget scores
- A choose/abstain policy based on the diagnostic improves deployment decisions

## First Runs to Launch

1. ResNet-18 clean CIFAR-100 `F_random` oracle and local baselines
2. evaluate the same systems on `T_noise`, `T_blur`, and `T_digital`
3. extract diagnostics for the first named source-target shift pairs

## Main Risks

- **Risk**: theorem is too stylized  
  **Mitigation**: controlled synthetic validation plus real-model predictive tests

- **Risk**: correlations are weak  
  **Mitigation**: keep the main claim predictive, not exact, and choose a stable interface layer

## Next Action

- Proceed to implementation of deletion splits, diagnostic extraction, and baseline reproduction
