# 🔀 替代模型组合

> [← 返回 README](../README_CN.md) · 用非默认的 executor / reviewer 组合跑 ARIS。

没有 Claude / OpenAI API？可以换用其他模型——同样的跨模型架构，不同的提供商。

> ⭐ **强烈推荐使用 Claude + GPT-5.5（默认组合）。** 这是经过最充分测试、最稳定的组合。替代方案可用但可能需要调整 prompt。

除了默认的 Claude × GPT-5.5，ARIS 还内置 **9 条替代路由（方案 A-I）**，覆盖 Z.ai 的 GLM、阿里百炼的 Kimi/Qwen/GLM/MiniMax 套餐、ModelScope 免费的 DeepSeek-V3.1、Codex 作为执行者搭配 Claude 或 Gemini 审稿、以及 Google Antigravity 作为执行器。

<details>
<summary><b>展开完整路由表</b> —— 默认 + 方案 A-I × 执行者 / 审稿人 / 是否需要 Claude API / 是否需要 OpenAI API / 配置指南链接</summary>

| | 执行者 | 审稿人 | 需要 Claude API？ | 需要 OpenAI API？ | 配置指南 |
|---|--------|--------|:---:|:---:|---------|
| **默认** ⭐ | Claude Opus/Sonnet | GPT-5.5（Codex MCP） | 是 | 是 | [快速开始](#quick-start) |
| **方案 A** | GLM-5（Z.ai） | GPT-5.5（Codex MCP） | 否 | 是 | [配置见下](#alt-a-glm--gpt) |
| **方案 B** | GLM-5（Z.ai） | MiniMax-M3 | 否 | 否 | [MINIMAX_MCP_GUIDE](docs/MINIMAX_MCP_GUIDE.md) |
| **方案 C** | 任意 CC 兼容 | 任意 OpenAI 兼容 | 否 | 否 | [LLM_API_MIX_MATCH_GUIDE](docs/LLM_API_MIX_MATCH_GUIDE.md) |
| **方案 D** | Kimi-K2.5 / Qwen3.5+ | GLM-5 / MiniMax-M3 | 否 | 否 | [ALI_CODING_PLAN_GUIDE](docs/ALI_CODING_PLAN_GUIDE.md) |
| **方案 E** 🆓 | DeepSeek-V3.1 / Qwen3-Coder | DeepSeek-R1 / Qwen3-235B | 否 | 否 | [MODELSCOPE_GUIDE](docs/MODELSCOPE_GUIDE.md) |
| **方案 F** | Codex CLI (GPT-5.5) | Codex `spawn_agent` (GPT-5.5) | 否 | 是 | [skills-codex/](skills/skills-codex/) |
| **方案 G** 🆕 | Codex CLI | Claude Code CLI（`claude-review` MCP） | 否* | 否* | [CODEX_CLAUDE_REVIEW_GUIDE_CN](docs/CODEX_CLAUDE_REVIEW_GUIDE_CN.md) |
| **方案 H** 🆕 | Antigravity（Claude Opus 4.6 / Gemini 3.1 Pro） | GPT-5.5（Codex MCP）或 llm-chat | 否 | 可选 | [ANTIGRAVITY_ADAPTATION_CN](docs/ANTIGRAVITY_ADAPTATION_CN.md) |
| **方案 I** 🆕 | Codex CLI | Gemini direct API（`gemini-review` MCP） | 否 | 否 | [CODEX_GEMINI_REVIEW_GUIDE_CN](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md) |

</details>

**怎么选：**

- **默认** —— 你有 Claude + OpenAI 双账号，想要最稳的路径。
- **方案 A** —— 只换执行者（Claude → GLM），审稿人保留 GPT-5.5 via Codex MCP。
- **方案 B** 或 **方案 E** —— 不用 Claude、不用 OpenAI API（方案 E 通过 ModelScope 免费）。
- **方案 C** 或 **方案 D** —— OpenAI 兼容 API 自由混搭（方案 D 用阿里一个 Key 跑双端）。
- **方案 G** 或 **方案 I** —— 保留 Codex 作为执行者，只换审稿人（Claude 或 Gemini）。
- **方案 H** —— 用 Antigravity 作为执行器（Claude Opus 4.6 或 Gemini 3.1 Pro），GPT-5.5 或任意 `llm-chat` 审稿。

\* 方案 G 通常依赖本地 Codex CLI 和 Claude Code CLI 的登录态；不强制要求 API key。

<details>
<summary><b>展开方案 C/D/E/G/H/I 的提供商细节</b></summary>

**方案 C** 已适配的提供商：GLM（Z.ai）、Kimi（Moonshot）、LongCat（美团）作为执行器；DeepSeek、MiniMax 作为审查器。任何 OpenAI 兼容 API 理论上均可通过通用 [`llm-chat`](mcp-servers/llm-chat/) MCP 服务器接入。

**方案 D** 使用[阿里百炼 Coding Plan](https://bailian.console.aliyun.com/)——一个 API Key 包含 4 款模型（Kimi、Qwen、GLM、MiniMax），双端点配置。

**方案 E** 使用 [ModelScope（魔搭社区）](https://www.modelscope.cn/)——**免费**（2000 次/天），一个 Key，无自动化限制。

**方案 G** 保持 Codex 作为执行者，但把审稿人切换成通过本地 `claude-review` MCP bridge 暴露出来的 Claude Code CLI，并用异步轮询处理长论文 / 长 review prompt。

**方案 H** 使用 [Google Antigravity](https://antigravity.google/) 作为执行器，原生支持 SKILL.md——可选 Claude Opus 4.6（Thinking）或 Gemini 3.1 Pro（high）作为执行模型。

**方案 I** 保持 Codex 作为执行者，只增加一层很薄的 `skills-codex-gemini-review` overlay，并通过本地 `gemini-review` MCP bridge 把 reviewer-aware 预定义 skills 默认接到 direct Gemini API。这是与现有 Codex+Claude 审稿路径最接近的 Gemini 版本，同时 skill 改动最少，而且连 poster PNG 审查也复用了同一个 bridge。免费层可用性、限速和数据处理条款仍以 Google 当前政策为准。

</details>

<a id="alt-a-glm--gpt"></a>

### 方案 A: GLM + GPT

只替换执行者（Claude → 通过 Z.ai 切到 GLM），保留 GPT-5.5 通过 Codex MCP 审稿。Codex CLI 复用你已有的 `OPENAI_API_KEY`（来自 `~/.codex/config.toml` 或环境变量），审稿端不需要额外配置。

<details>
<summary><b>展开方案 A 的安装命令与 <code>~/.claude/settings.json</code></b></summary>

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
codex setup   # 提示选模型时选 gpt-5.5
```

配置 `~/.claude/settings.json`：

```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "your_zai_api_key",
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5"
    },
    "mcpServers": {
        "codex": {
            "command": "/opt/homebrew/bin/codex",
            "args": ["mcp-server"]
        }
    }
}
```

</details>

### 方案 B: GLM + MiniMax

无需 Claude 或 OpenAI API。使用自定义 MiniMax MCP 服务器替代 Codex（因为 MiniMax 不支持 OpenAI 的 Responses API）。完整指南：[`docs/MINIMAX_MCP_GUIDE.md`](docs/MINIMAX_MCP_GUIDE.md)。

### 方案 C: 任意执行者 + 任意审稿人

通过通用 `llm-chat` MCP 服务器自由混搭，支持任意 OpenAI 兼容 API 作为审稿人。完整指南：[`docs/LLM_API_MIX_MATCH_GUIDE.md`](docs/LLM_API_MIX_MATCH_GUIDE.md)。

示例组合：GLM + DeepSeek、Kimi + MiniMax、Claude + DeepSeek、LongCat + GLM 等。

### 配置完成后：安装 Skills 并验证

推荐用上面 [§ 安装 Skills](#install-skills) 的项目级 symlink 安装——所有方案通用。下面的全局拷贝是 fallback，如果你更习惯把所有 skill 放到 `~/.claude/skills/` 也行。

<details>
<summary><b>展开全局拷贝 fallback 安装命令与非 Claude 执行者的验证 prompt</b></summary>

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
cp -r skills/* ~/.claude/skills/
claude
```

> **⚠️ 非 Claude 执行者（GLM、Kimi 等）：** 需要让模型先读一遍项目，确保 skill 能正确解析。尤其是当你已经[改写了 skill](#alternative-model-combinations)以使用不同的审查器 MCP（如 `mcp__llm-chat__chat` 替代 `mcp__codex__codex`）时——新执行器需要理解变更后的工具调用方式：
>
> ```
> 读一下这个项目，验证所有 skills 是否正常：
> /idea-creator, /research-review, /auto-review-loop, /novelty-check,
> /idea-discovery, /research-pipeline, /research-lit, /run-experiment,
> /analyze-results, /monitor-experiment, /pixel-art
> ```

</details>

> ⚠️ **注意：** 替代模型的行为可能与 Claude 和 GPT-5.5 有所不同。你可能需要微调 prompt 模板以获得最佳效果。核心的跨模型架构不变。


