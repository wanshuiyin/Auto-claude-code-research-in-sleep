# Pilot Experiment: Motion-Explicit Diffusion for MRI Motion Correction

方向B可行性验证实验 - 显式运动场建模的条件化扩散模型

## 概述

本实验验证**显式运动场建模**作为MRI运动校正的差异化方向的可行性。

**核心创新**: 显式预测运动场 φ，作为扩散模型的条件，而非盲估计

**与 AutoDPS 的区别**:
```
AutoDPS (盲估计):          我们的方法 (显式建模):
输入 y ──→ [扩散] ──→ x̂    输入 y ──→ [运动估计] ──→ φ ──→ [扩散] ──→ x̂
         隐式处理                        显式运动信息
```

## 文件结构

```
pilot_motion_explicit/
├── motion_network.py       # 运动场估计网络 (Encoder-Decoder)
├── diffusion_cond.py       # 条件化扩散模型 (Motion-conditioned U-Net)
├── physics_layer.py        # k-space物理约束层
├── self_supervised_loss.py # 自监督损失函数
├── pilot_train.py          # 端到端训练脚本
└── README.md               # 本文件
```

## 快速开始

### 1. 环境准备

```bash
cd experiments/pilot_motion_explicit
pip install torch torchvision numpy tqdm
```

### 2. 运行验证测试

测试各个模块:

```bash
# 测试运动场网络
python motion_network.py

# 测试物理层
python physics_layer.py

# 测试扩散模型
python diffusion_cond.py

# 测试损失函数
python self_supervised_loss.py
```

### 3. 运行完整pilot实验

```bash
python pilot_train.py
```

预期输出:
- 训练损失曲线
- 验证PSNR指标
- 模型检查点 (checkpoints/pilot_checkpoint.pt)
- 结果摘要 (checkpoints/pilot_results.json)

## 验证通过标准

| 检查项 | 标准 | 说明 |
|--------|------|------|
| 训练稳定性 | 无NaN/Inf | 梯度裁剪确保稳定 |
| 损失下降 | 最终 < 初始 | 模型在学习 |
| PSNR提升 | > 15 dB | 相比输入有改善 |
| 端到端可行 | 可联合训练 | 运动+扩散联合优化 |

## 实验结果解读

**成功标志**:
- ✅ 训练损失稳定下降
- ✅ 验证PSNR逐epoch提升
- ✅ 运动场可视化合理（平滑、与伪影模式匹配）

**失败可能原因**:
- ❌ 梯度爆炸 → 调整学习率或梯度裁剪
- ❌ 运动场不收敛 → 简化网络或增加监督信号
- ❌ 扩散模型不收敛 → 检查噪声调度或损失函数

## 技术细节

### 1. 运动场估计网络 (motion_network.py)

- **架构**: Encoder-Decoder with Skip Connections
- **输入**: 运动污染图像 (B, 1, H, W)
- **输出**: 运动场 φ (B, 2, H, W) - [dx, dy]
- **参数量**: ~0.5M (feature_dim=32)

### 2. 条件化扩散模型 (diffusion_cond.py)

- **架构**: U-Net with Time Embedding
- **条件**: 运动场 + 时间步
- **输入通道**: 图像(1) + 运动场(2) = 3
- **时间步**: 1000步DDPM调度

### 3. 物理约束层 (physics_layer.py)

- **FFT/IFFT**: PyTorch可微实现
- **数据一致性**: 软约束 (loss) + 硬约束 (projection)
- **运动模拟**: 刚性 + 非刚性两种模式

### 4. 自监督损失 (self_supervised_loss.py)

- **扩散损失**: MSE噪声预测
- **重建损失**: L1像素损失
- **运动平滑**: 总变差正则化
- **权重**: λ_diff=1.0, λ_recon=0.1, λ_smooth=0.01

## 与竞争方法的对比

| 方法 | 物理引导 | 扩散模型 | 显式运动 | 自监督 |
|------|---------|---------|---------|--------|
| AutoDPS, 2025 | ✅ | ✅ | ❌ 盲估计 | ✅ |
| Res-MoCoDiff, 2025 | ❌ | ✅ 残差引导 | ❌ | ❌ |
| PI-MoCoNet, 2025 | ✅ | ❌ | ❌ | ❌ |
| **我们的方法** | ✅ | ✅ 运动条件 | ✅ | ✅ |

## Novelty声明

> "首个将显式运动场预测作为扩散模型条件的MRI运动校正方法，实现可解释、可控的物理引导重建"

**差异化点**:
1. **可解释性**: 运动场 φ 可直接可视化
2. **可控性**: 可调整运动强度适应不同程度伪影
3. **端到端**: 联合优化运动估计和扩散重建

## 后续步骤

### 验证成功
1. 创建正式的 `docs/research_contract.md`
2. 扩展为完整实验 (fastMRI数据集、多对比度、消融实验)
3. 部署到4x4090进行完整训练

### 验证失败
考虑备选方向:
- **A**: 超快采样 (Consistency Model, 1-2步)
- **D**: 非刚性专用 (呼吸/心脏运动建模)
- **B2**: 纯物理方法 (无扩散模型, PI-MoCoNet路线)

## 参考

- [Res-MoCoDiff](https://pmc.ncbi.nlm.nih.gov/articles/PMC12083705/)
- [PI-MoCoNet Code](https://github.com/mosaf/pi-moconet)
- [DDPM Paper](https://arxiv.org/abs/2006.11239)

---

*Experiment created: 2026-03-26*
*Direction: B - Motion-Explicit Diffusion*
