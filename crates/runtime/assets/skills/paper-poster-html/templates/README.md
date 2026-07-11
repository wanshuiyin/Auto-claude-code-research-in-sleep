# Template gallery — paper-poster-html

Three neutral HTML scaffolds, forked from the posterly templates (MIT, © 2026 Ruishuo Chen —
see `../NOTICE.md`) and adapted for ARIS: flat de-gradient, `--fs-*` token scale, zero
inline-style utility classes, and the `data-source` / `data-color-exempt` contracts. Class
names are unchanged, so `COMPONENTS.md` (the component contract catalog) applies to all three.

Each template is **self-contained and neutral**: no lab branding, no paper content — only
`TODO` placeholders. The authoring loop is: copy one to your working dir as `poster.html` →
apply a token pack → fill `TODO`s with paper content + real figures → run the gates
(`run_gates.py`) and balance until they pass.

Every layout-critical element carries `data-measure-role` so the measurement gate can locate
columns / hero / footer regions across templates. **Do not remove these attributes** — the
measure gate depends on them.

## Picking a template

| Template | Canvas | Layout | Use when |
|----------|--------|--------|----------|
| **landscape_4col.html** | 60 × 36 in landscape | header → optional banner → **4 columns** → optional takeaways → footer | The default. Standard ML conference poster (ICML / NeurIPS / generic landscape) with ~3–5 content cards per column; mix of figures, equations, and tables. |
| **landscape_hero.html** | 60 × 36 in landscape | header → **hero panel (~60%)** + supporting column (~40%) → takeaways → footer | ONE figure / table / system diagram is the main message. One big illustration left, 3–4 short cards right. No framework banner — the hero *is* the banner. |
| **portrait_2col.html** | 24 × 36 in portrait | header → **2 columns** → footer (no banner, no takeaways strip) | Portrait venues / sub-A0 sizes. Vertical space is precious, so banner + takeaways are dropped; the final card in the right column carries the conclusion/takeaways. |

(File names follow DESIGN_FINAL §1: the ARIS forks drop the posterly `_neutral` suffix.)

## Scaffolds, not finished posters

A template is a **scaffold**, not a poster. Figures are commented out and copy is `TODO`
stubs, so each column only fills the top of the canvas. That has gate consequences you should
expect — do not "fix" them on a fresh scaffold:

- **`preflight` passes out of the box.** It checks structure (valid `data-measure-role` values,
  no LaTeX residue, no bare `<` inside `$…$` math, the root `data-measure-role="poster"`),
  which the scaffold already satisfies.
- **`style_check` source rules (1–3, 5–11) pass on the *forked* scaffold.** The ARIS fork has
  no inline styles, no `linear-gradient`, no stray hex outside the token block — so the static
  source gate is green on the empty template. (The upstream posterly *originals* keep inline
  styles and would FAIL `style_check` — that is expected; the fork exists precisely to fix
  that.)
- **`measure` and `polish` are gates for your *finished* poster.** They check that columns
  bottom-align to within 5 px, that the gap to the footer sits in a tight band (30–50), that
  intercard gaps stay in [12, 50], and that the canvas fills 95–101% — properties only a
  *filled* poster can have. An unfilled scaffold is **expected to fail them** (huge
  column-bottom spread, a large gap to the footer). That is the gate telling you the poster is
  not finished, not a bug in the template.
- **`asset_check` fails until you embed ≥2 real paper figures.** A scaffold has none.

So the loop is: copy → apply token pack → fill content + drop in real figures → run
`run_gates.py` and balance until `measure`/`polish`/`asset` go green. See DESIGN_FINAL §8 for
the full phase structure and the worked ICLR 2026 acceptance case (§13).

## Applying a token pack (`tokens/*.json` → `:root`)

The palette lives in two synchronized places: the `tokens/*.json` packs (machine-readable, what
`style_check`/`run_gates` read for the accent/gold `hue_centers`) and the `:root` DESIGN TOKENS
block in each template's `<style>` (what the browser renders). **`generic.json` is the default
for every venue.** Venue packs are opt-in (`— venue-colors: true`).

To apply a pack, **manually copy its values** into the template's `:root` token block (the
block fenced by `/* ===== DESIGN TOKENS ===== */` … `/* ===== END DESIGN TOKENS ===== */` —
`style_check` locates the token block by exactly this comment pair, so keep it intact). The
JSON-to-CSS field mapping:

| JSON path | CSS token |
|-----------|-----------|
| `accent.base` | `--accent` |
| `accent.deep` | `--accent-deep` |
| `accent.light` | `--accent-light` |
| `accent.soft` | `--accent-soft` |
| `gold.base` | `--gold` |
| `gold.soft` | `--gold-soft` |
| `neutrals.text_primary / text_secondary / text_muted` | `--text-primary / --text-secondary / --text-muted` |
| `neutrals.bg_page / bg_card / bg_card_tint` | `--bg-page / --bg-card / --bg-card-tint` |
| `neutrals.border_soft` | `--border-soft` |

`--bg-emphasis: var(--accent-light)` and `--border-strong: var(--accent)` are *derived* tokens —
leave them as `var(--…)` references; they follow the accent automatically.

When you pass a pack to the gates (`run_gates.py --tokens tokens/<venue>.json`,
`style_check.py --tokens …`), the `hue_centers` in the JSON are the source of truth for the
hue-cluster check (style rule 4): the two allowed non-neutral hue families are
`hue_centers.accent ± 22°` and `hue_centers.gold ± 22°`. If you copied the JSON values into
`:root` correctly, the rendered hues will land inside those windows. (If you omit `--tokens`,
`style_check` derives the centers from the `:root` `--accent` / `--gold` instead.)

Available packs (all share the generic gold family `#C9A24A` / `#FFF7E0`; all venue accents
satisfy S ≤ 0.55, L ∈ [0.25, 0.45], hue ∉ [250, 285]):

| Pack | Accent identity | accent hue center |
|------|-----------------|-------------------|
| `generic.json` | slate-blue `#2D5F8B` (the default for every venue) | 210 |
| `iclr.json` | deep green `#2E6048` | 151 |
| `icml.json` | deep maroon `#8B3A4A` | 348 |
| `neurips.json` | steel/slate blue `#3A5A7A` | 210 |
| `cvpr.json` | deep azure/indigo `#27407A` | 222 |
| `acl.json` | deep teal `#256E72` | 183 |

Venue packs are *opt-in identity*, not a license to deviate from the discipline: a single
accent family + the shared gold, deep and desaturated, never purple. The default text
`venue-badge` (COMPONENTS.md) is the primary venue cue; the color pack is secondary.

## Retargeting the canvas

A template ships with a default `@page` size and a matching `.poster` size. To change the
canvas you must edit **both** in the template (each in exactly one place), keeping them
identical — `measure`'s canvas-fill / position-align gate compares the rendered `.poster`
bounding box against the `@page` viewport, so a mismatch fails the gate.

1. **`@page`** in the `<style>` block — e.g. `@page { size: 185cm 90cm; margin: 0; }`.
2. **`.poster` print dimensions** in `@media print { .poster { … width: 185cm; height: 90cm; } }`.
   (The screen `.poster` uses `calc(N * var(--u))` with `--u: 1.6px`; print uses `--u: 1mm`, so
   the screen preview scales automatically — you only hardcode the print `width`/`height`.)

The canvas parser accepts `in` / `mm` / `cm` / `pt` units. **ICLR 2026 main conference example**
(the §13 acceptance case): the official print service spec is **185 × 90 cm landscape**, so
start from `landscape_4col.html` and set both `@page` and the print `.poster` to
`185cm 90cm` / `width: 185cm; height: 90cm;`.

Safe-area / margin design belongs as **internal padding on a full-bleed `.poster`**, never as a
smaller poster — a smaller poster fails the position-align gate (the `.poster` bbox must align
to `(0,0)`–`(viewport_w, viewport_h)`).

## Zero inline-style + utility-class policy

The templates and any finished poster carry **no** `style=` attribute (zero tolerance —
`style_check` rule 2; IMPLEMENTATION_CONVENTIONS §B). To make that possible the templates ship
their own **utility classes** in the `<style>` block, replacing every inline style the posterly
originals used:

```
.fs-1 … .fs-9        font-size: var(--fs-N)
.mt-1 … .mt-6        margin-top: calc(N * var(--u))
.mb-1 … .mb-4        margin-bottom: calc(N * var(--u))
.w-45 .w-50 … .w-100 figure <img> width 45%…100% (5% steps)
.text-secondary .text-muted .nowrap .text-center
```

The **only** sanctioned `style=` survivors:

- the internal markup of a `data-color-exempt="logo"` element (a logo / seal SVG), and
- `style="width: NN%"` on a `data-source="paper"` `<img>` for aspect-ratio width tuning when the
  value is off the 5% grid (prefer the `.w-NN` class when it lands on a step).

Likewise: **no `linear-gradient` anywhere**; the only gradient allowed is the `.poster`
background `radial-gradient` tint with all color stops at alpha ≤ 0.06 (style rule 5). All
font-sizes go through the `--fs-*` scale; `calc(var(--fs-N) * k)` is allowed **only** for the
predefined component variants catalogued in `COMPONENTS.md` (e.g. `.eqn--large`). All colors
are tokens — no hex literal outside the `:root` token block (and the exempted logo SVG).

## Adding a new template

A new template **MUST**:

1. Set `@page { size: <W> <H> }` (`in` / `mm` / `cm` / `pt`) inside a `<style>` block — the
   canvas parser fails if absent — and a matching print `.poster` size.
2. Carry `data-measure-role="poster"` on the root poster element.
3. Use the roles consistently: `header`, `banner` (optional), `body`, `column`, `card`,
   `hero` (mutually exclusive with `banner`), `footer-strip` (optional), `footer`.
4. Use the `--u` unit system (`1.6px` screen, `1mm` print) for ALL sizing via
   `calc(N * var(--u))` — never bare px except hairlines (≤ 2px).
5. Carry the `:root` DESIGN TOKENS block fenced by the
   `/* ===== DESIGN TOKENS ===== */` … `/* ===== END DESIGN TOKENS ===== */` comment pair,
   the full `--fs-1 … --fs-9` scale, and the §B utility classes.
6. Use **only** components from `COMPONENTS.md`; no inline `style=`, no `linear-gradient`,
   no hex outside the token block.
7. Keep all paper-specific content as `TODO` placeholders — neutral templates only.

Then add a row to the gallery table above, a catalog note if it introduces any new component
(which requires the COMPONENTS.md new-component checkpoint), and link it in `SKILL.md` Phase 3.
