# Acceptance-Gate Provenance

## Core Principle

**An autonomous loop's stop/acceptance gate determines whether the loop is safe from self-evaluation bias. The criterion evaluated at that gate — not the loop's subject matter or the number of worker agents — determines whether the generating model may evaluate it.**

ARIS has loops that keep working until a condition is met: `/auto-review-loop`, `/dse-loop`, the `/experiment-bridge` auto-debug cycle, the `/auto-paper-improvement-loop`, and any future iterative workflow. Every such loop terminates on a gate evaluated each iteration: "are we done yet?" That gate is where same-family self-approval can compromise quality. The loop body can be handled entirely by the executor model; the **gate** is what this contract governs.

This applies `reviewer-independence.md` and `experiment-integrity.md` to iterative workflows: those documents govern single-shot review and experiment judging; this document governs the recurring evaluation a loop makes on its own output, round after round, without human intervention.

**Rule:** An autonomous loop can generate iterations and run execution tasks, but it cannot declare its own output high-quality or submission-ready. Evaluating quality requires an independent, cross-family reviewer model.

The loop may freely drive iteration toward a target — schedule configs, recompile, re-run failed jobs, or spawn parallel search branches. What it cannot do is validate its own merit — declare the paper good, the proof valid, the claim supported, the idea novel, or the review satisfied. Quality evaluation requires an independent cross-model review.

## The Two Gate Types

Classify **every** stop/accept gate of a loop as exactly one of these types. There is no third bucket; if a gate appears to be both, it is a compound gate and must be split (see "Compound gates" below).

### Type-A — Execution / Objective Gate

A machine-checkable or externally observable signal of *what happened*, with no subjective judgment of *merit*. The executor model **may** evaluate Type-A gates directly — this is execution bookkeeping, not a quality verdict.

A gate is Type-A if and only if a non-LLM process (a shell exit code, a filesystem check, a counter, or a parser reading benchmark output) could answer it deterministically with the same result.

- ✅ Exit code == 0
- ✅ `figures/result.png` exists / `paper/main.pdf` compiled (LaTeX returned 0)
- ✅ N/N jobs finished (queue drained)
- ✅ Test suite passed (pytest exit 0)
- ✅ The reviewer **was invoked** (a reviewer thread returned, a JSON verdict file exists)
- ✅ All checklist items were **attempted** (each row processed)
- ✅ No `NaN` in the loss log / training reached `max_steps`
- ✅ The benchmark harness emitted a parsable numeric score
- ✅ Budget exhausted (timeout, patience limit, or max rounds reached)

Type-A gates verify *coverage and completion*. Self-checking "did the audit run?" is Type-A; self-checking "did the audit pass on quality grounds?" is Type-B.

### Type-B — Quality / Correctness / Acceptance Gate

A judgment of *merit, correctness, or sufficiency*. The executor must **never** self-judge a Type-B gate — it requires a **different model family** (per `reviewer-routing.md`: a Cursor Task subagent on a cross-family built-in model by default; legacy backends only on explicit user request with the routed model recorded). This maintains the cross-model invariant at the loop's terminating gate.

- ❌ "the paper is good" / "submission-ready"
- ❌ "the proof is valid" / "the gap is closed"
- ❌ "the claim is supported by the results"
- ❌ "the idea is novel"
- ❌ "the review is satisfied" / "the weaknesses are addressed"
- ❌ "score >= 6" — when the executor model assigned the score
- ❌ "this config is good enough to publish" / "the result is strong"
- ❌ "the rebuttal answers the reviewer"
- ❌ "the fix is correct" (as opposed to "the fix made the test pass", which is Type-A)

A Type-B gate left to the executor allows the loop to grade its own work and stop whenever it produces favorable text. Running multiple iterations does not resolve this: repeated iterations by the same model family still share identical biases and blind spots.

### The Dividing Question

> *Could a deterministic script without subjective domain judgment evaluate this gate?*
>
> **Yes → Type-A** (the executor may self-check — this is objective bookkeeping).
> **No, it requires domain judgment, scientific rigor, or quality assessment → Type-B** (route to an independent, cross-family reviewer model).

"The PDF compiled" requires no subjective judgment — Type-A. "The PDF is a strong, complete paper" is a quality judgment — Type-B. "The job exited 0" — Type-A. "The job's output supports the hypothesis" — Type-B.

## Compound Gates: Split, Do Not Average

Many natural-language stop conditions combine Type-A and Type-B components. For example, `/auto-review-loop` stops when *"score >= 6 AND verdict contains 'ready'"* each round. The score and verdict must come from the cross-model reviewer (Type-B), while the executor only verifies objective completion: "did the reviewer return a response?" and "is round < MAX_ROUNDS?" (Type-A).

Decompose compound gates explicitly:

```
STOP when "the paper is submission-ready"
  ├─ A: all audits were invoked and emitted valid JSON → executor self-checks
  ├─ A: verify_paper_audits.sh exit code == 0          → external verification script
  └─ B: "the paper meets publication standards"        → independent cross-model verdict
```

Never reduce a compound gate to its Type-A component and treat the quality evaluation as solved. The Type-B evaluation must be routed to an independent model.

## Decision Procedure (for Autonomous Loops)

When authoring or reviewing an iterative workflow:

1. **Enumerate every stop/accept gate.** Include early-exit on convergence, patience timeouts, per-iteration completion checks, and final acceptance checks.
2. **Classify each gate as Type-A or Type-B** using the dividing question. Split compound gates into distinct Type-A and Type-B checks.
3. **For Type-A gates:** The executor model may evaluate them directly. Prefer external deterministic checks (reading an exit code, file status, or counter) over model assertions.
4. **For Type-B gates:** Route evaluation to an independent, cross-family reviewer per `reviewer-routing.md` (default: a fresh Cursor Task subagent on a cross-family model). Pass file paths directly rather than filtered summaries (`reviewer-independence.md`). The loop continues or stops based on the reviewer's output. Save the verdict as a persistent artifact (`integration-contract.md` §3) for verification.
5. **State gate provenance in the SKILL.** Include a clear line: "STOP gate = Type-B, routed to cross-family reviewer."
6. **Reject unverified self-approval:** Avoid any loop where stop decisions rely on quality scores generated by the same model family that produced the work.

Rule of thumb: **If removing the cross-model reviewer would still allow the loop to declare success and stop, the loop has an unverified self-approval flaw.** A well-designed Type-B loop cannot terminate with an acceptance verdict without an independent evaluation.

## ARIS Loops Mapped to Taxonomy

*(In this Cursor environment, reviewer roles are fulfilled by cross-family Task subagents per `reviewer-routing.md`.)*

| Loop | Headline stop gate | Type | Verdict source / validator | Status |
|---|---|---|---|---|
| `/dse-loop` | Objective metric converged / TIMEOUT / PATIENCE | A | Benchmark harness emits number; executor checks against budget | ✅ Safe same-model |
| `/experiment-bridge` auto-debug | "Did it run / converge" (exit 0, no NaN, training started) | A | Process exit codes, log parsing | ✅ Safe same-model |
| `/run-experiment`, `/experiment-queue` retry | Job finished / retry budget exhausted / N jobs done | A | Scheduler + exit codes | ✅ Safe same-model |
| `/auto-review-loop` | Score >= 6 AND verdict "ready", per round | B | **Cross-family reviewer** assigns score & verdict | ✅ Cross-model |
| `/auto-paper-improvement-loop` | "Review criteria satisfied" (2 rounds) | B | **Cross-family reviewer** evaluates revisions | ✅ Cross-model |
| `/result-to-claim` | `claim_supported ∈ {yes,partial,no}` + `integrity_status` | B | **Cross-family reviewer** evaluates results vs claims | ✅ Cross-model |
| `/kill-argument` | Rejection memo → defense, residual issues | B | Two independent **cross-family reviewer** threads | ✅ Cross-model |
| `/proof-checker` | Each mathematical gap resolved, per round | B | **Cross-family reviewer** re-evaluates each round | ✅ Cross-model |
| `/experiment-audit` | Integrity verdict (baseline correctness, metric validity) | B | **Cross-family reviewer** audits evaluation code | ✅ Cross-model |
| `/paper-claim-audit` | Numerical claims match experiment result files | B | Fresh zero-context **cross-family reviewer** | ✅ Cross-model |
| `/citation-audit` | Citations exist and are contextually accurate | B | Fresh **cross-family reviewer** | ✅ Cross-model |
| `/paper-writing` Phase 6 (submission) | `verify_paper_audits.sh` exit 0 | A (gate) **wrapping** B (audits) | External verifier reads cross-model JSON artifacts | ✅ A-gate over B-verdicts |

Key distinctions:
- **Execution loops (dse, auto-debug, queue) are Type-A:** Completion, process exit status, and convergence are objective observations reported by the execution environment.
- **Quality and correctness loops are Type-B:** Claims, proofs, paper drafts, and reviews require independent cross-family evaluation.

### The DSE Loop Distinction (Objective Metric vs Quality Claim)

`/dse-loop` optimizes an objective metric produced directly by the benchmark simulator (e.g., cycles, area, latency). Determining that "Config B beats Config A on the simulator metric" is Type-A. However, two related claims are Type-B:
- "This configuration is sufficient to claim a state-of-the-art result."
- "The benchmark and metric are appropriate representations of the target problem."

Therefore, `/dse-loop` terminates on Type-A criteria (*"best configuration found within budget"*), but publishing scientific claims from those results requires `/result-to-claim` (Type-B).

## Fan-Out: Parallel Worker Coverage vs Independent Review

`fan-out-pattern.md` covers parallel agent execution (spawning multiple workers for broad literature search, section drafting, or citation checks).

**Parallel same-family workers provide Type-A coverage. They cannot provide Type-B independent review.**

- ✅ Ten parallel workers each running different search queries and merging results — Type-A coverage.
- ✅ Multiple workers drafting different sections in parallel, followed by a Type-A completion check ("all sections written").
- ❌ Multiple workers from the same model family reviewing a paper, with the average score used as an acceptance gate. This does not provide independence: workers from the same family share identical pretraining biases and blind spots. Agreement reflects correlated bias rather than validated correctness.

Multiple samples from one model family do not provide diversity of perspective. Independent review requires evaluation from a distinct, cross-family model.

## Requirements for Loop Verification Safety

An autonomous loop is safe from self-evaluation bias if and only if:

1. **Every stop/accept gate is classified** as Type-A or Type-B (compound gates split).
2. **Every Type-B gate routes to an independent cross-model reviewer** per `reviewer-routing.md`; loop termination depends on the reviewer's verdict.
3. **The cross-model verdict is saved as a durable artifact** (`integration-contract.md` §3) in JSON format.
4. **Parallel same-family agents are never treated as independent reviewers.**
5. **Type-A gates rely on deterministic checks** (exit codes, file existence, counters) rather than model self-assessment.

## Anti-Patterns to Reject

- **"The executor model decides when output is high quality."** Output quality is Type-B; the executor may only check whether execution completed.
- **"Iterate until the authoring model approves."** Iteration must stop based on external review, not author self-approval.
- **"Consensus among same-family agents equals independent validation."** Same-family agreement reflects shared bias.
- **"Execution convergence implies scientific correctness."** Convergence is Type-A (the run stabilized); correctness is Type-B.
- **"Score >= 6, so stop."** Valid only if an independent cross-family reviewer assigned the score.
- **Wrapping internal semantic loops in external cron/loop timers.** External timers should only be used to wait for long-running external compute jobs. Wrapping internal reasoning loops with timers breaks conversational continuity and reruns evaluation gates prematurely.

## Epistemic Status of a PASS Verdict

A cross-model PASS is an **independent second opinion**, not absolute ground truth. A reviewer from a different model family reduces correlated blind spots — catching issues the authoring model would miss in its own work. A PASS confirms that a differently trained model, evaluating the artifact independently, identified no critical blockers. It does not replace human domain expertise, updated literature awareness, or venue-specific expectations.

## See Also

- `reviewer-independence.md` — The single-shot requirement: authoring models must not filter reviewer inputs.
- `experiment-integrity.md` — Code authoring models must not evaluate experiment integrity.
- `reviewer-routing.md` — Routing rules for Type-B cross-family reviewers.
- `fan-out-pattern.md` — Parallel execution patterns for worker subagents.
- `integration-contract.md` §3 — Storing review verdicts as inspectable artifacts.
