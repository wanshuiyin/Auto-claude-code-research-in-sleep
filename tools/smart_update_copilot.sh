#!/usr/bin/env bash
# smart_update_copilot.sh -- update copied ARIS skills for Copilot CLI safely.
#
# Default upstream:
#   repo/skills (mainline, excluding codex-specific packages)
#
# Default local targets:
#   global:  ~/.copilot/skills
#   project: <project>/.github/skills
#
# This tool is for copied installs only. If the target is managed by
# install_aris_copilot.sh (manifest + symlinks), it refuses and points to:
#   git pull + install_aris_copilot.sh --reconcile
#
# Customization detection:
#   On first --apply, records SHA-256 checksums of installed files to
#   <local>/.aris-copilot-baselines.sha256. On subsequent runs, a file is
#   considered "customized" if its current hash differs from the recorded
#   baseline (i.e., user modified it after install). Files matching their
#   baseline are safe to overwrite with the new upstream version.
#
# New-skill policy (--apply only; dry-run always just reports):
#   default (TTY, no policy flag): each new upstream skill is confirmed one by
#                                  one [y/N]; a decline is remembered in
#                                  <local>/.aris-declined.txt and never re-asked
#   --add-new:  install every new skill (does NOT un-decline previously
#               declined skills)
#   --skip-new: skip every new skill without recording a decline (same as the
#               automatic behavior when there is no TTY)
# shared-references is support content, not a selectable skill: it is always
# kept in sync and never subject to this confirmation.
#
# On successful --apply, writes $HOME/.aris/repo <- this repo's root (helper
# resolution chain layer 4, #366) so copy-installed skills can find tools/.

set -euo pipefail

APPLY=false
MODE="global"
PROJECT_PATH=""
CUSTOM_UPSTREAM=""
CUSTOM_LOCAL=""
HAS_CUSTOM_UPSTREAM=false
HAS_CUSTOM_LOCAL=false
NEW_POLICY=""   # "" (prompt) | add | skip

usage() { sed -n '2,34p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
        --add-new) NEW_POLICY="add"; shift ;;
        --skip-new) NEW_POLICY="skip"; shift ;;
        --project) MODE="project"; PROJECT_PATH="${2:?--project requires path}"; shift 2 ;;
        --upstream) MODE="explicit"; HAS_CUSTOM_UPSTREAM=true; CUSTOM_UPSTREAM="${2:?--upstream requires path}"; shift 2 ;;
        --local) MODE="explicit"; HAS_CUSTOM_LOCAL=true; CUSTOM_LOCAL="${2:?--local requires path}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --*) echo "Unknown option: $1" >&2; exit 2 ;;
        *) echo "Unexpected positional argument: $1" >&2; exit 2 ;;
    esac
done

log() { echo "$@"; }
die() { echo "error: $*" >&2; exit 1; }
warn() { echo "warning: $*" >&2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_UPSTREAM="$REPO_ROOT/skills"

# Directories to skip when scanning upstream skills/.
# This pattern MUST stay in sync with install_aris_copilot.sh SKIP_DIRS.
# shared-references is NOT skipped here -- it's a valid update target for copy installs.
SKIP_DIRS_PATTERN="^(skills-codex|skills-codex-claude-review|skills-codex-gemini-review)$"

# Baseline checksum file for hash-based customization detection
BASELINE_FILE_NAME=".aris-copilot-baselines.sha256"

resolve_upstream() {
    if $HAS_CUSTOM_UPSTREAM; then
        [[ -d "$CUSTOM_UPSTREAM" ]] || die "upstream path not found: $CUSTOM_UPSTREAM"
        echo "$CUSTOM_UPSTREAM"
    else
        [[ -d "$BASE_UPSTREAM" ]] || die "default upstream not found: $BASE_UPSTREAM"
        echo "$BASE_UPSTREAM"
    fi
}

resolve_local() {
    if $HAS_CUSTOM_LOCAL; then
        echo "$CUSTOM_LOCAL"
    elif [[ "$MODE" == "project" ]]; then
        local p
        p="$(cd "$PROJECT_PATH" 2>/dev/null && pwd)" || die "project path not found: $PROJECT_PATH"
        echo "$p/.github/skills"
    else
        echo "$HOME/.copilot/skills"
    fi
}

# Compute SHA-256 of a file (portable across GNU/BSD)
file_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        # Fallback: no hash tool available, return empty (forces "changed" detection)
        echo ""
    fi
}

# Get baseline hash for a skill's SKILL.md from the baseline file
get_baseline_hash() {
    local baseline_file="$1" skill_name="$2"
    if [[ -f "$baseline_file" ]]; then
        awk -v name="$skill_name" '$2 == name {print $1; exit}' "$baseline_file"
    fi
}

# Record baseline hash for a skill after install/update
record_baseline() {
    local baseline_file="$1" skill_name="$2" hash="$3"
    local tmp="${baseline_file}.tmp.$$"
    # Remove old entry (if any) and append new one
    if [[ -f "$baseline_file" ]]; then
        grep -v "^[a-f0-9]* ${skill_name}$" "$baseline_file" > "$tmp" 2>/dev/null || : > "$tmp"
    else
        : > "$tmp"
    fi
    echo "$hash $skill_name" >> "$tmp"
    mv -f "$tmp" "$baseline_file"
}

UPSTREAM="$(resolve_upstream)"
LOCAL="$(resolve_local)"
BASELINE_FILE="$LOCAL/$BASELINE_FILE_NAME"

# Refuse if managed by install_aris_copilot.sh
if [[ "$MODE" == "project" ]]; then
    local_project="$(cd "$PROJECT_PATH" 2>/dev/null && pwd)"
    manifest="$local_project/.aris/installed-skills-copilot.txt"
    if [[ -f "$manifest" ]]; then
        die "this project uses symlink install (manifest: $manifest). Use: git pull && bash tools/install_aris_copilot.sh \"$local_project\" --reconcile"
    fi
fi

log ""
log "ARIS Copilot CLI Smart Update"
log "  Upstream:  $UPSTREAM"
log "  Local:     $LOCAL"
log "  Mode:      $MODE"
log ""

[[ -d "$LOCAL" ]] || die "local skill directory not found: $LOCAL (install skills first, or use --local)"

# ─── New-skill confirmation state (declined list + group catalog lookup) ──────
CATALOG_PATH="$REPO_ROOT/tools/skill-groups.tsv"
DECLINED_FILE="$LOCAL/.aris-declined.txt"

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

# Build diff report
UPDATED=()
NEW=()
CUSTOMIZED=()
UP_TO_DATE=0

for d in "$UPSTREAM"/*/; do
    [[ -d "$d" ]] || continue
    name="$(basename "$d")"

    # Skip Codex-specific packages
    if [[ "$name" =~ $SKIP_DIRS_PATTERN ]]; then
        continue
    fi

    # Must have SKILL.md or be shared-references
    if [[ ! -f "$d/SKILL.md" && "$name" != "shared-references" ]]; then
        continue
    fi

    local_dir="$LOCAL/$name"

    if [[ ! -e "$local_dir" ]]; then
        NEW+=("$name")
        continue
    fi

    # Check if local differs from upstream
    if [[ -d "$local_dir" ]]; then
        # Quick check: if directories are identical, skip
        if diff -rq "$d" "$local_dir" >/dev/null 2>&1; then
            UP_TO_DATE=$((UP_TO_DATE + 1))
            continue
        fi

        # Determine if local was customized using hash-based detection
        has_custom=false
        if [[ -f "$local_dir/SKILL.md" ]]; then
            local_hash="$(file_sha256 "$local_dir/SKILL.md")"
            baseline_hash="$(get_baseline_hash "$BASELINE_FILE" "$name")"

            if [[ -n "$baseline_hash" && -n "$local_hash" ]]; then
                # Baseline exists: compare local against recorded baseline
                if [[ "$local_hash" != "$baseline_hash" ]]; then
                    # Local SKILL.md was modified by user since last install/update
                    has_custom=true
                fi
            elif [[ -z "$baseline_hash" ]]; then
                # No baseline recorded (pre-existing copy install without baselines).
                # Fall back to comparing local vs upstream: if they differ and local
                # doesn't match upstream, assume customized (conservative).
                upstream_hash="$(file_sha256 "$d/SKILL.md")"
                if [[ -n "$local_hash" && "$local_hash" != "$upstream_hash" ]]; then
                    has_custom=true
                fi
            fi
        fi

        if $has_custom; then
            CUSTOMIZED+=("$name")
        else
            UPDATED+=("$name")
        fi
    fi
done

log "Summary:"
log "  Up-to-date:  $UP_TO_DATE"
log "  Updatable:   ${#UPDATED[@]}"
log "  New:         ${#NEW[@]}"
log "  Customized:  ${#CUSTOMIZED[@]} (skipped)"
log ""

if (( ${#CUSTOMIZED[@]} > 0 )); then
    log "Customized (will NOT update):"
    for name in "${CUSTOMIZED[@]}"; do
        log "  - $name"
    done
    log ""
fi

if (( ${#UPDATED[@]} > 0 )); then
    log "Will update:"
    for name in "${UPDATED[@]}"; do
        log "  ~ $name"
    done
    log ""
fi

# Pre-declined subset of NEW (informational only — the decision of what to
# install/skip/prompt is only made inside the --apply block below).
NEW_PREDECLINED=()
for name in "${NEW[@]:-}"; do
    [[ -n "$name" && "$name" != "shared-references" ]] || continue
    is_declined "$name" && NEW_PREDECLINED+=("$name")
done

if (( ${#NEW[@]} > 0 )); then
    log "New skills available (confirmed one-by-one on --apply, unless --add-new/--skip-new; ${#NEW_PREDECLINED[@]} previously declined):"
    for name in "${NEW[@]}"; do
        if [[ "$name" != "shared-references" ]] && is_declined "$name"; then
            log "  + $name (previously declined — stays skipped unless --add-new)"
        else
            log "  + $name"
        fi
    done
    log ""
fi

if (( ${#UPDATED[@]} == 0 && ${#NEW[@]} == 0 )); then
    log "Everything up to date."
    $APPLY && ensure_global_pointer
    exit 0
fi

if ! $APPLY; then
    log "Run with --apply to perform updates."
    exit 0
fi

# Apply updates
log "Applying updates..."

# bash 3.2 (stock macOS): "${ARR[@]}" on an EMPTY array trips `set -u`. Only one of
# UPDATED/NEW is guaranteed non-empty here (the line-236 early-exit needs BOTH empty),
# so each apply loop gets its own length guard.
if (( ${#UPDATED[@]} > 0 )); then
    for name in "${UPDATED[@]}"; do
        rm -rf "$LOCAL/$name"
        cp -r "$UPSTREAM/$name" "$LOCAL/$name"
        # Record new baseline hash
        if [[ -f "$LOCAL/$name/SKILL.md" ]]; then
            new_hash="$(file_sha256 "$LOCAL/$name/SKILL.md")"
            record_baseline "$BASELINE_FILE" "$name" "$new_hash"
        fi
        log "  ~ updated $name"
    done
fi

# ── New-skill three-state policy: interactive confirm / --add-new / --skip-new ──
# A skill already in .aris-declined.txt is never re-asked and never installed —
# not even by --add-new (only editing/clearing the declined file restores it).
# shared-references is support content, not a selectable skill: always synced.
TO_INSTALL_NEW=()
SKIPPED_NEW=()
JUST_DECLINED=()

if (( ${#NEW[@]} > 0 )); then
    for name in "${NEW[@]}"; do
        if [[ "$name" == "shared-references" ]]; then
            TO_INSTALL_NEW+=("$name")
            continue
        fi
        if is_declined "$name"; then
            continue
        fi
        case "$NEW_POLICY" in
            add)
                TO_INSTALL_NEW+=("$name")
                ;;
            skip)
                SKIPPED_NEW+=("$name")
                ;;
            *)
                if [[ -t 0 ]]; then
                    grp="$(catalog_group_of "$name")"
                    printf "  install new skill %-30s (group: %s) [y/N] " "$name" "$grp" >&2
                    read -r reply </dev/tty
                    if [[ "$reply" =~ ^[yY] ]]; then
                        TO_INSTALL_NEW+=("$name")
                    else
                        JUST_DECLINED+=("$name")
                    fi
                else
                    SKIPPED_NEW+=("$name")
                fi
                ;;
        esac
    done
fi

if (( ${#JUST_DECLINED[@]} > 0 )); then
    {
        [[ -f "$DECLINED_FILE" ]] && cat "$DECLINED_FILE"
        printf '%s\n' "${JUST_DECLINED[@]}"
    } | sort -u > "$DECLINED_FILE.tmp.$$" && mv -f "$DECLINED_FILE.tmp.$$" "$DECLINED_FILE"
fi

if (( ${#TO_INSTALL_NEW[@]} > 0 )); then
    for name in "${TO_INSTALL_NEW[@]}"; do
        cp -r "$UPSTREAM/$name" "$LOCAL/$name"
        # Record baseline hash for new installs
        if [[ -f "$LOCAL/$name/SKILL.md" ]]; then
            new_hash="$(file_sha256 "$LOCAL/$name/SKILL.md")"
            record_baseline "$BASELINE_FILE" "$name" "$new_hash"
        fi
        log "  + added $name"
    done
fi

log ""
log "Done. ${#UPDATED[@]} updated, ${#TO_INSTALL_NEW[@]} added."
log "Baselines recorded in: $BASELINE_FILE"

if (( ${#SKIPPED_NEW[@]} > 0 )); then
    log "  ${#SKIPPED_NEW[@]} new skill(s) skipped, not declined: ${SKIPPED_NEW[*]}"
    log "  Re-run with --add-new to install them (or re-run interactively on a TTY)."
fi
if (( ${#JUST_DECLINED[@]} > 0 )); then
    log "  Declined just now (recorded in $DECLINED_FILE, won't be asked again): ${JUST_DECLINED[*]}"
fi
if (( ${#NEW_PREDECLINED[@]} > 0 )); then
    log "  Previously declined, still skipped: ${#NEW_PREDECLINED[@]} (edit $DECLINED_FILE to reconsider)"
fi

ensure_global_pointer
