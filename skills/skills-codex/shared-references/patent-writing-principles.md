# Patent Writing Principles

Use this reference when `claims-drafting`, `specification-writing`, or `invention-structuring` need guidance on patent-specific writing rules.

## When to Read

- Read before drafting any claims.
- Read when specification text needs to support claim scope.
- Read when choosing between claim formats (Jepson vs. two-part vs. open-ended).
- Read when the language feels too academic or too vague for patent purposes.
- Read before jurisdiction-specific formatting.

## Contents

- [Core Patent Writing Rules](#core-patent-writing-rules)
- [Claim Drafting Principles](#claim-drafting-principles)
- [Specification Writing Rules](#specification-writing-rules)
- [Common Pitfalls](#common-pitfalls)
- [Terminology Discipline](#terminology-discipline)

---

## Core Patent Writing Rules

### The Three Requirements

Every patent application must satisfy three fundamental requirements:

1. **Novelty** (新颖性): The invention must be new -- not anticipated by a single prior art reference.
2. **Inventive Step / Non-obviousness** (创造性): The invention must not be obvious to a person skilled in the art (POSITA) based on prior art.
3. **Industrial Applicability / Utility** (实用性): The invention must be capable of being made or used in industry.

### The Written Description Requirement

The specification must demonstrate that the inventor was in **possession** of the claimed invention as of the filing date. This means:

- Every element in every claim must find explicit or inherent support in the specification.
- Broader claims require broader disclosure. If you claim "a processor," the spec must show you had a processor in mind, not just one specific chip.
- Adding claim scope after filing that wasn't in the original disclosure is not permitted (no new matter).

### The Enablement Requirement

The specification must teach a **Person Skilled in the Art (POSITA)** to make and use the invention without undue experimentation. Test: could a skilled practitioner reproduce the invention from your description alone?

### Claims Define Scope, Specification Enables It

- **Claims** = the legal boundary (what is protected)
- **Specification** = the teaching (how to practice the invention)
- **Figures** = the visual aid (reference numerals link claims to specification)

---

## Claim Drafting Principles

### Broadest Reasonable Interpretation (BRI)

Claims are interpreted under the **broadest reasonable interpretation** during prosecution (USPTO standard; EPO uses a different but analogous approach). This means:

- Common words are given their ordinary meaning.
- Terms are NOT limited to the embodiments described in the specification.
- If you want a term to have a special meaning, you must explicitly define it in the specification.

### Claim Structure (Universal)

Every claim has:
1. **Preamble**: Identifies the category of invention (e.g., "A method for...", "A system comprising...", "An apparatus for...")
2. **Transitional phrase**: Defines scope boundary
   - "comprising" / "including" / "containing" = OPEN (additional elements allowed)
   - "consisting of" = CLOSED (no additional elements)
   - "consisting essentially of" = SEMI-OPEN (allows insubstantial variations)
3. **Body**: The claim elements/limitations, each separated by semicolons or commas

### Antecedent Basis

- First mention of an element: use indefinite article ("a", "an") -- "a processor"
- Subsequent mentions: use definite article ("the", "said") -- "the processor"
- Never use "the" for something not previously introduced in the claim.
- Never use "a" again for the same element (implies a second instance).

### Independent vs. Dependent Claims

**Independent claims** define the broadest defensible scope. Draft these first.

**Dependent claims** narrow the scope by adding specific limitations. Each dependent claim:
- Must refer back to a prior claim ("The method of claim 1, wherein...")
- Must add at least one meaningful limitation
- Should provide fallback positions if the independent claim is rejected
- Should cover preferred embodiments described in the specification

### Multiple Claim Categories

For the same invention, draft claims in multiple categories:
- **Method/process claims**: Steps performed
- **System/apparatus claims**: Structural components
- **Computer-readable medium claims**: (US) Tangible medium storing instructions
- **Product-by-process claims**: (when structure is difficult to define)

This multiplies the scope of protection without requiring separate applications.

---

## Specification Writing Rules

### Section Structure (Universal)

1. **Title**: Concise, matches broadest claim scope, no trademark names, no "improved" or "new"
2. **Technical Field** (技术领域): 1-2 paragraphs identifying the technical domain
3. **Background** (背景技术): Prior art and its deficiencies -- NOT a literature review, but specific technical shortcomings that the invention addresses
4. **Summary** (发明内容): Problem-Solution-Advantage triple
5. **Brief Description of Drawings** (附图说明): One sentence per figure
6. **Detailed Description** (具体实施方式): Detailed embodiments with reference numerals
7. **Abstract** (摘要): Jurisdiction-specific word limits

### Language Rules for Specifications

**DO:**
- Use "embodiment", "aspect", "implementation", "configuration"
- Use "optionally", "preferably", "in some implementations"
- Use "may" for optional features, "shall" or "is configured to" for required features
- Reference figures by numeral: "As shown in FIG. 1, the processor 102..."
- Use consistent terminology throughout (same word for same concept)

**DO NOT:**
- Use subjective adjectives: "excellent", "surprising", "revolutionary", "superior"
- Use result-to-be-achieved language: "configured to achieve high accuracy" (instead describe HOW)
- Use relative terms without definition: "thin", "strong", "fast", "small"
- Admit prior art is better: avoid "unlike the prior art, which works well, we..."
- Include experimental results tables (save for prosecution arguments, not the spec itself)

### Reference Numeral Convention

- Use consistent numbering series: 100-series for FIG. 1, 200-series for FIG. 2
- Every component mentioned in specification must have a numeral
- Every numeral in figures must be explained in the specification
- Format: "processor 102", "memory 104", "bus 106" (numeral follows the noun)

---

## Common Pitfalls

### Negative Limitations

Avoid claims that define the invention by what it is NOT:
- Bad: "A method that does not use a database"
- Good: "A method comprising storing data in a local cache"

Negative limitations are sometimes necessary but require explicit basis in the specification.

### Result-to-Be-Achieved Claims

Do not claim a result without describing the mechanism:
- Bad: "A method for achieving 99% accuracy in image classification"
- Good: "A method comprising: extracting features using a convolutional neural network having at least three residual blocks..."

### Indefinite Terms

Avoid terms that create uncertainty about scope:
- "approximately", "about", "substantially" -- acceptable if the specification defines the range
- "high quality", "efficient", "optimal" -- too vague, will receive 112(b) rejection (US)
- "etc.", "and the like", "or similar" -- creates open-ended ambiguity

### Functional Claiming (Means-Plus-Function)

In US practice, "means for [function]" triggers 35 USC 112(f) and is limited to the corresponding structure in the specification. Use with caution:
- "means for processing" = limited to the specific processor embodiments described
- "a processor configured to process" = broader (not means-plus-function)
- In CN/EP practice, functional claiming is generally more restrictive

### Claim Differentiation Doctrine

Dependent claims are presumed to have different scope from their parent claims. Do not:
- Copy the parent claim verbatim into a dependent claim
- Add a limitation that is already inherent in the parent claim
- Create dependent claims that are merely cumulative combinations of other dependent claims

---

## Terminology Discipline

### Consistency Rule

Once a term is introduced, use it identically throughout:
- Do NOT alternate between "processor", "processing unit", "CPU", "computing device" for the same component
- If the invention has a specific component, name it once and reuse that name

### Definition Rule

If a term has a meaning specific to your invention:
1. Define it explicitly in the specification
2. Use "hereinafter referred to as" or "herein defined as" language
3. Use the defined term consistently thereafter

### Jurisdiction-Specific Terminology

- **CN**: Use standard patent Chinese. "所述" (said/the), "其特征在于" (characterized in that), "一种...的方法/装置" (a method/apparatus for...)
- **US**: Use standard patent English. "comprising", "configured to", "in communication with"
- **EP**: Follow EPO Guidelines for Examination. Two-part claim form mandatory.
