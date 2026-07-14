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
#
# New-skill policy (--apply only; dry-run always just reports):
#   default (TTY, no policy flag): each new upstream skill is confirmed one by
#                                  one [y/N]; a decline is remembered in
#                                  <local>/.aris-declined.txt and never re-asked
#   --add-new:  install every new skill (does NOT un-decline previously
#               declined skills — edit/clear .aris-declined.txt for that)
#   --skip-new: skip every new skill without recording a decline (same as the
#               automatic behavior when there is no TTY)
#
# On successful --apply, writes $HOME/.aris/repo <- this repo's root (helper
# resolution chain layer 4, #366) so copy-installed skills can find tools/.

set -euo pipefail

# ─── Parse arguments ───────────────────────────────────────────────────────────
APPLY=false
MODE="global"
PROJECT_PATH=""
TARGET_SUBDIR=".claude/skills"
CUSTOM_UPSTREAM=""
CUSTOM_LOCAL=""
NEW_POLICY=""   # "" (prompt) | add | skip

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        --add-new)
            NEW_POLICY="add"
            shift
            ;;
        --skip-new)
            NEW_POLICY="skip"
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
            echo "Usage: bash tools/smart_update.sh [--apply] [--add-new|--skip-new] [--project <path> [--target-subdir <rel>]] [--upstream <path> --local <path>]"
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

# install_aris.sh creates flat PER-SKILL symlinks (the root dir is real), so
# the root-symlink check above can't see a managed flat install. The manifest
# is the authoritative marker — refuse project-mode updates when one exists.
if [[ "$MODE" == "project" && -f "$PROJECT_ROOT/.aris/installed-skills.txt" ]]; then
    REPO_ROOT_FOR_HINT="$(cd "$(dirname "$0")/.." && pwd)"
    echo "" >&2
    echo -e "\033[0;31m✗ Managed symlink install detected (manifest: $PROJECT_ROOT/.aris/installed-skills.txt)\033[0m" >&2
    echo "" >&2
    echo "smart_update is for COPIED installs. This project is managed by install_aris.sh:" >&2
    echo "  cd <aris-repo> && git pull           # updates content of existing skills" >&2
    echo "  bash $REPO_ROOT_FOR_HINT/tools/install_aris.sh \"$PROJECT_ROOT\"   # reconciles new/removed skills" >&2
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

# ─── Stale-pristine detection ──────────────────────────────────────────────────
# A local SKILL.md that is byte-identical to SOME older committed upstream
# version is NOT a user customization — it is just a stale install. This matters
# because old releases occasionally contained lines (since redacted upstream)
# that trip PERSONAL_PATTERNS; without this check such installs get stuck in
# "needs manual merge" forever even though a plain overwrite is exactly right.
# Requires the upstream dir to live inside a git clone; otherwise we skip the
# check and keep the conservative needs-merge classification.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_HISTORY_OK=false
if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    GIT_HISTORY_OK=true
fi

# ─── New-skill confirmation state (declined list + group catalog lookup) ──────
CATALOG_PATH="$REPO_ROOT/tools/skill-groups.tsv"
DECLINED_FILE="$LOCAL_DIR/.aris-declined.txt"

is_declined() {  # $1 = skill name
    [[ -f "$DECLINED_FILE" ]] && grep -qxF "$1" "$DECLINED_FILE"
}

catalog_group_of() {  # $1 = skill name -> group id, or "?" if unknown
    local g=""
    [[ -f "$CATALOG_PATH" ]] && g=$(awk -F'\t' -v s="$1" '$1=="skill" && $2==s {print $3; exit}' "$CATALOG_PATH")
    echo "${g:-?}"
}

# Layer-4 helper resolution (#366): a global pointer file lets globally/copy-
# installed skills find $ARIS_REPO/tools without a per-project install.
ensure_global_pointer() {
    local pointer="$HOME/.aris/repo"
    mkdir -p "$(dirname "$pointer")" 2>/dev/null || return 0
    local cur=""
    [[ -f "$pointer" ]] && cur="$(cat "$pointer" 2>/dev/null || true)"
    [[ "$cur" == "$REPO_ROOT" ]] && return 0
    printf '%s\n' "$REPO_ROOT" > "$pointer.tmp.$$" && mv -f "$pointer.tmp.$$" "$pointer"
}

is_pristine_historical_copy() {
    # $1 = local file, $2 = repo-relative path of its upstream counterpart
    $GIT_HISTORY_OK || return 1
    local lf="$1" rel="$2" local_hash commits c blob
    local_hash=$(git -C "$REPO_ROOT" hash-object "$lf" 2>/dev/null) || return 1
    commits=$(git -C "$REPO_ROOT" log --format='%H' -n 200 -- "$rel" 2>/dev/null) || return 1
    for c in $commits; do
        blob=$(git -C "$REPO_ROOT" rev-parse -q --verify "$c:$rel" 2>/dev/null) || continue
        if [[ "$blob" == "$local_hash" ]]; then
            return 0
        fi
    done
    return 1
}

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
declare -a STALE_PRISTINE_SKILLS=()

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
        if is_pristine_historical_copy "$local_file" "skills/$skill_name/SKILL.md"; then
            # Byte-identical to an older committed upstream version — the
            # pattern hits are old upstream content (since redacted), not a
            # user customization. Plain overwrite is the correct resolution.
            SAFE_UPDATE=$((SAFE_UPDATE + 1))
            SAFE_SKILLS+=("$skill_name")
            STALE_PRISTINE_SKILLS+=("$skill_name")
        else
            # Has personal customizations — needs careful merge
            NEEDS_MERGE=$((NEEDS_MERGE + 1))
            MERGE_SKILLS+=("$skill_name")
        fi
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

# Pre-declined subset of NEW_SKILLS (informational only in dry-run — the
# decision of what to install/skip/prompt is only made inside the --apply block).
declare -a NEW_PREDECLINED_SKILLS=()
for s in "${NEW_SKILLS[@]:-}"; do
    [[ -n "$s" ]] || continue
    is_declined "$s" && NEW_PREDECLINED_SKILLS+=("$s")
done

echo -e "${GREEN}🆕 New skills upstream (confirmed one-by-one on --apply, unless --add-new/--skip-new): ${NEW}${NC}"
for s in "${NEW_SKILLS[@]:-}"; do
    [[ -n "$s" ]] || continue
    if is_declined "$s"; then
        echo -e "   $s ${YELLOW}(previously declined — stays skipped unless --add-new)${NC}"
    else
        echo "   $s"
    fi
done
echo ""

echo -e "${BLUE}🔄 Updated upstream, no personal info (safe to replace): ${SAFE_UPDATE}${NC}"
for s in "${SAFE_SKILLS[@]:-}"; do
    [[ -n "$s" ]] || continue
    is_stale=false
    for sp in "${STALE_PRISTINE_SKILLS[@]:-}"; do
        [[ "$sp" == "$s" ]] && is_stale=true && break
    done
    if $is_stale; then
        echo -e "   $s ${BLUE}(stale pristine copy of an older release — old upstream lines trip the personal-info patterns, but it carries no local edits)${NC}"
    else
        echo "   $s"
    fi
done
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
echo -e "  ${GREEN}New upstream: $NEW${NC} (requires confirmation on --apply; ${#NEW_PREDECLINED_SKILLS[@]} previously declined)"
echo -e "  ${BLUE}Safe update: $SAFE_UPDATE${NC}"
echo -e "  ${YELLOW}Need merge:  $NEEDS_MERGE${NC}"
echo -e "  Local only: $LOCAL_ONLY"
echo ""

if $APPLY; then
    echo -e "${BLUE}Applying safe updates...${NC}"

    # ── New-skill three-state policy: interactive confirm / --add-new / --skip-new ──
    # A skill already in .aris-declined.txt is never re-asked and never installed —
    # not even by --add-new (only editing/clearing the declined file restores it).
    declare -a TO_INSTALL_NEW=()
    declare -a SKIPPED_NEW=()
    declare -a JUST_DECLINED=()

    for s in "${NEW_SKILLS[@]:-}"; do
        [[ -n "$s" ]] || continue
        if is_declined "$s"; then
            continue
        fi
        case "$NEW_POLICY" in
            add)
                TO_INSTALL_NEW+=("$s")
                ;;
            skip)
                SKIPPED_NEW+=("$s")
                ;;
            *)
                if [[ -t 0 ]]; then
                    grp="$(catalog_group_of "$s")"
                    printf "  install new skill %-30s (group: %s) [y/N] " "$s" "$grp" >&2
                    read -r reply </dev/tty
                    if [[ "$reply" =~ ^[yY] ]]; then
                        TO_INSTALL_NEW+=("$s")
                    else
                        JUST_DECLINED+=("$s")
                    fi
                else
                    SKIPPED_NEW+=("$s")
                fi
                ;;
        esac
    done

    if [[ ${#JUST_DECLINED[@]} -gt 0 ]]; then
        {
            [[ -f "$DECLINED_FILE" ]] && cat "$DECLINED_FILE"
            printf '%s\n' "${JUST_DECLINED[@]}"
        } | sort -u > "$DECLINED_FILE.tmp.$$" && mv -f "$DECLINED_FILE.tmp.$$" "$DECLINED_FILE"
    fi

    # Add accepted new skills (no existing dir to clean)
    for s in "${TO_INSTALL_NEW[@]:-}"; do
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
    echo -e "${GREEN}Done! ${#TO_INSTALL_NEW[@]} new + $SAFE_UPDATE updated.${NC}"

    if [[ ${#SKIPPED_NEW[@]} -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  ${#SKIPPED_NEW[@]} new skill(s) skipped, not declined: ${SKIPPED_NEW[*]}${NC}"
        echo -e "${YELLOW}   Re-run with --add-new to install them (or re-run interactively on a TTY).${NC}"
    fi
    if [[ ${#JUST_DECLINED[@]} -gt 0 ]]; then
        echo -e "  Declined just now (recorded in $DECLINED_FILE, won't be asked again): ${JUST_DECLINED[*]}"
    fi
    if [[ ${#NEW_PREDECLINED_SKILLS[@]} -gt 0 ]]; then
        echo -e "  Previously declined, still skipped: ${#NEW_PREDECLINED_SKILLS[@]} (edit $DECLINED_FILE to reconsider)"
    fi

    if [[ $NEEDS_MERGE -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  $NEEDS_MERGE skills have personal customizations and were NOT updated.${NC}"
        echo -e "${YELLOW}   Review manually: ${MERGE_SKILLS[*]}${NC}"
        echo -e "${YELLOW}   Tip: diff the local and upstream SKILL.md files to merge changes${NC}"
    fi

    ensure_global_pointer
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
