#!/bin/bash
# Monitor all agent progress

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=========================================="
echo "MRI Motion Correction - Agent Status"
echo "=========================================="
echo ""

SUB_DIRS=(
    "sub-1-kspace:k-space Domain"
    "sub-2-image:Image Domain"
    "sub-3-pinn:PINN"
    "sub-4-selfsuper:Self-Supervised"
    "sub-5-diffusion:Diffusion Models"
    "sub-6-multiscale:Multi-Scale"
    "sub-7-brain:Brain-Specific"
    "sub-8-realtime:Fast/Lightweight"
)

check_status() {
    local dir=$1
    local name=$2
    local full_path="$PROJECT_ROOT/sub-dirs/$dir"

    printf "%-20s " "$name:"

    if [ -f "$full_path/IDEA_REPORT.md" ]; then
        # Extract status from file
        if grep -q "RECOMMENDED" "$full_path/IDEA_REPORT.md" 2>/dev/null; then
            echo "✅ COMPLETE (has recommendation)"
        else
            echo "🔄 IN PROGRESS (IDEA_REPORT exists)"
        fi
    elif [ -f "$full_path/refine-logs/FINAL_PROPOSAL.md" ]; then
        echo "✅ REFINED (proposal ready)"
    elif [ -f "$full_path/CLAUDE.md" ]; then
        echo "⏳ READY (waiting for start)"
    else
        echo "⬜ NOT STARTED"
    fi
}

echo "Agent Status:"
echo "-------------"
for item in "${SUB_DIRS[@]}"; do
    IFS=':' read -r dir name <<< "$item"
    check_status "$dir" "$name"
done

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="

completed=$(find "$PROJECT_ROOT/sub-dirs" -name "IDEA_REPORT.md" 2>/dev/null | wc -l)
ready=$(find "$PROJECT_ROOT/sub-dirs" -name "CLAUDE.md" 2>/dev/null | wc -l)

echo "Completed: $completed/8"
echo "Ready to start: $ready/8"
echo ""

if [ "$completed" -eq 8 ]; then
    echo "🎉 All agents complete! Time to converge."
    echo "   Run: python3 tools/compare_directions.py"
elif [ "$completed" -gt 0 ]; then
    echo "⏳ Some agents still running. Check back later."
else
    echo "🚀 No agents started yet. Run: ./tools/launch_agents.sh 1"
fi
