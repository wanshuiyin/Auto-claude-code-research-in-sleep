---
name: auto-review-loop-llm
description: Autonomous research review loop using any OpenAI-compatible LLM API. Configure via llm-chat MCP server or environment variables. Trigger with "auto review loop llm" or "llm review".
argument-hint: [topic-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill
---

# Auto Review Loop (Generic LLM): Autonomous Research Improvement

Autonomously iterate: review → implement fixes → re-review, until the external reviewer gives a positive assessment or MAX_ROUNDS is reached.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 6/10, or verdict contains "accept", "sufficient", "ready for submission"
- REVIEW_DOC: `AUTO_REVIEW.md` in project root (cumulative log)

## LLM Configuration

This skill uses **any OpenAI-compatible API** for external review via the `llm-chat` MCP server.

### Configuration via MCP Server (Recommended)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/Users/yourname/.claude/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_API_KEY": "your-api-key",
        "LLM_BASE_URL": "https://api.deepseek.com/v1",
        "LLM_MODEL": "deepseek-chat"
      }
    }
  }
}
```

### Supported Providers

| Provider | LLM_BASE_URL | LLM_MODEL |
|----------|--------------|-----------|
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4o`, `o3` |
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat`, `deepseek-reasoner` |
| **MiniMax** | `https://api.minimax.chat/v1` | `MiniMax-M2.5` |
| **Kimi (Moonshot)** | `https://api.moonshot.cn/v1` | `moonshot-v1-8k`, `moonshot-v1-32k` |
| **ZhiPu (GLM)** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4`, `glm-4-plus` |
| **SiliconFlow** | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` |
| **阿里云百炼** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| **零一万物** | `https://api.lingyiwanwu.com/v1` | `yi-large` |

## API Call Method

**Primary: MCP Tool**

```
mcp__llm-chat__chat:
  prompt: |
    [Review prompt content]
  model: "deepseek-chat"
  system: "You are a senior ML reviewer..."
```

**Fallback: curl**

```bash
curl -s "${LLM_BASE_URL}/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LLM_API_KEY}" \
  -d '{
    "model": "${LLM_MODEL}",
    "messages": [
      {"role": "system", "content": "You are a senior ML reviewer..."},
      {"role": "user", "content": "[review prompt]"}
    ],
    "max_tokens": 4096
  }'
```

## State Persistence (Compact Recovery)

Persist state to `REVIEW_STATE.json` after each round:

```json
{
  "round": 2,
  "status": "in_progress",
  "last_score": 5.0,
  "last_verdict": "not ready",
  "pending_experiments": [],
  "timestamp": "2026-03-15T10:00:00"
}
```

**Write this file at the end of every Phase E** (after documenting the round).

**On completion**, set `"status": "completed"`.

## Workflow

### Initialization

1. **Check `REVIEW_STATE.json`** for recovery
2. Read project context and prior reviews
3. Initialize round counter

### Loop (up to MAX_ROUNDS)

#### Phase A: Review

**If MCP available:**
```
mcp__llm-chat__chat:
  system: "You are a senior ML reviewer (NeurIPS/ICML level)."
  prompt: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    [Full research context: claims, methods, results, known weaknesses]
    [Changes since last round, if any]

    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix
    4. State clearly: is this READY for submission? Yes/No/Almost

    Be brutally honest. If the work is ready, say so clearly.
```

**If MCP NOT available:**
```bash
curl -s "${LLM_BASE_URL}/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LLM_API_KEY}" \
  -d '{
    "model": "${LLM_MODEL}",
    "messages": [
      {"role": "system", "content": "You are a senior ML reviewer (NeurIPS/ICML level)."},
      {"role": "user", "content": "[Full review prompt]"}
    ],
    "max_tokens": 4096
  }'
```

#### Phase B: Parse Assessment

**CRITICAL: Save the FULL raw response** verbatim. Then extract:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

**STOP**: If score >= 6 AND verdict contains "ready/almost"

#### Phase C: Implement Fixes

Priority: metric additions > reframing > new experiments

#### Phase D: Wait for Results

Monitor remote experiments

#### Phase E: Document Round

Append to `AUTO_REVIEW.md`:

```markdown
## Round N (timestamp)

### Assessment (Summary)
- Score: X/10
- Verdict: [ready/almost/not ready]
- Key criticisms: [bullet list]

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

[Paste the COMPLETE raw response here — verbatim, unedited.]

</details>

### Actions Taken
- [what was implemented/changed]

### Results
- [experiment outcomes, if any]

### Status
- [continuing to round N+1 / stopping]
```

**Write `REVIEW_STATE.json`** with current state.

### Termination

1. Set `REVIEW_STATE.json` status to "completed"
2. Write final summary

## Key Rules

- Be honest about weaknesses
- Implement fixes BEFORE re-reviewing
- Document everything
- Include previous context in round 2+ prompts
- Prefer MCP tool over curl when available

## Prompt Template for Round 2+

```
mcp__llm-chat__chat:
  system: "You are a senior ML reviewer (NeurIPS/ICML level)."
  prompt: |
    [Round N/MAX_ROUNDS of autonomous review loop]

    ## Previous Review Summary (Round N-1)
    - Previous Score: X/10
    - Previous Verdict: [ready/almost/not ready]
    - Previous Key Weaknesses: [list]

    ## Changes Since Last Review
    1. [Action 1]: [result]
    2. [Action 2]: [result]

    ## Updated Results
    [paste updated metrics/tables]

    Please re-score and re-assess:
    1. Score this work 1-10 for a top venue
    2. List remaining critical weaknesses (ranked by severity)
    3. For each weakness, specify the MINIMUM fix
    4. State clearly: is this READY for submission? Yes/No/Almost

    Be brutally honest. If the work is ready, say so clearly.
```
