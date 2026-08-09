use crate::session::Session;

const DEFAULT_INPUT_COST_PER_MILLION: f64 = 15.0;
const DEFAULT_OUTPUT_COST_PER_MILLION: f64 = 75.0;
const DEFAULT_CACHE_CREATION_COST_PER_MILLION: f64 = 18.75;
const DEFAULT_CACHE_READ_COST_PER_MILLION: f64 = 1.5;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModelPricing {
    pub input_cost_per_million: f64,
    pub output_cost_per_million: f64,
    pub cache_creation_cost_per_million: f64,
    pub cache_read_cost_per_million: f64,
}

impl ModelPricing {
    /// Generic fallback pricing tier for UNKNOWN models (`estimate_cost_usd`).
    ///
    /// v0.4.18: this is NO LONGER Sonnet's actual price — Sonnet 4.x is
    /// $3/$15 (see `pricing_for_model`). The name is retained for the
    /// fallthrough-contract test; the value ($15/$75 = the deprecated Opus-4
    /// tier) is kept deliberately as a CONSERVATIVE over-estimate for models
    /// we don't recognize, rather than silently under-billing them.
    #[must_use]
    pub const fn default_sonnet_tier() -> Self {
        Self {
            input_cost_per_million: DEFAULT_INPUT_COST_PER_MILLION,
            output_cost_per_million: DEFAULT_OUTPUT_COST_PER_MILLION,
            cache_creation_cost_per_million: DEFAULT_CACHE_CREATION_COST_PER_MILLION,
            cache_read_cost_per_million: DEFAULT_CACHE_READ_COST_PER_MILLION,
        }
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct TokenUsage {
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cache_creation_input_tokens: u32,
    pub cache_read_input_tokens: u32,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct UsageCostEstimate {
    pub input_cost_usd: f64,
    pub output_cost_usd: f64,
    pub cache_creation_cost_usd: f64,
    pub cache_read_cost_usd: f64,
}

impl UsageCostEstimate {
    #[must_use]
    pub fn total_cost_usd(self) -> f64 {
        self.input_cost_usd
            + self.output_cost_usd
            + self.cache_creation_cost_usd
            + self.cache_read_cost_usd
    }
}

/// Look up per-token pricing for a model. Returns `None` when the model
/// string doesn't match any known family — callers then fall back to a
/// generic Sonnet-tier estimate with `pricing=estimated-default` suffix.
///
/// v0.4.10 (C9 landmine) extended this from "Claude only" to cover the
/// major OpenAI / Gemini / DeepSeek / GLM / MiniMax / Kimi / Xiaomi /
/// Qwen / Doubao families that ARIS-Code already routes to. Prices are
/// USD per million tokens, sourced from each provider's published list
/// at the time of bundling (2026-05; the GPT-5.6 family was added
/// 2026-07 against the then-current official list). They will drift;
/// treat `/cost` as a rough estimate, not billing-grade.
///
/// Cache-tier handling per provider:
/// - **Anthropic**: distinct cache_creation (1.25x input) and cache_read
///   (0.1x input) tiers per the public schedule.
/// - **OpenAI**: automatic prefix-cache; reads billed at 10% of input,
///   no separate write tier (`cache_creation` = `input`).
/// - **DeepSeek V3/V4**: explicit cache-hit / cache-miss pricing in the
///   docs; we use cache-miss rate for `input`/`cache_creation`,
///   cache-hit rate (~10% of input for V4) for `cache_read`.
/// - **All others (Gemini, GLM, MiniMax, Kimi, MiMo, Qwen, Doubao)**:
///   no exposed cache billing; cache_creation = input, cache_read =
///   input/2 (a generic optimistic default).
#[must_use]
pub fn pricing_for_model(model: &str) -> Option<ModelPricing> {
    let m = model.to_ascii_lowercase();

    // ── Anthropic Claude family ──────────────────────────────────
    // v0.4.24: Mythos-class tier (Fable 5 / Mythos 5) = $10/$50, cache write
    // $12.50 / read $1 (verified against Anthropic's published schedule,
    // 2026-08). Checked before the opus/sonnet branches so a Mythos-class id
    // can never be mis-tiered by a family substring.
    if m.contains("fable") || m.contains("mythos") {
        return Some(ModelPricing {
            input_cost_per_million: 10.0,
            output_cost_per_million: 50.0,
            cache_creation_cost_per_million: 12.5,
            cache_read_cost_per_million: 1.0,
        });
    }
    if m.contains("haiku") {
        return Some(ModelPricing {
            input_cost_per_million: 1.0,
            output_cost_per_million: 5.0,
            cache_creation_cost_per_million: 1.25,
            cache_read_cost_per_million: 0.1,
        });
    }
    if m.contains("opus") {
        // v0.4.18: current Opus (4.5/4.6/4.7/4.8 and later) is $5/$25; the
        // DEPRECATED Opus 4.0 / 4.1 keep the legacy $15/$75 tier. Verified
        // against Anthropic's published schedule (2026-06). `has_word` (with
        // `-_/:` boundaries) is used for the legacy check so a FUTURE minor
        // like `opus-4-10` is NOT mis-classified as 4.1 — a bare `contains`
        // would wrongly match `opus-4-1` inside `opus-4-10`.
        let legacy_opus = has_word(&m, "opus-4-0")    // claude-opus-4-0 alias (4.0)
            || has_word(&m, "opus-4-1")               // claude-opus-4-1[-date] (4.1)
            || m.contains("opus-4-2025")              // claude-opus-4-20250514 (dated 4.0)
            || m.ends_with("opus-4"); // bare claude-opus-4 (4.0)
        if legacy_opus {
            return Some(ModelPricing {
                input_cost_per_million: 15.0,
                output_cost_per_million: 75.0,
                cache_creation_cost_per_million: 18.75,
                cache_read_cost_per_million: 1.5,
            });
        }
        return Some(ModelPricing {
            input_cost_per_million: 5.0,
            output_cost_per_million: 25.0,
            cache_creation_cost_per_million: 6.25,
            cache_read_cost_per_million: 0.5,
        });
    }
    if m.contains("sonnet") {
        // v0.4.18: Sonnet 4 / 4.5 / 4.6 are all $3/$15 (verified against
        // Anthropic's published schedule, 2026-06). Previously this returned
        // `default_sonnet_tier()` = $15/$75 (the deprecated Opus-4 tier), a 5x
        // over-estimate. `default_sonnet_tier()` is now ONLY the generic
        // unknown-model fallback (see `estimate_cost_usd`).
        return Some(ModelPricing {
            input_cost_per_million: 3.0,
            output_cost_per_million: 15.0,
            cache_creation_cost_per_million: 3.75,
            cache_read_cost_per_million: 0.30,
        });
    }

    // ── OpenAI families ──────────────────────────────────────────
    // Public price list as of 2026-05 (GPT-5.6 family added 2026-07).
    // cache_read = 10% of input (OpenAI's documented automatic-
    // prefix-cache discount).
    //
    // GPT-5.6 family — WebFetch-verified against the official OpenAI
    // pricing page 2026-07-11 (gpt-5.6-sol $5/$0.50/$30, terra
    // $2.50/$0.25/$15, luna $1/$0.10/$6). ORDER-SENSITIVE: the
    // terra/luna sub-SKUs MUST precede the bare `gpt-5.6` check,
    // which covers gpt-5.6-sol AND bare gpt-5.6 (both flagship tier).
    // Like the gpt-5.5 arm below, `contains` would also match a
    // hypothetical "gpt-5.60" — inherent to this file's contains
    // style, accepted.
    if m.contains("gpt-5.6-terra") {
        return Some(openai_pricing(2.5, 15.0));
    }
    if m.contains("gpt-5.6-luna") {
        return Some(openai_pricing(1.0, 6.0));
    }
    if m.contains("gpt-5.6") {
        return Some(openai_pricing(5.0, 30.0));
    }
    if m.contains("gpt-5.5") {
        return Some(openai_pricing(5.0, 30.0));
    }
    if m.contains("gpt-5.4-nano") {
        return Some(openai_pricing(0.20, 1.25));
    }
    if m.contains("gpt-5.4-mini") {
        return Some(openai_pricing(0.75, 4.5));
    }
    if m.contains("gpt-5.4") {
        return Some(openai_pricing(2.5, 15.0));
    }
    if m.contains("gpt-4o-mini") {
        return Some(openai_pricing(0.15, 0.6));
    }
    if m.contains("gpt-4o") {
        return Some(openai_pricing(2.5, 10.0));
    }
    // o-series reasoning models — match on word boundary to avoid
    // false-positives like "google/o3" being prefix-matched on a
    // provider-prefixed model string.
    if has_word(&m, "o4") {
        return Some(openai_pricing(4.0, 16.0));
    }
    if has_word(&m, "o3") {
        return Some(openai_pricing(2.0, 8.0));
    }
    if has_word(&m, "o1") {
        return Some(openai_pricing(15.0, 60.0));
    }

    // ── Google Gemini ────────────────────────────────────────────
    // Gemini Pro pricing is context-window-tiered (prompts ≤200K vs
    // >200K). We list the small-context tier; long-context users will
    // see /cost as an under-estimate. Tracked for v0.5.0 (full
    // context-aware pricing matrix).
    if m.contains("gemini-2.5-flash") {
        return Some(generic_pricing(0.3, 2.5));
    }
    if m.contains("gemini-2.5-pro") {
        return Some(generic_pricing(2.5, 10.0));
    }
    if m.contains("gemini-2.0-flash") {
        return Some(generic_pricing(0.1, 0.4));
    }

    // ── DeepSeek ────────────────────────────────────────────────
    // V3 / V4 / R1 expose explicit cache hit vs miss rates. cache_read =
    // cache-hit rate; input/cache_creation = cache-miss rate.
    //
    // NOTE: DeepSeek V4 currently ships in Flash and Pro tiers with
    // distinct rates; ARIS-Code v0.4.10 collapses both onto the
    // V3-equivalent cache-miss schedule (0.27 / 1.10 / cache-hit 0.07)
    // pending a context-aware pricing matrix in v0.5.0. Treat /cost
    // as a rough estimate for V4-Pro users; V4-Flash should be close.
    if m.contains("deepseek-v4") {
        return Some(ModelPricing {
            input_cost_per_million: 0.27,
            output_cost_per_million: 1.10,
            cache_creation_cost_per_million: 0.27,
            cache_read_cost_per_million: 0.07,
        });
    }
    if m.contains("deepseek-v3") {
        return Some(ModelPricing {
            input_cost_per_million: 0.27,
            output_cost_per_million: 1.10,
            cache_creation_cost_per_million: 0.27,
            cache_read_cost_per_million: 0.07,
        });
    }
    // DeepSeek-R1: only match the deepseek-prefixed name, NOT bare
    // "*-reasoner" which would catch other providers' reasoners.
    if m.contains("deepseek-r1") || m.contains("deepseek-reasoner") {
        return Some(ModelPricing {
            input_cost_per_million: 0.55,
            output_cost_per_million: 2.19,
            cache_creation_cost_per_million: 0.55,
            cache_read_cost_per_million: 0.14,
        });
    }
    if m.contains("deepseek") {
        return Some(ModelPricing {
            input_cost_per_million: 0.27,
            output_cost_per_million: 1.10,
            cache_creation_cost_per_million: 0.27,
            cache_read_cost_per_million: 0.07,
        });
    }

    // ── Other Chinese providers ─────────────────────────────────
    // No exposed cache-tier billing — generic_pricing (cache_read =
    // input/2, cache_creation = input).
    //
    // v0.4.12 P2 (codex audit): switched from `contains()` to
    // `provider_match()` which requires the family name to be either
    // a model-name prefix (`kimi-k2.5`, `qwen3.6-plus`, `glm-4-plus`)
    // OR appear as a provider segment (`openai/kimi-k2.5`). This
    // protects user-named models like `my-kimi-clone` from being
    // silently routed to the wrong tier while still catching real
    // model identifiers — including those with digit suffixes
    // (`qwen3.6`) that the boundary-based `has_word` would miss.
    if provider_match(&m, "glm") {
        return Some(generic_pricing(0.5, 2.0));
    }
    if provider_match(&m, "minimax") {
        return Some(generic_pricing(0.6, 2.4));
    }
    if provider_match(&m, "kimi") || provider_match(&m, "moonshot") {
        return Some(generic_pricing(0.6, 2.5));
    }
    if provider_match(&m, "mimo") {
        return Some(generic_pricing(0.4, 1.6));
    }
    if provider_match(&m, "qwen") {
        return Some(generic_pricing(0.4, 1.6));
    }
    if provider_match(&m, "doubao") {
        return Some(generic_pricing(0.3, 1.2));
    }

    None
}

/// v0.4.12 P2 — provider family name match. Recognises the prefix at the
/// start of a model name (`kimi-k2.5`, `qwen3.6-plus`) OR after a `/`
/// provider segment separator (`openai/kimi-foo`, `provider:moonshot-v1`).
/// Rejects mid-word matches (`my-kimi-clone`) which `contains()` would
/// have caught. More permissive than `has_word` for cases where the
/// suffix is a digit (Qwen versioning).
fn provider_match(model: &str, prefix: &str) -> bool {
    if prefix.is_empty() {
        return false;
    }
    if model.starts_with(prefix) {
        return true;
    }
    // provider-prefixed forms: "openai/kimi-...", "proxy:moonshot-..."
    for sep in &['/', ':'] {
        let needle = format!("{sep}{prefix}");
        if model.contains(&needle) {
            return true;
        }
    }
    false
}

/// OpenAI pricing helper. cache_read = 10% of input — OpenAI's
/// documented automatic-prefix-cache discount (e.g. GPT-5.5 input 5.0
/// → cached input 0.50; GPT-5.4 2.5 → 0.25; -mini 0.75 → 0.075).
/// Previously this was input/2; Codex audit caught the mismatch.
/// cache_creation = input (OpenAI bills writes at the regular input
/// rate since caching is silent / automatic).
fn openai_pricing(input: f64, output: f64) -> ModelPricing {
    ModelPricing {
        input_cost_per_million: input,
        output_cost_per_million: output,
        cache_creation_cost_per_million: input,
        cache_read_cost_per_million: input * 0.1,
    }
}

/// Generic pricing fallback for providers that don't publish a separate
/// cache-tier rate. Approximates with cache_read = input/2 (optimistic;
/// real billing is at full input rate unless the provider quietly
/// supports prefix caching). cache_creation = input.
fn generic_pricing(input: f64, output: f64) -> ModelPricing {
    ModelPricing {
        input_cost_per_million: input,
        output_cost_per_million: output,
        cache_creation_cost_per_million: input,
        cache_read_cost_per_million: input / 2.0,
    }
}

/// Word-boundary check so model fragments like `o3` don't accidentally
/// match `gpt-5.4-nano` or `provider-prefixed-o3-foo` from earlier
/// branches. Treats `-`, `_`, `/`, `:` and start-of-string as word
/// boundaries.
///
/// v0.4.16 P7: forwards to the canonical [`crate::text_match::word_match`]
/// (this was one of three verbatim copies; behavior is unchanged).
fn has_word(haystack: &str, needle: &str) -> bool {
    crate::text_match::word_match(haystack, needle)
}

impl TokenUsage {
    #[must_use]
    pub fn total_tokens(self) -> u32 {
        self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
    }

    #[must_use]
    pub fn estimate_cost_usd(self) -> UsageCostEstimate {
        self.estimate_cost_usd_with_pricing(ModelPricing::default_sonnet_tier())
    }

    #[must_use]
    pub fn estimate_cost_usd_with_pricing(self, pricing: ModelPricing) -> UsageCostEstimate {
        UsageCostEstimate {
            input_cost_usd: cost_for_tokens(self.input_tokens, pricing.input_cost_per_million),
            output_cost_usd: cost_for_tokens(self.output_tokens, pricing.output_cost_per_million),
            cache_creation_cost_usd: cost_for_tokens(
                self.cache_creation_input_tokens,
                pricing.cache_creation_cost_per_million,
            ),
            cache_read_cost_usd: cost_for_tokens(
                self.cache_read_input_tokens,
                pricing.cache_read_cost_per_million,
            ),
        }
    }

    #[must_use]
    pub fn summary_lines(self, label: &str) -> Vec<String> {
        self.summary_lines_for_model(label, None)
    }

    #[must_use]
    pub fn summary_lines_for_model(self, label: &str, model: Option<&str>) -> Vec<String> {
        let pricing = model.and_then(pricing_for_model);
        let cost = pricing.map_or_else(
            || self.estimate_cost_usd(),
            |pricing| self.estimate_cost_usd_with_pricing(pricing),
        );
        let model_suffix =
            model.map_or_else(String::new, |model_name| format!(" model={model_name}"));
        let pricing_suffix = if pricing.is_some() {
            ""
        } else if model.is_some() {
            " pricing=estimated-default"
        } else {
            ""
        };
        vec![
            format!(
                "{label}: total_tokens={} input={} output={} cache_write={} cache_read={} estimated_cost={}{}{}",
                self.total_tokens(),
                self.input_tokens,
                self.output_tokens,
                self.cache_creation_input_tokens,
                self.cache_read_input_tokens,
                format_usd(cost.total_cost_usd()),
                model_suffix,
                pricing_suffix,
            ),
            format!(
                "  cost breakdown: input={} output={} cache_write={} cache_read={}",
                format_usd(cost.input_cost_usd),
                format_usd(cost.output_cost_usd),
                format_usd(cost.cache_creation_cost_usd),
                format_usd(cost.cache_read_cost_usd),
            ),
        ]
    }
}

fn cost_for_tokens(tokens: u32, usd_per_million_tokens: f64) -> f64 {
    f64::from(tokens) / 1_000_000.0 * usd_per_million_tokens
}

#[must_use]
pub fn format_usd(amount: f64) -> String {
    format!("${amount:.4}")
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct UsageTracker {
    latest_turn: TokenUsage,
    cumulative: TokenUsage,
    turns: u32,
}

impl UsageTracker {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn from_session(session: &Session) -> Self {
        let mut tracker = Self::new();
        for message in &session.messages {
            if let Some(usage) = message.usage {
                tracker.record(usage);
            }
        }
        tracker
    }

    pub fn record(&mut self, usage: TokenUsage) {
        self.latest_turn = usage;
        self.cumulative.input_tokens += usage.input_tokens;
        self.cumulative.output_tokens += usage.output_tokens;
        self.cumulative.cache_creation_input_tokens += usage.cache_creation_input_tokens;
        self.cumulative.cache_read_input_tokens += usage.cache_read_input_tokens;
        self.turns += 1;
    }

    #[must_use]
    pub fn current_turn_usage(&self) -> TokenUsage {
        self.latest_turn
    }

    #[must_use]
    pub fn cumulative_usage(&self) -> TokenUsage {
        self.cumulative
    }

    #[must_use]
    pub fn turns(&self) -> u32 {
        self.turns
    }
}

#[cfg(test)]
mod tests {
    // Test docs reference matrix IDs like `matrix[39]` and bare provider
    // names (OpenAI, DeepSeek, IEEE-754) for traceability; the pedantic
    // `doc_markdown` lint wants every such token backticked. These are
    // test-only docs, so we silence it module-wide rather than peppering
    // backticks through prose.
    #![allow(clippy::doc_markdown)]

    use super::{
        format_usd, has_word, pricing_for_model, provider_match, TokenUsage, UsageTracker,
    };
    use crate::session::{ContentBlock, ConversationMessage, MessageRole, Session};

    // ── Characterization-test helpers (v0.4.16 Phase 0, T2) ─────────────
    //
    // These are GOLDEN-MASTER tests: they lock what `pricing_for_model`
    // *actually computes today*, NOT what it "should" compute. They exist
    // to guard the upcoming P7 provider-routing refactor. `pricing_for_model`
    // is a SEQUENCE-SENSITIVE if-else chain mixing THREE match strategies:
    //   * `contains()`     — claude / gpt-N / gemini / deepseek families
    //   * `has_word()`     — o-series (o4/o3/o1), word-boundary only
    //   * `provider_match()` — Chinese OSS providers, prefix/segment only
    // Re-ordering or unifying these branches would silently mis-price by up
    // to 12.5x (e.g. gpt-5.4-nano $0.20 vs gpt-5.4 $2.50 = 12.5x). Each test
    // documents WHICH branch it pins and WHY the order matters.
    //
    // Discipline: if a test fails, the CODE is source of truth — update the
    // expected value and record the discrepancy, never weaken the assertion.

    /// Assert all four per-million tiers of a resolved `ModelPricing`.
    ///
    /// input / output / cache_creation are stored verbatim from f64 literals
    /// in the chain, so they get EXACT equality. cache_read is always a
    /// DERIVED product (`input * 0.1` for OpenAI, `input / 2.0` for generic,
    /// or a verbatim Anthropic/DeepSeek literal), so IEEE-754 rounding can
    /// make e.g. `0.20 * 0.1 == 0.020000000000000004 != 0.02`. We therefore
    /// compare cache_read within a 1e-12 absolute tolerance — far tighter
    /// than ANY real pricing-tier gap (smallest is 0.005), so this still
    /// catches a wrong tier (off by 0.01+) while ignoring the last-ULP noise
    /// that is the code's actual output. (Code stays source of truth.)
    fn assert_pricing(model: &str, input: f64, output: f64, cc: f64, cr: f64) {
        let p = pricing_for_model(model)
            .unwrap_or_else(|| panic!("expected `{model}` to resolve to a pricing tier"));
        // 1e-12 abs tolerance on every field. input/output/cc are stored
        // verbatim so they match to the bit; cache_read is derived
        // (`input*0.1` / `input/2`) and carries last-ULP noise. The
        // tolerance is ~9 orders of magnitude below the smallest real tier
        // gap (0.005), so a wrong tier still fails loudly while ULP noise is
        // absorbed. Using `abs() < eps` (not `assert_eq!`) also keeps clippy
        // `float_cmp` quiet without an `#[allow]`.
        let close = |got: f64, want: f64, field: &str| {
            assert!(
                (got - want).abs() < 1e-12,
                "{field} tier mismatch for `{model}`: got {got}, expected ~{want}"
            );
        };
        close(p.input_cost_per_million, input, "input");
        close(p.output_cost_per_million, output, "output");
        close(p.cache_creation_cost_per_million, cc, "cache_creation");
        close(p.cache_read_cost_per_million, cr, "cache_read");
    }

    #[test]
    fn tracks_true_cumulative_usage() {
        let mut tracker = UsageTracker::new();
        tracker.record(TokenUsage {
            input_tokens: 10,
            output_tokens: 4,
            cache_creation_input_tokens: 2,
            cache_read_input_tokens: 1,
        });
        tracker.record(TokenUsage {
            input_tokens: 20,
            output_tokens: 6,
            cache_creation_input_tokens: 3,
            cache_read_input_tokens: 2,
        });

        assert_eq!(tracker.turns(), 2);
        assert_eq!(tracker.current_turn_usage().input_tokens, 20);
        assert_eq!(tracker.current_turn_usage().output_tokens, 6);
        assert_eq!(tracker.cumulative_usage().output_tokens, 10);
        assert_eq!(tracker.cumulative_usage().input_tokens, 30);
        assert_eq!(tracker.cumulative_usage().total_tokens(), 48);
    }

    #[test]
    fn computes_cost_summary_lines() {
        let usage = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 500_000,
            cache_creation_input_tokens: 100_000,
            cache_read_input_tokens: 200_000,
        };

        let cost = usage.estimate_cost_usd();
        assert_eq!(format_usd(cost.input_cost_usd), "$15.0000");
        assert_eq!(format_usd(cost.output_cost_usd), "$37.5000");
        let lines = usage.summary_lines_for_model("usage", Some("claude-sonnet-4-20250514"));
        // v0.4.18 DELIBERATE: Sonnet is now $3/$15/$3.75/$0.30 (was the wrong
        // $15/$75 deprecated-Opus tier). 1M*$3 + 0.5M*$15 + 0.1M*$3.75 +
        // 0.2M*$0.30 = 3 + 7.5 + 0.375 + 0.06 = $10.9350; cache_read 0.2M*$0.30
        // = $0.0600. (Note: the model-less estimate_cost_usd above still uses
        // the unchanged $15/$75 generic fallback — proving the decoupling.)
        assert!(lines[0].contains("estimated_cost=$10.9350"));
        assert!(lines[0].contains("model=claude-sonnet-4-20250514"));
        assert!(lines[1].contains("cache_read=$0.0600"));
    }

    #[test]
    fn supports_model_specific_pricing() {
        let usage = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 500_000,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
        };

        let haiku = pricing_for_model("claude-haiku-4-5-20251001").expect("haiku pricing");
        let opus = pricing_for_model("claude-opus-4-7").expect("opus pricing");
        let haiku_cost = usage.estimate_cost_usd_with_pricing(haiku);
        let opus_cost = usage.estimate_cost_usd_with_pricing(opus);
        assert_eq!(format_usd(haiku_cost.total_cost_usd()), "$3.5000");
        // v0.4.18 DELIBERATE: opus-4-7 is a CURRENT Opus ($5/$25), not the
        // deprecated $15/$75 tier. 1M in + 0.5M out = $5 + $12.5 = $17.50.
        assert_eq!(format_usd(opus_cost.total_cost_usd()), "$17.5000");
    }

    #[test]
    fn marks_unknown_model_pricing_as_fallback() {
        let usage = TokenUsage {
            input_tokens: 100,
            output_tokens: 100,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
        };
        let lines = usage.summary_lines_for_model("usage", Some("custom-model"));
        assert!(lines[0].contains("pricing=estimated-default"));
    }

    #[test]
    fn reconstructs_usage_from_session_messages() {
        let session = Session {
            version: 1,
            messages: vec![ConversationMessage {
                role: MessageRole::Assistant,
                blocks: vec![ContentBlock::Text {
                    text: "done".to_string(),
                }],
                usage: Some(TokenUsage {
                    input_tokens: 5,
                    output_tokens: 2,
                    cache_creation_input_tokens: 1,
                    cache_read_input_tokens: 0,
                }),
            }],
        };

        let tracker = UsageTracker::from_session(&session);
        assert_eq!(tracker.turns(), 1);
        assert_eq!(tracker.cumulative_usage().total_tokens(), 8);
    }

    // v0.4.13 regression — v0.4.12 P2 swapped the OSS provider lookup from
    // `contains()` to `provider_match()`. That match requires the family
    // name to appear at start-of-string OR after a `/`/`:` provider
    // separator — never mid-word. This guards against three landmines at
    // once:
    //   (a) real model names (`kimi-k2.5`, `qwen3.6-plus`, `glm-4-plus`)
    //       still resolve, including digit-suffix versions that
    //       `has_word` would miss.
    //   (b) provider-prefixed names (`openai/kimi-k2.5`) resolve via the
    //       slash branch.
    //   (c) user-named models with a family substring in the middle
    //       (`my-kimi-clone`) do NOT silently route to the wrong tier —
    //       they fall through to `None` so callers see the
    //       `pricing=estimated-default` marker.
    // Note: the start-of-string branch is intentionally permissive, so
    // `kimiclone-foo` does match — documented behaviour we want to keep
    // pinned so future tightening doesn't accidentally break the real
    // `kimi-...` names.
    #[test]
    fn provider_match_distinguishes_real_vs_userdefined() {
        // Real model names — must resolve to the family tier.
        assert!(
            pricing_for_model("qwen3.6-plus").is_some(),
            "qwen3.6-plus is a real Qwen model and must price"
        );
        assert!(
            pricing_for_model("kimi-k2.5").is_some(),
            "kimi-k2.5 is a real Kimi model and must price"
        );
        assert!(
            pricing_for_model("glm-4-plus").is_some(),
            "glm-4-plus is a real GLM model and must price"
        );

        // Provider-prefixed forms must resolve via the `/` branch.
        assert!(
            pricing_for_model("openai/kimi-k2.5").is_some(),
            "openai/kimi-k2.5 must resolve via provider-prefix branch"
        );

        // Mid-word matches must NOT route — falls through to None so
        // callers see pricing=estimated-default rather than silently
        // billing at the Kimi tier for a user model that happens to
        // contain the substring.
        assert!(
            pricing_for_model("my-kimi-clone").is_none(),
            "my-kimi-clone must NOT match Kimi family (mid-word rejection)"
        );

        // Start-of-string matches stay permissive (documented behaviour).
        assert!(
            pricing_for_model("kimiclone-foo").is_some(),
            "kimiclone-foo starts with `kimi` so the provider_match prefix branch fires"
        );
    }

    // ════════════════════════════════════════════════════════════════════
    // CHARACTERIZATION TESTS (v0.4.16 Phase 0, agent T2)
    // Golden master of `pricing_for_model` — pins TODAY'S routing for the
    // P7 provider-routing refactor. Maps to design_raw.json
    // characterization_test_matrix items 39-67 (price_*) plus added coverage.
    // ════════════════════════════════════════════════════════════════════

    // ── Anthropic Claude family (`contains` strategy) ───────────────────

    /// matrix[39] price_haiku — `contains("haiku")`, FIRST branch in chain.
    #[test]
    fn price_haiku() {
        assert_pricing("claude-haiku-4-5", 1.0, 5.0, 1.25, 0.1);
    }

    /// matrix[40] price_opus — `contains("opus")`, CURRENT tier.
    /// v0.4.18 DELIBERATE: current Opus (4.5–4.8) is $5/$25/$6.25/$0.50, NOT
    /// the old $15/$75 (which was the deprecated Opus-4 tier).
    /// v0.4.24: Opus 5 shares the current tier (verified 2026-08) — pinned so
    /// a future legacy-classification tweak can't accidentally mis-tier it.
    #[test]
    fn price_opus() {
        assert_pricing("claude-opus-4-8", 5.0, 25.0, 6.25, 0.5);
        assert_pricing("claude-opus-5", 5.0, 25.0, 6.25, 0.5);
    }

    /// v0.4.24 — Mythos-class tier (Fable 5 / Mythos 5) = $10/$50/$12.50/$1,
    /// verified against Anthropic's published schedule 2026-08. `fable`
    /// contains no other family substring, so without this branch it fell
    /// through to the conservative unknown-model tier ($15/$75) — a 1.5×
    /// over-estimate.
    #[test]
    fn price_fable_mythos() {
        assert_pricing("claude-fable-5", 10.0, 50.0, 12.5, 1.0);
        assert_pricing("claude-mythos-5", 10.0, 50.0, 12.5, 1.0);
    }

    /// v0.4.18 — deprecated Opus 4.0 / 4.1 keep the legacy $15/$75 tier; locks
    /// the tier-split so a current-minor (4.5+) never falls into legacy and a
    /// legacy id never falls into current. `has_word` boundary handling means
    /// `opus-4-1` matches 4.1 but NOT a future `opus-4-10`.
    #[test]
    fn price_opus_legacy() {
        assert_pricing("claude-opus-4-1", 15.0, 75.0, 18.75, 1.5);
        assert_pricing("claude-opus-4-20250514", 15.0, 75.0, 18.75, 1.5);
    }

    /// matrix[41] price_sonnet — `contains("sonnet")`.
    /// v0.4.18 DELIBERATE: Sonnet 4.x is $3/$15/$3.75/$0.30 (was wrongly the
    /// $15/$75 deprecated-Opus tier). No longer aligned with opus.
    /// v0.4.24: Sonnet 5 rides the same branch. Its $2/$10 introductory
    /// pricing (through 2026-08-31) is DELIBERATELY not modelled — the
    /// standard $3/$15 takes effect 2026-09-01 and a time-dependent price
    /// table isn't worth the complexity for a ≤1-month conservative
    /// over-estimate.
    #[test]
    fn price_sonnet() {
        assert_pricing("claude-sonnet-4-6", 3.0, 15.0, 3.75, 0.30);
        assert_pricing("claude-sonnet-5", 3.0, 15.0, 3.75, 0.30);
    }

    // ── OpenAI GPT families (`contains`, ORDER-SENSITIVE) ───────────────
    // openai_pricing(input, output): cache_creation = input,
    // cache_read = input * 0.1 (10% prefix-cache discount).

    /// v0.4.22 B4 — gpt-5.6 flagship: `contains("gpt-5.6")` covers the
    /// -sol SKU (and bare gpt-5.6, pinned below). WebFetch-verified against
    /// the official OpenAI pricing page 2026-07-11: $5/$30, cr = 5.0*0.1
    /// = 0.5.
    #[test]
    fn price_gpt56_sol_flagship_tier() {
        assert_pricing("gpt-5.6-sol", 5.0, 30.0, 5.0, 0.5);
    }

    /// v0.4.22 B4 — ORDER-SENSITIVE: `gpt-5.6-terra` MUST be checked
    /// BEFORE `gpt-5.6` (which `contains` would also match). If reordered,
    /// this $2.50 model gets billed at $5 = 2x. cr = 2.5*0.1 = 0.25.
    #[test]
    fn price_gpt56_terra_order_before_base() {
        assert_pricing("gpt-5.6-terra", 2.5, 15.0, 2.5, 0.25);
    }

    /// v0.4.22 B4 — ORDER-SENSITIVE: `gpt-5.6-luna` before `gpt-5.6`.
    /// cr = 1.0*0.1 = 0.10.
    #[test]
    fn price_gpt56_luna_order_before_base() {
        assert_pricing("gpt-5.6-luna", 1.0, 6.0, 1.0, 0.10);
    }

    /// v0.4.22 B4 — bare `gpt-5.6` (no SKU suffix) prices at the flagship
    /// tier, same as -sol.
    #[test]
    fn price_gpt56_bare_flagship_tier() {
        assert_pricing("gpt-5.6", 5.0, 30.0, 5.0, 0.5);
    }

    /// v0.4.22 B4 — provider-prefixed `openai/gpt-5.6-sol` still routes to
    /// the flagship tier (`contains` ignores the provider segment).
    #[test]
    fn price_gpt56_provider_prefixed_sol() {
        assert_pricing("openai/gpt-5.6-sol", 5.0, 30.0, 5.0, 0.5);
    }

    /// v0.4.22 B4 — near-miss `gpt-5.7` matches NO branch (not 5.6, not
    /// 5.5, not 5.4) -> None -> callers fall back to default_sonnet_tier
    /// with the `pricing=estimated-default` marker (same fallthrough
    /// contract as matrix[67]).
    #[test]
    fn price_gpt57_near_miss_falls_through_to_default() {
        assert!(
            pricing_for_model("gpt-5.7").is_none(),
            "gpt-5.7 must NOT match any gpt-5.x arm (near-miss falls through)"
        );
        let usage = TokenUsage {
            input_tokens: 100,
            output_tokens: 100,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
        };
        let lines = usage.summary_lines_for_model("usage", Some("gpt-5.7"));
        assert!(
            lines[0].contains("pricing=estimated-default"),
            "gpt-5.7 summary must carry the estimated-default marker"
        );
    }

    /// matrix[42] price_gpt55 — `contains("gpt-5.5")`. cr = 5.0*0.1 = 0.5.
    #[test]
    fn price_gpt55() {
        assert_pricing("gpt-5.5", 5.0, 30.0, 5.0, 0.5);
    }

    /// codex Phase-0 gap #2 — contains-vs-word_match discriminator for the
    /// pricing chain. `xxgpt-5.5yy` has NO word boundary around `gpt-5.5`
    /// (`x`/`y` are not in the -_/: set), so it routes to GPT-5.5 pricing ONLY
    /// because the chain uses `contains("gpt-5.5")`. If a refactor ever
    /// converts this branch to a word-boundary match, this case flips to the
    /// estimated-default tier and the assert fails — the regression we want to
    /// catch. (The order-sensitive `price_gpt54_*` cases use hyphen-bounded
    /// hosts and so do not exercise this axis.)
    #[test]
    fn price_contains_strategy_is_bare_substring() {
        assert_pricing("xxgpt-5.5yy", 5.0, 30.0, 5.0, 0.5);
    }

    /// matrix[43] price_gpt54_nano_order — ORDER-SENSITIVE: `gpt-5.4-nano`
    /// MUST be checked BEFORE `gpt-5.4` (which `contains` would also match).
    /// If reordered, this $0.20 model gets billed at $2.50 = 12.5x. cr=0.02.
    #[test]
    fn price_gpt54_nano_order_before_base() {
        assert_pricing("gpt-5.4-nano", 0.20, 1.25, 0.20, 0.02);
    }

    /// matrix[44] price_gpt54_mini_order — ORDER-SENSITIVE: `gpt-5.4-mini`
    /// before `gpt-5.4`. cr = 0.75*0.1 = 0.075.
    #[test]
    fn price_gpt54_mini_order_before_base() {
        assert_pricing("gpt-5.4-mini", 0.75, 4.5, 0.75, 0.075);
    }

    /// matrix[45] price_gpt54 — `contains("gpt-5.4")` base tier, reached
    /// only AFTER nano/mini have failed. cr = 2.5*0.1 = 0.25.
    #[test]
    fn price_gpt54_base() {
        assert_pricing("gpt-5.4", 2.5, 15.0, 2.5, 0.25);
    }

    /// matrix[46] price_gpt4o_mini_order — ORDER-SENSITIVE: `gpt-4o-mini`
    /// before `gpt-4o`. cr = 0.15*0.1 = 0.015.
    #[test]
    fn price_gpt4o_mini_order_before_base() {
        assert_pricing("gpt-4o-mini", 0.15, 0.6, 0.15, 0.015);
    }

    /// matrix[47] price_gpt4o — `contains("gpt-4o")` base. cr = 0.25.
    #[test]
    fn price_gpt4o_base() {
        assert_pricing("gpt-4o", 2.5, 10.0, 2.5, 0.25);
    }

    // ── OpenAI o-series (`has_word`, word-boundary strategy) ────────────

    /// matrix[48] price_o4_mini — `has_word("o4")` with `-mini` boundary.
    /// cr = 4.0*0.1 = 0.4.
    #[test]
    fn price_o4_mini_has_word() {
        assert_pricing("o4-mini", 4.0, 16.0, 4.0, 0.4);
    }

    /// matrix[49] price_o3 — bare `o3`, `has_word` start+end boundary.
    /// cr = 2.0*0.1 = 0.2.
    #[test]
    fn price_o3_bare_has_word() {
        assert_pricing("o3", 2.0, 8.0, 2.0, 0.2);
    }

    /// matrix[50] price_o1_preview — `has_word("o1")` with `-preview`
    /// boundary. cr = 15.0*0.1 = 1.5.
    #[test]
    fn price_o1_preview_has_word() {
        assert_pricing("o1-preview", 15.0, 60.0, 15.0, 1.5);
    }

    /// matrix[51] price_google_o3_to_openai — FEATURE: a provider-prefixed
    /// o-series model `google/o3` routes to the OpenAI o3 PRICE because
    /// `has_word` treats `/` as a boundary. The `google/` provider segment
    /// is intentionally ignored for pricing. Pins this cross-provider quirk.
    #[test]
    fn price_google_slash_o3_routes_to_openai() {
        assert_pricing("google/o3", 2.0, 8.0, 2.0, 0.2);
    }

    /// Added: `o3-mini` resolves to the o3 price tier (has_word `o3` with
    /// trailing `-` boundary). Mirrors reasoning matrix[20].
    #[test]
    fn price_o3_mini_has_word() {
        assert_pricing("o3-mini", 2.0, 8.0, 2.0, 0.2);
    }

    /// Added: mid-word `o32-mini` must NOT match the o3 tier (has_word
    /// rejects `o32` because `2` is not a boundary). Mirrors matrix[23].
    /// It also matches no other branch -> None -> estimated-default.
    #[test]
    fn price_o32_midword_rejected() {
        assert!(
            pricing_for_model("o32-mini").is_none(),
            "o32-mini must NOT route to o3 tier (has_word mid-word rejection)"
        );
    }

    // ── Google Gemini (`contains`, ORDER-SENSITIVE) ─────────────────────
    // generic_pricing(input, output): cache_creation = input,
    // cache_read = input / 2.

    /// matrix[52] price_gemini_flash_order — ORDER-SENSITIVE: `gemini-2.5-
    /// flash` MUST precede `gemini-2.5-pro` (both share the `gemini-2.5-`
    /// stem; pro's `contains` would NOT match flash, but flash's would not
    /// match pro — the real risk is a future merge). cr = 0.3/2 = 0.15.
    #[test]
    fn price_gemini_25_flash_order_before_pro() {
        assert_pricing("gemini-2.5-flash", 0.3, 2.5, 0.3, 0.15);
    }

    /// matrix[53] price_gemini_pro — `contains("gemini-2.5-pro")`.
    /// cr = 2.5/2 = 1.25.
    #[test]
    fn price_gemini_25_pro() {
        assert_pricing("gemini-2.5-pro", 2.5, 10.0, 2.5, 1.25);
    }

    /// matrix[54] price_gemini_20_flash — `contains("gemini-2.0-flash")`.
    /// cr = 0.1/2 = 0.05.
    #[test]
    fn price_gemini_20_flash() {
        assert_pricing("gemini-2.0-flash", 0.1, 0.4, 0.1, 0.05);
    }

    // ── DeepSeek (`contains`, ORDER-SENSITIVE + explicit cache tiers) ───

    /// matrix[55] price_deepseek_v4_order — ORDER-SENSITIVE: `deepseek-v4`
    /// before `deepseek-v3`. v4 happens to share v3's numerics today, so a
    /// reorder would not change the price — but this pins that they remain
    /// identical (the chain intentionally lists them separately).
    #[test]
    fn price_deepseek_v4_order_before_v3() {
        assert_pricing("deepseek-v4", 0.27, 1.10, 0.27, 0.07);
    }

    /// matrix[56] price_deepseek_v3 — `contains("deepseek-v3")`.
    #[test]
    fn price_deepseek_v3() {
        assert_pricing("deepseek-v3", 0.27, 1.10, 0.27, 0.07);
    }

    /// matrix[57] price_deepseek_r1 — both `deepseek-r1` and
    /// `deepseek-reasoner` alias to the R1 tier. Higher than v3/v4.
    #[test]
    fn price_deepseek_r1_and_reasoner_alias() {
        assert_pricing("deepseek-r1", 0.55, 2.19, 0.55, 0.14);
        assert_pricing("deepseek-reasoner", 0.55, 2.19, 0.55, 0.14);
    }

    /// matrix[58] price_deepseek_chat_fallthrough — `deepseek-chat` matches
    /// none of the v4/v3/r1 specific branches and falls through to the bare
    /// `contains("deepseek")` catch-all (v3-equivalent rate). ORDER-SENSITIVE:
    /// the bare branch MUST come LAST among deepseek branches.
    #[test]
    fn price_deepseek_chat_bare_fallthrough() {
        assert_pricing("deepseek-chat", 0.27, 1.10, 0.27, 0.07);
    }

    // ── Chinese OSS providers (`provider_match`, prefix/segment strategy) ─

    /// matrix[59] price_glm — `provider_match("glm")` start-of-string.
    /// generic cr = 0.5/2 = 0.25.
    #[test]
    fn price_glm() {
        assert_pricing("glm-4-plus", 0.5, 2.0, 0.5, 0.25);
    }

    /// matrix[60] price_minimax — `provider_match("minimax")` start-of-string
    /// (lowercased, so `MiniMax-...` also matches). cr = 0.6/2 = 0.3.
    #[test]
    fn price_minimax() {
        assert_pricing("minimax-m2.7", 0.6, 2.4, 0.6, 0.3);
        // Case-insensitive: chain lowercases first, so the real cased name
        // `MiniMax-M2.7` resolves identically.
        assert_pricing("MiniMax-M2.7", 0.6, 2.4, 0.6, 0.3);
    }

    /// matrix[61] price_kimi_moonshot — both `kimi` and `moonshot` prefixes
    /// share the same tier (Moonshot is Kimi's vendor). cr = 0.6/2 = 0.3.
    #[test]
    fn price_kimi_and_moonshot() {
        assert_pricing("kimi-k2.5", 0.6, 2.5, 0.6, 0.3);
        assert_pricing("moonshot-v1", 0.6, 2.5, 0.6, 0.3);
    }

    /// matrix[62] price_provider_prefix_kimi — `openai/kimi-k2.5` resolves
    /// via the `/kimi` provider-segment branch of `provider_match`. Pins
    /// that a provider-prefixed OSS name still prices at its OWN tier
    /// (NOT openai) — note this differs from the o-series quirk where
    /// `google/o3` routes to the OPENAI price.
    #[test]
    fn price_provider_prefix_kimi_resolves_kimi_tier() {
        assert_pricing("openai/kimi-k2.5", 0.6, 2.5, 0.6, 0.3);
    }

    /// matrix[63] price_my_kimi_clone_rejected — CRITICAL mid-word rejection:
    /// `my-kimi-clone` has `kimi` in the MIDDLE (no start, no `/`/`:` sep),
    /// so `provider_match` returns false -> None -> estimated-default sonnet
    /// tier. Protects user-named models from silently billing at Kimi rate.
    #[test]
    fn price_my_kimi_clone_midword_rejected() {
        assert!(
            pricing_for_model("my-kimi-clone").is_none(),
            "my-kimi-clone must NOT route to Kimi tier (provider_match mid-word reject)"
        );
    }

    /// matrix[64] price_kimiclone_permissive — PINNED documented behaviour:
    /// `kimiclone-foo` STARTS WITH `kimi`, so `provider_match`'s
    /// `starts_with` branch fires and it prices at the Kimi tier. This is
    /// intentionally permissive; pinned so a future tightening of
    /// provider_match doesn't silently break real `kimi-...` names.
    #[test]
    fn price_kimiclone_starts_with_permissive() {
        assert_pricing("kimiclone-foo", 0.6, 2.5, 0.6, 0.3);
    }

    /// matrix[65] price_qwen_digit_suffix — `qwen3.6-plus`: the family name
    /// is immediately followed by a DIGIT (`3`). `provider_match` uses
    /// `starts_with` so it matches; the boundary-based `has_word` would
    /// REJECT this (digit is not a boundary). Pins the reason provider_match
    /// is more permissive than has_word for version-suffixed names.
    #[test]
    fn price_qwen_digit_suffix() {
        assert_pricing("qwen3.6-plus", 0.4, 1.6, 0.4, 0.2);
    }

    /// matrix[66] price_mimo_doubao — remaining two providers.
    /// mimo generic(0.4,1.6) cr=0.2; doubao generic(0.3,1.2) cr=0.15.
    #[test]
    fn price_mimo_and_doubao() {
        assert_pricing("mimo-7b", 0.4, 1.6, 0.4, 0.2);
        assert_pricing("doubao-pro", 0.3, 1.2, 0.3, 0.15);
    }

    /// matrix[67] price_unknown_none — a model matching NO branch returns
    /// None; the caller then appends ` pricing=estimated-default` and falls
    /// back to default_sonnet_tier. Pins the fallthrough contract.
    #[test]
    fn price_unknown_returns_none_and_marks_default() {
        assert!(
            pricing_for_model("custom-model").is_none(),
            "unknown model must return None"
        );
        let usage = TokenUsage {
            input_tokens: 100,
            output_tokens: 100,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
        };
        let lines = usage.summary_lines_for_model("usage", Some("custom-model"));
        assert!(
            lines[0].contains("pricing=estimated-default"),
            "unknown model summary must carry estimated-default marker"
        );
    }

    // ── Cross-strategy boundary cases (added by T2) ─────────────────────

    /// Added: pins that the o-series `has_word` branch does NOT swallow
    /// the gpt-4o branch. `gpt-4o` contains the substring `o` but is matched
    /// by `contains("gpt-4o")` (earlier) at $2.5, NOT by any o-series word.
    /// Guards against a refactor that moves o-series before gpt families.
    #[test]
    fn price_gpt4o_not_captured_by_o_series() {
        // gpt-4o resolves to the gpt-4o tier (2.5/10.0), NOT o4/o3/o1.
        assert_pricing("gpt-4o", 2.5, 10.0, 2.5, 0.25);
    }

    /// Added: an o-series name with a provider prefix using `:` separator
    /// (`proxy:o3`) — `has_word` treats `:` as a boundary, so it routes to
    /// the o3 OpenAI tier. Complements the `/` case (matrix[51]).
    #[test]
    fn price_colon_prefixed_o3_routes_openai() {
        assert_pricing("proxy:o3", 2.0, 8.0, 2.0, 0.2);
    }

    /// Added: `moonshot`-prefixed via provider segment `proxy:moonshot-v1`
    /// resolves to the kimi/moonshot tier through provider_match's `:`
    /// branch. Pins the colon-separator path of provider_match for OSS.
    #[test]
    fn price_colon_prefixed_moonshot_resolves_kimi_tier() {
        assert_pricing("proxy:moonshot-v1", 0.6, 2.5, 0.6, 0.3);
    }

    // ── Direct unit tests for the two matcher primitives ────────────────

    /// `has_word` boundary semantics, locked directly (start/end of string
    /// and `-_/:` treated as boundaries; digits/letters are NOT boundaries).
    #[test]
    fn has_word_boundary_semantics() {
        // Hits: start+end, after `-`, after `/`, after `:`, before `_`.
        assert!(has_word("o3", "o3"), "bare needle == whole string");
        assert!(has_word("o3-mini", "o3"), "trailing `-` is a boundary");
        assert!(has_word("google/o3", "o3"), "leading `/` is a boundary");
        assert!(has_word("proxy:o3", "o3"), "leading `:` is a boundary");
        assert!(has_word("o3_x", "o3"), "trailing `_` is a boundary");
        // Misses: digit/letter neighbours are NOT boundaries.
        assert!(!has_word("o32", "o3"), "trailing digit is not a boundary");
        assert!(!has_word("xo3", "o3"), "leading letter is not a boundary");
        assert!(!has_word("o3x", "o3"), "trailing letter is not a boundary");
        // Empty needle never matches.
        assert!(!has_word("o3", ""), "empty needle never matches");
    }

    /// `provider_match` semantics, locked directly: start-of-string OR after
    /// a `/`/`:` provider separator; mid-word and empty-prefix are rejected.
    #[test]
    fn provider_match_semantics() {
        // Start-of-string (permissive — digit/letter suffix both OK).
        assert!(provider_match("kimi-k2.5", "kimi"), "start-of-string match");
        assert!(provider_match("qwen3.6", "qwen"), "digit suffix still matches");
        assert!(
            provider_match("kimiclone", "kimi"),
            "starts_with is permissive even with letter suffix"
        );
        // Provider-segment separators.
        assert!(provider_match("openai/kimi-x", "kimi"), "`/` segment match");
        assert!(provider_match("proxy:moonshot", "moonshot"), "`:` segment match");
        // Rejections.
        assert!(
            !provider_match("my-kimi-clone", "kimi"),
            "mid-word (after `-`) is NOT a provider segment -> reject"
        );
        assert!(!provider_match("kimi-x", ""), "empty prefix always false");
    }
}
