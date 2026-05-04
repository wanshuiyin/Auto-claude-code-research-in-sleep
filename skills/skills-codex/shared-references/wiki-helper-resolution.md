# Wiki helper resolution chain (Codex mirror)

Codex-side resolution chain for `research_wiki.py`. Same purpose as the
CC mirror at `../shared-references/wiki-helper-resolution.md`, adapted
for Codex's install layout (the helper may live under
`~/.codex/skills/research-wiki/` for global installs).

## The chain

```bash
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
WIKI_SCRIPT=""
[ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/research_wiki.py" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"
[ -z "$WIKI_SCRIPT" ] && [ -f tools/research_wiki.py ] && WIKI_SCRIPT="tools/research_wiki.py"
[ -z "$WIKI_SCRIPT" ] && [ -f ~/.codex/skills/research-wiki/research_wiki.py ] && WIKI_SCRIPT="$HOME/.codex/skills/research-wiki/research_wiki.py"
```

After the chain:

- `[ -n "$WIKI_SCRIPT" ]` → helper located, use as `python3 "$WIKI_SCRIPT" <subcommand>`
- `[ -z "$WIKI_SCRIPT" ]` → helper missing; pick a variant below

## Variant A — hard-fail (for `/research-wiki` itself)

```bash
[ -n "$WIKI_SCRIPT" ] || {
  echo "ERROR: research_wiki.py not found. Set ARIS_REPO, copy to tools/, or use Codex global install." >&2
  exit 1
}
```

## Variant B — warn + skip (for caller skills)

```bash
[ -n "$WIKI_SCRIPT" ] || {
  echo "WARN: research_wiki.py not found. Primary output will still be produced; wiki update is skipped." >&2
}
```

After Variant B, every helper invocation must be guarded:

```bash
[ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ --arxiv-id "$id"
```

## Differences from the CC chain

| | CC | Codex |
|---|---|---|
| Manifest filename | `installed-skills.txt` | `installed-skills-codex.txt` |
| Symlink layer (`.aris/tools/...`) | yes (PR #174 / #192) | no — Codex install model is direct copy under `~/.codex/skills/`, no symlink |
| Global-install layer (`~/.codex/skills/<name>/...`) | no | yes |
| `cd "$(git rev-parse --show-toplevel)"` preamble | yes — guards subdir cwd | optional — Codex usually invokes from project root |

Outcome of both chains is the same: a populated `$WIKI_SCRIPT` env var
or an empty string + warning.

## See also

- [`integration-contract.md`](integration-contract.md) §2 — canonical-helper invariant
- `../research-wiki/SKILL.md` (Codex side) — uses Variant A
- CC-side mirror: `../../shared-references/wiki-helper-resolution.md`
