use std::collections::BTreeMap;
use std::io;
use std::process::Stdio;

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};

use crate::codex_exec::{is_legacy_codex_mcp_server, CodexExecBridge};
use crate::config::{McpServerConfig, McpTransport, RuntimeConfig, ScopedMcpServerConfig};
use crate::mcp::{mcp_tool_name, mcp_tool_prefix, normalize_name_for_mcp};
use crate::mcp_client::{McpClientBootstrap, McpClientTransport, McpStdioTransport};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(untagged)]
pub enum JsonRpcId {
    Number(u64),
    String(String),
    Null,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JsonRpcRequest<T = JsonValue> {
    pub jsonrpc: String,
    pub id: JsonRpcId,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<T>,
}

impl<T> JsonRpcRequest<T> {
    #[must_use]
    pub fn new(id: JsonRpcId, method: impl Into<String>, params: Option<T>) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id,
            method: method.into(),
            params,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JsonRpcError {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JsonRpcResponse<T = JsonValue> {
    pub jsonrpc: String,
    pub id: JsonRpcId,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<T>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpInitializeParams {
    pub protocol_version: String,
    pub capabilities: JsonValue,
    pub client_info: McpInitializeClientInfo,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct McpInitializeClientInfo {
    pub name: String,
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpInitializeResult {
    pub protocol_version: String,
    pub capabilities: JsonValue,
    pub server_info: McpInitializeServerInfo,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct McpInitializeServerInfo {
    pub name: String,
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpListToolsParams {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct McpTool {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(rename = "inputSchema", skip_serializing_if = "Option::is_none")]
    pub input_schema: Option<JsonValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotations: Option<JsonValue>,
    #[serde(rename = "_meta", skip_serializing_if = "Option::is_none")]
    pub meta: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpListToolsResult {
    pub tools: Vec<McpTool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpToolCallParams {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub arguments: Option<JsonValue>,
    #[serde(rename = "_meta", skip_serializing_if = "Option::is_none")]
    pub meta: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct McpToolCallContent {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(flatten)]
    pub data: BTreeMap<String, JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpToolCallResult {
    #[serde(default)]
    pub content: Vec<McpToolCallContent>,
    #[serde(default)]
    pub structured_content: Option<JsonValue>,
    #[serde(default)]
    pub is_error: Option<bool>,
    #[serde(rename = "_meta", skip_serializing_if = "Option::is_none")]
    pub meta: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpListResourcesParams {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct McpResource {
    pub uri: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotations: Option<JsonValue>,
    #[serde(rename = "_meta", skip_serializing_if = "Option::is_none")]
    pub meta: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpListResourcesResult {
    pub resources: Vec<McpResource>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpReadResourceParams {
    pub uri: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct McpResourceContents {
    pub uri: String,
    #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blob: Option<String>,
    #[serde(rename = "_meta", skip_serializing_if = "Option::is_none")]
    pub meta: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct McpReadResourceResult {
    pub contents: Vec<McpResourceContents>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ManagedMcpTool {
    pub server_name: String,
    pub qualified_name: String,
    pub raw_name: String,
    pub tool: McpTool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnsupportedMcpServer {
    pub server_name: String,
    pub transport: McpTransport,
    pub reason: String,
}

/// v0.4.17 (RW6): a stdio MCP server that was configured and supported
/// but failed during `discover_tools` (spawn / initialize / tools/list).
/// Recorded per-server so one bad server no longer takes down the whole
/// MCP tool catalogue — the others' tools are still returned and the
/// failure is surfaced (stderr warning + this structured record).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct McpDiscoveryFailure {
    pub server_name: String,
    pub reason: String,
}

#[derive(Debug)]
pub enum McpServerManagerError {
    Io(io::Error),
    JsonRpc {
        server_name: String,
        method: &'static str,
        error: JsonRpcError,
    },
    InvalidResponse {
        server_name: String,
        method: &'static str,
        details: String,
    },
    UnknownTool {
        qualified_name: String,
    },
    UnknownServer {
        server_name: String,
    },
}

impl std::fmt::Display for McpServerManagerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "{error}"),
            Self::JsonRpc {
                server_name,
                method,
                error,
            } => write!(
                f,
                "MCP server `{server_name}` returned JSON-RPC error for {method}: {} ({})",
                error.message, error.code
            ),
            Self::InvalidResponse {
                server_name,
                method,
                details,
            } => write!(
                f,
                "MCP server `{server_name}` returned invalid response for {method}: {details}"
            ),
            Self::UnknownTool { qualified_name } => {
                write!(f, "unknown MCP tool `{qualified_name}`")
            }
            Self::UnknownServer { server_name } => write!(f, "unknown MCP server `{server_name}`"),
        }
    }
}

impl std::error::Error for McpServerManagerError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::JsonRpc { .. }
            | Self::InvalidResponse { .. }
            | Self::UnknownTool { .. }
            | Self::UnknownServer { .. } => None,
        }
    }
}

impl From<io::Error> for McpServerManagerError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ToolRoute {
    server_name: String,
    raw_name: String,
}

#[derive(Debug)]
struct ManagedMcpServer {
    bootstrap: McpClientBootstrap,
    process: Option<McpStdioProcess>,
    initialized: bool,
    /// v0.4.25: when set, this slot is backed by the built-in `codex exec`
    /// bridge instead of a spawned stdio process — `process` / `initialized`
    /// stay unused. One catalog, one dispatch path; only the transport differs.
    exec: Option<CodexExecBridge>,
}

impl ManagedMcpServer {
    fn new(bootstrap: McpClientBootstrap) -> Self {
        Self {
            bootstrap,
            process: None,
            initialized: false,
            exec: None,
        }
    }

    fn exec(bootstrap: McpClientBootstrap, bridge: CodexExecBridge) -> Self {
        Self {
            bootstrap,
            process: None,
            initialized: false,
            exec: Some(bridge),
        }
    }
}

/// Bootstrap record for the built-in `codex` server (no config entry backs
/// it). The stdio transport is descriptive only — the exec backend never
/// spawns through it.
fn codex_exec_bootstrap(server_name: &str, bridge: &CodexExecBridge) -> McpClientBootstrap {
    McpClientBootstrap {
        server_name: server_name.to_string(),
        normalized_name: normalize_name_for_mcp(server_name),
        tool_prefix: mcp_tool_prefix(server_name),
        signature: None,
        transport: McpClientTransport::Stdio(McpStdioTransport {
            command: bridge.codex_bin.to_string_lossy().into_owned(),
            args: vec!["exec".to_string(), "--json".to_string()],
            env: bridge.env.clone(),
            request_timeout_secs: None,
        }),
    }
}

#[derive(Debug)]
pub struct McpServerManager {
    servers: BTreeMap<String, ManagedMcpServer>,
    unsupported_servers: Vec<UnsupportedMcpServer>,
    /// v0.4.17 (RW6): failures from the most recent `discover_tools`
    /// pass. Cleared at the start of each `discover_tools` so it always
    /// reflects the latest discovery.
    discovery_failures: Vec<McpDiscoveryFailure>,
    tool_index: BTreeMap<String, ToolRoute>,
    next_request_id: u64,
}

impl McpServerManager {
    #[must_use]
    pub fn from_runtime_config(config: &RuntimeConfig) -> Self {
        Self::from_servers(config.mcp().servers())
    }

    #[must_use]
    pub fn from_servers(servers: &BTreeMap<String, ScopedMcpServerConfig>) -> Self {
        Self::from_servers_with_codex(servers, None)
    }

    /// v0.4.25: like [`from_servers`](Self::from_servers), plus the built-in
    /// `codex exec` backend. With `builtin = Some(bridge)`:
    /// - a `codex` entry that still launches the removed `codex mcp-server` is
    ///   migrated in memory onto the exec backend (keeping its executable
    ///   unless the bridge resolved a native path, its env, `-c` defaults and
    ///   explicit timeout — see [`CodexExecBridge::from_legacy_entry`]);
    /// - no `codex` entry at all ⇒ the bridge is registered as server `codex`;
    /// - any other explicit `codex` entry (e.g. the Python bridge) wins and
    ///   spawns as configured, whether or not it later discovers cleanly.
    ///
    /// With `builtin = None` behaviour is byte-identical to v0.4.24.
    #[must_use]
    pub fn from_servers_with_codex(
        servers: &BTreeMap<String, ScopedMcpServerConfig>,
        builtin: Option<&CodexExecBridge>,
    ) -> Self {
        const CODEX_SERVER: &str = "codex";
        let mut managed_servers = BTreeMap::new();
        let mut unsupported_servers = Vec::new();

        for (server_name, server_config) in servers {
            if server_config.transport() == McpTransport::Stdio {
                let bootstrap = McpClientBootstrap::from_scoped_config(server_name, server_config);
                if let (Some(bridge), McpServerConfig::Stdio(stdio)) =
                    (builtin, &server_config.config)
                {
                    if server_name == CODEX_SERVER && is_legacy_codex_mcp_server(stdio) {
                        let migrated =
                            CodexExecBridge::from_legacy_entry(stdio, Some(bridge.codex_bin.clone()));
                        managed_servers.insert(
                            server_name.clone(),
                            ManagedMcpServer::exec(bootstrap, migrated),
                        );
                        continue;
                    }
                }
                managed_servers.insert(server_name.clone(), ManagedMcpServer::new(bootstrap));
            } else {
                unsupported_servers.push(UnsupportedMcpServer {
                    server_name: server_name.clone(),
                    transport: server_config.transport(),
                    reason: format!(
                        "transport {:?} is not supported by McpServerManager",
                        server_config.transport()
                    ),
                });
            }
        }

        if let Some(bridge) = builtin {
            if !managed_servers.contains_key(CODEX_SERVER) {
                managed_servers.insert(
                    CODEX_SERVER.to_string(),
                    ManagedMcpServer::exec(codex_exec_bootstrap(CODEX_SERVER, bridge), bridge.clone()),
                );
            }
        }

        Self {
            servers: managed_servers,
            unsupported_servers,
            discovery_failures: Vec::new(),
            tool_index: BTreeMap::new(),
            next_request_id: 1,
        }
    }

    /// v0.4.25: the exec bridge backing `server_name`, if that slot runs on
    /// the built-in `codex exec` backend (built-in or migrated legacy entry).
    #[must_use]
    pub fn codex_exec_backend(&self, server_name: &str) -> Option<&CodexExecBridge> {
        self.servers.get(server_name).and_then(|s| s.exec.as_ref())
    }

    #[must_use]
    pub fn unsupported_servers(&self) -> &[UnsupportedMcpServer] {
        &self.unsupported_servers
    }

    /// v0.4.17 (RW6): per-server failures from the last `discover_tools`
    /// pass (empty if every server succeeded). The CLI/doctor layer can
    /// surface these without aborting the whole catalogue.
    #[must_use]
    pub fn discovery_failures(&self) -> &[McpDiscoveryFailure] {
        &self.discovery_failures
    }

    /// Discover the tools advertised by every configured stdio server.
    ///
    /// v0.4.17 (RW6): discovery is now **per-server resilient**. A
    /// server that fails to spawn / initialize / list its tools no
    /// longer aborts the whole catalogue — its failure is recorded in
    /// [`discovery_failures`] (and a one-line warning is written to
    /// stderr), and discovery proceeds to the remaining servers. The
    /// returned `Vec` therefore contains the union of every *healthy*
    /// server's tools. The method only returns `Err` for a genuinely
    /// unexpected internal inconsistency (e.g. a server vanishing from
    /// the map mid-pass), never for a routine per-server failure.
    pub async fn discover_tools(&mut self) -> Result<Vec<ManagedMcpTool>, McpServerManagerError> {
        let server_names = self.servers.keys().cloned().collect::<Vec<_>>();
        let mut discovered_tools = Vec::new();
        self.discovery_failures.clear();

        for server_name in server_names {
            match self.discover_server_tools(&server_name).await {
                Ok(tools) => discovered_tools.extend(tools),
                Err(error) => {
                    let reason = error.to_string();
                    // RW6: surface the failure (best-effort stderr line).
                    // Unlike progress-notification tracing (gated behind
                    // ARIS_MCP_STDERR=inherit), a server-discovery failure is a
                    // real error the user should always see, so it stays
                    // unconditional. Also record it structurally so the
                    // CLI/doctor can report it. Tools already routed for this
                    // server are dropped so we never dispatch to a broken server.
                    self.clear_routes_for_server(&server_name);
                    eprintln!(
                        "aris mcp: server `{server_name}` failed during tool discovery, skipping: {reason}"
                    );
                    self.discovery_failures.push(McpDiscoveryFailure {
                        server_name: server_name.clone(),
                        reason,
                    });
                }
            }
        }

        Ok(discovered_tools)
    }

    /// Discover one server's tools. Spawns/initializes the server (via
    /// `ensure_server_ready`) and pages through `tools/list`. Any error
    /// here is per-server (handled by the caller), never fatal to the
    /// whole pass.
    async fn discover_server_tools(
        &mut self,
        server_name: &str,
    ) -> Result<Vec<ManagedMcpTool>, McpServerManagerError> {
        if self.server_mut(server_name)?.exec.is_some() {
            self.clear_routes_for_server(server_name);
            let mut discovered_tools = Vec::new();
            for tool in CodexExecBridge::tools() {
                let qualified_name = mcp_tool_name(server_name, &tool.name);
                self.tool_index.insert(
                    qualified_name.clone(),
                    ToolRoute {
                        server_name: server_name.to_string(),
                        raw_name: tool.name.clone(),
                    },
                );
                discovered_tools.push(ManagedMcpTool {
                    server_name: server_name.to_string(),
                    qualified_name,
                    raw_name: tool.name.clone(),
                    tool,
                });
            }
            return Ok(discovered_tools);
        }
        self.ensure_server_ready(server_name).await?;
        self.clear_routes_for_server(server_name);

        let mut discovered_tools = Vec::new();
        let mut cursor = None;
        loop {
            let request_id = self.take_request_id();
            let response = {
                let server = self.server_mut(server_name)?;
                let process = server.process.as_mut().ok_or_else(|| {
                    McpServerManagerError::InvalidResponse {
                        server_name: server_name.to_string(),
                        method: "tools/list",
                        details: "server process missing after initialization".to_string(),
                    }
                })?;
                process
                    .list_tools(
                        request_id,
                        Some(McpListToolsParams {
                            cursor: cursor.clone(),
                        }),
                    )
                    .await?
            };

            if let Some(error) = response.error {
                return Err(McpServerManagerError::JsonRpc {
                    server_name: server_name.to_string(),
                    method: "tools/list",
                    error,
                });
            }

            let result = response
                .result
                .ok_or_else(|| McpServerManagerError::InvalidResponse {
                    server_name: server_name.to_string(),
                    method: "tools/list",
                    details: "missing result payload".to_string(),
                })?;

            for tool in result.tools {
                let qualified_name = mcp_tool_name(server_name, &tool.name);
                self.tool_index.insert(
                    qualified_name.clone(),
                    ToolRoute {
                        server_name: server_name.to_string(),
                        raw_name: tool.name.clone(),
                    },
                );
                discovered_tools.push(ManagedMcpTool {
                    server_name: server_name.to_string(),
                    qualified_name,
                    raw_name: tool.name.clone(),
                    tool,
                });
            }

            match result.next_cursor {
                Some(next_cursor) => cursor = Some(next_cursor),
                None => break,
            }
        }

        Ok(discovered_tools)
    }

    pub async fn call_tool(
        &mut self,
        qualified_tool_name: &str,
        arguments: Option<JsonValue>,
    ) -> Result<JsonRpcResponse<McpToolCallResult>, McpServerManagerError> {
        let route = self
            .tool_index
            .get(qualified_tool_name)
            .cloned()
            .ok_or_else(|| McpServerManagerError::UnknownTool {
                qualified_name: qualified_tool_name.to_string(),
            })?;

        if let Some(bridge) = self.server_mut(&route.server_name)?.exec.clone() {
            let request_id = self.take_request_id();
            return Ok(bridge.call(request_id, &route.raw_name, arguments).await);
        }

        self.ensure_server_ready(&route.server_name).await?;
        let request_id = self.take_request_id();
        let response =
            {
                let server = self.server_mut(&route.server_name)?;
                let process = server.process.as_mut().ok_or_else(|| {
                    McpServerManagerError::InvalidResponse {
                        server_name: route.server_name.clone(),
                        method: "tools/call",
                        details: "server process missing after initialization".to_string(),
                    }
                })?;
                process
                    .call_tool(
                        request_id,
                        McpToolCallParams {
                            name: route.raw_name,
                            arguments,
                            meta: None,
                        },
                    )
                    .await?
            };
        Ok(response)
    }

    pub async fn shutdown(&mut self) -> Result<(), McpServerManagerError> {
        let server_names = self.servers.keys().cloned().collect::<Vec<_>>();
        for server_name in server_names {
            let server = self.server_mut(&server_name)?;
            if let Some(process) = server.process.as_mut() {
                process.shutdown().await?;
            }
            server.process = None;
            server.initialized = false;
        }
        Ok(())
    }

    fn clear_routes_for_server(&mut self, server_name: &str) {
        self.tool_index
            .retain(|_, route| route.server_name != server_name);
    }

    fn server_mut(
        &mut self,
        server_name: &str,
    ) -> Result<&mut ManagedMcpServer, McpServerManagerError> {
        self.servers
            .get_mut(server_name)
            .ok_or_else(|| McpServerManagerError::UnknownServer {
                server_name: server_name.to_string(),
            })
    }

    fn take_request_id(&mut self) -> JsonRpcId {
        let id = self.next_request_id;
        self.next_request_id = self.next_request_id.saturating_add(1);
        JsonRpcId::Number(id)
    }

    async fn ensure_server_ready(
        &mut self,
        server_name: &str,
    ) -> Result<(), McpServerManagerError> {
        // v0.4.10 (M3 landmine fix): if a previous request left the
        // child dead — server crashed, was OOM-killed, or timed out
        // and we killed it ourselves in `McpStdioProcess::request` —
        // clear the slot so the spawn path below recreates it. Without
        // this we'd happily hand the next call to a dead pipe and the
        // user would see `BrokenPipe` errors instead of a transparent
        // respawn.
        if let Some(server) = self.servers.get_mut(server_name) {
            if let Some(process) = server.process.as_mut() {
                match process.try_wait() {
                    Ok(Some(_)) | Err(_) => {
                        server.process = None;
                        server.initialized = false;
                    }
                    Ok(None) => {}
                }
            }
        }

        let needs_spawn = self
            .servers
            .get(server_name)
            .map(|server| server.process.is_none())
            .ok_or_else(|| McpServerManagerError::UnknownServer {
                server_name: server_name.to_string(),
            })?;

        if needs_spawn {
            let server = self.server_mut(server_name)?;
            server.process = Some(spawn_mcp_stdio_process(&server.bootstrap)?);
            server.initialized = false;
        }

        let needs_initialize = self
            .servers
            .get(server_name)
            .map(|server| !server.initialized)
            .ok_or_else(|| McpServerManagerError::UnknownServer {
                server_name: server_name.to_string(),
            })?;

        if needs_initialize {
            let request_id = self.take_request_id();
            let response = {
                let server = self.server_mut(server_name)?;
                let process = server.process.as_mut().ok_or_else(|| {
                    McpServerManagerError::InvalidResponse {
                        server_name: server_name.to_string(),
                        method: "initialize",
                        details: "server process missing before initialize".to_string(),
                    }
                })?;
                process
                    .initialize(request_id, default_initialize_params())
                    .await?
            };

            if let Some(error) = response.error {
                return Err(McpServerManagerError::JsonRpc {
                    server_name: server_name.to_string(),
                    method: "initialize",
                    error,
                });
            }

            let Some(result) = response.result.as_ref() else {
                return Err(McpServerManagerError::InvalidResponse {
                    server_name: server_name.to_string(),
                    method: "initialize",
                    details: "missing result payload".to_string(),
                });
            };

            // v0.4.19: protocol-version negotiation guard. ARIS requested
            // REQUESTED_PROTOCOL_VERSION; a spec-compliant server echoes that,
            // or (if it doesn't support it) returns a version IT supports. If
            // the negotiated version is one ARIS does NOT speak, we must not
            // silently proceed — `tools/list` / `tools/call` would then run on
            // an incompatible protocol with opaque failures. The MCP lifecycle
            // spec says the client must terminate the connection in this case,
            // so tear the child down and clear the slot (per-server degrade;
            // `aris doctor` surfaces the reason). Healthy servers are unaffected
            // — 2025-03-26 (what we request) is in SUPPORTED_PROTOCOL_VERSIONS.
            let negotiated = result.protocol_version.clone();
            if !SUPPORTED_PROTOCOL_VERSIONS.contains(&negotiated.as_str()) {
                let server = self.server_mut(server_name)?;
                if let Some(process) = server.process.as_mut() {
                    let _ = process.terminate().await;
                }
                let server = self.server_mut(server_name)?;
                server.process = None;
                server.initialized = false;
                return Err(McpServerManagerError::InvalidResponse {
                    server_name: server_name.to_string(),
                    method: "initialize",
                    details: format!(
                        "server negotiated unsupported MCP protocol version '{negotiated}' \
                         (ARIS supports {}; requested '{REQUESTED_PROTOCOL_VERSION}')",
                        SUPPORTED_PROTOCOL_VERSIONS.join(", ")
                    ),
                });
            }

            // MCP spec mandatory step: announce that initialization
            // completed *before* marking the server ready / issuing
            // `tools/list`. Strict servers reject subsequent requests
            // without this. This is a notification (no id, no reply),
            // so it must not go through `request()`'s read loop.
            //
            // v0.4.17 (Track R / R5-P2.1): if the notification write
            // fails (broken stdin pipe, server already gone) the
            // protocol state is unrecoverable — the server never saw
            // `notifications/initialized`, so a strict server will
            // reject every later request, yet our slot still holds the
            // (now half-dead) process. Mirror `request()`'s I/O-failure
            // handling: kill the child and clear the slot so the next
            // call respawns from a clean state instead of reusing a
            // poisoned connection.
            {
                let server = self.server_mut(server_name)?;
                let process = server.process.as_mut().ok_or_else(|| {
                    McpServerManagerError::InvalidResponse {
                        server_name: server_name.to_string(),
                        method: "notifications/initialized",
                        details: "server process missing before initialized notification"
                            .to_string(),
                    }
                })?;
                if let Err(error) = process.notify_initialized().await {
                    let _ = process.terminate().await;
                    let server = self.server_mut(server_name)?;
                    server.process = None;
                    server.initialized = false;
                    return Err(error.into());
                }
            }

            let server = self.server_mut(server_name)?;
            server.initialized = true;
        }

        Ok(())
    }
}

/// v0.4.17 (R-6 / T4 prerequisite): synchronous façade over an
/// [`McpServerManager`].
///
/// `McpServerManager`'s API is fully `async`, but the CLI's tool
/// dispatch path (`ToolExecutor::execute`) is a synchronous trait
/// method. This handle owns its own single-threaded tokio runtime and
/// the manager, and exposes blocking wrappers that `block_on` the async
/// calls — the same bridge pattern already proven by the Bash tool
/// (`bash.rs` `Builder::new_current_thread() + block_on`).
///
/// SPIKE-A (R3-P2.2) hard constraint: this handle MUST NOT be used from
/// inside a tokio runtime — `block_on` panics with "Cannot start a
/// runtime from within a runtime" if it is. The current CLI topology
/// guarantees this (tool dispatch runs after the stream `block_on` has
/// already returned), and every sync entry point asserts it in debug
/// builds so a future regression is caught immediately rather than
/// silently risking a nested-runtime panic.
///
/// This is the single interface Track C (the `CliToolExecutor`
/// integration) is expected to consume: Track C never has to touch any
/// `async` code.
#[derive(Debug)]
pub struct McpManagerHandle {
    runtime: tokio::runtime::Runtime,
    manager: McpServerManager,
}

impl McpManagerHandle {
    /// Build a sync handle from a runtime config. Constructs the
    /// dedicated `current_thread` runtime and the manager. Returns the
    /// runtime-construction error if the (rare) runtime build fails.
    pub fn from_runtime_config(config: &RuntimeConfig) -> io::Result<Self> {
        Self::from_manager(McpServerManager::from_runtime_config(config))
    }

    /// Build a sync handle wrapping an already-constructed manager.
    pub fn from_manager(manager: McpServerManager) -> io::Result<Self> {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()?;
        Ok(Self { runtime, manager })
    }

    /// Debug-only guard: panics in debug builds if called from within a
    /// tokio runtime context, where `block_on` would itself panic. In
    /// release builds this is a no-op (the topology invariant is
    /// upheld; the assert exists to catch regressions during dev).
    fn assert_not_in_runtime() {
        debug_assert!(
            tokio::runtime::Handle::try_current().is_err(),
            "McpManagerHandle must not be used inside a tokio runtime (block_on would panic)"
        );
    }

    /// Discover every healthy server's tools (RW6: per-server
    /// resilient). Blocking.
    pub fn discover_tools(&mut self) -> Result<Vec<ManagedMcpTool>, McpServerManagerError> {
        Self::assert_not_in_runtime();
        let manager = &mut self.manager;
        self.runtime.block_on(manager.discover_tools())
    }

    /// Call a qualified MCP tool (`mcp__<server>__<tool>`). Blocking.
    pub fn call_tool(
        &mut self,
        qualified_tool_name: &str,
        arguments: Option<JsonValue>,
    ) -> Result<JsonRpcResponse<McpToolCallResult>, McpServerManagerError> {
        Self::assert_not_in_runtime();
        let manager = &mut self.manager;
        self.runtime
            .block_on(manager.call_tool(qualified_tool_name, arguments))
    }

    /// Shut every spawned child down cleanly. Blocking.
    pub fn shutdown(&mut self) -> Result<(), McpServerManagerError> {
        Self::assert_not_in_runtime();
        let manager = &mut self.manager;
        self.runtime.block_on(manager.shutdown())
    }

    /// Read-only view of servers that were configured but use an
    /// unsupported (non-stdio) transport.
    #[must_use]
    pub fn unsupported_servers(&self) -> &[UnsupportedMcpServer] {
        self.manager.unsupported_servers()
    }

    /// Read-only view of per-server failures from the last
    /// `discover_tools` pass.
    #[must_use]
    pub fn discovery_failures(&self) -> &[McpDiscoveryFailure] {
        self.manager.discovery_failures()
    }

    /// Borrow the wrapped manager (read-only). Escape hatch for any
    /// state query not yet surfaced as a dedicated method.
    #[must_use]
    pub fn manager(&self) -> &McpServerManager {
        &self.manager
    }
}

/// v0.4.17 (M6): upper bound on a single MCP frame's declared
/// `Content-Length`. A frame larger than this is rejected before we
/// allocate the receive buffer, so a hostile/buggy server can't OOM
/// the process by advertising an enormous length. 64 MiB comfortably
/// covers legitimate large tool results (multi-MB agent outputs) while
/// still bounding the worst case.
const MAX_CONTENT_LENGTH: usize = 64 * 1024 * 1024;

#[derive(Debug)]
pub struct McpStdioProcess {
    child: Child,
    /// v0.4.17 (RW9 / #286): the stdin write half and stdout read half
    /// are owned independently so [`request`] can drive them
    /// concurrently (write task + read pump under one `tokio::join!`),
    /// breaking the pipe-buffer deadlock where a large request body
    /// fills the child's stdin pipe while the child is blocked writing
    /// its stdout response into a pipe we haven't started draining.
    /// They are `Option` only so they can be temporarily `take`n into
    /// the join; in the steady state (and on every public method entry)
    /// both are `Some`.
    stdin: Option<ChildStdin>,
    stdout: Option<BufReader<ChildStdout>>,
    /// v0.4.13 P1.D: per-server timeout override copied from the
    /// transport. `None` means fall through to
    /// `MCP_REQUEST_TIMEOUT_SECS` env / 300s default at request time.
    /// We store the raw `Option<u64>` rather than a `Duration` so the
    /// clamp + env-fallback logic stays centralised in
    /// `mcp_request_timeout`.
    request_timeout_override_secs: Option<u64>,
}

/// v0.4.17 (Track R / R5-P1): outcome of [`McpStdioProcess::request`]'s
/// concurrent write+read round trip (the `select!` state machine).
///
/// * `Killed(err)` — a fatal-for-the-connection I/O error (write failed
///   first, or a read error). The caller kills the child (so the next
///   call respawns) and propagates `err`.
/// * `ResponseWithFlag(resp, kill_after)` — a successful read. The IO
///   halves are still healthy and get put back, UNLESS `kill_after` is
///   set: that flags the "response-wins-with-late-write-error" branch,
///   where the answer is valid but stdin is poisoned, so the connection
///   is torn down and respawned on the next call.
enum RoundTrip<R> {
    ResponseWithFlag(R, bool),
    Killed(io::Error),
}

/// Drive one MCP request's write half and response read pump
/// CONCURRENTLY over the borrowed stdio halves, collapsing the outcome
/// into a [`RoundTrip`]. Factored out of [`McpStdioProcess::request`]
/// (R5-P1) so that method stays small and this state machine is
/// self-contained.
///
/// Why concurrent (RW9 / #286): a request body larger than the OS stdin
/// pipe buffer blocks our `write_all` until the child drains stdin, but
/// an agent-style child often doesn't drain stdin until *after* it has
/// written its response to stdout — whose pipe fills (blocking the
/// child) because we haven't started reading. Both sides wedge. Racing
/// write + read drains the child's stdout while we feed its stdin, so
/// neither pipe can back-pressure into a hang.
///
/// State machine (R5-P1 — fixes the `tokio::join!` regression where a
/// broken write half still blocked the read pump until the global
/// timeout):
///   1. WRITE FAILS FIRST — abandon the read immediately and return the
///      write error (`Killed`). We do NOT wait for a read frame that may
///      never arrive, so a server that drops our stdin while holding
///      stdout open fails fast instead of at the global timeout. This is
///      the regression fix.
///   2. WRITE SUCCEEDS — fall through to a pure read loop bounded by the
///      caller's outer timeout (unchanged behaviour for the common
///      path).
///   3. RESPONSE FIRST ("response wins") — a matched response id
///      normally implies the server already drained our write, so the
///      write future is essentially done. For the rare interleaving
///      where the read completes while the write future is still
///      pending, we DEFINE the contract: await the write future to
///      completion (still inside the caller's outer timeout). If it
///      ultimately errors, the response is STILL returned via
///      `ResponseWithFlag(resp, true)` — the server demonstrably
///      received and answered the request — but the connection is no
///      longer trustworthy (stdin in an unknown state), so the `true`
///      flag tells the caller to tear the child down and force a clean
///      respawn on the next call.
///
/// The read pump skips JSON-RPC notifications (no `id` / `id == null`,
/// preserved verbatim from v0.4.13 #151 / #172) and returns the first
/// id-bearing frame; a generic `Value` is parsed first so a notification
/// frame can't fail the mandatory-`id` `JsonRpcResponse` deserialize.
async fn run_round_trip<TResult: DeserializeOwned>(
    stdin: &mut ChildStdin,
    stdout: &mut BufReader<ChildStdout>,
    encoded: &[u8],
) -> RoundTrip<JsonRpcResponse<TResult>> {
    let write_fut = async {
        stdin.write_all(encoded).await?;
        stdin.flush().await?;
        Ok::<(), io::Error>(())
    };

    let read_fut = async {
        // v0.4.17 push-gate (BUG A): notification frames are non-fatal — codex's
        // MCP server emits dozens-to-hundreds of `codex/event` progress
        // notifications between request and response. Logging one stderr line per
        // frame spammed the REPL on every review. Trace them only when the
        // operator opts in via the same `ARIS_MCP_STDERR=inherit` debug escape
        // hatch used for child stderr (read once per round-trip); otherwise skip
        // silently.
        let trace_notifications = std::env::var("ARIS_MCP_STDERR")
            .map(|value| value.eq_ignore_ascii_case("inherit"))
            .unwrap_or(false);
        loop {
            let payload = read_frame_from(stdout).await?;
            let value: JsonValue = serde_json::from_slice(&payload)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
            let frame_id = value.as_object().and_then(|object| object.get("id"));
            match frame_id {
                None | Some(JsonValue::Null) => {
                    // Notification frame — read on. Trace only when opted in.
                    if trace_notifications {
                        let method = value
                            .as_object()
                            .and_then(|object| object.get("method"))
                            .and_then(JsonValue::as_str)
                            .unwrap_or("?");
                        eprintln!("aris mcp: notification skipped: method={method}");
                    }
                }
                Some(_) => {
                    let response: JsonRpcResponse<TResult> = serde_json::from_value(value)
                        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
                    return Ok::<JsonRpcResponse<TResult>, io::Error>(response);
                }
            }
        }
    };

    tokio::pin!(write_fut);
    tokio::pin!(read_fut);

    tokio::select! {
        // Bias toward the write arm so a write error ready in the same
        // poll as a read result is surfaced first (more actionable),
        // matching the old serial path's ordering.
        biased;

        write_result = &mut write_fut => match write_result {
            // Case 1: write failed first. Abandon the read.
            Err(write_err) => RoundTrip::Killed(write_err),
            // Case 2: write succeeded. Pure read loop under the outer
            // deadline.
            Ok(()) => match (&mut read_fut).await {
                Ok(resp) => RoundTrip::ResponseWithFlag(resp, false),
                Err(read_err) => RoundTrip::Killed(read_err),
            },
        },
        read_result = &mut read_fut => match read_result {
            // Case 3: response wins. Await the still-pending write; a
            // late write error keeps the response but poisons the
            // connection (flag a kill).
            Ok(response) => {
                let kill_after = (&mut write_fut).await.is_err();
                RoundTrip::ResponseWithFlag(response, kill_after)
            }
            Err(read_err) => RoundTrip::Killed(read_err),
        },
    }
}

impl McpStdioProcess {
    pub fn spawn(transport: &McpStdioTransport) -> io::Result<Self> {
        // v0.4.17 (RW6): by default we DISCARD the child's stderr
        // rather than letting it `inherit()` straight onto the aris
        // terminal. Two reasons:
        //   1. agent-style MCP servers are chatty on stderr; inheriting
        //      interleaves their logs into the user's REPL output.
        //   2. correctness — if a server writes a lot to stderr and
        //      nothing reads it, a *piped* stderr buffer fills and the
        //      server BLOCKS on its next stderr write (the same class
        //      of pipe-full hang fixed for stdin in v0.4.13).
        // v0.4.17 (Track R / R5-P2.2): we used to satisfy (2) by piping
        // stderr and draining it on a background `tokio::spawn`. But
        // `spawn` is a *synchronous* method, so that drain task made it
        // implicitly depend on an ambient tokio runtime — an unclean
        // contract for a public `spawn` API even though every current
        // caller happens to run inside the manager's runtime. Since the
        // default behaviour is "discard" anyway, route stderr to
        // `Stdio::null()` instead: the kernel sends it to /dev/null, so
        // it can never back-pressure and there is no drain task and no
        // runtime dependency. The `ARIS_MCP_STDERR=inherit` escape hatch
        // for debugging is preserved.
        let inherit_stderr = std::env::var("ARIS_MCP_STDERR")
            .map(|value| value.eq_ignore_ascii_case("inherit"))
            .unwrap_or(false);

        let mut command = Command::new(&transport.command);
        command
            .args(&transport.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(if inherit_stderr {
                Stdio::inherit()
            } else {
                Stdio::null()
            });
        apply_env(&mut command, &transport.env);

        let mut child = command.spawn()?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("stdio MCP process missing stdin pipe"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("stdio MCP process missing stdout pipe"))?;

        Ok(Self {
            child,
            stdin: Some(stdin),
            stdout: Some(BufReader::new(stdout)),
            request_timeout_override_secs: transport.request_timeout_secs,
        })
    }

    /// Borrow the stdin write half, erroring if it is currently `take`n.
    /// The half is only absent transiently inside [`request`]'s
    /// `tokio::join!`; any caller observing `None` means a prior
    /// `request` was dropped mid-flight (e.g. a panic between `take`
    /// and put-back), so we surface a clean error rather than panic.
    fn stdin_mut(&mut self) -> io::Result<&mut ChildStdin> {
        self.stdin.as_mut().ok_or_else(|| {
            io::Error::other("MCP stdio stdin half unavailable (request in flight)")
        })
    }

    /// Borrow the stdout read half; see [`stdin_mut`] for the `None`
    /// rationale.
    fn stdout_mut(&mut self) -> io::Result<&mut BufReader<ChildStdout>> {
        self.stdout.as_mut().ok_or_else(|| {
            io::Error::other("MCP stdio stdout half unavailable (request in flight)")
        })
    }

    pub async fn write_all(&mut self, bytes: &[u8]) -> io::Result<()> {
        self.stdin_mut()?.write_all(bytes).await
    }

    pub async fn flush(&mut self) -> io::Result<()> {
        self.stdin_mut()?.flush().await
    }

    pub async fn write_line(&mut self, line: &str) -> io::Result<()> {
        self.write_all(line.as_bytes()).await?;
        self.write_all(b"\n").await?;
        self.flush().await
    }

    pub async fn read_line(&mut self) -> io::Result<String> {
        let mut line = String::new();
        let bytes_read = self.stdout_mut()?.read_line(&mut line).await?;
        if bytes_read == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "MCP stdio stream closed while reading line",
            ));
        }
        Ok(line)
    }

    pub async fn read_available(&mut self) -> io::Result<Vec<u8>> {
        let mut buffer = vec![0_u8; 4096];
        let read = self.stdout_mut()?.read(&mut buffer).await?;
        buffer.truncate(read);
        Ok(buffer)
    }

    pub async fn write_frame(&mut self, payload: &[u8]) -> io::Result<()> {
        let encoded = encode_frame(payload);
        self.write_all(&encoded).await?;
        self.flush().await
    }

    pub async fn read_frame(&mut self) -> io::Result<Vec<u8>> {
        let stdout = self.stdout_mut()?;
        read_frame_from(stdout).await
    }

    pub async fn write_jsonrpc_message<T: Serialize>(&mut self, message: &T) -> io::Result<()> {
        let body = serde_json::to_vec(message)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        self.write_frame(&body).await
    }

    pub async fn read_jsonrpc_message<T: DeserializeOwned>(&mut self) -> io::Result<T> {
        let payload = self.read_frame().await?;
        serde_json::from_slice(&payload)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
    }

    pub async fn send_request<T: Serialize>(
        &mut self,
        request: &JsonRpcRequest<T>,
    ) -> io::Result<()> {
        self.write_jsonrpc_message(request).await
    }

    pub async fn read_response<T: DeserializeOwned>(&mut self) -> io::Result<JsonRpcResponse<T>> {
        self.read_jsonrpc_message().await
    }

    /// Send a JSON-RPC request and wait for the matching response.
    ///
    /// v0.4.10 (M3 landmine fix): this used to forward straight to
    /// `read_response()` with no timeout and no correlation check. If
    /// the MCP server hung after `initialize`, `aris` would spin
    /// forever on the read (this was the #151 / #172 "Calling
    /// codex..." stall root cause). It also accepted whatever id the
    /// server emitted, so a buggy/stale response could be returned for
    /// a different in-flight call.
    ///
    /// Behaviour now (post-codex-review):
    /// * The entire send+read round trip is wrapped in
    ///   `tokio::time::timeout`. Default 300s (5 min, covers agent-style
    ///   MCP servers like codex), override via `MCP_REQUEST_TIMEOUT_SECS`
    ///   env (clamped 1..=1800). Wrapping both halves means a server
    ///   that blocks on stdin (write-side hang because the pipe buffer
    ///   fills) also unblocks the caller.
    /// * After a successful read, the response id must equal the
    ///   request id.
    /// * On *any* failure mode (timeout, I/O error during
    ///   send/read, id mismatch) we `kill().await` the child so the
    ///   stdio pipes are flushed and the next call respawns from a
    ///   clean state. `kill().await` (vs `start_kill()`) reaps the
    ///   process — avoiding a zombie window where the manager's
    ///   `try_wait()` could still see `Ok(None)` and reuse a poisoned
    ///   pipe.
    pub async fn request<TParams: Serialize, TResult: DeserializeOwned>(
        &mut self,
        id: JsonRpcId,
        method: impl Into<String>,
        params: Option<TParams>,
    ) -> io::Result<JsonRpcResponse<TResult>> {
        let request = JsonRpcRequest::new(id.clone(), method, params);
        let timeout = mcp_request_timeout(self.request_timeout_override_secs);

        // Encode the request as one NDJSON frame up front (v0.4.17 /
        // Track R) so the write task owns a plain `Vec<u8>` and doesn't
        // need to borrow `self`. `serde_json::to_vec` produces a single
        // line (any `\n` inside string values is escaped), and
        // `encode_frame` appends the terminating `\n`.
        let frame = serde_json::to_vec(&request)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        let encoded = encode_frame(&frame);

        // v0.4.17 (RW9 / #286, Track R / R5-P1): the write half and read
        // pump are driven CONCURRENTLY by `run_round_trip` (see its docs
        // for the deadlock rationale and the write-fails-first /
        // write-then-read / response-wins state machine).
        //
        // The two owned IO halves are taken out of `self` for the
        // duration of the round trip (borrow split: a single
        // `&mut self` can't lend two disjoint async borrows into two
        // concurrent futures). On the success path we put them back; on
        // any kill path we do NOT — the process is dead and
        // `ensure_server_ready` respawns a fresh `McpStdioProcess` (new
        // halves) on the next call, so leaving the slots empty is
        // correct and avoids handing out half-broken pipes.
        let mut stdin = self
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("MCP stdio stdin half unavailable"))?;
        let mut stdout = self
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("MCP stdio stdout half unavailable"))?;

        // The concurrent write+read `select!` state machine lives in the
        // free `run_round_trip` helper (R5-P1) so this method stays
        // focused on orchestration (take halves -> dispatch -> put back
        // or kill -> id check). See that helper for the full case
        // analysis (write-fails-first short-circuit, write-then-read,
        // response-wins-with-late-write-error).
        let round_trip =
            tokio::time::timeout(timeout, run_round_trip(&mut stdin, &mut stdout, &encoded)).await;

        let (response, kill_after): (JsonRpcResponse<TResult>, bool) = match round_trip {
            Ok(RoundTrip::ResponseWithFlag(response, kill_after)) => (response, kill_after),
            Ok(RoundTrip::Killed(error)) => {
                // I/O error during send or read. The stdio buffers are
                // now ambiguous and/or a half-write is in flight — kill
                // so the next call respawns cleanly. We deliberately do
                // NOT put the IO halves back: the process is being torn
                // down.
                let _ = self.child.kill().await;
                return Err(error);
            }
            Err(_elapsed) => {
                let _ = self.child.kill().await;
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!(
                        "MCP server did not respond within {}s (override via per-server requestTimeoutSecs or MCP_REQUEST_TIMEOUT_SECS env, max 1800s)",
                        timeout.as_secs()
                    ),
                ));
            }
        };

        if kill_after {
            // Response-wins-with-late-write-error: the answer is valid
            // (`response` below is returned `Ok`) but stdin is poisoned,
            // so tear the connection down and let `ensure_server_ready`
            // respawn on the next call. Do not put the halves back.
            let _ = self.child.kill().await;
        } else {
            // Success path: both halves are healthy, restore them so the
            // struct is consistent (both-`Some`) for the next call /
            // `shutdown`.
            self.stdin = Some(stdin);
            self.stdout = Some(stdout);
        }

        if response.id != id {
            // Correlation mismatch: server is desynced or buggy. Treat
            // as fatal for this connection so we respawn cleanly. (If
            // `kill_after` already killed the child above, a second
            // `kill().await` is a harmless no-op.)
            let _ = self.child.kill().await;
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "MCP response id mismatch: expected {:?}, got {:?}",
                    id, response.id
                ),
            ));
        }
        Ok(response)
    }

    /// Non-blocking liveness peek — `Ok(None)` means the child is still
    /// running, `Ok(Some(_))` means it has exited, `Err` means we
    /// couldn't poll. Used by `McpServerManager::ensure_server_ready`
    /// to detect crashed servers and respawn them transparently.
    pub fn try_wait(&mut self) -> io::Result<Option<std::process::ExitStatus>> {
        self.child.try_wait()
    }

    pub async fn initialize(
        &mut self,
        id: JsonRpcId,
        params: McpInitializeParams,
    ) -> io::Result<JsonRpcResponse<McpInitializeResult>> {
        self.request(id, "initialize", Some(params)).await
    }

    /// Send a fire-and-forget JSON-RPC notification (no `id`, no
    /// response read).
    ///
    /// Unlike [`request`], this writes a single NDJSON frame (v0.4.17 /
    /// Track R: one JSON object + `\n`, the canonical MCP stdio wire
    /// format) and returns immediately — it must not enter the response
    /// read loop, because a notification frame never gets a reply. We
    /// reuse [`write_frame`] (so the wire framing stays identical to
    /// every other message) but build the body by hand to guarantee the
    /// `id` field is entirely absent (an explicit `id: null` would be a
    /// *response* shape, not a notification).
    pub async fn notify(
        &mut self,
        method: &str,
        params: Option<JsonValue>,
    ) -> io::Result<()> {
        let mut message = serde_json::Map::new();
        message.insert("jsonrpc".to_string(), JsonValue::String("2.0".to_string()));
        message.insert("method".to_string(), JsonValue::String(method.to_string()));
        if let Some(params) = params {
            message.insert("params".to_string(), params);
        }
        let body = serde_json::to_vec(&JsonValue::Object(message))
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        self.write_frame(&body).await
    }

    /// MCP spec: after a successful `initialize` round trip the client
    /// MUST send a `notifications/initialized` notification before
    /// issuing any further requests. Strict servers (including the
    /// official SDK servers) reject `tools/list` until they have
    /// received it.
    pub async fn notify_initialized(&mut self) -> io::Result<()> {
        self.notify("notifications/initialized", None).await
    }

    pub async fn list_tools(
        &mut self,
        id: JsonRpcId,
        params: Option<McpListToolsParams>,
    ) -> io::Result<JsonRpcResponse<McpListToolsResult>> {
        self.request(id, "tools/list", params).await
    }

    pub async fn call_tool(
        &mut self,
        id: JsonRpcId,
        params: McpToolCallParams,
    ) -> io::Result<JsonRpcResponse<McpToolCallResult>> {
        self.request(id, "tools/call", Some(params)).await
    }

    pub async fn list_resources(
        &mut self,
        id: JsonRpcId,
        params: Option<McpListResourcesParams>,
    ) -> io::Result<JsonRpcResponse<McpListResourcesResult>> {
        self.request(id, "resources/list", params).await
    }

    pub async fn read_resource(
        &mut self,
        id: JsonRpcId,
        params: McpReadResourceParams,
    ) -> io::Result<JsonRpcResponse<McpReadResourceResult>> {
        self.request(id, "resources/read", Some(params)).await
    }

    pub async fn terminate(&mut self) -> io::Result<()> {
        self.child.kill().await
    }

    pub async fn wait(&mut self) -> io::Result<std::process::ExitStatus> {
        self.child.wait().await
    }

    async fn shutdown(&mut self) -> io::Result<()> {
        if self.child.try_wait()?.is_none() {
            self.child.kill().await?;
        }
        let _ = self.child.wait().await?;
        Ok(())
    }
}

pub fn spawn_mcp_stdio_process(bootstrap: &McpClientBootstrap) -> io::Result<McpStdioProcess> {
    match &bootstrap.transport {
        McpClientTransport::Stdio(transport) => McpStdioProcess::spawn(transport),
        other => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!(
                "MCP bootstrap transport for {} is not stdio: {other:?}",
                bootstrap.server_name
            ),
        )),
    }
}

fn apply_env(command: &mut Command, env: &BTreeMap<String, String>) {
    for (key, value) in env {
        command.env(key, value);
    }
}

/// v0.4.17 (Track R): encode one JSON-RPC message as a **newline-
/// delimited JSON** (NDJSON) frame — the canonical MCP stdio transport
/// wire format (one JSON object per line, terminated by `\n`).
///
/// The real-machine e2e blocker this fixes: we previously emitted the
/// LSP-style `Content-Length: N\r\n\r\n{json}` header framing, which is
/// LSP's dialect, NOT MCP stdio's. Spec-correct servers (e.g.
/// `codex mcp-server`) read line-by-line and stayed completely silent
/// on our header-prefixed bytes, so every request timed out. MCP stdio
/// is newline-delimited JSON-RPC: exactly one message per line.
///
/// `payload` is an already-serialised JSON object's bytes (no embedded
/// raw newline — `serde_json` escapes any `\n` inside string values as
/// `\\n`, so a single object never spans lines). We simply append the
/// `\n` terminator. A `\r` is intentionally NOT added: bare-LF is the
/// MCP convention and the legacy reader tolerates either anyway.
fn encode_frame(payload: &[u8]) -> Vec<u8> {
    let mut framed = Vec::with_capacity(payload.len() + 1);
    framed.extend_from_slice(payload);
    framed.push(b'\n');
    framed
}

/// Read one JSON-RPC message frame from `stdout`, auto-detecting the
/// wire dialect (v0.4.17 / Track R).
///
/// Factored out of `McpStdioProcess::read_frame` so the read pump in
/// `request` (RW9 / #286) can borrow the stdout half on its own while
/// the write task independently borrows stdin.
///
/// Two dialects are accepted on the *read* side for maximum
/// interoperability (we only ever *write* NDJSON):
///   * **NDJSON (canonical MCP stdio)** — one JSON object per line. This
///     is what real servers (codex, the official SDK servers) speak. A
///     non-`content-length:` line is taken verbatim as one message's
///     bytes (trailing CR/LF stripped).
///   * **Legacy LSP `Content-Length` framing** — a line beginning
///     `content-length:` (case-insensitive, leading whitespace
///     tolerated) switches to [`read_legacy_lsp_frame`], which reads the
///     remaining headers + the exact body (M6's bare-LF / case /
///     leading-space tolerance and 64 MiB cap all live there). This keeps
///     us bidirectionally tolerant of any server still on the LSP dialect.
///
/// Blank / all-whitespace lines are skipped before classification (some
/// servers pad output with stray newlines). The NDJSON path bounds each
/// line at `MAX_CONTENT_LENGTH` via [`read_line_capped`] so a server
/// that never emits a newline can't make us buffer unboundedly and OOM.
async fn read_frame_from<R: AsyncBufReadExt + AsyncReadExt + Unpin>(
    stdout: &mut R,
) -> io::Result<Vec<u8>> {
    loop {
        let line = read_line_capped(stdout).await?;
        // Skip blank / all-whitespace lines (stray padding newlines).
        let trimmed_end = line.trim_end_matches(['\r', '\n']);
        if trimmed_end.trim().is_empty() {
            continue;
        }
        // Legacy LSP framing: a `content-length:` header line (case-
        // insensitive, leading whitespace tolerated) switches dialects.
        if let Some((key, value)) = trimmed_end.split_once(':') {
            if key.trim().eq_ignore_ascii_case("content-length") {
                return read_legacy_lsp_frame(stdout, value).await;
            }
        }
        // NDJSON: the whole line (minus its terminator) is one message.
        return Ok(trimmed_end.as_bytes().to_vec());
    }
}

/// Read a single line from `stdout`, bounding its length at
/// `MAX_CONTENT_LENGTH` so a server that never emits a newline cannot
/// drive unbounded buffering (the NDJSON analogue of M6's
/// `Content-Length` cap). Reads byte-by-byte through the `BufReader`'s
/// own buffer (cheap — the reader batches the underlying syscalls) and
/// stops at the first `\n` (kept) or at EOF.
///
/// EOF with zero bytes read surfaces `UnexpectedEof` (stream closed),
/// matching the legacy reader's "stream closed while reading" contract.
async fn read_line_capped<R: AsyncBufReadExt + AsyncReadExt + Unpin>(
    stdout: &mut R,
) -> io::Result<String> {
    let mut buf: Vec<u8> = Vec::new();
    loop {
        let mut byte = [0_u8; 1];
        let n = stdout.read(&mut byte).await?;
        if n == 0 {
            if buf.is_empty() {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "MCP stdio stream closed while reading line",
                ));
            }
            break;
        }
        buf.push(byte[0]);
        if byte[0] == b'\n' {
            break;
        }
        if buf.len() > MAX_CONTENT_LENGTH {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "MCP NDJSON line exceeds maximum {MAX_CONTENT_LENGTH} bytes without a newline"
                ),
            ));
        }
    }
    String::from_utf8(buf).map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
}

/// Legacy LSP `Content-Length` framing reader (v0.4.17 / M6 tolerance,
/// preserved on the legacy path). Entered from [`read_frame_from`] once
/// the first line is recognised as a `content-length:` header;
/// `first_value` is that header's value portion (after the `:`). Reads
/// any further headers, then the empty separator line, then exactly
/// `Content-Length` body bytes.
///
/// Tolerances (all from M6): bare-LF (`\n`) header/body separators,
/// case-insensitive + leading-whitespace `Content-Length`, and the
/// `MAX_CONTENT_LENGTH` cap rejecting an oversized declared length
/// before the receive buffer is allocated (anti-OOM).
async fn read_legacy_lsp_frame<R: AsyncBufReadExt + AsyncReadExt + Unpin>(
    stdout: &mut R,
    first_value: &str,
) -> io::Result<Vec<u8>> {
    let mut content_length = Some(parse_content_length(first_value)?);
    loop {
        let mut line = String::new();
        let bytes_read = stdout.read_line(&mut line).await?;
        if bytes_read == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "MCP stdio stream closed while reading headers",
            ));
        }
        // v0.4.17 (M6): the header/body separator is an empty line.
        // Accept both CRLF (`\r\n`) and bare LF (`\n`) terminators
        // so servers that don't strictly emit CRLF still parse.
        // `read_line` keeps the trailing newline, so an empty line
        // is one whose only bytes are CR/LF.
        if line.trim_end_matches(['\r', '\n']).is_empty() {
            break;
        }
        // v0.4.17 (M6): match `Content-Length` case-insensitively
        // and tolerate leading whitespace on the header name. The
        // LSP/MCP framing convention is canonical-cased, but real
        // servers occasionally emit `content-length:`.
        if let Some((key, value)) = line.split_once(':') {
            if key.trim().eq_ignore_ascii_case("content-length") {
                content_length = Some(parse_content_length(value)?);
            }
        }
    }

    let content_length = content_length.ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "missing Content-Length header")
    })?;
    let mut payload = vec![0_u8; content_length];
    stdout.read_exact(&mut payload).await?;
    Ok(payload)
}

/// Parse + bound-check a `Content-Length` header value (M6). Rejects a
/// declared length above `MAX_CONTENT_LENGTH` before any buffer is
/// allocated so a malicious/buggy server can't OOM the process.
fn parse_content_length(value: &str) -> io::Result<usize> {
    let parsed = value
        .trim()
        .parse::<usize>()
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    if parsed > MAX_CONTENT_LENGTH {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("MCP frame Content-Length {parsed} exceeds maximum {MAX_CONTENT_LENGTH}"),
        ));
    }
    Ok(parsed)
}

/// Resolve the MCP request read timeout. Priority is:
///   1. per-server `override_secs` (from
///      `McpStdioServerConfig.request_timeout_secs` — v0.4.13 P1.D),
///   2. global `MCP_REQUEST_TIMEOUT_SECS` env (set process-wide),
///   3. 300s default.
///
/// Every layer is clamped to 1..=1800s so a bogus value can't disable
/// the timeout entirely or make it absurdly long.
///
/// Rationale for the 5-minute default: the most common MCP servers
/// users wire into `aris` are agent-style (codex, oracle, claude). A
/// single tool call there routinely takes 60-180s of model think time
/// before the first response byte. The earlier 60s default would have
/// killed those mid-call. 300s comfortably covers the p95 of observed
/// agent tool calls while still bounding a runaway server.
///
/// Rationale for the per-server override: when a user wires both a
/// fast MCP (e.g. filesystem) and a slow agent MCP (codex) into the
/// same session, a single env-level setting trades off responsiveness
/// on one for safety on the other. Per-server lets each pick the
/// right ceiling without affecting the others.
fn mcp_request_timeout(override_secs: Option<u64>) -> std::time::Duration {
    const DEFAULT_SECS: u64 = 300;
    const MIN_SECS: u64 = 1;
    const MAX_SECS: u64 = 1800;

    if let Some(secs) = override_secs {
        return std::time::Duration::from_secs(secs.clamp(MIN_SECS, MAX_SECS));
    }
    let secs = std::env::var("MCP_REQUEST_TIMEOUT_SECS")
        .ok()
        .and_then(|s| s.parse::<u64>().ok())
        .map(|n| n.clamp(MIN_SECS, MAX_SECS))
        .unwrap_or(DEFAULT_SECS);
    std::time::Duration::from_secs(secs)
}

/// v0.4.19: MCP protocol revisions ARIS can speak. The stdio transport framing
/// (newline-delimited JSON-RPC) is identical across these published revisions,
/// so ARIS accepts whichever one the server negotiates back — but ONLY these.
/// Per the MCP lifecycle spec, a client that cannot agree on a version with the
/// server must terminate the connection rather than proceed on an incompatible
/// protocol; `ensure_server_ready` enforces that. When a new revision is
/// adopted, add it here.
const SUPPORTED_PROTOCOL_VERSIONS: &[&str] =
    &["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

/// The protocol version ARIS advertises in `initialize`. Kept at 2025-03-26 —
/// proven against `codex mcp-server` (v0.4.17 e2e) and within
/// `SUPPORTED_PROTOCOL_VERSIONS`. A spec-compliant server that prefers a newer
/// revision responds with a version it shares; `ensure_server_ready` validates
/// that response. (Bumping the *request* to the current revision is a separate,
/// riskier change — a strict server could reject an unknown newer request —
/// and is intentionally out of scope here; the negotiation guard is the fix.)
const REQUESTED_PROTOCOL_VERSION: &str = "2025-03-26";

fn default_initialize_params() -> McpInitializeParams {
    McpInitializeParams {
        protocol_version: REQUESTED_PROTOCOL_VERSION.to_string(),
        capabilities: JsonValue::Object(serde_json::Map::new()),
        client_info: McpInitializeClientInfo {
            name: "runtime".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
        },
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::fs;
    use std::io::ErrorKind;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    use std::path::{Path, PathBuf};
    use std::time::{SystemTime, UNIX_EPOCH};

    use serde_json::json;
    use tokio::runtime::Builder;

    use crate::config::{
        ConfigSource, McpRemoteServerConfig, McpSdkServerConfig, McpServerConfig,
        McpStdioServerConfig, McpWebSocketServerConfig, ScopedMcpServerConfig,
    };
    use crate::mcp::mcp_tool_name;
    use crate::mcp_client::McpClientBootstrap;

    use super::{
        mcp_request_timeout, spawn_mcp_stdio_process, JsonRpcId, JsonRpcRequest, JsonRpcResponse,
        McpInitializeClientInfo, McpInitializeParams, McpInitializeResult, McpInitializeServerInfo,
        McpListToolsResult, McpManagerHandle, McpReadResourceParams, McpReadResourceResult,
        McpServerManager, McpServerManagerError, McpStdioProcess, McpTool, McpToolCallParams,
    };

    fn temp_dir() -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should be after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("runtime-mcp-stdio-{nanos}"))
    }

    fn make_executable(script_path: &Path) {
        #[cfg(not(unix))]
        let _ = script_path;

        #[cfg(unix)]
        {
            let mut permissions = fs::metadata(script_path).expect("metadata").permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(script_path, permissions).expect("chmod");
        }
    }

    fn write_echo_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("echo-mcp.sh");
        fs::write(
            &script_path,
            "#!/bin/sh\nprintf 'READY:%s\\n' \"$MCP_TEST_TOKEN\"\nIFS= read -r line\nprintf 'ECHO:%s\\n' \"$line\"\n",
        )
        .expect("write script");
        make_executable(&script_path);
        script_path
    }

    // v0.4.17 (Track R): the fake MCP servers speak NDJSON (one JSON
    // object per line), the canonical MCP stdio dialect — same as the
    // real `codex mcp-server`. The earlier `Content-Length` framing was
    // an LSP-ism that real servers never speak; using it here meant our
    // tests were self-consistently testing the wrong wire format (the
    // client and the fake both spoke a dialect no real server uses),
    // which is exactly why a green suite still shipped a protocol-level
    // blocker. A separate legacy `Content-Length` fake (see
    // `write_legacy_lsp_mcp_server_script`) covers the bidirectional
    // read tolerance.
    fn write_jsonrpc_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("jsonrpc-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys",
            "line = sys.stdin.readline()",
            "if not line:",
            "    raise SystemExit(1)",
            "request = json.loads(line)",
            r"assert request['jsonrpc'] == '2.0'",
            r"assert request['method'] == 'initialize'",
            r"response = json.dumps({",
            r"    'jsonrpc': '2.0',",
            r"    'id': request['id'],",
            r"    'result': {",
            r"        'protocolVersion': request['params']['protocolVersion'],",
            r"        'capabilities': {'tools': {}},",
            r"        'serverInfo': {'name': 'fake-mcp', 'version': '0.1.0'}",
            r"    }",
            r"})",
            r"sys.stdout.write(response + '\n')",
            "sys.stdout.flush()",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[allow(clippy::too_many_lines)]
    fn write_mcp_server_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("fake-mcp-server.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys",
            "",
            "def read_message():",
            "    line = sys.stdin.readline()",
            "    if not line:",
            "        return None",
            "    return json.loads(line)",
            "",
            "def send_message(message):",
            r"    sys.stdout.write(json.dumps(message) + '\n')",
            "    sys.stdout.flush()",
            "",
            "while True:",
            "    request = read_message()",
            "    if request is None:",
            "        break",
            "    method = request['method']",
            "    if method == 'initialize':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'protocolVersion': request['params']['protocolVersion'],",
            "                'capabilities': {'tools': {}, 'resources': {}},",
            "                'serverInfo': {'name': 'fake-mcp', 'version': '0.2.0'}",
            "            }",
            "        })",
            "    elif method == 'tools/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'tools': [",
            "                    {",
            "                        'name': 'echo',",
            "                        'description': 'Echoes text',",
            "                        'inputSchema': {",
            "                            'type': 'object',",
            "                            'properties': {'text': {'type': 'string'}},",
            "                            'required': ['text']",
            "                        }",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    elif method == 'tools/call':",
            "        args = request['params'].get('arguments') or {}",
            "        if request['params']['name'] == 'fail':",
            "            send_message({",
            "                'jsonrpc': '2.0',",
            "                'id': request['id'],",
            "                'error': {'code': -32001, 'message': 'tool failed'},",
            "            })",
            "        else:",
            "            text = args.get('text', '')",
            "            send_message({",
            "                'jsonrpc': '2.0',",
            "                'id': request['id'],",
            "                'result': {",
            "                    'content': [{'type': 'text', 'text': f'echo:{text}'}],",
            "                    'structuredContent': {'echoed': text},",
            "                    'isError': False",
            "                }",
            "            })",
            "    elif method == 'resources/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'resources': [",
            "                    {",
            "                        'uri': 'file://guide.txt',",
            "                        'name': 'guide',",
            "                        'description': 'Guide text',",
            "                        'mimeType': 'text/plain'",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    elif method == 'resources/read':",
            "        uri = request['params']['uri']",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'contents': [",
            "                    {",
            "                        'uri': uri,",
            "                        'mimeType': 'text/plain',",
            "                        'text': f'contents for {uri}'",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    else:",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'error': {'code': -32601, 'message': f'unknown method: {method}'},",
            "        })",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[allow(clippy::too_many_lines)]
    fn write_manager_mcp_server_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("manager-mcp-server.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, os, sys",
            "",
            "LABEL = os.environ.get('MCP_SERVER_LABEL', 'server')",
            "LOG_PATH = os.environ.get('MCP_LOG_PATH')",
            "initialize_count = 0",
            "",
            "def log(method):",
            "    if LOG_PATH:",
            "        with open(LOG_PATH, 'a', encoding='utf-8') as handle:",
            "            handle.write(f'{method}\\n')",
            "",
            "def read_message():",
            "    line = sys.stdin.readline()",
            "    if not line:",
            "        return None",
            "    return json.loads(line)",
            "",
            "def send_message(message):",
            r"    sys.stdout.write(json.dumps(message) + '\n')",
            "    sys.stdout.flush()",
            "",
            "while True:",
            "    request = read_message()",
            "    if request is None:",
            "        break",
            "    method = request['method']",
            "    log(method)",
            "    if 'id' not in request:",
            "        # Notification (e.g. notifications/initialized): no",
            "        # response is expected per JSON-RPC.",
            "        continue",
            "    if method == 'initialize':",
            "        initialize_count += 1",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'protocolVersion': request['params']['protocolVersion'],",
            "                'capabilities': {'tools': {}},",
            "                'serverInfo': {'name': LABEL, 'version': '1.0.0'}",
            "            }",
            "        })",
            "    elif method == 'tools/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'tools': [",
            "                    {",
            "                        'name': 'echo',",
            "                        'description': f'Echo tool for {LABEL}',",
            "                        'inputSchema': {",
            "                            'type': 'object',",
            "                            'properties': {'text': {'type': 'string'}},",
            "                            'required': ['text']",
            "                        }",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    elif method == 'tools/call':",
            "        args = request['params'].get('arguments') or {}",
            "        text = args.get('text', '')",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'content': [{'type': 'text', 'text': f'{LABEL}:{text}'}],",
            "                'structuredContent': {",
            "                    'server': LABEL,",
            "                    'echoed': text,",
            "                    'initializeCount': initialize_count",
            "                },",
            "                'isError': False",
            "            }",
            "        })",
            "    else:",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'error': {'code': -32601, 'message': f'unknown method: {method}'},",
            "        })",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    fn sample_bootstrap(script_path: &Path) -> McpClientBootstrap {
        let config = ScopedMcpServerConfig {
            scope: ConfigSource::Local,
            config: McpServerConfig::Stdio(McpStdioServerConfig {
                command: "/bin/sh".to_string(),
                args: vec![script_path.to_string_lossy().into_owned()],
                env: BTreeMap::from([("MCP_TEST_TOKEN".to_string(), "secret-value".to_string())]),
                request_timeout_secs: None,
                trust: None,
            }),
        };
        McpClientBootstrap::from_scoped_config("stdio server", &config)
    }

    fn script_transport(script_path: &Path) -> crate::mcp_client::McpStdioTransport {
        crate::mcp_client::McpStdioTransport {
            command: "python3".to_string(),
            args: vec![script_path.to_string_lossy().into_owned()],
            env: BTreeMap::new(),
            request_timeout_secs: None,
        }
    }

    fn cleanup_script(script_path: &Path) {
        fs::remove_file(script_path).expect("cleanup script");
        fs::remove_dir_all(script_path.parent().expect("script parent")).expect("cleanup dir");
    }

    fn manager_server_config(
        script_path: &Path,
        label: &str,
        log_path: &Path,
    ) -> ScopedMcpServerConfig {
        ScopedMcpServerConfig {
            scope: ConfigSource::Local,
            config: McpServerConfig::Stdio(McpStdioServerConfig {
                command: "python3".to_string(),
                args: vec![script_path.to_string_lossy().into_owned()],
                env: BTreeMap::from([
                    ("MCP_SERVER_LABEL".to_string(), label.to_string()),
                    (
                        "MCP_LOG_PATH".to_string(),
                        log_path.to_string_lossy().into_owned(),
                    ),
                ]),
                request_timeout_secs: None,
                trust: None,
            }),
        }
    }

    #[test]
    fn spawns_stdio_process_and_round_trips_io() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_echo_script();
            let bootstrap = sample_bootstrap(&script_path);
            let mut process = spawn_mcp_stdio_process(&bootstrap).expect("spawn stdio process");

            let ready = process.read_line().await.expect("read ready");
            assert_eq!(ready, "READY:secret-value\n");

            process
                .write_line("ping from client")
                .await
                .expect("write line");

            let echoed = process.read_line().await.expect("read echo");
            assert_eq!(echoed, "ECHO:ping from client\n");

            let status = process.wait().await.expect("wait for exit");
            assert!(status.success());

            cleanup_script(&script_path);
        });
    }

    #[test]
    fn rejects_non_stdio_bootstrap() {
        let config = ScopedMcpServerConfig {
            scope: ConfigSource::Local,
            config: McpServerConfig::Sdk(crate::config::McpSdkServerConfig {
                name: "sdk-server".to_string(),
            }),
        };
        let bootstrap = McpClientBootstrap::from_scoped_config("sdk server", &config);
        let error = spawn_mcp_stdio_process(&bootstrap).expect_err("non-stdio should fail");
        assert_eq!(error.kind(), ErrorKind::InvalidInput);
    }

    #[test]
    fn round_trips_initialize_request_and_response_over_stdio_frames() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_jsonrpc_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn transport directly");

            let response = process
                .initialize(
                    JsonRpcId::Number(1),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({"roots": {}}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect("initialize roundtrip");

            assert_eq!(response.id, JsonRpcId::Number(1));
            assert_eq!(response.error, None);
            assert_eq!(
                response.result,
                Some(McpInitializeResult {
                    protocol_version: "2025-03-26".to_string(),
                    capabilities: json!({"tools": {}}),
                    server_info: McpInitializeServerInfo {
                        name: "fake-mcp".to_string(),
                        version: "0.1.0".to_string(),
                    },
                })
            );

            let status = process.wait().await.expect("wait for exit");
            assert!(status.success());

            cleanup_script(&script_path);
        });
    }

    #[test]
    fn write_jsonrpc_request_round_trips_over_ndjson_frame() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_jsonrpc_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn transport directly");
            let request = JsonRpcRequest::new(
                JsonRpcId::Number(7),
                "initialize",
                Some(json!({
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "runtime-tests", "version": "0.1.0"}
                })),
            );

            process.send_request(&request).await.expect("send request");
            let response: JsonRpcResponse<serde_json::Value> =
                process.read_response().await.expect("read response");

            assert_eq!(response.id, JsonRpcId::Number(7));
            assert_eq!(response.jsonrpc, "2.0");

            let status = process.wait().await.expect("wait for exit");
            assert!(status.success());

            cleanup_script(&script_path);
        });
    }

    #[test]
    fn direct_spawn_uses_transport_env() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_echo_script();
            let transport = crate::mcp_client::McpStdioTransport {
                command: "/bin/sh".to_string(),
                args: vec![script_path.to_string_lossy().into_owned()],
                env: BTreeMap::from([("MCP_TEST_TOKEN".to_string(), "direct-secret".to_string())]),
                request_timeout_secs: None,
            };
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn transport directly");
            let ready = process.read_available().await.expect("read ready");
            assert_eq!(String::from_utf8_lossy(&ready), "READY:direct-secret\n");
            process.terminate().await.expect("terminate child");
            let _ = process.wait().await.expect("wait after kill");

            cleanup_script(&script_path);
        });
    }

    #[test]
    fn lists_tools_calls_tool_and_reads_resources_over_jsonrpc() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_mcp_server_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn fake mcp server");

            let tools = process
                .list_tools(JsonRpcId::Number(2), None)
                .await
                .expect("list tools");
            assert_eq!(tools.error, None);
            assert_eq!(tools.id, JsonRpcId::Number(2));
            assert_eq!(
                tools.result,
                Some(McpListToolsResult {
                    tools: vec![McpTool {
                        name: "echo".to_string(),
                        description: Some("Echoes text".to_string()),
                        input_schema: Some(json!({
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"]
                        })),
                        annotations: None,
                        meta: None,
                    }],
                    next_cursor: None,
                })
            );

            let call = process
                .call_tool(
                    JsonRpcId::String("call-1".to_string()),
                    McpToolCallParams {
                        name: "echo".to_string(),
                        arguments: Some(json!({"text": "hello"})),
                        meta: None,
                    },
                )
                .await
                .expect("call tool");
            assert_eq!(call.error, None);
            let call_result = call.result.expect("tool result");
            assert_eq!(call_result.is_error, Some(false));
            assert_eq!(
                call_result.structured_content,
                Some(json!({"echoed": "hello"}))
            );
            assert_eq!(call_result.content.len(), 1);
            assert_eq!(call_result.content[0].kind, "text");
            assert_eq!(
                call_result.content[0].data.get("text"),
                Some(&json!("echo:hello"))
            );

            let resources = process
                .list_resources(JsonRpcId::Number(3), None)
                .await
                .expect("list resources");
            let resources_result = resources.result.expect("resources result");
            assert_eq!(resources_result.resources.len(), 1);
            assert_eq!(resources_result.resources[0].uri, "file://guide.txt");
            assert_eq!(
                resources_result.resources[0].mime_type.as_deref(),
                Some("text/plain")
            );

            let read = process
                .read_resource(
                    JsonRpcId::Number(4),
                    McpReadResourceParams {
                        uri: "file://guide.txt".to_string(),
                    },
                )
                .await
                .expect("read resource");
            assert_eq!(
                read.result,
                Some(McpReadResourceResult {
                    contents: vec![super::McpResourceContents {
                        uri: "file://guide.txt".to_string(),
                        mime_type: Some("text/plain".to_string()),
                        text: Some("contents for file://guide.txt".to_string()),
                        blob: None,
                        meta: None,
                    }],
                })
            );

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await.expect("wait after kill");
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn surfaces_jsonrpc_errors_from_tool_calls() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_mcp_server_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn fake mcp server");

            let response = process
                .call_tool(
                    JsonRpcId::Number(9),
                    McpToolCallParams {
                        name: "fail".to_string(),
                        arguments: None,
                        meta: None,
                    },
                )
                .await
                .expect("call tool with error response");

            assert_eq!(response.id, JsonRpcId::Number(9));
            assert!(response.result.is_none());
            assert_eq!(response.error.as_ref().map(|e| e.code), Some(-32001));
            assert_eq!(
                response.error.as_ref().map(|e| e.message.as_str()),
                Some("tool failed")
            );

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await.expect("wait after kill");
            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.17 RW2 / M6 — legacy LSP-framing tolerance.
    //
    // These cover the *legacy* `Content-Length` read path
    // (`read_legacy_lsp_frame`), which `read_frame_from` switches into
    // when the first line is a `content-length:` header (Track R: we
    // write NDJSON, but still *read* either dialect). The M6 tolerances
    // all live on that path now:
    //   • bare LF (`\n`) header/body separator (no CRLF),
    //   • case-insensitive `Content-Length` name,
    //   • leading whitespace on the header name,
    //   • MAX_CONTENT_LENGTH guard against OOM.
    // Each uses a tiny printf-based emitter so we control the exact
    // bytes on the wire (the python fake servers now speak NDJSON, the
    // canonical MCP stdio dialect — these emitters are the only legacy
    // `Content-Length` producers left).
    // ============================================================

    /// Write a `/bin/sh` script that `printf`s `body` verbatim to
    /// stdout (so the test fully controls the framing bytes), then
    /// sleeps so the child stays alive for the read.
    fn write_raw_emitter_script(body: &str) -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("raw-frame-emitter.sh");
        // `printf %s` emits the argument with no added trailing
        // newline, so what we pass is exactly what hits the pipe.
        let escaped = body.replace('\\', "\\\\").replace('\'', "'\\''");
        let script = format!("#!/bin/sh\nprintf '%s' '{escaped}'\nsleep 30\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    fn sh_transport(script_path: &Path) -> crate::mcp_client::McpStdioTransport {
        crate::mcp_client::McpStdioTransport {
            command: "/bin/sh".to_string(),
            args: vec![script_path.to_string_lossy().into_owned()],
            env: BTreeMap::new(),
            request_timeout_secs: None,
        }
    }

    #[test]
    fn read_frame_accepts_lf_only_header_separator() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            // Bare LF terminators throughout — no CR anywhere.
            let script_path = write_raw_emitter_script("Content-Length: 7\n\npayload");
            let transport = sh_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn lf-only emitter");

            let frame = process.read_frame().await.expect("read lf-only frame");
            assert_eq!(frame, b"payload");

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn read_frame_accepts_lowercase_content_length_header() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            // Lowercased header name + canonical CRLF framing.
            let script_path = write_raw_emitter_script("content-length: 5\r\n\r\nhello");
            let transport = sh_transport(&script_path);
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn lowercase-header emitter");

            let frame = process.read_frame().await.expect("read lowercase-header frame");
            assert_eq!(frame, b"hello");

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn read_frame_accepts_leading_whitespace_header_name() {
        // R5-P2.3: the parser trims the header *name* before the
        // case-insensitive compare (`key.trim()` in `read_frame_from`),
        // so a leading space on the `Content-Length` header name must
        // still parse. Regression guard for that trim.
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            // One leading space before the header name; canonical CRLF.
            let script_path = write_raw_emitter_script(" Content-Length: 5\r\n\r\nhowdy");
            let transport = sh_transport(&script_path);
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn leading-space-header emitter");

            let frame = process
                .read_frame()
                .await
                .expect("read leading-space-header frame");
            assert_eq!(frame, b"howdy");

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn read_frame_rejects_oversized_content_length() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            // Declare a length far beyond MAX_CONTENT_LENGTH. The
            // parser must reject during header parsing, before it ever
            // tries to allocate `vec![0u8; len]`. No body bytes are
            // sent.
            let huge = super::MAX_CONTENT_LENGTH + 1;
            let script_path = write_raw_emitter_script(&format!("Content-Length: {huge}\r\n\r\n"));
            let transport = sh_transport(&script_path);
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn oversized emitter");

            let err = process
                .read_frame()
                .await
                .expect_err("oversized Content-Length should be rejected");
            assert_eq!(err.kind(), ErrorKind::InvalidData);
            assert!(
                err.to_string().contains("exceeds maximum"),
                "unexpected error: {err}"
            );

            process.terminate().await.expect("terminate child");
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.17 RW9 / #286 — large-payload pipe-buffer deadlock.
    //
    // The server writes a large (> OS pipe buffer) framed response to
    // stdout BEFORE it reads the request from stdin, while the client
    // sends a large request body. Under the old serial model
    // (write-all-then-read) both pipes back-pressure into a hang and
    // the call only survives by tripping the timeout. The concurrent
    // join model drains stdout while still feeding stdin, so the round
    // trip completes well under the timeout.
    // ============================================================

    /// MCP server that (1) emits one large framed response with a
    /// hard-coded `id` (matching the test's request id) BEFORE reading
    /// anything, then (2) drains stdin so the client's large write can
    /// finally complete. The response is padded past the pipe buffer
    /// via an extra ignored field so it deserialises cleanly into
    /// `McpInitializeResult` (unknown fields are dropped).
    // The response pad size is passed to the spawned server via the
    // `RESPONSE_PAD_BYTES` env (see the caller), so the script source
    // itself stays parameter-free.
    fn write_write_before_read_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("write-before-read-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, os, sys",
            "pad = 'x' * int(os.environ.get('RESPONSE_PAD_BYTES', '0'))",
            "response = {",
            "    'jsonrpc': '2.0',",
            "    'id': 7,",
            "    'result': {",
            "        'protocolVersion': '2025-03-26',",
            "        'capabilities': {},",
            "        'serverInfo': {'name': 'write-before-read', 'version': '0.1.0'},",
            "        '_pad': pad,",
            "    },",
            "}",
            "# NDJSON: emit the (large) one-line response BEFORE reading",
            "# the request. A serial client never reaches its read until",
            "# its write completes, so it deadlocks against this stdout.",
            r"encoded = (json.dumps(response) + '\n').encode()",
            "sys.stdout.buffer.write(encoded)",
            "sys.stdout.buffer.flush()",
            "# Only now drain stdin (one NDJSON line) so the client's",
            "# (large) write can finish.",
            "if not sys.stdin.readline():",
            "    raise SystemExit(0)",
            "import time; time.sleep(30)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn request_survives_large_payload_pipe_deadlock() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        // Keep the deadline tight so an accidental regression (serial
        // re-introduction) FAILS fast rather than hanging the suite for
        // the 300s default.
        let guard = env_lock().lock().expect("env lock");
        let prior = std::env::var("MCP_REQUEST_TIMEOUT_SECS").ok();
        std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", "10");

        runtime.block_on(async {
            // 256 KiB on both sides comfortably exceeds the 64 KiB
            // default pipe buffer on Linux and macOS.
            let pad = 256 * 1024;
            let script_path = write_write_before_read_script();
            let mut transport = script_transport(&script_path);
            transport
                .env
                .insert("RESPONSE_PAD_BYTES".to_string(), pad.to_string());
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn write-before-read server");

            // Large request body so the WRITE side also exceeds the
            // pipe buffer — the second half of the deadlock.
            let big = "y".repeat(pad);
            let started = std::time::Instant::now();
            let response = process
                .initialize(
                    JsonRpcId::Number(7),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({ "filler": big }),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect("concurrent write+read should complete, not deadlock");
            let elapsed = started.elapsed();

            assert_eq!(response.id, JsonRpcId::Number(7));
            let result = response.result.expect("response result");
            assert_eq!(result.server_info.name, "write-before-read");
            // Must finish far under the 10s ceiling; a deadlock would
            // only resolve at the timeout.
            assert!(
                elapsed < std::time::Duration::from_secs(8),
                "round trip took too long ({elapsed:?}); serial deadlock likely re-introduced"
            );

            let _ = process.terminate().await;
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });

        match prior {
            Some(value) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", value),
            None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
        }
        drop(guard);
    }

    // ============================================================
    // v0.4.17 Track R / R5-P1 — write-fails-first short-circuit.
    //
    // If the server closes the read end of OUR stdin (so our write
    // half breaks) but keeps its stdout open and silent, `request()`
    // must return the WRITE error immediately — it must NOT block the
    // read pump until the global timeout. The original `tokio::join!`
    // implementation waited for both arms, so it only unwedged at the
    // deadline; the `select!` state machine surfaces the write error at
    // once. We prove "fast path, not timeout path" by configuring a
    // large per-server timeout and asserting the call returns far
    // sooner.
    // ============================================================

    /// MCP server that closes its own stdin read end (`os.close(0)`)
    /// at startup, then keeps stdout open but never writes, sleeping
    /// long. With the read end gone, the client's write to stdin breaks
    /// (EPIPE), while the read pump would otherwise wait forever for a
    /// frame that never arrives.
    fn write_close_stdin_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("close-stdin-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import os, sys, time",
            "# Close the read end of our stdin so any client write to",
            "# the corresponding pipe write end fails with EPIPE.",
            "os.close(0)",
            "# Keep stdout open but silent (never emit a frame) and stay",
            "# alive well past the test's assertion window, so the only",
            "# way the client can return quickly is the write-error",
            "# short-circuit (NOT the global timeout).",
            "time.sleep(120)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn request_returns_write_error_without_waiting_for_timeout() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        // Large per-server ceiling: if the call ever returns via the
        // timeout path it would take ~30s, so a sub-5s return proves
        // the write-error short-circuit fired instead.
        let guard = env_lock().lock().expect("env lock");
        let prior = std::env::var("MCP_REQUEST_TIMEOUT_SECS").ok();
        std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", "30");

        runtime.block_on(async {
            let script_path = write_close_stdin_script();
            let transport = script_transport(&script_path);
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn close-stdin server");

            // A large body so even if the very first bytes slip into a
            // not-yet-collapsed pipe buffer, subsequent writes hit the
            // closed read end deterministically.
            let big = "z".repeat(256 * 1024);
            let started = std::time::Instant::now();
            let err = process
                .initialize(
                    JsonRpcId::Number(1),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({ "filler": big }),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect_err("write to a closed stdin must error");
            let elapsed = started.elapsed();

            // The error must be a write/IO failure (broken pipe), NOT a
            // timeout — that is the whole point of the short-circuit.
            assert_ne!(
                err.kind(),
                ErrorKind::TimedOut,
                "expected an immediate write error, got a timeout: {err}"
            );
            assert!(
                elapsed < std::time::Duration::from_secs(5),
                "write error returned too slowly ({elapsed:?}); \
                 the read pump likely blocked until the timeout instead \
                 of short-circuiting on the write failure"
            );

            // `request()` killed the child on the I/O failure; reap it.
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });

        match prior {
            Some(value) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", value),
            None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
        }
        drop(guard);
    }

    #[test]
    fn manager_discovers_tools_from_stdio_config() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("alpha.log");
            let servers = BTreeMap::from([(
                "alpha".to_string(),
                manager_server_config(&script_path, "alpha", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            let tools = manager.discover_tools().await.expect("discover tools");

            assert_eq!(tools.len(), 1);
            assert_eq!(tools[0].server_name, "alpha");
            assert_eq!(tools[0].raw_name, "echo");
            assert_eq!(tools[0].qualified_name, mcp_tool_name("alpha", "echo"));
            assert_eq!(tools[0].tool.name, "echo");
            assert!(manager.unsupported_servers().is_empty());

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn manager_routes_tool_calls_to_correct_server() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let alpha_log = root.join("alpha.log");
            let beta_log = root.join("beta.log");
            let servers = BTreeMap::from([
                (
                    "alpha".to_string(),
                    manager_server_config(&script_path, "alpha", &alpha_log),
                ),
                (
                    "beta".to_string(),
                    manager_server_config(&script_path, "beta", &beta_log),
                ),
            ]);
            let mut manager = McpServerManager::from_servers(&servers);

            let tools = manager.discover_tools().await.expect("discover tools");
            assert_eq!(tools.len(), 2);

            let alpha = manager
                .call_tool(
                    &mcp_tool_name("alpha", "echo"),
                    Some(json!({"text": "hello"})),
                )
                .await
                .expect("call alpha tool");
            let beta = manager
                .call_tool(
                    &mcp_tool_name("beta", "echo"),
                    Some(json!({"text": "world"})),
                )
                .await
                .expect("call beta tool");

            assert_eq!(
                alpha
                    .result
                    .as_ref()
                    .and_then(|result| result.structured_content.as_ref())
                    .and_then(|value| value.get("server")),
                Some(&json!("alpha"))
            );
            assert_eq!(
                beta.result
                    .as_ref()
                    .and_then(|result| result.structured_content.as_ref())
                    .and_then(|value| value.get("server")),
                Some(&json!("beta"))
            );

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn manager_records_unsupported_non_stdio_servers_without_panicking() {
        let servers = BTreeMap::from([
            (
                "http".to_string(),
                ScopedMcpServerConfig {
                    scope: ConfigSource::Local,
                    config: McpServerConfig::Http(McpRemoteServerConfig {
                        url: "https://example.test/mcp".to_string(),
                        headers: BTreeMap::new(),
                        headers_helper: None,
                        oauth: None,
                    }),
                },
            ),
            (
                "sdk".to_string(),
                ScopedMcpServerConfig {
                    scope: ConfigSource::Local,
                    config: McpServerConfig::Sdk(McpSdkServerConfig {
                        name: "sdk-server".to_string(),
                    }),
                },
            ),
            (
                "ws".to_string(),
                ScopedMcpServerConfig {
                    scope: ConfigSource::Local,
                    config: McpServerConfig::Ws(McpWebSocketServerConfig {
                        url: "wss://example.test/mcp".to_string(),
                        headers: BTreeMap::new(),
                        headers_helper: None,
                    }),
                },
            ),
        ]);

        let manager = McpServerManager::from_servers(&servers);
        let unsupported = manager.unsupported_servers();

        assert_eq!(unsupported.len(), 3);
        assert_eq!(unsupported[0].server_name, "http");
        assert_eq!(unsupported[1].server_name, "sdk");
        assert_eq!(unsupported[2].server_name, "ws");
    }

    #[test]
    fn manager_shutdown_terminates_spawned_children_and_is_idempotent() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("alpha.log");
            let servers = BTreeMap::from([(
                "alpha".to_string(),
                manager_server_config(&script_path, "alpha", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            manager.discover_tools().await.expect("discover tools");
            manager.shutdown().await.expect("first shutdown");
            manager.shutdown().await.expect("second shutdown");

            cleanup_script(&script_path);
        });
    }

    #[test]
    fn manager_reuses_spawned_server_between_discovery_and_call() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("alpha.log");
            let servers = BTreeMap::from([(
                "alpha".to_string(),
                manager_server_config(&script_path, "alpha", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            manager.discover_tools().await.expect("discover tools");
            let response = manager
                .call_tool(
                    &mcp_tool_name("alpha", "echo"),
                    Some(json!({"text": "reuse"})),
                )
                .await
                .expect("call tool");

            assert_eq!(
                response
                    .result
                    .as_ref()
                    .and_then(|result| result.structured_content.as_ref())
                    .and_then(|value| value.get("initializeCount")),
                Some(&json!(1))
            );

            let log = fs::read_to_string(&log_path).expect("read log");
            assert_eq!(log.lines().filter(|line| *line == "initialize").count(), 1);
            // RW1 (v0.4.17): after `initialize` succeeds the manager
            // now sends the spec-mandated `notifications/initialized`
            // notification before `tools/list`. The fake server logs
            // every received method, so it shows up in the trace.
            assert_eq!(
                log.lines().collect::<Vec<_>>(),
                vec![
                    "initialize",
                    "notifications/initialized",
                    "tools/list",
                    "tools/call"
                ]
            );

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.17 RW1 — initialize handshake completion notification.
    // ============================================================

    #[test]
    fn manager_sends_initialized_notification_after_initialize() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("alpha.log");
            let servers = BTreeMap::from([(
                "alpha".to_string(),
                manager_server_config(&script_path, "alpha", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            // Discovery drives `ensure_server_ready`, which performs
            // initialize and (RW1) the mandated
            // `notifications/initialized` before `tools/list`.
            manager.discover_tools().await.expect("discover tools");

            let log = fs::read_to_string(&log_path).expect("read log");
            let methods = log.lines().collect::<Vec<_>>();
            // The notification must land *after* the initialize reply
            // and *before* tools/list.
            let init_idx = methods
                .iter()
                .position(|m| *m == "initialize")
                .expect("initialize logged");
            let notify_idx = methods
                .iter()
                .position(|m| *m == "notifications/initialized")
                .expect("notifications/initialized logged");
            let list_idx = methods
                .iter()
                .position(|m| *m == "tools/list")
                .expect("tools/list logged");
            assert!(
                init_idx < notify_idx && notify_idx < list_idx,
                "expected initialize < notifications/initialized < tools/list, got {methods:?}"
            );
            // Exactly one initialized notification per initialize.
            assert_eq!(
                methods
                    .iter()
                    .filter(|m| **m == "notifications/initialized")
                    .count(),
                1
            );

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.10 (M3 landmine fix) — regression coverage for
    //   • response.id ↔ request.id correlation
    //   • read timeout via MCP_REQUEST_TIMEOUT_SECS
    //   • automatic respawn after the child exits between calls
    // The earlier #151 / #172 stalls all hit one of these three
    // codepaths, so each gets its own dedicated MCP script + test.
    // ============================================================

    fn write_wrong_id_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("wrong-id-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys",
            "line = sys.stdin.readline()",
            "if not line:",
            "    raise SystemExit(1)",
            "request = json.loads(line)",
            "# Intentionally respond with a different id so we exercise",
            "# the correlation check.",
            r"response = json.dumps({",
            r"    'jsonrpc': '2.0',",
            r"    'id': 999,",
            r"    'result': {",
            r"        'protocolVersion': request['params']['protocolVersion'],",
            r"        'capabilities': {},",
            r"        'serverInfo': {'name': 'wrong-id', 'version': '0.1.0'}",
            r"    }",
            r"})",
            r"sys.stdout.write(response + '\n')",
            "sys.stdout.flush()",
            "# Keep the process alive so the test can observe the kill.",
            "import time; time.sleep(30)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    fn write_no_response_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("no-response-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import sys, time",
            "# Read the request line so the client's write completes, then",
            "# deliberately hang. The client should trip",
            "# MCP_REQUEST_TIMEOUT_SECS and kill us.",
            "if not sys.stdin.readline():",
            "    raise SystemExit(0)",
            "time.sleep(30)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    fn write_die_after_tools_list_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("die-after-tools-list.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, os, sys",
            "LOG_PATH = os.environ.get('MCP_LOG_PATH')",
            "",
            "def log(method):",
            "    if LOG_PATH:",
            "        with open(LOG_PATH, 'a', encoding='utf-8') as handle:",
            "            handle.write(f'{method}\\n')",
            "",
            "def read_message():",
            "    line = sys.stdin.readline()",
            "    if not line:",
            "        return None",
            "    return json.loads(line)",
            "",
            "def send_message(message):",
            r"    sys.stdout.write(json.dumps(message) + '\n')",
            "    sys.stdout.flush()",
            "",
            "while True:",
            "    request = read_message()",
            "    if request is None:",
            "        break",
            "    method = request['method']",
            "    log(method)",
            "    if 'id' not in request:",
            "        # Notification (e.g. notifications/initialized): no",
            "        # response is expected per JSON-RPC.",
            "        continue",
            "    if method == 'initialize':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'protocolVersion': request['params']['protocolVersion'],",
            "                'capabilities': {'tools': {}},",
            "                'serverInfo': {'name': 'die-after-list', 'version': '0.1.0'}",
            "            }",
            "        })",
            "    elif method == 'tools/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'tools': [",
            "                    {",
            "                        'name': 'echo',",
            "                        'description': 'one-shot',",
            "                        'inputSchema': {'type': 'object'}",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "        # Exit cleanly after the first tools/list reply so the",
            "        # next manager call has to respawn.",
            "        sys.exit(0)",
            "    else:",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'error': {'code': -32601, 'message': f'unknown method: {method}'},",
            "        })",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    fn die_after_tools_list_config(script_path: &Path, log_path: &Path) -> ScopedMcpServerConfig {
        ScopedMcpServerConfig {
            scope: ConfigSource::Local,
            config: McpServerConfig::Stdio(McpStdioServerConfig {
                command: "python3".to_string(),
                args: vec![script_path.to_string_lossy().into_owned()],
                env: BTreeMap::from([(
                    "MCP_LOG_PATH".to_string(),
                    log_path.to_string_lossy().into_owned(),
                )]),
                request_timeout_secs: None,
                trust: None,
            }),
        }
    }

    #[test]
    fn rejects_response_with_mismatched_id() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_wrong_id_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn wrong-id server");

            let err = process
                .initialize(
                    JsonRpcId::Number(1),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect_err("id mismatch should error");

            assert_eq!(err.kind(), ErrorKind::InvalidData);
            assert!(
                err.to_string().contains("response id mismatch"),
                "unexpected error: {err}"
            );

            // The child was killed by `request()` — wait() reaps it.
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn times_out_when_server_does_not_respond() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_no_response_script();
            let transport = script_transport(&script_path);
            let mut process = McpStdioProcess::spawn(&transport).expect("spawn hanging server");

            // Set the env override *just before* the call and restore
            // the previous value after. Tests are otherwise local IPC
            // at sub-100ms latency, so a transient 1s ceiling can't
            // cause false failures elsewhere.
            let prior = std::env::var("MCP_REQUEST_TIMEOUT_SECS").ok();
            std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", "1");
            let started = std::time::Instant::now();
            let err = process
                .initialize(
                    JsonRpcId::Number(1),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect_err("hanging server should trigger timeout");
            let elapsed = started.elapsed();
            match prior {
                Some(value) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", value),
                None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
            }

            assert_eq!(err.kind(), ErrorKind::TimedOut);
            assert!(
                elapsed < std::time::Duration::from_secs(5),
                "timeout fired too slowly: {elapsed:?}"
            );

            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn manager_respawns_dead_server_on_next_discovery() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_die_after_tools_list_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("respawn.log");
            let servers = BTreeMap::from([(
                "ephemeral".to_string(),
                die_after_tools_list_config(&script_path, &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            // First discovery: server replies initialize + tools/list,
            // then exits cleanly.
            let first = manager.discover_tools().await.expect("first discover");
            assert_eq!(first.len(), 1);
            assert_eq!(first[0].raw_name, "echo");

            // Give the OS a moment to mark the child as exited so
            // `try_wait()` returns `Ok(Some(_))` on the next call.
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;

            // Second discovery must transparently respawn rather than
            // hang on the dead pipe.
            let second = manager.discover_tools().await.expect("respawn discover");
            assert_eq!(second.len(), 1);

            let log = fs::read_to_string(&log_path).expect("read log");
            let initialize_count = log.lines().filter(|line| *line == "initialize").count();
            assert_eq!(
                initialize_count, 2,
                "manager should have re-initialized after detecting the dead child; log was: {log}"
            );

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.17 RW6 — per-server discovery degradation.
    // A broken server must NOT take down the whole catalogue; the
    // healthy server's tools are still returned and the failure is
    // recorded in `discovery_failures`.
    // ============================================================

    /// MCP server that exits immediately without responding, so the
    /// client's initialize round trip fails fast (broken pipe / EOF)
    /// rather than timing out.
    fn write_immediate_exit_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("immediate-exit-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import sys",
            "# Emit a noisy stderr line (sent to Stdio::null() by the RW6",
            "# default; R5-P2.2) then exit without ever answering",
            "# initialize.",
            "sys.stderr.write('boom: server refuses to start\\n')",
            "sys.stderr.flush()",
            "raise SystemExit(1)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn discover_tools_skips_failed_server_and_keeps_healthy_one() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let healthy_script = write_manager_mcp_server_script();
            let root = healthy_script.parent().expect("script parent");
            let healthy_log = root.join("healthy.log");
            let broken_script = write_immediate_exit_script();

            let servers = BTreeMap::from([
                (
                    "healthy".to_string(),
                    manager_server_config(&healthy_script, "healthy", &healthy_log),
                ),
                (
                    "broken".to_string(),
                    ScopedMcpServerConfig {
                        scope: ConfigSource::Local,
                        config: McpServerConfig::Stdio(McpStdioServerConfig {
                            command: "python3".to_string(),
                            args: vec![broken_script.to_string_lossy().into_owned()],
                            env: BTreeMap::new(),
                            request_timeout_secs: Some(2),
                            trust: None,
                        }),
                    },
                ),
            ]);
            let mut manager = McpServerManager::from_servers(&servers);

            let tools = manager
                .discover_tools()
                .await
                .expect("discovery must succeed despite one broken server");

            // Healthy server's tool survives.
            assert_eq!(tools.len(), 1);
            assert_eq!(tools[0].server_name, "healthy");
            assert_eq!(tools[0].raw_name, "echo");

            // Broken server is recorded as a failure, not silently lost.
            let failures = manager.discovery_failures();
            assert_eq!(failures.len(), 1);
            assert_eq!(failures[0].server_name, "broken");
            assert!(
                !failures[0].reason.is_empty(),
                "failure reason should be populated"
            );

            // The healthy server is still routable after the partial
            // failure.
            let call = manager
                .call_tool(&mcp_tool_name("healthy", "echo"), Some(json!({"text": "ok"})))
                .await
                .expect("healthy server still routable");
            assert!(call.result.is_some());

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&healthy_script);
            let _ = fs::remove_file(&broken_script);
        });
    }

    // v0.4.19 — protocol-version negotiation guard. A server that negotiates a
    // version ARIS does not support must be REJECTED (per-server degrade with a
    // clear reason), not silently used on an incompatible protocol.
    fn write_bad_protocol_version_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("bad-protocol-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys",
            "line = sys.stdin.readline()",
            "if not line:",
            "    raise SystemExit(1)",
            "request = json.loads(line)",
            "# Respond with a protocolVersion ARIS does NOT support (correct id,",
            "# so this exercises the negotiation guard, not the id-mismatch path).",
            r"response = json.dumps({",
            r"    'jsonrpc': '2.0',",
            r"    'id': request['id'],",
            r"    'result': {",
            r"        'protocolVersion': '1999-01-01',",
            r"        'capabilities': {},",
            r"        'serverInfo': {'name': 'bad-protocol', 'version': '0.1.0'}",
            r"    }",
            r"})",
            r"sys.stdout.write(response + '\n')",
            "sys.stdout.flush()",
            "import time; time.sleep(30)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        script_path
    }

    #[test]
    fn discover_tools_rejects_unsupported_protocol_version() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script = write_bad_protocol_version_script();
            let servers = BTreeMap::from([(
                "badproto".to_string(),
                ScopedMcpServerConfig {
                    scope: ConfigSource::Local,
                    config: McpServerConfig::Stdio(McpStdioServerConfig {
                        command: "python3".to_string(),
                        args: vec![script.to_string_lossy().into_owned()],
                        env: BTreeMap::new(),
                        request_timeout_secs: Some(2),
                        trust: None,
                    }),
                },
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            // Soft-degrade: the server negotiated an unsupported protocol
            // version, so it contributes no tools and is recorded as a failure
            // (rather than silently proceeding on an incompatible protocol).
            let tools = manager
                .discover_tools()
                .await
                .expect("discovery soft-degrades around the bad server");
            assert!(
                tools.is_empty(),
                "unsupported-protocol server must contribute no tools, got {tools:?}"
            );

            let failures = manager.discovery_failures();
            assert_eq!(failures.len(), 1);
            assert_eq!(failures[0].server_name, "badproto");
            assert!(
                failures[0].reason.contains("unsupported MCP protocol version")
                    && failures[0].reason.contains("1999-01-01"),
                "failure reason must name the unsupported version: {}",
                failures[0].reason
            );

            manager.shutdown().await.expect("shutdown");
            let _ = fs::remove_file(&script);
        });
    }

    // ============================================================
    // v0.4.17 R-6 / T4 — synchronous McpManagerHandle façade.
    // Drives discover + call from a *plain synchronous* test body (no
    // surrounding tokio runtime), which is exactly the topology Track C
    // (CliToolExecutor::execute, a sync trait method) will use. The
    // SPIKE-A debug_assert holds because there is no ambient runtime
    // here; we deliberately don't test the panic path (documented as a
    // dev-time guard only).
    // ============================================================

    #[test]
    fn sync_handle_discovers_and_calls_tools_without_ambient_runtime() {
        // NOTE: intentionally NOT wrapped in `runtime.block_on(...)`.
        let script_path = write_manager_mcp_server_script();
        let root = script_path.parent().expect("script parent");
        let log_path = root.join("alpha.log");
        let servers = BTreeMap::from([(
            "alpha".to_string(),
            manager_server_config(&script_path, "alpha", &log_path),
        )]);
        let manager = McpServerManager::from_servers(&servers);
        let mut handle = McpManagerHandle::from_manager(manager).expect("build sync handle");

        // Sync discovery via the handle's own internal runtime.
        let tools = handle.discover_tools().expect("sync discover");
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].qualified_name, mcp_tool_name("alpha", "echo"));
        assert!(handle.discovery_failures().is_empty());
        assert!(handle.unsupported_servers().is_empty());

        // Sync tool call via the handle.
        let response = handle
            .call_tool(&mcp_tool_name("alpha", "echo"), Some(json!({"text": "sync"})))
            .expect("sync call");
        assert_eq!(
            response
                .result
                .as_ref()
                .and_then(|result| result.structured_content.as_ref())
                .and_then(|value| value.get("echoed")),
            Some(&json!("sync"))
        );

        handle.shutdown().expect("sync shutdown");
        cleanup_script(&script_path);
    }

    #[test]
    fn manager_reports_unknown_qualified_tool_name() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_manager_mcp_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("alpha.log");
            let servers = BTreeMap::from([(
                "alpha".to_string(),
                manager_server_config(&script_path, "alpha", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            let error = manager
                .call_tool(
                    &mcp_tool_name("alpha", "missing"),
                    Some(json!({"text": "nope"})),
                )
                .await
                .expect_err("unknown qualified tool should fail");

            match error {
                McpServerManagerError::UnknownTool { qualified_name } => {
                    assert_eq!(qualified_name, mcp_tool_name("alpha", "missing"));
                }
                other => panic!("expected unknown tool error, got {other:?}"),
            }

            cleanup_script(&script_path);
        });
    }

    // ============================================================
    // v0.4.13 P1.D — per-server MCP timeout precedence.
    // ============================================================

    /// Mutex serialising tests that mutate `MCP_REQUEST_TIMEOUT_SECS`.
    /// `mcp_request_timeout` reads the env at every call, so two
    /// concurrent tests poking the env would race even with
    /// `--test-threads=1` if the runtime crate ever switched to
    /// multi-threaded test execution.
    fn env_lock() -> &'static std::sync::Mutex<()> {
        use std::sync::OnceLock;
        static LOCK: OnceLock<std::sync::Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| std::sync::Mutex::new(()))
    }

    /// Run `body` while `MCP_REQUEST_TIMEOUT_SECS` is set (or
    /// removed). Always restores the prior env value on exit.
    fn with_env_timeout<F: FnOnce()>(value: Option<&str>, body: F) {
        let guard = env_lock().lock().expect("env lock");
        let prior = std::env::var("MCP_REQUEST_TIMEOUT_SECS").ok();
        match value {
            Some(v) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", v),
            None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
        }
        body();
        match prior {
            Some(value) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", value),
            None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
        }
        drop(guard);
    }

    #[test]
    fn per_server_timeout_overrides_global_env() {
        // Per-server `Some(42)` must beat `MCP_REQUEST_TIMEOUT_SECS=120`.
        with_env_timeout(Some("120"), || {
            let timeout = mcp_request_timeout(Some(42));
            assert_eq!(timeout, std::time::Duration::from_secs(42));
        });
    }

    #[test]
    fn global_env_overrides_default_when_no_per_server() {
        // No per-server override: env value wins over the 300s default.
        with_env_timeout(Some("77"), || {
            let timeout = mcp_request_timeout(None);
            assert_eq!(timeout, std::time::Duration::from_secs(77));
        });
    }

    #[test]
    fn default_300s_when_no_override() {
        // Neither per-server nor env: fall back to the 300s default.
        with_env_timeout(None, || {
            let timeout = mcp_request_timeout(None);
            assert_eq!(timeout, std::time::Duration::from_secs(300));
        });
    }

    #[test]
    fn per_server_timeout_clamped_to_1_to_1800s() {
        // Per-server override below 1s clamps up to 1s, above 1800s
        // clamps down to 1800s. The env doesn't matter for an
        // override path, so set it to something orthogonal to verify.
        with_env_timeout(Some("60"), || {
            assert_eq!(
                mcp_request_timeout(Some(0)),
                std::time::Duration::from_secs(1),
                "zero override should clamp up to 1s"
            );
            assert_eq!(
                mcp_request_timeout(Some(10_000)),
                std::time::Duration::from_secs(1800),
                "huge override should clamp down to 1800s"
            );
            assert_eq!(
                mcp_request_timeout(Some(1800)),
                std::time::Duration::from_secs(1800),
                "exactly 1800s should pass through"
            );
            assert_eq!(
                mcp_request_timeout(Some(1)),
                std::time::Duration::from_secs(1),
                "exactly 1s should pass through"
            );
        });
    }

    // ============================================================
    // v0.4.13 — JSON-RPC notifications (id-less frames) are skipped.
    // Closes the v0.4.10 known limitation tracked in #151 / #172.
    // ============================================================

    /// MCP server that emits N notification frames followed by a
    /// well-formed response with the request id. Used by both the
    /// "one notification" and "many notifications" tests; vary
    /// `notification_count`.
    fn write_notifications_then_response_script(notification_count: usize) -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join(format!("notifications-{notification_count}-mcp.py"));
        // The number of notifications is baked in via env so the
        // python source itself stays small and identical.
        let script = [
            "#!/usr/bin/env python3",
            "import json, os, sys",
            "n = int(os.environ.get('NOTIFICATION_COUNT', '1'))",
            "line = sys.stdin.readline()",
            "if not line:",
            "    raise SystemExit(1)",
            "request = json.loads(line)",
            "",
            "def emit(body):",
            r"    sys.stdout.write(json.dumps(body) + '\n')",
            "    sys.stdout.flush()",
            "",
            "# Emit N notifications first.",
            "for i in range(n):",
            "    emit({",
            r"        'jsonrpc': '2.0',",
            r"        'method': 'notifications/progress',",
            r"        'params': {'progressToken': i, 'progress': i},",
            "    })",
            "",
            "# Then the real response, correlated by id.",
            "emit({",
            r"    'jsonrpc': '2.0',",
            r"    'id': request['id'],",
            r"    'result': {",
            r"        'protocolVersion': request['params']['protocolVersion'],",
            r"        'capabilities': {},",
            r"        'serverInfo': {'name': 'notif-then-response', 'version': '0.1.0'}",
            r"    }",
            "})",
            "import time; time.sleep(30)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    /// Variant: only notifications, no response. Used to verify the
    /// timeout still bites when the read loop is starved.
    fn write_only_notifications_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("only-notifications-mcp.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys, time",
            "if not sys.stdin.readline():",
            "    raise SystemExit(1)",
            "",
            "def emit(body):",
            r"    sys.stdout.write(json.dumps(body) + '\n')",
            "    sys.stdout.flush()",
            "",
            "# Stream notifications indefinitely, never the response.",
            "# The client should still hit the read timeout because the",
            "# timeout wraps the entire send+read loop, not a single",
            "# read_frame call.",
            "for i in range(1000):",
            "    emit({",
            r"        'jsonrpc': '2.0',",
            r"        'method': 'notifications/log',",
            r"        'params': {'level': 'info', 'message': f'tick {i}'},",
            "    })",
            "    time.sleep(0.05)",
            "time.sleep(10)",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn notification_then_response_returns_response() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_notifications_then_response_script(1);
            let mut transport = script_transport(&script_path);
            transport.env.insert("NOTIFICATION_COUNT".to_string(), "1".to_string());
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn notif-then-response server");

            let response = process
                .initialize(
                    JsonRpcId::Number(7),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect("notification frame should be skipped and response returned");

            assert_eq!(response.id, JsonRpcId::Number(7));
            let result = response.result.expect("response result");
            assert_eq!(result.server_info.name, "notif-then-response");

            let _ = process.terminate().await;
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn multiple_notifications_before_response_all_skipped() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_notifications_then_response_script(5);
            let mut transport = script_transport(&script_path);
            transport.env.insert("NOTIFICATION_COUNT".to_string(), "5".to_string());
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn many-notifs server");

            let response = process
                .initialize(
                    JsonRpcId::Number(11),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect("five notifications should all be skipped, then response returned");

            assert_eq!(response.id, JsonRpcId::Number(11));
            assert!(response.result.is_some(), "response should carry a result");

            let _ = process.terminate().await;
            let _ = process.wait().await;
            cleanup_script(&script_path);
        });
    }

    #[test]
    fn notification_after_timeout_still_times_out() {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        // Hold the env-mutation lock around both `set_var` and the
        // `block_on(...)` to prevent racing with other env-toggling
        // tests under multi-threaded test execution. We inline the
        // mutex here rather than using `with_env_timeout` because the
        // call we're guarding is async.
        let guard = env_lock().lock().expect("env lock");
        let prior = std::env::var("MCP_REQUEST_TIMEOUT_SECS").ok();
        std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", "1");

        runtime.block_on(async {
            let script_path = write_only_notifications_script();
            let transport = script_transport(&script_path);
            let mut process =
                McpStdioProcess::spawn(&transport).expect("spawn streaming-notifs server");

            let started = std::time::Instant::now();
            let err = process
                .initialize(
                    JsonRpcId::Number(13),
                    McpInitializeParams {
                        protocol_version: "2025-03-26".to_string(),
                        capabilities: json!({}),
                        client_info: McpInitializeClientInfo {
                            name: "runtime-tests".to_string(),
                            version: "0.1.0".to_string(),
                        },
                    },
                )
                .await
                .expect_err("server only emits notifications, request should time out");
            let elapsed = started.elapsed();

            assert_eq!(err.kind(), ErrorKind::TimedOut);
            assert!(
                elapsed < std::time::Duration::from_secs(5),
                "timeout was not honoured by the notification-skip loop: {elapsed:?}"
            );

            let _ = process.wait().await;
            cleanup_script(&script_path);
        });

        match prior {
            Some(value) => std::env::set_var("MCP_REQUEST_TIMEOUT_SECS", value),
            None => std::env::remove_var("MCP_REQUEST_TIMEOUT_SECS"),
        }
        drop(guard);
    }

    // ============================================================
    // v0.4.17 Track R — NDJSON framing (the canonical MCP stdio
    // dialect) + bidirectional read tolerance.
    //
    // The real-machine blocker: we emitted LSP `Content-Length` frames;
    // spec-correct servers (e.g. `codex mcp-server`) read NDJSON
    // (one JSON object per line) and went silent on our header bytes,
    // so every request timed out. These tests lock:
    //   • the wire encoder is NDJSON (one line + `\n`),
    //   • the reader auto-detects NDJSON vs legacy `Content-Length`,
    //   • blank lines are skipped and over-long lines rejected,
    //   • a real NDJSON server completes the full handshake.
    // ============================================================

    /// Run `read_frame_from` over an in-memory NDJSON byte stream so we
    /// can assert the pure decode behaviour without spawning a process.
    fn decode_one_frame(bytes: &[u8]) -> std::io::Result<Vec<u8>> {
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let mut reader = tokio::io::BufReader::new(bytes);
            super::read_frame_from(&mut reader).await
        })
    }

    #[test]
    fn encode_frame_appends_single_newline_terminator() {
        // The NDJSON encoder must append exactly one `\n` and nothing
        // else (no `Content-Length` header, no CR).
        let framed = super::encode_frame(b"{\"jsonrpc\":\"2.0\"}");
        assert_eq!(framed, b"{\"jsonrpc\":\"2.0\"}\n");
    }

    #[test]
    fn read_frame_parses_single_ndjson_line() {
        // A bare JSON line (no header) is taken verbatim as one message,
        // with its trailing newline stripped.
        let frame = decode_one_frame(b"{\"id\":1,\"jsonrpc\":\"2.0\"}\n")
            .expect("ndjson line should parse");
        assert_eq!(frame, b"{\"id\":1,\"jsonrpc\":\"2.0\"}");
    }

    #[test]
    fn read_frame_strips_crlf_from_ndjson_line() {
        // Some servers terminate lines with CRLF; the trailing CR must
        // be stripped along with the LF so the JSON parses cleanly.
        let frame =
            decode_one_frame(b"{\"id\":2}\r\n").expect("crlf-terminated ndjson line should parse");
        assert_eq!(frame, b"{\"id\":2}");
    }

    #[test]
    fn read_frame_skips_blank_lines_before_ndjson() {
        // Blank / whitespace-only padding lines are skipped before the
        // real message line is returned.
        let frame = decode_one_frame(b"\n  \n\t\n{\"id\":3}\n")
            .expect("blank lines should be skipped, then message returned");
        assert_eq!(frame, b"{\"id\":3}");
    }

    #[test]
    fn read_frame_rejects_overlong_ndjson_line() {
        // A line longer than MAX_CONTENT_LENGTH without a newline must
        // be rejected (the NDJSON analogue of the Content-Length cap),
        // before it can drive unbounded buffering.
        let mut bytes = vec![b'a'; super::MAX_CONTENT_LENGTH + 16];
        // No trailing newline: forces the cap to trip.
        let last = bytes.len() - 1;
        bytes[last] = b'a';
        let err = decode_one_frame(&bytes).expect_err("overlong ndjson line should be rejected");
        assert_eq!(err.kind(), ErrorKind::InvalidData);
        assert!(
            err.to_string().contains("exceeds maximum"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn read_frame_reports_eof_on_closed_stream() {
        // An empty stream surfaces UnexpectedEof (stream closed),
        // matching the legacy reader's contract.
        let err = decode_one_frame(b"").expect_err("empty stream should be UnexpectedEof");
        assert_eq!(err.kind(), ErrorKind::UnexpectedEof);
    }

    /// Legacy LSP-framing MCP server (still speaks `Content-Length`).
    /// Proves the *read* path stays bidirectionally tolerant: our client
    /// writes NDJSON, but a server that replies in the old LSP dialect is
    /// still understood end-to-end (initialize → tools/list → tools/call).
    /// (legacy LSP-framing tolerance)
    #[allow(clippy::too_many_lines)]
    fn write_legacy_lsp_mcp_server_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("legacy-lsp-mcp-server.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, sys",
            "",
            "# Reads NDJSON (the client always writes NDJSON now) but",
            "# REPLIES in the legacy LSP Content-Length dialect, so the",
            "# client's bidirectional read tolerance is exercised.",
            "def read_message():",
            "    line = sys.stdin.readline()",
            "    if not line:",
            "        return None",
            "    return json.loads(line)",
            "",
            "def send_message(message):",
            "    payload = json.dumps(message).encode()",
            r"    sys.stdout.buffer.write(f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload)",
            "    sys.stdout.buffer.flush()",
            "",
            "while True:",
            "    request = read_message()",
            "    if request is None:",
            "        break",
            "    method = request['method']",
            "    if 'id' not in request:",
            "        continue",
            "    if method == 'initialize':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'protocolVersion': request['params']['protocolVersion'],",
            "                'capabilities': {'tools': {}},",
            "                'serverInfo': {'name': 'legacy-lsp', 'version': '0.1.0'}",
            "            }",
            "        })",
            "    elif method == 'tools/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'tools': [",
            "                    {",
            "                        'name': 'echo',",
            "                        'description': 'legacy echo',",
            "                        'inputSchema': {'type': 'object'}",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    elif method == 'tools/call':",
            "        args = request['params'].get('arguments') or {}",
            "        text = args.get('text', '')",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'content': [{'type': 'text', 'text': f'legacy:{text}'}],",
            "                'isError': False",
            "            }",
            "        })",
            "    else:",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'error': {'code': -32601, 'message': f'unknown method: {method}'},",
            "        })",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn legacy_lsp_server_round_trips_against_ndjson_client() {
        // legacy LSP-framing tolerance: client writes NDJSON, server
        // replies Content-Length — the full discover+call still works.
        let script_path = write_legacy_lsp_mcp_server_script();
        let root = script_path.parent().expect("script parent");
        let log_path = root.join("legacy.log");
        let servers = BTreeMap::from([(
            "legacy".to_string(),
            manager_server_config(&script_path, "legacy", &log_path),
        )]);
        let mut handle = McpManagerHandle::from_manager(McpServerManager::from_servers(&servers))
            .expect("build sync handle");

        let tools = handle.discover_tools().expect("discover via legacy server");
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].raw_name, "echo");
        assert!(handle.discovery_failures().is_empty());

        let response = handle
            .call_tool(&mcp_tool_name("legacy", "echo"), Some(json!({"text": "hi"})))
            .expect("call tool on legacy server");
        let result = response.result.expect("tool result");
        assert_eq!(result.content.len(), 1);
        assert_eq!(
            result.content[0].data.get("text"),
            Some(&json!("legacy:hi"))
        );

        handle.shutdown().expect("shutdown");
        cleanup_script(&script_path);
    }

    /// NDJSON MCP server that logs the EXACT method of every message it
    /// receives (requests AND notifications), so the protocol-level
    /// regression test below can assert the full canonical handshake
    /// order over the real wire dialect.
    #[allow(clippy::too_many_lines)]
    fn write_ndjson_protocol_server_script() -> PathBuf {
        let root = temp_dir();
        fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("ndjson-protocol-server.py");
        let script = [
            "#!/usr/bin/env python3",
            "import json, os, sys",
            "LOG_PATH = os.environ.get('MCP_LOG_PATH')",
            "",
            "def log(method):",
            "    if LOG_PATH:",
            "        with open(LOG_PATH, 'a', encoding='utf-8') as handle:",
            "            handle.write(f'{method}\\n')",
            "",
            "def read_message():",
            "    line = sys.stdin.readline()",
            "    if not line:",
            "        return None",
            "    return json.loads(line)",
            "",
            "def send_message(message):",
            r"    sys.stdout.write(json.dumps(message) + '\n')",
            "    sys.stdout.flush()",
            "",
            "while True:",
            "    request = read_message()",
            "    if request is None:",
            "        break",
            "    method = request['method']",
            "    log(method)",
            "    if 'id' not in request:",
            "        continue",
            "    if method == 'initialize':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'protocolVersion': request['params']['protocolVersion'],",
            "                'capabilities': {'tools': {}},",
            "                'serverInfo': {'name': 'ndjson-proto', 'version': '1.0.0'}",
            "            }",
            "        })",
            "    elif method == 'tools/list':",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'tools': [",
            "                    {",
            "                        'name': 'echo',",
            "                        'description': 'ndjson echo',",
            "                        'inputSchema': {'type': 'object'}",
            "                    }",
            "                ]",
            "            }",
            "        })",
            "    elif method == 'tools/call':",
            "        args = request['params'].get('arguments') or {}",
            "        text = args.get('text', '')",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'result': {",
            "                'content': [{'type': 'text', 'text': f'echo:{text}'}],",
            "                'isError': False",
            "            }",
            "        })",
            "    else:",
            "        send_message({",
            "            'jsonrpc': '2.0',",
            "            'id': request['id'],",
            "            'error': {'code': -32601, 'message': f'unknown method: {method}'},",
            "        })",
            "",
        ]
        .join("\n");
        fs::write(&script_path, script).expect("write script");
        make_executable(&script_path);
        script_path
    }

    #[test]
    fn ndjson_server_completes_full_protocol_handshake() {
        // The most important Track R regression: against a server that
        // speaks the REAL MCP stdio dialect (NDJSON, like codex), the
        // client must drive initialize → notifications/initialized →
        // tools/list → tools/call in order. The pre-fix LSP framing made
        // a real NDJSON server go silent, so this would have hung at the
        // initialize timeout.
        let runtime = Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let script_path = write_ndjson_protocol_server_script();
            let root = script_path.parent().expect("script parent");
            let log_path = root.join("proto.log");
            let servers = BTreeMap::from([(
                "proto".to_string(),
                manager_server_config(&script_path, "proto", &log_path),
            )]);
            let mut manager = McpServerManager::from_servers(&servers);

            let tools = manager.discover_tools().await.expect("ndjson discover");
            assert_eq!(tools.len(), 1);
            assert_eq!(tools[0].raw_name, "echo");

            let call = manager
                .call_tool(&mcp_tool_name("proto", "echo"), Some(json!({"text": "live"})))
                .await
                .expect("ndjson tool call");
            let result = call.result.expect("tool result");
            assert_eq!(
                result.content[0].data.get("text"),
                Some(&json!("echo:live"))
            );

            // Exact canonical handshake order over the real wire dialect.
            let log = fs::read_to_string(&log_path).expect("read log");
            assert_eq!(
                log.lines().collect::<Vec<_>>(),
                vec![
                    "initialize",
                    "notifications/initialized",
                    "tools/list",
                    "tools/call"
                ]
            );

            manager.shutdown().await.expect("shutdown");
            cleanup_script(&script_path);
        });
    }

    // ─── v0.4.25: built-in `codex exec` backend selection in the manager ───

    fn codex_entry(command: &str, args: &[&str]) -> ScopedMcpServerConfig {
        ScopedMcpServerConfig {
            scope: ConfigSource::User,
            config: McpServerConfig::Stdio(McpStdioServerConfig {
                command: command.to_string(),
                args: args.iter().map(|a| (*a).to_string()).collect(),
                env: BTreeMap::from([("CODEX_HOME".to_string(), "/legacy-home".to_string())]),
                request_timeout_secs: Some(900),
                trust: Some(true),
            }),
        }
    }

    #[test]
    fn manager_registers_builtin_codex_when_no_entry_and_discovers_two_tools() {
        let bridge = crate::CodexExecBridge::new("/opt/codex");
        let manager = McpServerManager::from_servers_with_codex(&BTreeMap::new(), Some(&bridge));
        assert_eq!(manager.codex_exec_backend("codex"), Some(&bridge));

        let mut handle = McpManagerHandle::from_manager(manager).unwrap();
        let tools = handle.discover_tools().unwrap();
        let names: Vec<&str> = tools.iter().map(|t| t.qualified_name.as_str()).collect();
        assert_eq!(names, vec!["mcp__codex__codex", "mcp__codex__codex-reply"]);
        assert!(handle.discovery_failures().is_empty());
        // no process was spawned for discovery, so shutdown is a no-op
        handle.shutdown().unwrap();
    }

    #[test]
    fn manager_migrates_legacy_codex_entry_in_memory() {
        let servers = BTreeMap::from([(
            "codex".to_string(),
            codex_entry("codex", &["mcp-server", "-c", "model_reasoning_effort=\"xhigh\""]),
        )]);
        let bridge = crate::CodexExecBridge::new("/opt/codex");
        let manager = McpServerManager::from_servers_with_codex(&servers, Some(&bridge));
        let migrated = manager.codex_exec_backend("codex").expect("legacy entry migrated");
        assert_eq!(migrated.codex_bin, PathBuf::from("/opt/codex"));
        assert_eq!(migrated.env.get("CODEX_HOME").map(String::as_str), Some("/legacy-home"));
        assert_eq!(migrated.timeout, std::time::Duration::from_mins(15));

        // without the built-in enabled, the same entry is a plain stdio server
        // (v0.4.24 behaviour, the ARIS_CODEX_BRIDGE=0 escape hatch)
        let plain = McpServerManager::from_servers(&servers);
        assert_eq!(plain.codex_exec_backend("codex"), None);
    }

    #[test]
    fn manager_keeps_custom_codex_entry_over_builtin() {
        let servers = BTreeMap::from([(
            "codex".to_string(),
            codex_entry("python3", &["/aris/mcp-servers/codex-exec/server.py"]),
        )]);
        let bridge = crate::CodexExecBridge::new("/opt/codex");
        let manager = McpServerManager::from_servers_with_codex(&servers, Some(&bridge));
        assert_eq!(manager.codex_exec_backend("codex"), None);
        assert_eq!(manager.servers.len(), 1);
    }
}
