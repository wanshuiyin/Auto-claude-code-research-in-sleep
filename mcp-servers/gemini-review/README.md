# Gemini Review MCP

Bridge Codex-first ARIS workflows to Gemini, using the direct Gemini API by default.

## What it does

- Keeps **Codex** as the executor
- Uses **Gemini** as the external reviewer
- Exposes synchronous MCP tools:
  - `review`
  - `review_reply`
- Exposes asynchronous MCP tools for long reviewer prompts:
  - `review_start`
  - `review_reply_start`
  - `review_status`

The synchronous tools return a JSON string containing `threadId` and `response`.
The asynchronous start tools return a JSON string containing `jobId` and `status`, and `review_status` later returns the final `threadId` and `response`.
When using the direct API backend, the tools also accept optional `imagePaths` / `image_paths` so Gemini can review local PNG/JPG/WebP files, which is used by the poster visual-review overlay.

## Install into Codex

```bash
mkdir -p ~/.codex/mcp-servers/gemini-review
cp mcp-servers/gemini-review/server.py ~/.codex/mcp-servers/gemini-review/server.py
codex mcp add gemini-review --env GEMINI_REVIEW_BACKEND=api -- python3 ~/.codex/mcp-servers/gemini-review/server.py
```

## Prerequisites

Prepare the direct Gemini API path before use:

- **Gemini API**: set `GEMINI_API_KEY` or `GOOGLE_API_KEY`

Optional fallback only:

- **Gemini CLI**: install `gemini` and complete CLI login/auth if you explicitly want `GEMINI_REVIEW_BACKEND=cli`
- **Antigravity CLI**: install/authenticate `agy` if you explicitly want `GEMINI_REVIEW_BACKEND=agy`

The server also auto-loads `~/.gemini/.env` if it exists, so a local file such as:

```bash
export GEMINI_API_KEY=...
```

is enough for API mode without exporting the variable in every shell.

## Environment Variables

- `GEMINI_BIN`: Gemini CLI path, defaults to `gemini`
- `AGY_BIN`: Antigravity CLI path, defaults to `agy`
- `GEMINI_REVIEW_MODEL`: optional reviewer model override used by API/Gemini CLI backends; `agy` model selection is controlled by Antigravity settings, so the bridge reports the actual model recovered from the current log/transcript and records any requested model as provenance only
- `GEMINI_REVIEW_API_MODEL`: API-only default when `GEMINI_REVIEW_MODEL` is unset, defaults to `gemini-2.5-flash`
- `GEMINI_REVIEW_SYSTEM`: optional default system prompt
- `GEMINI_REVIEW_BACKEND`: reviewer backend override, one of `api`, `auto`, `cli`, or `agy`; defaults to `api`
- `GEMINI_REVIEW_TIMEOUT_SEC`: HTTP / subprocess timeout, defaults to `600`
- `GEMINI_REVIEW_MAX_STATUS_WAIT_SECONDS`: maximum blocking wait for `review_status`, defaults to `30`
- `GEMINI_REVIEW_AGY_PRINT_TIMEOUT`: Antigravity `--print-timeout` value, defaults to `${GEMINI_REVIEW_TIMEOUT_SEC}s`
- `GEMINI_REVIEW_AGY_APP_DATA_DIR`: Antigravity CLI app data directory, defaults to `~/.gemini/antigravity-cli`
- `GEMINI_REVIEW_AGY_ARTIFACT_MAX_CHARS`: max characters read from an AGY-generated text artifact, defaults to `200000`
- `GEMINI_REVIEW_WORKSPACE_ROOT`: workspace root for local `imagePaths`, defaults to the server process current working directory
- `GEMINI_REVIEW_STATE_DIR`: bridge state directory, defaults to `~/.codex/state/gemini-review`
- `GEMINI_REVIEW_DEBUG_LOG`: debug log path, defaults to `~/.codex/state/gemini-review/debug.log`; custom paths must resolve under `GEMINI_REVIEW_STATE_DIR`
- `GEMINI_API_KEY`: Gemini API key
- `GOOGLE_API_KEY`: alternate Gemini API key env var

## Notes

- The bridge defaults to the direct Gemini API path. This is the intended reviewer backend for the ARIS skill overlay.
- The server auto-loads only `GEMINI_API_KEY` and `GOOGLE_API_KEY` from `~/.gemini/.env`; the file is ignored if it is a symlink, not owned by the current user, not a regular file, or group/world-writable.
- `GEMINI_REVIEW_BACKEND=auto` is still supported if you want API-first auto-selection; it uses the API when a Gemini API key is configured and otherwise falls back to the Gemini CLI. Antigravity is never selected by `auto`; use `GEMINI_REVIEW_BACKEND=agy` explicitly.
- `GEMINI_REVIEW_BACKEND=agy` routes review prompts through `agy --print`, which is useful when you want Codex to keep the MCP contract but use Antigravity CLI authentication/model routing. Because `agy --print` can exit successfully after writing a conversation transcript or generated artifact without printing the final text to stdout, the bridge passes a per-call `--log-file` and can recover from the Antigravity transcript for that same invocation only.
- The `agy` backend is fail-closed for ARIS's cross-model invariant: the bridge cannot choose the Antigravity model per call, so it treats Antigravity's selected model as external configuration. After each call it must recover an actual Gemini-family model id from the current invocation's log/transcript and returns that id as `model`. If a caller passes a `model` value, the response also includes `requested_model` and a `warning` because the current `agy` CLI does not expose per-call model selection. If Antigravity routes the request to a non-Gemini model, or the log/transcript does not expose a model id, the call fails instead of returning an unauditable `"agy-cli"` placeholder.
- Antigravity transcript recovery validates conversation ids with `^[0-9A-Za-z_-]+$`, caps ids at 128 characters, requires the per-call invocation nonce, and accepts the nonce only from user/bridge-written transcript events before considering later transcript lines. Generated text artifacts are read only from the final planner response, only as a fallback when that response has no substantive inline text, only if their resolved `file://` path stays under `GEMINI_REVIEW_AGY_APP_DATA_DIR/brain/<conversation>/`, and only if the artifact was updated during the current invocation window.
- If the default API model is temporarily rate-limited on your current free-tier window, keep the same bridge and set `GEMINI_REVIEW_MODEL=gemini-flash-latest` as a model override.
- The `tools` argument is accepted for compatibility with existing skills, but is ignored. This matches the original pattern where the external reviewer only sees the prompt context prepared by Codex.
- `imagePaths` / `image_paths` are supported only by the direct Gemini API backend in this bridge. Paths must resolve under `GEMINI_REVIEW_WORKSPACE_ROOT` and are opened with no-symlink safeguards; platforms where the opened fd cannot be re-verified fail closed. CLI and `agy` fallback paths remain text-only.
- `threadId` is a bridge-local conversation id persisted under `~/.codex/state/gemini-review/threads/` by default and can be passed to `review_reply`.
- `jobId` is a bridge-local background task id stored under `~/.codex/state/gemini-review/jobs/` by default, so status can be resumed across MCP server restarts.
- State files contain review prompts/responses so async jobs and threads can resume. The bridge creates state, thread, job, debug-log, and per-call `agy` log directories with owner-only permissions where possible; `agy` per-call log directories are temporary and are removed after the call. Delete `GEMINI_REVIEW_STATE_DIR` when you no longer need resumability. If you override `GEMINI_REVIEW_STATE_DIR`, choose a private directory rather than a shared `/tmp` path.
- This is intentionally a narrow, repo-local adapter. We did not directly vendor a generic Gemini MCP server, because the ARIS reviewer-aware skills expect the specific `review` / `review_reply` / `review_start` / `review_reply_start` / `review_status` interface and resumable review-thread semantics.

## Validation

This bridge was validated against the ARIS reviewer workflow in a privacy-safe way:

- direct bridge smoke tests passed for:
  - `review`
  - `review_start` -> `review_status`
  - `review_reply_start` -> `review_status`
  - local-image multimodal review through `imagePaths`
- the overlayed reviewer-aware Codex skills were checked to ensure all `15` predefined overrides point at this bridge contract
- representative Codex-side executions on a private, non-public research repository confirmed that real skill runs can enter the `gemini-review` path from research-review, idea-generation, and paper-planning style workflows

Important nuance from testing:

- Gemini free tier was sufficient for development-style validation, but bursty back-to-back runs could still trigger temporary `429` responses
- on the same setup, a later retry completed sync review, async `review_start` -> `review_status`, and threaded `review_reply_start` -> `review_status` successfully with `GEMINI_REVIEW_MODEL=gemini-flash-latest`
- long synchronous reviewer calls can still hit host-side MCP tool timeouts before Gemini responds
- because of that, the async path is not just an implementation detail; it is the recommended operational path for long reviews

## When to use sync vs async

- Use `review` / `review_reply` for short prompts that comfortably finish within the host MCP tool timeout.
- Use `review_start` / `review_reply_start` + `review_status` for long paper or project reviews. This avoids the observed `Codex -> tools/call` timeout around 120 seconds.

## Async flow

Start a long review:

```json
{
  "name": "review_start",
  "arguments": {
    "prompt": "Review this paper draft..."
  }
}
```

Multimodal example:

```json
{
  "name": "review_start",
  "arguments": {
    "prompt": "Review this poster PNG for readability and clipping.",
    "imagePaths": ["poster/poster_v1.png"]
  }
}
```

Example response:

```json
{
  "jobId": "5d8d0a9c5a2f4f42ae44f6f0c2d73f6f",
  "status": "queued",
  "done": false
}
```

Poll later:

```json
{
  "name": "review_status",
  "arguments": {
    "jobId": "5d8d0a9c5a2f4f42ae44f6f0c2d73f6f",
    "waitSeconds": 20
  }
}
```

When complete, `review_status` returns the same reviewer payload fields as the synchronous tools, including `threadId`, `response`, `model`, `backend`, and `stop_reason`. For `agy` calls, the payload also includes `model_provenance`; if a model was requested, it also includes `requested_model` and `warning`.

## Provenance and References

- Upstream interaction pattern: ARIS `claude-review` bridge and `skills-codex-claude-review` in `Auto-claude-code-research-in-sleep`
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/mcp-servers/claude-review>
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/skills/skills-codex-claude-review>
- Gemini backends used by this bridge:
  - Official Gemini API docs: <https://ai.google.dev/api>
  - Official Gemini CLI: <https://github.com/google-gemini/gemini-cli>
- Gemini API access and pricing:
  - API key / AI Studio entry: <https://aistudio.google.com/apikey>
  - Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- MCP protocol reference:
  - <https://modelcontextprotocol.info/specification/>
- Related generic Gemini MCP server example:
  - `eLyiN/gemini-bridge`: <https://github.com/eLyiN/gemini-bridge>
  - We inspected this class of generic Gemini MCP servers, but kept a thin compatibility adapter here because their tool schema and session model do not match the ARIS review-only bridge directly.
