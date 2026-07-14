# ARIS Quick Setup Guide

> Get ARIS fully configured from scratch. Once done, you're ready to use the complete research workflow.
>
> This guide targets a **macOS local + remote Linux GPU server** setup with the recommended configuration: **Claude Code as executor, Codex MCP (GPT) as reviewer**.
>
> English | [中文版](SETUP_GUIDE_CN.md)

---

## Step 1: Install Required Tools

### 1.1 Claude Code

Claude Code is Anthropic's CLI tool — all ARIS skills run on top of it. See the [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) for installation.

```bash
claude --version   # verify installation
```

### 1.2 Codex CLI + MCP Registration

Codex CLI is OpenAI's CLI tool — ARIS uses it to call GPT as a cross-model reviewer. See the [Codex CLI docs](https://developers.openai.com/codex) for installation.

After installing, authenticate Codex (one-time, opens a browser to log in to ChatGPT) and register it as a Claude Code MCP server:

```bash
codex --version   # verify installation
codex login       # one-time ChatGPT auth (skip if already logged in)
claude mcp add codex -s user -- codex mcp-server
```

- `codex` (after `add`) — the registered name. ARIS skills hardcode this name, **do not change it**
- `-s user` — applies globally to all projects
- `codex mcp-server` — built-in subcommand that starts the MCP server mode

Restart Claude Code after registration. Verify:

```bash
claude mcp list | grep codex
# should show: codex: codex mcp-server - ✓ Connected
```

### 1.3 LaTeX Environment (Optional)

Required for Workflow 3 (paper writing), providing `latexmk` and `pdfinfo`:

```bash
brew install --cask mactex    # or: brew install basictex
brew install poppler          # provides pdfinfo

# verify
latexmk --version && pdfinfo -v
```
> If you only need Workflow 1 & 2 (idea discovery + auto review), LaTeX is not required.

## Step 2: Create a Research Project

```bash
mkdir ~/your-paper-project
cd ~/your-paper-project
git init
touch CLAUDE.md
```

- `git init` — some skills need git to locate the project root
- `CLAUDE.md` — Claude Code's project config file; the install script will write ARIS info into it

## Step 3: Install Skills

Install ARIS skills into your project via symlinks (the recommended project-local install method):

```bash
# 1. Clone ARIS once to a stable location, ~/aris_repo is the local dir name (customizable)
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo

# 2. Install in each project that uses ARIS (via symlinks):
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh

# Install only what you need (selective install):
bash ~/aris_repo/tools/install_aris.sh --list-groups                  # show the 10 skill groups
bash ~/aris_repo/tools/install_aris.sh --groups paper-core,lit-search # install by group
bash ~/aris_repo/tools/install_aris.sh --skills paper-writing         # by skill (hard deps auto-included)
# A fresh install with no selection flags (run in a terminal) walks an interactive per-group menu

# Other useful flags:
bash ~/aris_repo/tools/install_aris.sh --dry-run        # preview install plan, no changes
bash ~/aris_repo/tools/install_aris.sh --uninstall      # uninstall per manifest, leaves other files intact
```

The script shows an install plan and asks for confirmation (type `y`). See [`install_aris.sh`](tools/install_aris.sh):

```
.claude/skills/<skill>        ← one symlink per skill → ~/aris_repo/skills/<skill>
.aris/installed-skills.txt    ← install manifest (tracks every skill symlink ARIS created)
.aris/tools                   ← → ~/aris_repo/tools/ (helper scripts)
CLAUDE.md                     ← updates the ARIS config block
```

Symlinks reference ARIS repo source files directly — no copies. Updates fall into two cases:

```bash
# Case 1: upstream modified existing skill content
# symlinks pick up changes automatically, just pull the latest
cd ~/aris_repo && git pull

# Case 2: upstream added or removed skill directories
# pull first, then rerun the install script to sync
cd ~/aris_repo && git pull
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh
```

## Step 4: Configure GPU Server

If your experiments run on a remote GPU server, you need two things: SSH key-based auth + server info in CLAUDE.md.

### 4.1 Set Up SSH Key-Based Login

Make sure you have an SSH key locally; generate one if you don't:

```bash
ls ~/.ssh/id_*.pub
# output exists → key already present, skip the next command
# No such file → run:

ssh-keygen -t ed25519   # press Enter through all prompts
```

Copy your public key to the server:

```bash
# will ask for server password once
ssh-copy-id username@your-server-ip
```

Verify key-based login (should not ask for password):

```bash
ssh username@your-server-ip "echo ok"
```

### 4.2 Add Server Info to CLAUDE.md

Append the following to your project's `CLAUDE.md`, replacing with your actual values:

```markdown
## Remote Server

- gpu: remote
- SSH: `ssh username@your-server-ip` (key-based auth, no password)
- GPU: 8x RTX 4090 (24GB)
- Conda env: `YOUR_ENV` (Python 3.x + PyTorch x.x.x)
- Activate: `eval "$(/path/to/miniconda3/bin/conda shell.bash hook)" && conda activate YOUR_ENV`
- Code directory: `/home/user/experiments/`
- Use `tmux` for background jobs: `tmux new -d -s exp0 'bash -c "..."'`
```

You can also use `screen`: `screen -dmS exp0 bash -c '...'` (ARIS README defaults to `screen`).

Verify the remote environment (run on your local Mac, replace with your actual values):

```bash
ssh username@your-server-ip 'eval "$(/path/to/miniconda3/bin/conda shell.bash hook)" && conda activate YOUR_ENV && python --version && python -c "import torch; print(torch.__version__, torch.cuda.device_count())"'
```

Should output Python version, PyTorch version, and GPU count.

## Step 5: Initialize Research Wiki

Research Wiki is ARIS's core knowledge base — it automatically accumulates papers you've read, ideas you've generated, and experiments you've run. Other skills write to it automatically; you don't need to maintain it manually.

Open Claude Code in your research project directory and enter:

```
/research-wiki init
```

This creates a `research-wiki/` directory. See [`research_wiki.py`](tools/research_wiki.py):

```
research-wiki/
  index.md               ← categorical index (auto-generated)
  log.md                 ← append-only timeline
  gap_map.md             ← field gap map
  query_pack.md          ← compressed summary (for /idea-creator)
  papers/                ← auto-populated by /alphaxiv, /arxiv, etc.
  ideas/                 ← auto-populated by /idea-creator
  experiments/           ← auto-populated by /result-to-claim
  claims/                ← scientific claims
  graph/                 ← relationship graph (edges.jsonl)
```

## Step 6: Verify

Restart Claude Code and test in your research project directory:

**1. Test MCP connectivity** — enter in Claude Code:

```
Ask GPT via codex MCP: what is 1+1?
```

Receiving GPT's answer means cross-model communication is working.

**2. Test skill recognition** — enter in Claude Code:

```
/alphaxiv https://arxiv.org/abs/1706.03762
```

A successful invocation means skills are installed. This skill will also auto-write the paper into Research Wiki — check `research-wiki/papers/`.

---

After completing all steps, your research project structure looks like:

```
~/your-paper-project/
  CLAUDE.md               ← ARIS config + GPU server info
  .claude/skills/          ← skill symlinks
  .aris/
    installed-skills.txt   ← install manifest
    tools/                 ← → ARIS repo tools/
  research-wiki/           ← knowledge base (auto-accumulated)
  .git/                    ← git repository
```

You're now ready to use ARIS research workflows:

```
claude
> /idea-discovery "your research direction"          # Workflow 1 — be specific! not "NLP" but "factorized gap in discrete diffusion LMs"
> /experiment-bridge                                 # Workflow 1.5 — have a plan? implement + deploy + collect results
> /auto-review-loop "your paper topic or scope"      # Workflow 2: review → fix → re-review overnight
> /paper-writing "NARRATIVE_REPORT.md"               # Workflow 3: narrative → polished PDF
> /rebuttal "paper/ + reviews" — venue: ICML          # Workflow 4: parse reviews → draft rebuttal → follow-up
> /resubmit-pipeline "paper/" — venue: NeurIPS        # Workflow 5: port to new venue (text-only, no new experiments)
> /paper-talk "paper/" — venue: ICLR                  # Workflow 6: paper → Beamer + PPTX talk + speaker notes + assurance audits
> /research-pipeline "your research direction"       # Full pipeline: W1 → 1.5 → 2 → handoff; default stops at NARRATIVE_REPORT.md. Add `— auto_write: true, venue: ICLR` to chain W3 paper writing too
```
