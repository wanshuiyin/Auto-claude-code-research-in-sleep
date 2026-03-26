# MRI运动伪影校正 - 图像域后处理

## 📚 Phase 1 Complete: Literature Survey

### Key Findings

**Current SOTA (2024–2025)**:
- **MACS-Net**: Swin Transformer + U-Net hybrid achieving best quantitative results (NRMSE: 45%→17%, SSIM: 79%→92%)
- **DIMA**: Unsupervised diffusion approach eliminating paired data requirements
- **Diffusion models**: Dominating for severe artifacts (MAR-CDPM, Res-MoCoDiff)

**Major Trends**:
1. **Architectural**: CNN → Transformer-CNN hybrids → Diffusion models
2. **Supervision**: Supervised → Unsupervised → Self-supervised → Zero-shot
3. **Domain**: K-space → Hybrid → Pure image-domain post-processing

**Critical Gaps Identified**:
| Gap | Opportunity |
|-----|-------------|
| Cross-scanner generalization | Domain-agnostic architectures |
| Multi-contrast unified models | Contrast-agnostic or promptable correction |
| Severity-adaptive correction | Artifact-level-aware networks |
| Real-time correction | Lightweight/mobile-optimized models |
| Diagnostic preservation | Task-aware loss functions |

### Generated Ideas

1. **Domain-Adaptive Motion Correction Network (DaMoCo)**
   - 跨扫描仪泛化的域自适应图像域校正

2. **Severity-Aware Dynamic Correction (SADC)**
   - 根据伪影严重程度自适应选择网络深度的层级感知网络

3. **Multi-Contrast Unified Motion Corrector (MCUMC)**
   - 单一模型处理 T1/T2/FLAIR 等多对比度 MRI

4. **Task-Preserving Motion Correction (TPMC)**
   - 保留诊断相关特征的下游任务感知损失

5. **Real-Time Lightweight Corrector (RTLC)**
   - 针对临床实时需求的轻量化模型
