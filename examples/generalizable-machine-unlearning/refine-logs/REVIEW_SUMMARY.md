# Review Summary

**Date**: 2026-03-31  
**Mode**: local critical review

## Round 1: Main Criticisms

1. The original theory idea was too broad.
   - It tried to explain multiple kinds of transfer at once without locking onto the user's intended notion of distribution shift.

2. The proposal lacked a measurable object.
   - A theorem without an operational predictor would read as stylized and non-actionable.

3. The paper risked becoming a benchmark paper accidentally.
   - Covering every transfer axis equally would dilute the core contribution.

4. The story had no constructive implication.
   - Reviewers would ask what the theory changes in practice.

## Revisions Applied

1. Narrowed the theorem to **path-oblivious local unlearning rules**.
2. Introduced three concrete structural quantities:
   - Forget Subspace Stability
   - Retain-Forget Entanglement
   - Linearization Residual
3. Added a practical shift-robustness diagnostic for prediction and deployment decisions.
4. Added a minimal source-projector constructive sanity check.
5. Focused the main empirical story on compact vision settings, with any LM result moved to appendix.

## Final Assessment

- **Score**: 9/10
- **Verdict**: READY

## Why It Is Now Stronger

- The paper has one dominant claim instead of a vague multi-claim story.
- The theorem is paired with a falsifiable OOD predictor.
- The experimental plan is compact and directly tied to the claim.
- The work explains a real pain point in current unlearning literature rather than proposing another optimizer.
