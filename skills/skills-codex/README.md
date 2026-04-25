# `skills-codex`

Codex-native mirror of the ARIS research skill pack.

## Overview

This package currently contains `39` skills adapted for OpenAI Codex-style agents, plus a small set of shared reference files used by writing workflows.

It is meant to be copied into `~/.codex/skills/` so the mirrored skills are available locally without depending on the original `skills/` tree.

## Included Skills

The current skill set is:

- `ablation-planner`
- `analyze-results`
- `arxiv`
- `auto-paper-improvement-loop`
- `auto-review-loop`
- `auto-review-loop-llm`
- `auto-review-loop-minimax`
- `comm-lit-review`
- `dse-loop`
- `experiment-bridge`
- `experiment-plan`
- `feishu-notify`
- `formula-derivation`
- `grant-proposal`
- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `mermaid-diagram`
- `monitor-experiment`
- `novelty-check`
- `paper-compile`
- `paper-figure`
- `paper-illustration`
- `paper-plan`
- `paper-poster`
- `paper-slides`
- `paper-write`
- `paper-writing`
- `pixel-art`
- `proof-writer`
- `rebuttal`
- `research-lit`
- `research-pipeline`
- `research-refine`
- `research-refine-pipeline`
- `research-review`
- `result-to-claim`
- `run-experiment`
- `training-check`

## Layout

```text
skills-codex/
  <skill-name>/
    SKILL.md
    ...
  comm-lit-review/
    references/
  paper-write/
    templates/
  shared-references/
    ...
```

Notes:

- `shared-references/` is not a skill by itself; it supports `paper-plan` and `paper-write`.
- `comm-lit-review` includes extra reference files.
- `paper-write` includes venue templates used during drafting.

## Scope

This package mirrors portable skill content for Codex. It intentionally focuses on:

- task boundaries and workflows
- Codex-compatible instructions
- lightweight bundled references or templates required by the skills

It does not try to ship the full runtime environment. In particular, this package does not include:

- Python dependency installation
- LaTeX, Poppler, GPU, SSH, or conda setup
- MCP server configuration
- API keys or environment variables

The following upstream-only areas are also intentionally not mirrored here:

- `.system/*`

## Install

> 💡 **Recommended: project-local symlink** (since v0.4.2). Project isolation keeps ARIS workflows separate from other community skill packs (Superpowers, etc.). See issue [#118](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/118).

```bash
# 1. Clone ARIS once to a stable location
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo

# 2. Attach to a Codex project (auto-detects platform from AGENTS.md):
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh
# → creates .agents/skills/aris symlink → <aris-repo>/skills/skills-codex/
# → adds managed block to AGENTS.md telling agent to use only project-local skills

# Windows (PowerShell, junctions need admin or developer mode):
.\tools\install_aris.ps1 C:\path\to\your-paper-project
```

<details>
<summary><b>Alternative: legacy global install (`~/.codex/skills/`)</b></summary>

```bash
cp -a ~/aris_repo/skills/skills-codex/* ~/.codex/skills/
```

Global install increases the risk of skill name collisions when other community skill packs are also installed globally. Use only if you understand the trade-off and don't mix ARIS with other packs.

</details>

<details>
<summary><b>Alternative: project-local copy (per-project customization)</b></summary>

```bash
mkdir -p ~/your-project/.agents/skills
bash ~/aris_repo/tools/smart_update.sh \
    --project ~/your-project \
    --target-subdir .agents/skills/aris \
    --apply
# Update with the same command (smart_update detects personal customizations)
```

</details>

Optional companion dependency for the `deepxiv` skill:

```bash
pip install deepxiv-sdk
```

If you also use reviewer overlay packages, install this base package first, then apply the overlay on top.
