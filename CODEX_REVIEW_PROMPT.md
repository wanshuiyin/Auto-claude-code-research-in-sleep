# Code Review Request: Motion-Explicit Diffusion for MRI Motion Correction

## Project Context

We are validating **Direction B: Explicit Motion Modeling** for MRI motion artifact correction research. This is a feasibility pilot experiment (not production code) to be completed in 1-2 days before committing to full Phase 3 implementation.

### Core Innovation
Explicitly predict motion field φ as condition for diffusion model, vs blind estimation (AutoDPS approach).

```
Our approach:
Input y ──→ [Motion Estimation] ──→ φ ──→ [Conditional Diffusion] ──→ x̂
              (explicit motion field as condition)
```

### Competitive Landscape
- **AutoDPS (2025)**: Blind estimation with diffusion + data consistency
- **Res-MoCoDiff (2025)**: Residual-guided diffusion
- **PI-MoCoNet (2025)**: Two-stage detection + correction
- **Our differentiation**: Explicit motion field conditioning

---

## Code Location

```
experiments/pilot_motion_explicit/
├── motion_network.py       # Motion field estimation (Encoder-Decoder)
├── physics_layer.py        # k-space physics constraints (FFT/IFFT, data consistency)
├── diffusion_cond.py       # Conditional diffusion model (Motion-conditioned U-Net)
├── self_supervised_loss.py # Combined loss (diffusion + reconstruction + smoothness)
├── pilot_train.py          # End-to-end training script
└── README.md               # Documentation
```

**Total**: ~1450 lines of PyTorch code

---

## Review Focus Areas

### 1. Architecture Correctness
- [ ] MotionNetwork → Physics → ConditionalDiffusion pipeline is sound
- [ ] Input/output tensor shapes are consistent across modules
- [ ] Motion field φ (B, 2, H, W) correctly conditions the diffusion model

### 2. Gradient Flow & Training Stability
- [ ] Joint training of motion network + diffusion model: gradients flow correctly?
- [ ] Any risk of gradient explosion/vanishing in the end-to-end setup?
- [ ] Is gradient clipping (max_norm=1.0) appropriate?

### 3. Physics Layer Implementation
- [ ] FFT/IFFT implementation: `torch.fft.fft2` with `norm='ortho'` correct?
- [ ] Data consistency loss: `||M * F(pred) - measured_kspace||^2` correctly implemented?
- [ ] Data consistency projection: hard constraint implementation sound?
- [ ] Motion corruption simulator: rigid and non-rigid modes reasonable for pilot?

### 4. Loss Design
- [ ] Combined loss weights: `λ_diff=1.0, λ_recon=0.1, λ_smooth=0.01` — are these reasonable?
- [ ] Self-supervised reconstruction loss: `L1(pred_x0, corrupted)` — is this the right target?
- [ ] Motion smoothness loss: total variation on motion field — sufficient regularization?

### 5. Diffusion Model Details
- [ ] Time embedding: sinusoidal + MLP projection — standard implementation?
- [ ] DDPM scheduler: beta schedule and variance computation correct?
- [ ] Sampling step: any issues with the denoising + optional physics projection?

### 6. Scalability Concerns (Pilot → Production)
- [ ] Current: 128x128 simulated data — what changes needed for real MRI (320x320 or 640x640)?
- [ ] Memory efficiency: any obvious bottlenecks for larger batch sizes?
- [ ] Model capacity: MotionNet (~0.5M) + Diffusion (~8M) — sufficient for pilot but scalable?

---

## Specific Questions

### Q1: Motion Field Conditioning
In `diffusion_cond.py`, the motion field is concatenated with noisy image as input:
```python
x_cond = torch.cat([x, motion_field], dim=1)  # (B, 3, H, W)
```
Is this the best way to condition, or should motion be injected at multiple U-Net levels?

### Q2: Physics Projection During Sampling
In `DiffusionScheduler.sample_step()`, there's optional physics projection:
```python
if physics_layer is not None and measured_kspace is not None:
    x_t_minus_1 = physics_layer.data_consistency_projection(x_t_minus_1, measured_kspace, mask)
```
Should this be applied at every step or only final steps? Impact on convergence?

### Q3: Self-Supervised Signal
The reconstruction loss compares `pred_x0` (predicted clean) with `corrupted` (input):
```python
recon_loss = F.l1_loss(pred_x0, corrupted)
```
Is this valid self-supervision, or should we use forward model: `||F(S*pred_x0) - y||`?

### Q4: Validation Criteria
Current pilot success criteria:
- No NaN/Inf
- Loss decreases
- PSNR > 15 dB (vs input)

Are these too lenient? What would indicate "direction is feasible" vs "implementation bug"?

---

## Deliverables

Please provide:
1. **Critical issues**: Any bugs that would prevent training from running
2. **Design concerns**: Architectural choices that may limit scalability
3. **Suggestions for improvement**: Quick wins to improve pilot success probability
4. **Go/No-go recommendation**: Is this code ready to run for 1-2 day feasibility validation?

---

## Constraints

- **Timeline**: 1-2 days for pilot validation
- **Compute**: Local CPU/small GPU only (no 4090 cluster for pilot)
- **Data**: Simulated 128x128 images (not real MRI yet)
- **Goal**: Prove "direction B is technically feasible" before full Phase 3

---

## References

- AutoDPS: https://arxiv.org/abs/2501.14769 (our main competitor)
- Res-MoCoDiff: https://pmc.ncbi.nlm.nih.gov/articles/PMC12083705/
- PI-MoCoNet: https://github.com/mosaf/pi-moconet
