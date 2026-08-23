# Fan-Out Pattern

> **Cursor mapping**: "Agent tool" below = Cursor's `Task` tool (supports true
> parallel spawn — launch multiple Task calls in one message). Fan-out subagents use `model: "inherit"` (same family);
> the independent reviewer always uses a cross-family model per `reviewer-routing.md`.

When a skill needs **breadth** — many candidate ideas, many sources, many attack angles, many proof obligations, or many draft sections — it may fan out the generation step across same-family worker subagents. This document defines the canonical convention for parallel generation **without** compromising independent cross-model review.

**Rule:** Parallel subagents only generate candidates (ideas, drafts, citations). Scoring, ranking, and final approval must always be handled by an independent cross-family reviewer model.

Fan-out accelerates coverage across candidate space. It does not alter how quality is evaluated: evaluation remains an independent, cross-family step regardless of whether generation ran across 8 parallel workers or sequentially in a single pass.

## Core Principle: Decouple Generation Fan-Out from Quality Evaluation

Generation and quality evaluation are distinct operations governed by different rules:

| | Fan-Out (Breadth) | Quality Evaluation (Verdict) |
|---|---|---|
| **Purpose** | Generates N candidate items | Renders the stop/acceptance decision |
| **Execution** | Same-family subagents (e.g. parallel worker agents) | Independent, **different** model family (`reviewer-routing.md`) |
| **Allowed to judge quality?** | **No.** Generation only. | **Yes.** Evaluates quality and correctness. |
| **Failure if violated** | None (produces candidate pool) | Evaluation bias: model assesses its own family's output |
| **System Role** | Candidate generation — broad search coverage | Independent evaluation — objective quality verification |

Decoupling generation from evaluation prevents correlated blind spots. A worker subagent that both generates a candidate and declares it high quality reintroduces self-evaluation bias. If a worker generates an idea and the same-family orchestrator declares that idea "novel" or "publishable", the review lacks independence regardless of how many subagents participated.

The operational contract for every worker shard is explicit:

- ✅ A shard **may**: enumerate, draft, propose, retrieve, hypothesize, decompose, and identify attack vectors (emit candidate items).
- ❌ A shard **must not**: rank candidates against each other, declare one "best", assert novelty/soundness/publishability, decide the loop is complete, or render an acceptance verdict.

Mechanical operations on the merged candidate set (deduplication, clustering, schema validation, sorting by a declared field) are execution bookkeeping and are handled directly by the executor (see § Structured-output contract).

## The 3-Tier Degradation Ladder

Fan-out is a **prompt pattern, not a hard runtime dependency.** Workflows degrade gracefully across environments. The three tiers below differ **only** in how candidate generation is dispatched; all three terminate in the **identical** independent cross-model review step.

| Tier | Dispatch mechanism | When available |
|---|---|---|
| **Tier 1** | Workflow true parallel — N shards run concurrently with dynamic orchestration | Runtime exposes a parallel-spawn primitive |
| **Tier 2** | Standard `Task`/`Agent` tool spawn — N subagents launched, static fan-in collection | Host supports subagent spawning without workflow engine |
| **Tier 3** | Sequential fallback — N passes run sequentially, each with a **fresh context** | Any runtime, including single-agent CLI environments |

```
                 ┌─────────────────────────────────────────┐
  Tier 1  ──┐    │                                          │
  Tier 2  ──┼──► │  Merged union → mechanical dedup (SAFE)  │ ──► CROSS-MODEL REVIEW
  Tier 3  ──┘    │     (executor-side, NOT judgment)        │      (identical step)
                 └─────────────────────────────────────────┘
       (dispatch differs)         (same)                          (same — invariant)
```

**Independent evaluation is orthogonal to whether subagents exist.** Tier 3 with sequential passes must produce a verdict from the *same* cross-model reviewer as Tier 1 with parallel workers. If an environment cannot run Tier 1, it falls back to Tier 2; if it cannot run Tier 2, it falls back to Tier 3. Independent evaluation is never dropped.

## Structured-Output Contract for Shards

Every shard returns a **structured result set**, not freeform prose, enabling mechanical merging and deduplication before review. Both envelope shapes include `shard_id`, a keyed list, and a `dedup_key` per item:

**Generation fan-out** — the shard *produces* new candidates (idea lenses, attack axes, draft variants). Returns `candidates[]`:

```json
{
  "shard_id": "lens:scaling-regime",
  "candidates": [
    {
      "kind": "idea | attack | draft_section",
      "payload": "<the produced item — domain fields may be inlined instead>",
      "provenance": "<which lens/seed produced it>",
      "dedup_key": "<normalized string for mechanical clustering>"
    }
  ]
}
```

**Extraction fan-out** — the shard *reads* fixed input and extracts specific units (verified papers, proof obligations). Returns `entries[]` using existing canonical IDs:

```json
{
  "shard_id": "section:4.2",
  "entries": [
    {
      "kind": "source | proof_obligation",
      "payload": "<the extracted record — domain fields may be inlined>",
      "dedup_key": "<canonical id assigned upstream: arXiv id / DOI / MC-17>"
    }
  ]
}
```

The `dedup_key` allows mechanical clustering without subjective judgment:
- For generation: normalize titles, claims, or statements to a canonical string and cluster by exact or near-match.
- For extraction: use upstream canonical IDs (arXiv ID, DOI, theorem identifier).

### Deduplication Discipline

Deduplication runs on the merged candidate pool, **on the executor model, BEFORE the reviewer evaluation**. This is safe because it is mechanical:

- ✅ Cluster candidates by `dedup_key` (exact and near-match on a declared metric).
- ✅ Drop exact duplicates; collapse near-duplicates into one representative item with an occurrence count.
- ✅ Sort or truncate by a *declared objective field* (e.g., top-K by retrieval score emitted by search index).
- ❌ Do not drop a candidate based on the executor's subjective opinion of quality.
- ❌ Do not re-rank candidates based on the executor's quality assessment before sending to the reviewer.

Ordering requirement: **Deduplicate BEFORE the cross-model review step.**
The cross-model reviewer is token-intensive and rate-limited. Passing 40 candidates where 25 are near-duplicates wastes evaluation budget. Mechanical deduplication keeps reviewer input concise and focused.

```
fan-out (N shards) → merge union → mechanical dedup (executor, SAFE) → CROSS-MODEL REVIEW
                                   └ cheap, judgment-free,             └ thorough, independent,
                                     shrinks input set                   evaluates deduped pool
```

## When to Fan Out — and When NOT to

Fan out when a task is **breadth-bound**: output quality scales with the breadth of candidate space covered.

| Fan Out (Breadth-Bound) | Do NOT Fan Out (Value is Independent Review) |
|---|---|
| Idea generation across diverse analytic lenses | `/novelty-check` — the verdict itself is the deliverable |
| Literature retrieval across multiple databases | `/research-review` — single independent critique |
| Attack-angle and counterargument enumeration | `/experiment-audit` — single cross-model integrity check |
| Proof obligation and assumption extraction | `/peer-review` meta-review — single external evaluation |
| First-pass section drafting | Any skill whose primary output is an acceptance decision |

**Anti-pattern to reject:** Fanning out a quality evaluation across same-family subagents. Spawning multiple subagents from the same model family to "assess novelty" or "evaluate paper quality" does not produce independent reviews; it produces correlated opinions with identical training biases. If a skill's objective is a quality verdict, fan out the *evidence gathering*, but keep the quality evaluation unified and cross-model.

**Rule:** Fan out candidate generation; keep quality evaluation unified and independent.

## Worked Examples

### `/kill-argument` — Tier-3 Sequential Generation, No Subagent Tool

`/kill-argument` executes two sequential reviewer threads in series:
1. Thread 1 drafts the strongest 200-word rejection critique.
2. Thread 2 decomposes that critique into 3–7 atomic rejection points and evaluates each against the paper.

The skill computes the final verdict mechanically from per-point evaluation counts. Generation fans out across argument points, while the final PASS/FAIL mapping is deterministic and handled in skill logic.

### `/idea-creator` — Tier-1 Parallel Lens Generation → Dedup → Cross-Model Review

`/idea-creator` fans out idea generation across analytic lenses (structural gaps, contradictory findings, untested assumptions, unexplored scaling regimes).
1. Lenses run as parallel worker tasks (Tier 1/2) or sequential passes (Tier 3).
2. The executor merges and mechanically deduplicates candidates.
3. The cross-model reviewer evaluates surviving distinct ideas to surface reviewer objections and rank candidates.

### `/research-lit` — Source Fan-Out with Deterministic Verification Gate

`/research-lit` fans out queries across multiple academic sources (arXiv, Semantic Scholar, OpenAlex, Exa, DeepXiv). Candidate papers are verified by `verify_papers.py` against arXiv/CrossRef/S2 metadata. Because verification is a deterministic external check against authoritative registries, same-family retrieval poses no evaluation risk.

## Shard Safety Invariants

1. **Shards are read-only on shared artifacts.** A worker shard may read workspace files and emit candidate data; it must not modify shared state or mutate files other shards are accessing. Only the executor writes merged output after deduplication.
2. **Verify upstream dependencies.** When reviewing work that depends on an upstream artifact (a cited paper, a numerical claim, a prior theorem), provide the reviewer with the path to that upstream source rather than an unverified intermediate summary.

## Cross-References

- **`reviewer-routing.md`** — Reviewer backend selection. Cross-model review routes to independent model families.
- **`reviewer-independence.md`** — Reviewers receive direct file paths in fresh contexts without author editorializing.
- **`acceptance-gate.md`** — Objective execution completion (exit codes, completed shards) can be verified by the executor; quality and correctness verdicts require independent cross-model review.
- **`integration-contract.md`** — Multi-source retrieval policies and durable JSON artifact specifications.

## Required Components for a Fan-Out Skill

A skill using the fan-out pattern must specify:

1. **Portable dispatch:** Define the parallel execution path (Tier 1/2) and sequential fallback (Tier 3).
2. **Structured shard output:** Return structured JSON keyed by `shard_id` with `dedup_key` fields, not unstructured prose.
3. **Mechanical deduplication:** Execute deduplication on merged results before invoking reviewer models.
4. **Independent quality evaluation:** Route final quality assessment to an independent cross-model reviewer or deterministic verification script.
5. **Breadth-bound justification:** Explain why parallel candidate generation improves output quality for this specific task.

## Subagent Tool Grant Policy (`Task` / `Agent`)

Granting subagent spawning capabilities in a skill's frontmatter is restricted to skills whose body actively fans out across parallel workers. It is not boilerplate.

- Tier-1 and Tier-3 execution require no special tool grants for sequential passes or external runtime dispatch.
- Tier-2 in-process subagent spawning requires the tool grant and must cite `fan-out-pattern.md` in the skill body.
- Tool grants track actual implementation; unused grants must be omitted.
