# Auto-claude-code-research-in-sleep (ARIS ⚔️🌙)

💡 *Use ARIS in Claude Code / Cursor / Trae as a skill-based workflow, or get the full experience with the standalone CLI — enjoy any way you like!*

🤖 **AI agents:** Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) instead — structured for LLM consumption, not human browsing.

🔥 [**ARIS-Code CLI — 独立安装版**](docs/ARIS-Code-README_CN.md) · [English](docs/ARIS-Code-README_EN.md) | [⬇️ Download](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest)

> 📰 **ARIS-Code v0.4.4** (2026-04-20) — **Setup UX + reviewer routing fixes** (resolves [#158](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/158), [#162](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/162)) | `/setup` no longer forces Bearer for Anthropic + custom URL (fixes ModelScope / `code.newcli.com` etc.) | Provider-aware proxy URL hints | Stale state no longer leaks across provider switches | LlmReview smart fallback
>
> <details><summary>Previous versions</summary>
>
> **v0.4.3** (2026-04-17) — **Third-party Anthropic-compat proxy support** (Bedrock etc.) | Skip beta flags that proxies reject | Propagate custom base URL for `anthropic` provider | Credit [@screw-44](https://github.com/screw-44)
>
> **v0.4.2** (2026-04-17) — **Auto-compaction corruption fix** | Compaction summary preserved on OpenAI-compat executors | Shell-provided API keys no longer erased on launch
>
> **v0.4.1** (2026-04-15) — **Plan mode** (`/plan`) | Cooperative Ctrl+C interrupt | Auto-retry (429/5xx/network) | **Research Wiki** 📚 (persistent knowledge base) | **Self-Evolution** 🧬 (`/meta-optimize`) | Local models (LM Studio/Ollama) | 62 skills synced
>
> **v0.3.11** (2026-04-13) — Reviewer Anthropic-compatible mode (Claude via proxy)
>
> **v0.3.9** (2026-04-11) — Proxy/custom base URL (CCSwitch) | Local models (LM Studio/Ollama) | Windows (experimental)
>
> **v0.3.5** (2026-04-08) — **Research Wiki** (persistent papers/ideas/experiments/claims + relationship graph) | **Meta-Optimize** self-evolution (analyze logs → propose SKILL.md patches)
>
> **v0.3.0** (2026-04-03) — Multi-file memory index | Rich task system (TodoWrite) | `/plan` | Security hardening
>
> **v0.2.2** (2026-04-03) — `/plan` step-by-step planning | `/tasks` persistent tracking
>
> **v0.2.1** (2026-04-03) — Persistent Memory | Kimi K2.5 multi-turn fix | CJK cursor fix
>
> **v0.2.0** (2026-04-02) — Open source | Kimi + MiniMax + GLM support | Smart LlmReview routing | CI/CD
>
> **v0.1.0** (2026-04-02) — Initial release | Multi-executor & reviewer | 42 bundled skills
>
> </details>

<img src="docs/aris-code-banner.png" width="600" alt="ARIS-Code CLI">

![ARIS Logo](docs/aris_logo.svg)

![Hero](docs/hero_combined.svg)

[中文版 README](README_CN.md) | English

![Score Progression](docs/auto_review_score_curve.png)

> 🌙 **Let Claude Code do research while you sleep.** Wake up to find your paper scored, weaknesses identified, experiments run, and narrative rewritten — autonomously.
>
> 🪶 **Radically lightweight — zero dependencies, zero lock-in.** The entire system is plain Markdown files. No framework to learn, no database to maintain, no Docker to configure, no daemon to babysit. Every skill is a single `SKILL.md` readable by any LLM — swap Claude Code for [Codex CLI](skills/skills-codex/), [OpenClaw](docs/OPENCLAW_ADAPTATION.md), [Cursor](docs/CURSOR_ADAPTATION.md), [Trae](docs/TRAE_ARIS_RUNBOOK_EN.md), [Antigravity](docs/ANTIGRAVITY_ADAPTATION.md), Windsurf, or your own agent and the workflows still work. Fork it, rewrite it, adapt it to your stack.
>
> *💡 ARIS is a methodology, not a platform. What matters is the research workflow — take it wherever you go. 🌱*

[![Featured on PaperWeekly](https://img.shields.io/badge/Featured%20on-PaperWeekly-red?style=flat)](https://mp.weixin.qq.com/s/tDniVryVGjDkkkWl-5sTkQ) · [![PaperWeekly — MiniMax-M2.7](https://img.shields.io/badge/PaperWeekly-MiniMax--M2.7-red?style=flat)](https://mp.weixin.qq.com/s/KLFU74lAL2FAIc9K6i1Kqg) · [![Featured in awesome-agent-skills](https://img.shields.io/badge/Featured%20in-awesome--agent--skills-blue?style=flat&logo=github)](https://github.com/VoltAgent/awesome-agent-skills) · [![AI Digital Crew - Project of the Day](https://img.shields.io/badge/AI%20Digital%20Crew-Project%20of%20the%20Day%20(2026.03.14)-orange?style=flat)](https://aidigitalcrew.com) · [💬 Join Community](#-community) · [![Cite](https://img.shields.io/badge/📖_Cite_Us-BibTeX-green?style=flat)](#-citation)

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous ML research workflows. These skills orchestrate **cross-model collaboration** — Claude Code drives the research while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer. 🔀 **Also supports [alternative model combinations](#-alternative-model-combinations) (Kimi, LongCat, DeepSeek, etc.) — no Claude or OpenAI API required.** For example, [MiniMax-M2.7 + GLM-5 or GLM-5 + MiniMax-M2.7](docs/MiniMax-GLM-Configuration.md). 🤖 **[Codex CLI native](skills/skills-codex/)** — full skill set also available for OpenAI Codex. 🖱️ **[Cursor](docs/CURSOR_ADAPTATION.md)** — works in Cursor too. 🖥️ **[Trae](docs/TRAE_ARIS_RUNBOOK_EN.md)** — ByteDance AI IDE. 🚀 **[Antigravity](docs/ANTIGRAVITY_ADAPTATION.md)** — Google's agent-first IDE. 🆓 **[Free tier via ModelScope](docs/MODELSCOPE_GUIDE.md) — zero cost, zero lock-in.**

> 💭 **Why not self-play with a single model?** Using Claude Code subagents or agent teams for both execution and review is technically possible, but tends to fall into **local minima** — the same model reviewing its own patterns creates blind spots.
>
> *Think of it like adversarial vs. stochastic bandits: a single model self-reviewing is the stochastic case (predictable reward noise), while cross-model review is adversarial (the reviewer actively probes weaknesses the executor didn't anticipate) — and adversarial bandits are fundamentally harder to game.*
>
> 💭 **Why two models, not more?** Two is the minimum needed to break self-play blind spots, and 2-player games converge to Nash equilibrium far more efficiently than n-player ones. Adding more reviewers increases API cost and coordination overhead with diminishing returns — the biggest gain is going from 1→2, not 2→4.
>
> Claude Code's strength is fast, fluid execution; Codex (GPT-5.4 xhigh) is slower but more deliberate and rigorous in critique. These complementary styles — **speed × rigor** — produce better outcomes than either model talking to itself.
>
> 🧿 **Want the strongest possible reviewer?** Add `— reviewer: oracle-pro` to any skill to route reviews through **GPT-5.4 Pro** via [Oracle MCP](https://github.com/steipete/oracle). Pro-level reasoning for proof verification, experiment auditing, and final stress tests. Works with API key or free browser mode. [Setup →](#-optional-gpt-54-pro-via-oracle)

## 🎯 More Than Just a Prompt

> These are full pipelines — you can also use each workflow independently. Already have an idea? Skip to Workflow 1.5. Have results? Jump to Workflow 3. Got reviews? Jump to Workflow 4. Want persistent memory? Enable [Research Wiki](#-research-wiki--persistent-research-memory). See [Quick Start](#-quick-start) for all commands and [Workflows](#-workflows) for the full breakdown.

**Basic mode** — give ARIS a research direction, it handles everything:

```
/research-pipeline "factorized gap in discrete diffusion LMs"
```

**🔥 Targeted mode** — got a paper you want to improve? Give ARIS the paper + the code:

```
/research-pipeline "improve method X" — ref paper: https://arxiv.org/abs/2406.04329, base repo: https://github.com/org/project
```

ARIS reads the paper → finds its weaknesses → clones the codebase → generates ideas that specifically fix *those* weaknesses with *that* code → runs experiments → writes your paper. Like telling a research assistant: *"read this paper, use this repo, find what's missing, and fix it."*

> Mix and match: `ref paper` only = "what can be improved?", `base repo` only = "what can I build with this code?", both = "improve *this* paper using *this* code."

**🔥 Rebuttal mode** — reviews just dropped? Don't panic. ARIS reads every concern, builds a strategy, and drafts a rebuttal that's grounded, structured, and under the character limit:

```
/rebuttal "paper/ + reviews" — venue: ICML, character limit: 5000
```

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `venue` | `ICML` | Target venue (ICML/NeurIPS/ICLR/CVPR/ACL/AAAI/ACM) |
| `character limit` | — | **Required.** Hard character limit for rebuttal text |
| `quick mode` | `false` | Stop after parsing + strategy (Phase 0-3). See what reviewers want before drafting |
| `auto experiment` | `false` | Auto-run supplementary experiments via `/experiment-bridge` when reviewers ask for new evidence |
| `max stress test rounds` | `1` | How many times GPT-5.4 xhigh stress-tests the draft |
| `max followup rounds` | `3` | Per-reviewer follow-up round limit |

Three safety gates — rebuttal will NOT finalize if any fails:
- 🔒 **No fabrication** — every claim maps to paper/review/user-confirmed result
- 🔒 **No overpromise** — every promise is user-approved
- 🔒 **Full coverage** — every reviewer concern is tracked

Two outputs: `PASTE_READY.txt` (exact char count, paste to venue) + `REBUTTAL_DRAFT_rich.md` (extended version for manual editing).

**After acceptance** — your paper is in, now prepare the presentation:

```
/paper-slides "paper/"     # → Beamer PDF + PPTX + speaker notes + Q&A prep
/paper-poster "paper/"     # → A0/A1 poster PDF + editable PPTX + SVG
```

> *💡 From idea to paper to podium — one toolchain. 🌱*

## 🏆 Papers Built with ARIS

| Paper | Score | Venue | Author | Stack |
|-------|:-----:|-------|--------|-------|
| CS Paper | **8/10** "clear accept" | CS Conference | [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) | Claude Code + GPT-5.4 |
| AAAI Paper | **7/10** "good paper, accept" | AAAI 2026 Main Technical | [@xinbo820-web](https://github.com/xinbo820-web) | Pure Codex CLI |
| UAV-CC | Under review | IEEE TGRS | [@wxx827](https://github.com/wxx827) | Claude Opus 4.6 + Codex 5.4 xhigh + Cursor |

> 🎉 Built with ARIS — from idea to submission. [Full details + PDFs →](#-community-showcase--papers-built-with-aris)

## 📢 What's New

- **2026-05-05** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🗡 **`/kill-argument` — adversarial Attack-Adjudication review for theory papers** ([#206](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/206)). Two fresh codex 5.5 + xhigh threads: Thread 1 writes the strongest 200-word rejection memo a senior area chair would produce; Thread 2 (independent adjudicator, NOT defender) reads the current paper and classifies each rejection point as `answered_by_current_text` / `partially_answered` / `still_unresolved` with file:line evidence. Output: `KILL_ARGUMENT.{md,json}`, detect-only. Integrated as **Phase 5.6** of `/paper-writing` (between claim-audit and citation-audit) and as the canonical implementation called from `/auto-paper-improvement-loop` Step 5.5 — replaces inline prompt in both places. Mandatory at `assurance: submission` for theory-heavy / scope-heavy papers; emits `NOT_APPLICABLE` for empirical papers without scope claims. Audit JSON is `verify_paper_audits.sh`-compatible (full schema per `shared-references/assurance-contract.md`, 6-state verdict). Catches the failure mode score-based reviews miss: when every local component is correct (numbers match, cites resolve, theorems prove) but the paper still oversells what it actually establishes.
- **2026-05-04** — ![FIX](https://img.shields.io/badge/FIX-orange?style=flat-square) 🪲 **`/research-wiki` and 8 caller skills now resolve helper via fallback chain** ([#204](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/204)). Bug: after `bash tools/install_aris.sh` the helper lives at `.aris/tools/research_wiki.py` (symlink), but skills hard-coded `tools/research_wiki.py` and silently failed when invoked — `research-wiki/` stayed empty across full W1 runs. Fix: 3-layer chain (`.aris/tools/` → `tools/` → `$ARIS_REPO/tools/`) codified in [`shared-references/wiki-helper-resolution.md`](skills/shared-references/wiki-helper-resolution.md). The manual-copy workaround at `<project>/tools/research_wiki.py` is layer 2, so users who `cp`-installed the helper as a temporary fix continue to work. **⚠️ Existing users**: rerun `bash tools/install_aris.sh` once — also picks up a separate Python 3.9 `ImportError` fix in the helper.
- **2026-05-03** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎨 **Opt-in `— style-ref: <source>` for writer-side skills** ([#202](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/202)). `/paper-{plan,write,writing,illustration,poster,slides}`, `/grant-proposal`, and `/auto-paper-improvement-loop` accept an optional `— style-ref: <source>` argument that mimics a reference paper's *structural* style (section ordering, theorem/figure density, sentence cadence, citation style) **without copying its prose, claims, or terminology**. Sources: local `.tex` dir/file, local PDF, arXiv id (`2501.12345` or `arxiv:2501.12345`), HTTP/HTTPS URL. Overleaf URLs/IDs are rejected — clone via `/overleaf-sync setup <id>` first. **Default OFF**; existing behavior unchanged when the flag is absent. Reviewer / auditor sub-skills (`/proof-checker`, `/paper-claim-audit`, `/citation-audit`, the improvement-loop reviewer) never see the style ref — cross-model review independence preserved. **⚠️ Existing ARIS users**: the helper ships at `tools/extract_paper_style.py`, distributed via the `.aris/tools` symlink (`install_aris.sh` Phase 0, added in [#192](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/192)). **Re-run `bash tools/install_aris.sh` once** to refresh the symlink and pick up the helper. Manual fallback: `cp <ARIS-repo>/tools/extract_paper_style.py <your-project>/tools/`. Without either, the writer skill aborts with a clear error pointing here.
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🪨 **Community spotlight: [rosetta](https://github.com/SyntaxSmith/rosetta)** by [@SyntaxSmith](https://github.com/SyntaxSmith). Programmatic access to **ChatGPT Pro / `gpt-5.5-pro` / DeepResearch** from Node, via Chrome CDP Fetch interception + WebSocket second-leg streaming; ships an MCP server for Claude Code / Codex / Cline. Alternative implementation path to Oracle MCP for ARIS users invoking `— reviewer: oracle-pro` — same target capability (Pro-tier reviewer), different mechanics. Indexed under [Awesome Community Skills & Extensions](#-awesome-community-skills--extensions). 🌟 if you're using it!
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 💎🧿 **Model & MCP routing updates**. (a) [`/gemini-search`](skills/gemini-search/SKILL.md) default bumped to `gemini-3-pro-preview` (strongest Gemini, out-of-box). ⚠️ **Action required**: requires `gemini-cli` v0.40+ (run `gemini --version`; upgrade with `npm i -g @google/gemini-cli` if older). Legacy override: `/gemini-search "topic" — model: gemini-2.5-pro`. Other overrides: `gemini-3-flash-preview` (faster), `auto-gemini-3` (load-routed). (b) [`/idea-discovery`](skills/idea-discovery/SKILL.md) Phase 1 now includes Gemini in its literature survey by default ([#199](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/199)) — auto-injects `— sources: all, gemini` into `/research-lit` unless the user passed an explicit `— sources:`; graceful skip if `gemini-cli` not installed. (c) Oracle MCP upstream PR queue ([`steipete/oracle/pulls`](https://github.com/steipete/oracle/pulls)) is the first triage stop when invoking `— reviewer: oracle-pro` (especially `o3-deep-research` / `gpt-5.5-pro`) — ARIS does not vendor Oracle MCP; check upstream first if behavior surprises you ([reviewer-routing.md](skills/shared-references/reviewer-routing.md))
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛠️🔗 **Tools-infrastructure migration started**. (a) [`install_aris.sh`](tools/install_aris.sh) creates optional `.aris/tools` symlink ([#192](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/192), closes [#174](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/174)) — Phase 0 of the 4-step tools-stability plan (#174 → #176 → #177 → #178); idempotent, **zero impact until rerun**. (b) [`/experiment-queue`](skills/experiment-queue/SKILL.md) orchestration paths repaired ([#193](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/193)) — first real user of the symlink; 7 cascading bugs fixed via 3 rounds of Codex MCP `gpt-5.5` xhigh audit. Pure prose + docstring; `queue_manager.py` logic untouched. Windows `install_aris.ps1` parallel update tracked as follow-up
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔬 **Three new opt-in audit flags via fast-path delegated-agent workflow** ([#187](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/187), [#188](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/188), [#189](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/189)). [`/citation-audit --uncited`](skills/citation-audit/SKILL.md) surfaces bib entries with no `\cite{}` reference (detect-only). [`/proof-checker --deep-fix`](skills/proof-checker/SKILL.md) adds a repair-grade plan to the Phase 1 reviewer prompt (corrected statement / patch plan / closure tests + Schur/quadratic-form algebra sanity). [`/proof-checker --restatement-check`](skills/proof-checker/SKILL.md) adds Phase 3.6 cross-location theorem drift detection (6 drift signatures). **Zero behavior change** when flags unset. Plus doc PRs [#190](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/190) (thread-policy) + [#191](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/191) (auto-loop xref). Delegated-agent + maintainer-fixup pattern; Codex MCP `gpt-5.5` xhigh review caught 6+ blockers
- **2026-05-01** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔍 **Gemini + OpenAlex literature sources for `/research-lit`** ([#175](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/175), community contribution by [@stdAri](https://github.com/stdAri)). Two opt-in sources: [`/gemini-search`](skills/gemini-search/SKILL.md) (AI-driven discovery via [`jamubc/gemini-mcp-tool`](https://github.com/jamubc/gemini-mcp-tool) MCP) and [`/openalex`](skills/openalex/SKILL.md) (250M+ work open citation graph, no API key). Triggered via `— sources: gemini` or `— sources: openalex`; **zero behavior change** when default `all` (both excluded). Maintainer fixups: corrected `@google/gemini-cli` npm name; added `try/except ImportError` + bash preflight for graceful OpenAlex skip when `requests` missing
- **2026-04-30** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📝 **`/rebuttal` per-reviewer thread mode + transferable patterns** ([SKILL.md](skills/rebuttal/SKILL.md)). Adds `VENUE_MODE` (`single_document` | `per_reviewer_thread`) for OpenReview-style venues, `reviewer_priority: pivotal` routing, `structural_distinction` response mode, 5 reviewer-defensive heuristics, 2 Phase 5 lints, and severity-scaled stress rounds. Default `VENUE_MODE = single_document` keeps ICML-style behavior — **zero change for existing users**. Three rounds of cross-model review before/after merge
- **2026-04-30** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🪞 **Codex skill mirror rebuilt + dedicated install/update chain** ([#179](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/179), community contribution by [@No-518](https://github.com/No-518)). `skills/skills-codex/` now mirrors all 67 mainline skills; replaces `mcp__codex__codex` reviewer path with Codex-native `spawn_agent` + `send_input`. New [`tools/install_aris_codex.sh`](tools/install_aris_codex.sh) + [`tools/smart_update_codex.sh`](tools/smart_update_codex.sh) handle project-local symlinks with manifest tracking. Anti-drift: `tests/test_codex_skill_mirror.py` + `tests/test_codex_install_update.py` (26 failure paths). Open discussion in [#184](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/184)
- **2026-04-24** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎨 **[`/paper-illustration-image2`](skills/paper-illustration-image2/SKILL.md)** — Codex-native image generation as Phase 2b illustration backend ([#166](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/166), community contribution by [@kbr19-thu](https://github.com/kbr19-thu) 清华). Uses ChatGPT Plus/Pro quota via local [Codex app-server MCP bridge](mcp-servers/codex-image2/) — **no `GEMINI_API_KEY` required**. Triggered by `/paper-writing — illustration: codex-image2`; default stays `figurespec` (**zero behavior change**). Async-only API, sandboxed writes to `figures/ai_generated/`, [integration-contract](skills/shared-references/integration-contract.md)-compliant helper. Marked **experimental** (Codex debug app-server is unstable upstream)
- **2026-04-21** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📚 **Research Wiki ingest actually works now** ([`research_wiki.py`](tools/research_wiki.py), [`/research-wiki`](skills/research-wiki/SKILL.md)). Fixes user-reported bug where `/research-wiki init` left `papers/` empty forever (`ingest` subcommand had no implementation; paper-reading skills had no wiki hook). New canonical `python3 tools/research_wiki.py ingest_paper` helper owns slugging / metadata fetch / dedup / page render; all 6 paper-reading skills wired to it. Manual backfill via `sync --arxiv-ids` or `sync --from-file`. Ships with [`integration-contract.md`](skills/shared-references/integration-contract.md) formalizing the six-component pattern every cross-skill integration must follow
- **2026-04-21** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛡️ **Assurance Gate: `— effort: beast | max` now really runs mandatory audits** ([`assurance-contract.md`](skills/shared-references/assurance-contract.md), [`tools/verify_paper_audits.sh`](tools/verify_paper_audits.sh)). Fixes silent-skip of `/proof-checker` / `/paper-claim-audit` / `/citation-audit` at high effort. New `assurance` axis (`draft` | `submission`) independent from `effort`: `lite` / `balanced` → `draft` (**zero behavior change**), `max` / `beast` → `submission`. At submission the 3 audits emit a JSON artifact with 6-state verdict; `paper-writing` Phase 6 runs the external verifier as source of truth (non-zero exit blocks Final Report). SHA256 input hashing catches stale audits. Escape hatch: `— effort: beast, assurance: draft`
<details>
<summary>Earlier updates (2026-03-12 — 2026-04-20, 44 entries)</summary>

- **2026-04-20** — 🩹 **Project install: flat layout + manifest tracking** — fixes a real bug where the previous nested install (`.claude/skills/aris/`) hid skills from Claude Code's slash-command discovery (CC only scans one directory level). Anyone who ran `install_aris.sh` before this date was silently affected. New `install_aris.sh` creates one symlink per skill at `.claude/skills/<name>`, writes a versioned manifest to `.aris/installed-skills.txt`, and is **re-runnable to reconcile** new/removed upstream skills. Defense-in-depth: 13 safety rules (no-symlinked-parents, exact-target revalidation, slug regex, atomic same-dir manifest rename, no-overwrite-real-files, mkdir-based portable lock, ADOPT for crash recovery, …). Granular `--adopt-existing` / `--replace-link` flags replace the all-or-nothing `--force`. Migration paths: `--from-old` for legacy nested symlink, `--migrate-copy keep-user|prefer-upstream` for legacy nested copy. `smart_update.sh --target-subdir .claude/skills/aris` is now deprecated with a redirect to `install_aris.sh`. Stale-file bug in `cp -r` overlay also fixed (now `rm -rf && cp -r` for safe-update path)
- **2026-04-19** — 🔗 **[`/overleaf-sync`](skills/overleaf-sync/SKILL.md)** — two-way bridge between local ARIS paper directory and an Overleaf project via the official **Overleaf Git bridge** (Premium). Lets collaborators keep editing in the Overleaf web UI while ARIS audit/edit pipelines (`/paper-claim-audit`, `/citation-audit`, `/auto-paper-improvement-loop`) keep running locally. Sub-commands: `setup` (one-time, user-driven so the agent never sees the token) / `pull` (with diff-protocol — flags half-sentences, typos, claim/cite changes that should re-trigger audits) / `push` (with confirmation gate before writing to shared Overleaf state) / `status` (3-way divergence check). **Token never touches the agent or any file** — primed once into macOS Keychain via the user's terminal, then auth-free for all subsequent agent operations
- **2026-04-19** — 📚 **[`/citation-audit`](skills/citation-audit/SKILL.md)** — fourth and final layer of the evidence-and-claim assurance stack (`experiment-audit` → `result-to-claim` → `paper-claim-audit` → `citation-audit`). Fresh cross-family reviewer (gpt-5.4 via Codex MCP) with web/DBLP/arXiv lookup verifies every `\cite{...}` along three independent axes: **existence** (paper resolves at claimed arXiv ID/DOI/venue), **metadata correctness** (authors/year/venue/title match canonical sources), and **context appropriateness** (the cited paper actually establishes the claim it supports — the most diagnostic check). Per-entry verdicts: KEEP / FIX / REPLACE / REMOVE. Auto-integrated into **Workflow 3 Phase 5.8** as the pre-submission bibliography gate. Empirical motivation: in a real submission run, several real papers were cited in contexts they did not actually support, and at least one entry shipped with `author = "Anonymous"` — none caught by metadata-only checks

- **2026-04-17** — 🔀 **`/experiment-queue` integrated into Workflow 1.5 + research-pipeline** — `experiment-bridge` Phase 4 Deploy now auto-routes by milestone job count: ≤5 jobs → `/run-experiment`, ≥10 jobs or phase dependencies → `/experiment-queue` (with OOM retry, stale-screen cleanup, wave-transition gating, crash-safe state). New `--- batch: queue` override for global force-queue mode. Large multi-seed sweeps from `EXPERIMENT_PLAN.md` (e.g., 36-cell `N × seed × n_train` grids) now get proper orchestration without manual queue invocation
- **2026-04-17** — 🔗 **[Project-local symlink install](tools/install_aris.sh)** (resolves [#118](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/118)) — new recommended default install. `bash tools/install_aris.sh` auto-detects platform (Claude Code / Codex CLI), creates `.claude/skills/aris` or `.agents/skills/aris` symlink to the ARIS repo, adds a managed `<!-- ARIS:BEGIN -->` block to `CLAUDE.md` / `AGENTS.md` telling the agent to use only project-local skills, and records install metadata in `.aris/skill-source.txt`. **Solves the skill collision problem** when ARIS is mixed with Superpowers / OpenHands / other community packs in the same global skill directory. PowerShell version (`install_aris.ps1`) ships with junction support for Windows. **`smart_update.sh --target-subdir`** flag added for `.agents/skills/aris` (Codex) project-copy installs; symlinked installs now correctly refuse `smart_update` and direct users to `git pull`. Global install remains supported for power users
- **2026-04-16** — 🎨 **[`/figure-spec`](skills/figure-spec/SKILL.md)** — deterministic JSON→SVG renderer packaged as a first-class skill. Preferred default for architecture/workflow/pipeline/audit-cascade figures in papers. Shape-aware edge clipping (rect/circle/ellipse/diamond), self-loops, curved edges, multi-line labels with CJK width estimation. Editable vector output, reproducible (same spec → same SVG), no external API. **Phase 2b in Workflow 3 restored**: `illustration: figurespec` (new default) / `gemini` / `mermaid` / `false` — 4-way illustration selector with complementary strengths
- **2026-04-16** — ⚙️ **[`/experiment-queue`](skills/experiment-queue/SKILL.md)** — SSH job queue for multi-seed/multi-config ML experiments. Designed from real 36-cell NeurIPS sweep pain points: OOM-aware retry with backoff, stale-screen cleanup, wave-transition race prevention, teacher→student phase dependencies, crash-safe scheduler that resumes from JSON state. Declarative grid specs expand automatically (e.g., `N × seed × n_train → 36 jobs`). Configurable `conda_hook` + `gpu_free_threshold_mib` for non-standard environments. Use for ≥10 jobs; `/run-experiment` stays for ad-hoc
- **2026-04-15** — 🛡️ **Paper Writing Pipeline Hardening** — 10 empirically-motivated patches from a real NeurIPS run. `REVIEWER_BIAS_GUARD=true`: every review round uses a fresh thread (codex-reply inflated 3→8/10). Reviewer Independence Protocol: no fix summaries to reviewer. Step 4.5 Restatement Regression Test: catches theorem drift across fix rounds. Step 5.5 Kill Argument Exercise: final-round adversarial attack/defense for theory papers. Location-aware overfull blocking. Theory Paper Consistency Pass in `/paper-write`. Enforced Bib Hygiene with DBLP/CrossRef validation. Phase 5.5 Mandatory Final Claim Audit as submission gate. **Review Tracing Protocol**: full prompt/response pairs saved to `.aris/traces/` for reviewer-independence audit ([`review-tracing.md`](skills/shared-references/review-tracing.md), [`save_trace.sh`](tools/save_trace.sh)). Inspired by community contribution from @李傲龍
- **2026-04-15** — 🎨 **[FigureSpec Renderer v2](tools/figure_renderer.py)** — deterministic JSON→SVG figure generation for academic papers. Shape-aware edge clipping (rect/circle/ellipse/diamond), self-loops, curved edges, multi-line labels with CJK width estimation, comprehensive validation (type checks, structure, palette). Went through 5 rounds of Codex review (3/10→7/10). All architecture and workflow diagrams in the ARIS tech report were generated with this pipeline. New `--- mode: vector` for `/paper-illustration` skill
- **2026-04-14** — 📋 **[`/paper-claim-audit`](skills/paper-claim-audit/SKILL.md)** — zero-context paper-to-evidence verification. Fresh reviewer with NO prior context compares every number in the paper against raw result files. Catches rounding inflation, best-seed cherry-pick, config mismatch, delta errors, scope overclaim. Auto-integrated into Workflow 3 (Phase 4.7). Completes the 3-layer audit chain: `/experiment-audit` (code) → `/result-to-claim` (science) → `/paper-claim-audit` (reporting). 👁️ **Visual PDF review** also added to improvement loop — reviewer now sees compiled PDF, not just LaTeX source. Inspired by [Hermes Agent](https://github.com/NousResearch/hermes-agent/tree/main/skills/research/research-paper-writing)
- **2026-04-13** — 🧿 **[GPT-5.4 Pro via Oracle](skills/shared-references/reviewer-routing.md)** — `— reviewer: oracle-pro` on any skill for the strongest available reviewer. API mode (fast) or browser mode (free). Supported on: `/research-review`, `/auto-review-loop`, `/experiment-audit`, `/proof-checker`, `/rebuttal`, `/idea-creator`, `/research-lit`. Default stays Codex xhigh. Not installed = zero impact. [Setup →](#-optional-gpt-54-pro-via-oracle)
- **2026-04-13** — 🔬 **[`/proof-checker`](skills/proof-checker/SKILL.md)** — rigorous mathematical proof verification via cross-model review. 20-category issue taxonomy, two-axis severity, side-condition checklists (DCT/MCT/Fubini/IFT/...), counterexample red team, proof-obligation ledger. Auto-integrated into Workflow 3: detects `\begin{theorem}` and runs before improvement loop. Complements `/proof-writer`
- **2026-04-10** — ⚡ **[Effort Levels](skills/shared-references/effort-contract.md)** — `— effort: lite | balanced | max | beast`. Controls work intensity across all skills: papers found, ideas generated, review rounds, writing depth. Codex reasoning stays `xhigh` always. `beast` = every knob to maximum for top-venue sprints. Default `balanced` = zero change for existing users. [Details →](#-effort-levels)
- **2026-04-10** — 🔎 **[DeepXiv integration](skills/deepxiv/SKILL.md)** — progressive paper retrieval via DeepXiv CLI. Opt-in: `— sources: deepxiv` or `— sources: all, deepxiv`. Staged reading: search → brief → head → section. `pip install deepxiv-sdk` to enable. Community contribution by [@DreamEnding](https://github.com/DreamEnding)
- **2026-04-10** — 🛡️ **[`/experiment-audit`](skills/experiment-audit/SKILL.md)** — cross-model experiment integrity verification. GPT-5.4 reads your eval scripts and results directly, checks for fake ground truth, self-normalized scores, phantom results, and scope inflation ([#131](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/131), [#57](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/57)). Advisory — warns loudly, never blocks. `/result-to-claim` auto-reads audit if present. New [experiment-integrity.md](skills/shared-references/experiment-integrity.md) shared reference. **The executor must never judge its own integrity.**
- **2026-04-10** — 🧠 **[`tools/smart_update.sh`](tools/smart_update.sh)** — intelligent skill updater. Compares local vs upstream, detects personal customizations (server paths, API keys), only updates safe skills. `bash tools/smart_update.sh --apply`
- **2026-04-10** — 🏆 **Community paper: [UAV-CC](community_papers/UAV-CC.pdf)** — first community paper with full PDF archived. UAV change captioning benchmark for IEEE TGRS by [@wxx827](https://github.com/wxx827). Stack: Claude Opus 4.6 + Codex 5.4 xhigh + Cursor. Papers now archived in `community_papers/`
- **2026-04-08** — 📚 **[`/research-wiki`](skills/research-wiki/SKILL.md)** — persistent research knowledge base inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Accumulates papers, ideas, experiments, and claims across the entire research lifecycle with typed relationships. Wiki-aware hooks in `/research-lit` (ingest papers), `/idea-creator` (read wiki + write ideas back), and `/result-to-claim` (update claim status + trigger re-ideation). Failed ideas become anti-repetition memory. **ARIS now learns from its mistakes.**
- **2026-04-05** — 🧬 **[`/meta-optimize`](skills/meta-optimize/SKILL.md)** — outer-loop harness optimization for ARIS. Passively logs skill invocations, tool calls, failures, and parameter overrides via [Claude Code hooks](templates/claude-hooks/meta_logging.json). Run `/meta-optimize` to analyze accumulated usage data and propose SKILL.md improvements — reviewer-gated, user-approved. Inspired by [Meta-Harness](https://arxiv.org/abs/2603.28052) (Lee et al., 2026). **ARIS now optimizes itself.**
- **2026-04-04** — 🔧 **Codex Plugin deep integration** — `/codex:rescue` now auto-invoked when experiments fail (Workflow 1.5) or LaTeX won't compile (Workflow 3). GPT independently diagnoses the bug before Claude retries — two AI debuggers are better than one. Optional: `codex exec` powers nightmare review, `/codex:rescue` powers auto-debug. [Setup →](#optional-codex-plugin-for-code-review)
- **2026-04-03** — ☁️ **[Modal serverless GPU](skills/serverless-modal/SKILL.md)** — no GPU? `gpu: modal` in CLAUDE.md, one command (`modal run launcher.py`), no SSH, no Docker, auto scale-to-zero. **$30/month free tier** — enough to try ARIS experiments without any hardware. `pip install modal && modal setup` and go. Community contribution by [@zeyuzhangzyz](https://github.com/zeyuzhangzyz)
- **2026-04-03** — 🎮 **Reviewer Difficulty Levels** — `medium` (default, unchanged), `hard` (reviewer memory + debate protocol), `nightmare` (GPT reads repo directly via `codex exec` — Claude can't hide anything). `— difficulty: nightmare` for maximum stress test before submission

- **2026-03-30** — 🔥 **Auto-debug & exhaust-before-surrender** — experiment-bridge auto-diagnoses failures (OOM, import, CUDA, NaN) and retries up to 3×. Inspired by [PUA](https://github.com/tanweai/pua)
- **2026-03-30** — ☁️ **[Vast.ai GPU rental](skills/vast-gpu/SKILL.md)** — `gpu: vast` auto-rents cheapest GPU. By [@YIHONG-JIN](https://github.com/YIHONG-JIN). 🔧 MiniMax M2.7 upgrade by [@octo-patch](https://github.com/octo-patch)
- **2026-03-27** — 📄 **IEEE venue support** (9 families). 🔎 **[Semantic Scholar](skills/semantic-scholar/SKILL.md)**. By [@ypd666](https://github.com/ypd666)
- **2026-03-26** — 📄 **Document-based input** — `RESEARCH_BRIEF.md` auto-detect
- **2026-03-24** — 📝 **[Workflow 4: `/rebuttal`](skills/rebuttal/SKILL.md)** — 7-phase pipeline, 3 safety gates
- **2026-03-23** — 🔧 `/training-check`, `/result-to-claim`, `/ablation-planner` integrated. 📦 `compact` mode. By [@JingxuanKang](https://github.com/JingxuanKang) & [@couragec](https://github.com/couragec)

- **2026-03-22** — 📋 **[Templates](templates/)** — input templates for every workflow. 📄 **7 venue templates** — CVPR, ACL, AAAI, ACM MM added. 🛡️ **Anti-hallucination fix** — Workflow 2 enforces DBLP → CrossRef → [VERIFY]. 🔗 **`base repo`** — clone a GitHub repo as base codebase (`— base repo: https://github.com/org/project`)
- **2026-03-22** — 🔍 **[Codex + Gemini review guide](docs/CODEX_GEMINI_REVIEW_GUIDE.md)** — Codex executes, Gemini reviews via local `gemini-review` MCP bridge. [CN](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md)
- **2026-03-20** — 🚀 **[Antigravity adaptation guide](docs/ANTIGRAVITY_ADAPTATION.md)** — use ARIS skills in [Google Antigravity](https://antigravity.google/) (agent-first IDE). Community contribution by [@PeppaPigw](https://github.com/PeppaPigw)
- **2026-03-20** — 🖥️ **[Trae adaptation guide](docs/TRAE_ARIS_RUNBOOK_EN.md)** — use ARIS skills in [Trae](https://www.trae.ai/) (ByteDance AI IDE). Community contribution by [@Prometheus-cotigo](https://github.com/Prometheus-cotigo). 🔢 **[`formula-derivation`](skills/formula-derivation/SKILL.md)** — Community contribution by [@Falling-Flower](https://github.com/Falling-Flower)
- **2026-03-19** — 🖼️ **[`paper-poster`](skills/paper-poster/SKILL.md)** — Conference poster. Community contribution by [@dengzhe-hou](https://github.com/dengzhe-hou)
- **2026-03-19** — 🔗 **Workflow 1.5 upgraded** — `/experiment-bridge` GPT-5.4 code review. 📊 **W&B fix**
- **2026-03-18** — 🎤 `paper-slides` + 🔁 Codex+Claude bridge + 🖱️ Cursor guide + 🤖 Codex CLI skills + 📝 `grant-proposal` + 🎨 `paper-illustration` (Gemini) + 📊 CitationClaw
- **2026-03-17** — 🔧 Git code sync + 🆓 ModelScope guide + parameter pass-through

- **2026-03-16** — 🔬 **[`research-refine`](skills/research-refine/SKILL.md)** + [`experiment-plan`](skills/experiment-plan/SKILL.md) — turn vague ideas into problem-anchored proposals with claim-driven experiment roadmaps. Now integrated into Workflow 1 (`/idea-discovery`). Community contribution by [@zjYao36](https://github.com/zjYao36)
- **2026-03-16** — 🇨🇳 **[Alibaba Coding Plan guide](docs/ALI_CODING_PLAN_GUIDE.md)** — one API key, 4 models (Kimi-K2.5 + Qwen3.5+ + GLM-5 + MiniMax-M2.7), dual-endpoint setup. Community contribution by [@tianhao909](https://github.com/tianhao909)
- **2026-03-15** — 🔀 **Bring your own model!** [Any OpenAI-compatible API](#-alternative-model-combinations) now works as reviewer via [`llm-chat`](mcp-servers/llm-chat/) MCP server. GLM, MiniMax, Kimi, LongCat, DeepSeek all tested — **zero Claude or OpenAI API needed**
- **2026-03-15** — 🐾 **[OpenClaw adaptation guide](docs/OPENCLAW_ADAPTATION.md)** — use ARIS research workflows in [OpenClaw](https://github.com/All-Hands-AI/OpenHands) without Claude Code slash skills
- **2026-03-15** — 📐 **[`proof-writer`](skills/proof-writer/SKILL.md)** — community skill for rigorous theorem proof drafting. 📚 **Anti-hallucination citations** — `/paper-write` now fetches real BibTeX from [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) instead of LLM-generated entries — on by default, zero install
- **2026-03-14** — 📱 [Feishu/Lark integration](#-feishulark-integration-optional): three modes (off/push/interactive), mobile notifications for experiments, reviews, and checkpoints
- **2026-03-13** — 🛑 Human-in-the-loop: configurable `AUTO_PROCEED` checkpoints across all workflows. Full autopilot or step-by-step approval
- **2026-03-12** — 🔗 [Zotero](#-zotero-integration-optional) + [Obsidian](#-obsidian-integration-optional) + local PDFs + arXiv/Scholar: multi-source literature search with cross-model novelty verification
- **2026-03-12** — 🚀 Three end-to-end workflows complete: one prompt → top-venue-style paper. `/research-pipeline` chains idea discovery → auto review → paper writing autonomously
- **2026-03-12** — 📝 `/paper-writing` workflow: narrative report → structured outline → figures → LaTeX → compiled PDF → 2-round auto-improvement (4/10 → 8.5/10)

</details>

## 🚀 Quick Start

```bash
# 1. Install skills
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
mkdir -p ~/.claude/skills/    # create if it doesn't exist (new Claude Code versions)
cp -r Auto-claude-code-research-in-sleep/skills/* ~/.claude/skills/

# 1b. Update skills (when upstream has new versions)
cd Auto-claude-code-research-in-sleep && git pull
bash tools/smart_update.sh          # dry-run: shows what's new/changed/safe
bash tools/smart_update.sh --apply  # apply: adds new + updates safe ones

# Optional Codex mirror managed project install
bash tools/install_aris_codex.sh ~/your-codex-project

# Managed Codex project update
cd Auto-claude-code-research-in-sleep && git pull
bash tools/install_aris_codex.sh ~/your-codex-project --reconcile

# Copied Codex installs only (not for projects installed by install_aris_codex.sh)
bash tools/smart_update_codex.sh --local ~/.codex/skills
bash tools/smart_update_codex.sh --local ~/.codex/skills --apply

# 2. Set up Codex MCP (for review skills)
npm install -g @openai/codex
codex setup                    # set model to gpt-5.4 when prompted
claude mcp add codex -s user -- codex mcp-server

# 3. Use in Claude Code
claude
> /idea-discovery "your research direction"  # Workflow 1 — be specific! not "NLP" but "factorized gap in discrete diffusion LMs"
> /experiment-bridge                         # Workflow 1.5 — have a plan? implement + deploy + collect results
> /auto-review-loop "your paper topic or scope"  # Workflow 2: review → fix → re-review overnight
> /paper-writing "NARRATIVE_REPORT.md"       # Workflow 3: narrative → polished PDF
> /rebuttal "paper/ + reviews" — venue: ICML    # Workflow 4: parse reviews → draft rebuttal → follow-up
> /research-pipeline "your research direction"  # Full pipeline: Workflow 1 → 1.5 → 2 → 3 end-to-end
> /research-wiki init                           # 📚 Enable persistent research memory (one-time)
> /meta-optimize                                # Meta: analyze usage logs → propose skill improvements
```

> 📚 **Research Wiki (optional):** Give ARIS persistent memory across sessions. Papers, ideas, failed experiments — nothing is forgotten:
> ```bash
> # In Claude Code:
> > /research-wiki init                         # creates research-wiki/ in your project
> # That's it. From now on, /research-lit auto-ingests papers, /idea-creator reads
> # the wiki before brainstorming (and writes ideas back), /result-to-claim updates
> # claim status. Failed ideas become anti-repetition memory for future ideation.
> ```
> See [Research Wiki](#-research-wiki--persistent-research-memory) for the full guide.

> 🧬 **Meta-optimization (optional):** Run these in your **normal terminal** (not inside Claude Code) to enable passive usage logging:
> ```bash
> # One-time setup in your project directory
> mkdir -p .claude .aris/meta tools/meta_opt
> cp Auto-claude-code-research-in-sleep/templates/claude-hooks/meta_logging.json .claude/settings.json
> cp Auto-claude-code-research-in-sleep/tools/meta_opt/*.sh tools/meta_opt/
> chmod +x tools/meta_opt/*.sh
> # Then start Claude Code — hooks are active immediately
> claude
> ```
> Events are logged to **both** project-level (`.aris/meta/events.jsonl`) and global (`~/.aris/meta/events.jsonl`) logs. After 5+ workflow runs, run `/meta-optimize` to see data-driven improvement proposals. Use `/meta-optimize --global` to analyze trends across all your projects. See [Workflow M](#workflow-m-meta-optimize--aris-optimizes-itself) for details.

> 📝 **Templates available!** See [`templates/`](templates/) for ready-to-use input templates for every workflow — [research brief](templates/RESEARCH_BRIEF_TEMPLATE.md) (Workflow 1), [experiment plan](templates/EXPERIMENT_PLAN_TEMPLATE.md) (Workflow 1.5), [narrative report](templates/NARRATIVE_REPORT_TEMPLATE.md) (Workflow 3), [paper plan](templates/PAPER_PLAN_TEMPLATE.md) (Workflow 3).
>
> 🔎 **Optional: DeepXiv progressive retrieval**
> ```bash
> pip install deepxiv-sdk
> ```
> Then use [`/deepxiv`](skills/deepxiv/SKILL.md) directly or opt into it from `/research-lit` with `— sources: deepxiv` or `— sources: all, deepxiv`.
>
> 🔎 **Optional: Exa AI-powered web search**
> ```bash
> pip install exa-py
> export EXA_API_KEY=your-key-here
> ```
> Then use [`/exa-search`](skills/exa-search/SKILL.md) directly or opt into it from `/research-lit` with `— sources: exa` or `— sources: all, exa`. Covers blogs, docs, news, and research papers with built-in content extraction.
>
> 🗑️ **Uninstall:** To remove ARIS skills without affecting your own personal skills:
> ```bash
> cd Auto-claude-code-research-in-sleep && ls skills/ | xargs -I{} rm -rf ~/.claude/skills/{}
> ```

> **Tip:** All pipeline behaviors are configurable via inline overrides — append `— key: value` to any command:
>
> | Parameter | Default | What it does |
> |-----------|---------|-------------|
> | `AUTO_PROCEED` | `true` | Auto-continue at idea selection gate. Set `false` to manually pick which idea to pursue before committing GPU time |
> | `human checkpoint` | `false` | Pause after each review round so you can read the score, give custom modification instructions, skip specific fixes, or stop early |
> | `sources` | `all` | Which literature sources to search: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, or `all`. Note: `semantic-scholar`, `deepxiv`, and `exa` must be explicitly listed — not included in `all` |
> | `arxiv download` | `false` | Download top relevant arXiv PDFs during literature survey. When `false`, only fetches metadata (title, abstract, authors) |
> | `DBLP_BIBTEX` | `true` | Fetch real BibTeX from [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) instead of LLM-generated entries. Eliminates hallucinated citations. Zero install |
> | `code review` | `true` | GPT-5.4 xhigh reviews experiment code before GPU deployment. Set `false` to skip |
> | `wandb` | `false` | Auto-add W&B logging to experiment scripts. Set `true` + configure `wandb_project` in CLAUDE.md. `/monitor-experiment` pulls training curves from W&B |
> | `illustration` | `gemini` | AI illustration in Workflow 3: `gemini` (default, needs `GEMINI_API_KEY`), `mermaid` (free), or `false` (skip) |
> | `venue` | `ICLR` | Target venue: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`. Determines LaTeX style file and page limit |
> | `base repo` | `false` | GitHub repo URL to clone as base codebase (e.g., `— base repo: https://github.com/org/project`). No code? Build on top of an open-source project |
> | `gpu` | `local` | GPU target: `local` (default), `remote` (SSH server), or `vast` (rent on-demand from [Vast.ai](https://vast.ai) — auto-provision, auto-destroy) |
> | `compact` | `false` | Generate compact summary files (`IDEA_CANDIDATES.md`, `findings.md`, `EXPERIMENT_LOG.md`) for short-context models and session recovery |
> | `ref paper` | `false` | Reference paper to build on (PDF path or arXiv URL). Summarized first, then ideas extend/improve it. Combine with `base repo` for paper+code workflows |
> | `effort` | `balanced` | Work intensity: `lite` (0.4x tokens), `balanced` (default), `max` (2.5x), `beast` (5-8x). Controls breadth/depth/iterations. Codex reasoning always `xhigh`. See [Effort Levels](#-effort-levels) |
> | `reviewer` | `codex` | Reviewer backend: `codex` (GPT-5.4 xhigh, default), `oracle-pro` (GPT-5.4 Pro via [Oracle](https://github.com/steipete/oracle) — strongest reasoning). See [Setup →](#-optional-gpt-54-pro-via-oracle) |
> | `difficulty` | `medium` | Reviewer adversarial level: `medium` (default), `hard` (+ memory + debate), `nightmare` (+ GPT reads repo via `codex exec`) |
>
> ```
> /research-pipeline "your topic" — AUTO_PROCEED: false                          # pause at idea selection gate
> /research-pipeline "your topic" — human checkpoint: true                       # pause after each review round to give feedback
> /research-pipeline "your topic" — sources: zotero, web                         # only search Zotero + web (skip local PDFs)
> /research-pipeline "your topic" — sources: all, deepxiv                        # default sources plus DeepXiv progressive retrieval
> /research-pipeline "your topic" — sources: all, exa                            # default sources plus Exa AI-powered web search
> /research-pipeline "your topic" — arxiv download: true                         # download top arXiv PDFs during literature survey
> /research-pipeline "your topic" — difficulty: nightmare                        # maximum adversarial review before submission
> /research-pipeline "your topic" — effort: beast                               # all knobs to maximum — top-venue sprint
> /research-pipeline "your topic" — effort: beast, reviewer: oracle-pro         # beast + GPT-5.4 Pro reviewer — ultimate mode
> /research-pipeline "your topic" — effort: lite                                # quick exploration, save tokens
> /research-pipeline "your topic" — effort: max, review_rounds: 3               # max effort but cap review at 3 rounds
> /research-pipeline "your topic" — AUTO_PROCEED: false, human checkpoint: true  # combine options
> /proof-checker "paper/" — reviewer: oracle-pro                                # Pro-level proof verification
> ```

> **Important:** Codex MCP uses the model from `~/.codex/config.toml`, not from skill files. Make sure it says `model = "gpt-5.4"` (recommended). Other options: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. Run `codex setup` or edit the file directly.

> **Want Codex to execute but Claude Code to review?** See [`docs/CODEX_CLAUDE_REVIEW_GUIDE.md`](docs/CODEX_CLAUDE_REVIEW_GUIDE.md). That path installs the base `skills/skills-codex/*`, then overlays `skills/skills-codex-claude-review/*`, and routes review-heavy skills through the local `claude-review` MCP bridge.

> **Want Codex to execute but Gemini to review locally?** See [`docs/CODEX_GEMINI_REVIEW_GUIDE.md`](docs/CODEX_GEMINI_REVIEW_GUIDE.md) and [CN](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md). That path installs the base `skills/skills-codex/*`, then overlays `skills/skills-codex-gemini-review/*`, and routes the reviewer-aware predefined skills through the local `gemini-review` MCP bridge using direct Gemini API by default.

> **Want the Codex mirror install chain?** Use `tools/install_aris_codex.sh` for managed project installs and `tools/smart_update_codex.sh` for copied Codex installs. The Claude scripts remain the mainline entry points for Claude projects.

See [full setup guide](#%EF%B8%8F-setup) for details and [alternative model combinations](#-alternative-model-combinations) if you don't have Claude/OpenAI API.

> 🧠 **Update skills later?** Smart update analyzes what's safe:
> ```bash
> cd Auto-claude-code-research-in-sleep
> git pull
> bash tools/smart_update.sh          # dry-run: shows what's new/changed/safe
> bash tools/smart_update.sh --apply  # apply: adds new + updates safe ones
> ```
> Compares local skills with upstream, detects personal customizations (server paths, API keys, etc.), and only updates skills that are safe to replace. Skills with your personal info are flagged for manual review.

## ✨ Features

- 📊 **31 composable skills** — mix and match, or chain into full pipelines (`/idea-discovery`, `/auto-review-loop`, `/paper-writing`, `/research-pipeline`)
- 🔍 **Literature & novelty** — multi-source paper search (**[Zotero](#-zotero-integration-optional)** + **[Obsidian](#-obsidian-integration-optional)** + **local PDFs** + arXiv/Scholar) + cross-model novelty verification
- 💡 **Idea discovery** — literature survey → brainstorm 8-12 ideas → novelty check → GPU pilot experiments → ranked report
- 🔄 **Auto review loop** — 4-round autonomous review, 5/10 → 7.5/10 overnight with 20+ GPU experiments
- 📝 **Paper writing** — narrative → outline → figures → LaTeX → PDF → auto-review (4/10 → 8.5/10), one command. Anti-hallucination citations via [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org)
- 🤖 **Cross-model collaboration** — Claude Code executes, GPT-5.4 xhigh reviews. Adversarial, not self-play. Optional upgrade: `— reviewer: oracle-pro` for **GPT-5.4 Pro** (strongest reasoning) via [Oracle](https://github.com/steipete/oracle)
- 📝 **Peer review** — review others' papers as a conference reviewer, with structured scoring and meta-review
- 🖥️ **Review-driven experiments** — when GPT-5.4 says "run an ablation", Claude Code automatically writes the script, rsyncs to your GPU server, launches in screen, collects results, and folds them back into the paper. Just configure your server in `CLAUDE.md` ([setup guide](#%EF%B8%8F-gpu-server-setup-for-auto-experiments)). **No GPU?** Use `gpu: vast` to rent one from [Vast.ai](https://vast.ai) on demand
- 🔀 **Flexible models** — default Claude × GPT-5.4, also supports [GLM, MiniMax, Kimi, LongCat, DeepSeek, etc.](#-alternative-model-combinations) — no Claude or OpenAI API required
- 🛑 **Human-in-the-loop** — configurable checkpoints at key decisions. `AUTO_PROCEED=true` for full autopilot, `false` to approve each step
- 📱 **[Feishu/Lark notifications](#-feishulark-integration-optional)** — three modes: **off (default, strongly recommended for most users)**, push-only (webhook, mobile alerts), interactive (approve/reject from Feishu). Zero impact when unconfigured

  <details>
  <summary>Preview: Push cards (group) &amp; Interactive chat (private)</summary>

  **Push Only** — group chat cards (experiment done, checkpoint, error, pipeline complete):

  <img src="assets/feishu_push.png" width="700" />

  **Interactive** — private chat with Claude Code (approve/reject, custom instructions):

  <img src="assets/feishu_interactive.jpg" width="700" />

  </details>

- 📚 **[Research Wiki](#-research-wiki--persistent-research-memory)** — persistent knowledge base that accumulates papers, ideas, experiments, and claims across the research lifecycle. Failed ideas become anti-repetition memory. ARIS learns from its mistakes and gets smarter with every run. Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
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

## 🏆 Community Showcase — Papers Built with ARIS

Real projects where the ARIS pipeline was used end-to-end. **If you've used ARIS to complete a paper, we'd love to feature it here — open an issue or PR!**

| Paper | Rating | Venue | Built by | Notes |
|-------|:------:|-------|----------|-------|
| CS Paper | **8/10** — "Top 50% of accepted papers, clear accept" | CS Conference | [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) | Full ARIS pipeline: idea → experiments → auto-review → paper writing. Reviewer: "empirical findings are stark, well-supported, and expose a fundamental flaw" |
| AAAI 2026 Paper | **7/10** — "Good paper, accept" | AAAI 2026 Main Technical | [@xinbo820-web](https://github.com/xinbo820-web) | Pure **Codex CLI** (ARIS-Codex skills). Accepted at AAAI 2026 |
| [UAV-CC](community_papers/UAV-CC.pdf) | Under review | IEEE TGRS | [@wxx827](https://github.com/wxx827) | UAV change captioning benchmark. Claude Opus 4.6 (executor) + Codex GPT-5.4 xhigh (reviewer) + Cursor Opus 4.6 (assist). [PDF →](community_papers/UAV-CC.pdf) |

<details><summary>Reviewer screenshots</summary>
<br>
<img src="assets/community_showcase_8_10.png" width="700" alt="8/10 — CS Paper" />
<img src="assets/community_showcase_7_10_codex.png" width="700" alt="7/10 — AAAI 2026, Codex CLI" />
</details>

> 🎉 *Papers built entirely with ARIS — from idea to acceptance. Know more? Let us know!*

## 🧩 Awesome Community Skills & Extensions

Domain-specific skills and external projects contributed by the community. PRs welcome — just add a `skills/your-skill/SKILL.md` and open a PR!

> 💡 **How to use:** Community skills are not auto-wired into core workflows. To use one, ask your executor (Claude Code / OpenClaw / etc.) to read the skill's `SKILL.md`, then plug it into the appropriate workflow stage based on the description below.

🎉 **Community Skills (13):** [research-refine](skills/research-refine/SKILL.md) · [experiment-plan](skills/experiment-plan/SKILL.md) · [grant-proposal](skills/grant-proposal/SKILL.md) · [paper-poster](skills/paper-poster/SKILL.md) · [paper-slides](skills/paper-slides/SKILL.md) · [mermaid-diagram](skills/mermaid-diagram/SKILL.md) · [proof-writer](skills/proof-writer/SKILL.md) · [comm-lit-review](skills/comm-lit-review/SKILL.md) · [dse-loop](skills/dse-loop/SKILL.md) · [idea-discovery-robot](skills/idea-discovery-robot/SKILL.md) · [formula-derivation](skills/formula-derivation/SKILL.md) · [paper-illustration](skills/paper-illustration/SKILL.md) · [writing-systems-papers](skills/writing-systems-papers/SKILL.md)

🌐 **External Projects & Docs (12):** [rosetta](https://github.com/SyntaxSmith/rosetta) · [open-source-hardening-skills](https://github.com/zeyuzhangzyz/open-source-hardening-skills) · [CitationClaw](https://github.com/VisionXLab/CitationClaw) · [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) · [paper-to-course](https://github.com/KaguraTart/paper-to-course) · [Antigravity Adaptation Guide](docs/ANTIGRAVITY_ADAPTATION.md) · [OpenClaw Adaptation Guide](docs/OPENCLAW_ADAPTATION.md) · [Cursor Adaptation Guide](docs/CURSOR_ADAPTATION.md) · [Codex+Claude Review Bridge](docs/CODEX_CLAUDE_REVIEW_GUIDE.md) · [Trae Adaptation Guide](docs/TRAE_ARIS_RUNBOOK_EN.md) · [paper-illustration](skills/paper-illustration/SKILL.md) · [MiniMax-AI/cli](https://github.com/MiniMax-AI/cli)

> 🙌 Thanks to every contributor! We fold the tables below to keep the README readable — but every skill and project here is equally valued. PRs always welcome!

<details>
<summary><b>🎉 Community Skills (13)</b> — click to expand</summary>

| Name | Domain | Description | Codex MCP? |
|------|--------|-------------|-----------|
| 🔬 [`research-refine`](skills/research-refine/SKILL.md) | General | Turn a vague idea into a problem-anchored, implementation-oriented method proposal. Best inserted between `/idea-discovery` and `/auto-review-loop` | Yes |
| 🧪 [`experiment-plan`](skills/experiment-plan/SKILL.md) | General | Turn a refined proposal into a claim-driven experiment roadmap with ablations, budgets, and run order | No |
| 🧭 [`research-refine-pipeline`](skills/research-refine-pipeline/SKILL.md) | General | One-shot chain: `/research-refine` → `/experiment-plan` for method refinement plus experiment planning | Yes |
| 📝 [`grant-proposal`](skills/grant-proposal/SKILL.md) | General | Grant proposal drafting (KAKENHI/NSF/NSFC/ERC/DFG/SNSF/ARC/NWO). Chains `/research-lit` → `/novelty-check` → `/research-review` → `/paper-illustration` | Yes |
| 🎤 [`paper-slides`](skills/paper-slides/SKILL.md) | General | Conference talk slides (beamer → PDF + PPTX) with speaker notes, full talk script + Q&A prep. Auto slide count from talk type | Yes |
| 🖼️ [`paper-poster`](skills/paper-poster/SKILL.md) | General | Conference poster (article + tcbposter → A0/A1 PDF + component PPTX + SVG). Venue-specific colors, visual review loop, Codex MCP review | Yes |
| 📐 [`proof-writer`](skills/proof-writer/SKILL.md) | ML Theory | Rigorous theorem/lemma proof drafting — feasibility triage, dependency maps, honest blockage reports | No |
| 📡 [`comm-lit-review`](skills/comm-lit-review/SKILL.md) | Communications / Wireless | Domain-specific literature review — IEEE/ACM/ScienceDirect priority, venue tiering, PHY/MAC/transport/NTN taxonomy | No |
| 🏗️ [`dse-loop`](skills/dse-loop/SKILL.md) | Architecture / EDA | Autonomous design space exploration — iteratively run, analyze, and tune parameters (gem5, Yosys, etc.) | No |
| 🤖 [`idea-discovery-robot`](skills/idea-discovery-robot/SKILL.md) | Robotics / Embodied AI | Workflow 1 adaptation — grounds idea discovery in embodiment, benchmark, sim2real path, and real-robot safety constraints | Yes |
| 📐 [`mermaid-diagram`](skills/mermaid-diagram/SKILL.md) | General | Mermaid diagrams (20+ types) — free alternative to `paper-illustration`, no API key needed | No |
| 🔢 [`formula-derivation`](skills/formula-derivation/SKILL.md) | General | Research formula development — derivation, verification, and LaTeX formatting | No |
| 🖥️ [`writing-systems-papers`](skills/writing-systems-papers/SKILL.md) | Systems | Paragraph-level blueprint for 10-12 page systems papers (OSDI/SOSP/ASPLOS/NSDI/EuroSys) — page allocation, writing patterns, self-check | Yes |

</details>

<details>
<summary><b>🌐 External Projects & Docs (12)</b> — click to expand</summary>

| Name | Domain | Description |
|------|--------|-------------|
| 🪨 [rosetta](https://github.com/SyntaxSmith/rosetta) | Pro-tier ChatGPT MCP | Programmatic access to **ChatGPT Pro / `gpt-5.5-pro` / DeepResearch** from Node, via Chrome CDP Fetch interception + WebSocket second-leg streaming. Ships an MCP server for Claude Code / Codex / Cline — alternative implementation path to Oracle MCP for `— reviewer: oracle-pro` style high-tier review. Supports multi-turn, parallel concurrency, live token deltas, 15-min idle-timeout watchdog (long Pro thinks survive). MIT, by [@SyntaxSmith](https://github.com/SyntaxSmith) |
| 🛡️ [open-source-hardening-skills](https://github.com/zeyuzhangzyz/open-source-hardening-skills) | DevOps / OSS | 10-skill pipeline to harden research code into production-ready open-source projects — audit, refactor, test, CI, docs, review |
| 📊 [CitationClaw](https://github.com/VisionXLab/CitationClaw) | General | Citation impact analysis — input paper title → citation crawling, scholar identification, tiered analysis, HTML dashboard |
| 🚀 [Antigravity Adaptation Guide](docs/ANTIGRAVITY_ADAPTATION.md) | General | Use ARIS skills in [Google Antigravity](https://antigravity.google/) — native SKILL.md support, dual model (Claude Opus 4.6 / Gemini 3.1 Pro), MCP setup, EN + [CN](docs/ANTIGRAVITY_ADAPTATION_CN.md) guides |
| 🐾 [OpenClaw Adaptation Guide](docs/OPENCLAW_ADAPTATION.md) | General | Use ARIS workflow methodology in [OpenClaw](https://github.com/All-Hands-AI/OpenHands) — skill-to-stage mapping, file-based orchestration, no Claude Code CLI needed |
| 🖱️ [Cursor Adaptation Guide](docs/CURSOR_ADAPTATION.md) | General | Use ARIS skills in [Cursor](https://www.cursor.com/) — `@`-reference skills, MCP setup, workflow mapping, state file recovery across sessions |
| 🖥️ [Trae Adaptation Guide](docs/TRAE_ARIS_RUNBOOK_EN.md) | General | Use ARIS skills in [Trae](https://www.trae.ai/) (ByteDance AI IDE) — EN + CN guides |
| 🎨 [`paper-illustration`](skills/paper-illustration/SKILL.md) | General | AI-generated architecture diagrams via Gemini. Built on [PaperBanana](https://github.com/dwzhu-pku/PaperBanana). Integrated into Workflow 3 |
| 🤖 [`skills-codex`](skills/skills-codex/) | General | Codex CLI sync pack for the main research skills, now including `training-check`, `result-to-claim`, `ablation-planner`, `rebuttal`, plus the `shared-references/` support directory |
| 🎛️ [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) | General | Automatic hyperparameter tuning — AI agent reads project, plans strategy, runs experiments, analyzes TensorBoard, learns from results. Hydra-based |
| 🔁 [Codex+Claude Review Bridge](docs/CODEX_CLAUDE_REVIEW_GUIDE.md) | General | Codex executes + Claude reviews via local `claude-review` MCP bridge with async polling |
| 📚 [paper-to-course](https://github.com/KaguraTart/paper-to-course) | Education | Convert research papers (PDF/LaTeX) into interactive six-module HTML courses with formula breakdowns, literature timelines, quizzes, and glossary tooltips — single bundled file, no server needed |
| 🤖 [MiniMax-AI/cli](https://github.com/MiniMax-AI/cli) | General | Official MiniMax CLI — text, image, video, speech, and music generation + web search. `skill/SKILL.md` follows the agentskills.io standard. Drop-in companion for the Alt B (MiniMax reviewer) setup |

</details>

## 🔄 Workflows

These skills compose into a full research lifecycle. The four workflows can be used independently or chained together:

- **Exploring a new area (e.g., writing a survey)?** Start with Workflow 1 → `/idea-discovery`
- **Have a plan, need to implement and run?** Workflow 1.5 → `/experiment-bridge`
- **Already have results, need iterative improvement?** Workflow 2 → `/auto-review-loop`
- **Ready to write the paper?** Workflow 3 → `/paper-writing` (or step by step: `/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile` → `/auto-paper-improvement-loop`)
- **Got reviews back? Need to rebuttal?** Workflow 4 → `/rebuttal` — parse reviews, draft safe rebuttal, follow-up rounds
- **Full pipeline?** Workflow 1 → 1.5 → 2 → 3 → submit → 4 → `/research-pipeline` + `/rebuttal` — from idea to acceptance
- **Want ARIS to remember and learn?** 📚 `/research-wiki init` — persistent memory across sessions. Papers, ideas, failed experiments compound over time
- **Want ARIS to improve itself?** Workflow M → `/meta-optimize` — analyze usage logs, propose skill improvements, reviewer-gated

> ⚠️ **Important:** These tools accelerate research, but they don't replace your own critical thinking. Always review generated ideas with your domain expertise, question the assumptions, and make the final call yourself. The best research comes from human insight + AI execution, not full autopilot.

### Full Pipeline 🚀

```
/research-lit → /idea-creator → /novelty-check → /research-refine → /experiment-bridge → /auto-review-loop → /paper-writing → submit → /rebuttal → accept! 🎉
  (survey)      (brainstorm)    (verify novel)   (refine method)   (implement+deploy)  (review & fix)      (write paper)   (send)   (reply to reviewers)
  ├────────────── Workflow 1: Idea Discovery ──────────────┤ ├ Workflow 1.5 ─┤ ├── Workflow 2 ──┤ ├── Workflow 3 ──┤         ├── Workflow 4 ──┤

                                     📚 research-wiki (persistent memory — papers, ideas, experiments, claims)
                                        ↕ reads before ideation, writes after every stage, failed ideas = anti-repetition memory

                                              /meta-optimize (Workflow M — runs independently, improves ARIS itself)
                                                 ↑ reads .aris/meta/events.jsonl (accumulated from all runs above)
```

📝 **Blog post:** [梦中科研全流程开源](http://xhslink.com/o/2iV33fYoc7Q)

### Workflow 1: Idea Discovery & Method Refinement 🔍

> **"What's the state of the art? Where are the gaps? How do we solve it?"**

Don't have a concrete idea yet? Just give a research direction — `/idea-discovery` handles the rest:

1. 📚 **Survey** the landscape (recent papers, open problems, recurring limitations)
2. 🧠 **Brainstorm** 8-12 concrete ideas via GPT-5.4 xhigh
3. 🔍 **Filter** by feasibility, compute cost, and quick novelty search
4. 🛡️ **Validate** top ideas with deep novelty check + devil's advocate review
5. 🧪 **Pilot** top 2-3 ideas in parallel on different GPUs (30 min - 2 hr each)
6. 🏆 **Rank** by empirical signal — ideas with positive pilot results rise to the top
7. 🔬 **Refine** the top idea into a problem-anchored proposal via iterative GPT-5.4 review
8. 🧪 **Plan** claim-driven experiments with ablations, budgets, and run order

The output is a ranked `IDEA_REPORT.md` plus a refined proposal (`refine-logs/FINAL_PROPOSAL.md`) and experiment plan (`refine-logs/EXPERIMENT_PLAN.md`) for the top idea. Dead-end ideas are documented too, saving future exploration.

```
┌─────────────────────────────────────────────────────────────────┐
│              Idea Discovery & Method Refinement                  │
│                                                                  │
│   /research-lit    /idea-creator    /novelty-check               │
│   (find papers)    (brainstorm)     (verify novelty)             │
│         │               │                │                       │
│         ▼               ▼                ▼                       │
│   ┌──────────┐    ┌──────────┐     ┌──────────┐                │
│   │ Scan     │───▶│ Generate │────▶│ Check if │                │
│   │ local    │    │ 8-12     │     │ idea is  │                │
│   │ papers + │    │ ideas    │     │ novel    │                │
│   │ search   │    │ + rank   │     │          │                │
│   └──────────┘    └──────────┘     └──────────┘                │
│                         │                │                       │
│                         ▼                ▼                       │
│                   ┌──────────┐     ┌──────────┐                │
│                   │ Filter   │────▶│ External │                │
│                   │ by cost, │     │ LLM      │                │
│                   │ novelty  │     │ evaluates│                │
│                   └──────────┘     └──────────┘                │
│                                          │                       │
│                   /research-refine       ▼                       │
│                   (refine method)   ┌──────────┐                │
│                         │          │ Freeze   │                │
│                         ▼          │ problem  │                │
│                   ┌──────────┐     │ anchor + │                │
│                   │ Iterate  │◀───▶│ refine   │                │
│                   │ until    │     │ method   │                │
│                   │ score≥9  │     └──────────┘                │
│                   └──────────┘          │                       │
│                         │               ▼                       │
│                   /experiment-plan  ┌──────────┐                │
│                         │          │ Claim-   │                │
│                         ▼          │ driven   │                │
│                   ┌──────────┐     │ experiment│               │
│                   │ Plan     │────▶│ roadmap  │                │
│                   │ runs     │     └──────────┘                │
│                   └──────────┘                                  │
│                                                                  │
│   Typical flow:                                                  │
│   1. /research-lit "discrete diffusion models"                   │
│   2. /idea-creator "DLLMs post training"                         │
│   3. Review ranked ideas, pick top 2-3                           │
│   4. /novelty-check "top idea" (deep verification)               │
│   5. /research-review "top idea" (critical feedback)             │
│   6. /research-refine "top idea" (problem anchor + method)       │
│   7. /experiment-plan (claim-driven roadmap)                     │
│   8. /run-experiment → /auto-review-loop                         │
└─────────────────────────────────────────────────────────────────┘
```

**Skills involved:** `research-lit` + `idea-creator` + `novelty-check` + `research-review` + `research-refine-pipeline`

> 💡 **One-command shortcut:** `/idea-discovery "your research direction"` runs this entire workflow automatically.

> 🔄 **Human-in-the-loop:** Each phase presents results and waits for your feedback. Not happy? Tell it what's missing — it refines the prompt and regenerates. Trust the defaults? It auto-proceeds with the top-ranked option. You decide how hands-on to be.

> ⚙️ Pilot experiment budgets (max hours, timeout, GPU budget) are configurable — see [Customization](#%EF%B8%8F-customization).

📝 **Blog post:** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

### Workflow 1.5: Experiment Bridge 🔗

> **"I have a plan. Now implement it, deploy it, and get me initial results."**

Already have an experiment plan (from Workflow 1 or your own)? `/experiment-bridge` turns it into running code:

1. 📋 **Parse** the experiment plan (`refine-logs/EXPERIMENT_PLAN.md`)
2. 💻 **Implement** experiment scripts (reuse existing code, add proper argparse/logging/seeds)
3. 🔍 **GPT-5.4 code review** — cross-model review catches logic bugs before wasting GPU hours (`code review: true` by default)
4. ✅ **Sanity check** — run the smallest experiment first to catch runtime bugs
5. 🚀 **Deploy** full experiment suite to GPU via `/run-experiment`
6. 📊 **Collect** initial results and update the experiment tracker

```
┌─────────────────────────────────────────────────────────────────┐
│                Workflow 1.5: Experiment Bridge                    │
│                                                                  │
│   EXPERIMENT_PLAN.md                                             │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Claude   │────▶│ GPT-5.4  │────▶│ Sanity   │               │
│   │ Code     │     │ xhigh    │     │ Check    │               │
│   │ writes   │     │ reviews  │     │ (1 GPU)  │               │
│   │ code     │     │ code     │     │          │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Collect  │◀────│ Monitor  │◀────│ Deploy   │               │
│   │ results  │     │ progress │     │ to GPUs  │               │
│   │          │     │ (+ W&B)  │     │          │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│         │                                                        │
│         ▼                                                        │
│   Ready for /auto-review-loop                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Skills involved:** `experiment-bridge` + `run-experiment` + `monitor-experiment`

> 💡 **One-command shortcut:** `/experiment-bridge` reads `refine-logs/EXPERIMENT_PLAN.md` automatically. Or point it to any plan: `/experiment-bridge "my_plan.md"`.

> ⚙️ `CODE_REVIEW`, `AUTO_DEPLOY`, `SANITY_FIRST`, `MAX_PARALLEL_RUNS` are configurable — see [Customization](#%EF%B8%8F-customization).

### Workflow 2: Auto Research Loop 🔁 (sleep & wake up to results)

> **"Review my paper, fix what's wrong, repeat until it's good."**
>
> GPT-5.4 reviews → identifies weaknesses → suggests experiments → Claude Code writes scripts, deploys to GPU, monitors results, rewrites the paper — all while you sleep. Just add your [GPU server config](#%EF%B8%8F-gpu-server-setup-for-auto-experiments) to `CLAUDE.md`.

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
│   /run-experiment    — deploy to local/remote/vast.ai GPU     │
│   /analyze-results   — interpret experiment outputs          │
│   /monitor-experiment — check progress, collect results      │
└─────────────────────────────────────────────────────────────┘
```

**Skills involved:** `auto-review-loop` + `research-review` + `novelty-check` + `run-experiment` + `analyze-results` + `monitor-experiment`

> 💡 **One-command shortcut:** `/auto-review-loop "your paper topic"` runs this entire workflow automatically.
>
> **What to pass as argument?** A short topic or scope is enough — the skill automatically reads your project's narrative docs (`NARRATIVE_REPORT.md`), memory files, experiment results, and prior reviews to build the full context for GPT-5.4. Examples:
> - `/auto-review-loop "factorized gap in discrete diffusion LMs"` — broad topic, skill finds everything
> - `/auto-review-loop "focus on Section 3-5, our CRF results are weak"` — targeted scope with hints
> - `/auto-review-loop` — also works: skill reads project files and infers the topic

**🎮 Reviewer Difficulty** — control how adversarial the reviewer is:

| Level | What changes | Use when |
|-------|-------------|----------|
| `medium` (default) | Standard MCP review — same as before | Normal workflow |
| `hard` | + Reviewer Memory (GPT tracks suspicions across rounds) + Debate Protocol (Claude rebuts, GPT rules) | Want tougher feedback |
| `nightmare` | + GPT reads repo directly via `codex exec` (Claude can't filter what it sees) + adversarial verification | Preparing for top venue, want maximum stress test |

```bash
/auto-review-loop "topic" — difficulty: nightmare    # GPT reads your code and verifies claims itself
```

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

**Skills involved:** `paper-plan` + `paper-figure` + `paper-write` + `paper-compile` + `auto-paper-improvement-loop` + (post-acceptance) `paper-poster` + `paper-slides`

> **One-command shortcut:** `/paper-writing "NARRATIVE_REPORT.md"` runs this entire workflow automatically.

**Input:** A `NARRATIVE_REPORT.md` describing the research: claims, experiments, results, figures. The more detailed the narrative (especially figure descriptions and quantitative results), the better the output. See [`templates/NARRATIVE_REPORT_TEMPLATE.md`](templates/NARRATIVE_REPORT_TEMPLATE.md) for a complete example.

**Output:** A `paper/` directory with LaTeX source, clean `.bib` (only cited entries), and compiled PDF. The PDF is labelled `submission-ready` **only when** run at `— effort: max | beast` (or explicit `— assurance: submission`) **and** `tools/verify_paper_audits.sh` reports green on the three mandatory audits (`proof-checker`, `paper-claim-audit`, `citation-audit`); see [Assurance Gate](#assurance-gate-effort-max--beast) below. At the default `balanced` level, the output is a reviewed draft.

**Key features:**
- 📐 **Claims-Evidence Matrix** — every claim maps to evidence, every experiment supports a claim
- 📊 **Auto figure generation** — line plots, bar charts, comparison tables from JSON data
- 🧹 **Clean bib** — automated filtering removes uncited entries (948→215 lines in testing). Real BibTeX from [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) instead of LLM-generated entries
- 📄 **Flexible sections** — 5-8 sections depending on paper type (theory papers often need 7)
- 🔍 **GPT-5.4 review** — each step optionally reviewed by external LLM
- ✂️ **De-AI polish** — removes AI writing patterns (delve, pivotal, landscape...)
- 🎯 **Page verification** — `pdftotext`-based precise check that main body fits page limit

> ⚠️ **Figure generation scope:** `/paper-figure` auto-generates **data-driven plots** (training curves, bar charts, heatmaps) and **comparison tables** from JSON/CSV. For **architecture diagrams and method figures**: `illustration: gemini` (default) uses Claude→Gemini→Nano Banana Pro for publication-quality diagrams; `illustration: mermaid` generates Mermaid diagrams for free; `illustration: false` skips AI figures entirely.
>
> **Gemini API setup** (for `illustration: gemini`): Get your API key at [Google AI Studio](https://aistudio.google.com/apikey), then set it as an environment variable: `export GEMINI_API_KEY="your-key"`. Or add to your shell profile (`~/.zshrc` / `~/.bashrc`). No other dependencies needed.

**Tested end-to-end:** Generated a 9-page ICLR 2026 theory paper (7 sections, 29 citations, 4 figures, 2 comparison tables) from a single NARRATIVE_REPORT.md — zero compilation errors, zero undefined references.

#### Auto Paper Improvement Loop ✨

After Workflow 3 generates the paper, `/auto-paper-improvement-loop` runs 2 rounds of GPT-5.4 xhigh content review → fix → recompile, plus a final format compliance check, autonomously polishing the paper from rough draft to a reviewer-scored draft. Whether the result is tagged `submission-ready` is decided separately by the Phase 6 assurance gate (see [Assurance Gate](#assurance-gate-effort-max--beast)).

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

### Workflow 4: Rebuttal 📝 (reply to reviewers safely)

> **"Reviews are in. Help me draft a safe, grounded rebuttal."**

Got reviews back? `/rebuttal` parses them, builds a strategy, and drafts a venue-compliant response:

1. 📋 **Parse** — normalize reviews, validate venue rules (character limit, text-only, etc.)
2. 🔍 **Atomize** — split each review into issue cards (type, severity, reviewer stance)
3. 🗺️ **Strategize** — global themes, per-reviewer priorities, character budget, blocked claims
4. 🧪 **Evidence sprint** — if `auto experiment: true`, auto-run supplementary experiments via `/experiment-bridge`
5. ✍️ **Draft** — global opener + numbered per-reviewer responses + closing for meta-reviewer
6. 🛡️ **Safety check** — 6 lints: coverage, provenance, commitment, tone, consistency, limit
7. 🔬 **GPT-5.4 stress test** — internal skeptical review of the draft
8. 📄 **Finalize** — two outputs: `PASTE_READY.txt` (exact character count) + `REBUTTAL_DRAFT_rich.md` (extended version for manual editing)
9. 🔄 **Follow-up rounds** — delta replies for reviewer discussions, technically escalating

```
┌─────────────────────────────────────────────────────────────────┐
│                   Workflow 4: Rebuttal                            │
│                                                                  │
│   Reviews arrive                                                 │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Parse &  │────▶│ Strategy │────▶│ Evidence  │               │
│   │ atomize  │     │ plan     │     │ sprint    │               │
│   │ reviews  │     │          │     │ (optional)│               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Finalize │◀────│ GPT-5.4  │◀────│ Draft    │               │
│   │ 2 versions│    │ stress   │     │ rebuttal │               │
│   │          │     │ test     │     │          │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│         │                                                        │
│         ▼                                                        │
│   PASTE_READY.txt (strict) + RICH.md (extended)                  │
│         │                                                        │
│         ▼                                                        │
│   Follow-up rounds (delta replies, per-reviewer threads)         │
└─────────────────────────────────────────────────────────────────┘
```

**Skills involved:** `rebuttal`

> 💡 **Quick mode:** `/rebuttal — quick mode: true` stops after parsing + strategy (Phase 0-3). See what reviewers want before committing to a full draft.

> ⚙️ `VENUE`, `AUTO_EXPERIMENT`, `QUICK_MODE`, `MAX_STRESS_TEST_ROUNDS` are configurable — see [Customization](#%EF%B8%8F-customization).

**Three safety gates — rebuttal will NOT finalize if any fails:**
- 🔒 **Provenance** — every claim maps to paper/review/user-confirmed result. No fabrication.
- 🔒 **Commitment** — every promise is user-approved. No overpromising.
- 🔒 **Coverage** — every reviewer concern is tracked. Nothing disappears.

### 📚 Research Wiki — Persistent Research Memory

> **"Stop re-deriving. Start compounding."** — inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Without the wiki, ARIS is stateless — every `/idea-discovery` starts from scratch. With the wiki, ARIS accumulates knowledge across the entire research lifecycle: papers read, ideas tested, experiments run, claims verified or invalidated.

**The key insight:** failed ideas are the most valuable memory. A researcher who knows what doesn't work generates better ideas than one starting from zero.

**Setup:**
```
> /research-wiki init     # one-time, creates research-wiki/ in your project
```

**That's it.** Once initialized, the wiki works automatically:

| When | What happens | Wiki action |
|------|-------------|-------------|
| `/research-lit` finds papers | Papers auto-ingested | `papers/<slug>.md` created, edges added, query_pack rebuilt |
| `/idea-creator` runs | Reads wiki first | Failed ideas = banlist, gaps = search seeds, papers = known prior work |
| `/idea-creator` finishes | ALL ideas written back | Both recommended AND eliminated ideas → `ideas/<id>.md` |
| `/result-to-claim` judges | Results written back | Experiment page created, claim status updated (supported/invalidated) |
| 3+ ideas fail | Re-ideation suggested | "💡 Consider re-running /idea-creator — the wiki now knows what doesn't work" |

**Four entity types:**

| Entity | What it stores | Example |
|--------|---------------|---------|
| 📄 **Paper** | Structured summary: thesis, method, limitations, reusable ingredients | `paper:chen2025_factorized_gap` |
| 💡 **Idea** | Hypothesis, status (proposed/failed/succeeded), failure notes, lessons | `idea:001` |
| 🧪 **Experiment** | Metrics, verdict, hardware, duration | `exp:001` |
| 📋 **Claim** | Testable statement + evidence status (reported/supported/invalidated) | `claim:C1` |

**Typed relationships** (stored in `graph/edges.jsonl`):
```
paper --extends--> paper              idea --inspired_by--> paper
paper --contradicts--> paper          idea --tested_by--> experiment
paper --addresses_gap--> gap          experiment --supports--> claim
paper --supersedes--> paper           experiment --invalidates--> claim
```

**Spiral learning in action:**
```
Round 1: read 15 papers → wiki remembers → idea A → experiment → FAIL
         wiki records: "A fails because OOM at batch>32, loss diverges"

Round 2: /idea-creator reads wiki → sees A failed → generates idea D (avoids A's trap)
         → experiment → PARTIAL SUCCESS
         wiki records: "D works on small models, fails on large"

Round 3: /idea-creator reads wiki → knows A failed + D partial → generates idea F
         (combines D's success with new approach) → experiment → SUCCESS 🎉
```

**Subcommands:**
```
/research-wiki init                              # initialize wiki
/research-wiki ingest "paper title" — arxiv: xxx  # manually add a paper
/research-wiki query "topic"                      # rebuild query_pack.md
/research-wiki update idea:001 — outcome: negative # update entity
/research-wiki lint                               # health check (orphans, contradictions, stale claims)
/research-wiki stats                              # overview (paper/idea/experiment/claim counts)
```

> 🔒 **Safe by design:** All workflow hooks are guarded by `if research-wiki/ exists`. No wiki = no impact. Zero dependencies (pure Python stdlib). You choose when to enable it.

---

### Workflow M: Meta-Optimize 🧬 (ARIS optimizes itself)

> **"Analyze my usage patterns and improve your own skills."**

Unlike Workflows 1–4 which optimize *research artifacts* (papers, code, experiments), Workflow M optimizes the *harness itself* — the SKILL.md instructions, default parameters, and convergence rules that govern how ARIS operates. Inspired by [Meta-Harness](https://arxiv.org/abs/2603.28052) (Lee et al., 2026).

**Setup (one-time, in normal terminal):**
```bash
mkdir -p .claude .aris/meta tools/meta_opt
cp Auto-claude-code-research-in-sleep/templates/claude-hooks/meta_logging.json .claude/settings.json
cp Auto-claude-code-research-in-sleep/tools/meta_opt/*.sh tools/meta_opt/
chmod +x tools/meta_opt/*.sh
claude   # hooks active immediately
```

**Usage (after 5+ workflow runs):**
```
> /meta-optimize                        # analyze current project
> /meta-optimize "auto-review-loop"     # focus on one skill
> /meta-optimize --global               # analyze trends across ALL projects
> /meta-optimize apply 1                # apply recommended change #1
```

**How it works:**

1. 📊 **Passive logging** — Claude Code hooks silently record every skill invocation, tool call, failure, parameter override, and user prompt. Events are written to **both** project-level (`.aris/meta/events.jsonl`) and global (`~/.aris/meta/events.jsonl`, with a `"project"` tag) logs. Zero user effort.
2. 🔍 **Pattern analysis** — `/meta-optimize` reads the log and identifies:
   - Parameters users override most often (bad defaults)
   - Tools that fail repeatedly in specific skills (missing error handling)
   - Review score plateaus (convergence rules too loose/tight)
   - Manual corrections users make (skill gaps)
3. 🩹 **Patch proposal** — generates minimal diffs to target SKILL.md files with data-backed justifications
4. 🔬 **Reviewer gate** — GPT-5.4 xhigh reviews each patch: does the evidence support it? could it hurt other users?
5. ✅ **User approval** — only applied with explicit user consent. All changes are logged and reversible.

```
┌─────────────────────────────────────────────────────────────────┐
│                  Workflow M: Meta-Optimize                        │
│                                                                  │
│   Normal ARIS usage (W1-W4)                                      │
│         │ (hooks log events passively)                           │
│         ▼                                                        │
│   .aris/meta/events.jsonl                                        │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Analyze  │────▶│ Propose  │────▶│ GPT-5.4  │               │
│   │ patterns │     │ SKILL.md │     │ reviews  │               │
│   │          │     │ patches  │     │ patch    │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│                                    User approves?                 │
│                                     Yes → Apply                  │
│                                     No  → Skip                   │
└─────────────────────────────────────────────────────────────────┘
```

**What gets optimized (harness components):**
| Component | Example |
|-----------|---------|
| Skill prompts | Reviewer instructions, quality gates, step descriptions |
| Default parameters | `difficulty`, `MAX_ROUNDS`, `threshold` |
| Convergence rules | When to stop the review loop, retry counts |
| Error handling | Auto-debug patterns, failure recovery steps |

**What does NOT get optimized:** research artifacts (papers, code, experiments) — that's what W1–W4 do.

**Skills involved:** `meta-optimize`

> 💡 This is a **maintenance workflow**, not part of the W1→W1.5→W2→W3→W4 research pipeline. Run it periodically, like `git gc` for your research harness.

---

### ⚡ Effort Levels

> **"How hard should ARIS work?"** — Every skill accepts `— effort: lite | balanced | max | beast`.

| Level | Tokens | Best for | What changes |
|-------|:------:|----------|-------------|
| `lite` | ~0.4x | Quick exploration, budget users | Fewer papers, ideas, rounds. Minimum viable depth |
| `balanced` | 1x | Normal workflow (**default**) | Current ARIS behavior. Zero change for existing users |
| `max` | ~2.5x | Serious submission prep | More papers, deeper review, more ablations |
| `beast` | ~5-8x | Top-venue final sprint | Every knob to maximum. No budget limit |

**What NEVER changes regardless of effort:**
- Codex reasoning: **always xhigh** (reviewer quality is non-negotiable)
- DBLP/CrossRef citations: **always on**
- Reviewer independence: **always on**
- Experiment integrity: **always on**

```bash
# Every skill accepts effort independently
/research-lit "topic" — effort: beast              # 40-50 papers, 15+ queries
/idea-creator "direction" — effort: lite           # 4-6 ideas, quick filter
/auto-review-loop — effort: max                    # 6 rounds, 4-6 fixes/round

# Mix with specific overrides
/auto-review-loop — effort: beast, review_rounds: 3  # beast everything, but cap at 3 rounds

# Full pipeline
/research-pipeline "your topic" — effort: beast    # top-venue sprint mode
```

<details>
<summary><b>Full effort comparison table</b> — click to expand</summary>

| Skill | Dimension | lite | balanced | max | beast |
|-------|-----------|:----:|:--------:|:---:|:-----:|
| research-lit | papers | 6-8 | 10-15 | 18-25 | 40-50 |
| idea-creator | ideas | 4-6 | 8-12 | 12-16 | 20-30 |
| idea-creator | pilots | 1-2 | 2-3 | 3-4 | 5-6 |
| novelty-check | claims | 2-3 | 3-4 | 4-6 | all |
| research-refine | rounds | 3 | 5 | 7 | 10+ |
| experiment-plan | experiments | 3 | 5 | 7 | 10+ |
| experiment-plan | seeds | 1 | 3 | 5 | 5 |
| auto-review-loop | rounds | 2 | 3-4 | 6 | 8+ |
| paper-improvement | rounds | 1 | 2 | 3 | 5 |
| paper-illustration | iterations | 2 | 3 | 5 | 7 |
| rebuttal | stress tests | 0-1 | 1 | 2 | 3 |
| experiment-audit | depth | skip | basic | full | line-by-line |

</details>

> 📖 Full specification: [`shared-references/effort-contract.md`](skills/shared-references/effort-contract.md)

### Assurance Gate (effort: max | beast)

ARIS has two independent axes: **`effort`** controls how much work is done
(breadth/depth), **`assurance`** controls whether mandatory audits are
load-bearing. Default mapping:

| `effort` | Implied `assurance` | Paper-writing Phase 6 behavior |
|----------|---------------------|--------------------------------|
| `lite` / `balanced` (**default**) | `draft` | **Current behavior, zero change.** Audits run only if their content detector matches; missing artifacts are non-blocking. |
| `max` / `beast` | `submission` | Phase 6 force-invokes `/proof-checker`, `/paper-claim-audit`, `/citation-audit` in fresh threads, runs `tools/verify_paper_audits.sh`, and **refuses to emit the Final Report** if the verifier returns non-zero (missing / stale / FAIL / BLOCKED / ERROR). |

**What this fixes:** previously, `— effort: beast` did not actually
guarantee the three mandatory audits ran — the content detectors could
silent-skip, so beast-mode papers could ship without proof verification or
citation checks. The assurance axis makes audit enforcement externally
verifiable via `tools/verify_paper_audits.sh` (the verifier's exit code is
the source of truth, not the executor's self-report).

**Backwards compatibility:** users on the default `balanced` level see
zero change. Only users who opt up to `max` / `beast`, or who explicitly
pass `— assurance: submission`, see the new gate.

**Escape hatch:** `— effort: beast, assurance: draft` gets the old
"depth-only, no audit gate" behavior back. Legal but discouraged for
actual submissions.

**Optional harness hardening (advanced):** teams who want the model to
be *physically* prevented from ending a session while the verifier is red
can register a Stop hook in `~/.claude/settings.json` (replace
`<ARIS_REPO>` with the absolute path to your ARIS clone, e.g.
`/Users/you/Auto-claude-code-research-in-sleep`):

```json
{
  "hooks": {
    "Stop": [
      {"command": "bash <ARIS_REPO>/tools/verify_paper_audits.sh paper/ --assurance submission"}
    ]
  }
}
```

This is not required — the default repo behavior (Phase 6 verifier-as-truth)
already blocks Final Report emission on a red verdict. The Stop hook is a
belt-and-suspenders layer for teams that want harness-level enforcement.

> 📖 Full specification: [`shared-references/assurance-contract.md`](skills/shared-references/assurance-contract.md)

### 🧿 Optional: GPT-5.4 Pro via Oracle

> **For expert researchers who want the strongest possible reviewer.**

[Oracle](https://github.com/steipete/oracle) unlocks **GPT-5.4 Pro** as an ARIS reviewer — the strongest reasoning model available. Pro excels at deep mathematical proof verification, line-by-line code auditing, and complex experimental design critique.

**Setup:**
```bash
# 1. Install Oracle
npm install -g @steipete/oracle

# 2. Add Oracle MCP to Claude Code
claude mcp add oracle -s user -- oracle-mcp

# 3. Restart Claude Code

# 4a. API mode (fast, recommended):
export OPENAI_API_KEY="your-key"

# 4b. Browser mode (free, no API key — log in to ChatGPT in Chrome):
# Just open Chrome → chatgpt.com → log in
```

**Usage — add `— reviewer: oracle-pro` to any skill:**
```bash
/research-review "my draft" — reviewer: oracle-pro          # Pro-level paper critique
/proof-checker "paper/" — reviewer: oracle-pro              # deepest mathematical verification
/experiment-audit — reviewer: oracle-pro                    # Pro audits your eval code
/auto-review-loop "scope" — reviewer: oracle-pro            # Pro stress test each round
/idea-creator "direction" — reviewer: oracle-pro            # Pro evaluates your ideas
/rebuttal "paper/ + reviews" — reviewer: oracle-pro         # Pro stress tests your rebuttal
```

**Default is always Codex xhigh.** Oracle not installed = zero impact. `— reviewer: oracle-pro` without Oracle installed = graceful fallback to Codex + warning.

> 📖 Full specification: [`shared-references/reviewer-routing.md`](skills/shared-references/reviewer-routing.md)

---

## 🧰 All Skills

### 🚀 Full Pipeline

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 🏗️ [`research-pipeline`](skills/research-pipeline/SKILL.md) | **End-to-end**: Workflow 1 → 1.5 → 2 → 3, from research direction to submission | Yes |

### 🔍 Workflow 1: Idea Discovery & Method Refinement

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 🔭 **[`idea-discovery`](skills/idea-discovery/SKILL.md)** | **Pipeline orchestrator** — runs all skills below in sequence | Yes |
| ├ 📚 [`research-lit`](skills/research-lit/SKILL.md) | Multi-source literature search ([Zotero](#-zotero-integration-optional) + [Obsidian](#-obsidian-integration-optional) + local PDFs + [arXiv API](#arxiv-integration) + web) | No |
| ├ 💡 [`idea-creator`](skills/idea-creator/SKILL.md) | Brainstorm 8-12 ideas, filter by feasibility, pilot on GPU, rank by signal | Yes |
| ├ 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | Verify idea novelty against recent literature (multi-source + GPT-5.4 cross-check) | Yes |
| ├ 🔬 [`research-review`](skills/research-review/SKILL.md) | Single-round deep review from external LLM (xhigh reasoning) | Yes |
| └ 🧭 **[`research-refine-pipeline`](skills/research-refine-pipeline/SKILL.md)** | Refine method + plan experiments in one chain | Yes |
| 　├ 🔬 [`research-refine`](skills/research-refine/SKILL.md) | Problem anchor → iterative method refinement (up to 5 rounds, score ≥ 9) | Yes |
| 　└ 🧪 [`experiment-plan`](skills/experiment-plan/SKILL.md) | Claim-driven experiment roadmap with ablations, budgets, and run order | No |

### 🔗 Workflow 1.5: Experiment Bridge

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 🔗 **[`experiment-bridge`](skills/experiment-bridge/SKILL.md)** | Read experiment plan → implement code → sanity check → deploy to GPU → collect initial results | No |
| ├ 🚀 [`run-experiment`](skills/run-experiment/SKILL.md) | Deploy experiments to local, remote, or [Vast.ai](https://vast.ai) GPU (`gpu: local/remote/vast`) | No |
| ├ 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | Monitor running experiments, check progress, collect results | No |
| └ ☁️ [`vast-gpu`](skills/vast-gpu/SKILL.md) | Rent, manage, and destroy on-demand GPU instances from [Vast.ai](https://vast.ai) | No |

### 🔁 Workflow 2: Auto Research Loop

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 🔁 **[`auto-review-loop`](skills/auto-review-loop/SKILL.md)** | **Pipeline orchestrator** — autonomous review→fix→re-review (max 4 rounds) | Yes |
| ├ 🔬 [`research-review`](skills/research-review/SKILL.md) | Deep review from external LLM (shared with Workflow 1) | Yes |
| ├ 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | Verify novelty when reviewer suggests new directions | Yes |
| ├ 🚀 [`run-experiment`](skills/run-experiment/SKILL.md) | Deploy experiments to local, remote, or [Vast.ai](https://vast.ai) GPU (`gpu: local/remote/vast`) | No |
| ├ 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | Analyze experiment results, compute statistics, generate insights | No |
| └ 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | Monitor running experiments, check progress, collect results | No |
| 🔁 [`auto-review-loop-llm`](skills/auto-review-loop-llm/SKILL.md) | Same as above, but uses any OpenAI-compatible API via [`llm-chat`](mcp-servers/llm-chat/) MCP server | No |

### 📝 Workflow 3: Paper Writing

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 📝 **[`paper-writing`](skills/paper-writing/SKILL.md)** | **Pipeline orchestrator** — runs all skills below in sequence | Yes |
| ├ 📐 [`paper-plan`](skills/paper-plan/SKILL.md) | Claims-evidence matrix, section structure, figure plan, citation scaffolding | Yes |
| ├ 📊 [`paper-figure`](skills/paper-figure/SKILL.md) | Publication-quality matplotlib/seaborn plots + LaTeX comparison tables | Optional |
| ├ 🎨 [`paper-illustration`](skills/paper-illustration/SKILL.md) | AI-generated architecture diagrams and method figures via Gemini (when `illustration: true`) | No (needs Gemini API) |
| ├ ✍️ [`paper-write`](skills/paper-write/SKILL.md) | Section-by-section LaTeX generation (ICLR/NeurIPS/ICML). Anti-hallucination BibTeX via DBLP/CrossRef | Yes |
| ├ 🔨 [`paper-compile`](skills/paper-compile/SKILL.md) | Compile LaTeX to PDF, auto-fix errors, submission readiness checks | No |
| └ 🔄 [`auto-paper-improvement-loop`](skills/auto-paper-improvement-loop/SKILL.md) | 2-round content review + format check (4/10 → 8.5/10) | Yes |

### 📝 Workflow 4: Rebuttal

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 📝 **[`rebuttal`](skills/rebuttal/SKILL.md)** | Parse reviews → atomize → strategy → draft → safety check → stress test → finalize (2 versions) → follow-up | Yes |

### 🛠️ Standalone / Utility

| Skill | Description | Codex MCP? |
|-------|-------------|:---:|
| 📄 [`arxiv`](skills/arxiv/SKILL.md) | Search, download, and summarize arXiv papers. Standalone or `/research-lit` supplement | No |
| 🔎 [`semantic-scholar`](skills/semantic-scholar/SKILL.md) | Search published venue papers (IEEE, ACM, Springer) via Semantic Scholar API. Citation counts, venue metadata, TLDR | No |
| 📚 [`deepxiv`](skills/deepxiv/SKILL.md) | Progressive paper retrieval via DeepXiv CLI: search, brief, section map, section reads, trending, web search | Yes (`pip install deepxiv-sdk`) |
| 🔎 [`exa-search`](skills/exa-search/SKILL.md) | AI-powered broad web search via Exa: blogs, docs, news, companies, research papers with content extraction (highlights, text, summaries) | Yes (`pip install exa-py`) |
| 📝 [`alphaxiv`](skills/alphaxiv/SKILL.md) | Quick single-paper lookup via [AlphaXiv](https://alphaxiv.org) LLM-optimized summaries. Three-tier fallback: overview → full markdown → LaTeX source | No |
| 🎨 [`pixel-art`](skills/pixel-art/SKILL.md) | Generate pixel art SVG illustrations for READMEs, docs, or slides | No |
| 📱 [`feishu-notify`](skills/feishu-notify/SKILL.md) | [Feishu/Lark](#-feishulark-integration-optional) push (webhook) or interactive (bidirectional). Off by default | No |

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

> 💡 **Recommended: project-local flat symlink install** (since 2026-04-20). Each ARIS skill is symlinked individually into `.claude/skills/<skill-name>`, so Claude Code's slash-command discovery picks them up. A manifest at `.aris/installed-skills.txt` tracks what ARIS installed — uninstall and reconcile only ever touch managed entries, never your own skills.
>
> 🤖 **Codex mirror route:** keep Claude on `install_aris.sh` / `smart_update.sh`. For Codex-native project installs, use `install_aris_codex.sh`; for copied Codex installs, use `smart_update_codex.sh`.

```bash
# 1. Clone ARIS once to a stable location
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo

# 2. For each project that uses ARIS, attach via symlinks:
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh
# → creates one symlink per skill: .claude/skills/<skill> → ~/aris_repo/skills/<skill>
# → writes manifest .aris/installed-skills.txt (tracks every entry ARIS installed)
# → updates managed CLAUDE.md ARIS block (best-effort, compare-and-swap)
# → re-runnable: rerun anytime to reconcile new/removed upstream skills

# 3. To update existing skills' content for ALL attached projects:
cd ~/aris_repo && git pull   # symlinks resolve to live upstream — content updates automatically

# 3a. To pick up newly added or removed upstream skills, rerun the installer:
bash ~/aris_repo/tools/install_aris.sh ~/your-paper-project   # adds new symlinks, removes broken ones

# Other useful flags:
bash ~/aris_repo/tools/install_aris.sh --dry-run        # show plan, no changes
bash ~/aris_repo/tools/install_aris.sh --uninstall      # remove only managed symlinks (per manifest)
bash ~/aris_repo/tools/install_aris.sh --from-old       # migrate from old nested .claude/skills/aris/

# Windows (PowerShell, requires admin or developer mode for junctions):
.\tools\install_aris.ps1 C:\path\to\your-paper-project
```

**Why "git pull" alone isn't enough for new/removed skills:** the flat layout uses one symlink per skill, so upstream additions/deletions don't propagate until the installer is re-run. The trade-off bought us Claude Code's automatic slash-command discovery (which only scans one directory level deep).

<details>
<summary><b>Migrating from the old nested install (pre-2026-04-20)</b></summary>

If you previously installed via `install_aris.sh` (which created `.claude/skills/aris/` as a single nested symlink) or via `smart_update.sh --target-subdir .claude/skills/aris`, your slash commands probably weren't being auto-discovered by Claude Code. Migrate to the flat layout:

```bash
# Symlink-style legacy install:
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old

# Copy-style legacy install (with possible local edits — chose strategy explicitly):
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old --migrate-copy keep-user
#   → keeps your nested .claude/skills/aris/ copy intact alongside the new flat install
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old --migrate-copy prefer-upstream
#   → archives nested copy to .aris/legacy-copy-backup-<timestamp>/, then flattens
```

</details>

<details>
<summary><b>Alternative installs (advanced)</b></summary>

**Project-local copy (no symlinks, useful for per-project skill edits):**
```bash
mkdir -p ~/your-project/.claude/skills
bash ~/aris_repo/tools/smart_update.sh --project ~/your-project --apply
# Default --target-subdir is .claude/skills (flat), which is what Claude Code expects.
# (The old --target-subdir .claude/skills/aris is now deprecated — see migration block above.)
```

**Global install (one copy in your home dir, available to every project):**
```bash
mkdir -p ~/.claude/skills
cp -r ~/aris_repo/skills/* ~/.claude/skills/
# Update with: bash tools/smart_update.sh --apply
```

> Global install increases the risk of skill name collisions with other globally-installed packs. Use only if you don't mix ARIS with Superpowers / OpenHands / etc. — otherwise prefer the project-local install above.

</details>

> 💡 **New Claude Code versions** may not auto-create `~/.claude/skills/`. If using global install, create it first: `mkdir -p ~/.claude/skills/`. The symlink installer handles directory creation automatically.

<details>
<summary><b>Optional: Codex Plugin for Code Review</b></summary>

[codex-plugin-cc](https://github.com/openai/codex-plugin-cc) provides additional Codex capabilities that ARIS auto-detects when installed:

```bash
# In Claude Code:
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

**Where ARIS uses the plugin:**

| Skill | Command | What it does |
|-------|---------|-------------|
| `/codex:review` | Workflow 1.5 | Review experiment code before GPU deployment |
| `/codex:adversarial-review` | Workflow 1.5 | Adversarial code review (find edge cases, bugs) |
| `/codex:rescue` | Workflow 1.5 + 3 | **Auto-debug rescue** — when experiment or LaTeX compilation fails after 2 attempts, Codex independently diagnoses the root cause before the next retry |

All plugin features are **optional** — if not installed, ARIS falls back to Claude's own diagnosis. The plugin just adds a second pair of eyes.

> Note: ARIS's core cross-model review (paper scoring, idea evaluation, rebuttal stress test) still uses Codex MCP, which allows custom prompts. The plugin cannot replace this.

</details>

### Update Skills

```bash
cd Auto-claude-code-research-in-sleep
git pull

# 🧠 Smart update (recommended) — analyzes what's safe to update
bash tools/smart_update.sh          # dry-run: shows what would change
bash tools/smart_update.sh --apply  # apply: adds new + updates safe ones

# Manual options (if you prefer):
# cp -r skills/* ~/.claude/skills/       # Option A: overwrite all
# cp -rn skills/* ~/.claude/skills/      # Option B: only add new, keep yours
# cp -r skills/experiment-bridge ~/.claude/skills/  # Option C: specific skill
```

> 💡 **Smart update** compares your local skills with upstream, detects personal customizations (server paths, API keys, etc.), and only updates skills that are safe to replace. Skills with your personal info are flagged for manual review.

### Usage

```
# Workflow 1: Idea Discovery
> /idea-discovery "your research direction"          # full pipeline
> /research-lit "topic"                              # just literature survey (all sources)
> /research-lit "topic" — sources: zotero, web        # mix and match sources
> /research-lit "topic" — sources: deepxiv            # DeepXiv-only progressive retrieval
> /research-lit "topic" — sources: exa                # Exa AI-powered web search with content extraction
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

Three GPU modes are supported — pick one and add it to your project's `CLAUDE.md`:

#### Option A: Remote SSH Server (`gpu: remote`)

```markdown
## Remote Server
- gpu: remote
- SSH: `ssh my-gpu-server` (key-based auth, no password)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`
- Use `screen` for background jobs: `screen -dmS exp0 bash -c '...'`
```

Claude Code reads this and knows how to SSH in, activate the environment, and launch experiments. GPT-5.4 (the reviewer) only decides **what** experiments to run — Claude Code figures out **how** based on your `CLAUDE.md`.

#### Option B: Local GPU (`gpu: local`)

If you are already on the GPU server, you can add the following to your `CLAUDE.md`:
```markdown
## GPU Environment
- gpu: local
- This machine has direct GPU access (no SSH needed)
- GPU: 4x A100 80GB
- Experiment environment: `YOUR_CONDA_ENV` (Python 3.x + PyTorch)
- Activate before any Python command: `The command to activate your experiment environment` (uv, conda, etc.)
- Code directory: `/home/YOUR_USERNAME/YOUR_CODE_DIRECTORY/`
```

#### Option C: Vast.ai On-Demand GPU (`gpu: vast`)

No GPU? Rent one from [Vast.ai](https://vast.ai) on demand. ARIS **analyzes your training task** (model size, dataset, estimated time), searches for the cheapest GPU that fits, and presents options with **estimated total cost** — not just $/hr. After you pick, it handles everything: rent → setup → run → collect results → destroy.

**Prerequisites:**

1. **Create a Vast.ai account** at https://cloud.vast.ai/ and add billing (credit card or crypto)

2. **Install the `vastai` CLI** (requires **Python ≥ 3.10**):
   ```bash
   pip install vastai
   ```
   If your Python is older (check with `python --version`), use a virtual environment with Python ≥ 3.10 (e.g., `conda create`, `pyenv`, `uv venv`, etc.).

3. **Set your API key** — get it from https://cloud.vast.ai/cli/:
   ```bash
   vastai set api-key YOUR_API_KEY
   ```

4. **Upload your SSH public key** at https://cloud.vast.ai/manage-keys/ — this is **required before renting any instance** (keys are baked in at creation time). If you don't have one:
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   cat ~/.ssh/id_ed25519.pub   # copy this to Vast.ai
   ```

5. **Verify setup** — test that search works:
   ```bash
   vastai search offers 'gpu_ram>=24 reliability>0.95' -o 'dph+' --limit 3
   ```

**Add to `CLAUDE.md`:**
```markdown
## Vast.ai
- gpu: vast                  # rent on-demand GPU from vast.ai
- auto_destroy: true         # auto-destroy after experiment completes (default)
- max_budget: 5.00           # optional: warn if estimated cost exceeds this
```

That's it — no GPU model or hardware config needed. When you run `/run-experiment`, ARIS reads your experiment scripts/plan, estimates VRAM and training time, and presents options like:

```
| # | GPU       | VRAM  | $/hr  | Est. Hours | Est. Total | Offer ID |
|---|-----------|-------|-------|------------|------------|----------|
| 1 | RTX 4090  | 24 GB | $0.28 | ~4h        | ~$1.12     | 6995713  |  ← best value
| 2 | A100 SXM  | 80 GB | $0.95 | ~2h        | ~$1.90     | 7023456  |  ← fastest
```

Pick a number and it handles the rest. Use `/vast-gpu` directly for manual control.

**No server at all?** The review and rewriting skills still work without GPU access. Only experiment-related fixes will be skipped (flagged for manual follow-up).

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

<details>
<summary><h3>📱 Feishu/Lark Integration (Optional)</h3></summary>

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
| `/vast-gpu` | Instance rented/destroyed | Instance ID + cost | Instance ID + cost |
| `/monitor-experiment` | Results collected | Results table | Results table |
| `/idea-discovery` | Phase transitions, final report | Summary at each phase | + approve/reject at checkpoints |
| `/research-pipeline` | Stage transitions, pipeline done | Stage summary | + approve/reject |

</details>

**Not using Feishu?** No problem — without `~/.claude/feishu.json`, all skills behave exactly as before. Zero overhead, zero side effects.

> 💡 **Alternative IM platforms**: The push-only webhook pattern works with any service that accepts incoming webhooks (Slack, Discord, DingTalk, WeChat Work). Just change the `webhook_url` and card format in `feishu-notify/SKILL.md`. For bidirectional support, see [cc-connect](https://github.com/chenhg5/cc-connect) (multi-platform bridge) or [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu).

</details>

## 🎛️ Customization

Skills are plain Markdown files. Fork and customize:

> 💡 **Parameter pass-through**: Parameters flow down the call chain automatically. For example, `/research-pipeline "topic" — sources: zotero, arxiv download: true` passes `sources` and `arxiv download` through `idea-discovery` all the way down to `research-lit`. This also works for optional sources such as `deepxiv` and `exa`: `/research-pipeline "topic" — sources: all, deepxiv, exa`. You can set any downstream parameter at any level — just add `— key: value` to your command.
>
> ```
> research-pipeline  ──→  idea-discovery      ──→  research-lit
>                    ──→  experiment-bridge    ──→  run-experiment
>                    ──→  auto-review-loop
>                                             ──→  idea-creator
>                                             ──→  novelty-check
>                                             ──→  research-review
> ```

### Full Research Pipeline (`research-pipeline`)

| Constant | Default | Description | Pass-through |
|----------|---------|-------------|:---:|
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond | → `idea-discovery` |
| `ARXIV_DOWNLOAD` | false | Download top arXiv PDFs after literature search | → `idea-discovery` → `research-lit` |
| `HUMAN_CHECKPOINT` | false | When `true`, pause after each review round for approval | → `auto-review-loop` |
| `WANDB` | false | Auto-add W&B logging to experiments | → `experiment-bridge` → `run-experiment` |
| `CODE_REVIEW` | true | GPT-5.4 reviews experiment code before deployment | → `experiment-bridge` |
| `BASE_REPO` | false | GitHub repo URL to clone as base codebase for experiments | → `experiment-bridge` |
| `GPU` | `local` | GPU target: `local`, `remote` (SSH), or `vast` ([Vast.ai](https://vast.ai) on-demand rental) | → `experiment-bridge` → `run-experiment` |
| `COMPACT` | false | Generate compact summary files for short-context models and session recovery | → all workflows |
| `REF_PAPER` | false | Reference paper (PDF path or URL) to base ideas on. Summarized first, then used as context | → `idea-discovery` |
| `ILLUSTRATION` | `gemini` | AI illustration: `gemini` (default), `mermaid` (free), or `false` (skip) | → `paper-writing` |

Override inline: `/research-pipeline "topic" — auto proceed: false, illustration: mermaid`

### Auto Review Loop (`auto-review-loop`)

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_ROUNDS` | 4 | Maximum review→fix→re-review iterations |
| `POSITIVE_THRESHOLD` | 6/10 | Score at which the loop stops (submission-ready) |
| `> 4 GPU-hour skip` | 4h | Experiments exceeding this are flagged for manual follow-up |

### Idea Discovery (`idea-discovery` / `idea-creator`)

| Constant | Default | Description | Pass-through |
|----------|---------|-------------|:---:|
| `PILOT_MAX_HOURS` | 2h | Skip any pilot estimated to take longer per GPU | — |
| `PILOT_TIMEOUT_HOURS` | 3h | Hard timeout — kill runaway pilots, collect partial results | — |
| `MAX_PILOT_IDEAS` | 3 | Maximum number of ideas to pilot in parallel | — |
| `MAX_TOTAL_GPU_HOURS` | 8h | Total GPU budget across all pilots | — |
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond | — |
| `ARXIV_DOWNLOAD` | false | Download top arXiv PDFs after literature search | → `research-lit` |

Override inline: `/idea-discovery "topic" — pilot budget: 4h per idea, sources: zotero, arxiv download: true`

### Experiment Bridge (`experiment-bridge`)

| Constant | Default | Description |
|----------|---------|-------------|
| `CODE_REVIEW` | true | GPT-5.4 xhigh reviews code before deployment. Catches logic bugs before wasting GPU hours |
| `AUTO_DEPLOY` | true | Automatically deploy experiments after implementation + review. Set `false` to manually inspect |
| `SANITY_FIRST` | true | Run smallest experiment first to catch setup bugs before full deployment |
| `MAX_PARALLEL_RUNS` | 4 | Maximum experiments to deploy in parallel (limited by available GPUs) |
| `WANDB` | false | Auto-add W&B logging. Requires `wandb_project` in CLAUDE.md |
| `BASE_REPO` | false | GitHub repo URL to clone as base codebase for experiments |

Override inline: `/experiment-bridge — base repo: https://github.com/org/project`

### Literature Search (`research-lit`)

| Constant | Default | Description |
|----------|---------|-------------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | Local directories to scan for PDFs before searching online |
| `MAX_LOCAL_PAPERS` | 20 | Max local PDFs to scan (first 3 pages each) |
| `SOURCES` | `all` | Which sources to search: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, or `all`. `semantic-scholar`, `deepxiv`, and `exa` must be explicitly listed |
| `ARXIV_DOWNLOAD` | false | When `true`, download top relevant arXiv PDFs to PAPER_LIBRARY after search |
| `ARXIV_MAX_DOWNLOAD` | 5 | Maximum number of PDFs to download when `ARXIV_DOWNLOAD = true` |

Override inline: `/research-lit "topic" — sources: zotero, web`, `/research-lit "topic" — sources: all, deepxiv`, `/research-lit "topic" — sources: all, exa`, `/research-lit "topic" — arxiv download: true, max download: 10`

### Paper Writing (`paper-write`)

| Constant | Default | Description |
|----------|---------|-------------|
| `DBLP_BIBTEX` | true | Fetch real BibTeX from DBLP/CrossRef instead of LLM-generated entries |
| `TARGET_VENUE` | `ICLR` | Target venue: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_JOURNAL`, `IEEE_CONF` |
| `ANONYMOUS` | true | Use anonymous author block for blind review. Note: most IEEE venues are NOT anonymous — set `false` for IEEE |
| `MAX_PAGES` | 9 | Page limit. ML conferences: main body excl. refs. IEEE: total pages incl. refs |
| `ILLUSTRATION` | `gemini` | AI illustration mode: `gemini` (default, needs `GEMINI_API_KEY`), `mermaid` (free), or `false` (skip) |

Override inline: `/paper-write — target venue: NeurIPS, illustration: mermaid`

### General (all skills using Codex MCP)

| Constant | Default | Description |
|----------|---------|-------------|
| `REVIEWER_MODEL` | `gpt-5.4` | OpenAI model used via Codex MCP. Also available: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. See [supported models](https://developers.openai.com/codex/models/) for full list. |

- **Prompt templates** — tailor the review persona and evaluation criteria
- **`allowed-tools`** — restrict or expand what each skill can do

## 🔀 Alternative Model Combinations

Don't have Claude / OpenAI API access? You can swap in other models — same cross-model architecture, different providers.

> ⭐ **We strongly recommend Claude + GPT-5.4 (default setup).** It's the most tested and reliable combination. Alternative setups work but may require prompt tuning.

| | Executor | Reviewer | Need Claude API? | Need OpenAI API? | Guide |
|---|----------|----------|:---:|:---:|-------|
| **Default** ⭐ | Claude Opus/Sonnet | GPT-5.4 (Codex MCP) | Yes | Yes | [Quick Start](#-quick-start) |
| **Alt A** | GLM-5 (Z.ai) | GPT-5.4 (Codex MCP) | No | Yes | [Setup below](#alt-a-glm--gpt) |
| **Alt B** | GLM-5 (Z.ai) | MiniMax-M2.7 | No | No | [MINIMAX_MCP_GUIDE](docs/MINIMAX_MCP_GUIDE.md) |
| **Alt C** | Any CC-compatible | Any OpenAI-compatible | No | No | [LLM_API_MIX_MATCH_GUIDE](docs/LLM_API_MIX_MATCH_GUIDE.md) |
| **Alt D** | Kimi-K2.5 / Qwen3.5+ | GLM-5 / MiniMax-M2.7 | No | No | [ALI_CODING_PLAN_GUIDE](docs/ALI_CODING_PLAN_GUIDE.md) |
| **Alt E** 🆓 | DeepSeek-V3.1 / Qwen3-Coder | DeepSeek-R1 / Qwen3-235B | No | No | [MODELSCOPE_GUIDE](docs/MODELSCOPE_GUIDE.md) |
| **Alt F** | Codex CLI (GPT-5.4) | Codex `spawn_agent` (GPT-5.4) | No | Yes | [skills-codex/](skills/skills-codex/) |
| **Alt G** 🆕 | Codex CLI | Claude Code CLI (`claude-review` MCP) | No* | No* | [CODEX_CLAUDE_REVIEW_GUIDE](docs/CODEX_CLAUDE_REVIEW_GUIDE.md) |
| **Alt H** 🆕 | Antigravity (Claude Opus 4.6 / Gemini 3.1 Pro) | GPT-5.4 (Codex MCP) or any via llm-chat | No | Optional | [ANTIGRAVITY_ADAPTATION](docs/ANTIGRAVITY_ADAPTATION.md) |
| **Alt I** 🆕 | Codex CLI | Gemini direct API (`gemini-review` MCP) | No | No | [CODEX_GEMINI_REVIEW_GUIDE](docs/CODEX_GEMINI_REVIEW_GUIDE.md) |

**Alt C** supports tested providers: GLM (Z.ai), Kimi (Moonshot), LongCat (Meituan) as executors; DeepSeek, MiniMax as reviewers. Any OpenAI-compatible API should also work via the generic [`llm-chat`](mcp-servers/llm-chat/) MCP server. **Alt D** uses [Alibaba Coding Plan](https://bailian.console.aliyun.com/) — one API key for both executor and reviewer, 4 models included (Kimi, Qwen, GLM, MiniMax). **Alt E** uses [ModelScope](https://www.modelscope.cn/) — **free** (2000 calls/day), one key, no automation restrictions. **Alt G** keeps Codex as executor but swaps the reviewer to Claude Code CLI via the local `claude-review` MCP bridge, with async polling for long paper/review prompts. **Alt H** uses [Google Antigravity](https://antigravity.google/) as the executor with native SKILL.md support — choose Claude Opus 4.6 (Thinking) or Gemini 3.1 Pro (high) as the execution model. **Alt I** keeps Codex as executor, adds only a thin `skills-codex-gemini-review` overlay, and routes the reviewer-aware predefined skills through the local `gemini-review` MCP bridge with direct Gemini API by default. It is the closest Gemini analogue to the existing Codex+Claude review path, while minimizing skill changes and now also covers poster PNG review via the same bridge. Free-tier availability, rate limits, and data-use terms remain subject to Google's current policy.

\* Alt G normally relies on local Codex CLI and Claude Code CLI logins. Direct API keys are optional, not required.

### Alt A: GLM + GPT

Only replace the executor (Claude → GLM), keep GPT-5.4 as reviewer via Codex MCP.

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
codex setup   # set model to gpt-5.4
```

Configure `~/.claude/settings.json`:

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
            "args": ["mcp-server"]
        }
    }
}
```

Codex CLI uses your existing `OPENAI_API_KEY` (from `~/.codex/config.toml` or environment) — no extra config needed for the reviewer side.

### Alt B: GLM + MiniMax

No Claude or OpenAI API needed. Uses a custom MiniMax MCP server instead of Codex (because MiniMax doesn't support OpenAI's Responses API). Full guide: [`docs/MINIMAX_MCP_GUIDE.md`](docs/MINIMAX_MCP_GUIDE.md).

### Alt C: Any Executor + Any Reviewer

Mix and match freely using the generic `llm-chat` MCP server. Supports any OpenAI-compatible API as reviewer. Full guide: [`docs/LLM_API_MIX_MATCH_GUIDE.md`](docs/LLM_API_MIX_MATCH_GUIDE.md).

Example combinations: GLM + DeepSeek, Kimi + MiniMax, Claude + DeepSeek, LongCat + GLM, etc.

### After Setup: Install Skills & Verify

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep
cp -r skills/* ~/.claude/skills/
claude
```

> **⚠️ For non-Claude executors (GLM, Kimi, etc.):** Let the model read through the project once to ensure skills are correctly parsed. This is especially important if you've [rewritten skills](#-alternative-model-combinations) to use a different reviewer MCP (e.g., `mcp__llm-chat__chat` instead of `mcp__codex__codex`) — the new executor needs to understand the changed tool call patterns:
>
> ```
> Read through this project and verify all skills are working:
> /idea-creator, /research-review, /auto-review-loop, /novelty-check,
> /idea-discovery, /research-pipeline, /research-lit, /run-experiment,
> /analyze-results, /monitor-experiment, /pixel-art
> ```

> ⚠️ **Note:** Alternative models may behave differently from Claude and GPT-5.4. You may need to tune prompt templates for best results. The core cross-model architecture remains the same.

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
- [x] **Peer review skill** — `/peer-review` for reviewing others' papers as a conference reviewer, with GPT-5.4 meta-review (planned; currently use `/research-review` with a paper PDF)
- [x] **Cross-model collaboration** — Claude Code (executor) × Codex GPT-5.4 xhigh (reviewer) architecture, avoiding single-model self-play local minima
- [x] **Feishu/Lark integration** — three modes (off/push/interactive), configurable via `~/.claude/feishu.json`. Push-only needs just a webhook URL; interactive uses [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code). Off by default — zero impact on existing workflows. See [setup guide](#-feishulark-integration-optional)
- [x] **Zotero MCP integration** — `/research-lit` searches Zotero collections, reads annotations/highlights, exports BibTeX. Recommended: [zotero-mcp](https://github.com/54yyyu/zotero-mcp) (1.8k⭐). See [setup guide](#-zotero-integration-optional)
- [x] **Obsidian integration** — `/research-lit` searches Obsidian vault for research notes, tagged references, wikilinks. Recommended: [mcpvault](https://github.com/bitbonsai/mcpvault) (760⭐) + [obsidian-skills](https://github.com/kepano/obsidian-skills) (13.6k⭐). See [setup guide](#-obsidian-integration-optional)
- [x] **More executor × reviewer combinations** — any OpenAI-compatible API works via [`llm-chat`](mcp-servers/llm-chat/) MCP server. GLM, MiniMax, Kimi, LongCat, DeepSeek all tested — no Claude or OpenAI API required
- [x] **GitHub-based code sync** — `/run-experiment` supports `code_sync: git` (`git push` → `ssh "git pull"`)
- [x] **W&B integration** — auto `wandb.init()` + `wandb.log()` when `wandb: true`. `/monitor-experiment` pulls training curves
- [x] **ModelScope integration** — [free](docs/MODELSCOPE_GUIDE.md) (2000 calls/day), one API key, dual-protocol

</details>

### Planned

- [ ] **Daemon mode** — auto-restart Claude Code session via `launchd`/`systemd` for true unattended operation. Currently the orchestration layer requires an active CLI session; state files (`REVIEW_STATE.json`, `AUTO_REVIEW.md`) support resuming across sessions, but relaunch is manual ([#11](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/11))
- [ ] **Reference-style figure generation** — read figures from reference PDFs → identify chart type, color scheme, layout → generate same-style figures with your own data. Sub-goal remaining: **Data charts** (extract color/font style → matplotlib rcParams). Method diagrams ✅ solved by `paper-illustration`
- [ ] **Workflow execution report** — after each workflow (1/1.5/2/3) completes, auto-generate a structured summary: what was done, key decisions made, experiments run, results obtained, scores, and time spent. Output as `WORKFLOW_REPORT.md` for progress tracking, team reporting, and supervisor updates
- [x] **Document-based pipeline input** — `/idea-discovery` and `/research-pipeline` auto-detect `RESEARCH_BRIEF.md` in project root. Detailed context replaces one-line prompt. Template: `templates/RESEARCH_BRIEF_TEMPLATE.md`
- [ ] **Auto hyperparameter tuning skill** — rewrite [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) as an ARIS SKILL.md. 5-step cycle: understand project → plan tuning strategy → run experiments → analyze metrics (TensorBoard/W&B) → learn and iterate. Would plug into Workflow 1.5 (`/experiment-bridge`) or Workflow 2 (`/auto-review-loop`) when reviewer says "tune hyperparameters"
- [ ] **Plugin format** — package ARIS as a Claude Code Plugin for one-click install via `/plugin install aris`. Skills version continues for cross-platform compatibility (Codex CLI, Cursor, Trae, etc.)

## 💬 Community

**Domain-specific skills welcome!** The core skills cover general research workflows, but every field has its own tools and patterns. We welcome PRs that add new skills for your domain — EDA, bioinformatics, robotics, HPC, or anything else. Just add a `skills/your-skill/SKILL.md` and open a PR. See [`dse-loop`](skills/dse-loop/SKILL.md) for an example.

Join the WeChat group for discussion on Claude Code + AI-driven research workflows:

<img src="docs/wechat_group.jpg" alt="WeChat Group QR Code" width="300">

## 📖 Citation

If you use ARIS in your research, please cite:

```bibtex
@misc{yang2026aris,
    author       = {Yang, Ruofeng and Li, Yongcan and Li, Shuai},
    title        = {ARIS: Fully Autonomous Research via Adversarial Multi-Agent Collaboration},
    year         = {2026},
    url          = {https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep},
}
```

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260328)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## 🙏 Acknowledgements

ARIS is inspired by:

- 🧪 [AI Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) — Automated research pioneer
- 📖 [AutoResearch](https://github.com/karpathy/autoresearch) (Andrej Karpathy) — End-to-end research automation
- 🔭 [FARS](https://analemma.ai/blog/introducing-fars/) (Analemma) — Fully Automated Research System
- 🎨 [PaperBanana](https://github.com/dwzhu-pku/PaperBanana) (PKU) — Multi-agent academic illustration framework

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

**Special Thanks — Platform Adaptation**

ARIS wouldn't run on so many platforms without these contributors:

- 🤖 [@Falling-Flower](https://github.com/Falling-Flower) — adapted all ARIS skills for [Codex CLI](https://github.com/openai/codex) using `spawn_agent`
- 🔧 [@No-518](https://github.com/No-518) — ongoing maintenance of the Codex skill set, keeping parity with latest updates
- 🖱️ [@YecanLee](https://github.com/YecanLee) — wrote the [Cursor adaptation guide](docs/CURSOR_ADAPTATION.md) and local GPU setup docs
- 🏆 [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) — first community paper built entirely with ARIS, scored 8/10 at CS conference

**Special Thanks — Architecture & Vision**

- 💡 [@JingxuanKang](https://github.com/JingxuanKang) — beyond code contributions (training-check, result-to-claim, ablation-planner, watchdog, templates, session recovery), deeply shaped ARIS through discussions on architecture design, compact mode, workflow state management, and the vision of what autonomous research workflows should look like. Many of today's core features — from structured project files to context-aware session recovery — grew out of these conversations.

## License

MIT
