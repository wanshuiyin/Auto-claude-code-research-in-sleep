# `skills-codex`

Codex-native mirror and adaptation layer for the main ARIS `skills/` package.

## Scope

- Base mirror coverage: all `87` mainline skills under `skills/`
- Support directory: `shared-references/`, with all `30/30` mainline reference names mirrored
- Default reviewer contract for reviewer-heavy skills:
  - round 1: `spawn_agent`
  - follow-up: `send_input`
  - model: `gpt-6-astra`; deep reviews: `ultra`, regular reviews: `xhigh`
  - base Codex self-review: `review_independence: same-family`,
    `acceptance_status: provisional`
  - other reviewers: select a backend in the full pack; acceptance depends on actual model identities, completed review scope, and the applicable gate

This package is still an appendage to the Claude mainline, not a separate Codex-first product line.

## Recommended Install

Project-local install is the default path for Codex:

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo
cd ~/your-project

bash ~/aris_repo/tools/install_aris_codex.sh .
```

This creates a flat managed layout:

```text
.agents/skills/<skill-name> -> ~/aris_repo/skills/skills-codex/<skill-name>
.aris/installed-skills-codex.txt
AGENTS.md   # managed Codex block
```

Reconcile after upstream changes:

```bash
cd ~/aris_repo && git pull
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile
```

Uninstall only managed Codex entries:

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --uninstall
```

## Goal Pulse for Codex Goals

When the user starts or resumes a Goal, or the main agent takes over an active
Goal, the main agent reads and enables [HERO Goal Pulse](https://github.com/wanshuiyin/HERO-Anti-OverDefense/tree/main/skills/goal-pulse)
for that thread by default, without a separate request or confirmation. First read
the installed `${CODEX_HOME:-~/.codex}/skills/goal-pulse/SKILL.md`; if missing, follow
HERO's public installation guide to prepare the skill and dependencies if missing;
report any setup blocker instead of claiming reminders are running. HERO maintains
the single implementation, outside ARIS's 87-skill pack. Project-local installs
receive the activation instructions through ARIS's managed `AGENTS.md` block.
For a global copied installation, follow HERO's guide once to add its persistent
`AGENTS.md` activation block; Goals then trigger it by default.

Use `CODEX_THREAD_ID` or an explicit thread ID supplied by the host; never infer
the current thread from the most recent session. Follow the installed skill's
start/status/stop commands. Defaults are bilingual reminders every 30 minutes and
read-only local-state polling every 60 seconds, on compatible Codex app-server
setups on macOS/Linux. Reminders stay within the bound thread, remain silent while
the Goal is paused, waiting for user input/approval, blocked, or budget-limited,
and exit when it is completed, deleted, or replaced. Preserve an explicit user
disable or pause; the timer never resumes a Goal or starts a new turn.

The managed `AGENTS.md` block instructs the main agent to do this; it is not a
native Codex lifecycle hook. Installing ARIS and ordinary chat do not start the
timer. The ARIS installer only writes its managed block; it does not download HERO
or restart Codex. Reviewer and writing-worker selection are unchanged.

## Session handoff for a fresh context

Use [HERO Session Handoff](https://github.com/wanshuiyin/HERO-Anti-OverDefense/tree/main/skills/session-handoff)
when you want to carry current work into a fresh session. Follow HERO's
installation instructions; the same Markdown skill serves Codex and Claude Code
and stays outside ARIS's skill inventory and installer.

In Codex, ask `$session-handoff prepare for a fresh session; reuse NEXT_SESSION.md`.
The skill checks current artifacts and active work, updates the existing recovery
entrypoint, and returns a starting prompt. Manually open a fresh session in the
intended workspace and paste that prompt, or ask `$session-handoff continue from
NEXT_SESSION.md`. In Claude Code, use `/session-handoff` with the same natural
parameters. Replace `NEXT_SESSION.md` with your actual recovery entrypoint;
omit the path when preparing a project’s first handoff.

The new session reuses completed evidence, checks live jobs and ownership, and
continues authorized work. Goal binding and budgets remain with the host; a
handoff does not transfer them or resume a paused Goal. Existing Pipeline Status,
research contracts, and workflow checkpoints remain the sources of state. Keep
`AGENTS.md` limited to a short pointer to the recovery entrypoint. Detailed usage
is in the [recovery guide](../../docs/SESSION_RECOVERY_GUIDE.md#prepare-a-fresh-session-with-hero).

## Select a Reviewer

Use the complete pack with [selectable reviewers](shared-references/reviewer-backends.md).
For one invocation, add `— reviewer: antigravity` (or `grok`, `claude-code`,
`codex`). For a project default, create `.aris/reviewer.json` yourself:

```json
{"backend": "antigravity", "model": "gemini-4-argon-high", "effort": "high"}
```

Register the selected backend's MCP separately as described in the linked
contract. `claude-code` uses the CLI's configured provider and accepts no effort
override. Selecting a transport does not by itself establish cross-family review
or acceptance. The legacy `agy` route still uses `gemini-review`; it is distinct
from `antigravity`.

## Migrate Frozen Partial Overlays

`skills-codex-claude-review/` and `skills-codex-gemini-review/` are frozen legacy
snapshots. Their directories and existing links remain available, but base skill
changes no longer regenerate them. New installations should use the full pack.
The old overlay install flags remain for compatibility, not ongoing feature sync.

For **managed project symlinks**, first inspect `.agents/skills/<name>` with
`readlink` and save `.aris/installed-skills-codex.txt` plus any customized source
files. Editing a symlinked skill edits its repository target; preserve those
changes before switching. Preview reconciliation without either overlay flag:

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile --dry-run
```

Check that the planned retargets point to `skills/skills-codex/`, then run the same
command without `--dry-run`. Real directories are conflicts and are not replaced.
For an unmanaged overlay link, inspect it and use `--replace-link <skill-name>`
only for that specific link, previewing first. Keep the overlay directories;
merge relevant personal edits into your chosen full-pack source deliberately.

For **global copied skills** in `~/.codex/skills/`, back up the affected skill
directories outside that discovery directory. Compare each installed overlay
skill with its frozen source and the corresponding full-pack skill, preserving
personal edits separately. Stage the full-pack replacements in a temporary
directory, reapply those edits, and inspect the result before replacing only the
reviewed installed directories. Do not copy an entire overlay over the full pack
or bulk overwrite existing skills. Then set the project reviewer configuration
and register its bridge. No migration command here writes global settings
automatically; restart Codex after installation changes so it reloads the pack.

## Copy Install and Update

If you intentionally use a copied Codex install instead of managed project symlinks:

```bash
mkdir -p ~/.codex/skills
cp -a ~/aris_repo/skills/skills-codex/. ~/.codex/skills/
```

Update copied installs with:

```bash
bash ~/aris_repo/tools/smart_update_codex.sh
bash ~/aris_repo/tools/smart_update_codex.sh --apply
```

For a copied project-local Codex install:

```bash
bash ~/aris_repo/tools/smart_update_codex.sh --project ~/your-project
bash ~/aris_repo/tools/smart_update_codex.sh --project ~/your-project --apply
```

`smart_update_codex.sh` refuses symlink-managed installs and redirects them to `install_aris_codex.sh --reconcile`.

## Non-Degrading Skills

The following Codex skills must not silently degrade when their required capability is missing:

- `comm-lit-review`
- `research-lit`
- `paper-poster-html`
- `pixel-art`

If the required source, reviewer, or local preview capability is unavailable, the skill should stop and tell the user what to configure.
