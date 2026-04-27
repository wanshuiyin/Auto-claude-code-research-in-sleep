---
name: patent-pipeline
description: "Full patent drafting pipeline from invention description to jurisdiction-formatted filing documents. Supports CN (CNIPA), US (USPTO), EP (EPO). Supports invention patents and utility models. Use when user says \"写专利\", \"patent pipeline\", \"专利申请\", \"draft patent\", \"写权利要求书\", or wants to draft a complete patent application."
argument-hint: [invention-description — jurisdiction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill
---

# Patent Pipeline: From Invention to Filing

Draft a complete patent application based on: **$ARGUMENTS**

## Overview

This skill orchestrates the full patent drafting lifecycle -- from prior art search through jurisdiction-formatted filing documents. It chains sub-skills into a patent-specific pipeline:

```
/prior-art-search → /patent-novelty-check → /invention-structuring → /claims-drafting → /specification-writing → /patent-review → /jurisdiction-format
     (search)           (verify)              (structure)             (claims)            (description)          (examiner)         (compile)
                                                                                              ├── /figure-description
                                                                                              └── /embodiment-description
```

**This is a parallel branch, not part of the linear research pipeline.** After `/idea-discovery` produces validated ideas, the user can either:
- Go to `/experiment-bridge` → `/auto-review-loop` → `/paper-writing` (publish track)
- Go to `/grant-proposal` (funding track)
- Go to `/patent-pipeline` (patent track) **<-- this skill**

```
                    ┌→ /experiment-bridge → /auto-review-loop → /paper-writing  (publish track)
/idea-discovery ────┤
                    ├→ /grant-proposal → [get funded] → ...  (funding track)
                    └→ /patent-pipeline → [file patent]       (patent track)
```

Patents are about **protecting inventions** (legal scope), not publishing results (academic contribution). This skill handles the unique requirements of patent drafting: prior art analysis, claims hierarchy design, specification writing with enablement support, embodiment descriptions, and jurisdiction-specific formatting.

## Constants

- **JURISDICTION = `CN`** — Target patent jurisdiction. Options: `CN` (CNIPA), `US` (USPTO), `EP` (EPO), `ALL` (generate all three). Override via argument (e.g., `/patent-pipeline "invention — US"`).
- **PATENT_TYPE = `invention`** — `invention` (发明专利, 20 year protection) or `utility_model` (实用新型, CN only, 10 year protection, apparatus claims only). Override via argument.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for examiner-style review.
- **MAX_REVIEW_ROUNDS = 2** — Maximum review-revision cycles.
- **AUTO_PROCEED = false** — At each checkpoint, **always wait for explicit user confirmation**. Patent applications require inventor judgment at every stage. Set `true` only if user explicitly requests autonomous mode.
- **LANGUAGE = `auto`** — Output language. Auto-detected from jurisdiction: CN->Chinese, US->English, EP->English. Override explicitly if needed.
- **OUTPUT_DIR = `patent/`** — Directory for generated patent files.
- **OUTPUT_FORMAT = `markdown`** — Draft format. `markdown` for review, `docx` for filing-ready.

> Override defaults via arguments: `/patent-pipeline "invention — US, utility model"` or `/patent-pipeline "invention — ALL, language: Chinese"`.

## Patent Type Specifications

### Invention Patent (发明专利)

| Field | Detail |
|-------|--------|
| **Protection** | 20 years from filing date |
| **Subject matter** | Methods, systems, products, compositions, processes |
| **Examination** | Substantive examination required |
| **Inventive step** | High (must involve an inventive step / 创造性) |
| **Timeline** | 2-4 years to grant (CN); 2-3 years (US); 3-5 years (EP) |
| **Claims** | Method + system + product claims allowed |

### Utility Model (实用新型) — CN Only

| Field | Detail |
|-------|--------|
| **Protection** | 10 years from filing date |
| **Subject matter** | Product shape, structure, or combination thereof only |
| **Examination** | Formal examination only (no substantive examination) |
| **Inventive step** | Lower than invention patent |
| **Timeline** | 6-8 months to grant |
| **Claims** | Apparatus/device claims only. NO method claims. |
| **Restriction** | CN jurisdiction only |

## State Persistence (Compact Recovery)

Patent drafting is a long task that may trigger context compaction. Persist state to `patent/PATENT_STATE.json` after each phase:

```json
{
  "phase": 3,
  "jurisdiction": "CN",
  "patent_type": "invention",
  "language": "Chinese",
  "codex_thread_id": "019cfcf4-...",
  "invention_title": "...",
  "claims_count": 15,
  "status": "in_progress",
  "timestamp": "2026-04-10T15:00:00"
}
```

**Write this file at the end of every phase.** On invocation, check for this file:
- If absent or `status: "completed"` -> fresh start
- If `status: "in_progress"` and within 24h -> **resume** from saved phase (read output files to restore context)
- If older than 24h -> fresh start (stale state)

On completion, set `"status": "completed"`.

## Workflow

### Phase 0: Input Parsing & Context Gathering

Parse `$ARGUMENTS` to extract:

1. **Invention description** — may be structured (references INVENTION_BRIEF.md), conversational with figures, or output from IDEA_REPORT.md
2. **Jurisdiction** — detect from keywords (e.g., "CN" or "中国" -> CN, "US" or "USPTO" -> US, "EP" or "EPO" -> EP, "ALL")
3. **Patent type** — detect from keywords (e.g., "utility model" or "实用新型" -> utility_model, default -> invention)
4. **Overrides** — language, output format, review rounds

Then gather context from the project directory:

1. Read `INVENTION_BRIEF.md` if it exists (user filled in the template)
2. Read `IDEA_REPORT.md` if it exists (from `/idea-discovery` -- can extract invention from research results)
3. Read `refine-logs/FINAL_PROPOSAL.md` if it exists
4. Read `NARRATIVE_REPORT.md` if it exists (research results that may be patentable)
5. Search for user-provided figures (PNG, JPG, SVG, PDF) in the project directory
6. Check for `patent/PATENT_STATE.json` (resume from prior interrupted run)

If insufficient context exists:
- No invention description at all -> suggest user describe the invention or fill in `INVENTION_BRIEF.md`
- Has IDEA_REPORT.md -> extract patentable aspects from the research
- Has figures -> reference them in the invention brief
- No figures -> note that figures will be needed and plan what drawings are required

**If the input is conversational** (not a structured brief), parse the description into the invention brief structure and write `patent/INVENTION_BRIEF.md` for downstream phases.

### Phase 1: Prior Art Search & Novelty Assessment

#### 1.1 Prior Art Search

Invoke `/prior-art-search`:

```
/prior-art-search "patent/INVENTION_BRIEF.md"
```

This searches patent databases (Google Patents, Espacenet) and academic literature for relevant prior art.

#### 1.2 Novelty Check

Invoke `/patent-novelty-check`:

```
/patent-novelty-check "patent/INVENTION_BRIEF.md"
```

This assesses novelty and non-obviousness against the prior art found in step 1.1.

**🚦 Checkpoint:** Present the prior art landscape and novelty assessment:

```
Prior art search complete:
- [X] patent references found
- [Y] non-patent literature references found
- Closest prior art: [reference] -- [why it's closest]
- Novelty assessment: [PATENTABLE / PATENTABLE WITH AMENDMENTS / NOT PATENTABLE]
- Key risk areas: [list]

Ready to proceed with invention structuring?
```

**⛔ STOP HERE and wait for user response.** Do NOT auto-proceed unless AUTO_PROCEED=true.

Options:
- Reply **"go"** -> proceed to Phase 2
- Reply with **adjustments** -> refine the invention scope and re-check novelty
- Reply **"stop"** -> save progress to `patent/DRAFT_NOTES.md`

**State**: Write `PATENT_STATE.json` with `phase: 1`.

### Phase 2: Invention Structuring & Claims Design

#### 2.1 Structure the Invention

Invoke `/invention-structuring`:

```
/invention-structuring "patent/INVENTION_BRIEF.md"
```

This decomposes the invention into core inventive concept, supporting features, and optional features. Produces `patent/INVENTION_DISCLOSURE.md`.

#### 2.2 Draft Claims

Invoke `/claims-drafting`:

```
/claims-drafting "patent/INVENTION_DISCLOSURE.md"
```

This drafts the claims hierarchy -- the most critical part of the patent. Produces `patent/CLAIMS.md`.

**🚦 Checkpoint:** Present the invention structure and claims:

```
Invention structured:
- Core inventive concept: [summary]
- Claim categories: [method, system, etc.]
- Claims drafted: [X] independent + [Y] dependent = [Z] total
- Independent claim 1 (broadest): [first 50 words of claim 1]
- Examiner review score: [X]/10

The claims define the legal scope of protection. Please review before proceeding to specification.
```

**⛔ STOP HERE and wait for user response.** Do NOT auto-proceed unless AUTO_PROCEED=true.

Options:
- Reply **"go"** -> proceed to Phase 3
- Reply with **adjustments** (e.g., "broaden claim 1", "add more dependent claims") -> revise claims
- Reply **"stop"** -> save progress

**State**: Write `PATENT_STATE.json` with `phase: 2`.

### Phase 3: Specification Writing

Invoke `/specification-writing`:

```
/specification-writing "patent/CLAIMS.md"
```

This writes the full specification section by section. Internally invokes `/figure-description` (if user-provided figures exist) and `/embodiment-description` for the detailed description. The specification-writing skill handles figure processing and embodiment writing as sub-skills.

**🚦 Checkpoint:** Present the specification overview:

```
Specification written:
- Title: [title]
- Sections: Technical Field, Background, Summary, Drawings Description, Detailed Description, Abstract
- Embodiments: [X]
- Reference numerals: [Y] components mapped
- Abstract length: [Z] words (limit: [jurisdiction limit])
- Claim support: [all elements covered / X elements missing]

Ready to proceed to review?
```

**⛔ STOP HERE and wait for user response.**

**State**: Write `PATENT_STATE.json` with `phase: 3`.

### Phase 4: Patent Review

Invoke `/patent-review`:

```
/patent-review "patent/"
```

This runs 2 rounds of examiner-style review via GPT-5.4 xhigh. The examiner evaluates clarity, written description, enablement, novelty, non-obviousness, and claim scope.

**State**: Write `PATENT_STATE.json` with `phase: 4` and review score.

### Phase 5: Jurisdiction Formatting & Output

Invoke `/jurisdiction-format`:

```
/jurisdiction-format "patent/"
```

This compiles the application into the target jurisdiction format(s).

#### Final Deliverables

| Output | Location | Description |
|--------|----------|-------------|
| CN: 权利要求书 | `patent/output/CN/` | Claims in CNIPA format |
| CN: 说明书 | `patent/output/CN/` | Description in CNIPA format |
| CN: 说明书摘要 | `patent/output/CN/` | Abstract (CN) |
| US: Claims | `patent/output/US/` | Claims in USPTO format |
| US: Specification | `patent/output/US/` | Description in USPTO format |
| US: Abstract | `patent/output/US/` | Abstract (US) |
| EP: Claims | `patent/output/EP/` | Claims in EPO format |
| EP: Description | `patent/output/EP/` | Description in EPO format |
| EP: Abstract | `patent/output/EP/` | Abstract (EP) |

#### Final Report

```markdown
## Patent Pipeline Complete

### Application Summary
- Title: [invention title]
- Jurisdiction: [CN/US/EP/ALL]
- Patent Type: [Invention / Utility Model]
- Language: [Chinese/English]
- Total Claims: [X] independent + [Y] dependent

### Pipeline Scores
| Phase | Score |
|-------|-------|
| Prior Art Search | [completeness assessment] |
| Novelty Assessment | [PATENTABLE/PATENTABLE WITH AMENDMENTS/NOT PATENTABLE] |
| Examiner Review Round 1 | [X]/10 |
| Examiner Review Round 2 | [Y]/10 |
| Final | [Z]/10 |

### Output Files
[Table of all generated files with paths]

### Next Steps
- [ ] Have a patent attorney review the application
- [ ] Conduct professional prior art search (this tool's search is preliminary)
- [ ] Prepare formal drawings (if user figures need professional rendering)
- [ ] File with the patent office
- [ ] For utility model (CN): formal examination typically takes 6-8 months
- [ ] For invention patent: substantive examination may take 2-4 years
```

**State**: Write `PATENT_STATE.json` with `phase: 5, status: "completed"`.

## Key Rules

- Never fabricate prior art references, patent numbers, or citations.
- Claims must be supported by the specification (written description requirement).
- Each jurisdiction has strict format requirements -- do not mix formats.
- Utility model (实用新型) applies ONLY to CN jurisdiction and ONLY covers apparatus/device claims.
- AUTO_PROCEED defaults to false -- patent applications require human review at every phase. Sub-skills inherit this flag: when AUTO_PROCEED=false, sub-skills present results and wait at their own internal checkpoints too.
- The patent pipeline produces drafts for attorney review, not final filing documents.
- Large file handling: if a Write operation fails, retry with Bash `cat <<'EOF'` heredoc.
- Never include experimental results or empirical evaluations in the specification.
- Consistent terminology is mandatory -- same word for the same concept throughout.
- If a downstream reviewer step is requested but reviewer delegation is unavailable in the current Codex host, stop and ask the user to enable Codex agent support before continuing.

## Composing with Other Workflows

The patent pipeline can start from multiple entry points:

```
User describes invention directly ──→ /patent-pipeline

/idea-discovery produces IDEA_REPORT.md ──→ /patent-pipeline (extract patentable aspects)

/research-refine produces FINAL_PROPOSAL.md ──→ /patent-pipeline (from refined research idea)

/auto-review-loop produces strong results ──→ /patent-pipeline (patent the method)
```

## Acknowledgements

Built on the ARIS (Auto-claude-code-research-in-sleep) skill architecture. Patent writing principles adapted from MPEP (US), CN Patent Examination Guidelines (CN), and EPO Guidelines for Examination (EP).
