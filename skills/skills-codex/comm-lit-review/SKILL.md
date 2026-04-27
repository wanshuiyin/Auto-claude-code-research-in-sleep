---
name: comm-lit-review
description: Communications-domain literature review with Claude-style knowledge-base-first retrieval. Use when the task is about communications, wireless, networking, satellite/NTN, Wi-Fi, cellular, transport protocols, congestion control, routing, scheduling, MAC/PHY, rate adaptation, channel estimation, beamforming, or communication-system research and the user wants papers, related work, a survey, or a landscape summary. Search Zotero, Obsidian, and local paper folders first when available, then search IEEE Xplore, ScienceDirect, ACM Digital Library, and broader web in that order.
allowed-tools: Bash(*), Read, Glob, Grep, WebSearch, WebFetch, Write, Agent, mcp__zotero__*, mcp__obsidian-vault__*
---

# Comm Lit Review Claude Single

Research topic: $ARGUMENTS

## Purpose

Use this skill for communications-domain literature review when the topic is about:

- wireless communications
- cellular systems, `4G/5G/6G`, `NR`, `NTN`
- satellite, `LEO`, `GEO`, integrated space-air-ground systems
- Wi-Fi, WLAN, mesh, ad hoc, sidelink, V2X
- routing, scheduling, resource allocation, beamforming
- rate adaptation, link adaptation, `ACM`, `HARQ`, `CSI` feedback
- transport protocols and congestion control in communication networks
- cross-layer optimization for communication systems

If the center of gravity is generic ML architecture research, pure control theory without communications literature, or software/API documentation rather than papers, fall back to a general literature skill.

## Constants

- **PAPER_LIBRARY**: Check local PDFs in this order:
  1. `papers/` in the current project
  2. `literature/` in the current project
  3. Custom path specified by the user in `AGENTS.md` under `## Paper Library`
- **MAX_LOCAL_PAPERS = 20**: Maximum number of local PDFs to scan. If there are more, prioritize by filename and first-page relevance.

## Source Selection

Parse `$ARGUMENTS` for a `— sources:` directive.

- If `— sources:` is specified, only search the listed sources.
- If not specified, default to:
  - `zotero`
  - `obsidian`
  - `local`
  - `ieee`
  - `sciencedirect`
  - `acm`
  - `web`

Valid source values:

- `zotero`
- `obsidian`
- `local`
- `ieee`
- `sciencedirect`
- `acm`
- `web`
- `all`

If `all` is specified, interpret it as the full default source set.

## Retrieval Order

This is a knowledge-base-first skill. Search in this order unless the user overrides it:

1. `Zotero`
2. `Obsidian`
3. local `papers/` and `literature/`
4. `IEEE Xplore`
5. `ScienceDirect`
6. `ACM Digital Library`
7. broader web

Graceful degradation rules:

- If an unrequested source is unavailable, do not fail.
- Skip it silently and continue to the next source.
- If the user explicitly requested a source and it is unavailable, stop and tell the user what must be configured. Do not silently downgrade an explicitly requested source policy.

## External Search Policy

For external search:

- prefer `IEEE Xplore` first
- then `ScienceDirect`
- then `ACM`
- then broader web only when needed

Publication policy:

- prefer peer-reviewed journals and major conferences
- label workshop papers as `workshop`
- label arXiv-only or author-hosted versions as `preprint`
- if both preprint and formal version exist, cite the formal version first

Time-window policy:

- if the user does not specify a year range, include both a short foundational set and a recent set
- recommended split:
  - `foundational`: before 2022
  - `recent`: 2022 to present

## Venue Priority

Within each database tier, search venue tiers in this order.

### Tier A

Journals:

- `IEEE Journal on Selected Areas in Communications (JSAC)`
- `IEEE/ACM Transactions on Networking (ToN)`
- `IEEE Transactions on Wireless Communications (TWC)`
- `IEEE Transactions on Communications (TCOM)`

Conferences:

- `ACM SIGCOMM`
- `USENIX NSDI`
- `ACM MobiCom`
- `ACM CoNEXT`
- `IEEE INFOCOM`

### Tier B

Journals:

- `IEEE Transactions on Vehicular Technology (TVT)`
- `IEEE Wireless Communications Letters (WCL)`
- `IEEE Communications Letters`
- `Computer Networks`
- `Computer Communications`
- `Ad Hoc Networks`
- `Physical Communication`

Conferences:

- `IEEE ICC`
- `IEEE GLOBECOM`
- `IEEE WCNC`
- `IEEE PIMRC`
- `ACM MobiHoc`

### Tier C

- other relevant IEEE journals and transactions
- other relevant Elsevier journals
- other clearly relevant ACM conferences and workshops
- topic-specific satellite, optical, vehicular, IoT, aerial, or edge communications venues

Usage rules:

- start from Tier A
- widen to Tier B if needed
- widen to Tier C if still sparse
- only then broaden to full web search
- by default this is a soft priority, not a hard whitelist
- if the user says `only top venues`, `top journals only`, or `top conferences only`, treat Tier A as a hard filter

## Workflow

### Step 0a: Search Zotero Library

Skip this step if Zotero MCP is not configured or `zotero` is not enabled.

If available:

1. search by topic
2. capture title, authors, year, venue
3. pull user annotations, tags, or collections when present
4. treat these as high-priority evidence because they reflect the user's existing library

### Step 0b: Search Obsidian Vault

Skip this step if Obsidian MCP is not configured or `obsidian` is not enabled.

If available:

1. search topic-related notes
2. collect summaries, wikilinks, tags, and paper references
3. treat these notes as the user's processed understanding of the topic

### Step 0c: Scan Local Paper Library

Run this step if `local` is enabled.

1. locate PDFs from `papers/**/*.pdf` and `literature/**/*.pdf`
2. de-duplicate against Zotero hits when possible
3. read the first pages of relevant PDFs
4. extract title, authors, year, problem, method, and relevance
5. use local hits to guide and de-duplicate later external search

### Step 1: Search External Primary Sources

Use a layered search strategy. For communications topics, avoid random blog posts or tertiary summaries.

Database ladder:

1. `ieeexplore.ieee.org`
2. `sciencedirect.com`
3. `dl.acm.org`
4. broader web using primary publisher pages, official conference sites, DOI pages, and author-hosted copies of already-identified formal papers

Move to the next database tier only when:

- the higher-priority tier is too sparse
- the topic clearly publishes elsewhere
- the user explicitly asks for broader coverage

Within each database tier:

1. start from Tier A venues
2. widen to Tier B if needed
3. widen to Tier C if still sparse

### Step 2: Extract Paper-Level Facts

For each relevant paper, capture:

- Title
- Authors
- Year
- Venue
- Layer or system scope
- Scenario and assumptions
- Core method
- Main result or claim
- Limitation
- Relevance to the user's topic
- Source URL
- Source origin: `zotero`, `obsidian`, `local`, `ieee`, `sciencedirect`, `acm`, or `web`

Favor concrete numbers, assumptions, and problem definitions over generic paraphrases.

Do not collapse transport-layer rate control and PHY/MAC rate adaptation into one bucket without saying so explicitly.

## Synthesis Rules

Group papers by technical axis rather than by search order. Common groupings:

- `PHY/MAC` adaptation
- transport and congestion control
- `NTN` and satellite resource management
- cross-layer or learning-based control
- measurement and empirical studies

When useful, explicitly separate:

- foundational vs recent work
- formal publications vs preprints
- top-tier vs lower-tier venues
- single-link vs multi-user formulations
- simulation-only vs deployment-backed work
- user-owned sources vs newly surfaced external papers

If evidence is weak, say so instead of smoothing it over.

## Output

Use a literature table with these columns:

| Paper | Venue | Year | Layer | Scenario | Method | Key Result | Limitation | Relevance | Source |
|---|---|---:|---|---|---|---|---|---|---|

`Source` should indicate where the paper came from first:

- `zotero`
- `obsidian`
- `local`
- `ieee`
- `sciencedirect`
- `acm`
- `web`

After the table, summarize in this order:

1. what the field is mostly trying to solve
2. how papers cluster into `2-4` approaches
3. what the user already had vs what was newly surfaced
4. where the evidence is strong vs weak
5. what research gap remains

End with `Practical Takeaway`:

- dominant current approach
- likely saturated direction
- promising open direction

## Key Rules

- Do not silently downgrade explicitly requested sources, account-backed databases, or primary-database constraints. Report the missing configuration instead.

- Never fail because Zotero or Obsidian MCP is missing.
- Prefer user-owned sources first when available, but do not let them replace external validation.
- Prefer primary formal sources over summaries or tertiary commentary.
- Prefer `IEEE` and `ScienceDirect` first, `ACM` second, and only then broader web search unless the user asks otherwise.
- Search venue tiers from top to broad within each database tier.
- Treat venue tiers as soft ranking by default and hard constraint only when the user explicitly asks for top-only search.
- Do not pretend a preprint is peer reviewed.
- If the topic spans multiple layers, say that the literature itself is split across layers.
