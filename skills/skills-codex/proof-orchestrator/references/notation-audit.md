# Proof Notation Audit

Apply this audit after correctness checking and before writing `final.md`.
Treat the thresholds as editing gates, not mathematical laws. Keep a warning
only when the notation genuinely shortens the proof, and record why.

## Required Inventory

First identify the semantic center from the theorem statement, algorithm
update, and final conclusion: the state variable, policy or distribution,
operator, objective, and their dependency direction. Then record each
nonstandard symbol's meaning, scope, first definition, and number of later uses.
Classify it as `core`, `keep`, `localize`, `inline`, `rename`, or `delete`.
Exclude bound variables, summation indices, and standard operators.

Report these seven metrics in `audit.md` with the exact labels and order below.
Do not substitute related measures such as "overloaded symbols," "irrelevant
chains," or a prose summary:

```text
Core semantic objects retained: <retained>/<declared> (<percent>)
Undefined symbols: <count>
Symbol collisions: <count>
One-use definitions: <count>/<all new symbols> (<percent>)
Maximum parallel representations of one object: <count>
Maximum alias-chain depth: <count>
Maximum active nonstandard symbols in one proof step: <count>
```

## Blocking Rules

Do not mark `READY_FOR_USER` unless core-object retention is 100% and both
counts below are zero:

- **Core-object loss:** a rewrite deletes, hides, or replaces a theorem's
  central state, policy or distribution, operator, objective, or dependency
  direction. A coordinate chart is not a substitute for the object it
  parameterizes.

- **Undefined symbol:** a symbol appears before its meaning and scope are clear.
- **Collision:** the same glyph denotes different objects anywhere in the
  artifact. Different subscripts do not cure a changed base meaning.

Prefer the established or standard meaning. Rename or remove the other use.
Do not rely on distant section boundaries to make a collision harmless.

Keep local coordinates only when they reduce calculations. State their map to
the core object at first use, and express every main theorem, flow, or final
bound again through the core object. Fewer glyphs do not compensate for a
changed mathematical interface.

Do not reduce blocker counts by supplying plausible missing mathematics. A
notation rewrite may rename or inline supported expressions, but it must not
invent a domain, assumption, derivative identity, sign relation, theorem
hypothesis, or definition. Leave an unresolved item in the scorecard and mark
the proof unusable until authoritative material resolves it.

## Warning Thresholds

### Definition Payoff

Keep a new symbol only if at least one condition holds:

- it appears in three or more later formulas;
- it appears in both a theorem statement and its proof;
- it names an object that the prose compares, varies, or cites later.

Inline an expression of roughly 12 characters or fewer when it appears at most
twice. A local abbreviation may remain when expanding it would obscure a long
derivation, but its scope must end with that derivation.

### One-Use Definitions

- Good: at most 10% of new symbols.
- Warning: more than 10% and at most 20%.
- Bad: more than 20%.

A one-use definition appears only in the immediately following sentence or
formula. Do not count bound variables or standard local placeholders.

### Parallel Representations

- Good: at most two persistent representations per object, such as a
  probability and its logit.
- Bad: three or more persistent representations.

Permit a third representation only inside one local derivation. Remove it when
the subsection ends.

### Alias-Chain Depth

- Good: one layer; a symbol refers directly to the original quantities.
- Warning: two layers.
- Bad: three or more layers.

Flatten chains such as `K := M+2`, `lambda := a/K`, `S := lambda x+b`, when the
last alias serves only one inequality.

### Active Symbol Load

Count the nonstandard symbols a reader must remember across one theorem
statement, proof paragraph, or uninterrupted formula chain.

- Good: at most 8.
- Warning: 9--12.
- Bad: more than 12.

When the count exceeds 8, split the argument, localize definitions, or inline
temporary aliases. Do not remove proof steps merely to lower the count.

### Definition Distance

Define a symbol within the paragraph before its first use. End local symbol
scope at the subsection boundary. A reader should not need to cross a section
boundary to recover a definition unless the symbol belongs to the theorem's
declared global notation.

## Rewrite Order

1. Identify and freeze the semantic center and dependency direction.
2. Fix undefined symbols and collisions.
3. Delete unused non-core symbols.
4. Inline one-use definitions and flatten alias chains.
5. Limit persistent representations of each object.
6. Split steps whose active symbol load remains above 8.
7. Map coordinate conclusions back to the core objects.
8. Recheck every substitution and theorem dependency.
9. Only then remove redundant prose or obvious algebra.

If a shorter rewrite would require a new mathematical relation, output a
diagnosis rather than a repaired proof.

Preserve a longer expression when a new name carries mathematical meaning.
Never trade correctness or a verifiable non-obvious step for a lower symbol
count.
