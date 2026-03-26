# MRI运动伪影校正 - K-space域运动校正

## 📚 Phase 1 Complete: Literature Survey

### 核心问题
MRI 扫描时间长，患者运动导致 k-space 数据污染，产生运动伪影。传统方法依赖导航回波(navigator)或外部追踪，增加扫描复杂度。**k-space 域直接运动估计**成为热点方向——无需额外采集，直接从原始 k-space 数据估计运动参数。

### 当前 SOTA 方法 (2024-2025)

| 方法 | 年份 | 核心创新 | 特点 |
|------|------|----------|------|
| **SISMIK** | IEEE TMI 2025 | 直接从 k-space 估计刚体运动参数，无需无运动参考 | 训练于 600k 模拟运动，支持全动态范围 k-space |
| **PI-MoCoNet** | arXiv 2025 | Physics-Informed 两阶段网络 (检测+校正) | 结合 L1 + LPIPS + k-space 数据一致性损失，PSNR 28→46 dB |
| **KS-RegNet** | 2022 | 无监督 k-space 驱动可变形配准 | 无需 ground truth DVF，直接从 k-space 定义损失 |
| **Data Consistent Deep Rigid MC** | MIDL 2024 | 将联合优化降维为仅运动参数搜索 | 深度网络生成重建结果作为运动参数函数 |

### 技术趋势
```
2019-2021: GAN-based 方法 (cGAN, MoCoGAN)
2022-2023: CNN + 物理约束 (数据一致性)
2024:     Transformer-CNN 混合 (Swin Transformer)
2025:     扩散模型 (DIMA, 无监督校正) + Physics-Informed
```

### 关键 Gap (研究机会)

| Gap | 机会 |
|-----|------|
| 仅限刚体运动 | **非刚体运动** (腹部呼吸、心脏) 的 k-space 建模 |
| 需模拟数据训练 | **真实运动数据**的自监督/无监督学习 |
| 2D 切片级处理 | **3D 体积** k-space 运动校正 |
| 单一对比度 | **多对比度统一**运动校正框架 |
| 逐扫描优化 | **Amortized** 运动估计 (避免 per-scan 优化) |

### Generated Ideas

1. **SISMIK-Extension**: 扩展 SISMIK 到非刚体运动（变形场估计）
2. **Self-Supervised K-space MoCo**: 利用 k-space 冗余性进行自监督
3. **3D Volumetric K-space Correction**: 3D 体积数据的运动校正
4. **Amortized K-space Motion Estimator**: 避免逐扫描优化的摊销方法
