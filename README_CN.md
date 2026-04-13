# 🌙 ARIS-Code — Auto Research in Sleep

```
    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
    ░  █████╗ ██████╗ ██╗███████╗            ░
    ░ ██╔══██╗██╔══██╗██║██╔════╝            ░
    ░ ███████║██████╔╝██║███████╗            ░
    ░ ██╔══██║██╔══██╗██║╚════██║            ░
    ░ ██║  ██║██║  ██║██║███████║            ░
    ░ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝           ░
    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
         🟦 [Claude]    🟩 [GPT 🕶️]
         executor  ←→  reviewer
         让 AI 边睡边帮你做研究
```

![ARIS-Code Screenshot](docs/screenshot.png)

> **对抗·多智能体研究自动化 CLI**
> Executor 执行 · Reviewer 审查 · 迭代精进

[![GitHub Release](https://img.shields.io/github/v/release/wanshuiyin/Auto-claude-code-research-in-sleep?style=flat-square)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20|%20Linux%20|%20Windows-black?style=flat-square)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)


## 📰 最新动态

> **v0.3.9** (2026-04-11) — 代理/自定义 base URL | 本地模型 (LM Studio/Ollama) | Research Wiki | 自进化 Meta-Optimize | Session 原子写入 | Bash 安全校验 | Windows (experimental)
>
> <details><summary>历史版本</summary>
>
> **v0.3.5** (2026-04-08) — Research Wiki | 自进化 Meta-Optimize | Session 原子写入 | Bash 安全校验 | Windows 支持
>
> **v0.3.3** (2026-04-04) — 修复所有 Claude Code hooks 配置崩溃路径
>
> **v0.3.0** (2026-04-03) — 多文件记忆索引 | 结构化任务系统 (TodoWrite) | `/plan` | 安全加固
>
> **v0.2.2** (2026-04-03) — `/plan` 步骤规划 | `/tasks` 持久任务
>
> **v0.2.1** (2026-04-03) — 持久记忆 | Kimi K2.5 多轮修复 | 中文光标修复
>
> **v0.2.0** (2026-04-02) — 开源发布 | Kimi + MiniMax + GLM | 智能路由 | CI/CD
>
> **v0.1.0** (2026-04-02) — 首次发布 | 多执行者/审阅者 | 42 个技能
>
> </details>
>
> [完整更新日志 →](CHANGELOG.md)


---

## ✨ 简介

**ARIS-Code**（*Auto Research in Sleep*）是一个面向学术研究者的终端 AI 编程/研究助手。它的核心思想是：

- 🤖 **Executor**（执行者）：主力 LLM，负责写代码、查文献、写论文、跑实验
- 🔍 **Reviewer**（审查者）：独立 LLM，通过 `LlmReview` 工具对 Executor 的输出进行对抗性审查
- 🔄 **迭代精进**：Executor 写 → Reviewer 批 → Executor 修 → 循环直至高质量

内置 **42 个研究技能**（Skills），覆盖从选题到投稿的完整研究流水线。

---

## 🚀 安装

**macOS (Apple Silicon)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-darwin-arm64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**macOS (Intel)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-darwin-x64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**Linux (x64)**
```bash
curl -fsSL https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-linux-x64.tar.gz | tar xz
sudo mv aris /usr/local/bin/aris
```

**Windows (x64)**
下载 [`aris-code-windows-x64.zip`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest/download/aris-code-windows-x64.zip)，解压后在 PowerShell 或 Windows Terminal 中运行 `aris.exe`。

> 运行 `aris` 启动，首次运行会自动触发交互式配置向导。

---

## ⚙️ 首次配置

首次运行 `aris` 会自动触发交互式引导配置：

```
🌙 ARIS-Code 首次配置向导

[1/3] 选择 Executor 提供商（主力执行 LLM）
  > Anthropic Claude
    OpenAI GPT
    Google Gemini
    Zhipu GLM
    MiniMax
请输入 API Key: sk-...

[2/3] 选择 Reviewer 提供商（对抗审查 LLM）
  > OpenAI GPT
    Google Gemini
    Zhipu GLM
    MiniMax
请输入 API Key: sk-...

[3/3] 选择语言偏好
  > 中文 (CN)
    English (EN)

✅ 配置已保存至 ~/.config/aris/config.json
```

配置完成后直接进入 REPL，也可随时在 REPL 中执行 `/setup` 重新配置，无需重启。

---

## 🤖 支持的模型提供商

| 提供商 | 作为 Executor | 作为 Reviewer | 主要模型 |
|--------|:------------:|:------------:|---------|
| 🟣 Anthropic Claude | ✅ | — | claude-opus, claude-sonnet, claude-haiku |
| 🟢 OpenAI | ✅ | ✅ | gpt-5.4, gpt-5.4-mini, gpt-5.4-nano |
| 🔵 Google Gemini | ✅ | ✅ | gemini-2.5-pro, gemini-2.5-flash |
| 🔶 Zhipu GLM | ✅ | ✅ | GLM-5, GLM-5-Turbo |
| 🔷 MiniMax | ✅ | ✅ | MiniMax-M2.7, MiniMax-M2.7-highspeed |

> **设计说明**：Anthropic Claude 仅作 Executor，其他四家可同时作 Executor 和 Reviewer。推荐经典搭配：**Claude Executor + GPT/GLM Reviewer**，构成真正的对抗多智能体。

---

## 🎯 核心功能

### 1. 🔄 对抗·多智能体架构

```
用户输入
    ↓
[Executor LLM]  ──── 调用工具 ────→  LlmReview Tool
  写代码/论文                           ↓
  查文献/分析                      [Reviewer LLM]
    ↑                               独立审查
    └──────── 审查意见 ──────────────┘
                  迭代直至质量达标
```

**直接调用 LlmReview 示例**：

```
❯ 帮我 review 一下这篇论文
# ARIS 读取论文后，调用 LlmReview 获取 GPT-5.4/GLM-5/MiniMax 的独立评审
# Executor 和 Reviewer 展开多轮对抗对话

❯ 用 LlmReview 给审稿人打个招呼
# 直接调用 LlmReview 工具
```

### 2. 📚 42 个内置研究技能

通过 `/skills` 命令查看所有可用技能：

```
/research-lit      — 文献搜索与综述
/idea-discovery    — 研究思路发现流水线
/research-review   — GPT xhigh 深度 review
/paper-write       — LaTeX 论文写作
/paper-compile     — 论文编译与修复
/auto-review-loop  — 自动多轮 review 循环
/experiment-plan   — 实验规划
/run-experiment    — 远程 GPU 实验部署
/peer-review       — 同行评审模拟
/rebuttal          — 投稿 Rebuttal 生成
...（共 42 个）
```

**技能三级优先级**（高优先覆盖低优先）：
```
~/.config/aris/skills/   [用户自定义，最高优先]
~/.claude/skills/        [Claude Code 兼容]
内置 bundled skills      [42 个开箱即用]
```

### 3. 🖥️ REPL 交互命令

| 命令 | 功能 |
|------|------|
| `/help` | 查看所有命令 |
| `/model` | 切换 Executor 模型 |
| `/reviewer` | 切换 Reviewer 模型 |
| `/permissions` | 切换权限模式（允许/拒绝/询问） |
| `/setup` | 重新配置（无需重启） |
| `/skills` | 查看/展示/导出技能列表 |
| `/status` | 当前配置状态 |
| `/cost` | Token 用量与费用统计 |
| `/compact` | 压缩对话历史 |
| `/clear` | 清空屏幕 |
| `/version` | 版本信息 |
| `/research-review` | 直接调用 review 技能 |
| `/paper-write` | 直接调用写作技能 |
| `...` | 以及全部 42 个技能命令 |

### 4. 🌐 多语言支持

配置语言偏好（CN/EN）后，语言设置会注入系统提示，ARIS 始终以你选择的语言响应。

### 5. 🛡️ 防幻觉设计

系统提示明确告知模型其身份（ARIS-Code），避免模型在多智能体场景下混淆自身角色。

---

## 📖 使用示例

### 文献调研
```
❯ /research-lit 帮我找一下 diffusion model 在 protein design 上的最新进展
```

### 自动 Review 循环
```
❯ /auto-review-loop
# ARIS 自动读取当前目录的论文，循环调用 Reviewer，
# 实现修改 → review → 修改 → review，直至质量达标
```

### 切换模型
```
❯ /model
  当前 Executor: claude-sonnet-4-5
  切换为:
  > claude-opus-4
    gpt-5.4
    gemini-2.5-pro
```

### 切换 Reviewer
```
❯ /reviewer
  当前 Reviewer: gpt-5.4
  切换为:
  > glm-5
    gemini-2.5-pro
    minimax-m2.7
```

---

## 📁 配置文件

```
~/.config/aris/
├── config.json        # 主配置（提供商、API Key、语言等）
└── skills/            # 用户自定义技能（覆盖内置技能）
```

**config.json 示例**：
```json
{
  "executor": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-5",
    "api_key": "sk-ant-..."
  },
  "reviewer": {
    "provider": "openai",
    "model": "gpt-5.4",
    "api_key": "sk-..."
  },
  "language": "CN"
}
```

---

## 🗺️ 路线图

- [x] Phase 0：Rust fork 基础架构（基于 claw-code）
- [x] Phase 1：多 Provider 支持（Anthropic/OpenAI/Gemini/GLM/MiniMax）
- [x] Phase 1：LlmReview 对抗审查工具
- [x] Phase 1：42 个研究技能内置
- [x] Phase 1：语言偏好与防幻觉系统提示
- [ ] Phase 2：Skills 系统完善（三级优先级 UI）
- [ ] Phase 2：Web UI 仪表盘
- [ ] Phase 3：Linux / Windows 支持
- [ ] Phase 3：本地模型（Ollama）集成

---

## 🙏 致谢

**ARIS-Code 建立在 [claw-code](https://github.com/ultraworkers/claw-code) 的优秀基础之上。**

claw-code 是 Claude Code 的 Rust 开源重新实现，为本项目提供了坚实的 REPL 框架、工具调用基础设施和跨平台编译能力。衷心感谢 ultraworkers 团队的出色工作！

- 🔗 claw-code 项目：https://github.com/ultraworkers/claw-code
- 🔗 ARIS-Code 项目：https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep

---

## 📄 License

MIT License © 2025 ARIS-Code Contributors

---

<div align="center">
  <sub>🌙 让 AI 在你睡觉时帮你做研究 · Built with ❤️ and Rust</sub>
</div>

