# ARIS on DeepSeek Harness

English | [中文](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/dsh-aris/README_CN.md)

> The `dsh-aris` distribution branch. The full ARIS project — every workflow, the docs, and the other host adaptations — lives on [`main`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep).

Runs the ARIS research workflow inside [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness): all 82 skills in the native skill catalog, with cross-model adversarial review through Codex.

The skills are unmodified. This bundle is one configuration layer plus a short adapter — it patches no Harness code and forks nothing.

## Install

```sh
dsh plugin --profile web add dsh-aris
```

Restart the profile afterwards; plugin code loads at startup, so reloading the page is not enough.

`dsh plugin` shells out to **pnpm**, which the Harness does not bundle. Without it on `PATH` the install exits before doing anything.

## Prerequisites

**Codex CLI, installed and authenticated.** It is the independent reviewer. The bundle spawns `codex mcp-server` and never overrides its model or reasoning effort — **`~/.codex/config.toml` is the reviewer posture contract**. ARIS expects a non-DeepSeek family at `xhigh`:

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
```

If Codex cannot start, the Harness fails to boot rather than running a composition with no reviewer. That is deliberate: ARIS without an independent reviewer is not ARIS.

**A DeepSeek API key**, through the Harness Models page or `DEEPSEEK_API_KEY`.

**Behind an HTTP proxy**, start the Harness with `NODE_USE_ENV_PROXY=1`. Node's fetch ignores `http_proxy` otherwise, and model requests fail with `TRANSPORT`. It must be set when Node starts; configuration cannot repair an already-started process.

**Optional — bound the executor too.** ARIS's reviewers already carry scope limits: the block that forbids proposing hashes, defensive scaffolding, corner-case hardening, and over-mechanized judgement is embedded in the skills that produce review prompts, and applies with no setup. Nothing bounds the *executor* the same way. Two ways to close that, and they are different things:

- **ARIS's own limits, one flag.** The `aris-scope-limits` row ships disabled; set `disabled: false` in your profile's patch to apply the same block to the executor. It reads the packaged `skills/shared-references/review-scope-limits.md` at load, so the reviewer path and the executor path cannot drift apart. Off by default because it spends tokens on every request.
- **The full [HERO](https://github.com/wanshuiyin/HERO-Anti-OverDefense) contract.** Paste its canonical block into the project's `AGENTS.md` or `CLAUDE.md`, or into `$DSH_HOME/AGENTS.md` for every dsh project — the Harness loads those files itself. This bundle does not vendor HERO's text; its canonical home is HERO's own `RULES.md`.

## Verify

```sh
dsh --profile web --dump-config | grep -A2 aris-
```

Then, in a session, type `/` — the skill menu lists the ARIS skills. To check the part that matters, ask the model to call `mcp__codex__codex` with a trivial prompt, report the `threadId` it can see, then continue that thread once with `mcp__codex__codex-reply`. A visible `threadId` is what makes multi-round review work.

## The ARIS tab

In the Web UI a session gains an **ARIS** tab beside Chat and Trajectory. It is
read-only: it shows what the reviewer and the loop's own artifacts say, and
never writes, advances a round, or turns a score into a completion decision.

It reads `review-stage/REVIEW_STATE.json` from the session's workspace, so it
stays empty until an `auto-review-loop` run finishes a round there.

The top section is the reason the tab exists: **who reviewed this round**, and
whether ARIS could verify that the reviewer belongs to a different model family
than the executor. On the Codex backend that verification is `unverified` by
design — Codex reports its own model, but nothing independently attests the
executor's, so ARIS records `identity_assurance: caller_declared`. Read it as
"route-consistent, not attested".

Two honest limits are shown in the tab and worth repeating: state is written
when a round finishes, not continuously, so a long round displays the previous
one; and `completed` means the loop ended — a positive assessment *or* the round
cap — never that the work was acquitted.

## What the layer changes

| Row | Effect |
|---|---|
| `agent-default-model` | executor becomes `deepseek-v4-pro` |
| `aris-skills` | mounts the 82-skill corpus, publishes `ARIS_REPO`, restores Codex's `threadId`, serves the ARIS tab |
| `aris-codex` | `codex mcp-server` over MCP, 20-minute call budget, pinned to a stable working directory |

The corpus mounts at the bundled rank, so a project or user skill of the same name wins. The executor default is a deployment default, not a lock: a saved model setting or a per-session choice overrides it.

## Developing against a checkout

```sh
ARIS_REPO=/absolute/path/to/aris NODE_USE_ENV_PROXY=1 \
  dsh --profile web --patch /absolute/path/to/aris/dsh/checkout.patch.yml
```

Skill edits take effect without a restart. `ARIS_REPO` is required; without it the load fails naming the variable.

This overlay is **not** equivalent to the installed bundle: it cannot restore Codex's `threadId`, so multi-round `codex-reply` — and therefore the hard-tier Debate Protocol — works only through the installed bundle. The two are mutually exclusive: applying the overlay to a profile that already has the bundle fails on a duplicate row id. Remove one.

## Known limits

- **Tracks one Harness release.** DeepSeek Harness is a developer preview; this bundle is verified against `0.1.1-rc.1`. Every surface it uses survived rc.5 → 0.1.1-rc.1 unchanged, but that is not a promise about the next one.
- **No dsh packages are declared as npm dependencies.** In-box packages are host-provided and resolve from the Harness installation through the profile module fallback. The Harness's own rule keeps `@deepseek-ai/dsh-*` out of `dependencies`, and the packages version in lockstep with the CLI, so any range this bundle pinned would fight the version the user already has installed.
- **`web_fetch` is off.** Stock dsh ships it disabled and this bundle does not enable it, which would mean depending on a provider package. Skills that reach the web use `web_search`, or `bash` with `curl`.
- **Reviewer thread continuity is process-local.** A Harness restart, or any MCP reconnect that replaces the Codex child, loses saved `threadId`s. Rounds after that start fresh; `review-stage/REVIEWER_MEMORY.md` remains the durable record either way.
- **Codex's own reasoning is not in the Harness log.** Only the verdict returns. The call arguments and the verdict are logged; the reviewer's intermediate work stays on the Codex side.
- **A verdict over 50 KB is spilled** to a file with a preview left in context. Raise `maxInlineBytes` on the `spill-policy` row if your reviews run longer.
