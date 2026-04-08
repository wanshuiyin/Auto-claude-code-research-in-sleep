# ARIS-Code Changelog

## Unreleased

- **Custom OpenAI-compatible provider**: Added a single `custom` provider for both Executor and Reviewer.
- **Dynamic model discovery**: Custom setup, `/model`, and `/reviewer` now fetch model ids from `/models` instead of asking users to type them manually.
- **Custom reviewer routing**: `LlmReview` now respects `ARIS_REVIEWER_PROVIDER=custom` and sends requests directly to the configured endpoint.

## v0.3.5 (2026-04-08)

- **New**: **Research Wiki** — persistent research knowledge base with papers, ideas, experiments, claims, and typed relationship graph. Python helper with auto-fallback to direct LLM execution.
- **New**: **Bundled helper resources** — `build.rs` now embeds `.py`/`.sh` files alongside SKILL.md, auto-extracted on first invocation.
- **New**: Skills integration — `idea-creator`, `research-lit`, `result-to-claim` now auto-ingest to research-wiki when it exists (skip silently if not).

## v0.3.4 (2026-04-08)

- **New**: **Workflow M: Meta-Optimize** — ARIS can now optimize its own skills based on usage patterns. Passive event logging (`ARIS_META_LOGGING=metadata`), usage analysis, LlmReview-gated patch proposals, and safe `/meta-optimize apply N` with Rust-enforced path validation.
- **New**: **EventSink** — pluggable runtime event logging (tool calls, skill invocations, user prompts). Three levels: `off` (default), `metadata`, `content`.
- **New**: **Session atomic writes** — sessions now saved via temp file + rename to prevent data loss on crash. Files exceeding 256 KB are automatically rotated (3 archives).
- **New**: **Bash command pre-validation** — dangerous patterns (`rm -rf /`, `sudo rm`, `mkfs`, fork bombs) are blocked before execution.
- **New**: **Windows support (experimental)** — CI now builds `aris-code-windows-x64.zip` via GitHub Actions.
- **Fix**: Skill resolution now searches `~/.config/aris/skills/` (highest priority), fixing split-brain between `/skills export` and the Skill tool.
- **Security**: Symlink rejection added to skill loader (same as memories). Path traversal (`..`, `/`) blocked in skill names. Reviewer independence protocol bundled.
- **New**: **Research Wiki** — persistent research knowledge base (papers, ideas, experiments, claims + relationship graph). Python helper auto-extracted with fallback to direct LLM execution if Python unavailable.
- **New**: **Bundled helper resources** — `build.rs` now embeds `.py`/`.sh` files alongside SKILL.md. Skills can ship deterministic helper scripts.

## v0.3.3 (2026-04-04)

- **Fix**: Catch config loading errors in ALL code paths (system prompt + runtime config). Users with incompatible Claude Code hooks settings no longer crash — ARIS shows a warning and continues with defaults.

## v0.3.2 (2026-04-04)

- **Fix**: Gracefully handle incompatible Claude Code hooks configuration (PreToolUse object format). Now falls back to default config instead of crashing.
- **Fix**: Install instructions now include `chmod +x` to fix `permission denied` on first run.

## v0.3.1 (2026-04-04)

- **Fix**: StructuredOutput tool schema now compatible with OpenAI API (added missing `properties` field). Previously caused `400 Bad Request` when using OpenAI/Kimi as executor.

## v0.3.0 (2026-04-03)

- **Multi-file Memory Index**: Memories now stored as individual files in `~/.config/aris/memories/` with YAML frontmatter. System prompt gets a catalog (name + description), model loads specific memories on demand via read_file. Old `memory.md` auto-migrated.
- **Rich Task System (TodoWrite)**: Tasks now use the structured TodoWrite tool with JSON storage (`~/.config/aris/tasks.json`). Supports pending/in_progress/completed status. `/tasks` shows formatted task list.
- **Security hardening**: Symlink rejection in memory directory, prompt injection sanitization for memory fields.

## v0.2.2 (2026-04-03)

- **`/plan` command**: Create step-by-step research plans before executing. Model presents numbered steps and waits for confirmation.
- **`/tasks` command**: Persistent task tracking via `~/.config/aris/tasks.md`. Auto-managed by the model with `- [ ]` / `- [x]` checklist format. Use `/tasks` to view, `/tasks clear` to reset.

## v0.2.1 (2026-04-03)

- **Persistent Memory**: ARIS now remembers context across sessions via `~/.config/aris/memory.md`. Say "remember this" and it persists. No extra setup needed.
- **Kimi K2.5 thinking mode fix**: Multi-turn tool calls now work correctly with Kimi's reasoning mode (reasoning_content preserved and replayed).
- **CJK cursor fix**: Chinese/Japanese/Korean input cursor positioning now correct in the REPL.
- **Banner box frame**: Startup banner wrapped in a clean box frame (like Claude Code).

## v0.2.0 (2026-04-02)

- **Open source release** on `aris-code` branch.
- **CI/CD**: GitHub Actions auto-builds for macOS ARM64, macOS x64, Linux x64.
- **Kimi K2.5 support**: New executor/reviewer provider via Moonshot API.
- **MiniMax M2.7**: OpenAI-compat endpoint (`api.minimax.chat/v1`).
- **GLM-5**: Zhipu AI via OpenAI-compat endpoint.
- **Smart LlmReview routing**: Routes by model name (gemini/glm/minimax/kimi/openai), not by which API key exists.
- **Expanded setup**: 6 executor providers, 6 reviewer providers, auto-set best model per provider.
- **Language setting**: CN/EN preference in setup, injected into system prompt.

## v0.1.0 (2026-04-02)

- **Initial release** (macOS ARM64 only).
- **Multi-executor**: Anthropic Claude / OpenAI / Gemini / GLM / MiniMax.
- **Multi-reviewer**: LlmReview tool for adversarial cross-model review.
- **42 bundled research skills**: paper-write, research-review, auto-review-loop, etc.
- **Interactive setup**: `aris` first-run wizard, persistent config at `~/.config/aris/config.json`.
- **Runtime switching**: `/model`, `/reviewer`, `/permissions` interactive menus.
- **Customizable skills**: `/skills list|show|export`, three-tier priority (ARIS > Claude > bundled).
- **Pixel art banner**: Claude (blue) and GPT (green/sunglasses) characters.
- **Anti-hallucination**: System prompt includes exact model identity.
- **UI improvements**: `●` indicators, `❯` prompt, turn separators, compact tool display.
- Based on [claw-code](https://github.com/ultraworkers/claw-code) Rust version.
