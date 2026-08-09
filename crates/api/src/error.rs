use std::env::VarError;
use std::fmt::{Display, Formatter};
use std::time::Duration;

#[derive(Debug)]
pub enum ApiError {
    MissingApiKey,
    ExpiredOAuthToken,
    Auth(String),
    InvalidApiKeyEnv(VarError),
    Http(reqwest::Error),
    Io(std::io::Error),
    Json(serde_json::Error),
    Api {
        status: reqwest::StatusCode,
        error_type: Option<String>,
        message: Option<String>,
        body: String,
        retryable: bool,
    },
    RetriesExhausted {
        attempts: u32,
        last_error: Box<ApiError>,
    },
    InvalidSseFrame(&'static str),
    BackoffOverflow {
        attempt: u32,
        base_delay: Duration,
    },
}

impl ApiError {
    /// v0.4.18: true when the API rejected the request because the *model* is
    /// not available on this account — Anthropic returns HTTP 404 with
    /// `error.type == "not_found_error"` for an unknown/unavailable model on the
    /// messages endpoint. Used to drive the default-model availability chain
    /// (v0.4.24: Opus 5 → 4.8 → 4.7; the only not-found case for this
    /// endpoint). Deliberately NOT matching 400, which covers a broad range of
    /// unrelated request errors.
    #[must_use]
    pub fn is_model_unavailable(&self) -> bool {
        match self {
            Self::Api {
                status,
                error_type,
                ..
            } => status.as_u16() == 404 && error_type.as_deref() == Some("not_found_error"),
            Self::RetriesExhausted { last_error, .. } => last_error.is_model_unavailable(),
            _ => false,
        }
    }

    #[must_use]
    pub fn is_retryable(&self) -> bool {
        match self {
            Self::Http(error) => error.is_connect() || error.is_timeout() || error.is_request(),
            Self::Api { retryable, .. } => *retryable,
            Self::RetriesExhausted { last_error, .. } => last_error.is_retryable(),
            Self::MissingApiKey
            | Self::ExpiredOAuthToken
            | Self::Auth(_)
            | Self::InvalidApiKeyEnv(_)
            | Self::Io(_)
            | Self::Json(_)
            | Self::InvalidSseFrame(_)
            | Self::BackoffOverflow { .. } => false,
        }
    }
}

impl Display for ApiError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingApiKey => {
                write!(
                    f,
                    "ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY is not set; export one before calling the Anthropic API"
                )
            }
            Self::ExpiredOAuthToken => {
                write!(
                    f,
                    "saved OAuth token is expired and no refresh token is available"
                )
            }
            Self::Auth(message) => write!(f, "auth error: {message}"),
            Self::InvalidApiKeyEnv(error) => {
                write!(
                    f,
                    "failed to read ANTHROPIC_AUTH_TOKEN / ANTHROPIC_API_KEY: {error}"
                )
            }
            Self::Http(error) => write!(f, "http error: {error}"),
            Self::Io(error) => write!(f, "io error: {error}"),
            Self::Json(error) => write!(f, "json error: {error}"),
            Self::Api {
                status,
                error_type,
                message,
                body,
                ..
            } => match (error_type, message) {
                (Some(error_type), Some(message)) => {
                    write!(
                        f,
                        "anthropic api returned {status} ({error_type}): {message}"
                    )
                }
                _ => write!(f, "anthropic api returned {status}: {body}"),
            },
            Self::RetriesExhausted {
                attempts,
                last_error,
            } => write!(
                f,
                "anthropic api failed after {attempts} attempts: {last_error}"
            ),
            Self::InvalidSseFrame(message) => write!(f, "invalid sse frame: {message}"),
            Self::BackoffOverflow {
                attempt,
                base_delay,
            } => write!(
                f,
                "retry backoff overflowed on attempt {attempt} with base delay {base_delay:?}"
            ),
        }
    }
}

impl std::error::Error for ApiError {}

impl From<reqwest::Error> for ApiError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

impl From<std::io::Error> for ApiError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for ApiError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

impl From<VarError> for ApiError {
    fn from(value: VarError) -> Self {
        Self::InvalidApiKeyEnv(value)
    }
}

#[cfg(test)]
mod tests {
    use super::ApiError;

    fn api(status: reqwest::StatusCode, error_type: Option<&str>) -> ApiError {
        ApiError::Api {
            status,
            error_type: error_type.map(str::to_string),
            message: Some("model: claude-opus-4-8".to_string()),
            body: String::new(),
            retryable: false,
        }
    }

    // v0.4.18: is_model_unavailable drives the default-model availability chain. It must
    // fire ONLY on the precise "model not found" signal (404 + not_found_error)
    // and never on unrelated request errors.
    #[test]
    fn model_unavailable_only_on_404_not_found() {
        assert!(api(reqwest::StatusCode::NOT_FOUND, Some("not_found_error")).is_model_unavailable());
        // 404 with a different error type is not a model-availability signal.
        assert!(!api(reqwest::StatusCode::NOT_FOUND, Some("rate_limit_error")).is_model_unavailable());
        // 400 (and other statuses) cover unrelated request errors — never fall back.
        assert!(!api(reqwest::StatusCode::BAD_REQUEST, Some("not_found_error")).is_model_unavailable());
        assert!(!api(reqwest::StatusCode::TOO_MANY_REQUESTS, Some("not_found_error")).is_model_unavailable());
        // Non-Api variants never match.
        assert!(!ApiError::MissingApiKey.is_model_unavailable());
    }

    #[test]
    fn model_unavailable_unwraps_retries_exhausted() {
        let inner = api(reqwest::StatusCode::NOT_FOUND, Some("not_found_error"));
        let exhausted = ApiError::RetriesExhausted {
            attempts: 3,
            last_error: Box::new(inner),
        };
        assert!(exhausted.is_model_unavailable());
    }
}
