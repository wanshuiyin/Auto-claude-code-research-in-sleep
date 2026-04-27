---
name: overleaf-sync
description: "Two-way sync between a local paper directory and an Overleaf project via the Overleaf Git bridge (Premium feature). Lets you keep ARIS audit/edit workflows on the local copy while collaborators edit in the Overleaf web UI. Token never touches the agent — user does the one-time auth via macOS Keychain. Use when user says \"同步 overleaf\", \"overleaf sync\", \"推送到 overleaf\", \"connect overleaf\", \"Overleaf 桥接\", \"pull overleaf\", \"push overleaf\", or wants to bridge their ARIS paper directory with an Overleaf project."
argument-hint: [setup <project-id> | pull | push | status]
allowed-tools: Bash(*), Read, Grep, Glob, Edit, Write
---

# Overleaf Sync

Bridge a local paper directory with an Overleaf project so that:

- **You** can keep editing in the Overleaf web UI (or share editing access with collaborators)
- **ARIS** can read your changes, run audits (`/paper-claim-audit`, `/citation-audit`, `/auto-paper-improvement-loop`), and push fixes back

This uses the official **Overleaf Git bridge** (Premium feature). The agent **never sees your authentication token** — you do the one-time auth manually so the token lives in macOS Keychain, not in chat history or `.git/config`.

## When to Use This Skill

- You want to use Overleaf as the editing surface (better collaboration, shared with team) but still run ARIS pipelines locally
- You want to take an existing local ARIS paper and push it to Overleaf for a co-author to edit
- A collaborator made changes in Overleaf and you want to pull + diff them before continuing local work

## Constants

- **CLONE_DIR_DEFAULT** = `paper-overleaf` (sibling of existing `paper/`, NOT inside `paper/`)
- **CREDENTIAL_HELPER** = `osxkeychain` (macOS) / `manager` (Windows) / `cache` (Linux fallback)
- **TOKEN_HANDLING** = **NEVER write token to disk, env var, or chat**. User pastes it once into the terminal credential prompt; the OS keychain stores it from then on.

## Architecture

```
┌─────────────────┐       git pull/push      ┌─────────────────┐
│  Local paper/   │ ◄─── rsync ──── ►       │ paper-overleaf/ │ ◄──► Overleaf web
│  (ARIS audits)  │                          │ (git bridge)    │     (collaborators)
└─────────────────┘                          └─────────────────┘
```

The `paper-overleaf/` directory is a **git clone of the Overleaf project**. The `paper/` directory is the working copy where ARIS skills run. They are kept in sync via `rsync`.

**Single-source-of-truth rule**: at any given time, treat *one* of them as authoritative for active editing. Switch directions explicitly with `pull` or `push`, and run a `status` check before either to surface unexpected divergence.

## Sub-commands

### `setup <project-id>` — one-time

Sets up the bridge for a new Overleaf project. **The user runs this in their own terminal, never through the agent.** The skill ships with a hardened setup script that:

1. Refuses to run unless stdin/stdout are a TTY (won't run inside an agent harness)
2. Reads the token from a hidden prompt (no chat history, no shell history)
3. Strips the token from the remote URL immediately after cloning
4. Primes the OS keychain so subsequent agent operations are auth-free
5. **Auto-installs a `pre-commit` hook in `paper-overleaf/.git/hooks/` that refuses to commit any blob containing the token pattern `olp_[A-Za-z0-9]{20,}`** — a hard technical block, not a behavioral rule

The agent's only role here is to print the user instruction:

```
Run this in your own terminal (NOT through me):

    bash <ARIS_REPO>/tools/overleaf_setup.sh <project-id-or-url>

When it finishes, tell me "setup done" and I'll verify.
```

After the user reports "setup done", the agent verifies (token-free):

```bash
cd paper-overleaf
git remote -v                    # must show URL WITHOUT token
git config --get credential.helper
git fetch && git log --oneline -3   # must succeed without prompting
ls .git/hooks/pre-commit         # must exist
bash <ARIS_REPO>/tools/overleaf_audit.sh .   # must report "Audit clean"
```

If `paper-overleaf/` exists but is empty (new Overleaf project), the agent then mirrors local `paper/` into it (see `push` workflow).

### `pull` — before each editing session

```bash
cd paper-overleaf && git pull --ff-only

# Show what changed since last pull
LAST=$(git rev-parse HEAD@{1})
git diff --stat $LAST..HEAD
git diff $LAST..HEAD -- 'sec/*.tex'        # detailed view for prose changes
```

**Diff protocol — DO NOT blindly merge into local `paper/`.** Overleaf edits frequently include:

- **Half-finished sentences** (collaborator clicked save mid-thought)
- **Typos** that aren't in canonical references (`Lrage` for `Large`)
- **Commented-out blocks** that may be intentional or may be a stash
- **Number changes** that should re-trigger `/paper-claim-audit`
- **Cite key changes** that should re-trigger `/citation-audit`

For each diff hunk, decide one of:

| Hunk character | Action |
|----------------|--------|
| Clean editorial improvement | Sync into `paper/`, no audit needed |
| Numerical / claim change | Sync, then re-run `/paper-claim-audit` |
| New `\cite{...}` | Sync, then re-run `/citation-audit` |
| Half-sentence / obvious typo | Flag to user, do NOT auto-sync |
| New section / restructure | Stop, ask user before syncing |

After deciding per-hunk:

```bash
# Sync only the files the user approved into local paper/
rsync -av paper-overleaf/sec/0.abstract.tex paper/sec/0.abstract.tex
# (or use Edit tool for surgical changes that skip half-sentences)
```

### `push` — after local editing

Use after ARIS skills have edited `paper/` and you want collaborators on Overleaf to see the changes.

```bash
# 1. Always pull first to surface remote drift
cd paper-overleaf && git pull --ff-only

# 2. If pull was a no-op, sync local paper → paper-overleaf
rsync -av --delete \
  --exclude='.git' --exclude='.DS_Store' \
  --exclude='*.aux' --exclude='*.log' --exclude='*.bbl' --exclude='*.blg' \
  --exclude='*.fls' --exclude='*.fdb_latexmk' --exclude='*.out' \
  --exclude='*.synctex.gz' --exclude='*.toc' \
  paper/ paper-overleaf/

# 3. Show what would be pushed
git status --short
git diff --stat

# 4. Commit + push
git add -A
git commit -m "<descriptive message — what ARIS changed and why>"
git push
```

**Commit message protocol**: include the ARIS skill that produced the change so collaborators on Overleaf understand provenance. Examples:

- `paper-write: regenerated sec/3.assurance after audit cascade refactor`
- `citation-audit: fix 14 metadata entries (madaan2023, lee2024, ...)`
- `paper-claim-audit: correct sec/5 numbers vs results/run_2026_04_19.json`

**Confirmation gate**: `push` writes to a shared resource. ALWAYS show the user `git diff --stat` (and a representative hunk for prose changes) before running `git push`. Wait for explicit confirmation unless the user said `auto: true` upfront.

### `status` — diagnostic

```bash
cd paper-overleaf
git fetch
echo "=== Remote-vs-local divergence ==="
git log --oneline HEAD..origin/master    # remote ahead
git log --oneline origin/master..HEAD    # local ahead
echo "=== paper/ vs paper-overleaf/ divergence ==="
diff -rq --brief paper/ paper-overleaf/ 2>/dev/null \
  | grep -v "Only in paper/.*\.\(aux\|log\|out\|fls\|fdb_latexmk\|bbl\|blg\|synctex\|toc\)" \
  | grep -v "Only in paper-overleaf/.git" \
  | grep -v "DS_Store"
```

Three-way state assessment:

| Remote ahead? | paper/ vs paper-overleaf/ differ? | Meaning | Recommended action |
|:-------------:|:---------------------------------:|---------|--------------------|
| No  | No  | Clean       | Nothing to do |
| Yes | No  | Overleaf has new edits | Run `pull`, then re-run status |
| No  | Yes | Local ARIS edits unsynced | Run `push` |
| Yes | Yes | Diverged — needs merge | Stop, surface to user, do NOT auto-resolve |

## Conflict Resolution

If `git pull --ff-only` fails because of true divergence:

1. **Do not** run `git pull` (which would auto-merge).
2. **Do not** run `git reset --hard` or `git push --force` (destructive).
3. Show the user `git log origin/master ^HEAD` (their Overleaf commits) and `git log HEAD ^origin/master` (local ARIS commits).
4. Ask the user which side to take per file, or to manually merge in Overleaf and then re-pull.

## Token Security — Defense in Depth

Behavioral rules alone are not enough — the next agent reading this skill might forget them. The skill therefore relies on **technical guards** that hold even if the agent misbehaves:

| Layer | Guard | Where enforced |
|-------|-------|---------------|
| 1. Setup | `overleaf_setup.sh` refuses to run without an interactive TTY (agents don't have one) | `tools/overleaf_setup.sh` |
| 2. Input | Token is read by `read -s` (hidden prompt, no shell history, never enters chat) | `tools/overleaf_setup.sh` |
| 3. Storage | Token goes straight into OS keychain via `git credential approve`; remote URL is stripped to a token-free form | `tools/overleaf_setup.sh` |
| 4. Commits | `paper-overleaf/.git/hooks/pre-commit` greps staged content for `olp_[A-Za-z0-9]{20,}` and aborts | auto-installed by setup script |
| 5. Audit | `overleaf_audit.sh` scans working tree, remote URLs, git history, credential files | `tools/overleaf_audit.sh` |

Behavioral rules (still apply, but secondary):

- **Never** ask the user to paste a token into chat. If they do anyway: (a) acknowledge it, (b) tell them to revoke it at https://www.overleaf.com/user/settings, (c) recover via keychain if already primed.
- **Never** write a token to a file (`.env`, `.netrc`, `tools/*.sh`, etc.) committed to any repo.
- **Never** include a token in a `git remote -v` URL — strip it after clone.
- On `401 Unauthorized` from push/pull, tell the user the keychain entry expired and to re-run `overleaf_setup.sh`. Do **not** ask for a fresh token.

## Mutual-Exclusion Rule

The single biggest source of pain in two-way sync is **simultaneous editing on both sides**.

- If the user is in an active Overleaf editing session, ARIS skills should **read-only** access `paper/` until the user runs `/overleaf-sync pull`.
- If ARIS is in the middle of `/auto-paper-improvement-loop` or `/paper-write`, the user should pause Overleaf editing until the loop finishes and `/overleaf-sync push` is run.

When in doubt, run `status` first.

## Output Contract

- `paper-overleaf/` directory at repo root, git clone of Overleaf project (origin URL has NO token)
- `paper/` directory unchanged in role — still the ARIS working copy
- Each `pull`/`push` operation: a one-line summary back to the user (commits pulled / pushed, file count, link to Overleaf project URL)

## See Also

- `/paper-claim-audit` — re-run after pulling Overleaf changes that touch numbers
- `/citation-audit` — re-run after pulling Overleaf changes that add/edit `\cite{...}`
- `/paper-compile` — local LaTeX build; Overleaf compiles independently in the cloud
- Overleaf Git bridge docs: https://www.overleaf.com/learn/how-to/Using_Git_and_GitHub
