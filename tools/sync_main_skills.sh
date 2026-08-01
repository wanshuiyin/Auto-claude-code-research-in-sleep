#!/usr/bin/env bash
# tools/sync_main_skills.sh — v0.4.22
#
# Syncs the skills/ + tools/ subset from origin/main into
# crates/runtime/assets/ so the binary bundle stays aligned with the
# skills source-of-truth on main.
#
# Per idea-stage/v0.4.11/sync_plan.md, idea-stage/v0.4.13/plan.md and
# idea-stage/v0.4.22/design.md:
# - Excludes skills-codex* mirror directories (codex agent install path,
#   not user-facing). build.rs already excludes them via
#   EXCLUDED_SKILL_PREFIXES; rsync exclude is double-defense.
# - Bundles 29 runtime helpers from tools/ (9 baseline refresh + 9 v0.4.11
#   additions + 2 v0.4.13 meta_opt hooks + 8 v0.4.22 additions + 1 v0.4.23
#   forensics gate).
#   `install_aris*` / `smart_update*` / `lint_skills_helpers.sh` etc. stay
#   out of the binary.
# - v0.4.13 introduced `meta_opt/{log_event,check_ready}.sh` so `aris init`
#   can deploy them as Claude Code hooks under `~/.claude/hooks/`.
# - v0.4.22 adds the 8 helpers newly referenced by synced SKILL.md files
#   (capture_filter/evidence_check/iteration_log/provenance/run_state/
#   threat_scan + meta_opt/trigger_eval.py + its sample eval file).
# - Aborts on any symlink under main's skills/ or tools/ (build.rs panics).
#
# Usage:
#   bash tools/sync_main_skills.sh
#   # Optional: pin the expected main SHA — the sync aborts BEFORE touching
#   # assets/ if origin/main resolved to anything else:
#   ARIS_SYNC_EXPECT_SHA=<sha> bash tools/sync_main_skills.sh
#
# After sync:
#   cargo build --release          # see "Embedded N skills, M helpers"
#   cargo test -p runtime          # drift tests pass
#   ./target/release/aris --version

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# v0.4.11 sync uses a per-pid temporary worktree path so concurrent runs
# never collide and stale worktrees from a previous aborted run are not
# silently reused.
WORKTREE="/tmp/aris-main-sync-$$"

cleanup() {
    # Best-effort cleanup. Don't fail the script if worktree was already
    # removed or never created.
    if [[ -d "$WORKTREE" ]]; then
        git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" 2>/dev/null || true
        rm -rf "$WORKTREE"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------
# Step 1: Pre-flight checks
# ---------------------------------------------------------------
echo "==> Pre-flight checks"

if [[ "${ARIS_SYNC_ALLOW_DIRTY:-0}" != "1" ]]; then
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "ERROR: working tree has uncommitted changes." >&2
        echo "Commit, stash, or revert first — sync will rewrite crates/runtime/assets/." >&2
        echo "(Set ARIS_SYNC_ALLOW_DIRTY=1 to bypass — used only for in-PR sync runs)" >&2
        exit 1
    fi
fi

# ---------------------------------------------------------------
# Step 2: Fetch + resolve main HEAD (race-safe form per codex round-3)
# ---------------------------------------------------------------
echo "==> Fetching origin/main"
# `main:refs/remotes/origin/main` updates the local remote-tracking ref
# atomically with the fetch, so the rev-parse below cannot race with
# another fetch that lands between these two commands.
git fetch --no-tags origin main:refs/remotes/origin/main

MAIN_SHA="$(git rev-parse refs/remotes/origin/main)"
echo "    origin/main = $MAIN_SHA"

# v0.4.22: optional SHA pin. When set, the sync refuses to proceed if
# origin/main resolved to a different commit — closes the race where main
# moves between the drift analysis and the sync run. Checked BEFORE any
# write to crates/runtime/assets/.
if [[ -n "${ARIS_SYNC_EXPECT_SHA:-}" && "$MAIN_SHA" != "$ARIS_SYNC_EXPECT_SHA" ]]; then
    echo "ERROR: origin/main is $MAIN_SHA but ARIS_SYNC_EXPECT_SHA=$ARIS_SYNC_EXPECT_SHA." >&2
    echo "main moved since your analysis — re-review the drift, then re-pin." >&2
    exit 1
fi
echo "    (verify this matches the SHA you expect before proceeding)"

# ---------------------------------------------------------------
# Step 3: Materialise main snapshot via temporary worktree
# ---------------------------------------------------------------
echo "==> Materialising main snapshot at $WORKTREE"

# Defensive: remove any pre-existing worktree at this path (could
# survive a previous run that crashed before trap fired).
git worktree remove --force "$WORKTREE" 2>/dev/null || true
rm -rf "$WORKTREE"

git worktree add --detach "$WORKTREE" "$MAIN_SHA"

# ---------------------------------------------------------------
# Step 4: Symlink guard (build.rs panics on any symlink)
# ---------------------------------------------------------------
echo "==> Symlink guard"

symlinks="$(find "$WORKTREE/skills" "$WORKTREE/tools" -type l 2>/dev/null || true)"
if [[ -n "$symlinks" ]]; then
    echo "ERROR: symlinks detected in main snapshot. build.rs would panic." >&2
    echo "$symlinks" >&2
    exit 1
fi

# ---------------------------------------------------------------
# Step 5: Skills full rsync, then explicit prune of mirrors
# ---------------------------------------------------------------
echo "==> Syncing skills/"

# Initial rsync. We do NOT use `--exclude='skills-codex*/'` here because
# macOS BSD rsync v2.6.9 silently ignores that pattern (verified during
# v0.4.11 implementation — codex agent mirrors leaked through). Instead
# we prune them deterministically below.
rsync -av --delete \
    --exclude='*.pyc' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    "$WORKTREE/skills/" \
    "$REPO_ROOT/crates/runtime/assets/skills/"

# Explicit prune: codex agent skill mirrors don't belong in the
# user-facing binary bundle. build.rs already excludes them via
# EXCLUDED_SKILL_PREFIXES, but removing here keeps assets/ clean and
# lets `git status` reflect the actual intended bundle.
echo "==> Pruning skills-codex* mirror directories"
SKILLS_CODEX_DIRS=(
    skills-codex
    skills-codex-claude-review
    skills-codex-gemini-review
)
for d in "${SKILLS_CODEX_DIRS[@]}"; do
    target="$REPO_ROOT/crates/runtime/assets/skills/$d"
    if [[ -d "$target" ]]; then
        rm -rf "$target"
        echo "  removed: $target"
    fi
done

# ---------------------------------------------------------------
# Step 6: Tools selective rsync (FULL 29 runtime helpers — codex round-3 #1, v0.4.13 +2, v0.4.22 +8, v0.4.23 +1)
# ---------------------------------------------------------------
echo "==> Syncing 29 runtime helpers from tools/"

# Codex round-3 #1 caught that the v0.4.8/0.4.9 helpers also drift on
# main (e.g. research_wiki.py went 315 -> 767 lines with the canonical
# ingest_paper API). Only syncing the 9 v0.4.11 additions would ship a
# bundle where new SKILL.md references a `research_wiki.py ingest_paper`
# API the bundled helper doesn't have yet.
#
# So the whitelist below covers the full runtime helper set:
#   - 9 baseline helpers (v0.4.8/0.4.9 era) — refresh from main
#   - 9 v0.4.11 additions — first time bundling
#   - 2 v0.4.13 meta_opt hooks — bundled so `aris init` can deploy them
#     to ~/.claude/hooks/ (see deploy_meta_opt_hooks in aris-cli main.rs).
#
# Explicitly NOT bundled (stay in main tools/ only):
#   - experiment_queue/README.md — doc, not runtime
#   - install_aris*.{sh,ps1}, smart_update*.{sh,ps1} — installer
#   - lint_skills_helpers.sh — CI/dev tool
#   - convert_skills_to_llm_chat.py — dev export tool
#   - generate_codex_claude_review_overrides.py — dev tool
RUNTIME_HELPERS=(
    # === baseline (already in v0.4.10 bundle — refresh in case main changed) ===
    arxiv_fetch.py
    deepxiv_fetch.py
    exa_search.py
    openalex_fetch.py
    research_wiki.py
    save_trace.sh
    semantic_scholar_fetch.py
    verify_paper_audits.sh
    verify_papers.py
    # === v0.4.11 additions (first-time bundle) ===
    extract_paper_style.py
    figure_renderer.py
    paper_illustration_image2.py
    overleaf_setup.sh
    overleaf_audit.sh
    verify_wiki_coverage.sh
    watchdog.py
    experiment_queue/build_manifest.py
    experiment_queue/queue_manager.py
    # === v0.4.13 additions: Claude Code hooks for meta-optimize ===
    meta_opt/log_event.sh
    meta_opt/check_ready.sh
    # === v0.4.22 additions: helpers newly referenced by synced SKILL.md ===
    # (research-wiki capture filter, result-to-claim evidence precheck,
    #  research-pipeline run-state/iteration-log, meta-apply/meta-optimize
    #  provenance jury gate, injection-hygiene threat scan, meta-optimize
    #  trigger-rate eval + its sample eval file)
    capture_filter.py
    evidence_check.py
    iteration_log.py
    provenance.py
    run_state.py
    threat_scan.py
    meta_opt/trigger_eval.py
    meta_opt/trigger_evals.sample.json
    # === v0.4.23 addition: integrity-forensics deterministic policy gate ===
    forensics_gate.py
)

for helper in "${RUNTIME_HELPERS[@]}"; do
    src="$WORKTREE/tools/$helper"
    if [[ ! -f "$src" ]]; then
        echo "ERROR: required runtime helper '$helper' missing in main tools/." >&2
        echo "Check audit_new_skills_and_helpers.md, or the helper was renamed/removed in main." >&2
        exit 1
    fi
    target="$REPO_ROOT/crates/runtime/assets/tools/$helper"
    mkdir -p "$(dirname "$target")"
    rsync -av "$src" "$target"
done

# NOTE: this script does NOT auto-prune assets/tools/ — the 29 helpers
# above are the complete intended bundle as of v0.4.23. A stale extra file
# is caught by the v0.4.22 exact-inventory test (asserts assets/tools has
# EXACTLY these 28 entries) on next `cargo test`.

# ---------------------------------------------------------------
# Step 7: Record source commit
# ---------------------------------------------------------------
echo "==> Writing SKILLS_SOURCE_COMMIT"
echo "$MAIN_SHA" > "$REPO_ROOT/crates/runtime/assets/SKILLS_SOURCE_COMMIT"

# ---------------------------------------------------------------
# Step 8: Cleanup is handled by trap. Final hint to the user.
# ---------------------------------------------------------------
echo
echo "==> Sync complete."
echo
echo "Next steps (run manually, in order):"
echo "  1. cargo build --release"
echo "     # confirm warning: Embedded 79 bundled skills, 103 helper resources"
echo "     # (second number counts ALL bundled resources, not just assets/tools)"
echo
echo "  2. cargo test -p runtime --lib cache -- --test-threads=1"
echo "     # all cache tests pass (incl. the 3 v0.4.11 drift tests + the"
echo "     # exact-inventory tests: 29 tools helpers, posterly MIT txt)"
echo
echo "  3. ./target/release/aris --version       # → 0.4.22 (or current after Cargo.toml bump)"
echo "  4. ./target/release/aris doctor          # smoke test"
echo
echo "  5. git diff --stat crates/runtime/assets/"
echo "     # quick visual on which skills changed"
