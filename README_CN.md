# ⚔️ Auto-claude-code-research-in-sleep (ARIS)

[English](README.md) | 中文版

![Hero](docs/hero_combined.svg)

![分数曲线](docs/auto_review_score_curve.png)

> 🌙 **让 Claude Code 在你睡觉时做科研。** 醒来发现论文已被打分、弱点已被定位、实验已跑完、叙事已重写——全自动。

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主 ML 科研工作流。核心机制是**跨模型协作**——Claude Code 负责执行（读文件、写代码、跑实验、收结果），外部 LLM（通过 [Codex MCP](https://github.com/openai/codex)）负责评审（打分、找弱点、建议修复）。两个模型互不评自己的作业，形成真正的反馈循环。

## 📈 真实运行效果

某 ML 研究项目上的 4 轮自动循环，从 borderline reject 到可投稿：

| 轮次 | 分数 | 发生了什么 |
|------|------|-----------|
| 初始 | 5.0/10 | Borderline reject |
| 第 1 轮 | 6.5/10 | 补了标准指标，发现指标脱钩 |
| 第 2 轮 | 6.8/10 | 核心声明不可复现，转换叙事 |
| 第 3 轮 | 7.0/10 | 大规模 seed 研究推翻了主要改善声明 |
| 第 4 轮 | **7.5/10** ✅ | 诊断证据确立，**可以投稿** |

循环自主跑了 **20+ 个 GPU 实验**，重写了论文叙事框架，杀掉了经不住检验的声明——全程无人干预。

## 💡 自动找 Idea（新功能）

还没有具体 idea？给一个研究方向就行——`/idea-creator` 搞定剩下的：

1. 📚 **调研**全景（最新论文、开放问题、反复出现的局限性）
2. 🧠 **头脑风暴** 8-12 个具体 idea（GPT-5.4 xhigh）
3. 🔍 **初筛**可行性、算力成本、快速查新
4. 🛡️ **深度验证** top idea（完整查新 + devil's advocate review）
5. 🧪 **并行 pilot 实验**（top 2-3 个 idea 分别上不同 GPU，30 分钟 - 2 小时）
6. 🏆 **按实验信号排序**——有正信号的 idea 排前面

输出 `IDEA_REPORT.md`：含假设、pilot 结果、审稿人可能的质疑、建议执行顺序。失败的 idea 也记录在案，避免重复踩坑。

---

## 🔄 工作流

所有 Skills 组成完整科研流水线。两个工作流可以单独使用，也可以串联：

- **探索新方向（比如写 survey）？** 从工作流 1 开始（找 idea）
- **已有 idea + 初步方案？** 直接用工作流 2（自动 review 循环）
- **全流程？** 工作流 1 → 工作流 2，从文献调研一路到投稿

> ⚠️ **重要提醒：** 这些工具加速科研，但不能替代你自己的思考。生成的 idea 一定要用你的领域知识审视，质疑其假设，最终决策权在你手上。最好的研究 = 人的洞察 + AI 的执行力，而不是全自动流水线。

### 完整流程 🚀

```
/research-lit → /idea-creator → /novelty-check → 实现 → /run-experiment → /auto-review-loop → 投稿
  (调研文献)      (找idea)       (查新验证)     (写代码)   (部署跑实验)     (自动改到能投)     (搞定!)
  ├──── 工作流 1：找 Idea ────┤                 ├──────── 工作流 2：自动循环 ────────┤
```

### 工作流 1：文献调研与找 Idea 🔍

> "这个领域最新进展是什么？哪里有 gap？"

**涉及 Skills：** `research-lit` + `idea-creator` + `novelty-check` + `research-review`

```
1. /research-lit "discrete diffusion models"    ← 搜论文，整理全景
2. /idea-creator "DLLMs post training"     ← 自动生成 8-12 个 idea，筛选排序
3. 选 top 2-3 个 idea
4. /novelty-check "top idea"                     ← 查新：有没有人做过？
5. /research-review "top idea"                   ← 让外部 LLM 批判你的想法
6. 实现 → /run-experiment → /auto-review-loop    ← 闭环！
```

📝 **博客：** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

### 工作流 2：自动科研循环 🔁（睡一觉醒来看结果）

> "帮我 review 论文，修复问题，循环到通过为止。"

**涉及 Skills：** `auto-review-loop` + `research-review` + `novelty-check` + `run-experiment` + `analyze-results` + `monitor-experiment`

```
外部 LLM 评审 → Claude Code 实现修复 → /run-experiment 部署 → 收结果 → 再评审 → 循环
                ↑ 需要新方向时自动 /novelty-check 查新
```

用法：
```
> /auto-review-loop 我的 diffusion model 论文
```

**🛡️ 关键安全机制：**

- 🔒 **MAX_ROUNDS = 4** — 防止无限循环；达到分数阈值时提前停止
- ⏱️ **> 4 GPU-hour 的实验自动跳过** — 不会启动超大实验，标记为"需人工跟进"
- 🧠 **优先改叙事而非跑新实验** — 同样能解决问题时，选择成本更低的路径
- 🪞 **不隐藏弱点** — 明确规则："不要隐藏弱点来骗高分"
- 🔧 **先修后审** — 必须实现修复后再重新 review，不能只承诺修

📝 **博客：** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

---

## 🧰 全部 Skills

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|-----------------|
| 💡 [`idea-creator`](skills/idea-creator/SKILL.md) | 给定研究方向，自动生成、筛选、排序研究 idea | 是 |
| 🔬 [`research-review`](skills/research-review/SKILL.md) | 单轮深度评审（外部 LLM，xhigh 推理） | 是 |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | 多轮自动 review→修复→再 review 循环（最多 4 轮） | 是 |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | 搜论文、分析相关工作、找研究空白 | 否 |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | 分析实验结果、统计、生成对比表 | 否 |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | 监控实验进度、收集结果 | 否 |
| 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | 查新：验证研究 idea 是否已有人做过 | 是 |
| 🚀 [`run-experiment`](skills/run-experiment/SKILL.md) | 部署实验到本地（MPS/CUDA）或远程 GPU 服务器 | 否 |
| 🎨 [`pixel-art`](skills/pixel-art/SKILL.md) | 生成像素风 SVG 插图，用于 README、文档或幻灯片 | 否 |

---

## ⚙️ 安装

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. （仅 review 类 skill 需要）安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```

### 安装 Skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep

# 安装全部 skills（全局可用）
cp -r skills/* ~/.claude/skills/

# 或者只安装特定 skill
cp -r skills/auto-review-loop ~/.claude/skills/
cp -r skills/research-lit ~/.claude/skills/
```

### 🌙 过夜自动运行的免确认配置（可选）

在 `.claude/settings.local.json` 中添加：

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__codex__codex-reply",
      "Write",
      "Edit",
      "Skill(auto-review-loop)"
    ]
  }
}
```

### 🖥️ GPU 服务器配置（自动跑实验用）

当 GPT-5.4 审稿说"需要补一个消融实验"或"加一个 baseline 对比"时，Claude Code 会自动写实验脚本并部署到你的 GPU 服务器。为此，Claude Code 需要知道你的服务器环境。

在项目的 `CLAUDE.md` 中添加服务器信息：

```markdown
## 远程服务器

- SSH：`ssh my-gpu-server`（密钥免密登录）
- GPU：4x A100
- Conda 环境：`research`（Python 3.10 + PyTorch）
- 激活：`eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- 代码目录：`/home/user/experiments/`
- 后台运行用 `screen`：`screen -dmS exp0 bash -c '...'`
```

Claude Code 读到这些就知道怎么 SSH、激活环境、启动实验。GPT-5.4（审稿人）只决定**做什么实验**——Claude Code 根据你的 `CLAUDE.md` 搞定**怎么跑**。

**没有 GPU 服务器？** Review 和改写功能不受影响，只有需要跑实验的修复会被跳过（标记为"需人工跟进"）。

## 🏗️ 工作原理

```
┌─────────────────────────────────────────────────┐
│                 Claude Code                      │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │  读取     │    │  写代码   │    │  SSH 到   │   │
│  │  项目上下文│───▶│  和脚本   │───▶│  GPU 服务器│   │
│  └──────────┘    └──────────┘    └──────────┘   │
│       │                               │          │
│       ▼                               ▼          │
│  ┌──────────────────────────────────────────┐    │
│  │         Codex MCP（外部 LLM）             │    │
│  │                                          │    │
│  │  第 1 轮："5/10 分，问题：..."             │    │
│  │  第 2 轮："6.5 分，好多了，但是..."         │    │
│  │  第 3 轮："7.0 分，差不多了..."             │    │
│  │  第 4 轮："7.5 分，可以投了" ✅             │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

核心设计：**Claude Code 负责执行**（读文件、写代码、跑实验、收结果），**外部 LLM 负责评审**（打分、找弱点、建议修复）。两个模型各司其职，互不评自己的作业，形成真正的反馈循环。

## 🎛️ 自定义

Skills 就是普通的 Markdown 文件，fork 后随意改：

- **`MAX_ROUNDS`** — 增加轮数上限（默认 4）
- **`POSITIVE_THRESHOLD`** — 调整停止条件的分数阈值
- **优先级规则** — 调整算力限制、跳过策略
- **Prompt 模板** — 定制评审人格和评估标准
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具

## 📋 Roadmap

- [ ] **GLM-5（执行者）+ Minimax-2.5（评审者）** — 与 Claude Code + Codex 平行的跨模型组合
- [ ] 更多执行者 × 评审者组合（Gemini、DeepSeek 等）

## 💬 交流群

欢迎加入微信群，交流 Claude Code + AI 科研工作流：

<img src="docs/wechat_group.jpg" alt="微信交流群二维码" width="300">

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260312)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## License

MIT
