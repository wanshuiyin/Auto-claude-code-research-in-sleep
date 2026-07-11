# Evidence Pre-check

ARIS's claim audits (`/result-to-claim`, `/experiment-audit`, `/paper-claim-audit`)
spend a cross-model (codex/gemini) call to judge whether a claim is supported. The
cheapest, most common integrity failure is *hallucinated evidence*: a claim cites
a number + a source file, and the file doesn't exist or the number isn't in it.
You should not need a model call to catch that.

## Two stages — and `verified` ≠ `correct`

```
stage 1  tools/evidence_check.py   deterministic · no model · fail-closed
         catches HALLUCINATION — cited path missing, or cited value not in source.
stage 2  the cross-model jury      codex/gemini
         catches WRONG-BUT-REAL — the number IS in the file, but it doesn't
         support the claim.
```

A `verified` from stage 1 means **only that the cited evidence exists** — never
that the claim holds. Existence is execution-completeness (deterministic / safe
same-model); *support* is a quality verdict that stays with the cross-model jury
(`acceptance-gate.md`: the pre-check DRIVES a gate, it cannot ACQUIT a claim).
This is the reconcile pattern — a model's self-report cross-checked against
mechanical ground-truth (adapted from Hermes's curator reconcile-classifier),
made into a cheap pre-gate that catches hallucination *before* the jury runs and
spares the codex call on fabricated evidence.

## Conservative by design

The pre-check favors **false-negative over false-positive**: when in doubt it
returns not-verified and lets the jury decide — it must never emit a false
`verified`. A pure number is matched by **numeric-token equality** (so `73.2`
matches `73.20` but `73` does NOT match `73.5`); a non-numeric value by
normalized substring.

## Where ARIS uses it

- **`/result-to-claim`** Step 1.5: parse each claim's cited `(value, source)`,
  run the batch pre-check, and **before the codex judgment** mark any claim whose
  evidence is `path_missing` / `value_not_found` as **unsupported — evidence not
  found**, and pass the per-claim pre-check status into the codex prompt so the
  jury sees which claims have verified vs hallucinated evidence.
- **To extend:** `/experiment-audit` (the "phantom results" check is exactly
  this) and `/paper-claim-audit` (every reported number → its result file).

## API / CLI

```
from evidence_check import check_claim, check_batch
check_claim(value, source, root=".")   # -> {status: verified|path_missing|value_not_found, ...}
check_batch([{value, source, id?}, ...], root)  # -> {results:[...], summary:{status: n}}
```
```
python3 tools/evidence_check.py <root> --value 73.2 --source results/eval.json   # exit 0 verified
python3 tools/evidence_check.py <root> --batch claims.json   # exit 1 if any claim hallucinated
```

## Cross-references
- `acceptance-gate.md` — the pre-check is the deterministic DRIVE; the jury is the
  ACQUIT. `verified` is existence (execution-completeness), not correctness.
- `reviewer-independence.md` — the jury still reads the artifacts itself; the
  pre-check only flags which claims have evidence to read, never pre-digests the
  verdict.
- `experiment-integrity.md` — fabricated/phantom results are exactly what stage 1
  catches deterministically before stage 2.
