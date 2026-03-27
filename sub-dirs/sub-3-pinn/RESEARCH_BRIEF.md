# Research Brief: Physics-Informed Neural Networks for MRI Motion Correction

## Problem Statement

Current deep learning methods for MRI motion correction are often "black boxes" that learn statistical patterns without enforcing physical constraints. This can lead to:
1. Physically implausible solutions
2. Poor generalization to unseen motion patterns
3. Lack of interpretability for clinical users

Can we embed MRI physics (Fourier transform, coil sensitivities, motion models) directly into neural networks for physically consistent motion correction?

## Background

- **Field**: Scientific Machine Learning / Physics-Informed ML
- **Sub-area**: PINN, inverse problems, MRI physics
- **Key concepts**:
  - MRI forward model: y = F{S · P(θ)x}
  - Physics constraints: data consistency, signal equations
  - Neural operators for PDE solving
  - Differentiable physics layers
- **Related work**:
  - PINNs for imaging inverse problems
  - Variational networks for MRI
  - Deep unfolding methods
  - Physics-driven data augmentation

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / MRM / Inverse Problems

## What I'm Looking For

- [x] New method: physics-informed motion correction architecture
- [ ] Improved interpretability over black-box methods
- [ ] Better generalization via physical constraints

## Domain Knowledge

### MRI Forward Model:

```
y_i = F{S_i · P(θ) · x} + n_i
```

where for coil i:
- y_i: measured k-space
- F: 2D/3D Fourier transform
- S_i: coil sensitivity map
- P(θ): motion transformation with parameters θ
- x: true image
- n_i: noise

### PINN Approaches for MRI:

1. **Hard constraints**: Network architecture enforces physics
   - Output projected onto data manifold
   - Fourier consistency layers

2. **Soft constraints**: Physics as regularization
   - Data consistency loss term
   - Physics-guided training

3. **Hybrid**: Learned components + physics modules
   - Learned prior + physics-based forward model
   - Unrolled optimization with learned updates

### Potential Advantages:

- **Interpretability**: Network learns physically meaningful representations
- **Data efficiency**: Physics reduces search space
- **Generalization**: Physical laws hold across datasets
- **Trust**: Clinicians can verify physical plausibility

## Non-Goals

- Ignoring physics entirely (that's standard DL)
- Pure analytical methods (no learned components)
- Coil compression (assume full coil arrays)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Quantitative improvement over physics-agnostic methods
- Demonstrated physical consistency (e.g., k-space data consistency)
- Interpretable intermediate representations
- Ablation showing benefit of physics constraints
