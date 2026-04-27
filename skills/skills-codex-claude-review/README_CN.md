# skills-codex-claude-review 说明

这是一个**薄覆盖层**，适用于想采用以下组合的用户：

- **Codex** 作为主执行者
- **Claude Code** 作为审稿人
- 用本地 `claude-review` MCP bridge 替代“第二个 Codex reviewer”

它不是新造一套完整技能包，而是叠加在上游已有的 `skills/skills-codex/` 之上。

## 这个包包含什么

- 只包含需要切换 reviewer backend 的 review-heavy skill 覆盖文件
- 不重复打包模板和资源目录
- 不替代基础的 `skills/skills-codex/` 安装

当前覆盖的技能：

- `research-review`
- `novelty-check`
- `research-refine`
- `auto-review-loop`
- `paper-plan`
- `paper-figure`
- `paper-write`
- `auto-paper-improvement-loop`

## 安装方式

1. 先安装上游原生 Codex 基座：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project
```

2. 再用 Claude overlay 重跑一次：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile --with-claude-review-overlay
```

3. 注册本地 reviewer bridge：

```bash
mkdir -p ~/.codex/mcp-servers/claude-review
cp mcp-servers/claude-review/server.py ~/.codex/mcp-servers/claude-review/server.py
codex mcp add claude-review -- python3 ~/.codex/mcp-servers/claude-review/server.py
```

如果你的 Claude 依赖 `claude-aws` 之类的 shell helper，再改用 wrapper：

```bash
cp mcp-servers/claude-review/run_with_claude_aws.sh ~/.codex/mcp-servers/claude-review/run_with_claude_aws.sh
chmod +x ~/.codex/mcp-servers/claude-review/run_with_claude_aws.sh
codex mcp add claude-review -- ~/.codex/mcp-servers/claude-review/run_with_claude_aws.sh
```

## 为什么需要这个包

上游 `skills/skills-codex/` 已经支持 Codex 原生执行，并通过 `spawn_agent` 使用第二个 Codex 做 reviewer。

这个覆盖层新增的是另一种分工：

- 执行者：Codex
- 审稿人：Claude Code CLI
- 传输层：`claude-review` MCP

对于长论文和长 review prompt，这条 reviewer 路径会改用：

- `review_start`
- `review_reply_start`
- `review_status`

这样可以绕开 Codex 宿主下，本地 Claude bridge 同步等待时更容易出现的超时问题。
