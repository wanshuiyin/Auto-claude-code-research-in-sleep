# OpenRouter Integration Guide

This document explains how to use [OpenRouter](https://openrouter.ai/) as an ARIS reviewer backend through the existing [`llm-chat`](../mcp-servers/llm-chat/) MCP server. This is useful when you want a free or pay-as-you-go alternative for review calls without replacing ARIS's default assurance routing.

> For mandatory audit gates, keep ARIS's default Codex MCP reviewer unless you have made a deliberate, audited routing change. Executor and reviewer must be pinned to different model families.

---

## Background

### What is OpenRouter

[OpenRouter](https://openrouter.ai/) is a unified AI model API gateway that provides:
- **200+ models**: OpenAI, Anthropic, Google, DeepSeek, MiniMax, Qwen, and more
- **Free models**: Some models offer free tiers, such as `minimax/minimax-m2.5:free`
- **Unified interface**: Standard OpenAI-compatible API, one key for many model providers
- **Transparent pricing**: Free models plus pay-as-you-go billing

### Recommended Reviewer Models

| Model | Provider family | Purpose | Notes |
|-------|-----------------|---------|-------|
| `minimax/minimax-m2.5:free` | MiniMax | Reviewer | Good free reviewer candidate when executor is not MiniMax |
| `meta-llama/llama-3.1-70b-instruct` | Meta Llama | Reviewer | Paid pinned fallback when executor is not Llama |

> Full model list: https://openrouter.ai/models
>
> Use a pinned model ID rather than the [Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-models-router) for any skill that emits an assurance-gated verdict, and ensure executor and reviewer pin to different model families.

---

## Dual-Layer Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Claude Code (CLI)                      │
│                                                           │
│  ┌──────────────────┐       ┌─────────────────────────┐  │
│  │     Executor     │──────▶│        Reviewer          │  │
│  │  (Claude CLI)    │       │   (llm-chat MCP)         │  │
│  │                  │       │                         │  │
│  │  ANTHROPIC_*     │       │  LLM_* environment       │  │
│  │  variables       │       │  variables               │  │
│  └──────────────────┘       └─────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

| Role | Protocol | Endpoint |
|------|----------|----------|
| Executor | Anthropic-compatible | Anthropic, OpenRouter, or another Claude Code-compatible endpoint |
| Reviewer | OpenAI-compatible | `https://openrouter.ai/api/v1` through `llm-chat` |

OpenRouter should be treated as an opt-in reviewer backend via `/auto-review-loop-llm`. Production audit and assurance skills that depend on cross-family review should stay on `mcp__codex__codex` unless reviewer routing is intentionally changed and re-audited.

---

## Getting an API Key

1. Visit [OpenRouter](https://openrouter.ai/) to register an account.
2. Go to the [Keys page](https://openrouter.ai/keys) and create an API key.
3. Key format: `sk-or-v1-xxxxxxxxxxxxxxxx`.
4. Free models can be used without deposit, subject to OpenRouter's current limits.

---

## Installation Steps

### Prerequisites

- Claude Code CLI installed: `npm install -g @anthropic-ai/claude-code`
- Python 3 available
- OpenRouter API key obtained
- A local ARIS checkout

### Step 1: Clone ARIS

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git /path/to/aris_repo
cd /path/to/aris_repo
```

### Step 2: Install Python Dependencies

```bash
pip3 install -r mcp-servers/llm-chat/requirements.txt
```

### Step 3: Install ARIS Skills with the Standard Installer

```bash
# Standard ARIS install: points symlinks from a target project into this ARIS repo.
bash /path/to/aris_repo/tools/install_aris.sh /path/to/your-project
```

Do not pass `$PWD` from inside the ARIS repo itself. The installer should target your paper or experiment project, not the ARIS checkout. It manages per-skill symlinks, the installed-skill manifest, the `.aris/tools/` helper chain (plus the global pointer file `~/.aris/repo`, which lets the same chain resolve even for a global copy-install with no per-project manifest), and reconcile/uninstall/migration paths.

### Step 4: Deploy the llm-chat MCP Server

```bash
mkdir -p ~/.claude/mcp-servers/llm-chat
cp mcp-servers/llm-chat/server.py ~/.claude/mcp-servers/llm-chat/server.py
```

This manual copy is only for the MCP server, which `install_aris.sh` does not manage. Do not copy `skills/*` by hand.

### Step 5: Configure `~/.claude/settings.json`

**Option A: Executor also uses OpenRouter**

Use a specific Anthropic-family model for Claude Code execution and a non-Anthropic OpenRouter model for review.

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

**Option B: Executor uses another API and reviewer uses OpenRouter (recommended)**

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

> **Path notes**: Replace `$HOME` with the actual path, such as `/root` or `/home/username`, and confirm the `python3` path with `which python3`.

---

## Use in ARIS

Use the already-shipped `/auto-review-loop-llm` skill when you want OpenRouter-backed review:

```bash
claude
> /auto-review-loop-llm "your paper topic"
```

Do not batch-rewrite upstream skills from `mcp__codex__codex` to `mcp__llm-chat__chat`. Skills with `assurance: submission`, such as production paper audits and proof/citation checks, rely on ARIS's reviewer independence contract and should remain on the default Codex MCP path unless you intentionally update reviewer routing.

---

## Verification

### 1. Verify Reviewer Endpoint

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

Expected: JSON response containing a `"choices"` field.

### 2. End-to-End Verification in Claude Code

```bash
claude
> Read the project and verify that the /auto-review-loop-llm skill is working properly
```

---

## Comparison with Other Solutions

| | Default | Coding Plan | ModelScope | **OpenRouter** |
|---|---|---|---|---|
| Executor | Claude Opus | kimi-k2.5 | DeepSeek-V3 | 200+ models available |
| Reviewer | GPT-5.6-Sol xhigh fresh thread | glm-5 | DeepSeek-R1 | 200+ pinned models available |
| Free Options | No | No | **Yes, 2000/day subject to current ModelScope policy** ([source](https://developer.aliyun.com/article/1644361)) | **Yes, free models subject to OpenRouter limits** |
| API Key Count | 2 | 1 | 1 | **1** |
| Model Selection | Limited | 4 types | 1000+ types | **200+ types** |
| Pricing | Pay-as-you-go | Package | Free | Free + pay-as-you-go |

**OpenRouter's advantage**: one key can access many reviewer model families, including free options. For ARIS audit correctness, pin the reviewer model explicitly.

---

## FAQ

**Q: What is `openrouter/free`?**

`openrouter/free` is OpenRouter's Free Models Router. It auto-selects from currently available free models and may return different model families over time. It is fine for casual experiments, but do not use it for ARIS assurance-gated review.

**Q: What are the limitations of free models?**

Free models have rate limits and availability can change. For heavy or reproducible usage, use a paid pinned model.

**Q: How do I switch reviewer models?**

Modify the `LLM_MODEL` value in `settings.json`, ensure the model is from a different family than the executor, and restart Claude Code.

**Q: Does OpenRouter support Claude Code execution?**

OpenRouter can be used as the Claude Code executor backend for compatible models, but this guide recommends OpenRouter first as a reviewer backend through `llm-chat`.

**Q: Why is the llm-chat MCP call failing?**

Check:
1. API key format is correct and starts with `sk-or-v1-`.
2. Model ID is pinned and includes a namespace, such as `minimax/minimax-m2.5:free`.
3. Account has sufficient free quota or paid balance.

---

## References

- [OpenRouter Official Website](https://openrouter.ai/)
- [OpenRouter Model List](https://openrouter.ai/models)
- [OpenRouter Documentation](https://openrouter.ai/docs)
- [OpenRouter Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-models-router)
- [ModelScope quota note](https://developer.aliyun.com/article/1644361)
- [LLM API Mix & Match Guide](LLM_API_MIX_MATCH_GUIDE.md)
