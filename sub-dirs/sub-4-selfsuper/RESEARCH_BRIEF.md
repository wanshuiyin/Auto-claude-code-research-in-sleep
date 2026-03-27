# Research Brief: Self-Supervised MRI Motion Correction

## Problem Statement

Supervised learning for motion correction requires paired training data (corrupted + clean images), which is difficult to obtain clinically. Simulated motion may not match real patient motion patterns.

Can we develop methods that learn from unpaired data or single corrupted images, without ground truth?

Key challenges:
1. Ill-posedness: multiple clean images could produce the same artifacts
2. Mode collapse: network learns trivial solutions
3. Evaluation: no ground truth for validation

## Background

- **Field**: Self-supervised Learning / Blind Image Restoration
- **Sub-area**: Unsupervised denoising, blind deconvolution, internal learning
- **Key concepts**:
  - Noise2Noise: learn from noisy pairs
  - Self-supervised losses: rotation prediction, jigsaw, contrastive
  - Internal learning: use patches within same image
  - Cycle consistency
- **Related work**:
  - Noise2Void, Noise2Self
  - Self-supervised MRI reconstruction
  - Zero-shot denoising
  - Blind motion deblurring (natural images)

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / IPMI / TMI

## What I'm Looking For

- [x] New method: self-supervised motion artifact removal
- [ ] Zero-shot approach using only test image
- [ ] Training without clean targets

## Domain Knowledge

### Self-Supervised Strategies:

1. **Internal learning (Noise2Void style)**:
   - Predict center pixel from neighbors
   - Assumes pixel-wise independence
   - Challenge: motion artifacts are highly correlated

2. **Cycle consistency**:
   - Corrupted → Clean → Corrupted' should match original
   - Requires differentiable forward model

3. **Augmentation consistency**:
   - Same image under different augmentations → same clean output
   - Contrastive learning approaches

4. **K-space redundancy**:
   - Use multi-coil or multi-shot redundancy
   - Self-consistency as supervision signal

5. **Statistical priors**:
   - Sparsity in transform domain
   - Low-rank structure in temporal dimension
   - Deep image prior

### Motion-Specific Considerations:

- Motion creates **structured** artifacts (not random noise)
- Spatial correlation is key signature
- Temporal dimension in cine MRI provides redundancy

## Non-Goals

- Fully supervised methods (need paired data)
- Pure simulation-based training
- Methods requiring clean calibration scans

## Existing Results

None yet - initial exploration.

## Success Criteria

- Method trains without ground truth
- Competitive with supervised methods (when evaluated on held-out test)
- Works on real clinical data
- Ablation showing each component's contribution

## Related Papers to Review

- "Noise2Void - Learning Denoising from Single Noisy Images"
- "Self-Supervised Data Undersampling for MRI"
- "Zero-Shot MRI Reconstruction"
