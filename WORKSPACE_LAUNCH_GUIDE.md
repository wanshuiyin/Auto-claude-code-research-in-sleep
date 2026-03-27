# 启动5个新Workspace的配置指南

## 概述
- 已有1个可行idea（sub-5: Diffusion-based）
- 已有5个方向完成文献调研
- **目标**: 5个新workspace（3个基础 + 2个综合）

---

## 基础方向（3个）

### Workspace 1: Multi-Scale Motion Correction
```bash
/idea-discovery "MRI motion artifact correction - Multi-scale hierarchical motion correction" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出**: `sub-dirs/sub-6-multiscale/IDEA_REPORT.md`

**关键问题**:
- 如何分层处理global/regional/fine-scale运动？
- Coarse-to-fine vs Parallel multi-scale？
- 计算资源如何分配到不同尺度？

---

### Workspace 2: Brain-Specific Motion Correction
```bash
/idea-discovery "MRI motion artifact correction - Brain-specific motion correction leveraging rigid-body constraints" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出**: `sub-dirs/sub-7-brain/IDEA_REPORT.md`

**关键问题**:
- 如何利用脑部刚体约束（6DOF）？
- 如何处理CSF脉动等脑特有artifact？
- 公开数据集：ABCD, UK Biobank, HCP

---

### Workspace 3: Real-time Lightweight Correction
```bash
/idea-discovery "MRI motion artifact correction - Real-time lightweight motion correction for clinical deployment" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出**: `sub-dirs/sub-8-realtime/IDEA_REPORT.md`

**关键问题**:
- 如何设计<100ms的轻量级网络？
- 知识蒸馏/模型压缩的效果？
- 速度和精度的最佳平衡？

---

## 综合方向（2个）

### Workspace 4: Physics-Guided Diffusion with Multi-Scale Estimation
**综合**: PINN (sub-3) + Diffusion (sub-5) + Multi-Scale (sub-6)

```bash
/idea-discovery "MRI motion artifact correction - Physics-guided diffusion with multi-scale motion estimation" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出**: `sub-dirs/sub-9-hybrid-pinn-diffusion/IDEA_REPORT.md`

**核心创新点**:
- 扩散模型作为生成先验，物理约束保证解剖正确性
- 多尺度运动估计：global rigid + local non-rigid
- 自监督训练策略减少配对数据依赖

**关键问题**:
- 如何将k-space数据一致性融入扩散采样过程？
- 多尺度运动如何与扩散时间步耦合？
- 如何实现单步/少步推理（Consistency Models）？

---

### Workspace 5: Self-Supervised Real-time Brain Motion Correction
**综合**: Self-Supervised (sub-4) + Real-time (sub-8) + Brain (sub-7)

```bash
/idea-discovery "MRI motion artifact correction - Self-supervised real-time brain motion correction with amortized estimation" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出**: `sub-dirs/sub-10-brain-realtime-selfsuper/IDEA_REPORT.md`

**核心创新点**:
- 摊销优化（Amortized）：避免逐扫描优化
- 脑部刚体约束简化运动参数空间
- 测试时训练（Test-time training）适应新患者

**关键问题**:
- 如何设计摊销运动估计器？
- 自监督信号如何设计（k-space冗余性）？
- 如何实现<50ms的实时推理？

---

## 5个Workspace对比

| # | 方向 | 类型 | 核心创新 | 技术难度 | 临床价值 |
|---|------|------|----------|----------|----------|
| 6 | Multi-scale | 基础 | 分层处理不同尺度运动 | 中 | 高 |
| 7 | Brain-specific | 基础 | 利用刚体约束简化问题 | 低 | 高 |
| 8 | Real-time | 基础 | 临床可部署的轻量模型 | 中 | 极高 |
| 9 | Physics-Diffusion-Hybrid | 综合 | SOTA精度 + 物理保证 | 高 | 高 |
| 10 | Brain-Real-time-SelfSuper | 综合 | 无监督 + 实时 + 专用 | 高 | 极高 |

---

## PR工作流程

### Branch命名
```
feat/idea-6-multiscale
feat/idea-7-brain
feat/idea-8-realtime
feat/idea-9-hybrid-pinn-diffusion
feat/idea-10-brain-realtime-selfsuper
```

### PR标题格式
```
[IDEA] Sub-6: Multi-scale hierarchical motion correction
[IDEA] Sub-7: Brain-specific motion correction
[IDEA] Sub-8: Real-time lightweight correction
[IDEA] Sub-9: Physics-guided diffusion with multi-scale estimation
[IDEA] Sub-10: Self-supervised real-time brain motion correction
```

### 建议的提交内容
每个PR应包含：
1. `IDEA_REPORT.md` - 文献调研 + 候选ideas
2. `FINDINGS.md` - 关键发现总结
3. `PAPERS/` - 下载的重要论文PDF

---

## 已有方向参考

已有5个方向的报告位置：
- `sub-dirs/sub-1-kspace/IDEA_REPORT.md`
- `sub-dirs/sub-2-image/IDEA_REPORT.md`
- `sub-dirs/sub-3-pinn/IDEA_REPORT.md`
- `sub-dirs/sub-4-selfsuper/IDEA_REPORT.md`
- `sub-dirs/sub-5-diffusion/IDEA_REPORT.md` ← 已有可行idea

**建议**：综合方向的Agent应参考sub-3, sub-4, sub-5的报告，了解已有基础。

---

## 合并后评估流程

等5个PR都合并后，在当前workspace：

```bash
# 拉取所有更新
git pull origin Hao003/mri-motion-artifact

# 对比8个方向的IDEA_REPORT
# 评估标准：
# 1. 与sub-5的diffusion idea互补性
# 2. 技术可行性（4x4090）
# 3. 新颖性（vs现有文献）
# 4. 临床价值
```

然后我可以帮你：
1. **横向对比** 8个方向的所有ideas
2. **可行性打分** 选出Top 2-3个
3. **生成对比矩阵** 帮助决策

---

## 备选综合方向

如果上述两个综合方向不满意，备选方案：

### 备选综合A: Uncertainty-Aware Motion Correction
**综合**: Diffusion (不确定性) + Multi-Scale + PINN
- 利用扩散模型估计校正不确定性
- 多尺度不确定性融合
- 不确定性指导的采集策略

### 备选综合B: Cross-Domain Transfer for Motion Correction
**综合**: Domain Adaptation (sub-2) + Self-Supervised (sub-4) + Real-time (sub-8)
- 跨扫描仪迁移学习
- 源域：模拟数据，目标域：真实扫描
- 实时适应新扫描仪
