---
name: paper-talk
description: "End-to-end conference talk pipeline: paper → slide outline → Beamer + PPTX → per-page polish → assurance checks (claim / citation / anonymity) → final export and report. Default-good for academic conference talks (NeurIPS / ICML / ICLR / VALSE / 投稿 talks). Trigger phrases: \"做 talk\", \"做 PPT 全流程\", \"talk pipeline\", \"end-to-end slides\", \"做演讲\", \"conference talk full workflow\". Use when the user wants the complete talk artifact, not just a slide deck."
argument-hint: "[paper-dir] [— talk_type: oral | spotlight | poster-talk | invited] [— minutes: N] [— assurance: draft | polished | conference-ready] [— reference: <pdf>] [— style: generic | why-rf | <venue>] [— style-ref: <paper-source>] [— effort: lite | balanced | max | beast] [— anonymous]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Skill, spawn_agent
---

# Paper Talk: End-to-End Conference Talk Pipeline

Workflow: from a completed paper to a conference-ready talk artifact —
slide outline, Beamer source, editable PPTX, speaker notes, full talk
script, polished visuals, and assurance checks.

Pipeline target: **$ARGUMENTS**

## Assurance Ladder

The skill takes an explicit `— assurance:` argument; default is `polished`.

| Level | Phases run | Use when |
|---|---|---|
| `draft` | 0 → 1 → 2 → 5 → 6 | Internal practice talk; quick first-pass deck |
| `polished` (default) | 0 → 1 → 2 → 3 → 5 → 6 | Lab seminar, workshop, default conference talk |
| `conference-ready` (or `submission`) | 0 → 1 → 2 → 3 → **4** → 5 → 6 | Top-venue oral / spotlight where slide claims are scrutinised; or anonymous submission |

Phase 4 (assurance checks) is opt-in via `— assurance: conference-ready`.
The lower levels skip claim / citation / anonymity audits, which is correct
when content has already been audited at the paper-writing stage.

## Hard Invariants

These are non-negotiable across all phases:

1. **Original paper is read-only.** This workflow consumes the paper directory; it never modifies `paper/main.tex` or other paper artifacts.
2. **Original deck is preserved.** `/paper-slides` produces a baseline deck; `/slides-polish` writes a `_polished` versioned copy. The original Beamer + PPTX are never overwritten.
3. **Speaker notes are byte-stable.** Polish must not change `slide.notes_slide` content. Phase 4 verifies this.
4. **No new content anywhere in the pipeline.** All slide text, speaker notes, talk script, Q&A answers, claims, numbers, citations, URLs, author names, affiliations, anonymity placeholders, and experiment results must be either paper-grounded (extracted from `PAPER_DIR/` artefacts) or explicitly user-provided. The pipeline never invents content during outline, build, polish, audit, or export. Phase-4 anonymity scan + claim audit verify this end-to-end.
5. **No slide reordering.** Add / drop / reorder requires explicit user flags.
6. **Fresh-context independence.** Per-page Codex calls in `/slides-polish` use fresh `spawn_agent` calls (no `send_input`) and are same-family provisional in the base mirror.
7. **Anonymity fail-closed.** If any audit (or any Codex fix proposal) would replace a placeholder with a real title / count / URL, the workflow halts and surfaces the proposal for human review. See `../shared-references/experiment-integrity.md`.
8. **Style references are guidance, not text source.** A `— reference:` PDF or `— style:` preset informs visual weight and structural rhythm; never copy prose, examples, slide titles, or speaker-note text from the reference.
9. **Final report cannot be `conference-ready` unless required audits pass.** Phase 6 verifies and downgrades verdict if audits fail.
10. **`reasoning_effort: xhigh`** is invariant across all `effort` levels for any Codex call invoked by sub-skills.

## Constants

- **PAPER_DIR = `paper/`** — Source paper directory. Override via positional argument.
- **OUTPUT_DIR = `slides/`** — Where the deck artefacts live.
- **STATE_DIR = `.aris/paper-talk/`** — Workflow state, audit logs, final report.
- **TALK_TYPE = `spotlight`** — Default talk format. Inherited by `/paper-slides`.
- **TALK_MINUTES = 15** — Default duration. Inherited by `/paper-slides`.
- **VENUE = `NeurIPS`** — Default venue (used by `/paper-slides` color schemes when `— style` is not passed).
- **ASPECT_RATIO = `16:9`** — Inherited by `/paper-slides`.
- **STYLE_PRESET** — `generic` if not passed; `why-rf` and venue presets supported by `/slides-polish`.
- **REFERENCE_VISUAL** — Required when `assurance ≥ polished`. The Beamer compile of this talk is an acceptable self-reference; an external academic talk PDF is preferred when the user wants visual alignment beyond defaults.
- **AUTO_PROCEED = false** — Each major phase pauses for user approval. Set `true` only when explicitly requested.

## Inputs

Discovered from `$ARGUMENTS` and the project directory:

1. **`PAPER_DIR/`** — compiled paper (`main.tex` + `main.pdf`). The paper must already be in good shape; this workflow does not write the paper.
2. **`PAPER_DIR/sections/*.tex`** — section sources for content extraction.
3. **`PAPER_DIR/figures/`** — figures available for slide reuse.
4. **(optional) `slides/SLIDE_OUTLINE.md`** — pre-existing outline (resume mode); skips Phase 1 generation.
5. **(optional) `— reference: <pdf>`** — visual anchor for `/slides-polish`. If absent and the assurance level requires polish, the workflow uses the Beamer self-compile as reference.
6. **(optional) `— talk_type`, `— minutes`, `— style`, `— effort`** — see Constants.

## Output Layout

File names match `/paper-slides`'s emit contract — this workflow is a
**non-renaming consumer**.

```
slides/
├── SLIDE_OUTLINE.md                # Phase-1 outline (claim-first per slide)
├── main.tex                        # Beamer source (from /paper-slides)
├── main.pdf                        # compiled Beamer
├── presentation.pptx               # editable PPTX (from /paper-slides; emit name fixed by /paper-slides)
├── presentation_pre_polish.pptx    # snapshot before /slides-polish
├── presentation_polished.pptx      # /slides-polish output (when assurance ≥ polished)
├── presentation_polished.pdf       # rendered (LibreOffice or user-export)
├── speaker_notes.md                # per-slide notes (from /paper-slides)
├── TALK_SCRIPT.md                  # full word-for-word talk script + Q&A (from /paper-slides)
└── assets/                         # per-slide PNG previews

.aris/paper-talk/
├── PIPELINE_STATE.json             # phase pointer, status, timestamps
├── FINAL_REPORT.md                 # human-readable summary at end
├── audit-input/                    # Phase-4 staging copies of slide text + notes + script (so /paper-claim-audit and /citation-audit can run on slide content as a synthetic "paper")
│   ├── main.tex                    # \input{sections/slide_text.tex} \input{sections/notes.tex} \input{sections/script.tex}
│   ├── sections/
│   │   ├── slide_text.tex          # all visible slide bullets/titles/callouts as \section{Slide K}
│   │   ├── notes.tex               # speaker_notes.md → LaTeX, one \section per slide
│   │   └── script.tex              # TALK_SCRIPT.md → LaTeX, one \section per slide
│   ├── references.bib → ../../../paper/references.bib   # symlink to source paper bib for /citation-audit
│   ├── results/ → ../../../paper/results/                # symlink — claim audit needs real evidence
│   └── figures/ → ../../../paper/figures/                # symlink — citation audit may reference figure captions
└── audits/
    ├── slide_claim_audit.json      # 6-state verdict per claim (PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR)
    ├── citation_audit.json         # citation existence / metadata
    ├── anonymity_scan.json         # placeholder discipline check
    └── export_integrity.json       # page-count / aspect / blank-slide / notes-preserved
```

The audit JSON files follow the shared 6-state schema; see
`../shared-references/assurance-contract.md`.

## Workflow

### Phase 0: Setup

1. **Validate paper directory**: `ls $PAPER_DIR/main.tex $PAPER_DIR/main.pdf`. If absent → halt and ask user to point to the compiled paper.
2. **Check prerequisites**:
   - LaTeX: `which xelatex pdflatex latexmk`
   - PPTX rendering: `which soffice` (LibreOffice headless) — required for Phase 4 export integrity check; otherwise prompt user to export PDF manually.
   - PDF tools: `which pdfinfo pdftoppm` (poppler) — required for `/slides-polish` PNG rendering.
   - Codex MCP availability.
   - python-pptx (`python3 -c 'import pptx'`).
3. **Resolve overrides** from `$ARGUMENTS`: `talk_type`, `minutes`, `assurance`, `reference`, `style`, `effort`.
4. **State init**: write `.aris/paper-talk/PIPELINE_STATE.json` with `phase: 0`, timestamp, all resolved overrides.
5. **Resume mode**: if `slides/SLIDE_OUTLINE.md` exists and `PIPELINE_STATE.json` shows recent in-progress work, prompt the user — resume from last phase or start fresh.

### Phase 1: Slide Outline (Checkpoint)

Goal: produce or accept a `slides/SLIDE_OUTLINE.md` that the user signs off
on before any deck-building happens.

If `slides/SLIDE_OUTLINE.md` already exists, present its summary (slide
count, time budget, claim-per-slide map) to the user and ask:

> "Use existing outline (Y/n)? Modify? Regenerate?"

Otherwise, delegate to `/paper-slides` Phase-1 only (content extraction +
slide outline generation). `/paper-slides` writes the outline into its own
state; we adopt it as `slides/SLIDE_OUTLINE.md`.

The outline must contain, per slide:

- A **claim-first** title (states the slide's point, not the topic).
- One main idea per slide.
- Bullet content (sentence fragments, not paragraphs).
- Figure / equation / callout note.
- Time budget (seconds).
- Transition cue.
- Speaker note seed (1-3 sentences; expanded in Phase 2).

**Checkpoint**: present the outline. Default behavior: pause for user
approval. Set `AUTO_PROCEED = true` only when the user is explicitly
running unattended.

### Phase 2: Build Baseline Deck

Invoke `/paper-slides` to generate Beamer source + PPTX from the approved
outline.

```
/paper-slides "<paper-dir>" — talk_type: <T> — minutes: <N> — venue: <V> — aspect: 16:9 — notes: true
```

Forward `— style-ref:` if the user originally passed it (writer-side; the
reviewer-side polish in Phase 3 must NOT see it — see invariant 8).

`/paper-slides` produces (emit names fixed by `/paper-slides`):

- `slides/main.tex` + `slides/main.pdf` (Beamer)
- `slides/presentation.pptx` (editable PPTX)
- `slides/speaker_notes.md`
- `slides/TALK_SCRIPT.md`

After return: verify the four artefacts exist. If any missing, halt with a
diagnostic. Do **not** rename outputs — downstream phases bind to these
exact paths.

### Phase 3: Visual Polish (when assurance ≥ polished)

Skip when `assurance == draft`.

Invoke `/slides-polish` against the freshly generated PPTX, with a
reference. If the user passed `— reference:`, use that. Otherwise, use the
Beamer compile (`slides/main.pdf`) as the visual reference — the Beamer is
the design intent for the same talk, so it is the correct anchor when no
external reference is available.

```
/slides-polish "slides/presentation.pptx" — reference: slides/main.pdf — style: <preset> — effort: <effort>
```

After return: verify `slides/presentation_polished.pptx` exists; if
rendering tools are available, also verify `slides/presentation_polished.pdf`.

The polish phase is read-only on content (see Hard Invariants). If
`/slides-polish` emits a `BLOCKED` verdict because a Codex fix proposal
would alter content, surface that block to the user and halt rather than
overriding.

### Phase 4: Assurance Checks (when assurance == conference-ready)

Skip when `assurance ∈ {draft, polished}`.

`/paper-claim-audit` and `/citation-audit` expect a paper-shaped input
(`paper/main.tex` + `paper/sections/*.tex` + `paper/results/`) and emit
JSON under `paper/`. Slides have a different shape, so this phase first
**stages** slide artefacts into a synthetic paper directory, then invokes
the audits against that synthetic input. Verdicts are written under
`.aris/paper-talk/audits/` using the shared 6-state schema (`PASS`,
`WARN`, `FAIL`, `NOT_APPLICABLE`, `BLOCKED`, `ERROR`) — see
`../shared-references/assurance-contract.md`.

#### 4.0 Staging adapter

The staged "paper" mirrors `/paper-claim-audit` and `/citation-audit`'s
expected layout: `main.tex` at the root that `\input{}`s `sections/*.tex`,
plus a `.bib` file and `results/`+`figures/` symlinks.

```
.aris/paper-talk/audit-input/
├── main.tex
│   # contains: \input{sections/slide_text.tex}
│   #           \input{sections/notes.tex}
│   #           \input{sections/script.tex}
│   #           \bibliography{references}
├── sections/
│   ├── slide_text.tex      # one \section{Slide K — <title>} per slide; visible bullets, titles, callout text, in-slide \cite{...}
│   ├── notes.tex           # speaker_notes.md converted to LaTeX, one \section per slide
│   └── script.tex          # TALK_SCRIPT.md converted to LaTeX, one \section per slide
├── references.bib → ../../../paper/references.bib  # symlink to source paper bib (or copy if symlink not allowed)
├── results/ → ../../../paper/results/              # symlink — claim audit needs real evidence
└── figures/ → ../../../paper/figures/              # symlink — citation audit may reference figure captions
```

If the source paper uses a different bib name (e.g., `paper.bib`),
mirror the actual file. If multiple bibs are used, link them all.

The staged "paper" exists only for the duration of Phase 4 and is removed
in Phase 6 unless the user passes `— keep-audit-input`.

#### 4.1 Slide claim audit

Invoke `/paper-claim-audit` against the staged input. Scope is **slide
text + speaker notes + full talk script** — talks often smuggle
unsupported claims into spoken parts that the visible bullets don't show.

```
/paper-claim-audit ".aris/paper-talk/audit-input"
```

The audit emits `audit-input/PAPER_CLAIM_AUDIT.json` with the shared
6-state schema. Move it to
`.aris/paper-talk/audits/slide_claim_audit.json` and de-stage the path
prefix so the verdicts cite slide K rather than synthetic-paper sections.

A `FAIL` or `BLOCKED` verdict on any claim downgrades the Phase-6 final
verdict from `conference-ready` to `polished`.

#### 4.2 Citation audit

Invoke `/citation-audit` over the staged input. Verify any `\cite{...}` in
slides + notes + script via DBLP / CrossRef; flag fabricated entries.

```
/citation-audit ".aris/paper-talk/audit-input"
```

Output → `.aris/paper-talk/audits/citation_audit.json` (6-state).

#### 4.3 Anonymity scan

When the talk is for an anonymous-submission venue or the user passed
`— anonymous`, scan **slides + notes + script** for:

- Real paper titles where placeholders should be (`[anonymized]`,
  `Withheld for anonymous review`, etc.).
- Real author names beyond the talk's own author block.
- Real submission counts.
- Real URLs that would deanonymize.

Output → `.aris/paper-talk/audits/anonymity_scan.json` (6-state). Any
`FAIL` (real-content leak) blocks `conference-ready`.

### Phase 5: Final Export + Integrity

Resolve the **final PPTX path**:

```
FINAL_PPTX = slides/presentation_polished.pptx  if Phase 3 ran
           = slides/presentation.pptx           if assurance == draft (Phase 3 skipped)
```

Then:

1. **Recompile Beamer cleanly**: `cd slides && latexmk -pdf -xelatex main.tex` (or `pdflatex` for non-CJK). Confirm `main.pdf` page count matches outline slide count.
2. **Render `FINAL_PPTX` → PDF** via `soffice --headless --convert-to pdf <FINAL_PPTX> -outdir slides/`. If unavailable, prompt user.
3. **Export integrity check** → `.aris/paper-talk/audits/export_integrity.json` (6-state):
   - PPTX-PDF page count == Beamer-PDF page count.
   - Aspect ratio == declared (16:9 default).
   - No fully-blank slide.
   - Speaker notes preserved on every slide that had them in the baseline. When Phase 3 ran, sha256 match against `presentation_pre_polish.pptx`'s notes; when Phase 3 skipped, against `presentation.pptx`'s own notes (no-op).
   - Embedded fonts are appropriate for projector use (e.g., Calibri / Helvetica Neue / PingFang SC for Chinese).

If any integrity check fails, downgrade the Phase-6 verdict and surface
specifics to the user.

### Phase 6: Final Report

Write `.aris/paper-talk/FINAL_REPORT.md` with:

- **Verdict**: `draft` | `polished` | `conference-ready` (downgraded if audits failed).
- **Artefact paths**: Beamer source / PDF, baseline PPTX, polished PPTX, polished PDF, notes, script.
- **Slide count**, time budget vs target.
- **Audit summary** (one line per audit run + PASS / WARN / FAIL).
- **Open warnings**: any unresolved Codex polish notes the user should review by hand.
- **Next steps**: e.g., "drop in real QR images on slide N", "verify HF Daily Papers screenshot", "rehearse to confirm 25-min budget".

A final `conference-ready` verdict requires:

- Phases 0-5 all completed without halt.
- All Phase-4 audit JSONs returned `PASS` (or `NOT_APPLICABLE` when the
  audit's content detector did not match — e.g., no citations on slides).
  Any `WARN`, `FAIL`, `BLOCKED`, or `ERROR` downgrades the verdict.
- Phase-5 export integrity returned `PASS`.
- No anonymity-scan `FAIL` when anonymous submission is declared.

Otherwise the report emits the highest passing level (`polished` or
`draft`) and itemises why `conference-ready` was not granted, citing the
specific audit JSON and the failing verdict line.

## Effort Levels

See `../shared-references/effort-contract.md`.

| `effort` | Behavior |
|---|---|
| `lite` | Forwarded to sub-skills. `/slides-polish` runs in `lite` (BLOCKERS only). **Phase 4 still runs at the requested assurance level** — `effort` controls depth, never audit gating (see `../shared-references/assurance-contract.md`). |
| `balanced` (default) | Standard pipeline. `/slides-polish` runs `balanced`. |
| `max` | `/slides-polish` runs `max` (per-page review on every slide). Phase-4 audits read all artefacts in full. |
| `beast` | `/slides-polish` runs `beast` (second polish round). Phase-4 audits include extended assurance checks; final report adds an executive summary. |

`reasoning_effort: xhigh` is invariant.

`assurance` and `effort` are **independent axes**. The user may legally
combine `effort: lite, assurance: conference-ready` to mean "fast pipeline,
but every audit must emit a verdict before finalisation."

## Parameter Pass-Through

```
/paper-talk "paper/" — talk_type: oral — minutes: 25 — assurance: conference-ready \
            — reference: ./refs/why_rf_2025.pdf — style: why-rf — effort: max
```

Forwarded to:

- `/paper-slides` (Phase 2): `paper-dir`, `talk_type`, `minutes`, `venue`, `aspect`, `notes`, `style-ref` if writer-side.
- `/slides-polish` (Phase 3): polished pptx target, `reference`, `style`, `effort`.
- `/paper-claim-audit` (Phase 4.1): scoped to slide deck artefacts (not paper).
- `/citation-audit` (Phase 4.2): scoped to slide-deck-only citations.
- Anonymity scan (Phase 4.3): inline tool, no external skill.

## When NOT to Use

- The paper is not yet compiled or claims are not stable. Run `/paper-writing` first.
- The user wants a poster, not a talk. Use `/paper-poster-html`.
- The user already has a finished deck and only needs visual polish. Use `/slides-polish` directly — `/paper-talk` would needlessly rebuild.
- The talk content is unrelated to a paper (general lecture, demo). The orchestration assumes a paper-grounded talk; for ad-hoc decks, use `/paper-slides` directly with manual outline.

## Prior Skill Relationship

- Composes `/paper-slides`, `/slides-polish`, `/paper-claim-audit`, `/citation-audit`.
- Does **not** call `/kill-argument` by default — that is upstream intellectual stress-test, not deck QA. Users who want talk-story stress-test before slide build can run `/kill-argument paper/` first.
- Sister workflow to `/paper-writing` (paper) and `/paper-poster-html` (poster).

## Empirical Origin

This workflow generalises a 30+ iteration polish run on a Chinese-spoken
academic conference talk (May 2026). The convergent learning was that talk
preparation has the same shape as paper preparation — plan, build, polish,
audit, export, report — and benefits from the same assurance ladder. The
per-page Codex polish pass (Phase 3) is the single most expensive but
highest-value step, and is hidden behind the `polished` default so users
get it without thinking about it.
