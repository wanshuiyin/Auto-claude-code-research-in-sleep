# ARIS Trae Adaptation Guide (Workflow Runbook)

Use ARIS research workflows in Trae without relying on Claude Code `/skill-name` slash commands.

## 1. Key Differences: Claude Code vs Trae

| Concept | Claude Code | Trae |
|---|---|---|
| Skill invocation | `/skill-name "args"` (slash command) | Natural language auto-discovery, `#` quick match, `@skills/.../SKILL.md` (file reference) |
| Skill storage | `~/.claude/skills/...` | Global `~/.trae/skills/` (cross-project available) or project `<project>/.trae/skills/` (current project only), or directly reference ARIS repo `skills/` |
| MCP setup | `claude mcp add ...` | `Settings → MCP → Manual Add` |
| Agent execution | Persistent CLI session | Chat/Agent session |
| File references | Auto-read from project | Explicit `@filename` attachment |
| Long-running recovery | Single session auto-compact recovery | Manual recovery via state files |

## 2. Setup

It is recommended to create a dedicated Trae agent for ARIS workflows to avoid conflicts with other agents and to keep role instructions stable.

### 2.1 Clone the repository and configure Skills

```powershell
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
```

**Two ways to install Skills in Trae:**

Method 1: Install via Trae UI (Recommended)

1. Go to `Settings → Rules and Skills`
2. Select "Global" or "Project" installation scope
3. Click "Import File" and select SKILL.md files from the ARIS repo's `skills/` directory
4. After installation, skills can be triggered via natural language

> **Note:** Globally installed skills can be triggered via natural language in all projects; project-level installed skills can be triggered via natural language within that project.

Method 2: Manual copy to skills directory

```powershell
# Global installation (available in all projects)
New-Item -ItemType Directory -Path "$env:USERPROFILE\.trae\skills" -Force
Copy-Item -Path "C:\path\to\Auto-claude-code-research-in-sleep\skills\*" -Destination "$env:USERPROFILE\.trae\skills\" -Recurse -Force

# Project-level installation (available only in current project)
New-Item -ItemType Directory -Path ".\.trae\skills" -Force
Copy-Item -Path "C:\path\to\Auto-claude-code-research-in-sleep\skills\*" -Destination ".\.trae\skills\" -Recurse -Force
```

After installation, simply describe your needs in natural language within the corresponding scope to trigger the relevant skill.

### 2.2 Configure Codex reviewer MCP (recommended)

ARIS relies on an executor model + external reviewer model. Configure reviewer MCP first, then run workflows.

1) Install and authenticate Codex CLI

```powershell
npm install -g @openai/codex
codex login
```

2) Configure MCP in Trae  
Go to `Settings → MCP → Manual Add`, then add:
- Name: `codex`
- Command: `codex`
- Args: `mcp-server`

If your Trae version supports workspace MCP config files, use:

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

3) Restart Trae and verify
- `codex` shows online in MCP panel.
- Running review-enabled skills shows review/score/feedback outputs.

### 2.3 Alternative reviewer MCP (without OpenAI API)

You can use `llm-chat` with OpenAI-compatible providers such as DeepSeek/GLM/MiniMax/Kimi.

1) Create virtual environment and install dependencies

```powershell
cd D:\path\to\Auto-claude-code-research-in-sleep
python -m venv .venv
.\.venv\Scripts\pip install -r mcp-servers\llm-chat\requirements.txt
```

2) Configure MCP (absolute paths required)

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/path/to/Auto-claude-code-research-in-sleep/.venv/Scripts/python.exe",
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

3) Must-check items
- `command` points to venv Python.
- `args` points to `server.py` with an absolute path.
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` are all set.
- Restart Trae and verify MCP online status.

4) If MCP is red/offline
- Check path typos.
- Check dependencies are installed in that venv.
- Check `llm-chat-mcp-debug.log` in system temp directory.
- If DeepSeek auth fails, verify API key and base URL first.

## 3. How to Invoke Skills in Trae

Trae supports the following five ways to invoke Skills:

### A. Natural Language Auto-Invocation (Recommended)

Describe your needs, and Trae will automatically determine and invoke relevant skills based on the skill's `description`:

```
Help me run an auto review loop for this paper
```

This is the most natural way—just describe what you want to do, and Trae will automatically match the appropriate Skills.

### B. `#` Quick Match

Type `#` in the chat to quickly search and invoke skills. After typing `#`, you'll see a skill list:

```
#auto-review-loop
```

### C. `@` Reference SKILL.md File

Directly reference the skill file and attach an action instruction in the conversation:

```
@skills/auto-review-loop/SKILL.md
Run the auto review loop for "factorized gap in discrete diffusion LMs".
```

Note: `@skills/.../SKILL.md` references only resolve if the ARIS repo (or its `skills/` folder) is part of the current Trae workspace. They will not work when the skills folder exists only in a separate workspace.
### D. Convert Frequent Skills into Local Rules

Move frequently used skill instructions into project rules to reduce repeated manual pasting.

### E. Direct One-off Prompt

Paste workflow instructions directly into chat for temporary tasks.

## 4. Workflow Mapping (Claude Flow → Trae Usage)

Trae automatically discovers ARIS skills via the YAML `description` field in `SKILL.md`. Below are invocation methods for each workflow:

### Workflow 1: Idea Discovery

**Claude Code:**
```
/idea-discovery "your research direction"
```

**Trae equivalent:**
```
Run the full idea discovery pipeline for "your research direction".

Use the following sub-skills in order:
1. Use research-lit skill — Literature review
2. Use idea-creator skill — Brainstorming
3. Use novelty-check skill — Novelty verification
4. Use research-review skill — Deep review
5. Use research-refine-pipeline skill — Method refinement + Experiment planning
```

> **Tip:** If context is too long, split each stage into separate conversations and pass results via files (e.g., `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`).

### Workflow 1.5: Experiment Bridge

**Claude Code:**
```
/experiment-bridge
```

**Trae equivalent:**
```
Use experiment-bridge skill.
Read refine-logs/EXPERIMENT_PLAN.md and implement experiments.
Use run-experiment skill to deploy to GPU.
```

### Workflow 2: Auto Review Loop

**Claude Code:**
```
/auto-review-loop "your paper topic"
```

**Trae equivalent:**
```
Use auto-review-loop skill.
Run auto review loop for "your paper topic".
Read project narrative docs, memory files, and experiment results.
Use MCP tool mcp__codex__codex for external review.
```

> **Note:** If using `llm-chat` MCP, replace `mcp__codex__codex` with `mcp__llm-chat__chat`. Or use the adapted skill: `auto-review-loop-llm`.

### Workflow 3: Paper Writing

**Claude Code:**
```
/paper-writing "NARRATIVE_REPORT.md"
```

**Trae equivalent:**
```
Use paper-writing skill.
Input: NARRATIVE_REPORT.md in project root.

Use the following sub-skills in order:
1. Use paper-plan skill — Outline + claims-evidence matrix
2. Use paper-figure skill — Generate figures
3. Use paper-write skill — Write LaTeX sections
4. Use paper-compile skill — Compile PDF
5. Use auto-paper-improvement-loop skill — Review and polish
```

### Full Pipeline Staging

| Stage | Execution | Output Files |
|--------|-----------|--------------|
| 1 | Idea Discovery: Use `idea-discovery` skill + research direction | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` |
| 2 | Experiment Bridge: Use `experiment-bridge` skill | Experiment scripts and results |
| 3 | Auto Review: Use `auto-review-loop` skill | `review-stage/AUTO_REVIEW.md` |
| 4 | Paper Writing: Use `paper-writing` skill + `NARRATIVE_REPORT.md` | `paper/` directory |

Each stage reads output files from the previous stage, so context can be passed across different conversations.

## 5. MCP Tool Calls Mapping

| ARIS MCP tool | Purpose | Required MCP server |
|---|---|---|
| `mcp__codex__codex` | Send review prompt to GPT-5.6-Sol | codex |
| `mcp__codex__codex-reply` | Continue review thread | codex |
| `mcp__llm-chat__chat` | Send prompt to OpenAI-compatible models | llm-chat |

## 6. State Files and Recovery

| File | Purpose | Typical workflow |
|---|---|---|
| `review-stage/REVIEW_STATE.json` | Tracks auto-review progress | auto-review-loop |
| `review-stage/AUTO_REVIEW.md` | Cumulative review log | auto-review-loop |
| `idea-stage/IDEA_REPORT.md` | Ranked ideas and initial findings | idea-discovery |
| `PAPER_PLAN.md` | Outline + claim-evidence matrix | paper-plan |
| `PAPER_IMPROVEMENT_LOG.md` | Paper improvement rounds log | auto-paper-improvement-loop |

Recovery example:

```text
@skills/auto-review-loop/SKILL.md
@review-stage/REVIEW_STATE.json
@review-stage/AUTO_REVIEW.md
Resume the auto review loop from saved state.
```

## 7. GPU Server Execution

Keep server configuration in project docs, then invoke:

```text
@skills/run-experiment/SKILL.md
Deploy: python train.py --lr 1e-4 --epochs 100
```

## 8. Common Limitations and Workarounds

| Limitation | Workaround |
|---|---|
| Natural language invocation depends on skill `description` quality | Ensure skills' YAML frontmatter description accurately describes applicable scenarios |
| Context pressure in long workflows | Split by stages and pass artifacts via files |
| No auto-compact resume | Resume using state files |
| `$ARGUMENTS` not auto-injected | Write explicit arguments in prompt |
| Sub-skills in SKILL.md still use slash syntax | Explicitly list `@skills/...` sub-skills in Trae prompt |

## 9. Quick Reference

```
# Literature review
Use research-lit skill to search papers on "discrete diffusion models".

# Idea Discovery (full pipeline)
Use idea-discovery skill for "factorized gap in discrete diffusion LMs".

# Single deep review
Use research-review skill to review my research: [description or file reference].

# Auto review loop
Use auto-review-loop skill. Topic: "your paper topic".

# Paper writing
Use paper-writing skill based on NARRATIVE_REPORT.md.

# Deploy experiment
Use run-experiment skill. Deploy: python train.py --lr 1e-4 --epochs 100
```

## 10. Migration Checklist: Claude Code → Trae

- [ ] Go to `Settings → Rules and Skills`, select "Global" or "Project" installation scope
- [ ] Import ARIS skills' SKILL.md files
- [ ] Configure MCP server in `Settings → MCP`
- [ ] Use natural language to describe needs and trigger skills
- [ ] Verify MCP tools are available (codex or llm-chat)
- [ ] Quick test: `Use research-review skill to review my project`
