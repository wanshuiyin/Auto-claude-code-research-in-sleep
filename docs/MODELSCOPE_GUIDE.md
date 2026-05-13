# ModelScope（魔搭社区）接入指南

本文档说明如何使用 [ModelScope](https://www.modelscope.cn/) 的免费 API 驱动 ARIS 全流程，无需 Claude 或 OpenAI API。

---

## 背景

### ModelScope 是什么

[ModelScope（魔搭社区）](https://www.modelscope.cn/) 是阿里达摩院推出的开源模型即服务（MaaS）平台，提供 1000+ 开源模型的免费 API 推理服务，同时兼容 OpenAI 和 Anthropic 两大主流 API 协议。

### 为什么适合 ARIS

- **免费**：注册即送每日 2000 次 API 调用，无需付费套餐
- **一个 Key 双协议**：同一个 `ms-xxx` API Key 同时支持 Anthropic 和 OpenAI 兼容端点
- **模型丰富**：DeepSeek-V4-Pro、DeepSeek-R1、Qwen3-Coder、GLM-5.1、Yi 等主流开源模型均可用
- **无使用限制**：不像 Coding Plan 有"禁止自动化调用"的条款限制

### 支持的模型（推荐）

| 模型 | 推荐用途 | 说明 |
|------|---------|------|
| `deepseek-ai/DeepSeek-V4-Pro` | 执行器主力 | 综合能力强 |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | 执行器轻量 / 快速模型 | 代码能力优秀，速度快 |
| `deepseek-ai/DeepSeek-R1` | 审查器主力 | 推理质量高，适合深度 review |
| `Qwen/Qwen3-235B-A22B-Instruct` | 审查器备选 | 大参数量，综合审查 |

> 完整模型列表见 [ModelScope 模型库](https://www.modelscope.cn/models)，筛选"API 推理"即可。模型 ID 格式为 `组织/模型名`。

### 为什么不能直接用 Codex MCP

原版 ARIS 的审查器使用 Codex MCP，而 Codex CLI 硬编码调用 OpenAI 专有的 **Responses API** (`/v1/responses`)，第三方 API 提供商（包括 ModelScope）均不支持该接口。

**解决方案**：使用项目内置的 `llm-chat` MCP 服务器，它调用标准 **Chat Completions API** (`/v1/chat/completions`)，兼容所有 OpenAI 兼容端点，包括 ModelScope。

---

## 双层架构

ModelScope 同时提供两套 API 端点，分别对应 ARIS 的两个角色：

```
┌──────────────────────────────────────────────────────────┐
│                    Claude Code (CLI)                      │
│                                                           │
│  ┌──────────────────┐       ┌─────────────────────────┐  │
│  │     执行器        │──────▶│        审查器            │  │
│  │  (Claude CLI)    │       │   (llm-chat MCP)        │  │
│  │                  │       │                         │  │
│  │  ANTHROPIC_* 变量 │       │  LLM_* 环境变量          │  │
│  │  → Anthropic 端点 │       │  → OpenAI 端点           │  │
│  └──────────────────┘       └─────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

| 角色 | 协议 | 端点 |
|------|------|------|
| 执行器（Claude CLI） | Anthropic 兼容 | `https://api-inference.modelscope.cn` |
| 审查器（llm-chat MCP） | OpenAI 兼容 | `https://api-inference.modelscope.cn/v1` |

两个端点使用**同一个 ModelScope API Key**（`ms-xxx` 格式），无需分别申请。

---

## 获取 API Key

1. 访问 [ModelScope](https://www.modelscope.cn/) 并注册账号（支持支付宝/GitHub 登录）
2. 登录后进入 [API Key 管理页](https://www.modelscope.cn/my/myaccesstoken)
3. 创建一个 SDK Token，格式为 `ms-xxxxxxxxxxxxxxxx`
4. 无需付费——注册即可获得每日 2000 次免费调用额度

---

## 安装步骤

### 前置条件

- Claude Code CLI 已安装：`npm install -g @anthropic-ai/claude-code`
- Python 3 可用：`python3 --version`（用 `which python3` 确认路径）
- 已获取 ModelScope API Key（见上方）

### Step 1：克隆仓库

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
```

### Step 2：安装 Python 依赖

```bash
pip3 install -r mcp-servers/llm-chat/requirements.txt
```

### Step 3：部署 llm-chat MCP 服务器

```bash
mkdir -p ~/.claude/mcp-servers/llm-chat
cp mcp-servers/llm-chat/server.py ~/.claude/mcp-servers/llm-chat/server.py
```

### Step 4：安装 Skills

```bash
mkdir -p ~/.claude/skills
cp -r skills/* ~/.claude/skills/
```

### Step 5：配置 ~/.claude/settings.json

以下为推荐配置（DeepSeek-V4-Pro 执行 + DeepSeek-R1 审查）。用 `which python3` 替换 `command` 中的 python3 路径，用 `echo $HOME` 替换路径中的 `$HOME`：

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "ms-your-modelscope-token",
    "ANTHROPIC_BASE_URL": "https://api-inference.modelscope.cn",
    "ANTHROPIC_MODEL": "deepseek-ai/DeepSeek-V4-Pro",
    "ANTHROPIC_SMALL_FAST_MODEL": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "API_TIMEOUT_MS": "3000000"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["$HOME/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "ms-your-modelscope-token",
        "LLM_BASE_URL": "https://api-inference.modelscope.cn/v1",
        "LLM_MODEL": "deepseek-ai/DeepSeek-R1"
      }
    }
  }
}
```

> **路径说明**：`$HOME` 需替换为实际路径（如 `/root` 或 `/home/用户名`），settings.json 不会自动展开 shell 变量。用 `which python3` 确认 python3 实际路径。

### Step 6：改写所有使用 Codex MCP 的 Skills

项目中有 **12 个 skill** 调用 `mcp__codex__codex`（依赖 OpenAI Responses API，ModelScope 不支持）。在启动 Claude Code 后执行以下指令，让它自动完成改写：

```
Read skills/auto-review-loop-llm/SKILL.md as a reference.
It replaces mcp__codex__codex with mcp__llm-chat__chat.
Now rewrite ALL other skills that use mcp__codex__codex / mcp__codex__codex-reply
to use mcp__llm-chat__chat instead, following the same pattern.
```

Claude Code 会自动扫描并改写所有相关 skill。

> **注意**：此操作只修改 `~/.claude/skills/` 中的本地副本，不影响仓库原文件。如需恢复，重新执行 Step 4 即可。

---

## 模型选择建议

| 场景 | 执行器 | 审查器 | 说明 |
|------|--------|--------|------|
| **推荐：能力均衡** | `deepseek-ai/DeepSeek-V4-Pro` | `deepseek-ai/DeepSeek-R1` | DeepSeek 系列综合最强 |
| 备选：速度优先 | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | `Qwen/Qwen3-235B-A22B-Instruct` | Qwen 系列，代码能力优秀 |
| 备选：跨模型 | `deepseek-ai/DeepSeek-V4-Pro` | `Qwen/Qwen3-235B-A22B-Instruct` | 不同模型族，更强对抗性 |

> **关于跨模型优势**：ARIS 的核心设计是执行器和审查器使用不同模型，形成真正的反馈循环。推荐使用不同模型族（如 DeepSeek 执行 + Qwen 审查）以最大化对抗性。

---

## 使用方法

配置完成后启动 Claude Code：

```bash
claude
```

### 直接可用（无需改写）

```
/auto-review-loop-llm "你的论文主题"    # 已原生支持 llm-chat MCP
```

### 改写后可用（Step 6 完成后）

```
/idea-discovery "你的研究方向"          # 工作流 1：文献 → idea → 查新 → 精炼 → 实验规划
/auto-review-loop "你的论文主题"        # 工作流 2：自动 review 循环
/paper-writing "NARRATIVE_REPORT.md"   # 工作流 3：叙事 → LaTeX → PDF
/research-pipeline "你的研究方向"       # 完整流水线：1 → 2 → 3
```

---

## 验证安装

### 1. 验证执行器端点（Anthropic 协议）

```bash
curl -s "https://api-inference.modelscope.cn/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ms-your-modelscope-token" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"deepseek-ai/DeepSeek-V4-Pro","max_tokens":50,"messages":[{"role":"user","content":"Say hello"}]}'
```

预期：返回包含 `"content"` 字段的 JSON。

### 2. 验证审查器端点（OpenAI 协议）

```bash
curl -s "https://api-inference.modelscope.cn/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ms-your-modelscope-token" \
  -d '{"model":"deepseek-ai/DeepSeek-R1","messages":[{"role":"user","content":"Say hello"}],"max_tokens":50}'
```

预期：返回包含 `"choices"` 字段的 JSON。

### 3. 验证 llm-chat MCP 服务器

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | \
  LLM_API_KEY="ms-your-modelscope-token" \
  LLM_BASE_URL="https://api-inference.modelscope.cn/v1" \
  LLM_MODEL="deepseek-ai/DeepSeek-R1" \
  python3 ~/.claude/mcp-servers/llm-chat/server.py
```

预期输出中包含：`"protocolVersion":"2024-11-05"`

### 4. 在 Claude Code 中端到端验证

```bash
claude
> 读一下这个项目，验证所有 skill 是否正常可用
```

---

## 与其他方案对比

| | 默认方案 | Coding Plan | **本方案（ModelScope）** | GLM + MiniMax |
|---|---|---|---|---|
| 执行器 | Claude Opus/Sonnet | kimi-k2.5 | **DeepSeek-V4-Pro** | GLM-5 (Z.ai) |
| 审查器 | GPT-5.4 (Codex MCP) | glm-5 | **DeepSeek-R1** | MiniMax-M2.7 |
| 需要 Claude API | 是 | 否 | **否** | 否 |
| 需要 OpenAI API | 是 | 否 | **否** | 否 |
| 费用 | 按量 | 套餐付费 | **免费（2000次/天）** | 按量 |
| 自动化限制 | 无 | 有（禁止无人值守） | **无** | 无 |
| API Key 数量 | 2 个 | 1 个 | **1 个** | 2 个 |
| 配置指南 | README | ALI_CODING_PLAN_GUIDE | **本文档** | LLM_API_MIX_MATCH_GUIDE |

**ModelScope 的独特优势**：免费 + 无自动化限制 + 一个 Key，是最低门槛的 ARIS 接入方式。

---

## 免费额度与限制

| 项目 | 限制 |
|------|------|
| 每日调用次数 | 2000 次（注册即送） |
| 单次请求 tokens | 取决于具体模型（通常 8K-128K） |
| 并发限制 | 有，具体见 [API 使用限制](https://www.modelscope.cn/docs/model-service/API-Inference/limits) |
| 自动化使用 | **允许**（无 Coding Plan 式限制） |

> 对于典型的 `/auto-review-loop`（4 轮，每轮 ~10 次 API 调用），一天可跑 ~50 次完整循环，远超日常使用需求。

---

## 常见问题

**Q：API Key 从哪里获取？**

登录 [ModelScope](https://www.modelscope.cn/)，进入 [我的令牌](https://www.modelscope.cn/my/myaccesstoken) 页面创建 SDK Token。格式为 `ms-xxxxxxxxxxxxxxxx`。

**Q：免费额度用完了怎么办？**

等待第二天自动刷新（每日 2000 次）。如需更高额度，可在 ModelScope 平台申请或使用其他提供商。

**Q：执行器报错 "401 Unauthorized"？**

确认使用的是 ModelScope SDK Token（`ms-xxx` 格式），非其他平台的 Key。

**Q：llm-chat MCP 工具在 Claude Code 中不出现？**

1. 确认 `settings.json` 中 `command` 的 python3 路径正确（`which python3`）
2. 确认 `args` 中的路径为绝对路径（不能包含 `$HOME`，需替换为实际值）
3. 重启 Claude Code

**Q：模型 ID 怎么找？**

在 [ModelScope 模型库](https://www.modelscope.cn/models) 搜索模型，页面 URL 中的路径即为模型 ID（如 `deepseek-ai/DeepSeek-R1`）。只有标注"API 推理"的模型才支持 API 调用。

**Q：如何切换审查器模型？**

修改 `~/.claude/settings.json` 中 `mcpServers.llm-chat.env.LLM_MODEL` 的值，重启 Claude Code 即可。

---

## 参考资料

- [ModelScope 官网](https://www.modelscope.cn/)
- [ModelScope API 推理文档](https://www.modelscope.cn/docs/model-service/API-Inference/intro)
- [ModelScope API 使用限制](https://www.modelscope.cn/docs/model-service/API-Inference/limits)
- [LLM API 混搭配置指南](LLM_API_MIX_MATCH_GUIDE.md)
- [阿里百炼 Coding Plan 指南](ALI_CODING_PLAN_GUIDE.md)
