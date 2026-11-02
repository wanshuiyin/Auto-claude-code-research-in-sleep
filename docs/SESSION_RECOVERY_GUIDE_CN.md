# 会话恢复与状态持久化指南

[English](SESSION_RECOVERY_GUIDE.md) | 中文版

> 在 ARIS 工作流中跨会话和上下文压缩维护项目状态 — 核心设计是**项目 CLAUDE.md 中的 Pipeline Status**，Claude Code 用户可选 hook 自动化。

## 为什么需要会话恢复

ARIS 工作流可能持续数小时（idea discovery、auto-review loop、overnight training）。两件事会打断状态连续性：

1. **上下文压缩（Context Compaction）** — 当上下文窗口满了，Claude Code 自动压缩之前的消息。压缩后 LLM 只有压缩摘要，可能忘记当前在哪个 stage、哪些实验在跑、下一步该做什么。
2. **主动开新会话** — 反复摘要和不断累积的对话可能掩盖任务细节、决策与证据。当它影响实际工作时，可以开新会话，从项目文件重建聚焦的上下文。

ARIS 已经将部分状态持久化到文件（`review-stage/REVIEW_STATE.json`、`review-stage/AUTO_REVIEW.md`），但**没有系统性机制确保 LLM 在恢复时去读这些文件**。压缩后，它经常忘记。

## 核心方案：Pipeline Status

最重要的一件事是在项目 `CLAUDE.md` 中维护一个 **`## Pipeline Status`** 段。这是一个轻量级、结构化的项目快照——30 秒读完，足以让任何 LLM 恢复工作。

### Pipeline Status 包含什么

在项目 `CLAUDE.md` 中添加：

```yaml
## Pipeline Status
stage: idea-discovery | implementation | training | paper
idea: "当前 idea 的一句话描述"
contract: idea-stage/docs/research_contract.md
current_branch: feature/idea-name
baseline: "代表数据集 acc=95.2（论文 95.5）"
training_status: running on server-X, GPU 0-3, tmux=train01, wandb=run_id,
  检查: ssh server-X "tmux capture-pane -t train01 -p | tail -5"
active_tasks:
  - "training exp01 on server-X (tmux=exp01, GPU 0-3)"
  - "downloading dataset-Y on server-Z (tmux=download01)"
language: en         # en | zh — 控制技能输出语言
last_updated: ""     # YYYY-MM-DD HH:mm — 技能每次输出时自动更新
next: 下一步行动
```

> 💡 从模板开始：`cp templates/CLAUDE_MD_TEMPLATE.md CLAUDE.md`

| 字段 | 用途 | 示例 |
|------|------|------|
| `stage` | 当前工作流阶段 | `training` |
| `idea` | 在做什么 | `"离散扩散 LM 中的分解注意力 gap"` |
| `contract` | 指向详细上下文 | `idea-stage/docs/research_contract.md` |
| `current_branch` | 当前 idea 的 git 分支 | `feature/factorized-gap` |
| `baseline` | 基线数字用于对比 | `"WikiText-103 PPL=18.2（论文 18.5）"` |
| `training_status` | 训练总体状态 | `running on b2, GPU 0-3, tmux=exp01` |
| `active_tasks` | 所有正在运行的任务（训练、下载、评估），含位置和检查方式 — 防止新 session 丢失对后台任务的追踪 | `training exp01 on b2 (GPU 0-3)` |
| `next` | 具体下一步 | `"等训练完，在测试集上跑 eval"` |
| `language` | 技能输出语言 | `en` 或 `zh` — 控制技能输出语言 |
| `last_updated` | 技能最后输出时间 | `2025-06-15 14:30` — 技能自动更新 |

### 什么时候更新 Pipeline Status

LLM 应在以下情况发生时**立即更新**：

- Stage 切换（如 idea-discovery → implementation）
- Idea 选定或更换
- Baseline 确认
- 训练启动或结束
- 做出重大决策
- **用户说"记录一下"、"保存"、"new session"、"收工"** — 这是在开新 session 前持久化所有状态的信号

### 为什么需要 Research Contract

工作流 1（`/idea-discovery`）完成后，`idea-stage/IDEA_REPORT.md` 包含 8-12 个候选 idea。一旦选定一个进入实现阶段，把所有候选都留在上下文中会浪费 LLM 的工作记忆、降低输出质量。

**`idea-stage/docs/research_contract.md`** 解决这个问题：只提取*当前正在做的那一个 idea* 到一份聚焦的工作文档——claim、实验设计、baseline、结果。新 session 读这个，而不是读整个 IDEA_REPORT.md。模板见 [`templates/RESEARCH_CONTRACT_TEMPLATE.md`](../templates/RESEARCH_CONTRACT_TEMPLATE.md)。

- **创建时机**：选定 idea 时（工作流 1 → 工作流 1.5）
- **更新时机**：baseline 复现后、实验完成后、做出关键决策后
- **读取时机**：每次会话恢复 — 这是主要的上下文文档

### 恢复流程

**新会话或压缩后**，LLM 按以下顺序读取：

1. `CLAUDE.md` → `## Pipeline Status`（30 秒定位）
2. `idea-stage/docs/research_contract.md`（当前 idea 的聚焦上下文 — 不是整个 IDEA_REPORT）
3. 项目笔记或日志文件（如有，恢复调试线索、决策理由）
4. 如果 `active_tasks`/`training_status` 非空 → 检查远程 session，重建监控

这在**任何平台**上都适用（Claude Code、Cursor、Trae、Codex CLI、OpenClaw）— 只是一个 Markdown 约定。

### 推荐的 CLAUDE.md 规则

在项目 `CLAUDE.md` 中添加这些规则，让 LLM 知道何时以及如何维护状态：

```markdown
## 状态持久化规则

Pipeline Status 更新时机：
- Stage 切换、idea 选定、baseline 确认、训练启动/结束
- 用户说"记录一下"/"保存"/"new session"/"收工"
- 任何长时间暂停或交接前

新会话或压缩后恢复：
1. 读 ## Pipeline Status
2. 读 idea-stage/docs/research_contract.md（当前 idea 的聚焦上下文）
3. 读项目笔记（如有，例如实验日志、决策理由）
4. 如有 active_tasks → 检查远程状态，重建监控
5. 继续工作，不问用户
```

## 用 HERO 准备新会话

[HERO Session Handoff](https://github.com/wanshuiyin/HERO-Anti-OverDefense/tree/main/skills/session-handoff)
将上面的状态持久化约定变成 agent 可执行的工作流。HERO 维护一份供 Codex 和 Claude Code 共用的 Markdown 技能，同目录提供安装说明。它是可选的外部技能，不加入 ARIS 技能目录，也不由 ARIS 安装器安装。

切换上下文前，用 `prepare` 保存有证据支撑的交接：

```text
Codex：$session-handoff prepare，准备新会话，复用 NEXT_SESSION.md。
Claude Code：/session-handoff prepare，准备新会话，复用 NEXT_SESSION.md。
```

`NEXT_SESSION.md` 请替换为项目实际恢复入口；没有现成入口时可省略这一要求。

技能复用项目已有恢复入口、Pipeline Status、当前 research contract，以及 `REFINE_STATE.json`、`REVIEW_STATE.json` 等工作流检查点。它核对当前文件、相关 Git 变动、已有验证和后台任务，保存完整目标、最新纠正、有价值的失败路线、写入归属及具体下一步。没有现成入口时才创建 `HANDOFF.md`；`AGENTS.md` 或 `CLAUDE.md` 只保留简短指针，不灌入完整交接。

`prepare` 返回可直接复制的启动提示。用户在目标工作区手动打开 fresh session，再粘贴提示。已有恢复入口也可以直接这样接续：

```text
Codex：$session-handoff continue，从 NEXT_SESSION.md 接续。
Claude Code：/session-handoff continue，从 NEXT_SESSION.md 接续。
```

新会话读取入口及原始材料，核对文件变化和任务实时状态，复用已完成的证据，继续已授权工作，并保留在途 worker 的写域归属。这是新上下文读取磁盘状态，与恢复旧聊天不同。宿主管理的 Goal 绑定和预算不会随交接迁移；暂停的 Goal 仍需用户恢复。在进行中的任务里准备交接，也不自动终止该任务。

ARIS 的 `/auto-review-loop` 参数 `compact: true` 是优先读取 `findings.md`、`EXPERIMENT_LOG.md` 等精简恢复材料，不是宿主压缩上下文的命令。完整的 prepare/continue 机制见 HERO 技能。

## 可选：Claude Code Hooks 自动化

Pipeline Status 约定不依赖任何工具——LLM 只需要遵循 CLAUDE.md 中的规则。但实践中 LLM 有时会忘记，尤其是压缩后。Claude Code [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) 可以自动化恢复过程。

> **这些 hook 是 Claude Code 专属的。** 如果使用 Cursor、Trae 或其他平台，跳过这一节——上面的 Pipeline Status 约定就是你需要的全部。

### 概览

| Hook | 事件 | 用途 |
|------|------|------|
| `session-restore.sh` | `PreToolUse`（首次调用） | 新会话 → 自动读取 Pipeline Status + 状态文件 |
| `context-refresh.sh` | `PreToolUse`（节流） | 周期性将 Pipeline Status 注入上下文 |
| `pre-compact-remind.sh` | `PreCompact` | 压缩前提醒 LLM 保存状态 |
| `progress-remind.sh` | `PostToolUse`（Write/Edit） | 代码修改后提醒更新 EXPERIMENT_TRACKER.md |

### 安装

#### 1. 创建 hooks 目录

```bash
mkdir -p ~/.claude/hooks
```

#### 2. 创建 hook 脚本

##### `session-restore.sh` — 新会话自动恢复

最重要的 hook。新会话的第一次工具调用时，自动读取 Pipeline Status 并提醒 LLM 恢复对应工作流。

```bash
cat > ~/.claude/hooks/session-restore.sh << 'HOOKEOF'
#!/bin/bash
# PreToolUse hook: 新会话首次工具调用时自动恢复项目上下文
# 每个会话只触发一次。修改 RESEARCH_ROOT 指向你的项目父目录。

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

FLAG="/tmp/aris-session-restore-$$"
[ -f "$FLAG" ] && exit 0
touch "$FLAG"

PROJECT_DIR=""
SEARCH_DIR="$CWD"
while [[ "$SEARCH_DIR" == "$RESEARCH_ROOT"/* ]]; do
  if [ -f "$SEARCH_DIR/CLAUDE.md" ]; then
    PROJECT_DIR="$SEARCH_DIR"
    break
  fi
  SEARCH_DIR=$(dirname "$SEARCH_DIR")
done
[ -z "$PROJECT_DIR" ] && exit 0

OUTPUT=""

# 1. Read Pipeline Status
STATUS=$(sed -n '/^## Pipeline Status/,/^## /{ /^## Pipeline Status/d; /^## /d; p; }' "$PROJECT_DIR/CLAUDE.md" 2>/dev/null | head -15)
if [ -n "$STATUS" ]; then
  OUTPUT="[session-restore] Research project detected. Current state:\n$STATUS"
fi

# 2. Check for research_contract.md (new path first, legacy fallback)
if [ -f "$PROJECT_DIR/idea-stage/docs/research_contract.md" ]; then
  OUTPUT="$OUTPUT\n\n[session-restore] idea-stage/docs/research_contract.md exists — read it to restore full idea context."
elif [ -f "$PROJECT_DIR/docs/research_contract.md" ]; then
  OUTPUT="$OUTPUT\n\n[session-restore] docs/research_contract.md exists (legacy path) — read it to restore full idea context."
fi

# 3. Check for active training
if grep -q "training_status:.*running" "$PROJECT_DIR/CLAUDE.md" 2>/dev/null; then
  OUTPUT="$OUTPUT\n\n[session-restore] Active training detected — check remote status and rebuild monitoring."
fi

# 4. Check for REVIEW_STATE.json (auto-review-loop recovery, new path first, legacy fallback)
REVIEW_STATE=""
if [ -f "$PROJECT_DIR/review-stage/REVIEW_STATE.json" ]; then
  REVIEW_STATE="$PROJECT_DIR/review-stage/REVIEW_STATE.json"
elif [ -f "$PROJECT_DIR/REVIEW_STATE.json" ]; then
  REVIEW_STATE="$PROJECT_DIR/REVIEW_STATE.json"
fi
if [ -n "$REVIEW_STATE" ]; then
  RS_STATUS=$(python3 -c "import json; d=json.load(open('$REVIEW_STATE')); print(d.get('status',''))" 2>/dev/null)
  if [ "$RS_STATUS" = "in_progress" ]; then
    OUTPUT="$OUTPUT\n\n[session-restore] REVIEW_STATE.json found (in_progress) — auto-review-loop can resume."
  fi
fi

# 5. Suggest stage-appropriate actions
STAGE=$(grep -oP '(?<=stage:\s).*' "$PROJECT_DIR/CLAUDE.md" 2>/dev/null | head -1 | tr -d ' ')
case "$STAGE" in
  idea-discovery)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: idea-discovery. Resume with /idea-discovery or /research-lit." ;;
  implementation)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: implementation. Resume with /experiment-bridge." ;;
  training)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: training. Check experiments, then /auto-review-loop if results are ready." ;;
  paper)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: paper. Resume with /paper-writing or /paper-write." ;;
esac

[ -n "$OUTPUT" ] && echo -e "$OUTPUT"
HOOKEOF
chmod +x ~/.claude/hooks/session-restore.sh
```

##### `context-refresh.sh` — 周期性状态刷新

```bash
cat > ~/.claude/hooks/context-refresh.sh << 'HOOKEOF'
#!/bin/bash
# PreToolUse hook: 每 30 次工具调用刷新一次 Pipeline Status

INPUT=$(cat)
RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

COUNTER_FILE="/tmp/aris-context-refresh-counter"
COUNT=0
[ -f "$COUNTER_FILE" ] && COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

[ "$COUNT" -ne 1 ] && [ $((COUNT % 30)) -ne 0 ] && exit 0

PROJECT_CLAUDE=""
SEARCH_DIR="$CWD"
while [[ "$SEARCH_DIR" == "$RESEARCH_ROOT"/* ]]; do
  if [ -f "$SEARCH_DIR/CLAUDE.md" ]; then
    PROJECT_CLAUDE="$SEARCH_DIR/CLAUDE.md"
    break
  fi
  SEARCH_DIR=$(dirname "$SEARCH_DIR")
done
[ -z "$PROJECT_CLAUDE" ] && exit 0

STATUS=$(sed -n '/^## Pipeline Status/,/^## [^P]/p' "$PROJECT_CLAUDE" | head -20 | sed '$d')
if [ -n "$STATUS" ]; then
  echo "[context-refresh] 当前项目状态："
  echo "$STATUS"
fi
HOOKEOF
chmod +x ~/.claude/hooks/context-refresh.sh
```

##### `pre-compact-remind.sh` — 压缩前保存状态

```bash
cat > ~/.claude/hooks/pre-compact-remind.sh << 'HOOKEOF'
#!/bin/bash
# PreCompact hook: 压缩前提醒 LLM 保存状态

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

echo "[pre-compact] Context compaction is about to happen."
echo "[pre-compact] Ensure these are up to date:"
echo "  1. CLAUDE.md Pipeline Status (stage, idea, active_tasks, next)"
echo "  2. idea-stage/docs/research_contract.md (current idea context and results)"
echo "  3. EXPERIMENT_TRACKER.md (any unreported results)"
echo "  4. review-stage/REVIEW_STATE.json (if running auto-review-loop)"
echo "[pre-compact] After compaction, read CLAUDE.md and idea-stage/docs/research_contract.md to recover."
HOOKEOF
chmod +x ~/.claude/hooks/pre-compact-remind.sh
```

##### `progress-remind.sh` — 代码修改后提醒

```bash
cat > ~/.claude/hooks/progress-remind.sh << 'HOOKEOF'
#!/bin/bash
# PostToolUse hook: 每 10 次写操作提醒更新状态文件

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL_NAME" in
  Write|Edit) ;;
  *) exit 0 ;;
esac

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)
[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
case "$FILE_PATH" in
  */CLAUDE.md|*/IDEA_REPORT.md|*/AUTO_REVIEW.md|*/REVIEW_STATE.json|*/EXPERIMENT_TRACKER.md|*/research_contract.md)
    exit 0 ;;
esac

COUNTER_FILE="/tmp/aris-progress-remind-counter"
COUNT=0
[ -f "$COUNTER_FILE" ] && COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

[ $((COUNT % 10)) -ne 0 ] && exit 0

echo "[progress-remind] 已累计 ${COUNT} 次代码修改。如有阶段性进展，请更新 EXPERIMENT_TRACKER.md 和 Pipeline Status。"
HOOKEOF
chmod +x ~/.claude/hooks/progress-remind.sh
```

#### 3. 注册到 settings.json

在 `~/.claude/settings.json` 中添加（已有 hooks 配置则合并）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/session-restore.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "~/.claude/hooks/context-refresh.sh",
            "timeout": 3
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/pre-compact-remind.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/progress-remind.sh",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

#### 4. 设置项目根目录（可选）

```bash
export ARIS_RESEARCH_ROOT="$HOME/my-projects"  # 默认: ~/research
```

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Pipeline Status                        │
│              （项目 CLAUDE.md 中）                         │
│                                                          │
│  "项目现在在哪" 的唯一真相源                                │
│  LLM 在每次状态变化时更新                                   │
│  LLM（或 hook）在每次恢复时读取                              │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   新会话           压缩后         用户说
                                 "new session"
        │              │              │
        ▼              ▼              ▼
   从磁盘读       从磁盘读         保存状态
   取状态         取状态           然后退出
        │              │
        ▼              ▼
   继续工作       继续工作

可选自动化（仅 Claude Code）：
  session-restore.sh → 新会话自动读取状态
  context-refresh.sh → 周期性重新注入状态
  pre-compact-remind.sh → 压缩前提醒保存
  progress-remind.sh → 代码修改后提醒持久化
```

## 其他平台的替代方案

Pipeline Status 约定在任何平台都适用。只有自动化层不同：

| 平台 | 自动化方式 |
|------|-----------|
| **Claude Code** | Hooks（本指南） |
| **Cursor** | `.cursor/rules/session-recovery.mdc` — 匹配 `CLAUDE.md` 时指示 agent 先读 Pipeline Status |
| **Trae** | `.trae/rules/` — 添加会话恢复指令 |
| **Codex CLI** | 在 `AGENTS.md` 中放入状态读取指令及恢复入口的简短指针 |
| **OpenClaw** | 在初始 agent prompt 中包含恢复步骤 |

核心洞察：**Pipeline Status 是协议，Hook 是一种实现。协议不依赖 hook 就能工作——hook 只是让它更可靠。**

## 常见问题

**Q：必须装 hook 吗？**
A：不需要。CLAUDE.md 中的 Pipeline Status 是核心——在任何平台都能用。Hook 只是 Claude Code 上的自动化层，可选。

**Q：4 个 hook 都要装吗？**
A：`session-restore.sh` 单独就覆盖 80% 的价值。建议从它开始。

**Q：hook 会拖慢工作流吗？**
A：不会。每个 <100ms。节流机制控制触发频率。

**Q：我的 CLAUDE.md 没有 `## Pipeline Status` 段怎么办？**
A：hook 查找 `## Pipeline Status`。用了不同名字就改 `sed` 模式。找不到时 hook 静默退出，不影响使用。
