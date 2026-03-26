# Research Brief: Brain MRI-Specific Motion Correction

## Problem Statement

Brain MRI is the most common MRI application, yet highly susceptible to motion artifacts due to:
1. Long scan times (structural: 5-10 min, fMRI: 30+ min)
2. Patient populations (children, elderly, patients with conditions)
3. High resolution requirements (sub-millimeter)
4. Need for quantitative accuracy

Generic motion correction methods don't account for brain-specific characteristics:
- Rigid skull constraint (bulk motion only, no deformation)
- CSF pulsatility
- Vascular pulsation artifacts
- Standard orientations (axial, sagittal, coronal)

Can we design specialized motion correction that leverages these constraints?

## Background

- **Field**: Neuroimaging / Brain MRI
- **Sub-area**: Structural MRI, fMRI, diffusion MRI
- **Key concepts**:
  - Brain anatomy (GM, WM, CSF)
  - Rigid motion within skull
  - Prospective motion correction (PROMO, slice tracking)
  - Retrospective correction
  - Quality metrics (tSNR for fMRI)
- **Related work**:
  - FSL motion correction (MCFLIRT)
  - SPM realignment
  - AFNI 3dvolreg
  - Deep learning brain MRI correction

## Constraints

- **Compute**: 4x RTX 4090 (remote server, manual deployment)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / NeuroImage / HBM

## What I'm Looking For

- [x] New method: brain-optimized motion correction
- [ ] Leverage rigid-body constraint
- [ ] Handle brain-specific artifacts (pulsatility)

## Domain Knowledge

### Brain Motion Characteristics:

1. **Rigid constraint**: Skull prevents deformation
   - Only 6 DOF (3 rotation + 3 translation)
   - Same motion for entire brain
   - Can use smaller parameter space

2. **Pulsatile artifacts**:
   - Cardiac cycle causes CSF pulsation
   - Vascular flow artifacts
   - Periodic, predictable patterns

3. **Scan types**:
   - T1-weighted: high resolution, contrast for anatomy
   - T2/FLAIR: pathology detection
   - fMRI: temporal dynamics critical
   - DWI/DTI: motion + distortion

### Domain-Specific Opportunities:

1. **Anatomical priors**:
   - Brain atlas as shape prior
   - Tissue segmentation guides correction
   - Ventricle shape constraints

2. **Head motion modeling**:
   - Physics of head rotation/translation
   - Predictable motion patterns
   - Center of rotation near brainstem

3. **Quality assessment**:
   - Brain-specific metrics (not just SSIM)
   - Cortical surface alignment
   - fMRI tSNR preservation

### Clinical Applications:

- Pediatric imaging (cannot stay still)
- Sedated patients (reduced sedation with better correction)
- fMRI (motion affects connectivity analysis)
- Longitudinal studies (consistent correction)

## Non-Goals

- Generic body motion correction (focus on brain)
- Non-rigid deformation (brain is rigid in skull)
- Other organs (cardiac, abdominal have different characteristics)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Designed specifically for brain MRI
- Leverages rigid-body constraint for better accuracy
- Validated on brain datasets (not just generic images)
- Improvement over general-purpose methods
- Clinical relevance demonstrated

## Datasets to Consider

- ABCD (Adolescent Brain Cognitive Development)
- UK Biobank
- HCP (Human Connectome Project)
- OpenNeuro brain datasets
- fastMRI brain subset
