# 手动评审指南

> **零 API 成本的跨模型评审。** 复制提示词到**不同**模型家族，粘贴回复即可。如果执行器是 Claude Code，请勿使用 Claude 产品作为评审者。

## 概述

手动评审 MCP 服务器是默认 Codex MCP 评审器的人工中转替代方案。无需 GPT Plus/Pro 订阅即可实现跨模型评审——你可以使用**不同**模型家族。如果执行器是 Claude Code，请勿使用 Claude 产品作为评审者。推荐：ChatGPT、DeepSeek、Kimi、Gemini、Qwen 等非 Claude 模型。

代价：失去完全自动化（需要手动复制粘贴），换来模型选择的完全自由和零 API 成本。

## 适用场景

- 有 Claude Code 订阅但没有 GPT Plus/Codex 订阅
- 想使用免费模型进行评审
- 希望每次自行选择评审模型
- 实验阶段不想在评审上消耗 API 额度

## 安装

```bash
# 一次性设置：注册 MCP 服务器到 Claude Code
claude mcp add manual-review -s user -- python3 /path/to/Auto-claude-code-research-in-sleep/mcp-servers/manual-review/server.py
```

无需额外依赖——服务器仅使用 Python 标准库。

## 使用方法

在已接线的技能后添加 `— reviewer: manual`（见下方支持的技能）：

```
/auto-review-loop "your topic" — reviewer: manual
/research-review "paper/" — reviewer: manual
/experiment-audit "results/" — reviewer: manual
/proof-checker "paper/" — reviewer: manual
/rebuttal "paper/" — reviewer: manual
/idea-creator "direction" — reviewer: manual
```

## 工作流程

### 浏览器模式（默认）

1. 流程到达评审步骤
2. 浏览器自动打开 `http://127.0.0.1:<port>`
3. **左侧面板**：完整评审提示词（点击"复制提示词"）
4. **右侧面板**：在此粘贴模型回复
5. 点击"提交"——流程继续

### 文件模式（无桌面 Linux / SSH）

设置环境变量 `MANUAL_REVIEW_MODE=file`。

1. 流程到达评审步骤
2. 查看 `.aris/pending_review/pending_review.json`，获取 `prompt_file` 和 `response_file` 路径。
3. 打开 `prompt_file` 指向的文件，阅读提示词。
4. 复制到你的模型，获取回复。
5. 将回复写入 `response_file` 指向的文件。
6. 服务器检测到文件（确认稳定后）继续流程。

**重要**：服务器等待回复文件非空且稳定（两次读取内容不变）后才读取。不要硬编码 `.aris/pending_review/response.md` — 始终使用 `pending_review.json` 中的路径。不要先创建空文件再编辑——直接一次性写入完整内容，或使用临时文件名后重命名。

## 多轮评审

对于使用多轮评审的技能（如 `/auto-review-loop`），浏览器页面会在可折叠的"历史对话"区域显示之前的交互。这帮助你在所选模型中保持上下文连续性。

**建议**：跨轮次保持同一个模型对话窗口，以获得最佳连续性。

## 最佳实践

1. **使用推理能力强的模型**——配置提示显示 `reasoning_effort = xhigh`，意味着提示词为深度推理设计。GPT-4o、DeepSeek-V3、Kimi、Gemini 等效果较好。如果执行器是 Claude Code，请勿使用任何 Claude 家族模型。
2. **粘贴完整回复**——不要截断或总结。流程会从回复中解析特定字段（分数、判定、行动项）。
3. **不要修改提示词**——原样粘贴。提示词与 Codex 收到的完全一致。
4. **多轮评审时**——在模型中保持对话（第 2 轮不要开新对话）。

## 恢复

- **不小心关了标签页？** 查看 `.aris/pending_review/pending_review.json` 获取完整 URL（包含一次性 token — 必须完整复制，不要手动输入裸地址 `http://127.0.0.1:17900`）。服务器仍在运行——重新打开 URL 即可。
- **服务器超时？** 默认超时 24 小时。超时后流程报错，重新运行技能即可。
- **粘贴了错误回复？** 提交后无法撤销。需要时重新运行技能。

## 支持的技能

以下技能已接线 manual-review（仅限 Claude Code）：

| 技能 | 评审用途 |
|------|----------|
| `/research-review` | 论文评审 |
| `/auto-review-loop` | 迭代改进 |
| `/experiment-audit` | 实验代码审计 |
| `/proof-checker` | 数学证明验证 |
| `/rebuttal` | 反驳压力测试 |
| `/idea-creator` | 想法评估 |

> `/research-lit` 当前没有 manual-review 调用块；如需文献分析深度评审，请使用已支持的 `oracle-pro` 路由或单独运行评审 skill。

## 后续计划

- **图片生成**：`codex-image2` 的手动替代方案（上传/粘贴图片）
- **图片评审循环**：通过同一 UI 进行论文插图的迭代改进
