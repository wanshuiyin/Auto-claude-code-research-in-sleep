---
name: aris
description: "ARIS 科研全流程总控（Auto Research In Sleep, Cursor 零API版）。81个子技能覆盖：文献检索/综述(找论文、查文献、literature review、related work、arxiv、survey)、选题(找idea、brainstorm、查新、novelty check、研究方向)、跨模型自动评审循环(auto review loop、审稿、review、评审、打分)、公式推导与证明(推导、证明、proof)、实验(实验计划、跑实验、部署GPU、消融、监控、分析结果)、论文写作(写论文、大纲、LaTeX、编译PDF、图表、引用核查、诚信审计)、配图海报幻灯(架构图、插图、poster、slides、演讲)、投稿(rebuttal、返修、重投、基金)、专利(专利检索、权利要求、专利撰写)。Use when 用户提到科研、研究、论文、实验、文献、评审、投稿、专利等任务，或明确说 aris / 自动科研 / research pipeline。"
---

# ARIS 总控（Cursor 零 API 版）

ARIS = 覆盖科研全生命周期的 81 个 Markdown 子技能：文献 → 选题 → 实验 → 自动评审循环 → 论文 → 投稿/返修 → 专利。本包是 [Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 的 **Cursor 原生移植**：执行者与审稿者都用 Cursor 内置模型，**零 API key、零 CLI**。

**读到本文件后：按下方路由表找到目标子技能，Read 它的 SKILL.md 并遵照执行。** 子技能都在本目录 `skills/<name>/SKILL.md`。

## 核心机制：跨模型对抗审（本包的灵魂，务必遵守）

- **执行者** = 你（当前 Cursor 主对话的模型）：读文件、写代码、跑实验、写论文。
- **审稿者** = **Task 子代理 + 不同家族的内置模型**：打分、找茬、裁决。执行者永远不给自己的工作定质量结论（Type-B 验收必须跨模型，见 `skills/shared-references/acceptance-gate.md`）。

审稿者调用约定（全部子技能通用，详见 `skills/shared-references/reviewer-routing.md`）：

```
# 新审稿线程（对应上游 mcp__codex__codex）
Task(subagent_type: "generalPurpose", description: "ARIS reviewer",
     model: <REVIEWER_MODEL>, prompt: <技能指定的审稿prompt>)

# 同线程续审（对应上游 codex-reply / threadId）
Task(resume: <上一次返回的子代理id>, prompt: <后续prompt>)
```

**跨家族模型表**（禁止 `inherit` 当审稿者）：

| 执行者家族 | 默认审稿者 | 备选 |
|---|---|---|
| Claude 系 | `gpt-5.6-sol-max-fast` | `kimi-k3-max`、`glm-5.2-max`、`cursor-grok-4.5-high-fast` |
| GPT/composer 系 | `claude-opus-5-thinking-max` | `kimi-k3-max`、`glm-5.2-max` |
| 其他（grok/glm/kimi） | `gpt-5.6-sol-max-fast` | `claude-opus-5-thinking-max` |

- 只用 max/thinking 档 slug 出评审结论；slug 不在会话可用列表时选最近的同家族 max 档并记录进 trace。
- 审稿子代理自带文件工具，**直接读仓库**——给它文件路径，绝不给摘要（`reviewer-independence.md`）。
- 审计链技能（experiment-audit / paper-claim-audit / citation-audit / kill-argument / result-to-claim）每次用**全新**子代理；循环类技能（auto-review-loop / proof-checker / research-refine）用 `resume` 续线程。
- 审稿不可用时输出 `REVIEW_UNAVAILABLE`，绝不代替审稿者下结论。

## 调用换算（读子技能时的通用规则）

| 子技能里写的 | 你执行为 |
|---|---|
| `/x "args" — k: v` | Read 本包 `skills/x/SKILL.md`，`args` 替换 `$ARGUMENTS`，`— k: v` 是行内参数 |
| `mcp__codex__codex` 等审稿调用 | Task 子代理（见上） |
| `Agent` 工具 / fan-out | Task 子代理；生成型分片用 `model: "inherit"` 可并行，陪审必须跨家族 |
| `tools/<helper>.py` | 按 `.aris/tools/` → 项目 `tools/` → `$ARIS_REPO/tools/` → `~/.aris/repo` 解析；本导出不捆绑上游 helper，首次使用前需配置上游仓库路径 |
| exa / gemini 搜索 | 已重写为 WebSearch/WebFetch 原生引擎 |
| 论文插图（Gemini/codex-image2） | 已重写为 Cursor GenerateImage |
| `CLAUDE.md` 项目配置 | 读项目根的 CLAUDE.md 或 AGENTS.md（GPU 服务器信息等写在那里） |

跨会话恢复：所有长流程都有状态文件（`review-stage/REVIEW_STATE.json`、`refine-logs/REFINE_STATE.json`、`.aris/runs/<id>.json`），新会话引用状态文件即可续跑。

## 工作流入口（W1–W6）

| 工作流 | 入口 | 输入 → 输出 |
|---|---|---|
| W1 找idea全流程 | `skills/idea-discovery/SKILL.md` | 研究方向 → `idea-stage/IDEA_REPORT.md` + 实验计划 |
| W1.5 实验桥接 | `skills/experiment-bridge/SKILL.md` | EXPERIMENT_PLAN.md → 跑通的代码+初步结果 |
| W2 自动评审循环 | `skills/auto-review-loop/SKILL.md` | 论文/结果 → 审→修→再审直到达标 |
| W3 论文写作 | `skills/paper-writing/SKILL.md` | NARRATIVE_REPORT.md → 投稿级 PDF |
| W4 返修 | `skills/rebuttal/SKILL.md` | 论文+审稿意见 → 安全回复稿 |
| W5 换会重投 | `skills/resubmit-pipeline/SKILL.md` | 已投论文+新venue → 移植稿（不跑新实验） |
| W6 演讲 | `skills/paper-talk/SKILL.md` | 论文 → slides+讲稿 |
| 端到端 | `skills/research-pipeline/SKILL.md` | 方向 → W1→1.5→2→3 一条龙 |
| 研究记忆 | `skills/research-wiki/SKILL.md` | 跨会话知识库（init 一次） |

## 全目录路由（10 组 · 81 技能）

**文献检索**：`arxiv`(arXiv搜索下载) · `alphaxiv`(单篇快速解读,优先用已装alphaXiv MCP) · `deepxiv`(渐进式读论文) · `semantic-scholar`(正式发表/引用数) · `openalex`(引用图谱/机构) · `exa-search`(泛网页搜索,WebSearch版) · `web-debug-search`(GitHub issue调试检索) · `gemini-search`(多角度AI侦察,原生版) · `research-lit`(文献综述主力) · `comm-lit-review`(通信领域专用)

**选题方向**：`idea-creator`(生成排序idea) · `idea-discovery`(W1管线) · `idea-discovery-robot`(机器人特化) · `novelty-check`(查新) · `research-refine`(方向打磨成提案) · `research-refine-pipeline`(打磨+实验计划) · `research-wiki`(知识库) · `wiki-enrich`(补全wiki) · `research-pipeline`(端到端总管线)

**评审闭环**：`research-review`(单次深度评审) · `auto-review-loop`(W2多轮循环,支持medium/hard/nightmare) · `kill-argument`(最强拒稿论证+裁决) · ~~auto-review-loop-llm / -minimax~~(已被子代理审稿取代,存根指路)

**公式证明**：`formula-derivation`(推导包) · `proof-writer`(写证明) · `proof-checker`(证明缺口审查+修复)

**实验算力**：`experiment-plan`(claim驱动路线图) · `experiment-bridge`(W1.5实现) · `experiment-queue`(SSH批量队列) · `run-experiment`(部署本地/远程/云GPU) · `monitor-experiment`(监控收结果) · `analyze-results`(统计分析) · `training-check`(训练健康度) · `system-profile`(GPU环境画像) · `dse-loop`(设计空间探索调参) · `qzcli`(启智平台) · `vast-gpu`(Vast.ai租卡) · `serverless-modal`(Modal无服务器) · `experiment-audit`(实验诚实度审计) · `result-to-claim`(结果→claim裁决门) · `ablation-planner`(消融规划)

**论文主线**：`paper-writing`(W3管线) · `paper-plan`(大纲) · `paper-write`(逐节LaTeX) · `paper-compile`(编译修错) · `paper-figure`(实验图表) · `citation-audit`(引用真实性核查) · `paper-claim-audit`(数字与原始结果核对) · `integrity-forensics`(投稿前诚信取证) · `auto-paper-improvement-loop`(论文润色循环) · `writing-systems-papers`(系统论文要领) · `specification-writing`(技术规格) · `overleaf-sync`(Overleaf同步) · `render-html`(工件渲染HTML)

**配图展示**：`paper-illustration`(AI插图,GenerateImage版) · ~~paper-illustration-image2~~(存根→paper-illustration) · `figure-spec`(确定性SVG架构图) · `mermaid-diagram`(流程/时序图) · `pixel-art`(像素画) · `paper-poster-html`(学术海报) · ~~paper-poster~~(弃用→poster-html) · `paper-slides`(beamer幻灯) · `paper-talk`(W6演讲一体) · `slides-polish`(逐页打磨)

**投稿基金**：`rebuttal`(W4返修) · `resubmit-pipeline`(W5重投) · `grant-proposal`(基金申请书)

**专利**：`patent-pipeline`(全流程) · `invention-structuring`(发明披露结构化) · `claims-drafting`(权利要求) · `embodiment-description`(实施例) · `figure-description`(附图说明) · `jurisdiction-format`(CN/US/EP格式) · `patent-review`(质量审查) · `prior-art-search`(现有技术检索) · `patent-novelty-check`(专利查新)

**元工具**：`meta-optimize`(技能语料自优化) · `meta-apply`(落地补丁) · `feishu-notify`(飞书通知,webhook) · `interview-cheatsheet`(面试速查)

## 常用行内参数（追加在指令后）

```
— effort: lite | balanced | max | beast        # 工作强度，默认 balanced
— assurance: draft | polished | conference-ready | submission   # 审计门槛
— difficulty: medium | hard | nightmare        # 审稿对抗强度
— human checkpoint: true                       # 每轮暂停等确认
— AUTO_PROCEED: false                          # 关卡不自动继续
— venue: ICLR | NeurIPS | ICML | ...           # 目标会议
— reviewer-model: <slug>                       # 钉死审稿模型（须跨家族）
— sources: web, semantic-scholar, openalex...  # 文献源
```

## 兜底与纪律

- 子技能之间用文件传状态，长管线可拆多个会话跑。
- 审稿 trace 落 `.aris/traces/<skill>/`（`review-tracing.md`），元事件落 `.aris/meta/events.jsonl`。
- 上游原版仓库（含 helper 脚本与 API 后端原文）：<https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep>。
- 遇到本文件与子技能 SKILL.md 冲突：**子技能优先**（本文件只是路由索引）。
