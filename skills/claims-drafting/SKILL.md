---
name: claims-drafting
description: "Draft patent claims for an invention. Use when user says \"撰写权利要求\", \"draft claims\", \"写权利要求书\", \"claim drafting\", or wants to create patent claims. The core skill of the patent pipeline."
argument-hint: "[invention-disclosure-path]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Task
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Cross-model review uses a **Cursor Task subagent** per [reviewer-routing.md](../shared-references/reviewer-routing.md) — cross-family built-in model; `threadId` / resume = the subagent id (`Task(resume: ...)`).
> - `allowed-tools` frontmatter is advisory on Cursor.

# Claims Drafting: The Core Patent Skill

Draft patent claims based on: **$ARGUMENTS**

This is the most critical skill in the patent pipeline. Claims define the legal scope of protection -- everything else (specification, figures, abstract) exists to support and enable the claims.

## Constants

- `REVIEWER_MODEL` — cross-family Cursor built-in model per `shared-references/reviewer-routing.md` (Task subagent)
- `MAX_CLAIM_REVISION_ROUNDS = 3` — Maximum revision iterations
- `CLAIM_STYLE = "auto"` — `US` (Jepson or open), `EP` (two-part mandatory), `CN` (two-part), `auto` (detect from jurisdiction)
- `MIN_INDEPENDENT_CLAIMS = 2` — Typically method + system. For utility model (实用新型): apparatus/device only, NO method claims.
- `MAX_TOTAL_CLAIMS = 20` — Practical limit (USPTO includes 20 in base fee)
- `PATENT_TYPE = "invention"` — `invention` (发明专利) or `utility_model` (实用新型, apparatus claims only)

## Inputs

1. `patent/INVENTION_DISCLOSURE.md` — structured invention with core/supporting/optional features
2. `patent/PRIOR_ART_REPORT.md` — prior art to avoid
3. `patent/NOVELTY_ASSESSMENT.md` — novelty analysis with suggested amendments
4. Target jurisdiction from invention disclosure or `$ARGUMENTS`

## Shared References

Load `../shared-references/patent-writing-principles.md` for claim drafting principles, antecedent basis rules, and common pitfalls.
Load `../shared-references/patent-format-cn.md` for CN claim format (其特征在于).
Load `../shared-references/patent-format-us.md` for US claim format (comprising, means-plus-function).
Load `../shared-references/patent-format-ep.md` for EP two-part form (characterised in that).

## Workflow

### Step 1: Determine Claim Style and Patent Type

Based on patent type and jurisdiction:

**If `PATENT_TYPE = utility_model` (实用新型)**:
- CN jurisdiction ONLY
- Apparatus/device claims ONLY — no method, no product-by-process
- `MIN_INDEPENDENT_CLAIMS = 1` (single apparatus claim is sufficient)
- Claim format: "1. 一种[主题]，其特征在于，包括：[组件描述]。"

Based on target jurisdiction:

| Jurisdiction | Claim Style | Characterising Phrase | Preamble Format |
|-------------|------------|----------------------|-----------------|
| CN | Two-part (两部式) | 其特征在于 | 一种...的方法/装置，包括： |
| US | Open (preferred) | comprising | A method for..., comprising: |
| EP | Two-part (mandatory) | characterised in that | A method for..., comprising [known], characterised in that [inventive] |
| ALL | Draft CN + US + EP | All of the above | All of the above |

### Step 2: Draft Independent Claims

**Claims numbering format (Continuous sequential numbering)**:
- Claims must be numbered 1, 2, 3, ... continuously without gaps.
- Independent and dependent claims are intermixed in logical hierarchical order (e.g., Claim 1 independent apparatus, Claims 2–3 dependent on 1, Claim 4 independent method, Claims 5–6 dependent on 4). Do not group independent claims in an arbitrary separate block.

**Rule on Claim Language: Describe physical structures and procedural steps, not experimental results.**
- Avoid outcome-based descriptions or empirical observations (e.g., do not write "decreases resonant frequency", "produces negative pulse", or "achieves 99% accuracy" — these are performance results, not structural limitations).
- Use structural definitions and physical/procedural constraints (e.g., write "a resonant loop having an open gap defining a fluid-sensing channel" / "所述开口谐振环的开口处形成用于检测通过流体中颗粒物的间隙传感区域").

For each claim category identified in `INVENTION_DISCLOSURE.md`:

**Method Claim (broadest)**:
1. Start with preamble identifying the category and purpose
2. List the core inventive features (from the "Core Inventive Concept" section)
3. Include enough known features for context (but not more than necessary)
4. Use open transition ("comprising" / "包括")
5. Each element should be separated by semicolons or on separate lines
6. Apply jurisdiction-specific format:
   - CN: 前序部分 + "其特征在于" + 特征部分 (Two-part form)
   - US: Preamble + "comprising:" + elements (Open form)
   - EP: Preamble + known features + "characterised in that" + inventive features (Two-part form)

**System/Apparatus Claim**:
1. Mirror the method claim in structural form
2. Each method step becomes a "module configured to..." or "component for..."
3. Same hierarchy of known vs. inventive features

**Quality checks for each independent claim**:
- [ ] Single sentence (US/EP) or properly structured (CN)
- [ ] Antecedent basis (先行基础): "a" upon first introduction, "the/said (所述)" thereafter for each element
- [ ] No vague relative terms without quantitative baseline (e.g., "rapid", "thin", "strong")
- [ ] No result-to-be-achieved limitations (纯功能性描述/以结果为特征)
- [ ] Transitional phrase is appropriate (open transition "comprising / 包括" preferred over closed "consisting of / 由...组成")
- [ ] Preamble does not import unnecessary limitations
- [ ] Each element is necessary for patentability
- [ ] Claim scope is broadest defensible over prior art

### Step 3: Draft Dependent Claims

For each independent claim, draft 5-10 dependent claims that:

1. **Narrow the core inventive features**: Specific implementations, parameters, ranges
2. **Cover preferred embodiments**: Features from the specification's detailed description
3. **Provide fallback positions**: If the independent claim is rejected, these narrower claims may survive
4. **Cover alternatives**: Different ways to achieve the same inventive result

**Dependent claim format**:
- CN: "根据权利要求X所述的[主题]，其特征在于，所述[特征]具体为..."
- US: "The [method/system] of claim X, wherein the [element] comprises [limitation]."
- EP: "The [method/system] according to claim X, characterised in that [limitation]."

**Rules for dependent claims**:
- Each must add at least one meaningful limitation
- Must reference a prior claim by number
- Must not merely repeat the parent claim
- Should not be cumulative (each claim should be independently useful as a fallback)
- Multiple dependent claims (US: only "or" references, not "and")

### Step 4: Claim-to-Specification Mapping

Create a preliminary mapping to verify enablement:

| Claim Element | Must be described in specification | Reference numeral |
|---------------|-----------------------------------|-------------------|
| [element 1] | Yes/No | [numeral] |
| [element 2] | Yes/No | [numeral] |

If any element lacks specification support, add it to the specification requirements.

### Step 5: Cross-Model Examiner Review

Launch a fresh reviewer Task subagent (`model: REVIEWER_MODEL`, cross-family):

```
Task(
  subagent_type: "generalPurpose",
  description: "ARIS reviewer (cross-family)",
  model: REVIEWER_MODEL,   # cross-family max tier per reviewer-routing.md
  prompt: |
    You are a senior patent examiner at the [USPTO/CNIPA/EPO].
    Review the following patent claims for quality and patentability.

    CLAIMS: [all claims]

    PRIOR ART: [prior art references from PRIOR_ART_REPORT.md]

    INVENTION: [summary from INVENTION_DISCLOSURE.md]

    Analyze each claim for:
    1. Clarity & Definiteness (35 USC 112(b) / Art 84 EPC / CN Art 26): Are all terms clear and unambiguous?
    2. Written description support: Does the specification support all claimed subject matter?
    3. Anticipation (Novelty / 102 / Art 54 EPC / CN Art 22): Would any single reference anticipate any claim?
    4. Obviousness (Inventive Step / 103 / Art 56 EPC / CN Art 22): Would any combination render claims obvious to a POSITA?
    5. Claim scope: Are independent claims broad enough to be commercially valuable?
    6. Dependent claims: Do they provide meaningful fallback positions?
    7. Antecedent basis: Any issues with missing antecedents ("a" vs "the" / "所述")?
    8. Indefinite / Functional language: Any improper result-to-be-achieved phrasing?

    For each issue found, provide:
    - The specific claim number and element
    - The problem (cite statute/rule)
    - A suggested fix

    Provide an overall PATENTABILITY SCORE: 1-10.
```

### Step 6: Revision Loop

If the examiner review identifies issues:

1. Address all CRITICAL issues (anticipation, obviousness, indefiniteness)
2. Address MAJOR issues (scope too narrow, missing support, weak fallbacks)
3. Consider MINOR issues (antecedent basis, formatting)
4. Re-submit to examiner for round 2 (`Task(resume: <examiner agent id>)`)
5. Repeat up to `MAX_CLAIM_REVISION_ROUNDS` times

### Step 7: Output

Write `patent/CLAIMS.md`:

```markdown
## Patent Claims

### Independent Claims

#### Claim 1 — Method
[formatted claim text]

#### Claim X — System/Apparatus
[formatted claim text]

### Dependent Claims

#### Claim 2 (depends on 1)
[formatted claim text]

#### Claim 3 (depends on 1)
[formatted claim text]
...

### Claims Summary Table

| Claim | Type | Depends On | Key Limitation | Prior Art Avoidance |
|-------|------|-----------|----------------|---------------------|
| 1 | Method | — | [core inventive features] | [what makes it novel over prior art] |
| 2 | Method | 1 | [narrowing] | [additional distinguishing] |
| X | System | — | [mirrors claim 1] | [same as claim 1] |
...

### Examiner Review Summary
[Key findings and how they were addressed]
```

## Key Rules

- Claims are the single most important part of the patent. Everything else supports them.
- Draft independent claims first, then dependent claims.
- Independent claims must be broadest defensible scope over prior art -- not broader, not narrower.
- Each dependent claim should be independently useful as a fallback position.
- Antecedent basis is mandatory: "a processor" first, "the processor" thereafter.
- Use "comprising" (open) unless there is a specific reason for "consisting of" (closed).
- Never include result-to-be-achieved language in claims ("configured to achieve high accuracy").
- Never fabricate claim language -- every element must come from the actual invention.
- If drafting for ALL jurisdictions, produce separate claim sets for CN, US, and EP.
- If the Task tool is unavailable (rare), skip cross-model review and note it in the output.
