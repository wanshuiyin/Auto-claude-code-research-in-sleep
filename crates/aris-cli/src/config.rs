//! ARIS persistent configuration.
//!
//! Stores API keys and model preferences in `~/.config/aris/config.json`.
//! Environment variables always take priority over saved config.

use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

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
    /// "gemini" or "openai"
    #[serde(default)]
    pub reviewer_provider: Option<String>,
    #[serde(default)]
    pub reviewer_api_key: Option<String>,
    #[serde(default)]
    pub reviewer_base_url: Option<String>,
    #[serde(default)]
    pub reviewer_model: Option<String>,
    /// "cn" or "en"
    #[serde(default)]
    pub language: Option<String>,
    /// Meta-logging level: "off", "metadata", or "content"
    #[serde(default)]
    pub meta_logging: Option<String>,
}

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

    pub fn save(&self) -> io::Result<()> {
        let path = Self::config_path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self).map_err(|e| {
            io::Error::new(io::ErrorKind::Other, e)
        })?;
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
        }
        // The rest of the function uses `force_exec` and `force_rev` to decide
        // whether to overwrite existing env vars.
        let force = force_exec;
        let force_reviewer = force_rev;

        if let Some(provider) = &self.executor_provider {
            if provider == "openai" {
                std::env::set_var("EXECUTOR_PROVIDER", provider);
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
                        if force || std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err() {
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
                        if force || std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS").is_err() {
                            std::env::set_var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1");
                        }
                    }
                }
                "openai" => {
                    if force || std::env::var("EXECUTOR_API_KEY").is_err() {
                        std::env::set_var("EXECUTOR_API_KEY", key);
                    }
                }
                _ => {}
            }
        }

        // Executor base URL (for openai-compat providers)
        if provider == "openai" {
            if force || std::env::var("EXECUTOR_BASE_URL").is_err() {
                if let Some(url) = &self.executor_base_url {
                    std::env::set_var("EXECUTOR_BASE_URL", url);
                }
            }
        }

        // Reviewer API key — gated on force_reviewer, not force_exec, so
        // executor-only force does not clobber shell-provided reviewer keys.
        if let Some(reviewer_provider) = &self.reviewer_provider {
            if let Some(key) = &self.reviewer_api_key {
                match reviewer_provider.as_str() {
                    "gemini" => {
                        if force_reviewer || std::env::var("GEMINI_API_KEY").is_err() {
                            std::env::set_var("GEMINI_API_KEY", key);
                        }
                    }
                    "openai" => {
                        if force_reviewer || std::env::var("OPENAI_API_KEY").is_err() {
                            std::env::set_var("OPENAI_API_KEY", key);
                        }
                    }
                    "glm" => {
                        if force_reviewer || std::env::var("GLM_API_KEY").is_err() {
                            std::env::set_var("GLM_API_KEY", key);
                        }
                    }
                    "minimax" => {
                        if force_reviewer || std::env::var("MINIMAX_API_KEY").is_err() {
                            std::env::set_var("MINIMAX_API_KEY", key);
                        }
                    }
                    "kimi" => {
                        if force_reviewer || std::env::var("KIMI_API_KEY").is_err() {
                            std::env::set_var("KIMI_API_KEY", key);
                        }
                    }
                    "anthropic-compat" => {
                        if force_reviewer || std::env::var("ARIS_REVIEWER_AUTH_TOKEN").is_err() {
                            std::env::set_var("ARIS_REVIEWER_AUTH_TOKEN", key);
                        }
                    }
                    _ => {}
                }
            }
            // Set reviewer provider env var
            if force_reviewer || std::env::var("ARIS_REVIEWER_PROVIDER").is_err() {
                std::env::set_var("ARIS_REVIEWER_PROVIDER", reviewer_provider);
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
    pub fn executor_model(&self) -> Option<&str> {
        self.executor_model.as_deref()
    }

    /// Check if we have minimum viable config (at least an executor API key).
    pub fn has_executor_key(&self) -> bool {
        self.executor_api_key.as_ref().is_some_and(|k| !k.is_empty())
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
    println!("  2. OpenAI      (gpt-5.4)");
    println!("  3. Gemini      (gemini-2.5-pro)");
    println!("  4. GLM         (GLM-5)");
    println!("  5. MiniMax     (MiniMax-M2.7)");
    println!("  6. Kimi        (kimi-k2.5)");

    let default_executor = match config.executor_provider.as_deref() {
        Some("openai") => match config.executor_base_url.as_deref() {
            Some(u) if u.contains("googleapis") => "3",
            Some(u) if u.contains("bigmodel") => "4",
            Some(u) if u.contains("minimax") => "5",
            Some(u) if u.contains("moonshot") => "6",
            _ => "2",
        },
        _ => "1",
    };
    let exec_choice = prompt_with_default("  Choose [1-6]", default_executor)?;

    // (provider, key_env, key_label, base_url, default_model)
    let exec_info: (&str, &str, &str, Option<&str>, &str) = match exec_choice.trim() {
        "2" => ("openai", "EXECUTOR_API_KEY", "OpenAI API key", Some("https://api.openai.com/v1"), "gpt-5.4"),
        "3" => ("openai", "EXECUTOR_API_KEY", "Gemini API key", Some("https://generativelanguage.googleapis.com/v1beta/openai"), "gemini-2.5-pro"),
        "4" => ("openai", "EXECUTOR_API_KEY", "GLM API key", Some("https://open.bigmodel.cn/api/paas/v4"), "GLM-5"),
        "5" => ("openai", "EXECUTOR_API_KEY", "MiniMax API key", Some("https://api.minimax.chat/v1"), "MiniMax-M2.7"),
        "6" => ("openai", "EXECUTOR_API_KEY", "Kimi API key", Some("https://api.moonshot.cn/v1"), "kimi-k2.5"),
        _ => ("anthropic", "ANTHROPIC_API_KEY", "Anthropic API key", None, "claude-opus-4-6"),
    };

    config.executor_provider = Some(exec_info.0.into());
    if let Some(url) = exec_info.3 {
        config.executor_base_url = Some(url.into());
    } else {
        config.executor_base_url = None;
    }

    // Ask for API key
    let current_key_masked = config
        .executor_api_key
        .as_deref()
        .filter(|k| k.len() > 8)
        .map(|k| format!("{}...{}", &k[..4], &k[k.len() - 4..]))
        .unwrap_or_else(|| "(not set)".into());
    let new_key = prompt_with_default(
        &format!("  {} [{current_key_masked}]", exec_info.2),
        "",
    )?;
    if !new_key.is_empty() {
        config.executor_api_key = Some(new_key);
    }

    // Ask for proxy/custom base URL (all providers)
    let current_url_hint = config.executor_base_url.as_deref().unwrap_or("default");
    let custom_url = prompt_with_default(
        &format!("  Proxy base URL [{current_url_hint}] (Enter for default)"),
        "",
    )?;
    if !custom_url.is_empty() {
        config.executor_base_url = Some(custom_url.clone());
        // Anthropic + custom URL → switch to anthropic-compat (Bearer token mode)
        if exec_info.0 == "anthropic" {
            config.executor_provider = Some("anthropic-compat".into());
        }
    }

    // Auto-set best model for the chosen provider
    config.executor_model = Some(exec_info.4.to_string());
    println!("  \x1b[2mModel: {}\x1b[0m", exec_info.4);

    // ── Step 4: Reviewer ──
    println!("\n\x1b[1m[2/3] Reviewer (for LlmReview tool)\x1b[0m");
    println!("  1. OpenAI          (gpt-5.4)");
    println!("  2. Gemini          (gemini-2.5-pro)");
    println!("  3. GLM             (GLM-5)");
    println!("  4. MiniMax         (MiniMax-M2.7)");
    println!("  5. Kimi            (kimi-k2.5)");
    println!("  6. Anthropic Proxy (claude via proxy)");
    println!("  7. Skip (no reviewer)");
    let reviewer_choice = prompt_with_default(
        "  Choose [1-7]",
        match config.reviewer_provider.as_deref() {
            Some("openai") => "1",
            Some("gemini") => "2",
            Some("glm") => "3",
            Some("minimax") => "4",
            Some("kimi") => "5",
            Some("anthropic-compat") => "6",
            None => "1",
            _ => "7",
        },
    )?;

    // (provider_name, key_env_var, key_label, default_model)
    let reviewer_info: Option<(&str, &str, &str, &str)> = match reviewer_choice.trim() {
        "1" => Some(("openai", "OPENAI_API_KEY", "OpenAI API key", "gpt-5.4")),
        "2" => Some(("gemini", "GEMINI_API_KEY", "Gemini API key", "gemini-2.5-pro")),
        "3" => Some(("glm", "GLM_API_KEY", "GLM API key", "GLM-5")),
        "4" => Some(("minimax", "MINIMAX_API_KEY", "MiniMax API key", "MiniMax-M2.7")),
        "5" => Some(("kimi", "KIMI_API_KEY", "Kimi API key", "kimi-k2.5")),
        "6" => Some(("anthropic-compat", "ARIS_REVIEWER_AUTH_TOKEN", "Reviewer auth token", "claude-sonnet-4-6")),
        _ => None,
    };

    if let Some((provider, key_env, key_label, default_model)) = reviewer_info {
        config.reviewer_provider = Some(provider.into());

        // Ask for API key
        let current_masked = std::env::var(key_env)
            .ok()
            .or_else(|| config.reviewer_api_key.clone())
            .filter(|k| k.len() > 8)
            .map(|k| format!("{}...{}", &k[..4], &k[k.len() - 4..]))
            .unwrap_or_else(|| "(not set)".into());
        let new_key = prompt_with_default(
            &format!("  {key_label} [{current_masked}]"),
            "",
        )?;
        if !new_key.is_empty() {
            config.reviewer_api_key = Some(new_key.clone());
            std::env::set_var(key_env, &new_key);
        } else if let Some(existing) = &config.reviewer_api_key {
            std::env::set_var(key_env, existing);
        }

        // Ask for proxy/custom base URL for reviewer
        let current_reviewer_url = config.reviewer_base_url.as_deref().unwrap_or("default");
        let custom_reviewer_url = prompt_with_default(
            &format!("  Proxy base URL [{current_reviewer_url}] (Enter for default)"),
            "",
        )?;
        if !custom_reviewer_url.is_empty() {
            config.reviewer_base_url = Some(custom_reviewer_url);
        } else if config.reviewer_base_url.is_none() {
            config.reviewer_base_url = None;
        }

        // Auto-set best model for the chosen reviewer provider
        config.reviewer_model = Some(default_model.to_string());
        println!("  \x1b[2mModel: {default_model}\x1b[0m");
    } else {
        config.reviewer_provider = None;
        config.reviewer_api_key = None;
        config.reviewer_base_url = None;
        config.reviewer_model = None;
    }

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
    config.language = Some(if lang_choice.trim() == "2" { "en" } else { "cn" }.into());

    // ── Save ──
    println!("\n\x1b[1mSaving configuration\x1b[0m");
    config.save()?;
    let path = ArisConfig::config_path();
    println!("  Saved to {}", path.display());

    println!("\n\x1b[1;32m✓ Setup complete!\x1b[0m Run `aris` to start.\n");

    Ok(config)
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
