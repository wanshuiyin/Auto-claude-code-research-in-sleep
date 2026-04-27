# CNIPA Patent Format Guide (中国专利格式指南)

Use this reference when drafting Chinese patent applications for filing with CNIPA (国家知识产权局).

## When to Read

- Read when `JURISDICTION = "CN"` or `JURISDICTION = "ALL"`
- Read before writing claims in Chinese format
- Read during `/jurisdiction-format` for CN output
- Read when choosing between invention patent (发明专利) and utility model (实用新型)

## Applicable Law and Regulations

- Patent Law of the People's Republic of China (中华人民共和国专利法, 2020 amendment)
- Implementing Regulations of the Patent Law (专利法实施细则)
- Guidelines for Patent Examination (专利审查指南, 2023 revision)

## Document Structure

A CNIPA patent application consists of:

### 1. 权利要求书 (Claims)

**Format rules:**
- Independent claims use two-part form (two-part form / 两部式):
  - 前序部分 (Preamble): Known technical features shared with closest prior art
  - 特征部分 (Characterizing part): After "其特征在于" -- the inventive features
- Dependent claims: "根据权利要求X所述的..., 其特征在于..."
- Each claim must be a single technical solution
- Claims must be clear, concise, and supported by the description
- Method claims: "一种...的方法，其特征在于，包括以下步骤："
- Apparatus claims: "一种...的装置/设备/系统，其特征在于，包括："

**Numbering:**
- Arabic numerals: 权利要求1, 权利要求2, ...
- Dependent claims must reference prior claims by number
- Multiple dependent claims are allowed but should be used sparingly

**Example structure:**
```
1. 一种[技术主题]的方法，包括：
   前序部分的已知技术特征；
   其特征在于，还包括：
   特征部分的技术特征。

2. 根据权利要求1所述的方法，其特征在于，所述[技术特征]具体为...
```

### 2. 说明书 (Description)

Required sections in order:

#### 发明名称 (Title)
- Concise, typically under 25 characters
- Must reflect the technical content, not marketing language
- No trademarks, no "新型" or "改进的"
- Format: "一种[技术领域]的[技术主题]" for methods; "[技术领域]的[技术主题]装置" for apparatus

#### 技术领域 (Technical Field)
- 1-2 sentences identifying the technical domain
- Use IPC classification references where appropriate

#### 背景技术 (Background Technology)
- Describe the closest prior art (引用现有技术)
- Identify specific deficiencies (不足之处)
- This is NOT a literature review -- it directly sets up the problem the invention solves
- Must cite specific prior art documents where possible

#### 发明内容 (Summary of Invention)
Three parts:
1. **要解决的技术问题** (Technical Problem to Solve): Derived from background deficiencies
2. **技术方案** (Technical Solution): How the invention solves the problem, matching claim scope
3. **有益效果** (Beneficial Effects): Quantifiable advantages over prior art

#### 附图说明 (Brief Description of Drawings)
- List each figure with a one-sentence description
- Format: "图1是...的示意图；图2是...的流程图；"

#### 具体实施方式 (Detailed Description of Embodiments)
- At least one complete embodiment (实施例)
- Reference numerals must match figures exactly
- Describe in sufficient detail for a skilled person to practice
- Include specific parameters, ranges, materials where applicable
- Multiple embodiments strengthen the application

### 3. 说明书摘要 (Abstract)

- Maximum 300 words (typically Chinese characters)
- Must summarize the technical solution and key advantages
- Include the most representative claim number
- Abstract is for search purposes only, not for interpreting scope

### 4. 摘要附图 (Abstract Drawing)

- Select the most representative figure
- Must be one of the figures in the application

### 5. 附图 (Drawings)

- Numbered sequentially: 图1, 图2, ...
- Reference numerals in Arabic: 101, 102, 103...
- No text in figures except reference numerals and standard terms
- Black and white preferred; color only when necessary

## Word Limits and Practical Constraints

| Item | Limit |
|------|-------|
| Title | Typically under 25 characters |
| Abstract | 300 words maximum |
| Claims | No hard limit, but examiners prefer focused sets (10-20 claims typical) |
| Description | No hard limit, but excessive length delays examination |
| Figures | No hard limit, but cost increases per page |

## Fees (2026 approximate, in CNY)

| Item | Invention (发明专利) | Utility Model (实用新型) |
|------|---------------------|------------------------|
| Filing fee | 900 | 500 |
| Claims fee (per claim over 10) | 150 each | 150 each |
| Examination fee (invention only) | 2500 | N/A |
| Annual fees | Increasing by year | Increasing by year |

## Utility Model (实用新型) Specific Rules

- Covers only product shape/structure or combination thereof (产品的形状、构造或其结合)
- NO method claims allowed
- NO process claims allowed
- Lower inventive step requirement than invention patent
- No substantive examination -- only formal examination
- Faster grant: typically 6-8 months vs. 2-4 years for invention
- Shorter protection: 10 years vs. 20 years

## Critical Chinese Patent Writing Rules

### Claims (权利要求书)

1. **Continuous numbering required**: Claims must be numbered 1, 2, 3, ... sequentially without gaps. Independent and dependent claims are intermixed, NOT grouped separately. Even if independent claims are 1, 5, 8 in the hierarchy, the final numbering must be 1-10 continuous.

2. **No experimental results in claims**: Claims must describe ONLY structural features or method steps. Do NOT include detection principles, signal characteristics, or measurement results (e.g., "产生负脉冲信号", "谐振频率下降" belong in the specification, not in claims).

3. **Standard claim opening formats**:
   - Product: "1. 一种[主题]，其特征在于，包括：[组件A]、[组件B]和[组件C]。"
   - Method: "1. 一种[主题]的方法，其特征在于，包括以下步骤：步骤S1...；步骤S2...；"
   - System: "1. 一种[主题]的系统，其特征在于，包括：[组件]。"

4. **Two-part form (两部式)**: The "其特征在于" separates known features (before) from inventive features (after). Known features should be minimal — just enough to set context.

### Specification (说明书)

5. **No experimental data in 具体实施方式**: The detailed description teaches HOW to make and use the invention. Do NOT include test results, accuracy percentages, detection rates, precision values, or comparative performance data. These belong in papers, not patents.

   WRONG: "传感器对直径超过150μm的金属颗粒实现了100%的检测精度，即使在检测限处仍保持94%的高精度。"
   RIGHT: "当不锈钢颗粒通过间隙传感区域时，谐振频率下降。颗粒直径越大，频率偏移幅度越大。"

6. **Formulas and principles go in 具体实施方式, NOT 发明内容**: The "发明内容" section is a high-level overview (problem + solution + advantages). Detailed derivation, RLC circuit models, and mathematical formulas belong in "具体实施方式".

7. **有益效果 must be qualitative or derived from structure**: Avoid specific numerical claims unless they appear in the claims themselves. Use structural reasoning: "由于采用了...结构，因此具有...效果。"

8. **Use "所述" consistently**: After first introducing a component with "一个" or "一种", all subsequent references must use "所述" (the said). Example: "一个处理器" → "所述处理器".

### Common CN Patent Phrases

| Usage | Correct Chinese |
|-------|----------------|
| Introducing invention | "本发明提供一种..." |
| Problem statement | "本发明要解决的技术问题是..." |
| Solution intro | "为解决上述技术问题，本发明采用的技术方案是：" |
| Benefits intro | "本发明的有益效果是：" |
| Embodiment intro | "下面结合附图和实施例对本发明作进一步详细描述。" |
| Referring to figure | "参照图1" |
| Component reference | "印刷电路板（101）" on first mention, "印刷电路板101" thereafter |

## Chinese Patent Terminology Glossary

| Chinese | English | Usage |
|---------|---------|-------|
| 权利要求 | Claim | "权利要求1" |
| 说明书 | Description | "如说明书所述" |
| 发明名称 | Title of invention | |
| 技术领域 | Technical field | |
| 背景技术 | Background technology | |
| 发明内容 | Summary of invention | |
| 附图说明 | Brief description of drawings | |
| 具体实施方式 | Detailed description of embodiments | |
| 其特征在于 | Characterized in that | Claim divider |
| 所述 | Said / The (definite article) | "所述处理器" |
| 包括 | Comprising (open) | |
| 由...组成 | Consisting of (closed) | Use rarely |
| 可选地 | Optionally | |
| 优选地 | Preferably | |
| 在一个实施例中 | In one embodiment | |
| 在另一个实施例中 | In another embodiment | |
| 进一步地 | Further / Furthermore | Dependent claims |
| 其中 | Wherein | |
| 与...通信 | In communication with | |
| 响应于 | In response to | |
| 基于 | Based on | |
| 使得 | Such that | |
