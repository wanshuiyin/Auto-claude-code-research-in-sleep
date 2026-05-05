---
name: resubmit-pipeline
description: "Workflow 5: orchestrate a text-only resubmit of a polished paper to a different venue under hard constraints (no new experiments, no bib edits, no framework changes, never overwrite prior submissions). Phase 0 physical isolation, Phase 0.5 health + anonymity check, Phase 1 audit (proof / claim / citation), Phase 2 microedits via auto-loop with edit-whitelist + citation-audit --soft-only, Phase 3 kill-argument adversarial gate, Phase 4 final compile + Overleaf push via /overleaf-sync. Use when user says \"resubmit pipeline\", \"重投流程\", \"port paper to <new venue>\", \"resubmit to <venue>\", \"tighten paper for resubmission\", or has a rejected/withdrawn paper to move to a different top venue under tight time budget."
argument-hint: "[paper-base-dir] [— target-venue: <name>] [— review-corpus: <path>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Resubmit Pipeline: Text-Only Microedit Mode

Compose a polished paper into a new venue under text-only constraints: **$ARGUMENTS**

## Why This Exists

Most ARIS writing workflows assume the input is either a narrative report (Workflow 3) or an in-progress paper that may still need experiments / bib changes / structural edits. Resubmit is a fundamentally different scope:

- The paper is **already polished** — proofs are done, experiments are done, bibliography is curated.
- The user wants to absorb prior reviewer concerns from a previous venue and re-submit, **without** introducing new experiments, new citations, or framework changes (LLM hallucination paranoia + tight resubmit timing + closed compute budget).
- The base submission directory is **read-only** — the new submission must compose into a sibling directory, never mutate prior state.
- Page limit may shrink between source and target venue (e.g., workshop camera-ready → 9-page main).

Existing skills cover adjacent territory but none of this exact composition: `/rebuttal` builds the OpenReview-style response document, not in-paper microedits; `/auto-paper-improvement-loop` is the per-round engine but presupposes someone has already chosen the base manuscript, migrated venue format, set the edit whitelist, queued the reviewer feedback, and decided what NOT to change. `/resubmit-pipeline` fills that orchestration gap.

## When to Use

- A theory or system paper was rejected at venue A and you want to resubmit to venue B with tight time budget (≤ 1-2 weeks).
- You have **3 inputs ready**: the polished paper directory at venue A's format, the target venue B's format/template/style files, and the prior reviewer reports.
- You explicitly do **not** want to re-derive theorems, run new experiments, or change the bibliography.

## When NOT to Use

- The paper still needs experiments — use `/experiment-bridge` → `/auto-review-loop` first.
- The paper still needs structural rewrites or new sections — use `/paper-writing` (Workflow 3).
- You want to write the rebuttal response itself — use `/rebuttal` (Workflow 4).
- The reviewer feedback demands new theorems or new framework — escalate to user before starting; this skill emits `BLOCKED` with `reason_code: out_of_scope_microedit` if it detects this case.

## Constants

- **REVIEWER_MODEL** = inherits from `/auto-paper-improvement-loop`'s default (`gpt-5.4` via Codex MCP) unless the user passes `— reviewer-model: gpt-5.5`. Codex reasoning effort is fixed at `xhigh` for all reviewer calls per the existing skill convention.
- **ROUNDS** = 2 (default; matches `/auto-paper-improvement-loop`'s diminishing-returns line). A 3rd round only fires if Phase 2 reports non-convergence AND the user explicitly approves at the round-2 checkpoint.
- **EFFORT** = `max` (default for resubmit; resubmit is high-stakes). The user can override with `— effort: balanced` if time is extremely tight.
- **EDIT_WHITELIST_PATH** = `<paper-base-dir>/../<NewVenue>/.aris/edit_whitelist.yaml` (auto-generated in Phase 0; user can override with a custom path).
- **NEVER_OVERWRITE** = true (always; this is a hard contract — prior submission directories are immutable).
- **ASSURANCE_LEVEL** = `submission` (default; resubmit always targets a real submission).

## Inputs

Three mandatory inputs:

1. **`paper-base-dir`** — the polished paper at venue A's format. Must contain `main.tex` (or equivalent entry), `sec/` or `sections/`, `references.bib` (or equivalent), and a compiled `main.pdf` (used for visual review).
2. **`— target-venue: <name>`** — one of: `iclr`, `icml`, `neurips`, `aaai`, `ijcai`, `colm`, `tmlr`, `uai`, or `other`. The skill expects venue style files at `<paper-base-dir>/templates/<venue>.{sty,tex,bst}` or in a recognized template directory. If `other`, the user passes `— target-style-dir: <path>`.
3. **`— review-corpus: <path>`** — directory containing prior venue's reviewer reports as `.txt` or `.md` files (one per reviewer, ideally). If `--review-corpus` is omitted, the skill emits `BLOCKED` with `reason_code: missing_review_corpus` because the whole point of resubmit is absorbing those concerns.

Optional:

- **`— reviewer-model: gpt-5.5`** — override the default reviewer (`gpt-5.4`).
- **`— rounds: <int>`** — override default 2.
- **`— assurance: draft`** — relax MANDATORY gates (default `submission`).
- **`— effort: balanced`** — relax `max` if time is critical.
- **`— skip-anonymity-scan`** — skip Phase 0.5 anonymity check (only valid for non-double-blind venues like TMLR; else WARN).
- **`— overleaf-target: <project-id>`** — the Overleaf project ID for Phase 4 push (per `/overleaf-sync setup`).

## Pipeline

### Phase 0: Physical Isolation Setup (zero edits to existing files)

Resubmit's hardest invariant: **never overwrite any prior submission directory**. The new venue's submission lives as a **sibling** of all prior venues.

```bash
# Resolve target-venue → new sibling dir name (capitalized)
NEW_VENUE_DIR="$(dirname "$PAPER_BASE_DIR")/$(echo "$TARGET_VENUE" | sed 's/.*/\u&/')"

# Atomic dir create — `mkdir` (not `mkdir -p`) fails fast if the dir exists,
# avoiding the TOCTOU race window of `[ -e ] && exit; mkdir -p`. The mkdir
# itself must succeed exactly once; if a concurrent run gets there first,
# this errors out per resubmit-pipeline's never-overwrite invariant.
mkdir "$NEW_VENUE_DIR" 2>/dev/null || {
    echo "ERROR: $NEW_VENUE_DIR already exists; resubmit-pipeline never overwrites prior submissions. Pick a different target-venue or rename the existing dir." >&2
    exit 1
}
mkdir -p "$NEW_VENUE_DIR/.aris"
```

**Composition rules** (all `cp`, never `\input{../...}`, never symlink):

1. **`main.tex`** — write fresh for the target venue's `.sty`. Use `templates/<venue>.tex` as the starting skeleton; only the `\title{}`, `\author{}`, abstract include, and section input lines are copied from the base venue's `main.tex`. The new `main.tex` lives entirely inside `$NEW_VENUE_DIR/`.
2. **`sec/` (or `sections/`)** — physical `cp -r $PAPER_BASE_DIR/sec/ $NEW_VENUE_DIR/sec/`. **Do not symlink, do not `\input{../sec/...}` from the new main.** Symlinks break Overleaf zip export; cross-directory `\input` would mutate the shared pool and pollute prior submissions.
3. **`math_commands.tex`** (and any other macro file the sections depend on) — physical `cp` into `$NEW_VENUE_DIR/`.
4. **`Figure/` (or `figures/`)** — copy the directory in (`cp -r`). **Path trap**: existing sections likely write `\includegraphics{Figure/foo.pdf}`. If you set `\graphicspath{{../Figure/}}` from a child directory, it resolves `../Figure/Figure/foo.pdf` — wrong. Either copy `Figure/` in directly (preferred), or use `\graphicspath{{../}}`.
5. **Bibliography** — write `\bibliographystyle{<venue-bst>}` + `\bibliography{../references}` directly in the new `main.tex`. **Never** `\input` an existing `ref.tex` or `references.tex` that already contains its own `\bibliography{}` command (path resolution silently breaks).
6. **`.aris/`** — create `$NEW_VENUE_DIR/.aris/` and write `assurance.txt` containing `submission` (matches the verifier's expected location).

**Output of Phase 0**: a new sibling dir with all source files, no edits to text content yet, ready for compile.

### Phase 0.5: Health Check + Anonymity Scan (still zero text edits)

Before any audit or edit, the paper must compile cleanly on the new venue's style and pass anonymity scan if the target venue is double-blind.

**Compile + page count**:

```bash
cd "$NEW_VENUE_DIR"
latexmk -C
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex 2>&1 | tee compile.log
```

If compile fails: emit `RESUBMIT_REPORT.json` with `verdict: BLOCKED, reason_code: phase_0_5_compile_failed`, surface the error to the user, and stop. Common causes: missing macro from `math_commands.tex`, venue style undefined command, `\graphicspath` issue.

Page count vs venue limit (measure first; do not assume):

```bash
PAGES=$(pdfinfo main.pdf | awk '/^Pages:/ {print $2}')
LIMIT=$(grep -oE "page_limit: [0-9]+" "$NEW_VENUE_DIR/templates/$TARGET_VENUE.tex" | awk '{print $2}')
echo "Pages: $PAGES, Limit: $LIMIT, Delta: $((PAGES - LIMIT))"
```

If `PAGES > LIMIT`, queue Phase 2 to honor a page-shrink heuristic (see "Page-Shrink Heuristic" below).

**Anonymity scan** (skip only if `— skip-anonymity-scan` is passed AND target venue is non-double-blind):

The scan covers **5 layers** (the proposal's 1-layer scan was incomplete):

1. **Surface identifiers**: author surnames, affiliations, institution names, lab codenames, prior funding tag IDs (`grep -E "$(echo $AUTHOR_SURNAMES | tr ' ' '|')|$(echo $AFFILIATIONS | tr ' ' '|')"`).
2. **Self-citation phrasing**: any sentence using "we showed in [...]" or "in our prior work [...]" that names the paper's own authors. Must rewrite to "X et al. [year] shows..." third-person form. Grep regex: `\b(we|our|my|I)\s+(showed|proved|demonstrated|prior work|earlier paper|previous paper)\b`.
3. **Acknowledgments + funding**: scan `acknowledgments.tex` (or `\acknowledgments{}` block) for institution-specific thanks, grant IDs, named collaborators. Comment out for double-blind submission.
4. **Cross-rebuttal references**: scan footnotes and body for "this paper builds on rebuttal at venue X" or "addressing reviewer N's concern from venue X" — these must be removed entirely (they violate anonymity AND signal prior rejection).
5. **Internal codenames / project links**: grep for repo URLs (`github.com/<user>/<project>`), Slack channel names, internal wiki links, and dataset codenames that may identify the lab.

If **any of the 5 layers** triggers a hit, emit `RESUBMIT_REPORT.json` with `verdict: BLOCKED, reason_code: anonymity_scan_failed` and present a per-hit list to the user. They must approve a fix or accept the risk before Phase 1 runs. Layers 4-5 are equally blocking as layers 1-3 — cross-rebuttal references and internal codenames signal both prior-venue identity AND lab identity, both of which violate double-blind in different ways.

**Residual coloring / margin-note scan**:

Search for `\revise{...}`, `\fix{...}`, `\new{...}`, `\todo{...}`, `\todonotes{...}`, `\textcolor{red}{...}` leftovers from camera-ready cycles. List them; user decides whether to keep (some venues accept revision-marker boxes) or strip.

**Output of Phase 0.5**: `BASELINE.md` with initial page count, anonymity-scan summary, residual-color list, overfull-hbox count.

### Phase 1: Audit (zero edits)

Three audits in parallel, all detect-only. The new dir's source files are read; nothing is written except audit artifacts.

| Skill | Purpose | Artifact |
|---|---|---|
| `/proof-checker $NEW_VENUE_DIR/main.tex --restatement-check` | Gap-find on theorems prior reviewers attacked; cross-location consistency between main statement and restatements | `PROOF_AUDIT.json` + `.md` |
| `/paper-claim-audit $NEW_VENUE_DIR/` | Numerical fidelity (every number in body matches what proofs / result files establish) | `PAPER_CLAIM_AUDIT.json` + `.md` |
| `/citation-audit $NEW_VENUE_DIR/ — soft-only` | Wrong-context citations + misattributions, mapped to "soften citing sentence" actions (NOT bib edits) | `CITATION_AUDIT.json` + `.md` |

**Critical**: the third audit MUST run with `— soft-only`. Without that flag, citation-audit emits `KEEP/FIX/REPLACE/REMOVE` verdicts that presuppose bib mutations — incompatible with resubmit's "no bib edits" constraint. With `--soft-only`, the same findings are translated to per-occurrence sentence-rewrite proposals consumable by Phase 2.

**Atomize prior reviewer concerns** in parallel:

```
For each file under $REVIEW_CORPUS:
    Read the reviewer report.
    Atomize into discrete concerns: severity (critical / major / minor),
      type (assumption / novelty / scope / rigor / experiment-coverage / framing),
      addressability (text-fixable / partial / unaddressable-under-constraints).
    Append to KNOWN_WEAKNESSES.md with stable IDs (W1, W2, ...).
```

`KNOWN_WEAKNESSES.md` schema:

```yaml
- id: W1
  severity: major
  type: scope
  source: reviewer_2_venue_a
  concern: "Theorem 3 states a generic result but the proof only handles a specific regime."
  addressability: text-fixable
  recommended_fix: "Narrow Theorem 3's title to 'restricted regime'; add scope qualifier in abstract."
- id: W2
  severity: critical
  type: experiment-coverage
  source: reviewer_3_venue_a
  concern: "No comparison against [prior method X]."
  addressability: unaddressable-under-constraints
  recommended_fix: "Acknowledge in Limitations that this comparison is left for future work."
```

**Output of Phase 1**: 4 artifacts (3 audits + KNOWN_WEAKNESSES.md). All are inputs to Phase 2.

### Phase 2: Targeted Text Microedits via Auto-Improvement Loop

The load-bearing phase. `/auto-paper-improvement-loop` is invoked with **two safety mechanisms**:

1. **`— edit-whitelist <path>`** — a YAML file enumerating allowed paths and forbidden operations. Auto-generated in Phase 0 at `$NEW_VENUE_DIR/.aris/edit_whitelist.yaml`:

   ```yaml
   allowed_paths:
     - "sec/*.tex"
     - "main.tex"
     - "appendix.tex"
   forbidden_paths:
     - "**/*.bib"
     - "**/*.sty"
     - "**/*.bst"
     - "../*Submission/**"           # all prior submission dirs
     - "../*Camera/**"
     - "templates/**"
   forbidden_operations:
     - new_cite                       # blocks \cite{...}, \citep{...}, \citet{...}, \citeauthor{...}
     - new_bibitem                    # blocks \bibitem{...} additions
     - new_theorem_env                # blocks \begin{theorem|lemma|proposition|corollary} additions
     - numerical_claim                # blocks adding numbers / percentages / metrics not present in original
   rationale: "Resubmit mode: text-only microedits, paper structure frozen by user constraint."
   ```

2. **Per-round diff gate via auto-loop's HUMAN_CHECKPOINT** — `/auto-paper-improvement-loop` does not accept `--rounds`, `--reviewer-model`, or `--resume-after-round-checkpoint` flags (those are not in its CLI). It uses the `MAX_ROUNDS = 2` constant and `REVIEWER_MODEL = gpt-5.4` defaults, with an existing `HUMAN_CHECKPOINT` mechanism for round gating. Resubmit-pipeline therefore invokes the loop **once** with `HUMAN_CHECKPOINT = true` so each round pauses for the orchestrator to inspect the diff:

   ```bash
   # Snapshot the new venue dir BEFORE auto-loop runs (for diff baseline,
   # works whether or not paper-base-dir is a git repo)
   SNAPSHOT_DIR="$NEW_VENUE_DIR/.aris/snapshots/round-0"
   mkdir -p "$SNAPSHOT_DIR"
   rsync -a --exclude='.aris' --exclude='*.pdf' --exclude='*.aux' \
         "$NEW_VENUE_DIR/" "$SNAPSHOT_DIR/"

   # Single auto-loop invocation; rounds + checkpoints are loop-internal.
   # The whitelist file is the only resubmit-specific param.
   /auto-paper-improvement-loop "$NEW_VENUE_DIR/" \
       --edit-whitelist "$NEW_VENUE_DIR/.aris/edit_whitelist.yaml" \
       — assurance: submission \
       — effort: "$EFFORT" \
       — human checkpoint: true
   ```

   Inside the loop, at each round-end checkpoint, the resubmit orchestrator inspects:

   ```bash
   for ROUND in 1 2; do  # auto-loop's MAX_ROUNDS = 2
     # auto-loop pauses at HUMAN_CHECKPOINT after each round
     # diff this round vs prior snapshot (works without git)
     diff -ruN "$NEW_VENUE_DIR/.aris/snapshots/round-$((ROUND-1))" "$NEW_VENUE_DIR" \
         > "$NEW_VENUE_DIR/.aris/round-$ROUND-diff.txt"

     # Whitelist compliance check on the diff
     check_whitelist_compliance "$NEW_VENUE_DIR/.aris/round-$ROUND-diff.txt" \
                                  "$NEW_VENUE_DIR/.aris/edit_whitelist.yaml"

     # Selective regression audits (only fire if relevant files touched)
     if grep -qE 'theorem|lemma|proposition|corollary' "$NEW_VENUE_DIR/.aris/round-$ROUND-diff.txt"; then
         /proof-checker "$NEW_VENUE_DIR/main.tex" --restatement-check
     fi
     if grep -qE '[0-9]+(\.[0-9]+)?\s*(%|±|x|×)' "$NEW_VENUE_DIR/.aris/round-$ROUND-diff.txt"; then
         /paper-claim-audit "$NEW_VENUE_DIR/"
     fi

     # Snapshot this round for next-round diff
     rsync -a --exclude='.aris' --exclude='*.pdf' --exclude='*.aux' \
           "$NEW_VENUE_DIR/" "$NEW_VENUE_DIR/.aris/snapshots/round-$ROUND/"

     # Convergence check — see "Convergence Criteria" section below
     # If converged, signal HUMAN_CHECKPOINT to terminate early
   done
   ```

   **Why the snapshot-rsync approach instead of `git diff HEAD~1..HEAD`**: the paper-base-dir is not guaranteed to be a git repo, and even when it is, intermediate states inside one auto-loop round don't produce per-round commits. rsync snapshots are repo-agnostic.

3. **Mapping of edits to concerns** — every proposed edit must be mapped to either (a) an entry in `KNOWN_WEAKNESSES.md` with an ID, OR (b) a Phase 1 audit finding. Un-mapped edits are rejected by the loop's reviewer prompt. This is enforced via the loop's reviewer prompt template (the resubmit-pipeline's invocation passes a custom prompt addendum saying "every fix must cite a W<n> ID or audit finding ID").

**Inputs into the loop's reviewer prompt** (concatenated):

- The 3 Phase 1 audit reports (`PROOF_AUDIT.md`, `PAPER_CLAIM_AUDIT.md`, `CITATION_AUDIT.md`)
- `KNOWN_WEAKNESSES.md`
- A custom addendum: "you are reviewing a resubmit; the user constraint is text-only microedits; every proposed fix MUST cite either a W<n> ID from KNOWN_WEAKNESSES or an audit finding ID; un-mapped fixes are rejected; the edit whitelist is binding."

**Output of Phase 2**: `PAPER_IMPROVEMENT_LOG.md` with per-round diffs, `rejected_by_edit_whitelist` list, and convergence status.

### Phase 3: Adversarial Gate

`/kill-argument $NEW_VENUE_DIR/`

**No `--difficulty` parameter exists** in `/kill-argument` — earlier proposal drafts referenced a non-existent flag. The skill always uses Codex 5.5 + xhigh and runs the standard 2-thread Attack-Adjudication protocol; the `assurance` level (set to `submission` for resubmit) determines whether `FAIL` blocks the final report.

The kill-argument output is **residual-risk reporting**, not auto-rewrite directives. A hostile reviewer may demand framework changes the user banned; the adjudication step exists to **triage** which findings are text-fixable vs need user escalation.

```
Read $NEW_VENUE_DIR/KILL_ARGUMENT.json
For each decomposed_point with verdict in {still_unresolved, partially_answered}:
    If severity_if_unresolved == critical:
        If recommended_fix is text-only AND maps to allowed paths:
            Append to "extra round queue"
        Else:
            Append to "user escalation queue" with note "outside text-only constraint"
```

If extra round queue is non-empty AND user-budget allows: one extra Phase 2 round. Else: stop and surface the user-escalation queue with a written escalation note ("here is what cannot be fixed under your constraints; please decide before submission").

### Phase 4: Final Compile + Diff Report + Overleaf Push

**Final compile**:

```bash
/paper-compile $NEW_VENUE_DIR/main.tex --venue $TARGET_VENUE
```

`/paper-compile` checks page limit, font, bib resolve, figure overflow, and emits `COMPILE_REPORT.json`. If page limit exceeded → trigger page-shrink heuristic (see below).

**Final paper-claim-audit zero-context pass**:

```bash
/paper-claim-audit $NEW_VENUE_DIR/
```

Verifies no Phase 2 microedit accidentally introduced a numerical claim that's not backed by results.

**Diff report**:

```bash
diff -u $PAPER_BASE_DIR/main.tex $NEW_VENUE_DIR/main.tex > $NEW_VENUE_DIR/.aris/DIFF_REPORT.md
for f in $PAPER_BASE_DIR/sec/*.tex; do
    base=$(basename $f)
    diff -u "$f" "$NEW_VENUE_DIR/sec/$base" >> $NEW_VENUE_DIR/.aris/DIFF_REPORT.md
done
```

This goes to the user for skim-review before any export.

**Overleaf push** (if `— overleaf-target: <project-id>` was passed):

Defer entirely to `/overleaf-sync setup` and `/overleaf-sync push`. Do **not** invent a parallel push mechanism — `/overleaf-sync setup` already handles token-stays-in-keychain (token never enters the agent), and `/overleaf-sync push` has a confirmation gate before writing to shared Overleaf state.

```bash
/overleaf-sync setup $OVERLEAF_TARGET   # one-time, user confirms in their terminal
/overleaf-sync push                      # confirmation-gated push from $NEW_VENUE_DIR
```

If `overleaf-target` is not provided, skip Overleaf push and tell the user to either `/overleaf-sync setup <id>` manually or zip-export the directory.

## Page-Shrink Heuristic

When Phase 0.5 or Phase 4 detects page overflow, apply this **ordered** heuristic. Stop as soon as the page limit is met. Each step is fully constrained by the edit whitelist (no theorem changes, no bib changes, no framework changes):

1. **Compress conclusion** (typically 1-2 paragraphs of "future work" can be cut to 2-3 sentences each). Save: 0.3-0.7 pages.
2. **Tighten abstract / intro hedging** (cut "in this paper, we" → "we"; cut "it is well known that" → straight to point). Save: 0.2-0.4 pages.
3. **Move marginal figures to appendix** (figures whose information is not load-bearing for the main argument). Save: 0.5-1 page per figure.
4. **Move proof sketches / extended remarks to appendix** (keep theorem statements + 1-line proof intuition in main; full proof goes to appendix). Save: 0.5-2 pages.
5. **Compress related-work prose** (cite-by-citation comparisons → comparison table). Save: 0.3-0.5 pages.

**Forbidden** under this heuristic: removing experiments, removing theorems from main, removing citations (bib frozen). If after step 5 the paper still overflows, emit `RESUBmit_REPORT.json` with `verdict: BLOCKED, reason_code: page_shrink_failed_under_constraints` and surface to user — they must decide whether to relax a constraint or pick a different target venue.

## Convergence Criteria (Phase 2 stop condition)

Phase 2's per-round loop terminates when **all three** hold:

1. **No new CRITICAL or MAJOR text-fixable findings** in the round's reviewer output (compared to the running running-deduped weakness list).
2. **Page budget passes** — `/paper-compile` reports page count ≤ venue limit.
3. **All audits non-blocking** — `/proof-checker`, `/paper-claim-audit`, `/citation-audit --soft-only` all return `verdict ∈ {PASS, NOT_APPLICABLE}` (not `WARN/FAIL/BLOCKED/ERROR`).

If after `ROUNDS` (default 2) any of (1)/(2)/(3) is still failing, emit a checkpoint to the user asking whether to continue with an extra round (not auto-extend). The user explicitly approving an extra round overrides the default-2 cap.

This pattern is borrowed from `/rebuttal` Phase 7's "terminate when no new substantive issues" — the same shape works for resubmit.

## Master `RESUBMIT_REPORT.md` Ledger

Every resubmit run writes one master report at `$NEW_VENUE_DIR/RESUBMIT_REPORT.{md,json}` collecting:

- Source dir, target venue, target style files used, run start / end timestamps
- Pointers to all artifacts: `BASELINE.md`, `PROOF_AUDIT.json`, `PAPER_CLAIM_AUDIT.json`, `CITATION_AUDIT.json`, `KNOWN_WEAKNESSES.md`, `PAPER_IMPROVEMENT_LOG.md`, `KILL_ARGUMENT.json`, `COMPILE_REPORT.json`, `DIFF_REPORT.md`
- SHA256 hashes of every input file consumed (for `verify_paper_audits.sh` compatibility)
- All thread IDs (Phase 1 audits + Phase 2 reviewer rounds + Phase 3 kill-argument's two threads)
- `audit_skill: resubmit-pipeline`, `verdict ∈ {PASS, WARN, FAIL, NOT_APPLICABLE, BLOCKED, ERROR}`, `reason_code: <one of the listed codes>`
- Decision log: every user checkpoint approval / rejection / escalation, with timestamp
- "Skipped constraints": if any user override (e.g., `— skip-anonymity-scan`, `— rounds 3`) was passed, recorded with rationale

The schema follows `shared-references/assurance-contract.md` (the same schema all mandatory audits use). This makes resubmit-pipeline runs forensically reproducible.

## Failure Modes

The skill emits one of 7 verdicts (the 6 from the assurance contract + a `USER_DECISION` runtime state for in-flight checkpoint pauses):

| Verdict | reason_code | Trigger | Recovery |
|---|---|---|---|
| `PASS` | `clean_resubmit` | All gates passed; final PDF compiled at venue limit | Submit |
| `WARN` | `partially_addressed_concerns` | All MUST-FIX gates passed but some `KNOWN_WEAKNESSES` remain unaddressable | User reviews unaddressed list; submits with awareness |
| `FAIL` | `kill_argument_unresolved_critical` | Phase 3 surfaces a `still_unresolved` critical finding that cannot be fixed under text-only constraints | User decides: relax constraints, escalate to framework change, or pick different venue |
| `NOT_APPLICABLE` | `not_a_resubmit` | The skill detects no prior reviews in `--review-corpus` or the directory looks like a fresh draft | User uses `/paper-writing` instead |
| `USER_DECISION` | `awaiting_phase_<N>_checkpoint` | Skill paused at a Phase 0.5 anonymity-fix checkpoint, Phase 2 round-end diff gate, Phase 3 escalation queue, or Phase 4 page-shrink approval | User responds to the checkpoint prompt; skill resumes with the user's decision recorded in the master ledger |
| `BLOCKED` | `phase_0_setup_blocked` | New venue dir already exists, or template files not found | User resolves the conflict; rerun |
| `BLOCKED` | `phase_0_5_compile_failed` | Initial compile fails on new venue's style | User fixes compile error before audits run |
| `BLOCKED` | `anonymity_scan_failed` | Phase 0.5 hits surface-identifier or self-citation patterns the user must approve | User approves fixes or passes `— skip-anonymity-scan` (only for non-double-blind) |
| `BLOCKED` | `missing_review_corpus` | `--review-corpus` not provided AND not detected | User provides the prior reviews |
| `BLOCKED` | `page_shrink_failed_under_constraints` | Page-shrink heuristic exhausted, paper still overflows | User relaxes a constraint or picks a different venue |
| `BLOCKED` | `out_of_scope_microedit` | `KNOWN_WEAKNESSES` analysis shows ≥1 critical concern requires new experiments / new theorems / framework change | User decides whether to escalate (drop resubmit-pipeline; use full Workflow 1.5 + 3) |
| `ERROR` | `audit_failure` / `loop_failure` | Any sub-skill emits `ERROR` | Examine sub-skill's report; fix + retry |

`BLOCKED` is recoverable; `ERROR` indicates an unexpected sub-skill failure; only `FAIL` and unrecoverable `BLOCKED` block submission.

## Key Rules

- **Never overwrite prior submission directories.** This is the single hardest invariant. The skill aborts at Phase 0 if the target dir already exists.
- **Bib is frozen.** All citation-audit findings flow through `--soft-only` and emerge as text-rewrite proposals, not bib edits.
- **Edit whitelist is binding.** Every Phase 2 round respects the whitelist; rejections logged to `PAPER_IMPROVEMENT_LOG.md`; the user sees a per-round summary at the round checkpoint.
- **Per-round diff gate is mandatory.** Multi-round drift is the highest-risk failure mode for resubmit (a small softening at round 1 + another small softening at round 2 can compound into a meaningful framing change). The orchestrator MUST inspect each round's diff before next round.
- **Convergence criteria are fixed.** Default is 2 rounds; a 3rd round requires explicit user approval at the round-2 checkpoint. The loop does not auto-extend.
- **Anonymity scan is 5-layer.** Surface identifiers, self-citation phrasing, acknowledgments, cross-rebuttal references, internal codenames — not just `grep author surnames`.
- **Phase 3 (kill-argument) is residual-risk reporting, not auto-rewrite.** Adjudicator's `still_unresolved` critical points may need user escalation, not blind extra-round triggering.
- **Overleaf push defers to `/overleaf-sync`.** Don't invent a parallel mechanism.
- **Master `RESUBMIT_REPORT.md` ledger is mandatory** at `assurance: submission`.

## Output Contract

- `<NEW_VENUE_DIR>/main.tex` + `sec/` + `main.pdf` — the new submission, compiled
- `<NEW_VENUE_DIR>/RESUBMIT_REPORT.md` + `RESUBMIT_REPORT.json` — master ledger (mandatory)
- `<NEW_VENUE_DIR>/BASELINE.md` — Phase 0.5 health snapshot
- `<NEW_VENUE_DIR>/KNOWN_WEAKNESSES.md` — atomized prior reviewer concerns with stable IDs
- `<NEW_VENUE_DIR>/PROOF_AUDIT.json` + `.md` — Phase 1 proof audit
- `<NEW_VENUE_DIR>/PAPER_CLAIM_AUDIT.json` + `.md` — Phase 1 claim audit
- `<NEW_VENUE_DIR>/CITATION_AUDIT.json` + `.md` — Phase 1 citation audit (--soft-only mode)
- `<NEW_VENUE_DIR>/PAPER_IMPROVEMENT_LOG.md` — per-round Phase 2 trace
- `<NEW_VENUE_DIR>/KILL_ARGUMENT.json` + `.md` — Phase 3 adversarial gate
- `<NEW_VENUE_DIR>/COMPILE_REPORT.json` — Phase 4 compile + page-limit check
- `<NEW_VENUE_DIR>/DIFF_REPORT.md` — full diff vs base venue body
- `<NEW_VENUE_DIR>/.aris/edit_whitelist.yaml` — Phase 0-generated whitelist
- `<NEW_VENUE_DIR>/.aris/round-N-diff.txt` — per-round diff for the gate
- `<NEW_VENUE_DIR>/.aris/traces/<phase>/<date>_runNN/` — Codex traces per phase

The new venue dir is **the** deliverable; the prior venue dir is untouched.

## Review Tracing

Every Codex MCP reviewer call across all phases saves traces per `shared-references/review-tracing.md` to `<NEW_VENUE_DIR>/.aris/traces/<phase-name>/<date>_run<NN>/`. Both threads of `/kill-argument` are preserved separately. The master `RESUBMIT_REPORT.json` `trace_path` field points to the top-level traces directory.

## Notes

- This skill orchestrates several existing skills (proof-checker, paper-claim-audit, citation-audit, auto-paper-improvement-loop, kill-argument, paper-compile, overleaf-sync) plus uses two recently-added parameters (`/auto-paper-improvement-loop --edit-whitelist`, `/citation-audit --soft-only`). Make sure those parameters resolve to the current SKILL.md versions before relying on the resubmit pipeline.
- The 5-layer anonymity scan is intentionally more thorough than `/paper-compile`'s generic self-citation warning, because resubmit-mode often inherits camera-ready text from a non-double-blind venue going to a double-blind venue.
- Page-shrink heuristic is ordered (compress conclusion → tighten hedging → move marginal figures → move proof sketches → compress related-work prose). The order is calibrated to "least risky to most risky" — compressing conclusion is mostly editorial; moving proof sketches changes the reading flow. Stop as early as page limit is met.
- `RESUBMIT_REPORT.json` schema follows `shared-references/assurance-contract.md` exactly. This makes resubmit runs forensically reproducible. **Note**: `tools/verify_paper_audits.sh` does not currently include `RESUBMIT_REPORT.json` in its `MANDATORY_AUDITS` list (the verifier checks proof / paper-claim / citation / kill-argument). The 4 mandatory audit files consumed by resubmit (which DO live in `<NEW_VENUE_DIR>/`) are recognized by the verifier as usual; `RESUBMIT_REPORT.json` is the orchestrator's own ledger and is not yet a verifier mandatory artifact. Adding it to the verifier is a separate follow-up if the user wants resubmit to be a submission gate via the verifier.
