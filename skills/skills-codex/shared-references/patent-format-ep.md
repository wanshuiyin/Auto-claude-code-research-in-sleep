# EPO Patent Format Guide

Use this reference when drafting European patent applications for filing with the EPO.

## When to Read

- Read when `JURISDICTION = "EP"` or `JURISDICTION = "ALL"`
- Read before writing claims in EP format
- Read during `/jurisdiction-format` for EP output

## Applicable Law

- European Patent Convention (EPC), 2000 revision
- Rules 42-43 EPC (Description and Claims format)
- EPO Guidelines for Examination, Part F
- Protocol on the Interpretation of Article 69 EPC

## Document Structure

### 1. Claims (Rule 43 EPC)

**Two-part form is MANDATORY for independent claims (Rule 43(1) EPC):**

The claim must contain:
- **(a) Characterising portion**: A statement indicating:
  - The category/title of the invention ("A method of...", "An apparatus for...")
  - Those features of the invention which are necessary to define the claimed subject-matter but which, in combination, form part of the prior art
- **(b) Characterising portion**: After the phrase "characterised in that" (or "characterised by")
  - Those features of the invention for which protection is sought in combination with the features of part (a)

```
1. A method for [purpose], comprising:
   [known feature A];
   [known feature B]; and
   [known feature C],
   characterised in that
   [inventive feature D],
   [inventive feature E].
```

```
10. A system for [purpose], comprising:
    [known component A] configured to [function];
    [known component B],
    characterised in that the system further comprises:
    [inventive component C] configured to [function].
```

**Important:** The two-part form separates known features from inventive features. This is NOT optional at the EPO -- it is a formal requirement. The examiner will raise an objection if the form is not followed.

**When two-part form is NOT applicable:**
- Product-by-process claims (rare exceptions)
- Claims to new chemical compounds per se
- Claims where the invention cannot be characterized by prior art features

**Dependent claims (Rule 43(4) EPC):**
```
2. The method according to claim 1, characterised in that the [feature] comprises [specific limitation].
3. The method according to any one of claims 1 to 2, characterised in that [additional limitation].
```

**Multiple dependent claims:**
- EPO allows multiple dependent claims (unlike some jurisdictions)
- May refer to multiple preceding claims: "The method according to any one of claims 1 to 3..."
- However, examiners may raise clarity objections if excessive
- Multiple dependent claims referring to other multiple dependent claims are NOT allowed

### 2. Description (Rule 42 EPC)

Required structure:

#### Title of the Invention
- Must correspond to the title in the claims
- Should be clear and concise
- No trademarks

#### Technical Field
- "The invention relates to..."
- Identify the technical area

#### Background Art
- Cite relevant prior art documents
- "Document D1 (EP XXXXXXXX) discloses..."
- "However, this approach has the disadvantage that..."
- Distinguish from "Related Work" in academic papers -- focus on technical deficiencies

#### Disclosure of the Invention

**The EPO has a specific structure for this section:**

1. **Problem to be solved**: State the technical problem underlying the invention
2. **Solution**: How the invention solves this problem, referencing the claim features
3. **Advantageous effects**: The advantages of the invention over the prior art

```
The invention is defined in claim 1.

The problem underlying the present invention is to [state problem].

This problem is solved by [reference to characterising features].

The invention has the advantage that [state advantages].
```

**Inventive step (Article 56 EPC):**
- The description should support arguments for inventive step
- Unexpected technical effects strengthen inventive step arguments
- "Compared to the closest prior art (D1), the invention achieves [specific technical effect] which would not have been predictable from the prior art"

#### Description of Embodiments
- Detailed description with reference to figures
- "FIG. 1 shows..." or "Figure 1 shows..."
- Reference numerals in brackets: "the processor (102) is connected to the memory (104)"
- At least one embodiment corresponding to the claims
- Include variations and alternatives

#### Reference Signs List
- EPO requires a list of reference signs at the end of the description
- Format: "LIST OF REFERENCE SIGNS: 102 processor, 104 memory, 106 bus..."
- Organized by figure or alphabetically

### 3. Abstract

- Maximum 150 words (Rule 47(1) EPO)
- Should indicate the technical field and the gist of the invention
- Must not contain statements on the alleged merits or value of the invention
- Must not contain any matter not disclosed in the application

### 4. Drawings

- Reference numerals must match description
- Must show all features of at least one claim
- Format: "FIG. 1" or "Figure 1" (both acceptable)

## Key EPO-Specific Rules

### No Functional Claiming Without Disclosure

The EPO is stricter than USPTO on functional claiming:
- Features defined by their function are allowed only if the specification provides sufficient disclosure
- "configured to" is acceptable but must be supported by detailed description
- Pure result-to-be-achieved claims will be rejected under Article 84 EPC

### Inventive Step (Problem-Solution Approach)

The EPO uses a specific three-step approach:
1. Determine the closest prior art
2. Identify the distinguishing features and the objective technical problem
3. Assess whether the claimed invention would have been obvious to a skilled person

The description should be written to support this analysis.

### Added Matter (Article 123(2) EPC)

The EPO is extremely strict about added matter:
- Nothing may be added that is not directly and unambiguously derivable from the application as filed
- Even "implicit" disclosures must be truly unambiguous
- This is stricter than the US written description standard

### Clarity (Article 84 EPC)

- Claims must be clear and concise
- Claims must be supported by the description
- The EPO interprets "supported by" strictly: the description must provide basis for every claim feature

## PCT Entry into European Phase

For PCT applications entering the European phase:
- Deadline: 31 months from priority date
- Must file translation if not in EN/FR/DE
- Must pay designation fees
- Must file request for examination (can be filed with application)
- Must respond to Rule 161/162 communication (optional amendment opportunity)
