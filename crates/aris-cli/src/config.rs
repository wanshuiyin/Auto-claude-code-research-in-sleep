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

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArisConfig {
    /// "anthropic", "anthropic-compat", or "openai"
    #[serde(default)]
    pub executor_provider: Option<String>,
    #[serde(default)]
    pub executor_api_key: Option<String>,
    #[serde(default)]
    pub executor_base_url: Option<String>,
    #[serde(default)]
    pub executor_model: Option<String>,
    /// "openai", "gemini", "glm", "minimax", "kimi", or "anthropic-compat"
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
        let json = serde_json::to_string_pretty(self)
            .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;
        fs::write(&path, json)
    }

    /// Apply saved config to environment variables.
    /// If `force` is true, overwrite existing env vars (used by /setup in REPL).
    pub fn apply_to_env(&self) {
        self.apply_to_env_inner(false);
    }

    pub fn force_apply_to_env(&self) {
        self.apply_to_env_inner(true);
    }

    fn apply_to_env_inner(&self, force: bool) {
        // Executor provider — clean up stale env vars from previous provider on switch
        if force {
            // Clear ALL executor-related env vars first to prevent cross-contamination
            std::env::remove_var("EXECUTOR_PROVIDER");
            std::env::remove_var("EXECUTOR_API_KEY");
            std::env::remove_var("EXECUTOR_BASE_URL");
            std::env::remove_var("ANTHROPIC_API_KEY");
            std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
            std::env::remove_var("ANTHROPIC_BASE_URL");
            // Clear ALL reviewer-related env vars
            std::env::remove_var("OPENAI_API_KEY");
            std::env::remove_var("GEMINI_API_KEY");
            std::env::remove_var("GLM_API_KEY");
            std::env::remove_var("MINIMAX_API_KEY");
            std::env::remove_var("KIMI_API_KEY");
            std::env::remove_var("ARIS_REVIEWER_PROVIDER");
            std::env::remove_var("ARIS_REVIEWER_AUTH_TOKEN");
            std::env::remove_var("ARIS_REVIEWER_MODEL");
            std::env::remove_var("ARIS_REVIEWER_BASE_URL");
        }

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

        // Reviewer API key
        if let Some(reviewer_provider) = &self.reviewer_provider {
            if force || std::env::var("ARIS_REVIEWER_PROVIDER").is_err() {
                std::env::set_var("ARIS_REVIEWER_PROVIDER", reviewer_provider);
            }
            if let Some(key) = &self.reviewer_api_key {
                match reviewer_provider.as_str() {
                    "gemini" => {
                        if force || std::env::var("GEMINI_API_KEY").is_err() {
                            std::env::set_var("GEMINI_API_KEY", key);
                        }
                    }
                    "openai" => {
                        if force || std::env::var("OPENAI_API_KEY").is_err() {
                            std::env::set_var("OPENAI_API_KEY", key);
                        }
                    }
                    "glm" => {
                        if force || std::env::var("GLM_API_KEY").is_err() {
                            std::env::set_var("GLM_API_KEY", key);
                        }
                    }
                    "minimax" => {
                        if force || std::env::var("MINIMAX_API_KEY").is_err() {
                            std::env::set_var("MINIMAX_API_KEY", key);
                        }
                    }
                    "kimi" => {
                        if force || std::env::var("KIMI_API_KEY").is_err() {
                            std::env::set_var("KIMI_API_KEY", key);
                        }
                    }
                    "anthropic-compat" => {
                        if force || std::env::var("ARIS_REVIEWER_AUTH_TOKEN").is_err() {
                            std::env::set_var("ARIS_REVIEWER_AUTH_TOKEN", key);
                        }
                    }
                    _ => {}
                }
            }
        }

        // Reviewer base URL
        if force || std::env::var("ARIS_REVIEWER_BASE_URL").is_err() {
            if let Some(url) = &self.reviewer_base_url {
                std::env::set_var("ARIS_REVIEWER_BASE_URL", url);
            }
        }

        // Reviewer model
        if force || std::env::var("ARIS_REVIEWER_MODEL").is_err() {
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
        self.executor_api_key
            .as_ref()
            .is_some_and(|k| !k.is_empty())
    }
}

/// Interactive setup wizard. Returns the configured settings.
pub fn run_interactive_setup() -> io::Result<ArisConfig> {
    let mut config = ArisConfig::load();

    println!("\x1b[1mARIS Setup\x1b[0m");
    println!("\x1b[2mConfigure API keys and models. Press Enter to keep current value.\x1b[0m\n");

    // ── Step 1+2: Executor provider + key + model ──
    println!("\x1b[1m[1/3] Executor (main LLM)\x1b[0m");
    println!("  1. Anthropic official           (Claude API / OAuth)");
    println!("  2. Anthropic-compatible proxy   (any /v1/messages endpoint)");
    println!("  3. OpenAI                       (official API)");
    println!("  4. OpenAI-compatible generic    (any /v1/chat/completions endpoint)");
    println!("  5. Gemini                       (preset OpenAI-compatible endpoint)");
    println!("  6. GLM                          (preset OpenAI-compatible endpoint)");
    println!("  7. MiniMax                      (preset OpenAI-compatible endpoint)");
    println!("  8. Kimi                         (preset Anthropic-compatible endpoint)");

    let default_executor = match config.executor_provider.as_deref() {
        Some("anthropic-compat") => "2",
        Some("openai") => match config.executor_base_url.as_deref() {
            Some(u) if u.contains("api.openai.com") => "3",
            Some(u) if u.contains("googleapis") => "5",
            Some(u) if u.contains("bigmodel") => "6",
            Some(u) if u.contains("minimax") => "7",
            _ => "4",
        },
        _ => "1",
    };
    let exec_choice = prompt_with_default("  Choose [1-8]", default_executor)?;

    // (provider, key_env, key_label, base_url, default_model)
    let exec_info: (&str, &str, &str, Option<&str>, &str) = match exec_choice.trim() {
        "2" => (
            "anthropic-compat",
            "ANTHROPIC_AUTH_TOKEN",
            "Anthropic-compatible bearer token",
            None,
            "claude-opus-4-6",
        ),
        "3" => (
            "openai",
            "EXECUTOR_API_KEY",
            "OpenAI API key",
            Some("https://api.openai.com/v1"),
            "gpt-5.4",
        ),
        "4" => (
            "openai",
            "EXECUTOR_API_KEY",
            "OpenAI-compatible API key",
            None,
            "gpt-4o",
        ),
        "5" => (
            "openai",
            "EXECUTOR_API_KEY",
            "Gemini API key",
            Some("https://generativelanguage.googleapis.com/v1beta/openai"),
            "gemini-2.5-pro",
        ),
        "6" => (
            "openai",
            "EXECUTOR_API_KEY",
            "GLM API key",
            Some("https://open.bigmodel.cn/api/paas/v4"),
            "GLM-5",
        ),
        "7" => (
            "openai",
            "EXECUTOR_API_KEY",
            "MiniMax API key",
            Some("https://api.minimax.chat/v1"),
            "MiniMax-M2.7",
        ),
        "8" => (
            "anthropic-compat",
            "ANTHROPIC_AUTH_TOKEN",
            "Kimi API key",
            Some("https://api.kimi.com/coding/"),
            "kimi-k2.5",
        ),
        _ => (
            "anthropic",
            "ANTHROPIC_API_KEY",
            "Anthropic API key",
            None,
            "claude-opus-4-6",
        ),
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
    let new_key = prompt_with_default(&format!("  {} [{current_key_masked}]", exec_info.2), "")?;
    if !new_key.is_empty() {
        config.executor_api_key = Some(new_key);
    }

    // Ask for proxy/custom base URL (all providers)
    let current_url_hint = config.executor_base_url.as_deref().unwrap_or("default");
    let custom_url = prompt_with_default(
        &format!("  Base URL [{current_url_hint}] (Enter for default)"),
        "",
    )?;
    if !custom_url.is_empty() {
        config.executor_base_url = Some(custom_url);
    } else if exec_info.3.is_none() {
        config.executor_base_url = None;
    }

    let current_executor_model = config.executor_model.as_deref().unwrap_or(exec_info.4);
    let executor_model = prompt_with_default(
        &format!("  Model [{current_executor_model}]"),
        current_executor_model,
    )?;
    config.executor_model = Some(executor_model.clone());
    println!("  \x1b[2mModel: {executor_model}\x1b[0m");

    // ── Step 4: Reviewer ──
    println!("\n\x1b[1m[2/3] Reviewer (for LlmReview tool)\x1b[0m");
    println!("  1. OpenAI                 (official API)");
    println!("  2. OpenAI-compatible      (any /v1/chat/completions endpoint)");
    println!("  3. Gemini                 (preset OpenAI-compatible endpoint)");
    println!("  4. GLM                    (preset OpenAI-compatible endpoint)");
    println!("  5. MiniMax                (preset OpenAI-compatible endpoint)");
    println!("  6. Kimi                   (preset Anthropic-compatible endpoint)");
    println!("  7. Anthropic-compatible   (any /v1/messages endpoint)");
    println!("  8. Skip (no reviewer)");
    let reviewer_choice = prompt_with_default(
        "  Choose [1-8]",
        match config.reviewer_provider.as_deref() {
            Some("openai") => match config.reviewer_base_url.as_deref() {
                Some(url) if !url.contains("api.openai.com") => "2",
                _ => "1",
            },
            Some("gemini") => "3",
            Some("glm") => "4",
            Some("minimax") => "5",
            Some("anthropic-compat") => match config.reviewer_base_url.as_deref() {
                Some(url) if url.contains("moonshot") || url.contains("api.kimi.com") => "6",
                _ => "7",
            },
            None => "1",
            _ => "8",
        },
    )?;

    // (provider_name, key_env_var, key_label, default_model)
    let reviewer_info: Option<(&str, &str, &str, &str)> = match reviewer_choice.trim() {
        "1" => Some(("openai", "OPENAI_API_KEY", "OpenAI API key", "gpt-5.4")),
        "2" => Some((
            "openai",
            "OPENAI_API_KEY",
            "OpenAI-compatible API key",
            "gpt-4o",
        )),
        "3" => Some((
            "gemini",
            "GEMINI_API_KEY",
            "Gemini API key",
            "gemini-2.5-pro",
        )),
        "4" => Some(("glm", "GLM_API_KEY", "GLM API key", "GLM-5")),
        "5" => Some((
            "minimax",
            "MINIMAX_API_KEY",
            "MiniMax API key",
            "MiniMax-M2.7",
        )),
        "6" => Some((
            "anthropic-compat",
            "KIMI_API_KEY",
            "Kimi API key",
            "kimi-k2.5",
        )),
        "7" => Some((
            "anthropic-compat",
            "ARIS_REVIEWER_AUTH_TOKEN",
            "Anthropic-compatible bearer token",
            "claude-opus-4-6",
        )),
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
        let new_key = prompt_with_default(&format!("  {key_label} [{current_masked}]"), "")?;
        if !new_key.is_empty() {
            config.reviewer_api_key = Some(new_key.clone());
            std::env::set_var(key_env, &new_key);
        } else if let Some(existing) = &config.reviewer_api_key {
            std::env::set_var(key_env, existing);
        }

        // Ask for proxy/custom base URL for reviewer
        let current_reviewer_url = config.reviewer_base_url.as_deref().unwrap_or("default");
        let reviewer_default_url = match reviewer_choice.trim() {
            "2" => "",
            "3" => "https://generativelanguage.googleapis.com/v1beta/openai",
            "4" => "https://open.bigmodel.cn/api/paas/v4",
            "5" => "https://api.minimax.chat/v1",
            "6" => "https://api.kimi.com/coding/",
            _ => "",
        };
        let custom_reviewer_url = prompt_with_default(
            &format!("  Base URL [{current_reviewer_url}] (Enter for default)"),
            reviewer_default_url,
        )?;
        if !custom_reviewer_url.is_empty() {
            config.reviewer_base_url = Some(custom_reviewer_url);
        } else if config.reviewer_base_url.is_none() {
            config.reviewer_base_url = None;
        }

        let current_reviewer_model = config.reviewer_model.as_deref().unwrap_or(default_model);
        let reviewer_model = prompt_with_default(
            &format!("  Model [{current_reviewer_model}]"),
            current_reviewer_model,
        )?;
        config.reviewer_model = Some(reviewer_model.clone());
        println!("  \x1b[2mModel: {reviewer_model}\x1b[0m");
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

#[cfg(test)]
mod tests {
    use super::ArisConfig;
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    #[test]
    fn anthropic_compat_executor_sets_expected_env_vars() {
        let _lock = env_lock();
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_BASE_URL");

        let config = ArisConfig {
            executor_provider: Some("anthropic-compat".into()),
            executor_api_key: Some("token-123".into()),
            executor_base_url: Some("https://proxy.example".into()),
            ..ArisConfig::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ANTHROPIC_AUTH_TOKEN").as_deref(),
            Ok("token-123")
        );
        assert_eq!(
            std::env::var("ANTHROPIC_BASE_URL").as_deref(),
            Ok("https://proxy.example")
        );
    }

    #[test]
    fn anthropic_compat_reviewer_sets_expected_env_vars() {
        let _lock = env_lock();
        std::env::remove_var("ARIS_REVIEWER_PROVIDER");
        std::env::remove_var("ARIS_REVIEWER_AUTH_TOKEN");
        std::env::remove_var("ARIS_REVIEWER_BASE_URL");
        std::env::remove_var("ARIS_REVIEWER_MODEL");

        let config = ArisConfig {
            reviewer_provider: Some("anthropic-compat".into()),
            reviewer_api_key: Some("reviewer-token".into()),
            reviewer_base_url: Some("https://reviewer.example".into()),
            reviewer_model: Some("claude-sonnet-4-6".into()),
            ..ArisConfig::default()
        };
        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_PROVIDER").as_deref(),
            Ok("anthropic-compat")
        );
        assert_eq!(
            std::env::var("ARIS_REVIEWER_AUTH_TOKEN").as_deref(),
            Ok("reviewer-token")
        );
        assert_eq!(
            std::env::var("ARIS_REVIEWER_BASE_URL").as_deref(),
            Ok("https://reviewer.example")
        );
        assert_eq!(
            std::env::var("ARIS_REVIEWER_MODEL").as_deref(),
            Ok("claude-sonnet-4-6")
        );
    }
}
