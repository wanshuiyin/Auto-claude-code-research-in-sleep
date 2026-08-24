---
name: integrity-forensics
description: "Run the Anti-Autoresearch integrity-forensics sweep (span-anchored evidence ledger → GPT auditors propose findings → a rules-only reporter that lists every proposal with what the auditor said about it) against a paper via a SHA-pinned thin launcher — then convert the verdict into a typed policy gate (BLOCK/WARN/NO_NEW_BLOCKER) and an append-only obligations ledger. Use when user says \"integrity forensics\", \"forensic audit this paper\", \"投稿前自查诚信\", \"审这篇论文的诚信\", or says \"anti-autoresearch\" when the upstream repo's own skills are not installed. Also invoked by /paper-writing (submission self-forensics, default ON), /peer-review (forensic appendix), /resubmit-pipeline."
argument-hint: "[paper-dir | pdf | arxiv-id]"
allowed-tools: Bash(*), Read, Write, Grep, Glob, mcp__codex__codex
---

# Integrity Forensics — thin launcher for Anti-Autoresearch

Audit target: **$ARGUMENTS**

> **What this is.** ARIS generates papers; [Anti-Autoresearch](https://github.com/wanshuiyin/Anti-Autoresearch)
> is its outward-pointed dual — reviewer-side integrity forensics (46 patterns
> across 8 families, deterministic GRIM/GRIMMER/statcheck core, span-anchored
> claims, a rules-only reporter that summarizes rather than adjudicates). This skill is a
> **thin launcher**: it pins an upstream commit, validates the pin with the
> upstream eval gate, delegates execution unchanged, and post-processes the
> verdict into ARIS's policy vocabulary. It vendors nothing and forks nothing.

> 🔁 **Cadence fence** (`shared-references/external-cadence.md`): this skill is
> verdict-bearing decision support. Do not wrap it in `/loop` / `/schedule` —
> and NEVER as "iterate edits until it stops flagging" (see The One Forbidden
> Loop below).

## Constants

- **ANTI_AR_REPO = `https://github.com/wanshuiyin/Anti-Autoresearch.git`**
- **ANTI_AR_COMMIT = `b47af6f983b38347b6d2110379e266400597cf66`** — the SHA-pin.
  The launcher NEVER tracks upstream HEAD; bumping this constant is a reviewed
  change (see Pin-bump checklist).
- **CLONE_DIR = `~/.aris/anti-autoresearch`** — the pinned working copy. Host-neutral
  on purpose: ARIS also runs on DeepSeek Harness, Codex CLI, Cursor, Trae,
  Antigravity and Copilot CLI, where `~/.claude/` would name an installation the
  user does not have. An older clone at `~/.claude/anti-autoresearch` is unused;
  move it and its `.aris_eval_ok_*` receipt only to keep an offline
  deterministic-only run working, otherwise delete it whenever convenient.
- **NO REVIEWER KNOBS.** This launcher exposes no reviewer model/effort
  parameters and never maps ARIS `— effort:` onto upstream settings. The
  pinned upstream runs exactly what it pins (`gpt-5.6-sol` + `xhigh`, its own
  design decision). Overriding upstream review policy from a launcher would
  create a second, unauditable configuration surface.
- **GATE_HELPER = `forensics_gate.py`** — resolved via the canonical chain
  (`shared-references/integration-contract.md` §2): `.aris/tools/` →
  `tools/` → `$ARIS_REPO/tools/` → `$ARIS_REPO/tools/` via `~/.aris/repo`.
  Failure policy A (required): if it cannot be resolved at
  `assurance: submission`, STOP — never improvise the gate.

## Step 0 — Bootstrap the pin (idempotent)

```bash
CLONE_DIR="$HOME/.aris/anti-autoresearch"
ANTI_AR_COMMIT="b47af6f983b38347b6d2110379e266400597cf66"

mkdir -p "$HOME/.aris"
if [ ! -d "$CLONE_DIR/.git" ]; then
    git clone --no-checkout https://github.com/wanshuiyin/Anti-Autoresearch.git "$CLONE_DIR"
fi
# fetch ONLY if the pin isn't already present — a cached, validated pin works offline
git -C "$CLONE_DIR" cat-file -e "$ANTI_AR_COMMIT^{commit}" 2>/dev/null \
    || git -C "$CLONE_DIR" fetch -q origin
git -C "$CLONE_DIR" checkout -qf "$ANTI_AR_COMMIT" || {
    echo "FATAL: cannot checkout pinned commit $ANTI_AR_COMMIT"; exit 1; }
# Force a PRISTINE tree at the pin — local tampering with the clone (edited
# adjudicator, injected module, even one hidden inside a NESTED git repo,
# which single-f clean skips) must not survive bootstrap and run under the
# official pin's name. Every step is checked; then the tree is verified.
git -C "$CLONE_DIR" reset --hard -q "$ANTI_AR_COMMIT" || {
    echo "FATAL: reset to pin failed"; exit 1; }
git -C "$CLONE_DIR" clean -ffdxq || {
    echo "FATAL: clean failed"; exit 1; }
[ -z "$(git -C "$CLONE_DIR" status --porcelain)" ] || {
    echo "FATAL: clone is not pristine after reset+clean — refusing to run"; exit 1; }

# One-time-per-pin validation: the upstream eval gate (8 injected-defect
# classes, 100% recall + zero clean false positives) must PASS before this
# pin is allowed to produce a verdict. NEVER skip; NEVER proceed on failure.
# The marker lives OUTSIDE the clone: a marker inside a tamperable tree proves
# nothing (and `git clean` above would erase it, forcing re-eval every run).
MARKER="${CLONE_DIR}.aris_eval_ok_${ANTI_AR_COMMIT}"
if [ ! -f "$MARKER" ]; then
    ( cd "$CLONE_DIR" && python3 eval/run_eval.py ) || {
        echo "FATAL: upstream eval gate FAILED at pin $ANTI_AR_COMMIT — refusing to"
        echo "       use an unvalidated forensics pin for verdicts."; exit 1; }
    touch "$MARKER"
fi
echo "anti-autoresearch pinned at $ANTI_AR_COMMIT (eval gate: validated)"
```

## Step 1 — Delegate: run the upstream sweep, unchanged

Open and follow **`$CLONE_DIR/workflows/anti-autoresearch/SKILL.md`** end to
end on the target. Two wrapper rules — the ONLY things this launcher adds:

1. **cwd.** Upstream skills self-locate via `git rev-parse --show-toplevel`.
   Run every upstream bash block with `cd "$CLONE_DIR"` first — ALWAYS the cd,
   never just an exported `ROOT` (upstream blocks re-derive ROOT themselves
   and would overwrite it) — and refer to the paper by **absolute path**,
   otherwise upstream resolves ROOT to the ARIS repo and finds the wrong
   Python spine.
2. **Codex calls carry `approval-policy: never` + `sandbox: read-only`**
   (session hygiene; upstream already specifies fresh-thread-per-dimension,
   serial execution, and its own model pins — do not alter them).

Everything else — the evidence ledger, coverage.json state machine, the nine
auditor dimensions, the refutation pass, the deterministic summary — is
upstream's contract. **Never rewrite, soften, or re-map its outputs**
(`report.json` + `REPORT.md`, verdict ∈ CLEAN_GIVEN_EVIDENCE / SOFT_FLAGS /
HARD_FLAGS / REVIEW_UNAVAILABLE). The observability level (L0/L1/L2) is
whatever upstream derives from the artifacts present — do not promise L2.

## Step 2 — Typed gate + obligations (ARIS-side post-processing)

```bash
# Resolve $GATE_HELPER via the canonical chain (integration-contract §2), then
# ONE atomic call (update + gate in a single locked transaction — the gate only
# ever speaks for the report the ledger has folded, sha-bound):
python3 "$GATE_HELPER" evaluate --report "$PAPER_DIR/report.json" --paper-dir "$PAPER_DIR" \
    --anti-ar-commit "$ANTI_AR_COMMIT" --executor-model "<this pipeline's executor>"
# exit 0 = WARN / NO_NEW_BLOCKER · exit 1 = BLOCK
```

The gate translates the verdict into policy WITHOUT re-labeling it:

| upstream verdict | policy |
|---|---|
| `HARD_FLAGS` | **BLOCK** — an auditor proposed something critical and it is on the table for you to read; never "the machine found fraud" |
| `REVIEW_UNAVAILABLE` | **BLOCK** — an incomplete sweep cannot wave a paper through |
| `SOFT_FLAGS` | **WARN** — human disposition. Read the never-ran list too: the upstream verdict folds incompleteness in only when it would otherwise be clean, so a WARN can sit on top of a sweep where verdict-bearing dimensions never ran. `evaluate` and `fresh` both print those dimensions |
| `CLEAN_GIVEN_EVIDENCE` | **NO_NEW_BLOCKER** — *never* called PASS or accepted: it means "no flag found in the evidence at hand", not an acquittal |
| anything else | **BLOCK** (fail closed) |

plus: any OPEN critical obligation → BLOCK; any OPEN obligation → at least
WARN; a closed-without-receipt or unknown-status ledger entry → BLOCK (a
hand-edited `"status": "RESOLVED"` does not open the gate).

`gate.json` also records a `paper_fingerprint` (sha over the paper's compile
inputs AND deliverables — `.tex`/`.bib`/`.sty`/`.cls`/figures/PDF). The
downstream preflight is ONE command:
`python3 "$GATE_HELPER" fresh --paper-dir "$PAPER_DIR" --anti-ar-commit "$ANTI_AR_COMMIT"`
— exit 0 ⟺ the gate was produced at the CURRENT pin ∧ a gate
exists ∧ nothing in the paper changed after it ∧ the gate matches the current
obligations ledger ∧ the decision — **re-computed from the sha-verified
archived report (`last_report.json`) + the live ledger, never read from the
gate's stored token** — is pass-capable (`WARN` / `NO_NEW_BLOCKER`). Anything
else — missing gate, post-gate edit or recompile, unbound ledger or archive,
recompute mismatch, `BLOCK`, unknown token — exits 1: re-run the sweep +
`evaluate`. Every ledger mutation (`update`/`resolve`/`waive`) deletes the
standing `gate.json`, so an interrupted run can never leave a stale pass; and
`evaluate` refuses a report OLDER than any paper file (a stale report cannot
be folded onto text it never audited). Run `evaluate` immediately after the
sweep, before touching any paper file.

The gate artifact also records honest provenance: upstream's auditors are
GPT-family, so for a **Claude executor** the findings carry `cross-family`
proposal provenance; for a **Codex executor** they are `same-family`. Either
way this gate only raises flags — it has no acceptance to grant, so the
distinction is informational, not a loophole.

## Step 3 — Fix what it found (obligations, not a polish loop)

Every OPEN obligation gets DISPOSITIONED — fixed, or explicitly waived. Upstream now
reports every proposal an auditor made rather than deciding which ones do not count, so
expect more obligations than a pre-2026-08 sweep opened, and expect some of them to be
proposals you disagree with. **`waive` is a first-class, expected outcome** — "a model
proposed this and I, the human, judge it wrong" is a normal disposition here, not a last
resort. Weigh each one against the report's columns: `Anchored`, `Observability`,
`FP-risk`, `Surface`, `Ext-check`.

For the ones that are real, use the right door:

| Finding family | Repair route |
|---|---|
| A — numeric self-consistency | recompute from the RESULT FILES (`/paper-claim-audit` evidence chain); fix the number, not the sentence |
| D — experiment integrity | back to `/experiment-audit` / rerun |
| E — citations | `/citation-audit` KEEP/FIX/REPLACE machinery |
| G — proof & derivation | `/proof-checker`'s fix loop |
| B / C / H — scope, baselines, eval design | science-level: feed the finding to `/auto-review-loop` as reviewer INPUT, or to the human |
| AIS / advisory (zero-weight) | optional context for `/auto-paper-improvement-loop`; never gates |

Close each obligation explicitly — the receipt is typed and hashed:

```bash
python3 "$GATE_HELPER" resolve --paper-dir "$PAPER_DIR" --obligation-id <id> \
    --fix-type corrected-from-results|claim-narrowed|claim-withdrawn|citation-replaced \
    --evidence <path-to-the-ground-truth-that-backs-the-fix> \
    --verified-by "human:<name>" | "checker:<tool>" | "cross-family-review:<thread-id>"
# or, with HUMAN sign-off only:
python3 "$GATE_HELPER" waive --paper-dir "$PAPER_DIR" --obligation-id <id> \
    --approver "human:<name>" --reason "<why this stands as-is>"
```

Rules the ledger enforces mechanically (`tests/test_forensics_gate.py`):
- **append-only** — re-running the sweep can open obligations, never close them;
- a finding that *disappears* from a later report stays OPEN and gains
  `UNRESOLVED_DISAPPEARANCE` — rewording the span is not a fix;
- `claim-withdrawn` is an honest fix (deleting an unsupported claim is a
  legitimate resolution — with the deletion diff as evidence);
- a **waiver is not a resolution**: human-approved, permanently recorded,
  original finding snapshot immutable;
- the executor's `fix_type` label is a receipt, not a verdict — closure of a
  critical needs a family checker, a fresh cross-family review, or a human
  (`--verified-by` requires TYPED provenance and is recorded; naming a human
  who did not approve is a false record with a permanent paper trail);
- receipts are **re-verified, not remembered**: on every later gate the
  evidence file must still exist and still hash to what was recorded at
  closure time — editing the evidence after closing re-opens the BLOCK;
- `resolve`/`waive` (like `update`) **invalidate the standing `gate.json`** —
  finish Step 3 by re-running the sweep + `evaluate`, so the gate that
  downstream preflights read reflects the post-fix state.

### The One Forbidden Loop

**Never run "edit → re-sweep → repeat until CLEAN".** That objective function
teaches the editor to defeat the detector — deleting an anchored span kills a
flag faster than fixing the number, and the result is a paper laundered
against its own audit. The re-run after fixes exists to confirm the
DISCREPANCY is gone (and to catch new ones); the obligations ledger — not the
verdict — decides whether the gate opens.

## Trust boundary (what is computed vs what is protocol)

- **Computed** (the gate enforces these mechanically): verdict→policy mapping,
  append-only ledger lifecycle, sha bindings (report ↔ ledger ↔ archive),
  receipt re-hashing, the paper fingerprint, pin/version match, and the
  recomputed decision (`fresh` never trusts a stored token).
- **Protocol** (instruction-graded, deliberately): that the sweep actually ran
  at the pinned clone against this paper. The gate raises the bar —
  structural floor (a report must name its adjudicator and carry a coverage
  map), stale-report mtime guard — and that is where it stops. There is no
  cryptographic binding between the report and the paper, deliberately: this is
  a research-workflow gate, not a provenance system, and the honest statement is
  that a determined executor can hand it a stale report. Likewise `human:` / `checker:` / `cross-family-review:` labels are
  accountability, not authentication: a false label is an explicit,
  permanent false record.
- **Out of scope**: a party rewriting the `.aris/` artifacts consistently with
  shell access has owner power (they could delete the directory outright).
  The gate defends against the sloppy or corner-cutting executor and against
  honest crashes/races/resumes — not against the machine's owner.

## Pin-bump checklist (maintainers)

1. Set the new `ANTI_AR_COMMIT`; delete no markers (the eval gate re-runs
   automatically for the new SHA).
2. Diff upstream's `schemas/report.schema.json` + verdict vocabulary against
   the gate's policy table; extend `tools/forensics_gate.py` BEFORE bumping if
   they moved.
3. Old findings/obligations stay valid (fingerprints are span/hash-based, not
   id-based) — but findings produced by an older adjudicator must be
   **re-audited, not re-adjudicated** (upstream's own migration rule).
4. Tell users when a bump changes how much they must disposition. `fresh`
   rejects every stored `gate.json` at the old pin with `PIN_MISMATCH`, so a
   bump already forces a re-sweep for everyone — bundle upstream changes behind
   ONE bump rather than two, or the re-sweep cost is paid twice.

> **2026-08 bump (`98a75fc`) — expect more open obligations.** Upstream moved
> from adjudicating proposals to reporting them: findings its FP-risk,
> observability, surface and needs-external-check gates used to demote to `info`
> now arrive above info, so they open obligations. Nothing got worse in the
> paper; more of what the auditors said is now visible. Waiving a proposal you
> judge wrong is the expected disposition, and the report's per-finding columns
> (`Anchored`, `Observability`, `FP-risk`, `Surface`, `Ext-check`) are what you
> weigh. Upstream also deleted its report self-binding hashes in the same window
> — nothing here ever consumed them.

## Codex-native note (mirror)

Upstream ships no Codex-native pack; its auditor skills are Claude-Code
contracts. A Codex-native session may run upstream's **deterministic-only
mode** (numeric core + adjudicator with an all-`review_unavailable` coverage
map — honestly scoped: it can flag, it can never say CLEAN). The full
nine-dimension sweep requires a host that can execute upstream's Claude-Code
contracts unchanged — Claude Code and the `dsh-aris` bundle on DeepSeek Harness
are the known ones. Translating upstream's
reviewer calls into `spawn_agent` on the fly is REWRITING an upstream
contract — forbidden.

## Review tracing

Upstream saves its own per-dimension traces under the paper's
`.aris/traces/`. The launcher adds only the `.aris/forensics/` artifacts:
`gate.json` (pins `anti_ar_commit` + report/ledger hashes + the paper-text
fingerprint), `obligations.json` (the append-only ledger), and
`last_report.json` (the sha-verified archive of the folded report that
`fresh` recomputes from).
