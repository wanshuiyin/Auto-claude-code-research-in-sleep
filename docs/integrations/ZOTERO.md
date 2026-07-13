# Zotero Integration (Optional)

> 🇨🇳 中文版：[ZOTERO_CN.md](ZOTERO_CN.md)
> Plugs into [`/research-lit`](../../skills/research-lit/SKILL.md) and the upstream skills that call it (`/idea-discovery`, `/research-pipeline`).

If you use [Zotero](https://www.zotero.org/) to manage your paper library, `/research-lit` can search your collections, read your annotations/highlights, and export BibTeX — all **before** searching the web. This dramatically improves citation quality because the literature search starts from papers you've already vetted.

## Recommended MCP server

**[zotero-mcp](https://github.com/54yyyu/zotero-mcp)** (1.8k⭐, semantic search, PDF annotations, BibTeX export)

```bash
# Install
uv tool install zotero-mcp-server   # or: pip install zotero-mcp-server

# Add to Claude Code (Local API — requires Zotero desktop running)
claude mcp add zotero -s user -- zotero-mcp -e ZOTERO_LOCAL=true

# Or use Web API (works without Zotero running)
claude mcp add zotero -s user -- zotero-mcp \
  -e ZOTERO_API_KEY=your_key -e ZOTERO_USER_ID=your_id
```

> Get your API key at https://www.zotero.org/settings/keys

## What it enables in `/research-lit`

- 🔍 Search your Zotero library by topic (including semantic/vector search)
- 📂 Browse collections and tags
- 📝 Read your PDF annotations and highlights (what *you* personally found important)
- 📄 Export BibTeX for direct use in paper writing

## How `/research-lit` orders sources

When Zotero is configured, the default search order becomes:

1. **Zotero** (your library — fastest, highest signal)
2. **Obsidian** (if [also configured](OBSIDIAN.md) — your processed notes)
3. **Local PDFs** under the project directory
4. **Web search** (`web`, including arXiv and Google Scholar; included in default `all`)
5. **Opt-in external sources** (`semantic-scholar`, `deepxiv`, `exa`, `gemini`, `openalex`; only searched when explicitly listed via `— sources:`)

Override the default with `— sources: zotero, web` or `— sources: all`.

## Fallback: no Zotero

Without Zotero configured, `/research-lit` automatically skips it and uses local PDFs + web search instead. No errors, no warnings.

## Combined Zotero + Obsidian workflow

Many researchers use Zotero for paper storage and Obsidian for notes. Both integrations work simultaneously — `/research-lit` checks Zotero first (raw papers + annotations), then Obsidian (your processed notes), then local PDFs, then web. See [OBSIDIAN.md](OBSIDIAN.md) for the Obsidian half of the setup.

## Related skills

- [`/research-lit`](../../skills/research-lit/SKILL.md) — primary consumer
- [`/idea-discovery`](../../skills/idea-discovery/SKILL.md) — uses `/research-lit` internally
- [`/research-pipeline`](../../skills/research-pipeline/SKILL.md) — Workflow 1 + 2 + 3 end-to-end
