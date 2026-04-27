---
name: paper-slides
description: "Generate conference presentation slides (beamer LaTeX → PDF + editable PPTX) from a compiled paper, with speaker notes and full talk script. Use when user says \"做PPT\", \"做幻灯片\", \"make slides\", \"conference talk\", \"presentation slides\", \"生成slides\", \"写演讲稿\", or wants beamer slides for a conference talk."
argument-hint: [paper-directory-or-talk-length]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# Paper Slides: From Paper to Conference Talk

Generate conference presentation slides from: **$ARGUMENTS**

## Context

This skill runs **after** Workflow 3 (`/paper-writing`). It takes a compiled paper and generates a presentation slide deck for conference oral talks, spotlight presentations, or poster lightning talks.

Unlike posters (single page, visual-first), slides tell a **temporal story**: each slide builds on the previous one, with progressive revelation of the research narrative. A good talk makes the audience understand *why this matters* before showing *what was done*.

## Constants

- **VENUE = `NeurIPS`** — Target venue, determines color scheme. Supported: `NeurIPS`, `ICML`, `ICLR`, `AAAI`, `ACL`, `EMNLP`, `CVPR`, `ECCV`, `GENERIC`. Override via argument.
- **TALK_TYPE = `spotlight`** — Talk format. Options: `oral` (15-20 min), `spotlight` (5-8 min), `poster-talk` (3-5 min), `invited` (30-45 min). Determines slide count and content depth.
- **TALK_MINUTES = 15** — Talk duration in minutes. Auto-adjusts slide count (~1 slide/minute for oral, ~1.5 slides/minute for spotlight). Override explicitly if needed.
- **ASPECT_RATIO = `16:9`** — Slide aspect ratio. Options: `16:9` (default, modern projectors), `4:3` (legacy).
- **SPEAKER_NOTES = true** — Generate `\note{}` blocks in beamer and corresponding PPTX notes. Set `false` for clean slides without notes.
- **PAPER_DIR = `paper/`** — Directory containing the compiled paper.
- **OUTPUT_DIR = `slides/`** — Output directory for all slide files.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for slide review.
- **AUTO_PROCEED = false** — At each checkpoint, **always wait for explicit user confirmation**.
- **COMPILER = `latexmk`** — LaTeX build tool.
- **ENGINE = `pdflatex`** — LaTeX engine. Use `xelatex` for CJK text.

> 💡 Override: `/paper-slides "paper/" — talk_type: oral, venue: ICML, minutes: 20, aspect: 4:3`

## Talk Type → Slide Count

| Talk Type | Duration | Slides | Content Depth |
|-----------|----------|:------:|---------------|
| `poster-talk` | 3-5 min | 5-8 | Problem + 1 method slide + 1 result + conclusion |
| `spotlight` | 5-8 min | 8-12 | Problem + 2 method + 2 results + conclusion |
| `oral` | 15-20 min | 15-22 | Full story with motivation, method detail, experiments, analysis |
| `invited` | 30-45 min | 25-40 | Comprehensive: background, related work, deep method, extensive results, discussion |

## Venue Color Schemes

Same as `/paper-poster`:

| Venue | Primary | Accent | Background | Text |
|-------|---------|--------|------------|------|
| NeurIPS | `#8B5CF6` | `#2563EB` | `#FFFFFF` | `#1E1E1E` |
| ICML | `#DC2626` | `#1D4ED8` | `#FFFFFF` | `#1E1E1E` |
| ICLR | `#059669` | `#0284C7` | `#FFFFFF` | `#1E1E1E` |
| CVPR | `#2563EB` | `#7C3AED` | `#FFFFFF` | `#1E1E1E` |
| GENERIC | `#334155` | `#2563EB` | `#FFFFFF` | `#1E1E1E` |

## State Persistence (Compact Recovery)

Persist state to `slides/SLIDES_STATE.json` after each phase:

```json
{
  "phase": 3,
  "venue": "NeurIPS",
  "talk_type": "spotlight",
  "slide_count": 10,
  "codex_thread_id": "019cfcf4-...",
  "status": "in_progress",
  "timestamp": "2026-03-18T15:00:00"
}
```

**On startup**: if `SLIDES_STATE.json` exists with `"status": "in_progress"` and within 24h → resume. Otherwise → fresh start.

## Workflow

### Phase 0: Input Validation & Setup

1. **Check prerequisites**:
   ```bash
   which pdflatex && which latexmk
   ```

2. **Verify paper exists**:
   ```bash
   ls $PAPER_DIR/main.tex || ls $PAPER_DIR/main.pdf
   ls $PAPER_DIR/sections/*.tex
   ls $PAPER_DIR/figures/
   ```

3. **Backup existing slides**: if `slides/` exists, copy to `slides-backup-{timestamp}/`

4. **Create output directory**: `mkdir -p slides/figures`

5. **Detect CJK**: if paper contains Chinese/Japanese/Korean, set ENGINE to `xelatex`

6. **Determine slide count**: from TALK_TYPE and TALK_MINUTES using the table above

7. **Check for resume**: read `slides/SLIDES_STATE.json` if it exists

**State**: Write `SLIDES_STATE.json` with `phase: 0`.

### Phase 1: Content Extraction & Slide Outline

Read `paper/sections/*.tex` and build a slide-by-slide outline.

**Slide template by talk type**:

#### Oral (15-22 slides)

| Slide | Purpose | Content Source | Figure? |
|:-----:|---------|----------------|:-------:|
| 1 | Title | Paper metadata | No |
| 2 | Outline | Section headers | No |
| 3-4 | Motivation & Problem | Introduction | Optional |
| 5 | Key Insight | Introduction (contribution) | No |
| 6-9 | Method | Method section | Yes (hero figure) |
| 10-14 | Results | Experiments | Yes (per slide) |
| 15-16 | Analysis / Ablations | Experiments | Yes |
| 17 | Limitations | Conclusion | No |
| 18 | Conclusion / Takeaway | Conclusion | No |
| 19 | Thank You + QR | — | QR code |

#### Spotlight (8-12 slides)

| Slide | Purpose | Content Source | Figure? |
|:-----:|---------|----------------|:-------:|
| 1 | Title | Paper metadata | No |
| 2-3 | Problem + Why It Matters | Introduction | Optional |
| 4 | Key Insight | Contribution | No |
| 5-6 | Method | Method (condensed) | Yes (hero) |
| 7-9 | Results | Key results only | Yes |
| 10 | Takeaway | Conclusion | No |
| 11 | Thank You + QR | — | QR code |

#### Poster-talk (5-8 slides)

| Slide | Purpose | Content Source | Figure? |
|:-----:|---------|----------------|:-------:|
| 1 | Title | Paper metadata | No |
| 2 | Problem | Introduction (1 slide) | No |
| 3 | Method | Method (1 slide) | Yes |
| 4-5 | Results | Key result only | Yes |
| 6 | Takeaway + QR | Conclusion | QR |

**For each slide, specify**:
- Title (max 8 words)
- 3-5 bullet points (max 8 words each)
- Figure reference (if any) from paper/figures/
- Speaker note (2-3 sentences of what to say)
- Time allocation (in seconds)

**Output**: `slides/SLIDE_OUTLINE.md`

**🚦 Checkpoint:**

```
📊 Slide outline ready:
- Talk type: [TALK_TYPE] ([TALK_MINUTES] min)
- Slide count: [N] slides
- Figures used: [N] from paper/figures/
- Time budget: [breakdown]

Slide-by-slide outline:
1. [Title slide]
2. [Motivation — 1.5 min]
3. [Problem statement — 1 min]
...

Proceed to drafting? Or adjust the outline?
```

**⛔ STOP HERE and wait for user response.** This is the most critical checkpoint — the outline determines the entire talk flow.

Options:
- **"go"** → proceed to Phase 2
- **adjustments** (e.g., "merge slides 3-4", "add a demo slide", "cut the ablation") → revise
- **"stop"** → save to `slides/SLIDE_OUTLINE.md`

**State**: Write `SLIDES_STATE.json` with `phase: 1`.

### Phase 2: Slide-by-Slide Content Drafting

For each slide in the outline, draft the actual content.

**Presentation rules (enforced strictly)**:

| Rule | Rationale |
|------|-----------|
| **One message per slide** | If a slide has two ideas, split it |
| **Max 6 lines per slide** | More than 6 lines = wall of text |
| **Max 8 words per line** | Audience reads, not listens, if text is long |
| **Sentence fragments, not sentences** | "Improves F1 by 3.2%" not "Our method improves the F1 score by 3.2 percentage points" |
| **Figure slides: figure ≥60% area** | The figure IS the content; bullets are annotations |
| **Bold key numbers** | "Achieves **94.3%** accuracy" |
| **Progressive disclosure** | Use `\pause` or `\onslide` for complex slides |
| **No Related Work slide** | Unless invited talk (30+ min) |

**For each slide, produce**:
1. `\frametitle{}`
2. Content (itemize or figure + caption)
3. `\note{}` with speaker text (if SPEAKER_NOTES=true)

### Phase 3: Generate Slides LaTeX

Create `slides/main.tex` using beamer.

**Template structure**:

```latex
\documentclass[aspectratio=169]{beamer}

% Venue theme
\usepackage{xcolor}
\definecolor{primary}{HTML}{VENUE_PRIMARY}
\definecolor{accent}{HTML}{VENUE_ACCENT}

% Clean theme
\usetheme{default}
\usecolortheme{default}
\setbeamercolor{frametitle}{fg=primary}
\setbeamercolor{title}{fg=primary}
\setbeamercolor{structure}{fg=accent}
\setbeamercolor{itemize item}{fg=primary}
\setbeamercolor{itemize subitem}{fg=accent}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{footline}{
  \hfill\insertframenumber/\inserttotalframenumber\hspace{2mm}\vspace{2mm}
}

% Packages
\usepackage{graphicx,amsmath,booktabs}
\graphicspath{{figures/}}

% Speaker notes (if enabled)
% \setbeameroption{show notes on second screen=right}

% Metadata
\title{PAPER TITLE}
\author{Author 1 \and Author 2}
\institute{Affiliation}
\date{VENUE YEAR}

\begin{document}

\begin{frame}
\titlepage
\end{frame}

% Content slides follow...

\begin{frame}{Motivation}
\begin{itemize}
  \item Bullet point 1
  \item Bullet point 2
  \item \textbf{Key insight in bold}
\end{itemize}
\note{Speaker note: explain the motivation...}
\end{frame}

% Figure slide example
\begin{frame}{Method Overview}
\centering
\includegraphics[width=0.85\textwidth]{method_overview.pdf}
\vspace{0.5em}
\begin{itemize}
  \item Key annotation about the figure
\end{itemize}
\note{Walk through the figure left to right...}
\end{frame}

% ... more slides ...

\begin{frame}{Thank You}
\centering
{\Large Questions?}\\[2em]
Paper: [URL or QR placeholder]\\
Code: [URL or QR placeholder]
\end{frame}

\end{document}
```

**Symlink figures**:
```bash
ln -sf ../paper/figures/*.pdf slides/figures/ 2>/dev/null
ln -sf ../paper/figures/*.png slides/figures/ 2>/dev/null
```

**Key formatting rules**:
- Title font: ≥28pt, venue primary color
- Body font: ≥20pt
- Footnotes: ≥14pt
- No navigation symbols
- Frame numbers in bottom-right
- Clean white background (no gradients, no decorative elements)

### Phase 4: Compile Slides

```bash
cd slides && latexmk -$ENGINE -interaction=nonstopmode main.tex
```

**Error handling loop** (max 3 attempts):
1. Parse error log
2. Fix: missing package, undefined command, file not found, overfull boxes
3. Recompile

**Verification**:
```bash
# Check slide count matches outline
pdfinfo slides/main.pdf | grep Pages
```

If page count differs significantly from outline (>2 slides off), investigate.

**State**: Write `SLIDES_STATE.json` with `phase: 4`.

### Phase 5: Codex MCP Review

Send the slide outline + selected LaTeX frames to GPT-5.4 xhigh:

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    Review this [TALK_TYPE] presentation ([TALK_MINUTES] min) for [VENUE].

    Evaluate using these criteria (score 1-5 each):

    1. **Story arc** — Does the talk build a compelling narrative? (Problem → insight → method → evidence → takeaway)
    2. **Slide density** — Any slides with too much text? (Max 6 lines, 8 words/line)
    3. **Time budget** — Is [N] slides realistic for [TALK_MINUTES] minutes?
    4. **Figure visibility** — Will figures be readable on a projector?
    5. **Opening hook** — Do slides 2-3 grab attention? (Not "In this paper, we...")
    6. **Takeaway** — Is the final message clear and memorable?
    7. **Progressive build** — Are complex ideas revealed gradually?

    Slide outline:
    [PASTE SLIDE_OUTLINE.md]

    Selected frames (LaTeX):
    [PASTE KEY FRAMES]

    Provide:
    - Score for each criterion
    - Top 3 actionable fixes
    - Overall: Ready to present? (Yes / Needs revision / Major issues)
```

Apply fixes. Recompile if LaTeX was changed.

> If reviewer delegation is unavailable in the current Codex host, stop and ask the user to enable Codex agent support before continuing Phase 6.

Save review to `slides/SLIDES_REVIEW.md`.

**State**: Write `SLIDES_STATE.json` with `phase: 5`.

### Phase 6: Speaker Notes

For each slide, ensure a `\note{}` block exists with:

1. **What to say** (2-3 complete sentences, conversational tone)
2. **Timing hint** (e.g., "spend 1 minute here", "quick — 20 seconds")
3. **Transition phrase** to the next slide (e.g., "So how do we actually implement this? Let me show you...")

Also generate `slides/speaker_notes.md` as a standalone backup:

```markdown
# Speaker Notes

## Slide 1: Title
[No speaking — wait for introduction]

## Slide 2: Motivation
"Thank you. So let me start with the problem we're trying to solve..."
[Time: 1.5 min]

## Slide 3: Problem Statement
"Specifically, the challenge is..."
→ Transition: "To address this, our key insight is..."
[Time: 1 min]

...
```

**State**: Write `SLIDES_STATE.json` with `phase: 6`.

### Phase 7: PowerPoint Export

Generate an editable PPTX using `python-pptx`:

```bash
python3 -c "import pptx" 2>/dev/null || pip install python-pptx
```

Write `slides/generate_pptx.py` that:

1. Creates a PPTX with correct aspect ratio (16:9 → 13.33" x 7.5"; 4:3 → 10" x 7.5")
2. For each beamer frame:
   - Creates a slide with matching layout
   - Title in venue primary color, bold
   - Bullet points with venue accent color markers
   - Figures embedded as images (from slides/figures/)
   - Speaker notes transferred to PPTX notes field
3. Title slide with special formatting (centered, larger title)
4. Thank You slide with centered text
5. Applies venue color scheme throughout

```bash
cd slides && python3 generate_pptx.py
# Output: slides/presentation.pptx
```

> ⚠️ If `python-pptx` is not installed, skip with a note: "Install `pip install python-pptx` to enable PowerPoint export."

**State**: Write `SLIDES_STATE.json` with `phase: 7`.

### Phase 8: Full Talk Script

Generate `slides/TALK_SCRIPT.md` — a complete, word-for-word script for the talk.

This is different from speaker notes (brief reminders). The talk script is a **full manuscript** that can be read aloud or used for practice.

```markdown
# Talk Script: [Paper Title]

**Venue**: [VENUE] [YEAR]
**Talk type**: [TALK_TYPE] ([TALK_MINUTES] min)
**Total slides**: [N]

---

## Slide 1: Title [0:00 - 0:15]

*[Wait for chair introduction]*

"Thank you [chair name]. I'm [author] from [affiliation], and today I'll be talking about [short title]."

---

## Slide 2: Motivation [0:15 - 1:30]

"Let me start with the problem. [Describe the real-world motivation in accessible terms]. This matters because [impact statement].

The current state of the art approaches this with [brief existing approach]. But there's a fundamental limitation: [gap statement]."

→ *Transition*: "So what's our key insight?"

---

## Slide 3: Key Insight [1:30 - 2:30]

"Our key observation is that [core insight in one sentence].

This leads us to propose [method name], which [one-sentence description]."

→ *Transition*: "Let me walk you through how this works."

---

## Slide 4-N: [Continue for each slide...]

...

---

## Slide [N]: Thank You [TALK_MINUTES:00]

"To summarize: we've shown that [main result]. The key takeaway is [memorable final message].

The paper and code are available at the QR code on screen. I'm happy to take questions."

---

## Time Budget Summary

| Slide | Topic | Duration | Cumulative |
|:-----:|-------|:--------:|:----------:|
| 1 | Title | 0:15 | 0:15 |
| 2 | Motivation | 1:15 | 1:30 |
| 3 | Key Insight | 1:00 | 2:30 |
| ... | ... | ... | ... |
| N | Thank You | 0:15 | [TALK_MINUTES]:00 |

**Total**: [sum] min (target: [TALK_MINUTES] min)

---

## Anticipated Q&A

### Q1: How does this compare to [strongest baseline]?
**A**: "[Specific comparison with numbers]. Our advantage is particularly clear in [specific scenario], where we see [X%] improvement."

### Q2: What are the main limitations?
**A**: "[Honest answer]. We see this as [future work direction]."

### Q3: How computationally expensive is this?
**A**: "[Training/inference cost]. Compared to [baseline], our method requires [comparison]."

### Q4: Does this generalize to [related domain]?
**A**: "[Answer based on paper's discussion section]."

### Q5: What's the most surprising finding?
**A**: "[Interesting insight from the experiments]."

### Q6: How sensitive is the method to [hyperparameter/design choice]?
**A**: "[Reference ablation study if available]."

### Q7: What's the next step for this research?
**A**: "[Future work from conclusion]."

### Q8: [Domain-specific question]
**A**: "[Answer]."
```

### Final Output Summary

```
📊 Slide generation complete:
- Talk type: [TALK_TYPE] ([TALK_MINUTES] min) for [VENUE]
- Files:
  slides/
  ├── main.tex              # Beamer LaTeX source
  ├── main.pdf              # Compiled slides (primary output)
  ├── presentation.pptx     # Editable PowerPoint
  ├── SLIDE_OUTLINE.md      # Slide-by-slide outline
  ├── SLIDES_REVIEW.md      # GPT-5.4 review feedback
  ├── speaker_notes.md      # Per-slide speaker notes
  ├── TALK_SCRIPT.md        # Full word-for-word talk script + Q&A
  ├── SLIDES_STATE.json     # State persistence
  ├── generate_pptx.py      # PPTX generation script
  └── figures/              # Symlinked from paper/figures/

Next steps:
1. Practice with TALK_SCRIPT.md (read aloud, time yourself)
2. Edit presentation.pptx for visual tweaks (animations, custom graphics)
3. Review Anticipated Q&A section before the talk
4. Do a dry run with a colleague
```

**State**: Write `SLIDES_STATE.json` with `phase: 8, status: "completed"`.

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **One message per slide.** If a slide has two ideas, split it into two slides.
- **Do NOT fabricate data.** All numbers must come from `paper/sections/*.tex`.
- **Bullet points only** — never full sentences on slides. Sentence fragments are fine.
- **Figure slides: figure ≥60% of slide area.** The figure IS the content.
- **Progressive disclosure**: Use `\pause` or `\onslide` for complex method slides.
- **De-AI polish**: Remove watch words from all slide text and talk script.
- **Do NOT hallucinate citations.** Reference only papers cited in the paper.
- **Opening hook matters**: Never start with "In this paper, we..." — start with the problem or a provocative question.
- **Font size minimums**: Title ≥28pt, body ≥20pt, footnotes ≥14pt.
- **Feishu notifications are optional.** If `~/.codex/feishu.json` exists, send notifications. If absent, skip.

## Parameter Pass-Through

```
/paper-slides "paper/" — talk_type: oral, venue: ICML, minutes: 20, aspect: 4:3, notes: false
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `venue` | NeurIPS | Conference for color scheme |
| `talk_type` | spotlight | oral/spotlight/poster-talk/invited |
| `minutes` | 15 | Talk duration |
| `aspect` | 16:9 | Aspect ratio (16:9 / 4:3) |
| `notes` | true | Generate speaker notes |
| `engine` | pdflatex | LaTeX engine |
| `auto proceed` | false | Skip checkpoints |
