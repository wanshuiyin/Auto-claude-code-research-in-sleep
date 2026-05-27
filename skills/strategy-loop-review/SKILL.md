---
name: strategy-loop-review
description: Reviews one round bundle from the AutoTrader strategy-optimization-loop study against the spec's 4-criterion rubric via Codex MCP. Reads result.json + bootstrap_diff.json + regime_breakdown.json + round_summary.json + cfg.json from a round-NN/variant-MM/ directory; writes codex_verdict.md + digest.md to the same directory. Use when user says "review round N", "score the round", "/strategy-loop-review", or wants Codex to gate an in-flight candidate before committing the round.
argument-hint: [round-bundle-directory-path]
allowed-tools: Bash(*), Read, Write, Grep, Glob, mcp__codex__codex
---

# Strategy Loop Review (single-round, MVS)

Review one candidate round of the AutoTrader strategy-optimization-loop study against the spec's 4-criterion rubric. Calls Codex via MCP.

## Bundle directory: $ARGUMENTS

## Constants

- **REVIEWER_MODEL**: `gpt-5.5`
- **SPEC_PATH**: `/Users/zongfan/Projects/AutoTrader/docs/studies/2026-05-26-strategy-optimization-loop.md`
- **REQUIRED_FILES**: `cfg.json`, `result.json`, `bootstrap_diff.json`, `regime_breakdown.json`, `round_summary.json`
- **OUTPUT_FILES**: `codex_verdict.md` (raw Codex response), `digest.md` (structured carry-forward)
- **PER_ROUND_DATE_RANGE_EXPECTED**: `2022-01-01:2025-11-30` (per spec §5.3.4; the wrapper enforces, this is the cross-check)

## Workflow

### Phase A — Validate bundle

1. `cd $ARGUMENTS` — verify directory exists.
2. For each `REQUIRED_FILES`: assert exists. If any missing, **STOP** and report which files are missing — the upstream pipeline (proposer + wrapper + evaluators) didn't complete; reviewer refuses to score per spec §3.1 line 61.
3. Read `result.json`. Pre-check: `date_range == PER_ROUND_DATE_RANGE_EXPECTED` (this is the proxy for "wrapper emitted seal tokens" — the wrapper validates and emits in one block; date_range matching the seal is sufficient evidence). If mismatch, **STOP** and report.
4. Read `round_summary.json`. Note which automated criteria pre-failed (criteria.*.passed=false). Codex will still review, but with this context.

### Phase B — Format the Codex prompt

Construct a single Codex input including:

- **Header**: "You are reviewing one round of the AutoTrader strategy-optimization-loop study. Score against the 4-criterion rubric verbatim from spec §3.1."
- **Spec excerpt**: copy lines 32-63 of `SPEC_PATH` (the Methodology / Loop structure section that defines the rubric, Phase A search space, and per-round rubric items 1-4). Use `Read` with offset=32, limit=32 to grab them.
- **Bundle dump**: include verbatim the contents of `cfg.json`, `bootstrap_diff.json`, `regime_breakdown.json`, `round_summary.json`. Also include the summary fields from `result.json` (final_equity, trade_count, date_range, purpose, composite_key).
- **Note about trade-integrity sub-checks**: round_summary.json may show `insufficient_data: true` for max_single_trade_pct_pnl, sector_concentration_pct, turnover_ratio_vs_baseline, and median_holding_days_vs_baseline — these are pending a future wrapper enhancement (per-trade trades.csv emission). Codex should: (a) score trade_integrity as PASS if trade_count_ok is true AND no obvious red flag from final_equity/trade_count ratio; (b) note in the response which sub-checks were inconclusive due to insufficient_data.
- **Output schema instruction**: Codex must respond in two parts:
  1. A free-form verdict section (<= 500 words) discussing each of the 4 criteria with quantitative evidence from the bundle.
  2. A machine-parseable JSON block at the end with fields:
     ```json
     {
       "accept": true | false,
       "criteria": {
         "statistical_lift": {"passed": true|false, "rationale": "..."},
         "regime_robust": {"passed": true|false, "rationale": "..."},
         "trade_integrity": {"passed": true|false, "rationale": "..."},
         "clean_diff_pit": {"passed": true|false, "rationale": "..."}
       },
       "next_round_recommendations": ["...", "...", ...],
       "rejection_digest": "Brief carryover for next round's proposer if accept=false"
     }
     ```

### Phase C — Invoke Codex via MCP

Call `mcp__codex__codex` with the formatted prompt. Use the model from REVIEWER_MODEL. Capture the full response text.

### Phase D — Persist outputs

1. Write `codex_verdict.md` to the round bundle directory — full raw Codex response, with a header containing: skill version, REVIEWER_MODEL, timestamp.
2. Extract the JSON block from Codex's response. If extraction fails (malformed JSON / missing block), fall back to a structured-by-hand `digest.md` based on the free-form text; flag this in the digest with a `parse_warning` field.
3. Write `digest.md` to the round bundle directory — a structured carryover for the next round, formatted as:
   ```markdown
   # Round Review Digest

   **Round bundle**: <path>
   **Reviewer**: Codex (REVIEWER_MODEL)
   **Accept**: <true|false>
   **Timestamp**: <iso>

   ## Per-criterion verdicts

   - **Statistical lift**: PASS | FAIL — <rationale>
   - **Regime robust**: PASS | FAIL — <rationale>
   - **Trade integrity**: PASS | FAIL — <rationale>
   - **Clean diff + PIT**: PASS | FAIL — <rationale>

   ## Carry-forward for next round

   <next_round_recommendations bulleted>

   ## Rejection digest (if rejected)

   <rejection_digest>
   ```

### Phase E — Report

Report to the user:
- Path to round bundle reviewed
- Accept / reject verdict
- Per-criterion pass/fail (one line each)
- Path to `codex_verdict.md` and `digest.md`
- If rejected: top-3 issues + rejection_digest for next round's proposer

## What this skill does NOT do

- **Does NOT propose configs.** Proposer step is upstream (manual for round 1; future Phase 3 orchestrator skill).
- **Does NOT run the wrapper or evaluators.** Bundle must already exist on disk.
- **Does NOT commit to git.** User commits the verdict + digest as part of round-NN bundle.
- **Does NOT iterate.** Single-round, single-bundle review. The multi-round loop is the future Phase 4 driver.

## Errors -> STOP, do not invoke Codex

- Bundle directory doesn't exist
- Any REQUIRED_FILES missing
- result.json.date_range mismatch with PER_ROUND_DATE_RANGE_EXPECTED
- bootstrap_diff.json malformed (KeyError on required keys)
- Codex MCP unreachable / errors

Each of these -> report the specific failure mode and refuse to write codex_verdict.md (avoid polluting the bundle with a bad review).
