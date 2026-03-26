# MRI 运动伪影 — 多 Agent 并行研究工作流

> **目标**: 8 个子方向同时探索，1 周内收敛到 1-2 个最有潜力的方向

---

## 概览

```
Week 1: 发散探索（8个Agent并行）
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Agent 1 │ │ Agent 2 │ │ Agent 3 │ │ Agent 4 │
│ k-space │ │ 图像域  │ │ PINN    │ │ 自监督  │
│   校正  │ │ 后处理  │ │ 联合重建│ │ 校正    │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     └─────────────┴─────────────┴─────────────┘
                   ↓
            sub-dirs/sub-1/ 到 sub-4/
                   ↓
            IDEA_REPORT_sub-{n}.md

┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Agent 5 │ │ Agent 6 │ │ Agent 7 │ │ Agent 8 │
│ 扩散模型│ │ 多尺度  │ │ 器官特定│ │ 实时快速│
│ 运动估计│ │ 方法    │ │ 运动建模│ │ 校正    │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     └─────────────┴─────────────┴─────────────┘
                   ↓
            sub-dirs/sub-5/ 到 sub-8/
                   ↓
            IDEA_REPORT_sub-{n}.md

Week 2: 收敛决策
                   ↓
     ┌─────────────────────────────┐
     │  对比分析 8 个子方向           │
     │  - 新颖性评分                  │
     │  - 可行性评估                  │
     │  - 影响力潜力                  │
     │  - 资源需求                    │
     └─────────────────────────────┘
                   ↓
     ┌─────────────────────────────┐
     │  选择 1-2 个方向               │
     │  生成 IDEA_CANDIDATES.md      │
     └─────────────────────────────┘

Week 3+: 深度实现
                   ↓
     ┌─────────────────────────────┐
     │  选定方向 → 完整代码          │
     │  手动部署到 4x4090            │
     │  /auto-review-loop            │
     └─────────────────────────────┘
```

---

## 8 个子方向定义

### Agent 1: k-space 域运动校正
**核心问题**: 直接在 k-space 学习运动参数，避免图像域的信息损失

**关键词**: k-space correction, motion parameter estimation, navigator-free

**启动命令**:
```bash
/idea-discovery "MRI motion artifact correction in k-space domain - learn motion parameters directly from k-space data without navigator echoes" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- k-space 运动模型（刚体/非刚体）
- 端到端可微的校正网络
- 与图像域方法的对比分析

---

### Agent 2: 图像域后处理校正
**核心问题**: 将带伪影的重建图像恢复为干净图像

**关键词**: image domain correction, post-processing, artifact removal

**启动命令**:
```bash
/idea-discovery "MRI motion artifact correction in image domain - deep learning based post-processing to remove artifacts from reconstructed images" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 轻量级后处理网络
- 与重建流程解耦的实用性
- 临床部署友好性

---

### Agent 3: 物理引导联合重建 (PINN)
**核心问题**: 将 MRI 物理模型嵌入神经网络，实现物理一致的运动校正

**关键词**: physics-informed neural network, PINN, MRI physics, joint reconstruction

**启动命令**:
```bash
/idea-discovery "Physics-informed neural networks for MRI motion correction - embed MRI forward model into deep learning for physically consistent motion artifact correction" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- MRI 物理模型 + 深度学习融合
- 可解释的运动参数估计
- 物理一致性保证

---

### Agent 4: 自监督/无监督校正
**核心问题**: 无需配对干净/带伪影数据，利用数据内在结构学习

**关键词**: self-supervised, unsupervised, blind motion correction, no ground truth

**启动命令**:
```bash
/idea-discovery "Self-supervised MRI motion artifact correction without ground truth - blind motion correction using data intrinsic structure" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 零/少样本学习方法
- 数据增强策略
- 临床数据友好性

---

### Agent 5: 扩散模型运动估计
**核心问题**: 利用扩散模型的生成能力进行高质量运动校正

**关键词**: diffusion model, generative correction, score-based model

**启动命令**:
```bash
/idea-discovery "Diffusion models for MRI motion artifact correction - leverage generative priors for high-quality motion artifact removal" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 扩散模型先验在 MRI 中的应用
- 条件扩散/引导采样
- 与确定性方法的对比

---

### Agent 6: 多尺度/多分辨率方法
**核心问题**: 不同分辨率层次处理不同类型的运动伪影

**关键词**: multi-scale, multi-resolution, hierarchical correction

**启动命令**:
```bash
/idea-discovery "Multi-scale hierarchical MRI motion correction - handle different motion artifacts at different resolution levels" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 粗到细的多尺度框架
- 各层级的任务分工
- 计算效率优化

---

### Agent 7: 特定器官运动建模
**核心问题**: 针对特定器官（脑、心脏、腹部）设计专门的运动模型

**关键词**: organ-specific, brain MRI, cardiac MRI, abdominal MRI

**启动命令**:
```bash
/idea-discovery "Organ-specific motion correction for brain MRI - tailored motion models for neuroimaging applications" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 脑部运动特性建模（头动、血管搏动）
- 与通用方法的对比
- 神经影像应用验证

---

### Agent 8: 实时/快速校正
**核心问题**: 平衡校正质量与计算速度，实现临床可行的时间成本

**关键词**: real-time, fast correction, lightweight network, clinical deployment

**启动命令**:
```bash
/idea-discovery "Fast and lightweight MRI motion correction for clinical deployment - real-time capable methods with minimal computational overhead" \
    — AUTO_PROCEED: false \
    — PILOT_MAX_HOURS: 0 \
    — sources: zotero, web \
    — arxiv download: true
```

**预期产出**:
- 轻量级网络架构
- 计算复杂度分析
- 实时性验证

---

## 文件组织结构

```
project/
├── CLAUDE.md                           # 项目仪表盘
├── RESEARCH_BRIEF.md                   # 研究简介
├── WORKFLOW.md                         # 本文件
├── ZOTERO_SETUP.md                     # Zotero配置
├── sub-dirs/
│   ├── sub-1-kspace/                   # Agent 1: k-space校正
│   │   ├── RESEARCH_BRIEF.md          # 子方向简介
│   │   └── (idea-discovery输出)
│   ├── sub-2-image/                    # Agent 2: 图像域
│   ├── sub-3-pinn/                     # Agent 3: PINN
│   ├── sub-4-selfsuper/                # Agent 4: 自监督
│   ├── sub-5-diffusion/                # Agent 5: 扩散模型
│   ├── sub-6-multiscale/               # Agent 6: 多尺度
│   ├── sub-7-brain/                    # Agent 7: 器官特定
│   └── sub-8-realtime/                 # Agent 8: 实时
├── idea-reports/                       # 汇总各Agent产出
│   ├── IDEA_REPORT_sub-1.md
│   ├── IDEA_REPORT_sub-2.md
│   └── ...
├── IDEA_CANDIDATES.md                  # Week 2: 候选方向汇总
└── docs/
    └── research_contract.md            # Week 2+: 最终选定方向
```

---

## 执行计划

### Day 0: 准备
- [ ] 创建 8 个 sub-dirs/
- [ ] 为每个 sub-dir 创建 RESEARCH_BRIEF.md（继承主简介 + 子方向特定信息）
- [ ] 配置 Zotero（如可用）
- [ ] 启动 8 个 Conductor workspace

### Day 1-3: 并行探索
- [ ] 每个 Agent 执行 `/idea-discovery`
- [ ] 监控进度，确保所有 Agent 正常运行
- [ ] 每个 Agent 产出 `IDEA_REPORT.md`

### Day 4-5: 汇总整理
- [ ] 收集 8 份 `IDEA_REPORT.md` 到 `idea-reports/`
- [ ] 创建 `IDEA_CANDIDATES.md` 对比表
- [ ] 初步评估各方向潜力

### Day 6-7: 收敛决策
- [ ] 深度分析 8 个子方向
- [ ] 评分：新颖性 × 可行性 × 影响力
- [ ] 选择 1-2 个方向
- [ ] 更新 `docs/research_contract.md`

---

## 对比评估矩阵

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| **新颖性** | 30% | 1-5分，5分为领域内首创 |
| **可行性** | 30% | 1-5分，考虑4x4090资源限制 |
| **影响力** | 20% | 1-5分，临床/学术价值 |
| **数据可得性** | 10% | 1-5分，公开数据集 availability |
| **发表潜力** | 10% | 1-5分，目标会议匹配度 |

**总分 = Σ(维度分数 × 权重)**

---

## 启动检查清单

每个 sub-dir 启动前确认：

- [ ] RESEARCH_BRIEF.md 已创建
- [ ] Agent 启动命令已确定
- [ ] Conductor workspace 已就绪
- [ ] Zotero MCP 已配置（推荐）
- [ ] Codex MCP 已配置
- [ ] 输出目录权限正确

---

## 监控命令

```bash
# 检查各 Agent 进度（在 project root）
for d in sub-dirs/*/; do
    echo "=== $d ==="
    ls -la "$d"/*.md 2>/dev/null || echo "No .md files yet"
done

# 汇总所有 IDEA_REPORT
find sub-dirs -name "IDEA_REPORT.md" -exec cp {} idea-reports/ \;

# 对比各方向得分
python3 tools/compare_directions.py idea-reports/
```

---

## 收敛后流程

选定方向后：

```bash
# 1. 为选定方向生成完整代码
/experiment-bridge — code review: true

# 2. 手动部署到 4x4090
#    - 复制代码到远程服务器
#    - 配置环境
#    - 启动训练

# 3. 进入审稿循环
/auto-review-loop "[选定方向描述]" — human checkpoint: true

# 4. 论文写作
/paper-writing "NARRATIVE_REPORT.md" — venue: MICCAI
```

---

## 风险与应对

| 风险 | 可能性 | 应对策略 |
|------|--------|----------|
| 8个Agent同时运行资源紧张 | 中 | 分批启动，先4个再4个 |
| 子方向同质化严重 | 低 | 通过关键词差异化定义 |
| 发现所有方向都已被做 | 低 | novelty-check 会识别 |
| 选定方向实验不顺利 | 中 | 保留2-3个backup方向 |
| Zotero配置失败 | 低 | 回退到纯web搜索 |

---

## 下一步

1. **配置 Zotero**: 阅读 `ZOTERO_SETUP.md`
2. **创建 sub-dirs**: 为 8 个子方向创建工作目录
3. **启动第一批次**: 选择 4 个子方向先启动
4. **监控进展**: 定期检查各 Agent 输出
