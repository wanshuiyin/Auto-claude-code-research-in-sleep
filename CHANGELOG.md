# ARIS-Code Changelog

## v0.4.4 (2026-04-20)

Setup UX + reviewer-routing fixes surfaced by issues [#158](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/158) and [#162](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/162) (Claude / ModelScope third-party proxies returning "暂不支持" / 403).

- **Fix**: **`/setup` no longer forces Anthropic custom-URL users into Bearer mode** — previously, picking "Anthropic" + entering a custom base URL auto-switched the provider to `anthropic-compat` (Bearer token), which made `x-api-key`-only proxies (ModelScope, Claude-Code-compatible proxies like `code.newcli.com/claude`) unreachable. Now those users stay on `provider=anthropic` and ARIS sends `x-api-key` — matching how vanilla Claude Code authenticates against the same proxies. Users who genuinely need Bearer mode and were already on `anthropic-compat` are preserved across re-runs of `/setup` (no silent downgrade).
- **Fix**: **Stale state leaking across provider switches in `/setup`** — switching the executor menu from Kimi → OpenAI (etc.) would keep the old provider's API key under the new env var, and the old base URL ("https://api.moonshot.cn/v1") would be shown as the new provider's "default". Same issue on the reviewer side (Kimi reviewer URL persisted after switching to OpenAI reviewer). Menu-option change now clears `executor_api_key` (and for reviewer also `reviewer_api_key` + `reviewer_base_url`). Detection compares the concrete menu choice, not just `executor_provider`, because OpenAI/Gemini/GLM/MiniMax/Kimi all serialize as `"openai"`.
- **Fix**: **Custom base URL silently wiped on `/setup` re-run** — previously, re-entering setup with the same menu option would overwrite `executor_base_url` with the provider's built-in default, nuking any custom URL the user had saved (e.g. an OpenRouter or newcli.com proxy). Base URL is now only overwritten when the user actually switches menu options.
- **Fix**: **LlmReview silently failed when executor guessed wrong `model`** — the tool's description only listed `OpenAI/Gemini/GLM/MiniMax` (no Kimi, no Anthropic), so a Kimi-executor would call LlmReview with `model="gpt-4o"`, route to the unset `OPENAI_API_KEY`, and fail. `resolve_reviewer_model()` now falls back to the user's configured reviewer model when (a) the requested model's API key is missing, or (b) the requested model routes to a different provider than the configured reviewer. Provider consistency is derived from `configured_model`, not `ARIS_REVIEWER_PROVIDER` — so `/reviewer <model>` works correctly even if it doesn't re-sync the provider env var. Tool description and schema hint updated to list all supported reviewer families and to tell the executor to prefer omitting `model`.
- **New**: **Provider-aware proxy URL hints in `/setup`** — before the "Proxy base URL" prompt, ARIS now prints examples of known-working third-party proxies for the chosen provider. For Anthropic: `https://code.newcli.com/claude`, `https://api-inference.modelscope.cn`. For OpenAI: `https://openrouter.ai/api/v1`, `https://api.deepseek.com/v1`, `https://dashscope.aliyuncs.com/compatible-mode/v1`. Pure UX — input-URL logic unchanged.
- **Improved**: Prompt text now says `"Enter to keep"` (truthful) instead of `"Enter for default"` (misleading — pressing Enter preserves the current value, not the provider's built-in default).
- **Improved**: `aris doctor` reviewer-API check now covers all six supported auth env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `GLM_API_KEY`, `MINIMAX_API_KEY`, `KIMI_API_KEY`, `ARIS_REVIEWER_AUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`). `/reviewer` slash-command summary updated similarly.

**Known limitations (planned for v0.4.5 / v0.5.0):**
- Reviewer-side Claude proxy is still Bearer-only (`tools/src/lib.rs` anthropic-compat branch). Fix coming with a provider-aware auth-mode option for the reviewer path.
- DashScope Anthropic-format (Coding Plan) needs a tier-specific request header we don't emit yet — issue [#159](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/159). Intentionally omitted from the Anthropic URL hints until the header is implemented.

## v0.4.3 (2026-04-17)

- **Fix**: **Third-party Anthropic-compatible proxies (Bedrock, etc.) rejected beta headers** — providers that emulate the Anthropic Messages API do not recognize Anthropic-specific beta flags (`oauth-2025-04-20`, `claude-code-20250219`, `interleaved-thinking-2025-05-14`, `context-1m-2025-08-07`), causing `400 Bad Request: invalid beta flag`. Introduced `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` env var (read via new `api::read_send_betas()`); when set, the Anthropic client omits the `anthropic-beta` header on OAuth requests. The flag is auto-enabled when a custom `executor_base_url` is configured for `anthropic` or `anthropic-compat` providers, and auto-cleared when switching back to the official API.
- **Fix**: **Custom `executor_base_url` ignored for `anthropic` provider** — previously only the `anthropic-compat` path propagated `executor_base_url` to `ANTHROPIC_BASE_URL`. A user who selected `provider=anthropic` with a proxy URL would silently hit `api.anthropic.com` and fail with `401 Unauthorized`. Now both `anthropic` and `anthropic-compat` propagate the URL.

Credit: [@screw-44](https://github.com/screw-44) ([#156](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/156)).

## v0.4.2 (2026-04-16)

- **Fix**: **Auto-compaction corrupted session after skill runs** — `assistant stream produced no content` after `[auto-compacted: removed N messages]` when the preservation window started mid-tool-chain or with a non-User message. Compaction now scans forward to the nearest User message as the boundary, avoiding dangling `tool_use`/`tool_result` pairs that caused the API to return an empty stream. Messages skipped during the forward scan are now correctly included in the summary instead of being silently dropped from both summary and tail. Symptom: after skills produced many tool calls, the next user prompt would fail; closing and reopening restored the ability to talk.
- **Fix**: **Compaction summary silently lost on OpenAI-compatible executors** — `openai_executor::convert_messages_openai` explicitly skips `MessageRole::System` messages inside the messages array, so the compaction continuation message (role=System) was erased before hitting the API. Changed continuation role from `System` to `User` so the summary survives for all executors. Added regression tests.
- **Fix**: **Custom executor base URL ignored when setup runs mid-launch** — if the saved `config.json` already had `executor_base_url` set to an old value, the startup `apply_to_env()` populated `EXECUTOR_BASE_URL` first; the post-setup `apply_to_env(force=false)` then skipped overwriting it because the env var was "already set." User would type `https://gmncode.cn` in setup but the CLI kept hitting `api.openai.com/v1`. Fixed by using `force_apply_to_env()` after the mid-launch setup wizard. Reviewer URL was unaffected because the reviewer API key setter always writes unconditionally.
- **Fix**: **Shell-provided `OPENAI_API_KEY` no longer erased on launch** — the mid-launch "no API key found" guard only checked `ANTHROPIC_API_KEY` / `EXECUTOR_API_KEY` / `ANTHROPIC_AUTH_TOKEN`, not `OPENAI_API_KEY`, even though `resolve_openai_executor_config` accepts the latter as a fallback. A user who set `EXECUTOR_PROVIDER=openai` + `OPENAI_API_KEY=...` in their shell would be wrongly routed through setup, and then `force_apply_to_env()` would clear their shell-provided key. Guard now also recognizes `OPENAI_API_KEY` when `EXECUTOR_PROVIDER=openai`, and saved Anthropic OAuth credentials count only when the selected executor is Anthropic (not OpenAI-compat).
- **Fix**: **Mid-launch setup no longer wipes shell reviewer keys** — when startup setup ran to populate an executor key, it previously called `force_apply_to_env()`, which also cleared reviewer env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.). Users with a shell-provided reviewer key who pressed Enter to keep the existing value lost reviewer access for the rest of the process. Added `force_apply_executor_env()`, which clears only executor-related env vars; the mid-launch path uses it. REPL `/setup` keeps the full clear since the user explicitly reconfigures everything there.
- **Fix**: Empty or whitespace-only `EXECUTOR_BASE_URL` env var now correctly falls back to the provider default and trims legitimate values to avoid malformed URLs.

## v0.4.1 (2026-04-15)

- **New**: **Robust reviewer/executor retries** — transient network errors, HTTP 429 rate limits, and 5xx server errors now auto-retry (up to 4 attempts, exponential backoff, honors `Retry-After`). Ctrl+C interrupts the backoff instantly.
- **Fix**: **Stale interrupt flag** — after a Ctrl+C mid-tool, subsequent tool calls no longer fail with "interrupted by user" forever. Every interrupt check now consumes the flag.
- **Fix**: **Broken connection pool on reviewer** — LlmReview builds a fresh HTTP client per attempt with `pool_max_idle_per_host=0`, avoiding reuse of dead TCP/TLS connections. Adds 15s connect timeout + 180s total timeout.
- **Improved**: Network error messages now include full `caused by:` chain (DNS / TLS / connection reset) so failures are diagnosable instead of opaque "error sending request".

## v0.4.0 (2026-04-15)

- **New**: **Plan mode** — `/plan <task>` enters read-only execution (Read/Grep/Glob/WebSearch only, no Edit/Write/Bash). `/plan execute` switches back to normal permissions. `/plan exit` cancels. Transactional state transitions: if runtime rebuild fails, previous state is preserved. Inspired by claw-code.
- **New**: **Cooperative Ctrl+C interrupt** — single Ctrl+C aborts the current in-flight operation and returns to REPL instead of killing the process. Works across Anthropic streaming, OpenAI-compatible streaming, conversation loops, and reviewer calls.
- **Fix**: **API errors no longer exit the REPL** — network failures, 4xx/5xx responses, and malformed responses are caught at the REPL boundary; user can retry or `/model` to switch.
- **New**: **Tool output folding** — WebSearch / WebFetch / LlmReview / Skill tool results get dedicated compact formats; default truncation tightened from 200 → 120 chars.
- **Sync**: 62 skills synced from main ARIS branch, plus 16 shared-references bundled as embedded resources. Auto-extracted to cwd on first skill invocation; `../shared-references/` paths rewritten to cwd-relative for bundled skills.
- **Fix**: **Windows `fs::rename`** — credentials save (oauth.rs) and Codex MCP config write now remove target before rename (Windows doesn't overwrite).
- **Fix**: **Stale reviewer env vars** — `force_apply_to_env` now clears `ARIS_REVIEWER_PROVIDER` / `ARIS_REVIEWER_AUTH_TOKEN` when switching reviewer config.

## v0.3.11 (2026-04-13)

- **New**: **Reviewer Anthropic-compatible mode** — LlmReview now supports Anthropic-compatible endpoints as reviewer (e.g., Claude via proxy). Set `ARIS_REVIEWER_PROVIDER=anthropic-compat` or select "Anthropic Proxy" in `/setup`.
- **New**: `/setup` adds option 6 "Anthropic Proxy" for reviewer, enabling Claude-as-reviewer via proxy services.

## v0.3.10 (2026-04-11)

- **Fix**: **Windows compatibility overhaul** — all path resolution now uses `USERPROFILE` fallback (previously only checked `HOME` which doesn't exist on Windows, causing crashes). Bash tool uses `cmd /C` on Windows. `fs::rename` handles existing target files.
- **Fix**: `/setup` "Skip reviewer" now properly clears `reviewer_model`. Force setup clears all reviewer env vars to prevent stale state.

## v0.3.9 (2026-04-11)

- **New**: **Proxy / custom base URL support** — `/setup` now asks for proxy base URL for ALL providers (Executor + Reviewer). Supports API proxy services (CCSwitch, CCVibe, etc.) and local models (LM Studio, Ollama). Leave blank for default — zero behavior change for existing users.
- **New**: Anthropic proxy mode — entering a custom URL for Anthropic automatically switches to Bearer token auth (compatible with Chinese API proxy services).
- **New**: `reviewer_base_url` field — LlmReview tool now respects custom reviewer proxy URL via `ARIS_REVIEWER_BASE_URL`.

## v0.3.8 (2026-04-09)

- **Fix**: `/setup` and `/model` now rebuild system prompt with new model identity. Previously the model would still identify as the old model (e.g., "I am Claude" after switching to GPT).

## v0.3.7 (2026-04-09)

- **Fix**: `/setup` provider switch now clears stale env vars. Switching from OpenAI to Anthropic no longer sends Claude model names to the OpenAI endpoint (404 error).
- **Fix**: OpenAI-compatible streaming tool calls no longer lose their name when a later delta sends an empty string. Fixes "assistant stream produced no content" for some providers.

## v0.3.6 (2026-04-08)

- **Fix**: Tab completion crash when skill descriptions contain CJK characters (Chinese/Japanese/Korean). The `clip()` function was slicing bytes instead of chars, causing a panic on multi-byte UTF-8 boundaries. Fixes #124.

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
