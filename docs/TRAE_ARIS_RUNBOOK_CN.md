# ARIS Trae 适配指南（Workflow Runbook）

在 Trae 中使用 ARIS 研究工作流，不依赖 Claude Code 的 `/skill-name` 斜杠命令。

## 1. 关键差异：Claude Code vs Trae

| 概念 | Claude Code | Trae |
|---|---|---|
| Skill 调用 | `/skill-name "args"`（斜杠命令） | 自然语言自动发现、`#` 快速匹配、`@skills/.../SKILL.md`（文件引用） |
| Skill 存放 | `~/.claude/skills/...` | 全局 `~/.trae/skills/`（跨项目可用）或项目 `<project>/.trae/skills/`（仅当前项目），或直接引用 ARIS 仓库 `skills/` |
| MCP 配置 | `claude mcp add ...` | `Settings → MCP → 手动添加` |
| Agent 执行 | 持续 CLI 会话 | Chat/Agent 会话 |
| 文件引用 | 自动读项目 | `@filename` 显式附加上下文 |
| 长任务恢复 | 单会话自动压缩恢复 | 通过状态文件手动恢复 |

## 2. Setup
最好在trae中创建一个单独的智能体负责运行ARIS工作流，避免与其他智能体冲突，并能给ARIS工作流提供扮演角色的必要信息。
### 2.1 克隆仓库并配置 Skills

```powershell
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
```

**安装 Skills 到 Trae 的两种方式：**

方式一：通过 Trae 界面安装（推荐）

1. 进入 `设置 → 规则和技能`
2. 选择「全局」或「项目」安装范围
3. 点击「导入文件」，选择 ARIS 仓库中的 `skills/` 目录下的 SKILL.md 文件
4. 安装后即可通过自然语言描述触发技能

> **说明：** 全局安装的技能可在所有项目中通过自然语言触发；项目级安装的技能可在该项目中通过自然语言触发。

方式二：手动复制到 skills 目录

```powershell
# 全局安装（所有项目可用）
$globalSkillsDir = Join-Path $env:USERPROFILE ".trae\skills"
New-Item -ItemType Directory -Path $globalSkillsDir -Force | Out-Null
Copy-Item -Path ".\Auto-claude-code-research-in-sleep\skills\*" -Destination $globalSkillsDir -Recurse -Force

# 项目级安装（仅当前项目可用）
$projectSkillsDir = ".\.trae\skills"
New-Item -ItemType Directory -Path $projectSkillsDir -Force | Out-Null
Copy-Item -Path ".\Auto-claude-code-research-in-sleep\skills\*" -Destination $projectSkillsDir -Recurse -Force
```

安装完成后，在对应范围内直接用自然语言描述需求即可触发相应技能。

### 2.2 设置 Codex 审阅 MCP（推荐）

ARIS 的关键机制是"执行模型 + 外部审阅模型"。先配好审阅 MCP，再跑流程。

1) 安装并登录 Codex CLI

```powershell
npm install -g @openai/codex
codex login
```

2) 在 Trae 中配置 MCP  
进入 `Settings → MCP → 手动添加`，新增：
- Name: `codex`
- Command: `codex`
- Args: `mcp-server`

如你的 Trae 版本支持工作区 MCP 文件，可用：

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

3) 重启 Trae 并验证
- MCP 面板中 `codex` 为在线状态；
- 跑含审阅步骤的技能时出现 review/score/feedback 输出。

### 2.3 替代审阅 MCP（无 OpenAI API）

可用 `llm-chat` 对接 DeepSeek/GLM/MiniMax/Kimi 等兼容接口。

1) 建虚拟环境并安装依赖

```powershell
cd D:\path\to\Auto-claude-code-research-in-sleep
python -m venv .venv
.\.venv\Scripts\pip install -r mcp-servers\llm-chat\requirements.txt
```

2) 配置 MCP（路径必须绝对路径）

```json
{
  "mcpServers": {
    "llm-chat": {
      "command": "/path/to/Auto-claude-code-research-in-sleep/.venv/Scripts/python.exe",
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

3) 必查项
- `command` 必须指向 venv Python；
- `args` 必须是 `server.py` 绝对路径；
- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 必须齐全；
- 改完后重启 Trae，再看 MCP 在线状态。

4) 若红点/离线
- 检查路径拼写；
- 检查 venv 里依赖是否安装；
- 查看 `llm-chat-mcp-debug.log`（系统临时目录）；
- 如 DeepSeek 返回认证失败，优先检查 key 与 base URL。

## 3. 在 Trae 里如何调用 Skills

Trae 支持以下五种方式调用 Skills：

### A. 自然语言自动调用（推荐）

描述你的需求，Trae 会根据技能的 `description`（描述/适用场景）自动判断并调用相关技能：

```
帮我对这篇论文进行自动评审循环
```

这是最自然的方式——只需说明你要做什么，Trae 会自动匹配合适的 Skills。

### B. `#` 快速匹配

在对话框输入 `#` 可以快速搜索和唤起技能，输入 `#` 后会看到技能列表：

```
#auto-review-loop
```

### C. `@` 引用 SKILL.md 文件

直接引用技能文件并在对话中附加动作指令：

```
@skills/auto-review-loop/SKILL.md
请为「factorized gap in discrete diffusion LMs」运行自动审查循环。
```

注意：使用 `@skills/.../SKILL.md` 时，对应的 `skills/` 目录必须在当前 Trae workspace 中可见（例如把 ARIS 仓库或其中的 `skills/` 目录加入当前工作区），否则文件引用会失败。
### D. 高频技能固化为本地规则

将常用技能说明写到项目规则文件，减少每次手动粘贴。

### E. 一次性直接指令

把 workflow 指令直接粘贴到对话里，适合临时任务。

## 4. Workflow Mapping（Claude 流程 → Trae 写法）

Trae 通过 `SKILL.md` 中的 YAML `description` 字段自动发现 ARIS 技能。以下是各工作流的调用方式：

### Workflow 1: Idea Discovery（创意发现）

**Claude Code：**
```
/idea-discovery "your research direction"
```

**Trae 等价写法：**
```
使用 idea-discovery 技能，运行完整的 idea discovery 流程，方向："your research direction"。

按顺序使用以下子技能：
1. 使用 research-lit 技能 —— 文献综述
2. 使用 idea-creator 技能 —— 头脑风暴
3. 使用 novelty-check 技能 —— 新颖性验证
4. 使用 research-review 技能 —— 深度评审
5. 使用 research-refine-pipeline 技能 —— 方法精化 + 实验规划
```

> **提示：** 如果上下文过长，可以将每个阶段拆分为单独的对话，通过文件（如 `idea-stage/IDEA_REPORT.md`、`refine-logs/FINAL_PROPOSAL.md`）传递结果。

### Workflow 1.5: Experiment Bridge（实验桥接）

**Claude Code：**
```
/experiment-bridge
```

**Trae 等价写法：**
```
使用 experiment-bridge 技能。
读取 refine-logs/EXPERIMENT_PLAN.md 并实现实验。
使用 run-experiment 技能部署到 GPU。
```

### Workflow 2: Auto Review Loop（自动评审循环）

**Claude Code：**
```
/auto-review-loop "your paper topic"
```

**Trae 等价写法：**
```
使用 auto-review-loop 技能。
对 "your paper topic" 运行自动评审循环。
读取项目叙事文档、记忆文件和实验结果。
使用 MCP 工具 mcp__codex__codex 进行外部审阅。
```

> **注意：** 如果使用 `llm-chat` MCP，把 `mcp__codex__codex` 替换为 `mcp__llm-chat__chat`。或使用适配版技能：`auto-review-loop-llm`。

### Workflow 3: Paper Writing（论文写作）

**Claude Code：**
```
/paper-writing "NARRATIVE_REPORT.md"
```

**Trae 等价写法：**
```
使用 paper-writing 技能。
输入：项目根目录的 NARRATIVE_REPORT.md。

按顺序使用以下子技能：
1. 使用 paper-plan 技能 —— 大纲 + claims-evidence matrix
2. 使用 paper-figure 技能 —— 生成图表
3. 使用 paper-write 技能 —— 写 LaTeX 章节
4. 使用 paper-compile 技能 —— 编译 PDF
5. 使用 auto-paper-improvement-loop 技能 —— 审阅与润色
```

### Full Pipeline 分阶段建议

| 阶段 | 执行方式 | 产出文件 |
|------|---------|---------|
| 1 | 创意发现：使用 `idea-discovery` 技能 + 研究方向 | `idea-stage/IDEA_REPORT.md`, `refine-logs/FINAL_PROPOSAL.md`, `refine-logs/EXPERIMENT_PLAN.md` |
| 2 | 实验桥接：使用 `experiment-bridge` 技能 | 实验脚本与结果 |
| 3 | 自动评审：使用 `auto-review-loop` 技能 | `review-stage/AUTO_REVIEW.md` |
| 4 | 论文写作：使用 `paper-writing` 技能 + `NARRATIVE_REPORT.md` | `paper/` 目录 |

每个阶段读取上一阶段的产出文件，因此上下文可在不同对话间传递。

## 5. MCP Tool Calls 对照

| ARIS MCP 工具 | 作用 | 需要的 MCP Server |
|---|---|---|
| `mcp__codex__codex` | 发审阅请求到 GPT-5.6-Sol | codex |
| `mcp__codex__codex-reply` | 续接审阅线程 | codex |
| `mcp__llm-chat__chat` | 发请求到兼容 OpenAI API 模型 | llm-chat |

## 6. 状态文件与恢复

| 文件 | 作用 | 典型流程 |
|---|---|---|
| `review-stage/REVIEW_STATE.json` | 记录自动审阅进度 | auto-review-loop |
| `review-stage/AUTO_REVIEW.md` | 累计审阅日志 | auto-review-loop |
| `idea-stage/IDEA_REPORT.md` | 创意筛选与初评结果 | idea-discovery |
| `PAPER_PLAN.md` | 论文大纲与 claim-evidence matrix | paper-plan |
| `PAPER_IMPROVEMENT_LOG.md` | 论文改进回合日志 | auto-paper-improvement-loop |

中断恢复示例：

```text
@skills/auto-review-loop/SKILL.md
@review-stage/REVIEW_STATE.json
@review-stage/AUTO_REVIEW.md
Resume the auto review loop from saved state.
```

## 7. GPU 服务器执行

和 ARIS 原流程一致，在项目说明里提供服务器信息，然后调用：

```text
@skills/run-experiment/SKILL.md
Deploy: python train.py --lr 1e-4 --epochs 100
```

## 8. 常见限制与处理

| 限制 | 处理方式 |
|---|---|
| 自然语言调用依赖技能的 `description` 描述质量 | 确保 skills 的 YAML frontmatter 中 description 准确描述适用场景 |
| 长流程上下文压力大 | 按阶段拆会话，靠产物文件衔接 |
| 无自动压缩恢复 | 用状态文件恢复 |
| `$ARGUMENTS` 不会自动替换 | 在提示词里写清实际参数 |
| 子技能写在 SKILL.md 里是斜杠语法 | 在 Trae 提示词中显式列出 `@skills/...` 子技能 |

## 9. Quick Reference（快速参考）

```
# 文献综述
使用 research-lit 技能，搜索 "discrete diffusion models" 相关论文。

# 创意发现（完整流程）
使用 idea-discovery 技能，对 "factorized gap in discrete diffusion LMs" 运行创意发现。

# 单次深度评审
使用 research-review 技能，评审我的研究：[描述或指向文件]。

# 自动评审循环
使用 auto-review-loop 技能，运行自动评审循环。课题："your paper topic"。

# 论文写作
使用 paper-writing 技能，根据 NARRATIVE_REPORT.md 写论文。

# 部署实验
使用 run-experiment 技能，部署：python train.py --lr 1e-4 --epochs 100
```

## 10. 迁移清单：Claude Code → Trae

- [ ] 进入 `设置 → 规则和技能`，选择「全局」或「项目」安装范围
- [ ] 导入 ARIS skills 的 SKILL.md 文件
- [ ] 在 `Settings → MCP` 配置 MCP 服务器
- [ ] 使用自然语言描述需求触发技能
- [ ] 验证 MCP 工具可用（codex 或 llm-chat）
- [ ] 快速测试：`使用 research-review 技能评审我的项目`
