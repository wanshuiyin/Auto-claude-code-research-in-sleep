# Auto-claude-code-research-in-sleep

[English](README.md) | 中文版

![Hero](hero_interaction.svg)

![分数曲线](auto_review_score_curve.png)

> 🌙 **让 Claude Code 在你睡觉时做科研。** 醒来发现论文已被打分、弱点已被定位、实验已跑完、叙事已重写——全自动。

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主 ML 科研工作流。核心机制是**跨模型协作**——Claude Code 负责执行（读文件、写代码、跑实验、收结果），外部 LLM（通过 [Codex MCP](https://github.com/openai/codex)）负责评审（打分、找弱点、建议修复）。两个模型互不评自己的作业，形成真正的反馈循环。

## 📈 真实运行效果

某 ML 研究项目上的 4 轮自动循环，从 borderline reject 到可投稿：

| 轮次 | 分数 | 发生了什么 |
|------|------|-----------|
| 初始 | 5.0/10 | Borderline reject |
| 第 1 轮 | 6.5/10 | 补了标准指标，发现指标脱钩 |
| 第 2 轮 | 6.8/10 | 核心声明不可复现，转换叙事 |
| 第 3 轮 | 7.0/10 | 大规模 seed 研究推翻了主要改善声明 |
| 第 4 轮 | **7.5/10** ✅ | 诊断证据确立，**可以投稿** |

循环自主跑了 **20+ 个 GPU 实验**，重写了论文叙事框架，杀掉了经不住检验的声明——全程无人干预。

---

## 🔄 工作流

所有 Skills 组成完整科研流水线：

### 完整流程 🚀

```
/research-lit → /novelty-check → 实现 → /auto-review-loop → 投稿
  (调研文献)      (查新验证)     (写代码)    (自动改到能投)     (搞定!)
```

### 工作流 1：自动科研循环 🔁（睡一觉醒来看结果）

> "帮我 review 论文，修复问题，循环到通过为止。"

**涉及 Skills：** `auto-review-loop` + `research-review` + `novelty-check` + `analyze-results` + `monitor-experiment`

```
外部 LLM 评审 → Claude Code 实现修复 → 跑实验 → 收结果 → 再评审 → 循环
                ↑ 需要新方向时自动 /novelty-check 查新
```

用法：
```
> /auto-review-loop 我的 diffusion model 论文
```

**🛡️ 关键安全机制：**

- 🔒 **MAX_ROUNDS = 4** — 防止无限循环；达到分数阈值时提前停止
- ⏱️ **> 4 GPU-hour 的实验自动跳过** — 不会启动超大实验，标记为"需人工跟进"
- 🧠 **优先改叙事而非跑新实验** — 同样能解决问题时，选择成本更低的路径
- 🪞 **不隐藏弱点** — 明确规则："不要隐藏弱点来骗高分"
- 🔧 **先修后审** — 必须实现修复后再重新 review，不能只承诺修

📝 **博客：** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### 工作流 2：文献调研与找 Idea 🔍

> "这个领域最新进展是什么？哪里有 gap？"

**涉及 Skills：** `research-lit` + `novelty-check` + `research-review`

```
1. /research-lit "discrete diffusion models"    ← 搜论文，整理全景
2. 读完全景，发现一个 gap
3. /novelty-check "我的 idea 是用 X 来解决 Y"   ← 查新：有没有人做过？
4. /research-review "我的 idea 是用 X 来解决 Y"   ← 让外部 LLM 批判你的想法
5. 根据反馈迭代
```

📝 **博客：** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

---

## 🧰 全部 Skills

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|-----------------|
| 🔬 [`research-review`](skills/research-review/SKILL.md) | 单轮深度评审（外部 LLM，xhigh 推理） | 是 |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | 多轮自动 review→修复→再 review 循环（最多 4 轮） | 是 |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | 搜论文、分析相关工作、找研究空白 | 否 |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | 分析实验结果、统计、生成对比表 | 否 |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | 监控实验进度、收集结果 | 否 |
| 🔍 [`novelty-check`](skills/novelty-check/SKILL.md) | 查新：验证研究 idea 是否已有人做过 | 是 |

---

## ⚙️ 安装

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. （仅 review 类 skill 需要）安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```

### 安装 Skills

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
cd Auto-claude-code-research-in-sleep

# 安装全部 skills（全局可用）
cp -r skills/* ~/.claude/skills/

# 或者只安装特定 skill
cp -r skills/auto-review-loop ~/.claude/skills/
cp -r skills/research-lit ~/.claude/skills/
```

### 🌙 过夜自动运行的免确认配置（可选）

在 `.claude/settings.local.json` 中添加：

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__codex__codex-reply",
      "Write",
      "Edit",
      "Skill(auto-review-loop)"
    ]
  }
}
```

### 🖥️ GPU 服务器配置（自动跑实验用）

当 GPT-5.4 审稿说"需要补一个消融实验"或"加一个 baseline 对比"时，Claude Code 会自动写实验脚本并部署到你的 GPU 服务器。为此，Claude Code 需要知道你的服务器环境。

在项目的 `CLAUDE.md` 中添加服务器信息：

```markdown
## 远程服务器

- SSH：`ssh my-gpu-server`（密钥免密登录）
- GPU：4x A100
- Conda 环境：`research`（Python 3.10 + PyTorch）
- 激活：`eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- 代码目录：`/home/user/experiments/`
- 后台运行用 `screen`：`screen -dmS exp0 bash -c '...'`
```

Claude Code 读到这些就知道怎么 SSH、激活环境、启动实验。GPT-5.4（审稿人）只决定**做什么实验**——Claude Code 根据你的 `CLAUDE.md` 搞定**怎么跑**。

**没有 GPU 服务器？** Review 和改写功能不受影响，只有需要跑实验的修复会被跳过（标记为"需人工跟进"）。

## 🎛️ 自定义

Skills 就是普通的 Markdown 文件，fork 后随意改：

- **`MAX_ROUNDS`** — 增加轮数上限（默认 4）
- **`POSITIVE_THRESHOLD`** — 调整停止条件的分数阈值
- **优先级规则** — 调整算力限制、跳过策略
- **Prompt 模板** — 定制评审人格和评估标准
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具

## 📋 Roadmap

- [ ] **GLM-5（执行者）+ Minimax-2.5（评审者）** — 与 Claude Code + Codex 平行的跨模型组合
- [ ] 更多执行者 × 评审者组合（Gemini、DeepSeek 等）

## 💬 交流群

欢迎加入微信群，交流 Claude Code + AI 科研工作流：

<img src="wechat_group.jpg" alt="微信交流群二维码" width="300">

## ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260312)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

## License

MIT
