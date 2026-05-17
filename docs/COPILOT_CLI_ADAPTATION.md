# GitHub Copilot CLI Adaptation Guide (ARIS Workflows)

> Use ARIS research workflows in **GitHub Copilot CLI** (`gh copilot` / standalone `copilot`).
>
> **Verified with:** Copilot CLI v0.130+ (GA, May 2026). Run `copilot --version` to confirm. If your version differs, use `/model` to check available models and verify MCP support.

Copilot CLI natively supports SKILL.md files with the same YAML frontmatter format used by ARIS, making it one of the most compatible hosts — **no skill mirror needed**, mainline skills work directly.

## 1. Key Differences: Claude Code vs Copilot CLI

| Concept | Claude Code | Copilot CLI |
|---------|-------------|-------------|
| Skill invocation | `/skill-name "args"` | `/skill-name "args"` (identical) |
| Skill storage | `~/.claude/skills/skill-name/SKILL.md` | `.github/skills/skill-name/SKILL.md` (project) or `~/.copilot/skills/skill-name/SKILL.md` (global) |
| MCP servers | `claude mcp add ...` | `~/.copilot/mcp-config.json` or `.mcp.json` (project) |
| Project instructions | `CLAUDE.md` | `AGENTS.md` (root) or `.github/copilot-instructions.md` |
| Agent execution | Persistent CLI session | Persistent CLI session (similar) |
| File operations | Always available | `--allow-tool='write'` / `--allow-tool='shell'` |
| Skill discovery | Slash commands + auto-match | Slash commands + auto-match from `description` |
| Models | Claude Opus 4.6 | GPT-5 mini, GPT-4.1, GPT-5, o3 (configurable via `/model`) |

## 2. Setup

### 2.1 Install Copilot CLI

```bash
# Via GitHub CLI extension
gh extension install github/copilot-cli

# Or standalone
npm install -g @github/copilot-cli
```

### 2.2 Clone ARIS and install skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo
cd ~/your-project

# Symlink install (recommended, stays in sync with upstream)
bash ~/aris_repo/tools/install_aris_copilot.sh .
```

This creates:
```
.github/skills/<skill-name> -> ~/aris_repo/skills/<skill-name>
.aris/installed-skills-copilot.txt    # manifest
AGENTS.md                             # managed block added
```

Reconcile after upstream changes:
```bash
cd ~/aris_repo && git pull
bash ~/aris_repo/tools/install_aris_copilot.sh ~/your-project --reconcile
```

Uninstall:
```bash
bash ~/aris_repo/tools/install_aris_copilot.sh ~/your-project --uninstall
```

### 2.3 Alternative: Copy-based install

For environments where symlinks don't work:

```bash
# Global install
mkdir -p ~/.copilot/skills
cp -r ~/aris_repo/skills/* ~/.copilot/skills/
# Remove Codex-specific mirrors (not needed for Copilot CLI)
rm -rf ~/.copilot/skills/skills-codex*

# Update later
bash ~/aris_repo/tools/smart_update_copilot.sh --apply

# Project-level
bash ~/aris_repo/tools/smart_update_copilot.sh --project ~/your-project --apply
```

### 2.4 Configure Codex MCP reviewer

ARIS uses a cross-model reviewer (GPT-5.4/5.5 via Codex MCP). Configure it in Copilot CLI:

1. Install and authenticate Codex:
   ```bash
   npm install -g @openai/codex
   codex login
   ```

2. Add MCP server — edit `~/.copilot/mcp-config.json`:
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

   Or project-level `.mcp.json`:
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

3. Restart Copilot CLI. Verify with `/mcp` or check that `mcp__codex__codex` appears in available tools.

### 2.5 Alternative reviewer MCP (no OpenAI API)

Use the [`llm-chat`](../mcp-servers/llm-chat/) MCP server with any OpenAI-compatible API (DeepSeek, GLM, MiniMax, Kimi, etc.):

1. Install dependencies:
   ```bash
   cd ~/aris_repo
   python3 -m venv .venv
   .venv/bin/pip install -r mcp-servers/llm-chat/requirements.txt
   ```

2. Add to `~/.copilot/mcp-config.json` (absolute paths required):
   ```json
   {
     "mcpServers": {
       "llm-chat": {
         "command": "/path/to/aris_repo/.venv/bin/python3",
         "args": ["/path/to/aris_repo/mcp-servers/llm-chat/server.py"],
         "env": {
           "LLM_BASE_URL": "https://api.deepseek.com/v1",
           "LLM_API_KEY": "your_key",
           "LLM_MODEL": "deepseek-chat"
         }
       }
     }
   }
   ```

See [LLM_API_MIX_MATCH_GUIDE.md](LLM_API_MIX_MATCH_GUIDE.md) for tested provider configurations.

### 2.6 Project instructions (AGENTS.md)

Copilot CLI reads `AGENTS.md` for project-specific instructions. The installer adds a managed block automatically. Add your own sections:

```markdown
## GPU Server

- SSH: `ssh my-gpu-server` (key-based auth)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`

## Research Project

- Topic: [your research topic]
- Target venue: ICLR/NeurIPS/ICML
```

## 3. How to Invoke Skills

Copilot CLI supports the **same slash command syntax** as Claude Code:

```
/research-lit "discrete diffusion models"
/idea-discovery "factorized gap in discrete diffusion LMs"
/auto-review-loop "your paper topic"
/paper-writing "NARRATIVE_REPORT.md"
/research-pipeline "your direction"
```

Skills are also auto-discovered from their `description` field — just describe what you want naturally:

```
Find papers about discrete diffusion models
Run the full idea discovery pipeline for my research direction
```

Type `/` to see all available skills.

## 4. Workflow Mapping

Since Copilot CLI uses the same slash command syntax, **all workflows work identically to Claude Code**:

### Full Pipeline
```
/research-pipeline "your research direction"
```

### Individual Workflows

| Workflow | Command |
|----------|---------|
| W1: Idea Discovery | `/idea-discovery "direction"` |
| W1.5: Experiment Bridge | `/experiment-bridge` |
| W2: Auto Review | `/auto-review-loop "scope"` |
| W3: Paper Writing | `/paper-writing "NARRATIVE_REPORT.md"` |
| W4: Rebuttal | `/rebuttal "paper/ + reviews" — venue: ICML, character limit: 5000` |

### Parameters

Same syntax as Claude Code:
```
/research-pipeline "topic" — effort: beast, difficulty: nightmare, auto_write: true, venue: NeurIPS
/auto-review-loop "topic" — human checkpoint: true, compact: true
```

## 5. MCP Tool Calls

ARIS skills reference MCP tools by name. These work in Copilot CLI once configured:

| ARIS MCP tool | What it does | Required MCP server |
|--------------|-------------|-------------------|
| `mcp__codex__codex` | Send prompt to GPT-5.4/5.5 | Codex |
| `mcp__codex__codex-reply` | Continue conversation thread | Codex |
| `mcp__llm-chat__chat` | Send prompt to any OpenAI-compatible model | llm-chat |
| `mcp__zotero__*` | Search Zotero library | zotero |
| `mcp__obsidian-vault__*` | Search Obsidian vault | obsidian-vault |

> **Note:** If using `llm-chat` instead of Codex, use the adapted skill variant: `/auto-review-loop-llm`.

## 6. State Files & Recovery

ARIS workflows persist state for crash recovery. These work identically in Copilot CLI:

| File | Purpose | Written by |
|------|---------|-----------|
| `review-stage/REVIEW_STATE.json` | Auto-review loop progress | `/auto-review-loop` |
| `review-stage/AUTO_REVIEW.md` | Cumulative review log | `/auto-review-loop` |
| `idea-stage/IDEA_REPORT.md` | Ranked ideas with pilot results | `/idea-discovery` |
| `PAPER_PLAN.md` | Paper outline + claims matrix | `/paper-plan` |
| `refine-logs/FINAL_PROPOSAL.md` | Refined method proposal | `/research-refine` |
| `refine-logs/EXPERIMENT_PLAN.md` | Experiment roadmap | `/experiment-plan` |

If a session ends mid-workflow, start a new session — the skill reads state files automatically and resumes.

## 7. Permission Flags

Copilot CLI requires explicit permission for file writes and shell execution. For ARIS workflows (which need both), launch with:

```bash
copilot --allow-tool='write' --allow-tool='shell'
```

Or configure in `~/.copilot/config`:
```yaml
allowed_tools:
  - write
  - shell
```

> **Security note:** Only grant these permissions in projects where you trust the ARIS skills. The skills never execute arbitrary code — they only run experiment scripts you've approved.

## 8. Model Selection

Copilot CLI supports multiple executor models. Use `/model` to switch:

| Model | Best for | Notes |
|-------|----------|-------|
| GPT-5 mini | Fast iteration, simple tasks | Included in subscription |
| GPT-4.1 | Balanced quality/speed | Included in subscription |
| GPT-5 | Complex reasoning, long pipelines | Premium requests |
| o3 | Deep mathematical reasoning | Premium requests |

> **Tip:** For full research pipelines (`/research-pipeline`, `/paper-writing`), use GPT-5 or o3 for best results. For quick tasks (`/research-lit`, `/paper-compile`), GPT-5 mini is sufficient.

## 9. Copilot CLI-Specific Features

### Explore Agent

Use Copilot's built-in `/explore` for fast codebase questions without cluttering main context — useful before invoking ARIS skills:

```
/explore How is the experiment pipeline structured in this project?
```

### Task Agent

Use `/task` for running builds and tests alongside ARIS workflows:

```
/task Run pytest and report failures
```

### GitHub MCP Server

Copilot's native GitHub MCP integrates with ARIS workflows for issue/PR management:

```
/research-pipeline "topic"
# ... after completion ...
# Create a PR with the paper
```

### Web Fetch

The built-in `web_fetch` tool complements ARIS's `/research-lit` for fetching paper content:

```
/research-lit "topic" — sources: web
```

## 10. Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| Skills reference `CLAUDE.md` | Copilot reads `AGENTS.md` instead. The installer creates this. Skills that read `CLAUDE.md` internally will still work if you keep both files, or create a symlink: `ln -s AGENTS.md CLAUDE.md` |
| `allowed-tools` in SKILL.md | Copilot respects these but requires user-level permission flags (`--allow-tool`) to actually execute |
| Different executor model family | ARIS's cross-model review still works: Copilot (GPT) executes, Codex MCP (GPT) reviews. For true cross-family review, use `llm-chat` MCP with Claude/Gemini as reviewer |
| No auto-compact recovery | Copilot CLI handles long sessions natively. Use state files for manual recovery if needed |
| Context window varies by model | GPT-5 mini has smaller context. For long pipelines, use GPT-5 or break into stages |

### Cross-Model Review Consideration

When Copilot CLI uses GPT-5 as executor **and** Codex MCP also routes to GPT-5.5 as reviewer, you lose the cross-family diversity that ARIS recommends. For maximum review quality, consider:

1. Use `llm-chat` MCP with **Claude** as reviewer (true cross-family):
   ```json
   {
     "mcpServers": {
       "llm-chat": {
         "command": "/path/to/.venv/bin/python3",
         "args": ["/path/to/mcp-servers/llm-chat/server.py"],
         "env": {
           "LLM_BASE_URL": "https://api.anthropic.com/v1",
           "LLM_API_KEY": "your_anthropic_key",
           "LLM_MODEL": "claude-sonnet-4-6"
         }
       }
     }
   }
   ```

2. Or use the dedicated [`claude-review`](../mcp-servers/claude-review/) MCP server.

## 11. Quick Reference

```bash
# Install skills to project
bash ~/aris_repo/tools/install_aris_copilot.sh .

# Update after upstream changes
cd ~/aris_repo && git pull
bash ~/aris_repo/tools/install_aris_copilot.sh ~/your-project --reconcile

# Launch Copilot with full permissions for ARIS
copilot --allow-tool='write' --allow-tool='shell'

# Run workflows (same as Claude Code)
/research-lit "discrete diffusion models"
/idea-discovery "factorized gap" — effort: max
/auto-review-loop "paper topic" — difficulty: hard
/paper-writing "NARRATIVE_REPORT.md" — venue: NeurIPS
/rebuttal "paper/ + reviews" — venue: ICML, character limit: 5000
```

## 12. Migration Checklist: Claude Code → Copilot CLI

- [ ] Install skills: `bash tools/install_aris_copilot.sh .`
- [ ] Configure MCP: add Codex or llm-chat to `~/.copilot/mcp-config.json`
- [ ] Copy `CLAUDE.md` content to `AGENTS.md` (or keep both + symlink)
- [ ] Set permission flags: `--allow-tool='write' --allow-tool='shell'`
- [ ] Verify: type `/` to see ARIS skills listed
- [ ] Test: `/research-review "your draft"` to confirm MCP reviewer works
- [ ] (Optional) Consider cross-family reviewer for GPT executor + non-GPT reviewer
