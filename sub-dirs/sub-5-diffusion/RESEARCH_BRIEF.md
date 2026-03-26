# Research Brief: Diffusion Models for MRI Motion Correction

## Problem Statement

Diffusion models have achieved state-of-the-art results in image generation and restoration tasks. Can we leverage their powerful generative priors for high-quality MRI motion artifact correction?

Key opportunities:
1. **Strong priors**: Diffusion models learn complex data distributions
2. **Conditional generation**: Can guide sampling toward artifact-free images
3. **Uncertainty quantification**: Multiple samples show solution diversity
4. **Score-based formulation**: Natural fit for inverse problems

Challenges:
1. Computational cost (iterative sampling)
2. Need domain-specific conditioning
3. Risk of generating anatomically incorrect content
4. Training stability with medical data

## Background

- **Field**: Generative Models / Score-Based Models
- **Sub-area**: Diffusion models, conditional generation, inverse problems
- **Key concepts**:
  - Forward diffusion: gradually add noise
  - Reverse process: learn to denoise
  - Score matching: ∇_x log p(x)
  - Classifier-free guidance
  - Posterior sampling for inverse problems
- **Related work**:
  - DDPM, DDIM for image generation
  - Diffusion models for MRI reconstruction
  - Score-based generative models
  - Latent diffusion models

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
  - Note: Diffusion models are compute-intensive; may need efficiency optimizations
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / IPMI / TMI

## What I'm Looking For

- [x] New method: diffusion-based motion correction
- [ ] Faster sampling strategies (not 1000 steps)
- [ ] Anatomically-constrained generation

## Domain Knowledge

### Diffusion Model Basics:

Forward process: q(x_t | x_{t-1}) = N(x_t; √(1-β_t)x_{t-1}, β_t I)

Reverse process: p_θ(x_{t-1} | x_t) = N(x_{t-1}; μ_θ(x_t, t), Σ_θ(x_t, t))

For inverse problems: condition on corrupted measurement y

### Approaches for Motion Correction:

1. **Direct conditioning**:
   - Train conditional diffusion: p(x_clean | x_corrupted)
   - Simple but may hallucinate

2. **Posterior sampling**:
   - Start from random noise
   - At each step, enforce data consistency
   - Gradient guidance toward measured data

3. **Latent diffusion**:
   - Encode to latent space (faster)
   - Apply diffusion in latent space
   - Decode to image

4. **Score-based formulation**:
   - View motion correction as MAP estimation
   - Use score model for prior
   - Data fidelity term from forward model

### Efficiency Considerations:

- DDIM: deterministic sampling, fewer steps
- Progressive distillation: student model learns few-step generation
- Latent space: lower dimensionality
- Model compression: knowledge distillation

## Non-Goals

- Unconditional generation (need conditioning on corrupted image)
- 1000-step sampling (aim for <50 steps clinically viable)
- Pure simulation training (validate on real data)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Quality matches or exceeds GAN-based methods
- Sampling in <50 steps (or show quality/speed tradeoff)
- No anatomical hallucination (validated by radiologists)
- Better uncertainty quantification than deterministic methods
