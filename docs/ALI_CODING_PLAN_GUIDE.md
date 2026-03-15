# 阿里百炼 Coding Plan 接入指南

本文档说明如何使用阿里百炼 Coding Plan 的一套 API Key 驱动 ARIS 全流程，无需 Claude 或 OpenAI API。

---

## 背景

### Coding Plan 是什么

[阿里百炼 Coding Plan](https://bailian.console.aliyun.com/) 是阿里云推出的 AI 编程套餐，一个专属 API Key 打通四款国产顶级模型，同时兼容 OpenAI 和 Anthropic 两大主流 API 协议。

### 支持的模型

| 模型 | 图像理解 | 推荐用途 | 速度参考 |
|------|---------|---------|---------|
| `qwen3.5-plus` | 是 | 执行器轻量任务 / 读图 | ~94 tokens/s |
| `kimi-k2.5` | 是 | 执行器主力（综合能力强） | ~42 tokens/s |
| `glm-5` | 否 | 审查器主力（推理质量高） | ~51 tokens/s |
| `MiniMax-M2.5` | 否 | 审查器备选（速度最快） | ~101 tokens/s |

### 为什么不能直接用 Codex MCP

原版 ARIS 的审查器使用 Codex MCP，而 Codex CLI 硬编码调用 OpenAI 专有的 **Responses API** (`/v1/responses`)，第三方 API 提供商（包括 Coding Plan）均不支持该接口。

**解决方案**：使用项目内置的 `llm-chat` MCP 服务器，它调用标准 **Chat Completions API** (`/v1/chat/completions`)，兼容所有 OpenAI 兼容端点，包括 Coding Plan。

相关讨论：[OpenAI Codex GitHub #7782](https://github.com/openai/codex/discussions/7782)

---

## 重要：使用条款限制

> **警告**：阿里百炼官方文档明确规定：
>
> *"仅限在编程工具（如 Claude Code、OpenClaw 等）中使用，禁止以 API 调用的形式用于自动化脚本、自定义应用程序后端或任何非交互式批量调用场景。将套餐 API Key 用于允许范围之外的调用将被视为违规或滥用，可能会导致订阅被暂停或 API Key 被封禁。"*

使用前请了解以下风险评估：

| 使用场景 | 是否符合条款 | 风险 |
|---------|------------|------|
| 交互式使用（手动触发 skill，人在回路） | **符合** | 低 |
| 半自动（每轮需人工确认，`AUTO_PROCEED: false`） | 基本符合 | 低 |
| 过夜全自动循环（`/auto-review-loop` 无人值守） | **违反** | 高，可能封禁 Key |
| llm-chat MCP 作为审查器被 Claude Code 调用 | 存在争议 | 中，取决于阿里方面解释 |

**建议**：如需完全自动化的过夜科研循环，考虑改用按量计费的百炼 API Key，或其他没有此限制的提供商（DeepSeek、MiniMax 直连等）。

---

## 双层架构

Coding Plan 提供两套 API 端点，分别对应 ARIS 的两个角色：

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
| 执行器（Claude CLI） | Anthropic 兼容 | `https://coding.dashscope.aliyuncs.com/apps/anthropic` |
| 审查器（llm-chat MCP） | OpenAI 兼容 | `https://coding.dashscope.aliyuncs.com/v1` |

两个端点使用**同一个 Coding Plan 专属 API Key**，无需分别申请。

---

## 安装步骤

### 前置条件

- Claude Code CLI 已安装：`npm install -g @anthropic-ai/claude-code`
- Python 3 可用：`python3 --version`（用 `which python3` 确认路径）
- 已购买阿里百炼 Coding Plan 套餐并获取专属 API Key（在套餐页面直接获取，与百炼按量 Key **不互通**）

### Step 1：克隆仓库

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
```

### Step 2：安装 Python 依赖

```bash
pip3 install httpx
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

以下为推荐配置（kimi-k2.5 执行 + glm-5 审查）。用 `which python3` 替换 `command` 中的 python3 路径，用 `echo $HOME` 替换路径中的 `$HOME`：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-coding-plan-api-key",
    "ANTHROPIC_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "kimi-k2.5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "qwen3.5-plus",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "MiniMax-M2.5",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "6000"
  },
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["$HOME/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-coding-plan-api-key",
        "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
        "LLM_MODEL": "glm-5"
      }
    }
  }
}
```

> **Linux 路径说明**：`$HOME` 通常为 `/root`（root 用户）或 `/home/用户名`。运行 `echo $HOME` 确认，并将配置中 `args` 里的 `$HOME` 替换为实际路径（settings.json 不会自动展开 shell 变量）。同理，用 `which python3` 确认 python3 实际路径。

### Step 6：改写所有使用 Codex MCP 的 Skills

项目中有 **12 个 skill** 调用 `mcp__codex__codex`（依赖 OpenAI Responses API，Coding Plan 不支持）。在启动 Claude Code 后执行以下指令，让它自动完成改写：

```
Read skills/auto-review-loop-llm/SKILL.md as a reference.
It replaces mcp__codex__codex with mcp__llm-chat__chat.
Now rewrite ALL other skills that use mcp__codex__codex / mcp__codex__codex-reply
to use mcp__llm-chat__chat instead, following the same pattern.
```

Claude Code 会自动：
1. 扫描 `~/.claude/skills/` 中所有使用 Codex MCP 的 skill 文件
2. 参考 `auto-review-loop-llm` 的写法（MCP 优先 + curl fallback）
3. 逐个改写为调用 `mcp__llm-chat__chat`

> **注意**：此操作只修改 `~/.claude/skills/` 中的本地副本，不影响仓库原文件。如需恢复，重新执行 Step 4 即可。

---

## 模型选择建议

| 场景 | 执行器（OPUS 位） | 审查器（llm-chat） | 说明 |
|------|-----------------|------------------|------|
| **推荐：能力均衡** | `kimi-k2.5` | `glm-5` | kimi 执行综合能力强，glm-5 推理审查严谨 |
| 备选：速度优先 | `qwen3.5-plus` | `MiniMax-M2.5` | 两者出词最快，适合快速迭代和调试 |
| 备选：测试阶段 | `qwen3.5-plus` | `glm-5` | 执行轻量省请求次数，审查保持质量 |

> **关于跨模型优势**：ARIS 的核心设计是执行器和审查器使用不同模型，互不审自己的输出，形成真正的反馈循环。如果两端用同一模型（如都用 kimi-k2.5），会部分削弱这一优势。

---

## 使用方法

配置完成后，按如下方式启动 Claude Code 并使用 skill：

```bash
claude
```

### 直接可用（无需改写）

```
/auto-review-loop-llm "你的论文主题"    # 已原生支持 llm-chat MCP
```

### 改写后可用（Step 6 完成后）

```
/idea-discovery "你的研究方向"          # 工作流 1：文献 → idea → 查新 → 实验
/auto-review-loop "你的论文主题"        # 工作流 2：自动 review 循环
/paper-writing "NARRATIVE_REPORT.md"   # 工作流 3：叙事 → LaTeX → PDF
/research-pipeline "你的研究方向"       # 完整流水线：1 → 2 → 3
```

---

## 验证安装

### 1. 验证执行器端点（Anthropic 协议）

```bash
curl -s "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-coding-plan-api-key" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"kimi-k2.5","max_tokens":50,"messages":[{"role":"user","content":"Say hello"}]}'
```

预期：返回包含 `"content"` 字段的 JSON，其中有模型回复文本。

### 2. 验证审查器端点（OpenAI 协议）

```bash
curl -s "https://coding.dashscope.aliyuncs.com/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-coding-plan-api-key" \
  -d '{"model":"glm-5","messages":[{"role":"user","content":"Say hello"}],"max_tokens":50}'
```

预期：返回包含 `"choices"` 字段的 JSON，其中有模型回复文本。

### 3. 验证 llm-chat MCP 服务器

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | \
  LLM_API_KEY="your-coding-plan-api-key" \
  LLM_BASE_URL="https://coding.dashscope.aliyuncs.com/v1" \
  LLM_MODEL="glm-5" \
  python3 ~/.claude/mcp-servers/llm-chat/server.py
```

预期输出中包含：`"protocolVersion":"2024-11-05"`

### 4. 在 Claude Code 中端到端验证

```bash
claude
> 读一下这个项目，验证 /auto-review-loop-llm skill 是否正常可用，列出可识别的所有 skill
```

---

## 文件结构总览

```
~/.claude/
├── settings.json                        # 包含 Coding Plan 执行器 + llm-chat MCP 配置
├── mcp-servers/
│   └── llm-chat/
│       └── server.py                    # 通用 LLM MCP 服务器（支持任意 OpenAI 兼容 API）
└── skills/
    ├── auto-review-loop-llm/
    │   └── SKILL.md                     # 已原生支持 llm-chat MCP，无需改写
    ├── idea-creator/
    │   └── SKILL.md                     # Step 6 改写后调用 mcp__llm-chat__chat
    ├── research-review/
    │   └── SKILL.md                     # Step 6 改写后调用 mcp__llm-chat__chat
    ├── novelty-check/
    │   └── SKILL.md                     # Step 6 改写后调用 mcp__llm-chat__chat
    └── ...（其余 11 个 skill 类似）

项目目录（运行时生成）/
├── AUTO_REVIEW.md                       # 审查日志（自动追加）
└── REVIEW_STATE.json                    # 状态持久化，支持断点恢复
```

---

## 与其他方案对比

| | 默认方案 | **本方案（Coding Plan）** | MiniMax 方案 | GLM + DeepSeek |
|---|---|---|---|---|
| 执行器 | Claude Opus/Sonnet | kimi-k2.5 / qwen3.5-plus | GLM-5 (Z.ai) | GLM-5 (Z.ai) |
| 审查器 | GPT-5.4 (Codex MCP) | glm-5 / MiniMax-M2.5 | MiniMax-M2.5 | DeepSeek |
| 需要 Claude API | 是 | **否** | 否 | 否 |
| 需要 OpenAI API | 是 | **否** | 否 | 否 |
| API Key 数量 | 2 个 | **1 个** | 2 个 | 2 个 |
| 配置指南 | README 快速开始 | **本文档** | MINIMAX_MCP_GUIDE | LLM_API_MIX_MATCH_GUIDE |

---

## 常见问题

**Q：执行器报错 "401 Unauthorized"？**

Coding Plan 专属 API Key 与百炼平台按量调用 Key 不互通。确认在 [Coding Plan 套餐页面](https://bailian.console.aliyun.com/) 获取的是套餐专属 Key，而非普通百炼 Key。

**Q：llm-chat MCP 工具在 Claude Code 中不出现？**

1. 检查 `/tmp/llm-chat-mcp-debug.log` 中的错误信息
2. 确认 `settings.json` 中 `command` 的 python3 路径正确（`which python3`）
3. 确认 `args` 中的路径为绝对路径，不能包含未展开的 `$HOME`（需替换为 `/root` 或实际路径）
4. 重启 Claude Code

**Q：改写后 skill 仍然调用 mcp__codex__codex？**

检查 `~/.claude/skills/` 下对应 SKILL.md 文件内容是否已更新。若未改写，重新执行 Step 6 的指令。

**Q：Linux 上 python3 路径在哪？**

运行 `which python3` 确认。常见路径：`/usr/bin/python3`。若使用 conda/venv 环境，路径会不同（如 `/root/miniconda3/envs/xxx/bin/python3`）。

**Q：过夜自动运行安全吗？**

Coding Plan 明确禁止"非交互式批量调用"，过夜无人值守的自动化循环存在封禁风险。建议改用百炼按量计费 Key 或其他无此限制的提供商。

**Q：如何切换审查器模型（如从 glm-5 改为 MiniMax-M2.5）？**

修改 `~/.claude/settings.json` 中 `mcpServers.llm-chat.env.LLM_MODEL` 的值，重启 Claude Code 即可生效。

---

## 参考资料

- [阿里百炼 Coding Plan 文档](https://help.aliyun.com/zh/model-studio/other-tools-coding-plan)
- [阿里百炼 Coding Plan 常见问题](https://www.alibabacloud.com/help/zh/model-studio/coding-plan-faq)
- [OpenAI Codex Responses API 讨论 #7782](https://github.com/openai/codex/discussions/7782)
- [LLM API 混搭配置指南](LLM_API_MIX_MATCH_GUIDE.md)
- [MiniMax MCP 集成指南](MINIMAX_MCP_GUIDE.md)
- [Claude Code 文档](https://docs.anthropic.com/claude-code)
