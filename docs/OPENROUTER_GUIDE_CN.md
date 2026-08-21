# OpenRouter 接入指南

本文档说明如何通过现有 [`llm-chat`](../mcp-servers/llm-chat/) MCP 服务器，把 [OpenRouter](https://openrouter.ai/) 作为 ARIS 的审稿后端。它适合想用免费或按量付费模型做 reviewer 的场景，但不替代 ARIS 默认的 assurance 审稿路由。

> 对强制审计 gate，请保留 ARIS 默认的 Codex MCP 审稿路径，除非你已经做过有意识、可审计的路由替换。执行者和审稿人必须固定到不同模型家族。

---

## 背景

### OpenRouter 是什么

[OpenRouter](https://openrouter.ai/) 是统一 AI 模型 API 网关，提供：
- **200+ 模型**：OpenAI、Anthropic、Google、DeepSeek、MiniMax、Qwen 等
- **免费模型**：部分模型提供免费额度，例如 `minimax/minimax-m2.5:free`
- **统一接口**：标准 OpenAI-compatible API，一个 Key 访问多个模型提供商
- **价格透明**：免费模型 + 按量计费

### 推荐审稿模型

| 模型 | 模型家族 | 用途 | 说明 |
|------|----------|------|------|
| `minimax/minimax-m2.5:free` | MiniMax | 审稿人 | 执行者不是 MiniMax 时可作为免费 reviewer 候选 |
| `meta-llama/llama-3.1-70b-instruct` | Meta Llama | 审稿人 | 执行者不是 Llama 时可作为付费固定 fallback |

> 完整模型列表：https://openrouter.ai/models
>
> 对任何会产出 assurance-gated verdict 的 skill，都应使用固定模型 ID，而不是 [Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-models-router)。同时确保执行者和审稿人固定到不同模型家族。

---

## 双层架构

```
┌──────────────────────────────────────────────────────────┐
│                    Claude Code (CLI)                      │
│                                                           │
│  ┌──────────────────┐       ┌─────────────────────────┐  │
│  │      执行者       │──────▶│        审稿人            │  │
│  │  (Claude CLI)    │       │   (llm-chat MCP)         │  │
│  │                  │       │                         │  │
│  │  ANTHROPIC_*     │       │  LLM_* 环境变量          │  │
│  │  环境变量         │       │                         │  │
│  └──────────────────┘       └─────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

| 角色 | 协议 | 端点 |
|------|------|------|
| 执行者 | Anthropic 兼容 | Anthropic、OpenRouter 或其他 Claude Code 兼容端点 |
| 审稿人 | OpenAI 兼容 | 通过 `llm-chat` 调用 `https://openrouter.ai/api/v1` |

OpenRouter 应作为 `/auto-review-loop-llm` 的 opt-in 审稿后端。依赖跨模型审稿的生产审计和 assurance skill 应继续使用 `mcp__codex__codex`，除非你有意修改并重新审计 reviewer routing。

---

## 获取 API Key

1. 访问 [OpenRouter](https://openrouter.ai/) 注册账号。
2. 进入 [Keys 页面](https://openrouter.ai/keys) 创建 API Key。
3. Key 格式：`sk-or-v1-xxxxxxxxxxxxxxxx`。
4. 免费模型无需充值即可使用，但受 OpenRouter 当前限额影响。

---

## 安装步骤

### 前置条件

- Claude Code CLI 已安装：`npm install -g @anthropic-ai/claude-code`
- Python 3 可用
- 已获取 OpenRouter API Key
- 本地已有 ARIS checkout

### Step 1：克隆 ARIS

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git /path/to/aris_repo
cd /path/to/aris_repo
```

### Step 2：安装 Python 依赖

```bash
pip3 install -r mcp-servers/llm-chat/requirements.txt
```

### Step 3：用标准安装器安装 ARIS Skills

```bash
# 标准 ARIS 安装：从目标项目创建 symlink，指向这个 ARIS repo。
bash /path/to/aris_repo/tools/install_aris.sh /path/to/your-project
```

不要在 ARIS repo 内部把 `$PWD` 作为目标传入。安装目标应是你的论文或实验项目，而不是 ARIS checkout 本身。安装器会管理 per-skill symlink、installed-skill manifest、`.aris/tools/` helper chain（以及全局指针文件 `~/.aris/repo`——即便是没有项目内 manifest 的全局 copy-install，同一条链也能借它解析成功），以及 reconcile / uninstall / migration 路径。

### Step 4：部署 llm-chat MCP 服务器

```bash
mkdir -p ~/.claude/mcp-servers/llm-chat
cp mcp-servers/llm-chat/server.py ~/.claude/mcp-servers/llm-chat/server.py
```

这里的手动复制只用于 MCP server，因为 `install_aris.sh` 不管理 MCP servers。不要手动复制 `skills/*`。

### Step 5：配置 `~/.claude/settings.json`

**方案 A：执行者也使用 OpenRouter**

执行者固定到 Anthropic 家族模型，审稿人固定到非 Anthropic 的 OpenRouter 模型。

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-or-v1-your-openrouter-key",
    "ANTHROPIC_API_KEY": "",
    "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "anthropic/claude-opus-4.6",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "anthropic/claude-sonnet-4.6",
    "ANTHROPIC_SMALL_FAST_MODEL": "anthropic/claude-sonnet-4.6",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["$HOME/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "sk-or-v1-your-openrouter-key",
        "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_MODEL": "minimax/minimax-m2.5:free"
      }
    }
  }
}
```

**方案 B：执行者使用其他 API，审稿人使用 OpenRouter（推荐）**

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-executor-api-key",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["$HOME/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "sk-or-v1-your-openrouter-key",
        "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_MODEL": "minimax/minimax-m2.5:free"
      }
    }
  }
}
```

> **路径说明**：`$HOME` 需替换为实际路径，例如 `/root` 或 `/home/username`；`python3` 路径用 `which python3` 确认。

---

## 在 ARIS 中使用

需要 OpenRouter-backed review 时，使用已经内置的 `/auto-review-loop-llm`：

```bash
claude
> /auto-review-loop-llm "你的论文主题"
```

不要把上游 skills 从 `mcp__codex__codex` 批量改写成 `mcp__llm-chat__chat`。带有 `assurance: submission` 的 skill，例如生产论文审计、证明检查和引用审计，依赖 ARIS 的 reviewer independence contract；除非你有意更新 reviewer routing，否则应保留默认 Codex MCP 路径。

---

## 验证安装

### 1. 验证审稿端点

```bash
curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-or-v1-your-key" \
  -d '{
    "model": "minimax/minimax-m2.5:free",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 50
  }'
```

预期：返回包含 `"choices"` 字段的 JSON。

### 2. 在 Claude Code 中端到端验证

```bash
claude
> 读一下这个项目，验证 /auto-review-loop-llm skill 是否正常可用
```

---

## 与其他方案对比

| | 默认方案 | Coding Plan | ModelScope | **OpenRouter** |
|---|---|---|---|---|
| 执行者 | Claude Opus | kimi-k2.5 | DeepSeek-V3 | 200+ 模型可选 |
| 审稿人 | GPT-5.6-Sol xhigh fresh thread | glm-5 | DeepSeek-R1 | 200+ 固定模型可选 |
| 免费选项 | 无 | 无 | **有，2000 次/天，受当前 ModelScope 政策限制**（[来源](https://developer.aliyun.com/article/1644361)） | **有，免费模型受 OpenRouter 限额影响** |
| API Key 数量 | 2 个 | 1 个 | 1 个 | **1 个** |
| 模型选择 | 受限 | 4 种 | 1000+ 种 | **200+ 种** |
| 价格 | 按量 | 套餐 | 免费 | 免费 + 按量 |

**OpenRouter 的优势**：一个 Key 可访问多个 reviewer 模型家族，包括免费选项。为了 ARIS 审计正确性，请显式固定审稿模型。

---

## 常见问题

**Q：`openrouter/free` 是什么？**

`openrouter/free` 是 OpenRouter 的 Free Models Router，会从当前可用免费模型中自动选择，且模型家族可能随时间变化。它适合随手实验，但不要用于 ARIS assurance-gated review。

**Q：免费模型有什么限制？**

免费模型有速率限制，可用性也可能变化。高强度或需要可复现的使用场景建议改用付费固定模型。

**Q：如何切换审稿模型？**

修改 `settings.json` 中的 `LLM_MODEL`，确认它和执行者来自不同模型家族，然后重启 Claude Code。

**Q：OpenRouter 可以作为 Claude Code 执行端吗？**

OpenRouter 可以通过兼容模型作为 Claude Code 执行端，但本文推荐先把 OpenRouter 作为 `llm-chat` 审稿后端使用。

**Q：为什么 llm-chat MCP 调用失败？**

检查：
1. API Key 格式正确，且以 `sk-or-v1-` 开头。
2. 模型 ID 已固定并包含命名空间，例如 `minimax/minimax-m2.5:free`。
3. 账户有足够免费额度或付费余额。

---

## 参考资料

- [OpenRouter 官网](https://openrouter.ai/)
- [OpenRouter 模型列表](https://openrouter.ai/models)
- [OpenRouter 文档](https://openrouter.ai/docs)
- [OpenRouter Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-models-router)
- [ModelScope 额度说明](https://developer.aliyun.com/article/1644361)
- [LLM API 混搭配置指南](LLM_API_MIX_MATCH_GUIDE.md)
