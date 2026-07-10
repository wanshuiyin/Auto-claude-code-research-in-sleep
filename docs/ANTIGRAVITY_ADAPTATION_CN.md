# Antigravity 适配指南（ARIS 工作流）

> 在 **Google Antigravity** 中使用 ARIS 研究工作流 —— Google DeepMind 出品的 Agent-First AI IDE。

Antigravity 原生支持与 ARIS 相同的 `SKILL.md` 格式（YAML frontmatter + Markdown body），是 ARIS 工作流最自然的宿主之一。

## 1. 关键差异：Claude Code vs Antigravity

| 概念 | Claude Code | Antigravity |
|------|-------------|-------------|
| Skill 调用 | `/skill-name "args"`（斜杠命令） | Agent 通过 `description` 自动发现；或通过 `view_file` 读取 SKILL.md |
| Skill 存放 | `~/.claude/skills/skill-name/SKILL.md` | `~/.gemini/antigravity/skills/skill-name/SKILL.md`（全局）或 `<workspace>/.agents/skills/skill-name/SKILL.md`（项目级） |
| MCP 配置 | `claude mcp add ...` | `~/.gemini/settings.json` → `mcpServers` 字段 |
| 项目说明 | 项目根目录 `CLAUDE.md` | 项目根目录 `GEMINI.md`（等效） |
| Agent 执行 | 持续 CLI 会话，自动压缩 | 编辑器侧边栏 + Manager 视图；支持多 agent 编排 |
| 文件引用 | 自动读取项目文件 | `view_file` 工具；agent 自动读取工作区文件 |
| 长任务 | 单 CLI 会话 | Agent 会话 + artifact 检查点 |
| 可用模型 | Claude Opus 4.6 / Sonnet 4.6 | **Gemini 3.1 Pro (high)**、**Claude Opus 4.6 (Thinking)**、GPT-OSS-120B |

## 2. 模型选择

Antigravity 支持多种模型作为**执行器**（运行 ARIS 工作流的模型）：

| 模型 | 最适合 | 配置方式 |
|------|--------|---------|
| **Claude Opus 4.6 (Thinking)** | 复杂推理、长流水线、代码生成 | 模型选择器 → `Claude Opus 4.6 (Thinking)` |
| **Gemini 3.1 Pro (high)** | 快速迭代、大上下文、Google 生态集成 | 模型选择器 → `Gemini 3.1 Pro`，推理力度设为 `high` |

> **提示：** Claude Opus 4.6 (Thinking) 和 Gemini 3.1 Pro (high) 各有优势。Claude Opus 擅长逐步推理和代码准确性；Gemini 3.1 Pro 上下文窗口更大、响应速度更快。请根据工作流需求选择。

### 模型特定说明

**Claude Opus 4.6 (Thinking)：**
- 默认启用扩展思考模式——适合复杂的研究推理
- ARIS skill 指令会被非常忠实地执行
- 长审阅 prompt 可能较慢，但更彻底

**Gemini 3.1 Pro (high)：**
- 上下文窗口更大（一次处理更多项目文件）
- 原生理解 SKILL.md 格式（Google 自己的标准）
- 推理力度建议设为 `high`——添加到 `~/.gemini/settings.json`：
  ```json
  {
    "model": {
      "name": "gemini-3.1-pro-preview"
    }
  }
  ```

## 3. 安装配置

### 3.1 安装 Skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep

# 方案 A：全局安装（所有项目可用）
mkdir -p ~/.gemini/antigravity/skills
cp -r skills/* ~/.gemini/antigravity/skills/

# 方案 B：项目级安装（推荐，隔离性好）
mkdir -p /path/to/your/project/.agents/skills
cp -r skills/* /path/to/your/project/.agents/skills/
```

> **重要：** Antigravity 从 `~/.gemini/antigravity/skills/`（全局）和 `<workspace>/.agents/skills/`（项目级）发现技能。Agent 启动时看到技能名称和描述，相关时加载完整 SKILL.md 内容。

### 3.2 配置 Codex 审阅 MCP（用于审阅技能）

ARIS 使用外部 LLM（GPT-5.6-Sol via Codex）作为审阅者。在 Antigravity 中启用：

1. 安装并认证 Codex CLI：
   ```bash
   npm install -g @openai/codex
   codex login   # 用 ChatGPT 或 API key 认证
   ```

2. 在 Antigravity 中添加 MCP——编辑 `~/.gemini/settings.json`：
   ```json
   {
     "mcpServers": {
       "codex": {
         "command": "codex",
         "args": ["mcp-server"]
       }
     }
   }
   ```

   或在项目根目录创建 `.gemini/settings.json`（项目级配置）：
   ```json
   {
     "mcpServers": {
       "codex": {
         "command": "codex",
         "args": ["mcp-server"]
       }
     }
   }
   ```

3. 重启 Antigravity，验证 MCP 连接——agent 应报告 `mcp__codex__codex` 和 `mcp__codex__codex-reply` 工具可用。

### 3.3 替代审阅 MCP（无 OpenAI API）

没有 OpenAI API key？使用 [`llm-chat`](../mcp-servers/llm-chat/) MCP 服务器对接 DeepSeek/GLM/MiniMax/Kimi 等兼容接口：

1. 创建虚拟环境并安装依赖：
   ```bash
   cd /path/to/Auto-claude-code-research-in-sleep
   python3 -m venv .venv
   .venv/bin/pip install -r mcp-servers/llm-chat/requirements.txt
   ```

2. 添加 MCP——编辑`~/.gemini/antigravity/mcp_config.json`（旧版：`~/.gemini/settings.json`），路径必须为**绝对路径**：
   ```json
   {
     "mcpServers": {
       "llm-chat": {
         "command": "/path/to/Auto-claude-code-research-in-sleep/.venv/bin/python3",
         "args": ["/path/to/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py"],
         "env": {
           "LLM_BASE_URL": "https://api.deepseek.com/v1",
           "LLM_API_KEY": "your_key",
           "LLM_MODEL": "deepseek-chat"
         }
       }
     }
   }
   ```

3. 重启 Antigravity，确认 `llm-chat` MCP 在可用工具中。

详见 [LLM_API_MIX_MATCH_GUIDE.md](LLM_API_MIX_MATCH_GUIDE.md) 获取已测试的提供商配置。

### 3.4 项目说明（GEMINI.md）

Antigravity 使用 `GEMINI.md`（等价于 Claude Code 的 `CLAUDE.md`）存放项目级说明。在项目根目录创建：

```markdown
## GPU 服务器（用于自动实验）

- SSH: `ssh my-gpu-server`（密钥认证，无密码）
- GPU: 4x A100
- Conda 环境: `research` (Python 3.10 + PyTorch)
- 激活命令: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- 代码目录: `/home/user/experiments/`
- 后台任务: `screen -dmS exp0 bash -c '...'`

## 研究项目

- 课题: [你的研究方向]
- 目标会议: ICLR/NeurIPS/ICML
- 关键文件: NARRATIVE_REPORT.md, idea-stage/IDEA_REPORT.md
```

## 4. 如何调用 Skills

Antigravity 通过 `SKILL.md` 中的 YAML `description` 字段自动发现 ARIS 技能。三种方式：

### 方式 A：自然语言（推荐——Antigravity 自动发现）

直接在对话中描述需求，Antigravity 会自动匹配已安装的技能：

```
对 "discrete diffusion models 中的 factorized gap" 运行自动评审循环。
```

如果 ARIS 技能已安装（§3.1），Antigravity 会自动发现并激活 `auto-review-loop` 技能。

### 方式 B：显式引用技能文件

要求 agent 读取特定 SKILL.md：

```
读取 skills/auto-review-loop/SKILL.md 并按照其指令执行。
课题："factorized gap in discrete diffusion LMs"。
```

### 方式 C：直接粘贴指令（一次性使用）

将相关 workflow 指令直接粘贴到对话中，适合临时任务。

## 5. 工作流映射

### Workflow 1：Idea Discovery（创意发现）

**Claude Code：**
```
/idea-discovery "your research direction"
```

**Antigravity 等价：**
```
运行完整的 idea discovery 流程，方向："your research direction"。

按顺序执行以下子技能：
1. 读取并执行 skills/research-lit/SKILL.md —— 文献综述
2. 读取并执行 skills/idea-creator/SKILL.md —— 头脑风暴
3. 读取并执行 skills/novelty-check/SKILL.md —— 新颖性验证
4. 读取并执行 skills/research-review/SKILL.md —— 深度评审
5. 读取并执行 skills/research-refine-pipeline/SKILL.md —— 方法精化 + 实验规划
```

### Workflow 1.5：Experiment Bridge（实验桥接）

**Claude Code：**
```
/experiment-bridge
```

**Antigravity 等价：**
```
读取并执行 skills/experiment-bridge/SKILL.md。
读取 refine-logs/EXPERIMENT_PLAN.md 并实现实验。
通过 skills/run-experiment/SKILL.md 部署到 GPU。
```

### Workflow 2：Auto Review Loop（自动评审循环）

**Claude Code：**
```
/auto-review-loop "your paper topic"
```

**Antigravity 等价：**
```
读取并执行 skills/auto-review-loop/SKILL.md。
对 "your paper topic" 运行自动评审循环。
读取项目叙事文档、记忆文件和实验结果。
使用 MCP 工具 mcp__codex__codex 进行外部审阅。
```

> **注意：** 如果使用 `llm-chat` MCP，把 `mcp__codex__codex` 替换为 `mcp__llm-chat__chat`。或使用适配版技能：`skills/auto-review-loop-llm/SKILL.md`。

### Workflow 3：Paper Writing（论文写作）

**Claude Code：**
```
/paper-writing "NARRATIVE_REPORT.md"
```

**Antigravity 等价：**
```
读取并执行 skills/paper-writing/SKILL.md。
输入：项目根目录的 NARRATIVE_REPORT.md。

按顺序执行以下子技能：
1. 读取并执行 skills/paper-plan/SKILL.md —— 大纲 + claims-evidence matrix
2. 读取并执行 skills/paper-figure/SKILL.md —— 生成图表
3. 读取并执行 skills/paper-write/SKILL.md —— 写 LaTeX 章节
4. 读取并执行 skills/paper-compile/SKILL.md —— 编译 PDF
5. 读取并执行 skills/auto-paper-improvement-loop/SKILL.md —— 审阅与润色
```

### 全流程分阶段建议

利用 Antigravity 的**多 agent** 能力，在可能的情况下并行运行各阶段：

| 阶段 | 执行方式 | 产出文件 |
|------|---------|---------|
| 1 | 创意发现：`skills/idea-discovery/SKILL.md` + 研究方向 | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` |
| 2 | 实验桥接：`skills/experiment-bridge/SKILL.md` | 实验脚本与结果 |
| 3 | 自动评审：`skills/auto-review-loop/SKILL.md` | `review-stage/AUTO_REVIEW.md` |
| 4 | 论文写作：`skills/paper-writing/SKILL.md` + `NARRATIVE_REPORT.md` | `paper/` 目录 |

## 6. MCP 工具对照

| ARIS MCP 工具 | 作用 | 需要的 MCP Server |
|--------------|------|------------------|
| `mcp__codex__codex` | 发审阅请求到 GPT-5.6-Sol | codex |
| `mcp__codex__codex-reply` | 续接审阅线程 | codex |
| `mcp__llm-chat__chat` | 发请求到兼容 OpenAI API 模型 | llm-chat |
| `mcp__zotero__*` | 搜索 Zotero 文献库 | zotero |
| `mcp__obsidian-vault__*` | 搜索 Obsidian 笔记库 | obsidian-vault |

## 7. 状态文件与恢复

| 文件 | 作用 | 对应流程 |
|------|------|---------|
| `review-stage/REVIEW_STATE.json` | 自动评审进度 | auto-review-loop |
| `review-stage/AUTO_REVIEW.md` | 累计评审日志 | auto-review-loop |
| `idea-stage/IDEA_REPORT.md` | 创意筛选与排名 | idea-discovery |
| `PAPER_PLAN.md` | 论文大纲 + claim-evidence matrix | paper-plan |
| `refine-logs/FINAL_PROPOSAL.md` | 精化后的方法提案 | research-refine |
| `refine-logs/EXPERIMENT_PLAN.md` | 实验路线图 | experiment-plan |

中断恢复示例：

```
读取 skills/auto-review-loop/SKILL.md，然后读取 review-stage/REVIEW_STATE.json 和 review-stage/AUTO_REVIEW.md。
从保存的状态恢复自动评审循环。
```

## 8. Antigravity 独有优势

### 多 Agent 编排
使用 Antigravity 的 **Manager View** 同时运行多个 ARIS 阶段：
- Agent 1：文献综述（Workflow 1 第 1 阶段）
- Agent 2：在 GPU 上跑实验（Workflow 1.5）
- Agent 3：审阅并迭代此前结果（Workflow 2）

### 内置浏览器
Antigravity 内置浏览器，可用于：
- 预览 `/paper-figure` 生成的图表
- `/research-lit` 中的 arXiv 搜索
- 查看 `/paper-compile` 编译的 PDF

### Artifact 系统
ARIS 产出自然映射到 Antigravity 的 artifact 系统：
- `idea-stage/IDEA_REPORT.md` → implementation plan artifact
- `review-stage/AUTO_REVIEW.md` → walkthrough artifact
- `PAPER_PLAN.md` → implementation plan artifact

### 知识持久化
Antigravity 的知识系统跨对话保留上下文：
- `/auto-review-loop` 的评审发现在未来会话中可用
- 实验配置和结果持久保存在知识条目中

## 9. 常见限制与处理

| 限制 | 处理方式 |
|------|---------|
| 无 `/skill-name` 斜杠命令 | 使用自然语言（自动发现）或显式引用 SKILL.md |
| Skills 引用 `$ARGUMENTS` | 在提示词中写明实际参数 |
| SKILL.md 中用斜杠语法调用子技能 | 告诉 agent 显式读取并执行子技能的 SKILL.md 文件 |
| `allowed-tools` 不强制执行 | Antigravity agent 默认可使用所有已配置工具——实际无影响 |
| Skills 引用 `CLAUDE.md` | Antigravity 读 `GEMINI.md`——重命名或复制 `CLAUDE.md` 为 `GEMINI.md`，或告诉 agent 两个文件都读 |
| 上下文窗口因模型而异 | Claude Opus 4.6 与 Claude Code 类似；Gemini 3.1 Pro 窗口更大。必要时分阶段执行 |

## 10. 快速参考

```
# 文献综述
读取 skills/research-lit/SKILL.md，搜索 "discrete diffusion models" 相关论文。

# 创意发现（完整流程）
读取 skills/idea-discovery/SKILL.md，对 "factorized gap in discrete diffusion LMs" 运行创意发现。

# 单次深度评审
读取 skills/research-review/SKILL.md，评审我的研究：[描述或指向文件]。

# 自动评审循环
读取 skills/auto-review-loop/SKILL.md，运行自动评审循环。课题："your paper topic"。

# 论文写作
读取 skills/paper-writing/SKILL.md，根据 NARRATIVE_REPORT.md 写论文。

# 部署实验
读取 skills/run-experiment/SKILL.md 和 GEMINI.md。
部署：python train.py --lr 1e-4 --epochs 100
```

## 11. 迁移清单：Claude Code → Antigravity

- [ ] 安装 skills 到 `~/.gemini/antigravity/skills/` 或 `<project>/.agents/skills/`
- [ ] 在 `~/.gemini/settings.json` 配置 MCP 服务器
- [ ] 将 `CLAUDE.md` 内容复制到 `GEMINI.md`（或保留两者）
- [ ] 选择模型：Claude Opus 4.6 (Thinking) 或 Gemini 3.1 Pro (high)
- [ ] 用自然语言或显式技能引用替代 `/斜杠命令`
- [ ] 验证 MCP 工具可用（codex 或 llm-chat）
- [ ] 快速测试：`读取 skills/research-review/SKILL.md 并评审我的项目`
