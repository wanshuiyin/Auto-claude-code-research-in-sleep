//! v0.4.25: the built-in `codex` reviewer backend, implemented over
//! `codex exec --json`.
//!
//! codex-cli 0.154.0 removed the `codex mcp-server` entry point that ARIS-Code
//! used to spawn as the `codex` MCP server (`aris setup` option 10 wrote it
//! into `settings.json`). This module speaks the same tool contract the removed
//! entry point spoke — tools `codex` / `codex-reply`, results shaped
//! `{threadId, content}`, `isError: true` + codex's own error text on failure —
//! and runs each call as a `codex exec` subprocess. The 81 bundled skills that
//! hardcode `mcp__codex__codex` do not change.
//!
//! It is the Rust twin of the main repository's zero-dependency Python bridge
//! (`mcp-servers/codex-exec/server.py`); both keep one settings record per
//! thread in the same directory so a thread started by either can be resumed
//! by the other.
//!
//! Contract facts this module encodes (verified on codex-cli 0.153.4/0.154.0):
//! - `codex exec resume <id>` forgets the thread's model / effort / sandbox /
//!   cwd and falls back to `config.toml`, so a reply re-sends `-m`,
//!   `-c model_reasoning_effort=…`, `-c sandbox_mode="…"` and runs in the
//!   remembered working directory (resume has no `--cd` / `--sandbox`).
//! - Event precedence: `turn.failed` is terminal; `turn.completed` clears an
//!   intermediate `error`; a stream that ends with an un-cleared `error`
//!   reports that message; a stream that ends with no `turn.completed` and no
//!   error reports the exit status plus the stderr tail.
//! - `approval-policy` and the other removed arguments cannot be honoured by
//!   `codex exec`; they are accepted and ignored so older skill text keeps
//!   working.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value as JsonValue};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;

use crate::config::McpStdioServerConfig;
use crate::mcp_stdio::{
    JsonRpcError, JsonRpcId, JsonRpcResponse, McpTool, McpToolCallContent, McpToolCallResult,
};

/// Wall-clock budget for one `codex exec` run. Deep-audit reviews at `ultra`
/// routinely exceed the MCP transport's 300 s default, which is why the exec
/// backend carries its own default instead of reusing `mcp_request_timeout`.
pub const CODEX_EXEC_DEFAULT_TIMEOUT_SECS: u64 = 1800;

/// The server-level effort floor `aris setup` used to pin through
/// `codex mcp-server -c model_reasoning_effort="xhigh"`. Applied to any call
/// whose own `config` does not set the key, so a bare `mcp__codex__codex` call
/// still reviews at xhigh (v0.4.18 promise, kept across the transport change).
const EFFORT_FLOOR_KEY: &str = "model_reasoning_effort";
const EFFORT_FLOOR_VALUE: &str = "\"xhigh\"";

const SANDBOX_MODES: [&str; 3] = ["read-only", "workspace-write", "danger-full-access"];
const SANDBOX_KEY: &str = "sandbox_mode";
const STDERR_TAIL_CHARS: usize = 2000;

/// How the `codex` server slot is backed. Pure data; the manager owns the
/// lifecycle and `McpServerManager::call_tool` routes to [`CodexExecBridge::call`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodexExecBridge {
    /// Executable to spawn. The CLI passes the probe-resolved native path so a
    /// Windows `.cmd` shim earlier on PATH never shadows the real binary.
    pub codex_bin: PathBuf,
    /// Extra environment for the child (carried over from a migrated legacy
    /// `mcpServers.codex` entry; empty for the built-in default).
    pub env: BTreeMap<String, String>,
    /// `-c key=<TOML literal>` defaults applied when the call's own `config`
    /// does not set `key`. Defaults to the xhigh effort floor.
    pub default_config: Vec<(String, String)>,
    /// Whole-run timeout; the child is killed and reaped on expiry.
    pub timeout: Duration,
    /// Directory holding one `<threadId>.json` per thread.
    pub threads_dir: PathBuf,
}

/// What a thread was created with — the record `codex-reply` re-applies.
/// Field set and file layout match the Python bridge byte-for-byte in
/// semantics (`null` values are written, not omitted).
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CallSpec {
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub config: Option<JsonValue>,
    #[serde(default)]
    pub sandbox: Option<String>,
    #[serde(default)]
    pub cwd: Option<String>,
}

impl CallSpec {
    fn from_arguments(arguments: &JsonValue) -> Self {
        let get_str = |key: &str| {
            arguments
                .get(key)
                .and_then(JsonValue::as_str)
                .filter(|s| !s.is_empty())
                .map(str::to_string)
        };
        Self {
            model: get_str("model"),
            config: arguments
                .get("config")
                .filter(|v| v.is_object())
                .cloned(),
            sandbox: get_str("sandbox"),
            cwd: get_str("cwd"),
        }
    }
}

/// Everything learned from one `codex exec` run.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct CallOutcome {
    pub thread_id: Option<String>,
    pub last_message: Option<String>,
    pub error: Option<String>,
    pub completed: bool,
    pub failed: bool,
    pub cancelled: bool,
}

impl CallOutcome {
    /// Fold one JSONL event into the outcome (pure; mirrors `run_codex` in the
    /// Python bridge).
    pub fn apply_event(&mut self, event: &JsonValue) {
        let kind = event.get("type").and_then(JsonValue::as_str).unwrap_or("");
        match kind {
            "thread.started" => {
                if let Some(id) = event.get("thread_id").and_then(JsonValue::as_str) {
                    if !id.is_empty() {
                        self.thread_id = Some(id.to_string());
                    }
                }
            }
            "item.completed" => {
                let item = event.get("item").cloned().unwrap_or(JsonValue::Null);
                if item.get("type").and_then(JsonValue::as_str) == Some("agent_message") {
                    self.last_message = Some(
                        item.get("text")
                            .and_then(JsonValue::as_str)
                            .unwrap_or("")
                            .to_string(),
                    );
                }
            }
            "turn.completed" => self.completed = true,
            "turn.failed" => {
                self.failed = true;
                let message = event
                    .get("error")
                    .and_then(|e| e.get("message"))
                    .and_then(JsonValue::as_str)
                    .filter(|m| !m.is_empty())
                    .map(str::to_string);
                self.error = message
                    .or_else(|| self.error.clone())
                    .or_else(|| Some("turn failed".to_string()));
            }
            "error" if !self.failed => {
                if let Some(message) = event
                    .get("message")
                    .and_then(JsonValue::as_str)
                    .filter(|m| !m.is_empty())
                {
                    self.error = Some(message.to_string());
                }
            }
            _ => {}
        }
    }

    /// Resolve the final error text once the child has exited (pure).
    /// `exit_status` is the child's exit description (`"0"`, `"1"`,
    /// `"signal"`…); `stderr` is the full captured stderr.
    pub fn finalize(&mut self, exit_status: &str, stderr: &str) {
        if self.cancelled {
            self.error = Some("cancelled by client".to_string());
        } else if self.failed {
            // terminal failure: codex's own error text stands
        } else if self.completed {
            self.error = None;
        } else if self.error.is_none() {
            let trimmed = stderr.trim();
            let tail: String = trimmed
                .chars()
                .rev()
                .take(STDERR_TAIL_CHARS)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect();
            let mut message =
                format!("codex exec exited with status {exit_status} before completing the turn");
            if !tail.is_empty() {
                message.push('\n');
                message.push_str(&tail);
            }
            self.error = Some(message);
        }
    }

    /// The MCP tool result for this outcome — identical shape to the Python
    /// bridge: text block + `structuredContent {threadId, content}`, and
    /// `isError: true` carrying codex's raw error text on failure.
    #[must_use]
    pub fn into_tool_result(self) -> McpToolCallResult {
        let (text, is_error) = match self.error {
            Some(error) => (error, true),
            None => (self.last_message.unwrap_or_default(), false),
        };
        let mut data = BTreeMap::new();
        data.insert("text".to_string(), JsonValue::String(text.clone()));
        McpToolCallResult {
            content: vec![McpToolCallContent {
                kind: "text".to_string(),
                data,
            }],
            structured_content: Some(json!({
                "threadId": self.thread_id,
                "content": text,
            })),
            is_error: if is_error { Some(true) } else { None },
            meta: None,
        }
    }
}

/// Render a JSON value as the TOML literal `codex -c key=value` parses.
fn toml_value(value: &JsonValue) -> Result<String, String> {
    match value {
        JsonValue::Bool(b) => Ok(b.to_string()),
        JsonValue::Number(n) => Ok(n.to_string()),
        JsonValue::String(s) => serde_json::to_string(s).map_err(|e| e.to_string()),
        JsonValue::Array(items) => {
            let rendered = items
                .iter()
                .map(toml_value)
                .collect::<Result<Vec<_>, _>>()?;
            Ok(format!("[{}]", rendered.join(", ")))
        }
        JsonValue::Null | JsonValue::Object(_) => Err(format!("unsupported config value: {value}")),
    }
}

/// Flatten a `config` object into `-c dotted.key=value` pairs (nested objects
/// become dotted keys, like the Python bridge and `codex -c` itself).
fn config_flags(config: Option<&JsonValue>, prefix: &str, out: &mut Vec<String>) -> Result<(), String> {
    let Some(JsonValue::Object(map)) = config else {
        return Ok(());
    };
    for (key, value) in map {
        let dotted = format!("{prefix}{key}");
        if value.is_object() {
            config_flags(Some(value), &format!("{dotted}."), out)?;
        } else {
            out.push("-c".to_string());
            out.push(format!("{dotted}={}", toml_value(value)?));
        }
    }
    Ok(())
}

/// Does this stdio server entry launch the removed `codex mcp-server`? Pure
/// over the config so setup / doctor / startup agree.
#[must_use]
pub fn is_legacy_codex_mcp_server(config: &McpStdioServerConfig) -> bool {
    let command = Path::new(&config.command)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(&config.command)
        .to_ascii_lowercase();
    let stem = command
        .strip_suffix(".exe")
        .or_else(|| command.strip_suffix(".cmd"))
        .or_else(|| command.strip_suffix(".bat"))
        .unwrap_or(&command);
    stem == "codex"
        && config.args.iter().any(|a| a == "mcp-server")
        && !config.args.iter().any(|a| a == "exec")
}

/// A `-c key=<TOML literal>` value back to the JSON the thread record stores
/// (the Python bridge renders record values with its own `toml_value`, so a
/// TOML string must be stored unquoted and a TOML array as a JSON array).
/// Covers what `codex -c` accepts on a command line: quoted strings (both
/// quote styles), booleans, numbers, arrays of those, and bare words.
fn toml_literal_to_json(literal: &str) -> JsonValue {
    let trimmed = literal.trim();
    if trimmed.len() >= 2
        && ((trimmed.starts_with('\'') && trimmed.ends_with('\''))
            || (trimmed.starts_with('"') && trimmed.ends_with('"')))
    {
        let inner = &trimmed[1..trimmed.len() - 1];
        if trimmed.starts_with('"') {
            if let Ok(JsonValue::String(s)) = serde_json::from_str::<JsonValue>(trimmed) {
                return JsonValue::String(s);
            }
        }
        return JsonValue::String(inner.to_string());
    }
    if trimmed.len() >= 2 && trimmed.starts_with('[') && trimmed.ends_with(']') {
        let items = split_toml_array(&trimmed[1..trimmed.len() - 1])
            .into_iter()
            .map(|item| toml_literal_to_json(&item))
            .collect();
        return JsonValue::Array(items);
    }
    if let Ok(value) = serde_json::from_str::<JsonValue>(trimmed) {
        // booleans and numbers read the same in JSON
        return value;
    }
    // Bare word (codex falls back to the raw string when TOML parsing fails).
    JsonValue::String(trimmed.to_string())
}

/// Split the inside of a TOML array on top-level commas (quotes and nested
/// brackets respected).
fn split_toml_array(body: &str) -> Vec<String> {
    let mut items = Vec::new();
    let mut current = String::new();
    let mut depth = 0usize;
    let mut quote: Option<char> = None;
    let mut escaped = false;
    for ch in body.chars() {
        match quote {
            Some(q) => {
                current.push(ch);
                if escaped {
                    escaped = false;
                } else if ch == '\\' && q == '"' {
                    // basic strings escape with backslash; literal strings don't
                    escaped = true;
                } else if ch == q {
                    quote = None;
                }
            }
            None => match ch {
                '\'' | '"' => {
                    quote = Some(ch);
                    current.push(ch);
                }
                '[' => {
                    depth += 1;
                    current.push(ch);
                }
                ']' => {
                    depth = depth.saturating_sub(1);
                    current.push(ch);
                }
                ',' if depth == 0 => {
                    if !current.trim().is_empty() {
                        items.push(current.trim().to_string());
                    }
                    current.clear();
                }
                _ => current.push(ch),
            },
        }
    }
    if !current.trim().is_empty() {
        items.push(current.trim().to_string());
    }
    items
}

fn has_path_separator(command: &str) -> bool {
    command.contains('/') || command.contains('\\')
}

fn default_threads_dir() -> PathBuf {
    match std::env::var("CODEX_EXEC_STATE_DIR") {
        Ok(dir) if !dir.is_empty() => PathBuf::from(dir).join("threads"),
        _ => PathBuf::from(crate::home_dir())
            .join(".codex")
            .join("state")
            .join("codex-exec")
            .join("threads"),
    }
}

impl CodexExecBridge {
    /// The built-in backend: `codex_bin` is the executable to run (the CLI
    /// passes its probe-resolved native path), xhigh floor, 1800 s timeout,
    /// shared thread directory.
    #[must_use]
    pub fn new(codex_bin: impl Into<PathBuf>) -> Self {
        Self {
            codex_bin: codex_bin.into(),
            env: BTreeMap::new(),
            default_config: vec![(EFFORT_FLOOR_KEY.to_string(), EFFORT_FLOOR_VALUE.to_string())],
            timeout: Duration::from_secs(CODEX_EXEC_DEFAULT_TIMEOUT_SECS),
            threads_dir: default_threads_dir(),
        }
    }

    /// In-memory migration of a legacy `codex mcp-server` entry: keep its
    /// executable (unless the caller resolved a native path), environment,
    /// `-c` defaults and explicit `requestTimeoutSecs`. Trust stays on the
    /// config entry itself (read by the CLI as before).
    #[must_use]
    pub fn from_legacy_entry(config: &McpStdioServerConfig, resolved_bin: Option<PathBuf>) -> Self {
        // An explicitly pinned executable path stays; only a bare `codex`
        // (PATH lookup, possibly shadowed by a Windows shim) takes the
        // probe-resolved native path.
        let bin = if has_path_separator(&config.command) {
            PathBuf::from(&config.command)
        } else {
            resolved_bin.unwrap_or_else(|| PathBuf::from(&config.command))
        };
        let mut bridge = Self::new(bin);
        bridge.env.clone_from(&config.env);
        let mut args = config.args.iter();
        while let Some(arg) = args.next() {
            let pair = if arg == "-c" || arg == "--config" {
                args.next().cloned()
            } else {
                arg.strip_prefix("--config=")
                    .or_else(|| arg.strip_prefix("-c="))
                    .map(str::to_string)
            };
            if let Some((key, value)) = pair.as_deref().and_then(|p| p.split_once('=')) {
                // Carried settings override a same-key default (the effort
                // floor included) but never remove the floor itself.
                match bridge.default_config.iter_mut().find(|(k, _)| k == key) {
                    Some(slot) => slot.1 = value.to_string(),
                    None => bridge.default_config.push((key.to_string(), value.to_string())),
                }
            }
        }
        if let Some(secs) = config.request_timeout_secs {
            bridge.timeout = Duration::from_secs(secs.max(1));
        }
        bridge
    }

    /// The defaults this bridge would apply to `spec` — everything in
    /// `default_config` whose dotted key the call's own `config` does not set.
    fn defaults_for(&self, spec: &CallSpec) -> Vec<(String, String)> {
        let mut call_flags = Vec::new();
        let _ = config_flags(spec.config.as_ref(), "", &mut call_flags);
        let mut call_keys: Vec<&str> = call_flags
            .iter()
            .filter(|a| *a != "-c")
            .filter_map(|a| a.split_once('=').map(|(k, _)| k))
            .collect();
        // The call's `sandbox` IS the sandbox_mode setting; a carried legacy
        // `-c sandbox_mode=…` default must not shadow it.
        if spec.sandbox.is_some() {
            call_keys.push(SANDBOX_KEY);
        }
        self.default_config
            .iter()
            .filter(|(key, _)| !call_keys.contains(&key.as_str()))
            .cloned()
            .collect()
    }

    /// The record to remember for a thread: the call's own settings plus the
    /// bridge defaults that were applied, so a resume — by this bridge or the
    /// Python one — re-applies the same effective configuration.
    fn record_for(&self, spec: &CallSpec, cwd: Option<String>) -> CallSpec {
        let mut config = match &spec.config {
            Some(JsonValue::Object(map)) => map.clone(),
            _ => serde_json::Map::new(),
        };
        let mut sandbox = spec.sandbox.clone();
        for (key, value) in self.defaults_for(spec) {
            let json = toml_literal_to_json(&value);
            if key == SANDBOX_KEY {
                // Only reached when the call had no sandbox: the default IS
                // the effective sandbox, so it belongs in the record's
                // `sandbox` field (resume emits exactly one sandbox_mode).
                if sandbox.is_none() {
                    sandbox = json.as_str().map(str::to_string);
                }
            } else {
                config.insert(key, json);
            }
        }
        CallSpec {
            model: spec.model.clone(),
            config: if config.is_empty() {
                None
            } else {
                Some(JsonValue::Object(config))
            },
            sandbox,
            cwd,
        }
    }

    /// The two tools the `codex` server advertises (same names, schemas and
    /// descriptions as the Python bridge, which mirror the removed entry point).
    #[must_use]
    pub fn tools() -> Vec<McpTool> {
        vec![
            McpTool {
                name: "codex".to_string(),
                description: Some(
                    "Run a Codex session. Accepts configuration parameters matching the Codex Config struct."
                        .to_string(),
                ),
                input_schema: Some(json!({
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The *initial user prompt* to start the Codex conversation."},
                        "model": {"type": "string", "description": "Optional override for the model name (e.g. 'gpt-6-astra', 'gpt-5.5')."},
                        "config": {
                            "type": "object",
                            "additionalProperties": true,
                            "description": "Individual config settings that will override what is in CODEX_HOME/config.toml (e.g. {\"model_reasoning_effort\": \"xhigh\"})."
                        },
                        "sandbox": {"type": "string", "enum": SANDBOX_MODES, "description": "Sandbox mode: `read-only`, `workspace-write`, or `danger-full-access`."},
                        "cwd": {"type": "string", "description": "Working directory for the session. If relative, it is resolved against the aris process's current working directory."}
                    },
                    "required": ["prompt"]
                })),
                annotations: None,
                meta: None,
            },
            McpTool {
                name: "codex-reply".to_string(),
                description: Some(
                    "Continue a Codex conversation by providing the thread id and prompt. The thread keeps the model and config it was created with."
                        .to_string(),
                ),
                input_schema: Some(json!({
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The *next user prompt* to continue the Codex conversation."},
                        "threadId": {"type": "string", "description": "The thread id for this Codex session."},
                        "conversationId": {"type": "string", "description": "DEPRECATED: use threadId instead."}
                    },
                    "required": ["prompt"]
                })),
                annotations: None,
                meta: None,
            },
        ]
    }

    /// Arguments after the executable for one run (pure). `resume` selects
    /// `codex exec resume <id>`, which carries sandbox through `-c sandbox_mode`
    /// and the working directory through the child's cwd instead of
    /// `--sandbox` / `--cd`.
    pub fn build_argv(&self, spec: &CallSpec, resume: Option<&str>) -> Result<Vec<String>, String> {
        let mut argv = vec!["exec".to_string()];
        if let Some(thread_id) = resume {
            argv.push("resume".to_string());
            argv.push(thread_id.to_string());
        }
        argv.push("--skip-git-repo-check".to_string());
        argv.push("--json".to_string());
        if resume.is_none() {
            if let Some(sandbox) = spec.sandbox.as_deref() {
                argv.push("--sandbox".to_string());
                argv.push(sandbox.to_string());
            }
            if let Some(cwd) = spec.cwd.as_deref() {
                argv.push("--cd".to_string());
                argv.push(cwd.to_string());
            }
        }
        if let Some(model) = spec.model.as_deref() {
            argv.push("-m".to_string());
            argv.push(model.to_string());
        }
        // Defaults first, the call's own settings after them: a later `-c`
        // wins in codex, so an explicit value always beats a bridge default.
        for (key, value) in self.defaults_for(spec) {
            argv.push("-c".to_string());
            argv.push(format!("{key}={value}"));
        }
        if resume.is_some() {
            if let Some(sandbox) = spec.sandbox.as_deref() {
                argv.push("-c".to_string());
                argv.push(format!("sandbox_mode={}", toml_value(&JsonValue::String(sandbox.to_string()))?));
            }
        }
        config_flags(spec.config.as_ref(), "", &mut argv)?;
        argv.push("-".to_string());
        Ok(argv)
    }

    fn thread_file(&self, thread_id: &str) -> PathBuf {
        self.threads_dir.join(format!("{thread_id}.json"))
    }

    /// Read the record a thread was created with; an absent or unreadable
    /// record yields an empty spec (the reply then runs on `config.toml`
    /// defaults, exactly like the Python bridge).
    #[must_use]
    pub fn recall_thread(&self, thread_id: &str) -> CallSpec {
        std::fs::read_to_string(self.thread_file(thread_id))
            .ok()
            .and_then(|text| serde_json::from_str(&text).ok())
            .unwrap_or_default()
    }

    /// Write the record (temp file + rename; one file per thread). Best effort:
    /// a failed write only costs the reply its remembered settings.
    pub fn remember_thread(&self, thread_id: &str, spec: &CallSpec) {
        let Ok(text) = serde_json::to_string(spec) else {
            return;
        };
        if std::fs::create_dir_all(&self.threads_dir).is_err() {
            return;
        }
        let tmp = self.threads_dir.join(format!("{thread_id}.json.tmp"));
        if std::fs::write(&tmp, text).is_ok() {
            let _ = std::fs::rename(&tmp, self.thread_file(thread_id));
        }
    }

    /// Handle one `tools/call` for this server. Invalid arguments surface as
    /// JSON-RPC errors (same codes as the Python bridge); a run that started
    /// always comes back as a tool result, `isError` on failure.
    pub async fn call(
        &self,
        request_id: JsonRpcId,
        raw_tool_name: &str,
        arguments: Option<JsonValue>,
    ) -> JsonRpcResponse<McpToolCallResult> {
        let arguments = arguments.unwrap_or(JsonValue::Null);
        let Some(prompt) = arguments.get("prompt").and_then(JsonValue::as_str) else {
            return rpc_error(request_id, -32602, "prompt is required");
        };

        let (spec, resume, run_cwd) = match raw_tool_name {
            "codex" => {
                let spec = CallSpec::from_arguments(&arguments);
                (spec, None, None)
            }
            "codex-reply" => {
                let thread_id = arguments
                    .get("threadId")
                    .or_else(|| arguments.get("conversationId"))
                    .and_then(JsonValue::as_str)
                    .filter(|s| !s.is_empty());
                let Some(thread_id) = thread_id else {
                    return rpc_error(request_id, -32602, "threadId is required");
                };
                let remembered = self.recall_thread(thread_id);
                let cwd = remembered.cwd.clone().map(PathBuf::from);
                (remembered, Some(thread_id.to_string()), cwd)
            }
            other => {
                return rpc_error(request_id, -32601, &format!("unknown tool: {other}"));
            }
        };

        let argv = match self.build_argv(&spec, resume.as_deref()) {
            Ok(argv) => argv,
            Err(message) => return rpc_error(request_id, -32602, &message),
        };

        let mut outcome = self.run(&argv, prompt, run_cwd.as_deref()).await;
        match resume {
            None => {
                if let Some(thread_id) = outcome.thread_id.clone() {
                    let cwd = spec
                        .cwd
                        .as_deref()
                        .map(|c| std::path::absolute(c).unwrap_or_else(|_| PathBuf::from(c)))
                        .or_else(|| std::env::current_dir().ok())
                        .map(|p| p.to_string_lossy().into_owned());
                    self.remember_thread(&thread_id, &self.record_for(&spec, cwd));
                }
            }
            Some(thread_id) => {
                if outcome.thread_id.is_none() {
                    outcome.thread_id = Some(thread_id);
                }
            }
        }

        JsonRpcResponse {
            jsonrpc: "2.0".to_string(),
            id: request_id,
            result: Some(outcome.into_tool_result()),
            error: None,
        }
    }

    /// Spawn `codex exec`, feed the prompt on stdin, fold the JSONL events,
    /// capture stderr. The child is killed on timeout or user interrupt.
    async fn run(&self, argv: &[String], prompt: &str, cwd: Option<&Path>) -> CallOutcome {
        let mut outcome = CallOutcome::default();
        let mut command = Command::new(&self.codex_bin);
        command
            .args(argv)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        for (key, value) in &self.env {
            command.env(key, value);
        }
        if let Some(cwd) = cwd {
            command.current_dir(cwd);
        }
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                outcome.error = Some(format!(
                    "could not start {}: {error}",
                    self.codex_bin.display()
                ));
                return outcome;
            }
        };
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();

        let prompt_bytes = prompt.as_bytes().to_vec();
        let feed = async move {
            if let Some(mut stdin) = stdin {
                // A child that exits early closes the pipe; that is reported
                // through the events / exit status, not here.
                let _ = stdin.write_all(&prompt_bytes).await;
                let _ = stdin.shutdown().await;
            }
        };
        let drain_stderr = async move {
            let mut buffer = Vec::new();
            if let Some(mut stderr) = stderr {
                let _ = stderr.read_to_end(&mut buffer).await;
            }
            String::from_utf8_lossy(&buffer).into_owned()
        };
        // Events fold into a shared cell as they arrive (the join below runs
        // on one task, so a RefCell is enough) — a timeout or Ctrl+C then still
        // knows the thread id `thread.started` announced, and the thread stays
        // resumable.
        let folded = std::cell::RefCell::new(CallOutcome::default());
        let read_events = async {
            if let Some(stdout) = stdout {
                let mut lines = BufReader::new(stdout).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    let line = line.trim();
                    if line.is_empty() {
                        continue;
                    }
                    if let Ok(event) = serde_json::from_str::<JsonValue>(line) {
                        folded.borrow_mut().apply_event(&event);
                    }
                }
            }
        };
        let work = async {
            let ((), stderr_text, ()) = tokio::join!(feed, drain_stderr, read_events);
            stderr_text
        };
        let interrupted = async {
            loop {
                if crate::is_interrupted() {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        };

        tokio::pin!(work);
        let (stderr_text, exit_status) = tokio::select! {
            result = tokio::time::timeout(self.timeout, &mut work) => {
                let Ok(stderr_text) = result else {
                    let _ = child.start_kill();
                    let _ = child.wait().await;
                    outcome = folded.borrow().clone();
                    outcome.failed = true;
                    outcome.error = Some(format!(
                        "codex exec timed out after {} s",
                        self.timeout.as_secs()
                    ));
                    return outcome;
                };
                let status = child.wait().await.ok();
                (stderr_text, describe_exit(status.as_ref()))
            },
            () = interrupted => {
                let _ = child.start_kill();
                let _ = child.wait().await;
                outcome = folded.borrow().clone();
                outcome.cancelled = true;
                (String::new(), "interrupted".to_string())
            }
        };
        if !outcome.cancelled {
            outcome = folded.borrow().clone();
        }
        outcome.finalize(&exit_status, &stderr_text);
        outcome
    }
}

fn describe_exit(status: Option<&std::process::ExitStatus>) -> String {
    match status.and_then(std::process::ExitStatus::code) {
        Some(code) => code.to_string(),
        None => "signal".to_string(),
    }
}

fn rpc_error(id: JsonRpcId, code: i64, message: &str) -> JsonRpcResponse<McpToolCallResult> {
    JsonRpcResponse {
        jsonrpc: "2.0".to_string(),
        id,
        result: None,
        error: Some(JsonRpcError {
            code,
            message: message.to_string(),
            data: None,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bridge() -> CodexExecBridge {
        let mut bridge = CodexExecBridge::new("codex");
        bridge.threads_dir = std::env::temp_dir().join(format!(
            "aris-codex-exec-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_or(0, |d| d.as_nanos())
        ));
        bridge
    }

    fn event(text: &str) -> JsonValue {
        serde_json::from_str(text).expect("valid event json")
    }

    #[test]
    fn fresh_argv_matches_python_bridge_shape() {
        let spec = CallSpec {
            model: Some("gpt-6-astra".to_string()),
            config: Some(json!({"model_reasoning_effort": "ultra", "nested": {"flag": true, "n": 3}})),
            sandbox: Some("read-only".to_string()),
            cwd: Some("/repo".to_string()),
        };
        let argv = bridge().build_argv(&spec, None).unwrap();
        assert_eq!(
            argv,
            vec![
                "exec",
                "--skip-git-repo-check",
                "--json",
                "--sandbox",
                "read-only",
                "--cd",
                "/repo",
                "-m",
                "gpt-6-astra",
                "-c",
                "model_reasoning_effort=\"ultra\"",
                "-c",
                "nested.flag=true",
                "-c",
                "nested.n=3",
                "-",
            ]
        );
    }

    #[test]
    fn resume_argv_reapplies_model_effort_and_sandbox_via_config() {
        let spec = CallSpec {
            model: Some("gpt-6-astra".to_string()),
            config: Some(json!({"model_reasoning_effort": "xhigh"})),
            sandbox: Some("workspace-write".to_string()),
            cwd: Some("/repo".to_string()),
        };
        let argv = bridge().build_argv(&spec, Some("thread-1")).unwrap();
        assert_eq!(
            argv,
            vec![
                "exec",
                "resume",
                "thread-1",
                "--skip-git-repo-check",
                "--json",
                "-m",
                "gpt-6-astra",
                "-c",
                "sandbox_mode=\"workspace-write\"",
                "-c",
                "model_reasoning_effort=\"xhigh\"",
                "-",
            ]
        );
        assert!(!argv.contains(&"--cd".to_string()));
    }

    #[test]
    fn bare_call_gets_xhigh_floor_and_explicit_effort_wins() {
        let bare = bridge().build_argv(&CallSpec::default(), None).unwrap();
        assert!(bare
            .windows(2)
            .any(|w| w[0] == "-c" && w[1] == "model_reasoning_effort=\"xhigh\""));

        let spec = CallSpec {
            config: Some(json!({"model_reasoning_effort": "ultra"})),
            ..CallSpec::default()
        };
        let explicit = bridge().build_argv(&spec, None).unwrap();
        let efforts: Vec<&String> = explicit
            .iter()
            .filter(|a| a.starts_with("model_reasoning_effort="))
            .collect();
        assert_eq!(efforts, vec!["model_reasoning_effort=\"ultra\""]);
    }

    #[test]
    fn approval_policy_never_reaches_argv() {
        let arguments = json!({
            "prompt": "hi",
            "approval-policy": "never",
            "sandbox": "read-only"
        });
        let spec = CallSpec::from_arguments(&arguments);
        let argv = bridge().build_argv(&spec, None).unwrap();
        assert!(!argv.iter().any(|a| a.contains("approval")));
    }

    #[test]
    fn legacy_entry_carries_env_config_and_timeout() {
        let mut env = BTreeMap::new();
        env.insert("CODEX_HOME".to_string(), "/x".to_string());
        let config = McpStdioServerConfig {
            command: "codex".to_string(),
            args: vec![
                "mcp-server".to_string(),
                "-c".to_string(),
                "model_reasoning_effort=\"xhigh\"".to_string(),
            ],
            env,
            request_timeout_secs: Some(900),
            trust: Some(true),
        };
        assert!(is_legacy_codex_mcp_server(&config));
        let bridge = CodexExecBridge::from_legacy_entry(&config, Some(PathBuf::from("/opt/codex")));
        assert_eq!(bridge.codex_bin, PathBuf::from("/opt/codex"));
        assert_eq!(bridge.env.get("CODEX_HOME").map(String::as_str), Some("/x"));
        assert_eq!(
            bridge.default_config,
            vec![("model_reasoning_effort".to_string(), "\"xhigh\"".to_string())]
        );
        assert_eq!(bridge.timeout, Duration::from_mins(15));
    }

    #[test]
    fn legacy_detection_ignores_custom_and_windows_shim_spelling() {
        let custom = McpStdioServerConfig {
            command: "python3".to_string(),
            args: vec!["/aris/mcp-servers/codex-exec/server.py".to_string()],
            env: BTreeMap::new(),
            request_timeout_secs: None,
            trust: None,
        };
        assert!(!is_legacy_codex_mcp_server(&custom));
        let windows = McpStdioServerConfig {
            command: "C:\\Users\\me\\AppData\\Roaming\\npm\\codex.cmd".to_string(),
            args: vec!["mcp-server".to_string()],
            env: BTreeMap::new(),
            request_timeout_secs: None,
            trust: None,
        };
        // `Path::file_name` on Unix does not split backslashes; the classifier
        // only needs the Windows spelling to be recognised on Windows, where
        // it does. Here we only assert the Unix-style path form.
        let unix_style = McpStdioServerConfig {
            command: "/usr/local/bin/codex".to_string(),
            ..windows
        };
        assert!(is_legacy_codex_mcp_server(&unix_style));
    }

    #[test]
    fn event_precedence_matches_bridge_contract() {
        // last agent_message wins; turn.completed clears an intermediate error
        let mut ok = CallOutcome::default();
        ok.apply_event(&event(r#"{"type":"thread.started","thread_id":"t1"}"#));
        ok.apply_event(&event(r#"{"type":"item.completed","item":{"type":"agent_message","text":"draft"}}"#));
        ok.apply_event(&event(r#"{"type":"error","message":"transient"}"#));
        ok.apply_event(&event(r#"{"type":"item.completed","item":{"type":"agent_message","text":"final"}}"#));
        ok.apply_event(&event(r#"{"type":"turn.completed"}"#));
        ok.finalize("0", "");
        assert_eq!(ok.thread_id.as_deref(), Some("t1"));
        assert_eq!(ok.last_message.as_deref(), Some("final"));
        assert_eq!(ok.error, None);

        // turn.failed is terminal even if turn.completed follows
        let mut failed = CallOutcome::default();
        failed.apply_event(&event(r#"{"type":"turn.failed","error":{"message":"model unknown: gpt-9"}}"#));
        failed.apply_event(&event(r#"{"type":"turn.completed"}"#));
        failed.finalize("0", "");
        assert_eq!(failed.error.as_deref(), Some("model unknown: gpt-9"));

        // an un-cleared error survives EOF without turn.completed
        let mut errored = CallOutcome::default();
        errored.apply_event(&event(r#"{"type":"error","message":"stream reset"}"#));
        errored.finalize("1", "ignored stderr");
        assert_eq!(errored.error.as_deref(), Some("stream reset"));

        // no completion, no error → status + stderr tail
        let mut silent = CallOutcome::default();
        silent.finalize("2", "  codex: not logged in\n");
        assert_eq!(
            silent.error.as_deref(),
            Some("codex exec exited with status 2 before completing the turn\ncodex: not logged in")
        );

        // cancellation beats everything
        let mut cancelled = CallOutcome::default();
        cancelled.apply_event(&event(r#"{"type":"turn.completed"}"#));
        cancelled.cancelled = true;
        cancelled.finalize("0", "");
        assert_eq!(cancelled.error.as_deref(), Some("cancelled by client"));
    }

    #[test]
    fn tool_result_keeps_raw_error_text_and_thread_id() {
        let outcome = CallOutcome {
            thread_id: Some("t9".to_string()),
            error: Some("The model `gpt-9` does not exist".to_string()),
            ..CallOutcome::default()
        };
        let result = outcome.into_tool_result();
        assert_eq!(result.is_error, Some(true));
        assert_eq!(
            result.content[0].data.get("text").and_then(JsonValue::as_str),
            Some("The model `gpt-9` does not exist")
        );
        assert_eq!(
            result.structured_content,
            Some(json!({"threadId": "t9", "content": "The model `gpt-9` does not exist"}))
        );

        let ok = CallOutcome {
            thread_id: Some("t9".to_string()),
            last_message: Some("VERDICT: GO".to_string()),
            ..CallOutcome::default()
        };
        let result = ok.into_tool_result();
        assert_eq!(result.is_error, None);
        assert_eq!(
            result.structured_content,
            Some(json!({"threadId": "t9", "content": "VERDICT: GO"}))
        );
    }

    #[test]
    fn thread_record_roundtrips_and_writes_python_compatible_json() {
        let bridge = bridge();
        let spec = CallSpec {
            model: Some("gpt-6-astra".to_string()),
            config: Some(json!({"model_reasoning_effort": "ultra"})),
            sandbox: None,
            cwd: Some("/repo".to_string()),
        };
        bridge.remember_thread("abc", &spec);
        let raw = std::fs::read_to_string(bridge.threads_dir.join("abc.json")).unwrap();
        let json: JsonValue = serde_json::from_str(&raw).unwrap();
        // null values are present (Python `json.dump` of the dict), keys match
        assert_eq!(json.get("sandbox"), Some(&JsonValue::Null));
        assert_eq!(json.get("model").and_then(JsonValue::as_str), Some("gpt-6-astra"));
        assert_eq!(bridge.recall_thread("abc"), spec);
        assert_eq!(bridge.recall_thread("missing"), CallSpec::default());
        // a record written by the Python bridge reads back
        std::fs::write(
            bridge.threads_dir.join("py.json"),
            r#"{"model": "gpt-5.5", "config": null, "sandbox": "read-only", "cwd": "/w"}"#,
        )
        .unwrap();
        let py = bridge.recall_thread("py");
        assert_eq!(py.model.as_deref(), Some("gpt-5.5"));
        assert_eq!(py.sandbox.as_deref(), Some("read-only"));
        assert_eq!(py.cwd.as_deref(), Some("/w"));
        let _ = std::fs::remove_dir_all(&bridge.threads_dir);
    }

    #[test]
    fn tools_advertise_codex_and_codex_reply() {
        let tools = CodexExecBridge::tools();
        let names: Vec<&str> = tools.iter().map(|t| t.name.as_str()).collect();
        assert_eq!(names, vec!["codex", "codex-reply"]);
        let schema = tools[0].input_schema.as_ref().unwrap();
        assert_eq!(schema["required"], json!(["prompt"]));
    }


    /// Live contract check against the installed codex-cli (run by hand:
    /// `cargo test -p runtime real_codex -- --ignored --nocapture`). Needs a
    /// logged-in `codex` on PATH; verifies fresh call + resume on the real
    /// `--json` event stream.
    #[test]
    #[ignore = "needs a logged-in codex on PATH; run by hand"]
    fn real_codex_roundtrip() {
        let which = std::process::Command::new("which").arg("codex").output().unwrap();
        let bin = String::from_utf8_lossy(&which.stdout).trim().to_string();
        assert!(!bin.is_empty(), "codex not on PATH");
        let mut bridge = bridge();
        bridge.codex_bin = PathBuf::from(bin);
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        let first = rt.block_on(bridge.call(
            JsonRpcId::Number(1),
            "codex",
            Some(json!({
                "prompt": "Reply with exactly the single word PONG and nothing else.",
                "sandbox": "read-only",
                "config": {"model_reasoning_effort": "low"}
            })),
        ));
        let result = first.result.expect("tool result");
        eprintln!("first: {result:?}");
        assert_eq!(result.is_error, None, "{result:?}");
        let structured = result.structured_content.unwrap();
        let thread_id = structured["threadId"].as_str().unwrap().to_string();
        assert!(structured["content"].as_str().unwrap().contains("PONG"));
        let record = bridge.recall_thread(&thread_id);
        assert_eq!(record.sandbox.as_deref(), Some("read-only"));

        let second = rt.block_on(bridge.call(
            JsonRpcId::Number(2),
            "codex-reply",
            Some(json!({"prompt": "Now reply with exactly the single word PING.", "threadId": thread_id})),
        ));
        let result = second.result.expect("tool result");
        eprintln!("second: {result:?}");
        assert_eq!(result.is_error, None, "{result:?}");
        assert_eq!(result.structured_content.unwrap()["threadId"].as_str(), Some(thread_id.as_str()));
        let _ = std::fs::remove_dir_all(&bridge.threads_dir);
    }


    #[test]
    fn legacy_detection_accepts_option_before_subcommand_and_rejects_exec() {
        let mk = |args: &[&str]| McpStdioServerConfig {
            command: "codex".to_string(),
            args: args.iter().map(|a| (*a).to_string()).collect(),
            env: BTreeMap::new(),
            request_timeout_secs: None,
            trust: None,
        };
        assert!(is_legacy_codex_mcp_server(&mk(&["-c", "model=\"gpt-5.5\"", "mcp-server"])));
        assert!(is_legacy_codex_mcp_server(&mk(&["mcp-server", "--config", "model_reasoning_effort=\"medium\""])));
        assert!(!is_legacy_codex_mcp_server(&mk(&["exec", "--json"])));
        assert!(!is_legacy_codex_mcp_server(&mk(&[])));
    }

    #[test]
    fn legacy_migration_keeps_pinned_path_and_merges_defaults_around_the_floor() {
        // pinned executable path is kept even when the probe found another codex
        let pinned = McpStdioServerConfig {
            command: "/opt/pinned/codex".to_string(),
            args: vec!["mcp-server".to_string()],
            env: BTreeMap::new(),
            request_timeout_secs: None,
            trust: None,
        };
        let bridge = CodexExecBridge::from_legacy_entry(&pinned, Some(PathBuf::from("/other/codex")));
        assert_eq!(bridge.codex_bin, PathBuf::from("/opt/pinned/codex"));

        // an unrelated -c default is carried AND the xhigh floor survives;
        // --config spelling and option-before-subcommand order both count
        let extra = McpStdioServerConfig {
            command: "codex".to_string(),
            args: vec![
                "--config".to_string(),
                "model_provider=\"azure\"".to_string(),
                "mcp-server".to_string(),
            ],
            env: BTreeMap::new(),
            request_timeout_secs: None,
            trust: None,
        };
        let bridge = CodexExecBridge::from_legacy_entry(&extra, None);
        assert_eq!(bridge.codex_bin, PathBuf::from("codex"));
        assert_eq!(
            bridge.default_config,
            vec![
                ("model_reasoning_effort".to_string(), "\"xhigh\"".to_string()),
                ("model_provider".to_string(), "\"azure\"".to_string()),
            ]
        );
        // a carried effort replaces the floor instead of duplicating it
        let medium = McpStdioServerConfig {
            args: vec!["mcp-server".to_string(), "-c".to_string(), "model_reasoning_effort=\"medium\"".to_string()],
            ..extra
        };
        let bridge = CodexExecBridge::from_legacy_entry(&medium, None);
        assert_eq!(
            bridge.default_config,
            vec![("model_reasoning_effort".to_string(), "\"medium\"".to_string())]
        );
    }

    #[test]
    fn defaults_precede_call_config_and_respect_nested_keys() {
        let mut bridge = bridge();
        bridge.default_config.push((
            "shell_environment_policy.inherit".to_string(),
            "\"all\"".to_string(),
        ));
        let spec = CallSpec {
            config: Some(json!({"shell_environment_policy": {"inherit": "none"}})),
            ..CallSpec::default()
        };
        let argv = bridge.build_argv(&spec, None).unwrap();
        let flags: Vec<&String> = argv.iter().filter(|a| a.contains('=')).collect();
        // the nested call key suppresses the dotted default; the floor is
        // still applied and comes BEFORE the call's own settings
        assert_eq!(
            flags,
            vec!["model_reasoning_effort=\"xhigh\"", "shell_environment_policy.inherit=\"none\""]
        );
    }

    #[test]
    fn legacy_sandbox_default_never_overrides_the_recorded_sandbox() {
        let mut bridge = bridge();
        bridge
            .default_config
            .push(("sandbox_mode".to_string(), "\"workspace-write\"".to_string()));
        // fresh call pins read-only → the default is suppressed on the fresh
        // argv and the record carries read-only as the effective sandbox
        let spec = CallSpec {
            sandbox: Some("read-only".to_string()),
            ..CallSpec::default()
        };
        let fresh = bridge.build_argv(&spec, None).unwrap();
        assert!(!fresh.iter().any(|a| a.starts_with("sandbox_mode=")));
        let record = bridge.record_for(&spec, Some("/w".to_string()));
        assert_eq!(record.sandbox.as_deref(), Some("read-only"));
        assert_eq!(record.config, Some(json!({"model_reasoning_effort": "xhigh"})));
        let resumed = bridge.build_argv(&record, Some("t1")).unwrap();
        let sandbox_flags: Vec<&String> =
            resumed.iter().filter(|a| a.starts_with("sandbox_mode=")).collect();
        assert_eq!(sandbox_flags, vec!["sandbox_mode=\"read-only\""]);

        // fresh call without a sandbox → the legacy default becomes the
        // recorded sandbox (one flag on resume, same value both times)
        let bare = CallSpec::default();
        let fresh = bridge.build_argv(&bare, None).unwrap();
        assert!(fresh.contains(&"sandbox_mode=\"workspace-write\"".to_string()));
        let record = bridge.record_for(&bare, None);
        assert_eq!(record.sandbox.as_deref(), Some("workspace-write"));
        let resumed = bridge.build_argv(&record, Some("t1")).unwrap();
        let sandbox_flags: Vec<&String> =
            resumed.iter().filter(|a| a.starts_with("sandbox_mode=")).collect();
        assert_eq!(sandbox_flags, vec!["sandbox_mode=\"workspace-write\""]);
    }

    #[test]
    fn toml_literals_decode_to_the_json_python_would_store() {
        assert_eq!(toml_literal_to_json("\"xhigh\""), json!("xhigh"));
        assert_eq!(toml_literal_to_json("'xhigh'"), json!("xhigh"));
        assert_eq!(toml_literal_to_json("true"), json!(true));
        assert_eq!(toml_literal_to_json("3"), json!(3));
        assert_eq!(toml_literal_to_json("[\"a\", 1]"), json!(["a", 1]));
        assert_eq!(toml_literal_to_json("['AWS_*', 'AZURE_*']"), json!(["AWS_*", "AZURE_*"]));
        assert_eq!(toml_literal_to_json("[['a,b'], true]"), json!([["a,b"], true]));
        // escaped quotes inside a basic string do not end it (codex `notify`)
        assert_eq!(
            toml_literal_to_json(r#"["sh", "-c", "printf \"review, done\""]"#),
            json!(["sh", "-c", "printf \"review, done\""])
        );
        let mut notify = Vec::new();
        config_flags(
            Some(&json!({"notify": toml_literal_to_json(r#"["sh", "-c", "printf \"review, done\""]"#)})),
            "",
            &mut notify,
        )
        .unwrap();
        assert_eq!(notify, vec!["-c", r#"notify=["sh", "-c", "printf \"review, done\""]"#]);
        assert_eq!(toml_literal_to_json("bare-word"), json!("bare-word"));
        // the array round-trips into the flag the Python bridge would emit
        let mut flags = Vec::new();
        config_flags(
            Some(&json!({"shell_environment_policy": {"exclude": toml_literal_to_json("['AWS_*', 'AZURE_*']")}})),
            "",
            &mut flags,
        )
        .unwrap();
        assert_eq!(flags, vec!["-c", "shell_environment_policy.exclude=[\"AWS_*\", \"AZURE_*\"]"]);
        // a single-quoted legacy effort round-trips into the double-quoted flag
        let mut flags = Vec::new();
        config_flags(Some(&json!({"model_reasoning_effort": toml_literal_to_json("'xhigh'")})), "", &mut flags).unwrap();
        assert_eq!(flags, vec!["-c", "model_reasoning_effort=\"xhigh\""]);
    }

    #[test]
    fn thread_record_includes_applied_defaults_as_json() {
        let bridge = bridge();
        let record = bridge.record_for(&CallSpec::default(), Some("/w".to_string()));
        assert_eq!(record.config, Some(json!({"model_reasoning_effort": "xhigh"})));
        // Python's toml_value(json.dumps) of that record yields the same flag
        let mut flags = Vec::new();
        config_flags(record.config.as_ref(), "", &mut flags).unwrap();
        assert_eq!(flags, vec!["-c", "model_reasoning_effort=\"xhigh\""]);
        // an explicit effort is stored as given, not overwritten by the floor
        let spec = CallSpec {
            config: Some(json!({"model_reasoning_effort": "ultra"})),
            ..CallSpec::default()
        };
        assert_eq!(
            bridge.record_for(&spec, None).config,
            Some(json!({"model_reasoning_effort": "ultra"}))
        );
    }

    #[cfg(unix)]
    mod fake_codex {
        use super::*;
        use std::os::unix::fs::PermissionsExt;

        /// Write a fake `codex` executable that records its argv and stdin,
        /// then prints the given JSONL script.
        fn fake(script: &str) -> (CodexExecBridge, PathBuf) {
            let bridge = bridge();
            std::fs::create_dir_all(&bridge.threads_dir).unwrap();
            let bin = bridge.threads_dir.join("codex");
            let log = bridge.threads_dir.join("argv.log");
            let body = format!(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\ncat > {stdin}\n{script}\n",
                log = log.display(),
                stdin = bridge.threads_dir.join("stdin.txt").display(),
            );
            std::fs::write(&bin, body).unwrap();
            std::fs::set_permissions(&bin, std::fs::Permissions::from_mode(0o755)).unwrap();
            let mut bridge = bridge;
            bridge.codex_bin.clone_from(&bin);
            (bridge, log)
        }

        fn block_on<F: std::future::Future>(future: F) -> F::Output {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(future)
        }

        #[test]
        fn fresh_call_returns_thread_and_message_and_records_thread() {
            let (bridge, log) = fake(
                r#"echo '{"type":"thread.started","thread_id":"th-1"}'
echo '{"type":"item.completed","item":{"type":"agent_message","text":"VERDICT: GO"}}'
echo '{"type":"turn.completed"}'"#,
            );
            let response = block_on(bridge.call(
                JsonRpcId::Number(1),
                "codex",
                Some(json!({"prompt": "review this", "model": "gpt-6-astra", "sandbox": "read-only"})),
            ));
            let result = response.result.unwrap();
            assert_eq!(result.is_error, None);
            assert_eq!(
                result.structured_content,
                Some(json!({"threadId": "th-1", "content": "VERDICT: GO"}))
            );
            let argv = std::fs::read_to_string(log).unwrap();
            assert!(argv.contains("--sandbox\nread-only"));
            assert!(argv.contains("-m\ngpt-6-astra"));
            assert!(argv.contains("model_reasoning_effort=\"xhigh\""));
            let stdin = std::fs::read_to_string(bridge.threads_dir.join("stdin.txt")).unwrap();
            assert_eq!(stdin, "review this");
            let record = bridge.recall_thread("th-1");
            assert_eq!(record.model.as_deref(), Some("gpt-6-astra"));
            assert!(record.cwd.is_some());

            // reply re-applies the remembered model on `exec resume`
            let response = block_on(bridge.call(
                JsonRpcId::Number(2),
                "codex-reply",
                Some(json!({"prompt": "again", "threadId": "th-1"})),
            ));
            let result = response.result.unwrap();
            assert_eq!(result.structured_content.unwrap()["threadId"], json!("th-1"));
            let argv = std::fs::read_to_string(bridge.threads_dir.join("argv.log")).unwrap();
            assert!(argv.starts_with("exec\nresume\nth-1\n"));
            assert!(argv.contains("-m\ngpt-6-astra"));
            assert!(argv.contains("sandbox_mode=\"read-only\""));
            let _ = std::fs::remove_dir_all(&bridge.threads_dir);
        }

        #[test]
        fn failed_turn_surfaces_raw_codex_error() {
            let (bridge, _) = fake(
                r#"echo '{"type":"thread.started","thread_id":"th-2"}'
echo '{"type":"turn.failed","error":{"message":"The requested model gpt-9 is not available"}}'
exit 1"#,
            );
            let response = block_on(bridge.call(
                JsonRpcId::Number(1),
                "codex",
                Some(json!({"prompt": "x"})),
            ));
            let result = response.result.unwrap();
            assert_eq!(result.is_error, Some(true));
            assert_eq!(
                result.content[0].data["text"],
                json!("The requested model gpt-9 is not available")
            );
            assert_eq!(result.structured_content.unwrap()["threadId"], json!("th-2"));
            let _ = std::fs::remove_dir_all(&bridge.threads_dir);
        }

        #[test]
        fn timeout_kills_child_and_reports() {
            let (mut bridge, _) = fake(
                r#"echo '{"type":"thread.started","thread_id":"th-slow"}'
sleep 30"#,
            );
            bridge.timeout = Duration::from_secs(2);
            let started = std::time::Instant::now();
            let response = block_on(bridge.call(
                JsonRpcId::Number(1),
                "codex",
                Some(json!({"prompt": "x"})),
            ));
            assert!(started.elapsed() < Duration::from_secs(10));
            let result = response.result.unwrap();
            assert_eq!(result.is_error, Some(true));
            assert!(result.content[0].data["text"]
                .as_str()
                .unwrap()
                .contains("timed out"));
            // the thread id announced before the timeout survives, and its
            // record was written, so the thread stays resumable
            assert_eq!(result.structured_content.unwrap()["threadId"], json!("th-slow"));
            assert!(bridge.threads_dir.join("th-slow.json").exists());
            let _ = std::fs::remove_dir_all(&bridge.threads_dir);
        }

        #[test]
        fn missing_prompt_and_unknown_tool_are_rpc_errors() {
            let (bridge, _) = fake("exit 0");
            let response = block_on(bridge.call(JsonRpcId::Number(1), "codex", Some(json!({}))));
            assert_eq!(response.error.unwrap().code, -32602);
            let response = block_on(bridge.call(
                JsonRpcId::Number(2),
                "codex-reply",
                Some(json!({"prompt": "x"})),
            ));
            assert_eq!(response.error.unwrap().code, -32602);
            let response =
                block_on(bridge.call(JsonRpcId::Number(3), "other", Some(json!({"prompt": "x"}))));
            assert_eq!(response.error.unwrap().code, -32601);
            let _ = std::fs::remove_dir_all(&bridge.threads_dir);
        }
    }
}
