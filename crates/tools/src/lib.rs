use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

// Bundled skills are compiled into the runtime crate and re-exported
use runtime::BUNDLED_SKILLS;

use api::{
    read_base_url, AnthropicClient, ContentBlockDelta, InputContentBlock, InputMessage,
    MessageRequest, MessageResponse, OutputContentBlock, StreamEvent as ApiStreamEvent, ToolChoice,
    ToolDefinition, ToolResultContentBlock,
};
use reqwest::blocking::Client;
use runtime::{
    edit_file, execute_bash, glob_search, grep_search, load_system_prompt, read_file, write_file,
    ApiClient, ApiRequest, AssistantEvent, BashCommandInput, ContentBlock, ConversationMessage,
    ConversationRuntime, GrepSearchInput, MessageRole, PermissionMode, PermissionPolicy,
    RuntimeError, Session, TokenUsage, ToolError, ToolExecutor,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ToolManifestEntry {
    pub name: String,
    pub source: ToolSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolSource {
    Base,
    Conditional,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ToolRegistry {
    entries: Vec<ToolManifestEntry>,
}

impl ToolRegistry {
    #[must_use]
    pub fn new(entries: Vec<ToolManifestEntry>) -> Self {
        Self { entries }
    }

    #[must_use]
    pub fn entries(&self) -> &[ToolManifestEntry] {
        &self.entries
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ToolSpec {
    pub name: &'static str,
    pub description: &'static str,
    pub input_schema: Value,
    pub required_permission: PermissionMode,
}

/// v0.4.17 (T1): the owned-name counterpart to the static [`ToolSpec`].
///
/// The static `ToolSpec` keeps `name`/`description` as `&'static str` so the
/// hard-coded MVP catalogue (see [`mvp_tool_specs`]) stays a zero-allocation,
/// byte-for-byte-stable source of truth. But runtime-discovered MCP tools have
/// names/descriptions that are only known at runtime, so the provider request
/// construction layer is migrated to consume this owned variant instead.
///
/// `RuntimeToolSpec` carries exactly the three fields the API request needs
/// (`name`, `description`, `input_schema`) and intentionally drops
/// `required_permission`: permission registration is the CLI's concern and is
/// handled separately (a static-MVP `ToolSpec` keeps that field). Converting a
/// static `ToolSpec` into a `RuntimeToolSpec` is lossless for the request
/// payload (`From<&ToolSpec>` below), and the conversion is byte-identical to
/// the previous inline `ToolDefinition { name, description, input_schema }`
/// construction, which the characterization tests pin.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeToolSpec {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
}

impl From<&ToolSpec> for RuntimeToolSpec {
    fn from(spec: &ToolSpec) -> Self {
        Self {
            name: spec.name.to_string(),
            description: spec.description.to_string(),
            input_schema: spec.input_schema.clone(),
        }
    }
}

impl From<ToolSpec> for RuntimeToolSpec {
    fn from(spec: ToolSpec) -> Self {
        Self::from(&spec)
    }
}

/// v0.4.17 (T2): a single advertised MCP tool's dispatch route.
///
/// Maps the advertised name back to everything dispatch needs:
/// - `qualified_name`: the key the manager's `tool_index` understands, passed
///   to `call_tool`.
/// - `server_name`: the **raw** MCP server name (as configured / reported by
///   the runtime, before any normalization), carried straight from
///   [`runtime::ManagedMcpTool::server_name`]. This is preserved so per-server
///   policy (C2's per-server approval / trust) can identify the originating
///   server without reverse-engineering it from the advertised or qualified
///   name — both of which are lossy (normalization can collapse two distinct
///   raw server names to the same qualified prefix).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct McpRoute {
    /// The original `qualified_name` (`mcp__<server>__<tool>`) the manager can
    /// route via `call_tool`.
    pub qualified_name: String,
    /// The raw, un-normalized MCP server name this tool came from.
    pub server_name: String,
}

/// v0.4.17 (T2): the result of turning the manager's discovered
/// [`runtime::ManagedMcpTool`] list into advertisable specs.
///
/// MCP tool names are advertised to the model under their `qualified_name`
/// (`mcp__<server>__<tool>`, already normalized by the runtime). Because the
/// runtime's `normalize_name_for_mcp` collapses illegal characters to `_`, two
/// distinct tools can normalize to the **same** advertised name (e.g. a server
/// named `"a b"` and one named `"a_b"`, or two tools `"do it"` / `"do_it"`).
///
/// The advertised catalogue must contain no duplicate names (providers reject
/// duplicate tool names, and the model would have no way to disambiguate).
/// Worse, the runtime's own `tool_index` is keyed by `qualified_name`, so a
/// collision there is last-writer-wins: both colliding tools resolve to the
/// SAME surviving manager route. A numeric `_2`/`_3` suffix on the advertised
/// side would therefore be **fake disambiguation** — both advertised names
/// would still call the one surviving tool.
///
/// Collision policy is **last-wins**, mirroring the runtime `tool_index`
/// insert-overwrite semantics ([`mcp_stdio.rs`](crate) `tool_index`): when two
/// tools normalize to the same `qualified_name`, the LAST one (in
/// `ManagedMcpTool` input order, which is deterministic) keeps the advertised
/// name; its spec **replaces** any earlier collider in place (preserving the
/// earlier slot so advertised ordering stays deterministic), and a one-line
/// warning is written to stderr. The catalog survivor MUST equal the manager
/// survivor — both consume the same `ManagedMcpTool` order, so taking the last
/// on collision keeps the advertised description/schema/server_name describing
/// exactly the tool the manager's `call_tool` will execute. Precise
/// per-`(server, raw_name)` routing through a collision would
/// require a new manager API on the runtime side and is deferred to v0.5.0 /
/// when a real need appears.
///
/// Dispatch must call the server with the *original* `qualified_name` (that is
/// the key the manager's `tool_index` understands). `route_for_advertised_name`
/// maps an advertised name back to its [`McpRoute`] (qualified name + raw
/// server identity) so the manager's `call_tool` is always given a name it can
/// resolve, and so downstream per-server policy can recover the raw server.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct McpToolCatalog {
    specs: Vec<RuntimeToolSpec>,
    /// advertised name -> route (qualified name + raw server name)
    routes: BTreeMap<String, McpRoute>,
}

impl McpToolCatalog {
    /// The advertisable specs, one per surviving advertised name, in discovery
    /// order. On a `qualified_name` collision the last colliding tool's spec
    /// replaces the earlier one in place (**last-wins**, matching the runtime
    /// `tool_index` insert-overwrite semantics), so there are no duplicate
    /// names and no collision suffixes.
    #[must_use]
    pub fn specs(&self) -> &[RuntimeToolSpec] {
        &self.specs
    }

    /// Consume the catalog and yield the owned specs (used by the request
    /// construction layer to append onto the static catalogue).
    #[must_use]
    pub fn into_specs(self) -> Vec<RuntimeToolSpec> {
        self.specs
    }

    /// Map an advertised MCP tool name (as the model called it) back to its
    /// [`McpRoute`] (original `qualified_name` the manager can route + the raw
    /// server identity). Returns `None` for an advertised name this catalog
    /// never produced. On a `qualified_name` collision the route reflects the
    /// **last** colliding tool (last-wins, matching the runtime `tool_index`),
    /// so the raw server identity here equals the manager's `call_tool` target.
    #[must_use]
    pub fn route_for_advertised_name(&self, advertised_name: &str) -> Option<&McpRoute> {
        self.routes.get(advertised_name)
    }

    /// v0.4.17 (T10/P1.3): does this catalog advertise any tool from the given
    /// raw MCP server name? Used by the inline-`/setup` restart notice to decide
    /// whether the live (startup-discovered) catalog already contains the
    /// `codex` server's tools — if it does, no restart is needed; if it doesn't,
    /// the user must restart so the newly-written `mcpServers.codex` is spawned
    /// and advertised. The match is against the route's raw `server_name` (the
    /// un-normalized name carried from discovery), not the advertised/qualified
    /// name, which is lossy under normalization.
    #[must_use]
    pub fn has_server(&self, server_name: &str) -> bool {
        self.routes
            .values()
            .any(|route| route.server_name == server_name)
    }

    /// Number of advertised MCP tools.
    #[must_use]
    pub fn len(&self) -> usize {
        self.specs.len()
    }

    /// Whether the catalog advertises any MCP tools.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.specs.is_empty()
    }
}

/// v0.4.17 (T2): build the advertisable MCP tool catalog from the manager's
/// discovered tools.
///
/// Per-tool transformation:
/// - **`name`**: the tool's `qualified_name` (already `mcp__<server>__<tool>`).
/// - **`description`**: `tool.description` when present, otherwise a synthesized
///   `"MCP tool <name> (server: <server>)"` hint so the model isn't handed a
///   blank description.
/// - **`input_schema`**: `tool.input_schema` when it is a JSON object, otherwise
///   the minimal `{"type":"object"}` net. A non-object schema (or a missing
///   one) is replaced and a one-line warning is written to stderr — providers
///   require an object schema for function/tool parameters.
///
/// **Collision handling (last-wins):** when two tools normalize to the same
/// `qualified_name`, the LAST one (in input order) wins — its spec replaces the
/// earlier collider in place (preserving the advertised slot) and its route
/// overwrites the earlier route (warning on stderr). This mirrors the runtime
/// `tool_index` insert-overwrite (mcp_stdio.rs): both consume the same
/// `Vec<ManagedMcpTool>` order, so the catalog survivor equals the manager
/// survivor — see [`McpToolCatalog`] for why a `_2` suffix would be fake
/// disambiguation.
#[must_use]
pub fn mcp_tool_specs(tools: &[runtime::ManagedMcpTool]) -> McpToolCatalog {
    let mut specs = Vec::with_capacity(tools.len());
    let mut routes: BTreeMap<String, McpRoute> = BTreeMap::new();
    // advertised_name -> index into `specs`, so a collision can replace the
    // already-recorded spec in place (last-wins) without scanning.
    let mut spec_index: HashMap<String, usize> = HashMap::new();

    for tool in tools {
        let qualified_name = tool.qualified_name.clone();

        let description = match tool.tool.description.as_deref() {
            Some(text) if !text.is_empty() => text.to_string(),
            _ => format!(
                "MCP tool {} (server: {})",
                tool.qualified_name, tool.server_name
            ),
        };

        let input_schema =
            sanitize_mcp_input_schema(tool.tool.input_schema.as_ref(), &qualified_name);

        let spec = RuntimeToolSpec {
            name: qualified_name.clone(),
            description,
            input_schema,
        };
        let route = McpRoute {
            qualified_name: qualified_name.clone(),
            server_name: tool.server_name.clone(),
        };

        // Last-wins, mirroring the runtime tool_index insert-overwrite
        // semantics (mcp_stdio.rs `tool_index`): when two tools normalize to
        // the same qualified_name, the manager's `call_tool` resolves to the
        // LAST inserted route, so the catalog survivor MUST equal the manager
        // survivor — otherwise the advertised description/schema/server_name
        // would describe a different tool than the one actually executed
        // (corrupting C2's per-server approval/trust). Both this catalog and
        // the manager consume the same `Vec<ManagedMcpTool>` order, so taking
        // the last on collision is naturally consistent with the manager.
        if let Some(&idx) = spec_index.get(&qualified_name) {
            eprintln!(
                "aris mcp: duplicate MCP tool `{qualified_name}` after normalization; \
                 replacing earlier (server `{}`) with later (server `{}`, tool `{}`) \
                 to match runtime last-writer-wins routing",
                routes[&qualified_name].server_name, tool.server_name, tool.raw_name
            );
            // Replace in place to keep advertised ordering deterministic.
            specs[idx] = spec;
            routes.insert(qualified_name, route);
        } else {
            spec_index.insert(qualified_name.clone(), specs.len());
            routes.insert(qualified_name, route);
            specs.push(spec);
        }
    }

    McpToolCatalog { specs, routes }
}

/// Minimal schema net (T2): MCP servers may return no `inputSchema` at all, or
/// a schema whose top level is not a JSON object. Providers require an object
/// schema for tool parameters, so anything that is not an object is replaced
/// with `{"type":"object"}` (a warning is emitted so the drift is visible).
fn sanitize_mcp_input_schema(schema: Option<&Value>, advertised_name: &str) -> Value {
    match schema {
        Some(value) if value.is_object() => value.clone(),
        Some(_) => {
            eprintln!(
                "aris mcp: tool `{advertised_name}` returned a non-object inputSchema; \
                 substituting a minimal object schema"
            );
            json!({ "type": "object" })
        }
        None => json!({ "type": "object" }),
    }
}

#[must_use]
#[allow(clippy::too_many_lines)]
pub fn mvp_tool_specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "bash",
            description: "Execute a shell command in the current workspace.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "command": { "type": "string" },
                    "timeout": { "type": "integer", "minimum": 1 },
                    "description": { "type": "string" },
                    "run_in_background": { "type": "boolean" },
                    "dangerouslyDisableSandbox": {
                        "type": "boolean",
                        "description": "Request that this single command bypass the sandbox. Honored only when the runtime config has `sandbox.strictMode != true`. When `sandbox.strictMode: true` is set by the user, this field is ignored and the runtime emits a warning. Default false."
                    }
                },
                "required": ["command"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::DangerFullAccess,
        },
        ToolSpec {
            name: "read_file",
            description: "Read a text file from the workspace.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "offset": { "type": "integer", "minimum": 0 },
                    "limit": { "type": "integer", "minimum": 1 }
                },
                "required": ["path"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "write_file",
            description: "Write a text file in the workspace.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "content": { "type": "string" }
                },
                "required": ["path", "content"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::WorkspaceWrite,
        },
        ToolSpec {
            name: "edit_file",
            description: "Replace text in a workspace file.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "old_string": { "type": "string" },
                    "new_string": { "type": "string" },
                    "replace_all": { "type": "boolean" }
                },
                "required": ["path", "old_string", "new_string"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::WorkspaceWrite,
        },
        ToolSpec {
            name: "glob_search",
            description: "Find files by glob pattern.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "pattern": { "type": "string" },
                    "path": { "type": "string" }
                },
                "required": ["pattern"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "grep_search",
            description: "Search file contents with a regex pattern.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "pattern": { "type": "string" },
                    "path": { "type": "string" },
                    "glob": { "type": "string" },
                    "output_mode": { "type": "string" },
                    "-B": { "type": "integer", "minimum": 0 },
                    "-A": { "type": "integer", "minimum": 0 },
                    "-C": { "type": "integer", "minimum": 0 },
                    "context": { "type": "integer", "minimum": 0 },
                    "-n": { "type": "boolean" },
                    "-i": { "type": "boolean" },
                    "type": { "type": "string" },
                    "head_limit": { "type": "integer", "minimum": 1 },
                    "offset": { "type": "integer", "minimum": 0 },
                    "multiline": { "type": "boolean" }
                },
                "required": ["pattern"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "WebFetch",
            description:
                "Fetch a URL, convert it into readable text, and answer a prompt about it.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": { "type": "string", "format": "uri" },
                    "prompt": { "type": "string" }
                },
                "required": ["url", "prompt"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "WebSearch",
            description: "Search the web for current information and return cited results.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": { "type": "string", "minLength": 2 },
                    "allowed_domains": {
                        "type": "array",
                        "items": { "type": "string" }
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": { "type": "string" }
                    }
                },
                "required": ["query"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "TodoWrite",
            description: "Update the structured task list for the current session.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": { "type": "string" },
                                "activeForm": { "type": "string" },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"]
                                }
                            },
                            "required": ["content", "activeForm", "status"],
                            "additionalProperties": false
                        }
                    }
                },
                "required": ["todos"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::WorkspaceWrite,
        },
        ToolSpec {
            name: "LlmReview",
            description: "Send content to an external LLM reviewer for independent critical review. Supports OpenAI, Gemini, GLM, MiniMax, Kimi, and Anthropic-compatible endpoints. Routes by model name. Prefer omitting `model` and letting ARIS use the user's configured reviewer. gpt-5.6-sol is allowed as an explicit value but experimental — not yet verified with reasoning_effort on chat-completions; use only when the user explicitly requests it.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The full content to review, including context and specific review instructions."
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional model override. Prefer omitting this — ARIS will use the user's configured reviewer (ARIS_REVIEWER_MODEL). Only specify a model if you have a specific reason and know the corresponding API key is set. Examples: gpt-5.5, gpt-5.6-sol (experimental — not yet verified with reasoning_effort on chat-completions; use only when the user explicitly requests it), gemini-2.5-pro, GLM-5, MiniMax-M2.7, kimi-k2.5, claude-sonnet-4-6. If the specified model's API key is missing, ARIS falls back to the configured reviewer."
                    }
                },
                "required": ["prompt"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "Skill",
            description: "Load a local skill definition and its instructions.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "skill": { "type": "string" },
                    "args": { "type": "string" }
                },
                "required": ["skill"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "Agent",
            description: "Launch a specialized agent task and persist its handoff metadata.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "description": { "type": "string" },
                    "prompt": { "type": "string" },
                    "subagent_type": { "type": "string" },
                    "name": { "type": "string" },
                    "model": { "type": "string" }
                },
                "required": ["description", "prompt"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::DangerFullAccess,
        },
        ToolSpec {
            name: "ToolSearch",
            description: "Search for deferred or specialized tools by exact name or keywords.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": { "type": "string" },
                    "max_results": { "type": "integer", "minimum": 1 }
                },
                "required": ["query"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "NotebookEdit",
            description: "Replace, insert, or delete a cell in a Jupyter notebook.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "notebook_path": { "type": "string" },
                    "cell_id": { "type": "string" },
                    "new_source": { "type": "string" },
                    "cell_type": { "type": "string", "enum": ["code", "markdown"] },
                    "edit_mode": { "type": "string", "enum": ["replace", "insert", "delete"] }
                },
                "required": ["notebook_path"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::WorkspaceWrite,
        },
        ToolSpec {
            name: "Sleep",
            description: "Wait for a specified duration without holding a shell process.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "duration_ms": { "type": "integer", "minimum": 0 }
                },
                "required": ["duration_ms"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "SendUserMessage",
            description: "Send a message to the user.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "message": { "type": "string" },
                    "attachments": {
                        "type": "array",
                        "items": { "type": "string" }
                    },
                    "status": {
                        "type": "string",
                        "enum": ["normal", "proactive"]
                    }
                },
                "required": ["message", "status"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "Config",
            description: "Get or set ARIS-Code settings.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "setting": { "type": "string" },
                    "value": {
                        "type": ["string", "boolean", "number"]
                    }
                },
                "required": ["setting"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::WorkspaceWrite,
        },
        ToolSpec {
            name: "StructuredOutput",
            description: "Return structured output in the requested format.",
            input_schema: json!({
                "type": "object",
                "properties": {},
                "additionalProperties": true
            }),
            required_permission: PermissionMode::ReadOnly,
        },
        ToolSpec {
            name: "REPL",
            description: "Execute code in a REPL-like subprocess.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "code": { "type": "string" },
                    "language": { "type": "string" },
                    "timeout_ms": { "type": "integer", "minimum": 1 }
                },
                "required": ["code", "language"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::DangerFullAccess,
        },
        ToolSpec {
            name: "PowerShell",
            description: "Execute a PowerShell command with optional timeout.",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "command": { "type": "string" },
                    "timeout": { "type": "integer", "minimum": 1 },
                    "description": { "type": "string" },
                    "run_in_background": { "type": "boolean" }
                },
                "required": ["command"],
                "additionalProperties": false
            }),
            required_permission: PermissionMode::DangerFullAccess,
        },
    ]
}

pub fn execute_tool(name: &str, input: &Value) -> Result<String, String> {
    match name {
        "bash" => from_value::<BashCommandInput>(input).and_then(run_bash),
        "read_file" => from_value::<ReadFileInput>(input).and_then(run_read_file),
        "write_file" => from_value::<WriteFileInput>(input).and_then(run_write_file),
        "edit_file" => from_value::<EditFileInput>(input).and_then(run_edit_file),
        "glob_search" => from_value::<GlobSearchInputValue>(input).and_then(run_glob_search),
        "grep_search" => from_value::<GrepSearchInput>(input).and_then(run_grep_search),
        "WebFetch" => from_value::<WebFetchInput>(input).and_then(run_web_fetch),
        "WebSearch" => from_value::<WebSearchInput>(input).and_then(run_web_search),
        "TodoWrite" => from_value::<TodoWriteInput>(input).and_then(run_todo_write),
        "LlmReview" => from_value::<LlmReviewInput>(input).and_then(run_llm_review),
        "Skill" => from_value::<SkillInput>(input).and_then(run_skill),
        "Agent" => from_value::<AgentInput>(input).and_then(run_agent),
        "ToolSearch" => from_value::<ToolSearchInput>(input).and_then(run_tool_search),
        "NotebookEdit" => from_value::<NotebookEditInput>(input).and_then(run_notebook_edit),
        "Sleep" => from_value::<SleepInput>(input).and_then(run_sleep),
        "SendUserMessage" | "Brief" => from_value::<BriefInput>(input).and_then(run_brief),
        "Config" => from_value::<ConfigInput>(input).and_then(run_config),
        "StructuredOutput" => {
            from_value::<StructuredOutputInput>(input).and_then(run_structured_output)
        }
        "REPL" => from_value::<ReplInput>(input).and_then(run_repl),
        "PowerShell" => from_value::<PowerShellInput>(input).and_then(run_powershell),
        _ => Err(format!("unsupported tool: {name}")),
    }
}

fn from_value<T: for<'de> Deserialize<'de>>(input: &Value) -> Result<T, String> {
    serde_json::from_value(input.clone()).map_err(|error| error.to_string())
}

fn run_bash(input: BashCommandInput) -> Result<String, String> {
    serde_json::to_string_pretty(&execute_bash(input).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())
}

#[allow(clippy::needless_pass_by_value)]
fn run_read_file(input: ReadFileInput) -> Result<String, String> {
    to_pretty_json(read_file(&input.path, input.offset, input.limit).map_err(io_to_string)?)
}

#[allow(clippy::needless_pass_by_value)]
fn run_write_file(input: WriteFileInput) -> Result<String, String> {
    to_pretty_json(write_file(&input.path, &input.content).map_err(io_to_string)?)
}

#[allow(clippy::needless_pass_by_value)]
fn run_edit_file(input: EditFileInput) -> Result<String, String> {
    to_pretty_json(
        edit_file(
            &input.path,
            &input.old_string,
            &input.new_string,
            input.replace_all.unwrap_or(false),
        )
        .map_err(io_to_string)?,
    )
}

#[allow(clippy::needless_pass_by_value)]
fn run_glob_search(input: GlobSearchInputValue) -> Result<String, String> {
    to_pretty_json(glob_search(&input.pattern, input.path.as_deref()).map_err(io_to_string)?)
}

#[allow(clippy::needless_pass_by_value)]
fn run_grep_search(input: GrepSearchInput) -> Result<String, String> {
    to_pretty_json(grep_search(&input).map_err(io_to_string)?)
}

#[allow(clippy::needless_pass_by_value)]
fn run_web_fetch(input: WebFetchInput) -> Result<String, String> {
    to_pretty_json(execute_web_fetch(&input)?)
}

#[allow(clippy::needless_pass_by_value)]
fn run_web_search(input: WebSearchInput) -> Result<String, String> {
    to_pretty_json(execute_web_search(&input)?)
}

fn run_todo_write(input: TodoWriteInput) -> Result<String, String> {
    to_pretty_json(execute_todo_write(input)?)
}

fn run_skill(input: SkillInput) -> Result<String, String> {
    to_pretty_json(execute_skill(input)?)
}

fn run_agent(input: AgentInput) -> Result<String, String> {
    to_pretty_json(execute_agent(input)?)
}

fn run_tool_search(input: ToolSearchInput) -> Result<String, String> {
    to_pretty_json(execute_tool_search(input))
}

fn run_notebook_edit(input: NotebookEditInput) -> Result<String, String> {
    to_pretty_json(execute_notebook_edit(input)?)
}

fn run_sleep(input: SleepInput) -> Result<String, String> {
    to_pretty_json(execute_sleep(input))
}

fn run_brief(input: BriefInput) -> Result<String, String> {
    to_pretty_json(execute_brief(input)?)
}

fn run_config(input: ConfigInput) -> Result<String, String> {
    to_pretty_json(execute_config(input)?)
}

fn run_structured_output(input: StructuredOutputInput) -> Result<String, String> {
    to_pretty_json(execute_structured_output(input))
}

fn run_repl(input: ReplInput) -> Result<String, String> {
    to_pretty_json(execute_repl(input)?)
}

fn run_powershell(input: PowerShellInput) -> Result<String, String> {
    to_pretty_json(execute_powershell(input).map_err(|error| error.to_string())?)
}

fn to_pretty_json<T: serde::Serialize>(value: T) -> Result<String, String> {
    serde_json::to_string_pretty(&value).map_err(|error| error.to_string())
}

#[allow(clippy::needless_pass_by_value)]
fn io_to_string(error: std::io::Error) -> String {
    error.to_string()
}

fn is_symlink(path: &std::path::Path) -> bool {
    std::fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink())
}

#[derive(Debug, Deserialize)]
struct ReadFileInput {
    path: String,
    offset: Option<usize>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct WriteFileInput {
    path: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct EditFileInput {
    path: String,
    old_string: String,
    new_string: String,
    replace_all: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct GlobSearchInputValue {
    pattern: String,
    path: Option<String>,
}

#[derive(Debug, Deserialize)]
struct WebFetchInput {
    url: String,
    prompt: String,
}

#[derive(Debug, Deserialize)]
struct WebSearchInput {
    query: String,
    allowed_domains: Option<Vec<String>>,
    blocked_domains: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct TodoWriteInput {
    todos: Vec<TodoItem>,
}

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq, Eq)]
struct TodoItem {
    content: String,
    #[serde(rename = "activeForm")]
    active_form: String,
    status: TodoStatus,
}

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum TodoStatus {
    Pending,
    InProgress,
    Completed,
}

#[derive(Debug, Deserialize)]
struct SkillInput {
    skill: String,
    args: Option<String>,
}

#[derive(Debug, Deserialize)]
struct AgentInput {
    description: String,
    prompt: String,
    subagent_type: Option<String>,
    name: Option<String>,
    model: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ToolSearchInput {
    query: String,
    max_results: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct NotebookEditInput {
    notebook_path: String,
    cell_id: Option<String>,
    new_source: Option<String>,
    cell_type: Option<NotebookCellType>,
    edit_mode: Option<NotebookEditMode>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum NotebookCellType {
    Code,
    Markdown,
}

#[derive(Debug, Deserialize, Serialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum NotebookEditMode {
    Replace,
    Insert,
    Delete,
}

#[derive(Debug, Deserialize)]
struct SleepInput {
    duration_ms: u64,
}

#[derive(Debug, Deserialize)]
struct BriefInput {
    message: String,
    attachments: Option<Vec<String>>,
    status: BriefStatus,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
enum BriefStatus {
    Normal,
    Proactive,
}

#[derive(Debug, Deserialize)]
struct ConfigInput {
    setting: String,
    value: Option<ConfigValue>,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum ConfigValue {
    String(String),
    Bool(bool),
    Number(f64),
}

#[derive(Debug, Deserialize)]
#[serde(transparent)]
struct StructuredOutputInput(BTreeMap<String, Value>);

#[derive(Debug, Deserialize)]
struct ReplInput {
    code: String,
    language: String,
    timeout_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct PowerShellInput {
    command: String,
    timeout: Option<u64>,
    description: Option<String>,
    run_in_background: Option<bool>,
}

#[derive(Debug, Serialize)]
struct WebFetchOutput {
    bytes: usize,
    code: u16,
    #[serde(rename = "codeText")]
    code_text: String,
    result: String,
    #[serde(rename = "durationMs")]
    duration_ms: u128,
    url: String,
}

#[derive(Debug, Serialize)]
struct WebSearchOutput {
    query: String,
    results: Vec<WebSearchResultItem>,
    #[serde(rename = "durationSeconds")]
    duration_seconds: f64,
}

#[derive(Debug, Serialize)]
struct TodoWriteOutput {
    #[serde(rename = "oldTodos")]
    old_todos: Vec<TodoItem>,
    #[serde(rename = "newTodos")]
    new_todos: Vec<TodoItem>,
    #[serde(rename = "verificationNudgeNeeded")]
    verification_nudge_needed: Option<bool>,
}

#[derive(Debug, Serialize)]
struct SkillOutput {
    skill: String,
    path: String,
    args: Option<String>,
    description: Option<String>,
    prompt: String,

    /// v0.4.8: per-skill slice of `runtime::ExtractionReport`. `None` for
    /// filesystem skills (no bundled helpers) or when startup eager-extract
    /// was bypassed (test code).
    #[serde(rename = "helperReport", skip_serializing_if = "Option::is_none")]
    helper_report: Option<SkillHelperReport>,
}

#[derive(Debug, Serialize)]
struct SkillHelperReport {
    /// Absolute path to the cache root (set as `$ARIS_CACHE_DIR` at startup).
    /// `None` iff `runtime::ExtractionReport.hard_error` — helpers unavailable.
    #[serde(rename = "cacheDir", skip_serializing_if = "Option::is_none")]
    cache_dir: Option<String>,

    /// True iff `cache_dir.is_some() && failed_helpers.is_empty()`.
    /// False under partial failure even if `cache_dir` is set.
    #[serde(rename = "cacheUsable")]
    cache_usable: bool,

    /// Helpers visible to this skill (shared `tools/*` + skill-local +
    /// always-extracted `shared-references/*`). Absolute paths.
    #[serde(rename = "availableHelpers")]
    available_helpers: Vec<HelperEntry>,

    /// Helpers from BUNDLED_RESOURCES that failed to extract.
    /// v0.4.8 scope: extraction-failure slice. NOT "SKILL.md references that
    /// aren't bundled" — that static inference is deferred to v0.5.0.
    #[serde(rename = "failedHelpers")]
    failed_helpers: Vec<HelperEntry>,
}

#[derive(Debug, Serialize)]
struct HelperEntry {
    /// Bundle key (e.g., "tools/arxiv_fetch.py", "skills/research-wiki/research_wiki.py").
    key: String,
    /// Absolute path where the helper lives, or where it would have lived if missing.
    path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AgentOutput {
    #[serde(rename = "agentId")]
    agent_id: String,
    name: String,
    description: String,
    #[serde(rename = "subagentType")]
    subagent_type: Option<String>,
    model: Option<String>,
    status: String,
    #[serde(rename = "outputFile")]
    output_file: String,
    #[serde(rename = "manifestFile")]
    manifest_file: String,
    #[serde(rename = "createdAt")]
    created_at: String,
    #[serde(rename = "startedAt", skip_serializing_if = "Option::is_none")]
    started_at: Option<String>,
    #[serde(rename = "completedAt", skip_serializing_if = "Option::is_none")]
    completed_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Debug, Clone)]
struct AgentJob {
    manifest: AgentOutput,
    prompt: String,
    system_prompt: Vec<String>,
    allowed_tools: BTreeSet<String>,
}

#[derive(Debug, Serialize)]
struct ToolSearchOutput {
    matches: Vec<String>,
    query: String,
    normalized_query: String,
    #[serde(rename = "total_deferred_tools")]
    total_deferred_tools: usize,
    #[serde(rename = "pending_mcp_servers")]
    pending_mcp_servers: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
struct NotebookEditOutput {
    new_source: String,
    cell_id: Option<String>,
    cell_type: Option<NotebookCellType>,
    language: String,
    edit_mode: String,
    error: Option<String>,
    notebook_path: String,
    original_file: String,
    updated_file: String,
}

#[derive(Debug, Serialize)]
struct SleepOutput {
    duration_ms: u64,
    message: String,
}

#[derive(Debug, Serialize)]
struct BriefOutput {
    message: String,
    attachments: Option<Vec<ResolvedAttachment>>,
    #[serde(rename = "sentAt")]
    sent_at: String,
}

#[derive(Debug, Serialize)]
struct ResolvedAttachment {
    path: String,
    size: u64,
    #[serde(rename = "isImage")]
    is_image: bool,
}

#[derive(Debug, Serialize)]
struct ConfigOutput {
    success: bool,
    operation: Option<String>,
    setting: Option<String>,
    value: Option<Value>,
    #[serde(rename = "previousValue")]
    previous_value: Option<Value>,
    #[serde(rename = "newValue")]
    new_value: Option<Value>,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct StructuredOutputResult {
    data: String,
    structured_output: BTreeMap<String, Value>,
}

#[derive(Debug, Serialize)]
struct ReplOutput {
    language: String,
    stdout: String,
    stderr: String,
    #[serde(rename = "exitCode")]
    exit_code: i32,
    #[serde(rename = "durationMs")]
    duration_ms: u128,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
enum WebSearchResultItem {
    SearchResult {
        tool_use_id: String,
        content: Vec<SearchHit>,
    },
    Commentary(String),
}

#[derive(Debug, Serialize)]
struct SearchHit {
    title: String,
    url: String,
}

fn execute_web_fetch(input: &WebFetchInput) -> Result<WebFetchOutput, String> {
    let started = Instant::now();
    let client = build_http_client()?;
    let request_url = normalize_fetch_url(&input.url)?;
    let response = client
        .get(request_url.clone())
        .send()
        .map_err(|error| error.to_string())?;

    let status = response.status();
    let final_url = response.url().to_string();
    let code = status.as_u16();
    let code_text = status.canonical_reason().unwrap_or("Unknown").to_string();
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_string();
    let body = response.text().map_err(|error| error.to_string())?;
    let bytes = body.len();
    let normalized = normalize_fetched_content(&body, &content_type);
    let result = summarize_web_fetch(&final_url, &input.prompt, &normalized, &body, &content_type);

    Ok(WebFetchOutput {
        bytes,
        code,
        code_text,
        result,
        duration_ms: started.elapsed().as_millis(),
        url: final_url,
    })
}

fn execute_web_search(input: &WebSearchInput) -> Result<WebSearchOutput, String> {
    let started = Instant::now();
    let client = build_http_client()?;
    let search_url = build_search_url(&input.query)?;
    let response = client
        .get(search_url)
        .send()
        .map_err(|error| error.to_string())?;

    let final_url = response.url().clone();
    let html = response.text().map_err(|error| error.to_string())?;
    let mut hits = extract_search_hits(&html);

    if hits.is_empty() && final_url.host_str().is_some() {
        hits = extract_search_hits_from_generic_links(&html);
    }

    if let Some(allowed) = input.allowed_domains.as_ref() {
        hits.retain(|hit| host_matches_list(&hit.url, allowed));
    }
    if let Some(blocked) = input.blocked_domains.as_ref() {
        hits.retain(|hit| !host_matches_list(&hit.url, blocked));
    }

    dedupe_hits(&mut hits);
    hits.truncate(8);

    let summary = if hits.is_empty() {
        format!("No web search results matched the query {:?}.", input.query)
    } else {
        let rendered_hits = hits
            .iter()
            .map(|hit| format!("- [{}]({})", hit.title, hit.url))
            .collect::<Vec<_>>()
            .join("\n");
        format!(
            "Search results for {:?}. Include a Sources section in the final answer.\n{}",
            input.query, rendered_hits
        )
    };

    Ok(WebSearchOutput {
        query: input.query.clone(),
        results: vec![
            WebSearchResultItem::Commentary(summary),
            WebSearchResultItem::SearchResult {
                tool_use_id: String::from("web_search_1"),
                content: hits,
            },
        ],
        duration_seconds: started.elapsed().as_secs_f64(),
    })
}

fn build_http_client() -> Result<Client, String> {
    Client::builder()
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::limited(10))
        .user_agent("clawd-rust-tools/0.1")
        .build()
        .map_err(|error| error.to_string())
}

fn normalize_fetch_url(url: &str) -> Result<String, String> {
    let parsed = reqwest::Url::parse(url).map_err(|error| error.to_string())?;
    if parsed.scheme() == "http" {
        let host = parsed.host_str().unwrap_or_default();
        if host != "localhost" && host != "127.0.0.1" && host != "::1" {
            let mut upgraded = parsed;
            upgraded
                .set_scheme("https")
                .map_err(|()| String::from("failed to upgrade URL to https"))?;
            return Ok(upgraded.to_string());
        }
    }
    Ok(parsed.to_string())
}

fn build_search_url(query: &str) -> Result<reqwest::Url, String> {
    if let Ok(base) = std::env::var("CLAWD_WEB_SEARCH_BASE_URL") {
        let mut url = reqwest::Url::parse(&base).map_err(|error| error.to_string())?;
        url.query_pairs_mut().append_pair("q", query);
        return Ok(url);
    }

    let mut url = reqwest::Url::parse("https://html.duckduckgo.com/html/")
        .map_err(|error| error.to_string())?;
    url.query_pairs_mut().append_pair("q", query);
    Ok(url)
}

fn normalize_fetched_content(body: &str, content_type: &str) -> String {
    if content_type.contains("html") {
        html_to_text(body)
    } else {
        body.trim().to_string()
    }
}

fn summarize_web_fetch(
    url: &str,
    prompt: &str,
    content: &str,
    raw_body: &str,
    content_type: &str,
) -> String {
    let lower_prompt = prompt.to_lowercase();
    let compact = collapse_whitespace(content);

    let detail = if lower_prompt.contains("title") {
        extract_title(content, raw_body, content_type).map_or_else(
            || preview_text(&compact, 600),
            |title| format!("Title: {title}"),
        )
    } else if lower_prompt.contains("summary") || lower_prompt.contains("summarize") {
        preview_text(&compact, 900)
    } else {
        let preview = preview_text(&compact, 900);
        format!("Prompt: {prompt}\nContent preview:\n{preview}")
    };

    format!("Fetched {url}\n{detail}")
}

fn extract_title(content: &str, raw_body: &str, content_type: &str) -> Option<String> {
    if content_type.contains("html") {
        let lowered = raw_body.to_lowercase();
        if let Some(start) = lowered.find("<title>") {
            let after = start + "<title>".len();
            if let Some(end_rel) = lowered[after..].find("</title>") {
                let title =
                    collapse_whitespace(&decode_html_entities(&raw_body[after..after + end_rel]));
                if !title.is_empty() {
                    return Some(title);
                }
            }
        }
    }

    for line in content.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }
    None
}

fn html_to_text(html: &str) -> String {
    let mut text = String::with_capacity(html.len());
    let mut in_tag = false;
    let mut previous_was_space = false;

    for ch in html.chars() {
        match ch {
            '<' => in_tag = true,
            '>' => in_tag = false,
            _ if in_tag => {}
            '&' => {
                text.push('&');
                previous_was_space = false;
            }
            ch if ch.is_whitespace() => {
                if !previous_was_space {
                    text.push(' ');
                    previous_was_space = true;
                }
            }
            _ => {
                text.push(ch);
                previous_was_space = false;
            }
        }
    }

    collapse_whitespace(&decode_html_entities(&text))
}

fn decode_html_entities(input: &str) -> String {
    input
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
}

fn collapse_whitespace(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn preview_text(input: &str, max_chars: usize) -> String {
    if input.chars().count() <= max_chars {
        return input.to_string();
    }
    let shortened = input.chars().take(max_chars).collect::<String>();
    format!("{}…", shortened.trim_end())
}

fn extract_search_hits(html: &str) -> Vec<SearchHit> {
    let mut hits = Vec::new();
    let mut remaining = html;

    while let Some(anchor_start) = remaining.find("result__a") {
        let after_class = &remaining[anchor_start..];
        let Some(href_idx) = after_class.find("href=") else {
            remaining = &after_class[1..];
            continue;
        };
        let href_slice = &after_class[href_idx + 5..];
        let Some((url, rest)) = extract_quoted_value(href_slice) else {
            remaining = &after_class[1..];
            continue;
        };
        let Some(close_tag_idx) = rest.find('>') else {
            remaining = &after_class[1..];
            continue;
        };
        let after_tag = &rest[close_tag_idx + 1..];
        let Some(end_anchor_idx) = after_tag.find("</a>") else {
            remaining = &after_tag[1..];
            continue;
        };
        let title = html_to_text(&after_tag[..end_anchor_idx]);
        if let Some(decoded_url) = decode_duckduckgo_redirect(&url) {
            hits.push(SearchHit {
                title: title.trim().to_string(),
                url: decoded_url,
            });
        }
        remaining = &after_tag[end_anchor_idx + 4..];
    }

    hits
}

fn extract_search_hits_from_generic_links(html: &str) -> Vec<SearchHit> {
    let mut hits = Vec::new();
    let mut remaining = html;

    while let Some(anchor_start) = remaining.find("<a") {
        let after_anchor = &remaining[anchor_start..];
        let Some(href_idx) = after_anchor.find("href=") else {
            remaining = &after_anchor[2..];
            continue;
        };
        let href_slice = &after_anchor[href_idx + 5..];
        let Some((url, rest)) = extract_quoted_value(href_slice) else {
            remaining = &after_anchor[2..];
            continue;
        };
        let Some(close_tag_idx) = rest.find('>') else {
            remaining = &after_anchor[2..];
            continue;
        };
        let after_tag = &rest[close_tag_idx + 1..];
        let Some(end_anchor_idx) = after_tag.find("</a>") else {
            remaining = &after_anchor[2..];
            continue;
        };
        let title = html_to_text(&after_tag[..end_anchor_idx]);
        if title.trim().is_empty() {
            remaining = &after_tag[end_anchor_idx + 4..];
            continue;
        }
        let decoded_url = decode_duckduckgo_redirect(&url).unwrap_or(url);
        if decoded_url.starts_with("http://") || decoded_url.starts_with("https://") {
            hits.push(SearchHit {
                title: title.trim().to_string(),
                url: decoded_url,
            });
        }
        remaining = &after_tag[end_anchor_idx + 4..];
    }

    hits
}

fn extract_quoted_value(input: &str) -> Option<(String, &str)> {
    let quote = input.chars().next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }
    let rest = &input[quote.len_utf8()..];
    let end = rest.find(quote)?;
    Some((rest[..end].to_string(), &rest[end + quote.len_utf8()..]))
}

fn decode_duckduckgo_redirect(url: &str) -> Option<String> {
    if url.starts_with("http://") || url.starts_with("https://") {
        return Some(html_entity_decode_url(url));
    }

    let joined = if url.starts_with("//") {
        format!("https:{url}")
    } else if url.starts_with('/') {
        format!("https://duckduckgo.com{url}")
    } else {
        return None;
    };

    let parsed = reqwest::Url::parse(&joined).ok()?;
    if parsed.path() == "/l/" || parsed.path() == "/l" {
        for (key, value) in parsed.query_pairs() {
            if key == "uddg" {
                return Some(html_entity_decode_url(value.as_ref()));
            }
        }
    }
    Some(joined)
}

fn html_entity_decode_url(url: &str) -> String {
    decode_html_entities(url)
}

fn host_matches_list(url: &str, domains: &[String]) -> bool {
    let Ok(parsed) = reqwest::Url::parse(url) else {
        return false;
    };
    let Some(host) = parsed.host_str() else {
        return false;
    };
    let host = host.to_ascii_lowercase();
    domains.iter().any(|domain| {
        let normalized = normalize_domain_filter(domain);
        !normalized.is_empty() && (host == normalized || host.ends_with(&format!(".{normalized}")))
    })
}

fn normalize_domain_filter(domain: &str) -> String {
    let trimmed = domain.trim();
    let candidate = reqwest::Url::parse(trimmed)
        .ok()
        .and_then(|url| url.host_str().map(str::to_string))
        .unwrap_or_else(|| trimmed.to_string());
    candidate
        .trim()
        .trim_start_matches('.')
        .trim_end_matches('/')
        .to_ascii_lowercase()
}

fn dedupe_hits(hits: &mut Vec<SearchHit>) {
    let mut seen = BTreeSet::new();
    hits.retain(|hit| seen.insert(hit.url.clone()));
}

fn execute_todo_write(input: TodoWriteInput) -> Result<TodoWriteOutput, String> {
    validate_todos(&input.todos)?;
    let store_path = todo_store_path()?;
    let old_todos = if store_path.exists() {
        serde_json::from_str::<Vec<TodoItem>>(
            &std::fs::read_to_string(&store_path).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?
    } else {
        Vec::new()
    };

    let all_done = input
        .todos
        .iter()
        .all(|todo| matches!(todo.status, TodoStatus::Completed));
    let persisted = if all_done {
        Vec::new()
    } else {
        input.todos.clone()
    };

    if let Some(parent) = store_path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    std::fs::write(
        &store_path,
        serde_json::to_string_pretty(&persisted).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;

    let verification_nudge_needed = (all_done
        && input.todos.len() >= 3
        && !input
            .todos
            .iter()
            .any(|todo| todo.content.to_lowercase().contains("verif")))
    .then_some(true);

    Ok(TodoWriteOutput {
        old_todos,
        new_todos: input.todos,
        verification_nudge_needed,
    })
}

fn execute_skill(input: SkillInput) -> Result<SkillOutput, String> {
    let requested = input.skill.trim().trim_start_matches('/').trim_start_matches('$');

    // Try filesystem search roots first (user overrides take priority)
    if let Ok(skill_path) = resolve_skill_path(requested) {
        let raw_prompt = std::fs::read_to_string(&skill_path).map_err(|e| e.to_string())?;
        let description = parse_skill_description(&raw_prompt);
        let helper_report = build_helper_report(requested);
        // Active filesystem skill dir = parent of SKILL.md. Used by the
        // resolver chain's Layer 1 (`<active_skill_dir>/tools/<helper>`).
        let active_skill_dir = skill_path
            .parent()
            .map(|p| forward_slash(&p.display().to_string()));
        let prompt = inject_resolver_preamble(
            &raw_prompt,
            helper_report.as_ref(),
            active_skill_dir.as_deref(),
        );
        return Ok(SkillOutput {
            skill: input.skill,
            path: skill_path.display().to_string(),
            args: input.args,
            description,
            prompt,
            helper_report,
        });
    }

    // Fallback: bundled skills compiled into the binary.
    // No per-skill extraction here — startup eager extract (runtime::extract_bundle)
    // already materialised every BUNDLED_RESOURCES entry into the cache. We just
    // surface a per-skill slice of the report so the model knows where helpers live.
    for (name, content) in BUNDLED_SKILLS {
        if name.eq_ignore_ascii_case(requested) {
            let description = parse_skill_description(content);
            let helper_report = build_helper_report(name);
            // Bundled skills have no on-disk skill dir; Layer 1 doesn't apply.
            let prompt = inject_resolver_preamble(content, helper_report.as_ref(), None);
            return Ok(SkillOutput {
                skill: input.skill,
                path: format!("<bundled:{name}>"),
                args: input.args,
                description,
                prompt,
                helper_report,
            });
        }
    }

    Err(format!("unknown skill: {requested}"))
}

/// Normalise a path string to forward slashes. The cache and active-skill paths
/// flow into SKILL.md prompts and from there into the model's `bash` tool
/// invocations. POSIX-shell + git-bash + WSL all tolerate `/` even on Windows;
/// raw backslashes from `Path::display()` confuse the shell escaping.
fn forward_slash(p: &str) -> String {
    p.replace('\\', "/")
}

/// Build the per-skill slice of the process-global `ExtractionReport`.
///
/// Helpers in scope: shared (`tools/*`), always-extracted refs
/// (`shared-references/*`), and skill-local (`skills/<skill_name>/*`).
fn build_helper_report(skill_name: &str) -> Option<SkillHelperReport> {
    let report = runtime::extraction_report()?;

    let cache_dir = report
        .used_dir
        .as_ref()
        .map(|p| forward_slash(&p.display().to_string()));

    let skill_prefix = format!("skills/{skill_name}/");
    let in_scope = |key: &str| -> bool {
        key.starts_with("tools/")
            || key.starts_with("shared-references/")
            || key.starts_with(&skill_prefix)
    };

    let make_path = |key: &str| -> String {
        report
            .used_dir
            .as_ref()
            .map(|d| forward_slash(&d.join(key).display().to_string()))
            .unwrap_or_default()
    };

    let available_helpers: Vec<HelperEntry> = report
        .extracted
        .iter()
        .filter(|k| in_scope(k))
        .map(|k| HelperEntry {
            key: k.clone(),
            path: make_path(k),
            error: None,
        })
        .collect();

    let failed_helpers: Vec<HelperEntry> = report
        .failed
        .iter()
        .filter(|e| in_scope(&e.key))
        .map(|e| HelperEntry {
            key: e.key.clone(),
            path: make_path(&e.key),
            error: Some(e.error.clone()),
        })
        .collect();

    let cache_usable = cache_dir.is_some() && failed_helpers.is_empty();

    Some(SkillHelperReport {
        cache_dir,
        cache_usable,
        available_helpers,
        failed_helpers,
    })
}

/// Prepend a hard resolver preamble to the SKILL.md prompt so the model knows
/// how to resolve helper paths. This is the bridge while SKILL.md bodies (T15)
/// still use legacy `tools/<helper>` hardcoded paths.
///
/// `active_skill_dir` should be `Some(dirname(skill_md))` for filesystem skills,
/// `None` for bundled skills (Layer 1 omitted).
fn inject_resolver_preamble(
    prompt: &str,
    report: Option<&SkillHelperReport>,
    active_skill_dir: Option<&str>,
) -> String {
    let Some(report) = report else {
        return prompt.to_string();
    };
    let Some(cache_dir) = &report.cache_dir else {
        // No usable cache — preamble omitted; SKILL.md must rely on
        // project-workspace fallback at layer 4.
        return prompt.to_string();
    };

    let mut preamble = String::with_capacity(1024 + prompt.len());
    preamble.push_str("# Helper resolution (ARIS-Code v0.4.8+)\n\n");
    preamble.push_str("When invoking a bundled helper script, resolve its path via this fallback chain (in order, first hit wins):\n\n");
    let mut layer = 1u32;
    if let Some(dir) = active_skill_dir {
        preamble.push_str(&format!(
            "{layer}. `{dir}/tools/<helper>` (active filesystem skill dir, where this SKILL.md lives)\n"
        ));
        layer += 1;
    }
    preamble.push_str(&format!(
        "{layer}. `~/.config/aris/<bundle-key>` (user-customised location; e.g. `~/.config/aris/tools/foo.py` for shared helpers, `~/.config/aris/skills/<name>/<rel>` for skill-local)\n"
    ));
    layer += 1;
    preamble.push_str(&format!(
        "{layer}. `{cache_dir}/<bundle-key>` (bundled fallback for this binary; also accessible as `$ARIS_CACHE_DIR/<bundle-key>`)\n"
    ));
    layer += 1;
    preamble.push_str(&format!(
        "{layer}. `<project_root>/tools/<helper>` (legacy compat with main-branch ARIS layouts)\n\n"
    ));

    if report.available_helpers.is_empty() {
        preamble.push_str("No bundled helpers extracted for this skill.\n");
    } else {
        preamble.push_str("Bundled helpers available for this skill (cache layer):\n");
        for entry in &report.available_helpers {
            preamble.push_str(&format!("- `{}` → `{}`\n", entry.key, entry.path));
        }
    }
    if !report.failed_helpers.is_empty() {
        preamble.push_str("\nWarning: the following bundled helpers failed to extract and may be unavailable:\n");
        for entry in &report.failed_helpers {
            preamble.push_str(&format!(
                "- `{}` — {}\n",
                entry.key,
                entry.error.as_deref().unwrap_or("unknown error")
            ));
        }
    }
    preamble.push_str("\n---\n\n");
    preamble.push_str(prompt);
    preamble
}

fn validate_todos(todos: &[TodoItem]) -> Result<(), String> {
    if todos.is_empty() {
        return Err(String::from("todos must not be empty"));
    }
    // Allow multiple in_progress items for parallel workflows
    if todos.iter().any(|todo| todo.content.trim().is_empty()) {
        return Err(String::from("todo content must not be empty"));
    }
    if todos.iter().any(|todo| todo.active_form.trim().is_empty()) {
        return Err(String::from("todo activeForm must not be empty"));
    }
    Ok(())
}

fn todo_store_path() -> Result<std::path::PathBuf, String> {
    if let Ok(path) = std::env::var("CLAWD_TODO_STORE") {
        return Ok(std::path::PathBuf::from(path));
    }
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    Ok(cwd.join(".clawd-todos.json"))
}

fn skill_search_roots() -> Vec<std::path::PathBuf> {
    let mut roots = Vec::new();

    // 1. ~/.config/aris/skills/ (ARIS user-level, highest priority)
    let home = runtime::home_dir();
    roots.push(std::path::PathBuf::from(&home).join(".config").join("aris").join("skills"));

    // 2. ~/.claude/skills/ (Claude Code compat, user-level)
    roots.push(std::path::PathBuf::from(&home).join(".claude").join("skills"));

    // 3. Project-level .claude/skills/
    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd.join(".claude").join("skills"));
    }

    // 3. CODEX_HOME/skills (legacy compat)
    if let Ok(codex_home) = std::env::var("CODEX_HOME") {
        roots.push(std::path::PathBuf::from(codex_home).join("skills"));
    }

    // 4. ARIS bundled share/skills/ (next to binary)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(bin_dir) = exe.parent() {
            let share_skills = bin_dir.parent()
                .map(|p| p.join("share").join("aris").join("skills"))
                .unwrap_or_else(|| bin_dir.join("share").join("aris").join("skills"));
            roots.push(share_skills);
        }
    }

    roots
}

fn resolve_skill_path(skill: &str) -> Result<std::path::PathBuf, String> {
    let requested = skill.trim().trim_start_matches('/').trim_start_matches('$');
    if requested.is_empty() {
        return Err(String::from("skill must not be empty"));
    }
    // Reject path traversal attempts
    if requested.contains("..") || requested.contains('/') || requested.contains('\\') {
        return Err(format!("invalid skill name: {requested}"));
    }

    for root in skill_search_roots() {
        // Direct match: root/<skill>/SKILL.md
        let direct = root.join(requested).join("SKILL.md");
        if direct.exists() && !is_symlink(&direct) {
            return Ok(direct);
        }

        // Case-insensitive scan
        if let Ok(entries) = std::fs::read_dir(&root) {
            for entry in entries.flatten() {
                // Reject symlinks to prevent directory traversal
                if is_symlink(&entry.path()) {
                    continue;
                }
                let path = entry.path().join("SKILL.md");
                if !path.exists() || is_symlink(&path) {
                    continue;
                }
                if entry
                    .file_name()
                    .to_string_lossy()
                    .eq_ignore_ascii_case(requested)
                {
                    return Ok(path);
                }
            }
        }
    }

    Err(format!("unknown skill: {requested}"))
}

/// A discovered skill with parsed frontmatter metadata.
#[derive(Debug, Clone, Serialize)]
pub struct SkillMeta {
    pub name: String,
    pub description: Option<String>,
    pub argument_hint: Option<String>,
    pub allowed_tools: Option<String>,
    pub path: std::path::PathBuf,
}

/// Discover all available skills from all search roots.
pub fn discover_skills() -> Vec<SkillMeta> {
    let mut seen = std::collections::HashSet::new();
    let mut skills = Vec::new();

    for root in skill_search_roots() {
        let entries = match std::fs::read_dir(&root) {
            Ok(e) => e,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            // Reject symlinks to prevent directory traversal
            if is_symlink(&entry.path()) {
                continue;
            }
            let skill_md = entry.path().join("SKILL.md");
            if !skill_md.exists() || is_symlink(&skill_md) {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_string();
            // First-found wins (user > project > codex > bundled)
            if seen.contains(&name) {
                continue;
            }
            seen.insert(name.clone());

            let content = std::fs::read_to_string(&skill_md).unwrap_or_default();
            let meta = parse_skill_frontmatter(&name, &content, skill_md);
            skills.push(meta);
        }
    }

    // Bundled skills as final fallback (user overrides already took priority above)
    for (name, content) in BUNDLED_SKILLS {
        if seen.contains(*name) {
            continue;
        }
        seen.insert(name.to_string());
        let meta = parse_skill_frontmatter(name, content, std::path::PathBuf::from(format!("<bundled:{name}>")));
        skills.push(meta);
    }

    skills.sort_by(|a, b| a.name.cmp(&b.name));
    skills
}

/// Parse YAML frontmatter from a SKILL.md file.
/// Expects `---` delimited YAML block at the top with fields like
/// name, description, argument-hint, allowed-tools.
fn parse_skill_frontmatter(
    dir_name: &str,
    content: &str,
    path: std::path::PathBuf,
) -> SkillMeta {
    let mut name = dir_name.to_string();
    let mut description = None;
    let mut argument_hint = None;
    let mut allowed_tools = None;

    // Check if content starts with YAML frontmatter
    let trimmed = content.trim_start();
    if trimmed.starts_with("---") {
        if let Some(end) = trimmed[3..].find("---") {
            let yaml_block = &trimmed[3..3 + end];
            for line in yaml_block.lines() {
                let line = line.trim();
                if let Some(val) = line.strip_prefix("name:") {
                    let val = val.trim().trim_matches('"').trim_matches('\'');
                    if !val.is_empty() {
                        name = val.to_string();
                    }
                } else if let Some(val) = line.strip_prefix("description:") {
                    let val = val.trim().trim_matches('"').trim_matches('\'');
                    if !val.is_empty() {
                        description = Some(val.to_string());
                    }
                } else if let Some(val) = line.strip_prefix("argument-hint:") {
                    let val = val.trim().trim_matches('"').trim_matches('\'');
                    if !val.is_empty() {
                        argument_hint = Some(val.to_string());
                    }
                } else if let Some(val) = line.strip_prefix("allowed-tools:") {
                    let val = val.trim().trim_matches('"').trim_matches('\'');
                    if !val.is_empty() {
                        allowed_tools = Some(val.to_string());
                    }
                }
            }
        }
    }

    // Fallback: try old-style description: line anywhere in content
    if description.is_none() {
        description = parse_skill_description(content);
    }

    SkillMeta {
        name,
        description,
        argument_hint,
        allowed_tools,
        path,
    }
}

/// Render a system prompt section listing all available skills.
pub fn render_skill_discovery_section() -> Option<String> {
    let skills = discover_skills();
    if skills.is_empty() {
        return None;
    }

    let mut lines = vec![
        "# Available skills".to_string(),
        String::new(),
        "The following skills are available via the Skill tool. Invoke with `/skill-name` or via the Skill tool.".to_string(),
        String::new(),
    ];

    for skill in &skills {
        let desc = skill.description.as_deref().unwrap_or("No description");
        // Truncate description to 200 chars (char-safe for CJK)
        let desc_short: String = desc.chars().take(200).collect();
        let hint = skill.argument_hint.as_deref().map_or(String::new(), |h| format!(" {h}"));
        lines.push(format!("- `/{}{hint}` — {}", skill.name, desc_short));
    }

    Some(lines.join("\n"))
}

const DEFAULT_AGENT_MODEL: &str = "claude-opus-4-8";
/// v0.4.18: subagent fallback when `DEFAULT_AGENT_MODEL` is unavailable on the
/// account (404 `not_found`). Mirrors the main session's `DEFAULT_MODEL_FALLBACK`
/// so a user without Opus 4.8 access doesn't hit hard subagent failures.
const DEFAULT_AGENT_MODEL_FALLBACK: &str = "claude-opus-4-7";
const DEFAULT_AGENT_MAX_ITERATIONS: usize = 32;

/// Subagent system date — use the same dynamic today as the main runtime
/// (`runtime::today_iso`) so subagents don't get a frozen `"2026-03-31"`
/// in their system prompt. Helper fn rather than a const so it stays live.
fn default_agent_system_date() -> String {
    runtime::today_iso()
}

fn execute_agent(input: AgentInput) -> Result<AgentOutput, String> {
    execute_agent_with_spawn(input, spawn_agent_job)
}

fn execute_agent_with_spawn<F>(input: AgentInput, spawn_fn: F) -> Result<AgentOutput, String>
where
    F: FnOnce(AgentJob) -> Result<(), String>,
{
    if input.description.trim().is_empty() {
        return Err(String::from("description must not be empty"));
    }
    if input.prompt.trim().is_empty() {
        return Err(String::from("prompt must not be empty"));
    }

    let agent_id = make_agent_id();
    let output_dir = agent_store_dir()?;
    std::fs::create_dir_all(&output_dir).map_err(|error| error.to_string())?;
    let output_file = output_dir.join(format!("{agent_id}.md"));
    let manifest_file = output_dir.join(format!("{agent_id}.json"));
    let normalized_subagent_type = normalize_subagent_type(input.subagent_type.as_deref());
    let model = resolve_agent_model(input.model.as_deref());
    let agent_name = input
        .name
        .as_deref()
        .map(slugify_agent_name)
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| slugify_agent_name(&input.description));
    let created_at = iso8601_now();
    let system_prompt = build_agent_system_prompt(&normalized_subagent_type)?;
    let allowed_tools = allowed_tools_for_subagent(&normalized_subagent_type);

    let output_contents = format!(
        "# Agent Task

- id: {}
- name: {}
- description: {}
- subagent_type: {}
- created_at: {}

## Prompt

{}
",
        agent_id, agent_name, input.description, normalized_subagent_type, created_at, input.prompt
    );
    std::fs::write(&output_file, output_contents).map_err(|error| error.to_string())?;

    let manifest = AgentOutput {
        agent_id,
        name: agent_name,
        description: input.description,
        subagent_type: Some(normalized_subagent_type),
        model: Some(model),
        status: String::from("running"),
        output_file: output_file.display().to_string(),
        manifest_file: manifest_file.display().to_string(),
        created_at: created_at.clone(),
        started_at: Some(created_at),
        completed_at: None,
        error: None,
    };
    write_agent_manifest(&manifest)?;

    let manifest_for_spawn = manifest.clone();
    let job = AgentJob {
        manifest: manifest_for_spawn,
        prompt: input.prompt,
        system_prompt,
        allowed_tools,
    };
    if let Err(error) = spawn_fn(job) {
        let error = format!("failed to spawn sub-agent: {error}");
        persist_agent_terminal_state(&manifest, "failed", None, Some(error.clone()))?;
        return Err(error);
    }

    Ok(manifest)
}

fn spawn_agent_job(job: AgentJob) -> Result<(), String> {
    let thread_name = format!("clawd-agent-{}", job.manifest.agent_id);
    std::thread::Builder::new()
        .name(thread_name)
        .spawn(move || {
            let result =
                std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| run_agent_job(&job)));
            match result {
                Ok(Ok(())) => {}
                Ok(Err(error)) => {
                    let _ =
                        persist_agent_terminal_state(&job.manifest, "failed", None, Some(error));
                }
                Err(_) => {
                    let _ = persist_agent_terminal_state(
                        &job.manifest,
                        "failed",
                        None,
                        Some(String::from("sub-agent thread panicked")),
                    );
                }
            }
        })
        .map(|_| ())
        .map_err(|error| error.to_string())
}

fn run_agent_job(job: &AgentJob) -> Result<(), String> {
    let mut runtime = build_agent_runtime(job)?.with_max_iterations(DEFAULT_AGENT_MAX_ITERATIONS);
    let summary = runtime
        .run_turn(job.prompt.clone(), None)
        .map_err(|error| error.to_string())?;
    let final_text = final_assistant_text(&summary);
    persist_agent_terminal_state(&job.manifest, "completed", Some(final_text.as_str()), None)
}

fn build_agent_runtime(
    job: &AgentJob,
) -> Result<ConversationRuntime<AnthropicRuntimeClient, SubagentToolExecutor>, String> {
    // P8 safety gate (v0.4.16): subagents are not yet routed to OpenAI-family
    // executors. `EXECUTOR_PROVIDER == "openai"` is the exact value
    // `apply_to_env` (config.rs) writes for executor providers openai/custom —
    // every OpenAI-compatible menu provider (GLM/Kimi/MiniMax/Gemini/…)
    // collapses to this literal. Without this gate an OpenAI-family main
    // session would SILENTLY build the Anthropic client below and bill the
    // user's Anthropic OAuth/Keychain credential. Fail loud instead. The
    // exact-match (no trim, no lowercase) mirrors
    // `resolve_openai_executor_config`, so the detection set is exactly the
    // routing set and never misfires on anthropic / anthropic-compat
    // (Category A/B), whose EXECUTOR_PROVIDER is unset/cleared. Full
    // OpenAI-family subagent routing (P8 — design in
    // idea-stage/v0.4.16/p8_design.json) is on the roadmap but not yet
    // shipped; this message is intentionally version-agnostic (it must not
    // promise a specific release) and carries no credential names.
    if std::env::var("EXECUTOR_PROVIDER").as_deref() == Ok("openai") {
        return Err("subagents currently require an Anthropic-family executor; \
                    dispatching a subagent from an OpenAI-family session is not yet \
                    supported. Your main session is unaffected — to use subagents, run \
                    with an Anthropic-family executor."
            .to_string());
    }

    let model = job
        .manifest
        .model
        .clone()
        .unwrap_or_else(|| DEFAULT_AGENT_MODEL.to_string());
    let allowed_tools = job.allowed_tools.clone();
    let api_client = AnthropicRuntimeClient::new(model, allowed_tools.clone())?;
    let tool_executor = SubagentToolExecutor::new(allowed_tools);
    Ok(ConversationRuntime::new(
        Session::new(),
        api_client,
        tool_executor,
        agent_permission_policy(),
        job.system_prompt.clone(),
    ))
}

fn build_agent_system_prompt(subagent_type: &str) -> Result<Vec<String>, String> {
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    let mut prompt = load_system_prompt(
        cwd,
        default_agent_system_date(),
        std::env::consts::OS,
        "unknown",
        None,
    )
    .map_err(|error| error.to_string())?;
    prompt.push(format!(
        "You are a background sub-agent of type `{subagent_type}`. Work only on the delegated task, use only the tools available to you, do not ask the user questions, and finish with a concise result."
    ));
    Ok(prompt)
}

fn resolve_agent_model(model: Option<&str>) -> String {
    model
        .map(str::trim)
        .filter(|model| !model.is_empty())
        .unwrap_or(DEFAULT_AGENT_MODEL)
        .to_string()
}

fn allowed_tools_for_subagent(subagent_type: &str) -> BTreeSet<String> {
    let tools = match subagent_type {
        "Explore" => vec![
            "read_file",
            "glob_search",
            "grep_search",
            "WebFetch",
            "WebSearch",
            "ToolSearch",
            "Skill",
            "StructuredOutput",
        ],
        "Plan" => vec![
            "read_file",
            "glob_search",
            "grep_search",
            "WebFetch",
            "WebSearch",
            "ToolSearch",
            "Skill",
            "TodoWrite",
            "StructuredOutput",
            "SendUserMessage",
        ],
        "Verification" => vec![
            "bash",
            "read_file",
            "glob_search",
            "grep_search",
            "WebFetch",
            "WebSearch",
            "ToolSearch",
            "TodoWrite",
            "StructuredOutput",
            "SendUserMessage",
            "PowerShell",
        ],
        "claw-code-guide" => vec![
            "read_file",
            "glob_search",
            "grep_search",
            "WebFetch",
            "WebSearch",
            "ToolSearch",
            "Skill",
            "StructuredOutput",
            "SendUserMessage",
        ],
        "statusline-setup" => vec![
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "glob_search",
            "grep_search",
            "ToolSearch",
        ],
        _ => vec![
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "glob_search",
            "grep_search",
            "WebFetch",
            "WebSearch",
            "TodoWrite",
            "Skill",
            "ToolSearch",
            "NotebookEdit",
            "Sleep",
            "SendUserMessage",
            "Config",
            "StructuredOutput",
            "REPL",
            "PowerShell",
        ],
    };
    tools.into_iter().map(str::to_string).collect()
}

fn agent_permission_policy() -> PermissionPolicy {
    mvp_tool_specs().into_iter().fold(
        PermissionPolicy::new(PermissionMode::DangerFullAccess),
        |policy, spec| policy.with_tool_requirement(spec.name, spec.required_permission),
    )
}

fn write_agent_manifest(manifest: &AgentOutput) -> Result<(), String> {
    std::fs::write(
        &manifest.manifest_file,
        serde_json::to_string_pretty(manifest).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn persist_agent_terminal_state(
    manifest: &AgentOutput,
    status: &str,
    result: Option<&str>,
    error: Option<String>,
) -> Result<(), String> {
    append_agent_output(
        &manifest.output_file,
        &format_agent_terminal_output(status, result, error.as_deref()),
    )?;
    let mut next_manifest = manifest.clone();
    next_manifest.status = status.to_string();
    next_manifest.completed_at = Some(iso8601_now());
    next_manifest.error = error;
    write_agent_manifest(&next_manifest)
}

fn append_agent_output(path: &str, suffix: &str) -> Result<(), String> {
    use std::io::Write as _;

    let mut file = std::fs::OpenOptions::new()
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    file.write_all(suffix.as_bytes())
        .map_err(|error| error.to_string())
}

fn format_agent_terminal_output(status: &str, result: Option<&str>, error: Option<&str>) -> String {
    let mut sections = vec![format!("\n## Result\n\n- status: {status}\n")];
    if let Some(result) = result.filter(|value| !value.trim().is_empty()) {
        sections.push(format!("\n### Final response\n\n{}\n", result.trim()));
    }
    if let Some(error) = error.filter(|value| !value.trim().is_empty()) {
        sections.push(format!("\n### Error\n\n{}\n", error.trim()));
    }
    sections.join("")
}

struct AnthropicRuntimeClient {
    runtime: tokio::runtime::Runtime,
    client: AnthropicClient,
    model: String,
    allowed_tools: BTreeSet<String>,
    /// v0.4.18: latches the subagent's Opus 4.8 → 4.7 fallback (see `stream`)
    /// so it warns once and never re-probes on subsequent turns.
    model_fell_back: bool,
}

impl AnthropicRuntimeClient {
    fn new(model: String, allowed_tools: BTreeSet<String>) -> Result<Self, String> {
        let client = AnthropicClient::from_env()
            .map_err(|error| error.to_string())?
            .with_base_url(read_base_url());
        Ok(Self {
            runtime: tokio::runtime::Runtime::new().map_err(|error| error.to_string())?,
            client,
            model,
            allowed_tools,
            model_fell_back: false,
        })
    }
}

impl ApiClient for AnthropicRuntimeClient {
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
        // v0.4.17 (T1/T6): subagents are deliberately NOT given MCP tools —
        // only the static catalogue flows through here. Converting via
        // RuntimeToolSpec keeps the request payload byte-identical to the
        // previous inline construction while migrating the request-building
        // layer onto the owned-name spec type.
        let tools = tool_specs_for_allowed_tools(Some(&self.allowed_tools))
            .iter()
            .map(RuntimeToolSpec::from)
            .map(|spec| ToolDefinition {
                name: spec.name,
                description: Some(spec.description),
                input_schema: spec.input_schema,
            })
            .collect::<Vec<_>>();
        let mut message_request = MessageRequest {
            model: self.model.clone(),
            max_tokens: 32_000,
            messages: convert_messages(&request.messages),
            system: if request.system_prompt.is_empty() {
                None
            } else {
                Some(serde_json::json!(request.system_prompt.join("\n\n")))
            },
            tools: (!tools.is_empty()).then_some(tools),
            tool_choice: (!self.allowed_tools.is_empty()).then_some(ToolChoice::Auto),
            stream: true,
        };

        self.runtime.block_on(async {
            // v0.4.18: subagent default-model fallback. If the default
            // DEFAULT_AGENT_MODEL (Opus 4.8) is unavailable on this account
            // (404 not_found from the initial POST, before any stream event),
            // fall back to 4.7 and retry once so background Agent tasks don't
            // hard-fail for users without 4.8 access. Latched + warn-once.
            let mut stream = match self.client.stream_message(&message_request).await {
                Ok(stream) => stream,
                Err(error)
                    if error.is_model_unavailable()
                        && message_request.model == DEFAULT_AGENT_MODEL
                        && !self.model_fell_back =>
                {
                    self.model_fell_back = true;
                    self.model = DEFAULT_AGENT_MODEL_FALLBACK.to_string();
                    message_request.model = DEFAULT_AGENT_MODEL_FALLBACK.to_string();
                    eprintln!(
                        "\x1b[33mwarning:\x1b[0m {DEFAULT_AGENT_MODEL} is not available on this \
                         account; subagent falling back to {DEFAULT_AGENT_MODEL_FALLBACK}."
                    );
                    self.client
                        .stream_message(&message_request)
                        .await
                        .map_err(|error| RuntimeError::new(error.to_string()))?
                }
                Err(error) => return Err(RuntimeError::new(error.to_string())),
            };
            let mut events = Vec::new();
            let mut pending_tool: Option<(String, String, String)> = None;
            let mut saw_stop = false;

            while let Some(event) = stream
                .next_event()
                .await
                .map_err(|error| RuntimeError::new(error.to_string()))?
            {
                match event {
                    ApiStreamEvent::MessageStart(start) => {
                        for block in start.message.content {
                            push_output_block(block, &mut events, &mut pending_tool, true);
                        }
                    }
                    ApiStreamEvent::ContentBlockStart(start) => {
                        push_output_block(
                            start.content_block,
                            &mut events,
                            &mut pending_tool,
                            true,
                        );
                    }
                    ApiStreamEvent::ContentBlockDelta(delta) => match delta.delta {
                        ContentBlockDelta::TextDelta { text } => {
                            if !text.is_empty() {
                                events.push(AssistantEvent::TextDelta(text));
                            }
                        }
                        ContentBlockDelta::InputJsonDelta { partial_json } => {
                            if let Some((_, _, input)) = &mut pending_tool {
                                input.push_str(&partial_json);
                            }
                        }
                        ContentBlockDelta::ThinkingDelta { .. } => {},
                        ContentBlockDelta::SignatureDelta { .. } => {},
                    },
                    ApiStreamEvent::ContentBlockStop(_) => {
                        if let Some((id, name, input)) = pending_tool.take() {
                            events.push(AssistantEvent::ToolUse { id, name, input });
                        }
                    }
                    ApiStreamEvent::MessageDelta(delta) => {
                        events.push(AssistantEvent::Usage(TokenUsage {
                            input_tokens: delta.usage.input_tokens,
                            output_tokens: delta.usage.output_tokens,
                            cache_creation_input_tokens: 0,
                            cache_read_input_tokens: 0,
                        }));
                    }
                    ApiStreamEvent::MessageStop(_) => {
                        saw_stop = true;
                        events.push(AssistantEvent::MessageStop);
                    }
                    ApiStreamEvent::Error(e) => {
                        let msg = e.error.get("message").and_then(|v| v.as_str()).unwrap_or("stream error").to_string();
                        return Err(RuntimeError::new(msg));
                    }
                }
            }

            if !saw_stop
                && events.iter().any(|event| {
                    matches!(event, AssistantEvent::TextDelta(text) if !text.is_empty())
                        || matches!(event, AssistantEvent::ToolUse { .. })
                })
            {
                events.push(AssistantEvent::MessageStop);
            }

            if events
                .iter()
                .any(|event| matches!(event, AssistantEvent::MessageStop))
            {
                return Ok(events);
            }

            let response = self
                .client
                .send_message(&MessageRequest {
                    stream: false,
                    ..message_request.clone()
                })
                .await
                .map_err(|error| RuntimeError::new(error.to_string()))?;
            Ok(response_to_events(response))
        })
    }
}

struct SubagentToolExecutor {
    allowed_tools: BTreeSet<String>,
}

impl SubagentToolExecutor {
    fn new(allowed_tools: BTreeSet<String>) -> Self {
        Self { allowed_tools }
    }
}

impl ToolExecutor for SubagentToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError> {
        if !self.allowed_tools.contains(tool_name) {
            return Err(ToolError::new(format!(
                "tool `{tool_name}` is not enabled for this sub-agent"
            )));
        }
        let value = serde_json::from_str(input)
            .map_err(|error| ToolError::new(format!("invalid tool input JSON: {error}")))?;
        execute_tool(tool_name, &value).map_err(ToolError::new)
    }
}

/// v0.4.17 (T6): the tool catalogue a SUB-AGENT may use.
///
/// This is **structurally** the static MVP catalogue only — it is built solely
/// from [`mvp_tool_specs`], which never contains an `mcp__`-prefixed name. A
/// sub-agent therefore can never be advertised, nor dispatch, an MCP tool:
/// - it has no [`crate::McpToolCatalog`] / `SharedMcpRuntime` (only the main
///   session's `CliToolExecutor` holds one), and
/// - [`SubagentToolExecutor::execute`] routes through [`execute_tool`], which
///   returns `unsupported tool` for any `mcp__` name (the main session
///   intercepts MCP names ABOVE `execute_tool`, in `CliToolExecutor::execute`).
///
/// This is a deliberate v0.4.17 boundary: giving sub-agents their own MCP
/// access is re-considered alongside P8 (OpenAI-family subagent routing) in
/// v0.4.18 (plan.md T6). Until then the no-MCP property is enforced here purely
/// by construction (no MCP source can flow in), pinned by
/// `subagent_tool_directory_never_contains_mcp_names`.
fn tool_specs_for_allowed_tools(allowed_tools: Option<&BTreeSet<String>>) -> Vec<ToolSpec> {
    mvp_tool_specs()
        .into_iter()
        .filter(|spec| allowed_tools.is_none_or(|allowed| allowed.contains(spec.name)))
        .collect()
}

fn convert_messages(messages: &[ConversationMessage]) -> Vec<InputMessage> {
    messages
        .iter()
        .filter_map(|message| {
            let role = match message.role {
                MessageRole::System | MessageRole::User | MessageRole::Tool => "user",
                MessageRole::Assistant => "assistant",
            };
            let content = message
                .blocks
                .iter()
                .map(|block| match block {
                    ContentBlock::Text { text } => InputContentBlock::Text { text: text.clone() },
                    ContentBlock::ToolUse { id, name, input } => InputContentBlock::ToolUse {
                        id: id.clone(),
                        name: name.clone(),
                        input: serde_json::from_str(input)
                            .unwrap_or_else(|_| serde_json::json!({ "raw": input })),
                    },
                    ContentBlock::ToolResult {
                        tool_use_id,
                        output,
                        is_error,
                        ..
                    } => InputContentBlock::ToolResult {
                        tool_use_id: tool_use_id.clone(),
                        content: vec![ToolResultContentBlock::Text {
                            text: output.clone(),
                        }],
                        is_error: *is_error,
                    },
                    ContentBlock::Thinking {
                        thinking,
                        signature,
                    } => InputContentBlock::Thinking {
                        thinking: thinking.clone(),
                        signature: signature.clone(),
                    },
                })
                .collect::<Vec<_>>();
            (!content.is_empty()).then(|| InputMessage {
                role: role.to_string(),
                content,
            })
        })
        .collect()
}

fn push_output_block(
    block: OutputContentBlock,
    events: &mut Vec<AssistantEvent>,
    pending_tool: &mut Option<(String, String, String)>,
    streaming_tool_input: bool,
) {
    match block {
        OutputContentBlock::Text { text } => {
            if !text.is_empty() {
                events.push(AssistantEvent::TextDelta(text));
            }
        }
        OutputContentBlock::ToolUse { id, name, input } => {
            let initial_input = if streaming_tool_input
                && input.is_object()
                && input.as_object().is_some_and(serde_json::Map::is_empty)
            {
                String::new()
            } else {
                input.to_string()
            };
            *pending_tool = Some((id, name, initial_input));
        }
        OutputContentBlock::Thinking {
            thinking,
            signature,
        } => {
            events.push(AssistantEvent::Thinking {
                thinking,
                signature,
            });
        }
    }
}

fn response_to_events(response: MessageResponse) -> Vec<AssistantEvent> {
    let mut events = Vec::new();
    let mut pending_tool = None;

    for block in response.content {
        push_output_block(block, &mut events, &mut pending_tool, false);
        if let Some((id, name, input)) = pending_tool.take() {
            events.push(AssistantEvent::ToolUse { id, name, input });
        }
    }

    events.push(AssistantEvent::Usage(TokenUsage {
        input_tokens: response.usage.input_tokens,
        output_tokens: response.usage.output_tokens,
        cache_creation_input_tokens: response.usage.cache_creation_input_tokens,
        cache_read_input_tokens: response.usage.cache_read_input_tokens,
    }));
    events.push(AssistantEvent::MessageStop);
    events
}

fn final_assistant_text(summary: &runtime::TurnSummary) -> String {
    summary
        .assistant_messages
        .last()
        .map(|message| {
            message
                .blocks
                .iter()
                .filter_map(|block| match block {
                    ContentBlock::Text { text } => Some(text.as_str()),
                    _ => None,
                })
                .collect::<Vec<_>>()
                .join("")
        })
        .unwrap_or_default()
}

#[allow(clippy::needless_pass_by_value)]
fn execute_tool_search(input: ToolSearchInput) -> ToolSearchOutput {
    let deferred = deferred_tool_specs();
    let max_results = input.max_results.unwrap_or(5).max(1);
    let query = input.query.trim().to_string();
    let normalized_query = normalize_tool_search_query(&query);
    let matches = search_tool_specs(&query, max_results, &deferred);

    ToolSearchOutput {
        matches,
        query,
        normalized_query,
        total_deferred_tools: deferred.len(),
        pending_mcp_servers: None,
    }
}

fn deferred_tool_specs() -> Vec<ToolSpec> {
    mvp_tool_specs()
        .into_iter()
        .filter(|spec| {
            !matches!(
                spec.name,
                "bash" | "read_file" | "write_file" | "edit_file" | "glob_search" | "grep_search"
            )
        })
        .collect()
}

fn search_tool_specs(query: &str, max_results: usize, specs: &[ToolSpec]) -> Vec<String> {
    let lowered = query.to_lowercase();
    if let Some(selection) = lowered.strip_prefix("select:") {
        return selection
            .split(',')
            .map(str::trim)
            .filter(|part| !part.is_empty())
            .filter_map(|wanted| {
                let wanted = canonical_tool_token(wanted);
                specs
                    .iter()
                    .find(|spec| canonical_tool_token(spec.name) == wanted)
                    .map(|spec| spec.name.to_string())
            })
            .take(max_results)
            .collect();
    }

    let mut required = Vec::new();
    let mut optional = Vec::new();
    for term in lowered.split_whitespace() {
        if let Some(rest) = term.strip_prefix('+') {
            if !rest.is_empty() {
                required.push(rest);
            }
        } else {
            optional.push(term);
        }
    }
    let terms = if required.is_empty() {
        optional.clone()
    } else {
        required.iter().chain(optional.iter()).copied().collect()
    };

    let mut scored = specs
        .iter()
        .filter_map(|spec| {
            let name = spec.name.to_lowercase();
            let canonical_name = canonical_tool_token(spec.name);
            let normalized_description = normalize_tool_search_query(spec.description);
            let haystack = format!(
                "{name} {} {canonical_name}",
                spec.description.to_lowercase()
            );
            let normalized_haystack = format!("{canonical_name} {normalized_description}");
            if required.iter().any(|term| !haystack.contains(term)) {
                return None;
            }

            let mut score = 0_i32;
            for term in &terms {
                let canonical_term = canonical_tool_token(term);
                if haystack.contains(term) {
                    score += 2;
                }
                if name == *term {
                    score += 8;
                }
                if name.contains(term) {
                    score += 4;
                }
                if canonical_name == canonical_term {
                    score += 12;
                }
                if normalized_haystack.contains(&canonical_term) {
                    score += 3;
                }
            }

            if score == 0 && !lowered.is_empty() {
                return None;
            }
            Some((score, spec.name.to_string()))
        })
        .collect::<Vec<_>>();

    scored.sort_by(|left, right| right.0.cmp(&left.0).then_with(|| left.1.cmp(&right.1)));
    scored
        .into_iter()
        .map(|(_, name)| name)
        .take(max_results)
        .collect()
}

fn normalize_tool_search_query(query: &str) -> String {
    query
        .trim()
        .split(|ch: char| ch.is_whitespace() || ch == ',')
        .filter(|term| !term.is_empty())
        .map(canonical_tool_token)
        .collect::<Vec<_>>()
        .join(" ")
}

fn canonical_tool_token(value: &str) -> String {
    let mut canonical = value
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .flat_map(char::to_lowercase)
        .collect::<String>();
    if let Some(stripped) = canonical.strip_suffix("tool") {
        canonical = stripped.to_string();
    }
    canonical
}

fn agent_store_dir() -> Result<std::path::PathBuf, String> {
    if let Ok(path) = std::env::var("CLAWD_AGENT_STORE") {
        return Ok(std::path::PathBuf::from(path));
    }
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    if let Some(workspace_root) = cwd.ancestors().nth(2) {
        return Ok(workspace_root.join(".clawd-agents"));
    }
    Ok(cwd.join(".clawd-agents"))
}

fn make_agent_id() -> String {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("agent-{nanos}")
}

fn slugify_agent_name(description: &str) -> String {
    let mut out = description
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>();
    while out.contains("--") {
        out = out.replace("--", "-");
    }
    out.trim_matches('-').chars().take(32).collect()
}

fn normalize_subagent_type(subagent_type: Option<&str>) -> String {
    let trimmed = subagent_type.map(str::trim).unwrap_or_default();
    if trimmed.is_empty() {
        return String::from("general-purpose");
    }

    match canonical_tool_token(trimmed).as_str() {
        "general" | "generalpurpose" | "generalpurposeagent" => String::from("general-purpose"),
        "explore" | "explorer" | "exploreagent" => String::from("Explore"),
        "plan" | "planagent" => String::from("Plan"),
        "verification" | "verificationagent" | "verify" | "verifier" => {
            String::from("Verification")
        }
        "claudecodeguide" | "claudecodeguideagent" | "guide" => String::from("claw-code-guide"),
        "statusline" | "statuslinesetup" => String::from("statusline-setup"),
        _ => trimmed.to_string(),
    }
}

fn iso8601_now() -> String {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string()
}

#[allow(clippy::too_many_lines)]
fn execute_notebook_edit(input: NotebookEditInput) -> Result<NotebookEditOutput, String> {
    let path = std::path::PathBuf::from(&input.notebook_path);
    if path.extension().and_then(|ext| ext.to_str()) != Some("ipynb") {
        return Err(String::from(
            "File must be a Jupyter notebook (.ipynb file).",
        ));
    }

    let original_file = std::fs::read_to_string(&path).map_err(|error| error.to_string())?;
    let mut notebook: serde_json::Value =
        serde_json::from_str(&original_file).map_err(|error| error.to_string())?;
    let language = notebook
        .get("metadata")
        .and_then(|metadata| metadata.get("kernelspec"))
        .and_then(|kernelspec| kernelspec.get("language"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or("python")
        .to_string();
    let cells = notebook
        .get_mut("cells")
        .and_then(serde_json::Value::as_array_mut)
        .ok_or_else(|| String::from("Notebook cells array not found"))?;

    let edit_mode = input.edit_mode.unwrap_or(NotebookEditMode::Replace);
    let target_index = match input.cell_id.as_deref() {
        Some(cell_id) => Some(resolve_cell_index(cells, Some(cell_id), edit_mode)?),
        None if matches!(
            edit_mode,
            NotebookEditMode::Replace | NotebookEditMode::Delete
        ) =>
        {
            Some(resolve_cell_index(cells, None, edit_mode)?)
        }
        None => None,
    };
    let resolved_cell_type = match edit_mode {
        NotebookEditMode::Delete => None,
        NotebookEditMode::Insert => Some(input.cell_type.unwrap_or(NotebookCellType::Code)),
        NotebookEditMode::Replace => Some(input.cell_type.unwrap_or_else(|| {
            target_index
                .and_then(|index| cells.get(index))
                .and_then(cell_kind)
                .unwrap_or(NotebookCellType::Code)
        })),
    };
    let new_source = require_notebook_source(input.new_source, edit_mode)?;

    let cell_id = match edit_mode {
        NotebookEditMode::Insert => {
            let resolved_cell_type = resolved_cell_type.expect("insert cell type");
            let new_id = unused_cell_id(cells);
            let new_cell = build_notebook_cell(&new_id, resolved_cell_type, &new_source);
            let insert_at = target_index.map_or(cells.len(), |index| index + 1);
            cells.insert(insert_at, new_cell);
            cells
                .get(insert_at)
                .and_then(|cell| cell.get("id"))
                .and_then(serde_json::Value::as_str)
                .map(ToString::to_string)
        }
        NotebookEditMode::Delete => {
            let removed = cells.remove(target_index.expect("delete target index"));
            removed
                .get("id")
                .and_then(serde_json::Value::as_str)
                .map(ToString::to_string)
        }
        NotebookEditMode::Replace => {
            let resolved_cell_type = resolved_cell_type.expect("replace cell type");
            let cell = cells
                .get_mut(target_index.expect("replace target index"))
                .ok_or_else(|| String::from("Cell index out of range"))?;
            cell["source"] = serde_json::Value::Array(source_lines(&new_source));
            cell["cell_type"] = serde_json::Value::String(match resolved_cell_type {
                NotebookCellType::Code => String::from("code"),
                NotebookCellType::Markdown => String::from("markdown"),
            });
            match resolved_cell_type {
                NotebookCellType::Code => {
                    if !cell.get("outputs").is_some_and(serde_json::Value::is_array) {
                        cell["outputs"] = json!([]);
                    }
                    if cell.get("execution_count").is_none() {
                        cell["execution_count"] = serde_json::Value::Null;
                    }
                }
                NotebookCellType::Markdown => {
                    if let Some(object) = cell.as_object_mut() {
                        object.remove("outputs");
                        object.remove("execution_count");
                    }
                }
            }
            cell.get("id")
                .and_then(serde_json::Value::as_str)
                .map(ToString::to_string)
        }
    };

    let updated_file =
        serde_json::to_string_pretty(&notebook).map_err(|error| error.to_string())?;
    std::fs::write(&path, &updated_file).map_err(|error| error.to_string())?;

    Ok(NotebookEditOutput {
        new_source,
        cell_id,
        cell_type: resolved_cell_type,
        language,
        edit_mode: format_notebook_edit_mode(edit_mode),
        error: None,
        notebook_path: path.display().to_string(),
        original_file,
        updated_file,
    })
}

fn require_notebook_source(
    source: Option<String>,
    edit_mode: NotebookEditMode,
) -> Result<String, String> {
    match edit_mode {
        NotebookEditMode::Delete => Ok(source.unwrap_or_default()),
        NotebookEditMode::Insert | NotebookEditMode::Replace => source
            .ok_or_else(|| String::from("new_source is required for insert and replace edits")),
    }
}

fn build_notebook_cell(cell_id: &str, cell_type: NotebookCellType, source: &str) -> Value {
    let mut cell = json!({
        "cell_type": match cell_type {
            NotebookCellType::Code => "code",
            NotebookCellType::Markdown => "markdown",
        },
        "id": cell_id,
        "metadata": {},
        "source": source_lines(source),
    });
    if let Some(object) = cell.as_object_mut() {
        match cell_type {
            NotebookCellType::Code => {
                object.insert(String::from("outputs"), json!([]));
                object.insert(String::from("execution_count"), Value::Null);
            }
            NotebookCellType::Markdown => {}
        }
    }
    cell
}

fn cell_kind(cell: &serde_json::Value) -> Option<NotebookCellType> {
    cell.get("cell_type")
        .and_then(serde_json::Value::as_str)
        .map(|kind| {
            if kind == "markdown" {
                NotebookCellType::Markdown
            } else {
                NotebookCellType::Code
            }
        })
}

#[allow(clippy::needless_pass_by_value)]
fn execute_sleep(input: SleepInput) -> SleepOutput {
    std::thread::sleep(Duration::from_millis(input.duration_ms));
    SleepOutput {
        duration_ms: input.duration_ms,
        message: format!("Slept for {}ms", input.duration_ms),
    }
}

fn execute_brief(input: BriefInput) -> Result<BriefOutput, String> {
    if input.message.trim().is_empty() {
        return Err(String::from("message must not be empty"));
    }

    let attachments = input
        .attachments
        .as_ref()
        .map(|paths| {
            paths
                .iter()
                .map(|path| resolve_attachment(path))
                .collect::<Result<Vec<_>, String>>()
        })
        .transpose()?;

    let message = match input.status {
        BriefStatus::Normal | BriefStatus::Proactive => input.message,
    };

    Ok(BriefOutput {
        message,
        attachments,
        sent_at: iso8601_timestamp(),
    })
}

fn resolve_attachment(path: &str) -> Result<ResolvedAttachment, String> {
    let resolved = std::fs::canonicalize(path).map_err(|error| error.to_string())?;
    let metadata = std::fs::metadata(&resolved).map_err(|error| error.to_string())?;
    Ok(ResolvedAttachment {
        path: resolved.display().to_string(),
        size: metadata.len(),
        is_image: is_image_path(&resolved),
    })
}

fn is_image_path(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|ext| ext.to_str())
            .map(str::to_ascii_lowercase)
            .as_deref(),
        Some("png" | "jpg" | "jpeg" | "gif" | "webp" | "bmp" | "svg")
    )
}

fn execute_config(input: ConfigInput) -> Result<ConfigOutput, String> {
    let setting = input.setting.trim();
    if setting.is_empty() {
        return Err(String::from("setting must not be empty"));
    }
    let Some(spec) = supported_config_setting(setting) else {
        return Ok(ConfigOutput {
            success: false,
            operation: None,
            setting: None,
            value: None,
            previous_value: None,
            new_value: None,
            error: Some(format!("Unknown setting: \"{setting}\"")),
        });
    };

    let path = config_file_for_scope(spec.scope)?;
    let mut document = read_json_object(&path)?;

    if let Some(value) = input.value {
        let normalized = normalize_config_value(spec, value)?;
        let previous_value = get_nested_value(&document, spec.path).cloned();
        set_nested_value(&mut document, spec.path, normalized.clone());
        write_json_object(&path, &document)?;
        Ok(ConfigOutput {
            success: true,
            operation: Some(String::from("set")),
            setting: Some(setting.to_string()),
            value: Some(normalized.clone()),
            previous_value,
            new_value: Some(normalized),
            error: None,
        })
    } else {
        Ok(ConfigOutput {
            success: true,
            operation: Some(String::from("get")),
            setting: Some(setting.to_string()),
            value: get_nested_value(&document, spec.path).cloned(),
            previous_value: None,
            new_value: None,
            error: None,
        })
    }
}

fn execute_structured_output(input: StructuredOutputInput) -> StructuredOutputResult {
    StructuredOutputResult {
        data: String::from("Structured output provided successfully"),
        structured_output: input.0,
    }
}

fn execute_repl(input: ReplInput) -> Result<ReplOutput, String> {
    if input.code.trim().is_empty() {
        return Err(String::from("code must not be empty"));
    }
    let _ = input.timeout_ms;
    let runtime = resolve_repl_runtime(&input.language)?;
    let started = Instant::now();
    let output = Command::new(runtime.program)
        .args(runtime.args)
        .arg(&input.code)
        .output()
        .map_err(|error| error.to_string())?;

    Ok(ReplOutput {
        language: input.language,
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        exit_code: output.status.code().unwrap_or(1),
        duration_ms: started.elapsed().as_millis(),
    })
}

struct ReplRuntime {
    program: &'static str,
    args: &'static [&'static str],
}

fn resolve_repl_runtime(language: &str) -> Result<ReplRuntime, String> {
    match language.trim().to_ascii_lowercase().as_str() {
        "python" | "py" => Ok(ReplRuntime {
            program: detect_first_command(&["python3", "python"])
                .ok_or_else(|| String::from("python runtime not found"))?,
            args: &["-c"],
        }),
        "javascript" | "js" | "node" => Ok(ReplRuntime {
            program: detect_first_command(&["node"])
                .ok_or_else(|| String::from("node runtime not found"))?,
            args: &["-e"],
        }),
        "sh" | "shell" | "bash" => Ok(ReplRuntime {
            program: detect_first_command(&["bash", "sh"])
                .ok_or_else(|| String::from("shell runtime not found"))?,
            args: &["-lc"],
        }),
        other => Err(format!("unsupported REPL language: {other}")),
    }
}

fn detect_first_command(commands: &[&'static str]) -> Option<&'static str> {
    commands
        .iter()
        .copied()
        .find(|command| command_exists(command))
}

#[derive(Clone, Copy)]
enum ConfigScope {
    Global,
    Settings,
}

#[derive(Clone, Copy)]
struct ConfigSettingSpec {
    scope: ConfigScope,
    kind: ConfigKind,
    path: &'static [&'static str],
    options: Option<&'static [&'static str]>,
}

#[derive(Clone, Copy)]
enum ConfigKind {
    Boolean,
    String,
}

fn supported_config_setting(setting: &str) -> Option<ConfigSettingSpec> {
    Some(match setting {
        "theme" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::String,
            path: &["theme"],
            options: None,
        },
        "editorMode" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::String,
            path: &["editorMode"],
            options: Some(&["default", "vim", "emacs"]),
        },
        "verbose" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["verbose"],
            options: None,
        },
        "preferredNotifChannel" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::String,
            path: &["preferredNotifChannel"],
            options: None,
        },
        "autoCompactEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["autoCompactEnabled"],
            options: None,
        },
        "autoMemoryEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::Boolean,
            path: &["autoMemoryEnabled"],
            options: None,
        },
        "autoDreamEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::Boolean,
            path: &["autoDreamEnabled"],
            options: None,
        },
        "fileCheckpointingEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["fileCheckpointingEnabled"],
            options: None,
        },
        "showTurnDuration" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["showTurnDuration"],
            options: None,
        },
        "terminalProgressBarEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["terminalProgressBarEnabled"],
            options: None,
        },
        "todoFeatureEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::Boolean,
            path: &["todoFeatureEnabled"],
            options: None,
        },
        "model" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::String,
            path: &["model"],
            options: None,
        },
        "alwaysThinkingEnabled" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::Boolean,
            path: &["alwaysThinkingEnabled"],
            options: None,
        },
        "permissions.defaultMode" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::String,
            path: &["permissions", "defaultMode"],
            options: Some(&["default", "plan", "acceptEdits", "dontAsk", "auto"]),
        },
        "language" => ConfigSettingSpec {
            scope: ConfigScope::Settings,
            kind: ConfigKind::String,
            path: &["language"],
            options: None,
        },
        "teammateMode" => ConfigSettingSpec {
            scope: ConfigScope::Global,
            kind: ConfigKind::String,
            path: &["teammateMode"],
            options: Some(&["tmux", "in-process", "auto"]),
        },
        _ => return None,
    })
}

fn normalize_config_value(spec: ConfigSettingSpec, value: ConfigValue) -> Result<Value, String> {
    let normalized = match (spec.kind, value) {
        (ConfigKind::Boolean, ConfigValue::Bool(value)) => Value::Bool(value),
        (ConfigKind::Boolean, ConfigValue::String(value)) => {
            match value.trim().to_ascii_lowercase().as_str() {
                "true" => Value::Bool(true),
                "false" => Value::Bool(false),
                _ => return Err(String::from("setting requires true or false")),
            }
        }
        (ConfigKind::Boolean, ConfigValue::Number(_)) => {
            return Err(String::from("setting requires true or false"))
        }
        (ConfigKind::String, ConfigValue::String(value)) => Value::String(value),
        (ConfigKind::String, ConfigValue::Bool(value)) => Value::String(value.to_string()),
        (ConfigKind::String, ConfigValue::Number(value)) => json!(value),
    };

    if let Some(options) = spec.options {
        let Some(as_str) = normalized.as_str() else {
            return Err(String::from("setting requires a string value"));
        };
        if !options.iter().any(|option| option == &as_str) {
            return Err(format!(
                "Invalid value \"{as_str}\". Options: {}",
                options.join(", ")
            ));
        }
    }

    Ok(normalized)
}

fn config_file_for_scope(scope: ConfigScope) -> Result<PathBuf, String> {
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    Ok(match scope {
        ConfigScope::Global => config_home_dir()?.join("settings.json"),
        ConfigScope::Settings => cwd.join(".claude").join("settings.local.json"),
    })
}

fn config_home_dir() -> Result<PathBuf, String> {
    if let Ok(path) = std::env::var("CLAUDE_CONFIG_HOME") {
        return Ok(PathBuf::from(path));
    }
    let home = Ok::<String, String>(runtime::home_dir())?;
    Ok(PathBuf::from(home).join(".claude"))
}

fn read_json_object(path: &Path) -> Result<serde_json::Map<String, Value>, String> {
    match std::fs::read_to_string(path) {
        Ok(contents) => {
            if contents.trim().is_empty() {
                return Ok(serde_json::Map::new());
            }
            serde_json::from_str::<Value>(&contents)
                .map_err(|error| error.to_string())?
                .as_object()
                .cloned()
                .ok_or_else(|| String::from("config file must contain a JSON object"))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(serde_json::Map::new()),
        Err(error) => Err(error.to_string()),
    }
}

fn write_json_object(path: &Path, value: &serde_json::Map<String, Value>) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    std::fs::write(
        path,
        serde_json::to_string_pretty(value).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn get_nested_value<'a>(
    value: &'a serde_json::Map<String, Value>,
    path: &[&str],
) -> Option<&'a Value> {
    let (first, rest) = path.split_first()?;
    let mut current = value.get(*first)?;
    for key in rest {
        current = current.as_object()?.get(*key)?;
    }
    Some(current)
}

fn set_nested_value(root: &mut serde_json::Map<String, Value>, path: &[&str], new_value: Value) {
    let (first, rest) = path.split_first().expect("config path must not be empty");
    if rest.is_empty() {
        root.insert((*first).to_string(), new_value);
        return;
    }

    let entry = root
        .entry((*first).to_string())
        .or_insert_with(|| Value::Object(serde_json::Map::new()));
    if !entry.is_object() {
        *entry = Value::Object(serde_json::Map::new());
    }
    let map = entry.as_object_mut().expect("object inserted");
    set_nested_value(map, rest, new_value);
}

fn iso8601_timestamp() -> String {
    if let Ok(output) = Command::new("date")
        .args(["-u", "+%Y-%m-%dT%H:%M:%SZ"])
        .output()
    {
        if output.status.success() {
            return String::from_utf8_lossy(&output.stdout).trim().to_string();
        }
    }
    iso8601_now()
}

#[allow(clippy::needless_pass_by_value)]
fn execute_powershell(input: PowerShellInput) -> std::io::Result<runtime::BashCommandOutput> {
    let _ = &input.description;
    let shell = detect_powershell_shell()?;
    execute_shell_command(
        shell,
        &input.command,
        input.timeout,
        input.run_in_background,
    )
}

fn detect_powershell_shell() -> std::io::Result<&'static str> {
    if command_exists("pwsh") {
        Ok("pwsh")
    } else if command_exists("powershell") {
        Ok("powershell")
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            "PowerShell executable not found (expected `pwsh` or `powershell` in PATH)",
        ))
    }
}

fn command_exists(command: &str) -> bool {
    // v0.4.22 (C5): Windows probes via `where.exe` ONLY — never spawn the
    // target program itself (an argument-less python/pwsh can enter
    // interactive mode and hang). Runtime `cfg!` branch (not item-level
    // #[cfg]) so the unix `sh -lc` login-shell PATH semantics — which the
    // PowerShell stub-shell tests rely on — stay byte-identical.
    if cfg!(windows) {
        return std::process::Command::new("where.exe")
            .arg(command)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
    }
    std::process::Command::new("sh")
        .arg("-lc")
        .arg(format!("command -v {command} >/dev/null 2>&1"))
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

#[allow(clippy::too_many_lines)]
fn execute_shell_command(
    shell: &str,
    command: &str,
    timeout: Option<u64>,
    run_in_background: Option<bool>,
) -> std::io::Result<runtime::BashCommandOutput> {
    if run_in_background.unwrap_or(false) {
        let child = std::process::Command::new(shell)
            .arg("-NoProfile")
            .arg("-NonInteractive")
            .arg("-Command")
            .arg(command)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()?;
        return Ok(runtime::BashCommandOutput {
            stdout: String::new(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: Some(child.id().to_string()),
            backgrounded_by_user: Some(true),
            assistant_auto_backgrounded: Some(false),
            dangerously_disable_sandbox: None,
            return_code_interpretation: None,
            no_output_expected: Some(true),
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: None,
        });
    }

    let mut process = std::process::Command::new(shell);
    process
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-Command")
        .arg(command);
    process
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    if let Some(timeout_ms) = timeout {
        let mut child = process.spawn()?;
        let started = Instant::now();
        loop {
            if let Some(status) = child.try_wait()? {
                let output = child.wait_with_output()?;
                return Ok(runtime::BashCommandOutput {
                    stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
                    stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
                    raw_output_path: None,
                    interrupted: false,
                    is_image: None,
                    background_task_id: None,
                    backgrounded_by_user: None,
                    assistant_auto_backgrounded: None,
                    dangerously_disable_sandbox: None,
                    return_code_interpretation: status
                        .code()
                        .filter(|code| *code != 0)
                        .map(|code| format!("exit_code:{code}")),
                    no_output_expected: Some(output.stdout.is_empty() && output.stderr.is_empty()),
                    structured_content: None,
                    persisted_output_path: None,
                    persisted_output_size: None,
                    sandbox_status: None,
                });
            }
            if started.elapsed() >= Duration::from_millis(timeout_ms) {
                let _ = child.kill();
                let output = child.wait_with_output()?;
                let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
                let stderr = if stderr.trim().is_empty() {
                    format!("Command exceeded timeout of {timeout_ms} ms")
                } else {
                    format!(
                        "{}
Command exceeded timeout of {timeout_ms} ms",
                        stderr.trim_end()
                    )
                };
                return Ok(runtime::BashCommandOutput {
                    stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
                    stderr,
                    raw_output_path: None,
                    interrupted: true,
                    is_image: None,
                    background_task_id: None,
                    backgrounded_by_user: None,
                    assistant_auto_backgrounded: None,
                    dangerously_disable_sandbox: None,
                    return_code_interpretation: Some(String::from("timeout")),
                    no_output_expected: Some(false),
                    structured_content: None,
                    persisted_output_path: None,
                    persisted_output_size: None,
                    sandbox_status: None,
                });
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    let output = process.output()?;
    Ok(runtime::BashCommandOutput {
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        raw_output_path: None,
        interrupted: false,
        is_image: None,
        background_task_id: None,
        backgrounded_by_user: None,
        assistant_auto_backgrounded: None,
        dangerously_disable_sandbox: None,
        return_code_interpretation: output
            .status
            .code()
            .filter(|code| *code != 0)
            .map(|code| format!("exit_code:{code}")),
        no_output_expected: Some(output.stdout.is_empty() && output.stderr.is_empty()),
        structured_content: None,
        persisted_output_path: None,
        persisted_output_size: None,
        sandbox_status: None,
    })
}

fn resolve_cell_index(
    cells: &[serde_json::Value],
    cell_id: Option<&str>,
    edit_mode: NotebookEditMode,
) -> Result<usize, String> {
    if cells.is_empty()
        && matches!(
            edit_mode,
            NotebookEditMode::Replace | NotebookEditMode::Delete
        )
    {
        return Err(String::from("Notebook has no cells to edit"));
    }
    if let Some(cell_id) = cell_id {
        cells
            .iter()
            .position(|cell| cell.get("id").and_then(serde_json::Value::as_str) == Some(cell_id))
            .ok_or_else(|| format!("Cell id not found: {cell_id}"))
    } else {
        Ok(cells.len().saturating_sub(1))
    }
}

fn source_lines(source: &str) -> Vec<serde_json::Value> {
    if source.is_empty() {
        return vec![serde_json::Value::String(String::new())];
    }
    source
        .split_inclusive('\n')
        .map(|line| serde_json::Value::String(line.to_string()))
        .collect()
}

fn format_notebook_edit_mode(mode: NotebookEditMode) -> String {
    match mode {
        NotebookEditMode::Replace => String::from("replace"),
        NotebookEditMode::Insert => String::from("insert"),
        NotebookEditMode::Delete => String::from("delete"),
    }
}

fn make_cell_id(index: usize) -> String {
    format!("cell-{}", index + 1)
}

/// v0.4.22 (C8): mint a collision-free id for an inserted cell.
/// `make_cell_id(cells.len())` alone collides after delete-then-insert
/// ([cell-1, cell-3] has len 2, so it would mint "cell-3" again), and the
/// first-match lookup in `resolve_cell_index` would then edit the WRONG cell.
/// Collect the existing id set and probe cell-{len+1}, cell-{len+2}, … until
/// an unused id is found. Existing cells' ids are never rewritten; non-numeric
/// ids (e.g. "cell-a", UUIDs) simply occupy the set.
fn unused_cell_id(cells: &[serde_json::Value]) -> String {
    let existing: std::collections::HashSet<&str> = cells
        .iter()
        .filter_map(|cell| cell.get("id").and_then(serde_json::Value::as_str))
        .collect();
    let mut index = cells.len();
    loop {
        let candidate = make_cell_id(index);
        if !existing.contains(candidate.as_str()) {
            return candidate;
        }
        index += 1;
    }
}

fn parse_skill_description(contents: &str) -> Option<String> {
    for line in contents.lines() {
        if let Some(value) = line.strip_prefix("description:") {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
    }
    None
}

// ─── LlmReview Tool ──────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct LlmReviewInput {
    prompt: String,
    model: Option<String>,
}

/// Route a model name to its OpenAI-compatible reviewer endpoint and API key
/// env var. Returns (key_env, default_base_url, provider_tag).
/// The provider_tag lets us compare against `ARIS_REVIEWER_PROVIDER` to detect
/// mismatches (e.g. executor requested `gpt-5.5` but user configured `kimi`).
fn route_openai_compat_model(model: &str) -> (&'static str, &'static str, &'static str) {
    if model.contains("gemini") {
        ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini")
    } else if model.contains("glm") || model.contains("GLM") {
        ("GLM_API_KEY", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm")
    } else if model.starts_with("MiniMax") || model.starts_with("minimax") {
        ("MINIMAX_API_KEY", "https://api.minimax.chat/v1/chat/completions", "minimax")
    } else if model.contains("kimi") || model.contains("moonshot") {
        ("KIMI_API_KEY", "https://api.moonshot.cn/v1/chat/completions", "kimi")
    } else if model.contains("deepseek") {
        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek")
    } else {
        // Default: OpenAI (also covers gpt, o3, o4)
        ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "openai")
    }
}

/// True iff the given env var is set to a non-empty value.
fn env_non_empty(name: &str) -> bool {
    std::env::var(name).ok().filter(|k| !k.is_empty()).is_some()
}

/// Decide which model LlmReview should use for an OpenAI-compatible call.
///
/// The executor tool-call may specify a `model` override. Earlier versions of
/// ARIS always honored that override, which caused two failure modes when the
/// executor guessed wrong:
///
/// 1. The override routed to an API key env var that wasn't set (e.g. executor
///    specified `model="gpt-4o"` but the user configured Kimi as reviewer and
///    only `KIMI_API_KEY` is present).
/// 2. The override routed to a different provider than the user configured,
///    and — if that provider's key happened to be set for an unrelated reason —
///    the request silently hit the wrong reviewer.
///
/// v0.4.4 falls back to `configured_model` whenever the override is unusable
/// (key missing) or routes to a different provider than `configured_model`.
/// Provider consistency is derived from `configured_model` itself — we do NOT
/// read `ARIS_REVIEWER_PROVIDER` because `/reviewer <model>` updates the model
/// env var but leaves the provider env var stale, which would block legitimate
/// overrides (e.g. `/reviewer gpt-5.5` after `/setup Gemini`).
fn resolve_reviewer_model<'a>(
    input_model: Option<&'a str>,
    configured_model: &'a str,
) -> &'a str {
    let Some(requested) = input_model.filter(|s| !s.is_empty()) else {
        return configured_model;
    };

    if requested == configured_model {
        return requested;
    }

    let (requested_key_env, _, requested_provider) = route_openai_compat_model(requested);
    let (_, _, configured_provider) = route_openai_compat_model(configured_model);

    // Both must match: key available AND provider consistent with configured.
    if !env_non_empty(requested_key_env) || requested_provider != configured_provider {
        return configured_model;
    }

    requested
}

/// v0.4.17 (T11): the "double-no" guidance appended to every `LlmReview`
/// missing-credential error. A user who hits this has neither an MCP reviewer
/// nor an API reviewer configured; point them at both escape hatches. Carries
/// NO key value (the callers interpolate only the env var NAME, never its
/// contents).
const LLM_REVIEW_NO_CREDENTIAL_GUIDANCE: &str =
    " — configure mcpServers (ChatGPT subscription, see aris setup option 10) \
     or set an API reviewer via aris setup";

fn run_llm_review(input: LlmReviewInput) -> Result<String, String> {
    let env_reviewer_model = std::env::var("ARIS_REVIEWER_MODEL").ok().filter(|s| !s.is_empty());
    let configured_model = env_reviewer_model.as_deref().unwrap_or("gpt-5.5");

    // Check for user-configured reviewer provider and base URL
    let raw_reviewer_provider = std::env::var("ARIS_REVIEWER_PROVIDER")
        .ok()
        .filter(|s| !s.is_empty());
    // v0.4.17 (T10/P1.2): when the PRIMARY reviewer is Codex MCP, LlmReview is
    // only ever reached as the explicit fallback path. The effective HTTP
    // provider is therefore the configured fallback
    // (ARIS_REVIEWER_FALLBACK_PROVIDER), not "codex-mcp" (which has no HTTP
    // routing).
    //
    // v0.4.17 push-gate (BUG C) DELIBERATE FLIP: when no HTTP fallback is set we
    // previously fell through to the OpenAI-compat path, whose missing-key error
    // read "OPENAI_API_KEY not set (needed for model 'gpt-5.5')". For a user who
    // deliberately configured Codex MCP that is actively misleading — it names a
    // credential and model they never opted into. Return a clear, accurate error
    // instead: tell them to invoke `mcp__codex__codex` directly (LlmReview only
    // routes to HTTP API reviewers, and they have no HTTP fallback). The message
    // must NOT mention OPENAI_API_KEY or gpt-5.5.
    let reviewer_provider = if raw_reviewer_provider.as_deref() == Some("codex-mcp") {
        match std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER")
            .ok()
            .filter(|s| !s.is_empty())
        {
            Some(fallback) => Some(fallback),
            None => {
                return Err(
                    "LlmReview: Codex MCP is your configured reviewer — invoke the \
                     `mcp__codex__codex` tool directly instead of LlmReview. LlmReview only routes \
                     to HTTP API reviewers, and no HTTP fallback reviewer is configured. To add an \
                     HTTP fallback reviewer, run `aris setup`."
                        .to_string(),
                );
            }
        }
    } else {
        raw_reviewer_provider
    };
    let custom_base_url = std::env::var("ARIS_REVIEWER_BASE_URL").ok().filter(|s| !s.is_empty());

    // Custom OpenAI-compatible reviewer mode. Uses ARIS_REVIEWER_AUTH_TOKEN as
    // the API key and ARIS_REVIEWER_BASE_URL for the endpoint. Routes through
    // the same OpenAI-compat call path — no third routing path added.
    if reviewer_provider.as_deref() == Some("custom") {
        let key = std::env::var("ARIS_REVIEWER_AUTH_TOKEN")
            .ok()
            .filter(|k| !k.is_empty())
            .ok_or_else(|| {
                format!(
                    "LlmReview: ARIS_REVIEWER_AUTH_TOKEN not set (needed for custom reviewer){LLM_REVIEW_NO_CREDENTIAL_GUIDANCE}"
                )
            })?;
        // For Custom reviewer, refuse to fall back to gpt-5.5 — that would
        // silently send the user's request to the wrong model on their custom
        // proxy. Require explicit model from input or ARIS_REVIEWER_MODEL.
        let model = input
            .model
            .as_deref()
            .filter(|s| !s.is_empty())
            .or(env_reviewer_model.as_deref())
            .ok_or_else(|| {
                "LlmReview: custom reviewer has no model configured. \
                 Set ARIS_REVIEWER_MODEL or run /setup → reviewer → Custom and \
                 provide a model name."
                    .to_string()
            })?;
        let base = custom_base_url.ok_or_else(|| {
            format!(
                "LlmReview: ARIS_REVIEWER_BASE_URL not set (needed for custom reviewer){LLM_REVIEW_NO_CREDENTIAL_GUIDANCE}"
            )
        })?;
        let trimmed = base.trim_end_matches('/');
        let url = if trimmed.ends_with("/chat/completions") {
            trimmed.to_string()
        } else if trimmed.ends_with("/v1") {
            format!("{trimmed}/chat/completions")
        } else {
            format!("{trimmed}/v1/chat/completions")
        };
        return call_openai_compat_reviewer(&key, &url, model, &input.prompt);
    }

    // Anthropic-compatible reviewer mode (e.g., Claude via proxy, DeepSeek).
    // This path uses ARIS_REVIEWER_AUTH_TOKEN (Bearer) and ignores the openai-compat
    // key routing. We still honor an explicit input.model override here because
    // the target endpoint decides which Anthropic-format model name it accepts.
    if reviewer_provider.as_deref() == Some("anthropic-compat")
        || reviewer_provider.as_deref() == Some("deepseek")
    {
        let key = std::env::var("ARIS_REVIEWER_AUTH_TOKEN")
            .or_else(|_| std::env::var("ANTHROPIC_AUTH_TOKEN"))
            .ok()
            .filter(|k| !k.is_empty())
            .ok_or_else(|| {
                format!(
                    "LlmReview: ARIS_REVIEWER_AUTH_TOKEN not set (needed for anthropic-compat reviewer){LLM_REVIEW_NO_CREDENTIAL_GUIDANCE}"
                )
            })?;
        let model = input
            .model
            .as_deref()
            .filter(|s| !s.is_empty())
            .unwrap_or(configured_model);
        let default_base = if reviewer_provider.as_deref() == Some("deepseek") {
            "https://api.deepseek.com/anthropic"
        } else {
            "https://api.anthropic.com"
        };
        let base = custom_base_url.unwrap_or_else(|| default_base.to_string());
        let endpoint = format!("{}/v1/messages", base.trim_end_matches('/'));
        return call_anthropic_compat_reviewer(&key, &endpoint, model, &input.prompt);
    }

    // OpenAI-compat path: resolve model with fallback, then route to its endpoint.
    let _ = reviewer_provider; // kept for future use; resolution derives provider from model
    let model = resolve_reviewer_model(input.model.as_deref(), configured_model);
    let (key_env, default_base_url, _) = route_openai_compat_model(model);

    // Use custom base URL if provided, appending /chat/completions if needed
    let base_url = if let Some(ref custom) = custom_base_url {
        let trimmed = custom.trim_end_matches('/');
        if trimmed.ends_with("/chat/completions") {
            trimmed.to_string()
        } else if trimmed.ends_with("/v1") {
            format!("{trimmed}/chat/completions")
        } else {
            format!("{trimmed}/v1/chat/completions")
        }
    } else {
        default_base_url.to_string()
    };

    let key = std::env::var(key_env)
        .ok()
        .filter(|k| !k.is_empty())
        .ok_or_else(|| {
            format!(
                "LlmReview: {key_env} not set (needed for model '{model}'){LLM_REVIEW_NO_CREDENTIAL_GUIDANCE}"
            )
        })?;

    call_openai_compat_reviewer(&key, &base_url, model, &input.prompt)
}

/// Returns true if this reqwest error is a transient network-level failure
/// worth retrying (connection reset, timeout, DNS hiccup, etc.).
/// HTTP 4xx/5xx responses are NOT retried here — those come back as Ok(response).
fn is_transient_network_error(err: &reqwest::Error) -> bool {
    err.is_timeout() || err.is_connect() || err.is_request() || err.is_body()
}

/// Build a fresh blocking HTTP client. Each retry attempt gets its own pool
/// so we never reuse a broken TCP/TLS connection that caused the last failure.
fn fresh_reviewer_client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .pool_max_idle_per_host(0) // no connection pooling between calls
        .connect_timeout(std::time::Duration::from_secs(15))
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .unwrap_or_else(|_| reqwest::blocking::Client::new())
}

/// Format a reqwest error with its full source chain so we can see what actually failed
/// (DNS? TLS? connection reset?) instead of just "error sending request".
fn describe_reqwest_error(err: &reqwest::Error) -> String {
    let mut parts: Vec<String> = vec![err.to_string()];
    let mut src: Option<&(dyn std::error::Error + 'static)> = std::error::Error::source(err);
    let mut depth = 0;
    while let Some(s) = src {
        parts.push(format!("  caused by: {s}"));
        src = s.source();
        depth += 1;
        if depth > 6 {
            break;
        }
    }
    parts.join("\n")
}

/// Send a reviewer request with retry on transient network errors AND HTTP 429/5xx.
/// Up to 4 attempts total, exponential backoff (1s, 2s, 4s). Aborts early on Ctrl+C.
/// Respects Retry-After header when present.
fn send_reviewer_request_with_retry(
    build: impl Fn() -> reqwest::blocking::RequestBuilder,
) -> Result<reqwest::blocking::Response, String> {
    const MAX_ATTEMPTS: u32 = 4;
    let mut last_err: Option<String> = None;
    for attempt in 1..=MAX_ATTEMPTS {
        if runtime::is_interrupted() {
            runtime::clear_interrupt();
            return Err("LlmReview interrupted by user".to_string());
        }
        match build().send() {
            Ok(resp) => {
                let status = resp.status();
                if status.is_success() {
                    return Ok(resp);
                }
                let retryable = status.as_u16() == 429 || status.is_server_error();
                if !retryable || attempt == MAX_ATTEMPTS {
                    let body = resp.text().unwrap_or_default();
                    return Err(format!("LlmReview API error {status}: {body}"));
                }
                let retry_after = resp
                    .headers()
                    .get("retry-after")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|s| s.parse::<u64>().ok());
                let body = resp.text().unwrap_or_default();
                let preview: String = body.chars().take(160).collect();
                let backoff_ms = if let Some(secs) = retry_after {
                    (secs * 1000).min(10_000)
                } else {
                    (1u64 << (attempt - 1)) * 1000
                };
                eprintln!(
                    "\x1b[33m  LlmReview {status} (attempt {attempt}/{MAX_ATTEMPTS}), retrying in {backoff_ms}ms: {preview}\x1b[0m"
                );
                let deadline = std::time::Instant::now()
                    + std::time::Duration::from_millis(backoff_ms);
                while std::time::Instant::now() < deadline {
                    if runtime::is_interrupted() {
                        runtime::clear_interrupt();
                        return Err("LlmReview interrupted by user".to_string());
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }
            }
            Err(e) => {
                let transient = is_transient_network_error(&e);
                let detail = describe_reqwest_error(&e);
                last_err = Some(format!("LlmReview request failed: {detail}"));
                if !transient || attempt == MAX_ATTEMPTS {
                    break;
                }
                let backoff_ms: u64 = (1u64 << (attempt - 1)) * 1000;
                eprintln!(
                    "\x1b[33m  LlmReview transient error (attempt {attempt}/{MAX_ATTEMPTS}), retrying in {backoff_ms}ms:\n{detail}\x1b[0m"
                );
                let deadline = std::time::Instant::now()
                    + std::time::Duration::from_millis(backoff_ms);
                while std::time::Instant::now() < deadline {
                    if runtime::is_interrupted() {
                        runtime::clear_interrupt();
                        return Err("LlmReview interrupted by user".to_string());
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }
            }
        }
    }
    Err(last_err.unwrap_or_else(|| "LlmReview request failed: unknown".to_string()))
}

/// Whether this reviewer model accepts an OpenAI-style `reasoning_effort`
/// request field. Mirrors the allow-list in `aris-cli/openai_executor.rs`
/// so reviewer and executor agree on which models route through which API
/// shape.
///
/// v0.4.12 P1.B: uses [`reviewer_word_match`] so provider-prefixed names
/// (`openai/o3-mini`, `proxy:o4`) are recognised — `starts_with` was the
/// prior gate and missed those.
#[must_use]
fn reviewer_supports_reasoning_effort(model: &str) -> bool {
    let m = model.to_ascii_lowercase();
    reviewer_word_match(&m, "o1")
        || reviewer_word_match(&m, "o3")
        || reviewer_word_match(&m, "o4")
        || m.contains("gpt-5.5")
        || m.contains("gpt-5.6")
        || m.contains("reasoner")
        || m.contains("thinking")
}

/// v0.4.12 P1.B — word-boundary match (boundary = `-_/:` + start/end).
/// Mirrors `runtime::usage::has_word` and `openai_executor::word_match`
/// so reviewer capability detection stays consistent with executor +
/// pricing table.
///
/// v0.4.16 P7: forwards to the canonical [`runtime::word_match`] (this was one
/// of three verbatim copies; behavior is unchanged).
fn reviewer_word_match(haystack: &str, needle: &str) -> bool {
    runtime::word_match(haystack, needle)
}

/// Effort tier for reasoning-capable reviewer calls. Reads
/// `ARIS_REASONING_EFFORT` and falls back to `xhigh`.
#[must_use]
fn reviewer_reasoning_effort() -> String {
    std::env::var("ARIS_REASONING_EFFORT")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "xhigh".to_string())
}

fn call_anthropic_compat_reviewer(
    api_key: &str,
    endpoint: &str,
    model: &str,
    prompt: &str,
) -> Result<String, String> {
    let body = serde_json::json!({
        "model": model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}]
    });

    // Build a fresh client per request to avoid reusing a broken connection pool.
    let response = send_reviewer_request_with_retry(|| {
        fresh_reviewer_client()
            .post(endpoint)
            .bearer_auth(api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&body)
    })?;

    let json: serde_json::Value = response
        .json()
        .map_err(|e| format!("LlmReview response parse failed: {e}"))?;

    // Anthropic format: content[0].text
    json.get("content")
        .and_then(|c| c.get(0))
        .and_then(|b| b.get("text"))
        .and_then(|t| t.as_str())
        .map(ToOwned::to_owned)
        .ok_or_else(|| format!("LlmReview: unexpected response format: {json}"))
}

fn call_openai_compat_reviewer(
    api_key: &str,
    base_url: &str,
    model: &str,
    prompt: &str,
) -> Result<String, String> {
    let mut body = serde_json::json!({
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    });

    // Reasoning-capable models (o1/o3/o4 family, gpt-5.5+, thinking variants)
    // accept an explicit `reasoning_effort` field; older OpenAI-compat
    // models reject it, so gate on an allow-list. Default tier is `xhigh`,
    // overridable via `ARIS_REASONING_EFFORT`.
    if reviewer_supports_reasoning_effort(model) {
        body["reasoning_effort"] = serde_json::json!(reviewer_reasoning_effort());
    }

    // Build a fresh client per request to avoid reusing a broken connection pool.
    let response = send_reviewer_request_with_retry(|| {
        fresh_reviewer_client().post(base_url).bearer_auth(api_key).json(&body)
    })?;

    let json: serde_json::Value = response
        .json()
        .map_err(|e| format!("LlmReview response parse failed: {e}"))?;

    json.get("choices")
        .and_then(|c| c.get(0))
        .and_then(|c| c.get("message"))
        .and_then(|m| m.get("content"))
        .and_then(|c| c.as_str())
        .map(ToOwned::to_owned)
        .ok_or_else(|| format!("LlmReview: unexpected response format: {json}"))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;
    use std::fs;
    use std::io::{Read, Write};
    use std::net::{SocketAddr, TcpListener};
    use std::path::PathBuf;
    use std::sync::{Arc, Mutex, OnceLock};
    use std::thread;
    use std::time::Duration;

    use super::{
        agent_permission_policy, allowed_tools_for_subagent, build_agent_runtime,
        execute_agent_with_spawn, execute_tool, final_assistant_text, mvp_tool_specs,
        persist_agent_terminal_state, resolve_reviewer_model, reviewer_supports_reasoning_effort,
        route_openai_compat_model, AgentInput, AgentJob, AnthropicClient, SubagentToolExecutor,
    };
    use api::AuthSource;
    use runtime::{ApiRequest, AssistantEvent, ConversationRuntime, RuntimeError, Session};
    use serde_json::json;

    /// v0.4.23: web_fetch/web_search tests drive LOCAL mock servers through
    /// reqwest — a developer shell's http(s)_proxy routes 127.0.0.1 through
    /// the proxy and the tests fail (observed live). Scrub once per process.
    fn scrub_proxy_env() {
        static ONCE: std::sync::Once = std::sync::Once::new();
        ONCE.call_once(|| {
            for var in [
                "http_proxy",
                "https_proxy",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "all_proxy",
                "ALL_PROXY",
            ] {
                std::env::remove_var(var);
            }
            std::env::set_var("NO_PROXY", "127.0.0.1,localhost");
        });
    }

    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    fn temp_path(name: &str) -> PathBuf {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        std::env::temp_dir().join(format!("clawd-tools-{unique}-{name}"))
    }

    /// v0.4.17 (T11): when no reviewer credentials are set, the LlmReview error
    /// must guide the user toward BOTH escape hatches (Codex MCP via
    /// `aris setup option 10`, or an API reviewer via `aris setup`) and must
    /// NOT leak any key value. We force the missing-credential branch by
    /// clearing every reviewer env var while holding the env lock.
    #[test]
    fn llm_review_missing_key_error_guides_to_mcp_and_api_reviewer() {
        let _guard = env_lock().lock().unwrap_or_else(|p| p.into_inner());
        let reviewer_vars = [
            "ARIS_REVIEWER_MODEL",
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_BASE_URL",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "OPENAI_API_KEY",
        ];
        let saved: Vec<(&str, Option<String>)> = reviewer_vars
            .iter()
            .map(|k| (*k, std::env::var(k).ok()))
            .collect();
        for k in &reviewer_vars {
            std::env::remove_var(k);
        }

        let err = super::run_llm_review(super::LlmReviewInput {
            prompt: "review please".to_string(),
            model: None,
        })
        .expect_err("no creds => Err");

        // Default model gpt-5.5 routes to OPENAI_API_KEY (the var NAME may
        // appear; its value must not — we never set one).
        assert!(
            err.contains("OPENAI_API_KEY"),
            "error should name the missing key env var: {err}"
        );
        assert!(
            err.contains("aris setup option 10"),
            "error should point at the Codex MCP escape hatch: {err}"
        );
        assert!(
            err.contains("set an API reviewer via aris setup"),
            "error should point at the API-reviewer escape hatch: {err}"
        );
        assert!(
            err.contains("ChatGPT subscription"),
            "error should mention the no-API-key path: {err}"
        );

        for (k, v) in saved {
            match v {
                Some(val) => std::env::set_var(k, val),
                None => std::env::remove_var(k),
            }
        }
    }

    /// v0.4.17 (T10/P1.2): when the PRIMARY reviewer is Codex MCP and a
    /// fallback provider is set, LlmReview's EFFECTIVE provider is the fallback —
    /// NOT "codex-mcp". We prove this by setting the fallback to `custom` (whose
    /// path has a distinctive, network-free error: it requires
    /// ARIS_REVIEWER_AUTH_TOKEN before any HTTP call). If the effective provider
    /// were still "codex-mcp", that string has no LlmReview routing arm and we'd
    /// fall through to the OpenAI-compat path, producing a different error.
    #[test]
    fn llm_review_codex_mcp_with_fallback_routes_to_fallback_provider() {
        let _guard = env_lock().lock().unwrap_or_else(|p| p.into_inner());
        let vars = [
            "ARIS_REVIEWER_MODEL",
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_FALLBACK_PROVIDER",
            "ARIS_REVIEWER_BASE_URL",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "OPENAI_API_KEY",
        ];
        let saved: Vec<(&str, Option<String>)> =
            vars.iter().map(|k| (*k, std::env::var(k).ok())).collect();
        for k in &vars {
            std::env::remove_var(k);
        }
        std::env::set_var("ARIS_REVIEWER_PROVIDER", "codex-mcp");
        std::env::set_var("ARIS_REVIEWER_FALLBACK_PROVIDER", "custom");

        let err = super::run_llm_review(super::LlmReviewInput {
            prompt: "review please".to_string(),
            model: Some("some-model".to_string()),
        })
        .expect_err("custom fallback w/o auth token => Err");
        // The custom-reviewer arm's error names ARIS_REVIEWER_AUTH_TOKEN — proof
        // the effective provider resolved to `custom`, not `codex-mcp`.
        assert!(
            err.contains("ARIS_REVIEWER_AUTH_TOKEN") && err.contains("custom reviewer"),
            "codex-mcp + custom fallback must route through the custom-reviewer arm: {err}"
        );

        for (k, v) in saved {
            match v {
                Some(val) => std::env::set_var(k, val),
                None => std::env::remove_var(k),
            }
        }
    }

    /// v0.4.17 push-gate (BUG C) DELIBERATE FLIP: when the PRIMARY reviewer is
    /// Codex MCP and NO fallback is set, LlmReview previously fell through to the
    /// OpenAI-compat path, whose error named OPENAI_API_KEY + gpt-5.5 — actively
    /// misleading for a user who deliberately configured Codex MCP. It now
    /// returns a clear error that directs the model to `mcp__codex__codex` and
    /// must NOT mention OPENAI_API_KEY or gpt-5.5 (no phantom credential / model).
    #[test]
    fn llm_review_codex_mcp_without_fallback_directs_to_mcp_not_openai_key() {
        let _guard = env_lock().lock().unwrap_or_else(|p| p.into_inner());
        let vars = [
            "ARIS_REVIEWER_MODEL",
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_FALLBACK_PROVIDER",
            "ARIS_REVIEWER_BASE_URL",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "OPENAI_API_KEY",
        ];
        let saved: Vec<(&str, Option<String>)> =
            vars.iter().map(|k| (*k, std::env::var(k).ok())).collect();
        for k in &vars {
            std::env::remove_var(k);
        }
        std::env::set_var("ARIS_REVIEWER_PROVIDER", "codex-mcp");
        // No ARIS_REVIEWER_FALLBACK_PROVIDER set.

        let err = super::run_llm_review(super::LlmReviewInput {
            prompt: "review please".to_string(),
            model: None,
        })
        .expect_err("no fallback + codex-mcp primary => clear Err");
        // Clear, accurate guidance: use the Codex MCP channel directly.
        assert!(
            err.contains("mcp__codex__codex"),
            "no-fallback codex-mcp must direct the user to the Codex MCP tool: {err}"
        );
        // Must NOT name a credential or model the user never opted into.
        assert!(
            !err.contains("OPENAI_API_KEY") && !err.contains("gpt-5.5"),
            "no-fallback codex-mcp error must not mention OPENAI_API_KEY or gpt-5.5: {err}"
        );

        for (k, v) in saved {
            match v {
                Some(val) => std::env::set_var(k, val),
                None => std::env::remove_var(k),
            }
        }
    }

    #[test]
    fn exposes_mvp_tools() {
        let names = mvp_tool_specs()
            .into_iter()
            .map(|spec| spec.name)
            .collect::<Vec<_>>();
        assert!(names.contains(&"bash"));
        assert!(names.contains(&"read_file"));
        assert!(names.contains(&"WebFetch"));
        assert!(names.contains(&"WebSearch"));
        assert!(names.contains(&"TodoWrite"));
        assert!(names.contains(&"Skill"));
        assert!(names.contains(&"Agent"));
        assert!(names.contains(&"ToolSearch"));
        assert!(names.contains(&"NotebookEdit"));
        assert!(names.contains(&"Sleep"));
        assert!(names.contains(&"SendUserMessage"));
        assert!(names.contains(&"Config"));
        assert!(names.contains(&"StructuredOutput"));
        assert!(names.contains(&"REPL"));
        assert!(names.contains(&"PowerShell"));
    }

    #[test]
    fn rejects_unknown_tool_names() {
        let error = execute_tool("nope", &json!({})).expect_err("tool should be rejected");
        assert!(error.contains("unsupported tool"));
    }

    // ---------------------------------------------------------------
    // v0.4.17 Phase 0 — CHARACTERIZATION TESTS (tool directory truth)
    //
    // These lock the *current* (HEAD=81e5652) MVP tool catalogue so the
    // v0.4.17 MCP wiring (T1/T2/T3/T5/T6/RW5) can prove it only ADDS the
    // `mcp__` dispatch surface without disturbing the static catalogue.
    // ---------------------------------------------------------------

    /// Locks the EXACT count and ordered name list of `mvp_tool_specs()`.
    /// T1 (RuntimeToolSpec) must leave this static list byte-for-byte
    /// identical; any drift here is a deliberate catalogue change.
    #[test]
    fn char_mvp_tool_specs_exact_count_and_ordered_names() {
        let names: Vec<&str> = mvp_tool_specs().iter().map(|spec| spec.name).collect();
        assert_eq!(
            names,
            vec![
                "bash",
                "read_file",
                "write_file",
                "edit_file",
                "glob_search",
                "grep_search",
                "WebFetch",
                "WebSearch",
                "TodoWrite",
                "LlmReview",
                "Skill",
                "Agent",
                "ToolSearch",
                "NotebookEdit",
                "Sleep",
                "SendUserMessage",
                "Config",
                "StructuredOutput",
                "REPL",
                "PowerShell",
            ],
            "MVP tool catalogue name list / order changed"
        );
        assert_eq!(mvp_tool_specs().len(), 20, "MVP tool count changed");
    }

    /// Every ToolSpec's `input_schema` serializes to a JSON object (the
    /// invariant T2's `mcp_tool_specs` net-min-schema must preserve for MCP
    /// tools, and that provider request construction relies on).
    #[test]
    fn char_every_input_schema_serializes_to_json_object() {
        for spec in mvp_tool_specs() {
            let serialized = serde_json::to_value(&spec.input_schema)
                .unwrap_or_else(|e| panic!("schema for {} must serialize: {e}", spec.name));
            assert!(
                serialized.is_object(),
                "input_schema for {} is not a JSON object",
                spec.name
            );
            assert_eq!(
                serialized["type"], "object",
                "input_schema top-level `type` for {} is not \"object\"",
                spec.name
            );
        }
    }

    /// Representative deep-snapshot #1 — `bash`: name + description keyword
    /// + schema top-level keys + the `command` required field.
    #[test]
    fn char_bash_spec_shape() {
        let spec = mvp_tool_specs()
            .into_iter()
            .find(|s| s.name == "bash")
            .expect("bash spec present");
        assert_eq!(spec.name, "bash");
        assert!(
            spec.description.contains("shell command"),
            "bash description drifted: {}",
            spec.description
        );
        let schema = spec.input_schema.as_object().expect("bash schema object");
        let mut top_keys: Vec<&str> = schema.keys().map(String::as_str).collect();
        top_keys.sort_unstable();
        assert_eq!(
            top_keys,
            vec!["additionalProperties", "properties", "required", "type"],
            "bash schema top-level keys drifted"
        );
        assert_eq!(spec.input_schema["required"], json!(["command"]));
        assert_eq!(spec.input_schema["additionalProperties"], json!(false));
        assert_eq!(spec.required_permission, super::PermissionMode::DangerFullAccess);
    }

    /// Representative deep-snapshot #2 — `read_file`: the canonical
    /// read-only file tool.
    #[test]
    fn char_read_file_spec_shape() {
        let spec = mvp_tool_specs()
            .into_iter()
            .find(|s| s.name == "read_file")
            .expect("read_file spec present");
        assert_eq!(spec.name, "read_file");
        assert!(
            spec.description.contains("Read a text file"),
            "read_file description drifted: {}",
            spec.description
        );
        let schema = spec
            .input_schema
            .as_object()
            .expect("read_file schema object");
        let mut top_keys: Vec<&str> = schema.keys().map(String::as_str).collect();
        top_keys.sort_unstable();
        assert_eq!(
            top_keys,
            vec!["additionalProperties", "properties", "required", "type"],
            "read_file schema top-level keys drifted"
        );
        assert_eq!(spec.input_schema["required"], json!(["path"]));
        assert_eq!(spec.required_permission, super::PermissionMode::ReadOnly);
    }

    /// Representative deep-snapshot #3 — `Agent`: the subagent-spawning
    /// tool. T6 keeps subagents OFF the MCP path, so locking Agent's shape
    /// here pins the surface that test must reason about.
    #[test]
    fn char_agent_spec_shape() {
        let spec = mvp_tool_specs()
            .into_iter()
            .find(|s| s.name == "Agent")
            .expect("Agent spec present");
        assert_eq!(spec.name, "Agent");
        assert!(
            spec.description.contains("agent"),
            "Agent description drifted: {}",
            spec.description
        );
        let schema = spec.input_schema.as_object().expect("Agent schema object");
        let mut top_keys: Vec<&str> = schema.keys().map(String::as_str).collect();
        top_keys.sort_unstable();
        assert_eq!(
            top_keys,
            vec!["additionalProperties", "properties", "required", "type"],
            "Agent schema top-level keys drifted"
        );
        assert_eq!(spec.input_schema["required"], json!(["description", "prompt"]));
        assert_eq!(spec.required_permission, super::PermissionMode::DangerFullAccess);
    }

    /// BASELINE for T3/T6: an `mcp__`-prefixed name routed through the
    /// static `execute_tool` match today returns the `unsupported tool`
    /// error verbatim. v0.4.17 T3 intercepts MCP names ABOVE this layer
    /// (in `CliToolExecutor::execute`), so `execute_tool` itself must keep
    /// returning unsupported — that is the structural guarantee subagents
    /// never reach MCP. Locking the exact message form is load-bearing.
    #[test]
    fn char_execute_tool_mcp_prefixed_name_is_unsupported() {
        let err = execute_tool("mcp__fake__tool", &json!({}))
            .expect_err("mcp-prefixed name must be unsupported at the static layer");
        assert_eq!(err, "unsupported tool: mcp__fake__tool");
    }

    /// BASELINE for T3/T6 (companion): a plain unknown name also returns the
    /// same `unsupported tool: <name>` form. Locks the precise message shape
    /// (prefix + interpolated name) so the v0.4.17 changes are provably
    /// scoped to MCP-prefixed names only.
    #[test]
    fn char_execute_tool_unknown_name_message_form() {
        let err = execute_tool("nonexistent", &json!({}))
            .expect_err("unknown tool must be unsupported");
        assert_eq!(err, "unsupported tool: nonexistent");
    }

    // ── v0.4.17 C1 (T1/T2): RuntimeToolSpec + mcp_tool_specs ────────────────

    fn managed_tool(
        server: &str,
        raw_name: &str,
        schema: Option<serde_json::Value>,
    ) -> runtime::ManagedMcpTool {
        runtime::ManagedMcpTool {
            server_name: server.to_string(),
            qualified_name: runtime::mcp_tool_name(server, raw_name),
            raw_name: raw_name.to_string(),
            tool: runtime::McpTool {
                name: raw_name.to_string(),
                description: Some(format!("desc for {raw_name}")),
                input_schema: schema,
                annotations: None,
                meta: None,
            },
        }
    }

    /// T1: converting every static ToolSpec into a RuntimeToolSpec is lossless
    /// for the request payload — the resulting ToolDefinition serializes
    /// byte-for-byte identically to the previous inline construction.
    #[test]
    fn runtime_tool_spec_conversion_matches_legacy_tool_definition_bytes() {
        for spec in mvp_tool_specs() {
            // Legacy inline construction (pre-T1).
            let legacy = api::ToolDefinition {
                name: spec.name.to_string(),
                description: Some(spec.description.to_string()),
                input_schema: spec.input_schema.clone(),
            };
            // New path: through RuntimeToolSpec.
            let runtime_spec = super::RuntimeToolSpec::from(&spec);
            let migrated = api::ToolDefinition {
                name: runtime_spec.name,
                description: Some(runtime_spec.description),
                input_schema: runtime_spec.input_schema,
            };
            let legacy_bytes = serde_json::to_string(&legacy).expect("legacy serializes");
            let migrated_bytes = serde_json::to_string(&migrated).expect("migrated serializes");
            assert_eq!(
                legacy_bytes, migrated_bytes,
                "RuntimeToolSpec conversion changed the serialized ToolDefinition for {}",
                spec.name
            );
        }
    }

    /// T2: a normal discovered tool becomes one advertised spec whose name is
    /// the qualified name and whose route maps back to that same qualified name,
    /// carrying the raw server identity (P2.2).
    #[test]
    fn mcp_tool_specs_basic_conversion_and_route() {
        let tools = vec![managed_tool(
            "codex",
            "codex",
            Some(json!({"type": "object", "properties": {"prompt": {"type": "string"}}})),
        )];
        let catalog = super::mcp_tool_specs(&tools);
        assert_eq!(catalog.len(), 1);
        let spec = &catalog.specs()[0];
        assert_eq!(spec.name, "mcp__codex__codex");
        assert_eq!(spec.description, "desc for codex");
        assert_eq!(spec.input_schema["type"], "object");
        let route = catalog
            .route_for_advertised_name("mcp__codex__codex")
            .expect("advertised tool routes");
        assert_eq!(route.qualified_name, "mcp__codex__codex");
        assert_eq!(route.server_name, "codex");
        assert_eq!(catalog.route_for_advertised_name("mcp__codex__nope"), None);
    }

    /// v0.4.17 (T10/P1.3): `has_server` matches against the route's raw
    /// `server_name` (not the advertised/qualified name), so the inline-`/setup`
    /// restart notice can tell whether the live catalog already advertises the
    /// `codex` server's tools. Empty catalog ⇒ false; a catalog with `codex`
    /// tools ⇒ true for "codex" and false for an unrelated name.
    #[test]
    fn catalog_has_server_matches_raw_server_name() {
        let empty = super::McpToolCatalog::default();
        assert!(!empty.has_server("codex"));

        let tools = vec![
            managed_tool("codex", "codex", None),
            managed_tool("other", "thing", None),
        ];
        let catalog = super::mcp_tool_specs(&tools);
        assert!(catalog.has_server("codex"));
        assert!(catalog.has_server("other"));
        assert!(!catalog.has_server("nonexistent"));
    }

    /// T2 collision strategy (**last-wins**, matching the runtime tool_index):
    /// two tools that normalize to the SAME qualified name cannot both be
    /// advertised. The runtime's `tool_index.insert` is last-writer-wins
    /// (mcp_stdio.rs), so the manager's `call_tool` resolves a colliding name to
    /// the LAST-discovered tool's route. The catalog therefore MUST also keep
    /// the last — both the catalog and the manager consume the SAME
    /// `Vec<ManagedMcpTool>` order, so taking the last on collision is
    /// naturally consistent: the advertised description / schema / route's
    /// server_name all describe exactly the tool that will be executed. Locks:
    /// len == 1; the survivor's metadata equals the LAST input's; the FIRST
    /// input's metadata is absent.
    #[test]
    fn mcp_tool_specs_collision_last_wins_matching_runtime_index() {
        // Two tools from DIFFERENT raw servers that both normalize to the same
        // qualified name (manager's tool_index would overwrite first with
        // second), with DISTINCT description + schema + server_name so we can
        // prove which one survives.
        let tools = vec![
            // FIRST: server "a b", raw "do it"  -> mcp__a_b__do_it
            managed_tool("a b", "do it", Some(json!({"type": "object", "first": true}))),
            // LAST:  server "a_b", raw "do_it"  -> mcp__a_b__do_it (collision)
            managed_tool("a_b", "do_it", Some(json!({"type": "object", "last": true}))),
        ];
        assert_eq!(tools[0].qualified_name, tools[1].qualified_name);
        // Sanity: the two inputs really do carry different metadata.
        assert_ne!(tools[0].tool.description, tools[1].tool.description);
        assert_ne!(tools[0].server_name, tools[1].server_name);

        let catalog = super::mcp_tool_specs(&tools);

        // Exactly one advertised tool (no duplicate name, no `_2` suffix).
        let names: Vec<&str> = catalog.specs().iter().map(|s| s.name.as_str()).collect();
        assert_eq!(names, vec!["mcp__a_b__do_it"]);
        assert_eq!(catalog.len(), 1);

        // The survivor's spec carries the LAST input's description + schema.
        let spec = &catalog.specs()[0];
        assert_eq!(spec.description, "desc for do_it");
        assert_eq!(spec.input_schema, json!({"type": "object", "last": true}));

        // The survivor's route carries the LAST input's raw server identity —
        // this MUST equal the manager's `call_tool` target so C2's per-server
        // approval/trust acts on the tool that actually executes.
        let route = catalog
            .route_for_advertised_name("mcp__a_b__do_it")
            .expect("the survivor routes");
        assert_eq!(route.qualified_name, "mcp__a_b__do_it");
        assert_eq!(route.server_name, "a_b");

        // The FIRST input's metadata is GONE: its description, its schema, and
        // its raw server_name ("a b") no longer appear anywhere in the catalog.
        assert_ne!(spec.description, "desc for do it");
        assert_ne!(spec.input_schema, json!({"type": "object", "first": true}));
        assert_ne!(route.server_name, "a b");
    }

    /// P2.2: routes carry the RAW server name (not derivable from the
    /// advertised/qualified name once two raw server names normalize to the same
    /// prefix). Lock that the raw server identity is passed through verbatim so
    /// C2's per-server approval/trust can recover it.
    #[test]
    fn mcp_tool_specs_route_preserves_raw_server_identity() {
        // A raw server name with a space normalizes for the qualified prefix but
        // must survive untouched in the route's `server_name`.
        let tools = vec![managed_tool(
            "my server",
            "act",
            Some(json!({"type": "object"})),
        )];
        let catalog = super::mcp_tool_specs(&tools);
        let advertised = catalog.specs()[0].name.clone();
        let route = catalog
            .route_for_advertised_name(&advertised)
            .expect("advertised tool routes");
        assert_eq!(route.server_name, "my server");
        assert_eq!(route.qualified_name, advertised);
    }

    /// T2 schema sanitization: a missing schema and a non-object schema both
    /// become the minimal `{"type":"object"}` net; an object schema passes
    /// through unchanged.
    #[test]
    fn mcp_tool_specs_sanitizes_input_schema() {
        let tools = vec![
            managed_tool("srv", "no_schema", None),
            managed_tool("srv", "array_schema", Some(json!(["not", "an", "object"]))),
            managed_tool(
                "srv",
                "object_schema",
                Some(json!({"type": "object", "properties": {"x": {"type": "number"}}})),
            ),
        ];
        let catalog = super::mcp_tool_specs(&tools);
        let specs = catalog.specs();

        assert_eq!(specs[0].input_schema, json!({"type": "object"}));
        assert_eq!(specs[1].input_schema, json!({"type": "object"}));
        assert_eq!(
            specs[2].input_schema,
            json!({"type": "object", "properties": {"x": {"type": "number"}}})
        );
    }

    /// T2: a tool with no description (or an empty one) gets a synthesized,
    /// non-empty hint rather than a blank string.
    #[test]
    fn mcp_tool_specs_synthesizes_missing_description() {
        let mut tool = managed_tool("srv", "thing", Some(json!({"type": "object"})));
        tool.tool.description = None;
        let catalog = super::mcp_tool_specs(std::slice::from_ref(&tool));
        let desc = &catalog.specs()[0].description;
        assert!(
            desc.contains("mcp__srv__thing") && desc.contains("srv"),
            "synthesized description should reference tool + server: {desc}"
        );

        tool.tool.description = Some(String::new());
        let catalog = super::mcp_tool_specs(std::slice::from_ref(&tool));
        assert!(!catalog.specs()[0].description.is_empty());
    }

    /// v0.4.17 (T6): pin the structural guarantee that a SUB-AGENT's tool
    /// directory never contains an `mcp__`-prefixed name. `SubagentToolExecutor`
    /// derives its catalogue from `tool_specs_for_allowed_tools`, which is built
    /// only from the static `mvp_tool_specs()`. Even when the user's main
    /// session has `mcpServers` configured (which would add `mcp__*` names to
    /// the MAIN session's `McpToolCatalog`), that catalog never reaches a
    /// sub-agent — the sub-agent has no `SharedMcpRuntime`. Here we assert the
    /// directory unconditionally (with and without an allowlist) so any future
    /// change that tried to thread MCP into the subagent path would break this
    /// pin. MCP-for-subagents is re-considered with P8 in v0.4.18 (plan.md T6).
    #[test]
    fn subagent_tool_directory_never_contains_mcp_names() {
        // No allowlist: the full static catalogue, never any mcp__ name.
        let full = super::tool_specs_for_allowed_tools(None);
        assert!(
            !full.is_empty(),
            "static catalogue must be non-empty (guards against vacuous pass)"
        );
        assert!(
            full.iter().all(|spec| !spec.name.starts_with("mcp__")),
            "subagent tool directory must never contain an mcp__ tool"
        );

        // Even if a caller hand-builds an allowlist that NAMES an mcp__ tool,
        // the filter only ever yields static specs (the mcp__ name matches
        // nothing in mvp_tool_specs and is dropped). This mirrors the main
        // session's filter-layer behavior but here it is the only layer.
        let mut allow: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
        allow.insert("read_file".to_string());
        allow.insert("mcp__codex__codex".to_string());
        let filtered = super::tool_specs_for_allowed_tools(Some(&allow));
        assert!(
            filtered.iter().all(|spec| !spec.name.starts_with("mcp__")),
            "an mcp__ name in a subagent allowlist must not surface an MCP tool"
        );
        assert!(
            filtered.iter().any(|spec| spec.name == "read_file"),
            "static names in the allowlist still resolve"
        );
    }

    #[test]
    fn web_fetch_returns_prompt_aware_summary() {
        scrub_proxy_env();
        let server = TestServer::spawn(Arc::new(|request_line: &str| {
            assert!(request_line.starts_with("GET /page "));
            HttpResponse::html(
                200,
                "OK",
                "<html><head><title>Ignored</title></head><body><h1>Test Page</h1><p>Hello <b>world</b> from local server.</p></body></html>",
            )
        }));

        let result = execute_tool(
            "WebFetch",
            &json!({
                "url": format!("http://{}/page", server.addr()),
                "prompt": "Summarize this page"
            }),
        )
        .expect("WebFetch should succeed");

        let output: serde_json::Value = serde_json::from_str(&result).expect("valid json");
        assert_eq!(output["code"], 200);
        let summary = output["result"].as_str().expect("result string");
        assert!(summary.contains("Fetched"));
        assert!(summary.contains("Test Page"));
        assert!(summary.contains("Hello world from local server"));

        let titled = execute_tool(
            "WebFetch",
            &json!({
                "url": format!("http://{}/page", server.addr()),
                "prompt": "What is the page title?"
            }),
        )
        .expect("WebFetch title query should succeed");
        let titled_output: serde_json::Value = serde_json::from_str(&titled).expect("valid json");
        let titled_summary = titled_output["result"].as_str().expect("result string");
        assert!(titled_summary.contains("Title: Ignored"));
    }

    #[test]
    fn web_fetch_supports_plain_text_and_rejects_invalid_url() {
        scrub_proxy_env();
        let server = TestServer::spawn(Arc::new(|request_line: &str| {
            assert!(request_line.starts_with("GET /plain "));
            HttpResponse::text(200, "OK", "plain text response")
        }));

        let result = execute_tool(
            "WebFetch",
            &json!({
                "url": format!("http://{}/plain", server.addr()),
                "prompt": "Show me the content"
            }),
        )
        .expect("WebFetch should succeed for text content");

        let output: serde_json::Value = serde_json::from_str(&result).expect("valid json");
        assert_eq!(output["url"], format!("http://{}/plain", server.addr()));
        assert!(output["result"]
            .as_str()
            .expect("result")
            .contains("plain text response"));

        let error = execute_tool(
            "WebFetch",
            &json!({
                "url": "not a url",
                "prompt": "Summarize"
            }),
        )
        .expect_err("invalid URL should fail");
        assert!(error.contains("relative URL without a base") || error.contains("invalid"));
    }

    #[test]
    fn web_search_extracts_and_filters_results() {
        scrub_proxy_env();
        let server = TestServer::spawn(Arc::new(|request_line: &str| {
            assert!(request_line.contains("GET /search?q=rust+web+search "));
            HttpResponse::html(
                200,
                "OK",
                r#"
                <html><body>
                  <a class="result__a" href="https://docs.rs/reqwest">Reqwest docs</a>
                  <a class="result__a" href="https://example.com/blocked">Blocked result</a>
                </body></html>
                "#,
            )
        }));

        std::env::set_var(
            "CLAWD_WEB_SEARCH_BASE_URL",
            format!("http://{}/search", server.addr()),
        );
        let result = execute_tool(
            "WebSearch",
            &json!({
                "query": "rust web search",
                "allowed_domains": ["https://DOCS.rs/"],
                "blocked_domains": ["HTTPS://EXAMPLE.COM"]
            }),
        )
        .expect("WebSearch should succeed");
        std::env::remove_var("CLAWD_WEB_SEARCH_BASE_URL");

        let output: serde_json::Value = serde_json::from_str(&result).expect("valid json");
        assert_eq!(output["query"], "rust web search");
        let results = output["results"].as_array().expect("results array");
        let search_result = results
            .iter()
            .find(|item| item.get("content").is_some())
            .expect("search result block present");
        let content = search_result["content"].as_array().expect("content array");
        assert_eq!(content.len(), 1);
        assert_eq!(content[0]["title"], "Reqwest docs");
        assert_eq!(content[0]["url"], "https://docs.rs/reqwest");
    }

    #[test]
    fn web_search_handles_generic_links_and_invalid_base_url() {
        scrub_proxy_env();
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let server = TestServer::spawn(Arc::new(|request_line: &str| {
            assert!(request_line.contains("GET /fallback?q=generic+links "));
            HttpResponse::html(
                200,
                "OK",
                r#"
                <html><body>
                  <a href="https://example.com/one">Example One</a>
                  <a href="https://example.com/one">Duplicate Example One</a>
                  <a href="https://docs.rs/tokio">Tokio Docs</a>
                </body></html>
                "#,
            )
        }));

        std::env::set_var(
            "CLAWD_WEB_SEARCH_BASE_URL",
            format!("http://{}/fallback", server.addr()),
        );
        let result = execute_tool(
            "WebSearch",
            &json!({
                "query": "generic links"
            }),
        )
        .expect("WebSearch fallback parsing should succeed");
        std::env::remove_var("CLAWD_WEB_SEARCH_BASE_URL");

        let output: serde_json::Value = serde_json::from_str(&result).expect("valid json");
        let results = output["results"].as_array().expect("results array");
        let search_result = results
            .iter()
            .find(|item| item.get("content").is_some())
            .expect("search result block present");
        let content = search_result["content"].as_array().expect("content array");
        assert_eq!(content.len(), 2);
        assert_eq!(content[0]["url"], "https://example.com/one");
        assert_eq!(content[1]["url"], "https://docs.rs/tokio");

        std::env::set_var("CLAWD_WEB_SEARCH_BASE_URL", "://bad-base-url");
        let error = execute_tool("WebSearch", &json!({ "query": "generic links" }))
            .expect_err("invalid base URL should fail");
        std::env::remove_var("CLAWD_WEB_SEARCH_BASE_URL");
        assert!(error.contains("relative URL without a base") || error.contains("empty host"));
    }

    #[test]
    fn todo_write_persists_and_returns_previous_state() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let path = temp_path("todos.json");
        std::env::set_var("CLAWD_TODO_STORE", &path);

        let first = execute_tool(
            "TodoWrite",
            &json!({
                "todos": [
                    {"content": "Add tool", "activeForm": "Adding tool", "status": "in_progress"},
                    {"content": "Run tests", "activeForm": "Running tests", "status": "pending"}
                ]
            }),
        )
        .expect("TodoWrite should succeed");
        let first_output: serde_json::Value = serde_json::from_str(&first).expect("valid json");
        assert_eq!(first_output["oldTodos"].as_array().expect("array").len(), 0);

        let second = execute_tool(
            "TodoWrite",
            &json!({
                "todos": [
                    {"content": "Add tool", "activeForm": "Adding tool", "status": "completed"},
                    {"content": "Run tests", "activeForm": "Running tests", "status": "completed"},
                    {"content": "Verify", "activeForm": "Verifying", "status": "completed"}
                ]
            }),
        )
        .expect("TodoWrite should succeed");
        std::env::remove_var("CLAWD_TODO_STORE");
        let _ = std::fs::remove_file(path);

        let second_output: serde_json::Value = serde_json::from_str(&second).expect("valid json");
        assert_eq!(
            second_output["oldTodos"].as_array().expect("array").len(),
            2
        );
        assert_eq!(
            second_output["newTodos"].as_array().expect("array").len(),
            3
        );
        assert!(second_output["verificationNudgeNeeded"].is_null());
    }

    #[test]
    fn todo_write_rejects_invalid_payloads_and_sets_verification_nudge() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let path = temp_path("todos-errors.json");
        std::env::set_var("CLAWD_TODO_STORE", &path);

        let empty = execute_tool("TodoWrite", &json!({ "todos": [] }))
            .expect_err("empty todos should fail");
        assert!(empty.contains("todos must not be empty"));

        // Multiple in_progress items are now allowed for parallel workflows
        let _multi_active = execute_tool(
            "TodoWrite",
            &json!({
                "todos": [
                    {"content": "One", "activeForm": "Doing one", "status": "in_progress"},
                    {"content": "Two", "activeForm": "Doing two", "status": "in_progress"}
                ]
            }),
        )
        .expect("multiple in-progress todos should succeed");

        let blank_content = execute_tool(
            "TodoWrite",
            &json!({
                "todos": [
                    {"content": "   ", "activeForm": "Doing it", "status": "pending"}
                ]
            }),
        )
        .expect_err("blank content should fail");
        assert!(blank_content.contains("todo content must not be empty"));

        let nudge = execute_tool(
            "TodoWrite",
            &json!({
                "todos": [
                    {"content": "Write tests", "activeForm": "Writing tests", "status": "completed"},
                    {"content": "Fix errors", "activeForm": "Fixing errors", "status": "completed"},
                    {"content": "Ship branch", "activeForm": "Shipping branch", "status": "completed"}
                ]
            }),
        )
        .expect("completed todos should succeed");
        std::env::remove_var("CLAWD_TODO_STORE");
        let _ = fs::remove_file(path);

        let output: serde_json::Value = serde_json::from_str(&nudge).expect("valid json");
        assert_eq!(output["verificationNudgeNeeded"], true);
    }

    #[test]
    fn skill_loads_local_skill_prompt() {
        // Create a temporary skill directory
        let tmp = std::env::temp_dir().join(format!("aris-skill-test-{}", std::process::id()));
        let skill_dir = tmp.join("test-skill");
        fs::create_dir_all(&skill_dir).expect("create skill dir");
        fs::write(
            skill_dir.join("SKILL.md"),
            "---\nname: test-skill\ndescription: \"A test skill\"\n---\n\n# Test Skill\n\nThis is a test skill prompt.",
        )
        .expect("write SKILL.md");

        // Point HOME to temp dir so ~/.claude/skills/ resolves there
        let _guard = env_lock();
        let original_home = std::env::var("HOME").ok();
        let claude_skills = tmp.parent().unwrap().join("claude-home").join(".claude").join("skills");
        fs::create_dir_all(&claude_skills).expect("create claude skills dir");
        // Copy the skill into the claude skills dir
        let target_skill = claude_skills.join("test-skill");
        fs::create_dir_all(&target_skill).expect("create target skill dir");
        fs::copy(skill_dir.join("SKILL.md"), target_skill.join("SKILL.md")).expect("copy skill");
        std::env::set_var("HOME", claude_skills.parent().unwrap().parent().unwrap());

        let result = execute_tool(
            "Skill",
            &json!({
                "skill": "test-skill",
                "args": "overview"
            }),
        )
        .expect("Skill should succeed");

        let output: serde_json::Value = serde_json::from_str(&result).expect("valid json");
        assert_eq!(output["skill"], "test-skill");
        assert!(output["path"]
            .as_str()
            .expect("path")
            .ends_with("/test-skill/SKILL.md"));
        assert!(output["prompt"]
            .as_str()
            .expect("prompt")
            .contains("This is a test skill prompt"));

        // Test $skill form
        let dollar_result = execute_tool(
            "Skill",
            &json!({
                "skill": "$test-skill"
            }),
        )
        .expect("Skill should accept $skill invocation form");
        let dollar_output: serde_json::Value =
            serde_json::from_str(&dollar_result).expect("valid json");
        assert_eq!(dollar_output["skill"], "$test-skill");
        assert!(dollar_output["path"]
            .as_str()
            .expect("path")
            .ends_with("/test-skill/SKILL.md"));

        // Cleanup
        if let Some(home) = original_home {
            std::env::set_var("HOME", home);
        }
        let _ = fs::remove_dir_all(&tmp);
        let _ = fs::remove_dir_all(claude_skills.parent().unwrap().parent().unwrap());
    }

    #[test]
    fn tool_search_supports_keyword_and_select_queries() {
        let keyword = execute_tool(
            "ToolSearch",
            &json!({"query": "web current", "max_results": 3}),
        )
        .expect("ToolSearch should succeed");
        let keyword_output: serde_json::Value = serde_json::from_str(&keyword).expect("valid json");
        let matches = keyword_output["matches"].as_array().expect("matches");
        assert!(matches.iter().any(|value| value == "WebSearch"));

        let selected = execute_tool("ToolSearch", &json!({"query": "select:Agent,Skill"}))
            .expect("ToolSearch should succeed");
        let selected_output: serde_json::Value =
            serde_json::from_str(&selected).expect("valid json");
        assert_eq!(selected_output["matches"][0], "Agent");
        assert_eq!(selected_output["matches"][1], "Skill");

        let aliased = execute_tool("ToolSearch", &json!({"query": "AgentTool"}))
            .expect("ToolSearch should support tool aliases");
        let aliased_output: serde_json::Value = serde_json::from_str(&aliased).expect("valid json");
        assert_eq!(aliased_output["matches"][0], "Agent");
        assert_eq!(aliased_output["normalized_query"], "agent");

        let selected_with_alias =
            execute_tool("ToolSearch", &json!({"query": "select:AgentTool,Skill"}))
                .expect("ToolSearch alias select should succeed");
        let selected_with_alias_output: serde_json::Value =
            serde_json::from_str(&selected_with_alias).expect("valid json");
        assert_eq!(selected_with_alias_output["matches"][0], "Agent");
        assert_eq!(selected_with_alias_output["matches"][1], "Skill");
    }

    #[test]
    fn agent_persists_handoff_metadata() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let dir = temp_path("agent-store");
        std::env::set_var("CLAWD_AGENT_STORE", &dir);
        let captured = Arc::new(Mutex::new(None::<AgentJob>));
        let captured_for_spawn = Arc::clone(&captured);

        let manifest = execute_agent_with_spawn(
            AgentInput {
                description: "Audit the branch".to_string(),
                prompt: "Check tests and outstanding work.".to_string(),
                subagent_type: Some("Explore".to_string()),
                name: Some("ship-audit".to_string()),
                model: None,
            },
            move |job| {
                *captured_for_spawn
                    .lock()
                    .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(job);
                Ok(())
            },
        )
        .expect("Agent should succeed");
        std::env::remove_var("CLAWD_AGENT_STORE");

        assert_eq!(manifest.name, "ship-audit");
        assert_eq!(manifest.subagent_type.as_deref(), Some("Explore"));
        assert_eq!(manifest.status, "running");
        assert!(!manifest.created_at.is_empty());
        assert!(manifest.started_at.is_some());
        assert!(manifest.completed_at.is_none());
        let contents = std::fs::read_to_string(&manifest.output_file).expect("agent file exists");
        let manifest_contents =
            std::fs::read_to_string(&manifest.manifest_file).expect("manifest file exists");
        assert!(contents.contains("Audit the branch"));
        assert!(contents.contains("Check tests and outstanding work."));
        assert!(manifest_contents.contains("\"subagentType\": \"Explore\""));
        assert!(manifest_contents.contains("\"status\": \"running\""));
        let captured_job = captured
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
            .expect("spawn job should be captured");
        assert_eq!(captured_job.prompt, "Check tests and outstanding work.");
        assert!(captured_job.allowed_tools.contains("read_file"));
        assert!(!captured_job.allowed_tools.contains("Agent"));

        let normalized = execute_tool(
            "Agent",
            &json!({
                "description": "Verify the branch",
                "prompt": "Check tests.",
                "subagent_type": "explorer"
            }),
        )
        .expect("Agent should normalize built-in aliases");
        let normalized_output: serde_json::Value =
            serde_json::from_str(&normalized).expect("valid json");
        assert_eq!(normalized_output["subagentType"], "Explore");

        let named = execute_tool(
            "Agent",
            &json!({
                "description": "Review the branch",
                "prompt": "Inspect diff.",
                "name": "Ship Audit!!!"
            }),
        )
        .expect("Agent should normalize explicit names");
        let named_output: serde_json::Value = serde_json::from_str(&named).expect("valid json");
        assert_eq!(named_output["name"], "ship-audit");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_fake_runner_can_persist_completion_and_failure() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let dir = temp_path("agent-runner");
        std::env::set_var("CLAWD_AGENT_STORE", &dir);

        let completed = execute_agent_with_spawn(
            AgentInput {
                description: "Complete the task".to_string(),
                prompt: "Do the work".to_string(),
                subagent_type: Some("Explore".to_string()),
                name: Some("complete-task".to_string()),
                model: Some("claude-sonnet-4-6".to_string()),
            },
            |job| {
                persist_agent_terminal_state(
                    &job.manifest,
                    "completed",
                    Some("Finished successfully"),
                    None,
                )
            },
        )
        .expect("completed agent should succeed");

        let completed_manifest = std::fs::read_to_string(&completed.manifest_file)
            .expect("completed manifest should exist");
        let completed_output =
            std::fs::read_to_string(&completed.output_file).expect("completed output should exist");
        assert!(completed_manifest.contains("\"status\": \"completed\""));
        assert!(completed_output.contains("Finished successfully"));

        let failed = execute_agent_with_spawn(
            AgentInput {
                description: "Fail the task".to_string(),
                prompt: "Do the failing work".to_string(),
                subagent_type: Some("Verification".to_string()),
                name: Some("fail-task".to_string()),
                model: None,
            },
            |job| {
                persist_agent_terminal_state(
                    &job.manifest,
                    "failed",
                    None,
                    Some(String::from("simulated failure")),
                )
            },
        )
        .expect("failed agent should still spawn");

        let failed_manifest =
            std::fs::read_to_string(&failed.manifest_file).expect("failed manifest should exist");
        let failed_output =
            std::fs::read_to_string(&failed.output_file).expect("failed output should exist");
        assert!(failed_manifest.contains("\"status\": \"failed\""));
        assert!(failed_manifest.contains("simulated failure"));
        assert!(failed_output.contains("simulated failure"));

        let spawn_error = execute_agent_with_spawn(
            AgentInput {
                description: "Spawn error task".to_string(),
                prompt: "Never starts".to_string(),
                subagent_type: None,
                name: Some("spawn-error".to_string()),
                model: None,
            },
            |_| Err(String::from("thread creation failed")),
        )
        .expect_err("spawn errors should surface");
        assert!(spawn_error.contains("failed to spawn sub-agent"));
        let spawn_error_manifest = std::fs::read_dir(&dir)
            .expect("agent dir should exist")
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("json"))
            .find_map(|path| {
                let contents = std::fs::read_to_string(&path).ok()?;
                contents
                    .contains("\"name\": \"spawn-error\"")
                    .then_some(contents)
            })
            .expect("failed manifest should still be written");
        assert!(spawn_error_manifest.contains("\"status\": \"failed\""));
        assert!(spawn_error_manifest.contains("thread creation failed"));

        std::env::remove_var("CLAWD_AGENT_STORE");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_tool_subset_mapping_is_expected() {
        let general = allowed_tools_for_subagent("general-purpose");
        assert!(general.contains("bash"));
        assert!(general.contains("write_file"));
        assert!(!general.contains("Agent"));

        let explore = allowed_tools_for_subagent("Explore");
        assert!(explore.contains("read_file"));
        assert!(explore.contains("grep_search"));
        assert!(!explore.contains("bash"));

        let plan = allowed_tools_for_subagent("Plan");
        assert!(plan.contains("TodoWrite"));
        assert!(plan.contains("StructuredOutput"));
        assert!(!plan.contains("Agent"));

        let verification = allowed_tools_for_subagent("Verification");
        assert!(verification.contains("bash"));
        assert!(verification.contains("PowerShell"));
        assert!(!verification.contains("write_file"));
    }

    #[derive(Debug)]
    struct MockSubagentApiClient {
        calls: usize,
        input_path: String,
    }

    impl runtime::ApiClient for MockSubagentApiClient {
        fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
            self.calls += 1;
            match self.calls {
                1 => {
                    assert_eq!(request.messages.len(), 1);
                    Ok(vec![
                        AssistantEvent::ToolUse {
                            id: "tool-1".to_string(),
                            name: "read_file".to_string(),
                            input: json!({ "path": self.input_path }).to_string(),
                        },
                        AssistantEvent::MessageStop,
                    ])
                }
                2 => {
                    assert!(request.messages.len() >= 3);
                    Ok(vec![
                        AssistantEvent::TextDelta("Scope: completed mock review".to_string()),
                        AssistantEvent::MessageStop,
                    ])
                }
                _ => panic!("unexpected mock stream call"),
            }
        }
    }

    #[test]
    fn subagent_runtime_executes_tool_loop_with_isolated_session() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let path = temp_path("subagent-input.txt");
        std::fs::write(&path, "hello from child").expect("write input file");

        let mut runtime = ConversationRuntime::new(
            Session::new(),
            MockSubagentApiClient {
                calls: 0,
                input_path: path.display().to_string(),
            },
            SubagentToolExecutor::new(BTreeSet::from([String::from("read_file")])),
            agent_permission_policy(),
            vec![String::from("system prompt")],
        );

        let summary = runtime
            .run_turn("Inspect the delegated file", None)
            .expect("subagent loop should succeed");

        assert_eq!(
            final_assistant_text(&summary),
            "Scope: completed mock review"
        );
        assert!(runtime
            .session()
            .messages
            .iter()
            .flat_map(|message| message.blocks.iter())
            .any(|block| matches!(
                block,
                runtime::ContentBlock::ToolResult { output, .. }
                    if output.contains("hello from child")
            )));

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn agent_rejects_blank_required_fields() {
        let missing_description = execute_tool(
            "Agent",
            &json!({
                "description": "  ",
                "prompt": "Inspect"
            }),
        )
        .expect_err("blank description should fail");
        assert!(missing_description.contains("description must not be empty"));

        let missing_prompt = execute_tool(
            "Agent",
            &json!({
                "description": "Inspect branch",
                "prompt": " "
            }),
        )
        .expect_err("blank prompt should fail");
        assert!(missing_prompt.contains("prompt must not be empty"));
    }

    #[test]
    fn notebook_edit_replaces_inserts_and_deletes_cells() {
        let path = temp_path("notebook.ipynb");
        std::fs::write(
            &path,
            r#"{
  "cells": [
    {"cell_type": "code", "id": "cell-a", "metadata": {}, "source": ["print(1)\n"], "outputs": [], "execution_count": null}
  ],
  "metadata": {"kernelspec": {"language": "python"}},
  "nbformat": 4,
  "nbformat_minor": 5
}"#,
        )
        .expect("write notebook");

        let replaced = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "cell_id": "cell-a",
                "new_source": "print(2)\n",
                "edit_mode": "replace"
            }),
        )
        .expect("NotebookEdit replace should succeed");
        let replaced_output: serde_json::Value = serde_json::from_str(&replaced).expect("json");
        assert_eq!(replaced_output["cell_id"], "cell-a");
        assert_eq!(replaced_output["cell_type"], "code");

        let inserted = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "cell_id": "cell-a",
                "new_source": "# heading\n",
                "cell_type": "markdown",
                "edit_mode": "insert"
            }),
        )
        .expect("NotebookEdit insert should succeed");
        let inserted_output: serde_json::Value = serde_json::from_str(&inserted).expect("json");
        assert_eq!(inserted_output["cell_type"], "markdown");
        let appended = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "new_source": "print(3)\n",
                "edit_mode": "insert"
            }),
        )
        .expect("NotebookEdit append should succeed");
        let appended_output: serde_json::Value = serde_json::from_str(&appended).expect("json");
        assert_eq!(appended_output["cell_type"], "code");

        let deleted = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "cell_id": "cell-a",
                "edit_mode": "delete"
            }),
        )
        .expect("NotebookEdit delete should succeed without new_source");
        let deleted_output: serde_json::Value = serde_json::from_str(&deleted).expect("json");
        assert!(deleted_output["cell_type"].is_null());
        assert_eq!(deleted_output["new_source"], "");

        let final_notebook: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&path).expect("read notebook"))
                .expect("valid notebook json");
        let cells = final_notebook["cells"].as_array().expect("cells array");
        assert_eq!(cells.len(), 2);
        assert_eq!(cells[0]["cell_type"], "markdown");
        assert!(cells[0].get("outputs").is_none());
        assert_eq!(cells[1]["cell_type"], "code");
        assert_eq!(cells[1]["source"][0], "print(3)\n");
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn notebook_edit_rejects_invalid_inputs() {
        let text_path = temp_path("notebook.txt");
        fs::write(&text_path, "not a notebook").expect("write text file");
        let wrong_extension = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": text_path.display().to_string(),
                "new_source": "print(1)\n"
            }),
        )
        .expect_err("non-ipynb file should fail");
        assert!(wrong_extension.contains("Jupyter notebook"));
        let _ = fs::remove_file(&text_path);

        let empty_notebook = temp_path("empty.ipynb");
        fs::write(
            &empty_notebook,
            r#"{"cells":[],"metadata":{"kernelspec":{"language":"python"}},"nbformat":4,"nbformat_minor":5}"#,
        )
        .expect("write empty notebook");

        let missing_source = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": empty_notebook.display().to_string(),
                "edit_mode": "insert"
            }),
        )
        .expect_err("insert without source should fail");
        assert!(missing_source.contains("new_source is required"));

        let missing_cell = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": empty_notebook.display().to_string(),
                "edit_mode": "delete"
            }),
        )
        .expect_err("delete on empty notebook should fail");
        assert!(missing_cell.contains("Notebook has no cells to edit"));
        let _ = fs::remove_file(empty_notebook);
    }

    /// v0.4.22 (C8): the exact delete-then-insert repro. `cell-{len+1}` minting
    /// collides ([cell-1, cell-3] has len 2 → mints "cell-3" again) and the
    /// first-match lookup then edits the WRONG cell. The probe must skip taken
    /// ids (len+1=3 → "cell-3" taken → "cell-4") and the output must report
    /// the id actually stored.
    #[test]
    fn notebook_edit_insert_mints_collision_free_cell_id() {
        let path = temp_path("collision.ipynb");
        std::fs::write(
            &path,
            r#"{
  "cells": [
    {"cell_type": "code", "id": "cell-1", "metadata": {}, "source": ["print(1)\n"], "outputs": [], "execution_count": null},
    {"cell_type": "code", "id": "cell-2", "metadata": {}, "source": ["print(2)\n"], "outputs": [], "execution_count": null},
    {"cell_type": "code", "id": "cell-3", "metadata": {}, "source": ["print(3)\n"], "outputs": [], "execution_count": null}
  ],
  "metadata": {"kernelspec": {"language": "python"}},
  "nbformat": 4,
  "nbformat_minor": 5
}"#,
        )
        .expect("write notebook");

        execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "cell_id": "cell-2",
                "edit_mode": "delete"
            }),
        )
        .expect("NotebookEdit delete should succeed");

        let inserted = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "new_source": "print(4)\n",
                "edit_mode": "insert"
            }),
        )
        .expect("NotebookEdit insert should succeed");
        let inserted_output: serde_json::Value = serde_json::from_str(&inserted).expect("json");
        assert_eq!(inserted_output["cell_id"], "cell-4");

        // A follow-up edit via the returned id must hit the NEW cell, not the
        // pre-existing cell-3.
        let replaced = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "cell_id": inserted_output["cell_id"].as_str().expect("cell id"),
                "new_source": "print(99)\n",
                "edit_mode": "replace"
            }),
        )
        .expect("NotebookEdit replace via returned id should succeed");
        let replaced_output: serde_json::Value = serde_json::from_str(&replaced).expect("json");
        assert_eq!(replaced_output["cell_id"], "cell-4");

        let final_notebook: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&path).expect("read notebook"))
                .expect("valid notebook json");
        let cells = final_notebook["cells"].as_array().expect("cells array");
        assert_eq!(cells.len(), 3);
        let source_of = |id: &str| -> serde_json::Value {
            cells
                .iter()
                .find(|cell| cell.get("id").and_then(serde_json::Value::as_str) == Some(id))
                .unwrap_or_else(|| panic!("cell {id} should exist"))["source"]
                .clone()
        };
        assert_eq!(source_of("cell-3"), json!(["print(3)\n"]));
        assert_eq!(source_of("cell-4"), json!(["print(99)\n"]));
        let _ = std::fs::remove_file(path);
    }

    /// v0.4.22 (C8): non-numeric ids (e.g. "cell-a", UUIDs) must not panic —
    /// they simply occupy the id set, and the insert returns a fresh unique id.
    #[test]
    fn notebook_edit_insert_with_non_numeric_ids_returns_fresh_unique_id() {
        let path = temp_path("non-numeric-ids.ipynb");
        std::fs::write(
            &path,
            r#"{
  "cells": [
    {"cell_type": "code", "id": "cell-a", "metadata": {}, "source": ["print(1)\n"], "outputs": [], "execution_count": null},
    {"cell_type": "code", "id": "3f2b8c1e-4d5a-4b6c-8d7e-9f0a1b2c3d4e", "metadata": {}, "source": ["print(2)\n"], "outputs": [], "execution_count": null}
  ],
  "metadata": {"kernelspec": {"language": "python"}},
  "nbformat": 4,
  "nbformat_minor": 5
}"#,
        )
        .expect("write notebook");

        let inserted = execute_tool(
            "NotebookEdit",
            &json!({
                "notebook_path": path.display().to_string(),
                "new_source": "print(3)\n",
                "edit_mode": "insert"
            }),
        )
        .expect("NotebookEdit insert with non-numeric ids should succeed");
        let inserted_output: serde_json::Value = serde_json::from_str(&inserted).expect("json");
        assert_eq!(inserted_output["cell_id"], "cell-3");

        let final_notebook: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&path).expect("read notebook"))
                .expect("valid notebook json");
        let cells = final_notebook["cells"].as_array().expect("cells array");
        assert_eq!(cells.len(), 3);
        let ids: BTreeSet<&str> = cells
            .iter()
            .filter_map(|cell| cell.get("id").and_then(serde_json::Value::as_str))
            .collect();
        assert_eq!(ids.len(), 3, "all cell ids must be unique");
        assert!(ids.contains("cell-3"));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn bash_tool_reports_success_exit_failure_timeout_and_background() {
        let success = execute_tool("bash", &json!({ "command": "printf 'hello'" }))
            .expect("bash should succeed");
        let success_output: serde_json::Value = serde_json::from_str(&success).expect("json");
        assert_eq!(success_output["stdout"], "hello");
        assert_eq!(success_output["interrupted"], false);

        let failure = execute_tool("bash", &json!({ "command": "printf 'oops' >&2; exit 7" }))
            .expect("bash failure should still return structured output");
        let failure_output: serde_json::Value = serde_json::from_str(&failure).expect("json");
        assert_eq!(failure_output["returnCodeInterpretation"], "exit_code:7");
        assert!(failure_output["stderr"]
            .as_str()
            .expect("stderr")
            .contains("oops"));

        let timeout = execute_tool("bash", &json!({ "command": "sleep 1", "timeout": 10 }))
            .expect("bash timeout should return output");
        let timeout_output: serde_json::Value = serde_json::from_str(&timeout).expect("json");
        assert_eq!(timeout_output["interrupted"], true);
        assert_eq!(timeout_output["returnCodeInterpretation"], "timeout");
        assert!(timeout_output["stderr"]
            .as_str()
            .expect("stderr")
            .contains("Command exceeded timeout"));

        let background = execute_tool(
            "bash",
            &json!({ "command": "sleep 1", "run_in_background": true }),
        )
        .expect("bash background should succeed");
        let background_output: serde_json::Value = serde_json::from_str(&background).expect("json");
        assert!(background_output["backgroundTaskId"].as_str().is_some());
        assert_eq!(background_output["noOutputExpected"], true);
    }

    #[test]
    fn file_tools_cover_read_write_and_edit_behaviors() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let root = temp_path("fs-suite");
        fs::create_dir_all(&root).expect("create root");
        let original_dir = std::env::current_dir().expect("cwd");
        std::env::set_current_dir(&root).expect("set cwd");

        let write_create = execute_tool(
            "write_file",
            &json!({ "path": "nested/demo.txt", "content": "alpha\nbeta\nalpha\n" }),
        )
        .expect("write create should succeed");
        let write_create_output: serde_json::Value =
            serde_json::from_str(&write_create).expect("json");
        assert_eq!(write_create_output["type"], "create");
        assert!(root.join("nested/demo.txt").exists());

        let write_update = execute_tool(
            "write_file",
            &json!({ "path": "nested/demo.txt", "content": "alpha\nbeta\ngamma\n" }),
        )
        .expect("write update should succeed");
        let write_update_output: serde_json::Value =
            serde_json::from_str(&write_update).expect("json");
        assert_eq!(write_update_output["type"], "update");
        assert_eq!(write_update_output["originalFile"], "alpha\nbeta\nalpha\n");

        let read_full = execute_tool("read_file", &json!({ "path": "nested/demo.txt" }))
            .expect("read full should succeed");
        let read_full_output: serde_json::Value = serde_json::from_str(&read_full).expect("json");
        assert_eq!(read_full_output["file"]["content"], "alpha\nbeta\ngamma");
        assert_eq!(read_full_output["file"]["startLine"], 1);

        let read_slice = execute_tool(
            "read_file",
            &json!({ "path": "nested/demo.txt", "offset": 1, "limit": 1 }),
        )
        .expect("read slice should succeed");
        let read_slice_output: serde_json::Value = serde_json::from_str(&read_slice).expect("json");
        assert_eq!(read_slice_output["file"]["content"], "beta");
        assert_eq!(read_slice_output["file"]["startLine"], 2);

        let read_past_end = execute_tool(
            "read_file",
            &json!({ "path": "nested/demo.txt", "offset": 50 }),
        )
        .expect("read past EOF should succeed");
        let read_past_end_output: serde_json::Value =
            serde_json::from_str(&read_past_end).expect("json");
        assert_eq!(read_past_end_output["file"]["content"], "");
        assert_eq!(read_past_end_output["file"]["startLine"], 4);

        let read_error = execute_tool("read_file", &json!({ "path": "missing.txt" }))
            .expect_err("missing file should fail");
        assert!(!read_error.is_empty());

        let edit_once = execute_tool(
            "edit_file",
            &json!({ "path": "nested/demo.txt", "old_string": "alpha", "new_string": "omega" }),
        )
        .expect("single edit should succeed");
        let edit_once_output: serde_json::Value = serde_json::from_str(&edit_once).expect("json");
        assert_eq!(edit_once_output["replaceAll"], false);
        assert_eq!(
            fs::read_to_string(root.join("nested/demo.txt")).expect("read file"),
            "omega\nbeta\ngamma\n"
        );

        execute_tool(
            "write_file",
            &json!({ "path": "nested/demo.txt", "content": "alpha\nbeta\nalpha\n" }),
        )
        .expect("reset file");
        let edit_all = execute_tool(
            "edit_file",
            &json!({
                "path": "nested/demo.txt",
                "old_string": "alpha",
                "new_string": "omega",
                "replace_all": true
            }),
        )
        .expect("replace all should succeed");
        let edit_all_output: serde_json::Value = serde_json::from_str(&edit_all).expect("json");
        assert_eq!(edit_all_output["replaceAll"], true);
        assert_eq!(
            fs::read_to_string(root.join("nested/demo.txt")).expect("read file"),
            "omega\nbeta\nomega\n"
        );

        let edit_same = execute_tool(
            "edit_file",
            &json!({ "path": "nested/demo.txt", "old_string": "omega", "new_string": "omega" }),
        )
        .expect_err("identical old/new should fail");
        assert!(edit_same.contains("must differ"));

        let edit_missing = execute_tool(
            "edit_file",
            &json!({ "path": "nested/demo.txt", "old_string": "missing", "new_string": "omega" }),
        )
        .expect_err("missing substring should fail");
        assert!(edit_missing.contains("old_string not found"));

        std::env::set_current_dir(&original_dir).expect("restore cwd");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn glob_and_grep_tools_cover_success_and_errors() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let root = temp_path("search-suite");
        fs::create_dir_all(root.join("nested")).expect("create root");
        let original_dir = std::env::current_dir().expect("cwd");
        std::env::set_current_dir(&root).expect("set cwd");

        fs::write(
            root.join("nested/lib.rs"),
            "fn main() {}\nlet alpha = 1;\nlet alpha = 2;\n",
        )
        .expect("write rust file");
        fs::write(root.join("nested/notes.txt"), "alpha\nbeta\n").expect("write txt file");

        let globbed = execute_tool("glob_search", &json!({ "pattern": "nested/*.rs" }))
            .expect("glob should succeed");
        let globbed_output: serde_json::Value = serde_json::from_str(&globbed).expect("json");
        assert_eq!(globbed_output["numFiles"], 1);
        assert!(globbed_output["filenames"][0]
            .as_str()
            .expect("filename")
            .ends_with("nested/lib.rs"));

        let glob_error = execute_tool("glob_search", &json!({ "pattern": "[" }))
            .expect_err("invalid glob should fail");
        assert!(!glob_error.is_empty());

        let grep_content = execute_tool(
            "grep_search",
            &json!({
                "pattern": "alpha",
                "path": "nested",
                "glob": "*.rs",
                "output_mode": "content",
                "-n": true,
                "head_limit": 1,
                "offset": 1
            }),
        )
        .expect("grep content should succeed");
        let grep_content_output: serde_json::Value =
            serde_json::from_str(&grep_content).expect("json");
        assert_eq!(grep_content_output["numFiles"], 0);
        assert!(grep_content_output["appliedLimit"].is_null());
        assert_eq!(grep_content_output["appliedOffset"], 1);
        assert!(grep_content_output["content"]
            .as_str()
            .expect("content")
            .contains("let alpha = 2;"));

        let grep_count = execute_tool(
            "grep_search",
            &json!({ "pattern": "alpha", "path": "nested", "output_mode": "count" }),
        )
        .expect("grep count should succeed");
        let grep_count_output: serde_json::Value = serde_json::from_str(&grep_count).expect("json");
        assert_eq!(grep_count_output["numMatches"], 3);

        let grep_error = execute_tool(
            "grep_search",
            &json!({ "pattern": "(alpha", "path": "nested" }),
        )
        .expect_err("invalid regex should fail");
        assert!(!grep_error.is_empty());

        std::env::set_current_dir(&original_dir).expect("restore cwd");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn sleep_waits_and_reports_duration() {
        let started = std::time::Instant::now();
        let result =
            execute_tool("Sleep", &json!({"duration_ms": 20})).expect("Sleep should succeed");
        let elapsed = started.elapsed();
        let output: serde_json::Value = serde_json::from_str(&result).expect("json");
        assert_eq!(output["duration_ms"], 20);
        assert!(output["message"]
            .as_str()
            .expect("message")
            .contains("Slept for 20ms"));
        assert!(elapsed >= Duration::from_millis(15));
    }

    #[test]
    fn brief_returns_sent_message_and_attachment_metadata() {
        let attachment = std::env::temp_dir().join(format!(
            "clawd-brief-{}.png",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ));
        std::fs::write(&attachment, b"png-data").expect("write attachment");

        let result = execute_tool(
            "SendUserMessage",
            &json!({
                "message": "hello user",
                "attachments": [attachment.display().to_string()],
                "status": "normal"
            }),
        )
        .expect("SendUserMessage should succeed");

        let output: serde_json::Value = serde_json::from_str(&result).expect("json");
        assert_eq!(output["message"], "hello user");
        assert!(output["sentAt"].as_str().is_some());
        assert_eq!(output["attachments"][0]["isImage"], true);
        let _ = std::fs::remove_file(attachment);
    }

    #[test]
    fn config_reads_and_writes_supported_values() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let root = std::env::temp_dir().join(format!(
            "clawd-config-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ));
        let home = root.join("home");
        let cwd = root.join("cwd");
        std::fs::create_dir_all(home.join(".claude")).expect("home dir");
        std::fs::create_dir_all(cwd.join(".claude")).expect("cwd dir");
        std::fs::write(
            home.join(".claude").join("settings.json"),
            r#"{"verbose":false}"#,
        )
        .expect("write global settings");

        let original_home = std::env::var("HOME").ok();
        let original_claude_home = std::env::var("CLAUDE_CONFIG_HOME").ok();
        let original_dir = std::env::current_dir().expect("cwd");
        std::env::set_var("HOME", &home);
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::set_current_dir(&cwd).expect("set cwd");

        let get = execute_tool("Config", &json!({"setting": "verbose"})).expect("get config");
        let get_output: serde_json::Value = serde_json::from_str(&get).expect("json");
        assert_eq!(get_output["value"], false);

        let set = execute_tool(
            "Config",
            &json!({"setting": "permissions.defaultMode", "value": "plan"}),
        )
        .expect("set config");
        let set_output: serde_json::Value = serde_json::from_str(&set).expect("json");
        assert_eq!(set_output["operation"], "set");
        assert_eq!(set_output["newValue"], "plan");

        let invalid = execute_tool(
            "Config",
            &json!({"setting": "permissions.defaultMode", "value": "bogus"}),
        )
        .expect_err("invalid config value should error");
        assert!(invalid.contains("Invalid value"));

        let unknown =
            execute_tool("Config", &json!({"setting": "nope"})).expect("unknown setting result");
        let unknown_output: serde_json::Value = serde_json::from_str(&unknown).expect("json");
        assert_eq!(unknown_output["success"], false);

        std::env::set_current_dir(&original_dir).expect("restore cwd");
        match original_home {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
        match original_claude_home {
            Some(value) => std::env::set_var("CLAUDE_CONFIG_HOME", value),
            None => std::env::remove_var("CLAUDE_CONFIG_HOME"),
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn structured_output_echoes_input_payload() {
        let result = execute_tool("StructuredOutput", &json!({"ok": true, "items": [1, 2, 3]}))
            .expect("StructuredOutput should succeed");
        let output: serde_json::Value = serde_json::from_str(&result).expect("json");
        assert_eq!(output["data"], "Structured output provided successfully");
        assert_eq!(output["structured_output"]["ok"], true);
        assert_eq!(output["structured_output"]["items"][1], 2);
    }

    #[test]
    fn repl_executes_python_code() {
        let result = execute_tool(
            "REPL",
            &json!({"language": "python", "code": "print(1 + 1)", "timeout_ms": 500}),
        )
        .expect("REPL should succeed");
        let output: serde_json::Value = serde_json::from_str(&result).expect("json");
        assert_eq!(output["language"], "python");
        assert_eq!(output["exitCode"], 0);
        assert!(output["stdout"].as_str().expect("stdout").contains('2'));
    }

    #[test]
    fn powershell_runs_via_stub_shell() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let dir = std::env::temp_dir().join(format!(
            "clawd-pwsh-bin-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).expect("create dir");
        let script = dir.join("pwsh");
        std::fs::write(
            &script,
            r#"#!/bin/sh
while [ "$1" != "-Command" ] && [ $# -gt 0 ]; do shift; done
shift
printf 'pwsh:%s' "$1"
"#,
        )
        .expect("write script");
        std::process::Command::new("/bin/chmod")
            .arg("+x")
            .arg(&script)
            .status()
            .expect("chmod");
        let original_path = std::env::var("PATH").unwrap_or_default();
        std::env::set_var("PATH", format!("{}:{}", dir.display(), original_path));

        let result = execute_tool(
            "PowerShell",
            &json!({"command": "Write-Output hello", "timeout": 1000}),
        )
        .expect("PowerShell should succeed");

        let background = execute_tool(
            "PowerShell",
            &json!({"command": "Write-Output hello", "run_in_background": true}),
        )
        .expect("PowerShell background should succeed");

        std::env::set_var("PATH", original_path);
        let _ = std::fs::remove_dir_all(dir);

        let output: serde_json::Value = serde_json::from_str(&result).expect("json");
        assert_eq!(output["stdout"], "pwsh:Write-Output hello");
        assert!(output["stderr"].as_str().expect("stderr").is_empty());

        let background_output: serde_json::Value = serde_json::from_str(&background).expect("json");
        assert!(background_output["backgroundTaskId"].as_str().is_some());
        assert_eq!(background_output["backgroundedByUser"], true);
        assert_eq!(background_output["assistantAutoBackgrounded"], false);
    }

    #[test]
    fn powershell_errors_when_shell_is_missing() {
        let _guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let original_path = std::env::var("PATH").unwrap_or_default();
        let empty_dir = std::env::temp_dir().join(format!(
            "clawd-empty-bin-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ));
        std::fs::create_dir_all(&empty_dir).expect("create empty dir");
        std::env::set_var("PATH", empty_dir.display().to_string());

        let err = execute_tool("PowerShell", &json!({"command": "Write-Output hello"}))
            .expect_err("PowerShell should fail when shell is missing");

        std::env::set_var("PATH", original_path);
        let _ = std::fs::remove_dir_all(empty_dir);

        assert!(err.contains("PowerShell executable not found"));
    }

    /// v0.4.22 (C5): on Windows the probe routes through `where.exe` (the unix
    /// `sh -lc` path is dead on stock Windows). These run in the Windows CI
    /// job — a build-only gate would never execute the branch.
    #[cfg(windows)]
    #[test]
    fn command_exists_probe_finds_cmd() {
        assert!(super::command_exists("cmd"));
    }

    #[cfg(windows)]
    #[test]
    fn command_exists_probe_rejects_garbage() {
        assert!(!super::command_exists("aris-definitely-not-a-real-cmd-xyz"));
    }

    struct TestServer {
        addr: SocketAddr,
        shutdown: Option<std::sync::mpsc::Sender<()>>,
        handle: Option<thread::JoinHandle<()>>,
    }

    impl TestServer {
        fn spawn(handler: Arc<dyn Fn(&str) -> HttpResponse + Send + Sync + 'static>) -> Self {
            let listener = TcpListener::bind("127.0.0.1:0").expect("bind test server");
            listener
                .set_nonblocking(true)
                .expect("set nonblocking listener");
            let addr = listener.local_addr().expect("local addr");
            let (tx, rx) = std::sync::mpsc::channel::<()>();

            let handle = thread::spawn(move || loop {
                if rx.try_recv().is_ok() {
                    break;
                }

                match listener.accept() {
                    Ok((mut stream, _)) => {
                        let mut buffer = [0_u8; 4096];
                        let size = stream.read(&mut buffer).expect("read request");
                        let request = String::from_utf8_lossy(&buffer[..size]).into_owned();
                        let request_line = request.lines().next().unwrap_or_default().to_string();
                        let response = handler(&request_line);
                        stream
                            .write_all(response.to_bytes().as_slice())
                            .expect("write response");
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(error) => panic!("server accept failed: {error}"),
                }
            });

            Self {
                addr,
                shutdown: Some(tx),
                handle: Some(handle),
            }
        }

        fn addr(&self) -> SocketAddr {
            self.addr
        }
    }

    impl Drop for TestServer {
        fn drop(&mut self) {
            if let Some(tx) = self.shutdown.take() {
                let _ = tx.send(());
            }
            if let Some(handle) = self.handle.take() {
                handle.join().expect("join test server");
            }
        }
    }

    struct HttpResponse {
        status: u16,
        reason: &'static str,
        content_type: &'static str,
        body: String,
    }

    impl HttpResponse {
        fn html(status: u16, reason: &'static str, body: &str) -> Self {
            Self {
                status,
                reason,
                content_type: "text/html; charset=utf-8",
                body: body.to_string(),
            }
        }

        fn text(status: u16, reason: &'static str, body: &str) -> Self {
            Self {
                status,
                reason,
                content_type: "text/plain; charset=utf-8",
                body: body.to_string(),
            }
        }

        fn to_bytes(&self) -> Vec<u8> {
            format!(
                "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                self.status,
                self.reason,
                self.content_type,
                self.body.len(),
                self.body
            )
            .into_bytes()
        }
    }

    // ─── LlmReview routing + fallback tests ──────────────────────────────
    //
    // These tests serialize around ENV_LOCK_REVIEWER because resolve_reviewer_model
    // reads real env vars (to check whether the requested model's key is set).

    fn env_lock_reviewer() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    const REVIEWER_KEY_ENVS: &[&str] = &[
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GLM_API_KEY",
        "MINIMAX_API_KEY",
        "KIMI_API_KEY",
    ];

    struct ReviewerEnvSnapshot {
        vars: Vec<(&'static str, Option<String>)>,
    }

    impl ReviewerEnvSnapshot {
        fn capture_and_clear() -> Self {
            let vars = REVIEWER_KEY_ENVS
                .iter()
                .map(|n| (*n, std::env::var(n).ok()))
                .collect();
            for n in REVIEWER_KEY_ENVS {
                std::env::remove_var(n);
            }
            Self { vars }
        }
    }

    impl Drop for ReviewerEnvSnapshot {
        fn drop(&mut self) {
            for (name, prior) in &self.vars {
                match prior {
                    Some(v) => std::env::set_var(name, v),
                    None => std::env::remove_var(name),
                }
            }
        }
    }

    // v0.4.16 Phase 0 — env vars that govern the SUBAGENT auth path
    // (AnthropicClient::from_env -> AuthSource resolution) and the
    // provider-blind executor env that build_agent_runtime currently
    // ignores. Captured + cleared so the subagent characterization tests
    // run against a known-empty baseline and restore the developer's
    // real shell on drop.
    const SUBAGENT_AUTH_ENVS: &[&str] = &[
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
        "EXECUTOR_PROVIDER",
        "EXECUTOR_API_KEY",
        "EXECUTOR_BASE_URL",
        // codex Phase-0 gap #3: clear OPENAI_API_KEY too. Without this, a P8
        // regression that mis-routes a Category A/B (Anthropic / anthropic-
        // compat) subagent into the OpenAI branch could still build Ok on a
        // dev/CI box that happens to export OPENAI_API_KEY, hiding the
        // misroute behind a false-green Ok-only assertion.
        "OPENAI_API_KEY",
    ];

    struct SubagentEnvSnapshot {
        vars: Vec<(&'static str, Option<String>)>,
    }

    impl SubagentEnvSnapshot {
        fn capture_and_clear() -> Self {
            let vars = SUBAGENT_AUTH_ENVS
                .iter()
                .map(|n| (*n, std::env::var(n).ok()))
                .collect();
            for n in SUBAGENT_AUTH_ENVS {
                std::env::remove_var(n);
            }
            Self { vars }
        }
    }

    impl Drop for SubagentEnvSnapshot {
        fn drop(&mut self) {
            for (name, prior) in &self.vars {
                match prior {
                    Some(v) => std::env::set_var(name, v),
                    None => std::env::remove_var(name),
                }
            }
        }
    }

    /// Build a real `AgentJob` (the input to `build_agent_runtime`) without
    /// going through `execute_agent_with_spawn`'s disk side-effects. We grab
    /// one via the existing fake-spawn capture path so the manifest/prompt
    /// shape stays in sync with production. Returns an `AgentJob` that points
    /// at a temp store the caller is responsible for cleaning up.
    //
    // CLAWD_AGENT_STORE is a PROCESS-GLOBAL env var also mutated by the
    // existing `agent_*` tests under `env_lock()`. Those tests use a DIFFERENT
    // mutex than the subagent characterization tests (`env_lock_reviewer()`),
    // so we must serialize on `env_lock()` here too while we touch the store,
    // otherwise our `remove_var` races and clobbers a concurrent agent test's
    // store path. Lock order is always reviewer-lock (held by caller) then
    // env_lock (here) — no other test acquires them in the reverse order, so
    // there is no deadlock cycle.
    fn capture_agent_job(store_name: &str) -> (AgentJob, PathBuf) {
        let _agent_guard = env_lock()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let dir = temp_path(store_name);
        std::env::set_var("CLAWD_AGENT_STORE", &dir);
        let captured = Arc::new(Mutex::new(None::<AgentJob>));
        let captured_for_spawn = Arc::clone(&captured);
        execute_agent_with_spawn(
            AgentInput {
                description: "char build_agent_runtime".to_string(),
                prompt: "Do the delegated work.".to_string(),
                subagent_type: Some("Explore".to_string()),
                name: Some("char-runtime".to_string()),
                model: None,
            },
            move |job| {
                *captured_for_spawn
                    .lock()
                    .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(job);
                Ok(())
            },
        )
        .expect("Agent should capture the job");
        std::env::remove_var("CLAWD_AGENT_STORE");
        let job = captured
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
            .expect("spawn job should be captured");
        (job, dir)
    }

    #[test]
    fn route_openai_compat_model_picks_provider_from_name() {
        assert_eq!(route_openai_compat_model("gpt-5.5").0, "OPENAI_API_KEY");
        assert_eq!(route_openai_compat_model("gemini-2.5-pro").0, "GEMINI_API_KEY");
        assert_eq!(route_openai_compat_model("GLM-5").0, "GLM_API_KEY");
        assert_eq!(route_openai_compat_model("MiniMax-M2.7").0, "MINIMAX_API_KEY");
        assert_eq!(route_openai_compat_model("kimi-k2.5").0, "KIMI_API_KEY");
        assert_eq!(route_openai_compat_model("moonshot-v1").0, "KIMI_API_KEY");
        // DeepSeek models route to their own API key.
        assert_eq!(route_openai_compat_model("deepseek-chat").0, "DEEPSEEK_API_KEY");
    }

    #[test]
    fn resolve_reviewer_model_returns_configured_when_input_absent() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();

        let model = resolve_reviewer_model(None, "kimi-k2.5");
        assert_eq!(model, "kimi-k2.5");
    }

    #[test]
    fn resolve_reviewer_model_returns_configured_when_input_empty_string() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();

        let model = resolve_reviewer_model(Some(""), "kimi-k2.5");
        assert_eq!(model, "kimi-k2.5");
    }

    #[test]
    fn resolve_reviewer_model_falls_back_when_requested_key_missing() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();
        std::env::set_var("KIMI_API_KEY", "sk-kimi");
        // Executor requested gpt-4o but only KIMI_API_KEY is set — fall back.
        let model = resolve_reviewer_model(Some("gpt-4o"), "kimi-k2.5");
        assert_eq!(model, "kimi-k2.5");
    }

    #[test]
    fn resolve_reviewer_model_falls_back_on_provider_mismatch() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();
        // Both keys set, but configured reviewer is MiniMax — executor asking
        // for gpt-4o must NOT silently route to the stray OPENAI_API_KEY.
        std::env::set_var("MINIMAX_API_KEY", "mx-token");
        std::env::set_var("OPENAI_API_KEY", "sk-openai");
        let model = resolve_reviewer_model(Some("gpt-4o"), "MiniMax-M2.7");
        assert_eq!(
            model, "MiniMax-M2.7",
            "configured reviewer should win over coincidentally-present OpenAI key"
        );
    }

    #[test]
    fn resolve_reviewer_model_honors_matching_override() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();
        // Configured reviewer is OpenAI (gpt-5.5); executor asks for gpt-5.5-mini.
        std::env::set_var("OPENAI_API_KEY", "sk-openai");
        let model = resolve_reviewer_model(Some("gpt-5.5-mini"), "gpt-5.5");
        assert_eq!(
            model, "gpt-5.5-mini",
            "same-provider override should be honored when the key is set"
        );
    }

    #[test]
    fn resolve_reviewer_model_after_slash_reviewer_switch() {
        // Regression test: `/setup` Gemini → `/reviewer gpt-5.5` updates
        // ARIS_REVIEWER_MODEL but leaves ARIS_REVIEWER_PROVIDER stale as "gemini".
        // Executor now asks for gpt-5.5-mini — this MUST be honored since the
        // user's real intent (per ARIS_REVIEWER_MODEL) is OpenAI.
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();
        std::env::set_var("OPENAI_API_KEY", "sk-openai");
        // Stale provider env var from earlier /setup — deliberately wrong.
        std::env::set_var("ARIS_REVIEWER_PROVIDER", "gemini");

        let model = resolve_reviewer_model(Some("gpt-5.5-mini"), "gpt-5.5");
        assert_eq!(
            model, "gpt-5.5-mini",
            "provider consistency must come from configured_model, not stale ARIS_REVIEWER_PROVIDER"
        );

        std::env::remove_var("ARIS_REVIEWER_PROVIDER");
    }

    // v0.4.13 regression — v0.4.12 P1.B introduced reviewer_word_match,
    // a copy of runtime::usage::has_word so the reviewer crate stays
    // consistent with the executor + pricing word-boundary detection.
    // Lock down provider-prefix and digit-suffix boundary cases so a
    // future divergence between the three copies surfaces here.
    #[test]
    fn reviewer_word_match_provider_prefix() {
        assert!(super::reviewer_word_match("openai/o3-mini", "o3"));
        assert!(super::reviewer_word_match("proxy:o4-preview", "o4"));
        // Digit-suffix collision — "o32-mini" must NOT count as an o3 model.
        assert!(!super::reviewer_word_match("o32-mini", "o3"));
    }

    // ===================================================================
    // v0.4.16 Phase 0 — CHARACTERIZATION TESTS (reviewer routing + subagent)
    //
    // These lock down what `route_openai_compat_model`, `resolve_reviewer_model`,
    // `reviewer_supports_reasoning_effort`, and `build_agent_runtime` actually
    // do TODAY, BEFORE the P7 (provider routing) and P8 (subagent dispatch)
    // refactors. They are intentionally strict: if a refactor changes any
    // observed value, the test fails and the change must be deliberate.
    //
    // The most load-bearing locks here capture KNOWN, INTENTIONAL
    // inconsistencies between the reviewer router (contains / starts_with)
    // and the pricing table (provider_match word-boundary). Unifying the two
    // would "fix" these and silently change routing — these tests forbid that
    // from happening by accident.
    // ===================================================================

    // ---- A. reviewer route_openai_compat_model characterization -----------

    // route_kimi_contains: "my-kimi" routes to KIMI because the reviewer
    // router uses a bare `model.contains("kimi")`. This is the MAJOR known
    // inconsistency: the pricing table's `provider_match` REJECTS the
    // mid-word "my-kimi-clone" (-> None / sonnet default) because it requires
    // a word boundary, while the reviewer router accepts it as Kimi. We lock
    // BOTH halves of that divergence right next to each other so a future
    // "unification" cannot quietly collapse them.
    #[test]
    fn char_route_kimi_contains_differs_from_pricing() {
        // Reviewer side: contains("kimi") -> Kimi, no boundary required.
        assert_eq!(
            route_openai_compat_model("my-kimi"),
            (
                "KIMI_API_KEY",
                "https://api.moonshot.cn/v1/chat/completions",
                "kimi"
            ),
            "reviewer router uses contains() so mid-word 'my-kimi' -> Kimi"
        );
        // Same loose contains for the design's `my-kimi-clone` string: the
        // reviewer router STILL classifies it as Kimi, whereas pricing's
        // provider_match rejects it (locked separately in the pricing tests
        // as price_my_kimi_clone_rejected -> None). This asymmetry is the
        // point of the test.
        assert_eq!(
            route_openai_compat_model("my-kimi-clone").2,
            "kimi",
            "INTENTIONAL inconsistency: reviewer contains('kimi') accepts \
             'my-kimi-clone' as Kimi even though pricing provider_match rejects it"
        );
        // moonshot is the other alias in the same contains() branch.
        assert_eq!(route_openai_compat_model("moonshot-v1").0, "KIMI_API_KEY");

        // codex Phase-0 gap #2: the `my-kimi` / `my-kimi-clone` cases above do
        // NOT distinguish contains() from word_match() — `kimi` sits between
        // `-` boundaries there, so word_match would ALSO match. To truly lock
        // that the reviewer router is `contains` (so P7's word_match
        // consolidation can't silently tighten it), assert a host with
        // NON-boundary chars hugging the needle: contains matches, word_match
        // would reject (`x`/`y` are not in the -_/: boundary set).
        assert_eq!(
            route_openai_compat_model("xxkimiyy").2,
            "kimi",
            "reviewer router must use contains() — 'xxkimiyy' has no boundary \
             around 'kimi' yet still routes to Kimi"
        );
    }

    // route_my_minimax_to_openai: MiniMax is matched with starts_with, NOT
    // contains. So "my-minimax-clone" (minimax NOT at the front) falls
    // through to the OpenAI else-branch. Locks the starts_with mid-word miss.
    #[test]
    fn char_route_minimax_startswith_and_midword_miss() {
        // starts_with hit (both case variants are explicitly handled).
        assert_eq!(
            route_openai_compat_model("MiniMax-M2.7"),
            (
                "MINIMAX_API_KEY",
                "https://api.minimax.chat/v1/chat/completions",
                "minimax"
            )
        );
        assert_eq!(
            route_openai_compat_model("minimax-m2.7").0,
            "MINIMAX_API_KEY",
            "lowercase starts_with branch"
        );
        // starts_with MISS: minimax not at front -> falls through to OpenAI.
        // NOTE asymmetry: kimi uses contains() (would match here) but minimax
        // uses starts_with() (does not). Locked deliberately.
        assert_eq!(
            route_openai_compat_model("my-minimax-clone"),
            (
                "OPENAI_API_KEY",
                "https://api.openai.com/v1/chat/completions",
                "openai"
            ),
            "minimax starts_with() miss falls to OpenAI else-branch"
        );
    }

    // route_glm_case: GLM is matched with contains("glm") || contains("GLM"),
    // i.e. dual-case but NOT ascii-lowercased. Lock both cases route to GLM.
    #[test]
    fn char_route_glm_dual_case_contains() {
        assert_eq!(
            route_openai_compat_model("GLM-5"),
            (
                "GLM_API_KEY",
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "glm"
            )
        );
        // lowercase contains branch
        assert_eq!(route_openai_compat_model("glm-4-plus").0, "GLM_API_KEY");
        // mixed-case substring still hits (contains is case-sensitive but the
        // branch ORs both "glm" and "GLM"; a "Glm" mixed form matches neither,
        // so it falls through — lock that too as the current behavior).
        assert_eq!(
            route_openai_compat_model("Glm-7").0,
            "OPENAI_API_KEY",
            "mixed-case 'Glm' matches neither 'glm' nor 'GLM' substring -> OpenAI \
             (current behavior; only the two explicit cases are handled)"
        );
    }

    // route_gemini / route_deepseek / route_else fallthrough.
    #[test]
    fn char_route_gemini_deepseek_and_else() {
        assert_eq!(
            route_openai_compat_model("gemini-2.5-pro"),
            (
                "GEMINI_API_KEY",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                "gemini"
            )
        );
        assert_eq!(
            route_openai_compat_model("deepseek-chat"),
            (
                "DEEPSEEK_API_KEY",
                "https://api.deepseek.com/v1/chat/completions",
                "deepseek"
            )
        );
        // else-branch: gpt / o3 / o4 all collapse to OpenAI.
        for m in ["gpt-5.5", "o3", "o4", "totally-unknown-model"] {
            assert_eq!(
                route_openai_compat_model(m),
                (
                    "OPENAI_API_KEY",
                    "https://api.openai.com/v1/chat/completions",
                    "openai"
                ),
                "{m} should fall through to OpenAI else-branch"
            );
        }
    }

    // route ordering: a string containing BOTH "gemini" and a later keyword
    // hits gemini first (it is the first arm). Lock the first-match order so a
    // refactor that reorders arms is caught.
    #[test]
    fn char_route_first_arm_wins_ordering() {
        // gemini arm precedes glm/minimax/kimi/deepseek.
        assert_eq!(
            route_openai_compat_model("gemini-glm-hybrid").2,
            "gemini",
            "gemini arm is checked first"
        );
        // glm arm precedes kimi: a name with both "glm" and "kimi" -> glm.
        assert_eq!(
            route_openai_compat_model("glm-kimi").2,
            "glm",
            "glm arm precedes the kimi arm"
        );
    }

    // ---- resolve_reviewer_model: equality short-circuit (matrix gap) ------

    // resolve_reviewer_equal_shortcircuit: when requested == configured, the
    // function returns early WITHOUT consulting env keys or provider routing.
    // Lock it with NO keys set (capture_and_clear) to prove the key/provider
    // checks are skipped.
    #[test]
    fn char_resolve_reviewer_model_equality_short_circuit() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = ReviewerEnvSnapshot::capture_and_clear();
        // No KIMI_API_KEY set, yet requested == configured -> still returned.
        let model = resolve_reviewer_model(Some("kimi-k2.5"), "kimi-k2.5");
        assert_eq!(
            model, "kimi-k2.5",
            "requested == configured short-circuits before the key/provider check"
        );
    }

    // ---- reviewer_supports_reasoning_effort word-match parity ------------

    // reviewer_word_match_prefix / midword: exercise the public wrapper
    // reviewer_supports_reasoning_effort (which lowercases then word_matches
    // o1/o3/o4 and contains-matches gpt-5.5/5.6/reasoner/thinking).
    #[test]
    fn char_reviewer_supports_reasoning_effort_boundaries() {
        // word_match boundary hits via provider/colon prefixes.
        assert!(reviewer_supports_reasoning_effort("openai/o3-mini"));
        assert!(reviewer_supports_reasoning_effort("proxy:o4-preview"));
        assert!(reviewer_supports_reasoning_effort("o1-preview"));
        // mid-word reject: "o32-mini" is not an o3 model.
        assert!(!reviewer_supports_reasoning_effort("o32-mini"));
        // contains branches (case-insensitive via to_ascii_lowercase).
        assert!(reviewer_supports_reasoning_effort("GPT-5.5"));
        assert!(reviewer_supports_reasoning_effort("gpt-5.6-pro"));
        assert!(reviewer_supports_reasoning_effort("deepseek-reasoner"));
        assert!(reviewer_supports_reasoning_effort("glm-4.6-thinking"));
        // codex Phase-0 gap #2 (round 2): contains-vs-word_match discriminators
        // for the reviewer reasoning predicate. The cases above are mostly
        // hyphen-bounded, so a word_match conversion would still pass them.
        // These hosts hug the needle with NON-boundary chars (`x`/`y`): they
        // match ONLY because gpt-5.5/gpt-5.6/reasoner/thinking are `contains`
        // branches (o1/o3/o4 use reviewer_word_match). If P7 ever converts
        // these to word_match, these flip to false and the assert fails.
        assert!(reviewer_supports_reasoning_effort("xxgpt-5.5yy"));
        assert!(reviewer_supports_reasoning_effort("xxgpt-5.6yy"));
        assert!(reviewer_supports_reasoning_effort("xxreasoneryy"));
        assert!(reviewer_supports_reasoning_effort("xxthinkingyy"));
        // negatives
        assert!(!reviewer_supports_reasoning_effort("gpt-4o"));
        assert!(!reviewer_supports_reasoning_effort("gpt-5.4"));
        assert!(!reviewer_supports_reasoning_effort("kimi-k2.5"));
    }

    // ===================================================================
    // B. SUBAGENT (build_agent_runtime) characterization — Category A/B/C
    //
    // For Anthropic-family executors (A: anthropic native, B: anthropic-compat)
    // `build_agent_runtime` constructs an `AnthropicRuntimeClient` exactly as
    // before — EXECUTOR_PROVIDER is unset/cleared for them so the P8 v0.4.16
    // guard never fires; these tests lock that unchanged behavior.
    // For OpenAI-family executors (C: EXECUTOR_PROVIDER=="openai") the P8
    // v0.4.16 minimal guard now FAILS LOUD (was: silently built an Anthropic
    // client and billed the user's Anthropic credential). The C tests assert
    // that fail-loud contract; full OpenAI subagent routing (P8) is on the
    // roadmap but unshipped (design in idea-stage/v0.4.16/p8_design.json).
    //
    // The auth BRANCH (x-api-key vs Bearer) is not observable through the
    // built `ConversationRuntime` (its inner api_client is private with no
    // accessor). We therefore lock the auth branch directly on
    // `AnthropicClient::from_env().auth_source()` — the exact dependency
    // `AnthropicRuntimeClient::new` consumes — and separately lock the
    // Ok/Err structural outcome of `build_agent_runtime` itself.
    // ===================================================================

    // Category A auth branch: ANTHROPIC_API_KEY set (official/custom-url
    // anthropic) -> AuthSource::ApiKey -> apply() emits `x-api-key`, NOT
    // Bearer. This is the subagent path Category A users (and #158/#162
    // anthropic+custom-url users) rely on.
    #[test]
    fn char_subagent_auth_anthropic_api_key_is_apikey_xheader() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("ANTHROPIC_API_KEY", "sk-ant-test");

        let client = AnthropicClient::from_env().expect("api key present -> Ok");
        assert_eq!(
            client.auth_source(),
            &AuthSource::ApiKey("sk-ant-test".to_string()),
            "ANTHROPIC_API_KEY alone resolves to ApiKey (x-api-key header), not Bearer"
        );
    }

    // Category B auth branch: ANTHROPIC_AUTH_TOKEN (+ ANTHROPIC_BASE_URL for
    // a compat endpoint) and NO ANTHROPIC_API_KEY -> AuthSource::BearerToken
    // -> Authorization: Bearer. This is the anthropic-compat / DeepSeek /
    // MiniMax-compat subagent path that must keep working silently after P8.
    #[test]
    fn char_subagent_auth_anthropic_compat_is_bearer() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "compat-bearer");
        std::env::set_var("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic");

        let client = AnthropicClient::from_env().expect("auth token present -> Ok");
        assert_eq!(
            client.auth_source(),
            &AuthSource::BearerToken("compat-bearer".to_string()),
            "ANTHROPIC_AUTH_TOKEN (no API key) resolves to BearerToken (Authorization: Bearer)"
        );
    }

    // Combined-header state (documented intentional): both ANTHROPIC_API_KEY
    // and ANTHROPIC_AUTH_TOKEN set -> ApiKeyAndBearer -> apply() emits BOTH
    // x-api-key AND Bearer. Locks the not-either-or behavior the subagent
    // would also inherit.
    #[test]
    fn char_subagent_auth_combined_api_key_and_bearer() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("ANTHROPIC_API_KEY", "sk-ant-test");
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "also-bearer");

        let client = AnthropicClient::from_env().expect("both present -> Ok");
        assert_eq!(
            client.auth_source(),
            &AuthSource::ApiKeyAndBearer {
                api_key: "sk-ant-test".to_string(),
                bearer_token: "also-bearer".to_string(),
            },
            "both env vars set -> ApiKeyAndBearer (emits BOTH headers, not either-or)"
        );
    }

    // Category A end-to-end structural: build_agent_runtime with
    // ANTHROPIC_API_KEY set returns Ok (the runtime is constructed). Must
    // stay Ok after P8 for anthropic executors. Note: AnthropicClient::from_env
    // does no network I/O, so this is deterministic.
    #[test]
    fn char_build_agent_runtime_anthropic_api_key_builds_ok() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("ANTHROPIC_API_KEY", "sk-ant-test");

        let (job, dir) = capture_agent_job("char-runtime-a");
        let result = build_agent_runtime(&job);
        assert!(
            result.is_ok(),
            "Category A: ANTHROPIC_API_KEY set -> build_agent_runtime returns Ok, got {:?}",
            result.err()
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    // Category B end-to-end structural: build_agent_runtime with
    // ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL (anthropic-compat) returns Ok.
    // Must stay Ok after P8.
    #[test]
    fn char_build_agent_runtime_anthropic_compat_builds_ok() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "compat-bearer");
        std::env::set_var("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic");

        let (job, dir) = capture_agent_job("char-runtime-b");
        let result = build_agent_runtime(&job);
        assert!(
            result.is_ok(),
            "Category B: anthropic-compat env -> build_agent_runtime returns Ok, got {:?}",
            result.err()
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    // P8 v0.4.16 (minimal error-guard): build_agent_runtime now FAILS LOUD for
    // an OpenAI-family executor instead of silently building an Anthropic
    // client (which would bill the user's Anthropic credential). The baseline
    // (anthropic) path is unchanged. Full OpenAI subagent routing (P8 — design
    // in idea-stage/v0.4.16/p8_design.json) is on the roadmap but unshipped, at
    // which point the openai run should build an OpenAI runtime instead of
    // erroring.
    #[test]
    fn char_build_agent_runtime_rejects_openai_provider() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        // No ANTHROPIC_* / EXECUTOR_* set: the anthropic baseline path is
        // whatever OAuth/Keychain fallback exists — we do NOT force its outcome
        // (a dev box with Claude Code can legally build Ok). We only assert it
        // does not hit the new openai guard.
        let (job1, dir1) = capture_agent_job("char-runtime-c1");
        let baseline = build_agent_runtime(&job1);
        let _ = std::fs::remove_dir_all(dir1);
        if let Err(msg) = &baseline {
            assert!(
                !msg.contains("Anthropic-family"),
                "baseline (no EXECUTOR_PROVIDER) must NOT hit the openai guard: {msg}"
            );
        }

        // EXECUTOR_PROVIDER=openai must now hard-error with the guard message
        // (no more silent provider-blind Anthropic build).
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        std::env::set_var("EXECUTOR_API_KEY", "sk-openai-exec");
        std::env::set_var("EXECUTOR_BASE_URL", "https://api.openai.com/v1");
        let (job2, dir2) = capture_agent_job("char-runtime-c2");
        let openai = build_agent_runtime(&job2);
        let _ = std::fs::remove_dir_all(dir2);

        // `ConversationRuntime` is not `Debug`, so use let-else rather than
        // `expect_err` to pull out the error.
        let Err(err) = openai else {
            panic!("EXECUTOR_PROVIDER=openai must fail loud, not build an Anthropic client");
        };
        // v0.4.19 (T2): the guard message is now VERSION-AGNOSTIC. The old
        // "lands in v0.4.18" marker went stale the moment v0.4.18 shipped
        // without P8, misleading OpenAI-family users into thinking the build
        // was broken. The fail-loud contract is unchanged; only the wording is.
        assert!(
            err.contains("Anthropic-family") && err.contains("not yet supported"),
            "openai subagent must fail loud with the version-agnostic guard message. got: {err}"
        );
        assert!(
            !err.contains("v0.4.1") && !err.contains("lands in"),
            "guard message must NOT promise a specific release (stays version-agnostic): {err}"
        );
        // The message must never leak the executor credential.
        assert!(
            !err.contains("sk-openai-exec"),
            "guard message must not leak credentials: {err}"
        );
    }

    // P8 v0.4.16 fail-loud contract: EXECUTOR_PROVIDER=openai now returns the
    // guard Err DETERMINISTICALLY (no longer depends on OAuth/Keychain state,
    // because the guard returns before any Anthropic client is built), and the
    // message carries NO credential env names (anti-leak, mirroring the v0.4.14
    // S9 redaction posture).
    #[test]
    fn char_build_agent_runtime_rejects_openai_with_credential_free_message() {
        let _g = env_lock_reviewer().lock().unwrap();
        let _snap = SubagentEnvSnapshot::capture_and_clear();
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        std::env::set_var("EXECUTOR_API_KEY", "sk-openai-exec");

        let (job, dir) = capture_agent_job("char-runtime-c-err");
        let result = build_agent_runtime(&job);
        let _ = std::fs::remove_dir_all(dir);

        // `ConversationRuntime` is not `Debug`; use let-else instead of expect_err.
        let Err(msg) = result else {
            panic!("EXECUTOR_PROVIDER=openai subagent must fail loud");
        };
        // v0.4.19 (T2): the guard message is now version-agnostic (the old
        // "lands in v0.4.18" marker went stale once v0.4.18 shipped without P8).
        // The fail-loud + credential-free contract is otherwise unchanged.
        assert!(
            msg.contains("Anthropic-family") && msg.contains("not yet supported"),
            "must be the version-agnostic fail-loud guard message: {msg}"
        );
        assert!(
            !msg.contains("v0.4.1") && !msg.contains("lands in"),
            "guard message must not promise a specific release: {msg}"
        );
        // Anti-leak: the guard message must never echo a credential env NAME
        // nor the actual key VALUE (the sentinel set above).
        assert!(
            !msg.contains("ANTHROPIC_API_KEY")
                && !msg.contains("ANTHROPIC_AUTH_TOKEN")
                && !msg.contains("EXECUTOR_API_KEY")
                && !msg.contains("OPENAI_API_KEY")
                && !msg.contains("sk-openai-exec"),
            "guard message must not leak any credential env name or value: {msg}"
        );
    }
}
