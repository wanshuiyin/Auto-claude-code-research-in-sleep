//! OpenAI-compatible executor client for ARIS.
//!
//! Supports any provider that implements the OpenAI `/v1/chat/completions` API:
//! OpenAI, Gemini, DeepSeek, GLM, MiniMax, Moonshot, Qwen, Yi, etc.

use std::io::{self, Write};

use crate::render::{MarkdownStreamState, TerminalRenderer};
use runtime::{
    ApiClient, ApiRequest, AssistantEvent, ContentBlock, ConversationMessage, MessageRole,
    RuntimeError, TokenUsage,
};
use serde_json::{json, Value};
use tools::ToolSpec;

use crate::{filter_tool_specs, format_tool_call_start, AllowedToolSet};

const DEFAULT_OPENAI_BASE_URL: &str = "https://api.openai.com/v1";

/// Resolve executor configuration from environment variables.
///
/// Returns `(api_key, base_url, model)` or `None` if `EXECUTOR_PROVIDER` is not set to `openai`.
pub fn resolve_openai_executor_config() -> Option<OpenAIExecutorConfig> {
    let provider = std::env::var("EXECUTOR_PROVIDER").ok()?;
    if provider != "openai" {
        return None;
    }

    let api_key = std::env::var("EXECUTOR_API_KEY")
        .or_else(|_| std::env::var("OPENAI_API_KEY"))
        .ok()
        .filter(|s| !s.is_empty())?;

    // Treat empty/whitespace-only values the same as unset, and trim otherwise
    // so accidental leading/trailing whitespace doesn't produce a malformed URL.
    let base_url = std::env::var("EXECUTOR_BASE_URL")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| DEFAULT_OPENAI_BASE_URL.to_string());

    Some(OpenAIExecutorConfig { api_key, base_url })
}

#[derive(Debug, Clone)]
pub struct OpenAIExecutorConfig {
    pub api_key: String,
    pub base_url: String,
}

pub struct OpenAIRuntimeClient {
    runtime: tokio::runtime::Runtime,
    http: reqwest::Client,
    api_key: String,
    base_url: String,
    model: String,
    enable_tools: bool,
    emit_output: bool,
    allowed_tools: Option<AllowedToolSet>,
    /// Kimi K2.5: stores reasoning_content per assistant turn for replay.
    /// Key = message index in session, Value = reasoning text.
    kimi_reasoning_cache: std::collections::HashMap<usize, String>,
}

impl OpenAIRuntimeClient {
    pub fn new(
        config: OpenAIExecutorConfig,
        model: String,
        enable_tools: bool,
        emit_output: bool,
        allowed_tools: Option<AllowedToolSet>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            runtime: tokio::runtime::Runtime::new()?,
            http: reqwest::Client::new(),
            api_key: config.api_key,
            base_url: config.base_url,
            model,
            enable_tools,
            emit_output,
            allowed_tools,
            kimi_reasoning_cache: std::collections::HashMap::new(),
        })
    }
}

impl ApiClient for OpenAIRuntimeClient {
    #[allow(clippy::too_many_lines)]
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
        let system_prompt = if request.system_prompt.is_empty() {
            None
        } else {
            Some(request.system_prompt.join("\n\n"))
        };

        let is_kimi = self.base_url.contains("moonshot");
        let messages = convert_messages_openai(
            &request.messages,
            system_prompt.as_deref(),
            is_kimi,
            &self.kimi_reasoning_cache,
        );

        let tools: Option<Value> = self.enable_tools.then(|| {
            let specs = filter_tool_specs(self.allowed_tools.as_ref());
            json!(specs
                .into_iter()
                .map(|spec| convert_tool_spec_openai(&spec))
                .collect::<Vec<_>>())
        });

        let mut body = json!({
            "model": self.model,
            "stream": true,
            "messages": messages,
        });

        if let Some(tools) = tools {
            body["tools"] = tools;
            body["tool_choice"] = json!("auto");
        }

        let url = format!(
            "{}/chat/completions",
            self.base_url.trim_end_matches('/')
        );

        self.runtime.block_on(async {
            const MAX_ATTEMPTS: u32 = 4;
            let mut attempt: u32 = 0;
            let mut response = loop {
                attempt += 1;
                if runtime::is_interrupted() {
                    runtime::clear_interrupt();
                    return Err(RuntimeError::new("interrupted by user"));
                }
                let send_result = self
                    .http
                    .post(&url)
                    .bearer_auth(&self.api_key)
                    .header("content-type", "application/json")
                    .json(&body)
                    .send()
                    .await;

                match send_result {
                    Ok(resp) => {
                        let status = resp.status();
                        // Retry on 429 (rate limit) and 5xx (server errors)
                        let retryable = status.as_u16() == 429 || status.is_server_error();
                        if resp.status().is_success() {
                            break resp;
                        }
                        if retryable && attempt < MAX_ATTEMPTS {
                            let retry_after_secs = resp
                                .headers()
                                .get("retry-after")
                                .and_then(|v| v.to_str().ok())
                                .and_then(|s| s.parse::<u64>().ok());
                            let backoff_ms = if let Some(secs) = retry_after_secs {
                                (secs * 1000).min(10_000)
                            } else {
                                (1u64 << (attempt - 1)) * 1000 // 1s, 2s, 4s
                            };
                            let body_preview = resp.text().await.unwrap_or_default();
                            let preview: String = body_preview.chars().take(160).collect();
                            eprintln!(
                                "\x1b[33m  OpenAI {status} (attempt {attempt}/{MAX_ATTEMPTS}), retrying in {}ms: {preview}\x1b[0m",
                                backoff_ms
                            );
                            let deadline =
                                std::time::Instant::now() + std::time::Duration::from_millis(backoff_ms);
                            while std::time::Instant::now() < deadline {
                                if runtime::is_interrupted() {
                                    return Err(RuntimeError::new("interrupted by user"));
                                }
                                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                            }
                            continue;
                        }
                        let body = resp.text().await.unwrap_or_else(|_| String::new());
                        return Err(RuntimeError::new(format!(
                            "OpenAI API error {status}: {body}"
                        )));
                    }
                    Err(e) => {
                        let transient = e.is_timeout() || e.is_connect() || e.is_request() || e.is_body();
                        // Build full error chain for diagnostic visibility
                        let mut chain = vec![e.to_string()];
                        let mut src: Option<&(dyn std::error::Error + 'static)> =
                            std::error::Error::source(&e);
                        let mut depth = 0;
                        while let Some(s) = src {
                            chain.push(format!("  caused by: {s}"));
                            src = s.source();
                            depth += 1;
                            if depth > 6 {
                                break;
                            }
                        }
                        let detail = chain.join("\n");
                        if transient && attempt < MAX_ATTEMPTS {
                            let backoff_ms: u64 = (1u64 << (attempt - 1)) * 1000;
                            eprintln!(
                                "\x1b[33m  OpenAI network error (attempt {attempt}/{MAX_ATTEMPTS}), retrying in {backoff_ms}ms:\n{detail}\x1b[0m"
                            );
                            let deadline = std::time::Instant::now()
                                + std::time::Duration::from_millis(backoff_ms);
                            while std::time::Instant::now() < deadline {
                                if runtime::is_interrupted() {
                                    runtime::clear_interrupt();
                                    return Err(RuntimeError::new("interrupted by user"));
                                }
                                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                            }
                            continue;
                        }
                        return Err(RuntimeError::new(format!("OpenAI request failed: {detail}")));
                    }
                }
            };

            let mut stdout = io::stdout();
            let mut sink = io::sink();
            let out: &mut dyn Write = if self.emit_output {
                &mut stdout
            } else {
                &mut sink
            };
            let renderer = TerminalRenderer::new();
            let mut markdown_stream = MarkdownStreamState::default();
            let mut events: Vec<AssistantEvent> = Vec::new();

            // Kimi: accumulate reasoning_content from this turn
            let mut current_reasoning = String::new();
            let current_msg_index = request.messages.len(); // index of the new assistant msg

            // Accumulate tool calls: index → (id, name, arguments_json)
            let mut pending_tools: Vec<(String, String, String)> = Vec::new();

            let mut stream_buf = String::new();
            let mut done = false;

            loop {
                // Check for Ctrl+C interrupt between chunks
                if runtime::is_interrupted() {
                    runtime::clear_interrupt();
                    return Err(RuntimeError::new("interrupted by user"));
                }
                let chunk = response
                    .chunk()
                    .await
                    .map_err(|e: reqwest::Error| RuntimeError::new(e.to_string()))?;
                let Some(chunk) = chunk else { break };
                let text = String::from_utf8_lossy(&chunk);
                stream_buf.push_str(&text);

                // Process complete SSE lines
                while let Some(line_end) = stream_buf.find('\n') {
                    let line = stream_buf[..line_end].trim_end_matches('\r').to_string();
                    stream_buf = stream_buf[line_end + 1..].to_string();

                    if line.is_empty() || line.starts_with(':') {
                        continue;
                    }

                    let data = if let Some(d) = line.strip_prefix("data: ") {
                        d.trim()
                    } else {
                        continue;
                    };

                    if data == "[DONE]" {
                        flush_pending_tools(
                            &mut pending_tools,
                            out,
                            &mut events,
                        )?;
                        if let Some(rendered) = markdown_stream.flush(&renderer) {
                            write!(out, "{rendered}")
                                .and_then(|()| out.flush())
                                .map_err(|e| RuntimeError::new(e.to_string()))?;
                        }
                        events.push(AssistantEvent::MessageStop);
                        done = true;
                        break;
                    }

                    let parsed: Value = match serde_json::from_str(data) {
                        Ok(v) => v,
                        Err(_) => continue,
                    };

                    // Extract usage if present (some providers send it)
                    if let Some(usage) = parsed.get("usage") {
                        let input_tokens =
                            usage.get("prompt_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                        let output_tokens = usage
                            .get("completion_tokens")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0) as u32;
                        events.push(AssistantEvent::Usage(TokenUsage {
                            input_tokens,
                            output_tokens,
                            cache_creation_input_tokens: 0,
                            cache_read_input_tokens: 0,
                        }));
                    }

                    let Some(choices) = parsed.get("choices").and_then(|c| c.as_array()) else {
                        continue;
                    };

                    for choice in choices {
                        let Some(delta) = choice.get("delta") else {
                            continue;
                        };

                        // Kimi: capture reasoning_content from delta
                        if is_kimi {
                            if let Some(rc) = delta.get("reasoning_content").and_then(|r| r.as_str()) {
                                current_reasoning.push_str(rc);
                            }
                        }

                        // Text content
                        if let Some(content) = delta.get("content").and_then(|c| c.as_str()) {
                            if !content.is_empty() {
                                if let Some(rendered) = markdown_stream.push(&renderer, content) {
                                    write!(out, "{rendered}")
                                        .and_then(|()| out.flush())
                                        .map_err(|e| RuntimeError::new(e.to_string()))?;
                                }
                                events.push(AssistantEvent::TextDelta(content.to_string()));
                            }
                        }

                        // Tool calls
                        if let Some(tool_calls) =
                            delta.get("tool_calls").and_then(|tc| tc.as_array())
                        {
                            for tc in tool_calls {
                                let idx = tc.get("index").and_then(|i| i.as_u64()).unwrap_or(0)
                                    as usize;

                                // Ensure vector is long enough
                                while pending_tools.len() <= idx {
                                    pending_tools.push((String::new(), String::new(), String::new()));
                                }

                                if let Some(id) = tc.get("id").and_then(|i| i.as_str()) {
                                    pending_tools[idx].0 = id.to_string();
                                }
                                if let Some(func) = tc.get("function") {
                                    if let Some(name) = func.get("name").and_then(|n| n.as_str()) {
                                        if !name.is_empty() {
                                            pending_tools[idx].1 = name.to_string();
                                        }
                                    }
                                    if let Some(args) =
                                        func.get("arguments").and_then(|a| a.as_str())
                                    {
                                        pending_tools[idx].2.push_str(args);
                                    }
                                }
                            }
                        }

                        // Check finish_reason
                        if let Some(reason) = choice.get("finish_reason").and_then(|r| r.as_str())
                        {
                            if reason == "tool_calls" || reason == "stop" {
                                flush_pending_tools(
                                    &mut pending_tools,
                                    out,
                                    &mut events,
                                )?;
                            }
                        }
                    }
                }

                if done {
                    break;
                }
            }

            // Ensure MessageStop
            if !events
                .iter()
                .any(|e| matches!(e, AssistantEvent::MessageStop))
            {
                // Flush any leftover tools
                for (id, name, input) in pending_tools.drain(..) {
                    if !name.is_empty() {
                        events.push(AssistantEvent::ToolUse { id, name, input });
                    }
                }
                if let Some(rendered) = markdown_stream.flush(&renderer) {
                    write!(out, "{rendered}")
                        .and_then(|()| out.flush())
                        .map_err(|e| RuntimeError::new(e.to_string()))?;
                }
                events.push(AssistantEvent::MessageStop);
            }

            // Kimi: save reasoning_content for this turn so we can replay it
            if is_kimi && !current_reasoning.is_empty() {
                self.kimi_reasoning_cache.insert(current_msg_index, current_reasoning);
            }

            Ok(events)
        })
    }
}

fn flush_pending_tools(
    pending_tools: &mut Vec<(String, String, String)>,
    out: &mut (impl Write + ?Sized),
    events: &mut Vec<AssistantEvent>,
) -> Result<(), RuntimeError> {
    for (id, name, input) in pending_tools.drain(..) {
        if !name.is_empty() {
            writeln!(out, "\n{}", format_tool_call_start(&name, &input))
                .and_then(|()| out.flush())
                .map_err(|e| RuntimeError::new(e.to_string()))?;
            events.push(AssistantEvent::ToolUse { id, name, input });
        }
    }
    Ok(())
}

// ── Message conversion ──────────────────────────────────────────────────────

fn convert_messages_openai(
    messages: &[ConversationMessage],
    system_prompt: Option<&str>,
    is_kimi: bool,
    kimi_reasoning_cache: &std::collections::HashMap<usize, String>,
) -> Vec<Value> {
    let mut result: Vec<Value> = Vec::new();

    // System message first
    if let Some(prompt) = system_prompt {
        result.push(json!({
            "role": "system",
            "content": prompt,
        }));
    }

    for (msg_idx, message) in messages.iter().enumerate() {
        match message.role {
            MessageRole::System => {
                // Already handled above
            }
            MessageRole::User => {
                let text = message
                    .blocks
                    .iter()
                    .filter_map(|b| match b {
                        ContentBlock::Text { text } => Some(text.as_str()),
                        _ => None,
                    })
                    .collect::<Vec<_>>()
                    .join("\n");

                // Also emit tool_result blocks as separate "tool" role messages
                for block in &message.blocks {
                    if let ContentBlock::ToolResult {
                        tool_use_id,
                        output,
                        ..
                    } = block
                    {
                        result.push(json!({
                            "role": "tool",
                            "tool_call_id": tool_use_id,
                            "content": output,
                        }));
                    }
                }

                if !text.is_empty() {
                    result.push(json!({
                        "role": "user",
                        "content": text,
                    }));
                }
            }
            MessageRole::Tool => {
                // Tool results
                for block in &message.blocks {
                    if let ContentBlock::ToolResult {
                        tool_use_id,
                        output,
                        ..
                    } = block
                    {
                        result.push(json!({
                            "role": "tool",
                            "tool_call_id": tool_use_id,
                            "content": output,
                        }));
                    }
                }
            }
            MessageRole::Assistant => {
                let mut content_text = String::new();
                let mut tool_calls: Vec<Value> = Vec::new();

                for block in &message.blocks {
                    match block {
                        ContentBlock::Text { text } => {
                            content_text.push_str(text);
                        }
                        ContentBlock::ToolUse { id, name, input } => {
                            tool_calls.push(json!({
                                "id": id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": input,
                                }
                            }));
                        }
                        ContentBlock::ToolResult { .. } => {}
                        ContentBlock::Thinking { .. } => {}
                    }
                }

                let mut msg = json!({ "role": "assistant" });
                if !content_text.is_empty() {
                    msg["content"] = json!(content_text);
                }
                if !tool_calls.is_empty() {
                    msg["tool_calls"] = json!(tool_calls);
                }
                // Kimi K2.5: attach cached reasoning_content for this message
                if is_kimi {
                    if let Some(reasoning) = kimi_reasoning_cache.get(&msg_idx) {
                        msg["reasoning_content"] = json!(reasoning);
                    } else {
                        msg["reasoning_content"] = json!("");
                    }
                }
                result.push(msg);
            }
        }
    }

    result
}

fn convert_tool_spec_openai(spec: &ToolSpec) -> Value {
    json!({
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use runtime::{ContentBlock, ConversationMessage, MessageRole};

    #[test]
    fn convert_messages_drops_system_role_in_messages_array() {
        // Regression: before v0.4.2 the auto-compaction continuation message
        // was role=System and was silently dropped here, erasing the summary.
        let messages = vec![
            ConversationMessage {
                role: MessageRole::System,
                blocks: vec![ContentBlock::Text {
                    text: "compaction summary".into(),
                }],
                usage: None,
            },
            ConversationMessage::user_text("next question"),
        ];
        let result = convert_messages_openai(&messages, None, false, &std::collections::HashMap::new());
        // Should contain only the User message; the System one is skipped.
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["role"], "user");
        assert!(result[0]["content"]
            .as_str()
            .unwrap_or("")
            .contains("next question"));
    }

    #[test]
    fn resolve_base_url_falls_back_for_empty_or_whitespace() {
        use std::sync::Mutex;
        // Serialize env mutation to avoid cross-test races.
        static LOCK: Mutex<()> = Mutex::new(());
        let _g = LOCK.lock().unwrap();

        let prior_provider = std::env::var("EXECUTOR_PROVIDER").ok();
        let prior_api_key = std::env::var("EXECUTOR_API_KEY").ok();
        let prior_base_url = std::env::var("EXECUTOR_BASE_URL").ok();

        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        std::env::set_var("EXECUTOR_API_KEY", "sk-test");

        // Empty string → falls back to default.
        std::env::set_var("EXECUTOR_BASE_URL", "");
        let cfg = resolve_openai_executor_config().expect("config");
        assert_eq!(cfg.base_url, DEFAULT_OPENAI_BASE_URL);

        // Whitespace-only → falls back to default.
        std::env::set_var("EXECUTOR_BASE_URL", "   ");
        let cfg = resolve_openai_executor_config().expect("config");
        assert_eq!(cfg.base_url, DEFAULT_OPENAI_BASE_URL);

        // Whitespace-padded custom URL → trimmed.
        std::env::set_var("EXECUTOR_BASE_URL", "  https://gmncode.cn  ");
        let cfg = resolve_openai_executor_config().expect("config");
        assert_eq!(cfg.base_url, "https://gmncode.cn");

        // Restore prior state to avoid polluting sibling tests.
        match prior_provider {
            Some(v) => std::env::set_var("EXECUTOR_PROVIDER", v),
            None => std::env::remove_var("EXECUTOR_PROVIDER"),
        }
        match prior_api_key {
            Some(v) => std::env::set_var("EXECUTOR_API_KEY", v),
            None => std::env::remove_var("EXECUTOR_API_KEY"),
        }
        match prior_base_url {
            Some(v) => std::env::set_var("EXECUTOR_BASE_URL", v),
            None => std::env::remove_var("EXECUTOR_BASE_URL"),
        }
    }

    #[test]
    fn convert_messages_preserves_user_role_continuation() {
        // After v0.4.2, the continuation uses User role and must survive.
        let messages = vec![
            ConversationMessage {
                role: MessageRole::User,
                blocks: vec![ContentBlock::Text {
                    text: "compaction summary".into(),
                }],
                usage: None,
            },
            ConversationMessage::user_text("next question"),
        ];
        let result = convert_messages_openai(&messages, None, false, &std::collections::HashMap::new());
        // Both User messages present.
        assert_eq!(result.len(), 2);
        assert_eq!(result[0]["role"], "user");
        assert!(result[0]["content"]
            .as_str()
            .unwrap_or("")
            .contains("compaction summary"));
        assert_eq!(result[1]["role"], "user");
    }
}
