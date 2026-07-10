# 🎛️ 自定义

> [← 返回 README](../README_CN.md) · ARIS 各 skill 的可调参数(环境变量)。

Skills 就是普通的 Markdown 文件，fork 后随意改：

> 💡 **参数自动透传**：参数沿调用链自动向下传递。例如 `/research-pipeline "方向" — sources: zotero, arxiv download: true` 会将 `sources` 和 `arxiv download` 经 `idea-discovery` 一路传到 `research-lit`。这同样适用于 `deepxiv` 和 `exa` 这类可选源：`/research-pipeline "方向" — sources: all, deepxiv, exa`。你可以在任何层级设置下游参数——只需加 `— key: value`。
>
> ```
> research-pipeline  ──→  idea-discovery      ──→  research-lit
>                    ──→  experiment-bridge    ──→  run-experiment
>                    ──→  auto-review-loop
>                                             ──→  idea-creator
>                                             ──→  novelty-check
>                                             ──→  research-review
> ```

### 全流程（`research-pipeline`）

调端到端行为：GPU 目标、arXiv 下载、代码审查、人工 checkpoint、base repo、W&B 日志、精简摘要、参考论文、作图后端，以及自动继续。

行内覆盖：`/research-pipeline "方向" — auto proceed: false, wandb: true, illustration: true`

<details>
<summary><b>展开 <code>/research-pipeline</code> 的常量、默认值与透传</b></summary>

| 常量 | 默认值 | 说明 | 透传 |
|------|--------|------|:---:|
| `AUTO_PROCEED` | true | 用户不回复时自动带着最优方案继续 | → `idea-discovery` |
| `ARXIV_DOWNLOAD` | false | 搜索后自动下载最相关的 arXiv PDF | → `idea-discovery` → `research-lit` |
| `HUMAN_CHECKPOINT` | false | 设为 `true` 时每轮 review 后暂停等待确认 | → `auto-review-loop` |
| `WANDB` | false | 自动给实验脚本加 W&B 日志 | → `experiment-bridge` → `run-experiment` |
| `CODE_REVIEW` | true | GPT-5.6-Sol 部署前审查实验代码 | → `experiment-bridge` |
| `BASE_REPO` | false | GitHub 仓库 URL，克隆作为实验基础代码 | → `experiment-bridge` |
| `GPU` | `local` | GPU 目标：`local`、`remote`（SSH）、或 `vast`（[Vast.ai](https://vast.ai) 按需租用） | → `experiment-bridge` → `run-experiment` |
| `COMPACT` | false | 生成精简摘要文件，适合短 context 模型和 session 恢复 | → 所有工作流 |
| `REF_PAPER` | false | 参考论文（PDF 或 URL），先总结再基于它找 idea | → `idea-discovery` |
| `ILLUSTRATION` | `gemini` | AI 作图：`gemini`（默认，需 API key）、`mermaid`（免费）、`false`（跳过） | → `paper-writing` |

</details>

### 自动 Review 循环（`auto-review-loop`）

调停止条件：review→修复 轮数上限、判定"可投稿"的分数阈值、超过哪个 GPU-小时预算的实验自动标记为需人工跟进。

<details>
<summary><b>展开 <code>/auto-review-loop</code> 的停止条件</b></summary>

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_ROUNDS` | 4 | 最多 review→修复→再 review 轮数 |
| `POSITIVE_THRESHOLD` | 6/10 | 达到此分数自动停止（可投稿） |
| `> 4 GPU-hour 跳过` | 4h | 超过此时长的实验标记为"需人工跟进" |

</details>

### 找 Idea（`idea-discovery` / `idea-creator`）

调 pilot 阶段：单 pilot 最大耗时、硬超时、并行 pilot 数、总 GPU 预算，外加自动继续和 arXiv 下载开关。

行内覆盖：`/idea-discovery "方向" — pilot budget: 4h per idea, sources: zotero, arxiv download: true`

<details>
<summary><b>展开 <code>/idea-discovery</code> 与 <code>/idea-creator</code> 的 pilot 预算常量</b></summary>

| 常量 | 默认值 | 说明 | 透传 |
|------|--------|------|:---:|
| `PILOT_MAX_HOURS` | 2h | 单个 pilot 预估超时则跳过 | — |
| `PILOT_TIMEOUT_HOURS` | 3h | 硬超时——强制终止，收集部分结果 | — |
| `MAX_PILOT_IDEAS` | 3 | 最多并行 pilot 几个 idea | — |
| `MAX_TOTAL_GPU_HOURS` | 8h | 所有 pilot 的总 GPU 预算 | — |
| `AUTO_PROCEED` | true | 用户不回复时自动带着最优方案继续。设 `false` 则每步都等确认 | — |
| `ARXIV_DOWNLOAD` | false | 搜索后自动下载最相关的 arXiv PDF | → `research-lit` |

</details>

### 实验桥接（`experiment-bridge`）

调部署安全：GPT-5.6-Sol 代码审查、审查后自动部署、最小实验先跑、并行上限、W&B 日志、base repo URL。

行内覆盖：`/experiment-bridge — code review: false, wandb: true`

<details>
<summary><b>展开 <code>/experiment-bridge</code> 的部署与安全常量</b></summary>

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `CODE_REVIEW` | true | GPT-5.6-Sol xhigh 部署前审查代码。在浪费 GPU 前抓逻辑 bug |
| `AUTO_DEPLOY` | true | 实现 + 审查后自动部署。设 `false` 可手动检查 |
| `BASE_REPO` | false | GitHub 仓库 URL，克隆作为实验基础代码 |
| `SANITY_FIRST` | true | 先跑最小实验，提前发现 bug |
| `MAX_PARALLEL_RUNS` | 4 | 最多并行部署几个实验（受可用 GPU 限制） |
| `WANDB` | false | 自动加 W&B 日志。需在 CLAUDE.md 配 `wandb_project` |

</details>

### 文献搜索（`research-lit`）

调来源：本地 PDF 目录、本地扫描上限、搜索哪些源（Zotero / Obsidian / 网络 / Semantic Scholar / DeepXiv / Exa），以及 arXiv PDF 自动下载设置。

行内覆盖：`/research-lit "方向" — sources: zotero, web`、`/research-lit "方向" — sources: all, deepxiv`、`/research-lit "方向" — sources: all, exa`、`/research-lit "方向" — arxiv download: true, max download: 10`

<details>
<summary><b>展开 <code>/research-lit</code> 的源选择和 arXiv 下载常量</b></summary>

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | 本地论文目录，搜外部之前先扫这里的 PDF |
| `MAX_LOCAL_PAPERS` | 20 | 最多扫描多少本地 PDF（每篇读前 3 页） |
| `SOURCES` | `all` | 搜索哪些源：`zotero`、`obsidian`、`local`、`web`、`semantic-scholar`、`deepxiv`、`exa`、`all`（逗号分隔）。`semantic-scholar`、`deepxiv` 和 `exa` 需显式指定 |
| `ARXIV_DOWNLOAD` | false | 设为 `true` 时，搜索后自动下载最相关的 arXiv PDF 到 PAPER_LIBRARY |
| `ARXIV_MAX_DOWNLOAD` | 5 | `ARXIV_DOWNLOAD = true` 时最多下载的 PDF 数量 |

</details>

### 论文写作（`paper-write`）

调论文格式：DBLP 真实 BibTeX、目标会议（ICLR/NeurIPS/ICML/CVPR/ACL/AAAI/IEEE…）、匿名作者块、页数上限、作图后端。

行内覆盖：`/paper-write — target venue: NeurIPS, illustration: true`

<details>
<summary><b>展开 <code>/paper-write</code> 的论文格式与作图常量</b></summary>

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `DBLP_BIBTEX` | true | 从 DBLP/CrossRef 拉取真实 BibTeX，替代 LLM 生成的条目 |
| `TARGET_VENUE` | `ICLR` | 目标会议/期刊格式：`ICLR`、`NeurIPS`、`ICML`、`CVPR`、`ACL`、`AAAI`、`ACM`、`IEEE_JOURNAL`、`IEEE_CONF` |
| `ANONYMOUS` | true | 匿名审稿模式。注意：大多数 IEEE 期刊/会议不匿名，IEEE 时设为 `false` |
| `MAX_PAGES` | 9 | 页数上限。ML 会议：正文不含参考文献。IEEE：总页数含参考文献 |
| `ILLUSTRATION` | `gemini` | AI 作图：`gemini`（默认，需 API key）、`mermaid`（免费）、`false`（跳过） |

</details>

### 通用（所有使用 Codex MCP 的 skill）

调所有 Codex MCP 调用使用的 reviewer 模型（默认 `gpt-5.6-sol`），或者 fork SKILL.md 定制 prompt 模板与每个 skill 的工具白名单。

- **Prompt 模板** — 定制评审人格和评估标准
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具

<details>
<summary><b>展开 Codex MCP reviewer 模型选项</b></summary>

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `REVIEWER_MODEL` | `gpt-5.6-sol` | Codex MCP 调用的 OpenAI 模型。其他可选：`gpt-5.3-codex`、`gpt-5.2-codex`、`o3`。完整列表见 [supported models](https://developers.openai.com/codex/models/) |

</details>


