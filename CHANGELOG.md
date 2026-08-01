# ARIS-Code Changelog

## v0.4.23 (2026-08-02)

The **output-folding release** — fixes the top real-user complaint that the
CLI dumps the full content of every document it reads (and every command's
full stdout) onto the screen — plus the bundled-skills refresh that brings in
`/integrity-forensics`, and a real fix for bash timeouts not killing the child.

### 🧹 Tool-output folding (display layer ONLY)

- **What users saw**: reading a 2000-line paper printed all 2000 lines;
  `pdftotext`-class bash commands dumped their entire stdout; grep content
  mode dumped every matched line. (Thinking was NOT actually printed — that
  perception came from these dumps; two new end-to-end sentinel tests now
  lock "thinking/reasoning never reaches the terminal".)
- **Now**: Read/Grep show the first 6 lines, Bash shows the first 4 + last 4
  per stream (stderr keeps its red), then one dim line
  "… (+N more lines — set ARIS_TOOL_OUTPUT_LINES=0 for full output)".
  Kept lines are capped at 240 chars so a minified single-line file can't
  defeat the fold. The structured edit preview gets the same char cap.
- **One escape hatch**: `ARIS_TOOL_OUTPUT_LINES` — unset = defaults, a
  positive integer overrides every tool's budget, `0` = the exact old
  display. The session, the model's context, `--output-format json` and
  `/export` are UNTOUCHED and always carry complete payloads.
- ⚠️ Compat note: external scripts that parse the human text UI as a full
  transcript should set `ARIS_TOOL_OUTPUT_LINES=0` or use
  `--output-format json`.
- Ride-along: grep's content mode no longer reports a false "0 matches"
  above real results.

### 🐛 Bash timeout actually kills the command

Previously a timed-out bash tool call reported `interrupted: true` while the
command **kept running** — its side effects landed after the report (the
dropped tokio future never killed the child). The foreground command now uses
`kill_on_drop`; a real behavioral test locks it (a timed-out
`sleep 1 && touch marker` must not create the marker). Escape hatch:
`ARIS_BASH_KILL_ON_TIMEOUT=0`. Background tasks are untouched; process-group
kill is deliberately out of scope. (The rest of the runtime-state package —
compaction re-arm, failed-turn cleanup, /cost dollars, SSE tail — ships as
v0.4.24; the cached-token cost fix is deliberately held back because it
changes what the compaction trigger measures.)

### 📦 Bundled skills: 79 → 81

Resync to main (pin 7182624 → 3e49e63): **`/integrity-forensics`** — the
Anti-Autoresearch SHA-pinned launcher (span-anchored evidence ledger → GPT
auditors → deterministic rules-only adjudicator → typed BLOCK/WARN gate) —
and **`/web-debug-search`** (GitHub Issues/Discussions debugging search);
+`tools/forensics_gate.py` (29 helpers, 104 embedded resources).

### 🧪 Dev/test hygiene

All four crates' local-mock-server tests scrub proxy env vars once per
process — a developer shell with `http(s)_proxy` set used to turn 15 tests
red on a released tag (127.0.0.1 routed through the proxy → 502). CI was
never affected.

### ✅ Tests / review

- Full workspace green **under a live proxy**: api 35+6, aris-cli 212 (+8)
  + 3 e2e (+2 thinking/reasoning sentinels), runtime 225 (+2), tools 69,
  commands 5. New-code clippy delta zero.
- Codex MCP (gpt-5.6-sol ultra) scope discussion adjudicated the design
  (fold defaults, bash head+tail, 240-char cap, JSON untouched, B4a
  exclusion) before implementation.

## v0.4.22 (2026-07-11)

The **skills resync + GPT-5.6-Sol release**: the bundled skill set catches up
93 commits to the source-of-truth (77 → **79 skills**, 28 tools helpers, 11 new
shared-references docs), the reviewer control plane moves to the **GPT-5.6-Sol
two-tier doctrine** the new skills carry, and **8 disk-verified bugs** land —
including Windows `aris login` being completely broken and an explicit
`--model` being silently overridden. Design gated by codex gpt-5.6-sol ultra
across 5 rounds (NO-GO ×4 → GO).

### 📦 Skills resync (pin 7e3ab67 → 7182624)

- **79 bundled skills** (+ `meta-apply`, + `paper-poster-html`; `paper-poster`
  is now a redirect stub), **28 tools/ helpers** (8 new, referenced by the
  synced SKILL.md files), **11 new shared-references** convention docs
  (fan-out-pattern, acceptance-gate, external-cadence, skill-governance,
  compute-env-contract, resumable-runs, evidence-precheck, injection-hygiene,
  capture-antipatterns, output-composition, taste-calibration).
- Sync hardening: `ARIS_SYNC_EXPECT_SHA` guard (aborts BEFORE touching assets/
  if origin/main moved — it caught a move on its first real run);
  exact-inventory drift tests (set equality over the 28 helper keys — catches
  both a missing helper and a stale extra); the vendored posterly MIT license
  text now ships (`build.rs` embeds `.txt`).
- ⚠️ `meta-apply` caveat for CLI-only installs: bundled SKILL.md bodies are
  compiled into the binary and have no editable corpus path — `/skills export
  <name>` first, or point it at a real `~/.claude/skills` checkout. (Upstream
  wart, mirrored as-is: main's meta-apply still uses the legacy
  `reasoning: ultra` shorthand; the system prompt now tells the model to
  translate it.)

### 🎛 GPT-5.6-Sol reviewer alignment (two-tier: deep audits ultra, floor xhigh)

- **System-prompt reviewer nudge rewritten** — the v0.4.17 blanket "never pass
  a model to codex" rule now CONTRADICTED the synced skills (which explicitly
  pin `model: gpt-5.6-sol` + per-call effort) and would silently strip deep
  audits down to xhigh. The new nudge passes the skills' pins through, carries
  the canonical capability-only fallback chain (effort-unsupported → same
  model at xhigh, deep tier only; model-unknown → EXPLICIT gpt-5.5 + xhigh;
  never degrade on timeout/rate-limit/auth/transport), requires
  `approval-policy: "never"` + an explicit `sandbox` on every fresh codex call
  (ARIS cannot service interactive escalation requests), keeps `codex-reply`
  to thread-id + prompt, makes the HTTP fallback **pre-dispatch-only**, and
  strips the skill's Codex params when re-targeting to `LlmReview`.
- **Deliberately conservative HTTP split**: the LlmReview HTTP fallback default
  **stays gpt-5.5** (the verified-working chat-completions + reasoning_effort
  combo). gpt-5.6-sol is offered as an EXPERIMENTAL explicit opt-in (it is
  API-listed for chat-completions but not yet smoked with reasoning_effort).
- `/cost` groundwork: gpt-5.6 family pricing (sol/bare $5/$0.50/$30, terra
  $2.50/$0.25/$15, luna $1/$0.10/$6 — verified against the official pricing
  page) instead of the $15/$75 unknown-model fallthrough.
- Honest reviewer UI: the banner says "GPT-5.6-Sol · tiered"; the Reviewer
  line is a three-state display (Codex primary never presents the HTTP
  fallback model as "the Reviewer"); `/reviewer` says plainly that it controls
  the HTTP fallback only — pure-Codex setups get guidance instead of a fake
  switch, and with a fallback configured it edits only that provider's model.
- `aris doctor`: codex version note (< 0.144.1 → ultra/gpt-5.6-sol
  unavailable; prerelease/malformed get conservative notes) and a
  stale-option-10 note (pre-v0.4.18 entries lack the xhigh floor args).
  Neither flips doctor's overall status.

### 🐛 Fixes (all disk-verified by a 4-agent adversarial pass)

- **Explicit `--model` wins.** `--model opus` (or the full default id) was
  silently overridden by a saved executor model; aliases were also resolved
  before the setup wizard could change the provider. Model provenance is now
  tracked end-to-end; the 4.8→4.7 availability fallback fires only for
  non-explicit sources, and `/model` / `/setup` re-arm it.
- **Saved model no longer leaks across transports.** Shell
  `EXECUTOR_PROVIDER=anthropic` over a saved OpenAI config sent "gpt-5.5" to
  the Anthropic API; the saved model now applies only on a matching provider
  family, blank saved models count as absent, and an OpenAI transport with no
  model source fails fast instead of sending the Claude default id.
- **`--output-format json` never prompts.** A danger-tier tool call under
  `--permission-mode workspace-write` printed "Permission approval required"
  to stdout and blocked reading stdin — breaking the single-JSON-document
  contract. The JSON path now takes the structured-deny path.
- **Windows: `aris login` works.** PKCE randomness read `/dev/urandom`
  (file-not-found on the shipped windows-x64 build); now `getrandom`.
- **Windows: command probing works.** The REPL/PowerShell tools probed via
  `sh -lc` (the PowerShell tool was dead on the one platform it exists for);
  Windows now probes via `where.exe`. Doctor/gh detection use `where` too.
- **Codex `.cmd` shim honesty.** `where codex` resolving an npm `.cmd` shim
  read as "✓ found", then the MCP spawn of `codex` failed. Three-state
  classification (native / script-shim / missing); setup requires explicit
  confirmation before writing config against a shim.
- **Nested config.json detected.** `{"executor": {...}}` silently parsed to
  all-defaults while startup/doctor said OK; unrecognized top-level keys now
  produce a Warning (doctor stays healthy — forward-compatible configs are
  not punished).
- **NotebookEdit duplicate cell ids.** Delete-then-insert minted an existing
  id (`cell-{len+1}`) and later edits hit the WRONG cell; ids are now
  collision-free.

### 🖥 CI / docs

- New `windows-latest` CI job: workspace compile gate + three targeted test
  groups (PKCE, command probing, codex classifier), each guarded against
  silent 0-test green.
- README/README_CN current-state sweep (the skill count claim was still
  **42**), real flat config.json example (the old nested example would trip
  the new Warning), MCP example carries the xhigh args, screenshot captioned;
  README_EN.md is now a redirect stub to the canonical README.md.
- Residual limitation (documented): a same-transport endpoint override (e.g.
  a custom base URL within the same provider family) can still carry a stale
  saved model — full route provenance is v0.5.0 provider-trait work.

### ✅ Tests / review

- +54 tests: api 35+6, aris-cli 204 (+23) plus 1 end-to-end binary
  integration test (json_mode — real aris binary vs a mock Anthropic SSE
  server, closed stdin, structured deny, single JSON document), runtime 223
  (+9), tools 69 (+2 unix-visible; the Windows-only probes run in the new CI
  job), commands 5 — all green; new-code clippy delta zero.
- Codex MCP (gpt-5.6-sol): **ultra** design gate — 5 rounds, NO-GO ×4 → GO
  (each round caught real issues: sync dirty-tree/79-vs-103 acceptance, the
  no-model-retry contradiction, the .cmd false-success, the /reviewer fake
  switch, README_EN) — then an **implementation gate** whose round 2 caught
  the first-run active-config wiring blocker, the chain-disable omission and
  the stale-entry predicate holes (all fixed + test-locked); 4 implementation
  subagents disk-verified.

## v0.4.21 (2026-06-28)

A **bug-fix patch** — five new user-facing bugs surfaced by a Codex adversarial
hunt (all five disk-verified, all distinct from v0.4.20 and the known-deferred
backlog), each cross-model reviewed at a design gate and an implementation gate
(gpt-5.5 xhigh). The headline fix stops streamed CJK/emoji text from being
corrupted into `�` on OpenAI-compatible providers.

### 🐛 Streaming / output

- **OpenAI-compatible streaming corrupted multi-byte UTF-8 split across network
  chunks.** Each HTTP body chunk was decoded with `String::from_utf8_lossy`
  independently before being buffered, so a CJK (3-byte) or emoji (4-byte) scalar
  whose bytes straddled a chunk boundary became `�` on both sides — a frequent
  hit for Chinese users on domestic OpenAI-compatible providers
  (Kimi/GLM/MiniMax/DeepSeek/Qwen/Doubao) streaming Chinese text. The stream
  buffer is now raw bytes (`Vec<u8>`); only complete, newline-terminated SSE
  lines are UTF-8-decoded, so a character split across chunks is never decoded
  mid-scalar (mirrors the Anthropic side's byte discipline).

- **An Anthropic stream truncated after content but before a terminal signal was
  saved as a complete turn.** On a clean EOF (e.g. a proxy dropping the
  connection) after meaningful text but with no `message_stop` and no
  `stop_reason`-bearing `message_delta`, `next_event()` returned `Ok(None)` and
  the consumer synthesized a `MessageStop` — committing a half-finished answer to
  history as if complete, so the next turn continued as though the model had
  finished. It now hard-errors (`premature_eof`), symmetric to the OpenAI-side
  `#249` truncation guard; the `stop_reason`-only compat path (CL2) is preserved.
  Safety valve: a proxy that legitimately never emits a terminal signal can opt
  back into the pre-v0.4.21 accept-as-complete behavior with
  `ARIS_ALLOW_EOF_WITHOUT_STOP=1`.

### 🐛 Provider routing

- **A saved OpenAI/custom executor config silently overrode a shell-set
  `EXECUTOR_PROVIDER`.** `apply_to_env` (the startup "shell-provided vars win"
  path) wrote `EXECUTOR_PROVIDER=openai` unconditionally when the saved config
  was `openai`/`custom`, contradicting its own contract and every sibling field —
  so `EXECUTOR_PROVIDER=anthropic … aris …` got re-pointed to OpenAI (wrong
  executor / model-not-found). The write is now gated like its siblings (the
  shell value wins; the explicit `/setup` force path is unchanged).

### 🐛 Tools

- **`grep_search` with `multiline: true` silently returned nothing in
  content/default mode.** `count` mode matched over the whole file (multiline
  worked), but content/default mode matched per-line, so a cross-line pattern
  could never match. Multiline now derives matched line indices from whole-file
  matches, mapping the end to the *last matched byte* to avoid an off-by-one that
  would pull in a nonexistent line on trailing-newline files.

- **MCP tool results carried only in `structuredContent` were dropped.** Dispatch
  flattened only the `content` blocks, so a spec-valid server returning only
  `structuredContent` (empty/absent `content`) handed the model an empty result.
  It now falls back to the JSON-serialized structured content when the flattened
  text is empty (content-bearing results are byte-identical).

### ✅ Tests / review

- +21 tests (CI mode, all green): api 32→35 (incl. **2 stream-level integration
  tests** — truncation → `premature_eof`; stop_reason-only → clean drain — and
  the safety-valve parse), runtime 205→212, aris-cli 172→181, tools 67,
  commands 5.
- Codex MCP (gpt-5.5 xhigh): **design gate** (NO-GO → corrected an off-by-one in
  the grep line-mapping, the provider-gate semantics, and the truncation
  hard-error decision) → **implementation gate** (NO-GO on a #1 test gap → added
  the stream-level integration tests → GO). The Anthropic streaming spec (every
  stream ends with `message_stop`) was WebFetch-verified.
- Two latent-only candidates (Anthropic `content_block_start.index` routing,
  OpenAI multi-line `data:` SSE frames) remain deferred to a hardening pass.

## v0.4.20 (2026-06-19)

A **bug-fix patch** — seven user-facing bugs, surfaced by a Codex adversarial
hunt and each cross-model reviewed across three rounds (the reviewer caught a
redraw gap, a trailing-blank, a spinner tail, and a blank-line edge before GO).
The headline fix closes [#299](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/299).

### 🐛 REPL output

- **[#299] Short replies showed only "✔ Done."** The spinner draws "⠋ Thinking…"
  with Save/RestorePosition so streamed output overwrites it on the same line —
  but then `finish` cleared that whole line, **erasing a short single-line
  reply**. The REPL now finishes with a non-clearing path when the turn printed
  visible text (`Clear(UntilNewLine)` wipes only the spinner tail after the
  reply, then a newline + "✔ Done"); tool-only/empty turns still clear the
  leftover "Thinking…" line.
- **Streamed multi-paragraph replies rendered glued together** ("para1para2").
  Each streamed chunk's paragraph separator was trimmed at the stream-safe
  boundary. The markdown streamer now preserves boundaries via a held-separator
  (emit a chunk's trailing newlines just before the *next* body, drop them at
  stream end) so streamed output now equals a single full render — with no
  dangling blank line.
- **Markdown tables with CJK / fullwidth content misaligned** — column width
  counted characters, not display cells. It now counts cells (CJK = 2).

### 🐛 CLI / tools

- **`aris "prompt"` / `--print` ignored the executor model saved by `aris
  setup`** — only the REPL applied it, so a configured OpenAI/custom executor
  got the Anthropic default model sent to its endpoint (→ model-not-found). The
  one-shot and REPL paths now share one `effective_model` resolver.
- **Esc didn't close the completion dropdown** — `redraw` recomputed matches and
  painted it right back. Esc now snapshots the buffer; completions stay hidden
  until an edit changes it.
- **`glob_search` reported the wrong file count when truncated** — `num_files`
  was the capped-100 returned count, so the model believed a 1000-match glob had
  only 100 files. It now reports the total matched (`filenames` stays ≤100).
- **`/model`'s custom-provider menu read stale on-disk config** instead of the
  effective env the executor actually uses — it now mirrors the executor's own
  resolution (env first, config fallback).

### Tests

CI mode (`--test-threads=1`): **api 32 / runtime 205 / tools 67 / aris-cli 172 /
commands 5** — all green; +7 new (markdown stream separator + concat==full-render
incl. blank-line edges, CJK cell width, effective_model, visible-text detection,
glob total count). Real-machine verified: a short reply now renders followed by
"✔ Done", and multi-paragraph replies keep their blank lines. Codex MCP (gpt-5.5
xhigh) hunt → 3 review rounds (NO-GO → NO-GO → GO). Two further candidates
(Anthropic block-`index` routing, OpenAI multi-line SSE frames) are latent-only
with no current trigger and deferred to a hardening pass.

## v0.4.19 (2026-06-14)

A **honesty / guardrails** patch release — fix a real MCP latent bug and a few
papercuts, no behavior change for healthy setups. Theme + shortlist proposed by
Codex MCP (gpt-5.5 xhigh) in a fresh-eyes audit; every change cross-model
reviewed. (Architecture work — sandbox, rustls, provider trait, Responses API —
remains deferred to v0.5.0.)

### 🔴 MCP protocol-version negotiation guard (the real bug)

The stdio handshake requested protocol version `2025-03-26` but **never read the
version the server negotiated back** (a parsed-but-dead field). A server that
agreed on a version ARIS can't speak was silently accepted, and the subsequent
`tools/list` / `tools/call` then ran on an incompatible protocol with opaque
failures. Now ARIS validates the negotiated version against a supported set
(`2025-11-25` / `2025-06-18` / `2025-03-26` / `2024-11-05` — the stdio framing is
identical across these); an unsupported version terminates the child, clears the
slot, and surfaces a clear per-server error (soft-degrade; `aris doctor` shows
the reason) — exactly the "terminate when versions can't be agreed" behavior the
MCP lifecycle spec requires. The requested version stays `2025-03-26` (proven
against `codex mcp-server`; bumping the *request* is a separate, riskier change),
so **healthy servers are unaffected** — verified end-to-end: the real Codex MCP
server still spawns + initializes + advertises its tools.

### 🧹 Papercuts

- **Stale subagent-guard message.** An OpenAI-family session that spawns a
  subagent fails loud (it would otherwise bill the wrong credential); the message
  said *"lands in v0.4.18"*, which went stale the moment v0.4.18 shipped without
  P8 — making it read like a broken build. It's now version-agnostic and
  actionable ("use an Anthropic-family executor"), still credential-free.
- **OpenAI error-body hygiene.** A non-retryable upstream error splatted the raw
  response body verbatim into the error. It's now truncated (500 chars) and
  credential-redacted — `sk-…` keys and `Bearer …` tokens are scrubbed by a
  substring scanner that also catches the compact-JSON shape (`{"api_key":"sk-…"}`)
  a misconfigured proxy can reflect back. Diagnostic text survives.
- **Honest hook-events summary count.** The system-prompt hooks summary counted
  the whole `hooks` array; it now counts only the hooks the runtime actually
  executes (a `command` hook with a `command` string), matching the parser — so
  the number the model sees equals what really runs.

### Tests

CI mode (`--test-threads=1`): **api 32 / runtime 204 / tools 67 / aris-cli 167 /
commands 5** — all green. New: protocol-version rejection (fake server returns an
unsupported version → per-server degrade), error-body redaction incl. compact
JSON, command-only hook count, and the version-agnostic guard-message assertions.
Live smoke: `aris doctor` shows the real Codex MCP server still initializes under
the new guard; a one-shot turn returns `model=claude-opus-4-8`. Codex MCP
(gpt-5.5 xhigh): design GO → impl NO-GO (compact-secret miss + command-string
strictness) → GO after fixes.

## v0.4.18 (2026-06-14)

Default model is now **Claude Opus 4.8** — with correct pricing and a safety
net so the bump can't regress anyone who lacks 4.8 access. Plus three
backlog fixes. Built with the same zero-regression discipline (characterization
tests + annotated deliberate flips); reviewed by Codex MCP (gpt-5.5 xhigh)
across the design and both implementation batches.

### 🆕 Default model: Claude Opus 4.7 → 4.8

- `DEFAULT_MODEL`, the `opus` alias, the model picker, the `aris setup` default,
  and the subagent `DEFAULT_AGENT_MODEL` all move to **`claude-opus-4-8`**. The
  friendly-name map keeps a `claude-opus-4-7` entry, so explicitly pinning 4.7
  still renders a clean name.
- **Availability fallback (4.8 → 4.7).** Bumping the default must not break
  users whose account lacks Opus 4.8. If the initial request returns
  `404 not_found_error` ("model unavailable"), ARIS automatically falls back to
  `claude-opus-4-7` for the session, **rebuilds the system-prompt model identity
  so it stays coherent** (the model is never told it is 4.8 while serving 4.7),
  warns once, and retries — for the main session (text + JSON) and for
  subagents. The fallback fires only on that precise 404 signal (never on 400 /
  rate-limit / auth), latches to avoid loops, and the text path rebuilds from a
  pre-turn session snapshot so the retry never double-appends the user message.
  Users *with* 4.8 access are byte-identical to a plain bump (the fallback never
  fires).

### 💰 Correct Anthropic pricing (was a 3–5× over-estimate)

Verified against Anthropic's published schedule. The registry had been pricing
both Opus and Sonnet at the **deprecated** Opus-4 tier ($15/$75):

- **Opus 4.5–4.8** → `$5 / $25` input/output (`$6.25` cache write, `$0.50`
  cache read). The deprecated **Opus 4.0 / 4.1** keep `$15/$75`; the split uses
  word-boundary matching so a future minor like `opus-4-10` is never
  mis-classified as 4.1.
- **Sonnet 4.x** → `$3 / $15` (was `$15/$75`), decoupled from the generic
  unknown-model fallback (which stays `$15/$75` as a conservative estimate —
  zero behavior change for unrecognized models). Haiku was already correct.

### 🧹 Backlog

- **Codex MCP reviewer pinned to xhigh.** `aris setup` option 10 now writes
  `mcpServers.codex` args `["mcp-server", "-c", "model_reasoning_effort=\"xhigh\""]`,
  so the zero-API-key reviewer runs at xhigh deterministically — independent of
  `~/.codex/config.toml` — even for an ad-hoc `mcp__codex__codex` call that omits
  a per-call config. Only new setups are touched (the idempotent merge never
  clobbers an existing entry); the reviewer system-prompt nudge dropped its
  stale "xhigh from ~/.codex/config.toml" claim.
- **Misconfig hint ([#259](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/259)).**
  A malformed `~/.config/aris/config.json`, or a misplaced/wrong-format stray
  (`~/.aris/config.yaml`, YAML/nested keys, …), was silently swallowed — your
  settings ignored with no clue why. ARIS now surfaces a one-line hint at
  startup (stderr only, so `--print`/JSON stdout stays clean) and as an "ARIS
  config" check in `aris doctor`, naming the correct flat-JSON path + keys.
  `load()` is unchanged (still degrades to defaults) — the hint is purely
  additive diagnostics.
- **Honest hook-events summary.** The runtime only dispatches
  `PreToolUse`/`PostToolUse`, but `aris init` writes
  `SessionStart`/`SessionEnd`/`UserPromptSubmit`/`PostToolUseFailure` hooks and
  the system-prompt summary listed them all — telling the model dead hooks
  exist. The summary now marks non-dispatched events **"PARSED ONLY … will NOT
  run"**. Pure prompt text; no hook execution change. Actually firing those
  events (full event expansion) is deferred to a separate issue (needs lifecycle
  dispatch + a behavior change for everyone who ran `aris init` + payload-contract
  validation).

### Tests

CI mode (`--test-threads=1`): **api 32 / runtime 202 / tools 67 / aris-cli 166 /
commands 5** — all green. New: model-availability detection (`ApiError` /
`RuntimeError`), `price_opus_legacy` tier-split lock, `diagnose_misconfig`
matrix, hook-summary parsed-only marking — plus the deliberate flips
(pricing values, `opus` alias) annotated in place. Live smoke: a one-shot turn
on the new default returns `model=claude-opus-4-8` end-to-end. Reviewed by Codex
MCP (gpt-5.5 xhigh): design REWORK→GO, impl NO-GO (duplicate-message)→GO, batch-2 GO.

## v0.4.17 (2026-06-10)

The **MCP release**: user-configured `mcpServers` finally drive real tool
dispatch — and `aris setup` can now configure a **zero-API-key Codex MCP
reviewer** (ChatGPT subscription) in one step. Plus hooks schema fidelity
with matcher filtering and per-hook timeouts, and a batch of long-tail
robustness fixes. Built with the v0.4.16 zero-regression methodology:
24 new characterization tests locked current behavior first (commit
`90c8c91` = rollback anchor) and every deliberate behavior flip is
annotated in the test that locks it. Reviewed phase-by-phase by Codex MCP
(gpt-5.5 xhigh) across 17 rounds (R1–R17, 7 NO-GOs all resolved; R17 = the
real-machine push-gate hardening below); design trail in
`idea-stage/v0.4.17/`.

### 🆕 MCP tool dispatch is real now (M1/M2)

Before v0.4.17, `mcpServers` in `settings.json` parsed, showed in
`aris doctor` — and did nothing. Now:

- **Tools enter the model's catalogue.** On startup ARIS spawns each
  configured stdio server, runs the MCP handshake, discovers tools, and
  advertises them as `mcp__<server>__<tool>` alongside the built-in tools
  on **both** provider paths (Anthropic and OpenAI-family executors).
- **Calls dispatch end-to-end.** The executor routes `mcp__*` calls
  through the managed server process and returns the tool result
  (text blocks flattened; `isError` mapped to a tool error).
- **Per-server failure degrades softly.** A server that fails to spawn /
  initialize / list is skipped with a one-line warning and recorded for
  `aris doctor`; healthy servers keep working (previously an all-or-
  nothing discover). Server stderr no longer pollutes the terminal
  (`ARIS_MCP_STDERR=inherit` restores pass-through).
- **Approval gate.** MCP servers are external processes — the sandbox
  does not cover them — so untrusted MCP tool calls prompt for
  confirmation even under `danger-full-access` (allow once / always for
  this server this session / deny). `mcpServers.<name>.trust: true`
  skips the prompt; non-interactive runs deny untrusted MCP tools with a
  clear error. `--allowedTools` now accepts `mcp__` names (deferred
  validation), and advertising and dispatch share one filter.
- **`aris doctor`** shows real per-server status (spawned / initialized /
  tool count / failure reason / trust) instead of the old placeholder
  warning, and discloses the legacy `~/.claude.json` vs
  `<config_home>/settings.json` path split.
- **Subagents deliberately get no MCP tools** in this release (pinned by
  test); revisited in v0.4.18 with P8 full routing.

### 🔴 Protocol fix the fakes couldn't catch: NDJSON framing

Real-machine e2e against `codex mcp-server` exposed that our stdio
transport spoke LSP-style `Content-Length:` framing while the MCP spec
(and codex) use **newline-delimited JSON-RPC** — codex silently ignored
every frame and discovery timed out. Every prior MCP test passed because
the fake servers spoke the same wrong dialect. Fixed: writes are NDJSON;
reads auto-detect both dialects (legacy `Content-Length:` servers still
work, with the M6 tolerances — LF-only, case-insensitive header, 64 MiB
cap — preserved on that path). A full NDJSON protocol-handshake
regression test now locks the real dialect, verified end-to-end against
codex (`initialize → notifications/initialized → tools/list → tools/call`).

Also hardened while in there: the spec-mandated `notifications/initialized`
is now sent after initialize (strict servers refuse `tools/list` without
it), and `request()` writes/reads concurrently with a select-based
round-trip (a large request no longer deadlocks against a server that
writes before reading — the failure mode behind [#286](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/286);
a failed write now short-circuits immediately instead of waiting out the
timeout).

### 🆕 `aris setup` option 10: Codex MCP reviewer, zero API key

The reviewer menu gains **`10. Codex MCP (ChatGPT subscription, no API
key)`** — the recommended path. Selecting it detects the codex CLI,
writes an idempotent `mcpServers.codex` entry into the settings file the
runtime actually reads (atomic write + backup; existing entries never
clobbered; a write failure aborts without touching your reviewer
config), asks explicit consent before setting `trust: true`, and
optionally configures an API reviewer as **fallback** — tracked in a new
`reviewer_fallback_provider` field so MCP stays primary
(`ARIS_REVIEWER_PROVIDER=codex-mcp` + `ARIS_REVIEWER_FALLBACK_PROVIDER`).
`LlmReview` resolves the fallback automatically, and an API reviewer's
missing-credential error points at both escape hatches (subscription via
option 10, or an API reviewer) — except when Codex MCP is primary with no
fallback, which now gets a Codex-specific message (see push-gate hardening
below). `/setup` inside the REPL now rebuilds
the system prompt and runtime unconditionally, so reviewer changes take
effect without quitting (new MCP servers still need a restart — ARIS
tells you when).

### 🆕 Hooks: schema fidelity, matcher filtering, per-hook timeout

- Object-style Claude Code hooks (`{matcher, hooks:[{type, command,
  timeout}]}`) no longer flatten to bare command strings: **matcher**,
  **timeout**, and **async** are preserved. Metadata parses leniently —
  wrong JSON types degrade to `None`, never a load error; any
  settings.json that loaded yesterday loads today.
- **Matcher filtering**: PreToolUse/PostToolUse hooks run only when the
  anchored regex matches the tool name (`"Edit"` matches Edit, not
  MultiEdit; `"Edit|Write"` works). Missing/empty matcher = match-all
  (existing behavior; `aris init` meta_opt hooks unaffected). An invalid
  pattern warns once and falls back to literal matching.
- **Per-hook timeout** — ⚠️ *behavior change*: hooks are now killed after
  **30 s by default** (previously ARIS waited forever); the hook's
  `timeout` field (seconds, clamped 1–600) overrides. Timeout is a
  **warning, not a deny** — tool execution continues (a blocking hook
  must exit 2 within budget). The direct child is killed and reaped;
  grandchildren a hook backgrounds itself are not torn down.
- `async: true` is parsed and stored but **not yet executed**
  (known-unsupported; honest in the schema, on the v0.4.18 list).

### 🧹 Long tail

- **`ARIS_DISABLE_KEYCHAIN`**: skips the macOS Keychain OAuth fallback
  (auth + `aris doctor`) — for GUI-less macs, CI, and dev machines where
  the real Claude Code credential made `api` tests nondeterministic
  (the 7 locally-failing tests are green for the first time since
  v0.4.15).
- **CL2**: Anthropic clean-EOF now also accepts a `message_delta` with a
  non-empty `stop_reason` as the terminal signal (symmetric with the
  v0.4.15 OpenAI `finish_reason` fix) — anthropic-compat proxies that
  never send `message_stop` no longer misclassify completion as
  truncation. Reads are not stopped early; retry semantics unchanged.
- **OE6**: OpenAI tool-call deltas missing an `index` now merge by `id`
  when one matches (slot-0 fallback retained otherwise). **OE5**: stream
  usage parsing accepts `input_tokens`/`output_tokens` variants.
- **Slash commands enter history** (in-memory + disk, `/exit` and
  `/quit` excluded, secret-skip applies) — a deliberate flip of the
  v0.4.16 convention.
- The OpenAI-family subagent fail-loud guard now says v0.4.18 (P8 full
  routing moved there so this release stays MCP-focused).

### 🩹 Real-machine push-gate hardening (the zero-API-key reviewer's first run)

Dogfooding the new Codex MCP reviewer end-to-end surfaced three rough
edges in the *first-impression* path — all UX, no protocol change:

- **No more notification spam.** codex emits dozens-to-hundreds of
  `codex/event` progress notifications per call; ARIS logged one
  `aris mcp: notification skipped` stderr line per frame, flooding the
  REPL on every review. The trace is now gated behind the existing
  `ARIS_MCP_STDERR=inherit` debug flag (read once per round-trip) and
  silent by default — control flow is unchanged, notifications are still
  skipped and the read loop still waits for the id-bearing response.
- **Don't let the model override Codex's model.** The system prompt for a
  Codex MCP reviewer now tells the model **not** to pass a `model`
  parameter — a ChatGPT-subscription Codex rejects arbitrary names (e.g.
  `gpt-5.2`) and the call fails until retried without it. Codex uses your
  account default (gpt-5.5 + xhigh from `~/.codex/config.toml`).
- **Accurate error when Codex MCP is primary with no fallback.** Calling
  `LlmReview` in this state previously fell through to the OpenAI-compat
  path and complained that `OPENAI_API_KEY` was unset for `gpt-5.5` —
  a credential and model the user never opted into. It now returns a
  clear message directing them to invoke `mcp__codex__codex` directly
  (and names no phantom credential).

### Tests

CI mode (`--test-threads=1`): **runtime 199 / aris-cli 165 / tools 67 /
api 30 / commands 5** — all green, including the Phase 0
characterization suite (deliberate flips annotated in-place). E2E:
zero-API-key `mcp__codex__codex` call returns a literal round-trip
through a real ChatGPT-subscription codex server; no-MCP baseline
byte-equivalent; `aris setup` option 10 PTY smoke passes.

**Deferred to v0.4.18**: P8 full OpenAI-family subagent routing (design
in `idea-stage/v0.4.16/p8_design.json`), MCP `protocolVersion` bump to
2025-06-18 (negotiation works today), hook `async` execution + event
expansion (SessionStart…), process-tree teardown on hook timeout,
`~/.aris/config.yaml` misconfig hint ([#259](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/259) follow-up).

## v0.4.16 (2026-05-30)

A **REPL UX + provider-hardening** release built on a zero-regression
discipline: before any refactor, 64 characterization ("golden") tests were
written to lock the *current* behavior of every provider-routing, pricing,
reviewer, subagent, and REPL surface the changes would touch; those tests
stayed green through every subsequent commit, so a regression would have
failed at the source. Reviewed phase-by-phase by Codex MCP (gpt-5.5 xhigh)
plus a final integration pass. Design + the full 96-case behavior matrix:
`idea-stage/v0.4.16/{plan.md,design_raw.json,p8_design.json}`.

### 🆕 REPL command history + Ctrl+R search ([#274](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/274))

Two purely-additive interactive-shell features (Up/Down history navigation
already worked in-session; this adds the rest):

- **Cross-session persistence** — submitted prompts are saved to
  `~/.config/aris/history` and reloaded on startup, so history survives
  restarts. The file is `0600`; an `ARIS_NO_HISTORY` env var is a
  kill-switch (load + save become no-ops); a **disk-only** secret-skip
  heuristic refuses to persist a line that looks like a credential
  (`sk-…` key shape, known credential env names incl. AWS, `password=` /
  `api_key:` / `--api-key value` forms, long high-entropy tokens) — the
  line still enters in-memory history (so in-session Up/Down is
  unchanged), only the on-disk copy is withheld. Best-effort: a write
  failure never breaks the REPL.
- **Ctrl+R reverse incremental search** (`(reverse-i-search)\`query':`,
  bash-style): type to narrow, Ctrl+R for the next older match, Enter to
  load the match into the buffer (you still press Enter to submit), Esc /
  Ctrl+C / Ctrl+G to cancel and restore. CJK/wide-char-aware single-line
  rendering; no new dependency (built on the existing crossterm input
  layer). No existing key binding or render path changed.

### 🔒 OpenAI-family subagents now fail loud (stops a credential leak)

Previously, when the main session used an OpenAI-family executor
(Kimi / GLM / Gemini / MiniMax / OpenAI / …), spawning a sub-agent would
**silently fall back to building an Anthropic client and bill the user's
Anthropic OAuth/Keychain credential** with a wrong model name. The
sub-agent runtime now detects this (`EXECUTOR_PROVIDER == "openai"`) and
returns a clear error instead — *"subagents currently require an
Anthropic-family executor; OpenAI-family subagent dispatch lands in
v0.4.17. Your main session is unaffected."* — carrying no credential
names. Anthropic-family executors (native + anthropic-compat) are
completely unaffected (their `EXECUTOR_PROVIDER` is never `"openai"`, so
the guard cannot fire). Full OpenAI-family sub-agent **routing** is a
larger cross-crate change (lowering the OpenAI executor into a shared
crate) scheduled for v0.4.17; this release closes the credential-leak
window in the meantime.

### 🧱 Provider-classification groundwork (no behavior change)

- The three byte-identical word-boundary matchers
  (`openai_executor::word_match`, `usage::has_word`,
  `tools::reviewer_word_match`) are consolidated into one canonical
  `runtime::word_match`; the three former functions now forward to it, so
  every call site and every routing/pricing/reviewer truth value is
  unchanged. (`usage::provider_match`, a different and more permissive
  matcher, is deliberately left separate.)
- A new `runtime::ProviderFamily` classifier
  (`AnthropicNative` / `AnthropicCompat` / `OpenAiCompat` / `Unknown`,
  exact-match) names the executor families as a *pure type* — it reads no
  env, picks no endpoint, and is wired into no routing yet (P8 / v0.4.17
  will consume it). `Unknown` is intentional so a future dispatch can't
  misclassify an unrecognized provider string.

### Zero-regression / tests

`cargo test` (single-threaded, CI mode): runtime 164, aris-cli 128,
tools 49, commands 5 — all green, including the 64 Phase-0
characterization tests that lock the unchanged routing/pricing/reviewer/
push_history behavior. The dangerous code (config env-writing, the
order-sensitive pricing chain, reviewer routing, `provider_match`, the
in-memory `push_history` contract, every existing key binding) is
byte-identical.

### Deferred to v0.4.17

Full OpenAI-family sub-agent routing (headless OpenAI client lowered into
the `api` crate + a `SubagentExecutorClient` enum), and the `api`-crate
`read_api_key_*` test isolation (they read the machine's real macOS
Keychain OAuth credential, so they fail locally on a box with Claude Code
installed; CI is unaffected — the real fix needs a Keychain gate, not just
a config-dir override). Hook-schema preservation + MCP manager production
wiring remain v0.4.17 scope; CL2 / OE5 / OE6 / OE8 streaming siblings and
the sandbox / rustls / JSON architecture work remain v0.5.0.

## v0.4.15 (2026-05-29)

A focused **OpenAI-compatible streaming robustness** hotfix. Closes
issue [#249](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/249):
MiniMax (and other OpenAI-compatible providers / proxies) were
effectively unusable because aris-code treated the `data: [DONE]` SSE
sentinel as the *only* authoritative stream-completion signal.

Seeded by a read-only streaming-interop audit (5-agent workflow) and
cross-reviewed by Codex MCP (gpt-5.5 xhigh) over 3 rounds
(GO-WITH-NITS → GO-WITH-NITS → GO). All changes live in one file
(`crates/aris-cli/src/openai_executor.rs`); the Anthropic SSE path is
untouched.

### 🔴 #249 — `finish_reason` is a valid completion signal

The OpenAI Chat Completions spec defines a non-empty
`choices[].finish_reason` as the model's terminal chunk; `data: [DONE]`
is an SSE-transport convention that **not every compatible provider
emits**. MiniMax sends `finish_reason: "stop"` then closes the
connection without `[DONE]`, so the clean-EOF branch — which only broke
on `observed_done` — fell through to a hard
`OpenAI stream ended prematurely without [DONE] sentinel` error on
*every* successful completion.

The clean-EOF decision is now a pure, unit-tested function:

```
stream_eof_action(observed_done, observed_finish_reason,
                  nothing_emitted, retries_remaining)
    -> { Complete, Restart, Truncated }
```

A response is **complete** when *either* `[DONE]` OR a non-empty
`finish_reason` arrived. Crucially the read loop is **not** stopped
early at `finish_reason` — a trailing usage-only chunk (emitted under
`stream_options.include_usage` between the finish_reason chunk and
`[DONE]`) is still consumed, so `/cost` accounting is unaffected.
`finish_reason` only re-classifies an *already-reached* clean EOF from
"truncated" to "complete". A genuine mid-response truncation (neither
signal seen + content already emitted) still hard-errors, and a
proxy abort before any output still restarts within the
`ARIS_STREAM_RETRY` budget. This mirrors the lenience the Anthropic
path already had (synthesize-terminal-on-missing-MessageStop).

### Coupled robustness fixes (same SSE path)

- **OE7** — `finish_reason` is now read *before* the `delta` guard. A
  terminal choice carrying only `finish_reason` and no `delta` was
  previously skipped wholesale, which would have defeated the
  completion check above.
- **OE2** — pending tool calls flush on *any* non-empty `finish_reason`,
  not just `stop`/`tool_calls`. Compatible providers send
  `length` / `content_filter` / `max_output` / `sensitive`; flushing
  here preserves in-stream ordering and per-tool terminal rendering
  (`length` / `content_filter` also print a truncated/filtered hint).
- **OE4** — a mid-stream error envelope (top-level non-null `error`,
  no `choices`) now hard-errors instead of being silently dropped by
  the `choices` guard. This closes the regression window where an
  error arriving *after* a `finish_reason` would otherwise be misjudged
  a success. Only `message` + `code`/`type` are surfaced — never the
  whole envelope.
- **OE3** — SSE `data:` parsing tolerates a missing space after the
  colon (`data:{...}`, which W3C EventSource permits and some
  compatible providers emit). The old `strip_prefix("data: ")` silently
  dropped such lines.

### Tests

`cargo test -p aris-cli`: 82 passed (was 77 at v0.4.14; **+5**).
New coverage extracts the previously-untested SSE completion logic into
pure helpers: `stream_eof_action` truth table (11 cases),
`stream_error_detail` (9), `choice_finish_reason` (6),
`accumulate_tool_call`, `sse_data_payload` (12). Mirrors the
`api/src/client.rs` `should_retry_on_premature_eof` truth-table pattern.

### Deferred to v0.4.16

The same audit surfaced lower-priority / larger siblings left for the
next release: **CL2** (Anthropic `MessageDelta.stop_reason` symmetry —
the Anthropic path is already lenient so no user is blocked), **OE6**
(tool-call slot routing by `id` for parallel calls), **OE5** (usage
field-name fallbacks), **OE8** (SSE `event:` field). The
ProviderFamily resolver (P7) and Subagent provider parity (P8) remain
v0.4.16 scope. A separate pre-existing test-isolation issue (the
`api` crate's `read_api_key_*` tests read the user's real
`~/.config/aris/config.json` instead of an isolated temp dir, poisoning
`env_lock` locally — CI is unaffected) is also tracked for v0.4.16.

## v0.4.14 (2026-05-25)

A **security-hygiene** release closing the top items from the v0.4.13
codex audit (gpt-5.5 xhigh, 6/10 NEEDS-REWORK verdict): one P0 (config
secret leak in system prompt), one P1 trivial (DeepSeek help doc), one
P1 documentation (MCP experimental status), one P2 reliability (stream
idle timeout). No headlining new feature.

Codex MCP cross-review: 4 rounds (NO-GO → GO-WITH-NITS → NO-GO →
**GO**). Findings + fixes captured in
`idea-stage/v0.4.14/audit-followup-plan.md`.

### 🔴 S9 (P0 security) — config redaction in system prompt

Before v0.4.14, `render_config_section()` dumped the merged
`settings.json` value verbatim into the system prompt sent to the LLM
provider. Anything you put in `settings.json` — `env` maps,
`mcpServers.<name>.headers.Authorization` Bearer tokens, hook command
env, `apiKey` fields, signed URL parameters — would round-trip through
the model's context window. For users running an OpenAI-compatible
proxy executor with Anthropic-format settings, that is a real
cross-vendor token leak path.

`render_config_section()` now:

- Renders a **whitelist** of top-level fields (`model`,
  `permissionMode`, `theme`, `outputStyle`, `permissions`, `sandbox`)
  with values intact, recursing into sub-trees to redact sensitive keys.
- Recursively replaces values under sensitive keys with `"[REDACTED]"`.
  Sensitive keys are matched case-insensitively on substring (`apikey`,
  `token`, `secret`, `password`, `authorization`, `headers`, `env`) and
  suffix (`_KEY`, `_SECRET`, `_TOKEN`).
- For non-whitelisted top-level fields, prints a type indicator
  (`<object: N keys>`, `<string: N chars>`, `<array: N items>`) so users
  can see the structure without leaking values.
- For `mcpServers`: shows server name + transport + a fixed
  `command=<configured>` / `command=<empty>` / `command=<unrecognized
  shape>` placeholder, plus `origin=<scheme://host[:port]>` only.
  `args`, `env`, `headers`, full URL (path/query/userinfo/fragment) are
  never rendered. URL parsing is hand-rolled with strict scheme +
  host + port validation; anything malformed → `<redacted: ...>`.
- For `hooks`: shows event name + hook count per event. Hook command
  strings are **never rendered** (they routinely embed `curl -H
  'Authorization: Bearer ...'`-style invocations).

Regression test exercises 9 distinct leak surfaces (top-level
`apiKey`/`env`, MCP `headers`/`command`/`url`-userinfo/`url`-query/
`args`, hook `command`/`env`, nested `sandbox.env`/`sandbox.apiKey`),
asserting that none of the 9 mock secrets appear in the rendered
output while whitelist fields remain visible.

URL redaction has its own targeted test covering happy paths (DNS,
IPv4, IPv6, ports) plus 7 smuggling attempts (no scheme, suspect
scheme, backslash/whitespace/control-char host, non-ASCII host,
non-digit port, empty port, IPv6 trailing garbage, IPv6 non-digit
port). MCP `command` summary and hook count both have dedicated
branch-coverage tests too.

### 🟡 P9 (P1 trivial) — DeepSeek help line pointed at the wrong path

`aris --help` printed:

```
DeepSeek:  EXECUTOR_PROVIDER=anthropic-compat EXECUTOR_BASE_URL=... aris --model deepseek-v4-pro
```

but `resolve_openai_executor_config()` only honors
`EXECUTOR_PROVIDER=openai`; the `anthropic-compat` path is configured
through `aris setup` and is **menu option 7** (not the placeholder
"option 6" the round-1 fix briefly used). Help text now points users at
`aris setup → option 7 (DeepSeek) → base URL https://api.deepseek.com/anthropic`,
which actually wires up `executor_provider="anthropic-compat"`,
`ANTHROPIC_AUTH_TOKEN`, and the correct base URL.

### 🟡 M1/M2 (P1 doc) — MCP experimental status surfaced

The v0.4.13 stdio reliability fixes (per-server timeout, JSON-RPC
notifications skip) are real, but `McpServerManager` is **not** wired
into `CliToolExecutor`'s tool dispatch yet — meaning `mcpServers`
configured in `settings.json` will be parsed, validated, and shown in
`aris doctor`, but their tool calls do not reach the LLM context. Codex
audit M1/M2 finding.

v0.4.14 surfaces this honestly:

- `aris doctor`'s MCP section now prints a yellow experimental warning
  whenever `mcpServers.len() > 0` saying full dispatch is planned for
  v0.4.16.
- README + README_CN both gain an `🔌 MCP servers (experimental)` /
  `🔌 MCP servers（实验性）` section with the same callout, plus a note
  that the Codex MCP reviewer is the exception (it goes through the
  dedicated reviewer path, not the generic MCP dispatch).

Full MCP tool dispatch is on the v0.4.16 roadmap.

### 🟢 C11 (P2 reliability) — stream idle timeout

Both streaming pipelines (Anthropic `MessageStream` and OpenAI SSE
loop) now wrap `response.chunk().await` in `tokio::time::timeout`,
configurable via `ARIS_STREAM_IDLE_TIMEOUT_SECS` (default `120`,
clamped to `[10, 1800]`; setting `0` or a negative value disables the
timeout). On idle the stream takes the same path as a mid-body
abort: restart the request if no meaningful content has been emitted
yet (Anthropic gates on `has_emitted_meaningful_content`, OpenAI on
`nothing_emitted_yet()`), otherwise return an idle-timeout error.

Closes the "aris hangs forever with no output" symptom when an upstream
HTTPS proxy holds a connection open without sending keepalives. The
parsed-env helper has 9 unit cases covering default, valid, clamp
bounds, zero/negative, parse failure, and edge boundaries.

### 🟢 H11 (P2 trivial) — sync script hint version bump

`tools/sync_main_skills.sh` final hint and inline NOTE both rolled
from `v0.4.11` (when the sync infrastructure first landed) to
`v0.4.13` (current bundle generation). Cosmetic.

### Late bundle sync (post-release `357a418`)

Tag `v0.4.14` also includes a same-day sync to main HEAD
[`7e3ab67`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/commit/7e3ab67)
that picks up:

- `tools/meta_opt/check_ready.sh` upstream fix — extracts `"ts"`
  field with `match()` before comparison (closes the same `$0 > ts`
  always-true bug ARIS-Code flagged in v0.4.13 audit followup, plus
  a pre-existing `grep -c X || echo 0` two-line-output crash that
  ARIS-Code's first patch hadn't caught — main's codex-round-1 did).
- New `/wiki-enrich` skill (fills paper TODO sections left by
  `ingest_paper`).
- Two minor SKILL.md / script refreshes (`auto-review-loop-llm`,
  `render-html`).

Bundle inventory: 76 → **77 skills**, 54 helpers unchanged. All 9
cache drift tests pass; `SKILLS_SOURCE_COMMIT` pin updated.

### Test inventory

`cargo test -p runtime --lib`: 117 passed (3 new prompt tests +
existing 9 v0.4.13 regression backfill).
`cargo test -p api --lib`: 19 passed (1 new stream-idle helper test).
`cargo test -p aris-cli`: 77 passed.
`cargo test -p tools --lib`: 35 passed.
`cargo test -p commands --lib`: 5 passed.

### Excluded from v0.4.14

Three items from the audit are deferred to follow-up releases by design
(see `idea-stage/v0.4.14/audit-followup-plan.md`):

- **P7 ProviderFamily resolver** centralization (5+ scattered
  `contains()`/`provider_match()`/`EXECUTOR_PROVIDER==openai` /
  `starts_with()` checks) — v0.4.15, scoped as a real refactor not a
  hotfix.
- **P8 Subagent provider parity** (`build_agent_runtime()` always
  binds `AnthropicRuntimeClient`) — v0.4.15.
- **Hook schema preservation** (matcher/timeout/async fields
  currently dropped) + **MCP manager production wiring** (M1/M2 real
  fix) — v0.4.16.

OpenSSL → rustls switch (L1), full sandbox hardening (S1-S6), JSON
parser standardization (C10), and provider abstraction trait remain
v0.5.0 scope. Per the v0.4.14 audit-followup plan.

## v0.4.13 (2026-05-25)

A residue-cleanup release closing every codex-audit P1 left over from
v0.4.10 through v0.4.12 plus the long-tail regression tests. No
headlining new feature — the goal is to make the existing per-server
MCP / hook / streaming code paths actually behave the way the docs
already say they do.

### 🟡 v0.4.10 audit P1.D — per-server MCP timeout

`McpStdioServerConfig` gains `request_timeout_secs: Option<u64>`,
parsed from `settings.json` as `mcpServers.<name>.requestTimeoutSecs`.
Per-server override > `MCP_REQUEST_TIMEOUT_SECS` env > 300 s default,
clamped 1..=1800 s. Useful when one Codex MCP agent legitimately
needs 5 min while a filesystem MCP must error out in 5 s — the
global env couldn't serve both.

### 🟡 v0.4.10 known limitation — JSON-RPC notifications skip

`McpStdioProcess::request()` now skips frames with absent / null
`id` (JSON-RPC notification semantics, used by `notifications/log` /
`notifications/progress`), prints
`aris mcp: notification skipped: method=…` to stderr, and continues
reading until the correlated response arrives. id-mismatch on a
response frame is still fatal (kills the child).

### 🟢 meta_opt hook deploy via `aris init`

`tools/meta_opt/{log_event,check_ready}.sh` are now bundled. `aris
init` deploys them to `~/.claude/hooks/` as
**`aris-meta-opt-log-event.sh`** and **`aris-meta-opt-check-ready.sh`**
(ARIS-namespaced — codex round-1 #1 caught that plain names would
silently clobber user hooks). Entries are merged into
`~/.claude/settings.json`'s `hooks.PostToolUse` /
`PostToolUseFailure` / `UserPromptSubmit` / `SessionStart` /
`SessionEnd` array (de-duped against existing — idempotent).
Backups go to `settings.json.bak.<unix-millis>` with hard-fail
semantics (codex round-1 #2: never silently destroy state). Final
rewrite is atomic via tempfile + rename.

### 🧪 v0.4.12 targeted regression coverage (9 new tests)

Codex's v0.4.12 round-3 left a debt of "no targeted tests for the new
fixes". Closed here:

- `sandbox::tests`: `strict_mode_overrides_llm_disable`,
  `strict_mode_ignores_all_five_llm_overrides`,
  `default_non_strict_honors_llm_overrides`
- `config::tests`: `parses_sandbox_strict_mode`
- `usage::tests`: `provider_match_distinguishes_real_vs_userdefined`
- `openai_executor::tests`: `word_match_handles_provider_prefixes`,
  `is_stream_options_unknown_field_error_classification`
- `client::tests`: `event_is_meaningful_content_classification` +
  v0.4.13 `should_retry_on_premature_eof_truth_table` (codex round-1
  #3 closed the "end-to-end retry trigger" gap by extracting the
  5-condition retry guard into a pure fn so the truth table is
  directly testable without mocking `reqwest::Response`)
- `tools::tests`: `reviewer_word_match_provider_prefix`

### 📦 Skills source-of-truth Gemini fix (`origin/main`)

The `auto-gemini-3` MCP alias fix v0.4.11 and v0.4.12 had to re-apply
to the bundle after every `sync_main_skills.sh` run is now in
`origin/main` (`fedf361`): `skills/gemini-search/SKILL.md`
DEFAULT_MODEL + literal in the Gemini-search MCP call,
`skills/research-lit/SKILL.md` Gemini source MCP call. Next sync
stays correct. `SKILLS_SOURCE_COMMIT` advanced from `d5f450c` to
`fedf3612b696bd34f21d349d1859668983e6f4aa`.

### 📦 Bundle

`Embedded 76 bundled skills, 54 helper resources` (+2 from
`meta_opt/{log_event,check_ready}.sh`).

### 📐 Cross-model review

Codex MCP (gpt-5.5 xhigh):
- subagent dispatch + parallel implementation → 4 commits (plan +
  3 subagent outputs c7afa95 / ffff3fa / b8cbcbd)
- round-1 final diff: NO-GO + 3 findings (hook clobber, settings.json
  non-atomic + best-effort backup, missing EOF-retry regression test)
- round-2 (after `428b73f`): NO-GO + release-metadata-not-bumped —
  fixed in this commit
- round-3: post-bump confirmation pending

### ⚠️ Known limitations deferred to v0.4.14

- `tools/meta_opt/check_ready.sh` uses `awk '$0 > ts'` to filter
  events since the last optimize, which compares whole JSONL lines
  (start with `{`) against an ISO timestamp string and effectively
  always matches. The bundled file is byte-exact from `origin/main`,
  so the fix needs to go to main first then sync.
- #240 README chapter numbering / further compression.
- v0.5.0+ architectural work (provider abstraction, OpenAI Responses
  API, complete MCP transport stack, sandbox hardening).

## v0.4.12 (2026-05-22)

A bug-fix + small-feature release polishing several rough edges that
surfaced in v0.4.10's Codex audit + community-reported issues since
v0.4.11 shipped. Headlining the sandbox-config priority fix (#238),
plus the four streaming/pricing P1 follow-ups deferred from v0.4.10.

### 🚨 P0 — user-reported bugs

- **#238 `sandbox.strictMode` config option** — `SandboxConfig` gains
  `strict_mode: Option<bool>` (parsed from `settings.json` as
  `sandbox.strictMode`). When `true`, `resolve_request()` ignores **all**
  LLM-supplied overrides — `dangerouslyDisableSandbox`,
  `namespaceRestrictions`, `isolateNetwork`, `filesystemMode`,
  `allowedMounts` — and uses only what the user configured. Closes the
  gap where a LLM could silently bypass the user's strict sandbox by
  passing `dangerouslyDisableSandbox: true`. Default is `false`
  (opt-in) for backward compatibility; explicitly set `strictMode: true`
  to hard-lock. The bash tool schema now documents this on the
  `dangerouslyDisableSandbox` field, and `aris doctor` reports the
  effective sandbox configuration. A one-shot per-process stderr
  warning fires when a strict config silently overrides an LLM request.

- **#232 `auto-review-loop-llm` DeepSeek deprecation** — Provider table
  and config examples updated from `deepseek-chat` / `deepseek-reasoner`
  to `deepseek-v4-flash` / `deepseek-v4-pro`. DeepSeek announced the
  legacy aliases deprecate 2026-07-24, and R1-class reasoner models
  reject `tool_choice` (which the auto-review loop requires). The
  `aris setup` reviewer menu was also updated.

### 🟡 P1 — v0.4.10 audit follow-ups (Codex GPT-5.5 xhigh)

- **P1.A Anthropic stream retry coverage** — `MessageStream` gains
  `has_emitted_meaningful_content: bool` next to the existing
  `events_emitted` counter. The whole-stream retry now triggers when
  no meaningful content has been emitted, not just when *no* event
  has. This means a stream that only sent `MessageStart` before EOF
  is now retry-eligible. Meaningful = non-empty text/thinking, any
  `InputJsonDelta`, any `ContentBlockStop`, or any `ContentBlockStart`
  for `ToolUse`/non-empty Text/non-empty Thinking. `ToolUse` start
  is conservatively counted (per Codex round-3) because the caller
  commits `pending_tool` state on receipt.

- **P1.B o-series reasoning effort detection (provider-prefixed)** —
  Both the executor (`openai_executor.rs::supports_reasoning_effort`)
  and the reviewer mirror (`tools/lib.rs::reviewer_supports_reasoning_effort`)
  now use word-boundary matching (boundary = `-_/:` + start/end).
  `openai/o3-mini`, `proxy:o4` and similar provider-prefixed names
  are now recognised. Previously `starts_with("o3")` missed them and
  the request omitted `reasoning_effort`.

- **P1.C `stream_options.include_usage` proxy fallback** — When the
  OpenAI executor's request returns `400` with an error body that
  fingers `stream_options` as an unknown/extra field (strict
  matcher: JSON `error.param.starts_with("stream_options")` OR body
  containing both `stream_options` and one of
  `unknown`/`unrecognized`/`extra`/`additional`/`unsupported`/
  `not allowed`/`invalid field`), the executor retries once without
  the field. Sacrifices prefix-cache token reporting for
  compatibility with compat-mode proxies. Real OpenAI, vLLM, SGLang,
  OpenRouter all accept `stream_options` so this only fires on
  noncompliant proxies.

- **P2 pricing match precision** — `runtime/usage.rs` switched from
  `contains()` to a new `provider_match()` helper for `kimi`,
  `moonshot`, `mimo`, `qwen`, `glm`, `minimax`, `doubao`. The new
  helper matches at the start of the model name or after a `/`/`:`
  provider separator. This catches `qwen3.6-plus`, `kimi-k2.5`,
  `glm-4-plus` etc. (which the boundary-based `has_word` would have
  missed because digits aren't word boundaries), while rejecting
  mid-word matches like `my-kimi-clone`.

### 🔧 v0.4.11 follow-ups

- **`build.rs` skills-codex glob** — `EXCLUDED_SKILL_PREFIXES` exact
  match list collapsed to a single `EXCLUDED_SKILL_PREFIX = "skills-codex"`
  with `starts_with()` semantics. Future `skills-codex-*` mirror
  variants are now auto-excluded without code change.

- **`build.rs` ALLOWED_EXTS gains `html`** — Required because the
  newly bundled `/render-html` skill ships `.html` template files
  under `skills/render-html/scripts/templates/`. Without this, the
  templates didn't make it into the binary and `/render-html
  --template academic` would fail at runtime.

- **CI `fetch-depth: 0` + origin/main fetch** — Both `ubuntu` and
  `macos` jobs in `.github/workflows/ci.yml` now do a full-depth
  checkout and explicitly fetch `origin/main` so the
  `skills_source_commit_pin_present_and_well_formed` drift test's
  optional ancestor check actually runs in CI (was silently skipping
  before due to shallow checkout).

### 📦 Skills sync追新

`SKILLS_SOURCE_COMMIT` advanced from v0.4.11's `ed638f3` to the
current `main` HEAD. Inventory:

- **Bundle skills**: 74 → 76 (+`/interview-cheatsheet`, +`/render-html`)
- **Helper resources**: 49 → 52 (+`render_html.py`,
  +`academic.html`, +`dashboard.html` under
  `skills/render-html/scripts/`)
- **Gemini MCP alias re-applied** — `gemini-search` and `research-lit`
  v0.4.11's `auto-gemini-3` patch was reverted by sync (rsync
  `--delete` overwriting hand-patched files). Re-applied; main-branch
  PR pending.

### 📐 Cross-model review

Codex MCP (gpt-5.5 xhigh) reviewed four rounds:
- round-1: plan v1 → GO-WITH-CAUTION + 8 findings → plan v2
- round-2: plan v2 → GO-WITH-CAUTION + 3 implementation precision
  findings → plan v3
- round-3: final diff → NO-GO + 5 findings → all addressed
  (`ContentBlockStart::ToolUse` conservative classification,
  Cargo/CHANGELOG/README version bump, untracked new skills tracked,
  doctor multi-field detection, setup UI DeepSeek alias fixed)
- round-4: post-fix confirmation → GO

Plan committed at `idea-stage/v0.4.12/plan.md` (round-1/2/3 review
history recorded inline as `v2 修订` / `v3 修订` sections).

### ⚠️ Known limitations deferred to v0.4.13

- P1.D per-server MCP timeout (per-`ScopedMcpServerConfig` field)
- JSON-RPC server notifications (`id == null` skip) in `mcp_stdio.rs`
- `meta_opt/{log_event,check_ready}.sh` hook deploy via CLI init
- #240 README章节层级 + 进一步精简
- Comprehensive new-fix unit tests (current coverage: cache 9/9 +
  sandbox 5/5 pass, but P1.A/B/C/P2/#238 changes don't yet have
  targeted regression tests)

## v0.4.11 (2026-05-18)

The skills bundle refresh / research workflow sync release. The binary
runtime behaviour is essentially unchanged from v0.4.10 — what shipped
new is the **embedded skills set** catching up to the current state of
the `main` skills branch. Closes the gap that built up during the
v0.4.5 → v0.4.10 maintenance cycle (only ~6 of 56 main commits in
`skills/` had been cherry-picked into the bundle).

### 📦 Bundle inventory

**Embedded skills**: 65 → 74 user-facing skills (+10 new, refreshed
46 existing SKILL.md files). New skills:

- `/citation-audit` — fourth-layer bibliography audit (existence +
  metadata + cited-context coverage)
- `/experiment-queue` — SSH job queue for multi-seed / multi-config
  experiments with OOM-aware retry, stale-screen cleanup, wave
  transitions
- `/gemini-search` — Gemini-backed broad literature discovery
- `/kill-argument` — two-thread adversarial review (reject memo →
  defence → unresolved critical issues)
- `/openalex` — OpenAlex API source for open citation graph + funding
- `/overleaf-sync` — two-way sync between local paper directory and
  an Overleaf project via the Git bridge (token-safe via Keychain)
- `/paper-talk` — end-to-end conference talk pipeline (outline →
  Beamer + PPTX → per-page polish → assurance)
- `/qzcli` — manage Qizhi (启智) platform GPU jobs (kubectl-style)
- `/resubmit-pipeline` — W5 workflow: text-only paper resubmit to a
  different venue under hard constraints + kill-argument gate
- `/slides-polish` — per-page Codex review + targeted python-pptx /
  Beamer fixes for academic talk slides

**Embedded helpers**: 34 → 49 helper resources. tools/ goes 9 → 18:
the 9 baseline helpers are *refreshed* (notably `research_wiki.py`
grew 315 → 767 lines with the canonical `ingest_paper` API) and 9
new helpers ship for the new skills:

- `extract_paper_style.py` — used by 7 paper-series skills when
  `— style-ref: <source>` is passed
- `figure_renderer.py` — used by `/figure-spec`
- `paper_illustration_image2.py` — used by `/paper-illustration-image2`
- `overleaf_setup.sh` + `overleaf_audit.sh` — `/overleaf-sync`
  Premium-feature integration
- `verify_wiki_coverage.sh` — wiki coverage helper
- `watchdog.py` — `/experiment-queue` watchdog
- `experiment_queue/build_manifest.py` +
  `experiment_queue/queue_manager.py` — `/experiment-queue`
  orchestration

`shared-references/` gains `assurance-contract.md` and
`wiki-helper-resolution.md`; the existing 5 shared references all
refreshed.

### 🔧 Sync infrastructure (new)

- `tools/sync_main_skills.sh` — automated rsync from `origin/main`
  with symlink pre-flight, deterministic codex-mirror prune,
  full-helper whitelist, source-commit SHA pinning.
- `crates/runtime/assets/SKILLS_SOURCE_COMMIT` — records the main
  commit that this bundle was rsync'd from, so drift between
  releases can be tracked.
- New CI drift tests in `crates/runtime/src/cache.rs`:
  - `skills_source_commit_pin_present_and_well_formed` — hard-fails
    if the source-commit file is missing or malformed; best-effort
    ancestor check when `origin/main` is resolvable.
  - `skill_md_aris_tools_and_repo_refs_resolve_to_bundled` —
    extends existing inventory test to `.aris/tools/<helper>` and
    `${ARIS_REPO}/tools/<helper>` resolver patterns (codex
    round-3 caught these were uncovered).
  - `skill_md_cross_skill_references_bundled_warn_only` —
    warn-only scan for inter-skill `/<name>` references; run with
    `-- --nocapture` to see the warnings.

### 🔧 Gemini alias correction

`research-lit/SKILL.md` Gemini MCP call now passes
`model: 'auto-gemini-3'` instead of the historical `gemini-2.5-pro`
(silently routed through OAuth-personal capacity exhaustion since
gemini-3 GA). The 5 references in `paper-illustration/SKILL.md`
are direct REST URLs (`generativelanguage.googleapis.com/...`)
where `auto-gemini-3` is not a server-side model ID, so those
stay on the explicit `gemini-3-pro-preview` / `gemini-3-pro-image-preview`.

### ⚠️ What did NOT change in v0.4.11

- **No CLI runtime / API client changes.** v0.4.10 audit's 4 P1
  follow-ups (Anthropic stream retry coverage, o-series reasoning
  effort, OpenAI `stream_options` proxy fallback, per-server MCP
  timeout) are still pending — pushed to v0.4.12.
- **No reviewer default change.** `gpt-5.5` has been the CLI
  default since v0.4.5 (commit `87e1088`); main's `d43d77a`
  brought `skills/` docs in line with that, so the bundle now
  consistently shows `REVIEWER_MODEL = gpt-5.5` in SKILL.md
  examples. Users who pin `ARIS_REVIEWER_MODEL=gpt-5.4` continue
  to override unchanged.
- **No `meta_opt/` hook bundling.** `tools/meta_opt/log_event.sh`
  and `check_ready.sh` are SessionEnd hooks that need a deploy
  mechanism, not on-demand extraction. Deferred to v0.4.12
  alongside a CLI hook-install path.
- **No skills-codex mirror in binary.** The 3 `skills-codex*/`
  directories in main are for the Codex CLI agent install path,
  not user-facing skills. `build.rs` already excludes them and
  `sync_main_skills.sh` prunes them post-rsync.

### 📐 Cross-model review

Codex MCP (gpt-5.5 xhigh) reviewed every step:
- round-1 (plan): REQUEST CHANGES (8 findings)
- round-2 (plan v2): APPROVE WITH NITS (7 nits)
- round-3 (plan + sync_script + drift_tests drafts): NO-GO
  (5 blocking findings — missing baseline helper refresh,
  incomplete drift coverage, fetch race, draft notation,
  stale paths)
- round-3.5 (after fixes): GO with 4 watch-outs (all addressed)

Three drift-test cross-skill warnings remain (informational, warn-only
test). They are not bundle misses:

- `/experiment-bridge -> /codex` — refers to the `mcp__codex__codex`
  MCP tool name, not an ARIS skill (regex false positive).
- `/paper-compile -> /codex` — same.
- `/kill-argument -> /peer-review` — `/peer-review` is a planned
  v0.5.0+ skill, intentionally referenced in the rebuttal pipeline
  before it ships.

## v0.4.10 (2026-05-17)

The stream + MCP reliability release. Closes three classes of stalls
and degraded UX users reported against v0.4.8 and v0.4.9: the
`#228`-style "error decoding response body" mid-stream loop, the
`#151` / `#172` "Calling codex..." MCP hangs, and silently inaccurate
cache / cost reporting after v0.4.5+ when more providers were added.

### 🚨 Fix (streaming reliability — C6)

- **Whole-stream restart on chunk abort / premature EOF** —
  `MessageStream::next_event` (Anthropic) and the OpenAI executor's
  SSE loop now both detect (a) chunk decode failure mid-flight and
  (b) Ok(None) before any terminal sentinel (`MessageStop` /
  `[DONE]`), and restart the *whole request* from scratch. Restart
  budget is `ARIS_STREAM_RETRY` (default 2, clamped 0..=5 via
  `u32.min(5) as u8`), and only fires when `events_emitted == 0` so
  the user never sees torn output. Backoff is 500 ms between
  attempts. `stream_chunk_error_is_retryable()` predicate gates on
  `is_request / is_connect / is_timeout / is_body / is_decode`.

### 🚨 Fix (MCP stdio reliability — M3)

- **Default 300 s read timeout via `tokio::time::timeout`** wrapping
  both `send_request` and `read_response`. Override via
  `MCP_REQUEST_TIMEOUT_SECS` env, clamped to 1..=1800 s. Default
  raised from the codex-audit-suggested 60 s to 300 s because the
  most common MCP servers users wire in are agent-style (codex,
  oracle) and 60-180 s of model think time before the first
  response byte is normal.
- **`response.id ↔ request.id` correlation check**. Mismatch returns
  `InvalidData` and kills the child so the connection respawns
  clean.
- **Dead-process detection in `ensure_server_ready()`** via
  `try_wait()`. Crashed / OOM-killed / timed-out MCP servers are
  transparently respawned on the next call instead of stalling on a
  dead pipe.
- **All failure paths use `kill().await`** (not `start_kill()`) so
  the child is reaped, no zombie window where the manager could see
  `Ok(None)` from `try_wait` and reuse a poisoned pipe.
- 3 new regression tests:
  `rejects_response_with_mismatched_id`,
  `times_out_when_server_does_not_respond`,
  `manager_respawns_dead_server_on_next_discovery`.
- Known limitation deferred to v0.4.11: server-initiated JSON-RPC
  notifications (`notifications/log`, `notifications/progress`)
  are currently treated as invalid responses; a read loop that
  skips frames without an `id` until the correlated response
  arrives is the v0.4.11 follow-up.

### 🚨 Fix (cache token accounting — C8 / P4)

- **OpenAI streaming requests** now include
  `stream_options: { include_usage: true }`. Without this the SSE
  default omits the usage block entirely. The chunk parser now
  reads `prompt_tokens_details.cached_tokens` and routes it to
  `cache_read_input_tokens` so REPL prompt-cache reporting works
  for gpt-5.5 / gpt-5.4 / -mini.
- **Anthropic streaming** stashes `MessageStart.message.usage`
  (carries `input_tokens` + `cache_read_input_tokens` +
  `cache_creation_input_tokens`) and merges it with
  `MessageDelta.usage.output_tokens` at end-of-stream. Previously
  only the delta was read, so the input/cache halves were silently
  dropped.
- `Usage` struct fields are now `#[serde(default)]` so Anthropic's
  partial usage payloads (e.g. delta carrying only output) parse
  cleanly without losing the surrounding event.

### ✨ Feature (multi-provider pricing registry — C9)

`pricing_for_model()` extended from "Sonnet + Opus default" to a
full registry:

- **OpenAI**: gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano,
  gpt-4o, gpt-4o-mini, o1, o3, o4 — cache_read = input × 0.1
  per the actual OpenAI prefix-cache discount (previously the
  generic fallback used 50%, overstating savings 5×).
- **Gemini**: 2.5-pro, 2.5-flash, 2.0-flash.
- **DeepSeek**: V3 / V4 (cache_read 0.07) and R1 / reasoner
  (cache_read 0.14), with explicit cache-hit vs cache-miss tiers
  per DeepSeek's published rates.
- **OSS / regional**: GLM, MiniMax, Kimi / Moonshot, MiMo, Qwen,
  Doubao.
- `has_word()` boundary matcher treats `-_/:` as word boundaries
  so `openai/o3-mini`, `provider/gpt-5.5-turbo`, and
  `anthropic-compat/claude-sonnet-4.5` route to the right tier.
- Helpers `openai_pricing(input, output)` and `generic_pricing()`
  factor out the common cache-read tier maths.

### 🧹 Cleanup

- **Nine dead-code warnings cleared** across the workspace:
  `aris setup` removed `run_setup()` + `configure_codex_mcp()`
  (these advertised "install skills, configure MCP" but only
  routed to `config::run_interactive_setup`); deleted
  `has_executor_key()`, `buf_display_width()`,
  `chat_completions_url()`; renamed `error` → `_error` in
  `runtime::config` legacy branch.
- **`aris setup` user-facing strings** synced with actual
  behaviour: help text now says "Configure API keys / model /
  language (interactive)" and doctor's MCP-not-configured branch
  points users at `~/.claude.json` direct edit or
  `claude mcp add`.
- `cargo fmt` over the seven v0.4.10-touched files (other
  baseline drift left alone so this release stays scoped).

### 🧪 Tests

- `cargo test -p runtime --lib mcp_stdio --test-threads=1`: 16
  passing (13 pre-existing + 3 M3 regressions).
- Pre-existing macOS-only `api` crate `PoisonError` test residuals
  are unchanged (Linux CI clean).

### 📐 Cross-model review

Codex MCP (gpt-5.5 xhigh) reviewed every step plus a final
`v0.4.9..HEAD` cross-cutting audit. Verdict: READY TO SHIP.
Four P1 follow-ups (Anthropic retry coverage, o-series
reasoning-effort detection, `stream_options` proxy fallback,
per-server MCP timeout) and one P2 (pricing substring matchers)
are captured in `idea-stage/v0.4.10/v0.4.11_followups.md`.

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
