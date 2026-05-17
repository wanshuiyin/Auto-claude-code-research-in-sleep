# Auto-claude-code-research-in-sleep (ARIS ⚔️🌙)

💡 *Use ARIS in Claude Code / Cursor / Trae as a skill-based workflow, or get the full experience with the standalone CLI — enjoy any way you like!*

🤖 **AI agents:** Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) instead — structured for LLM consumption, not human browsing.

🔥 [**ARIS-Code CLI — 独立安装版**](docs/ARIS-Code-README_CN.md) · [English](docs/ARIS-Code-README_EN.md) | [⬇️ Download](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest)

> 📰 **ARIS-Code v0.4.5 → v0.4.9** (2026-05) — Five-release polish sequence. **New providers**: DeepSeek V4 Pro / Xiaomi MiMo / Qwen 3.6 / Doubao / Custom OpenAI-compatible / DashScope Coding Plan (via `native-tls` switch). **Reasoning + tool-use first class**: `reasoning_effort='xhigh'` on the wire for o-series / gpt-5.5 / DeepSeek-thinking, `reasoning_content` cache+replay for Kimi / Moonshot / Xiaomi MiMo / DeepSeek-R1, thinking content blocks end-to-end. **Skill helper subsystem rewrite**: bundled helpers materialise into `~/.config/aris/cache/<version>/` at startup (no more cwd pollution), `SkillOutput.helperReport` JSON + 4-layer fallback chain, new `integration-contract.md` with 6 failure policies, inventory test + smoke regression guard. **Critical bug fixes**: `PermissionMode::Prompt` was silently allowing every tool (derived-`Ord` bug, every version pre-v0.4.6); hardcoded `current_date = "2026-03-31"` made models reject real post-cutoff data; Custom reviewer reset to gpt-5.5 every restart (setup menu option 9 vs 8 typo); third-party Anthropic-compat proxies hit `missing field signature` ([#228](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/228)); gpt-5.5 / o3 / o4 + tools 400 on OpenAI. Credits: [@GetIT-Sunday](https://github.com/GetIT-Sunday), [@Anduin9527](https://github.com/Anduin9527), [@GO-player-hhy](https://github.com/GO-player-hhy), [@Jxy-yxJ](https://github.com/Jxy-yxJ), [@screw-44](https://github.com/screw-44), [@StevenUST](https://github.com/StevenUST).
>
> <details><summary>Per-release details (v0.4.5 → v0.4.9)</summary>
>
> **v0.4.9** (2026-05-17) — Closes Codex v0.4.7 audit residuals (L1 TLS double-stack, L3 reasoning_cache compaction misalign, L4 reasoning replay unbounded). 2 new skills bundled (`/figure-spec` + `/paper-illustration-image2` with `scripts/` subdirs, new Layer 0b = `$ARIS_CACHE_DIR/skills/<name>/scripts/`); `research_wiki.py` promoted to shared `tools/` (9+ callers); 5 more SKILL.md migrated to fallback chain.
>
> **v0.4.8** (2026-05-17) — Skill helper subsystem rewrite. Bundled helpers extract to `~/.config/aris/cache/<version>/` at startup; every Skill invocation surfaces `helperReport` JSON + 4-layer resolver preamble; `/skills export` copies helpers; new `integration-contract.md` with 6 failure policies; 8 shared helpers (arxiv/deepxiv/exa/S2/openalex/save_trace/verify_papers/verify_paper_audits) bundled; `/research-lit` + `/deepxiv` migrated. Plus 4 bug fixes: gpt-5.5+tools 400 on OpenAI; Custom reviewer reset; missing `signature` field ([#228](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/228)); `--version` Build date hardcoded.
>
> **v0.4.7** (2026-05-16) — DashScope Coding Plan 405 fixed ([#159](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/159)) via `native-tls` switch ([#225](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/225)); `reasoning_content` replay for all reasoning models (OpenAI o1/o3/o4 / DeepSeek-R1 etc.), not just Kimi ([#226](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/226)); 600+ lines dead code cleanup + `rustyline` dep removed + "Claw Code" → "ARIS-Code" rebrand.
>
> **v0.4.6** (2026-05-14) — 🚨 Two long-standing silent bugs fixed: `PermissionMode::Prompt` silently allowed every tool (derived-`Ord` bug); system prompt hardcoded `current_date = "2026-03-31"` made models reject post-cutoff data as future/prompt-injection. Plus Custom OpenAI-compatible provider (`/setup` option 11) with dynamic `/models` discovery ([@Anduin9527](https://github.com/Anduin9527) [#221](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/221) + [#222](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/222)).
>
> **v0.4.5** (2026-05-13) — First-class reasoning-model support: thinking content blocks end-to-end (fixes [#161](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/161)) + `reasoning_effort='xhigh'` for GPT-5.5 / o1 / o3 / o4 / DeepSeek-thinking. DeepSeek V4 Pro + Xiaomi MiMo + Qwen 3.6 + Doubao in `/setup` (options 7-10). Object-style hooks parser. Default model bumped to Claude Opus 4.7 + GPT-5.5. REPL input hardening (multi-line wrap / Cmd+V paste / CJK boundary). GitHub Actions CI. Credits: [@GO-player-hhy](https://github.com/GO-player-hhy) ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186)), [@Jxy-yxJ](https://github.com/Jxy-yxJ) ([#171](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/171)), [@GetIT-Sunday](https://github.com/GetIT-Sunday) ([#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216) partial).
>
> </details>
>
> <details><summary>Older versions</summary>
>
> **v0.4.4** (2026-04-20) — **Setup UX + reviewer routing fixes** (resolves [#158](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/158), [#162](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/162)) | `/setup` no longer forces Bearer for Anthropic + custom URL | Provider-aware proxy URL hints | Stale state no longer leaks across provider switches | LlmReview smart fallback
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

> 🌙 **Let Claude Code do research while you sleep.** Wake up to find your paper scored, weaknesses identified, experiments run, and narrative rewritten — autonomously.
>
> 🪶 **Radically lightweight — zero dependencies, zero lock-in.** The entire system is plain Markdown files. No framework to learn, no database to maintain, no Docker to configure, no daemon to babysit. Every skill is a single `SKILL.md` readable by any LLM — swap Claude Code for [Codex CLI](skills/skills-codex/), [OpenClaw](docs/OPENCLAW_ADAPTATION.md), [Cursor](docs/CURSOR_ADAPTATION.md), [Trae](docs/TRAE_ARIS_RUNBOOK_EN.md), [Antigravity](docs/ANTIGRAVITY_ADAPTATION.md), [Copilot CLI](docs/COPILOT_CLI_ADAPTATION.md), Windsurf, or your own agent and the workflows still work. Fork it, rewrite it, adapt it to your stack.
>
> *💡 ARIS is a methodology, not a platform. What matters is the research workflow — take it wherever you go. 🌱*

<p align="center">
  <a href="https://huggingface.co/papers/2605.03042">
    <img src="docs/hf_daily_paper_1.svg" alt="Hugging Face Daily Paper · #1 Paper of the Day" width="360">
  </a>
</p>

[![Technical Report](https://img.shields.io/badge/Technical%20Report-arXiv%3A2605.03042-b31b1b?style=flat&logo=arxiv)](https://huggingface.co/papers/2605.03042) · [![ARIS Intro Slides](https://img.shields.io/badge/ARIS%20Intro%20Slides-PDF-EC1C24?style=flat&logo=adobeacrobatreader&logoColor=white)](docs/aris_intro_slides.pdf) · [![Featured on PaperWeekly](https://img.shields.io/badge/Featured%20on-PaperWeekly-red?style=flat)](https://mp.weixin.qq.com/s/tDniVryVGjDkkkWl-5sTkQ) · [![PaperWeekly — MiniMax-M2.7](https://img.shields.io/badge/PaperWeekly-MiniMax--M2.7-red?style=flat)](https://mp.weixin.qq.com/s/KLFU74lAL2FAIc9K6i1Kqg) · [![Featured in awesome-agent-skills](https://img.shields.io/badge/Featured%20in-awesome--agent--skills-blue?style=flat&logo=github)](https://github.com/VoltAgent/awesome-agent-skills) · [![AI Digital Crew - Project of the Day](https://img.shields.io/badge/AI%20Digital%20Crew-Project%20of%20the%20Day%20(2026.03.14)-orange?style=flat)](https://aidigitalcrew.com) · [💬 Join Community](#-community) · [![Cite](https://img.shields.io/badge/📖_Cite_Us-BibTeX-green?style=flat)](#-citation)

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous ML research workflows. These skills orchestrate **cross-model collaboration** — Claude Code drives the research while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer. 🔀 **Also supports [alternative model combinations](#-alternative-model-combinations) (Kimi, LongCat, DeepSeek, etc.) — no Claude or OpenAI API required.** For example, [MiniMax-M2.7 + GLM-5 or GLM-5 + MiniMax-M2.7](docs/MiniMax-GLM-Configuration.md). 🤖 **[Codex CLI native](skills/skills-codex/)** — full skill set also available for OpenAI Codex. 🖱️ **[Cursor](docs/CURSOR_ADAPTATION.md)** — works in Cursor too. 🖥️ **[Trae](docs/TRAE_ARIS_RUNBOOK_EN.md)** — ByteDance AI IDE. 🚀 **[Antigravity](docs/ANTIGRAVITY_ADAPTATION.md)** — Google's agent-first IDE. 🐙 **[Copilot CLI](docs/COPILOT_CLI_ADAPTATION.md)** — GitHub's terminal agent (native SKILL.md + MCP). 🆓 **[Free tier via ModelScope](docs/MODELSCOPE_GUIDE.md) — zero cost, zero lock-in.**

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

Three safety gates — rebuttal will NOT finalize if any fails:
- 🔒 **No fabrication** — every claim maps to paper/review/user-confirmed result
- 🔒 **No overpromise** — every promise is user-approved
- 🔒 **Full coverage** — every reviewer concern is tracked

Two outputs: `PASTE_READY.txt` (exact char count, paste to venue) + `REBUTTAL_DRAFT_rich.md` (extended version for manual editing).

<details>
<summary><b>Show rebuttal parameters</b> — venue, character limit (required), quick mode, auto experiment, stress test rounds, followup rounds</summary>

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `venue` | `ICML` | Target venue (ICML/NeurIPS/ICLR/CVPR/ACL/AAAI/ACM) |
| `character limit` | — | **Required.** Hard character limit for rebuttal text |
| `quick mode` | `false` | Stop after parsing + strategy (Phase 0-3). See what reviewers want before drafting |
| `auto experiment` | `false` | Auto-run supplementary experiments via `/experiment-bridge` when reviewers ask for new evidence |
| `max stress test rounds` | `1` | How many times GPT-5.4 xhigh stress-tests the draft |
| `max followup rounds` | `3` | Per-reviewer follow-up round limit |

</details>

**After acceptance** — your paper is in, now prepare the presentation:

```
/paper-slides "paper/"     # → Beamer PDF + PPTX + speaker notes + Q&A prep
/paper-poster "paper/"     # → A0/A1 poster PDF + editable PPTX + SVG
```

> *💡 From idea to paper to podium — one toolchain. 🌱*

## 📢 What's New

- **2026-05-17** — ![FIX](https://img.shields.io/badge/FIX-orange?style=flat-square) 🛠 **Tools-stability roadmap (Phase 1+2+3) complete** (closes [#176](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/176) / [#177](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/177) / [#178](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/178)). Community reported that helper scripts weren't propagating into user projects after `install_aris.sh`. **Phase 1** — every SKILL.md caller of the 10 canonical helpers now resolves via the strict-safe 3-layer chain `.aris/tools/` → `tools/` → `$ARIS_REPO/tools/` documented in [`integration-contract.md`](skills/shared-references/integration-contract.md) §2 (which also defines 5 failure policies A/B/C/D1/D2/E). **Phase 2** — new [advisory CI lint](.github/workflows/lint-skills-helpers.yml) catches hardcoded `python3 tools/foo.py` patterns in PR-modified SKILL.md (advisory only, never fails CI). **Phase 3** — three single-owner helpers (`figure-spec`, `paper-illustration-image2`, `experiment-queue`) moved into their SKILL's `scripts/` subdirectory; owner SKILLs use Layer 0 `${CLAUDE_SKILL_DIR}/scripts/` ahead of the canonical chain; legacy `tools/` paths retained as `os.execv` Python forwarding shims. **⚠️ Existing users**: no action needed — legacy `tools/` entries are now shims. If you haven't run `install_aris.sh` since 2026-04-30, one idempotent rerun catches everything up.
- **2026-05-14** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🩹 **`/paper-plan` + `/paper-write` learn `GAP_REPORT.md` + `<!-- DATA_NEEDED -->` discipline** ([#217](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/217)). When `— style-ref:` is set and the user's project has structural assets (`figures/`, `results/`, `NARRATIVE_REPORT.md`, etc.), `/paper-plan` emits a **Gap Report** mapping the exemplar's section topology + density (from `style_profile.md`) against your actual assets — surfacing slots you have **no evidence to fill** (e.g., "exemplar has 3×4 ablation table, you have no ablation data"). Then `/paper-write` writes `<!-- DATA_NEEDED: <Slot ID> — <description> -->` HTML comments **instead of fabricating content** at missing slots — invisible in the compiled PDF, `grep`-friendly for human triage / `/experiment-bridge` follow-up. Narrow carve-out from the "no placeholders" rule, scoped to GAP_REPORT-listed slots only. Original idea by [@zhangpelf](https://github.com/zhangpelf).
<details>
<summary>Earlier updates (2026-03-12 — 2026-05-14, 63 entries)</summary>

- **2026-05-14** — ![BREAKING](https://img.shields.io/badge/BREAKING-purple?style=flat-square) ⚙️ **Default reviewer model: `gpt-5.4` → `gpt-5.5`** across ~30 SKILL.md `REVIEWER_MODEL` defaults. Codex MCP has routed `gpt-5.5` as the default since 2026-04-24; this catches the docs up to runtime. **⚠️ Behavior changes**: (a) `.aris/traces/*` JSONs from prior runs are **not reproducible** — re-runs on 5.5 may emit different `WARN/FAIL` verdicts on borderline cases (reviewer-quality lift, not regression). (b) ChatGPT Plus/Pro monthly quotas drain faster under heavy use. **Fallback**: pass `— reviewer-model: gpt-5.4` per invocation, or pin `REVIEWER_MODEL = gpt-5.4` per skill. Oracle Pro tier (routed via `— reviewer: oracle-pro`) is a separate path and unaffected.
- **2026-05-13** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔍 **[`tools/verify_papers.py`](tools/verify_papers.py) + Pre-Search Verification Protocol — anti-hallucination filter for literature-facing skills**. New helper does 3-layer fallback verification (arXiv batch API up to 40 IDs/request → CrossRef DOI lookup → Semantic Scholar fuzzy title match, default 0.6 word-overlap) and emits 4-state per-paper status (`verified` / `unverified` / `verify_pending` / `error`) plus a top-level verdict aligning with `assurance-contract.md` (`PASS` / `WARN` / `BLOCKED` / `ERROR`). Transient failures (5xx, timeouts, 429) are tagged `verify_pending` and **excluded from the hallucination rate** so network blips don't get conflated with fabricated references. Per-project cache at `<project>/.aris/cache/verify_papers.json` with 30-day TTL; canonical key priority `arxiv:{id_without_version}` → `doi:{lowercase}` → `title:{sha1[:16]}`. New `Pre-Search Verification Protocol` subsection in [`shared-references/citation-discipline.md`](skills/shared-references/citation-discipline.md) makes the split explicit: this protocol is the **fast filter** between SEARCH (Step 1) and full VERIFY (Step 2); `/citation-audit` and `/paper-claim-audit` remain the submission-time audit gates and are not replaced. [`/research-lit`](skills/research-lit/SKILL.md) gets a mandatory `Step 1.5: Verify Candidate Papers` calling the helper; [`/idea-creator`](skills/idea-creator/SKILL.md) and [`/novelty-check`](skills/novelty-check/SKILL.md) add a Key Rule reference for cited Closest Prior Work / landscape entries. Unverified papers are **retained** in output tagged `[UNVERIFIED]` (retention-over-silent-removal) so search-quality issues stay visible. Set `ARIS_VERIFY_EMAIL` in your shell to lift CrossRef to the polite-pool rate. Original signal from [@YiwenZhu77](https://github.com/YiwenZhu77) in [#120](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/120) — landed via clean reimplementation rather than direct merge (PR was 5 weeks old + scope creep into figure-style).
- **2026-05-06** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎤 **[`/paper-talk`](skills/paper-talk/SKILL.md) workflow + [`/slides-polish`](skills/slides-polish/SKILL.md) skill — end-to-end conference talk pipeline**. `/paper-talk` orchestrates paper → slide outline → Beamer + PPTX → per-page polish → assurance audits → final report (sister to `/paper-writing`, `/paper-poster`); composes `/paper-slides`, `/slides-polish`, plus `/paper-claim-audit` + `/citation-audit` when `assurance: conference-ready`. `/slides-polish` is the post-generation visual pass: per-page Codex review against a reference PDF + a fix-pattern catalog (PPTX font scaling 1.5-1.8× for projector-readable size, text-frame resize after font bump, banner-as-tcolorbox, italic style leak guard, em-dash spacing, Chinese EA font hint via PingFang SC, anonymity placeholder discipline). Assurance ladder `draft / polished (default) / conference-ready` is independent from the effort axis; `effort: lite, assurance: conference-ready` is legal and means "fast pipeline, every audit must emit verdict before final". Phase 4 staging adapter materializes slide text + speaker notes + talk script as a synthetic paper directory (`.aris/paper-talk/audit-input/sections/*.tex` + symlinked `.bib` / `results/` / `figures/`) so the existing audits run with their paper-shaped contracts and emit 6-state JSON verdicts per `shared-references/assurance-contract.md`.
- **2026-05-05** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔁 **`/resubmit-pipeline` — Workflow 5: text-only resubmit across venues** ([#208](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/208)). Port a polished paper from one venue to another under hard constraints (no new experiments, no bib edits, no framework changes, never overwrite prior submissions). 5 phases: physical isolation → 5-layer anonymity check → audits (proof / claim / citation `--soft-only`) → microedits via `/auto-paper-improvement-loop --edit-whitelist` with per-round diff gate → adversarial gate via `/kill-argument` → final compile + Overleaf push via `/overleaf-sync`. Two prerequisite SKILL upgrades shipped in the same PR: **`/auto-paper-improvement-loop --edit-whitelist <path>`** (YAML schema with allowed/forbidden paths + `forbidden_operations` like `new_cite` / `new_theorem_env` / `numerical_claim`, `forbidden_deletions`, `requires_user_approval_for`, `max_edits_per_round`) and **`/citation-audit --soft-only`** (translates KEEP/FIX/REPLACE/REMOVE verdicts to text-rewrite proposals when bib is frozen; hallucinated citations get `drop_cite_in_body_only` action). Master `RESUBMIT_REPORT.json` ledger per `shared-references/assurance-contract.md`; 7-verdict failure mode table including `USER_DECISION` runtime state.
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
- **2026-03-14** — 📱 [Feishu/Lark integration](docs/integrations/FEISHU.md): three modes (off/push/interactive), mobile notifications for experiments, reviews, and checkpoints
- **2026-03-13** — 🛑 Human-in-the-loop: configurable `AUTO_PROCEED` checkpoints across all workflows. Full autopilot or step-by-step approval
- **2026-03-12** — 🔗 [Zotero](docs/integrations/ZOTERO.md) + [Obsidian](docs/integrations/OBSIDIAN.md) + local PDFs + arXiv/Scholar: multi-source literature search with cross-model novelty verification
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
codex setup                    # set model to gpt-5.5 when prompted
claude mcp add codex -s user -- codex mcp-server

# 3. Use in Claude Code
claude
> /idea-discovery "your research direction"  # Workflow 1 — be specific! not "NLP" but "factorized gap in discrete diffusion LMs"
> /experiment-bridge                         # Workflow 1.5 — have a plan? implement + deploy + collect results
> /auto-review-loop "your paper topic or scope"  # Workflow 2: review → fix → re-review overnight
> /paper-writing "NARRATIVE_REPORT.md"       # Workflow 3: narrative → polished PDF
> /rebuttal "paper/ + reviews" — venue: ICML    # Workflow 4: parse reviews → draft rebuttal → follow-up
> /resubmit-pipeline "paper/" — venue: NeurIPS  # Workflow 5: port a polished paper to a new venue (text-only, no new experiments)
> /paper-talk "paper/" — venue: ICLR            # Workflow 6: paper → Beamer + PPTX talk + speaker notes + assurance audits
> /research-pipeline "your research direction"  # Full pipeline: Workflow 1 → 1.5 → 2 → 3 end-to-end
> /research-wiki init                           # 📚 Enable persistent research memory (one-time)
> /meta-optimize                                # Meta: analyze usage logs → propose skill improvements
```

<details>
<summary><b>📚 Research Wiki (optional)</b> — one-line init for persistent memory across sessions; see <a href="#-research-wiki--persistent-research-memory">full Research Wiki section</a></summary>

Give ARIS persistent memory across sessions. Papers, ideas, failed experiments — nothing is forgotten:

```bash
# In Claude Code:
> /research-wiki init                         # creates research-wiki/ in your project
# That's it. From now on, /research-lit auto-ingests papers, /idea-creator reads
# the wiki before brainstorming (and writes ideas back), /result-to-claim updates
# claim status. Failed ideas become anti-repetition memory for future ideation.
```

</details>

<details>
<summary><b>🧬 Meta-Optimization (optional)</b> — passive usage logging + /meta-optimize for data-driven SKILL.md improvements; see <a href="#workflow-m-meta-optimize--aris-optimizes-itself">full Workflow M section</a></summary>

Run these in your **normal terminal** (not inside Claude Code) to enable passive usage logging:

```bash
# One-time setup in your project directory
mkdir -p .claude .aris/meta tools/meta_opt
cp Auto-claude-code-research-in-sleep/templates/claude-hooks/meta_logging.json .claude/settings.json
cp Auto-claude-code-research-in-sleep/tools/meta_opt/*.sh tools/meta_opt/
chmod +x tools/meta_opt/*.sh
# Then start Claude Code — hooks are active immediately
claude
```

Events are logged to **both** project-level (`.aris/meta/events.jsonl`) and global (`~/.aris/meta/events.jsonl`) logs. After 5+ workflow runs, run `/meta-optimize` to see data-driven improvement proposals. Use `/meta-optimize --global` to analyze trends across all your projects.

</details>

<details>
<summary><b>📝 Templates + 🔎 DeepXiv + 🔎 Exa + 🗑️ Uninstall</b> — input templates, two extra literature sources, and the uninstall command</summary>

**📝 Templates available!** See [`templates/`](templates/) for ready-to-use input templates for every workflow — [research brief](templates/RESEARCH_BRIEF_TEMPLATE.md) (Workflow 1), [experiment plan](templates/EXPERIMENT_PLAN_TEMPLATE.md) (Workflow 1.5), [narrative report](templates/NARRATIVE_REPORT_TEMPLATE.md) (Workflow 3), [paper plan](templates/PAPER_PLAN_TEMPLATE.md) (Workflow 3).

**🔎 Optional: DeepXiv progressive retrieval**
```bash
pip install deepxiv-sdk
```
Then use [`/deepxiv`](skills/deepxiv/SKILL.md) directly or opt into it from `/research-lit` with `— sources: deepxiv` or `— sources: all, deepxiv`.

**🔎 Optional: Exa AI-powered web search**
```bash
pip install exa-py
export EXA_API_KEY=your-key-here
```
Then use [`/exa-search`](skills/exa-search/SKILL.md) directly or opt into it from `/research-lit` with `— sources: exa` or `— sources: all, exa`. Covers blogs, docs, news, and research papers with built-in content extraction.

**🗑️ Uninstall:** To remove ARIS skills without affecting your own personal skills:
```bash
cd Auto-claude-code-research-in-sleep && ls skills/ | xargs -I{} rm -rf ~/.claude/skills/{}
```

</details>

<details>
<summary><b>Show all 16 inline parameters and 12 override examples</b> — AUTO_PROCEED / sources / arxiv download / DBLP_BIBTEX / code review / wandb / illustration / venue / base repo / gpu / compact / ref paper / effort / reviewer / difficulty (full per-skill defaults live in <a href="#%EF%B8%8F-customization">§ Customization</a>)</summary>

All pipeline behaviors are configurable via inline overrides — append `— key: value` to any command:

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `AUTO_PROCEED` | `true` | Auto-continue at idea selection gate. Set `false` to manually pick which idea to pursue before committing GPU time |
| `human checkpoint` | `false` | Pause after each review round so you can read the score, give custom modification instructions, skip specific fixes, or stop early |
| `sources` | `all` | Which literature sources to search: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, or `all`. Note: `semantic-scholar`, `deepxiv`, and `exa` must be explicitly listed — not included in `all` |
| `arxiv download` | `false` | Download top relevant arXiv PDFs during literature survey. When `false`, only fetches metadata (title, abstract, authors) |
| `DBLP_BIBTEX` | `true` | Fetch real BibTeX from [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) instead of LLM-generated entries. Eliminates hallucinated citations. Zero install |
| `code review` | `true` | GPT-5.4 xhigh reviews experiment code before GPU deployment. Set `false` to skip |
| `wandb` | `false` | Auto-add W&B logging to experiment scripts. Set `true` + configure `wandb_project` in CLAUDE.md. `/monitor-experiment` pulls training curves from W&B |
| `illustration` | `gemini` | AI illustration in Workflow 3: `gemini` (default, needs `GEMINI_API_KEY`), `mermaid` (free), or `false` (skip) |
| `venue` | `ICLR` | Target venue: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`. Determines LaTeX style file and page limit |
| `base repo` | `false` | GitHub repo URL to clone as base codebase (e.g., `— base repo: https://github.com/org/project`). No code? Build on top of an open-source project |
| `gpu` | `local` | GPU target: `local` (default), `remote` (SSH server), or `vast` (rent on-demand from [Vast.ai](https://vast.ai) — auto-provision, auto-destroy) |
| `compact` | `false` | Generate compact summary files (`IDEA_CANDIDATES.md`, `findings.md`, `EXPERIMENT_LOG.md`) for short-context models and session recovery |
| `ref paper` | `false` | Reference paper to build on (PDF path or arXiv URL). Summarized first, then ideas extend/improve it. Combine with `base repo` for paper+code workflows |
| `effort` | `balanced` | Work intensity: `lite` (0.4x tokens), `balanced` (default), `max` (2.5x), `beast` (5-8x). Controls breadth/depth/iterations. Codex reasoning always `xhigh`. See [Effort Levels](#-effort-levels) |
| `reviewer` | `codex` | Reviewer backend: `codex` (GPT-5.4 xhigh, default), `oracle-pro` (GPT-5.4 Pro via [Oracle](https://github.com/steipete/oracle) — strongest reasoning). See [Setup →](#-optional-gpt-54-pro-via-oracle) |
| `difficulty` | `medium` | Reviewer adversarial level: `medium` (default), `hard` (+ memory + debate), `nightmare` (+ GPT reads repo via `codex exec`) |

```
/research-pipeline "your topic" — AUTO_PROCEED: false                          # pause at idea selection gate
/research-pipeline "your topic" — human checkpoint: true                       # pause after each review round to give feedback
/research-pipeline "your topic" — sources: zotero, web                         # only search Zotero + web (skip local PDFs)
/research-pipeline "your topic" — sources: all, deepxiv                        # default sources plus DeepXiv progressive retrieval
/research-pipeline "your topic" — sources: all, exa                            # default sources plus Exa AI-powered web search
/research-pipeline "your topic" — arxiv download: true                         # download top arXiv PDFs during literature survey
/research-pipeline "your topic" — difficulty: nightmare                        # maximum adversarial review before submission
/research-pipeline "your topic" — effort: beast                               # all knobs to maximum — top-venue sprint
/research-pipeline "your topic" — effort: beast, reviewer: oracle-pro         # beast + GPT-5.4 Pro reviewer — ultimate mode
/research-pipeline "your topic" — effort: lite                                # quick exploration, save tokens
/research-pipeline "your topic" — effort: max, review_rounds: 3               # max effort but cap review at 3 rounds
/research-pipeline "your topic" — AUTO_PROCEED: false, human checkpoint: true  # combine options
/proof-checker "paper/" — reviewer: oracle-pro                                # Pro-level proof verification
```

</details>

<details>
<summary><b>Codex MCP config + alternative reviewer routing</b> — pin the model in <code>~/.codex/config.toml</code>; pointers to Codex+Claude-review, Codex+Gemini-review, and the Codex mirror install chain</summary>

**Important:** Codex MCP uses the model from `~/.codex/config.toml`, not from skill files. Make sure it says `model = "gpt-5.5"` (recommended). Other options: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. Run `codex setup` or edit the file directly.

**Want Codex to execute but Claude Code to review?** See [`docs/CODEX_CLAUDE_REVIEW_GUIDE.md`](docs/CODEX_CLAUDE_REVIEW_GUIDE.md). That path installs the base `skills/skills-codex/*`, then overlays `skills/skills-codex-claude-review/*`, and routes review-heavy skills through the local `claude-review` MCP bridge.

**Want Codex to execute but Gemini to review locally?** See [`docs/CODEX_GEMINI_REVIEW_GUIDE.md`](docs/CODEX_GEMINI_REVIEW_GUIDE.md) and [CN](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md). That path installs the base `skills/skills-codex/*`, then overlays `skills/skills-codex-gemini-review/*`, and routes the reviewer-aware predefined skills through the local `gemini-review` MCP bridge using direct Gemini API by default.

**Want the Codex mirror install chain?** Use `tools/install_aris_codex.sh` for managed project installs and `tools/smart_update_codex.sh` for copied Codex installs. The Claude scripts remain the mainline entry points for Claude projects.

</details>

See [full setup guide](#%EF%B8%8F-setup) for details and [alternative model combinations](#-alternative-model-combinations) if you don't have Claude/OpenAI API.

> 🧠 **Smart-update workflow** — git pull + dry-run + apply; detects personal customizations and only updates safe skills.
>
> ```bash
> cd Auto-claude-code-research-in-sleep
> git pull
> bash tools/smart_update.sh          # dry-run: shows what's new/changed/safe
> bash tools/smart_update.sh --apply  # apply: adds new + updates safe ones
> ```
>
> Compares local skills with upstream, detects personal customizations (server paths, API keys, etc.), and only updates skills that are safe to replace. Skills with your personal info are flagged for manual review.

## ✨ Features

- 📊 **74 composable skills** — mix and match, or chain into full pipelines (`/idea-discovery`, `/auto-review-loop`, `/paper-writing`, `/research-pipeline`). See [full catalog →](docs/SKILLS_CATALOG.md)
- 🔍 **Literature & novelty** — multi-source paper search (**[Zotero](docs/integrations/ZOTERO.md)** + **[Obsidian](docs/integrations/OBSIDIAN.md)** + **local PDFs** + arXiv/Scholar) + cross-model novelty verification
- 💡 **Idea discovery** — literature survey → brainstorm 8-12 ideas → novelty check → GPU pilot experiments → ranked report
- 🔄 **Auto review loop** — 4-round autonomous review, 5/10 → 7.5/10 overnight with 20+ GPU experiments
- 📝 **Paper writing** — narrative → outline → figures → LaTeX → PDF → auto-review (4/10 → 8.5/10), one command. Anti-hallucination citations via [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org)
- 🤖 **Cross-model collaboration** — Claude Code executes, GPT-5.4 xhigh reviews. Adversarial, not self-play. Optional: `— reviewer: oracle-pro` → **GPT-5.4 Pro** via [Oracle](https://github.com/steipete/oracle)
- 📝 **Peer review** — review others' papers as a conference reviewer, with structured scoring and meta-review
- 🖥️ **Review-driven experiments** — when GPT-5.4 says "run an ablation", Claude auto-writes the script, rsyncs to GPU, runs in `screen`, collects results, folds back into the paper. Configure server in `CLAUDE.md` ([setup](#%EF%B8%8F-gpu-server-setup-for-auto-experiments)), or rent from [Vast.ai](https://vast.ai) with `gpu: vast`
- 🔀 **Flexible models** — default Claude × GPT-5.4, also supports [GLM, MiniMax, Kimi, LongCat, DeepSeek, etc.](#-alternative-model-combinations) — no Claude or OpenAI API required
- 🛑 **Human-in-the-loop** — configurable checkpoints at key decisions. `AUTO_PROCEED=true` for full autopilot, `false` to approve each step
- 📱 **[Feishu/Lark notifications](docs/integrations/FEISHU.md)** — three modes: **off (default, recommended)**, push-only (webhook → mobile), interactive (approve/reject in Feishu). Zero impact when off

  <details>
  <summary>Preview: Push cards (group) &amp; Interactive chat (private)</summary>

  **Push Only** — group chat cards (experiment done, checkpoint, error, pipeline complete):

  <img src="assets/feishu_push.png" width="700" />

  **Interactive** — private chat with Claude Code (approve/reject, custom instructions):

  <img src="assets/feishu_interactive.jpg" width="700" />

  </details>

- 📚 **[Research Wiki](#-research-wiki--persistent-research-memory)** — persistent knowledge base across papers/ideas/experiments/claims. Failed ideas become anti-repetition memory — ARIS gets smarter every run. Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
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

Real projects where the ARIS pipeline was used end-to-end to produce submitted manuscripts. **This section does not claim official acceptance unless a row explicitly says so:** ratings and quoted verdicts are AI/third-party review signals from tools such as [CSPaper](https://cspaper.org/) and [Stanford Agentic Reviewer](https://paperreview.ai/), not venue decisions. One important caveat: ARIS is designed to optimize through AI-review loops, so elevated AI-review scores are a normal consequence of the workflow rather than independent proof of acceptance. Human reviewers can still bring updated literature knowledge, community context, venue-specific taste, and objections that an AI reviewer did not model. **If you've used ARIS to complete a paper, we'd love to feature it here — open an issue or PR!**

| Paper | AI-review signal | Submission status | Built by | Notes |
|-------|:----------------:|-------------------|----------|-------|
| **CS Paper Submission** | [CSPaper](https://cspaper.org/) **8/10** — AI reviewer recommendation: "Top 50% of accepted papers, clear accept" | Submitted to a CS conference; awaiting official feedback | [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) | Full ARIS pipeline: idea → experiments → auto-review → paper writing. The quote is from CSPaper's simulated review, not an official venue review. |
| **AAAI 2026 Paper Submission** | [Stanford Agentic Reviewer](https://paperreview.ai/) **7/10** — AI reviewer recommendation: "Good paper, accept" | Submitted to AAAI 2026 Main Technical; awaiting official decision | [@xinbo820-web](https://github.com/xinbo820-web) | Pure **Codex CLI** (ARIS-Codex skills). The 7/10 signal comes from an AAAI-style Stanford Agentic Reviewer run, not an official AAAI acceptance result. |
| [UAV-CC](community_papers/UAV-CC.pdf) | Under review | Submitted to IEEE TGRS | [@wxx827](https://github.com/wxx827) | UAV change captioning benchmark. Claude Opus 4.6 (executor) + Codex GPT-5.4 xhigh (reviewer) + Cursor Opus 4.6 (assist). [PDF →](community_papers/UAV-CC.pdf) |

<details><summary>Reviewer screenshots</summary>
<br>
<img src="assets/community_showcase_8_10.png" width="700" alt="8/10 — CS Paper" />
<img src="assets/community_showcase_7_10_codex.png" width="700" alt="7/10 — AAAI 2026, Codex CLI" />
</details>

> *Papers built with ARIS — from idea to submission. Know more? Let us know!*

## 🧩 Awesome Community Skills & Extensions

Domain-specific skills and external projects contributed by the community. PRs welcome — just add a `skills/your-skill/SKILL.md` and open a PR!

> 💡 **How to use:** Community skills are not auto-wired into core workflows. To use one, ask your executor (Claude Code / OpenClaw / etc.) to read the skill's `SKILL.md`, then plug it into the appropriate workflow stage based on the description below.

🎉 **Community Skills (13):** [research-refine](skills/research-refine/SKILL.md) · [experiment-plan](skills/experiment-plan/SKILL.md) · [grant-proposal](skills/grant-proposal/SKILL.md) · [paper-poster](skills/paper-poster/SKILL.md) · [paper-slides](skills/paper-slides/SKILL.md) · [mermaid-diagram](skills/mermaid-diagram/SKILL.md) · [proof-writer](skills/proof-writer/SKILL.md) · [comm-lit-review](skills/comm-lit-review/SKILL.md) · [dse-loop](skills/dse-loop/SKILL.md) · [idea-discovery-robot](skills/idea-discovery-robot/SKILL.md) · [formula-derivation](skills/formula-derivation/SKILL.md) · [paper-illustration](skills/paper-illustration/SKILL.md) · [writing-systems-papers](skills/writing-systems-papers/SKILL.md)

🌐 **External Projects & Docs (13):** [rosetta](https://github.com/SyntaxSmith/rosetta) · [open-source-hardening-skills](https://github.com/zeyuzhangzyz/open-source-hardening-skills) · [CitationClaw](https://github.com/VisionXLab/CitationClaw) · [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) · [paper-to-course](https://github.com/KaguraTart/paper-to-course) · [deep-research-skills](https://github.com/Weizhena/deep-research-skills) · [Antigravity Adaptation Guide](docs/ANTIGRAVITY_ADAPTATION.md) · [OpenClaw Adaptation Guide](docs/OPENCLAW_ADAPTATION.md) · [Cursor Adaptation Guide](docs/CURSOR_ADAPTATION.md) · [Codex+Claude Review Bridge](docs/CODEX_CLAUDE_REVIEW_GUIDE.md) · [Trae Adaptation Guide](docs/TRAE_ARIS_RUNBOOK_EN.md) · [paper-illustration](skills/paper-illustration/SKILL.md) · [MiniMax-AI/cli](https://github.com/MiniMax-AI/cli)

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
<summary><b>🌐 External Projects & Docs (13)</b> — click to expand</summary>

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
| 🔎 [deep-research-skills](https://github.com/Weizhena/deep-research-skills) | General / Web Search | Modular web-search strategy bundle — per-source playbooks for Stack Overflow, GitHub Issues / error-string debugging, Chinese tech communities (CSDN / 掘金 / 知乎 / V2EX / Tencent + Aliyun cloud forums), and general web (Reddit / HN / Dev.to / Medium). Complements ARIS's academic-paper-focused [`/research-lit`](skills/research-lit/SKILL.md) stack with **non-academic** sources useful for debugging, version-compat tracking, and Chinese-language tech search. By [@Weizhena](https://github.com/Weizhena) |

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

<details>
<summary><b>Show W1 flow diagram and example command sequence</b> — research-lit → idea-creator → novelty-check → research-refine → experiment-plan</summary>

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

</details>

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

<details>
<summary><b>Show W1.5 flow diagram</b> — experiment plan → Claude implements → GPT-5.4 code review → sanity check → GPU deploy → monitor → results</summary>

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

</details>

**Skills involved:** `experiment-bridge` + `run-experiment` + `monitor-experiment`

> 💡 **One-command shortcut:** `/experiment-bridge` reads `refine-logs/EXPERIMENT_PLAN.md` automatically. Or point it to any plan: `/experiment-bridge "my_plan.md"`.

> ⚙️ `CODE_REVIEW`, `AUTO_DEPLOY`, `SANITY_FIRST`, `MAX_PARALLEL_RUNS` are configurable — see [Customization](#%EF%B8%8F-customization).

### Workflow 2: Auto Research Loop 🔁 (sleep & wake up to results)

> **"Review my paper, fix what's wrong, repeat until it's good."**
>
> GPT-5.4 reviews → identifies weaknesses → suggests experiments → Claude Code writes scripts, deploys to GPU, monitors results, rewrites the paper — all while you sleep. Just add your [GPU server config](#%EF%B8%8F-gpu-server-setup-for-auto-experiments) to `CLAUDE.md`.

1. 🔍 **Deep review** — GPT-5.4 xhigh reviews the current paper / claims / experiments and identifies weaknesses
2. 🩹 **Fix** — Claude implements the fixes (rewrites sections, adds baselines, or runs new experiments via `/run-experiment`); skips any experiment estimated > 4 GPU-hours and flags it for manual follow-up
3. 📊 **Re-evaluate** — collect results via `/monitor-experiment`, update paper, feed back to the reviewer
4. 🔁 **Repeat** — until score ≥ `POSITIVE_THRESHOLD` (default 6/10) or `MAX_ROUNDS` (default 4) is hit; if context window fills mid-loop, the workflow auto-resumes from `REVIEW_STATE.json`

<details>
<summary><b>Show W2 loop diagram</b> — external review → implement fixes / run experiments → monitor results → repeat until threshold</summary>

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

</details>

**Skills involved:** `auto-review-loop` + `research-review` + `novelty-check` + `run-experiment` + `analyze-results` + `monitor-experiment`

> 💡 **One-command shortcut:** `/auto-review-loop "your paper topic"` runs this entire workflow automatically.

<details>
<summary><b>Show W2 usage examples, reviewer difficulty levels, and full safety guarantees</b> — topic/scope arguments, medium/hard/nightmare, 6 safety rules</summary>

**What to pass as argument?** A short topic or scope is enough — the skill automatically reads your project's narrative docs (`NARRATIVE_REPORT.md`), memory files, experiment results, and prior reviews to build the full context for GPT-5.4. Examples:
- `/auto-review-loop "factorized gap in discrete diffusion LMs"` — broad topic, skill finds everything
- `/auto-review-loop "focus on Section 3-5, our CRF results are weak"` — targeted scope with hints
- `/auto-review-loop` — also works: skill reads project files and infers the topic

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

</details>

> ⚙️ MAX_ROUNDS, score threshold, and GPU limits are configurable — see [Customization](#%EF%B8%8F-customization).

📝 **Blog post:** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### Workflow 3: Paper Writing Pipeline 📝

> **"Turn my research narrative into a submission-ready PDF."** Requires a local LaTeX environment — see [Prerequisites](#prerequisites).

1. 📝 **Narrate** — write `NARRATIVE_REPORT.md` (claims, experiments, results, figure descriptions); see [`templates/NARRATIVE_REPORT_TEMPLATE.md`](templates/NARRATIVE_REPORT_TEMPLATE.md)
2. 🧭 **Plan** — `/paper-plan` builds the claims-evidence matrix + section plan
3. 📊 **Figures** — `/paper-figure` generates data-driven plots and comparison tables from JSON/CSV
4. ✍️ **Write** — `/paper-write` produces section-by-section LaTeX
5. 🔧 **Compile** — `/paper-compile` builds the PDF, fixes errors, runs the page-limit check
6. ✨ **Improve** — `/auto-paper-improvement-loop` runs 2 rounds of GPT-5.4 content review + final format check

<details>
<summary><b>Show W3 architecture diagram and exact writing flow</b> — NARRATIVE_REPORT → /paper-plan → /paper-figure → /paper-write → /paper-compile → improvement loop</summary>

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

</details>

**Skills involved:** `paper-plan` + `paper-figure` + `paper-write` + `paper-compile` + `auto-paper-improvement-loop` + (post-acceptance) `paper-poster` + `paper-slides`

> **One-command shortcut:** `/paper-writing "NARRATIVE_REPORT.md"` runs this entire workflow automatically.

**Input:** A `NARRATIVE_REPORT.md` describing the research: claims, experiments, results, figures. The more detailed the narrative (especially figure descriptions and quantitative results), the better the output.

**Output:** A `paper/` directory with LaTeX source, clean `.bib` (only cited entries), and compiled PDF. The PDF is labelled `submission-ready` **only when** run at `— effort: max | beast` (or explicit `— assurance: submission`) **and** `tools/verify_paper_audits.sh` reports green on the three mandatory audits (`proof-checker`, `paper-claim-audit`, `citation-audit`); see [Assurance Gate](#assurance-gate-effort-max--beast) below. At the default `balanced` level, the output is a reviewed draft.

<details>
<summary><b>Show W3 feature details</b> — Claims-Evidence Matrix, figure modes, clean bib, Gemini API setup, ICLR end-to-end test</summary>

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

</details>

#### Auto Paper Improvement Loop ✨

After Workflow 3 generates the paper, `/auto-paper-improvement-loop` runs 2 rounds of GPT-5.4 xhigh content review → fix → recompile, plus a final format compliance check, autonomously polishing the paper from rough draft to a reviewer-scored draft. Whether the result is tagged `submission-ready` is decided separately by the Phase 6 assurance gate (see [Assurance Gate](#assurance-gate-effort-max--beast)).

<details>
<summary><b>Show auto-paper-improvement benchmark</b> — Score Progression on a real ICLR 2026 theory paper (4/10 → 8.5/10), plus Round 1/2/3 fix details</summary>

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

<details>
<summary><b>Show W4 rebuttal flow diagram</b> — parse reviews → strategy → optional evidence sprint → draft → GPT-5.4 stress test → finalize 2 versions → follow-up rounds</summary>

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

</details>

**Skills involved:** `rebuttal`

> 💡 **Quick mode:** `/rebuttal — quick mode: true` stops after parsing + strategy (Phase 0-3). See what reviewers want before committing to a full draft.

> ⚙️ `VENUE`, `AUTO_EXPERIMENT`, `QUICK_MODE`, `MAX_STRESS_TEST_ROUNDS` are configurable — see [Customization](#%EF%B8%8F-customization).

**Three safety gates — rebuttal will NOT finalize if any fails:**
- 🔒 **Provenance** — every claim maps to paper/review/user-confirmed result. No fabrication.
- 🔒 **Commitment** — every promise is user-approved. No overpromising.
- 🔒 **Coverage** — every reviewer concern is tracked. Nothing disappears.

### Workflow 5: Resubmit Pipeline 🔁 (port a paper to a new venue, text-only)

> **"Paper accepted somewhere or rejected from venue A. Port it to venue B under hard constraints."**

`/resubmit-pipeline` ports a polished paper from one venue to another with strict guardrails — **no new experiments, no bib edits, no framework changes, never overwrites prior submissions**. Use it for journal version of a conference paper, ML venue → other ML venue, anonymized re-submit after a non-anonymous workshop. Not for major revisions (use `/paper-writing` for those).

1. 📁 **Physical isolation** — copy into `<NEW_VENUE_DIR>/`; the original submission directory is never touched.
2. 🛡️ **5-layer anonymity check** — author names, affiliations, self-citations, GitHub / Overleaf URLs, in-text "we" patterns that break double-blind.
3. 🔬 **Audits (soft-only)** — `/proof-checker`, `/paper-claim-audit`, `/citation-audit --soft-only`. The `--soft-only` mode translates `KEEP/FIX/REPLACE/REMOVE` verdicts to text-rewrite proposals when the bib is frozen; hallucinated citations get a `drop_cite_in_body_only` action.
4. ✏️ **Microedit** — `/auto-paper-improvement-loop --edit-whitelist <path>` with a YAML schema (`allowed_paths` / `forbidden_paths` / `forbidden_operations` like `new_cite` / `new_theorem_env` / `numerical_claim`, `forbidden_deletions`, `max_edits_per_round`) + per-round diff gate.
5. 🗡 **Adversarial gate** — `/kill-argument` final attack/adjudication pass; rejection if any `still_unresolved` at critical severity.
6. 📤 **Compile + push** — `/paper-compile` + optional `/overleaf-sync push`.

<details>
<summary><b>Show W5 resubmit flow diagram</b> — isolated copy → 5-layer anonymity → soft-only audits → whitelist microedit → kill-argument adversarial gate → compile + Overleaf push</summary>

```
┌──────────────────────────────────────────────────────────────────────┐
│              Workflow 5: Text-only Resubmit                          │
│                                                                      │
│  Polished paper                                                      │
│       │                                                              │
│       ▼                                                              │
│  Isolate → Anonymity (5-layer) → Audits (--soft-only)                │
│       │                                                              │
│       ▼                                                              │
│  Microedit (whitelist + diff gate) → /kill-argument adversarial gate │
│       │                                                              │
│       ▼                                                              │
│  Compile + Overleaf push     →    <NEW_VENUE_DIR>/                   │
└──────────────────────────────────────────────────────────────────────┘
```

</details>

**Skills involved:** `resubmit-pipeline` (orchestrator), `auto-paper-improvement-loop --edit-whitelist`, `citation-audit --soft-only`, `proof-checker`, `paper-claim-audit`, `kill-argument`, `paper-compile`, `overleaf-sync` (optional)

**Hard constraints (cannot be overridden):**
- 🔒 **No new experiments** — every numerical claim must already exist in the source paper.
- 🔒 **No bib edits** — citation issues become body-text rewrites via `--soft-only`.
- 🔒 **No framework changes** — theorem environment, claim shape, contribution scope are frozen.
- 🔒 **Never overwrites prior submissions** — the new venue gets its own directory.

**Master ledger:** `RESUBMIT_REPORT.json` with the 7-verdict failure-mode table (including `USER_DECISION` runtime state) per `shared-references/assurance-contract.md`. See the [2026-05-05 News entry](#-whats-new) for the full feature breakdown.

### Workflow 6: Conference Talk Pipeline 🎤 (paper → slides → polish → audits)

> **"Paper is in. Now prepare the conference talk."**

`/paper-talk` orchestrates the full talk-prep flow as a sister workflow to `/paper-writing` and `/paper-poster`. `/slides-polish` is the post-generation visual pass invoked internally — you do not need to call it separately.

1. 📋 **Outline** — extract from `paper/` (or `NARRATIVE_REPORT.md`); one slide-cluster per contribution; map sections to talk beats.
2. 🎨 **Generate** — `/paper-slides` produces Beamer source + PPTX + speaker notes + Q&A prep.
3. 💎 **Polish** — `/slides-polish` per-page Codex review against the reference PDF, applying a fix-pattern catalog (PPTX font scaling 1.5-1.8× for projector legibility, text-frame resize after font bump, banner-as-tcolorbox, italic style leak guard, em-dash spacing, Chinese EA font hint via PingFang SC, anonymity placeholder discipline).
4. 🛡️ **Audit** (when `assurance: conference-ready`) — `/paper-claim-audit` + `/citation-audit` run against a synthetic paper directory at `.aris/paper-talk/audit-input/sections/*.tex` + symlinked `.bib` / `results/` / `figures/`. Each emits a 6-state JSON verdict per `shared-references/assurance-contract.md`; non-green blocks the Final Report.

<details>
<summary><b>Show W6 talk-prep flow diagram</b> — paper → outline → /paper-slides → /slides-polish → optional conference-ready audit gate</summary>

```
┌──────────────────────────────────────────────────────────────────────┐
│             Workflow 6: Conference Talk                              │
│                                                                      │
│  paper/  →  outline  →  /paper-slides  (Beamer + PPTX + notes)       │
│                                  │                                   │
│                                  ▼                                   │
│                         /slides-polish  (per-page Codex pass)        │
│                                  │                                   │
│                                  ▼                                   │
│               assurance: conference-ready ?                          │
│                 ├─ yes → /paper-claim-audit + /citation-audit        │
│                 │        on synthetic-paper staging adapter          │
│                 │        → 6-state verdict gates Final Report        │
│                 └─ no  → Final Report directly                       │
└──────────────────────────────────────────────────────────────────────┘
```

</details>

**Skills involved:** `paper-talk` (orchestrator), `paper-slides`, `slides-polish`, `paper-claim-audit` + `citation-audit` (at `assurance: conference-ready`)

**Assurance ladder** (independent from the `effort` axis): `draft / polished (default) / conference-ready`. Legal combination: `— effort: lite, assurance: conference-ready` means "fast pipeline, every audit must emit a verdict before final report."

**Standalone slide / poster tools:** if you only want the artifact and not the full orchestration, `/paper-slides "paper/"` and `/paper-poster "paper/"` work directly without `/paper-talk`. See the [2026-05-06 News entry](#-whats-new) for the full feature breakdown.

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

<details>
<summary><b>Show Research Wiki data model</b> — Paper / Idea / Experiment / Claim entities and the typed graph edges that connect them</summary>

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

</details>

<details>
<summary><b>Show Research Wiki spiral-learning example and manual subcommands</b> — failed ideas → better ideas across 3 rounds; ingest / query / update / lint / stats</summary>

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

</details>

> 🔒 **Safe by design:** All workflow hooks are guarded by `if research-wiki/ exists`. No wiki = no impact. Zero dependencies (pure Python stdlib). You choose when to enable it.

---

### Workflow M: Meta-Optimize 🧬 (ARIS optimizes itself)

> **"Analyze my usage patterns and improve your own skills."**

Unlike Workflows 1–4 which optimize *research artifacts* (papers, code, experiments), Workflow M optimizes the *harness itself* — the SKILL.md instructions, default parameters, and convergence rules that govern how ARIS operates. Inspired by [Meta-Harness](https://arxiv.org/abs/2603.28052) (Lee et al., 2026).

<details>
<summary><b>Show Workflow M one-time setup and usage commands</b> — Claude Code hook install, /meta-optimize variants (project / per-skill / --global / apply)</summary>

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

</details>

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

<details>
<summary><b>Show Workflow M diagram and "what gets optimized" component table</b> — event logs → SKILL.md patches → GPT-5.4 review → user approval; prompts / defaults / convergence / error handling</summary>

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

</details>

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

<details>
<summary><b>Show effort usage examples and per-skill comparison table</b> — command overrides; exact counts for papers / ideas / pilots / rounds / seeds / audit depth at each level</summary>

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

<details>
<summary><b>Show optional Stop-hook hardening snippet</b> — harness-level block (~/.claude/settings.json) that physically prevents session end while the verifier is red</summary>

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

</details>

> 📖 Full specification: [`shared-references/assurance-contract.md`](skills/shared-references/assurance-contract.md)

### 🧿 Optional: GPT-5.4 Pro via Oracle

> **For expert researchers who want the strongest possible reviewer.**

[Oracle](https://github.com/steipete/oracle) unlocks **GPT-5.4 Pro** as an ARIS reviewer — the strongest reasoning model available. Pro excels at deep mathematical proof verification, line-by-line code auditing, and complex experimental design critique.

**Usage rule:** add `— reviewer: oracle-pro` to any reviewer-aware skill (`/research-review`, `/proof-checker`, `/experiment-audit`, `/auto-review-loop`, `/idea-creator`, `/rebuttal`, …).

**Default is always Codex xhigh.** Oracle not installed = zero impact. `— reviewer: oracle-pro` without Oracle installed = graceful fallback to Codex + warning.

<details>
<summary><b>Show Oracle setup commands and per-skill examples</b> — npm install, claude mcp add, API vs browser mode, 6 reviewer-aware skill examples</summary>

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

**Examples — add `— reviewer: oracle-pro` to any skill:**
```bash
/research-review "my draft" — reviewer: oracle-pro          # Pro-level paper critique
/proof-checker "paper/" — reviewer: oracle-pro              # deepest mathematical verification
/experiment-audit — reviewer: oracle-pro                    # Pro audits your eval code
/auto-review-loop "scope" — reviewer: oracle-pro            # Pro stress test each round
/idea-creator "direction" — reviewer: oracle-pro            # Pro evaluates your ideas
/rebuttal "paper/ + reviews" — reviewer: oracle-pro         # Pro stress tests your rebuttal
```

</details>

> 📖 Full specification: [`shared-references/reviewer-routing.md`](skills/shared-references/reviewer-routing.md)

---

## 🧰 Skills Catalog

ARIS ships **74+ skills** across literature, ideation, experiments, audit,
writing, talks, patents, and meta-utilities. The full catalog (with role,
category, and requirements per skill) lives in
**[`docs/SKILLS_CATALOG.md`](docs/SKILLS_CATALOG.md)** to keep this README
scannable.

**Start here for common entry points:**

| Use case | Start here |
|---|---|
| End-to-end research (idea → paper) | [`/research-pipeline`](skills/research-pipeline/SKILL.md) |
| Idea discovery + method refinement | [`/idea-discovery`](skills/idea-discovery/SKILL.md) |
| Run experiments from a plan | [`/experiment-bridge`](skills/experiment-bridge/SKILL.md) |
| Auto review → fix → re-review | [`/auto-review-loop`](skills/auto-review-loop/SKILL.md) |
| Narrative → polished PDF | [`/paper-writing`](skills/paper-writing/SKILL.md) |
| Reply to peer reviews | [`/rebuttal`](skills/rebuttal/SKILL.md) |
| Port a paper to a new venue | [`/resubmit-pipeline`](skills/resubmit-pipeline/SKILL.md) |
| Paper → conference talk | [`/paper-talk`](skills/paper-talk/SKILL.md) |
| Persistent research memory | [`/research-wiki`](skills/research-wiki/SKILL.md) |
| Patent drafting (CN / US / EP) | [`/patent-pipeline`](skills/patent-pipeline/SKILL.md) |
| ARIS optimizes itself | [`/meta-optimize`](skills/meta-optimize/SKILL.md) |

→ **[Browse all 74 skills by category in the full catalog →](docs/SKILLS_CATALOG.md)**

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

No GPU? Rent one from [Vast.ai](https://vast.ai) on demand. ARIS analyzes your training task (model size, dataset, time), finds the cheapest GPU that fits, ranks options by **total cost** (not just $/hr), then rents → runs → collects → destroys automatically.

Drop this in `CLAUDE.md`:

```markdown
## Vast.ai
- gpu: vast                  # rent on-demand GPU from vast.ai
- auto_destroy: true         # auto-destroy after experiment completes (default)
- max_budget: 5.00           # optional: warn if estimated cost exceeds this
```

**📖 Full setup guide → [docs/integrations/VAST_GPU_GUIDE.md](docs/integrations/VAST_GPU_GUIDE.md)** covers:
- Account + `vastai` CLI install + API key + SSH key prerequisites (5 steps)
- How ARIS picks GPUs and shows a live cost-ranked table
- Manual rental via `/vast-gpu` (list / rent / destroy)
- Typical cost expectations (~$0.30-2 for ablations on RTX 4090, ~$2-10 for A100/H100 baselines)
- When `gpu: vast` is preferable to `gpu: remote` / `gpu: local`

**No server at all?** The review and rewriting skills still work without GPU access. Only experiment-related fixes will be skipped (flagged for manual follow-up).

</details>

<details>
<summary><b>📚 Zotero Integration (Optional)</b></summary>

Connect your Zotero library to `/research-lit` — search collections, read your annotations/highlights, export BibTeX, all **before** web search. Recommended MCP: [zotero-mcp](https://github.com/54yyyu/zotero-mcp) (1.8k⭐, semantic search + PDF annotations + BibTeX export).

**📖 Full setup guide → [docs/integrations/ZOTERO.md](docs/integrations/ZOTERO.md)** covers:
- `zotero-mcp` install (Local API for desktop, or Web API)
- API key + user ID setup
- What it enables in `/research-lit` (semantic search, collections, PDF annotations, BibTeX export)
- New default source order: Zotero → Obsidian → local PDFs → web
- Combined Zotero + Obsidian workflow

**Not using Zotero?** `/research-lit` auto-skips and uses local PDFs + web search instead.

</details>

<details>
<summary><b>📓 Obsidian + arXiv Integration (Optional)</b></summary>

Connect your Obsidian vault to `/research-lit` — search your notes, tagged references, and processed insights (often more valuable than raw papers). Recommended MCP: [mcpvault](https://github.com/bitbonsai/mcpvault) (760⭐, no Obsidian app needed). Pairs with Zotero. **arXiv access is built-in — no setup needed**, `/research-lit` queries the arXiv API automatically.

**📖 Full setup guide → [docs/integrations/OBSIDIAN.md](docs/integrations/OBSIDIAN.md)** covers:
- `mcpvault` install (point to vault path, BM25 search, 14 tools)
- Optional [obsidian-skills](https://github.com/kepano/obsidian-skills) (13.6k⭐, by Obsidian CEO) for wikilinks/callouts
- What it enables in `/research-lit` (vault search, tag filter, processed summaries, wikilink traversal)
- Combined Zotero + Obsidian workflow
- arXiv defaults + how to enable PDF download (`— arxiv download: true`)
- Standalone `/arxiv "topic"` and `/arxiv 2301.07041 — download`

**Not using Obsidian?** `/research-lit` auto-skips and works as before. arXiv stays on regardless.

</details>

<details>
<summary><h3>📱 Feishu/Lark Integration (Optional)</h3></summary>

Get mobile notifications when experiments finish, reviews score, or checkpoints need your input — without sitting in front of the terminal.

| Push Only (group cards) | Interactive (private chat) |
|:-:|:-:|
| <img src="assets/feishu_push.png" width="450" /> | <img src="assets/feishu_interactive.jpg" width="450" /> |

**Three modes — choose per-project:**

| Mode | What happens | You need |
|------|-------------|----------|
| **Off** (default) | Nothing. Pure CLI, no Feishu | Nothing |
| **Push only** | Webhook notifications at key events. Mobile push, no reply | Feishu bot webhook URL |
| **Interactive** | Full bidirectional. Approve/reject ideas, reply to checkpoints from Feishu | [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) running |

**📖 Full setup guide → [docs/integrations/FEISHU.md](docs/integrations/FEISHU.md)** covers:
- **Push-only setup (5 min)** — create a group bot, copy the webhook URL, drop `~/.claude/feishu.json`, test with a curl
- **Interactive setup (15 min)** — Feishu Open Platform app, the 5 required permissions (incl. the easy-to-miss `im:message.p2p_msg:readonly`), `feishu-claude-code` bridge install, `screen` deployment
- Card color/content table (Review ≥ 6 → green, < 6 → orange, error → red, etc.)
- Which skills send notifications, push vs. interactive payload per skill
- Common bot-doesn't-reply troubleshooting table
- Alternative IM platforms ([cc-connect](https://github.com/chenhg5/cc-connect), [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu), [lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp))

**Not using Feishu?** Without `~/.claude/feishu.json`, all skills behave exactly as before. Zero overhead, zero side effects.

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

Tune end-to-end behavior: GPU target, arXiv download, code review, human checkpoints, base repo, W&B logging, compact summaries, reference paper, illustration backend, and auto-proceed.

Override inline: `/research-pipeline "topic" — auto proceed: false, illustration: mermaid`

<details>
<summary><b>Show constants, defaults, and pass-through for <code>/research-pipeline</code></b></summary>

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

</details>

### Auto Review Loop (`auto-review-loop`)

Tune stopping criteria: how many review→fix iterations, score threshold to declare submission-ready, and GPU-hour budget above which long experiments get flagged for manual follow-up.

<details>
<summary><b>Show stopping criteria for <code>/auto-review-loop</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_ROUNDS` | 4 | Maximum review→fix→re-review iterations |
| `POSITIVE_THRESHOLD` | 6/10 | Score at which the loop stops (submission-ready) |
| `> 4 GPU-hour skip` | 4h | Experiments exceeding this are flagged for manual follow-up |

</details>

### Idea Discovery (`idea-discovery` / `idea-creator`)

Tune the pilot phase: max hours per pilot, hard timeout, max ideas piloted in parallel, total GPU budget, plus auto-proceed and arXiv download toggles.

Override inline: `/idea-discovery "topic" — pilot budget: 4h per idea, sources: zotero, arxiv download: true`

<details>
<summary><b>Show pilot-budget constants for <code>/idea-discovery</code> and <code>/idea-creator</code></b></summary>

| Constant | Default | Description | Pass-through |
|----------|---------|-------------|:---:|
| `PILOT_MAX_HOURS` | 2h | Skip any pilot estimated to take longer per GPU | — |
| `PILOT_TIMEOUT_HOURS` | 3h | Hard timeout — kill runaway pilots, collect partial results | — |
| `MAX_PILOT_IDEAS` | 3 | Maximum number of ideas to pilot in parallel | — |
| `MAX_TOTAL_GPU_HOURS` | 8h | Total GPU budget across all pilots | — |
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond | — |
| `ARXIV_DOWNLOAD` | false | Download top arXiv PDFs after literature search | → `research-lit` |

</details>

### Experiment Bridge (`experiment-bridge`)

Tune deployment safety: GPT-5.4 code review, auto-deploy after review, sanity-test smallest experiment first, parallel run cap, W&B logging, and base-repo URL.

Override inline: `/experiment-bridge — base repo: https://github.com/org/project`

<details>
<summary><b>Show deployment and safety constants for <code>/experiment-bridge</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `CODE_REVIEW` | true | GPT-5.4 xhigh reviews code before deployment. Catches logic bugs before wasting GPU hours |
| `AUTO_DEPLOY` | true | Automatically deploy experiments after implementation + review. Set `false` to manually inspect |
| `SANITY_FIRST` | true | Run smallest experiment first to catch setup bugs before full deployment |
| `MAX_PARALLEL_RUNS` | 4 | Maximum experiments to deploy in parallel (limited by available GPUs) |
| `WANDB` | false | Auto-add W&B logging. Requires `wandb_project` in CLAUDE.md |
| `BASE_REPO` | false | GitHub repo URL to clone as base codebase for experiments |

</details>

### Literature Search (`research-lit`)

Tune sourcing: local PDF directories, local-scan cap, which sources to search (Zotero / Obsidian / web / Semantic Scholar / DeepXiv / Exa), and arXiv PDF download settings.

Override inline: `/research-lit "topic" — sources: zotero, web`, `/research-lit "topic" — sources: all, deepxiv`, `/research-lit "topic" — sources: all, exa`, `/research-lit "topic" — arxiv download: true, max download: 10`

<details>
<summary><b>Show source-selection and arXiv download constants for <code>/research-lit</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | Local directories to scan for PDFs before searching online |
| `MAX_LOCAL_PAPERS` | 20 | Max local PDFs to scan (first 3 pages each) |
| `SOURCES` | `all` | Which sources to search: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, or `all`. `semantic-scholar`, `deepxiv`, and `exa` must be explicitly listed |
| `ARXIV_DOWNLOAD` | false | When `true`, download top relevant arXiv PDFs to PAPER_LIBRARY after search |
| `ARXIV_MAX_DOWNLOAD` | 5 | Maximum number of PDFs to download when `ARXIV_DOWNLOAD = true` |

</details>

### Paper Writing (`paper-write`)

Tune paper format: real BibTeX from DBLP, target venue (ICLR/NeurIPS/ICML/CVPR/ACL/AAAI/IEEE…), anonymous author block, page limit, and illustration backend.

Override inline: `/paper-write — target venue: NeurIPS, illustration: mermaid`

<details>
<summary><b>Show paper-format and illustration constants for <code>/paper-write</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `DBLP_BIBTEX` | true | Fetch real BibTeX from DBLP/CrossRef instead of LLM-generated entries |
| `TARGET_VENUE` | `ICLR` | Target venue: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_JOURNAL`, `IEEE_CONF` |
| `ANONYMOUS` | true | Use anonymous author block for blind review. Note: most IEEE venues are NOT anonymous — set `false` for IEEE |
| `MAX_PAGES` | 9 | Page limit. ML conferences: main body excl. refs. IEEE: total pages incl. refs |
| `ILLUSTRATION` | `gemini` | AI illustration mode: `gemini` (default, needs `GEMINI_API_KEY`), `mermaid` (free), or `false` (skip) |

</details>

### General (all skills using Codex MCP)

Tune the reviewer model used by every Codex MCP call (default `gpt-5.5`), or fork the SKILL.md to customize prompt templates and the per-skill tool allowlist.

- **Prompt templates** — tailor the review persona and evaluation criteria
- **`allowed-tools`** — restrict or expand what each skill can do

<details>
<summary><b>Show Codex MCP reviewer-model options</b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `REVIEWER_MODEL` | `gpt-5.5` | OpenAI model used via Codex MCP. Also available: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. See [supported models](https://developers.openai.com/codex/models/) for full list. |

</details>

## 🔀 Alternative Model Combinations

Don't have Claude / OpenAI API access? You can swap in other models — same cross-model architecture, different providers.

> ⭐ **We strongly recommend Claude + GPT-5.4 (default setup).** It's the most tested and reliable combination. Alternative setups work but may require prompt tuning.

Beyond the default Claude × GPT-5.4 route, ARIS ships **9 alternative routes (Alt A-I)** covering Z.ai's GLM, Alibaba's Kimi/Qwen/GLM/MiniMax bundle, ModelScope's free DeepSeek-V3.1, Codex-as-executor with Claude or Gemini reviewers, and Google Antigravity as the executor.

<details>
<summary><b>Show full routing table</b> — Default + Alt A-I × executor / reviewer / Claude-API needed / OpenAI-API needed / guide link</summary>

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

</details>

**How to choose:**

- **Default** — you have Claude + OpenAI access and want the most tested route.
- **Alt A** — only swap Claude for GLM, keep GPT-5.4 as reviewer via Codex MCP.
- **Alt B** or **Alt E** — no Claude API, no OpenAI API (Alt E is free via ModelScope).
- **Alt C** or **Alt D** — OpenAI-compatible mix-and-match (Alt D = one Alibaba key for both sides).
- **Alt G** or **Alt I** — Codex stays as executor, only the reviewer changes (Claude or Gemini).
- **Alt H** — Antigravity as the executor (Claude Opus 4.6 or Gemini 3.1 Pro), GPT-5.4 or any `llm-chat` reviewer.

\* Alt G normally relies on local Codex CLI and Claude Code CLI logins. Direct API keys are optional, not required.

<details>
<summary><b>Show detailed provider notes for Alt C/D/E/G/H/I</b></summary>

**Alt C** supports tested providers: GLM (Z.ai), Kimi (Moonshot), LongCat (Meituan) as executors; DeepSeek, MiniMax as reviewers. Any OpenAI-compatible API should also work via the generic [`llm-chat`](mcp-servers/llm-chat/) MCP server.

**Alt D** uses [Alibaba Coding Plan](https://bailian.console.aliyun.com/) — one API key for both executor and reviewer, 4 models included (Kimi, Qwen, GLM, MiniMax).

**Alt E** uses [ModelScope](https://www.modelscope.cn/) — **free** (2000 calls/day), one key, no automation restrictions.

**Alt G** keeps Codex as executor but swaps the reviewer to Claude Code CLI via the local `claude-review` MCP bridge, with async polling for long paper/review prompts.

**Alt H** uses [Google Antigravity](https://antigravity.google/) as the executor with native SKILL.md support — choose Claude Opus 4.6 (Thinking) or Gemini 3.1 Pro (high) as the execution model.

**Alt I** keeps Codex as executor, adds only a thin `skills-codex-gemini-review` overlay, and routes the reviewer-aware predefined skills through the local `gemini-review` MCP bridge with direct Gemini API by default. It is the closest Gemini analogue to the existing Codex+Claude review path, while minimizing skill changes and now also covers poster PNG review via the same bridge. Free-tier availability, rate limits, and data-use terms remain subject to Google's current policy.

</details>

### Alt A: GLM + GPT

Only replace the executor (Claude → GLM via Z.ai), keep GPT-5.4 as reviewer via Codex MCP. Codex CLI reuses your existing `OPENAI_API_KEY` (from `~/.codex/config.toml` or environment); no extra reviewer-side config.

<details>
<summary><b>Show Alt A setup commands and <code>~/.claude/settings.json</code></b></summary>

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
codex setup   # set model to gpt-5.5
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

</details>

### Alt B: GLM + MiniMax

No Claude or OpenAI API needed. Uses a custom MiniMax MCP server instead of Codex (because MiniMax doesn't support OpenAI's Responses API). Full guide: [`docs/MINIMAX_MCP_GUIDE.md`](docs/MINIMAX_MCP_GUIDE.md).

### Alt C: Any Executor + Any Reviewer

Mix and match freely using the generic `llm-chat` MCP server. Supports any OpenAI-compatible API as reviewer. Full guide: [`docs/LLM_API_MIX_MATCH_GUIDE.md`](docs/LLM_API_MIX_MATCH_GUIDE.md).

Example combinations: GLM + DeepSeek, Kimi + MiniMax, Claude + DeepSeek, LongCat + GLM, etc.

### After Setup: Install Skills & Verify

Use the project-local symlink install from [§ Install Skills above](#install-skills) — that's the recommended path for all routes. The global-copy fallback below also works if you prefer everything under `~/.claude/skills/`.

<details>
<summary><b>Show global-copy fallback install commands and the non-Claude executor verification prompt</b></summary>

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

</details>

> ⚠️ **Note:** Alternative models may behave differently from Claude and GPT-5.4. You may need to tune prompt templates for best results. The core cross-model architecture remains the same.

## 💬 Community

**Domain-specific skills welcome!** The core skills cover general research workflows, but every field has its own tools and patterns. We welcome PRs that add new skills for your domain — EDA, bioinformatics, robotics, HPC, or anything else. Just add a `skills/your-skill/SKILL.md` and open a PR. See [`dse-loop`](skills/dse-loop/SKILL.md) for an example.

Join the WeChat group for discussion on Claude Code + AI-driven research workflows:

<img src="docs/wechat_group.jpg" alt="WeChat Group QR Code" width="300">

## 📖 Citation

If you use ARIS in your research, please cite:

```bibtex
@article{yang2026aris,
  title={ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration},
  author={Yang, Ruofeng and Li, Yongcan and Li, Shuai},
  journal={arXiv preprint arXiv:2605.03042},
  year={2026}
}
```

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260328)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## 🙏 Acknowledgements

**Inspired by** — 🧪 [AI Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana) · 📖 [AutoResearch](https://github.com/karpathy/autoresearch) (Karpathy) · 🔭 [FARS](https://analemma.ai/blog/introducing-fars/) (Analemma) · 🎨 [PaperBanana](https://github.com/dwzhu-pku/PaperBanana) (PKU).

**Core infra** — [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (execution backbone) · [Codex CLI](https://github.com/openai/codex) (cross-model review via MCP).

**Integrations** — **Zotero** ([guide](docs/integrations/ZOTERO.md)): [zotero-mcp](https://github.com/54yyyu/zotero-mcp), [Zotero](https://www.zotero.org/). **Obsidian** ([guide](docs/integrations/OBSIDIAN.md)): [mcpvault](https://github.com/bitbonsai/mcpvault), [obsidian-skills](https://github.com/kepano/obsidian-skills) (by Obsidian CEO [Steph Ango](https://github.com/kepano)). **Feishu/Lark** ([guide](docs/integrations/FEISHU.md)): [feishu-claude-code](https://github.com/joewongjc/feishu-claude-code), [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu), [cc-connect](https://github.com/chenhg5/cc-connect), [lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp).

**Paper-writing inspiration** — [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) · [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) · [baoyu-skills](https://github.com/jimliu/baoyu-skills). **Community** — [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) (featured).

**Platform adaptation** — 🤖 [@Falling-Flower](https://github.com/Falling-Flower) (Codex CLI adaptation via `spawn_agent`) · 🔧 [@No-518](https://github.com/No-518) (Codex skill maintenance) · 🖱️ [@YecanLee](https://github.com/YecanLee) ([Cursor guide](docs/CURSOR_ADAPTATION.md) + local GPU docs) · 🏆 [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) (first ARIS community paper, CS conference 8/10).

**Architecture & vision** — 💡 [@JingxuanKang](https://github.com/JingxuanKang): beyond code (training-check, result-to-claim, ablation-planner, watchdog, templates, session recovery), deeply shaped ARIS through discussions on compact mode, workflow state management, and the vision of autonomous research — many of today's core features (structured project files, context-aware session recovery) grew out of these conversations.

## License

MIT
