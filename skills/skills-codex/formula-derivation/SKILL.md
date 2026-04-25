---
name: "formula-derivation"
description: "Structure and derive research formulas when the task is to build the derivation itself from a problem statement or rough notes. Use for research-style derivation development. Do not use for theorem-proof writing once the exact claim is fixed; use `proof-writer` then."
---

# Formula Derivation

Use this skill when the task is not merely to prove a finished theorem, but to **build the derivation itself**:

## Routing Boundaries

- Use this skill when the main need is to construct the derivation line, assumptions, and intermediate objects.
- Use `proof-writer` when the claim is already fixed and the user wants a rigorous proof package.
- Do not use this skill as a generic math-explanation fallback when no derivation artifact is needed.

- define the right object,
- decide what should be assumed,
- determine what is identity vs proposition vs approximation,
- connect simple and general regimes without splitting into two unrelated stories,
- and turn messy notes into a derivation line that can later be written into a paper.

Do **not** use this skill as a replacement for strict proof writing once the exact claim is already fixed and the user wants a theorem-proof package. In that case, hand off to `proof-writer`.

## Core Principle

The derivation must be built around **one invariant object**. Do not start from scattered formulas. Start from the object that survives across regimes, then derive proxies, decompositions, and interpretations from it.

## What to Produce

Prefer one of these outputs:

1. a **mainline derivation note** for internal alignment;
2. a **paper-style theory draft** with tighter narrative;
3. a **blocker report** if the current notes cannot support a coherent derivation.

## Workflow

### 1. Freeze the Target

State explicitly:

- what phenomenon is being explained;
- what claim is being supported;
- whether the goal is:
  - identity / algebra,
  - local comparative statics,
  - approximation,
  - or mechanism interpretation.

Do not start symbolic manipulation before this is fixed.

### 2. Choose the Invariant Object

Find the single quantity that should remain meaningful across regimes.

Examples:

- objective / loss / utility
- total energy / cost / welfare
- state variable / conserved quantity / effective rate
- expected performance metric

If the current notes use a narrower quantity (`c_i`, throughput, delay, CW, etc.), decide whether it is:

- the true top-level object,
- or only a proxy / slice / approximation.

### 3. Put Assumptions and Notation First

Before deriving, list:

- assumptions;
- notation;
- regime boundaries;
- which quantities are fixed and which are state dependent.

Do not introduce hidden assumptions mid-derivation unless they are clearly marked as extra local assumptions.

### 4. Classify Every Step

Every nontrivial part of the derivation must be labeled mentally as one of:

- **identity**: exact algebraic reformulation;
- **proposition**: a claim requiring conditions;
- **approximation**: model simplification or surrogate;
- **interpretation**: prose-level explanation of what the formula means.

Never mix these without signaling the change.

### 5. Derive from the Global Quantity When Splitting Costs

If the goal is to split a quantity into components, start from the **global quantity** and then differentiate / decompose.

Pattern:

1. define the global quantity, e.g. `W = \sum_j \Gamma_j`;
2. perturb one local variable, e.g. `c_i`;
3. compute the marginal social effect;
4. split the result into:
   - direct term,
   - indirect term,
   - or private / external terms if that distinction is part of the model.

Do **not** present the decomposition as if it appeared magically from one local variable itself. The split must come from the effect of changing that variable on the chosen global quantity.

### 6. Keep Special Cases and General Cases in One Line

If the theory must cover both a simplified regime and a more general regime, do not write two unrelated stories.

Use this pattern:

- same invariant object across all regimes;
- special case: some terms vanish or collapse;
- general case: the same object gains extra structure.

This prevents the simple case from looking like an exception and the general case from looking like a different theory.

### 7. Treat Simplified Parameters as Analysis Slices

If the true object is state dependent, adaptive, vector-valued, or otherwise complicated, but a theorem needs a simpler parameterization, write:

- the general object first;
- then define the simpler case as a **tractable slice**.

Use language such as:

- frozen-parameter approximation;
- constant-coefficient slice;
- local linearization;
- reduced-order case.

Do not let the simplified case silently replace the real conceptual object.

### 8. Separate Main Text from Remarks

For derivations intended for papers:

- the **main derivation** should contain only equations and immediate mathematical consequences;
- explanatory prose, intuition, scenario reading, and caveats should be moved to **Remark / Discussion / Scope** paragraphs.

If a section starts to read like an internal lecture note, split it into:

- derivation body;
- remark.

### 9. Write Boundaries Explicitly

At the end, state:

- what the derivation actually proves;
- what remains approximation;
- what should **not** be claimed.

Especially guard against:

- turning a local proposition into a universal theorem;
- letting an interpretation sound like a proof;
- hiding a proxy as if it were the true quantity.

## Common Derivation Patterns

When the user is unsure how to start, try one of these common patterns:

1. **Definition -> substitution -> simplification**
   Use when the target formula is mostly algebraic.

2. **Global quantity -> perturbation -> decomposition**
   Use when the target needs direct / indirect, private / external, or local / global splitting.

3. **Primitive law -> intermediate variable -> target expression**
   Use when deriving from a physical principle, conservation law, or probabilistic identity.

4. **Exact model -> approximation -> interpretable closed form**
   Use when the exact formula is too heavy and a paper needs a usable surrogate.

5. **General dynamic object -> frozen slice -> theorem -> return to general case**
   Use when the real system is adaptive or state dependent, but the proof needs a simpler slice.

## Recommended Output Structure

For an internal derivation note:

1. Target
2. Invariant object
3. Assumptions and notation
4. Main derivation
5. Regime interpretation
6. Approximations and open risks

For a paper-style theory section:

1. Unified object
2. Formal proxy and assumptions
3. Special-case to general-case decomposition
4. Reward / objective reformulation
5. Local theorem or proposition
6. State-dependent extension
7. Scope and non-claims

## Relationship to `proof-writer`

Use `formula-derivation` when the user says things like:

- “我不知道怎么起这条推导主线”
- “这个公式到底该从哪个量出发”
- “帮我把理论搭顺”
- “把说明文档变成可写进论文的公式文档”

Use `proof-writer` only after:

- the exact claim is already fixed,
- the assumptions are stable,
- and the task is now to prove or refute that claim rigorously.
