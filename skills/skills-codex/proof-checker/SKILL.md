---
name: proof-checker
description: Rigorous mathematical proof verification and fixing workflow. Reads a LaTeX proof, identifies gaps via cross-model review (Codex GPT-5.4 xhigh), fixes each gap with full derivations, re-reviews, and generates an audit report. Use when user says "检查证明", "verify proof", "proof check", "审证明", "check this proof", or wants rigorous mathematical verification of a theory paper.
argument-hint: [path-to-tex-file or proof-description]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Proof Checker: Rigorous Mathematical Verification & Fixing

Systematically verify a mathematical proof via cross-model adversarial review, fix identified gaps, re-review until convergence, and generate a detailed audit report with proof-obligation accounting.

## Context: $ARGUMENTS

## Constants

- MAX_REVIEW_ROUNDS = 3
- REVIEWER_MODEL = `gpt-5.4` via Codex reviewer agent, reasoning effort always `xhigh`
- **REVIEWER_BACKEND = `codex`** — Default: Codex reviewer agent (`spawn_agent`, xhigh). Override with `— reviewer: oracle-pro` for GPT-5.4 Pro via Oracle MCP. See `shared-references/reviewer-routing.md`.
- AUDIT_DOC: `PROOF_AUDIT.md` at the paper directory root, alongside `main.tex` (cumulative log; when invoked via `/paper-writing`, this is `paper/PROOF_AUDIT.md`)
- REPORT_TEX: `proof_audit_report.tex` (formal before/after PDF)
- STATE_FILE: `PROOF_CHECK_STATE.json` (for recovery)
- SKELETON_DOC: `PROOF_SKELETON.md` (micro-claim inventory)

### Acceptance Gate (objective, replaces subjective scoring)

The proof passes when ALL of the following hold:
1. Zero open FATAL or CRITICAL issues
2. Every theorem/lemma has: (i) explicit hypotheses, (ii) proof with all interchanges justified, (iii) every application discharges hypotheses in the ledger
3. All big-O/Θ/o statements have declared parameter dependence and uniformity scope
4. Counterexample pass executed on all key lemmas (log candidates even if none found)

## Issue Taxonomy (20 categories, 4 groups)

### Group A: Logic & Proof Structure

| Category | Description | Example |
|----------|-------------|---------|
| **UNJUSTIFIED_ASSERTION** | Claim stated without proof or reference | "The Hessian splits into Gram blocks" |
| **UNPROVEN_SUBCLAIM** | "Clearly" / "it follows" hides a nontrivial lemma | "By symmetry, the cross-terms vanish" without checking |
| **QUANTIFIER_ERROR** | Wrong order ∀/∃, missing "for sufficiently small κ" | "For all π, there exists ε" vs "there exists ε for all π" |
| **IMPLICATION_REVERSAL** | Uses (A⇒B) as (B⇒A), or claims equivalence with only one direction | |
| **CASE_INCOMPLETE** | Misses boundary/degenerate cases | Singular covariance, zero weight, non-unique argmin |
| **CIRCULAR_DEPENDENCY** | Lemma uses theorem that depends on it | |
| **LOGICAL_GAP** | A step is not justified by what precedes it | B=Θ(1) → β_K=0 without analyzing W |

### Group B: Analysis & Measure Theory

| Category | Description | Example |
|----------|-------------|---------|
| **ILLEGAL_INTERCHANGE** | Swaps limit/expectation/derivative/integral without DCT/MCT/Fubini | Differentiating under E without domination |
| **NONUNIFORM_CONVERGENCE** | Pointwise convergence used as uniform | sup and limit swapped |
| **MISSING_DOMINATION** | DCT cited but no dominating function given | |
| **INTEGRABILITY_GAP** | Uses E|X|^p without proving/assuming finite moments | |
| **REGULARITY_GAP** | Differentiability/Lipschitz/convexity used but not established | |
| **STOCHASTIC_MODE_CONFUSION** | Mixes a.s./in prob./in L²/in expectation | |

### Group C: Model & Parameter Tracking

| Category | Description | Example |
|----------|-------------|---------|
| **MISSING_DERIVATION** | A quantity is used but never derived from the model | Risk functional with undefined B, W |
| **HIDDEN_ASSUMPTION** | Proof silently uses a condition not in the theorem | Gaussianity assumed but not stated |
| **INSUFFICIENT_ASSUMPTION** | Hypotheses too weak for proof (counterexample exists) | Moment conditions admitting 2-point distributions |
| **DIMENSION_TRACKING** | Parameter dependence (d, n, K, ...) not explicit | d enters only through κ |
| **NORMALIZATION_MISMATCH** | Coordinate/scaling conventions inconsistent | Rescaled vs raw coordinates |
| **CONSTANT_DEPENDENCE_HIDDEN** | "C" depends on d,n,K but treated as universal | |

### Group D: Scope & Claims

| Category | Description | Example |
|----------|-------------|---------|
| **SCOPE_OVERCLAIM** | Conclusion stated more broadly than proof supports | "β_K=0" with only generic overlap |
| **REFERENCE_MISMATCH** | Cited theorem's hypotheses not verified at point of use | |

## Two-Axis Severity System

### Axis A — Proof Status (what is wrong)

| Status | Meaning |
|--------|---------|
| **INVALID** | Statement false as written (counterexample exists or contradiction) |
| **UNJUSTIFIED** | Could be true, but current proof does not establish it |
| **UNDERSTATED** | True only after strengthening assumptions |
| **OVERSTATED** | True only after weakening conclusion / adding qualifiers |
| **UNCLEAR** | Ambiguous notation / definition drift (not wrong per se) |

### Axis B — Impact (how much breaks)

| Impact | Meaning |
|--------|---------|
| **GLOBAL** | Breaks main theorem or core dependency chain |
| **LOCAL** | Affects a side result but not the main theorem |
| **COSMETIC** | Exposition only |

### Severity Labels (derived)

| Label | Definition |
|-------|------------|
| **FATAL** | INVALID + GLOBAL |
| **CRITICAL** | (INVALID + LOCAL) or (UNJUSTIFIED + GLOBAL) |
| **MAJOR** | (UNJUSTIFIED + LOCAL) or (UNDERSTATED/OVERSTATED + GLOBAL) |
| **MINOR** | Clarity / notation / dimension bookkeeping that doesn't change claims |

## Side-Condition Checklists for Common Theorems

When the proof invokes any of the following, require explicit verification of ALL listed conditions:

| Theorem | Required Conditions |
|---------|-------------------|
| **DCT** (Dominated Convergence) | Pointwise a.e. convergence + integrable dominating function |
| **MCT** (Monotone Convergence) | Monotone increasing + non-negative |
| **Fubini/Tonelli** | Product measurability + integrability (Fubini) or non-negative (Tonelli) |
| **Leibniz integral rule** | Continuity of integrand + dominating function for derivative |
| **Implicit Function Theorem** | Continuous differentiability + non-singular Jacobian |
| **Taylor with remainder** | Sufficient differentiability + remainder form (Lagrange/integral) |
| **Jensen's inequality** | Convexity of function + integrability |
| **Cauchy-Schwarz** | Correct inner product space + integrability of both factors |
| **Weyl/Davis-Kahan** | Symmetry/Hermiticity + perturbation bound conditions |
| **Analytic continuation** | Domain connectivity + identity theorem conditions |
| **WLOG reduction** | Invariance under claimed symmetry + reduction is reversible |

## Workflow

### Phase 0: Preparation

1. **Locate the proof**: Find the main `.tex` file(s).
2. **Read the entire proof**: Extract list of all theorems/lemmas/propositions/corollaries/definitions/assumptions.
3. **Read reference materials**: Reference papers, prior results.
4. **Build a section map**: Structured list with line numbers and key claims.
5. **Identify the main theorem**: Central result, assumptions, claims.

### Phase 0.5: Proof-Obligation Ledger

Build formal accounting artifacts. Save to `PROOF_SKELETON.md`:

#### 1. Dependency DAG
Nodes = Definitions / Assumptions / Lemmas / Theorems. Edges = "uses". **Detect cycles** (including semantic circularity where Lemma A uses a corollary that quietly depends on A).

#### 2. Assumption Ledger
For each theorem/lemma, list every hypothesis with WHERE each is verified (or mark "UNVERIFIED"). Track **usage-minimal assumption sets** — which assumptions were actually used vs merely stated.

#### 3. Typed Symbol Table
Each symbol must have a **type signature**:
```
κ : scalar ∈ (0,1), depends on (d, α_t, Σ, μ)
u* : vector ∈ ℝ^d, u* = C^{-1}m
B^even : matrix ∈ ℝ^{(L+1)×(L+1)}, symmetric PSD
Ψ_v : function ℝ → ℝ, analytic in (ζ,κ), parity determined by v
```
Flag any symbol whose meaning changes or whose type is inconsistent across uses.

#### 4. Canonical Quantified Statements
For each theorem/lemma, rewrite the statement with **explicit quantifiers, domains, and limit order**:
```
∀K ≥ 3, ∀π ∈ Π_K^{ms,∘} \ E_K, ∃κ_0 > 0 such that ∀κ ∈ (0, κ_0):
  h_act^{(K,π)} = Θ(κ^{α_K^act})  [uniform in π on compact subsets]
```
If you cannot restate a theorem this precisely, mark it **UNCLEAR — needs disambiguation**.

#### 5. Micro-Claim Inventory
Every nontrivial step becomes a numbered micro-claim in **sequent form**:
```
MC-17: Context: [Lemma 3.1, κ < κ_0, Z_κ has bounded moments up to order 2m+2]
       ⊢ Goal: P̂_0 is positive definite
       Rule: monomials linearly independent on support of continuous distribution
       Side-conditions: positive density near origin ✓ (by GMM weak convergence)
```
Each micro-claim has: justification rule name + required conditions + where conditions are proven.

#### 6. Limit-Order Map
Track every asymptotic statement's **limit order and uniformity scope**:
```
h_act = Θ(κ^α)  [as κ→0, uniform in π on compact subsets of Π_K, for fixed K]
τ_act ~ (b/a)n   [as n→∞, for fixed κ,K,π with x_K ≪ 1]
```
Flag any statement where limit order is ambiguous or uniformity is unclear.

### Phase 1: First Review (Codex GPT-5.4 xhigh)

Submit the **complete proof content** with the following **mandatory reviewer checklist** in the prompt:

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    You are performing a rigorous mathematical proof review. For EVERY theorem,
    lemma, and proposition, check ALL of the following:

    ## MANDATORY CHECKS

    A. DEFINITIONS: List any symbol whose meaning is ambiguous or changes.
    B. HYPOTHESIS DISCHARGE: For each lemma/theorem APPLICATION (not statement),
       list each hypothesis and whether it was verified, with location.
    C. INEQUALITY AUDIT: For each inequality chain, verify direction, missing
       absolute values, missing conditions (convexity, PSD, integrability).
    D. INTERCHANGE AUDIT: Flag every limit/derivative/expectation/integral
       interchange. State which theorem justifies it (DCT/MCT/Fubini/Leibniz)
       and which conditions are verified/missing.
    E. PROBABILITY MODE: Track whether claims are a.s./in prob./in expectation/
       w.h.p. Ensure transitions are justified.
    F. UNIFORMITY & CONSTANTS: For every O(·), o(·), Θ(·), ≲, state whether
       it is uniform over all parameters. List hidden parameter dependence.
    G. EDGE/DEGENERATE CASES: Attempt to break each key lemma with a 1D,
       low-rank, or extreme-parameter construction.
    H. DEPENDENCY CONSISTENCY: Detect cycles or forward references to unproven
       results.

    ## OUTPUT FORMAT (per issue)
    For each issue found, provide:
    - id: sequential number
    - status: INVALID / UNJUSTIFIED / UNDERSTATED / OVERSTATED / UNCLEAR
    - impact: GLOBAL / LOCAL / COSMETIC
    - category: [from taxonomy]
    - location: section/equation/line
    - statement: what the proof claims
    - why_invalid: why this is wrong or unjustified
    - counterexample: YES (describe) / NO / CANDIDATE (describe attempt)
    - affects: which downstream results break if this is wrong
    - minimal_fix: how to fix it

    [FULL PROOF CONTENT HERE]
```

**Save the threadId.** Parse into structured issue list. Write to `PROOF_AUDIT.md`.

### Phase 1.5: Counterexample Red Team

For each CRITICAL or MAJOR issue, and for every key lemma that introduces:
- a new inequality bound
- an identifiability/uniqueness claim
- a curvature/PSD/strong convexity assertion
- a uniform-in-parameter claim
- a convergence mode upgrade (pointwise → uniform, in prob → w.h.p.)

Systematically attempt to construct counterexamples using:

| Strategy | Description |
|----------|-------------|
| **Dimensional collapse** | Set d=1 or 2, K=2, n small |
| **Degeneracy** | Singular covariance, tiny weight, overlapping means, identical components |
| **Extremal distributions** | Two-point ±a, bounded non-subGaussian, heavy tails |
| **Adversarial parameter scaling** | Pick parameters making neglected terms dominate |
| **Numeric falsification** | Translate lemma to a function, brute-force optimize over small domain |

**Rule**: Label "counterexample found" ONLY if algebraically verified. Otherwise log as "candidate counterexample — needs verification."

Record all attempts (successful or not) in `PROOF_AUDIT.md`.

### Phase 2: Fix Implementation

For each issue, ordered by severity (FATAL → CRITICAL → MAJOR → MINOR):

#### Step 2a: Choose fix strategy
For each issue, explicitly choose one of:
- **ADD_DERIVATION**: Write missing proof steps
- **STRENGTHEN_ASSUMPTION**: Add conditions to theorem statement
- **WEAKEN_CLAIM**: Reduce conclusion scope
- **ADD_REFERENCE**: Cite known result + verify its conditions apply

Log this choice — it is a scope-changing decision when it alters theorem statements.

#### Step 2b: Derive the fix mathematically
- Complete mathematical derivation, not just a claim
- If new proposition/lemma needed, write in full theorem-proof style

#### Step 2c: Implement in LaTeX
- Edit the `.tex` file
- Preserve existing `\label` references where possible

#### Step 2d: Record the fix
```markdown
### Fix N: [SHORT TITLE]
**Issue**: [id] [CATEGORY] — [description]
**Severity**: FATAL / CRITICAL / MAJOR / MINOR
**Status**: INVALID / UNJUSTIFIED / UNDERSTATED / OVERSTATED
**Impact**: GLOBAL / LOCAL / COSMETIC
**Fix strategy**: ADD_DERIVATION / STRENGTHEN_ASSUMPTION / WEAKEN_CLAIM / ADD_REFERENCE
**Location**: Section X, Lines Y-Z

**BEFORE**: [what the proof originally did]
**WHY WRONG**: [mathematical problem, with counterexample if applicable]
**AFTER**: [what the fix does]
**KEY EQUATION**: [central new equation]
**PROOF OBLIGATIONS ADDED**: [new conditions/lemmas introduced]
**DOWNSTREAM EFFECTS**: [which results now need re-checking]
```

#### Step 2e: Compile check
```bash
pdflatex -interaction=nonstopmode <file>.tex 2>&1 | grep -E "Error|Warning|undefined"
```

### Phase 3: Re-Review (Codex GPT-5.4 xhigh)

Launch a fresh reviewer agent for the next review round. Do not use `send_input` here; proof-checker keeps each round independent. Request the same mandatory checklist.

Check acceptance gate. If not met, repeat Phases 2-3 (up to MAX_REVIEW_ROUNDS).

### Phase 3.5: Global Closure & Independent Verification

#### Global closure checks
After all fixes, verify the proof as a whole:
- **Statement–conclusion match**: Does the proof end with EXACTLY what the theorem claims (quantifiers, constants, uniformity)?
- **All obligations discharged**: Every node in the obligation DAG is proven or explicitly assumed (and the theorem statement includes it).
- **Case analysis coverage**: Cases partition the domain AND include boundary/degenerate cases.
- **Induction correctness** (if applicable): Base case, inductive step, correct use of IH, induction measure strictly decreases.
- **WLOG reductions**: Each "without loss of generality" spawns a micro-claim proving the reduction is lossless.
- **No silent assumption strengthening**: Any fix that strengthened assumptions has propagated to the main theorem statement.

#### Independent second review for FATAL/CRITICAL fixes
For any fix that resolved a FATAL or CRITICAL issue, submit the **fixed section alone** (without showing the previous critique) to a **fresh Codex thread**:

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    Blind review of the following proof section. You have NOT seen any prior
    review or discussion. Check every step for correctness, hidden assumptions,
    illegal interchanges, and counterexamples.
    [FIXED SECTION ONLY]
```

If the blind reviewer finds new issues, re-enter Phase 2.

#### Regression proof-audit
After fixes, re-run:
- DAG acyclicity check (no new cycles introduced)
- Counterexample suite on all DOWNSTREAM lemmas of modified results
- Assumption-delta report: what became stronger/weaker due to fixes?

### Phase 3.9: Unrecoverable Proof Protocol

If acceptance gate is not met after MAX_REVIEW_ROUNDS, output a **Proof Unrecoverable Report**:
1. Minimal set of blocking FATAL/CRITICAL issues that could not be resolved
2. Salvage options ranked: (a) weaken claim, (b) strengthen assumptions, (c) add missing lemmas, (d) restructure argument
3. Which parts of the proof are likely still reusable
4. Recommended next steps for the author

Do NOT silently declare success. The report must be honest.

### Phase 4: Audit Report Generation

Generate `proof_audit_report.tex` with:

1. **Overview table**: All issues with two-axis severity, category, fix strategy, status
2. **Before/After logic chain**: Red (BEFORE) → Green (AFTER) comparison
3. **For each fix**: original proof → why wrong → counterexample (if any) → complete derivation → remaining subtleties
4. **Proof-obligation diff**: What was unverified before, what is verified now
5. **Summary**: Now proven / still assumed / open problems
6. **Colored boxes**: BEFORE (red), AFTER (green), WHY WRONG (orange), KEY INSIGHT (blue), WARNING (yellow)

Compile: `pdflatex proof_audit_report.tex && pdflatex proof_audit_report.tex`

### Phase 5: State Persistence

Write `PROOF_CHECK_STATE.json`:
```json
{
  "status": "completed",
  "rounds": 2,
  "threadId": "...",
  "fatal_fixed": 0,
  "critical_fixed": 3,
  "major_fixed": 2,
  "minor_fixed": 1,
  "counterexamples_found": 1,
  "counterexample_candidates": 2,
  "acceptance_gate": "PASS",
  "timestamp": "..."
}
```

## Key Rules

### Mathematical rigor
- **Never accept a proof step on faith**. "Clearly" / "it follows" / "by standard arguments" are red flags — each must spawn a micro-claim.
- **Hypothesis discharge**: Every time a lemma is APPLIED, verify EACH of its hypotheses at that point. Use the side-condition checklists above.
- **Interchange discipline**: Every swap of limit/expectation/derivative/integral must cite a theorem (DCT/MCT/Fubini/Leibniz) and verify its conditions with explicit dominating function or integrability proof.
- **Uniformity discipline**: Every O(·)/Θ(·) must declare what parameters it is uniform over. "O(1)" that secretly depends on d,n,K is a CONSTANT_DEPENDENCE_HIDDEN issue.
- **Quantifier discipline**: Check ∀/∃ order. "For sufficiently small κ" must specify: does κ₀ depend on K? On π? On d?
- **Counterexample-first**: Before trying to fix a gap, first try to break it.
- **WLOG prohibition**: Every "without loss of generality" must have an explicit micro-claim proving the reduction. No free WLOGs.
- **No silent assumption strengthening**: Any fix that adds conditions must propagate to the theorem statement.

### Cross-model protocol
- **Claude analyzes, Codex reviews**: Claude reads proof, formulates questions, implements fixes. Codex provides adversarial review.
- **Codex reasoning always xhigh**: Never downgrade.
- **Send full content**: Don't summarize — send actual math for line-by-line checking.
- **Preserve threadId**: Use `codex-reply` for follow-up rounds.

### Fix quality
- **Minimal fixes**: Fix exactly what's broken, nothing more.
- **Full derivation**: Every fix includes complete mathematical argument.
- **Explicit scope decisions**: Each fix is tagged ADD_DERIVATION / STRENGTHEN_ASSUMPTION / WEAKEN_CLAIM / ADD_REFERENCE.
- **Compile after each fix**: LaTeX must compile cleanly.

### Scope honesty
- **Don't overclaim**: If a fix makes a result conditional, say so.
- **Separate "proven" from "assumed"**: The audit report has an explicit section for this.
- **Log open problems**: Issues requiring future work are listed, not hidden.

## Output Files

| File | Content | When |
|------|---------|------|
| `PROOF_SKELETON.md` | Dependency DAG + assumption ledger + micro-claims | Phase 0.5 |
| `PROOF_AUDIT.md` | Cumulative round-by-round audit log | Updated each round |
| `PROOF_AUDIT.json` | Machine-readable submission verdict (see below) | Always emitted |
| `proof_audit_report.tex/.pdf` | Formal before/after report | Phase 4 |
| `PROOF_CHECK_STATE.json` | State for recovery | Phase 5 |

## Submission Artifact Emission

This skill **always** writes `PROOF_AUDIT.json` at the paper directory
root (i.e. `paper/PROOF_AUDIT.json` when invoked from `/paper-writing`
with paper-dir `paper/`; `<your-paper-dir>/PROOF_AUDIT.json` when invoked
standalone), regardless of caller or whether the paper contains theorems.
A paper with no `\begin{theorem}` / `\begin{lemma}` / `\begin{proof}` emits
verdict `NOT_APPLICABLE`; silent skip is forbidden. `paper-writing`
Phase 6 and `tools/verify_paper_audits.sh` both rely on this artifact
existing at `<paper-dir>/PROOF_AUDIT.json`.

The artifact conforms to the schema in `shared-references/assurance-contract.md`:

```json
{
  "audit_skill":      "proof-checker",
  "verdict":          "PASS | WARN | FAIL | NOT_APPLICABLE | BLOCKED | ERROR",
  "reason_code":      "all_proofs_complete | minor_gaps | critical_gap | no_theorems | ...",
  "summary":          "One-line human-readable verdict summary.",
  "audited_input_hashes": {
    "main.tex":                 "sha256:...",
    "sections/4.theory.tex":    "sha256:..."
  },
  "trace_path":       ".aris/traces/proof-checker/<date>_run<NN>/",
  "thread_id":        "<codex mcp thread id>",
  "reviewer_model":   "gpt-5.4",
  "reviewer_reasoning": "xhigh",
  "generated_at":     "<UTC ISO-8601>",
  "details": {
    "theorems_audited": <int>,
    "issues": [ { "id": "T1-H3", "severity": "FATAL|CRITICAL|MAJOR|MINOR",
                  "category": "quantifier|domination|...",
                  "location": "sections/4.theory.tex:L182",
                  "note": "..." }, ... ]
  }
}
```

### `audited_input_hashes` scope

Hash the **declared input set** actually reviewed — the theorem-bearing
`.tex` files passed into this invocation — not a repo-wide union and not
the reviewer's self-reported opened subset. The external verifier rehashes
these entries; any mismatch flags `STALE`.

**Path convention** (must match `tools/verify_paper_audits.sh`): keys are
**paths relative to the paper directory** (no `paper/` prefix — the
verifier resolves relative to the paper dir; prefixing produces
`paper/paper/...` and false-fails as STALE). Use **absolute paths** for
files outside the paper dir.

### Verdict decision table

| Input state                                           | Verdict          | `reason_code` example |
|-------------------------------------------------------|------------------|-----------------------|
| No theorems / lemmas / proofs in paper                | `NOT_APPLICABLE` | `no_theorems`         |
| Theorems present but referenced files unreadable      | `BLOCKED`        | `source_unreadable`   |
| All proof obligations discharged, no gaps             | `PASS`           | `all_proofs_complete` |
| Only MINOR issues (notation / exposition)             | `WARN`           | `minor_gaps`          |
| Any FATAL or CRITICAL issue (logic gap, wrong claim)  | `FAIL`           | `critical_gap`        |
| Reviewer invocation failed (network / malformed)      | `ERROR`          | `reviewer_error`      |

MAJOR issues alone map to `WARN` or `FAIL` at the reviewer's discretion and
must carry an explicit justification in `summary` + `details.issues`.

### Thread independence

Every invocation uses a fresh reviewer agent. Never use `send_input` across
proof-checker runs. Do not accept prior audit outputs
(PAPER_CLAIM_AUDIT, CITATION_AUDIT, EXPERIMENT_LOG) as input — the fresh
thread preserves reviewer independence per
`shared-references/reviewer-independence.md`.

This skill never blocks by itself; `paper-writing` Phase 6 plus the
verifier decide whether the verdict blocks finalization based on the
`assurance` level.

## Example Invocations

```
/proof-checker "neurips_2025.tex"
/proof-checker "check the GMM generalization proof, focus on dimension dependence"
/proof-checker "verify proof in paper.tex — difficulty: nightmare"
```
