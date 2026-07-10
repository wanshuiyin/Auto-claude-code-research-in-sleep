# 🔀 Alternative Model Combinations

> [← back to README](../README.md#12--alternative-model-combinations) · run ARIS with non-default executor / reviewer providers.

Don't have Claude / OpenAI API access? You can swap in other models — same cross-model architecture, different providers.

> ⭐ **We strongly recommend Claude + GPT-5.6-Sol (default setup).** It's the most tested and reliable combination. Alternative setups work but may require prompt tuning.

Beyond the default Claude × GPT-5.6-Sol route, ARIS ships **10 alternative routes (Alt A-I + C.1)** covering Z.ai's GLM, Alibaba's Kimi/Qwen/GLM/MiniMax bundle, ModelScope's free DeepSeek-V3.1, Codex-as-executor with Claude or Gemini reviewers, and Google Antigravity as the executor.

<details>
<summary><b>Show full routing table</b> — Default + Alt A-I × executor / reviewer / Claude-API needed / OpenAI-API needed / guide link</summary>

| | Executor | Reviewer | Need Claude API? | Need OpenAI API? | Guide |
|---|----------|----------|:---:|:---:|-------|
| **Default** ⭐ | Claude Opus/Sonnet | GPT-5.6-Sol (Codex MCP) | Yes | Yes | [Quick Start](#quick-start) |
| **Alt A** | GLM-5 (Z.ai) | GPT-5.6-Sol (Codex MCP) | No | Yes | [Setup below](#alt-a-glm--gpt) |
| **Alt B** | GLM-5 (Z.ai) | MiniMax-M3 | No | No | [MINIMAX_MCP_GUIDE](MINIMAX_MCP_GUIDE.md) |
| **Alt C** | Any CC-compatible | Any OpenAI-compatible | No | No | [LLM_API_MIX_MATCH_GUIDE](LLM_API_MIX_MATCH_GUIDE.md) |
| **Alt C.1** | Claude / any CC-compatible | OpenRouter pinned model via `llm-chat` | Optional | No | [OPENROUTER_GUIDE](OPENROUTER_GUIDE.md) |
| **Alt D** | Kimi-K2.5 / Qwen3.5+ | GLM-5 / MiniMax-M3 | No | No | [ALI_CODING_PLAN_GUIDE](ALI_CODING_PLAN_GUIDE.md) |
| **Alt E** 🆓 | DeepSeek-V3.1 / Qwen3-Coder | DeepSeek-R1 / Qwen3-235B | No | No | [MODELSCOPE_GUIDE](MODELSCOPE_GUIDE.md) |
| **Alt F** | Codex CLI (GPT-5.6-Sol) | Codex `spawn_agent` (GPT-5.6-Sol) | No | Yes | [skills-codex/](../skills/skills-codex/) |
| **Alt G** 🆕 | Codex CLI | Claude Code CLI (`claude-review` MCP) | No* | No* | [CODEX_CLAUDE_REVIEW_GUIDE](CODEX_CLAUDE_REVIEW_GUIDE.md) |
| **Alt H** 🆕 | Antigravity (Claude Opus 4.6 / Gemini 3.1 Pro) | GPT-5.6-Sol (Codex MCP) or any via llm-chat | No | Optional | [ANTIGRAVITY_ADAPTATION](ANTIGRAVITY_ADAPTATION.md) |
| **Alt I** 🆕 | Codex CLI | Gemini direct API (`gemini-review` MCP) | No | No | [CODEX_GEMINI_REVIEW_GUIDE](CODEX_GEMINI_REVIEW_GUIDE.md) |

</details>

**How to choose:**

- **Default** — you have Claude + OpenAI access and want the most tested route.
- **Alt A** — only swap Claude for GLM, keep GPT-5.6-Sol as reviewer via Codex MCP.
- **Alt B** or **Alt E** — no Claude API, no OpenAI API (Alt E is free via ModelScope).
- **Alt C** or **Alt D** — OpenAI-compatible mix-and-match (Alt D = one Alibaba key for both sides).
- **Alt C.1** — [OpenRouter](OPENROUTER_GUIDE.md) as an opt-in `llm-chat` reviewer backend: one key, many models; pin a concrete reviewer model and keep it in a different family from the executor.
- **Alt G** or **Alt I** — Codex stays as executor, only the reviewer changes (Claude or Gemini).
- **Alt H** — Antigravity as the executor (Claude Opus 4.6 or Gemini 3.1 Pro), GPT-5.6-Sol or any `llm-chat` reviewer.

\* Alt G normally relies on local Codex CLI and Claude Code CLI logins. Direct API keys are optional, not required.

<details>
<summary><b>Show detailed provider notes for Alt C/D/E/G/H/I</b></summary>

**Alt C** supports tested providers: GLM (Z.ai), Kimi (Moonshot), LongCat (Meituan) as executors; DeepSeek, MiniMax as reviewers. Any OpenAI-compatible API should also work via the generic [`llm-chat`](../mcp-servers/llm-chat/) MCP server.

**Alt D** uses [Alibaba Coding Plan](https://bailian.console.aliyun.com/) — one API key for both executor and reviewer, 4 models included (Kimi, Qwen, GLM, MiniMax).

**Alt E** uses [ModelScope](https://www.modelscope.cn/) — **free** (2000 calls/day), one key, no automation restrictions.

**Alt G** keeps Codex as executor but swaps the reviewer to Claude Code CLI via the local `claude-review` MCP bridge, with async polling for long paper/review prompts.

**Alt H** uses [Google Antigravity](https://antigravity.google/) as the executor with native SKILL.md support — choose Claude Opus 4.6 (Thinking) or Gemini 3.1 Pro (high) as the execution model.

**Alt I** keeps Codex as executor, adds only a thin `skills-codex-gemini-review` overlay, and routes the reviewer-aware predefined skills through the local `gemini-review` MCP bridge with direct Gemini API by default. It is the closest Gemini analogue to the existing Codex+Claude review path, while minimizing skill changes and now also covers poster PNG review via the same bridge. Free-tier availability, rate limits, and data-use terms remain subject to Google's current policy.

</details>

<a id="alt-a-glm--gpt"></a>

### 12.1 Alt A: GLM + GPT

Only replace the executor (Claude → GLM via Z.ai), keep GPT-5.6-Sol as reviewer via Codex MCP. Codex CLI reuses your existing `OPENAI_API_KEY` (from `~/.codex/config.toml` or environment); no extra reviewer-side config.

<details>
<summary><b>Show Alt A setup commands and <code>~/.claude/settings.json</code></b></summary>

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
codex setup   # set model to gpt-5.6-sol
```

Configure `~/.claude/settings.json`:

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

### 12.2 Alt B: GLM + MiniMax

No Claude or OpenAI API needed. Uses a custom MiniMax MCP server instead of Codex (because MiniMax doesn't support OpenAI's Responses API). Full guide: [`docs/MINIMAX_MCP_GUIDE.md`](MINIMAX_MCP_GUIDE.md).

### 12.3 Alt C: Any Executor + Any Reviewer

Mix and match freely using the generic `llm-chat` MCP server. Supports any OpenAI-compatible API as reviewer. Full guide: [`docs/LLM_API_MIX_MATCH_GUIDE.md`](LLM_API_MIX_MATCH_GUIDE.md).

Example combinations: GLM + DeepSeek, Kimi + MiniMax, Claude + DeepSeek, LongCat + GLM, etc.

### 12.4 After Setup: Install Skills & Verify

Use the project-local symlink install from [§ Install Skills above](#install-skills) — that's the recommended path for all routes. The global-copy fallback below also works if you prefer everything under `~/.claude/skills/`.

<details>
<summary><b>Show global-copy fallback install commands and the non-Claude executor verification prompt</b></summary>

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
cp -r skills/* ~/.claude/skills/
claude
```

> **⚠️ For non-Claude executors (GLM, Kimi, etc.):** Let the model read through the project once to ensure skills are correctly parsed. This is especially important if you've [rewritten skills](#alternative-model-combinations) to use a different reviewer MCP (e.g., `mcp__llm-chat__chat` instead of `mcp__codex__codex`) — the new executor needs to understand the changed tool call patterns:
>
> ```
> Read through this project and verify all skills are working:
> /idea-creator, /research-review, /auto-review-loop, /novelty-check,
> /idea-discovery, /research-pipeline, /research-lit, /run-experiment,
> /analyze-results, /monitor-experiment, /pixel-art
> ```

</details>

> ⚠️ **Note:** Alternative models may behave differently from Claude and GPT-5.6-Sol. You may need to tune prompt templates for best results. The core cross-model architecture remains the same.


