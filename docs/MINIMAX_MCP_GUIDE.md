# MiniMax MCP 集成指南

本文档说明如何在 Auto-claude-code-research-in-sleep 项目中使用 MiniMax API 替代 OpenAI Codex MCP 进行研究审查。

## 背景

OpenAI Codex CLI 使用 **Responses API** (`/v1/responses`)，而 MiniMax 等第三方 API 提供商只支持 **Chat Completions API** (`/v1/chat/completions`)。因此，Codex MCP 无法直接与 MiniMax 配合使用。

**解决方案**：创建自定义 MCP 服务器直接调用 MiniMax Chat Completions API。

相关讨论：[GitHub #7782](https://github.com/openai/codex/discussions/7782)

## 两种 Review Loop 版本

| 版本 | Skill 名称 | 触发词 | 外部审查服务 |
|------|-----------|--------|-------------|
| 原版 | `auto-review-loop` | "auto review loop" | Codex MCP (OpenAI) |
| MiniMax版 | `auto-review-loop-minimax` | "auto review loop minimax" | MiniMax API |

### 如何选择

- **使用原版**：如果你有 OpenAI API Key，且预算充足
- **使用 MiniMax版**：如果你想使用 MiniMax API（更便宜，或已有 MiniMax 账号）

## 安装步骤

### 1. 创建 MCP 服务器目录

```bash
mkdir -p ~/.claude/mcp-servers/minimax-chat
```

### 2. 复制 MCP 服务器代码

将 `mcp-servers/minimax-chat/server.py` 复制到：
```
~/.claude/mcp-servers/minimax-chat/server.py
```

### 3. 安装 Python 依赖

```bash
pip3 install httpx
```

### 4. 配置 Claude Code settings.json

在 `~/.claude/settings.json` 中添加：

```json
{
  "env": {
    "MINIMAX_API_KEY": "你的MiniMax API Key"
  },
  "mcpServers": {
    "minimax-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/你的用户名/.claude/mcp-servers/minimax-chat/server.py"],
      "env": {
        "MINIMAX_API_KEY": "你的MiniMax API Key",
        "MINIMAX_BASE_URL": "https://api.minimax.chat/v1",
        "MINIMAX_MODEL": "MiniMax-M2.5"
      }
    }
  }
}
```

### 5. 重启 Claude Code

重启后，MCP 服务器将自动加载。

## 改写所有 Skills（重要！）

`auto-review-loop-minimax` 只是**一个** skill 的 MiniMax 版。项目中有 **12 个 skill** 使用 Codex MCP (`mcp__codex__codex`) 调用 GPT-5.4 做审查。如果你想全面切换到 MiniMax，需要让 Claude Code 把它们全部改写。

安装完 MCP 服务器后，在 Claude Code 对话中执行：

```
Read skills/auto-review-loop-minimax/SKILL.md as a reference.
It replaces mcp__codex__codex with mcp__minimax-chat__minimax_chat.
Now rewrite ALL other skills that use mcp__codex__codex / mcp__codex__codex-reply
to use mcp__minimax-chat__minimax_chat instead, following the same pattern.
```

Claude Code 会自动：
1. 扫描所有 skill 文件，找到使用 Codex MCP 的地方
2. 参考 `auto-review-loop-minimax` 的写法（MCP 优先 + curl fallback）
3. 逐个改写到你本地的 `~/.claude/skills/` 目录

> **注意**：这只修改你本地的 skill 副本，不影响仓库原文件。

## 使用方法

### 方法一：通过 MCP 工具（推荐）

当 MCP 正确配置后，使用：

```
/auto-review-loop-minimax
```

Skill 会自动检测并使用 `mcp__minimax-chat__minimax_chat` 工具。

### 方法二：通过 curl（备选）

如果 MCP 不可用，Skill 会自动回退到使用 curl 直接调用 MiniMax API。

确保环境变量 `MINIMAX_API_KEY` 已设置。

## 文件结构

```
~/.claude/
├── settings.json                    # Claude Code 全局配置
├── mcp-servers/
│   └── minimax-chat/
│       └── server.py                # MiniMax MCP 服务器
└── skills/
    ├── auto-review-loop/
    │   └── SKILL.md                 # 原版（Codex MCP）
    └── auto-review-loop-minimax/
        └── SKILL.md                 # MiniMax 版

项目目录/
├── AUTO_REVIEW.md                   # 审查日志（自动生成）
└── REVIEW_STATE.json                # 状态持久化（自动生成）
```

## MCP 服务器特性

- **双格式支持**：自动检测并支持标准 MCP 格式和 NDJSON 格式
- **调试日志**：日志保存在 `/tmp/minimax-mcp-debug.log`
- **错误处理**：完善的错误处理和恢复机制

## 验证安装

### 测试 MCP 服务器

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | \
  MINIMAX_API_KEY="your-key" \
  python3 ~/.claude/mcp-servers/minimax-chat/server.py
```

预期输出：
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...}}
```

### 测试 MiniMax API 连通性

```bash
curl -s "https://api.minimax.chat/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "MiniMax-M2.5",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 50
  }'
```

## 常见问题

### Q: MCP 工具不可用？

1. 检查 `/tmp/minimax-mcp-debug.log` 日志文件
2. 确认 `settings.json` 配置正确
3. 确认 Python 路径正确（`/usr/bin/python3` 或 `which python3`）
4. 重启 Claude Code

### Q: API 调用失败？

1. 确认 API Key 正确且有效
2. 确认网络可访问 `https://api.minimax.chat/v1`
3. 检查 API 余额是否充足
4. 查看调试日志中的错误信息

### Q: Skill 没有触发？

确保使用正确的触发词：
- 原版：`auto review loop`
- MiniMax版：`auto review loop minimax`

### Q: 为什么不用 Codex MCP？

Codex CLI 硬编码使用 OpenAI Responses API，该 API 不被第三方提供商支持。详见 [GitHub 讨论](https://github.com/openai/codex/discussions/7782)。

## 贡献

欢迎提交 Issue 和 PR 来改进这个集成！

## 参考资料

- [OpenAI Codex Discussions #7782](https://github.com/openai/codex/discussions/7782)
- [MiniMax 开放平台](https://platform.minimax.chat/)
- [Claude Code 文档](https://docs.anthropic.com/claude-code)
