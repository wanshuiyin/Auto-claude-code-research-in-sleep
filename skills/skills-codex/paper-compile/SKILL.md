---
name: "paper-compile"
description: "Compile LaTeX paper to PDF, fix errors, and verify output. Use when user says \\\"\u7f16\u8bd1\u8bba\u6587\\\", \\\"compile paper\\\", \\\"build PDF\\\", \\\"\u751f\u6210PDF\\\", or wants to compile LaTeX into a submission-ready PDF."
---

# Paper Compile: LaTeX to Submission-Ready PDF

Compile the LaTeX paper and fix any issues: **$ARGUMENTS**

## Constants

- **COMPILER = `latexmk`** — LaTeX build tool. Handles multi-pass compilation automatically.
- **ENGINE = `pdflatex`** — LaTeX engine. Options: `pdflatex` (default), `xelatex` (for CJK/custom fonts), `lualatex`.
- **MAX_COMPILE_ATTEMPTS = 3** — Maximum attempts to fix errors and recompile.
- **PAPER_DIR = `paper/`** — Directory containing LaTeX source files.
- **MAX_PAGES** — Page limit. ML conferences: main body to Conclusion end (excluding references & appendix). ICLR=9, NeurIPS=9, ICML=8. **IEEE venues: references ARE included in page count.** IEEE journal ≈ 12-14 pages, IEEE conference ≈ 5-8 pages (all inclusive).
- **RESCUE_ON_REPEAT_FAILURE = true** — If the same compile class fails after two attempts, preserve `compile.log` and ask for a focused rescue / second opinion before further edits.

## Workflow

### Step 1: Verify Prerequisites

Check that the compilation environment is ready:

```bash
# Check LaTeX installation
which pdflatex && which latexmk && which bibtex

# If not installed, provide instructions:
# macOS: brew install --cask mactex-no-gui
# Ubuntu: sudo apt-get install texlive-full
# Server: conda install -c conda-forge texlive-core
```

Verify all required files exist:

```bash
# Must exist
ls $PAPER_DIR/main.tex

# Should exist
ls $PAPER_DIR/references.bib
ls $PAPER_DIR/sections/*.tex
ls $PAPER_DIR/figures/*.pdf 2>/dev/null || ls $PAPER_DIR/figures/*.png 2>/dev/null
```

### Step 2: First Compilation Attempt

```bash
cd $PAPER_DIR

# Clean previous build artifacts
latexmk -C

# Full compilation (pdflatex + bibtex + pdflatex × 2)
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex 2>&1 | tee compile.log
```

### Step 3: Error Diagnosis and Auto-Fix

If compilation fails, read `compile.log` and fix common errors:

**Missing packages:**
```
! LaTeX Error: File `somepackage.sty' not found.
```
→ Install via `tlmgr install somepackage` or remove the `\usepackage` if unused.

**Undefined references:**
```
LaTeX Warning: Reference `fig:xyz' on page 3 undefined
```
→ Check `\label{fig:xyz}` exists in the correct figure environment.

**Missing figures:**
```
! LaTeX Error: File `figures/fig1.pdf' not found.
```
→ Check if the file exists with a different extension (.png vs .pdf). Update the `\includegraphics` path.

**Citation undefined:**
```
LaTeX Warning: Citation `smith2024' undefined
```
→ Add the missing entry to `references.bib` or fix the citation key.

**`[VERIFY]` markers in text:**
→ Search for `[VERIFY]` markers left by `/paper-write`. These indicate unverified citations or facts. Search for the correct information or flag to the user.

**Overfull hbox:**
```
Overfull \hbox (12.5pt too wide) in paragraph at lines 42--45
```
→ Minor: usually ignorable. If severe (>20pt), rephrase the text or adjust figure width.

**BibTeX errors:**
```
I was expecting a `,' or a `}'---line 15 of references.bib
```
→ Fix BibTeX syntax (missing comma, unmatched braces, special characters in title).

**`\crefname` undefined for custom theorem types:**
→ Ensure `\crefname{assumption}{Assumption}{Assumptions}` and similar are in the preamble after `\newtheorem{assumption}`.

### Step 4: Iterative Fix Loop

```
for attempt in 1..MAX_COMPILE_ATTEMPTS:
    compile()
    if success:
        break
    parse_errors()
    auto_fix()
```

For each error:
1. Read the error message from `compile.log`
2. Locate the source file and line number
3. Apply the fix
4. Recompile

### Step 5: Post-Compilation Checks

After successful compilation, verify the output:

```bash
# Check PDF exists and has content
ls -la main.pdf
# Check page count
pdfinfo main.pdf | grep Pages

# macOS: open for visual inspection
# open main.pdf
```

**Automated checks:**

- [ ] PDF file exists and is > 100KB (not empty/corrupt)
- [ ] Total page count is reasonable (MAX_PAGES + appendix + references)
- [ ] No "??" in the PDF (undefined references — grep the log)
- [ ] No "[?]" in the PDF (undefined citations — grep the log)
- [ ] Figures are rendered (not missing image placeholders)

```bash
# Check for undefined references
grep -c "LaTeX Warning.*undefined" compile.log

# Check for missing citations
grep -c "Citation.*undefined" compile.log
```

### Step 6: Page Count Verification

**CRITICAL**: Verify paper fits within MAX_PAGES.

**For ML conferences (ICLR/NeurIPS/ICML/CVPR/ACL/AAAI):** Main body = first page through end of Conclusion section (not necessarily §5 — could be §6, §7, or §8 depending on structure). References and appendix are NOT counted.

**For IEEE venues:** The TOTAL page count (including references) must fit within the limit. There is no separate "main body" counting — everything up to and including the references counts.

**Precise check using `pdftotext`:**
```bash
# Extract text and find where Conclusion ends vs References begin
pdftotext main.pdf - | python3 -c "
import sys
text = sys.stdin.read()
pages = text.split('\f')
for i, page in enumerate(pages):
    if 'Ethics Statement' in page or 'Reproducibility' in page:
        print(f'Conclusion ends on page {i+1}')
    if any(w in page for w in ['References', 'Bibliography']):
        lines = [l for l in page.split('\n') if l.strip()]
        for l in lines[:3]:
            if 'References' in l or 'Bibliography' in l:
                print(f'References start on page {i+1}')
                break
"
```

If Conclusion ends mid-page and References start on the same page, the main body is that page number (e.g., if both are on page 9, main body = ~8.5 pages, which is fine for a 9-page limit since it leaves room for the References header).

If over limit:
- Identify which sections are longest
- Suggest specific cuts (move proofs to appendix, compress tables, tighten writing)
- Report: "Main body is X pages (limit: MAX_PAGES). Suggestion: move [specific content] to appendix."

### Step 6.5: Stale File Detection

Check for orphaned section files not referenced by `main.tex`:

```bash
# Find all .tex files in sections/ and check which are \input'ed by main.tex
for f in paper/sections/*.tex; do
    base=$(basename "$f")
    if ! grep -q "$base" paper/main.tex; then
        echo "WARNING: $f is not referenced by main.tex — consider removing"
    fi
done
```

This prevents confusion from leftover files when section structure changes (e.g., old `5_conclusion.tex` left behind after restructuring to 7 sections).

### Step 7: Submission Readiness

For conference submission, additional checks:

- [ ] **Anonymous**: no author names, affiliations, or self-citations that reveal identity
- [ ] **Page limit**: main body within MAX_PAGES (to end of Conclusion)
- [ ] **Font embedding**: all fonts embedded in PDF
  ```bash
  pdffonts main.pdf | grep -v "yes"  # should return nothing (or only header)
  ```
- [ ] **No supplementary mixed in**: appendix clearly after `\newpage\appendix`
- [ ] **File size**: reasonable (< 50MB for most venues, < 10MB preferred)
- [ ] **No `[VERIFY]` markers**: search the PDF text for leftover markers

### Step 8: Output Summary

```markdown
## Compilation Report

- **Status**: SUCCESS / FAILED
- **PDF**: paper/main.pdf
- **Pages**: X (main body to Conclusion) + Y (references) + Z (appendix)
- **Within page limit**: YES/NO (MAX_PAGES = N)
- **Errors fixed**: [list of auto-fixed issues]
- **Warnings remaining**: [list of non-critical warnings]
- **Undefined references**: 0
- **Undefined citations**: 0

### Next Steps
- [ ] Visual inspection of PDF
- [ ] Run `/paper-write` to fix any content issues
- [ ] Submit to [venue] via OpenReview / CMT / HotCRP
```

## Key Rules

- **Never delete the user's source files** — only modify to fix errors
- **Keep compile.log** — useful for debugging
- **Don't suppress warnings** — report them, let the user decide
- **If LaTeX is not installed**, provide clear installation instructions rather than failing silently
- **Font embedding is critical** — some venues reject PDFs with non-embedded fonts
- **Page count rules differ by venue** — ML conferences: main body to Conclusion (refs excluded). **IEEE venues: total pages including references.**

## Common Venue Requirements

| Venue | Style File | Citation | Page Limit | Refs in limit? | Submission |
|-------|-----------|----------|------------|----------------|------------|
| ICLR 2026 | `iclr2026_conference.sty` | `natbib` (`\citep`/`\citet`) | 9 pages (to Conclusion end) | No | OpenReview |
| NeurIPS 2025 | `neurips_2025.sty` | `natbib` (`\citep`/`\citet`) | 9 pages (to Conclusion end) | No | OpenReview |
| ICML 2025 | `icml2025.sty` | `natbib` (`\citep`/`\citet`) | 8 pages (to Conclusion end) | No | OpenReview |
| IEEE Journal | `IEEEtran.cls` [journal] | `cite` (`\cite{}`, numeric) | ~12-14 pages (Transactions) / ~4-5 (Letters) | **Yes** | IEEE Author Portal / ScholarOne |
| IEEE Conference | `IEEEtran.cls` [conference] | `cite` (`\cite{}`, numeric) | 5-8 pages (varies by conf) | **Yes** | EDAS / IEEE Author Portal |
