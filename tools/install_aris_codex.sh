#!/usr/bin/env bash
# install_aris_codex.sh -- Project-local ARIS Codex skill installation.
#
# This installer manages a flat Codex project layout:
#   <project>/.agents/skills/<skill-name> -> <aris-repo>/skills/<package>/<skill-name>
#
# Managed entries are tracked in:
#   <project>/.aris/installed-skills-codex.txt
#
# Default package set:
#   - skills/skills-codex
#
# Optional overlays:
#   --with-claude-review-overlay
#   --with-gemini-review-overlay
#
# Usage:
#   bash tools/install_aris_codex.sh [project_path] [options]
#
# Actions (mutually exclusive, default: auto):
#   default          install if no manifest, else reconcile
#   --reconcile      explicit reconcile; refuse if no manifest
#   --uninstall      remove only entries in manifest; delete manifest
#
# Options:
#   --aris-repo PATH                 override repo discovery
#   --with-claude-review-overlay     install skills-codex-claude-review on top
#   --with-gemini-review-overlay     install skills-codex-gemini-review on top
#   --dry-run                        show plan, no writes
#   --quiet                          no prompts
#   --no-doc                         skip AGENTS.md managed block update
#   --replace-link NAME              replace a conflicting symlink for NAME
#   --clear-stale-lock               clear a stale installer lock

set -euo pipefail

MANIFEST_VERSION="1"
MANIFEST_NAME="installed-skills-codex.txt"
MANIFEST_PREV_NAME="installed-skills-codex.txt.prev"
ARIS_DIR_NAME=".aris"
LOCK_DIR_NAME=".install-codex.lock.d"
SKILLS_REL=".agents/skills"
DOC_FILE_NAME="AGENTS.md"
BLOCK_BEGIN="<!-- ARIS-CODEX:BEGIN -->"
BLOCK_END="<!-- ARIS-CODEX:END -->"
SAFE_NAME_REGEX='^[A-Za-z0-9][A-Za-z0-9._-]*$'
BASE_PACKAGE="skills-codex"

PROJECT_PATH=""
ARIS_REPO_OVERRIDE=""
ACTION="auto"
DRY_RUN=false
QUIET=false
NO_DOC=false
CLEAR_STALE_LOCK=false
WITH_CLAUDE_OVERLAY=false
WITH_GEMINI_OVERLAY=false
REPLACE_LINK_NAMES=()

usage() { sed -n '2,34p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --reconcile) ACTION="reconcile"; shift ;;
        --uninstall) ACTION="uninstall"; shift ;;
        --aris-repo) ARIS_REPO_OVERRIDE="${2:?--aris-repo requires path}"; shift 2 ;;
        --with-claude-review-overlay) WITH_CLAUDE_OVERLAY=true; shift ;;
        --with-gemini-review-overlay) WITH_GEMINI_OVERLAY=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --quiet) QUIET=true; shift ;;
        --no-doc) NO_DOC=true; shift ;;
        --replace-link) REPLACE_LINK_NAMES+=("${2:?--replace-link requires NAME}"); shift 2 ;;
        --clear-stale-lock) CLEAR_STALE_LOCK=true; shift ;;
        -h|--help) usage; exit 0 ;;
        --*) echo "Unknown option: $1" >&2; exit 2 ;;
        *)
            if [[ -z "$PROJECT_PATH" ]]; then
                PROJECT_PATH="$1"
            else
                echo "Error: unexpected positional argument: $1" >&2
                exit 2
            fi
            shift
            ;;
    esac
done

log() { $QUIET && return 0; echo "$@"; }
warn() { echo "warning: $*" >&2; }
die() { echo "error: $*" >&2; exit 1; }
prompt() { $QUIET && return 0; printf "%s " "$1" >&2; read -r REPLY; [[ "$REPLY" =~ ^[Yy]$ ]]; }
abs_path() { ( cd "$1" 2>/dev/null && pwd ) || return 1; }
is_safe_name() { [[ "$1" =~ $SAFE_NAME_REGEX ]]; }
is_symlink() { [[ -L "$1" ]]; }
name_in_replace_allowlist() {
    local needle="$1"
    local item
    for item in "${REPLACE_LINK_NAMES[@]}"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

read_link_target() {
    if command -v greadlink >/dev/null 2>&1; then greadlink "$1"
    else readlink "$1"; fi
}

canonicalize() {
    if command -v greadlink >/dev/null 2>&1; then greadlink -f "$1" 2>/dev/null || true
    elif readlink -f "$1" 2>/dev/null; then :
    else
        local d f
        if [[ -d "$1" ]]; then
            ( cd "$1" && pwd )
        else
            d="$(dirname "$1")"
            f="$(basename "$1")"
            ( cd "$d" 2>/dev/null && echo "$(pwd)/$f" )
        fi
    fi
}

resolve_aris_repo() {
    local p
    if [[ -n "$ARIS_REPO_OVERRIDE" ]]; then
        p="$(abs_path "$ARIS_REPO_OVERRIDE")" || die "--aris-repo path not found: $ARIS_REPO_OVERRIDE"
    else
        local script_dir parent guess
        script_dir="$(cd "$(dirname "$0")" && pwd)"
        parent="$(cd "$script_dir/.." && pwd)"
        if [[ -d "$parent/skills/$BASE_PACKAGE" ]]; then
            p="$parent"
        elif [[ -n "${ARIS_REPO:-}" && -d "$ARIS_REPO/skills/$BASE_PACKAGE" ]]; then
            p="$(abs_path "$ARIS_REPO")"
        else
            for guess in \
                "$HOME/Desktop/Auto-claude-code-research-in-sleep" \
                "$HOME/Auto-claude-code-research-in-sleep" \
                "$HOME/aris_repo" \
                "$HOME/.codex/Auto-claude-code-research-in-sleep"; do
                if [[ -d "$guess/skills/$BASE_PACKAGE" ]]; then
                    p="$(abs_path "$guess")"
                    break
                fi
            done
        fi
    fi
    [[ -n "${p:-}" ]] || die "cannot find ARIS repo with skills/$BASE_PACKAGE. Use --aris-repo PATH."
    [[ -d "$p/skills/$BASE_PACKAGE" ]] || die "repo missing skills/$BASE_PACKAGE: $p"
    echo "$p"
}

selected_packages() {
    local packages=("$BASE_PACKAGE")
    $WITH_CLAUDE_OVERLAY && packages+=("skills-codex-claude-review")
    $WITH_GEMINI_OVERLAY && packages+=("skills-codex-gemini-review")
    printf "%s\n" "${packages[@]}"
}

build_upstream_inventory() {
    local repo="$1" out="$2"
    local package package_dir d name kind source_rel tmp
    tmp="$(mktemp -t aris-codex-upstream-raw.XXXX)"
    : > "$out"
    : > "$tmp"

    while IFS= read -r package; do
        [[ -z "$package" ]] && continue
        package_dir="$repo/skills/$package"
        [[ -d "$package_dir" ]] || die "selected package missing: $package_dir"
        for d in "$package_dir"/*; do
            [[ -d "$d" ]] || continue
            name="$(basename "$d")"
            is_safe_name "$name" || { warn "skipping unsafe upstream name: $name"; continue; }
            if [[ "$name" == "shared-references" ]]; then
                kind="support"
            elif [[ -f "$d/SKILL.md" ]]; then
                kind="skill"
            else
                continue
            fi
            source_rel="skills/$package/$name"
            printf "%s|%s|%s\n" "$kind" "$name" "$source_rel" >> "$tmp"
        done
    done < <(selected_packages)

    if [[ ! -s "$tmp" ]]; then
        rm -f "$tmp"
        die "upstream inventory empty"
    fi

    # Keep the last entry for duplicate names so overlays override the base
    # package, then sort by skill/support name for deterministic plans.
    awk -F'|' '{row[$2]=$0} END {for (name in row) print row[name]}' "$tmp" | sort -t'|' -k2,2 > "$out"
    rm -f "$tmp"
}

load_manifest() {
    local path="$1" out="$2"
    : > "$out"
    [[ -f "$path" ]] || return 0
    local ver
    ver="$(awk -F'\t' '$1=="version"{print $2}' "$path" | head -1)"
    [[ "$ver" == "$MANIFEST_VERSION" ]] || die "manifest version mismatch (got: ${ver:-none}, expected: $MANIFEST_VERSION)"
    awk -F'\t' '
        BEGIN { in_body=0 }
        /^kind\tname\tsource_rel\ttarget_rel\tmode$/ { in_body=1; next }
        in_body && NF==5 { print }
    ' "$path" > "$out"
}

manifest_lookup_target() { awk -F'\t' -v n="$2" '$2==n {print $4; exit}' "$1"; }
manifest_lookup_source() { awk -F'\t' -v n="$2" '$2==n {print $3; exit}' "$1"; }
manifest_repo_root() { awk -F'\t' '$1=="repo_root" {print $2; exit}' "$1"; }

PROJECT_PATH="${PROJECT_PATH:-$(pwd)}"
[[ -d "$PROJECT_PATH" ]] || die "project path does not exist: $PROJECT_PATH"
PROJECT_PATH="$(abs_path "$PROJECT_PATH")"
ARIS_REPO="$(resolve_aris_repo)"
PROJECT_SKILLS_DIR="$PROJECT_PATH/$SKILLS_REL"
PROJECT_ARIS_DIR="$PROJECT_PATH/$ARIS_DIR_NAME"
MANIFEST_PATH="$PROJECT_ARIS_DIR/$MANIFEST_NAME"
MANIFEST_PREV="$PROJECT_ARIS_DIR/$MANIFEST_PREV_NAME"
LOCK_DIR="$PROJECT_ARIS_DIR/$LOCK_DIR_NAME"
DOC_FILE="$PROJECT_PATH/$DOC_FILE_NAME"
LEGACY_NESTED="$PROJECT_PATH/.agents/skills/aris"

check_no_symlinked_parents() {
    local p
    for p in "$PROJECT_ARIS_DIR" "$PROJECT_PATH/.agents" "$PROJECT_SKILLS_DIR"; do
        if is_symlink "$p"; then
            die "$p is a symlink; refusing to mutate symlinked parent directories"
        fi
    done
}

check_legacy_nested_install() {
    if [[ -e "$LEGACY_NESTED" || -L "$LEGACY_NESTED" ]]; then
        die "legacy nested Codex install detected at $LEGACY_NESTED. Remove or migrate it before using the flat .agents/skills/<name> layout."
    fi
}

write_lock_metadata() {
    cat > "$LOCK_DIR/owner.json" <<EOF
{"host":"$(hostname)","pid":$$,"started_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","tool":"install_aris_codex.sh"}
EOF
    echo "$$" > "$LOCK_DIR/owner.pid"
    echo "$(hostname)" > "$LOCK_DIR/owner.host"
}

release_lock() {
    [[ -d "$LOCK_DIR" ]] || return 0
    if [[ -f "$LOCK_DIR/owner.pid" && -f "$LOCK_DIR/owner.host" ]]; then
        local pid host
        pid="$(cat "$LOCK_DIR/owner.pid" 2>/dev/null || echo "")"
        host="$(cat "$LOCK_DIR/owner.host" 2>/dev/null || echo "")"
        if [[ "$pid" == "$$" && "$host" == "$(hostname)" ]]; then
            rm -rf "$LOCK_DIR"
        fi
    fi
}

acquire_lock() {
    mkdir -p "$PROJECT_ARIS_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        write_lock_metadata
        trap release_lock EXIT INT TERM
        return 0
    fi
    if $CLEAR_STALE_LOCK; then
        warn "removing stale lock: $LOCK_DIR"
        rm -rf "$LOCK_DIR"
        mkdir "$LOCK_DIR" || die "cannot acquire lock after stale clear"
        write_lock_metadata
        trap release_lock EXIT INT TERM
        return 0
    fi
    local owner=""
    [[ -f "$LOCK_DIR/owner.json" ]] && owner="$(cat "$LOCK_DIR/owner.json")"
    die "another install_aris_codex.sh appears to be running (lock: $LOCK_DIR, owner: $owner)"
}

compute_plan() {
    local upstream_file="$1" manifest_data="$2" out="$3"
    local kind name source_rel target_path expected_target current_target in_manifest
    : > "$out"

    while IFS='|' read -r kind name source_rel; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_SKILLS_DIR/$name"
        expected_target="$ARIS_REPO/$source_rel"
        in_manifest=false
        [[ -n "$(manifest_lookup_target "$manifest_data" "$name")" ]] && in_manifest=true

        if [[ -L "$target_path" ]]; then
            current_target="$(read_link_target "$target_path")"
            [[ "$current_target" != /* ]] && current_target="$(canonicalize "$(dirname "$target_path")/$current_target")"
            if [[ "$current_target" == "$expected_target" ]]; then
                if $in_manifest; then
                    printf "REUSE|%s|%s|%s|\n" "$kind" "$name" "$source_rel" >> "$out"
                else
                    printf "ADOPT|%s|%s|%s|\n" "$kind" "$name" "$source_rel" >> "$out"
                fi
            elif $in_manifest || name_in_replace_allowlist "$name"; then
                printf "UPDATE_TARGET|%s|%s|%s|%s\n" "$kind" "$name" "$source_rel" "$current_target" >> "$out"
            else
                printf "CONFLICT|%s|%s|%s|symlink_to:%s\n" "$kind" "$name" "$source_rel" "$current_target" >> "$out"
            fi
        elif [[ -e "$target_path" ]]; then
            printf "CONFLICT|%s|%s|%s|real_path\n" "$kind" "$name" "$source_rel" >> "$out"
        else
            printf "CREATE|%s|%s|%s|\n" "$kind" "$name" "$source_rel" >> "$out"
        fi
    done < "$upstream_file"

    local recorded_repo_root
    recorded_repo_root="$(manifest_repo_root "$MANIFEST_PATH" 2>/dev/null || true)"
    local mkind mname msource mtarget mmode
    while IFS=$'\t' read -r mkind mname msource mtarget mmode; do
        [[ -z "$mname" ]] && continue
        if awk -F'|' -v n="$mname" '$2==n {found=1} END{exit found?0:1}' "$upstream_file"; then
            continue
        fi
        [[ -n "$recorded_repo_root" ]] || die "manifest missing repo_root: $MANIFEST_PATH"
        printf "REMOVE|%s|%s|%s|%s/%s\n" "$mkind" "$mname" "$msource" "$recorded_repo_root" "$msource" >> "$out"
    done < "$manifest_data"
}

print_plan() {
    local plan="$1"
    local action
    log ""
    log "Plan summary:"
    for action in CREATE ADOPT UPDATE_TARGET REUSE REMOVE CONFLICT; do
        log "  $action: $(grep -c "^$action|" "$plan" || true)"
    done
    if grep -q '^CONFLICT|' "$plan"; then
        log ""
        log "Conflicts:"
        while IFS='|' read -r _ kind name _source extra; do
            log "  - $name ($kind): $extra"
        done < <(grep '^CONFLICT|' "$plan")
    fi
}

write_manifest_tmp() {
    local plan="$1" out="$2"
    {
        printf "version\t%s\n" "$MANIFEST_VERSION"
        printf "repo_root\t%s\n" "$ARIS_REPO"
        printf "project_root\t%s\n" "$PROJECT_PATH"
        printf "generated\t%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf "packages\t%s\n" "$(selected_packages | paste -sd, -)"
        printf "kind\tname\tsource_rel\ttarget_rel\tmode\n"
        awk -F'|' '$1=="REUSE"||$1=="ADOPT"||$1=="CREATE"||$1=="UPDATE_TARGET"{print}' "$plan" \
        | while IFS='|' read -r _ kind name source_rel _extra; do
            printf "%s\t%s\t%s\t%s/%s\tsymlink\n" "$kind" "$name" "$source_rel" "$SKILLS_REL" "$name"
        done
    } > "$out"
}

apply_plan() {
    local plan="$1"
    local action kind name source_rel extra target_path expected_target current_target
    mkdir -p "$PROJECT_SKILLS_DIR"
    while IFS='|' read -r action kind name source_rel extra; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_SKILLS_DIR/$name"
        expected_target="$ARIS_REPO/$source_rel"
        case "$action" in
            REUSE|ADOPT)
                :
                ;;
            CREATE)
                if [[ -e "$target_path" || -L "$target_path" ]]; then
                    die "path appeared during install: $target_path"
                fi
                if $DRY_RUN; then
                    log "  (dry-run) ln -s $expected_target $target_path"
                else
                    ln -s "$expected_target" "$target_path"
                    log "  + $name"
                fi
                ;;
            UPDATE_TARGET)
                if [[ -L "$target_path" ]]; then
                    current_target="$(read_link_target "$target_path")"
                    [[ "$current_target" != /* ]] && current_target="$(canonicalize "$(dirname "$target_path")/$current_target")"
                else
                    current_target=""
                fi
                if [[ "$current_target" != "$extra" ]]; then
                    die "symlink target changed during install for $name (expected: $extra, got: ${current_target:-missing})"
                fi
                if $DRY_RUN; then
                    log "  (dry-run) relink $target_path -> $expected_target"
                else
                    rm -f "$target_path"
                    ln -s "$expected_target" "$target_path"
                    log "  ↻ $name"
                fi
                ;;
            REMOVE)
                [[ -n "$extra" ]] || die "remove action missing recorded target for $name"
                if [[ -L "$target_path" ]]; then
                    current_target="$(read_link_target "$target_path")"
                    [[ "$current_target" != /* ]] && current_target="$(canonicalize "$(dirname "$target_path")/$current_target")"
                    if [[ "$current_target" == "$extra" ]]; then
                        if $DRY_RUN; then
                            log "  (dry-run) rm $target_path"
                        else
                            rm -f "$target_path"
                            log "  - $name"
                        fi
                    else
                        die "refusing to remove $name; target changed during reconcile (expected: $extra, got: $current_target)"
                    fi
                elif [[ -e "$target_path" ]]; then
                    die "refusing to remove $name; target path is no longer a symlink"
                else
                    log "  - $name (already removed)"
                fi
                ;;
            CONFLICT)
                die "conflict reached apply phase for $name"
                ;;
        esac
    done < "$plan"
}

commit_manifest() {
    local manifest_tmp="$1"
    if $DRY_RUN; then
        log "  (dry-run) would commit manifest"
        return 0
    fi
    mkdir -p "$PROJECT_ARIS_DIR"
    if [[ -f "$MANIFEST_PATH" ]]; then
        cp -p "$MANIFEST_PATH" "$MANIFEST_PREV.tmp"
        mv -f "$MANIFEST_PREV.tmp" "$MANIFEST_PREV"
    fi
    mv -f "$manifest_tmp" "$MANIFEST_PATH"
}

update_agents_doc() {
    local installed_names_file="$1"
    $NO_DOC && return 0
    local original=""
    [[ -f "$DOC_FILE" ]] && original="$(cat "$DOC_FILE")"
    local count packages_csv new_block new_content tmp current
    count="$(wc -l < "$installed_names_file" | tr -d ' ')"
    packages_csv="$(selected_packages | paste -sd, -)"
    local repo_lookup_cmd
    repo_lookup_cmd="ARIS_REPO=\$(awk -F'\\t' '\$1==\"repo_root\"{print \$2; exit}' \"$PROJECT_PATH/$ARIS_DIR_NAME/$MANIFEST_NAME\")"
    new_block="$BLOCK_BEGIN
## ARIS Codex Skill Scope
ARIS Codex packages installed in this project: $packages_csv
Managed entries: $count
Manifest: \`$ARIS_DIR_NAME/$MANIFEST_NAME\`
ARIS repo root: \`$ARIS_REPO\`
Project skill path: \`$SKILLS_REL/<skill-name>\`
For ARIS Codex workflows, prefer the project-local skills under \`$SKILLS_REL/\`.
When a skill needs ARIS helper scripts, resolve the repo root from the manifest or set it explicitly:
\`$repo_lookup_cmd\`
Do not edit or delete symlinked skills in place; update upstream or rerun:
\`bash $ARIS_REPO/tools/install_aris_codex.sh \"$PROJECT_PATH\" --reconcile\`
For copied Codex installs, use:
\`bash $ARIS_REPO/tools/smart_update_codex.sh --project \"$PROJECT_PATH\"\`
$BLOCK_END"

    if printf '%s' "$original" | grep -qF "$BLOCK_BEGIN"; then
        new_content="$(python3 - "$DOC_FILE" "$BLOCK_BEGIN" "$BLOCK_END" "$new_block" <<'PYEOF'
import pathlib
import re
import sys

path, begin, end, body = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
text = pathlib.Path(path).read_text() if pathlib.Path(path).exists() else ""
pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
matches = pattern.findall(text)
if len(matches) > 1:
    sys.stderr.write("ARIS-CODEX:WARN multiple managed blocks found; skipping update\n")
    sys.stdout.write(text)
else:
    sys.stdout.write(pattern.sub(body, text))
PYEOF
        )" || { warn "AGENTS.md update failed; continuing"; return 0; }
    else
        new_content="$original"
        [[ -n "$new_content" && "${new_content: -1}" != $'\n' ]] && new_content="${new_content}"$'\n'
        new_content="${new_content}${new_block}"$'\n'
    fi

    if $DRY_RUN; then
        log "  (dry-run) would update AGENTS.md managed block"
        return 0
    fi

    tmp="$DOC_FILE.aris-codex-tmp.$$"
    printf '%s' "$new_content" > "$tmp"
    current=""
    [[ -f "$DOC_FILE" ]] && current="$(cat "$DOC_FILE")"
    if [[ "$current" != "$original" ]]; then
        rm -f "$tmp"
        warn "AGENTS.md changed during install; skipping managed block update"
        return 0
    fi
    mv -f "$tmp" "$DOC_FILE"
    log "  ✓ updated AGENTS.md"
}

remove_agents_doc_block() {
    $NO_DOC && return 0
    [[ -f "$DOC_FILE" ]] || return 0

    local original new_content tmp current
    original="$(cat "$DOC_FILE")"
    if ! printf '%s' "$original" | grep -qF "$BLOCK_BEGIN"; then
        return 0
    fi

    new_content="$(python3 - "$DOC_FILE" "$BLOCK_BEGIN" "$BLOCK_END" <<'PYEOF'
import pathlib
import re
import sys

path, begin, end = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(path).read_text()
pattern = re.compile(r"\n?" + re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
matches = pattern.findall(text)
if len(matches) > 1:
    sys.stderr.write("ARIS-CODEX:WARN multiple managed blocks found; skipping removal\n")
    sys.stdout.write(text)
else:
    updated = pattern.sub("\n", text)
    sys.stdout.write(updated.lstrip("\n"))
PYEOF
    )" || { warn "AGENTS.md managed block removal failed; continuing"; return 0; }

    if $DRY_RUN; then
        log "  (dry-run) would remove AGENTS.md managed block"
        return 0
    fi

    tmp="$DOC_FILE.aris-codex-tmp.$$"
    printf '%s' "$new_content" > "$tmp"
    current="$(cat "$DOC_FILE")"
    if [[ "$current" != "$original" ]]; then
        rm -f "$tmp"
        warn "AGENTS.md changed during uninstall; skipping managed block removal"
        return 0
    fi
    mv -f "$tmp" "$DOC_FILE"
    log "  ✓ removed AGENTS.md managed block"
}

do_uninstall() {
    [[ -f "$MANIFEST_PATH" ]] || die "no manifest at $MANIFEST_PATH; nothing to uninstall"
    local manifest_data
    manifest_data="$(mktemp -t aris-codex-manifest.XXXX)"
    load_manifest "$MANIFEST_PATH" "$manifest_data"
    log ""
    log "Uninstall plan:"
    while IFS=$'\t' read -r kind name _source _target _mode; do
        [[ -z "$name" ]] && continue
        log "  - $name ($kind)"
    done < "$manifest_data"
    if ! $DRY_RUN; then
        prompt "Proceed?" || { log "aborted"; exit 0; }
    fi
    local kind name source_rel target_rel mode target_path expected_target current_target
    local recorded_repo_root
    recorded_repo_root="$(manifest_repo_root "$MANIFEST_PATH")"
    [[ -n "$recorded_repo_root" ]] || die "manifest missing repo_root: $MANIFEST_PATH"
    while IFS=$'\t' read -r kind name source_rel target_rel mode; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_PATH/$target_rel"
        expected_target="$recorded_repo_root/$source_rel"
        if [[ -L "$target_path" ]]; then
            current_target="$(read_link_target "$target_path")"
            [[ "$current_target" != /* ]] && current_target="$(canonicalize "$(dirname "$target_path")/$current_target")"
            if [[ "$current_target" == "$expected_target" ]]; then
                if $DRY_RUN; then
                    log "  (dry-run) rm $target_path"
                else
                    rm -f "$target_path"
                    log "  - removed $name"
                fi
            else
                warn "skipping $name during uninstall; target changed to $current_target"
            fi
        else
            warn "skipping $name during uninstall; not a symlink"
        fi
    done < "$manifest_data"
    rm -f "$manifest_data"
    if ! $DRY_RUN; then
        mv -f "$MANIFEST_PATH" "$MANIFEST_PREV"
        log "  ✓ uninstalled (manifest preserved as $MANIFEST_PREV)"
    fi
    remove_agents_doc_block
}

log ""
log "ARIS Codex Project Install"
log "  Project:   $PROJECT_PATH"
log "  Repo:      $ARIS_REPO"
log "  Packages:  $(selected_packages | paste -sd, -)"
log "  Action:    $ACTION$($DRY_RUN && echo ' (dry-run)')"
log ""

check_no_symlinked_parents
check_legacy_nested_install
if ! $DRY_RUN; then
    acquire_lock
fi

if [[ "$ACTION" == "uninstall" ]]; then
    do_uninstall
    exit 0
fi

if [[ "$ACTION" == "reconcile" && ! -f "$MANIFEST_PATH" ]]; then
    die "--reconcile requires existing manifest; none found at $MANIFEST_PATH"
fi

UPSTREAM_FILE="$(mktemp -t aris-codex-upstream.XXXX)"
build_upstream_inventory "$ARIS_REPO" "$UPSTREAM_FILE"

MANIFEST_DATA="$(mktemp -t aris-codex-manifest.XXXX)"
load_manifest "$MANIFEST_PATH" "$MANIFEST_DATA"

PLAN_FILE="$(mktemp -t aris-codex-plan.XXXX)"
compute_plan "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE"
print_plan "$PLAN_FILE"

if grep -q '^CONFLICT|' "$PLAN_FILE"; then
    log ""
    log "Aborting due to unresolved conflicts."
    log "Use --replace-link NAME for a symlink you intentionally want to replace."
    exit 1
fi

if $DRY_RUN; then
    log ""
    log "(dry-run) no changes made"
    rm -f "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE"
    exit 0
fi

N_CHANGES="$(awk -F'|' '$1=="CREATE"||$1=="UPDATE_TARGET"||$1=="REMOVE"{n++} END{print n+0}' "$PLAN_FILE")"
if (( N_CHANGES > 0 )); then
    prompt "Apply these $N_CHANGES changes?" || { log "aborted"; exit 0; }
fi

MANIFEST_TMP="$MANIFEST_PATH.tmp.$$"
write_manifest_tmp "$PLAN_FILE" "$MANIFEST_TMP"
log ""
log "Applying:"
apply_plan "$PLAN_FILE"
commit_manifest "$MANIFEST_TMP"

INSTALLED_NAMES="$(mktemp -t aris-codex-names.XXXX)"
awk -F'|' '$1=="REUSE"||$1=="ADOPT"||$1=="CREATE"||$1=="UPDATE_TARGET"{print $3}' "$PLAN_FILE" > "$INSTALLED_NAMES"
update_agents_doc "$INSTALLED_NAMES"

if ! $DRY_RUN; then
    local_bad=0
    while IFS=$'\t' read -r kind name source_rel target_rel mode; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_PATH/$target_rel"
        expected_target="$ARIS_REPO/$source_rel"
        if [[ ! -L "$target_path" ]]; then
            warn "verify: missing symlink $target_path"
            local_bad=$((local_bad + 1))
            continue
        fi
        current_target="$(read_link_target "$target_path")"
        [[ "$current_target" != /* ]] && current_target="$(canonicalize "$(dirname "$target_path")/$current_target")"
        if [[ "$current_target" != "$expected_target" ]]; then
            warn "verify: wrong target for $target_path -> $current_target"
            local_bad=$((local_bad + 1))
        fi
    done < <(awk -F'\t' '
        BEGIN { in_body=0 }
        /^kind\tname\tsource_rel\ttarget_rel\tmode$/ { in_body=1; next }
        in_body && NF==5 { print }
    ' "$MANIFEST_PATH")
    (( local_bad == 0 )) && log "" && log "✓ Codex install complete. $N_CHANGES changes applied."
fi

rm -f "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE" "$INSTALLED_NAMES"
