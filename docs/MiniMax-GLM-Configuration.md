# MiniMax-M2.7 + GLM 配置教程 (Alt C)

## 概述

此配置方案使用 **MiniMax-M2.7** 作为执行者（Executor），**GLM-5** 作为审稿人（Reviewer）。

与方案 B（GLM + MiniMax）正好相反——适合需要 MiniMax 强大推理能力作为主力，GLM 进行代码审查的场景。

## 模型组合对比

| 角色 | 方案 A：GLM + GPT | 方案 B：GLM + MiniMax | 方案 C：MiniMax + GLM |
|------|-------------------|----------------------|----------------------|
| 执行者（Claude Code） | GLM-5（智谱 API） | GLM-5（智谱 API） | MiniMax-M2.7（MiniMax API） |
| 审稿人（Skill 工具） | `mcp__codex__codex` | `mcp__llm-chat__chat` | `mcp__llm-chat__chat` |
| 需要 OpenAI API？ | 是 | **否** | **否** |

## 配置步骤

### 第 1 步：安装 Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### 第 2 步：克隆 MCP Servers

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep/mcp-servers/llm-chat
pip install -r requirements.txt
cd ../..
```

### 第 3 步：配置 `~/.claude/settings.json`

编辑 `~/.claude/settings.json`：

```bash
nano ~/.claude/settings.json
```

添加以下配置：

```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "your_minimax_api_key",
        "ANTHROPIC_BASE_URL": "https://api.minimax.chat/v1/",
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "MiniMax-M2.7",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "MiniMax-M2.7",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "MiniMax-M2.7"
    },
    "mcpServers": {
        "llm-chat": {
            "command": "python",
            "args": [
                "/path/to/mcp-servers/llm-chat/server.py"
            ],
            "env": {
                "LLM_API_KEY": "your_glm_api_key",
                "LLM_BASE_URL": "https://open.bigmodel.cn/api/paas/v4/",
                "LLM_MODEL": "GLM-5",
                "LLM_SERVER_NAME": "glm"
            }
        }
    }
}
```

> **注意**：将 `/path/to/mcp-servers/llm-chat/server.py` 替换为实际路径。

保存：`Ctrl+O` → `Enter` → `Ctrl+X`

### 第 4 步：验证配置

```bash
# 启动 Claude Code
claude

# 验证 MiniMax 连接
> 请简单介绍一下你自己，告诉我你是什么模型

# 验证 GLM MCP
> 请使用 mcp__glm__chat 工具审查一段简单的代码
```

## 配置说明

### 执行者配置（MiniMax）

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `ANTHROPIC_AUTH_TOKEN` | MiniMax API Key | 从 [MiniMax 开放平台](https://www.minimaxi.com/) 获取 |
| `ANTHROPIC_BASE_URL` | `https://api.minimax.chat/v1/` | MiniMax Claude 兼容端点 |
| `ANTHROPIC_DEFAULT_*_MODEL` | `MiniMax-M2.7` | 使用 MiniMax-M2.7 作为所有模型 |

### 审稿人配置（GLM via llm-chat MCP）

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `LLM_API_KEY` | GLM API Key | 从 [智谱开放平台](https://open.bigmodel.cn/) 获取 |
| `LLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | GLM OpenAI 兼容端点 |
| `LLM_MODEL` | `GLM-5` | 使用 GLM-5 作为审稿模型 |
| MCP 工具 | `mcp__glm__chat` | 调用 GLM 进行审稿 |

## API 密钥获取

### MiniMax API Key

1. 访问 [MiniMax 开放平台](https://www.minimaxi.com/)
2. 注册/登录账号
3. 进入「API 密钥管理」
4. 创建新的 API Key

### GLM API Key

1. 访问 [智谱开放平台](https://open.bigmodel.cn/)
2. 注册/登录账号
3. 进入「API Keys」页面
4. 创建新的 API Key

## 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Auto-claude-code-research                │
│                    (Sleep Mode Research)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      MiniMax-M2.7             │
              │      (Executor)               │
              │                               │
              │  • 理解研究任务                 │
              │  • 执行代码编写                 │
              │  • 运行测试验证                 │
              │  • 生成研究报告                 │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      GLM-5 (via llm-chat)    │
              │      (Reviewer)               │
              │                               │
              │  • 代码质量审查                │
              │  • 逻辑正确性验证              │
              │  • 安全漏洞检查                │
              │  • 改进建议生成                │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         最终输出               │
              │    (代码 + 报告 + 审查意见)    │
              └───────────────────────────────┘
```

## 关键区别

此方案与方案 B 的关键区别：

| | 方案 B：GLM + MiniMax | 方案 C：MiniMax + GLM |
|--|----------------------|----------------------|
| 审稿人 API | MiniMax OpenAI 兼容 API | GLM OpenAI 兼容 API |
| MCP 工具 | `mcp__codex__codex` | `mcp__glm__chat` |
| 模型 | MiniMax-M2.5 | GLM-5 |

## 常见问题

### Q: MiniMax API 返回错误

检查以下几点：
- API Key 是否正确配置
- Base URL 是否正确（注意末尾的 `/`）
- 账户余额是否充足

### Q: GLM MCP 未生效

确保：
- `llm-chat/server.py` 路径正确
- Python 依赖已安装 (`pip install -r requirements.txt`)
- `mcp__glm__chat` 工具可用
- 网络可访问智谱 API 端点

## 参考

- [Auto-claude-code-research-in-sleep 主项目](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
- [方案 A：GLM + GPT](./README.md#alt-a-glm--gpt)
- [方案 B：GLM + MiniMax](./README.md#alt-b-glm--minimax)

---

*此配置方案由社区贡献，适用于 Auto-claude-code-research-in-sleep 项目*
