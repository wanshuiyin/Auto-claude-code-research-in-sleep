# Research Brief: MRI 运动伪影校正

## Problem Statement

MRI (磁共振成像) 是一种重要的医学影像技术，但扫描时间长导致患者运动不可避免地引入运动伪影，严重影响图像质量和诊断准确性。传统运动校正方法依赖外部追踪设备或导航回波，增加了扫描复杂度和时间。

近年来，深度学习为回顾性运动校正提供了新思路，但现有方法仍存在关键局限：(1) 对复杂运动的建模能力不足；(2) 对未见运动模式的泛化性差；(3) 缺乏对校正过程的可解释性。如何设计鲁棒、高效、可解释的 MRI 运动校正方法仍是开放问题。

## Background

- **Field**: 医学影像处理 / 计算机视觉
- **Sub-area**: MRI 重建、运动校正、深度学习医学影像
- **Key papers I've read**:
  - Motion-correction using deep learning (通用框架)
  - k-space 域运动校正方法
  - 自监督/无监督 MRI 重建
- **What I already tried**: [待填写]
- **What didn't work**: [待填写]

## Constraints

- **Compute**: 4x RTX 4090 (远程服务器，需手动部署)
- **Timeline**: 4-6 months to MICCAI/IPMI/MRM
- **Target venue**: MICCAI / IPMI / MRM / TMI

## What I'm Looking For

- [x] New research direction from scratch
- [ ] Improvement on existing method: [待填写]
- [ ] Diagnostic study / analysis paper
- [ ] Other: [待填写]

## Domain Knowledge

### MRI 运动伪影的核心挑战：

1. **运动类型复杂**: 刚体运动(平移+旋转) + 非刚体运动(呼吸、心跳、肠道蠕动)
2. **数据获取困难**: 真实运动数据难以标注，依赖模拟数据
3. **临床约束严格**: 校正不能引入新的伪影，实时性要求

### 可能的研究切入点：

- **方向 A**: 基于扩散模型/流模型的运动参数估计
- **方向 B**: 自监督运动伪影检测与校正
- **方向 C**: 物理引导的神经网络(PINN)结合 MRI 物理模型
- **方向 D**: 大模型/多模态预训练用于 MRI 运动校正
- **方向 E**: 联邦学习场景下的 MRI 运动校正

## Non-Goals

- 不涉及 MRI 序列设计(纯软件/算法层面)
- 不追求实时性(允许离线校正)
- 暂不考虑多模态融合(CT/MRI)

## Existing Results (if any)

[待填写]
