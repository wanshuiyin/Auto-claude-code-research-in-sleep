# Fan-Out Pattern

When a skill needs **breadth** — many candidate ideas, many sources, many
attack angles, many proof obligations, many draft sections — it may fan
the generation step out across same-family subagents. This document is
the canonical convention for doing that **without** weakening the
cross-model jury that the entire ARIS design rests on.

Rule of thumb: **Fan-out is 火力 (firepower); the jury is 裁判席 (the
bench). Subagents GENERATE candidates; they NEVER score them.** Fan-out
multiplies how much breadth you can cover per unit time. It does not, and
must not, change *who renders the verdict*. The verdict stays a single,
heterogeneous, cross-model step — identical whether you fanned out across
8 parallel workers or ran one shard at a time on a slow night.

## Core principle: decouple FAN-OUT from JURY

These are two different operations and they are governed by two different
rules:

| | FAN-OUT (breadth) | JURY (verdict) |
|---|---|---|
| What it does | Generates N candidate items | Renders the STOP/ACCEPT decision |
| Who runs it | Same-family subagents (Claude clones, or codex shards) | A **different** model family (`reviewer-routing.md`) |
| Allowed to judge quality? | **No.** Generate only. | **Yes.** That is its only job. |
| Failure if violated | None (it's just more candidates) | Invariant breach: model judges its own family's output |
| Analogy | 火力 — fire more shots | 裁判席 — the bench that rules |

The decoupling is the whole point. A subagent that both generates a
candidate *and* decides whether it is good has collapsed the two
operations and re-introduced exactly the correlated blind spot that
heterogeneous review exists to remove. A Claude subagent generating an
idea, then a Claude orchestrator declaring that idea "novel" or
"publishable," is a Claude judging Claude — the invariant is dead, no
matter how many subagents were involved.

So the contract on every shard is narrow and absolute:

- ✅ A shard MAY: enumerate, draft, propose, retrieve, hypothesize,
  decompose, attack — i.e., emit candidate items.
- ❌ A shard MUST NOT: rank candidates against each other, declare one
  "best," assert novelty/soundness/publishability, decide the loop is
  done, or otherwise render the acceptance verdict.

Mechanical operations on the merged candidate set (deduplication,
clustering, schema validation, sorting by a declared field) are **not**
judgment and are explicitly allowed on the executor — see
§ Structured-output contract.

## The 3-tier degradation ladder

Fan-out is a **skill-prompt pattern, not a harness capability.** ARIS
already fans out today on runtimes that have no parallel-orchestration
primitive at all (`/kill-argument` runs two sequential fresh codex
threads with **no Agent tool**; `/citation-audit` verifies per-entry;
`/proof-checker` re-derives per-round). A richer runtime (ultracode /
Workflow true parallelism) merely *accelerates* the same pattern.

Therefore fan-out must degrade gracefully across runtimes. The three
tiers below differ **only** in how the candidate-generation step is
dispatched. They terminate in the **identical** cross-model jury step.

| Tier | Dispatch mechanism | When available |
|---|---|---|
| **Tier 1** | ultracode / Workflow true parallel — N shards run concurrently with dynamic orchestration | Runtime exposes a parallel-spawn primitive |
| **Tier 2** | Plain `Agent`-tool spawn — N subagents launched, no dynamic orchestration (static fan, collect, merge) | Host has the `Agent` tool but no Workflow engine |
| **Tier 3** | Sequential fallback — the same N shards run one-by-one, each in a **fresh context** (context reset between shards) | Any runtime, including codex CLI / bare Claude Code with no Agent tool |

```
                 ┌─────────────────────────────────────────┐
  Tier 1  ──┐    │                                          │
  Tier 2  ──┼──► │  merged union → mechanical dedup (SAFE)  │ ──► CROSS-MODEL JURY
  Tier 3  ──┘    │     (executor-side, NOT judgment)        │      (identical step)
                 └─────────────────────────────────────────┘
       (dispatch differs)         (same)                          (same — invariant)
```

**The jury invariant is strictly orthogonal to whether subagents
exist.** Tier 3 with zero subagents (one fresh-context pass per shard,
in series) must produce a verdict from the *same* cross-model jury as
Tier 1 with eight parallel workers. If a skill cannot run Tier 1, it
drops to Tier 2; if it cannot run Tier 2, it drops to Tier 3. It never
drops the jury. Degrading the dispatch is free; degrading the verdict is
a breach.

Known failure mode: a skill author "optimizes" Tier 3 by letting the
single sequential pass *also* pick the winner, because there is no
orchestrator to do it. That is self-acquittal smuggled in through the
fallback path. Tier 3 still ends at the cross-model jury; the sequential
pass only generates.

## Structured-output contract for shards

Every shard returns a **structured result set**, not prose, so the merge +
dedup + jury steps can operate mechanically. There are two envelope shapes,
chosen by what the shard does — but they share one invariant: `shard_id` + a
keyed list + a `dedup_key` per item.

**Generation fan-out** — the shard *produces* new candidates (idea lenses,
attack axes, draft variants). Returns `candidates[]`:

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

**Extraction fan-out** — the shard *reads* a fixed input set and reports the
units it finds (papers in a verified set, obligations in a proof). Returns
`entries[]` with the same per-item keys, except `dedup_key` is the unit's
**pre-existing canonical id** (assigned upstream), not a freshly normalized
string:

```json
{
  "shard_id": "section:4.2",
  "entries": [
    {
      "kind": "source | proof_obligation",
      "payload": "<the extracted record — domain fields may be inlined>",
      "dedup_key": "<canonical id already assigned upstream: arXiv id / DOI / MC-17>"
    }
  ]
}
```

The `dedup_key` is what makes mechanical clustering possible without judgment:
for generation, normalize titles / claim-stems / obligation-statements to a
canonical string and cluster on string match / near-match; for extraction, the
canonical id already identifies the unit. No model decides "are these the
same?" by *taste* — the key decides by *normalization rule*. Domain-specific
fields (an idea's hypothesis, a paper's method) may be inlined alongside these
keys rather than buried in an opaque `payload`.

### Dedup discipline

Deduplication runs on the merged union, **on the executor (Claude),
BEFORE the jury**, and is **SAFE** because it is mechanical, not
judgment:

- ✅ Cluster candidates by `dedup_key` (exact + near-match on a declared
  metric).
- ✅ Drop exact duplicates; collapse near-duplicates into one
  representative + a count.
- ✅ Sort/limit by a *declared field* (e.g. keep top-K by retrieval
  score the source already returned).
- ❌ Drop a candidate because the executor *thinks* it's weak — that is
  quality judgment and belongs to the jury.
- ❌ Re-rank candidates by the executor's own quality opinion before the
  jury sees them — that pre-filters the jury's input with same-family
  judgment.

Required ordering: **dedup BEFORE jury, on the merged union.** This is
not just hygiene — it is a cost-control invariant. The jury backend
(codex GPT-5.5 / Gemini / oracle-pro) is the rate-limited,
token-expensive resource. Sending it 40 candidates of which 25 are
near-duplicate is a waste of the scarce cross-model budget and invites
rate-limit failure mid-verdict. Mechanical dedup on the cheap
same-family side, first, keeps the expensive heterogeneous step lean.

```
fan-out (N shards) → merge union → mechanical dedup (Claude, SAFE) → CROSS-MODEL JURY
                                   └ cheap, judgment-free,            └ expensive, rate-limited,
                                     shrinks the jury's input set       sees a deduped set only
```

## When to fan out — and when NOT to

Fan out when the task is **breadth-bound**: its quality scales with how
much of the candidate space you cover, and coverage is the bottleneck.

| Fan out (breadth-bound) | Do NOT fan out (value IS the single jury) |
|---|---|
| Idea generation across lenses | `/novelty-check` — the verdict IS the product |
| Literature retrieval across sources | `/research-review` — single heterogeneous critique |
| Attack-angle enumeration | `/experiment-audit` — one cross-model integrity ruling |
| Proof-obligation extraction | `/peer-review` meta-review — one external verdict |
| Draft-section first passes | Any skill whose output *is* the acceptance decision |

Known failure mode (the one to refuse in review): fanning out a
**judgment** skill across Claude clones. `/novelty-check`,
`/research-review`, `/experiment-audit`, and the `/peer-review`
meta-review do not have a breadth bottleneck — their entire value is the
*single heterogeneous jury verdict*. Spawning eight Claude subagents to
each "assess novelty" and then aggregating their opinions does not give
you eight independent reviews; it gives you eight **correlated** Claude
opinions (same family, same blind spots) dressed up as a panel. Worse,
it dilutes the invariant: the aggregate now *looks* like a review but
was never adjudicated by a different model family. If a skill's deliverable
is a verdict, you may fan out the *evidence-gathering* that feeds the
verdict, but the verdict itself stays a single cross-model call.

One-liner to apply at review time: **fan out the search for candidates;
never fan out the bench.**

## Worked examples (real ARIS skills)

### `/kill-argument` — Tier 3 sequential fan-out, NO Agent tool

`/kill-argument` is the canonical proof that fan-out is a prompt pattern,
not a harness feature. It runs **two** fresh `mcp__codex__codex` threads
in series — Thread 1 writes the strongest 200-word rejection memo; Thread
2 (independent, no `codex-reply`) decomposes that memo into 3-7 atomic
rejection points and adjudicates each. There is **no `Agent` tool** in
its `allowed-tools`; the "fan" is the decomposition into per-point
obligations, run sequentially with context reset between threads. The
jury here is cross-model by construction — both threads are GPT-5.5
adjudicating a Claude-executor's paper, and **the skill code computes the
final verdict from per-point counts; the codex thread is forbidden from
emitting the top-level verdict** (`Verdict is computed by the skill, not
by the adjudicator`). Generation (the attack, the per-point
classification) fans out; the ACCEPT/FAIL mapping is mechanical and
lives in the skill, not the model.

### `/idea-creator` — Tier-1 parallel lens fan-out → dedup → existing cross-model jury

`/idea-creator` fans out idea generation across analytic *lenses*
(structural gaps: method-in-A-not-B, contradictory findings, untested
assumptions, unexplored scaling regimes — Phase 1). On a Tier-1 runtime
these lenses run as parallel shards; on Tier 3 they are enumerated in one
pass. After fan-out the merged set should be **mechanically deduped only**
(cluster near-identical ideas; never drop one for being "weak"). The
**jury** is the already-existing Phase-4 cross-model devil's-advocate
pass: GPT-5.5 via Codex MCP surfaces the strongest reviewer objection per
idea and ranks for a top venue. `/idea-creator` does **not** currently
declare the `Agent` tool — it was stripped in the WB2 least-privilege
sweep because its body does not yet fan out. The WB3 fan-out refactor
re-grants `Agent` in the *same* change that wires these lens shards and
fixes the Phase-3 gap below (per the re-grant rule in **Allowed-tools
hygiene**). On a Tier-1 runtime the lenses then run as Workflow shards;
on Tier 3 they fall back to sequential enumeration with no grant needed.

> ⚠️ **Known gap — idea-creator is an *aspirational* example here, not yet a clean one.**
> Today `/idea-creator` Phase 3 (`skills/idea-creator/SKILL.md:159,175`)
> does same-family *quick novelty check + feasibility gating* and
> **eliminates ideas** before the Phase-4 cross-model jury ever sees them.
> That is exactly the ❌ "executor pre-filters the jury's input with
> same-family quality judgment" this doc forbids above — a Type-B
> novelty/quality verdict made same-family (see
> [`acceptance-gate.md`](acceptance-gate.md)). The fan-out refactor must
> push all novelty/quality elimination INTO (or after) the Phase-4
> cross-model jury; Phase 3 keeps only mechanical dedup + *objective*
> feasibility (compute/time budget), and every non-duplicate idea reaches
> the jury. Fixing this is part of fanning the skill out, not a separate
> chore.

### `/research-lit` — per-source fan-out, deterministic gate as "jury"

`/research-lit` fans out retrieval across sources (arXiv, Semantic
Scholar, OpenAlex, Exa, DeepXiv, Zotero, web) under integration-contract
**Policy D2** (multi-source aggregate: invoke every resolved source,
warn-and-continue on per-source failure, proceed if ≥1 contributed).
Here the "jury" is **not** an LLM at all — it is the **deterministic**
`verify_papers.py` gate (Policy D1: 3-layer arXiv / CrossRef / S2
cross-check), which decides KEEP / `[UNVERIFIED]` by mechanical
cross-reference, not by taste. This is the **near-zero-risk** corner of
the design space: the candidate generators are same-family (or just API
fetchers), but the acceptance gate is a deterministic external verifier,
so there is no same-family-self-judgment risk to begin with. When the
"jury" is a deterministic check rather than a model verdict, the
cross-model-family rule is automatically satisfied (a process is not a
model family). Fan out freely.

## Cross-references

- **`reviewer-routing.md`** — jury backend selection. The cross-model
  jury step routes through Codex MCP (`gpt-5.5`, `xhigh`) by default, or
  Oracle MCP (`gpt-5.4-pro`) under `— reviewer: oracle-pro`. Fan-out
  tier never changes the jury backend.
- **`reviewer-independence.md`** — the jury call receives **file paths
  only**, in a **fresh thread**, with no executor summary/interpretation.
  This applies to the post-fan-out jury exactly as to any other review:
  the deduped candidate set is handed over as artifacts the reviewer
  reads itself, not as the executor's pre-digested ranking.
- **`acceptance-gate.md`** — when self-judgment is allowed. Self-judging
  EXECUTION-completeness (exit code, files exist, N shards returned, PDF
  compiled) is SAFE same-model; self-judging QUALITY/CORRECTNESS (idea
  novel, proof valid, claim supported, review satisfied) MUST be
  cross-model. A fan-out loop may self-verify *that all N shards ran*; it
  may not self-verify *that the candidates are good*. The loop can DRIVE;
  it cannot ACQUIT.
- **`integration-contract.md`** — fan-out across sources/helpers uses the
  §2 resolver chain and the Policy D1/D2 failure policies; the jury step,
  when load-bearing, needs an artifact + verdict schema like any audit.

## Required components for a fan-out skill

A SKILL that fans out must specify all of:

1. **Tier-portable dispatch.** State the Tier-1 parallel form AND the
   Tier-3 sequential fallback. Never assume `Agent` or Workflow exists.
2. **Per-shard structured output.** Each shard returns a structured object
   keyed by `shard_id`, never prose. A *generation* fan-out (e.g.
   idea-creator's lenses) returns `candidates[]`, each item carrying a
   `dedup_key`. An *extraction* fan-out over a fixed input set (e.g.
   research-lit per-paper, proof-checker per-section) returns `entries[]`,
   each item carrying its canonical id as the `dedup_key`. Either shape:
   `shard_id` + a keyed list + a dedup/identity key per item.
3. **Mechanical dedup before the jury.** On the merged union, on the
   executor, judgment-free, declared metric — to control jury cost and
   rate-limit exposure.
4. **A single cross-model jury step** (per `reviewer-routing.md` +
   `reviewer-independence.md`) — OR a deterministic verifier gate — that
   is **identical** across all three tiers.
5. **A breadth-bound justification.** State why this task benefits from
   breadth. If the deliverable IS a verdict, do not fan out the verdict;
   fan out only the evidence that feeds it.

## Allowed-tools hygiene — the `Agent` grant policy

`Agent` in a skill's `allowed-tools` frontmatter is the capability gate for
**Tier-2** dispatch (spawning Claude subagents via the Agent tool). It is
**granted only to skills whose body actually fans out** — i.e. whose prose
instructs the model to spawn parallel Claude subagents. It is **not**
boilerplate to be copied across skills.

This matters because the other two tiers need no per-skill grant:

- **Tier-1** (ultracode / Workflow) is a *harness* capability, not a tool a
  skill lists. A skill cannot "grant itself" Workflow; the runtime provides
  it. So fanning out at Tier-1 requires no `Agent` in `allowed-tools`.
- **Tier-3** (sequential fallback) spawns nothing — e.g. `/kill-argument`
  runs its two passes as fresh `mcp__codex__codex` threads, no Agent tool.
  Correctly, `kill-argument` does **not** grant `Agent`.

So `Agent` is needed *only* for the Tier-2 form, *only* in skills that
genuinely fan out. As of the WB2 least-privilege sweep, **no mainline skill
spawns Claude subagents in its body**, so no mainline skill grants `Agent`.
(48 vestigial grants — pure copied boilerplate, never invoked — were
removed.) Note that "reviewer **sub-agent**" in several skills refers to the
cross-model *codex/GPT reviewer*, not the Agent tool, and never implied a
real grant need.

**Re-granting rule.** A skill that adds genuine fan-out re-introduces
`Agent` to its `allowed-tools` **in the same change that adds the fan-out
prose**, and that prose must cite this document (`fan-out-pattern.md`) so
the grant is self-justifying. Grant tracks usage; never the reverse.

**Enforcement.** `tools/check_skills_inventory.py` fails the drift check if
any mainline skill grants `Agent` without citing `fan-out-pattern.md` in its
body. This keeps vestigial grants from creeping back and guarantees every
real grant is traceable to the convention it follows.
