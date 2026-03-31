# Refinement Report

**Date**: 2026-03-31  
**Selected Idea**: distribution-shift robustness theory for machine unlearning

## Round 0

- Starting point: "derive a theory of why unlearning rules transfer or fail"
- Problem: promising, but too abstract to survive review without a measurable prediction target

## Round 1

- Added explicit problem anchor around unlearning under source-to-target distribution shift
- Identified closest prior boundary:
  - FT-failure theory explains within-environment hidden retention
  - ILU uses invariance as a method prior
  - MUSE / MU-Bench improve evaluation breadth but not a theory of unlearning under distribution shift
- Main issue found: no concrete object linking theory to experiments

## Round 2

- Introduced the transfer object: path-oblivious local unlearning rules under shift
- Introduced structural variables:
  - Forget Subspace Stability
  - Retain-Forget Entanglement
  - Linearization Residual
- Defined a practical prediction target: OOD unlearning gap against oracle retraining

## Round 3

- Added a shift-robustness index
- Added a choose/abstain deployment policy so the paper has clear practical value
- Reduced benchmark sprawl by making vision the primary setting and LM only optional appendix

## Final Output

- Proposal is now focused on OOD unlearning, falsifiable, and executable within the stated budget
- Dominant contribution remains theory plus diagnostic
- Supporting contribution is intentionally lightweight
