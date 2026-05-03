---
name: paper-poster
description: "Generate a conference poster (article + tcbposter LaTeX → A0/A1 PDF + editable PPTX + SVG) from a compiled paper. Use when user says \"做海报\", \"制作海报\", \"conference poster\", \"make poster\", \"生成poster\", \"poster session\", or wants to create a poster for a conference presentation."
argument-hint: "[paper-directory-or-venue] [— style-ref: <source>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Paper Poster: From Paper to Conference Poster

Generate a conference poster from: **$ARGUMENTS**

## Context

This skill runs **after** Workflow 3 (`/paper-writing`). It takes a compiled paper and generates a print-ready poster for conference poster sessions. The poster extracts key content from the paper — it does **not** dump the full paper text onto a poster.

Unlike papers (dense prose, 8-15 pages), posters are **visual-first**: one page, 4 columns, bullet points only, figures dominant. A good poster tells the story in 60 seconds.

## Constants

- **VENUE = `NeurIPS`** — Target venue, determines color scheme. Supported: `NeurIPS`, `ICML`, `ICLR`, `AAAI`, `ACL`, `EMNLP`, `CVPR`, `ECCV`, `GENERIC`. Override via argument (e.g., `/paper-poster "— venue: ICML"`).
- **POSTER_SIZE = `A0`** — Paper size. Options: `A0` (841x1189mm, default), `A1` (594x841mm).
- **ORIENTATION = `landscape`** — Orientation. Options: `landscape` (default), `portrait`.
- **COLUMNS = 4** — Number of content columns. Typical: 4 for landscape A0 (IMRAD), **3 for portrait A0** (research consensus), 2 for portrait A1. Portrait A0 should NEVER use 4 columns — text becomes too narrow and unreadable.
- **PAPER_DIR = `paper/`** — Directory containing the compiled paper (main.tex + figures/).
- **OUTPUT_DIR = `poster/`** — Output directory for all poster files.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for poster review.
- **AUTO_PROCEED = false** — At each checkpoint, **always wait for explicit user confirmation**. Set `true` only if user explicitly requests fully autonomous mode.
- **COMPILER = `latexmk`** — LaTeX build tool.
- **ENGINE = `pdflatex`** — LaTeX engine. Use `xelatex` for CJK text.

> 💡 Override: `/paper-poster "paper/" — venue: CVPR, size: A1, orientation: portrait, columns: 3`

## Optional: Style reference (`— style-ref: <source>`, opt-in)

Lets the user steer the poster's **structural** layout (panel-to-text ratio, figure density, caption length) toward a reference paper. **Default OFF — when the user does not pass `— style-ref`, do nothing differently from before.**

Only when `— style-ref: <source>` appears in `$ARGUMENTS`, run the helper FIRST:

```bash
if [ ! -f tools/extract_paper_style.py ]; then
  echo "error: tools/extract_paper_style.py not found — re-run 'bash tools/install_aris.sh' to refresh the '.aris/tools' symlink (added in #174), or copy the helper manually from the ARIS repo" >&2
  exit 1
fi
CACHE=$(python3 tools/extract_paper_style.py --source "<source>")
case $? in
  0) ;;                                       # use $CACHE/style_profile.md as structural guidance
  2) echo "warning: style-ref skipped (missing optional dep)" >&2 ;;
  3) echo "error: --style-ref source failed; aborting poster" >&2 ; exit 1 ;;
  *) echo "error: helper failed unexpectedly; aborting poster" >&2 ; exit 1 ;;
esac
```

Sources accepted: local TeX dir / file, local PDF, arXiv id, http(s) URL. Overleaf URLs/IDs are rejected — clone via `/overleaf-sync setup <id>` first and pass the local clone path.

**Strict rules** (full contract in `tools/extract_paper_style.py` docstring):

- Use `style_profile.md` to align figure-to-text ratio, caption length tendency, and paragraph density. Venue color scheme and column count above still take precedence — `--style-ref` only refines density tendencies.
- **Never copy poster content, design elements, slogans, or section names verbatim** from anything reachable through the cache.
- **Never pass `— style-ref` (or the cache contents) to the GPT-5.4 reviewer sub-agent** — the reviewer must judge the poster's clarity on its own merits.

## Venue Color Schemes

Use **deep, saturated** colors for primary — pastel/light colors wash out on large posters viewed from distance. Each venue uses a **3-color system**: primary (dark, for title bar), secondary (medium, for section headers), accent (contrast, for highlights).

| Venue | Primary | Secondary | Accent | Background | Text |
|-------|---------|-----------|--------|------------|------|
| NeurIPS | `#4C1D95` (deep purple) | `#6D28D9` (purple) | `#2563EB` (blue) | `#F5F3FF` | `#1F2937` |
| ICML | `#7F1D1D` (deep maroon) | `#B91C1C` (red) | `#1E40AF` (blue) | `#EDD5D5` | `#111827` |
| ICLR | `#065F46` (deep green) | `#059669` (green) | `#0284C7` (blue) | `#F0FDF4` | `#1F2937` |
| CVPR | `#1E3A8A` (deep blue) | `#2563EB` (blue) | `#7C3AED` (purple) | `#F8FAFC` | `#1F2937` |
| AAAI | `#0C4A6E` (deep navy) | `#0369A1` (blue) | `#DC2626` (red) | `#F0F9FF` | `#1F2937` |
| ACL | `#155E75` (deep teal) | `#0891B2` (teal) | `#7C3AED` (purple) | `#F0FDFA` | `#1F2937` |
| EMNLP | `#713F12` (deep amber) | `#D97706` (amber) | `#2563EB` (blue) | `#FFFBEB` | `#1F2937` |
| ECCV | `#701A75` (deep fuchsia) | `#C026D3` (fuchsia) | `#0891B2` (teal) | `#FDF4FF` | `#1F2937` |
| GENERIC | `#1E293B` (deep slate) | `#334155` (slate) | `#2563EB` (blue) | `#F8FAFC` | `#1F2937` |

> ⚠️ **Color lesson**: Never use light/pastel colors (e.g., `#8B5CF6`) as primary — they look washed out on A0 posters. Always use the darkest shade as primary for the title bar.

## State Persistence (Compact Recovery)

Poster generation can be long. Persist state to `poster/POSTER_STATE.json` after each phase:

```json
{
  "phase": 3,
  "venue": "NeurIPS",
  "poster_size": "A0",
  "orientation": "landscape",
  "columns": 4,
  "figures_selected": ["architecture.pdf", "results.pdf"],
  "codex_thread_id": "019cfcf4-...",
  "status": "in_progress",
  "timestamp": "2026-03-18T15:00:00"
}
```

**On startup**: if `POSTER_STATE.json` exists with `"status": "in_progress"` and within 24h → resume from saved phase. Otherwise → fresh start.

## Critical LaTeX Architecture Decisions

> ⚠️ **MUST use `article` class, NEVER `beamer` class.** The beamer class consumes too many TeX grouping levels for its overlay/mode system. Combined with tcbposter's `enhanced` style on 8+ posterboxes, this triggers `! TeX capacity exceeded, sorry [grouping levels=255]`. The article class + geometry package for custom page size is the correct approach. This was validated through 5 failed compilation attempts with beamer before switching to article.

> ⚠️ **NEVER use `adjustbox` package.** It may not be installed in minimal TeX distributions. Use plain `\includegraphics[width=0.96\linewidth]{file}` instead. Do NOT use `max height` option (requires adjustbox).

### Template Foundation

```latex
\documentclass{article}
% A0 landscape: paperwidth=1189mm,paperheight=841mm
% A0 portrait:  paperwidth=841mm,paperheight=1189mm
\usepackage[paperwidth=1189mm,paperheight=841mm,margin=0mm]{geometry}
\usepackage{tcolorbox}
\tcbuselibrary{poster,skins,fitting}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage[table]{xcolor}  % MUST use [table] option for \rowcolor in tables
\usepackage{lmodern}
\usepackage[T1]{fontenc}
\pagestyle{empty}
```

> ⚠️ **NEVER use `\usepackage[most]{tcolorbox}`** — it pulls in `listingsutf8.sty` which may not be installed. Always use `\tcbuselibrary{poster,skins,fitting}` explicitly.

> ⚠️ **Use `[table]{xcolor}`** not plain `{xcolor}` — needed for `\rowcolor` in benchmark tables. The `colortbl` package is loaded automatically by this option.

## tcbposter Layout Rules (Critical)

> ⚠️ **The #1 cause of poster failures is content overflow.** tcbposter uses a fixed grid — content that exceeds the box is **silently clipped** with no compilation error. You will NOT see any warning; the poster will simply be cut off.

> ⚠️ **The #2 cause is large whitespace gaps.** Using too few rows (e.g., `rows=5`) creates ~168mm per row on A0 landscape. If title text only needs 120mm, the remaining 48mm is wasted whitespace. Solution: use `rows=20` for fine-grained control (~42mm per row).

### Grid System: `rows=20` (Critical)

Use `rows=20` for A0 landscape. Each row ≈ 42mm, giving precise control over section heights.

**Recommended row allocation for 4-column A0 landscape:**

| Section | Rows | Height | Row range |
|---------|:----:|:------:|-----------|
| Title bar | 3 | ~126mm | `top` to `row4` |
| Stat banner | 2 | ~84mm | `row4` to `row6` |
| Body content | 14 | ~588mm | `row6` to `bottom` |

**Key principle**: Always use `between=rowN and rowM` syntax (not `below=name`) for precise vertical placement. The `below=` syntax lets tcolorbox auto-place, which often leaves unwanted gaps.

### Row Count Guidance

| Poster Size | Orientation | Recommended rows | Columns | Row height |
|-------------|-------------|:---:|:---:|:---:|
| A0 | landscape | 20 | 4 | ~42mm |
| A0 | portrait | 20 | **3** | ~59mm |
| A1 | landscape | 16 | 3 | ~37mm |
| A1 | portrait | 20 | 2 | ~30mm |

### Portrait A0 Layout (3 columns, rows=20)

> ⚠️ **Portrait A0 posters use 2-3 columns, NEVER 4.** Research consensus: "Two columns is typical for a poster with a portrait orientation" (Colin Purrington, NYU poster guides). At 841mm width, 4 columns give only ~195mm per column — too narrow for readable text at poster-session distance. **3 columns (~260mm each) is the recommended default** for content-rich papers. Use 2 columns for simpler posters or when figures need more horizontal space.

For portrait posters (841x1189mm), use a **3-column, 3-row-band** layout:

| Section | Rows | Row range | Content |
|---------|:----:|-----------|---------|
| Title bar | 4 | `top` to `row4` | Title + authors + venue (span=3) |
| Stat banner | 2 | `row4` to `row6` | 3 headline stat callouts (span=3) |
| Row A | 5 | `row6` to `row11` | Background+Motivation, Method (hero fig), Key Results (fig) |
| Row B | 5 | `row11` to `row16` | Contributions, Equations+Ablation, Result 2 (fig+table) |
| Row C | 4 | `row16` to `bottom` | References+QR, Setup+Benchmarks, Key Takeaways |

**3-column portrait layout diagram:**
```
┌─────────────────────────────────────┐
│         TITLE BAR (span=3)          │
├─────────────────────────────────────┤
│   Stat 1   │   Stat 2   │  Stat 3  │
├────────────┼────────────┼──────────┤
│ Background │  Method    │ Result 1 │
│ & Motiv.   │ (hero fig) │ (figure) │
├────────────┼────────────┼──────────┤
│ Contribu-  │ Equations  │ Result 2 │
│ tions      │ & Ablation │ (fig+tbl)│
├────────────┼────────────┼──────────┤
│ References │  Setup &   │   Key    │
│ + QR Code  │ Benchmarks │Takeaways │
└────────────┴────────────┴──────────┘
```

> ⚠️ **All 3 columns in each row band share the same row boundaries.** This ensures cross-column alignment. Never mix `row6 to row11` in one column with `row6 to row10` in another — it creates visual misalignment.

> ⚠️ **Use `spacing=0mm`** for tight layouts. Card separation is handled by card styles (left accent stripe, drop shadow), not grid spacing. Grid spacing > 2mm creates visible gaps between rows.

### Modern Card Design System (Left Accent Stripe)

Instead of rounded boxes with colored headers, use a **left accent stripe** design. This is cleaner, more modern, and avoids the "PowerPoint box" look.

Define **4 card styles** using the venue's 3-color system:

```latex
% Tinted card backgrounds (NOT pure white — adds warmth)
\definecolor{redbg}{HTML}{FFF5F3}     % warm pink tint for redcard
\definecolor{bluebg}{HTML}{F0F4FF}    % cool blue tint for bluecard
\definecolor{darkbg}{HTML}{FDF6F3}    % warm cream tint for darkcard
\definecolor{redtitlebg}{HTML}{FDEAE8}   % title bar tint
\definecolor{bluetitlebg}{HTML}{E4ECFF}
\definecolor{darktitlebg}{HTML}{F5E8E2}

\tcbset{
  redcard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=redbg,
    borderline west={5pt}{0pt}{secondary},
    left=16pt, right=14pt, top=4pt, bottom=4pt,
    fonttitle=\fontsize{40}{48}\selectfont\bfseries\color{secondary},
    coltitle=secondary, colbacktitle=redtitlebg,
    toptitle=6pt, bottomtitle=6pt,
    titlerule=2pt, titlerule style={secondary!50},
    valign=top, drop shadow={opacity=0.18},
  },
  bluecard/.style={...same pattern with accent color and bluebg...},
  darkcard/.style={...same pattern with primary color and darkbg...},
  highlightcard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=primary!18!white,
    borderline west={6pt}{0pt}{primary},
    fonttitle=...\color{white}, colbacktitle=primary,
    ...
  },
}
```

**Card assignment pattern** (creates visual rhythm):
- **redcard** (secondary stripe): Background, Key Idea, Ablation, References, Setup
- **bluecard** (accent stripe): Result 1, Result 2, Benchmarks, Analysis
- **darkcard** (primary stripe): Contributions, Method
- **highlightcard** (primary fill): Key Takeaways / Conclusion

> ⚠️ **Card backgrounds must NOT be pure white (#FFFFFF).** Use subtle tints matching the card's color family. Pure white cards on a tinted poster background look disconnected. The tint should be barely visible but adds cohesion.

### Figure + Caption Macro

Define a consistent macro for all figures to ensure uniform spacing:

```latex
\newcommand{\posterfig}[3]{%
  \centering\includegraphics[width=#1\linewidth]{#2}\\[3mm]
  {\fontsize{26}{32}\selectfont\color{textgray}\textit{#3}}\vspace{2mm}%
}
% Usage: \posterfig{0.96}{figures/results.png}{Caption text here.}
```

> ⚠️ **Inconsistent figure-text spacing** is the #1 visual flaw in generated posters. The `\posterfig` macro enforces uniform 3mm gap + 2mm bottom padding across all figures.

### Content Colorbox Intensity

Inside cards, use `\colorbox{color!N}` for highlighted blocks. The intensity `N` must be **18-25%** (not 8-12% which is too faint):

```latex
% TOO FAINT (invisible on print):
\colorbox{primary!8}{\parbox{...}{...}}

% CORRECT (visible, distinct):
\colorbox{primary!20}{\parbox{0.94\linewidth}{...}}
\colorbox{accent!20}{\parbox{0.94\linewidth}{...}}
\colorbox{secondary!20}{\parbox{0.94\linewidth}{...}}
```

Similarly, `\rowcolor` in tables should use 15% intensity: `\rowcolor{primary!15}`.

### Font Size Rules (A0 at article class — NO scale factor)

> ⚠️ **Critical**: When using `article` class (not beamerposter), there is NO automatic scale factor. All font sizes are literal. A poster viewed from 1.5m needs much larger fonts than you think.

| Element | Font size | Leading | Example |
|---------|:---------:|:-------:|---------|
| Title | 90pt | 108pt | `\fontsize{90}{108}\selectfont` |
| Author line | 42pt | 50pt | `\fontsize{42}{50}\selectfont` |
| Section headers | 42pt | 50pt | via `fonttitle=\fontsize{42}{50}...` |
| Sub-headers | 38pt | 46pt | `\subheader{}{}` command |
| Body text | 34pt | 44pt | `\fontsize{34}{44}\selectfont` |
| Stat callout numbers | 72pt | 86pt | `\fontsize{72}{86}\selectfont` |
| Stat callout labels | 30pt | 36pt | `\fontsize{30}{36}\selectfont` |
| Equations | 32pt | 40pt | `\fontsize{32}{40}\selectfont` |
| Table cells | 30pt | 38pt | `\fontsize{30}{38}\selectfont` |
| Figure captions | 28pt | 34pt | `\fontsize{28}{34}\selectfont` |
| References | 30pt | 40pt | `\fontsize{30}{40}\selectfont` |

> ⚠️ **Lesson learned from testing**: Body text at 20pt on A0 is unreadable from more than 0.5m. 34pt is the minimum for comfortable reading at poster-session distance.

### Content Budget

**Total target: 300-500 words** (excluding figure captions and stat callout numbers).

> ⚠️ **The #1 content mistake is too much text.** A poster is NOT a paper summary — it's a visual guide. Each bullet should be a **key phrase** (5-8 words), not a sentence. If you find yourself writing full sentences, you're putting too much text.

> ⚠️ **Content density calibration**: When in doubt, use LESS text. It's much easier to add a few words than to trim dense paragraphs. Target ~70% fill per card (some breathing room), NOT 100%.

| Box type | Max bullets | Max words | Figure? | Style |
|----------|:-:|:-:|---------|-------|
| Background | 3 | 40-60 | No | Short bullets + 1 key insight colorbox |
| Key Idea / Architecture | 0-1 | 20-30 | Yes (hero fig) | Figure dominant + 2 one-liner colorboxes |
| Contributions | 3-4 | 60-80 | No | Numbered, 1 line each |
| Method | 2-3 | 40-60 | No | 2 equation colorboxes + 3 short bullets |
| Results (each) | 2-3 | 30-50 | Yes (figure) | Figure + 2-3 one-line colorboxes |
| Ablation | 3 | 30-40 | No | 3 colorboxes, 2 lines each max |
| Analysis | 3 | 30-50 | Yes (figure) | Figure + 3 one-line colorboxes |
| References | 4-5 | 30-40 | No | Author (year). Short title. *Venue* |
| Setup | 4-5 | 30-40 | No | 5 one-liner colorboxes |
| Benchmarks | 0 | 20 | No | Table + 1-line caption |
| Key Takeaways | 3 | 30-40 | No | 3 short items + code link |

**Bullet point rules:**
- Maximum **8 words per bullet** when possible
- Use `$\Rightarrow$` and `$\to$` for causal arrows instead of words
- Numbers > words: "**42% less memory**" not "reduces memory usage by 42 percent"
- Colorbox labels: "**vs. Depth:** 4L CoE ≈ 12L MoE, **42% less memory**" (one line)

### Recommended 4-Column IMRAD Layout

```
┌──────────────────────────────────────────────────────────┐
│                    TITLE BAR (span=4)                     │
│     Title (90pt) + Authors (42pt) + Venue + GitHub        │
├──────────────────────────────────────────────────────────┤
│  Stat 1  │  Stat 2  │  Stat 3  │  Stat 4  │  STAT BANNER│
├──────────┼──────────┼──────────┼──────────┤             │
│Background│ Dataset  │Architectu│ Result 2 │             │
│    &     │    &     │   re     │  + Table │             │
│Motivation│Paradigms │ Overview │  + Stats │             │
│    +     │  + Fig   │  + Fig   │  + Fig   │             │
│Contributi│          │──────────│──────────│             │
│   ons    │──────────│ Result 1 │ Ablation │             │
│──────────│Computat. │  + Fig   │──────────│             │
│References│ Models   │  + Table │Conclusion│             │
│ + QR Code│+ Equations│ + Bullets│ + Future │             │
└──────────┴──────────┴──────────┴──────────┘
```

## Workflow

### Phase 0: Input Validation & Setup

1. **Check prerequisites**:
   ```bash
   which pdflatex && which latexmk
   ```

   **If LaTeX is NOT installed**, try in order:
   ```bash
   # Option 1: brew cask (requires sudo — may fail in non-interactive shells)
   brew install --cask mactex-no-gui

   # Option 2: BasicTeX (smaller, may still need sudo)
   brew install --cask basictex

   # Option 3: User-directory install (NO sudo needed — always works)
   curl -L https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz | tar xz
   cd install-tl-*
   cat > texlive.profile << 'PROF'
   selected_scheme scheme-basic
   TEXDIR ~/texlive/YYYY
   TEXMFLOCAL ~/texlive/texmf-local
   TEXMFSYSCONFIG ~/texlive/YYYY/texmf-config
   TEXMFSYSVAR ~/texlive/YYYY/texmf-var
   TEXMFHOME ~/texmf
   binary_x86_64-darwin 1
   instopt_adjustpath 0
   instopt_adjustrepo 1
   instopt_write18_restricted 1
   tlpdbopt_autobackup 1
   tlpdbopt_install_docfiles 0
   tlpdbopt_install_srcfiles 0
   PROF
   ./install-tl --profile=texlive.profile
   export PATH="$HOME/texlive/YYYY/bin/universal-darwin:$PATH"
   ```

   After installation, install required packages:
   ```bash
   tlmgr install tcolorbox pgf etoolbox environ trimspaces \
     type1cm pdfcol tikzfill latexmk lm enumitem geometry
   ```

   > ⚠️ **Lesson learned**: `brew install --cask mactex-no-gui` often fails in non-interactive shells because the macOS installer requires sudo password. The user-directory TeX Live install (Option 3) always works without sudo.

   > ⚠️ **Do NOT install or use `beamerposter`**. The article class approach does not need it.

2. **Verify paper exists**:
   ```bash
   ls $PAPER_DIR/main.tex || ls $PAPER_DIR/main.pdf
   ls $PAPER_DIR/sections/*.tex
   ls $PAPER_DIR/figures/
   ```

3. **Backup existing poster**: if `poster/` exists, copy to `poster-backup-{timestamp}/`

4. **Create output directory**: `mkdir -p poster/figures`

5. **Copy figures** to poster directory:
   ```bash
   # IMPORTANT: Use cp, NOT ln -sf (symlinks)
   # pdflatex often fails to resolve symlinks across directories
   cp paper/figures/selected_figure.pdf poster/figures/
   ```

   > ⚠️ **Never use symlinks** for poster figures. `pdflatex` cannot reliably follow symlinks across directories. Always `cp` the actual files.

6. **Convert PDF figures to PNG** for PPTX embedding:
   ```bash
   python3 -c "import pdf2image" 2>/dev/null || pip install pdf2image
   # For each figure:
   python3 -c "
   from pdf2image import convert_from_path
   for name in ['paradigm', 'architecture', 'results', 'hallucination']:
       imgs = convert_from_path(f'poster/figures/{name}.pdf', dpi=300)
       imgs[0].save(f'poster/figures/{name}.png', 'PNG')
   "
   ```

   > ⚠️ **python-pptx CANNOT embed PDF images.** You MUST convert to PNG first. This is a hard limitation of the OOXML format. Always generate PNG copies at 300 DPI during setup.

7. **Detect CJK**: if paper contains Chinese/Japanese/Korean text, set ENGINE to `xelatex`

8. **Check for resume**: read `poster/POSTER_STATE.json` if it exists

### Phase 1: Content Extraction

Read each section from `paper/sections/*.tex` and extract poster-appropriate content:

**Extraction rules** — a poster shows ~30-40% of the paper's content:

| Paper Section | Poster Extraction | Target Length |
|---------------|-------------------|---------------|
| Abstract | **Skip** — replace with 2-4 big-number stat callout boxes spanning all columns | 0 words (numbers only) |
| Introduction | Motivation: 2-3 bullet points + numbered contribution list (4 items) | 120-160 words |
| Method | 1 hero architecture figure + key equations + 3-5 bullet points | 80-120 words |
| Experiments | Dataset details + main result figures + numeric stat tables + ablation | 150-200 words |
| Conclusion | 3-4 key findings + 2-3 next steps | 60-80 words |
| Related Work | **Skip entirely** — no space on poster | 0 |

**Total target: 400-700 words** (excluding figure captions and stat callout numbers).

> ⚠️ **No abstract paragraph on poster.** Replace with a stat banner: 3-4 large-number callout boxes showing headline results. This is the single highest-impact change for 60-second comprehension.

**Output**: `poster/POSTER_CONTENT_PLAN.md` — structured markdown showing exactly what goes where, with word counts per box.

**🚦 Checkpoint:**

```
📋 Poster content plan ready:
- Title: [paper title]
- Venue: [VENUE] ([POSTER_SIZE] [ORIENTATION])
- Layout: [COLUMNS] columns, rows=20
- Figures selected: [N] figures
- Boxes per column: Col1=[N], Col2=[N], Col3=[N], Col4=[N]
- Estimated word count: [N] words

Proceed with this layout? Or adjust content selection?
```

**⛔ STOP HERE and wait for user response.**

**State**: Write `POSTER_STATE.json` with `phase: 1`.

### Phase 2: Figure Selection & Layout

1. **Inventory** all figures in `paper/figures/`:
   ```bash
   ls -la paper/figures/*.{pdf,png,jpg,svg} 2>/dev/null
   ```

2. **Rank by poster importance**:
   - **Tier 1 (must include)**: Architecture/method overview diagram, main results plot
   - **Tier 2 (include if space)**: Ablation bar chart, qualitative examples, experimental paradigm
   - **Tier 3 (skip)**: Appendix figures, supplementary plots, tables-as-figures

3. **Select top 3-5 figures** that fit the 4-column layout

4. **Copy figures** to poster directory (NOT symlinks) + **convert PDF→PNG** for PPTX

5. **Design column layout** — 4-column IMRAD:
   - **Col 1**: Background & Motivation + Contributions + References & QR
   - **Col 2**: Dataset & Paradigms (fig) + Computational Models (equations)
   - **Col 3**: Architecture (fig) + Result 1 (fig + stat table)
   - **Col 4**: Result 2 (fig + stat table) + Ablation + Conclusion

### Phase 3: Generate Poster LaTeX

Create `poster/main.tex` using **article class + geometry + tcbposter**.

**Template structure** (validated through testing):

```latex
\documentclass{article}
\usepackage[paperwidth=1189mm,paperheight=841mm,margin=0mm]{geometry}
\usepackage{tcolorbox}
\tcbuselibrary{poster,skins,fitting}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage[table]{xcolor}
\usepackage{lmodern}
\usepackage[T1]{fontenc}
\pagestyle{empty}

% ── Venue Color Theme ──
\definecolor{primary}{HTML}{VENUE_PRIMARY}     % deep, saturated
\definecolor{secondary}{HTML}{VENUE_SECONDARY} % medium
\definecolor{accent}{HTML}{VENUE_ACCENT}       % contrast
\definecolor{bgposter}{HTML}{VENUE_BG_DEEP}    % poster background (NOT white, use tinted)
\definecolor{redbg}{HTML}{FFF5F3}              % card backgrounds (tinted, NOT white)
\definecolor{bluebg}{HTML}{F0F4FF}
\definecolor{darkbg}{HTML}{FDF6F3}
\definecolor{redtitlebg}{HTML}{FDEAE8}         % card title bar backgrounds
\definecolor{bluetitlebg}{HTML}{E4ECFF}
\definecolor{darktitlebg}{HTML}{F5E8E2}
\definecolor{textdark}{HTML}{111827}
\definecolor{textgray}{HTML}{4B5563}
\definecolor{stathighlight}{HTML}{FEE8E8}

\pagecolor{bgposter}
\color{textdark}

% ── List styling ──
\setlist[itemize]{leftmargin=24pt, itemsep=6pt, parsep=2pt, topsep=2pt,
  label={\color{secondary}$\blacktriangleright$}}
\setlist[enumerate]{leftmargin=24pt, itemsep=6pt, parsep=2pt, topsep=2pt,
  label={\color{primary}\bfseries\arabic*.}}

% ── Figure+caption macro (ensures uniform spacing) ──
\newcommand{\posterfig}[3]{%
  \centering\includegraphics[width=#1\linewidth]{#2}\\[3mm]
  {\fontsize{26}{32}\selectfont\color{textgray}\textit{#3}}\vspace{2mm}%
}

% ── Card styles (left accent stripe design) ──
\tcbset{
  redcard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=redbg,
    borderline west={5pt}{0pt}{secondary},
    left=16pt, right=14pt, top=4pt, bottom=4pt,
    fonttitle=\fontsize{40}{48}\selectfont\bfseries\color{secondary},
    coltitle=secondary, colbacktitle=redtitlebg,
    toptitle=6pt, bottomtitle=6pt,
    titlerule=2pt, titlerule style={secondary!50},
    valign=top, drop shadow={opacity=0.18},
  },
  bluecard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=bluebg,
    borderline west={5pt}{0pt}{accent},
    left=16pt, right=14pt, top=4pt, bottom=4pt,
    fonttitle=\fontsize{40}{48}\selectfont\bfseries\color{accent},
    coltitle=accent, colbacktitle=bluetitlebg,
    toptitle=6pt, bottomtitle=6pt,
    titlerule=2pt, titlerule style={accent!50},
    valign=top, drop shadow={opacity=0.18},
  },
  darkcard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=darkbg,
    borderline west={5pt}{0pt}{primary},
    left=16pt, right=14pt, top=4pt, bottom=4pt,
    fonttitle=\fontsize{40}{48}\selectfont\bfseries\color{primary},
    coltitle=primary, colbacktitle=darktitlebg,
    toptitle=6pt, bottomtitle=6pt,
    titlerule=2pt, titlerule style={primary!50},
    valign=top, drop shadow={opacity=0.18},
  },
  highlightcard/.style={
    enhanced, arc=0pt, boxrule=0pt, colback=primary!18!white,
    borderline west={6pt}{0pt}{primary},
    left=16pt, right=14pt, top=4pt, bottom=4pt,
    fonttitle=\fontsize{40}{48}\selectfont\bfseries\color{white},
    coltitle=white, colbacktitle=primary,
    toptitle=6pt, bottomtitle=6pt,
    valign=top, drop shadow={opacity=0.22},
  },
}

\begin{document}
\begin{tcbposter}[
  coverage={spread},
  poster={columns=4, rows=20, spacing=0mm},  % Use columns=3 for portrait A0
]

% ══ TITLE BAR ══
\posterbox[
  enhanced, colback=primary, colframe=primary, colupper=white,
  arc=0pt, boxrule=0pt,
  left=40pt, right=40pt, top=12pt, bottom=8pt,
  halign=center, valign=center,
  drop shadow={opacity=0.3}
]{name=title, column=1, span=4, between=top and row4}{
  {\fontsize{84}{100}\selectfont\bfseries PAPER TITLE}\\[12pt]
  {\fontsize{36}{44}\selectfont Authors}\\[8pt]
  {\fontsize{30}{38}\selectfont\color{white!70} Affiliations | VENUE YEAR | github.com/...}
}

% ══ STATS BANNER ══
\posterbox[
  enhanced, colback=primary!15!white, boxrule=0pt, arc=0pt,
  left=12pt, right=12pt, top=6pt, bottom=6pt,
  valign=center, borderline south={3pt}{0pt}{primary!35},
]{name=stats, column=1, span=4, between=row4 and row6}{
  \centering
  \begin{minipage}[c]{0.235\linewidth}\centering
    \fcolorbox{primary!40}{stathighlight}{\parbox{0.88\linewidth}{%
      \centering\vspace{6pt}%
      {\fontsize{66}{80}\selectfont\bfseries\color{primary} STAT1}\\[4pt]
      {\fontsize{26}{32}\selectfont\color{textdark} Label 1}\vspace{6pt}%
    }}
  \end{minipage}\hfill
  % ... 3 more stat callouts in same pattern
}

% ══ CONTENT CARDS ══
% Use card styles: \posterbox[redcard, title={...}]{...}{...}
% Body text: \fontsize{34}{44}\selectfont
% Figures: \posterfig{0.96}{figures/name.png}{Caption.}
% Colorboxes: \colorbox{primary!20}{\parbox{0.94\linewidth}{...}}

\end{tcbposter}
\end{document}
```

**Key formatting rules**:
- Title: 84pt, bold, primary background, white text
- Author line: 36pt, white text
- Section headers: 40pt via `fonttitle` — colored text on tinted title background
- Body text: 34pt with 44pt leading — `\fontsize{34}{44}\selectfont`
- Figures: via `\posterfig{0.96}{figures/name.png}{Caption}` macro
- Stat callout numbers: 66pt in primary color on stathighlight background
- Tables: `\renewcommand{\arraystretch}{1.6}` with `\rowcolor{primary!15}` zebra striping
- Equations in colorboxes: use `$\displaystyle ...$` (inline), **NOT** `\[...\]` (display math adds margins that cause overfull hbox)

**Posterbox pattern** (using card styles):
```latex
\posterbox[redcard, title={Section Title}
]{name=uniquename, column=N, between=rowA and rowB}{
  \fontsize{34}{44}\selectfont
  \begin{itemize}[itemsep=12pt]
    \item Key point one
    \item Key point two
  \end{itemize}
}
```

> ⚠️ **Equations in narrow colorboxes**: Display math `\[...\]` adds horizontal margins that cause overfull hbox errors inside `\colorbox{\parbox{}}`. Always use `$\displaystyle ...$` with `\centering` instead. Reduce equation font to 26-28pt inside colorboxes.

**🚦 Checkpoint:**

```
🖼️ Poster LaTeX generated:
- Template: article + tcbposter (rows=20)
- Layout: [COLUMNS] columns, [ORIENTATION] [POSTER_SIZE]
- Colors: [VENUE] theme (primary: [HEX] / secondary: [HEX] / accent: [HEX])
- Figures: [N] embedded
- Font sizes: title=90pt, body=34pt, headers=42pt
- Word count: ~[N] words

Compile now?
```

**⛔ STOP HERE and wait for user response.**

**State**: Write `POSTER_STATE.json` with `phase: 3`.

### Phase 4: Compile Poster

```bash
cd poster && latexmk -pdf -interaction=nonstopmode main.tex
```

> ⚠️ If using user-directory TeX Live, prepend PATH: `export PATH="$HOME/texlive/YYYY/bin/universal-darwin:$PATH"`

**Error handling loop** (max 3 attempts):
1. Parse error log for the first error
2. Fix the most likely cause:
   - `grouping levels=255` → **STOP. Switch from beamer to article class.** This is not fixable by removing styles.
   - Missing package → `tlmgr install <package>`
   - `File not found: adjustbox.sty` → Remove `\usepackage{adjustbox}` and any `max height` options
   - File not found → verify `poster/figures/` has the file (not a broken symlink)
   - Overfull boxes → reduce text or figure size
3. Recompile

**Common missing packages** (install proactively if not present):
```bash
tlmgr install type1cm pdfcol tikzfill
```

**Verification**:
```bash
pdfinfo poster/main.pdf
# Check: Pages: 1, Page size: ~3370.39 x 2383.94 pts (A0 landscape)
```

**Visual inspection** after compilation:
1. All 4 columns have content visible to the bottom — no silent clipping
2. No large whitespace gaps between title/stats and body content
3. Figures are fully visible, not cut off
4. Text is readable (zoom to 100% = actual A0 size)

### Phase 5: Visual Review via Claude + Gemini (Iterative Refinement)

> This phase uses **Claude visual assessment** on rendered poster images to iteratively refine layout, readability, and visual hierarchy — similar to the `paper-illustration` skill's review loop.

**Step 1: Render poster to PNG preview**

```python
import fitz
doc = fitz.open('poster/main.pdf')
page = doc[0]
pix = page.get_pixmap(dpi=200)  # 200 DPI for visual review (higher than 150 preview)
pix.save('poster/poster_review.png')
doc.close()
```

**Step 2: Claude visual assessment**

Read the rendered `poster/poster_review.png` and perform a **STRICT visual review** with the following rubric (score 1-10):

**Critical checks** (must all pass, any failure = score ≤ 5):
1. **Content accuracy** — No fabricated data, all numbers match paper
2. **Text readability** — All text readable at simulated 1.5m distance (no text too small)
3. **No clipping** — All content visible, no cut-off figures or text
4. **Column alignment** — Row bands align across all columns

**Secondary checks** (affect score 6-10):
5. **Visual hierarchy** — Title → stat banner → body flow is immediately clear
6. **Figure prominence** — Figures occupy 40-50% of content area
7. **Color coherence** — Card tints, accent stripes, and venue colors work harmoniously
8. **Whitespace balance** — No large empty gaps, no overly cramped sections
9. **Information density** — Can understand the contribution in 60 seconds
10. **Overall aesthetics** — Would you be proud to present this at a top venue?

**Scoring**:
- **9-10**: Print-ready, no changes needed
- **7-8**: Minor tweaks (spacing, font size adjustments)
- **5-6**: Needs revision (layout issues, readability problems)
- **1-4**: Major issues (clipping, fabricated data, broken layout)

**Step 3: Iterative refinement loop**

```
MAX_ITERATIONS = 5
SCORE_THRESHOLD = 9

for iteration in 1..MAX_ITERATIONS:
    1. Render poster to poster/poster_v{iteration}.png (200 DPI)
    2. Claude reads the PNG and performs STRICT visual review
    3. Score the poster (1-10) with detailed feedback
    4. If score >= SCORE_THRESHOLD → PASS, proceed to Phase 6
    5. If score < SCORE_THRESHOLD:
       a. Identify top 3 issues (ranked by visual impact)
       b. Generate targeted LaTeX fixes for each issue
       c. Apply fixes to main.tex
       d. Recompile (Phase 4 error loop)
       e. Continue to next iteration
    6. Save all versions: poster/poster_v{iteration}.png
```

> ⚠️ **All versions are preserved.** Never overwrite previous renders. Save as `poster_v1.png`, `poster_v2.png`, etc. This allows comparison and rollback.

> ⚠️ **Targeted fixes only.** Each iteration should fix at most 3 specific issues. Do NOT rewrite the entire LaTeX — small, focused edits prevent regression.

**Optional: Gemini visual generation** (if `mcp__illustrator__run` is available):

For poster elements that need custom illustrations (e.g., hero architecture diagram, method workflow), use the Gemini illustration pipeline:
1. Write a detailed specification for the illustration
2. Call `mcp__illustrator__run` with the specification
3. Claude reviews the generated image for accuracy
4. Iterate until score ≥ 9 or max 3 attempts
5. Save final illustration to `poster/figures/` and embed in LaTeX

**Step 4: Save visual review log**

Append all iteration scores and feedback to `poster/POSTER_VISUAL_REVIEW.md`:

```markdown
# Visual Review Log

## Iteration 1 — Score: 7/10
- Issue 1: Title font too small (72pt → should be 84pt+)
- Issue 2: Results figure clipped at bottom
- Issue 3: Stat banner numbers not prominent enough
- Fixes applied: [list of changes]

## Iteration 2 — Score: 9/10
- All critical checks pass
- Minor: References column slightly shorter than others
- Decision: PASS — print-ready
```

### Phase 6: Codex MCP Review

Send the poster content plan + key LaTeX sections to GPT-5.4 xhigh for review.

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Review this academic conference poster for [VENUE].

    Evaluate using these criteria (score 1-5 each):

    1. **Information hierarchy** — Can someone understand the contribution in 60 seconds?
    2. **Text density** — Is it concise enough? (Target: 400-700 words total, bullet points only, NO abstract paragraph)
    3. **Figure prominence** — Are key results visually dominant? (Target: figures occupy 40-50% of area)
    4. **Column balance** — Are columns roughly equal height?
    5. **Readability** — Font sizes appropriate for 1.5m distance? (Title ≥90pt, body ≥34pt)
    6. **Narrative flow** — Does the poster tell a left-to-right story?
    7. **Whitespace** — Is content filling the space well? No large empty gaps?

    Poster content:
    [PASTE POSTER_CONTENT_PLAN.md]

    LaTeX source:
    [PASTE key sections of main.tex]

    Provide:
    - Score for each criterion
    - Top 3 actionable fixes (ranked by impact)
    - Overall: Ready to print? (Yes / Needs revision / Major issues)
```

Apply CRITICAL and MAJOR fixes to `poster/main.tex`. Recompile if changes were made.

Save review to `poster/POSTER_REVIEW.md`.

> ⚠️ **Important**: After applying review fixes, proceed to Phase 6 only when the poster is finalized. PPTX and SVG must be generated from the **final** LaTeX/PDF — never from an intermediate version.

### Phase 7: Editable Format Export

> ⚠️ **Generate PPTX and SVG only AFTER all revisions are complete.** This phase runs last (after review fixes) to ensure all formats contain identical content.

#### 6.1 PowerPoint (.pptx)

Generate a native PPTX using `python-pptx` (not pandoc — pandoc conversion is lossy):

```bash
python3 -c "import pptx" 2>/dev/null || pip install python-pptx
```

Write a Python script `poster/generate_pptx.py` that:
1. Creates a single-slide PPTX with poster dimensions (A0 landscape: 1189mm x 841mm)
2. Replicates the 4-column layout using positioned text boxes
3. **Embeds PNG figures** (from poster/figures/*.png — NOT PDFs, python-pptx cannot embed PDFs)
4. Applies venue color scheme (primary/secondary/accent) to title bar and section headers
5. Keeps all text editable (not images of text)
6. Uses large font sizes matching the PDF (title 86pt, body 34pt, headers 42pt, stats 68pt)
7. **Reads content from the FINAL `main.tex`** — do NOT hardcode content separately

> ⚠️ **PPTX font sizes must also be large.** A common mistake is using small fonts (17-24pt) in the PPTX while the PDF has 34pt+. The PPTX is A0-sized so needs identical large fonts.

**PPTX helper pattern:**
```python
def add_image(left, top, w, filename):
    """Add PNG image, auto-calculate height from aspect ratio."""
    path = os.path.join(FIG_DIR, filename)
    if not os.path.exists(path):
        txt(left, top, w, 60, f"[Image: {filename}]", ...)
        return top + 60
    pic = slide.shapes.add_picture(path, Mm(left), Mm(top), Mm(w))
    h_mm = pic.height / Mm(1)
    return top + h_mm
```

```bash
cd poster && python3 generate_pptx.py
# Output: poster/poster.pptx
```

#### 6.2 SVG (for Adobe Illustrator)

Convert the compiled PDF to editable SVG. **Preferred method: PyMuPDF** (always available via pip, no brew/system install needed):

```python
# Preferred: PyMuPDF (pip install pymupdf) — always works, no system deps
python3 -c "import fitz" 2>/dev/null || pip install pymupdf
python3 -c "
import fitz
doc = fitz.open('poster/main.pdf')
page = doc[0]
svg = page.get_svg_image()
with open('poster/poster.svg', 'w') as f:
    f.write(svg)
doc.close()
print('SVG saved')
"
```

```bash
# Fallback 1: pdf2svg (if installed)
which pdf2svg && pdf2svg poster/main.pdf poster/poster.svg

# Fallback 2: inkscape
which inkscape && inkscape poster/main.pdf --export-type=svg --export-filename=poster/poster.svg
```

> ⚠️ **SVG inherits all layout issues from PDF.** If the PDF has whitespace gaps or clipped figures, the SVG will too. Always fix the PDF first.

> 💡 **PyMuPDF bonus**: Can also generate PNG previews for quick visual inspection:
> ```python
> pix = page.get_pixmap(dpi=150)
> pix.save('poster/poster_preview.png')
> ```

#### 6.3 Component-based PPTX (Recommended — PDF→independent shapes)

> ⚠️ **This is the recommended PPTX export method.** It produces pixel-perfect output (from PDF) while keeping each poster card as an independent, movable/resizable shape in PowerPoint. The python-pptx rebuild (6.1) loses card styles, shadows, and colorboxes; the full-page image (single PNG) cannot be manipulated at all. This method is the best of both worlds.

**How it works**: Crop each posterbox region from the compiled PDF at 300 DPI, then embed each crop as a separate picture shape in PPTX at its exact grid position. Result: 10-15 independent shapes that can be individually selected, moved, resized, or deleted in PowerPoint.

```python
import fitz, os, tempfile, shutil
from pptx import Presentation
from pptx.util import Mm
from pptx.dml.color import RGBColor

doc = fitz.open('poster/main.pdf')
page = doc[0]
pw, ph = page.rect.width, page.rect.height

# A0 dimensions in mm (adjust for portrait/A1)
W_mm, H_mm = 1189, 841  # landscape
# W_mm, H_mm = 841, 1189  # portrait

def pts_to_mm(x, y):
    return x / pw * W_mm, y / ph * H_mm

# ── Define regions from tcbposter grid ──
# Format: name → (col_0based, row_start, col_span, row_end)
# rows=20, columns=4 for landscape (3 for portrait)
COLS = 4
row_h = ph / 20
col_w = pw / COLS

regions = {
    "title":        (0, 0, COLS, 4),
    "stats":        (0, 4, COLS, 6),
    # ... add one entry per posterbox, matching between=rowN and rowM
    # Example for 4-column landscape:
    "background":   (0, 6, 1, 11),
    "contributions":(0, 11, 1, 16),
    "references":   (0, 16, 1, 20),
    "paradigms":    (1, 6, 1, 11),
    "models":       (1, 11, 1, 20),
    "architecture": (2, 6, 1, 10),
    "results1":     (2, 10, 1, 20),
    "hallucination":(3, 6, 1, 11),
    "ablation":     (3, 11, 1, 15),
    "takeaways":    (3, 15, 1, 20),
}

# ── Create PPTX ──
prs = Presentation()
prs.slide_width = Mm(W_mm)
prs.slide_height = Mm(H_mm)
slide = prs.slides.add_slide(prs.slide_layouts[6])

# Set background
bg = slide.background
bg.fill.solid()
bg.fill.fore_color.rgb = RGBColor(0xF5, 0xF3, 0xFF)  # venue bg color

tmpdir = tempfile.mkdtemp()
mat = fitz.Matrix(300/72, 300/72)  # 300 DPI

for name, (col, r0, span, r1) in regions.items():
    # Clip rectangle in PDF points
    clip = fitz.Rect(col * col_w, r0 * row_h,
                     (col + span) * col_w, r1 * row_h)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    img_path = os.path.join(tmpdir, f"{name}.png")
    pix.save(img_path)

    # Position in mm
    left, top = pts_to_mm(clip.x0, clip.y0)
    right, bottom = pts_to_mm(clip.x1, clip.y1)

    slide.shapes.add_picture(img_path, Mm(left), Mm(top),
                             Mm(right - left), Mm(bottom - top))

prs.save('poster/poster_components.pptx')
doc.close()
shutil.rmtree(tmpdir)
```

> ⚠️ **The `regions` dict must match your `main.tex` posterbox grid exactly.** Parse the `between=rowN and rowM` values from each `\posterbox` to build this dict. If you add/remove cards in LaTeX, update the regions accordingly.

**Output comparison:**

| File | Method | Components movable | Visual fidelity | Text editable | Size |
|------|--------|:--:|:--:|:--:|----:|
| `poster.pptx` | python-pptx rebuild | Yes | Approximate | Yes | ~300 KB |
| `poster_from_pdf.pptx` | PDF→single image | No | Perfect | No | ~3 MB |
| **`poster_components.pptx`** | **PDF→per-card crops** | **Yes** | **Perfect** | No | ~2.5 MB |

> 💡 **Tip**: To edit text in `poster_components.pptx`, add a text box on top of the card image and type your replacement text. The image underneath can be deleted or kept as reference.

### Phase 8: Poster Speech Script

Generate `poster/POSTER_SPEECH.md` — a complete script for presenting the poster at a poster session.

**Structure**:

```markdown
# Poster Presentation Script

**Paper**: [title]
**Venue**: [VENUE] [YEAR]
**Estimated time**: 2-3 minutes (quick walkthrough)

## Opening (15 seconds)
"Hi, thanks for stopping by! Let me give you a quick overview of our work..."

## Motivation (30 seconds)
[2-3 sentences explaining the problem and why it matters]

## Method (45 seconds)
[3-4 sentences walking through the hero figure and key approach]

## Key Results (30 seconds)
[2-3 sentences highlighting headline numbers from figures]

## Takeaway (15 seconds)
[1-2 sentences summarizing the contribution]

## Closing
"Happy to discuss any questions! Here's a QR code for the paper and code."

---

## Anticipated Q&A

### Q1-Q5: [Most likely questions + suggested answers]
```

### Final Output Summary

```
📋 Poster generation complete:
- Type: [VENUE] poster ([POSTER_SIZE] [ORIENTATION])
- Files:
  poster/
  ├── main.tex                # LaTeX source (editable)
  ├── main.pdf                # Print-ready PDF (primary output)
  ├── poster_components.pptx  # PPTX with per-card movable shapes (recommended)
  ├── poster.pptx             # PPTX with editable text (approximate layout)
  ├── poster.svg              # Editable SVG (for Illustrator)
  ├── POSTER_CONTENT_PLAN.md
  ├── POSTER_REVIEW.md
  ├── POSTER_VISUAL_REVIEW.md
  ├── POSTER_SPEECH.md
  ├── POSTER_STATE.json
  ├── generate_pptx.py
  └── figures/                # PDF + PNG copies

Next steps:
1. Use poster_components.pptx for layout tweaks (move/resize cards)
2. Use poster.svg for fine vector editing in Illustrator
3. Practice with POSTER_SPEECH.md (target: 2-3 min walkthrough)
4. Print at A0 (300 DPI recommended)
```

## Key Rules

### Architecture
- **MUST use article class, NEVER beamer.** Beamer + tcbposter with 8+ enhanced boxes triggers `grouping levels=255` overflow. This is an architectural constraint, not fixable by style tweaks.
- **NEVER use adjustbox package.** Use plain `\includegraphics[width=...]` only.
- **NEVER use `\usepackage[most]{tcolorbox}`.** It pulls `listingsutf8.sty` which may not be installed. Use `\tcbuselibrary{poster,skins,fitting}` explicitly.
- **Use `[table]{xcolor}`** not `{xcolor}` — needed for `\rowcolor` in tables.

### Layout
- **`rows=20` and `spacing=0mm`** for tight layout. Card separation via left accent stripe + drop shadow, not grid spacing.
- **Use `between=rowN and rowM` positioning.** Not `below=name` which leaves auto-sized gaps.
- **All columns in a row band share identical row boundaries.** Never mix `row6-row11` in col 1 with `row6-row10` in col 2.
- **Adjust row distribution to match content density.** After trimming text, reduce row allocation proportionally. Cards with `valign=top` show all whitespace at the bottom.

### Content
- **Less text is more.** Target 300-500 words total. Each bullet: 5-8 words max. If it reads like a sentence, it's too long.
- **Do NOT fabricate data.** All numbers must come from `paper/sections/*.tex`.
- **No abstract paragraph.** Replace with stat banner (3-4 big-number callout boxes).
- **Figures should occupy 40-50% of poster area.** Posters are visual-first.
- **Use `\posterfig` macro** for all figures to ensure consistent spacing.
- **References: author (year). Short title. *Venue*** — no full titles.
- **De-AI polish**: Remove watch words (delve, pivotal, underscore, noteworthy, leverage, facilitate, harness).

### Color & Design
- **Card backgrounds must NOT be pure white.** Use subtle tints (e.g., `#FFF5F3`, `#F0F4FF`) that match each card's color family.
- **Poster background should be tinted** (e.g., `#EDD5D5` for ICML red theme), not white or near-white.
- **Colorbox intensity: 18-25%**, not 8-12%. Faint colorboxes are invisible on print.
- **Left accent stripe card design** (`borderline west={5pt}{0pt}{color}`) — cleaner than rounded colored boxes.
- **4 card styles** (redcard/bluecard/darkcard/highlightcard) create visual rhythm across the poster.

### Equations
- **Use `$\displaystyle ...$` inside colorboxes**, NOT `\[...\]`. Display math adds margins causing overfull hbox.
- **Reduce equation font to 26-28pt** inside narrow colorboxes.
- **Wrap equations in `\centering` + `\parbox{0.92\linewidth}`** for proper alignment.

### Export
- **Copy figures, never symlink.** `cp` not `ln -sf`. pdflatex can't follow symlinks.
- **Convert PDF figures to PNG for PPTX.** python-pptx cannot embed PDFs. Use `pdf2image` at 300 DPI.
- **SVG via PyMuPDF** (`fitz.Page.get_svg_image()`) — works everywhere, no system deps needed.
- **PPTX/SVG last.** Generate editable exports only after ALL LaTeX revisions are finalized.
- **Large file handling**: If the Write tool fails due to file size, use Bash (`cat << 'EOF' > file`) silently.

### Misc
- **Do NOT hallucinate citations.** Use only references from the paper's bibliography.
- **Include QR code placeholder** or code link for paper/code repository.
- **Font size minimums (article class)**: Title ≥84pt, section headers ≥40pt, body ≥34pt, captions ≥26pt, references ≥30pt, stat numbers ≥66pt.
- **Feishu notifications are optional.** If `~/.claude/feishu.json` exists, send notifications. Otherwise skip.

## Parameter Pass-Through

Parameters can be passed inline with `—` separator:

```
/paper-poster "paper/" — venue: CVPR, size: A1, orientation: portrait, columns: 3
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `venue` | NeurIPS | Conference for color scheme |
| `size` | A0 | Paper size (A0/A1) |
| `orientation` | landscape | landscape/portrait |
| `columns` | 4 | Number of content columns |
| `engine` | pdflatex | LaTeX engine (pdflatex/xelatex) |
| `auto proceed` | false | Skip checkpoints |
