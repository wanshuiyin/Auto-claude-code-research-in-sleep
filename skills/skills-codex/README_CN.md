# `skills-codex` 说明

## 1. 这个包是什么

这是一个面向 OpenAI Codex 的科研技能镜像包，用来把主线技能目录中的可迁移部分同步到 `~/.codex/skills/`。

当前目录包含：

- `39` 个技能目录
- `1` 个共享参考目录 `shared-references/`
- 少量技能自带资源目录，例如 `paper-write/templates/`、`comm-lit-review/references/`

它的目标不是复制整套运行环境，而是把 Codex 需要直接读取的技能工作流、说明文本和必要静态资源带过来。

## 2. 当前包含哪些技能

当前技能列表如下：

- `ablation-planner`
- `analyze-results`
- `arxiv`
- `auto-paper-improvement-loop`
- `auto-review-loop`
- `auto-review-loop-llm`
- `auto-review-loop-minimax`
- `comm-lit-review`
- `dse-loop`
- `experiment-bridge`
- `experiment-plan`
- `feishu-notify`
- `formula-derivation`
- `grant-proposal`
- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `mermaid-diagram`
- `monitor-experiment`
- `novelty-check`
- `paper-compile`
- `paper-figure`
- `paper-illustration`
- `paper-plan`
- `paper-poster`
- `paper-slides`
- `paper-write`
- `paper-writing`
- `pixel-art`
- `proof-writer`
- `rebuttal`
- `research-lit`
- `research-pipeline`
- `research-refine`
- `research-refine-pipeline`
- `research-review`
- `result-to-claim`
- `run-experiment`
- `training-check`

## 3. 目录结构

当前目录结构可以概括为：

```text
skills-codex/
  <skill-name>/
    SKILL.md
    ...
  comm-lit-review/
    references/
  paper-write/
    templates/
  shared-references/
    ...
```

说明：

- `shared-references/` 不是独立 skill，它给 `paper-plan` 和 `paper-write` 提供共享参考材料。
- `comm-lit-review` 不是单文件 skill，它依赖 `references/`。
- `paper-write` 不是单文件 skill，它依赖 `templates/` 中的会议模板。

## 4. 和主线相比的范围边界

这个包只保留适合在 Codex 本地直接使用的内容，重点是：

- 技能边界和工作流说明
- 适配 Codex 的调用方式
- 技能运行所需的静态模板、参考文件、提示词资源

这个包不负责迁移完整运行环境，因此默认不包含：

- Python 依赖安装
- LaTeX / Poppler / GPU / SSH / conda 环境
- MCP 服务配置
- API Key 和环境变量

另外，以下内容当前也不在这个包里：

- `.system/*`

## 5. 如何安装

```bash
mkdir -p ~/.codex/skills
cp -a skills/skills-codex/* ~/.codex/skills/
```

如果你还有额外的 overlay 包，建议先安装这个基础包，再叠加你自己的扩展。
