#!/usr/bin/env bash
# ARIS Smart Skill Update
# Intelligently compares local skills with upstream, detects personal
# customizations, and recommends safe update strategy per skill.
#
# Usage:
#   Global (default):
#     bash tools/smart_update.sh [--apply]
#   Project-level (Claude Code):
#     bash tools/smart_update.sh --project <path> [--apply]
#   Project-level (Codex CLI):
#     bash tools/smart_update.sh --project <path> --target-subdir .agents/skills/aris [--apply]
#   Custom paths:
#     bash tools/smart_update.sh --upstream <path> --local <path> [--apply]
#
#   --apply: actually perform the updates (default: dry-run analysis only)
#   --project <path>: project root — upstream from repo, local from <path>/<target-subdir>
#   --target-subdir <relative>: project-mode skill subdirectory (default: .claude/skills)
#                               common values: .claude/skills, .claude/skills/aris,
#                                              .agents/skills, .agents/skills/aris
#                               must be a relative path
#   --upstream <path>: explicit upstream skills directory
#   --local <path>: explicit local skills directory

set -euo pipefail

# ─── Parse arguments ───────────────────────────────────────────────────────────
APPLY=false
MODE="global"
PROJECT_PATH=""
TARGET_SUBDIR=".claude/skills"
CUSTOM_UPSTREAM=""
CUSTOM_LOCAL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        --project)
            MODE="project"
            PROJECT_PATH="${2:?--project requires a path argument}"
            shift 2
            ;;
        --target-subdir)
            TARGET_SUBDIR="${2:?--target-subdir requires a relative path argument}"
            if [[ "$TARGET_SUBDIR" == /* ]]; then
                echo "Error: --target-subdir must be a relative path (got: $TARGET_SUBDIR)" >&2
                echo "Hint: use --local for absolute paths" >&2
                exit 1
            fi
            shift 2
            ;;
        --upstream)
            MODE="explicit"
            CUSTOM_UPSTREAM="${2:?--upstream requires a path argument}"
            shift 2
            ;;
        --local)
            MODE="explicit"
            CUSTOM_LOCAL="${2:?--local requires a path argument}"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: bash tools/smart_update.sh [--apply] [--project <path> [--target-subdir <rel>]] [--upstream <path> --local <path>]"
            exit 1
            ;;
    esac
done

# ─── Resolve paths ─────────────────────────────────────────────────────────────
REPO_SKILLS_DIR="$(cd "$(dirname "$0")/.." && pwd)/skills"

case "$MODE" in
    project)
        # Resolve project path
        if [[ "$PROJECT_PATH" == /* ]]; then
            PROJECT_ROOT="$PROJECT_PATH"
        else
            PROJECT_ROOT="$(cd "$PROJECT_PATH" && pwd)"
        fi
        # Upstream always from repo
        UPSTREAM_DIR="$REPO_SKILLS_DIR"
        LOCAL_DIR="$PROJECT_ROOT/$TARGET_SUBDIR"
        SCOPE="Project: $PROJECT_ROOT (subdir: $TARGET_SUBDIR)"

        # Platform marker auto-detect: warn on mismatch (never silently switch)
        HAS_CLAUDE_MARKERS=false
        HAS_CODEX_MARKERS=false
        [[ -e "$PROJECT_ROOT/CLAUDE.md" || -e "$PROJECT_ROOT/.claude/skills" || -e "$PROJECT_ROOT/.claude/settings.json" ]] && HAS_CLAUDE_MARKERS=true
        [[ -e "$PROJECT_ROOT/AGENTS.md" || -e "$PROJECT_ROOT/.agents/skills" || -e "$PROJECT_ROOT/.codex/config.toml" ]] && HAS_CODEX_MARKERS=true
        if $HAS_CLAUDE_MARKERS && ! $HAS_CODEX_MARKERS && [[ "$TARGET_SUBDIR" == .agents/* ]]; then
            echo -e "\033[1;33m⚠️  Warning: project has Claude markers but --target-subdir points to Codex path ($TARGET_SUBDIR)\033[0m" >&2
        fi
        if $HAS_CODEX_MARKERS && ! $HAS_CLAUDE_MARKERS && [[ "$TARGET_SUBDIR" == .claude/* ]]; then
            echo -e "\033[1;33m⚠️  Warning: project has Codex markers but --target-subdir points to Claude path ($TARGET_SUBDIR)\033[0m" >&2
        fi
        ;;
    explicit)
        if [[ -z "$CUSTOM_UPSTREAM" ]] || [[ -z "$CUSTOM_LOCAL" ]]; then
            echo "Error: --upstream and --local must both be specified"
            exit 1
        fi
        UPSTREAM_DIR="$CUSTOM_UPSTREAM"
        LOCAL_DIR="$CUSTOM_LOCAL"
        SCOPE="Custom"
        ;;
    *)
        # Global default
        UPSTREAM_DIR="$REPO_SKILLS_DIR"
        LOCAL_DIR="${HOME}/.claude/skills"
        SCOPE="Global"
        ;;
esac

# ─── Deprecate nested --target-subdir (.claude/skills/aris, .agents/skills/aris) ──
# Nested install hides skills from Claude Code's slash-command discovery (it scans
# only one level deep). The replacement is the flat install via install_aris.sh.
if [[ "$TARGET_SUBDIR" == ".claude/skills/aris" || "$TARGET_SUBDIR" == ".agents/skills/aris" ]]; then
    REPO_ROOT_FOR_HINT="$(cd "$(dirname "$0")/.." && pwd)"
    echo "" >&2
    echo -e "\033[1;33m⚠️  --target-subdir $TARGET_SUBDIR is DEPRECATED\033[0m" >&2
    echo "" >&2
    echo "  Reason: the nested 'aris/' subdirectory hides skills from Claude Code's" >&2
    echo "          slash-command discovery (which only scans .claude/skills/ one level deep)." >&2
    echo "" >&2
    echo "  Switch to the flat install (auto-reconciles new/removed skills on re-run):" >&2
    echo "    bash $REPO_ROOT_FOR_HINT/tools/install_aris.sh \"${PROJECT_PATH:-<project>}\"" >&2
    echo "" >&2
    echo "  To migrate an existing nested install:" >&2
    echo "    bash $REPO_ROOT_FOR_HINT/tools/install_aris.sh \"${PROJECT_PATH:-<project>}\" --from-old" >&2
    echo "    (for COPY-style installs, also pass --migrate-copy keep-user|prefer-upstream)" >&2
    echo "" >&2
    if $APPLY; then
        echo -e "\033[0;31mRefusing to --apply with deprecated nested target. Use install_aris.sh instead.\033[0m" >&2
        exit 2
    fi
    echo "(continuing dry-run analysis for backward compatibility — no changes will be made)" >&2
    echo "" >&2
fi

# ─── Refuse to operate on symlinked installs (those use install_aris.sh, not smart_update) ──
if [[ -L "$LOCAL_DIR" ]]; then
    LINK_TARGET="$(readlink "$LOCAL_DIR")"
    REPO_ROOT_FOR_HINT="$(cd "$(dirname "$0")/.." && pwd)"
    echo "" >&2
    echo -e "\033[0;31m✗ Local skill directory is a symlink: $LOCAL_DIR\033[0m" >&2
    echo "  → $LINK_TARGET" >&2
    echo "" >&2
    echo "smart_update is for COPIED installs. Symlinked installs are managed by install_aris.sh:" >&2
    echo "  cd <aris-repo> && git pull           # updates content of existing skills" >&2
    echo "  bash $REPO_ROOT_FOR_HINT/tools/install_aris.sh <project>   # reconciles new/removed skills" >&2
    echo "" >&2
    exit 2
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Personal info patterns (paths, IPs, API keys, usernames, server configs)
PERSONAL_PATTERNS=(
    'ssh '
    'SJTUServer'
    'rfyang'
    'yangruofeng'
    'api_key'
    'API_KEY'
    'sk-'
    'token'
    '@sjtu'
    '@gmail'
    '/home/'
    '/Users/'
    'CUDA_VISIBLE'
    'wandb_project'
    'server_ip'
    'gpu_server'
    'screen -'
    'conda activate'
    '192\.168\.'
    '10\.\d+\.'
    '122\.'
)

echo -e "${BLUE}━━━ ARIS Smart Skill Update ━━━${NC}"
echo -e "Scope:    ${SCOPE}"
echo -e "Upstream: ${UPSTREAM_DIR}"
echo -e "Local:    ${LOCAL_DIR}"
echo ""

if [[ ! -d "$UPSTREAM_DIR" ]]; then
    echo -e "${RED}Upstream skills directory not found: ${UPSTREAM_DIR}${NC}"
    exit 1
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
    echo -e "${RED}Local skills directory not found: ${LOCAL_DIR}${NC}"
    exit 1
fi

# Counters
NEW=0
IDENTICAL=0
SAFE_UPDATE=0
NEEDS_MERGE=0
LOCAL_ONLY=0

# Results arrays
declare -a NEW_SKILLS=()
declare -a IDENTICAL_SKILLS=()
declare -a SAFE_SKILLS=()
declare -a MERGE_SKILLS=()
declare -a LOCAL_SKILLS=()

# Track upstream skill names for local-only detection
declare -a UPSTREAM_NAMES=()

# Check each upstream skill
for skill_dir in "$UPSTREAM_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    [[ "$skill_name" == "skills-codex" ]] && continue  # skip codex mirror
    [[ "$skill_name" == "shared-references" ]] && continue  # handled separately

    UPSTREAM_NAMES+=("$skill_name")

    local_skill="$LOCAL_DIR/$skill_name"
    upstream_file="$skill_dir/SKILL.md"

    if [[ ! -f "$upstream_file" ]]; then
        continue
    fi

    if [[ ! -d "$local_skill" ]]; then
        # New skill — doesn't exist locally
        NEW=$((NEW + 1))
        NEW_SKILLS+=("$skill_name")
        continue
    fi

    local_file="$local_skill/SKILL.md"
    if [[ ! -f "$local_file" ]]; then
        NEW=$((NEW + 1))
        NEW_SKILLS+=("$skill_name")
        continue
    fi

    # Compare
    if diff -q "$upstream_file" "$local_file" > /dev/null 2>&1; then
        # Identical
        IDENTICAL=$((IDENTICAL + 1))
        IDENTICAL_SKILLS+=("$skill_name")
        continue
    fi

    # Different — check if local has personal info
    has_personal=false
    for pattern in "${PERSONAL_PATTERNS[@]}"; do
        # Check if the LOCAL version has lines matching personal patterns
        # that the UPSTREAM version does NOT have
        local_matches=$(grep -c "$pattern" "$local_file" 2>/dev/null || true)
        local_matches=${local_matches:-0}
        upstream_matches=$(grep -c "$pattern" "$upstream_file" 2>/dev/null || true)
        upstream_matches=${upstream_matches:-0}
        if [[ $local_matches -gt $upstream_matches ]]; then
            has_personal=true
            break
        fi
    done

    if $has_personal; then
        # Has personal customizations — needs careful merge
        NEEDS_MERGE=$((NEEDS_MERGE + 1))
        MERGE_SKILLS+=("$skill_name")
    else
        # Changed upstream, no personal info in local — safe to replace
        SAFE_UPDATE=$((SAFE_UPDATE + 1))
        SAFE_SKILLS+=("$skill_name")
    fi
done

# Check for local-only skills (not in upstream)
for skill_dir in "$LOCAL_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    [[ "$skill_name" == "shared-references" ]] && continue
    found=false
    for uname in "${UPSTREAM_NAMES[@]:-}"; do
        if [[ "$uname" == "$skill_name" ]]; then
            found=true
            break
        fi
    done
    if ! $found; then
        LOCAL_ONLY=$((LOCAL_ONLY + 1))
        LOCAL_SKILLS+=("$skill_name")
    fi
done

# Report
echo -e "${GREEN}✅ Identical (no action needed): ${IDENTICAL}${NC}"
for s in "${IDENTICAL_SKILLS[@]:-}"; do [[ -n "$s" ]] && echo "   $s"; done
echo ""

echo -e "${GREEN}🆕 New skills (safe to add): ${NEW}${NC}"
for s in "${NEW_SKILLS[@]:-}"; do [[ -n "$s" ]] && echo "   $s"; done
echo ""

echo -e "${BLUE}🔄 Updated upstream, no personal info (safe to replace): ${SAFE_UPDATE}${NC}"
for s in "${SAFE_SKILLS[@]:-}"; do [[ -n "$s" ]] && echo "   $s"; done
echo ""

echo -e "${YELLOW}⚠️  Updated upstream + local customizations (needs manual merge): ${NEEDS_MERGE}${NC}"
for s in "${MERGE_SKILLS[@]:-}"; do
    [[ -n "$s" ]] && echo "   $s"
    if [[ -n "$s" ]]; then
        # Show what personal patterns were found
        local_file="$LOCAL_DIR/$s/SKILL.md"
        for pattern in "${PERSONAL_PATTERNS[@]}"; do
            # `|| true`: under `set -euo pipefail` this assignment would otherwise
            # abort the whole script — grep exits 1 on no-match, and even on a match
            # `head -1` closes the pipe early so grep dies with SIGPIPE (141). Either
            # way pipefail propagates the failure and `set -e` kills the run *before*
            # the Summary and the apply block, so `--apply` silently writes nothing
            # whenever a skill is flagged "needs merge".
            match=$(grep -n "$pattern" "$local_file" 2>/dev/null | head -1 || true)
            if [[ -n "$match" ]]; then
                echo -e "     ${YELLOW}→ contains: ${match}${NC}"
                break
            fi
        done
    fi
done
echo ""

echo -e "${NC}📦 Local-only skills (yours, not in upstream): ${LOCAL_ONLY}"
for s in "${LOCAL_SKILLS[@]:-}"; do [[ -n "$s" ]] && echo "   $s"; done
echo ""

# Summary
TOTAL=$((NEW + IDENTICAL + SAFE_UPDATE + NEEDS_MERGE))
echo -e "${BLUE}━━━ Summary ━━━${NC}"
echo -e "Total upstream skills: $TOTAL"
echo -e "  ${GREEN}Up to date:  $IDENTICAL${NC}"
echo -e "  ${GREEN}New to add:  $NEW${NC}"
echo -e "  ${BLUE}Safe update: $SAFE_UPDATE${NC}"
echo -e "  ${YELLOW}Need merge:  $NEEDS_MERGE${NC}"
echo -e "  Local only: $LOCAL_ONLY"
echo ""

if $APPLY; then
    echo -e "${BLUE}Applying safe updates...${NC}"

    # Add new skills (no existing dir to clean)
    for s in "${NEW_SKILLS[@]:-}"; do
        if [[ -n "$s" ]]; then
            cp -r "$UPSTREAM_DIR/$s" "$LOCAL_DIR/"
            echo -e "  ${GREEN}+ Added: $s${NC}"
        fi
    done

    # Replace safely updated skills (rm-then-copy to avoid stale-file bug:
    # plain `cp -r` overlays and leaves files that upstream removed)
    for s in "${SAFE_SKILLS[@]:-}"; do
        if [[ -n "$s" ]]; then
            rm -rf "$LOCAL_DIR/$s"
            cp -r "$UPSTREAM_DIR/$s" "$LOCAL_DIR/"
            echo -e "  ${BLUE}↑ Updated: $s${NC}"
        fi
    done

    # Update shared-references (same fix)
    if [[ -d "$UPSTREAM_DIR/shared-references" ]]; then
        rm -rf "$LOCAL_DIR/shared-references"
        cp -r "$UPSTREAM_DIR/shared-references" "$LOCAL_DIR/"
        echo -e "  ${BLUE}↑ Updated: shared-references${NC}"
    fi

    echo ""
    echo -e "${GREEN}Done! $NEW new + $SAFE_UPDATE updated.${NC}"

    if [[ $NEEDS_MERGE -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  $NEEDS_MERGE skills have personal customizations and were NOT updated.${NC}"
        echo -e "${YELLOW}   Review manually: ${MERGE_SKILLS[*]}${NC}"
        echo -e "${YELLOW}   Tip: diff the local and upstream SKILL.md files to merge changes${NC}"
    fi
else
    case "$MODE" in
        project)
            if [[ "$TARGET_SUBDIR" == ".claude/skills" ]]; then
                CMD_HINT="bash tools/smart_update.sh --project \"$PROJECT_ROOT\" --apply"
            else
                CMD_HINT="bash tools/smart_update.sh --project \"$PROJECT_ROOT\" --target-subdir \"$TARGET_SUBDIR\" --apply"
            fi
            ;;
        explicit)
            CMD_HINT="bash tools/smart_update.sh --upstream \"$UPSTREAM_DIR\" --local \"$LOCAL_DIR\" --apply"
            ;;
        *)
            CMD_HINT="bash tools/smart_update.sh --apply"
            ;;
    esac
    echo -e "Dry run complete. Run with ${GREEN}--apply${NC} to perform updates:"
    echo -e "  ${GREEN}${CMD_HINT}${NC}"
fi
