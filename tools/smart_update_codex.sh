#!/usr/bin/env bash
# smart_update_codex.sh -- update copied ARIS Codex skills safely.
#
# Default upstream:
#   repo/skills/skills-codex
#
# Optional overlays:
#   --overlay claude-review
#   --overlay gemini-review
#
# Default local targets:
#   global:  ~/.codex/skills
#   project: <project>/.agents/skills
#
# This tool is for copied installs only. If the target is managed by
# install_aris_codex.sh (manifest + symlinks), it refuses and points to:
#   git pull + install_aris_codex.sh --reconcile

set -euo pipefail

APPLY=false
MODE="global"
PROJECT_PATH=""
CUSTOM_UPSTREAM=""
CUSTOM_LOCAL=""
HAS_CUSTOM_UPSTREAM=false
HAS_CUSTOM_LOCAL=false
OVERLAYS=()

usage() { sed -n '2,24p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
        --project) MODE="project"; PROJECT_PATH="${2:?--project requires path}"; shift 2 ;;
        --upstream) MODE="explicit"; HAS_CUSTOM_UPSTREAM=true; CUSTOM_UPSTREAM="${2:?--upstream requires path}"; shift 2 ;;
        --local) MODE="explicit"; HAS_CUSTOM_LOCAL=true; CUSTOM_LOCAL="${2:?--local requires path}"; shift 2 ;;
        --overlay) OVERLAYS+=("${2:?--overlay requires claude-review or gemini-review}"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --*) echo "Unknown option: $1" >&2; exit 2 ;;
        *) echo "Unexpected positional argument: $1" >&2; exit 2 ;;
    esac
done

log() { echo "$@"; }
die() { echo "error: $*" >&2; exit 1; }
warn() { echo "warning: $*" >&2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_UPSTREAM="$REPO_ROOT/skills/skills-codex"
DEFAULT_GLOBAL_LOCAL="$HOME/.codex/skills"

for overlay in "${OVERLAYS[@]}"; do
    case "$overlay" in
        claude-review|gemini-review) ;;
        *) die "--overlay must be claude-review or gemini-review (got: $overlay)" ;;
    esac
done

case "$MODE" in
    explicit)
        $HAS_CUSTOM_LOCAL || die "--local must be provided when using --upstream"
        if $HAS_CUSTOM_UPSTREAM; then
            [[ ${#OVERLAYS[@]} -eq 0 ]] || die "--overlay is only supported with repo-default upstream"
            UPSTREAM_DIR="$CUSTOM_UPSTREAM"
        else
            UPSTREAM_DIR="$BASE_UPSTREAM"
        fi
        LOCAL_DIR="$CUSTOM_LOCAL"
        SCOPE="local:$CUSTOM_LOCAL"
        PROJECT_ROOT=""
        ;;
    project)
        [[ -n "$PROJECT_PATH" ]] || die "--project requires a path"
        PROJECT_ROOT="$(cd "$PROJECT_PATH" && pwd)"
        UPSTREAM_DIR="$BASE_UPSTREAM"
        LOCAL_DIR="$PROJECT_ROOT/.agents/skills"
        SCOPE="project:$PROJECT_ROOT"
        ;;
    *)
        PROJECT_ROOT=""
        UPSTREAM_DIR="$BASE_UPSTREAM"
        LOCAL_DIR="$DEFAULT_GLOBAL_LOCAL"
        SCOPE="global"
        ;;
esac

[[ -d "$UPSTREAM_DIR" ]] || die "upstream directory not found: $UPSTREAM_DIR"
[[ -d "$LOCAL_DIR" ]] || die "local directory not found: $LOCAL_DIR"

MANAGED_MANIFEST=""
if [[ -n "$PROJECT_ROOT" ]]; then
    MANAGED_MANIFEST="$PROJECT_ROOT/.aris/installed-skills-codex.txt"
fi
if [[ -n "$MANAGED_MANIFEST" && -f "$MANAGED_MANIFEST" ]]; then
    die "target project is managed by install_aris_codex.sh. Use: git pull && bash $REPO_ROOT/tools/install_aris_codex.sh \"$PROJECT_ROOT\" --reconcile"
fi
if [[ -L "$LOCAL_DIR" ]]; then
    die "local skill directory is a symlink. Use: git pull && bash $REPO_ROOT/tools/install_aris_codex.sh \"${PROJECT_ROOT:-<project>}\" --reconcile"
fi
while IFS= read -r link_entry; do
    link_name="$(basename "$link_entry")"
    if [[ "$link_name" == "shared-references" || -d "$UPSTREAM_DIR/$link_name" ]]; then
        die "local skill directory contains symlink-managed ARIS entry '$link_name'. Use: git pull && bash $REPO_ROOT/tools/install_aris_codex.sh \"${PROJECT_ROOT:-<project>}\" --reconcile"
    fi
    for overlay in "${OVERLAYS[@]}"; do
        if [[ -d "$REPO_ROOT/skills/skills-codex-$overlay/$link_name" ]]; then
            die "local skill directory contains symlink-managed ARIS overlay entry '$link_name'. Use: git pull && bash $REPO_ROOT/tools/install_aris_codex.sh \"${PROJECT_ROOT:-<project>}\" --reconcile"
        fi
    done
done < <(find "$LOCAL_DIR" -mindepth 1 -maxdepth 1 -type l)

TMP_ROOT=""
MERGED_UPSTREAM="$UPSTREAM_DIR"
cleanup() {
    if [[ -n "$TMP_ROOT" ]]; then
        rm -rf "$TMP_ROOT"
    fi
    return 0
}
trap cleanup EXIT INT TERM

if [[ ${#OVERLAYS[@]} -gt 0 ]]; then
    TMP_ROOT="$(mktemp -d /tmp/aris-codex-update.XXXXXX)"
    MERGED_UPSTREAM="$TMP_ROOT/upstream"
    mkdir -p "$MERGED_UPSTREAM"
    cp -a "$BASE_UPSTREAM/." "$MERGED_UPSTREAM/"
    for overlay in "${OVERLAYS[@]}"; do
        cp -a "$REPO_ROOT/skills/skills-codex-$overlay/." "$MERGED_UPSTREAM/"
    done
fi

UPSTREAM_DIR="$MERGED_UPSTREAM"

list_entries() {
    local root="$1"
    local entry name
    for entry in "$root"/*; do
        [[ -e "$entry" ]] || continue
        [[ -d "$entry" ]] || continue
        name="$(basename "$entry")"
        if [[ "$name" == "shared-references" || -f "$entry/SKILL.md" ]]; then
            printf "%s\n" "$name"
        fi
    done | sort
}

NEW=0
IDENTICAL=0
SAFE_UPDATE=0
NEEDS_MERGE=0
LOCAL_ONLY=0

declare -a NEW_SKILLS=()
declare -a IDENTICAL_SKILLS=()
declare -a SAFE_SKILLS=()
declare -a MERGE_SKILLS=()
declare -a LOCAL_SKILLS=()
declare -a UPSTREAM_NAMES=()
declare -a NEW_SHARED_REFERENCES=()

while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    UPSTREAM_NAMES+=("$name")
    upstream_entry="$UPSTREAM_DIR/$name"
    local_entry="$LOCAL_DIR/$name"
    if [[ ! -d "$local_entry" ]]; then
        NEW=$((NEW + 1))
        NEW_SKILLS+=("$name")
        continue
    fi
    if diff -qr "$upstream_entry" "$local_entry" >/dev/null 2>&1; then
        IDENTICAL=$((IDENTICAL + 1))
        IDENTICAL_SKILLS+=("$name")
        continue
    fi
    if [[ ${#OVERLAYS[@]} -gt 0 && -d "$BASE_UPSTREAM/$name" ]] && diff -qr "$BASE_UPSTREAM/$name" "$local_entry" >/dev/null 2>&1; then
        SAFE_UPDATE=$((SAFE_UPDATE + 1))
        SAFE_SKILLS+=("$name")
        continue
    fi
    # Unlike managed installs, copied installs have no manifest/baseline telling us
    # whether a diff is upstream-only or includes local edits. Be conservative:
    # any non-identical local entry requires manual merge instead of replacement.
    NEEDS_MERGE=$((NEEDS_MERGE + 1))
    MERGE_SKILLS+=("$name")
done < <(list_entries "$UPSTREAM_DIR")

while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    found=false
    for upstream_name in "${UPSTREAM_NAMES[@]}"; do
        if [[ "$upstream_name" == "$name" ]]; then
            found=true
            break
        fi
    done
    if ! $found; then
        LOCAL_ONLY=$((LOCAL_ONLY + 1))
        LOCAL_SKILLS+=("$name")
    fi
done < <(list_entries "$LOCAL_DIR")

if [[ -d "$UPSTREAM_DIR/shared-references" ]]; then
    while IFS= read -r ref_file; do
        rel_ref="${ref_file#"$UPSTREAM_DIR/shared-references/"}"
        local_ref="$LOCAL_DIR/shared-references/$rel_ref"
        if [[ ! -e "$local_ref" ]]; then
            NEW_SHARED_REFERENCES+=("$rel_ref")
        fi
    done < <(find "$UPSTREAM_DIR/shared-references" -type f | sort)
fi

log "ARIS Codex Smart Update"
log "  Scope:    $SCOPE"
log "  Upstream: $UPSTREAM_DIR"
log "  Local:    $LOCAL_DIR"
if [[ ${#OVERLAYS[@]} -gt 0 ]]; then
    log "  Overlays: ${OVERLAYS[*]}"
fi
log ""

log "Identical: $IDENTICAL"
for s in "${IDENTICAL_SKILLS[@]:-}"; do [[ -n "$s" ]] && log "  $s"; done
log ""
log "New: $NEW"
for s in "${NEW_SKILLS[@]:-}"; do [[ -n "$s" ]] && log "  $s"; done
log ""
log "Safe update: $SAFE_UPDATE"
for s in "${SAFE_SKILLS[@]:-}"; do [[ -n "$s" ]] && log "  $s"; done
log ""
log "Needs merge: $NEEDS_MERGE"
for s in "${MERGE_SKILLS[@]:-}"; do [[ -n "$s" ]] && log "  $s"; done
log ""
log "Local only: $LOCAL_ONLY"
for s in "${LOCAL_SKILLS[@]:-}"; do [[ -n "$s" ]] && log "  $s"; done
log ""
log "New shared references: ${#NEW_SHARED_REFERENCES[@]}"
for s in "${NEW_SHARED_REFERENCES[@]:-}"; do [[ -n "$s" ]] && log "  shared-references/$s"; done
log ""

if ! $APPLY; then
    log "Dry-run only. Re-run with --apply to copy new entries, new shared references, and replace safe-update entries."
    exit 0
fi

for name in "${NEW_SKILLS[@]:-}"; do
    [[ -n "$name" ]] || continue
    mkdir -p "$LOCAL_DIR"
    cp -a "$UPSTREAM_DIR/$name" "$LOCAL_DIR/$name"
    log "  + added $name"
done

for name in "${SAFE_SKILLS[@]:-}"; do
    [[ -n "$name" ]] || continue
    rm -rf "$LOCAL_DIR/$name"
    cp -a "$UPSTREAM_DIR/$name" "$LOCAL_DIR/$name"
    log "  ↻ updated $name"
done

for rel_ref in "${NEW_SHARED_REFERENCES[@]:-}"; do
    [[ -n "$rel_ref" ]] || continue
    mkdir -p "$(dirname "$LOCAL_DIR/shared-references/$rel_ref")"
    cp -a "$UPSTREAM_DIR/shared-references/$rel_ref" "$LOCAL_DIR/shared-references/$rel_ref"
    log "  + added shared-references/$rel_ref"
done

validate_shared_references() {
    local root="$1"
    local failures=0
    local name skill_file ref
    for name in "${UPSTREAM_NAMES[@]:-}"; do
        [[ -n "$name" && "$name" != "shared-references" ]] || continue
        skill_file="$root/$name/SKILL.md"
        [[ -f "$skill_file" ]] || continue
        while IFS= read -r ref; do
            [[ -n "$ref" ]] || continue
            if [[ ! -f "$root/shared-references/$ref" ]]; then
                warn "missing shared reference: $(basename "$(dirname "$skill_file")") -> shared-references/$ref"
                failures=$((failures + 1))
            fi
        done < <(grep -Eo '\.\./shared-references/[A-Za-z0-9._-]+\.md' "$skill_file" 2>/dev/null | sed 's|../shared-references/||' | sort -u)
    done
    return "$failures"
}

log ""
log "Apply complete."
if (( NEEDS_MERGE > 0 )); then
    warn "$NEEDS_MERGE entries still need manual merge"
fi
if ! validate_shared_references "$LOCAL_DIR"; then
    die "copied install has missing shared references after update; merge or copy the reported files before using affected skills"
fi
