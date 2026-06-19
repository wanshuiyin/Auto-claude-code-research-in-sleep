---
name: wiki-enrich
description: "Fill in the per-paper TODO sections of research-wiki/papers/<slug>.md pages that literature-ingest skills leave as bare scaffolds. Use when user says 'enrich wiki', 'fill paper TODOs', 'wiki body 補完', '把 paper 摘要寫進 wiki', 'research-wiki 自動填', or after a batch ingest that left papers/ as TODO scaffolds."
argument-hint: "[target: slug|missing|all] [--source alphaxiv|deepxiv|arxiv|auto] [--force] [--max N]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, WebFetch
---

# Wiki Enrich: Fill Paper TODO Sections (Karpathy LLM-Wiki)

Target: **$ARGUMENTS**

## Why this skill exists

`ingest_paper` (called by `/research-lit`, `/arxiv`, `/alphaxiv`, `/deepxiv`, `/semantic-scholar`, `/exa-search`) only renders the per-paper scaffold — frontmatter + abstract + **10 fillable** `_TODO._` placeholder sections (plus two protected sections: `## Connections` is graph-summary and `## Abstract (original)` is auto-populated when `--arxiv-id` is given). No downstream skill in ARIS fills those 10 sections; the wiki sits as TODO until someone reads each paper.

This contradicts the Karpathy LLM-wiki design (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):

> "You never (or rarely) write the wiki yourself — the LLM writes and maintains all of it. … The tedious part of maintaining a knowledge base is not the reading or the thinking — it's the bookkeeping. … LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass."

`/wiki-enrich` is the missing back half of `ingest_paper`: it reads each scaffolded paper page, fetches paper content from external sources via a graceful fallback chain (see Phase 2.3 for the full 5-source chain), and rewrites the 10 fillable TODO sections into 1-3 sentence prose summaries.

## Constants

- **WIKI_ROOT = `research-wiki/`** — Resolved relative to git root. Skill hard-fails if not a directory.
- **TARGET_DEFAULT = `missing`** — When no target is given, enrich only papers with ≥1 TODO section. Other targets: `<slug>` (one paper) or `all` (every paper, even ones already enriched — usually combined with `--force` to overwrite).
- **SOURCE_DEFAULT = `auto`** — Fetch order: alphaxiv overview → alphaxiv abs → deepxiv brief → arXiv API abstract → page abstract fallback. First non-empty wins (full chain documented in Phase 2.3 table). Override with `--source` to pin one source.
- **MAX_PAPERS = 20** — Hard cap per invocation; LLMs touch many files but token budgets are real. Override with `--max N`.
- **FORCE = false** — When `false` (default), skip sections that already have non-TODO content. When `true`, overwrite every fillable section, but **never** touch the two protected sections: `## Connections` (auto-generated from `edges.jsonl`) and `## Abstract (original)` (immutable arXiv-fetched source data).
- **SECTIONS_TO_FILL** — 10 fillable sections + 2 protected. `ingest_paper` (`research_wiki.py:436-473`) scaffolds 11 section headers unconditionally and a 12th — `## Abstract (original)` — only when arXiv returns an abstract for the given `--arxiv-id` (`research_wiki.py:469-473`). Of these, 10 carry a `_TODO._` (or `_TODO: fill in after reading._`) marker and need filling. The other 2 — `## Connections` (position 10 in the enumeration below) and `## Abstract (original)` (position 12, conditional) — are protected by construction: `Connections` is auto-generated from `graph/edges.jsonl`, `Abstract (original)` is immutable source data from the arXiv API. This skill writes to the 10, never the 2.
  1. `One-line thesis` (marker: `_TODO: fill in after reading._`)
  2. `Problem / Gap` (marker: `_TODO._`)
  3. `Method` (marker: `_TODO._`)
  4. `Key Results` (marker: `_TODO._`)
  5. `Assumptions` (marker: `_TODO._`)
  6. `Limitations / Failure Modes` (marker: `_TODO._`)
  7. `Reusable Ingredients` (marker: `_TODO._`)
  8. `Open Questions` (marker: `_TODO._`)
  9. `Claims` (marker: `_TODO._`) — fill with `_No claims tracked yet._` if no `claim:` edges point to this paper; otherwise list them.
  10. `Connections` — **NEVER edit** (auto-generated from `graph/edges.jsonl`).
  11. `Relevance to This Project` (marker: `_TODO._`) — use `RESEARCH_BRIEF.md`, `AGENTS.md` (or legacy `CLAUDE.md`), or `gap_map.md` for project context. If no project context exists, leave as TODO and report it.
  12. `Abstract (original)` — leave alone (already populated by `ingest_paper` when `--arxiv-id` was used).

> 💡 Examples:
> - `/wiki-enrich` — enrich every paper with ≥1 TODO section (most common usage)
> - `/wiki-enrich vllm` — enrich a single paper by slug
> - `/wiki-enrich all --force` — rewrite every paper from scratch (use when you've adopted a new style)
> - `/wiki-enrich --source alphaxiv --max 5` — only use alphaxiv, only do 5 papers
> - `/wiki-enrich missing --max 50` — bigger batch (watch token budget)

## Pre-flight

Resolve `$WIKI_ROOT` and `$WIKI_SCRIPT` (canonical chain — see `shared-references/wiki-helper-resolution.md`):

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
[ -d research-wiki/ ] || { echo "ERROR: research-wiki/ not found. Run /research-wiki init first." >&2; exit 1; }

ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
WIKI_SCRIPT=""
[ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/research_wiki.py" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"
[ -z "$WIKI_SCRIPT" ] && [ -f tools/research_wiki.py ] && WIKI_SCRIPT="tools/research_wiki.py"
[ -z "$WIKI_SCRIPT" ] && [ -f ~/.codex/skills/research-wiki/research_wiki.py ] && WIKI_SCRIPT="$HOME/.codex/skills/research-wiki/research_wiki.py"
[ -n "$WIKI_SCRIPT" ] || { echo "ERROR: research_wiki.py not found." >&2; exit 1; }
```

If either fails, **hard-fail** — this skill manipulates wiki state and must not run blind.

## Workflow

### Phase 1: Parse target + discover candidates

Parse `$ARGUMENTS` for the first positional (target) and flags (`--source`, `--force`, `--max`).

Build the candidate paper list:

```bash
case "$TARGET" in
  all)
    PAPERS=( research-wiki/papers/*.md )
    ;;
  missing|"")
    # only papers with at least one TODO marker line
    PAPERS=( $(grep -lE "^_TODO(\._?|: fill in after reading\._?)$" research-wiki/papers/*.md 2>/dev/null) )
    ;;
  *)
    P="research-wiki/papers/${TARGET}.md"
    [ -f "$P" ] || { echo "ERROR: paper not found: $P" >&2; exit 1; }
    PAPERS=( "$P" )
    ;;
esac
echo "Candidate papers: ${#PAPERS[@]} (cap ${MAX_PAPERS})"
PAPERS=( "${PAPERS[@]:0:${MAX_PAPERS}}" )
```

If the candidate list is empty, print `"✓ Nothing to enrich."` and exit 0. Do not error.

### Phase 2: For each paper — read, fetch, fill

Iterate **one paper at a time**. For each `$PAPER` in `$PAPERS`:

**Step 2.1 — Read the page and project context.** Use the `Read` tool on the full paper file. Extract from the YAML frontmatter:
- `node_id` (e.g. `paper:vllm`) — slug = part after `paper:`
- `arxiv` from `external_ids.arxiv` — empty string if absent
- `title`
- existing `## Abstract (original)` blockquote (if present) — fallback content source

Additionally, on the FIRST paper of the batch (cache for the rest), read project-context files needed for the `Claims` and `Relevance to This Project` sections:
- `research-wiki/graph/edges.jsonl` — scan for `claim:` edges pointing to the current paper's `node_id`
- `RESEARCH_BRIEF.md` (project root) — if present, source for project goals
- `AGENTS.md` (project root, Codex CLI primary) or legacy `CLAUDE.md` — if present, fallback for project context
- `research-wiki/gap_map.md` — if non-empty, source for gap framing

If none of the project-context files exist, the `Relevance to This Project` section will be filled with the literal "context not yet set" line (see Step 2.4 table).

**Step 2.2 — Identify which sections are TODO.**

Match each section header against its marker:
- A header followed by exactly `_TODO._` → fill
- A header followed by `_TODO: fill in after reading._` → fill (One-line thesis)
- A header followed by any other content → skip (unless `--force`)
- `## Connections` → **always skip** (auto-generated)
- `## Abstract (original)` → **always skip** (immutable source data)

If no fillable sections remain, log `"skip: <slug> (already enriched)"` and continue.

**Step 2.3 — Fetch source content.**

The fetch chain runs **in order** until one returns usable content (>200 chars of text):

| Order | Source | How |
|-------|--------|-----|
| 1 | **alphaxiv overview** (`auto` default; `--source alphaxiv` to pin) | `WebFetch https://alphaxiv.org/overview/<arxiv_id>.md` — LLM-optimized summary, often best for filling sections |
| 2 | **alphaxiv abs** (fallback within alphaxiv) | `WebFetch https://alphaxiv.org/abs/<arxiv_id>.md` |
| 3 | **deepxiv brief** (`--source deepxiv` to pin) | `python3 "$DEEPXIV_FETCHER" paper-brief <arxiv_id>` if helper resolves |
| 4 | **arXiv API abstract — fresh fetch** (`--source arxiv` to pin) | `curl http://export.arxiv.org/api/query?id_list=<arxiv_id>` — log label: `arxiv-api-abstract` |
| 5 | **Page abstract — fallback** (last resort) | Reuse the existing `## Abstract (original)` blockquote already present in the page body from a prior `ingest_paper` run — log label: `page-abstract-fallback` |
| — | **No arxiv id + no page abstract** | Skip this paper, log `"skip: <slug> (no arxiv id, no abstract)"`, continue |

When trying alphaxiv: if WebFetch returns 404 / "Paper not found" / a redirect to the homepage, treat as miss and fall through.

When trying deepxiv: resolve `$DEEPXIV_FETCHER` per `shared-references/integration-contract.md`. If the helper or `deepxiv` CLI is missing, fall through silently.

Save the fetched content as `$SOURCE_TEXT`. Record which source succeeded for the log entry.

**Step 2.4 — Generate per-section content.**

You (the executor agent) are the LLM doing the grunt work. Given:
- `$SOURCE_TEXT` (the fetched overview / brief / abstract)
- `$TITLE`
- the list of fillable section headers

Write each TODO section's body following these rules:

| Section | Length | Style | What to extract |
|---------|--------|-------|-----------------|
| One-line thesis | 1 sentence, ≤25 words | Declarative | The paper's core contribution in one sentence — what they built / proved / improved |
| Problem / Gap | 1-2 sentences | Declarative | What problem the field had, why prior work fell short |
| Method | 2-4 sentences | Technical, name the technique | Core mechanism — algorithm name + key idea + how it differs from baselines |
| Key Results | 1-3 bullets OR 2-3 sentences | Quantitative | Headline numbers from the abstract / overview (X% improvement, Yx speedup, etc.). Keep units verbatim. |
| Assumptions | 1-3 bullets | Declarative | What the paper takes for granted (workload type, hardware, model class, distribution shape) |
| Limitations / Failure Modes | 1-3 bullets | Honest | What the paper explicitly admits OR what's structurally absent (e.g. "no multi-node evaluation", "assumes uniform request length") |
| Reusable Ingredients | 1-3 bullets | Concrete | Techniques / datasets / insights from this paper that could be ported elsewhere. **Highest value for `/idea-creator` — write carefully.** |
| Open Questions | 1-2 bullets | Question form | What the paper does NOT answer but raises |
| Claims | 1 line | Static | If no `claim:` edges in `graph/edges.jsonl` reference this paper, write the literal italic line: `_No claims tracked yet — populate via /proof-checker._`. Else list claim node IDs. |
| Relevance to This Project | 1-2 sentences | Project-contextual | Use `RESEARCH_BRIEF.md` / `AGENTS.md` (or legacy `CLAUDE.md`) / `gap_map.md` to phrase the connection. If no project context, write the literal italic line: `_Project context not yet set — populate RESEARCH_BRIEF.md or gap_map.md to enable this section._` and report. |

**Rules** (Karpathy fidelity):
- **Faithful to source.** If the paper doesn't say it, don't invent it. Prefer `_Not stated in source._` over hallucination.
- **No filler.** "This paper presents an approach to..." — don't write that. Start with the noun.
- **Keep technical terms in English.** vLLM, KV cache, prefill, decode, TTFT, etc. stay verbatim.
- **Quantitative when possible.** If the abstract has numbers, use them; don't paraphrase as "significant".
- **Bilingual support.** If the project's `AGENTS.md` declares a language preference (`language: zh` or `language: bilingual`), match it. Otherwise default to English (or follow `shared-references/output-language.md`).

**Step 2.5 — Edit the file.**

For each fillable section, use the `Edit` tool to replace the TODO marker with the generated body. Match the exact section header + marker pair to keep edits unique, e.g.:

```
## Problem / Gap
_TODO._
```

→

```
## Problem / Gap
<generated body>
```

**Never** touch the YAML frontmatter, `## Connections`, or `## Abstract (original)`.

**Step 2.6 — Append log entry.**

```bash
python3 "$WIKI_SCRIPT" log research-wiki/ "wiki-enrich: enriched paper:<slug> from <source> (filled N/M sections)"
```

Record which source provided content (`alphaxiv-overview`, `alphaxiv-abs`, `deepxiv-brief`, `arxiv-api-abstract`, or `page-abstract-fallback`) so the audit trail is honest about provenance.

### Phase 3: Final report

After processing all candidates, print:

```
✓ wiki-enrich complete

Processed:  N
Enriched:   X (sections filled: total)
Skipped:    Y  (reasons: already enriched / no arxiv id / fetch failed)
Failed:     Z  (with paper + reason)

Source breakdown:
  alphaxiv-overview: A
  alphaxiv-abs:      B
  deepxiv-brief:     C
  arxiv-api-abstract:     D
  page-abstract-fallback: E

Re-ideation suggestion: <if ≥5 papers were enriched, recommend `/idea-creator "topic"` so the freshly-filled `Reusable Ingredients` and `Limitations` feed brainstorming. `query_pack.md` is already rebuilt below — the user does NOT need to call `/research-wiki query` manually.>
```

Also rebuild `query_pack.md` once at the end (single `python3 "$WIKI_SCRIPT" rebuild_query_pack research-wiki/` call) so `/idea-creator` sees the new bodies on its next run.

## Output Protocols

> Follow the shared protocols:
> - **No `MANIFEST.md` entry.** This skill edits existing scaffolded pages in place rather than generating new artifacts. The audit trail lives in `research-wiki/log.md` (Step 2.6), with provenance per paper. Adding a `wiki-enrich` stage to `shared-references/output-manifest.md` is out of scope for this PR.
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting.

## Key Rules

- **Idempotent by default.** Re-running without `--force` only touches still-TODO sections. Safe to invoke as a cron.
- **Never touch frontmatter, `## Connections`, or `## Abstract (original)`.** Frontmatter is metadata, Connections is graph-generated, Abstract is immutable source data.
- **Hard-fail on missing wiki / missing helper.** Do not silently create `research-wiki/` — if it's missing, the user is in the wrong cwd or hasn't run `/research-wiki init`.
- **Track provenance.** Every log entry records which source actually filled the body. If a future audit shows alphaxiv hallucinated for a paper, you can find every page touched by that source.
- **Don't auto-trigger `/idea-creator`.** This skill builds the substrate; the user decides when to brainstorm next. Only *suggest* re-ideation in the final report.
- **Gracefully degrade.** If `WebFetch` is rate-limited, fall through to next source. If all sources miss, skip the paper and continue — don't abort the whole batch.
- **Karpathy fidelity above completeness.** It is better to leave a section as `_Not stated in source._` than to hallucinate. The wiki's value is that it doesn't lie.

## Composing with Other Skills

```
/research-lit "topic"               ← ingests papers as scaffolds (Step 6)
/wiki-enrich                        ← THIS — fills paper bodies (you are here)
/research-wiki lint                 ← health-check (orphans, contradictions, dead ideas)
/idea-creator "direction"           ← reads query_pack, ideates on top of enriched wiki
/research-wiki query "topic"        ← rebuild query_pack after big wiki changes
```

After a fresh `/research-pipeline` run leaves Stage 1 Phase 1 done but Phase 2 not started (the failure mode that prompted this skill), the recovery path is:

```
/wiki-enrich              # fill the paper TODOs ingest_paper left behind
/idea-creator "..."        # now ideate with a wiki that actually has content
```
