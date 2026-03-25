# 学术研究完整方案：Idea Discovery Workflow + Zotero MCP

## 目录
1. [总体架构](#1-总体架构)
2. [Multi-Agent Workflow 设计](#2-multi-agent-workflow-设计)
3. [Agent 详细配置](#3-agent-详细配置)
4. [Zotero MCP 集成](#4-zotero-mcp-集成)
5. [论文搜集与存储](#5-论文搜集与存储)
6. [执行与验证](#6-执行与验证)
7. [故障排除](#7-故障排除)

---

## 1. 总体架构

### 1.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Idea Discovery Pipeline                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Stage 1: Discovery (3 Agents Parallel)                                     │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│   │ Agent 1-A   │  │ Agent 1-B   │  │ Agent 1-C   │                         │
│   │ Paper       │  │ Code Scout  │  │ Web Scanner │                         │
│   │ Researcher  │  │             │  │             │                         │
│   │ (Claude)    │  │ (Claude)    │  │ (Gemini)    │                         │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│          │                │                │                                 │
│          ▼                ▼                ▼                                 │
│   ┌──────────────────────────────────────────────────┐                      │
│   │           Checkpoint 1: Direction Review         │                      │
│   └──────────────────────┬───────────────────────────┘                      │
│                          │                                                   │
│   Stage 2: Analysis (3 Agents Parallel)                                     │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│   │ Agent 2-A   │  │ Agent 2-B   │  │ Agent 2-C   │                         │
│   │ Direction   │  │ Direction   │  │ Direction   │                         │
│   │ Analyzer A  │  │ Analyzer B  │  │ Analyzer C  │                         │
│   │ (GPT-5.4)   │  │ (GPT-5.4)   │  │ (GPT-5.4)   │                         │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│          │                │                │                                 │
│          ▼                ▼                ▼                                 │
│   ┌──────────────────────────────────────────────────┐                      │
│   │          Checkpoint 2: Select Direction          │                      │
│   └──────────────────────┬───────────────────────────┘                      │
│                          │                                                   │
│   Stage 3: Idea Generation (2 Agents Parallel)                              │
│   ┌─────────────┐  ┌─────────────┐                                          │
│   │ Agent 3-A   │  │ Agent 3-B   │                                          │
│   │ Creative    │  │ Constraint- │                                          │
│   │ Generator   │  │ Based Gen   │                                          │
│   │ (GPT-5.4)   │  │ (Claude Opus│                                          │
│   └──────┬──────┘  └──────┬──────┘                                          │
│          │                │                                                 │
│          └────────┬───────┘                                                 │
│                   ▼ Merge (Claude Opus)                                     │
│   ┌──────────────────────────────────────────────────┐                      │
│   │           Checkpoint 3: Select Ideas             │                      │
│   └──────────────────────┬───────────────────────────┘                      │
│                          │                                                   │
│   Stage 4: Validation (2 Agents Parallel)                                   │
│   ┌─────────────┐  ┌─────────────┐                                          │
│   │ Agent 4-A   │  │ Agent 4-B   │                                          │
│   │ Novelty     │  │ Prototype   │                                          │
│   │ Verifier    │  │ Prover      │                                          │
│   │ (Opus+GPT)  │  │ (Claude Sonnet)                                       │
│   └──────┬──────┘  └──────┬──────┘                                          │
│          │                │                                                 │
│          ▼                ▼                                                 │
│   ┌──────────────────────────────────────────────────┐                      │
│   │          Checkpoint 4: Go/No-Go Decision         │                      │
│   └──────────────────────┬───────────────────────────┘                      │
│                          │                                                   │
│   Stage 5: Documentation (1 Agent)                                          │
│   ┌─────────────┐                                                           │
│   │ Agent 5     │                                                           │
│   │ Report      │                                                           │
│   │ Compiler    │                                                           │
│   │ (Claude Opus)                                                          │
│   └─────────────┘                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

                              ↕ Zotero MCP Integration
                              ↕ (双向数据流)
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Zotero Knowledge Base                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                          │
│  │ Collections │  │   Papers    │  │ Annotations │                          │
│  │ (Projects)  │  │  (Metadata) │  │ (User Notes)│                          │
│  └─────────────┘  └─────────────┘  └─────────────┘                          │
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                          │
│  │  arXiv API  │  │   GitHub    │  │  Web Search │                          │
│  │  Integration│  │   Scout     │  │   Results   │                          │
│  └─────────────┘  └─────────────┘  └─────────────┘                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流向

```
输入: TOPIC (研究主题)
  ↓
┌─────────────────────────────────────────────────────────┐
│ Zotero 检查 (所有 Stage 1 Agents 启动时执行)             │
│ - 读取用户已有论文                                      │
│ - 获取用户注释和高亮                                    │
│ - 避免重复搜索                                          │
└─────────────────────────────────────────────────────────┘
  ↓
Stage 1 → 2 → 3 → 4 → 5 (Sequential with Checkpoints)
  ↓
输出: RESEARCH_REPORT.md + Zotero_Collections (自动更新)
```

---

## 2. Multi-Agent Workflow 设计

### 2.1 模型能力矩阵

| 模型 | 优势领域 | 最佳用途 |
|------|---------|---------|
| **GPT-5.4 (OpenAI)** | 推理深度、创意生成、结构化输出 | 想法生成、深度分析、评审 |
| **Claude Sonnet 4.6** | 代码理解、长文本、研究分析 | 代码分析、文献综述、技术实现 |
| **Claude Opus 4.6** | 复杂推理、长上下文、精准分析 | 深度研究、复杂验证、最终报告 |
| **Gemini 2.5 Pro** | 多模态、快速处理、大规模上下文 | 快速搜索、多源汇总、初步筛选 |

### 2.2 完整执行时序图

```
时间 →
────────────────────────────────────────────────────────────────────────

Stage 1: Parallel Discovery (3 Agents)
[Agent 1-A: Claude Sonnet] ──────┐
[Agent 1-B: Claude Sonnet] ──────┼── Checkpoint 1 (人工审核)
[Agent 1-C: Gemini 2.5] ─────────┘

Stage 2: Parallel Analysis (3 Agents)
[Agent 2-A: GPT-5.4 xhigh] ──────┐
[Agent 2-B: GPT-5.4 xhigh] ──────┼── Checkpoint 2 (选择方向)
[Agent 2-C: GPT-5.4 xhigh] ──────┘

Stage 3: Parallel Idea Generation (2 Agents)
[Agent 3-A: GPT-5.4 xhigh] ──────┐
[Agent 3-B: Claude Opus] ────────┤── Merge (Opus) ─── Checkpoint 3
                                 │
Stage 4: Parallel Validation (2 Agents)
[Agent 4-A Phase 1: Opus] ──────┐│
[Agent 4-B: Sonnet] ────────────┼┤
    ↓                           ││
[Agent 4-A Phase 2: GPT-5.4] ───┘│── Checkpoint 4 (Go/No-Go)
                                 │
Stage 5: Documentation (1 Agent)
[Agent 5: Claude Opus] ──────────┘

────────────────────────────────────────────────────────────────────────
```

---

## 3. Agent 详细配置

### 3.1 Stage 1: Discovery Agents

#### Agent 1-A: Paper Researcher

```yaml
agent_config:
  name: "paper-researcher"
  model: claude-sonnet-4.6
  temperature: 0.3
  timeout: 3600  # 1小时

  mcp_servers:
    - zotero      # 核心：读取/写入 Zotero

  tools:
    - WebSearch
    - WebFetch
    - Bash

  system_prompt: |
    你是一位学术文献分析专家。你的任务是深度分析论文，提取方法论和关键发现。

    ## 核心原则
    1. 优先检查 Zotero：始终先搜索用户的 Zotero 图书馆
    2. 尊重用户注释：用户的高亮和笔记是极高价值信号
    3. 填补知识空白：只搜索 Zotero 中没有覆盖的内容
    4. 回写发现：将新发现的高质量论文存入 Zotero

    ## 工作流程

    ### Step 1: Zotero 检查 (必须)
    - 使用 mcp__zotero__search_items 搜索 "{{TOPIC}}"
    - 获取相关条目的完整信息
    - 对于有注释的条目，读取用户高亮和评论
    - 生成 "用户已有论文摘要"

    ### Step 2: 外部搜索 (仅针对缺失内容)
    - arXiv API 搜索 (使用 arxiv_fetch.py)
    - Google Scholar 搜索
    - OpenReview / ACL Anthology 会议论文

    ### Step 3: 去重与整合
    - 基于标题相似度去重
    - 按相关性评分排序
    - 识别研究空白 (Gaps)

    ### Step 4: 存入 Zotero
    - 将新发现的高质量论文添加到 Zotero
    - 创建收藏夹 "Research Sprint: {{TOPIC}}"
    - 添加标签：["auto-discovered", "{{TOPIC}}", "to-read"]
    - 下载前 5 篇最相关论文的 PDF

    ## 输出格式

    输出文件：.context/stage1/papers_deep.md

    ```markdown
    # 论文深度分析报告: {{TOPIC}}

    ## 1. Zotero 中已有的相关论文

    ### [论文标题] (用户已读 ✓ 或 未读)
    - **作者**: ...
    - **年份**: 2024
    - **来源**: Zotero / arXiv:xxx
    - **用户笔记**: "[从 Zotero 注释提取]"
    - **关键发现**: ...

    ## 2. 新发现的高相关论文 (已存入 Zotero)

    ### [新论文] ⭐ HIGH PRIORITY
    - **arXiv**: 2403.xxxxx
    - **相关性**: 9/10
    - **创新性**: ...
    - **Zotero 链接**: [已添加]
    - **PDF**: papers/2025/2403.xxxxx.pdf

    ## 3. 研究地图 (Mermaid)
    ## 4. 关键空白 (Gaps)
    ## 5. 推荐阅读顺序
    ```

  task_template: |
    深度分析 "{{TOPIC}}" 相关论文。

    具体要求：
    1. 先检查我的 Zotero 中是否已有相关论文
    2. 如果有，获取所有注释和笔记
    3. 搜索 arXiv、Google Scholar、OpenReview
    4. 去重后选择最相关的 10-15 篇
    5. 将新发现存入 Zotero (创建收藏夹)
    6. 下载前 5 篇的 PDF
    7. 生成完整分析报告

    TOPIC: {{TOPIC}}

  output: .context/stage1/papers_deep.md
  workdir: .context/stage1/
```

**启动命令：**

```bash
export TOPIC="diffusion models for time series"

conductor agent start \
  --name "paper-researcher" \
  --model claude-sonnet-4.6 \
  --mcp zotero \
  --task "深度分析 '$TOPIC' 相关论文，充分利用 Zotero" \
  --output .context/stage1/papers_deep.md \
  --workdir .context/stage1/
```

#### Agent 1-B: Code Scout

```yaml
agent_config:
  name: "code-scout"
  model: claude-sonnet-4.6
  temperature: 0.2

  tools:
    - WebSearch
    - WebFetch
    - Bash

  system_prompt: |
    你是一位开源代码分析专家。搜索并分析相关 GitHub 仓库。

    ## 任务
    1. 搜索相关 GitHub 仓库
    2. 分析代码结构、质量和活跃度
    3. 评估可复用性和许可兼容性
    4. 提供使用建议

    ## 输出
    - 仓库列表（按星标排序）
    - 代码质量评估
    - 关键文件分析
    - 复用建议

  output: .context/stage1/code_analysis.md
```

**启动命令：**

```bash
conductor agent start \
  --name "code-scout" \
  --model claude-sonnet-4.6 \
  --task "搜索并分析 '$TOPIC' 开源代码" \
  --output .context/stage1/code_analysis.md \
  --workdir .context/stage1/
```

#### Agent 1-C: Web Scanner

```yaml
agent_config:
  name: "web-scanner"
  model: gemini-2.5-pro
  temperature: 0.4

  tools:
    - WebSearch
    - WebFetch

  system_prompt: |
    你是一位技术情报搜集专家。快速扫描技术博客、文档、论坛。

    ## 聚焦
    - 实际应用中的痛点
    - 最佳实践
    - 性能数据
    - 开发者讨论

    ## 输出
    - 技术趋势
    - 常见问题
    - 实践经验

  output: .context/stage1/web_insights.md
```

**启动命令：**

```bash
conductor agent start \
  --name "web-scanner" \
  --model gemini-2.5-pro \
  --task "扫描 '$TOPIC' 技术博客和讨论" \
  --output .context/stage1/web_insights.md \
  --workdir .context/stage1/
```

#### Checkpoint 1: Direction Review

```bash
# 等待所有 Stage 1 Agents 完成
conductor agent wait --stage 1

# 创建 Checkpoint 提示
cat > .context/checkpoints/checkpoint_1_prompt.md << 'EOF'
## Checkpoint 1: Discovery Review

请审核以下报告：
1. .context/stage1/papers_deep.md (论文分析)
2. .context/stage1/code_analysis.md (代码分析)
3. .context/stage1/web_insights.md (网络洞察)

决策：确认 2-3 个最有潜力的研究方向

回复格式：
- 方向 A: [名称] - [理由]
- 方向 B: [名称] - [理由]
- 方向 C: [名称] - [理由] (可选)
EOF
```

### 3.2 Stage 2: Analysis Agents

#### Agent 2-A/B/C: Direction Analyzers

```yaml
agent_config:
  name: "analyzer-{A|B|C}"
  model: openai/gpt-5.4
  reasoning_effort: xhigh
  temperature: 0.3

  mcp_servers:
    - zotero      # 读取更多相关论文

  system_prompt: |
    你是一位技术战略分析师。对指定技术方向进行深度分析。

    ## 分析维度
    1. 技术成熟度评估 (TRL 1-9)
    2. 生态系统健康度 (社区、商业支持)
    3. 与现有系统的兼容性
    4. 风险矩阵 (技术/商业/法律)
    5. 机会窗口分析

    ## 输出结构
    - Executive Summary
    - TRL Assessment
    - Ecosystem Analysis
    - Risk Matrix
    - Recommendations

  output: .context/stage2/analysis_{A|B|C}.md
```

**启动命令（需要根据 Checkpoint 1 的结果替换 DIRECTION）：**

```bash
# 读取 Checkpoint 1 的决策
DIRECTION_A=$(cat .context/checkpoints/checkpoint_1_response.md | grep "方向 A" | cut -d: -f2)
DIRECTION_B=$(cat .context/checkpoints/checkpoint_1_response.md | grep "方向 B" | cut -d: -f2)
DIRECTION_C=$(cat .context/checkpoints/checkpoint_1_response.md | grep "方向 C" | cut -d: -f2)

# Agent 2-A
conductor agent start \
  --name "analyzer-A" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "深度分析方向: $DIRECTION_A" \
  --output .context/stage2/analysis_A.md \
  --workdir .context/stage2/

# Agent 2-B
conductor agent start \
  --name "analyzer-B" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "深度分析方向: $DIRECTION_B" \
  --output .context/stage2/analysis_B.md \
  --workdir .context/stage2/

# Agent 2-C (如果存在)
conductor agent start \
  --name "analyzer-C" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "深度分析方向: $DIRECTION_C" \
  --output .context/stage2/analysis_C.md \
  --workdir .context/stage2/
```

#### Checkpoint 2: Select Direction

```bash
# 等待 Stage 2 完成
conductor agent wait --stage 2

# 创建 Checkpoint 提示
cat > .context/checkpoints/checkpoint_2_prompt.md << 'EOF'
## Checkpoint 2: Direction Selection

请对比以下分析报告：
1. .context/stage2/analysis_A.md
2. .context/stage2/analysis_B.md
3. .context/stage2/analysis_C.md (如果有)

决策：选择 1-2 个方向进入下一阶段

回复格式：
- 选择: [方向名称]
- 理由: [简要说明]
- 备选: [方向名称] (可选)
EOF
```

### 3.3 Stage 3: Idea Generation Agents

#### Agent 3-A: Creative Generator

```yaml
agent_config:
  name: "creative-generator"
  model: openai/gpt-5.4
  reasoning_effort: xhigh
  temperature: 0.7  # 更高温度促进创意

  mcp_servers:
    - zotero      # 确保创意基于已有文献

  system_prompt: |
    你是一位创新研究专家。基于技术方向生成 5-8 个创新想法。

    ## 每个想法必须包含
    1. 一句话标题
    2. 核心假设 (可验证)
    3. 预期贡献类型 (empirical / method / theory)
    4. 创新性评估 (1-10)
    5. 可行性评估 (1-10)
    6. 风险等级 (LOW/MEDIUM/HIGH)
    7. 预估资源需求

    ## 思考原则
    - 避免"应用 X 到 Y"的浅层想法
    - 追求答案具有双向价值的想法
    - 考虑反直觉的可能性

  output: .context/stage3/ideas_alpha.md
```

**启动命令：**

```bash
SELECTED_DIRECTION=$(cat .context/checkpoints/checkpoint_2_response.md | grep "选择:" | cut -d: -f2)

conductor agent start \
  --name "creative-generator" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh", "temperature": 0.7}' \
  --task "基于方向 '$SELECTED_DIRECTION' 生成 5-8 个创新研究想法" \
  --output .context/stage3/ideas_alpha.md \
  --workdir .context/stage3/
```

#### Agent 3-B: Constraint-Based Generator

```yaml
agent_config:
  name: "constraint-generator"
  model: claude-opus-4.6
  temperature: 0.5

  system_prompt: |
    你是一位务实的研究工程师。基于技术方向生成 3-5 个约束驱动的想法。

    ## 约束条件
    - 可在 2 周内完成原型
    - 不需要稀有数据集
    - 计算成本 < 100 GPU 小时
    - 结果可明确判断成败

    ## 每个想法必须包含
    1. 具体可执行的实验设计
    2. 明确的 success criteria
    3. 潜在失败模式及应对
    4. 所需具体资源清单

  output: .context/stage3/ideas_beta.md
```

**启动命令：**

```bash
conductor agent start \
  --name "constraint-generator" \
  --model claude-opus-4.6 \
  --task "基于方向 '$SELECTED_DIRECTION' 生成约束驱动的想法 (2周原型)" \
  --output .context/stage3/ideas_beta.md \
  --workdir .context/stage3/
```

#### Merge: Idea Consolidation

```bash
# 使用 Claude Opus 合并两份想法列表
conductor agent start \
  --name "idea-merger" \
  --model claude-opus-4.6 \
  --task "合并 .context/stage3/ideas_alpha.md 和 .context/stage3/ideas_beta.md，去重、评估冲突、排序，输出整合后的想法列表" \
  --output .context/stage3/ideas_merged.md \
  --workdir .context/stage3/
```

#### Checkpoint 3: Select Ideas

```bash
# 等待合并完成
conductor agent wait --name "idea-merger"

cat > .context/checkpoints/checkpoint_3_prompt.md << 'EOF'
## Checkpoint 3: Idea Selection

请审核整合后的想法列表：
.context/stage3/ideas_merged.md

决策：选择 1-2 个最有潜力的想法进行验证

回复格式：
- 选择想法: [标题]
- 选择理由: [说明]
- 备选想法: [标题] (可选)
EOF
```

### 3.4 Stage 4: Validation Agents

#### Agent 4-A: Novelty Verifier (Two-Phase)

**Phase 1: Claude Opus 初步查新**

```yaml
agent_config:
  name: "novelty-verifier-phase1"
  model: claude-opus-4.6
  temperature: 0.2

  tools:
    - WebSearch
    - WebFetch
    - mcp__zotero__search_items  # 检查 Zotero 中是否已有类似想法

  system_prompt: |
    你是一位学术查新专家。对选定想法进行第一轮查新。

    ## 步骤
    1. 提取 3-5 个核心技术创新点
    2. 对每个创新点进行多源搜索
    3. 记录所有潜在相关论文
    4. 初步评估新颖性

    ## 搜索范围
    - Google Scholar
    - arXiv
    - Semantic Scholar
    - OpenReview
    - 用户 Zotero (避免重复已有想法)

  output: .context/stage4/novelty_raw.md
```

**Phase 2: GPT-5.4 交叉验证**

```yaml
agent_config:
  name: "novelty-verifier-phase2"
  model: openai/gpt-5.4
  reasoning_effort: xhigh

  system_prompt: |
    你是一位严格的学术评审。基于初步查新结果进行交叉验证。

    ## 任务
    1. 验证搜索结果是否完整
    2. 识别潜在遗漏的相关工作
    3. 评估每个核心声明的新颖性 (HIGH/MEDIUM/LOW)
    4. 识别最接近的现有工作及差异化点
    5. 给出总体新颖性评分 (1-10) 和建议

  input: .context/stage4/novelty_raw.md
  output: .context/stage4/novelty_report.md
```

**启动命令：**

```bash
SELECTED_IDEA=$(cat .context/checkpoints/checkpoint_3_response.md | grep "选择想法:" | cut -d: -f2)

# Phase 1
conductor agent start \
  --name "novelty-phase1" \
  --model claude-opus-4.6 \
  --mcp zotero \
  --task "对想法 '$SELECTED_IDEA' 进行第一轮查新，搜索相关论文并记录" \
  --output .context/stage4/novelty_raw.md \
  --workdir .context/stage4/

# Phase 2 (依赖 Phase 1)
conductor agent start \
  --name "novelty-phase2" \
  --model openai/gpt-5.4 \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "基于 .context/stage4/novelty_raw.md 进行交叉验证，评估新颖性并给出评分" \
  --output .context/stage4/novelty_report.md \
  --workdir .context/stage4/ \
  --depends-on "novelty-phase1"
```

#### Agent 4-B: Feasibility Prototyper

```yaml
agent_config:
  name: "prototype-prover"
  model: claude-sonnet-4.6
  temperature: 0.3

  tools:
    - Bash
    - Read
    - Write
    - WebSearch

  constraints:
    max_time: 2h
    max_gpu_hours: 4

  system_prompt: |
    你是一位快速原型验证专家。对选定想法进行最小可行实验 (MVE)。

    ## 步骤
    1. 分析想法的核心技术假设
    2. 设计最小可行实验 (MVE)
    3. 编写原型代码
    4. 运行实验并收集结果
    5. 分析结果并给出结论

    ## 输出要求
    - 代码位置
    - 实验配置
    - 关键指标结果
    - 结论 (POSITIVE/NEGATIVE/INCONCLUSIVE)
    - 建议是否继续深入

  output: .context/stage4/prototype_result.md
```

**启动命令：**

```bash
conductor agent start \
  --name "prototype-prover" \
  --model claude-sonnet-4.6 \
  --task "对想法 '$SELECTED_IDEA' 进行快速原型验证 (2小时内完成)" \
  --output .context/stage4/prototype_result.md \
  --workdir .context/stage4/
```

#### Checkpoint 4: Go/No-Go Decision

```bash
# 等待两个验证 Agent 完成
conductor agent wait --stage 4

cat > .context/checkpoints/checkpoint_4_prompt.md << 'EOF'
## Checkpoint 4: Go/No-Go Decision

请审核验证结果：
1. .context/stage4/novelty_report.md (查新报告)
2. .context/stage4/prototype_result.md (原型结果)

决策：是否继续执行选定想法？

回复格式：
- 决策: [GO / NO-GO / PIVOT]
- 理由: [简要说明]
- 下一步建议: [具体行动]
EOF
```

### 3.5 Stage 5: Documentation Agent

#### Agent 5: Report Compiler

```yaml
agent_config:
  name: "report-compiler"
  model: claude-opus-4.6
  temperature: 0.4
  context_window: 200k  # 利用长上下文整合所有信息

  mcp_servers:
    - zotero      # 添加最终报告到 Zotero

  system_prompt: |
    你是一位学术报告撰写专家。基于所有 stage 的输出，生成完整的研究冲刺报告。

    ## 输入文件
    - .context/stage1/*.md
    - .context/stage2/*.md
    - .context/stage3/ideas_merged.md
    - .context/stage4/novelty_report.md
    - .context/stage4/prototype_result.md

    ## 输出结构
    1. Executive Summary (1页)
    2. Research Landscape (文献地图)
    3. Direction Analysis (各方向对比)
    4. Generated Ideas (想法生成过程)
    5. Selected Idea Deep Dive (选定想法深度分析)
    6. Validation Results (查新 + 原型结果)
    7. Risk Assessment (风险评估)
    8. Recommendations (明确建议)
    9. Next Steps (具体行动计划)
    10. Appendix (详细数据)

    ## 风格要求
    - 专业、客观、数据驱动
    - 明确标注不确定性和假设
    - 提供可操作的见解

  output: RESEARCH_SPRINT_REPORT.md
```

**启动命令：**

```bash
conductor agent start \
  --name "report-compiler" \
  --model claude-opus-4.6 \
  --mcp zotero \
  --task "基于所有 stage 输出生成完整研究冲刺报告，并存入 Zotero" \
  --output RESEARCH_SPRINT_REPORT.md \
  --workdir .
```

---

## 4. Zotero MCP 集成

### 4.1 环境配置

**当前配置（已验证）：**

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
      "command": "npx",
      "args": ["@xbghc/zotero-mcp"],
      "env": {
        "ZOTERO_API_KEY": "your-api-key",
        "ZOTERO_USER_ID": "your-user-id"
      }
    }
  }
}
```

**验证连接：**

```bash
claude mcp list
# 应该显示: zotero: npx @xbghc/zotero-mcp - ✓ Connected
```

### 4.2 可用工具清单

| 工具 | 功能 | Agent 使用场景 |
|------|------|---------------|
| `zotero_search_items` | 搜索 Zotero 库 | 所有 Agent 启动时检查用户已有资源 |
| `zotero_get_item` | 获取单条记录详情 | 读取特定论文的元数据 |
| `zotero_get_collections` | 获取收藏夹列表 | 按项目组织论文 |
| `zotero_create_collection` | 创建新收藏夹 | 为当前研究项目创建专属收藏夹 |
| `zotero_add_item` | 添加新条目 | 将发现的论文存入 Zotero |
| `zotero_add_annotations` | 添加笔记 | 记录 Agent 的发现和评论 |
| `zotero_attach_file` | 附加 PDF | 下载的论文 PDF 附加到条目 |

### 4.3 Zotero 工作流集成

```yaml
# 每个 Agent 启动时的标准 Zotero 流程

zotero_workflow:
  on_agent_start:
    - action: search_items
      query: "{{TOPIC}}"
      limit: 50
      purpose: "检查用户已有相关论文"

    - action: get_collections
      purpose: "了解用户的研究组织方式"

  on_relevant_paper_found:
    - action: get_item
      item_key: "{{item_key}}"
      purpose: "获取完整元数据"

    - action: get_annotations (if has_annotations)
      item_key: "{{item_key}}"
      purpose: "读取用户高亮和笔记 (极高价值)"

  on_new_discovery:
    - action: create_collection
      name: "Research Sprint: {{TOPIC}}"
      parent: null
      purpose: "创建项目收藏夹"

    - action: add_item
      item_type: "preprint"
      title: "{{paper.title}}"
      abstract: "{{paper.abstract}}"
      url: "{{paper.url}}"
      tags: ["auto-discovered", "{{TOPIC}}", "to-read"]
      collection: "Research Sprint: {{TOPIC}}"
      purpose: "存储新发现"

    - action: attach_file (if pdf_downloaded)
      item_key: "{{new_item_key}}"
      file_path: "{{local_pdf_path}}"
      purpose: "附加 PDF"

  on_agent_complete:
    - action: add_annotations
      collection: "Research Sprint: {{TOPIC}}"
      note: "Agent 分析报告摘要..."
      purpose: "记录 Agent 的分析结论"
```

### 4.4 目录结构

```
project-root/
├── .context/                        # Agent 工作目录
│   ├── stage1/
│   │   ├── papers_deep.md          # Agent 1-A 输出
│   │   ├── code_analysis.md        # Agent 1-B 输出
│   │   ├── web_insights.md         # Agent 1-C 输出
│   │   ├── zotero_results.json     # Zotero 搜索结果缓存
│   │   └── arxiv_results.json      # arXiv API 结果
│   ├── stage2/
│   │   ├── analysis_A.md
│   │   ├── analysis_B.md
│   │   └── analysis_C.md
│   ├── stage3/
│   │   ├── ideas_alpha.md          # Agent 3-A 输出
│   │   ├── ideas_beta.md           # Agent 3-B 输出
│   │   └── ideas_merged.md         # 合并后输出
│   ├── stage4/
│   │   ├── novelty_raw.md          # Phase 1 输出
│   │   ├── novelty_report.md       # Phase 2 输出
│   │   └── prototype_result.md     # Agent 4-B 输出
│   └── checkpoints/                # 人工审核点
│       ├── checkpoint_1_prompt.md
│       ├── checkpoint_1_response.md
│       ├── checkpoint_2_prompt.md
│       └── ...
│
├── papers/                          # PDF 本地缓存
│   ├── 2024/
│   └── 2025/
│
├── RESEARCH_SPRINT_REPORT.md       # 最终报告
└── run_workflow.sh                 # 一键启动脚本
```

---

## 5. 论文搜集与存储

### 5.1 多源搜索策略

```python
# Agent 1-A 的搜索优先级

PRIORITY_ORDER = [
    # Priority 1: 用户已有资源 (最了解用户)
    ("zotero", "search_items", {"query": topic, "limit": 50}),

    # Priority 2: 本地缓存 (快速、离线可用)
    ("local", "glob", {"pattern": "papers/**/*.pdf"}),

    # Priority 3: arXiv API (结构化、最新)
    ("arxiv", "api_search", {"query": topic, "max": 10, "sort": "relevance"}),

    # Priority 4: 学术搜索引擎
    ("google_scholar", "web_search", {"query": f"{topic} site:scholar.google.com"}),
    ("semantic_scholar", "api", {"query": topic, "limit": 10}),

    # Priority 5: 特定会议
    ("openreview", "web_search", {"query": f"{topic} site:openreview.net"}),
    ("acl_anthology", "web_search", {"query": f"{topic} site:aclanthology.org"}),
]
```

### 5.2 智能去重策略

```python
def deduplicate_papers(zotero_papers, arxiv_papers):
    """基于标题相似度和 arXiv ID 去重"""
    seen_arxiv_ids = set()
    seen_titles = set()
    unique_papers = []

    # 首先处理 Zotero 论文 (优先级更高)
    for paper in zotero_papers:
        arxiv_id = extract_arxiv_id(paper.get('url', ''))
        if arxiv_id:
            seen_arxiv_ids.add(arxiv_id)
        seen_titles.add(normalize_title(paper['title']))
        unique_papers.append({
            **paper,
            'source': 'zotero',
            'user_has_read': len(paper.get('annotations', [])) > 0
        })

    # 处理 arXiv 论文，跳过重复的
    for paper in arxiv_papers:
        arxiv_id = paper['id']
        title = normalize_title(paper['title'])

        if arxiv_id in seen_arxiv_ids:
            continue
        if title in seen_titles:
            continue

        unique_papers.append({
            **paper,
            'source': 'arxiv',
            'user_has_read': False
        })

    return unique_papers
```

### 5.3 PDF 下载策略

```yaml
# Agent 1-A 的 PDF 下载决策流程

for paper in ranked_papers:
  # 决策1: 用户已经在 Zotero 中有 PDF?
  if paper in zotero and zotero.has_pdf(paper):
    - 跳过下载
    - 记录: "PDF available in Zotero"

  # 决策2: 本地缓存中已有?
  elif local_cache.exists(paper.arxiv_id):
    - 跳过下载
    - 记录: "PDF available in local cache"

  # 决策3: 是否值得下载?
  elif paper.relevance_score > 0.7 and downloads_count < MAX_DOWNLOADS:
    - download_arxiv_pdf(paper.arxiv_id)
    - save_to: papers/2025/{arxiv_id}.pdf
    - add_to_zotero: true
    - downloads_count += 1

  # 决策4: 只保存元数据
  else:
    - 只保存摘要和元数据
    - 记录: "Metadata only"
```

---

## 6. 执行与验证

### 6.1 完整启动脚本

创建 `run_idea_discovery.sh`：

```bash
#!/bin/bash
# run_idea_discovery.sh
# 一键启动 Idea Discovery Workflow

set -e

TOPIC="${1:-diffusion models for time series}"
echo "🚀 启动 Idea Discovery Workflow"
echo "Topic: $TOPIC"

# 创建目录结构
mkdir -p .context/{stage1,stage2,stage3,stage4,checkpoints}
mkdir -p papers/{2024,2025}

# ===== Stage 1: Discovery =====
echo ""
echo "📚 Stage 1: Discovery (3 Agents Parallel)"

# Agent 1-A: Paper Researcher (with Zotero)
echo "  → Starting Agent 1-A: Paper Researcher"
conductor agent start \
  --name "paper-researcher" \
  --model claude-sonnet-4.6 \
  --mcp zotero \
  --task "深度分析 '$TOPIC' 相关论文。先检查 Zotero 中已有内容，然后搜索 arXiv/Google Scholar，将新发现存入 Zotero，下载前5篇 PDF" \
  --output .context/stage1/papers_deep.md \
  --workdir .context/stage1/ &

# Agent 1-B: Code Scout
echo "  → Starting Agent 1-B: Code Scout"
conductor agent start \
  --name "code-scout" \
  --model claude-sonnet-4.6 \
  --task "搜索并分析 '$TOPIC' 相关 GitHub 仓库，评估代码质量和可复用性" \
  --output .context/stage1/code_analysis.md \
  --workdir .context/stage1/ &

# Agent 1-C: Web Scanner
echo "  → Starting Agent 1-C: Web Scanner"
conductor agent start \
  --name "web-scanner" \
  --model gemini-2.5-pro \
  --task "扫描 '$TOPIC' 技术博客、论坛、教程，收集实践经验和痛点" \
  --output .context/stage1/web_insights.md \
  --workdir .context/stage1/ &

# 等待所有 Stage 1 Agents
echo "  ⏳ Waiting for Stage 1 completion..."
wait

echo ""
echo "✅ Stage 1 Complete!"
echo "请查看 .context/stage1/ 下的报告，然后运行："
echo "  ./scripts/checkpoint_1.sh"
```

### 6.2 Checkpoint 处理脚本

创建 `scripts/checkpoint_1.sh`：

```bash
#!/bin/bash
# checkpoint_1.sh

TOPIC="${1:-diffusion models for time series}"

echo "📝 Checkpoint 1: Direction Review"
echo ""
echo "请审核以下报告："
echo "  1. .context/stage1/papers_deep.md"
echo "  2. .context/stage1/code_analysis.md"
echo "  3. .context/stage1/web_insights.md"
echo ""
echo "决策后，创建 .context/checkpoints/checkpoint_1_response.md"
echo "格式："
echo "  - 方向 A: [名称] - [理由]"
echo "  - 方向 B: [名称] - [理由]"
echo "  - 方向 C: [名称] - [理由] (可选)"
echo ""
read -p "按 Enter 继续启动 Stage 2..."

# 检查响应文件是否存在
if [ ! -f .context/checkpoints/checkpoint_1_response.md ]; then
    echo "❌ Error: checkpoint_1_response.md not found"
    exit 1
fi

# 提取方向
DIRECTION_A=$(grep "方向 A:" .context/checkpoints/checkpoint_1_response.md | cut -d: -f2 | xargs)
DIRECTION_B=$(grep "方向 B:" .context/checkpoints/checkpoint_1_response.md | cut -d: -f2 | xargs)
DIRECTION_C=$(grep "方向 C:" .context/checkpoints/checkpoint_1_response.md | cut -d: -f2 | xargs)

echo ""
echo "🚀 Stage 2: Analysis (3 Agents Parallel)"

# Agent 2-A
conductor agent start \
  --name "analyzer-A" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "深度分析方向: $DIRECTION_A" \
  --output .context/stage2/analysis_A.md \
  --workdir .context/stage2/ &

# Agent 2-B
conductor agent start \
  --name "analyzer-B" \
  --model openai/gpt-5.4 \
  --mcp zotero \
  --config '{"reasoning_effort": "xhigh"}' \
  --task "深度分析方向: $DIRECTION_B" \
  --output .context/stage2/analysis_B.md \
  --workdir .context/stage2/ &

# Agent 2-C (如果有)
if [ -n "$DIRECTION_C" ]; then
    conductor agent start \
      --name "analyzer-C" \
      --model openai/gpt-5.4 \
      --mcp zotero \
      --config '{"reasoning_effort": "xhigh"}' \
      --task "深度分析方向: $DIRECTION_C" \
      --output .context/stage2/analysis_C.md \
      --workdir .context/stage2/ &
fi

echo "  ⏳ Waiting for Stage 2 completion..."
wait

echo ""
echo "✅ Stage 2 Complete!"
echo "请运行 ./scripts/checkpoint_2.sh"
```

### 6.3 Agent 验证清单

在每个 Checkpoint，验证以下内容：

#### Checkpoint 1 验证

- [ ] Agent 1-A 成功读取 Zotero (无连接错误)
- [ ] Agent 1-A 正确识别用户已有论文
- [ ] Agent 1-A 获取了用户注释 (如果有)
- [ ] Agent 1-A 将新发现存入了 Zotero
- [ ] PDF 成功下载到 papers/2025/
- [ ] Agent 1-B 找到相关 GitHub 仓库
- [ ] Agent 1-C 收集到技术博客/论坛信息

#### Checkpoint 2 验证

- [ ] 每个方向都有完整的分析报告
- [ ] 包含 TRL 评估
- [ ] 包含风险矩阵
- [ ] 包含生态系统分析

#### Checkpoint 3 验证

- [ ] 生成 5-8 个创意想法
- [ ] 生成 3-5 个约束驱动想法
- [ ] 想法合并后无重复
- [ ] 每个想法都有可行性评分

#### Checkpoint 4 验证

- [ ] 查新报告覆盖主要相关论文
- [ ] 新颖性评分合理 (1-10)
- [ ] 原型在 2 小时内完成
- [ ] 原型有明确的结论

### 6.4 成本估算

| Stage | Agents | 模型 | 预估 Token | 预估成本 |
|-------|--------|------|-----------|---------|
| 1 | 3 | Sonnet/Gemini | ~150k | $0.50 |
| 2 | 3 | GPT-5.4 xhigh | ~200k | $2.00 |
| 3 | 2+1 | GPT-5.4 + Opus | ~180k | $1.80 |
| 4 | 2+1 | Opus + GPT-5.4 | ~150k | $1.50 |
| 5 | 1 | Opus | ~100k | $1.00 |
| **总计** | **11-12** | - | **~780k** | **~$6.80** |

*注：不包括 GPU 计算成本*

---

## 7. 故障排除

### 7.1 Zotero MCP 故障

**连接失败：**

```bash
# 检查 Zotero MCP 状态
claude mcp list

# 如果显示 "✗ Failed to connect"
# 1. 检查环境变量
echo $ZOTERO_API_KEY
echo $ZOTERO_USER_ID

# 2. 验证 API 凭证
curl -s "https://api.zotero.org/users/YOUR_USER_ID/items?limit=1" \
  -H "Zotero-API-Key: YOUR_API_KEY"

# 3. 重启 MCP server
claude mcp restart zotero
```

**权限错误：**

```bash
# 检查 API Key 权限
# 1. 登录 zotero.org
# 2. Settings → Security → Edit Key
# 3. 确保勾选：
#    - Read Library
#    - Write Library (如果需要添加文献)
#    - Access Files (如果需要下载 PDF)
```

### 7.2 Agent 故障

**Agent 超时：**

```bash
# 检查 Agent 状态
conductor agent status

# 查看失败 Agent 的日志
conductor agent logs --name "failed-agent"

# 重启特定 Agent
conductor agent restart \
  --name "failed-agent" \
  --checkpoint .context/checkpoints/last_known_good/
```

**Agent 输出格式错误：**

```bash
# 检查输出文件是否存在
cat .context/stage1/papers_deep.md

# 如果格式不正确，重新运行 Agent
conductor agent restart --name "paper-researcher"
```

### 7.3 网络/API 故障

**arXiv API 限制：**

```bash
# 如果遇到 503 错误，添加延迟
# 在脚本中添加：
sleep 3  # 每次请求后延迟 3 秒
```

**Google Scholar 封锁：**

```bash
# 使用 Semantic Scholar 作为备选
# Agent 任务中指定备选搜索源
```

### 7.4 存储故障

**磁盘空间不足：**

```bash
# 检查磁盘空间
df -h .

# 清理旧 PDF
find papers/ -name "*.pdf" -mtime +30 -delete

# 或者只保留元数据
rm -rf papers/*/20*.pdf  # 保留最近论文
```

---

## 8. 最佳实践

1. **始终先检查 Zotero**：避免重复搜索用户已有论文
2. **尊重用户注释**：用户的高亮和笔记是极高价值信号
3. **结构化存储**：使用年份+主题双维度组织 PDF
4. **元数据完整**：确保每篇论文都有标题、作者、年份、来源
5. **增量更新**：后续运行只搜索新论文
6. **双向同步**：新发现应回写 Zotero，形成知识积累
7. **及时审核**：每个 Checkpoint 尽快做出决策，保持工作流顺畅
8. **备份重要数据**：定期备份 Zotero 库和 .context/ 目录

---

## 附录：快速参考

### 启动完整 Workflow

```bash
# 1. 设置主题
export TOPIC="your research topic"

# 2. 运行 Stage 1
./run_idea_discovery.sh "$TOPIC"

# 3. 审核 Checkpoint 1，然后
./scripts/checkpoint_1.sh

# 4. 审核 Checkpoint 2，然后
./scripts/checkpoint_2.sh

# 5. 审核 Checkpoint 3，然后
./scripts/checkpoint_3.sh

# 6. 审核 Checkpoint 4，然后
./scripts/checkpoint_4.sh

# 7. 生成最终报告
./scripts/stage_5.sh
```

### 单独测试 Zotero 集成

```bash
# 测试 Zotero 连接
claude -c "请列出我的 Zotero 收藏夹"

# 测试搜索
claude -c "搜索我 Zotero 中关于 'transformer' 的论文"

# 测试添加
cat > /tmp/test_paper.json << 'EOF'
{
  "title": "Test Paper",
  "abstract": "This is a test abstract",
  "url": "https://arxiv.org/abs/2401.00001"
}
EOF
```

---

**文档版本**: 1.0
**最后更新**: 2026-03-25
**Zotero MCP 版本**: @xbghc/zotero-mcp
