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
use tools::{RuntimeToolSpec, ToolSpec};

use crate::{filter_tool_specs, format_tool_call_start, AllowedToolSet};

const DEFAULT_OPENAI_BASE_URL: &str = "https://api.openai.com/v1";

/// Per-turn reasoning_content size cap (chars; rough proxy for tokens ~4:1).
/// Captures up to ~8K tokens of thinking per assistant turn before truncating.
/// Long reasoning traces still go to the model in real-time; only the cache
/// entry for replay is capped, preventing the request body from ballooning
/// over many turns.
const MAX_REASONING_CHARS_PER_TURN: usize = 32_000;

/// Total reasoning_cache size cap (sum of all turns' cached reasoning,
/// bytes — implementation uses `String::len`). When exceeded, oldest
/// turns are evicted. ~32K tokens for ASCII; multi-byte chars trim
/// faster (acceptable conservative bound for non-ASCII reasoning).
const MAX_REASONING_CACHE_TOTAL_CHARS: usize = 128_000;

/// Whether this model accepts an OpenAI-style `reasoning_effort` request field.
/// Heuristic-only: matches OpenAI reasoning families (o1/o3/o4, gpt-5.5+) and
/// providers that advertise an explicit thinking/reasoner variant.
///
/// v0.4.12 P1.B: uses [`word_match`] so provider-prefixed model names like
/// `openai/o3-mini` or `proxy:o4` are recognised — `starts_with("o3")` was
/// the prior gate and missed those.
#[must_use]
fn supports_reasoning_effort(model: &str) -> bool {
    let m = model.to_ascii_lowercase();
    word_match(&m, "o1")
        || word_match(&m, "o3")
        || word_match(&m, "o4")
        || m.contains("gpt-5.5")
        || m.contains("gpt-5.6")
        || m.contains("reasoner")
        || m.contains("thinking")
}

/// v0.4.19: sanitize an upstream error body before surfacing it in a
/// `RuntimeError`. Two risks with splatting the raw body verbatim: a
/// misbehaving proxy can return a huge body (floods the terminal), and it can
/// reflect request content — including an `Authorization: Bearer …` header or
/// an `sk-…` key — straight back into the error. So we (1) truncate to a cap
/// and (2) lightly redact the two unambiguous credential shapes. Diagnostic
/// value is preserved (status + the leading error text survive).
fn sanitize_error_body(body: &str) -> String {
    const MAX_CHARS: usize = 500;
    let redacted = redact_secret_shapes(body);
    if redacted.chars().count() > MAX_CHARS {
        let head: String = redacted.chars().take(MAX_CHARS).collect();
        format!("{head}… [truncated]")
    } else {
        redacted
    }
}

/// Substring scanner (NOT token-based — API error bodies are usually compact
/// JSON like `{"error":{"message":"... sk-… ..."}}`, where the secret has no
/// surrounding whitespace). Redacts at ANY position: `sk-<key>` → `sk-***`, and
/// a `Bearer`/`bearer` immediately followed by a short delimiter run then a
/// token → `Bearer ***` (covers `Authorization: Bearer x`, `"Bearer x"`,
/// `Bearer:x`). All slicing is char-boundary-safe (`get`, `find` offsets, and
/// `len_utf8`), so no UTF-8 panic on a multibyte body.
fn redact_secret_shapes(body: &str) -> String {
    let key_char = |c: char| c.is_ascii_alphanumeric() || c == '-' || c == '_';
    let mut out = String::with_capacity(body.len() + 16);
    let mut rest = body;
    while !rest.is_empty() {
        // `sk-<key>` anywhere.
        if let Some(after) = rest.strip_prefix("sk-") {
            let klen = after.find(|c: char| !key_char(c)).unwrap_or(after.len());
            if klen >= 4 {
                out.push_str("sk-***");
                rest = &after[klen..];
                continue;
            }
        }
        // `Bearer` (case-insensitive) + a short non-token delimiter run + token.
        if rest.get(..6).is_some_and(|p| p.eq_ignore_ascii_case("bearer")) {
            let after = &rest[6..];
            let delim_len = after.find(key_char).unwrap_or(0);
            if (1..=3).contains(&delim_len) {
                let token = &after[delim_len..];
                let tlen = token
                    .find(|c: char| !(key_char(c) || c == '.'))
                    .unwrap_or(token.len());
                if tlen >= 4 {
                    out.push_str(&rest[..6]); // preserve original "Bearer" casing
                    out.push_str(&after[..delim_len]); // preserve the delimiter(s)
                    out.push_str("***");
                    rest = &token[tlen..];
                    continue;
                }
            }
        }
        // Default: copy exactly one char (keeps byte indices on boundaries).
        let ch = rest.chars().next().expect("rest non-empty");
        let n = ch.len_utf8();
        out.push_str(&rest[..n]);
        rest = &rest[n..];
    }
    out
}

/// v0.4.12 P1.C — detect a 400 response whose error body actually fingers
/// `stream_options` as an unknown/extra/unsupported field. Used by the
/// streaming chat completion call to decide whether to retry once without
/// the `stream_options.include_usage` opt-in (compat-mode proxies that
/// reject unknown body fields).
///
/// Strict match to avoid swallowing unrelated 400s:
/// 1. Try JSON-parse the body and check `error.param` starts with
///    `stream_options` (covers `stream_options.include_usage` deep path).
/// 2. Otherwise fall back to substring scan requiring **both** the
///    `stream_options` keyword and at least one rejection keyword
///    (`unknown` / `unrecognized` / `extra` / `additional` / `unsupported`)
///    in the same body.
fn is_stream_options_unknown_field_error(body: &str) -> bool {
    if body.is_empty() {
        return false;
    }
    if let Ok(json) = serde_json::from_str::<Value>(body) {
        if let Some(param) = json
            .get("error")
            .and_then(|e| e.get("param"))
            .and_then(|p| p.as_str())
        {
            if param.starts_with("stream_options") {
                return true;
            }
        }
    }
    let lower = body.to_ascii_lowercase();
    if !lower.contains("stream_options") {
        return false;
    }
    const REJECT_KEYWORDS: &[&str] = &[
        "unknown",
        "unrecognized",
        "extra",
        "additional",
        "unsupported",
        "not allowed",
        "invalid field",
    ];
    REJECT_KEYWORDS.iter().any(|kw| lower.contains(kw))
}

/// v0.4.12 P1.B — word-boundary match (treats `-`, `_`, `/`, `:` and start /
/// end of string as boundaries). Mirrors `runtime::usage::has_word` so the
/// executor's capability detection stays consistent with the pricing table.
///
/// v0.4.16 P7: forwards to the canonical [`runtime::word_match`] (this was one
/// of three verbatim copies; behavior is unchanged).
fn word_match(haystack: &str, needle: &str) -> bool {
    runtime::word_match(haystack, needle)
}

/// Whether this model EMITS `reasoning_content` blocks in the response that
/// we should cache and replay on subsequent turns. Superset of
/// [`supports_reasoning_effort`] — Kimi/Moonshot emit reasoning_content
/// without accepting reasoning_effort as a request field (the original
/// reason this cache exists), so we treat the two capabilities separately.
/// v0.4.7's hardcoded `supports_reasoning = true` shipped reasoning to
/// every provider; v0.4.9 gates it.
#[must_use]
fn supports_reasoning_content_replay(model: &str) -> bool {
    let m = model.to_ascii_lowercase();
    supports_reasoning_effort(&m)
        || m.contains("kimi")
        || m.contains("moonshot")
        || m.contains("mimo")
        || m.contains("deepseek-r1")
        || m.contains("-r1")
}

/// Effort tier sent alongside reasoning-capable models. Reads
/// `ARIS_REASONING_EFFORT` and falls back to `xhigh`. Valid values per OpenAI
/// reasoning API: `none` / `minimal` / `low` / `medium` / `high` / `xhigh`.
#[must_use]
fn reasoning_effort() -> String {
    std::env::var("ARIS_REASONING_EFFORT")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "xhigh".to_string())
}

/// Number of whole-stream restarts to attempt when chunk read fails (or
/// returns a premature EOF) before any event has been emitted. Closes
/// C6 landmine on the OpenAI executor path. Mirrors the same env knob
/// used by the Anthropic api crate. Default 2, clamped 0..=5. Parses
/// as u32 first so `ARIS_STREAM_RETRY=999` doesn't silently fall back
/// to the default (would happen with direct `u8` parse).
fn stream_retry_budget() -> u8 {
    let raw = std::env::var("ARIS_STREAM_RETRY")
        .ok()
        .and_then(|v| v.trim().parse::<u32>().ok())
        .unwrap_or(2);
    raw.min(5) as u8
}

/// Whether a reqwest::Error from `response.chunk()` represents a
/// transient mid-body failure that warrants a whole-stream restart.
fn stream_chunk_error_is_retryable(error: &reqwest::Error) -> bool {
    error.is_request()
        || error.is_connect()
        || error.is_timeout()
        || error.is_body()
        || error.is_decode()
}

/// What to do when an OpenAI-compatible stream hits a clean EOF
/// (`response.chunk()` returned `Ok(None)`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum StreamEofAction {
    /// A terminal signal arrived — break the loop and let the
    /// `Ensure MessageStop` fallback synthesize the terminal event.
    Complete,
    /// Nothing meaningful was emitted yet and restart budget remains —
    /// re-send the whole request (a proxy likely closed the connection
    /// before producing any output).
    Restart,
    /// Content was already emitted but no terminal signal arrived — the
    /// stream was cut mid-response. Hard error.
    Truncated,
}

/// Decide how to treat a clean stream EOF. Extracted as a pure function
/// so the completion-vs-truncation decision is unit-testable (the live
/// loop needs an HTTP body).
///
/// A response is **complete** when *either* terminal signal arrived:
/// - `observed_done` — the `data: [DONE]` SSE sentinel (OpenAI canonical), or
/// - `observed_finish_reason` — a non-empty `choices[].finish_reason`, which
///   the Chat Completions spec defines as the model's terminal chunk.
///
/// Many OpenAI-compatible providers (MiniMax — issue #249, and others)
/// send `finish_reason: "stop"` but never emit `[DONE]`. Requiring
/// `[DONE]` alone misreported every successful completion as a
/// truncation. We accept either signal; only when NEITHER arrived do we
/// fall back to the emitted-content heuristic (restart if nothing was
/// emitted and budget remains, otherwise treat as a genuine mid-response
/// truncation). Crucially this only relaxes how a *clean* EOF is judged —
/// reads are never stopped early at `finish_reason`, so a trailing
/// usage-only chunk (`stream_options.include_usage`) is still consumed.
fn stream_eof_action(
    observed_done: bool,
    observed_finish_reason: bool,
    nothing_emitted: bool,
    retries_remaining: u8,
) -> StreamEofAction {
    if observed_done || observed_finish_reason {
        return StreamEofAction::Complete;
    }
    if nothing_emitted && retries_remaining > 0 {
        return StreamEofAction::Restart;
    }
    StreamEofAction::Truncated
}

/// Detail of a mid-stream error envelope, if a parsed SSE `data:` object
/// carries a non-null top-level `error` (OE4 / #249). Returns `None` for a
/// normal data chunk. Only message + code/type are surfaced — never the
/// whole envelope — so nothing the provider may have reflected leaks into
/// logs. `code` is read as either a string or an integer (providers vary).
fn stream_error_detail(parsed: &Value) -> Option<String> {
    let err = parsed.get("error")?;
    if err.is_null() {
        return None;
    }
    // Some proxies send a bare string `"error": "..."`.
    if let Some(s) = err.as_str() {
        return Some(s.to_string());
    }
    let msg = err
        .get("message")
        .and_then(|m| m.as_str())
        .unwrap_or("(no message)");
    let code = err
        .get("code")
        .and_then(|c| {
            c.as_str()
                .map(str::to_string)
                .or_else(|| c.as_i64().map(|n| n.to_string()))
        })
        .or_else(|| err.get("type").and_then(|t| t.as_str()).map(str::to_string))
        .unwrap_or_default();
    if code.is_empty() {
        Some(msg.to_string())
    } else {
        Some(format!("{msg} ({code})"))
    }
}

/// The non-empty `finish_reason` of a streaming choice, if present. Read
/// independently of `delta` so a terminal choice carrying only
/// `finish_reason` (no `delta`) is still recognized (OE7 / #249).
fn choice_finish_reason(choice: &Value) -> Option<&str> {
    choice
        .get("finish_reason")
        .and_then(|r| r.as_str())
        .filter(|r| !r.is_empty())
}

/// Accumulate one streaming `tool_calls[]` delta entry into `pending`
/// (slot index → (id, name, arguments)). Tool-call fields arrive
/// incrementally across chunks: `id` is overwritten whenever the field is
/// present, a non-empty `name` is retained, and `arguments` concatenate.
///
/// v0.4.17 A5.3 (OE6) — when the delta omits `index` (`OpenAI` always sends
/// it; some compat providers may not), fall back to matching an existing
/// slot by the delta's non-empty `id` before defaulting to slot 0. This is
/// the conservative fix for the parallel-tool-call clobber: an index-less
/// continuation chunk that names an already-known call lands in that call's
/// slot instead of merging into slot 0. If the delta has no id, or the id
/// matches no existing slot, the long-standing slot-0 default applies
/// unchanged (no new-slot semantics are invented). The index-present path
/// is byte-identical to before.
fn accumulate_tool_call(pending: &mut Vec<(String, String, String)>, tc: &Value) {
    let idx = match tc.get("index").and_then(Value::as_u64) {
        Some(i) => i as usize,
        None => tc
            .get("id")
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty())
            .and_then(|id| pending.iter().position(|slot| slot.0 == id))
            .unwrap_or(0),
    };
    while pending.len() <= idx {
        pending.push((String::new(), String::new(), String::new()));
    }
    if let Some(id) = tc.get("id").and_then(|i| i.as_str()) {
        pending[idx].0 = id.to_string();
    }
    if let Some(func) = tc.get("function") {
        if let Some(name) = func.get("name").and_then(|n| n.as_str()) {
            if !name.is_empty() {
                pending[idx].1 = name.to_string();
            }
        }
        if let Some(args) = func.get("arguments").and_then(|a| a.as_str()) {
            pending[idx].2.push_str(args);
        }
    }
}

/// Parse a streaming chunk's `usage` object into a [`TokenUsage`].
///
/// v0.4.17 A5.3 (OE5) — reads the OpenAI-canonical fields first and falls
/// back to the Anthropic-style variant names some OpenAI-compatible
/// providers emit instead:
///
/// * input:  `prompt_tokens`, else `input_tokens`
/// * output: `completion_tokens`, else `output_tokens`
///
/// The canonical field wins whenever it carries a number; a missing,
/// `null`, or non-numeric canonical field falls through to the variant.
/// Cache-read stays `prompt_tokens_details.cached_tokens` only (v0.4.10
/// T35) — no variant is known for it. Absent/unparseable values are 0, as
/// before.
fn parse_stream_usage(usage: &Value) -> TokenUsage {
    let read = |canonical: &str, variant: &str| -> u32 {
        usage
            .get(canonical)
            .and_then(Value::as_u64)
            .or_else(|| usage.get(variant).and_then(Value::as_u64))
            .unwrap_or(0) as u32
    };
    let cached_tokens = usage
        .get("prompt_tokens_details")
        .and_then(|d| d.get("cached_tokens"))
        .and_then(Value::as_u64)
        .unwrap_or(0) as u32;
    TokenUsage {
        input_tokens: read("prompt_tokens", "input_tokens"),
        output_tokens: read("completion_tokens", "output_tokens"),
        cache_creation_input_tokens: 0,
        cache_read_input_tokens: cached_tokens,
    }
}

/// Extract the trimmed payload of an SSE `data:` line (OE3 / #249).
/// Tolerates both `data: {...}` (OpenAI canonical, one space) and
/// `data:{...}` (no space — W3C EventSource permits zero or one space
/// after the field colon, and some OpenAI-compatible providers omit it,
/// which the old `strip_prefix("data: ")` silently dropped). Returns
/// `None` for blank lines, comment lines, and non-`data:` field lines
/// (`event:`, `id:`, `retry:`), which the streaming loop skips.
///
/// OE8 (v0.4.17 A5.3) evaluated, skipped: skipping `event:` lines IS the
/// correct tolerance for the Chat Completions protocol — `OpenAI` never emits
/// them, no known compat provider attaches semantics to the event name, and
/// `data:` payloads are processed regardless of any preceding `event:`
/// field. Wiring an event-name parser would be dead code with no trigger
/// surface.
fn sse_data_payload(line: &str) -> Option<&str> {
    line.strip_prefix("data:").map(str::trim)
}

/// Drain all COMPLETE (newline-terminated) lines from `buf`, decoding each as
/// UTF-8 (lossy — a complete SSE line is valid UTF-8) with the trailing `\n`
/// and any `\r` stripped. Incomplete trailing bytes stay in `buf` until more
/// arrive, so a multi-byte character split across chunk boundaries is never
/// decoded mid-character. Returns the decoded lines in order.
///
/// v0.4.21 #3: boundary-safe replacement for the old per-chunk
/// `String::from_utf8_lossy(&chunk)` decode, which corrupted a CJK (3-byte) or
/// emoji (4-byte) scalar straddling a chunk boundary into `�` on both sides.
/// Mirrors the Anthropic side's discipline of feeding raw bytes to the parser
/// and decoding only complete units.
fn drain_complete_lines(buf: &mut Vec<u8>) -> Vec<String> {
    let mut lines = Vec::new();
    while let Some(nl) = buf.iter().position(|&b| b == b'\n') {
        let line_bytes: Vec<u8> = buf.drain(..=nl).collect(); // includes trailing \n
        let s = String::from_utf8_lossy(&line_bytes);
        let s = s.trim_end_matches('\n').trim_end_matches('\r');
        lines.push(s.to_string());
    }
    lines
}

/// Re-send the streaming POST when restarting a broken stream. Bounded
/// inline retry loop covers 429 / 5xx / transient network errors during
/// the restart — without it, a restart triggered by proxy instability
/// would immediately fail again if the proxy returns 429 (which is the
/// most common companion to chunk aborts). 3 attempts max with 1s/2s
/// backoff between attempts 1→2 and 2→3 (no sleep after the final
/// attempt). Mirrors the OpenAI executor's primary send-retry semantics.
async fn stream_restart_send(
    http: &reqwest::Client,
    url: &str,
    api_key: &str,
    body: &Value,
) -> Result<reqwest::Response, RuntimeError> {
    const RESTART_MAX_ATTEMPTS: u32 = 3;
    let mut attempt: u32 = 0;
    loop {
        attempt += 1;
        if runtime::is_interrupted() {
            runtime::clear_interrupt();
            return Err(RuntimeError::new("interrupted by user"));
        }
        let send_result = http
            .post(url)
            .bearer_auth(api_key)
            .header("content-type", "application/json")
            .json(body)
            .send()
            .await;
        match send_result {
            Ok(resp) => {
                let status = resp.status();
                if resp.status().is_success() {
                    return Ok(resp);
                }
                let retryable = status.as_u16() == 429 || status.is_server_error();
                if retryable && attempt < RESTART_MAX_ATTEMPTS {
                    let backoff_ms: u64 = (1u64 << (attempt - 1)) * 1000;
                    eprintln!(
                        "\x1b[33m  OpenAI restart {status} (attempt {attempt}/{RESTART_MAX_ATTEMPTS}), retrying in {backoff_ms}ms\x1b[0m"
                    );
                    tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                    continue;
                }
                let body_preview = resp.text().await.unwrap_or_default();
                return Err(RuntimeError::new(format!(
                    "OpenAI stream restart failed: {status}: {body_preview}"
                )));
            }
            Err(e) => {
                let transient = e.is_timeout() || e.is_connect() || e.is_request() || e.is_body();
                if transient && attempt < RESTART_MAX_ATTEMPTS {
                    let backoff_ms: u64 = (1u64 << (attempt - 1)) * 1000;
                    eprintln!(
                        "\x1b[33m  OpenAI restart network error (attempt {attempt}/{RESTART_MAX_ATTEMPTS}), retrying in {backoff_ms}ms: {e}\x1b[0m"
                    );
                    tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                    continue;
                }
                return Err(RuntimeError::new(format!(
                    "OpenAI stream restart failed: {e}"
                )));
            }
        }
    }
}

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
    /// v0.4.17 (RW5): MCP tools to advertise in addition to the static
    /// catalogue. Empty when no MCP servers are configured (no-MCP path is
    /// byte-for-byte identical to pre-v0.4.17). Mirrors the Anthropic path so
    /// OpenAI-family main sessions also see MCP tools.
    mcp_specs: Vec<RuntimeToolSpec>,
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
        mcp_specs: Vec<RuntimeToolSpec>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            runtime: tokio::runtime::Runtime::new()?,
            http: reqwest::Client::builder()
                .user_agent(concat!("aris/", env!("CARGO_PKG_VERSION")))
                .build()?,
            api_key: config.api_key,
            base_url: config.base_url,
            model,
            enable_tools,
            emit_output,
            allowed_tools,
            mcp_specs,
            kimi_reasoning_cache: std::collections::HashMap::new(),
        })
    }
}

impl ApiClient for OpenAIRuntimeClient {
    fn on_session_compacted(&mut self, removed_count: usize) {
        // reasoning_cache is keyed by absolute message index in the session.
        // After auto-compaction the session is replaced with [summary,
        // ...preserved_tail], so every index in the cache now points at the
        // wrong message (or no message at all). Re-populating organically
        // from subsequent assistant turns is cheaper and more correct than
        // attempting an index remap. Clear unconditionally.
        if removed_count > 0 && !self.kimi_reasoning_cache.is_empty() {
            self.kimi_reasoning_cache.clear();
        }
    }

    #[allow(clippy::too_many_lines)]
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
        let system_prompt = if request.system_prompt.is_empty() {
            None
        } else {
            Some(request.system_prompt.join("\n\n"))
        };

        // Provider-aware reasoning_content capture. v0.4.9 closes Codex
        // v0.4.7 audit L4: was hardcoded `true` for every model. We use the
        // separate `supports_reasoning_content_replay` predicate (superset
        // of reasoning_effort senders) so Kimi/Moonshot/DeepSeek-R1, which
        // emit reasoning_content but don't accept reasoning_effort as a
        // request field, still get cached and replayed.
        let supports_reasoning = supports_reasoning_content_replay(&self.model);
        let messages = convert_messages_openai(
            &request.messages,
            system_prompt.as_deref(),
            &self.kimi_reasoning_cache,
        );

        let tools: Option<Value> = self.enable_tools.then(|| {
            // v0.4.17 (RW5): static catalogue (byte-identical to pre-v0.4.17 —
            // same `convert_tool_spec_openai` over the same filtered specs)
            // followed by the cached MCP specs. When `mcp_specs` is empty (no
            // MCP servers) this is exactly the pre-v0.4.17 tools array.
            let specs = filter_tool_specs(self.allowed_tools.as_ref());
            let mut converted: Vec<Value> = specs
                .into_iter()
                .map(|spec| convert_tool_spec_openai(&spec))
                .collect();
            converted.extend(
                self.mcp_specs
                    .iter()
                    .map(convert_runtime_tool_spec_openai),
            );
            json!(converted)
        });

        let mut body = json!({
            "model": self.model,
            "stream": true,
            // v0.4.10 T35: OpenAI Chat Completions API does NOT emit
            // `usage` in streaming chunks by default. Opt in with
            // `stream_options.include_usage = true` so we can read
            // `prompt_tokens_details.cached_tokens` (automatic prefix
            // cache hits) and report token cost accurately.
            "stream_options": { "include_usage": true },
            "messages": messages,
        });

        if let Some(tools) = tools {
            body["tools"] = tools;
            body["tool_choice"] = json!("auto");
        }

        // For reasoning-capable models, attach the effort tier so the server
        // doesn't silently default to medium. Safe for o1/o3/o4/gpt-5.5/
        // thinking variants; older models would reject this field, hence the
        // explicit allow-list.
        //
        // OpenAI gate (v0.4.8): when both `tools` and `reasoning_effort` are
        // present, gpt-5.5 + the OpenAI /v1/chat/completions endpoint returns
        // 400 "Function tools with reasoning_effort are not supported …,
        // please use /v1/responses instead". The CLI executor always sends
        // tools (enable_tools = true for the agent loop), so for OpenAI's own
        // gpt-5.5 we strip reasoning_effort and warn. Third-party providers
        // that ship gpt-5.5-compatible models without this restriction (e.g.
        // some proxies) opt back in by setting ARIS_FORCE_REASONING_WITH_TOOLS=1.
        // Proper fix (Responses API support) is tracked for v0.4.9.
        let on_openai = self.base_url.contains("api.openai.com");
        let model_lower = self.model.to_ascii_lowercase();
        let openai_tool_reasoning_block = self.enable_tools
            && on_openai
            && (model_lower.contains("gpt-5.5")
                || model_lower.contains("gpt-5.6")
                || word_match(&model_lower, "o3")
                || word_match(&model_lower, "o4"));
        let force_with_tools = std::env::var("ARIS_FORCE_REASONING_WITH_TOOLS")
            .ok()
            .as_deref()
            == Some("1");
        if supports_reasoning_effort(&self.model)
            && (!openai_tool_reasoning_block || force_with_tools)
        {
            body["reasoning_effort"] = json!(reasoning_effort());
        } else if openai_tool_reasoning_block && !force_with_tools {
            // One-shot warning per process so users understand why their
            // gpt-5.5 executor is running at default reasoning. Stderr to
            // avoid polluting stdout JSON parsers.
            static WARNED: std::sync::OnceLock<()> = std::sync::OnceLock::new();
            WARNED.get_or_init(|| {
                eprintln!(
                    "\x1b[33mwarning:\x1b[0m {} as executor on OpenAI does not accept \
`reasoning_effort` when tools are enabled (OpenAI /v1/chat/completions returns 400). \
Continuing without reasoning_effort. Set ARIS_FORCE_REASONING_WITH_TOOLS=1 to override \
on a compatible third-party proxy, or use Claude/another provider as executor and keep \
{} as reviewer (LlmReview path is unaffected).",
                    self.model, self.model
                );
            });
        }

        let url = format!("{}/chat/completions", self.base_url.trim_end_matches('/'));

        self.runtime.block_on(async {
            const MAX_ATTEMPTS: u32 = 4;
            let mut attempt: u32 = 0;
            // v0.4.12 P1.C — `stream_options.include_usage:true` is sent
            // unconditionally for token-cost accuracy. Major providers
            // (OpenAI, vLLM, SGLang, OpenRouter, Together) accept it,
            // but some compatible-mode proxies reject unknown body
            // fields with 400. When that happens, retry once without
            // `stream_options` (sacrificing prefix-cache token reporting
            // for compatibility). Only fires once per request.
            let mut tried_without_stream_options = false;
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
                        let body_text = resp.text().await.unwrap_or_else(|_| String::new());

                        // v0.4.12 P1.C — proxy compatibility fallback
                        // for `stream_options`. Only fires on a real 400
                        // whose error body actually fingers
                        // `stream_options` as an unknown / extra field.
                        if status.as_u16() == 400
                            && !tried_without_stream_options
                            && is_stream_options_unknown_field_error(&body_text)
                        {
                            tried_without_stream_options = true;
                            body.as_object_mut()
                                .map(|m| m.remove("stream_options"));
                            eprintln!(
                                "\x1b[33m  OpenAI proxy rejected `stream_options.include_usage`, retrying without it (cached_tokens reporting will be skipped this turn)\x1b[0m"
                            );
                            // Don't bump attempt — this is a one-shot
                            // body-shape adjustment, not a real retry.
                            attempt = attempt.saturating_sub(1);
                            continue;
                        }

                        return Err(RuntimeError::new(format!(
                            "OpenAI API error {status}: {}",
                            sanitize_error_body(&body_text)
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

            // v0.4.21 #3: raw byte buffer (was `String`). SSE chunks are
            // accumulated as bytes and decoded only at COMPLETE line boundaries
            // (see `drain_complete_lines`) so a multi-byte UTF-8 scalar split
            // across two HTTP chunks is never decoded mid-character into `�`.
            let mut stream_buf: Vec<u8> = Vec::new();
            let mut done = false;
            // C6 v0.4.10: whole-stream restart budget for mid-body aborts
            // or premature EOF before any event has been emitted. See
            // openai_executor.rs::stream_retry_budget docstring.
            let mut stream_retries_remaining: u8 = stream_retry_budget();
            // v0.4.14 C11: per-chunk idle timeout. None = wait forever
            // (legacy behaviour, opt-in via `ARIS_STREAM_IDLE_TIMEOUT_SECS=0`).
            // On elapse the stream walks the same retry path as a
            // mid-body abort.
            let idle_timeout = api::resolve_stream_idle_timeout();
            // "Has the caller seen any meaningful output yet?" If true,
            // we cannot restart — there's no resume primitive in
            // OpenAI's API and re-sending would duplicate output.
            let nothing_emitted_yet = |events: &Vec<AssistantEvent>,
                                       pending_tools: &Vec<(String, String, String)>,
                                       current_reasoning: &String|
             -> bool {
                events.is_empty()
                    && pending_tools.is_empty()
                    && current_reasoning.is_empty()
            };
            // `[DONE]` sentinel — distinguishes "stream completed normally"
            // from "proxy closed connection before sending [DONE]".
            let mut observed_done = false;
            // #249 v0.4.15: a non-empty `choices[].finish_reason` is the
            // Chat Completions spec's terminal-chunk marker and is an
            // equally authoritative completion signal. OpenAI-compatible
            // providers (MiniMax etc.) often send it but never emit
            // `[DONE]`; without this a clean EOF was misreported as a
            // truncation. We still read until EOF (never stop early at
            // finish_reason) so a trailing usage-only chunk isn't lost.
            let mut observed_finish_reason = false;

            loop {
                // Check for Ctrl+C interrupt between chunks
                if runtime::is_interrupted() {
                    runtime::clear_interrupt();
                    return Err(RuntimeError::new("interrupted by user"));
                }
                // v0.4.14 C11 — wrap chunk read in tokio::time::timeout so
                // a hung upstream proxy can't stall this loop forever.
                // Idle elapse is treated equivalently to a premature
                // EOF / mid-body abort and walks through the same
                // retry path.
                let chunk_future = response.chunk();
                let chunk_result = match idle_timeout {
                    Some(dur) => match tokio::time::timeout(dur, chunk_future).await {
                        Ok(inner) => inner,
                        Err(_elapsed) => {
                            if nothing_emitted_yet(
                                &events,
                                &pending_tools,
                                &current_reasoning,
                            ) && stream_retries_remaining > 0
                            {
                                stream_retries_remaining -= 1;
                                eprintln!(
                                    "\x1b[33m  OpenAI stream restart (idle timeout {}s, {} attempt(s) left)\x1b[0m",
                                    dur.as_secs(),
                                    stream_retries_remaining
                                );
                                response = stream_restart_send(
                                    &self.http,
                                    &url,
                                    &self.api_key,
                                    &body,
                                )
                                .await?;
                                stream_buf.clear();
                                done = false;
                                continue;
                            }
                            return Err(RuntimeError::new(format!(
                                "OpenAI stream idle timeout ({}s, retries exhausted or partial output already emitted)",
                                dur.as_secs()
                            )));
                        }
                    },
                    None => chunk_future.await,
                };
                let chunk = match chunk_result {
                    Ok(Some(c)) => c,
                    Ok(None) => {
                        // Clean EOF. Decide complete / restart / truncated
                        // via the pure `stream_eof_action` helper. A
                        // response is complete if EITHER `[DONE]` OR a
                        // non-empty `finish_reason` was seen (#249: MiniMax
                        // & other compat providers send finish_reason but
                        // not `[DONE]`); only with neither do we restart
                        // (nothing emitted yet) or hard-error (truncated).
                        match stream_eof_action(
                            observed_done,
                            observed_finish_reason,
                            nothing_emitted_yet(&events, &pending_tools, &current_reasoning),
                            stream_retries_remaining,
                        ) {
                            StreamEofAction::Complete => break,
                            StreamEofAction::Restart => {
                                stream_retries_remaining -= 1;
                                eprintln!(
                                    "\x1b[33m  OpenAI stream restart (premature EOF, {} attempt(s) left)\x1b[0m",
                                    stream_retries_remaining
                                );
                                response = stream_restart_send(
                                    &self.http,
                                    &url,
                                    &self.api_key,
                                    &body,
                                )
                                .await?;
                                stream_buf.clear();
                                done = false;
                                continue;
                            }
                            StreamEofAction::Truncated => {
                                // Returning Err prevents `Ensure MessageStop`
                                // below from synthesizing success out of a
                                // half-finished response.
                                return Err(RuntimeError::new(
                                    "OpenAI stream ended prematurely without [DONE] sentinel \
                                     or finish_reason (retries exhausted or partial output \
                                     already emitted)"
                                        .to_string(),
                                ));
                            }
                        }
                    }
                    Err(error) => {
                        if nothing_emitted_yet(&events, &pending_tools, &current_reasoning)
                            && stream_retries_remaining > 0
                            && stream_chunk_error_is_retryable(&error)
                        {
                            stream_retries_remaining -= 1;
                            eprintln!(
                                "\x1b[33m  OpenAI stream restart (body abort: {error}, {} attempt(s) left)\x1b[0m",
                                stream_retries_remaining
                            );
                            response = stream_restart_send(
                                &self.http,
                                &url,
                                &self.api_key,
                                &body,
                            )
                            .await?;
                            stream_buf.clear();
                            done = false;
                            continue;
                        }
                        return Err(RuntimeError::new(error.to_string()));
                    }
                };
                // v0.4.21 #3: accumulate RAW bytes; decode only COMPLETE
                // (newline-terminated) lines via `drain_complete_lines`. A
                // multi-byte UTF-8 scalar (CJK = 3 bytes, emoji = 4) whose bytes
                // straddle a chunk boundary used to be `from_utf8_lossy`'d into
                // `�` on BOTH sides when each chunk was decoded independently.
                // The helper keeps the incomplete trailing bytes in `stream_buf`
                // until the next chunk arrives, so a split character is never
                // decoded mid-character. A complete SSE line is valid UTF-8
                // (JSON), so lossy decoding of a whole line is effectively
                // lossless.
                stream_buf.extend_from_slice(&chunk);

                // Process complete SSE lines
                for line in drain_complete_lines(&mut stream_buf) {

                    if line.is_empty() || line.starts_with(':') {
                        continue;
                    }

                    // OE3 (#249): tolerate `data:{...}` without the space
                    // after the colon (some OpenAI-compatible providers omit
                    // it). Non-`data:` field lines (event:/id:/retry:) → skip.
                    let Some(data) = sse_data_payload(&line) else {
                        continue;
                    };

                    if data == "[DONE]" {
                        observed_done = true;
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

                    // OE4 (#249): a mid-stream error envelope carries no
                    // `choices`, so it would be silently dropped by the
                    // `choices` guard below. That is doubly dangerous now
                    // that a prior `finish_reason` marks the stream
                    // "complete" on EOF — an error chunk arriving after a
                    // finish_reason would otherwise be misjudged as
                    // success. Surface it as a hard error.
                    if let Some(detail) = stream_error_detail(&parsed) {
                        return Err(RuntimeError::new(format!(
                            "OpenAI stream returned a mid-stream error: {detail}"
                        )));
                    }

                    // Extract usage if present (some providers send it).
                    // v0.4.10 T35: read OpenAI's automatic prefix-cache hit
                    // counter from `usage.prompt_tokens_details.cached_tokens`
                    // so /cost and the usage tracker reflect cache savings.
                    // OpenAI's API automatically caches request prefixes
                    // >1024 tokens — the cached portion is billed at a
                    // discount, and previously aris-code threw the number
                    // away (always 0). Anthropic-style cache_creation
                    // doesn't have a direct equivalent on OpenAI; we leave
                    // it 0 (their automatic write-on-first-use is not
                    // reported as a separate quantity).
                    // v0.4.17 A5.3 (OE5): parsing extracted to the pure
                    // `parse_stream_usage`, which also accepts the
                    // input_tokens/output_tokens variant field names.
                    if let Some(usage) = parsed.get("usage") {
                        events.push(AssistantEvent::Usage(parse_stream_usage(usage)));
                    }

                    let Some(choices) = parsed.get("choices").and_then(|c| c.as_array()) else {
                        continue;
                    };

                    for choice in choices {
                        // OE7 (#249): read finish_reason BEFORE touching
                        // `delta`. Some providers emit a terminal choice
                        // carrying only `finish_reason` and no `delta`; the
                        // old `let Some(delta) = … else continue` skipped
                        // such a choice entirely, so its finish_reason was
                        // never recorded and the EOF completion check below
                        // would not fire. Capture it here, flush after the
                        // delta block (a chunk may carry both tool_calls and
                        // finish_reason — flush last so final args land).
                        let finish_reason = choice_finish_reason(choice);
                        if finish_reason.is_some() {
                            observed_finish_reason = true;
                        }

                        if let Some(delta) = choice.get("delta") {
                            // Kimi: capture reasoning_content from delta
                            if supports_reasoning {
                                if let Some(rc) =
                                    delta.get("reasoning_content").and_then(|r| r.as_str())
                                {
                                    current_reasoning.push_str(rc);
                                }
                            }

                            // Text content
                            if let Some(content) = delta.get("content").and_then(|c| c.as_str()) {
                                if !content.is_empty() {
                                    if let Some(rendered) =
                                        markdown_stream.push(&renderer, content)
                                    {
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
                                    accumulate_tool_call(&mut pending_tools, tc);
                                }
                            }
                        }

                        // OE2 (#249): flush on ANY non-empty finish_reason,
                        // not just stop/tool_calls. Non-standard terminal
                        // values (length / content_filter / max_output /
                        // sensitive …) are emitted by some compat providers.
                        // Not logical ToolUse loss-prevention — the
                        // `Ensure MessageStop` fallback below would still
                        // drain leftover pending_tools into events — but
                        // flushing here keeps in-stream ordering AND the
                        // per-tool terminal rendering (`flush_pending_tools`
                        // prints the tool-call start line; the fallback
                        // drain does not).
                        if let Some(reason) = finish_reason {
                            if reason == "length" || reason == "content_filter" {
                                eprintln!(
                                    "\x1b[33m  OpenAI stream finished with reason='{reason}' — output may be truncated or filtered\x1b[0m"
                                );
                            }
                            flush_pending_tools(&mut pending_tools, out, &mut events)?;
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

            // Kimi: save reasoning_content for this turn so we can replay it.
            // v0.4.9 L4: capped at MAX_REASONING_CHARS_PER_TURN per entry +
            // MAX_REASONING_CACHE_TOTAL_CHARS across all entries (oldest
            // evicted first) so the request body doesn't balloon over a
            // long session.
            if supports_reasoning && !current_reasoning.is_empty() {
                if current_reasoning.chars().count() > MAX_REASONING_CHARS_PER_TURN {
                    // UTF-8-safe truncate at char boundary
                    let byte_idx = current_reasoning
                        .char_indices()
                        .nth(MAX_REASONING_CHARS_PER_TURN)
                        .map(|(i, _)| i)
                        .unwrap_or(current_reasoning.len());
                    current_reasoning.truncate(byte_idx);
                }
                self.kimi_reasoning_cache
                    .insert(current_msg_index, current_reasoning);

                // Enforce total-size cap by evicting oldest entries (smallest
                // msg_idx) until we're back under MAX_REASONING_CACHE_TOTAL_CHARS.
                while self
                    .kimi_reasoning_cache
                    .values()
                    .map(String::len)
                    .sum::<usize>()
                    > MAX_REASONING_CACHE_TOTAL_CHARS
                {
                    let Some(oldest_idx) =
                        self.kimi_reasoning_cache.keys().copied().min()
                    else {
                        break;
                    };
                    if oldest_idx == current_msg_index {
                        // Never evict the entry we just inserted; if total cap is
                        // smaller than a single turn, accept the overflow (the
                        // per-turn truncate already bounded it).
                        break;
                    }
                    self.kimi_reasoning_cache.remove(&oldest_idx);
                }
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
                // Attach cached reasoning_content for providers that support
                // thinking mode (Kimi, Xiaomi MiMo, DeepSeek R1, etc.)
                if let Some(reasoning) = kimi_reasoning_cache.get(&msg_idx) {
                    if !reasoning.is_empty() {
                        msg["reasoning_content"] = json!(reasoning);
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

/// v0.4.17 (RW5): `OpenAI` tool-spec JSON for a runtime (MCP) spec. Produces
/// the exact same `{type, function:{name, description, parameters}}` shape as
/// `convert_tool_spec_openai` so MCP tools are advertised identically to static
/// ones.
fn convert_runtime_tool_spec_openai(spec: &RuntimeToolSpec) -> Value {
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

    // v0.4.19: error bodies surfaced from an OpenAI-compatible upstream are
    // truncated + credential-redacted before reaching the user-visible error.
    #[test]
    fn sanitize_error_body_redacts_and_truncates() {
        // sk- key with surrounding whitespace → redacted, diagnostic text kept.
        let spaced = r#"{"error":{"message":"bad key sk-ABCDEF1234567890 used"}}"#;
        let s = sanitize_error_body(spaced);
        assert!(s.contains("sk-***") && !s.contains("sk-ABCDEF1234567890"), "{s}");
        assert!(s.contains("error") && s.contains("bad key"), "diagnostic text kept: {s}");

        // COMPACT JSON (the common API-error shape) — secret has no surrounding
        // whitespace. A token-based scanner would miss these; the substring
        // scanner must catch them (codex NO-GO #e).
        let compact_json = r#"{"api_key":"sk-ABCDEF1234567890"}"#;
        let cj = sanitize_error_body(compact_json);
        assert!(cj.contains("sk-***") && !cj.contains("ABCDEF1234567890"), "{cj}");

        let kv = "OPENAI_API_KEY=sk-ABCDEF1234567890";
        let k = sanitize_error_body(kv);
        assert!(k.contains("sk-***") && !k.contains("ABCDEF1234567890"), "{k}");

        // Bearer token, both spaced and compact-JSON forms.
        let bearer_spaced = "rejected: Authorization: Bearer SECRETTOKEN99x";
        let bs = sanitize_error_body(bearer_spaced);
        assert!(bs.contains("Bearer ***") && !bs.contains("SECRETTOKEN99x"), "{bs}");

        let bearer_json = r#"{"Authorization":"Bearer SECRETTOKEN99x"}"#;
        let bj = sanitize_error_body(bearer_json);
        assert!(bj.contains("Bearer ***") && !bj.contains("SECRETTOKEN99x"), "{bj}");

        // Short, clean body is passed through unchanged.
        let clean = r#"{"error":{"type":"invalid_request_error"}}"#;
        assert_eq!(sanitize_error_body(clean), clean);

        // A huge reflected body is capped (no terminal flood).
        let huge = "x".repeat(5000);
        let t = sanitize_error_body(&huge);
        assert!(t.ends_with("… [truncated]") && t.chars().count() < 600, "len={}", t.chars().count());
    }

    // Env-mutating tests below serialize via the crate-wide
    // `crate::env_test_guard()` (codex Phase-0 gap #1) so they cannot race the
    // config.rs env tests on EXECUTOR_*/OPENAI_API_KEY in a parallel run.

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
        let result = convert_messages_openai(&messages, None, &std::collections::HashMap::new());
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
        // Crate-wide env_test_guard() (not a per-test lock) so this cannot race
        // the char_resolve_* / config.rs tests on EXECUTOR_*/OPENAI_API_KEY
        // (codex Phase-0 gap #1).
        let _g = crate::env_test_guard();

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
        let result = convert_messages_openai(&messages, None, &std::collections::HashMap::new());
        // Both User messages present.
        assert_eq!(result.len(), 2);
        assert_eq!(result[0]["role"], "user");
        assert!(result[0]["content"]
            .as_str()
            .unwrap_or("")
            .contains("compaction summary"));
        assert_eq!(result[1]["role"], "user");
    }

    // v0.4.13 regression — v0.4.12 P1.B promoted the o-series detector
    // from a bare `contains()` to a word-boundary check so that
    // provider-prefixed (`openai/o3-mini`) and proxy-prefixed
    // (`proxy:o4-preview`) names still resolve, but mid-word collisions
    // (`foo-o3bar`, `o32-mini`) don't accidentally route. Pin every
    // boundary case so a future tightening of the boundary set can't
    // silently flip executor capability detection.
    #[test]
    fn word_match_handles_provider_prefixes() {
        // Provider/proxy prefixed forms — `/` and `:` are valid boundaries.
        assert!(word_match("openai/o3-mini", "o3"));
        assert!(word_match("proxy:o4-preview", "o4"));
        // `-` boundary at the start.
        assert!(word_match("o1-mini", "o1"));
        // Mid-word `o3` substring (no boundary before) — must NOT match.
        assert!(!word_match("foo-o3bar", "o3"));
        // Digit-suffix collision (`o32-mini` contains "o3" but the next
        // byte is a digit, not a boundary char) — must NOT match.
        assert!(!word_match("o32-mini", "o3"));
        // Trailing boundary on the needle.
        assert!(word_match("o3-", "o3"));
        // Exact-equality (start-of-string + end-of-string boundaries).
        assert!(word_match("o3", "o3"));
    }

    // v0.4.13 regression — v0.4.12 added the JSON-first stream_options
    // rejection detector. The classifier has three branches and a fail-
    // safe; pin all of them so a refactor can't silently relax detection.
    #[test]
    fn is_stream_options_unknown_field_error_classification() {
        // JSON path: error.param == "stream_options" (exact match).
        assert!(is_stream_options_unknown_field_error(
            r#"{"error":{"message":"x","param":"stream_options","type":"invalid_request_error"}}"#
        ));
        // JSON path: error.param starts_with "stream_options" (deep field
        // like `stream_options.include_usage`).
        assert!(is_stream_options_unknown_field_error(
            r#"{"error":{"param":"stream_options.include_usage","message":"x"}}"#
        ));
        // Text path: body contains "stream_options" + a reject keyword.
        assert!(is_stream_options_unknown_field_error(
            "{\"error\": \"unknown field stream_options\"}"
        ));
        // Negative: 400 about something else entirely.
        assert!(!is_stream_options_unknown_field_error(
            r#"{"error":{"message":"invalid api key","type":"auth_error"}}"#
        ));
        // Negative: contains "stream_options" but no reject keyword.
        assert!(!is_stream_options_unknown_field_error(
            r#"{"error":{"message":"stream_options ok"}}"#
        ));
        // Negative: empty body must not classify (fail-safe).
        assert!(!is_stream_options_unknown_field_error(""));
    }

    // #249 v0.4.15: clean-EOF completion-vs-truncation truth table.
    // Mirrors api/src/client.rs should_retry_on_premature_eof_truth_table.
    // Columns: observed_done × observed_finish_reason × nothing_emitted ×
    //          retries_remaining → StreamEofAction.
    #[test]
    fn stream_eof_action_truth_table() {
        use StreamEofAction::*;

        // --- Completion via [DONE] (legacy / OpenAI canonical) ---
        // [DONE] seen → Complete regardless of finish_reason / emitted / retries.
        assert_eq!(stream_eof_action(true, false, false, 2), Complete);
        assert_eq!(stream_eof_action(true, false, true, 0), Complete);
        assert_eq!(stream_eof_action(true, true, false, 2), Complete);

        // --- Completion via finish_reason, NO [DONE] (#249 MiniMax core) ---
        // finish_reason seen + content emitted + clean EOF → Complete, NOT error.
        assert_eq!(stream_eof_action(false, true, false, 2), Complete);
        // finish_reason seen even with retries exhausted → still Complete.
        assert_eq!(stream_eof_action(false, true, false, 0), Complete);
        // finish_reason seen and nothing emitted (terminal-only choice) →
        // Complete (don't waste a restart on a finished-but-empty response).
        assert_eq!(stream_eof_action(false, true, true, 2), Complete);

        // --- Genuine truncation: NEITHER signal, content already emitted ---
        // Cannot restart (would duplicate output) → Truncated (hard error).
        assert_eq!(stream_eof_action(false, false, false, 2), Truncated);
        assert_eq!(stream_eof_action(false, false, false, 0), Truncated);

        // --- Proxy abort before any output: NEITHER signal, nothing emitted ---
        // Restart if budget remains, else Truncated.
        assert_eq!(stream_eof_action(false, false, true, 2), Restart);
        assert_eq!(stream_eof_action(false, false, true, 1), Restart);
        assert_eq!(stream_eof_action(false, false, true, 0), Truncated);
    }

    // OE4 (#249): mid-stream error envelope detection.
    #[test]
    fn stream_error_detail_classification() {
        use serde_json::json;
        // Normal data chunk → None.
        assert_eq!(
            stream_error_detail(&json!({"choices": [{"delta": {"content": "hi"}}]})),
            None
        );
        // No error key → None.
        assert_eq!(stream_error_detail(&json!({"usage": {"prompt_tokens": 1}})), None);
        // Explicit null error → None (some providers send `error: null`).
        assert_eq!(stream_error_detail(&json!({"error": null})), None);
        // Error object with message + string code.
        assert_eq!(
            stream_error_detail(
                &json!({"error": {"message": "rate limited", "code": "rate_limit"}})
            ),
            Some("rate limited (rate_limit)".to_string())
        );
        // Error object with integer code (providers vary).
        assert_eq!(
            stream_error_detail(&json!({"error": {"message": "bad", "code": 400}})),
            Some("bad (400)".to_string())
        );
        // Error object with `type` fallback when no `code`.
        assert_eq!(
            stream_error_detail(
                &json!({"error": {"message": "nope", "type": "invalid_request_error"}})
            ),
            Some("nope (invalid_request_error)".to_string())
        );
        // Error object message only.
        assert_eq!(
            stream_error_detail(&json!({"error": {"message": "boom"}})),
            Some("boom".to_string())
        );
        // Bare string error (some proxies).
        assert_eq!(
            stream_error_detail(&json!({"error": "upstream exploded"})),
            Some("upstream exploded".to_string())
        );
        // Error object with neither message nor code → placeholder.
        assert_eq!(
            stream_error_detail(&json!({"error": {"foo": "bar"}})),
            Some("(no message)".to_string())
        );
    }

    // OE7 (#249): finish_reason read independently of `delta`.
    #[test]
    fn choice_finish_reason_handles_delta_less_and_empty() {
        use serde_json::json;
        // Terminal choice with finish_reason and NO delta — the core OE7
        // case: must still be recognized.
        assert_eq!(
            choice_finish_reason(&json!({"finish_reason": "stop"})),
            Some("stop")
        );
        // Non-standard terminal value still recognized.
        assert_eq!(
            choice_finish_reason(&json!({"finish_reason": "length"})),
            Some("length")
        );
        // finish_reason alongside a delta.
        assert_eq!(
            choice_finish_reason(&json!({"delta": {"content": "x"}, "finish_reason": "tool_calls"})),
            Some("tool_calls")
        );
        // Empty string finish_reason → None (not a terminal signal).
        assert_eq!(choice_finish_reason(&json!({"finish_reason": ""})), None);
        // Null finish_reason (mid-stream chunk) → None.
        assert_eq!(
            choice_finish_reason(&json!({"delta": {"content": "x"}, "finish_reason": null})),
            None
        );
        // Absent finish_reason → None.
        assert_eq!(choice_finish_reason(&json!({"delta": {"content": "x"}})), None);
    }

    // Tool-call delta accumulation across chunks.
    #[test]
    fn accumulate_tool_call_builds_and_concatenates() {
        use serde_json::json;
        let mut pending: Vec<(String, String, String)> = Vec::new();

        // First delta: id + name + partial args.
        accumulate_tool_call(
            &mut pending,
            &json!({"index": 0, "id": "call_1", "function": {"name": "search", "arguments": "{\"q\":"}}),
        );
        // Second delta (same index): only more args — id/name must persist,
        // args concatenate.
        accumulate_tool_call(
            &mut pending,
            &json!({"index": 0, "function": {"arguments": "\"rust\"}"}}),
        );
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].0, "call_1");
        assert_eq!(pending[0].1, "search");
        assert_eq!(pending[0].2, "{\"q\":\"rust\"}");

        // A second tool at index 1 must not clobber index 0.
        accumulate_tool_call(
            &mut pending,
            &json!({"index": 1, "id": "call_2", "function": {"name": "fetch", "arguments": "{}"}}),
        );
        assert_eq!(pending.len(), 2);
        assert_eq!(pending[0].0, "call_1"); // unchanged
        assert_eq!(pending[1].0, "call_2");
        assert_eq!(pending[1].1, "fetch");
        assert_eq!(pending[1].2, "{}");

        // Missing index with an UNKNOWN id still defaults to slot 0 (OpenAI
        // always sends index; the v0.4.17 OE6 id-fallback only redirects to
        // an EXISTING slot whose id matches — it never invents a new slot).
        let mut p2: Vec<(String, String, String)> = Vec::new();
        accumulate_tool_call(&mut p2, &json!({"id": "x", "function": {"name": "n"}}));
        assert_eq!(p2.len(), 1);
        assert_eq!(p2[0].0, "x");
    }

    // ---------------------------------------------------------------
    // v0.4.17 A5.3 (OE6) — the Phase 0 characterization baseline
    // (`char_accumulate_tool_call_missing_index_merges_into_slot_zero`) was
    // DELIBERATELY FLIPPED here: an index-less delta now falls back to
    // matching an existing slot by `id` before defaulting to slot 0. The
    // slot-0 default is preserved for deltas whose id is unknown or absent
    // (no new-slot semantics), and the index-present path is unchanged.
    #[test]
    fn accumulate_tool_call_missing_index_falls_back_to_id_match() {
        use serde_json::json;

        // --- id HIT: index-less continuation routed to the matching slot ---
        let mut pending: Vec<(String, String, String)> = Vec::new();
        accumulate_tool_call(
            &mut pending,
            &json!({"index": 0, "id": "call_A", "function": {"name": "alpha", "arguments": "{\"a\":1}"}}),
        );
        accumulate_tool_call(
            &mut pending,
            &json!({"index": 1, "id": "call_B", "function": {"name": "beta", "arguments": "{\"b\":"}}),
        );
        // A continuation for call_B arrives WITHOUT an index. Pre-OE6 this
        // merged into slot 0 (clobbering call_A); now the id match routes it
        // into slot 1.
        accumulate_tool_call(
            &mut pending,
            &json!({"id": "call_B", "function": {"arguments": "2}"}}),
        );
        assert_eq!(pending.len(), 2, "id-matched delta must not grow pending");
        assert_eq!(
            (pending[0].0.as_str(), pending[0].1.as_str(), pending[0].2.as_str()),
            ("call_A", "alpha", "{\"a\":1}"),
            "slot 0 must be untouched by the index-less call_B continuation"
        );
        assert_eq!(
            (pending[1].0.as_str(), pending[1].1.as_str(), pending[1].2.as_str()),
            ("call_B", "beta", "{\"b\":2}"),
            "call_B's arguments must concatenate in ITS slot, not slot 0"
        );

        // --- id MISS: unknown id keeps the long-standing slot-0 default ---
        let mut miss: Vec<(String, String, String)> = Vec::new();
        accumulate_tool_call(
            &mut miss,
            &json!({"index": 0, "id": "call_A", "function": {"name": "alpha", "arguments": "{\"a\":1}"}}),
        );
        accumulate_tool_call(
            &mut miss,
            &json!({"id": "call_NEW", "function": {"name": "nu", "arguments": "{\"n\":3}"}}),
        );
        assert_eq!(miss.len(), 1, "unknown-id delta must NOT open a new slot");
        assert_eq!(miss[0].0, "call_NEW", "slot-0 default: id overwritten");
        assert_eq!(miss[0].1, "nu");
        assert_eq!(miss[0].2, "{\"a\":1}{\"n\":3}");

        // --- no id at all: slot-0 default unchanged ---
        let mut no_id: Vec<(String, String, String)> = Vec::new();
        accumulate_tool_call(
            &mut no_id,
            &json!({"index": 0, "id": "call_A", "function": {"name": "alpha", "arguments": "x"}}),
        );
        accumulate_tool_call(&mut no_id, &json!({"function": {"arguments": "y"}}));
        assert_eq!(no_id.len(), 1);
        assert_eq!(no_id[0].2, "xy");

        // --- empty-string id never matches the empty-id padding slots ---
        let mut padded: Vec<(String, String, String)> = Vec::new();
        // index 1 first → slot 0 is an empty-id padding slot.
        accumulate_tool_call(
            &mut padded,
            &json!({"index": 1, "id": "call_B", "function": {"name": "beta", "arguments": "b"}}),
        );
        accumulate_tool_call(&mut padded, &json!({"id": "", "function": {"arguments": "z"}}));
        assert_eq!(padded.len(), 2);
        assert_eq!(padded[0].2, "z", "empty id falls to slot 0 by default, not by match");
        assert_eq!(padded[1].2, "b");
    }

    // v0.4.17 A5.3 (OE5): usage parsing — canonical fields, variant
    // fallback, and precedence.
    #[test]
    fn parse_stream_usage_reads_canonical_and_variant_fields() {
        use serde_json::json;

        // Canonical OpenAI fields (pre-OE5 behavior, must be unchanged).
        let u = parse_stream_usage(&json!({
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 4}
        }));
        assert_eq!(u.input_tokens, 10);
        assert_eq!(u.output_tokens, 20);
        assert_eq!(u.cache_read_input_tokens, 4);
        assert_eq!(u.cache_creation_input_tokens, 0);

        // OE5 core: variant names only (input_tokens/output_tokens).
        let u = parse_stream_usage(&json!({"input_tokens": 7, "output_tokens": 9}));
        assert_eq!(u.input_tokens, 7);
        assert_eq!(u.output_tokens, 9);
        assert_eq!(u.cache_read_input_tokens, 0);

        // Canonical wins when both are present.
        let u = parse_stream_usage(&json!({
            "prompt_tokens": 10, "input_tokens": 99,
            "completion_tokens": 20, "output_tokens": 99
        }));
        assert_eq!(u.input_tokens, 10);
        assert_eq!(u.output_tokens, 20);

        // A null/non-numeric canonical field falls through to the variant.
        let u = parse_stream_usage(&json!({
            "prompt_tokens": null, "input_tokens": 7,
            "completion_tokens": "n/a", "output_tokens": 9
        }));
        assert_eq!(u.input_tokens, 7);
        assert_eq!(u.output_tokens, 9);

        // Nothing usable → all zeros (pre-OE5 behavior, unchanged).
        let u = parse_stream_usage(&json!({}));
        assert_eq!(u.input_tokens, 0);
        assert_eq!(u.output_tokens, 0);
        assert_eq!(u.cache_read_input_tokens, 0);
    }

    // OE3 (#249): SSE `data:` payload parsing tolerates missing space.
    #[test]
    fn sse_data_payload_tolerates_missing_space() {
        // Canonical OpenAI form (one space).
        assert_eq!(sse_data_payload("data: {\"x\":1}"), Some("{\"x\":1}"));
        // No space after colon (OE3 core — some compat providers).
        assert_eq!(sse_data_payload("data:{\"x\":1}"), Some("{\"x\":1}"));
        // [DONE] sentinel both ways.
        assert_eq!(sse_data_payload("data: [DONE]"), Some("[DONE]"));
        assert_eq!(sse_data_payload("data:[DONE]"), Some("[DONE]"));
        // Extra surrounding whitespace is trimmed.
        assert_eq!(sse_data_payload("data:   spaced  "), Some("spaced"));
        // Empty payload (harmless — serde parse fails downstream, skipped).
        assert_eq!(sse_data_payload("data:"), Some(""));
        // Non-data field lines → None (loop skips them).
        assert_eq!(sse_data_payload("event: message"), None);
        assert_eq!(sse_data_payload("id: 42"), None);
        assert_eq!(sse_data_payload("retry: 1000"), None);
        // A field that merely starts with "data" but isn't "data:" → None.
        assert_eq!(sse_data_payload("database: x"), None);
        // Blank / comment lines → None.
        assert_eq!(sse_data_payload(""), None);
        assert_eq!(sse_data_payload(": keep-alive"), None);
    }

    // v0.4.21 #3: drain_complete_lines must never decode a multi-byte UTF-8
    // scalar that straddles a chunk boundary as `�`. The old per-chunk
    // `from_utf8_lossy(&chunk)` corrupted CJK (3-byte) and emoji (4-byte)
    // characters split across chunk boundaries on both sides.
    #[test]
    fn drain_complete_lines_cjk_split_across_chunks() {
        // `data: {"x":"你好"}\n` — split the FIRST push in the MIDDLE of the
        // 3-byte '你' (U+4F60 = E4 BD A0). We cut one byte into '你' so the
        // chunk boundary lands mid-character.
        let full: Vec<u8> = "data: {\"x\":\"你好\"}\n".as_bytes().to_vec();
        let prefix = "data: {\"x\":\"".len(); // byte offset where '你' begins
        let split = prefix + 1; // one byte into the 3-byte '你'
        let (first, second) = full.split_at(split);

        let mut buf: Vec<u8> = Vec::new();
        buf.extend_from_slice(first);
        // No newline yet → no line emitted, and the partial multi-byte char
        // stays buffered (nothing decoded).
        assert!(
            drain_complete_lines(&mut buf).is_empty(),
            "no newline yet → no line emitted"
        );

        buf.extend_from_slice(second);
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(lines.len(), 1, "one complete line after the newline arrives");
        assert_eq!(lines[0], "data: {\"x\":\"你好\"}");
        assert!(
            !lines[0].contains('\u{FFFD}'),
            "no replacement char in reassembled CJK line: {}",
            lines[0]
        );
        assert!(buf.is_empty(), "no leftover bytes after a clean newline");
    }

    // 4-byte emoji split across the chunk boundary → no mojibake.
    #[test]
    fn drain_complete_lines_emoji_split_across_chunks() {
        // '🦀' = U+1F980 = F0 9F A6 80 (4 bytes).
        let full: Vec<u8> = "data: \"🦀\"\n".as_bytes().to_vec();
        let prefix = "data: \"".len(); // byte offset where '🦀' begins
        let split = prefix + 2; // two bytes into the 4-byte emoji
        let (first, second) = full.split_at(split);

        let mut buf: Vec<u8> = Vec::new();
        buf.extend_from_slice(first);
        assert!(drain_complete_lines(&mut buf).is_empty(), "no newline yet");

        buf.extend_from_slice(second);
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(lines.len(), 1);
        assert_eq!(lines[0], "data: \"🦀\"");
        assert!(
            !lines[0].contains('\u{FFFD}'),
            "no replacement char in reassembled emoji line: {}",
            lines[0]
        );
    }

    // `\r\n` (CRLF) line endings: the trailing `\r` is stripped along with `\n`.
    #[test]
    fn drain_complete_lines_strips_crlf() {
        let mut buf: Vec<u8> = b"data: {\"x\":1}\r\n".to_vec();
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(lines, vec!["data: {\"x\":1}".to_string()]);
        assert!(buf.is_empty());
    }

    // Multiple complete lines in one buffer are all returned, in order.
    #[test]
    fn drain_complete_lines_multiple_lines_in_order() {
        let mut buf: Vec<u8> = b"a\nb\nc\n".to_vec();
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(
            lines,
            vec!["a".to_string(), "b".to_string(), "c".to_string()]
        );
        assert!(buf.is_empty());
    }

    // A trailing partial line (no `\n`) stays buffered; only the complete lines
    // are returned. The leftover bytes wait for the next chunk, then complete.
    #[test]
    fn drain_complete_lines_trailing_partial_stays_buffered() {
        let mut buf: Vec<u8> = b"first\nsecond-incomplete".to_vec();
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(lines, vec!["first".to_string()]);
        // The incomplete tail remains for the next push.
        assert_eq!(buf, b"second-incomplete".to_vec());

        // When the rest (with a newline) arrives, the buffered tail is
        // completed and emitted as one line.
        buf.extend_from_slice(b"-done\n");
        let lines = drain_complete_lines(&mut buf);
        assert_eq!(lines, vec!["second-incomplete-done".to_string()]);
        assert!(buf.is_empty());
    }

    // ─────────────────────────────────────────────────────────────────────
    // v0.4.16 Phase 0 — CHARACTERIZATION (golden master) tests.
    //
    // These pin the CURRENT behavior of the executor predicates +
    // resolve_openai_executor_config before the P7 ProviderFamily / P8
    // subagent refactor. They lock today's routing so any drift during the
    // refactor is a caught regression, not a silent behavior change.
    // `word_match` / `supports_reasoning_effort` are pure; the resolve tests
    // serialize + save/restore the EXECUTOR_* env vars they touch.
    // ─────────────────────────────────────────────────────────────────────

    /// case: reasoning_o3_mini / reasoning_provider_prefix_o3 /
    /// reasoning_colon_prefix_o4 / reasoning_midword_o32_reject /
    /// reasoning_gpt55 — table-driven over `supports_reasoning_effort`.
    /// Locks which model strings the executor flags as reasoning-capable
    /// (and thus attaches `reasoning_effort` for). The word-boundary set
    /// (`-` `_` `/` `:` + string ends) is the contract; mid-word matches
    /// (`o32-mini`) must NOT trip it.
    #[test]
    fn char_supports_reasoning_effort_routing() {
        // o3 with trailing `-` boundary.
        assert!(supports_reasoning_effort("o3-mini"));
        // provider prefix `openai/o3-mini` — `/` is a boundary (P1.B).
        assert!(supports_reasoning_effort("openai/o3-mini"));
        // proxy colon prefix `proxy:o4` — `:` boundary + end-of-string.
        assert!(supports_reasoning_effort("proxy:o4"));
        // mid-word `o32-mini`: "o3" followed by a digit → NOT a boundary →
        // must reject (this is the load-bearing negative).
        assert!(!supports_reasoning_effort("o32-mini"));
        // gpt-5.5 → matched via the `contains("gpt-5.5")` branch (NOT
        // word_match — it's a plain substring check in the source).
        assert!(supports_reasoning_effort("gpt-5.5"));

        // Extra boundary pins to lock the full predicate shape:
        // o1 family.
        assert!(supports_reasoning_effort("o1"));
        assert!(supports_reasoning_effort("o1-mini"));
        // gpt-5.6 contains branch.
        assert!(supports_reasoning_effort("gpt-5.6"));
        // reasoner / thinking substring branches.
        assert!(supports_reasoning_effort("deepseek-reasoner"));
        assert!(supports_reasoning_effort("glm-4.6-thinking"));
        // Case-insensitive (model is lowercased first).
        assert!(supports_reasoning_effort("O3-MINI"));
        // Plain non-reasoning models reject.
        assert!(!supports_reasoning_effort("gpt-4o"));
        assert!(!supports_reasoning_effort("claude-opus-4-7"));
        // `gpt-5.5` is a substring check, so a mid-word host still matches
        // (characterization: this is what the code DOES, contains() not
        // word_match — pinning current behavior, not endorsing it).
        assert!(supports_reasoning_effort("my-gpt-5.5-proxy"));
        // codex gap #2: the case above is NOT a contains-vs-word_match
        // discriminator — `-` is a word boundary, so word_match("gpt-5.5")
        // would ALSO match "my-gpt-5.5-proxy". To truly lock that these are
        // `contains` (so P7's word_match consolidation can't silently convert
        // them), assert a host with NON-boundary chars hugging the needle:
        // `contains` matches, `word_match` would REJECT (x/y are not in the
        // -_/: boundary set). If this flips to false, someone changed the
        // gpt-5.x / reasoner / thinking branches from contains to word_match.
        assert!(
            supports_reasoning_effort("xxgpt-5.5yy"),
            "gpt-5.5 must match via contains(), not word_match() — no boundary around it here"
        );
        assert!(supports_reasoning_effort("xxgpt-5.6yy"));
        assert!(supports_reasoning_effort("xxreasoneryy"));
        assert!(supports_reasoning_effort("xxthinkingyy"));
    }

    /// case: reasoning_midword_o32_reject — isolated emphasis on the
    /// digit-suffix boundary rejection (mirrors word_match_handles_provider_
    /// prefixes but at the supports_reasoning_effort surface, which is the
    /// actual capability gate the stream() body reads).
    #[test]
    fn char_reasoning_midword_o32_reject() {
        assert!(
            !supports_reasoning_effort("o32-mini"),
            "o32 must not be misrouted as an o3 reasoning model"
        );
        // And the positive twin so the boundary's two sides are both pinned.
        assert!(supports_reasoning_effort("o3-mini"));
    }

    /// case: resolve_returns_none_for_non_openai
    /// Locks the EXACT-match gate: resolve_openai_executor_config returns
    /// None for any EXECUTOR_PROVIDER value that is not exactly "openai"
    /// (anthropic-compat / unset / arbitrary). This is the 1:1 contract with
    /// main.rs that decides Anthropic-client vs OpenAI-client routing.
    #[test]
    fn char_resolve_returns_none_for_non_openai() {
        let _g = crate::env_test_guard();

        let prior_provider = std::env::var("EXECUTOR_PROVIDER").ok();
        let prior_api_key = std::env::var("EXECUTOR_API_KEY").ok();

        // Provide a key so the only thing under test is the provider gate.
        std::env::set_var("EXECUTOR_API_KEY", "sk-test");

        // anthropic-compat → None.
        std::env::set_var("EXECUTOR_PROVIDER", "anthropic-compat");
        assert!(resolve_openai_executor_config().is_none());

        // arbitrary value → None.
        std::env::set_var("EXECUTOR_PROVIDER", "anthropic");
        assert!(resolve_openai_executor_config().is_none());

        // empty string → None.
        std::env::set_var("EXECUTOR_PROVIDER", "");
        assert!(resolve_openai_executor_config().is_none());

        // unset → None (the `.ok()?` short-circuit).
        std::env::remove_var("EXECUTOR_PROVIDER");
        assert!(resolve_openai_executor_config().is_none());

        // exactly "openai" → Some (positive control).
        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        assert!(resolve_openai_executor_config().is_some());

        match prior_provider {
            Some(v) => std::env::set_var("EXECUTOR_PROVIDER", v),
            None => std::env::remove_var("EXECUTOR_PROVIDER"),
        }
        match prior_api_key {
            Some(v) => std::env::set_var("EXECUTOR_API_KEY", v),
            None => std::env::remove_var("EXECUTOR_API_KEY"),
        }
    }

    /// case: resolve_exact_no_trim
    /// Locks that the provider compare is byte-exact with NO trim/lowercase:
    /// `" openai "` (surrounding spaces) does NOT match "openai" → None.
    /// Pins the no-trim contract that main.rs's prediction must mirror.
    #[test]
    fn char_resolve_exact_no_trim() {
        let _g = crate::env_test_guard();

        let prior_provider = std::env::var("EXECUTOR_PROVIDER").ok();
        let prior_api_key = std::env::var("EXECUTOR_API_KEY").ok();

        std::env::set_var("EXECUTOR_API_KEY", "sk-test");

        // Spaces around "openai" → exact compare fails → None.
        std::env::set_var("EXECUTOR_PROVIDER", " openai ");
        assert!(
            resolve_openai_executor_config().is_none(),
            "provider compare must be exact (no trim): ' openai ' != 'openai'"
        );

        // Different case → None (no lowercasing).
        std::env::set_var("EXECUTOR_PROVIDER", "OpenAI");
        assert!(resolve_openai_executor_config().is_none());

        match prior_provider {
            Some(v) => std::env::set_var("EXECUTOR_PROVIDER", v),
            None => std::env::remove_var("EXECUTOR_PROVIDER"),
        }
        match prior_api_key {
            Some(v) => std::env::set_var("EXECUTOR_API_KEY", v),
            None => std::env::remove_var("EXECUTOR_API_KEY"),
        }
    }

    /// case: exec_openai_api_key_fallback
    /// Locks the api_key fallback chain in resolve_openai_executor_config:
    /// EXECUTOR_API_KEY is preferred; when it is UNSET the resolver falls
    /// back to OPENAI_API_KEY. An empty EXECUTOR_API_KEY is treated as set
    /// (the `.or_else` only fires on the Err/unset arm), but the trailing
    /// `.filter(|s| !s.is_empty())` then makes an empty value yield None —
    /// pin both behaviors.
    #[test]
    fn char_resolve_openai_api_key_fallback() {
        let _g = crate::env_test_guard();

        let prior_provider = std::env::var("EXECUTOR_PROVIDER").ok();
        let prior_exec_key = std::env::var("EXECUTOR_API_KEY").ok();
        let prior_openai_key = std::env::var("OPENAI_API_KEY").ok();
        let prior_base = std::env::var("EXECUTOR_BASE_URL").ok();

        std::env::set_var("EXECUTOR_PROVIDER", "openai");
        std::env::remove_var("EXECUTOR_BASE_URL");

        // EXECUTOR_API_KEY UNSET, OPENAI_API_KEY set → fall back to R.
        std::env::remove_var("EXECUTOR_API_KEY");
        std::env::set_var("OPENAI_API_KEY", "R");
        let cfg = resolve_openai_executor_config().expect("should resolve via OPENAI_API_KEY");
        assert_eq!(cfg.api_key, "R");

        // EXECUTOR_API_KEY set → it wins over OPENAI_API_KEY.
        std::env::set_var("EXECUTOR_API_KEY", "E");
        let cfg = resolve_openai_executor_config().expect("should resolve via EXECUTOR_API_KEY");
        assert_eq!(cfg.api_key, "E");

        // Both unset → None.
        std::env::remove_var("EXECUTOR_API_KEY");
        std::env::remove_var("OPENAI_API_KEY");
        assert!(resolve_openai_executor_config().is_none());

        // EXECUTOR_API_KEY empty → the `.or_else` does NOT fire (Ok("")), but
        // the final `.filter(|s| !s.is_empty())` drops it → None.
        // (characterization: locks that empty EXECUTOR_API_KEY does NOT fall
        // through to OPENAI_API_KEY — current behavior.)
        std::env::set_var("EXECUTOR_API_KEY", "");
        std::env::set_var("OPENAI_API_KEY", "R2");
        assert!(
            resolve_openai_executor_config().is_none(),
            "empty EXECUTOR_API_KEY currently yields None (does not fall back to OPENAI_API_KEY)"
        );

        match prior_provider {
            Some(v) => std::env::set_var("EXECUTOR_PROVIDER", v),
            None => std::env::remove_var("EXECUTOR_PROVIDER"),
        }
        match prior_exec_key {
            Some(v) => std::env::set_var("EXECUTOR_API_KEY", v),
            None => std::env::remove_var("EXECUTOR_API_KEY"),
        }
        match prior_openai_key {
            Some(v) => std::env::set_var("OPENAI_API_KEY", v),
            None => std::env::remove_var("OPENAI_API_KEY"),
        }
        match prior_base {
            Some(v) => std::env::set_var("EXECUTOR_BASE_URL", v),
            None => std::env::remove_var("EXECUTOR_BASE_URL"),
        }
    }

    /// case: word_match boundary completeness — pins every boundary char the
    /// executor's reasoning detection relies on, plus the negatives, at the
    /// `word_match` surface directly. Complements the pre-existing
    /// `word_match_handles_provider_prefixes` without overlapping its exact
    /// asserts.
    #[test]
    fn char_word_match_boundary_chars() {
        // All four boundary chars before the needle.
        assert!(word_match("a-o3", "o3")); // dash
        assert!(word_match("a_o3", "o3")); // underscore
        assert!(word_match("a/o3", "o3")); // slash
        assert!(word_match("a:o3", "o3")); // colon
        // All four boundary chars after the needle.
        assert!(word_match("o3-x", "o3"));
        assert!(word_match("o3_x", "o3"));
        assert!(word_match("o3/x", "o3"));
        assert!(word_match("o3:x", "o3"));
        // A boundary NOT in the set (`.` and space) does NOT count.
        assert!(!word_match("o3.mini", "o3"));
        assert!(!word_match("o3 mini", "o3"));
        // Needle longer than haystack → false (length guard).
        assert!(!word_match("o3", "o3-mini"));
        // Empty needle → false.
        assert!(!word_match("anything", ""));
    }
}
