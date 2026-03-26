# MRI运动伪影校正 - 扩散模型运动估计

## ✅ Agent-5 (Diffusion Models) - Phase 1 Complete

### Key Findings

| Discovery | Significance |
|-----------|--------------|
| **Res-MoCoDiff (2025)** | First diffusion model specifically for MRI motion correction - **only 4 steps**, 275x speedup |
| **Efficiency feasible** | DDIM (20-50 steps), DPM-Solver++ (15-20 steps), Consistency Models (1-4 steps) |
| **Physics-guided trend** | SPIRiT-Diffusion, Heat-Diffusion - k-space self-consistency driven |
| **Major gap** | Very few motion-specific diffusion architectures (only Res-MoCoDiff) |

### Critical Gaps Identified

1. **Motion-specific architectures** - Res-MoCoDiff is the only one
2. **Real-time clinical deployment** - Need <10 steps with quality preservation
3. **Anatomical correctness validation** - Risk of hallucination in generative models
4. **Physics-guided motion estimation** - Joint parameter estimation + reconstruction
5. **Self-supervised/blind settings** - Reduce paired data dependency

### Generated Ideas

1. **Res-MoCoDiff + Consistency Models** → single-step motion correction
2. **Physics-guided joint motion estimation + diffusion reconstruction**
3. **Anatomically-constrained diffusion** to prevent hallucination
4. **Self-supervised motion correction** without paired data
