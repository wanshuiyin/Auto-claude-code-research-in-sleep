# `skills-codex`

Codex-native mirror and adaptation layer for the main ARIS `skills/` package.

## Scope

- Base mirror coverage: all `88` mainline skills under `skills/`
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
