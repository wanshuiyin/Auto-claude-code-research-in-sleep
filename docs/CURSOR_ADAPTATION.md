# Cursor Adaptation Guide (ARIS Workflows)

> Use ARIS research workflows in **Cursor** without Claude Code slash commands.

## 1. Key Differences: Claude Code vs Cursor

| Concept | Claude Code | Cursor |
|---------|-------------|--------|
| Skill invocation | `/skill-name "args"` (slash command) | Paste instructions or `@`-reference the SKILL.md |
| Skill storage | `~/.claude/skills/skill-name/SKILL.md` | `.cursor/rules/*.mdc` or reference directly |
| MCP servers | `claude mcp add ...` | Cursor Settings → Features → MCP, or `.cursor/mcp.json` |
| Agent execution | Always-on CLI | Agent mode (Ctrl/Cmd+I or chat panel) |
| File references | Auto-read from project | `@filename` to attach context |
| Long-running jobs | Single CLI session, auto-compact recovery | Chat sessions; use state files for recovery |

## 2. Setup

### 2.1 Clone the repo

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
```

> **Important:** Open this repo (or add it as a workspace folder) in Cursor. The `@skills/...` references throughout this guide use Cursor's `@`-file feature, which only resolves files within your open workspace. If you work in a separate project, either copy the `skills/` folder into it or add the ARIS repo as a second workspace folder (File → Add Folder to Workspace).

### 2.2 Set up Codex MCP in Cursor (for review skills)

ARIS uses an external LLM (GPT-5.6-Sol via Codex) as a critical reviewer. To enable this in Cursor:

1. Install Codex CLI and authenticate:
   ```bash
   npm install -g @openai/codex
   codex login   # authenticate with your ChatGPT or API key
   ```

2. Add MCP server in Cursor — create or edit `.cursor/mcp.json` in your project root:
   ```json
   {
     "mcpServers": {
       "codex": {
         "command": "codex",
         "args": ["mcp-server"]
       }
     }
   }
   ```

3. Restart Cursor. Verify the MCP server appears under Settings → Features → MCP.

### 2.3 Set up alternative reviewer (no OpenAI API)

If you don't have an OpenAI API key, use the [`llm-chat`](../mcp-servers/llm-chat/) MCP server with any OpenAI-compatible API (DeepSeek, GLM, MiniMax, Kimi, etc.):

1. Create a virtual environment and install the required dependency (the server needs `httpx`):
   ```bash
   cd /path/to/Auto-claude-code-research-in-sleep
   python3 -m venv .venv
    .venv/bin/pip install -r mcp-servers/llm-chat/requirements.txt
   ```

2. Add MCP server in Cursor — create or edit `.cursor/mcp.json`. Both paths must be **absolute** — `command` points to the venv python (not system python, otherwise `httpx` won't be found), and `args` points to the server script:
   ```json
   {
     "mcpServers": {
       "llm-chat": {
         "command": "/path/to/Auto-claude-code-research-in-sleep/.venv/bin/python3",
         "args": ["/path/to/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py"],
         "env": {
           "LLM_BASE_URL": "https://api.deepseek.com/v1",
           "LLM_API_KEY": "your_key",
           "LLM_MODEL": "deepseek-chat"
         }
       }
     }
   }
   ```

3. Restart Cursor. Verify the MCP server appears (green dot) under Settings → Features → MCP. If it shows a red dot, check `llm-chat-mcp-debug.log` in your system temp directory (run `python3 -c "import tempfile; print(tempfile.gettempdir())"` to locate it).

See [LLM_API_MIX_MATCH_GUIDE.md](LLM_API_MIX_MATCH_GUIDE.md) for tested provider configurations.

## 3. How to Invoke Skills

Claude Code uses `/skill-name` to auto-load a SKILL.md. In Cursor, you have three approaches:

### Approach A: `@`-reference the SKILL.md (recommended)

In Cursor's agent mode chat, type:

```
@skills/auto-review-loop/SKILL.md

Run the auto review loop for "factorized gap in discrete diffusion LMs".
```

Cursor reads the full SKILL.md and follows the instructions. This is the closest equivalent to Claude Code's `/auto-review-loop`.

### Approach B: Convert to Cursor Rules (for frequent use)

For skills you use often, convert them to Cursor Rules so they load automatically:

1. Create `.cursor/rules/` in your project root.

2. Create a rule file, e.g. `.cursor/rules/auto-review-loop.mdc`:
   ```
   ---
   description: "Autonomous multi-round research review loop"
   globs:
     - "review-stage/AUTO_REVIEW.md"
     - "review-stage/REVIEW_STATE.json"
   ---

   [Paste the full SKILL.md content here, minus the YAML frontmatter]
   ```

3. The rule activates automatically when you work with matching files, or you can reference it manually.

### Approach C: Direct prompt (one-off use)

Copy the relevant workflow instructions directly into the chat. Best for quick, one-time use.

## 4. Workflow Mapping

### Workflow 1: Idea Discovery

**Claude Code:**
```
/idea-discovery "your research direction"
```

**Cursor equivalent:**
```
@skills/idea-discovery/SKILL.md

Run the full idea discovery pipeline for "your research direction".

Use these sub-skills in sequence (the SKILL.md references them as
/skill-name which is Claude Code syntax — use these @-references instead):
1. @skills/research-lit/SKILL.md — literature survey
2. @skills/idea-creator/SKILL.md — brainstorm ideas
3. @skills/novelty-check/SKILL.md — verify novelty
4. @skills/research-review/SKILL.md — critical review
5. @skills/research-refine-pipeline/SKILL.md — refine method + plan experiments
```

> **Tip:** Cursor's context window may be smaller than Claude Code's. For long pipelines, run each phase in a separate chat and pass results via files (e.g., `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`).

### Workflow 1.5: Experiment Bridge

**Claude Code:**
```
/experiment-bridge
```

**Cursor equivalent:**
```
@skills/experiment-bridge/SKILL.md

Read refine-logs/EXPERIMENT_PLAN.md and implement the experiments.
Deploy to GPU via @skills/run-experiment/SKILL.md.
```

### Workflow 2: Auto Review Loop

**Claude Code:**
```
/auto-review-loop "your paper topic"
```

**Cursor equivalent:**
```
@skills/auto-review-loop/SKILL.md

Run the auto review loop for "your paper topic".
Read project narrative docs, memory files, experiment results.
Use MCP tool mcp__codex__codex for external review.
```

> **Important:** If using the `llm-chat` MCP instead of Codex, replace `mcp__codex__codex` with `mcp__llm-chat__chat` in your prompt. See [auto-review-loop-llm](../skills/auto-review-loop-llm/SKILL.md) for the adapted skill.

### Workflow 3: Paper Writing

**Claude Code:**
```
/paper-writing "NARRATIVE_REPORT.md"
```

**Cursor equivalent:**
```
@skills/paper-writing/SKILL.md
@NARRATIVE_REPORT.md

Run the full paper writing pipeline from NARRATIVE_REPORT.md.

Sub-skills to use in sequence (replace /skill-name from SKILL.md):
1. @skills/paper-plan/SKILL.md — outline + claims-evidence matrix
2. @skills/paper-figure/SKILL.md — generate plots and tables
3. @skills/paper-write/SKILL.md — write LaTeX sections
4. @skills/paper-compile/SKILL.md — build PDF
5. @skills/auto-paper-improvement-loop/SKILL.md — review and polish
```

### Full Pipeline

For the full pipeline (`/research-pipeline`), break it into stages across chat sessions:

| Stage | What to do | Output files |
|-------|-----------|-------------|
| 1 | `@skills/idea-discovery/SKILL.md` + your direction | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` |
| 2 | `@skills/experiment-bridge/SKILL.md` + `@refine-logs/EXPERIMENT_PLAN.md` + `@refine-logs/FINAL_PROPOSAL.md` | Experiment scripts, results |
| 3 | `@skills/auto-review-loop/SKILL.md` + your topic | `review-stage/AUTO_REVIEW.md` |
| 4 | `@skills/paper-writing/SKILL.md` + `@NARRATIVE_REPORT.md` | `paper/` directory |

Each stage reads the previous stage's output files, so context carries forward even across sessions.

> **Note:** Stage 4 expects a `NARRATIVE_REPORT.md` describing your research story (claims, experiments, results). This is typically written by you based on `review-stage/AUTO_REVIEW.md` and experiment results — see [NARRATIVE_REPORT_EXAMPLE.md](NARRATIVE_REPORT_EXAMPLE.md) for the expected format.

## 5. MCP Tool Calls

ARIS skills reference MCP tools by name (e.g., `mcp__codex__codex`). Cursor supports MCP tool calls in agent mode — when the SKILL.md instructions say to call an MCP tool, Cursor's agent will invoke it if the server is configured.

| ARIS MCP tool | What it does | Required MCP server |
|--------------|-------------|-------------------|
| `mcp__codex__codex` | Send prompt to GPT-5.6-Sol | Codex |
| `mcp__codex__codex-reply` | Continue conversation thread | Codex |
| `mcp__llm-chat__chat` | Send prompt to any OpenAI-compatible model | llm-chat |
| `mcp__zotero__*` | Search Zotero library | zotero (name may vary by config) |
| `mcp__obsidian-vault__*` | Search Obsidian vault | obsidian-vault (name may vary by config) |

## 6. State Files & Recovery

ARIS workflows persist state to files for crash recovery. These work identically in Cursor:

| File | Purpose | Written by |
|------|---------|-----------|
| `review-stage/REVIEW_STATE.json` | Auto-review loop progress | `/auto-review-loop` |
| `review-stage/AUTO_REVIEW.md` | Cumulative review log | `/auto-review-loop` |
| `idea-stage/IDEA_REPORT.md` | Ranked ideas with pilot results | `/idea-discovery` |
| `PAPER_PLAN.md` | Paper outline + claims-evidence matrix | `/paper-plan` |
| `refine-logs/FINAL_PROPOSAL.md` | Refined method proposal | `/research-refine` |
| `refine-logs/EXPERIMENT_PLAN.md` | Experiment roadmap | `/experiment-plan` |
| `refine-logs/EXPERIMENT_TRACKER.md` | Run-by-run execution status | `/experiment-plan` |

If a Cursor chat session ends mid-workflow, start a new session and reference the state file:

```
@skills/auto-review-loop/SKILL.md
@review-stage/REVIEW_STATE.json
@review-stage/AUTO_REVIEW.md

Resume the auto review loop from the saved state.
```

## 7. GPU Server Setup

Same as Claude Code — add your server info to `CLAUDE.md` (or any project doc that Cursor reads). Reference it in your prompt:

```
@CLAUDE.md
@skills/run-experiment/SKILL.md

Deploy the training script to the remote GPU server.
```

## 8. Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| No native slash commands | Use `@skills/skill-name/SKILL.md` to reference skills |
| Context window may be smaller | Break long pipelines into per-stage sessions, pass results via files |
| No auto-compact recovery | Use `review-stage/REVIEW_STATE.json` to resume manually across sessions |
| `allowed-tools` not enforced | Cursor agent has access to all its tools by default — not a problem in practice |
| Skills reference `$ARGUMENTS` | Replace with your actual arguments in the prompt |
| SKILL.md files use `/skill-name` to call sub-skills | Cursor ignores these. For pipeline skills (`idea-discovery`, `paper-writing`), list the sub-skill `@` references explicitly in your prompt — see Workflow 1 and 3 examples |
| `@skills/...` requires workspace access | The ARIS repo (or its `skills/` folder) must be in your Cursor workspace — see Setup §2.1 |

## 9. Quick Reference

```
# Literature survey
@skills/research-lit/SKILL.md
Search for papers on "discrete diffusion models".

# Idea discovery (full pipeline)
@skills/idea-discovery/SKILL.md
Run idea discovery for "factorized gap in discrete diffusion LMs".

# Single deep review
@skills/research-review/SKILL.md
Review this research: [paste or @-reference your work].

# Auto review loop
@skills/auto-review-loop/SKILL.md
Run the auto review loop. Topic: "your paper topic".

# Paper writing
@skills/paper-writing/SKILL.md
@NARRATIVE_REPORT.md
Write the paper from this narrative report.

# Run experiment
@skills/run-experiment/SKILL.md
@CLAUDE.md
Deploy: python train.py --lr 1e-4 --epochs 100
```
