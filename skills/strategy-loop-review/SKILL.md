---
name: strategy-loop-review
description: Reviews one round bundle from any AutoTrader strategy-optimization study against the 4-criterion rubric via Codex MCP. Reads result.json + bootstrap_diff.json + regime_breakdown.json + round_summary.json + cfg.json from a round-NN/variant-MM/ directory; writes codex_verdict.md + digest.md to the same directory. Use when user says "review round N", "score the round", "/strategy-loop-review", or wants Codex to gate an in-flight candidate before committing the round.
argument-hint: [round-bundle-directory-path]
allowed-tools: Bash(*), Read, Write, mcp__codex__codex
---

# Strategy Loop Review (single-round)

Review one candidate round bundle against the 4-criterion rubric. Codex reads the bundle files itself via its read-only sandbox; this skill just validates the bundle is complete, dispatches Codex with a short prompt, and persists Codex's response.

The skill is **idempotent**: re-invoking it on the same bundle (e.g. retry after a Codex MCP outage) overwrites `codex_verdict.md` and `digest.md`. No special retry mode is needed.

## Bundle directory: $ARGUMENTS

## Constants

- **REVIEWER_MODEL**: `gpt-5.5`
- **PROJECT_ROOT**: parent of the `study_runs/` ancestor in `$ARGUMENTS` (auto-detected by walking up the path until a `study_runs/` segment is found). Passed to Codex as `cwd` so it can `Read` bundle files.
- **REQUIRED_FILES**: `cfg.json`, `result.json`, `bootstrap_diff.json`, `regime_breakdown.json`, `round_summary.json`
- **OUTPUT_FILES**: `codex_verdict.md` (raw Codex response + header), `digest.md` (structured carry-forward parsed from Codex's JSON block)

The 4-criterion rubric is inlined in the Codex prompt below — no external spec excerpt needed. Study-specific overrides (e.g. delta-vs-baseline concentration semantics) are picked up from the study brief if one is auto-discovered for the bundle.

## Workflow

### Phase A — Validate bundle (one Bash call)

Run one Bash check that asserts the bundle directory exists and every REQUIRED_FILE is present. If anything is missing, **STOP** and report — the upstream pipeline (proposer + wrapper + evaluators) didn't complete; reviewer refuses to score a partial bundle.

```bash
BUNDLE="$ARGUMENTS"
test -d "$BUNDLE" || { echo "MISSING dir: $BUNDLE"; exit 1; }
for f in cfg.json result.json bootstrap_diff.json regime_breakdown.json round_summary.json; do
  test -f "$BUNDLE/$f" || { echo "MISSING: $BUNDLE/$f"; exit 1; }
done
echo "BUNDLE OK"
```

### Phase B — Invoke Codex via MCP (one mcp__codex__codex call)

Resolve two values before the call:

- **PROJECT_ROOT**: the prefix of `$ARGUMENTS` ending immediately before the first `study_runs/` segment.
- **STUDY_BRIEF_PATH**: if `$ARGUMENTS` matches `study_runs/<slug>/round-NN/variant-MM/`, glob `<PROJECT_ROOT>/docs/studies/*<slug>*.md` and `<PROJECT_ROOT>/docs/briefs/*<slug>*.md`. If exactly one match, use it; otherwise `none`.

Call `mcp__codex__codex` with:

- `model`: `gpt-5.5`
- `sandbox`: `read-only`
- `approval-policy`: `never`
- `cwd`: PROJECT_ROOT
- `prompt`: the template below, with `<BUNDLE_PATH>` and `<STUDY_BRIEF_PATH_OR_NONE>` filled in.

**Prompt template:**

```
You are reviewing one round bundle of an AutoTrader strategy-optimization study. Read the bundle files yourself; do not assume any context beyond what is on disk.

BUNDLE_PATH: <BUNDLE_PATH>
STUDY_BRIEF (optional, for study-specific overrides): <STUDY_BRIEF_PATH_OR_NONE>

READ these files from BUNDLE_PATH (use the Read tool):
- cfg.json
- result.json
- bootstrap_diff.json
- regime_breakdown.json
- round_summary.json
- proposer_brief.md (optional — if present, surfaces the hypothesis + falsifier)
- deviations.md (optional — if present, lists methodology deviations the implementer recorded)

If STUDY_BRIEF is provided, read it too — its "Success criteria" section may override the default rubric (e.g. delta-vs-baseline concentration semantics, study-specific windows, additional gates, or a primary Pareto cell question).

RUBRIC (default — 4 criteria, all must pass for accept=true):

1. **Statistical lift** — 95% CI of paired-day Sharpe-difference bootstrap (>=10,000 resamples) excludes zero on the POSITIVE side. Read bootstrap_diff.json:lift_ci_95.
2. **Regime-robust** — Better on >=2 of {Greed, Fear, Neutral}, not worse in any by > 0.10 Sharpe. PIT-verified labels. Read regime_breakdown.json:verdict and :per_regime.
3. **Trade integrity** — >=20 trades; max single-trade <=25% of total |pnl|; sector concentration <=30% (strict-absolute Tech |pnl| cap unless the study brief overrides); turnover within [1/1.5, 1.5] vs baseline; median holding within [0.5, 1.5] vs baseline. Read round_summary.json:criteria.trade_integrity.
4. **Clean diff + PIT** — One logical change vs baseline; hypothesis falsifiable; any new data sources honor observed_ts <= bar.event_date; ATR uses only prior bars; momentum decay uses only prior signal history. Read cfg.json + proposer_brief.md (if present).

OUTPUT — respond in two parts:

PART 1: Free-form verdict (<=500 words) discussing each of the 4 criteria with quantitative evidence from the bundle files. If the study brief defines a primary success cell (e.g. a specific Pareto question), answer it explicitly and identify which brief-defined falsifier (if any) triggered.

PART 2: A machine-parseable JSON block at the very end of your reply:
{
  "accept": true | false,
  "criteria": {
    "statistical_lift": {"passed": true|false, "rationale": "..."},
    "regime_robust": {"passed": true|false, "rationale": "..."},
    "trade_integrity": {"passed": true|false, "rationale": "..."},
    "clean_diff_pit": {"passed": true|false, "rationale": "..."}
  },
  "primary_pareto_cell_landed": true | false | null,
  "falsifier_triggered": "<brief-defined falsifier ID or 'none'>",
  "next_round_recommendations": ["...", "...", ...],
  "rejection_digest": "Brief carryover for next round's proposer if accept=false; '(accepted)' if accept=true"
}
```

### Phase C — Persist outputs (two Write calls)

1. **`codex_verdict.md`** — Codex's full raw response, prefixed by a header:

   ```markdown
   # Codex Strategy-Loop Review

   **Skill**: strategy-loop-review (simplified)
   **Reviewer model**: gpt-5.5 via mcp__codex__codex
   **Timestamp**: <iso UTC>
   **Bundle**: <BUNDLE_PATH>

   ---

   <Codex response, verbatim>
   ```

2. **`digest.md`** — structured carry-forward parsed from the JSON block in Codex's response. Schema:

   ```markdown
   # Round Review Digest

   **Round bundle**: <path>
   **Reviewer**: Codex (gpt-5.5)
   **Accept**: <true|false>
   **Primary Pareto cell landed**: <true|false|n/a>
   **Falsifier triggered**: <id or none>
   **Timestamp**: <iso UTC>

   ## Per-criterion verdicts

   - **Statistical lift**: PASS|FAIL — <rationale>
   - **Regime robust**: PASS|FAIL — <rationale>
   - **Trade integrity**: PASS|FAIL — <rationale>
   - **Clean diff + PIT**: PASS|FAIL — <rationale>

   ## Carry-forward for next round

   - <each next_round_recommendation as bullet>

   ## Rejection digest

   <rejection_digest, or "(accepted)" if accept=true>
   ```

   If the JSON block fails to parse (malformed / missing), write `digest.md` with a `parse_warning` line at the top and best-effort fields extracted from the free-form text. Do not abort — downstream `/strategy-loop-feature` orchestrators depend on `digest.md` existing.

### Phase D — Report

One concise message:
- Path to bundle reviewed
- `accept`: true|false
- 4 one-liners (one per criterion)
- Paths to `codex_verdict.md` + `digest.md`
- If `accept=false`: the `rejection_digest`

## What this skill does NOT do

- **Does NOT propose configs.** Upstream's job (`/strategy-loop-feature`, `/strategy-loop-round`, or manual).
- **Does NOT run the wrapper or evaluators.** Bundle must exist on disk.
- **Does NOT commit to git.** The caller commits the verdict + digest.
- **Does NOT iterate.** Single-round, single-bundle review.

## Errors → STOP, do not write outputs

- Bundle directory doesn't exist.
- Any REQUIRED_FILE missing (partial bundle — upstream pipeline didn't complete).
- Codex MCP unreachable / errors (e.g. usage-limit). Report the failure; re-invoke the skill later when MCP is available — the skill is idempotent.

In all stop cases, refuse to write `codex_verdict.md` or `digest.md` (avoid polluting the bundle with a partial review). Downstream `/strategy-loop-feature` checks for `digest.md` existence after invoking this skill; missing digest = reviewer didn't complete.
