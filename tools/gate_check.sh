#!/usr/bin/env bash
# ARIS Gate Check — verify Phase outputs before pipeline transitions.
# Usage: bash gate_check.sh <phase>
#   phase 0: check knowledge base outputs
#   phase 1: check idea discovery outputs
#   phase 2: check deep experiment outputs (per-round + final)
#   phase 2-round: check current round's 6 mandatory files
#   phase 3: check paper writing outputs
#   phase 4: check review outputs
# Exit 0 = gate PASS, proceed.  Exit 1 = gate FAIL, go back.
set -euo pipefail

# Auto-log to deep-experiment-logs/ or project root
LOG_DIR="${ARIS_LOG_DIR:-deep-experiment-logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/gate_check_$(date +%Y%m%d_%H%M%S).log"

# Tee all output to log file while still showing on terminal
exec > >(tee -a "$LOG_FILE") 2>&1

PHASE="${1:-}"
ROUND_NN="${2:-}"  # for per-round checks

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; EXIT_CODE=1; }
EXIT_CODE=0

# ─── Phase 0: Knowledge Base ────────────────────────────────────────────────
check_phase_0() {
    echo "=== Gate Check: Phase 0 — Knowledge Base ==="
    local kb="research-wiki/knowledge_base"

    [ -f "$kb/domain_overview.md" ] && pass "domain_overview.md" || fail "domain_overview.md missing"
    [ -f "$kb/metrics_and_baselines.md" ] && pass "metrics_and_baselines.md" || fail "metrics_and_baselines.md missing"
    [ -f "$kb/field_conventions.md" ] && pass "field_conventions.md" || fail "field_conventions.md missing"
    [ -f "$kb/index.json" ] && pass "index.json" || fail "index.json missing"
    [ -f "$kb/search.py" ] && pass "search.py" || fail "search.py missing"

    # Papers must have full-text JSON extracted (not just empty papers/ dir)
    local n_papers=$(ls "$kb/papers/"*.json 2>/dev/null | wc -l)
    [ "$n_papers" -gt 0 ] && pass "papers: $n_papers full-text JSON files" || fail "papers/: 0 JSON files — PDFs not downloaded/extracted"

    # At least one domain file must have substantive content (>500 chars)
    local content_ok=false
    for f in "$kb/domain_overview.md" "$kb/metrics_and_baselines.md" "$kb/field_conventions.md"; do
        [ -f "$f" ] && [ $(wc -c < "$f") -gt 500 ] && content_ok=true && break
    done
    $content_ok && pass "domain content is substantive (>500 chars)" || fail "domain content is too thin (<500 chars in all files)"

    return $EXIT_CODE
}

# ─── Phase 1: Idea Discovery ────────────────────────────────────────────────
check_phase_1() {
    echo "=== Gate Check: Phase 1 — Idea Discovery ==="
    [ -f "idea-stage/IDEA_REPORT.md" ] && pass "IDEA_REPORT.md" || fail "IDEA_REPORT.md missing"
    [ -f "idea-stage/IDEA_REPORT.md" ] && [ $(wc -c < "idea-stage/IDEA_REPORT.md") -gt 2000 ] && pass "IDEA_REPORT.md > 2000 chars" || fail "IDEA_REPORT.md too short (< 2000 chars)"

    # Must mention at least one baseline method and one metric
    if [ -f "idea-stage/IDEA_REPORT.md" ]; then
        grep -qi "baseline\|compare\|method\|approach\|FFT\|NLS\|MCMC\|LSTM\|neural\|classical" idea-stage/IDEA_REPORT.md && pass "mentions baseline/comparison methods" || fail "no baseline methods mentioned"
    fi

    return $EXIT_CODE
}

# ─── Phase 2: Per-Round Audit ───────────────────────────────────────────────
check_phase_2_round() {
    local R="${1:-ROUND_01}"
    echo "=== Gate Check: Phase 2 — Round Audit ($R) ==="

    [ -f "$R/hypothesis.md" ] && pass "hypothesis.md" || fail "hypothesis.md missing"
    [ -f "$R/code/run.py" ] && pass "code/run.py" || fail "code/run.py missing"
    [ -f "$R/code/run.py" ] && [ $(wc -l < "$R/code/run.py") -ge 50 ] && pass "code/run.py >= 50 lines" || fail "code/run.py < 50 lines"
    [ -f "$R/results/metrics.json" ] && pass "results/metrics.json" || fail "results/metrics.json missing"
    [ -f "$R/analysis.md" ] && pass "analysis.md" || fail "analysis.md missing"
    [ -f "$R/analysis.md" ] && grep -q "[0-9]" "$R/analysis.md" && pass "analysis.md contains numbers" || fail "analysis.md has no numbers"
    [ -f "$R/decision.md" ] && pass "decision.md" || fail "decision.md missing"

    # Plots: at least 4 PDF files, each > 5KB (not placeholder/empty)
    local n_plots=0
    local small_plots=0
    for pdf in "$R/plots/"*.pdf; do
        [ -f "$pdf" ] || continue
        n_plots=$((n_plots + 1))
        [ $(stat -c%s "$pdf" 2>/dev/null || echo 0) -lt 5000 ] && small_plots=$((small_plots + 1))
    done
    [ "$n_plots" -ge 4 ] && pass "plots: $n_plots PDF files" || fail "plots: $n_plots PDF files (need >= 4)"
    [ "$small_plots" -eq 0 ] && pass "all plot files > 5KB (not placeholders)" || fail "$small_plots plot(s) < 5KB — likely empty/placeholder"

    # plot.py must include quality markers AND be substantial (not a 20-line stub)
    if [ -f "code/plot.py" ]; then
        local plot_lines=$(wc -l < "code/plot.py" 2>/dev/null || echo 0)
        [ "$plot_lines" -ge 100 ] && pass "plot.py: $plot_lines lines (need ≥100 — write real plotting code)" || fail "plot.py: only $plot_lines lines (need ≥100 — too short for publication-quality figures)"
        grep -q "bar\|errorbar\|fill_between\|err" code/plot.py 2>/dev/null && pass "plot.py includes error bars" || fail "plot.py has no error bars (add plt.errorbar or similar)"
        grep -q "label\|set_xlabel\|set_ylabel\|xlabel\|ylabel" code/plot.py 2>/dev/null && pass "plot.py includes axis labels" || fail "plot.py has no axis labels"
        grep -q "rad/s\|μs\|dB\|Hz\|ms\|unit\|RMS\|MAE\|SNR\|Hz\|sec" code/plot.py 2>/dev/null && pass "plot.py includes units" || fail "plot.py may lack units (add rad/s, μs, dB, etc.)"
    fi

    # TSV must have an entry for this round
    [ -f "deep-experiment-logs/EXPERIMENT_HISTORY.tsv" ] && pass "EXPERIMENT_HISTORY.tsv exists" || fail "EXPERIMENT_HISTORY.tsv missing"
    # Check that this round number appears in TSV
    local round_num=$(echo "$R" | grep -o '[0-9]*')
    if [ -f "deep-experiment-logs/EXPERIMENT_HISTORY.tsv" ] && [ -n "$round_num" ]; then
        grep -q "^${round_num#0}\s" deep-experiment-logs/EXPERIMENT_HISTORY.tsv 2>/dev/null && pass "round $round_num logged in TSV" || fail "round $round_num not found in TSV"
    fi

    return $EXIT_CODE
}

# ─── Phase 2: Final Outputs ─────────────────────────────────────────────────
check_phase_2() {
    echo "=== Gate Check: Phase 2 — Final Outputs ==="
    [ -f "deep-experiment-logs/FINAL_REPORT.md" ] && pass "FINAL_REPORT.md" || fail "FINAL_REPORT.md missing"
    [ -f "deep-experiment-logs/BIBLIOGRAPHY.bib" ] && pass "BIBLIOGRAPHY.bib" || fail "BIBLIOGRAPHY.bib missing"
    [ -f "deep-experiment-logs/EXPERIMENT_HISTORY.tsv" ] && pass "EXPERIMENT_HISTORY.tsv" || fail "EXPERIMENT_HISTORY.tsv missing"
    [ -f "deep-experiment-logs/reproduce.sh" ] && pass "reproduce.sh" || fail "reproduce.sh missing"
    # BIBLIOGRAPHY must have >= 25 entries (SYNTHESIZE condition 7)
    local bib_count=$(grep -c '^@' deep-experiment-logs/BIBLIOGRAPHY.bib 2>/dev/null || echo 0)
    [ "$bib_count" -ge 25 ] && pass "BIBLIOGRAPHY: $bib_count entries (need >= 25)" || fail "BIBLIOGRAPHY: only $bib_count entries (need >= 25)"

    # FIGURES must include architecture diagram
    # PHASE2_CHECKLIST must exist and have no unchecked items
    [ -f "deep-experiment-logs/PHASE2_CHECKLIST.md" ] && pass "PHASE2_CHECKLIST.md exists" || fail "PHASE2_CHECKLIST.md missing — did Phase 1 generate it?"
    if [ -f "deep-experiment-logs/PHASE2_CHECKLIST.md" ]; then
        local unchecked=$(grep -c '\[ \]' deep-experiment-logs/PHASE2_CHECKLIST.md 2>/dev/null; true)
        [ "$unchecked" -eq 0 ] && pass "PHASE2_CHECKLIST: all items checked" || fail "PHASE2_CHECKLIST: $unchecked unchecked items remain"
    fi

    # EXPERIMENT_REVIEW.md must exist with PASS verdict
    [ -f "deep-experiment-logs/EXPERIMENT_REVIEW.md" ] && pass "EXPERIMENT_REVIEW.md exists" || fail "EXPERIMENT_REVIEW.md missing — did /experiment-reviewer run?"
    if [ -f "deep-experiment-logs/EXPERIMENT_REVIEW.md" ]; then
        grep -qi "PASS\|OVERALL.*PASS\|Ready for paper writing" deep-experiment-logs/EXPERIMENT_REVIEW.md && pass "experiment-reviewer verdict: PASS" || fail "experiment-reviewer did NOT pass — our method doesn't beat baselines yet"
    fi

    # SYNTHESIZE requires ≥5 seeds — check metrics.json for seed count
    local max_epochs=0
    for f in deep-experiment-logs/ROUND_*/results/metrics.json; do
        [ -f "$f" ] || continue
        local ep=$(python -c "import json; d=json.load(open('$f')); print(d.get('epochs',0))" 2>/dev/null || echo 0)
        [ "$ep" -gt "$max_epochs" ] && max_epochs=$ep
    done
    [ "$max_epochs" -ge 100 ] && pass "max training epochs: $max_epochs (need ≥100)" || fail "max training epochs: $max_epochs (need ≥100 — train longer)"

    # Check for multi-seed results
    local n_seeds=$(grep -r "seed\|n_seeds\|num_seeds" deep-experiment-logs/ROUND_*/results/metrics.json 2>/dev/null | wc -l)
    [ "$n_seeds" -ge 5 ] && pass "seed references: $n_seeds (need ≥5)" || fail "seed references: $n_seeds (need ≥5 — run multi-seed experiments)"

    # Total training volume: sum epochs across all rounds
    local total_epochs=0
    for f in deep-experiment-logs/ROUND_*/results/metrics.json; do
        [ -f "$f" ] || continue
        local ep=$(python -c "import json; d=json.load(open('$f')); print(d.get('epochs',0))" 2>/dev/null || echo 0)
        total_epochs=$((total_epochs + ep))
    done
    [ "$total_epochs" -ge 600 ] && pass "total training: $total_epochs epochs across all rounds (need ≥600)" || fail "total training: only $total_epochs epochs (need ≥600 — train more rounds and longer each)"

    [ -d "deep-experiment-logs/FIGURES/" ] && [ $(ls deep-experiment-logs/FIGURES/*.pdf 2>/dev/null | wc -l) -ge 8 ] && pass "FIGURES: >= 8 PDFs" || fail "FIGURES: < 8 PDFs"
    [ -f "deep-experiment-logs/FIGURES/fig_architecture.pdf" ] && pass "fig_architecture.pdf exists" || fail "fig_architecture.pdf missing (required as Figure 1)"

    # reproduce.sh must be executable
    [ -x "deep-experiment-logs/reproduce.sh" ] && pass "reproduce.sh is executable" || fail "reproduce.sh is not executable (run: chmod +x)"

    # Checkpoint/model files must exist (≥3: best + final + at least one intermediate)
    local n_checkpoints=$(ls checkpoints/*.pt checkpoints/*.pth 2>/dev/null | wc -l)
    [ "$n_checkpoints" -ge 3 ] && pass "checkpoints: $n_checkpoints model files (need ≥3: best+final+intermediate)" || fail "checkpoints/: only $n_checkpoints .pt files (need ≥3 — save best.pt + final.pt + ckpt_epoch_N.pt)"

    return $EXIT_CODE
}

# ─── Phase 3: Paper Writing ─────────────────────────────────────────────────
check_phase_3() {
    echo "=== Gate Check: Phase 3 — Paper Writing ==="
    [ -f "paper/main.pdf" ] && pass "main.pdf" || fail "main.pdf missing (paper not compiled)"
    [ -f "paper/main.tex" ] && pass "main.tex" || fail "main.tex missing"
    [ -f "paper/references.bib" ] && pass "references.bib" || fail "references.bib missing"

    # VENUE_CONSTRAINTS must exist (from Phase 0 template detection)
    [ -f "paper/VENUE_CONSTRAINTS.md" ] && pass "VENUE_CONSTRAINTS.md" || fail "VENUE_CONSTRAINTS.md missing"

    # Template file must exist (.cls or .sty)
    local has_template=false
    ls paper/*.cls paper/*.sty 2>/dev/null | head -1 | grep -q . && has_template=true
    $has_template && pass "LaTeX template (.cls/.sty) found" || fail "no .cls or .sty file in paper/ (template not downloaded)"

    # AI disclosure prohibited: paper must not mention AI tools
    if [ -f "paper/main.tex" ]; then
        grep -qi "claude\|chatgpt\|ai assistant\|ai-assisted\|ai generated\|language model assisted\|LLM assisted" paper/main.tex paper/sections/*.tex 2>/dev/null \
            && fail "AI disclosure detected in paper text — REMOVE IT" \
            || pass "AI disclosure check clean"
    fi

    # Bidirectional citation check
    if [ -f "paper/main.tex" ] && [ -f "paper/references.bib" ]; then
        local bib_entries=$(grep -c '^@' paper/references.bib 2>/dev/null || echo 0)
        [ "$bib_entries" -ge 10 ] && pass "references: $bib_entries entries" || fail "references: only $bib_entries entries (need >= 10)"
        # Every \cite key must exist in references.bib
        local orphan_cites=0
        for key in $(grep -oh '\\cite{[^}]*}' paper/main.tex paper/sections/*.tex 2>/dev/null | sed 's/.*{//;s/}//' | tr ',' '\n' | sed 's/^ *//' | sort -u | grep -v '^$'); do
            grep -q "{$key," paper/references.bib 2>/dev/null || { fail "orphan citation: '$key' not in references.bib"; orphan_cites=$((orphan_cites+1)); }
        done
        [ "$orphan_cites" -eq 0 ] && pass "all \\cite keys found in references.bib"
        # Every bib entry must be cited in text
        local uncited=0
        for key in $(grep -o '@article{[^,]*' paper/references.bib 2>/dev/null | sed 's/.*{//'); do
            grep -q "$key" paper/main.tex paper/sections/*.tex 2>/dev/null || { fail "uncited bib entry: '$key' (remove or cite it)"; uncited=$((uncited+1)); }
        done
        [ "$uncited" -eq 0 ] && pass "all bib entries cited in text"
    fi

    # paper/figures/ must NOT be empty (no placeholder-only directories)
    local n_figs=$(ls paper/figures/*.pdf paper/figures/*.png 2>/dev/null | wc -l)
    [ "$n_figs" -ge 4 ] && pass "paper/figures/: $n_figs figure files" || fail "paper/figures/: only $n_figs figures (need >= 4 PDF/PNG)"

    # Figure check: \includegraphics must point to existing files
    local missing_figs=0
    for fig in $(grep -oh 'includegraphics{[^}]*}' paper/main.tex paper/sections/*.tex 2>/dev/null | sed 's/.*{//;s/}//'); do
        [ -f "paper/$fig" ] || [ -f "paper/figures/$fig" ] || { fail "figure not found: $fig"; missing_figs=$((missing_figs+1)); }
    done
    [ "$missing_figs" -eq 0 ] && pass "all includegraphics files exist"

    return $EXIT_CODE
}

# ─── Phase 4: Cross-Stage Review ────────────────────────────────────────────
check_phase_4() {
    echo "=== Gate Check: Phase 4 — Cross-Stage Review ==="
    [ -f "review-stage/SUBMISSION_READY.md" ] && pass "SUBMISSION_READY.md" || fail "SUBMISSION_READY.md missing"
    [ -f "review-stage/STAGE1_IDEA_REVIEW.md" ] && pass "STAGE1_IDEA_REVIEW.md" || fail "STAGE1_IDEA_REVIEW.md missing"
    [ -f "review-stage/STAGE2_EXPERIMENT_REVIEW.md" ] && pass "STAGE2_EXPERIMENT_REVIEW.md" || fail "STAGE2_EXPERIMENT_REVIEW.md missing"
    [ -f "review-stage/STAGE3_PAPER_REVIEW.md" ] && pass "STAGE3_PAPER_REVIEW.md" || fail "STAGE3_PAPER_REVIEW.md missing"

    # Each review must contain a verdict
    for stage in 1 2 3; do
        local f="review-stage/STAGE${stage}_IDEA_REVIEW.md"
        [ "$stage" = "2" ] && f="review-stage/STAGE2_EXPERIMENT_REVIEW.md"
        [ "$stage" = "3" ] && f="review-stage/STAGE3_PAPER_REVIEW.md"
        if [ -f "$f" ]; then
            grep -qi "PASS\|REVISE\|BLOCKED" "$f" && pass "Stage $stage review contains verdict" || fail "Stage $stage review missing verdict (PASS/REVISE/BLOCKED)"
        fi
    done

    # SUBMISSION_READY must explicitly say "ready"
    if [ -f "review-stage/SUBMISSION_READY.md" ]; then
        grep -qi "ready\|pass\|submit" review-stage/SUBMISSION_READY.md && pass "SUBMISSION_READY confirms readiness" || fail "SUBMISSION_READY does not confirm readiness"
    fi

    return $EXIT_CODE
}

# ─── Dispatch ────────────────────────────────────────────────────────────────
case "$PHASE" in
    0) check_phase_0 ;;
    1) check_phase_1 ;;
    2) check_phase_2 ;;
    2-round) check_phase_2_round "${ROUND_NN:-ROUND_01}" ;;
    3) check_phase_3 ;;
    4) check_phase_4 ;;
    all)
        check_phase_0; echo
        check_phase_1; echo
        check_phase_2; echo
        check_phase_3; echo
        check_phase_4
        ;;
    *)
        echo "Usage: bash gate_check.sh <0|1|2|2-round <ROUND_NN>|3|4|all>"
        echo "  phase 0: Knowledge Base"
        echo "  phase 1: Idea Discovery"
        echo "  phase 2: Deep Experiment Loop (final outputs)"
        echo "  phase 2-round ROUND_NN: per-round 6-file audit"
        echo "  phase 3: Paper Writing"
        echo "  phase 4: Cross-Stage Review"
        echo "  all: Run all checks"
        exit 2
        ;;
esac

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}═══════════════════════════════════════${NC}"
    echo -e "${GREEN}  GATE PASS — proceed to next phase${NC}"
    echo -e "${GREEN}═══════════════════════════════════════${NC}"
else
    echo -e "\n${RED}═══════════════════════════════════════${NC}"
    echo -e "${RED}  GATE FAIL — fix issues before proceeding${NC}"
    echo -e "${RED}═══════════════════════════════════════${NC}"
fi

exit $EXIT_CODE
