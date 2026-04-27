---
name: jurisdiction-format
description: "Compile patent application into jurisdiction-specific filing format. Use when user says \"格式转换\", \"jurisdiction format\", \"国家格式\", \"compile patent\", or wants formatted patent documents for CN/US/EP filing."
argument-hint: [patent-directory-or-jurisdiction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# Jurisdiction Format: Patent Filing Compilation

Compile the patent application into filing-ready format based on: **$ARGUMENTS**

Analogous to `/paper-compile` but for patent document formatting instead of LaTeX.

## Constants

- `JURISDICTION = "auto"` — From pipeline or args: `CN`, `US`, `EP`, `ALL`
- `PATENT_TYPE = "invention"` — `invention` (发明专利) or `utility_model` (实用新型, CN only)
- `OUTPUT_FORMAT = "markdown"` — `markdown` (for review) or `docx` (for filing, requires python-docx)
- `OUTPUT_DIR = "patent/output/"` — Base output directory

## Inputs

1. `patent/CLAIMS.md` — drafted claims
2. `patent/specification/` — all specification sections (title, technical_field, background, summary, drawings_description, detailed_description, abstract)
3. `patent/figures/` — figure descriptions and numeral index
4. `patent/INVENTION_DISCLOSURE.md` — for metadata

## Shared References

Load `../shared-references/patent-format-cn.md` for CNIPA document structure and formatting rules.
Load `../shared-references/patent-format-us.md` for USPTO document structure.
Load `../shared-references/patent-format-ep.md` for EPO document structure.

## Workflow

### Step 1: Determine Output Jurisdictions

From `$ARGUMENTS` or constant:
- `CN` -> Generate CNIPA format only
- `US` -> Generate USPTO format only
- `EP` -> Generate EPO format only
- `ALL` -> Generate all three formats

### Step 2: Generate CN Format (if CN or ALL)

Output to `patent/output/CN/`:

#### 权利要求书 (Claims)
- Extract claims from `patent/CLAIMS.md`
- Format per CNIPA conventions:
  - Independent claims: "1. 一种[主题]的方法，...其特征在于..."
  - Dependent claims: "2. 根据权利要求1所述的方法，其特征在于..."
- Ensure Chinese terminology is correct (所述, 其特征在于, 包括, 等)

#### 说明书 (Description)
Combine all specification sections in CNIPA order:
1. 发明名称 (from title.md)
2. 技术领域 (from technical_field.md)
3. 背景技术 (from background.md)
4. 发明内容 (from summary.md — split into 技术问题/技术方案/有益效果)
5. 附图说明 (from drawings_description.md)
6. 具体实施方式 (from detailed_description.md)

#### 说明书摘要 (Abstract)
- Extract from abstract.md
- Verify word count <= 300 Chinese characters
- Include most representative claim

#### Format as markdown or docx
If `OUTPUT_FORMAT = "markdown"`:
- Write as separate .md files with clear section headers

If `OUTPUT_FORMAT = "docx"`:
- Use python-docx to create Word documents matching CNIPA templates
- Set font to 宋体 (SimSun) for body, 黑体 (SimHei) for headers
- Standard margins (上下 2.54cm, 左右 3.17cm)

### Step 3: Generate US Format (if US or ALL)

Output to `patent/output/US/`:

#### Claims Section
- Number all claims sequentially (1, 2, 3, ...)
- Format per US conventions:
  - "1. A method for [purpose], comprising:"
  - "2. The method of claim 1, wherein..."
- Ensure antecedent basis is correct ("a" -> "the")

#### Specification
Combine all sections in USPTO order:
1. Title
2. Cross-Reference to Related Applications (if any)
3. Field of the Invention
4. Background of the Invention
5. Brief Summary of the Invention
6. Brief Description of the Drawings
7. Detailed Description of Preferred Embodiments
8. Abstract

Format drawings references as "FIG. 1" (not "Figure 1").

#### Abstract
- Extract from abstract.md
- Verify word count <= 150 words / 2500 characters

#### Application Data Sheet (ADS) Template
Generate a skeleton ADS with:
- Title
- Inventor information (placeholder)
- Application type
- Entity status (small/micro/large)

### Step 4: Generate EP Format (if EP or ALL)

Output to `patent/output/EP/`:

#### Claims Section
- Format in two-part form per Rule 43(1) EPC:
  - "1. A method for [purpose], comprising [known features], characterised in that [inventive features]."
- Ensure the "characterised in that" phrase is present in all independent claims

#### Description
Combine all sections in EPO Rule 42 order:
1. Title of the Invention
2. Technical Field
3. Background Art
4. Disclosure of the Invention (problem-solution-advantage)
5. Description of Embodiments
6. Brief Description of Drawings
7. Reference Signs List (mandatory at EPO)

Format drawings references as "FIG. 1" or "Figure 1".

#### Abstract
- Extract from abstract.md
- ~150 words limit

### Step 5: Consistency Check

Verify across all generated formats:
- [ ] All claims are present in every format
- [ ] Claim numbering is consistent
- [ ] Reference numerals match specification across all formats
- [ ] No format-specific requirements are violated
- [ ] Language is correct for each jurisdiction (Chinese for CN, English for US/EP)

### Step 6: Output Summary

Write `patent/output/OUTPUT_SUMMARY.md`:

```markdown
## Patent Filing Documents

### Generated Files

#### CN (CNIPA)
| File | Description | Status |
|------|-------------|--------|
| 权利要求书.md | Claims in CN format | Complete |
| 说明书.md | Description in CN format | Complete |
| 说明书摘要.md | Abstract (CN) | Complete |

#### US (USPTO)
| File | Description | Status |
|------|-------------|--------|
| claims.md | Claims in US format | Complete |
| specification.md | Description in US format | Complete |
| abstract.md | Abstract (US) | Complete |
| ads_template.md | Application Data Sheet skeleton | Complete |

#### EP (EPO)
| File | Description | Status |
|------|-------------|--------|
| claims.md | Claims in EP format | Complete |
| description.md | Description in EP format | Complete |
| abstract.md | Abstract (EP) | Complete |

### Consistency Check
- [ ] All claims present in all formats
- [ ] Reference numerals consistent
- [ ] Language correct per jurisdiction
```

## Key Rules

- Never mix jurisdiction formats (e.g., do not include "其特征在于" in US claims).
- Claims must be identical in technical content across jurisdictions, only the format differs.
- For CN output, verify Chinese patent terminology is correct and consistent.
- For EP output, the two-part claim form is mandatory -- every independent claim must have "characterised in that."
- Abstract word limits are jurisdiction-specific and must be verified.
- The jurisdiction-format skill does NOT modify claim content -- it reformats existing content only.
- If `OUTPUT_FORMAT = "docx"`, check that python-docx is available; if not, fall back to markdown.
