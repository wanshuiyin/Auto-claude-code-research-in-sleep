# Patent Claims Worksheet

> **Template for pre-drafting claims structure.** Fill in before running `/claims-drafting`, or use as a reference during claim drafting.

## Invention Summary
[One-sentence description of the core inventive concept.]

## Independent Claims Plan

### Claim 1: Method Claim (broadest)
- **Preamble**: A method for [purpose], comprising:
- **Known features** (from prior art):
  1. [feature A]
  2. [feature B]
- **Inventive features** (novel):
  1. [feature C]
  2. [feature D]
- **Transition**: comprising / characterised in that (per jurisdiction)

### Claim X: System/Apparatus Claim (mirrors Claim 1)
- **Preamble**: A system for [purpose], comprising:
- **Structural components mapping to method steps**:
  1. [component corresponding to step 1]
  2. [component corresponding to step 2]
  ...

### Claim Y: Computer-Readable Medium Claim (US only, optional)
- Maps to method claim 1

## Dependent Claims Plan

| Claim # | Depends On | Adds Feature | Fallback Value |
|---------|-----------|-------------|----------------|
| 2 | 1 | [specific limitation of feature C] | Medium |
| 3 | 1 | [specific limitation of feature D] | Medium |
| 4 | 2 | [additional narrowing] | Low |
| 5 | 1 or 2 | [alternative implementation of C] | High |

## Claims Hierarchy (dependency tree)

```
1. (Independent — method, broadest)
├── 2. (narrows feature C)
│   └── 4. (narrows further)
├── 3. (narrows feature D)
├── 5. (alternative to 2 or 3)
│
X. (Independent — system, mirrors 1)
├── X+1. (narrows component)
├── X+2. (narrows component)
│
Y. (Independent — medium, US only, mirrors 1)
```

## Prior Art Avoidance Matrix

| Claim Element | Prior Art Reference | Avoidance Strategy |
|---------------|--------------------|--------------------|
| Feature C | [Ref X] | Ref X uses different approach... |
| Feature D | [Ref Y] | Ref Y doesn't combine C+D... |
| Combination C+D | [Ref X + Y] | No motivation to combine... |

## Jurisdiction-Specific Formatting Notes

### CN (Chinese)
- Use "其特征在于" to separate known and inventive features
- Method: "一种...的方法，包括：...；其特征在于，还包括：..."
- Apparatus: "一种...的装置，包括：...；其特征在于，还包括：..."

### US
- Use "comprising" (open transition)
- Method: "A method for [purpose], comprising: [step A]; [step B];..."
- System: "A system for [purpose], comprising: [component A]; [component B];..."

### EP
- Two-part form MANDATORY (Rule 43(1) EPC)
- "A method for [purpose], comprising [known features], characterised in that [inventive features]."
- "A system for [purpose], comprising [known components], characterised in that [inventive components]."
