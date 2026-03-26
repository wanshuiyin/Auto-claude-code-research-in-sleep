# MRI运动伪影校正 - 完整方向收敛分析 (5个方向)

## 各子方向评估汇总

### 1. K-space域运动校正 (sub-1-kspace) ⭐⭐⭐⭐

**核心发现：**
- **SISMIK** (TMI 2025): 直接从 k-space 估计刚体运动，无需参考图像
- **PI-MoCoNet**: Physics-Informed，PSNR 28→46 dB
- **趋势**: 2025年热点是 Physics-Informed + 扩散模型

**关键 Gap:**
- 仅限刚体运动 → **非刚体运动**建模是明确机会
- 需模拟数据训练 → **自监督/无监督**学习
- 2D切片级 → **3D体积**运动校正

**价值**: 物理基础扎实，但实现复杂度高

---

### 2. 图像域后处理 (sub-2-image) ⭐⭐⭐⭐

**核心发现：**
- **MACS-Net**: Swin Transformer + U-Net，NRMSE: 45%→17%
- **DIMA**: 无监督扩散方法，无需配对数据
- **趋势**: CNN → Transformer-CNN → 扩散模型

**关键 Gap:**
- 跨扫描仪泛化
- 多对比度统一模型
- 严重伪影自适应校正

**价值**: 最成熟，临床落地最容易

---

### 3. 物理引导联合重建 (sub-3-pinn) ⭐⭐⭐⭐⭐

**核心发现：**
- **PI-MoCoNet** (2025): Physics-Informed，~1dB PSNR 提升
- **PHIMO** (2024): 自监督运动检测，40%扫描时间减少
- 关键公式: **y = M·F(S·W(φ)·x) + n**

**架构**: 数据一致性块(CG/梯度下降) + CNN正则化块交替

**关键 Gap:**
- 联合运动估计+重建优化
- 扩散模型结合物理引导
- 基础模型跨协议预训练

**价值**: 理论扎实，结合物理保证

---

### 4. 自监督/无监督校正 (sub-4-selfsuper) ⭐⭐⭐⭐⭐

**核心发现：**
- **IM-MoCo** (MICCAI 2024): 运动引导INR，+5% SSIM
- **技术趋势**: INR + k-space数据一致性 + 物理引导自监督

**关键 Gap:**
1. Amortized INR运动校正（避免逐扫描优化）
2. 盲非刚性运动校正（心脏/呼吸）
3. 多线圈自监督学习
4. 测试时训练适应新运动

**价值**: 无需配对ground truth，数据获取最容易，临床最实用

---

### 5. 扩散模型运动估计 (sub-5-diffusion) ⭐⭐⭐⭐⭐🔥

**核心发现：**
- **Res-MoCoDiff** (2025): 首个MRI运动校正专用扩散模型
- **效率可行**: DDIM 20-50步 → DPM-Solver++ 15-20步 → Consistency Models 1-4步
- **趋势**: SPIRiT-Diffusion, Heat-Diffusion - k-space自一致性驱动

**关键 Gap:**
1. **运动专用架构** - 仅Res-MoCoDiff一个工作
2. **实时部署** - 需要<10步保持质量
3. **解剖正确性验证** - 防止生成模型幻觉
4. **物理引导联合估计** - 运动参数+重建联合优化
5. **自监督设置** - 减少配对数据依赖

**价值**: 当前热点方向，高影响力潜力

---

## 🎯 最终推荐决策

### 推荐方向: 物理引导的扩散模型自监督运动校正

**融合策略**:
```
物理引导 (PINN)    +    扩散模型 (Diffusion)    +    自监督 (Self-supervised)
     ↓                        ↓                           ↓
 k-space数据一致性      高质量重建先验            无需配对ground truth
 保证重建准确性         处理严重伪影              临床数据直接训练
```

**核心创新点**:
1. **Physics-Guided Diffusion**: 扩散模型结合k-space数据一致性约束
2. **Self-Supervised Training**: 利用MRI前向模型作为监督信号，无需清晰参考图像
3. **Motion-Aware Diffusion**: 显式建模运动场作为扩散条件
4. **Fast Sampling**: Consistency Model或DPM-Solver++实现<10步推理

**为何这是最佳选择**:
| 维度 | 评估 |
|------|------|
| **新颖性** | ⭐⭐⭐⭐⭐ 融合三个热点方向，极少现有工作 |
| **可行性** | ⭐⭐⭐⭐ 有Res-MoCoDiff、PI-MoCoNet等代码基础 |
| **影响力** | ⭐⭐⭐⭐⭐ 扩散模型是当前顶会热点 |
| **实用性** | ⭐⭐⭐⭐⭐ 自监督=无需配对数据，临床落地友好 |
| **算力匹配** | ⭐⭐⭐⭐⭐ 4x4090可支持扩散模型训练+物理迭代 |

---

## 备选方案

### 方案 B: 纯自监督物理方法（更保守）
聚焦 PHIMO + IM-MoCo 方向，做 amortized INR + 物理约束，不引入扩散模型
- 优势: 实现更简单，训练更稳定
- 劣势: 影响力可能不如扩散模型方向

### 方案 C: 图像域多对比度（最保守）
基于 MACS-Net 做多对比度统一校正
- 优势: 实现最简单，快速出成果
- 劣势: 创新性较低，竞争激烈

---

## 下一步行动计划

### Phase 2: 深度实验设计（当前 → 3天内）
1. **创建 research_contract.md** - 聚焦当前方向
2. **生成 EXPERIMENT_PLAN.md** - 实验设计（claim → 实验块）
3. **数据集准备** - IXI, fastMRI, MR-ART 下载
4. **代码框架** - 基于 PI-MoCoNet + Res-MoCoDiff 修改

### Phase 3: 代码实现（1-2周）
1. Baseline复现（PI-MoCoNet, Res-MoCoDiff）
2. 核心创新实现（Physics-Guided Diffusion）
3. 自监督训练策略

### Phase 4: 实验迭代（2-4周）
1. 本地小规模验证
2. 部署到4x4090完整训练
3. Ablation studies

### Phase 5: 论文写作（1-2周）
1. 投稿级论文撰写
2. MICCAI/IPMI/MRM 投稿

---

## 参考代码资源

| 方法 | 链接 | 用途 |
|------|------|------|
| PI-MoCoNet | https://github.com/mosaf/PI-MoCoNet.git | Physics-Informed基础 |
| PHIMO | https://github.com/HannahEichhorn/PHIMO | 自监督运动检测 |
| IM-MoCo | arXiv:2407.02974 | INR运动建模参考 |
| Res-MoCoDiff | (需搜索) | 扩散模型基础 |
| fastMRI | https://github.com/facebookresearch/fastMRI | 数据集+基础模型 |

---

## 确认决策

**请选择：**
- [ ] **主推荐**: 物理引导的扩散模型自监督运动校正
- [ ] **备选B**: 纯自监督物理方法（无扩散模型）
- [ ] **备选C**: 图像域多对比度统一校正

确认后生成详细的 `docs/research_contract.md` 和实验计划。
