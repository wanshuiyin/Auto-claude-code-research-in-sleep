# USPTO Patent Format Guide

Use this reference when drafting US patent applications for filing with USPTO.

## When to Read

- Read when `JURISDICTION = "US"` or `JURISDICTION = "ALL"`
- Read before writing claims in US format
- Read during `/jurisdiction-format` for US output

## Applicable Law

- Title 35, United States Code
- Manual of Patent Examining Procedure (MPEP), 9th Edition, Rev. 2024
- America Invents Act (AIA, 2011)

## Document Structure

A USPTO patent application consists of:

### 1. Claims Section

**Format rules:**
- Claims are numbered sequentially with Arabic numerals starting from 1
- Independent claims stand alone; dependent claims reference prior claims
- Each claim is a single sentence (grammatically complex but technically one sentence)
- Use semicolons to separate elements within a claim

**Claim Preamble Types:**

**Process/Method claims:**
```
1. A method for [purpose], comprising:
   [step A];
   [step B]; and
   [step C].
```

**System/Apparatus claims:**
```
10. A system for [purpose], comprising:
    a [component A] configured to [function];
    a [component B] in communication with the [component A]; and
    a [component C] configured to [function].
```

**Computer-readable medium claims (US-specific):**
```
15. A non-transitory computer-readable storage medium storing instructions that, when executed by a processor, cause the processor to perform operations comprising:
    [operation A];
    [operation B].
```

**Transitional Phrases:**
| Phrase | Type | Meaning |
|--------|------|---------|
| comprising | Open | Includes the listed elements but may also include others |
| consisting of | Closed | Limited to ONLY the listed elements |
| consisting essentially of | Semi-open | Allows only insubstantial additional elements |

**Default: use "comprising"** unless there is a specific reason to use a closed transition.

**Dependent Claim Format:**
```
2. The method of claim 1, wherein the [element] comprises [specific limitation].
3. The method of claim 1 or claim 2, further comprising [additional step].
4. The system of claim 10, wherein the [component A] is a [specific type].
```

**Multiple Dependent Claims (US rules):**
- US allows multiple dependent claims but ONLY in the alternative ("or", not "and")
- "The method of claim 1 or claim 2, wherein..." -- VALID
- "The method of claims 1 and 2, wherein..." -- INVALID
- Each multiple dependent claim counts as one claim for fee purposes

### 2. Specification

#### Title
- Concise and specific (MPEP 606)
- No more than 500 characters
- No trademarks, no "improved", no "new"
- Must describe the invention, not its use

#### Cross-Reference to Related Applications
- If claiming priority to earlier applications, include at the very beginning
- Format: "This application claims the benefit of U.S. Provisional Application No. XX/XXX,XXX, filed [date]"

#### Statement Regarding Federally Sponsored Research
- Include if invention was made with government funding

#### Field of the Invention
- 1-2 sentences: "The present invention relates generally to [field], and more particularly to [specific area]."

#### Background of the Invention
- Describe the field
- Describe existing approaches and their limitations
- Do NOT admit prior art as "the best" or "superior"
- Set up the technical problem the invention solves
- Do NOT include citations to prior art here (that's for IDS)

#### Brief Summary of the Invention
- "In accordance with one or more embodiments..."
- Problem-Solution-Advantage structure
- Mirror the claim scope

#### Brief Description of the Drawings
- "FIG. 1 is a block diagram showing..."
- "FIG. 2 is a flowchart illustrating..."
- One sentence per figure

#### Detailed Description of Preferred Embodiments
- Must enable a POSITA to make and use the invention (35 USC 112(a))
- Must provide written description support for all claim scope (35 USC 112(a))
- Reference numerals: use consistent numbering (100-series for FIG. 1, 200-series for FIG. 2)
- Include at least one "preferred embodiment" or "exemplary embodiment"
- Describe alternatives and variations to support broad claim interpretation
- Best mode: must disclose the best way known to the inventor (less enforced post-AIA but still required by statute)

#### Abstract
- 150 words or 2500 characters maximum (37 CFR 1.72(b))
- Purpose: enable efficient prior art searching
- Include the most important technical features
- Do NOT include legal phrases or claim references

### 3. Drawings (Figures)

- Must show every feature specified in the claims
- Reference numerals must match specification
- Black and white line drawings preferred
- Format: "FIG. 1", "FIG. 2" (not "Figure 1")
- No text except reference numerals and essential labels

## IDS (Information Disclosure Statement)

Under the duty of disclosure (37 CFR 1.56), applicants must cite all known material prior art:
- List all patents, publications, and other references known to be material
- Use form PTO/SB/08 for listing references
- Filed during prosecution, not as part of the initial application

## Means-Plus-Function (35 USC 112(f))

When a claim element uses "means for [function]" or equivalent language:
- The claim is limited to the corresponding structure, material, or acts described in the specification AND equivalents thereof
- Must disclose the algorithm/structure that performs the function
- Software "means for" claims MUST disclose the algorithm (flowchart, pseudocode)

**Safer alternative:** Use "a processor configured to [function]" instead of "means for [function]"

## Continuation and CIP Strategy

- **Continuation**: Same disclosure, new claims
- **Continuation-in-part (CIP)**: Adds new matter, claims to new matter get new priority date
- **Divisional**: Required when examiner issues restriction requirement

## Common 102/103 Rejection Responses

Document these patterns for use in `/patent-review`:
- Amend claims to distinguish over cited reference
- Argue the reference does not teach a specific claim element
- Argue the combination of references would not have been obvious
- Provide evidence of unexpected results or commercial success
