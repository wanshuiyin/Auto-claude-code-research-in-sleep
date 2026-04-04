# ARIS-Code Changelog

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
