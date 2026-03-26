# MRI 运动伪影校正 — 多 Agent 并行研究

> 利用 ARIS (Auto-claude-code-research-in-sleep) 框架，8 个 Agent 同时探索 MRI 运动伪影校正的不同方向，1 周内收敛到最有潜力的研究方向。

---

## 项目结构

```
.
├── CLAUDE.md                    # 项目仪表盘 - 查看当前状态
├── RESEARCH_BRIEF.md            # 主研究简介
├── WORKFLOW.md                  # 详细工作流程文档
├── ZOTERO_SETUP.md             # Zotero 文献库配置指南
├── QUICKSTART.md               # 快速启动指南 (本文档)
├── sub-dirs/                   # 8 个子方向工作目录
│   ├── sub-1-kspace/           # Agent 1: k-space 域校正
│   ├── sub-2-image/            # Agent 2: 图像域后处理
│   ├── sub-3-pinn/             # Agent 3: 物理引导神经网络
│   ├── sub-4-selfsuper/        # Agent 4: 自监督校正
│   ├── sub-5-diffusion/        # Agent 5: 扩散模型
│   ├── sub-6-multiscale/       # Agent 6: 多尺度方法
│   ├── sub-7-brain/            # Agent 7: 脑部专用
│   └── sub-8-realtime/         # Agent 8: 实时快速
├── idea-reports/               # 各 Agent 产出汇总
├── docs/                       # 研究合约等文档
└── tools/                      # 辅助脚本
    ├── launch_agents.sh        # 批量启动脚本
    ├── check_status.sh         # 状态监控
    └── compare_directions.py   # 方向对比分析
```

---

## 快速启动 (5 分钟)

### Step 0: 准备

确保已配置 Claude Code 和 Codex MCP：

```bash
# 安装 Codex MCP（作为审查者）
npm install -g @openai/codex
codex setup  # 设置 model = "gpt-5.4"
claude mcp add codex -s user -- codex mcp-server

# 验证配置
claude mcp list  # 应显示 codex
```

### Step 1: 配置 Zotero (可选但推荐)

如果你有 Zotero 文献库：

```bash
# 阅读配置指南
cat ZOTERO_SETUP.md

# 快速测试
mcp__zotero__search_items — query "MRI motion" — limit 5
```

无 Zotero 也能正常工作，只是会缺失你的历史收藏。

### Step 2: 启动第一批次 (4 个 Agent)

在 Conductor 中创建 4 个新 workspace，分别进入 4 个子目录：

```bash
# Workspace 1
cd sub-dirs/sub-1-kspace
claude
> /idea-discovery "MRI motion artifact correction in k-space domain" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web

# Workspace 2
cd sub-dirs/sub-2-image
claude
> /idea-discovery "MRI motion artifact correction in image domain" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web

# Workspace 3
cd sub-dirs/sub-3-pinn
claude
> /idea-discovery "Physics-informed neural networks for MRI motion correction" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web

# Workspace 4
cd sub-dirs/sub-4-selfsuper
claude
> /idea-discovery "Self-supervised MRI motion artifact correction" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web
```

### Step 3: 监控进度

在新 terminal 中运行：

```bash
./tools/check_status.sh
```

输出示例：
```
k-space Domain:       ⏳ READY (waiting for start)
Image Domain:         🔄 IN PROGRESS (IDEA_REPORT exists)
PINN:                 ✅ COMPLETE (has recommendation)
Self-Supervised:      ⬜ NOT STARTED
```

### Step 4: 启动第二批次

第一批运行稳定后，启动剩余 4 个：

```bash
# Workspaces 5-8 for sub-5-diffusion, sub-6-multiscale, sub-7-brain, sub-8-realtime
```

命令模板：
```bash
cd sub-dirs/sub-{N}-{name}
claude
> /idea-discovery "[方向描述]" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web
```

---

## 时间线

| 阶段 | 时间 | 任务 |
|------|------|------|
| **发散探索** | Week 1 | 8 个 Agent 并行运行 `/idea-discovery` |
| **收敛决策** | Week 2 | 对比 8 个方向，选择 1-2 个最有潜力的 |
| **深度实现** | Week 3+ | 为选定方向生成代码，部署到 4x4090 |
| **审稿循环** | Week 4-6 | `/auto-review-loop` 改进直到投稿就绪 |
| **论文写作** | Week 7-8 | `/paper-writing` 生成 MICCAI 投稿 |

---

## 8 个探索方向

| # | 方向 | 核心问题 | 技术关键词 |
|---|------|----------|-----------|
| 1 | **k-space 域校正** | 直接在 k-space 学习运动参数 | navigator-free, end-to-end |
| 2 | **图像域后处理** | 将伪影图像恢复为干净图像 | post-processing, lightweight |
| 3 | **物理引导网络** | MRI 物理模型嵌入神经网络 | PINN, differentiable physics |
| 4 | **自监督校正** | 无需配对数据学习 | blind correction, no ground truth |
| 5 | **扩散模型** | 利用生成先验高质量校正 | diffusion, score-based |
| 6 | **多尺度方法** | 不同分辨率处理不同运动 | hierarchical, coarse-to-fine |
| 7 | **脑部专用** | 利用脑部刚性约束 | brain MRI, rigid-body |
| 8 | **实时快速** | 临床可部署的轻量级方法 | efficient, edge deployment |

---

## 常用命令速查

### 启动探索
```bash
/idea-discovery "[方向]" — AUTO_PROCEED: false — PILOT_MAX_HOURS: 0 — sources: zotero, web
```

### 生成实验代码
```bash
/experiment-bridge — code review: true
```

### 审稿循环
```bash
/auto-review-loop "[选定方向]" — human checkpoint: true
```

### 论文写作
```bash
/paper-writing "NARRATIVE_REPORT.md" — venue: MICCAI
```

---

## 资源约束

| 资源 | 配置 |
|------|------|
| **GPU** | 4x RTX 4090 (远程服务器，手动部署) |
| **本地** | 仅做 idea 生成，不跑 GPU 实验 |
| **目标会议** | MICCAI / IPMI / MRM / TMI |
| **时间线** | 4-6 个月 |

---

## 监控与汇总

### 检查所有 Agent 状态
```bash
./tools/check_status.sh
```

### 对比各方向并生成排名
```bash
python3 tools/compare_directions.py
# 输出: IDEA_CANDIDATES.md
```

### 收集所有 IDEA_REPORT
```bash
for d in sub-dirs/*/; do
    cp "$d/IDEA_REPORT.md" "idea-reports/$(basename $d)_report.md" 2>/dev/null
done
```

---

## 关键文件

| 文件 | 用途 | 更新时机 |
|------|------|----------|
| `CLAUDE.md` | 项目仪表盘 | 手动更新状态 |
| `IDEA_REPORT.md` | Agent 产出 | `/idea-discovery` 完成 |
| `IDEA_CANDIDATES.md` | 方向排名 | `compare_directions.py` 生成 |
| `docs/research_contract.md` | 最终选定方向 | Week 2 决策后 |
| `refine-logs/EXPERIMENT_PLAN.md` | 实验计划 | `/research-refine-pipeline` 后 |
| `AUTO_REVIEW.md` | 审稿循环记录 | `/auto-review-loop` 后 |

---

## 故障排除

### Agent 运行缓慢
- `/idea-discovery` 通常需要 30-60 分钟
- 文献调研阶段较慢，正常现象
- 如超过 2 小时无输出，检查网络连接

### Zotero 连接失败
- 跳过 Zotero，仅用 web 搜索：
```bash
/idea-discovery "..." — sources: web
```

### 存储空间不足
- arxiv 下载可选：
```bash
/idea-discovery "..." — arxiv download: false
```

### 想暂停某个 Agent
- 直接关闭该 workspace
- 进度保存在 `IDEA_REPORT.md` 中
- 重新打开会继续

---

## 下一步

1. **配置 Codex MCP** (如无)
2. **可选：配置 Zotero**
3. **启动第一批 4 个 Agent**
4. **运行 `./tools/check_status.sh` 监控**
5. **第一批稳定后启动第二批**

---

## 文档索引

| 文档 | 内容 |
|------|------|
| `CLAUDE.md` | 项目仪表盘，查看当前状态 |
| `WORKFLOW.md` | 详细工作流程，8 个方向定义 |
| `ZOTERO_SETUP.md` | Zotero 配置步骤 |
| `RESEARCH_BRIEF.md` | 主研究简介 |
| `QUICKSTART.md` | 本文档 |

---

**祝你研究顺利！有问题查阅相应文档或检查 Agent 输出。**
