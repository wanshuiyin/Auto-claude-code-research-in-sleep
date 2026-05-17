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

set -euo pipefail

APPLY=false
MODE="global"
PROJECT_PATH=""
CUSTOM_UPSTREAM=""
CUSTOM_LOCAL=""
HAS_CUSTOM_UPSTREAM=false
HAS_CUSTOM_LOCAL=false

usage() { sed -n '2,20p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
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

if (( ${#NEW[@]} > 0 )); then
    log "New skills available:"
    for name in "${NEW[@]}"; do
        log "  + $name"
    done
    log ""
fi

if (( ${#UPDATED[@]} == 0 && ${#NEW[@]} == 0 )); then
    log "Everything up to date."
    exit 0
fi

if ! $APPLY; then
    log "Run with --apply to perform updates."
    exit 0
fi

# Apply updates
log "Applying updates..."

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

for name in "${NEW[@]}"; do
    cp -r "$UPSTREAM/$name" "$LOCAL/$name"
    # Record baseline hash for new installs
    if [[ -f "$LOCAL/$name/SKILL.md" ]]; then
        new_hash="$(file_sha256 "$LOCAL/$name/SKILL.md")"
        record_baseline "$BASELINE_FILE" "$name" "$new_hash"
    fi
    log "  + added $name"
done

log ""
log "Done. ${#UPDATED[@]} updated, ${#NEW[@]} added."
log "Baselines recorded in: $BASELINE_FILE"
