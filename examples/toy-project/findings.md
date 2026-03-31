# Findings

- Count-only summaries retain a weak signal at short lengths, but the advantage shrinks rapidly with sequence length.
- The task is exactly solvable once boundary information is restored; there is no optimization difficulty hiding the result.
- Exhaustive enumeration is enough for this toy setting, which keeps the example deterministic and easy to reuse in demos.
