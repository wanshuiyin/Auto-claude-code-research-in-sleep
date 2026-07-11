# paper-poster-html 实现约定(所有实现 agent 必读)

配合 DESIGN_FINAL.md(规格)使用。本文档定死跨文件契约——实现时**逐字遵守**,
有疑问按本文档,不要自由发挥。

## A. CSS Token 契约(templates + tokens/*.json + style_check 三方共享)

`:root` 中的 token block 必须被注释 `/* ===== DESIGN TOKENS ===== */` 和
`/* ===== END DESIGN TOKENS ===== */` 包围(style_check 靠这对注释定位 token block)。

颜色 token(只有这些地方允许出现颜色字面量):
```css
--accent: #2D5F8B;  --accent-deep: #1F4566;  --accent-light: #E8F1F8;  --accent-soft: #D7E5F0;
--gold: #C9A24A;    --gold-soft: #FFF7E0;
--text-primary: #1A1A1A;  --text-secondary: #555555;  --text-muted: #888888;
--bg-page: #F6F2F0;  --bg-card: #FFFFFF;  --bg-card-tint: #FAFAFB;  --bg-emphasis: var(--accent-light);
--border-soft: #D8D8D8;  --border-strong: var(--accent);
```

字号 scale(9 档,模板内所有 font-size 必须引用之一;`calc(var(--fs-N) * k)` 仅许
COMPONENTS.md 预定义 variant 使用):
```css
--fs-1: calc(9 * var(--u));   /* 微标签 */      --fs-2: calc(10 * var(--u));  /* 小 caption */
--fs-3: calc(11 * var(--u));  /* caption/表格 */ --fs-4: calc(12 * var(--u));  /* 正文 */
--fs-5: calc(13 * var(--u));  /* 公式/强调 */    --fs-6: calc(15 * var(--u));  /* 副标题 */
--fs-7: calc(16 * var(--u));  /* 节标题 */       --fs-8: calc(22 * var(--u));  /* banner 数字 */
--fs-9: calc(32 * var(--u));  /* 主标题 */
```

单位:`--u: 1.6px`(screen)/ `@media print { :root { --u: 1mm } }`。其余尺寸一律
`calc(N * var(--u))`,hairline 可用裸 px(≤2px)。

## B. HTML 属性契约

| 属性 | 用途 | 谁检查 |
|------|------|--------|
| `data-measure-role="poster|header|banner|body|column|card|hero|footer-strip|footer"` | vendored measure 的定位锚(原契约,勿改) | poster_check measure |
| `data-source="paper"` + `data-asset-id="<manifest id>"` | 标记来自论文的图 | asset_check + style_check 豁免 |
| `data-color-exempt="logo"` | logo/印章 SVG 的调色豁免 | style_check |
| `data-fig-layout="beside-text"` | 图文并排的 AR 门 opt-out(vendored) | poster_check polish |

**模板和最终 poster 中禁止任何 `style=` 属性**(零容忍,style_check 规则 2 实现成这样,
简单可靠)。例外:`data-color-exempt="logo"` 元素的内部 SVG 标记、`data-source="paper"`
的 `<img>` 上仅允许 `style="width: NN%"`(AR 调宽)。
为此模板必须自带 utility classes(替代 posterly 模板里的 inline style):
```css
.fs-1 … .fs-9        /* font-size: var(--fs-N) */
.mt-1 … .mt-6        /* margin-top: calc(N * var(--u)) */
.mb-1 … .mb-4        /* margin-bottom */
.w-45 .w-50 … .w-100 /* 图宽 45%…100%,步长 5 */
.text-secondary .text-muted .nowrap .text-center
```

## C. CLI 契约(scripts/)

全部 Python 3.10+,只用 stdlib + 已确认可用的 PyMuPDF(fitz)/PIL/playwright(lazy import,
缺失时给可读错误+降级指引)。每个脚本 `--help` 完整。exit code:0=pass,1=hard fail,2=用法/环境错误。

### style_check.py
```
python3 style_check.py POSTER.html [--tokens TOKENS.json] [--json OUT.json]
                       [--no-render]  # 跳过渲染门(规则4、12 标 SKIPPED)
```
实现 DESIGN_FINAL §3 的 12 条规则 + §12.5 nit 1。源门(规则 1-3,5-11)纯静态解析
(html.parser + 正则提 CSS);渲染门(规则 4、12)用 playwright 取 computed style。
色相聚类:rgba→HSL;非中性= alpha≥0.10 且 S≥0.18;greedy 聚类半径 18°(色环距离);
聚类数 ≤2 且每类中心落在 tokens 的 accent/gold hue ±22°(hue_centers 来自 --tokens JSON,
缺省从 :root 解析 --accent/--gold 算)。
JSON 输出:`{"gate":"style","status":"PASS|FAIL|WARN","rules":[{"id":1,"severity":"hard","status":"PASS","detail":"..."}]}`

### asset_check.py
```
python3 asset_check.py POSTER.html --manifest FIGURE_MANIFEST.json [--json OUT.json]
                       [--min-paper-figs 2] [--min-fig-area 0.015] [--min-total-area 0.12]
                       [--waive-total-area]   # 纯理论论文 waiver(DESIGN_FINAL §12.5 nit 2)
                       [--no-render]          # 面积检查降级为 natural-size 估算
```
检查:≥N 张 data-source="paper" 且 manifest 里 from_paper=true;每张渲染面积 ≥ poster 1.5%;
总面积 ≥ body 12%(可 waive);natural_px ≥ rendered px 1.5×(WARN 在 <2×);
manifest 必填字段齐全(见 D);文件存在且 sha256 匹配。

### run_gates.py
```
python3 run_gates.py POSTER.html [--report GATE_REPORT.json] [--fail-fast]
                     [--strict-polish] [--tokens TOKENS.json] [--manifest FIGURE_MANIFEST.json]
                     [--waive-total-area] [--no-render]
```
canonical order:preflight → style → asset → measure → polish。默认 accumulate。
子门以 subprocess 调同目录脚本(sys.executable;poster_check.py 子命令用其 CLI)。
GATE_REPORT.json 严格按 DESIGN_FINAL §7 schema(canvas 信息从 POSTER_STATE.json 读,
读不到则从 @page 解析,source 标 "page-rule")。汇总 overall=PASS/FAIL + hard_failures + warnings。

### extract_pdf_figures.py
```
python3 extract_pdf_figures.py PAPER.pdf --out DIR [--dpi 350]
        contact-sheet                      # 整页缩略 contact sheet + 自动候选框
        crop --page P --bbox x0,y0,x1,y1 --name ID [--caption-hint "..."]
        auto                               # 自动检测大图块候选(图/表),输出候选列表
```
bbox 单位 = PDF points(72dpi 坐标,fitz 默认)。crop 模式渲染该区域至 --dpi,写 PNG 到
DIR,并 upsert FIGURE_MANIFEST.json(同目录上级)。contact-sheet 写 DIR/contact_sheet_pNN.png。

### preprocess_figures.py
```
python3 preprocess_figures.py IMG... [--autocrop] [--pad 6] [--min-px 1200 700] [--manifest M.json]
```
PIL autocrop 白边(ImageChops.difference vs 白底,留 --pad px),报告 natural size,
低于 --min-px 给 WARN;改动后同步更新 manifest 的 natural_px/sha256。

## D. FIGURE_MANIFEST.json schema

```json
{
  "schema_version": 1,
  "source_pdf": {"path": "…", "sha256": "…"},
  "figures": [
    {"asset_id": "fig_method", "file": "assets/paper_figures/fig_method.png",
     "from_paper": true, "page": 3, "bbox": [72.0, 100.0, 520.0, 380.0], "dpi": 350,
     "sha256": "…", "natural_px": [2178, 1362], "caption_hint": "Figure 2: …"}
  ]
}
```

## E. 模板改造配方(posterly → ARIS fork)

对 3 个模板各做(以上游 posterly 仓库的 templates/*.html 为底):
1. 文件头注释:保留原说明,追加 "Adapted from posterly (MIT, © 2026 Ruishuo Chen) — see LICENSES/ & NOTICE.md; ARIS modifications: flat de-gradient, --fs token scale, zero-inline-style utilities, data-source/data-color-exempt contracts."
2. **去渐变**:`.poster::before` 顶条 → 纯色 `var(--accent)`;`.framework-banner`、
   `.takeaways-strip` 背景 → 纯 `var(--bg-emphasis)`;`.callout.gold` → 纯 `var(--gold)`。
   `.poster` 的 radial tint(alpha≤0.06)保留。
3. **token block**:按 §A 注释包围;加 --fs-1..9;所有 font-size 改 var(--fs-N)。
4. **消灭 inline style**:模板正文里所有 `style="…"` 换成 §B utility classes(在 CSS 段新增)。
5. **图组件**:`.figure img` 的 TODO 注释里写明契约:`<img src="assets/paper_figures/x.png" data-source="paper" data-asset-id="x" class="w-95">`。
6. logo 槽注释写明 `data-color-exempt="logo"`。
7. `data-measure-role` 一律保留。
8. @page 默认值保留(60×36in / 24×36in),在头注释加"画布重定位:同步改 @page 与 .poster 的
   width/height(各一处),ICLR 2026 main = 185cm 90cm landscape 示例"。
9. eqn 组件加 variant `.eqn--large`(font-size: calc(var(--fs-5) * 1.25),预定义 calc 豁免)。
10. 自检:改完后模板里 grep 不到 `linear-gradient`、`style="`(除 §B 两个例外注释示例)、
    裸 `#hex`(token block 与 logo SVG 例外)。

## F. tokens/*.json schema

```json
{"name": "generic",
 "accent": {"base": "#2D5F8B", "deep": "#1F4566", "light": "#E8F1F8", "soft": "#D7E5F0"},
 "gold": {"base": "#C9A24A", "soft": "#FFF7E0"},
 "neutrals": {"text_primary": "#1A1A1A", "text_secondary": "#555555", "text_muted": "#888888",
              "bg_page": "#F6F2F0", "bg_card": "#FFFFFF", "bg_card_tint": "#FAFAFB",
              "border_soft": "#D8D8D8"},
 "hue_centers": {"accent": 210, "gold": 43}}
```
venue 包约束:accent S≤0.55、L∈[0.25,0.45]、禁 H 250–285;gold 全包固定 generic 值;
light/soft 从 base 推(同 hue 低饱和高亮度)。bg_page 可随 accent 微调暖/冷但 ΔE 要小。

## G. 测试基线

上游 posterly 仓库的 examples/hello_world/poster.html 是全门 PASS 的参照(vendored 四门)。
新脚本写完后:style_check 对 hello_world 允许 FAIL(它有 inline style——posterly 原版风格),
但对我们改造后的模板(填充前)源门必须 PASS;run_gates 对脚手架预期 measure FAIL(未填充),
这是正常的(模板=脚手架)。
