# LLM API 混搭配置指南

本指南说明如何自由搭配 Claude Code 执行器和外部审查器的 API。

## 双层架构

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code                        │
│                                                      │
│  ┌─────────────────┐      ┌─────────────────────┐   │
│  │    执行器        │─────▶│      审查器          │   │
│  │  (Executor)     │      │    (Reviewer)       │   │
│  │                 │      │                     │   │
│  │  ANTHROPIC_*    │      │  LLM_*              │   │
│  │  环境变量        │      │  环境变量            │   │
│  └─────────────────┘      └─────────────────────┘   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 执行器配置

执行器通过 `ANTHROPIC_*` 环境变量配置。

### 1. 原生 Claude API
```json
{
  "ANTHROPIC_AUTH_TOKEN": "sk-ant-xxx",
  "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6"
}
```

### 2. Z.ai (GLM)
```json
{
  "ANTHROPIC_AUTH_TOKEN": "your-zai-key",
  "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
  "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
  "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
}
```

### 3. Kimi (Moonshot)
官方文档: https://platform.moonshot.cn/docs/guide/agent-support
```json
{
  "ANTHROPIC_AUTH_TOKEN": "sk-xxx",
  "ANTHROPIC_BASE_URL": "https://api.moonshot.cn/anthropic",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "kimi-k2",
  "ANTHROPIC_DEFAULT_SONNET_MODEL": "kimi-k2",
  "ANTHROPIC_SMALL_FAST_MODEL": "kimi-k2-thinking-turbo",
  "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
}
```

### 4. LongCat (美团)
官方文档: https://longcat.chat/platform/docs/zh/ClaudeCode.html
```json
{
  "ANTHROPIC_AUTH_TOKEN": "ak_xxx",
  "ANTHROPIC_BASE_URL": "https://api.longcat.chat/anthropic",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "LongCat-Flash-Thinking-2601",
  "ANTHROPIC_DEFAULT_SONNET_MODEL": "LongCat-Flash-Thinking-2601",
  "ANTHROPIC_SMALL_FAST_MODEL": "LongCat-Flash-Lite",
  "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
}
```

### 5. 自定义兼容端点
```json
{
  "ANTHROPIC_AUTH_TOKEN": "your-key",
  "ANTHROPIC_BASE_URL": "https://your-endpoint.com/anthropic",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "your-model"
}
```

---

## 审查器配置

审查器通过 `llm-chat` MCP 服务器调用任意API。

### MCP 服务器配置

在 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-api-key",
        "LLM_BASE_URL": "https://api.example.com/v1",
        "LLM_MODEL": "model-name"
      }
    }
  }
}
```

### 常用审查器提供商

| 提供商 | LLM_BASE_URL | LLM_MODEL |
|--------|--------------|-----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| MiniMax | `https://api.minimax.chat/v1` | `MiniMax-M2.5` |

---

## 完整配置示例

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-executor-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-reviewer-key",
        "LLM_BASE_URL": "https://api.deepseek.com/v1",
        "LLM_MODEL": "deepseek-chat"
      }
    }
  }
}
```

---

## 使用方式

```bash
# 使用通用 LLM 审查 skill
/auto-review-loop-llm
```

---

## 改写所有 Skills（重要！）

`auto-review-loop-llm` 只是一个 skill 的通用 LLM 版。项目中有 **12 个 skill** 使用 Codex MCP (`mcp__codex__codex`) 调用 GPT-5.4 做审查。如果你想全面切换到其他模型，需要让 Claude Code 把它们全部改写。

安装完 `llm-chat` MCP 服务器后，在 Claude Code 对话中执行：

```
Read skills/auto-review-loop-llm/SKILL.md as a reference.
It replaces mcp__codex__codex with mcp__llm-chat__chat.
Now rewrite ALL other skills that use mcp__codex__codex / mcp__codex__codex-reply
to use mcp__llm-chat__chat instead, following the same pattern.
```

Claude Code 会自动：

1. 扫描所有 skill 文件，找到使用 Codex MCP 的地方
2. 参考 `auto-review-loop-llm` 的写法（MCP 优先 + curl fallback）
3. 逐个改写到你本地的 `~/.claude/skills/` 目录

> ⚠️ **注意：** 这只修改你本地的 skill 副本，不影响仓库原文件。想恢复默认？重新 `cp -r skills/* ~/.claude/skills/` 即可。

---

## 常见问题

### Q: 为什么不用 Codex MCP？

Codex CLI 使用 OpenAI 的 **Responses API** (`/v1/responses`)，这个 API 只有 OpenAI 官方支持，第三方提供商（DeepSeek、MiniMax 等）都不支持。所以我们新建了 `llm-chat` MCP 服务器，使用标准的 **Chat Completions API** (`/v1/chat/completions`)，兼容所有 OpenAI-compatible API。

### Q: GLM/Kimi/LongCat 能用吗？

可以！这些提供商支持 Anthropic-compatible API，配置到执行器（`ANTHROPIC_*` 环境变量）即可。审查器（`LLM_*` 环境变量）可以用任意 OpenAI-compatible API。

---

## 混搭组合示例

### 组合 1: GLM + DeepSeek（性价比）

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-zai-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-deepseek-key",
        "LLM_BASE_URL": "https://api.deepseek.com/v1",
        "LLM_MODEL": "deepseek-chat"
      }
    }
  }
}
```

### 组合 2: GLM + Kimi（长文本）

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-zai-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-kimi-key",
        "LLM_BASE_URL": "https://api.moonshot.cn/v1",
        "LLM_MODEL": "moonshot-v1-32k"
      }
    }
  }
}
```

### 组合 3: 原生 Claude + MiniMax

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-ant-xxx",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-minimax-key",
        "LLM_BASE_URL": "https://api.minimax.chat/v1",
        "LLM_MODEL": "MiniMax-M2.5"
      }
    }
  }
}
```
