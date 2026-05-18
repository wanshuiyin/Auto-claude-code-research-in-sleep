# llm-chat MCP Server

Generic MCP chat bridge for ARIS reviewer workflows.

It supports two backends:

- `api` (default): calls any OpenAI-compatible `/chat/completions` endpoint with `LLM_API_KEY`.
- `codex-cli`: calls the local `codex exec` command and reuses the user's existing Codex login, including ChatGPT/OAuth login.

## OpenAI-Compatible API

```bash
python3 -m pip install -r mcp-servers/llm-chat/requirements.txt
```

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/path/to/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_BACKEND": "api",
        "LLM_API_KEY": "your-api-key",
        "LLM_BASE_URL": "https://api.example.com/v1",
        "LLM_MODEL": "model-name"
      }
    }
  }
}
```

## Codex OAuth Backend

Use this when you can run Codex through a ChatGPT/OAuth login but do not have an OpenAI API key:

```bash
codex login status
```

Expected status:

```text
Logged in using ChatGPT
```

Then configure the MCP server without `LLM_API_KEY`:

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/usr/bin/python3",
      "args": ["/path/to/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py"],
      "env": {
        "LLM_BACKEND": "codex-cli",
        "LLM_MODEL": "gpt-5.5",
        "CODEX_WORKDIR": "/path/to/your/project"
      }
    }
  }
}
```

Optional settings:

| Variable | Default | Meaning |
|---|---:|---|
| `CODEX_BIN` | `codex` | Codex CLI binary path |
| `CODEX_WORKDIR` | server cwd | Working directory passed to `codex exec -C` |
| `CODEX_TIMEOUT_SECS` | `600` | Per-call timeout |
| `LLM_MODEL` | Codex config default | Optional model override passed as `codex exec -m` |
| `CODEX_DISABLE_PLUGINS` | `1` | Adds `--disable plugins` to avoid unrelated plugin loading/sync failures |

The bridge runs Codex with `codex exec --disable plugins --ephemeral --sandbox read-only` and reads the final answer through `--output-last-message`.
