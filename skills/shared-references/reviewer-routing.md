# Reviewer Routing

## Default (NEVER changes without explicit user request)

All review calls use **Codex MCP** (`mcp__codex__codex`), model **`gpt-5.6-sol`** (GPT-5.6-Sol), with a **two-tier reasoning-effort policy** (since 2026-07-10; `ultra`/`max` need codex-cli ≥ 0.144.1):

| Tier | `model_reasoning_effort` | Which calls |
|------|--------------------------|-------------|
| **Deep-audit** | `ultra` | `/proof-checker` · `/kill-argument` (attack / defense / adjudication threads; beast-mode extra axis probes stay `xhigh`) · `/research-review` · `/experiment-audit` · `/paper-claim-audit` · `/result-to-claim` · `/meta-apply` |
| **Regular** | `xhigh` | every other reviewer call — including ALL rounds of `/auto-review-loop` and other multi-round loops (a `codex-reply` cannot change model/effort mid-thread), and per-item fan-outs like `/citation-audit` (per-entry fresh calls would multiply `ultra`'s delegation cost for no verdict gain) |

**Always pin BOTH `model` and `config.model_reasoning_effort` explicitly in the first call of every thread.** Do not rely on the user's `~/.codex/config.toml`: the catalog default effort for gpt-5.6-sol is `low`, far below the review floor.

`ultra` = deepest reasoning + automatic task delegation — right for one-shot verdict-bearing audits, wrong for per-item loops (slower, pricier). Effort enums accepted by codex-cli ≥ 0.144.1: `none / minimal / low / medium / high / xhigh / max / ultra`.

> **Do not confuse the two "max"es.** ARIS's `— effort: lite|balanced|max|beast` ([effort-contract.md](effort-contract.md)) sets how much WORK the pipeline does; Codex's `model_reasoning_effort: …|max|ultra` sets how hard the REVIEWER thinks. `— effort: max` does NOT imply `model_reasoning_effort: max`.

### Codex capability fallback (new reviewer sessions only)

Resolve the reviewer pair on the **first new Codex session of each tier** in a run, then reuse that resolved pair for later sessions of the same tier. Try the declared pair first (`gpt-5.6-sol` + `ultra` for deep-audit; `gpt-5.6-sol` + `xhigh` for regular). Then:

- Only if the call fails **before returning a usable thread** AND the error **explicitly identifies the requested effort as unsupported** (older codex-cli): retry `gpt-5.6-sol` + `xhigh`. (This step exists only for the deep tier's `ultra` — a regular-tier `xhigh` call skips it; `xhigh` predates 0.144.1.)
- Only if the error **explicitly identifies `gpt-5.6-sol` as unknown or unavailable** to this account/plan: retry `gpt-5.5` + `xhigh` (skip redundant intermediate steps).
- **NEVER downgrade on** timeout, rate-limit/capacity, authentication, transport/protocol, server, sandbox/tool, context-length, malformed-request, or response-parse errors — a blind downgrade retry there risks double-running (and double-billing) a review that may have gone through.
- **Never run a verdict-bearing review below `xhigh`.** `gpt-5.4` is available only as an explicit user override for legacy/repro runs — it is NOT part of the automatic chain.
- Replies (`codex-reply`) inherit the successful session's model and effort — pass only the saved `threadId` plus the message.
- Trace every attempt, the resolved pair, and the fallback reason (see `review-tracing.md`); the trace records the pair that actually ran, not the target pair.
- If no allowed pair succeeds, emit `REVIEW_UNAVAILABLE` (or, for a mandatory audit gate, `ERROR`) — never a substantive verdict.
- This automatic chain applies only when no explicit reviewer-model override was supplied.

### After upgrading codex-cli

MCP servers are spawned per session: after upgrading codex-cli (e.g. to 0.144.1 for `ultra`/`max`), **restart the Claude Code session** so `codex mcp-server` runs the new binary — an old server process rejects the new effort enums even though the CLI on disk is new.

## Optional: GPT-5.5 Pro via Oracle

When the user explicitly passes `— reviewer: oracle-pro`, route the review through Oracle MCP instead of Codex MCP.

### Routing Logic (add to any reviewer-invoking skill)

```
Parse $ARGUMENTS for `— reviewer:` directive.

If not specified OR `— reviewer: codex`:
    → Use mcp__codex__codex with model: gpt-5.6-sol at the tier's effort
      (deep-audit: ultra / regular: xhigh — see the Default table above).
    → This is the DEFAULT. No change from current behavior.

If `— reviewer: oracle-pro`:
    → Check if mcp__oracle__consult tool is available
    → If available:
        Use mcp__oracle__consult with:
          model: "gpt-5.5-pro"
          prompt: [same prompt you would send to Codex]
          files: [file paths for reviewer to read directly]
        Note: Oracle may use API mode (fast, needs OPENAI_API_KEY)
              or browser mode (slow ~1-2 min, needs Chrome + ChatGPT login)
    → If NOT available:
        Print: "⚠️ Oracle MCP not installed. Falling back to Codex at this call's declared tier."
        Use mcp__codex__codex as normal.
```

### Invariants

- `— reviewer: oracle-pro` ONLY takes effect when explicitly passed
- Reviewer independence protocol still applies (pass file paths, not summaries)
- `effort` and `difficulty` are orthogonal — they don't change reviewer backend
- `beast` mode may RECOMMEND oracle-pro but never requires it
- Browser mode: acceptable for one-shot reviews; NOT recommended inside multi-round loops (too slow/brittle)

### Oracle MCP Call Format

```
mcp__oracle__consult:
  prompt: |
    [role + task + output schema]
    Read all listed files directly.
  model: "gpt-5.5-pro"
  files:
    - /absolute/path/to/file1
    - /absolute/path/to/file2
```

### Skills That Support `— reviewer: oracle-pro`

| Skill | Use case for Pro |
|-------|-----------------|
| `/research-review` | Deeper critique on paper drafts |
| `/auto-review-loop` | Final stress test (last round only in browser mode) |
| `/experiment-audit` | Line-by-line eval code audit |
| `/proof-checker` | Deep mathematical reasoning |
| `/rebuttal` | Stress test before submission |
| `/idea-creator` | Idea evaluation depth |
| `/research-lit` | Literature analysis depth |

### Installation

```bash
# Install Oracle CLI + MCP
npm install -g @steipete/oracle

# Add Oracle MCP to Claude Code
claude mcp add oracle -s user -- oracle-mcp

# Restart Claude Code session to load

# API mode (fast, recommended):
export OPENAI_API_KEY="your-key"

# Browser mode (no API key, slower):
# Just log in to ChatGPT in Chrome
```

### NOT installed = ZERO impact

If Oracle is not installed, `— reviewer: oracle-pro` gracefully falls back to Codex. No error, no breakage, just a warning.

### Upstream development & known issues

Oracle MCP is maintained at [`steipete/oracle`](https://github.com/steipete/oracle). When you invoke `— reviewer: oracle-pro` (and especially the `o3-deep-research` / `gpt-5.5-pro` paths), it's worth checking the **[open PRs](https://github.com/steipete/oracle/pulls)** for in-flight fixes that may affect your run — e.g., model routing changes, browser-mode auth fixes, rate-limit handling, or new model alias support. ARIS does not vendor Oracle MCP; you're running the published version from `npm install -g @steipete/oracle`. If a behavior surprises you, the upstream PR queue is the first place to check before opening an issue here.

## Optional: Gemini via Antigravity CLI (`— reviewer: agy`)

When the user explicitly passes `— reviewer: agy`, route the review through the **gemini-review MCP** with the Antigravity (`agy`) backend — a native cross-model reviewer for Antigravity users who don't run Codex MCP / Oracle. Added in [#267](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/267).

### Routing Logic (add to any reviewer-invoking skill)

```
Parse $ARGUMENTS for `— reviewer:` directive.

If `— reviewer: agy`:
    → Check if the gemini-review MCP tool is available (mcp__gemini_review__review).
    → If available (server configured with GEMINI_REVIEW_BACKEND=agy):
        Use mcp__gemini_review__review with:
          prompt: [same prompt you would send to Codex]
        For round 2+: mcp__gemini_review__review_reply with the saved threadId.
        For long paper/project reviews (avoid the ~120s MCP tool timeout):
          mcp__gemini_review__review_start + mcp__gemini_review__review_status (async).
    → If NOT available:
        Print: "⚠️ gemini-review (agy) MCP not configured. Falling back to Codex at this call's declared tier."
        Use mcp__codex__codex as normal.
```

### Invariants

- `— reviewer: agy` ONLY takes effect when explicitly passed.
- **Cross-model family holds by construction.** The `agy` backend is fail-closed on ARIS's invariant: it recovers the *actual* Gemini-family model id from the current invocation's Antigravity transcript, **refuses** to return a verdict if the routed model is non-Gemini (no `"agy-cli"` placeholder), and binds the recovered transcript to *this* call via a **user-event nonce** (a model echo can't spoof the binding). So when the executor is Claude, `— reviewer: agy` (Gemini) satisfies the cross-model gate.
- Reviewer independence still applies — pass prompt context only (the `tools` arg is accepted for compatibility but ignored).
- `effort` and `difficulty` are orthogonal — they don't change the reviewer backend.

### Install

```bash
# Install + authenticate the Antigravity CLI (`agy`), then add the MCP with the agy backend:
claude mcp add gemini-review --env GEMINI_REVIEW_BACKEND=agy -- python3 <path>/mcp-servers/gemini-review/server.py
# (codex mcp add gemini-review ... for Codex CLI). Without the env var the server defaults to the direct Gemini API.
```

### NOT installed = ZERO impact

If the gemini-review (agy) MCP isn't configured, `— reviewer: agy` gracefully falls back to Codex at the call's declared tier (deep-audit: ultra / regular: xhigh). No error, no breakage, just a warning.

## Optional: Manual Review (any model, zero API cost)

When the user explicitly passes `— reviewer: manual`, route the review through the manual-review MCP server. Instead of calling an API, it opens a browser page (or writes a file on headless Linux) where the user copies the prompt to any model and pastes the response back.

**Zero API cost. Works with any text-capable model.**

### Routing Logic

```
Parse $ARGUMENTS for `— reviewer:` directive.

If `— reviewer: manual`:
    → Check if mcp__manual_review__review tool is available
    → If available:
        Use mcp__manual_review__review with:
          prompt: [same prompt you would send to Codex]
          config: {"model_reasoning_effort": "xhigh"}
        For round 2+ in multi-round skills:
          Use mcp__manual_review__review_reply with:
            threadId: [saved from prior call]
            prompt: [follow-up prompt]
            config: {"model_reasoning_effort": "xhigh"}
    → If NOT available:
        Print: "⚠️ Manual Review MCP not installed. Install with: claude mcp add manual-review -s user -- python3 /path/to/mcp-servers/manual-review/server.py"
        STOP. Do NOT fall back to Codex (the target user likely has no Codex subscription).
```

### Invariants

- `— reviewer: manual` ONLY takes effect when explicitly passed
- **Cross-model family is mandatory, not optional.** "any model" above means any *non-executor-family* model. When the executor is Claude (the normal case), the user MUST paste the prompt into a non-Claude model (ChatGPT / DeepSeek / Kimi / Gemini / a local model) — never any Claude product. Pasting into Claude makes Claude judge Claude, which silently voids the cross-model invariant and the verdict is worthless. The manual-review UI surfaces this as a banner; the routing contract requires it. A Type-B acceptance gate (`acceptance-gate.md`) is satisfied by `manual` only when the routed model is verifiably non-Claude.
- Prompt fidelity: the user sees the EXACT same prompt text that Codex would receive
- `config.model_reasoning_effort` is shown as a recommendation badge, not embedded in the prompt
- Thread continuity: `review_reply` shows previous exchanges so the user can maintain context in their chosen model
- Reviewer independence protocol still applies

### Thread continuity

For round 2+ in multi-round skills (`/auto-review-loop`, `/proof-checker` Phase 3):
- Use `mcp__manual_review__review_reply` with the saved `threadId`
- The browser page displays previous prompt/response exchanges
- The user should continue the conversation in the same model session for best results

### Installation

```bash
claude mcp add manual-review -s user -- python3 /path/to/mcp-servers/manual-review/server.py
```

### Modes

- **Browser mode** (default): opens a local web page on Windows/macOS/Linux desktop
- **File mode** (`MANUAL_REVIEW_MODE=file`): writes prompt to a per-thread subdirectory. Read `.aris/pending_review/pending_review.json` for the `prompt_file` and `response_file` paths — for headless/SSH environments

### Skills That Support `— reviewer: manual`

The following skills are wired for manual review (Claude Code only):

| Skill | Manual support |
|-------|----------------|
| `/research-review` | Yes |
| `/auto-review-loop` | Yes |
| `/experiment-audit` | Yes |
| `/proof-checker` | Yes |
| `/rebuttal` | Yes |
| `/idea-creator` | Yes |

> `/research-lit` supports `oracle-pro` only; manual review is not wired because the skill has no reviewer call blocks.

> **Platform note**: Manual review requires MCP tools (available only in Claude Code). Mirrored skill packs under `skills/skills-codex/` and `skills/skills-codex-*-review/` do NOT include manual-review wiring — they target Codex CLI and other platforms that lack MCP support. Oracle-pro support in those mirrors is unaffected.

### Nightmare mode (Codex-only)

Manual review supports medium/hard MCP-style review. Codex-exec nightmare mode is Codex-only and must fail closed when reviewer is manual.

### NOT installed = explicit error (not silent fallback)

If manual-review MCP is not installed, `— reviewer: manual` prints install instructions and stops. It does NOT fall back to Codex — the target user likely has no Codex subscription, so a silent fallback would fail anyway.

### `codex exec` CLI is NOT an equivalent Codex backend

The mainline reviewer contract is `mcp__codex__codex` + `mcp__codex__codex-reply`: skills rely on **thread continuity** (e.g. `/idea-creator` Phase 4 runs its devil's-advocate triage as a same-thread `codex-reply`), structured returns, and saved `threadId` traces. `codex exec --ephemeral` is a stateless one-shot — fine for a single self-contained review, but NOT a drop-in replacement: hand-rewriting every MCP call to `codex exec` silently loses reply continuity and tends to mangle SKILL.md instructions (observed in the wild as "the executor skips phases and improvises" — issue #284).

If Codex MCP is broken in your setup, prefer in order:

1. Fix the MCP registration: `claude mcp add codex -s user -- codex mcp-server`, then `/mcp` in-session to (re)connect.
2. Codex-CLI-as-executor: use the native mirror pack [`skills/skills-codex/`](../skills-codex/) — designed to run inside Codex CLI without Claude-side MCP.
3. One-shot `codex exec` only for skills whose review is a single call with no follow-up reply.

### Future work

- `mcp__manual_review__generate_image`: manual alternative to `codex-image2` for paper illustrations
- Image review loop integration
