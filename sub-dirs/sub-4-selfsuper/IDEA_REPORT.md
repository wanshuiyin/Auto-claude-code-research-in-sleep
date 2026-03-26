# MRI运动伪影校正 - 自监督/无监督方法

## 🚦 Phase 1 Complete: Literature Survey

### Key Findings

**Landscape Summary:**
- **6 major gaps identified:** Real motion evaluation, non-rigid correction, 3D volumetric correction, multi-coil parallel imaging, computational efficiency, and pathology preservation
- **Technical trends:** Implicit Neural Representations (INRs), data consistency losses in k-space, and physics-informed self-supervision
- **Most relevant recent work:** IM-MoCo (MICCAI 2024) - self-supervised motion correction using motion-guided INRs with +5% SSIM improvement

**Papers Downloaded:**
- [IM-MoCo](https://arxiv.org/abs/2407.02974) (MICCAI 2024) → `papers/immoco_2407.02974.pdf`

**Structural Gaps (Opportunities):**
1. Amortized INR-based motion correction (avoid per-scan optimization)
2. Blind non-rigid motion correction for cardiac/respiratory motion
3. Multi-coil self-supervised learning
4. Test-time training for motion correction
5. Diffusion models for motion correction

### Generated Ideas

1. **Amortized Motion INR (AMINR)**
   - 摊销优化的隐式神经表示运动校正，避免逐扫描优化

2. **Blind Non-Rigid Motion Correction (BNR-MoCo)**
   - 心脏/呼吸运动的盲非刚性运动校正

3. **Multi-Coil Self-Supervised MoCo (MC-SSMoCo)**
   - 利用多线圈冗余的自监督学习

4. **Test-Time Training MoCo (TTT-MoCo)**
   - 测试时训练适应新运动模式

5. **Self-Supervised Diffusion MoCo (SS-DiffMoCo)**
   - 结合扩散模型与自监督
