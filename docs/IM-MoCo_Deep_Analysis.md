# IM-MoCo Deep Analysis Report

*Self-supervised MRI Motion Correction using Motion-Guided Implicit Neural Representations (MICCAI 2024)*

**arXiv:** [2407.02974](https://arxiv.org/abs/2407.02974)
**Official Code:** [github.com/multimodallearning/MICCAI24_IMMoCo](https://github.com/multimodallearning/MICCAI24_IMMoCo)
**Authors:** Ziad Al-Haj Hemidi, Christian Weihsbach, Mattias P. Heinrich (Universität zu Lübeck)

---

## Executive Summary

IM-MoCo presents a two-stage self-supervised framework for MRI motion correction that achieves state-of-the-art results (+5% SSIM, +5dB PSNR) without requiring ground truth data. The key innovation is coupling two Implicit Neural Representations (INRs)—one for image content, one for motion patterns—with a pre-trained motion detection network (kID-Net).

---

## 1. Problem Statement

### What the Paper Addresses
- **Problem:** Patient motion during MRI scans causes artifacts that degrade image quality and downstream diagnostic tasks
- **Traditional Limitations:**
  - Supervised methods require paired motion-free/motion-corrupted data (rare in clinical practice)
  - Model-based methods are computationally expensive
  - Existing self-supervised methods struggle with heavy motion

### Key Insight
Instead of treating motion correction as image-to-image translation, view it as **joint optimization of content and motion parameters** in a neural representation space.

---

## 2. Architecture Deep Dive

### 2.1 Overall Pipeline (Two-Stage)

```
Stage 1: Motion Detection (Pre-trained kID-Net)
===============================================
Motion-corrupted k-space ──► kID-Net ──► Motion mask S
                                              │
Stage 2: Joint Optimization (Test-time)         │
================================================│
                                                ▼
┌─────────────────────────────────────────────────────────────┐
│                     Coupled INRs                            │
│  ┌──────────────┐          ┌──────────────┐                │
│  │  Image INR   │◄────────►│  Motion INR  │                │
│  │   (INR_Ψ)    │          │  (INR_θ)     │                │
│  └──────┬───────┘          └──────┬───────┘                │
│         │                         │                         │
│    h_I(x)                    h_M(n_M,x)                     │
│         │                         │                         │
│         ▼                         ▼                         │
│    Motion-free              Transformation                 │
│    Image Î                  Grids (T)                      │
│         │                         │                         │
│         └──────────┬──────────────┘                         │
│                    ▼                                        │
│            Forward Model                                    │
│    K̂ = Σ_t S_t ⊙ F{T_t(Î)}                                 │
│                    │                                        │
│                    ▼                                        │
│            DC Loss + Entropy Regularization                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Image INR (INR_Ψ)

**Purpose:** Represents the motion-free image as a continuous function of spatial coordinates.

```python
# Architecture Specification
Image_INR(
  input: spatial coordinates x = (x, y)
  encoding: hash_grid_encoding(h_I(x))  # tiny-cuda-nn

  mlp: Sequential(
    Linear(encoding_dim, 256), ReLU,
    Linear(256, 256), ReLU,
    Linear(256, 256), ReLU,
    Linear(256, 2)  # 2-channel complex output
  )

  output: complex-valued intensity Î(x) = I_real + j·I_imag
)
```

**Key Details:**
- **3 layers** with **256 channels** each
- **ReLU activations**
- **Hash grid encoding** for efficient coordinate representation (replaces large MLPs with lookup table + small MLP)
- Outputs **2-channel complex-valued** image (real + imaginary)

### 2.3 Motion INR (INR_θ)

**Purpose:** Models motion transformations as a function of spatial coordinates and motion group index.

```python
# Architecture Specification
Motion_INR(
  input: [spatial coordinates x, motion group index n_M]
  encoding: hash_grid_encoding(h_M(n_M, x))

  mlp: Sequential(
    Linear(encoding_dim, 64), Tanh,
    Linear(64, 64), Tanh,
    Linear(64, 64), Tanh,
    Linear(64, n_transformations * 2)  # (dx, dy) per motion group
  )

  output: transformation grids T_t for t = 1...n_movements
)
```

**Key Details:**
- **3 layers** with **64 channels** each
- **Tanh activations** (constrains motion magnitude)
- Encodes both **spatial position** and **motion group** n_M ∈ [-1, 1]
- Outputs **n transformation grids** (one per detected movement)

### 2.4 Hash Grid Encoding (tiny-cuda-nn)

**Purpose:** Efficient encoding of high-frequency details without massive MLPs.

```
┌─────────────────────────────────────────────────────┐
│              Hash Grid Encoding                     │
│                                                     │
│   Input Coordinates ──► Multi-resolution Grids    │
│                              │                      │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│   │ Level 1 │  │ Level 2 │  │ Level N │  ...       │
│   │ coarse  │  │ medium  │  │  fine   │            │
│   │ 16³     │  │ 32³     │  │ 512³    │            │
│   └────┬────┘  └────┬────┘  └────┬────┘            │
│        │            │            │                   │
│        └────────────┴────────────┘                   │
│                     │                                │
│              Feature Vectors                        │
│                     │                                │
│              Small MLP (256/64 dims)                │
│                     │                                │
│                Output                               │
└─────────────────────────────────────────────────────┘
```

**Parameters:**
- Uses NVIDIA's tiny-cuda-nn implementation
- Multi-resolution feature grids with hash table lookup
- Replaces need for large coordinate MLPs

### 2.5 kID-Net (k-space Line Detection Network)

**Purpose:** Detects which k-space lines are corrupted by motion.

```python
# Architecture: U-Net with 4 encoder levels
kID_Net(
  input: complex k-space [real, imag] → 2-channel tensor

  encoder: [
    Conv2d(2, 16, 3x3) + BN + ReLU + AvgPool2d,      # Level 1
    Conv2d(16, 32, 3x3) + BN + ReLU + AvgPool2d,     # Level 2
    Conv2d(32, 64, 3x3) + BN + ReLU + AvgPool2d,     # Level 3
    Conv2d(64, 128, 3x3) + BN + ReLU + AvgPool2d,    # Level 4
  ]

  decoder: [standard U-Net skip connections]

  output_head: Conv2d(channels, 1, 1x1)  # binary mask
  output: motion mask Ŝ ∈ {0, 1}^{H×W}
)
```

**Training Configuration:**
```yaml
optimizer: Adam
learning_rate: 1e-4
epochs: 4200
loss: binary_cross_entropy_with_logits
input: motion-corrupted k-space (real/imag concatenated)
output: binary mask (1 = corrupted line, 0 = clean line)
```

**Inference Post-processing:**
1. Apply sigmoid to output
2. Threshold at > 0.5
3. A line is corrupted if **> 20%** of its frequencies are classified as corrupted
4. Group consecutive corrupted lines into **motion groups**

---

## 3. Loss Functions & Training

### 3.1 Data Consistency (DC) Loss

**Purpose:** Ensure reconstructed k-space matches acquired data.

```
L_DC = 1/N Σ_{i=1}^N ||K_acq,i - K̂_i||²₂

where:
  K_acq = acquired (corrupted) k-space
  K̂ = forward_model(Image_INR, Motion_INR, mask_S)
  N = number of sampled k-space points
```

**Forward Model:**
```
K̂ = Σ_{t=1}^T S_t ⊙ F{T_t(Î)}

where:
  Î = Image_INR(h_I(x))           # motion-free image
  T_t = Motion_INR(h_M(n_M,x))_t  # transformation for motion group t
  F{} = Fourier transform
  S_t = motion mask for group t
  ⊙ = element-wise multiplication
```

### 3.2 Gradient Entropy Regularization

**Purpose:** Impose crisp image priors (acts as implicit denoiser).

```
L_reg = -Σ_{i=1}^N ∇Î_i · log(∇Î_i)

where:
  ∇Î = image gradients
  N = number of pixels
```

**Physical Interpretation:** Minimizing gradient entropy encourages sparse gradients → sharper edges, less blur.

### 3.3 Total Loss

```
L_total = L_DC + λ · L_reg
```

**Annealing Schedule:**
```python
lambda_start = 1e-2
lambda_schedule: halved every 10 steps after iteration 100

# Rationale: Strong regularization early (suppress high-freq noise),
#            weaker later (allow fine details)
```

### 3.4 Optimization Hyperparameters

```yaml
# Test-time optimization (per image)
optimizer: Adam
iterations: 200
learning_rate_Image_INR: 1e-2
learning_rate_Motion_INR: 1e-2
encoding: hash_grid (tiny-cuda-nn)
```

---

## 4. Experimental Setup

### 4.1 Dataset

**NYU fastMRI T2-weighted Brain:**
- 300 2D slices from multiple subjects
- Split: 200 train / 50 val / 50 test
- Resolution: 320×320 (typically)

**fastMRI+ Annotations (Classification Task):**
- 1116 slices from 60 subjects
- Pathology labels for downstream evaluation

### 4.2 Motion Simulation

```python
# Motion Parameters
rotation_range: [-10°, +10°]
translation_range: [-10mm, +10mm]

light_motion:
  n_movements: 6-10
  severity: small rotations/translations

heavy_motion:
  n_movements: 16-20
  severity: larger rotations/translations

# Each movement affects a group of consecutive k-space lines
```

### 4.3 Evaluation Metrics

| Metric | Purpose |
|--------|---------|
| SSIM | Structural similarity (perceptual quality) |
| PSNR | Peak signal-to-noise ratio (pixel-level accuracy) |
| HaarPSI | Haar wavelet-based perceptual similarity |
| Classification Accuracy | Downstream task performance |

### 4.4 Baselines

- **Motion Corrupted:** Raw motion-affected images
- **AF (Autofocus):** Model-based motion correction
- **U-Net:** Supervised deep learning approach

---

## 5. Results

### 5.1 Quantitative Results (Light Motion)

| Method | SSIM ↑ | PSNR (dB) ↑ | HaarPSI ↑ |
|--------|--------|-------------|-----------|
| Motion Corrupted | 87.26 ± 4.42 | 28.34 ± 2.97 | 70.48 ± 8.69 |
| Autofocus (AF) | 94.47 ± 2.06 | 33.91 ± 2.37 | 88.49 ± 4.11 |
| U-Net | 91.39 ± 2.14 | 30.58 ± 2.33 | 81.58 ± 4.49 |
| **IM-MoCo** | **98.25 ± 1.25** | **40.06 ± 3.33** | **97.20 ± 4.05** |

**Improvements over SOTA:**
- +3.78% SSIM vs Autofocus
- +6.15 dB PSNR vs Autofocus
- +8.71% HaarPSI vs Autofocus

### 5.2 Quantitative Results (Heavy Motion)

| Method | SSIM ↑ | PSNR (dB) ↑ | HaarPSI ↑ |
|--------|--------|-------------|-----------|
| Motion Corrupted | 78.42 ± 5.73 | 25.17 ± 2.56 | 54.12 ± 9.12 |
| Autofocus (AF) | 87.19 ± 3.51 | 31.02 ± 2.29 | 77.45 ± 5.64 |
| U-Net | 82.15 ± 3.90 | 27.86 ± 2.15 | 67.89 ± 6.03 |
| **IM-MoCo** | **92.77 ± 3.59** | **35.84 ± 2.88** | **89.12 ± 5.22** |

### 5.3 Downstream Classification Task

| Motion Level | Corrupted | U-Net | **IM-MoCo** | Improvement |
|--------------|-----------|-------|-------------|-------------|
| Light | 94.12% | 96.91% | **97.94%** | +1.82% |
| Heavy | 94.12% | 88.24% | **96.32%** | +2.20% |

**Key Insight:** IM-MoCo maintains high classification accuracy even under heavy motion, while U-Net degrades significantly.

---

## 6. Key Innovations & Insights

### 6.1 Motion-Guided INRs

**Novelty:** Unlike standard INRs that only encode spatial coordinates, the Motion INR encodes **both position and motion group index**, allowing it to learn different transformations for different motion events.

### 6.2 Decoupled Content-Motion Representation

```
Traditional:  image ──► [network] ──► corrected_image
                    (black box)

IM-MoCo:      image ──► Image_INR ──► motion-free content
                          ▲                │
                          │                │
              motion ──► Motion_INR ──► transforms
                          (separate, interpretable)
```

### 6.3 Self-Supervised via Physics

The only supervision is **data consistency** in k-space—no ground truth images needed. The gradient entropy regularizer acts as a generic image prior.

---

## 7. Reproducibility Notes

### 7.1 Environment Setup

```bash
# Create environment
mamba create -n immoco python=3.10
mamba activate immoco

# Install dependencies
pip install torch torchvision h5py numpy

# Install hash-grid encoding (critical for performance)
pip install git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch

# Clone repository
git clone https://github.com/multimodallearning/MICCAI24_IMMoCo.git
cd MICCAI24_IMMoCo
```

### 7.2 Training kID-Net (Pre-training Stage)

```bash
python src/train/train_kld_net.py \
  --data_path /path/to/fastmri \
  --epochs 4200 \
  --lr 1e-4 \
  --batch_size 4
```

### 7.3 Test-Time Optimization (Per Image)

```bash
python src/test/optimize_inrs.py \
  --input_kspace /path/to/corrupted_kspace.h5 \
  --kid_net_checkpoint /path/to/kid_net.pth \
  --output_dir ./results \
  --iterations 200 \
  --lr 1e-2
```

### 7.4 Critical Implementation Details

| Aspect | Detail |
|--------|--------|
| **Coordinate Encoding** | Must use hash-grid (not positional encoding) for efficiency |
| **Motion Group Index** | Normalize to [-1, 1] range for Motion INR input |
| **Complex Representation** | Handle real/imaginary as 2-channel tensors |
| **DC Loss Masking** | Only compute on acquired k-space lines (for undersampled data) |
| **Memory** | ~8GB GPU memory for 320×320 images |

### 7.5 Potential Pitfalls

1. **tiny-cuda-nn compilation:** May fail on non-CUDA systems or older GPUs
   - *Solution:* Use pre-built wheels or Docker container

2. **kID-Net thresholding:** The 20% line-corruption threshold is dataset-dependent
   - *Solution:* Validate on your data, may need tuning

3. **Motion group assignment:** Consecutive line grouping assumes contiguous motion
   - *Limitation:* May fail for non-contiguous motion patterns

4. **Computational cost:** 200 iterations per image takes ~2-3 minutes on RTX 3090
   - *Not real-time* but acceptable for offline correction

---

## 8. Limitations (Per Authors)

1. **Assumes known motion model:** Uses rigid transformations (rotation + translation)
   - *Extension:* Could incorporate non-rigid/B0 effects

2. **2D slices only:** Does not model through-plane motion in 3D volumes
   - *Extension:* Extend to 3D with slice-wise motion parameters

3. **Pre-trained kID-Net:** Requires supervised training on simulated motion
   - *Mitigation:* Could explore unsupervised motion detection

4. **Computational cost:** Per-image optimization is slower than feed-forward methods
   - *Trade-off:* Quality vs. speed

---

## 9. Extensions & Future Work

### 9.1 Immediate Extensions

1. **3D Motion Correction:** Extend to full 3D volumes with through-plane motion
2. **Non-rigid Motion:** Incorporate deformable transformations
3. **Joint Multi-slice:** Model motion correlations across slices

### 9.2 Integration with Your MRI Motion Research

Given your 8-direction exploration framework:

| Direction | IM-MoCo Relevance |
|-----------|-------------------|
| k-space domain correction | Direct extension - improve kID-Net or motion model |
| Image domain post-processing | Alternative to INR approach - compare CNN vs INR |
| Physics-informed methods | Combine with parallel imaging constraints |
| Self-supervised methods | Build on IM-MoCo's loss design |
| Diffusion models | Replace INRs with diffusion for motion estimation |
| Multi-scale methods | Apply IM-MoCo at multiple resolutions |
| Organ-specific modeling | Adapt motion priors for cardiac/abdominal |
| Real-time methods | Distill IM-MoCo into feed-forward network |

---

## 10. Citation

```bibtex
@InProceedings{Al_IMMoCo_MICCAI2024,
    author = {Al-Haj Hemidi, Ziad and Weihsbach, Christian and Heinrich, Mattias P.},
    title = {IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Implicit Neural Representations},
    booktitle = {Proceedings of Medical Image Computing and Computer Assisted Intervention -- MICCAI 2024},
    year = {2024},
    publisher = {Springer Nature Switzerland},
    volume = {LNCS 15007},
    pages = {382--392},
    doi = {10.1007/978-3-031-72104-5_37}
}
```

---

## 11. Cognitive Insights for Research

### Insight 1: Test-Time Optimization Paradigm

```
Traditional ML          IM-MoCo Approach
─────────────────       ─────────────────
Train once              Pre-train detector
                        │
Inference: forward      Test-time: optimize
pass (deterministic)    per sample (adaptive)
     │                        │
     ▼                        ▼
Fixed model              Instance-specific
                         solution
```

**Takeaway:** For inverse problems with known physics, test-time optimization can outperform fixed feed-forward networks.

### Insight 2: Decoupling Content and Degradation

```
┌────────────────────────────────────────────────────────┐
│  Black Box: corrupted ──► network ──► clean            │
│           (uninterpretable mapping)                    │
├────────────────────────────────────────────────────────┤
│  IM-MoCo:  corrupted ──┬─► Image_INR ──┐               │
│                        │   (content)    ├──► combine   │
│                        ├─► Motion_INR ──┘   (physics)  │
│                        │   (degradation)              │
│                        │                              │
│                        └──► interpretable!            │
└────────────────────────────────────────────────────────┘
```

**Takeaway:** Explicitly modeling the degradation process (motion) separately from content enables better generalization and interpretability.

### Insight 3: Self-Supervision via Domain Knowledge

```
No Ground Truth?         Use Physics!
─────────────────────────────────────────
K-space acquisition      Forward model
     │                        │
     ├── Data consistency ────┤
     │    (physics-based      │
     │     supervision)       │
     │                        │
     └── Image prior ─────────┤
          (gradient entropy   │
           = generic prior)   │
```

**Takeaway:** Domain physics (MRI forward model) can replace ground truth for self-supervised learning.

---

## 12. Action Items for Your Research

1. **Reproduce IM-MoCo** on fastMRI subset (baseline establishment)
2. **Ablation Study:** Test different motion models (rigid vs non-rigid)
3. **Extension:** Apply to your target anatomy (if not brain)
4. **Comparison:** Benchmark against your other 7 sub-directions
5. **Integration:** Could kID-Net + INRs be combined with diffusion models?

---

*Report generated: 2026-03-26*
*For: MRI Motion Artifact Correction Research Project*
