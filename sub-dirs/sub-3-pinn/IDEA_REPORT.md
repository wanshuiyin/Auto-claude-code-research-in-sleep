# MRI运动伪影校正 - 物理引导联合重建 (PINN)

## 📚 Phase 1 Complete: Literature Survey

### State-of-the-Art Methods (2024-2025)

| Method | Year | Key Innovation | Results |
|--------|------|----------------|---------|
| **PI-MoCoNet** | 2025 | Physics-informed losses (k-space DC + perceptual) | 34→46 dB PSNR on IXI |
| **PHIMO** | 2024 | Self-supervised motion detection via signal model physics | 40% scan time reduction |
| **Motion-Informed MoDL** | 2024 | Motion fields embedded in forward operator | Cine cardiac MRI |

### Key Technical Insight

The MRI forward model with motion is: **y = M·F(S·W(φ)·x) + n**

State-of-the-art approaches **unroll iterative optimization** into neural networks, alternating:
1. **Data Consistency blocks** (physics): Enforce y ≈ E(φ)x using CG or gradient descent
2. **CNN Regularization blocks** (learning): Denoise and restore anatomy

### Critical Finding

Ablation studies show physics-informed losses provide **~1 dB PSNR improvement** over pure data-driven approaches. k-space data consistency is essential.

### Open Opportunities

1. **Joint optimization**: Simultaneous motion estimation + reconstruction
2. **Diffusion models**: Physics-guided generative reconstruction with uncertainty
3. **Foundation models**: Pre-trained across MRI protocols
4. **Fully unsupervised**: No ground truth needed

### Key Resources

- **PI-MoCoNet code**: https://github.com/mosaf/PI-MoCoNet.git
- **PHIMO code**: https://github.com/HannahEichhorn/PHIMO
- **Datasets**: IXI, MR-ART, fastMRI
