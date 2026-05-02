#!/usr/bin/env bash
# install_aris.sh — Project-local ARIS skill installation (flat per-skill symlinks).
#
# Each ARIS skill is symlinked into `<project>/.claude/skills/<skill-name>` so
# Claude Code's slash-command discovery (which only scans one level deep) finds it.
# A versioned manifest at `<project>/.aris/installed-skills.txt` tracks every
# entry this installer created — uninstall and reconcile read from the manifest
# and never touch user-owned skills with the same name.
#
# Usage:
#   bash tools/install_aris.sh [project_path] [options]
#
# Actions (mutually exclusive, default: auto):
#   default          install if no manifest, else reconcile
#   --reconcile      explicit reconcile; refuse if no manifest
#   --uninstall      remove only entries in manifest; delete manifest
#
# Options:
#   --aris-repo PATH       override aris-repo discovery
#   --dry-run              show plan, no writes
#   --quiet                no prompts; abort on any condition that would prompt
#   --no-doc               skip CLAUDE.md update
#   --adopt-existing NAME  adopt a non-managed symlink that already points to
#                          the correct upstream target (repeatable)
#   --replace-link NAME    replace an upstream-internal symlink that points to
#                          a DIFFERENT entry than expected (repeatable)
#   --from-old             trigger migration from legacy nested install
#                          (.claude/skills/aris/)
#   --migrate-copy STRAT   for legacy COPY install: STRAT = keep-user | prefer-upstream
#                          (default: refuse)
#   --clear-stale-lock     remove stale lock dir from a crashed prior run
#                          (host+PID metadata is verified before removal)
#
# Safety rules enforced:
#   S1  Never delete a path that is not a symlink.
#   S2  Never delete a symlink whose target is outside the configured aris-repo.
#   S3  Never delete a symlink not listed in the manifest (except via --uninstall
#       which only deletes manifest entries).
#   S4  Never overwrite an existing path during CREATE — abort by default.
#   S5  Manifest write is atomic (temp + rename in same dir).
#   S6  Concurrent runs in same project serialize via mkdir lockdir.
#   S7  Crash mid-apply leaves the previous manifest intact; rerun adopts.
#   S8  Uninstall revalidates each managed symlink's target before removing.
#   S9  If .aris/, .claude/, or .claude/skills/ is itself a symlink, abort.
#   S10 Reject upstream entries that are symlinks to outside aris-repo.
#   S11 Revalidate exact target match (lstat + readlink) before every mutation.
#   S12 The optional `.aris/tools` symlink (added in #174) is the only managed
#       artifact NOT tracked in the manifest. It is identified at uninstall
#       time by exact target match against `<aris-repo>/tools`. Any other
#       path or differently-targeted symlink at `.aris/tools` is left alone.
#   S12 Temp files live in the same directory as the destination.
#   S13 Skill names must match ^[A-Za-z0-9][A-Za-z0-9._-]*$ (slug regex).

set -euo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
MANIFEST_VERSION="1"
MANIFEST_NAME="installed-skills.txt"
MANIFEST_PREV_NAME="installed-skills.txt.prev"
ARIS_DIR_NAME=".aris"
LOCK_DIR_NAME=".install.lock.d"
SKILLS_REL=".claude/skills"
DOC_FILE_NAME="CLAUDE.md"
BLOCK_BEGIN="<!-- ARIS:BEGIN -->"
BLOCK_END="<!-- ARIS:END -->"
SAFE_NAME_REGEX='^[A-Za-z0-9][A-Za-z0-9._-]*$'
SUPPORT_NAMES=("shared-references")
EXCLUDE_TOP_NAMES=("skills-codex" "skills-codex.bak")  # not skills, not symlinked

# ─── Argument parsing ─────────────────────────────────────────────────────────
PROJECT_PATH=""
ARIS_REPO_OVERRIDE=""
ACTION="auto"        # auto | reconcile | uninstall
DRY_RUN=false
QUIET=false
NO_DOC=false
FROM_OLD=false
MIGRATE_COPY=""      # "" | keep-user | prefer-upstream
CLEAR_STALE_LOCK=false
ADOPT_NAMES=()
REPLACE_LINK_NAMES=()

usage() { sed -n '2,40p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --reconcile)         ACTION="reconcile"; shift ;;
        --uninstall)         ACTION="uninstall"; shift ;;
        --aris-repo)         ARIS_REPO_OVERRIDE="${2:?--aris-repo requires path}"; shift 2 ;;
        --dry-run)           DRY_RUN=true; shift ;;
        --quiet)             QUIET=true; shift ;;
        --no-doc)            NO_DOC=true; shift ;;
        --from-old)          FROM_OLD=true; shift ;;
        --migrate-copy)      MIGRATE_COPY="${2:?--migrate-copy requires keep-user|prefer-upstream}"; shift 2 ;;
        --clear-stale-lock)  CLEAR_STALE_LOCK=true; shift ;;
        --adopt-existing)    ADOPT_NAMES+=("${2:?--adopt-existing requires NAME}"); shift 2 ;;
        --replace-link)      REPLACE_LINK_NAMES+=("${2:?--replace-link requires NAME}"); shift 2 ;;
        --platform)
            echo "Error: --platform is removed. ARIS now only supports Claude Code (.claude/skills/)." >&2
            echo "       Codex CLI users: see docs for the manual codex setup." >&2
            exit 2 ;;
        --force)
            echo "Error: --force is removed. Use the granular flags:" >&2
            echo "       --adopt-existing NAME (for non-managed symlinks pointing to correct upstream)" >&2
            echo "       --replace-link NAME (for managed symlinks pointing to different upstream entry)" >&2
            echo "       Real files/directories are never overwritten — back up and remove them yourself." >&2
            exit 2 ;;
        -h|--help)           usage; exit 0 ;;
        --*)                 echo "Unknown option: $1" >&2; exit 2 ;;
        *)
            if [[ -z "$PROJECT_PATH" ]]; then PROJECT_PATH="$1"
            else echo "Error: unexpected positional: $1" >&2; exit 2; fi
            shift ;;
    esac
done

if [[ -n "$MIGRATE_COPY" && "$MIGRATE_COPY" != "keep-user" && "$MIGRATE_COPY" != "prefer-upstream" ]]; then
    echo "Error: --migrate-copy must be keep-user or prefer-upstream (got: $MIGRATE_COPY)" >&2; exit 2
fi

# ─── Helpers ──────────────────────────────────────────────────────────────────
log()      { $QUIET && return 0; echo "$@"; }
warn()     { echo "warning: $*" >&2; }
die()      { echo "error: $*" >&2; exit 1; }
prompt()   { $QUIET && return 1; printf "%s " "$1" >&2; read -r REPLY; [[ "$REPLY" =~ ^[Yy]$ ]]; }
abs_path() { ( cd "$1" 2>/dev/null && pwd ) || return 1; }

is_safe_name() { [[ "$1" =~ $SAFE_NAME_REGEX ]]; }

# Read symlink target without following further (one hop)
read_link_target() {
    if command -v greadlink >/dev/null 2>&1; then greadlink "$1"
    else readlink "$1"; fi
}

# Resolve a path, following all symlinks, to a canonical absolute path
canonicalize() {
    if command -v greadlink >/dev/null 2>&1; then greadlink -f "$1" 2>/dev/null || true
    elif readlink -f "$1" 2>/dev/null; then :
    else
        # macOS fallback: cd + pwd
        local d f
        if [[ -d "$1" ]]; then ( cd "$1" && pwd )
        else d="$(dirname "$1")"; f="$(basename "$1")"; ( cd "$d" 2>/dev/null && echo "$(pwd)/$f" )
        fi
    fi
}

# True if $1 is a symlink (lstat-style; doesn't follow)
is_symlink() { [[ -L "$1" ]]; }

# Find aris-repo location
resolve_aris_repo() {
    local p
    if [[ -n "$ARIS_REPO_OVERRIDE" ]]; then
        p="$(abs_path "$ARIS_REPO_OVERRIDE")" || die "--aris-repo path not found: $ARIS_REPO_OVERRIDE"
        [[ -d "$p/skills" ]] || die "--aris-repo has no skills/ subdir: $p"
        echo "$p"; return
    fi
    local script_dir parent
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    parent="$(cd "$script_dir/.." && pwd)"
    if [[ -d "$parent/skills" ]]; then echo "$parent"; return; fi
    if [[ -n "${ARIS_REPO:-}" && -d "$ARIS_REPO/skills" ]]; then abs_path "$ARIS_REPO"; return; fi
    for guess in \
        "$HOME/Desktop/aris_repo" \
        "$HOME/aris_repo" \
        "$HOME/.aris" \
        "$HOME/Desktop/Auto-claude-code-research-in-sleep" \
        "$HOME/.codex/Auto-claude-code-research-in-sleep" \
        "$HOME/.claude/Auto-claude-code-research-in-sleep" ; do
        [[ -d "$guess/skills" ]] && { abs_path "$guess"; return; }
    done
    die "cannot find ARIS repo. Use --aris-repo PATH or set ARIS_REPO env var."
}

# Build the upstream inventory: array of "kind|name" entries
# Skills = top-level dirs in <aris-repo>/skills/ containing SKILL.md
# Support = explicitly listed support directories (shared-references)
# Rejects: anything in EXCLUDE_TOP_NAMES, names failing slug regex, symlinks to outside aris-repo (S10)
build_upstream_inventory() {
    local repo="$1"
    local skills_dir="$repo/skills"
    local entries=() name kind src
    # skills (with SKILL.md)
    for d in "$skills_dir"/*/; do
        name="$(basename "$d")"
        is_safe_name "$name" || { warn "skipping unsafe upstream name: $name"; continue; }
        # exclude listed
        for ex in "${EXCLUDE_TOP_NAMES[@]}"; do [[ "$name" == "$ex" ]] && continue 2; done
        # support entries handled separately
        local is_support=false
        for s in "${SUPPORT_NAMES[@]}"; do [[ "$name" == "$s" ]] && { is_support=true; break; }; done
        if $is_support; then continue; fi
        if [[ ! -f "$d/SKILL.md" ]]; then continue; fi
        # S10: source must not be a symlink leading outside the repo
        src="$skills_dir/$name"
        if is_symlink "$src"; then
            local resolved; resolved="$(canonicalize "$src")"
            [[ "$resolved" == "$repo"/* ]] || { warn "skipping upstream symlink leading outside repo: $name -> $resolved"; continue; }
        fi
        entries+=("skill|$name")
    done
    # support directories (existing only)
    for s in "${SUPPORT_NAMES[@]}"; do
        if [[ -d "$skills_dir/$s" ]]; then entries+=("support|$s"); fi
    done
    printf "%s\n" "${entries[@]}"
}

# Parse manifest into a global associative-style array via temp file lookup
# We store the parsed content in $MANIFEST_DATA_FILE (one entry per line) for grep lookup
load_manifest() {
    local path="$1" out="$2"
    : > "$out"
    [[ -f "$path" ]] || return 0
    # Validate version header
    local ver; ver="$(awk -F'\t' '$1=="version"{print $2}' "$path" | head -1)"
    [[ "$ver" == "$MANIFEST_VERSION" ]] || die "manifest version mismatch (file: $ver, expected: $MANIFEST_VERSION)"
    # Body lines: kind\tname\tsource_rel\ttarget_rel\tmode
    awk -F'\t' '
        BEGIN { in_body=0 }
        /^kind\tname\tsource_rel\ttarget_rel\tmode$/ { in_body=1; next }
        in_body && NF==5 { print }
    ' "$path" > "$out"
}

manifest_lookup_target() {
    # echo target_rel for given name from $1=manifest_data_file $2=name
    awk -F'\t' -v n="$2" '$2==n {print $4; exit}' "$1"
}
manifest_lookup_source() {
    awk -F'\t' -v n="$2" '$2==n {print $3; exit}' "$1"
}
manifest_names() { awk -F'\t' '{print $2}' "$1"; }
manifest_kind_of() {
    awk -F'\t' -v n="$2" '$2==n {print $1; exit}' "$1"
}

# ─── Resolve project path & aris-repo ─────────────────────────────────────────
PROJECT_PATH="${PROJECT_PATH:-$(pwd)}"
[[ -d "$PROJECT_PATH" ]] || die "project path does not exist: $PROJECT_PATH"
PROJECT_PATH="$(abs_path "$PROJECT_PATH")"
ARIS_REPO="$(resolve_aris_repo)"
SKILLS_DIR_ABS="$ARIS_REPO/skills"
PROJECT_SKILLS_DIR="$PROJECT_PATH/$SKILLS_REL"
PROJECT_ARIS_DIR="$PROJECT_PATH/$ARIS_DIR_NAME"
MANIFEST_PATH="$PROJECT_ARIS_DIR/$MANIFEST_NAME"
MANIFEST_PREV="$PROJECT_ARIS_DIR/$MANIFEST_PREV_NAME"
LOCK_DIR="$PROJECT_ARIS_DIR/$LOCK_DIR_NAME"
DOC_FILE="$PROJECT_PATH/$DOC_FILE_NAME"

# ─── S9: refuse if .aris / .claude / .claude/skills is itself a symlink ───────
# (.aris and .claude/skills may not exist yet — only check if present.)
check_no_symlinked_parents() {
    local p
    for p in "$PROJECT_ARIS_DIR" "$PROJECT_PATH/.claude" "$PROJECT_SKILLS_DIR"; do
        if is_symlink "$p"; then
            die "S9: $p is a symlink — refusing to install (would mutate symlink target)"
        fi
    done
}

# ─── Lock acquisition (mkdir-based, portable) ─────────────────────────────────
write_lock_metadata() {
    # Two files: owner.json for human inspection, owner.pid for reliable parsing
    cat > "$LOCK_DIR/owner.json" <<EOF
{"host":"$(hostname)","pid":$$,"started_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","tool":"install_aris.sh"}
EOF
    echo "$$" > "$LOCK_DIR/owner.pid"
    echo "$(hostname)" > "$LOCK_DIR/owner.host"
}

acquire_lock() {
    mkdir -p "$PROJECT_ARIS_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        write_lock_metadata
        trap release_lock EXIT INT TERM
        return 0
    fi
    if $CLEAR_STALE_LOCK; then
        local owner=""
        [[ -f "$LOCK_DIR/owner.json" ]] && owner="$(cat "$LOCK_DIR/owner.json")"
        warn "removing stale lock: $LOCK_DIR (was: $owner)"
        rm -rf "$LOCK_DIR"
        mkdir "$LOCK_DIR" || die "still cannot acquire lock after stale clear"
        write_lock_metadata
        trap release_lock EXIT INT TERM
        return 0
    fi
    local owner=""
    [[ -f "$LOCK_DIR/owner.json" ]] && owner="$(cat "$LOCK_DIR/owner.json")"
    die "another install_aris.sh is running in this project (lock: $LOCK_DIR)
       owner: $owner
       if you are sure no install is in progress, rerun with --clear-stale-lock"
}

release_lock() {
    [[ -d "$LOCK_DIR" ]] || return 0
    if [[ -f "$LOCK_DIR/owner.pid" ]]; then
        local pid; pid="$(cat "$LOCK_DIR/owner.pid" 2>/dev/null || echo "")"
        local host; host="$(cat "$LOCK_DIR/owner.host" 2>/dev/null || echo "")"
        if [[ "$pid" == "$$" && "$host" == "$(hostname)" ]]; then
            rm -rf "$LOCK_DIR"
        fi
    fi
}

# ─── Migration detection ──────────────────────────────────────────────────────
LEGACY_NESTED="$PROJECT_SKILLS_DIR/aris"

detect_legacy() {
    if [[ ! -e "$LEGACY_NESTED" && ! -L "$LEGACY_NESTED" ]]; then echo "none"; return; fi
    if is_symlink "$LEGACY_NESTED"; then
        local tgt; tgt="$(read_link_target "$LEGACY_NESTED")"
        if [[ "$tgt" == "$SKILLS_DIR_ABS" || "$tgt" == "$SKILLS_DIR_ABS/" ]]; then
            echo "symlink_to_repo"
        else
            echo "symlink_to_other"
        fi
    elif [[ -d "$LEGACY_NESTED" ]]; then
        echo "real_dir"
    else
        echo "real_file"
    fi
}

migrate_legacy() {
    local kind; kind="$(detect_legacy)"
    case "$kind" in
        none)
            return 0 ;;
        symlink_to_repo)
            log "→ migrating legacy nested symlink: removing $LEGACY_NESTED"
            $DRY_RUN || rm -f "$LEGACY_NESTED"
            return 0 ;;
        symlink_to_other)
            die "S2: legacy $LEGACY_NESTED is a symlink to OUTSIDE the repo — refusing to touch.
       investigate manually before re-running."
            ;;
        real_file)
            die "$LEGACY_NESTED is a regular file (unexpected). Move/delete it manually." ;;
        real_dir)
            if [[ -z "$MIGRATE_COPY" ]]; then
                die "legacy nested COPY install detected at $LEGACY_NESTED.
       This may contain user edits. Choose explicitly:
         --migrate-copy keep-user        (keep nested copy intact, install flat alongside;
                                          old copy becomes inert for Claude discovery)
         --migrate-copy prefer-upstream  (archive nested copy to .aris/legacy-copy-backup-<ts>/
                                          AFTER new flat install is verified, then flatten)"
            fi
            # actual handling deferred until after apply (for prefer-upstream)
            return 0 ;;
    esac
}

archive_legacy_copy() {
    local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
    local archive="$PROJECT_ARIS_DIR/legacy-copy-backup-$ts"
    log "→ archiving legacy nested copy to: $archive"
    $DRY_RUN || mv "$LEGACY_NESTED" "$archive"
}

# ─── Plan computation ─────────────────────────────────────────────────────────
# Plan is written to a temp file, one line per action: ACTION|kind|name|extra
# Actions: CREATE | UPDATE_TARGET | REUSE | REMOVE | ADOPT | CONFLICT
compute_plan() {
    local upstream_file="$1" manifest_data="$2" out="$3"
    : > "$out"
    local target_path src expected_target current_target line kind name
    # Iterate upstream entries
    while IFS='|' read -r kind name; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_SKILLS_DIR/$name"
        expected_target="$SKILLS_DIR_ABS/$name"
        if [[ -L "$target_path" ]]; then
            current_target="$(read_link_target "$target_path")"
            # Convert relative readlink to absolute (relative to symlink's dir)
            if [[ "$current_target" != /* ]]; then
                current_target="$(canonicalize "$PROJECT_SKILLS_DIR/$current_target")"
            fi
            local in_manifest=false
            if [[ -n "$(manifest_lookup_target "$manifest_data" "$name")" ]]; then in_manifest=true; fi
            if [[ "$current_target" == "$expected_target" ]]; then
                if $in_manifest; then echo "REUSE|$kind|$name|" >> "$out"
                else echo "ADOPT|$kind|$name|" >> "$out"
                fi
            else
                # symlink exists but points elsewhere
                if $in_manifest; then
                    # managed symlink with stale target — can update with --replace-link or auto if safely inside repo
                    echo "UPDATE_TARGET|$kind|$name|$current_target" >> "$out"
                else
                    # foreign symlink (user's own?) — conflict
                    echo "CONFLICT|$kind|$name|symlink_to:$current_target" >> "$out"
                fi
            fi
        elif [[ -e "$target_path" ]]; then
            # real file/dir
            echo "CONFLICT|$kind|$name|real_path" >> "$out"
        else
            echo "CREATE|$kind|$name|" >> "$out"
        fi
    done < "$upstream_file"
    # Manifest entries no longer in upstream → REMOVE
    while IFS=$'\t' read -r mkind mname msrc mtarget mmode; do
        [[ -z "$mname" ]] && continue
        # is name in upstream?
        if grep -q "^[^|]*|$mname$" "$upstream_file"; then continue; fi
        echo "REMOVE|$mkind|$mname|" >> "$out"
    done < "$manifest_data"
}

# ─── Plan rendering ───────────────────────────────────────────────────────────
print_plan() {
    local plan="$1"
    local n_create n_update n_reuse n_remove n_adopt n_conflict
    n_create=$(grep -c '^CREATE|' "$plan" || true)
    n_update=$(grep -c '^UPDATE_TARGET|' "$plan" || true)
    n_reuse=$(grep -c '^REUSE|' "$plan" || true)
    n_remove=$(grep -c '^REMOVE|' "$plan" || true)
    n_adopt=$(grep -c '^ADOPT|' "$plan" || true)
    n_conflict=$(grep -c '^CONFLICT|' "$plan" || true)
    log ""
    log "Plan summary:"
    log "  CREATE:        $n_create  (new flat symlinks to add)"
    log "  ADOPT:         $n_adopt   (orphan symlinks already pointing to correct target)"
    log "  UPDATE_TARGET: $n_update  (managed symlinks with stale target)"
    log "  REUSE:         $n_reuse   (already correct, no-op)"
    log "  REMOVE:        $n_remove  (in old manifest, no longer upstream)"
    log "  CONFLICT:      $n_conflict  (must be resolved before apply)"
    if (( n_conflict > 0 )); then
        log ""
        log "Conflicts (need user action):"
        grep '^CONFLICT|' "$plan" | while IFS='|' read -r _ kind name extra; do
            log "  - $name ($kind): $extra"
        done
    fi
}

# ─── Apply ────────────────────────────────────────────────────────────────────
# Order (safer than mine, per codex round 3):
#   1. Write new manifest temp (in-place dir for atomic rename)
#   2. Apply mutations with revalidation (lstat + readlink) right before each
#   3. Copy current manifest to .prev.tmp, rename to .prev
#   4. Rename new manifest temp over current manifest (LAST commit point)
#   5. CLAUDE.md update (best-effort, compare-and-swap, never fails install)

write_manifest_tmp() {
    local plan="$1" out="$2"
    {
        printf "version\t%s\n" "$MANIFEST_VERSION"
        printf "repo_root\t%s\n" "$ARIS_REPO"
        printf "project_root\t%s\n" "$PROJECT_PATH"
        printf "generated\t%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf "kind\tname\tsource_rel\ttarget_rel\tmode\n"
        # New manifest = REUSE + ADOPT + CREATE + UPDATE_TARGET (i.e., everything that will exist as a managed symlink after apply)
        awk -F'|' '$1=="REUSE"||$1=="ADOPT"||$1=="CREATE"||$1=="UPDATE_TARGET"{print $0}' "$plan" \
        | while IFS='|' read -r action kind name _; do
            printf "%s\t%s\tskills/%s\t%s/%s\tsymlink\n" "$kind" "$name" "$name" "$SKILLS_REL" "$name"
        done
    } > "$out"
}

# Verify current symlink state matches our expectation immediately before mutating
revalidate_symlink_target() {
    local path="$1" expected="$2"
    is_symlink "$path" || return 1
    local cur; cur="$(read_link_target "$path")"
    [[ "$cur" != /* ]] && cur="$(canonicalize "$(dirname "$path")/$cur")"
    [[ "$cur" == "$expected" ]]
}

apply_plan() {
    local plan="$1" manifest_tmp="$2"
    mkdir -p "$PROJECT_SKILLS_DIR"
    local action kind name extra target_path expected_target
    while IFS='|' read -r action kind name extra; do
        [[ -z "$name" ]] && continue
        target_path="$PROJECT_SKILLS_DIR/$name"
        expected_target="$SKILLS_DIR_ABS/$name"
        case "$action" in
            REUSE|ADOPT)
                : # nothing to do; manifest will record it
                ;;
            CREATE)
                # S4: must not exist
                if [[ -e "$target_path" || -L "$target_path" ]]; then
                    die "S4 violation: $target_path appeared between plan and apply"
                fi
                if $DRY_RUN; then log "  (dry-run) ln -s $expected_target $target_path"
                else ln -s "$expected_target" "$target_path"; log "  + $name"
                fi
                ;;
            UPDATE_TARGET)
                # S11: revalidate current target equals what plan saw
                local plan_saw_target; plan_saw_target="$(read_link_target "$target_path" 2>/dev/null || echo "")"
                [[ "$plan_saw_target" != /* && -n "$plan_saw_target" ]] && plan_saw_target="$(canonicalize "$(dirname "$target_path")/$plan_saw_target")"
                if [[ "$plan_saw_target" != "$extra" ]]; then
                    warn "S11: $target_path target changed since plan ($plan_saw_target vs $extra) — skipping"
                    continue
                fi
                # S2: stale target must point inside aris-repo
                if [[ "$plan_saw_target" != "$ARIS_REPO"/* ]]; then
                    warn "S2: refusing to replace symlink pointing outside aris-repo: $target_path -> $plan_saw_target"
                    continue
                fi
                if $DRY_RUN; then log "  (dry-run) update target: $target_path -> $expected_target"
                else
                    rm -f "$target_path"
                    ln -s "$expected_target" "$target_path"
                    log "  ↻ $name"
                fi
                ;;
            REMOVE)
                # S1: must be a symlink
                is_symlink "$target_path" || { warn "S1: $target_path is not a symlink, refusing to remove"; continue; }
                # S2: target must be inside aris-repo
                local cur; cur="$(read_link_target "$target_path")"
                [[ "$cur" != /* ]] && cur="$(canonicalize "$(dirname "$target_path")/$cur")"
                [[ "$cur" == "$ARIS_REPO"/* ]] || { warn "S2: $target_path target $cur outside aris-repo, refusing"; continue; }
                if $DRY_RUN; then log "  (dry-run) rm $target_path"
                else rm -f "$target_path"; log "  - $name"
                fi
                ;;
            CONFLICT)
                die "BUG: CONFLICT $name reached apply phase"
                ;;
        esac
    done < "$plan"
}

# Phase 0 (#174): ensure project-local `.aris/tools` symlink exists, pointing
# to the canonical aris-repo `tools/` dir. Pure-additive: existing users who
# don't rerun the installer never see this. The symlink is currently inert
# (no SKILL.md references it); it sets up future #177 path-rewrites.
#
# Idempotent. If `.aris/tools` already exists with a different target (or as
# a real file/dir), warn and leave it alone — never replace user content.
# Membership in the "managed" set is determined by exact target match against
# `$ARIS_REPO/tools`, not via the manifest, so we don't need to bump the
# manifest format for this single-link addition (per #174 non-goals).
ensure_tools_symlink() {
    local link_path="$PROJECT_ARIS_DIR/tools"
    local expected_target="$ARIS_REPO/tools"

    if is_symlink "$link_path"; then
        local cur; cur="$(read_link_target "$link_path")"
        [[ "$cur" != /* ]] && cur="$(canonicalize "$(dirname "$link_path")/$cur")"
        if [[ "$cur" == "$expected_target" ]]; then
            return 0
        fi
        warn ".aris/tools already exists with different target ($cur); leaving alone (#174)"
        return 0
    fi

    if [[ -e "$link_path" ]]; then
        warn ".aris/tools already exists as a non-symlink path; leaving alone (#174)"
        return 0
    fi

    if $DRY_RUN; then
        log "  (dry-run) ln -s $expected_target $link_path"
    else
        ln -s "$expected_target" "$link_path"
        log "  + .aris/tools -> tools/ (Phase 0, #174)"
    fi
}

# Counterpart for uninstall: only remove `.aris/tools` if it is exactly the
# managed symlink (target == $ARIS_REPO/tools). User-created directories /
# files / different symlinks are untouched.
remove_tools_symlink() {
    local link_path="$PROJECT_ARIS_DIR/tools"
    local expected_target="$ARIS_REPO/tools"

    is_symlink "$link_path" || return 0
    local cur; cur="$(read_link_target "$link_path")"
    [[ "$cur" != /* ]] && cur="$(canonicalize "$(dirname "$link_path")/$cur")"
    if [[ "$cur" != "$expected_target" ]]; then
        return 0
    fi

    if $DRY_RUN; then
        log "  (dry-run) rm $link_path"
    else
        rm -f "$link_path"
        log "  - .aris/tools (managed symlink)"
    fi
}

commit_manifest() {
    local manifest_tmp="$1"
    if $DRY_RUN; then log "  (dry-run) would commit manifest"; return; fi
    # Backup current manifest if exists
    if [[ -f "$MANIFEST_PATH" ]]; then
        cp -p "$MANIFEST_PATH" "$MANIFEST_PREV.tmp"
        mv -f "$MANIFEST_PREV.tmp" "$MANIFEST_PREV"
    fi
    # Atomic rename from temp (same dir → atomic on same FS)
    mv -f "$manifest_tmp" "$MANIFEST_PATH"
}

# ─── CLAUDE.md best-effort update (compare-and-swap) ──────────────────────────
update_claude_doc() {
    local installed_names_file="$1"
    [[ -f "$DOC_FILE" ]] || { log "  (skip CLAUDE.md: file not present)"; return 0; }
    if $NO_DOC; then return 0; fi

    local original new_block tmp
    original="$(cat "$DOC_FILE")"
    # Build new block
    local count; count="$(wc -l < "$installed_names_file" | tr -d ' ')"
    new_block="$BLOCK_BEGIN
## ARIS Skill Scope
ARIS skills installed in this project: $count entries.
Manifest: \`$ARIS_DIR_NAME/$MANIFEST_NAME\` (lists every skill ARIS installed and its upstream target).
For ARIS workflows, prefer the project-local skills under \`$SKILLS_REL/\` over global skills.
Do not modify or delete files inside any skill that is a symlink (symlinks point into \`$ARIS_REPO\`).
Update with: \`bash $ARIS_REPO/tools/install_aris.sh\`  (re-runnable; reconciles new/removed skills).
$BLOCK_END"

    # Compute new content
    local new_content
    if printf '%s' "$original" | grep -qF "$BLOCK_BEGIN"; then
        new_content="$(python3 - "$DOC_FILE" "$BLOCK_BEGIN" "$BLOCK_END" "$new_block" <<'PYEOF'
import re, sys, pathlib
path, begin, end, body = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
text = pathlib.Path(path).read_text()
pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
matches = pattern.findall(text)
if len(matches) > 1:
    sys.stderr.write("ARIS:WARN multiple ARIS blocks found in CLAUDE.md; skipping update\n")
    sys.stdout.write(text)
else:
    sys.stdout.write(pattern.sub(body, text))
PYEOF
        )" || { warn "CLAUDE.md update failed (best-effort, continuing)"; return 0; }
    else
        new_content="$original"
        [[ -n "$original" ]] && new_content="${new_content}"$'\n'
        new_content="${new_content}${new_block}"$'\n'
    fi

    # Compare-and-swap: re-read file, only commit if unchanged from snapshot
    if $DRY_RUN; then log "  (dry-run) would update CLAUDE.md ARIS block"; return 0; fi
    tmp="$DOC_FILE.aris-tmp.$$"
    printf '%s' "$new_content" > "$tmp"
    local current; current="$(cat "$DOC_FILE")"
    if [[ "$current" != "$original" ]]; then
        rm -f "$tmp"
        warn "CLAUDE.md changed during install — skipping doc update (rerun to retry)"
        return 0
    fi
    mv -f "$tmp" "$DOC_FILE"
    log "  ✓ updated CLAUDE.md (ARIS managed block)"
}

# ─── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
    [[ -f "$MANIFEST_PATH" ]] || die "no manifest at $MANIFEST_PATH; nothing to uninstall"
    local manifest_data; manifest_data="$(mktemp -t aris-manifest.XXXX)"
    load_manifest "$MANIFEST_PATH" "$manifest_data"
    log ""
    log "Uninstall plan:"
    while IFS=$'\t' read -r kind name src target mode; do
        [[ -z "$name" ]] && continue
        log "  - $name ($kind)"
    done < "$manifest_data"
    if ! $DRY_RUN && ! $QUIET; then
        prompt "Proceed?" || { log "aborted"; exit 0; }
    fi
    while IFS=$'\t' read -r kind name src target mode; do
        [[ -z "$name" ]] && continue
        local target_path="$PROJECT_PATH/$target"
        local expected="$SKILLS_DIR_ABS/$name"
        # S1: must be symlink
        is_symlink "$target_path" || { warn "S1: $target_path not a symlink, skipping"; continue; }
        # S8 + S11: revalidate target
        local cur; cur="$(read_link_target "$target_path")"
        [[ "$cur" != /* ]] && cur="$(canonicalize "$(dirname "$target_path")/$cur")"
        if [[ "$cur" != "$expected" ]]; then
            warn "S8: $target_path target $cur != expected $expected, skipping"
            continue
        fi
        if $DRY_RUN; then log "  (dry-run) rm $target_path"
        else rm -f "$target_path"; log "  - removed $name"
        fi
    done < "$manifest_data"
    rm -f "$manifest_data"
    # #174 Phase 0: best-effort cleanup of `.aris/tools` symlink, only if it
    # is exactly the managed symlink. Anything else (user-created dir, custom
    # symlink target) is left alone.
    remove_tools_symlink
    if ! $DRY_RUN; then
        # Keep .prev for forensics, remove current manifest
        [[ -f "$MANIFEST_PATH" ]] && mv -f "$MANIFEST_PATH" "$MANIFEST_PREV"
        log "  ✓ uninstalled (manifest preserved as $MANIFEST_PREV)"
    fi
}

# ─── Main flow ────────────────────────────────────────────────────────────────
log ""
log "ARIS Project Install"
log "  Project:    $PROJECT_PATH"
log "  ARIS repo:  $ARIS_REPO"
log "  Action:     $ACTION$($DRY_RUN && echo ' (dry-run)')"
log ""

check_no_symlinked_parents
acquire_lock

if [[ "$ACTION" == "uninstall" ]]; then
    do_uninstall
    exit 0
fi

# Migration check (only for install/reconcile)
LEGACY_KIND="$(detect_legacy)"
if [[ "$LEGACY_KIND" != "none" ]]; then
    if ! $FROM_OLD; then
        log "Legacy nested install detected: $LEGACY_NESTED ($LEGACY_KIND)"
        log "→ to migrate, rerun with --from-old"
        log "  for COPY-style legacy installs, also pass --migrate-copy keep-user|prefer-upstream"
        exit 1
    fi
    migrate_legacy
fi

# If --reconcile but no manifest, fail
if [[ "$ACTION" == "reconcile" && ! -f "$MANIFEST_PATH" ]]; then
    die "--reconcile requires existing manifest; none found at $MANIFEST_PATH"
fi

# Build inventories
UPSTREAM_FILE="$(mktemp -t aris-upstream.XXXX)"
build_upstream_inventory "$ARIS_REPO" > "$UPSTREAM_FILE"
[[ -s "$UPSTREAM_FILE" ]] || die "upstream inventory empty (broken aris-repo?)"

MANIFEST_DATA="$(mktemp -t aris-manifest.XXXX)"
load_manifest "$MANIFEST_PATH" "$MANIFEST_DATA"

PLAN_FILE="$(mktemp -t aris-plan.XXXX)"
compute_plan "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE"
print_plan "$PLAN_FILE"

# Conflict resolution
N_CONFLICT=$(grep -c '^CONFLICT|' "$PLAN_FILE" || true)
if (( N_CONFLICT > 0 )); then
    # Check if any can be auto-resolved by --adopt-existing (where current target == expected)
    # (Already handled by ADOPT classification — anything still in CONFLICT is a real conflict.)
    # Apply --replace-link allowlist for symlink-to-other-repo-entry conflicts
    if [[ ${#REPLACE_LINK_NAMES[@]} -gt 0 ]]; then
        for n in "${REPLACE_LINK_NAMES[@]}"; do
            sed -i.bak "s|^CONFLICT|$n|UPDATE_TARGET|$n|" "$PLAN_FILE" 2>/dev/null || true
            rm -f "$PLAN_FILE.bak"
        done
        N_CONFLICT=$(grep -c '^CONFLICT|' "$PLAN_FILE" || true)
    fi
    if (( N_CONFLICT > 0 )); then
        log ""
        log "Aborting due to $N_CONFLICT unresolved conflicts."
        log "Resolve options per name:"
        log "  - back up & remove the conflicting path manually, then rerun"
        log "  - if it's a foreign symlink that should be replaced: --replace-link NAME"
        exit 1
    fi
fi

if $DRY_RUN; then
    # #174 preview: print the planned `.aris/tools` symlink action (function
    # is idempotent + DRY_RUN-aware, so it just logs in this mode)
    ensure_tools_symlink
    log ""
    log "(dry-run) no changes made"
    exit 0
fi

# Confirm if any mutations
N_CHANGES=$(awk -F'|' '$1=="CREATE"||$1=="UPDATE_TARGET"||$1=="REMOVE"' "$PLAN_FILE" | wc -l | tr -d ' ')
if (( N_CHANGES > 0 )) && ! $QUIET; then
    prompt "Apply these $N_CHANGES changes?" || { log "aborted"; exit 0; }
fi

# Apply
MANIFEST_TMP="$MANIFEST_PATH.tmp.$$"   # S12: same dir as destination
mkdir -p "$PROJECT_ARIS_DIR"
write_manifest_tmp "$PLAN_FILE" "$MANIFEST_TMP"
log ""
log "Applying:"
apply_plan "$PLAN_FILE" "$MANIFEST_TMP"
commit_manifest "$MANIFEST_TMP"

# #174 Phase 0: ensure project-local .aris/tools symlink (purely additive).
# Runs after manifest commit so a failure here doesn't roll back skill links.
ensure_tools_symlink

# Handle prefer-upstream legacy archive AFTER successful apply
if [[ "$LEGACY_KIND" == "real_dir" && "$MIGRATE_COPY" == "prefer-upstream" ]]; then
    archive_legacy_copy
fi

# CLAUDE.md best-effort
INSTALLED_NAMES="$(mktemp -t aris-names.XXXX)"
awk -F'|' '$1=="REUSE"||$1=="ADOPT"||$1=="CREATE"||$1=="UPDATE_TARGET"{print $3}' "$PLAN_FILE" > "$INSTALLED_NAMES"
update_claude_doc "$INSTALLED_NAMES"
rm -f "$INSTALLED_NAMES"

# Verify
if ! $DRY_RUN; then
    BAD=0
    while IFS=$'\t' read -r v_kind v_name v_src v_target v_mode; do
        [[ -z "$v_name" ]] && continue
        VTARGET="$PROJECT_PATH/$v_target"
        if ! is_symlink "$VTARGET"; then warn "verify: $VTARGET missing"; BAD=$((BAD+1)); fi
    done < <(awk -F'\t' '
        BEGIN { in_body=0 }
        /^kind\tname\tsource_rel\ttarget_rel\tmode$/ { in_body=1; next }
        in_body && NF==5 { print }
    ' "$MANIFEST_PATH")
    (( BAD == 0 )) && log "" && log "✓ Install complete. $N_CHANGES changes applied."
fi

# Cleanup
rm -f "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE"
