---
name: integrity-forensics
description: "Run the Anti-Autoresearch integrity-forensics DETERMINISTIC slice (numeric core + rules-only adjudicator) against a paper via a SHA-pinned thin launcher, then convert the verdict into a typed policy gate (BLOCK/WARN/NO_NEW_BLOCKER) and an append-only obligations ledger. Codex-native limitation: upstream ships no Codex-native auditor pack, so the full nine-dimension semantic sweep requires a Claude Code session — this pack runs the honestly-scoped deterministic-only mode (it can flag, it can never say CLEAN). Use when user says \"integrity forensics\", \"forensic audit this paper\", \"投稿前自查诚信\"."
argument-hint: "[paper-dir | pdf | arxiv-id]"
---

# Integrity Forensics — thin launcher (Codex-native: deterministic slice)

Audit target: **$ARGUMENTS**

> Same launcher doctrine as the mainline skill: SHA-pin, upstream eval-gate
> validation per pin, delegate unchanged, no vendoring, no forking, **no
> reviewer knobs**. The one Codex-native difference: upstream's nine auditor
> skills are Claude-Code contracts, so this pack runs upstream's
> **deterministic-only mode** — the numeric forensic core (GRIM / GRIMMER /
> statcheck / delta arithmetic) plus the rules-only adjudicator with an
> all-`review_unavailable` coverage map. That mode is honestly scoped by
> upstream: it can raise HARD/SOFT flags; it can NEVER return
> `CLEAN_GIVEN_EVIDENCE`. Translating upstream's reviewer calls into
> `spawn_agent` would REWRITE an upstream contract — forbidden.

## Constants

- **ANTI_AR_REPO = `https://github.com/wanshuiyin/Anti-Autoresearch.git`**
- **ANTI_AR_COMMIT = `d8f510c49c29ccb5f98ecb1f8e397a7a27eb97c4`** — never
  tracks HEAD; bumping is a reviewed change (mainline Pin-bump checklist).
- **CLONE_DIR = `~/.claude/anti-autoresearch`**
- **NO REVIEWER KNOBS** — and no `— effort:` mapping onto upstream settings.

## Step 0 — Bootstrap the pin (identical to mainline)

```bash
CLONE_DIR="$HOME/.claude/anti-autoresearch"
ANTI_AR_COMMIT="d8f510c49c29ccb5f98ecb1f8e397a7a27eb97c4"
if [ ! -d "$CLONE_DIR/.git" ]; then
    git clone --no-checkout https://github.com/wanshuiyin/Anti-Autoresearch.git "$CLONE_DIR"
fi
git -C "$CLONE_DIR" cat-file -e "$ANTI_AR_COMMIT^{commit}" 2>/dev/null \
    || git -C "$CLONE_DIR" fetch -q origin
git -C "$CLONE_DIR" checkout -qf "$ANTI_AR_COMMIT" || { echo "FATAL: cannot checkout pin"; exit 1; }
# pristine tree at the pin — local tampering (incl. nested-repo injections;
# hence double -f) must not run under the pin's name; verify, don't assume
git -C "$CLONE_DIR" reset --hard -q "$ANTI_AR_COMMIT" || { echo "FATAL: reset failed"; exit 1; }
git -C "$CLONE_DIR" clean -ffdxq || { echo "FATAL: clean failed"; exit 1; }
[ -z "$(git -C "$CLONE_DIR" status --porcelain)" ] || { echo "FATAL: tree not pristine"; exit 1; }
# marker OUTSIDE the clone (a marker inside a tamperable tree proves nothing)
MARKER="${CLONE_DIR}.aris_eval_ok_${ANTI_AR_COMMIT}"
if [ ! -f "$MARKER" ]; then
    ( cd "$CLONE_DIR" && python3 eval/run_eval.py ) || {
        echo "FATAL: upstream eval gate FAILED at pin — refusing an unvalidated pin"; exit 1; }
    touch "$MARKER"
fi
```

## Step 1 — Delegate: upstream deterministic-only mode, unchanged

Open **`$CLONE_DIR/workflows/anti-autoresearch/SKILL.md`** and follow its
**deterministic-only** path (its own documented degraded mode): Step 0 ingest →
Step 1 evidence ledger → deterministic auditors → adjudication with the
generated all-`review_unavailable` coverage map. Wrapper rules: run every
upstream bash block with `cd "$CLONE_DIR"` (upstream self-locates via
`git rev-parse --show-toplevel`); refer to the paper by ABSOLUTE path; never
rewrite upstream outputs.

Expected outcome: `report.json` whose verdict is `HARD_FLAGS` / `SOFT_FLAGS` /
`REVIEW_UNAVAILABLE` — by construction never `CLEAN_GIVEN_EVIDENCE`.

## Step 2 — Typed gate + obligations

Resolve `forensics_gate.py` via the canonical helper chain
(`shared-references/integration-contract.md` §2, Policy A), then:

```bash
python3 "$GATE_HELPER" evaluate --report "$PAPER_DIR/report.json" --paper-dir "$PAPER_DIR" \
    --anti-ar-commit "$ANTI_AR_COMMIT" --executor-model "codex-gpt-5.6-sol"
```

Policy: `HARD_FLAGS` → **BLOCK** · `REVIEW_UNAVAILABLE` → **BLOCK** (which a
deterministic-only run reports whenever it found no flags — the semantic
dimensions never ran, so nothing may wave the paper through) · `SOFT_FLAGS` →
**WARN**. The gate records `same-family` proposal provenance for a Codex
executor — informational: this gate only raises flags, it grants nothing.
The downstream preflight is ONE command:
`python3 "$GATE_HELPER" fresh --paper-dir "$PAPER_DIR" --anti-ar-commit "$ANTI_AR_COMMIT"`
— exit 0 ⟺ produced at the current pin ∧ gate
exists ∧ paper unchanged since ∧ gate matches the current ledger ∧ decision
pass-capable (WARN/NO_NEW_BLOCKER), where the decision is RE-computed from
the sha-verified archived report + live ledger (the stored token is display,
not authority). Any ledger mutation deletes the standing gate.json, and
`evaluate` refuses a report older than any paper file — neither a stale pass
nor a stale report can be replayed.

## Step 3 — Fix what it found

Identical obligations discipline to the mainline skill: append-only ledger,
`UNRESOLVED_DISAPPEARANCE` on vanished-but-unresolved findings, typed + hashed
`resolve` receipts (`corrected-from-results | claim-narrowed | claim-withdrawn |
citation-replaced`; `--verified-by` must be typed provenance —
`human:<name>` / `checker:<tool>` / `cross-family-review:<thread-id>` — and
the evidence file is RE-hashed on every later gate), human-only `waive`
(never a resolution), and **The One Forbidden Loop**: never "edit → re-sweep
→ repeat until it stops flagging".
Numeric obligations route to the result files; the rest to the matching audit
skill or the human.
