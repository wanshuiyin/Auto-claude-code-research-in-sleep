mod config;
mod init;
mod input;
mod memories;
mod meta_optimize;
mod openai_executor;
mod render;

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use api::{
    resolve_startup_auth_source, AnthropicClient, AuthSource, ContentBlockDelta, InputContentBlock,
    InputMessage, MessageRequest, MessageResponse, OutputContentBlock,
    StreamEvent as ApiStreamEvent, ToolChoice, ToolDefinition, ToolResultContentBlock,
};

use commands::{
    render_slash_command_help, resume_supported_slash_commands, slash_command_specs, SlashCommand,
};
use compat_harness::{extract_manifest, UpstreamPaths};
use init::initialize_repo;
use render::{MarkdownStreamState, Spinner, TerminalRenderer};
use runtime::{
    clear_oauth_credentials, generate_pkce_pair, generate_state, load_system_prompt,
    parse_oauth_callback_request_target, save_oauth_credentials, ApiClient, ApiRequest,
    AssistantEvent, CompactionConfig, ConfigLoader, ConfigSource, ContentBlock,
    ConversationMessage, ConversationRuntime, MessageRole, OAuthAuthorizationRequest, OAuthConfig,
    OAuthTokenExchangeRequest, PermissionMode, PermissionPolicy, ProjectContext, RuntimeError,
    Session, TokenUsage, ToolError, ToolExecutor, UsageTracker,
};
use serde_json::json;
use tools::{execute_tool, mvp_tool_specs, ToolSpec};

const DEFAULT_MODEL: &str = "claude-opus-4-6";
fn max_tokens_for_model(model: &str) -> u32 {
    if model.contains("opus") {
        32_000
    } else if model.contains("gpt") || model.contains("o3") || model.contains("o4") {
        16_384
    } else {
        // Works for Claude sonnet/haiku (64k), and most OpenAI-compat providers
        64_000
    }
}
const DEFAULT_DATE: &str = "2026-03-31";
const DEFAULT_OAUTH_CALLBACK_PORT: u16 = 4545;
const VERSION: &str = env!("CARGO_PKG_VERSION");
const BUILD_TARGET: Option<&str> = option_env!("TARGET");
const GIT_SHA: Option<&str> = option_env!("GIT_SHA");

pub(crate) type AllowedToolSet = BTreeSet<String>;

/// True if the process has at least one usable executor auth source for the
/// currently selected executor provider. Mirrors the real resolution in
/// `resolve_openai_executor_config` and `api::resolve_startup_auth_source` so
/// the "no API key, run setup" guard does not misfire for users with
/// legitimate credentials. We deliberately do NOT probe the macOS keychain —
/// the API client handles that with proper error propagation.
///
/// Importantly, this is gated on `EXECUTOR_PROVIDER`: if the user selected
/// `openai`, an Anthropic OAuth token on disk is NOT usable auth — letting it
/// pass the gate would skip setup then fall back to an Anthropic runtime with
/// an OpenAI model, which fails in confusing ways.
fn has_any_executor_auth() -> bool {
    let env_non_empty = |name: &str| {
        std::env::var(name)
            .ok()
            .map(|v| !v.trim().is_empty())
            .unwrap_or(false)
    };

    // Use EXACT match (no trim) to stay 1:1 with `resolve_openai_executor_config()`.
    // If we trimmed here but the resolver didn't, a value like `"openai "` would
    // pass the gate but the resolver would reject it, causing a silent fallback
    // to the Anthropic runtime with an OpenAI model.
    let openai_selected = std::env::var("EXECUTOR_PROVIDER")
        .ok()
        .as_deref()
        == Some("openai");

    if openai_selected {
        // OpenAI-compat executor: only OpenAI-style keys count. Anthropic
        // OAuth tokens can't authenticate an OpenAI endpoint, so they must
        // NOT make this function return true.
        return env_non_empty("EXECUTOR_API_KEY") || env_non_empty("OPENAI_API_KEY");
    }

    // Anthropic executor (default or explicit): native API key or Bearer token.
    if env_non_empty("ANTHROPIC_API_KEY") || env_non_empty("ANTHROPIC_AUTH_TOKEN") {
        return true;
    }

    // Saved OAuth credentials. Mirrors `api::resolve_startup_auth_source`:
    //   - non-expired token → usable
    //   - expired token + refresh_token → usable ONLY if the runtime OAuth
    //     config is loadable (refresh needs the client_id/endpoint from it)
    //   - expired without refresh → NOT usable, fall through to setup
    //
    // `load_oauth_credentials` / `runtime_oauth_config_loadable` are offline
    // file reads; no network calls happen in this gate.
    if let Ok(Some(token)) = runtime::load_oauth_credentials() {
        let expired = token
            .expires_at
            .is_some_and(|ts| ts <= unix_timestamp_now());
        if !expired {
            return true;
        }
        let has_refresh = token.refresh_token.as_deref().is_some_and(|s| !s.is_empty());
        if has_refresh && runtime_oauth_config_loadable() {
            return true;
        }
    }

    false
}

/// True if the runtime OAuth config (client_id + endpoints) can be loaded from
/// disk. Used by `has_any_executor_auth` to decide whether an expired-with-
/// refresh token will actually be refreshable on first API call.
fn runtime_oauth_config_loadable() -> bool {
    let Ok(cwd) = env::current_dir() else {
        return false;
    };
    ConfigLoader::default_for(&cwd)
        .load()
        .ok()
        .and_then(|cfg| cfg.oauth().cloned())
        .is_some()
}

fn unix_timestamp_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn main() {
    if let Err(error) = run() {
        eprintln!(
            "error: {error}

Run `aris --help` for usage."
        );
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    // Load saved ARIS config and apply to env (env vars always take priority)
    let saved_config = config::ArisConfig::load();
    saved_config.apply_to_env();
    init_aris_tasks_env();

    let args: Vec<String> = env::args().skip(1).collect();
    let action = parse_args(&args)?;

    // For REPL and Prompt modes: if no executor auth is available, run setup first.
    // Must mirror the real auth resolution in resolve_openai_executor_config() +
    // api::resolve_startup_auth_source() — otherwise a user whose auth DOES work
    // (shell env var or saved OAuth credentials) would be wrongly routed through
    // setup, and force_apply_to_env() would erase their shell-provided key.
    let needs_api_key = matches!(action, CliAction::Repl { .. } | CliAction::Prompt { .. });
    if needs_api_key && !has_any_executor_auth() {
        println!("\x1b[1;33mNo API key found.\x1b[0m Let's set up ARIS first.\n");
        let new_config = config::run_interactive_setup()?;
        // Force-apply only EXECUTOR env vars. This overrides any stale
        // executor values left over from `saved_config.apply_to_env()` above
        // (e.g. `EXECUTOR_BASE_URL` pointing at an old proxy URL), while
        // preserving shell-provided reviewer keys like `OPENAI_API_KEY`,
        // `GEMINI_API_KEY`, etc. Using the full `force_apply_to_env()` here
        // would wipe a reviewer key the user set in their shell but did not
        // retype during the wizard.
        new_config.force_apply_executor_env();
    }

    match action {
        CliAction::DumpManifests => dump_manifests(),
        CliAction::BootstrapPlan => print_bootstrap_plan(),
        CliAction::PrintSystemPrompt { cwd, date } => print_system_prompt(cwd, date),
        CliAction::Version => print_version(),
        CliAction::ResumeSession {
            session_path,
            commands,
        } => resume_session(&session_path, &commands),
        CliAction::Prompt {
            prompt,
            model,
            output_format,
            allowed_tools,
            permission_mode,
        } => LiveCli::new(model, true, allowed_tools, permission_mode)?
            .run_turn_with_output(&prompt, output_format)?,
        CliAction::Login => run_login()?,
        CliAction::Logout => run_logout()?,
        CliAction::Init => run_init()?,
        CliAction::Repl {
            model,
            allowed_tools,
            permission_mode,
        } => {
            // Use saved model from config if user didn't specify --model
            let model = if model == DEFAULT_MODEL {
                saved_config
                    .executor_model()
                    .map(|m| resolve_model_alias(m).to_string())
                    .unwrap_or(model)
            } else {
                model
            };
            run_repl(model, allowed_tools, permission_mode)?;
        }
        CliAction::Help => print_help(),
        CliAction::Setup => {
            config::run_interactive_setup()?;
        }
        CliAction::Doctor => run_doctor()?,
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum CliAction {
    DumpManifests,
    BootstrapPlan,
    PrintSystemPrompt {
        cwd: PathBuf,
        date: String,
    },
    Version,
    ResumeSession {
        session_path: PathBuf,
        commands: Vec<String>,
    },
    Prompt {
        prompt: String,
        model: String,
        output_format: CliOutputFormat,
        allowed_tools: Option<AllowedToolSet>,
        permission_mode: PermissionMode,
    },
    Login,
    Logout,
    Init,
    Repl {
        model: String,
        allowed_tools: Option<AllowedToolSet>,
        permission_mode: PermissionMode,
    },
    // prompt-mode formatting is only supported for non-interactive runs
    Help,
    Setup,
    Doctor,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CliOutputFormat {
    Text,
    Json,
}

impl CliOutputFormat {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "text" => Ok(Self::Text),
            "json" => Ok(Self::Json),
            other => Err(format!(
                "unsupported value for --output-format: {other} (expected text or json)"
            )),
        }
    }
}

#[allow(clippy::too_many_lines)]
fn parse_args(args: &[String]) -> Result<CliAction, String> {
    let mut model = DEFAULT_MODEL.to_string();
    let mut output_format = CliOutputFormat::Text;
    let mut permission_mode = default_permission_mode();
    let mut wants_version = false;
    let mut allowed_tool_values = Vec::new();
    let mut rest = Vec::new();
    let mut index = 0;

    while index < args.len() {
        match args[index].as_str() {
            "--version" | "-V" => {
                wants_version = true;
                index += 1;
            }
            "--model" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --model".to_string())?;
                model = resolve_model_alias(value).to_string();
                index += 2;
            }
            flag if flag.starts_with("--model=") => {
                model = resolve_model_alias(&flag[8..]).to_string();
                index += 1;
            }
            "--output-format" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --output-format".to_string())?;
                output_format = CliOutputFormat::parse(value)?;
                index += 2;
            }
            "--permission-mode" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --permission-mode".to_string())?;
                permission_mode = parse_permission_mode_arg(value)?;
                index += 2;
            }
            flag if flag.starts_with("--output-format=") => {
                output_format = CliOutputFormat::parse(&flag[16..])?;
                index += 1;
            }
            flag if flag.starts_with("--permission-mode=") => {
                permission_mode = parse_permission_mode_arg(&flag[18..])?;
                index += 1;
            }
            "--dangerously-skip-permissions" => {
                permission_mode = PermissionMode::DangerFullAccess;
                index += 1;
            }
            "-p" => {
                // Claude Code compat: -p "prompt" = one-shot prompt
                let prompt = args[index + 1..].join(" ");
                if prompt.trim().is_empty() {
                    return Err("-p requires a prompt string".to_string());
                }
                return Ok(CliAction::Prompt {
                    prompt,
                    model: resolve_model_alias(&model).to_string(),
                    output_format,
                    allowed_tools: normalize_allowed_tools(&allowed_tool_values)?,
                    permission_mode,
                });
            }
            "--print" => {
                // Claude Code compat: --print makes output non-interactive
                output_format = CliOutputFormat::Text;
                index += 1;
            }
            "--allowedTools" | "--allowed-tools" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --allowedTools".to_string())?;
                allowed_tool_values.push(value.clone());
                index += 2;
            }
            flag if flag.starts_with("--allowedTools=") => {
                allowed_tool_values.push(flag[15..].to_string());
                index += 1;
            }
            flag if flag.starts_with("--allowed-tools=") => {
                allowed_tool_values.push(flag[16..].to_string());
                index += 1;
            }
            other => {
                rest.push(other.to_string());
                index += 1;
            }
        }
    }

    if wants_version {
        return Ok(CliAction::Version);
    }

    let allowed_tools = normalize_allowed_tools(&allowed_tool_values)?;

    if rest.is_empty() {
        return Ok(CliAction::Repl {
            model,
            allowed_tools,
            permission_mode,
        });
    }
    if matches!(rest.first().map(String::as_str), Some("--help" | "-h")) {
        return Ok(CliAction::Help);
    }
    if rest.first().map(String::as_str) == Some("--resume") {
        return parse_resume_args(&rest[1..]);
    }

    match rest[0].as_str() {
        "dump-manifests" => Ok(CliAction::DumpManifests),
        "bootstrap-plan" => Ok(CliAction::BootstrapPlan),
        "system-prompt" => parse_system_prompt_args(&rest[1..]),
        "login" => Ok(CliAction::Login),
        "logout" => Ok(CliAction::Logout),
        "init" => Ok(CliAction::Init),
        "setup" => Ok(CliAction::Setup),
        "doctor" => Ok(CliAction::Doctor),
        "prompt" => {
            let prompt = rest[1..].join(" ");
            if prompt.trim().is_empty() {
                return Err("prompt subcommand requires a prompt string".to_string());
            }
            Ok(CliAction::Prompt {
                prompt,
                model,
                output_format,
                allowed_tools,
                permission_mode,
            })
        }
        other if !other.starts_with('/') => Ok(CliAction::Prompt {
            prompt: rest.join(" "),
            model,
            output_format,
            allowed_tools,
            permission_mode,
        }),
        other => Err(format!("unknown subcommand: {other}")),
    }
}

fn resolve_model_alias(model: &str) -> &str {
    // When using OpenAI-compat executor, don't map to Claude model IDs
    if std::env::var("EXECUTOR_PROVIDER")
        .ok()
        .is_some_and(|p| p == "openai")
    {
        return model;
    }
    match model {
        "opus" => "claude-opus-4-6",
        "sonnet" => "claude-sonnet-4-6",
        "haiku" => "claude-haiku-4-5-20251001",
        _ => model,
    }
}

fn normalize_allowed_tools(values: &[String]) -> Result<Option<AllowedToolSet>, String> {
    if values.is_empty() {
        return Ok(None);
    }

    let canonical_names = mvp_tool_specs()
        .into_iter()
        .map(|spec| spec.name.to_string())
        .collect::<Vec<_>>();
    let mut name_map = canonical_names
        .iter()
        .map(|name| (normalize_tool_name(name), name.clone()))
        .collect::<BTreeMap<_, _>>();

    for (alias, canonical) in [
        ("read", "read_file"),
        ("write", "write_file"),
        ("edit", "edit_file"),
        ("glob", "glob_search"),
        ("grep", "grep_search"),
    ] {
        name_map.insert(alias.to_string(), canonical.to_string());
    }

    let mut allowed = AllowedToolSet::new();
    for value in values {
        for token in value
            .split(|ch: char| ch == ',' || ch.is_whitespace())
            .filter(|token| !token.is_empty())
        {
            let normalized = normalize_tool_name(token);
            let canonical = name_map.get(&normalized).ok_or_else(|| {
                format!(
                    "unsupported tool in --allowedTools: {token} (expected one of: {})",
                    canonical_names.join(", ")
                )
            })?;
            allowed.insert(canonical.clone());
        }
    }

    Ok(Some(allowed))
}

fn normalize_tool_name(value: &str) -> String {
    value.trim().replace('-', "_").to_ascii_lowercase()
}

fn parse_permission_mode_arg(value: &str) -> Result<PermissionMode, String> {
    normalize_permission_mode(value)
        .ok_or_else(|| {
            format!(
                "unsupported permission mode '{value}'. Use read-only, workspace-write, or danger-full-access."
            )
        })
        .map(permission_mode_from_label)
}

fn permission_mode_from_label(mode: &str) -> PermissionMode {
    match mode {
        "read-only" => PermissionMode::ReadOnly,
        "workspace-write" => PermissionMode::WorkspaceWrite,
        "danger-full-access" => PermissionMode::DangerFullAccess,
        other => panic!("unsupported permission mode label: {other}"),
    }
}

fn default_permission_mode() -> PermissionMode {
    env::var("RUSTY_CLAUDE_PERMISSION_MODE")
        .ok()
        .as_deref()
        .and_then(normalize_permission_mode)
        .map_or(PermissionMode::DangerFullAccess, permission_mode_from_label)
}

pub(crate) fn filter_tool_specs(allowed_tools: Option<&AllowedToolSet>) -> Vec<tools::ToolSpec> {
    mvp_tool_specs()
        .into_iter()
        .filter(|spec| allowed_tools.is_none_or(|allowed| allowed.contains(spec.name)))
        .collect()
}

fn parse_system_prompt_args(args: &[String]) -> Result<CliAction, String> {
    let mut cwd = env::current_dir().map_err(|error| error.to_string())?;
    let mut date = DEFAULT_DATE.to_string();
    let mut index = 0;

    while index < args.len() {
        match args[index].as_str() {
            "--cwd" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --cwd".to_string())?;
                cwd = PathBuf::from(value);
                index += 2;
            }
            "--date" => {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "missing value for --date".to_string())?;
                date.clone_from(value);
                index += 2;
            }
            other => return Err(format!("unknown system-prompt option: {other}")),
        }
    }

    Ok(CliAction::PrintSystemPrompt { cwd, date })
}

fn parse_resume_args(args: &[String]) -> Result<CliAction, String> {
    let session_path = args
        .first()
        .ok_or_else(|| "missing session path for --resume".to_string())
        .map(PathBuf::from)?;
    let commands = args[1..].to_vec();
    if commands
        .iter()
        .any(|command| !command.trim_start().starts_with('/'))
    {
        return Err("--resume trailing arguments must be slash commands".to_string());
    }
    Ok(CliAction::ResumeSession {
        session_path,
        commands,
    })
}

fn dump_manifests() {
    let workspace_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let paths = UpstreamPaths::from_workspace_dir(&workspace_dir);
    match extract_manifest(&paths) {
        Ok(manifest) => {
            println!("commands: {}", manifest.commands.entries().len());
            println!("tools: {}", manifest.tools.entries().len());
            println!("bootstrap phases: {}", manifest.bootstrap.phases().len());
        }
        Err(error) => {
            eprintln!("failed to extract manifests: {error}");
            std::process::exit(1);
        }
    }
}

fn print_bootstrap_plan() {
    for phase in runtime::BootstrapPlan::claude_code_default().phases() {
        println!("- {phase:?}");
    }
}

fn default_oauth_config() -> OAuthConfig {
    OAuthConfig {
        client_id: String::from("9d1c250a-e61b-44d9-88ed-5944d1962f5e"),
        authorize_url: String::from("https://platform.claude.com/oauth/authorize"),
        token_url: String::from("https://platform.claude.com/v1/oauth/token"),
        callback_port: None,
        manual_redirect_url: None,
        scopes: vec![
            String::from("user:profile"),
            String::from("user:inference"),
            String::from("user:sessions:claude_code"),
        ],
    }
}

fn run_login() -> Result<(), Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let config = ConfigLoader::default_for(&cwd).load()?;
    let default_oauth = default_oauth_config();
    let oauth = config.oauth().unwrap_or(&default_oauth);
    let callback_port = oauth.callback_port.unwrap_or(DEFAULT_OAUTH_CALLBACK_PORT);
    let redirect_uri = runtime::loopback_redirect_uri(callback_port);
    let pkce = generate_pkce_pair()?;
    let state = generate_state()?;
    let authorize_url =
        OAuthAuthorizationRequest::from_config(oauth, redirect_uri.clone(), state.clone(), &pkce)
            .build_url();

    println!("Starting Claude OAuth login...");
    println!("Listening for callback on {redirect_uri}");
    if let Err(error) = open_browser(&authorize_url) {
        eprintln!("warning: failed to open browser automatically: {error}");
        println!("Open this URL manually:\n{authorize_url}");
    }

    let callback = wait_for_oauth_callback(callback_port)?;
    if let Some(error) = callback.error {
        let description = callback
            .error_description
            .unwrap_or_else(|| "authorization failed".to_string());
        return Err(io::Error::other(format!("{error}: {description}")).into());
    }
    let code = callback.code.ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "callback did not include code")
    })?;
    let returned_state = callback.state.ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "callback did not include state")
    })?;
    if returned_state != state {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "oauth state mismatch").into());
    }

    let client = AnthropicClient::from_auth(AuthSource::None).with_base_url(api::read_base_url());
    let exchange_request =
        OAuthTokenExchangeRequest::from_config(oauth, code, state, pkce.verifier, redirect_uri);
    let runtime = tokio::runtime::Runtime::new()?;
    let token_set = runtime.block_on(client.exchange_oauth_code(oauth, &exchange_request))?;
    save_oauth_credentials(&runtime::OAuthTokenSet {
        access_token: token_set.access_token,
        refresh_token: token_set.refresh_token,
        expires_at: token_set.expires_at,
        scopes: token_set.scopes,
    })?;
    println!("Claude OAuth login complete.");
    Ok(())
}

fn run_logout() -> Result<(), Box<dyn std::error::Error>> {
    clear_oauth_credentials()?;
    println!("Claude OAuth credentials cleared.");
    Ok(())
}

fn open_browser(url: &str) -> io::Result<()> {
    let commands = if cfg!(target_os = "macos") {
        vec![("open", vec![url])]
    } else if cfg!(target_os = "windows") {
        vec![("cmd", vec!["/C", "start", "", url])]
    } else {
        vec![("xdg-open", vec![url])]
    };
    for (program, args) in commands {
        match Command::new(program).args(args).spawn() {
            Ok(_) => return Ok(()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::NotFound,
        "no supported browser opener command found",
    ))
}

fn wait_for_oauth_callback(
    port: u16,
) -> Result<runtime::OAuthCallbackParams, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    let (mut stream, _) = listener.accept()?;
    let mut buffer = [0_u8; 4096];
    let bytes_read = stream.read(&mut buffer)?;
    let request = String::from_utf8_lossy(&buffer[..bytes_read]);
    let request_line = request.lines().next().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "missing callback request line")
    })?;
    let target = request_line.split_whitespace().nth(1).ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "missing callback request target",
        )
    })?;
    let callback = parse_oauth_callback_request_target(target)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    let body = if callback.error.is_some() {
        "Claude OAuth login failed. You can close this window."
    } else {
        "Claude OAuth login succeeded. You can close this window."
    };
    let response = format!(
        "HTTP/1.1 200 OK\r\ncontent-type: text/plain; charset=utf-8\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    stream.write_all(response.as_bytes())?;
    Ok(callback)
}

fn print_system_prompt(cwd: PathBuf, date: String) {
    match load_system_prompt(cwd, date, env::consts::OS, "unknown", None) {
        Ok(sections) => println!("{}", sections.join("\n\n")),
        Err(error) => {
            eprintln!("failed to build system prompt: {error}");
            std::process::exit(1);
        }
    }
}

fn print_version() {
    println!("{}", render_version_report());
}

fn resume_session(session_path: &Path, commands: &[String]) {
    let session = match Session::load_from_path(session_path) {
        Ok(session) => session,
        Err(error) => {
            eprintln!("failed to restore session: {error}");
            std::process::exit(1);
        }
    };

    if commands.is_empty() {
        println!(
            "Restored session from {} ({} messages).",
            session_path.display(),
            session.messages.len()
        );
        return;
    }

    let mut session = session;
    for raw_command in commands {
        let Some(command) = SlashCommand::parse(raw_command) else {
            eprintln!("unsupported resumed command: {raw_command}");
            std::process::exit(2);
        };
        match run_resume_command(session_path, &session, &command) {
            Ok(ResumeCommandOutcome {
                session: next_session,
                message,
            }) => {
                session = next_session;
                if let Some(message) = message {
                    println!("{message}");
                }
            }
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(2);
            }
        }
    }
}

#[derive(Debug, Clone)]
struct ResumeCommandOutcome {
    session: Session,
    message: Option<String>,
}

#[derive(Debug, Clone)]
struct StatusContext {
    cwd: PathBuf,
    session_path: Option<PathBuf>,
    loaded_config_files: usize,
    discovered_config_files: usize,
    memory_file_count: usize,
    project_root: Option<PathBuf>,
    git_branch: Option<String>,
}

#[derive(Debug, Clone, Copy)]
struct StatusUsage {
    message_count: usize,
    turns: u32,
    latest: TokenUsage,
    cumulative: TokenUsage,
    estimated_tokens: usize,
}

fn format_model_report(model: &str, message_count: usize, turns: u32) -> String {
    format!(
        "Model
  Current model    {model}
  Session messages {message_count}
  Session turns    {turns}

Usage
  Inspect current model with /model
  Switch models with /model <name>"
    )
}

fn format_model_switch_report(previous: &str, next: &str, message_count: usize) -> String {
    format!(
        "Model updated
  Previous         {previous}
  Current          {next}
  Preserved msgs   {message_count}"
    )
}

fn format_permissions_report(mode: &str) -> String {
    let modes = [
        ("read-only", "Read/search tools only", mode == "read-only"),
        (
            "workspace-write",
            "Edit files inside the workspace",
            mode == "workspace-write",
        ),
        (
            "danger-full-access",
            "Unrestricted tool access",
            mode == "danger-full-access",
        ),
    ]
    .into_iter()
    .map(|(name, description, is_current)| {
        let marker = if is_current {
            "● current"
        } else {
            "○ available"
        };
        format!("  {name:<18} {marker:<11} {description}")
    })
    .collect::<Vec<_>>()
    .join(
        "
",
    );

    format!(
        "Permissions
  Active mode      {mode}
  Mode status      live session default

Modes
{modes}

Usage
  Inspect current mode with /permissions
  Switch modes with /permissions <mode>"
    )
}

fn format_permissions_switch_report(previous: &str, next: &str) -> String {
    format!(
        "Permissions updated
  Result           mode switched
  Previous mode    {previous}
  Active mode      {next}
  Applies to       subsequent tool calls
  Usage            /permissions to inspect current mode"
    )
}

fn format_cost_report(usage: TokenUsage) -> String {
    format!(
        "Cost
  Input tokens     {}
  Output tokens    {}
  Cache create     {}
  Cache read       {}
  Total tokens     {}",
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_creation_input_tokens,
        usage.cache_read_input_tokens,
        usage.total_tokens(),
    )
}

fn format_resume_report(session_path: &str, message_count: usize, turns: u32) -> String {
    format!(
        "Session resumed
  Session file     {session_path}
  Messages         {message_count}
  Turns            {turns}"
    )
}

fn format_compact_report(removed: usize, resulting_messages: usize, skipped: bool) -> String {
    if skipped {
        format!(
            "Compact
  Result           skipped
  Reason           session below compaction threshold
  Messages kept    {resulting_messages}"
        )
    } else {
        format!(
            "Compact
  Result           compacted
  Messages removed {removed}
  Messages kept    {resulting_messages}"
        )
    }
}

fn format_auto_compaction_notice(removed: usize) -> String {
    format!("[auto-compacted: removed {removed} messages]")
}

fn parse_git_status_metadata(status: Option<&str>) -> (Option<PathBuf>, Option<String>) {
    let Some(status) = status else {
        return (None, None);
    };
    let branch = status.lines().next().and_then(|line| {
        line.strip_prefix("## ")
            .map(|line| {
                line.split(['.', ' '])
                    .next()
                    .unwrap_or_default()
                    .to_string()
            })
            .filter(|value| !value.is_empty())
    });
    let project_root = find_git_root().ok();
    (project_root, branch)
}

fn find_git_root() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let output = std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(env::current_dir()?)
        .output()?;
    if !output.status.success() {
        return Err("not a git repository".into());
    }
    let path = String::from_utf8(output.stdout)?.trim().to_string();
    if path.is_empty() {
        return Err("empty git root".into());
    }
    Ok(PathBuf::from(path))
}

#[allow(clippy::too_many_lines)]
fn run_resume_command(
    session_path: &Path,
    session: &Session,
    command: &SlashCommand,
) -> Result<ResumeCommandOutcome, Box<dyn std::error::Error>> {
    match command {
        SlashCommand::Help => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(render_repl_help()),
        }),
        SlashCommand::Compact => {
            let result = runtime::compact_session(
                session,
                CompactionConfig {
                    max_estimated_tokens: 0,
                    ..CompactionConfig::default()
                },
            );
            let removed = result.removed_message_count;
            let kept = result.compacted_session.messages.len();
            let skipped = removed == 0;
            result.compacted_session.save_to_path(session_path)?;
            Ok(ResumeCommandOutcome {
                session: result.compacted_session,
                message: Some(format_compact_report(removed, kept, skipped)),
            })
        }
        SlashCommand::Clear { confirm } => {
            if !confirm {
                return Ok(ResumeCommandOutcome {
                    session: session.clone(),
                    message: Some(
                        "clear: confirmation required; rerun with /clear --confirm".to_string(),
                    ),
                });
            }
            let cleared = Session::new();
            cleared.save_to_path(session_path)?;
            Ok(ResumeCommandOutcome {
                session: cleared,
                message: Some(format!(
                    "Cleared resumed session file {}.",
                    session_path.display()
                )),
            })
        }
        SlashCommand::Status => {
            let tracker = UsageTracker::from_session(session);
            let usage = tracker.cumulative_usage();
            Ok(ResumeCommandOutcome {
                session: session.clone(),
                message: Some(format_status_report(
                    "restored-session",
                    StatusUsage {
                        message_count: session.messages.len(),
                        turns: tracker.turns(),
                        latest: tracker.current_turn_usage(),
                        cumulative: usage,
                        estimated_tokens: 0,
                    },
                    default_permission_mode().as_str(),
                    &status_context(Some(session_path))?,
                )),
            })
        }
        SlashCommand::Cost => {
            let usage = UsageTracker::from_session(session).cumulative_usage();
            Ok(ResumeCommandOutcome {
                session: session.clone(),
                message: Some(format_cost_report(usage)),
            })
        }
        SlashCommand::Config { section } => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(render_config_report(section.as_deref())?),
        }),
        SlashCommand::Memory => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(render_memory_report()?),
        }),
        SlashCommand::Init => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(init_claude_md()?),
        }),
        SlashCommand::Diff => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(render_diff_report()?),
        }),
        SlashCommand::Version => Ok(ResumeCommandOutcome {
            session: session.clone(),
            message: Some(render_version_report()),
        }),
        SlashCommand::Export { path } => {
            let export_path = resolve_export_path(path.as_deref(), session)?;
            fs::write(&export_path, render_export_text(session))?;
            Ok(ResumeCommandOutcome {
                session: session.clone(),
                message: Some(format!(
                    "Export\n  Result           wrote transcript\n  File             {}\n  Messages         {}",
                    export_path.display(),
                    session.messages.len(),
                )),
            })
        }
        SlashCommand::Bughunter { .. }
        | SlashCommand::Commit
        | SlashCommand::Pr { .. }
        | SlashCommand::Issue { .. }
        | SlashCommand::Ultraplan { .. }
        | SlashCommand::Teleport { .. }
        | SlashCommand::DebugToolCall
        | SlashCommand::Resume { .. }
        | SlashCommand::Model { .. }
        | SlashCommand::Reviewer { .. }
        | SlashCommand::Setup
        | SlashCommand::Plan { .. }
        | SlashCommand::Tasks { .. }
        | SlashCommand::Skills { .. }
        | SlashCommand::Permissions { .. }
        | SlashCommand::Session { .. }
        | SlashCommand::MetaOptimize { .. }
        | SlashCommand::Unknown { .. } => Err("unsupported resumed slash command".into()),
    }
}

fn run_repl(
    model: String,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut cli = LiveCli::new(model, true, allowed_tools, permission_mode)?;
    let mut editor = input::LineEditor::new("\x1b[38;5;74m❯\x1b[0m ", slash_command_completion_candidates());

    // Install Ctrl+C handler: set runtime interrupt flag instead of killing the process
    let _ = ctrlc::set_handler(|| {
        runtime::set_interrupt();
    });

    println!("{}", cli.startup_banner());

    loop {
        match editor.read_line()? {
            input::ReadOutcome::Submit(input) => {
                let trimmed = input.trim().to_string();
                if trimmed.is_empty() {
                    continue;
                }
                if matches!(trimmed.as_str(), "/exit" | "/quit") {
                    cli.persist_session()?;
                    break;
                }
                if let Some(command) = SlashCommand::parse(&trimmed) {
                    // Clear interrupt flag before command
                    runtime::clear_interrupt();
                    match cli.handle_repl_command(command) {
                        Ok(persist) => {
                            if persist {
                                let _ = cli.persist_session();
                            }
                        }
                        Err(e) => {
                            if runtime::is_interrupted() {
                                eprintln!("\n\x1b[38;5;208m● Interrupted\x1b[0m");
                            } else {
                                eprintln!("\n\x1b[38;5;203m● Error:\x1b[0m {e}");
                            }
                            runtime::clear_interrupt();
                        }
                    }
                    continue;
                }
                editor.push_history(input);
                // Visual separator before assistant response
                let term_w = crossterm::terminal::size().map(|(w, _)| w as usize).unwrap_or(80);
                let sep = "─".repeat(term_w.min(80));
                println!("\x1b[38;5;240m{sep}\x1b[0m");
                // Clear interrupt flag before starting
                runtime::clear_interrupt();
                if let Err(e) = cli.run_turn(&trimmed) {
                    if runtime::is_interrupted() {
                        eprintln!("\n\x1b[38;5;208m● Interrupted\x1b[0m");
                    } else {
                        eprintln!("\n\x1b[38;5;203m● Error:\x1b[0m {e}");
                    }
                    runtime::clear_interrupt();
                    // Don't exit REPL — let user retry or switch model
                }
            }
            input::ReadOutcome::Cancel => {}
            input::ReadOutcome::Exit => {
                cli.persist_session()?;
                break;
            }
        }
    }

    Ok(())
}

#[derive(Debug, Clone)]
struct SessionHandle {
    id: String,
    path: PathBuf,
}

#[derive(Debug, Clone)]
struct ManagedSessionSummary {
    id: String,
    path: PathBuf,
    modified_epoch_secs: u64,
    message_count: usize,
}

struct LiveCli {
    model: String,
    reviewer_model: String,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
    system_prompt: Vec<String>,
    runtime: ConversationRuntime<ExecutorClient, CliToolExecutor>,
    session: SessionHandle,
    /// Plan mode state: stores original permissions/tools before entering plan mode.
    plan_mode: Option<PlanModeState>,
}

#[derive(Debug, Clone)]
struct PlanModeState {
    previous_permission_mode: PermissionMode,
    previous_allowed_tools: Option<AllowedToolSet>,
}

impl LiveCli {
    fn new(
        model: String,
        enable_tools: bool,
        allowed_tools: Option<AllowedToolSet>,
        permission_mode: PermissionMode,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let system_prompt = build_system_prompt(Some(&model))?;
        let session = create_managed_session_handle()?;
        let runtime = build_runtime(
            Session::new(),
            model.clone(),
            system_prompt.clone(),
            enable_tools,
            true,
            allowed_tools.clone(),
            permission_mode,
        )?;
        // Determine default reviewer model
        let reviewer_model = std::env::var("ARIS_REVIEWER_MODEL")
            .ok()
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| {
                if std::env::var("GEMINI_API_KEY").is_ok() {
                    "gemini-2.5-pro".to_string()
                } else {
                    "gpt-5.4".to_string()
                }
            });
        std::env::set_var("ARIS_REVIEWER_MODEL", &reviewer_model);
        let cli = Self {
            model,
            reviewer_model,
            allowed_tools,
            permission_mode,
            system_prompt,
            runtime,
            session,
            plan_mode: None,
        };
        cli.persist_session()?;
        Ok(cli)
    }

    fn startup_banner(&self) -> String {
        let cwd = env::current_dir().map_or_else(
            |_| "<unknown>".to_string(),
            |path| path.display().to_string(),
        );

        // ── Pixel sprites (13 wide × 12 tall → 13 cols × 6 terminal lines) ──
        // Designed to match ARIS GitHub banner pixel art as closely as possible.
        // Half-block rendering: rows 0+1, 2+3, 4+5, 6+7, 8+9, 10+11 → 6 lines
        //
        // 0=transparent 1=brown-hair 2=skin 3=black 4=blue 5=khaki 6=olive 7=unused 8=dark-gray
        const CLAUDE: [[u8; 13]; 12] = [
            [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0], // hair top
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0], // hair wider
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // face
            [0, 0, 2, 2, 3, 2, 2, 2, 3, 2, 2, 0, 0], // eyes
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // face
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // chin
            [0, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 2, 0], // arms + shirt top
            [0, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 2, 0], // arms + shirt
            [0, 0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 0, 0], // shirt body
            [0, 0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 0, 0], // shirt lower
            [0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 0], // legs
            [0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 0], // shoes
        ];
        const GPT: [[u8; 13]; 12] = [
            [0, 0, 8, 8, 8, 8, 8, 8, 8, 8, 8, 0, 0], // hat
            [0, 0, 8, 8, 8, 8, 8, 8, 8, 8, 8, 0, 0], // hat
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // face
            [0, 0, 2, 3, 3, 2, 2, 2, 3, 3, 2, 0, 0], // sunglasses: 2px + gap + 2px
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // face below
            [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0], // chin
            [0, 2, 6, 6, 6, 6, 6, 6, 6, 6, 6, 2, 0], // arms + shirt
            [0, 2, 6, 6, 6, 6, 6, 6, 6, 6, 6, 2, 0], // arms + shirt
            [0, 0, 6, 6, 6, 6, 6, 6, 6, 6, 6, 0, 0], // shirt body
            [0, 0, 6, 6, 6, 6, 6, 6, 6, 6, 6, 0, 0], // shirt lower
            [0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 0], // legs
            [0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 0], // shoes
        ];
        // ANSI 256-color per index (None = terminal background)
        const COLOR: [Option<u8>; 9] = [
            None,      // 0 transparent
            Some(137), // 1 warm brown hair (Claude) - #af875f
            Some(223), // 2 skin/peach - #ffd7af
            Some(233), // 3 near-black (eyes, glasses, shoes) - #121212
            Some(74),  // 4 medium blue shirt (Claude) - #5fafd7
            Some(101), // 5 khaki pants - #87875f
            Some(65),  // 6 olive shirt (GPT) - #5f875f
            Some(217), // 7 mouth - #ffafaf (light pink)
            Some(240), // 8 dark gray hat (GPT, visible on dark bg) - #585858
        ];

        let render = |sprite: &[[u8; 13]; 12]| -> Vec<String> {
            (0..6usize)
                .map(|line| {
                    let r0 = &sprite[line * 2];
                    let r1 = &sprite[line * 2 + 1];
                    let mut s = String::new();
                    for col in 0..13usize {
                        let top = COLOR[r0[col] as usize];
                        let bot = COLOR[r1[col] as usize];
                        match (top, bot) {
                            (None, None) => s.push(' '),
                            (Some(t), None) => s.push_str(&format!("\x1b[38;5;{t}m▀\x1b[0m")),
                            (None, Some(b)) => s.push_str(&format!("\x1b[38;5;{b}m▄\x1b[0m")),
                            (Some(t), Some(b)) if t == b => {
                                s.push_str(&format!("\x1b[48;5;{t}m \x1b[0m"))
                            }
                            (Some(t), Some(b)) => {
                                s.push_str(&format!("\x1b[38;5;{t};48;5;{b}m▀\x1b[0m"))
                            }
                        }
                    }
                    s
                })
                .collect()
        };

        let left = render(&CLAUDE);
        let right = render(&GPT);

        // Center text: 6 lines, ALL exactly 34 visible chars
        // 0: 2sp + 30 dashes + 2sp                            = 34
        // 1: 7sp + "A     R     I     S" (19) + 8sp             = 34
        // 2: 6sp + "Auto Research in Sleep" (22) + 6sp        = 34
        // 3: 4sp + "adversarial | multi-agent" (25) + 5sp     = 34
        // 4: 6sp + "Claude x GPT-5.4 xhigh" (22) + 6sp       = 34
        // 5: same as 0                                        = 34
        let center = [
            "\x1b[2m  ──────────────────────────────  \x1b[0m",
            "\x1b[1;38;5;45m       A     R     I     S        \x1b[0m",
            "\x1b[38;5;45m      Auto Research in Sleep      \x1b[0m",
            "\x1b[2m    adversarial | multi-agent     \x1b[0m",
            "      \x1b[38;5;45mClaude\x1b[0m x \x1b[38;5;71mGPT-5.4 xhigh\x1b[0m      ",
            "\x1b[2m  ──────────────────────────────  \x1b[0m",
        ];

        // Build sprite lines
        let mut sprite_lines: Vec<String> = Vec::new();
        for i in 0..6 {
            let mut line = String::new();
            line.push_str(&left[i]);
            line.push_str("  ");
            line.push_str(center[i]);
            line.push_str("  ");
            line.push_str(&right[i]);
            sprite_lines.push(line);
        }

        let executor_label = if openai_executor::resolve_openai_executor_config().is_some() {
            let base = std::env::var("EXECUTOR_BASE_URL").unwrap_or_default();
            if base.contains("deepseek") {
                "DeepSeek"
            } else if base.contains("bigmodel") {
                "GLM"
            } else if base.contains("minimax") {
                "MiniMax"
            } else if base.contains("moonshot") {
                "Moonshot"
            } else if base.contains("dashscope") || base.contains("qwen") {
                "Qwen"
            } else if base.contains("generativelanguage.googleapis") {
                "Gemini"
            } else {
                "OpenAI"
            }
        } else {
            "Anthropic"
        };

        let info_lines = [
            format!("\x1b[2mExecutor\x1b[0m     {executor_label} · {}", self.model),
            format!("\x1b[2mReviewer\x1b[0m     {}", self.reviewer_model),
            format!("\x1b[2mPermissions\x1b[0m  {}", self.permission_mode.as_str()),
            format!("\x1b[2mDirectory\x1b[0m    {cwd}"),
            format!("\x1b[2mSession\x1b[0m      {}", self.session.id),
        ];

        // Box drawing
        let term_w = crossterm::terminal::size().map(|(w, _)| w as usize).unwrap_or(80);
        let box_w = term_w.min(76);
        let hr = "─".repeat(box_w.saturating_sub(2));
        let dim = "\x1b[38;5;240m";
        let reset = "\x1b[0m";

        let mut banner = String::new();
        // Top border with title
        banner.push_str(&format!("{dim}╭─ {reset}ARIS-Code v{VERSION}{dim} {hr}{reset}\n", hr = "─".repeat(box_w.saturating_sub(18 + VERSION.len()))));
        // Sprite lines
        for line in &sprite_lines {
            banner.push_str(&format!("{dim}│{reset} {line}\n"));
        }
        // Separator
        banner.push_str(&format!("{dim}├{hr}┤{reset}\n"));
        // Info lines
        for line in &info_lines {
            banner.push_str(&format!("{dim}│{reset}  {line}\n"));
        }
        // Bottom border
        banner.push_str(&format!("{dim}╰{hr}╯{reset}\n"));
        // Help hint (outside box)
        banner.push_str(&format!(
            "\n  Type \x1b[1m/help\x1b[0m for commands · \x1b[2m/model\x1b[0m or \x1b[2m/reviewer\x1b[0m to switch"
        ));
        banner
    }

    fn run_turn(&mut self, input: &str) -> Result<(), Box<dyn std::error::Error>> {
        let mut spinner = Spinner::new();
        let mut stdout = io::stdout();
        spinner.tick(
            "\x1b[38;5;74m●\x1b[0m \x1b[2mThinking...\x1b[0m",
            TerminalRenderer::new().color_theme(),
            &mut stdout,
        )?;
        let mut permission_prompter = CliPermissionPrompter::new(self.permission_mode);
        let result = self.runtime.run_turn(input, Some(&mut permission_prompter));
        match result {
            Ok(summary) => {
                spinner.finish(
                    "\x1b[38;5;74m●\x1b[0m \x1b[2mDone\x1b[0m",
                    TerminalRenderer::new().color_theme(),
                    &mut stdout,
                )?;
                println!();
                if let Some(event) = summary.auto_compaction {
                    println!(
                        "{}",
                        format_auto_compaction_notice(event.removed_message_count)
                    );
                }
                self.persist_session()?;
                Ok(())
            }
            Err(error) => {
                spinner.fail(
                    "\x1b[38;5;203m●\x1b[0m \x1b[1;31mRequest failed\x1b[0m",
                    TerminalRenderer::new().color_theme(),
                    &mut stdout,
                )?;
                Err(Box::new(error))
            }
        }
    }

    fn run_turn_with_output(
        &mut self,
        input: &str,
        output_format: CliOutputFormat,
    ) -> Result<(), Box<dyn std::error::Error>> {
        match output_format {
            CliOutputFormat::Text => self.run_turn(input),
            CliOutputFormat::Json => self.run_prompt_json(input),
        }
    }

    fn run_prompt_json(&mut self, input: &str) -> Result<(), Box<dyn std::error::Error>> {
        let session = self.runtime.session().clone();
        let mut runtime = build_runtime(
            session,
            self.model.clone(),
            self.system_prompt.clone(),
            true,
            false,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        let mut permission_prompter = CliPermissionPrompter::new(self.permission_mode);
        let summary = runtime.run_turn(input, Some(&mut permission_prompter))?;
        self.runtime = runtime;
        self.persist_session()?;
        println!(
            "{}",
            json!({
                "message": final_assistant_text(&summary),
                "model": self.model,
                "iterations": summary.iterations,
                "auto_compaction": summary.auto_compaction.map(|event| json!({
                    "removed_messages": event.removed_message_count,
                    "notice": format_auto_compaction_notice(event.removed_message_count),
                })),
                "tool_uses": collect_tool_uses(&summary),
                "tool_results": collect_tool_results(&summary),
                "usage": {
                    "input_tokens": summary.usage.input_tokens,
                    "output_tokens": summary.usage.output_tokens,
                    "cache_creation_input_tokens": summary.usage.cache_creation_input_tokens,
                    "cache_read_input_tokens": summary.usage.cache_read_input_tokens,
                }
            })
        );
        Ok(())
    }

    fn handle_repl_command(
        &mut self,
        command: SlashCommand,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        Ok(match command {
            SlashCommand::Help => {
                println!("{}", render_repl_help());
                false
            }
            SlashCommand::Status => {
                self.print_status();
                false
            }
            SlashCommand::Bughunter { scope } => {
                self.run_bughunter(scope.as_deref())?;
                false
            }
            SlashCommand::Commit => {
                self.run_commit()?;
                true
            }
            SlashCommand::Pr { context } => {
                self.run_pr(context.as_deref())?;
                false
            }
            SlashCommand::Issue { context } => {
                self.run_issue(context.as_deref())?;
                false
            }
            SlashCommand::Ultraplan { task } => {
                self.run_ultraplan(task.as_deref())?;
                false
            }
            SlashCommand::Teleport { target } => {
                self.run_teleport(target.as_deref())?;
                false
            }
            SlashCommand::DebugToolCall => {
                self.run_debug_tool_call()?;
                false
            }
            SlashCommand::Compact => {
                self.compact()?;
                false
            }
            SlashCommand::Model { model } => self.set_model(model)?,
            SlashCommand::Reviewer { model } => self.set_reviewer(model)?,
            SlashCommand::Setup => self.run_inline_setup()?,
            SlashCommand::Plan { task } => {
                self.handle_plan_mode(task.as_deref())?
            }
            SlashCommand::Tasks { action } => {
                Self::handle_tasks(action.as_deref())?;
                false
            }
            SlashCommand::Skills { action, target } => {
                Self::handle_skills(action.as_deref(), target.as_deref())?;
                false
            }
            SlashCommand::Permissions { mode } => self.set_permissions(mode)?,
            SlashCommand::Clear { confirm } => self.clear_session(confirm)?,
            SlashCommand::Cost => {
                self.print_cost();
                false
            }
            SlashCommand::Resume { session_path } => self.resume_session(session_path)?,
            SlashCommand::Config { section } => {
                Self::print_config(section.as_deref())?;
                false
            }
            SlashCommand::Memory => {
                Self::print_memory()?;
                false
            }
            SlashCommand::Init => {
                run_init()?;
                false
            }
            SlashCommand::Diff => {
                Self::print_diff()?;
                false
            }
            SlashCommand::Version => {
                Self::print_version();
                false
            }
            SlashCommand::Export { path } => {
                self.export_session(path.as_deref())?;
                false
            }
            SlashCommand::Session { action, target } => {
                self.handle_session_command(action.as_deref(), target.as_deref())?
            }
            SlashCommand::MetaOptimize { action, target } => {
                self.handle_meta_optimize(action.as_deref(), target.as_deref())?;
                false
            }
            SlashCommand::Unknown { ref name, ref args } => {
                // Try to resolve as a skill invocation
                if is_known_skill(name) {
                    let args_hint = args.as_deref().unwrap_or("");
                    let skill_prompt = if args_hint.is_empty() {
                        format!(
                            "Use the Skill tool to invoke the skill named \"{name}\". Follow the skill instructions precisely."
                        )
                    } else {
                        format!(
                            "Use the Skill tool to invoke the skill named \"{name}\" with arguments: {args_hint}. Follow the skill instructions precisely."
                        )
                    };
                    self.run_turn(&skill_prompt)?;
                    false
                } else {
                    eprintln!("unknown slash command: /{name}");
                    false
                }
            }
        })
    }

    fn persist_session(&self) -> Result<(), Box<dyn std::error::Error>> {
        self.runtime.session().save_to_path(&self.session.path)?;
        Ok(())
    }

    fn print_status(&self) {
        let cumulative = self.runtime.usage().cumulative_usage();
        let latest = self.runtime.usage().current_turn_usage();
        println!(
            "{}",
            format_status_report(
                &self.model,
                StatusUsage {
                    message_count: self.runtime.session().messages.len(),
                    turns: self.runtime.usage().turns(),
                    latest,
                    cumulative,
                    estimated_tokens: self.runtime.estimated_tokens(),
                },
                self.permission_mode.as_str(),
                &status_context(Some(&self.session.path)).expect("status context should load"),
            )
        );
    }

    fn set_model(&mut self, model: Option<String>) -> Result<bool, Box<dyn std::error::Error>> {
        let model = match model {
            Some(m) => resolve_model_alias(&m).to_string(),
            None => {
                // Show interactive menu
                let is_openai = openai_executor::resolve_openai_executor_config().is_some();
                let items: Vec<input::SelectItem> = if is_openai {
                    // OpenAI-compat mode: show common models
                    vec![
                        ("gpt-5.4", "OpenAI · Best intelligence at scale"),
                        ("gpt-5.4-mini", "OpenAI · Strong mini model"),
                        ("gpt-5.4-nano", "OpenAI · Cheapest, high-volume"),
                        ("gemini-2.5-pro", "Google · Most capable Gemini"),
                        ("gemini-2.5-flash", "Google · Fast Gemini"),
                        ("GLM-5", "Zhipu · GLM 5 latest"),
                        ("MiniMax-M2.7", "MiniMax · M2.7 latest"),
                        ("kimi-k2.5", "Kimi · K2.5 reasoning"),
                    ]
                    .into_iter()
                    .map(|(name, desc)| input::SelectItem {
                        label: name.to_string(),
                        description: desc.to_string(),
                        is_current: self.model == name,
                    })
                    .collect()
                } else {
                    // Anthropic mode
                    vec![
                        ("claude-opus-4-6", "Opus 4.6 · Most capable for complex work"),
                        ("claude-sonnet-4-6", "Sonnet 4.6 · Best for everyday tasks"),
                        ("claude-haiku-4-5-20251001", "Haiku 4.5 · Fastest for quick answers"),
                    ]
                    .into_iter()
                    .map(|(name, desc)| input::SelectItem {
                        label: name.to_string(),
                        description: desc.to_string(),
                        is_current: self.model == name,
                    })
                    .collect()
                };

                match input::select_menu("Select executor model", "Switch the model used for the main conversation.", &items)? {
                    Some(idx) => items[idx].label.clone(),
                    None => return Ok(false),
                }
            }
        };

        if model == self.model {
            println!(
                "{}",
                format_model_report(
                    &self.model,
                    self.runtime.session().messages.len(),
                    self.runtime.usage().turns(),
                )
            );
            return Ok(false);
        }

        let previous = self.model.clone();
        // Rebuild system prompt with new model identity
        let new_system_prompt = build_system_prompt(Some(&model))?;
        let session = self.runtime.session().clone();
        let message_count = session.messages.len();
        self.runtime = build_runtime(
            session,
            model.clone(),
            new_system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        self.system_prompt = new_system_prompt;
        self.model.clone_from(&model);
        println!(
            "{}",
            format_model_switch_report(&previous, &model, message_count)
        );
        Ok(true)
    }

    fn set_reviewer(&mut self, model: Option<String>) -> Result<bool, Box<dyn std::error::Error>> {
        let model = match model {
            Some(m) => m,
            None => {
                let has_gemini = std::env::var("GEMINI_API_KEY").is_ok();
                let has_openai = std::env::var("OPENAI_API_KEY").is_ok();

                let mut items: Vec<input::SelectItem> = Vec::new();
                if has_gemini {
                    for (name, desc) in [
                        ("gemini-2.5-pro", "Google · Most capable, deep reasoning"),
                        ("gemini-2.5-flash", "Google · Fast and efficient"),
                        ("gemini-2.0-flash-001", "Google · Previous gen fast model"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }
                // GLM models
                if std::env::var("GLM_API_KEY").is_ok() {
                    for (name, desc) in [
                        ("GLM-5", "Zhipu · Most capable"),
                        ("GLM-5-Turbo", "Zhipu · Fast"),
                        ("GLM-4.7", "Zhipu · Previous gen"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }
                // MiniMax models
                if std::env::var("MINIMAX_API_KEY").is_ok() {
                    for (name, desc) in [
                        ("MiniMax-M2.7", "MiniMax · Latest, recursive self-improvement"),
                        ("MiniMax-M2.7-highspeed", "MiniMax · Fast inference"),
                        ("MiniMax-M2.5", "MiniMax · Code generation"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }
                // Kimi models
                if std::env::var("KIMI_API_KEY").is_ok() {
                    for (name, desc) in [
                        ("kimi-k2.5", "Kimi · K2.5 reasoning"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }
                if has_openai {
                    for (name, desc) in [
                        ("gpt-5.4", "OpenAI · Best intelligence for reviews"),
                        ("gpt-5.4-mini", "OpenAI · Strong and affordable"),
                        ("gpt-5.4-nano", "OpenAI · Cheapest, high-volume"),
                        ("gpt-4o", "OpenAI · Previous gen, stable"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }

                if items.is_empty() {
                    println!("No reviewer API key found. Set GEMINI_API_KEY or OPENAI_API_KEY.");
                    return Ok(false);
                }

                match input::select_menu("Select reviewer model", "Switch the model used by LlmReview for external reviews.", &items)? {
                    Some(idx) => items[idx].label.clone(),
                    None => return Ok(false),
                }
            }
        };

        let previous = self.reviewer_model.clone();
        self.reviewer_model.clone_from(&model);

        // Update the REVIEWER_MODEL env var so LlmReview picks it up
        std::env::set_var("ARIS_REVIEWER_MODEL", &model);

        println!(
            "\x1b[1mReviewer model\x1b[0m\n  Previous         {previous}\n  Current          \x1b[1;32m{model}\x1b[0m"
        );
        Ok(false)
    }

    fn run_inline_setup(&mut self) -> Result<bool, Box<dyn std::error::Error>> {
        let new_config = config::run_interactive_setup()?;
        new_config.force_apply_to_env();

        // Update model if config changed it
        if let Some(new_model) = new_config.executor_model() {
            let new_model = resolve_model_alias(new_model).to_string();
            if new_model != self.model {
                let previous = self.model.clone();
                // Rebuild system prompt with new model identity
                let new_system_prompt = build_system_prompt(Some(&new_model))?;
                let session = self.runtime.session().clone();
                self.runtime = build_runtime(
                    session,
                    new_model.clone(),
                    new_system_prompt.clone(),
                    true,
                    true,
                    self.allowed_tools.clone(),
                    self.permission_mode,
                )?;
                self.system_prompt = new_system_prompt;
                self.model.clone_from(&new_model);
                println!("  Executor model: {previous} → \x1b[1;32m{new_model}\x1b[0m");
            }
        }

        // Update reviewer model
        if let Some(new_reviewer) = &new_config.reviewer_model {
            self.reviewer_model.clone_from(new_reviewer);
        }

        Ok(true)
    }

    fn handle_tasks(action: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let tasks_path = aris_tasks_path();
        match action {
            Some("clear") => {
                if tasks_path.exists() {
                    fs::remove_file(&tasks_path)?;
                    println!("\x1b[1;32m✓\x1b[0m Tasks cleared.");
                } else {
                    println!("No tasks file to clear.");
                }
            }
            _ => {
                if tasks_path.exists() {
                    let content = fs::read_to_string(&tasks_path)?;
                    if let Ok(todos) = serde_json::from_str::<Vec<serde_json::Value>>(&content) {
                        if todos.is_empty() {
                            println!("\x1b[2mNo tasks yet. The model manages tasks automatically via TodoWrite.\x1b[0m");
                        } else {
                            println!("\x1b[1mTasks\x1b[0m\n");
                            for todo in &todos {
                                let status = todo.get("status").and_then(|s| s.as_str()).unwrap_or("pending");
                                let content_text = todo.get("content").and_then(|c| c.as_str()).unwrap_or("?");
                                let icon = match status {
                                    "completed" => "\x1b[1;32m✓\x1b[0m",
                                    "in_progress" => "\x1b[1;33m●\x1b[0m",
                                    _ => "\x1b[2m○\x1b[0m",
                                };
                                println!("  {icon} {content_text}");
                            }
                            println!();
                        }
                    } else {
                        // Fallback: show raw content
                        println!("{content}");
                    }
                } else {
                    println!("\x1b[2mNo tasks yet. The model manages tasks automatically via TodoWrite.\x1b[0m");
                }
            }
        }
        Ok(())
    }

    fn handle_skills(
        action: Option<&str>,
        target: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        match action {
            None | Some("list") => {
                let skills = discover_all_skills();
                if skills.is_empty() {
                    println!("No skills found.");
                    return Ok(());
                }
                let max_name = skills.iter().map(|(n, _, _)| n.len()).max().unwrap_or(10);
                let name_col = max_name.max(15) + 2;
                println!("\x1b[1mAvailable skills\x1b[0m\n");
                for (name, desc, source) in &skills {
                    let tag = match *source {
                        "aris" => "\x1b[1;32m[aris]\x1b[0m  ",
                        "user" => "\x1b[1;34m[user]\x1b[0m  ",
                        _ => "\x1b[2m[built-in]\x1b[0m",
                    };
                    let d = if desc.is_empty() { "" } else { desc.as_str() };
                    println!("  {tag} {name:<width$} \x1b[2m{d}\x1b[0m", width = name_col);
                }
                println!(
                    "\n\x1b[2mSkill dirs: {} > {} > bundled\x1b[0m",
                    dirs_aris_skills().display(),
                    dirs_claude_skills().display(),
                );
                println!("\x1b[2mUse /skills show <name> to view · /skills export <name> to customize\x1b[0m");
            }
            Some("show") => {
                let Some(name) = target else {
                    println!("Usage: /skills show <name>");
                    return Ok(());
                };
                if let Some(content) = find_skill_content(name) {
                    println!("\x1b[1m/{name}\x1b[0m\n");
                    println!("{content}");
                } else {
                    println!("Skill '{name}' not found.");
                }
            }
            Some("export") => {
                let Some(name) = target else {
                    println!("Usage: /skills export <name>");
                    return Ok(());
                };
                let Some(content) = find_skill_content(name) else {
                    println!("Skill '{name}' not found.");
                    return Ok(());
                };
                let target_dir = dirs_aris_skills().join(name);
                let target_file = target_dir.join("SKILL.md");
                if target_file.exists() {
                    println!(
                        "Already exists: {}\n\x1b[2mEdit it directly to customize.\x1b[0m",
                        target_file.display()
                    );
                    return Ok(());
                }
                fs::create_dir_all(&target_dir)?;
                fs::write(&target_file, &content)?;
                println!(
                    "\x1b[1;32m✓\x1b[0m Exported to {}\n\x1b[2mEdit this file to customize the skill.\x1b[0m",
                    target_file.display()
                );
            }
            Some(other) => {
                println!("Unknown action '{other}'. Use: /skills [list|show <name>|export <name>]");
            }
        }
        Ok(())
    }

    fn set_permissions(
        &mut self,
        mode: Option<String>,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        let mode = match mode {
            Some(m) => m,
            None => {
                let items: Vec<input::SelectItem> = vec![
                    ("read-only", "Safe · Read files only, no writes or commands"),
                    ("workspace-write", "Normal · Read + write files in workspace"),
                    ("danger-full-access", "Full · All tools, no restrictions"),
                ]
                .into_iter()
                .map(|(name, desc)| input::SelectItem {
                    label: name.to_string(),
                    description: desc.to_string(),
                    is_current: self.permission_mode.as_str() == name,
                })
                .collect();

                match input::select_menu(
                    "Select permission mode",
                    "Controls which tools require approval.",
                    &items,
                )? {
                    Some(idx) => items[idx].label.clone(),
                    None => return Ok(false),
                }
            }
        };

        let normalized = normalize_permission_mode(&mode).ok_or_else(|| {
            format!(
                "unsupported permission mode '{mode}'. Use read-only, workspace-write, or danger-full-access."
            )
        })?;

        if normalized == self.permission_mode.as_str() {
            println!("{}", format_permissions_report(normalized));
            return Ok(false);
        }

        let previous = self.permission_mode.as_str().to_string();
        let session = self.runtime.session().clone();
        self.permission_mode = permission_mode_from_label(normalized);
        self.runtime = build_runtime(
            session,
            self.model.clone(),
            self.system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        println!(
            "{}",
            format_permissions_switch_report(&previous, normalized)
        );
        Ok(true)
    }

    fn clear_session(&mut self, confirm: bool) -> Result<bool, Box<dyn std::error::Error>> {
        if !confirm {
            println!(
                "clear: confirmation required; run /clear --confirm to start a fresh session."
            );
            return Ok(false);
        }

        self.session = create_managed_session_handle()?;
        self.runtime = build_runtime(
            Session::new(),
            self.model.clone(),
            self.system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        println!(
            "Session cleared\n  Mode             fresh session\n  Preserved model  {}\n  Permission mode  {}\n  Session          {}",
            self.model,
            self.permission_mode.as_str(),
            self.session.id,
        );
        Ok(true)
    }

    fn print_cost(&self) {
        let cumulative = self.runtime.usage().cumulative_usage();
        println!("{}", format_cost_report(cumulative));
    }

    fn resume_session(
        &mut self,
        session_path: Option<String>,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        let Some(session_ref) = session_path else {
            println!("Usage: /resume <session-path>");
            return Ok(false);
        };

        let handle = resolve_session_reference(&session_ref)?;
        let session = Session::load_from_path(&handle.path)?;
        let message_count = session.messages.len();
        self.runtime = build_runtime(
            session,
            self.model.clone(),
            self.system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        self.session = handle;
        println!(
            "{}",
            format_resume_report(
                &self.session.path.display().to_string(),
                message_count,
                self.runtime.usage().turns(),
            )
        );
        Ok(true)
    }

    fn print_config(section: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        println!("{}", render_config_report(section)?);
        Ok(())
    }

    fn print_memory() -> Result<(), Box<dyn std::error::Error>> {
        println!("{}", render_memory_report()?);
        Ok(())
    }

    fn print_diff() -> Result<(), Box<dyn std::error::Error>> {
        println!("{}", render_diff_report()?);
        Ok(())
    }

    fn print_version() {
        println!("{}", render_version_report());
    }

    fn export_session(
        &self,
        requested_path: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let export_path = resolve_export_path(requested_path, self.runtime.session())?;
        fs::write(&export_path, render_export_text(self.runtime.session()))?;
        println!(
            "Export\n  Result           wrote transcript\n  File             {}\n  Messages         {}",
            export_path.display(),
            self.runtime.session().messages.len(),
        );
        Ok(())
    }

    fn handle_session_command(
        &mut self,
        action: Option<&str>,
        target: Option<&str>,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        match action {
            None | Some("list") => {
                println!("{}", render_session_list(&self.session.id)?);
                Ok(false)
            }
            Some("switch") => {
                let Some(target) = target else {
                    println!("Usage: /session switch <session-id>");
                    return Ok(false);
                };
                let handle = resolve_session_reference(target)?;
                let session = Session::load_from_path(&handle.path)?;
                let message_count = session.messages.len();
                self.runtime = build_runtime(
                    session,
                    self.model.clone(),
                    self.system_prompt.clone(),
                    true,
                    true,
                    self.allowed_tools.clone(),
                    self.permission_mode,
                )?;
                self.session = handle;
                println!(
                    "Session switched\n  Active session   {}\n  File             {}\n  Messages         {}",
                    self.session.id,
                    self.session.path.display(),
                    message_count,
                );
                Ok(true)
            }
            Some(other) => {
                println!("Unknown /session action '{other}'. Use /session list or /session switch <session-id>.");
                Ok(false)
            }
        }
    }

    fn handle_plan_mode(
        &mut self,
        task: Option<&str>,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        match task.map(str::trim) {
            // /plan execute — exit plan mode and execute
            Some(arg) if arg.starts_with("execute") => {
                if self.plan_mode.is_none() {
                    println!("Not in plan mode. Use /plan <task> to enter plan mode first.");
                    return Ok(false);
                }
                let state = self.plan_mode.as_ref().expect("plan_mode checked above").clone();
                let session = self.runtime.session().clone();
                let new_runtime = match build_runtime(
                    session,
                    self.model.clone(),
                    self.system_prompt.clone(),
                    true,
                    true,
                    state.previous_allowed_tools.clone(),
                    state.previous_permission_mode,
                ) {
                    Ok(rt) => rt,
                    Err(e) => {
                        eprintln!("\x1b[1;31mFailed to exit plan mode:\x1b[0m {e}");
                        return Ok(false);
                    }
                };
                // Commit only on success
                self.runtime = new_runtime;
                self.permission_mode = state.previous_permission_mode;
                self.allowed_tools = state.previous_allowed_tools;
                self.plan_mode = None;
                println!(
                    "\x1b[1;32m✓\x1b[0m Plan mode ended. Permissions restored to \x1b[1m{}\x1b[0m.",
                    self.permission_mode.as_str()
                );
                let extra = arg.strip_prefix("execute").unwrap_or("").trim();
                let exec_prompt = if extra.is_empty() {
                    "Execute the plan you proposed. Proceed step by step.".to_string()
                } else {
                    format!("Execute the plan you proposed. Additional instructions: {extra}")
                };
                self.run_turn(&exec_prompt)?;
                Ok(true)
            }
            // /plan exit — exit plan mode without executing
            Some("exit") => {
                if let Some(state) = self.plan_mode.as_ref().cloned() {
                    let session = self.runtime.session().clone();
                    let new_runtime = match build_runtime(
                        session,
                        self.model.clone(),
                        self.system_prompt.clone(),
                        true,
                        true,
                        state.previous_allowed_tools.clone(),
                        state.previous_permission_mode,
                    ) {
                        Ok(rt) => rt,
                        Err(e) => {
                            eprintln!("\x1b[1;31mFailed to exit plan mode:\x1b[0m {e}");
                            return Ok(false);
                        }
                    };
                    self.runtime = new_runtime;
                    self.permission_mode = state.previous_permission_mode;
                    self.allowed_tools = state.previous_allowed_tools;
                    self.plan_mode = None;
                    println!(
                        "\x1b[1;32m✓\x1b[0m Plan mode exited. Permissions restored to \x1b[1m{}\x1b[0m.",
                        self.permission_mode.as_str()
                    );
                } else {
                    println!("Not in plan mode.");
                }
                Ok(false)
            }
            // /plan <task> — enter plan mode
            _ => {
                if self.plan_mode.is_some() {
                    println!("Already in plan mode. Use /plan execute or /plan exit.");
                    return Ok(false);
                }

                // Save previous state for rollback
                let prev_perm = self.permission_mode;
                let prev_tools = self.allowed_tools.clone();

                // Prepare plan-mode tools
                let plan_tools: AllowedToolSet = [
                    "read_file", "glob_search", "grep_search",
                    "WebFetch", "WebSearch", "ToolSearch", "Skill",
                ].iter().map(|s| s.to_string()).collect();

                // Try rebuilding runtime FIRST, then commit state only on success
                let session = self.runtime.session().clone();
                let new_runtime = match build_runtime(
                    session,
                    self.model.clone(),
                    self.system_prompt.clone(),
                    true,
                    true,
                    Some(plan_tools.clone()),
                    PermissionMode::ReadOnly,
                ) {
                    Ok(rt) => rt,
                    Err(e) => {
                        eprintln!("\x1b[1;31mFailed to enter plan mode:\x1b[0m {e}");
                        return Ok(false);
                    }
                };

                // Commit state only after runtime built successfully
                self.runtime = new_runtime;
                self.allowed_tools = Some(plan_tools);
                self.permission_mode = PermissionMode::ReadOnly;
                self.plan_mode = Some(PlanModeState {
                    previous_permission_mode: prev_perm,
                    previous_allowed_tools: prev_tools,
                });

                println!(
                    "\x1b[1;34m●\x1b[0m \x1b[1mPlan mode\x1b[0m — read-only tools only. \
                     Use \x1b[1m/plan execute\x1b[0m to run or \x1b[1m/plan exit\x1b[0m to cancel."
                );

                let task_desc = task.unwrap_or("the user's request");
                let plan_prompt = format!(
                    "You are in PLAN MODE. You can ONLY read and search — no writing, editing, or commands.\n\n\
                     Analyze the codebase and create a detailed step-by-step plan for: {task_desc}\n\n\
                     For each step:\n\
                     1. What file(s) to change and why\n\
                     2. The specific changes needed\n\
                     3. Potential risks or edge cases\n\n\
                     Do NOT attempt to execute anything. Only produce the plan."
                );
                self.run_turn(&plan_prompt)?;
                Ok(true)
            }
        }
    }

    fn handle_meta_optimize(
        &mut self,
        action: Option<&str>,
        target: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        match action {
            Some("apply") => {
                let Some(id_str) = target else {
                    println!("Usage: /meta-optimize apply <proposal-number>");
                    return Ok(());
                };
                let id: usize = id_str.parse().map_err(|_| {
                    format!("Invalid proposal number: {id_str}")
                })?;
                match meta_optimize::apply_proposal(id) {
                    Ok(msg) => println!("{msg}"),
                    Err(e) => eprintln!("\x1b[1;31mError\x1b[0m: {e}"),
                }
            }
            Some("status") | None => {
                match meta_optimize::status_report() {
                    Ok(report) => println!("{report}"),
                    Err(e) => eprintln!("\x1b[1;31mError\x1b[0m: {e}"),
                }
            }
            Some(other) => {
                // Anything else (e.g., a skill name or "all") → run as skill invocation
                let args = if let Some(t) = target {
                    format!("{other} {t}")
                } else {
                    other.to_string()
                };
                let prompt = format!(
                    "Use the Skill tool to invoke the skill named \"meta-optimize\" with arguments: {args}. Follow the skill instructions precisely."
                );
                self.run_turn(&prompt)?;
            }
        }
        Ok(())
    }

    fn compact(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let result = self.runtime.compact(CompactionConfig::default());
        let removed = result.removed_message_count;
        let kept = result.compacted_session.messages.len();
        let skipped = removed == 0;
        self.runtime = build_runtime(
            result.compacted_session,
            self.model.clone(),
            self.system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        self.persist_session()?;
        println!("{}", format_compact_report(removed, kept, skipped));
        Ok(())
    }

    fn run_internal_prompt_text(
        &self,
        prompt: &str,
        enable_tools: bool,
    ) -> Result<String, Box<dyn std::error::Error>> {
        let session = self.runtime.session().clone();
        let mut runtime = build_runtime(
            session,
            self.model.clone(),
            self.system_prompt.clone(),
            enable_tools,
            false,
            self.allowed_tools.clone(),
            self.permission_mode,
        )?;
        let mut permission_prompter = CliPermissionPrompter::new(self.permission_mode);
        let summary = runtime.run_turn(prompt, Some(&mut permission_prompter))?;
        Ok(final_assistant_text(&summary).trim().to_string())
    }

    fn run_bughunter(&self, scope: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let scope = scope.unwrap_or("the current repository");
        let prompt = format!(
            "You are /bughunter. Inspect {scope} and identify the most likely bugs or correctness issues. Prioritize concrete findings with file paths, severity, and suggested fixes. Use tools if needed."
        );
        println!("{}", self.run_internal_prompt_text(&prompt, true)?);
        Ok(())
    }

    fn run_ultraplan(&self, task: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let task = task.unwrap_or("the current repo work");
        let prompt = format!(
            "You are /ultraplan. Produce a deep multi-step execution plan for {task}. Include goals, risks, implementation sequence, verification steps, and rollback considerations. Use tools if needed."
        );
        println!("{}", self.run_internal_prompt_text(&prompt, true)?);
        Ok(())
    }

    fn run_teleport(&self, target: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let Some(target) = target.map(str::trim).filter(|value| !value.is_empty()) else {
            println!("Usage: /teleport <symbol-or-path>");
            return Ok(());
        };

        println!("{}", render_teleport_report(target)?);
        Ok(())
    }

    fn run_debug_tool_call(&self) -> Result<(), Box<dyn std::error::Error>> {
        println!("{}", render_last_tool_debug_report(self.runtime.session())?);
        Ok(())
    }

    fn run_commit(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let status = git_output(&["status", "--short"])?;
        if status.trim().is_empty() {
            println!("Commit\n  Result           skipped\n  Reason           no workspace changes");
            return Ok(());
        }

        git_status_ok(&["add", "-A"])?;
        let staged_stat = git_output(&["diff", "--cached", "--stat"])?;
        let prompt = format!(
            "Generate a git commit message in plain text Lore format only. Base it on this staged diff summary:\n\n{}\n\nRecent conversation context:\n{}",
            truncate_for_prompt(&staged_stat, 8_000),
            recent_user_context(self.runtime.session(), 6)
        );
        let message = sanitize_generated_message(&self.run_internal_prompt_text(&prompt, false)?);
        if message.trim().is_empty() {
            return Err("generated commit message was empty".into());
        }

        let path = write_temp_text_file("aris-commit-message.txt", &message)?;
        let output = Command::new("git")
            .args(["commit", "--file"])
            .arg(&path)
            .current_dir(env::current_dir()?)
            .output()?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(format!("git commit failed: {stderr}").into());
        }

        println!(
            "Commit\n  Result           created\n  Message file     {}\n\n{}",
            path.display(),
            message.trim()
        );
        Ok(())
    }

    fn run_pr(&self, context: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let staged = git_output(&["diff", "--stat"])?;
        let prompt = format!(
            "Generate a pull request title and body from this conversation and diff summary. Output plain text in this format exactly:\nTITLE: <title>\nBODY:\n<body markdown>\n\nContext hint: {}\n\nDiff summary:\n{}",
            context.unwrap_or("none"),
            truncate_for_prompt(&staged, 10_000)
        );
        let draft = sanitize_generated_message(&self.run_internal_prompt_text(&prompt, false)?);
        let (title, body) = parse_titled_body(&draft)
            .ok_or_else(|| "failed to parse generated PR title/body".to_string())?;

        if command_exists("gh") {
            let body_path = write_temp_text_file("aris-pr-body.md", &body)?;
            let output = Command::new("gh")
                .args(["pr", "create", "--title", &title, "--body-file"])
                .arg(&body_path)
                .current_dir(env::current_dir()?)
                .output()?;
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                println!(
                    "PR\n  Result           created\n  Title            {title}\n  URL              {}",
                    if stdout.is_empty() { "<unknown>" } else { &stdout }
                );
                return Ok(());
            }
        }

        println!("PR draft\n  Title            {title}\n\n{body}");
        Ok(())
    }

    fn run_issue(&self, context: Option<&str>) -> Result<(), Box<dyn std::error::Error>> {
        let prompt = format!(
            "Generate a GitHub issue title and body from this conversation. Output plain text in this format exactly:\nTITLE: <title>\nBODY:\n<body markdown>\n\nContext hint: {}\n\nConversation context:\n{}",
            context.unwrap_or("none"),
            truncate_for_prompt(&recent_user_context(self.runtime.session(), 10), 10_000)
        );
        let draft = sanitize_generated_message(&self.run_internal_prompt_text(&prompt, false)?);
        let (title, body) = parse_titled_body(&draft)
            .ok_or_else(|| "failed to parse generated issue title/body".to_string())?;

        if command_exists("gh") {
            let body_path = write_temp_text_file("aris-issue-body.md", &body)?;
            let output = Command::new("gh")
                .args(["issue", "create", "--title", &title, "--body-file"])
                .arg(&body_path)
                .current_dir(env::current_dir()?)
                .output()?;
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                println!(
                    "Issue\n  Result           created\n  Title            {title}\n  URL              {}",
                    if stdout.is_empty() { "<unknown>" } else { &stdout }
                );
                return Ok(());
            }
        }

        println!("Issue draft\n  Title            {title}\n\n{body}");
        Ok(())
    }
}

fn sessions_dir() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let path = cwd.join(".claude").join("sessions");
    fs::create_dir_all(&path)?;
    Ok(path)
}

fn create_managed_session_handle() -> Result<SessionHandle, Box<dyn std::error::Error>> {
    let id = generate_session_id();
    let path = sessions_dir()?.join(format!("{id}.json"));
    Ok(SessionHandle { id, path })
}

fn generate_session_id() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    format!("session-{millis}")
}

fn resolve_session_reference(reference: &str) -> Result<SessionHandle, Box<dyn std::error::Error>> {
    let direct = PathBuf::from(reference);
    let path = if direct.exists() {
        direct
    } else {
        sessions_dir()?.join(format!("{reference}.json"))
    };
    if !path.exists() {
        return Err(format!("session not found: {reference}").into());
    }
    let id = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or(reference)
        .to_string();
    Ok(SessionHandle { id, path })
}

fn list_managed_sessions() -> Result<Vec<ManagedSessionSummary>, Box<dyn std::error::Error>> {
    let mut sessions = Vec::new();
    for entry in fs::read_dir(sessions_dir()?)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let metadata = entry.metadata()?;
        let modified_epoch_secs = metadata
            .modified()
            .ok()
            .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
            .map(|duration| duration.as_secs())
            .unwrap_or_default();
        let message_count = Session::load_from_path(&path)
            .map(|session| session.messages.len())
            .unwrap_or_default();
        let id = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("unknown")
            .to_string();
        sessions.push(ManagedSessionSummary {
            id,
            path,
            modified_epoch_secs,
            message_count,
        });
    }
    sessions.sort_by(|left, right| right.modified_epoch_secs.cmp(&left.modified_epoch_secs));
    Ok(sessions)
}

fn render_session_list(active_session_id: &str) -> Result<String, Box<dyn std::error::Error>> {
    let sessions = list_managed_sessions()?;
    let mut lines = vec![
        "Sessions".to_string(),
        format!("  Directory         {}", sessions_dir()?.display()),
    ];
    if sessions.is_empty() {
        lines.push("  No managed sessions saved yet.".to_string());
        return Ok(lines.join("\n"));
    }
    for session in sessions {
        let marker = if session.id == active_session_id {
            "● current"
        } else {
            "○ saved"
        };
        lines.push(format!(
            "  {id:<20} {marker:<10} msgs={msgs:<4} modified={modified} path={path}",
            id = session.id,
            msgs = session.message_count,
            modified = session.modified_epoch_secs,
            path = session.path.display(),
        ));
    }
    Ok(lines.join("\n"))
}

fn render_repl_help() -> String {
    [
        "REPL".to_string(),
        "  /exit                Quit the REPL".to_string(),
        "  /quit                Quit the REPL".to_string(),
        "  Up/Down              Navigate prompt history".to_string(),
        "  Tab                  Complete slash commands".to_string(),
        "  Ctrl-C               Clear input (or exit on empty prompt)".to_string(),
        "  Shift+Enter/Ctrl+J   Insert a newline".to_string(),
        String::new(),
        render_slash_command_help(),
    ]
    .join(
        "
",
    )
}

fn status_context(
    session_path: Option<&Path>,
) -> Result<StatusContext, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let loader = ConfigLoader::default_for(&cwd);
    let discovered_config_files = loader.discover().len();
    let runtime_config = loader.load()?;
    let project_context = ProjectContext::discover_with_git(&cwd, DEFAULT_DATE)?;
    let (project_root, git_branch) =
        parse_git_status_metadata(project_context.git_status.as_deref());
    Ok(StatusContext {
        cwd,
        session_path: session_path.map(Path::to_path_buf),
        loaded_config_files: runtime_config.loaded_entries().len(),
        discovered_config_files,
        memory_file_count: project_context.instruction_files.len(),
        project_root,
        git_branch,
    })
}

fn format_status_report(
    model: &str,
    usage: StatusUsage,
    permission_mode: &str,
    context: &StatusContext,
) -> String {
    [
        format!(
            "Status
  Model            {model}
  Permission mode  {permission_mode}
  Messages         {}
  Turns            {}
  Estimated tokens {}",
            usage.message_count, usage.turns, usage.estimated_tokens,
        ),
        format!(
            "Usage
  Latest total     {}
  Cumulative input {}
  Cumulative output {}
  Cumulative total {}",
            usage.latest.total_tokens(),
            usage.cumulative.input_tokens,
            usage.cumulative.output_tokens,
            usage.cumulative.total_tokens(),
        ),
        format!(
            "Workspace
  Cwd              {}
  Project root     {}
  Git branch       {}
  Session          {}
  Config files     loaded {}/{}
  Memory files     {}",
            context.cwd.display(),
            context
                .project_root
                .as_ref()
                .map_or_else(|| "unknown".to_string(), |path| path.display().to_string()),
            context.git_branch.as_deref().unwrap_or("unknown"),
            context.session_path.as_ref().map_or_else(
                || "live-repl".to_string(),
                |path| path.display().to_string()
            ),
            context.loaded_config_files,
            context.discovered_config_files,
            context.memory_file_count,
        ),
    ]
    .join(
        "

",
    )
}

fn render_config_report(section: Option<&str>) -> Result<String, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let loader = ConfigLoader::default_for(&cwd);
    let discovered = loader.discover();
    let runtime_config = loader.load()?;

    let mut lines = vec![
        format!(
            "Config
  Working directory {}
  Loaded files      {}
  Merged keys       {}",
            cwd.display(),
            runtime_config.loaded_entries().len(),
            runtime_config.merged().len()
        ),
        "Discovered files".to_string(),
    ];
    for entry in discovered {
        let source = match entry.source {
            ConfigSource::User => "user",
            ConfigSource::Project => "project",
            ConfigSource::Local => "local",
        };
        let status = if runtime_config
            .loaded_entries()
            .iter()
            .any(|loaded_entry| loaded_entry.path == entry.path)
        {
            "loaded"
        } else {
            "missing"
        };
        lines.push(format!(
            "  {source:<7} {status:<7} {}",
            entry.path.display()
        ));
    }

    if let Some(section) = section {
        lines.push(format!("Merged section: {section}"));
        let value = match section {
            "env" => runtime_config.get("env"),
            "hooks" => runtime_config.get("hooks"),
            "model" => runtime_config.get("model"),
            other => {
                lines.push(format!(
                    "  Unsupported config section '{other}'. Use env, hooks, or model."
                ));
                return Ok(lines.join(
                    "
",
                ));
            }
        };
        lines.push(format!(
            "  {}",
            match value {
                Some(value) => value.render(),
                None => "<unset>".to_string(),
            }
        ));
        return Ok(lines.join(
            "
",
        ));
    }

    lines.push("Merged JSON".to_string());
    lines.push(format!("  {}", runtime_config.as_json().render()));
    Ok(lines.join(
        "
",
    ))
}

fn render_memory_report() -> Result<String, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let project_context = ProjectContext::discover(&cwd, DEFAULT_DATE)?;
    let mut lines = vec![format!(
        "Memory
  Working directory {}
  Instruction files {}",
        cwd.display(),
        project_context.instruction_files.len()
    )];
    if project_context.instruction_files.is_empty() {
        lines.push("Discovered files".to_string());
        lines.push(
            "  No CLAUDE instruction files discovered in the current directory ancestry."
                .to_string(),
        );
    } else {
        lines.push("Discovered files".to_string());
        for (index, file) in project_context.instruction_files.iter().enumerate() {
            let preview = file.content.lines().next().unwrap_or("").trim();
            let preview = if preview.is_empty() {
                "<empty>"
            } else {
                preview
            };
            lines.push(format!("  {}. {}", index + 1, file.path.display(),));
            lines.push(format!(
                "     lines={} preview={}",
                file.content.lines().count(),
                preview
            ));
        }
    }
    Ok(lines.join(
        "
",
    ))
}

fn init_claude_md() -> Result<String, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    Ok(initialize_repo(&cwd)?.render())
}

fn run_init() -> Result<(), Box<dyn std::error::Error>> {
    println!("{}", init_claude_md()?);
    Ok(())
}

fn normalize_permission_mode(mode: &str) -> Option<&'static str> {
    match mode.trim() {
        "read-only" => Some("read-only"),
        "workspace-write" => Some("workspace-write"),
        "danger-full-access" => Some("danger-full-access"),
        _ => None,
    }
}

fn render_diff_report() -> Result<String, Box<dyn std::error::Error>> {
    let output = std::process::Command::new("git")
        .args(["diff", "--", ":(exclude).omx"])
        .current_dir(env::current_dir()?)
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(format!("git diff failed: {stderr}").into());
    }
    let diff = String::from_utf8(output.stdout)?;
    if diff.trim().is_empty() {
        return Ok(
            "Diff\n  Result           clean working tree\n  Detail           no current changes"
                .to_string(),
        );
    }
    Ok(format!("Diff\n\n{}", diff.trim_end()))
}

fn render_teleport_report(target: &str) -> Result<String, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;

    let file_list = Command::new("rg")
        .args(["--files"])
        .current_dir(&cwd)
        .output()?;
    let file_matches = if file_list.status.success() {
        String::from_utf8(file_list.stdout)?
            .lines()
            .filter(|line| line.contains(target))
            .take(10)
            .map(ToOwned::to_owned)
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };

    let content_output = Command::new("rg")
        .args(["-n", "-S", "--color", "never", target, "."])
        .current_dir(&cwd)
        .output()?;

    let mut lines = vec![format!("Teleport\n  Target           {target}")];
    if !file_matches.is_empty() {
        lines.push(String::new());
        lines.push("File matches".to_string());
        lines.extend(file_matches.into_iter().map(|path| format!("  {path}")));
    }

    if content_output.status.success() {
        let matches = String::from_utf8(content_output.stdout)?;
        if !matches.trim().is_empty() {
            lines.push(String::new());
            lines.push("Content matches".to_string());
            lines.push(truncate_for_prompt(&matches, 4_000));
        }
    }

    if lines.len() == 1 {
        lines.push("  Result           no matches found".to_string());
    }

    Ok(lines.join("\n"))
}

fn render_last_tool_debug_report(session: &Session) -> Result<String, Box<dyn std::error::Error>> {
    let last_tool_use = session
        .messages
        .iter()
        .rev()
        .find_map(|message| {
            message.blocks.iter().rev().find_map(|block| match block {
                ContentBlock::ToolUse { id, name, input } => {
                    Some((id.clone(), name.clone(), input.clone()))
                }
                _ => None,
            })
        })
        .ok_or_else(|| "no prior tool call found in session".to_string())?;

    let tool_result = session.messages.iter().rev().find_map(|message| {
        message.blocks.iter().rev().find_map(|block| match block {
            ContentBlock::ToolResult {
                tool_use_id,
                tool_name,
                output,
                is_error,
            } if tool_use_id == &last_tool_use.0 => {
                Some((tool_name.clone(), output.clone(), *is_error))
            }
            _ => None,
        })
    });

    let mut lines = vec![
        "Debug tool call".to_string(),
        format!("  Tool id          {}", last_tool_use.0),
        format!("  Tool name        {}", last_tool_use.1),
        "  Input".to_string(),
        indent_block(&last_tool_use.2, 4),
    ];

    match tool_result {
        Some((tool_name, output, is_error)) => {
            lines.push("  Result".to_string());
            lines.push(format!("    name           {tool_name}"));
            lines.push(format!(
                "    status         {}",
                if is_error { "error" } else { "ok" }
            ));
            lines.push(indent_block(&output, 4));
        }
        None => lines.push("  Result           missing tool result".to_string()),
    }

    Ok(lines.join("\n"))
}

fn indent_block(value: &str, spaces: usize) -> String {
    let indent = " ".repeat(spaces);
    value
        .lines()
        .map(|line| format!("{indent}{line}"))
        .collect::<Vec<_>>()
        .join("\n")
}

fn git_output(args: &[&str]) -> Result<String, Box<dyn std::error::Error>> {
    let output = Command::new("git")
        .args(args)
        .current_dir(env::current_dir()?)
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(format!("git {} failed: {stderr}", args.join(" ")).into());
    }
    Ok(String::from_utf8(output.stdout)?)
}

fn git_status_ok(args: &[&str]) -> Result<(), Box<dyn std::error::Error>> {
    let output = Command::new("git")
        .args(args)
        .current_dir(env::current_dir()?)
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(format!("git {} failed: {stderr}", args.join(" ")).into());
    }
    Ok(())
}

fn command_exists(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false)
}

fn write_temp_text_file(
    filename: &str,
    contents: &str,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = env::temp_dir().join(filename);
    fs::write(&path, contents)?;
    Ok(path)
}

fn recent_user_context(session: &Session, limit: usize) -> String {
    let requests = session
        .messages
        .iter()
        .filter(|message| message.role == MessageRole::User)
        .filter_map(|message| {
            message.blocks.iter().find_map(|block| match block {
                ContentBlock::Text { text } => Some(text.trim().to_string()),
                _ => None,
            })
        })
        .rev()
        .take(limit)
        .collect::<Vec<_>>();

    if requests.is_empty() {
        "<no prior user messages>".to_string()
    } else {
        requests
            .into_iter()
            .rev()
            .enumerate()
            .map(|(index, text)| format!("{}. {}", index + 1, text))
            .collect::<Vec<_>>()
            .join("\n")
    }
}

fn truncate_for_prompt(value: &str, limit: usize) -> String {
    if value.chars().count() <= limit {
        value.trim().to_string()
    } else {
        let truncated = value.chars().take(limit).collect::<String>();
        format!("{}\n…[truncated]", truncated.trim_end())
    }
}

fn sanitize_generated_message(value: &str) -> String {
    value.trim().trim_matches('`').trim().replace("\r\n", "\n")
}

fn parse_titled_body(value: &str) -> Option<(String, String)> {
    let normalized = sanitize_generated_message(value);
    let title = normalized
        .lines()
        .find_map(|line| line.strip_prefix("TITLE:").map(str::trim))?;
    let body_start = normalized.find("BODY:")?;
    let body = normalized[body_start + "BODY:".len()..].trim();
    Some((title.to_string(), body.to_string()))
}

fn render_version_report() -> String {
    let git_sha = GIT_SHA.unwrap_or("unknown");
    let target = BUILD_TARGET.unwrap_or("unknown");
    format!(
        "ARIS (Auto Research in Sleep)\n  Version          {VERSION}\n  Git SHA          {git_sha}\n  Target           {target}\n  Build date       {DEFAULT_DATE}"
    )
}

fn render_export_text(session: &Session) -> String {
    let mut lines = vec!["# Conversation Export".to_string(), String::new()];
    for (index, message) in session.messages.iter().enumerate() {
        let role = match message.role {
            MessageRole::System => "system",
            MessageRole::User => "user",
            MessageRole::Assistant => "assistant",
            MessageRole::Tool => "tool",
        };
        lines.push(format!("## {}. {role}", index + 1));
        for block in &message.blocks {
            match block {
                ContentBlock::Text { text } => lines.push(text.clone()),
                ContentBlock::ToolUse { id, name, input } => {
                    lines.push(format!("[tool_use id={id} name={name}] {input}"));
                }
                ContentBlock::ToolResult {
                    tool_use_id,
                    tool_name,
                    output,
                    is_error,
                } => {
                    lines.push(format!(
                        "[tool_result id={tool_use_id} name={tool_name} error={is_error}] {output}"
                    ));
                }
            }
        }
        lines.push(String::new());
    }
    lines.join("\n")
}

fn default_export_filename(session: &Session) -> String {
    let stem = session
        .messages
        .iter()
        .find_map(|message| match message.role {
            MessageRole::User => message.blocks.iter().find_map(|block| match block {
                ContentBlock::Text { text } => Some(text.as_str()),
                _ => None,
            }),
            _ => None,
        })
        .map_or("conversation", |text| {
            text.lines().next().unwrap_or("conversation")
        })
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .take(8)
        .collect::<Vec<_>>()
        .join("-");
    let fallback = if stem.is_empty() {
        "conversation"
    } else {
        &stem
    };
    format!("{fallback}.txt")
}

fn resolve_export_path(
    requested_path: Option<&str>,
    session: &Session,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    let file_name =
        requested_path.map_or_else(|| default_export_filename(session), ToOwned::to_owned);
    let final_name = if Path::new(&file_name)
        .extension()
        .is_some_and(|ext| ext.eq_ignore_ascii_case("txt"))
    {
        file_name
    } else {
        format!("{file_name}.txt")
    };
    Ok(cwd.join(final_name))
}

fn build_system_prompt(model_id: Option<&str>) -> Result<Vec<String>, Box<dyn std::error::Error>> {
    let mut prompt = match load_system_prompt(
        env::current_dir()?,
        DEFAULT_DATE,
        env::consts::OS,
        "unknown",
        model_id,
    ) {
        Ok(p) => p,
        Err(e) => {
            eprintln!(
                "\x1b[33mwarning\x1b[0m: could not load system prompt: {e}\n\
                 \x1b[2mUsing minimal prompt. This may be caused by incompatible Claude Code settings.\x1b[0m"
            );
            Vec::new()
        }
    };

    // ARIS identity: tell the model exactly who it is to prevent hallucination.
    let model_name = model_id.unwrap_or("unknown");
    let friendly_name = match model_name {
        "claude-opus-4-6" => "Claude Opus 4.6",
        "claude-sonnet-4-6" => "Claude Sonnet 4.6",
        "claude-haiku-4-5-20251001" => "Claude Haiku 4.5",
        other => other,
    };
    prompt.push(format!(
        "You are running inside ARIS (Auto Research in Sleep), a research automation CLI. \
         Your exact model is {model_name} ({friendly_name}), developed by Anthropic. \
         When users ask what model you are, answer: \"{friendly_name}\" (model ID: {model_name}). \
         Do NOT guess or hallucinate a different version number."
    ));

    // ARIS language preference
    let lang = std::env::var("ARIS_LANGUAGE").unwrap_or_else(|_| "cn".into());
    if lang == "cn" {
        prompt.push("用户偏好语言为中文。请始终用中文回复，除非用户明确使用英文提问。".to_string());
    } else {
        prompt.push("User language preference is English. Always respond in English unless the user explicitly writes in another language.".to_string());
    }

    // ARIS override: tell the model to use LlmReview instead of Codex MCP for external reviews.
    prompt.push(
        "IMPORTANT: When a skill instructs you to use `mcp__codex__codex` or `mcp__codex__codex-reply` \
         for external LLM review, use the `LlmReview` tool instead. The LlmReview tool calls \
         Gemini or OpenAI directly (via GEMINI_API_KEY or OPENAI_API_KEY) without needing MCP. \
         Pass the full review prompt as the `prompt` parameter to LlmReview."
            .to_string(),
    );

    // ARIS persistent memory (multi-file index system)
    memories::migrate_legacy_memory();
    let mem_entries = memories::load_memory_catalog();
    let mem_dir = memories::memories_dir();
    if !mem_entries.is_empty() {
        let catalog = memories::render_memory_catalog(&mem_entries);
        prompt.push(format!(
            "# ARIS Persistent Memory\n\
             You have {} memories from previous sessions. \
             Below is the catalog (name + description + path). \
             Use the read_file tool to load a specific memory when relevant.\n\n\
             {catalog}\n\n\
             To save new memories, use write_file to create .md files in {dir} \
             with YAML frontmatter (---\\nname: ...\\ndescription: ...\\n---).\n\
             When the user says \"remember this\" or you learn important context, save it.",
            mem_entries.len(),
            dir = mem_dir.display(),
        ));
    } else {
        prompt.push(format!(
            "# ARIS Persistent Memory\n\
             Memory directory: {dir}\n\
             No memories yet. When the user says \"remember this\" or you learn important context, \
             create .md files in {dir} with frontmatter:\n\
             ---\n\
             name: Memory Title\n\
             description: One-line summary for catalog\n\
             ---\n\
             (content here)\n\
             This memory persists across sessions.",
            dir = mem_dir.display(),
        ));
    }

    // ARIS persistent tasks (uses TodoWrite tool, stored as JSON)
    let tasks_path = aris_tasks_path();
    if tasks_path.exists() {
        if let Ok(content) = fs::read_to_string(&tasks_path) {
            if let Ok(todos) = serde_json::from_str::<Vec<serde_json::Value>>(&content) {
                if !todos.is_empty() {
                    let summary: Vec<String> = todos.iter().map(|t| {
                        let status = t.get("status").and_then(|s| s.as_str()).unwrap_or("pending");
                        let text = t.get("content").and_then(|c| c.as_str()).unwrap_or("?");
                        format!("- [{status}] {text}")
                    }).collect();
                    prompt.push(format!(
                        "# ARIS Task List\n\
                         Current tasks:\n{}\n\n\
                         Use the TodoWrite tool to update tasks (status: pending/in_progress/completed).",
                        summary.join("\n"),
                    ));
                }
            }
        }
    } else {
        prompt.push(
            "# ARIS Task List\n\
             Use the TodoWrite tool to create and manage tasks. \
             Each task has: content (description), status (pending/in_progress/completed)."
                .to_string(),
        );
    }

    Ok(prompt)
}

fn aris_tasks_path() -> PathBuf {
    let home = runtime::home_dir();
    PathBuf::from(home)
        .join(".config")
        .join("aris")
        .join("tasks.json")
}

/// Ensure TodoWrite uses ARIS tasks path.
fn init_aris_tasks_env() {
    if env::var("CLAWD_TODO_STORE").is_err() {
        env::set_var("CLAWD_TODO_STORE", aris_tasks_path().to_string_lossy().as_ref());
    }
}


fn build_runtime_feature_config(
) -> Result<runtime::RuntimeFeatureConfig, Box<dyn std::error::Error>> {
    let cwd = env::current_dir()?;
    match ConfigLoader::default_for(cwd).load() {
        Ok(config) => Ok(config.feature_config().clone()),
        Err(e) => {
            // Gracefully handle incompatible Claude Code settings (e.g. hooks format)
            eprintln!(
                "\x1b[33mwarning\x1b[0m: could not load settings: {e}\n\
                 \x1b[2mUsing default configuration. This may be caused by incompatible Claude Code settings.\x1b[0m"
            );
            Ok(runtime::RuntimeFeatureConfig::default())
        }
    }
}

fn build_runtime(
    session: Session,
    model: String,
    system_prompt: Vec<String>,
    enable_tools: bool,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
) -> Result<ConversationRuntime<ExecutorClient, CliToolExecutor>, Box<dyn std::error::Error>> {
    let executor: ExecutorClient =
        if let Some(config) = openai_executor::resolve_openai_executor_config() {
            ExecutorClient::OpenAI(openai_executor::OpenAIRuntimeClient::new(
                config,
                model,
                enable_tools,
                emit_output,
                allowed_tools.clone(),
            )?)
        } else {
            ExecutorClient::Anthropic(AnthropicRuntimeClient::new(
                model,
                enable_tools,
                emit_output,
                allowed_tools.clone(),
            )?)
        };

    let feature_config = build_runtime_feature_config()?;
    let event_sink = build_event_sink(&feature_config);
    Ok(ConversationRuntime::new_with_features(
        session,
        executor,
        CliToolExecutor::new(allowed_tools, emit_output),
        permission_policy(permission_mode),
        system_prompt,
        feature_config,
    )
    .with_event_sink(event_sink))
}

fn build_event_sink(
    _feature_config: &runtime::RuntimeFeatureConfig,
) -> Box<dyn runtime::EventSink> {
    let level_str = std::env::var("ARIS_META_LOGGING")
        .unwrap_or_default();
    let level = runtime::MetaLoggingLevel::parse(&level_str);
    if level == runtime::MetaLoggingLevel::Off {
        return Box::new(runtime::NoopEventSink);
    }
    let path = runtime::JsonlEventSink::default_path();
    let session_id = std::env::var("ARIS_SESSION_ID").unwrap_or_default();
    Box::new(runtime::JsonlEventSink::new(path, level, session_id))
}

struct CliPermissionPrompter {
    current_mode: PermissionMode,
}

impl CliPermissionPrompter {
    fn new(current_mode: PermissionMode) -> Self {
        Self { current_mode }
    }
}

impl runtime::PermissionPrompter for CliPermissionPrompter {
    fn decide(
        &mut self,
        request: &runtime::PermissionRequest,
    ) -> runtime::PermissionPromptDecision {
        println!();
        println!("Permission approval required");
        println!("  Tool             {}", request.tool_name);
        println!("  Current mode     {}", self.current_mode.as_str());
        println!("  Required mode    {}", request.required_mode.as_str());
        println!("  Input            {}", request.input);
        print!("Approve this tool call? [y/N]: ");
        let _ = io::stdout().flush();

        let mut response = String::new();
        match io::stdin().read_line(&mut response) {
            Ok(_) => {
                let normalized = response.trim().to_ascii_lowercase();
                if matches!(normalized.as_str(), "y" | "yes") {
                    runtime::PermissionPromptDecision::Allow
                } else {
                    runtime::PermissionPromptDecision::Deny {
                        reason: format!(
                            "tool '{}' denied by user approval prompt",
                            request.tool_name
                        ),
                    }
                }
            }
            Err(error) => runtime::PermissionPromptDecision::Deny {
                reason: format!("permission approval failed: {error}"),
            },
        }
    }
}

// ── Executor client enum: dispatches to Anthropic or OpenAI-compat ───────────

enum ExecutorClient {
    Anthropic(AnthropicRuntimeClient),
    OpenAI(openai_executor::OpenAIRuntimeClient),
}

impl ApiClient for ExecutorClient {
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
        match self {
            Self::Anthropic(c) => c.stream(request),
            Self::OpenAI(c) => c.stream(request),
        }
    }
}

struct AnthropicRuntimeClient {
    runtime: tokio::runtime::Runtime,
    client: AnthropicClient,
    model: String,
    enable_tools: bool,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
}

impl AnthropicRuntimeClient {
    fn new(
        model: String,
        enable_tools: bool,
        emit_output: bool,
        allowed_tools: Option<AllowedToolSet>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            runtime: tokio::runtime::Runtime::new()?,
            client: AnthropicClient::from_auth(resolve_cli_auth_source()?)
                .with_base_url(api::read_base_url())
                .with_send_betas(api::read_send_betas()),
            model,
            enable_tools,
            emit_output,
            allowed_tools,
        })
    }
}

fn resolve_cli_auth_source() -> Result<AuthSource, Box<dyn std::error::Error>> {
    Ok(resolve_startup_auth_source(|| {
        let cwd = env::current_dir().map_err(api::ApiError::from)?;
        let config = ConfigLoader::default_for(&cwd).load().map_err(|error| {
            api::ApiError::Auth(format!("failed to load runtime OAuth config: {error}"))
        })?;
        Ok(config.oauth().cloned())
    })?)
}

impl ApiClient for AnthropicRuntimeClient {
    #[allow(clippy::too_many_lines)]
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
        let message_request = MessageRequest {
            model: self.model.clone(),
            max_tokens: max_tokens_for_model(&self.model),
            messages: convert_messages(&request.messages),
            system: if request.system_prompt.is_empty() {
                None
            } else {
                let prompt = request.system_prompt.join("\n\n");
                // ttl:"1h" requires claude-code-20250219 beta (OAuth only)
                let is_oauth = self.client.auth_source().bearer_token().is_some()
                    && self.client.auth_source().api_key().is_none();
                let cache_control = if is_oauth {
                    serde_json::json!({ "type": "ephemeral", "ttl": "1h" })
                } else {
                    serde_json::json!({ "type": "ephemeral" })
                };
                Some(serde_json::json!([{
                    "type": "text",
                    "text": prompt,
                    "cache_control": cache_control
                }]))
            },
            tools: self.enable_tools.then(|| {
                filter_tool_specs(self.allowed_tools.as_ref())
                    .into_iter()
                    .map(|spec| ToolDefinition {
                        name: spec.name.to_string(),
                        description: Some(spec.description.to_string()),
                        input_schema: spec.input_schema,
                    })
                    .collect()
            }),
            tool_choice: self.enable_tools.then_some(ToolChoice::Auto),
            stream: true,
        };

        self.runtime.block_on(async {
            let mut stream = self
                .client
                .stream_message(&message_request)
                .await
                .map_err(|error| RuntimeError::new(error.to_string()))?;
            let mut stdout = io::stdout();
            let mut sink = io::sink();
            let out: &mut dyn Write = if self.emit_output {
                &mut stdout
            } else {
                &mut sink
            };
            let renderer = TerminalRenderer::new();
            let mut markdown_stream = MarkdownStreamState::default();
            let mut events = Vec::new();
            let mut pending_tool: Option<(String, String, String)> = None;
            let mut saw_stop = false;

            while let Some(event) = stream
                .next_event()
                .await
                .map_err(|error| RuntimeError::new(error.to_string()))?
            {
                // Check for Ctrl+C interrupt between events
                if runtime::is_interrupted() {
                    runtime::clear_interrupt();
                    return Err(RuntimeError::new("interrupted by user"));
                }
                match event {
                    ApiStreamEvent::MessageStart(start) => {
                        for block in start.message.content {
                            push_output_block(block, out, &mut events, &mut pending_tool, true)?;
                        }
                    }
                    ApiStreamEvent::ContentBlockStart(start) => {
                        push_output_block(
                            start.content_block,
                            out,
                            &mut events,
                            &mut pending_tool,
                            true,
                        )?;
                    }
                    ApiStreamEvent::ContentBlockDelta(delta) => match delta.delta {
                        ContentBlockDelta::TextDelta { text } => {
                            if !text.is_empty() {
                                if let Some(rendered) = markdown_stream.push(&renderer, &text) {
                                    write!(out, "{rendered}")
                                        .and_then(|()| out.flush())
                                        .map_err(|error| RuntimeError::new(error.to_string()))?;
                                }
                                events.push(AssistantEvent::TextDelta(text));
                            }
                        }
                        ContentBlockDelta::InputJsonDelta { partial_json } => {
                            if let Some((_, _, input)) = &mut pending_tool {
                                input.push_str(&partial_json);
                            }
                        }
                    },
                    ApiStreamEvent::ContentBlockStop(_) => {
                        if let Some(rendered) = markdown_stream.flush(&renderer) {
                            write!(out, "{rendered}")
                                .and_then(|()| out.flush())
                                .map_err(|error| RuntimeError::new(error.to_string()))?;
                        }
                        if let Some((id, name, input)) = pending_tool.take() {
                            // Display tool call now that input is fully accumulated
                            writeln!(out, "\n{}", format_tool_call_start(&name, &input))
                                .and_then(|()| out.flush())
                                .map_err(|error| RuntimeError::new(error.to_string()))?;
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
                        if let Some(rendered) = markdown_stream.flush(&renderer) {
                            write!(out, "{rendered}")
                                .and_then(|()| out.flush())
                                .map_err(|error| RuntimeError::new(error.to_string()))?;
                        }
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
            response_to_events(response, out)
        })
    }
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

fn collect_tool_uses(summary: &runtime::TurnSummary) -> Vec<serde_json::Value> {
    summary
        .assistant_messages
        .iter()
        .flat_map(|message| message.blocks.iter())
        .filter_map(|block| match block {
            ContentBlock::ToolUse { id, name, input } => Some(json!({
                "id": id,
                "name": name,
                "input": input,
            })),
            _ => None,
        })
        .collect()
}

fn collect_tool_results(summary: &runtime::TurnSummary) -> Vec<serde_json::Value> {
    summary
        .tool_results
        .iter()
        .flat_map(|message| message.blocks.iter())
        .filter_map(|block| match block {
            ContentBlock::ToolResult {
                tool_use_id,
                tool_name,
                output,
                is_error,
            } => Some(json!({
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "output": output,
                "is_error": is_error,
            })),
            _ => None,
        })
        .collect()
}

fn slash_command_completion_candidates() -> Vec<(String, String)> {
    let mut candidates: Vec<(String, String)> = slash_command_specs()
        .iter()
        .map(|spec| (format!("/{}", spec.name), spec.summary.to_string()))
        .collect();

    let existing: std::collections::HashSet<String> =
        candidates.iter().map(|(n, _)| n.clone()).collect();
    let mut seen = existing;

    // Add all discovered skills (ARIS > Claude > bundled, already deduplicated)
    let all_skills = discover_all_skills();
    let mut skill_candidates: Vec<(String, String)> = all_skills
        .into_iter()
        .filter_map(|(name, desc, _source)| {
            let candidate = format!("/{name}");
            if seen.contains(&candidate) {
                return None;
            }
            seen.insert(candidate.clone());
            Some((candidate, desc))
        })
        .collect();
    skill_candidates.sort_by(|a, b| a.0.cmp(&b.0));
    candidates.extend(skill_candidates);

    candidates
}

/// Extract the `description:` field from a SKILL.md YAML frontmatter.
fn parse_skill_description(content: &str) -> Option<String> {
    let inner = content.strip_prefix("---")?.trim_start_matches('\n');
    let end = inner.find("\n---")?;
    let frontmatter = &inner[..end];
    for line in frontmatter.lines() {
        if let Some(rest) = line.strip_prefix("description:") {
            return Some(rest.trim().to_string());
        }
    }
    None
}

pub(crate) fn format_tool_call_start(name: &str, input: &str) -> String {
    let parsed: serde_json::Value =
        serde_json::from_str(input).unwrap_or(serde_json::Value::String(input.to_string()));

    let detail = match name {
        "bash" | "Bash" => format_bash_call(&parsed),
        "read_file" | "Read" => {
            let path = extract_tool_path(&parsed);
            format!("\x1b[2m📄 Reading {path}…\x1b[0m")
        }
        "write_file" | "Write" => {
            let path = extract_tool_path(&parsed);
            let lines = parsed
                .get("content")
                .and_then(|value| value.as_str())
                .map_or(0, |content| content.lines().count());
            format!("\x1b[1;32m✏️ Writing {path}\x1b[0m \x1b[2m({lines} lines)\x1b[0m")
        }
        "edit_file" | "Edit" => {
            let path = extract_tool_path(&parsed);
            let old_value = parsed
                .get("old_string")
                .or_else(|| parsed.get("oldString"))
                .and_then(|value| value.as_str())
                .unwrap_or_default();
            let new_value = parsed
                .get("new_string")
                .or_else(|| parsed.get("newString"))
                .and_then(|value| value.as_str())
                .unwrap_or_default();
            format!(
                "\x1b[1;33m📝 Editing {path}\x1b[0m{}",
                format_patch_preview(old_value, new_value)
                    .map(|preview| format!("\n{preview}"))
                    .unwrap_or_default()
            )
        }
        "glob_search" | "Glob" => format_search_start("🔎 Glob", &parsed),
        "grep_search" | "Grep" => format_search_start("🔎 Grep", &parsed),
        "web_search" | "WebSearch" => parsed
            .get("query")
            .and_then(|value| value.as_str())
            .unwrap_or("?")
            .to_string(),
        _ => summarize_tool_payload(input),
    };

    format!(
        "\x1b[38;5;74m●\x1b[0m \x1b[1m{name}\x1b[0m\x1b[38;5;245m({detail})\x1b[0m"
    )
}

fn format_tool_result(name: &str, output: &str, is_error: bool) -> String {
    let icon = if is_error {
        "\x1b[1;31m✗\x1b[0m"
    } else {
        "\x1b[1;32m✓\x1b[0m"
    };
    let connector = "\x1b[38;5;240m└\x1b[0m";
    if is_error {
        let summary = truncate_for_summary(output.trim(), 160);
        return if summary.is_empty() {
            format!("  {connector} {icon} \x1b[38;5;245m{name}\x1b[0m")
        } else {
            format!("  {connector} {icon} \x1b[38;5;245m{name}\x1b[0m\n    \x1b[38;5;203m{summary}\x1b[0m")
        };
    }

    let parsed: serde_json::Value =
        serde_json::from_str(output).unwrap_or(serde_json::Value::String(output.to_string()));
    let result_body = match name {
        "bash" | "Bash" => format_bash_result(icon, &parsed),
        "read_file" | "Read" => format_read_result(icon, &parsed),
        "write_file" | "Write" => format_write_result(icon, &parsed),
        "edit_file" | "Edit" => format_edit_result(icon, &parsed),
        "glob_search" | "Glob" => format_glob_result(icon, &parsed),
        "grep_search" | "Grep" => format_grep_result(icon, &parsed),
        "web_search" | "WebSearch" => {
            // Show just query and hit count
            let query = parsed.get("query").and_then(|v| v.as_str()).unwrap_or("?");
            let hit_count = parsed.get("results")
                .and_then(|v| v.as_array())
                .map_or(0, |a| a.iter().filter(|v| v.get("content").is_some()).flat_map(|v| v.get("content").and_then(|c| c.as_array())).map(|a| a.len()).sum::<usize>());
            format!("{icon} \x1b[38;5;245mWebSearch:\x1b[0m \"{query}\" ({hit_count} results)")
        }
        "web_fetch" | "WebFetch" => {
            let url = parsed.get("url").and_then(|v| v.as_str()).unwrap_or("?");
            let bytes = parsed.get("bytes").and_then(|v| v.as_u64()).unwrap_or(0);
            let code = parsed.get("code").and_then(|v| v.as_u64()).unwrap_or(0);
            format!("{icon} \x1b[38;5;245mWebFetch:\x1b[0m {url} ({code}, {bytes} bytes)")
        }
        "LlmReview" => {
            let summary = truncate_for_summary(output.trim(), 120);
            format!("{icon} \x1b[38;5;245mLlmReview:\x1b[0m {summary}")
        }
        "Skill" => {
            let skill = parsed.get("skill").and_then(|v| v.as_str()).unwrap_or("?");
            format!("{icon} \x1b[38;5;245mSkill:\x1b[0m /{skill} loaded")
        }
        _ => {
            let summary = truncate_for_summary(output.trim(), 120);
            format!("{icon} \x1b[38;5;245m{name}:\x1b[0m {summary}")
        }
    };
    format!("  {connector} {result_body}")
}

fn extract_tool_path(parsed: &serde_json::Value) -> String {
    parsed
        .get("file_path")
        .or_else(|| parsed.get("filePath"))
        .or_else(|| parsed.get("path"))
        .and_then(|value| value.as_str())
        .unwrap_or("?")
        .to_string()
}

fn format_search_start(label: &str, parsed: &serde_json::Value) -> String {
    let pattern = parsed
        .get("pattern")
        .and_then(|value| value.as_str())
        .unwrap_or("?");
    let scope = parsed
        .get("path")
        .and_then(|value| value.as_str())
        .unwrap_or(".");
    format!("{label} {pattern}\n\x1b[2min {scope}\x1b[0m")
}

fn format_patch_preview(old_value: &str, new_value: &str) -> Option<String> {
    if old_value.is_empty() && new_value.is_empty() {
        return None;
    }
    Some(format!(
        "\x1b[38;5;203m- {}\x1b[0m\n\x1b[38;5;70m+ {}\x1b[0m",
        truncate_for_summary(first_visible_line(old_value), 72),
        truncate_for_summary(first_visible_line(new_value), 72)
    ))
}

fn format_bash_call(parsed: &serde_json::Value) -> String {
    let command = parsed
        .get("command")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    if command.is_empty() {
        String::new()
    } else {
        format!(
            "\x1b[48;5;236;38;5;255m $ {} \x1b[0m",
            truncate_for_summary(command, 160)
        )
    }
}

fn first_visible_line(text: &str) -> &str {
    text.lines()
        .find(|line| !line.trim().is_empty())
        .unwrap_or(text)
}

fn format_bash_result(icon: &str, parsed: &serde_json::Value) -> String {
    let mut lines = vec![format!("{icon} \x1b[38;5;245mbash\x1b[0m")];
    if let Some(task_id) = parsed
        .get("backgroundTaskId")
        .and_then(|value| value.as_str())
    {
        lines[0].push_str(&format!(" backgrounded ({task_id})"));
    } else if let Some(status) = parsed
        .get("returnCodeInterpretation")
        .and_then(|value| value.as_str())
        .filter(|status| !status.is_empty())
    {
        lines[0].push_str(&format!(" {status}"));
    }

    if let Some(stdout) = parsed.get("stdout").and_then(|value| value.as_str()) {
        if !stdout.trim().is_empty() {
            lines.push(stdout.trim_end().to_string());
        }
    }
    if let Some(stderr) = parsed.get("stderr").and_then(|value| value.as_str()) {
        if !stderr.trim().is_empty() {
            lines.push(format!("\x1b[38;5;203m{}\x1b[0m", stderr.trim_end()));
        }
    }

    lines.join("\n\n")
}

fn format_read_result(icon: &str, parsed: &serde_json::Value) -> String {
    let file = parsed.get("file").unwrap_or(parsed);
    let path = extract_tool_path(file);
    let start_line = file
        .get("startLine")
        .and_then(|value| value.as_u64())
        .unwrap_or(1);
    let num_lines = file
        .get("numLines")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let total_lines = file
        .get("totalLines")
        .and_then(|value| value.as_u64())
        .unwrap_or(num_lines);
    let content = file
        .get("content")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    let end_line = start_line.saturating_add(num_lines.saturating_sub(1));

    format!(
        "{icon} \x1b[2m📄 Read {path} (lines {}-{} of {})\x1b[0m\n{}",
        start_line,
        end_line.max(start_line),
        total_lines,
        content
    )
}

fn format_write_result(icon: &str, parsed: &serde_json::Value) -> String {
    let path = extract_tool_path(parsed);
    let kind = parsed
        .get("type")
        .and_then(|value| value.as_str())
        .unwrap_or("write");
    let line_count = parsed
        .get("content")
        .and_then(|value| value.as_str())
        .map(|content| content.lines().count())
        .unwrap_or(0);
    format!(
        "{icon} \x1b[1;32m✏️ {} {path}\x1b[0m \x1b[2m({line_count} lines)\x1b[0m",
        if kind == "create" { "Wrote" } else { "Updated" },
    )
}

fn format_structured_patch_preview(parsed: &serde_json::Value) -> Option<String> {
    let hunks = parsed.get("structuredPatch")?.as_array()?;
    let mut preview = Vec::new();
    for hunk in hunks.iter().take(2) {
        let lines = hunk.get("lines")?.as_array()?;
        for line in lines.iter().filter_map(|value| value.as_str()).take(6) {
            match line.chars().next() {
                Some('+') => preview.push(format!("\x1b[38;5;70m{line}\x1b[0m")),
                Some('-') => preview.push(format!("\x1b[38;5;203m{line}\x1b[0m")),
                _ => preview.push(line.to_string()),
            }
        }
    }
    if preview.is_empty() {
        None
    } else {
        Some(preview.join("\n"))
    }
}

fn format_edit_result(icon: &str, parsed: &serde_json::Value) -> String {
    let path = extract_tool_path(parsed);
    let suffix = if parsed
        .get("replaceAll")
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
    {
        " (replace all)"
    } else {
        ""
    };
    let preview = format_structured_patch_preview(parsed).or_else(|| {
        let old_value = parsed
            .get("oldString")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        let new_value = parsed
            .get("newString")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        format_patch_preview(old_value, new_value)
    });

    match preview {
        Some(preview) => format!("{icon} \x1b[1;33m📝 Edited {path}{suffix}\x1b[0m\n{preview}"),
        None => format!("{icon} \x1b[1;33m📝 Edited {path}{suffix}\x1b[0m"),
    }
}

fn format_glob_result(icon: &str, parsed: &serde_json::Value) -> String {
    let num_files = parsed
        .get("numFiles")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let filenames = parsed
        .get("filenames")
        .and_then(|value| value.as_array())
        .map(|files| {
            files
                .iter()
                .filter_map(|value| value.as_str())
                .take(8)
                .collect::<Vec<_>>()
                .join("\n")
        })
        .unwrap_or_default();
    if filenames.is_empty() {
        format!("{icon} \x1b[38;5;245mglob_search\x1b[0m matched {num_files} files")
    } else {
        format!("{icon} \x1b[38;5;245mglob_search\x1b[0m matched {num_files} files\n{filenames}")
    }
}

fn format_grep_result(icon: &str, parsed: &serde_json::Value) -> String {
    let num_matches = parsed
        .get("numMatches")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let num_files = parsed
        .get("numFiles")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let content = parsed
        .get("content")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    let filenames = parsed
        .get("filenames")
        .and_then(|value| value.as_array())
        .map(|files| {
            files
                .iter()
                .filter_map(|value| value.as_str())
                .take(8)
                .collect::<Vec<_>>()
                .join("\n")
        })
        .unwrap_or_default();
    let summary = format!(
        "{icon} \x1b[38;5;245mgrep_search\x1b[0m {num_matches} matches across {num_files} files"
    );
    if !content.trim().is_empty() {
        format!("{summary}\n{}", content.trim_end())
    } else if !filenames.is_empty() {
        format!("{summary}\n{filenames}")
    } else {
        summary
    }
}

fn summarize_tool_payload(payload: &str) -> String {
    let compact = match serde_json::from_str::<serde_json::Value>(payload) {
        Ok(value) => value.to_string(),
        Err(_) => payload.trim().to_string(),
    };
    truncate_for_summary(&compact, 96)
}

fn truncate_for_summary(value: &str, limit: usize) -> String {
    let mut chars = value.chars();
    let truncated = chars.by_ref().take(limit).collect::<String>();
    if chars.next().is_some() {
        format!("{truncated}…")
    } else {
        truncated
    }
}

fn push_output_block(
    block: OutputContentBlock,
    out: &mut (impl Write + ?Sized),
    events: &mut Vec<AssistantEvent>,
    pending_tool: &mut Option<(String, String, String)>,
    streaming_tool_input: bool,
) -> Result<(), RuntimeError> {
    match block {
        OutputContentBlock::Text { text } => {
            if !text.is_empty() {
                let rendered = TerminalRenderer::new().markdown_to_ansi(&text);
                write!(out, "{rendered}")
                    .and_then(|()| out.flush())
                    .map_err(|error| RuntimeError::new(error.to_string()))?;
                events.push(AssistantEvent::TextDelta(text));
            }
        }
        OutputContentBlock::ToolUse { id, name, input } => {
            // During streaming, the initial content_block_start has an empty input ({}).
            // The real input arrives via input_json_delta events. In
            // non-streaming responses, preserve a legitimate empty object.
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
    }
    Ok(())
}

fn response_to_events(
    response: MessageResponse,
    out: &mut (impl Write + ?Sized),
) -> Result<Vec<AssistantEvent>, RuntimeError> {
    let mut events = Vec::new();
    let mut pending_tool = None;

    for block in response.content {
        push_output_block(block, out, &mut events, &mut pending_tool, false)?;
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
    Ok(events)
}

struct CliToolExecutor {
    renderer: TerminalRenderer,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
}

impl CliToolExecutor {
    fn new(allowed_tools: Option<AllowedToolSet>, emit_output: bool) -> Self {
        Self {
            renderer: TerminalRenderer::new(),
            emit_output,
            allowed_tools,
        }
    }
}

impl ToolExecutor for CliToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError> {
        if self
            .allowed_tools
            .as_ref()
            .is_some_and(|allowed| !allowed.contains(tool_name))
        {
            return Err(ToolError::new(format!(
                "tool `{tool_name}` is not enabled by the current --allowedTools setting"
            )));
        }
        let value = serde_json::from_str(input)
            .map_err(|error| ToolError::new(format!("invalid tool input JSON: {error}")))?;
        match execute_tool(tool_name, &value) {
            Ok(output) => {
                if self.emit_output {
                    let markdown = format_tool_result(tool_name, &output, false);
                    self.renderer
                        .stream_markdown(&markdown, &mut io::stdout())
                        .map_err(|error| ToolError::new(error.to_string()))?;
                }
                Ok(output)
            }
            Err(error) => {
                if self.emit_output {
                    let markdown = format_tool_result(tool_name, &error, true);
                    self.renderer
                        .stream_markdown(&markdown, &mut io::stdout())
                        .map_err(|stream_error| ToolError::new(stream_error.to_string()))?;
                }
                Err(ToolError::new(error))
            }
        }
    }
}

fn permission_policy(mode: PermissionMode) -> PermissionPolicy {
    tool_permission_specs()
        .into_iter()
        .fold(PermissionPolicy::new(mode), |policy, spec| {
            policy.with_tool_requirement(spec.name, spec.required_permission)
        })
}

fn tool_permission_specs() -> Vec<ToolSpec> {
    mvp_tool_specs()
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
                })
                .collect::<Vec<_>>();
            (!content.is_empty()).then(|| InputMessage {
                role: role.to_string(),
                content,
            })
        })
        .collect()
}

fn print_help_to(out: &mut impl Write) -> io::Result<()> {
    writeln!(out, "aris v{VERSION} — Auto Research in Sleep")?;
    writeln!(out)?;
    writeln!(out, "Usage:")?;
    writeln!(
        out,
        "  aris [--model MODEL] [--allowedTools TOOL[,TOOL...]]"
    )?;
    writeln!(out, "      Start the interactive REPL")?;
    writeln!(
        out,
        "  aris [--model MODEL] [--output-format text|json] prompt TEXT"
    )?;
    writeln!(out, "      Send one prompt and exit")?;
    writeln!(
        out,
        "  aris [--model MODEL] [--output-format text|json] TEXT"
    )?;
    writeln!(out, "      Shorthand non-interactive prompt mode")?;
    writeln!(
        out,
        "  aris --resume SESSION.json [/status] [/compact] [...]"
    )?;
    writeln!(
        out,
        "      Inspect or maintain a saved session without entering the REPL"
    )?;
    writeln!(out, "  aris setup                                          Initialize ARIS (install skills, configure MCP)")?;
    writeln!(out, "  aris doctor                                         Health check")?;
    writeln!(out, "  aris dump-manifests")?;
    writeln!(out, "  aris bootstrap-plan")?;
    writeln!(out, "  aris system-prompt [--cwd PATH] [--date YYYY-MM-DD]")?;
    writeln!(out, "  aris login")?;
    writeln!(out, "  aris logout")?;
    writeln!(out, "  aris init")?;
    writeln!(out)?;
    writeln!(out, "Flags:")?;
    writeln!(
        out,
        "  --model MODEL              Override the active model"
    )?;
    writeln!(
        out,
        "  --output-format FORMAT     Non-interactive output format: text or json"
    )?;
    writeln!(
        out,
        "  --permission-mode MODE     Set read-only, workspace-write, or danger-full-access"
    )?;
    writeln!(
        out,
        "  --dangerously-skip-permissions  Skip all permission checks"
    )?;
    writeln!(out, "  --allowedTools TOOLS       Restrict enabled tools (repeatable; comma-separated aliases supported)")?;
    writeln!(
        out,
        "  --version, -V              Print version and build information locally"
    )?;
    writeln!(out)?;
    writeln!(out, "Executor providers:")?;
    writeln!(
        out,
        "  Default:   Anthropic Claude (ANTHROPIC_API_KEY)"
    )?;
    writeln!(
        out,
        "  OpenAI:    EXECUTOR_PROVIDER=openai EXECUTOR_API_KEY=xxx aris --model gpt-4o"
    )?;
    writeln!(
        out,
        "  DeepSeek:  EXECUTOR_PROVIDER=openai EXECUTOR_BASE_URL=https://api.deepseek.com EXECUTOR_API_KEY=xxx aris --model deepseek-chat"
    )?;
    writeln!(
        out,
        "  GLM:       EXECUTOR_PROVIDER=openai EXECUTOR_BASE_URL=https://open.bigmodel.cn/api/paas/v4/ EXECUTOR_API_KEY=xxx aris --model glm-4-plus"
    )?;
    writeln!(
        out,
        "  Gemini:    EXECUTOR_PROVIDER=openai EXECUTOR_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai EXECUTOR_API_KEY=xxx aris --model gemini-2.5-pro"
    )?;
    writeln!(out)?;
    writeln!(out, "Interactive slash commands:")?;
    writeln!(out, "{}", render_slash_command_help())?;
    writeln!(out)?;
    let resume_commands = resume_supported_slash_commands()
        .into_iter()
        .map(|spec| match spec.argument_hint {
            Some(argument_hint) => format!("/{} {}", spec.name, argument_hint),
            None => format!("/{}", spec.name),
        })
        .collect::<Vec<_>>()
        .join(", ");
    writeln!(out, "Resume-safe commands: {resume_commands}")?;
    writeln!(out, "Examples:")?;
    writeln!(out, "  aris --model claude-opus \"summarize this repo\"")?;
    writeln!(
        out,
        "  aris --output-format json prompt \"explain src/main.rs\""
    )?;
    writeln!(
        out,
        "  aris --allowedTools read,glob \"summarize Cargo.toml\""
    )?;
    writeln!(
        out,
        "  aris --resume session.json /status /diff /export notes.txt"
    )?;
    writeln!(out, "  aris setup")?;
    writeln!(out, "  aris doctor")?;
    writeln!(out, "  aris login")?;
    writeln!(out, "  aris init")?;
    Ok(())
}

fn print_help() {
    let _ = print_help_to(&mut io::stdout());
}

fn check_auth_status() -> &'static str {
    if env::var("ANTHROPIC_API_KEY").map_or(false, |v| !v.is_empty()) {
        return "OK (API key)";
    }
    if env::var("ANTHROPIC_AUTH_TOKEN").map_or(false, |v| !v.is_empty()) {
        return "OK (bearer token)";
    }
    let home = runtime::home_dir();
    let creds_path = PathBuf::from(&home).join(".claude").join("credentials.json");
    if creds_path.exists() {
        return "OK (OAuth saved)";
    }
    // Check macOS Keychain for Claude Code's OAuth token
    if let Ok(output) = Command::new("security")
        .args(["find-generic-password", "-s", "Claude Code-credentials", "-w"])
        .output()
    {
        if output.status.success() {
            return "OK (Keychain OAuth)";
        }
    }
    "NOT FOUND"
}

fn run_setup() -> Result<(), Box<dyn std::error::Error>> {
    println!("ARIS Setup v{VERSION}");
    println!();

    // Step 1: Check API auth
    let auth_status = check_auth_status();
    println!("  [1/3] API auth:    {auth_status}");
    if auth_status == "NOT FOUND" {
        println!("        Run `aris login` or set ANTHROPIC_API_KEY");
    }

    // Step 2: Ensure skills directory exists
    let skills_dir = dirs_claude_skills();
    print!("  [2/3] Skills:      ");
    if !skills_dir.exists() {
        fs::create_dir_all(&skills_dir)?;
    }
    let skill_count = fs::read_dir(&skills_dir)
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .filter(|e| e.path().join("SKILL.md").exists())
                .count()
        })
        .unwrap_or(0);
    println!("{skill_count} skills in {}", skills_dir.display());

    // Step 3: Configure Codex MCP
    print!("  [3/3] Codex MCP:   ");
    match which_codex() {
        Some(codex_path) => {
            println!("codex found at {}", codex_path.display());
            // Try to add Codex MCP to ~/.claude.json
            match configure_codex_mcp(&codex_path) {
                Ok(true) => println!("        Added Codex MCP to ~/.claude.json"),
                Ok(false) => println!("        Codex MCP already configured"),
                Err(e) => println!("        Warning: could not configure MCP: {e}"),
            }
        }
        None => {
            println!("NOT FOUND");
            println!("        Install with: npm install -g @openai/codex");
            println!("        Then re-run `aris setup` to configure MCP");
        }
    }

    println!();
    println!("Setup complete. Run `aris doctor` to verify.");
    Ok(())
}

/// Add Codex MCP server entry to ~/.claude.json if not already present.
/// Returns Ok(true) if added, Ok(false) if already exists.
fn configure_codex_mcp(codex_path: &Path) -> Result<bool, Box<dyn std::error::Error>> {
    let home = Ok::<String, std::env::VarError>(runtime::home_dir())?;
    let config_path = PathBuf::from(&home).join(".claude.json");

    // Read existing config or start fresh
    let mut config: serde_json::Value = if config_path.exists() {
        let content = fs::read_to_string(&config_path)?;
        serde_json::from_str(&content)?
    } else {
        serde_json::json!({})
    };

    // Check if codex MCP already configured
    if let Some(servers) = config.get("mcpServers").and_then(|s| s.as_object()) {
        if servers.contains_key("codex") {
            return Ok(false);
        }
    }

    // Add codex MCP entry with absolute path
    let mcp_entry = serde_json::json!({
        "type": "stdio",
        "command": codex_path.to_string_lossy(),
        "args": ["mcp-server"]
    });

    if let Some(obj) = config.as_object_mut() {
        let servers = obj
            .entry("mcpServers")
            .or_insert_with(|| serde_json::json!({}));
        if let Some(servers_obj) = servers.as_object_mut() {
            servers_obj.insert("codex".to_string(), mcp_entry);
        }
    }

    // Atomic write: write to temp file then rename
    let tmp_path = config_path.with_extension("json.tmp");
    fs::write(&tmp_path, serde_json::to_string_pretty(&config)?)?;
    // Windows fs::rename fails if target exists — remove first
    if config_path.exists() {
        let _ = fs::remove_file(&config_path);
    }
    fs::rename(&tmp_path, &config_path)?;

    Ok(true)
}

fn run_doctor() -> Result<(), Box<dyn std::error::Error>> {
    println!("ARIS Doctor v{VERSION}");
    println!();

    let mut all_ok = true;

    // Check 0: Executor provider
    let executor_provider = std::env::var("EXECUTOR_PROVIDER").unwrap_or_else(|_| "anthropic".into());
    print!("  Executor:     ");
    if executor_provider == "openai" {
        let base = std::env::var("EXECUTOR_BASE_URL").unwrap_or_else(|_| "https://api.openai.com/v1".into());
        let has_key = std::env::var("EXECUTOR_API_KEY")
            .or_else(|_| std::env::var("OPENAI_API_KEY"))
            .is_ok();
        if has_key {
            println!("OpenAI-compat ({base})");
        } else {
            println!("OpenAI-compat (NO API KEY!)");
            all_ok = false;
        }
    } else {
        println!("Anthropic (default)");
    }

    // Check 1: API auth
    let auth_status = check_auth_status();
    println!("  API auth:     {auth_status}");
    if auth_status == "NOT FOUND" && executor_provider != "openai" { all_ok = false; }

    // Check 2: Skills directory + discovered skills
    let skills_dir = dirs_claude_skills();
    print!("  Skills dir:   ");
    if skills_dir.exists() {
        // Count actual skills (dirs with SKILL.md)
        let skill_count = fs::read_dir(&skills_dir)
            .map(|entries| {
                entries
                    .filter_map(Result::ok)
                    .filter(|e| e.path().join("SKILL.md").exists())
                    .count()
            })
            .unwrap_or(0);
        println!("OK ({skill_count} skills in {})", skills_dir.display());
    } else {
        println!("MISSING ({})", skills_dir.display());
        all_ok = false;
    }

    // Check 2b: Reviewer API (LlmReview)
    print!("  Reviewer API: ");
    if std::env::var("GEMINI_API_KEY").is_ok() {
        println!("OK (Gemini)");
    } else if std::env::var("OPENAI_API_KEY").is_ok() {
        println!("OK (OpenAI)");
    } else {
        println!("NOT FOUND (set GEMINI_API_KEY or OPENAI_API_KEY for LlmReview)");
    }

    // Check 3: Codex CLI
    print!("  Codex CLI:    ");
    match which_codex() {
        Some(path) => println!("OK ({})", path.display()),
        None => { println!("NOT FOUND (optional)"); }
    }

    // Check 4: Codex MCP in config
    print!("  Codex MCP:    ");
    let home = runtime::home_dir();
    let config_path = PathBuf::from(&home).join(".claude.json");
    if config_path.exists() {
        if let Ok(content) = fs::read_to_string(&config_path) {
            if let Ok(config) = serde_json::from_str::<serde_json::Value>(&content) {
                if config.get("mcpServers")
                    .and_then(|s| s.as_object())
                    .map_or(false, |s| s.contains_key("codex"))
                {
                    println!("OK (configured in ~/.claude.json)");
                } else {
                    println!("NOT CONFIGURED (run `aris setup`)");
                }
            } else {
                println!("ERROR (invalid ~/.claude.json)");
            }
        } else {
            println!("ERROR (cannot read ~/.claude.json)");
        }
    } else {
        println!("NOT CONFIGURED (no ~/.claude.json)");
    }

    println!();
    if all_ok {
        println!("All checks passed.");
    } else {
        println!("Some checks failed. Run `aris setup` to fix.");
    }
    Ok(())
}

/// ARIS-specific skills directory (highest priority).
fn dirs_aris_skills() -> PathBuf {
    let home = runtime::home_dir();
    PathBuf::from(home).join(".config").join("aris").join("skills")
}

/// Claude Code user skills directory.
fn dirs_claude_skills() -> PathBuf {
    let home = runtime::home_dir();
    PathBuf::from(home).join(".claude").join("skills")
}

/// All skill search directories in priority order.
fn skill_search_dirs() -> Vec<PathBuf> {
    let mut dirs = vec![dirs_aris_skills(), dirs_claude_skills()];
    if let Ok(cwd) = env::current_dir() {
        dirs.push(cwd.join(".claude").join("skills"));
    }
    dirs
}

/// Find skill content by name, checking all sources in priority order.
fn find_skill_content(name: &str) -> Option<String> {
    // Check filesystem dirs first (ARIS > Claude > project)
    for dir in skill_search_dirs() {
        let path = dir.join(name).join("SKILL.md");
        if let Ok(content) = fs::read_to_string(&path) {
            return Some(content);
        }
    }
    // Fallback to bundled
    runtime::BUNDLED_SKILLS
        .iter()
        .find(|(n, _)| n.eq_ignore_ascii_case(name))
        .map(|(_, content)| (*content).to_string())
}

fn which_codex() -> Option<PathBuf> {
    let output = Command::new("which").arg("codex").output().ok()?;
    if output.status.success() {
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if path.is_empty() { None } else { Some(PathBuf::from(path)) }
    } else {
        None
    }
}

/// Check if a name matches a known skill in any search root.
fn is_known_skill(name: &str) -> bool {
    for dir in skill_search_dirs() {
        if dir.join(name).join("SKILL.md").exists() {
            return true;
        }
    }
    runtime::BUNDLED_SKILLS
        .iter()
        .any(|(skill_name, _)| skill_name.eq_ignore_ascii_case(name))
}

/// Discover all skills with source info: (name, description, source_label).
fn discover_all_skills() -> Vec<(String, String, &'static str)> {
    let mut seen = std::collections::HashSet::new();
    let mut result = Vec::new();

    // ARIS user skills
    if let Ok(entries) = fs::read_dir(dirs_aris_skills()) {
        for entry in entries.flatten() {
            let skill_md = entry.path().join("SKILL.md");
            if !skill_md.exists() {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_string();
            if seen.insert(name.clone()) {
                let desc = fs::read_to_string(&skill_md)
                    .ok()
                    .and_then(|c| parse_skill_description(&c))
                    .unwrap_or_default();
                result.push((name, desc, "aris"));
            }
        }
    }

    // Claude Code user skills
    if let Ok(entries) = fs::read_dir(dirs_claude_skills()) {
        for entry in entries.flatten() {
            let skill_md = entry.path().join("SKILL.md");
            if !skill_md.exists() {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_string();
            if seen.insert(name.clone()) {
                let desc = fs::read_to_string(&skill_md)
                    .ok()
                    .and_then(|c| parse_skill_description(&c))
                    .unwrap_or_default();
                result.push((name, desc, "user"));
            }
        }
    }

    // Bundled skills
    for (name, content) in runtime::BUNDLED_SKILLS {
        let name = (*name).to_string();
        if seen.insert(name.clone()) {
            let desc = parse_skill_description(content).unwrap_or_default();
            result.push((name, desc, "bundled"));
        }
    }

    result.sort_by(|a, b| a.0.cmp(&b.0));
    result
}

#[cfg(test)]
mod tests {
    use super::{
        filter_tool_specs, format_compact_report, format_cost_report, format_model_report,
        format_model_switch_report, format_permissions_report, format_permissions_switch_report,
        format_resume_report, format_status_report, format_tool_call_start, format_tool_result,
        normalize_permission_mode, parse_args, parse_git_status_metadata, print_help_to,
        push_output_block, render_config_report, render_memory_report, render_repl_help,
        resolve_model_alias, response_to_events, resume_supported_slash_commands, status_context,
        CliAction, CliOutputFormat, SlashCommand, StatusUsage, DEFAULT_MODEL,
    };
    use api::{MessageResponse, OutputContentBlock, Usage};
    use runtime::{AssistantEvent, ContentBlock, ConversationMessage, MessageRole, PermissionMode};
    use serde_json::json;
    use std::path::PathBuf;

    #[test]
    fn defaults_to_repl_when_no_args() {
        assert_eq!(
            parse_args(&[]).expect("args should parse"),
            CliAction::Repl {
                model: DEFAULT_MODEL.to_string(),
                allowed_tools: None,
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn parses_prompt_subcommand() {
        let args = vec![
            "prompt".to_string(),
            "hello".to_string(),
            "world".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::Prompt {
                prompt: "hello world".to_string(),
                model: DEFAULT_MODEL.to_string(),
                output_format: CliOutputFormat::Text,
                allowed_tools: None,
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn parses_bare_prompt_and_json_output_flag() {
        let args = vec![
            "--output-format=json".to_string(),
            "--model".to_string(),
            "claude-opus".to_string(),
            "explain".to_string(),
            "this".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::Prompt {
                prompt: "explain this".to_string(),
                model: "claude-opus".to_string(),
                output_format: CliOutputFormat::Json,
                allowed_tools: None,
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn resolves_model_aliases_in_args() {
        let args = vec![
            "--model".to_string(),
            "opus".to_string(),
            "explain".to_string(),
            "this".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::Prompt {
                prompt: "explain this".to_string(),
                model: "claude-opus-4-6".to_string(),
                output_format: CliOutputFormat::Text,
                allowed_tools: None,
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn resolves_known_model_aliases() {
        assert_eq!(resolve_model_alias("opus"), "claude-opus-4-6");
        assert_eq!(resolve_model_alias("sonnet"), "claude-sonnet-4-6");
        assert_eq!(resolve_model_alias("haiku"), "claude-haiku-4-5-20251001");
        assert_eq!(resolve_model_alias("claude-opus"), "claude-opus");
    }

    #[test]
    fn parses_version_flags_without_initializing_prompt_mode() {
        assert_eq!(
            parse_args(&["--version".to_string()]).expect("args should parse"),
            CliAction::Version
        );
        assert_eq!(
            parse_args(&["-V".to_string()]).expect("args should parse"),
            CliAction::Version
        );
    }

    #[test]
    fn parses_permission_mode_flag() {
        let args = vec!["--permission-mode=read-only".to_string()];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::Repl {
                model: DEFAULT_MODEL.to_string(),
                allowed_tools: None,
                permission_mode: PermissionMode::ReadOnly,
            }
        );
    }

    #[test]
    fn parses_allowed_tools_flags_with_aliases_and_lists() {
        let args = vec![
            "--allowedTools".to_string(),
            "read,glob".to_string(),
            "--allowed-tools=write_file".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::Repl {
                model: DEFAULT_MODEL.to_string(),
                allowed_tools: Some(
                    ["glob_search", "read_file", "write_file"]
                        .into_iter()
                        .map(str::to_string)
                        .collect()
                ),
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn rejects_unknown_allowed_tools() {
        let error = parse_args(&["--allowedTools".to_string(), "teleport".to_string()])
            .expect_err("tool should be rejected");
        assert!(error.contains("unsupported tool in --allowedTools: teleport"));
    }

    #[test]
    fn parses_system_prompt_options() {
        let args = vec![
            "system-prompt".to_string(),
            "--cwd".to_string(),
            "/tmp/project".to_string(),
            "--date".to_string(),
            "2026-04-01".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::PrintSystemPrompt {
                cwd: PathBuf::from("/tmp/project"),
                date: "2026-04-01".to_string(),
            }
        );
    }

    #[test]
    fn parses_login_and_logout_subcommands() {
        assert_eq!(
            parse_args(&["login".to_string()]).expect("login should parse"),
            CliAction::Login
        );
        assert_eq!(
            parse_args(&["logout".to_string()]).expect("logout should parse"),
            CliAction::Logout
        );
        assert_eq!(
            parse_args(&["init".to_string()]).expect("init should parse"),
            CliAction::Init
        );
    }

    #[test]
    fn parses_resume_flag_with_slash_command() {
        let args = vec![
            "--resume".to_string(),
            "session.json".to_string(),
            "/compact".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::ResumeSession {
                session_path: PathBuf::from("session.json"),
                commands: vec!["/compact".to_string()],
            }
        );
    }

    #[test]
    fn parses_resume_flag_with_multiple_slash_commands() {
        let args = vec![
            "--resume".to_string(),
            "session.json".to_string(),
            "/status".to_string(),
            "/compact".to_string(),
            "/cost".to_string(),
        ];
        assert_eq!(
            parse_args(&args).expect("args should parse"),
            CliAction::ResumeSession {
                session_path: PathBuf::from("session.json"),
                commands: vec![
                    "/status".to_string(),
                    "/compact".to_string(),
                    "/cost".to_string(),
                ],
            }
        );
    }

    #[test]
    fn filtered_tool_specs_respect_allowlist() {
        let allowed = ["read_file", "grep_search"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let filtered = filter_tool_specs(Some(&allowed));
        let names = filtered
            .into_iter()
            .map(|spec| spec.name)
            .collect::<Vec<_>>();
        assert_eq!(names, vec!["read_file", "grep_search"]);
    }

    #[test]
    fn shared_help_uses_resume_annotation_copy() {
        let help = commands::render_slash_command_help();
        assert!(help.contains("Slash commands"));
        assert!(help.contains("works with --resume SESSION.json"));
    }

    #[test]
    fn repl_help_includes_shared_commands_and_exit() {
        let help = render_repl_help();
        assert!(help.contains("REPL"));
        assert!(help.contains("/help"));
        assert!(help.contains("/status"));
        assert!(help.contains("/model [model]"));
        assert!(help.contains("/permissions [read-only|workspace-write|danger-full-access]"));
        assert!(help.contains("/clear [--confirm]"));
        assert!(help.contains("/cost"));
        assert!(help.contains("/resume <session-path>"));
        assert!(help.contains("/config [env|hooks|model]"));
        assert!(help.contains("/memory"));
        assert!(help.contains("/init"));
        assert!(help.contains("/diff"));
        assert!(help.contains("/version"));
        assert!(help.contains("/export [file]"));
        assert!(help.contains("/session [list|switch <session-id>]"));
        assert!(help.contains("/exit"));
    }

    #[test]
    fn resume_supported_command_list_matches_expected_surface() {
        let names = resume_supported_slash_commands()
            .into_iter()
            .map(|spec| spec.name)
            .collect::<Vec<_>>();
        assert_eq!(
            names,
            vec![
                "help", "status", "compact", "clear", "cost", "config", "memory", "init", "diff",
                "version", "export",
            ]
        );
    }

    #[test]
    fn resume_report_uses_sectioned_layout() {
        let report = format_resume_report("session.json", 14, 6);
        assert!(report.contains("Session resumed"));
        assert!(report.contains("Session file     session.json"));
        assert!(report.contains("Messages         14"));
        assert!(report.contains("Turns            6"));
    }

    #[test]
    fn compact_report_uses_structured_output() {
        let compacted = format_compact_report(8, 5, false);
        assert!(compacted.contains("Compact"));
        assert!(compacted.contains("Result           compacted"));
        assert!(compacted.contains("Messages removed 8"));
        let skipped = format_compact_report(0, 3, true);
        assert!(skipped.contains("Result           skipped"));
    }

    #[test]
    fn cost_report_uses_sectioned_layout() {
        let report = format_cost_report(runtime::TokenUsage {
            input_tokens: 20,
            output_tokens: 8,
            cache_creation_input_tokens: 3,
            cache_read_input_tokens: 1,
        });
        assert!(report.contains("Cost"));
        assert!(report.contains("Input tokens     20"));
        assert!(report.contains("Output tokens    8"));
        assert!(report.contains("Cache create     3"));
        assert!(report.contains("Cache read       1"));
        assert!(report.contains("Total tokens     32"));
    }

    #[test]
    fn permissions_report_uses_sectioned_layout() {
        let report = format_permissions_report("workspace-write");
        assert!(report.contains("Permissions"));
        assert!(report.contains("Active mode      workspace-write"));
        assert!(report.contains("Modes"));
        assert!(report.contains("read-only          ○ available Read/search tools only"));
        assert!(report.contains("workspace-write    ● current   Edit files inside the workspace"));
        assert!(report.contains("danger-full-access ○ available Unrestricted tool access"));
    }

    #[test]
    fn permissions_switch_report_is_structured() {
        let report = format_permissions_switch_report("read-only", "workspace-write");
        assert!(report.contains("Permissions updated"));
        assert!(report.contains("Result           mode switched"));
        assert!(report.contains("Previous mode    read-only"));
        assert!(report.contains("Active mode      workspace-write"));
        assert!(report.contains("Applies to       subsequent tool calls"));
    }

    #[test]
    fn init_help_mentions_direct_subcommand() {
        let mut help = Vec::new();
        print_help_to(&mut help).expect("help should render");
        let help = String::from_utf8(help).expect("help should be utf8");
        assert!(help.contains("aris init"));
    }

    #[test]
    fn model_report_uses_sectioned_layout() {
        let report = format_model_report("claude-sonnet", 12, 4);
        assert!(report.contains("Model"));
        assert!(report.contains("Current model    claude-sonnet"));
        assert!(report.contains("Session messages 12"));
        assert!(report.contains("Switch models with /model <name>"));
    }

    #[test]
    fn model_switch_report_preserves_context_summary() {
        let report = format_model_switch_report("claude-sonnet", "claude-opus", 9);
        assert!(report.contains("Model updated"));
        assert!(report.contains("Previous         claude-sonnet"));
        assert!(report.contains("Current          claude-opus"));
        assert!(report.contains("Preserved msgs   9"));
    }

    #[test]
    fn status_line_reports_model_and_token_totals() {
        let status = format_status_report(
            "claude-sonnet",
            StatusUsage {
                message_count: 7,
                turns: 3,
                latest: runtime::TokenUsage {
                    input_tokens: 5,
                    output_tokens: 4,
                    cache_creation_input_tokens: 1,
                    cache_read_input_tokens: 0,
                },
                cumulative: runtime::TokenUsage {
                    input_tokens: 20,
                    output_tokens: 8,
                    cache_creation_input_tokens: 2,
                    cache_read_input_tokens: 1,
                },
                estimated_tokens: 128,
            },
            "workspace-write",
            &super::StatusContext {
                cwd: PathBuf::from("/tmp/project"),
                session_path: Some(PathBuf::from("session.json")),
                loaded_config_files: 2,
                discovered_config_files: 3,
                memory_file_count: 4,
                project_root: Some(PathBuf::from("/tmp")),
                git_branch: Some("main".to_string()),
            },
        );
        assert!(status.contains("Status"));
        assert!(status.contains("Model            claude-sonnet"));
        assert!(status.contains("Permission mode  workspace-write"));
        assert!(status.contains("Messages         7"));
        assert!(status.contains("Latest total     10"));
        assert!(status.contains("Cumulative total 31"));
        assert!(status.contains("Cwd              /tmp/project"));
        assert!(status.contains("Project root     /tmp"));
        assert!(status.contains("Git branch       main"));
        assert!(status.contains("Session          session.json"));
        assert!(status.contains("Config files     loaded 2/3"));
        assert!(status.contains("Memory files     4"));
    }

    #[test]
    fn config_report_supports_section_views() {
        let report = render_config_report(Some("env")).expect("config report should render");
        assert!(report.contains("Merged section: env"));
    }

    #[test]
    fn memory_report_uses_sectioned_layout() {
        let report = render_memory_report().expect("memory report should render");
        assert!(report.contains("Memory"));
        assert!(report.contains("Working directory"));
        assert!(report.contains("Instruction files"));
        assert!(report.contains("Discovered files"));
    }

    #[test]
    fn config_report_uses_sectioned_layout() {
        let report = render_config_report(None).expect("config report should render");
        assert!(report.contains("Config"));
        assert!(report.contains("Discovered files"));
        assert!(report.contains("Merged JSON"));
    }

    #[test]
    fn parses_git_status_metadata() {
        let (root, branch) = parse_git_status_metadata(Some(
            "## rcc/cli...origin/rcc/cli
 M src/main.rs",
        ));
        assert_eq!(branch.as_deref(), Some("rcc/cli"));
        let _ = root;
    }

    #[test]
    fn status_context_reads_real_workspace_metadata() {
        let context = status_context(None).expect("status context should load");
        assert!(context.cwd.is_absolute());
        assert_eq!(context.discovered_config_files, 5);
        assert!(context.loaded_config_files <= context.discovered_config_files);
    }

    #[test]
    fn normalizes_supported_permission_modes() {
        assert_eq!(normalize_permission_mode("read-only"), Some("read-only"));
        assert_eq!(
            normalize_permission_mode("workspace-write"),
            Some("workspace-write")
        );
        assert_eq!(
            normalize_permission_mode("danger-full-access"),
            Some("danger-full-access")
        );
        assert_eq!(normalize_permission_mode("unknown"), None);
    }

    #[test]
    fn clear_command_requires_explicit_confirmation_flag() {
        assert_eq!(
            SlashCommand::parse("/clear"),
            Some(SlashCommand::Clear { confirm: false })
        );
        assert_eq!(
            SlashCommand::parse("/clear --confirm"),
            Some(SlashCommand::Clear { confirm: true })
        );
    }

    #[test]
    fn parses_resume_and_config_slash_commands() {
        assert_eq!(
            SlashCommand::parse("/resume saved-session.json"),
            Some(SlashCommand::Resume {
                session_path: Some("saved-session.json".to_string())
            })
        );
        assert_eq!(
            SlashCommand::parse("/clear --confirm"),
            Some(SlashCommand::Clear { confirm: true })
        );
        assert_eq!(
            SlashCommand::parse("/config"),
            Some(SlashCommand::Config { section: None })
        );
        assert_eq!(
            SlashCommand::parse("/config env"),
            Some(SlashCommand::Config {
                section: Some("env".to_string())
            })
        );
        assert_eq!(SlashCommand::parse("/memory"), Some(SlashCommand::Memory));
        assert_eq!(SlashCommand::parse("/init"), Some(SlashCommand::Init));
    }

    #[test]
    fn init_template_mentions_detected_rust_workspace() {
        let rendered = crate::init::render_init_claude_md(std::path::Path::new("."));
        assert!(rendered.contains("# CLAUDE.md"));
        assert!(rendered.contains("cargo clippy --workspace --all-targets -- -D warnings"));
    }

    #[test]
    fn converts_tool_roundtrip_messages() {
        let messages = vec![
            ConversationMessage::user_text("hello"),
            ConversationMessage::assistant(vec![ContentBlock::ToolUse {
                id: "tool-1".to_string(),
                name: "bash".to_string(),
                input: "{\"command\":\"pwd\"}".to_string(),
            }]),
            ConversationMessage {
                role: MessageRole::Tool,
                blocks: vec![ContentBlock::ToolResult {
                    tool_use_id: "tool-1".to_string(),
                    tool_name: "bash".to_string(),
                    output: "ok".to_string(),
                    is_error: false,
                }],
                usage: None,
            },
        ];

        let converted = super::convert_messages(&messages);
        assert_eq!(converted.len(), 3);
        assert_eq!(converted[1].role, "assistant");
        assert_eq!(converted[2].role, "user");
    }
    #[test]
    fn repl_help_mentions_history_completion_and_multiline() {
        let help = render_repl_help();
        assert!(help.contains("Up/Down"));
        assert!(help.contains("Tab"));
        assert!(help.contains("Shift+Enter/Ctrl+J"));
    }

    #[test]
    fn tool_rendering_helpers_compact_output() {
        let start = format_tool_call_start("read_file", r#"{"path":"src/main.rs"}"#);
        assert!(start.contains("read_file"));
        assert!(start.contains("src/main.rs"));

        let done = format_tool_result(
            "read_file",
            r#"{"file":{"filePath":"src/main.rs","content":"hello","numLines":1,"startLine":1,"totalLines":1}}"#,
            false,
        );
        assert!(done.contains("📄 Read src/main.rs"));
        assert!(done.contains("hello"));
    }

    #[test]
    fn push_output_block_renders_markdown_text() {
        let mut out = Vec::new();
        let mut events = Vec::new();
        let mut pending_tool = None;

        push_output_block(
            OutputContentBlock::Text {
                text: "# Heading".to_string(),
            },
            &mut out,
            &mut events,
            &mut pending_tool,
            false,
        )
        .expect("text block should render");

        let rendered = String::from_utf8(out).expect("utf8");
        assert!(rendered.contains("Heading"));
        assert!(rendered.contains('\u{1b}'));
    }

    #[test]
    fn push_output_block_skips_empty_object_prefix_for_tool_streams() {
        let mut out = Vec::new();
        let mut events = Vec::new();
        let mut pending_tool = None;

        push_output_block(
            OutputContentBlock::ToolUse {
                id: "tool-1".to_string(),
                name: "read_file".to_string(),
                input: json!({}),
            },
            &mut out,
            &mut events,
            &mut pending_tool,
            true,
        )
        .expect("tool block should accumulate");

        assert!(events.is_empty());
        assert_eq!(
            pending_tool,
            Some(("tool-1".to_string(), "read_file".to_string(), String::new(),))
        );
    }

    #[test]
    fn response_to_events_preserves_empty_object_json_input_outside_streaming() {
        let mut out = Vec::new();
        let events = response_to_events(
            MessageResponse {
                id: "msg-1".to_string(),
                kind: "message".to_string(),
                model: "claude-opus-4-6".to_string(),
                role: "assistant".to_string(),
                content: vec![OutputContentBlock::ToolUse {
                    id: "tool-1".to_string(),
                    name: "read_file".to_string(),
                    input: json!({}),
                }],
                stop_reason: Some("tool_use".to_string()),
                stop_sequence: None,
                usage: Usage {
                    input_tokens: 1,
                    output_tokens: 1,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                },
                request_id: None,
            },
            &mut out,
        )
        .expect("response conversion should succeed");

        assert!(matches!(
            &events[0],
            AssistantEvent::ToolUse { name, input, .. }
                if name == "read_file" && input == "{}"
        ));
    }

    #[test]
    fn response_to_events_preserves_non_empty_json_input_outside_streaming() {
        let mut out = Vec::new();
        let events = response_to_events(
            MessageResponse {
                id: "msg-2".to_string(),
                kind: "message".to_string(),
                model: "claude-opus-4-6".to_string(),
                role: "assistant".to_string(),
                content: vec![OutputContentBlock::ToolUse {
                    id: "tool-2".to_string(),
                    name: "read_file".to_string(),
                    input: json!({ "path": "rust/Cargo.toml" }),
                }],
                stop_reason: Some("tool_use".to_string()),
                stop_sequence: None,
                usage: Usage {
                    input_tokens: 1,
                    output_tokens: 1,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                },
                request_id: None,
            },
            &mut out,
        )
        .expect("response conversion should succeed");

        assert!(matches!(
            &events[0],
            AssistantEvent::ToolUse { name, input, .. }
                if name == "read_file" && input == "{\"path\":\"rust/Cargo.toml\"}"
        ));
    }
}
