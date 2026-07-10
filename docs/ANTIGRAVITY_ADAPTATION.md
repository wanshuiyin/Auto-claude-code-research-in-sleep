# Antigravity Adaptation Guide (ARIS Workflows)

> Use ARIS research workflows in **Google Antigravity** — the agent-first AI IDE from Google DeepMind.

Antigravity natively supports `SKILL.md` files with the same YAML frontmatter + Markdown body format used by ARIS, making it one of the most natural hosts for ARIS workflows.

## 1. Key Differences: Claude Code vs Antigravity

| Concept | Claude Code | Antigravity |
|---------|-------------|-------------|
| Skill invocation | `/skill-name "args"` (slash command) | Agent auto-discovers from `description`; or read SKILL.md via `view_file` |
| Skill storage | `~/.claude/skills/skill-name/SKILL.md` | `~/.gemini/antigravity/skills/skill-name/SKILL.md` (global) or `<workspace>/.agents/skills/skill-name/SKILL.md` (project-local) |
| MCP servers | `claude mcp add ...` | `~/.gemini/settings.json` → `mcpServers` section |
| Project instructions | `CLAUDE.md` in project root | `GEMINI.md` in project root (equivalent) |
| Agent execution | Persistent CLI session, auto-compact | Editor sidebar + Manager View; multi-agent orchestration |
| File references | Auto-read from project | `view_file` tool; agent reads workspace files automatically |
| Long-running jobs | Single CLI session | Agent sessions with artifact-based checkpoints |
| Models available | Claude Opus 4.6 / Sonnet 4.6 | **Gemini 3.1 Pro (high)**, **Claude Opus 4.6 (Thinking)**, GPT-OSS-120B |

## 2. Model Selection

Antigravity supports multiple models as the **executor** (the model that runs ARIS workflows):

| Model | Best for | Configuration |
|-------|----------|---------------|
| **Claude Opus 4.6 (Thinking)** | Complex reasoning, long pipelines, code generation | Model selector → `Claude Opus 4.6 (Thinking)` |
| **Gemini 3.1 Pro (high)** | Fast iteration, large context, Google ecosystem integration | Model selector → `Gemini 3.1 Pro` with reasoning effort set to `high` |

> **Tip:** Claude Opus 4.6 (Thinking) and Gemini 3.1 Pro (high) have different strengths. Claude Opus excels at step-by-step reasoning and code accuracy; Gemini 3.1 Pro has a larger context window and faster response times. Choose based on your workflow needs.

### Model-Specific Notes

**For Claude Opus 4.6 (Thinking):**
- Extended thinking mode is enabled by default — ideal for complex research reasoning
- ARIS skill instructions will be followed very faithfully
- May be slower on long review prompts but more thorough

**For Gemini 3.1 Pro (high):**
- Larger context window (handles more project files at once)
- Natively understands SKILL.md format (Google's own standard)
- Set reasoning effort to `high` for best research quality — add to `~/.gemini/settings.json`:
  ```json
  {
    "model": {
      "name": "gemini-3.1-pro-preview"
    }
  }
  ```

## 3. Setup

### 3.1 Install skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep

# Option A: Global install (available across all projects)
mkdir -p ~/.gemini/antigravity/skills
cp -r skills/* ~/.gemini/antigravity/skills/

# Option B: Project-local install (recommended for isolation)
mkdir -p /path/to/your/project/.agents/skills
cp -r skills/* /path/to/your/project/.agents/skills/
```

> **Important:** Antigravity discovers skills from `~/.gemini/antigravity/skills/` (global) and `<workspace>/.agents/skills/` (project-scoped). The agent sees skill names and descriptions at startup, then loads full SKILL.md content when relevant.

### 3.2 Set up Codex MCP in Antigravity (for review skills)

ARIS uses an external LLM (GPT-5.6-Sol via Codex) as a critical reviewer. To enable this in Antigravity:

1. Install Codex CLI and authenticate:
   ```bash
   npm install -g @openai/codex
   codex login   # authenticate with your ChatGPT or API key
   ```

2. Add MCP server in Antigravity — edit `~/.gemini/settings.json`:
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

   Or for project-local scope, create `.gemini/settings.json` in your project root:
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

3. Restart Antigravity. Verify the MCP server connects — the agent will report available tools that include `mcp__codex__codex` and `mcp__codex__codex-reply`.

### 3.3 Alternative reviewer MCP (no OpenAI API)

If you don't have an OpenAI API key, use the [`llm-chat`](../mcp-servers/llm-chat/) MCP server with any OpenAI-compatible API (DeepSeek, GLM, MiniMax, Kimi, etc.):

1. Create a virtual environment and install the required dependency:
   ```bash
   cd /path/to/Auto-claude-code-research-in-sleep
   python3 -m venv .venv
   .venv/bin/pip install -r mcp-servers/llm-chat/requirements.txt
   ```

2. Add MCP server — edit `~/.gemini/settings.json`. Both paths must be **absolute**:
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

3. Restart Antigravity. The `llm-chat` MCP should appear in available tools.

See [LLM_API_MIX_MATCH_GUIDE.md](LLM_API_MIX_MATCH_GUIDE.md) for tested provider configurations.

### 3.4 Project instructions (GEMINI.md)

Antigravity uses `GEMINI.md` (equivalent to Claude Code's `CLAUDE.md`) for project-specific instructions. Create this file in your project root:

```markdown
## GPU Server (for auto-experiments)

- SSH: `ssh my-gpu-server` (key-based auth, no password)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`
- Use `screen` for background jobs: `screen -dmS exp0 bash -c '...'`

## Research Project

- Topic: [your research topic]
- Target venue: ICLR/NeurIPS/ICML
- Key files: NARRATIVE_REPORT.md, idea-stage/IDEA_REPORT.md
```

## 4. How to Invoke Skills

Antigravity discovers ARIS skills via the YAML `description` field in each `SKILL.md`. There are three approaches:

### Approach A: Natural language (recommended — Antigravity auto-discovers)

Simply describe what you want in the chat. Antigravity matches your intent to installed skills:

```
Run the auto review loop for "factorized gap in discrete diffusion LMs".
```

If ARIS skills are installed (§3.1), Antigravity will automatically discover and activate the `auto-review-loop` skill.

### Approach B: Explicit skill reference

Ask the agent to read a specific SKILL.md:

```
Read the file skills/auto-review-loop/SKILL.md and follow its instructions.
Topic: "factorized gap in discrete diffusion LMs".
```

Or if installed globally:

```
Read ~/.gemini/antigravity/skills/auto-review-loop/SKILL.md and execute it.
Topic: "factorized gap in discrete diffusion LMs".
```

### Approach C: Direct prompt (one-off use)

Copy the relevant workflow instructions directly into the chat. Best for quick, one-time use.

## 5. Workflow Mapping

### Workflow 1: Idea Discovery

**Claude Code:**
```
/idea-discovery "your research direction"
```

**Antigravity equivalent:**
```
Run the full idea discovery pipeline for "your research direction".

Follow these sub-skills in sequence:
1. Read and execute skills/research-lit/SKILL.md — literature survey
2. Read and execute skills/idea-creator/SKILL.md — brainstorm ideas
3. Read and execute skills/novelty-check/SKILL.md — verify novelty
4. Read and execute skills/research-review/SKILL.md — critical review
5. Read and execute skills/research-refine-pipeline/SKILL.md — refine method + plan experiments
```

> **Tip:** If the context gets long, run each phase as a separate agent task in Antigravity's Manager View. Pass results via files (e.g., `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`).

### Workflow 1.5: Experiment Bridge

**Claude Code:**
```
/experiment-bridge
```

**Antigravity equivalent:**
```
Read and execute skills/experiment-bridge/SKILL.md.
Read refine-logs/EXPERIMENT_PLAN.md and implement the experiments.
Deploy to GPU via skills/run-experiment/SKILL.md.
```

### Workflow 2: Auto Review Loop

**Claude Code:**
```
/auto-review-loop "your paper topic"
```

**Antigravity equivalent:**
```
Read and execute skills/auto-review-loop/SKILL.md.
Run the auto review loop for "your paper topic".
Read project narrative docs, memory files, experiment results.
Use MCP tool mcp__codex__codex for external review.
```

> **Important:** If using the `llm-chat` MCP instead of Codex, replace `mcp__codex__codex` with `mcp__llm-chat__chat`. Or use the adapted skill: `skills/auto-review-loop-llm/SKILL.md`.

### Workflow 3: Paper Writing

**Claude Code:**
```
/paper-writing "NARRATIVE_REPORT.md"
```

**Antigravity equivalent:**
```
Read and execute skills/paper-writing/SKILL.md.
Input: NARRATIVE_REPORT.md in project root.

Sub-skills to execute in sequence:
1. Read and execute skills/paper-plan/SKILL.md — outline + claims-evidence matrix
2. Read and execute skills/paper-figure/SKILL.md — generate plots and tables
3. Read and execute skills/paper-write/SKILL.md — write LaTeX sections
4. Read and execute skills/paper-compile/SKILL.md — build PDF
5. Read and execute skills/auto-paper-improvement-loop/SKILL.md — review and polish
```

### Full Pipeline

For the full pipeline (`/research-pipeline`), leverage Antigravity's **multi-agent** capability to run stages in parallel where possible:

| Stage | What to do | Output files |
|-------|-----------|-------------|
| 1 | Idea Discovery: `skills/idea-discovery/SKILL.md` + your direction | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` |
| 2 | Experiment Bridge: `skills/experiment-bridge/SKILL.md` | Experiment scripts, results |
| 3 | Auto Review Loop: `skills/auto-review-loop/SKILL.md` | `review-stage/AUTO_REVIEW.md` |
| 4 | Paper Writing: `skills/paper-writing/SKILL.md` + `NARRATIVE_REPORT.md` | `paper/` directory |

Each stage reads the previous stage's output files, so context carries forward across agent sessions.

> **Note:** Stage 4 expects a `NARRATIVE_REPORT.md` — see [NARRATIVE_REPORT_EXAMPLE.md](NARRATIVE_REPORT_EXAMPLE.md) for the expected format.

## 6. MCP Tool Calls

ARIS skills reference MCP tools by name. These work identically in Antigravity once configured:

| ARIS MCP tool | What it does | Required MCP server |
|--------------|-------------|-------------------|
| `mcp__codex__codex` | Send prompt to GPT-5.6-Sol | Codex |
| `mcp__codex__codex-reply` | Continue conversation thread | Codex |
| `mcp__llm-chat__chat` | Send prompt to any OpenAI-compatible model | llm-chat |
| `mcp__zotero__*` | Search Zotero library | zotero (name may vary) |
| `mcp__obsidian-vault__*` | Search Obsidian vault | obsidian-vault (name may vary) |

## 7. State Files & Recovery

ARIS workflows persist state to files for crash recovery. These work identically in Antigravity:

| File | Purpose | Written by |
|------|---------|----|
| `review-stage/REVIEW_STATE.json` | Auto-review loop progress | `auto-review-loop` |
| `review-stage/AUTO_REVIEW.md` | Cumulative review log | `auto-review-loop` |
| `idea-stage/IDEA_REPORT.md` | Ranked ideas with pilot results | `idea-discovery` |
| `PAPER_PLAN.md` | Paper outline + claims-evidence matrix | `paper-plan` |
| `refine-logs/FINAL_PROPOSAL.md` | Refined method proposal | `research-refine` |
| `refine-logs/EXPERIMENT_PLAN.md` | Experiment roadmap | `experiment-plan` |
| `refine-logs/EXPERIMENT_TRACKER.md` | Run-by-run execution status | `experiment-plan` |

If an Antigravity agent session ends mid-workflow, start a new session and reference the state file:

```
Read skills/auto-review-loop/SKILL.md, then read review-stage/REVIEW_STATE.json and review-stage/AUTO_REVIEW.md.
Resume the auto review loop from the saved state.
```

## 8. GPU Server Setup

Add your server info to `GEMINI.md` in your project root (equivalent to `CLAUDE.md`):

```markdown
## Remote Server

- SSH: `ssh my-gpu-server` (key-based auth, no password)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`
- Use `screen` for background jobs
```

Then invoke:

```
Read skills/run-experiment/SKILL.md and GEMINI.md.
Deploy the training script to the remote GPU server.
```

## 9. Antigravity-Specific Advantages

Antigravity provides several unique capabilities that enhance ARIS workflows:

### Multi-Agent Orchestration
Use Antigravity's **Manager View** to run multiple ARIS stages simultaneously:
- Agent 1: Literature survey (Workflow 1, Stage 1)
- Agent 2: Running experiments on GPU (Workflow 1.5)
- Agent 3: Reviewing and iterating on prior results (Workflow 2)

### Browser Integration
Antigravity includes a built-in browser. Useful for:
- Previewing generated charts/figures from `/paper-figure`
- Testing web-based arXiv searches during `/research-lit`
- Viewing compiled PDF from `/paper-compile`

### Artifact System
Antigravity's artifact system (implementation plans, walkthroughs) maps naturally to ARIS outputs:
- `idea-stage/IDEA_REPORT.md` → implementation plan artifact
- `review-stage/AUTO_REVIEW.md` → walkthrough artifact
- `PAPER_PLAN.md` → implementation plan artifact

### Knowledge Persistence
Antigravity's knowledge system retains context across conversations:
- Past review findings from `/auto-review-loop` are available in future sessions
- Experiment configurations and results persist in knowledge items
- Literature survey results can be referenced without re-running

## 10. Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| No native `/skill-name` slash commands | Use natural language (auto-discovery) or explicit `read SKILL.md` references |
| Skills reference `$ARGUMENTS` | Replace with your actual arguments in the prompt |
| SKILL.md files use `/skill-name` to call sub-skills | Tell the agent to read and execute the sub-skill SKILL.md files explicitly |
| `allowed-tools` not enforced | Antigravity's agent has access to all configured tools by default — not a problem in practice |
| `CLAUDE.md` references in skills | Antigravity reads `GEMINI.md` instead — rename or copy `CLAUDE.md` to `GEMINI.md`, or tell the agent to read both |
| Context window varies by model | Claude Opus 4.6: similar to Claude Code. Gemini 3.1 Pro: larger window. Both handle full pipelines well. Break into stages if needed |

## 11. Quick Reference

```
# Literature survey
Read skills/research-lit/SKILL.md and search for papers on "discrete diffusion models".

# Idea discovery (full pipeline)
Read skills/idea-discovery/SKILL.md and run idea discovery for
"factorized gap in discrete diffusion LMs".

# Single deep review
Read skills/research-review/SKILL.md and review this research:
[describe your work or point to files].

# Auto review loop
Read skills/auto-review-loop/SKILL.md and run the auto review loop.
Topic: "your paper topic".

# Paper writing
Read skills/paper-writing/SKILL.md and write the paper from NARRATIVE_REPORT.md.

# Run experiment
Read skills/run-experiment/SKILL.md and GEMINI.md.
Deploy: python train.py --lr 1e-4 --epochs 100
```

## 12. Summary: Claude Code → Antigravity Migration Checklist

- [ ] Install skills to `~/.gemini/antigravity/skills/` or `<project>/.agents/skills/`
- [ ] Configure MCP servers in `~/.gemini/settings.json`
- [ ] Copy `CLAUDE.md` content to `GEMINI.md` (or keep both)
- [ ] Select model: Claude Opus 4.6 (Thinking) or Gemini 3.1 Pro (high)
- [ ] Use natural language or explicit skill references instead of `/slash-commands`
- [ ] Verify MCP tools are available (codex or llm-chat)
- [ ] Run a quick test: `Read skills/research-review/SKILL.md and review my project`
