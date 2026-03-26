# MRI 运动伪影校正研究 — Project Dashboard

## Pipeline Status

| Stage | Status | Notes |
|-------|--------|-------|
| **Phase 0: Setup** | ✅ | 研究简介已创建 |
| **Phase 1: 多方向并行探索** | 🔄 | 8个sub-direction同时探索 |
| **Phase 2: 方向收敛** | ⏸️ | 选择最佳方向 |
| **Phase 3: 实验实现** | ⏸️ | 代码 + 部署到4090 |
| **Phase 4: 审稿循环** | ⏸️ | 自动改进循环 |
| **Phase 5: 论文写作** | ⏸️ | 投稿级论文 |

## 当前活跃子方向

| # | 子方向 | Agent | 状态 | 负责人 |
|---|--------|-------|------|--------|
| 1 | k-space域运动校正 | Agent-1 | 🔄 探索中 | Claude+Codex |
| 2 | 图像域后处理校正 | Agent-2 | 🔄 探索中 | Claude+Codex |
| 3 | 物理引导联合重建 | Agent-3 | 🔄 探索中 | Claude+Codex |
| 4 | 自监督/无监督校正 | Agent-4 | 🔄 探索中 | Claude+Codex |
| 5 | 扩散模型运动估计 | Agent-5 | 🔄 探索中 | Claude+Codex |
| 6 | 多尺度/多分辨率方法 | Agent-6 | 🔄 探索中 | Claude+Codex |
| 7 | 特定器官运动建模 | Agent-7 | 🔄 探索中 | Claude+Codex |
| 8 | 实时/快速校正 | Agent-8 | 🔄 探索中 | Claude+Codex |

## 项目约束

### 计算资源
- **GPU**: 4x RTX 4090 (远程服务器)
- **部署方式**: 手动部署（非自动）
- **预算意识**: 本地仅做idea生成，不跑GPU实验

### 时间线
- **目标会议**: MICCAI / IPMI / MRM / TMI
- **截止日期**: 待定
- **当前阶段**: Phase 1 - 多方向并行探索

### 数据/工具
- **文献库**: Zotero (待配置)
- **本地PDF**: `papers/` 或 `literature/`
- **论文写作**: LaTeX模板 (MICCAI/MRM格式)

## 关键文件

| File | Purpose | Status |
|------|---------|--------|
| `QUICKSTART.md` | 快速启动指南 | ✅ |
| `RESEARCH_BRIEF.md` | 研究简介 | ✅ |
| `WORKFLOW.md` | 多Agent流程 | ✅ |
| `ZOTERO_SETUP.md` | Zotero配置指南 | ✅ |
| `sub-dirs/sub-*/` | 各子方向workspace | ✅ |
| `tools/` | 辅助脚本 | ✅ |
| `IDEA_REPORT.md` | 主报告汇总 | ⏸️ |
| `IDEA_CANDIDATES.md` | 候选方向 | ⏸️ |
| `docs/research_contract.md` | 最终选定方向 | ⏸️ |

## 启动命令速查

```bash
# Phase 1: 单方向探索（每个Agent执行）
/idea-discovery "MRI motion artifact correction - [子方向名称]" \\
    — AUTO_PROCEED: false \\
    — PILOT_MAX_HOURS: 0 \\
    — sources: zotero, web

# Phase 1.5: 快速验证（选定方向后）
/experiment-bridge — code review: true

# Phase 2: 深度审稿循环
/auto-review-loop "[选定方向]" — human checkpoint: true

# Phase 3: 论文写作
/paper-writing "NARRATIVE_REPORT.md" — venue: MICCAI
```

## 多Agent并行策略

### 第1周：发散探索
- 8个workspace同时运行
- 每个生成该子方向的文献调研 + 想法
- 输出: 8份 `IDEA_REPORT.md`

### 第2周：收敛决策
- 对比8个子方向的潜力
- 评估：新颖性、可行性、影响力
- 选择1-2个最有潜力的方向

### 第3周+：深度实现
- 为选定方向生成完整代码
- 手动部署到4x4090服务器
- 进入审稿循环

## Zotero集成

### 状态
- [ ] MCP服务器配置
- [ ] 文献集合检查
- [ ] 标注同步

### 配置路径
```bash
# 检查Zotero连接
mcp__zotero__list_collections

# 搜索MRI相关文献
mcp__zotero__search_items — query "MRI motion artifact"
```

详见: `ZOTERO_SETUP.md`

## 会议恢复

如果会话中断，按顺序读取：
1. `CLAUDE.md` (本文件) - 30秒定位
2. `docs/research_contract.md` - 当前方向上下文
3. `findings.md` - 最近发现
4. `EXPERIMENT_LOG.md` - 实验记录

## 下一步行动

1. **配置Zotero**: 按 `ZOTERO_SETUP.md` 配置文献库
2. **启动8个Agent**: 按 `WORKFLOW.md` 启动各子方向探索
3. **监控进度**: 定期检查各workspace的 `IDEA_REPORT.md`
4. **收敛决策**: 1周后选择最佳方向

## 联系人

- **研究者**: Hao003
- **分支**: `Hao003/mri-motion-artifact`
- **工作目录**: `/Users/ljh/conductor/workspaces/auto-claude-code-research-in-sleep/helsinki`
