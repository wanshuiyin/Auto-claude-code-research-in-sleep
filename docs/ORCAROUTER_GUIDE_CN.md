# OrcaRouter 接入指南

本文档说明如何通过现有 [`llm-chat`](../mcp-servers/llm-chat/) MCP 服务器，把 [OrcaRouter](https://www.orcarouter.ai) 作为 ARIS 的审稿后端，并可选地同时作为 Claude Code 执行端。它适合想用一个 Key 覆盖多个 reviewer 模型家族的场景，但不替代 ARIS 默认的 assurance 审稿路由。

> 对强制审计 gate，请保留 ARIS 默认的 Codex MCP 审稿路径，除非你已经做过有意识、可审计的路由替换。执行者和审稿人必须固定到不同模型家族。

---

## 背景

### OrcaRouter 是什么

[OrcaRouter](https://www.orcarouter.ai) 是统一 AI 模型 API 网关，提供：
- **180+ 模型**：OpenAI、Anthropic、Google、xAI、DeepSeek、Qwen、Moonshot、Z.ai、MiniMax 等
- **一个 Key 两套协议**：审稿人走 OpenAI-compatible 的 `/v1/chat/completions`；执行端走 Anthropic-compatible 的 `/v1/messages`，Claude Code 可直接使用
- **命名 router**：`orcarouter/auto`、`orcarouter/fusion`、`orcarouter/free` 按请求选择上游，而不是固定单一模型
- **价格透明**：按量计费，用量与路由结果在 console 可见

同时它在同一端点上提供网关层的零信任 AI agent 安全能力 —— 逐条筛查 prompt/response、按默认拒绝策略管控每次工具调用，且无需改动应用代码。对 ARIS 来说，这意味着审稿流量可以集中筛查，而不用改任何 skill。

### 推荐审稿模型

| 模型 | 模型家族 | 用途 | 说明 |
|------|----------|------|------|
| `minimax/minimax-m3` | MiniMax | 审稿人 | 执行者是 Claude 或 GLM 时的默认推荐 |
| `deepseek/deepseek-v4-pro` | DeepSeek | 审稿人 | 推理能力强，与 Claude、GPT 均不同家族 |
| `z-ai/glm-5.2` | Z.ai GLM | 审稿人 | 执行者不是 GLM 时可用 |
| `openai/gpt-5.6-sol` | OpenAI | 审稿人 | 不额外申请 OpenAI Key 的前提下，最接近 ARIS 默认审稿人 |

> 完整模型列表：https://www.orcarouter.ai/models
>
> 对任何会产出 assurance-gated verdict 的 skill，都应使用固定模型 ID，而不是 `orcarouter/auto` 或 `orcarouter/free`。同时确保执行者和审稿人固定到不同模型家族。

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
| 执行者 | Anthropic-compatible | Anthropic、OrcaRouter（`https://api.orcarouter.ai`）或其他 Claude Code 兼容端点 |
| 审稿人 | OpenAI-compatible | 通过 `llm-chat` 访问 `https://api.orcarouter.ai/v1` |

OrcaRouter 应作为通过 `/auto-review-loop-llm` 使用的 opt-in 审稿后端。依赖跨家族审稿的生产审计与 assurance skill，除非你有意修改审稿路由并重新审计，否则应继续留在 `mcp__codex__codex`。

---

## 获取 API Key

1. 访问 [OrcaRouter](https://www.orcarouter.ai) 注册账号。
2. 进入 [console](https://www.orcarouter.ai/console) 创建 API Key。
3. Key 格式：`sk-orca-xxxxxxxxxxxxxxxx`。
4. 同一个 Key 同时可用于审稿端点（`/v1/chat/completions`）和执行端点（`/v1/messages`）。

---

## 安装步骤

### 前置条件

- 已安装 Claude Code CLI：`npm install -g @anthropic-ai/claude-code`
- 可用的 Python 3
- 已获取 OrcaRouter API Key
- 本地已 clone ARIS

### 步骤 1：Clone ARIS

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git /path/to/aris_repo
cd /path/to/aris_repo
```

### 步骤 2：安装 Python 依赖

```bash
pip3 install -r mcp-servers/llm-chat/requirements.txt
```

### 步骤 3：用标准安装器安装 ARIS Skills

```bash
# ARIS 标准安装：从目标项目建立指向本 ARIS 仓库的符号链接。
bash /path/to/aris_repo/tools/install_aris.sh /path/to/your-project
```

不要在 ARIS 仓库内部传 `$PWD`。安装器的目标应该是你的论文或实验项目，而不是 ARIS 检出目录。它负责逐 skill 的符号链接、已安装 skill 清单、`.aris/tools/` 辅助链（以及全局指针文件 `~/.aris/repo`，让全局 copy 安装在没有项目级清单时也能解析），以及 reconcile / uninstall / 迁移路径。

### 步骤 4：部署 llm-chat MCP 服务器

```bash
mkdir -p ~/.claude/mcp-servers/llm-chat
cp mcp-servers/llm-chat/server.py ~/.claude/mcp-servers/llm-chat/server.py
```

这一步手工拷贝只针对 MCP 服务器，`install_aris.sh` 不管理它。不要手工拷贝 `skills/*`。

### 步骤 5：配置 `~/.claude/settings.json`

**方案 A：执行者也用 OrcaRouter**

一个 Key 覆盖两端。注意 `ANTHROPIC_BASE_URL` 用裸 host、**不带** `/v1`，并且所有执行端模型都必须带厂商命名空间。

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-orca-your-orcarouter-key",
    "ANTHROPIC_API_KEY": "",
    "ANTHROPIC_BASE_URL": "https://api.orcarouter.ai",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "anthropic/claude-opus-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "anthropic/claude-sonnet-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anthropic/claude-haiku-4.5",
    "ANTHROPIC_SMALL_FAST_MODEL": "anthropic/claude-haiku-4.5",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["$HOME/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "sk-orca-your-orcarouter-key",
        "LLM_BASE_URL": "https://api.orcarouter.ai/v1",
        "LLM_MODEL": "minimax/minimax-m3"
      }
    }
  }
}
```

> **三个 `ANTHROPIC_DEFAULT_*_MODEL` 都要写。** OrcaRouter 按带命名空间的模型 ID 路由，Claude Code 默认发出的裸模型名（例如 `claude-sonnet-4-6`）会返回 `model_not_found`。不写这些 pin，执行端第一次调用就会失败。

**方案 B：执行者用别的 API，审稿人用 OrcaRouter（推荐）**

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
        "LLM_API_KEY": "sk-orca-your-orcarouter-key",
        "LLM_BASE_URL": "https://api.orcarouter.ai/v1",
        "LLM_MODEL": "minimax/minimax-m3"
      }
    }
  }
}
```

> **路径说明**：把 `$HOME` 替换成实际路径，例如 `/root` 或 `/home/username`；用 `which python3` 确认 `python3` 路径。

---

## 在 ARIS 中使用

想用 OrcaRouter 做审稿时，直接用已内置的 `/auto-review-loop-llm` skill：

```bash
claude
> /auto-review-loop-llm "你的论文主题"
```

不要把上游 skill 批量从 `mcp__codex__codex` 改写成 `mcp__llm-chat__chat`。带 `assurance: submission` 的 skill（例如生产级论文审计、证明/引用核查）依赖 ARIS 的审稿人独立性契约，除非你有意修改审稿路由，否则应保留默认的 Codex MCP 路径。

---

## 验证

### 1. 验证审稿端点

```bash
curl -s "https://api.orcarouter.ai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-orca-your-key" \
  -d '{
    "model": "minimax/minimax-m3",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 50
  }'
```

预期：返回包含 `"choices"` 字段的 JSON。

### 2. 验证执行端点（仅方案 A 需要）

```bash
curl -s "https://api.orcarouter.ai/v1/messages" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: sk-orca-your-key" \
  -d '{
    "model": "anthropic/claude-sonnet-5",
    "max_tokens": 64,
    "messages": [{"role": "user", "content": "Say hello"}]
  }'
```

预期：返回包含 `"content"` 数组的 JSON。如果收到 `model_not_found`，说明模型 ID 少了厂商命名空间。

### 3. 在 Claude Code 里做端到端验证

```bash
claude
> 读一遍项目，确认 /auto-review-loop-llm skill 工作正常
```

---

## 与其他方案对比

| | 默认 | Coding Plan | ModelScope | **OrcaRouter** |
|---|---|---|---|---|
| 执行者 | Claude Opus | kimi-k2.5 | DeepSeek-V3 | 通过 Anthropic-compatible 端点使用 Claude 家族 |
| 审稿人 | GPT-5.6-Sol xhigh 新线程 | glm-5 | DeepSeek-R1 | 180+ 可固定模型 |
| 免费额度 | 无 | 无 | **有，2000/天，以 ModelScope 当前政策为准**（[来源](https://developer.aliyun.com/article/1644361)） | 无，按量计费 |
| 需要几个 Key | 2 | 1 | 1 | **1（执行端 + 审稿端共用）** |
| 可选模型 | 有限 | 4 种 | 1000+ 种 | **180+ 种** |
| 计费 | 按量 | 套餐 | 免费 | 按量 |

**OrcaRouter 的优势**：一个 Key 同时覆盖 Anthropic-compatible 执行端点和 OpenAI-compatible 审稿端点，跨家族的执行者/审稿人拆分只需要一个账号。为保证 ARIS 审计正确性，请显式固定审稿模型。

---

## 常见问题

**Q：`orcarouter/auto` 是什么？**

`orcarouter/auto` 是命名 router，不是模型 ID。它按你在 console 配置的路由策略，逐请求挑选上游。做随手实验很方便，但不要用在 ARIS 的 assurance-gated 审稿上 —— 因为这时无法保证审稿人与执行者不同家族。

**Q：执行端为什么返回 `model_not_found`？**

OrcaRouter 按带命名空间的 ID 路由。请把 `ANTHROPIC_DEFAULT_OPUS_MODEL`、`ANTHROPIC_DEFAULT_SONNET_MODEL`、`ANTHROPIC_DEFAULT_HAIKU_MODEL` 设成例如 `anthropic/claude-opus-5` 这类值，否则 Claude Code 会发出网关无法解析的裸模型名。

**Q：`ANTHROPIC_BASE_URL` 要不要带 `/v1`？**

不要。`ANTHROPIC_BASE_URL` 用 `https://api.orcarouter.ai`（Claude Code 自己会拼 `/v1/messages`）；`LLM_BASE_URL` 用 `https://api.orcarouter.ai/v1`（`llm-chat` 自己会拼 `/chat/completions`）。

**Q：如何切换审稿模型？**

修改 `settings.json` 中的 `LLM_MODEL`，确认它和执行者来自不同模型家族，然后重启 Claude Code。

**Q：为什么 llm-chat MCP 调用失败？**

检查：
1. API Key 格式正确，且以 `sk-orca-` 开头。
2. `LLM_BASE_URL` 以 `/v1` 结尾。
3. 模型 ID 已固定并包含命名空间，例如 `minimax/minimax-m3`。
4. 账户余额充足。

---

## 参考资料

- [OrcaRouter 官网](https://www.orcarouter.ai)
- [OrcaRouter 模型列表](https://www.orcarouter.ai/models)
- [OrcaRouter 文档](https://docs.orcarouter.ai)
- [OrcaRouter Console](https://www.orcarouter.ai/console)
- [ModelScope 额度说明](https://developer.aliyun.com/article/1644361)
- [LLM API 混搭配置指南](LLM_API_MIX_MATCH_GUIDE.md)
- [OpenRouter 接入指南](OPENROUTER_GUIDE_CN.md) —— 另一条多模型网关路线的姊妹文档
