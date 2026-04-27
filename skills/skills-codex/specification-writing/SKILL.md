---
name: specification-writing
description: "Write the full patent specification from claims and invention disclosure. Use when user says \"撰写说明书\", \"write specification\", \"写说明书\", \"patent description\", or wants to draft the complete patent specification."
argument-hint: [claims-path]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, Skill, WebSearch, WebFetch
---

# Specification Writing: Section-by-Section Patent Description

Write the patent specification based on: **$ARGUMENTS**

Adapted from `/paper-write` for patent specifications. The specification supports the claims -- it is not a paper.

## Constants

- `REVIEWER_MODEL = gpt-5.4` — External reviewer for specification quality
- `JURISDICTION = "auto"` — Inherit from pipeline or detect from args; `CN`, `US`, `EP`, `ALL`
- `OUTPUT_FORMAT = "markdown"` — Markdown drafts; converted to filing format by `/jurisdiction-format`
- `OUTPUT_DIR = "patent/"` — Base output directory
- `LANGUAGE = "auto"` — Auto from jurisdiction: CN->Chinese, US/EP->English

## Inputs

1. `patent/CLAIMS.md` — the drafted claims (primary source)
2. `patent/INVENTION_DISCLOSURE.md` — invention decomposition
3. `patent/PRIOR_ART_REPORT.md` — for background section
4. User-provided figures (if any)

## Shared References

Load `../shared-references/patent-writing-principles.md` for specification writing rules, language guidelines, and reference numeral conventions.
Load `../shared-references/patent-format-cn.md` or `patent-format-us.md` or `patent-format-ep.md` based on jurisdiction.

## Workflow

### Step 1: Initialize Specification Structure

Create the output directory and section files:

```
patent/specification/
├── title.md
├── technical_field.md
├── background.md
├── summary.md
├── drawings_description.md
├── detailed_description.md
└── abstract.md
```

### Step 2: Write Title (发明名称)

- Must match the broadest claim scope
- No trademarks, no "improved" or "new" or "novel"
- CN format: "一种[领域]的[技术主题]" or "[领域]的[技术主题]装置"
- US/EP format: "[Technical topic] for [purpose]" or "[Technical topic] and method thereof"
- Keep concise (CN: typically under 25 characters; US: under 500 characters)

### Step 3: Write Technical Field (技术领域)

1-2 paragraphs identifying the technical domain:
- "The present invention relates to [broad field], and more particularly to [specific area]."
- CN: "本发明涉及[技术领域]，具体涉及[具体领域]。"

### Step 4: Write Background (背景技术)

This is NOT a literature review. It directly sets up the problem.

Structure:
1. Describe the closest prior art approaches (2-3 paragraphs)
2. Identify specific technical deficiencies of each approach
3. The deficiencies must be technical, not commercial or social
4. DO NOT admit the prior art is "superior" or "better"
5. DO NOT cite specific patent numbers unless they are known prior art (citations go in IDS for US, or Background section for CN)

CN format: "背景技术" section describing existing technology and its shortcomings.

### Step 5: Write Summary (发明内容)

Three parts, directly mirroring INVENTION_DISCLOSURE.md:

**Technical Problem (要解决的技术问题)**:
- State the problem derived from background deficiencies
- CN: "本发明要解决的技术问题是..."

**Technical Solution (技术方案)**:
- Describe how the invention solves the problem
- Must provide support for ALL claim elements
- Start from the broadest claim and describe the core inventive concept
- CN: "为解决上述技术问题，本发明采用的技术方案是：..."
- **NO formulas, NO mathematical derivations, NO circuit models** — these belong in 具体实施方式, not 发明内容

**Advantages (有益效果)**:
- Benefits derived from the structural/technical features (qualitative reasoning)
- CN: "本发明的有益效果是：..."
- **NO specific numerical results** (e.g., "detection limit 70μm", "response time 105ms") — these are experimental findings, not invention properties
- Frame advantages structurally: "由于采用了...结构，因此具有...效果"

### Step 6: Write Brief Description of Drawings (附图说明)

Invoke `/figure-description` as a sub-skill if user has provided figures:
```
/figure-description "patent/figures/"
```

If no user figures, describe what figures should exist based on the claims.

Format:
- CN: "图1是...的示意图；图2是...的流程图；"
- US: "FIG. 1 is a block diagram showing...; FIG. 2 is a flowchart illustrating..."

### Step 7: Write Detailed Description (具体实施方式)

Invoke `/embodiment-description` as a sub-skill:
```
/embodiment-description "patent/CLAIMS.md"
```

This section must:
- Describe at least one complete embodiment with reference numerals
- Enable a POSITA to make and use the invention
- Support every claim element with explicit description
- Include variations and alternatives for broader claim interpretation

### Step 8: Write Abstract (摘要)

Jurisdiction-specific word limits:

| Jurisdiction | Word Limit | Notes |
|-------------|-----------|-------|
| CN | 300 words (Chinese characters) | Include most representative claim reference |
| US | 150 words (2500 characters) | Enable efficient searching, no legal phrases |
| EP | ~150 words | No statements on merits or value |

The abstract summarizes:
1. The technical field
2. The problem being solved
3. The technical solution (core features)
4. Key advantages

### Step 9: Claim Support Verification

Verify every claim element finds support in the specification:

| Claim | Element | Specification Section | Paragraph(s) | Reference Numeral |
|-------|---------|----------------------|-------------|-------------------|
| 1 | step a | detailed_description | ¶3 | 202 |
| 1 | step b | detailed_description | ¶4 | 204 |
| X | component A | detailed_description | ¶2 | 102 |

If any element lacks support, add the necessary description before proceeding.

### Step 10: Cross-Model Review

Call `REVIEWER_MODEL` via a dedicated Codex reviewer agent at xhigh reasoning:

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    You are a patent examiner reviewing a specification for completeness.
    CLAIMS: [all claims]
    SPECIFICATION: [all specification sections]

    Check for:
    1. Written description support: Does every claim element have explicit or inherent support?
    2. Enablement: Can a POSITA practice the invention from this specification?
    3. Consistency: Do reference numerals match across figures and specification?
    4. Language quality: Any subjective terms, relative terms without definition, or result-to-be-achieved language?
    5. Missing embodiments: Are there claim features that need additional embodiments?
    6. Background deficiencies: Are they technical and specific enough?
```

### Step 11: Output

All specification sections are in `patent/specification/`.

Summary file: `patent/specification/SPECIFICATION_INDEX.md` with:
```markdown
## Patent Specification

### Sections
| Section | File | Word Count | Status |
|---------|------|-----------|--------|
| Title | title.md | | Complete |
| Technical Field | technical_field.md | | Complete |
| Background | background.md | | Complete |
| Summary | summary.md | | Complete |
| Drawings Description | drawings_description.md | | Complete |
| Detailed Description | detailed_description.md | | Complete |
| Abstract | abstract.md | | Complete |

### Claim Support Status
| Claim | Elements Supported | Elements Missing |
|-------|-------------------|-----------------|
| 1 | All | None |
| X | All | None |
```

## Key Rules

- The specification supports the claims, not the other way around. Every claim element must have support.
- Use consistent terminology -- same word for the same concept throughout.
- DO NOT include experimental results, accuracy metrics, or empirical evaluations.
- DO NOT use subjective language ("excellent", "surprising", "superior").
- Reference numerals must be consistent: same component, same numeral, everywhere.
- Background section describes specific deficiencies, not general "need for improvement."
- Multiple embodiments strengthen the specification but are not always required.
- Large file handling: if a Write operation fails, retry with Bash `cat <<'EOF'` heredoc.
- If reviewer delegation is unavailable in the current Codex host, stop and ask the user to enable Codex agent support before continuing.
