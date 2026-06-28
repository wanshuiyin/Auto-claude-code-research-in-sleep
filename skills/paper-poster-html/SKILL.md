---
name: paper-poster-html
description: "DEFAULT poster pipeline — build an academic conference poster (ICML/NeurIPS/ICLR/CVPR/...) as a single HTML/CSS file with measurement-driven hard gates, real paper figures, a two-hue design-token system, and print-ready PDF via headless Chromium. Use when the user says \"做海报\", \"poster\", \"conference poster\", \"paper poster\", or asks to design/redo a research poster. Supersedes the retired LaTeX /paper-poster."
argument-hint: "[paper-dir-or-pdf] [— venue: ICLR, canvas: 185x90cm landscape, venue-colors: true]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebFetch, WebSearch, AskUserQuestion, mcp__codex__codex
---

# Paper Poster (HTML): measurement-gated poster generation

One HTML file styled for an exact print canvas (`@page { size: W H }`), rendered to PDF
via Playwright print emulation. **Iterate by measuring, not eyeballing** — the screen
preview lies; only print emulation at the correct viewport tells the truth. Core gate
machinery is adapted from [posterly](https://github.com/Chenruishuo/posterly) (MIT, ©
2026 Ruishuo Chen — see `NOTICE.md` and `LICENSES/posterly-MIT.txt`); ARIS adds style
discipline gates, figure-provenance gates, the cross-model review loop, and the
anti-patch-loop fix vocabulary.

## Why this skill exists (the failure it prevents)

A predecessor pipeline produced a poster with **30+ colors, zero real paper figures, a
screen-pixel canvas, and tiny formulas floating in oversized boxes**, then spent 12+
review rounds making it *worse* — each round added a new badge color or bespoke SVG
patch. The cure is structural, not exhortative:

1. **Hard gates run before any aesthetic opinion** (alignment, style, assets must PASS
   first — a reviewer never sees an unmeasured poster).
2. **A closed fix vocabulary** — visual-review fixes can only touch design tokens,
   whole catalogued components, content rebalance, assets, or canvas choice. New inline
   styles / new hex values / bespoke decorations are structurally forbidden.
3. **Two-hue discipline as a machine check**, not a style suggestion.
4. **Real paper figures with provenance manifest**, or the gate fails.

## Mental model

```
paper (.tex / PDF) ──► content plan + claim→evidence audit (codex, fresh)
                              │
   figures extracted ─────────┤  FIGURE_MANIFEST.json (provenance, sha256)
   (real paper figures ONLY)  ▼
   template scaffold ──► fill ──► run_gates.py            ◄─── HARD, loop here
                                  preflight → style → asset → measure → polish
                              │ all hard gates PASS
                              ▼
                    Claude visual review (≤3 issues × ≤3 rounds, fix-vocabulary only)
                              │ score ≥ 9
                              ▼
                    codex final cross-model review (fresh thread, full HTML+PDF)
                              │ pass
                              ▼
                    verify-final → poster.pdf + GATE_REPORT.json
```

## Constants

- **SKILL_SCRIPTS** = `${CLAUDE_SKILL_DIR}/scripts` — all helpers are single-owner and
  ship inside this skill (Arch C). If the directory is missing the install is broken:
  abort and tell the user to re-install the skill (Policy A — the gates ARE the skill;
  never improvise replacements).
- **REVIEWER_MODEL** = `gpt-5.5`, reasoning `xhigh`, **fresh thread per review call**
  (`mcp__codex__codex`, never `codex-reply` across review boundaries).
- **CANVAS** — from the venue's official spec, looked up live in Phase 0. Never assume.
  (Known anchor: ICLR 2026 main = 185×90 cm landscape per its official printing
  service; ICML/NeurIPS commonly 60×36 in landscape; workshop posters often 61×91 cm
  portrait. Specs change yearly — verify.)
- **PALETTE** — default = `templates/tokens/generic.json` (slate-blue `#2D5F8B` accent
  + gold `#C9A24A` highlight + neutrals) for **all** venues. Venue packs are opt-in via
  `— venue-colors: true`. Purple-dominant accents (hue 250–285) are banned unless the
  user passes `— allow-purple: true`.
- **AUTO_PROCEED = false** — wait for explicit confirmation at every 🚦 checkpoint.
- **OUTPUT_DIR** = `poster_html/` in the working directory.

## Workflow

### Phase 0 — Resume, dependencies, venue spec

1. **Resume**: if `poster_html/POSTER_STATE.json` exists with `status: in_progress`
   (< 24 h), resume from the saved phase.
2. **Dependencies** (degradation chain, in order):
   - Playwright + bundled Chromium → if missing, `python3 -m playwright install
     chromium` → if install fails but system Chrome exists, scripts fall back to
     `channel="chrome"` → if all fail: you may produce the content plan and scaffold
     only, label everything **"not print verified"**, and must NOT emit a final PDF.
   - `pdfinfo` missing → PyMuPDF reads PDF dimensions. At least one of
     pdftoppm / PyMuPDF must exist for PNG review renders.
   - MathJax: download `tex-svg.js` once into `poster_html/assets/mathjax/` and
     reference it locally in the HTML. CDN is acceptable only for drafts; the measure
     gate hard-fails on unrendered MathJax either way.
3. **Venue spec lookup (live)**: consult the venue's official poster-instructions page
   (search + fetch). Extract dimensions, orientation, font floor, logo policy,
   anonymity rules, file format. Record `{spec, source_url, retrieved}` into
   `POSTER_STATE.json` — specs change yearly; never reuse a cached spec silently.

**🚦 Checkpoint**: echo the venue spec table (canvas, orientation, source URL) and the
chosen template. Wait.

### Phase 0.5 — Design discovery (one AskUserQuestion batch)

Ask once, ≤4 questions: layout template (from `templates/README.md`), palette
(default generic pack / venue pack / custom within constraints), logos + venue mark
(paths or "none" — never fabricate; check the venue's logo policy), QR target (paper /
code / project page / none — generate **offline** with `qrencode` or python-`qrcode`;
never a remote QR-service URL). Persist answers in `POSTER_STATE.json` as
`design_decisions` — re-read before any later "improvement" so deliberate choices are
never reverted.

### Phase 1 — Paper ingest, content plan, claim audit

1. Read the paper source (`.tex` ideal; PDF otherwise). Extract: title/authors/affils,
   the 3–5 headline numbers, core method (equations verbatim), main results
   (tables/figures and what they show), takeaways. Build
   `poster_html/POSTER_CONTENT_PLAN.md` — what goes in which column, word budget per
   card. **Target density** (excluding table cells, captions, author line, footer):
   standard poster **550–850 words**; dense theory+empirical poster **750–1050 words**,
   allowed only when ≥2 compact components are used (`eqn-anatomy`, `flow-strip`,
   `derived-col`, `claim-pills`, `keybox--4`). Warn yourself below 500 words on a
   4-column landscape (it will read as sparse next to professionally dense posters)
   unless the template is hero/visual-first; warn above 1100 unless the user asked for
   dense mode. Bullets ≤ 8 words when possible — density comes from *structure*, not
   long prose. **Prefer compact structure over prose**: if the paper contains an
   explicit objective, algorithm, theorem mechanism, or baseline comparison, extract at
   least two of: (1) empirical objective / loss stack; (2) term-by-term equation
   anatomy; (3) a method-flow strip grounded in paper variables; (4) a derived-Δ column
   for method-vs-baseline rows; (5) a 4-up implementation/theory keybox; (6) a
   claim/evidence pill table for numeric-heavy posters. **Do not invent an algorithm.**
   If the paper has only an objective, label the component "objective flow" or "loss
   anatomy", never "algorithm".
2. **Cross-model content audit** (fresh codex thread, `xhigh`): give it the content
   plan path + paper source path(s) — paths only, no summaries — and ask for a
   claim→evidence table: `| claim on poster | paper file:line | paper says (verbatim) |
   match? |` with match ∈ {OK, NUMERIC-MISMATCH, OVERCLAIM, MISSING-PRECONDITION,
   NOT-IN-PAPER, SCOPE-NARROWED}. Save to `poster_html/CLAIM_EVIDENCE.md`.
3. Fix every non-OK row or record it as a user-acknowledged tradeoff.

**🚦 Checkpoint**: content plan + audit summary. Wait.

### Phase 2 — Real paper figures (provenance-gated)

Source preference chain:
1. Paper source `figures/` (vector SVG/PDF → convert to SVG via
   `inkscape`/`pdf2svg` if available, else rasterize ≥ 2× rendered px).
2. PDF-only: `extract_pdf_figures.py contact-sheet` + `auto` to list candidate
   regions → pick crops (**🚦 human confirms crop choices**) → `crop` at 300–450 DPI.
3. Last resort: user supplies explicit `page,x0,y0,x1,y1` bboxes.

Then `preprocess_figures.py --autocrop` every asset. Every paper-derived image gets a
`FIGURE_MANIFEST.json` entry (source hash, page, bbox, dpi, sha256, natural_px) and is
embedded as `<img data-source="paper" data-asset-id="...">`.

**Hard rule**: ≥ 2 paper-derived visuals or the asset gate fails. Theory-only papers
may waive the *total-area* rule (`--waive-total-area`) at a human checkpoint — never
silently. Never draw bespoke decorative SVG "figures" as substitutes.

**Figure-area bands** (asset gate, fractions of *body*): total target **14–22 %**
(warn < 12 % / > 24 %, hard < 10 % / > 28 %); per ordinary figure target 4–8 % (warn
> 10 %, hard > 13 %); `figure--duo` combined 8–12 %. Hero templates pass `--hero`
(centerpiece may take 30–40 %). The failure mode is symmetric: too small reads as
decoration, too big crowds out content. Sibling figures that share axes or tell a
before→after story belong in one `figure--duo` card, not two cards.

### Phase 3 — Scaffold + tokens

`cp templates/<chosen>.html poster_html/poster.html`; retarget `@page` + `.poster`
dims to the venue canvas (two edits, same values); apply the chosen token pack onto the
`:root` DESIGN TOKENS block; fill content per the plan; embed manifest figures.
Run `preflight` + `style_check` — both must PASS before any layout iteration. (A fresh
scaffold is *expected* to fail `measure` — that gate judges a filled poster.)

### Phase 4 — Layout hard loop

After every layout change:

```bash
python3 "$SKILL_SCRIPTS/run_gates.py" poster_html/poster.html \
    --tokens <pack.json> --manifest poster_html/FIGURE_MANIFEST.json \
    --report poster_html/GATE_REPORT.json
```

Canonical order: preflight → style → asset → measure → polish. Targets: column-bottom
**spread < 5 px** (aim < 3), footer gap ∈ [30, 50] px, intercard gap ∈ [12, 50] px,
canvas-fill ∈ [95, 101] %, poster bbox aligned to page within ±2 px. Fix guidance for
each failure mode lives in the gate output and `templates/COMPONENTS.md`. **Do not
proceed while any hard gate fails. Do not let a reviewer see an unmeasured poster.**
Balance under-filled columns with *content from the paper* (Gate C), never with
whitespace, `space-between`, or stretched cards.

### Phase 5 — Claude visual review (gated aesthetics)

Render and read the result yourself:

```bash
python3 "$SKILL_SCRIPTS/render_preview.py" poster_html/poster.html
pdftoppm -r 100 poster_html/poster_preview.pdf poster_html/review_full -png -f 1 -l 1
# plus 2-4 region crops at higher res (header / one column / equations) via PIL
```

Score strictly 1–10. **Critical caps**: < 2 real paper figures → ≤ 3; broken canvas /
clipped content / unreadable math → ≤ 4; ≥ 4 visible hue families or gradient-heavy
header → ≤ 4; large blank cards or columns → ≤ 5; fabricated visual claim → ≤ 3.
Checks: posterly-showcase gestalt (would this hang next to a professionally designed
poster without looking like a patched dashboard?), single-accent discipline, real
figures readable and central, print hierarchy (title → headline stats → figures →
detail), column fill, **equation prominence** (no tiny math in oversized boxes),
serif-body/sans-display pairing, no gradient kitsch, component consistency, 60-second
narrative. Output format:

```
SCORE: N/10
CAPS_TRIGGERED: ...
TOP_ISSUES: (max 3)
ALLOWED_FIX_TYPE per issue: token | component | rebalance | asset | template/canvas
PATCH_LOOP_RISK: low | medium | high
```

Loop: fix (fix vocabulary below) → re-run Phase 4 gates → re-score. **≤ 3 issues per
round, ≤ 3 rounds.** Score ≥ 9 → Phase 6. Still < 9 after 3 rounds → STOP patching;
escalate to template / canvas / content re-choice (back to Phase 3) or a human
decision. Never enter round 4 of cosmetic patching.

#### Fix vocabulary (closed set — the anti-patch-loop core)

Allowed: **(a)** edit a `:root` token value; **(b)** swap/remove/add a whole component
instance from `templates/COMPONENTS.md`; **(c)** content rebalance (move a card across
columns, trim/grow text *from the paper*, resize a figure within its AR band);
**(d)** template/canvas re-choice; **(e)** global edits to an existing component's CSS
that reference only tokens; **(f)** switching predefined variants (`.eqn--large`,
`.card--compact`, `.figure--wide`, `.nowrap`, …); **(g)** asset fixes (re-crop, swap
for a clearer figure from the same paper, re-preprocess).

Forbidden: new inline styles, new hex values anywhere, bespoke decorative SVG,
per-element font-size overrides. **A new component may not be born inside the visual
loop** — stop, get a human checkpoint, add it to `COMPONENTS.md`, re-run from Phase 3.

### Phase 6 — Codex final review (fresh thread, cross-model)

All hard gates PASS + polish warnings zero-or-waived + visual ≥ 9 first. Then a fresh
codex thread (`xhigh`) reviews the **final artifacts** (not the content plan):
`poster.html`, the rendered PDF/PNG, the paper source, `GATE_REPORT.json`,
`CLAIM_EVIDENCE.md` — paths only, no executor framing. It checks: (1) fidelity &
overclaims **re-checked on final text** (polish introduces new claims), (2) residue
(`\ref{`, `TODO`, raw `<` in math, missing images, remote URLs), (3) visual rhetoric
(headline numbers prominent, banner readable from 2 m), (4) gate-log coherence. The
reviewer recommends; it does not edit. Any fix → back through Phase 4/5 gates — never
straight to re-review.

### Phase 7 — Final verification + report

```bash
python3 "$SKILL_SCRIPTS/poster_check.py" verify-final poster_html/poster_preview.pdf \
    --from-html poster_html/poster.html --max-size-mb 20
```

Page count 1, dimensions match `@page`, size ≤ 20 MB, no TODO/residue, no remote
assets. Report: PDF path, final spread px, footer-gap range, gate summary table,
unresolved waivers, codex verdict. Update `POSTER_STATE.json` → `done`.

## State persistence

`poster_html/POSTER_STATE.json`: `{phase, venue, canvas{w,h,orientation,source_url,
retrieved}, template, token_pack, design_decisions{...}, figures_selected[],
visual_rounds, codex_threads{audit, final}, status, timestamp}` — written after every
phase; enables compact-recovery resume.

## Key rules

- **Measure, don't eyeball.** No layout claim without `run_gates.py` output.
- **Gates before aesthetics.** Claude/codex review only ever sees a poster whose hard
  gates PASS. This ordering is what kills the patch-loop death spiral.
- **Never invent paper numbers or figures.** Numbers come from the paper source;
  visuals carry manifest provenance. Fabrication = critical cap ≤ 3.
- **Two hues, one system.** Accent + gold + neutrals. The style gate enforces it;
  don't negotiate with the gate.
- **Real figures are the poster.** A poster without the paper's own figures is a
  dashboard, not a poster.
- **Fix vocabulary is closed.** If a fix isn't expressible as token / component /
  rebalance / asset / canvas, it's the wrong fix.
- **Cross-model verdicts.** Claude drives the loop and scores visuals; acceptance of
  content fidelity comes from the fresh codex thread (a loop can drive, never acquit).
- **Preserve user decisions.** Re-read `design_decisions` before "improving" anything.
- **Vendor boundary.** `poster_check.py`, `render_preview.py`, `_posterly/` are
  vendored from posterly — keep diffs minimal; ARIS-side logic goes in the new
  scripts, not in vendored files.

## Review tracing

Save every codex reviewer call's trace per `shared-references/review-tracing.md` to
`.aris/traces/paper-poster-html/<date>_run<NN>/` (audit + final threads, raw responses).

## Output contract

```
poster_html/
├── poster.html              # single-file source of truth
├── poster_preview.pdf       # print-emulated, verify-final-checked
├── poster_preview.png       # thumbnail
├── POSTER_STATE.json        # resume state
├── GATE_REPORT.json         # canonical gate ledger (schema v1)
├── POSTER_CONTENT_PLAN.md   # what-goes-where + word budgets
├── CLAIM_EVIDENCE.md        # codex claim→evidence audit
├── FIGURE_MANIFEST.json     # figure provenance (sha256, page, bbox, dpi)
└── assets/{paper_figures,logos,qr,mathjax}/
```

## When NOT to use

- Slides, not a poster → `/paper-talk` / `/slides-polish`.
- The paper's headline isn't stable yet — fix the paper first; a poster amplifies
  whatever story it's given.
