# 启动3个新Workspace的配置指南

## 需要创建的3个Workspace

### Workspace 1: Multi-Scale Motion Correction
```bash
# 启动命令
/idea-discovery "MRI motion artifact correction - Multi-scale hierarchical motion correction" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出文件位置**: `sub-dirs/sub-6-multiscale/IDEA_REPORT.md`

**关键研究问题**:
- 如何分层处理global/regional/fine-scale运动？
- Coarse-to-fine vs Parallel multi-scale哪个更好？
- 如何分配计算资源到不同尺度？

---

### Workspace 2: Brain-Specific Motion Correction
```bash
# 启动命令
/idea-discovery "MRI motion artifact correction - Brain-specific motion correction leveraging rigid-body constraints" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出文件位置**: `sub-dirs/sub-7-brain/IDEA_REPORT.md`

**关键研究问题**:
- 如何利用脑部刚体约束（6DOF）简化问题？
- 如何处理CSF脉动等脑特有artifact？
- 有哪些公开脑数据集可用（ABCD, UK Biobank, HCP）？

---

### Workspace 3: Real-time Lightweight Correction
```bash
# 启动命令
/idea-discovery "MRI motion artifact correction - Real-time lightweight motion correction for clinical deployment" \
    --AUTO_PROCEED: false \
    --PILOT_MAX_HOURS: 0 \
    --sources: zotero, web
```

**输出文件位置**: `sub-dirs/sub-8-realtime/IDEA_REPORT.md`

**关键研究问题**:
- 如何设计<100ms的轻量级网络？
- 知识蒸馏/模型压缩在运动校正中的效果？
- 如何在速度和精度之间找到最佳平衡？

---

## PR工作流程

### 1. 每个Agent完成探索后
- 生成 `IDEA_REPORT.md`
- 创建新branch: `feat/idea-{sub-number}-{direction}`
- 提交PR到 `Hao003/mri-motion-artifact` 分支

### 2. PR标题格式
```
[IDEA] Sub-6: Multi-scale hierarchical motion correction
[IDEA] Sub-7: Brain-specific motion correction
[IDEA] Sub-8: Real-time lightweight motion correction
```

### 3. 合并后综合
等3个PR都合并后，在当前workspace运行：

```bash
# 拉取最新代码
git pull origin Hao003/mri-motion-artifact

# 读取3个新的IDEA_REPORT
sub-dirs/sub-6-multiscale/IDEA_REPORT.md
sub-dirs/sub-7-brain/IDEA_REPORT.md
sub-dirs/sub-8-realtime/IDEA_REPORT.md
```

然后我可以帮你对比评估，选出第二个可行idea。

---

## 已有方向的参考

已有的5个方向报告在：
- `sub-dirs/sub-1-kspace/IDEA_REPORT.md`
- `sub-dirs/sub-2-image/IDEA_REPORT.md`
- `sub-dirs/sub-3-pinn/IDEA_REPORT.md` (需要补充ideas)
- `sub-dirs/sub-4-selfsuper/IDEA_REPORT.md`
- `sub-dirs/sub-5-diffusion/IDEA_REPORT.md` (已有可行idea)

可以让新Agent参考这些报告，避免重复。
