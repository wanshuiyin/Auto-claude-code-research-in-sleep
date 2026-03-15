# Auto-claude-code-research-in-sleep (ARIS ⚔️)

![Hero](docs/hero_combined.svg)

[中文版 README](README_CN.md) | English

![Score Progression](docs/auto_review_score_curve.png)

> 🌙 **Let Claude Code do research while you sleep.** Wake up to find your paper scored, weaknesses identified, experiments run, and narrative rewritten — autonomously.

[![Featured in awesome-agent-skills](https://img.shields.io/badge/Featured%20in-awesome--agent--skills-blue?style=flat&logo=github)](https://github.com/VoltAgent/awesome-agent-skills) · [![AI Digital Crew - Project of the Day](https://img.shields.io/badge/AI%20Digital%20Crew-Project%20of%20the%20Day%20(2026.03.14)-orange?style=flat)](https://aidigitalcrew.com) · [💬 Join Community](#-community)

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous ML research workflows. These skills orchestrate **cross-model collaboration** — Claude Code drives the research while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer. 🔀 **Also supports [alternative model combinations](#-alternative-model-combinations) (e.g., GLM + GPT, GLM + MiniMax) — no Claude API required.**

> 💭 **Why not self-play with a single model?** Using Claude Code subagents or agent teams for both execution and review is technically possible, but tends to fall into **local minima** — the same model reviewing its own patterns creates blind spots.
>
> *Think of it like adversarial vs. stochastic bandits: a single model self-reviewing is the stochastic case (predictable reward noise), while cross-model review is adversarial (the reviewer actively probes weaknesses the executor didn't anticipate) — and adversarial bandits are fundamentally harder to game.*
>
> 💭 **Why two models, not more?** Two is the minimum needed to break self-play blind spots, and 2-player games converge to Nash equilibrium far more efficiently than n-player ones. Adding more reviewers increases API cost and coordination overhead with diminishing returns — the biggest gain is going from 1→2, not 2→4.
>
> Claude Code's strength is fast, fluid execution; Codex (GPT-5.4 xhigh) is slower but more deliberate and rigorous in critique. These complementary styles — **speed × rigor** — produce better outcomes than either model talking to itself.

## 📢 What's New

- **2026-03-14** — 📱 [Feishu/Lark integration](#-feishulark-integration-optional): three modes (off/push/interactive), mobile notifications for experiments, reviews, and checkpoints
- **2026-03-13** — 🛑 Human-in-the-loop: configurable `AUTO_PROCEED` checkpoints across all workflows. Full autopilot or step-by-step approval
- **2026-03-12** — 🔗 [Zotero](#-zotero-integration-optional) + [Obsidian](#-obsidian-integration-optional) + local PDFs + arXiv/Scholar: multi-source literature search with cross-model novelty verification
- **2026-03-11** — 🚀 Three end-to-end workflows complete: one prompt → top-venue-style paper. `/research-pipeline` chains idea discovery → auto review → paper writing autonomously
- **2026-03-09** — 📝 `/paper-writing` workflow: narrative report → structured outline → figures → LaTeX → compiled PDF → 2-round auto-improvement (4/10 → 8.5/10)

## 🚀 Quick Start

```bash
# 1. Install skills
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cp -r Auto-claude-code-research-in-sleep/skills/* ~/.claude/skills/

# 2. Set up Codex MCP (for review skills)
npm install -g @openai/codex
codex setup                    # set model to gpt-5.4 when prompted
claude mcp add codex -s user -- codex mcp-server

# 3. Use in Claude Code
claude
> /idea-discovery "your research direction"  # Workflow 1 — be specific! not "NLP" but "factorized gap in discrete diffusion LMs"
> /auto-review-loop                          # Workflow 2: review → fix → re-review overnight
> /paper-writing "NARRATIVE_REPORT.md"       # Workflow 3: narrative → polished PDF
> /research-pipeline "your research direction"  # Full pipeline: Workflow 1 → 2 → 3 end-to-end
```

> **Tip:** Workflows auto-continue at checkpoints by default (`AUTO_PROCEED=true`). To pause and review before each major step (e.g., before committing GPU time), override in your command:
> ```
> /research-pipeline "your topic" — AUTO_PROCEED: false
> ```

> **Important:** Codex MCP uses the model from `~/.codex/config.toml`, not from skill files. Make sure it says `model = "gpt-5.4"` (recommended). Other options: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. Run `codex setup` or edit the file directly.

See [full setup guide](#%EF%B8%8F-setup) for details and [alternative model combinations](#-alternative-model-combinations) if you don't have Claude/OpenAI API.

## ✨ Features

- 📊 **19 composable skills** — mix and match, or chain into full pipelines (`/idea-discovery`, `/auto-review-loop`, `/paper-writing`, `/research-pipeline`)
- 🔍 **Literature & novelty** — multi-source paper search (**[Zotero](#-zotero-integration-optional)** + **[Obsidian](#-obsidian-integration-optional)** + **local PDFs** + arXiv/Scholar) + cross-model novelty verification
- 💡 **Idea discovery** — literature survey → brainstorm 8-12 ideas → novelty check → GPU pilot experiments → ranked report
- 🔄 **Auto review loop** — 4-round autonomous review, 5/10 → 7.5/10 overnight with 20+ GPU experiments
- 📝 **Paper writing** — narrative → outline → figures → LaTeX → PDF → auto-review (4/10 → 8.5/10), one command
- 🤖 **Cross-model collaboration** — Claude Code executes, GPT-5.4 xhigh reviews. Adversarial, not self-play
- 📝 **Peer review** — review others' papers as a conference reviewer, with structured scoring and meta-review
- 🖥️ **GPU deployment** — auto rsync, screen sessions, multi-GPU parallel experiments, live monitoring
- 🔀 **Flexible models** — default Claude × GPT-5.4, also supports [GLM + GPT, GLM + MiniMax](#-alternative-model-combinations) — no Claude API required
- 🛑 **Human-in-the-loop** — configurable checkpoints at key decisions. `AUTO_PROCEED=true` for full autopilot, `false` to approve each step
- 📱 **[Feishu/Lark notifications](#-feishulark-integration-optional)** — three modes: **off (default, strongly recommended for most users)**, push-only (webhook, mobile alerts), interactive (approve/reject from Feishu). Zero impact when unconfigured

  <details>
  <summary>Preview: Push cards (group) &amp; Interactive chat (private)</summary>

  **Push Only** — group chat cards (experiment done, checkpoint, error, pipeline complete):

  <img src="assets/feishu_push.png" width="700" />

  **Interactive** — private chat with Claude Code (approve/reject, custom instructions):

  <img src="assets/feishu_interactive.jpg" width="700" />

  </details>

- 🧩 **Extensible** — domain-specific skills welcome! Add a `SKILL.md` and open a PR. See [community skills](#-all-skills) like [`dse-loop`](skills/dse-loop/SKILL.md) (architecture/EDA)

---

## 📈 Score Progression (Real Run)

A real overnight 4-round run on an ML research project, from borderline reject to submission-ready:

| Round | Score | What Happened |
|-------|-------|---------------|
| Initial | 5.0/10 | Borderline reject |
| Round 1 | 6.5/10 | Added standard metrics, discovered metric decoupling |
| Round 2 | 6.8/10 | Key claim failed to reproduce, pivoted narrative |
| Round 3 | 7.0/10 | Large seed study killed main improvement claim |
| Round 4 | **7.5/10** ✅ | Diagnostic evidence solidified, **submission ready** |

The loop autonomously ran **20+ GPU experiments**, rewrote the paper's narrative framing, and killed claims that didn't hold up — all without human intervention.

## 🧩 Awesome Community Skills & Extensions

Domain-specific skills and external projects contributed by the community. PRs welcome — just add a `skills/your-skill/SKILL.md` and open a PR!

| Type | Name | Domain | Description | Codex MCP? |
|------|------|--------|-------------|-----------|
| Skill | 🏗️ [`dse-loop`](skills/dse-loop/SKILL.md) | Architecture / EDA | Autonomous design space exploration — iteratively run, analyze, and tune parameters (gem5, Yosys, etc.). Works for any domain with tunable parameters | No |
| Skill | 🤖 [`idea-discovery-robot`](skills/idea-discovery-robot/SKILL.md) | Robotics / Embodied AI | Workflow 1 adaptation — grounds idea discovery in embodiment, benchmark, sim2real path, and real-robot safety constraints | Yes |
| External | 🔬 [Auto-Research-Refine](https://github.com/zjYao36/Auto-Research-Refine) | General | Turn a vague idea into an executable research proposal — bridges `/idea-discovery` and `/auto-review-loop`. Claude + GPT-5.4 iterative refinement | Yes |

> **⭐ Highlighted: [Auto-Research-Refine](https://github.com/zjYao36/Auto-Research-Refine)** — Fills the gap between "what to research" and "how to research it". Plug it into the ARIS pipeline:
>
> `/idea-discovery` → **`/research-refine`** → `/auto-review-loop` → `/paper-writing`
>
> Vague idea → Ranked ideas → **Executable proposal** → Polished paper

## 🔄 Workflows

These skills compose into a full research lifecycle. The three workflows can be used independently or chained together:

- **Exploring a new area (e.g., writing a survey)?** Start with Workflow 1 → `/idea-discovery`
- **Already have an idea + initial plan?** Jump straight to Workflow 2 → `/auto-review-loop`
- **Ready to write the paper?** Workflow 3 → `/paper-writing` (or step by step: `/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile` → `/auto-paper-improvement-loop`)
- **Full pipeline?** Workflow 1 → Workflow 2 → Workflow 3 → `/research-pipeline` — from literature survey all the way to submission

> ⚠️ **Important:** These tools accelerate research, but they don't replace your own critical thinking. Always review generated ideas with your domain expertise, question the assumptions, and make the final call yourself. The best research comes from human insight + AI execution, not full autopilot.

### Full Pipeline 🚀

```
/research-lit → /idea-creator → /novelty-check → implement → /run-experiment → /auto-review-loop → /paper-plan → /paper-figure → /paper-write → /auto-paper-improvement-loop → submit
  (survey)      (brainstorm)    (verify novel)    (code)      (deploy & run)    (review & fix)      (outline)     (plots)        (LaTeX+PDF)     (review ×2 + format)     (done!)
  ├──── Workflow 1: Idea Discovery ────┤              ├──── Workflow 2: Auto Loop ────┤   ├──────────────── Workflow 3: Paper Writing ──────────────────┤
```

📝 **Blog post:** [梦中科研全流程开源](http://xhslink.com/o/2iV33fYoc7Q)

### Workflow 1: Literature & Idea Discovery 🔍

> **"What's the state of the art? Where are the gaps?"**

Don't have a concrete idea yet? Just give a research direction — `/idea-creator` handles the rest:

1. 📚 **Survey** the landscape (recent papers, open problems, recurring limitations)
2. 🧠 **Brainstorm** 8-12 concrete ideas via GPT-5.4 xhigh
3. 🔍 **Filter** by feasibility, compute cost, and quick novelty search
4. 🛡️ **Validate** top ideas with deep novelty check + devil's advocate review
5. 🧪 **Pilot** top 2-3 ideas in parallel on different GPUs (30 min - 2 hr each)
6. 🏆 **Rank** by empirical signal — ideas with positive pilot results rise to the top

The output is a ranked `IDEA_REPORT.md` with hypotheses, pilot results, reviewer objections, and a suggested execution order. Ideas that fail are documented too, saving future dead-end exploration.

```
┌─────────────────────────────────────────────────────────────┐
│                  Idea Discovery                              │
│                                                              │
│   /research-lit     /idea-creator     /novelty-check         │
│   (find papers)     (brainstorm)      (verify novelty)       │
│         │                │                  │                │
│         ▼                ▼                  ▼                │
│   ┌──────────┐     ┌──────────┐       ┌──────────┐         │
│   │ Scan     │────▶│ Generate │──────▶│ Check if │         │
│   │ local    │     │ 8-12     │       │ idea is  │         │
│   │ papers + │     │ ideas    │       │ novel    │         │
│   │ search   │     │ + rank   │       │          │         │
│   └──────────┘     └──────────┘       └──────────┘         │
│                          │                  │                │
│                          ▼                  ▼                │
│                    ┌──────────┐       ┌──────────┐         │
│                    │ Filter   │──────▶│ External │         │
│                    │ by cost, │       │ LLM      │         │
│                    │ novelty  │       │ evaluates│         │
│                    └──────────┘       └──────────┘         │
│                                                              │
│   Typical flow:                                              │
│   1. /research-lit "discrete diffusion models"  (local → online) │
│   2. /idea-creator "DLLMs post training"               │
│   3. Review ranked ideas, pick top 2-3                       │
│   4. /novelty-check "top idea" (deep verification)           │
│   5. /research-review "top idea" (critical feedback)         │
│   6. Implement → /run-experiment → /auto-review-loop         │
└─────────────────────────────────────────────────────────────┘
```

**Skills involved:** `research-lit` + `idea-creator` + `novelty-check` + `research-review`

> 💡 **One-command shortcut:** `/idea-discovery "your research direction"` runs this entire workflow automatically.

> 🔄 **Human-in-the-loop:** Each phase presents results and waits for your feedback. Not happy? Tell it what's missing — it refines the prompt and regenerates. Trust the defaults? It auto-proceeds with the top-ranked option. You decide how hands-on to be.

> ⚙️ Pilot experiment budgets (max hours, timeout, GPU budget) are configurable — see [Customization](#%EF%B8%8F-customization).

📝 **Blog post:** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

### Workflow 2: Auto Research Loop 🔁 (sleep & wake up to results)

> **"Review my paper, fix what's wrong, repeat until it's good."**

```
┌─────────────────────────────────────────────────────────────┐
│                    Auto Review Loop                          │
│                                                              │
│   /research-review          /auto-review-loop                │
│   (single deep review)      (autonomous loop)                │
│         │                         │                          │
│         ▼                         ▼                          │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│   │ External  │──▶│ Implement│──▶│ Monitor  │──▶ repeat     │
│   │ LLM      │   │ fixes    │   │ results  │    until       │
│   │ reviews  │   │ & run    │   │          │    score ≥ 6   │
│   └──────────┘   │ experiments│  └──────────┘               │
│                   └──────────┘                               │
│                                                              │
│   When reviewer suggests a new method direction:             │
│   /novelty-check — verify idea isn't already published       │
│                                                              │
│   Supporting skills:                                         │
│   /run-experiment    — deploy to local/remote GPU            │
│   /analyze-results   — interpret experiment outputs          │
│   /monitor-experiment — check progress, collect results      │
└─────────────────────────────────────────────────────────────┘
```

**Skills involved:** `auto-review-loop` + `research-review` + `novelty-check` + `run-experiment` + `analyze-results` + `monitor-experiment`

> 💡 **One-command shortcut:** `/auto-review-loop "your paper topic"` runs this entire workflow automatically.

**🛡️ Key safety features:**

- 🔒 **MAX_ROUNDS = 4** — prevents infinite loops; stops early if score threshold is met
- ⏱️ **> 4 GPU-hour experiments skipped** — won't launch massive jobs; flags them for manual follow-up
- 🧠 **Prefer reframing over new experiments** — when both can address a weakness, chooses the cheaper path
- 🪞 **No hiding weaknesses** — explicit rule: "Do NOT hide weaknesses to game a positive score"
- 🔧 **Fix before re-review** — must actually implement fixes before resubmitting; no empty promises
- 💾 **Compact recovery** — persists state (`REVIEW_STATE.json`) after each round. If the context window fills up and auto-compacts mid-loop, the workflow reads the state file and resumes from where it left off — no human intervention needed

> ⚙️ MAX_ROUNDS, score threshold, and GPU limits are configurable — see [Customization](#%EF%B8%8F-customization).

📝 **Blog post:** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### Workflow 3: Paper Writing Pipeline 📝

> **"Turn my research narrative into a submission-ready PDF."** Requires a local LaTeX environment — see [Prerequisites](#prerequisites).

```
┌─────────────────────────────────────────────────────────────┐
│                   Paper Writing Pipeline                      │
│                                                               │
│   /paper-plan      /paper-figure     /paper-write             │
│   (outline)        (plots & tables)  (LaTeX draft)            │
│        │                │                 │                   │
│        ▼                ▼                 ▼                   │
│   ┌──────────┐    ┌──────────┐     ┌──────────┐              │
│   │ Claims-  │───▶│ Generate │────▶│ Section  │──┐           │
│   │ Evidence │    │ figures, │     │ by       │  │           │
│   │ Matrix + │    │ tables,  │     │ section  │  │           │
│   │ Section  │    │ LaTeX    │     │ LaTeX    │  │           │
│   │ Plan     │    │ includes │     │ draft    │  │           │
│   └──────────┘    └──────────┘     └──────────┘  │           │
│        │                                          │           │
│        │         /paper-compile                   │           │
│        │         (build PDF)                      │           │
│        │              │                           │           │
│        ▼              ▼                           ▼           │
│   ┌──────────────────────────────────────────────────┐       │
│   │ NARRATIVE_REPORT.md ──► PAPER_PLAN.md ──► paper/ │       │
│   │    (input)             (outline)      (LaTeX+PDF)│       │
│   └──────────────────────────────────────────────────┘       │
│                                                               │
│   Typical flow:                                               │
│   1. Write NARRATIVE_REPORT.md (from Workflow 2 results)      │
│   2. /paper-plan (claims-evidence matrix + section plan)      │
│   3. /paper-figure (comparison tables, training curves, etc.) │
│   4. /paper-write (section-by-section LaTeX generation)       │
│   5. /paper-compile (build PDF, fix errors, page check)       │
│   6. /auto-paper-improvement-loop (review ×2 + format check)  │
└─────────────────────────────────────────────────────────────┘
```

**Skills involved:** `paper-plan` + `paper-figure` + `paper-write` + `paper-compile` + `auto-paper-improvement-loop`

> **One-command shortcut:** `/paper-writing "NARRATIVE_REPORT.md"` runs this entire workflow automatically.

**Input:** A `NARRATIVE_REPORT.md` describing the research: claims, experiments, results, figures. The more detailed the narrative (especially figure descriptions and quantitative results), the better the output.

**Output:** A submission-ready `paper/` directory with LaTeX source, clean `.bib` (only cited entries), and compiled PDF.

**Key features:**
- 📐 **Claims-Evidence Matrix** — every claim maps to evidence, every experiment supports a claim
- 📊 **Auto figure generation** — line plots, bar charts, comparison tables from JSON data
- 🧹 **Clean bib** — automated filtering removes uncited entries (948→215 lines in testing)
- 📄 **Flexible sections** — 5-8 sections depending on paper type (theory papers often need 7)
- 🔍 **GPT-5.4 review** — each step optionally reviewed by external LLM
- ✂️ **De-AI polish** — removes AI writing patterns (delve, pivotal, landscape...)
- 🎯 **Page verification** — `pdftotext`-based precise check that main body fits page limit

> ⚠️ **What `/paper-figure` can and cannot do:** It auto-generates **data-driven plots** (training curves, bar charts, heatmaps) and **comparison tables** (LaTeX) from JSON/CSV data. It **cannot** generate architecture diagrams, pipeline figures, model diagrams, or grids of generated images — these must be created manually (e.g., draw.io, Figma, TikZ) and placed in `figures/` before running `/paper-write`. In a typical ML paper, ~60% of figures are auto-generated and ~40% are manual.

**Tested end-to-end:** Generated a 9-page ICLR 2026 theory paper (7 sections, 29 citations, 4 figures, 2 comparison tables) from a single NARRATIVE_REPORT.md — zero compilation errors, zero undefined references.

#### Auto Paper Improvement Loop ✨

After Workflow 3 generates the paper, `/auto-paper-improvement-loop` runs 2 rounds of GPT-5.4 xhigh content review → fix → recompile, plus a final format compliance check, autonomously polishing the paper from rough draft to submission-ready.

**Score Progression (Real Test — ICLR 2026 theory paper):**

| Round | Score | Key Changes |
|-------|-------|-------------|
| Round 0 | 4/10 (content) | Baseline |
| Round 1 | 6/10 (content) | Fixed assumptions, softened claims, renamed notation |
| Round 2 | 7/10 (content) | Added synthetic validation, stronger limitations |
| Round 3 | 5→8.5/10 (format) | Removed hero fig, appendix, compressed conclusion, float spacing |

**Final: 8 pages main body (ICLR limit: 9), 0 overfull hbox, ICLR-compliant.** +4.5 points across 3 rounds.

<details>
<summary>Round 1 fixes (6 items)</summary>

1. **CRITICAL — Assumption-model mismatch**: A boundedness assumption contradicted the model's distributional family. Replaced with a tail-compatible assumption and added formal truncation bridge.
2. **CRITICAL — Theory-practice gap**: Theory assumes idealized encoders, experiments use learned nonlinear encoders. Softened "validate" → "demonstrate practical relevance" and added explicit disclaimer.
3. **MAJOR — Missing quantitative metrics**: Added parameter count table (latent vs total) with honest accounting of system cost.
4. **MAJOR — Theorem not self-contained**: Added "Interpretation" paragraph listing all dependencies explicitly.
5. **MAJOR — Overclaim in novelty statement**: Scoped a broad "first convergence guarantee" to precise conditions under which it holds.
6. **MAJOR — Notation confusion**: Renamed a symbol that clashed with another key variable. Added Notation paragraph.

</details>

<details>
<summary>Round 2 fixes (4 items)</summary>

1. **MAJOR — Missing theory-aligned experiments**: Added a synthetic validation subsection directly testing the two main theoretical predictions under controlled conditions.
2. **MAJOR — Overclaim softening**: Replaced strong equivalence claims with appropriately hedged language across all files.
3. **MAJOR — Informal theoretical argument**: Formalized an informal justification into a proper proposition with explicit error bounds.
4. **MINOR — Weak limitations**: Expanded to explicitly list all assumptions and acknowledge missing standard evaluations.

</details>

<details>
<summary>Round 3 format fixes (8 items)</summary>

1. Removed hero figure block (saved ~0.7 pages)
2. Compressed conclusion from 15→9 lines
3. Moved synthetic validation to Appendix A
4. Moved comparison tables to Appendix B
5. Fixed overfull hbox (85pt) with `\resizebox`
6. Added compact float spacing (`\captionsetup`, `\textfloatsep`)
7. Inlined centered question block in introduction
8. Tightened `itemize` environments

</details>

---

## 🧰 All Skills

| Skill | Description | Needs Codex MCP? |
|-------|-------------|-----------------|
| 💡 [`idea-creator`](skills/idea-creator/SKILL.md) | Generate and rank research ideas given a broad direction (brainstorm + filter + validate) | Yes |
| 🔬 [`research-review`](skills/research-review/SKILL.md) | Single-round deep review from external LLM (xhigh reasoning) | Yes |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | Autonomous multi-round review→fix→re-review loop (max 4 rounds) | Yes |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | Scan [Zotero](#-zotero-integration-optional) + [Obsidian](#-obsidian-integration-optional) + local PDFs + [arXiv API](#arxiv-integration) + web search, analyze related work, find gaps | No (Optional: Zotero/Obsidian MCP) |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | Analyze experiment results, compute statistics, generate insights | No |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | Monitor running experiments, check progress, collect results | No |
| 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | Verify research idea novelty against recent literature before implementing | Yes |
| 🚀 [`run-experiment`](skills/run-experiment/SKILL.md) | Deploy experiments to local (MPS/CUDA) or remote GPU servers | No |
| 🎨 [`pixel-art`](skills/pixel-art/SKILL.md) | Generate pixel art SVG illustrations for READMEs, docs, or slides | No |
| 🔭 [`idea-discovery`](skills/idea-discovery/SKILL.md) | **Workflow 1 pipeline**: research-lit → idea-creator → novelty-check → research-review | Yes |
| 🏗️ [`research-pipeline`](skills/research-pipeline/SKILL.md) | **Full pipeline**: Workflow 1 → implement → Workflow 2 → Workflow 3, from direction to submission | Yes |
| 📐 [`paper-plan`](skills/paper-plan/SKILL.md) | Generate paper outline with claims-evidence matrix, figure plan, and citation scaffolding | Yes |
| 📊 [`paper-figure`](skills/paper-figure/SKILL.md) | Publication-quality matplotlib/seaborn plots from experiment data, with LaTeX snippets | Optional |
| ✍️ [`paper-write`](skills/paper-write/SKILL.md) | Section-by-section LaTeX generation with ICLR/NeurIPS/ICML templates | Yes |
| 🔨 [`paper-compile`](skills/paper-compile/SKILL.md) | Compile LaTeX to PDF, auto-fix errors, submission readiness checks | No |
| 🔄 [`auto-paper-improvement-loop`](skills/auto-paper-improvement-loop/SKILL.md) | 2-round content review + format check loop on generated paper (4/10 → 8.5/10) | Yes |
| 📝 [`paper-writing`](skills/paper-writing/SKILL.md) | **Workflow 3 pipeline**: paper-plan → paper-figure → paper-write → paper-compile → auto-paper-improvement-loop | Yes |
| 📄 [`arxiv`](skills/arxiv/SKILL.md) | Search, download, and summarize papers from arXiv. Standalone or as `/research-lit` supplement | No |
| 📱 [`feishu-notify`](skills/feishu-notify/SKILL.md) | [Feishu/Lark](#-feishulark-integration-optional) notifications — push (webhook) or interactive (bidirectional). Off by default | No |

---

## ⚙️ Setup

### Prerequisites

1. [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
2. (For review skills) [Codex CLI](https://github.com/openai/codex) installed and configured as MCP server:
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. (For Workflow 3: paper writing) **LaTeX** environment with `latexmk` and `pdfinfo`:
   ```bash
   # macOS
   brew install --cask mactex    # or: brew install basictex
   brew install poppler          # provides pdfinfo

   # Ubuntu/Debian
   sudo apt install texlive-full latexmk poppler-utils

   # Verify
   latexmk --version && pdfinfo -v
   ```
   > If you only need Workflow 1 & 2 (idea discovery + auto review), LaTeX is not required.

### Install Skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep

# Install all skills globally
cp -r skills/* ~/.claude/skills/

# Or install specific skills
cp -r skills/auto-review-loop ~/.claude/skills/
cp -r skills/research-lit ~/.claude/skills/
```

### Usage

```
# Workflow 1: Idea Discovery
> /idea-discovery "your research direction"          # full pipeline
> /research-lit "topic"                              # just literature survey (all sources)
> /research-lit "topic" — sources: zotero, web        # mix and match sources
> /research-lit "topic" — arxiv download: true         # also download top arXiv PDFs
> /arxiv "discrete diffusion" — download               # standalone arXiv search + download
> /idea-creator "topic"                              # just brainstorm

# Workflow 2: Auto Research Loop
> /auto-review-loop "your paper topic"               # review → fix → repeat
> /research-review "your paper"                      # single deep review

# Workflow 3: Paper Writing
> /paper-writing "NARRATIVE_REPORT.md"               # full pipeline
> /paper-plan "NARRATIVE_REPORT.md"                  # just outline
> /paper-compile "paper/"                            # just compile

# Full Pipeline
> /research-pipeline "your research direction"       # Workflow 1 → 2 → 3 end-to-end

# Supporting Skills
> /run-experiment train.py --lr 1e-4 --epochs 100
> /analyze-results figures/*.json
> /monitor-experiment server5
```

### 🌙 Auto-Allow for Overnight Runs (Optional)

To run the auto-review loop without clicking permission prompts, add to `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__codex__codex-reply",
      "Write",
      "Edit",
      "Skill(auto-review-loop)"
    ]
  }
}
```

<details>
<summary><h3>🖥️ GPU Server Setup (For Auto-Experiments)</h3></summary>

When GPT-5.4 says "run an ablation study" or "add a baseline comparison", Claude Code automatically writes the experiment script and deploys it to your GPU server. For this to work, Claude Code needs to know your server environment.

Add your server info to your project's `CLAUDE.md`:

```markdown
## Remote Server

- SSH: `ssh my-gpu-server` (key-based auth, no password)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`
- Use `screen` for background jobs: `screen -dmS exp0 bash -c '...'`
```

Claude Code reads this and knows how to SSH in, activate the environment, and launch experiments. GPT-5.4 (the reviewer) only decides **what** experiments to run — Claude Code figures out **how** based on your `CLAUDE.md`.

**No server?** The review and rewriting skills still work without GPU access. Only experiment-related fixes will be skipped (flagged for manual follow-up).

</details>

<details>
<summary><b>📚 Zotero Integration (Optional)</b></summary>

If you use [Zotero](https://www.zotero.org/) to manage your paper library, `/research-lit` can search your collections, read your annotations/highlights, and export BibTeX — all before searching the web.

**Recommended: [zotero-mcp](https://github.com/54yyyu/zotero-mcp)** (1.8k⭐, semantic search, PDF annotations, BibTeX export)

```bash
# Install
uv tool install zotero-mcp-server   # or: pip install zotero-mcp-server

# Add to Claude Code (Local API — requires Zotero desktop running)
claude mcp add zotero -s user -- zotero-mcp -e ZOTERO_LOCAL=true

# Or use Web API (works without Zotero running)
claude mcp add zotero -s user -- zotero-mcp \
  -e ZOTERO_API_KEY=your_key -e ZOTERO_USER_ID=your_id
```

> Get your API key at https://www.zotero.org/settings/keys

**What it enables in `/research-lit`:**
- 🔍 Search your Zotero library by topic (including semantic/vector search)
- 📂 Browse collections and tags
- 📝 Read your PDF annotations and highlights (what you personally found important)
- 📄 Export BibTeX for direct use in paper writing

**Not using Zotero?** No problem — `/research-lit` automatically skips Zotero and uses local PDFs + web search instead.

</details>

<details>
<summary><b>📓 Obsidian Integration (Optional)</b></summary>

If you use [Obsidian](https://obsidian.md/) for research notes, `/research-lit` can search your vault for paper summaries, tagged references, and your own insights.

**Recommended: [mcpvault](https://github.com/bitbonsai/mcpvault)** (760⭐, no Obsidian app needed, 14 tools, BM25 search)

```bash
# Add to Claude Code (point to your vault path)
claude mcp add obsidian-vault -s user -- npx @bitbonsai/mcpvault@latest /path/to/your/vault
```

**Optional complement: [obsidian-skills](https://github.com/kepano/obsidian-skills)** (13.6k⭐, by Obsidian CEO) — teaches Claude to understand Obsidian-specific Markdown (wikilinks, callouts, properties). Copy to your vault:

```bash
git clone https://github.com/kepano/obsidian-skills.git
cp -r obsidian-skills/.claude /path/to/your/vault/
```

**What it enables in `/research-lit`:**
- 🔍 Search your vault for notes on the research topic
- 🏷️ Find notes by tags (e.g., `#paper-review`, `#diffusion-models`)
- 📝 Read your processed summaries and insights (more valuable than raw papers)
- 🔗 Follow wikilinks to discover related notes

**Not using Obsidian?** No problem — `/research-lit` automatically skips Obsidian and works as before.

> 💡 **Zotero + Obsidian together**: Many researchers use Zotero for paper storage and Obsidian for notes. Both integrations work simultaneously — `/research-lit` checks Zotero first (raw papers + annotations), then Obsidian (your processed notes), then local PDFs, then web search.

#### arXiv Integration

`/research-lit` automatically queries the arXiv API for structured metadata (title, abstract, full author list, categories) — richer than web search snippets. No setup required.

By default, only metadata is fetched (no files downloaded). To also download the most relevant PDFs:

```
/research-lit "topic" — arxiv download: true              # download top 5 PDFs
/research-lit "topic" — arxiv download: true, max download: 10  # download up to 10
```

For standalone arXiv access, use the dedicated [`/arxiv`](skills/arxiv/SKILL.md) skill:

```
/arxiv "attention mechanism"           # search
/arxiv "2301.07041" — download         # download specific paper
```

</details>

### 📱 Feishu/Lark Integration (Optional)

Get mobile notifications when experiments finish, reviews score, or checkpoints need your input — without sitting in front of the terminal.

| Push Only (group cards) | Interactive (private chat) |
|:-:|:-:|
| <img src="assets/feishu_push.png" width="450" /> | <img src="assets/feishu_interactive.jpg" width="450" /> |

**Three modes — you choose per-project:**

| Mode | What happens | You need |
|------|-------------|----------|
| **Off** (default) | Nothing. Pure CLI, no Feishu | Nothing |
| **Push only** | Webhook notifications at key events. Mobile push, no reply | Feishu bot webhook URL |
| **Interactive** | Full bidirectional. Approve/reject ideas, reply to checkpoints from Feishu | [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) running |

<details>
<summary><b>Push Only Setup (5 min)</b></summary>

Group notifications with rich cards — experiment done, review scored, pipeline complete. Mobile push, no reply needed.

**Step 1: Create a Feishu group bot**

1. Open your Feishu group (or create a test group)
2. Group Settings → Bots → Add Bot → **Custom Bot**
3. Name it (e.g., `ARIS Notifications`), copy the **Webhook URL**
4. Security: add custom keyword `ARIS` (all notifications include this word), or leave unrestricted

**Step 2: Create config file**

```bash
cat > ~/.claude/feishu.json << 'EOF'
{
  "mode": "push",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID"
}
EOF
```

**Step 3: Test it**

```bash
curl -s -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "msg_type": "interactive",
    "card": {
      "header": {"title": {"tag": "plain_text", "content": "🧪 ARIS Test"}, "template": "blue"},
      "elements": [{"tag": "markdown", "content": "Push mode working! 🎉"}]
    }
  }'
```

You should see a blue card in your group. Skills will now automatically send rich cards at key events:

| Event | Card color | Content |
|-------|-----------|---------|
| Review scored ≥ 6 | 🟢 Green | Score, verdict, top weaknesses |
| Review scored < 6 | 🟠 Orange | Score, verdict, action items |
| Experiment complete | 🟢 Green | Results table, delta vs baseline |
| Checkpoint waiting | 🟡 Yellow | Question, options, context |
| Error | 🔴 Red | Error message, suggested fix |
| Pipeline done | 🟣 Purple | Score progression, deliverables |

</details>

<details>
<summary><b>Interactive Setup (15 min)</b></summary>

Everything Push mode does, **plus** bidirectional private chat with Claude Code via Feishu. Approve/reject ideas, reply to checkpoints, give custom instructions — all from your phone.

**How it works**: Push cards go to the **group** (everyone sees status). Interactive conversations happen in **private chat** with the bot (you reply, Claude Code acts on it).

**Step 1: Complete Push setup above first** (you'll keep both)

**Step 2: Create a Feishu app on [open.feishu.cn](https://open.feishu.cn/app)**

1. Click **Create Enterprise App** → name it (e.g., `ARIS Claude Bot`) → create
2. Left menu → **Add Capabilities** → check **Bot**
3. Left menu → **Permissions** → search and enable these 5 permissions:

| Permission | Scope | Why |
|-----------|-------|-----|
| `im:message` | Send & receive messages | Core messaging |
| `im:message:send_as_bot` | Send as bot | Bot replies |
| `im:message.group_at_msg:readonly` | Receive group @mentions | Group messages |
| `im:message.p2p_msg:readonly` | **Receive private messages** | ⚠️ **Easy to miss!** Without this, the bot connects but never receives your messages |
| `im:resource` | Access attachments | Images/files |

4. Left menu → **Events & Callbacks** → select **Long Connection** mode → add event: `im.message.receive_v1` → save

> ⚠️ **Important**: The "Long Connection" page may show "未检测到应用连接信息" — this is normal. You need to start the bridge first (Step 3), then come back and save.

5. Left menu → **Version Management** → **Create Version** → fill description → **Submit for Review**

> For personal/test Feishu organizations, approval is usually instant.

**Step 3: Deploy the bridge**

```bash
git clone https://github.com/joewongjc/feishu-claude-code.git
cd feishu-claude-code
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
```

Edit `.env`:

```bash
FEISHU_APP_ID=cli_your_app_id          # From app credentials page
FEISHU_APP_SECRET=your_app_secret      # From app credentials page
DEFAULT_MODEL=claude-opus-4-6          # ⚠️ Default is sonnet — change to opus for best results
DEFAULT_CWD=/path/to/your/project      # Working directory for Claude Code
PERMISSION_MODE=bypassPermissions      # Or "default" for safer mode
```

> ⚠️ **Model matters**: The default `claude-sonnet-4-6` works but may struggle with complex project context. `claude-opus-4-6` correctly identified 18 ARIS skills on first try where sonnet could not.

Start the bridge:

```bash
python main.py
# Expected output:
# ✅ 连接飞书 WebSocket 长连接（自动重连）...
# [Lark] connected to wss://msg-frontier.feishu.cn/ws/v2?...
```

For long-running use, put it in a screen session:

```bash
screen -dmS feishu-bridge bash -c 'cd /path/to/feishu-claude-code && source .venv/bin/activate && python main.py'
```

**Step 4: Save event config** — Go back to Feishu Open Platform → Events & Callbacks → the long connection should now show "已检测到连接" → **Save**

> If you published the app version before the bridge was running, you may need to create a new version (e.g., 1.0.1) and re-publish after saving event config.

**Step 5: Test private chat**

1. In Feishu, find the bot in your contacts (search by app name)
2. Send it a message: `你好`
3. It should reply via Claude Code

**If the bot doesn't reply**: Send `/new` to reset the session, then try again. Common issues:

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bot connects but never receives messages | Missing `im:message.p2p_msg:readonly` permission | Add permission → create new version → publish |
| Bot replies but doesn't know your project | `DEFAULT_CWD` points to wrong directory | Edit `.env` → restart bridge |
| Bot replies but seems less capable | Using `claude-sonnet-4-6` | Change to `claude-opus-4-6` in `.env` → restart |
| Old session has stale context | Session cached from before config change | Send `/new` in chat to start fresh session |
| "未检测到应用连接信息" when saving events | Bridge not running yet | Start bridge first, then save event config |

**Step 6: Update ARIS config**

```bash
cat > ~/.claude/feishu.json << 'EOF'
{
  "mode": "interactive",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID",
  "interactive": {
    "bridge_url": "http://localhost:5000",
    "timeout_seconds": 300
  }
}
EOF
```

Now skills will:
- **Push** rich cards to the group (status notifications, everyone sees)
- **Private chat** you for decisions (checkpoints, approve/reject, custom instructions)

#### Which skills send notifications?

| Skill | Events | Push | Interactive |
|-------|--------|------|-------------|
| `/auto-review-loop` | Review scored (each round), loop complete | Score + verdict | + wait for continue/stop |
| `/auto-paper-improvement-loop` | Review scored, all rounds done | Score progression | Score progression |
| `/run-experiment` | Experiments deployed | GPU assignment + ETA | GPU assignment + ETA |
| `/monitor-experiment` | Results collected | Results table | Results table |
| `/idea-discovery` | Phase transitions, final report | Summary at each phase | + approve/reject at checkpoints |
| `/research-pipeline` | Stage transitions, pipeline done | Stage summary | + approve/reject |

</details>

**Not using Feishu?** No problem — without `~/.claude/feishu.json`, all skills behave exactly as before. Zero overhead, zero side effects.

> 💡 **Alternative IM platforms**: The push-only webhook pattern works with any service that accepts incoming webhooks (Slack, Discord, DingTalk, WeChat Work). Just change the `webhook_url` and card format in `feishu-notify/SKILL.md`. For bidirectional support, see [cc-connect](https://github.com/chenhg5/cc-connect) (multi-platform bridge) or [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu).

## 🎛️ Customization

Skills are plain Markdown files. Fork and customize:

### Auto Review Loop (`auto-review-loop`)

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_ROUNDS` | 4 | Maximum review→fix→re-review iterations |
| `POSITIVE_THRESHOLD` | 6/10 | Score at which the loop stops (submission-ready) |
| `> 4 GPU-hour skip` | 4h | Experiments exceeding this are flagged for manual follow-up |

### Idea Discovery (`idea-discovery` / `idea-creator`)

| Constant | Default | Description |
|----------|---------|-------------|
| `PILOT_MAX_HOURS` | 2h | Skip any pilot estimated to take longer per GPU |
| `PILOT_TIMEOUT_HOURS` | 3h | Hard timeout — kill runaway pilots, collect partial results |
| `MAX_PILOT_IDEAS` | 3 | Maximum number of ideas to pilot in parallel |
| `MAX_TOTAL_GPU_HOURS` | 8h | Total GPU budget across all pilots |
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond. Set `false` to always wait for explicit approval |

Override inline: `/idea-discovery "topic" — pilot budget: 4h per idea, wait for my approval at each step`

### Literature Search (`research-lit`)

| Constant | Default | Description |
|----------|---------|-------------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | Local directories to scan for PDFs before searching online |
| `MAX_LOCAL_PAPERS` | 20 | Max local PDFs to scan (first 3 pages each) |

Override inline: `/research-lit "topic" — paper library: ~/Zotero/storage/`

### General (all skills using Codex MCP)

| Constant | Default | Description |
|----------|---------|-------------|
| `REVIEWER_MODEL` | `gpt-5.4` | OpenAI model used via Codex MCP. Also available: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. See [supported models](https://developers.openai.com/codex/models/) for full list. |

- **Prompt templates** — tailor the review persona and evaluation criteria
- **`allowed-tools`** — restrict or expand what each skill can do

## 🔀 Alternative Model Combinations

Don't have Claude / OpenAI API access? You can swap in other models — same cross-model architecture, different providers.

| Role | Default | Alt A: GLM + GPT | Alt B: GLM + MiniMax |
|------|---------|-------------------|----------------------|
| Executor (Claude Code) | Claude Opus/Sonnet | GLM-5 (ZhiPu API) | GLM-5 (ZhiPu API) |
| Reviewer (Codex MCP) | GPT-5.4 | GPT-5.4 (OpenAI API) | MiniMax-M2.5 (MiniMax API) |
| Need OpenAI API? | Yes | Yes | **No** |

### Step 1: Install Claude Code & Codex CLI

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
```

### Step 2: Configure `~/.claude/settings.json`

Open with: `nano ~/.claude/settings.json`

<details>
<summary><b>Alt A: GLM (executor) + GPT (reviewer)</b> — Only replace Claude, keep GPT-5.4 as reviewer</summary>

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
            "args": [
                "mcp-server"
            ]
        }
    }
}
```

Codex CLI uses your existing `OPENAI_API_KEY` (from `~/.codex/config.toml` or environment) — no extra config needed for the reviewer side.

</details>

<details>
<summary><b>Alt B: GLM (executor) + MiniMax (reviewer)</b> — No Claude or OpenAI API needed</summary>

```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "your_zai_api_key",
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5",
        "MINIMAX_API_KEY": "your_minimax_api_key"
    },
    "mcpServers": {
        "minimax-chat": {
            "command": "/usr/bin/python3",
            "args": ["/Users/YOUR_USERNAME/.claude/mcp-servers/minimax-chat/server.py"],
            "env": {
                "MINIMAX_API_KEY": "your_minimax_api_key",
                "MINIMAX_BASE_URL": "https://api.minimax.chat/v1",
                "MINIMAX_MODEL": "MiniMax-M2.5"
            }
        }
    }
}
```

> **⚠️ Extra step for Alt B:** Codex MCP uses OpenAI's Responses API (`/v1/responses`), which MiniMax does not support ([details](https://github.com/openai/codex/discussions/7782)). So Alt B uses a **custom MiniMax MCP server** instead of Codex. Full guide: [`docs/MINIMAX_MCP_GUIDE.md`](docs/MINIMAX_MCP_GUIDE.md). Quick steps:
>
> 1. Copy `mcp-servers/minimax-chat/server.py` → `~/.claude/mcp-servers/minimax-chat/server.py`
> 2. `pip3 install httpx`
> 3. After setup, tell Claude Code to rewrite all skills:
>
> ```
> Read skills/auto-review-loop-minimax/SKILL.md as a reference.
> It replaces mcp__codex__codex with mcp__minimax-chat__minimax_chat.
> Now rewrite ALL other skills that use mcp__codex__codex / mcp__codex__codex-reply
> to use mcp__minimax-chat__minimax_chat instead, following the same pattern.
> ```

</details>

Save: `Ctrl+O` → `Enter` → `Ctrl+X`

### Step 3: Install Skills & Run

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
cp -r skills/* ~/.claude/skills/

# Launch Claude Code (now powered by GLM)
claude
```

### Step 4: Let GLM Read the Project ⚠️ IMPORTANT

> **🔴 Do NOT skip this step.** GLM's prompt handling differs from Claude's. You must let GLM read through the project once to ensure skills are correctly parsed.

After launching `claude`, run in the conversation:

```
Read through this project and verify all skills are working:
/idea-creator, /research-review, /auto-review-loop, /novelty-check,
/idea-discovery, /research-pipeline, /research-lit, /run-experiment,
/analyze-results, /monitor-experiment, /pixel-art

For each skill, confirm: (1) it loads without errors, (2) the frontmatter is parsed correctly.
```

This lets GLM (acting as Claude Code) familiarize itself with the skill files and catch any compatibility issues upfront — rather than discovering them mid-workflow when it's expensive to fail.

> ⚠️ **Note:** Alternative models may behave differently from Claude and GPT-5.4. You may need to adjust `REVIEWER_MODEL` in the skills and tune prompt templates for best results. The core cross-model architecture remains the same.

## 📋 Roadmap

### Done

- [x] **Human-in-the-loop checkpoints** — idea-discovery and research-pipeline pause at key decision points for user approval. Configurable via `AUTO_PROCEED` (default: auto-continue; set `false` to always wait)
- [x] **Alternative model combinations** — [GLM + GPT, GLM + MiniMax](#-alternative-model-combinations) fully documented with setup guides. No Claude or OpenAI API required
- [x] **Workflow 3: Paper Writing Pipeline** — full chain: `/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile`. ICLR/NeurIPS/ICML templates, claims-evidence matrix, publication-quality figures, latexmk auto-fix. Inspired by [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar), [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills), [baoyu-skills](https://github.com/jimliu/baoyu-skills)

<details>
<summary>Show 6 more completed items</summary>

- [x] **Configurable REVIEWER_MODEL** — all Codex-dependent skills support custom reviewer model (default `gpt-5.4`, also works with `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`, etc.)

- [x] **Local paper library scanning** — `/research-lit` scans local `papers/` and `literature/` directories before external search, leveraging papers you've already read
- [x] **Idea Discovery pipeline** — `/idea-discovery` orchestrates research-lit → idea-creator → novelty-check → research-review in one command, with pilot experiments on GPU
- [x] **Full research pipeline** — `/research-pipeline` chains Workflow 1 (idea discovery) → implementation → Workflow 2 (auto-review-loop) end-to-end
- [x] **Peer review skill** — `/peer-review` for reviewing others' papers as a conference reviewer, with GPT-5.4 meta-review
- [x] **Cross-model collaboration** — Claude Code (executor) × Codex GPT-5.4 xhigh (reviewer) architecture, avoiding single-model self-play local minima

</details>

### Planned

- [x] **Feishu/Lark integration** — three modes (off/push/interactive), configurable via `~/.claude/feishu.json`. Push-only needs just a webhook URL; interactive uses [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code). Off by default — zero impact on existing workflows. See [setup guide](#-feishulark-integration-optional)
- [ ] **W&B integration** — pull training curves and metrics from Weights & Biases as feedback signal. Auto-review-loop can read loss/accuracy plots to diagnose training issues and suggest next experiments
  - Related projects: [wandb-mcp-server](https://github.com/wandb/wandb-mcp-server) (official W&B MCP, 40⭐), or via `wandb api` CLI
- [x] **Zotero MCP integration** — `/research-lit` searches Zotero collections, reads annotations/highlights, exports BibTeX. Recommended: [zotero-mcp](https://github.com/54yyyu/zotero-mcp) (1.8k⭐). See [setup guide](#-zotero-integration-optional)
- [x] **Obsidian integration** — `/research-lit` searches Obsidian vault for research notes, tagged references, wikilinks. Recommended: [mcpvault](https://github.com/bitbonsai/mcpvault) (760⭐) + [obsidian-skills](https://github.com/kepano/obsidian-skills) (13.6k⭐). See [setup guide](#-obsidian-integration-optional)
- [ ] More executor × reviewer combinations (Gemini, DeepSeek, etc.)
- [ ] **Daemon mode** — auto-restart Claude Code session via `launchd`/`systemd` for true unattended operation. Currently the orchestration layer requires an active CLI session; state files (`REVIEW_STATE.json`, `AUTO_REVIEW.md`) support resuming across sessions, but relaunch is manual ([#11](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/11))

## 💬 Community

**Domain-specific skills welcome!** The core skills cover general research workflows, but every field has its own tools and patterns. We welcome PRs that add new skills for your domain — EDA, bioinformatics, robotics, HPC, or anything else. Just add a `skills/your-skill/SKILL.md` and open a PR. See [`dse-loop`](skills/dse-loop/SKILL.md) for an example.

Join the WeChat group for discussion on Claude Code + AI-driven research workflows:

<img src="docs/wechat_group.jpg" alt="WeChat Group QR Code" width="300">

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260314b)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## 🙏 Acknowledgements

This project builds on and integrates with many excellent open-source projects:

**Core Infrastructure**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic's CLI for Claude, the execution backbone
- [Codex CLI](https://github.com/openai/codex) — OpenAI's CLI, used as MCP server for cross-model review

**Zotero Integration** ([setup guide](#-zotero-integration-optional))
- [zotero-mcp](https://github.com/54yyyu/zotero-mcp) — Zotero MCP server with semantic search and PDF annotations
- [Zotero](https://www.zotero.org/) — Open-source reference manager

**Obsidian Integration** ([setup guide](#-obsidian-integration-optional))
- [mcpvault](https://github.com/bitbonsai/mcpvault) — Obsidian vault MCP server (no app required)
- [obsidian-skills](https://github.com/kepano/obsidian-skills) — Claude Code skills for Obsidian Markdown by Steph Ango (Obsidian CEO)

**Paper Writing Inspiration**
- [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) — Academic paper writing with Claude
- [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) — Paper writing skill templates
- [baoyu-skills](https://github.com/jimliu/baoyu-skills) — Claude Code skills collection

**Feishu/Lark Integration** ([setup guide](#-feishulark-integration-optional))
- [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) — Bidirectional Feishu ↔ Claude Code bridge
- [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu) — Feishu bot for Claude
- [cc-connect](https://github.com/chenhg5/cc-connect) — Multi-platform messaging bridge
- [lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp) — Official Lark MCP server

**Community**
- [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — Curated list of Claude Code skills (featured)

## License

MIT
