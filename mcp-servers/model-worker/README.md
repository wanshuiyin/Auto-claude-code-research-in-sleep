# Model Worker MCP

Let another model read source material, write files, and revise them in the same
native session. `worker` starts a task with a backend, model, and thinking effort;
`worker_reply` continues it. This is a file author for prose and code. The existing
reviewer services remain separate.

| Backend | CLI | Example model | Example effort |
|---|---|---|---|
| `antigravity` | `agy` | `gemini-4-argon-high` | `high` |
| `grok` | `grok` | `grok-4.7` | `xhigh` |
| `claude-code` | `claude` | `deepseek/deepseek-flash[1m]` | `max` |

Omitting `effort` selects `high` for Antigravity/Claude Code and `xhigh` for Grok;
the chosen value is saved for replies. Use a model supported by your own account
and CLI. Backend names identify the
execution channel: Claude Code can run DeepSeek, and Antigravity can run models
other than Gemini. A failed request is reported without an automatic retry or
model substitution.

## Setup

The server uses Python 3.10+ and the adjacent ARIS reviewer parser modules; keep
it inside this repository. Only the CLI for the backend you use is required.

For Antigravity, copy `aris-model-worker.md` to
`~/.gemini/config/agents/aris-model-worker.md`. It enables the author file tools
and disables inherited MCPs and command execution for this agent. Existing
interactive and reviewer profiles are unchanged.

Register the new service, substituting your paths:

```bash
codex mcp add model-worker \
  --env 'MODEL_WORKER_ALLOWED_ROOTS=["/absolute/path/to/your/project"]' \
  -- python3 /absolute/path/to/aris/mcp-servers/model-worker/server.py
```

Set `tool_timeout_sec = 3660` in its Codex MCP entry. Other MCP hosts use the same
command, arguments, and environment. Claude Code registration is:

```bash
claude mcp add model-worker -s user \
  -e 'MODEL_WORKER_ALLOWED_ROOTS=["/absolute/path/to/your/project"]' \
  -- python3 /absolute/path/to/aris/mcp-servers/model-worker/server.py
```

Set `AGY_BIN`, `GROK_BIN`, or `CLAUDE_BIN` in the server environment when the CLI
is not on its PATH. Configure your existing proxy in that environment if needed.
Antigravity and Grok use their existing CLI login. The Claude backend uses bare,
restricted mode: provide API credentials through the server environment, or let
it read provider authentication fields from `~/.claude/settings.json` (override
with `MODEL_WORKER_CLAUDE_SETTINGS`). Bare mode does not load OAuth/keychain login.
Credentials are passed only to the Claude child, never saved in thread records.

## Call and revise

Call `worker`:

```json
{
  "backend": "antigravity",
  "model": "gemini-4-argon-high",
  "effort": "high",
  "cwd": "/absolute/path/to/your/project/paper",
  "prompt": "Read FACTS.md and writing-principles.md. Write the related-work section in sections/related-work.tex, connecting the papers around our research question. Preserve the supplied formulas, assumptions and citations. Report the changed file path.",
  "timeout_sec": 600
}
```

Put the relevant materials inside the workspace before calling. Give each worker
specific output files; avoid having another writer edit those files concurrently.
The worker does not inherit the executor's conversation or skills automatically.

Save the returned `threadId`. Call `worker_reply` with just that ID and feedback:

```json
{
  "threadId": "UUID returned by worker",
  "prompt": "Keep the opening and the comparison. Shorten the second paragraph, and restore the fixed-depth assumption next to the complexity claim. Update the same section file."
}
```

Replies keep the original backend, model, effort, cwd, and timeout, including
after a bridge restart. To change those settings, start a new worker. Returned
`model` and `effort` describe observed CLI metadata; `requestedModel` and
`requestedEffort` record the request. Missing observed values stay null.

The service serializes calls in each server process. For a longer task, set
`timeout_sec` and the host tool timeout together. Progress, ping, cancellation,
and CLI process cleanup are supported. A completed turn means the CLI finished;
read the resulting files as part of normal integration.

### Use before the host reloads its tools

The small client calls the registered Codex MCP entry without restarting Codex
(Python 3.11+ for TOML config parsing):

```bash
python3 /absolute/path/to/aris/mcp-servers/model-worker/client.py tools/list
python3 /absolute/path/to/aris/mcp-servers/model-worker/client.py worker --input /absolute/task.json
python3 /absolute/path/to/aris/mcp-servers/model-worker/client.py worker_reply --input /absolute/revision.json
```

For another host or an isolated setup, `--local` launches the adjacent server
using the current environment. This still uses MCP stdio, including initialization
and tool calls. `tools/list` does not call a model.

## Writing with ARIS

The skill packs support an optional external writer independently of the reviewer, configured through flags or natural-language preferences:

```text
/paper-writing "PAPER_PLAN.md" — writer: antigravity, writer-model: gemini-4-argon-high, writer-effort: high
```

When an external writer is configured, the main executor reads the source material, prepares the narrative spine and factual brief, and passes the workspace, target files, and writing guidance to `worker`. The writer drafts the substantive prose, and the executor saves the returned `threadId` so `worker_reply` continues the same session. The executor then checks technical accuracy, formulas, citations, and compilation against that brief while preserving good wording, sending targeted revisions through `worker_reply`. Without an external writer, the main executor writes directly.

Regardless of who writes, every draft follows HERO and the launch principle: lead with the strongest genuine contribution and its decisive evidence, state claim-defining assumptions where used, and communicate full results and supported tradeoffs clearly; see [writing principles](../../skills/shared-references/writing-principles.md).

## File access

`MODEL_WORKER_ALLOWED_ROOTS` admits task working directories; it is not an OS
sandbox. The backend's native permissions govern individual file operations.
Antigravity uses its author profile and `accept-edits` mode, Grok uses native
`workspace` mode and file-tool permissions, and Claude uses `--restricted`.
This version exposes file tools, without a shell or compilation runner. The main
executor runs builds and other commands. Native denial or failure is surfaced;
the bridge does not bypass permission checks.

Private session settings live at `~/.codex/state/model-worker` or
`MODEL_WORKER_STATE_DIR`, outside the task workspace. No global configuration is
changed by starting the server.

## Development checks

```bash
python3 -m pytest tests/test_model_worker.py -q
```

Protocol tests use fake CLIs for file writes, native continuation, routing and
failure handling. On 2026-11-01, Gemini 4 / high also wrote this README's usage
section through the new MCP and revised the file in the same native session
after a bridge restart. Grok and Claude author adapters have protocol coverage;
live provider calls for those two adapters have not been run for this release.
