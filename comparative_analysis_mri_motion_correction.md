# Comparative Analysis: MRI Motion Correction Methods

## Executive Summary

This analysis compares four state-of-the-art MRI motion correction approaches: **PI-MoCoNet** (physics-informed), **Res-MoCoDiff** (diffusion-based), **IM-MoCo** (self-supervised INR), and **SISMIK** (k-space deep learning). Each method represents a distinct paradigm with unique strengths, limitations, and potential for hybrid fusion.

---

## 1. COMPARATIVE TABLE

| **Dimension** | **PI-MoCoNet** | **Res-MoCoDiff** | **IM-MoCo** | **SISMIK** |
|---------------|----------------|------------------|-------------|------------|
| **Paper** | arXiv:2502.09296 (Feb 2025) | arXiv:2505.03498 (May 2025) | arXiv:2407.02974 (MICCAI 2024) | arXiv:2312.13220 (TMI 2024) |
| **Authors** | Safari et al., Emory | Safari et al., Emory | Al-Haj Hemidi et al., Lübeck | Dabrowski et al., Geneva |
| **Code** | [github.com/mosaf/PI-MoCoNet](https://github.com/mosaf/PI-MoCoNet) | Not public yet | [github.com/multimodallearning/MICCAI24_IMMoCo](https://github.com/multimodallearning/MICCAI24_IMMoCo) | [gitlab.unige.ch/Oscar.Dabrowski/sismik_mri/](https://gitlab.unige.ch/Oscar.Dabrowski/sismik_mri/) |

### 1.1 Architecture Comparison

| **Aspect** | **PI-MoCoNet** | **Res-MoCoDiff** | **IM-MoCo** | **SISMIK** |
|------------|----------------|------------------|-------------|------------|
| **Core Design** | Dual-network: Detection + Correction | Residual-guided diffusion | Dual INR: Image + Motion | DL estimation + Model-based correction |
| **Backbone** | U-Net (Det) + Swin-UNet (Corr) | U-Net with Swin Transformer blocks | Hash-grid INR + MLP | Custom CNN (motion estimator) |
| **Attention** | Swin Transformer blocks | Swin Transformer blocks | None (implicit via INR) | Channel/Spatial attention |
| **Input Domain** | Image + k-space hybrid | Image domain | k-space only | k-space only |
| **Output Domain** | Image domain | Image domain | Image domain | k-space → Image via NUFFT |
| **Multi-scale** | Yes (U-Net skip connections) | Yes (hierarchical Swin) | Yes (hash grid levels) | Limited (single-scale) |
| **Parameters** | ~10-50M (estimated) | ~30-50M (estimated) | ~1-5M (lightweight INR) | ~5-20M (estimated) |

### 1.2 Supervision Type & Data Requirements

| **Aspect** | **PI-MoCoNet** | **Res-MoCoDiff** | **IM-MoCo** | **SISMIK** |
|------------|----------------|------------------|-------------|------------|
| **Supervision** | Supervised (end-to-end) | Supervised (end-to-end) | Self-supervised (instance-wise) | Supervised (motion estimation only) |
| **Training Data** | Paired corrupted/clean (simulated) | Paired corrupted/clean (simulated) | Pre-trained detector + instance optimization | 600k simulations from 43 subjects |
| **Ground Truth** | Required for training | Required for training | Not required at inference | Required for motion estimator training |
| **Test-time Adaptation** | No | No | Yes (per-instance optimization) | No |
| **Data Efficiency** | Medium-High | Medium | Very High (test-time trained) | High (separates estimation/correction) |

### 1.3 Computational Efficiency

| **Metric** | **PI-MoCoNet** | **Res-MoCoDiff** | **IM-MoCo** | **SISMIK** |
|------------|----------------|------------------|-------------|------------|
| **Inference Time** | ~0.1-0.5s per slice (estimated) | **0.37s per 2 slices** | 30-60s per scan (instance optimization) | ~1-5s per scan (fast) |
| **Diffusion Steps** | N/A | **4 steps** (vs. 100+ conventional) | N/A | N/A |
| **GPU Memory** | ~4-8 GB | ~4-8 GB | ~2-4 GB | ~2-4 GB |
| **Training Time** | Hours-days | Hours-days | Minutes (instance opt) | Hours-days (motion estimator) |
| **Real-time Capable** | Potentially | **Yes** | No | Yes |

### 1.4 Performance Metrics (from Papers)

#### Minor Motion
| **Method** | **PSNR (dB)** | **SSIM** | **NMSE (%)** |
|------------|---------------|----------|--------------|
| PI-MoCoNet | **45.95** | **1.00** | **0.04** |
| Res-MoCoDiff | **41.91 ± 2.94** | Highest | Lowest |
| IM-MoCo | **40.06** | **98.25%** | - |
| SISMIK | ~38-40 (estimated) | ~0.95 | ~0.1 |

#### Heavy Motion
| **Method** | **PSNR (dB)** | **SSIM** | **Clinical Impact** |
|------------|---------------|----------|---------------------|
| PI-MoCoNet | 36.01 | 0.97 | Good |
| Res-MoCoDiff | ~35-38 | High | Good |
| IM-MoCo | **33.06** | **92.77%** | **+1.5% classification accuracy** |
| SISMIK | ~32-35 | ~0.90 | Moderate |

### 1.5 Strengths Summary

| **Method** | **Key Strengths** |
|------------|-------------------|
| **PI-MoCoNet** | • Physics-informed: data consistency loss enforces k-space fidelity<br>• Dual-domain: leverages both image and k-space information<br>• No explicit motion parameter estimation → reduced hallucination risk<br>• Swin Transformer captures long-range dependencies |
| **Res-MoCoDiff** | • **Ultra-fast diffusion**: 4 steps vs. 100+ in conventional DDPMs<br>• Residual shifting avoids restrictive Gaussian prior<br>• Superior artifact removal across all severity levels<br>• Highest SSIM and lowest NMSE in benchmarks |
| **IM-MoCo** | • **Fully self-supervised**: no training data for correction needed<br>• Instance-wise optimization adapts to specific corruption<br>• INR provides implicit regularization/prior<br>• Improves downstream clinical tasks (+1.5% accuracy) |
| **SISMIK** | | • Separates motion estimation from correction → no hallucination<br>• Model-based correction ensures physical validity<br>• Works without motion-free reference<br>• Robust to high-frequency motion |

### 1.6 Limitations Summary

| **Method** | **Key Limitations** |
|------------|---------------------|
| **PI-MoCoNet** | • Requires supervised training with paired data<br>• Fixed after training → no test-time adaptation<br>• Limited to rigid motion (as reported)<br>• Higher memory/compute than model-based methods |
| **Res-MoCoDiff** | • Still requires paired training data<br>• Diffusion can hallucinate fine details<br>• Residual shifting requires corrupted reference<br>• Limited interpretability of correction process |
| **IM-MoCo** | • **Slow inference**: requires per-instance optimization<br>• Pre-trained detector still needs supervised training<br>• INR may struggle with complex motion patterns<br>• Requires careful hyperparameter tuning per scan |
| **SISMIK** | • Limited to 2D Spin-Echo, in-plane rigid motion<br>• Motion estimator quality limits correction accuracy<br>• NUFFT reconstruction adds computational cost<br>• Less effective for non-rigid or through-plane motion |

---

## 2. DETAILED ANALYSIS

### 2.1 PI-MoCoNet (Physics-Informed)

**Core Innovation**: Integrates physics constraints (data consistency loss) directly into the learning objective, ensuring k-space fidelity without explicit motion parameter estimation.

**Architecture Details**:
- Motion Detection Network (Dθ): Standard U-Net with spatial averaging along frequency encoding direction
- Motion Correction Network (Cν): U-Net with Swin Transformer blocks replacing standard attention
- Loss: L1 + LPIPS + Ldc (data consistency: ||M⊙(F(y) - F(ŷ))||²)

**Why It Works**: The data consistency loss acts as a physics-informed regularizer, preventing the network from hallucinating structures that violate the forward MRI acquisition model.

**Fusion Potential**: **HIGH** - The physics-informed loss can be integrated into any other method.

---

### 2.2 Res-MoCoDiff (Residual-Guided Diffusion)

**Core Innovation**: Residual error shifting during forward diffusion avoids the Gaussian prior assumption, enabling ultra-fast sampling (4 steps vs. 100+).

**Architecture Details**:
- Backbone: U-Net with Swin Transformer blocks
- Forward process: p(x_N) ~ N(x; y, γ²I) where y is corrupted image
- Loss: Combined L1 + L2 for sharpness and pixel accuracy

**Why It Works**: By shifting the noise distribution to match the corrupted data distribution, the reverse process only needs to remove residual artifacts, not generate the full image.

**Fusion Potential**: **MEDIUM** - Diffusion backbone can be combined with physics constraints or INRs, but may conflict with instance-wise optimization.

---

### 2.3 IM-MoCo (Self-Supervised INR)

**Core Innovation**: Instance-wise optimization using dual INRs (Image + Motion) enables test-time training without paired data.

**Architecture Details**:
- kLD-Net: Pre-trained CNN detects corrupted k-space lines → motion mask M
- Image INR: f_θ(x,y,z) → intensity, provides implicit prior
- Motion INR: g_φ(t) → (tx, ty, θz), models motion trajectory
- Loss: ||M⊙(k_measured - k_predicted)||²

**Why It Works**: The INR acts as a strong implicit prior for natural images, and the data consistency loss ensures the reconstruction matches the measured k-space data.

**Fusion Potential**: **HIGH** - Instance-wise optimization can complement any pre-trained model.

---

### 2.4 SISMIK (k-Space Deep Learning)

**Core Innovation**: Separates motion parameter estimation (DL) from motion correction (model-based NUFFT), avoiding hallucinations.

**Architecture Details**:
- Motion Estimator: CNN predicts motion parameters from k-space features
- Motion Correction: NUFFT-based model reconstruction
- Quality Metric: Novel k-space metric for detecting corrupted lines

**Why It Works**: By keeping the correction physics-based, the method ensures reconstructed images are physically plausible, not neural network hallucinations.

**Fusion Potential**: **HIGH** - The separation of estimation/correction can be applied to any method.

---

## 3. HYBRID METHOD DESIGN PROPOSALS

### 3.1 Fusion Strategy Matrix

| **Fusion** | **Components** | **Novelty** | **Feasibility** | **Expected Gain** |
|------------|----------------|-------------|-----------------|-------------------|
| **π-MoCo** | PI-MoCoNet + IM-MoCo | Physics + Self-supervision | HIGH | +2-3 dB PSNR, no training data |
| **Res-π** | Res-MoCoDiff + PI physics loss | Fast diffusion + physics | MEDIUM | Faster + more accurate |
| **SISMIK-INR** | SISMIK + IM-MoCo INR | Separation + instance opt | HIGH | Better generalization |
| **Diff-SISMIK** | Res-MoCoDiff + SISMIK correction | DL generation + physics rec | MEDIUM | Avoid hallucinations |
| **Universal** | All four combined | Ultimate hybrid | MEDIUM | Best of all worlds |

---

### 3.2 Proposed Hybrid: π-MoCo (Physics-Informed Motion-Correcting Implicit Neural Representations)

**Concept**: Combine PI-MoCoNet's physics-informed dual-domain approach with IM-MoCo's self-supervised instance-wise optimization.

**Architecture**:
```
Input: Corrupted k-space k_corrupted
       ↓
[Optional] Pre-trained PI-MoCoNet Detection Network → Initial motion mask M_init
       ↓
Dual INR:
  - Image INR f_θ: (x,y,z) → intensity (SIREN or hash-grid)
  - Motion INR g_φ: (t) → (tx, ty, θz, s) (rigid + scale)
       ↓
Physics-Informed Loss:
  L_total = L_data + α·L_physics + β·L_perceptual

  where L_data = ||M⊙(k_corrupted - F{motion_warp(f_θ, g_φ)})||²
        L_physics = ||(1-M)⊙(k_corrupted - F{f_θ})||²  [unmasked consistency]
        L_perceptual = LPIPS(f_θ, PI-MoCoNet_output) [optional warm start]
```

**Training Strategy**:
1. **Warm Start**: Use PI-MoCoNet (frozen) to provide initial estimates, reducing INR optimization time
2. **Instance Optimization**: 100-500 iterations per scan (minutes instead of hours)
3. **Meta-Learning**: Use Model-Agnostic Meta-Learning (MAML) to learn good INR initialization

**Expected Advantages**:
- No paired training data required
- Test-time adaptation to specific motion patterns
- Physics constraints prevent hallucinations
- Faster convergence with PI warm start

---

### 3.3 Proposed Hybrid: Res-SISMIK (Residual Diffusion with Model-Based Correction)

**Concept**: Use Res-MoCoDiff for fast initial correction, followed by SISMIK's model-based refinement.

**Architecture**:
```
Input: Motion-corrupted image y
       ↓
Res-MoCoDiff (4-step diffusion)
  → Fast initial correction: ŷ_0
       ↓
Motion Estimation (lightweight CNN)
  → Estimate motion parameters θ from residual: r = y - ŷ_0
       ↓
Model-Based Correction (NUFFT)
  → Final reconstruction: x_final = NUFFT(k_corrupted, θ)
       ↓
Output: Physics-validated motion-corrected image
```

**Key Insight**: Res-MoCoDiff provides excellent initial artifact removal, but diffusion may hallucinate. The subsequent model-based step ensures physical validity.

**Expected Advantages**:
- 0.37s initial correction (Res-MoCoDiff speed)
- No hallucinations (SISMIK guarantee)
- Works for arbitrary motion patterns

---

### 3.4 Proposed Hybrid: Universal Motion Corrector (UMC)

**Concept**: Ensemble all four methods with learned weighting.

**Architecture**:
```
Input: k_corrupted, y_corrupted
       ↓
Parallel Branches:
  ├─ PI-MoCoNet → ŷ_PI (physics-informed)
  ├─ Res-MoCoDiff → ŷ_Res (fast diffusion)
  ├─ IM-MoCo (optimized) → ŷ_IM (self-supervised)
  └─ SISMIK → ŷ_SIS (model-based)
       ↓
Adaptive Fusion Network:
  - Lightweight CNN predicts weights w_PI, w_Res, w_IM, w_SIS
  - Weights sum to 1
  - Conditioned on: motion severity, anatomy type, SNR
       ↓
Output: ŷ_final = Σ w_i · ŷ_i
```

**Training**:
- Fusion network trained with L1 + SSIM loss
- Base methods can be frozen (efficient) or fine-tuned (optimal)

**Expected Advantages**:
- Combines all strengths
- Adapts to different motion types
- Robust to individual method failures

---

## 4. IMPLEMENTATION ROADMAP

### Phase 1: Component Validation (Week 1-2)
- Reproduce each method on fastMRI subset
- Establish baseline metrics
- Identify implementation gaps

### Phase 2: Hybrid Development (Week 3-6)
1. **π-MoCo** (Priority 1)
   - Integrate PI-MoCoNet detection with IM-MoCo framework
   - Add physics-informed loss to INR optimization
   - Test on fastMRI with simulated motion

2. **Res-SISMIK** (Priority 2)
   - Connect Res-MoCoDiff output to motion estimator
   - Implement NUFFT refinement pipeline
   - Validate on MR-ART dataset

### Phase 3: Fusion & Evaluation (Week 7-10)
- Implement adaptive fusion strategies
- Comprehensive evaluation across:
  - Motion types (rigid, non-rigid, through-plane)
  - Severity levels (minor, moderate, heavy)
  - Anatomies (brain, cardiac, abdominal)
- Clinical validation (downstream task performance)

### Phase 4: Optimization (Week 11-12)
- Real-time optimization
- Memory-efficient implementation
- 4x4090 deployment preparation

---

## 5. KEY RESEARCH QUESTIONS

1. **Physics vs. Data**: Can physics-informed constraints compensate for lack of training data in self-supervised settings?

2. **Speed vs. Accuracy**: Is there a Pareto frontier combining Res-MoCoDiff's speed with IM-MoCo's self-supervision?

3. **Hallucination Prevention**: Does the SISMIK separation strategy generalize to diffusion-based methods?

4. **Instance Adaptation**: Can meta-learning reduce IM-MoCo's optimization time from minutes to seconds?

5. **Universal Fusion**: Can a learned fusion network outperform the best individual method across all scenarios?

---

## 6. REFERENCES

1. Safari et al., "A Physics-Informed Deep Learning Model for MRI Brain Motion Correction," arXiv:2502.09296, 2025.
2. Safari et al., "Res-MoCoDiff: Residual-guided diffusion models for motion artifact correction in brain MRI," arXiv:2505.03498, 2025.
3. Al-Haj Hemidi et al., "IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Implicit Neural Representations," MICCAI 2024.
4. Dabrowski et al., "SISMIK for brain MRI: Deep-learning-based motion estimation and model-based motion correction in k-space," IEEE TMI 2024.

---

*Generated: 2026-03-26*
*Analysis Framework: Comparative Methodology Assessment*
