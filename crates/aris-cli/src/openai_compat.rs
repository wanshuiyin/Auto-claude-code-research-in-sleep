use std::collections::HashSet;

use reqwest::Client;
use serde_json::Value;

use crate::input::SelectItem;

const DEFAULT_OPENAI_BASE_URL: &str = "https://api.openai.com/v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OpenAIModelInfo {
    pub id: String,
    pub owned_by: Option<String>,
}

pub fn is_openai_compat_provider(provider: &str) -> bool {
    matches!(provider, "openai" | "custom")
}

pub fn normalize_openai_base_url(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');
    if trimmed.is_empty() {
        return DEFAULT_OPENAI_BASE_URL.to_string();
    }

    let without_chat = trimmed.strip_suffix("/chat/completions").unwrap_or(trimmed);
    let without_models = without_chat.strip_suffix("/models").unwrap_or(without_chat);
    without_models.trim_end_matches('/').to_string()
}

pub fn chat_completions_url(base_url: &str) -> String {
    format!("{}/chat/completions", normalize_openai_base_url(base_url))
}

pub fn models_url(base_url: &str) -> String {
    format!("{}/models", normalize_openai_base_url(base_url))
}

pub fn openai_provider_label(provider: Option<&str>, base_url: &str) -> &'static str {
    if provider == Some("custom") {
        return "Custom OpenAI-compatible";
    }

    let normalized = normalize_openai_base_url(base_url);
    if normalized.contains("deepseek") {
        "DeepSeek"
    } else if normalized.contains("bigmodel") {
        "GLM"
    } else if normalized.contains("minimax") {
        "MiniMax"
    } else if normalized.contains("moonshot") {
        "Moonshot"
    } else if normalized.contains("dashscope") || normalized.contains("qwen") {
        "Qwen"
    } else if normalized.contains("generativelanguage.googleapis") {
        "Gemini"
    } else {
        "OpenAI"
    }
}

pub fn model_select_items(models: &[OpenAIModelInfo], current_model: &str) -> Vec<SelectItem> {
    models
        .iter()
        .map(|model| SelectItem {
            label: model.id.clone(),
            description: model.owned_by.clone().unwrap_or_default(),
            is_current: model.id == current_model,
        })
        .collect()
}

pub fn fetch_openai_models(base_url: &str, api_key: &str) -> Result<Vec<OpenAIModelInfo>, String> {
    let base_url = normalize_openai_base_url(base_url);
    let api_key = api_key.trim();
    if api_key.is_empty() {
        return Err("API key is required".to_string());
    }

    let runtime = tokio::runtime::Runtime::new()
        .map_err(|error| format!("Failed to start async runtime: {error}"))?;
    runtime.block_on(async move {
        let response = Client::new()
            .get(models_url(&base_url))
            .bearer_auth(api_key)
            .send()
            .await
            .map_err(|error| format!("Failed to fetch /models: {error}"))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(format!("Failed to fetch /models ({status}): {body}"));
        }

        let payload = response
            .json::<Value>()
            .await
            .map_err(|error| format!("Failed to parse /models response: {error}"))?;
        parse_openai_models(payload)
    })
}

fn parse_openai_models(payload: Value) -> Result<Vec<OpenAIModelInfo>, String> {
    let items = payload
        .get("data")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("Unexpected /models response: {payload}"))?;

    let mut seen = HashSet::new();
    let mut models = Vec::new();
    for item in items {
        let Some(id) = item.get("id").and_then(Value::as_str).map(str::trim) else {
            continue;
        };
        if id.is_empty() || !seen.insert(id.to_string()) {
            continue;
        }
        let owned_by = item
            .get("owned_by")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned);
        models.push(OpenAIModelInfo {
            id: id.to_string(),
            owned_by,
        });
    }

    if models.is_empty() {
        return Err("The /models endpoint returned no usable model ids".to_string());
    }

    Ok(models)
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};
    use std::thread;

    use super::{fetch_openai_models, model_select_items, normalize_openai_base_url};

    #[test]
    fn normalize_openai_base_url_strips_known_suffixes() {
        assert_eq!(
            normalize_openai_base_url("https://example.com/v1/chat/completions"),
            "https://example.com/v1"
        );
        assert_eq!(
            normalize_openai_base_url("https://example.com/v1/models"),
            "https://example.com/v1"
        );
        assert_eq!(
            normalize_openai_base_url("https://example.com/v1/"),
            "https://example.com/v1"
        );
    }

    #[test]
    fn fetch_openai_models_uses_models_endpoint_and_deduplicates_ids() {
        let request_capture = Arc::new(Mutex::new(String::new()));
        let request_capture_for_thread = Arc::clone(&request_capture);
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind test listener");
        let addr = listener.local_addr().expect("listener addr");

        let handle = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept connection");
            let mut buffer = [0_u8; 4096];
            let bytes = stream.read(&mut buffer).expect("read request");
            *request_capture_for_thread.lock().expect("lock capture") =
                String::from_utf8_lossy(&buffer[..bytes]).into_owned();

            let body = serde_json::json!({
                "data": [
                    {"id": "alpha", "owned_by": "vendor-a"},
                    {"id": "alpha", "owned_by": "vendor-a"},
                    {"id": "beta"}
                ]
            })
            .to_string();
            write!(
                stream,
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                body.len(),
                body
            )
            .expect("write response");
        });

        let models =
            fetch_openai_models(&format!("http://{addr}/v1"), "test-key").expect("fetch models");
        handle.join().expect("server thread");

        let request = request_capture.lock().expect("lock capture").clone();
        assert!(request.starts_with("GET /v1/models HTTP/1.1"));
        assert!(request
            .to_ascii_lowercase()
            .contains("authorization: bearer test-key"));
        assert_eq!(models.len(), 2);
        assert_eq!(models[0].id, "alpha");
        assert_eq!(models[0].owned_by.as_deref(), Some("vendor-a"));
        assert_eq!(models[1].id, "beta");
        assert_eq!(models[1].owned_by, None);
    }

    #[test]
    fn model_select_items_marks_current_model() {
        let items = model_select_items(
            &[
                super::OpenAIModelInfo {
                    id: "alpha".to_string(),
                    owned_by: Some("vendor-a".to_string()),
                },
                super::OpenAIModelInfo {
                    id: "beta".to_string(),
                    owned_by: None,
                },
            ],
            "beta",
        );
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].description, "vendor-a");
        assert!(!items[0].is_current);
        assert!(items[1].is_current);
    }
}
