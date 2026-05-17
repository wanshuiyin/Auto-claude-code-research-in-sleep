# ARIS-Code Changelog

## v0.4.9 (2026-05-17)

The "v0.4.8 second half" release — closes the three Codex v0.4.7
cross-cutting audit residuals (L1 TLS double-stack, L3 reasoning
cache misalignment, L4 reasoning replay unbounded + no provider
gate), syncs two missing main-branch skills with `scripts/`
helpers, promotes `research_wiki.py` to the shared `tools/`
namespace, finishes the SKILL.md fallback-chain migration started
in v0.4.8, and lays down the regression test surface that v0.4.8
had deferred.

### 🚨 Fix (Codex T16 audit residuals)

- **L1: TLS double-stack** — `crates/tools/Cargo.toml` switches reqwest
  features from `rustls-tls` to `native-tls`. Now all three reqwest
  consumers (`api`, `aris-cli`, `tools`) use platform TLS uniformly.
  Previously v0.4.7 #225 only switched `api` + `aris-cli`, leaving
  the `LlmReview` reviewer path on the rustls fingerprint and
  DashScope-class endpoints still 405-able via reviewer. `cargo
  tree -i hyper-rustls` now returns "did not match any packages".
  `.github/workflows/release.yml` gains a Linux-only step that
  installs `libssl-dev` + `pkg-config` for openssl-sys's
  compile-time headers.

- **L3: reasoning_cache compaction misalignment** — `ApiClient` trait
  gains `on_session_compacted(removed_count)` default-no-op.
  `maybe_auto_compact()` in `crates/runtime/src/conversation.rs`
  notifies the client after replacing the session.
  `OpenAIRuntimeClient` clears its message-index-keyed
  `kimi_reasoning_cache` on compaction so re-injected reasoning
  aims at the right turn after the index shift.

- **L4: reasoning replay no cap + no gate** — Two changes:
  (a) split predicate `supports_reasoning_content_replay` as a
  superset of `supports_reasoning_effort` (adds Kimi / Moonshot /
  Xiaomi MiMo / DeepSeek-R1 — providers that emit reasoning_content
  but don't accept reasoning_effort as a request field, which is
  the reason this cache exists). (b) Per-turn cap
  `MAX_REASONING_CHARS_PER_TURN = 32_000` (UTF-8-safe char-boundary
  truncate) + total cap `MAX_REASONING_CACHE_TOTAL_CHARS = 128_000`
  with oldest-eviction. Drops vestigial `supports_reasoning: bool`
  parameter from `convert_messages_openai`.

### 🆕 Skill helper subsystem completion

- **Bundle 2 new skills with `scripts/` subdir**: `/figure-spec`
  (`scripts/figure_renderer.py`, 29.9KB) and `/paper-illustration-image2`
  (`scripts/paper_illustration_image2.py`, 8.7KB). Both follow
  main-branch ARIS's Phase 3 Arch C ("single-owner helpers in
  `skills/<owner>/scripts/`"). Their SKILL.md resolvers gain a new
  **Layer 0b**: `$ARIS_CACHE_DIR/skills/<name>/scripts/<helper>.py`,
  the primary path under the aris-code single-binary distribution.
  Bundle inventory: 64 skills + 36 helpers (was 62 + 34 in v0.4.8).

- **Promote `research_wiki.py` to shared `tools/`** — used by 9+
  skills (idea-creator, research-lit, result-to-claim, future
  `/research-wiki` redesign). Moved from `skills/research-wiki/`
  to `tools/research_wiki.py` so the policy table in
  `shared-references/integration-contract.md` correctly classifies
  it as "shared cross-skill helper" per the Repo A contract.
  14 callsites across 3 SKILL.md updated to
  `python3 "${ARIS_CACHE_DIR:-.}/tools/research_wiki.py"`.

- **5 more SKILL.md migrated to 4-layer fallback chain**:
  `/exa-search` (Policy A — gate), `/semantic-scholar` (Policy D1 —
  primary cascade to inline-urllib fallback), `/arxiv` (Policy D1 —
  expanded inline-Python candidate list with `$ARIS_CACHE_DIR`),
  `/idea-creator` (5 callsites). `/research-lit` + `/deepxiv`
  migrated in v0.4.8.

### 🧪 Tests (closes the v0.4.8 deferred T9-T12 work)

- **`cache::tests::bundle_inventory_skill_md_refs_resolve_to_bundled_resources`**
  (cargo test, every CI invocation). Scans every `BUNDLED_SKILLS`
  prompt for `$ARIS_CACHE_DIR/<key>` and bare `python3
  tools/<helper>.{py,sh}` references; asserts every captured key
  exists in `BUNDLED_RESOURCES`. Closes the H6 regression class.

- **`idea-stage/v0.4.9/skill_helper_smoke.sh`** — release-binary
  smoke test in isolated `$HOME`/`$cwd`: validates cache layout, 9
  shared helpers present, each Python helper passes `python3 -m
  py_compile`, shell helpers pass `sh -n`, and **cwd has zero
  pollution** (H6 regression guard: v0.4.7 wrote helpers to
  `cwd/<skill_name>/`).

### Provenance

- 8 commits, all individually reviewed by Codex 5.5 xhigh. Final
  audit (T30) caught one **Hold** blocker — the new figure-spec /
  image2 skills used Repo A's `$CLAUDE_SKILL_DIR` resolver which
  doesn't exist under the aris-code bundle. Fixed by adding Layer 0b.
  Final ship verdict: **B / ship** (not A because provider routing
  split + Responses API support are v0.5.0 work; not a v0.4.9
  blocker).

## v0.4.8 (2026-05-17)

The skill-helper subsystem rewrite. v0.4.7 was the last release where bundled helper scripts (`tools/*.py`, `templates/*.tex`) extracted into the user's current working directory and where SKILL.md files hardcoded `python3 tools/foo.py` paths that frequently silent-exit-2'd because `tools/` didn't exist there. v0.4.8 materialises the bundle into a versioned global cache (`~/.config/aris/cache/<version>/`), surfaces the materialisation report to the model on every Skill invocation, and ships a four-layer fallback chain documented in a new integration contract. Plus two community-reported bug fixes that landed on the way through.

### 🚨 Fix

- **gpt-5.5 / o3 / o4 + tools 400 on OpenAI** ([executor 400 bug](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues)) — Switching the executor to gpt-5.5 (or o3/o4) on `api.openai.com` caused immediate `OpenAI API error 400: Function tools with reasoning_effort are not supported for gpt-5.5 in /v1/chat/completions. Please use /v1/responses instead`. The intersection of `tools` + `reasoning_effort` + reasoning-model on the chat-completions endpoint is server-rejected. v0.4.5 added `reasoning_effort='xhigh'` for executor without realising the executor always sends `tools` (agent loop), and the bug shipped silent for reviewer because the LlmReview path doesn't send tools. v0.4.8 strips `reasoning_effort` on the gated path (gpt-5.5/5.6/o3*/o4* + tools + api.openai.com), with a one-shot stderr warning explaining the gate. Override via `ARIS_FORCE_REASONING_WITH_TOOLS=1` for compatible third-party proxies. Proper fix (OpenAI Responses API support) tracked for v0.4.9.

- **Custom reviewer reset to gpt-5.5 every restart** (Windows-reported community bug) — `/setup` Custom reviewer (menu option 9) didn't persist `reviewer_model` because the model-selection branch in `config.rs` checked `reviewer_choice == "8"` (which is "Skip"), not `"9"`. Custom fell through to the else branch and set `reviewer_model = Some("")`, which round-tripped through config.json and reset the reviewer on every launch. Three layered fixes: (1) `config.rs:577` corrected to `"9"`, (2) `LlmReview` custom branch refuses to fall back to gpt-5.5 when the user has a Custom provider but model is empty — returns a clear error pointing to `/setup`, (3) `/reviewer` menu now shows "Custom reviewer configured" with current endpoint and model instead of the misleading "No reviewer API key found" error when items list is empty.

### 🆕 New — skill-helper subsystem rewrite

- **Global versioned cache** at `~/.config/aris/cache/<CARGO_PKG_VERSION>/` (Windows: `%USERPROFILE%\.config\aris\cache\<version>\`) — bundled helpers extract here at startup, not into cwd. `runtime::ExtractionReport` captures `extracted` / `failed` / `paths_tried` / `hard_error`; stored once in a `OnceLock` and accessible via `runtime::extraction_report()`. Atomic-replace via tmp-then-rename (Unix atomic, Windows first-writer-wins with content equality check — same bundle bytes = success). Falls back to `std::env::temp_dir()/aris-cache-<version>/` if home cache unavailable. Sets `$ARIS_CACHE_DIR` to the actually-used directory (or unsets it if both home and temp failed), forward-slash normalised for cross-platform shell compatibility.

- **`SkillOutput.helperReport` field** — every Skill tool invocation now returns per-skill scoped extraction report (cache dir, available helpers with absolute paths, failed helpers with error messages, `cacheUsable` flag). Runtime injects a resolver-chain preamble in front of the SKILL.md prompt text so the model sees the four-layer fallback explicitly: active skill dir → `~/.config/aris/<bundle-key>` → `$ARIS_CACHE_DIR/<bundle-key>` → project workspace. Forward-slash normalised paths on Windows for shell compatibility.

- **`/skills export` now copies bundled helpers** along with SKILL.md. Previously only the SKILL.md was exported; the filesystem skill then took precedence over the bundled one but lost its helpers (templates/, scripts/, etc.) — a silent regression. Now iterates `BUNDLED_RESOURCES` filtered by `skills/<canonical_name>/` prefix, preserves subdirectory structure, skips files that already exist (user edits survive re-export). Case-insensitive `find_skill_content` matching is now resolved to the canonical bundled name BEFORE building the export prefix, so `/skills export Research-Wiki` correctly lands at `~/.config/aris/skills/research-wiki/` with all helpers.

- **8 shared cross-skill helpers bundled** into `assets/tools/`: `arxiv_fetch.py`, `deepxiv_fetch.py`, `exa_search.py`, `semantic_scholar_fetch.py`, `openalex_fetch.py`, `save_trace.sh`, `verify_papers.py`, `verify_paper_audits.sh`. Synced from main-branch ARIS. `BUNDLED_RESOURCES` count now 34 (17 shared-references + 9 skill-local + 8 shared tools).

- **`shared-references/integration-contract.md`** — new canonical document for SKILL authors. Defines the 4-layer resolver chain and 6 failure policies (A gate / B side-effect / C forensic / D1 cascade / D2 multi-source / E diagnostic) for binding helper invocations to the cost of their silent failure. Adapted from main-branch ARIS contract but rewritten for aris-code's bundled-binary distribution. Skills authored after v0.4.8 should declare the policy of every helper invocation alongside the resolver block.

- **`/research-lit` and `/deepxiv` migrated** to the canonical fallback chain as proof-of-concept (Policy D2 for /research-lit's three fetchers, D1 primary cascade for /deepxiv). The runtime resolver preamble covers other SKILL.md files in the meantime; full SKILL.md sweep (5+ remaining) tracked for v0.4.9.

### 🛠 Build / internals

- **build.rs recursive walk** — replaces flat `fs::read_dir` with `walkdir` traversal under `assets/tools/` and `assets/skills/<name>/`, preserving subdirectories. Strict namespace migration to three prefixes: `tools/<rel>`, `skills/<name>/<rel>`, `shared-references/<rel>`. Symlinks rejected at every level (top-level `assets/`, SKILL.md, recursive entries). WalkDir errors panic instead of silently filtering. Allow-listed extensions: `md`, `py`, `sh`, `tex`, `cls`, `bst`, `toml`, `yaml`, `yml`, `json`. 512KB per-file cap (allow-listed files exceeding cap panic at build time; never silently skipped). Sanitised OUT_DIR filenames include hash prefix to defeat key collisions.

- **`skills-codex*` review-snapshot mirrors excluded** from BUNDLED_RESOURCES — `skills-codex/`, `skills-codex-claude-review/`, `skills-codex-gemini-review/` were accidentally getting README.md emitted into the bundle. They're review-format mirrors of the same skills, not user-facing — removing the noise saves ~thousands of would-be-entries if recursion were enabled. Users wanting them can clone the repo and copy under `~/.config/aris/skills/`.

- **`paper-write/templates/`** (8 LaTeX files including 275KB IEEEtran.cls) now bundled correctly. The flat scanner in v0.4.7 silently dropped them; v0.4.8's recursive walker picks them up under `skills/paper-write/templates/` key prefix.

### 🧹 Cleanup

- **`bundled_resource()` vestigial getter** in `runtime/lib.rs` deleted. Zero workspace references (consumers iterate `BUNDLED_RESOURCES` directly). 9 lines down.

- **`extract_bundled_helpers()` cwd-based extractor** in `tools/src/lib.rs` deleted. Startup eager extract via `runtime::extract_bundle` replaces it cleanly; cwd pollution gone.

### Credits

- Two community bug reports: gpt-5.5+tools 400 (executor) and Custom-reviewer-resets-to-gpt-5.5 (Windows). Thank you for the reproduction steps.

## v0.4.7 (2026-05-16)

A community-driven release. [@GetIT-Sunday](https://github.com/GetIT-Sunday) followed through on the v0.4.5 commitment to land DashScope Coding Plan support and added a nice reasoning-content generalization on top of v0.4.5's `reasoning_effort='xhigh'` work. Bundled with a sweep of pre-rename dead code and a legacy branding cleanup.

### Fix

- **DashScope Coding Plan returning 405 ([#159](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/159))** — Switched reqwest's TLS backend from `rustls-tls` to `native-tls` for the `api` and `aris-cli` crates, plus added a DashScope Coding Plan endpoint hint in `/setup`. `native-tls` uses platform TLS (SecureTransport on macOS, OpenSSL on Linux, SChannel on Windows), which DashScope's Coding Plan endpoint accepts where rustls did not. Credit [@GetIT-Sunday](https://github.com/GetIT-Sunday) ([#225](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/225)).
- **Hardcoded `user_agent("aris/0.4.5")` follow-up** — Now derived from `CARGO_PKG_VERSION` at build time so it tracks the binary version automatically.

### New

- **`reasoning_content` replay for all reasoning-capable providers**, not just Kimi — Previously the assistant-message replay cache that preserves multi-turn reasoning traces was gated behind an `is_kimi` check. Generalized so OpenAI o1/o3/o4-family, DeepSeek-R1, and any future reasoning model that returns `reasoning_content` keeps its chain-of-thought visible across turns. Pairs with v0.4.5's `reasoning_effort='xhigh'` (request-side) — together they make multi-turn reasoning conversations actually coherent. Credit [@GetIT-Sunday](https://github.com/GetIT-Sunday) ([#226](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/226)).

### Cleanup / removed

- **Dead-code removal**: `crates/runtime/src/sse.rs` (128-line generic SSE parser never wired in — `runtime/lib.rs` had no `mod sse`), `crates/aris-cli/src/app.rs` + `crates/aris-cli/src/args.rs` (398 + 108 lines of `rusty-claude-cli` prototype code with no references). Each verified by Codex audit before deletion (zero workspace references).
- **Dropped unused `rustyline = "15"` dependency** from `aris-cli/Cargo.toml`. The interactive editor in `input.rs` has used `crossterm` for several versions; the rustyline crate was scaffolding never consumed.
- **User-facing "Claw Code" → "ARIS-Code" rebranding** in three strings the user actually sees: the `.gitignore` section title written by `aris init`, the `CLAUDE.md` template body line, and the `Config` tool description (LLM-visible). Deliberately did **not** rename `CLAWD_*` env vars, the `claw-code-guide` subagent type string, or the `compat-harness` upstream vendor paths — those are API surface and need a separate v0.5.0 transition with `ARIS_*` aliases.

### Docs

- `compat-harness` crate header doc clarifying it is a static manifest extractor (driven by `aris dump-manifests`), not a runtime regression harness.

### Credits

- [@GetIT-Sunday](https://github.com/GetIT-Sunday) — native-tls for DashScope Coding Plan ([#225](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/225)) + reasoning_content for all providers ([#226](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/226)) — second contribution after the v0.4.5 Xiaomi/Qwen/Doubao cherry-pick

## v0.4.6 (2026-05-14)

A small but high-impact follow-up to v0.4.5. Two critical fixes that were
shipping silently broken for multiple releases, plus a third community-driven
feature ([@Anduin9527](https://github.com/Anduin9527)'s reworked PR #221/#222
landing as a custom OpenAI-compatible provider).

### Fix

- **🚨 `PermissionMode::Prompt` was silently granting every tool** — The
  `PermissionMode` enum derived `Ord` with `Prompt` placed *above*
  `DangerFullAccess` (positions 4 vs 3), so the short-circuit
  `current_mode >= required_mode` inside `authorize()` was always true when
  the active mode was `Prompt`, and the prompter branch was unreachable.
  Users who explicitly chose "ask me before every tool" were getting silent
  approval for every request — the exact opposite of the intent. Fix splits
  the `Allow` short-circuit from the Ord comparison and excludes `Prompt`
  from the latter, with two new regression tests pinning the corrected
  behavior. ([permissions.rs:97-108](crates/runtime/src/permissions.rs#L97))
- **🚨 System prompt hard-coded `current_date = "2026-03-31"`** — Every
  conversation (main + subagent) injected that frozen date into the
  Anthropic system prompt via `ProjectContext::current_date`, so the model
  literally believed today was 2026-03-31 forever. Real data from later
  dates was rejected as "future / prompt injection" — including a user's own
  arXiv paper submitted after the cutoff, which the model loudly flagged as
  fabricated. Added `runtime::today_iso()` (reusing the existing
  chrono-free `days_to_ymd` algorithm) and threaded it through all 5 prompt
  call-sites (`aris-cli/main.rs:529, 2707, 2856, 3232`,
  `tools/lib.rs` subagent date). The `aris --version` "Build date" still
  uses the old constant — that one is *supposed* to be frozen.

### New

- **Custom OpenAI-compatible provider** (`/setup` option **11**, reviewer
  option **9**) — Plug ARIS into any OpenAI-compatible endpoint that isn't
  in the built-in menu: OpenRouter, self-hosted LLM gateways, internal
  inference servers, small Chinese vendors, etc. Stores `provider="custom"`
  internally but maps to the same OpenAI-compat HTTP path as the built-in
  presets at runtime, so existing routing / `reasoning_effort` allow-list
  still applies. Reviewer "Custom" uses `ARIS_REVIEWER_AUTH_TOKEN` /
  `ARIS_REVIEWER_BASE_URL` so it doesn't collide with the executor's
  `OPENAI_API_KEY`. Banner now reports "Custom" rather than mislabeling it
  as "OpenAI". Credit [@Anduin9527](https://github.com/Anduin9527)
  ([#221](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/221)).
- **Dynamic `/models` discovery for custom providers** — When the user
  selects the Custom provider in `/setup` (or invokes `/model`), ARIS calls
  the provider's `GET /v1/models` endpoint to populate the interactive
  picker with the actual available model list. We added a 10s connect
  timeout + 20s total timeout so a bad URL / TLS stall / half-open
  connection can no longer hang the wizard, and we clear stale
  `executor_model` / `reviewer_model` on menu-switch so the manual-entry
  fallback prompt always fires when the fetch fails. The new
  `crates/aris-cli/src/openai_compat.rs` carries 3 `TcpListener`-based
  offline tests so CI never hits `api.openai.com`. Credit
  [@Anduin9527](https://github.com/Anduin9527)
  ([#222](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/222)).

### Credits

- [@Anduin9527](https://github.com/Anduin9527) — Custom OpenAI-compatible provider + dynamic `/models` discovery (PR [#121](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/121) reworked into [#221](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/221) + [#222](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/222), then cherry-picked with three small follow-up adjustments)

## v0.4.5 (2026-05-13)

A reasoning-model + multi-provider release. The headline is **first-class support for thinking-content models** (DeepSeek V4 Pro, OpenAI o1/o3/o4 family, GPT-5.5 with `reasoning_effort='xhigh'`) — both the wire-format plumbing and the interactive setup were missing pieces. Bundled with that: 3 new Chinese provider presets (Xiaomi MiMo / Qwen 3.6 / Doubao), object-style hooks parser, default model bump to Claude Opus 4.7 + GPT-5.5, and a stack of REPL input fixes (multi-line wrap, bracketed paste, CJK wide-char layout).

### New

- **Thinking content blocks** — Full pipeline now handles models that return reasoning/thinking output. Adds `Thinking` variants to `OutputContentBlock` / `InputContentBlock` / `ContentBlockDelta` / session `ContentBlock` / runtime `AssistantEvent`, threads them through stream decoding, session persistence, and `convert_messages` so they're handed back to the API on follow-up turns. **Fixes [#161](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/161)** (unknown variant `thinking` deserialization) and the consequent 400 Bad Request when reasoning models expect their thinking to be echoed back. Credit [@GO-player-hhy](https://github.com/GO-player-hhy) ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186)).
- **`reasoning_effort='xhigh'`** is now actually sent on requests for reasoning-capable models (`gpt-5.5`, `gpt-5.6`, `o1*`, `o3*`, `o4*`, `*-reasoner`, `*-thinking`). Both the executor (`openai_executor.rs`) and the reviewer (`LlmReview` in `tools/lib.rs`) attach the field. Before this, the banner advertised "Claude x GPT-5.5 xhigh" but the field was never on the wire, so OpenAI servers defaulted to `medium` effort. Override the tier with `ARIS_REASONING_EFFORT={none|minimal|low|medium|high|xhigh}`.
- **DeepSeek V4 Pro in `/setup`** — Executor option 7 + reviewer option 7, via `anthropic-compat` provider against `https://api.deepseek.com/anthropic` with default model `deepseek-v4-pro`. The anthropic-compat path is chosen over openai-compat specifically because it preserves DeepSeek's thinking content blocks. Credit [@GO-player-hhy](https://github.com/GO-player-hhy) ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186)).
- **Xiaomi MiMo / Qwen 3.6 / Doubao** in `/setup` wizard as options 8/9/10 and in `/model` interactive picker. Endpoints: `xiaomimimo.com/v1`, `dashscope.aliyuncs.com/compatible-mode/v1`, `ark.cn-beijing.volces.com/api/v3`. Default models: `mimo-v2.5-pro`, `qwen3.6-plus` (1M context), `doubao-pro-4k` (Ark API format). Partial cherry-pick of [@GetIT-Sunday](https://github.com/GetIT-Sunday)'s [#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216); the openai-compat DeepSeek alternative and native-tls swap from that PR are deferred to v0.4.6.
- **Claude Code object-style hooks** parser — `settings.json` / `.claude.json` can now use the richer hook syntax `{ "matcher": ".*", "hooks": [ { "type": "command", "command": "..." } ] }` in addition to the legacy string-array form. Object-style hooks are flattened to commands internally so the rest of `HookRunner` is unchanged. Credit [@Jxy-yxJ](https://github.com/Jxy-yxJ) ([#171](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/171)).
- **Default model bump** — `DEFAULT_MODEL`, `/setup` wizard defaults, `/model` and `/reviewer` interactive picker top entries all upgraded to `claude-opus-4-7` (Anthropic) and `gpt-5.5` with the new `xhigh reasoning` label (OpenAI). Previous flagships (`gpt-5.4`, `gpt-5.4-mini`, `-nano`) remain as fallback options in the menu.
- **CI workflow** — `.github/workflows/ci.yml` runs `cargo build --workspace --all-targets` + `cargo test --workspace -- --test-threads=1` on Ubuntu and `cargo build --workspace --all-targets` on macOS for every push/PR to `aris-code` or `main`. Serialized test runner avoids a pre-existing ubuntu cwd race in tools integration tests. clippy/fmt/macos-test will tighten in follow-up PRs.

### Fix

- **Multi-tool result grouping** — When a single assistant turn issued multiple parallel tool calls, each `ToolResult` used to be emitted as its own `ConversationMessage`, which the next API call would then reject with `tool_use_ids_without_tool_result`. All tool results from one turn are now grouped into a single message (role `MessageRole::Tool`, mapped to Anthropic's `user` role at the adapter boundary via `convert_messages`). Credit [@GO-player-hhy](https://github.com/GO-player-hhy) ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186)).
- **REPL input duplicated forever when buffer wrapped multiple rows** — Pasting a long API key (e.g. `sk-ant-api03-...` over the terminal width) used to make every subsequent keystroke re-print the entire buffer below the previous render. Root cause: `redraw()` ran `MoveToColumn(0)` + `Clear(FromCursorDown)` from the *last* physical row of the wrapped block, so the prior wrap rows survived and the new block stacked underneath. Now a per-read `RenderState` tracks the previously drawn cursor row and `redraw` jumps back to the top of the input area before clearing.
- **Cmd+V multi-line paste fired one prompt per line** — Without bracketed paste mode, the pasted byte stream was delivered to the raw-mode editor character-by-character, and every `\n` parsed as `KeyCode::Enter` triggered submit. A 5-line paste became 5 separate prompts to Claude. Now `EnableBracketedPaste` is queued after `enable_raw_mode()` (with graceful fallback for terminals that report Unsupported), and `Event::Paste(String)` inserts the whole block at the cursor as a single edit. Newlines / tabs / control chars inside the paste are flattened to spaces (single-line editor; multi-line buffer is a v0.5.x feature).
- **CJK wide chars at the right edge collapsed the cursor** — Typing Chinese at the end of an already-wrapped buffer would make the previously-typed character visually disappear (data was preserved, but redraw clobbered the cell). Root cause: cursor row was derived from `display_width / terminal_width`, which puts the cursor in the middle of a wide-cell at exactly the wrap boundary. `RenderState` now stores `cursor_row` directly and `layout_position()` simulates actual terminal cell layout (pre-wrap before drawing a wide char if it would partially overflow; pending-wrap when a narrow char exactly fills the last column).
- **`settings.json` object-style hooks made the entire feature_config fall back to default** — When the hooks parser saw a non-string-array hook value it returned a load error, and the CLI's load-error path silently swapped in `RuntimeFeatureConfig::default()`, which wiped user-configured MCP servers / OAuth / sandbox / permissionMode too. Object-style hooks are now parsed natively. Credit [@Jxy-yxJ](https://github.com/Jxy-yxJ) ([#171](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/171)).
- **DeepSeek user identifying as "developed by Anthropic"** — The ARIS identity line in the system prompt hard-coded `developed by Anthropic`. `friendly_name` map now covers `deepseek-v4-pro`, `mimo-*`, `qwen3.6-*`, `doubao-*-4k`, and the vendor is derived from a prefix-map (`mimo-→Xiaomi`, `deepseek-→DeepSeek`, `qwen-`/`qwen3.→Alibaba`, `doubao-→ByteDance`, `gpt-`/`o1`/`o3`/`o4→OpenAI`, `gemini-→Google`, `GLM→Zhipu`, `MiniMax→MiniMax`, `kimi-`/`moonshot-→Moonshot`).

### Improved

- **Banner provider label** recognizes Xiaomi / Doubao base URLs and shows the correct family name on startup.
- **Compaction summary** continuation uses `MessageRole::Tool` for tool results (mapped through `convert_messages`), restoring the v0.4.2 fix for OpenAI-compat executors that drop System-role messages.

### Skipped / planned for v0.4.6 (intentional)

- **DeepSeek openai-compat alternative path** (PR [#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216) `a1fbea8`) — conflicts with the anthropic-compat path we landed in v0.4.5; v0.4.6 will decide whether to support both with a sub-option.
- **native-tls swap for DashScope Coding Plan 405** ([#159](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/159), PR [#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216) `033f2cd`) — cross-cutting change (replaces rustls with native-tls for *all* HTTPS, affecting OAuth / MCP / OpenAI / Anthropic / OpenRouter), needs per-platform release-binary validation; will land in its own release.
- **Custom OpenAI-compatible provider rework** ([#121](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/121)) — author rework needed (split into 3 PRs + preserve v0.4.4 routing invariants); tracked.
- **Provider abstraction layer, MCP timeout/restart, bash sandbox hardening, Permission Ord bug, file_ops workspace boundary, dead code cleanup** (`app.rs` / `args.rs` / `run_setup` / `rustyline` dep) — slated for v0.4.6 architectural pass.

### Credits

- [@GO-player-hhy](https://github.com/GO-player-hhy) — Thinking blocks + multi-tool grouping + DeepSeek `/setup` ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186))
- [@Jxy-yxJ](https://github.com/Jxy-yxJ) — Claude Code object-style hooks ([#171](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/171))
- [@GetIT-Sunday](https://github.com/GetIT-Sunday) — Xiaomi / Qwen 3.6 / Doubao provider presets (partial cherry-pick of [#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216))

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
