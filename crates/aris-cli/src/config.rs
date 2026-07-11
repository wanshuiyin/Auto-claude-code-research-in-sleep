//! ARIS persistent configuration.
//!
//! Stores API keys and model preferences in `~/.config/aris/config.json`.
//! Environment variables always take priority over saved config.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

const CONFIG_DIR: &str = ".config/aris";
const CONFIG_FILE: &str = "config.json";

/// Controls which env vars `apply_to_env_inner` is allowed to overwrite.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ApplyMode {
    /// Only set env vars that are currently unset. Shell-provided vars win.
    IfMissing,
    /// Clear + re-apply all executor AND reviewer env vars. Used by REPL
    /// `/setup` where the user explicitly reconfigured everything.
    ForceAll,
    /// Clear + re-apply only executor env vars. Used by mid-launch setup,
    /// which only asks about executor auth; reviewer env vars set by the
    /// user's shell must be preserved.
    ForceExecutorOnly,
}

/// v0.4.22 (C7/Δ-C7): a single config-diagnosis finding, with severity.
///
/// `Problem` = the config is broken or ignored (malformed JSON, misplaced
/// file) — doctor flips `all_ok`. `Warning` = the config parsed fine but
/// something looks off (e.g. unrecognized top-level keys, possibly from a
/// newer ARIS version or a nested structure) — doctor prints it but does
/// NOT flip `all_ok`. Before v0.4.22 both classes came back as a flat
/// `Option<String>`, so every hint flipped `all_ok` (main.rs doctor).
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ConfigDiagnostic {
    Problem(String),
    Warning(String),
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArisConfig {
    /// "anthropic" or "openai"
    #[serde(default)]
    pub executor_provider: Option<String>,
    #[serde(default)]
    pub executor_api_key: Option<String>,
    #[serde(default)]
    pub executor_base_url: Option<String>,
    #[serde(default)]
    pub executor_model: Option<String>,
    /// "gemini" / "openai" / ... / "codex-mcp"
    #[serde(default)]
    pub reviewer_provider: Option<String>,
    #[serde(default)]
    pub reviewer_api_key: Option<String>,
    #[serde(default)]
    pub reviewer_base_url: Option<String>,
    #[serde(default)]
    pub reviewer_model: Option<String>,
    /// v0.4.17 (T10/P1.2): the HTTP reviewer to fall back to when the primary
    /// reviewer is Codex MCP (`reviewer_provider == "codex-mcp"`) but the MCP
    /// channel is unavailable. Separating this from `reviewer_provider` keeps
    /// "MCP primary" and "fallback provider" as two distinct states — the
    /// fallback never usurps the primary the way it did when it was written
    /// straight into `reviewer_provider`. `#[serde(default)]` means an older
    /// `config.json` with no such key still parses (round-trip test locks this).
    /// The fallback's key, base URL, and model reuse the existing
    /// `reviewer_api_key` / `reviewer_base_url` / `reviewer_model` fields.
    #[serde(default)]
    pub reviewer_fallback_provider: Option<String>,
    /// "cn" or "en"
    #[serde(default)]
    pub language: Option<String>,
    /// Meta-logging level: "off", "metadata", or "content"
    #[serde(default)]
    pub meta_logging: Option<String>,
}

/// v0.4.22 (C7/Δ-C7): every serde field name of [`ArisConfig`], used by
/// `diagnose_misconfig_in` to flag unrecognized top-level keys in
/// `config.json` as a soft [`ConfigDiagnostic::Warning`]. MUST stay in sync
/// with the struct above — the `known_config_keys_match_aris_config_fields`
/// test serializes `ArisConfig::default()` and asserts key-set equality, so
/// adding a field without extending this list fails the build's tests.
const KNOWN_CONFIG_KEYS: &[&str] = &[
    "executor_provider",
    "executor_api_key",
    "executor_base_url",
    "executor_model",
    "reviewer_provider",
    "reviewer_api_key",
    "reviewer_base_url",
    "reviewer_model",
    "reviewer_fallback_provider",
    "language",
    "meta_logging",
];

impl ArisConfig {
    fn config_path() -> PathBuf {
        let home = runtime::home_dir();
        PathBuf::from(home).join(CONFIG_DIR).join(CONFIG_FILE)
    }

    pub fn load() -> Self {
        let path = Self::config_path();
        if !path.exists() {
            return Self::default();
        }
        fs::read_to_string(&path)
            .ok()
            .and_then(|content| serde_json::from_str(&content).ok())
            .unwrap_or_default()
    }

    /// v0.4.18 (#259): detect the two silent-misconfiguration traps.
    /// v0.4.22 (C7/Δ-C7): returns a list of [`ConfigDiagnostic`]s instead of a
    /// flat `Option<String>` so doctor can distinguish hard `Problem`s
    /// (malformed / misplaced config — flips `all_ok`) from soft `Warning`s
    /// (unrecognized top-level keys — printed only). Empty vec = config fine,
    /// including the normal first-run "no config" case — so this never nags
    /// new users.
    ///
    /// `load()` swallows a malformed config via `unwrap_or_default()`, and ARIS
    /// reads only `~/.config/aris/config.json` (flat JSON) — so a user who put
    /// YAML or nested keys, or used the wrong path, gets "my config is silently
    /// ignored and I can't tell why". This surfaces that. It is purely
    /// diagnostic: it never mutates anything and `load()` stays unchanged, so
    /// callers still get a valid `ArisConfig` on every path.
    #[must_use]
    pub(crate) fn diagnose_misconfig() -> Vec<ConfigDiagnostic> {
        Self::diagnose_misconfig_in(&runtime::home_dir())
    }

    /// Home-parameterized core of [`diagnose_misconfig`] so it can be unit-tested
    /// against a temp directory without mutating the process `$HOME`.
    fn diagnose_misconfig_in(home: &str) -> Vec<ConfigDiagnostic> {
        let path = PathBuf::from(home).join(CONFIG_DIR).join(CONFIG_FILE);
        if path.exists() {
            // File present — is it parseable as our flat JSON shape?
            let content = fs::read_to_string(&path).ok();
            let parses = content
                .as_deref()
                .and_then(|content| serde_json::from_str::<Self>(content).ok())
                .is_some();
            if parses {
                // v0.4.22 (C7/Δ-C7): the typed parse SUCCEEDED (serde ignores
                // unknown fields), but unrecognized top-level keys usually mean
                // a nested structure or a newer ARIS's config — surface them as
                // a soft Warning so the user learns why a setting is ignored.
                if let Some(warning) = content.as_deref().and_then(Self::unknown_key_warning) {
                    return vec![ConfigDiagnostic::Warning(warning)];
                }
                return Vec::new();
            }
            return vec![ConfigDiagnostic::Problem(format!(
                "found {} but could not parse it as ARIS's flat JSON config — ignoring it. \
                 Expected top-level keys like executor_provider / executor_api_key / \
                 executor_model / executor_base_url / reviewer_provider / language. \
                 Run `aris setup` to rewrite it.",
                path.display()
            ))];
        }
        // Real config absent — look for a misplaced / wrong-format stray so the
        // user isn't left wondering why their settings are ignored.
        let strays = [
            ".aris/config.yaml",
            ".aris/config.yml",
            ".aris/config.json",
            ".config/aris/config.yaml",
            ".config/aris/config.yml",
            "aris.yaml",
            "aris.yml",
        ];
        for rel in strays {
            let candidate = PathBuf::from(home).join(rel);
            if candidate.exists() {
                return vec![ConfigDiagnostic::Problem(format!(
                    "found {} but ARIS reads {} (flat JSON, not YAML or nested keys). \
                     Run `aris setup` to generate the correct file.",
                    candidate.display(),
                    path.display()
                ))];
            }
        }
        Vec::new()
    }

    /// v0.4.22 (C7/Δ-C7): given the raw text of a config.json whose TYPED parse
    /// succeeded, re-parse it as a `serde_json::Value` and compare top-level
    /// keys against [`KNOWN_CONFIG_KEYS`]. Unknown keys produce ONE warning
    /// message; `None` when the value is not an object or every key is known.
    ///
    /// Display discipline (v0.4.17 `sanitize_for_display` class of bug — key
    /// names come from a user-editable file, so they are terminal-injection
    /// surface): keys are sorted, control-char-stripped, capped at 40 chars
    /// each, at most 5 are listed ("… and N more" after that), and the whole
    /// message is capped at ~300 chars.
    fn unknown_key_warning(content: &str) -> Option<String> {
        const MAX_KEYS_SHOWN: usize = 5;
        const MAX_MESSAGE_CHARS: usize = 300;
        let value: serde_json::Value = serde_json::from_str(content).ok()?;
        let obj = value.as_object()?;
        let mut unknown: Vec<String> = obj
            .keys()
            .filter(|k| !KNOWN_CONFIG_KEYS.contains(&k.as_str()))
            .map(|k| sanitize_config_key(k))
            .collect();
        if unknown.is_empty() {
            return None;
        }
        unknown.sort();
        let total = unknown.len();
        let mut list = unknown[..total.min(MAX_KEYS_SHOWN)].join(", ");
        if total > MAX_KEYS_SHOWN {
            use std::fmt::Write as _;
            let _ = write!(list, " … and {} more", total - MAX_KEYS_SHOWN);
        }
        let mut msg = format!(
            "config.json contains unrecognized top-level keys (possibly from a newer \
             ARIS version, or a nested structure — ARIS expects flat top-level keys): {list}"
        );
        if msg.chars().count() > MAX_MESSAGE_CHARS {
            msg = msg.chars().take(MAX_MESSAGE_CHARS - 1).collect();
            msg.push('…');
        }
        Some(msg)
    }

    pub fn save(&self) -> io::Result<()> {
        let path = Self::config_path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self)
            .map_err(io::Error::other)?;
        fs::write(&path, json)
    }

    /// Apply saved config to environment variables.
    /// Only sets vars that are currently unset or empty — shell-provided vars
    /// always win. Used at startup before we know what auth the user has.
    pub fn apply_to_env(&self) {
        self.apply_to_env_inner(ApplyMode::IfMissing);
    }

    /// Full clear + re-apply of both executor AND reviewer env vars.
    /// Used by REPL `/setup` where the user explicitly reconfigured everything.
    pub fn force_apply_to_env(&self) {
        self.apply_to_env_inner(ApplyMode::ForceAll);
    }

    /// Clear + re-apply only executor env vars; leave reviewer env vars alone.
    /// Used by the mid-launch setup wizard, which only asks about executor auth
    /// when that auth is missing. A shell-provided reviewer key (e.g.
    /// `OPENAI_API_KEY` for the reviewer) must not be wiped just because the
    /// user typed in an Anthropic executor key.
    pub fn force_apply_executor_env(&self) {
        self.apply_to_env_inner(ApplyMode::ForceExecutorOnly);
    }

    fn apply_to_env_inner(&self, mode: ApplyMode) {
        let force_exec = matches!(mode, ApplyMode::ForceAll | ApplyMode::ForceExecutorOnly);
        let force_rev = matches!(mode, ApplyMode::ForceAll);

        if force_exec {
            // Clear executor-related env vars to prevent cross-contamination
            // between providers when switching.
            std::env::remove_var("EXECUTOR_PROVIDER");
            std::env::remove_var("EXECUTOR_API_KEY");
            std::env::remove_var("EXECUTOR_BASE_URL");
            std::env::remove_var("ANTHROPIC_API_KEY");
            std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
            std::env::remove_var("ANTHROPIC_BASE_URL");
            // `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` is executor-scoped (it
            // controls whether the Anthropic client attaches beta headers),
            // so it belongs in the executor clear block, not the reviewer one.
            std::env::remove_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS");
        }
        if force_rev {
            // Clear reviewer-related env vars — only when user explicitly
            // reconfigured reviewer via REPL /setup. NOT cleared by mid-launch
            // executor-only setup, to preserve shell-provided reviewer keys.
            std::env::remove_var("OPENAI_API_KEY");
            std::env::remove_var("GEMINI_API_KEY");
            std::env::remove_var("GLM_API_KEY");
            std::env::remove_var("MINIMAX_API_KEY");
            std::env::remove_var("KIMI_API_KEY");
            std::env::remove_var("ARIS_REVIEWER_MODEL");
            std::env::remove_var("ARIS_REVIEWER_BASE_URL");
            std::env::remove_var("ARIS_REVIEWER_PROVIDER");
            std::env::remove_var("ARIS_REVIEWER_AUTH_TOKEN");
            // v0.4.17 (T10/P1.2): the Codex-MCP fallback provider env var.
            std::env::remove_var("ARIS_REVIEWER_FALLBACK_PROVIDER");
        }
        // The rest of the function uses `force_exec` and `force_rev` to decide
        // whether to overwrite existing env vars.
        let force = force_exec;
        let force_reviewer = force_rev;

        if let Some(provider) = &self.executor_provider {
            // Gate this write like every sibling field below: in IfMissing mode a
            // shell-provided EXECUTOR_PROVIDER must win (honoring the function
            // docstring), so a saved openai/custom config can no longer silently
            // re-point a shell-set EXECUTOR_PROVIDER=anthropic at startup. In Force*
            // modes EXECUTOR_PROVIDER was already remove_var'd above, so `force`
            // still applies the value → the explicit /setup path is unchanged.
            if (provider == "openai" || provider == "custom")
                && (force || std::env::var("EXECUTOR_PROVIDER").is_err())
            {
                std::env::set_var("EXECUTOR_PROVIDER", "openai");
            }
        }

        // Executor API key + base URL
        let provider = self.executor_provider.as_deref().unwrap_or("anthropic");
        if let Some(key) = &self.executor_api_key {
            match provider {
                "anthropic" => {
                    if force || std::env::var("ANTHROPIC_API_KEY").is_err() {
                        std::env::set_var("ANTHROPIC_API_KEY", key);
                    }
                    if let Some(url) = &self.executor_base_url {
                        if force || std::env::var("ANTHROPIC_BASE_URL").is_err() {
                            std::env::set_var("ANTHROPIC_BASE_URL", url);
                        }
                        // Third-party providers may reject Anthropic-specific beta flags
                        if force || std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err()
                        {
                            std::env::set_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1");
                        }
                    }
                }
                "anthropic-compat" => {
                    // MiniMax etc: Anthropic-compatible endpoint with bearer token
                    if force || std::env::var("ANTHROPIC_AUTH_TOKEN").is_err() {
                        std::env::set_var("ANTHROPIC_AUTH_TOKEN", key);
                    }
                    if let Some(url) = &self.executor_base_url {
                        if force || std::env::var("ANTHROPIC_BASE_URL").is_err() {
                            std::env::set_var("ANTHROPIC_BASE_URL", url);
                        }
                        // Third-party providers may reject Anthropic-specific beta flags
                        if force || std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err()
                        {
                            std::env::set_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1");
                        }
                    }
                }
                "openai" | "custom" => {
                    if force || std::env::var("EXECUTOR_API_KEY").is_err() {
                        std::env::set_var("EXECUTOR_API_KEY", key);
                    }
                }
                _ => {}
            }
        }

        // Executor base URL (for openai-compat providers)
        if provider == "openai" || provider == "custom" {
            if force || std::env::var("EXECUTOR_BASE_URL").is_err() {
                if let Some(url) = &self.executor_base_url {
                    std::env::set_var("EXECUTOR_BASE_URL", url);
                }
            }
        }

        // Reviewer API key — gated on force_reviewer, not force_exec, so
        // executor-only force does not clobber shell-provided reviewer keys.
        if let Some(reviewer_provider) = &self.reviewer_provider {
            // v0.4.17 (T10/P1.2): when Codex MCP is the PRIMARY reviewer, the
            // HTTP key/model fields belong to the *fallback* provider, not to
            // codex-mcp (which has no HTTP credentials). The key env var must be
            // chosen from `reviewer_fallback_provider`, NOT `reviewer_provider`.
            // We export the fallback key only when both a fallback provider and
            // a key are present; with no fallback, nothing HTTP is exported
            // (zero stale state).
            let key_provider = if reviewer_provider == "codex-mcp" {
                self.reviewer_fallback_provider.as_deref()
            } else {
                Some(reviewer_provider.as_str())
            };
            if let (Some(kp), Some(key)) = (key_provider, &self.reviewer_api_key) {
                if let Some(key_env) = reviewer_key_env(kp) {
                    if force_reviewer || std::env::var(key_env).is_err() {
                        std::env::set_var(key_env, key);
                    }
                }
            }
            // Set reviewer provider env var. For codex-mcp this stays
            // "codex-mcp" (MCP primary); the fallback provider is exported
            // separately below as ARIS_REVIEWER_FALLBACK_PROVIDER so it never
            // usurps the primary (the P1.2 bug: fallback written into
            // reviewer_provider made the MCP gate think MCP was unselected).
            if force_reviewer || std::env::var("ARIS_REVIEWER_PROVIDER").is_err() {
                std::env::set_var("ARIS_REVIEWER_PROVIDER", reviewer_provider);
            }
            // v0.4.17 (T10/P1.2): for codex-mcp primary, export the fallback
            // provider name (used by LlmReview's effective-provider resolution
            // and the system-prompt gate). No fallback ⇒ nothing exported.
            if reviewer_provider == "codex-mcp" {
                if let Some(fallback) = &self.reviewer_fallback_provider {
                    if force_reviewer || std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER").is_err() {
                        std::env::set_var("ARIS_REVIEWER_FALLBACK_PROVIDER", fallback);
                    }
                }
            }
        }

        // Reviewer base URL
        if force_reviewer || std::env::var("ARIS_REVIEWER_BASE_URL").is_err() {
            if let Some(url) = &self.reviewer_base_url {
                std::env::set_var("ARIS_REVIEWER_BASE_URL", url);
            }
        }

        // Reviewer model
        if force_reviewer || std::env::var("ARIS_REVIEWER_MODEL").is_err() {
            if let Some(model) = &self.reviewer_model {
                std::env::set_var("ARIS_REVIEWER_MODEL", model);
            }
        }

        // Language
        if force || std::env::var("ARIS_LANGUAGE").is_err() {
            if let Some(lang) = &self.language {
                std::env::set_var("ARIS_LANGUAGE", lang);
            }
        }

        // Meta-logging
        if force || std::env::var("ARIS_META_LOGGING").is_err() {
            if let Some(level) = &self.meta_logging {
                std::env::set_var("ARIS_META_LOGGING", level);
            }
        }
    }

    /// Returns the executor model from config, or None.
    ///
    /// v0.4.22 (Δ-C2): a blank (empty or whitespace-only) saved model is
    /// treated as ABSENT — consumers get `None`, never `Some("")`, so a blank
    /// custom/OpenAI model can no longer masquerade as a configured one.
    pub fn executor_model(&self) -> Option<&str> {
        self.executor_model
            .as_deref()
            .filter(|m| !m.trim().is_empty())
    }
}

/// v0.4.22 (C7/Δ-C7): sanitize a config.json top-level key name for terminal
/// display — strip control characters (ANSI/terminal injection guard, same
/// discipline as v0.4.17's sanitize_for_display) and cap at 40 chars.
fn sanitize_config_key(key: &str) -> String {
    key.chars().filter(|c| !c.is_control()).take(40).collect()
}

/// v0.4.17 (T10/P1.2): map a reviewer provider string to the env var its API
/// key is exported under. Single source of truth for both the normal-provider
/// path and the Codex-MCP fallback path in `apply_to_env_inner`, so the two can
/// never drift on which env var a given provider's key lands in. Returns `None`
/// for providers that carry no HTTP key (e.g. `codex-mcp`) or unknown strings.
fn reviewer_key_env(provider: &str) -> Option<&'static str> {
    match provider {
        "gemini" => Some("GEMINI_API_KEY"),
        "openai" => Some("OPENAI_API_KEY"),
        "glm" => Some("GLM_API_KEY"),
        "minimax" => Some("MINIMAX_API_KEY"),
        "kimi" => Some("KIMI_API_KEY"),
        // anthropic-compat / deepseek / custom all store their key in the
        // dedicated reviewer auth token so it never collides with the
        // executor's OPENAI_API_KEY.
        "anthropic-compat" | "deepseek" | "custom" => Some("ARIS_REVIEWER_AUTH_TOKEN"),
        _ => None,
    }
}

/// Interactive setup wizard. Returns the configured settings.
pub fn run_interactive_setup() -> io::Result<ArisConfig> {
    let mut config = ArisConfig::load();

    println!("\x1b[1mARIS Setup\x1b[0m");
    println!("\x1b[2mConfigure API keys and models. Press Enter to keep current value.\x1b[0m\n");

    // ── Step 1+2: Executor provider + key + model ──
    println!("\x1b[1m[1/3] Executor (main LLM)\x1b[0m");
    println!("  1. Anthropic   (claude-opus / sonnet / haiku)");
    println!("  2. OpenAI      (gpt-5.5)");
    println!("  3. Gemini      (gemini-2.5-pro)");
    println!("  4. GLM         (GLM-5)");
    println!("  5. MiniMax     (MiniMax-M2.7)");
    println!("  6. Kimi        (kimi-k2.5)");
    println!("  7. DeepSeek    (deepseek-v4-pro)");
    println!("  8. Xiaomi      (mimo-v2.5-pro)");
    println!("  9. Qwen        (qwen3.6-plus)");
    println!(" 10. Doubao      (doubao-pro-4k)");
    println!(" 11. Custom      (OpenAI-compatible endpoint)");

    let default_executor = match config.executor_provider.as_deref() {
        Some("anthropic") => "1",
        Some("anthropic-compat") => match config.executor_base_url.as_deref() {
            Some(u) if u.contains("deepseek") => "7",
            _ => "1",
        },
        Some("custom") => "11",
        Some("openai") => match config.executor_base_url.as_deref() {
            Some(u) if u.contains("googleapis") => "3",
            Some(u) if u.contains("bigmodel") => "4",
            Some(u) if u.contains("minimax") => "5",
            Some(u) if u.contains("moonshot") => "6",
            Some(u) if u.contains("xiaomimimo") => "8",
            Some(u) if u.contains("dashscope") => "9",
            Some(u) if u.contains("volces") => "10",
            _ => "2",
        },
        _ => "1",
    };
    let exec_choice_raw = prompt_with_default("  Choose [1-11]", default_executor)?;
    let exec_choice = exec_choice_raw.trim();
    // Detect real menu change, not just provider-string change. OpenAI / Gemini /
    // GLM / MiniMax / Kimi all serialize to provider="openai" so we must compare
    // the menu choice to catch switches like "OpenAI → Kimi" properly.
    let switched_executor = exec_choice != default_executor;

    // (provider, key_env, key_label, base_url, default_model)
    let exec_info: (&str, &str, &str, Option<&str>, &str) = match exec_choice {
        "2" => (
            "openai",
            "EXECUTOR_API_KEY",
            "OpenAI API key",
            Some("https://api.openai.com/v1"),
            "gpt-5.5",
        ),
        "3" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Gemini API key",
            Some("https://generativelanguage.googleapis.com/v1beta/openai"),
            "gemini-2.5-pro",
        ),
        "4" => (
            "openai",
            "EXECUTOR_API_KEY",
            "GLM API key",
            Some("https://open.bigmodel.cn/api/paas/v4"),
            "GLM-5",
        ),
        "5" => (
            "openai",
            "EXECUTOR_API_KEY",
            "MiniMax API key",
            Some("https://api.minimax.chat/v1"),
            "MiniMax-M2.7",
        ),
        "6" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Kimi API key",
            Some("https://api.moonshot.cn/v1"),
            "kimi-k2.5",
        ),
        "7" => (
            "anthropic-compat",
            "ANTHROPIC_AUTH_TOKEN",
            "DeepSeek API key",
            Some("https://api.deepseek.com/anthropic"),
            "deepseek-v4-pro",
        ),
        "8" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Xiaomi API key",
            Some("https://token-plan-cn.xiaomimimo.com/v1"),
            "mimo-v2.5-pro",
        ),
        "9" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Qwen (DashScope) API key",
            Some("https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "qwen3.6-plus",
        ),
        "10" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Doubao (Ark) API key",
            Some("https://ark.cn-beijing.volces.com/api/v3"),
            "doubao-pro-4k",
        ),
        "11" => ("custom", "EXECUTOR_API_KEY", "API key", None, ""),
        _ => (
            "anthropic",
            "ANTHROPIC_API_KEY",
            "Anthropic API key",
            None,
            "claude-opus-4-8",
        ),
    };

    // Preserve an explicit `anthropic-compat` choice across re-runs of `/setup`.
    // Menu option 1 covers both `anthropic` (x-api-key) and `anthropic-compat`
    // (Bearer) — if the user had Bearer mode set previously (e.g. for a proxy
    // that requires it) and stays on option 1, we must NOT silently downgrade
    // them to `anthropic`. Switching menu options obviously resets this.
    let prev_provider = config.executor_provider.as_deref();
    let target_provider = if !switched_executor
        && exec_info.0 == "anthropic"
        && prev_provider == Some("anthropic-compat")
    {
        "anthropic-compat"
    } else {
        exec_info.0
    };
    config.executor_provider = Some(target_provider.into());

    // Only overwrite base_url + clear stale key when user actually switched
    // to a different menu option. If they stayed on the same option, preserve
    // any custom base_url they typed previously (e.g. OpenRouter, newcli.com
    // proxy). Previously we always overwrote the URL to the provider's built-in
    // default, which silently wiped custom URLs between setup runs.
    if switched_executor {
        if let Some(url) = exec_info.3 {
            config.executor_base_url = Some(url.into());
        } else {
            config.executor_base_url = None;
        }
        config.executor_api_key = None;
        // Clear stale model on menu switch. For built-in providers the next
        // line overwrites this with `exec_info.4` anyway, but for the Custom
        // option this matters: otherwise switching from OpenAI/Gemini → Custom
        // would carry forward `gpt-5.5` / `gemini-2.5-pro` as the "current"
        // custom model, and the post-fetch fallback prompt (which only fires
        // when executor_model is empty) would be skipped.
        config.executor_model = None;
    }

    // Ask for API key
    let current_key_masked = config
        .executor_api_key
        .as_deref()
        .filter(|k| k.len() > 8)
        .map(|k| format!("{}...{}", &k[..4], &k[k.len() - 4..]))
        .unwrap_or_else(|| "(not set)".into());
    let new_key = prompt_with_default(&format!("  {} [{current_key_masked}]", exec_info.2), "")?;
    if !new_key.is_empty() {
        config.executor_api_key = Some(new_key);
    }

    // Show known-working proxy URLs before the prompt (provider-aware).
    print_executor_url_hints(exec_choice);

    // Ask for proxy/custom base URL (all providers). The prompt text says
    // "Enter to keep" — pressing Enter preserves the current value, it does
    // NOT reset to the provider's official default. To switch back to the
    // official endpoint, type the URL explicitly.
    let current_url_hint = config
        .executor_base_url
        .as_deref()
        .unwrap_or("(none — uses official default)");
    let custom_url = prompt_with_default(
        &format!("  Proxy base URL [{current_url_hint}] (Enter to keep)"),
        "",
    )?;
    if !custom_url.is_empty() {
        config.executor_base_url = Some(custom_url.clone());
    }
    // NOTE (v0.4.4): Removed the auto-switch from "anthropic" to
    // "anthropic-compat" when a custom URL was entered. Anthropic-format
    // proxies like code.newcli.com/claude and api-inference.modelscope.cn
    // accept `x-api-key` (which the `anthropic` provider path sends), not
    // `Authorization: Bearer` (which `anthropic-compat` forces) — the old
    // auto-switch made issues #158 and #162 unreachable via the UI.

    // Auto-set best model for the chosen provider
    if exec_choice == "11" {
        // Custom provider: try fetching available models from /models endpoint
        let api_key = config.executor_api_key.as_deref().unwrap_or("");
        let base_url = config.executor_base_url.as_deref().unwrap_or("");
        if !api_key.is_empty() && !base_url.is_empty() {
            println!("  \x1b[2mFetching models from {base_url}...\x1b[0m");
            match crate::openai_compat::fetch_openai_models(base_url, api_key) {
                Ok(models) => {
                    let current = config.executor_model.as_deref().unwrap_or("");
                    let items = crate::openai_compat::model_select_items(&models, current);
                    match crate::input::select_menu(
                        "Select model",
                        "Choose a model from the provider's /models endpoint.",
                        &items,
                    ) {
                        Ok(Some(idx)) => {
                            config.executor_model = Some(items[idx].label.clone());
                        }
                        Ok(None) => {
                            // User cancelled — keep existing model
                        }
                        Err(_) => {
                            // select_menu I/O error — fall through to manual
                        }
                    }
                }
                Err(err) => {
                    println!("  \x1b[33m⚠ Could not fetch models: {err}\x1b[0m");
                    println!("  \x1b[2mYou can type the model name manually below.\x1b[0m");
                }
            }
        }
        // If no model set yet (fetch failed or user has no key/url), ask manually
        if config.executor_model.as_deref().unwrap_or("").is_empty() {
            let current_model_hint = config.executor_model.as_deref().unwrap_or("(not set)");
            let custom_model = prompt_with_default(
                &format!("  Model name [{current_model_hint}]"),
                config.executor_model.as_deref().unwrap_or(""),
            )?;
            if !custom_model.is_empty() {
                config.executor_model = Some(custom_model.clone());
            }
        }
        println!(
            "  \x1b[2mModel: {}\x1b[0m",
            config.executor_model.as_deref().unwrap_or("(none)")
        );
    } else {
        config.executor_model = Some(exec_info.4.to_string());
        println!("  \x1b[2mModel: {}\x1b[0m", exec_info.4);
    }

    // v0.4.22 (Δ5-4): an OpenAI/custom executor with a blank model MUST be
    // rejected HERE, at the executor step — before the reviewer step (which
    // set_vars reviewer keys into the live env) and before save(). A later
    // check could not restore that state. Re-prompt until a non-blank model
    // id arrives; on EOF / non-interactive stdin, abort the wizard with an
    // error WITHOUT saving (env, runtime, and config file all untouched).
    while executor_model_required(
        target_provider,
        config.executor_model.as_deref().unwrap_or(""),
    ) {
        println!("  \x1b[33m⚠ an OpenAI/custom executor requires an explicit model id.\x1b[0m");
        match prompt_line_eof_aware("  Model name (required)")? {
            Some(model) if !model.trim().is_empty() => {
                config.executor_model = Some(model.trim().to_string());
            }
            Some(_) => {
                // Blank again — loop back and re-prompt.
            }
            None => {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "setup aborted: an OpenAI/custom executor requires an explicit model id, \
                     but stdin closed before one was provided — nothing was saved",
                ));
            }
        }
    }

    // ── Step 4: Reviewer ──
    println!("\n\x1b[1m[2/3] Reviewer (for cross-model review)\x1b[0m");
    println!(
        "  \x1b[2m★ Option 10 (Codex MCP) needs no API key — uses your ChatGPT subscription.\x1b[0m"
    );
    println!("  1. OpenAI          (gpt-5.5)");
    println!("  2. Gemini          (gemini-2.5-pro)");
    println!("  3. GLM             (GLM-5)");
    println!("  4. MiniMax         (MiniMax-M2.7)");
    println!("  5. Kimi            (kimi-k2.5)");
    println!("  6. Anthropic Proxy (claude via proxy)");
    println!("  7. DeepSeek        (deepseek-v4-pro)");
    println!("  8. Skip (no reviewer)");
    println!("  9. Custom          (OpenAI-compatible endpoint)");
    // v0.4.17 (T10): APPENDED, not reordered — reordering would break the
    // `main.rs` "aris setup → option 7 (DeepSeek)" reference (the v0.4.14 P9
    // regression). Codex MCP routes external reviews through Claude Code's own
    // `mcp__codex__codex` channel (no API key).
    println!(" 10. Codex MCP (ChatGPT subscription, no API key) \x1b[1m★recommended\x1b[0m");
    let default_reviewer = default_reviewer_choice(config.reviewer_provider.as_deref());
    let reviewer_choice_raw = prompt_with_default("  Choose [1-10]", default_reviewer)?;
    let reviewer_choice = reviewer_choice_raw.trim();
    let switched_reviewer = reviewer_choice != default_reviewer;

    // v0.4.17 (T10): Codex MCP reviewer — special-cased BEFORE the
    // `reviewer_info` match below, because that match's `_ => None` arm would
    // clear `reviewer_provider` (config.rs `else` branch) and wipe the choice.
    if reviewer_choice == "10" {
        configure_codex_mcp_reviewer(&mut config)?;
        // Skip the API-reviewer key/URL/model prompts entirely; codex-mcp uses
        // no HTTP reviewer credentials. If the user opted into a fallback inside
        // `configure_codex_mcp_reviewer`, the primary stays "codex-mcp" and the
        // fallback provider is stored in `reviewer_fallback_provider` (T10/P1.2),
        // whose key/url/model export via apply_to_env's codex-mcp fallback arm.
    } else {

    // (provider_name, key_env_var, key_label, default_model)
    let reviewer_info: Option<(&str, &str, &str, &str)> = match reviewer_choice {
        "1" => Some(("openai", "OPENAI_API_KEY", "OpenAI API key", "gpt-5.5")),
        "2" => Some((
            "gemini",
            "GEMINI_API_KEY",
            "Gemini API key",
            "gemini-2.5-pro",
        )),
        "3" => Some(("glm", "GLM_API_KEY", "GLM API key", "GLM-5")),
        "4" => Some((
            "minimax",
            "MINIMAX_API_KEY",
            "MiniMax API key",
            "MiniMax-M2.7",
        )),
        "5" => Some(("kimi", "KIMI_API_KEY", "Kimi API key", "kimi-k2.5")),
        "6" => Some((
            "anthropic-compat",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "Reviewer auth token",
            "claude-sonnet-4-6",
        )),
        "7" => Some((
            "deepseek",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "DeepSeek API key",
            "deepseek-v4-pro",
        )),
        "9" => Some(("custom", "ARIS_REVIEWER_AUTH_TOKEN", "API key", "")),
        _ => None,
    };

    if let Some((provider, key_env, key_label, default_model)) = reviewer_info {
        config.reviewer_provider = Some(provider.into());
        // Clear stale reviewer state when switching menu option. Without this,
        // e.g. Kimi → OpenAI leaves the moonshot URL saved as reviewer_base_url
        // and the old Kimi key as reviewer_api_key — both get shown as
        // "current" values for the new OpenAI provider, producing confused
        // configs (seen in issue #158 testing).
        if switched_reviewer {
            config.reviewer_api_key = None;
            config.reviewer_base_url = None;
            // Same reasoning as the executor switch above: clear stale model so
            // the Custom-reviewer fetch-failure fallback prompt actually fires.
            config.reviewer_model = None;
        }

        // Ask for API key
        let current_masked = std::env::var(key_env)
            .ok()
            .or_else(|| config.reviewer_api_key.clone())
            .filter(|k| k.len() > 8)
            .map(|k| format!("{}...{}", &k[..4], &k[k.len() - 4..]))
            .unwrap_or_else(|| "(not set)".into());
        let new_key = prompt_with_default(&format!("  {key_label} [{current_masked}]"), "")?;
        if !new_key.is_empty() {
            config.reviewer_api_key = Some(new_key.clone());
            std::env::set_var(key_env, &new_key);
        } else if let Some(existing) = &config.reviewer_api_key {
            std::env::set_var(key_env, existing);
        }

        // Show known-working proxy URLs before the prompt (provider-aware).
        print_reviewer_url_hints(reviewer_choice);

        // Ask for proxy/custom base URL for reviewer
        let current_reviewer_url = config
            .reviewer_base_url
            .as_deref()
            .unwrap_or("(none — uses official default)");
        let custom_reviewer_url = prompt_with_default(
            &format!("  Proxy base URL [{current_reviewer_url}] (Enter to keep)"),
            "",
        )?;
        if !custom_reviewer_url.is_empty() {
            config.reviewer_base_url = Some(custom_reviewer_url);
        }

        // Auto-set best model for the chosen reviewer provider
        // v0.4.8 fix: Custom is menu option 9, not 8 (8 is "Skip"). The
        // previous "8" check meant Custom fell through to the else branch
        // (`reviewer_model = Some(default_model)` = `Some("")` since custom's
        // default_model is the empty string), which then persisted in
        // config.json and caused every reboot to reset reviewer to the
        // gpt-5.5 fallback chain in main.rs.
        if reviewer_choice == "9" {
            // Custom provider: try fetching available models from /models endpoint
            let api_key = config.reviewer_api_key.as_deref().unwrap_or("");
            let base_url = config.reviewer_base_url.as_deref().unwrap_or("");
            if !api_key.is_empty() && !base_url.is_empty() {
                println!("  \x1b[2mFetching models from {base_url}...\x1b[0m");
                match crate::openai_compat::fetch_openai_models(base_url, api_key) {
                    Ok(models) => {
                        let current = config.reviewer_model.as_deref().unwrap_or("");
                        let items = crate::openai_compat::model_select_items(&models, current);
                        match crate::input::select_menu(
                            "Select reviewer model",
                            "Choose a model from the provider's /models endpoint.",
                            &items,
                        ) {
                            Ok(Some(idx)) => {
                                config.reviewer_model = Some(items[idx].label.clone());
                            }
                            Ok(None) => {}
                            Err(_) => {}
                        }
                    }
                    Err(err) => {
                        println!("  \x1b[33m⚠ Could not fetch models: {err}\x1b[0m");
                        println!("  \x1b[2mYou can type the model name manually below.\x1b[0m");
                    }
                }
            }
            // If no model set yet, ask manually
            if config.reviewer_model.as_deref().unwrap_or("").is_empty() {
                let current_model_hint = config.reviewer_model.as_deref().unwrap_or("(not set)");
                let custom_model = prompt_with_default(
                    &format!("  Model name [{current_model_hint}]"),
                    config.reviewer_model.as_deref().unwrap_or(""),
                )?;
                if !custom_model.is_empty() {
                    config.reviewer_model = Some(custom_model.clone());
                }
            }
            println!(
                "  \x1b[2mModel: {}\x1b[0m",
                config.reviewer_model.as_deref().unwrap_or("(none)")
            );
        } else {
            config.reviewer_model = Some(default_model.to_string());
            println!("  \x1b[2mModel: {default_model}\x1b[0m");
        }
    } else {
        config.reviewer_provider = None;
        config.reviewer_api_key = None;
        config.reviewer_base_url = None;
        config.reviewer_model = None;
    }
    } // end: non-codex-mcp reviewer branch (v0.4.17 T10)

    // ── Step 5: Language ──
    println!("\n\x1b[1m[3/3] Language\x1b[0m");
    println!("  1. 中文 (CN)");
    println!("  2. English (EN)");
    let lang_choice = prompt_with_default(
        "  Choose [1/2]",
        match config.language.as_deref() {
            Some("en") => "2",
            _ => "1",
        },
    )?;
    config.language = Some(
        if lang_choice.trim() == "2" {
            "en"
        } else {
            "cn"
        }
        .into(),
    );

    // ── Save ──
    println!("\n\x1b[1mSaving configuration\x1b[0m");
    config.save()?;
    let path = ArisConfig::config_path();
    println!("  Saved to {}", path.display());

    println!("\n\x1b[1;32m✓ Setup complete!\x1b[0m Run `aris` to start.\n");

    Ok(config)
}

/// v0.4.17 (T10): map a saved `reviewer_provider` to the reviewer-menu default
/// choice. Pure (no I/O) so it can be unit-tested for the round-trip
/// `Some("codex-mcp") -> "10"` (the bug class: a missing arm would let the
/// default drift to "8"/Skip on the next `setup`). Mirrors the menu order in
/// `run_interactive_setup`.
// `openai` and `None` both map to "1" intentionally (the menu default is
// OpenAI); keeping them as distinct arms mirrors the original inline match and
// documents each provider's slot explicitly.
#[allow(clippy::match_same_arms)]
fn default_reviewer_choice(provider: Option<&str>) -> &'static str {
    match provider {
        Some("openai") => "1",
        Some("gemini") => "2",
        Some("glm") => "3",
        Some("minimax") => "4",
        Some("kimi") => "5",
        Some("anthropic-compat") => "6",
        Some("deepseek") => "7",
        Some("custom") => "9",
        // v0.4.17 (T10): keep the Codex MCP default sticky across runs.
        Some("codex-mcp") => "10",
        None => "1",
        _ => "8",
    }
}

/// v0.4.17 (T10): interactive flow for the Codex MCP reviewer (menu option 10).
///
/// 1. `which codex` detection — if missing, print an install hint and ask
///    whether to still write the config.
/// 2. Idempotently merge `mcpServers.codex = {command, args, [trust]}` into the
///    `ConfigLoader` user-scope settings file (`~/.claude/settings.json`) via the
///    atomic-write/backup helper. An existing `mcpServers.codex` is NOT
///    clobbered. **P1.1:** if this write FAILS, the entire option-10 branch is
///    aborted — `config` is left exactly as it was (the previous reviewer config
///    is preserved) so we never advertise a Codex MCP reviewer whose server
///    entry never landed in settings.json (an unrecoverable bad state).
/// 3. Ask whether to trust the server (skip per-call approval).
/// 4. Optionally configure an API reviewer as a fallback (routes through the
///    SAME menu choices 1-9). **P1.2:** when a fallback is chosen, the primary
///    `reviewer_provider` STAYS `"codex-mcp"` and the fallback provider name is
///    stored in the dedicated `reviewer_fallback_provider` field (its
///    key/url/model reuse the existing `reviewer_api_key`/`reviewer_base_url`/
///    `reviewer_model` fields). This keeps "MCP primary" and "fallback provider"
///    as two distinct states so the fallback never usurps the MCP primary. With
///    no fallback, `reviewer_provider` is `"codex-mcp"`, `reviewer_fallback_provider`
///    is cleared, and the stale HTTP-reviewer fields are cleared so nothing
///    bogus is exported.
#[allow(clippy::too_many_lines)]
fn configure_codex_mcp_reviewer(config: &mut ArisConfig) -> io::Result<()> {
    println!("\n  \x1b[1mCodex MCP reviewer\x1b[0m");

    // Step 1: detect the codex CLI. v0.4.22 (Δ4-4/C6): three-state — a native
    // executable, a script shim `where` resolves but the MCP client cannot
    // spawn, or missing entirely.
    match probe_codex() {
        CodexProbe::NativeExe(_) => {
            println!("  \x1b[2m✓ found `codex` on PATH (native executable)\x1b[0m");
        }
        CodexProbe::ScriptShim(path) => {
            // Deliberately NO checkmark: the resolved candidate is a .cmd/.bat
            // script shim. ARIS's MCP client spawns `codex` as a plain command
            // (mcp_stdio.rs) and cannot spawn a script shim directly in
            // v0.4.22, so the configured server would fail to start.
            // (Making the MCP spawn shim-aware is deferred.)
            println!(
                "  \x1b[33m⚠ found `codex` only as a script shim ({}).\x1b[0m",
                path.display()
            );
            println!(
                "  \x1b[2mARIS's MCP client spawns `codex` directly and cannot launch a .cmd/.bat\x1b[0m"
            );
            println!(
                "  \x1b[2mshim in v0.4.22 — install the native `codex` binary (e.g. Homebrew or a\x1b[0m"
            );
            println!("  \x1b[2mGitHub release), then re-run setup.\x1b[0m");
            let go_on = prompt_with_default("  Write the Codex MCP config anyway? [y/N]", "n")?;
            if !go_on.trim().eq_ignore_ascii_case("y") {
                println!("  \x1b[2mSkipped Codex MCP config; reviewer unchanged.\x1b[0m");
                // Leave reviewer_provider untouched (do NOT set codex-mcp
                // without a spawnable server, which would advertise a reviewer
                // that can't run).
                return Ok(());
            }
        }
        CodexProbe::Missing => {
            println!("  \x1b[33m⚠ `codex` not found on PATH.\x1b[0m");
            println!(
                "  \x1b[2mInstall it with `npm i -g @openai/codex` (or your platform's package),\x1b[0m"
            );
            println!("  \x1b[2mthen sign in once with `codex` so the MCP server can start.\x1b[0m");
            let go_on = prompt_with_default("  Write the MCP config anyway? [Y/n]", "y")?;
            if go_on.trim().eq_ignore_ascii_case("n") {
                println!("  \x1b[2mSkipped Codex MCP config; reviewer unchanged.\x1b[0m");
                // Leave reviewer_provider untouched (do NOT set codex-mcp without a
                // server entry, which would advertise a reviewer that can't run).
                return Ok(());
            }
        }
    }

    // Step 3 (asked before the write so we know whether to set trust): trust.
    let trust_ans = prompt_with_default(
        "  Trust this server? (skip per-call approval) [Y/n]",
        "y",
    )?;
    let trust = !trust_ans.trim().eq_ignore_ascii_case("n");

    // Step 2: write into the ConfigLoader user-scope settings file.
    let claude_dir = claude_config_home();
    let settings_display = claude_dir.join("settings.json");
    let settings_display = settings_display.display();
    match merge_codex_mcp_into_settings(&claude_dir, trust) {
        Ok(true) => {
            let trust_note = if trust { " (trusted)" } else { "" };
            println!("  \x1b[2m✓ added mcpServers.codex to {settings_display}{trust_note}\x1b[0m");
        }
        Ok(false) => {
            println!(
                "  \x1b[2mmcpServers.codex already exists in {settings_display} — left unchanged.\x1b[0m"
            );
        }
        Err(e) => {
            // v0.4.17 (T10/P1.1): the settings write FAILED. If we continued
            // and set reviewer_provider="codex-mcp", the system-prompt gate +
            // LlmReview override would switch to the MCP path even though
            // mcpServers.codex never landed in settings.json — an unrecoverable
            // bad state (restart can't fix a server that isn't configured).
            // So abort the ENTIRE option-10 branch: report the error, leave the
            // previous reviewer config completely untouched, and tell the user
            // how to recover. `config` is unmodified up to here, so returning
            // now preserves their old reviewer exactly.
            println!("  \x1b[31m✗ could not write MCP config: {e}\x1b[0m");
            println!(
                "  \x1b[33mAborting Codex MCP setup; your previous reviewer config is unchanged.\x1b[0m"
            );
            println!(
                "  \x1b[2mCheck write permissions on {settings_display}, then re-run setup — \
                 or add mcpServers.codex to that file by hand.\x1b[0m"
            );
            return Ok(());
        }
    }

    // Step 4: optional API reviewer fallback.
    println!(
        "  \x1b[2mYou can also set an API reviewer as a fallback (used when Codex MCP is unavailable).\x1b[0m"
    );
    let fallback_choice_raw =
        prompt_with_default("  Optionally configure an API reviewer as fallback? [Enter=skip / 1-9]", "")?;
    let fallback_choice = fallback_choice_raw.trim();
    let fallback_info: Option<(&str, &str)> = match fallback_choice {
        "1" => Some(("openai", "gpt-5.5")),
        "2" => Some(("gemini", "gemini-2.5-pro")),
        "3" => Some(("glm", "GLM-5")),
        "4" => Some(("minimax", "MiniMax-M2.7")),
        "5" => Some(("kimi", "kimi-k2.5")),
        "6" => Some(("anthropic-compat", "claude-sonnet-4-6")),
        "7" => Some(("deepseek", "deepseek-v4-pro")),
        "9" => Some(("custom", "")),
        // "" / "8" / anything else = skip fallback (do NOT clear codex-mcp).
        _ => None,
    };

    if let Some((provider, default_model)) = fallback_info {
        // v0.4.17 (T10/P1.2): the primary reviewer STAYS Codex MCP. The fallback
        // provider name is recorded in the dedicated `reviewer_fallback_provider`
        // field (NOT `reviewer_provider`), so it never usurps the MCP primary —
        // the old design wrote the fallback straight into `reviewer_provider`,
        // which made the system-prompt gate think MCP was unselected and routed
        // every review through the fallback. The fallback's key/url/model reuse
        // the existing reviewer_api_key/base_url/model fields.
        config.reviewer_provider = Some("codex-mcp".into());
        config.reviewer_fallback_provider = Some(provider.into());
        config.reviewer_api_key = None;
        config.reviewer_base_url = None;
        config.reviewer_model = None;
        // Mirror reviewer_key_env() for the live env-set + the label; keeping
        // the label here (reviewer_key_env returns only the env var) is why this
        // small match stays local.
        let (key_env, key_label) = match provider {
            "openai" => ("OPENAI_API_KEY", "OpenAI API key"),
            "gemini" => ("GEMINI_API_KEY", "Gemini API key"),
            "glm" => ("GLM_API_KEY", "GLM API key"),
            "minimax" => ("MINIMAX_API_KEY", "MiniMax API key"),
            "kimi" => ("KIMI_API_KEY", "Kimi API key"),
            _ => ("ARIS_REVIEWER_AUTH_TOKEN", "Reviewer auth token"),
        };
        let new_key = prompt_with_default(&format!("  {key_label} [(not set)]"), "")?;
        if !new_key.is_empty() {
            config.reviewer_api_key = Some(new_key.clone());
            std::env::set_var(key_env, &new_key);
        }
        if provider == "custom" {
            let url = prompt_with_default("  Custom reviewer base URL", "")?;
            if !url.is_empty() {
                config.reviewer_base_url = Some(url);
            }
            let model = prompt_with_default("  Model name", "")?;
            config.reviewer_model = if model.is_empty() { None } else { Some(model) };
        } else {
            config.reviewer_model = Some(default_model.to_string());
        }
        println!(
            "  \x1b[2mPrimary reviewer: Codex MCP — fallback: {provider} ({})\x1b[0m",
            config.reviewer_model.as_deref().unwrap_or("(none)")
        );
    } else {
        // Pure Codex MCP: no HTTP reviewer. Clear stale fields (incl. any
        // previously-saved fallback) so apply_to_env doesn't export a leftover
        // base_url / model / fallback from a previous provider.
        config.reviewer_provider = Some("codex-mcp".into());
        config.reviewer_fallback_provider = None;
        config.reviewer_api_key = None;
        config.reviewer_base_url = None;
        config.reviewer_model = None;
    }

    Ok(())
}

/// v0.4.17 (T10): resolve the user-scope config directory the runtime
/// `ConfigLoader` reads `mcpServers` from. Mirrors `ConfigLoader::default_for`
/// exactly: honor `CLAUDE_CONFIG_HOME` if set, else `$HOME/.claude`
/// (`$USERPROFILE/.claude` on Windows), else `.claude`. This is what makes the
/// `setup` write land in the SAME file the runtime later reads (otherwise a
/// `CLAUDE_CONFIG_HOME` user would get a config written where it's never read).
pub(crate) fn claude_config_home() -> PathBuf {
    std::env::var_os("CLAUDE_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("HOME")
                .or_else(|| std::env::var_os("USERPROFILE"))
                .map(|home| PathBuf::from(home).join(".claude"))
        })
        .unwrap_or_else(|| PathBuf::from(".claude"))
}

/// v0.4.22 (Δ4-4/C6): three-state result of probing for the `codex` CLI.
///
/// The old bool `which_codex()` conflated "found a native executable" with
/// "found an npm `.cmd`/`.bat` shim" — `where` resolves the shim, but ARIS's
/// MCP client spawns `codex` as a plain command and cannot start a script
/// shim directly, so setup used to bless configs that could never run.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum CodexProbe {
    /// A native executable the MCP client can spawn directly. On Windows:
    /// the first `.exe` candidate in PATH order (even when a script shim
    /// shadows it earlier); on Unix: the `which`-resolved path.
    NativeExe(PathBuf),
    /// Only script shims resolved (`.cmd`/`.bat`/`.com`/…) — carries the
    /// first candidate in PATH order.
    ScriptShim(PathBuf),
    /// No candidates at all.
    Missing,
}

/// Pure classifier over `where`/`which` output. `windows` selects the rule set.
///
/// Lines are trimmed (CRLF-safe: `\r` is stripped too) and empty lines —
/// including leading blanks — are skipped. Unix (`windows == false`): first
/// non-empty line → `NativeExe` (byte-identical semantics to the pre-v0.4.22
/// probe), none → `Missing`. Windows (`windows == true`): ALL candidates are
/// scanned in PATH order with CASE-INSENSITIVE extension compare — the FIRST
/// `.exe` wins → `NativeExe`; candidates but no `.exe` → `ScriptShim(first)`;
/// none → `Missing`.
pub(crate) fn classify_codex_candidates(raw: &str, windows: bool) -> CodexProbe {
    let mut candidates = raw.lines().map(str::trim).filter(|line| !line.is_empty());
    if !windows {
        return match candidates.next() {
            Some(path) => CodexProbe::NativeExe(PathBuf::from(path)),
            None => CodexProbe::Missing,
        };
    }
    let candidates: Vec<&str> = candidates.collect();
    for candidate in &candidates {
        // Extension of the last path component, extracted textually so the
        // classifier stays a pure function of its input on every host (a
        // `\`-separated Windows path is one opaque component to a Unix
        // `std::path::Path`, which would mis-split dotted directory names).
        let file_name = candidate
            .rsplit(['\\', '/'])
            .next()
            .unwrap_or(candidate);
        let is_exe = file_name
            .rsplit_once('.')
            .is_some_and(|(_, ext)| ext.eq_ignore_ascii_case("exe"));
        if is_exe {
            return CodexProbe::NativeExe(PathBuf::from(*candidate));
        }
    }
    match candidates.first() {
        Some(first) => CodexProbe::ScriptShim(PathBuf::from(*first)),
        None => CodexProbe::Missing,
    }
}

/// v0.4.22 (Δ4-4/C6): probe PATH for the `codex` CLI via `where` (Windows) /
/// `which` (Unix) and classify the candidates — see [`classify_codex_candidates`].
/// Best-effort: a spawn error or non-zero exit counts as [`CodexProbe::Missing`],
/// matching the old `which_codex` status-based semantics.
pub(crate) fn probe_codex() -> CodexProbe {
    let probe = if cfg!(windows) { "where" } else { "which" };
    match std::process::Command::new(probe)
        .arg("codex")
        .stderr(std::process::Stdio::null())
        .output()
    {
        Ok(out) if out.status.success() => {
            classify_codex_candidates(&String::from_utf8_lossy(&out.stdout), cfg!(windows))
        }
        _ => CodexProbe::Missing,
    }
}

/// v0.4.17 (T10): the JSON object written for `mcpServers.codex`.
///
/// v0.4.22 (B2): the v0.4.18 server-level `-c model_reasoning_effort="xhigh"`
/// pin stays, as the xhigh FLOOR (`-c` is parsed as TOML by `codex
/// mcp-server`, so the value must be a quoted TOML string) — independent of
/// the user's `~/.codex/config.toml`, even a bare `mcp__codex__codex` call
/// that omits a per-call `config` arg reviews at xhigh. ARIS skills now
/// explicitly pin `model: gpt-5.6-sol` plus a per-call effort on every fresh
/// call (deep audits "ultra", regular review "xhigh"), and per-call `config`
/// overrides the server `-c` upward (v0.4.18-verified precedence) — so the
/// two-tier doctrine is satisfied WITHOUT a server-level model pin. Do not
/// add one: a `-c model=` pin here would hard-break codex-cli < 0.144.1
/// (which does not know gpt-5.6-sol). Only NEW setups get this entry (the
/// merge is idempotent and never clobbers an existing `mcpServers.codex`).
fn codex_mcp_server_entry(trust: bool) -> serde_json::Value {
    let mut obj = serde_json::Map::new();
    obj.insert("command".into(), serde_json::Value::String("codex".into()));
    obj.insert(
        "args".into(),
        serde_json::Value::Array(vec![
            serde_json::Value::String("mcp-server".into()),
            serde_json::Value::String("-c".into()),
            serde_json::Value::String("model_reasoning_effort=\"xhigh\"".into()),
        ]),
    );
    if trust {
        obj.insert("trust".into(), serde_json::Value::Bool(true));
    }
    serde_json::Value::Object(obj)
}

/// v0.4.17 (T10): idempotently merge `mcpServers.codex` into the user-scope
/// settings file `<home>/.claude/settings.json` — the file the runtime
/// `ConfigLoader` resolves as `ConfigSource::User` for `mcpServers` (NOT
/// `~/.claude.json`, which the doctor "Codex MCP" check reads; that path
/// mismatch is disclosed in `run_doctor`).
///
/// `claude_dir` is the resolved config home (e.g. `~/.claude` or
/// `$CLAUDE_CONFIG_HOME`) — see [`claude_config_home`]; `settings.json` lives
/// directly inside it.
///
/// Returns `Ok(true)` if it ADDED the entry, `Ok(false)` if `mcpServers.codex`
/// already existed (left untouched — never clobbered). Reuses the same
/// safety mechanism as `deploy_meta_opt_hooks_to`: read-or-`{}`, refuse to
/// clobber a malformed file, back up the existing file to
/// `settings.json.bak.<millis>`, then atomically write via tempfile + rename.
fn merge_codex_mcp_into_settings(claude_dir: &Path, trust: bool) -> Result<bool, String> {
    fs::create_dir_all(claude_dir)
        .map_err(|e| format!("create_dir_all({}): {e}", claude_dir.display()))?;
    let settings_path = claude_dir.join("settings.json");

    let (mut settings, had_existing) = match fs::read_to_string(&settings_path) {
        Ok(text) => {
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
                    ));
                }
                (parsed, true)
            }
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => (serde_json::json!({}), false),
        Err(e) => return Err(format!("read {}: {e}", settings_path.display())),
    };

    // Idempotency: never clobber an existing codex entry.
    let mcp_servers = settings
        .as_object_mut()
        .expect("settings is a JSON object (checked above / freshly created)")
        .entry("mcpServers")
        .or_insert_with(|| serde_json::Value::Object(serde_json::Map::new()));
    let Some(mcp_obj) = mcp_servers.as_object_mut() else {
        return Err(format!(
            "{}: `mcpServers` is not a JSON object",
            settings_path.display()
        ));
    };
    if mcp_obj.contains_key("codex") {
        return Ok(false);
    }
    mcp_obj.insert("codex".into(), codex_mcp_server_entry(trust));

    // Backup existing file (hard-fail if backup fails), then atomic rewrite.
    if had_existing {
        let backup_suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let backup_path = claude_dir.join(format!("settings.json.bak.{backup_suffix}"));
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
        let _ = fs::remove_file(&temp_path);
        format!(
            "atomic rename {} → {}: {e}",
            temp_path.display(),
            settings_path.display()
        )
    })?;

    Ok(true)
}

/// Print a provider-specific list of known-working third-party proxy URLs
/// before the executor URL prompt. Keeps the input-URL flow unchanged —
/// this is pure UX (helps users know what to type for OpenRouter, ModelScope,
/// etc.) and costs nothing if the user doesn't care.
///
/// Examples are restricted to URLs we've actually validated or seen reported
/// working in issues (#158, #162, etc.). Avoid listing proxies that need
/// transport-specific headers we don't implement yet (e.g. DashScope Coding
/// Plan under Anthropic — issue #159 — requires a specific header).
fn print_executor_url_hints(exec_choice: &str) {
    match exec_choice {
        "1" => {
            // Anthropic: official api.anthropic.com or an Anthropic-format proxy.
            println!(
                "  \x1b[2mProxy examples (leave blank for official api.anthropic.com):\x1b[0m"
            );
            println!("    \x1b[2m• https://code.newcli.com/claude        (Claude-Code-compatible proxy)\x1b[0m");
            println!("    \x1b[2m• https://api-inference.modelscope.cn   (ModelScope Anthropic endpoint)\x1b[0m");
        }
        "2" => {
            // OpenAI (vanilla) or OpenAI-format proxy.
            println!("  \x1b[2mProxy examples (leave blank for official api.openai.com):\x1b[0m");
            println!("    \x1b[2m• https://openrouter.ai/api/v1                        (OpenRouter)\x1b[0m");
            println!("    \x1b[2m• https://api.deepseek.com/v1                         (DeepSeek)\x1b[0m");
            println!("    \x1b[2m• https://dashscope.aliyuncs.com/compatible-mode/v1   (阿里云百练 OpenAI-compat)\x1b[0m");
        }
        "7" => {
            // DeepSeek via Anthropic-compatible API (supports extended thinking).
            println!("  \x1b[2mDeepSeek Anthropic-compatible endpoint:\x1b[0m");
            println!("    \x1b[2m• https://api.deepseek.com/anthropic                       (official)\x1b[0m");
        }
        "9" => {
            // Qwen: DashScope has both standard and Coding Plan endpoints.
            println!("  \x1b[2mProxy examples (leave blank for official DashScope):\x1b[0m");
            println!("    \x1b[2m• https://coding.dashscope.aliyuncs.com/v1               (百炼 Coding Plan)\x1b[0m");
        }
        _ => {}
    }
}

/// Print provider-specific proxy URL hints for the reviewer menu. v0.4.4
/// only covers OpenAI-format reviewer proxies; anthropic-compat reviewer
/// still sends Bearer-only (separate fix planned), so `code.newcli.com`-
/// style proxies that require x-api-key aren't listed under option 6.
fn print_reviewer_url_hints(reviewer_choice: &str) {
    match reviewer_choice {
        "1" => {
            println!("  \x1b[2mProxy examples (leave blank for official api.openai.com):\x1b[0m");
            println!("    \x1b[2m• https://openrouter.ai/api/v1                        (OpenRouter)\x1b[0m");
            println!("    \x1b[2m• https://api.deepseek.com/v1                         (DeepSeek)\x1b[0m");
            println!("    \x1b[2m• https://dashscope.aliyuncs.com/compatible-mode/v1   (阿里云百练 OpenAI-compat)\x1b[0m");
        }
        "7" => {
            println!("  \x1b[2mDeepSeek Anthropic-compatible endpoint:\x1b[0m");
            println!("    \x1b[2m• https://api.deepseek.com/anthropic                       (official)\x1b[0m");
        }
        _ => {}
    }
}

fn prompt_with_default(prompt: &str, default: &str) -> io::Result<String> {
    print!("{prompt}: ");
    io::stdout().flush()?;
    let mut input = String::new();
    io::stdin().read_line(&mut input)?;
    let trimmed = input.trim().to_string();
    if trimmed.is_empty() {
        Ok(default.to_string())
    } else {
        Ok(trimmed)
    }
}

/// v0.4.22 (Δ5-4): like [`prompt_with_default`] but distinguishes EOF from an
/// empty line — `read_line` returning 0 bytes means stdin is exhausted
/// (non-interactive run / ^D), which comes back as `Ok(None)` so a re-prompt
/// loop can abort instead of spinning forever on a closed stdin.
/// `prompt_with_default` can't express this: it maps both cases to the default.
fn prompt_line_eof_aware(prompt: &str) -> io::Result<Option<String>> {
    print!("{prompt}: ");
    io::stdout().flush()?;
    let mut input = String::new();
    if io::stdin().read_line(&mut input)? == 0 {
        return Ok(None);
    }
    Ok(Some(input.trim().to_string()))
}

/// v0.4.22 (Δ5-4): pure decision behind the wizard's executor-step gate — does
/// this (provider, model) pair still REQUIRE a model id before the wizard may
/// proceed? OpenAI/custom executors send the model id verbatim to an
/// OpenAI-compatible endpoint, so a blank (empty / whitespace-only, matching
/// `executor_model()`'s Δ-C2 trim semantics) model must be rejected at the
/// executor step. Anthropic-family providers fall back to the built-in
/// default model and never require one here.
fn executor_model_required(provider: &str, model: &str) -> bool {
    matches!(provider, "openai" | "custom") && model.trim().is_empty()
}

#[cfg(test)]
mod tests {
    use super::*;

    // Env mutation is serialized across the whole crate test binary via the
    // shared `crate::env_test_guard()` (codex Phase-0 gap #1) so config.rs and
    // openai_executor.rs env tests cannot race on EXECUTOR_*/OPENAI_API_KEY.

    struct EnvSnapshot {
        vars: Vec<(&'static str, Option<String>)>,
    }

    impl EnvSnapshot {
        fn capture(names: &[&'static str]) -> Self {
            let vars = names.iter().map(|n| (*n, std::env::var(n).ok())).collect();
            // Clear them so the test starts from a known state.
            for n in names {
                std::env::remove_var(n);
            }
            Self { vars }
        }
    }

    impl Drop for EnvSnapshot {
        fn drop(&mut self) {
            for (name, prior) in &self.vars {
                match prior {
                    Some(v) => std::env::set_var(name, v),
                    None => std::env::remove_var(name),
                }
            }
        }
    }

    const EXECUTOR_ENV_VARS: &[&str] = &[
        "EXECUTOR_PROVIDER",
        "EXECUTOR_API_KEY",
        "EXECUTOR_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
    ];

    #[test]
    fn anthropic_with_custom_base_url_sets_base_url_and_disables_betas() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("sk-ant-test".into()),
            executor_base_url: Some("https://bedrock-proxy.example.com".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ANTHROPIC_API_KEY").ok().as_deref(),
            Some("sk-ant-test")
        );
        assert_eq!(
            std::env::var("ANTHROPIC_BASE_URL").ok().as_deref(),
            Some("https://bedrock-proxy.example.com")
        );
        assert_eq!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS")
                .ok()
                .as_deref(),
            Some("1")
        );
    }

    #[test]
    fn anthropic_without_custom_base_url_leaves_betas_enabled() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("sk-ant-test".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_to_env();

        // Official api.anthropic.com path: no base URL override, betas stay on.
        assert!(std::env::var("ANTHROPIC_BASE_URL").is_err());
        assert!(std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err());
    }

    #[test]
    fn anthropic_compat_with_base_url_sets_auth_token_base_url_and_disables_betas() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic-compat".into()),
            executor_api_key: Some("mx-token".into()),
            executor_base_url: Some("https://minimax.example.com/anthropic".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ANTHROPIC_AUTH_TOKEN").ok().as_deref(),
            Some("mx-token")
        );
        assert_eq!(
            std::env::var("ANTHROPIC_BASE_URL").ok().as_deref(),
            Some("https://minimax.example.com/anthropic")
        );
        assert_eq!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS")
                .ok()
                .as_deref(),
            Some("1")
        );
    }

    #[test]
    fn force_apply_executor_env_clears_stale_beta_disable_flag() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        // Simulate a prior run that had a custom base URL and thus set the flag.
        std::env::set_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1");
        std::env::set_var("ANTHROPIC_BASE_URL", "https://old-proxy.example.com");

        // User then reconfigured to official api.anthropic.com (no base URL).
        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("sk-ant-test".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_executor_env();

        // Stale flags from the prior custom-URL run must be gone, otherwise
        // the Anthropic client would keep stripping beta headers against the
        // official API and we'd lose OAuth/long-context/interleaved-thinking.
        assert!(
            std::env::var("ANTHROPIC_BASE_URL").is_err(),
            "expected ANTHROPIC_BASE_URL to be cleared by force_apply_executor_env"
        );
        assert!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err(),
            "expected CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS to be cleared too"
        );
    }

    // ─────────────────────────────────────────────────────────────────────
    // v0.4.16 Phase 0 — CHARACTERIZATION (golden master) tests.
    //
    // These lock the CURRENT behavior of `apply_to_env_inner` before the
    // P7 ProviderFamily refactor. They are NOT specifications of what the
    // code SHOULD do — they pin what it ACTUALLY does today so any
    // behavior change during the refactor is caught immediately. If one of
    // these fails after a refactor, that is a REGRESSION, not a stale
    // assertion: the env-writing contract these providers rely on changed.
    //
    // Env isolation: every test below takes crate::env_test_guard() + EnvSnapshot::capture
    // (save/clear/restore) exactly like the pre-existing tests above.
    // `apply_to_env_inner` reads only `&self` + process env (never disk),
    // so no HOME/config-file isolation is needed.
    // ─────────────────────────────────────────────────────────────────────

    /// case: exec_anthropic_official_endpoint
    /// Locks: executor_provider="anthropic" + base_url=None (official
    /// api.anthropic.com path). The highest-priority Category-A invariant —
    /// ANTHROPIC_API_KEY (x-api-key auth) is set, NO base URL override is
    /// written, betas stay ON (CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS unset),
    /// and EXECUTOR_PROVIDER is NOT set (so resolve_openai_executor_config
    /// returns None → Anthropic client path).
    #[test]
    fn char_exec_anthropic_official_endpoint() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ANTHROPIC_API_KEY").ok().as_deref(),
            Some("K")
        );
        // Official endpoint: no base URL, no beta-disable, betas remain ON.
        assert!(std::env::var("ANTHROPIC_BASE_URL").is_err());
        assert!(std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err());
        // anthropic path never sets EXECUTOR_PROVIDER → OpenAI resolver = None.
        assert!(std::env::var("EXECUTOR_PROVIDER").is_err());
        // anthropic path never sets ANTHROPIC_AUTH_TOKEN (that's the
        // anthropic-compat Bearer path).
        assert!(std::env::var("ANTHROPIC_AUTH_TOKEN").is_err());
    }

    /// case: exec_anthropic_custom_url_keeps_xapikey  🔴 HIGHEST-PRIORITY GUARD
    /// Locks the #158/#162 regression: executor_provider="anthropic" with a
    /// CUSTOM base_url must keep x-api-key auth (ANTHROPIC_API_KEY), and must
    /// NOT silently switch to the anthropic-compat Bearer path
    /// (ANTHROPIC_AUTH_TOKEN). Anthropic-format proxies (code.newcli.com/claude,
    /// modelscope) accept x-api-key, NOT `Authorization: Bearer`. Custom URL
    /// DOES set ANTHROPIC_BASE_URL and disables betas (third-party may reject
    /// Anthropic beta flags). This is the single most refactor-fragile route.
    #[test]
    fn char_exec_anthropic_custom_url_keeps_xapikey() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: Some("https://code.newcli.com/claude".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        // x-api-key auth preserved — the load-bearing assertion.
        assert_eq!(
            std::env::var("ANTHROPIC_API_KEY").ok().as_deref(),
            Some("K")
        );
        // Must NOT have flipped to Bearer (anthropic-compat) auth.
        assert!(
            std::env::var("ANTHROPIC_AUTH_TOKEN").is_err(),
            "#158/#162 regression: anthropic+custom URL must NOT set ANTHROPIC_AUTH_TOKEN"
        );
        assert_eq!(
            std::env::var("ANTHROPIC_BASE_URL").ok().as_deref(),
            Some("https://code.newcli.com/claude")
        );
        assert_eq!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS")
                .ok()
                .as_deref(),
            Some("1")
        );
        // Still Anthropic-client routed (no OpenAI EXECUTOR_PROVIDER).
        assert!(std::env::var("EXECUTOR_PROVIDER").is_err());
    }

    /// case: exec_anthropic_compat_bearer
    /// Locks the Bearer path: executor_provider="anthropic-compat" sets
    /// ANTHROPIC_AUTH_TOKEN (Bearer) — NOT ANTHROPIC_API_KEY (x-api-key) —
    /// plus base URL + beta-disable. This is the other side of the
    /// x-api-key vs Bearer bisection that #158/#162 turns on.
    #[test]
    fn char_exec_anthropic_compat_bearer() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic-compat".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: Some("https://api.deepseek.com/anthropic".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        // Bearer token, NOT x-api-key.
        assert_eq!(
            std::env::var("ANTHROPIC_AUTH_TOKEN").ok().as_deref(),
            Some("K")
        );
        assert!(
            std::env::var("ANTHROPIC_API_KEY").is_err(),
            "anthropic-compat must NOT set ANTHROPIC_API_KEY (x-api-key)"
        );
        assert_eq!(
            std::env::var("ANTHROPIC_BASE_URL").ok().as_deref(),
            Some("https://api.deepseek.com/anthropic")
        );
        assert_eq!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS")
                .ok()
                .as_deref(),
            Some("1")
        );
        assert!(std::env::var("EXECUTOR_PROVIDER").is_err());
    }

    /// case: exec_anthropic_compat_no_baseurl_edge
    /// Locks the corner where anthropic-compat has base_url=None: both the
    /// ANTHROPIC_BASE_URL set AND the beta-disable are gated inside
    /// `if let Some(url)`, so with no URL the token is still set (Bearer) but
    /// betas stay ON and no base URL is written. Mirrors the official-edge
    /// behavior but on the Bearer side.
    #[test]
    fn char_exec_anthropic_compat_no_baseurl_edge() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("anthropic-compat".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ANTHROPIC_AUTH_TOKEN").ok().as_deref(),
            Some("K")
        );
        // base_url=None → both gated effects skipped.
        assert!(std::env::var("ANTHROPIC_BASE_URL").is_err());
        assert!(
            std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err(),
            "betas-disable is gated on Some(url); with None it must stay unset"
        );
    }

    /// case: exec_openai_family
    /// Locks the OpenAI executor path: provider="openai" sets
    /// EXECUTOR_PROVIDER=openai + EXECUTOR_API_KEY + EXECUTOR_BASE_URL, and
    /// writes NO ANTHROPIC_* vars. EXECUTOR_PROVIDER=openai is the exact-match
    /// gate that makes resolve_openai_executor_config return Some.
    #[test]
    fn char_exec_openai_family() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("openai".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: Some("https://api.openai.com/v1".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_PROVIDER").ok().as_deref(),
            Some("openai")
        );
        assert_eq!(std::env::var("EXECUTOR_API_KEY").ok().as_deref(), Some("K"));
        assert_eq!(
            std::env::var("EXECUTOR_BASE_URL").ok().as_deref(),
            Some("https://api.openai.com/v1")
        );
        // OpenAI path writes no Anthropic vars.
        assert!(std::env::var("ANTHROPIC_API_KEY").is_err());
        assert!(std::env::var("ANTHROPIC_AUTH_TOKEN").is_err());
        assert!(std::env::var("ANTHROPIC_BASE_URL").is_err());
    }

    /// case: exec_custom_maps_to_openai
    /// Locks the custom→openai collapse: provider="custom" is
    /// runtime-indistinguishable from "openai" — it sets EXECUTOR_PROVIDER
    /// to the literal "openai" (NOT "custom") plus EXECUTOR_API_KEY +
    /// EXECUTOR_BASE_URL. (config.json keeps "custom" only for the setup
    /// menu echo; at the env layer it is openai.)
    #[test]
    fn char_exec_custom_maps_to_openai() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        let config = ArisConfig {
            executor_provider: Some("custom".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: Some("https://proxy.example.com/v1".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_PROVIDER").ok().as_deref(),
            Some("openai"),
            "custom must collapse to literal openai at the env layer"
        );
        assert_eq!(std::env::var("EXECUTOR_API_KEY").ok().as_deref(), Some("K"));
        assert_eq!(
            std::env::var("EXECUTOR_BASE_URL").ok().as_deref(),
            Some("https://proxy.example.com/v1")
        );
        assert!(std::env::var("ANTHROPIC_API_KEY").is_err());
        assert!(std::env::var("ANTHROPIC_AUTH_TOKEN").is_err());
    }

    /// case: force_clears_stale_beta_flag
    /// Companion to the pre-existing force_apply_executor_env test, but via
    /// ForceAll (force_apply_to_env). Locks that a prior run's stale
    /// ANTHROPIC_BASE_URL + beta-disable flag are removed first, so the
    /// official endpoint (base_url=None) runs with betas ON.
    #[test]
    fn char_force_clears_stale_beta_flag_forceall() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        std::env::set_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1");
        std::env::set_var("ANTHROPIC_BASE_URL", "https://old-proxy.example.com");

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("K".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_to_env();

        assert!(std::env::var("ANTHROPIC_BASE_URL").is_err());
        assert!(std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err());
        assert_eq!(
            std::env::var("ANTHROPIC_API_KEY").ok().as_deref(),
            Some("K")
        );
    }

    /// case: force_executor_only_preserves_reviewer_keys
    /// Locks the executor/reviewer env isolation under ForceExecutorOnly
    /// (force_apply_executor_env): a shell-provided OPENAI_API_KEY (the
    /// reviewer key) must NOT be cleared when the user re-applies only the
    /// executor auth. force_rev is false in this mode, so the reviewer-clear
    /// block is skipped.
    #[test]
    fn char_force_executor_only_preserves_reviewer_keys() {
        let _g = crate::env_test_guard();
        // Capture executor vars AND OPENAI_API_KEY so we restore both.
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);
        let _rev_snap = EnvSnapshot::capture(&["OPENAI_API_KEY"]);

        // Reviewer key supplied by the user's shell.
        std::env::set_var("OPENAI_API_KEY", "reviewer-key");

        let config = ArisConfig {
            executor_provider: Some("anthropic".into()),
            executor_api_key: Some("exec-key".into()),
            executor_base_url: None,
            ..Default::default()
        };
        config.force_apply_executor_env();

        // Executor auth applied …
        assert_eq!(
            std::env::var("ANTHROPIC_API_KEY").ok().as_deref(),
            Some("exec-key")
        );
        // … but the reviewer key survives (ForceExecutorOnly leaves it alone).
        assert_eq!(
            std::env::var("OPENAI_API_KEY").ok().as_deref(),
            Some("reviewer-key"),
            "ForceExecutorOnly must not clobber shell-provided reviewer OPENAI_API_KEY"
        );
    }

    /// case: exec_openai_api_key_fallback (config-layer half)
    /// Locks that the openai-provider env-writing uses EXECUTOR_API_KEY (the
    /// resolver's OPENAI_API_KEY fallback is tested in openai_executor.rs).
    /// Here we pin: a force-apply with provider=openai writes the key to
    /// EXECUTOR_API_KEY, and an IfMissing apply with EXECUTOR_API_KEY already
    /// set leaves the shell value untouched (shell wins).
    #[test]
    fn char_exec_openai_ifmissing_shell_wins() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        // Shell already provided EXECUTOR_PROVIDER + key.
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        std::env::set_var("EXECUTOR_API_KEY", "shell-key");

        let config = ArisConfig {
            executor_provider: Some("openai".into()),
            executor_api_key: Some("config-key".into()),
            executor_base_url: Some("https://api.openai.com/v1".into()),
            ..Default::default()
        };
        // IfMissing mode: shell-provided vars win, config does not overwrite.
        config.apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_API_KEY").ok().as_deref(),
            Some("shell-key"),
            "IfMissing must not overwrite a shell-provided EXECUTOR_API_KEY"
        );
        // base_url was unset in the shell, so IfMissing fills it from config.
        assert_eq!(
            std::env::var("EXECUTOR_BASE_URL").ok().as_deref(),
            Some("https://api.openai.com/v1")
        );
    }

    /// case: ifmissing_shell_executor_provider_wins  🔴 v0.4.21 #2 BUG-FIX GUARD
    /// A saved openai/custom config must NOT clobber a shell-provided
    /// EXECUTOR_PROVIDER under IfMissing (the apply_to_env / startup path).
    /// Before the fix the provider write was unconditional, so
    /// `EXECUTOR_PROVIDER=anthropic aris …` with a saved OpenAI config got
    /// silently re-pointed to OpenAI → wrong executor / model-not-found. The
    /// gate now mirrors every sibling field: the shell value wins.
    #[test]
    fn char_ifmissing_shell_executor_provider_wins() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        // Shell explicitly selects the Anthropic executor.
        std::env::set_var("EXECUTOR_PROVIDER", "anthropic");

        let config = ArisConfig {
            executor_provider: Some("openai".into()),
            executor_api_key: Some("config-key".into()),
            executor_base_url: Some("https://api.openai.com/v1".into()),
            ..Default::default()
        };
        // IfMissing mode: the shell-provided EXECUTOR_PROVIDER must survive.
        config.apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_PROVIDER").ok().as_deref(),
            Some("anthropic"),
            "IfMissing must not let a saved openai config clobber a shell-set EXECUTOR_PROVIDER"
        );
    }

    /// case: ifmissing_unset_executor_provider_takes_config
    /// v0.4.21 #2 companion: with NO shell EXECUTOR_PROVIDER, IfMissing still
    /// applies the saved openai/custom provider (the gate's `is_err()` branch),
    /// so config-only setups are unaffected by the fix.
    #[test]
    fn char_ifmissing_unset_executor_provider_takes_config() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        // EnvSnapshot::capture cleared EXECUTOR_PROVIDER → it is unset here.
        assert!(std::env::var("EXECUTOR_PROVIDER").is_err());

        let config = ArisConfig {
            executor_provider: Some("openai".into()),
            executor_api_key: Some("config-key".into()),
            executor_base_url: Some("https://api.openai.com/v1".into()),
            ..Default::default()
        };
        config.apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_PROVIDER").ok().as_deref(),
            Some("openai"),
            "IfMissing must fill EXECUTOR_PROVIDER from saved config when the shell left it unset"
        );
    }

    /// case: force_executor_provider_applies_over_shell
    /// v0.4.21 #2 companion: force_apply_to_env (ForceAll) remove_var's
    /// EXECUTOR_PROVIDER first, so the `force` arm of the gate still applies the
    /// saved openai value even though the shell had set anthropic. Locks that
    /// the explicit /setup path is UNCHANGED by the fix.
    #[test]
    fn char_force_executor_provider_applies_over_shell() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(EXECUTOR_ENV_VARS);

        // Even a shell-set value is overridden by an explicit force-apply.
        std::env::set_var("EXECUTOR_PROVIDER", "anthropic");

        let config = ArisConfig {
            executor_provider: Some("openai".into()),
            executor_api_key: Some("config-key".into()),
            executor_base_url: Some("https://api.openai.com/v1".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("EXECUTOR_PROVIDER").ok().as_deref(),
            Some("openai"),
            "force_apply_to_env must still apply the saved openai provider (unchanged force behavior)"
        );
    }

    // ── setup_menu echo / exec_info mirror tests ──────────────────────────
    //
    // The setup wizard's `exec_info` tuple table and the `default_executor`
    // menu-echo `match` live INLINE inside `run_interactive_setup`, which is
    // interactive (reads stdin). They cannot be unit-tested directly without
    // refactoring production code (out of scope for a characterization
    // agent). The truly load-bearing thing for zero-regression is the RUNTIME
    // env each menu choice produces — so the round-trip tests above already
    // lock the openai/anthropic-compat env contracts those menus map to.
    //
    // The mirror helpers below replicate the production `default_executor`
    // echo `match` VERBATIM so the menu→number routing is pinned. NOTE: these
    // are mirror assertions, not auto-drift detectors — if production changes
    // the table, a reviewer diffing the two catches it; the test itself only
    // fails if the COPIED logic here is edited. They document current echo
    // behavior (DISCREPANCY-aware, see report).

    /// Replica of the production `default_executor` echo match
    /// (config.rs run_interactive_setup, copied verbatim 2026-05-30).
    fn echo_default_executor(provider: Option<&str>, base_url: Option<&str>) -> &'static str {
        match provider {
            Some("anthropic") => "1",
            Some("anthropic-compat") => match base_url {
                Some(u) if u.contains("deepseek") => "7",
                _ => "1",
            },
            Some("custom") => "11",
            Some("openai") => match base_url {
                Some(u) if u.contains("googleapis") => "3",
                Some(u) if u.contains("bigmodel") => "4",
                Some(u) if u.contains("minimax") => "5",
                Some(u) if u.contains("moonshot") => "6",
                Some(u) if u.contains("xiaomimimo") => "8",
                Some(u) if u.contains("dashscope") => "9",
                Some(u) if u.contains("volces") => "10",
                _ => "2",
            },
            _ => "1",
        }
    }

    /// case: setup_menu_3_gemini / 4_glm / 5_minimax / 6_kimi / 7_deepseek /
    /// 8_9_10_echo / 2_or_unknown_proxy_echo — all in one table-driven test.
    /// Locks the executor menu-echo routing (provider + base_url substring →
    /// menu number). Pins each provider's substring keyword and that
    /// anthropic-compat+deepseek echoes "7" while anthropic-compat without a
    /// deepseek URL falls back to "1".
    #[test]
    fn char_setup_menu_default_executor_echo() {
        // (provider, base_url, expected_menu_number)
        let cases: &[(Option<&str>, Option<&str>, &str)] = &[
            // setup_menu_3_gemini: googleapis → "3"
            (
                Some("openai"),
                Some("https://generativelanguage.googleapis.com/v1beta/openai"),
                "3",
            ),
            // setup_menu_4_glm: bigmodel → "4"
            (
                Some("openai"),
                Some("https://open.bigmodel.cn/api/paas/v4"),
                "4",
            ),
            // setup_menu_5_minimax_openai: minimax → "5"
            (Some("openai"), Some("https://api.minimax.chat/v1"), "5"),
            // setup_menu_6_kimi: moonshot → "6"
            (Some("openai"), Some("https://api.moonshot.cn/v1"), "6"),
            // setup_menu_8_9_10_echo: xiaomimimo/dashscope/volces → 8/9/10
            (
                Some("openai"),
                Some("https://token-plan-cn.xiaomimimo.com/v1"),
                "8",
            ),
            (
                Some("openai"),
                Some("https://dashscope.aliyuncs.com/compatible-mode/v1"),
                "9",
            ),
            (
                Some("openai"),
                Some("https://ark.cn-beijing.volces.com/api/v3"),
                "10",
            ),
            // setup_menu_7_deepseek_compat: anthropic-compat + deepseek → "7"
            (
                Some("anthropic-compat"),
                Some("https://api.deepseek.com/anthropic"),
                "7",
            ),
            // anthropic-compat WITHOUT a deepseek URL → falls back to "1".
            (
                Some("anthropic-compat"),
                Some("https://other-compat.example.com/anthropic"),
                "1",
            ),
            // setup_menu_2_or_unknown_proxy_echo: openai + unmatched URL → "2"
            (
                Some("openai"),
                Some("https://my-custom-openai-proxy.example.com/v1"),
                "2",
            ),
            // openai + no URL → "2"
            (Some("openai"), None, "2"),
            // anthropic → "1"; custom → "11"; unknown/None → "1"
            (Some("anthropic"), None, "1"),
            (
                Some("anthropic"),
                Some("https://code.newcli.com/claude"),
                "1",
            ),
            (Some("custom"), None, "11"),
            (None, None, "1"),
        ];
        for (provider, base_url, expected) in cases {
            assert_eq!(
                echo_default_executor(*provider, *base_url),
                *expected,
                "echo mismatch for provider={provider:?} base_url={base_url:?}"
            );
        }
    }

    // ── v0.4.17 (T10): Codex MCP reviewer setup integration ──────────────────

    fn codex_mcp_test_root() -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time after epoch")
            .as_nanos();
        let pid = std::process::id();
        std::env::temp_dir().join(format!("aris-codex-mcp-test-{pid}-{nanos}"))
    }

    // v0.4.18 (#259): diagnose_misconfig must (a) stay silent on a clean
    // first-run and a valid config, (b) flag a malformed config at the right
    // path, and (c) flag a misplaced/wrong-format stray when the real config is
    // absent. v0.4.22 (C7/Δ-C7): return type is now Vec<ConfigDiagnostic>;
    // (b) and (c) are Problems (doctor flips all_ok). Filesystem-only (passes
    // an explicit home) so it never touches the process $HOME and is
    // parallel-safe.
    #[test]
    fn diagnose_misconfig_detects_malformed_and_misplaced() {
        let home = codex_mcp_test_root();
        let home_str = home.to_str().expect("utf8 path");
        let cfg_dir = home.join(".config/aris");
        let cfg = cfg_dir.join("config.json");

        // (a) nothing anywhere → first-run, no nag.
        assert!(ArisConfig::diagnose_misconfig_in(home_str).is_empty());

        // (a) valid flat-JSON config → fine.
        fs::create_dir_all(&cfg_dir).expect("mkdir");
        fs::write(&cfg, r#"{"language":"en"}"#).expect("write valid");
        assert!(ArisConfig::diagnose_misconfig_in(home_str).is_empty());

        // (b) malformed config AT the right path (e.g. YAML pasted into the
        // .json file) → parse-failure Problem pointing at `aris setup`.
        fs::write(&cfg, "executor:\n  provider: anthropic\n").expect("write malformed");
        let diags = ArisConfig::diagnose_misconfig_in(home_str);
        assert_eq!(diags.len(), 1, "malformed => exactly one diagnostic");
        let ConfigDiagnostic::Problem(hint) = &diags[0] else {
            panic!("malformed config must be a Problem, got: {:?}", diags[0]);
        };
        assert!(
            hint.contains("could not parse") && hint.contains("aris setup"),
            "malformed hint wrong: {hint}"
        );

        // (c) real config absent + a misplaced YAML stray → misplaced Problem.
        fs::remove_file(&cfg).expect("rm");
        let stray = home.join(".aris/config.yaml");
        fs::create_dir_all(stray.parent().unwrap()).expect("mkdir stray");
        fs::write(&stray, "executor:\n  provider: anthropic\n").expect("write stray");
        let diags = ArisConfig::diagnose_misconfig_in(home_str);
        assert_eq!(diags.len(), 1, "misplaced => exactly one diagnostic");
        let ConfigDiagnostic::Problem(hint) = &diags[0] else {
            panic!("misplaced stray must be a Problem, got: {:?}", diags[0]);
        };
        assert!(
            hint.contains("config.yaml") && hint.contains("flat JSON"),
            "misplaced hint wrong: {hint}"
        );

        let _ = fs::remove_dir_all(&home);
    }

    /// v0.4.22 (C7/Δ-C7): KNOWN_CONFIG_KEYS must stay in sync with the serde
    /// field names of ArisConfig. Serializing the default config yields every
    /// field as a top-level key (all fields are plain `Option`s, no
    /// `skip_serializing_if`), so the two sets must be EQUAL — a new struct
    /// field without a matching const entry (or vice versa) fails here.
    #[test]
    fn known_config_keys_match_aris_config_fields() {
        let value = serde_json::to_value(ArisConfig::default()).expect("serialize default");
        let obj = value.as_object().expect("ArisConfig serializes to an object");
        let mut struct_keys: Vec<&str> = obj.keys().map(String::as_str).collect();
        struct_keys.sort_unstable();
        let mut const_keys: Vec<&str> = KNOWN_CONFIG_KEYS.to_vec();
        const_keys.sort_unstable();
        assert_eq!(
            struct_keys, const_keys,
            "KNOWN_CONFIG_KEYS is out of sync with ArisConfig's serde fields"
        );
    }

    /// v0.4.22 (C7/Δ-C7): a NESTED config (`{"executor": {...}}`) parses fine
    /// as the typed struct (serde ignores unknown fields) but every setting in
    /// it is silently ignored — diagnose must return exactly ONE Warning (not
    /// a Problem: doctor must not flip all_ok) naming the unknown key.
    #[test]
    fn diagnose_misconfig_nested_executor_object_warns() {
        let home = codex_mcp_test_root();
        let home_str = home.to_str().expect("utf8 path");
        let cfg_dir = home.join(".config/aris");
        fs::create_dir_all(&cfg_dir).expect("mkdir");
        fs::write(
            cfg_dir.join("config.json"),
            r#"{"executor": {"provider": "openai", "model": "gpt-5.5"}}"#,
        )
        .expect("write nested");

        let diags = ArisConfig::diagnose_misconfig_in(home_str);
        assert_eq!(diags.len(), 1, "nested config => exactly one diagnostic");
        let ConfigDiagnostic::Warning(msg) = &diags[0] else {
            panic!("nested config must be a Warning, got: {:?}", diags[0]);
        };
        assert!(
            msg.contains("unrecognized top-level keys") && msg.contains("executor"),
            "nested-config warning wrong: {msg}"
        );
        assert!(
            msg.contains("flat top-level keys"),
            "warning must explain ARIS expects flat keys: {msg}"
        );

        let _ = fs::remove_dir_all(&home);
    }

    /// v0.4.22 (C7/Δ-C7): a single unknown top-level key next to valid known
    /// keys → one Warning naming it; the known keys are not listed.
    #[test]
    fn diagnose_misconfig_single_unknown_key_warns() {
        let home = codex_mcp_test_root();
        let home_str = home.to_str().expect("utf8 path");
        let cfg_dir = home.join(".config/aris");
        fs::create_dir_all(&cfg_dir).expect("mkdir");
        fs::write(
            cfg_dir.join("config.json"),
            r#"{"language": "en", "executor_modle": "gpt-5.5"}"#,
        )
        .expect("write typo config");

        let diags = ArisConfig::diagnose_misconfig_in(home_str);
        assert_eq!(diags.len(), 1, "one unknown key => exactly one diagnostic");
        let ConfigDiagnostic::Warning(msg) = &diags[0] else {
            panic!("unknown key must be a Warning, got: {:?}", diags[0]);
        };
        assert!(
            msg.contains("executor_modle"),
            "warning must name the unknown key: {msg}"
        );
        assert!(
            !msg.contains("language"),
            "known keys must not be listed as unrecognized: {msg}"
        );

        let _ = fs::remove_dir_all(&home);
    }

    /// v0.4.22 (C7/Δ-C7): unknown-key list display discipline — sorted, at
    /// most 5 keys shown then "… and N more", control chars stripped, each
    /// key capped at 40 chars, total message capped at ~300 chars.
    #[test]
    fn diagnose_misconfig_unknown_key_list_sorted_capped_sanitized() {
        let home = codex_mcp_test_root();
        let home_str = home.to_str().expect("utf8 path");
        let cfg_dir = home.join(".config/aris");
        fs::create_dir_all(&cfg_dir).expect("mkdir");
        // 7 unknown keys, inserted out of order; one carries a control char,
        // one is 60 chars long. serde_json's BTreeMap already sorts, but the
        // message contract is sorted regardless of map backend.
        let long_key = "a".repeat(60);
        fs::write(
            cfg_dir.join("config.json"),
            format!(
                r#"{{"zeta": 1, "beta": 1, "delta": 1, "epsilon": 1, "gamma": 1, "e\u0007vil": 1, "{long_key}": 1}}"#
            ),
        )
        .expect("write many unknown keys");

        let diags = ArisConfig::diagnose_misconfig_in(home_str);
        assert_eq!(diags.len(), 1, "many unknown keys => ONE Warning, not many");
        let ConfigDiagnostic::Warning(msg) = &diags[0] else {
            panic!("unknown keys must be a Warning, got: {:?}", diags[0]);
        };
        // Cap: 7 unknown → 5 shown + "… and 2 more".
        assert!(msg.contains("… and 2 more"), "count tail missing: {msg}");
        // Sorted: the 60×'a' key sorts first; capped to 40 chars.
        assert!(
            msg.contains(&"a".repeat(40)),
            "long key must appear (40-char capped): {msg}"
        );
        assert!(
            !msg.contains(&"a".repeat(41)),
            "long key must be capped at 40 chars: {msg}"
        );
        // Control char stripped from "e\u{7}vil".
        assert!(msg.contains("evil"), "sanitized key missing: {msg}");
        assert!(!msg.contains('\u{7}'), "control char must be stripped: {msg}");
        // "zeta" sorts last of the 7 → beyond the 5 shown.
        assert!(!msg.contains("zeta"), "keys beyond the first 5 must be elided: {msg}");
        // Total message cap.
        assert!(
            msg.chars().count() <= 300,
            "message must be capped at ~300 chars, got {}: {msg}",
            msg.chars().count()
        );

        let _ = fs::remove_dir_all(&home);
    }

    /// default_reviewer_choice must round-trip the saved provider back to the
    /// matching menu number — most importantly `codex-mcp -> "10"` so the next
    /// `setup` defaults to the Codex MCP reviewer instead of drifting to Skip.
    #[test]
    fn default_reviewer_choice_round_trips_codex_mcp_to_10() {
        assert_eq!(default_reviewer_choice(Some("codex-mcp")), "10");
        // The pre-existing providers keep their numbers (no reorder).
        assert_eq!(default_reviewer_choice(Some("openai")), "1");
        assert_eq!(default_reviewer_choice(Some("deepseek")), "7");
        assert_eq!(default_reviewer_choice(Some("custom")), "9");
        assert_eq!(default_reviewer_choice(None), "1");
        // Unknown / "skip" provider falls back to Skip (8), not to codex-mcp.
        assert_eq!(default_reviewer_choice(Some("something-else")), "8");
    }

    #[test]
    fn codex_mcp_server_entry_has_command_args_and_optional_trust() {
        let trusted = codex_mcp_server_entry(true);
        assert_eq!(trusted["command"], "codex");
        // v0.4.18: args pin xhigh reasoning on the spawned server.
        assert_eq!(
            trusted["args"],
            serde_json::json!(["mcp-server", "-c", "model_reasoning_effort=\"xhigh\""])
        );
        assert_eq!(trusted["trust"], serde_json::json!(true));

        let untrusted = codex_mcp_server_entry(false);
        // Absent (not false) — matches the "absent => untrusted" parser default.
        assert!(untrusted.get("trust").is_none());
    }

    /// Fresh write: no settings.json yet → creates it with mcpServers.codex,
    /// returns true (added), writes trust:true, and leaves no backup (nothing
    /// to back up).
    #[test]
    fn merge_codex_mcp_creates_settings_when_absent() {
        let root = codex_mcp_test_root();
        let home = root.join("home");
        let claude_dir = home.join(".claude");
        let added = merge_codex_mcp_into_settings(&claude_dir, true).expect("write should succeed");
        assert!(added, "first write must report it ADDED the entry");

        let settings_path = claude_dir.join("settings.json");
        let body = fs::read_to_string(&settings_path).expect("settings written");
        let parsed: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
        assert_eq!(parsed["mcpServers"]["codex"]["command"], "codex");
        assert_eq!(
            parsed["mcpServers"]["codex"]["args"],
            serde_json::json!(["mcp-server", "-c", "model_reasoning_effort=\"xhigh\""])
        );
        assert_eq!(parsed["mcpServers"]["codex"]["trust"], serde_json::json!(true));

        // No backups created when there was no prior file.
        let backups: Vec<_> = fs::read_dir(&claude_dir)
            .expect("read .claude dir")
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().contains("settings.json.bak."))
            .collect();
        assert!(backups.is_empty(), "no backup expected on fresh write");

        let _ = fs::remove_dir_all(&root);
    }

    /// Idempotent: a second call with an existing mcpServers.codex must NOT
    /// clobber it and must report `false` (not added).
    #[test]
    fn merge_codex_mcp_is_idempotent_and_never_clobbers() {
        let root = codex_mcp_test_root();
        let home = root.join("home");
        let claude_dir = home.join(".claude");
        // First: add it untrusted.
        assert!(merge_codex_mcp_into_settings(&claude_dir, false).expect("first add"));
        // Second: try to add trusted — must be a no-op (existing entry kept).
        let added = merge_codex_mcp_into_settings(&claude_dir, true).expect("second call");
        assert!(!added, "second call must report it did NOT add (already exists)");

        let settings_path = claude_dir.join("settings.json");
        let parsed: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&settings_path).expect("read")).expect("json");
        // Still the ORIGINAL untrusted entry (no trust flag) — not clobbered.
        assert!(
            parsed["mcpServers"]["codex"].get("trust").is_none(),
            "existing entry must not be overwritten with trust:true"
        );

        // The no-op second call returns early (before any write), so it makes
        // NO backup — idempotency means zero side effects on disk.
        let had_backup = fs::read_dir(&claude_dir)
            .expect("read dir")
            .filter_map(|e| e.ok())
            .any(|e| e.file_name().to_string_lossy().contains("settings.json.bak."));
        assert!(
            !had_backup,
            "a no-op (already-exists) call must not write a backup"
        );

        let _ = fs::remove_dir_all(&root);
    }

    /// Existing unrelated settings + another MCP server are PRESERVED when we
    /// merge codex in, and a backup is written.
    #[test]
    fn merge_codex_mcp_preserves_existing_settings_and_backs_up() {
        let root = codex_mcp_test_root();
        let home = root.join("home");
        let claude_dir = home.join(".claude");
        fs::create_dir_all(&claude_dir).expect("mkdir .claude");
        let existing = serde_json::json!({
            "language": "cn",
            "mcpServers": { "other": { "command": "foo", "args": ["bar"] } }
        });
        let settings_path = claude_dir.join("settings.json");
        fs::write(
            &settings_path,
            format!("{}\n", serde_json::to_string_pretty(&existing).unwrap()),
        )
        .expect("seed settings");

        let added = merge_codex_mcp_into_settings(&claude_dir, true).expect("merge");
        assert!(added);

        let parsed: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&settings_path).expect("read")).expect("json");
        // Unrelated keys preserved.
        assert_eq!(parsed["language"], "cn");
        // Sibling MCP server preserved.
        assert_eq!(parsed["mcpServers"]["other"]["command"], "foo");
        // Codex added.
        assert_eq!(parsed["mcpServers"]["codex"]["command"], "codex");

        // Backup of the prior file exists and parses to the ORIGINAL content.
        let backup = fs::read_dir(&claude_dir)
            .expect("read dir")
            .filter_map(|e| e.ok())
            .find(|e| e.file_name().to_string_lossy().contains("settings.json.bak."))
            .expect("a backup file");
        let backup_body = fs::read_to_string(backup.path()).expect("read backup");
        let backup_parsed: serde_json::Value =
            serde_json::from_str(&backup_body).expect("backup json");
        assert!(
            backup_parsed["mcpServers"].get("codex").is_none(),
            "backup must be the pre-merge content (no codex yet)"
        );

        let _ = fs::remove_dir_all(&root);
    }

    /// A malformed settings.json must be REFUSED (never clobbered).
    #[test]
    fn merge_codex_mcp_refuses_malformed_settings() {
        let root = codex_mcp_test_root();
        let home = root.join("home");
        let claude_dir = home.join(".claude");
        fs::create_dir_all(&claude_dir).expect("mkdir");
        let settings_path = claude_dir.join("settings.json");
        fs::write(&settings_path, "{ this is : not json").expect("seed garbage");

        let err = merge_codex_mcp_into_settings(&claude_dir, true)
            .expect_err("malformed settings must be rejected");
        assert!(
            err.contains("refusing to clobber"),
            "error should explain it refused to clobber: {err}"
        );
        // Original garbage untouched.
        assert_eq!(
            fs::read_to_string(&settings_path).expect("read"),
            "{ this is : not json"
        );

        let _ = fs::remove_dir_all(&root);
    }

    /// apply_to_env with reviewer_provider="codex-mcp" and NO api key must set
    /// ARIS_REVIEWER_PROVIDER="codex-mcp" and must NOT write any provider API
    /// key env var (codex-mcp has no HTTP credentials).
    #[test]
    fn apply_to_env_codex_mcp_sets_provider_and_writes_no_api_key() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(&[
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_BASE_URL",
            "ARIS_REVIEWER_MODEL",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ]);

        let config = ArisConfig {
            reviewer_provider: Some("codex-mcp".into()),
            reviewer_api_key: None,
            reviewer_base_url: None,
            reviewer_model: None,
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_PROVIDER").ok().as_deref(),
            Some("codex-mcp")
        );
        // No provider key / auth token written.
        assert!(std::env::var("OPENAI_API_KEY").is_err());
        assert!(std::env::var("GEMINI_API_KEY").is_err());
        assert!(std::env::var("ARIS_REVIEWER_AUTH_TOKEN").is_err());
        // No stale base URL / model exported.
        assert!(std::env::var("ARIS_REVIEWER_BASE_URL").is_err());
        assert!(std::env::var("ARIS_REVIEWER_MODEL").is_err());
        // P1.2: pure codex-mcp ⇒ no fallback provider exported.
        assert!(std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER").is_err());
    }

    // ── v0.4.17 (T10/P1.2): reviewer_fallback_provider round-trip + apply ────

    /// An OLD config.json (written before the `reviewer_fallback_provider` field
    /// existed) must still parse — `#[serde(default)]` makes the missing key
    /// deserialize to `None`. This locks backward compatibility (the field is
    /// additive, never required).
    #[test]
    fn config_parses_legacy_json_without_fallback_field() {
        let legacy = r#"{
            "reviewer_provider": "codex-mcp",
            "reviewer_api_key": null,
            "reviewer_base_url": null,
            "reviewer_model": null,
            "language": "en"
        }"#;
        let parsed: ArisConfig = serde_json::from_str(legacy).expect("legacy json parses");
        assert_eq!(parsed.reviewer_provider.as_deref(), Some("codex-mcp"));
        assert_eq!(parsed.reviewer_fallback_provider, None);
        assert_eq!(parsed.language.as_deref(), Some("en"));
    }

    /// Round-trip with the field PRESENT: serialize → parse must preserve the
    /// fallback provider, and a config carrying it must round-trip losslessly.
    #[test]
    fn config_round_trips_fallback_provider_when_present() {
        let config = ArisConfig {
            reviewer_provider: Some("codex-mcp".into()),
            reviewer_fallback_provider: Some("gemini".into()),
            reviewer_api_key: Some("sk-test-key".into()),
            reviewer_model: Some("gemini-2.5-pro".into()),
            ..Default::default()
        };
        let json = serde_json::to_string(&config).expect("serialize");
        let parsed: ArisConfig = serde_json::from_str(&json).expect("re-parse");
        assert_eq!(parsed.reviewer_provider.as_deref(), Some("codex-mcp"));
        assert_eq!(parsed.reviewer_fallback_provider.as_deref(), Some("gemini"));
        assert_eq!(parsed.reviewer_api_key.as_deref(), Some("sk-test-key"));
        assert_eq!(parsed.reviewer_model.as_deref(), Some("gemini-2.5-pro"));
    }

    /// apply_to_env state 2 (codex-mcp PRIMARY + fallback): the primary provider
    /// stays "codex-mcp", the fallback name is exported separately as
    /// ARIS_REVIEWER_FALLBACK_PROVIDER, and the fallback's key lands in the
    /// fallback provider's key env var (here: gemini → GEMINI_API_KEY), with the
    /// model exported too. The primary must NEVER be overwritten by the fallback.
    #[test]
    fn apply_to_env_codex_mcp_with_fallback_exports_fallback_separately() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(&[
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_FALLBACK_PROVIDER",
            "ARIS_REVIEWER_BASE_URL",
            "ARIS_REVIEWER_MODEL",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ]);

        let config = ArisConfig {
            reviewer_provider: Some("codex-mcp".into()),
            reviewer_fallback_provider: Some("gemini".into()),
            reviewer_api_key: Some("gem-key".into()),
            reviewer_base_url: None,
            reviewer_model: Some("gemini-2.5-pro".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        // Primary stays codex-mcp (NOT usurped by the fallback).
        assert_eq!(
            std::env::var("ARIS_REVIEWER_PROVIDER").ok().as_deref(),
            Some("codex-mcp")
        );
        // Fallback provider exported separately.
        assert_eq!(
            std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER")
                .ok()
                .as_deref(),
            Some("gemini")
        );
        // Fallback key lands in the fallback provider's key env var.
        assert_eq!(
            std::env::var("GEMINI_API_KEY").ok().as_deref(),
            Some("gem-key")
        );
        // Model exported; OpenAI key never written.
        assert_eq!(
            std::env::var("ARIS_REVIEWER_MODEL").ok().as_deref(),
            Some("gemini-2.5-pro")
        );
        assert!(std::env::var("OPENAI_API_KEY").is_err());
    }

    /// apply_to_env state 3 (a NORMAL provider): a plain reviewer provider is
    /// unaffected by the new field — its key exports under its own env var, no
    /// ARIS_REVIEWER_FALLBACK_PROVIDER is ever set, and the provider is itself.
    #[test]
    fn apply_to_env_normal_provider_unaffected_by_fallback_field() {
        let _g = crate::env_test_guard();
        let _snap = EnvSnapshot::capture(&[
            "ARIS_REVIEWER_PROVIDER",
            "ARIS_REVIEWER_FALLBACK_PROVIDER",
            "ARIS_REVIEWER_MODEL",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ]);

        let config = ArisConfig {
            reviewer_provider: Some("openai".into()),
            // No fallback — irrelevant for a non-codex-mcp provider.
            reviewer_fallback_provider: None,
            reviewer_api_key: Some("oa-key".into()),
            reviewer_model: Some("gpt-5.5".into()),
            ..Default::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_PROVIDER").ok().as_deref(),
            Some("openai")
        );
        assert_eq!(
            std::env::var("OPENAI_API_KEY").ok().as_deref(),
            Some("oa-key")
        );
        // Never set for a normal provider.
        assert!(std::env::var("ARIS_REVIEWER_FALLBACK_PROVIDER").is_err());
        assert!(std::env::var("GEMINI_API_KEY").is_err());
    }

    // ── v0.4.22 (Δ4-4/C6): codex probe three-state classifier ────────────────
    //
    // Pure-function tests over `classify_codex_candidates` — no PATH probing,
    // no process spawns, so they run identically on every host (the Windows
    // rule set is selected by the `windows` flag, not cfg!).

    /// Uppercase extensions must classify case-insensitively: .EXE is still a
    /// native executable, .CMD/.BAT are still script shims.
    #[test]
    fn classify_codex_windows_uppercase_extensions() {
        assert_eq!(
            classify_codex_candidates("C:\\tools\\CODEX.EXE\r\n", true),
            CodexProbe::NativeExe(PathBuf::from("C:\\tools\\CODEX.EXE"))
        );
        assert_eq!(
            classify_codex_candidates("C:\\nodejs\\codex.CMD\r\nC:\\nodejs\\codex.BAT\r\n", true),
            CodexProbe::ScriptShim(PathBuf::from("C:\\nodejs\\codex.CMD"))
        );
    }

    /// Leading blank lines (and blank separators) are tolerated — the first
    /// real candidate wins, on both rule sets.
    #[test]
    fn classify_codex_tolerates_leading_blank_lines() {
        assert_eq!(
            classify_codex_candidates("\r\n\r\nC:\\tools\\codex.exe\r\n", true),
            CodexProbe::NativeExe(PathBuf::from("C:\\tools\\codex.exe"))
        );
        assert_eq!(
            classify_codex_candidates("\n\n/usr/local/bin/codex\n", false),
            CodexProbe::NativeExe(PathBuf::from("/usr/local/bin/codex"))
        );
    }

    /// CRLF endings must not leak a trailing `\r` into the classified path.
    #[test]
    fn classify_codex_windows_crlf_endings() {
        let probe = classify_codex_candidates(
            "C:\\Program Files\\Codex\\codex.exe\r\nC:\\nodejs\\codex.cmd\r\n",
            true,
        );
        assert_eq!(
            probe,
            CodexProbe::NativeExe(PathBuf::from("C:\\Program Files\\Codex\\codex.exe"))
        );
    }

    /// The Δ4-4 core rule: a .cmd shim EARLIER in PATH order must NOT hide a
    /// native .exe later in the list — the first .exe wins.
    #[test]
    fn classify_codex_windows_shim_first_native_later_prefers_exe() {
        let raw = "C:\\nodejs\\codex.cmd\r\nC:\\tools\\codex.exe\r\nC:\\other\\codex.exe\r\n";
        assert_eq!(
            classify_codex_candidates(raw, true),
            CodexProbe::NativeExe(PathBuf::from("C:\\tools\\codex.exe")),
            "the FIRST .exe in PATH order must win over an earlier shim"
        );
    }

    /// Candidates but no .exe at all (here: only .com) → ScriptShim carrying
    /// the first candidate.
    #[test]
    fn classify_codex_windows_only_com_is_script_shim() {
        assert_eq!(
            classify_codex_candidates("C:\\legacy\\codex.com\r\n", true),
            CodexProbe::ScriptShim(PathBuf::from("C:\\legacy\\codex.com"))
        );
    }

    /// Empty / whitespace-only `where` output → Missing.
    #[test]
    fn classify_codex_windows_empty_is_missing() {
        assert_eq!(classify_codex_candidates("", true), CodexProbe::Missing);
        assert_eq!(
            classify_codex_candidates("\r\n  \r\n", true),
            CodexProbe::Missing
        );
    }

    /// Unix `which`: a single plain path is always NativeExe (byte-identical
    /// to the pre-v0.4.22 "found" semantics — no extension inspection).
    #[test]
    fn classify_codex_unix_single_path_native() {
        assert_eq!(
            classify_codex_candidates("/opt/homebrew/bin/codex\n", false),
            CodexProbe::NativeExe(PathBuf::from("/opt/homebrew/bin/codex"))
        );
    }

    /// Unix `which` with no output → Missing.
    #[test]
    fn classify_codex_unix_empty_is_missing() {
        assert_eq!(classify_codex_candidates("", false), CodexProbe::Missing);
        assert_eq!(classify_codex_candidates("\n\n", false), CodexProbe::Missing);
    }

    // ── v0.4.22 (Δ-C2/Δ5-4): blank executor model handling ──────────────────

    /// Δ-C2: a blank / whitespace-only saved executor model must read back as
    /// ABSENT (None); real values still come through.
    #[test]
    fn executor_model_blank_or_whitespace_is_none() {
        let blank = ArisConfig {
            executor_model: Some(String::new()),
            ..Default::default()
        };
        assert_eq!(blank.executor_model(), None);

        let whitespace = ArisConfig {
            executor_model: Some("   \t ".into()),
            ..Default::default()
        };
        assert_eq!(whitespace.executor_model(), None);

        let unset = ArisConfig::default();
        assert_eq!(unset.executor_model(), None);

        let real = ArisConfig {
            executor_model: Some("gpt-5.5".into()),
            ..Default::default()
        };
        assert_eq!(real.executor_model(), Some("gpt-5.5"));
    }

    /// Δ5-4: the pure decision behind the wizard's executor-step gate — an
    /// OpenAI/custom executor with a blank (trim-empty) model requires one;
    /// Anthropic-family providers and non-blank models never do.
    #[test]
    fn executor_model_required_only_for_blank_openai_or_custom() {
        // Blank model + OpenAI-transport providers → required.
        assert!(executor_model_required("openai", ""));
        assert!(executor_model_required("openai", "   "));
        assert!(executor_model_required("custom", ""));
        assert!(executor_model_required("custom", " \t "));
        // A real model id satisfies the gate.
        assert!(!executor_model_required("openai", "gpt-5.5"));
        assert!(!executor_model_required("custom", "my-model"));
        // Anthropic-family providers have a built-in default → never required.
        assert!(!executor_model_required("anthropic", ""));
        assert!(!executor_model_required("anthropic-compat", ""));
    }
}
