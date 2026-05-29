---
name: slides-polish
description: "Per-page Codex review + targeted python-pptx / Beamer fixes for academic talk slides. Use AFTER /paper-slides (or any externally generated PPTX/Beamer) when the deck looks 'mostly OK' but the user wants a final pass that aligns visual weight with a reference, bumps PPTX fonts to projector-readable size, kills italic style leaks, fixes text-frame overflow, and catches per-slide layout drift. Trigger phrases: \"polish slides\", \"slides 排版不对\", \"PPTX 字体太小\", \"和 Beamer 比一下\", \"per-page review\", \"和 codex 一页一页过\"."
argument-hint: "[slides-dir-or-pptx] — reference: <ref-pdf> [— style: generic | why-rf | neurips | icml | iclr | cvpr] [— effort: lite | balanced | max | beast] [— interactive]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, spawn_agent
---

# Slides Polish: Per-Page Codex Review + Targeted Layout Fixes

Polish a generated slide deck — Beamer (`.tex` + `.pdf`) and/or PPTX — by
running **per-page Codex review** against a reference visual and applying
surgical fixes (font scaling, text-frame resize, callout-box style, em-dash
spacing, anonymity placeholders, Chinese-font hints, italic style leaks)
until each slide reads at the same visual weight as the reference.

Polish: **$ARGUMENTS**

## What This Skill Is — and Is NOT

**This skill polishes layout and typography only.** It is the post-generation
visual pass for an existing deck.

**Hard scope rules** (load-bearing — see Hard Invariants):

- It **does not** rewrite content, claims, numbers, citations, URLs, author
  names, affiliations, or experiment results.
- It **does not** add, remove, or reorder slides unless the user explicitly
  asks (e.g., `— add-slide` / `— drop-slide` flags).
- It **does not** generate outlines, speaker scripts, or new Beamer/PPTX from
  paper source. That is `/paper-slides`'s job.
- It **does not** change figures or equations content.

If you do not yet have a deck, run `/paper-slides` first. If you want to
change content, go back to `/paper-slides` Phases 1-2 (or rewrite the outline
manually) — do not run `/slides-polish` for that.

## Constants

- **REVIEWER_MODEL = `gpt-5.5`** — Codex MCP model for per-page review. xhigh reasoning is non-negotiable (see `../shared-references/effort-contract.md`). `gpt-5.4` is acceptable when the user has no `gpt-5.5` access; `gpt-5.5` is preferred for visual nuance.
- **REVIEWER_REASONING = `xhigh`** — Hard invariant; the effort knob does **not** change this.
- **CONTEXT_POLICY = `fresh`** — Each per-page review uses a **fresh** Codex reviewer call (`spawn_agent`, never `send_input`). See `../shared-references/reviewer-independence.md`. This prevents the reviewer from anchoring on prior fixes.
- **REFERENCE_VISUAL** — Path to a PDF the user wants the polished deck to **align with** in visual weight (typography proportion, color discipline, callout density). Required input. If polishing PPTX only, the **Beamer compile of the same talk** is the ideal reference. If no reference exists yet, ask the user; do not silently default to "Why-RF" or any preset.
- **STYLE_PRESET = `generic`** — Default style anchor. Other options: `why-rf` (academic-minimalist, derived from a 2025 academic talk), `neurips`, `icml`, `iclr`, `cvpr`. Presets influence color discipline + element library; the **reference PDF is the visual ground truth**, not the preset.
- **PPTX_SCALE_HINT = `1.6×`** — Heuristic multiplier from Beamer point sizes to PPTX point sizes for matched visual weight on 13.33"×7.5" PowerPoint at 16:9. Range 1.5-1.8×. The actual scale is **always** validated by visual review, never blindly applied.
- **INTERACTIVE = false** — When false, applies the recommended fix automatically and continues to the next slide. When true (`— interactive`), pauses for user confirmation before each fix.
- **OUTPUT_VERSIONING = on** — Output is a versioned file named `<input-stem>_polished.<ext>` (or `_polished_v2`, `_v3`, …). Snapshot of the input is preserved as `<input-stem>_pre_polish.<ext>`. **The original is never overwritten.** All edit operations target the `_polished` working copy.

> 💡 Override examples
>
> - `/slides-polish talk_pptx/talk.pptx — reference: talk_beamer/main.pdf — style: why-rf`
> - `/slides-polish talk_beamer/ — reference: ./reference_talk.pdf — style: generic — effort: max`
> - `/slides-polish talk.pptx — reference: ./why_rf_2025.pdf — interactive`

## Prerequisites

The skill discovers and reports missing prerequisites at Phase 0; it does not
auto-install. Required:

- **Python**: `python3` with `python-pptx>=0.6` (`pip install python-pptx`).
- **PDF inspection**: `pdfinfo` and either `pdftoppm` (poppler, preferred) or `mutool draw` (mupdf) for rendering slides to PNG. Required so the per-page Codex call sees actual slide pixels, not text extraction alone. Render command: `pdftoppm -r 150 -png <pdf> <out-stem>` (or `mutool draw -o <out-stem>-%d.png -r 150 <pdf>`).
- **PPTX → PDF rendering**: `soffice` (LibreOffice headless) preferred; otherwise the user must export PDF manually from PowerPoint/Keynote.
- **LaTeX** (Beamer side only): `xelatex` (CJK) or `pdflatex`, plus `latexmk` for clean recompiles. The Beamer fix patterns in Phase 2 may require these LaTeX packages: `microtype` (letter-spacing in section labels), `array` (raggedright p-columns), `tcolorbox` (banners and callouts), `ctex` or `xeCJK` (CJK), `tikz` + `tikz-cd` (diagrams).
- **Codex MCP**: `spawn_agent` must be available (the user must be signed in to Codex MCP). The skill aborts at Phase 0 if Codex MCP cannot be reached.

Fallback rules:

- If `pdftoppm`/`mutool` missing → ask user to install, do not proceed (visual review without rendered pages produces low-confidence Codex feedback).
- If `soffice` missing and PPTX is the input → ask user to export PDF from their slide tool; resume after.

## Inputs

Discovered automatically from `$ARGUMENTS` and the project directory:

1. **Slides source**:
   - A directory containing `*.pptx`, or `talk_beamer/main.tex` + `main.pdf`, or both.
   - A specific file path (`talk.pptx` or `main.tex`).
2. **Reference PDF** (`— reference: <path>`, REQUIRED). If not supplied, the skill prompts the user. Do not silently substitute.
3. **Style preset** (`— style: <preset>`, default `generic`). Influences color hex codes and element library; see Style Presets below.
4. **Effort** (`— effort: lite | balanced | max | beast`, default `balanced`). See Effort Levels.
5. **Interactive flag** (`— interactive`). Pauses after each per-slide fix.

## Output Layout

```
<deck-dir>/
├── <stem>.pptx                       # original (untouched)
├── <stem>_pre_polish.pptx            # snapshot before any edit
├── <stem>_polished.pptx              # versioned working output
├── <stem>_polished.pdf               # rendered (when conversion available)
└── ... (Beamer files mirrored)

.aris/slides-polish/<deck-stem>/
├── POLISH_STATE.json                 # phase + per-slide status + version pointer
├── INSPECT_<stem>.json               # pre-polish shape inventory
├── TRIAGE.md                         # Phase-1 verdict matrix (per-slide PASS/NEEDS-WORK/BLOCKER)
├── POLISH_CHANGELOG.md               # per-slide fix log (auditable)
└── traces/                           # codex traces (per-slide review JSON, see review-tracing.md)
    ├── slide_01.json
    ├── slide_02.json
    └── ...
```

The skill keeps a self-contained cache under
`.aris/slides-polish/<deck-stem>/`. Per-call Codex traces also follow the
shared convention `.aris/traces/slides-polish/<date>_runNN/` per
`../shared-references/review-tracing.md`. Resumable across sessions if
`POLISH_STATE.json` exists with `"status": "in_progress"` and is < 24h old.

Note: existing skills like `/paper-slides` may use a co-located state file
(e.g., `slides/SLIDES_STATE.json`). `/slides-polish` keeps its state
in `.aris/` to keep the deck directory free of polish-specific cruft.

## Workflow

### Phase 0: Inventory, Inspect, Triage

1. **Discover inputs**: parse `$ARGUMENTS`; locate slides files; check prerequisites; emit a brief inventory report.
2. **Confirm reference PDF**: validate the file exists and has the same slide count (or at least ≥ slide count) as the input. If a mismatch, ask user.
3. **Inspect shapes**: run the inspector (Phase 0 sub-step below) to produce `INSPECT_<stem>.json` listing every text-frame and shape on every slide with: shape id, type, text content (escaped), font sizes per run, bbox in inches, fill/line color, image dimensions for pictures, presence of speaker notes. This file is the ground truth for "find shape by text" downstream.
4. **Snapshot original**: `cp <stem>.pptx <stem>_pre_polish.pptx` (and `.tex` if Beamer present). All subsequent edits target `_polished` copy.
5. **Render PPTX → PDF if needed** (`soffice --headless --convert-to pdf`). If unavailable, prompt user to export.
6. **Render PDF → PNG**: `pdftoppm -r 150 <pdf> .aris/slides-polish/<stem>/png/page` produces one PNG per slide; passed to Codex during per-page review.
7. **Triage pass**: a single fresh Codex call sweeps all N slides comparing PPTX-PDF (or Beamer PDF) against the reference. Output: per-slide verdict matrix.

#### Inspector contract

The skill ships a contract for `inspect_pptx.py` rather than a fixed
implementation. **On first run, if the script is absent under
`.aris/slides-polish/<deck-stem>/inspect_pptx.py`, create it from this
contract.** Implementations may evolve; the contract is what downstream
phases depend on.

CLI:

```
python3 inspect_pptx.py --pptx <input.pptx> --out <state-dir>/INSPECT_<stem>.json
# exit 0 on success, 2 on missing python-pptx, 3 on parse failure
```

Recurse through groups; surface table cells and placeholders. Convert all
geometry from EMU to inches via `EMU_PER_INCH = 914400`. Compute
`notes_text_hash` as `sha256(notes_text)` for byte-level integrity check
in Phase 4. Schema:

```json
{
  "slide_count": 22,
  "slide_size_in": [13.33, 7.5],
  "slides": [
    {
      "index": 0,
      "page_number_text": "1 / 22",
      "has_notes": true,
      "notes_text_hash": "sha256:…",
      "shapes": [
        {
          "id": "13",
          "name": "TextBox 3",
          "shape_path": ["13"],
          "parent_group_ids": [],
          "type": "TEXT_FRAME",
          "placeholder_type": null,
          "table_cell": null,
          "text": "ARIS",
          "runs": [
            {"text": "ARIS", "font_pt": 80.0, "bold": false,
             "italic": false, "color_rgb": "1F1F1F"}
          ],
          "bbox_in": {"left": 0.5, "top": 1.6, "width": 12.33, "height": 0.95},
          "fill_rgb": null,
          "line_rgb": null,
          "image_size_px": null
        }
      ]
    }
  ]
}
```

Schema notes:

- `shape_path`: list of shape IDs from outermost group to leaf shape.
- `parent_group_ids`: empty if shape is at the slide root.
- `type`: one of `TEXT_FRAME | PICTURE | AUTO_SHAPE | GROUP | TABLE | CONNECTOR | PLACEHOLDER`.
- `placeholder_type`: e.g., `TITLE | BODY | OBJECT | NONE`.
- `table_cell`: `{row, col}` if shape is a table cell, else null.
- All hex colors are 6-char uppercase, no leading `#`.
- All geometry in inches, rounded to 4 decimals.

#### Triage Codex prompt

```
spawn_agent:
  model: gpt-5.5
  reasoning_effort: xhigh
  message: |
    Triage pass. For each of N slides in <pptx-pdf-path>, compared against
    <reference-pdf-path>, give one line:

      Slide K | PASS | NEEDS-WORK | BLOCKER — <one-sentence reason>

    Focus on: visual-weight match, text-frame overflow, page-number overlap,
    awkward title wraps, italic style leaks, Chinese tofu/missing-glyph
    boxes, callout-box color discipline, anonymity leaks (e.g., real titles
    appearing where placeholders should be).

    Do NOT rewrite content. Do NOT propose font scaling for slides that
    already read fine. Do NOT comment on speaker notes.

    End with a one-line summary: "K BLOCKERS, K NEEDS-WORK, K PASS."
```

Save matrix to `TRIAGE.md`. Present to user before deep work begins.

### Phase 1: Per-Page Review + Fix Loop

For each slide flagged `NEEDS-WORK` or `BLOCKER`, run a focused fresh-thread
Codex call. Apply the returned fix immediately (subject to `INTERACTIVE`),
recompile or save, move to next slide.

**Per-page loop, not batch.** Empirically: per-page Codex calls converge in
1-2 polish rounds where single-pass batch review never converges.

#### Per-page Codex prompt template

```
spawn_agent:
  model: gpt-5.5
  reasoning_effort: xhigh
  message: |
    SLIDE K review. Compare PPTX page K against reference page K.

    Files:
    - PPTX page rendering: <png-path>/page-K.png
    - Reference page rendering: <ref-png-path>/page-K.png
    - Source: <pptx-file-path> (slide index K-1) and/or <main-tex-path>
    - Inspector inventory for slide K: <inspect-json-slide-K-snippet>

    Slide K title (from inventory): "<title>".

    Style anchor: <style-preset> + reference PDF.

    Give:
    1. Status: PASS / NEEDS-WORK / BROKEN
    2. What's working (1-2 specifics)
    3. What's drifting vs reference (1-3 specifics)
    4. Concrete python-pptx (or .tex) fixes:
       - Identify shapes by their text content (NOT by index — index drifts).
       - Use unique-prefix substring matching; if duplicate matches, abort
         and request human disambiguation rather than touching the first.
       - Give before/after snippets.
    5. If a fix would change CONTENT (claims, numbers, anonymity placeholder
       text, etc.), STOP and report it instead of suggesting it.

    End: VERDICT: PASS | NEEDS-WORK | BROKEN. Under 500 words.
```

#### Fix application

After Codex returns, call `apply_fix(slide_index, fix_block)` which:

1. Loads the `_polished` working copy.
2. Locates each target shape by `text_frame.text` substring; **asserts unique match** or aborts.
3. Applies edits (font size, position, color, italic, line spacing).
4. Saves atomically (write to tmp + rename).
5. Logs the change to `POLISH_CHANGELOG.md` (one line: `Slide K | <change> | reason`).

After every 3 slides, write a checkpoint snapshot
`<stem>_polished_checkpoint_KK.pptx`.

#### Robust shape selection

```python
def find_shape(slide, contains: str, *, kind: str | None = None):
    """Return the unique shape whose text_frame.text contains `contains`.
    Aborts if duplicate matches (caller must disambiguate by bbox or kind).
    """
    matches = []
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        if kind is not None and sh.shape_type != kind:
            continue
        if contains in sh.text_frame.text:
            matches.append(sh)
    if len(matches) == 0:
        raise LookupError(f"no shape contains {contains!r} on slide")
    if len(matches) > 1:
        raise AmbiguousMatch(f"{len(matches)} shapes contain {contains!r}; "
                             f"need disambiguator (kind, bbox, or longer needle)")
    return matches[0]
```

For grouped shapes, recurse into `shape.shapes` if `shape_type == GROUP`.

### Phase 2: Beamer-Side Polish (if Beamer source present)

Same per-page review pattern, but on `main.tex` source + compiled PDF. Fixes
are direct `Edit` tool operations on a `main_polished.tex` working copy
followed by `xelatex` recompile and PNG re-render. The original `main.tex`
is preserved.

#### Common Beamer fix patterns (inline catalog — no external file required)

These are encoded directly in this SKILL.md so the skill has zero external
dependencies:

- **Frame title size + thin underline rule**: use `beamercolorbox` template
  with `\hrule height 0.55pt` AFTER the title text, NOT a bare `\rule{}`
  outside the beamercolorbox (which renders top-right, not under title).
- **`\sectionlabel` macro for small caps blue mini-headers**:
  ```latex
  \newcommand{\sectionlabel}[1]{%
    {\sffamily\fontsize{8}{10}\selectfont
     \textcolor{<accent>}{\textls[200]{\MakeUppercase{#1}}}}}
  ```
  Requires `microtype` for `\textls`.
- **`array` package for `>{\raggedright\arraybackslash}p{Xcm}` in cards**.
  Without it, tabular cells justify and create rivers / mid-word hyphenation
  in narrow columns.
- **Banner = real `tcolorbox`**, not `\begin{center}\color{...}` (which
  renders as plain centered text, not a banner).
- **Em-dash spacing**: prefer `\textemdash{}` (with explicit braces) or
  `\,---\,` over a bare `—`. A bare em-dash often renders with collapsed
  surrounding whitespace.
- **Color-leak inside `\sectionlabel`**: `\sectionlabel{... \textcolor{red}{...}}`
  BREAKS because `\MakeUppercase` uppercases color name → undefined-color
  error. Put `\textcolor` outside or define a colored `\sectionlabel*` variant.
- **CJK + math**: with `xelatex`, use `\usepackage[fontset=fandol]{ctex}` or
  set EA fonts explicitly. Mixed Chinese-English in titles needs the EA font
  hint or characters fall back to Latin.

### Phase 3: PPTX-Side Polish

Apply font scaling **first** (Phase 3a), then layout fix loop (Phase 3b).
Bumping fonts without resizing frames creates overflow.

#### Phase 3a: Font scaling (heuristic table)

Compute target sizes from Beamer reference using `PPTX_SCALE_HINT`. Reference
mapping:

| Beamer pt | PPTX target | Role |
|---|---|---|
| 8 / 8.5 | 14-18 small caps | section labels |
| 10 italic | 14 italic | gray italic cue / hints |
| 11 body | 22-24 | bullets, paragraphs |
| 12 page number | 16 | "N / total" gray bottom-right (cap at 16) |
| 14 emphasis body | 22-24 | bigger sub-headers |
| 16 callout content | 24-28 | eqbox / yellowstrip body |
| 17-22 big number | 28-36 | hero stats (e.g., "8.1k+", funnel "8/6/2/1") |
| 22 frame title | 40-44 | every page title |
| 28 emphasis hero | 36-44 | hero text |
| 42 cover wordmark | 80-100 plain BLACK | cover (Why-RF discipline: not colored) |

**Page-number rule**: never bump page numbers above 16pt. They stay small.

After scaling, **always** revisit Phase 1 triage — the 1.6× hint is a
starting point; some slides need 1.5×, some 1.8×.

#### Phase 3b: Text-frame layout fix loop

Two recurring failure modes after font bump:

1. **Title overlaps subtitle/body**: a title at 100pt sits in a 0.95"-tall
   frame but the glyph is ~1.4" tall, so it bleeds down. Fix: increase the
   text frame height AND reposition the next-element top.
2. **Body bullets wrap mid-sentence**: a long-noun-phrase bullet wraps
   with the final noun alone on the next line because the frame width is
   sized for the old (smaller) font. Fix: widen the frame AND narrow the
   adjacent column.

Each per-page Codex call returns specific shape resize commands; apply via
the inspector's bbox primitives.

#### Phase 3c: Common PPTX pitfalls (inline catalog)

- **Image aspect ratio**: bumping `width` without `height` stretches embedded
  PNGs. Always compute `height = width × (image_height_px / image_width_px)`.
- **Banner = real filled rectangle**: use `tcolorbox`-equivalent (in PPTX,
  a separate `MSO_SHAPE.RECTANGLE` behind the text frame), not just colored
  text.
- **Curved arrows**: python-pptx has no curved-arrow primitive. Approximate
  with two straight `MSO_CONNECTOR_TYPE.STRAIGHT` connectors (vertical +
  horizontal) or use an `add_freeform` Bezier. Document the approximation.
- **Italic style leak**: `\itshape` in the source without braces causes all
  following runs in the same paragraph to inherit italic. Wrap as
  `{\itshape ...}` or scope to a single run.
- **Chinese rendering**: PowerPoint needs the East Asian font hint
  (`<a:ea typeface="PingFang SC"/>` for macOS, `Microsoft YaHei` for
  Windows). Without it, characters fall back to a Latin font and render
  as tofu boxes.
- **Em-dash spacing**: bare `—` in titles often renders with collapsed
  spaces. Insert literal spaces (`" — "`) or use figure-space.
- **Cycle-arrow / feedback-loop labels**: ensure label bbox stays inside
  slide bounds (`L > 0.4in`, `T > 0.4in`). PPTX silently clips off-slide
  content, and curved labels positioned near the left/top edge are the
  most common offenders.
- **Anonymity placeholder discipline**: ALL placeholders for under-review
  work must use generic phrasing (e.g., "Withheld for anonymous review",
  "[anonymized]"). NEVER infer or fill in real titles, counts, or URLs.
  See `../shared-references/experiment-integrity.md`.

### Phase 4: Verification + Re-Triage

1. **Re-render PPTX → PDF** (LibreOffice or user-export).
2. **Re-render PDF → PNG** for visual.
3. **Re-triage**: rerun Phase 0.7 prompt. Goal: 0 BLOCKERS, ≤2 NEEDS-WORK.
   If > 2 NEEDS-WORK remain, loop back to Phase 1 for those slides.
4. **Speaker-notes integrity check**: assert every slide's `notes_slide` is
   present and unchanged from `_pre_polish.pptx` (a polish round must never
   touch notes content).
5. **Anonymity scan**: grep the final PPTX for known sensitive strings (real
   author names absent from the original, real URLs added by the LLM, real
   submission counts). If found, fail closed and report.
6. **Final emit**: `<stem>_polished.pptx` (and `.pdf` if rendered).

### Phase 5: Changelog

Write `POLISH_CHANGELOG.md`:

```
Slide  1 cover  | bumped wordmark 80→86; subtitle 36→40; line spacing 0.9        | Codex per-page review
Slide  2 hook   | left body L=0.45 W=8.30; right cards 28→19pt; yellow strip 22→19 | wrap fix
Slide  3 …      | …                                                              | …
```

This makes every polish round auditable and reversible (each line maps to
a `_polished_v{i}` checkpoint).

## Style Presets

Presets influence default colors and the element library only — the
**reference PDF is always the visual ground truth**, not the preset.

### `generic` (default)

Black + one accent (default `#2563EB`). No callout-box fills beyond a single
neutral background where load-bearing.

### `why-rf` (academic-minimalist, example preset)

Anchor: a 2025 academic talk on rectified flow with the following discipline.

| Element | Beamer | PPTX (1.6× hint) | Notes |
|---|---|---|---|
| Frame title | `\fontsize{22}{26}` | 40-44pt sans bold | + thin 0.55pt accent underline rule full-width |
| Body text | 11pt | 22-26pt | Calibri / Helvetica Neue equivalent |
| Card title (chorebox) | 11pt bold | 20-26pt bold | Within `chorebox` callout |
| Section label | 8pt small caps | 16-18pt small caps wide-tracked | Color = primary accent |
| Italic gray cue | `\scriptsize\itshape` | 12-14pt italic | Color = pagegray |
| Page number | `\footnotesize` | 14-16pt | Bottom-right gray |
| Cover title | 44pt plain BLACK | 80-100pt plain BLACK | Title is **not** colored |

**Color palette** (load-bearing only, sparingly):

- Primary accent (e.g., `#2E75B6`)
- Darker accent (chip backgrounds, big numbers, e.g., `#1F4E79`)
- Light callout bg (e.g., `#DEEBF7`)
- Honest-disclosure yellow (e.g., `#FFF4CC`)
- Audit-bug red (safety disclaimers only, e.g., `#C00000`)
- Page gray (e.g., `#808080`)
- Text dark (e.g., `#1F1F1F`)

**Element library** (used sparingly):

- `chorebox`: white bg + thin top accent rule + section-label + bold title + body
- `eqbox`: light-accent full-width banner; load-bearing assumption / conclusion only
- `yellowstrip`: honest-yellow + 3pt left-edge orange rule; honest disclosures only
- `redbox`: light red + red border; **safety disclaimers only**
- `banner`: light-accent full-width strip; brief banner caption

**Discipline**: fewer color boxes than typical "designerly" templates. Cosmetic
cards become plain bullets; marketing flourishes are removed.

### `neurips` / `icml` / `iclr` / `cvpr`

Inherit color schemes from `/paper-slides`. Polish-loop and font-scaling rules
unchanged.

## Effort Levels

See `../shared-references/effort-contract.md` for the full contract.

| `effort` | Behavior |
|---|---|
| `lite` | Triage pass + fix BLOCKERS only. Skip per-page review for NEEDS-WORK slides. ~30% of full token cost. |
| `balanced` (default) | Triage + per-page review for all NEEDS-WORK and BLOCKER slides. PASS slides untouched. |
| `max` | Per-page review on **every** slide (including PASS). ~2.5× tokens. |
| `beast` | `max` + a second polish round after Phase-4 re-triage; chase remaining ≤2pt overfull / minor wraps. ~5× tokens. |

`reasoning_effort: xhigh` is non-negotiable across all levels.

## Hard Invariants

These are non-negotiable:

1. **Reference is required.** The skill never polishes without an explicit visual anchor. If no reference PDF, ask the user. A style preset is **not** a substitute.
2. **Original is never overwritten.** All edits target `<stem>_polished.<ext>`; the snapshot at `<stem>_pre_polish.<ext>` is the rollback target.
3. **Speaker notes are preserved verbatim.** Every PPTX edit must preserve `slide.notes_slide` content. Phase 4.4 verifies this byte-for-byte against the snapshot.
4. **No content edits.** No new claims, numbers, citations, URLs, author names, affiliations, or experiment results. No equation or figure-content changes. No paraphrasing of body text — only style/typography/box edits. If a Codex fix proposal would change content, the skill stops and reports it.
5. **No slide reordering, addition, or deletion** unless the user passes an explicit flag (`— add-slide-K-after-J`, `— drop-slide-K`).
6. **Cross-model independence**: per-page Codex calls are fresh `spawn_agent` calls, not `send_input`. Reviewer never sees prior fix lists. See `reviewer-independence.md`.
7. **Anonymity placeholders fail closed.** If a Codex fix proposes filling in a real title, count, or URL where a placeholder was, the skill rejects it and surfaces the proposal for human review. See `experiment-integrity.md`.
8. **Page numbers stay ≤ 16pt.** Why-RF discipline; never bump them.
9. **`reasoning_effort: xhigh`** is invariant across all `effort` levels.
10. **Robust shape selection**: edits use unique-prefix `text_frame.text` matching with assert-unique semantics. If duplicate matches, abort and request disambiguation.

## Review Tracing

After each per-page Codex call, save the trace following
`../shared-references/review-tracing.md`. Per-call file under
`.aris/slides-polish/<stem>/traces/slide_KK.json` with:

- Codex `agent_id`
- prompt (verbatim)
- response (verbatim)
- applied diff summary (list of shape edits with before/after sizes/bboxes)
- validation status (post-fix re-render PASS/FAIL)

Both the triage pass and the per-slide passes are traced.

## Prior Skill Relationship

- Runs **after** `/paper-slides` (or any externally generated deck).
- Compatible with `/paper-poster` workflow (same color discipline) but
  different output cadence.
- Uses the same `spawn_agent` MCP infrastructure as
  `/auto-paper-improvement-loop`, `/research-review`, etc.
- Does **not** call or compose with `/paper-slides` content phases — strict
  separation.

## When NOT to Use

- Slides are still in **content drafting** phase — go back to `/paper-slides`
  Phases 1-2.
- Complete redesign needed (different colors / template / aspect ratio) —
  re-run `/paper-slides`, not polish.
- Deck has fewer than 5 slides — per-page review overhead is not worth it;
  hand-edit.
- The user explicitly says "no Codex" — this skill is Codex-driven by design.

## Empirical Origin

This skill was extracted from a polish run on a Chinese-spoken academic
conference talk (May 2026). The convergent observation: **once content
is locked, the remaining cost is per-page visual fidelity** — and per-page
Codex review with concrete python-pptx / `.tex` fix snippets converges in
1-2 rounds where single-pass batch review never converges. The fix-pattern
catalogs in Phases 2-3 (Beamer template gotchas, PPTX font scaling, layout
fix loop, Chinese-font hints) are the durable artifact.

## Parameter Pass-Through

When invoked via `/research-pipeline` or another orchestrator, parameters
flow as:

- `— effort` → see Effort Levels.
- `— reference` → `REFERENCE_VISUAL`.
- `— style` → `STYLE_PRESET`.
- `— interactive` → `INTERACTIVE = true`.

Other args (e.g., `— venue`) are ignored by this skill and not propagated.
