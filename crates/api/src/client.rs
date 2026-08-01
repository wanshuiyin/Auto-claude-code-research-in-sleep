use std::collections::VecDeque;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use runtime::{
    load_oauth_credentials, save_oauth_credentials, OAuthConfig, OAuthRefreshRequest,
    OAuthTokenExchangeRequest,
};
use serde::Deserialize;

use crate::error::ApiError;
use crate::sse::SseParser;
use crate::types::{
    ContentBlockDelta, MessageRequest, MessageResponse, OutputContentBlock, StreamEvent,
};

const DEFAULT_BASE_URL: &str = "https://api.anthropic.com";
const ANTHROPIC_VERSION: &str = "2023-06-01";
const REQUEST_ID_HEADER: &str = "request-id";
const ALT_REQUEST_ID_HEADER: &str = "x-request-id";
const DEFAULT_INITIAL_BACKOFF: Duration = Duration::from_millis(200);
const DEFAULT_MAX_BACKOFF: Duration = Duration::from_secs(2);
const DEFAULT_MAX_RETRIES: u32 = 2;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthSource {
    None,
    ApiKey(String),
    BearerToken(String),
    ApiKeyAndBearer {
        api_key: String,
        bearer_token: String,
    },
}

impl AuthSource {
    pub fn from_env() -> Result<Self, ApiError> {
        let api_key = read_env_non_empty("ANTHROPIC_API_KEY")?;
        let auth_token = read_env_non_empty("ANTHROPIC_AUTH_TOKEN")?;
        match (api_key, auth_token) {
            (Some(api_key), Some(bearer_token)) => Ok(Self::ApiKeyAndBearer {
                api_key,
                bearer_token,
            }),
            (Some(api_key), None) => Ok(Self::ApiKey(api_key)),
            (None, Some(bearer_token)) => Ok(Self::BearerToken(bearer_token)),
            (None, None) => Err(ApiError::MissingApiKey),
        }
    }

    #[must_use]
    pub fn api_key(&self) -> Option<&str> {
        match self {
            Self::ApiKey(api_key) | Self::ApiKeyAndBearer { api_key, .. } => Some(api_key),
            Self::None | Self::BearerToken(_) => None,
        }
    }

    #[must_use]
    pub fn bearer_token(&self) -> Option<&str> {
        match self {
            Self::BearerToken(token)
            | Self::ApiKeyAndBearer {
                bearer_token: token,
                ..
            } => Some(token),
            Self::None | Self::ApiKey(_) => None,
        }
    }

    #[must_use]
    pub fn masked_authorization_header(&self) -> &'static str {
        if self.bearer_token().is_some() {
            "Bearer [REDACTED]"
        } else {
            "<absent>"
        }
    }

    pub fn apply(&self, mut request_builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        if let Some(api_key) = self.api_key() {
            request_builder = request_builder.header("x-api-key", api_key);
        }
        if let Some(token) = self.bearer_token() {
            request_builder = request_builder.bearer_auth(token);
        }
        request_builder
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct OAuthTokenSet {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: Option<u64>,
    #[serde(default)]
    pub scopes: Vec<String>,
}

impl From<OAuthTokenSet> for AuthSource {
    fn from(value: OAuthTokenSet) -> Self {
        Self::BearerToken(value.access_token)
    }
}

#[derive(Debug, Clone)]
pub struct AnthropicClient {
    http: reqwest::Client,
    auth: AuthSource,
    base_url: String,
    max_retries: u32,
    initial_backoff: Duration,
    max_backoff: Duration,
    send_betas: bool,
}

impl AnthropicClient {
    #[must_use]
    pub fn new(api_key: impl Into<String>) -> Self {
        Self {
            http: reqwest::Client::new(),
            auth: AuthSource::ApiKey(api_key.into()),
            base_url: DEFAULT_BASE_URL.to_string(),
            max_retries: DEFAULT_MAX_RETRIES,
            initial_backoff: DEFAULT_INITIAL_BACKOFF,
            max_backoff: DEFAULT_MAX_BACKOFF,
            send_betas: true,
        }
    }

    #[must_use]
    pub fn from_auth(auth: AuthSource) -> Self {
        Self {
            http: reqwest::Client::new(),
            auth,
            base_url: DEFAULT_BASE_URL.to_string(),
            max_retries: DEFAULT_MAX_RETRIES,
            initial_backoff: DEFAULT_INITIAL_BACKOFF,
            max_backoff: DEFAULT_MAX_BACKOFF,
            send_betas: true,
        }
    }

    pub fn from_env() -> Result<Self, ApiError> {
        Ok(Self::from_auth(AuthSource::from_env_or_saved()?)
            .with_base_url(read_base_url())
            .with_send_betas(read_send_betas()))
    }

    #[must_use]
    pub fn with_auth_source(mut self, auth: AuthSource) -> Self {
        self.auth = auth;
        self
    }

    #[must_use]
    pub fn with_auth_token(mut self, auth_token: Option<String>) -> Self {
        match (
            self.auth.api_key().map(ToOwned::to_owned),
            auth_token.filter(|token| !token.is_empty()),
        ) {
            (Some(api_key), Some(bearer_token)) => {
                self.auth = AuthSource::ApiKeyAndBearer {
                    api_key,
                    bearer_token,
                };
            }
            (Some(api_key), None) => {
                self.auth = AuthSource::ApiKey(api_key);
            }
            (None, Some(bearer_token)) => {
                self.auth = AuthSource::BearerToken(bearer_token);
            }
            (None, None) => {
                self.auth = AuthSource::None;
            }
        }
        self
    }

    #[must_use]
    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into();
        self
    }

    #[must_use]
    pub fn with_send_betas(mut self, send_betas: bool) -> Self {
        self.send_betas = send_betas;
        self
    }

    #[must_use]
    pub fn with_retry_policy(
        mut self,
        max_retries: u32,
        initial_backoff: Duration,
        max_backoff: Duration,
    ) -> Self {
        self.max_retries = max_retries;
        self.initial_backoff = initial_backoff;
        self.max_backoff = max_backoff;
        self
    }

    #[must_use]
    pub fn auth_source(&self) -> &AuthSource {
        &self.auth
    }

    pub async fn send_message(
        &self,
        request: &MessageRequest,
    ) -> Result<MessageResponse, ApiError> {
        let request = MessageRequest {
            stream: false,
            ..request.clone()
        };
        let response = self.send_with_retry(&request).await?;
        let request_id = request_id_from_headers(response.headers());
        let mut response = response
            .json::<MessageResponse>()
            .await
            .map_err(ApiError::from)?;
        if response.request_id.is_none() {
            response.request_id = request_id;
        }
        Ok(response)
    }

    pub async fn stream_message(
        &self,
        request: &MessageRequest,
    ) -> Result<MessageStream, ApiError> {
        let streaming_request = request.clone().with_streaming();
        let response = self.send_with_retry(&streaming_request).await?;
        Ok(MessageStream {
            inner: self.clone(),
            request: streaming_request,
            request_id: request_id_from_headers(response.headers()),
            response,
            parser: SseParser::new(),
            pending: VecDeque::new(),
            events_emitted: 0,
            has_emitted_meaningful_content: false,
            stream_retries_remaining: read_stream_retry_budget(),
            observed_terminal: false,
            idle_timeout: resolve_stream_idle_timeout(),
            done: false,
        })
    }

    pub async fn exchange_oauth_code(
        &self,
        config: &OAuthConfig,
        request: &OAuthTokenExchangeRequest,
    ) -> Result<OAuthTokenSet, ApiError> {
        let response = self
            .http
            .post(&config.token_url)
            .header("content-type", "application/x-www-form-urlencoded")
            .form(&request.form_params())
            .send()
            .await
            .map_err(ApiError::from)?;
        let response = expect_success(response).await?;
        response
            .json::<OAuthTokenSet>()
            .await
            .map_err(ApiError::from)
    }

    pub async fn refresh_oauth_token(
        &self,
        config: &OAuthConfig,
        request: &OAuthRefreshRequest,
    ) -> Result<OAuthTokenSet, ApiError> {
        let response = self
            .http
            .post(&config.token_url)
            .header("content-type", "application/x-www-form-urlencoded")
            .form(&request.form_params())
            .send()
            .await
            .map_err(ApiError::from)?;
        let response = expect_success(response).await?;
        response
            .json::<OAuthTokenSet>()
            .await
            .map_err(ApiError::from)
    }

    async fn send_with_retry(
        &self,
        request: &MessageRequest,
    ) -> Result<reqwest::Response, ApiError> {
        let mut attempts = 0;
        let mut last_error: Option<ApiError>;

        loop {
            attempts += 1;
            match self.send_raw_request(request).await {
                Ok(response) => match expect_success(response).await {
                    Ok(response) => return Ok(response),
                    Err(error) if error.is_retryable() && attempts <= self.max_retries + 1 => {
                        last_error = Some(error);
                    }
                    Err(error) => return Err(error),
                },
                Err(error) if error.is_retryable() && attempts <= self.max_retries + 1 => {
                    last_error = Some(error);
                }
                Err(error) => return Err(error),
            }

            if attempts > self.max_retries {
                break;
            }

            tokio::time::sleep(self.backoff_for_attempt(attempts)?).await;
        }

        Err(ApiError::RetriesExhausted {
            attempts,
            last_error: Box::new(last_error.expect("retry loop must capture an error")),
        })
    }

    async fn send_raw_request(
        &self,
        request: &MessageRequest,
    ) -> Result<reqwest::Response, ApiError> {
        let is_oauth = self.auth.bearer_token().is_some() && self.auth.api_key().is_none();
        let request_url = format!("{}/v1/messages", self.base_url.trim_end_matches('/'));
        let mut request_builder = self
            .http
            .post(&request_url)
            .header("anthropic-version", ANTHROPIC_VERSION)
            .header("content-type", "application/json");
        if is_oauth && self.send_betas {
            let model = &request.model;
            let is_haiku = model.contains("haiku");
            let mut betas = vec!["oauth-2025-04-20"];
            if !is_haiku {
                betas.push("claude-code-20250219");
                betas.push("interleaved-thinking-2025-05-14");
            }
            if model.contains("opus") {
                betas.push("context-1m-2025-08-07");
            }
            request_builder = request_builder.header("anthropic-beta", betas.join(","));
        }
        request_builder = self.auth.apply(request_builder);

        request_builder = request_builder.json(request);
        request_builder.send().await.map_err(ApiError::from)
    }

    fn backoff_for_attempt(&self, attempt: u32) -> Result<Duration, ApiError> {
        let Some(multiplier) = 1_u32.checked_shl(attempt.saturating_sub(1)) else {
            return Err(ApiError::BackoffOverflow {
                attempt,
                base_delay: self.initial_backoff,
            });
        };
        Ok(self
            .initial_backoff
            .checked_mul(multiplier)
            .map_or(self.max_backoff, |delay| delay.min(self.max_backoff)))
    }
}

impl AuthSource {
    pub fn from_env_or_saved() -> Result<Self, ApiError> {
        if let Some(api_key) = read_env_non_empty("ANTHROPIC_API_KEY")? {
            return match read_env_non_empty("ANTHROPIC_AUTH_TOKEN")? {
                Some(bearer_token) => Ok(Self::ApiKeyAndBearer {
                    api_key,
                    bearer_token,
                }),
                None => Ok(Self::ApiKey(api_key)),
            };
        }
        if let Some(bearer_token) = read_env_non_empty("ANTHROPIC_AUTH_TOKEN")? {
            return Ok(Self::BearerToken(bearer_token));
        }
        // Try claw-code's own credentials.json
        match load_saved_oauth_token() {
            Ok(Some(token_set)) if !oauth_token_is_expired(&token_set) => {
                return Ok(Self::BearerToken(token_set.access_token));
            }
            _ => {}
        }
        // Fallback: try reading from macOS Keychain (Claude Code's stored OAuth token)
        if let Some(token_set) = load_keychain_oauth_token() {
            if !oauth_token_is_expired(&token_set) {
                return Ok(Self::BearerToken(token_set.access_token));
            }
        }
        Err(ApiError::MissingApiKey)
    }
}

/// True when the `ARIS_DISABLE_KEYCHAIN` escape hatch is set to a truthy
/// value. Truthy = any value other than empty / `0` / `false` / `no` / `off`
/// (case-insensitive); an unset variable is falsy — exactly the
/// `ARIS_NO_HISTORY` truthy semantics (`history.rs::history_disabled`).
///
/// v0.4.17 A5.1 — this is a **public escape hatch**, not just a test gate:
/// it skips every macOS Keychain fallback (both `from_env_or_saved` and
/// `resolve_startup_auth_source` route through `load_keychain_oauth_token`),
/// which is useful on machines where the official Claude Code credential is
/// installed but the user wants `ANTHROPIC_API_KEY`/saved-credentials-only
/// auth, on GUI-less macs, and in CI/test environments where reading the
/// real Keychain would be nondeterministic.
pub fn keychain_disabled() -> bool {
    match std::env::var("ARIS_DISABLE_KEYCHAIN") {
        Ok(v) => {
            let v = v.trim().to_ascii_lowercase();
            !matches!(v.as_str(), "" | "0" | "false" | "no" | "off")
        }
        Err(_) => false,
    }
}

/// Try to load OAuth token set from macOS Keychain (where official Claude Code stores it).
///
/// Honors the `ARIS_DISABLE_KEYCHAIN` escape hatch (see [`keychain_disabled`]):
/// when set to a truthy value this returns `None` unconditionally, so both
/// callers (`AuthSource::from_env_or_saved` and `resolve_startup_auth_source`)
/// skip the Keychain fallback in one place.
fn load_keychain_oauth_token() -> Option<OAuthTokenSet> {
    if keychain_disabled() {
        return None;
    }
    #[cfg(target_os = "macos")]
    {
        let output = std::process::Command::new("security")
            .args([
                "find-generic-password",
                "-s",
                "Claude Code-credentials",
                "-w",
            ])
            .output()
            .ok()?;
        if !output.status.success() {
            return None;
        }
        let raw = String::from_utf8(output.stdout).ok()?;
        let parsed: serde_json::Value = serde_json::from_str(raw.trim()).ok()?;
        let oauth = parsed.get("claudeAiOauth")?;
        let access_token = oauth.get("accessToken")?.as_str()?.to_string();
        if access_token.is_empty() {
            return None;
        }
        let refresh_token = oauth
            .get("refreshToken")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(ToOwned::to_owned);
        // Claude Code stores expiresAt as milliseconds since epoch; convert to seconds
        let expires_at = oauth.get("expiresAt").and_then(|v| v.as_u64()).map(|ms| {
            if ms > 1_000_000_000_000 {
                ms / 1000
            } else {
                ms
            }
        });
        Some(OAuthTokenSet {
            access_token,
            refresh_token,
            expires_at,
            scopes: Vec::new(),
        })
    }
    #[cfg(not(target_os = "macos"))]
    {
        None
    }
}

#[must_use]
pub fn oauth_token_is_expired(token_set: &OAuthTokenSet) -> bool {
    token_set
        .expires_at
        .is_some_and(|expires_at| expires_at <= now_unix_timestamp())
}

pub fn resolve_saved_oauth_token(config: &OAuthConfig) -> Result<Option<OAuthTokenSet>, ApiError> {
    let Some(token_set) = load_saved_oauth_token()? else {
        return Ok(None);
    };
    resolve_saved_oauth_token_set(config, token_set).map(Some)
}

pub fn resolve_startup_auth_source<F>(load_oauth_config: F) -> Result<AuthSource, ApiError>
where
    F: FnOnce() -> Result<Option<OAuthConfig>, ApiError>,
{
    if let Some(api_key) = read_env_non_empty("ANTHROPIC_API_KEY")? {
        return match read_env_non_empty("ANTHROPIC_AUTH_TOKEN")? {
            Some(bearer_token) => Ok(AuthSource::ApiKeyAndBearer {
                api_key,
                bearer_token,
            }),
            None => Ok(AuthSource::ApiKey(api_key)),
        };
    }
    if let Some(bearer_token) = read_env_non_empty("ANTHROPIC_AUTH_TOKEN")? {
        return Ok(AuthSource::BearerToken(bearer_token));
    }

    let Some(token_set) = load_saved_oauth_token()? else {
        // Fallback: try macOS Keychain (official Claude Code's stored OAuth token)
        if let Some(keychain_set) = load_keychain_oauth_token() {
            if !oauth_token_is_expired(&keychain_set) {
                return Ok(AuthSource::BearerToken(keychain_set.access_token));
            }
            // Token expired: no refresh config available here, fall through to error
        }
        return Err(ApiError::MissingApiKey);
    };
    if !oauth_token_is_expired(&token_set) {
        return Ok(AuthSource::BearerToken(token_set.access_token));
    }
    if token_set.refresh_token.is_none() {
        return Err(ApiError::ExpiredOAuthToken);
    }

    let Some(config) = load_oauth_config()? else {
        return Err(ApiError::Auth(
            "saved OAuth token is expired; runtime OAuth config is missing".to_string(),
        ));
    };
    Ok(AuthSource::from(resolve_saved_oauth_token_set(
        &config, token_set,
    )?))
}

fn resolve_saved_oauth_token_set(
    config: &OAuthConfig,
    token_set: OAuthTokenSet,
) -> Result<OAuthTokenSet, ApiError> {
    if !oauth_token_is_expired(&token_set) {
        return Ok(token_set);
    }
    let Some(refresh_token) = token_set.refresh_token.clone() else {
        return Err(ApiError::ExpiredOAuthToken);
    };
    let client = AnthropicClient::from_auth(AuthSource::None).with_base_url(read_base_url());
    let refreshed = client_runtime_block_on(async {
        client
            .refresh_oauth_token(
                config,
                &OAuthRefreshRequest::from_config(
                    config,
                    refresh_token,
                    Some(token_set.scopes.clone()),
                ),
            )
            .await
    })?;
    let resolved = OAuthTokenSet {
        access_token: refreshed.access_token,
        refresh_token: refreshed.refresh_token.or(token_set.refresh_token),
        expires_at: refreshed.expires_at,
        scopes: refreshed.scopes,
    };
    save_oauth_credentials(&runtime::OAuthTokenSet {
        access_token: resolved.access_token.clone(),
        refresh_token: resolved.refresh_token.clone(),
        expires_at: resolved.expires_at,
        scopes: resolved.scopes.clone(),
    })
    .map_err(ApiError::from)?;
    Ok(resolved)
}

fn client_runtime_block_on<F, T>(future: F) -> Result<T, ApiError>
where
    F: std::future::Future<Output = Result<T, ApiError>>,
{
    tokio::runtime::Runtime::new()
        .map_err(ApiError::from)?
        .block_on(future)
}

fn load_saved_oauth_token() -> Result<Option<OAuthTokenSet>, ApiError> {
    let token_set = load_oauth_credentials().map_err(ApiError::from)?;
    Ok(token_set.map(|token_set| OAuthTokenSet {
        access_token: token_set.access_token,
        refresh_token: token_set.refresh_token,
        expires_at: token_set.expires_at,
        scopes: token_set.scopes,
    }))
}

fn now_unix_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_secs())
}

fn read_env_non_empty(key: &str) -> Result<Option<String>, ApiError> {
    match std::env::var(key) {
        Ok(value) if !value.is_empty() => Ok(Some(value)),
        Ok(_) | Err(std::env::VarError::NotPresent) => Ok(None),
        Err(error) => Err(ApiError::from(error)),
    }
}

#[cfg(test)]
fn read_api_key() -> Result<String, ApiError> {
    let auth = AuthSource::from_env_or_saved()?;
    auth.api_key()
        .or_else(|| auth.bearer_token())
        .map(ToOwned::to_owned)
        .ok_or(ApiError::MissingApiKey)
}

#[cfg(test)]
fn read_auth_token() -> Option<String> {
    read_env_non_empty("ANTHROPIC_AUTH_TOKEN")
        .ok()
        .and_then(std::convert::identity)
}

#[must_use]
pub fn read_base_url() -> String {
    std::env::var("ANTHROPIC_BASE_URL").unwrap_or_else(|_| DEFAULT_BASE_URL.to_string())
}

/// Returns `false` when `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` is set to a truthy value,
/// indicating that Anthropic-specific beta headers should not be sent. This is needed for
/// third-party API providers (e.g. AWS Bedrock proxies) that reject unknown beta flags.
#[must_use]
pub fn read_send_betas() -> bool {
    !std::env::var("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS")
        .map(|v| matches!(v.as_str(), "1" | "true" | "yes"))
        .unwrap_or(false)
}

/// Number of additional whole-stream restarts the SSE reader will attempt
/// when the body abort or premature EOF occurs before any event was
/// emitted. v0.4.10 closes the C6 landmine documented in the v0.4.7
/// audit: stream chunk read failures used to surface directly as
/// `http error: error decoding response body`, with no retry, even
/// though the wider request-level retry wrapper (`send_with_retry`)
/// already exists. Default 2 (clamped 0..=5). Parsed as u32 first so
/// `ARIS_STREAM_RETRY=999` clamps to 5 instead of silently falling
/// back to default (would happen with direct u8 parse).
fn read_stream_retry_budget() -> u8 {
    let raw = std::env::var("ARIS_STREAM_RETRY")
        .ok()
        .and_then(|v| v.trim().parse::<u32>().ok())
        .unwrap_or(2);
    raw.min(5) as u8
}

/// Backoff between stream restarts. Small fixed delay to avoid hammering
/// a flaky proxy. Independent of the existing send_with_retry backoff,
/// which already handles the request-send phase.
const STREAM_RETRY_BACKOFF: Duration = Duration::from_millis(500);

/// Default chunk-idle timeout when `ARIS_STREAM_IDLE_TIMEOUT_SECS` is unset
/// or unparseable: 120s.
const STREAM_IDLE_TIMEOUT_DEFAULT_SECS: i64 = 120;
/// Lower clamp for the chunk-idle timeout (10s). Smaller values would
/// race normal long-thinking turns.
const STREAM_IDLE_TIMEOUT_MIN_SECS: i64 = 10;
/// Upper clamp for the chunk-idle timeout (30min). Larger values are
/// equivalent to "no timeout" — use `0` / negative to opt out explicitly.
const STREAM_IDLE_TIMEOUT_MAX_SECS: i64 = 1800;

/// v0.4.14 C11 — pure helper for parsing the chunk-idle timeout string.
/// Returns `None` when the parsed value is `<= 0` (caller treats as
/// "indefinite chunk wait"), otherwise clamps into `[10, 1800]` seconds.
/// Unparseable / missing / blank → default 120s. Pure so it's testable
/// without `std::env::set_var` racing the cargo test harness.
#[must_use]
pub(crate) fn parse_stream_idle_timeout_secs(raw: Option<&str>) -> Option<Duration> {
    let secs = raw
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(STREAM_IDLE_TIMEOUT_DEFAULT_SECS);
    if secs <= 0 {
        return None;
    }
    let clamped = secs.clamp(STREAM_IDLE_TIMEOUT_MIN_SECS, STREAM_IDLE_TIMEOUT_MAX_SECS) as u64;
    Some(Duration::from_secs(clamped))
}

/// Resolve the chunk-idle timeout for streaming reads from the
/// `ARIS_STREAM_IDLE_TIMEOUT_SECS` env var. Default 120s, clamp
/// `[10, 1800]`, `0` / negative disables. Returning `None` means
/// "do not wrap chunk().await in tokio::time::timeout" — chunks may
/// block indefinitely if the upstream proxy stops sending keepalives.
///
/// v0.4.14 C11 (codex audit P2): prevents stuck-forever symptoms on
/// long-lived HTTPS streams when the upstream silently hangs without
/// sending TCP RST or HTTP body.
#[must_use]
pub fn resolve_stream_idle_timeout() -> Option<Duration> {
    parse_stream_idle_timeout_secs(std::env::var("ARIS_STREAM_IDLE_TIMEOUT_SECS").ok().as_deref())
}

/// Whether a reqwest::Error represents a transient stream-body failure
/// that warrants a whole-stream restart (mid-body abort, decode/framing
/// interrupted, timeout, connect reset). Excludes HTTP status errors
/// (those are caught earlier by send_with_retry's expect_success).
fn stream_chunk_error_is_retryable(error: &reqwest::Error) -> bool {
    error.is_request()
        || error.is_connect()
        || error.is_timeout()
        || error.is_body()
        || error.is_decode()
}

fn request_id_from_headers(headers: &reqwest::header::HeaderMap) -> Option<String> {
    headers
        .get(REQUEST_ID_HEADER)
        .or_else(|| headers.get(ALT_REQUEST_ID_HEADER))
        .and_then(|value| value.to_str().ok())
        .map(ToOwned::to_owned)
}

#[derive(Debug)]
pub struct MessageStream {
    /// AnthropicClient handle, cloned at stream creation. Used by
    /// [`try_refresh_stream`](Self::try_refresh_stream) when a chunk
    /// read aborts before any event has been emitted. reqwest::Client
    /// is Arc-wrapped internally so the clone is cheap.
    inner: AnthropicClient,
    /// Request body as sent (already had `.with_streaming()` applied).
    /// Stored verbatim so retries re-send the same payload.
    request: MessageRequest,
    request_id: Option<String>,
    response: reqwest::Response,
    parser: SseParser,
    pending: VecDeque<StreamEvent>,
    /// Number of events the caller has already observed via
    /// [`next_event`](Self::next_event). Retained from v0.4.10 for
    /// session-level stats / debugging — covers any yielded protocol
    /// event including `MessageStart`, empty `text_delta`, etc.
    events_emitted: usize,
    /// `true` once we've yielded at least one event the caller can
    /// actually use (non-empty text/thinking delta, accumulating
    /// tool_use input, or ContentBlockStop). v0.4.12 retry-eligibility
    /// gate (codex P1.A): `MessageStart` alone or a stream that only
    /// sent `MessageStart` then EOF can still be safely retried because
    /// nothing observable was committed. Aligns with OpenAI executor's
    /// `nothing_emitted_yet()` predicate.
    has_emitted_meaningful_content: bool,
    /// Remaining whole-stream restart budget. Initialised from
    /// `ARIS_STREAM_RETRY` (default 2, clamped 0..=5).
    stream_retries_remaining: u8,
    /// `true` once we see Anthropic's `MessageStop` (the protocol's
    /// terminal event). Combined with
    /// `has_emitted_meaningful_content == false` to distinguish
    /// "proxy aborted before sending anything" from "complete short
    /// response".
    observed_terminal: bool,
    /// v0.4.14 C11 — per-chunk idle timeout wrapped around
    /// `response.chunk().await`. `None` means "wait indefinitely"
    /// (legacy behaviour, opt-in via `ARIS_STREAM_IDLE_TIMEOUT_SECS=0`).
    /// On elapse the stream goes through the existing mid-body abort
    /// retry path (same gates as a transient reqwest::Error).
    idle_timeout: Option<Duration>,
    done: bool,
}

/// v0.4.12 P1.A — classify whether yielding this event commits visible
/// state to the caller (so a whole-stream restart afterwards would
/// break output continuity). Aligns with OpenAI executor's
/// `nothing_emitted_yet()` definition: non-empty text/thinking, any
/// accumulating tool_use input, or a finished content block all count
/// as meaningful.
///
/// `ContentBlockStart::ToolUse` is **also** meaningful (codex round-3
/// finding #1): callers write `pending_tool` state when they see a
/// `ToolUse` start, so if the stream then aborts and we transparently
/// retry with a new request, the new stream might come back with text
/// and we'd risk emitting a stale `pending_tool` at the next
/// `ContentBlockStop`. Being conservative here closes that window —
/// the price is a marginally larger pool of unretryable streams.
///
/// `MessageStart` / `MessageDelta` / `MessageStop` and `ContentBlockStart`
/// with empty `Text` / `Thinking` content are still safe to discard
/// and so are NOT meaningful.
fn event_is_meaningful_content(event: &StreamEvent) -> bool {
    match event {
        StreamEvent::ContentBlockDelta(e) => match &e.delta {
            ContentBlockDelta::TextDelta { text } => !text.is_empty(),
            ContentBlockDelta::ThinkingDelta { thinking } => !thinking.is_empty(),
            ContentBlockDelta::InputJsonDelta { .. } => true,
            ContentBlockDelta::SignatureDelta { .. } => false,
        },
        StreamEvent::ContentBlockStop(_) => true,
        StreamEvent::ContentBlockStart(e) => match &e.content_block {
            OutputContentBlock::Text { text } => !text.is_empty(),
            OutputContentBlock::Thinking { thinking, .. } => !thinking.is_empty(),
            // ToolUse start commits caller pending_tool state — see doc above.
            OutputContentBlock::ToolUse { .. } => true,
        },
        // MessageStart / MessageDelta / MessageStop / Error — protocol-only,
        // no caller-visible content commitment.
        _ => false,
    }
}

/// v0.4.13 codex round-1 #3 — extracted retry-trigger truth table so it
/// can be unit-tested in isolation without mocking a `reqwest::Response`.
///
/// Returns `true` exactly when the premature-EOF retry path in
/// `MessageStream::next_event` should fire:
/// - no meaningful content yet (`MessageStart`-only stream is OK to discard)
/// - never saw `MessageStop` (would be a complete short response, not abort)
/// - parser surfaced an error OR finished with zero leftover events
/// - retry budget remains
///
/// Together these guarantee a retry is safe (no user-visible state to
/// preserve) and useful (something actually went wrong).
fn should_retry_on_premature_eof(
    has_emitted_meaningful_content: bool,
    observed_terminal: bool,
    parser_errored: bool,
    leftover_empty: bool,
    stream_retries_remaining: u8,
) -> bool {
    !has_emitted_meaningful_content
        && !observed_terminal
        && (parser_errored || leftover_empty)
        && stream_retries_remaining > 0
}

/// v0.4.21 #1 — once the premature-EOF retry gate has declined and
/// `SseParser::finish()` yielded no terminal event, decide whether a *clean*
/// EOF is a truncation that must hard-error rather than be reported as success.
/// True iff meaningful content was already delivered to the caller but no
/// terminal signal (`message_stop`, or a non-empty `stop_reason` `message_delta`)
/// was ever observed. Symmetric to the OpenAI executor's
/// `StreamEofAction::Truncated` branch: the point is to stop the consumer
/// synthesizing a `MessageStop` and committing a half-finished answer as a
/// complete turn (which corrupts follow-up turns). When no meaningful content
/// was emitted the retry path owns that case and an empty `Ok(None)` is correct;
/// when a terminal WAS seen the response is genuinely complete. Extracted as a
/// pure fn so it is unit-testable without mocking a `reqwest::Response`,
/// mirroring [`should_retry_on_premature_eof`].
fn eof_is_truncation(has_emitted_meaningful_content: bool, observed_terminal: bool) -> bool {
    has_emitted_meaningful_content && !observed_terminal
}

/// v0.4.21 #1 safety valve — pure parse of `ARIS_ALLOW_EOF_WITHOUT_STOP`. A
/// third-party Anthropic-compatible proxy that legitimately streams a COMPLETE
/// response without ever emitting a terminal signal (no `message_stop`, no
/// `stop_reason`-bearing `message_delta`) can opt back into the pre-v0.4.21
/// behavior (accept the partial as complete) by setting this to `1`/`true`.
/// Off by default: a missing terminal signal is a truncation and hard-errors,
/// so a half-finished answer is never silently saved as complete. Pure fn so
/// the mapping is unit-tested without env races (mirrors
/// `parse_stream_idle_timeout_secs`).
fn parse_allow_eof_without_terminal(value: Option<&str>) -> bool {
    value
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
}

/// Env-backed wrapper over [`parse_allow_eof_without_terminal`].
fn allow_eof_without_terminal() -> bool {
    parse_allow_eof_without_terminal(
        std::env::var("ARIS_ALLOW_EOF_WITHOUT_STOP")
            .ok()
            .as_deref(),
    )
}

/// v0.4.17 A5.2 (CL2) — classify whether an event signals that the stream
/// reached a terminal state, symmetric to the `OpenAI` executor's v0.4.15
/// `observed_done || observed_finish_reason` semantics:
///
/// * `MessageStop` — the canonical Anthropic terminal frame (pre-CL2 this
///   was the ONLY signal that flipped `observed_terminal`).
/// * `MessageDelta` with a **non-empty** `stop_reason` — anthropic-compat
///   proxies may emit `message_delta` carrying `stop_reason` and then close
///   the connection without ever sending `message_stop`; treating the delta
///   as terminal turns that clean EOF into a complete response instead of a
///   spurious premature-EOF retry. Empty-string `stop_reason` is NOT
///   terminal (mirrors `choice_finish_reason`'s non-empty filter on the
///   `OpenAI` side).
///
/// Like the `OpenAI` `stream_eof_action` philosophy, this only relaxes how a
/// *clean* EOF is judged — the reader never stops early at a terminal
/// signal, so trailing `MessageStop` / usage frames are still consumed, and
/// a true truncation (no terminal signal at all) still hard-errors. The
/// meaningful-content retry gate (`event_is_meaningful_content`) is
/// deliberately untouched.
fn event_signals_terminal(event: &StreamEvent) -> bool {
    match event {
        StreamEvent::MessageStop(_) => true,
        StreamEvent::MessageDelta(e) => e
            .delta
            .stop_reason
            .as_deref()
            .is_some_and(|reason| !reason.is_empty()),
        _ => false,
    }
}

impl MessageStream {
    #[must_use]
    pub fn request_id(&self) -> Option<&str> {
        self.request_id.as_deref()
    }

    pub async fn next_event(&mut self) -> Result<Option<StreamEvent>, ApiError> {
        loop {
            if let Some(event) = self.pending.pop_front() {
                // Convert in-stream error events to ApiError
                if let StreamEvent::Error(e) = &event {
                    let msg = e
                        .error
                        .get("message")
                        .and_then(|v| v.as_str())
                        .unwrap_or("stream error")
                        .to_string();
                    return Err(ApiError::Api {
                        status: reqwest::StatusCode::OK,
                        error_type: e
                            .error
                            .get("type")
                            .and_then(|v| v.as_str())
                            .map(ToOwned::to_owned),
                        message: Some(msg.clone()),
                        body: msg,
                        retryable: false,
                    });
                }
                // Track terminal signal + meaningful-content flag + counter.
                // v0.4.17 A5.2 (CL2): MessageStop OR a stop_reason-bearing
                // MessageDelta both count as terminal — see event_signals_terminal.
                if event_signals_terminal(&event) {
                    self.observed_terminal = true;
                }
                if event_is_meaningful_content(&event) {
                    self.has_emitted_meaningful_content = true;
                }
                self.events_emitted = self.events_emitted.saturating_add(1);
                return Ok(Some(event));
            }

            if self.done {
                // Premature EOF retry path: if the server closed the
                // stream cleanly (no reqwest error) but no meaningful
                // content reached the caller AND we never saw
                // MessageStop, the proxy probably aborted upstream.
                // Try a whole-stream restart before surfacing the
                // parser error or empty result. v0.4.12 P1.A (codex
                // round-2 finding #3): gate retry on
                // `!has_emitted_meaningful_content` not `events_emitted == 0`,
                // so a stream that only sent `MessageStart` then died
                // is still retry-eligible.
                let finish_result = self.parser.finish();
                let parser_errored = finish_result.is_err();
                let leftover_empty = finish_result.as_ref().map(Vec::is_empty).unwrap_or(false);
                if should_retry_on_premature_eof(
                    self.has_emitted_meaningful_content,
                    self.observed_terminal,
                    parser_errored,
                    leftover_empty,
                    self.stream_retries_remaining,
                ) {
                    self.stream_retries_remaining -= 1;
                    eprintln!(
                        "stream restart (premature EOF, {} attempt(s) left)",
                        self.stream_retries_remaining
                    );
                    self.try_refresh_stream().await?;
                    continue;
                }
                let remaining = finish_result?;
                self.pending.extend(remaining);
                if let Some(event) = self.pending.pop_front() {
                    // v0.4.17 A5.2 (CL2): same terminal classification as the
                    // main pop path above.
                    if event_signals_terminal(&event) {
                        self.observed_terminal = true;
                    }
                    if event_is_meaningful_content(&event) {
                        self.has_emitted_meaningful_content = true;
                    }
                    self.events_emitted = self.events_emitted.saturating_add(1);
                    return Ok(Some(event));
                }
                // v0.4.21 #1: symmetric to the OpenAI `StreamEofAction::Truncated`
                // branch. A clean EOF that delivered meaningful content but never
                // a terminal signal (message_stop / stop_reason-bearing
                // message_delta) is a TRUNCATED response, not success. Returning
                // Ok(None) here lets the consumer synthesize a MessageStop and
                // commit a half-finished answer as a complete turn. The retry
                // gate above never fires once meaningful content was emitted
                // (tearing visible output is worse), and SseParser::finish()
                // returns Ok(empty) on a mid-message EOF, so without this guard
                // the truncation is silently masked. `observed_terminal` here
                // already reflects any terminal frame popped from the trailing
                // buffer just above. Safety valve: ARIS_ALLOW_EOF_WITHOUT_STOP=1
                // opts a proxy that legitimately never sends a terminal signal
                // back into the pre-v0.4.21 accept-as-complete behavior.
                if eof_is_truncation(self.has_emitted_meaningful_content, self.observed_terminal)
                    && !allow_eof_without_terminal()
                {
                    return Err(ApiError::Api {
                        status: reqwest::StatusCode::OK,
                        error_type: Some("premature_eof".to_string()),
                        message: Some(
                            "Anthropic stream ended without message_stop or a stop_reason \
                             (truncated response)"
                                .to_string(),
                        ),
                        body: "Anthropic stream ended without message_stop or a stop_reason \
                               (truncated response)"
                            .to_string(),
                        retryable: false,
                    });
                }
                return Ok(None);
            }

            // v0.4.14 C11 — wrap chunk read in tokio::time::timeout so
            // a hung upstream (proxy holding the connection without
            // sending keepalives) can't stall this loop forever. Idle
            // elapse is treated equivalently to a mid-body abort and
            // walks through the same restart gate.
            let chunk_future = self.response.chunk();
            let chunk_result = match self.idle_timeout {
                Some(dur) => match tokio::time::timeout(dur, chunk_future).await {
                    Ok(inner) => inner,
                    Err(_elapsed) => {
                        if !self.has_emitted_meaningful_content
                            && self.stream_retries_remaining > 0
                        {
                            self.stream_retries_remaining -= 1;
                            eprintln!(
                                "stream restart (idle timeout {}s, {} attempt(s) left)",
                                dur.as_secs(),
                                self.stream_retries_remaining
                            );
                            self.try_refresh_stream().await?;
                            continue;
                        }
                        return Err(ApiError::Api {
                            status: reqwest::StatusCode::REQUEST_TIMEOUT,
                            error_type: Some("stream_idle_timeout".to_string()),
                            message: Some(format!(
                                "Anthropic stream idle timeout ({}s, retries exhausted or partial output already emitted)",
                                dur.as_secs()
                            )),
                            body: format!(
                                "Anthropic stream idle timeout after {}s with no chunk; retries exhausted or partial output already emitted",
                                dur.as_secs()
                            ),
                            retryable: false,
                        });
                    }
                },
                None => chunk_future.await,
            };
            match chunk_result {
                Ok(Some(chunk)) => {
                    self.pending.extend(self.parser.push(&chunk)?);
                }
                Ok(None) => {
                    self.done = true;
                }
                Err(error) => {
                    // Mid-body abort. Retry the whole request if we
                    // haven't surfaced any meaningful content to the
                    // caller yet — there's no resume primitive in
                    // either upstream API. v0.4.12 P1.A: gate on
                    // `!has_emitted_meaningful_content` not raw
                    // `events_emitted`, so a stream that only sent
                    // `MessageStart` before aborting is still safe
                    // to restart.
                    if !self.has_emitted_meaningful_content
                        && self.stream_retries_remaining > 0
                        && stream_chunk_error_is_retryable(&error)
                    {
                        self.stream_retries_remaining -= 1;
                        eprintln!(
                            "stream restart (body abort: {}, {} attempt(s) left)",
                            error, self.stream_retries_remaining
                        );
                        self.try_refresh_stream().await?;
                        continue;
                    }
                    return Err(ApiError::from(error));
                }
            }
        }
    }

    /// Re-sends the original request and rebinds the parser/response
    /// state. Used only when `next_event` decides the prior stream
    /// died before any event reached the caller.
    async fn try_refresh_stream(&mut self) -> Result<(), ApiError> {
        tokio::time::sleep(STREAM_RETRY_BACKOFF).await;
        let response = self.inner.send_with_retry(&self.request).await?;
        self.request_id = request_id_from_headers(response.headers());
        self.response = response;
        self.parser = SseParser::new();
        self.pending.clear();
        self.done = false;
        // Defensive reset — restart only fires while these are already
        // in their "nothing committed" state, but resetting explicitly
        // keeps the invariant obvious to future readers.
        self.events_emitted = 0;
        self.has_emitted_meaningful_content = false;
        self.observed_terminal = false;
        Ok(())
    }
}

async fn expect_success(response: reqwest::Response) -> Result<reqwest::Response, ApiError> {
    let status = response.status();
    if status.is_success() {
        return Ok(response);
    }

    let body = response.text().await.unwrap_or_else(|_| String::new());
    let parsed_error = serde_json::from_str::<AnthropicErrorEnvelope>(&body).ok();
    let retryable = is_retryable_status(status);

    Err(ApiError::Api {
        status,
        error_type: parsed_error
            .as_ref()
            .map(|error| error.error.error_type.clone()),
        message: parsed_error
            .as_ref()
            .map(|error| error.error.message.clone()),
        body,
        retryable,
    })
}

const fn is_retryable_status(status: reqwest::StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 409 | 429 | 500 | 502 | 503 | 504)
}

#[derive(Debug, Deserialize)]
struct AnthropicErrorEnvelope {
    error: AnthropicErrorBody,
}

#[derive(Debug, Deserialize)]
struct AnthropicErrorBody {
    #[serde(rename = "type")]
    error_type: String,
    message: String,
}

#[cfg(test)]
mod tests {
    use super::{ALT_REQUEST_ID_HEADER, REQUEST_ID_HEADER};
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{Mutex, OnceLock};
    use std::thread;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    use runtime::{clear_oauth_credentials, save_oauth_credentials, OAuthConfig};

    use crate::client::{
        now_unix_timestamp, oauth_token_is_expired, resolve_saved_oauth_token,
        resolve_startup_auth_source, AnthropicClient, AuthSource, OAuthTokenSet,
    };
    use crate::types::{ContentBlockDelta, MessageRequest};

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        let guard = LOCK
            .get_or_init(|| Mutex::new(()))
            .lock()
            .expect("env lock");
        // v0.4.23: these tests drive LOCAL mock HTTP servers through reqwest,
        // which honors proxy env vars — a developer shell with http(s)_proxy
        // set routes 127.0.0.1 through the proxy and every request comes back
        // 502 (observed live: 4 tests red on a released tag purely from the
        // shell's proxy). Scrub the proxy env under the lock; tests never
        // need a proxy and the test process env is disposable.
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
        guard
    }

    fn temp_config_home() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "api-oauth-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ))
    }

    fn sample_oauth_config(token_url: String) -> OAuthConfig {
        OAuthConfig {
            client_id: "runtime-client".to_string(),
            authorize_url: "https://console.test/oauth/authorize".to_string(),
            token_url,
            callback_port: Some(4545),
            manual_redirect_url: Some("https://console.test/oauth/callback".to_string()),
            scopes: vec!["org:read".to_string(), "user:write".to_string()],
        }
    }

    fn spawn_token_server(response_body: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind listener");
        let address = listener.local_addr().expect("local addr");
        thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept connection");
            let mut buffer = [0_u8; 4096];
            let _ = stream.read(&mut buffer).expect("read request");
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{}",
                response_body.len(),
                response_body
            );
            stream
                .write_all(response.as_bytes())
                .expect("write response");
        });
        format!("http://{address}/oauth/token")
    }

    #[test]
    fn read_api_key_requires_presence() {
        let _guard = env_lock();
        // v0.4.17 A5.1: without the gate, a developer machine with the
        // official Claude Code Keychain credential would resolve a real
        // token here and the expect_err would fail (local-red/CI-green).
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        let error = super::read_api_key().expect_err("missing key should error");
        assert!(matches!(error, crate::error::ApiError::MissingApiKey));
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
    }

    #[test]
    fn read_api_key_requires_non_empty_value() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "");
        std::env::remove_var("ANTHROPIC_API_KEY");
        let error = super::read_api_key().expect_err("empty key should error");
        assert!(matches!(error, crate::error::ApiError::MissingApiKey));
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
    }

    #[test]
    fn read_api_key_prefers_api_key_env() {
        let _guard = env_lock();
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "auth-token");
        std::env::set_var("ANTHROPIC_API_KEY", "legacy-key");
        assert_eq!(
            super::read_api_key().expect("api key should load"),
            "legacy-key"
        );
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
    }

    #[test]
    fn read_auth_token_reads_auth_token_env() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "auth-token");
        assert_eq!(super::read_auth_token().as_deref(), Some("auth-token"));
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
    }

    #[test]
    fn oauth_token_maps_to_bearer_auth_source() {
        let auth = AuthSource::from(OAuthTokenSet {
            access_token: "access-token".to_string(),
            refresh_token: Some("refresh".to_string()),
            expires_at: Some(123),
            scopes: vec!["scope:a".to_string()],
        });
        assert_eq!(auth.bearer_token(), Some("access-token"));
        assert_eq!(auth.api_key(), None);
    }

    #[test]
    fn auth_source_from_env_combines_api_key_and_bearer_token() {
        let _guard = env_lock();
        std::env::set_var("ANTHROPIC_AUTH_TOKEN", "auth-token");
        std::env::set_var("ANTHROPIC_API_KEY", "legacy-key");
        let auth = AuthSource::from_env().expect("env auth");
        assert_eq!(auth.api_key(), Some("legacy-key"));
        assert_eq!(auth.bearer_token(), Some("auth-token"));
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
    }

    #[test]
    fn auth_source_from_saved_oauth_when_env_absent() {
        let _guard = env_lock();
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        save_oauth_credentials(&runtime::OAuthTokenSet {
            access_token: "saved-access-token".to_string(),
            refresh_token: Some("refresh".to_string()),
            expires_at: Some(now_unix_timestamp() + 300),
            scopes: vec!["scope:a".to_string()],
        })
        .expect("save oauth credentials");

        let auth = AuthSource::from_env_or_saved().expect("saved auth");
        assert_eq!(auth.bearer_token(), Some("saved-access-token"));

        clear_oauth_credentials().expect("clear credentials");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::fs::remove_dir_all(config_home).expect("cleanup temp dir");
    }

    #[test]
    fn oauth_token_expiry_uses_expires_at_timestamp() {
        assert!(oauth_token_is_expired(&OAuthTokenSet {
            access_token: "access-token".to_string(),
            refresh_token: None,
            expires_at: Some(1),
            scopes: Vec::new(),
        }));
        assert!(!oauth_token_is_expired(&OAuthTokenSet {
            access_token: "access-token".to_string(),
            refresh_token: None,
            expires_at: Some(now_unix_timestamp() + 60),
            scopes: Vec::new(),
        }));
    }

    #[test]
    fn resolve_saved_oauth_token_refreshes_expired_credentials() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        save_oauth_credentials(&runtime::OAuthTokenSet {
            access_token: "expired-access-token".to_string(),
            refresh_token: Some("refresh-token".to_string()),
            expires_at: Some(1),
            scopes: vec!["scope:a".to_string()],
        })
        .expect("save expired oauth credentials");

        let token_url = spawn_token_server(
            "{\"access_token\":\"refreshed-token\",\"refresh_token\":\"fresh-refresh\",\"expires_at\":9999999999,\"scopes\":[\"scope:a\"]}",
        );
        let resolved = resolve_saved_oauth_token(&sample_oauth_config(token_url))
            .expect("resolve refreshed token")
            .expect("token set present");
        assert_eq!(resolved.access_token, "refreshed-token");
        let stored = runtime::load_oauth_credentials()
            .expect("load stored credentials")
            .expect("stored token set");
        assert_eq!(stored.access_token, "refreshed-token");

        clear_oauth_credentials().expect("clear credentials");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
        std::fs::remove_dir_all(config_home).expect("cleanup temp dir");
    }

    #[test]
    fn resolve_startup_auth_source_uses_saved_oauth_without_loading_config() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        save_oauth_credentials(&runtime::OAuthTokenSet {
            access_token: "saved-access-token".to_string(),
            refresh_token: Some("refresh".to_string()),
            expires_at: Some(now_unix_timestamp() + 300),
            scopes: vec!["scope:a".to_string()],
        })
        .expect("save oauth credentials");

        let auth = resolve_startup_auth_source(|| panic!("config should not be loaded"))
            .expect("startup auth");
        assert_eq!(auth.bearer_token(), Some("saved-access-token"));

        clear_oauth_credentials().expect("clear credentials");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
        std::fs::remove_dir_all(config_home).expect("cleanup temp dir");
    }

    #[test]
    fn resolve_startup_auth_source_errors_when_refreshable_token_lacks_config() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        save_oauth_credentials(&runtime::OAuthTokenSet {
            access_token: "expired-access-token".to_string(),
            refresh_token: Some("refresh-token".to_string()),
            expires_at: Some(1),
            scopes: vec!["scope:a".to_string()],
        })
        .expect("save expired oauth credentials");

        let error =
            resolve_startup_auth_source(|| Ok(None)).expect_err("missing config should error");
        assert!(
            matches!(error, crate::error::ApiError::Auth(message) if message.contains("runtime OAuth config is missing"))
        );

        let stored = runtime::load_oauth_credentials()
            .expect("load stored credentials")
            .expect("stored token set");
        assert_eq!(stored.access_token, "expired-access-token");
        assert_eq!(stored.refresh_token.as_deref(), Some("refresh-token"));

        clear_oauth_credentials().expect("clear credentials");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
        std::fs::remove_dir_all(config_home).expect("cleanup temp dir");
    }

    #[test]
    fn resolve_saved_oauth_token_preserves_refresh_token_when_refresh_response_omits_it() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");
        save_oauth_credentials(&runtime::OAuthTokenSet {
            access_token: "expired-access-token".to_string(),
            refresh_token: Some("refresh-token".to_string()),
            expires_at: Some(1),
            scopes: vec!["scope:a".to_string()],
        })
        .expect("save expired oauth credentials");

        let token_url = spawn_token_server(
            "{\"access_token\":\"refreshed-token\",\"expires_at\":9999999999,\"scopes\":[\"scope:a\"]}",
        );
        let resolved = resolve_saved_oauth_token(&sample_oauth_config(token_url))
            .expect("resolve refreshed token")
            .expect("token set present");
        assert_eq!(resolved.access_token, "refreshed-token");
        assert_eq!(resolved.refresh_token.as_deref(), Some("refresh-token"));
        let stored = runtime::load_oauth_credentials()
            .expect("load stored credentials")
            .expect("stored token set");
        assert_eq!(stored.refresh_token.as_deref(), Some("refresh-token"));

        clear_oauth_credentials().expect("clear credentials");
        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
        std::fs::remove_dir_all(config_home).expect("cleanup temp dir");
    }

    /// v0.4.17 A5.1 — the gate's own unit test: with `ARIS_DISABLE_KEYCHAIN`
    /// set, no env keys, and a fresh (credential-less) config home,
    /// `from_env_or_saved` must surface `MissingApiKey` — i.e. the Keychain
    /// fallback is skipped even on a macOS machine that has the official
    /// Claude Code credential installed. (Without the gate this would
    /// nondeterministically return a real `BearerToken` locally.)
    #[test]
    fn keychain_gate_skips_keychain_fallback() {
        let _guard = env_lock();
        std::env::set_var("ARIS_DISABLE_KEYCHAIN", "1");
        let config_home = temp_config_home();
        std::env::set_var("CLAUDE_CONFIG_HOME", &config_home);
        std::env::remove_var("ANTHROPIC_AUTH_TOKEN");
        std::env::remove_var("ANTHROPIC_API_KEY");

        let error = AuthSource::from_env_or_saved()
            .expect_err("gated keychain + no env + no saved credentials must error");
        assert!(matches!(error, crate::error::ApiError::MissingApiKey));

        std::env::remove_var("CLAUDE_CONFIG_HOME");
        std::env::remove_var("ARIS_DISABLE_KEYCHAIN");
    }

    #[test]
    fn message_request_stream_helper_sets_stream_true() {
        let request = MessageRequest {
            model: "claude-opus-4-7".to_string(),
            max_tokens: 64,
            messages: vec![],
            system: None,
            tools: None,
            tool_choice: None,
            stream: false,
        };

        assert!(request.with_streaming().stream);
    }

    #[test]
    fn backoff_doubles_until_maximum() {
        let client = AnthropicClient::new("test-key").with_retry_policy(
            3,
            Duration::from_millis(10),
            Duration::from_millis(25),
        );
        assert_eq!(
            client.backoff_for_attempt(1).expect("attempt 1"),
            Duration::from_millis(10)
        );
        assert_eq!(
            client.backoff_for_attempt(2).expect("attempt 2"),
            Duration::from_millis(20)
        );
        assert_eq!(
            client.backoff_for_attempt(3).expect("attempt 3"),
            Duration::from_millis(25)
        );
    }

    #[test]
    fn retryable_statuses_are_detected() {
        assert!(super::is_retryable_status(
            reqwest::StatusCode::TOO_MANY_REQUESTS
        ));
        assert!(super::is_retryable_status(
            reqwest::StatusCode::INTERNAL_SERVER_ERROR
        ));
        assert!(!super::is_retryable_status(
            reqwest::StatusCode::UNAUTHORIZED
        ));
    }

    #[test]
    fn tool_delta_variant_round_trips() {
        let delta = ContentBlockDelta::InputJsonDelta {
            partial_json: "{\"city\":\"Paris\"}".to_string(),
        };
        let encoded = serde_json::to_string(&delta).expect("delta should serialize");
        let decoded: ContentBlockDelta =
            serde_json::from_str(&encoded).expect("delta should deserialize");
        assert_eq!(decoded, delta);
    }

    #[test]
    fn request_id_uses_primary_or_fallback_header() {
        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert(REQUEST_ID_HEADER, "req_primary".parse().expect("header"));
        assert_eq!(
            super::request_id_from_headers(&headers).as_deref(),
            Some("req_primary")
        );

        headers.clear();
        headers.insert(
            ALT_REQUEST_ID_HEADER,
            "req_fallback".parse().expect("header"),
        );
        assert_eq!(
            super::request_id_from_headers(&headers).as_deref(),
            Some("req_fallback")
        );
    }

    #[test]
    fn auth_source_applies_headers() {
        let auth = AuthSource::ApiKeyAndBearer {
            api_key: "test-key".to_string(),
            bearer_token: "proxy-token".to_string(),
        };
        let request = auth
            .apply(reqwest::Client::new().post("https://example.test"))
            .build()
            .expect("request build");
        let headers = request.headers();
        assert_eq!(
            headers.get("x-api-key").and_then(|v| v.to_str().ok()),
            Some("test-key")
        );
        assert_eq!(
            headers.get("authorization").and_then(|v| v.to_str().ok()),
            Some("Bearer proxy-token")
        );
    }

    // v0.4.13 regression — codex round-3 finding #1. The streaming retry
    // path skips reconnects only when the events emitted so far are
    // "meaningful content" — empty MessageStart/Stop frames are safe to
    // discard. Pin the classification on every branch so a future refactor
    // can't silently widen "non-meaningful" and break user-visible content
    // commitments (text already streamed, tool_use call sites already
    // committed).
    #[test]
    fn event_is_meaningful_content_classification() {
        use crate::types::{
            ContentBlockDelta, ContentBlockDeltaEvent, ContentBlockStartEvent, ContentBlockStopEvent,
            MessageDelta, MessageDeltaEvent, MessageResponse, MessageStartEvent, MessageStopEvent,
            OutputContentBlock, StreamEvent, Usage,
        };

        fn dummy_message_response() -> MessageResponse {
            MessageResponse {
                id: "msg_test".to_string(),
                kind: "message".to_string(),
                role: "assistant".to_string(),
                content: vec![],
                model: "claude-test".to_string(),
                stop_reason: None,
                stop_sequence: None,
                usage: Usage {
                    input_tokens: 0,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                    output_tokens: 0,
                },
                request_id: None,
            }
        }

        // Protocol-only frames: NOT meaningful (safe to discard on retry).
        assert!(!super::event_is_meaningful_content(&StreamEvent::MessageStart(
            MessageStartEvent {
                message: dummy_message_response(),
            }
        )));
        assert!(!super::event_is_meaningful_content(&StreamEvent::MessageDelta(
            MessageDeltaEvent {
                delta: MessageDelta {
                    stop_reason: None,
                    stop_sequence: None,
                },
                usage: Usage {
                    input_tokens: 0,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                    output_tokens: 0,
                },
            }
        )));
        assert!(!super::event_is_meaningful_content(&StreamEvent::MessageStop(
            MessageStopEvent {}
        )));

        // Empty text_delta — caller hasn't seen any chars yet, safe to discard.
        assert!(!super::event_is_meaningful_content(&StreamEvent::ContentBlockDelta(
            ContentBlockDeltaEvent {
                index: 0,
                delta: ContentBlockDelta::TextDelta { text: String::new() },
            }
        )));

        // Non-empty text_delta — committed user-visible content, MUST be meaningful.
        assert!(super::event_is_meaningful_content(&StreamEvent::ContentBlockDelta(
            ContentBlockDeltaEvent {
                index: 0,
                delta: ContentBlockDelta::TextDelta {
                    text: "hello".to_string(),
                },
            }
        )));

        // ContentBlockStop — block-level commitment, must be meaningful.
        assert!(super::event_is_meaningful_content(&StreamEvent::ContentBlockStop(
            ContentBlockStopEvent { index: 0 }
        )));

        // ContentBlockStart::ToolUse — caller writes pending_tool state on
        // the start frame; even with empty `input`, transparent retry now
        // would risk stale tool_use commit on next BlockStop. Conservative
        // per round-3 finding.
        assert!(super::event_is_meaningful_content(&StreamEvent::ContentBlockStart(
            ContentBlockStartEvent {
                index: 0,
                content_block: OutputContentBlock::ToolUse {
                    id: "x".to_string(),
                    name: "y".to_string(),
                    input: serde_json::json!({}),
                },
            }
        )));

        // ContentBlockStart::Text with empty text — no commitment yet.
        assert!(!super::event_is_meaningful_content(&StreamEvent::ContentBlockStart(
            ContentBlockStartEvent {
                index: 0,
                content_block: OutputContentBlock::Text { text: String::new() },
            }
        )));
    }

    /// v0.4.13 codex round-1 #3 — verify the premature-EOF retry trigger
    /// truth table. Covers the "MessageStart only, then EOF" case that
    /// P1.A is supposed to enable retry for, without needing to mock a
    /// real SSE stream.
    #[test]
    fn should_retry_on_premature_eof_truth_table() {
        // Happy path: MessageStart consumed (no meaningful), no terminal,
        // parser finished with leftover_empty, retries remain → SHOULD retry.
        assert!(super::should_retry_on_premature_eof(
            /* has_emitted_meaningful_content */ false,
            /* observed_terminal */ false,
            /* parser_errored */ false,
            /* leftover_empty */ true,
            /* stream_retries_remaining */ 2,
        ));

        // Parser errored variant: should also retry.
        assert!(super::should_retry_on_premature_eof(false, false, true, false, 2));

        // Meaningful content already emitted (e.g. real text_delta yielded) →
        // NO retry, would tear output.
        assert!(!super::should_retry_on_premature_eof(true, false, false, true, 2));

        // observed_terminal (MessageStop seen) → complete short response,
        // NOT a premature EOF, NO retry.
        assert!(!super::should_retry_on_premature_eof(false, true, false, true, 2));

        // Neither parser errored NOR leftover_empty → there are events
        // about to be replayed; NO retry, drain them.
        assert!(!super::should_retry_on_premature_eof(false, false, false, false, 2));

        // Retry budget exhausted → NO retry regardless of other state.
        assert!(!super::should_retry_on_premature_eof(false, false, true, true, 0));

        // Single retry left + good preconditions → DO retry.
        assert!(super::should_retry_on_premature_eof(false, false, true, true, 1));
    }

    // ---------------------------------------------------------------
    // v0.4.17 A5.2 (CL2) — the Phase 0 characterization baseline
    // (`char_message_delta_with_stop_reason_is_not_meaningful_today`) was
    // DELIBERATELY FLIPPED here: a `MessageDelta` carrying a non-empty
    // `stop_reason` now signals stream-terminal (symmetric to v0.4.15's
    // OpenAI finish_reason handling), while its meaningful-content
    // classification — the retry gate — is deliberately UNCHANGED.
    #[test]
    fn message_delta_with_stop_reason_is_terminal_but_not_meaningful() {
        use crate::types::{MessageDelta, MessageDeltaEvent, StreamEvent, Usage};

        fn delta_event(stop_reason: Option<&str>) -> StreamEvent {
            StreamEvent::MessageDelta(MessageDeltaEvent {
                delta: MessageDelta {
                    stop_reason: stop_reason.map(ToOwned::to_owned),
                    stop_sequence: None,
                },
                usage: Usage {
                    input_tokens: 0,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                    output_tokens: 0,
                },
            })
        }

        // CL2 flip: a non-empty stop_reason now marks the stream terminal.
        assert!(
            super::event_signals_terminal(&delta_event(Some("end_turn"))),
            "MessageDelta with non-empty stop_reason must be terminal (CL2)"
        );
        // ...but it is STILL not meaningful content — the premature-EOF
        // retry gate (`has_emitted_meaningful_content`) is untouched.
        assert!(
            !super::event_is_meaningful_content(&delta_event(Some("end_turn"))),
            "stop_reason delta must remain NON-meaningful (retry gate unchanged)"
        );
        // Empty-string stop_reason is NOT a terminal signal (mirrors the
        // OpenAI choice_finish_reason non-empty filter).
        assert!(!super::event_signals_terminal(&delta_event(Some(""))));
        // stop_reason-less delta: neither terminal nor meaningful.
        assert!(!super::event_signals_terminal(&delta_event(None)));
        assert!(!super::event_is_meaningful_content(&delta_event(None)));
    }

    /// v0.4.17 A5.2 (CL2) — flip of Phase 0's
    /// `char_clean_eof_after_stop_reason_delta_is_still_retry_eligible_today`:
    /// a `stop_reason`-bearing `MessageDelta` now sets `observed_terminal`, so a
    /// clean EOF afterwards (anthropic-compat proxy that never sends
    /// `message_stop`) is judged COMPLETE — no retry fires.
    #[test]
    fn clean_eof_after_stop_reason_delta_is_complete_not_retried() {
        use crate::types::{MessageDelta, MessageDeltaEvent, MessageStopEvent, StreamEvent, Usage};

        // The stream produced a stop_reason-bearing MessageDelta; per CL2 it
        // flips observed_terminal...
        let delta_with_stop = StreamEvent::MessageDelta(MessageDeltaEvent {
            delta: MessageDelta {
                stop_reason: Some("end_turn".to_string()),
                stop_sequence: None,
            },
            usage: Usage {
                input_tokens: 0,
                cache_creation_input_tokens: 0,
                cache_read_input_tokens: 0,
                output_tokens: 0,
            },
        });
        let observed_terminal = super::event_signals_terminal(&delta_with_stop);
        assert!(observed_terminal);

        // ...so the clean-EOF retry gate no longer fires: complete response.
        assert!(
            !super::should_retry_on_premature_eof(
                /* has_emitted_meaningful_content */ false,
                observed_terminal,
                /* parser_errored */ false,
                /* leftover_empty */ true,
                /* stream_retries_remaining */ 2,
            ),
            "stop_reason delta + clean EOF must be complete, not retried (CL2)"
        );

        // MessageStop is unchanged as the canonical terminal frame, so the
        // native Anthropic flow (delta-with-stop_reason THEN message_stop)
        // just sets observed_terminal twice — no behavior change.
        assert!(super::event_signals_terminal(&StreamEvent::MessageStop(
            MessageStopEvent {}
        )));
    }

    /// CL2 companion: a stream with NO terminal signal at all (no
    /// `MessageStop`, no `stop_reason`-bearing delta) is still retry-eligible on
    /// clean EOF — true truncations keep hard-failing/retrying exactly as
    /// before.
    #[test]
    fn clean_eof_without_any_terminal_signal_remains_retry_eligible() {
        use crate::types::{MessageDelta, MessageDeltaEvent, StreamEvent, Usage};

        // A usage-only MessageDelta (stop_reason: None) — common mid-stream
        // frame — must NOT count as terminal...
        let plain_delta = StreamEvent::MessageDelta(MessageDeltaEvent {
            delta: MessageDelta {
                stop_reason: None,
                stop_sequence: None,
            },
            usage: Usage {
                input_tokens: 0,
                cache_creation_input_tokens: 0,
                cache_read_input_tokens: 0,
                output_tokens: 7,
            },
        });
        assert!(!super::event_signals_terminal(&plain_delta));

        // ...so the premature-EOF retry still fires with budget remaining.
        assert!(super::should_retry_on_premature_eof(
            /* has_emitted_meaningful_content */ false,
            /* observed_terminal */ false,
            /* parser_errored */ false,
            /* leftover_empty */ true,
            /* stream_retries_remaining */ 2,
        ));
    }

    /// v0.4.21 #1 — `eof_is_truncation` truth table. A clean EOF is a truncation
    /// (and `next_event` must hard-error instead of returning Ok(None)) iff
    /// meaningful content was delivered to the caller but no terminal signal was
    /// ever observed. Mirrors `should_retry_on_premature_eof_truth_table`.
    #[test]
    fn eof_is_truncation_truth_table() {
        // content emitted + NO terminal → TRUNCATION (hard-error).
        assert!(super::eof_is_truncation(true, false));
        // content emitted + terminal seen → genuinely complete, NOT a truncation.
        assert!(!super::eof_is_truncation(true, true));
        // no content + no terminal → the retry path owns this; an empty Ok(None)
        // is correct, not a truncation error.
        assert!(!super::eof_is_truncation(false, false));
        // no content + terminal → signalled completion (empty but not truncated).
        assert!(!super::eof_is_truncation(false, true));
    }

    /// v0.4.21 #1 safety valve — `ARIS_ALLOW_EOF_WITHOUT_STOP` parsing. Only an
    /// explicit `1`/`true` (case-insensitive) opts back into accept-as-complete;
    /// anything else (incl. unset) keeps the default truncation hard-error.
    #[test]
    fn parse_allow_eof_without_terminal_truth_table() {
        assert!(super::parse_allow_eof_without_terminal(Some("1")));
        assert!(super::parse_allow_eof_without_terminal(Some("true")));
        assert!(super::parse_allow_eof_without_terminal(Some("TRUE")));
        assert!(!super::parse_allow_eof_without_terminal(Some("0")));
        assert!(!super::parse_allow_eof_without_terminal(Some("")));
        // only 1/true count — a stray value does NOT silently disable the guard.
        assert!(!super::parse_allow_eof_without_terminal(Some("yes")));
        assert!(!super::parse_allow_eof_without_terminal(None));
    }

    /// v0.4.21 #1 — composition test (same style as the CL2 tests above):
    /// the codex-required scenarios expressed through the pure helpers that
    /// `next_event`'s EOF branch composes. (a) content + NO message_stop + NO
    /// stop_reason + clean EOF → truncation (Err); (b) stop_reason-only delta +
    /// EOF → complete (CL2 compat path NOT regressed); (c) canonical
    /// message_stop → complete; (d) no content + EOF → not a truncation.
    #[test]
    fn eof_truncation_matches_codex_scenarios() {
        use crate::types::{MessageDelta, MessageDeltaEvent, MessageStopEvent, StreamEvent, Usage};

        let usage = || Usage {
            input_tokens: 0,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            output_tokens: 0,
        };

        // (a) content streamed, then a usage-only delta (stop_reason: None), then
        // clean EOF — no terminal signal ever observed → TRUNCATION → Err.
        let plain_delta = StreamEvent::MessageDelta(MessageDeltaEvent {
            delta: MessageDelta {
                stop_reason: None,
                stop_sequence: None,
            },
            usage: usage(),
        });
        assert!(!super::event_signals_terminal(&plain_delta));
        assert!(
            super::eof_is_truncation(/* content emitted */ true, /* observed_terminal */ false),
            "content + no terminal + clean EOF must be a truncation (Err), not synthesized success"
        );

        // (b) stop_reason-only delta then clean EOF (anthropic-compat proxy that
        // never sends message_stop): observed_terminal=true → COMPLETE, not a
        // truncation. Proves the CL2 compat path is NOT regressed by #1.
        let stop_delta = StreamEvent::MessageDelta(MessageDeltaEvent {
            delta: MessageDelta {
                stop_reason: Some("end_turn".to_string()),
                stop_sequence: None,
            },
            usage: usage(),
        });
        let observed = super::event_signals_terminal(&stop_delta);
        assert!(observed);
        assert!(
            !super::eof_is_truncation(true, observed),
            "stop_reason-only delta + EOF must be complete (CL2 path intact)"
        );

        // (c) canonical message_stop → terminal → complete.
        let observed_stop =
            super::event_signals_terminal(&StreamEvent::MessageStop(MessageStopEvent {}));
        assert!(observed_stop);
        assert!(!super::eof_is_truncation(true, observed_stop));

        // (d) no content emitted + no terminal → not a truncation (retry/empty
        // path owns it; unchanged behavior).
        assert!(!super::eof_is_truncation(false, false));
    }

    /// v0.4.14 C11 — chunk-idle timeout env parser truth table. Pure
    /// helper avoids racing the global env var across parallel tests;
    /// `resolve_stream_idle_timeout()` is a thin env-read wrapper around
    /// this function, so coverage here is sufficient.
    #[test]
    fn resolve_stream_idle_timeout_parses_env() {
        use super::parse_stream_idle_timeout_secs;
        use std::time::Duration;

        // unset → default 120s
        assert_eq!(parse_stream_idle_timeout_secs(None), Some(Duration::from_secs(120)));

        // valid mid-range
        assert_eq!(parse_stream_idle_timeout_secs(Some("30")), Some(Duration::from_secs(30)));

        // below clamp (10s) → clamped up to 10s
        assert_eq!(parse_stream_idle_timeout_secs(Some("5")), Some(Duration::from_secs(10)));

        // above clamp (1800s) → clamped down to 1800s
        assert_eq!(parse_stream_idle_timeout_secs(Some("9999")), Some(Duration::from_secs(1800)));

        // zero → opt-out (None == indefinite wait)
        assert_eq!(parse_stream_idle_timeout_secs(Some("0")), None);

        // negative → opt-out
        assert_eq!(parse_stream_idle_timeout_secs(Some("-1")), None);

        // parse failure → fall back to default 120s, not silently disable
        assert_eq!(parse_stream_idle_timeout_secs(Some("abc")), Some(Duration::from_secs(120)));

        // blank / whitespace-only → treated as missing → default 120s
        assert_eq!(parse_stream_idle_timeout_secs(Some("   ")), Some(Duration::from_secs(120)));

        // exact boundaries → pass through
        assert_eq!(parse_stream_idle_timeout_secs(Some("10")), Some(Duration::from_secs(10)));
        assert_eq!(parse_stream_idle_timeout_secs(Some("1800")), Some(Duration::from_secs(1800)));
    }
}
