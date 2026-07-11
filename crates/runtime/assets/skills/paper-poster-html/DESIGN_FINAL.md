# paper-poster-html — 收敛后的最终设计(codex 3 轮讨论产物)

日期:2026-06-05。讨论 thread:019e96dc-8350-70f0-a595-c1ad15919aa8(gpt-5.5 xhigh)。
状态:Round 2 全点收敛,本文档为实现规格。

## 0. 定位

- HTML+CSS 是新的默认 poster 路径;旧 `/paper-poster`(LaTeX tcbposter)已退役为
  重定向 stub(2026-06-07 落库决定,较本规格的 legacy 共存方案更进一步;
  旧实现仅存于 git history)。
- posterly(MIT, github.com/Chenruishuo/posterly)的 tools **vendor 进 skill**,不外部依赖
  不重写;`LICENSES/posterly-MIT.txt` + `NOTICE.md` 注明来源与 ARIS 修改。

## 1. 目录布局

```
skills/paper-poster-html/
├── SKILL.md
├── LICENSES/posterly-MIT.txt
├── NOTICE.md
├── templates/
│   ├── README.md
│   ├── COMPONENTS.md          # 组件契约目录(Q6)
│   ├── landscape_4col.html    # fork 自 posterly,de-gradient + token 化
│   ├── landscape_hero.html
│   ├── portrait_2col.html
│   └── tokens/
│       ├── generic.json       # 默认:slate-blue #2D5F8B + gold #C9A24A
│       ├── iclr.json … cvpr.json   # opt-in venue 包
└── scripts/
    ├── poster_check.py        # vendored(measure/preflight/polish/verify-final)
    ├── render_preview.py      # vendored(Playwright print render)
    ├── _posterly/…            # vendored 内部模块
    ├── style_check.py         # 新:风格硬门(12 条规则)
    ├── asset_check.py         # 新:真图溯源门
    ├── run_gates.py           # 新:canonical 顺序跑全门,写 GATE_REPORT.json
    ├── extract_pdf_figures.py # 新:PDF→contact sheet→候选裁剪
    └── preprocess_figures.py  # 新:autocrop/转格式/分辨率检查
```

工作目录输出:
```
poster_html/
├── poster.html / poster.pdf / poster_preview.png
├── POSTER_STATE.json / GATE_REPORT.json
├── CLAIM_EVIDENCE.md / FIGURE_MANIFEST.json
└── assets/{paper_figures,logos,qr,mathjax}/
```

## 2. 设计 token 纪律

- **默认色卡 = generic(所有 venue)**:accent #2D5F8B 族 + gold #C9A24A 族 + 中性色。
  venue 色卡 opt-in(`— venue-colors: true`),约束:accent S≤0.55、L∈[0.25,0.45];
  gold 族固定 H∈[38,48]、S≤0.65、L∈[0.42,0.65];**主 accent 禁紫**(H 250–285),
  除非 `— allow-purple: true`。venue identity 默认文字 badge。
- 字号必须走 `--fs-*` token scale(≤9 档,超出 warn)。
- serif 正文(Charter/Source Serif Pro/Georgia/Times New Roman)+
  sans 标题(Inter/Aptos/Helvetica Neue/Arial);mono 仅代码(Menlo/Consolas)。

## 3. style_check.py 源门规则(codex 定稿,逐条实现)

| # | 严重度 | 规则 |
|---|--------|------|
| 1 | HARD | 颜色字面量只许出现在 token 文件 / `:root` token block;例外:`data-color-exempt="logo"` 的 SVG 内部 |
| 2 | HARD | 禁 inline `style` 含颜色/字体/字号/布局关键值(豁免同上 + paper asset 内部) |
| 3 | HARD | 组件 CSS 颜色必须 `var(--…)` |
| 4 | HARD | 渲染后非中性色相聚类 ≤2(聚类半径 18°,须落在 accent/gold hue ±22°;非中性=alpha≥0.10 且 S≥0.18;豁免 `<img>`、logo、`data-source="paper"`、QR) |
| 5 | HARD | 禁 `linear-gradient`;`radial-gradient` 仅许 `.poster` 背景且所有 color stop alpha≤0.06 |
| 6 | HARD | 字体配对:正文 serif 栈、标题/表头 sans 栈 |
| 7 | HARD | 字体白名单(§2) |
| 8 | HARD | 字号必须用 `--fs-*` token 或组件 class,禁任意 px 漂移 |
| 9 | WARN | 字号 token >9 档 |
| 10 | HARD | 契约属性:论文图必须 `data-source="paper"` + `data-asset-id`;logo 豁免必须显式标注 |
| 11 | HARD | 禁自造装饰 SVG;inline SVG 仅许 logo / QR fallback / COMPONENTS.md 已收录的结构图 |
| 12 | WARN | 大面积深色(L<0.18 且 >8% poster 面积)→ 土嗨预警 |

## 4. asset_check.py 真图门

- ≥2 张 `data-source="paper"` 图;每张面积 ≥ poster 1.5%;paper-image 总面积 ≥ body 12%。
- raster natural size ≥ rendered size 1.5×(目标 2×)。
- FIGURE_MANIFEST.json 必填:source PDF hash、page、bbox、crop dpi、asset sha256、是否来自论文。
- 真图获取链:论文源 figures/(SVG/PDF→SVG 转换优先)→ PDF-only 时 PyMuPDF 300–450 DPI
  渲染 contact sheet → 自动候选 + 人工选 → 用户给 `page,x0,y0,x1,y1` bbox → 不足 2 张硬失败
  (除非 human checkpoint 显式 waiver)。

## 5. 公式门(半硬)

- `EQN/BROKEN`(MathJax 没渲染出来)= HARD(vendored measure 已有)。
- `EQN/UNDERSIZED`:.eqn inner box >80px 高且 math bbox 面积 <15% → HARD;
  <25% 或底部空白 >35% → WARN(final 前必须修复或记录 waiver)。

## 6. MathJax 本地化

Phase 0 下载 tex-svg.js 到 `poster_html/assets/mathjax/`(缓存复用),HTML 引本地路径;
下载失败 → 询问后 CDN 仅供草稿;final 的 measure 门对 MathJax 失败保持硬失败。

## 7. run_gates.py + GATE_REPORT.json

- canonical order:`preflight → style_check → asset_check → measure → polish`。
- 默认 accumulate(一次给全修复面),`--fail-fast` 可选。
- style/asset 保持独立 CLI(vendor diff 干净),run_gates.py 做编排。
- GATE_REPORT.json schema:schema_version/skill/timestamp/poster_html/canvas{source,width_cm,
  height_cm,orientation,source_url}/overall/hard_failures/warnings/gates[{name,severity,status,
  command,summary,artifacts}]。
- **polish 的 WARN 在 Phase 6 前必须清零或显式 waiver。**

## 8. Workflow phases(SKILL.md 主结构)

| Phase | 内容 | 门 | Checkpoint |
|-------|------|----|------------|
| 0 | resume + deps(Playwright 链)+ venue spec 实时调研(WebSearch/WebFetch 官方页,URL+date 入 state) | — | 🚦确认 venue/canvas |
| 0.5 | 设计问卷(layout/palette/logo/QR/source 一轮 AskUserQuestion) | — | 🚦确认设计输入 |
| 1 | paper ingest + content plan + claim→evidence 表 | codex fresh xhigh 内容审计 | 🚦全 claim OK 或用户接受 tradeoff |
| 2 | 真图提取/预处理 | asset_check + FIGURE_MANIFEST | 🚦PDF-only 时人工选裁剪 |
| 3 | scaffold + token patch | preflight + style_check | — |
| 4 | 布局硬循环 | preflight+style+asset+measure(spread<5 aim<3;footer gap 30–50;intercard 12–50;fill 95–101%;position≤2px) | — |
| 5 | 渲染 + Claude 视觉审(rubric §9) | ≤3 issue×≤3 轮;fix 限定词汇表 §10 | — |
| 6 | codex 终审(fresh xhigh,审 final HTML+PDF 不是 plan;fidelity/overclaim/residue/叙事/gate logs;不直接改文件) | 任何 fix 回 Phase 4/5 | — |
| 7 | verify-final + 报告 | PDF 1 页/尺寸/≤20MB/无 TODO/无 remote asset | 完成 |

Playwright 降级链:bundled Chromium → `python -m playwright install chromium` →
`channel="chrome"` → 仍失败则只产 content plan/scaffold,标注 "not print verified",
不许产出最终 PDF。pdfinfo 缺 → PyMuPDF 读尺寸;pdftoppm/PyMuPDF 至少一个用于 PNG。

## 9. Claude 视觉 rubric(Phase 5)

1–10 分;critical cap:无真图或 <2 张 →≤3;画布坏/裁切/公式不可读 →≤4;
≥4 个色相家族或重渐变 header →≤4;大空白卡/列 →≤5;捏造视觉 claim →≤3。
检查项:posterly-showcase gestalt / 单 accent 纪律 / 真图居中可读 / 打印层级
(title→headline→figures→details)/ 列底对齐无半空卡 / 公式占框 / serif+sans 配对 /
无渐变 kitsch / 组件一体感 / 60 秒叙事。
输出格式:`SCORE: N/10`、`CAPS_TRIGGERED`、`TOP_ISSUES(≤3)`、
`ALLOWED_FIX_TYPE: token|component|rebalance|asset|template/canvas`、`PATCH_LOOP_RISK`。
校准:旧 poster ≤3 分;posterly showcase ≥9 分。

## 10. Fix 词汇表(反补丁循环核心)

视觉审循环内只允许:
(a) 改 `:root` token 值;
(b) 整组件实例的换/删/加(组件集来自 COMPONENTS.md);
(c) 内容再平衡(卡片跨列移动 / 从论文取材增删文字 / AR 门带宽内调图);
(d) 画布/模板重选(升级路径);
(e) 组件 stylesheet 的全局改动(只许引用 token,禁新 hex);
(f) 预定义 variant 切换(`.figure--wide`、`.card--compact`、`.eqn--large`、`.nowrap` 等,
   必须已录入 COMPONENTS.md);
(g) asset fix(重裁剪/换同论文更清晰图/重跑 preprocess)。
禁止:新 inline style、新 hex、自造装饰 SVG、单元素字号 override。
**新组件禁止在视觉循环内诞生**——需要新组件 → 停,human checkpoint 录入 COMPONENTS.md,
从 Phase 3 重跑。

## 11. COMPONENTS.md 契约

每组件:purpose / allowed variants / required data attributes / token usage /
which gates inspect it / allowed fix operations / anti-patterns。
首发组件:card、numbered-card、figure-card、hero-figure、eqn、result-table、
claim-evidence、keybox、takeaways、qr-block、venue-badge、footer。

## 12. 已知失败模式防御(codex round 1 §7)

remote 资源 networkidle 假死→本地化;logo 豁免走私颜色→显式 data-color-exempt;
低清裁剪→1.5×/2× 检查;截图导致 PDF 爆体积→verify-final 20MB;
视觉审诱发新组件/新色→fix 词汇表;venue 规格过期→每次实时查+记录 URL/date;
改写引入新 claim→Phase 6 审 final HTML 不是 content plan。

## 12.5 Round-3 ACK nits(已采纳)

1. style_check 规则 8:`calc(var(--fs-*) * …)` 仅许预定义组件 variant 使用,否则成漏洞。
2. asset_check 的"paper-image 总面积 ≥ body 12%"对纯理论论文可 waiver——但首个验收案例不许 waiver。
3. Phase 0 的 venue 调研在 skill 文案里写成泛化的 "official venue page lookup"(跨工具栈映射,codex 镜像兼容)。

## 13. 验收

首个验收案例:为一篇公开的 ICLR 2026 OpenReview 论文(理论+实验混合型)重做 poster:
画布 185×90cm 横版(ICLR 官方打印服务规格),generic 色卡,
真图来自 OpenReview PDF,目标执行方视觉 rubric ≥9 + 跨模型终审通过。
(已达成:全 gate PASS、列底 spread <1px、两轮跨模型终审 PRINT-READY。)
