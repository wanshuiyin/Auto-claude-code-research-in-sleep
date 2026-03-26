# Research Brief: Multi-Scale Hierarchical MRI Motion Correction

## Problem Statement

Motion artifacts in MRI occur at different spatial scales:
- **Global**: Patient bulk motion (rigid, affects entire image)
- **Regional**: Organ-specific motion (non-rigid, local)
- **Fine**: Tissue deformation, pulsatile flow

Current methods often use a single network scale. Can hierarchical multi-scale processing better handle this complexity?

Key hypothesis: Processing motion at the appropriate scale improves both accuracy and efficiency.

## Background

- **Field**: Multi-scale Processing / Hierarchical Networks
- **Sub-area**: U-Net variants, wavelets, Laplacian pyramid, attention
- **Key concepts**:
  - Image pyramid: Gaussian/Laplacian
  - Multi-resolution analysis
  - Coarse-to-fine optimization
  - Scale-space theory
  - Feature pyramid networks
- **Related work**:
  - U-Net and variants
  - Deep Laplacian pyramid networks
  - HRNet for high-resolution
  - Multi-scale attention mechanisms

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / MRM

## What I'm Looking For

- [x] New method: hierarchical motion correction framework
- [ ] Explicit scale assignment for different motion types
- [ ] Computational efficiency gains

## Domain Knowledge

### Scale-Space Decomposition:

1. **Gaussian pyramid**:
   - Coarse levels: global motion estimation
   - Fine levels: detail preservation

2. **Wavelet decomposition**:
   - Low-frequency: bulk motion
   - High-frequency: texture, fine details
   - Motion artifacts appear across bands

3. **Learned multi-scale features**:
   - Network learns scale-specific representations
   - Cross-scale connections for information flow

### Hierarchical Processing Strategies:

1. **Coarse-to-fine correction**:
   - Start with heavily downsampled image
   - Correct global motion
   - Progressively refine at higher resolutions
   - Each level focuses on residual errors

2. **Parallel multi-scale**:
   - Process all scales simultaneously
   - Fuse scale-specific predictions
   - Attention-based scale weighting

3. **Scale-specific experts**:
   - Different sub-networks for different scales
   - Routing mechanism assigns patches to experts
   - Efficient computation allocation

### Motion-Scale Relationship:

| Motion Type | Typical Scale | Frequency Content |
|-------------|---------------|-------------------|
| Bulk head motion | Full FOV | Low frequency |
| Respiratory | Torso region | Low-medium |
| Cardiac | Heart region | Medium |
| Vessel pulsation | Vessels | Medium-high |
| Micro-motion | Local | High frequency |

## Non-Goals

- Single-scale processing (baseline comparison only)
- Fixed decomposition (learned/adaptive preferred)
- Processing all scales equally (computational waste)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Explicit handling of multi-scale motion
- Improved accuracy over single-scale baseline
- Computational efficiency (not 4x slower for 4 scales)
- Clear interpretation of what each scale handles
