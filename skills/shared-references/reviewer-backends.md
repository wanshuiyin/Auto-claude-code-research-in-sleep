# Selectable Reviewers

The complete Claude Code and Codex skill packs share this selection contract.
It changes the reviewer transport at an existing review step, preserving the
step's prompt, evidence, fresh-context requirements, rebuttal, and verdict schema.
Generation workers and the main executor do not change.

## Select once, preserve the session

Selection order is **this invocation → project configuration → host default**.
Use `— reviewer: <backend>` with optional `reviewer model:` and `reviewer effort:`
directives. The project file is `.aris/reviewer.json`, for example:

```json
{"backend": "antigravity", "model": "gemini-4-argon-high", "effort": "high"}
```

Supported routes:

| Backend | Transport and default pair |
|---|---|
| `codex` | Codex host: fresh native reviewer agent; Claude Code host: Codex MCP. `gpt-6-astra`, deep tier `ultra`, regular tier `xhigh`. |
| `antigravity` / `gemini` | Antigravity MCP; `gemini-4-argon-high` / `high`. To use its Claude option, explicitly select e.g. `claude-opus-5-5-high` / `high`. |
| `grok` | Grok MCP; `grok-4.7` / `xhigh`. |
| `claude-code` / `claude` / `claude-review` | Local Claude Code through `claude-review` MCP. No model override by default; it uses the CLI's configured provider, which can be DeepSeek. |

The aliases identify a transport, not proof of a model family. Always record the
returned model. `agy` remains the older **gemini-review** route; it is not an
alias for the separate Antigravity MCP. Existing `oracle-pro`, `manual`,
`copilot`, and `copilot-native` contracts remain in `reviewer-routing.md`.

Resolve `tools/reviewer_route.py` through `integration-contract.md` §2. It is a
local parser, not an MCP client; it never launches a review or changes settings.
Pass the actual host and the skill's existing tier, plus only the directives
the user supplied. For example, an explicit Gemini review in the Codex host:

```bash
python3 "$REVIEWER_ROUTE" --project "$PWD" --host codex --tier deep \
  --reviewer antigravity --model gemini-4-argon-high --effort high
```

Without an override, Claude Code retains Codex MCP and Codex retains its native
reviewer. In the main pack's Copilot auto-review loop, apply the existing host
marker protocol before supplying `copilot-native` as the host default; explicit
or project selection takes precedence over that default. Do not probe Copilot
when a different reviewer was already selected.

An inline backend override to a different provider discards that provider's
project model/effort. An override to the same backend may inherit those fields.
`reviewer effort` is separate from ARIS workflow `effort`. The Claude Code bridge
has no effort argument: omit it, and do not label the configured CLI effort as
observed evidence. Configuration errors or an unavailable selected backend are
`REVIEW_UNAVAILABLE` for the new MCP routes; do not silently switch providers.
Existing Codex capability fallback and legacy Oracle/Agy warning/fallback rules
remain in `reviewer-routing.md` and apply only to their own routes.

Save the resolved route alongside the review session id and working directory.
Forward an invocation override to child skills instead of silently resetting it
to their default. A resumed run uses its saved route; changing provider/model or
fixed session options starts a new review session. A step requiring a fresh
reviewer always starts a fresh session, even when another reviewer session exists.
The model/effort pins in a skill's Codex examples apply when `backend=codex`;
use the selected backend's contract below for other routes.

## First call and continuation

Discover the tool names actually exposed by the host. The canonical names below
may have normalized hyphens/underscores. Native `spawn_agent` / `send_input`
may be exposed as `collaboration.spawn_agent` / `collaboration.followup_task`.
Preserve the caller's delegation authorization and fresh-context boundaries.
When the native tool is `collaboration.spawn_agent`, explicitly pass
`fork_turns: "none"` with the selected `model` and `reasoning_effort`, supplying
only the review task and primary input paths. Its default history fork would
inherit the executor's conversation and disallow those model overrides. For
other native hosts, use their actual fresh-context mechanism; do not pass an
unsupported parameter merely because another host uses it.

| Route | First call | Continuation |
|---|---|---|
| Codex native | `spawn_agent`: model, reasoning_effort, review task; a fresh context | `send_input` with the saved reviewer id and follow-up task |
| Codex MCP | `mcp__codex__codex`: existing skill parameters and pinned model/effort | `mcp__codex__codex-reply`: saved thread id and prompt |
| Antigravity | `mcp__antigravity__antigravity`: prompt, explicit cwd, model, effort | `antigravity-reply`: **only** threadId and prompt |
| Grok | `mcp__grok__grok`: prompt, explicit cwd, model, effort; read-only sandbox and `read_file,grep,list_dir` | `grok-reply`: **only** threadId and prompt |
| Claude Code | `mcp__claude-review__review`: prompt, cwd, optional model; `tools: Read,Grep,Glob` for file reviews, empty tools for prompt-only reviews | `review_reply`: threadId, prompt, and repeat cwd/tools and any explicit model override |

Antigravity and Grok replies retain the first call's cwd, model, effort and
review tools. Do not pass Claude's `tools` string to Antigravity, Codex `config`
to Grok, or native agent ids to an MCP. Keep each route's saved session id.

For a long Claude Code review, use `review_start` / `review_reply_start`, save
the **jobId**, and poll `review_status` until `done=true`. A queued/running job
is not a completed review; only its final payload supplies the conversation
id and response. Repeat cwd/tools when starting a follow-up job.

Artifact-grounded reviews still give the reviewer primary file paths and ask it
to read them. Set cwd to a directory that contains the review inputs; do not
replace unreadable evidence with the executor's conclusions. The prompt may
include the original problem and author claims, clearly marked as claims.
For an existing prompt-only step, preserve its full source material.

**Exception — outbound-publication pipelines.** When the reviewed artifact is
content that is about to leave the local machine for an external service
(publishing, community posting, external-audience triage), the
artifact-grounded convention above is deliberately inverted: the reviewer
receives the text inline, and `cwd` is pinned to a neutral directory (`/tmp`)
rather than to the inputs directory. Antigravity can read any file under its
working directory and writes that directory's absolute path into its context,
so a business directory would leak the local account name and business paths to
an external model. The full contract — including why this is a deviation and
the explicit prohibition on "fixing" it back to the general convention —
lives in `mcp-servers/antigravity-exec/aris-antigravity-review-protocol.md`.
Do not treat this exception as a bug to be corrected.

Image/PDF visual review is a separate capability: preserve the skill's actual
image inputs and verify that the selected tool can consume them. A text-only
bridge or a reviewer that never opened the images cannot complete a visual
review. Keep independent attack/defense sessions, per-item isolation, and
mandatory deterministic checks where the skill already requires them.
The same capability check applies to independent web/citation lookup or command
execution: the file-review defaults above do not grant those tools. If a slot
requires them and the selected bridge cannot provide them, record that slot as
unavailable/incomplete; a file-only opinion cannot satisfy that requirement.

## Completion, identity and acceptance

Save the complete raw response before interpreting it. Check transport success:
no MCP `isError`; Antigravity must report `status=SUCCESS`; Grok must report
`stopReason=end_turn`; Claude sync calls must return a nonempty successful review,
and async calls must reach `status=completed`. Timeout, cancellation, truncated
output, queued work, or an unavailable tool is not a reviewer verdict. Do not
automatically retry a dispatched paid call after an ambiguous failure.

Use actual returned `model`, effort and their source fields, never the requested
pair as substitute evidence. Claude's `modelSource=cli_model_usage` may report a
configured alias; preserve that source and do not claim independent server
identity verification. Antigravity's selected variant and Grok's session summary
likewise have specific evidence limits. Missing values remain unknown/null.

The current executor model also matters: Claude Code can run DeepSeek, and
Antigravity can run Claude. Compute families from model identities, not bridge
names. Known same-family review remains `same-family / provisional`, even when
adversarial. A completed, in-scope, positive review with known different families
can record `cross-family / accepted`; selecting a cross-family route alone
cannot do so. An unavailable or incomplete review never becomes a fabricated PASS.
Keep the substantive verdict separately, including negative findings.

For the three new MCP routes, auto-review loops call `review_gate.py` with the
canonical backend, score/verdict, actual executor/reviewer models, and
`--review-status ok --review-completed --review-scope-complete` **only after**
checking those facts. Missing identity/completion/scope gives `review_unavailable`;
a positive same-family review may stop the drive loop provisionally. Existing
Copilot native evidence and compatibility-finalizer obligations remain unchanged.

Trace every call using `review-tracing.md`. With `save_trace.sh`, record backend,
tool, requested model, reported model, actual effort and session id. Add
`--verdict`, `--review-completed`, and `--review-scope-complete` only when warranted;
add `--review-positive` only after the skill's own positive gate succeeds (for
auto-review loops, score >= 6 AND ready/almost). A verdict word alone is not
positivity;
failed calls use `--status error`. Acceptance in a trace does not replace a
skill's submission, proof, citation, or experiment gate.

## Existing installations

Use the full `skills/skills-codex/` pack with this selection mechanism. The two
old partial reviewer overlays remain available for existing links, but receive
no new workflow features. Do not delete their directories or overwrite customized
installed skills during migration. See the Codex README for project-link and
global-copy migration procedures.
