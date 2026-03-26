# Research Brief: k-space Domain Motion Correction

## Problem Statement

MRI motion artifacts originate from patient movement during k-space sampling. Traditional methods either require additional navigator echoes (increasing scan time) or perform correction in the image domain (losing k-space information). The core challenge is: can we directly estimate and correct motion parameters from k-space data without navigators?

Key limitations of current approaches:
1. Navigator-based methods add 10-25% scan time overhead
2. Image-domain correction cannot recover lost k-space information
3. Existing k-space methods struggle with non-rigid motion
4. Joint estimation of motion and image is computationally expensive

## Background

- **Field**: Medical Image Reconstruction / Signal Processing
- **Sub-area**: k-space sampling, motion parameter estimation, navigator-free correction
- **Key concepts**:
  - k-space sampling trajectories (Cartesian, radial, spiral)
  - Rigid motion model (6 parameters: 3 rotation + 3 translation)
  - Non-rigid motion (respiratory, cardiac)
  - Forward model: k-space data = FT[motion_transform(image)]
- **Related work**:
  - Lustig et al.: Sparse MRI reconstruction
  - Uecker et al.: ESPIRiT calibration
  - Recent deep learning k-space methods (2022-2024)

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / IPMI / MRM

## What I'm Looking For

- [x] New method: end-to-end differentiable k-space motion correction
- [ ] Improvement on existing: [to be identified after lit review]
- [ ] Novel formulation of the inverse problem

## Domain Knowledge

### k-space Motion Physics:

Rigid motion in k-space corresponds to phase modulation:
- Translation → linear phase ramp in k-space
- Rotation → rotation of k-space coordinates

The forward model with motion:
```
y = F{P(θ) * x} + n
```
where:
- y: measured k-space data
- F: Fourier transform
- P(θ): motion transformation with parameters θ
- x: image to reconstruct
- n: noise

### Potential Approaches:

1. **Direct motion parameter regression**: CNN → motion parameters → apply correction
2. **Implicit motion modeling**: Attention mechanisms that learn motion patterns
3. **Differentiable forward model**: Unrolled optimization with learned priors
4. **Multi-shot consistency**: Use redundant k-space sampling for self-calibration

## Non-Goals

- Real-time correction (focus on image quality first)
- New pulse sequence design (software-only solution)
- Multi-coil reconstruction (start with single-coil)

## Existing Results

None yet - this is the initial exploration phase.

## Success Criteria

- Method works without navigator echoes
- Outperforms image-domain correction on retrospective motion
- Validated on public datasets (e.g., fastMRI with simulated motion)

## References to Start With

- "Motion Correction in MRI" - surveys
- "Deep Learning for k-space Motion Correction" - recent works
- "End-to-End Variational Networks for Accelerated MRI Reconstruction"
