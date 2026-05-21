# Loop Budget Helper Resolution

This document describes how `auto-review-loop*` skills resolve `tools/loop_budget.py`.
The pattern mirrors `wiki-helper-resolution.md` and `review-tracing.md`.

See `shared-references/integration-contract.md` §2 for the canonical resolver chain
and the per-helper Policy A (gate) classification, plus the "Known ARIS integrations"
table row covering this guard.

## Resolver block

Paste this into the skill's bash setup, then use `$LOOP_BUDGET_SCRIPT` thereafter.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
LOOP_BUDGET_SCRIPT=".aris/tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT="tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && LOOP_BUDGET_SCRIPT="$ARIS_REPO/tools/loop_budget.py"; }
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT=""
```

## Failure policy (Policy A — gate)

If the helper is unresolved, the loop MUST refuse to start:

```bash
[ -n "$LOOP_BUDGET_SCRIPT" ] || {
  echo "ERROR: loop_budget.py not resolved at .aris/tools/, tools/, or \$ARIS_REPO/tools/." >&2
  echo "       The auto-review-loop guard cannot enforce subscription quota; aborting." >&2
  echo "       Fix: rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
  exit 1
}
```

## Pre-iteration check

Run before each side's call. Exit 0 = ok; exit 2 = at/over budget; the tool prints
a one-line status to stderr in both cases.

```bash
python3 "$LOOP_BUDGET_SCRIPT" check --side claude || exit $?  # before executor turn
python3 "$LOOP_BUDGET_SCRIPT" check --side codex  || exit $?  # before reviewer turn
```

## Post-call record

Run after each side's call succeeds:

```bash
python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill <this-skill-name>
python3 "$LOOP_BUDGET_SCRIPT" record --side codex  --skill <this-skill-name>
```

## Configuration

Defaults are conservative for $100/mo Claude.ai and ChatGPT subscriptions.
Override per-machine via environment:

| Env var                         | Default | Meaning                                  |
|---------------------------------|---------|------------------------------------------|
| `CLAUDE_LOOP_MAX_ITERATIONS`    | `15`    | Executor turns per Claude window         |
| `CLAUDE_LOOP_WINDOW_HOURS`      | `5`     | Claude rolling window length             |
| `CODEX_LOOP_MAX_ITERATIONS`     | `30`    | Reviewer turns per Codex window          |
| `CODEX_LOOP_WINDOW_HOURS`       | `5`     | Codex rolling window length              |
| `CLAUDE_LOOP_WARN_AT`           | `0.8`   | Warn-stderr threshold (still exits 0)    |
| `ARIS_USAGE_DIR`                | `~/.aris/usage` | State directory                  |

## Status (manual inspection)

`python3 "$LOOP_BUDGET_SCRIPT" status` prints current usage on both sides — no exit-code semantics, safe to run anytime.
