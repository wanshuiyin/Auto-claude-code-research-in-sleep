# OrcaRouter Integration Guide

This document explains how to use [OrcaRouter](https://www.orcarouter.ai) as an ARIS reviewer backend through the existing [`llm-chat`](../mcp-servers/llm-chat/) MCP server, and optionally as the Claude Code executor backend. This is useful when you want one key to reach many reviewer model families without replacing ARIS's default assurance routing.

> For mandatory audit gates, keep ARIS's default Codex MCP reviewer unless you have made a deliberate, audited routing change. Executor and reviewer must be pinned to different model families.

---

## Background

### What is OrcaRouter

[OrcaRouter](https://www.orcarouter.ai) is a unified AI model API gateway that provides:
- **180+ models**: OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, Moonshot, Z.ai, MiniMax, and more
- **Two protocols on one key**: an OpenAI-compatible `/v1/chat/completions` endpoint for the reviewer, and an Anthropic-compatible `/v1/messages` endpoint that Claude Code can use as the executor
- **Named routers**: `orcarouter/auto`, `orcarouter/fusion` and `orcarouter/free` select an upstream per request instead of pinning one model
- **Transparent pricing**: pay-as-you-go, with usage and routing visible in the console

It also runs gateway-level, zero-trust security for AI agents on the same endpoint — screening every prompt/response and governing every tool call on a default-deny basis, with no application code changes. For ARIS this means reviewer traffic can be screened centrally without touching any skill.

### Recommended Reviewer Models

| Model | Provider family | Purpose | Notes |
|-------|-----------------|---------|-------|
| `minimax/minimax-m3` | MiniMax | Reviewer | Good default reviewer when the executor is Claude or GLM |
| `deepseek/deepseek-v4-pro` | DeepSeek | Reviewer | Strong reasoning reviewer, different family from Claude and GPT |
| `z-ai/glm-5.2` | Z.ai GLM | Reviewer | Use when the executor is not GLM |
| `openai/gpt-5.6-sol` | OpenAI | Reviewer | Closest match to the ARIS default reviewer without a separate OpenAI key |

> Full model list: https://www.orcarouter.ai/models
>
> Use a pinned model ID rather than `orcarouter/auto` or `orcarouter/free` for any skill that emits an assurance-gated verdict, and ensure executor and reviewer pin to different model families.

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
| Executor | Anthropic-compatible | Anthropic, OrcaRouter (`https://api.orcarouter.ai`), or another Claude Code-compatible endpoint |
| Reviewer | OpenAI-compatible | `https://api.orcarouter.ai/v1` through `llm-chat` |

OrcaRouter should be treated as an opt-in reviewer backend via `/auto-review-loop-llm`. Production audit and assurance skills that depend on cross-family review should stay on `mcp__codex__codex` unless reviewer routing is intentionally changed and re-audited.

---

## Getting an API Key

1. Visit [OrcaRouter](https://www.orcarouter.ai) to register an account.
2. Go to the [console](https://www.orcarouter.ai/console) and create an API key.
3. Key format: `sk-orca-xxxxxxxxxxxxxxxx`.
4. The same key works for both the reviewer (`/v1/chat/completions`) and executor (`/v1/messages`) endpoints.

---

## Installation Steps

### Prerequisites

- Claude Code CLI installed: `npm install -g @anthropic-ai/claude-code`
- Python 3 available
- OrcaRouter API key obtained
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

**Option A: Executor also uses OrcaRouter**

One key for both sides. Note that `ANTHROPIC_BASE_URL` is the bare host with **no** `/v1` suffix, and that every executor model must be pinned with its vendor namespace.

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

> **Set all three `ANTHROPIC_DEFAULT_*_MODEL` pins.** OrcaRouter routes on namespaced model IDs, so the bare names Claude Code would otherwise send (for example `claude-sonnet-4-6`) return `model_not_found`. Without the pins the executor fails on the first call.

**Option B: Executor uses another API and reviewer uses OrcaRouter (recommended)**

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

> **Path notes**: Replace `$HOME` with the actual path, such as `/root` or `/home/username`, and confirm the `python3` path with `which python3`.

---

## Use in ARIS

Use the already-shipped `/auto-review-loop-llm` skill when you want OrcaRouter-backed review:

```bash
claude
> /auto-review-loop-llm "your paper topic"
```

Do not batch-rewrite upstream skills from `mcp__codex__codex` to `mcp__llm-chat__chat`. Skills with `assurance: submission`, such as production paper audits and proof/citation checks, rely on ARIS's reviewer independence contract and should remain on the default Codex MCP path unless you intentionally update reviewer routing.

---

## Verification

### 1. Verify Reviewer Endpoint

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

Expected: JSON response containing a `"choices"` field.

### 2. Verify Executor Endpoint (only for Option A)

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

Expected: JSON response containing a `"content"` array. If you get `model_not_found`, the model ID is missing its vendor namespace.

### 3. End-to-End Verification in Claude Code

```bash
claude
> Read the project and verify that the /auto-review-loop-llm skill is working properly
```

---

## Comparison with Other Solutions

| | Default | Coding Plan | ModelScope | **OrcaRouter** |
|---|---|---|---|---|
| Executor | Claude Opus | kimi-k2.5 | DeepSeek-V3 | Claude family via Anthropic-compatible endpoint |
| Reviewer | GPT-5.6-Sol xhigh fresh thread | glm-5 | DeepSeek-R1 | 180+ pinned models available |
| Free Options | No | No | **Yes, 2000/day subject to current ModelScope policy** ([source](https://developer.aliyun.com/article/1644361)) | No, pay-as-you-go |
| API Key Count | 2 | 1 | 1 | **1 (covers both executor and reviewer)** |
| Model Selection | Limited | 4 types | 1000+ types | **180+ types** |
| Pricing | Pay-as-you-go | Package | Free | Pay-as-you-go |

**OrcaRouter's advantage**: a single key covers both the Anthropic-compatible executor endpoint and the OpenAI-compatible reviewer endpoint, so a cross-family executor/reviewer split needs only one account. For ARIS audit correctness, pin the reviewer model explicitly.

---

## FAQ

**Q: What is `orcarouter/auto`?**

`orcarouter/auto` is a named router rather than a model ID. It selects an upstream per request according to a routing policy you configure in the console. It is convenient for casual experiments, but do not use it for ARIS assurance-gated review, because the reviewer family is then not guaranteed to differ from the executor.

**Q: Why does my executor call return `model_not_found`?**

OrcaRouter routes on namespaced IDs. Set `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_HAIKU_MODEL` to values such as `anthropic/claude-opus-5`, otherwise Claude Code sends a bare model name that the gateway cannot resolve.

**Q: Should `ANTHROPIC_BASE_URL` include `/v1`?**

No. Use `https://api.orcarouter.ai` for `ANTHROPIC_BASE_URL` (Claude Code appends `/v1/messages` itself), and `https://api.orcarouter.ai/v1` for `LLM_BASE_URL` (the `llm-chat` server appends `/chat/completions`).

**Q: How do I switch reviewer models?**

Modify the `LLM_MODEL` value in `settings.json`, ensure the model is from a different family than the executor, and restart Claude Code.

**Q: Why is the llm-chat MCP call failing?**

Check:
1. API key format is correct and starts with `sk-orca-`.
2. `LLM_BASE_URL` ends with `/v1`.
3. Model ID is pinned and includes a namespace, such as `minimax/minimax-m3`.
4. Account has sufficient balance.

---

## References

- [OrcaRouter Official Website](https://www.orcarouter.ai)
- [OrcaRouter Model List](https://www.orcarouter.ai/models)
- [OrcaRouter Documentation](https://docs.orcarouter.ai)
- [OrcaRouter Console](https://www.orcarouter.ai/console)
- [ModelScope quota note](https://developer.aliyun.com/article/1644361)
- [LLM API Mix & Match Guide](LLM_API_MIX_MATCH_GUIDE.md)
- [OpenRouter Integration Guide](OPENROUTER_GUIDE.md) — the sibling guide for the other multi-model gateway route
