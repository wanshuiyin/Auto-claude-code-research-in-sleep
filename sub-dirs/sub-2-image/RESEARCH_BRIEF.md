# Research Brief: Image Domain Post-Processing Correction

## Problem Statement

After MRI reconstruction, motion artifacts manifest as ghosting, blurring, and streaking in the image. Can we train a deep network to "clean up" these artifacts as a post-processing step, decoupled from the reconstruction pipeline?

Advantages of image-domain approach:
- Compatible with any reconstruction method
- Can be applied retrospectively to existing data
- Lower computational complexity than joint reconstruction
- Easier clinical deployment

Challenges:
- Lost information cannot be truly recovered
- Risk of hallucinating anatomically incorrect structures
- Need to preserve true anatomical details while removing artifacts

## Background

- **Field**: Medical Image Restoration / Computer Vision
- **Sub-area**: Image denoising, artifact removal, GANs, diffusion models
- **Key concepts**:
  - Motion artifact patterns (ghosting from periodic motion)
  - Perceptual loss vs pixel-wise loss
  - Adversarial training for realistic output
  - Uncertainty quantification
- **Related work**:
  - CNN-based denoising (DnCNN, RED-CNN)
  - GANs for medical image synthesis
  - Recent diffusion-based restoration

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / TMI / MRM

## What I'm Looking For

- [x] New method: lightweight post-processing network
- [ ] Improvement on existing UNet/denoising architectures
- [ ] Novel loss functions for artifact removal

## Domain Knowledge

### Motion Artifact Patterns:

1. **Rigid motion**: Global blurring, ghost replicas
2. **Respiratory motion**: Blurring in phase-encode direction
3. **Cardiac motion**: Time-varying artifacts in cardiac MRI
4. **Bulk motion**: Sudden translations/rotations

### Network Design Considerations:

1. **Multi-scale processing**: Artifacts occur at different scales
2. **Residual learning**: Network learns artifact rather than clean image
3. **Attention mechanisms**: Focus on artifact regions
4. **Adversarial component**: Ensure perceptual quality

### Loss Function Options:

- L1/L2: Pixel-wise accuracy
- Perceptual (VGG): Feature-space similarity
- Adversarial: Realism
- SSIM: Structural similarity
- Fourier: Frequency-domain correctness

## Non-Goals

- k-space manipulation (purely image-domain)
- Real-time processing (offline correction OK)
- Training data synthesis (assume paired data available)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Significant improvement in quantitative metrics (SSIM, PSNR)
- No anatomical hallucination
- Faster than re-scanning the patient
- Works across different MRI contrasts (T1, T2, FLAIR)
