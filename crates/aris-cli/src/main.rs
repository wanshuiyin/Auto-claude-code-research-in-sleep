mod config;
mod history;
mod init;
mod input;
mod memories;
mod meta_optimize;
mod openai_compat;
mod openai_executor;
mod render;

/// Crate-wide test lock for any test that mutates process-global env vars
/// (`EXECUTOR_*` / `OPENAI_API_KEY` / `ANTHROPIC_*`). A SINGLE lock shared
/// across the `config` and `openai_executor` test modules so their
/// env-mutating characterization tests cannot race in a parallel
/// `cargo test` (codex Phase-0 gap #1). Poison-tolerant guard helper so one
/// panicking test does not cascade-poison the rest.
#[cfg(test)]
pub(crate) static ENV_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[cfg(test)]
pub(crate) fn env_test_guard() -> std::sync::MutexGuard<'static, ()> {
    let guard = ENV_TEST_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    scrub_proxy_env_for_tests();
    guard
}

/// v0.4.23: tests that drive local mock HTTP servers through reqwest break
/// under a developer shell's http(s)_proxy (127.0.0.1 gets routed through the
/// proxy → 502; observed live on a released tag). Scrub once per process —
/// no test needs a proxy and the test-process env is disposable.
#[cfg(test)]
pub(crate) fn scrub_proxy_env_for_tests() {
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

use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::rc::Rc;
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
use tools::{
    execute_tool, mcp_tool_specs, mvp_tool_specs, McpToolCatalog, RuntimeToolSpec, ToolSpec,
};

/// v0.4.24: ordered availability chain for the built-in default model. On the
/// precise "model unavailable on this account" failure (404
/// `not_found_error`), a non-explicit session walks FORWARD through this
/// chain — Opus 5 → Opus 4.8 → Opus 4.7 — one step per failed request,
/// warning each time. Strictly-forward stepping replaces the v0.4.18
/// single-hop latch: no retry loop is possible (the walk terminates at the
/// last entry), and the v0.4.18 guarantee is preserved for accounts with only
/// 4.7 access AND for configs saved by older versions whose `executor_model`
/// is a former default (e.g. `claude-opus-4-8` written by v0.4.23's setup).
const DEFAULT_MODEL_CHAIN: [&str; 3] = ["claude-opus-5", "claude-opus-4-8", "claude-opus-4-7"];
const DEFAULT_MODEL: &str = DEFAULT_MODEL_CHAIN[0];

/// v0.4.24: the chain entry after `current`, or `None` when `current` is not
/// a chain member (a model the user explicitly named never silently changes)
/// or is the chain's last entry (nothing left to fall back to).
fn next_default_fallback(current: &str) -> Option<&'static str> {
    let position = DEFAULT_MODEL_CHAIN
        .iter()
        .position(|model| *model == current)?;
    DEFAULT_MODEL_CHAIN.get(position + 1).copied()
}
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
const DEFAULT_OAUTH_CALLBACK_PORT: u16 = 4545;
const VERSION: &str = env!("CARGO_PKG_VERSION");
const BUILD_TARGET: Option<&str> = option_env!("TARGET");
/// Compile date injected by build.rs (`date '+%Y-%m-%d'` on Unix; "unknown"
/// fallback on platforms without date(1)). Replaces the legacy `DEFAULT_DATE`
/// const that survived v0.4.6's system-prompt-date fix (v0.4.6 only touched
/// ProjectContext::current_date, not the --version surface).
const BUILD_DATE: &str = match option_env!("ARIS_BUILD_DATE") {
    Some(d) if !d.is_empty() => d,
    _ => "unknown",
};
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
    let openai_selected = std::env::var("EXECUTOR_PROVIDER").ok().as_deref() == Some("openai");

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
        let has_refresh = token
            .refresh_token
            .as_deref()
            .is_some_and(|s| !s.is_empty());
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
    // Materialise bundled skill helpers into ~/.config/aris/cache/<version>/
    // and set ARIS_CACHE_DIR so SKILL.md resolver chains + bash subprocesses can
    // find helpers via a stable path. Must run BEFORE any other init that may
    // spawn child processes. See idea-stage/v0.4.8/T1_cache_design.md.
    let report = runtime::extract_bundle();
    if let Some(dir) = &report.used_dir {
        // Forward-slash normalise on Windows so SKILL.md bash blocks (POSIX
        // shell under git-bash / WSL) and the T6 resolver preamble see the
        // same shape. Rust + Windows API accept `/` in paths, so fs ops still
        // work; only the env var representation changes.
        let dir_str = dir.display().to_string().replace('\\', "/");
        env::set_var("ARIS_CACHE_DIR", dir_str);
    } else {
        env::remove_var("ARIS_CACHE_DIR");
    }
    if report.hard_error {
        eprintln!(
            "warning: bundled helper extraction failed at all locations ({}). \
             Skills that depend on bundled helpers may not work; see fallback chain.",
            report.paths_tried.join(", ")
        );
    } else if !report.failed.is_empty() {
        eprintln!(
            "warning: {} bundled helper(s) failed to extract; see SkillOutput.helperReport for details.",
            report.failed.len()
        );
    }

    // Load saved ARIS config and apply to env (env vars always take priority)
    let saved_config = config::ArisConfig::load();
    saved_config.apply_to_env();
    // v0.4.18 (#259) → v0.4.22 (C7): surface a silently-ignored / misplaced /
    // partially-ignored ARIS config so the user isn't left wondering why their
    // settings had no effect. Stderr only, so `--print` / JSON stdout stays
    // clean; empty on the normal no-config first run (never nags new users).
    // Problems and Warnings both print here; only doctor distinguishes them.
    for diag in config::ArisConfig::diagnose_misconfig() {
        match diag {
            config::ConfigDiagnostic::Problem(hint) => {
                eprintln!("\x1b[33mwarning:\x1b[0m {hint}");
            }
            config::ConfigDiagnostic::Warning(hint) => {
                eprintln!("\x1b[33mnote:\x1b[0m {hint}");
            }
        }
    }
    init_aris_tasks_env();

    let args: Vec<String> = env::args().skip(1).collect();
    let action = parse_args(&args)?;

    // For REPL and Prompt modes: if no executor auth is available, run setup first.
    // Must mirror the real auth resolution in resolve_openai_executor_config() +
    // api::resolve_startup_auth_source() — otherwise a user whose auth DOES work
    // (shell env var or saved OAuth credentials) would be wrongly routed through
    // setup, and force_apply_to_env() would erase their shell-provided key.
    let needs_api_key = matches!(action, CliAction::Repl { .. } | CliAction::Prompt { .. });
    let mut saved_config = saved_config;
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
        // v0.4.22 (C2, gate round-2 BLOCKER): the wizard's config is the
        // ACTIVE config from here on. Without this, resolve_startup_model
        // below still read the pre-wizard saved_config — a clean first run
        // that just configured an OpenAI-family executor immediately failed
        // "no model configured" (the model it had just saved was invisible),
        // and an anthropic-compat first run could adopt a stale model.
        saved_config = adopt_wizard_config(saved_config, Some(new_config));
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
        } =>
        // v0.4.17 (T5): one-shot `--print`/prompt is non-interactive, so MCP
        // approval may NOT prompt (untrusted MCP calls are denied here).
        {
            // v0.4.20 (#1) → v0.4.22 (C1/C2): shared startup model resolution —
            // explicit --model wins; the saved model applies only on a matching
            // provider family; OpenAI transport with no model source fails fast.
            let (model, model_source) = resolve_startup_model(model, &saved_config)?;
            LiveCli::new(
                model,
                model_source,
                true,
                allowed_tools,
                permission_mode,
                false,
            )?
            .run_turn_with_output(&prompt, output_format)?;
        }
        CliAction::Login => run_login()?,
        CliAction::Logout => run_logout()?,
        CliAction::Init => run_init()?,
        CliAction::Repl {
            model,
            allowed_tools,
            permission_mode,
        } => {
            // v0.4.20 (#1) → v0.4.22 (C1/C2): shared with the one-shot Prompt
            // path via resolve_startup_model.
            let (model, model_source) = resolve_startup_model(model, &saved_config)?;
            run_repl(model, model_source, allowed_tools, permission_mode)?;
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
        /// v0.4.22 (C1): the RAW `--model` value, `None` when the flag was not
        /// passed. Alias resolution happens exactly once, AFTER the final
        /// provider env is settled (post-wizard), in `resolve_startup_model`.
        model: Option<String>,
        output_format: CliOutputFormat,
        allowed_tools: Option<AllowedToolSet>,
        permission_mode: PermissionMode,
    },
    Login,
    Logout,
    Init,
    Repl {
        /// v0.4.22 (C1): raw `--model` value; see `CliAction::Prompt::model`.
        model: Option<String>,
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
    // v0.4.22 (C1): None = --model not passed. The raw value is preserved
    // verbatim (no alias resolution here — the wizard can still change
    // EXECUTOR_PROVIDER after parsing, and resolve_model_alias reads it).
    let mut model: Option<String> = None;
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
                model = Some(value.clone());
                index += 2;
            }
            flag if flag.starts_with("--model=") => {
                model = Some(flag[8..].to_string());
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
                    // v0.4.22 (C1): raw value; the (single) alias resolution
                    // happens in resolve_startup_model after the final env.
                    model,
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

/// v0.4.22 (C1): where the session's model came from. Decides whether the
/// saved executor model applies and whether the v0.4.18 availability fallback
/// (a forward walk over `DEFAULT_MODEL_CHAIN`) is allowed to fire.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ModelSource {
    /// `--model` on the command line — a reproducibility contract; never
    /// silently substituted (neither by the saved model nor by the
    /// availability fallback, even when it names the default id).
    CliExplicit,
    /// Chosen interactively via `/model` in the REPL — same contract as
    /// `CliExplicit`.
    ReplExplicit,
    /// Adopted from the saved `aris setup` config (`executor_model`).
    /// The availability fallback may fire.
    Configured,
    /// Nothing requested and nothing saved → `DEFAULT_MODEL`. The
    /// availability fallback may fire.
    BuiltInDefault,
}

impl ModelSource {
    /// v0.4.22 (C1): only non-explicit sources may silently fall back
    /// along `DEFAULT_MODEL_CHAIN` on account unavailability.
    fn allows_availability_fallback(self) -> bool {
        matches!(self, Self::Configured | Self::BuiltInDefault)
    }
}

/// v0.4.20 (#1) → v0.4.22 (C1+C2): resolve the model the session should run,
/// AFTER the final provider env is settled (post `apply_to_env` + wizard).
///
/// - `requested = Some(raw)` (an explicit `--model`) wins unconditionally
///   (C1); the raw value gets its single alias resolution here.
/// - Otherwise the saved executor model applies ONLY when the saved provider's
///   transport family matches the effective transport (C2): saved
///   `None`/`anthropic`/`anthropic-compat`/unknown → the Anthropic transport;
///   saved `openai`/`custom` → the `OpenAI` transport; the effective transport
///   is `OpenAI` iff the FINAL env `EXECUTOR_PROVIDER` is exactly "openai"
///   (v0.4.21 gate semantics). A mismatched saved model previously leaked (e.g.
///   shell `EXECUTOR_PROVIDER=anthropic` + a saved `OpenAI` config sent
///   `gpt-5.5` to the Anthropic API → model-not-found).
/// - Reverse fail-fast (C2/Δ4-5): when the effective transport is `OpenAI`
///   and no model source remains (no `--model`, saved model absent/blank or
///   from the wrong family), do NOT send the Claude default id to an `OpenAI`
///   endpoint — error out asking for `--model` or `aris setup`.
fn resolve_startup_model(
    requested: Option<String>,
    saved_config: &config::ArisConfig,
) -> Result<(String, ModelSource), String> {
    if let Some(raw) = requested {
        return Ok((
            resolve_model_alias(&raw).to_string(),
            ModelSource::CliExplicit,
        ));
    }

    let effective_openai = std::env::var("EXECUTOR_PROVIDER").as_deref() == Ok("openai");
    let saved_openai_family = matches!(
        saved_config.executor_provider.as_deref(),
        Some("openai" | "custom")
    );

    // executor_model() treats blank/whitespace as absent (Δ-C2, config.rs).
    if let Some(saved_model) = saved_config.executor_model() {
        if saved_openai_family == effective_openai {
            return Ok((
                resolve_model_alias(saved_model).to_string(),
                ModelSource::Configured,
            ));
        }
    }

    if effective_openai {
        return Err(
            "the effective executor transport is OpenAI-compatible, but no model is \
             configured for it (the saved model is absent, blank, or belongs to a \
             different provider family). Refusing to send the Anthropic default model \
             to an OpenAI endpoint — pass --model <id> or run `aris setup`. Note: a \
             same-family endpoint override (e.g. a custom base URL) can still carry a \
             stale saved model; see the v0.4.22 CHANGELOG."
                .to_string(),
        );
    }

    Ok((DEFAULT_MODEL.to_string(), ModelSource::BuiltInDefault))
}

/// v0.4.22 (C2, gate round-2): the startup config seam — when the mid-launch
/// wizard ran, ITS config becomes the active one for model resolution;
/// otherwise the loaded config stands. Trivial by construction, extracted so
/// the wiring point is lockable by a test (the round-2 blocker was exactly
/// this wiring being absent).
/// v0.4.22 (Δ4-5): validate a wizard-returned config against its TARGET
/// transport BEFORE any live env/runtime mutation (the caller invokes this
/// ahead of `force_apply_to_env`, so an `Err` leaves env, runtime, model and
/// provenance untouched by construction). The wizard itself refuses blank
/// OpenAI/custom models at the executor step (Δ5-4); this is the in-session
/// belt to that suspender.
fn inline_setup_guard(new_config: &config::ArisConfig) -> Result<(), String> {
    let openai_family = matches!(
        new_config.executor_provider.as_deref(),
        Some("openai" | "custom")
    );
    if openai_family && new_config.executor_model().is_none() {
        return Err(
            "setup saved an OpenAI/custom executor without a model id; refusing to \
             switch the live session to it. Re-run /setup and enter an explicit model."
                .to_string(),
        );
    }
    Ok(())
}

fn adopt_wizard_config(
    saved: config::ArisConfig,
    wizard_result: Option<config::ArisConfig>,
) -> config::ArisConfig {
    wizard_result.unwrap_or(saved)
}

/// v0.4.22 (B5): pure three-state reviewer display (unit-testable without env).
/// (1) Codex MCP primary, no fallback → the Codex-pinned reality only.
/// (2) Codex MCP + HTTP fallback → primary first, fallback labeled as such.
/// (3) non-Codex → the HTTP reviewer model, as before.
fn reviewer_display_for(
    primary_provider: Option<&str>,
    fallback_provider: Option<&str>,
    http_reviewer_model: &str,
) -> String {
    if primary_provider == Some("codex-mcp") {
        match fallback_provider.filter(|s| !s.trim().is_empty()) {
            Some(provider) => format!(
                "Codex MCP · gpt-5.6-sol preferred (HTTP fallback: {provider} · {http_reviewer_model})"
            ),
            None => "Codex MCP · gpt-5.6-sol preferred".to_string(),
        }
    } else {
        http_reviewer_model.to_string()
    }
}

/// v0.4.22 (Δ4-3, gate round-2): the `/reviewer` command's four-state gate,
/// pure over (primary, fallback, explicit-model) so each state is lockable.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ReviewerCmdGate {
    /// Codex primary, no HTTP fallback, bare `/reviewer` → print status only.
    PureCodexStatus,
    /// Codex primary, no HTTP fallback, `/reviewer <model>` → refuse with
    /// /setup guidance (there is no HTTP reviewer to configure).
    PureCodexRefuseExplicit,
    /// Codex primary + known-provider fallback, explicit model from another
    /// family → reject (never produce fallback=gemini + model=gpt-*).
    CrossFamilyReject,
    /// Proceed (menu or accepted explicit model).
    Allow,
}

fn reviewer_command_gate(
    primary: Option<&str>,
    fallback: Option<&str>,
    explicit_model: Option<&str>,
) -> ReviewerCmdGate {
    let codex_primary = primary == Some("codex-mcp");
    let fallback = fallback.filter(|s| !s.trim().is_empty());
    if codex_primary && fallback.is_none() {
        return if explicit_model.is_some() {
            ReviewerCmdGate::PureCodexRefuseExplicit
        } else {
            ReviewerCmdGate::PureCodexStatus
        };
    }
    if codex_primary {
        if let (Some(provider), Some(model)) = (fallback, explicit_model) {
            if !reviewer_model_matches_provider(provider, model) {
                return ReviewerCmdGate::CrossFamilyReject;
            }
        }
    }
    ReviewerCmdGate::Allow
}

/// v0.4.22 (Δ4-3/Δ5-3): loose catalog-family check for `/reviewer <model>`
/// when Codex MCP is primary and the command therefore edits the HTTP
/// FALLBACK provider's model. Known providers reject obviously-cross-family
/// ids (never produce fallback=gemini + model=gpt-*); "custom" has no catalog
/// and accepts any non-blank explicit model; unknown labels are permissive.
fn reviewer_model_matches_provider(provider: &str, model: &str) -> bool {
    let m = model.trim();
    if m.is_empty() {
        return false;
    }
    let lower = m.to_ascii_lowercase();
    match provider {
        // "custom" (no catalog) and unknown labels are both permissive.
        "gemini" => lower.starts_with("gemini"),
        "openai" => lower.starts_with("gpt-") || lower.starts_with('o'),
        "glm" => lower.starts_with("glm"),
        "minimax" => lower.starts_with("minimax"),
        "kimi" => lower.starts_with("kimi") || lower.starts_with("moonshot"),
        _ => true,
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
        "fable" => "claude-fable-5",
        "opus" => "claude-opus-5",
        "sonnet" => "claude-sonnet-5",
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
            // v0.4.17 (T8): an `mcp__`-prefixed token names an MCP tool whose
            // existence is only known after runtime discovery, so it CANNOT be
            // validated against the static catalogue here. Accept it verbatim
            // (deferred validation): the advertising layer filters the MCP
            // catalogue to this allowlist (so only listed MCP tools are shown
            // to the model) and the dispatch gate in `CliToolExecutor::execute`
            // rejects any MCP name not in the allowlist. A token that names an
            // MCP tool which does not exist simply never advertises / never
            // dispatches — the same effect as an unknown static name being
            // dropped by `filter_tool_specs`. Case is preserved (MCP names are
            // case-sensitive and already normalized by the runtime); only
            // non-MCP names go through the canonical-name map below.
            if token.starts_with("mcp__") {
                allowed.insert(token.to_string());
                continue;
            }
            let normalized = normalize_tool_name(token);
            let canonical = name_map.get(&normalized).ok_or_else(|| {
                format!(
                    "unsupported tool in --allowedTools: {token} (expected one of: {}, or an mcp__<server>__<tool> name)",
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
    let mut date = runtime::today_iso();
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
    model_source: ModelSource,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
) -> Result<(), Box<dyn std::error::Error>> {
    // v0.4.17 (T5): the REPL is interactive, so MCP approval may prompt.
    let mut cli = LiveCli::new(model, model_source, true, allowed_tools, permission_mode, true)?;
    let mut editor = input::LineEditor::new(
        "\x1b[38;5;74m❯\x1b[0m ",
        slash_command_completion_candidates(),
    );

    // v0.4.16 Track A (additive): seed in-memory history from the persisted
    // file (`~/.config/aris/history`) before the first read_line. Best-effort —
    // missing/corrupt file or the ARIS_NO_HISTORY kill-switch → silent empty
    // start. This only adds entries to the existing in-memory Vec.
    let history_path = history::history_path();
    editor.load_history_from(&history_path);

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
                    // v0.4.17 A5.4 — deliberately flipped in v0.4.17 (A5.4):
                    // slash commands now enter history per maintainer decision
                    // 2026-06-05. Same call shape as the free-text path below:
                    // disk append first (honors ARIS_NO_HISTORY + the
                    // disk-only secret-skip, which applies to slash entries
                    // too), then the raw untrimmed in-memory push for Up/Down
                    // and Ctrl+R. `/exit` and `/quit` break above and so stay
                    // out of history, as before.
                    history::append_entry(&history_path, &input);
                    editor.push_history(input);
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
                // v0.4.16 Track A: persist the submitted entry to disk in
                // addition to the (unchanged) in-memory push. The disk append
                // honors the ARIS_NO_HISTORY kill-switch and a disk-only
                // secret-skip; the in-memory push below is byte-identical to
                // before so session-local Up/Down behaviour is unchanged.
                history::append_entry(&history_path, &input);
                editor.push_history(input);
                // Visual separator before assistant response
                let term_w = crossterm::terminal::size()
                    .map(|(w, _)| w as usize)
                    .unwrap_or(80);
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

/// v0.4.22 (B5): the startup banner's 6 center lines — every line must be
/// EXACTLY 34 visible chars once ANSI escapes are stripped (the pixel sprites
/// on either side assume it; locked by `banner_center_lines_are_34_visible_chars`).
const BANNER_CENTER: [&str; 6] = [
    "\x1b[2m  ──────────────────────────────  \x1b[0m",
    "\x1b[1;38;5;45m       A     R     I     S        \x1b[0m",
    "\x1b[38;5;45m      Auto Research in Sleep      \x1b[0m",
    "\x1b[2m    adversarial | multi-agent     \x1b[0m",
    "  \x1b[38;5;45mClaude\x1b[0m x \x1b[38;5;71mGPT-5.6-Sol · tiered\x1b[0m   ",
    "\x1b[2m  ──────────────────────────────  \x1b[0m",
];

struct LiveCli {
    model: String,
    /// v0.4.22 (C1): provenance of `model` — gates the saved-model
    /// substitution (startup) and the availability-chain walk.
    model_source: ModelSource,
    reviewer_model: String,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
    system_prompt: Vec<String>,
    runtime: ConversationRuntime<ExecutorClient, CliToolExecutor>,
    session: SessionHandle,
    /// Plan mode state: stores original permissions/tools before entering plan mode.
    plan_mode: Option<PlanModeState>,
    /// v0.4.17 (T4/RW5): shared MCP runtime (handle + discovered tool catalog),
    /// reused across every `build_runtime` rebuild (plan-mode switches) so MCP
    /// servers are spawned/discovered exactly once. `None` when no `mcpServers`
    /// are configured.
    mcp: Option<SharedMcpRuntime>,
    /// v0.4.17 (T5): whether this CLI session may interactively prompt for MCP
    /// tool approval. `true` for the interactive REPL; `false` for one-shot
    /// `--print` / JSON output (where an untrusted MCP call is denied rather
    /// than silently run). Threaded into every `build_runtime` so plan-mode
    /// rebuilds keep the same posture.
    may_prompt: bool,
}

#[derive(Debug, Clone)]
struct PlanModeState {
    previous_permission_mode: PermissionMode,
    previous_allowed_tools: Option<AllowedToolSet>,
}

impl LiveCli {
    fn new(
        model: String,
        model_source: ModelSource,
        enable_tools: bool,
        allowed_tools: Option<AllowedToolSet>,
        permission_mode: PermissionMode,
        may_prompt: bool,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let system_prompt = build_system_prompt(Some(&model))?;
        let session = create_managed_session_handle()?;
        // v0.4.17 (RW5): eager MCP discovery once at startup. None when no
        // mcpServers are configured (no-MCP path unchanged).
        let mcp = build_shared_mcp_runtime();
        let runtime = build_runtime(
            Session::new(),
            model.clone(),
            system_prompt.clone(),
            enable_tools,
            true,
            allowed_tools.clone(),
            permission_mode,
            mcp.clone(),
            may_prompt,
        )?;
        // Determine the default HTTP reviewer model (this is the LlmReview /
        // HTTP-fallback STATE, exported as ARIS_REVIEWER_MODEL — NOT a display
        // string; the Codex-MCP primary is described separately by
        // reviewer_display, Δ4-2). saved_config.apply_to_env() runs BEFORE
        // this point in run(), so a persisted reviewer_model is read back via
        // the env var. The fallback only fires when nothing was persisted.
        //
        // v0.4.8 → v0.4.22 (Δ4-2/Δ5-3): when the EFFECTIVE reviewer provider
        // is Custom — either primary "custom" OR "codex-mcp" with
        // reviewer_fallback_provider "custom" — don't inject gpt-5.5 (surely
        // wrong for a custom proxy). The rule is the provider formula ONLY;
        // never inferred from ARIS_REVIEWER_AUTH_TOKEN presence (credential
        // errors and missing models must fail loud separately).
        let reviewer_primary = std::env::var("ARIS_REVIEWER_PROVIDER").ok();
        let reviewer_fallback = std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER").ok();
        let effective_custom_reviewer = reviewer_primary.as_deref() == Some("custom")
            || (reviewer_primary.as_deref() == Some("codex-mcp")
                && reviewer_fallback.as_deref() == Some("custom"));
        let reviewer_model = std::env::var("ARIS_REVIEWER_MODEL")
            .ok()
            .filter(|s| !s.trim().is_empty())
            .unwrap_or_else(|| {
                if effective_custom_reviewer {
                    eprintln!(
                        "\x1b[33mwarning:\x1b[0m custom reviewer provider configured but \
                         model name is empty in config. Run /setup or /reviewer <model-name>."
                    );
                    String::new()
                } else if std::env::var("GEMINI_API_KEY").is_ok() {
                    "gemini-2.5-pro".to_string()
                } else {
                    "gpt-5.5".to_string()
                }
            });
        std::env::set_var("ARIS_REVIEWER_MODEL", &reviewer_model);
        let cli = Self {
            model,
            model_source,
            reviewer_model,
            allowed_tools,
            permission_mode,
            system_prompt,
            runtime,
            session,
            plan_mode: None,
            mcp,
            may_prompt,
        };
        cli.persist_session()?;
        Ok(cli)
    }

    /// v0.4.22 (B5/Δ4-2): honest three-state reviewer description. The HTTP
    /// model (`self.reviewer_model` / ARIS_REVIEWER_MODEL) is fallback STATE,
    /// not the primary — with Codex MCP configured, presenting the HTTP model
    /// as "the Reviewer" misled users (e.g. option 10 + Gemini fallback showed
    /// "Reviewer  gemini-2.5-pro" while every skill review ran through Codex).
    fn reviewer_display(&self) -> String {
        reviewer_display_for(
            std::env::var("ARIS_REVIEWER_PROVIDER").ok().as_deref(),
            std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER")
                .ok()
                .as_deref(),
            &self.reviewer_model,
        )
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
        // (locked by test `banner_center_lines_are_34_visible_chars`)
        // 0: 2sp + 30 dashes + 2sp                              = 34
        // 1: 7sp + "A     R     I     S" (19) + 8sp             = 34
        // 2: 6sp + "Auto Research in Sleep" (22) + 6sp          = 34
        // 3: 4sp + "adversarial | multi-agent" (25) + 5sp       = 34
        // 4: 2sp + "Claude x GPT-5.6-Sol · tiered" (29) + 3sp   = 34
        //    (v0.4.22 B5: "tiered" — deep audits ultra, floor xhigh; avoids
        //     implying every review runs at one effort)
        // 5: same as 0                                          = 34
        let center = BANNER_CENTER;

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
            // Check if this is a custom provider
            let is_custom =
                config::ArisConfig::load().executor_provider.as_deref() == Some("custom");
            if is_custom {
                "Custom"
            } else {
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
                } else if base.contains("xiaomimimo") {
                    "Xiaomi"
                } else if base.contains("volces") {
                    "Doubao"
                } else {
                    "OpenAI"
                }
            }
        } else {
            "Anthropic"
        };

        let info_lines = [
            format!(
                "\x1b[2mExecutor\x1b[0m     {executor_label} · {}",
                self.model
            ),
            format!("\x1b[2mReviewer\x1b[0m     {}", self.reviewer_display()),
            format!(
                "\x1b[2mPermissions\x1b[0m  {}",
                self.permission_mode.as_str()
            ),
            format!("\x1b[2mDirectory\x1b[0m    {cwd}"),
            format!("\x1b[2mSession\x1b[0m      {}", self.session.id),
        ];

        // Box drawing
        let term_w = crossterm::terminal::size()
            .map(|(w, _)| w as usize)
            .unwrap_or(80);
        let box_w = term_w.min(76);
        let hr = "─".repeat(box_w.saturating_sub(2));
        let dim = "\x1b[38;5;240m";
        let reset = "\x1b[0m";

        let mut banner = String::new();
        // Top border with title
        banner.push_str(&format!(
            "{dim}╭─ {reset}ARIS-Code v{VERSION}{dim} {hr}{reset}\n",
            hr = "─".repeat(box_w.saturating_sub(18 + VERSION.len()))
        ));
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
        let mut stdout = io::stdout();
        // v0.4.18: snapshot the session BEFORE the turn. `ConversationRuntime::
        // run_turn` appends the user message before the API call, so a failed
        // attempt leaves `input` in `self.runtime`'s session. If we then fall
        // back, we rebuild from THIS pre-turn snapshot (not the polluted live
        // session) so the retry appends `input` exactly once — no duplicate.
        let pre_turn_session = self.runtime.session().clone();
        loop {
            let mut spinner = Spinner::new();
            spinner.tick(
                "\x1b[38;5;74m●\x1b[0m \x1b[2mThinking...\x1b[0m",
                TerminalRenderer::new().color_theme(),
                &mut stdout,
            )?;
            let mut permission_prompter = CliPermissionPrompter::new(self.permission_mode);
            let result = self.runtime.run_turn(input, Some(&mut permission_prompter));
            match result {
                Ok(summary) => {
                    let done_label = "\x1b[38;5;74m●\x1b[0m \x1b[2mDone\x1b[0m";
                    // v0.4.20 (#299): when the turn printed visible assistant
                    // text, finish WITHOUT clearing the current line (the reply
                    // lives there — `Clear(CurrentLine)` would erase a short
                    // single-line reply, leaving only "✔ Done"). Tool-only /
                    // empty turns still clear the leftover "Thinking…" line.
                    if turn_has_visible_assistant_text(&summary) {
                        spinner.finish_after_output(
                            done_label,
                            TerminalRenderer::new().color_theme(),
                            &mut stdout,
                        )?;
                    } else {
                        spinner.finish(
                            done_label,
                            TerminalRenderer::new().color_theme(),
                            &mut stdout,
                        )?;
                    }
                    println!();
                    if let Some(event) = summary.auto_compaction {
                        println!(
                            "{}",
                            format_auto_compaction_notice(event.removed_message_count)
                        );
                    }
                    self.persist_session()?;
                    return Ok(());
                }
                Err(error) => {
                    // v0.4.18: if the default model is unavailable on this
                    // account, step along DEFAULT_MODEL_CHAIN — rebuilding BOTH
                    // the runtime and the system-prompt model identity so they
                    // stay coherent — and retry (once per chain step) before
                    // surfacing the failure.
                    if self.fall_back_default_model_if_needed(&error)? {
                        spinner.finish(
                            "\x1b[33m●\x1b[0m \x1b[2mretrying with the fallback model…\x1b[0m",
                            TerminalRenderer::new().color_theme(),
                            &mut stdout,
                        )?;
                        self.runtime = build_runtime(
                            pre_turn_session.clone(),
                            self.model.clone(),
                            self.system_prompt.clone(),
                            true,
                            true,
                            self.allowed_tools.clone(),
                            self.permission_mode,
                            self.mcp.clone(),
                            self.may_prompt,
                        )?;
                        continue;
                    }
                    spinner.fail(
                        "\x1b[38;5;203m●\x1b[0m \x1b[1;31mRequest failed\x1b[0m",
                        TerminalRenderer::new().color_theme(),
                        &mut stdout,
                    )?;
                    return Err(Box::new(error));
                }
            }
        }
    }

    /// v0.4.18: when `error` is "model unavailable on this account" and the
    /// session's model has a next step in `DEFAULT_MODEL_CHAIN`, step to it,
    /// rebuild the system prompt so the model identity the model is told
    /// about stays coherent, warn, and return `true` so the caller rebuilds
    /// its runtime from the new `self.model`/`self.system_prompt` and
    /// retries. Returns `false` (no state change) otherwise — for a model
    /// outside the chain, at the chain's end, and for an explicitly-chosen
    /// model (the user owns that choice).
    ///
    /// v0.4.22 (C1): "explicitly-chosen" now includes an explicit `--model`
    /// or `/model` selection that NAMES the default id — an explicit choice is
    /// a reproducibility contract, so only `Configured`/`BuiltInDefault`
    /// sources may silently fall back (`ModelSource::allows_availability_fallback`).
    ///
    /// v0.4.24: single-hop constant + latch → forward walk over
    /// `DEFAULT_MODEL_CHAIN` (Opus 5 → 4.8 → 4.7). The walk is strictly
    /// forward, so it terminates without a latch; a saved `executor_model`
    /// naming a former default (e.g. v0.4.23's `claude-opus-4-8`) keeps its
    /// pre-existing fallback protection.
    fn fall_back_default_model_if_needed(
        &mut self,
        error: &RuntimeError,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        if !error.is_model_unavailable() || !self.model_source.allows_availability_fallback() {
            return Ok(false);
        }
        let Some(next) = next_default_fallback(&self.model) else {
            return Ok(false);
        };
        let unavailable = std::mem::replace(&mut self.model, next.to_string());
        self.system_prompt = build_system_prompt(Some(&self.model))?;
        eprintln!(
            "\x1b[33mwarning:\x1b[0m {unavailable} is not available on this account; \
             falling back to {next} for this session."
        );
        Ok(true)
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
        // v0.4.18: same default-model fallback as the text path. On a
        // "model unavailable" failure we step along DEFAULT_MODEL_CHAIN,
        // rebuild the local runtime from the new model + system prompt, and
        // retry (once per chain step).
        let summary = loop {
            let session = self.runtime.session().clone();
            let mut runtime = build_runtime(
                session,
                self.model.clone(),
                self.system_prompt.clone(),
                true,
                false,
                self.allowed_tools.clone(),
                self.permission_mode,
                self.mcp.clone(),
                // v0.4.17 (T5): JSON output path is non-interactive — never
                // prompt for MCP approval (an untrusted MCP call is denied
                // instead so the JSON stream is never polluted by a prompt).
                false,
            )?;
            // v0.4.22 (C3): the GENERIC permission gate must not prompt either.
            // Passing a real CliPermissionPrompter here printed "Permission
            // approval required" + a [y/N] read to STDOUT under
            // `--output-format json --permission-mode workspace-write` with a
            // danger-tier tool (bash) — blocking on stdin and breaking the
            // single-JSON-document contract. With `None`, permissions.rs
            // yields a clean structured Deny ("requires approval to
            // escalate…"), the tool errors, the turn continues, and stdout
            // stays exactly one JSON document.
            match runtime.run_turn(input, None) {
                Ok(summary) => {
                    self.runtime = runtime;
                    break summary;
                }
                Err(error) => {
                    if self.fall_back_default_model_if_needed(&error)? {
                        continue;
                    }
                    return Err(Box::new(error));
                }
            }
        };
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
            SlashCommand::Plan { task } => self.handle_plan_mode(task.as_deref())?,
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
                let is_custom =
                    config::ArisConfig::load().executor_provider.as_deref() == Some("custom");

                let items: Vec<input::SelectItem> = if is_custom {
                    // Custom provider: try dynamic /models fetch.
                    // v0.4.20 (#3): read the EFFECTIVE executor endpoint — the
                    // env vars the executor actually uses (set by apply_to_env;
                    // a shell override wins) — falling back to on-disk config.
                    // Previously this read ONLY the disk config, so an env
                    // override left the menu fetching from a stale endpoint (or
                    // showing "not configured") while requests went elsewhere.
                    // Mirrors resolve_openai_executor_config's resolution.
                    let cfg = config::ArisConfig::load();
                    let api_key = std::env::var("EXECUTOR_API_KEY")
                        .or_else(|_| std::env::var("OPENAI_API_KEY"))
                        .ok()
                        .filter(|s| !s.is_empty())
                        .or_else(|| cfg.executor_api_key.clone().filter(|s| !s.is_empty()))
                        .unwrap_or_default();
                    let base_url = std::env::var("EXECUTOR_BASE_URL")
                        .ok()
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty())
                        .or_else(|| cfg.executor_base_url.clone().filter(|s| !s.is_empty()))
                        .unwrap_or_default();
                    if !api_key.is_empty() && !base_url.is_empty() {
                        match openai_compat::fetch_openai_models(&base_url, &api_key) {
                            Ok(models) => openai_compat::model_select_items(&models, &self.model),
                            Err(err) => {
                                println!("\x1b[33m⚠ Could not fetch models: {err}\x1b[0m");
                                println!("  Use /model <name> to switch directly.");
                                return Ok(false);
                            }
                        }
                    } else {
                        println!("Custom provider not fully configured. Run /setup first.");
                        return Ok(false);
                    }
                } else if is_openai {
                    // OpenAI-compat mode: show common models
                    vec![
                        (
                            "gpt-5.5",
                            "OpenAI · Best intelligence at scale (xhigh reasoning)",
                        ),
                        ("gpt-5.4", "OpenAI · Previous flagship"),
                        ("gpt-5.4-mini", "OpenAI · Strong mini model"),
                        ("gpt-5.4-nano", "OpenAI · Cheapest, high-volume"),
                        ("gemini-2.5-pro", "Google · Most capable Gemini"),
                        ("gemini-2.5-flash", "Google · Fast Gemini"),
                        ("GLM-5", "Zhipu · GLM 5 latest"),
                        ("MiniMax-M2.7", "MiniMax · M2.7 latest"),
                        ("kimi-k2.5", "Kimi · K2.5 reasoning"),
                        ("mimo-v2.5-pro", "Xiaomi · MiMo v2.5 Pro"),
                        ("mimo-v2.5", "Xiaomi · MiMo v2.5"),
                        ("mimo-v2-pro", "Xiaomi · MiMo v2 Pro"),
                        ("mimo-v2-omni", "Xiaomi · MiMo v2 Omni"),
                        ("qwen3.6-plus", "Alibaba · Qwen 3.6 Plus (1M ctx)"),
                        ("qwen3.6-flash", "Alibaba · Qwen 3.6 Flash (1M ctx)"),
                        ("qwen3.6-max-preview", "Alibaba · Qwen 3.6 Max Preview"),
                        ("doubao-pro-4k", "ByteDance · Doubao Pro 4K"),
                        ("doubao-lite-4k", "ByteDance · Doubao Lite 4K"),
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
                        (
                            "claude-fable-5",
                            "Fable 5 · Frontier Mythos-class, most intelligent",
                        ),
                        ("claude-opus-5", "Opus 5 · Most capable for complex work"),
                        ("claude-sonnet-5", "Sonnet 5 · Best for everyday tasks"),
                        (
                            "claude-opus-4-8",
                            "Opus 4.8 · Previous-generation Opus",
                        ),
                        ("claude-sonnet-4-6", "Sonnet 4.6 · Previous-generation Sonnet"),
                        (
                            "claude-haiku-4-5-20251001",
                            "Haiku 4.5 · Fastest for quick answers",
                        ),
                    ]
                    .into_iter()
                    .map(|(name, desc)| input::SelectItem {
                        label: name.to_string(),
                        description: desc.to_string(),
                        is_current: self.model == name,
                    })
                    .collect()
                };

                match input::select_menu(
                    "Select executor model",
                    "Switch the model used for the main conversation.",
                    &items,
                )? {
                    Some(idx) => items[idx].label.clone(),
                    None => return Ok(false),
                }
            }
        };

        if model == self.model {
            // v0.4.22 (C1): re-selecting the CURRENT model via /model is still
            // an explicit choice — mark it so the availability fallback stops
            // firing (covers "the default fell back mid-session, user
            // explicitly re-selects the served model": the old early-return
            // kept the stale Configured/BuiltInDefault source forever).
            self.model_source = ModelSource::ReplExplicit;
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
            self.mcp.clone(),
            self.may_prompt,
        )?;
        self.system_prompt = new_system_prompt;
        self.model.clone_from(&model);
        // v0.4.22 (C1): /model is an explicit choice.
        self.model_source = ModelSource::ReplExplicit;
        println!(
            "{}",
            format_model_switch_report(&previous, &model, message_count)
        );
        Ok(true)
    }

    fn set_reviewer(&mut self, model: Option<String>) -> Result<bool, Box<dyn std::error::Error>> {
        // v0.4.22 (Δ4-3): `/reviewer` controls the HTTP (LlmReview) reviewer
        // ONLY. With Codex MCP as the primary, the skills pin gpt-5.6-sol per
        // call — this command NEVER changes that, and it must say so instead
        // of pretending to switch the reviewer.
        let primary_provider = std::env::var("ARIS_REVIEWER_PROVIDER").ok();
        let fallback_provider = std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER")
            .ok()
            .filter(|s| !s.trim().is_empty());
        let codex_primary = primary_provider.as_deref() == Some("codex-mcp");

        // v0.4.22 (Δ4-3, gate round-2): the four-state decision is the pure
        // `reviewer_command_gate` (locked by reviewer_command_gate_four_states);
        // this fn only renders the outcome.
        match reviewer_command_gate(
            primary_provider.as_deref(),
            fallback_provider.as_deref(),
            model.as_deref(),
        ) {
            ReviewerCmdGate::PureCodexStatus | ReviewerCmdGate::PureCodexRefuseExplicit => {
                // Pure Codex: no HTTP reviewer exists to configure.
                println!(
                    "\x1b[1mReviewer\x1b[0m  Codex MCP · gpt-5.6-sol preferred \
                     \x1b[2m(skill-pinned per call; deep audits ultra, floor xhigh)\x1b[0m"
                );
                if model.is_some() {
                    println!(
                        "  `/reviewer <model>` controls the HTTP fallback only, and no HTTP \
                         fallback is configured. Run /setup to add one first."
                    );
                } else {
                    println!(
                        "  \x1b[2mNo HTTP fallback configured. This picker controls the HTTP \
                         fallback only — run /setup to add one.\x1b[0m"
                    );
                }
                return Ok(false);
            }
            ReviewerCmdGate::CrossFamilyReject => {
                let provider = fallback_provider.as_deref().unwrap_or("?");
                let m = model.as_deref().unwrap_or("?");
                println!(
                    "'{m}' does not look like a \x1b[1m{provider}\x1b[0m model — your \
                     HTTP fallback provider is {provider}, and `/reviewer` changes the \
                     fallback MODEL only (primary stays Codex MCP · gpt-5.6-sol). To \
                     switch the fallback provider, run /setup."
                );
                return Ok(false);
            }
            ReviewerCmdGate::Allow => {}
        }
        // When Codex MCP is primary WITH an HTTP fallback, /reviewer edits
        // ONLY that fallback provider's model.
        let restrict_to_provider: Option<String> = if codex_primary {
            fallback_provider.clone()
        } else {
            None
        };

        let model = match model {
            Some(m) => m,
            None => {
                if let Some(provider) = restrict_to_provider.as_deref() {
                    println!(
                        "\x1b[2mPrimary reviewer: Codex MCP · gpt-5.6-sol (skill-pinned). This \
                         picker controls the HTTP fallback ({provider}) only.\x1b[0m"
                    );
                }
                let has_gemini = std::env::var("GEMINI_API_KEY").is_ok();
                let has_openai = std::env::var("OPENAI_API_KEY").is_ok();
                // Custom OpenAI-compatible reviewer (Δ5-3): effective when the
                // PRIMARY is custom, or when codex-mcp has a custom FALLBACK.
                // Determined by the provider formula only — never inferred
                // from ARIS_REVIEWER_AUTH_TOKEN presence (credential errors
                // fail loud separately in LlmReview).
                let has_custom_reviewer = primary_provider.as_deref() == Some("custom")
                    || (codex_primary && fallback_provider.as_deref() == Some("custom"));
                // Provider gate for the menu: no restriction (non-codex
                // primary) → every provider with a key; restricted → only the
                // fallback provider's catalog.
                let provider_allowed = |p: &str| {
                    restrict_to_provider
                        .as_deref()
                        .map_or(true, |only| only == p)
                };

                let mut items: Vec<input::SelectItem> = Vec::new();
                if has_gemini && provider_allowed("gemini") {
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
                if std::env::var("GLM_API_KEY").is_ok() && provider_allowed("glm") {
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
                if std::env::var("MINIMAX_API_KEY").is_ok() && provider_allowed("minimax") {
                    for (name, desc) in [
                        (
                            "MiniMax-M2.7",
                            "MiniMax · Latest, recursive self-improvement",
                        ),
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
                if std::env::var("KIMI_API_KEY").is_ok() && provider_allowed("kimi") {
                    for (name, desc) in [("kimi-k2.5", "Kimi · K2.5 reasoning")] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }
                if has_openai && provider_allowed("openai") {
                    for (name, desc) in [
                        (
                            "gpt-5.5",
                            "OpenAI · Best intelligence for reviews (xhigh reasoning)",
                        ),
                        // v0.4.22 (Δ4-1/Δ-B5): opt-in only — endpoint-listed but
                        // not yet smoked with reasoning_effort on chat-completions.
                        (
                            "gpt-5.6-sol",
                            "OpenAI · EXPERIMENTAL for HTTP reviews (unverified with reasoning_effort)",
                        ),
                        ("gpt-5.4", "OpenAI · Previous flagship"),
                        ("gpt-5.4-mini", "OpenAI · Strong and affordable"),
                        ("gpt-5.4-nano", "OpenAI · Cheapest, high-volume"),
                        ("gpt-4o", "OpenAI · Older gen, stable"),
                    ] {
                        items.push(input::SelectItem {
                            label: name.to_string(),
                            description: desc.to_string(),
                            is_current: self.reviewer_model == name,
                        });
                    }
                }

                if items.is_empty() {
                    if has_custom_reviewer {
                        // Custom provider is configured but we can't enumerate
                        // its model catalog. Show the current model and tell
                        // the user how to change it (`/reviewer <model-name>`).
                        // v0.4.22 (Δ5-3, gate round-2): a blank custom model
                        // must read "(not configured)", never a blank line;
                        // blank checks use trim().
                        let current = std::env::var("ARIS_REVIEWER_MODEL")
                            .ok()
                            .filter(|s| !s.trim().is_empty())
                            .or_else(|| {
                                Some(self.reviewer_model.clone())
                                    .filter(|s| !s.trim().is_empty())
                            })
                            .unwrap_or_else(|| "(not configured)".to_string());
                        let base_url = std::env::var("ARIS_REVIEWER_BASE_URL")
                            .ok()
                            .unwrap_or_else(|| "(not set)".to_string());
                        println!(
                            "\x1b[1mCustom reviewer configured\x1b[0m\n  Endpoint  {base_url}\n  Model     \x1b[1;32m{current}\x1b[0m"
                        );
                        println!(
                            "  \x1b[2mType '/reviewer <model-name>' to change, or '/setup' to re-enter API key / endpoint.\x1b[0m"
                        );
                        return Ok(false);
                    }
                    if let Some(provider) = restrict_to_provider.as_deref() {
                        // Codex primary + a configured fallback whose API key
                        // is missing from the env — say that, not "no key".
                        println!(
                            "HTTP fallback provider \x1b[1m{provider}\x1b[0m is configured but \
                             its API key is not present in the environment. Run /setup to \
                             re-enter it. (Primary reviewer stays Codex MCP · gpt-5.6-sol.)"
                        );
                        return Ok(false);
                    }
                    // No known API keys set — guide the user to /setup.
                    println!("No reviewer API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, or use /setup to configure a custom provider.");
                    println!("  You can also type: /reviewer <model-name>");
                    return Ok(false);
                }

                match input::select_menu(
                    "Select reviewer model",
                    "Switch the model used by LlmReview for external reviews.",
                    &items,
                )? {
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

        // v0.4.22 (Δ4-5): validate the executor model against the TARGET
        // transport BEFORE mutating the live env/runtime — the same resolver
        // the startup path uses. Without this, an OpenAI/custom setup whose
        // model somehow ended up absent would keep the stale (possibly Claude)
        // self.model and rebuild the runtime against the new OpenAI env. The
        // wizard itself now refuses blank OpenAI/custom models (Δ5-4), so this
        // is the belt to that suspender. The check runs against the CANDIDATE
        // env (the wizard's saved provider), not the live one, so failure
        // leaves env/runtime/model/provenance untouched.
        inline_setup_guard(&new_config)?;
        new_config.force_apply_to_env();

        // Resolve the effective executor model after /setup. If the config
        // changed it, switch to the new one; otherwise keep the current model.
        let new_model = new_config
            .executor_model()
            .map(|m| resolve_model_alias(m).to_string())
            .filter(|m| *m != self.model);
        let model_changed = new_model.is_some();
        let previous_model = self.model.clone();
        let effective_model = new_model.unwrap_or_else(|| self.model.clone());

        // Rebuild system prompt + runtime UNCONDITIONALLY after /setup (codex R11):
        // reviewer provider/fallback and language preference all affect the system
        // prompt, and `build_system_prompt` reads them live from the env that
        // `force_apply_to_env()` just refreshed. Without this, a session that
        // already has a Codex catalog would silently keep an outdated reviewer
        // routing nudge (e.g. switching codex-mcp → API still tells the model to
        // use `mcp__codex__codex`, and API → codex-mcp leaves the stale "use
        // LlmReview instead" override) for the rest of the session. /setup is a
        // low-frequency operation, so an unconditional rebuild is the cheapest and
        // most robust fix — we do NOT try to diff which fields are prompt-affecting.
        //
        // This reuses the existing build_runtime path with `self.mcp.clone()`
        // (the C1-designed SharedMcpRuntime is shared, NOT re-spawned/re-discovered
        // here); spawning new mcpServers entries still requires a restart, handled
        // by the restart notice below. The executor-switch case keeps its prior
        // behavior: when the model changed we additionally adopt the new model id
        // and print the switch line; when it did not change, runtime/prompt are
        // refreshed in place against the unchanged model with no behavior drift.
        let new_system_prompt = build_system_prompt(Some(&effective_model))?;
        let session = self.runtime.session().clone();
        self.runtime = build_runtime(
            session,
            effective_model.clone(),
            new_system_prompt.clone(),
            true,
            true,
            self.allowed_tools.clone(),
            self.permission_mode,
            self.mcp.clone(),
            self.may_prompt,
        )?;
        self.system_prompt = new_system_prompt;
        if model_changed {
            self.model.clone_from(&effective_model);
            println!("  Executor model: {previous_model} → \x1b[1;32m{effective_model}\x1b[0m");
        }
        // v0.4.22 (Δ4-5/C1): a successful /setup re-establishes the model's
        // provenance — even when the model string did not change (covers "the
        // default fell back mid-session, user re-selects it via /setup": the
        // stale source would otherwise mis-gate the fallback). v0.4.24: the
        // latch this used to re-arm is gone — the chain walk needs none.
        self.model_source = if new_config.executor_model().is_some() {
            ModelSource::Configured
        } else {
            ModelSource::BuiltInDefault
        };

        // Update reviewer model
        if let Some(new_reviewer) = &new_config.reviewer_model {
            self.reviewer_model.clone_from(new_reviewer);
        }

        // v0.4.17 (T10/P1.3): an inline /setup may have just written
        // `mcpServers.codex` into ~/.claude/settings.json, but the live
        // `SharedMcpRuntime` is discovered ONCE at startup and is not rebuilt
        // here (rebuilding would re-spawn every server mid-session). The restart
        // notice must be gated on whether the LIVE catalog already advertises
        // the `codex` server's tools — NOT on `self.mcp.is_none()`. The old
        // `is_none()` check was wrong: if THIS session already has some OTHER
        // MCP server running, `self.mcp` is `Some` but its catalog was built at
        // startup and won't contain `codex` (discovery is not re-run here), so
        // the system prompt would claim Codex MCP is available while
        // `mcp__codex__codex` is absent from the catalog — an "unknown tool"
        // call. So: if the catalog already has `codex`, no restart is needed; if
        // it doesn't (no runtime at all, or a runtime that predates this write /
        // where codex failed to spawn), tell the user to restart.
        if new_config.reviewer_provider.as_deref() == Some("codex-mcp") {
            let codex_in_catalog = self
                .mcp
                .as_ref()
                .is_some_and(|m| m.borrow().catalog_has_server("codex"));
            if !codex_in_catalog {
                println!(
                    "  \x1b[33mRestart aris to activate the Codex MCP server (MCP servers are spawned at startup).\x1b[0m"
                );
            }
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
                                let status = todo
                                    .get("status")
                                    .and_then(|s| s.as_str())
                                    .unwrap_or("pending");
                                let content_text =
                                    todo.get("content").and_then(|c| c.as_str()).unwrap_or("?");
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
                // Canonicalise the skill name so the export dir and the
                // BUNDLED_RESOURCES prefix match exactly. find_skill_content
                // matches bundled names case-insensitively; without this,
                // `/skills export Research-Wiki` would write SKILL.md but
                // miss every helper because `skills/Research-Wiki/` ≠
                // `skills/research-wiki/` in the bundle keys.
                let canonical_name = runtime::BUNDLED_SKILLS
                    .iter()
                    .find(|(n, _)| n.eq_ignore_ascii_case(name))
                    .map(|(n, _)| (*n).to_string())
                    .unwrap_or_else(|| name.to_string());
                let target_dir = dirs_aris_skills().join(&canonical_name);
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

                // v0.4.8: also copy bundled skill-local helpers (`skills/<name>/*`)
                // into the exported skill dir, preserving subdirectories. Without
                // this, the exported skill loses access to its bundled helpers
                // (templates/, tools/, etc.) because the filesystem skill takes
                // precedence over the bundled one in execute_skill (`tools/src/lib.rs`).
                // Shared `tools/*` and `shared-references/*` stay in cache and are
                // accessed via $ARIS_CACHE_DIR by the resolver chain.
                let skill_prefix = format!("skills/{canonical_name}/");
                let mut copied = 0usize;
                let mut failed: Vec<(String, String)> = Vec::new();
                for (key, body) in runtime::BUNDLED_RESOURCES {
                    let Some(rel) = key.strip_prefix(&skill_prefix) else {
                        continue;
                    };
                    let dst = target_dir.join(rel);
                    if dst.exists() {
                        continue; // user-edited files are preserved
                    }
                    if let Some(parent) = dst.parent() {
                        if let Err(e) = fs::create_dir_all(parent) {
                            failed.push((key.to_string(), e.to_string()));
                            continue;
                        }
                    }
                    if let Err(e) = fs::write(&dst, body) {
                        failed.push((key.to_string(), e.to_string()));
                        continue;
                    }
                    copied += 1;
                }

                println!(
                    "\x1b[1;32m✓\x1b[0m Exported to {}\n\x1b[2mEdit this file to customize the skill.\x1b[0m",
                    target_file.display()
                );
                if copied > 0 {
                    println!(
                        "\x1b[2mBundled {copied} helper file(s) into {}\x1b[0m",
                        target_dir.display()
                    );
                }
                for (key, err) in &failed {
                    eprintln!("\x1b[33mwarning:\x1b[0m failed to copy {key}: {err}");
                }
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
                    (
                        "workspace-write",
                        "Normal · Read + write files in workspace",
                    ),
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
            self.mcp.clone(),
            self.may_prompt,
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
            self.mcp.clone(),
            self.may_prompt,
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
            self.mcp.clone(),
            self.may_prompt,
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
                    self.mcp.clone(),
                    self.may_prompt,
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

    fn handle_plan_mode(&mut self, task: Option<&str>) -> Result<bool, Box<dyn std::error::Error>> {
        match task.map(str::trim) {
            // /plan execute — exit plan mode and execute
            Some(arg) if arg.starts_with("execute") => {
                if self.plan_mode.is_none() {
                    println!("Not in plan mode. Use /plan <task> to enter plan mode first.");
                    return Ok(false);
                }
                let state = self
                    .plan_mode
                    .as_ref()
                    .expect("plan_mode checked above")
                    .clone();
                let session = self.runtime.session().clone();
                let new_runtime = match build_runtime(
                    session,
                    self.model.clone(),
                    self.system_prompt.clone(),
                    true,
                    true,
                    state.previous_allowed_tools.clone(),
                    state.previous_permission_mode,
                    self.mcp.clone(),
                    self.may_prompt,
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
                        self.mcp.clone(),
                        self.may_prompt,
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
                    "read_file",
                    "glob_search",
                    "grep_search",
                    "WebFetch",
                    "WebSearch",
                    "ToolSearch",
                    "Skill",
                ]
                .iter()
                .map(|s| s.to_string())
                .collect();

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
                    self.mcp.clone(),
                    self.may_prompt,
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
                let id: usize = id_str
                    .parse()
                    .map_err(|_| format!("Invalid proposal number: {id_str}"))?;
                match meta_optimize::apply_proposal(id) {
                    Ok(msg) => println!("{msg}"),
                    Err(e) => eprintln!("\x1b[1;31mError\x1b[0m: {e}"),
                }
            }
            Some("status") | None => match meta_optimize::status_report() {
                Ok(report) => println!("{report}"),
                Err(e) => eprintln!("\x1b[1;31mError\x1b[0m: {e}"),
            },
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
            self.mcp.clone(),
            self.may_prompt,
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
            self.mcp.clone(),
            self.may_prompt,
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
    let project_context = ProjectContext::discover_with_git(&cwd, &runtime::today_iso())?;
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
    let project_context = ProjectContext::discover(&cwd, &runtime::today_iso())?;
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

    // v0.4.13: deploy bundled meta_opt hooks to ~/.claude/hooks/ and merge
    // their entries into ~/.claude/settings.json so /meta-optimize starts
    // accumulating events from the next Claude Code run.
    //
    // extract_bundled_helpers() (run at startup, see main()) already wrote
    // tools/meta_opt/{log_event,check_ready}.sh into
    // ~/.config/aris/cache/<version>/. We copy from there to ~/.claude/hooks/
    // (overwrite OK — bytes are versioned by aris release), then merge the
    // hook config into ~/.claude/settings.json without clobbering existing
    // user fields or hook entries.
    match deploy_meta_opt_hooks() {
        Ok(report) => {
            if !report.is_empty() {
                println!("{report}");
            }
        }
        Err(e) => {
            // Non-fatal: init succeeded for CLAUDE.md, hooks deploy is a
            // nice-to-have. Surface as warning so users can investigate.
            eprintln!(
                "\x1b[33mwarning\x1b[0m: failed to deploy meta_opt hooks: {e}\n\
                 \x1b[2m(CLAUDE.md was still initialized successfully.)\x1b[0m"
            );
        }
    }

    Ok(())
}

/// Deploy bundled meta_opt hook scripts to `~/.claude/hooks/` and merge their
/// hook config into `~/.claude/settings.json`.
///
/// Resolves HOME via `runtime::home_dir()` and the cache directory via
/// `runtime::extraction_report()` (set by `runtime::extract_bundle()` at
/// startup), then delegates to [`deploy_meta_opt_hooks_to`] for the actual
/// file ops so tests can drive it with a tmp HOME.
fn deploy_meta_opt_hooks() -> Result<String, Box<dyn std::error::Error>> {
    let home = PathBuf::from(runtime::home_dir());
    let cache_dir = runtime::extraction_report()
        .and_then(|r| r.used_dir.clone())
        .ok_or_else(|| {
            "bundled helper cache unavailable; cannot deploy meta_opt hooks".to_string()
        })?;
    deploy_meta_opt_hooks_to(&home, &cache_dir)
}

/// v0.4.13 meta_opt hook scripts that get deployed from the cache to
/// `~/.claude/hooks/`. Tuple order: (cache-relative path, destination basename).
///
/// **Codex round-1 finding #1**: destination names are ARIS-namespaced
/// (`aris-meta-opt-*.sh`) so `aris init` never silently clobbers a user's
/// own `log_event.sh` / `check_ready.sh` in `~/.claude/hooks/`. ARIS-owned
/// files are visibly ours, impossible to collide with a hand-rolled hook,
/// and safe to overwrite on every `aris init` since only we put them there.
const META_OPT_HOOK_SCRIPTS: &[(&str, &str)] = &[
    ("tools/meta_opt/log_event.sh", "aris-meta-opt-log-event.sh"),
    (
        "tools/meta_opt/check_ready.sh",
        "aris-meta-opt-check-ready.sh",
    ),
];

/// Pure-fn variant of [`deploy_meta_opt_hooks`] that takes explicit `home` +
/// `cache_dir` paths so unit tests can isolate them from the real environment.
///
/// Behaviour:
/// 1. Create `<home>/.claude/hooks/` if missing.
/// 2. Copy `<cache_dir>/tools/meta_opt/{log_event,check_ready}.sh` to
///    `<home>/.claude/hooks/`, chmod +x on Unix.
/// 3. Read `<home>/.claude/settings.json` (or start with `{}`) and merge in
///    PostToolUse / PostToolUseFailure / UserPromptSubmit / SessionStart /
///    SessionEnd hook entries that reference the deployed scripts. Idempotent:
///    a second run does not duplicate entries pointing at the same script.
/// 4. Backup the existing settings.json to
///    `<home>/.claude/settings.json.bak.<unix-millis>` before overwriting (only
///    when there was a previous file).
fn deploy_meta_opt_hooks_to(
    home: &Path,
    cache_dir: &Path,
) -> Result<String, Box<dyn std::error::Error>> {
    let claude_dir = home.join(".claude");
    let hooks_dir = claude_dir.join("hooks");
    fs::create_dir_all(&hooks_dir)
        .map_err(|e| format!("create_dir_all({}): {e}", hooks_dir.display()))?;

    // ---- Step 1: copy bundled scripts from cache → ~/.claude/hooks/ ----
    let mut deployed: Vec<PathBuf> = Vec::new();
    for (rel, dest_name) in META_OPT_HOOK_SCRIPTS {
        let src = cache_dir.join(rel);
        if !src.is_file() {
            return Err(format!(
                "bundled hook script missing from cache: {} (cache_dir={})",
                rel,
                cache_dir.display()
            )
            .into());
        }
        let dest = hooks_dir.join(dest_name);
        fs::copy(&src, &dest)
            .map_err(|e| format!("copy {} -> {}: {e}", src.display(), dest.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&dest)
                .map_err(|e| format!("stat {}: {e}", dest.display()))?
                .permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&dest, perms)
                .map_err(|e| format!("chmod 0755 {}: {e}", dest.display()))?;
        }
        deployed.push(dest);
    }

    // ---- Step 2: merge entries into ~/.claude/settings.json ----
    let settings_path = claude_dir.join("settings.json");
    let (mut settings, had_existing) = match fs::read_to_string(&settings_path) {
        Ok(text) => {
            // Empty file → start with {} (avoid serde error on empty input).
            let trimmed = text.trim();
            if trimmed.is_empty() {
                (serde_json::json!({}), true)
            } else {
                let parsed: serde_json::Value = serde_json::from_str(trimmed).map_err(|e| {
                    format!(
                        "parse {}: {e} (refusing to clobber malformed user settings)",
                        settings_path.display()
                    )
                })?;
                if !parsed.is_object() {
                    return Err(format!(
                        "{} is not a JSON object (top-level must be {{...}})",
                        settings_path.display()
                    )
                    .into());
                }
                (parsed, true)
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (serde_json::json!({}), false),
        Err(e) => return Err(format!("read {}: {e}", settings_path.display()).into()),
    };

    // v0.4.13 codex round-1 #1: paths must match the ARIS-namespaced
    // destinations declared in META_OPT_HOOK_SCRIPTS so settings.json
    // hook command strings actually point at the deployed scripts.
    let log_event_path = hooks_dir.join("aris-meta-opt-log-event.sh");
    let check_ready_path = hooks_dir.join("aris-meta-opt-check-ready.sh");

    // Hook entry layout follows main's templates/claude-hooks/meta_logging.json
    // verbatim, but with the bundled hook script paths (not $CLAUDE_PROJECT_DIR
    // references). One hook entry per event name; "matcher": "" matches all
    // tool calls / events for PostToolUse* variants. SessionEnd carries two
    // sub-hooks: log_event AND check_ready.
    let events_for_log_event = [
        "PostToolUse",
        "PostToolUseFailure",
        "UserPromptSubmit",
        "SessionStart",
        "SessionEnd",
    ];

    let mut added_log_event = 0usize;
    let mut added_check_ready = 0usize;

    for event in events_for_log_event {
        if ensure_hook_entry(
            &mut settings,
            event,
            &log_event_path,
            /*async_run=*/ true,
        )? {
            added_log_event += 1;
        }
    }
    if ensure_hook_entry(
        &mut settings,
        "SessionEnd",
        &check_ready_path,
        /*async_run=*/ false,
    )? {
        added_check_ready += 1;
    }

    // ---- Step 3: backup existing file (hard-fail if backup fails), then
    // atomically rewrite via tempfile + rename (codex round-1 #2). ----
    if had_existing {
        let backup_suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let backup_path = claude_dir.join(format!("settings.json.bak.{backup_suffix}"));
        // Hard-fail on backup error so user never loses their settings.
        // If the FS is read-only or we can't write, abort rather than
        // silently destroying state.
        fs::copy(&settings_path, &backup_path).map_err(|e| {
            format!(
                "backup {} → {} failed: {e}; aborting to protect existing settings",
                settings_path.display(),
                backup_path.display()
            )
        })?;
    }

    let pretty = serde_json::to_string_pretty(&settings)
        .map_err(|e| format!("serialize settings.json: {e}"))?;
    let body = format!("{pretty}\n");

    // Atomic rewrite: write to a tempfile in the same directory, then
    // rename. This is the only way to guarantee that a crash or signal
    // can't leave settings.json half-written.
    let temp_path = claude_dir.join(format!(
        "settings.json.tmp.{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    fs::write(&temp_path, body)
        .map_err(|e| format!("write tempfile {}: {e}", temp_path.display()))?;
    fs::rename(&temp_path, &settings_path).map_err(|e| {
        // Best-effort cleanup; the user can manually rm the .tmp.* file
        let _ = fs::remove_file(&temp_path);
        format!(
            "atomic rename {} → {}: {e}",
            temp_path.display(),
            settings_path.display()
        )
    })?;

    // ---- Step 4: human-readable report ----
    let mut lines = Vec::new();
    lines.push(format!(
        "Meta-Optimize hooks deployed to {}",
        hooks_dir.display()
    ));
    for p in &deployed {
        if let Some(name) = p.file_name() {
            lines.push(format!("  installed       {}", name.to_string_lossy()));
        }
    }
    lines.push(format!(
        "Merged into     {} (log_event added: {added_log_event}, check_ready added: {added_check_ready})",
        settings_path.display()
    ));
    Ok(lines.join("\n"))
}

/// Look up `hooks.<event>` in `settings`, ensure there is a matcher entry whose
/// sub-hooks include `command = "bash <script_path>"`. If an entry referencing
/// the same script already exists (anywhere under `hooks.<event>[*].hooks[*]`),
/// returns `false` (no-op). Otherwise inserts a new matcher entry and returns
/// `true`.
fn ensure_hook_entry(
    settings: &mut serde_json::Value,
    event: &str,
    script_path: &Path,
    async_run: bool,
) -> Result<bool, Box<dyn std::error::Error>> {
    use serde_json::{json, Value};

    let script_str = script_path.to_string_lossy().to_string();
    let command = format!("bash {script_str}");

    let obj = settings
        .as_object_mut()
        .ok_or_else(|| "settings is not a JSON object".to_string())?;
    let hooks_entry = obj
        .entry("hooks".to_string())
        .or_insert_with(|| Value::Object(serde_json::Map::new()));
    let hooks_obj = hooks_entry
        .as_object_mut()
        .ok_or_else(|| "settings.hooks is not a JSON object".to_string())?;
    let event_entry = hooks_obj
        .entry(event.to_string())
        .or_insert_with(|| Value::Array(Vec::new()));
    let event_arr = event_entry
        .as_array_mut()
        .ok_or_else(|| format!("settings.hooks.{event} is not a JSON array"))?;

    // Idempotency check: scan all existing matcher entries for a sub-hook with
    // the exact same command. If found, do nothing.
    for matcher_entry in event_arr.iter() {
        let Some(matcher_obj) = matcher_entry.as_object() else {
            continue;
        };
        let Some(inner_hooks) = matcher_obj.get("hooks").and_then(|v| v.as_array()) else {
            continue;
        };
        for hook in inner_hooks {
            if let Some(cmd) = hook.get("command").and_then(|v| v.as_str()) {
                if cmd == command {
                    return Ok(false);
                }
            }
        }
    }

    let new_entry = if async_run {
        json!({
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 5,
                    "async": true,
                }
            ],
        })
    } else {
        json!({
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 5,
                }
            ],
        })
    };
    event_arr.push(new_entry);
    Ok(true)
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
    // v0.4.22 (C6): `which` does not exist on stock Windows — use `where`.
    let finder = if cfg!(windows) { "where" } else { "which" };
    Command::new(finder)
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
        "ARIS (Auto Research in Sleep)\n  Version          {VERSION}\n  Git SHA          {git_sha}\n  Target           {target}\n  Build date       {BUILD_DATE}"
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
                ContentBlock::Thinking { thinking, .. } => {
                    lines.push(format!("[thinking] {thinking}"));
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

/// Pure (I/O-free) reviewer-routing nudge used in the system prompt.
///
/// v0.4.22 (B1): rewritten for the GPT-5.6-Sol two-tier doctrine that the
/// synced skills now carry (main 6142715 / reviewer-routing.md). The v0.4.17
/// blanket "never pass a model" rule contradicted the skills' explicit
/// `model: gpt-5.6-sol` pins — obeying it would silently strip deep audits
/// down from ultra. The rules below mirror the canonical capability-only
/// fallback chain and add the transport-safety rules (approval-policy /
/// sandbox / `LlmReview` parameter stripping) from the v0.4.22 design.
///
/// Three states:
///   - `codex-mcp` + fallback configured → Codex MCP primary + the
///     `LlmReview` HTTP fallback, PRE-DISPATCH-ONLY (Δ5-1).
///   - `codex-mcp` + no fallback         → pure Codex MCP.
///   - any other provider                → the "use `LlmReview` instead"
///     override, with Codex-parameter stripping (Δ4-1).
///
/// Extracted as a pure fn (codex R11) so its output across all three states is
/// unit-testable without the filesystem I/O that `build_system_prompt` performs.
fn reviewer_routing_nudge(reviewer_provider: &str, fallback: Option<&str>) -> Vec<String> {
    // Shared Codex-MCP call discipline (both codex-mcp states).
    const CODEX_RULES: &str = "ARIS's preferred reviewer is gpt-5.6-sol; skills pin the model and \
         reasoning effort explicitly per fresh call — pass them through exactly as the skill \
         specifies (per-call `config: {\"model_reasoning_effort\": ...}`; deep audits \"ultra\", \
         regular reviews \"xhigh\"; never below xhigh for verdict-bearing review). If a skill uses \
         the legacy `reasoning: ultra` shorthand, translate it to \
         `config: {\"model_reasoning_effort\": \"ultra\"}` — never send an unknown `reasoning` \
         field. Capability fallback (in order, capability errors ONLY): (1) run as pinned; \
         (2) if the EFFORT is explicitly unsupported, retry the SAME model at \"xhigh\" — this \
         applies only to deep-tier calls, a regular xhigh call is never retried with the same \
         params; (3) if the MODEL is explicitly unknown/unavailable, retry as explicit gpt-5.5 + \
         \"xhigh\"; (4) NEVER auto-degrade on timeouts, rate limits, auth, transport, sandbox, or \
         parse errors. When THIS review call carries an explicit user-chosen reviewer-model \
         override (an explicit model parameter on the call itself), the automatic capability \
         chain is DISABLED for that call — surface the capability error instead of substituting \
         a different model; the user owns an explicit choice. ARIS's /reviewer command is NOT \
         such an override — it controls the HTTP fallback exclusively and never disables this \
         chain. On every FRESH `mcp__codex__codex` call also pass \
         `approval-policy: \"never\"` and an explicit `sandbox` (default \"read-only\" for review; \
         wider only when the skill needs writes) — ARIS cannot service Codex's interactive \
         escalation requests, so an approval prompt would stall the call. `mcp__codex__codex-reply` \
         takes ONLY the thread id and prompt (it inherits the thread's model/effort).";

    if reviewer_provider == "codex-mcp" {
        match fallback.filter(|s| !s.trim().is_empty()) {
            Some(fallback) => vec![format!(
                "IMPORTANT: Your external LLM reviewer is Codex MCP — use `mcp__codex__codex` / \
                 `mcp__codex__codex-reply` as instructed by skills. {CODEX_RULES} HTTP fallback: \
                 ONLY when the Codex MCP channel is already known absent BEFORE dispatch (the tool \
                 is missing from the catalog or discovery failed) may you use the `LlmReview` tool, \
                 which calls the configured HTTP fallback reviewer ({fallback}) directly. Once a \
                 Codex call has been dispatched, never re-target it to HTTP on any error. When \
                 using LlmReview, pass ONLY the review `prompt` — never forward the skill's Codex \
                 `model`, `config`, `sandbox`, or `approval-policy` parameters; pass a `model` to \
                 LlmReview only when the user explicitly chose an HTTP reviewer model."
            )],
            None => vec![format!(
                "IMPORTANT: Your external LLM reviewer is Codex MCP — use the `mcp__codex__codex` / \
                 `mcp__codex__codex-reply` tools as instructed by skills. {CODEX_RULES}"
            )],
        }
    } else {
        vec![
            "IMPORTANT: When a skill instructs you to use `mcp__codex__codex` or `mcp__codex__codex-reply` \
             for external LLM review, use the `LlmReview` tool instead. The LlmReview tool calls \
             Gemini or OpenAI directly (via GEMINI_API_KEY or OPENAI_API_KEY) without needing MCP. \
             Pass ONLY the full review prompt as the `prompt` parameter — never forward the skill's \
             Codex `model`, `config`, `sandbox`, or `approval-policy` parameters into LlmReview; \
             pass a `model` only when the user explicitly chose an HTTP reviewer model."
                .to_string(),
        ]
    }
}

fn build_system_prompt(model_id: Option<&str>) -> Result<Vec<String>, Box<dyn std::error::Error>> {
    let mut prompt = match load_system_prompt(
        env::current_dir()?,
        &runtime::today_iso(),
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
        "claude-fable-5" => "Claude Fable 5",
        "claude-opus-5" => "Claude Opus 5",
        "claude-sonnet-5" => "Claude Sonnet 5",
        "claude-opus-4-8" => "Claude Opus 4.8",
        "claude-opus-4-7" => "Claude Opus 4.7",
        "claude-sonnet-4-6" => "Claude Sonnet 4.6",
        "claude-haiku-4-5-20251001" => "Claude Haiku 4.5",
        "deepseek-v4-pro" => "DeepSeek V4 Pro",
        "mimo-v2.5-pro" => "Xiaomi MiMo v2.5 Pro",
        "mimo-v2.5" => "Xiaomi MiMo v2.5",
        "mimo-v2-pro" => "Xiaomi MiMo v2 Pro",
        "mimo-v2-omni" => "Xiaomi MiMo v2 Omni",
        "qwen3.6-plus" => "Qwen 3.6 Plus",
        "qwen3.6-flash" => "Qwen 3.6 Flash",
        "qwen3.6-max-preview" => "Qwen 3.6 Max Preview",
        "doubao-pro-4k" => "Doubao Pro 4K",
        "doubao-lite-4k" => "Doubao Lite 4K",
        other => other,
    };
    // Map model-name prefix to developer/vendor for the ARIS identity line.
    // Without this, e.g. a DeepSeek user would see "developed by Anthropic".
    let developer = if model_name.starts_with("mimo-") {
        "Xiaomi"
    } else if model_name.starts_with("deepseek-") {
        "DeepSeek"
    } else if model_name.starts_with("qwen-") || model_name.starts_with("qwen3.") {
        "Alibaba"
    } else if model_name.starts_with("doubao-") {
        "ByteDance"
    } else if model_name.starts_with("gpt-")
        || model_name.starts_with("o1")
        || model_name.starts_with("o3")
        || model_name.starts_with("o4")
    {
        "OpenAI"
    } else if model_name.starts_with("gemini-") {
        "Google"
    } else if model_name.starts_with("GLM") || model_name.starts_with("glm") {
        "Zhipu"
    } else if model_name.starts_with("MiniMax") || model_name.starts_with("minimax") {
        "MiniMax"
    } else if model_name.starts_with("kimi-") || model_name.starts_with("moonshot-") {
        "Moonshot"
    } else {
        "Anthropic"
    };
    prompt.push(format!(
        "You are running inside ARIS (Auto Research in Sleep), a research automation CLI. \
         Your exact model is {model_name} ({friendly_name}), developed by {developer}. \
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

    // ARIS reviewer routing nudge (read live env, then defer to the pure helper
    // so the three-state behavior — codex-mcp w/ fallback, codex-mcp w/o
    // fallback, any other provider — stays unit-testable without filesystem I/O).
    let reviewer_provider = std::env::var("ARIS_REVIEWER_PROVIDER").unwrap_or_default();
    let reviewer_fallback = std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER")
        .ok()
        .filter(|s| !s.is_empty());
    prompt.extend(reviewer_routing_nudge(
        &reviewer_provider,
        reviewer_fallback.as_deref(),
    ));

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
                    let summary: Vec<String> = todos
                        .iter()
                        .map(|t| {
                            let status = t
                                .get("status")
                                .and_then(|s| s.as_str())
                                .unwrap_or("pending");
                            let text = t.get("content").and_then(|c| c.as_str()).unwrap_or("?");
                            format!("- [{status}] {text}")
                        })
                        .collect();
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
        env::set_var(
            "CLAWD_TODO_STORE",
            aris_tasks_path().to_string_lossy().as_ref(),
        );
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

/// Human-readable label for a config scope (used in MCP skip notices + doctor).
fn scope_label(scope: ConfigSource) -> &'static str {
    match scope {
        ConfigSource::User => "user",
        ConfigSource::Project => "project",
        ConfigSource::Local => "local",
    }
}

/// v0.4.17 (codex R Track C2 P2): sanitize a raw MCP server name for terminal
/// display. A project/local config can no longer SPAWN a server, but it can
/// still put ANSI/control characters in a server NAME, which would corrupt the
/// terminal when echoed in skip notices / approval prompts / doctor output.
/// Replace any control character (incl. ESC) with `?`; leave everything else
/// (including non-ASCII) intact.
fn sanitize_for_display(raw: &str) -> String {
    raw.chars()
        .map(|c| if c.is_control() { '?' } else { c })
        .collect()
}

/// v0.4.17 (T4/RW5): the long-lived MCP state shared across the REPL.
///
/// Holds the sync [`runtime::McpManagerHandle`] (which owns the spawned MCP
/// server child processes and their dedicated `current_thread` tokio runtime)
/// plus the [`McpToolCatalog`] cached from the single startup `discover_tools`
/// pass. Both the advertising path (the executors, which append the catalog's
/// specs to the static catalogue) and the dispatch path (the
/// [`CliToolExecutor`], which routes `mcp__` names back through the handle) read
/// from this one instance.
///
/// It is held behind `Rc<RefCell<_>>` by [`LiveCli`] so the spawned servers
/// survive `build_runtime` rebuilds (plan-mode enter/exit/execute rebuild the
/// whole `ConversationRuntime`; reusing this handle avoids re-spawning and
/// re-`initialize`-ing every server on each switch — SPIKE-A §3.2). Single
/// threaded REPL ⇒ `Rc<RefCell>` suffices; no `Arc<Mutex>` / `Send` needed.
struct McpRuntime {
    handle: runtime::McpManagerHandle,
    catalog: McpToolCatalog,
    /// v0.4.17 (T5): raw server names the user PRE-TRUSTED (`trust: true`) AND
    /// that come from a USER-scope config. Trust from project/local config is
    /// NOT honored (a checked-out repo must not be able to self-authorize its
    /// own MCP tools — codex R2 Track C2). A trusted server's tool calls skip
    /// the dispatch approval prompt.
    trusted_servers: HashSet<String>,
    /// v0.4.17 (T5): raw server names the user approved "don't ask again" for
    /// during THIS session (in-memory only, never persisted). Lives here (not
    /// on the executor) so it survives `build_runtime` rebuilds (plan-mode
    /// switches reuse the same `SharedMcpRuntime`).
    session_approved: HashSet<String>,
}

type SharedMcpRuntime = Rc<RefCell<McpRuntime>>;

impl McpRuntime {
    /// Eager startup discovery (RW5) with a v0.4.17 (T5) pre-discovery scope
    /// gate.
    ///
    /// **Security boundary (codex R2 Track C2 P0):** a checked-out repository
    /// may carry `.claude/settings.json` (project scope) or
    /// `.claude/settings.local.json` (local scope) declaring `mcpServers`.
    /// Eager discovery SPAWNS each server's command, so discovering an
    /// untrusted project/local server would be arbitrary command execution
    /// triggered merely by `cd`-ing into a cloned repo. To close this, ONLY
    /// USER-scope servers (`~/.claude*`, written by the user themselves) are
    /// discovered/spawned/advertised. Project- and local-scope servers are
    /// skipped entirely: not spawned, not advertised, not dispatchable (a name
    /// the manager never indexed can't be called). The user can promote a
    /// server to their user config to enable it. `trust: true` is likewise only
    /// honored for user-scope servers.
    ///
    /// Per-server discovery failures (among the user-scope set) are non-fatal
    /// (surfaced by the manager via `discovery_failures` + a stderr line); only
    /// a hard handle/runtime construction error returns `Err`.
    ///
    /// MUST be called from outside any tokio runtime context (the handle's
    /// internal `block_on` would panic otherwise) — the CLI's `fn main` is not
    /// `#[tokio::main]`, so this holds (SPIKE-A).
    fn discover(config: &runtime::RuntimeConfig) -> io::Result<Self> {
        // RW5: surface (but do not truncate) catalogues large enough to crowd a
        // provider's tool array / token budget. Deferred advertising is a
        // v0.5.0 item; for now we just warn.
        const MCP_TOOL_WARN_THRESHOLD: usize = 40;

        // T5 pre-discovery scope gate: keep only user-scope servers; skip
        // (don't spawn) project/local-scope servers with a one-line notice.
        let mut user_scope: BTreeMap<String, runtime::ScopedMcpServerConfig> = BTreeMap::new();
        let mut trusted_servers: HashSet<String> = HashSet::new();
        for (name, scoped) in config.mcp().servers() {
            match scoped.scope {
                ConfigSource::User => {
                    // Honor trust only from user scope.
                    if let runtime::McpServerConfig::Stdio(stdio) = &scoped.config {
                        if stdio.trust() == Some(true) {
                            trusted_servers.insert(name.clone());
                        }
                    }
                    user_scope.insert(name.clone(), scoped.clone());
                }
                ConfigSource::Project | ConfigSource::Local => {
                    eprintln!(
                        "aris mcp: skipping {}-scoped MCP server `{}` \
                         (project/local config cannot authorize a process spawn); \
                         move it to your user config (~/.claude) to enable.",
                        scope_label(scoped.scope),
                        sanitize_for_display(name)
                    );
                }
            }
        }

        let user_manager = runtime::McpServerManager::from_servers(&user_scope);
        let mut handle = runtime::McpManagerHandle::from_manager(user_manager)?;
        let discovered_tools = handle.discover_tools().unwrap_or_else(|error| {
            eprintln!("aris mcp: tool discovery failed, continuing without MCP tools: {error}");
            Vec::new()
        });
        let catalog = mcp_tool_specs(&discovered_tools);

        if catalog.len() > MCP_TOOL_WARN_THRESHOLD {
            eprintln!(
                "aris mcp: {} MCP tools discovered (>{}); this may crowd the provider tool list",
                catalog.len(),
                MCP_TOOL_WARN_THRESHOLD
            );
        }

        Ok(Self {
            handle,
            catalog,
            trusted_servers,
            session_approved: HashSet::new(),
        })
    }

    /// The advertisable MCP specs (cloned) for appending onto a provider's
    /// static tool catalogue.
    fn advertised_specs(&self) -> Vec<RuntimeToolSpec> {
        self.catalog.specs().to_vec()
    }

    /// v0.4.17 (T10/P1.3): does the live (startup-discovered) catalog already
    /// advertise tools from the given raw MCP server name? The inline-`/setup`
    /// restart notice uses this for `codex`: if the server's tools are already
    /// in the catalog, an inline `/setup` that (re)wrote `mcpServers.codex`
    /// needs no restart; if not (the server was added this session, or failed to
    /// spawn at startup), the user must restart so it's actually spawned.
    fn catalog_has_server(&self, server_name: &str) -> bool {
        self.catalog.has_server(server_name)
    }
}

/// v0.4.17 (RW5): build the shared MCP runtime if (and only if) the config
/// declares MCP servers. Returns `None` when no servers are configured so that
/// every downstream path is byte-for-byte identical to the pre-MCP behavior
/// (no handle, no extra advertised tools, no dispatch branch taken).
fn build_shared_mcp_runtime() -> Option<SharedMcpRuntime> {
    let cwd = env::current_dir().ok()?;
    let config = ConfigLoader::default_for(&cwd).load().ok()?;
    if config.mcp().servers().is_empty() {
        return None;
    }
    match McpRuntime::discover(&config) {
        Ok(mcp) => Some(Rc::new(RefCell::new(mcp))),
        Err(error) => {
            eprintln!(
                "aris mcp: could not initialize MCP runtime, continuing without MCP tools: {error}"
            );
            None
        }
    }
}

/// v0.4.17 (T8): apply an `--allowedTools` allowlist to a set of advertised MCP
/// specs. Mirrors [`filter_tool_specs`]'s semantics for the static catalogue so
/// the ADVERTISING side and the DISPATCH side
/// ([`CliToolExecutor::execute`]'s allowlist gate) share one allowlist meaning:
/// - `None` (no `--allowedTools` given) ⇒ advertise every MCP tool (status quo).
/// - `Some(set)` ⇒ advertise only the MCP tools whose advertised name is in the
///   set (an MCP name reaches the set only via the deferred-validation path in
///   [`normalize_allowed_tools`]).
///
/// Pulled into one helper so the two provider advertising paths (`Anthropic` +
/// `OpenAI`) never drift on which MCP tools they expose.
fn filter_mcp_specs(
    specs: Vec<RuntimeToolSpec>,
    allowed_tools: Option<&AllowedToolSet>,
) -> Vec<RuntimeToolSpec> {
    match allowed_tools {
        None => specs,
        Some(allowed) => specs
            .into_iter()
            .filter(|spec| allowed.contains(&spec.name))
            .collect(),
    }
}

/// Snapshot of the advertised MCP specs to hand to a freshly built executor,
/// filtered to the current `--allowedTools` allowlist (T8). Empty when there is
/// no MCP runtime (preserving the no-MCP byte-equivalence).
fn advertised_mcp_specs(
    mcp: Option<&SharedMcpRuntime>,
    allowed_tools: Option<&AllowedToolSet>,
) -> Vec<RuntimeToolSpec> {
    let specs = mcp
        .map(|m| m.borrow().advertised_specs())
        .unwrap_or_default();
    filter_mcp_specs(specs, allowed_tools)
}

#[allow(clippy::too_many_arguments)]
fn build_runtime(
    session: Session,
    model: String,
    system_prompt: Vec<String>,
    enable_tools: bool,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
    permission_mode: PermissionMode,
    mcp: Option<SharedMcpRuntime>,
    may_prompt: bool,
) -> Result<ConversationRuntime<ExecutorClient, CliToolExecutor>, Box<dyn std::error::Error>> {
    let mcp_specs = advertised_mcp_specs(mcp.as_ref(), allowed_tools.as_ref());
    let executor: ExecutorClient =
        if let Some(config) = openai_executor::resolve_openai_executor_config() {
            ExecutorClient::OpenAI(openai_executor::OpenAIRuntimeClient::new(
                config,
                model,
                enable_tools,
                emit_output,
                allowed_tools.clone(),
                mcp_specs.clone(),
            )?)
        } else {
            ExecutorClient::Anthropic(AnthropicRuntimeClient::new(
                model,
                enable_tools,
                emit_output,
                allowed_tools.clone(),
                mcp_specs,
            )?)
        };

    // v0.4.17 (T5): register each ADVERTISED MCP tool with the generic
    // PermissionPolicy at the MINIMAL required mode (ReadOnly). Rationale: an
    // unregistered tool defaults to required=DangerFullAccess, which would make
    // the generic gate silently DENY MCP tools in read-only/workspace mode
    // (never reaching the executor's MCP approval) — and conversely the generic
    // gate must not be the place that auto-grants them either. Registering at
    // ReadOnly means the generic gate always passes an advertised MCP tool
    // through to the executor (ReadOnly ≤ any active level; Prompt mode still
    // prompts once; Allow bypasses), where the real MCP-specific safety
    // confirmation runs (`CliToolExecutor::dispatch_mcp`). We register the
    // ALLOWLIST-FILTERED advertised names so a name not exposed to the model
    // also isn't registered.
    let mcp_names = advertised_mcp_specs(mcp.as_ref(), allowed_tools.as_ref())
        .into_iter()
        .map(|spec| spec.name);

    let feature_config = build_runtime_feature_config()?;
    let event_sink = build_event_sink(&feature_config);
    Ok(ConversationRuntime::new_with_features(
        session,
        executor,
        CliToolExecutor::new(allowed_tools, emit_output, mcp, permission_mode, may_prompt),
        permission_policy_with_mcp(permission_mode, mcp_names),
        system_prompt,
        feature_config,
    )
    .with_event_sink(event_sink))
}

fn build_event_sink(
    _feature_config: &runtime::RuntimeFeatureConfig,
) -> Box<dyn runtime::EventSink> {
    let level_str = std::env::var("ARIS_META_LOGGING").unwrap_or_default();
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
        // v0.4.17 (T5): in Prompt mode the generic gate confirms every tool,
        // including MCP tools — and for MCP tools the executor-layer approval
        // is intentionally skipped to avoid double-confirmation. So this generic
        // prompt IS the confirmation for an MCP call; surface the external-
        // process caveat here too.
        if request.tool_name.starts_with("mcp__") {
            println!(
                "  Note             MCP servers run as external processes; the sandbox does NOT cover them."
            );
        }
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

    fn on_session_compacted(&mut self, removed_count: usize) {
        match self {
            // Anthropic uses thinking blocks inside session content, no
            // out-of-band cache to invalidate.
            Self::Anthropic(_) => {}
            // OpenAI executor's reasoning_cache is keyed by message index;
            // compaction shifts every index so we drop the whole cache.
            // Re-population happens organically as the model emits new
            // reasoning_content blocks post-compaction.
            Self::OpenAI(c) => c.on_session_compacted(removed_count),
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
    /// v0.4.17 (RW5): MCP tools to advertise in addition to the static
    /// catalogue. Empty when no MCP servers are configured (no-MCP path is
    /// byte-for-byte identical to pre-v0.4.17).
    mcp_specs: Vec<RuntimeToolSpec>,
}

impl AnthropicRuntimeClient {
    fn new(
        model: String,
        enable_tools: bool,
        emit_output: bool,
        allowed_tools: Option<AllowedToolSet>,
        mcp_specs: Vec<RuntimeToolSpec>,
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
            mcp_specs,
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
                // v0.4.17 (T1/RW5): static catalogue (via RuntimeToolSpec —
                // byte-identical to the old inline construction) followed by
                // the cached MCP specs. When `mcp_specs` is empty (no MCP
                // servers) this is exactly the pre-v0.4.17 payload.
                filter_tool_specs(self.allowed_tools.as_ref())
                    .iter()
                    .map(RuntimeToolSpec::from)
                    .chain(self.mcp_specs.iter().cloned())
                    .map(|spec| ToolDefinition {
                        name: spec.name,
                        description: Some(spec.description),
                        input_schema: spec.input_schema,
                    })
                    .collect()
            }),
            tool_choice: self.enable_tools.then_some(ToolChoice::Auto),
            stream: true,
        };

        self.runtime.block_on(async {
            // v0.4.18: tag a "model unavailable on this account" failure (404
            // not_found_error from the initial POST, before any stream event) so
            // the CLI can walk DEFAULT_MODEL_CHAIN toward an available model.
            // All other errors keep the plain `new` form.
            let mut stream = self
                .client
                .stream_message(&message_request)
                .await
                .map_err(|error| {
                    if error.is_model_unavailable() {
                        RuntimeError::model_unavailable(error.to_string())
                    } else {
                        RuntimeError::new(error.to_string())
                    }
                })?;
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
            let mut pending_thinking: Option<(String, String)> = None;
            let mut saw_stop = false;
            // v0.4.10 T35: cache initial input/cache token usage from
            // MessageStart so the eventual MessageDelta can merge them
            // into a complete TokenUsage event.
            let mut start_usage: Option<api::Usage> = None;

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
                        // v0.4.10 T35: stash the initial input/cache token
                        // counts. Anthropic streaming splits usage across
                        // message_start (input + cache) and message_delta
                        // (output), so we have to remember the start
                        // numbers and merge them on the final delta. The
                        // previous code only used delta.usage and lost
                        // input/cache entirely.
                        start_usage = Some(start.message.usage.clone());
                        for block in start.message.content {
                            push_output_block(block, out, &mut events, &mut pending_tool, true)?;
                        }
                    }
                    ApiStreamEvent::ContentBlockStart(start) => {
                        if let OutputContentBlock::Thinking {
                            thinking,
                            signature,
                        } = &start.content_block
                        {
                            pending_thinking = Some((thinking.clone(), signature.clone()));
                        } else {
                            push_output_block(
                                start.content_block,
                                out,
                                &mut events,
                                &mut pending_tool,
                                true,
                            )?;
                        }
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
                        ContentBlockDelta::ThinkingDelta { thinking } => {
                            if let Some((ref mut t, _)) = pending_thinking {
                                t.push_str(&thinking);
                            }
                        }
                        ContentBlockDelta::SignatureDelta { signature } => {
                            if let Some((_, ref mut s)) = pending_thinking {
                                *s = signature;
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
                        if let Some((thinking, signature)) = pending_thinking.take() {
                            events.push(AssistantEvent::Thinking {
                                thinking,
                                signature,
                            });
                        }
                    }
                    ApiStreamEvent::MessageDelta(delta) => {
                        // v0.4.10 T35 / C8 landmine fix: merge the
                        // earlier MessageStart usage (input/cache) with
                        // this delta's output_tokens before emitting,
                        // since the streaming protocol splits them.
                        // Falls back to delta-only if MessageStart was
                        // somehow missed (defensive — should not happen
                        // on a well-formed stream).
                        let start = start_usage.as_ref();
                        events.push(AssistantEvent::Usage(TokenUsage {
                            input_tokens: start
                                .map(|u| u.input_tokens)
                                .unwrap_or(delta.usage.input_tokens),
                            output_tokens: delta.usage.output_tokens,
                            cache_creation_input_tokens: start
                                .map(|u| u.cache_creation_input_tokens)
                                .unwrap_or(delta.usage.cache_creation_input_tokens),
                            cache_read_input_tokens: start
                                .map(|u| u.cache_read_input_tokens)
                                .unwrap_or(delta.usage.cache_read_input_tokens),
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
                        let msg = e
                            .error
                            .get("message")
                            .and_then(|v| v.as_str())
                            .unwrap_or("stream error")
                            .to_string();
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

/// v0.4.20 (#299): did this turn print visible assistant TEXT (vs only tool
/// calls / thinking / nothing)? Drives whether `run_turn` finishes the spinner
/// with the non-clearing `finish_after_output` (keep the reply on screen) or the
/// clearing `finish` (wipe the leftover "Thinking…" line on a tool-only/empty
/// turn).
fn turn_has_visible_assistant_text(summary: &runtime::TurnSummary) -> bool {
    summary.assistant_messages.iter().any(|message| {
        message
            .blocks
            .iter()
            .any(|block| matches!(block, ContentBlock::Text { text } if !text.trim().is_empty()))
    })
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

    format!("\x1b[38;5;74m●\x1b[0m \x1b[1m{name}\x1b[0m\x1b[38;5;245m({detail})\x1b[0m")
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
            let hit_count = parsed
                .get("results")
                .and_then(|v| v.as_array())
                .map_or(0, |a| {
                    a.iter()
                        .filter(|v| v.get("content").is_some())
                        .flat_map(|v| v.get("content").and_then(|c| c.as_array()))
                        .map(|a| a.len())
                        .sum::<usize>()
                });
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

    // v0.4.23 (A2): fold both streams for display, head+tail (the tail
    // carries the error/summary). stderr keeps its red per KEPT line.
    if let Some(stdout) = parsed.get("stdout").and_then(|value| value.as_str()) {
        if !stdout.trim().is_empty() {
            lines.push(fold_tool_output(
                stdout.trim_end(),
                tool_output_line_budget(8),
                FoldKeep::HeadTail,
                None,
            ));
        }
    }
    if let Some(stderr) = parsed.get("stderr").and_then(|value| value.as_str()) {
        if !stderr.trim().is_empty() {
            lines.push(fold_tool_output(
                stderr.trim_end(),
                tool_output_line_budget(8),
                FoldKeep::HeadTail,
                Some("\x1b[38;5;203m"),
            ));
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

    // v0.4.23 (A1): the main "dumps the whole document" offender — fold the
    // read payload for display (session/model/JSON keep the full content).
    format!(
        "{icon} \x1b[2m📄 Read {path} (lines {}-{} of {})\x1b[0m\n{}",
        start_line,
        end_line.max(start_line),
        total_lines,
        fold_tool_output(content, tool_output_line_budget(6), FoldKeep::Head, None)
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
            // v0.4.23 (A, codex catch): hunk/line COUNTS were capped but line
            // LENGTH was not — editing a minified file could still print MB.
            // ARIS_TOOL_OUTPUT_LINES=0 restores the uncapped preview too.
            let line = if tool_output_line_budget(6) == usize::MAX {
                line.to_string()
            } else {
                cap_fold_line(line)
            };
            match line.chars().next() {
                Some('+') => preview.push(format!("\x1b[38;5;70m{line}\x1b[0m")),
                Some('-') => preview.push(format!("\x1b[38;5;203m{line}\x1b[0m")),
                _ => preview.push(line),
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
    // v0.4.23 ride-along (codex): content mode returns numLines with NO
    // numMatches — the old summary showed a false "0 matches" above real
    // content. Report per-mode: returned lines when that's what we have.
    // Gate round-2 (codex): num_matches is an Option WITHOUT
    // skip_serializing_if — content mode serializes `"numMatches": null`, so
    // a bare `.get(...).is_some()` was ALWAYS true and the ride-along never
    // fired. Detect the mode by whether a real NUMBER is present.
    let matches_value = parsed
        .get("numMatches")
        .and_then(serde_json::Value::as_u64);
    let num_lines = parsed.get("numLines").and_then(serde_json::Value::as_u64);
    let stat = match (matches_value, num_lines) {
        (Some(n), _) => format!("{n} matches across {num_files} files"),
        (None, Some(l)) => format!("{l} returned lines across {num_files} files"),
        (None, None) => format!("{num_matches} matches across {num_files} files"),
    };
    let summary = format!("{icon} \x1b[38;5;245mgrep_search\x1b[0m {stat}");
    if !content.trim().is_empty() {
        // v0.4.23 (A3): fold the content-mode blob for display.
        format!(
            "{summary}\n{}",
            fold_tool_output(
                content.trim_end(),
                tool_output_line_budget(6),
                FoldKeep::Head,
                None
            )
        )
    } else if !filenames.is_empty() {
        format!("{summary}\n{filenames}")
    } else {
        summary
    }
}

/// v0.4.23 (A): how [`fold_tool_output`] keeps lines when folding.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FoldKeep {
    /// Keep the FIRST `budget` lines (read/grep — the opening matters).
    Head,
    /// Keep the first `budget/2` and last `budget - budget/2` lines (bash —
    /// the tail carries the error/summary; odd budgets favor the tail).
    HeadTail,
}

/// v0.4.23 (A): kept lines are additionally capped at this many chars so a
/// single million-char minified-JSON/SVG line can't defeat line folding.
/// `ARIS_TOOL_OUTPUT_LINES=0` disables BOTH the folding and this cap.
const FOLD_LINE_CHAR_CAP: usize = 240;

/// Resolve the per-tool display line budget: env unset → `default_lines`;
/// a positive integer overrides every tool's default; `0` → unlimited
/// (exact pre-v0.4.23 display, char cap included).
fn tool_output_line_budget(default_lines: usize) -> usize {
    match std::env::var("ARIS_TOOL_OUTPUT_LINES")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
    {
        Some(0) => usize::MAX,
        Some(n) => n,
        None => default_lines,
    }
}

/// Cap one kept line at [`FOLD_LINE_CHAR_CAP`] chars (char-boundary safe).
fn cap_fold_line(line: &str) -> String {
    if line.chars().count() <= FOLD_LINE_CHAR_CAP {
        return line.to_string();
    }
    let kept: String = line.chars().take(FOLD_LINE_CHAR_CAP).collect();
    format!("{kept}\x1b[2m…\x1b[0m")
}

/// v0.4.23 (A): the tool-output folding fix for the real-user report "aris
/// dumps the full content of documents it reads onto the screen". Display
/// layer ONLY — the session, model context, JSON output and /export always
/// keep the complete payload. `line_style` wraps each KEPT content line
/// (used to preserve bash stderr's red); the fold hint is always dim.
fn fold_tool_output(
    text: &str,
    budget: usize,
    keep: FoldKeep,
    line_style: Option<&str>,
) -> String {
    let style = |line: &str| match line_style {
        Some(color) => format!("{color}{}\x1b[0m", cap_fold_line(line)),
        None => cap_fold_line(line),
    };
    if budget == usize::MAX {
        // Unlimited: exact old display (no folding, no char cap), styling only.
        return match line_style {
            Some(color) => text
                .lines()
                .map(|l| format!("{color}{l}\x1b[0m"))
                .collect::<Vec<_>>()
                .join("\n"),
            None => text.to_string(),
        };
    }
    let lines: Vec<&str> = text.lines().collect();
    if lines.len() <= budget {
        return lines.iter().map(|l| style(l)).collect::<Vec<_>>().join("\n");
    }
    let hidden_hint = |n: usize| {
        format!(
            "\x1b[2m… (+{n} more lines — set ARIS_TOOL_OUTPUT_LINES=0 for full output)\x1b[0m"
        )
    };
    match keep {
        FoldKeep::Head => {
            let mut out: Vec<String> = lines[..budget].iter().map(|l| style(l)).collect();
            out.push(hidden_hint(lines.len() - budget));
            out.join("\n")
        }
        FoldKeep::HeadTail => {
            let head = budget / 2;
            let tail = budget - head;
            let mut out: Vec<String> = lines[..head].iter().map(|l| style(l)).collect();
            out.push(hidden_hint(lines.len() - budget));
            out.extend(lines[lines.len() - tail..].iter().map(|l| style(l)));
            out.join("\n")
        }
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

/// v0.4.17 (T5): outcome of the MCP-specific approval decision, computed by the
/// pure [`mcp_approval_decision`] so it can be exhaustively unit-tested without
/// touching stdin.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum McpApprovalDecision {
    /// Run the tool without prompting (trusted / session-approved / Prompt mode
    /// already confirmed via the generic gate / explicit Allow bypass).
    Allow,
    /// Interactively confirm with the user before running.
    Prompt,
    /// Refuse without prompting (non-interactive + untrusted).
    Deny,
}

/// v0.4.17 (T5): the MCP-specific safety decision, made AFTER the generic
/// [`PermissionPolicy`] gate has already allowed the call through to the
/// executor. MCP servers are out-of-process children the sandbox cannot
/// contain, so even `DangerFullAccess` must confirm an MCP tool call — UNLESS
/// the user pre-trusted the server or already approved it this session.
///
/// Pure (no I/O) so the full truth table is unit-tested. Inputs:
/// - `mode`: the active [`PermissionMode`].
/// - `trusted`: the originating server is in the user-scope `trust: true` set.
/// - `session_approved`: the user picked "don't ask again" for this server
///   earlier this session.
/// - `may_prompt`: the run can interactively prompt (the REPL turn path).
///   `false` for `--print`/one-shot/JSON output, where no prompt is possible.
///
/// Decision order:
/// 1. `trusted` ⇒ Allow (explicit user pre-approval).
/// 2. `session_approved` ⇒ Allow (already confirmed this session).
/// 3. `Prompt` mode ⇒ Allow — the generic gate ALREADY prompted y/N for this
///    tool (Prompt mode routes every tool to the prompter regardless of the
///    registered required mode), so a second MCP-specific prompt would be a
///    double confirmation. The generic prompt carries an MCP warning line (see
///    `CliPermissionPrompter::decide`).
/// 4. `Allow` mode ⇒ Allow — the explicit "bypass everything" mode (the generic
///    gate short-circuits it too). Distinct from `DangerFullAccess`.
/// 5. otherwise (`ReadOnly`/`WorkspaceWrite`/`DangerFullAccess`, untrusted):
///    Prompt if interactive, else Deny.
const fn mcp_approval_decision(
    mode: PermissionMode,
    trusted: bool,
    session_approved: bool,
    may_prompt: bool,
) -> McpApprovalDecision {
    if trusted || session_approved {
        return McpApprovalDecision::Allow;
    }
    match mode {
        // Generic gate already prompted (Prompt) / bypassed everything (Allow).
        PermissionMode::Prompt | PermissionMode::Allow => McpApprovalDecision::Allow,
        // Read-only / workspace-write / danger-full-access: the sandbox does
        // not cover the out-of-process MCP child, so confirm interactively;
        // when we can't prompt (non-interactive), deny.
        PermissionMode::ReadOnly
        | PermissionMode::WorkspaceWrite
        | PermissionMode::DangerFullAccess => {
            if may_prompt {
                McpApprovalDecision::Prompt
            } else {
                McpApprovalDecision::Deny
            }
        }
    }
}

struct CliToolExecutor {
    renderer: TerminalRenderer,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
    /// v0.4.17 (T4/T3): shared MCP runtime for dispatching `mcp__`-prefixed
    /// tool calls. `None` when no MCP servers are configured, in which case
    /// an `mcp__` name falls through to `execute_tool` and gets the usual
    /// `unsupported tool` error (preserving pre-v0.4.17 behavior).
    mcp: Option<SharedMcpRuntime>,
    /// v0.4.17 (T5): the active permission mode, used by the MCP-specific
    /// approval decision (see [`mcp_approval_decision`]).
    permission_mode: PermissionMode,
    /// v0.4.17 (T5): whether this run may interactively prompt for MCP
    /// approval. `true` only for the interactive REPL turn path; `false` for
    /// `--print`/one-shot/JSON output (where an untrusted MCP call is denied
    /// rather than silently run). Passed in explicitly — NOT derived from a
    /// stdin TTY check alone (codex R1 Track C2 P1).
    may_prompt: bool,
}

impl CliToolExecutor {
    fn new(
        allowed_tools: Option<AllowedToolSet>,
        emit_output: bool,
        mcp: Option<SharedMcpRuntime>,
        permission_mode: PermissionMode,
        may_prompt: bool,
    ) -> Self {
        Self {
            renderer: TerminalRenderer::new(),
            emit_output,
            allowed_tools,
            mcp,
            permission_mode,
            may_prompt,
        }
    }

    /// v0.4.17 (T3 + T5): dispatch a single `mcp__`-prefixed tool call through
    /// the shared MCP handle, AFTER clearing the MCP-specific approval gate.
    /// Returns the flattened textual content. An MCP-level `isError: true`
    /// result and any transport/JSON-RPC error both map to an `Err(ToolError)`
    /// — the message never includes credentials or env var names.
    ///
    /// SPIKE-A invariant: this runs in `CliToolExecutor::execute`, the pure
    /// synchronous tool-dispatch layer (outside any `block_on`), so the
    /// handle's internal `block_on` is safe.
    ///
    /// T5 approval flow (codex R1 Track C2): the route is resolved and the
    /// trust/session state SNAPSHOTTED first, then the `RefCell` borrow is
    /// dropped BEFORE any (blocking) interactive prompt — we never hold a
    /// borrow across user input. The pure [`mcp_approval_decision`] picks
    /// Allow/Prompt/Deny; a Prompt is resolved by a small executor-local stdin
    /// confirmation (the generic [`CliPermissionPrompter`] is not reachable from
    /// the executor, and threading it through the `ToolExecutor` trait would be
    /// a runtime-crate change this step forbids).
    fn dispatch_mcp(
        mcp: &SharedMcpRuntime,
        tool_name: &str,
        value: &serde_json::Value,
        permission_mode: PermissionMode,
        may_prompt: bool,
    ) -> Result<String, ToolError> {
        // Phase 1: resolve route + snapshot approval inputs, then DROP the
        // borrow so a prompt can't deadlock the RefCell.
        let (qualified, server_name, trusted, session_approved) = {
            let mcp_ref = mcp.borrow();
            // codex R2 Track C2: a name the catalog never produced has no
            // server identity to authorize against — deny rather than fall back
            // to the raw name (which would dispatch un-approved).
            let route = mcp_ref
                .catalog
                .route_for_advertised_name(tool_name)
                .ok_or_else(|| {
                    // tool_name is model-supplied; sanitize before it reaches the
                    // terminal renderer.
                    ToolError::new(format!(
                        "unknown MCP tool: {}",
                        sanitize_for_display(tool_name)
                    ))
                })?;
            let server_name = route.server_name.clone();
            (
                route.qualified_name.clone(),
                server_name.clone(),
                mcp_ref.trusted_servers.contains(&server_name),
                mcp_ref.session_approved.contains(&server_name),
            )
        };

        // Phase 2: pure decision (no borrow held).
        match mcp_approval_decision(permission_mode, trusted, session_approved, may_prompt) {
            McpApprovalDecision::Allow => {}
            McpApprovalDecision::Deny => {
                let safe_server = sanitize_for_display(&server_name);
                return Err(ToolError::new(format!(
                    "MCP tool `{}` (server `{safe_server}`) requires interactive \
                     approval or `mcpServers.{safe_server}.trust: true` in your user config; \
                     not run in a non-interactive session.",
                    sanitize_for_display(tool_name)
                )));
            }
            McpApprovalDecision::Prompt => {
                // No borrow held while we block on stdin.
                match prompt_mcp_approval(tool_name, &server_name) {
                    McpPromptOutcome::AllowOnce => {}
                    McpPromptOutcome::AllowSession => {
                        mcp.borrow_mut()
                            .session_approved
                            .insert(server_name.clone());
                    }
                    McpPromptOutcome::Deny => {
                        return Err(ToolError::new(format!(
                            "MCP tool `{}` (server `{}`) denied by user.",
                            sanitize_for_display(tool_name),
                            sanitize_for_display(&server_name)
                        )));
                    }
                }
            }
        }

        // Phase 3: dispatch (re-borrow for the call).
        let mut mcp = mcp.borrow_mut();
        let arguments = if value.is_null() {
            None
        } else {
            Some(value.clone())
        };
        let response = mcp
            .handle
            .call_tool(&qualified, arguments)
            .map_err(|error| ToolError::new(format!("MCP tool call failed: {error}")))?;
        if let Some(rpc_error) = response.error {
            return Err(ToolError::new(format!(
                "MCP tool `{tool_name}` returned an error: {}",
                rpc_error.message
            )));
        }
        let result = response.result.ok_or_else(|| {
            ToolError::new(format!("MCP tool `{tool_name}` returned an empty response"))
        })?;
        let text = mcp_result_text(&result.content, result.structured_content.as_ref());
        if result.is_error.unwrap_or(false) {
            return Err(ToolError::new(if text.is_empty() {
                format!("MCP tool `{tool_name}` reported an error")
            } else {
                text
            }));
        }
        Ok(text)
    }
}

/// v0.4.17 (T5): the user's answer to the MCP approval prompt.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum McpPromptOutcome {
    /// Run this one call only; ask again next time.
    AllowOnce,
    /// Run this call and don't ask again for this server this session.
    AllowSession,
    /// Refuse this call.
    Deny,
}

/// v0.4.17 (T5): interactively confirm an MCP tool call on stdin. Mirrors the
/// style of [`CliPermissionPrompter::decide`] (no `RefCell` borrow is held by
/// the caller while this blocks). Surfaces the RAW server name + tool name and
/// the out-of-process / sandbox-uncovered caveat, and offers: allow once /
/// don't-ask-again-for-this-server / deny. A read error or any unrecognized
/// input is treated as Deny (fail-closed). Carries no credentials.
fn prompt_mcp_approval(tool_name: &str, server_name: &str) -> McpPromptOutcome {
    println!();
    println!("MCP tool approval required");
    // Sanitize raw config-sourced names against terminal control-char injection.
    println!("  Server (raw)  {}", sanitize_for_display(server_name));
    println!("  Tool          {}", sanitize_for_display(tool_name));
    println!(
        "  Note          MCP servers run as external processes; the sandbox does NOT cover them."
    );
    print!("Approve? [o]nce / [s]ession (don't ask again for this server) / [N]o deny: ");
    let _ = io::stdout().flush();

    let mut response = String::new();
    match io::stdin().read_line(&mut response) {
        Ok(_) => match response.trim().to_ascii_lowercase().as_str() {
            "o" | "once" | "y" | "yes" => McpPromptOutcome::AllowOnce,
            "s" | "session" => McpPromptOutcome::AllowSession,
            _ => McpPromptOutcome::Deny,
        },
        Err(_) => McpPromptOutcome::Deny,
    }
}

/// v0.4.17 (T3): flatten an MCP tool result's content blocks into a single
/// string. `text` blocks contribute their text; any other block kind is
/// serialized to a JSON line so nothing is silently dropped.
fn flatten_mcp_content(content: &[runtime::McpToolCallContent]) -> String {
    let mut parts: Vec<String> = Vec::with_capacity(content.len());
    for block in content {
        if block.kind == "text" {
            if let Some(serde_json::Value::String(text)) = block.data.get("text") {
                parts.push(text.clone());
                continue;
            }
        }
        // Non-text (or malformed text) block: emit a JSON line. Reconstruct
        // the full block (kind + flattened data) so structured content
        // survives round-trip.
        let mut obj = serde_json::Map::new();
        obj.insert(
            "type".to_string(),
            serde_json::Value::String(block.kind.clone()),
        );
        for (key, value) in &block.data {
            obj.insert(key.clone(), value.clone());
        }
        parts.push(serde_json::Value::Object(obj).to_string());
    }
    parts.join("\n")
}

/// v0.4.21 (#4): resolve an MCP tool result to its text payload. Flattens the
/// `content` blocks via [`flatten_mcp_content`]; when that yields no meaningful
/// text (empty or whitespace-only) but the server supplied `structuredContent`,
/// fall back to the JSON-serialized structured payload. A spec-valid server that
/// returns ONLY `structuredContent` (absent/empty `content`) would otherwise hand
/// the model an empty tool result. Content-bearing results are byte-identical to
/// the pre-fallback behavior — the structured payload is consulted only when the
/// flattened text is empty.
fn mcp_result_text(
    content: &[runtime::McpToolCallContent],
    structured: Option<&serde_json::Value>,
) -> String {
    let mut text = flatten_mcp_content(content);
    if text.trim().is_empty() {
        if let Some(structured) = structured {
            text = structured.to_string();
        }
    }
    text
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
        // v0.4.17 (T3): intercept MCP-prefixed names BEFORE the static
        // `execute_tool` match. Only when an MCP runtime is present — without
        // one, the name falls through to `execute_tool` → `unsupported tool`
        // (the T6 structural guarantee that subagents never reach MCP, and the
        // pre-v0.4.17 behavior for users without `mcpServers`).
        if tool_name.starts_with("mcp__") {
            if let Some(mcp) = self.mcp.as_ref() {
                let result = Self::dispatch_mcp(
                    mcp,
                    tool_name,
                    &value,
                    self.permission_mode,
                    self.may_prompt,
                );
                if self.emit_output {
                    let (body, is_error) = match &result {
                        Ok(output) => (output.clone(), false),
                        Err(error) => (error.to_string(), true),
                    };
                    let markdown = format_tool_result(tool_name, &body, is_error);
                    self.renderer
                        .stream_markdown(&markdown, &mut io::stdout())
                        .map_err(|error| ToolError::new(error.to_string()))?;
                }
                return result;
            }
        }
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

/// v0.4.17 (T5): the generic [`PermissionPolicy`] plus the advertised MCP tool
/// names registered at the MINIMAL required mode ([`PermissionMode::ReadOnly`]).
/// See [`build_runtime`] for why the minimal mode (so the generic gate neither
/// blocks nor auto-grants MCP tools — it passes them to the executor's
/// MCP-specific approval). Static tools keep their own required modes from
/// [`tool_permission_specs`].
fn permission_policy_with_mcp(
    mode: PermissionMode,
    mcp_names: impl Iterator<Item = String>,
) -> PermissionPolicy {
    let policy = tool_permission_specs()
        .into_iter()
        .fold(PermissionPolicy::new(mode), |policy, spec| {
            policy.with_tool_requirement(spec.name, spec.required_permission)
        });
    mcp_names.fold(policy, |policy, name| {
        policy.with_tool_requirement(name, PermissionMode::ReadOnly)
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
    writeln!(out, "  aris setup                                          Configure API keys / model / language (interactive)")?;
    writeln!(
        out,
        "  aris doctor                                         Health check"
    )?;
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
    writeln!(out, "  Default:   Anthropic Claude (ANTHROPIC_API_KEY)")?;
    writeln!(
        out,
        "  OpenAI:    EXECUTOR_PROVIDER=openai EXECUTOR_API_KEY=xxx aris --model gpt-4o"
    )?;
    writeln!(
        out,
        "  DeepSeek:  Run `aris setup` → option 7 (DeepSeek) → base URL https://api.deepseek.com/anthropic"
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
    let creds_path = PathBuf::from(&home)
        .join(".claude")
        .join("credentials.json");
    if creds_path.exists() {
        return "OK (OAuth saved)";
    }
    // Check macOS Keychain for Claude Code's OAuth token. Respect the same
    // ARIS_DISABLE_KEYCHAIN escape hatch as the api crate's auth fallback so
    // the gate's "never touch the real Keychain" promise holds for doctor
    // too (codex R15).
    if api::keychain_disabled() {
        return "missing (Keychain check disabled)";
    }
    if let Ok(output) = Command::new("security")
        .args([
            "find-generic-password",
            "-s",
            "Claude Code-credentials",
            "-w",
        ])
        .output()
    {
        if output.status.success() {
            return "OK (Keychain OAuth)";
        }
    }
    "NOT FOUND"
}

/// v0.4.17 (RW7): per-server outcome the doctor reports for a configured MCP
/// server. Computed by `run_doctor` (which does the I/O — spawn/initialize/
/// tools-list) and rendered by the pure [`mcp_doctor_section`] formatter.
#[derive(Debug, Clone, PartialEq, Eq)]
enum McpDoctorStatus {
    /// User-scope server that was spawned + initialized; `tool_count` tools
    /// discovered.
    Discovered { tool_count: usize },
    /// User-scope server that failed to spawn/initialize/list (reason carried
    /// for the user; never credentials).
    Failed { reason: String },
    /// User-scope server whose transport is not stdio (the only transport this
    /// build spawns). The manager records these in `unsupported_servers()`, not
    /// the spawn set — so without this they'd falsely render as "discovered, 0
    /// tools" (codex R Track C2 P2).
    Unsupported { transport: String },
    /// Project/local-scope server skipped by the T5 pre-discovery scope gate
    /// (not spawned).
    SkippedScope,
}

/// v0.4.17 (RW7): one row of the doctor MCP section.
#[derive(Debug, Clone, PartialEq, Eq)]
struct McpDoctorServer {
    name: String,
    scope: ConfigSource,
    trusted: bool,
    status: McpDoctorStatus,
}

/// v0.4.17 (RW7) step ①: PURE formatter for the doctor MCP section. Takes the
/// already-collected per-server outcomes and renders the section, or `None`
/// when no MCP servers are configured (so users who don't use MCP see nothing).
/// All I/O (spawn/initialize/discovery) stays in [`run_doctor`]; this function
/// is side-effect-free so it can be unit-tested.
///
/// RW7 sequence note: this replaced the old inline Check-6 warning whose text
/// claimed "Full tool dispatch into LLM context lands in v0.4.16" — that
/// placeholder is now false (dispatch landed in v0.4.17). The baseline of the
/// OLD text was captured + then updated here in one move (the section was never
/// unit-tested before, so there was no separate locked baseline to break);
/// `mcp_doctor_section_*` tests now lock this real-status text.
fn mcp_doctor_section(servers: &[McpDoctorServer]) -> Option<String> {
    use std::fmt::Write as _;
    if servers.is_empty() {
        return None;
    }
    let discovered: usize = servers
        .iter()
        .filter(|s| matches!(s.status, McpDoctorStatus::Discovered { .. }))
        .count();
    let mut out = String::new();
    // `write!` to a String is infallible; ignore the Result.
    let _ = writeln!(
        out,
        "  MCP servers:  {} configured ({} user-scope discovered)",
        servers.len(),
        discovered
    );
    for server in servers {
        let trust = if server.trusted { ", trusted" } else { "" };
        let scope = scope_label(server.scope);
        // Sanitize the raw config-sourced name against terminal injection.
        let name = sanitize_for_display(&server.name);
        let _ = match &server.status {
            McpDoctorStatus::Discovered { tool_count } => writeln!(
                out,
                "    - {name} [{scope}{trust}]: spawned + initialized, {tool_count} tool(s)"
            ),
            McpDoctorStatus::Failed { reason } => writeln!(
                out,
                "    - {name} [{scope}{trust}]: FAILED — {}",
                sanitize_for_display(reason)
            ),
            McpDoctorStatus::Unsupported { transport } => writeln!(
                out,
                "    - {name} [{scope}]: unsupported transport ({transport}); only stdio is spawned"
            ),
            McpDoctorStatus::SkippedScope => writeln!(
                out,
                "    - {name} [{scope}]: skipped (project/local scope is not spawned; \
                 move to user config to enable)"
            ),
        };
    }
    out.push_str(
        "    Note: only user-scope servers are spawned at startup; tool CALLS are \
         approval-gated (trusted servers skip the prompt).\n",
    );
    // v0.4.17 (T10/P2 / RW7 step ③, deliberately updated): make the path
    // mismatch between the legacy "Codex MCP" check and the runtime's
    // ConfigLoader scope user-visible (previously this was only a source
    // comment). The "Codex MCP" line above reads ~/.claude.json; the runtime
    // (and this per-server section) reads mcpServers from settings.json.
    out.push_str(
        "    Note: legacy ~/.claude.json is checked separately for Codex MCP; \
         mcpServers used at runtime live in <config_home>/settings.json.",
    );
    Some(out)
}

/// v0.4.17 (RW7): collect per-server MCP doctor outcomes (the I/O side that
/// feeds the pure [`mcp_doctor_section`]). Project/local servers are reported
/// as scope-skipped without spawning; user-scope servers are spawned once and
/// reported as discovered (with tool count) or failed. Best-effort: a hard
/// config/handle error yields an empty list rather than failing `aris doctor`.
fn collect_mcp_doctor_servers(cwd: &std::path::Path) -> Vec<McpDoctorServer> {
    let Ok(config) = runtime::ConfigLoader::default_for(cwd).load() else {
        return Vec::new();
    };
    let servers = config.mcp().servers();
    if servers.is_empty() {
        return Vec::new();
    }

    // Partition by scope (mirror McpRuntime::discover): only user-scope is
    // spawned.
    let mut user_scope: BTreeMap<String, runtime::ScopedMcpServerConfig> = BTreeMap::new();
    let mut rows: Vec<McpDoctorServer> = Vec::new();
    for (name, scoped) in servers {
        let trusted = matches!(&scoped.config, runtime::McpServerConfig::Stdio(s) if s.trust() == Some(true))
            && scoped.scope == ConfigSource::User;
        match scoped.scope {
            ConfigSource::User => {
                user_scope.insert(name.clone(), scoped.clone());
                // status filled in after discovery; placeholder Failed replaced
                // below.
                rows.push(McpDoctorServer {
                    name: name.clone(),
                    scope: scoped.scope,
                    trusted,
                    status: McpDoctorStatus::Failed {
                        reason: "not discovered".to_string(),
                    },
                });
            }
            ConfigSource::Project | ConfigSource::Local => {
                rows.push(McpDoctorServer {
                    name: name.clone(),
                    scope: scoped.scope,
                    trusted: false,
                    status: McpDoctorStatus::SkippedScope,
                });
            }
        }
    }

    if !user_scope.is_empty() {
        let manager = runtime::McpServerManager::from_servers(&user_scope);
        if let Ok(mut handle) = runtime::McpManagerHandle::from_manager(manager) {
            let discovered = handle.discover_tools().unwrap_or_default();
            // Tools per server name.
            let mut counts: BTreeMap<String, usize> = BTreeMap::new();
            for tool in &discovered {
                *counts.entry(tool.server_name.clone()).or_insert(0) += 1;
            }
            // Per-server failures from this pass.
            let failures: BTreeMap<String, String> = handle
                .discovery_failures()
                .iter()
                .map(|f| (f.server_name.clone(), f.reason.clone()))
                .collect();
            // Non-stdio servers are recorded here (not the spawn set), so a
            // user-scope SSE/HTTP/WS server must NOT render as "discovered, 0
            // tools" (codex R Track C2 P2).
            let unsupported: BTreeMap<String, String> = handle
                .unsupported_servers()
                .iter()
                .map(|u| (u.server_name.clone(), format!("{:?}", u.transport)))
                .collect();
            for row in &mut rows {
                if row.scope != ConfigSource::User {
                    continue;
                }
                row.status = if let Some(transport) = unsupported.get(&row.name) {
                    McpDoctorStatus::Unsupported {
                        transport: transport.clone(),
                    }
                } else if let Some(reason) = failures.get(&row.name) {
                    McpDoctorStatus::Failed {
                        reason: reason.clone(),
                    }
                } else {
                    McpDoctorStatus::Discovered {
                        tool_count: counts.get(&row.name).copied().unwrap_or(0),
                    }
                };
            }
            let _ = handle.shutdown();
        }
    }

    rows
}

fn run_doctor() -> Result<(), Box<dyn std::error::Error>> {
    println!("ARIS Doctor v{VERSION}");
    println!();

    let mut all_ok = true;

    // Check 0: Executor provider
    let executor_provider =
        std::env::var("EXECUTOR_PROVIDER").unwrap_or_else(|_| "anthropic".into());
    print!("  Executor:     ");
    if executor_provider == "openai" {
        let base = std::env::var("EXECUTOR_BASE_URL")
            .unwrap_or_else(|_| "https://api.openai.com/v1".into());
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

    // Check 0b: ARIS config health (#259) → v0.4.22 (C7): structured severity.
    // Problems (malformed/misplaced config) flip all_ok; Warnings (unrecognized
    // top-level keys — possibly a newer-version config or a nested structure)
    // print as NOTE and deliberately do NOT fail doctor (forward compat).
    print!("  ARIS config:  ");
    let diags = config::ArisConfig::diagnose_misconfig();
    let problems: Vec<&String> = diags
        .iter()
        .filter_map(|d| match d {
            config::ConfigDiagnostic::Problem(h) => Some(h),
            config::ConfigDiagnostic::Warning(_) => None,
        })
        .collect();
    let warnings: Vec<&String> = diags
        .iter()
        .filter_map(|d| match d {
            config::ConfigDiagnostic::Warning(h) => Some(h),
            config::ConfigDiagnostic::Problem(_) => None,
        })
        .collect();
    if !problems.is_empty() {
        println!("PROBLEM");
        for hint in problems {
            println!("                {hint}");
        }
        all_ok = false;
    } else {
        println!("OK (~/.config/aris/config.json — flat JSON, or defaults)");
    }
    for hint in warnings {
        println!("                NOTE: {hint}");
    }

    // Check 1: API auth
    let auth_status = check_auth_status();
    println!("  API auth:     {auth_status}");
    if auth_status == "NOT FOUND" && executor_provider != "openai" {
        all_ok = false;
    }

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
    let reviewer_keys: &[(&str, &str)] = &[
        ("OPENAI_API_KEY", "OpenAI"),
        ("GEMINI_API_KEY", "Gemini"),
        ("GLM_API_KEY", "GLM"),
        ("MINIMAX_API_KEY", "MiniMax"),
        ("KIMI_API_KEY", "Kimi"),
        ("ARIS_REVIEWER_AUTH_TOKEN", "Anthropic-compat"),
        // run_llm_review also accepts ANTHROPIC_AUTH_TOKEN as a fallback for
        // anthropic-compat reviewer (see tools/src/lib.rs).
        ("ANTHROPIC_AUTH_TOKEN", "Anthropic-compat"),
    ];
    let found: Vec<&str> = reviewer_keys
        .iter()
        .filter(|(var, _)| std::env::var(var).ok().is_some_and(|v| !v.is_empty()))
        .map(|(_, label)| *label)
        .collect();
    if found.is_empty() {
        println!(
            "NOT FOUND (set one of: OPENAI_API_KEY / GEMINI_API_KEY / GLM_API_KEY / MINIMAX_API_KEY / KIMI_API_KEY / ARIS_REVIEWER_AUTH_TOKEN / ANTHROPIC_AUTH_TOKEN)"
        );
    } else {
        println!("OK ({})", found.join(", "));
    }

    // Check 3: Codex CLI — v0.4.22 (C6/Δ4-4): three-state classification; a
    // .cmd/.bat shim resolves on `where` but the MCP client spawns `codex`
    // directly, so a shim must not read as a clean "OK". v0.4.22 (B6/Δ4-6):
    // soft version + stale-entry notes; neither flips all_ok.
    print!("  Codex CLI:    ");
    match config::probe_codex() {
        config::CodexProbe::NativeExe(path) => {
            println!("OK ({})", path.display());
            if let Some(note) = codex_version_note(&path) {
                println!("                NOTE: {note}");
            }
        }
        config::CodexProbe::ScriptShim(path) => {
            println!("FOUND AS SCRIPT SHIM ({})", path.display());
            println!(
                "                NOTE: ARIS's MCP client spawns `codex` directly and cannot \
                 spawn a .cmd/.bat shim in v0.4.22 — install the native codex binary if \
                 `mcp__codex__codex` fails to start."
            );
        }
        config::CodexProbe::Missing => {
            println!("NOT FOUND (optional)");
        }
    }
    if let Some(note) = stale_codex_entry_note() {
        println!("                NOTE: {note}");
    }

    // Check 4 (v0.4.12 #238): Sandbox effective config
    print!("  Sandbox:      ");
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    let sandbox_config = runtime::ConfigLoader::default_for(&cwd)
        .load()
        .map(|rc| rc.sandbox().clone())
        .unwrap_or_default();
    let strict = sandbox_config.is_strict();
    let enabled = sandbox_config.enabled.unwrap_or(true);
    // codex round-3 #4: detect any explicit sandbox field, not only `enabled`.
    let has_any_explicit_sandbox_field = sandbox_config.enabled.is_some()
        || sandbox_config.namespace_restrictions.is_some()
        || sandbox_config.network_isolation.is_some()
        || sandbox_config.filesystem_mode.is_some()
        || !sandbox_config.allowed_mounts.is_empty()
        || sandbox_config.strict_mode.is_some();
    if strict {
        println!(
            "strict (config), enabled={enabled} — LLM override of `dangerouslyDisableSandbox` is IGNORED"
        );
    } else if has_any_explicit_sandbox_field {
        println!(
            "permissive (config), enabled={enabled} — LLM tool calls can override per-command via `dangerouslyDisableSandbox`"
        );
    } else {
        println!(
            "default-allow (no config) — set `sandbox.strictMode: true` in settings.json to hard-lock"
        );
    }

    // Check 5: Codex MCP in config
    print!("  Codex MCP:    ");
    let home = runtime::home_dir();
    let config_path = PathBuf::from(&home).join(".claude.json");
    if config_path.exists() {
        if let Ok(content) = fs::read_to_string(&config_path) {
            if let Ok(config) = serde_json::from_str::<serde_json::Value>(&content) {
                if config
                    .get("mcpServers")
                    .and_then(|s| s.as_object())
                    .map_or(false, |s| s.contains_key("codex"))
                {
                    println!("OK (configured in ~/.claude.json)");
                } else {
                    println!("NOT CONFIGURED (edit ~/.claude.json by hand or via Claude Code's own `claude mcp add`)");
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
    // v0.4.17 (T10/P2): user-visible disclosure of the path mismatch (was only a
    // source comment). Always printed so it shows even when no settings.json MCP
    // servers exist (the per-server section below is omitted in that case).
    println!(
        "                note: legacy ~/.claude.json is checked for Codex MCP; \
         mcpServers used at runtime live in <config_home>/settings.json"
    );

    // Check 6 (v0.4.17 RW7 step ③): real per-server MCP status.
    //
    // Disclosure (plan RW7): the "Codex MCP" check above reads `~/.claude.json`
    // directly, which is NOT the same path set the runtime `ConfigLoader`
    // resolves (user `~/.claude/settings.json` + project `.claude/settings.json`
    // + local `.claude/settings.local.json`). The section below uses the
    // ConfigLoader-resolved `mcpServers`, so a codex server declared only in
    // `~/.claude.json` may show under "Codex MCP" but not here, and vice versa.
    // This is surfaced rather than reconciled (no path refactor this version).
    //
    // We do a one-shot discovery pass over USER-scope servers (the same scope
    // gate as `McpRuntime::discover`): project/local servers are reported as
    // skipped (never spawned). Per-server timeouts are honored by the manager's
    // own `discover_tools` (per-server `requestTimeoutSecs`), so a hung server
    // can't wedge the doctor. Discovery is best-effort: any hard error degrades
    // to an empty/partial section rather than failing the whole command.
    let doctor_servers = collect_mcp_doctor_servers(&cwd);
    if let Some(section) = mcp_doctor_section(&doctor_servers) {
        println!();
        println!("{section}");
    }

    println!();
    if all_ok {
        println!("All checks passed.");
    } else {
        println!("Some checks failed. Run `aris setup` to (re)configure API keys/models, or fix the items above manually.");
    }
    Ok(())
}

/// ARIS-specific skills directory (highest priority).
fn dirs_aris_skills() -> PathBuf {
    let home = runtime::home_dir();
    PathBuf::from(home)
        .join(".config")
        .join("aris")
        .join("skills")
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

// v0.4.22 (C6): the old `which`-only probe lived here; doctor now uses
// config::probe_codex() — the shared three-state classifier (NativeExe /
// ScriptShim / Missing, `where` on Windows, CRLF-safe, .exe-preferring).

/// v0.4.22 (B6): run `--version` via the RESOLVED codex path and return a
/// doctor NOTE when the version is too old / unclassifiable. `None` = supported
/// (or the probe itself failed — the presence check already reported).
fn codex_version_note(path: &Path) -> Option<String> {
    let output = Command::new(path).arg("--version").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let raw = String::from_utf8_lossy(&output.stdout);
    codex_version_support_note(raw.trim())
}

/// v0.4.22 (B6/Δ4-6): deterministic version oracle over `codex --version`
/// output (real shape: "codex-cli 0.144.1"; bare semver also accepted).
/// `None` = supported (>= 0.144.1 stable). Old stable → old-version note.
/// Prerelease → conservative treat-as-old note. Malformed → "unknown
/// version" note (DECIDED: note, not silent). Never a Problem; the doctor
/// prints these as NOTE and never flips all_ok.
fn codex_version_support_note(raw: &str) -> Option<String> {
    const UPGRADE_HINT: &str = "'ultra' reasoning effort and gpt-5.6-sol may be unavailable — \
         deep-audit skills degrade to xhigh per the fallback chain. Upgrade codex-cli and \
         restart the session.";
    let Some(token) = raw
        .split_whitespace()
        .find(|t| t.chars().next().is_some_and(|c| c.is_ascii_digit()))
    else {
        return Some(format!("codex-cli version unrecognized ({raw:.40}) — {UPGRADE_HINT}"));
    };
    if token.contains('-') {
        // Prerelease (e.g. 0.144.1-beta.2): conservatively treat as pre-0.144.1.
        return Some(format!("codex-cli {token} is a prerelease — treating as pre-0.144.1: {UPGRADE_HINT}"));
    }
    let mut parts = token.split('.').map(str::parse::<u64>);
    let (Some(Ok(major)), Some(Ok(minor)), Some(Ok(patch))) =
        (parts.next(), parts.next(), parts.next())
    else {
        return Some(format!("codex-cli version unrecognized ({token:.40}) — {UPGRADE_HINT}"));
    };
    if (major, minor, patch) >= (0, 144, 1) {
        None
    } else {
        Some(format!("codex-cli {token} < 0.144.1: {UPGRADE_HINT}"))
    }
}

/// v0.4.22 (B6, gate round-2): does this `mcpServers.codex` entry carry the
/// v0.4.18 xhigh server floor? Pure over the JSON entry so both failure
/// shapes are covered: (a) args MISSING or not an array — the classic
/// pre-v0.4.18 entry, which the first cut wrongly skipped via `?`; (b) args
/// present but pinning a DIFFERENT effort (e.g. "medium"), which a bare
/// `contains("model_reasoning_effort")` wrongly accepted as the floor.
fn codex_entry_has_xhigh_floor(entry: &serde_json::Value) -> bool {
    entry
        .get("args")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|args| {
            args.iter().any(|a| {
                a.as_str().is_some_and(|s| {
                    s.contains("model_reasoning_effort") && s.contains("xhigh")
                })
            })
        })
}

/// v0.4.22 (B6): pre-v0.4.18 `mcpServers.codex` entries were written without
/// the `-c model_reasoning_effort="xhigh"` server floor and are never migrated
/// (the option-10 merge is deliberately non-clobbering). Reads the SAME
/// settings.json that option 10 writes and the runtime reads
/// (`CLAUDE_CONFIG_HOME` or `~/.claude`) — NOT the legacy `~/.claude.json`. Soft
/// note only; absent file/entry → None.
fn stale_codex_entry_note() -> Option<String> {
    let path = config::claude_config_home().join("settings.json");
    let content = fs::read_to_string(path).ok()?;
    let json: serde_json::Value = serde_json::from_str(&content).ok()?;
    let entry = json.get("mcpServers")?.get("codex")?;
    if codex_entry_has_xhigh_floor(entry) {
        None
    } else {
        Some(
            "your mcpServers.codex entry predates v0.4.18 and lacks the \
             `-c model_reasoning_effort=\"xhigh\"` server floor — bare codex calls may run \
             below xhigh. Edit settings.json to add args [\"mcp-server\", \"-c\", \
             \"model_reasoning_effort=\\\"xhigh\\\"\"] or remove the entry and re-run \
             `aris setup` (option 10)."
                .to_string(),
        )
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
        codex_version_support_note, deploy_meta_opt_hooks_to, filter_tool_specs,
        format_compact_report, format_cost_report, format_model_report,
        format_model_switch_report, format_permissions_report, format_permissions_switch_report,
        format_resume_report, format_status_report, format_tool_call_start, format_tool_result,
        normalize_permission_mode, parse_args, parse_git_status_metadata, print_help_to,
        push_output_block, render_config_report, render_memory_report, render_repl_help,
        fold_tool_output, next_default_fallback, resolve_model_alias, resolve_startup_model,
        response_to_events, resume_supported_slash_commands, reviewer_display_for,
        reviewer_model_matches_provider, reviewer_routing_nudge, status_context,
        turn_has_visible_assistant_text, CliAction, CliOutputFormat, FoldKeep, ModelSource,
        SlashCommand, StatusUsage, BANNER_CENTER, DEFAULT_MODEL, DEFAULT_MODEL_CHAIN,
    };
    use api::{MessageResponse, OutputContentBlock, Usage};
    use runtime::{
        AssistantEvent, ContentBlock, ConversationMessage, MessageRole, PermissionMode, TokenUsage,
        TurnSummary,
    };
    use serde_json::json;
    use std::path::PathBuf;

    // v0.4.20 (#1) → v0.4.22 (C1/C2): startup model resolution. Explicit
    // --model wins (even naming the default); the saved model applies only on
    // a matching transport family; OpenAI transport with no model source
    // fails fast. Env-dependent → serialized via the crate-wide env guard.
    #[test]
    fn resolve_startup_model_matrix() {
        let _g = crate::env_test_guard();
        let cfg_openai = crate::config::ArisConfig {
            executor_provider: Some("openai".to_string()),
            executor_model: Some("gpt-5.5".to_string()),
            ..Default::default()
        };
        let cfg_anthropic_saved = crate::config::ArisConfig {
            executor_model: Some("claude-sonnet-4-6".to_string()),
            ..Default::default()
        };
        let empty = crate::config::ArisConfig::default();

        // ── Anthropic transport (EXECUTOR_PROVIDER unset) ──
        std::env::remove_var("EXECUTOR_PROVIDER");
        // v0.4.20 lock: no --model + family-matching saved model → Configured.
        assert_eq!(
            resolve_startup_model(None, &cfg_anthropic_saved).unwrap(),
            (
                "claude-sonnet-4-6".to_string(),
                ModelSource::Configured
            )
        );
        // C1: explicit --model beats the saved model — including the alias
        // and the FULL default id (a reproducibility contract).
        assert_eq!(
            resolve_startup_model(Some("opus".to_string()), &cfg_anthropic_saved).unwrap(),
            (DEFAULT_MODEL.to_string(), ModelSource::CliExplicit)
        );
        assert_eq!(
            resolve_startup_model(Some(DEFAULT_MODEL.to_string()), &cfg_anthropic_saved).unwrap(),
            (DEFAULT_MODEL.to_string(), ModelSource::CliExplicit)
        );
        // C2: saved OpenAI-family model must NOT leak onto the Anthropic
        // transport (shell EXECUTOR_PROVIDER=anthropic overrode a saved
        // OpenAI config) → BuiltInDefault, not gpt-5.5.
        assert_eq!(
            resolve_startup_model(None, &cfg_openai).unwrap(),
            (DEFAULT_MODEL.to_string(), ModelSource::BuiltInDefault)
        );
        // Nothing anywhere → BuiltInDefault.
        assert_eq!(
            resolve_startup_model(None, &empty).unwrap(),
            (DEFAULT_MODEL.to_string(), ModelSource::BuiltInDefault)
        );

        // ── OpenAI transport ──
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        // v0.4.20 lock: saved openai config still applies its model.
        assert_eq!(
            resolve_startup_model(None, &cfg_openai).unwrap(),
            ("gpt-5.5".to_string(), ModelSource::Configured)
        );
        // C2 reverse fail-fast: OpenAI transport + Anthropic-family/no saved
        // model → error (never send the Claude default to an OpenAI endpoint).
        assert!(resolve_startup_model(None, &cfg_anthropic_saved).is_err());
        assert!(resolve_startup_model(None, &empty).is_err());
        // Explicit --model bypasses the fail-fast (user owns the choice); on
        // the OpenAI transport aliases pass through unresolved.
        assert_eq!(
            resolve_startup_model(Some("gpt-5.6-sol".to_string()), &empty).unwrap(),
            ("gpt-5.6-sol".to_string(), ModelSource::CliExplicit)
        );
        std::env::remove_var("EXECUTOR_PROVIDER");
    }

    // v0.4.22 (C1): only non-explicit sources may silently walk the chain.
    #[test]
    fn model_source_gates_availability_fallback() {
        assert!(ModelSource::Configured.allows_availability_fallback());
        assert!(ModelSource::BuiltInDefault.allows_availability_fallback());
        assert!(!ModelSource::CliExplicit.allows_availability_fallback());
        assert!(!ModelSource::ReplExplicit.allows_availability_fallback());
    }

    // v0.4.22 (C2, gate round-2 BLOCKER lock): the wizard's config must become
    // the active config for startup model resolution.
    #[test]
    fn wizard_config_becomes_active_config() {
        use super::adopt_wizard_config;
        let old = crate::config::ArisConfig {
            executor_provider: Some("openai".to_string()),
            executor_model: Some("stale-model".to_string()),
            ..Default::default()
        };
        let wizard = crate::config::ArisConfig {
            executor_model: Some("deepseek-v4-pro".to_string()),
            ..Default::default()
        };
        // Wizard ran → its config wins (the round-2 blocker was resolving
        // against the stale pre-wizard config).
        assert_eq!(
            adopt_wizard_config(old.clone(), Some(wizard.clone())).executor_model(),
            Some("deepseek-v4-pro")
        );
        // No wizard → the loaded config stands.
        assert_eq!(
            adopt_wizard_config(old, None).executor_model(),
            Some("stale-model")
        );
    }

    // v0.4.22 (B6, gate round-2): the xhigh-floor predicate covers BOTH stale
    // shapes — args missing entirely (the classic pre-v0.4.18 entry) and args
    // pinning a different effort.
    #[test]
    fn codex_entry_xhigh_floor_predicate() {
        use super::codex_entry_has_xhigh_floor;
        // Real v0.4.18+ entry → has the floor.
        assert!(codex_entry_has_xhigh_floor(&json!({
            "command": "codex",
            "args": ["mcp-server", "-c", "model_reasoning_effort=\"xhigh\""]
        })));
        // Pre-v0.4.18 entry: NO args at all → lacks the floor (the first cut
        // returned None here via `?` and never noted exactly this case).
        assert!(!codex_entry_has_xhigh_floor(&json!({ "command": "codex" })));
        // args present but a DIFFERENT effort pinned → lacks the xhigh floor
        // (a bare contains("model_reasoning_effort") wrongly passed this).
        assert!(!codex_entry_has_xhigh_floor(&json!({
            "command": "codex",
            "args": ["mcp-server", "-c", "model_reasoning_effort=\"medium\""]
        })));
        // args not an array → lacks the floor.
        assert!(!codex_entry_has_xhigh_floor(&json!({
            "command": "codex",
            "args": "mcp-server"
        })));
    }

    // v0.4.22 (Δ4-3, gate round-2): the /reviewer command's four states.
    #[test]
    fn reviewer_command_gate_four_states() {
        use super::{reviewer_command_gate, ReviewerCmdGate};
        // (1) Pure Codex, bare /reviewer → status display only.
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), None, None),
            ReviewerCmdGate::PureCodexStatus
        );
        // Blank fallback counts as none.
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), Some("  "), None),
            ReviewerCmdGate::PureCodexStatus
        );
        // (2) Pure Codex, /reviewer <model> → refuse with /setup guidance.
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), None, Some("gpt-5.5")),
            ReviewerCmdGate::PureCodexRefuseExplicit
        );
        // (3) Codex + known-provider fallback: cross-family explicit model is
        // rejected; same-family proceeds; custom accepts any non-blank model.
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), Some("gemini"), Some("gpt-5.5")),
            ReviewerCmdGate::CrossFamilyReject
        );
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), Some("gemini"), Some("gemini-2.5-pro")),
            ReviewerCmdGate::Allow
        );
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), Some("custom"), Some("my-proxy-model")),
            ReviewerCmdGate::Allow
        );
        // Menu form with a fallback → proceeds (restricted menu).
        assert_eq!(
            reviewer_command_gate(Some("codex-mcp"), Some("openai"), None),
            ReviewerCmdGate::Allow
        );
        // (4) Non-Codex primary → current behavior, no gating.
        assert_eq!(
            reviewer_command_gate(Some("openai"), None, Some("gemini-2.5-pro")),
            ReviewerCmdGate::Allow
        );
        assert_eq!(reviewer_command_gate(None, None, None), ReviewerCmdGate::Allow);
    }

    // v0.4.22 (Δ4-5, gate round-2): the inline /setup guard runs BEFORE any
    // env/runtime mutation; it must reject an OpenAI/custom config whose model
    // is absent/blank and pass everything else. (The fn touches no env/runtime
    // by construction — the caller sequences it ahead of force_apply_to_env.)
    #[test]
    fn inline_setup_guard_rejects_blank_openai_model() {
        use super::inline_setup_guard;
        let blank_openai = crate::config::ArisConfig {
            executor_provider: Some("openai".to_string()),
            executor_model: Some("   ".to_string()),
            ..Default::default()
        };
        assert!(inline_setup_guard(&blank_openai).is_err());
        let missing_custom = crate::config::ArisConfig {
            executor_provider: Some("custom".to_string()),
            ..Default::default()
        };
        assert!(inline_setup_guard(&missing_custom).is_err());
        let ok_openai = crate::config::ArisConfig {
            executor_provider: Some("openai".to_string()),
            executor_model: Some("gpt-5.5".to_string()),
            ..Default::default()
        };
        assert!(inline_setup_guard(&ok_openai).is_ok());
        // Anthropic-family configs never need an explicit model.
        let anthropic_blank = crate::config::ArisConfig::default();
        assert!(inline_setup_guard(&anthropic_blank).is_ok());
    }

    // v0.4.22 (B5): three-state reviewer display — the HTTP fallback model is
    // never presented as the Codex primary.
    #[test]
    fn reviewer_display_three_states() {
        assert_eq!(
            reviewer_display_for(Some("codex-mcp"), None, "gpt-5.5"),
            "Codex MCP · gpt-5.6-sol preferred"
        );
        assert_eq!(
            reviewer_display_for(Some("codex-mcp"), Some("gemini"), "gemini-2.5-pro"),
            "Codex MCP · gpt-5.6-sol preferred (HTTP fallback: gemini · gemini-2.5-pro)"
        );
        // Blank fallback provider counts as none.
        assert_eq!(
            reviewer_display_for(Some("codex-mcp"), Some("  "), "gpt-5.5"),
            "Codex MCP · gpt-5.6-sol preferred"
        );
        assert_eq!(reviewer_display_for(Some("openai"), None, "gpt-5.5"), "gpt-5.5");
        assert_eq!(reviewer_display_for(None, None, "gpt-5.5"), "gpt-5.5");
    }

    // v0.4.22 (Δ4-3/Δ5-3): catalog-family check for `/reviewer <model>` under
    // a Codex-primary + HTTP-fallback setup.
    #[test]
    fn reviewer_model_provider_catalog_check() {
        // Known providers reject cross-family ids.
        assert!(!reviewer_model_matches_provider("gemini", "gpt-5.5"));
        assert!(reviewer_model_matches_provider("gemini", "gemini-2.5-pro"));
        assert!(reviewer_model_matches_provider("openai", "gpt-5.6-sol"));
        assert!(reviewer_model_matches_provider("openai", "o4-mini"));
        assert!(!reviewer_model_matches_provider("openai", "gemini-2.5-pro"));
        assert!(reviewer_model_matches_provider("glm", "GLM-5"));
        assert!(reviewer_model_matches_provider("minimax", "MiniMax-M2.7"));
        assert!(reviewer_model_matches_provider("kimi", "kimi-k2.5"));
        // Custom has no catalog: any non-blank explicit model is accepted.
        assert!(reviewer_model_matches_provider("custom", "my-proxy-model"));
        assert!(!reviewer_model_matches_provider("custom", "   "));
        // Unknown provider labels are permissive.
        assert!(reviewer_model_matches_provider("someday", "anything"));
    }

    // v0.4.22 (B5): every banner center line is exactly 34 visible chars once
    // ANSI escapes are stripped (the pixel sprites on either side assume it).
    #[test]
    fn banner_center_lines_are_34_visible_chars() {
        for (i, line) in BANNER_CENTER.iter().enumerate() {
            // Strip CSI sequences: ESC '[' ... final byte in @-~.
            let mut visible = 0usize;
            let mut chars = line.chars().peekable();
            while let Some(c) = chars.next() {
                if c == '\u{1b}' {
                    if chars.peek() == Some(&'[') {
                        chars.next();
                        for esc in chars.by_ref() {
                            if ('@'..='~').contains(&esc) {
                                break;
                            }
                        }
                    }
                    continue;
                }
                visible += 1;
            }
            assert_eq!(visible, 34, "banner center line {i} is {visible} visible chars: {line:?}");
        }
    }

    // v0.4.23 (A): tool-output folding — display layer only.
    #[test]
    fn fold_head_keeps_first_lines_and_hints_the_rest() {
        let text = (1..=10).map(|i| format!("line{i}")).collect::<Vec<_>>().join("\n");
        let folded = fold_tool_output(&text, 6, FoldKeep::Head, None);
        let lines: Vec<&str> = folded.lines().collect();
        assert_eq!(lines.len(), 7, "6 kept + 1 hint: {folded}");
        assert!(lines[0].contains("line1") && lines[5].contains("line6"));
        assert!(
            lines[6].contains("+4 more lines")
                && lines[6].contains("ARIS_TOOL_OUTPUT_LINES=0"),
            "hint must name the count and the escape hatch: {}",
            lines[6]
        );
        assert!(!folded.contains("line7"), "hidden lines must not appear");
    }

    #[test]
    fn fold_headtail_splits_budget_and_keeps_tail() {
        let text = (1..=20).map(|i| format!("line{i}")).collect::<Vec<_>>().join("\n");
        let folded = fold_tool_output(&text, 8, FoldKeep::HeadTail, None);
        let lines: Vec<&str> = folded.lines().collect();
        assert_eq!(lines.len(), 9, "4 head + hint + 4 tail: {folded}");
        assert!(lines[3].contains("line4"), "head keeps first budget/2");
        assert!(lines[4].contains("+12 more lines"));
        assert!(lines[5].contains("line17") && lines[8].contains("line20"), "tail keeps the end");
    }

    #[test]
    fn fold_within_budget_adds_no_hint() {
        let text = "a\nb\nc";
        let folded = fold_tool_output(text, 6, FoldKeep::Head, None);
        assert_eq!(folded, text);
    }

    #[test]
    fn fold_caps_single_huge_line() {
        // The minified-JSON case: line folding alone would keep a 500-char
        // line intact; the 240-char cap must trim it.
        let huge = "x".repeat(500);
        let folded = fold_tool_output(&huge, 6, FoldKeep::Head, None);
        let first = folded.lines().next().unwrap();
        assert!(first.starts_with(&"x".repeat(240)));
        assert!(!first.contains(&"x".repeat(241)), "must cap at 240 chars");
        assert!(first.contains('…'));
    }

    #[test]
    fn fold_unlimited_budget_is_exact_old_display() {
        let huge = format!("{}\n{}", "x".repeat(500), (1..=50).map(|i| i.to_string()).collect::<Vec<_>>().join("\n"));
        let folded = fold_tool_output(&huge, usize::MAX, FoldKeep::Head, None);
        assert_eq!(folded, huge, "budget=MAX (env 0) must be byte-identical");
    }

    #[test]
    fn fold_styles_kept_lines_but_not_the_hint() {
        let text = (1..=10).map(|i| format!("e{i}")).collect::<Vec<_>>().join("\n");
        let folded = fold_tool_output(&text, 4, FoldKeep::HeadTail, Some("\x1b[38;5;203m"));
        let lines: Vec<&str> = folded.lines().collect();
        assert!(lines[0].starts_with("\x1b[38;5;203m"), "kept stderr lines stay red");
        assert!(lines[2].starts_with("\x1b[2m…"), "the hint is dim, not red: {}", lines[2]);
    }

    // v0.4.23 (A): env resolution — unset → default, N → N, 0 → unlimited.
    #[test]
    fn tool_output_line_budget_env_resolution() {
        let _g = crate::env_test_guard();
        std::env::remove_var("ARIS_TOOL_OUTPUT_LINES");
        assert_eq!(super::tool_output_line_budget(6), 6);
        std::env::set_var("ARIS_TOOL_OUTPUT_LINES", "17");
        assert_eq!(super::tool_output_line_budget(6), 17);
        std::env::set_var("ARIS_TOOL_OUTPUT_LINES", "0");
        assert_eq!(super::tool_output_line_budget(6), usize::MAX);
        std::env::set_var("ARIS_TOOL_OUTPUT_LINES", "junk");
        assert_eq!(super::tool_output_line_budget(6), 6, "unparsable falls back to default");
        std::env::remove_var("ARIS_TOOL_OUTPUT_LINES");
    }

    // v0.4.23 ride-along (gate round-2 lock): grep content mode serializes
    // `"numMatches": null` (Option without skip_serializing_if) — the summary
    // must say "returned lines", never a false "0 matches".
    #[test]
    fn grep_content_mode_summary_reports_returned_lines() {
        let done = super::format_tool_result(
            "grep_search",
            r#"{"numFiles":2,"numMatches":null,"numLines":5,"content":"a\nb\nc\nd\ne","filenames":["x","y"]}"#,
            false,
        );
        assert!(
            done.contains("5 returned lines across 2 files"),
            "content mode must report returned lines: {done}"
        );
        assert!(!done.contains("0 matches"), "false zero-matches banner: {done}");
        // matches-bearing mode unchanged.
        let counted = super::format_tool_result(
            "grep_search",
            r#"{"numFiles":1,"numMatches":7,"content":"","filenames":["x"]}"#,
            false,
        );
        assert!(counted.contains("7 matches across 1 files"), "{counted}");
    }

    // v0.4.22 (B6/Δ4-6): deterministic codex version oracle, real output shape.
    #[test]
    fn codex_version_oracle_truth_table() {
        // Supported: >= 0.144.1 stable (real "codex-cli X" shape + bare semver).
        assert!(codex_version_support_note("codex-cli 0.144.1").is_none());
        assert!(codex_version_support_note("0.144.1").is_none());
        assert!(codex_version_support_note("codex-cli 0.145.0").is_none());
        assert!(codex_version_support_note("codex-cli 1.0.0").is_none());
        // Old stable → old-version note.
        assert!(codex_version_support_note("codex-cli 0.144.0")
            .is_some_and(|n| n.contains("< 0.144.1")));
        // Prerelease → conservative note.
        assert!(codex_version_support_note("codex-cli 0.144.1-beta.2")
            .is_some_and(|n| n.contains("prerelease")));
        // Malformed → unknown-version note (decided: note, not silent).
        assert!(codex_version_support_note("weird output")
            .is_some_and(|n| n.contains("unrecognized")));
        assert!(codex_version_support_note("codex-cli 0.x")
            .is_some_and(|n| n.contains("unrecognized")));
    }

    // v0.4.20 (#299): the spinner-finish choice keys off whether the turn
    // printed visible assistant text.
    #[test]
    fn turn_has_visible_assistant_text_distinguishes_text_from_tool_only() {
        let summary = |blocks| TurnSummary {
            assistant_messages: vec![ConversationMessage::assistant(blocks)],
            tool_results: vec![],
            iterations: 1,
            usage: TokenUsage::default(),
            auto_compaction: None,
        };
        // Non-empty text → true.
        assert!(turn_has_visible_assistant_text(&summary(vec![ContentBlock::Text {
            text: "你好".to_string()
        }])));
        // Whitespace-only text → false (nothing visible on screen).
        assert!(!turn_has_visible_assistant_text(&summary(vec![ContentBlock::Text {
            text: "  \n ".to_string()
        }])));
        // Tool-only turn → false (keep clearing the "Thinking…" line).
        assert!(!turn_has_visible_assistant_text(&summary(vec![ContentBlock::ToolUse {
            id: "t1".to_string(),
            name: "read_file".to_string(),
            input: "{}".to_string(),
        }])));
        // Empty turn → false.
        assert!(!turn_has_visible_assistant_text(&TurnSummary {
            assistant_messages: vec![],
            tool_results: vec![],
            iterations: 0,
            usage: TokenUsage::default(),
            auto_compaction: None,
        }));
    }

    #[test]
    fn defaults_to_repl_when_no_args() {
        assert_eq!(
            parse_args(&[]).expect("args should parse"),
            CliAction::Repl {
                model: None,
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
                model: None,
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
                // v0.4.22 (C1): parse_args preserves the RAW value.
                model: Some("claude-opus".to_string()),
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
                // v0.4.22 (C1): the alias is NO LONGER resolved at parse time
                // (the wizard can still change EXECUTOR_PROVIDER after this);
                // resolve_startup_model resolves it exactly once — covered by
                // resolve_startup_model_matrix.
                model: Some("opus".to_string()),
                output_format: CliOutputFormat::Text,
                allowed_tools: None,
                permission_mode: PermissionMode::DangerFullAccess,
            }
        );
    }

    #[test]
    fn resolves_known_model_aliases() {
        // `resolve_model_alias` reads EXECUTOR_PROVIDER (aliases are
        // deliberately inert in OpenAI-compat mode) — hold the crate-wide env
        // guard and pin the var, or a concurrent env-writing test flakes this.
        let _g = crate::env_test_guard();
        std::env::remove_var("EXECUTOR_PROVIDER");
        assert_eq!(resolve_model_alias("fable"), "claude-fable-5");
        assert_eq!(resolve_model_alias("opus"), "claude-opus-5");
        assert_eq!(resolve_model_alias("sonnet"), "claude-sonnet-5");
        assert_eq!(resolve_model_alias("haiku"), "claude-haiku-4-5-20251001");
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        assert_eq!(resolve_model_alias("opus"), "opus");
        std::env::remove_var("EXECUTOR_PROVIDER");
    }

    /// v0.4.24: the availability chain walks Opus 5 → 4.8 → 4.7 and stops.
    /// The 4.8 entry point is the regression population codex flagged: a
    /// config saved by v0.4.23's setup (`executor_model: claude-opus-4-8`)
    /// on an account with only 4.7 access must keep its fallback.
    #[test]
    fn default_model_chain_walks_forward_and_terminates() {
        assert_eq!(DEFAULT_MODEL, DEFAULT_MODEL_CHAIN[0]);
        assert_eq!(next_default_fallback("claude-opus-5"), Some("claude-opus-4-8"));
        assert_eq!(
            next_default_fallback("claude-opus-4-8"),
            Some("claude-opus-4-7")
        );
        assert_eq!(next_default_fallback("claude-opus-4-7"), None);
        // Non-chain models (explicitly named or saved) never silently change.
        assert_eq!(next_default_fallback("claude-fable-5"), None);
        assert_eq!(next_default_fallback("claude-sonnet-4-6"), None);
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
                model: None,
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
                model: None,
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

    // ---------------------------------------------------------------
    // v0.4.17 Phase 0 — CHARACTERIZATION TESTS (filter_tool_specs semantics)
    //
    // T5/T8/RW5 change how the catalogue is built/filtered for MCP names.
    // These lock the current filter semantics so the MCP additions can be
    // proven to leave the non-MCP filtering path identical.
    // ---------------------------------------------------------------

    /// `filter_tool_specs(None)` returns the FULL catalogue unchanged
    /// (no allowlist => every MVP tool passes), in canonical order.
    #[test]
    fn char_filter_tool_specs_none_returns_full_catalogue() {
        let all = filter_tool_specs(None);
        let names: Vec<&str> = all.iter().map(|s| s.name).collect();
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
            "filter_tool_specs(None) must return the full ordered catalogue"
        );
    }

    /// An empty allowlist filters EVERYTHING out (current behavior: an
    /// allowlist that contains nothing matches nothing).
    #[test]
    fn char_filter_tool_specs_empty_allowlist_is_empty() {
        let allowed: super::AllowedToolSet = std::collections::BTreeSet::new();
        let filtered = filter_tool_specs(Some(&allowed));
        assert!(
            filtered.is_empty(),
            "empty allowlist must filter out all tools"
        );
    }

    /// Unknown names in the allowlist are silently ignored (no error, no
    /// synthesized spec): only the intersection with the catalogue passes,
    /// and the result preserves catalogue order — NOT allowlist order.
    #[test]
    fn char_filter_tool_specs_unknown_names_ignored_and_order_is_catalogue_order() {
        let allowed: super::AllowedToolSet = ["totally_made_up", "grep_search", "bash"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let names: Vec<&str> = filter_tool_specs(Some(&allowed))
            .iter()
            .map(|s| s.name)
            .collect();
        // "totally_made_up" dropped; order follows mvp_tool_specs() not the
        // allowlist (bash precedes grep_search in the catalogue).
        assert_eq!(names, vec!["bash", "grep_search"]);
    }

    /// `filter_tool_specs` only ever filters the STATIC catalogue, so an
    /// `mcp__`-prefixed name in its allowlist matches nothing there and is
    /// dropped — and MUST be, because MCP tools are advertised via the separate
    /// `filter_mcp_specs` path, not this one. (See `char_filter_mcp_specs_*` for
    /// the MCP advertising filter.) deliberately flipped in v0.4.17 (T8): the
    /// docstring previously claimed an mcp__ name "never even reaches this
    /// filter" because `normalize_allowed_tools` rejected it; T8 now ACCEPTS
    /// mcp__ names (deferred validation), so they can reach here — and this
    /// filter still correctly drops them from the STATIC tool list while
    /// `filter_mcp_specs` advertises them on the MCP side.
    #[test]
    fn char_filter_tool_specs_mcp_name_currently_dropped() {
        let allowed: super::AllowedToolSet = ["mcp__codex__codex", "read_file"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let names: Vec<&str> = filter_tool_specs(Some(&allowed))
            .iter()
            .map(|s| s.name)
            .collect();
        assert_eq!(names, vec!["read_file"]);
    }

    /// deliberately flipped in v0.4.17 (T8): `--allowedTools mcp__<server>__<tool>`
    /// is now ACCEPTED at arg-parse time via deferred validation (the static
    /// catalogue cannot know which MCP tools exist before runtime discovery).
    /// Previously `normalize_allowed_tools` rejected any non-catalogue name,
    /// including `mcp__` names; the new behavior records the mcp__ name verbatim
    /// (case-preserved) so the advertising/dispatch layers can filter to it.
    /// Non-mcp unknown names still hard-error (per-name validation unchanged).
    #[test]
    fn char_normalize_allowed_tools_accepts_mcp_name() {
        let set = super::normalize_allowed_tools(&["mcp__codex__codex".to_string()])
            .expect("mcp__ names are now accepted via deferred validation")
            .expect("non-empty input yields a set");
        assert!(
            set.contains("mcp__codex__codex"),
            "mcp__ name must be recorded verbatim (case-preserved): {set:?}"
        );

        // A NON-mcp unknown name still hard-errors (deferred validation is
        // scoped to the mcp__ prefix only; per-name validation is unchanged).
        let err = super::normalize_allowed_tools(&["totally_made_up".to_string()])
            .expect_err("unknown non-mcp names still rejected");
        assert!(
            err.contains("unsupported tool in --allowedTools: totally_made_up"),
            "unexpected error shape: {err}"
        );

        // Known-good static names still parse alongside mcp__ names.
        let mixed = super::normalize_allowed_tools(&["read_file, mcp__codex__codex".to_string()])
            .expect("mixed list parses")
            .expect("non-empty input yields a set");
        assert!(mixed.contains("read_file") && mixed.contains("mcp__codex__codex"));
    }

    // ── v0.4.17 C2 (T8): MCP advertising filter consistency ─────────────────

    fn runtime_spec(name: &str) -> super::RuntimeToolSpec {
        super::RuntimeToolSpec {
            name: name.to_string(),
            description: format!("desc for {name}"),
            input_schema: json!({ "type": "object" }),
        }
    }

    /// T8 (advertising side): with NO `--allowedTools`, every discovered MCP
    /// tool is advertised (status quo — the allowlist is the only gate).
    #[test]
    fn char_filter_mcp_specs_no_allowlist_advertises_all() {
        let specs = vec![
            runtime_spec("mcp__codex__codex"),
            runtime_spec("mcp__gh__list_prs"),
        ];
        let out = super::filter_mcp_specs(specs.clone(), None);
        let names: Vec<&str> = out.iter().map(|s| s.name.as_str()).collect();
        assert_eq!(names, vec!["mcp__codex__codex", "mcp__gh__list_prs"]);
    }

    /// T8 (advertising side): an allowlist containing an MCP name advertises
    /// EXACTLY that MCP tool and drops the others — the same allowlist that
    /// `normalize_allowed_tools` accepted via deferred validation.
    #[test]
    fn char_filter_mcp_specs_allowlist_keeps_only_listed_mcp_name() {
        let specs = vec![
            runtime_spec("mcp__codex__codex"),
            runtime_spec("mcp__gh__list_prs"),
        ];
        let allowed: super::AllowedToolSet = ["mcp__codex__codex", "read_file"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let out = super::filter_mcp_specs(specs, Some(&allowed));
        let names: Vec<&str> = out.iter().map(|s| s.name.as_str()).collect();
        assert_eq!(names, vec!["mcp__codex__codex"]);
    }

    /// T8 (advertising side): an allowlist with NO MCP name advertises ZERO MCP
    /// tools (a `--allowedTools read_file` user gets no MCP tools, matching the
    /// dispatch gate which would also reject them).
    #[test]
    fn char_filter_mcp_specs_allowlist_without_mcp_name_advertises_none() {
        let specs = vec![runtime_spec("mcp__codex__codex")];
        let allowed: super::AllowedToolSet =
            ["read_file"].into_iter().map(str::to_string).collect();
        let out = super::filter_mcp_specs(specs, Some(&allowed));
        assert!(
            out.is_empty(),
            "no MCP name in allowlist => no MCP advertised"
        );
    }

    /// T8 (dispatch side): the `CliToolExecutor` allowlist gate rejects an MCP
    /// name that is NOT in the allowlist BEFORE any MCP dispatch is attempted —
    /// the same allowlist semantics as the advertising filter, so advertising
    /// and dispatch never disagree. (mcp: None here only proves the gate fires
    /// first; the gate runs identically with an MCP runtime present.)
    #[test]
    fn char_cli_executor_allowlist_gate_rejects_unlisted_mcp_name() {
        let allowed: super::AllowedToolSet = ["mcp__codex__codex"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let mut executor = super::CliToolExecutor::new(
            Some(allowed),
            false,
            None,
            super::PermissionMode::DangerFullAccess,
            true,
        );
        let err = executor
            .execute("mcp__other__tool", "{}")
            .expect_err("an MCP name not in the allowlist must be gated");
        assert!(
            err.to_string()
                .contains("not enabled by the current --allowedTools"),
            "must be rejected by the allowlist gate, not dispatch: {err}"
        );
    }

    // ── v0.4.17 C2 (T5): MCP approval decision truth table ──────────────────

    /// The full truth table of `mcp_approval_decision` across the four active
    /// modes the CLI exposes (read-only / workspace-write / danger-full-access /
    /// prompt) × trusted/untrusted × interactive/non-interactive. The
    /// interactive prompt itself is not unit-testable (stdin), so only this pure
    /// decision is tested — it is the single source of truth for the gate.
    #[test]
    fn mcp_approval_decision_truth_table() {
        use super::mcp_approval_decision as decide;
        use super::McpApprovalDecision::{Allow as DAllow, Deny as DDeny, Prompt as DPrompt};
        use runtime::PermissionMode::{
            Allow as MAllow, DangerFullAccess, Prompt as MPrompt, ReadOnly, WorkspaceWrite,
        };

        // trusted => Allow, regardless of mode / interactivity / session.
        for &mode in &[ReadOnly, WorkspaceWrite, DangerFullAccess, MPrompt, MAllow] {
            for &interactive in &[true, false] {
                for &session in &[true, false] {
                    assert_eq!(
                        decide(mode, true, session, interactive),
                        DAllow,
                        "trusted must always Allow (mode={mode:?}, interactive={interactive}, session={session})"
                    );
                }
            }
        }

        // session_approved => Allow (even if not pre-trusted), regardless of
        // mode / interactivity.
        for &mode in &[ReadOnly, WorkspaceWrite, DangerFullAccess, MPrompt, MAllow] {
            for &interactive in &[true, false] {
                assert_eq!(
                    decide(mode, false, true, interactive),
                    DAllow,
                    "session-approved must Allow (mode={mode:?}, interactive={interactive})"
                );
            }
        }

        // Untrusted + not-session-approved, by mode:
        // Prompt mode => Allow (generic gate already prompted, no double-ask).
        assert_eq!(decide(MPrompt, false, false, true), DAllow);
        assert_eq!(decide(MPrompt, false, false, false), DAllow);
        // Allow mode => Allow (explicit bypass-everything mode).
        assert_eq!(decide(MAllow, false, false, true), DAllow);
        assert_eq!(decide(MAllow, false, false, false), DAllow);
        // ReadOnly / WorkspaceWrite / DangerFullAccess: Prompt if interactive,
        // else Deny. DangerFullAccess is NOT auto-Allow (the sandbox can't
        // contain the external MCP process, so it still confirms).
        for &mode in &[ReadOnly, WorkspaceWrite, DangerFullAccess] {
            assert_eq!(
                decide(mode, false, false, true),
                DPrompt,
                "interactive untrusted {mode:?} must Prompt"
            );
            assert_eq!(
                decide(mode, false, false, false),
                DDeny,
                "non-interactive untrusted {mode:?} must Deny"
            );
        }
    }

    /// v0.4.17 (T5): `permission_policy_with_mcp` registers each advertised MCP
    /// name at the MINIMAL required mode (`ReadOnly`) so the generic gate passes
    /// them through to the executor's MCP approval in every active mode (rather
    /// than the unregistered default of `DangerFullAccess`, which would make the
    /// generic gate deny them in read-only/workspace). Static tools keep their
    /// own required modes.
    #[test]
    fn permission_policy_registers_mcp_names_at_readonly() {
        use runtime::PermissionMode;
        let policy = super::permission_policy_with_mcp(
            PermissionMode::ReadOnly,
            ["mcp__alpha__echo".to_string(), "mcp__beta__run".to_string()].into_iter(),
        );
        // MCP names registered at ReadOnly.
        assert_eq!(
            policy.required_mode_for("mcp__alpha__echo"),
            PermissionMode::ReadOnly
        );
        assert_eq!(
            policy.required_mode_for("mcp__beta__run"),
            PermissionMode::ReadOnly
        );
        // Static tools keep their own required modes (bash = DangerFullAccess).
        assert_eq!(
            policy.required_mode_for("bash"),
            PermissionMode::DangerFullAccess
        );
        assert_eq!(
            policy.required_mode_for("read_file"),
            PermissionMode::ReadOnly
        );
        // And in ReadOnly active mode the generic gate ALLOWS a ReadOnly-
        // required MCP tool through to the executor (the executor then runs the
        // MCP-specific approval). No prompter needed because ReadOnly >=
        // ReadOnly short-circuits to Allow.
        assert_eq!(
            policy.authorize("mcp__alpha__echo", "{}", None),
            runtime::PermissionOutcome::Allow
        );
    }

    // ── v0.4.17 C2 (RW7): doctor MCP section formatter ──────────────────────

    /// No MCP servers => no section at all (users without MCP see nothing).
    #[test]
    fn mcp_doctor_section_empty_is_none() {
        assert_eq!(super::mcp_doctor_section(&[]), None);
    }

    /// v0.4.17 (codex R Track C2 P2): control characters in a (project-sourced)
    /// raw server name must be neutralized before display so a cloned repo's
    /// config cannot inject terminal escape sequences. Non-control (incl.
    /// non-ASCII) characters pass through unchanged.
    #[test]
    fn sanitize_for_display_neutralizes_control_chars() {
        assert_eq!(super::sanitize_for_display("plain_name"), "plain_name");
        assert_eq!(super::sanitize_for_display("café-server"), "café-server");
        // ESC + CSI sequence and a newline are all replaced with '?'.
        assert_eq!(
            super::sanitize_for_display("evil\x1b[31mRED\nx"),
            "evil?[31mRED?x"
        );
    }

    /// A user-scope server whose transport is not stdio renders as
    /// "unsupported transport", NOT "discovered, 0 tools" (codex R Track C2 P2).
    #[test]
    fn mcp_doctor_section_renders_unsupported_transport() {
        use super::{ConfigSource, McpDoctorServer, McpDoctorStatus};
        let servers = vec![McpDoctorServer {
            name: "remote".to_string(),
            scope: ConfigSource::User,
            trusted: false,
            status: McpDoctorStatus::Unsupported {
                transport: "Sse".to_string(),
            },
        }];
        let section = super::mcp_doctor_section(&servers).expect("non-empty => Some");
        assert!(
            section.contains("remote [user]: unsupported transport (Sse); only stdio is spawned"),
            "{section}"
        );
        // Not counted as discovered.
        assert!(section.contains("0 user-scope discovered"), "{section}");
    }

    /// RW7 step ②/③: lock the REAL per-server status text and prove the stale
    /// "lands in v0.4.16" placeholder is gone (it falsely promised a feature
    /// that shipped in v0.4.17). deliberately updated in RW7 step ③: the old
    /// inline Check-6 warning text is replaced by this formatter's output.
    #[test]
    fn mcp_doctor_section_renders_real_per_server_status() {
        use super::{ConfigSource, McpDoctorServer, McpDoctorStatus};
        let servers = vec![
            McpDoctorServer {
                name: "codex".to_string(),
                scope: ConfigSource::User,
                trusted: true,
                status: McpDoctorStatus::Discovered { tool_count: 2 },
            },
            McpDoctorServer {
                name: "broken".to_string(),
                scope: ConfigSource::User,
                trusted: false,
                status: McpDoctorStatus::Failed {
                    reason: "spawn failed: no such file".to_string(),
                },
            },
            McpDoctorServer {
                name: "repo_tool".to_string(),
                scope: ConfigSource::Project,
                trusted: false,
                status: McpDoctorStatus::SkippedScope,
            },
        ];
        let section = super::mcp_doctor_section(&servers).expect("non-empty => Some");

        // Header reports total + user-scope discovered count.
        assert!(
            section.contains("3 configured (1 user-scope discovered)"),
            "{section}"
        );
        // Per-server rows: discovered (with trust + tool count), failed, skipped.
        assert!(
            section.contains("codex [user, trusted]: spawned + initialized, 2 tool(s)"),
            "{section}"
        );
        assert!(
            section.contains("broken [user]: FAILED — spawn failed: no such file"),
            "{section}"
        );
        assert!(
            section.contains("repo_tool [project]: skipped")
                && section.contains("move to user config to enable"),
            "{section}"
        );
        // The approval-vs-spawn distinction is surfaced (codex R1 Track C2 P1).
        assert!(
            section.contains("only user-scope servers are spawned at startup")
                && section.contains("tool CALLS are approval-gated"),
            "{section}"
        );
        // The stale placeholder must be gone (it lied: dispatch landed in
        // v0.4.17, not "lands in v0.4.16").
        assert!(
            !section.contains("lands in v0.4.16"),
            "stale placeholder text must be removed: {section}"
        );
        // v0.4.17 (T10/P2, deliberately updated): the path-mismatch disclosure
        // is now user-visible (was source-comment only). It names the legacy
        // ~/.claude.json check and the runtime settings.json path.
        assert!(
            section.contains("legacy ~/.claude.json is checked separately for Codex MCP")
                && section.contains("settings.json"),
            "doctor section must disclose the legacy-vs-settings.json path mismatch: {section}"
        );
    }

    // ── v0.4.17 C1 (T3/T4/RW5): MCP dispatch + no-MCP equivalence ───────────

    use runtime::ToolExecutor as _;

    /// No-MCP path char test: a `CliToolExecutor` built with `mcp: None`
    /// continues to route an `mcp__`-prefixed name into the static
    /// `execute_tool`, producing the verbatim `unsupported tool` error. This is
    /// the structural guarantee that users without `mcpServers` see no behavior
    /// change (and the T6 guarantee that subagents — which always go through
    /// the no-MCP path — never reach MCP).
    #[test]
    fn char_cli_tool_executor_without_mcp_treats_mcp_name_as_unsupported() {
        let mut executor = super::CliToolExecutor::new(
            None,
            false,
            None,
            super::PermissionMode::DangerFullAccess,
            true,
        );
        let err = executor
            .execute("mcp__fake__tool", "{}")
            .expect_err("mcp name without an MCP runtime must be unsupported");
        assert_eq!(err.to_string(), "unsupported tool: mcp__fake__tool");
    }

    /// `flatten_mcp_content` joins text blocks and serializes non-text blocks
    /// to JSON lines (T3 content flattening).
    #[test]
    fn flatten_mcp_content_text_and_nontext() {
        use runtime::McpToolCallContent;
        let mut text_block = McpToolCallContent {
            kind: "text".to_string(),
            data: std::collections::BTreeMap::new(),
        };
        text_block
            .data
            .insert("text".to_string(), json!("hello world"));

        let mut image_block = McpToolCallContent {
            kind: "image".to_string(),
            data: std::collections::BTreeMap::new(),
        };
        image_block
            .data
            .insert("data".to_string(), json!("base64=="));

        let flattened = super::flatten_mcp_content(&[text_block, image_block]);
        let lines: Vec<&str> = flattened.lines().collect();
        assert_eq!(lines[0], "hello world");
        // Second line is a JSON object reconstructing the non-text block.
        let parsed: serde_json::Value =
            serde_json::from_str(lines[1]).expect("non-text block serialized as JSON");
        assert_eq!(parsed["type"], "image");
        assert_eq!(parsed["data"], "base64==");
    }

    /// v0.4.21 (#4): `mcp_result_text` falls back to `structuredContent` only
    /// when the flattened `content` text is empty. A spec-valid server returning
    /// ONLY structuredContent must not hand the model an empty result, while a
    /// content-bearing result keeps its content verbatim (structured ignored).
    /// The fallback is pure, so it is unit-tested directly here rather than
    /// through `dispatch_mcp` (which needs a live `McpServerManager` subprocess);
    /// the wiring is still exercised end-to-end by
    /// `mcp_executor_dispatch_end_to_end`.
    #[test]
    fn mcp_result_text_structured_fallback() {
        use runtime::McpToolCallContent;

        let structured = json!({"answer": 42});

        // (1) Empty content + structuredContent present → serialized structured JSON.
        assert_eq!(
            super::mcp_result_text(&[], Some(&structured)),
            "{\"answer\":42}"
        );

        // (2) Non-empty text content + structuredContent present → content wins,
        //     the structured payload is ignored (common path unchanged).
        let mut text_block = McpToolCallContent {
            kind: "text".to_string(),
            data: std::collections::BTreeMap::new(),
        };
        text_block
            .data
            .insert("text".to_string(), json!("hello world"));
        assert_eq!(
            super::mcp_result_text(&[text_block], Some(&structured)),
            "hello world"
        );

        // (3) Neither content nor structuredContent → empty string (unchanged).
        assert_eq!(super::mcp_result_text(&[], None), "");

        // (4) Whitespace-only content + structuredContent → fallback still fires
        //     (the guard trims before testing emptiness).
        let mut blank_block = McpToolCallContent {
            kind: "text".to_string(),
            data: std::collections::BTreeMap::new(),
        };
        blank_block.data.insert("text".to_string(), json!("   "));
        assert_eq!(
            super::mcp_result_text(&[blank_block], Some(&structured)),
            "{\"answer\":42}"
        );
    }

    fn fake_mcp_echo_server_script() -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("aris-cli-mcp-it-{nanos}"));
        std::fs::create_dir_all(&root).expect("temp dir");
        let script_path = root.join("echo-server.py");
        // v0.4.17 (Track R): NDJSON framing — one JSON object per line,
        // the canonical MCP stdio dialect the runtime client now speaks
        // (matching the real `codex mcp-server`). The earlier
        // `Content-Length` framing was an LSP-ism no real MCP server
        // reads; keeping it here would have this fixture silently speak a
        // dialect the fixed client never writes, re-creating the exact
        // self-consistent test hallucination Track R removed.
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
            "def send(message):",
            r"    sys.stdout.write(json.dumps(message) + '\n')",
            "    sys.stdout.flush()",
            "",
            "while True:",
            "    req = read_message()",
            "    if req is None:",
            "        break",
            "    method = req['method']",
            "    if 'id' not in req:",
            "        continue",
            "    if method == 'initialize':",
            "        send({'jsonrpc': '2.0', 'id': req['id'], 'result': {",
            "            'protocolVersion': req['params']['protocolVersion'],",
            "            'capabilities': {'tools': {}},",
            "            'serverInfo': {'name': 'alpha', 'version': '1.0.0'}}})",
            "    elif method == 'tools/list':",
            "        send({'jsonrpc': '2.0', 'id': req['id'], 'result': {'tools': [{",
            "            'name': 'echo',",
            "            'description': 'Echo the text back.',",
            "            'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text']}}]}})",
            "    elif method == 'tools/call':",
            "        args = req['params'].get('arguments') or {}",
            "        text = args.get('text', '')",
            "        is_error = text == 'BOOM'",
            "        send({'jsonrpc': '2.0', 'id': req['id'], 'result': {",
            "            'content': [{'type': 'text', 'text': f'echoed: {text}'}],",
            "            'isError': is_error}})",
            "    else:",
            "        send({'jsonrpc': '2.0', 'id': req['id'], 'error': {'code': -32601, 'message': 'unknown'}})",
            "",
        ]
        .join("\n");
        std::fs::write(&script_path, script).expect("write script");
        script_path
    }

    fn build_mcp_runtime_for_echo_server() -> super::SharedMcpRuntime {
        use runtime::{
            ConfigSource, McpServerConfig, McpServerManager, McpStdioServerConfig,
            ScopedMcpServerConfig,
        };
        let script_path = fake_mcp_echo_server_script();
        let servers = std::collections::BTreeMap::from([(
            "alpha".to_string(),
            ScopedMcpServerConfig {
                scope: ConfigSource::Local,
                config: McpServerConfig::Stdio(McpStdioServerConfig {
                    command: "python3".to_string(),
                    args: vec![script_path.to_string_lossy().into_owned()],
                    env: std::collections::BTreeMap::new(),
                    request_timeout_secs: None,
                    trust: None,
                }),
            },
        )]);
        let manager = McpServerManager::from_servers(&servers);
        let mut handle =
            runtime::McpManagerHandle::from_manager(manager).expect("build sync handle");
        let managed = handle.discover_tools().expect("discover tools");
        let catalog = super::mcp_tool_specs(&managed);
        // Pre-trust `alpha` so the v0.4.17 (T5) dispatch approval is bypassed
        // (this test drives dispatch mechanics, not the approval prompt — the
        // approval decision itself is exhaustively covered by the
        // `mcp_approval_decision_*` truth-table tests).
        let mut trusted_servers = std::collections::HashSet::new();
        trusted_servers.insert("alpha".to_string());
        std::rc::Rc::new(std::cell::RefCell::new(super::McpRuntime {
            handle,
            catalog,
            trusted_servers,
            session_approved: std::collections::HashSet::new(),
        }))
    }

    /// End-to-end (T3/T4): a `CliToolExecutor` holding a real MCP runtime backed
    /// by a fake stdio server dispatches an `mcp__alpha__echo` call all the way
    /// to the server and flattens the text result. Drives the executor layer
    /// exactly as `ConversationRuntime` would (synchronous, outside any tokio
    /// runtime — SPIKE-A invariant; the handle's debug_assert must not fire).
    #[test]
    fn mcp_executor_dispatch_end_to_end() {
        let mcp = build_mcp_runtime_for_echo_server();
        // The catalog should advertise exactly the echo tool.
        assert_eq!(mcp.borrow().catalog.len(), 1);
        assert_eq!(mcp.borrow().catalog.specs()[0].name, "mcp__alpha__echo");

        // `alpha` is pre-trusted (see helper), so DangerFullAccess + may_prompt
        // both irrelevant: the approval bypasses to Allow and dispatch proceeds.
        let mut executor = super::CliToolExecutor::new(
            None,
            false,
            Some(mcp.clone()),
            super::PermissionMode::DangerFullAccess,
            false,
        );
        let output = executor
            .execute("mcp__alpha__echo", &json!({"text": "hi"}).to_string())
            .expect("mcp dispatch succeeds");
        assert_eq!(output, "echoed: hi");

        // is_error mapping: the fake server flags text == "BOOM" as an error.
        let err = executor
            .execute("mcp__alpha__echo", &json!({"text": "BOOM"}).to_string())
            .expect_err("isError:true must map to a tool error");
        assert_eq!(err.to_string(), "echoed: BOOM");

        // An mcp__ name the catalog never produced is rejected at the approval
        // layer (route miss => deny, no server identity to authorize) BEFORE any
        // dispatch — clean error, no credentials / env names leaked.
        let unknown = executor
            .execute("mcp__alpha__missing", "{}")
            .expect_err("unknown mcp tool errors");
        assert_eq!(
            unknown.to_string(),
            "unknown MCP tool: mcp__alpha__missing",
            "route miss must be a clean deny: {unknown}"
        );

        mcp.borrow_mut()
            .handle
            .shutdown()
            .expect("shutdown servers");
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
                model: "claude-opus-4-7".to_string(),
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
                model: "claude-opus-4-7".to_string(),
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

    // ----- v0.4.13: deploy_meta_opt_hooks_to tests -----
    //
    // These tests build a fake cache_dir + a fake HOME under env::temp_dir(),
    // never touch the real ~/.claude, and exercise:
    //   1. fresh deploy (no settings.json): hooks copied + settings created
    //   2. existing settings preserved without clobber when we merge
    //   3. idempotency: a second run does not duplicate hook entries

    fn meta_opt_test_root() -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time after epoch")
            .as_nanos();
        let pid = std::process::id();
        std::env::temp_dir().join(format!("aris-meta-opt-test-{pid}-{nanos}"))
    }

    fn write_fake_cache(root: &std::path::Path) -> std::path::PathBuf {
        let cache_dir = root.join("cache");
        let meta_opt = cache_dir.join("tools").join("meta_opt");
        std::fs::create_dir_all(&meta_opt).expect("create cache meta_opt dir");
        std::fs::write(
            meta_opt.join("log_event.sh"),
            "#!/usr/bin/env bash\necho log_event\n",
        )
        .expect("write log_event.sh");
        std::fs::write(
            meta_opt.join("check_ready.sh"),
            "#!/usr/bin/env bash\necho check_ready\n",
        )
        .expect("write check_ready.sh");
        cache_dir
    }

    #[test]
    fn deploy_meta_opt_hooks_creates_hooks_dir_and_copies_scripts() {
        let root = meta_opt_test_root();
        let cache_dir = write_fake_cache(&root);
        let home = root.join("home");
        std::fs::create_dir_all(&home).expect("create home");

        let report =
            deploy_meta_opt_hooks_to(&home, &cache_dir).expect("first deploy should succeed");
        assert!(
            report.contains("Meta-Optimize hooks deployed"),
            "report missing header: {report}"
        );

        let hooks_dir = home.join(".claude").join("hooks");
        assert!(hooks_dir.is_dir(), "hooks dir should exist");
        // v0.4.13 codex round-1 #1: ARIS-namespaced destination names
        let log_event = hooks_dir.join("aris-meta-opt-log-event.sh");
        let check_ready = hooks_dir.join("aris-meta-opt-check-ready.sh");
        assert!(
            log_event.is_file(),
            "aris-meta-opt-log-event.sh should exist"
        );
        assert!(
            check_ready.is_file(),
            "aris-meta-opt-check-ready.sh should exist"
        );

        let log_event_body =
            std::fs::read_to_string(&log_event).expect("read aris-meta-opt-log-event.sh");
        assert!(log_event_body.contains("echo log_event"));
        let check_ready_body =
            std::fs::read_to_string(&check_ready).expect("read aris-meta-opt-check-ready.sh");
        assert!(check_ready_body.contains("echo check_ready"));

        // settings.json was created with the new hooks block
        let settings_path = home.join(".claude").join("settings.json");
        assert!(settings_path.is_file(), "settings.json should exist");
        let settings_value: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(&settings_path).expect("read settings.json"),
        )
        .expect("settings.json parses");
        // PostToolUse references aris-meta-opt-log-event.sh
        let post_arr = settings_value
            .pointer("/hooks/PostToolUse")
            .and_then(|v| v.as_array())
            .expect("hooks.PostToolUse array");
        assert_eq!(post_arr.len(), 1);
        let post_cmd = post_arr[0]
            .pointer("/hooks/0/command")
            .and_then(|v| v.as_str())
            .expect("PostToolUse command");
        assert!(
            post_cmd.contains("aris-meta-opt-log-event.sh"),
            "PostToolUse cmd should mention aris-meta-opt-log-event.sh, got {post_cmd}"
        );
        // SessionEnd has BOTH log_event and check_ready
        let session_end_arr = settings_value
            .pointer("/hooks/SessionEnd")
            .and_then(|v| v.as_array())
            .expect("hooks.SessionEnd array");
        assert_eq!(
            session_end_arr.len(),
            2,
            "SessionEnd should have 2 matcher entries (log_event + check_ready)"
        );

        std::fs::remove_dir_all(&root).expect("cleanup");
    }

    #[test]
    fn deploy_meta_opt_hooks_merges_into_existing_settings_json_without_clobber() {
        let root = meta_opt_test_root();
        let cache_dir = write_fake_cache(&root);
        let home = root.join("home");
        let claude_dir = home.join(".claude");
        std::fs::create_dir_all(&claude_dir).expect("create claude dir");

        // Pre-existing settings.json with user fields aris must NOT clobber.
        let prior = serde_json::json!({
            "model": "gpt-5.5",
            "env": {"FOO": "bar"},
            "permissions": {"defaultMode": "dontAsk"},
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "echo user-hook"}
                        ]
                    }
                ]
            }
        });
        let settings_path = claude_dir.join("settings.json");
        std::fs::write(
            &settings_path,
            serde_json::to_string_pretty(&prior).unwrap(),
        )
        .expect("write prior settings.json");

        deploy_meta_opt_hooks_to(&home, &cache_dir).expect("deploy should succeed");

        let merged: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(&settings_path).expect("read settings.json"),
        )
        .expect("settings.json parses");

        // User fields survived
        assert_eq!(
            merged.pointer("/model").and_then(|v| v.as_str()),
            Some("gpt-5.5"),
            "model field must be preserved"
        );
        assert_eq!(
            merged.pointer("/env/FOO").and_then(|v| v.as_str()),
            Some("bar"),
            "env.FOO must be preserved"
        );
        assert_eq!(
            merged
                .pointer("/permissions/defaultMode")
                .and_then(|v| v.as_str()),
            Some("dontAsk"),
            "permissions.defaultMode must be preserved"
        );

        // Existing PreToolUse user hook survived intact
        let pre_arr = merged
            .pointer("/hooks/PreToolUse")
            .and_then(|v| v.as_array())
            .expect("hooks.PreToolUse array");
        assert_eq!(pre_arr.len(), 1, "user PreToolUse not duplicated");
        let pre_cmd = pre_arr[0]
            .pointer("/hooks/0/command")
            .and_then(|v| v.as_str())
            .expect("PreToolUse command");
        assert_eq!(pre_cmd, "echo user-hook");

        // New PostToolUse / SessionEnd hooks were added
        assert!(merged.pointer("/hooks/PostToolUse").is_some());
        assert!(merged.pointer("/hooks/SessionEnd").is_some());

        // Backup file exists alongside (best-effort, but should be present here)
        let mut backup_count = 0usize;
        for entry in std::fs::read_dir(&claude_dir).expect("read claude dir") {
            let e = entry.expect("dir entry");
            let name = e.file_name().to_string_lossy().into_owned();
            if name.starts_with("settings.json.bak.") {
                backup_count += 1;
            }
        }
        assert!(backup_count >= 1, "expected a settings.json.bak.* backup");

        std::fs::remove_dir_all(&root).expect("cleanup");
    }

    #[test]
    fn deploy_meta_opt_hooks_idempotent_doesnt_dupe_on_second_run() {
        let root = meta_opt_test_root();
        let cache_dir = write_fake_cache(&root);
        let home = root.join("home");
        std::fs::create_dir_all(&home).expect("create home");

        deploy_meta_opt_hooks_to(&home, &cache_dir).expect("first deploy");
        deploy_meta_opt_hooks_to(&home, &cache_dir).expect("second deploy idempotent");

        let settings_path = home.join(".claude").join("settings.json");
        let merged: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(&settings_path).expect("read settings.json"),
        )
        .expect("settings.json parses");

        // Each event should still have exactly one log_event matcher entry.
        for event in [
            "PostToolUse",
            "PostToolUseFailure",
            "UserPromptSubmit",
            "SessionStart",
        ] {
            let arr = merged
                .pointer(&format!("/hooks/{event}"))
                .and_then(|v| v.as_array())
                .unwrap_or_else(|| panic!("hooks.{event} array missing"));
            assert_eq!(
                arr.len(),
                1,
                "{event} should have exactly 1 matcher entry after 2 deploys, got {}",
                arr.len()
            );
        }

        // SessionEnd has 2 entries (log_event + check_ready); they must NOT
        // grow on the second deploy.
        let session_end = merged
            .pointer("/hooks/SessionEnd")
            .and_then(|v| v.as_array())
            .expect("hooks.SessionEnd array");
        assert_eq!(
            session_end.len(),
            2,
            "SessionEnd should have exactly 2 matcher entries after 2 deploys"
        );

        std::fs::remove_dir_all(&root).expect("cleanup");
    }

    // ---------------------------------------------------------------
    // v0.4.17 Phase 0 — CHARACTERIZATION TEST (meta_opt hook PARSE result)
    //
    // deliberately flipped in v0.4.17 Phase 2: schema now preserves
    // matcher/timeout/async. SCHEMA-1/2 replaced the flatten-to-Vec<String>
    // parse with RuntimeHookSpec, so the EXACT object-style shape that
    // `aris init` (ensure_hook_entry) writes for meta_opt hooks now parses
    // to a single PostToolUse spec that KEEPS matcher ("") / timeout (5) /
    // async (true) instead of dropping them. matcher="" means match-all
    // under SCHEMA-3 filtering, so meta_opt hooks keep firing for every
    // tool — runtime behavior unchanged. Still locked as before:
    //
    //   * the parser only reads PreToolUse / PostToolUse keys, so
    //     PreToolUse stays empty (meta_opt writes no PreToolUse);
    //   * unknown/extra events (PostToolUseFailure / UserPromptSubmit /
    //     SessionStart / SessionEnd) are silently ignored by the parser.
    // ---------------------------------------------------------------
    #[test]
    fn char_meta_opt_hook_shape_parses_to_command_dropping_matcher_and_timeout() {
        let root = meta_opt_test_root();
        let cache_dir = write_fake_cache(&root);
        let home = root.join("home");
        std::fs::create_dir_all(&home).expect("create home");

        // Produce the REAL settings.json shape `aris init` writes.
        deploy_meta_opt_hooks_to(&home, &cache_dir).expect("deploy should succeed");

        let claude_dir = home.join(".claude");
        let cwd = root.join("project");
        std::fs::create_dir_all(&cwd).expect("create project cwd");

        // Sanity-pin the written shape Phase 2 will migrate: object-style
        // entry with matcher="" + async timeout=5 + async:true.
        let settings_value: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(claude_dir.join("settings.json")).expect("read settings"),
        )
        .expect("settings parses");
        let post_entry = settings_value
            .pointer("/hooks/PostToolUse/0")
            .expect("PostToolUse[0] entry");
        assert_eq!(
            post_entry.pointer("/matcher").and_then(|v| v.as_str()),
            Some("")
        );
        assert_eq!(
            post_entry.pointer("/hooks/0/type").and_then(|v| v.as_str()),
            Some("command")
        );
        assert_eq!(
            post_entry
                .pointer("/hooks/0/timeout")
                .and_then(|v| v.as_u64()),
            Some(5)
        );
        assert_eq!(
            post_entry
                .pointer("/hooks/0/async")
                .and_then(|v| v.as_bool()),
            Some(true)
        );

        // Now load through the real runtime parser and lock the result.
        let loaded = runtime::ConfigLoader::new(&cwd, &claude_dir)
            .load()
            .expect("config should load meta_opt hook shape");

        // PreToolUse: empty (meta_opt writes no PreToolUse).
        assert!(
            loaded.hooks().pre_tool_use().is_empty(),
            "PreToolUse must be empty for meta_opt config, got {:?}",
            loaded.hooks().pre_tool_use()
        );

        // PostToolUse: a SINGLE spec whose command is unchanged and whose
        // matcher ("") / timeout (5) / async (true) are now PRESERVED
        // (deliberately flipped in v0.4.17 Phase 2).
        let post = loaded.hooks().post_tool_use();
        assert_eq!(post.len(), 1, "PostToolUse should parse to one spec");
        assert!(
            post[0].command.contains("aris-meta-opt-log-event.sh")
                && post[0].command.starts_with("bash "),
            "PostToolUse command should be the bash log_event invocation, got {}",
            post[0].command
        );
        assert_eq!(
            post[0].matcher.as_deref(),
            Some(""),
            "meta_opt matcher \"\" must be preserved (and means match-all)"
        );
        assert_eq!(post[0].timeout_secs, Some(5), "timeout must be preserved");
        assert_eq!(post[0].async_flag, Some(true), "async must be preserved");

        std::fs::remove_dir_all(&root).expect("cleanup");
    }

    // --- reviewer_routing_nudge: three-state system-prompt routing (codex R11) ---
    //
    // These pin the exact prompt the model receives for each reviewer provider
    // state. The P1 bug was that a REPL session never re-derived this after
    // /setup; the fix rebuilds the system prompt unconditionally, so the
    // *content* this helper produces per state must stay correct.

    /// Shared v0.4.22 (B1) contract locks for BOTH codex-mcp states: the
    /// two-tier gpt-5.6-sol doctrine, the canonical capability-only fallback
    /// chain, the legacy-shorthand translation, transport-safety params, the
    /// codex-reply shape, and the Δ5-2 /reviewer scoping.
    fn assert_codex_rules_contract(line: &str) {
        assert!(
            line.contains("gpt-5.6-sol"),
            "must name the preferred reviewer gpt-5.6-sol, got: {line}"
        );
        assert!(
            line.contains("skills pin the model and") && line.contains("exactly as the skill"),
            "must pass through the skills' explicit model+effort pins, got: {line}"
        );
        assert!(
            !line.contains("Do NOT pass a `model` parameter"),
            "the v0.4.17 blanket no-model rule must be GONE (it contradicts the \
             synced skills' pins), got: {line}"
        );
        // Canonical capability-only chain (reviewer-routing.md:20-29).
        assert!(
            line.contains("retry the SAME model at \"xhigh\"")
                && line.contains("only to deep-tier calls"),
            "effort downgrade must be same-model and deep-tier-only, got: {line}"
        );
        assert!(
            line.contains("explicit gpt-5.5"),
            "model-unknown fallback must be the EXPLICIT gpt-5.5 (never an \
             ambient default), got: {line}"
        );
        assert!(
            line.contains("NEVER auto-degrade on timeouts"),
            "transport/limit errors must never degrade, got: {line}"
        );
        // Δ4-1 legacy shorthand translation.
        assert!(
            line.contains("legacy `reasoning: ultra` shorthand")
                && line.contains("never send an unknown `reasoning` field"),
            "must translate the legacy shorthand instead of forwarding it, got: {line}"
        );
        // Approval/sandbox on every FRESH call; reply inherits.
        assert!(
            line.contains("approval-policy: \"never\"")
                && line.contains("explicit `sandbox`")
                && line.contains("FRESH `mcp__codex__codex` call"),
            "must pin approval-policy/sandbox on fresh calls, got: {line}"
        );
        assert!(
            line.contains("ONLY the thread id and prompt"),
            "codex-reply must carry only thread id + prompt, got: {line}"
        );
        // Gate round-2 BLOCKER: an explicit call-level model override must
        // DISABLE the automatic chain (explicit choice = contract)...
        assert!(
            line.contains("chain is DISABLED for that call"),
            "explicit call-level override must disable the auto chain, got: {line}"
        );
        // ...while Δ5-2 keeps /reviewer OUT of that definition.
        assert!(
            line.contains("controls the HTTP fallback exclusively"),
            "must scope explicit-override to the call, not /reviewer, got: {line}"
        );
    }

    #[test]
    fn reviewer_nudge_codex_mcp_with_fallback_mentions_llmreview_fallback() {
        let out = reviewer_routing_nudge("codex-mcp", Some("openai"));
        assert_eq!(out.len(), 1, "codex-mcp + fallback emits exactly one line");
        let line = &out[0];
        // Codex MCP is primary; LlmReview is only the fallback.
        assert!(
            line.contains("Your external LLM reviewer is Codex MCP")
                && line.contains("mcp__codex__codex"),
            "must instruct the model to use the Codex MCP channel, got: {line}"
        );
        assert_codex_rules_contract(line);
        // Δ5-1: fallback is PRE-DISPATCH-ONLY.
        assert!(
            line.contains("BEFORE dispatch") && line.contains("never re-target"),
            "HTTP fallback must be pre-dispatch-only, got: {line}"
        );
        assert!(
            line.contains("`LlmReview` tool") && line.contains("openai"),
            "must name the configured HTTP fallback reviewer, got: {line}"
        );
        // Δ4-1: parameter stripping on the re-target.
        assert!(
            line.contains("never forward the skill's Codex"),
            "must strip Codex params when re-targeting to LlmReview, got: {line}"
        );
        // Must NOT push the "use LlmReview instead" override.
        assert!(
            !line.contains("use the `LlmReview` tool instead"),
            "codex-mcp must not contradict the chosen reviewer, got: {line}"
        );
    }

    #[test]
    fn reviewer_nudge_codex_mcp_without_fallback_guides_mcp_no_model() {
        // v0.4.17 flipped this state from silent to one guidance line;
        // v0.4.22 (B1) replaced the blanket "never pass a model" rule with the
        // two-tier gpt-5.6-sol doctrine + canonical capability chain. An
        // empty/blank fallback string is still treated as "no fallback".
        for fallback in [None, Some(""), Some("  ")] {
            let out = reviewer_routing_nudge("codex-mcp", fallback);
            assert_eq!(
                out.len(),
                1,
                "no-fallback codex-mcp emits exactly one guidance line, got: {out:?}"
            );
            let line = &out[0];
            assert!(
                line.contains("Your external LLM reviewer is Codex MCP")
                    && line.contains("mcp__codex__codex"),
                "must direct the model to the Codex MCP channel, got: {line}"
            );
            assert_codex_rules_contract(line);
            // Must not contradict the chosen reviewer with the LlmReview override,
            // and (no fallback configured) must not advertise an HTTP fallback.
            assert!(
                !line.contains("use the `LlmReview` tool instead")
                    && !line.contains("HTTP fallback:"),
                "no-fallback codex-mcp must not mention any LlmReview path, got: {line}"
            );
        }
    }

    #[test]
    fn reviewer_nudge_non_codex_provider_pushes_llmreview_override() {
        // Any provider other than codex-mcp gets the LlmReview override so
        // skills' MCP review calls are redirected to the HTTP reviewer.
        for provider in ["", "openai", "gemini", "minimax", "codex"] {
            let out = reviewer_routing_nudge(provider, None);
            assert_eq!(
                out.len(),
                1,
                "provider {provider:?} should emit exactly one override line"
            );
            // v0.4.22 (Δ4-1): the override must also strip the skill's Codex
            // params so a synced skill's `model: gpt-5.6-sol` can't ride into
            // the HTTP reviewer.
            assert!(
                out[0].contains("never forward the skill's Codex"),
                "provider {provider:?} must strip Codex params, got: {}",
                out[0]
            );
            assert!(
                out[0].contains("use the `LlmReview` tool instead"),
                "provider {provider:?} must push the LlmReview override, got: {}",
                out[0]
            );
        }
        // A non-codex-mcp provider ignores any fallback value (override is fixed).
        let with_fb = reviewer_routing_nudge("openai", Some("gemini"));
        assert_eq!(with_fb, reviewer_routing_nudge("openai", None));
    }
}
