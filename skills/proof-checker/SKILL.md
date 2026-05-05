---
name: proof-checker
description: Rigorous mathematical proof verification and fixing workflow. Reads a LaTeX proof, identifies gaps via cross-model review (Codex GPT-5.4 xhigh), fixes each gap with full derivations, re-reviews, and generates an audit report. Use when user says "检查证明", "verify proof", "proof check", "审证明", "check this proof", or wants rigorous mathematical verification of a theory paper.
argument-hint: "[path-to-tex-file or proof-description] [--deep-fix] [--restatement-check]"
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Proof Checker: Rigorous Mathematical Verification & Fixing

Systematically verify a mathematical proof via cross-model adversarial review, fix identified gaps, re-review until convergence, and generate a detailed audit report with proof-obligation accounting.

## Context: $ARGUMENTS

## Constants

- MAX_REVIEW_ROUNDS = 3
- REVIEWER_MODEL = `gpt-5.4` via Codex MCP, reasoning effort always `xhigh`
- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for GPT-5.4 Pro via Oracle MCP. See `shared-references/reviewer-routing.md`.
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

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
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

#### Phase 1 addendum — `--deep-fix` opt-in

If the user passed `--deep-fix` on invocation, append the following block to the reviewer prompt **after** the OUTPUT FORMAT block above (do **not** modify the original block; the new fields are additive). Default invocations skip this block entirely and emit the original output schema unchanged.

```
    ## DEEP-FIX OUTPUT (opt-in, only when --deep-fix is set)

    For EACH issue listed above, additionally provide a `deep_fix_plan`
    that is repair-grade — sufficient for an executor to apply the fix
    in one Edit pass without spawning a follow-up review thread:

    - issue_id: same as the issue id above
    - corrected_statement: the theorem/lemma statement as it should
      read after the fix, with explicit quantifiers, regime conditions,
      and uniformity scope (LaTeX, paste-ready)
    - changed_equations: list of {before: <LaTeX>, after: <LaTeX>}
      pairs for each equation that needs replacement
    - downstream_labels: list of \label{...} keys whose statements or
      proofs depend on this fix and must be re-checked or rewritten
    - minimal_tex_patch_plan: ordered list of concrete edits, each as
      {file: <path>, anchor_old: <unique LaTeX snippet to find>,
       replacement_new: <LaTeX to insert>}; the executor will pass
      these directly to its file-editing tool
    - closure_tests: 2-5 sanity checks the executor must run after
      applying the fix (e.g., "verify constant_dependence_diff matches
      computed value", "limit case γ→0 reduces to identity",
      "dimension count matches before/after")

    ## ALGEBRA / TYPE SANITY PASS (opt-in, only when --deep-fix is set)

    If any issue invokes Schur test, Young's inequality, Cauchy-Schwarz,
    Hölder, quadratic form, operator norm, or power counting, the
    deep_fix_plan for that issue MUST also include an `algebra_sanity`
    object:

    - dimension_table: map of {symbol: type_signature}, e.g.
      {"K(i,α)": "scalar ≥ 0",
       "‖K‖_{2→2}": "scalar ≥ 0",
       "Σ_i V_i^rem": "scalar quadratic in w"}
    - power_count: number of times each operator-norm or Schur factor
      appears on each side; flag mismatch as INVALID
    - zero_coupling_check: evaluate the expression at γ=0 (or the
      analogous degenerate point); confirm it reduces to the expected
      identity / vanishing case
    - constant_dependence_diff: list of constants whose dependence on
      (d, K, n, ...) changes between BEFORE and AFTER, with the new
      explicit dependence written out

    Be precise. The executor will apply this plan literally; vague
    prose ("strengthen the bound", "redo the Schur step") is not
    acceptable in deep-fix mode. If you cannot produce a precise plan
    for an issue, omit that issue's deep-fix block and signal the
    deep-fix path is unavailable — do NOT emit a vague plan, and do
    NOT add a deep-fix-only category (e.g. UNCLEAR_DEEP_FIX) into the
    standard issue list, since that contaminates default-call output.
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

Use `codex-reply` with saved threadId. Include fix summaries. Request the same mandatory checklist.

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

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
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

### Phase 3.6: Theorem Restatement Regression (opt-in)

**Default**: skipped. Existing callers see no change.

**Opt-in**: pass `--restatement-check` on invocation. The skill then runs a cross-location consistency pass after Phase 3.5 (Global Closure) and before Phase 3.9 (Unrecoverable Protocol).

This phase catches a specific class of bugs that Phase 3.5's "Statement-conclusion match" check does NOT catch: **drift between the canonical theorem statement and its restatements elsewhere in the paper** (summary tables, "Key Contributions" / "Summary" sections, abstract, discussion, captions). Common drift patterns observed in practice:

- Main theorem makes a partly-conditional claim (e.g., "regime A unconditional, regime B conditional on assumption X") but a later summary cites it as the fully unconditional version.
- Main theorem κ exponent is `O(d²K²)` but a constants table writes `O(K²)`.
- Main theorem regime condition is squared envelope, but a remark elsewhere still shows the first-order envelope.
- Restatement quietly drops a quantifier ("for $n \ge n_0$") that the proof relied on.

#### Algorithm

1. **Build canonical statement table.** Scan all `*.tex` files in the paper for `\begin{theorem}` / `\begin{lemma}` / `\begin{proposition}` / `\begin{corollary}` blocks with a `\label{...}`. For each: record `(label, full_statement_text, file:line_range)`.

2. **Collect restatement candidates.** For each canonical label `thm:foo`:
   - Every `\Cref{thm:foo}` / `\ref{thm:foo}` / `\cref{thm:foo}` invocation, with the surrounding 2 sentences as candidate restatement context.
   - Rows in tables (`\begin{tabular}` … `\end{tabular}`) that mention the label, the theorem's informal name, or its constants.
   - Bullets in "Key Contributions" / "Summary" / "Main Results" lists.
   - Sentences in the abstract and introduction that paraphrase the theorem.

3. **Normalized diff.** For each (canonical_statement, restatement_context) pair:
   - Strip `\,` `\;` `\!` `~`, normalize whitespace, normalize math-mode delimiters (`$..$`, `\(..\)`, display vs inline).
   - Detect drift signatures (one or more):
     - **conditional_loss** — canonical says "under \Cref{ass:X}" or "for w=1"; restatement omits the conditional.
     - **scope_change** — big-O exponent or rate differs (`O(K^2)` vs `O(d^2K^2)`; `√n` vs `n`).
     - **quantifier_loss** — quantifier present canonically (e.g. "for $n \ge n_0$", "for sufficiently small $\gamma$") absent in restatement.
     - **regime_envelope_change** — first-order leakage `Cγ/(1-Δγ)` vs squared envelope `(Cγ/(1-Δγ))²` (or analogous).
     - **constant_change** — different numeric constant or different parameter dependence stated.
     - **variable_rename** — same role in argument played by differently-named symbol with no explicit alias.

4. **Emit findings.** Each detected drift becomes an entry in `details.restatement_drift` (see "Submission Artifact Emission" below). Severity defaults to **MAJOR** (UNDERSTATED/OVERSTATED + GLOBAL); reviewer may downgrade to MINOR if drift is purely cosmetic (e.g. `\,` placement) and upgrade to CRITICAL only if the restatement is used downstream as if it were the canonical (e.g. another proof cites the restated version).

#### What this phase does NOT do
- It does **not** fix drift automatically. The output is advisory; the executor or a follow-up `--deep-fix` run handles the rewrite.
- It does **not** alter `details.issues`; restatement drift is reported as a sibling field, so existing consumers reading `issues[]` see no schema change.
- It does **not** alter the top-level `verdict` decision rule. A paper with non-empty `restatement_drift` may still emit `PASS` if all proof obligations are otherwise discharged; the drift is independent of proof correctness. (The reviewer may at its discretion mirror a **CRITICAL**-severity drift into the `issues` list as a regular issue — typically when the restated version is used downstream as if it were canonical — but that is a per-issue judgment, never an automatic rule. MAJOR or MINOR drift never mirrors into `issues`.)

#### Failure mode
If `--restatement-check` is set but the cross-location scan cannot complete, emit `details.restatement_drift: []` plus `details.restatement_check_status: "unavailable"` with a one-line note explaining why. Verifier gates and downstream skills MUST treat `"unavailable"` identically to the field being absent: not blocking. Phases 1 / 1.5 / 2 / 3 / 3.5 / 3.9 / 4 / 5 still run normally. Cases that trigger this fallback include:
- Unreadable `.tex` (parser / encoding error on a file that contains a theorem block).
- Ambiguous label resolution (e.g., the same `\label{thm:foo}` appears more than once with no clear canonical pick).
- **No labeled canonical theorem-like block found** (the algorithm only inspects `\begin{theorem|lemma|proposition|corollary}` blocks with an explicit `\label{...}`; if there is no such block, there is nothing to compare restatements against).

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

## Deep-Fix Mode (opt-in)

**Default**: disabled. The Phase 1 reviewer emits issues with `minimal_fix` (a 1-2 sentence pointer); existing callers see no change.

**Opt-in**: pass `--deep-fix` on invocation. The Phase 1 reviewer prompt is **augmented** (not replaced) with the "DEEP-FIX OUTPUT" and "ALGEBRA / TYPE SANITY PASS" blocks above, so the reviewer also returns a `deep_fix_plan` per issue: corrected statement, changed equations, downstream label list, minimal LaTeX patch plan, and closure tests. Issues invoking Schur / Young / Cauchy-Schwarz / Hölder / quadratic forms / operator norms / power counting additionally carry an `algebra_sanity` block (dimension table + power count + zero-coupling check + constant-dependence diff).

### Why opt-in
The default `minimal_fix` prose is intentionally short — it suits the common case where the executor wants high-level pointers and will derive the patch separately. Forcing `deep_fix_plan` on every run would (a) inflate every reviewer call by 2-5×, (b) trigger re-review thrash for issues the executor has already decided to weaken or defer, and (c) change the shape of `details.issues` for every existing caller. The flag preserves zero behavior change for default invocations while letting the executor request repair-grade output when the fix is going to be applied immediately.

### Effect when enabled
- The Phase 1 reviewer prompt is augmented with the deep-fix and algebra-sanity blocks; nothing in the original mandatory checklist or output format is removed.
- `PROOF_AUDIT.json` `details` gains a sibling field `deep_fix_plans` (parallel to `details.issues`); see "Submission Artifact Emission" below.
- The top-level `verdict`, `reason_code`, and `summary` are **unchanged in shape and decision rule**: deep-fix output is advisory tooling for the executor, not a verdict-altering signal.
- Verifier gates and downstream skills (`paper-writing` Phase 6, `tools/verify_paper_audits.sh`) MUST treat absence of `deep_fix_plans` as the only valid default state and MUST NOT block on its presence or content.

### When opt-in is appropriate
- The executor intends to apply the fix in the same session and wants to skip a follow-up "give me a concrete patch" thread.
- A previous default-mode run identified a CRITICAL or MAJOR issue whose `minimal_fix` was too vague to act on (e.g., "redo the Schur step" without specifying the corrected operator-norm bound).
- Algebra-heavy proofs with Schur / quadratic-form / operator-norm steps where the reviewer's first pass has consistently produced under-specified fixes.

### Failure modes

A deep-fix-only failure must never contaminate the default proof-check output. All of the following paths emit `details.deep_fix_status: "unavailable"` + `details.deep_fix_plans: []` (with a one-line note in `details.deep_fix_note`) and leave the standard issue list, top-level verdict, reason_code, and summary unchanged:

- The reviewer refuses to produce a repair-grade plan because the fix would require choices the reviewer is unwilling to make.
- The Phase 1 reviewer call returns truncated or malformed deep-fix output (parse failure on the augmented section).
- The augmented Phase 1 call times out before producing the deep-fix block, but otherwise returned a valid normal proof review.

Verifier gates MUST treat `unavailable` identically to the field being absent: not blocking. Do **not** add a `UNCLEAR_DEEP_FIX` (or any deep-fix-only) entry into `details.issues`, since `details.issues` is the default schema's issue list and adding deep-fix-specific failures to it would change default behavior for callers without the flag.

If the augmented Phase 1 call fails so badly that the normal proof review cannot be recovered (e.g., the reviewer thread itself errored), retry once with the unaugmented prompt; if that also fails, fall through to the existing reviewer-failure path that maps to the top-level `ERROR` verdict.

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
- **Preserve threadId within a single run**: Use `codex-reply` for Phase 3 follow-up rounds within the same top-level `/proof-checker` invocation, so the reviewer keeps prior-issue context when judging whether a fix closed the gap. Across separate top-level invocations, always start a fresh thread (see "Thread independence" below).

### Fix quality
- **Minimal fixes**: Fix exactly what's broken, nothing more.
- **Full derivation**: Every fix includes complete mathematical argument.
- **Explicit scope decisions**: Each fix is tagged ADD_DERIVATION / STRENGTHEN_ASSUMPTION / WEAKEN_CLAIM / ADD_REFERENCE.
- **Compile after each fix**: LaTeX must compile cleanly.

### Scope honesty
- **Don't overclaim**: If a fix makes a result conditional, say so.
- **Separate "proven" from "assumed"**: The audit report has an explicit section for this.
- **Log open problems**: Issues requiring future work are listed, not hidden.

### Opt-in flag discipline
- **Deep-fix is opt-in only**: never auto-enable; never block on `deep_fix_plans` content; existing callers must observe identical reviewer output and identical JSON schema if they do not pass `--deep-fix`.
- **Reviewer prompt augmentation is additive**: the deep-fix block is appended to the Phase 1 prompt, not substituted for any part of it. The original mandatory checklist (A-H) and original per-issue OUTPUT FORMAT remain in place verbatim.
- **Restatement check is opt-in only**: Phase 3.6 runs only when `--restatement-check` is set; existing callers must observe identical reviewer output and identical JSON schema if they do not pass the flag.
- **No Phase reordering**: enabling Phase 3.6 inserts it strictly between 3.5 and 3.9; it does not skip any other phase or change their semantics.
- **No verdict crosstalk**: neither deep-fix output nor `restatement_drift` ever alters top-level `verdict` or `reason_code`. A paper with non-empty drift or with deep-fix plans may still pass; a paper with FAIL verdict stays FAIL whether or not either flag was set.

## Output Files

| File | Content | When |
|------|---------|------|
| `PROOF_SKELETON.md` | Dependency DAG + assumption ledger + micro-claims | Phase 0.5 |
| `PROOF_AUDIT.md` | Cumulative round-by-round audit log | Updated each round |
| `PROOF_AUDIT.json` | Machine-readable submission verdict (see below) | Always emitted |
| `proof_audit_report.tex/.pdf` | Formal before/after report | Phase 4 |
| `PROOF_CHECK_STATE.json` | State for recovery | Phase 5 |

When `--restatement-check` is set, `PROOF_AUDIT.json` additionally carries `details.restatement_drift` and `details.restatement_check_status`; both fields are omitted when the flag is unset. See "Submission Artifact Emission" below.

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

### Optional: `details.deep_fix_plans` (only when `--deep-fix` is set)

```json
"details": {
  ...
  "deep_fix_plans": [
    {
      "issue_id": "T1-H3",
      "corrected_statement": "<LaTeX, paste-ready>",
      "changed_equations": [{"before": "<LaTeX>", "after": "<LaTeX>"}, ...],
      "downstream_labels": ["thm:convergence", "cor:minimax", ...],
      "minimal_tex_patch_plan": [
        {"file": "sections/4.theory.tex",
         "anchor_old": "<unique LaTeX snippet>",
         "replacement_new": "<LaTeX to insert>"},
        ...
      ],
      "closure_tests": [
        "verify constant_dependence_diff matches computed value",
        "limit case γ→0 reduces to identity",
        ...
      ],
      "algebra_sanity": {
        "dimension_table": {"<symbol>": "<type_signature>", ...},
        "power_count": "<one-line check>",
        "zero_coupling_check": "<one-line check>",
        "constant_dependence_diff": "<before vs after>"
      }
    }
  ],
  "deep_fix_status": "ok" | "unavailable"
}
```

Field semantics:
- Both `deep_fix_plans` and `deep_fix_status` are **omitted entirely** when the flag is not set. The default schema does not include either key.
- When the flag is set and reviewer returns well-formed plans, `deep_fix_status` is `"ok"` and `deep_fix_plans` mirrors `details.issues` one-to-one (each plan referenced by `issue_id`); `algebra_sanity` is present only for issues invoking Schur / Young / Cauchy-Schwarz / Hölder / quadratic-form / operator-norm / power-counting steps.
- When the flag is set but reviewer output is malformed or truncated, `deep_fix_status` is `"unavailable"` and `deep_fix_plans` is `[]`. Downstream consumers MUST treat `"unavailable"` identically to the field being absent: not blocking.
- Downstream consumers MUST treat absence of either field as the only valid default state and MUST NOT raise on missing.
- `deep_fix_plans` is advisory tooling for the executor; `tools/verify_paper_audits.sh` and `paper-writing` Phase 6 do not block on its content or shape.

### Optional: `details.restatement_drift` (only when `--restatement-check` is set)

```json
"details": {
  ...
  "restatement_drift": [
    {
      "label": "thm:main",
      "canonical_location": "sections/2.setup.tex:117",
      "restatement_location": "sections/appendix.tex:1614",
      "drift_type": "conditional_loss" | "scope_change" | "quantifier_loss" |
                    "regime_envelope_change" | "constant_change" | "variable_rename",
      "canonical_excerpt": "<short LaTeX>",
      "restatement_excerpt": "<short LaTeX>",
      "severity": "MAJOR" | "MINOR" | "CRITICAL",
      "note": "..."
    }
  ],
  "restatement_check_status": "ok" | "unavailable"
}
```

Field semantics:
- Both `restatement_drift` and `restatement_check_status` are **omitted entirely** when the flag is not set. The default schema does not include either key.
- When the flag is set and the cross-location scan completes, `restatement_check_status` is `"ok"` and `restatement_drift` lists detected pairs (possibly empty if none found).
- When the scan fails (per "Failure mode" in Phase 3.6), `restatement_check_status` is `"unavailable"` and `restatement_drift` is `[]`.
- Downstream consumers MUST treat absence or `"unavailable"` identically as the default state and MUST NOT raise on missing.
- `restatement_drift` does **not** alter `details.issues` and does **not** change the top-level `verdict` decision rule. The reviewer may at its discretion mirror a CRITICAL-severity drift into `details.issues` as a regular issue, but that is a per-issue judgment, not an automatic schema-driven rule.

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

Every **top-level** `/proof-checker` invocation starts a fresh `mcp__codex__codex` thread; do not reuse a saved threadId across separate invocations of this skill. Within a single top-level invocation, `codex-reply` is the correct primitive to thread the Phase 3 follow-up rounds — the reviewer needs prior-issue context to judge whether a fix actually closed the gap, and the Phase 1→3 flow above explicitly relies on this. The Phase 3.5 "Independent second review for FATAL/CRITICAL fixes" sub-step is the deliberate exception inside a single run: it must spawn a fresh thread so the blind reviewer has no exposure to the original critique.

Do not accept prior audit outputs (PAPER_CLAIM_AUDIT, CITATION_AUDIT, EXPERIMENT_LOG) as input across separate invocations — the cross-run freshness is what preserves reviewer independence per `shared-references/reviewer-independence.md`.

This skill never blocks by itself; `paper-writing` Phase 6 plus the
verifier decide whether the verdict blocks finalization based on the
`assurance` level.

## Example Invocations

```
/proof-checker "neurips_2025.tex"
/proof-checker "check the GMM generalization proof, focus on dimension dependence"
/proof-checker "verify proof in paper.tex — difficulty: nightmare"
/proof-checker "paper/main.tex --deep-fix"            # opt-in: ask reviewer to also emit repair-grade deep_fix_plans
/proof-checker "paper/main.tex --restatement-check"   # opt-in: run Phase 3.6 to detect cross-location theorem-statement drift
/proof-checker "paper/main.tex --deep-fix --restatement-check"   # both opt-ins, independent
```
