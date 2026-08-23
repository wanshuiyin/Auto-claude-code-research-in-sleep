# ARIS-Cursor 移植台账

- **来源**：[wanshuiyin/Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 的本地 fork
- **安装位置**：复制本目录到 `~/.cursor/skills/aris/`（Cursor 只自动发现总控 `SKILL.md`，81 个子技能由总控按需路由）
- **移植日期**：2026-08-04
- **移植目标**：执行者+审稿者全部用 Cursor 内置模型（Task 子代理跨家族审稿），零 API key、零 CLI
- **helper 解析**：本导出不包含上游 `tools/`。克隆上游仓库后设置 `ARIS_REPO`，或把仓库绝对路径写入 `~/.aris/repo`；需要 helper 的子技能会按约定解析

## 移植状态图例

- **rewrite** = 审稿/引擎段落全量重写为 Cursor 原生
- **patch** = 局部替换（调用块/常量/描述性字眼）
- **header** = 仅加统一移植头（正文无 API 耦合）
- **stub** = 指路存根（用途已被其他技能覆盖）
- **engine-rewrite** = 更换底层引擎（搜索/图像）

## 分组清单（81）

### 文献检索（10）
| skill | 状态 | 说明 |
|---|---|---|
| arxiv | header | arXiv 公共 API，含内联 python 兜底 |
| alphaxiv | patch | alphaxiv.org 公开端点；新增 Tier-0 = 已装的 alphaXiv MCP |
| deepxiv | header | deepxiv-sdk 免费自注册 token，可选依赖 |
| semantic-scholar | header | S2 公共 API（可选免费 key 提限速） |
| openalex | header | OpenAlex 公共 API（可选免费 key） |
| exa-search | engine-rewrite | Exa API → Cursor WebSearch+WebFetch |
| web-debug-search | header | 本来就是 WebSearch/WebFetch |
| gemini-search | engine-rewrite | Gemini CLI/MCP → 原生多角度侦察（分解+WebSearch+arXiv API） |
| research-lit | patch | exa/gemini 源指向重写版；其余多源降级逻辑原样 |
| comm-lit-review | header | 知识库优先检索，WebSearch 原生 |

### 选题方向（9）
| skill | 状态 | 说明 |
|---|---|---|
| idea-creator | rewrite | 调用约定/Phase2 头脑风暴/Phase4 陪审团/tracing 全换 Task 子代理 |
| idea-discovery | patch | 编排器；常量+描述性字眼 |
| idea-discovery-robot | patch | 常量 |
| novelty-check | rewrite | Phase C 跨模型验证 → 新子代理（可自行搜索验证） |
| research-refine | rewrite | Phase2/Phase4 审稿线程 → Task/resume；REFINE_STATE.json 的 threadId 存子代理 id |
| research-refine-pipeline | header | 编排器 |
| research-wiki | header | 确定性 helper（research_wiki.py）驱动 |
| wiki-enrich | header | 同上 |
| research-pipeline | patch | 编排器；resumable-runs 验收表 reviewer 标签改为 cursor-subagent |

### 评审闭环（5）
| skill | 状态 | 说明 |
|---|---|---|
| research-review | rewrite | 深审计档；fresh+resume 双模式全换 |
| auto-review-loop | rewrite | W2 核心（21 处耦合）：medium/hard/nightmare 三档、辩论协议、Round2+ 模板、REVIEW_STATE.json 全部移植；nightmare 的仓库直读现为子代理原生能力 |
| auto-review-loop-llm | stub | → auto-review-loop（子代理审稿已覆盖"无 Codex 订阅"场景） |
| auto-review-loop-minimax | stub | → auto-review-loop |
| kill-argument | rewrite | 攻击/裁决双 fresh 线程；beast 六轴探针因 Task 支持并行反而升级（上游受 Codex 串行限制） |

### 公式证明（3）
| skill | 状态 | 说明 |
|---|---|---|
| formula-derivation | header | 纯执行侧 |
| proof-writer | header | 纯执行侧 |
| proof-checker | rewrite | Phase1/3 线程续审 + Phase3.5 盲审 fresh 线程全换 |

### 实验算力（15）
| skill | 状态 | 说明 |
|---|---|---|
| experiment-plan | header | 纯执行侧 |
| experiment-bridge | patch | Phase2 代码评审块 → Task |
| experiment-queue | header | SSH 队列 + scripts/ 已随包复制 |
| run-experiment | header | SSH/screen 部署 |
| monitor-experiment | header | 纯执行侧 |
| analyze-results | header | 纯执行侧 |
| training-check | patch | 模糊信号升级评审块 → Task |
| system-profile | header | 纯执行侧 |
| dse-loop | header | Type-A 自终止循环，无审稿依赖 |
| qzcli | header | 启智平台 CLI（用户自装） |
| vast-gpu | header | Vast.ai CLI（用户自装） |
| serverless-modal | header | Modal（用户自装） |
| experiment-audit | rewrite | 审计链；fresh 子代理 + 只读指令 |
| result-to-claim | rewrite | 裁决门；fail-closed 语义保留（REVIEW_UNAVAILABLE） |
| ablation-planner | patch | "Codex 主导设计"→ 审稿子代理主导 |

### 论文主线（13）
| skill | 状态 | 说明 |
|---|---|---|
| paper-writing | patch | W3 编排器；合同谈判/各阶段审稿块全换 |
| paper-plan | patch | 常量+审稿块（通用替换命中） |
| paper-write | patch | 同上 |
| paper-compile | header | LaTeX 本地编译 |
| paper-figure | patch | matplotlib 出图；图表质量审稿块 → Task |
| citation-audit | rewrite | 逐条引用核查；审稿子代理可用 WebSearch/curl 查 DBLP/arXiv |
| paper-claim-audit | rewrite | 零上下文 fresh 审计 |
| integrity-forensics | patch | 描述性字眼 |
| auto-paper-improvement-loop | rewrite | REVIEWER_BIAS_GUARD（fresh-thread 防分数膨胀）语义完整保留 |
| writing-systems-papers | header | 写作要领文档 |
| specification-writing | patch | 审稿调用短语 |
| overleaf-sync | header | git/rclone 同步 |
| render-html | patch | 渲染保真审稿块 → Task；REVIEW_UNAVAILABLE 兜底保留 |

### 配图展示（10）
| skill | 状态 | 说明 |
|---|---|---|
| paper-illustration | engine-rewrite | Gemini 图像 API → Cursor GenerateImage；监督循环保留 |
| paper-illustration-image2 | stub | → paper-illustration |
| figure-spec | patch | 确定性 SVG（scripts/ 已复制）；可选评审标题改字眼 |
| mermaid-diagram | header | 纯执行侧 |
| pixel-art | header | 纯执行侧 |
| paper-poster | header | 上游已弃用，重定向 poster-html |
| paper-poster-html | patch | HTML 海报（scripts/templates 已复制） |
| paper-slides | patch | beamer；审稿块 → Task |
| paper-talk | patch | W6 编排器 |
| slides-polish | patch | 逐页 fresh 审稿 → Task；无需再登录 Codex |

### 投稿基金（3）
| skill | 状态 | 说明 |
|---|---|---|
| rebuttal | patch | W4；调用约定换 Task |
| resubmit-pipeline | patch | W5；reviewer-model 参数语义改为跨家族 slug |
| grant-proposal | patch | 评审面板角色 → 审稿子代理 |

### 专利（9）
| skill | 状态 | 说明 |
|---|---|---|
| patent-pipeline | patch | 编排器 |
| invention-structuring | patch | 审稿调用短语 |
| claims-drafting | patch | 同上 + round2 resume |
| embodiment-description | header | 纯执行侧 |
| figure-description | header | 纯执行侧 |
| jurisdiction-format | header | 格式编译（shared-references/patent-format-* 已随包） |
| patent-review | patch | 审查员角色 → Task + resume |
| prior-art-search | header | 公开数据库检索 |
| patent-novelty-check | patch | 审稿调用短语 |

### 元工具（4）
| skill | 状态 | 说明 |
|---|---|---|
| meta-optimize | patch | 补丁对抗审 → Task；events.jsonl 工具名改 cursor-task-subagent |
| meta-apply | patch | 陪审 PASS 门 → fresh Task |
| feishu-notify | header | webhook，无 LLM 依赖 |
| interview-cheatsheet | patch | 数学/代码审稿 → Task |

## 共享协议层（skills/shared-references/，31 份）

- `reviewer-routing.md` — **全量重写**（本包基石：模型表/Task 映射/失败语义/换算速查）
- `reviewer-independence.md` / `review-tracing.md` / `acceptance-gate.md` / `fan-out-pattern.md` — 局部补丁（工具名与并行说明）
- `press-release-principle.md` — **新增**（非上游移植，2026-08）：写作端主张姿态参考（发布会原则）——双向对齐主张与证据、有界范围式 Limitations、披露段只许迁移/收窄/带回执撤回而不许裸删；仅写作侧加载，严禁进入审稿/审计 prompt。基于 [Adkid-Zephyr/anti-defensive-writing-Skill](https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill)（Press-Release Principle），MIT License
- 其余 25 份平台无关，原样保留

## 已知限制

1. "睡觉时跑" = 保持一个 Cursor 长对话运行；IDE 需开着（可配 KC 面板远程看进度）。
2. 审稿隔离性：跨家族内置模型 + 子代理独立上下文；相比真外部 API 少一层进程隔离，但直读仓库使审稿保真度 ≥ 上游 medium 档。
3. exa/gemini 搜索重写版的 neural 相似度/严格日期过滤为近似实现。
4. `~/.claude/skills/` 里有一批旧 ARIS 拷贝（仍引用 legacy Codex MCP）与本包同名（auto-review-loop、research-lit 等 18 个左右）——建议清理避免路由歧义（见最终报告）。
