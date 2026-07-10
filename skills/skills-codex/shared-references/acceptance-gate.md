# Acceptance-Gate Provenance

> **Codex mirror adaptation (normative).** In this mirror the executor is the
> current Codex agent and the default reviewer is a fresh `spawn_agent` Codex
> agent. That route is same-family: it may drive revisions and terminate a loop,
> but its positive verdict is recorded as `acceptance_status: provisional` and
> never as cross-family `accepted`. A Claude/Gemini overlay or a deterministic
> verifier may record `accepted`. Where the mainline examples name Claude or
> `mcp__codex__codex`, read them as current executor or fresh `spawn_agent`;
> follow-up dialogue uses `send_input` only when continuity is intentional.

## Core Principle

**An autonomous loop's STOP/ACCEPT gate determines its assurance level. The
thing being judged at that gate — not the loop's subject matter, not how many
agents ran — decides whether a base Codex review is provisional or an overlay /
deterministic route may mark it accepted.** (A deterministic verifier accepts
only what a PROCESS can actually decide — compilation, schema validity, hash
freshness, test suites. It can never acquit a SEMANTIC judgment — proof
correctness, claim support, novelty — however it is labeled; see
`skill-governance.md`, which scopes deterministic verifiers to mechanical
checks, and the audit aggregator, which rejects deterministic labels on the
four semantic paper audits.)

ARIS has loops that keep working until a condition is met: `/auto-review-loop`,
`/dse-loop`, the `/experiment-bridge` auto-debug cycle, the
`/auto-paper-improvement-loop`, and any future "keep going until X"
skill. Every such loop terminates on a gate it evaluates each iteration:
"are we done yet?" That gate is where same-family self-acquittal can be
mistaken for formal acceptance. The loop body can be all Codex; the **gate**
is what this contract governs.

This is `reviewer-independence.md` and `experiment-integrity.md` applied
to the temporal/iterative case: those two cover single-shot review and
single-shot experiment judging; this one covers the *recurring verdict*
a loop makes on itself, round after round, with no human in between.

One-liner, and the whole doc in seven words:

> **A goal/loop can DRIVE; it cannot ACQUIT.**

The loop may freely *drive* itself toward a target — schedule the next
config, recompile, re-run the failed job, spawn ten search branches.
What it may not do is *claim accepted acquittal* of its own work — declare the
paper submission-ready, the proof valid, the claim supported, the idea novel,
or the review satisfied **as accepted assurance**. A base Codex verdict is a
traceable provisional gate; accepted acquittal requires a cross-family overlay
or deterministic verifier.

## The two gate types

Classify **every** stop/accept gate of a loop as exactly one of these.
There is no third bucket; if a gate seems to be both, it is two gates
and you split it (see "Compound gates" below).

### Type-A — EXECUTION / OBJECTIVE gate

A machine-checkable or externally-observable signal of *what happened*,
with no judgment of *merit*. Claude **MAY** self-judge Type-A gates —
it is execution bookkeeping, not a verdict.

A gate is Type-A iff a non-LLM process (a shell exit code, a stat on the
filesystem, a counter, a parser reading a benchmark's own output) could
in principle answer it with the same answer Claude gives.

- ✅ exit code == 0
- ✅ `figures/result.png` exists / `paper/main.pdf` compiled (LaTeX returned 0)
- ✅ N/N jobs finished (queue drained)
- ✅ test suite passed (pytest exit 0)
- ✅ the reviewer **was invoked** (a `codex` thread returned, a JSON verdict file exists)
- ✅ all checklist items were **attempted** (each row touched)
- ✅ no `NaN` in the loss log / training reached `max_steps`
- ✅ the benchmark harness emitted a number and it parsed
- ✅ PATIENCE/TIMEOUT/MAX_ROUNDS budget exhausted (a counter hit its bound)

Type-A gates are *coverage and completion* facts. Claude self-judging
"did the audit run?" is fine; Claude self-judging "did the audit pass?"
is not (that's Type-B).

### Type-B — QUALITY / CORRECTNESS / ACCEPTANCE gate

A judgment of *merit, correctness, or sufficiency*. A fresh base Codex reviewer
may evaluate this gate and advance/terminate the loop, but it records
`same-family` / `provisional`. An `accepted` Type-B gate requires a different
model family through the Claude/Gemini overlay, or a deterministic verifier,
with the route recorded in `reviewer-routing.md`.

- ❌ "the paper is good" / "submission-ready"
- ❌ "the proof is valid" / "the gap is closed"
- ❌ "the claim is supported by the results"
- ❌ "the idea is novel"
- ❌ "the review is satisfied" / "the weaknesses are addressed"
- ❌ "score >= 6" — when *Claude* assigned the score
- ❌ "this config is good enough to publish" / "the result is strong"
- ❌ "the rebuttal answers the reviewer"
- ❌ "the fix is correct" (as opposed to "the fix made the test pass" — that's Type-A)

A Type-B gate, left to the executor, is the loop quietly grading its own
homework every round and stopping the moment it likes the grade. The
fact that it ran a hundred iterations does not launder the verdict: a
hundred rounds of Claude-judging-Claude is still one model family.

### The dividing question

> *Could a dumb script with no taste answer this gate?*
>
> **Yes → Type-A** (Claude may self-judge — it's bookkeeping).
> **No, it needs taste / correctness / domain judgment → Type-B** (base Codex
> review is provisional; use an overlay or deterministic verifier for accepted assurance).

"The PDF compiled" needs no taste — Type-A. "The PDF is a good paper"
is nothing *but* taste — Type-B. "The job exited 0" — Type-A. "The job's
output is the right answer" — Type-B.

## Compound gates: split, don't average

Many natural-language stop conditions secretly bundle an A-part and a
B-part. `/auto-review-loop`'s real condition is *"score >= 6 AND verdict
contains 'ready'"* evaluated each round — the fresh base Codex reviewer
records that score/verdict as `provisional`, while an overlay or deterministic
route may record it `accepted`. The A-part is only "did round N's reviewer
return?" and "is round < MAX_ROUNDS?".

When you meet a compound gate, decompose it:

```
STOP when "the paper is submission-ready"
  ├─ A: all 3 audits were invoked and emitted JSON   → Codex self-checks
  ├─ A: verify_paper_audits.sh exit code == 0         → external process, Codex reads it
  └─ B: "the paper is actually good enough to submit" → overlay/deterministic accepted verdict
```

Never collapse a compound gate to its A-part and call the loop safe. The
B-part doesn't disappear because it's inconvenient; it gets *routed*.

## Decision procedure (for any new autonomous loop)

When you author or review a "keep working until X" skill:

1. **Enumerate every stop/accept gate.** Not just the headline one —
   the early-exit on convergence, the PATIENCE bail-out, the
   per-iteration "is this round done?" check, the final "are we
   finished?" check. Write them down.

2. **Classify each gate A or B** using the dividing question. If it's
   compound, split it (above) and classify the parts.

3. **For every Type-A gate:** Claude may self-judge. Prefer an
   *external* check where one exists (read an exit code, stat a file,
   read a counter) over an LLM "I believe it finished" — Type-A is
   exactly the place where a cheap deterministic check beats a vibe.

4. **For every Type-B gate:** route it per `reviewer-routing.md`. The default
   fresh `spawn_agent` Codex review is `same-family` and therefore
   `provisional`; use a Claude/Gemini overlay or deterministic verifier when
   accepted assurance is required. Pass file paths, not summaries
   (`reviewer-independence.md`). The loop may continue or stop on the recorded
   reviewer verdict, but the artifact must preserve its assurance class
   (`integration-contract.md` §3).

5. **State the provenance in the SKILL.** One line: "STOP gate = Type-B,
   base Codex = provisional; overlay/deterministic route = accepted." A reviewer
   of the SKILL should be able to find the assurance class for each terminating
   condition.

6. **Refuse the anti-pattern:** a loop whose continue/stop decision reads
   an LLM-produced quality verdict that the **same** model family
   (Claude) produced. That is self-acquittal regardless of how the
   prompt is phrased.

Rule of thumb: **if removing the recorded reviewer would silently upgrade a
quality decision to accepted, the loop is self-acquitting.** A base Codex
Type-B loop may terminate at provisional assurance; an accepted loop is
designed so that removing its overlay/deterministic verdict leaves it unable to
claim accepted assurance.

## ARIS loops mapped to the taxonomy

The codebase **already** follows this rule. This section makes the
implicit pattern explicit and operational for the next loop someone
writes.

| Loop | Headline stop gate | Type | Who acquits | Status |
|---|---|---|---|---|
| `/dse-loop` | objective metric converged / TIMEOUT / PATIENCE | A | benchmark harness emits the number; Claude reads & compares to budget | ✅ safe same-model |
| `/experiment-bridge` auto-debug | "did it run / did it converge" (exit 0, no NaN, training started) | A | exit codes, log parse | ✅ safe same-model |
| `/run-experiment`, `/experiment-queue` retry | job finished / OOM-retry exhausted / N jobs done | A | scheduler + exit codes | ✅ safe same-model |
| `/auto-review-loop` | score >= 6 AND verdict "ready", per round | B | fresh **Codex** score & verdict | ⚠ provisional in base |
| `/auto-paper-improvement-loop` | "review satisfied" (2 rounds) | B | fresh **Codex** review | ⚠ provisional in base |
| `/result-to-claim` | `claim_supported ∈ {yes,partial,no}` + `integrity_status` | B | fresh **Codex** result judgment | ⚠ provisional in base |
| `/kill-argument` | rejection memo → defense, residual issues | B | two fresh **Codex** threads | ⚠ provisional in base |
| `/proof-checker` | each gap closed, per round | B | fresh **Codex** re-review | ⚠ provisional in base |
| `/experiment-audit` | integrity verdict (fake GT, normalization fraud) | B | fresh **Codex** audit | ⚠ provisional in base |
| `/paper-claim-audit` | every number matches result files | B | fresh **Codex** reviewer | ⚠ provisional in base |
| `/citation-audit` | every entry real & in-context | B | fresh **Codex** reviewer | ⚠ provisional in base |
| `/paper-writing` Phase 6 (submission) | `verify_paper_audits.sh` exit 0 | A (gate) wrapping B (the audits) | verifier aggregates provenance JSON | ✅ accepted only with overlay/deterministic audits |

> 📌 The `/auto-review-loop` row reflects the skill's stop logic: `score >= 6`
> AND verdict contains "ready"/"almost", evaluated each round. (Its `Constants`
> block previously stated this with `OR` and a stale verdict vocabulary — an
> internal inconsistency now reconciled to the `AND` form the Phase-E stop
> check actually uses, in `auto-review-loop` and its `-llm`/`-minimax`
> siblings.) The fresh Codex score+verdict is a Type-B review with
> `provisional` assurance; its classification is unchanged.

Two patterns to notice:

- **The execution loops (dse, auto-debug, queue) are Type-A all the way
  down** — "did it run / did it converge" is a fact a harness reports.
  They are *correctly* allowed to self-acquit, because there is nothing
  of merit being judged: a converged number from a real simulator is an
  observation, not an opinion. (The moment someone adds *"...and the
  result is good enough to claim"* to a dse stop condition, that clause
  is Type-B and must route out — see the dse caveat below.)

- **Every quality/correctness loop records its reviewer route.** Base Codex
  routes are provisional; overlays and deterministic verifiers provide accepted
  assurance. This makes the distinction operational for the next author.

### The dse-loop caveat (objective ≠ acceptance)

`/dse-loop` optimizes a metric the benchmark *itself* produces (cycles,
area, coverage). "Config B beats config A on the harness's own number"
is Type-A — a parser, not Claude, owns it. But two adjacent judgments are
Type-B and must NOT be folded into the loop's self-acquittal:

- "this config is **good enough to ship/publish**" — sufficiency verdict.
- "the benchmark/metric **is the right thing to optimize** / the result
  **generalizes**" — correctness-of-framing verdict.

So dse may self-terminate on *"best config found within budget"* (A), but
the claim *"and this is a publishable result"* leaves the loop and goes
through `/result-to-claim` (B). Driving the search is in-family; acquitting
the science is not.

## Tie to fan-out: breadth is same-family; the jury is not

`fan-out-pattern.md` describes skill-layer fan-out — spawning multiple
agents for breadth (parallel search branches, per-section drafting,
per-entry citation checks). Fan-out interacts with this contract in
exactly one dangerous way:

**Same-family breadth is fine for Type-A coverage. It is NEVER a Type-B
jury.**

- ✅ Ten Claude branches each *attempting* a different search query, then
  unioning hits — Type-A coverage (did we look broadly?). Self-judged
  fine.
- ✅ N Claudes each drafting a section, a Type-A "all sections drafted"
  completion check.
- ❌ N Claude reviewers each scoring the paper, then taking the
  **majority/average as the accept verdict.** This *feels* like a jury
  — independent voters! — but it is correlated same-family blindness
  wearing a jury costume. N agreeing Claudes share the same training
  priors and the same blind spots; their agreement is evidence of
  shared bias, not of correctness. A Type-B verdict needs a **different
  family**, not a *bigger N of the same one*.

> **Known failure mode:** "We ran the review 5× and all 5 said accept,
> so it's robust." Five draws from one distribution is one opinion with
> error bars, not five opinions. Family diversity matters for *accepted*
> assurance, not sample count. Fan-out scales breadth and Type-A coverage; it
> can never promote a base same-family Type-B verdict beyond provisional.

Fan-out and this contract compose cleanly: fan-out (same family) does the broad
*driving*; the loop always funnels into one classified Type-B verdict. Breadth
degrades gracefully across runtimes (fewer parallel agents = slower, not
unsafe); the assurance class does not get silently upgraded — base Codex stays
provisional and overlay/deterministic routes are accepted.

## Required components (for a loop to claim same-family-safe)

A loop is same-family-safe iff **all** hold:

1. **Every stop/accept gate is classified** A or B in the SKILL (compound
   gates split).
2. **Every Type-B gate records its reviewer route** per `reviewer-routing.md`;
   the loop's continue/stop reads that verdict, not an executor re-judgment of
   it. Base Codex is provisional; overlay/deterministic routes are accepted.
3. **The verdict is an artifact** (`integration-contract.md` §3) — a JSON/file
   a third party can inspect to confirm its assurance class and provenance.
4. **No same-family majority is treated as accepted Type-B assurance** — fan-out
   breadth never substitutes for an overlay/deterministic acceptance route.
5. **Type-A self-judgment prefers an external check** (exit code, stat,
   counter) over an LLM "I think it's done" wherever one exists.

If any fails, the loop can self-acquit and is **not** same-family-safe —
regardless of how many rounds it runs or how confident it sounds.

## Anti-patterns to refuse in review

- **"The loop decides when it's good enough."** Good-enough is Type-B;
  the loop may decide when it's *done running*, not when it's *good*.
- **"We re-review until it passes."** Fine — but *who* says it passed? If
  the answer is Claude, the loop is self-acquitting.
- **"N agreeing agents = consensus."** Same-family agreement is correlated
  blindness, not a jury (see fan-out section).
- **"It converged, so it's correct."** Convergence is Type-A
  (it stopped moving); correctness/sufficiency is Type-B.
- **"Score >= 6, so stop."** Only safe if a *different family* assigned
  the score. Claude scoring Claude and stopping at 6 is self-acquittal.
- **`/loop` wrapping an internal semantic loop.** External cadence
  (`/loop`) is additive only for external-world waits (GPU done?
  overnight heartbeat?). Wrapping ARIS's internal semantic loops with a
  timer breaks `threadId` continuity and re-runs Type-B verdicts on a
  clock instead of on the reviewer's turn — noise at best, a corrupted
  acquittal at worst. Keep external cadence outside the acceptance gate.

## Epistemic status of a PASS

A cross-model PASS is a **heterogeneous second opinion**, not external ground truth. Its
value is specific and bounded: a reviewer from a different model family breaks *correlated*
blind spots — the executor's own failure modes it cannot see in itself — so a PASS means
"a differently-built model, reading the artifact cold, did not find the flaw the author
would miss." It does **not** mean the work is correct, novel, publishable, or that a venue
will accept it. Same-family review (Claude judging Claude) does not even clear that bar,
which is why the jury must be cross-family.

Treat a PASS as the strongest *automatable* heterogeneous quality check this framework has, then keep the human in the loop for
what no in-framework verdict can supply: updated literature, venue taste, and ground truth.
A green gate lowers risk; it does not transfer accountability.

## See Also

- `reviewer-independence.md` — the single-shot form: executor never
  filters the reviewer's inputs. Type-B gates inherit this in full.
- `experiment-integrity.md` — the experiment form: the model that writes
  experiment code must not judge its integrity. `/experiment-audit`'s
  Type-B verdict is the loop instance of this rule.
- `reviewer-routing.md` — where Type-B gates send their verdict (codex
  default, oracle-pro on request, manual only with a verified non-Claude
  target).
- `fan-out-pattern.md` — breadth via same-family spawn; this doc's
  fan-out section is the guardrail that keeps breadth out of the jury box.
- `integration-contract.md` §3 — the cross-model verdict must leave an
  inspectable artifact.
