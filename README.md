# 🌙 ARIS-Code — Auto Research in Sleep

```
    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
    ░  █████╗ ██████╗ ██╗███████╗            ░
    ░ ██╔══██╗██╔══██╗██║██╔════╝            ░
    ░ ███████║██████╔╝██║███████╗            ░
    ░ ██╔══██║██╔══██╗██║╚════██║            ░
    ░ ██║  ██║██║  ██║██║███████║            ░
    ░ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝           ░
    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
         🟦 [Claude]    🟩 [GPT 🕶️]
         executor  ←→  reviewer
         Let AI do research while you sleep
```

![ARIS-Code Screenshot](docs/screenshot.png)

> **Adversarial · Multi-Agent Research Automation CLI**
> Executor acts · Reviewer critiques · Iterate to excellence

[![GitHub Release](https://img.shields.io/github/v/release/wanshuiyin/Auto-claude-code-research-in-sleep?style=flat-square)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20|%20Linux%20|%20Windows-black?style=flat-square)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)


## 📰 What's New

> **v0.4.9** (2026-05-17) — **Closes Codex v0.4.7 audit residuals (L1+L3+L4)** + skill-helper subsystem completion. **L1**: `tools` crate also switches reqwest to `native-tls`, unifying TLS across all 3 reqwest consumers (DashScope-class endpoints now work on the LlmReview reviewer path too, not just main executor). Linux CI installs OpenSSL dev headers. **L3**: ApiClient trait gains `on_session_compacted()`; OpenAI's message-index-keyed reasoning_cache is cleared on auto-compaction so post-compaction replay doesn't aim at stale indices. **L4**: split `supports_reasoning_content_replay` predicate (superset includes Kimi/Moonshot/Xiaomi-MiMo/DeepSeek-R1 — providers that emit reasoning_content but don't accept reasoning_effort) + 32K char per-turn cap + 128K char total-cache cap with oldest-eviction. Plus: 2 new skills bundled (`/figure-spec` + `/paper-illustration-image2` with `scripts/` subdirs, new resolver Layer 0b = `$ARIS_CACHE_DIR/skills/<name>/scripts/`); `research_wiki.py` promoted from skill-local to shared `tools/` (9+ callers); 5 more SKILL.md migrated to fallback chain (`exa-search`, `semantic-scholar`, `arxiv`, `idea-creator`); inventory cargo test + smoke shell script for H6 regression class.

> **v0.4.8** (2026-05-17) — **Skill helper subsystem rewrite** + **two community bug fixes**. Bundled helpers now extract to `~/.config/aris/cache/<version>/` at startup (not cwd); every Skill invocation surfaces a `helperReport` with cache dir + 4-layer resolver preamble. `/skills export` ships helpers alongside SKILL.md. New `integration-contract.md` defines 6 failure policies (A gate / B side-effect / C forensic / D1 cascade / D2 multi-source / E diagnostic). 8 shared helpers (arxiv/deepxiv/exa/S2/openalex fetchers + save_trace + verify_papers + verify_paper_audits) bundled. `/research-lit` + `/deepxiv` SKILL.md migrated to fallback chain. Fixes: (a) `gpt-5.5 + tools 400` on OpenAI (executor stripped of `reasoning_effort` for gpt-5.5/o3/o4+tools on api.openai.com), (b) Custom reviewer reset-to-gpt-5.5 every restart (`/setup` menu option 9 vs 8 bug + `LlmReview` no longer falls back to gpt-5.5 for Custom).

> **v0.4.7** (2026-05-16) — **DashScope Coding Plan 405 fixed** (#159) via `native-tls` switch — credit [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#225) | **`reasoning_content` replay for all reasoning models** (OpenAI o1/o3/o4 / DeepSeek-R1 / etc.), not just Kimi — pairs with v0.4.5 `reasoning_effort='xhigh'` for coherent multi-turn reasoning — credit [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#226) | Cleanup: removed 600+ lines of `rusty-claude-cli` prototype dead code (`app.rs` / `args.rs` / `runtime/sse.rs`) + unused `rustyline` dep + "Claw Code" → "ARIS-Code" rebranding in user-facing strings.

> **v0.4.6** (2026-05-14) — **🚨 Two long-standing silent bugs fixed**: (1) `PermissionMode::Prompt` was *silently allowing every tool* due to derived-`Ord` bug, now correctly routes through the prompter; (2) system prompt hard-coded `current_date = "2026-03-31"`, causing models to reject real post-March-2026 data (including users' own arXiv papers) as "future / prompt injection" — now uses real system time via new `runtime::today_iso()`. Plus **Custom OpenAI-compatible provider** (`/setup` option 11, reviewer option 9) with dynamic `/models` discovery — credit [@Anduin9527](https://github.com/Anduin9527) (#221 + #222).

> **v0.4.5** (2026-05-13) — **First-class reasoning-model support** — `reasoning_effort='xhigh'` actually on the wire for GPT-5.5 / o1 / o3 / o4 / DeepSeek-thinking | **Thinking content blocks** end-to-end (fixes #161) | **Multi-tool result grouping** fix (`tool_use_ids_without_tool_result`) | **DeepSeek V4 Pro** + **Xiaomi MiMo** + **Qwen 3.6** + **Doubao** in `/setup` (options 7-10) | **Claude Code object-style hooks** parser | Default model bumped to **Claude Opus 4.7 + GPT-5.5** | REPL input hardening: multi-line wrap no longer duplicates, Cmd+V multi-line paste no longer auto-submits, CJK chars at wrap boundary render correctly | CI workflow added | Credits: [@GO-player-hhy](https://github.com/GO-player-hhy) (#186), [@Jxy-yxJ](https://github.com/Jxy-yxJ) (#171), [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#216 partial)

> **v0.4.4** (2026-04-20) — **`/setup` no longer forces Bearer mode for Anthropic + custom URL** (fixes ModelScope / Claude-Code proxies like `code.newcli.com`) | Provider-aware proxy URL hints in `/setup` (OpenRouter / DeepSeek / DashScope / ModelScope / ...) | Stale state no longer leaks across provider switches | Custom base URL preserved across `/setup` re-runs | LlmReview falls back to configured reviewer when executor guesses a wrong model | Fixes #158, #162

> **v0.4.3** (2026-04-17) — **Third-party Anthropic-compat proxy support** (Bedrock etc.) — skip beta flags that proxies reject | Propagate custom base URL to `anthropic` provider (not just `anthropic-compat`) | Credit [@screw-44](https://github.com/screw-44)

> **v0.4.2** (2026-04-17) — **Auto-compaction corruption fix** (no more empty streams after skill runs) | Compaction summary preserved on OpenAI-compat executors | Custom executor base URL now applied after mid-launch setup | Shell-provided API keys no longer erased on launch | `EXECUTOR_BASE_URL` trim + empty handling

> **v0.4.1** (2026-04-15) — Reviewer/executor retries (429, 5xx, network) | Stale interrupt flag fix | Fresh HTTP client per reviewer call | Verbose error chains
>
> **v0.4.0** (2026-04-15) — **Plan mode** (`/plan`) | Cooperative Ctrl+C interrupt | API errors no longer exit REPL | Tool output folding | 62 skills synced
>
> <details><summary>Previous versions</summary>
>
> **v0.3.9** (2026-04-11) — Proxy/custom base URL | Local models (LM Studio/Ollama) | Research Wiki | Meta-Optimize | Atomic sessions | Bash safety | Windows (experimental)
>
> **v0.3.5** (2026-04-08) — Research Wiki | Meta-Optimize self-evolution | Atomic session writes | Bash safety | Windows support
>
> **v0.3.3** (2026-04-04) — Fix all config loading crashes for Claude Code hooks compatibility
>
> **v0.3.0** (2026-04-03) — Multi-file memory index | Rich task system (TodoWrite) | `/plan` | Security hardening
>
> **v0.2.2** (2026-04-03) — `/plan` step-by-step planning | `/tasks` persistent tracking
>
> **v0.2.1** (2026-04-03) — Persistent Memory | Kimi K2.5 multi-turn fix | CJK cursor fix
>
> **v0.2.0** (2026-04-02) — Open source | Kimi + MiniMax + GLM | Smart LlmReview routing | CI/CD
>
> **v0.1.0** (2026-04-02) — Initial release | Multi-executor & reviewer | 42 bundled skills
>
> </details>
>
> [Full Changelog →](CHANGELOG.md)


---

## ✨ What is ARIS-Code?

**ARIS-Code** (*Auto Research in Sleep*) is a terminal-based AI research assistant built for academic researchers. Its core philosophy:

- 🤖 **Executor**: The primary LLM — writes code, surveys literature, drafts papers, plans experiments
- 🔍 **Reviewer**: An independent LLM that adversarially critiques the Executor's output via the `LlmReview` tool
- 🔄 **Iterate**: Executor writes → Reviewer critiques → Executor revises → loop until quality converges

With **42 bundled research skills**, ARIS covers the full pipeline from idea discovery to paper submission.

---

## 🚀 Installation

**macOS (Apple Silicon)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-darwin-arm64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**macOS (Intel)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-darwin-x64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**Linux (x64)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-linux-x64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**Windows (x64)**
Download [`aris-code-windows-x64.zip`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-windows-x64.zip), extract, and run `aris.exe` in PowerShell or Windows Terminal.

> Run `aris` to start. First launch triggers the interactive setup wizard.

---

## ⚙️ First-Run Setup

The first time you run `aris`, an interactive setup wizard launches automatically:

```
🌙 ARIS-Code Setup Wizard

[1/3] Choose Executor provider (primary LLM)
  > Anthropic Claude
    OpenAI GPT
    Google Gemini
    Zhipu GLM
    MiniMax
Enter API Key: sk-...

[2/3] Choose Reviewer provider (adversarial LLM)
  > OpenAI GPT
    Google Gemini
    Zhipu GLM
    MiniMax
Enter API Key: sk-...

[3/3] Choose language preference
    中文 (CN)
  > English (EN)

✅ Config saved to ~/.config/aris/config.json
```

After setup you drop straight into the REPL. Run `/setup` at any time to reconfigure without restarting.

---

## 🤖 Supported Providers

| Provider | As Executor | As Reviewer | Key Models |
|----------|:-----------:|:-----------:|-----------|
| 🟣 Anthropic Claude | ✅ | — | claude-opus, claude-sonnet, claude-haiku |
| 🟢 OpenAI | ✅ | ✅ | gpt-5.4, gpt-5.4-mini, gpt-5.4-nano |
| 🔵 Google Gemini | ✅ | ✅ | gemini-2.5-pro, gemini-2.5-flash |
| 🔶 Zhipu GLM | ✅ | ✅ | GLM-5, GLM-5-Turbo |
| 🔷 MiniMax | ✅ | ✅ | MiniMax-M2.7, MiniMax-M2.7-highspeed |

> **Design note**: Anthropic Claude is Executor-only; all other providers can serve as both Executor and Reviewer. The classic pairing is **Claude Executor + GPT/GLM Reviewer** for true adversarial multi-agent research.

---

## 🎯 Key Features

### 1. 🔄 Adversarial Multi-Agent Architecture

```
User input
    ↓
[Executor LLM]  ──── calls ────→  LlmReview Tool
  write / code                         ↓
  research / analyze             [Reviewer LLM]
    ↑                             independent critique
    └──────── review feedback ───┘
              iterate until quality target met
```

**LlmReview in action**:

```
❯ Please review this paper for me
# ARIS reads the paper, calls LlmReview to get GPT-5.4/GLM-5/MiniMax's
# independent assessment — multi-round adversarial dialogue ensues

❯ Use LlmReview to say hello to the reviewer
# Direct LlmReview tool invocation
```

### 2. 📚 42 Bundled Research Skills

Use `/skills` to list all available skills:

```
/research-lit        — Literature search & survey
/idea-discovery      — Full idea discovery pipeline
/research-review     — GPT xhigh deep review
/paper-write         — LaTeX paper drafting
/paper-compile       — Paper compilation & error fixing
/auto-review-loop    — Autonomous multi-round review loop
/experiment-plan     — Experiment roadmap generation
/run-experiment      — Remote GPU deployment
/peer-review         — Conference reviewer simulation
/rebuttal            — Submission rebuttal generation
...  (42 total)
```

**Three-tier skill priority** (higher overrides lower):
```
~/.config/aris/skills/   [user custom — highest priority]
~/.claude/skills/        [Claude Code compatible]
bundled skills           [42 out-of-the-box skills]
```

### 3. 🖥️ REPL Commands

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/model` | Switch Executor model |
| `/reviewer` | Switch Reviewer model |
| `/permissions` | Toggle permission mode (allow / deny / ask) |
| `/setup` | Reconfigure without restarting |
| `/skills` | List / show / export skills |
| `/status` | Show current configuration |
| `/cost` | Token usage & cost summary |
| `/compact` | Compress conversation history |
| `/clear` | Clear the screen |
| `/version` | Version info |
| `/research-review` | Invoke research review skill directly |
| `/paper-write` | Invoke paper writing skill directly |
| `...` | All 42 skill slash commands |

### 4. 🌐 Language Preference

Your chosen language (CN/EN) is injected into the system prompt so ARIS always responds in your preferred language — no per-message configuration needed.

### 5. 🛡️ Anti-Hallucination Design

The system prompt explicitly informs the model of its exact identity (ARIS-Code), preventing role confusion in multi-agent scenarios where the Executor and Reviewer are different models from different providers.

---

## 📖 Usage Examples

### Literature Survey
```
❯ /research-lit find the latest work on diffusion models for protein design
```

### Autonomous Review Loop
```
❯ /auto-review-loop
# ARIS reads the paper in the current directory and runs:
# draft → review → revise → review → ... until quality converges
```

### Switch Executor Model
```
❯ /model
  Current Executor: claude-sonnet-4-5
  Switch to:
  > claude-opus-4
    gpt-5.4
    gemini-2.5-pro
```

### Switch Reviewer
```
❯ /reviewer
  Current Reviewer: gpt-5.4
  Switch to:
  > glm-5
    gemini-2.5-pro
    minimax-m2.7
```

### Direct Adversarial Review
```
❯ Review my method section — be brutal
# Executor reads the section, calls LlmReview,
# receives an independent adversarial critique, and iterates
```

---

## 📁 Configuration

```
~/.config/aris/
├── config.json        # Main config (provider, API keys, language)
└── skills/            # Custom user skills (override bundled skills)
```

**Example config.json**:
```json
{
  "executor": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-5",
    "api_key": "sk-ant-..."
  },
  "reviewer": {
    "provider": "openai",
    "model": "gpt-5.4",
    "api_key": "sk-..."
  },
  "language": "EN"
}
```

---

## 🗺️ Roadmap

- [x] Phase 0: Rust fork foundation (based on claw-code)
- [x] Phase 1: Multi-provider support (Anthropic / OpenAI / Gemini / GLM / MiniMax)
- [x] Phase 1: LlmReview adversarial critique tool
- [x] Phase 1: 42 bundled research skills
- [x] Phase 1: Language preference & anti-hallucination system prompt
- [ ] Phase 2: Skills system polish (three-tier priority UI)
- [ ] Phase 2: Web UI dashboard
- [ ] Phase 3: Linux / Windows support
- [ ] Phase 3: Local model integration (Ollama)

---

## 🙏 Credits & Acknowledgements

**ARIS-Code is built on the excellent foundation of [claw-code](https://github.com/ultraworkers/claw-code).**

claw-code is an open-source Rust reimplementation of Claude Code. It provided the REPL framework, tool-calling infrastructure, and cross-platform compilation that made ARIS-Code possible. Huge thanks to the ultraworkers team for their outstanding work!

- 🔗 claw-code: https://github.com/ultraworkers/claw-code
- 🔗 ARIS-Code: https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep

---

## 📄 License

MIT License © 2025 ARIS-Code Contributors

---

<div align="center">
  <sub>🌙 Let AI do research while you sleep · Built with ❤️ and Rust</sub>
</div>

