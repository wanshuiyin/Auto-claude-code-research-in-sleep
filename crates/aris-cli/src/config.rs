//! ARIS persistent configuration.
//!
//! Stores API keys and model preferences in `~/.config/aris/config.json`.
//! Environment variables always take priority over saved config.

use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::input;
use crate::openai_compat::{
    fetch_openai_models, is_openai_compat_provider, model_select_items, normalize_openai_base_url,
};

const CONFIG_DIR: &str = ".config/aris";
const CONFIG_FILE: &str = "config.json";

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArisConfig {
    /// "anthropic", "openai", or "custom"
    #[serde(default)]
    pub executor_provider: Option<String>,
    #[serde(default)]
    pub executor_api_key: Option<String>,
    #[serde(default)]
    pub executor_base_url: Option<String>,
    #[serde(default)]
    pub executor_model: Option<String>,
    /// "gemini", "openai", "glm", "minimax", "kimi", "custom", or "none"
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
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
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
        if force {
            std::env::remove_var("EXECUTOR_PROVIDER");
            std::env::remove_var("EXECUTOR_API_KEY");
            std::env::remove_var("EXECUTOR_BASE_URL");
            std::env::remove_var("ARIS_REVIEWER_PROVIDER");
            std::env::remove_var("ARIS_REVIEWER_API_KEY");
            std::env::remove_var("ARIS_REVIEWER_BASE_URL");
            std::env::remove_var("ARIS_REVIEWER_MODEL");
            std::env::remove_var("ARIS_REVIEWER_DISABLED");
        }

        // Executor provider
        let provider = self.executor_provider.as_deref().unwrap_or("anthropic");
        if is_openai_compat_provider(provider) {
            if force || std::env::var("EXECUTOR_PROVIDER").is_err() {
                std::env::set_var("EXECUTOR_PROVIDER", provider);
            }
        } else if force {
            std::env::remove_var("EXECUTOR_PROVIDER");
            std::env::remove_var("EXECUTOR_BASE_URL");
        }

        // Executor API key + base URL
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
                "custom" => {
                    if force || std::env::var("EXECUTOR_API_KEY").is_err() {
                        std::env::set_var("EXECUTOR_API_KEY", key);
                    }
                }
                _ => {}
            }
        }

        // Executor base URL (for openai-compat providers)
        if is_openai_compat_provider(provider) {
            if force || std::env::var("EXECUTOR_BASE_URL").is_err() {
                if let Some(url) = &self.executor_base_url {
                    std::env::set_var("EXECUTOR_BASE_URL", normalize_openai_base_url(url));
                }
            }
        }

        // Reviewer API key
        if let Some(reviewer_provider) = &self.reviewer_provider {
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
                    "custom" => {
                        if force || std::env::var("ARIS_REVIEWER_API_KEY").is_err() {
                            std::env::set_var("ARIS_REVIEWER_API_KEY", key);
                        }
                    }
                    _ => {}
                }
            }
        }

        let should_disable_reviewer = self.reviewer_provider.as_deref() == Some("none")
            && (force || !reviewer_env_present());
        if should_disable_reviewer
            && (force || std::env::var("ARIS_REVIEWER_DISABLED").is_err())
        {
            std::env::set_var("ARIS_REVIEWER_DISABLED", "1");
        }

        if let Some(reviewer_provider) = &self.reviewer_provider {
            if reviewer_provider == "custom" {
                if force || std::env::var("ARIS_REVIEWER_PROVIDER").is_err() {
                    std::env::set_var("ARIS_REVIEWER_PROVIDER", reviewer_provider);
                }
                if force || std::env::var("ARIS_REVIEWER_BASE_URL").is_err() {
                    if let Some(url) = &self.reviewer_base_url {
                        std::env::set_var("ARIS_REVIEWER_BASE_URL", normalize_openai_base_url(url));
                    }
                }
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
    println!("  1. Anthropic   (claude-opus / sonnet / haiku)");
    println!("  2. OpenAI      (gpt-5.4)");
    println!("  3. Gemini      (gemini-2.5-pro)");
    println!("  4. GLM         (GLM-5)");
    println!("  5. MiniMax     (MiniMax-M2.7)");
    println!("  6. Kimi        (kimi-k2.5)");
    println!("  7. Custom OpenAI-compatible");

    let default_executor = match config.executor_provider.as_deref() {
        Some("openai") => match config.executor_base_url.as_deref() {
            Some(u) if u.contains("googleapis") => "3",
            Some(u) if u.contains("bigmodel") => "4",
            Some(u) if u.contains("minimax") => "5",
            Some(u) if u.contains("moonshot") => "6",
            Some(u) if u.contains("api.openai.com") => "2",
            Some(_) => "7",
            _ => "2",
        },
        Some("custom") => "7",
        _ => "1",
    };
    let exec_choice = prompt_with_default("  Choose [1-7]", default_executor)?;

    // (provider, key_env, key_label, base_url, default_model)
    match exec_choice.trim() {
        "2" => configure_builtin_executor(
            &mut config,
            "openai",
            "OpenAI API key",
            Some("https://api.openai.com/v1"),
            "gpt-5.4",
        )?,
        "3" => configure_builtin_executor(
            &mut config,
            "openai",
            "Gemini API key",
            Some("https://generativelanguage.googleapis.com/v1beta/openai"),
            "gemini-2.5-pro",
        )?,
        "4" => configure_builtin_executor(
            &mut config,
            "openai",
            "GLM API key",
            Some("https://open.bigmodel.cn/api/paas/v4"),
            "GLM-5",
        )?,
        "5" => configure_builtin_executor(
            &mut config,
            "openai",
            "MiniMax API key",
            Some("https://api.minimax.chat/v1"),
            "MiniMax-M2.7",
        )?,
        "6" => configure_builtin_executor(
            &mut config,
            "openai",
            "Kimi API key",
            Some("https://api.moonshot.cn/v1"),
            "kimi-k2.5",
        )?,
        "7" => configure_custom_executor(&mut config)?,
        _ => configure_builtin_executor(
            &mut config,
            "anthropic",
            "Anthropic API key",
            None,
            "claude-opus-4-6",
        )?,
    }

    // ── Step 4: Reviewer ──
    println!("\n\x1b[1m[2/3] Reviewer (for LlmReview tool)\x1b[0m");
    println!("  1. OpenAI    (gpt-5.4)");
    println!("  2. Gemini    (gemini-2.5-pro)");
    println!("  3. GLM       (GLM-5)");
    println!("  4. MiniMax   (MiniMax-M2.7)");
    println!("  5. Kimi      (kimi-k2.5)");
    println!("  6. Custom OpenAI-compatible");
    println!("  7. Skip (no reviewer)");
    let reviewer_choice = prompt_with_default(
        "  Choose [1-7]",
        match config.reviewer_provider.as_deref() {
            Some("openai") => "1",
            Some("gemini") => "2",
            Some("glm") => "3",
            Some("minimax") => "4",
            Some("kimi") => "5",
            Some("custom") => "6",
            None => "1",
            _ => "7",
        },
    )?;

    match reviewer_choice.trim() {
        "1" => configure_builtin_reviewer(
            &mut config,
            "openai",
            "OPENAI_API_KEY",
            "OpenAI API key",
            "gpt-5.4",
        )?,
        "2" => configure_builtin_reviewer(
            &mut config,
            "gemini",
            "GEMINI_API_KEY",
            "Gemini API key",
            "gemini-2.5-pro",
        )?,
        "3" => {
            configure_builtin_reviewer(&mut config, "glm", "GLM_API_KEY", "GLM API key", "GLM-5")?
        }
        "4" => configure_builtin_reviewer(
            &mut config,
            "minimax",
            "MINIMAX_API_KEY",
            "MiniMax API key",
            "MiniMax-M2.7",
        )?,
        "5" => configure_builtin_reviewer(
            &mut config,
            "kimi",
            "KIMI_API_KEY",
            "Kimi API key",
            "kimi-k2.5",
        )?,
        "6" => configure_custom_reviewer(&mut config)?,
        _ => {
            config.reviewer_provider = Some("none".to_string());
            config.reviewer_api_key = None;
            config.reviewer_base_url = None;
            config.reviewer_model = None;
        }
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

fn configure_builtin_executor(
    config: &mut ArisConfig,
    provider: &str,
    key_label: &str,
    base_url: Option<&str>,
    default_model: &str,
) -> io::Result<()> {
    let preserve_existing = same_executor_slot(config, provider, base_url);
    config.executor_provider = Some(provider.to_string());
    config.executor_base_url = base_url.map(normalize_openai_base_url);

    let current_key_masked = if preserve_existing {
        mask_secret(config.executor_api_key.as_deref())
    } else {
        "(not set)".to_string()
    };
    let key_prompt = if current_key_masked == "(not set)" {
        format!("  {key_label}")
    } else {
        format!("  {key_label} [{current_key_masked}]")
    };
    let new_key = prompt_with_default(&key_prompt, "")?;
    apply_prompted_secret(&mut config.executor_api_key, preserve_existing, new_key);

    config.executor_model = Some(default_model.to_string());
    println!("  \x1b[2mModel: {default_model}\x1b[0m");
    Ok(())
}

fn configure_builtin_reviewer(
    config: &mut ArisConfig,
    provider: &str,
    key_env: &str,
    key_label: &str,
    default_model: &str,
) -> io::Result<()> {
    let preserve_existing = same_reviewer_slot(config, provider);
    config.reviewer_provider = Some(provider.to_string());
    config.reviewer_base_url = None;

    let current_secret = if preserve_existing {
        std::env::var(key_env)
            .ok()
            .or_else(|| config.reviewer_api_key.clone())
    } else {
        None
    };
    let current_masked = mask_secret(current_secret.as_deref());
    let key_prompt = if current_masked == "(not set)" {
        format!("  {key_label}")
    } else {
        format!("  {key_label} [{current_masked}]")
    };
    let new_key = prompt_with_default(&key_prompt, "")?;
    apply_prompted_secret(&mut config.reviewer_api_key, preserve_existing, new_key);
    if let Some(existing) = &config.reviewer_api_key {
        std::env::set_var(key_env, existing);
    }

    config.reviewer_model = Some(default_model.to_string());
    println!("  \x1b[2mModel: {default_model}\x1b[0m");
    Ok(())
}

fn configure_custom_executor(config: &mut ArisConfig) -> io::Result<()> {
    let preserve_existing = config.executor_provider.as_deref() == Some("custom");
    loop {
        config.executor_provider = Some("custom".to_string());

        let current_key_masked = if preserve_existing {
            mask_secret(config.executor_api_key.as_deref())
        } else {
            "(not set)".to_string()
        };
        let key_prompt = if current_key_masked == "(not set)" {
            "  Custom API key".to_string()
        } else {
            format!("  Custom API key [{current_key_masked}]")
        };
        let new_key = prompt_with_default(&key_prompt, "")?;
        apply_prompted_secret(&mut config.executor_api_key, preserve_existing, new_key);

        let current_base_url = if preserve_existing {
            config.executor_base_url.as_deref()
        } else {
            None
        };
        let base_prompt = match current_base_url {
            Some(url) => format!("  Custom base URL [{url}]"),
            None => "  Custom base URL".to_string(),
        };
        let base_default = current_base_url.unwrap_or("");
        let new_base_url = prompt_with_default(&base_prompt, base_default)?;
        apply_prompted_base_url(&mut config.executor_base_url, preserve_existing, new_base_url);

        let Some(api_key) = config
            .executor_api_key
            .as_deref()
            .filter(|value| !value.is_empty())
        else {
            println!("  Error: Custom API key is required.");
            continue;
        };
        let Some(base_url) = config
            .executor_base_url
            .as_deref()
            .filter(|value| !value.is_empty())
        else {
            println!("  Error: Custom base URL is required.");
            continue;
        };

        match fetch_openai_models(base_url, api_key) {
            Ok(models) => {
                let current_model = config.executor_model.as_deref().unwrap_or("");
                match select_model_from_list(
                    "Select executor model",
                    "Models fetched from the custom /models endpoint.",
                    &models,
                    current_model,
                )? {
                    Some(model) => {
                        config.executor_model = Some(model.clone());
                        println!("  \x1b[2mModel: {model}\x1b[0m");
                        return Ok(());
                    }
                    None => println!(
                        "  Model selection cancelled. Fetching the custom model list again."
                    ),
                }
            }
            Err(error) => {
                println!("  Error fetching custom models: {error}");
                println!("  Re-enter the custom API key or base URL and try again.");
            }
        }
    }
}

fn configure_custom_reviewer(config: &mut ArisConfig) -> io::Result<()> {
    let preserve_existing = config.reviewer_provider.as_deref() == Some("custom");
    loop {
        config.reviewer_provider = Some("custom".to_string());

        let current_key_masked = if preserve_existing {
            mask_secret(config.reviewer_api_key.as_deref())
        } else {
            "(not set)".to_string()
        };
        let key_prompt = if current_key_masked == "(not set)" {
            "  Custom reviewer API key".to_string()
        } else {
            format!("  Custom reviewer API key [{current_key_masked}]")
        };
        let new_key = prompt_with_default(&key_prompt, "")?;
        apply_prompted_secret(&mut config.reviewer_api_key, preserve_existing, new_key);

        let current_base_url = if preserve_existing {
            config.reviewer_base_url.as_deref()
        } else {
            None
        };
        let base_prompt = match current_base_url {
            Some(url) => format!("  Custom reviewer base URL [{url}]"),
            None => "  Custom reviewer base URL".to_string(),
        };
        let base_default = current_base_url.unwrap_or("");
        let new_base_url = prompt_with_default(&base_prompt, base_default)?;
        apply_prompted_base_url(&mut config.reviewer_base_url, preserve_existing, new_base_url);

        let Some(api_key) = config
            .reviewer_api_key
            .as_deref()
            .filter(|value| !value.is_empty())
        else {
            println!("  Error: Custom reviewer API key is required.");
            continue;
        };
        let Some(base_url) = config
            .reviewer_base_url
            .as_deref()
            .filter(|value| !value.is_empty())
        else {
            println!("  Error: Custom reviewer base URL is required.");
            continue;
        };

        match fetch_openai_models(base_url, api_key) {
            Ok(models) => {
                let current_model = config.reviewer_model.as_deref().unwrap_or("");
                match select_model_from_list(
                    "Select reviewer model",
                    "Models fetched from the custom reviewer /models endpoint.",
                    &models,
                    current_model,
                )? {
                    Some(model) => {
                        config.reviewer_model = Some(model.clone());
                        println!("  \x1b[2mModel: {model}\x1b[0m");
                        return Ok(());
                    }
                    None => println!(
                        "  Model selection cancelled. Fetching the custom model list again."
                    ),
                }
            }
            Err(error) => {
                println!("  Error fetching custom reviewer models: {error}");
                println!("  Re-enter the custom reviewer API key or base URL and try again.");
            }
        }
    }
}

fn select_model_from_list(
    title: &str,
    subtitle: &str,
    models: &[crate::openai_compat::OpenAIModelInfo],
    current_model: &str,
) -> io::Result<Option<String>> {
    let items = model_select_items(models, current_model);
    match input::select_menu(title, subtitle, &items)? {
        Some(index) => Ok(Some(items[index].label.clone())),
        None => Ok(None),
    }
}

fn mask_secret(value: Option<&str>) -> String {
    value
        .filter(|secret| secret.len() > 8)
        .map(|secret| format!("{}...{}", &secret[..4], &secret[secret.len() - 4..]))
        .unwrap_or_else(|| "(not set)".to_string())
}

fn apply_prompted_secret(existing: &mut Option<String>, preserve_existing: bool, new_value: String) {
    if new_value.is_empty() {
        if !preserve_existing {
            *existing = None;
        }
    } else {
        *existing = Some(new_value);
    }
}

fn apply_prompted_base_url(existing: &mut Option<String>, preserve_existing: bool, new_value: String) {
    if new_value.is_empty() {
        if !preserve_existing {
            *existing = None;
        }
    } else {
        *existing = Some(normalize_openai_base_url(&new_value));
    }
}

fn same_executor_slot(config: &ArisConfig, provider: &str, base_url: Option<&str>) -> bool {
    match (config.executor_provider.as_deref(), provider) {
        (Some("anthropic"), "anthropic") => true,
        (Some("custom"), "custom") => true,
        (Some("openai"), "openai") => config.executor_base_url.as_deref().map(normalize_openai_base_url)
            == base_url.map(normalize_openai_base_url),
        _ => false,
    }
}

fn same_reviewer_slot(config: &ArisConfig, provider: &str) -> bool {
    config.reviewer_provider.as_deref() == Some(provider)
}

fn reviewer_env_present() -> bool {
    [
        "ARIS_REVIEWER_DISABLED",
        "ARIS_REVIEWER_PROVIDER",
        "ARIS_REVIEWER_API_KEY",
        "ARIS_REVIEWER_BASE_URL",
        "ARIS_REVIEWER_MODEL",
    ]
    .into_iter()
    .any(|name| std::env::var(name).ok().is_some_and(|value| !value.is_empty()))
}

#[cfg(test)]
mod tests {
    use std::sync::{Mutex, OnceLock};

    use super::{
        apply_prompted_secret, same_executor_slot, same_reviewer_slot, ArisConfig,
    };

    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    #[test]
    fn config_round_trip_preserves_reviewer_base_url() {
        let config = ArisConfig {
            reviewer_provider: Some("custom".to_string()),
            reviewer_api_key: Some("rk-test-123456789".to_string()),
            reviewer_base_url: Some("https://example.com/v1".to_string()),
            reviewer_model: Some("custom-model".to_string()),
            ..ArisConfig::default()
        };

        let json = serde_json::to_string(&config).expect("serialize config");
        let decoded: ArisConfig = serde_json::from_str(&json).expect("deserialize config");
        assert_eq!(
            decoded.reviewer_base_url.as_deref(),
            Some("https://example.com/v1")
        );
    }

    #[test]
    fn force_apply_to_env_sets_custom_reviewer_envs() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::remove_var("ARIS_REVIEWER_PROVIDER");
        std::env::remove_var("ARIS_REVIEWER_API_KEY");
        std::env::remove_var("ARIS_REVIEWER_BASE_URL");
        std::env::remove_var("ARIS_REVIEWER_DISABLED");

        let config = ArisConfig {
            reviewer_provider: Some("custom".to_string()),
            reviewer_api_key: Some("rk-test-123456789".to_string()),
            reviewer_base_url: Some("https://example.com/v1/chat/completions".to_string()),
            reviewer_model: Some("custom-reviewer".to_string()),
            ..ArisConfig::default()
        };

        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_PROVIDER").as_deref(),
            Ok("custom")
        );
        assert_eq!(
            std::env::var("ARIS_REVIEWER_API_KEY").as_deref(),
            Ok("rk-test-123456789")
        );
        assert_eq!(
            std::env::var("ARIS_REVIEWER_BASE_URL").as_deref(),
            Ok("https://example.com/v1")
        );
    }

    #[test]
    fn force_apply_to_env_clears_custom_reviewer_envs_for_builtin_provider() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::set_var("ARIS_REVIEWER_PROVIDER", "custom");
        std::env::set_var("ARIS_REVIEWER_API_KEY", "stale-key");
        std::env::set_var("ARIS_REVIEWER_BASE_URL", "https://stale.example/v1");
        std::env::set_var("ARIS_REVIEWER_DISABLED", "1");

        let config = ArisConfig {
            reviewer_provider: Some("openai".to_string()),
            reviewer_api_key: Some("rk-openai-123456789".to_string()),
            reviewer_model: Some("gpt-5.4".to_string()),
            ..ArisConfig::default()
        };

        config.force_apply_to_env();

        assert!(std::env::var("ARIS_REVIEWER_PROVIDER").is_err());
        assert!(std::env::var("ARIS_REVIEWER_API_KEY").is_err());
        assert!(std::env::var("ARIS_REVIEWER_BASE_URL").is_err());
        assert!(std::env::var("ARIS_REVIEWER_DISABLED").is_err());
    }

    #[test]
    fn force_apply_to_env_clears_executor_provider_when_switching_to_anthropic() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::set_var("EXECUTOR_PROVIDER", "custom");
        std::env::set_var("EXECUTOR_API_KEY", "stale-executor-key");
        std::env::set_var("EXECUTOR_BASE_URL", "https://old.example/v1");

        let config = ArisConfig {
            executor_provider: Some("anthropic".to_string()),
            executor_api_key: Some("sk-ant-test".to_string()),
            ..ArisConfig::default()
        };

        config.force_apply_to_env();

        assert!(std::env::var("EXECUTOR_PROVIDER").is_err());
        assert!(std::env::var("EXECUTOR_API_KEY").is_err());
        assert!(std::env::var("EXECUTOR_BASE_URL").is_err());
    }

    #[test]
    fn force_apply_to_env_marks_reviewer_as_disabled_for_skip() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::remove_var("ARIS_REVIEWER_DISABLED");
        std::env::remove_var("ARIS_REVIEWER_MODEL");

        let config = ArisConfig {
            reviewer_provider: Some("none".to_string()),
            ..ArisConfig::default()
        };

        config.force_apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_DISABLED").as_deref(),
            Ok("1")
        );
        assert!(std::env::var("ARIS_REVIEWER_MODEL").is_err());
    }

    #[test]
    fn force_apply_to_env_clears_stale_executor_key_when_config_key_is_missing() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::set_var("EXECUTOR_API_KEY", "stale-executor-key");

        let config = ArisConfig {
            executor_provider: Some("custom".to_string()),
            executor_base_url: Some("https://custom.example/v1".to_string()),
            executor_api_key: None,
            ..ArisConfig::default()
        };

        config.force_apply_to_env();

        assert_eq!(std::env::var("EXECUTOR_PROVIDER").as_deref(), Ok("custom"));
        assert_eq!(
            std::env::var("EXECUTOR_BASE_URL").as_deref(),
            Ok("https://custom.example/v1")
        );
        assert!(std::env::var("EXECUTOR_API_KEY").is_err());
    }

    #[test]
    fn apply_to_env_marks_reviewer_as_disabled_even_with_openai_key_present() {
        let _guard = env_lock().lock().expect("lock env");
        std::env::remove_var("ARIS_REVIEWER_DISABLED");
        std::env::remove_var("ARIS_REVIEWER_PROVIDER");
        std::env::remove_var("ARIS_REVIEWER_API_KEY");
        std::env::remove_var("ARIS_REVIEWER_BASE_URL");
        std::env::remove_var("ARIS_REVIEWER_MODEL");
        std::env::set_var("OPENAI_API_KEY", "sk-openai-test");

        let config = ArisConfig {
            reviewer_provider: Some("none".to_string()),
            ..ArisConfig::default()
        };

        config.apply_to_env();

        assert_eq!(
            std::env::var("ARIS_REVIEWER_DISABLED").as_deref(),
            Ok("1")
        );

        std::env::remove_var("OPENAI_API_KEY");
        std::env::remove_var("ARIS_REVIEWER_DISABLED");
    }

    #[test]
    fn prompted_secret_clears_when_switching_provider_and_pressing_enter() {
        let mut secret = Some("stale-key".to_string());
        apply_prompted_secret(&mut secret, false, String::new());
        assert_eq!(secret, None);
    }

    #[test]
    fn same_slot_helpers_only_preserve_matching_provider_configuration() {
        let config = ArisConfig {
            executor_provider: Some("openai".to_string()),
            executor_base_url: Some("https://api.moonshot.cn/v1".to_string()),
            reviewer_provider: Some("gemini".to_string()),
            ..ArisConfig::default()
        };

        assert!(same_executor_slot(
            &config,
            "openai",
            Some("https://api.moonshot.cn/v1/")
        ));
        assert!(!same_executor_slot(
            &config,
            "openai",
            Some("https://api.openai.com/v1")
        ));
        assert!(same_reviewer_slot(&config, "gemini"));
        assert!(!same_reviewer_slot(&config, "openai"));
    }
}
