# Auto-claude-code-research-in-sleep (ARIS ⚔️)

![Hero](docs/hero_combined.svg)

[English](README.md) | 中文版

![分数曲线](docs/auto_review_score_curve.png)

> 🌙 **让 Claude Code 在你睡觉时做科研。** 醒来发现论文已被打分、弱点已被定位、实验已跑完、叙事已重写——全自动。

[![Featured in awesome-agent-skills](https://img.shields.io/badge/Featured%20in-awesome--agent--skills-blue?style=flat&logo=github)](https://github.com/VoltAgent/awesome-agent-skills) · [![AI Digital Crew - Project of the Day](https://img.shields.io/badge/AI%20Digital%20Crew-Project%20of%20the%20Day%20(2026.03.14)-orange?style=flat)](https://aidigitalcrew.com) · [💬 加入交流群](#-交流群)

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主 ML 科研工作流。核心机制是**跨模型协作**——Claude Code 负责执行（读文件、写代码、跑实验、收结果），外部 LLM（通过 [Codex MCP](https://github.com/openai/codex)）负责评审（打分、找弱点、建议修复）。两个模型互不评自己的作业，形成真正的反馈循环。🔀 **也支持[替代模型组合](#-替代模型组合)（如 GLM + GPT、GLM + MiniMax）——无需 Claude API。**

> 💭 **为什么不用单模型自我博弈？** 用 Claude Code 的 subagent 或 agent team 同时做执行和审稿在技术上可行，但容易陷入**局部最优**——同一个模型审自己的输出会产生盲区。
>
> *类比 bandit 问题：单模型自审是 stochastic bandit（噪声可预测），跨模型审稿则是 adversarial bandit（审稿者会主动探测执行者未预料的弱点）——而 adversarial bandit 天然更难被 game。*
>
> 💭 **为什么是两个模型而不是更多？** 两个是打破自我博弈盲区的最小配置，且双人博弈收敛到 Nash 均衡的效率远高于多人博弈。增加更多审稿者只会增加 API 开销和协调成本，边际收益递减——最大的提升来自 1→2，而非 2→4。
>
> Claude Code 的优势是快速丝滑的执行，Codex（GPT-5.4 xhigh）虽然慢但审稿更严谨深入。两者**速度 × 严谨**的互补特性，比单模型自我对话效果更好。

## 📢 最近更新

- **2026-03-14** — 📱 [飞书集成](#-飞书lark-集成可选)：三种模式（关闭/推送/交互），实验完成、review 出分、checkpoint 审批均可手机收通知
- **2026-03-13** — 🛑 Human-in-the-loop：所有工作流支持 `AUTO_PROCEED` 检查点，全自动或逐步审批
- **2026-03-12** — 🔗 [Zotero](#-zotero-集成可选) + [Obsidian](#-obsidian-集成可选) + 本地 PDF + arXiv/Scholar：多源文献检索 + 跨模型新颖性验证
- **2026-03-11** — 🚀 三大工作流端到端贯通：一句 prompt → 三大会风格论文。`/research-pipeline` 自动串联 idea 发现 → 自动 review → 论文写作
- **2026-03-09** — 📝 `/paper-writing` 工作流：叙事报告 → 大纲 → 图表 → LaTeX → PDF → 两轮自动改进（4/10 → 8.5/10）

## 🚀 快速开始

```bash
# 1. 安装 skills
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cp -r Auto-claude-code-research-in-sleep/skills/* ~/.claude/skills/

# 2. 配置 Codex MCP（review 类 skill 需要）
npm install -g @openai/codex
codex setup                    # 提示选模型时选 gpt-5.4
claude mcp add codex -s user -- codex mcp-server

# 3. 在 Claude Code 中使用
claude
> /idea-discovery "你的研究方向"              # 工作流 1 — 方向要具体！不要 "NLP"，要 "离散扩散语言模型的 factorized gap"
> /auto-review-loop                          # 工作流 2：审稿 → 修复 → 再审，一夜完成
> /paper-writing "NARRATIVE_REPORT.md"       # 工作流 3：研究叙事 → 精修 PDF
> /research-pipeline "你的研究方向"            # 全流程：工作流 1 → 2 → 3 端到端
```

> **提示：** 工作流默认自动继续（`AUTO_PROCEED=true`）。如果想在每个关键步骤前暂停审核（比如确认 idea 再花 GPU），在命令中覆盖：
> ```
> /research-pipeline "你的课题" — AUTO_PROCEED: false
> ```

> **重要：** Codex MCP 使用的模型取决于 `~/.codex/config.toml`，而非 skill 文件中的设置。请确认其中写的是 `model = "gpt-5.4"`（推荐）。其他可用模型：`gpt-5.3-codex`、`gpt-5.2-codex`、`o3`。运行 `codex setup` 或直接编辑该文件。

详见[完整安装指南](#%EF%B8%8F-安装)和[替代模型组合](#-替代模型组合)（无需 Claude/OpenAI API）。

## ✨ 功能亮点

- 📊 **19 个可组合 skill** — 自由混搭，或串联为完整流水线（`/idea-discovery`、`/auto-review-loop`、`/paper-writing`、`/research-pipeline`）
- 🔍 **文献 & 查新** — 多源论文搜索（**[Zotero](#-zotero-集成可选)** + **[Obsidian](#-obsidian-集成可选)** + **本地 PDF** + arXiv/Scholar）+ 跨模型查新验证
- 💡 **Idea 发现** — 文献调研 → 头脑风暴 8-12 个 idea → 查新 → GPU pilot 实验 → 排名报告
- 🔄 **自动 review 循环** — 4 轮自主审稿，一夜从 5/10 提升到 7.5/10，自动跑 20+ 组 GPU 实验
- 📝 **论文写作** — 研究叙事 → 大纲 → 图表 → LaTeX → PDF → 自动审稿（4/10 → 8.5/10），一条命令
- 🤖 **跨模型协作** — Claude Code 执行，GPT-5.4 xhigh 审稿。对抗式而非自我博弈
- 📝 **Peer Review** — 以审稿人视角审阅他人论文，结构化打分 + meta-review
- 🖥️ **GPU 部署** — 自动 rsync、screen 会话、多 GPU 并行实验、实时监控
- 🔀 **灵活模型** — 默认 Claude × GPT-5.4，也支持 [GLM + GPT、GLM + MiniMax](#-替代模型组合)——无需 Claude API
- 🛑 **Human-in-the-loop** — 关键决策点可配置检查点。`AUTO_PROCEED=true` 全自动，`false` 逐步审批
- 📱 **[飞书通知](#-飞书lark-集成可选)** — 三种模式：**关闭（默认，强烈建议大多数用户保持关闭）**、仅推送（webhook，手机收通知）、双向交互（在飞书里审批/回复）。未配置时零影响

  <details>
  <summary>预览：推送卡片（群聊）&amp; 交互对话（私聊）</summary>

  **仅推送** — 群聊彩色卡片（实验完成、checkpoint、报错、流水线结束）：

  <img src="assets/feishu_push.png" width="700" />

  **双向交互** — 与 Claude Code 私聊（审批/拒绝、自定义指令）：

  <img src="assets/feishu_interactive.jpg" width="700" />

  </details>

- 🧩 **可扩展** — 欢迎贡献领域专用 skill！添加一个 `SKILL.md` 即可提 PR。参见[社区 skills](#-全部-skills)，如 [`dse-loop`](skills/dse-loop/SKILL.md)（体系结构/EDA）

---

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

## 🧩 Awesome 社区 Skills & 扩展

社区贡献的领域专用 skills 和外部项目。欢迎 PR——添加 `skills/your-skill/SKILL.md` 即可！

| 类型 | 名称 | 领域 | 描述 | Codex MCP？ |
|------|------|------|------|-----------|
| Skill | 🏗️ [`dse-loop`](skills/dse-loop/SKILL.md) | 体系结构 / EDA | 自动设计空间探索——迭代运行、分析、调参（gem5、Yosys 等）。适用于任何有可调参数的领域 | 否 |
| Skill | 🤖 [`idea-discovery-robot`](skills/idea-discovery-robot/SKILL.md) | 机器人 / 具身智能 | 工作流 1 适配版——按 embodiment、benchmark、sim2real 路径和安全约束生成、筛选 idea | 是 |
| External | 🔬 [Auto-Research-Refine](https://github.com/zjYao36/Auto-Research-Refine) | 通用 | 把模糊 idea 变成可执行研究方案——衔接 `/idea-discovery` 和 `/auto-review-loop`。Claude + GPT-5.4 迭代精炼 | 是 |

> **⭐ 推荐：[Auto-Research-Refine](https://github.com/zjYao36/Auto-Research-Refine)** — 填补了"研究什么"到"怎么研究"之间的空白。接入 ARIS 流水线：
>
> `/idea-discovery` → **`/research-refine`** → `/auto-review-loop` → `/paper-writing`
>
> 模糊想法 → 排名后的 idea → **可执行研究方案** → 精修论文

## 🔄 工作流

所有 Skills 组成完整科研流水线。三个工作流可以单独使用，也可以串联：

- **探索新方向（比如写 survey）？** 从工作流 1 开始 → `/idea-discovery`
- **已有 idea + 初步方案？** 直接用工作流 2 → `/auto-review-loop`
- **准备写论文了？** 工作流 3 → `/paper-writing`（或分步：`/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile` → `/auto-paper-improvement-loop`）
- **全流程？** 工作流 1 → 工作流 2 → 工作流 3 → `/research-pipeline`，从文献调研一路到投稿

> ⚠️ **重要提醒：** 这些工具加速科研，但不能替代你自己的思考。生成的 idea 一定要用你的领域知识审视，质疑其假设，最终决策权在你手上。最好的研究 = 人的洞察 + AI 的执行力，而不是全自动流水线。

### 完整流程 🚀

```
/research-lit → /idea-creator → /novelty-check → 实现 → /run-experiment → /auto-review-loop → /paper-plan → /paper-figure → /paper-write → /auto-paper-improvement-loop → 投稿
  (调研文献)      (找idea)       (查新验证)     (写代码)   (部署跑实验)     (自动改到能投)      (大纲)        (作图)        (LaTeX+PDF)     (审稿×2 + 格式检查)     (搞定!)
  ├──── 工作流 1：找 Idea ────┤                 ├──── 工作流 2：自动循环 ────┤   ├───────────────── 工作流 3：论文写作 ─────────────────────┤
```

📝 **博客：** [梦中科研全流程开源](http://xhslink.com/o/2iV33fYoc7Q)

### 工作流 1：文献调研与找 Idea 🔍

> "这个领域最新进展是什么？哪里有 gap？"

还没有具体 idea？给一个研究方向就行——`/idea-creator` 搞定剩下的：

1. 📚 **调研**全景（最新论文、开放问题、反复出现的局限性）
2. 🧠 **头脑风暴** 8-12 个具体 idea（GPT-5.4 xhigh）
3. 🔍 **初筛**可行性、算力成本、快速查新
4. 🛡️ **深度验证** top idea（完整查新 + devil's advocate review）
5. 🧪 **并行 pilot 实验**（top 2-3 个 idea 分别上不同 GPU，30 分钟 - 2 小时）
6. 🏆 **按实验信号排序**——有正信号的 idea 排前面

输出 `IDEA_REPORT.md`：含假设、pilot 结果、审稿人可能的质疑、建议执行顺序。失败的 idea 也记录在案，避免重复踩坑。

**涉及 Skills：** `research-lit` + `idea-creator` + `novelty-check` + `research-review`

> 💡 **一键调用：** `/idea-discovery "你的研究方向"` 自动跑完整个工作流 1。

> 🔄 **人在回路中：** 每个阶段都会展示结果等你反馈。不满意？告诉它哪里不对——调整 prompt 重新生成。信任默认选择？它会自动带着最优方案继续。你决定参与多深。

> ⚙️ Pilot 实验预算（最大时长、超时、GPU 总预算）均可配置——见[自定义](#%EF%B8%8F-自定义)。

```
1. /research-lit "discrete diffusion models"    ← Zotero→Obsidian→本地→网络，整理全景
   /research-lit "topic" — sources: zotero, web  ← 或指定只搜部分源
   /research-lit "topic" — arxiv download: true   ← 同时下载最相关的 arXiv PDF
   /arxiv "attention mechanism" — download         ← 独立 arXiv 搜索+下载
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

> 💡 **一键调用：** `/auto-review-loop "你的论文主题"` 自动跑完整个工作流 2。

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
- 💾 **上下文压缩恢复** — 每轮结束后持久化状态到 `REVIEW_STATE.json`。如果上下文窗口满了触发自动 compact，工作流会从状态文件恢复断点继续——无需人工干预

> ⚙️ MAX_ROUNDS、分数阈值、GPU 限制均可配置——见[自定义](#%EF%B8%8F-自定义)。

📝 **博客：** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### 工作流 3：论文写作流水线 📝

> "把我的研究报告变成可投稿的 PDF。" 需要本地 LaTeX 环境——见[前置条件](#前置条件)。

**涉及 Skills：** `paper-plan` + `paper-figure` + `paper-write` + `paper-compile` + `auto-paper-improvement-loop`

> **一键调用：** `/paper-writing "NARRATIVE_REPORT.md"` 自动跑完整个工作流 3。

**输入：** 一份 `NARRATIVE_REPORT.md`，描述研究内容：声明、实验、结果、图表。叙事越详细（尤其是图表描述和定量结果），输出越好。

**输出：** 一个可投稿的 `paper/` 目录，含 LaTeX 源码、干净的 `.bib`（仅含实际引用）、编译好的 PDF。

```
NARRATIVE_REPORT.md ──► /paper-plan ──► /paper-figure ──► /paper-write ──► /paper-compile
    (研究叙事)          (大纲+矩阵)     (图表+LaTeX)      (逐节LaTeX)      (编译PDF)
```

```
典型流程：
1. 写 NARRATIVE_REPORT.md（来自工作流 2 的结果）
2. /paper-plan — 生成 claims-evidence 矩阵 + 分节计划
3. /paper-figure — 生成对比表、训练曲线等图表
4. /paper-write — 逐 section 生成 LaTeX（含 bib 清理、de-AI 打磨）
5. /paper-compile — 编译 PDF、修复错误、页数验证
6. /auto-paper-improvement-loop — 内容审稿 ×2 + 格式合规检查
```

**核心特性：**
- 📐 **Claims-Evidence 矩阵** — 每个声明映射到证据，每个实验支撑一个声明
- 📊 **自动图表生成** — 从 JSON 数据生成折线图、柱状图、对比表
- 🧹 **Bib 自动清理** — 过滤未引用条目（实测 948→215 行）
- 📄 **灵活节数** — 5-8 节按论文类型选择（理论论文常需 7 节）
- 🔍 **GPT-5.4 审稿** — 每步可选外部 LLM 审查
- ✂️ **De-AI 打磨** — 去除 AI 写作痕迹（delve、pivotal、landscape…）
- 🎯 **精确页数验证** — 基于 `pdftotext` 定位 Conclusion 结束位置

> ⚠️ **`/paper-figure` 能做什么、不能做什么：** 能自动生成**数据驱动的图表**（训练曲线、柱状图、热力图）和 **LaTeX 对比表**（从 JSON/CSV 数据）。**不能**生成架构图、流程图、模型示意图、生成样本网格——这些需要手动创建（draw.io、Figma、TikZ 等），放到 `figures/` 目录后再跑 `/paper-write`。一篇典型 ML 论文中，约 60% 的图表可自动生成，约 40% 需手动制作。

**端到端实测：** 从一份 NARRATIVE_REPORT.md 生成了一篇 9 页 ICLR 2026 理论论文（7 节、29 条引用、4 张图、2 个对比表）——零编译错误、零 undefined reference。

#### 论文自动润色循环 ✨

工作流 3 生成论文后，`/auto-paper-improvement-loop` 自动跑 2 轮 GPT-5.4 xhigh 内容审稿 → 修复 → 重编译，外加一轮格式合规检查，将粗稿自动提升到可投稿质量。

**分数变化（实测 — ICLR 2026 理论论文）：**

| 轮次 | 分数 | 关键改动 |
|------|------|---------|
| Round 0 | 4/10（内容） | 基线生成论文 |
| Round 1 | 6/10（内容） | 修复假设、软化声明、重命名符号 |
| Round 2 | 7/10（内容） | 添加合成验证、强化局限性 |
| Round 3 | 5→8.5/10（格式） | 移除多余图、拆附录、压缩结论、修 overfull hbox |

**最终：正文 8 页（ICLR 限 9 页），0 个 overfull hbox，格式合规。** 3 轮共涨 4.5 分。

<details>
<summary>Round 1 修复细节（6 项）</summary>

1. **CRITICAL — 假设与模型矛盾**：有界性假设与模型的分布族不一致。改为与尾部兼容的假设，并添加正式截断桥接。
2. **CRITICAL — 理论-实验 gap**：理论假设理想化编码器，实验用学习的非线性编码器。软化 "validate" → "demonstrate practical relevance"，添加明确声明。
3. **MAJOR — 缺定量指标**：添加参数量对比表（latent vs total），诚实计入系统总开销。
4. **MAJOR — 定理不自包含**：添加 "Interpretation" 段落，显式列出所有依赖。
5. **MAJOR — 新颖性声明过宽**：将宽泛的 "首个收敛保证" 精确限定到具体成立条件。
6. **MAJOR — 符号冲突**：重命名一个与另一关键变量冲突的符号。添加 Notation 段。

</details>

<details>
<summary>Round 2 修复细节（4 项）</summary>

1. **MAJOR — 缺理论验证实验**：添加合成验证子节，在受控条件下直接测试两个核心理论预测。
2. **MAJOR — 声明仍然过强**：将强等价声明替换为适当的 hedge 语言，全文统一。
3. **MAJOR — 非正式理论论证**：将非正式论证正式化为一个命题，给出显式误差界。
4. **MINOR — 局限性不足**：扩展为显式列出所有假设，承认缺少标准评估指标。

</details>

<details>
<summary>Round 3 格式修复（8 项）</summary>

1. 移除多余的 hero figure（省 ~0.7 页）
2. 压缩结论 15→9 行
3. 合成验证移至附录 A
4. 对比表格移至附录 B
5. 修复 overfull hbox (85pt)，用 `\resizebox`
6. 添加紧凑 float spacing（`\captionsetup`、`\textfloatsep`）
7. Introduction 中行内化居中问题块
8. 收紧 `itemize` 环境间距

</details>

---

## 🧰 全部 Skills

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|-----------------|
| 💡 [`idea-creator`](skills/idea-creator/SKILL.md) | 给定研究方向，自动生成、筛选、排序研究 idea | 是 |
| 🔬 [`research-review`](skills/research-review/SKILL.md) | 单轮深度评审（外部 LLM，xhigh 推理） | 是 |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | 多轮自动 review→修复→再 review 循环（最多 4 轮） | 是 |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | 搜索 [Zotero](#-zotero-集成可选) + [Obsidian](#-obsidian-集成可选) + 本地 PDF + [arXiv API](#arxiv-集成) + 网络，分析相关工作、找空白 | 否（可选：Zotero/Obsidian MCP） |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | 分析实验结果、统计、生成对比表 | 否 |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | 监控实验进度、收集结果 | 否 |
| 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | 查新：验证研究 idea 是否已有人做过 | 是 |
| 🚀 [`run-experiment`](skills/run-experiment/SKILL.md) | 部署实验到本地（MPS/CUDA）或远程 GPU 服务器 | 否 |
| 🎨 [`pixel-art`](skills/pixel-art/SKILL.md) | 生成像素风 SVG 插图，用于 README、文档或幻灯片 | 否 |
| 🔭 [`idea-discovery`](skills/idea-discovery/SKILL.md) | **工作流 1 全流程**：research-lit → idea-creator → novelty-check → research-review | 是 |
| 🏗️ [`research-pipeline`](skills/research-pipeline/SKILL.md) | **完整流水线**：工作流 1 → 实现 → 工作流 2 → 工作流 3，从方向到投稿 | 是 |
| 📐 [`paper-plan`](skills/paper-plan/SKILL.md) | 生成论文大纲：claims-evidence 矩阵、图表计划、引用规划 | 是 |
| 📊 [`paper-figure`](skills/paper-figure/SKILL.md) | 从实验数据生成出版级 matplotlib/seaborn 图表，含 LaTeX 插入代码 | 可选 |
| ✍️ [`paper-write`](skills/paper-write/SKILL.md) | 逐 section LaTeX 生成，支持 ICLR/NeurIPS/ICML 模板 | 是 |
| 🔨 [`paper-compile`](skills/paper-compile/SKILL.md) | 编译 LaTeX 为 PDF，自动修复错误，投稿就绪检查 | 否 |
| 🔄 [`auto-paper-improvement-loop`](skills/auto-paper-improvement-loop/SKILL.md) | 2 轮内容审稿 + 格式检查循环（4/10 → 8.5/10） | 是 |
| 📝 [`paper-writing`](skills/paper-writing/SKILL.md) | **工作流 3 全流程**：paper-plan → paper-figure → paper-write → paper-compile → auto-paper-improvement-loop | 是 |
| 📄 [`arxiv`](skills/arxiv/SKILL.md) | 搜索、下载、摘要 arXiv 论文。可独立使用或作为 `/research-lit` 的补充 | 否 |
| 📱 [`feishu-notify`](skills/feishu-notify/SKILL.md) | [飞书](#-飞书lark-集成可选)通知——推送（webhook）或双向交互。默认关闭 | 否 |

---

## ⚙️ 安装

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. （仅 review 类 skill 需要）安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. （仅工作流 3：论文写作需要）**LaTeX** 环境，含 `latexmk` 和 `pdfinfo`：
   ```bash
   # macOS
   brew install --cask mactex    # 或: brew install basictex
   brew install poppler          # 提供 pdfinfo

   # Ubuntu/Debian
   sudo apt install texlive-full latexmk poppler-utils

   # 验证
   latexmk --version && pdfinfo -v
   ```
   > 如果只用工作流 1 和 2（找 idea + 自动 review），不需要安装 LaTeX。

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

<details>
<summary><h3>🖥️ GPU 服务器配置（自动跑实验用）</h3></summary>

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

</details>

<details>
<summary><b>📚 Zotero 集成（可选）</b></summary>

如果你用 [Zotero](https://www.zotero.org/) 管理论文，`/research-lit` 可以搜索你的文献库、读取标注/高亮、导出 BibTeX——全在联网搜索之前完成。

**推荐：[zotero-mcp](https://github.com/54yyyu/zotero-mcp)**（1.8k⭐，语义搜索 + PDF 标注 + BibTeX 导出）

```bash
# 安装
uv tool install zotero-mcp-server   # 或: pip install zotero-mcp-server

# 添加到 Claude Code（本地 API——需要 Zotero 桌面端运行）
claude mcp add zotero -s user -- zotero-mcp -e ZOTERO_LOCAL=true

# 或使用 Web API（不需要打开 Zotero）
claude mcp add zotero -s user -- zotero-mcp \
  -e ZOTERO_API_KEY=your_key -e ZOTERO_USER_ID=your_id
```

> API Key 在 https://www.zotero.org/settings/keys 获取

**启用后 `/research-lit` 新增能力：**
- 🔍 按主题搜索 Zotero 库（含语义/向量搜索）
- 📂 浏览 Collections 和 Tags
- 📝 读取你的 PDF 标注和高亮（你个人认为重要的内容）
- 📄 导出 BibTeX 供论文写作直接使用

**不用 Zotero？** 没关系——`/research-lit` 自动跳过，用本地 PDF + 网络搜索。

</details>

<details>
<summary><b>📓 Obsidian 集成（可选）</b></summary>

如果你用 [Obsidian](https://obsidian.md/) 做研究笔记，`/research-lit` 可以搜索你的 vault 中的论文总结、带标签的引用和你自己的洞察。

**推荐：[mcpvault](https://github.com/bitbonsai/mcpvault)**（760⭐，不需要打开 Obsidian，14 个工具，BM25 搜索）

```bash
# 添加到 Claude Code（指向你的 vault 路径）
claude mcp add obsidian-vault -s user -- npx @bitbonsai/mcpvault@latest /path/to/your/vault
```

**可选补充：[obsidian-skills](https://github.com/kepano/obsidian-skills)**（13.6k⭐，Obsidian CEO 维护）——让 Claude 理解 Obsidian 特有的 Markdown 格式（wikilinks、callouts、properties）：

```bash
git clone https://github.com/kepano/obsidian-skills.git
cp -r obsidian-skills/.claude /path/to/your/vault/
```

**启用后 `/research-lit` 新增能力：**
- 🔍 搜索 vault 中与研究主题相关的笔记
- 🏷️ 按标签查找笔记（如 `#paper-review`、`#diffusion-models`）
- 📝 读取你的加工后总结和洞察（比原始论文更有价值）
- 🔗 沿 wikilinks 发现相关笔记

**不用 Obsidian？** 没关系——`/research-lit` 自动跳过，照常工作。

> 💡 **Zotero + Obsidian 同时使用**：很多研究者用 Zotero 存论文、Obsidian 记笔记。两个集成可以同时工作——`/research-lit` 先查 Zotero（原始论文 + 标注），再查 Obsidian（加工后笔记），再查本地 PDF，最后搜网络。

#### arXiv 集成

`/research-lit` 自动通过 arXiv API 获取结构化元数据（标题、摘要、完整作者列表、分类），比网页搜索片段更丰富。无需额外配置。

默认只获取元数据（不下载文件）。如需同时下载最相关的 PDF：

```
/research-lit "topic" — arxiv download: true                    # 下载 top 5 篇 PDF
/research-lit "topic" — arxiv download: true, max download: 10  # 下载至多 10 篇
```

也可使用独立的 [`/arxiv`](skills/arxiv/SKILL.md) skill 直接搜索和下载：

```
/arxiv "attention mechanism"           # 搜索
/arxiv "2301.07041" — download         # 下载指定论文
```

</details>

### 📱 飞书/Lark 集成（可选）

实验跑完、review 出分、checkpoint 等你审批——手机收飞书通知，不用守在终端前。

| 仅推送（群聊卡片） | 双向交互（私聊） |
|:-:|:-:|
| <img src="assets/feishu_push.png" width="450" /> | <img src="assets/feishu_interactive.jpg" width="450" /> |

**三种模式，按需选择：**

| 模式 | 效果 | 你需要 |
|------|------|--------|
| **关闭**（默认） | 什么都不做，纯 CLI 不变 | 什么都不用 |
| **仅推送** | 关键事件发 webhook 通知，手机收推送，不能回复 | 飞书机器人 webhook URL |
| **双向交互** | 全双工：在飞书里审批/拒绝 idea、回复 checkpoint | [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) 运行中 |

<details>
<summary><b>仅推送模式（5 分钟配好）</b></summary>

群通知，彩色富文本卡片——实验跑完、review 出分、流水线结束，手机收推送就行，不需要回复。

**第 1 步：创建飞书群机器人**

1. 打开你的飞书群（或新建一个测试群）
2. 群设置 → 群机器人 → 添加机器人 → **自定义机器人**
3. 起个名字（如 `ARIS Notifications`），复制 **Webhook 地址**
4. 安全设置：添加自定义关键词 `ARIS`（所有通知都包含这个词），或不设限制

**第 2 步：创建配置文件**

```bash
cat > ~/.claude/feishu.json << 'EOF'
{
  "mode": "push",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID"
}
EOF
```

**第 3 步：测试**

```bash
curl -s -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "msg_type": "interactive",
    "card": {
      "header": {"title": {"tag": "plain_text", "content": "🧪 ARIS Test"}, "template": "blue"},
      "elements": [{"tag": "markdown", "content": "Push mode working! 🎉"}]
    }
  }'
```

群里应该出现一张蓝色卡片。之后 skill 会在关键事件自动推送富文本卡片：

| 事件 | 卡片颜色 | 内容 |
|------|---------|------|
| Review 出分 ≥ 6 | 🟢 绿色 | 分数、结论、主要 weakness |
| Review 出分 < 6 | 🟠 橙色 | 分数、结论、待修复项 |
| 实验完成 | 🟢 绿色 | 结果对比表、delta vs baseline |
| Checkpoint 等待 | 🟡 黄色 | 问题、选项、上下文 |
| 出错 | 🔴 红色 | 错误信息、建议修复方案 |
| 流水线结束 | 🟣 紫色 | 分数进展表、最终交付物 |

</details>

<details>
<summary><b>双向交互模式（15 分钟）</b></summary>

推送模式的全部功能 **加上** 通过飞书私聊与 Claude Code 双向对话。审批/拒绝 idea、回复 checkpoint、给自定义指令——全在手机上完成。

**工作方式**：推送卡片发到**群里**（所有人看到状态），交互对话发到**私聊**（你回复，Claude Code 执行）。

**第 1 步：先完成上面的推送模式配置**（两种模式并存）

**第 2 步：在[飞书开放平台](https://open.feishu.cn/app)创建应用**

1. 点击 **创建企业自建应用** → 填名称（如 `ARIS Claude Bot`）→ 创建
2. 左侧菜单 → **添加应用能力** → 勾选 **机器人**
3. 左侧 → **权限管理** → 搜索并开通以下 5 个权限：

| 权限 | Scope | 作用 |
|------|-------|------|
| `im:message` | 获取与发送单聊、群组消息 | 核心消息能力 |
| `im:message:send_as_bot` | 以应用身份发消息 | 机器人回复 |
| `im:message.group_at_msg:readonly` | 接收群聊中@机器人消息 | 群消息 |
| `im:message.p2p_msg:readonly` | **读取用户发给机器人的单聊消息** | ⚠️ **极易遗漏！** 不开这个权限，机器人能连上但永远收不到你的私聊消息 |
| `im:resource` | 获取与上传图片或文件资源 | 图片/文件 |

4. 左侧 → **事件与回调** → 选择 **长连接** 模式 → 添加事件：`im.message.receive_v1` → 保存

> ⚠️ **注意**：长连接页面可能显示"未检测到应用连接信息"——这是正常的。需要先启动桥接服务（第 3 步），再回来保存。

5. 左侧 → **版本管理与发布** → **创建版本** → 填写描述 → **提交审核**

> 个人/测试企业通常秒过审核。

**第 3 步：部署桥接服务**

```bash
git clone https://github.com/joewongjc/feishu-claude-code.git
cd feishu-claude-code
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置
cp .env.example .env
```

编辑 `.env`：

```bash
FEISHU_APP_ID=cli_your_app_id          # 凭证与基础信息页面获取
FEISHU_APP_SECRET=your_app_secret      # 凭证与基础信息页面获取
DEFAULT_MODEL=claude-opus-4-6          # ⚠️ 默认是 sonnet——改成 opus 效果好很多
DEFAULT_CWD=/path/to/your/project      # Claude Code 的工作目录
PERMISSION_MODE=bypassPermissions      # 或 "default"（需手动确认敏感操作）
```

> ⚠️ **模型很重要**：默认的 `claude-sonnet-4-6` 能用但可能无法理解复杂项目上下文。实测 `claude-opus-4-6` 首次即正确识别了 18 个 ARIS skills，而 sonnet 反复失败。

启动桥接：

```bash
python main.py
# 预期输出：
# ✅ 连接飞书 WebSocket 长连接（自动重连）...
# [Lark] connected to wss://msg-frontier.feishu.cn/ws/v2?...
```

长期运行丢 screen 里：

```bash
screen -dmS feishu-bridge bash -c 'cd /path/to/feishu-claude-code && source .venv/bin/activate && python main.py'
```

**第 4 步：保存事件配置** — 回到飞书开放平台 → 事件与回调 → 长连接应该显示"已检测到连接"→ **保存**

> 如果在桥接启动前就发布了应用版本，可能需要再创建一个新版本（如 1.0.1）并重新发布。

**第 5 步：测试私聊**

1. 在飞书里搜索机器人名称，打开私聊
2. 发送：`你好`
3. 机器人应通过 Claude Code 回复

**如果机器人不回复**：发 `/new` 重置 session，再试一次。常见问题：

| 症状 | 原因 | 解决 |
|------|------|------|
| 机器人连上了但收不到消息 | 缺少 `im:message.p2p_msg:readonly` 权限 | 开通权限 → 创建新版本 → 发布 |
| 机器人回复但不认识你的项目 | `DEFAULT_CWD` 指向错误目录 | 修改 `.env` → 重启桥接 |
| 机器人回复但不够聪明 | 使用的是 `claude-sonnet-4-6` | 改为 `claude-opus-4-6` → 重启桥接 |
| 旧 session 上下文过时 | 修改配置前的 session 被缓存 | 在聊天中发 `/new` 开始新 session |
| 保存事件时"未检测到连接" | 桥接服务还没启动 | 先启动桥接，再保存事件配置 |

**第 6 步：更新 ARIS 配置**

```bash
cat > ~/.claude/feishu.json << 'EOF'
{
  "mode": "interactive",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID",
  "interactive": {
    "bridge_url": "http://localhost:5000",
    "timeout_seconds": 300
  }
}
EOF
```

现在 skill 会：
- **推送**富文本卡片到群里（状态通知，所有人可见）
- **私聊**你做决策（checkpoint 审批、继续/停止、自定义指令）

#### 哪些 skill 会发通知？

| Skill | 事件 | 推送模式 | 交互模式 |
|-------|------|----------|----------|
| `/auto-review-loop` | 每轮出分、循环结束 | 分数 + 结论 | + 等你决定继续/停止 |
| `/auto-paper-improvement-loop` | 每轮出分、全部完成 | 分数进展表 | 分数进展表 |
| `/run-experiment` | 实验已部署 | GPU 分配 + 预计时间 | GPU 分配 + 预计时间 |
| `/monitor-experiment` | 结果已收集 | 结果对比表 | 结果对比表 |
| `/idea-discovery` | 阶段切换、最终报告 | 各阶段摘要 | + 审批/拒绝 |
| `/research-pipeline` | 阶段切换、流水线结束 | 阶段摘要 | + 审批/拒绝 |

</details>

**不用飞书？** 没关系——没有 `~/.claude/feishu.json` 文件时，所有 skill 行为完全不变。零开销，零副作用。

> 💡 **其他 IM 平台**：推送模式的 webhook 模式适用于任何支持 incoming webhook 的服务（Slack、Discord、钉钉、企业微信）。只需改 `webhook_url` 和卡片格式。双向交互可参考 [cc-connect](https://github.com/chenhg5/cc-connect)（多平台桥接）或 [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu)。

## 🎛️ 自定义

Skills 就是普通的 Markdown 文件，fork 后随意改：

### 自动 Review 循环（`auto-review-loop`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_ROUNDS` | 4 | 最多 review→修复→再 review 轮数 |
| `POSITIVE_THRESHOLD` | 6/10 | 达到此分数自动停止（可投稿） |
| `> 4 GPU-hour 跳过` | 4h | 超过此时长的实验标记为"需人工跟进" |

### 找 Idea（`idea-discovery` / `idea-creator`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `PILOT_MAX_HOURS` | 2h | 单个 pilot 预估超时则跳过 |
| `PILOT_TIMEOUT_HOURS` | 3h | 硬超时——强制终止，收集部分结果 |
| `MAX_PILOT_IDEAS` | 3 | 最多并行 pilot 几个 idea |
| `MAX_TOTAL_GPU_HOURS` | 8h | 所有 pilot 的总 GPU 预算 |
| `AUTO_PROCEED` | true | 用户不回复时自动带着最优方案继续。设 `false` 则每步都等确认 |

行内覆盖：`/idea-discovery "方向" — pilot budget: 4h per idea, 每步等我确认`

### 文献搜索（`research-lit`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | 本地论文目录，搜外部之前先扫这里的 PDF |
| `MAX_LOCAL_PAPERS` | 20 | 最多扫描多少本地 PDF（每篇读前 3 页） |

行内覆盖：`/research-lit "方向" — paper library: ~/Zotero/storage/`

### 通用（所有使用 Codex MCP 的 skill）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `REVIEWER_MODEL` | `gpt-5.4` | Codex MCP 调用的 OpenAI 模型。其他可选：`gpt-5.3-codex`、`gpt-5.2-codex`、`o3`。完整列表见 [supported models](https://developers.openai.com/codex/models/) |

- **Prompt 模板** — 定制评审人格和评估标准
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具

## 🔀 替代模型组合

没有 Claude / OpenAI API？可以换用其他模型——同样的跨模型架构，不同的提供商。

| 角色 | 默认 | 方案 A：GLM + GPT | 方案 B：GLM + MiniMax |
|------|------|-------------------|----------------------|
| 执行者（Claude Code） | Claude Opus/Sonnet | GLM-5（智谱 API） | GLM-5（智谱 API） |
| 审稿人（Codex MCP） | GPT-5.4 | GPT-5.4（OpenAI API） | MiniMax-M2.5（MiniMax API） |
| 需要 OpenAI API？ | 是 | 是 | **否** |

### 第 1 步：安装 Claude Code 和 Codex CLI

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
```

### 第 2 步：配置 `~/.claude/settings.json`

终端输入：`nano ~/.claude/settings.json`

<details>
<summary><b>方案 A：GLM（执行者）+ GPT（审稿人）</b> — 只替换 Claude，保留 GPT-5.4 审稿</summary>

```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "your_zai_api_key",
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
    },
    "mcpServers": {
        "codex": {
            "command": "/opt/homebrew/bin/codex",
            "args": [
                "mcp-server"
            ]
        }
    }
}
```

Codex CLI 使用你已有的 `OPENAI_API_KEY`（来自 `~/.codex/config.toml` 或环境变量）——审稿端不需要额外配置。

</details>

<details>
<summary><b>方案 B：GLM（执行者）+ MiniMax（审稿人）</b> — 无需 Claude 或 OpenAI API</summary>

```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "your_zai_api_key",
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5",
        "MINIMAX_API_KEY": "your_minimax_api_key"
    },
    "mcpServers": {
        "minimax-chat": {
            "command": "/usr/bin/python3",
            "args": ["/Users/YOUR_USERNAME/.claude/mcp-servers/minimax-chat/server.py"],
            "env": {
                "MINIMAX_API_KEY": "your_minimax_api_key",
                "MINIMAX_BASE_URL": "https://api.minimax.chat/v1",
                "MINIMAX_MODEL": "MiniMax-M2.5"
            }
        }
    }
}
```

> **⚠️ 方案 B 额外步骤：** Codex MCP 使用 OpenAI 的 Responses API (`/v1/responses`)，MiniMax 不支持该接口（[详情](https://github.com/openai/codex/discussions/7782)）。因此方案 B 使用**自定义 MiniMax MCP 服务器**替代 Codex。完整指南：[`docs/MINIMAX_MCP_GUIDE.md`](docs/MINIMAX_MCP_GUIDE.md)。快速步骤：
>
> 1. 复制 `mcp-servers/minimax-chat/server.py` → `~/.claude/mcp-servers/minimax-chat/server.py`
> 2. `pip3 install httpx`
> 3. 配置完成后，让 Claude Code 改写所有 skill：
>
> ```
> 读一下 skills/auto-review-loop-minimax/SKILL.md 作为参考模板。
> 它把 mcp__codex__codex 替换成了 mcp__minimax-chat__minimax_chat。
> 现在请把所有其他使用 mcp__codex__codex / mcp__codex__codex-reply 的 skill
> 都按照同样的模式改写成使用 mcp__minimax-chat__minimax_chat。
> ```

</details>

保存：`Ctrl+O` → `Enter` → `Ctrl+X`

### 第 3 步：安装 Skills 并运行

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
cp -r skills/* ~/.claude/skills/

# 启动 Claude Code（现在由 GLM 驱动）
claude
```

### 第 4 步：让 GLM 读一遍项目 ⚠️ 重要

> **🔴 不要跳过这一步。** GLM 的 prompt 处理方式与 Claude 不同，必须让 GLM 先读一遍项目，确保 skill 文件能正确解析。

启动 `claude` 后，在对话中输入：

```
读一下这个项目，验证所有 skills 是否正常：
/idea-creator, /research-review, /auto-review-loop, /novelty-check,
/idea-discovery, /research-pipeline, /research-lit, /run-experiment,
/analyze-results, /monitor-experiment, /pixel-art

逐个确认：(1) 能正常加载 (2) frontmatter 解析正确
```

这让 GLM（作为 Claude Code 执行者）先熟悉 skill 文件并提前发现兼容性问题——而不是在跑到一半时才报错。

> ⚠️ **注意：** 替代模型的行为可能与 Claude 和 GPT-5.4 有所不同。你可能需要调整 skill 中的 `REVIEWER_MODEL` 并微调 prompt 模板以获得最佳效果。核心的跨模型架构不变。

## 📋 Roadmap

### 已完成

- [x] **Human-in-the-loop 检查点** — idea-discovery 和 research-pipeline 在关键决策点暂停等待用户审批。通过 `AUTO_PROCEED` 配置（默认自动继续，设 `false` 则每步等确认）
- [x] **替代模型组合** — [GLM + GPT、GLM + MiniMax](#-替代模型组合) 完整文档及配置指南。无需 Claude 或 OpenAI API
- [x] **Workflow 3：论文写作流水线** — 完整链路：`/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile`。支持 ICLR/NeurIPS/ICML 模板、claims-evidence 矩阵、出版级图表、latexmk 自动修复。参考 [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar)、[Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills)、[baoyu-skills](https://github.com/jimliu/baoyu-skills)

<details>
<summary>展开 6 项更早完成的功能</summary>

- [x] **可配置 REVIEWER_MODEL** — 所有依赖 Codex 的 skill 支持自定义审稿模型（默认 `gpt-5.4`，也支持 `gpt-5.3-codex`、`gpt-5.2-codex`、`o3` 等）

- [x] **本地论文库扫描** — `/research-lit` 在外部搜索前先扫描本地 `papers/` 和 `literature/` 目录，复用已读论文
- [x] **Idea Discovery 流水线** — `/idea-discovery` 一键编排 research-lit → idea-creator → novelty-check → research-review，含 GPU pilot 实验
- [x] **全流程研究管线** — `/research-pipeline` 串联 Workflow 1（idea discovery）→ 实现 → Workflow 2（auto-review-loop），端到端
- [x] **Peer Review skill** — `/peer-review` 以审稿人视角审阅他人论文，含 GPT-5.4 meta-review
- [x] **跨模型协作架构** — Claude Code（执行者）× Codex GPT-5.4 xhigh（审稿者），避免单模型自我博弈的局部最优

</details>

### 计划中

- [x] **飞书集成** — 三种模式（关闭/推送/交互），通过 `~/.claude/feishu.json` 配置。推送只需 webhook URL；交互用 [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code)。默认关闭——对已有工作流零影响。见[设置指南](#-飞书lark-集成可选)
- [ ] **W&B 集成** — 从 Weights & Biases 拉取训练曲线和指标作为反馈信号。auto-review-loop 可读取 loss/accuracy 图诊断训练问题并建议下一步实验
  - 相关项目：[wandb-mcp-server](https://github.com/wandb/wandb-mcp-server)（W&B 官方 MCP，40⭐）或通过 `wandb api` CLI
- [x] **Zotero MCP 集成** — `/research-lit` 搜索 Zotero 文献库、读取标注/高亮、导出 BibTeX。推荐：[zotero-mcp](https://github.com/54yyyu/zotero-mcp)（1.8k⭐）。见[设置指南](#-zotero-集成可选)
- [x] **Obsidian 集成** — `/research-lit` 搜索 Obsidian vault 中的研究笔记、标签引用、wikilinks。推荐：[mcpvault](https://github.com/bitbonsai/mcpvault)（760⭐）+ [obsidian-skills](https://github.com/kepano/obsidian-skills)（13.6k⭐）。见[设置指南](#-obsidian-集成可选)
- [ ] 更多执行者 × 评审者组合（Gemini、DeepSeek 等）
- [ ] **常驻模式（Daemon mode）** — 通过 `launchd`/`systemd` 自动重启 Claude Code 会话，实现真正的无人值守运行。当前编排层需要活跃的 CLI 会话；状态文件（`REVIEW_STATE.json`、`AUTO_REVIEW.md`）支持跨会话恢复，但重启需手动操作（[#11](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/11)）

## 💬 交流群

**欢迎贡献领域专用 skill！** 核心 skills 覆盖通用科研工作流，但每个领域都有自己的工具和范式。欢迎提交 PR 为你的领域添加新 skill——EDA、生物信息学、机器人、HPC 等等。只需添加一个 `skills/your-skill/SKILL.md` 并开 PR 即可。参考 [`dse-loop`](skills/dse-loop/SKILL.md) 作为示例。

欢迎加入微信群，交流 Claude Code + AI 科研工作流：

<img src="docs/wechat_group.jpg" alt="微信交流群二维码" width="300">

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260314b)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## 🙏 致谢

本项目构建于并集成了许多优秀的开源项目：

**核心基础设施**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic 的 Claude CLI，执行层骨干
- [Codex CLI](https://github.com/openai/codex) — OpenAI 的 CLI，作为 MCP server 实现跨模型审稿

**Zotero 集成**（[安装指南](#-zotero-集成可选)）
- [zotero-mcp](https://github.com/54yyyu/zotero-mcp) — Zotero MCP server，语义搜索 + PDF 标注
- [Zotero](https://www.zotero.org/) — 开源文献管理器

**Obsidian 集成**（[安装指南](#-obsidian-集成可选)）
- [mcpvault](https://github.com/bitbonsai/mcpvault) — Obsidian vault MCP server（不需要打开 Obsidian）
- [obsidian-skills](https://github.com/kepano/obsidian-skills) — Obsidian CEO Steph Ango 维护的 Claude Code skills

**论文写作灵感来源**
- [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) — 用 Claude 写学术论文
- [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) — 论文写作 skill 模板
- [baoyu-skills](https://github.com/jimliu/baoyu-skills) — Claude Code skills 合集

**飞书集成**（[安装指南](#-飞书lark-集成可选)）
- [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) — 飞书 ↔ Claude Code 双向桥接
- [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu) — 飞书 Claude 机器人
- [cc-connect](https://github.com/chenhg5/cc-connect) — 多平台消息桥接
- [lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp) — 飞书官方 MCP server

**社区**
- [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — Claude Code skills 精选列表（已收录）

## License

MIT
