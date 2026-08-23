# Knowledge Capture Filtering (Anti-Self-Poisoning)

When saving durable knowledge — such as research wiki nodes (ideas, claims, experiment results) or skill proposals — record reusable technical solutions, permanent constraints, and validated findings. Do not persist temporary operational noise or transient environment errors as permanent facts or tool limitations.

## The Four Anti-Patterns to Reject

| Class | Examples to Avoid | What to Record Instead |
|---|---|---|
| **Environment-specific failure** | "pip failed: No module named torch", "command not found" | The required dependency, installation step, or correct configuration |
| **Transient error** | "got a 429", "CUDA OOM", "connection refused" | Nothing (if self-resolving), or the retry/backoff policy that succeeded |
| **Negative tool-capability claim** | "model X cannot handle long files", "tool Y is broken" | The required flags, file size limits, or specific workaround |
| **Single-instance narrative** | "in run 47 the loss spiked at step 300" | The generalizable principle, if any (e.g., "learning rates > 3e-4 diverge on this architecture") |

**Core Rule:** Record *how to fix an issue*, *what configuration is required*, or *the effective workaround*. Never record blanket negative capability assertions like *"Tool X cannot do Y"*. Storing negative capability claims about system tooling causes future sessions to avoid functional tools long after an underlying transient issue is resolved.

## Mechanical vs. Judgment Filtering

- **Mechanical Screen** (deterministic, via `tools/capture_filter.py`): Detects unambiguous error signatures: raw stack traces (`ModuleNotFoundError`, `Permission denied`), transient errors (rate limits, OOM, network resets), and negative capability assertions about system tools.
- **Judgment Screen** (this document): Identifies one-off run narratives and operational noise disguised as scientific findings.

The mechanical filter is conservative: it does not flag legitimate research findings about algorithms or models (e.g., "the baseline degrades on out-of-distribution inputs"). It focuses on raw error messages and unfounded claims about system tooling.

## Verification Asymmetry

Filtering out operational noise is a safety pre-check that the executor model may perform directly. However, any finding that passes the filter and is proposed as a durable skill change or scientific claim still requires independent cross-model review before being committed to persistent memory.

## Helper Utilities

```python
from capture_filter import screen, reason_detail
reasons = screen(text)  # Returns [] if clean; reasons in {env_failure, transient_error, negative_tool_claim}
```

```bash
python3 tools/capture_filter.py <file|->   # Exits 1 with reasons if anti-patterns are detected
```

## Where This Is Applied

- **`/research-wiki`** (and `/idea-creator` annotations): Screen ideas, claims, and experiment notes before saving them. Rewrite flagged notes to capture the solution, or discard transient noise.
- **`/meta-optimize`**: Screen proposed skill modifications to prevent encoding transient failures as permanent guidelines.

## Cross-References

- `acceptance-gate.md` — Deterministic rejection pre-checks vs. independent cross-model review for durable claims.
- `evidence-precheck.md` / `injection-hygiene.md` — Deterministic pre-checks feeding downstream review.
