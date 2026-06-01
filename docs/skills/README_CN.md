# ARIS Skill 系统梳理与自动科研工作流分析

这份文档梳理 `Auto-claude-code-research-in-sleep` 仓库里的自动科研 skill 体系：skill 放在哪里、`SKILL.md` 如何组织、不同 agent 平台如何安装和镜像、核心自动科研 workflow 如何串联，以及报告产物和质量门如何落地。

本文的分析结构参考 AutoResearchClaw 的 skill 系统说明：

- <https://github.com/Holosemantix/AutoResearchClaw/blob/lyr_ar_devi/docs/skills/README_CN.md>

本文基于以下文件阅读整理：

- `README_CN.md` / `README.md`
- `AGENT_GUIDE.md`
- `docs/SKILLS_CATALOG.md`
- `skills/*/SKILL.md`
- `skills/skills-codex/README_CN.md`
- `skills/skills-codex-claude-review/README_CN.md`
- `skills/skills-codex-gemini-review/README_CN.md`
- `skills/shared-references/*.md`
- `tools/install_aris.sh`
- `tools/install_aris_codex.sh`
- `tools/check_skills_inventory.py`
- `tools/verify_paper_audits.sh`
- `tools/research_wiki.py`

## 核心结论

ARIS 的 skill 体系不是一个代码驱动的固定 stage engine，而是一组可组合的 Markdown 工作流规范。每个 skill 用一个 `SKILL.md` 表达：

- 什么时候触发；
- 需要哪些工具和外部能力；
- 输入 artifact 在哪里；
- 应该调用哪些子 skill；
- 输出 artifact 写到哪里；
- 哪些环节必须由跨模型 reviewer 或确定性 verifier 裁决；
- 出错、降级、恢复和 resume 时怎么处理。

和 AutoResearchClaw 的 23-stage runtime matcher 不同，ARIS 的自动科研链路主要靠 orchestrator skill 显式串联：

```text
/research-pipeline
  -> /idea-discovery
  -> /experiment-bridge
  -> /auto-review-loop
  -> /paper-writing
```

ARIS 的关键设计取向是：

- 用纯 Markdown skill 保持轻量、可移植、可 fork；
- 用少数 workflow orchestrator 管住长流程；
- 用 `shared-references/` 统一跨 skill 契约，避免每个 skill 自己写一份易漂移规则；
- 用跨模型 reviewer 和外部 verifier 裁决质量，而不是让执行者自判；
- 用 `research-wiki/`、`.aris/runs/`、`.aris/traces/` 保存长期记忆和审计轨迹。

## Skill 目录来源

ARIS 当前主要有四类 skill / skill 包。

| 来源 | 路径 | 用途 |
| --- | --- | --- |
| 主线 skill | `skills/<name>/SKILL.md` | Claude Code / Cursor / Trae / Antigravity / Copilot CLI 等平台的主线规范 |
| Codex 原生镜像 | `skills/skills-codex/<name>/SKILL.md` | Codex CLI 适配层，语义尽量保持一致，review 路由换成 Codex 原生能力 |
| Codex + Claude reviewer overlay | `skills/skills-codex-claude-review/` | 薄覆盖层，只替换 reviewer-heavy skill 的 reviewer backend |
| Codex + Gemini reviewer overlay | `skills/skills-codex-gemini-review/` | 薄覆盖层，把 reviewer-aware skill 切到 `gemini-review` MCP |

本次 checkout 统计：

| 范围 | 数量 | 说明 |
| --- | ---: | --- |
| `skills/*/SKILL.md` 主线 skill | 78 | 顶层主线 skill，包括 `meta-apply` |
| `skills/skills-codex/*/SKILL.md` | 77 | Codex mirror 缺少主线里的 `meta-apply` |
| `skills/skills-codex-claude-review/*/SKILL.md` | 8 | 只覆盖核心 reviewer-heavy skill |
| `skills/skills-codex-gemini-review/*/SKILL.md` | 15 | 覆盖更宽的 reviewer-aware 入口 |
| `skills/shared-references/*.md` | 28 | 系统级契约和跨 skill 共享协议 |

这说明当前仓库已有一个小的 inventory drift：`docs/SKILLS_CATALOG.md` 和 `skills/skills-codex/README_CN.md` 都仍写 `77`，但主线顶层实际已经是 `78`，差异是 `meta-apply`。

## `SKILL.md` 基本格式

ARIS skill 使用 Markdown 文件加 YAML frontmatter。最小结构通常是：

```markdown
---
name: research-pipeline
description: "Full research pipeline: ..."
argument-hint: "[research-direction] [-- resume <run_id>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Skill
---

# Skill Title

## Constants

...

## Inputs

...

## Workflow

...

## Output Protocols

...

## Key Rules

...
```

常见字段含义：

| 字段 | 作用 |
| --- | --- |
| `name` | slash skill 名称，通常和目录名一致 |
| `description` | 给 agent / skill matcher 看的能力说明和触发语境 |
| `argument-hint` | 提示用户或 agent 该如何传参 |
| `allowed-tools` | skill 允许使用的工具集合，体现权限边界 |

和 AutoResearchClaw 不同，ARIS 的主线 `SKILL.md` 通常没有 `metadata.category`、`trigger-keywords`、`applicable-stages` 这样的 stage matcher 元数据。ARIS 更依赖：

- 用户显式 `/skill-name ...` 调用；
- orchestrator skill 显式委托子 skill；
- `description` 描述触发场景；
- `AGENT_GUIDE.md` 作为冷启动路由索引。

行为的 source of truth 是具体 `SKILL.md`。`AGENT_GUIDE.md` 和 README 是路由和说明，如果冲突，应以 `SKILL.md` 为准。

## 自动科研主链路

ARIS 把自动科研拆成多个 workflow，而不是 23 个固定 runtime stage。核心链路如下。

| Workflow | Skill | 主要输入 | 主要输出 | 作用 |
| --- | --- | --- | --- | --- |
| W1 | `/idea-discovery` | research direction / `RESEARCH_BRIEF.md` | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` | 文献调研、idea 生成、novelty check、外部评审、方法细化 |
| W1.5 | `/experiment-bridge` | `EXPERIMENT_PLAN.md`, `FINAL_PROPOSAL.md` | experiment code, `refine-logs/EXPERIMENT_RESULTS.md`, `EXPERIMENT_LOG.md` | 从计划到代码、sanity run、GPU 部署、初始结果收集 |
| W2 | `/auto-review-loop` | 当前方法、结果、论文/报告上下文 | `review-stage/AUTO_REVIEW.md`, `REVIEW_STATE.json` | 多轮跨模型 review -> fix -> re-review |
| W3 | `/paper-writing` | `NARRATIVE_REPORT.md` / 研究结果 | `paper/` LaTeX 源码、PDF、审计报告 | 论文规划、图表、写作、编译、改进、submission gate |
| W4 | `/rebuttal` | paper + reviewer comments | rebuttal drafts and safety checks | 论文评审后的 rebuttal |
| W5 | `/resubmit-pipeline` | 已打磨 paper + 新 venue | 新 venue 目录、`RESUBMIT_REPORT.json` | 文本-only 重投，禁止新实验和 bib 编辑 |
| W6 | `/paper-talk` | 完成论文 | Beamer / PPTX / notes / script | 会议报告和 slides polish |

### W1: `/idea-discovery`

`/idea-discovery` 是从研究方向到可执行实验计划的入口。它显式串联：

```text
/research-lit -> /idea-creator -> /novelty-check -> /research-review -> /research-refine-pipeline
```

它的报告逻辑强调一个 canonical deliverable：`idea-stage/IDEA_REPORT.md`。子 skill 在 composed mode 下把文献、idea、novelty、review 结果折叠进同一份报告，而不是散落生成多个重复 Markdown。

典型 `IDEA_REPORT.md` 结构：

```markdown
# Idea Discovery Report

**Direction**: ...
**Pipeline**: research-lit -> idea-creator -> novelty-check -> research-review -> research-refine-pipeline

## Executive Summary

## Literature Landscape

## Ranked Ideas

## Eliminated Ideas

## Refined Proposal

## Next Steps
```

这一点和 AutoResearchClaw 的 stage artifact 目录不同：AutoResearchClaw 每个 stage 都有固定输入输出；ARIS 在 W1 内更强调“一个面向人读和下游 handoff 的总报告”。

### W1.5: `/experiment-bridge`

`/experiment-bridge` 是从 idea 到真实实验的桥：

```text
refine-logs/EXPERIMENT_PLAN.md
  -> parse plan
  -> implement code
  -> cross-model code review
  -> sanity run
  -> full deployment
  -> collect initial results
```

关键约束：

- 优先读取 `refine-logs/EXPERIMENT_PLAN.md`；
- code review 默认打开，用 GPT reviewer 检查实验实现；
- sanity experiment 先跑，失败最多自动调试 3 次；
- 小批量实验走 `/run-experiment`，大批量或多 seed sweep 走 `/experiment-queue`；
- 结果要写成 JSON / CSV / Markdown 形式，供 W2 和 W3 继续消费。

### W2: `/auto-review-loop`

`/auto-review-loop` 是“自动科研 in sleep”的关键闭环。它重复：

```text
review -> parse assessment -> implement fixes -> run experiments -> re-review
```

停止条件是：

```text
score >= 6/10 AND verdict in {"ready", "almost"}
```

注意这里是 AND，不是 OR。高分但 verdict 仍是 `not ready` 不能停止。

它还提供三种 reviewer difficulty：

| 难度 | 行为 |
| --- | --- |
| `medium` | 普通 MCP review |
| `hard` | 增加 reviewer memory 和 debate protocol |
| `nightmare` | reviewer 直接读仓库和结果文件，执行者不能筛选上下文 |

这个 skill 的可靠性重点在于：评审线程要连续、raw response 要保存、state 要写到 `review-stage/REVIEW_STATE.json`，以便 context compact 或长任务中断后恢复。

### W3: `/paper-writing`

`/paper-writing` 从 `NARRATIVE_REPORT.md` 到 paper：

```text
/paper-plan
  -> /paper-figure
  -> /figure-spec | /paper-illustration | /paper-illustration-image2 | /mermaid-diagram
  -> /paper-write
  -> /paper-compile
  -> /auto-paper-improvement-loop
  -> audits and verifier
```

核心 artifact：

| Artifact | 作用 |
| --- | --- |
| `PAPER_PLAN.md` | claims-evidence matrix、section plan、figure plan |
| `figures/` | 数据图、表格、架构图、插图 |
| `paper/main.tex` | 主 LaTeX 源 |
| `paper/main.pdf` | 编译后的论文 |
| `PAPER_CLAIM_AUDIT.{md,json}` | 数字和 claim 核验 |
| `CITATION_AUDIT.{md,json}` | 引用存在性、元数据、上下文适配性核验 |
| `KILL_ARGUMENT.{md,json}` | 对理论/范围 claim 的攻击-裁决式评审 |

在 `-- effort: max | beast` 或显式 `-- assurance: submission` 下，Phase 6 会调用 `verify_paper_audits.sh`，外部 verifier 不通过则不能把 PDF 标成 submission-ready。

## ARIS 与 AutoResearchClaw 的 stage 对照

AutoResearchClaw 使用 23-stage pipeline，并在运行时按 stage 和 topic/context 自动匹配 skill。ARIS 没有同构的 stage enum，但主链路可以粗略对应：

| AutoResearchClaw stage | ARIS 对应 |
| --- | --- |
| 1 `topic_init` | `RESEARCH_BRIEF.md`, `/idea-discovery` Phase 0 |
| 2 `problem_decompose` | `/research-lit`, `/idea-creator` 的 landscape / gap 分析 |
| 3 `search_strategy` | `/research-lit`, `/gemini-search`, `/openalex`, `/semantic-scholar` |
| 4 `literature_collect` | `/research-lit`, `/arxiv`, `/deepxiv`, `/exa-search`, `/openalex` |
| 5 `literature_screen` | `/research-lit` dedup/filter + `/novelty-check` closest-prior-work |
| 6 `knowledge_extract` | `/research-wiki`, `/wiki-enrich` |
| 7 `synthesis` | `IDEA_REPORT.md` 的 Literature Landscape / gap |
| 8 `hypothesis_gen` | `/idea-creator`, `/research-refine` |
| 9 `experiment_design` | `/experiment-plan`, `/ablation-planner` |
| 10 `code_generation` | `/experiment-bridge` Phase 2 |
| 11 `resource_planning` | `/run-experiment`, `/experiment-queue`, `/vast-gpu`, `/serverless-modal` |
| 12 `experiment_run` | `/run-experiment`, `/experiment-queue`, `/monitor-experiment` |
| 13 `iterative_refine` | `/auto-review-loop`, `/research-refine-pipeline` |
| 14 `result_analysis` | `/analyze-results`, `/result-to-claim` |
| 15 `research_decision` | `/result-to-claim`, `/auto-review-loop` STOP condition |
| 16 `paper_outline` | `/paper-plan` |
| 17 `paper_draft` | `/paper-write`, `/paper-writing` |
| 18 `peer_review` | `/research-review`, `/auto-paper-improvement-loop`, `/kill-argument` |
| 19 `paper_revision` | `/auto-paper-improvement-loop` |
| 20 `quality_gate` | `assurance-contract.md`, `verify_paper_audits.sh` |
| 21 `knowledge_archive` | `/research-wiki`, `.aris/traces/`, `.aris/runs/` |
| 22 `export_publish` | `/paper-compile`, `/overleaf-sync`, `/resubmit-pipeline` |
| 23 `citation_verify` | `/citation-audit` |

因此，ARIS 不是缺少 stage，而是把 stage 组织成几个可读的 workflow，并把跨 stage 契约下沉到 artifact 文件和 shared references。

## 报告逻辑

ARIS 的报告逻辑可以概括为三层。

### 1. Workflow canonical report

长 workflow 尽量维护一份 canonical report：

| Workflow | Canonical report |
| --- | --- |
| `/idea-discovery` | `idea-stage/IDEA_REPORT.md` |
| `/auto-review-loop` | `review-stage/AUTO_REVIEW.md` |
| `/research-pipeline` | `NARRATIVE_REPORT.md` + pipeline report |
| `/resubmit-pipeline` | `RESUBMIT_REPORT.json` / Markdown ledger |
| `/paper-talk` | final talk report |

`output-composition.md` 明确要求：子 skill 在 composed mode 下应该折叠进 orchestrator 的 report，不要生成重复的 `LIT_LANDSCAPE.md`、`RESEARCH_REVIEW.md` 等散文件。

### 2. Machine-readable audit artifact

审计类 skill 必须尽量输出 JSON：

```json
{
  "audit_skill": "paper-claim-audit",
  "verdict": "PASS",
  "reason_code": "all_numbers_match",
  "summary": "...",
  "audited_input_hashes": {
    "main.tex": "sha256:..."
  },
  "trace_path": ".aris/traces/paper-claim-audit/...",
  "thread_id": "...",
  "reviewer_model": "gpt-5.5",
  "generated_at": "..."
}
```

这使 verifier 可以不信任自然语言总结，而是检查 JSON schema、verdict、hash、trace 路径和 reviewer 信息。

### 3. HTML view

`/render-html` 把 selected Markdown / JSON artifact 渲染为单文件 HTML，便于阅读。Markdown / JSON 仍是 canonical source，HTML 只是派生 view。部分 workflow 会默认在结束时渲染：

- `idea-stage/IDEA_REPORT.md` -> `IDEA_REPORT.html`
- `review-stage/AUTO_REVIEW.md` -> `AUTO_REVIEW.html`
- `NARRATIVE_REPORT.md` -> HTML view

## 质量门与防幻觉机制

ARIS 的主要防幻觉机制不是“更长 prompt”，而是把关键判断拆给不同机制。

| 机制 | 文件 / skill | 作用 |
| --- | --- | --- |
| 跨模型 reviewer | `/research-review`, `/auto-review-loop`, `/paper-claim-audit` 等 | 执行者不能自判正确性 |
| reviewer independence | `shared-references/reviewer-independence.md` | reviewer 读 artifact / file path，而不是执行者摘要 |
| assurance gate | `shared-references/assurance-contract.md` | 区分 draft 和 submission；submission 下 audit verdict 必须存在 |
| external verifier | `tools/verify_paper_audits.sh` | 重新检查 audit JSON、hash、trace、verdict |
| trace | `.aris/traces/<skill>/...` | 保存 reviewer prompt / response / metadata |
| research wiki | `research-wiki/` | 记住论文、idea、experiment、claim 状态 |
| helper resolution | `shared-references/integration-contract.md` | 防止 helper path 写死导致 side effect 静默失效 |

`assurance-contract.md` 定义 6 种 verdict：

| Verdict | 含义 | 是否阻断 submission |
| --- | --- | --- |
| `PASS` | 检查通过 | 否 |
| `WARN` | 有问题但不致命 | 否 |
| `FAIL` | 发现致命问题 | 是 |
| `NOT_APPLICABLE` | 该 audit 不适用，但已写明原因 | 否 |
| `BLOCKED` | 应该 audit，但缺少前置证据 | 是 |
| `ERROR` | audit 调用失败 | 是 |

关键点是：`NOT_APPLICABLE` 不是 silent skip。submission 模式下，即使“无 theorem / 无 numeric claim”，也应该有一个记录说明 audit phase 运行过。

## 代表性 skill 解读

### `/research-pipeline`

这是总入口，负责把 W1 -> W1.5 -> W2 -> summary -> W3 串起来。它还引入可恢复运行状态：

```text
.aris/runs/<run_id>.json
```

每个 phase 分成 `running`、`done`、`accepted` 等状态。`accepted` 只能在对应 gate 通过后写入，不能因为 executor 完成了文件写入就直接接受。

### `/idea-discovery`

这是最典型的 report composition 样板。它要求子 skill 使用：

```text
-- composed: idea-stage/IDEA_REPORT.md
```

这样文献、idea、novelty、external review 都折叠进同一份 `IDEA_REPORT.md`。这解决了长流程中“每个子任务都写一份 Markdown，内容互相重复”的问题。

### `/experiment-bridge`

它是自动科研落到真实工程的关键。设计重点包括：

- 计划解析；
- 代码实现；
- 跨模型 code review；
- sanity-first；
- 小批量 / 大批量实验自动路由；
- OOM / crash / failed run 的结构化记录。

它直接对应 AutoResearchClaw stage 10-13，但 ARIS 把这些合成一个 bridge workflow，使 handoff 更清晰。

### `/auto-review-loop`

这是自主迭代能力的核心。它的强约束包括：

- 不要外面再包 `/loop` 或 cron 来重复调用；
- reviewer thread 要保持连续；
- 每轮 raw response 必须保存；
- hard / nightmare 模式下 reviewer memory 不能丢；
- 停止条件同时需要 score 和 verdict 达标。

### `/paper-writing`

它集中体现 ARIS 的“写作不是终点，审计才是出口”：

- `paper-plan` 建立 claims-evidence matrix；
- `paper-figure` / `figure-spec` 生成图表；
- `paper-write` 写 LaTeX；
- `paper-compile` 编译；
- `auto-paper-improvement-loop` 修改；
- `paper-claim-audit`、`citation-audit`、`proof-checker`、`kill-argument` 等对质量进行外部裁决；
- `verify_paper_audits.sh` 作为最终机器 gate。

### `/meta-optimize` 与 `/meta-apply`

`/meta-optimize` 面向 skill 自我改进，但应保持 read-only。`/meta-apply` 是唯一允许把 self-modification patch 落到 skill corpus 的 privileged applier。

`/meta-apply` 的设计重点是权限边界：

- producer 只能 stage patch；
- human 明确选择要 land 的 patch；
- landing 时重新跑 fresh cross-model jury；
- 不信任 producer 写入 manifest 的 `jury_verdict`；
- 备份、stamp provenance、写日志。

这个设计比“让优化循环自己改自己的 prompt”稳得多。

## 和 AutoResearchClaw 的主要差异

| 维度 | AutoResearchClaw | ARIS |
| --- | --- | --- |
| Pipeline 形态 | 代码中固定 23-stage pipeline | Markdown orchestrator 串联多个 workflow |
| Skill 触发 | stage + context runtime matcher | slash invocation + orchestrator delegation + description |
| Skill 元数据 | `metadata.category`, `trigger-keywords`, `applicable-stages`, `priority` | 通常只用 `name`, `description`, `argument-hint`, `allowed-tools` |
| 输出组织 | 每个 stage 有 I/O contract 和 artifact 目录 | 每个 workflow 有 canonical report + known artifact paths |
| 扩展方式 | 新 skill 加入 registry / matcher | 新 `skills/<name>/SKILL.md`，必要时加入 catalog / installer / mirror |
| 防幻觉 | stage gate、human approval、citation verify | cross-model jury、assurance JSON、external verifier、traces |
| 自我进化 | MetaClaw lesson-to-skill | `/meta-optimize` 提案 + `/meta-apply` privileged landing |
| 平台适配 | 面向 ResearchClaw runtime | 面向 Claude / Codex / Cursor / Trae / Antigravity / Copilot 等 agent |

AutoResearchClaw 的优势是 stage contract 更强、自动匹配更明确；ARIS 的优势是轻量、可读、跨 agent、易迁移，并把 reviewer / audit / trace 作为核心质量结构。

## 当前发现的文档与一致性风险

### 1. Skill 数量文档漂移

主线顶层实际有 `78` 个 `SKILL.md`，但多个文档仍写 `77`。差异是 `meta-apply`：

```text
main skills: 78
skills-codex mirror: 77
missing in mirror: meta-apply
```

建议：

- 更新 `docs/SKILLS_CATALOG.md` 的数量和表格；
- 明确 `meta-apply` 是否应该进入 `skills/skills-codex/`；
- 如果不进入 mirror，文档应说明这是有意排除，因为它是 privileged applier。

### 2. `assurance` 术语存在双轨

`paper-writing` 和 `assurance-contract.md` 使用：

```text
draft | submission
```

`paper-talk` 使用：

```text
draft | polished | conference-ready
```

`AGENT_GUIDE.md` 把它们合在同一行写成：

```text
draft | polished | conference-ready | submission
```

这会让用户误以为所有 workflow 都支持同一套 assurance 值。建议把文档拆成：

- paper-writing / submission audit：`draft | submission`
- talk artifact readiness：`draft | polished | conference-ready`

或在 `assurance-contract.md` 里正式定义多 workflow 的 assurance namespace。

### 3. `allowed-tools` 不是强执行机制

`SKILL.md` 里的 `allowed-tools` 能表达权限意图，但在不同 agent 宿主中执行强度不一定一致。因此像 `/meta-apply` 这种高风险 skill，不能只依赖 prose 或 frontmatter 权限，应继续依赖：

- human explicit invocation；
- staged patch whitelist；
- fresh cross-model jury；
- backup；
- provenance stamp；
- trace。

### 4. Helper 集成仍需要持续 lint

`integration-contract.md` 已经说明不要硬编码 `python3 tools/foo.py`，但这类回归很容易在新 skill 中出现。建议：

- 保持 `.github/workflows/lint-skills-helpers.yml`；
- 对新增 skill 的 PR review 加一条 checklist：所有 helper 调用都走 resolver chain；
- 对 load-bearing verifier 使用 failure policy A，不允许 warn-and-skip。

## 写新 ARIS skill 的建议流程

1. 明确 skill 类型：workflow orchestrator、leaf executor、review/audit、utility、integration、meta-governance。
2. 写清触发场景：让 `description` 包含用户自然语言可能说法。
3. 明确输入 artifact：文件名、目录、fallback、缺失时如何处理。
4. 明确输出 artifact：固定路径、JSON schema、是否需要 HTML view。
5. 判断是否需要 composed mode：如果会被 orchestrator 调用，支持 `-- composed: <report>`。
6. 如果调用 helper，按 `integration-contract.md` 写 resolver chain 和 failure policy。
7. 如果涉及质量裁决，必须引入 cross-model reviewer 或 deterministic verifier。
8. 如果涉及 submission，输出 6-state audit verdict JSON。
9. 如果涉及长任务，写 state / resume 规则。
10. 加入 `docs/SKILLS_CATALOG.md` 和对应 mirror / overlay 策略。

推荐模板：

```markdown
---
name: <skill-name>
description: "<what this skill does and exactly when to use it>"
argument-hint: "[input] [-- option: value]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(*), Skill
---

# <Skill Title>

## Overview

...

## Constants

- OUTPUT_DIR = ...
- RENDER_HTML = true

## Inputs

1. ...
2. ...

## Workflow

### Phase 1: ...

### Phase 2: ...

## Output Protocols

- Follow `shared-references/output-versioning.md`
- Follow `shared-references/output-composition.md` when invoked by an orchestrator
- Save reviewer traces per `shared-references/review-tracing.md` if review is used

## Failure Policy

- Missing optional helper: warn and skip
- Missing load-bearing verifier: block
- Network failure: mark `ERROR` or `BLOCKED`, do not fabricate results

## Key Rules

- ...

## Anti-Patterns

- Do not ...
```

ARIS skill 最有价值的地方，是把自动科研中容易漂移的“判断权”和“证据链”外化成可读、可审计、可复用的协议。写新 skill 时，重点不是堆更多背景知识，而是明确：输入是什么、证据在哪里、谁有权裁决、失败如何暴露、下游如何继续。
