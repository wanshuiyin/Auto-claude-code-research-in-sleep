#!/usr/bin/env bash
# ARIS Factual Audit — automated truth check before Codex MCP review.
# Usage: bash factual_audit.sh <paper_dir> <experiment_log_dir>
# Exit 0 = all checks passed. Exit 1 = issues found (sent to Codex as context).
set -euo pipefail

PAPER_DIR="${1:-paper}"
EXPERIMENT_DIR="${2:-deep-experiment-logs}"
ISSUES=0

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
pass() { echo -e "${GREEN}[AUDIT OK]${NC} $*"; }
fail() { echo -e "${RED}[AUDIT FAIL]${NC} $*"; ISSUES=$((ISSUES + 1)); }

echo "══════════════════════════════════════════"
echo "  FACTUAL AUDIT"
echo "══════════════════════════════════════════"

# ─── Check 1: reproduce.sh exists and is executable ──────────────────────
if [ -f "reproduce.sh" ] && [ -x "reproduce.sh" ]; then
    pass "reproduce.sh exists and is executable"
else
    fail "reproduce.sh missing or not executable — REPRODUCIBILITY FAILED"
fi

# ─── Check 2: checkpoint files exist (>= 3 .pt files) ───────────────────
N_CHECKPOINTS=$(ls checkpoints/*.pt checkpoints/*.pth 2>/dev/null | wc -l)
if [ "$N_CHECKPOINTS" -ge 3 ]; then
    pass "checkpoints: $N_CHECKPOINTS model files (need >= 3)"
else
    fail "checkpoints: only $N_CHECKPOINTS .pt files (need >= 3)"
fi

# ─── Check 3: Seed count consistency ─────────────────────────────────────
# Extract claimed seeds from paper text
CLAIMED_SEEDS=$(grep -oi "seed[s]\? *= *[0-9]*\|[0-9]\+ seed[s]\?\|n_seeds *= *[0-9]*" "$PAPER_DIR"/main.tex "$PAPER_DIR"/sections/*.tex 2>/dev/null | grep -o '[0-9]\+' | sort -n | tail -1 || echo "0")

# Count actual seed directories or seed references in results
ACTUAL_SEEDS=$(find "$EXPERIMENT_DIR" -name "metrics.json" -exec grep -l "seed" {} \; 2>/dev/null | wc -l || echo 1)

if [ "$CLAIMED_SEEDS" -gt 4 ] 2>/dev/null && [ "$ACTUAL_SEEDS" -lt 2 ]; then
    fail "Seed fraud: paper claims $CLAIMED_SEEDS seeds, but only 1 seed found in results"
elif [ "$ACTUAL_SEEDS" -ge 5 ]; then
    pass "seeds: $ACTUAL_SEEDS actual >= 5"
elif [ "$ACTUAL_SEEDS" -lt 2 ]; then
    fail "seeds: only 1 seed found — need >= 5 for SYNTHESIZE"
else
    pass "seeds: $ACTUAL_SEEDS found"
fi

# ─── Check 4: Test set size ─────────────────────────────────────────────
CLAIMED_TEST=$(grep -oi "test.*[0-9]\+\|n_test *= *[0-9]*" "$PAPER_DIR"/main.tex "$PAPER_DIR"/sections/*.tex 2>/dev/null | grep -o '[0-9]\+' | sort -n | tail -1 || echo "0")
if [ "$CLAIMED_TEST" -gt 0 ] 2>/dev/null && [ "$CLAIMED_TEST" -lt 200 ]; then
    fail "test set: paper claims n=$CLAIMED_TEST (need >= 200)"
else
    pass "test set: n=$CLAIMED_TEST (or not explicitly stated)"
fi

# ─── Check 5: Epoch count ───────────────────────────────────────────────
MAX_EPOCHS=0
for f in "$EXPERIMENT_DIR"/ROUND_*/results/metrics.json; do
    [ -f "$f" ] || continue
    ep=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('epochs',0))" 2>/dev/null || python -c "import json; d=json.load(open('$f')); print(d.get('epochs',0))" 2>/dev/null || echo 0)
    [ "$ep" -gt "$MAX_EPOCHS" ] && MAX_EPOCHS=$ep
done
if [ "$MAX_EPOCHS" -ge 100 ]; then
    pass "training: max epochs = $MAX_EPOCHS (need >= 100)"
else
    fail "training: max epochs = $MAX_EPOCHS (need >= 100)"
fi

# ─── Check 6: Baseline sources exist ─────────────────────────────────────
if [ -f "BASELINE_SOURCES.md" ]; then
    pass "BASELINE_SOURCES.md exists"
else
    fail "BASELINE_SOURCES.md missing — no baseline paper citations documented"
fi

# ─── Check 7: paper/figures/ not empty ───────────────────────────────────
N_FIGS=$(ls "$PAPER_DIR"/figures/*.pdf "$PAPER_DIR"/figures/*.png 2>/dev/null | wc -l)
if [ "$N_FIGS" -ge 4 ]; then
    pass "paper/figures: $N_FIGS figure files"
else
    fail "paper/figures: only $N_FIGS figures (need >= 4)"
fi

# ─── Check 8: Evidence existence — numbers cited in paper exist in results ──
EVIDENCE_ISSUES=0
if [ -f "$PAPER_DIR/main.tex" ]; then
    # Extract all numeric values from paper (e.g., "MAE 0.264", "RMSE = 0.0545")
    CLAIMED_NUMS=$(grep -oh '[0-9]\+\.[0-9]\+' "$PAPER_DIR"/main.tex "$PAPER_DIR"/sections/*.tex 2>/dev/null | sort -u || echo "")
    # Check if each claimed number appears somewhere in experiment logs
    for num in $CLAIMED_NUMS; do
        if ! grep -rq "$num" "$EXPERIMENT_DIR"/ROUND_*/results/ 2>/dev/null; then
            # Not found in results — might be a typo or hallucination
            EVIDENCE_ISSUES=$((EVIDENCE_ISSUES + 1))
            [ $EVIDENCE_ISSUES -le 5 ] && fail "Evidence: claimed value '$num' not found in experiment results"
        fi
    done
    [ $EVIDENCE_ISSUES -eq 0 ] && pass "Evidence: all paper numbers found in experiment results"
fi

# ─── Summary ─────────────────────────────────────────────────────────────
echo ""
if [ "$ISSUES" -eq 0 ]; then
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    echo -e "${GREEN}  FACTUAL AUDIT: ALL CLEAN${NC}"
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    exit 0
else
    echo -e "${RED}══════════════════════════════════════════${NC}"
    echo -e "${RED}  FACTUAL AUDIT: $ISSUES ISSUE(S) FOUND${NC}"
    echo -e "${RED}  Send to Codex MCP as mandatory review context.${NC}"
    echo -e "${RED}══════════════════════════════════════════${NC}"
    exit 1
fi
