---
name: patent-novelty-check
description: "Assess patent novelty and non-obviousness against prior art. Use when user says \"专利查新\", \"patent novelty\", \"可专利性评估\", \"patentability check\", or wants to evaluate if an invention is patentable."
argument-hint: "[invention-description-or-brief-path]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Task
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Cross-model review uses a **Cursor Task subagent** per [reviewer-routing.md](../shared-references/reviewer-routing.md) — cross-family built-in model; `threadId` / resume = the subagent id (`Task(resume: ...)`).
> - `allowed-tools` frontmatter is advisory on Cursor.

# Patent Novelty and Non-Obviousness Check

Assess patentability of: **$ARGUMENTS**

Adapted from `/novelty-check` for patent legal standards. Research novelty is NOT the same as patent novelty.

## Constants

- `REVIEWER_MODEL` — cross-family Cursor built-in model per `shared-references/reviewer-routing.md` (Task subagent)
- `NOVELTY_STANDARD = patent` — Always use legal patentability standard, not research contribution standard

## Inputs

1. Invention description from `$ARGUMENTS`
2. `patent/PRIOR_ART_REPORT.md` (output of `/prior-art-search`)
3. `patent/INVENTION_BRIEF.md` if exists

## Shared References

Load `../shared-references/patent-writing-principles.md` for novelty/non-obviousness standards.
Load `../shared-references/patent-format-us.md` for 102/103 analysis framework.

## Workflow

### Step 1: Define Claim Elements

From the invention description, extract the key claim elements that would define the invention's scope:
1. List the technical features that make the invention novel
2. Identify which features are known from prior art vs. inventive
3. Draft preliminary claim language for 2-3 independent claims (method + system)

### Step 2: Anticipation Analysis (Novelty / 新颖性)

For each preliminary claim, test against EACH prior art reference in `PRIOR_ART_REPORT.md`:

**Single-reference test**: Does any single reference disclose ALL claim elements?

| Claim Element | Ref 1 | Ref 2 | Ref 3 | ... |
|--------------|-------|-------|-------|-----|
| Feature A | Yes/No + evidence | | | |
| Feature B | Yes/No + evidence | | | |
| Feature C | Yes/No + evidence | | | |
| Feature D | Yes/No + evidence | | | |

**Verdict per reference (Novelty / 35 USC § 102 / CN Article 22)**:
- **ANTICIPATED (已公开 / 无新颖性)**: A single prior publication reveals all claimed features → claim is not novel.
- **NOT ANTICIPATED (具备新颖性)**: At least one claimed feature is missing from every single reference → claim is novel.

### Step 3: Obviousness Analysis (Inventive Step / 创造性)

If the invention is novel (passes Step 2), test for obviousness:

**Two/three-reference combination test**: Can 2-3 references be combined to render the claim obvious?

For each combination of the top references:
1. **Primary reference**: Which reference is closest to the claimed invention?
2. **Secondary reference(s)**: Which reference(s) teach the missing element(s)?
3. **Motivation to combine**: Would a Person Having Ordinary Skill in the Art (POSITA, 本领域技术人员) find it natural or obvious to combine these references?
   - Explicit suggestion in the references themselves?
   - Same field, same problem?
   - Common design incentive?
   - Known technique for improving similar devices?

Format as a matrix:

| Combination | Primary | Secondary | Missing Elements | Motivation to Combine | Obvious? (显而易见性) |
|-------------|---------|-----------|-----------------|----------------------|-----------------------|
| Ref1 + Ref2 | Ref1 | Ref2 | Feature D | Same field, similar problem | Yes/No |

### Step 4: Cross-Model Examiner Verification

Launch a fresh reviewer Task subagent (`model: REVIEWER_MODEL`, cross-family):

```
Task(
  subagent_type: "generalPurpose",
  description: "ARIS reviewer (cross-family)",
  model: REVIEWER_MODEL,   # cross-family max tier per reviewer-routing.md
  prompt: |
    You are a senior patent examiner at the [USPTO/CNIPA/EPO].
    Examine the following invention for patentability.

    INVENTION: [invention description + preliminary claims]

    PRIOR ART: [prior art references with key teachings]

    Please analyze:
    1. Anticipation (novelty / 35 USC § 102): Does any single reference anticipate any claim?
    2. Obviousness (inventive step / 35 USC § 103): Can any combination of references render claims obvious to a POSITA?
    3. Claim scope: Are the claims broad enough to be valuable?
    4. Recommended amendments if any claim is rejected.
    Be rigorous and cite specific references.
```

### Step 5: Jurisdiction-Specific Assessment

For each target jurisdiction, provide a patentability assessment with clear plain-language summaries:

**Under US Patent Law (35 USC § 102 Novelty / § 103 Non-Obviousness)**:
- Novelty (§ 102): PASS / FAIL (cite specific reference if fail; explain why no single reference discloses all elements)
- Non-obviousness (§ 103): PASS / FAIL (cite combination if fail; explain why a POSITA would not find the combination obvious)

**Under Chinese Patent Law (Article 22 CNIPA / 中国专利法第二十二条)**:
- 新颖性 (Novelty): 通过 (PASS) / 未通过 (FAIL) — 现有技术中未公开全部技术特征
- 创造性 (Inventive Step): 通过 (PASS) / 未通过 (FAIL) — 具备突出的实质性特点和显著的进步

**Under European Patent Law (Article 54/56 EPC)**:
- Novelty (Art 54 EPC): PASS / FAIL
- Inventive step (Art 56 EPC): PASS / FAIL (using the Problem-Solution Approach)

### Step 6: Output

Write `patent/NOVELTY_ASSESSMENT.md`:

```markdown
## Patentability Assessment

### Invention Summary
[description]

### Overall Assessment
[PATENTABLE / PATENTABLE WITH AMENDMENTS / NOT PATENTABLE]

### Anticipation Analysis
[claim-by-claim matrix against each reference]

### Obviousness Analysis
[combination analysis with motivation to combine]

### Cross-Model Examiner Review
[summary of the cross-family examiner feedback]

### Recommended Claim Amendments
[If claims need modification to overcome prior art, suggest specific amendments]

### Risk Factors
[What could cause rejection during actual prosecution?]
```

## Key Rules

- Patent novelty is absolute: any public disclosure before the priority date counts as prior art, worldwide.
- Research novelty ("has anyone published this?") is NOT the same as patent novelty ("does any single reference teach every claim element?").
- Obviousness requires BOTH: (1) a combination of references AND (2) a motivation to combine them.
- Never assume the invention is patentable just because no identical patent exists.
- The assessment is advisory only -- actual prosecution may reveal different prior art.
- If the Task tool is unavailable (rare), skip cross-model review and note it in the output.
