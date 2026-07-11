# Component contract catalog

This is the **authoritative component set** for `paper-poster-html`. The visual-审 loop
(DESIGN_FINAL.md §5, Phase 5) and the fix vocabulary (DESIGN_FINAL.md §10) may only
touch components listed here. A component that is not in this catalog **does not exist**
as far as the loop is concerned: see [New components require a checkpoint](#new-components-require-a-human-checkpoint).

Why this file is load-bearing: the anti-pattern loop in poster authoring is "agent invents a
new visual element to fix one issue, the element brings its own hex / inline style / extra hue,
the next gate flags *that*, the agent invents another element…". Pinning the component set turns
every fix into a bounded edit (swap a known component, flip a known variant, retune a token)
instead of unbounded markup invention. COMPONENTS.md is what makes fix vocabulary item (b)
("whole-instance swap/add/delete, component set drawn from COMPONENTS.md") well-defined.

The component classes are inherited verbatim from the posterly templates (MIT, © 2026 Ruishuo
Chen — see `../NOTICE.md`); the ARIS fork only de-gradients them, tokenizes their colors/sizes,
and strips inline `style=`. Class names did not change, so this catalog applies to both the
posterly originals and the ARIS forks.

---

## How to read each entry

| Field | Meaning |
|-------|---------|
| **Purpose** | The single job this component does. If your content needs a different job, you need a *different* component, not a restyled one. |
| **Allowed variants** | Predefined modifier classes only. Adding an undeclared variant = fix-vocabulary violation. |
| **Required data attributes** | Attributes a gate keys off. Omitting them breaks a gate (usually `measure` or `asset_check`). |
| **Token usage** | Which `--*` tokens the component's CSS references. Component CSS may **only** name colors via `var(--…)` (style_check rule 3). |
| **Inspected by** | Which gate(s) read this component. Tells you which gate a bad edit will trip. |
| **Allowed fix operations** | Subset of DESIGN_FINAL §10 letters `(a)–(g)` legal on this component. |
| **Anti-patterns** | Specific things the loop has been caught doing. Each maps to a HARD style/asset rule or a rubric cap. |

Gate name shorthand (DESIGN_FINAL §3–§7):
`preflight` (structure), `style` (`style_check.py`, 12 rules), `asset` (`asset_check.py`),
`measure` (`poster_check.py measure`, column/footer/canvas geometry),
`polish` (`poster_check.py polish`, figure-AR / orphan / whitespace).

---

## card

- **Purpose**: The atomic content unit inside a column — holds one section's prose, list,
  figure, equation, table, or callout. Everything in the body lives in a card.
- **Allowed variants**: `.card.highlight` (accent left-bar + tinted emphasis, for the most
  important card in a column), `.card.tinted` (subtle `--bg-card-tint` fill), `.card--compact`
  (predefined tighter padding variant — fix vocabulary (f)). No other modifiers.
- **Required data attributes**: `data-measure-role="card"` (every card; `measure` aligns card
  bottoms across columns using this).
- **Token usage**: `--bg-card`, `--bg-card-tint`, `--bg-emphasis`, `--accent` (highlight
  left-bar / border-strong), `--border-soft`, `--text-primary`. Shadow uses a token-derived
  rgba allowed by style rule 5 only at alpha ≤ 0.06.
- **Inspected by**: `measure` (card-bottom spread < 5px, intercard gap 12–50, no half-empty
  card), `preflight` (valid role), `style` (no inline style, colors via var).
- **Allowed fix operations**: (a) token retune, (b) move/add/delete a whole card across columns,
  (c) content rebalance inside the card, (e) global card stylesheet change (tokens only),
  (f) switch to `.card--compact` / `.card.highlight` / `.card.tinted`.
- **Anti-patterns**: inline `style="background:#…"` on a card to "make it pop" (style rule 1/2);
  padding a card with blank lines to fill column height instead of moving content (measure
  intercard-gap WARN, rubric "half-empty card" cap ≤5); a fourth highlight per column (dilutes
  the single-accent discipline, rubric ≤4 if it adds a hue family).

## numbered-card (`.card` + `.section-title` with `.num`)

- **Purpose**: A `card` whose header is a numbered section title — the standard reading order
  cue ("1 Motivation", "2 Method"…). Not a separate element: it is `.card` containing
  `<div class="section-title"><span class="num">N</span> Title</div>`.
- **Allowed variants**: inherits all `card` variants. The `.section-title` may carry a small
  inline gold "★ KEY" marker **only** via the predefined `.keyword-gold` class (never an inline
  `style="color:…"` — the posterly originals did this; the ARIS fork replaces it with the class).
- **Required data attributes**: same as `card` (`data-measure-role="card"`). The number itself
  carries no data attribute.
- **Token usage**: `.section-title` → `--accent-deep` (text), `--font-sans`; `.num` →
  `--accent` background, white text. Font-size via `--fs-7` (section title) and `--fs-5` (.num).
- **Inspected by**: `measure`, `preflight`, `style` (font pairing rule 6 — section title must be
  the sans stack; rule 8 — font-size via `--fs-*`).
- **Allowed fix operations**: (a), (b), (c), (e), (f). Renumbering is content rebalance (c).
- **Anti-patterns**: section title rendered in the serif body stack (rule 6 HARD); a per-title
  font-size override in px (rule 8 HARD); decorative inline SVG icon next to the number instead
  of the `.num` circle (rule 11 HARD — no homemade decorative SVG).

## figure-card (`.card` containing `.figure`)

- **Purpose**: A card whose payload is a paper figure: `.figure > img + .caption`. The primary
  carrier of real, paper-sourced images (the thing `asset_check` exists to enforce).
- **Allowed variants**: `.figure--wide` (predefined, image spans full card width — fix (f));
  the `<img>` width is set with the utility classes `.w-45 … .w-100` (5% steps), never inline,
  **except** the one sanctioned inline exception below.
- **Required data attributes**:
  - On the `<img>`: `data-source="paper"` **and** `data-asset-id="<manifest id>"` (both HARD,
    style rule 10 + asset_check). The asset id must exist in `FIGURE_MANIFEST.json` with
    `from_paper:true`.
  - Optional `data-fig-layout="beside-text"` on the `<img>` to opt the figure out of the
    AR-width gate when it legitimately shares its card with a meaningful text column
    (DESIGN_FINAL §10 (g) territory; polish honors it).
  - Sanctioned inline style: `data-source="paper"` `<img>` may carry **only**
    `style="width: NN%"` for aspect-ratio width tuning (B-contract exception); prefer the
    `.w-NN` utility class when the value lands on a 5% step.
- **Token usage**: `.figure img` border → `--border-soft`; `.caption` → `--text-secondary`,
  `--accent-deep` (caption `<strong>`); caption font-size `--fs-3`/`--fs-2`.
- **Inspected by**: `asset` (≥2 paper figures, per-figure area ≥1.5% poster, total ≥12% body,
  natural_px ≥1.5× rendered, manifest fields + sha256), `polish` (figure AR sizing:
  FIG/WIDE / FIG/SQUARE / FIG/TALL / FIG/BROKEN), `style` (rule 10 contract attrs; rule 4
  exempts paper images from hue clustering), `measure` (card geometry).
- **Allowed fix operations**: (c) AR-bandwidth width adjust, (f) `.figure--wide`, (g) asset fix
  (re-crop, swap for a sharper figure from the *same* paper, re-run preprocess). Width changes
  via `.w-NN` utility (b/e) or the sanctioned `style="width:NN%"`.
- **Anti-patterns**: `<img>` without `data-source`/`data-asset-id` (rule 10 HARD; also invisible
  to asset_check so it doesn't count toward the ≥2 quota); a wide figure shrunk into a gray
  margin below 65% width (polish FIG/WIDE); a low-res crop where natural_px < 1.5× rendered
  (asset WARN→FAIL); fabricating/“illustrating” a figure not in the paper (rubric ≤3 cap,
  manifest `from_paper` must be false → fails the paper-figure quota).

## hero-figure (`.hero` + `.hero-stage` > img, `landscape_hero` template only)

- **Purpose**: The single dominant visual on the hero template — one large figure / system
  diagram / table that *is* the poster's message. Replaces the framework banner.
- **Allowed variants**: optional `.hero-caption` and one optional `.hero-aside` text block; a
  `.stage-placeholder` is shown only while authoring (must be removed once the real img drops
  in). The hero `<img>` has **no border** (the `.hero-stage` frames it).
- **Required data attributes**: `data-measure-role="hero"` on the `.hero` panel (mutually
  exclusive with `data-measure-role="banner"`). The hero `<img>` carries the same
  `data-source="paper"` + `data-asset-id` contract as any paper figure (asset_check probes the
  hero centerpiece too — the worst image to silently lose).
- **Token usage**: `--bg-card`, `--border-soft`, `--accent` (8u left-bar), `--bg-card-tint`
  (stage gradient → flattened in the ARIS fork), `--bg-emphasis` (`.hero-aside`). Section title
  font-size `calc(var(--fs-7) * …)` is a predefined hero variant (rule 8 calc exception).
- **Inspected by**: `asset` (counts as a paper figure; FIG/BROKEN on the hero img is fatal),
  `polish` (hero img BROKEN check), `measure` (hero bottom must bottom-align with the supporting
  column's last card, spread < 5px), `preflight`, `style`.
- **Allowed fix operations**: (c), (d) (switch templates if hero is the wrong frame),
  (f) hero variants, (g) asset fix.
- **Anti-patterns**: padding the hero with empty space to fill the row (rubric "large empty
  card/column" ≤5 cap; measure spread); putting a border on the hero img; leaving the
  `.stage-placeholder` in the final poster (preflight/polish residue); a hero img that is not
  paper-sourced (asset quota + rubric ≤3).

## eqn (`.eqn`, optional `.eqn .label`)

- **Purpose**: A display-equation block — MathJax-rendered math with an optional uppercase label
  ("CORE EQUATION"). The only sanctioned home for math.
- **Allowed variants**: `.eqn--large` (predefined `font-size: calc(var(--fs-5) * 1.25)` — the
  one calc-on-token variant blessed by IMPLEMENTATION_CONVENTIONS §E.9 and style rule 8/§12.5
  nit 1). No other size variant.
- **Required data attributes**: none. (Math is found by gate via the rendered MathJax SVG, not a
  data attribute.)
- **Token usage**: `--bg-emphasis` (block fill, flat in the fork), `--accent` (3u left-bar),
  `--accent` (`.label` text), `--font-sans` (label). Block font-size `--fs-5`.
- **Inspected by**: equation gate (DESIGN_FINAL §5): `EQN/BROKEN` (MathJax did not render) =
  HARD; `EQN/UNDERSIZED` (inner box > 80px tall but math bbox < 15% area) = HARD, < 25% or
  bottom whitespace > 35% = WARN. Also `preflight` (bare `<` inside `$…$`, LaTeX residue),
  `style` (label is sans, size via `--fs-*`).
- **Allowed fix operations**: (a) token retune, (c) shorten/split the equation (content
  rebalance), (f) `.eqn--large` to fill an undersized box, (e) global eqn stylesheet (tokens).
- **Anti-patterns**: raw `<` inside math (preflight — MathJax parses it as an HTML tag);
  embedding the equation as a screenshot image instead of MathJax (defeats EQN gate, inflates
  PDF, fails the "real text" expectation); a per-equation px font-size override (rule 8 HARD);
  an `.eqn` box left mostly empty (EQN/UNDERSIZED).

## callout (`.callout`, variant `.callout.gold`)

- **Purpose**: An accent-filled emphasis strip for a question, theorem, or one-line takeaway —
  the "read this even if you read nothing else" line inside a card.
- **Allowed variants**: `.callout` (solid `--accent`, white text, `<strong>` in gold) and
  `.callout.gold` (solid `--gold`, `--accent-deep` text — the ARIS fork flattens the original
  gold *gradient* to a flat fill per §E.2). No third variant.
- **Required data attributes**: none.
- **Token usage**: `.callout` → `--accent` bg, white text, `--gold` (`<strong>`); `.callout.gold`
  → `--gold` bg, `--accent-deep` text. Font-size `--fs-4`.
- **Inspected by**: `style` (rule 5 — `.callout.gold` must be a flat fill, no `linear-gradient`;
  rule 4 — its accent/gold are the two allowed hue families; rule 1/3 — colors via var),
  `measure` (counts toward card height).
- **Allowed fix operations**: (a), (b) add/remove a callout instance, (c) reword from paper
  source, (f) toggle `.callout` ↔ `.callout.gold`.
- **Anti-patterns**: `linear-gradient` fill (rule 5 HARD — this is the single most common
  de-gradient regression); a third color on a callout (rule 4 — >2 hue clusters); using a
  callout to introduce a claim not in the paper (Phase 6 final-HTML overclaim audit).

## result-table (`table.result-table`)

- **Purpose**: A benchmark / comparison table with the "ours" row highlighted in gold and group
  rows / best cells marked. The quantitative payload of a results card.
- **Allowed variants**: row classes `tr.group-row` (section divider row), `tr.ours` (gold
  highlight for our method), cell classes `.method` (left-aligned method name), `.best`
  (accent-colored winning number). These are the defined row/cell modifiers — no others.
- **Required data attributes**: none (it lives inside a `card` which carries the measure role).
- **Token usage**: `thead th` → `--accent` bg / white; `tr.group-row td` → `--bg-emphasis`,
  `--accent-deep`, `--accent` bottom border; `tr.ours td` → `--gold-soft`; `.best` → `--accent`;
  borders → `--border-soft`. Font is the **sans** stack (tables/headers are sans per rule 6),
  size `--fs-3`/`--fs-2`.
- **Inspected by**: `style` (rule 6 — table uses sans; rule 4 — gold-soft + accent are within
  the two hue families; rule 8 — sizes via token), `measure` (height in card), `preflight`.
- **Allowed fix operations**: (a), (c) add/remove rows or edit numbers from the paper/results
  (content rebalance), (e) global table stylesheet (tokens). Switching which row is `.ours` is (c).
- **Anti-patterns**: per-cell inline `style="color:#888"` for the reference row (the posterly
  originals did this; the ARIS fork replaces with `.text-muted`) — rule 2 HARD; numbers that do
  not match the paper/results files (Phase 1 claim→evidence audit + Phase 6); a third highlight
  color beyond gold-soft/accent (rule 4).

## keybox (`.keybox` > `.kb-item` × N)

- **Purpose**: A compact 2–4-up strip of headline statistics ("3.2× faster", "92% acc"),
  each a big number over a small caption. The at-a-glance numeric hook.
- **Allowed variants**: count is set by content (2–4 items); no separate variant classes.
  Each item is `.kb-item > .kb-num + .kb-label`.
- **Required data attributes**: none.
- **Token usage**: `.kb-item` → `--bg-emphasis` bg, `--accent` top-border; `.kb-num` →
  `--accent` (`--fs-6`, sans); `.kb-label` → `--text-secondary` (`--fs-1`, sans).
- **Inspected by**: `style` (rule 6 sans, rule 8 token sizes, rule 4 single accent family),
  `polish` (Gate B typography orphans — a trailing `↑ × % ↓` glyph on `.kb-num` that could wrap
  alone must carry `.nowrap`), `measure`.
- **Allowed fix operations**: (a), (b) add/remove the strip, (c) edit stats from results,
  (f) `.nowrap` on an orphan-prone number.
- **Anti-patterns**: a lone trailing glyph wrapping to its own line (polish Gate B → add
  `.nowrap`); fabricated stats (claim audit); a per-number color/size override (rules 8/4).

## takeaways-strip (`.takeaways-strip`, landscape templates)

- **Purpose**: A full-width bottom strip of 3–4 one-line takeaways ("Idea / Method / Result /
  Practical") — the 60-second narrative exit. Portrait templates drop it (final card carries
  the conclusion instead).
- **Allowed variants**: title via `.ts-title` (+ `.num` circle), items via `.ts-item` >
  `.ts-key` + `.ts-text`. Item count 3–4. No other variant.
- **Required data attributes**: `data-measure-role="footer-strip"` (measure positions it between
  body and footer; footer-gap band 30–50 is measured to this strip when present).
- **Token usage**: `--bg-emphasis` (strip bg — flattened from the posterly gradient per §E.2),
  `--border-soft`, `--accent`/`--accent-deep` (title, `.num`, item left-bar, `.ts-key`),
  `--font-sans` (keys), `--font-serif` (text). Sizes `--fs-6`/`--fs-4`/`--fs-3`.
- **Inspected by**: `measure` (footer-gap band, full-width span), `style` (rule 5 — strip bg
  must be flat, rule 6 font pairing), `preflight`.
- **Allowed fix operations**: (a), (b) add/remove the whole strip, (c) reword takeaways from the
  paper, (e) global strip stylesheet (tokens).
- **Anti-patterns**: `linear-gradient` strip background (rule 5 HARD — the de-gradient target);
  using it on a portrait template where it competes for scarce vertical space (use the final
  conclusion card instead); inventing a takeaway not supported by the poster body (Phase 6).

## qr-block (`.qr-block` > img + `.qr-label`)

- **Purpose**: A scannable QR pointing at the paper / arXiv / code / project page, with a small
  label. Lives in the header right-block.
- **Allowed variants**: none. The img is either a **local raster** QR or, as a last-resort
  authoring placeholder, an inline SVG QR (one of the two sanctioned inline-SVG uses).
- **Required data attributes**: none for the raster QR. If the QR is the inline-SVG fallback, it
  is exempt from hue clustering (rule 4 exempts QR) but must still be a **local** asset in the
  final poster.
- **Token usage**: `--accent` (border), white background, `--accent` (`.qr-label`, sans).
- **Inspected by**: `style` (rule 4 QR exemption; rule 11 — inline SVG allowed only for
  logo / QR fallback / catalogued structural diagram), `preflight` (no remote `src` — a remote
  QR-service URL hangs `measure`'s networkidle wait and link-rots), verify-final (no remote
  asset, ≤20MB).
- **Allowed fix operations**: (a) token retune (border color), (g) asset fix (regenerate the QR
  locally at ≥2× rendered px).
- **Anti-patterns**: a remote QR-service `src` (preflight/verify-final — networkidle hang +
  link rot); a homemade decorative SVG that is not actually a QR (rule 11); a blurry QR below
  2× rendered px (asset/polish).

## venue-badge (`.venue-badge`, default text identity)

- **Purpose**: The default, logo-free venue identity in the header left slot — venue / year /
  "POSTER" tag as text. ARIS default is a **text** badge (DESIGN_FINAL §2: "venue identity
  默认文字 badge"); a venue logo is opt-in and goes in `.logo-slot`, not here.
- **Allowed variants**: `.vb-venue`, `.vb-year`, `.vb-tag` sub-lines. No image variant — if the
  venue permits a logo, use `.logo-slot` with the logo contract instead.
- **Required data attributes**: none. (If ever replaced by a logo SVG, that SVG needs
  `data-color-exempt="logo"` — but that is the `.logo-slot` path, not the badge.)
- **Token usage**: `--accent-deep` (`.vb-venue`), `--text-secondary` (`.vb-year`), `--accent`
  (`.vb-tag`), `--border-soft` (right divider), `--font-sans`. Sizes `--fs-9`/`--fs-5`/`--fs-1`.
- **Inspected by**: `style` (rule 6 sans, rule 8 token sizes, rule 1 colors as tokens),
  `measure` (header geometry), `preflight`.
- **Allowed fix operations**: (a), (c) edit venue/year text. Switching to a logo is a (b)
  component swap into `.logo-slot` (requires the logo contract, see below).
- **Anti-patterns**: hardcoding a venue's brand hex inline to "match their logo" (rule 1/2 HARD —
  venue color comes from the opt-in token pack, not inline hex); putting a raster logo inside
  the badge without the `.logo-slot` `data-color-exempt` path (rule 1 — un-exempted foreign
  colors trip hue clustering).

## logo-slot (`.logo-slot` > img/svg, optional)

- **Purpose**: Optional lab/affiliation logo in the header right-block. The **only** place an
  off-palette color is allowed, via explicit exemption.
- **Allowed variants**: a raster `<img>` logo, or an inline `<svg>` logo. Either way the logo
  must be height-matched to the QR (~85u) so the header does not grow.
- **Required data attributes**: `data-color-exempt="logo"` on the logo element (HARD, style
  rule 1 + rule 11) — this is what tells `style_check` the foreign colors inside are sanctioned.
  Inline SVG logos are one of the two sanctioned inline-SVG uses (rule 11).
- **Token usage**: container only (`--border-soft` if framed); the logo's own colors are exempt.
- **Inspected by**: `style` (rule 1 exemption, rule 2 inline-style exemption for the logo SVG's
  internal markup, rule 11 inline-SVG allowance), `measure` (header geometry).
- **Allowed fix operations**: (b) add/remove the slot, (g) asset fix (swap logo file). Resizing
  via height utility, not inline.
- **Anti-patterns**: a logo *without* `data-color-exempt="logo"` (rule 1 — its colors leak into
  hue clustering, rule 4 fails); an empty `.logo-slot` left in place (adds a stray gap — delete
  the whole div instead); using the exemption to smuggle general decorative color (rule 1 intent
  — exemption is for the logo/seal only).

## footer (`.footer`, role `footer`)

- **Purpose**: The bottom info bar — method name, venue·year, acknowledgements, code repo,
  contact. Closes the poster.
- **Allowed variants**: `.footer .repo` (accent-colored repo/contact spans). No others.
- **Required data attributes**: `data-measure-role="footer"` (measure anchors the footer gap to
  this).
- **Token usage**: `--text-muted` (body), `--accent` (`.repo`), `--accent-deep` (method name),
  `--border-soft` (top border), `--font-sans`. Size `--fs-5`.
- **Inspected by**: `measure` (footer gap to body/takeaways 30–50, full-width span), `style`
  (rule 6 sans, rule 1 colors-as-tokens), `preflight`.
- **Allowed fix operations**: (a), (c) edit footer text, (e) global footer stylesheet (tokens).
- **Anti-patterns**: inline `style="color:var(--accent-deep)"` on the method name (the posterly
  original did this — the fork uses `.text-accent-deep` / a class; rule 2 forbids inline style);
  a remote contact-tracking pixel or remote asset in the footer (verify-final).

---

## Utility classes (the zero-inline-style layer)

These exist so the templates carry **no** `style=` attribute (IMPLEMENTATION_CONVENTIONS §B —
zero-tolerance). They are not "components" but the loop uses them under fix vocabulary (f). They
are catalogued here so style_check rule 2 (no inline style) has a sanctioned alternative for
every former inline use.

| Class group | Effect | Replaces former inline |
|-------------|--------|------------------------|
| `.fs-1 … .fs-9` | `font-size: var(--fs-N)` | `style="font-size: calc(N * var(--u))"` |
| `.mt-1 … .mt-6` | `margin-top: calc(N * var(--u))` | `style="margin-top: …"` |
| `.mb-1 … .mb-4` | `margin-bottom: calc(N * var(--u))` | `style="margin-bottom: …"` |
| `.w-45 … .w-100` (5% steps) | figure `<img>` width | `style="width: NN%"` |
| `.text-secondary` `.text-muted` | secondary/muted text color tokens | `style="color:#888"` |
| `.nowrap` | `white-space: nowrap` | orphan-glyph guard (polish Gate B) |
| `.text-center` | `text-align: center` | `style="text-align:center"` |

The **only** sanctioned `style=` survivors (IMPLEMENTATION_CONVENTIONS §B): the internal markup
of a `data-color-exempt="logo"` element, and `style="width: NN%"` on a `data-source="paper"`
`<img>` (AR width tuning when the value is off the 5% grid).

---

## Fix vocabulary (DESIGN_FINAL §10)

Inside the Phase 5 visual loop, **only** these operations are allowed. Every entry above maps
its "Allowed fix operations" to these letters.

| ID | Operation | Constraint |
|----|-----------|------------|
| **(a)** | Change a `:root` **token value** | Token names fixed by IMPLEMENTATION_CONVENTIONS §A; no new tokens, no new hex outside the token block. |
| **(b)** | Swap / delete / add a **whole component instance** | Component must be in this catalog. |
| **(c)** | **Content rebalance** | Move a card across columns; add/remove paper-sourced text; adjust a figure width within the AR gate's band. |
| **(d)** | **Canvas / template reselect** | The upgrade path — pick a different template or retarget the canvas (README §"Retargeting"). |
| **(e)** | Global **component stylesheet** change | May reference tokens only; **no new hex**. |
| **(f)** | Toggle a **predefined variant** | `.figure--wide`, `.card--compact`, `.eqn--large`, `.nowrap`, `.callout.gold`, etc. — must already be in this catalog. |
| **(g)** | **Asset fix** | Re-crop, swap for a sharper figure from the *same* paper, re-run `preprocess_figures.py`. |

**Forbidden inside the loop** (DESIGN_FINAL §10, last paragraph): new inline `style=`,
new hex literal, homemade decorative SVG, single-element font-size override.

---

## New components require a human checkpoint

If a fix genuinely needs a component that is **not** in this catalog, the loop **must stop**.
A new component cannot be born inside the Phase 5 visual loop (DESIGN_FINAL §10).

The procedure (DESIGN_FINAL §10, final paragraph):

1. **Stop** the visual loop. Do not improvise the element inline.
2. **Human checkpoint (🚦)** — get explicit human approval for the new component.
3. **Add a catalog entry** here in COMPONENTS.md with all seven fields (purpose / variants /
   data attributes / token usage / inspected-by / allowed fix ops / anti-patterns), and add its
   tokenized CSS to the template stylesheet (colors via `var(--…)` only, sizes via `--fs-*`).
4. **Re-run from Phase 3** (scaffold + token patch), so the new component passes `preflight` +
   `style` from a clean state before re-entering the layout/visual loop. You may not splice a
   new component into a mid-loop poster and keep going.

This is what keeps the fix loop bounded: the component set is closed during the loop, and only
a human-gated, catalogued, re-run-from-Phase-3 step can extend it.

---

## Density components (added 2026-06-05, codex-converged; user-checkpointed)

> **Shared guardrail (all components below): no component-local color semantics.**
> Semantic distinction must be conveyed by labels, order, typography, and FACT/DERIVED
> text — never by new hues. Every CSS declaration references `--accent`/`--gold`/neutral
> tokens only. This is what keeps a dense poster from regressing into the 30-color
> "patched dashboard" failure class.

### `equation-stack`
- **Purpose**: 2–4 compact formula rows (e.g. population objective + empirical loss) —
  denser than stacking full-margin `.eqn` blocks.
- **Variants**: none. **Data attributes**: none.
- **Tokens**: inherits `.eqn` tokens; tightened margins/padding only.
- **Inspected by**: style (rule 8 via `.eqn`), measure (height), EQN gates.
- **Allowed fix ops**: rebalance (move rows between stack and prose); variant via `.eqn--large` on one row.
- **Anti-patterns**: >4 rows (split into two cards); mixing unrelated equations.

### `eqn-anatomy` (+ `eqn-anatomy--row`)
- **Purpose**: term-by-term anatomy of ONE displayed equation: each `.ea-item` = a pill
  `.ea-tag` (term name) + one-line explanation. 2×2 grid default; `--row` = 1×4.
- **Tokens**: accent family only (tint bg, accent left bar, accent-light tag).
- **Inspected by**: style rule 4 (all tags accent), measure.
- **Allowed fix ops**: token edits; 2×2 ↔ 1×4 variant swap; rebalance text.
- **Anti-patterns**: per-term colors (DPO=blue, δ=green, λ=red is FORBIDDEN); anatomy of
  an equation not displayed on the poster; >4 items.

### `flow-strip`
- **Purpose**: horizontal labeled pipeline (`.step` boxes + `.arrow` glyphs) grounded in
  paper variables, e.g. data pair → implicit reward → shift → penalty → optimum.
- **Variants**: `.step--final` (gold top bar + gold-soft bg) — at most ONE, the endpoint.
- **Tokens**: every step the same accent-light; final step gold-soft.
- **Inspected by**: style rule 4, measure, polish FLEX-BR (no `<br>` in steps — use
  `.step-name` block + text).
- **Allowed fix ops**: step count/text rebalance; token edits.
- **Anti-patterns**: calling it an "Algorithm" when the paper has none (label it
  "Objective flow" / "Loss anatomy"); per-step colors; >6 steps.

### `figure--duo`
- **Purpose**: two sibling paper figures sharing one card and ONE caption (e.g.
  failure-geometry → fix-geometry on the same axes).
- **Contract**: both `<img>` carry `data-source="paper"` + `data-asset-id` + `.w-45`/`.w-50`
  (each 42–48% of the card); combined target 8–12% of body.
- **Inspected by**: asset (provenance + per-figure + total bands), polish FIG gates.
- **Allowed fix ops**: asset fixes (re-crop), width within band, swap member figures.
- **Anti-patterns**: pairing unrelated figures; before/after labels in extra hues (use
  text labels with accent/gold only).

### `result-table` derived column (`th.derived` / `td.derived`)
- **Purpose**: a DERIVED arithmetic column (e.g. Δ = Ours − Baseline) next to verbatim
  paper values; gold-soft background marks "derived, not copied".
- **Contract**: the table caption or setup line MUST state the derivation ("Δ = AuxDPO −
  DPO, derived"). Negative/degrading values use *italic*, never red.
- **Inspected by**: style rule 4 (gold family), content audits (Phase 1/6 verify arithmetic).
- **Anti-patterns**: mixing derived and verbatim values in one column; unlabeled derived data.

### `keybox--4`
- **Purpose**: 4-up stat/property tiles (e.g. params / complexity / loss type / guarantee).
- **Contract**: all four tiles identical styling; numbers must trace to the paper.
- **Anti-patterns**: per-tile colors; tiles restating the banner stats verbatim.

### `algo`
- **Purpose**: compact numbered procedure list — **only when the paper itself states an
  explicit algorithm/procedure**. Cite it ("Alg. 1", "the procedure of §4.2").
- **Anti-patterns**: INVENTING steps from prose (the v31 poster fabricated a "5 steps per
  batch" algorithm that was not in the paper — this is the cautionary tale).

### `claim-pills`
- **Purpose**: provenance mini-table (`.cp-id` pill + evidence + `.cp-fact`/`.cp-derived`
  badge) for numeric-heavy posters where every number should trace to a source.
- **Contract**: use only when the poster carries ≥8 distinct numeric claims; badges are
  text (FACT/DERIVED), accent/gold colored — no new hues.
- **Anti-patterns**: pills for trivial claims; turning it into a second results table.

### `logo-row` + venue-badge logo (added 2026-06-05, user-checkpointed)
- **Purpose**: institution logos in the header right block (beside the QR), and the
  official venue logo above the venue-badge text. Sized to pair with the QR
  (logo-row 68u, venue logo 52u) — visible from poster distance, never tiny.
- **Contract**: REAL logo files only (user-provided or official sources) — fabricating
  a seal as inline SVG is forbidden (the v31 cautionary tale). Every logo `<img>` MUST
  carry `data-color-exempt="logo"` (palette-gate exemption) and a meaningful `alt`.
- **Tokens**: layout-only CSS; logo artwork colors are exempt by contract.
- **Inspected by**: style rules 10/11 (exemption attribute), preflight (file exists).
- **Allowed fix ops**: swap logo file, adjust the row's height token, drop a logo.
- **Anti-patterns**: fabricated/approximated seals; logos so small they read as dirt
  (< ~40u); using the logo row to smuggle decorative graphics.
