#!/usr/bin/env bash
# install_aris_copilot.sh -- Project-local ARIS skill installation for GitHub Copilot CLI.
#
# This installer manages a flat layout using mainline skills:
#   <project>/.github/skills/<skill-name> -> <aris-repo>/skills/<skill-name>
#
# Unlike the Codex installer, Copilot CLI natively supports SKILL.md with
# allowed-tools and MCP tool calls, so mainline skills work directly --
# no separate skill mirror is needed.
#
# Managed entries are tracked in:
#   <project>/.aris/installed-skills-copilot.txt
#
# Usage:
#   bash tools/install_aris_copilot.sh [project_path] [options]
#
# Actions (mutually exclusive, default: auto):
#   default          install if no manifest, else reconcile
#   --reconcile      explicit reconcile; refuse if no manifest
#   --uninstall      remove only entries in manifest; delete manifest
#
# Selection (catalog: tools/skill-groups.tsv in the aris-repo):
#   --groups A,B           install only these skill groups (see --list-groups)
#   --skills X,Y           additionally install these skills (clears declined mark)
#   --exclude X,Y          never install these skills (recorded as declined)
#   --all                  install every upstream skill (legacy default)
#   --add-new              reconcile: accept all upstream skills not yet installed
#   --skip-new             reconcile: skip new upstream skills without prompting
#   --list-groups          print the group catalog and exit
#   With no selection flags: fresh install on a TTY opens a full-screen
#   checkbox picker (Space toggles a skill / a whole group, Enter confirms;
#   ARIS_NO_PICKER=1 or missing python3/curses falls back to per-group
#   Y/n/e prompts); fresh install with --quiet/no TTY installs everything (old behavior).
#   Reconcile keeps exactly what the manifest says is installed; NEW upstream
#   skills need per-skill confirmation (declined ones are remembered in
#   .aris/skills-declined-copilot.txt and never re-asked).
#
# Options:
#   --aris-repo PATH       override aris-repo discovery
#   --dry-run              show plan, no writes
#   --quiet                no prompts; abort on any condition that would prompt
#   --no-doc               skip AGENTS.md managed block update
#   --replace-link NAME    replace a conflicting symlink for NAME (repeatable)
#   --clear-stale-lock     clear a stale installer lock
#
# Safety rules enforced:
#   S1  Never delete a path that is not a symlink.
#   S2  Never delete a symlink whose target is outside the configured aris-repo.
#   S3  Never delete a symlink not listed in the manifest.
#   S4  Never overwrite an existing path during CREATE -- abort by default.
#   S5  Manifest write is atomic (temp + rename in same dir).
#   S6  Concurrent runs in same project serialize via mkdir lockdir.
#   S7  Crash mid-apply leaves the previous manifest intact; rerun adopts.
#   S8  Uninstall revalidates each managed symlink's target before removing.
#   S9  If .aris/, .github/, or .github/skills/ is itself a symlink, abort.
#   S10 Reject upstream entries that are symlinks to outside aris-repo.
#   S11 Revalidate exact target match (lstat + readlink) before every mutation.
#   S12 Temp files live in the same directory as the destination.
#   S13 Skill names must match ^[A-Za-z0-9][A-Za-z0-9._-]*$ (slug regex).

set -euo pipefail

# --- Constants ---
MANIFEST_VERSION="1"
MANIFEST_NAME="installed-skills-copilot.txt"
MANIFEST_PREV_NAME="installed-skills-copilot.txt.prev"
DECLINED_NAME="skills-declined-copilot.txt"
CATALOG_REL="tools/skill-groups.tsv"
GLOBAL_POINTER="$HOME/.aris/repo"
ARIS_DIR_NAME=".aris"
LOCK_DIR_NAME=".install-copilot.lock.d"
SKILLS_REL=".github/skills"
DOC_FILE_NAME="AGENTS.md"
BLOCK_BEGIN="<!-- ARIS-COPILOT:BEGIN -->"
BLOCK_END="<!-- ARIS-COPILOT:END -->"
SAFE_NAME_REGEX='^[A-Za-z0-9][A-Za-z0-9._-]*$'

# Directories to skip when scanning upstream skills/ as installable skills.
# shared-references is handled separately as a "support" entry.
# This pattern MUST stay in sync with smart_update_copilot.sh SKIP_DIRS_PATTERN.
SKIP_DIRS="skills-codex|skills-codex-claude-review|skills-codex-gemini-review|shared-references"

PROJECT_PATH=""
ARIS_REPO_OVERRIDE=""
ACTION="auto"
DRY_RUN=false
QUIET=false
NO_DOC=false
CLEAR_STALE_LOCK=false
REPLACE_LINK_NAMES=()
SELECT_GROUPS=""     # comma list from --groups
SELECT_SKILLS=""     # comma list from --skills
EXCLUDE_SKILLS=""    # comma list from --exclude
SELECT_ALL=false
NEW_POLICY=""        # "" (prompt) | add | skip
LIST_GROUPS=false

usage() { sed -n '2,59p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --reconcile) ACTION="reconcile"; shift ;;
        --uninstall) ACTION="uninstall"; shift ;;
        --aris-repo) ARIS_REPO_OVERRIDE="${2:?--aris-repo requires path}"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --quiet) QUIET=true; shift ;;
        --no-doc) NO_DOC=true; shift ;;
        --replace-link) REPLACE_LINK_NAMES+=("${2:?--replace-link requires NAME}"); shift 2 ;;
        --clear-stale-lock) CLEAR_STALE_LOCK=true; shift ;;
        --groups) SELECT_GROUPS="${SELECT_GROUPS:+$SELECT_GROUPS,}${2:?--groups requires A,B,...}"; shift 2 ;;
        --skills) SELECT_SKILLS="${SELECT_SKILLS:+$SELECT_SKILLS,}${2:?--skills requires X,Y,...}"; shift 2 ;;
        --exclude) EXCLUDE_SKILLS="${EXCLUDE_SKILLS:+$EXCLUDE_SKILLS,}${2:?--exclude requires X,Y,...}"; shift 2 ;;
        --all) SELECT_ALL=true; shift ;;
        --add-new) NEW_POLICY="add"; shift ;;
        --skip-new) NEW_POLICY="skip"; shift ;;
        --list-groups) LIST_GROUPS=true; shift ;;
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

if $SELECT_ALL && [[ -n "$SELECT_GROUPS$SELECT_SKILLS" ]]; then
    echo "Error: --all cannot be combined with --groups/--skills (only --exclude)" >&2; exit 2
fi

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
    # bash 3.2: empty-array "${ARR[@]}" trips `set -u`; no --replace-link = empty allowlist
    [[ ${#REPLACE_LINK_NAMES[@]} -gt 0 ]] || return 1
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
        local script_dir parent
        script_dir="$(cd "$(dirname "$0")" && pwd)"
        parent="$(cd "$script_dir/.." && pwd)"
        if [[ -d "$parent/skills" && -f "$parent/AGENT_GUIDE.md" ]]; then
            p="$parent"
        elif [[ -n "${ARIS_REPO:-}" && -d "$ARIS_REPO/skills" ]]; then
            p="$(abs_path "$ARIS_REPO")"
        else
            local guess
            for guess in \
                "$HOME/Desktop/Auto-claude-code-research-in-sleep" \
                "$HOME/Auto-claude-code-research-in-sleep" \
                "$HOME/aris_repo" \
                "$HOME/.copilot/Auto-claude-code-research-in-sleep"; do
                if [[ -d "$guess/skills" && -f "$guess/AGENT_GUIDE.md" ]]; then
                    p="$(abs_path "$guess")"
                    break
                fi
            done
        fi
    fi
    [[ -n "${p:-}" ]] || die "cannot find ARIS repo with skills/. Use --aris-repo PATH."
    [[ -d "$p/skills" ]] || die "repo missing skills/ directory: $p"
    echo "$p"
}

build_upstream_inventory() {
    local repo="$1" out="$2"
    local skills_dir="$repo/skills"
    local d name
    : > "$out"

    for d in "$skills_dir"/*/; do
        [[ -d "$d" ]] || continue
        name="$(basename "$d")"
        # Skip Codex-specific packages and shared-references (support dir handled separately)
        if [[ "$name" =~ ^($SKIP_DIRS)$ ]]; then
            continue
        fi
        is_safe_name "$name" || { warn "skipping unsafe upstream name: $name"; continue; }
        if [[ -f "$d/SKILL.md" ]]; then
            printf "skill|%s|skills/%s\n" "$name" "$name" >> "$out"
        fi
    done

    # Include shared-references as a support directory
    if [[ -d "$skills_dir/shared-references" ]]; then
        printf "support|shared-references|skills/shared-references\n" >> "$out"
    fi

    [[ -s "$out" ]] || die "upstream inventory empty"
    sort -t'|' -k2,2 -o "$out" "$out"
}

# --- Selective install (#366, ported from install_aris.sh) ---
# Upstream rows are 3-field (kind|name|source_rel); catalog skill names match
# these mainline skill names 1:1.

catalog_ok() { [[ -n "${CATALOG_PATH:-}" && -f "$CATALOG_PATH" ]]; }
catalog_groups() { awk -F'\t' '$1=="group"{print $2 "\t" $3 "\t" $4}' "$CATALOG_PATH"; }
catalog_group_of() { awk -F'\t' -v s="$1" '$1=="skill" && $2==s {print $3; exit}' "$CATALOG_PATH"; }
catalog_desc_of() { awk -F'\t' -v s="$1" '$1=="skill" && $2==s {print (NF>=5?$5:""); exit}' "$CATALOG_PATH"; }
catalog_requires() { awk -F'\t' -v s="$1" '$1=="skill" && $2==s && $4!="-" {print $4; exit}' "$CATALOG_PATH" | tr ',' '\n'; }
catalog_skills_in_group() { awk -F'\t' -v g="$1" '$1=="skill" && $3==g {print $2}' "$CATALOG_PATH"; }
catalog_has_skill() { awk -F'\t' -v s="$1" '$1=="skill" && $2==s {found=1; exit} END{exit !found}' "$CATALOG_PATH"; }

in_file() { grep -qxF "$1" "$2" 2>/dev/null; }
upstream_has_skill() { grep -q "^skill|$1|" "$2"; }

print_group_catalog() {
    catalog_ok || die "skill catalog not found: ${CATALOG_PATH:-<unset>}"
    echo "Skill groups (from $CATALOG_PATH):"
    local gid display desc n
    while IFS=$'\t' read -r gid display desc; do
        n=$(catalog_skills_in_group "$gid" | wc -l | tr -d ' ')
        printf "\n  %-14s %s — %s  [%s skills]\n" "$gid" "$display" "$desc" "$n"
        catalog_skills_in_group "$gid" | sed 's/^/      /'
    done < <(catalog_groups)
}

load_declined() {  # $1 = out file
    : > "$1"
    [[ -f "$DECLINED_PATH" ]] || return 0
    grep -v '^[[:space:]]*$' "$DECLINED_PATH" >> "$1" || true
}

save_declined() {  # $1 = candidates file, $2 = selected file
    $DRY_RUN && return 0
    mkdir -p "$PROJECT_ARIS_DIR"
    local tmp="$DECLINED_PATH.tmp.$$"
    sort -u "$1" | grep -v '^$' | grep -vxF -f "$2" > "$tmp" || true
    if [[ -s "$tmp" || -f "$DECLINED_PATH" ]]; then
        mv -f "$tmp" "$DECLINED_PATH"
    else
        rm -f "$tmp"
    fi
}

# Auto-include hard pipeline deps (catalog `requires` column, transitively).
expand_deps() {  # $1 = selected file, $2 = excludes file, $3 = upstream file
    catalog_ok || return 0
    local changed=1 name dep
    while (( changed )); do
        changed=0
        for name in $(cat "$1"); do
            for dep in $(catalog_requires "$name"); do
                in_file "$dep" "$1" && continue
                if in_file "$dep" "$2"; then
                    warn "'$name' requires '$dep' but it is excluded — that pipeline phase will break"
                    continue
                fi
                upstream_has_skill "$dep" "$3" || continue
                echo "$dep" >> "$1"
                log "  ↳ auto-including '$dep' (required by '$name')"
                changed=1
            done
        done
    done
}

# Interactive selection (fresh install on a TTY, no selection flags).
# Preferred UI: full-screen checkbox picker (tools/skill_picker.py, curses) —
# Space toggles a skill / a whole group, Enter confirms, q aborts. Falls back
# to the classic per-group Y/n/e prompts when python3/curses/tty are
# unavailable or ARIS_NO_PICKER=1 is set.
interactive_select() {  # $1 = upstream file, $2 = out (selected) file
    if [[ "${ARIS_NO_PICKER:-0}" != "1" ]] && command -v python3 >/dev/null 2>&1 \
       && [[ -f "$ARIS_REPO/tools/skill_picker.py" ]]; then
        local avail_f rc=0
        avail_f="$(mktemp -t aris-avail.XXXX)"
        grep '^skill|' "$1" | cut -d'|' -f2 > "$avail_f" || true
        python3 "$ARIS_REPO/tools/skill_picker.py" \
            --catalog "$CATALOG_PATH" --available "$avail_f" --out "$2" \
            </dev/tty >/dev/tty || rc=$?
        rm -f "$avail_f"
        if [[ $rc -eq 0 ]]; then return 0
        elif [[ $rc -eq 1 ]]; then die "interactive selection aborted"
        fi
        # rc=2 (or unexpected): picker unusable — fall through to prompts.
        warn "checkbox picker unavailable — using per-group prompts"
    fi
    log ""
    log "Interactive skill selection — per group: Y=install all, n=skip, e=pick per skill."
    local gid display desc n reply r2 name glist
    glist="$(mktemp -t aris-copilot-glist.XXXX)"
    while IFS=$'\t' read -r gid display desc; do
        catalog_skills_in_group "$gid" | while read -r name; do
            upstream_has_skill "$name" "$1" && echo "$name"
        done > "$glist" || true
        n=$(wc -l < "$glist" | tr -d ' ')
        (( n == 0 )) && continue
        printf "\n%s (%s) — %s\n" "$display" "$gid" "$desc" >&2
        sed 's/^/    /' "$glist" >&2
        printf "Install group '%s' (%s skills)? [Y/n/e] " "$gid" "$n" >&2
        read -r reply </dev/tty
        case "$reply" in
            [nN]*) : ;;
            [eE]*)
                while read -r name; do
                    printf "  install %-30s [Y/n] " "$name" >&2
                    read -r r2 </dev/tty
                    [[ "$r2" =~ ^[nN] ]] || echo "$name" >> "$2"
                done < "$glist"
                ;;
            *) cat "$glist" >> "$2" ;;
        esac
    done < <(catalog_groups)
    # Upstream skills the catalog doesn't know yet (catalog drift): never drop silently.
    local ungrouped; ungrouped="$(mktemp -t aris-copilot-ungrouped.XXXX)"
    grep '^skill|' "$1" | cut -d'|' -f2 | while read -r name; do
        catalog_has_skill "$name" || echo "$name"
    done > "$ungrouped" || true
    if [[ -s "$ungrouped" ]]; then
        printf "\nSkills not in the catalog yet:\n" >&2
        sed 's/^/    /' "$ungrouped" >&2
        while read -r name; do
            printf "  install %-30s [Y/n] " "$name" >&2
            read -r r2 </dev/tty
            [[ "$r2" =~ ^[nN] ]] || echo "$name" >> "$2"
        done < "$ungrouped"
    fi
    rm -f "$glist" "$ungrouped"
}

# Validate --groups/--skills names against catalog + upstream.
validate_selection_flags() {  # $1 = upstream file
    local g s
    if [[ -n "$SELECT_GROUPS" ]]; then
        catalog_ok || die "--groups needs the catalog at $CATALOG_PATH (update your aris-repo clone)"
        for g in $(echo "$SELECT_GROUPS" | tr ',' ' '); do
            catalog_groups | cut -f1 | grep -qxF "$g" \
                || die "unknown group '$g' — run with --list-groups to see valid ids"
        done
    fi
    for s in $(echo "$SELECT_SKILLS" | tr ',' ' '); do
        upstream_has_skill "$s" "$1" || die "unknown skill '$s' (not an upstream skill)"
    done
}

# Build the selected-skill set (one name per line in $3).
build_selection() {  # $1 = upstream file, $2 = declined-candidates out file, $3 = selected out file
    local upstream="$1" declined_out="$2" out="$3"
    : > "$out"
    load_declined "$declined_out"

    local excl; excl="$(mktemp -t aris-copilot-excl.XXXX)"
    echo "$EXCLUDE_SKILLS" | tr ',' '\n' | grep -v '^$' > "$excl" || true
    cat "$excl" >> "$declined_out"

    validate_selection_flags "$upstream"

    local has_selection_flags=false
    [[ -n "$SELECT_GROUPS$SELECT_SKILLS" ]] && has_selection_flags=true
    local fresh=true
    [[ -f "$MANIFEST_PATH" ]] && fresh=false

    local name g subset_choice=false
    if $fresh; then
        if $SELECT_ALL || { ! $has_selection_flags && { $QUIET || [[ ! -t 0 ]]; }; }; then
            grep '^skill|' "$upstream" | cut -d'|' -f2 > "$out"
        elif $has_selection_flags; then
            subset_choice=true
            for g in $(echo "$SELECT_GROUPS" | tr ',' ' '); do
                catalog_skills_in_group "$g" | while read -r name; do
                    upstream_has_skill "$name" "$upstream" && echo "$name"
                done >> "$out" || true
            done
            echo "$SELECT_SKILLS" | tr ',' '\n' | grep -v '^$' >> "$out" || true
        elif catalog_ok; then
            subset_choice=true
            interactive_select "$upstream" "$out"
        else
            warn "catalog missing at $CATALOG_PATH — falling back to full install"
            grep '^skill|' "$upstream" | cut -d'|' -f2 > "$out"
        fi
        # Explicit subset choice ⇒ remember the rest as declined (won't re-ask).
        if $subset_choice; then
            grep '^skill|' "$upstream" | cut -d'|' -f2 | grep -vxF -f "$out" >> "$declined_out" 2>/dev/null || true
        fi
    else
        # Reconcile: installed set = manifest ∩ upstream (auto-detected).
        manifest_names "$MANIFEST_DATA" | while read -r name; do
            [[ "$(manifest_kind_of "$MANIFEST_DATA" "$name")" == "skill" ]] || continue
            upstream_has_skill "$name" "$upstream" && echo "$name"
        done >> "$out" || true
        # Flag-based additions re-enable previously declined skills.
        for g in $(echo "$SELECT_GROUPS" | tr ',' ' '); do
            catalog_skills_in_group "$g" | while read -r name; do
                upstream_has_skill "$name" "$upstream" && echo "$name"
            done >> "$out" || true
        done
        echo "$SELECT_SKILLS" | tr ',' '\n' | grep -v '^$' >> "$out" || true
        # NEW upstream skills: not installed, not declined, not just selected.
        local new_file; new_file="$(mktemp -t aris-copilot-new.XXXX)"
        grep '^skill|' "$upstream" | cut -d'|' -f2 | while read -r name; do
            in_file "$name" "$out" && continue
            in_file "$name" "$declined_out" && continue
            echo "$name"
        done > "$new_file" || true
        if [[ -s "$new_file" ]]; then
            if $SELECT_ALL || [[ "$NEW_POLICY" == "add" ]]; then
                cat "$new_file" >> "$out"
                log "→ adding $(wc -l < "$new_file" | tr -d ' ') new upstream skill(s) (--all/--add-new)"
            elif [[ "$NEW_POLICY" == "skip" ]] || $QUIET || [[ ! -t 0 ]]; then
                log ""
                log "New upstream skills NOT installed (rerun without --skip-new/--quiet to be asked,"
                log "or pass --add-new / --skills NAME):"
                sed 's/^/    /' "$new_file" | while read -r l; do log "$l"; done
            else
                log ""
                log "New skills appeared upstream since your last install:"
                local reply grp sdesc
                while read -r name; do
                    grp="$(catalog_group_of "$name")"
                    sdesc="$(catalog_desc_of "$name")"
                    printf "  install new skill %-30s (group: %s)%s [y/N] " "$name" "${grp:-?}" "${sdesc:+ — $sdesc}" >&2
                    read -r reply </dev/tty
                    if [[ "$reply" =~ ^[yY] ]]; then echo "$name" >> "$out"
                    else echo "$name" >> "$declined_out"
                    fi
                done < "$new_file"
            fi
        fi
        rm -f "$new_file"
    fi

    # Excludes beat every other source (manifest, groups, deps, new skills).
    local pruned
    if [[ -s "$excl" ]]; then
        pruned="$(mktemp -t aris-copilot-pruned.XXXX)"
        grep -vxF -f "$excl" "$out" > "$pruned" || true
        mv -f "$pruned" "$out"
    fi
    expand_deps "$out" "$excl" "$upstream"
    sort -u -o "$out" "$out"
    rm -f "$excl"
    [[ -s "$out" ]] || die "selection is empty — nothing to install (use --all or --groups/--skills)"
}

# Keep support entries + selected skills only (upstream rows stay 3-field).
filter_upstream_by_selection() {  # $1 = upstream file, $2 = selected file, $3 = out
    awk -F'|' -v sel="$2" '
        BEGIN { while ((getline line < sel) > 0) picked[line]=1 }
        $1=="support" { print; next }
        $1=="skill" && picked[$2] { print }
    ' "$1" > "$3"
}

# Layer-4 helper resolution (#366): a global pointer file lets globally/copy-
# installed skills find $ARIS_REPO/tools without a per-project install.
ensure_global_pointer() {
    $DRY_RUN && return 0
    mkdir -p "$(dirname "$GLOBAL_POINTER")" 2>/dev/null || { warn "cannot create $(dirname "$GLOBAL_POINTER") — skipping global pointer"; return 0; }
    local cur=""
    [[ -f "$GLOBAL_POINTER" ]] && cur="$(cat "$GLOBAL_POINTER" 2>/dev/null || true)"
    [[ "$cur" == "$ARIS_REPO" ]] && return 0
    printf '%s\n' "$ARIS_REPO" > "$GLOBAL_POINTER.tmp.$$" && mv -f "$GLOBAL_POINTER.tmp.$$" "$GLOBAL_POINTER"
    log "  + global pointer $GLOBAL_POINTER -> $ARIS_REPO"
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
manifest_names() { awk -F'\t' '{print $2}' "$1"; }
manifest_kind_of() { awk -F'\t' -v n="$2" '$2==n {print $1; exit}' "$1"; }

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
LEGACY_NESTED="$PROJECT_PATH/.github/skills/aris"
CATALOG_PATH="$ARIS_REPO/$CATALOG_REL"
DECLINED_PATH="$PROJECT_ARIS_DIR/$DECLINED_NAME"

if $LIST_GROUPS; then
    print_group_catalog
    exit 0
fi

check_no_symlinked_parents() {
    local p
    for p in "$PROJECT_ARIS_DIR" "$PROJECT_PATH/.github" "$PROJECT_SKILLS_DIR"; do
        if is_symlink "$p"; then
            die "$p is a symlink; refusing to mutate symlinked parent directories"
        fi
    done
}

check_legacy_nested_install() {
    if [[ -e "$LEGACY_NESTED" || -L "$LEGACY_NESTED" ]]; then
        die "legacy nested install detected at $LEGACY_NESTED. Remove it before using the flat .github/skills/<name> layout."
    fi
}

write_lock_metadata() {
    cat > "$LOCK_DIR/owner.json" <<EOF
{"host":"$(hostname)","pid":$$,"started_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","tool":"install_aris_copilot.sh"}
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
    die "another install_aris_copilot.sh appears to be running (lock: $LOCK_DIR, owner: $owner)"
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

    # Detect removals: entries in manifest but not in upstream
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
        printf "installer\tinstall_aris_copilot.sh\n"
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
                    log "  ~ $name"
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
    local count new_block new_content tmp current
    count="$(wc -l < "$installed_names_file" | tr -d ' ')"
    local repo_lookup_cmd
    repo_lookup_cmd="ARIS_REPO=\$(awk -F'\\t' '\$1==\"repo_root\"{print \$2; exit}' \"$PROJECT_PATH/$ARIS_DIR_NAME/$MANIFEST_NAME\")"
    new_block="$BLOCK_BEGIN
## ARIS Copilot CLI Skill Scope
ARIS mainline skills installed in this project for GitHub Copilot CLI.
Managed entries: $count
Manifest: \`$ARIS_DIR_NAME/$MANIFEST_NAME\`
ARIS repo root: \`$ARIS_REPO\`
Project skill path: \`$SKILLS_REL/<skill-name>\`
For ARIS workflows, prefer the project-local skills under \`$SKILLS_REL/\`.
When a skill needs ARIS helper scripts, resolve the repo root from the manifest or set it explicitly:
\`$repo_lookup_cmd\`
Do not edit or delete symlinked skills in place; update upstream or rerun:
\`bash $ARIS_REPO/tools/install_aris_copilot.sh \"$PROJECT_PATH\" --reconcile\`
For copied installs, use:
\`bash $ARIS_REPO/tools/smart_update_copilot.sh --project \"$PROJECT_PATH\"\`
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
    sys.stderr.write("ARIS-COPILOT:WARN multiple managed blocks found; skipping update\n")
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

    tmp="$DOC_FILE.aris-copilot-tmp.$$"
    printf '%s' "$new_content" > "$tmp"
    current=""
    [[ -f "$DOC_FILE" ]] && current="$(cat "$DOC_FILE")"
    if [[ "$current" != "$original" ]]; then
        rm -f "$tmp"
        warn "AGENTS.md changed during install; skipping managed block update"
        return 0
    fi
    mv -f "$tmp" "$DOC_FILE"
    log "  updated AGENTS.md"
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
    sys.stderr.write("ARIS-COPILOT:WARN multiple managed blocks found; skipping removal\n")
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

    tmp="$DOC_FILE.aris-copilot-tmp.$$"
    printf '%s' "$new_content" > "$tmp"
    current="$(cat "$DOC_FILE")"
    if [[ "$current" != "$original" ]]; then
        rm -f "$tmp"
        warn "AGENTS.md changed during uninstall; skipping managed block removal"
        return 0
    fi
    mv -f "$tmp" "$DOC_FILE"
    log "  removed AGENTS.md managed block"
}

do_uninstall() {
    [[ -f "$MANIFEST_PATH" ]] || die "no manifest at $MANIFEST_PATH; nothing to uninstall"
    local manifest_data
    manifest_data="$(mktemp -t aris-copilot-manifest.XXXX)"
    load_manifest "$MANIFEST_PATH" "$manifest_data"
    log ""
    log "Uninstall plan:"
    while IFS=$'\t' read -r kind name _source _target _mode; do
        [[ -z "$name" ]] && continue
        log "  - $name ($kind)"
    done < "$manifest_data"
    if ! $DRY_RUN; then
        prompt "Proceed? [y/N]" || { log "aborted"; exit 0; }
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
        log "  uninstalled (manifest preserved as $MANIFEST_PREV)"
    fi
    remove_agents_doc_block
}

# --- Main ---
log ""
log "ARIS Copilot CLI Project Install"
log "  Project:   $PROJECT_PATH"
log "  Repo:      $ARIS_REPO"
log "  Target:    $SKILLS_REL/"
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

UPSTREAM_FILE="$(mktemp -t aris-copilot-upstream.XXXX)"
build_upstream_inventory "$ARIS_REPO" "$UPSTREAM_FILE"

MANIFEST_DATA="$(mktemp -t aris-copilot-manifest.XXXX)"
load_manifest "$MANIFEST_PATH" "$MANIFEST_DATA"

# Selective install (#366): build the selected set, then plan against it.
SELECTED_FILE="$(mktemp -t aris-copilot-selected.XXXX)"
DECLINED_CANDIDATES="$(mktemp -t aris-copilot-declined.XXXX)"
build_selection "$UPSTREAM_FILE" "$DECLINED_CANDIDATES" "$SELECTED_FILE"
SELECTED_UPSTREAM="$(mktemp -t aris-copilot-upstream-sel.XXXX)"
filter_upstream_by_selection "$UPSTREAM_FILE" "$SELECTED_FILE" "$SELECTED_UPSTREAM"
N_SELECTED=$(grep -c '^skill|' "$SELECTED_UPSTREAM" || true)
N_UPSTREAM=$(grep -c '^skill|' "$UPSTREAM_FILE" || true)
log ""
log "Selection: $N_SELECTED of $N_UPSTREAM upstream skills"

PLAN_FILE="$(mktemp -t aris-copilot-plan.XXXX)"
compute_plan "$SELECTED_UPSTREAM" "$MANIFEST_DATA" "$PLAN_FILE"
print_plan "$PLAN_FILE"

if grep -q '^CONFLICT|' "$PLAN_FILE"; then
    die "aborting due to unresolved conflicts. Use --replace-link NAME for a symlink you want to replace."
fi

if $DRY_RUN; then
    log ""
    log "(dry-run) no changes made"
    rm -f "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE" "$SELECTED_FILE" "$SELECTED_UPSTREAM" "$DECLINED_CANDIDATES"
    exit 0
fi

N_CHANGES="$(awk -F'|' '$1=="CREATE"||$1=="UPDATE_TARGET"||$1=="REMOVE"{n++} END{print n+0}' "$PLAN_FILE")"
if (( N_CHANGES > 0 )); then
    prompt "Apply these $N_CHANGES changes? [y/N]" || { log "aborted"; exit 0; }
fi

MANIFEST_TMP="$MANIFEST_PATH.tmp.$$"
write_manifest_tmp "$PLAN_FILE" "$MANIFEST_TMP"
log ""
log "Applying:"
apply_plan "$PLAN_FILE"
commit_manifest "$MANIFEST_TMP"

# #366: persist declined skills + global repo pointer (best-effort, after
# manifest commit for the same reason as install_aris.sh).
save_declined "$DECLINED_CANDIDATES" "$SELECTED_FILE"
ensure_global_pointer

INSTALLED_NAMES="$(mktemp -t aris-copilot-names.XXXX)"
awk -F'|' '$1=="REUSE"||$1=="ADOPT"||$1=="CREATE"||$1=="UPDATE_TARGET"{print $3}' "$PLAN_FILE" > "$INSTALLED_NAMES"
update_agents_doc "$INSTALLED_NAMES"

# Post-install verification
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
    (( local_bad == 0 )) && log "" && log "Copilot CLI install complete. $N_CHANGES changes applied."
fi

rm -f "$UPSTREAM_FILE" "$MANIFEST_DATA" "$PLAN_FILE" "$INSTALLED_NAMES" "$SELECTED_FILE" "$SELECTED_UPSTREAM" "$DECLINED_CANDIDATES"
