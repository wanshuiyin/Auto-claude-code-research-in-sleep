# NOTICE — third-party provenance

`paper-poster-html` vendors part of **posterly** and adds ARIS-specific components on top.
This file records the vendor boundary so upstream sync stays clean and attribution is preserved.

## Vendored from posterly (MIT)

- **Upstream**: posterly — https://github.com/Chenruishuo/posterly
- **License**: MIT, © 2026 Ruishuo Chen. Full text: `LICENSES/posterly-MIT.txt`.
- **Why vendored** (DESIGN_FINAL §0): the posterly tools are copied into this skill, not pulled
  as an external dependency and not rewritten — so the skill is self-contained and the original
  measurement/render logic is preserved unchanged.

Vendored, **unmodified** components (the vendor boundary — keep diffs minimal across syncs):

| Path | Origin in posterly |
|------|--------------------|
| `scripts/poster_check.py` | `tools/poster_check.py` (measure / preflight / polish / verify-final) |
| `scripts/render_preview.py` | `tools/render_preview.py` (Playwright print render) |
| `scripts/_posterly/` | `tools/_posterly/` internal modules (measure, render, polish, preflight, canvas, verify_final, textutil) |

Vendored and **adapted** (templates):

| Path | Origin | ARIS modifications |
|------|--------|--------------------|
| `templates/landscape_4col.html` | `templates/landscape_4col_neutral.html` | flat de-gradient, `--fs-*` token scale, zero-inline-style utility classes, `data-source`/`data-color-exempt` contracts |
| `templates/landscape_hero.html` | `templates/landscape_hero_neutral.html` | (same modifications) |
| `templates/portrait_2col.html` | `templates/portrait_2col_neutral.html` | (same modifications) |

The component **class names** are inherited verbatim from posterly; the catalog in
`templates/COMPONENTS.md` therefore describes both the originals and the ARIS forks.

## ARIS-side additions (not from posterly)

These are original ARIS work, layered on top of the vendored base:

- `scripts/style_check.py` — style hard-gate, 12 rules (DESIGN_FINAL §3 / §12.5 nit 1).
- `scripts/asset_check.py` — real-figure provenance gate (DESIGN_FINAL §4).
- `scripts/run_gates.py` — runs all gates in canonical order, writes `GATE_REPORT.json`
  (DESIGN_FINAL §7).
- `scripts/extract_pdf_figures.py` — PDF → contact sheet → candidate crops (DESIGN_FINAL §4).
- `scripts/preprocess_figures.py` — autocrop / format-convert / resolution check.
- `templates/tokens/*.json` — generic + venue color packs (generic, iclr, icml, neurips, cvpr,
  acl).
- `templates/COMPONENTS.md`, `templates/README.md`, this `NOTICE.md`.
- The template modifications listed above (de-gradient, token scale, zero-inline-style
  utilities, contract attributes).

## Upstream-sync rule

When pulling new posterly releases, **preserve the vendor boundary**: re-vendor the unmodified
files (`scripts/poster_check.py`, `scripts/render_preview.py`, `scripts/_posterly/`) as drop-in
replacements, and re-apply the documented template adaptations on top of the new neutral
templates. Do **not** fold ARIS additions into the vendored files — keep `style_check.py`,
`asset_check.py`, `run_gates.py`, `extract_pdf_figures.py`, `preprocess_figures.py`, the token
packs, and the docs as separate ARIS-owned files so the posterly diff stays clean and
re-syncable.
