# skills-codex-gemini-review 说明

这是一个**薄覆盖层**，适用于想采用以下组合的用户：

- **Codex** 作为主执行者
- **Gemini** 作为审稿人
- 用本地 `gemini-review` MCP bridge 替代“第二个 Codex reviewer”

它不是新造一套完整技能包，而是叠加在上游已有的 `skills/skills-codex/` 之上。

## 这个包包含什么

- 只包含需要切换 reviewer backend 的 reviewer-aware skill 覆盖文件
- 不重复打包模板和资源目录
- 不替代基础的 `skills/skills-codex/` 安装

当前覆盖的技能：

- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `research-review`
- `novelty-check`
- `research-refine`
- `auto-review-loop`
- `grant-proposal`
- `paper-plan`
- `paper-figure`
- `paper-poster`
- `paper-slides`
- `paper-write`
- `paper-writing`
- `auto-paper-improvement-loop`

## 核心 8 个 vs 完整 15 个

为了避免误解，这个 overlay 有两种常用描述方式：

- **核心 8 个**：和早先 Claude-review 路线一一对齐的 reviewer-heavy overlay 核心集合
- **完整 15 个**：当前这个仓库里实际已经切到 Gemini reviewer 的 reviewer-aware Codex 技能面

其中 **核心 8 个** 是：

- `research-review`
- `novelty-check`
- `research-refine`
- `auto-review-loop`
- `paper-plan`
- `paper-figure`
- `paper-write`
- `auto-paper-improvement-loop`

额外扩展的 **7 个** reviewer-aware 入口是：

- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `grant-proposal`
- `paper-writing`
- `paper-slides`
- `paper-poster`

所以和 Claude overlay 对比时，最准确的一句话是：

> Gemini 这条路保持了相同的核心 8-skill reviewer overlay 形状，但在当前仓库里把实际 reviewer 入口扩展到了 15 个。

## 直接消费者 vs wrapper

- **12 个直接消费者**：自己直接调用 `mcp__gemini-review__review_start` / `review_reply_start` / `review_status`
  - `research-review`
  - `novelty-check`
  - `research-refine`
  - `auto-review-loop`
  - `paper-plan`
  - `paper-figure`
  - `paper-write`
  - `auto-paper-improvement-loop`
  - `idea-creator`
  - `grant-proposal`
  - `paper-slides`
  - `paper-poster`
- **3 个 wrapper**：主要串联下游 reviewer-aware skill，并传递 `REVIEWER_MODEL=gemini-review`
  - `idea-discovery`
  - `idea-discovery-robot`
  - `paper-writing`

## 安装方式

注册 bridge 之前，请先准备好 direct Gemini API 路径：

- **Gemini API**：设置 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`（例如写进 `~/.gemini/.env`）

可选 fallback：

- **Gemini CLI**：只有在你明确想用 `GEMINI_REVIEW_BACKEND=cli` 时，才需要本机安装 `gemini` 并完成登录/认证

1. 先安装上游原生 Codex 基座：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project
```

2. 再用 Gemini overlay 重跑一次：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile --with-gemini-review-overlay
```

3. 注册本地 reviewer bridge：

```bash
mkdir -p ~/.codex/mcp-servers/gemini-review
cp mcp-servers/gemini-review/server.py ~/.codex/mcp-servers/gemini-review/server.py
codex mcp add gemini-review --env GEMINI_REVIEW_BACKEND=api -- python3 ~/.codex/mcp-servers/gemini-review/server.py
```

bridge 默认直接走 Gemini API。这也是这套 overlay 预期使用的 reviewer backend。

如果默认 API 模型在你当前免费层窗口里临时被限流，不需要改 overlay 和 bridge 结构，只需要覆盖 reviewer model：

```bash
codex mcp remove gemini-review
codex mcp add gemini-review --env GEMINI_REVIEW_BACKEND=api --env GEMINI_REVIEW_MODEL=gemini-flash-latest -- python3 ~/.codex/mcp-servers/gemini-review/server.py
```

## 为什么需要这个包

上游 `skills/skills-codex/` 已经支持 Codex 原生执行，并通过 `spawn_agent` 使用第二个 Codex 做 reviewer。

这个覆盖层新增的是另一种分工：

- 执行者：Codex
- 审稿人：Gemini direct API
- 传输层：`gemini-review` MCP

对于长论文和长 review prompt，这条 reviewer 路径会改用：

- `review_start`
- `review_reply_start`
- `review_status`

这样可以绕开 Codex 宿主下，本地 Gemini bridge 同步等待时更容易出现的超时问题。

## 验证结果摘要

这套 overlay 做了两类验证：

- **覆盖检查**：本包里的 `15` 个预定义 reviewer-aware skill override 都核对过，确认目标都是 `gemini-review`
- **运行时检查**：
  - 底层 bridge 已完成同步、异步、thread 续聊、本地图像多模态审查等测试
  - 在一个私有、未公开的研究仓库上，代表性的 Codex 实跑已经确认：真实 skill 执行可以进入 Gemini reviewer 路径，覆盖研究审稿、idea 生成、论文规划这几类工作流

实际使用上的结论：

- Gemini 免费层对这条工作流是可用的，但密集压测时仍可能出现临时 `429`
- 在同一套环境上的后续重试里，把 `GEMINI_REVIEW_MODEL` 设为 `gemini-flash-latest` 后，同步 review、异步 `review_start` -> `review_status`、以及带 thread 的 `review_reply_start` -> `review_status` 都已跑通
- 对长 prompt，优先使用异步 `review_start` / `review_reply_start` + `review_status`

## 引用与来源

- 上游 ARIS 的 overlay 组织方式：
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/skills/skills-codex-claude-review>
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/mcp-servers/claude-review>
- 本仓库里的本地 Gemini reviewer bridge：
  - `mcp-servers/gemini-review/README.md`
- 本覆盖层依赖的 Gemini 官方后端：
  - 官方 Gemini API：<https://ai.google.dev/api>
  - 官方 Gemini CLI：<https://github.com/google-gemini/gemini-cli>
  - AI Studio API key：<https://aistudio.google.com/apikey>

这个包保持了上游 ARIS review skill 的组织和调用形状，但把 reviewer transport 换成了本地 `gemini-review` bridge。现在它覆盖了本仓库里所有原先依赖第二个 Codex reviewer 或 `mcp__codex__codex` 审稿步骤的预定义 Codex skill。这里没有直接依赖通用的 Gemini MCP server 成品包，因为 ARIS 这组 review skills 依赖的是特定的 `review*` 工具契约、可恢复的 review thread 语义，以及 poster PNG 这类本地图像审查入口。
