#!/usr/bin/env bash
# switch_reviewer.sh — Switch the reviewer backend between Codex MCP and Claude CLI.
#
# Usage:
#   ./tools/switch_reviewer.sh claude   # Switch to Claude CLI as reviewer
#   ./tools/switch_reviewer.sh codex    # Switch back to Codex MCP (GPT)
#   ./tools/switch_reviewer.sh status   # Show current reviewer backend
#
# This script:
# 1. Copies the appropriate skill overlay files into skills/
# 2. Registers/deregisters the claude-review MCP server in Claude Code
#
# Prerequisites:
#   - Claude Code CLI installed
#   - This repo cloned locally

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
USER_SKILLS_DIR="$HOME/.claude/skills"
CC_CLAUDE_OVERLAY="$SKILLS_DIR/skills-cc-claude-review"
MCP_SERVER="$REPO_ROOT/mcp-servers/claude-review/server.py"

# Skills that have Claude reviewer overlays
OVERLAY_SKILLS=(
    ablation-planner
    auto-paper-improvement-loop
    auto-review-loop
    experiment-bridge
    grant-proposal
    idea-creator
    idea-discovery
    idea-discovery-robot
    novelty-check
    paper-figure
    paper-illustration
    paper-plan
    paper-poster
    paper-slides
    paper-write
    paper-writing
    rebuttal
    research-pipeline
    research-refine
    research-refine-pipeline
    research-review
    result-to-claim
    training-check
)

usage() {
    echo "Usage: $0 {claude|codex|status}"
    echo ""
    echo "  claude  — Use Claude CLI as the external reviewer (via claude-review MCP)"
    echo "  codex   — Use Codex MCP (GPT) as the external reviewer (default)"
    echo "  status  — Show which reviewer backend is currently active"
    exit 1
}

detect_current() {
    # Check user-level first (Claude Code reads ~/.claude/skills/ with priority)
    local skill_file="$USER_SKILLS_DIR/research-review/SKILL.md"
    [ -f "$skill_file" ] || skill_file="$SKILLS_DIR/research-review/SKILL.md"
    if [ ! -f "$skill_file" ]; then
        echo "unknown"
        return
    fi
    if grep -q "mcp__claude-review__review_start" "$skill_file" 2>/dev/null; then
        echo "claude"
    elif grep -q "mcp__codex__codex" "$skill_file" 2>/dev/null; then
        echo "codex"
    else
        echo "unknown"
    fi
}

switch_to_claude() {
    local current
    current="$(detect_current)"
    if [ "$current" = "claude" ]; then
        echo "Already using Claude CLI as reviewer. Nothing to do."
        return 0
    fi

    echo "Switching reviewer backend: Codex MCP -> Claude CLI"
    echo ""

    # 1. Generate overlays if they don't exist
    if [ ! -d "$CC_CLAUDE_OVERLAY" ]; then
        echo "[1/3] Generating Claude reviewer overlay skills..."
        python3 "$REPO_ROOT/tools/generate_cc_claude_review_overrides.py"
    else
        echo "[1/3] Claude reviewer overlay skills already exist."
    fi

    # 2. Backup originals and copy overlays (both project and user-level)
    echo "[2/3] Installing overlay skills..."
    local count=0
    for skill in "${OVERLAY_SKILLS[@]}"; do
        local src="$CC_CLAUDE_OVERLAY/$skill/SKILL.md"
        [ -f "$src" ] || continue

        # Project-level: skills/
        local dst="$SKILLS_DIR/$skill/SKILL.md"
        if [ -f "$dst" ]; then
            [ -f "$dst.codex-bak" ] || cp "$dst" "$dst.codex-bak"
            cp "$src" "$dst"
        fi

        # User-level: ~/.claude/skills/ (Claude Code reads this first)
        local udst="$USER_SKILLS_DIR/$skill/SKILL.md"
        if [ -f "$udst" ]; then
            [ -f "$udst.codex-bak" ] || cp "$udst" "$udst.codex-bak"
            cp "$src" "$udst"
        fi

        count=$((count + 1))
    done
    echo "  Installed $count overlay skills (project + user-level)."

    # 3. Register claude-review MCP server
    echo "[3/3] Registering claude-review MCP server..."
    if command -v claude &>/dev/null; then
        # Remove first to avoid duplicates, ignore errors
        claude mcp remove claude-review 2>/dev/null || true
        claude mcp add claude-review -s user -- python3 "$MCP_SERVER"
        echo "  MCP server registered."
    else
        echo "  WARNING: 'claude' CLI not found. Please register manually:"
        echo "    claude mcp add claude-review -s user -- python3 $MCP_SERVER"
    fi

    echo ""
    echo "Done! Reviewer backend is now: Claude CLI"
    echo ""
    echo "Optional: set a specific Claude model for reviews:"
    echo "  claude mcp remove claude-review"
    echo "  claude mcp add claude-review -s user -e CLAUDE_REVIEW_MODEL=claude-opus-4-1 -- python3 $MCP_SERVER"
}

switch_to_codex() {
    local current
    current="$(detect_current)"
    if [ "$current" = "codex" ]; then
        echo "Already using Codex MCP as reviewer. Nothing to do."
        return 0
    fi

    echo "Switching reviewer backend: Claude CLI -> Codex MCP"
    echo ""

    # 1. Restore backed-up originals (both project and user-level)
    echo "[1/2] Restoring original Codex-based skills..."
    local restored=0
    for skill in "${OVERLAY_SKILLS[@]}"; do
        # Project-level
        local dst="$SKILLS_DIR/$skill/SKILL.md"
        local bak="$dst.codex-bak"
        if [ -f "$bak" ]; then
            cp "$bak" "$dst"
            rm "$bak"
            restored=$((restored + 1))
        fi

        # User-level
        local udst="$USER_SKILLS_DIR/$skill/SKILL.md"
        local ubak="$udst.codex-bak"
        if [ -f "$ubak" ]; then
            cp "$ubak" "$udst"
            rm "$ubak"
        fi
    done
    echo "  Restored $restored skills (project + user-level)."

    # 2. Deregister claude-review MCP server
    echo "[2/2] Deregistering claude-review MCP server..."
    if command -v claude &>/dev/null; then
        claude mcp remove claude-review 2>/dev/null || true
        echo "  MCP server removed."
    else
        echo "  WARNING: 'claude' CLI not found. Please remove manually."
    fi

    echo ""
    echo "Done! Reviewer backend is now: Codex MCP (GPT)"
}

show_status() {
    local current
    current="$(detect_current)"
    case "$current" in
        claude)
            echo "Current reviewer backend: Claude CLI (via claude-review MCP)"
            echo ""
            echo "Flow: Claude Code -> claude-review MCP -> fresh Claude CLI -> Claude API"
            ;;
        codex)
            echo "Current reviewer backend: Codex MCP (GPT)"
            echo ""
            echo "Flow: Claude Code -> Codex MCP -> OpenAI API"
            ;;
        *)
            echo "Current reviewer backend: unknown"
            echo ""
            echo "Could not determine the active backend. Check skills/research-review/SKILL.md"
            ;;
    esac

    # Check if claude-review MCP is registered
    if command -v claude &>/dev/null; then
        if claude mcp list 2>/dev/null | grep -q "claude-review"; then
            echo "claude-review MCP: registered"
        else
            echo "claude-review MCP: not registered"
        fi
    fi
}

# Main
[ $# -lt 1 ] && usage

case "$1" in
    claude)  switch_to_claude ;;
    codex)   switch_to_codex ;;
    status)  show_status ;;
    *)       usage ;;
esac
