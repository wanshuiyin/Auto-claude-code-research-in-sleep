#!/bin/bash
# MRI Motion Correction - Multi-Agent Launch Script
# Usage: ./launch_agents.sh [batch_number]
#   batch_number: 1 (first 4 agents) or 2 (last 4 agents)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BATCH="${1:-1}"

echo "=========================================="
echo "MRI Motion Correction - Multi-Agent Launch"
echo "Batch: $BATCH"
echo "=========================================="
echo ""

# Function to launch an agent
launch_agent() {
    local num=$1
    local name=$2
    local dir=$3
    local prompt=$4

    echo "[$num/8] Launching Agent $num: $name"
    echo "  Directory: $dir"
    echo "  Command: /idea-discovery ..."
    echo ""

    # Create agent-specific CLAUDE.md
    cat > "$dir/CLAUDE.md" << EOF
# Agent $num: $name

## Mission
Explore "$name" direction for MRI motion artifact correction.

## Context
- Parent project: MRI Motion Correction Research
- This workspace: $name exploration
- Resources: 4x RTX 4090 (manual deployment)

## Quick Commands

### Start exploration
/idea-discovery "$prompt" \\
    — AUTO_PROCEED: false \\
    — PILOT_MAX_HOURS: 0 \\
    — sources: zotero, web \\
    — arxiv download: true

### After idea-discovery completes
/research-refine-pipeline "[top idea from IDEA_REPORT.md]"

### Generate experiment code
/experiment-bridge — code review: true

## Output Files
- IDEA_REPORT.md (main output)
- refine-logs/FINAL_PROPOSAL.md
- refine-logs/EXPERIMENT_PLAN.md

## Parent Project
See $PROJECT_ROOT/CLAUDE.md for overall status.
EOF

    echo "  Created $dir/CLAUDE.md"
    echo ""
}

if [ "$BATCH" == "1" ]; then
    echo "=== LAUNCHING BATCH 1 (Agents 1-4) ==="
    echo ""

    launch_agent \
        1 \
        "k-space Domain Motion Correction" \
        "$PROJECT_ROOT/sub-dirs/sub-1-kspace" \
        "MRI motion artifact correction in k-space domain - learn motion parameters directly from k-space data without navigator echoes"

    launch_agent \
        2 \
        "Image Domain Post-Processing" \
        "$PROJECT_ROOT/sub-dirs/sub-2-image" \
        "MRI motion artifact correction in image domain - deep learning based post-processing to remove artifacts from reconstructed images"

    launch_agent \
        3 \
        "Physics-Informed Neural Networks" \
        "$PROJECT_ROOT/sub-dirs/sub-3-pinn" \
        "Physics-informed neural networks for MRI motion correction - embed MRI forward model into deep learning for physically consistent motion artifact correction"

    launch_agent \
        4 \
        "Self-Supervised Correction" \
        "$PROJECT_ROOT/sub-dirs/sub-4-selfsuper" \
        "Self-supervised MRI motion artifact correction without ground truth - blind motion correction using data intrinsic structure"

elif [ "$BATCH" == "2" ]; then
    echo "=== LAUNCHING BATCH 2 (Agents 5-8) ==="
    echo ""

    launch_agent \
        5 \
        "Diffusion Model Motion Estimation" \
        "$PROJECT_ROOT/sub-dirs/sub-5-diffusion" \
        "Diffusion models for MRI motion artifact correction - leverage generative priors for high-quality motion artifact removal"

    launch_agent \
        6 \
        "Multi-Scale Hierarchical Methods" \
        "$PROJECT_ROOT/sub-dirs/sub-6-multiscale" \
        "Multi-scale hierarchical MRI motion correction - handle different motion artifacts at different resolution levels"

    launch_agent \
        7 \
        "Brain-Specific Motion Correction" \
        "$PROJECT_ROOT/sub-dirs/sub-7-brain" \
        "Organ-specific motion correction for brain MRI - tailored motion models for neuroimaging applications leveraging rigid-body constraints"

    launch_agent \
        8 \
        "Fast and Lightweight Correction" \
        "$PROJECT_ROOT/sub-dirs/sub-8-realtime" \
        "Fast and lightweight MRI motion correction for clinical deployment - real-time capable methods with minimal computational overhead"

else
    echo "Error: Invalid batch number. Use 1 or 2."
    echo "  Batch 1: Agents 1-4"
    echo "  Batch 2: Agents 5-8"
    exit 1
fi

echo "=========================================="
echo "Batch $BATCH setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Open each sub-directory in a separate Conductor workspace"
echo "2. Run the /idea-discovery command from the CLAUDE.md in each workspace"
echo "3. Monitor progress in each sub-dir/IDEA_REPORT.md"
echo ""
echo "To launch Batch 2, run:"
echo "  ./launch_agents.sh 2"
echo ""
