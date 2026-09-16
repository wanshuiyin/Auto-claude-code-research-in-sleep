# ARIS Agent Guide

> **For AI agents reading this repo cold.** If you are a human, see [README.md](README.md) or [docs/ARIS_INTRO.html](https://wanshuiyin.github.io/Auto-claude-code-research-in-sleep/ARIS_INTRO.html).

ARIS is a research harness: composable Markdown skills that orchestrate the ML research lifecycle through cross-model adversarial collaboration. Executor (Claude / Codex / Cursor / Antigravity / Copilot CLI) writes code & papers; reviewer (GPT-6-Astra via Codex MCP, Claude / Gemini via `claude-review` / `gemini-review` MCP, or Copilot's evidence-gated native complementary reviewer for `/auto-review-loop`) critiques independently.

> **Source of Truth.** This file is a *routing index*, not a specification.
> Behavior of a skill lives in `skills/<name>/SKILL.md`. System-wide
> contracts live in `skills/shared-references/*.md`. If this guide
> conflicts with a SKILL.md, the **SKILL.md wins**.

## Skill Locations & Platforms

| Platform | Skill root | Notes |
|----------|-----------|-------|
| Claude Code / Cursor / Trae / Antigravity / Copilot CLI | `skills/<name>/SKILL.md` | Mainline skills; native `SKILL.md` invocation |
| Codex CLI | `skills/skills-codex/<name>/SKILL.md` | Codex mirror; uses `spawn_agent` instead of `mcp__codex__codex` |
| Codex + Claude-review | `skills/skills-codex-claude-review/` | Overlay on top of `skills-codex/` |
| Codex + Gemini-review | `skills/skills-codex-gemini-review/` | Same pattern, Gemini reviewer |
| DeepSeek Harness | `dsh plugin --profile web add dsh-aris` | One plugin, mainline skills unchanged; see the [`dsh-aris` branch](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/dsh-aris#readme) |

Codex base review is a fresh same-family `spawn_agent` review. It may drive and
complete workflows but records `review_independence: same-family` and
`acceptance_status: provisional`. Claude/Gemini overlays or deterministic
verifiers may record accepted; never describe base Codex self-review as
cross-model acceptance.

**Full catalog**: [`docs/SKILLS_CATALOG.md`](docs/SKILLS_CATALOG.md) — **83 skills**, grouped by role.

Invocation syntax is identical across hosts:
```
/skill-name "arguments" — key: value, key2: value2
```

**The `codex` MCP server is ARIS's own.** codex-cli 0.154.0 removed `codex mcp-server`; `mcp__codex__codex` / `mcp__codex__codex-reply` are served by [`mcp-servers/codex-exec/server.py`](mcp-servers/codex-exec/README.md), a zero-dependency bridge over `codex exec` with the identical tool contract. Registration: `claude mcp add codex -s user -- python3 <aris-repo>/mcp-servers/codex-exec/server.py` (other MCP hosts: same `codex` key, command `python3` + that path). Never register `codex mcp-server`. A `codex-reply` keeps the model, effort, sandbox and cwd its thread was created with — do not re-send them.

## Common Parameters

ARIS has **two independent control axes** plus scoped flags.

### Axis 1 — `effort` (depth / budget)

```
— effort: lite | balanced | max | beast      # default: balanced
```

Controls how many papers / ideas / rounds / pilots. Codex reasoning never drops below the tier floor regardless of effort (regular reviews `xhigh`; the deep-audit skills run `ultra` — see `skills/shared-references/reviewer-routing.md`).

### Axis 2 — `assurance` (audit strictness, independent of effort)

```
— assurance: draft | polished | conference-ready | submission
```

Controls whether mandatory audits gate the final report. `lite` / `balanced` default to `draft`; `max` / `beast` default to `submission`. Override is legal: `--- effort: lite --- assurance: conference-ready` is meaningful. Spec: [`shared-references/assurance-contract.md`](skills/shared-references/assurance-contract.md).

### Other common parameters

```
— human checkpoint: true | false             # pause for approval (default: false)
— AUTO_PROCEED: true | false                 # auto-continue at gates (default: true)
— difficulty: medium | hard | nightmare      # reviewer adversarial level
— venue: ICLR | NeurIPS | ICML | ...         # target venue (no silent default; /research-pipeline binds it at the paper stage)
— sources: web, zotero, deepxiv, exa, ...    # literature sources
— gpu: local | remote | vast | modal         # GPU backend
— reviewer: auto | codex | oracle-pro | manual # reviewer routing; auto is native only for Copilot /auto-review-loop
```

### Scoped flags (skill-specific)

| Flag | Skill | Effect |
|------|-------|--------|
| `--- style-ref <source>` | writer-side skills | Mimic exemplar's structural style WITHOUT copying claims / terms |
| `--- edit-whitelist <path>` | `/auto-paper-improvement-loop` | YAML schema gating which paths / operations the loop may touch |
| `--- soft-only` | `/citation-audit` | Bib frozen — rewrites body instead of editing `.bib` |
| `--review` / `--no-review` | `/render-html` | Toggle cross-model review gate (default: academic=on, dashboard=off) |
| `--author "..."` | `/render-html` | Optional byline rendered between subtitle and meta |
| `--deep-fix` / `--restatement-check` | `/proof-checker` | Patch-grade fix plans / cross-location theorem drift |

Parameters pass through workflow chains automatically.

## Workflow Index

```
Main chain:      /research-pipeline = W1 → W1.5 → W2 → W3
Post-paper:      W4 (rebuttal), W5 (resubmit to new venue), W6 (talk)
```

| ID | Skill | Input | Output | When to invoke |
|----|-------|-------|--------|----------------|
| W1 | `/idea-discovery "direction"` | research direction | `IDEA_REPORT.md`, `EXPERIMENT_PLAN.md`, `FINAL_PROPOSAL.md` | Starting new research |
| W1.5 | `/experiment-bridge` | `EXPERIMENT_PLAN.md` | running code, `EXPERIMENT_LOG.md` | Have a plan, need to implement |
| W2 | `/auto-review-loop "scope"` | paper + results | improved paper + `REVIEW_STATE.json` | Iterative improvement loop |
| W3 | `/paper-writing "NARRATIVE_REPORT.md"` | narrative report | `paper/main.pdf` + LaTeX source | Ready to write |
| W4 | `/rebuttal "paper/ + reviews"` | paper + reviews | `PASTE_READY.txt` + `REBUTTAL_DRAFT_rich.md` | Reviews received |
| W5 | `/resubmit-pipeline "paper/" --- venue: X` | polished paper + new venue | `<NEW_VENUE_DIR>/` + `RESUBMIT_REPORT.json` | Port to another venue under hard constraints |
| W6 | `/paper-talk "paper/" --- venue: X` | paper | Beamer + PPTX + speaker notes + Q&A prep | Conference talk after acceptance |

Hard constraints on W5: no new experiments, no bib edits, no framework changes, never overwrites prior submissions. Enforced via `--edit-whitelist` + `RESUBMIT_REPORT.json` 7-state failure-mode ledger.

## Assurance & Audit Chain

ARIS gates submission via a 5-layer cross-model audit chain. Each layer is invoked by a different skill, all use **fresh codex threads** (never `codex-reply`):

| Layer | Skill | Asks | Verdict file |
|:----:|-------|------|--------------|
| 1 | `/experiment-audit` | "Is the eval code honest? (no fake GT, no self-normalized scores, no phantom results)" | `EXPERIMENT_AUDIT.{md,json}` |
| 2 | `/result-to-claim` | "Does the claim scientifically follow from the result?" | (writes claim status to Research Wiki) |
| 3 | `/paper-claim-audit` | "Does the paper *report* the numbers truthfully?" (zero-context reviewer) | `PAPER_CLAIM_AUDIT.{md,json}` |
| 4 | `/citation-audit` | "Every `\cite{}` valid? Existence + metadata + context-appropriateness?" | `CITATION_AUDIT.{md,json}` |
| 5 | `/kill-argument` | "Strongest 200-word rejection memo + independent adjudicator scoring each attack point" | `KILL_ARGUMENT.{md,json}` |

All five emit verdicts on the 6-state schema per [`shared-references/assurance-contract.md`](skills/shared-references/assurance-contract.md): `PASS | WARN | FAIL | BLOCKED | ERROR | NOT_APPLICABLE`.

At `assurance: submission`, Phase 6 of `/paper-writing` runs `tools/verify_paper_audits.sh` and refuses to emit the Final Report if ANY layer is non-green.

**Executor must NOT judge its own integrity.** Reviewer reads the artifact cold (file paths only, never summaries or interpretations). Trace each reviewer call to `.aris/traces/<skill>/<date>_run<NN>/` per [`shared-references/review-tracing.md`](skills/shared-references/review-tracing.md).

## HTML Rendering (for human reading)

[`/render-html`](skills/render-html/SKILL.md) renders selected MD / JSON artifacts (IDEA_REPORT, AUTO_REVIEW, KILL_ARGUMENT, PAPER_PLAN, research-wiki state) into single-file HTML for human reading. **MD / JSON remains canonical**; HTML is a generated view derived from the user's academic-newspaper style.

```
/render-html <input.md> [--template academic|dashboard]
                        [--out <path>] [--author "..."]
                        [--review | --no-review]
```

- `academic` template (linear long-form with sticky TOC): **review by default** — fresh `mcp__codex__codex` thread audits render fidelity / safety / structure (NOT claim truthfulness; that's owned by `/paper-claim-audit` etc.)
- `dashboard` template (grid cockpit): no review by default; pass `--review` to force
- Outputs: `<file>.html` + `<file>.review.json` sidecar + trace at `.aris/traces/render-html/<date>_run<NN>/`
- Do NOT hand-edit the generated HTML — edit the source, re-render

## Artifact Contracts

Skills communicate through plain-text files in known locations:

| Artifact | Created by | Consumed by |
|----------|-----------|-------------|
| `IDEA_REPORT.md` | `/idea-discovery` | `/experiment-bridge` |
| `refine-logs/FINAL_PROPOSAL.md` | `/research-refine` | `/experiment-plan` |
| `EXPERIMENT_PLAN.md` | `/experiment-plan` | `/experiment-bridge` |
| `EXPERIMENT_LOG.md` | `/experiment-bridge` | `/auto-review-loop`, `/result-to-claim` |
| `NARRATIVE_REPORT.md` | `/auto-review-loop` (or human) | `/paper-writing` |
| `paper/main.tex` | `/paper-write` | `/paper-compile` |
| `paper/main.pdf` | `/paper-compile` | `/auto-paper-improvement-loop` |
| `REVIEW_STATE.json` | `/auto-review-loop` | `/auto-review-loop` (resume after context auto-compact) |
| `EXPERIMENT_AUDIT.{md,json}` | `/experiment-audit` | `/result-to-claim` |
| `PAPER_CLAIM_AUDIT.{md,json}` | `/paper-claim-audit` | `/paper-writing` Phase 5.5 gate |
| `CITATION_AUDIT.{md,json}` | `/citation-audit` | `/paper-writing` Phase 5.8 submission gate |
| `KILL_ARGUMENT.{md,json}` | `/kill-argument` | `/paper-writing` Phase 5.6 + `/resubmit-pipeline` adversarial gate |
| `RESUBMIT_REPORT.json` | `/resubmit-pipeline` | submission-gate verifier (7-state ledger) |
| `GAP_REPORT.md` | `/paper-plan` (when `--- style-ref:` set) | `/paper-write` (emits `<!-- DATA_NEEDED: ... -->` HTML comments for missing slots) |
| `<artifact>.review.json` | `/render-html` review gate | manual triage |
| `.aris/edit_whitelist.yaml` | human / `/resubmit-pipeline` | `/auto-paper-improvement-loop --edit-whitelist` |
| `research-wiki/` | `/research-wiki` | `/idea-creator`, `/research-lit`, `/result-to-claim` |
| `.aris/meta/events.jsonl` | hooks (passive logging) | `/meta-optimize` |
| `.aris/traces/<skill>/<date>_run<NN>/` | reviewer-class skills | audit / forensic replay |

## Helper Resolution (writing new skills)

When a SKILL.md invokes a canonical helper (e.g., `verify_papers.py`, `research_wiki.py`, `save_trace.sh`, `arxiv_fetch.py`, `verify_paper_audits.sh`), **do NOT hardcode** `python3 tools/foo.py`. Resolve via the strict-safe chain documented in [`shared-references/integration-contract.md`](skills/shared-references/integration-contract.md) §2:

```
Layer 0:  ${CLAUDE_SKILL_DIR}/scripts/<helper>     # owner SKILL self-contained (CC 1.0+)
Layer 1:  .aris/tools/<helper>                     # project-local symlink
Layer 2:  tools/<helper>                           # repo-local
Layer 3:  $ARIS_REPO/tools/<helper>                # global fallback
```

Pick a failure policy from `integration-contract.md` §2 per-helper table: A (gate) / B (side-effect) / C (forensic) / D1 (cascade) / D2 (multi-source aggregate) / E (diagnostic). Each has POSIX-sh + `set -e` + `set -u` safe example blocks.

Advisory CI lint at `.github/workflows/lint-skills-helpers.yml` flags hardcoded `python3 tools/foo.py` patterns in PR-modified SKILL.md (warning only, never fails CI). Single-owner helpers (used by exactly one SKILL) live at `skills/<owner>/scripts/<helper>` per Arch C; precedents: `figure-spec`, `paper-illustration-image2`, `experiment-queue`, `render-html`.

## Cross-Model Protocol

- **Executor** (Claude / Codex / Cursor / Antigravity / Copilot): writes code, runs experiments, drafts papers
- **Reviewer** (GPT-6-Astra via Codex MCP, default; or Claude / Gemini via `*-review` MCP overlays): critiques, scores, demands revisions
- **Rule**: executor and reviewer **must** be different model families. Same-family review is a non-feature.
- **Reviewer independence**: pass file paths only, never summaries or interpretations
- **Thread freshness**: audit-class skills open a fresh `mcp__codex__codex` thread per review round — narrative accumulation inflates scores. `/auto-review-loop` is the documented exception: it keeps one thread across rounds via `codex-reply` (its SKILL.md governs)
- **Scope limits in every reviewer prompt**: the [`review-scope-limits.md`](skills/shared-references/review-scope-limits.md) block bounds what a reviewer may *propose* (no hashes, no over-defense, no corner-case obsession, not a security product), never what it looks for
- **Experiment integrity**: executor must NOT judge its own eval code — reviewer audits directly per [`shared-references/experiment-integrity.md`](skills/shared-references/experiment-integrity.md)

The external Codex default is `gpt-6-astra` with two-tier reasoning (deep-audit `ultra` / regular `xhigh`, since 2026-07-10; needs codex-cli ≥ 0.144.1). Capability fallback runs `gpt-5.6-sol` then `gpt-5.5`, both at xhigh; legacy `gpt-5.4` is available as `--- reviewer-model: gpt-5.4`. In a bound Copilot CLI session, `/auto-review-loop` instead defaults to the built-in `rubber-duck` subagent and accepts it only when host events prove the dynamically selected model is from a different family. Oracle Pro tier (`gpt-5.5-pro`) via `--- reviewer: oracle-pro` is a separate routing path.

## Shared References

Read these before invoking review-related or audit-class skills:

| File | When you need it |
|------|------------------|
| [`reviewer-independence.md`](skills/shared-references/reviewer-independence.md) | Any cross-model review |
| [`experiment-integrity.md`](skills/shared-references/experiment-integrity.md) | Writing eval / audit code |
| [`fan-out-pattern.md`](skills/shared-references/fan-out-pattern.md) | Fanning out subagents for breadth (any runtime tier) |
| [`acceptance-gate.md`](skills/shared-references/acceptance-gate.md) | Autonomous loops / goal mode — who may ACCEPT a result |
| [`external-cadence.md`](skills/shared-references/external-cadence.md) | Before wrapping a skill in `/loop`, `/schedule`, or `CronCreate` |
| [`assurance-contract.md`](skills/shared-references/assurance-contract.md) | 6-state verdict schema, audit gating |
| [`integration-contract.md`](skills/shared-references/integration-contract.md) | Helper resolution + failure policies (writing new SKILL.md) |
| [`review-tracing.md`](skills/shared-references/review-tracing.md) | Where to save reviewer traces |
| [`reviewer-routing.md`](skills/shared-references/reviewer-routing.md) | `--- reviewer: oracle-pro` etc., model tiers, capability fallback |
| [`review-scope-limits.md`](skills/shared-references/review-scope-limits.md) | The block every reviewer prompt carries — what a reviewer may propose |
| [`taste-calibration.md`](skills/shared-references/taste-calibration.md) | Grading subjective quality against written, anchored taste |
| [`evidence-precheck.md`](skills/shared-references/evidence-precheck.md) | Reconciling a model's self-report against artifacts before trusting it |
| [`resumable-runs.md`](skills/shared-references/resumable-runs.md) | Long runs that survive context compaction / restarts |
| [`output-language.md`](skills/shared-references/output-language.md) | Which language artifacts and replies are written in |
| [`skill-governance.md`](skills/shared-references/skill-governance.md) | Who may change the skill corpus (`/meta-apply`) |
| [`compute-env-contract.md`](skills/shared-references/compute-env-contract.md) | Declaring GPU / remote environments for experiment skills |
| [`citation-discipline.md`](skills/shared-references/citation-discipline.md) | Citation rules |
| [`effort-contract.md`](skills/shared-references/effort-contract.md) | Effort level specifications |
| [`writing-principles.md`](skills/shared-references/writing-principles.md) | Writing standards |
| [`venue-checklists.md`](skills/shared-references/venue-checklists.md) | Venue formatting |

## Research Wiki (Optional)

If `research-wiki/` exists in the project:
- `/research-lit` auto-ingests discovered papers
- `/idea-creator` reads wiki before ideation, writes ideas (both successful and failed) back after
- `/result-to-claim` updates claim status (supported / invalidated / pending)
- 3+ failed ideas → triggers re-ideation suggestion (failed ideas become anti-repetition memory)

Initialize with `/research-wiki init`. Spec: [`skills/research-wiki/SKILL.md`](skills/research-wiki/SKILL.md). Helper canonical path: `tools/research_wiki.py` (resolved via Layer 1-3 chain above).
