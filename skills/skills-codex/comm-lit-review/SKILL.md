---
name: comm-lit-review
description: "Communications-domain literature review for networking, wireless, cellular, and satellite/NTN research. Use when the topic is in communications systems and the user wants papers, prior art, surveys, or related work. Do not use for generic ML or non-communications literature search; use `research-lit` there."
---

# Comm Lit Review

## Overview

Run communications-focused paper search with tighter source policy than a generic literature review. Default to formal publications, prioritize `IEEE Xplore` and `ScienceDirect`, then `ACM Digital Library`, and output a review that is structured for research use rather than casual browsing.

## Routing Boundaries

- Use this skill when the topic is clearly within communications, networking, wireless, cellular, or satellite/NTN systems.
- Use `research-lit` instead for generic paper search, mixed-domain topics, or non-communications literature review.
- Use `novelty-check` instead when the user already has a concrete idea and mainly wants a novelty verdict.

Read [references/source-policy.md](references/source-policy.md) before searching. Use [references/domain-taxonomy.md](references/domain-taxonomy.md) to classify the topic, [references/venue-tiering.md](references/venue-tiering.md) to rank venues, and [references/output-template.md](references/output-template.md) to format the final answer.

## Workflow

### 1. Classify the request

Decide whether the request is primarily about:

- Wireless PHY/MAC
- Networking / transport / congestion control
- Satellite / NTN / integrated space-air-ground systems
- Cross-layer optimization / scheduling / resource allocation
- Sensing / MEC / edge intelligence within communications systems

If the request is not clearly in communications systems research, fall back to a more general literature skill.

### 2. Lock the search policy

Apply these defaults unless the user overrides them:

- Databases first: `IEEE Xplore`, `ScienceDirect`, then `ACM Digital Library`, then broader web
- Publication bias: formal publications first, preprints second
- Time window: cover both foundational and recent work
  - Default split: foundational before 2022, recent from 2022 onward
- Output goal: research note, related-work summary, or comparison table rather than a raw search dump

If the user explicitly narrows scope, obey the narrower scope:

- only journals
- only IEEE / only ScienceDirect
- only top venues
- only LEO / only Wi-Fi / only transport
- exclude arXiv
- only papers after a certain year

### 3. Search primary sources first

Use a layered search strategy. For communications topics, do not build the review from random blog posts or derivative summaries.

#### Database ladder

Search in this order by default:

1. `ieeexplore.ieee.org`
2. `sciencedirect.com`
3. `dl.acm.org`
4. broader web using primary publisher pages, official conference sites, DOI pages, and author-hosted copies of already-identified formal papers

Only move to the next database tier when one of these is true:

- the higher-priority tiers are too sparse for the topic
- the topic is known to publish heavily outside the higher tier
- the user explicitly asks for broader coverage

#### Venue ladder

Within each database tier, search venue tiers in this order:

1. top communications and networking journals / top conferences
2. mainstream strong journals / flagship broader conferences
3. all remaining relevant formal venues

Follow the concrete tier lists in [references/venue-tiering.md](references/venue-tiering.md).

By default this venue tiering is a soft priority, not a hard whitelist.

- Default behavior: start from Tier A, then widen if needed
- If the user says `only top venues`, `top journals only`, `top conferences only`, or equivalent, switch to hard constraint mode and do not auto-expand beyond Tier A unless the user later relaxes the constraint

Use preprints only when:

- the user explicitly asks for them
- the area is very recent and formal versions are missing
- a paper is clearly influential but only publicly accessible as a preprint

When a preprint is used, label it clearly as `preprint`.

### 4. Extract paper-level facts

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

Favor numbers, assumptions, and actual problem statements over generic summaries.

### 5. Synthesize as a communications review

Group papers by technical axis, not by search order. Common groupings:

- PHY/MAC adaptation
- Transport / congestion control
- NTN / satellite resource management
- Cross-layer or learning-based control
- Measurement / empirical studies

Explicitly separate:

- foundational vs recent papers
- formal publications vs preprints
- top-tier vs lower-tier venues when that distinction matters
- single-link vs multi-user / network-wide formulations
- simulation-only vs measurement / deployment-backed work

### 6. Produce a research-useful output

Follow the templates in [references/output-template.md](references/output-template.md).

The default output should include:

- a compact literature table
- a short narrative on where the field stands
- disagreements or unresolved assumptions
- likely research gaps

## Rules

- Prefer primary sources over summaries or tertiary commentary.
- Prefer IEEE and ScienceDirect first, ACM second, and only then broader web search unless the user asks otherwise.
- Search venue tiers from top to broad within each database tier.
- Treat venue tiers as soft ranking by default and hard constraint only when the user explicitly asks for top-only search.
- Do not pretend a preprint is peer reviewed.
- Do not collapse transport-layer rate control and PHY/MAC rate adaptation into one bucket without saying so explicitly.
- If the topic spans multiple layers, say that the literature itself is split across layers.
- If evidence is weak, say so instead of smoothing it over.
