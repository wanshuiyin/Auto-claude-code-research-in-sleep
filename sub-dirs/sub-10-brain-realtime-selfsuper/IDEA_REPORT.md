# Sub-10: Self-Supervised Real-Time Brain Motion Correction with Amortized Estimation

## 🧬 Synthesis Direction Overview

This direction **synthesizes three research threads**:
| Thread | Source | Key Insight |
|--------|--------|-------------|
| **Self-supervised learning** | Sub-4 | IM-MoCo shows instance-wise INR eliminates training data dependency |
| **Real-time/amortized inference** | Sub-8 | MC-Net achieves 40ms inference vs. minutes of iterative methods |
| **Brain-specific constraints** | Sub-7 | Rigid-body 6 DOF significantly simplifies the problem space |

**Core Hypothesis**: Can we achieve **real-time brain motion correction** (amortized inference) while maintaining the **self-supervised advantage** (no training data per scan) by leveraging **brain rigid-body constraints**?

---

## 📚 Literature Synthesis

### 1. Self-Supervised Motion Correction (Foundation from Sub-4)

**IM-MoCo (MICCAI 2024)** [[Paper]](https://arxiv.org/abs/2407.02974) [[Code]](https://github.com/multimodallearning/MICCAI24_IMMoCo)
- **Method**: Motion-guided Implicit Neural Representations (INRs) for instance-wise correction
- **Innovation**: kLD-Net detects motion-affected k-space lines → separate Image-INR and Motion-INR modules
- **Performance**: +5% SSIM, +5 dB PSNR, +14% HaarPSI over SOTA reconstruction
- **Limitation**: Requires per-scan optimization (~minutes) — NOT real-time

**Moner (2024/2025)** [[Paper]](https://arxiv.org/abs/2409.16921)
- **Method**: Unsupervised INR for radial MRI with quasi-static motion model
- **Innovation**: Back-projects radial k-space using Fourier-slice theorem
- **Key Point**: Hash encoding for coarse-to-fine motion estimation

**Gap Identified in Sub-4**: "Amortized INR-based motion correction (avoid per-scan optimization)"

### 2. Real-Time / Amortized Approaches

**MC-Net (2024)** [[Paper]](https://www.mdpi.com/1999-4893/17/5/215)
- **Speed**: 40ms per image with GPU
- **Architecture**: Modified U-Net with hybrid loss (L1 + TV)
- **Trade-off**: Requires pre-training on large datasets — NOT self-supervised

**UniMo (2024)** [[Paper]](https://arxiv.org/pdf/2409.14204v2)
- **Innovation**: Universal motion correction without network retraining
- **Capability**: Multimodal, rigid + non-rigid, real-time inference
- **Significance**: Fully amortized solution generalizing across modalities

**Multi-Head CNN for fMRI (RSNA 2024)**
- **Speed**: 0.02s on GPU per volume
- **Parameters**: Predicts 12 affine parameters
- **Performance**: 82% reduction vs. AFNI traditional methods

### 3. Brain-Specific Rigid Body Constraints

**Key Insight**: Brain MRI assumes **6 degrees of freedom (DOF)** rigid body motion [[NIH PMC]](https://pmc.ncbi.nlm.nih.gov/articles/PMC4930872/):
- 3 translations (x, y, z)
- 3 rotations (pitch, roll, yaw)

**Implications for Motion Correction**:
1. Motion parameter space is bounded (only 6 parameters vs. dense deformation field)
2. Enables compact neural network representation
3. Amortized inference becomes tractable — predict 6 parameters in single forward pass

---

## 💡 Generated Synthesis Ideas

### Idea-1: Amortized Brain Motion INR (ABM-INR) ⭐ **PRIMARY**

**Problem Statement**: IM-MoCo achieves self-supervised correction but requires minutes of per-scan optimization. MC-Net achieves real-time inference but requires large training datasets. Can we combine both advantages?

**Proposed Solution**:
```
┌─────────────────────────────────────────────────────────────┐
│  ABM-INR: Amortized Brain Motion Implicit Neural Rep        │
├─────────────────────────────────────────────────────────────┤
│  Training Phase (Once):                                     │
│    - Meta-learn a network that predicts INR parameters      │
│    - Input: Motion-corrupted k-space lines                  │
│    - Output: 6-DOF rigid motion parameters + image INR      │
│                                                             │
│  Inference Phase (Per Scan, Real-Time):                     │
│    - Single forward pass predicts motion parameters         │
│    - No per-scan optimization needed                        │
│    - ~50ms inference on GPU                                 │
└─────────────────────────────────────────────────────────────┘
```

**Technical Approach**:
1. **Amortized Meta-Learning**: Train a hypernetwork $H_\theta$ that maps corrupted k-space $k_{corr}$ to INR parameters:
   - $\phi_{motion} = H_\theta(k_{corr})$ → 6 rigid body parameters
   - $\phi_{image} = H_\theta(k_{corr})$ → image INR parameters

2. **Self-Supervised Training Loss**: No paired clean/corrupted data needed
   - K-space data consistency: $\mathcal{L}_{DC} = ||\mathcal{F}(f_{INR}(\phi_{image})) - k_{corr} \cdot mask||^2$
   - Motion model constraint (rigid body): $\mathcal{L}_{rigid} = ||T_{\phi_{motion}}(x) - R_{rigid}(x; \phi_{motion})||$
   - Total variation regularization: $\mathcal{L}_{TV}$

3. **Brain-Specific Simplifications**:
   - Only 6 motion parameters to predict (compact output layer)
   - Rigid body constraint reduces motion model complexity
   - Head shape prior can be incorporated

**Novelty**:
- First method to achieve **both** self-supervised (no per-scan training) **AND** real-time (amortized inference) motion correction
- Leverages brain rigid-body constraint to make amortization tractable

**Expected Performance**:
- Inference time: <50ms (comparable to MC-Net)
- Quality: Approach IM-MoCo (+5% SSIM over SOTA)
- Data requirement: Zero per-scan training (fully amortized)

---

### Idea-2: Test-Time Adapted Amortized Motion Correction (TTA-AMoCo)

**Problem**: Amortized networks may fail on out-of-distribution motion patterns not seen during training.

**Solution**: Amortized base network + lightweight test-time adaptation

```
Training: Standard amortized network (like MC-Net)
Inference:
  1. Predict initial correction (single forward pass, ~30ms)
  2. Run 10-20 steps of gradient descent on motion parameters only
  3. Final correction (~100ms total)
```

**Advantage**: Handles distribution shift while maintaining near-real-time speed

---

### Idea-3: Hierarchical Brain Motion Amortization (HBMA)

**Problem**: Brain motion has both gross head movement and subtle physiological motion (cardiac pulsation).

**Solution**: Two-level amortized estimation:
1. **Coarse level**: Amortized network predicts 6-DOF rigid motion (~30ms)
2. **Fine level**: Lightweight INR corrects residual non-rigid cardiac motion (~50ms)

**Total**: ~80ms — still real-time for most clinical applications

---

## 🔬 Comparison with Existing Sub-Directions

| Method | Self-Supervised | Real-Time | Brain-Specific | Novelty |
|--------|-----------------|-----------|----------------|---------|
| IM-MoCo (Sub-4) | ✅ | ❌ (minutes) | ❌ | Instance-wise INR |
| MC-Net (Sub-8) | ❌ (needs training) | ✅ (40ms) | ❌ | Fast CNN inference |
| **ABM-INR (Sub-10)** | ✅ | ✅ (<50ms) | ✅ | **First to combine all three** |

---

## ⚠️ Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Amortization quality gap | High | Test-time adaptation fallback (Idea-2) |
| Rigid body assumption violation | Medium | Add deformable correction as residual (Idea-3) |
| Training data diversity | Medium | Use HCP + simulated motion augmentation |
| Inference speed on CPU | Medium | Optimize for TensorRT/CoreML deployment |

---

## 📋 Feasibility Assessment

| Factor | Assessment | Notes |
|--------|------------|-------|
| **Technical Feasibility** | HIGH | Combines proven techniques (IM-MoCo + MC-Net + rigid constraints) |
| **Computational Cost** | LOW-MED | Single forward pass, compact 6-DOF output |
| **Data Requirements** | LOW | Meta-training on HCP, zero per-scan training |
| **Clinical Impact** | HIGH | Real-time + self-supervised = clinically deployable |
| **Novelty** | HIGH | No existing method combines all three properties |

---

## 🎯 Recommended Next Steps

1. **Prototype ABM-INR** on fastMRI brain data with simulated rigid motion
2. **Baseline comparison**: IM-MoCo (quality upper bound) vs. MC-Net (speed upper bound)
3. **Ablation study**: Test importance of rigid-body constraint vs. general deformable
4. **Clinical validation**: Real patient data with navigator-based ground truth

---

## 📚 Key References

1. Al-Haj Hemidi et al. "IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Implicit Neural Representations." MICCAI 2024. [[arXiv]](https://arxiv.org/abs/2407.02974)
2. Wu et al. "Moner: Motion Correction in Undersampled Radial MRI with Unsupervised Neural Representation." arXiv:2409.16921.
3. Balan et al. "Motion Correction for Brain MRI Using Deep Learning." Algorithms 2024. [[MDPI]](https://www.mdpi.com/1999-4893/17/5/215)
4. UniMo: Universal Motion Correction For Medical Images without Network Retraining. arXiv:2409.14204.
5. Maclaren et al. "Motion correction in MRI of the brain." NIH PMC. [[Link]](https://pmc.ncbi.nlm.nih.gov/articles/PMC4930872/)

---

*Report generated: 2026-03-26*
*Synthesis of: Self-supervised (Sub-4) + Real-time (Sub-8) + Brain-specific (Sub-7)*
