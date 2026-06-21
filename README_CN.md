# Auto-claude-code-research-in-sleep (ARIS ⚔️🌙)

<p align="center">
  <a href="https://huggingface.co/papers/2605.03042">
    <img src="docs/hf_daily_paper_1.svg" alt="Hugging Face Daily Paper · #1 Paper of the Day" width="360">
  </a>
</p>

[![技术报告](https://img.shields.io/badge/技术报告-arXiv%3A2605.03042-b31b1b?style=flat&logo=arxiv)](https://huggingface.co/papers/2605.03042) · [![ARIS 介绍 (HTML)](https://img.shields.io/badge/ARIS%20介绍-HTML%20%C2%B7%20由%20%2Frender--html%20生成-1a4a8c?style=flat&logo=html5&logoColor=white)](https://wanshuiyin.github.io/Auto-claude-code-research-in-sleep/ARIS_INTRO.html) · [![ARIS 介绍幻灯 — VALSE 2026](https://img.shields.io/badge/VALSE%202026%20幻灯-PDF%20%C2%B7%20由%20%2Fpaper--talk%20生成-EC1C24?style=flat&logo=adobeacrobatreader&logoColor=white)](docs/aris_intro_slides.pdf) · [![AI Agents 指南](https://img.shields.io/badge/AI%20Agents-AGENT__GUIDE.md-4B2E83?style=flat&logo=readthedocs&logoColor=white)](AGENT_GUIDE.md) · [![PaperWeekly 收录](https://img.shields.io/badge/PaperWeekly-收录-red?style=flat)](https://mp.weixin.qq.com/s/tDniVryVGjDkkkWl-5sTkQ) · [![Featured in awesome-agent-skills](https://img.shields.io/badge/Featured%20in-awesome--agent--skills-blue?style=flat&logo=github)](https://github.com/VoltAgent/awesome-agent-skills) · [![AI Digital Crew - Project of the Day](https://img.shields.io/badge/AI%20Digital%20Crew-Project%20of%20the%20Day%20(2026.03.14)-orange?style=flat)](https://aidigitalcrew.com) · [![GitHub 星标](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=flat&logo=github&logoColor=white&color=gold&label=Stars)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/stargazers) · [💬 加入交流群](#community) · [![引用](https://img.shields.io/badge/📖_引用-BibTeX-green?style=flat)](#citation)

💡 *在 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) / [Codex CLI](skills/skills-codex/) / [Cursor](docs/CURSOR_ADAPTATION.md) / [Trae](docs/TRAE_ARIS_RUNBOOK_CN.md) / [Antigravity](docs/ANTIGRAVITY_ADAPTATION_CN.md) / [GitHub Copilot CLI](docs/COPILOT_CLI_ADAPTATION.md) / [OpenClaw](docs/OPENCLAW_ADAPTATION.md) 里以 skill-based workflow 用 ARIS，或用独立的 **[ARIS-Code](docs/ARIS-Code-README_CN.md)** CLI 完整版体验——任你选！*

🌱 *ARIS 是方法论，不是平台。重要的是科研工作流——带着它去任何地方。*

🤖 **AI agent 兄弟们：** 直接读 [`AGENT_GUIDE.md`](AGENT_GUIDE.md) —— 给 LLM 消费的路由 index，不是给人浏览的。

🎬 **ARIS 走向多模态 → [ARIS-Movie-Director](https://github.com/wanshuiyin/ARIS-Movie-Director)** —— 把模糊的故事丢给 agent，睡醒收一部**跨模型审过的电影**（参考片 = 19 个场景）。长程视觉叙事会两头漂（🧠 **长程遗忘** · 🗣️ 每帧由**画它的模型自己签收**，错误一路累积）；ARIS 用同宗的法宝兜住 —— **research-wiki** 当记忆,**多智能体对抗审**(跨模型盲转写 + token-diff)确保*没有一帧能自己给自己放行*。

<p align="center">
  <a href="https://wanshuiyin.github.io/ARIS-Movie-Director/comic/">
    <img src="https://raw.githubusercontent.com/wanshuiyin/ARIS-Movie-Director/main/docs/comic_cover_v4.webp" alt="ARIS-Movie-Director —— 浏览器里看跨模型审过的图像电影（19 个场景）" width="100%">
  </a>
</p>

<p align="center">
  <a href="https://github.com/wanshuiyin/ARIS-Movie-Director">
    <img src="docs/aris-movie-director-method.png" alt="ARIS-Movie-Director 方法图 —— 受审螺旋：可信源头（asset library · outline · storyboard · comic.json）→ 逐格 image_gen + 跨模型 panel_gate（盲 token-diff、单票否决）→ research-wiki 审计留痕 → 组装与发布" width="100%">
  </a>
</p>

> 🧭 *不止做电影 —— 同一套**受审螺旋**也能生成干净的**方法图 / 流程图**:这张图就是 ARIS-Movie-Director 自己的 `image_gen` + 跨模型 `panel_gate` loop 跑出来的。👉 **skills 和端到端 CLI 都在 [ARIS-Movie-Director](https://github.com/wanshuiyin/ARIS-Movie-Director)**:[`/movie-pipeline`](https://github.com/wanshuiyin/ARIS-Movie-Director/blob/main/skills/movie-pipeline/SKILL.md)(agent 工作流 + 可独立跑的确定性 CLI 内核)和做出这张图的 [`/method-figure`](https://github.com/wanshuiyin/ARIS-Movie-Director/blob/main/skills/method-figure/SKILL.md)。*

<details>
<summary>🎞️ <i>参考片里的几帧 —— 故事自身的诚实度 beat：一次 <b>号称 <code>+6.2</code></b> 实则 <b>只动了 <code>+1.4</code></b> 的 run。</i> &nbsp;<b><a href="https://wanshuiyin.github.io/ARIS-Movie-Director/comic/">▶ 浏览器看全部 19 个场景 →</a></b></summary>

<table><tr>
<td width="33%"><a href="https://wanshuiyin.github.io/ARIS-Movie-Director/comic/"><img src="https://raw.githubusercontent.com/wanshuiyin/ARIS-Movie-Director/main/docs/preview_audit.webp" alt="ARIS-Movie-Director 帧 —— evaluator 诚实度审计页" width="100%"></a></td>
<td width="33%"><a href="https://wanshuiyin.github.io/ARIS-Movie-Director/comic/"><img src="https://raw.githubusercontent.com/wanshuiyin/ARIS-Movie-Director/main/docs/preview_panels.webp" alt="ARIS-Movie-Director 帧 —— 多格场景" width="100%"></a></td>
<td width="33%"><a href="https://wanshuiyin.github.io/ARIS-Movie-Director/comic/"><img src="https://raw.githubusercontent.com/wanshuiyin/ARIS-Movie-Director/main/docs/preview_fix.webp" alt="ARIS-Movie-Director 帧 —— 诚实度 beat（号称 +6.2，实际只动了 +1.4）" width="100%"></a></td>
</tr></table>

</details>

🎯 **准备 2026 AI 秋招？** → [**🌐 ARIS-in-AI-Offer 网页版**](https://wanshuiyin.github.io/ARIS-in-AI-Offer/) · [GitHub repo](https://github.com/wanshuiyin/ARIS-in-AI-Offer) · [English](https://github.com/wanshuiyin/ARIS-in-AI-Offer/blob/main/README_EN.md) —— 长文中文 ML / LLM / 多模态 / 生成式 / Agent 面试 cheat sheet，每篇 = 公式推导 + 从零 PyTorch + 25 高频面试题（L1 / L2 / L3），全部由 ARIS 的 `/render-html` 自动生成。**希望大家秋招的时候轻松一点 🌱**

<details>
<summary><b>🖼️ 预览</b> —— 三栏 cheat sheet（① 基础知识 · ② 面试 Q&amp;A · ③ 从零代码）</summary>

<p align="center">
  <a href="https://github.com/wanshuiyin/ARIS-in-AI-Offer">
    <img src="https://raw.githubusercontent.com/wanshuiyin/ARIS-in-AI-Offer/main/assets/preview_strip.jpg" alt="ARIS-in-AI-Offer 预览 — ① 基础知识 + ② 面试 Q&A + ③ 从零代码，三栏来自一篇代表性 cheat sheet" width="100%">
  </a>
</p>

</details>

> 📖 *预览来自 [Diffusion Foundations cheat sheet](https://wanshuiyin.github.io/ARIS-in-AI-Offer/tutorials/diffusion_foundations_tutorial.html) —— [ARIS-in-AI-Offer](https://github.com/wanshuiyin/ARIS-in-AI-Offer) 里每篇 tutorial 都按相同的三柱结构组织（基础 / 面试 Q&A / 可跑代码）。*
>
> 🌐 *同一套 workflow，不同的 deliverable —— [**ARIS-Homepage v1 live demo**](https://wanshuiyin.github.io/)（CV → fact-checked 单文件学术主页，由 `/homepage-generator` 生成）。*
>
> 📝 *三篇 long-form blog，跨模型协作写成（`/render-html`）—— [Continuous DLM：表征视角综述（2026 上半年）](https://wanshuiyin.github.io/ARIS-in-AI-Offer/blogs/continuous_dlm_representation_perspective.html) · [Cosmos 3：理解与生成缝进一个 Transformer（MoT）](https://wanshuiyin.github.io/ARIS-in-AI-Offer/blogs/cosmos3_mot_guide.html) · [扩散 × 表征 × 流形学习](https://wanshuiyin.github.io/ARIS-in-AI-Offer/blogs/diffusion_representation_manifold.html)。*

![ARIS Logo](docs/aris_logo.svg)

![Hero](docs/hero_combined.svg)

[English](README.md) | 中文版

> 🌙 **让 Claude Code 在你睡觉时做科研。** 醒来发现论文已被打分、弱点已被定位、实验已跑完、叙事已重写——全自动。
>
> 🪶 **极致轻量——无基础设施，零锁定。** 整个 skill 层就是纯 Markdown 文件。没有框架要学、没有数据库要维护、没有 Docker 要配、没有守护进程要看管。每个 skill 就是一个 `SKILL.md`，任何 LLM 都能读懂——换成 [Codex CLI](skills/skills-codex/)、[OpenClaw](docs/OPENCLAW_ADAPTATION.md)、[Cursor](docs/CURSOR_ADAPTATION.md)、[Trae](docs/TRAE_ARIS_RUNBOOK_CN.md)、[Antigravity](docs/ANTIGRAVITY_ADAPTATION_CN.md)、[Copilot CLI](docs/COPILOT_CLI_ADAPTATION.md)、Windsurf 或者你自己的 agent，工作流照样跑。Fork 它、改写它、适配到你的技术栈。

🛰 **社区好物 · [Claude Fleet](https://github.com/tianyilt/claude-fleet)**（by [@tianyilt](https://github.com/tianyilt)）—— 本地**只读**看板，一眼盯住并行的一堆 **Claude Code / Codex** 窗口(谁在跑 / 等授权 / 跑完了)，一键跳转 + 全文搜 transcript。多 agent 工作流神器，**好用点个 ⭐**

🪟 **更轻的自家选择 · [ARIS-Monitor](aris-monitor/)** —— ARIS 自带的 macOS 置顶**悬浮小窗**(纯 Python · 无浏览器)：只亮"**哪个会话在等你授权**" 🔴，点一行跳到那个终端。

<details>
<summary><b>🖼️ 预览</b> —— Claude Fleet 网页看板 &amp; ARIS-Monitor 悬浮小窗(自带)</summary>

<table align="center" width="100%">
<tr>
<td width="66%" align="center" valign="top">
<a href="https://github.com/tianyilt/claude-fleet"><img src="assets/claude-fleet-preview.png" width="100%" alt="Claude Fleet — 同时盯住一堆并行的 Claude Code / Codex 窗口的数据看板（triage / Focus / 全文搜索 / skill·memory 分析）"></a>
</td>
<td width="34%" align="center" valign="top">
<a href="aris-monitor/"><img src="aris-monitor/assets/screenshot.png" width="100%" alt="ARIS-Monitor — 极简置顶悬浮小窗，盯住哪个 Claude Code 会话在等你授权（all-clear 与红色 ATTENTION 双态）"></a>
</td>
</tr>
<tr>
<td align="center"><b><a href="https://github.com/tianyilt/claude-fleet">Claude Fleet</a></b> · 全功能网页看板</td>
<td align="center"><b><a href="aris-monitor/">ARIS-Monitor</a></b> · 极简悬浮小窗(自带)</td>
</tr>
</table>

</details>

<details>
<summary><b>几秒跑起来</b> —— ARIS-Monitor（5s）/ Claude Fleet（30s）</summary>

**ARIS-Monitor** —— 就在本仓库，不用 clone / 不装依赖 / 不开浏览器:

```bash
cd aris-monitor && ./run.sh
# 右上角冒出一个无边框悬浮窗;点一行直接跳到那个终端
```

**Claude Fleet** —— 全功能网页看板:

```bash
git clone https://github.com/tianyilt/claude-fleet
cd claude-fleet && bash run.sh
# 浏览器打开 http://127.0.0.1:7878
```

</details>

🚀 **从 科研 → 任何 "研究"**：[**ARIS-Anything**](https://github.com/wanshuiyin/ARIS-Anything) 把 ARIS 的五步 loop（plan / draft / 跨模型对抗审 / 迭代 / 持久化）从学术科研推广到非学术的结构化研究——投资尽调 / 法律研究 / 市场研究 / 自驱学习 / 调查新闻 / 工程复盘等。

🔥 [**ARIS-Code CLI — 独立安装版**](docs/ARIS-Code-README_CN.md) · [English](docs/ARIS-Code-README_EN.md) | [⬇️ 下载](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases/latest)

<table>
<tr>
<td valign="top" width="60%">

📰 **ARIS-Code v0.4.20**（2026-06）—— 最新是 **bug-fix 补丁**（Codex 排查出的 7 个用户可见修复：短 REPL 回复、粘连段落、CJK 表格、记住的 executor 模型、Esc 等；[#299](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/299)）。头牌特性：**v0.4.18 —— 默认模型 Claude Opus 4.8**（计费已修正 + 可用性 fallback）和 **v0.4.17 —— MCP 版本**（`mcpServers` 驱动真实工具调度；**跨模型对抗审无需 OpenAI API key** —— `aris setup` 一步把你的 **ChatGPT 订阅**经 *Codex MCP* 接成 reviewer）。收官 16 个 release 打磨（v0.4.5 → v0.4.20）；逐版本详情见下。贡献者：[@GetIT-Sunday](https://github.com/GetIT-Sunday)、[@Anduin9527](https://github.com/Anduin9527)、[@GO-player-hhy](https://github.com/GO-player-hhy)、[@Jxy-yxJ](https://github.com/Jxy-yxJ)、[@screw-44](https://github.com/screw-44)、[@StevenUST](https://github.com/StevenUST)、[@opposj](https://github.com/opposj)、[@ShijunLei-cn](https://github.com/ShijunLei-cn)、[@algojogacor](https://github.com/algojogacor)。

</td>
<td valign="top" width="40%">

<img src="docs/aris-code-banner.png" width="100%" alt="ARIS-Code CLI 终端 — Auto Research in Sleep">

</td>
</tr>
</table>

> <details><summary>逐版本详情（v0.4.5 → v0.4.20）</summary>
>
> **v0.4.20** (2026-06-19) — **bug-fix 补丁**：Codex 对抗式排查出的 7 个用户可见 bug，每个放行前审 3 轮（reviewer 在 GO 前抓到一处 redraw 缺口、一处尾随空行、一处 spinner 残尾、一处空行边界）。**🐛 头牌（[#299](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/299)）**：短 REPL 回复只剩 "✔ Done" —— spinner 用 Save/RestorePosition 画 "⠋ Thinking…"，让流式输出在同一行覆盖它，但 `finish` 随后清掉了整行，**把一条短的单行回复也抹了**。现在这一轮若打印过可见文本，REPL 收尾不再清行（`Clear(UntilNewLine)` 只擦回复之后的 spinner 残尾）。**流式多段回复粘连**（"para1para2"）—— 每个 chunk 的段落分隔符在流边界被裁掉；markdown 流式渲染器现在用 held-separator 保留分隔符，使流式输出等同一次完整渲染（无悬空空行）。**含 CJK/全角内容的 markdown 表格错位** —— 宽度现在按显示单元计（CJK = 2）而非字符数。**`aris "prompt"` / `--print` 忽略了 `aris setup` 存的 executor 模型**（此前仅 REPL 生效）—— 配了 OpenAI/自定义 executor 的人，请求却把 Anthropic 默认发到了它的 endpoint；一次性与 REPL 两条路径现在共用一个 resolver。**Esc** 现在真能关掉补全下拉（之前会被立刻重算回来）。**`glob_search`** 截断时报告匹配总数（而非封顶的 100，否则模型会以为 1000 个匹配只有 100 个文件）。**`/model` 的自定义菜单**读 executor 实际用的环境，而非过期的磁盘配置。测试（CI 模式）：api 32 / runtime 205 / tools 67 / aris-cli 172 / commands 5 全绿；新增 7 个；真机验证（短回复正常显示 + "✔ Done"；段落保留空行）。Codex MCP（gpt-5.5 xhigh）：排查 → 3 轮审（NO-GO → NO-GO → GO）。两个仅潜伏的候选（Anthropic block-`index` 路由、OpenAI 多行 SSE）推迟到一次加固 pass。
>
> **v0.4.19** (2026-06-14) — **诚实度 / guardrails 补丁**（主题来自一次 Codex fresh-eyes 审计；健康配置零行为变化）。**🔴 MCP 协议版本协商守卫** —— stdio 握手请求 `2025-03-26`，却从不读 server 协商回来的版本（一个被解析但没用的字段），于是 server 同意了一个 ARIS 不会说的版本也被静默接受，后续 `tools/list` / `tools/call` 跑在不兼容协议上、报错晦涩。ARIS 现在把协商版本对一个受支持集合（`2025-11-25` / `2025-06-18` / `2025-03-26` / `2024-11-05` —— 这些之间 stdio 分帧一致）校验，遇到不支持的就终止子进程 + 清槽 + 给出清晰的 per-server 报错（`aris doctor` 会显示）—— 正是 MCP 生命周期规范要求的"版本谈不拢就终止"。**请求**仍发 `2025-03-26`（对 `codex mcp-server` 验证过），健康 server 不受影响 —— 端到端验证：真实 Codex MCP server 在守卫下仍能拉起 + 初始化 + 暴露工具。**🧹 小瑕疵**：OpenAI 系 subagent 的响亮报错去掉了过期的 "lands in v0.4.18" 字样（现在版本无关 + 可操作，仍不含凭证）；OpenAI 上游错误体现在会被截断（500 字符）+ 凭证脱敏（`sk-…` key 和 `Bearer …` token，用子串扫描器抓住误配代理可能反射回来的紧凑 JSON 形态 `{"api_key":"sk-…"}`）而非原样喷出；system prompt 的 hook 事件摘要现在只数运行时真正执行的 hook（带 `command` 字符串的 `command` hook），和解析器对齐。测试（CI 模式）：api 32 / runtime 204 / tools 67 / aris-cli 167 / commands 5 全绿；live smoke 确认真实 Codex MCP server 在守卫下仍能初始化。Codex MCP（gpt-5.5 xhigh）审：design GO → impl NO-GO（漏了紧凑 secret + command-string 严格性）→ 修后 GO。
>
> **v0.4.18** (2026-06-14) — **默认模型 → Claude Opus 4.8**，附计费修正 + 安全网。这次升级把 `DEFAULT_MODEL`、`opus` 别名、模型选择器、`aris setup`、subagent 默认都移到 `claude-opus-4-8` —— 并带**可用性 fallback**：若账号没有 4.8（API 返回 `404 not_found_error`），ARIS 本会话自动回退到 `claude-opus-4-7`，**重建 system-prompt 的模型身份以保持自洽**（绝不在实际服务 4.7 时还告诉模型它是 4.8），告警一次后重试 —— 主会话（文本 + JSON）和 subagent 都覆盖。它只在那个精确的 404 上触发（绝不在 400/限流/鉴权上），有防循环 latch，文本路径从回合前快照重建，使重试绝不重复 append 用户消息；**有** 4.8 的账号与单纯升级字节一致。**💰 计费已修正**（对 Anthropic 公布的价目表核对过；此前高估了 3–5×）：当前 **Opus 4.5–4.8 = `$5/$25`**（弃用的 Opus 4/4.1 保持 `$15/$75`，按词边界切分，使未来的 `opus-4-10` 不被错分档）；**Sonnet 4.x = `$3/$15`**（与通用未知模型 fallback 解耦，后者仍 `$15/$75`）；Haiku 本就正确。**🧹 待办清理**：`aris setup` 选项 10 把 Codex MCP reviewer 钉到 `model_reasoning_effort="xhigh"`（对新配置确定、独立于 `~/.codex/config.toml`；幂等合并绝不覆盖已有条目）；启动时 + `aris doctor` 的**误配提示**（[#259](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/259)）针对被静默忽略/放错位置的配置（坏 JSON，或一个多余的 `~/.aris/config.yaml` —— 仅 stderr，使 `--print`/JSON stdout 保持干净）；system prompt 的 hook 摘要现在把"解析了但从不触发"的事件标为 **"PARSED ONLY … will NOT run"** 而非暗示死 hook 会跑（完整事件展开 —— 真正触发 `SessionStart`/`SessionEnd`/… —— 推迟到单独 issue）。测试（CI 模式）：api 32 / runtime 202 / tools 67 / aris-cli 166 / commands 5 全绿；一次 live one-shot smoke 端到端返回 `model=claude-opus-4-8`。Codex MCP（gpt-5.5 xhigh）审了 design + 两批实现（design REWORK→GO，impl NO-GO→GO，batch-2 GO）。
>
> **v0.4.17** (2026-06-13) — **MCP 版本。** v0.4.17 之前，`settings.json` 里的 `mcpServers` 只是被解析、在 `aris doctor` 里显示，却**什么都不做**；现在 ARIS 会拉起每个配置的 stdio server、走 MCP 握手、发现工具，并在 **Anthropic + OpenAI 两条 provider 路径**上以 `mcp__<server>__<tool>` 暴露，端到端调度 + 单 server 软降级 + 未受信 MCP 工具的审批门（`--allowedTools` 现接受 `mcp__` 名）。**🆕 零 API key 的跨模型 reviewer**：`aris setup` → **选项 10（Codex MCP，ChatGPT 订阅，无需 API key）** 把幂等的 `mcpServers.codex` 写进运行时真正读取的配置文件（原子写 + 备份，`trust: true` 前显式确认），可选 API reviewer 作 **fallback**（`ARIS_REVIEWER_PROVIDER=codex-mcp` + `ARIS_REVIEWER_FALLBACK_PROVIDER`）；REPL 内 `/setup` 重建 system prompt + runtime，reviewer 改动无需退出即生效。**🔴 假 server 测不出的协议 bug**：真机 e2e 对着 `codex mcp-server` 才暴露——我们的 stdio 传输在用 LSP 式 `Content-Length:` 分帧，而 MCP 规范（和 codex）用**换行分隔的 JSON-RPC**；所有 fake-server 测试都过，是因为 fake 也讲同一种错方言。现在写为 NDJSON、读两种都自动识别，并在 `initialize` 后补发规范要求的 `notifications/initialized`（顺带用 select 往返修掉 [#286](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/286) 大请求死锁）。**Hooks**：object 式 Claude Code hook 保留 `matcher` / `timeout` / `async`（锚定正则匹配；每 hook 超时，默认 30s kill = 警告而非拒绝）。**收尾**：codex `codex/event` 通知刷屏默认静默（`ARIS_MCP_STDERR=inherit` 开），system prompt 现告诉模型**别**给 Codex 传 `model` 参数（账号默认 = gpt-5.5 + xhigh），Codex-MCP 为主且无 fallback 的 `LlmReview` 调用返回清晰的 “用 `mcp__codex__codex`” 提示而非误导性的 `OPENAI_API_KEY` 报错。沿用 v0.4.16 零回归方法论（24 个新 characterization 测试）。测试（CI 模式）：runtime 199 / aris-cli 165 / tools 67 / api 30 / commands 5 全绿。Codex MCP（gpt-5.5 xhigh）逐 phase 审 17 轮（7 个 NO-GO 全解决）。
>
> **v0.4.16** (2026-05-30) — REPL UX + provider 加固,零回归纪律交付:先写 64 个 characterization（golden）测试锁死**当前** provider 路由 / 计费 / reviewer / subagent / REPL 行为,再动手改,全程保持绿。关闭 [#274](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/274)：命令历史持久化到 `~/.config/aris/history`（0600 权限）,启动自动加载;`ARIS_NO_HISTORY` 一键关闭;disk-only secret-skip——疑似凭证的行保留在会话内历史但**永不落盘**。bash 风格 **Ctrl+R** 反向增量搜索（CJK 显示宽度感知的单行渲染;不改任何现有按键;零新依赖）。安全:OpenAI 系主会话（Kimi / GLM / MiniMax / …）派 subagent 此前会**静默扣用户的 Anthropic OAuth/Keychain 凭证**,现在改为响亮报错（错误信息不含凭证名）;完整 OpenAI 系 subagent 路由是跨 crate 改动,推迟到 v0.4.17。地基（零行为变化）:3 处字节级相同的词边界匹配器合并为唯一权威 `runtime::word_match`;新增纯分类器 `ProviderFamily`（未接线）。测试（CI 模式）:runtime 164 / aris-cli 128 / tools 49 / commands 5 全绿。Codex MCP（gpt-5.5 xhigh）逐 phase 审 + 最终集成审。
>
> **v0.4.15** (2026-05-29) — OpenAI-兼容流式健壮性 hotfix。关闭 [#249](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/249)：MiniMax（及其他 OpenAI-compatible provider / 代理）实际不可用,因为 clean-EOF 完成判定把 `data: [DONE]` 哨兵当成**唯一**权威完成信号。非空 `choices[].finish_reason` 才是 Chat Completions spec 定义的终止帧标志,`[DONE]` 只是部分 compat provider 不发的 transport 约定（MiniMax 发 `finish_reason: "stop"` 然后直接关连接不发 `[DONE]`）。clean-EOF 判定现在抽成可单测纯函数 `stream_eof_action(...)`,见到 `[DONE]` **或** 非空 `finish_reason` 任一即算完成;**不**在 finish_reason 处提前停读（include_usage 尾随 usage-only chunk 仍消费）;真截断仍硬报错,出输出前 proxy abort 仍重试。配套：**OE7** finish_reason 移到 `delta` guard 前读（只带 finish_reason 无 delta 的终止 choice）；**OE2** 任何非空 finish_reason 都 flush pending tool；**OE4** mid-stream error 信封硬报错不再静默吞；**OE3** 容忍 `data:{...}` 冒号后无空格。+5 单测（77→82）把此前零覆盖的 SSE 完成逻辑抽成纯函数。Anthropic SSE 路径未动。Codex MCP（gpt-5.5 xhigh）3 轮（GO-WITH-NITS → GO-WITH-NITS → GO）。
>
> **v0.4.14** (2026-05-25) — 安全 + 文档卫生 release，关闭 v0.4.13 codex audit（gpt-5.5 xhigh，6/10 NEEDS-REWORK）最关键的几项。**🔴 S9 (P0) system prompt 配置脱敏** — v0.4.14 之前 `render_config_section()` 把合并后的 `settings.json` 原样塞进发给 LLM provider 的 system prompt，会泄漏 `env`、`mcpServers.<name>.headers.Authorization` Bearer token、hook command env、签名 URL 的 query 参数、`apiKey` 等字段。新渲染器：白名单顶层字段（`model`/`permissionMode`/`theme`/`outputStyle`/`permissions`/`sandbox` 子树仍走递归 redact）原样输出；敏感 key（`apikey`/`token`/`secret`/`password`/`authorization`/`headers`/`env`/`_KEY`/`_SECRET`/`_TOKEN`）递归替换成 `[REDACTED]`；MCP `command` 替换 `<configured>` 占位符；MCP `url` 仅保留 `<scheme://host[:port]>` origin（scheme 仅 `http`/`https`/`ws`/`wss`，host 仅 ASCII，port 仅数字，IPv6 走 `[...]`）；hook command 字符串完全不输出。Regression test 覆盖 9 处 leak 面；URL parser 单独测 7 种 smuggling（含 codex round-3 抓到的 port 位置 secret 注入）。**🟡 P9 (P1)**：DeepSeek `aris --help` 指向 `aris setup` option 7（真正的 anthropic-compat 菜单项），不再印那条 resolver 根本不认的 `EXECUTOR_PROVIDER=anthropic-compat` env 路径。**🟡 M1/M2 (P1) 文档**：`aris doctor` + README + README_CN 在 `mcpServers.len() > 0` 时打黄色实验性 warning（完整 MCP 工具分发 v0.4.16 落地）。**🟢 C11 (P2) 流式 idle timeout** — Anthropic `MessageStream` 和 OpenAI SSE loop 都在 `response.chunk().await` 外包 `tokio::time::timeout`（env `ARIS_STREAM_IDLE_TIMEOUT_SECS`，默认 120，clamp `[10, 1800]`，0/负数关闭）；关闭"aris 永远卡死无输出"症状（broken proxy 不发 keepalive 时）。**Bundle**：77 skills（+1 `/wiki-enrich`，同日 late sync 到 main `7e3ab67` 顺带把上游 `check_ready.sh` awk + grep-c null-match 修复也带进来），54 helpers。Codex MCP 6 轮（NO-GO + 4 → GO-WITH-NITS + 3 → NO-GO + port smuggling → GO → release metadata GO → sync GO）。
>
> **v0.4.13** (2026-05-25) — 收尾 release，关闭从 v0.4.10 到 v0.4.12 累积的所有 codex audit P1 + 补长尾 regression test。**🟡 v0.4.10 P1.D per-server MCP timeout** — `mcpServers.<name>.requestTimeoutSecs` override > `MCP_REQUEST_TIMEOUT_SECS` env > 300s default（clamp 1..=1800），让 codex MCP 可以 5 分钟而 fs MCP 5 秒 timeout 共存。**🟡 v0.4.10 known limitation 关闭** — `McpStdioProcess::request()` 跳过 JSON-RPC notification (id 缺失/null) 继续读直到 response。**🟢 meta_opt hook 通过 `aris init` 部署** — `tools/meta_opt/{log_event,check_ready}.sh` 嵌入 binary，`aris init` 写 ARIS-namespaced **`aris-meta-opt-log-event.sh`** / **`aris-meta-opt-check-ready.sh`** 到 `~/.claude/hooks/`（codex round-1 #1：永远不覆盖用户已有同名 hook）；settings.json 合并 idempotent + backup 强保证 + tempfile + rename 原子写。**🧪 9 个 v0.4.12 targeted regression test** 覆盖 sandbox.strictMode (3) + parse strictMode + provider_match pricing + has_word o-series + stream_options 400 + meaningful-content classification + premature-EOF retry truth table（codex round-1 #3 — `should_retry_on_premature_eof()` 提成纯函数 + 7 行真值表）。**Bundle**：76 skills，**54 helpers**（+2 meta_opt 脚本 vs v0.4.12）。Codex 3 轮（NO-GO + 3 → NO-GO + metadata → GO）。
>
> **v0.4.12** (2026-05-22) — Bug-fix + 小功能 release。**#238 `sandbox.strictMode`** opt-in 配置项；为 `true` 时 `SandboxConfig::resolve_request()` 忽略全部 5 个 LLM-supplied override（`dangerouslyDisableSandbox`、`namespaceRestrictions`、`isolateNetwork`、`filesystemMode`、`allowedMounts`）—— 关掉 tool-call 静默绕过用户 sandbox 策略的漏洞。`aris doctor` 加 "Sandbox:" 一行；bash tool schema 文档化 strictMode 语义。**#232** `auto-review-loop-llm` 从老的 `deepseek-chat` / `deepseek-reasoner`（2026-07-24 弃用；reasoner reject `tool_choice`）改成 `deepseek-v4-flash` / `deepseek-v4-pro`。**v0.4.10 audit P1 follow-up**：P1.A Anthropic 流式 retry 改成基于 `has_emitted_meaningful_content`（只发了 `MessageStart` 就 EOF 也能 retry）；P1.B `supports_reasoning_effort` + reviewer 镜像都用 word-boundary 匹配，`openai/o3-mini` / `proxy:o4` 走对路径；P1.C `stream_options.include_usage:true` proxy fallback —— 真的 400 报 unknown field 时去掉这个字段 retry 一次；P2 pricing 用新 `provider_match()` 让 `qwen3.6-plus` / `kimi-k2.5` 走对 tier，同时拒绝 `my-kimi-clone` 这种 mid-word 误判。**Skills 追新**（76 skills, 52 helpers）：嵌入 `/interview-cheatsheet` + `/render-html`；`build.rs` `ALLOWED_EXTS` 加 `html`；`EXCLUDED_SKILL_PREFIXES` → `starts_with("skills-codex")`。**CI fetch-depth: 0** + origin/main fetch 让 drift-test ancestor check 真生效。Codex MCP（gpt-5.5 xhigh）4 轮 review。
>
> **v0.4.11** (2026-05-18) — Skills bundle 刷新 + sync 基础设施。v0.4.10 binary 嵌入的 skills 已落后 main（56 个 main `skills/` commits 中只有 ~6 个被 cherry-pick 进 bundle）；v0.4.11 sync 完整集合 + 落 sync infrastructure 防漂移再扩大。Bundle：65→74 个 user-facing skill，34→49 个 helper resource。新嵌入 10 个 skill：`/citation-audit`（第四层文献审计：存在性 + metadata + 引用 context）、`/experiment-queue`（SSH 多 seed 任务队列，含 OOM retry）、`/kill-argument`（理论论文双线对抗审）、`/resubmit-pipeline`（W5：纯文本换会议投稿）、`/paper-talk`（端到端 conference talk pipeline）、`/slides-polish`（逐页 Codex 排版审）、`/overleaf-sync`（双向 Overleaf Git-bridge）、`/gemini-search` + `/openalex`（更广文献源）、`/qzcli`（启智 GPU 任务）。46 个已有 SKILL.md 刷新——最关键是 canonical resolver chain 全面铺开（修复真实事故：硬编码 `tools/research_wiki.py` 让 `/research-wiki` 空了一周）+ submission assurance gate + external verifier（`/paper-writing` Phase 6 现在能跑通）。tools/ 9→18：9 个 baseline 刷新（`research_wiki.py` 从 315 行刷到 767 行含 canonical `ingest_paper` API）+ 9 个新增（`extract_paper_style.py`、`figure_renderer.py`、`paper_illustration_image2.py`、`overleaf_{setup,audit}.sh`、`verify_wiki_coverage.sh`、`watchdog.py`、`experiment_queue/{build_manifest,queue_manager}.py`）。新 `tools/sync_main_skills.sh` 自动化 main → bundle rsync（symlink 前置检测 + codex-mirror prune + `SKILLS_SOURCE_COMMIT` 钉版本）。`crates/runtime/src/cache.rs` 新增 3 个 CI drift test 覆盖全部 4 个 resolver layer pattern。`/research-lit` 和 `/gemini-search` 的 Gemini MCP 调用改成 `model: 'auto-gemini-3'`（避免 OAuth-personal 在 capacity 满时 silent downgrade 到 2.5-pro）。CLI runtime 行为不变——codex-audit P1 follow-up 留在 v0.4.12 backlog。Codex MCP（gpt-5.5 xhigh）5 轮交叉评审（REQUEST CHANGES → APPROVE WITH NITS → NO-GO → GO → final GO）。
>
> **v0.4.10** (2026-05-17) — 流式 + MCP 可靠性 + 多 provider 计费。C6 Anthropic `MessageStream` 和 OpenAI SSE 循环都支持 chunk decode 失败 / 早 EOF 时整段重启请求（`ARIS_STREAM_RETRY`，default 2，clamp 0..=5，仅在尚未输出任何内容时触发——关闭 [#228](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/228) "error decoding response body" 循环）。M3 MCP stdio 用 `tokio::time::timeout` 同时包 send + read（default 300s，env `MCP_REQUEST_TIMEOUT_SECS` clamp 1..=1800）+ `response.id ↔ request.id` 关联校验 + `ensure_server_ready()` `try_wait()` 检测死进程并 respawn + 任何失败路径 `kill().await` 让下次调用从干净状态开始（关闭 [#151](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/151) / [#172](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/172) "Calling codex..." 卡死）。C8/P4 OpenAI 流式请求加 `stream_options.include_usage:true` + 解析 `cached_tokens`；Anthropic 流式合并 `MessageStart.usage`（input/cache）和 `MessageDelta.usage`（output）。C9 多 provider 计费 registry（15+ 模型，OpenAI cache_read = input × 0.1 修正之前 generic 50% 高估 5×，DeepSeek cache_hit/cache_miss 分层，`has_word()` boundary matcher 让 `provider/<model>` slug 走对 tier）。9 个 dead-code warning 修复；`aris setup` help 文案与实际行为同步。
>
> **v0.4.9** (2026-05-17) — 关闭 Codex v0.4.7 audit 三个 cross-cutting 残留（L1 TLS 双栈 / L3 reasoning_cache 错位 / L4 reasoning replay 无 cap）。2 个新 skill 嵌入（`/figure-spec` + `/paper-illustration-image2` 含 `scripts/` 子目录，新 Layer 0b = `$ARIS_CACHE_DIR/skills/<name>/scripts/`）；`research_wiki.py` 提升到 shared `tools/`（9+ 调用方）；5 个 SKILL.md 迁移到 fallback chain。
>
> **v0.4.8** (2026-05-17) — Skill helper 子系统重写。Bundled helper 在 startup 提取到 `~/.config/aris/cache/<version>/`；每次 Skill 调用输出 `helperReport` JSON + 4 层 resolver preamble；`/skills export` 一并导出 helper；新 `integration-contract.md` 含 6 个失败策略；8 个 shared helper（arxiv/deepxiv/exa/S2/openalex/save_trace/verify_papers/verify_paper_audits）嵌入；`/research-lit` + `/deepxiv` 迁移。另 4 个 bug 修复：gpt-5.5+tools 在 OpenAI 400；Custom reviewer 重启变 gpt-5.5；缺 `signature` 字段 ([#228](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/228))；`--version` Build date 硬编码。
>
> **v0.4.7** (2026-05-16) — DashScope Coding Plan 405 修复 ([#159](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/159)) 通过 `native-tls` 切换 ([#225](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/225))；所有 reasoning model 的 `reasoning_content` replay（不只 Kimi）([#226](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/226))；600+ 行死代码 + `rustyline` 移除 + "Claw Code" → "ARIS-Code" 品牌统一。
>
> **v0.4.6** (2026-05-14) — 🚨 两个长期静默 bug 修复：`PermissionMode::Prompt` 因 derived-`Ord` 顺序错误一直在静默放过所有 tool；system prompt 硬编码 `current_date = "2026-03-31"` 让 model 把真实数据判为"未来 / prompt injection"。另 Custom OpenAI 兼容 provider（`/setup` 选项 11）+ dynamic `/models` 发现（[@Anduin9527](https://github.com/Anduin9527) [#221](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/221) + [#222](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/222)）。
>
> **v0.4.5** (2026-05-13) — 推理模型一等公民支持：thinking content blocks 全链路（修 [#161](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/161)）+ `reasoning_effort='xhigh'` 真正发到 GPT-5.5 / o1 / o3 / o4 / DeepSeek-thinking。DeepSeek V4 Pro + Xiaomi MiMo + Qwen 3.6 + Doubao 加入 `/setup`（选项 7-10）。对象式 hooks 解析器。默认模型升级 Claude Opus 4.7 + GPT-5.5。REPL 输入加固（折行 / Cmd+V 粘贴 / CJK 边界）。新增 GitHub Actions CI workflow。贡献者：[@GO-player-hhy](https://github.com/GO-player-hhy) ([#186](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/186))、[@Jxy-yxJ](https://github.com/Jxy-yxJ) ([#171](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/171))、[@GetIT-Sunday](https://github.com/GetIT-Sunday) ([#216](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/216) 部分)。
>
> </details>
> <details><summary>更早历史版本</summary>
>
> **v0.4.4** (2026-04-20) — Setup UX + reviewer 路由修复（修 [#158](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/158) / [#162](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/162)）| Anthropic + 自定义 URL 不再强制 Bearer | LlmReview 智能 fallback
>
> **v0.4.3** (2026-04-17) — 第三方 Anthropic-compat 代理支持（Bedrock 等）| 致谢 [@screw-44](https://github.com/screw-44)
>
> **v0.4.2** (2026-04-17) — Auto-compaction 修复 | OpenAI-compat 摘要保留 | Shell API key 不再被清
>
> **v0.4.1** (2026-04-15) — Plan 模式 + Ctrl+C 协作中断 + 自动重试 (429/5xx) | 多文件 Memory
>
> </details>

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主 ML 科研工作流。核心机制是**跨模型协作**——Claude Code 负责执行（读文件、写代码、跑实验、收结果），外部 LLM（通过 [Codex MCP](https://github.com/openai/codex)）负责评审（打分、找弱点、建议修复）。两个模型互不评自己的作业，形成真正的反馈循环。🔀 **也支持[替代模型组合](#alternative-model-combinations)（Kimi、LongCat、DeepSeek 等）——无需 Claude 或 OpenAI API。** 例如 [MiniMax-M3 + GLM-5 或 GLM-5 + MiniMax-M3](docs/MiniMax-GLM-Configuration.md)。 🤖 **[Codex CLI 原生版](skills/skills-codex/)** — 完整 skill 集合也支持 OpenAI Codex。🖱️ **[Cursor](docs/CURSOR_ADAPTATION.md)** — Cursor 也能用。🖥️ **[Trae](docs/TRAE_ARIS_RUNBOOK_CN.md)** — 字节跳动 AI IDE。🚀 **[Antigravity](docs/ANTIGRAVITY_ADAPTATION_CN.md)** — Google Agent-First IDE。🐙 **[Copilot CLI](docs/COPILOT_CLI_ADAPTATION.md)** — GitHub 终端 Agent（原生 SKILL.md + MCP）。🆓 **[ModelScope 免费接入](docs/MODELSCOPE_GUIDE.md)——零成本，零锁定。**

> 💭 **为什么不用单模型自我博弈？** 用 Claude Code 的 subagent 或 agent team 同时做执行和审稿在技术上可行，但容易陷入**局部最优**——同一个模型审自己的输出会产生盲区。
>
> *类比 bandit 问题：单模型自审是 stochastic bandit（噪声可预测），跨模型审稿则是 adversarial bandit（审稿者会主动探测执行者未预料的弱点）——而 adversarial bandit 天然更难被 game。*
>
> 💭 **为什么是两个模型而不是更多？** 两个是打破自我博弈盲区的最小配置，且双人博弈收敛到 Nash 均衡的效率远高于多人博弈。增加更多审稿者只会增加 API 开销和协调成本，边际收益递减——最大的提升来自 1→2，而非 2→4。
>
> Claude Code 的优势是快速丝滑的执行，Codex（GPT-5.5 xhigh）虽然慢但审稿更严谨深入。两者**速度 × 严谨**的互补特性，比单模型自我对话效果更好。
>
> 🧿 **想要最强审稿者？** 任何 skill 加 `— reviewer: oracle-pro` 即可通过 [Oracle MCP](https://github.com/steipete/oracle) 调用 **GPT-5.5 Pro**。Pro 级推理能力适合证明验证、实验审计和最终 stress test。支持 API key 或免费浏览器模式。[设置 →](#-optional-gpt-54-pro-via-oracle)

<a id="contents"></a>

## 目录

1. [不止一句 Prompt](#more-than-just-a-prompt)
2. [最近更新](#whats-new) · changelog
3. [快速开始](#quick-start) · 安装 + 第一次跑
4. [功能亮点](#features)
5. [真实运行效果](#score-progression)
6. [社区实操 — 用 ARIS 完成的论文](#community-showcase)
7. [Awesome 社区 Skills & 扩展](#awesome-community-skills)
8. [工作流](#workflows) · 13 个命名 pipeline（W1 / W1.5 / W2 / W3 / W4 / W5 / W6 / Wiki / WM + Effort / Assurance / Oracle）
9. [安装](#setup) · prerequisites / install / update / usage / [GPU 服务器配置](#gpu-server-setup)
10. [自定义](#customization) · 每个 skill 的配置开关
11. [替代模型组合](#alternative-model-combinations) · GLM / MiniMax / Kimi / 等
12. [交流群](#community)
13. [引用](#citation)
14. [Star History](#star-history)
15. [致谢](#acknowledgements)
16. [License](#license)

---

<a id="more-than-just-a-prompt"></a>

## 1. 🎯 不止一句 Prompt

**基础模式** — 给 ARIS 一个研究方向，全自动：

```
/research-pipeline "离散扩散语言模型的 factorized gap"
```

**🔥 精准模式** — 有篇论文想改进？把论文 + 代码给 ARIS：

```
/research-pipeline "改进方法 X" — ref paper: https://arxiv.org/abs/2406.04329, base repo: https://github.com/org/project
```

ARIS 读论文 → 找弱点 → 克隆代码 → 针对*那些*弱点用*那套*代码生成改进方案 → 跑实验 → 写论文。就像跟研究助手说：*"读这篇论文，用这个 repo，找出哪里不行，然后修好它。"*

> 自由组合：`ref paper` 单独 = "这篇论文哪里能改进？"，`base repo` 单独 = "这个代码能做什么？"，两个都给 = "用*这个*代码改进*这篇*论文。"

**🔥 Rebuttal 模式** — 审稿意见来了？别慌。ARIS 读每条意见、制定策略、起草安全的 rebuttal：

```
/rebuttal "paper/ + reviews" — venue: ICML, character limit: 5000
```

三道安全门：
- 🔒 **不编造** — 每句话有出处
- 🔒 **不过度承诺** — 没批准的不承诺
- 🔒 **全覆盖** — 每个审稿意见都追踪

两版输出：`PASTE_READY.txt`（精确字数，直接粘贴）+ `REBUTTAL_DRAFT_rich.md`（详细版，自己改）

<details>
<summary><b>展开 rebuttal 参数</b> —— venue、character limit（必填）、quick mode、auto experiment、压测轮数、follow-up 上限</summary>

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `venue` | `ICML` | 目标会议 |
| `character limit` | — | **必填。** 字符限制 |
| `quick mode` | `false` | 仅解析 + 策略（Phase 0-3），先看审稿人要什么 |
| `auto experiment` | `false` | 自动跑补充实验（`/experiment-bridge`） |
| `max stress test rounds` | `1` | GPT-5.5 压力测试轮数 |
| `max followup rounds` | `3` | 每个 reviewer follow-up 上限 |

</details>

**中稿之后** — 论文录了，准备展示：

```
/paper-slides "paper/"     # → Beamer PDF + PPTX + 演讲稿 + Q&A 预案
/paper-poster-html "paper/" # → 测量门控 HTML/CSS 海报 → 可印刷 PDF
```

> *💡 从 idea 到论文到讲台到 rebuttal——一条工具链。🌱*
> 以上是全流程——你也可以单独用任何一个工作流。已有 idea？直接进工作流 1.5。有结果了？跳到工作流 3。见[快速开始](#quick-start)查看所有命令，[工作流](#workflows)了解完整流程。

<a id="whats-new"></a>

## 2. 📢 最近更新

- **2026-06-20** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📚 **Research wiki 四层节点全部用确定性写入器 —— 修复"重新生成的 idea 没被记录"**([#305](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/305)、[#306](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/306)、[#307](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/307)、[#308](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/308))。一位用户踩到真 bug:首次 `/idea-creator` 记下的 idea,重新生成时不见了 —— 因为 wiki 页面是 **freehand**(LLM 手写)写的,这种 prose 步骤在"再生成一版"时容易被跳过。现在每层都有专属 `research_wiki.py` 写入器,与 `ingest_paper` 并列:**`add_claim`**(claim 出生于 [`/proof-checker`](skills/proof-checker/SKILL.md))、**`upsert_idea`**([`/idea-creator`](skills/idea-creator/SKILL.md))、**`add_experiment`**([`/result-to-claim`](skills/result-to-claim/SKILL.md)),每个都有 drift-check 守护、防止退化成死代码。claim 的 `status` 现在是严格的**证明轴**(`verified`/`refuted`/`unproven`/…),实验支持改由 `supports`/`invalidates` **边**承载(修掉一个共享 validator 会拒绝的潜伏矛盾);**Codex-CLI skill 镜像也已同步**。无 `research-wiki/` 时**零行为变化**。
- **2026-06-19** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛰 **通宵 loop 韧性:静默死亡看门狗 + stall→结构性 pivot**([#300](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/300)、[#301](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/301)、[#302](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/302);运行时模式吸收自 [Deli Chen 的 AutoResearch](https://victorchen96.github.io/auto_research/framework.html) 框架)。补两个无人值守 `/loop` / `CronCreate` 心跳抓不到的失败模式。**(1) 静默死亡** —— 心跳寄生于活着的 session,context 压缩或 session 关闭会把它杀掉而无人察觉。新增 watchdog `loop` 任务类型([`watchdog.py`](tools/watchdog.py))以状态文件的 mtime 对比该 loop 自己声明的 `stale_after_seconds` 判活,把 **STALE / MISSING / COMPLETED** 写入 `alerts.log` —— **仅检测**,绝不重启任何带裁决性质的 loop。**(2) 认知打转** —— 卡住的 loop 会无限重试近似变体。新增 [`iteration_log.py`](tools/iteration_log.py) 每个 tick 计数 NEW findings:`stale_count ≥ 2` 强制**结构性** pivot(换 frame + 选一个没试过的方向),`≥ 4` 升级给人处理。两者都是 **Type-A 信号** —— 只说"继续 / 换方向",从不说"够好了";质量裁决仍然终结于跨模型裁判席。
- **2026-06-07** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🖼️ **[`/paper-poster-html`](skills/paper-poster-html/SKILL.md) —— 新的默认海报流水线(skill #79);LaTeX 版 `/paper-poster` 退役为重定向 stub。** 海报即单个 HTML/CSS 文件,按会议官方印刷画布迭代,**靠测量不靠目测**:硬性 gate(列底对齐 spread < 5 px、双色相 design-token 纪律、论文原图 provenance manifest、图面积区间)全 PASS 之后 reviewer 才能看到海报;封闭修复词表(token / 组件 / 内容再平衡 / 素材 / 画布)从结构上杜绝化妆式 patch 死循环;内容保真由 fresh 跨模型审裁决(claim→evidence 审计 + 最终印刷就绪审)。内置 3 套模板 + 组件库(含信息密度组件:公式逐项解剖、flow-strip、双图合卡、derived-Δ 表、claim pills)和 6 个会议配色 token 包。门控机制改造自 [posterly](https://github.com/Chenruishuo/posterly)(MIT,by [@Chenruishuo](https://github.com/Chenruishuo))——ARIS 增加风格/素材 gate、密度体系与跨模型审循环。⚠️ `/paper-poster` 现在重定向到 `/paper-poster-html`;旧 LaTeX 流水线仅存于 git history。
- **2026-05-31** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🤝 **社区好物 —— 两个值得一看的工具。** [**Claude Fleet**](https://github.com/tianyilt/claude-fleet)（[@tianyilt](https://github.com/tianyilt)）—— 本地只读看板，同时 triage / Focus / 全文搜你开的一堆 **Claude Code + Codex** 窗口。[**posterly**](https://github.com/Chenruishuo/posterly)（[@Chenruishuo](https://github.com/Chenruishuo)）—— 一个 Claude Code skill，把学术会议海报做成单个 HTML/CSS 文件 → 可印刷 PDF（headless Chromium，无需 LaTeX）。两个都收录在 [Awesome 社区](#awesome-community-skills)。觉得有用 🌟 一下。
- **2026-05-28** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📝 **首篇 blog 上线**：[A Survey on Continuous DLM (2026 H1, 6 papers)](https://wanshuiyin.github.io/ARIS-in-AI-Offer/blogs/continuous_dlm_representation_perspective.html) —— Ruofeng Yang (SJTU) 写的 long-form 双语技术综述，全程通过 ARIS-in-AI-Offer workflow 完成（Claude Opus 4.7 + Codex GPT-5.5 xhigh + Gemini auto-gemini-3 跨模型讨论）。对比 ELF / 字节 Cola-DLM / Flow-Matching 系列：discrete-DLM 的问题、"known-unknown" 连续空间思路、训练 pipeline、架构 / 参数 / shapes、推理 grids + Tab 6/7 数值结果、去噪轨迹、对比 Cola-DLM 的 Field Landscape。单文件自含 HTML（1.7 MB，无 build）—— 展示 `/render-html` toolchain 能产出的 long-form 研究分析深度。
- **2026-05-26** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🌐 **8 个 workflow 关键节点自动出 HTML view**。`/idea-discovery`、`/auto-review-loop`、`/research-pipeline`、`/kill-argument`、`/proof-checker`、`/paper-claim-audit`、`/citation-audit`、`/rebuttal` 跑完会自动调 [`/render-html`](skills/render-html/SKILL.md) 把主 MD 工件渲染成单文件 HTML。成本分层：interim view 用 `--no-review`，audit / reviewer-facing 交付物保留 full Codex render-fidelity gate。默认开（`RENDER_HTML = true`），每个 skill 可单独 opt-out。失败非阻塞 —— MD 源始终是 canonical。
<details>
<summary>更早的更新（2026-03-12 — 2026-05-29，60 条）</summary>

- **2026-05-29** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) ⚙️ **ultracode 原生约定层 —— 任意运行时档位都能 fan out 拓宽广度，跨模型裁判席始终神圣不可侵犯**。三个新 [`shared-references`](skills/shared-references/) 文档把*广度*和*裁决*解耦：[`fan-out-pattern.md`](skills/shared-references/fan-out-pattern.md)（skill 用同家族 Claude subagent 生成候选 —— Tier-1 Workflow / Tier-2 Agent / Tier-3 顺序 —— 全部汇入*同一个*跨模型裁判席），[`acceptance-gate.md`](skills/shared-references/acceptance-gate.md)（"loop 可以 DRIVE，不能 ACQUIT" —— 可自判执行完成度，绝不可自判质量/正确性），[`external-cadence.md`](skills/shared-references/external-cadence.md)（`/loop` 和 `CronCreate` 只是 fire-control，绝非裁判席）。已接入 `/idea-creator`、`/research-lit`、`/proof-checker`、`/kill-argument`（fan-out）+ 16 个 skill（cadence fence/affordance）。另外：清理 48 个 vestigial `Agent` grant（最小权限 + drift 守卫），修掉 `/idea-creator` 的同家族 idea 预筛，并校正 `/auto-review-loop` 的 `OR`→`AND` 停止条件矛盾。**没有 ultracode 的用户也立刻受益** —— fan-out 退化成顺序执行，最终裁判席不变。

- **2026-05-26** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🤝 **本周社区 PR 汇 (5 个 merge)**。[`/wiki-enrich`](skills/wiki-enrich/SKILL.md) ([#247](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/247) by [@hungchun0201](https://github.com/hungchun0201)) 补全 `ingest_paper` 留下的论文 TODO 占位 —— Karpathy LLM-wiki 原则，fetch 链 alphaxiv→deepxiv→arXiv。[Mirror drift checker + CI](tools/check_skills_inventory.py) ([#241](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/241) by [@VeraPyuyi](https://github.com/VeraPyuyi)) 防 main↔mirror 漂移。`/research-pipeline` Stage 2/3 统一到 `/experiment-bridge` 委托 ([#243](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/243) by [@ZBigFish](https://github.com/ZBigFish)) —— 老的 inline 实现本来就是 bridge 的严格子集。Windows PowerShell 安装器对齐 + reparse-chain 内仓守卫 + `-FromOld` legacy 迁移 + Windows CI matrix ([#242](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/242) by [@VeraPyuyi](https://github.com/VeraPyuyi))。加 [`manual-review` MCP](mcp-servers/manual-review/README.md) ([#246](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/246) by [@ZBigFish](https://github.com/ZBigFish)) —— **第三个 reviewer backend `— reviewer: manual`**，零 API 成本跨模型 review（把 prompt 粘贴到任意非 Claude 模型：DeepSeek / Kimi / ChatGPT / Gemini / 本地 llama），跨模型不变量靠双语 UI 警告 + per-session token 认证 + manual MCP 未装时 fail-closed 保护。

- **2026-05-17** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🐙 **[GitHub Copilot CLI 适配](docs/COPILOT_CLI_ADAPTATION.md)** —— 原生 `SKILL.md` + MCP 支持，无需 skill mirror。安装器（`install_aris_copilot.sh`）+ smart-updater + 13 个 pytest。社区贡献 by [@EarendelH](https://github.com/EarendelH)（[#229](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/229)，关闭 [#214](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/214) / [#227](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/227) / [#203](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/203)）。

- **2026-05-17** — ![FIX](https://img.shields.io/badge/FIX-orange?style=flat-square) 🛠 **Tools-stability roadmap (Phase 1+2+3) 完整收尾**（closes [#176](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/176) / [#177](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/177) / [#178](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/178)）。社区反馈 `install_aris.sh` 跑完但 helper script 在用户项目里找不到。**Phase 1** —— 10 个 canonical helper 的所有 SKILL.md 调用方现在统一通过 [`integration-contract.md`](skills/shared-references/integration-contract.md) §2 定义的 3 层链 `.aris/tools/` → `tools/` → `$ARIS_REPO/tools/` 解析（§2 同时定义 5 种 failure policy A/B/C/D1/D2/E）。**Phase 2** —— 新增 [advisory CI lint](.github/workflows/lint-skills-helpers.yml) 在 PR 扫硬编码 `python3 tools/foo.py` 模式（仅警告，**永不卡 CI**）。**Phase 3** —— 3 个 single-owner helper（`figure-spec`、`paper-illustration-image2`、`experiment-queue`）迁入对应 SKILL 的 `scripts/` 目录，owner SKILL 用 Layer 0 `${CLAUDE_SKILL_DIR}/scripts/` 优先于 canonical chain，原 `tools/` 路径保留 `os.execv` Python 转发 shim。**⚠️ 现有用户**：无需操作，legacy `tools/` 入口现在是转发 shim。如果 2026-04-30 之后没跑过 `install_aris.sh`，幂等重跑一次即可全部对齐。
- **2026-05-14** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🩹 **`/paper-plan` + `/paper-write` 学会 `GAP_REPORT.md` + `<!-- DATA_NEEDED -->` 规则** ([#217](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/217))。当 `— style-ref:` 启用且用户项目下存在结构性 assets（`figures/`、`results/`、`NARRATIVE_REPORT.md` 等）时，`/paper-plan` emit **Gap Report**，把 exemplar 的 section 拓扑 + 密度（从 `style_profile.md`）对照用户实际 assets，暴露**没有证据填充**的结构性槽位（如"exemplar 有 3×4 ablation 表，你没有 ablation 数据"）。然后 `/paper-write` 在 missing 槽位写 `<!-- DATA_NEEDED: <Slot ID> — <描述> -->` HTML 注释**而不是编造内容**——PDF 不可见，`grep` 友好供人审 triage / `/experiment-bridge` 后续补实验。是对默认"no placeholders"规则的窄 carve-out，只在 GAP_REPORT 列出的 missing 槽位生效。原始想法来自 [@zhangpelf](https://github.com/zhangpelf)。

- **2026-05-14** — ![BREAKING](https://img.shields.io/badge/BREAKING-purple?style=flat-square) ⚙️ **默认 reviewer 模型：`gpt-5.4` → `gpt-5.5`**，覆盖 ~30 个 SKILL.md `REVIEWER_MODEL` 默认值。Codex MCP 自 2026-04-24 起 runtime 就是 `gpt-5.5`，本次让文档对齐 runtime。**⚠️ 行为变化**：(a) 之前 run 留下的 `.aris/traces/*` JSON **不可复现**——重跑用 5.5，边界 case 可能给出不同的 `WARN/FAIL` 判决（reviewer 质量提升，不是回归）。(b) ChatGPT Plus/Pro 月度配额在重度使用下消耗更快。**回退**：单次调用传 `— reviewer-model: gpt-5.4`，或在 skill 文件里固定 `REVIEWER_MODEL = gpt-5.4`。Oracle Pro tier（`— reviewer: oracle-pro`）走独立路由，不受影响。
- **2026-05-13** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔍 **[`tools/verify_papers.py`](tools/verify_papers.py) + Pre-Search Verification Protocol —— 给文献类 skill 加反幻觉过滤**。新 helper 走 3 层 fallback 验证（arXiv batch API 每次最多 40 个 ID → CrossRef DOI 查询 → Semantic Scholar 模糊标题匹配，默认 0.6 词重叠阈值），每篇 paper 输出 4 态（`verified` / `unverified` / `verify_pending` / `error`），顶层 verdict 对齐 `assurance-contract.md`（`PASS` / `WARN` / `BLOCKED` / `ERROR`）。**关键设计点**：网络瞬时失败（5xx、超时、429）单独标 `verify_pending` 且**不计入幻觉率**，避免网络挂被当成伪造引用。per-project 缓存路径 `<project>/.aris/cache/verify_papers.json`，30 天 TTL；缓存键优先级 `arxiv:{id_去版本号}` → `doi:{小写}` → `title:{sha1[:16]}`。[`shared-references/citation-discipline.md`](skills/shared-references/citation-discipline.md) 新增 `Pre-Search Verification Protocol` 小节，明确 search-time vs write-time 分工：本协议是 SEARCH（Step 1）和完整 VERIFY（Step 2）之间的**快速过滤器**；`/citation-audit` 和 `/paper-claim-audit` 仍是 submission 时的硬性 audit gate，**没被替代**。[`/research-lit`](skills/research-lit/SKILL.md) 新增 mandatory `Step 1.5: Verify Candidate Papers` 调 helper；[`/idea-creator`](skills/idea-creator/SKILL.md) 和 [`/novelty-check`](skills/novelty-check/SKILL.md) 各加 1 行 Key Rule 引用，覆盖 landscape 引用和 Closest Prior Work 表格。**保留而非静默删除**：未验证 paper 留在输出里打 `[UNVERIFIED]` 标记，让搜索质量问题对用户可见。可选：shell 里 `export ARIS_VERIFY_EMAIL=you@institution.edu` 进 CrossRef polite-pool 提高速率。最初由 [@YiwenZhu77](https://github.com/YiwenZhu77) 在 [#120](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/120) 提出——做了干净重写而非直接合 PR（PR 5 周老 + scope creep 到 figure-style）。
- **2026-05-06** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎤 **[`/paper-talk`](skills/paper-talk/SKILL.md) workflow + [`/slides-polish`](skills/slides-polish/SKILL.md) skill —— 端到端 conference talk pipeline**。`/paper-talk` 编排 paper → slide outline → Beamer + PPTX → per-page polish → assurance 审计 → final report（`/paper-writing`、`/paper-poster` 的姊妹 workflow）；组合 `/paper-slides`、`/slides-polish`，`assurance: conference-ready` 时再叠 `/paper-claim-audit` + `/citation-audit`。`/slides-polish` 是 post-generation 视觉打磨阶段：per-page Codex 对照 reference PDF 一页一页审 + 一套针对性 python-pptx / Beamer fix pattern（PPTX 字号 1.5-1.8× 缩放保证投影可读、字号 bump 后 text frame resize、banner 真用 tcolorbox 而不是 centered text、italic style 泄漏防御、em-dash 间距、中文 EA font hint 走 PingFang SC、anonymity placeholder 纪律）。Assurance 阶梯 `draft / polished（默认）/ conference-ready` 与 effort 轴正交——`effort: lite, assurance: conference-ready` 合法，意为「快流水线 + 每个审计必出 verdict 才能 final」。Phase 4 staging adapter 把 slide 文字 + 讲稿 + 完整 script 物化成合成 paper 目录（`.aris/paper-talk/audit-input/sections/*.tex` + symlink 真实 `.bib` / `results/` / `figures/`），让现有 `/paper-claim-audit` 和 `/citation-audit` 用它们 paper-shaped 合约审 talk 内容，输出 6 态 JSON verdict（见 `shared-references/assurance-contract.md`）。
- **2026-05-05** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔁 **`/resubmit-pipeline` —— Workflow 5：跨 venue 文本-only 重投流程** ([#208](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/208))。把已经打磨好的 paper 从一个 venue 移到另一个，硬约束：不跑新实验、不改 bib、不动 framework、不覆盖任何先前 submission 目录。5 阶段：物理隔离 → 5 层匿名检查 → 三审（proof / claim / citation `--soft-only`）→ `/auto-paper-improvement-loop --edit-whitelist` 微编辑 + 每轮 diff gate → `/kill-argument` 对抗 gate → 终编译 + `/overleaf-sync` 推送。同 PR 一起落地两个前置 skill 升级：**`/auto-paper-improvement-loop --edit-whitelist <path>`**（YAML schema，含 `allowed_paths` / `forbidden_paths` / `forbidden_operations`（如 `new_cite` / `new_theorem_env` / `numerical_claim`）/ `forbidden_deletions` / `requires_user_approval_for` / `max_edits_per_round`）和 **`/citation-audit --soft-only`**（bib 冻结时把 KEEP/FIX/REPLACE/REMOVE 翻译成文本改写建议；hallucinated 引用走 `drop_cite_in_body_only` 动作）。Master `RESUBMIT_REPORT.json` ledger 兼容 `shared-references/assurance-contract.md`；7 态 verdict 表（含 `USER_DECISION` runtime 状态）。
- **2026-05-05** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🗡 **`/kill-argument` —— 理论论文的对抗式 Attack-Adjudication review** ([#206](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/206))。两个新鲜 codex 5.5 + xhigh thread：Thread 1 写senior area chair 会写的最强 200 字 rejection memo；Thread 2 是独立 adjudicator（**不是** paper 的辩护人），读当前 paper 把每个攻击点分类为 `answered_by_current_text` / `partially_answered` / `still_unresolved`，带 file:line evidence。输出 `KILL_ARGUMENT.{md,json}`，detect-only。集成为 `/paper-writing` 的 **Phase 5.6**（在 claim-audit 和 citation-audit 之间），同时作为 `/auto-paper-improvement-loop` Step 5.5 的 canonical 调用——两处都不再内嵌 prompt 模板。`assurance: submission` 时对理论/scope-heavy paper 强制运行；非理论纯 empirical paper 自动 emit `NOT_APPLICABLE`。审计 JSON 兼容 `verify_paper_audits.sh`（完整 schema 见 `shared-references/assurance-contract.md`，6 态 verdict）。补 score-based review 漏掉的失败模式：每个 local 组件都对（数字对、引用对、定理证）但论文整体还是 oversell 了它真正证明的东西。
- **2026-05-04** — ![FIX](https://img.shields.io/badge/FIX-orange?style=flat-square) 🪲 **`/research-wiki` 和 8 个调用方 skill 改用 fallback chain 解析 helper** ([#204](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/204))。Bug：跑过 `bash tools/install_aris.sh` 后 helper 在 `.aris/tools/research_wiki.py`（symlink），但 skill 写死了 `tools/research_wiki.py`，调用时 silently 失败——整个 W1 跑完 `research-wiki/` 一直是空的。修复：3 层 chain（`.aris/tools/` → `tools/` → `$ARIS_REPO/tools/`），canonical pattern 在 [`shared-references/wiki-helper-resolution.md`](skills/shared-references/wiki-helper-resolution.md)。手动 `cp` 到 `<project>/tools/research_wiki.py` 的临时方案是 chain 第二层，照常 work。**⚠️ 已装 ARIS 用户**：重跑一次 `bash tools/install_aris.sh`——同时拿到 helper 的 Python 3.9 `ImportError` 修复（独立 bug）。
- **2026-05-03** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎨 **写作类 skill 的 opt-in `— style-ref: <source>` 参数** ([#202](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/202))。`/paper-{plan,write,writing,illustration,poster,slides}`、`/grant-proposal`、`/auto-paper-improvement-loop` 接受可选的 `— style-ref: <source>` 参数，**模仿参考论文的结构性风格**（section 顺序、theorem/figure 密度、句长节奏、引用风格），但**不复制其 prose / claim / 术语**。支持的 source：本地 `.tex` 目录/文件、本地 PDF、arXiv id（`2501.12345` 或 `arxiv:2501.12345`）、HTTP/HTTPS URL。Overleaf URL/ID 会被拒绝——先 `/overleaf-sync setup <id>` 把项目 clone 到本地再传路径。**默认关闭**；不传参数时所有 8 个 skill 行为完全不变。Reviewer / auditor 子 skill（`/proof-checker`、`/paper-claim-audit`、`/citation-audit`、improvement-loop reviewer）永远拿不到 style ref——跨模型 review 独立性保留。**⚠️ 已安装 ARIS 的用户**：helper 是新的 `tools/extract_paper_style.py`，通过 `.aris/tools` symlink 分发（`install_aris.sh` Phase 0，[#192](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/192) 引入）。**重跑一次 `bash tools/install_aris.sh`** 刷新 symlink 即可拿到 helper。手动 fallback：`cp <ARIS-repo>/tools/extract_paper_style.py <你的项目>/tools/`。两者都没做的话，writer skill 会 abort 并给清晰错误指向这条 News
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🪨 **社区项目推荐：[rosetta](https://github.com/SyntaxSmith/rosetta)** by [@SyntaxSmith](https://github.com/SyntaxSmith)。Node 程序化访问 **ChatGPT Pro / `gpt-5.5-pro` / DeepResearch**——Chrome CDP Fetch 拦截 + WebSocket second-leg streaming；自带 MCP server（Claude Code / Codex / Cline）。是 ARIS 用户 `— reviewer: oracle-pro` 调高 tier reviewer 的另一种实现路径——同样的能力目标（Pro 级 reviewer），不同机制。已收录到[社区 Skills & 扩展](#awesome-community-skills)。觉得有用 🌟 一下！
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 💎🧿 **Model & MCP routing 更新**。(a) [`/gemini-search`](skills/gemini-search/SKILL.md) 默认升级到 `gemini-3-pro-preview`（最强 Gemini 开箱默认）。⚠️ **需要操作**：需要 `gemini-cli` v0.40+（`gemini --version` 查版本；老版本 `npm i -g @google/gemini-cli` 升级）。Legacy override：`/gemini-search "topic" — model: gemini-2.5-pro`。其他 override：`gemini-3-flash-preview`（更快）、`auto-gemini-3`（按负载 route）。(b) [`/idea-discovery`](skills/idea-discovery/SKILL.md) Phase 1 现在默认包含 Gemini 文献检索 ([#199](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/199))——除非用户显式传 `— sources:`，否则给 `/research-lit` 自动注入 `— sources: all, gemini`；没装 `gemini-cli` 时优雅 skip。(c) Oracle MCP 上游 PR 队列（[`steipete/oracle/pulls`](https://github.com/steipete/oracle/pulls)）是用 `— reviewer: oracle-pro`（尤其 `o3-deep-research` / `gpt-5.5-pro`）时**开 issue 之前的第一排查点**——ARIS 不 vendor Oracle MCP，你跑的是 `@steipete/oracle` npm 发布版（[reviewer-routing.md](skills/shared-references/reviewer-routing.md)）
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛠️🔗 **Tools-infrastructure 迁移启动**。(a) [`install_aris.sh`](tools/install_aris.sh) 创建可选 `.aris/tools` 符号链接 ([#192](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/192), 关闭 [#174](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/174))——4 步 tools-stability 迁移（#174 → #176 → #177 → #178）的 Phase 0；幂等，**对老用户零影响**直到 rerun installer。(b) [`/experiment-queue`](skills/experiment-queue/SKILL.md) 编排路径修复 ([#193](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/193))——symlink 第一个真实用户；修了 7 个串联 bug，3 轮 Codex MCP `gpt-5.5` xhigh review 抓出 cascade。纯 prose + docstring；`queue_manager.py` Python 逻辑未动。Windows `install_aris.ps1` 平行更新作为 follow-up
- **2026-05-02** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔬 **三个 opt-in audit flag 通过 fast-path delegated-agent 工作流落地** ([#187](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/187), [#188](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/188), [#189](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/189))。[`/citation-audit --uncited`](skills/citation-audit/SKILL.md) 扫出 bib 里没人 `\cite{}` 的死条目（纯检测）。[`/proof-checker --deep-fix`](skills/proof-checker/SKILL.md) 给 Phase 1 reviewer prompt 加 repair-grade 修复计划（corrected_statement / patch plan / closure tests + Schur/quadratic-form 代数 sanity）。[`/proof-checker --restatement-check`](skills/proof-checker/SKILL.md) 加 Phase 3.6 跨位置定理飘移检测（6 类 drift signature）。**flag 不传时零行为变化**。同期合了两条文档 PR（[#190](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/190) thread-policy / [#191](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/191) auto-loop xref）。delegated-agent + maintainer-fixup 模式；Codex MCP `gpt-5.5` xhigh review 抓出 6+ 个 blocker
- **2026-05-01** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔍 **`/research-lit` 新增 Gemini + OpenAlex 文献源** ([#175](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/175)，社区贡献 [@stdAri](https://github.com/stdAri))。两个 opt-in 源：[`/gemini-search`](skills/gemini-search/SKILL.md)（AI 驱动的广覆盖检索，走 [`jamubc/gemini-mcp-tool`](https://github.com/jamubc/gemini-mcp-tool) MCP）+ [`/openalex`](skills/openalex/SKILL.md)（2.5 亿+ 条目开放引用图，免 API key）。`— sources: gemini` 或 `openalex` 显式触发；**默认 `all` 不含**（老用户零变化）。Maintainer fixup：修正 `@google/gemini-cli` npm 包名 + 加 `try/except ImportError` 让缺 `requests` 时 OpenAlex silent skip
- **2026-04-20** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🩹 **项目级安装重构：扁平布局 + manifest 追踪** — 修一个真 bug：老的嵌套安装（`.claude/skills/aris/`）让 Claude Code 的 slash command 自动补全发现不了 skill（CC 只扫一层目录）。在此日期之前用过 `install_aris.sh` 的项目都中招但大多没意识到。新的 `install_aris.sh` 给每个 skill 单独创建 symlink 到 `.claude/skills/<name>`，写版本化 manifest 到 `.aris/installed-skills.txt`，**可重入**——再跑一次会自动 reconcile 上游的新增/删除。防御性设计：13 条安全规则（不写穿 symlinked 父目录、mutate 前精确 revalidate target、slug 正则、同目录 atomic rename、绝不覆盖真实文件、mkdir 锁跨平台、ADOPT 状态用于崩溃恢复、…）。`--force` 拆成细粒度 `--adopt-existing` / `--replace-link`。迁移路径：`--from-old` 走老 symlink；`--migrate-copy keep-user|prefer-upstream` 走老 copy。`smart_update.sh --target-subdir .claude/skills/aris` 已弃用并重定向到 `install_aris.sh`。同时修了 `cp -r` 的 stale-file bug（现在用 `rm -rf && cp -r`，上游删的文件不再残留）
- **2026-04-19** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔗 **[`/overleaf-sync`](skills/overleaf-sync/SKILL.md)** — 本地 ARIS 论文目录与 Overleaf 项目的双向桥接，基于官方 **Overleaf Git Bridge**（Premium）。让合作者继续在 Overleaf 网页端编辑，本地同时跑 ARIS 审计/改写流水线（`/paper-claim-audit`、`/citation-audit`、`/auto-paper-improvement-loop`）。子命令：`setup`（一次性，由用户在终端完成，agent 全程不接触 token）/ `pull`（diff-protocol——自动识别半截草稿、typo、需要重新触发审计的数字/引用改动）/ `push`（写入共享 Overleaf 状态前必须用户确认）/ `status`（三方差异诊断）。**Token 永远不进入 agent 或任何文件**——只在用户终端里输入一次，存进 macOS Keychain，之后 agent 所有操作都免认证
- **2026-04-19** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📚 **[`/citation-audit`](skills/citation-audit/SKILL.md)** — 证据-到-claim 审计栈的第四层也是最后一层（`experiment-audit` → `result-to-claim` → `paper-claim-audit` → `citation-audit`）。新鲜跨家族 reviewer（gpt-5.4 通过 Codex MCP）配合 web/DBLP/arXiv 实时查找，对每个 `\cite{...}` 沿三条独立轴进行验证：**存在性**（论文是否真在所声称的 arXiv ID/DOI/会议）、**元数据正确性**（作者/年份/会议/标题与权威源一致）、**上下文恰当性**（被引论文是否真正支持引用处的 claim——这是最具诊断价值的检查）。每条 entry 给出 KEEP / FIX / REPLACE / REMOVE 判决。已**自动集成到 Workflow 3 Phase 5.8** 作为投稿前的参考文献门控。实证动机：在一次真实投稿 run 中，多篇真实论文被引用在它们实际不支持的语境中，至少一条 entry 的 `author` 字段是 `"Anonymous"`——这些都是仅做元数据检查会漏掉的问题
- **2026-04-17** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔀 **`/experiment-queue` 集成到 Workflow 1.5 + research-pipeline** — `experiment-bridge` Phase 4 Deploy 阶段按 milestone 任务数自动路由：≤5 jobs → `/run-experiment`，≥10 jobs 或 phase 依赖 → `/experiment-queue`（自带 OOM 重试 / stale screen 清理 / wave 切换门控 / 崩溃安全状态）。新增 `--- batch: queue` 全局强制选项。`EXPERIMENT_PLAN.md` 里的大型多种子 sweep（如 36 格 `N × seed × n_train` grid）现在自动用队列调度，无需手动调用
- **2026-04-17** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔗 **[项目级 symlink 安装](tools/install_aris.sh)**（解决 [#118](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/118)）— 新推荐默认安装方式。`bash tools/install_aris.sh` 自动检测平台（Claude Code / Codex CLI），创建 `.claude/skills/aris` 或 `.agents/skills/aris` symlink 指向 ARIS 仓库，在 `CLAUDE.md` / `AGENTS.md` 添加 `<!-- ARIS:BEGIN -->` 管理块告知 agent 仅用项目本地 skill，并在 `.aris/skill-source.txt` 记录安装元数据。**解决 skill 命名冲突问题**——当 ARIS 与 Superpowers / OpenHands 等社区 skill 包共用全局目录时，agent 会错误调用其他包的 skill 打断 ARIS 工作流。Windows 用户用 `install_aris.ps1`（基于 junction）。同时 `smart_update.sh` 新增 `--target-subdir` 参数支持 Codex `.agents/skills/aris` 项目级 copy 安装；symlink 安装会被拒绝并提示用 `git pull` 更新。全局安装继续支持给 power user
- **2026-04-16** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎨 **[`/figure-spec`](skills/figure-spec/SKILL.md)** — 确定性 JSON→SVG 渲染器正式包装为一级 skill。论文架构图/工作流/流水线/审计级联图的首选默认方案。形状感知边裁剪（矩形/圆/椭圆/菱形）、自环、弯曲边、多行标签含 CJK 宽度估算。矢量输出可编辑、可复现（相同 spec → 相同 SVG）、无外部 API。**Workflow 3 Phase 2b 恢复**：`illustration: figurespec`（新默认）/ `gemini` / `mermaid` / `false`——四档作图引擎互补并存
- **2026-04-16** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) ⚙️ **[`/experiment-queue`](skills/experiment-queue/SKILL.md)** — 面向多 seed 多配置 ML 实验的 SSH 任务队列。从真实 36 格 NeurIPS sweep 的痛点反推设计：OOM 感知重试（延迟退避）、stale screen 清理、wave 切换竞争防护、teacher→student 阶段依赖、崩溃安全的调度器（从 JSON 状态恢复）。声明式 grid 自动展开（如 `N × seed × n_train → 36 jobs`）。`conda_hook` + `gpu_free_threshold_mib` 可配置以适应非标准环境。≥10 jobs 时使用；`/run-experiment` 继续服务单点实验
- **2026-04-15** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛡️ **论文写作流水线加固** — 基于真实 NeurIPS run 失败分析的 10 个 patch。`REVIEWER_BIAS_GUARD=true`：每轮 review 用全新 thread（codex-reply 导致分数从真实 3/10 膨胀到虚假 8/10）。Reviewer Independence Protocol：禁止向 reviewer 传递修复摘要。Step 4.5 定理重述回归测试：捕捉修复轮次中的定理漂移。Step 5.5 Kill Argument Exercise：理论论文最终轮对抗攻防。位置感知 overfull 阻断。`/paper-write` 新增 Theory Paper Consistency Pass。Bib Hygiene 强制 DBLP/CrossRef 验证。Phase 5.5 Mandatory Final Claim Audit 作为投稿门控。**Review Tracing Protocol**：完整 prompt/response 对保存到 `.aris/traces/`，支持 reviewer-independence 审计（[`review-tracing.md`](skills/shared-references/review-tracing.md)，[`save_trace.sh`](tools/save_trace.sh)）。灵感来自社区贡献 @李傲龍
- **2026-04-15** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎨 **[FigureSpec 渲染器 v2](tools/figure_renderer.py)** — 确定性 JSON→SVG 论文作图。形状感知边裁剪（矩形/圆/椭圆/菱形）、自环、弯曲边、多行标签含 CJK 宽度估算、综合输入验证。经 5 轮 Codex review（3/10→7/10）。ARIS 技术报告中的所有架构图和工作流图均由此生成。`/paper-illustration` 新增 `--- mode: vector` 模式
- **2026-04-14** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📋 **[`/paper-claim-audit`](skills/paper-claim-audit/SKILL.md)** — 零上下文论文-证据验证。全新 reviewer（无任何先验上下文）逐一比对论文中的每个数字与原始结果文件。捕捉四舍五入膨胀、最优种子挑选、配置不匹配、增量误差、范围过度声明。自动集成到工作流 3（Phase 4.7）。完成三层审计链：`/experiment-audit`（代码）→ `/result-to-claim`（科学）→ `/paper-claim-audit`（报告）。👁️ **Visual PDF review** 同步加入 improvement loop——reviewer 现在看编译后 PDF，不只是 LaTeX 源码
- **2026-04-13** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🧿 **[GPT-5.4 Pro via Oracle](skills/shared-references/reviewer-routing.md)** — `— reviewer: oracle-pro` 调用最强推理模型。API 模式（快）或浏览器模式（免费）。支持 `/research-review`、`/auto-review-loop`、`/experiment-audit`、`/proof-checker`、`/rebuttal`、`/idea-creator`、`/research-lit`。默认仍为 Codex xhigh。未安装 = 零影响。[设置 →](#-optional-gpt-54-pro-via-oracle)
- **2026-04-13** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔬 **[`/proof-checker`](skills/proof-checker/SKILL.md)** — 严格数学证明验证。20 类问题分类、双轴严重度、侧条件检查表（DCT/MCT/Fubini/IFT/...）、反例红队、证明义务台账。自动集成到工作流 3。
- **2026-04-10** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) ⚡ **[Effort Levels](skills/shared-references/effort-contract.md)** — `— effort: lite | balanced | max | beast`。控制工作强度。Codex reasoning 永远 `xhigh`。`beast` = 全部拉满。默认 `balanced` = 零变化。
- **2026-04-10** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔎 **[DeepXiv 集成](skills/deepxiv/SKILL.md)** — 渐进式文献检索。`— sources: deepxiv`。`pip install deepxiv-sdk`。社区贡献 by [@DreamEnding](https://github.com/DreamEnding)
- **2026-04-10** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🛡️ **[`/experiment-audit`](skills/experiment-audit/SKILL.md)** — 跨模型实验诚实度验证。GPT-5.4 直接读你的评估脚本和结果，检查伪造 GT、分数归一化作弊、幽灵结果、范围夸大（[#131](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/131), [#57](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/57)）。仅警告不阻断。`/result-to-claim` 自动读取审计结果。新增 [experiment-integrity.md](skills/shared-references/experiment-integrity.md) 共享规则。**执行者不得审判自己的诚实度。**
- **2026-04-10** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🧠 **[`tools/smart_update.sh`](tools/smart_update.sh)** — 智能技能更新器。对比本地 vs 上游，检测个人定制（服务器路径、API key 等），只更新安全的 skill。`bash tools/smart_update.sh --apply`
- **2026-04-10** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🏆 **社区论文：[UAV-CC](community_papers/UAV-CC.pdf)** — 首篇带完整 PDF 存档的社区论文。无人机变化描述基准，投稿 IEEE TGRS，作者 [@wxx827](https://github.com/wxx827)。配置：Claude Opus 4.6 + Codex 5.4 xhigh + Cursor。论文存档于 `community_papers/`
- **2026-04-08** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 📚 **[`/research-wiki`](skills/research-wiki/SKILL.md)** — 持久化研究知识库，灵感来自 [Karpathy 的 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)。跨研究全生命周期积累论文、想法、实验、claim 及其 typed 关系。Wiki hooks 集成到 `/research-lit`（论文入库）、`/idea-creator`（读 wiki + 写回 idea）、`/result-to-claim`（更新 claim 状态 + 触发重新构思）。失败的 idea 成为防重复记忆。**ARIS 现在能从错误中学习。**
- **2026-04-05** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🧬 **[`/meta-optimize`](skills/meta-optimize/SKILL.md)** — ARIS 外循环 harness 优化。通过 [Claude Code hooks](templates/claude-hooks/meta_logging.json) 被动记录技能调用、工具执行、失败和参数覆盖。运行 `/meta-optimize` 分析使用数据，提出 SKILL.md 改进方案——经 reviewer 审核、用户批准。灵感来自 [Meta-Harness](https://arxiv.org/abs/2603.28052)（Lee et al., 2026）。**ARIS 现在可以优化自己。**
- **2026-04-04** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🔧 **Codex Plugin 深度集成** — 实验失败（工作流 1.5）或 LaTeX 编译出错（工作流 3）时，自动调用 `/codex:rescue` 让 GPT 独立诊断 bug，再由 Claude 重试。两个 AI 一起 debug。`codex exec` 驱动 nightmare review，`/codex:rescue` 驱动 auto-debug，各司其职
- **2026-04-03** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) ☁️ **[Modal 无服务器 GPU](skills/serverless-modal/SKILL.md)** — 没有 GPU？CLAUDE.md 写 `gpu: modal`，一条命令跑实验，无需 SSH/Docker，跑完自动停止。**$30/月免费额度**，`pip install modal && modal setup` 即可体验 ARIS 全流程。社区贡献 by [@zeyuzhangzyz](https://github.com/zeyuzhangzyz)
- **2026-04-03** — ![NEW](https://img.shields.io/badge/NEW-red?style=flat-square) 🎮 **审稿难度等级** — `medium`（默认，不变）、`hard`（reviewer memory + 辩论协议）、`nightmare`（GPT 通过 `codex exec` 直接读代码仓库，Claude 无法隐藏任何东西）。投顶会前用 `— difficulty: nightmare` 做极限压测
- **2026-03-27** — 📄 **IEEE 模板**（9 个 venue 族）+ 🔎 **Semantic Scholar**。By [@ypd666](https://github.com/ypd666)
- **2026-03-26** — 📄 **文档输入** — `RESEARCH_BRIEF.md` 自动检测
- **2026-03-24** — 📝 **[工作流 4：`/rebuttal`](skills/rebuttal/SKILL.md)** — 7 阶段，3 道安全门
- **2026-03-23** — 🔧 `/training-check`、`/result-to-claim`、`/ablation-planner` 集成。📦 `compact` 模式。By [@JingxuanKang](https://github.com/JingxuanKang) & [@couragec](https://github.com/couragec)

- **2026-03-22** — 📋 **[模板](templates/)** + 📄 **7 个会议模板** + 🛡️ **反幻觉修复** + 🔗 **`base repo`**
- **2026-03-22** — 🔍 **[Codex + Gemini 审稿](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md)** — Codex 执行，Gemini 审稿
- **2026-03-20** — 🚀 **[Antigravity 适配](docs/ANTIGRAVITY_ADAPTATION_CN.md)**。社区贡献 by [@PeppaPigw](https://github.com/PeppaPigw)
- **2026-03-20** — 🖥️ **[Trae 适配](docs/TRAE_ARIS_RUNBOOK_CN.md)**。社区贡献 by [@Prometheus-cotigo](https://github.com/Prometheus-cotigo)。🔢 **[`formula-derivation`](skills/formula-derivation/SKILL.md)**。社区贡献 by [@Falling-Flower](https://github.com/Falling-Flower)
- **2026-03-19** — 🖼️ **[`paper-poster`](skills/paper-poster/SKILL.md)**。社区贡献 by [@dengzhe-hou](https://github.com/dengzhe-hou)
- **2026-03-19** — 🔗 **工作流 1.5 升级** — GPT-5.4 代码审查 + W&B 修正
- **2026-03-18** — 🎤 `paper-slides` + 🔁 Codex+Claude bridge + 🖱️ Cursor 适配 + 🤖 Codex CLI skills + 📝 `grant-proposal` + 🎨 `paper-illustration` + 📊 CitationClaw
- **2026-03-17** — 🔧 Git 代码同步 + 🆓 ModelScope 指南 + 参数透传
<details>
<summary>更早的更新（2026-03-12 — 2026-03-16）</summary>

- **2026-03-16** — 🔬 **[`research-refine`](skills/research-refine/SKILL.md)** + [`experiment-plan`](skills/experiment-plan/SKILL.md) — 模糊 idea → 问题锚点明确的方案 + claim-driven 实验路线图。社区贡献 by [@zjYao36](https://github.com/zjYao36)
- **2026-03-16** — 🇨🇳 **[阿里百炼 Coding Plan 接入指南](docs/ALI_CODING_PLAN_GUIDE.md)** — 一个 API Key、4 款模型。社区贡献 by [@tianhao909](https://github.com/tianhao909)
- **2026-03-15** — 🔀 **自带模型！** [任意 OpenAI 兼容 API](#alternative-model-combinations) 均可作为审查器
- **2026-03-15** — 🐾 **[OpenClaw 适配指南](docs/OPENCLAW_ADAPTATION.md)** — 在 OpenClaw 中使用 ARIS 工作流
- **2026-03-15** — 📐 **[`proof-writer`](skills/proof-writer/SKILL.md)** + 📚 **反幻觉引用**（DBLP/CrossRef）
- **2026-03-14** — 📱 [飞书集成](docs/integrations/FEISHU_CN.md)：三种模式（关闭/推送/交互）
- **2026-03-13** — 🛑 Human-in-the-loop：`AUTO_PROCEED` 检查点
- **2026-03-12** — 🔗 Zotero + Obsidian + arXiv/Scholar 多源文献检索
- **2026-03-12** — 🚀 三大工作流端到端贯通 + 📝 论文写作流水线（4/10 → 8.5/10）

</details>
</details>

<a id="quick-start"></a>
<a id="-quick-start"></a>

## 3. 🚀 快速开始

```bash
# 1. 安装 skills —— 项目级 symlink（推荐）
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
bash Auto-claude-code-research-in-sleep/tools/install_aris.sh ~/your-project   # 把 ARIS skill symlink 进 <project>/.claude/skills/
# （想全局安装？cp -r Auto-claude-code-research-in-sleep/skills/* ~/.claude/skills/）

# 可选：Codex mirror 项目级受管安装
bash Auto-claude-code-research-in-sleep/tools/install_aris_codex.sh ~/your-codex-project

# Codex 受管项目更新
cd Auto-claude-code-research-in-sleep && git pull
bash Auto-claude-code-research-in-sleep/tools/install_aris_codex.sh ~/your-codex-project --reconcile

# 仅用于 Codex copy install（不要用于 install_aris_codex.sh 管理的项目）
bash Auto-claude-code-research-in-sleep/tools/smart_update_codex.sh --local ~/.codex/skills
bash Auto-claude-code-research-in-sleep/tools/smart_update_codex.sh --local ~/.codex/skills --apply

# 2. 配置 Codex MCP（review 类 skill 需要）
npm install -g @openai/codex
codex setup                    # 提示选模型时选 gpt-5.5
claude mcp add codex -s user -- codex mcp-server

# 3. 在 Claude Code 中使用
claude
> /idea-discovery "你的研究方向"              # 工作流 1 — 方向要具体！不要 "NLP"，要 "离散扩散语言模型的 factorized gap"
> /experiment-bridge                         # 工作流 1.5 — 有计划了？实现 + 部署 + 收结果
> /auto-review-loop "你的论文主题或范围"         # 工作流 2：审稿 → 修复 → 再审，一夜完成
> /paper-writing "NARRATIVE_REPORT.md"       # 工作流 3：研究叙事 → 精修 PDF
> /rebuttal "paper/ + reviews" — venue: ICML  # 工作流 4：解析 review → 起草 rebuttal → follow-up
> /resubmit-pipeline "paper/" — venue: NeurIPS  # 工作流 5：把已打磨论文移植到新 venue（纯文本，不跑新实验）
> /paper-talk "paper/" — venue: ICLR            # 工作流 6：论文 → Beamer + PPTX talk slides + 讲稿 + 评审审计
> /research-pipeline "你的研究方向"            # 全流程：工作流 1 → 1.5 → 2 → 3 端到端
> /research-wiki init                          # 📚 启用持久化研究记忆（一次性）
> /meta-optimize                               # 元优化：分析使用记录 → 提出技能改进方案
```

<details>
<summary><b>📚 Research Wiki（可选）</b> —— 一行 init 启用跨 session 持久记忆；完整说明见 <a href="#-research-wiki--persistent-research-memory">§ Research Wiki</a></summary>

给 ARIS 装上持久记忆。论文、idea、失败实验——什么都不忘：

```bash
# 在 Claude Code 中：
> /research-wiki init                         # 创建 research-wiki/ 目录
# 搞定。此后 /research-lit 自动入库论文，/idea-creator 读 wiki 再想 idea
# （并把 idea 写回），/result-to-claim 更新 claim 状态。
# 失败的 idea 成为未来构思的防重复记忆。
```

</details>

<details>
<summary><b>🧬 元优化（可选）</b> —— 被动使用日志 + /meta-optimize 出数据驱动的 SKILL.md 改进建议；完整说明见 <a href="#工作流-mmeta-optimize-aris-优化自己">§ 工作流 M</a></summary>

在**普通终端**（不是 Claude Code 会话内）运行以下命令启用被动日志：

```bash
# 在项目目录下一次性设置
mkdir -p .claude .aris/meta tools/meta_opt
cp Auto-claude-code-research-in-sleep/templates/claude-hooks/meta_logging.json .claude/settings.json
cp Auto-claude-code-research-in-sleep/tools/meta_opt/*.sh tools/meta_opt/
chmod +x tools/meta_opt/*.sh
# 然后启动 Claude Code — hooks 立即生效
claude
```

事件同时记录到**项目级**（`.aris/meta/events.jsonl`）和**全局**（`~/.aris/meta/events.jsonl`）日志。累积 5 次以上工作流运行后，运行 `/meta-optimize` 查看改进建议。使用 `/meta-optimize --global` 分析跨项目的使用趋势。

</details>

<details>
<summary><b>📝 模板 + 🔎 DeepXiv + 🔎 Exa + 🗑️ 卸载</b> —— 输入模板、两个额外文献源、以及卸载命令</summary>

**📝 模板可用！** 见 [`templates/`](templates/) 目录——每个工作流都有现成输入模板：[研究简报](templates/RESEARCH_BRIEF_TEMPLATE.md)（工作流 1）、[实验计划](templates/EXPERIMENT_PLAN_TEMPLATE.md)（工作流 1.5）、[研究叙事](templates/NARRATIVE_REPORT_TEMPLATE.md)（工作流 3）、[论文大纲](templates/PAPER_PLAN_TEMPLATE.md)（工作流 3）。

**🔎 可选：DeepXiv 渐进式论文检索**
```bash
pip install deepxiv-sdk
```
安装后可直接使用 [`/deepxiv`](skills/deepxiv/SKILL.md)，或在 `/research-lit` 中通过 `— sources: deepxiv` / `— sources: all, deepxiv` 显式启用。

**🔎 可选：Exa AI 智能网页搜索**
```bash
pip install exa-py
export EXA_API_KEY=your-key-here
```
安装后可直接使用 [`/exa-search`](skills/exa-search/SKILL.md)，或在 `/research-lit` 中通过 `— sources: exa` / `— sources: all, exa` 显式启用。覆盖博客、文档、新闻和研究论文，并内置内容提取。

**🗑️ 卸载：** 仅删除 ARIS skills，不影响你自己的 skills：
```bash
cd Auto-claude-code-research-in-sleep && ls skills/ | xargs -I{} rm -rf ~/.claude/skills/{}
```

</details>

<details>
<summary><b>展开全部 15 个内联参数和 8 个 override 示例</b> —— AUTO_PROCEED / sources / arxiv download / DBLP_BIBTEX / code review / wandb / illustration / venue / base repo / compact / ref paper / effort / reviewer / difficulty（完整 per-skill 默认值见 <a href="#customization">§ 自定义</a>）</summary>

所有流水线行为均可通过内联参数配置——在命令后追加 `— key: value`：

| 参数 | 默认 | 说明 |
|------|------|------|
| `AUTO_PROCEED` | `true` | 在 idea 选择关卡自动继续。设为 `false` 可在花 GPU 前手动挑选 idea |
| `human checkpoint` | `false` | 每轮 review 后暂停，让你查看分数、给出修改意见、跳过特定修复或提前终止 |
| `sources` | `all` | 搜索哪些文献源：`zotero`、`obsidian`、`local`、`web`、`semantic-scholar`、`deepxiv`、`exa`、`all`。`semantic-scholar`、`deepxiv` 和 `exa` 都需显式指定 |
| `arxiv download` | `false` | 文献调研时下载最相关的 arXiv PDF。为 `false` 时仅获取元数据（标题、摘要、作者） |
| `DBLP_BIBTEX` | `true` | 从 [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) 获取真实 BibTeX，替代 LLM 生成。杜绝幻觉引用。零安装 |
| `code review` | `true` | GPT-5.5 xhigh 部署前审查实验代码。设 `false` 跳过 |
| `wandb` | `false` | 自动给实验脚本加 W&B 日志。设 `true` + 在 CLAUDE.md 配 `wandb_project`。`/monitor-experiment` 从 W&B 拉训练曲线 |
| `illustration` | `gemini` | 工作流 3 AI 作图：`gemini`（默认，需 `GEMINI_API_KEY`，[获取](https://aistudio.google.com/apikey)）、`mermaid`（免费）、`false`（跳过） |
| `venue` | `ICLR` | 目标会议：`ICLR`、`NeurIPS`、`ICML`、`CVPR`、`ACL`、`AAAI`、`ACM`、`IEEE_JOURNAL`、`IEEE_CONF`。决定 LaTeX 样式和页数限制 |
| `base repo` | `false` | GitHub 仓库 URL，克隆作为实验基础代码（如 `— base repo: https://github.com/org/project`）。没有代码？基于开源项目开发 |
| `compact` | `false` | 生成精简摘要文件（`IDEA_CANDIDATES.md`、`findings.md`、`EXPERIMENT_LOG.md`），适合短 context 模型和 session 恢复 |
| `ref paper` | `false` | 参考论文（PDF 路径或 arXiv URL）。先总结论文，再基于它找 idea。配合 `base repo` 实现"论文+代码"工作流 |
| `effort` | `balanced` | 工作强度：`lite`(0.4x)、`balanced`(默认)、`max`(2.5x)、`beast`(5-8x)。Codex reasoning 永远 `xhigh` |
| `reviewer` | `codex` | 审稿后端：`codex`（GPT-5.5 xhigh，默认）、`oracle-pro`（GPT-5.5 Pro via [Oracle](https://github.com/steipete/oracle)） |
| `difficulty` | `medium` | 审稿对抗强度：`medium`（默认）、`hard`（+ memory + 辩论）、`nightmare`（+ GPT 通过 `codex exec` 直读仓库） |

```
/research-pipeline "你的课题" — AUTO_PROCEED: false                          # 在 idea 选择关卡暂停
/research-pipeline "你的课题" — human checkpoint: true                       # 每轮 review 后暂停，可给修改意见
/research-pipeline "你的课题" — sources: zotero, web                         # 只搜 Zotero + 网络（跳过本地 PDF）
/research-pipeline "你的课题" — sources: all, deepxiv                        # 默认源 + DeepXiv 渐进式检索
/research-pipeline "你的课题" — sources: all, exa                            # 默认源 + Exa AI 智能网页搜索
/research-pipeline "你的课题" — arxiv download: true                         # 文献调研时下载最相关的 arXiv PDF
/research-pipeline "你的课题" — difficulty: nightmare                        # 投顶会前极限压测
/research-pipeline "你的课题" — AUTO_PROCEED: false, human checkpoint: true  # 组合使用
```

</details>

<details>
<summary><b>Codex MCP 配置 + 替代 reviewer 路由</b> —— 在 <code>~/.codex/config.toml</code> 钉模型；Codex+Claude 审稿、Codex+Gemini 审稿、Codex mirror 安装链的入口指向</summary>

**重要：** Codex MCP 使用的模型取决于 `~/.codex/config.toml`，而非 skill 文件中的设置。请确认其中写的是 `model = "gpt-5.5"`（推荐）。其他可用模型：`gpt-5.3-codex`、`gpt-5.2-codex`、`o3`。运行 `codex setup` 或直接编辑该文件。

**想让 Codex 执行、Claude Code 审稿？** 见 [`docs/CODEX_CLAUDE_REVIEW_GUIDE_CN.md`](docs/CODEX_CLAUDE_REVIEW_GUIDE_CN.md)。这条路径会先安装基础 `skills/skills-codex/*`，再叠加 `skills/skills-codex-claude-review/*`，并通过本地 `claude-review` MCP bridge 转发 review-heavy skill 的审稿请求。

**想让 Codex 执行、Gemini 在本地做审稿？** 见 [`docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md`](docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md) 和[英文版](docs/CODEX_GEMINI_REVIEW_GUIDE.md)。这条路径会先安装基础 `skills/skills-codex/*`，再叠加 `skills/skills-codex-gemini-review/*`，并通过本地 `gemini-review` MCP bridge 转发 reviewer-aware 预定义 skills 的审稿请求，默认 direct Gemini API。

**想走 Codex mirror 安装链？** 项目级受管安装用 `tools/install_aris_codex.sh`，copy 安装更新用 `tools/smart_update_codex.sh`。Claude 脚本仍然是 Claude 主线入口。

</details>

详见[完整安装指南](#setup)和[替代模型组合](#alternative-model-combinations)（无需 Claude/OpenAI API）。

<a id="features"></a>

## 4. ✨ 功能亮点

ARIS 用 **79 个可组合 skill** 覆盖科研全生命周期——文献查新 → idea 发现 → GPU 实验 → 自动 review 循环 → 论文写作 → peer review——配合**跨模型对抗审**（Claude 执行 · GPT-5.5 xhigh 审 · 可选 **GPT-5.5 Pro** via Oracle）、DBLP/CrossRef 反幻觉引用、持久化 **Research Wiki**、灵活模型后端、human-in-the-loop 检查点，以及可选的飞书 / Zotero / Obsidian / GPU 集成。

🔥 *而且这套"广度 / 审 / 记忆"三角能适配任何 agent 的 **ultracode 式深度模式**：广度 pass 适配运行时暴露的能力（Claude Code 原生 ultracode / workflows + Opus 4.8、Codex `spawn_agent`，或纯顺序执行），并按层级干净降级（fan-out → agent spawn → 顺序）。三件事分得很清楚：**广度 · 跨模型对抗审 → 准确性 · research wiki → 记忆性**。无论循环由谁推进，最后都回到同一套跨模型对抗审 + research wiki：**能推进，不能定案**。*

<details>
<summary><b>完整功能清单</b></summary>

- 📊 **79 个可组合 skill** — 自由混搭，或串联为完整流水线（`/idea-discovery`、`/auto-review-loop`、`/paper-writing`、`/research-pipeline`）。[完整目录 →](docs/SKILLS_CATALOG.md)
- 🔍 **文献 & 查新** — 多源论文搜索（**[Zotero](docs/integrations/ZOTERO_CN.md)** + **[Obsidian](docs/integrations/OBSIDIAN_CN.md)** + **本地 PDF** + arXiv/Scholar）+ 跨模型查新验证
- 💡 **Idea 发现** — 文献调研 → 头脑风暴 8-12 个 idea → 查新 → GPU pilot 实验 → 排名报告
- 🔄 **自动 review 循环** — 4 轮自主审稿，一夜从 5/10 提升到 7.5/10，自动跑 20+ 组 GPU 实验
- 📝 **论文写作** — 研究叙事 → 大纲 → 图表 → LaTeX → PDF → 自动审稿（4/10 → 8.5/10），一条命令。通过 [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) 反幻觉引用
- 🤖 **跨模型协作** — Claude Code 执行，GPT-5.5 xhigh 审稿。对抗式而非自我博弈。可选：`— reviewer: oracle-pro` → **GPT-5.5 Pro** via [Oracle](https://github.com/steipete/oracle)
- 📝 **Peer Review** — 以审稿人视角审阅他人论文，结构化打分 + meta-review
- 🖥️ **审稿驱动实验** — GPT-5.5 说"跑个消融"，Claude 自动写脚本、rsync 到 GPU、`screen` 启动、收结果、写回论文。`CLAUDE.md` 里配服务器（[配置](#gpu-server-setup)），或用 `gpu: vast` 从 [Vast.ai](https://vast.ai) 按需租
- 🔀 **灵活模型** — 默认 Claude × GPT-5.5，也支持 [GLM、MiniMax、Kimi、LongCat、DeepSeek 等](#alternative-model-combinations)——无需 Claude 或 OpenAI API
- 🛑 **Human-in-the-loop** — 关键决策点可配置检查点。`AUTO_PROCEED=true` 全自动，`false` 逐步审批
- 📱 **[飞书通知](docs/integrations/FEISHU_CN.md)** — 三种模式：**关闭（默认，推荐）**、仅推送（webhook → 手机）、双向交互（飞书里审批/回复）。未配置时零影响

  <details>
  <summary>预览：推送卡片（群聊）&amp; 交互对话（私聊）</summary>

  **仅推送** — 群聊彩色卡片（实验完成、checkpoint、报错、流水线结束）：

  <img src="assets/feishu_push.png" width="700" />

  **双向交互** — 与 Claude Code 私聊（审批/拒绝、自定义指令）：

  <img src="assets/feishu_interactive.jpg" width="700" />

  </details>

- 📚 **[Research Wiki](#-research-wiki--persistent-research-memory)** — 持久化知识库，跨论文/idea/实验/claim 累积记忆。失败的 idea 成为防重复记忆——ARIS 每跑一次都更聪明。灵感来自 [Karpathy 的 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- 🧩 **可扩展** — 欢迎贡献领域专用 skill！添加一个 `SKILL.md` 即可提 PR。参见[社区 skills](#awesome-community-skills)，如 [`dse-loop`](skills/dse-loop/SKILL.md)（体系结构/EDA）

</details>

<a id="skills-catalog"></a>
<a id="-skills-catalog"></a>

ARIS 现有 **79+ 个 skill**，覆盖文献调研、idea 生成、实验、审计、论文写作、演讲、专利、meta 工具等——完整目录（每个 skill 含 role / category / 依赖）在 **[`docs/SKILLS_CATALOG.md`](docs/SKILLS_CATALOG.md)**，独立成文以保持 README 可扫读。

<details>
<summary><b>常用入口</b> —— 场景 → 入口 skill</summary>

| 场景 | 入口 skill |
|---|---|
| 端到端研究（idea → paper） | [`/research-pipeline`](skills/research-pipeline/SKILL.md) |
| Idea 发现 + 方案精炼 | [`/idea-discovery`](skills/idea-discovery/SKILL.md) |
| 按计划跑实验 | [`/experiment-bridge`](skills/experiment-bridge/SKILL.md) |
| 自动 review → 修 → 再 review | [`/auto-review-loop`](skills/auto-review-loop/SKILL.md) |
| 报告 → 打磨 PDF | [`/paper-writing`](skills/paper-writing/SKILL.md) |
| 回应审稿意见 | [`/rebuttal`](skills/rebuttal/SKILL.md) |
| 跨 venue 移植论文 | [`/resubmit-pipeline`](skills/resubmit-pipeline/SKILL.md) |
| 论文 → 会议演讲 | [`/paper-talk`](skills/paper-talk/SKILL.md) |
| 持久化研究记忆 | [`/research-wiki`](skills/research-wiki/SKILL.md) |
| 专利撰写（CN / US / EP） | [`/patent-pipeline`](skills/patent-pipeline/SKILL.md) |
| ARIS 自我优化 | [`/meta-optimize`](skills/meta-optimize/SKILL.md) |

</details>

→ **[按 category 浏览全部 79 个 skill →](docs/SKILLS_CATALOG.md)**

---

<a id="score-progression"></a>

## 5. 📈 真实运行效果

某 ML 研究项目上的 4 轮通宵自动循环 —— AI 审稿评分从 **5.0/10（borderline reject）爬到 7.5/10（审稿就绪）**，期间自主跑了 **20+ 个 GPU 实验**、重写叙事框架、杀掉经不住检验的声明，全程无人干预。

<details>
<summary>逐轮明细</summary>

| 轮次 | 分数 | 发生了什么 |
|------|------|-----------|
| 初始 | 5.0/10 | Borderline reject |
| 第 1 轮 | 6.5/10 | 补了标准指标，发现指标脱钩 |
| 第 2 轮 | 6.8/10 | 核心声明不可复现，转换叙事 |
| 第 3 轮 | 7.0/10 | 大规模 seed 研究推翻了主要改善声明 |
| 第 4 轮 | **7.5/10** ✅ | 诊断证据确立，**可以投稿** |

</details>

<a id="community-showcase"></a>

## 6. 🏆 社区实操 — 用 ARIS 完成的论文

ARIS 全流程完成并进入投稿/审稿阶段的真实项目。**所列分数是 AI 审稿信号（[CSPaper](https://cspaper.org/) / [Stanford Agentic Reviewer](https://paperreview.ai/)），不等于正式录用** —— 而且 ARIS 本就靠 AI-review 循环迭代，AI 分偏高是正常副产物、不是录用证据（真实人类审稿仍会带来 AI 没建模到的文献 / venue / 社区判断）。**你也用 ARIS 完成了论文？提 Issue / PR 来上榜！**

<details>
<summary>论文 + AI 审稿信号（3 篇）</summary>

| 论文 | AI 审稿信号 | 投稿状态 | 作者 | 备注 |
|------|:------------:|----------|------|------|
| **CS 论文投稿** | [CSPaper](https://cspaper.org/) **8/10** — AI 审稿建议："Top 50% of accepted papers, clear accept" | 已投 CS 会议，等待正式审稿反馈 | [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay) | ARIS 全流程：idea → 实验 → auto-review → 论文写作。该评价来自 CSPaper 模拟审稿，不是会议官方审稿意见。 |
| **AAAI 2026 论文投稿** | [Stanford Agentic Reviewer](https://paperreview.ai/) **7/10** — AI 审稿建议："Good paper, accept" | 已投 AAAI 2026 Main Technical，等待官方结果 | [@xinbo820-web](https://github.com/xinbo820-web) | 纯 **Codex CLI**（ARIS-Codex skills）。7/10 来自 Stanford Agentic Reviewer 的 AAAI-style 模拟审稿，不代表 AAAI 官方审稿/录用结果。 |
| [UAV-CC](community_papers/UAV-CC.pdf) | 审稿中 | 已投 IEEE TGRS | [@wxx827](https://github.com/wxx827) | 无人机变化描述基准。Claude Opus 4.6（执行）+ Codex GPT-5.5 xhigh（审阅）+ Cursor Opus 4.6（辅助）。[PDF →](community_papers/UAV-CC.pdf) |

</details>

<details><summary>审稿截图</summary>
<br>
<img src="assets/community_showcase_8_10.png" width="700" alt="8/10 — CS 论文" />
<img src="assets/community_showcase_7_10_codex.png" width="700" alt="7/10 — AAAI 2026，Codex CLI" />
</details>

<a id="awesome-community-skills"></a>

## 7. 🧩 Awesome 社区 Skills & 扩展

社区贡献的领域专用 skills 和外部项目。欢迎 PR——添加 `skills/your-skill/SKILL.md` 即可！

> 💡 **使用方法：** 社区 skill 不会自动接入核心工作流。使用时，让你的执行者（Claude Code / OpenClaw 等）先读一遍该 skill 的 `SKILL.md`，再根据下方描述接入对应的工作流阶段。

🎉 **社区 Skills（13 个）：** [research-refine](skills/research-refine/SKILL.md) · [experiment-plan](skills/experiment-plan/SKILL.md) · [research-refine-pipeline](skills/research-refine-pipeline/SKILL.md) · [grant-proposal](skills/grant-proposal/SKILL.md) · [paper-poster](skills/paper-poster/SKILL.md) · [paper-slides](skills/paper-slides/SKILL.md) · [mermaid-diagram](skills/mermaid-diagram/SKILL.md) · [proof-writer](skills/proof-writer/SKILL.md) · [comm-lit-review](skills/comm-lit-review/SKILL.md) · [dse-loop](skills/dse-loop/SKILL.md) · [idea-discovery-robot](skills/idea-discovery-robot/SKILL.md) · [paper-illustration](skills/paper-illustration/SKILL.md) · [skills-codex](skills/skills-codex/)

🌐 **外部项目 & 文档（12 个）：** [rosetta](https://github.com/SyntaxSmith/rosetta) · [open-source-hardening-skills](https://github.com/zeyuzhangzyz/open-source-hardening-skills) · [CitationClaw](https://github.com/VisionXLab/CitationClaw) · [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) · [paper-to-course](https://github.com/KaguraTart/paper-to-course) · [deep-research-skills](https://github.com/Weizhena/deep-research-skills) · [Antigravity 适配指南](docs/ANTIGRAVITY_ADAPTATION_CN.md) · [OpenClaw 适配指南](docs/OPENCLAW_ADAPTATION.md) · [Cursor 适配指南](docs/CURSOR_ADAPTATION.md) · [Trae 适配指南](docs/TRAE_ARIS_RUNBOOK_CN.md) · [posterly](https://github.com/Chenruishuo/posterly) · [Claude Fleet](https://github.com/tianyilt/claude-fleet)

> 🙌 感谢每一位贡献者！为了 README 的可读性，下方表格折叠展示——但每个 skill 和项目都同样珍贵。欢迎 PR！

<details>
<summary><b>🎉 社区 Skills（13 个）</b> — 点击展开</summary>

| 名称 | 领域 | 描述 | Codex MCP？ |
|------|------|------|-----------|
| 🔬 [`research-refine`](skills/research-refine/SKILL.md) | 通用 | 把模糊 idea 精炼成问题锚点明确、可实现的方法方案 | 是 |
| 🧪 [`experiment-plan`](skills/experiment-plan/SKILL.md) | 通用 | claim-driven 实验路线图，含 ablation、预算和执行顺序 | 否 |
| 🧭 [`research-refine-pipeline`](skills/research-refine-pipeline/SKILL.md) | 通用 | 一条龙：`/research-refine` → `/experiment-plan` | 是 |
| 📝 [`grant-proposal`](skills/grant-proposal/SKILL.md) | 通用 | 基金申请书（科研費/NSF/国自然/ERC/DFG/SNSF/ARC/NWO） | 是 |
| 🎤 [`paper-slides`](skills/paper-slides/SKILL.md) | 通用 | 会议演讲幻灯片（beamer → PDF + PPTX），含完整演讲稿、speaker notes、Q&A 预案 | 是 |
| 📐 [`proof-writer`](skills/proof-writer/SKILL.md) | ML 理论 | 严格定理/引理证明撰写——可行性分类、依赖图谱 | 否 |
| 📡 [`comm-lit-review`](skills/comm-lit-review/SKILL.md) | 通信 / 无线 | 通信领域文献检索——IEEE/ACM 优先、venue 分层、PHY/MAC/NTN 分类 | 否 |
| 🏗️ [`dse-loop`](skills/dse-loop/SKILL.md) | 体系结构 / EDA | 自动设计空间探索——迭代调参（gem5、Yosys 等） | 否 |
| 🤖 [`idea-discovery-robot`](skills/idea-discovery-robot/SKILL.md) | 机器人 / 具身智能 | 工作流 1 适配版——按 embodiment、sim2real、安全约束筛选 idea | 是 |
| 🖼️ [`paper-poster`](skills/paper-poster/SKILL.md) | 通用 | 已弃用——重定向 stub,指向核心 [`/paper-poster-html`](skills/paper-poster-html/SKILL.md)(测量门控 HTML/CSS 流水线);旧 LaTeX 实现仅存于 git history | — |
| 📐 [`mermaid-diagram`](skills/mermaid-diagram/SKILL.md) | 通用 | Mermaid 图表（20+ 种类型）——`paper-illustration` 的免费替代，无需 API key | 否 |
| 🎨 [`paper-illustration`](skills/paper-illustration/SKILL.md) | 通用 | AI 生成架构图（Gemini），基于 [PaperBanana](https://github.com/dwzhu-pku/PaperBanana)，集成到工作流 3 | 否 |
| 🤖 [`skills-codex`](skills/skills-codex/) | 通用 | 主线科研技能的 Codex CLI 同步包（含 `result-to-claim`、`rebuttal`、`ablation-planner`）+ `shared-references/` 支持目录 | — |

</details>

<details>
<summary><b>🌐 外部项目 & 文档（12 个）</b> — 点击展开</summary>

| 名称 | 领域 | 描述 |
|------|------|------|
| 🪨 [rosetta](https://github.com/SyntaxSmith/rosetta) | Pro 级 ChatGPT MCP | Node 程序化访问 **ChatGPT Pro / `gpt-5.5-pro` / DeepResearch**——通过 Chrome CDP Fetch 拦截 + WebSocket second-leg streaming 实现。自带 MCP server（Claude Code / Codex / Cline），是 Oracle MCP 在 `— reviewer: oracle-pro` 高 tier review 上的另一种实现路径。支持多轮对话、并发、live token deltas、15 分钟 idle-timeout watchdog（长 Pro thinking 不会被误杀）。MIT，by [@SyntaxSmith](https://github.com/SyntaxSmith) |
| 🛡️ [open-source-hardening-skills](https://github.com/zeyuzhangzyz/open-source-hardening-skills) | DevOps / 开源 | 10 个 skill 流水线，将研究代码加固为生产级开源项目 |
| 📊 [CitationClaw](https://github.com/VisionXLab/CitationClaw) | 通用 | 引用影响力分析——论文标题 → 引用爬取、学者识别、HTML 报告 |
| 🚀 [Antigravity 适配指南](docs/ANTIGRAVITY_ADAPTATION_CN.md) | 通用 | 在 [Google Antigravity](https://antigravity.google/) 中使用 ARIS skills——原生 SKILL.md 支持，双模型（Claude Opus 4.6 / Gemini 3.1 Pro），MCP 配置，中[英](docs/ANTIGRAVITY_ADAPTATION.md)文指南 |
| 🐾 [OpenClaw 适配指南](docs/OPENCLAW_ADAPTATION.md) | 通用 | 在 [OpenClaw](https://github.com/All-Hands-AI/OpenHands) 中使用 ARIS 工作流 |
| 🖱️ [Cursor 适配指南](docs/CURSOR_ADAPTATION.md) | 通用 | 在 [Cursor](https://www.cursor.com/) 中使用 ARIS skills |
| 🖥️ [Trae 适配指南](docs/TRAE_ARIS_RUNBOOK_CN.md) | 通用 | 在 [Trae](https://www.trae.ai/)（字节跳动 AI IDE）中使用 ARIS skills |
| 🎛️ [auto-hparam-tuning](https://github.com/zxh0916/auto-hparam-tuning) | 通用 | 自动超参调优——AI agent 读项目、规划策略、跑实验、分析 TensorBoard、从结果中学习。基于 Hydra |
| 📚 [paper-to-course](https://github.com/KaguraTart/paper-to-course) | 教育 | 论文转交互式课程——PDF/LaTeX 论文自动转为六模块 HTML 课程，含公式拆解、文献时间线、测验、术语提示。单文件打包，无需服务器 |
| 🔎 [deep-research-skills](https://github.com/Weizhena/deep-research-skills) | 通用 / Web 搜索 | 模块化 web 搜索策略包——按源拆分独立模块：Stack Overflow / GitHub Issues 错误串调试 / 中文技术社区（CSDN / 掘金 / 知乎 / V2EX / 腾讯阿里云社区）/ 通用 Web（Reddit / HN / Dev.to / Medium）。补 ARIS [`/research-lit`](skills/research-lit/SKILL.md) 以学术源为主的栈，给**非学术**场景（调试、版本兼容追踪、中文技术检索）提供查询策略。by [@Weizhena](https://github.com/Weizhena) |
| 🖼️ [posterly](https://github.com/Chenruishuo/posterly) | 通用 / 海报 | 把学术会议海报做成**单个 HTML/CSS 文件 → 可印刷 PDF**（headless Chromium，无需 LaTeX）。一个 Claude Code skill——其门控机制现已成为 ARIS 默认 `/paper-poster-html` 的核心。by [@Chenruishuo](https://github.com/Chenruishuo) |
| 🛰️ [Claude Fleet](https://github.com/tianyilt/claude-fleet) | 看板 / DevEx | 本地**只读**看板，同时盯住一堆并行的 Claude Code / Codex 窗口——triage（干活 / 等你 / 跑完）、一键 Focus、~50ms 全文搜 transcript、skill/memory 用量分析。by [@tianyilt](https://github.com/tianyilt) |

</details>

<a id="workflows"></a>
<a id="-workflows"></a>

## 8. 🔄 工作流

所有 Skills 组成完整科研流水线。每个工作流都可以单独使用，也可以串联：

- **探索新方向（比如写 survey）？** 从工作流 1 开始 → `/idea-discovery`
- **有计划了，需要实现和跑实验？** 工作流 1.5 → `/experiment-bridge`
- **已有结果，需要迭代改进？** 工作流 2 → `/auto-review-loop`
- **准备写论文了？** 工作流 3 → `/paper-writing`（或分步：`/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile` → `/auto-paper-improvement-loop`）
- **全流程？** 工作流 1 → 1.5 → 2 → 3 → `/research-pipeline`，从文献调研一路到投稿
- **想让 ARIS 记住并学习？** 📚 `/research-wiki init` — 跨会话持久记忆，论文、idea、失败实验复合积累
- **想让 ARIS 优化自己？** 工作流 M → `/meta-optimize` — 分析使用日志，提出技能改进，reviewer 审核

> ⚠️ **重要提醒：** 这些工具加速科研，但不能替代你自己的思考。生成的 idea 一定要用你的领域知识审视，质疑其假设，最终决策权在你手上。最好的研究 = 人的洞察 + AI 的执行力，而不是全自动流水线。

### 完整流程 🚀

```
/research-lit → /idea-creator → /novelty-check → /research-refine → /experiment-bridge → /auto-review-loop → /paper-plan → /paper-figure → /paper-write → /auto-paper-improvement-loop → 投稿
  (调研文献)      (找idea)       (查新验证)      (打磨方案)      (实现+部署)       (自动改到能投)      (大纲)        (作图)        (LaTeX+PDF)     (审稿×2 + 格式检查)     (搞定!)
  ├────────────── 工作流 1：找 Idea + 方案精炼 ──────────────┤ ├─ 工作流 1.5 ─┤ ├── 工作流 2 ──┤   ├───────────────── 工作流 3：论文写作 ─────────────────────┤
```

📝 **博客：** [梦中科研全流程开源](http://xhslink.com/o/2iV33fYoc7Q)

### 工作流 1：Idea 发现与方案精炼 🔍

> "这个领域最新进展是什么？哪里有 gap？怎么解决？"

还没有具体 idea？给一个研究方向就行——`/idea-discovery` 搞定剩下的：

1. 📚 **调研**全景（最新论文、开放问题、反复出现的局限性）
2. 🧠 **头脑风暴** 8-12 个具体 idea（GPT-5.5 xhigh）
3. 🔍 **初筛**可行性、算力成本、快速查新
4. 🛡️ **深度验证** top idea（完整查新 + devil's advocate review）
5. 🧪 **并行 pilot 实验**（top 2-3 个 idea 分别上不同 GPU，30 分钟 - 2 小时）
6. 🏆 **按实验信号排序**——有正信号的 idea 排前面
7. 🔬 **精炼方案**——冻结问题锚点，通过 GPT-5.5 迭代 review 打磨方法
8. 🧪 **规划实验**——claim-driven 实验路线图，含 ablation、预算和执行顺序

输出 `IDEA_REPORT.md`（排名后的 idea）+ `refine-logs/FINAL_PROPOSAL.md`（精炼后的方案）+ `refine-logs/EXPERIMENT_PLAN.md`（实验路线图）。失败的 idea 也记录在案，避免重复踩坑。

**涉及 Skills：** `research-lit` + `idea-creator` + `novelty-check` + `research-review` + `research-refine-pipeline`

> 💡 **一键调用：** `/idea-discovery "你的研究方向"` 自动跑完整个工作流 1。

> 🔄 **人在回路中：** 每个阶段都会展示结果等你反馈。不满意？告诉它哪里不对——调整 prompt 重新生成。信任默认选择？它会自动带着最优方案继续。你决定参与多深。

> ⚙️ Pilot 实验预算（最大时长、超时、GPU 总预算）均可配置——见[自定义](#customization)。

<details>
<summary><b>展开工作流 1 的命令清单示例</b> —— research-lit → idea-creator → novelty-check → research-refine → experiment-plan 一步步该敲什么</summary>

```
1. /research-lit "discrete diffusion models"    ← Zotero→Obsidian→本地→网络，整理全景
   /research-lit "topic" — sources: zotero, web  ← 或指定只搜部分源
   /research-lit "topic" — arxiv download: true   ← 同时下载最相关的 arXiv PDF
2. /idea-creator "DLLMs post training"     ← 自动生成 8-12 个 idea，筛选排序
3. 选 top 2-3 个 idea
4. /novelty-check "top idea"                     ← 查新：有没有人做过？
5. /research-review "top idea"                   ← 让外部 LLM 批判你的想法
6. /research-refine "top idea"                   ← 冻结问题锚点 + 精炼方法
7. /experiment-plan                              ← claim-driven 实验路线图
8. /run-experiment → /auto-review-loop           ← 闭环！
```

</details>

📝 **博客：** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

### 工作流 1.5：实验桥接 🔗

> "我有计划了，帮我实现代码、部署实验、拿到初始结果。"

已有实验计划（来自工作流 1 或自己写的）？`/experiment-bridge` 一键搞定：

1. 📋 **解析**实验计划（`refine-logs/EXPERIMENT_PLAN.md`）
2. 💻 **实现**实验脚本（复用已有代码，加 argparse/logging/seed）
3. 🔍 **GPT-5.5 代码审查** — 跨模型 review 在浪费 GPU 前抓逻辑 bug（`code review: true` 默认开启）
4. ✅ **Sanity check** — 先跑最小实验，发现运行时 bug
5. 🚀 **部署**完整实验到 GPU（`/run-experiment`）
6. 📊 **收集**初始结果，更新实验 tracker

<details>
<summary><b>展开工作流 1.5 流程图</b> —— 实验计划 → Claude 实现 → GPT-5.5 审码 → sanity check → GPU 部署 → 监控 → 结果</summary>

```
┌─────────────────────────────────────────────────────────────────┐
│                工作流 1.5：实验桥接                                │
│                                                                  │
│   EXPERIMENT_PLAN.md                                             │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ Claude   │────▶│ GPT-5.5  │────▶│ Sanity   │               │
│   │ Code     │     │ xhigh    │     │ Check    │               │
│   │ 写代码    │     │ 审查代码  │     │ (1 GPU)  │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ 收集      │◀────│ 监控进度  │◀────│ 部署到    │               │
│   │ 结果      │     │ (+ W&B)  │     │ GPU      │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│         │                                                        │
│         ▼                                                        │
│   准备好进入 /auto-review-loop                                    │
└─────────────────────────────────────────────────────────────────┘
```

</details>

**涉及 Skills：** `experiment-bridge` + `run-experiment` + `monitor-experiment`

> 💡 **一键调用：** `/experiment-bridge` 自动读取 `refine-logs/EXPERIMENT_PLAN.md`。也可指定：`/experiment-bridge "my_plan.md"`。

> ⚙️ `CODE_REVIEW`、`AUTO_DEPLOY`、`SANITY_FIRST`、`MAX_PARALLEL_RUNS` 均可配置——见[自定义](#customization)。

### 工作流 2：自动科研循环 🔁（睡一觉醒来看结果）

> "帮我 review 论文，修复问题，循环到通过为止。"
>
> GPT-5.5 审稿 → 定位弱点 → 建议实验 → Claude Code 自动写脚本、部署到 GPU、监控结果、改写论文——你睡觉就行。只需在 `CLAUDE.md` 里配好[GPU 服务器信息](#gpu-server-setup)。

1. 🔍 **深度评审** — GPT-5.5 xhigh 对当前论文 / claims / 实验做一遍深读，定位弱点
2. 🩹 **修复** — Claude 实现修复（改写章节、加 baseline、或通过 `/run-experiment` 跑新实验）；预估超过 4 GPU-小时的实验直接跳过、标记为"需人工跟进"
3. 📊 **再评估** — `/monitor-experiment` 收结果、改稿、再喂回 reviewer
4. 🔁 **循环** — 直到分数 ≥ `POSITIVE_THRESHOLD`（默认 6/10）或撞到 `MAX_ROUNDS`（默认 4）；中途上下文窗口满了，工作流会从 `REVIEW_STATE.json` 自动恢复

<details>
<summary><b>展开工作流 2 的小流程图</b> —— 外部评审 → 实现修复 / 跑实验 → 监控结果 → 循环到阈值</summary>

```
外部 LLM 评审 → Claude Code 实现修复 → /run-experiment 部署 → 收结果 → 再评审 → 循环
                ↑ 需要新方向时自动 /novelty-check 查新
```

</details>

**涉及 Skills：** `auto-review-loop` + `research-review` + `novelty-check` + `run-experiment` + `analyze-results` + `monitor-experiment`

> 💡 **一键调用：** `/auto-review-loop "你的论文主题"` 自动跑完整个工作流 2。

<details>
<summary><b>展开工作流 2 的参数示例、reviewer 难度等级和完整安全机制</b> —— topic/scope 怎么传、medium/hard/nightmare 区别、6 条安全规则</summary>

**传什么参数？** 简短的主题或范围就够——skill 会自动读取项目中的叙事文档（`NARRATIVE_REPORT.md`）、memory 文件、实验结果和历史 review，为 GPT-5.5 组装完整上下文。示例：
- `/auto-review-loop "离散扩散语言模型的 factorized gap"` — 宽泛主题，skill 自动搜集
- `/auto-review-loop "重点看第 3-5 节，CRF 结果偏弱"` — 指定范围 + 提示
- `/auto-review-loop` — 也行：skill 读项目文件自动推断主题

用法：
```
> /auto-review-loop 我的 diffusion model 论文
```

**🎮 审稿难度** — 控制 reviewer 的对抗强度：

| 难度 | 变化 | 适用场景 |
|------|------|---------|
| `medium`（默认） | 标准 MCP review，和之前完全一样 | 日常使用 |
| `hard` | + Reviewer Memory（GPT 跨轮追踪疑点）+ 辩论协议（Claude 可反驳，GPT 裁决） | 想要更严格的反馈 |
| `nightmare` | + GPT 通过 `codex exec` 直接读代码仓库（Claude 无法过滤信息）+ 对抗性验证 | 投顶会前的极限压测 |

```bash
/auto-review-loop "topic" — difficulty: nightmare    # GPT 自己读你的代码和结果来验证
```

**🛡️ 关键安全机制：**

- 🔒 **MAX_ROUNDS = 4** — 防止无限循环；达到分数阈值时提前停止
- ⏱️ **> 4 GPU-hour 的实验自动跳过** — 不会启动超大实验，标记为"需人工跟进"
- 🧠 **优先改叙事而非跑新实验** — 同样能解决问题时，选择成本更低的路径
- 🪞 **不隐藏弱点** — 明确规则："不要隐藏弱点来骗高分"
- 🔧 **先修后审** — 必须实现修复后再重新 review，不能只承诺修
- 💾 **上下文压缩恢复** — 每轮结束后持久化状态到 `REVIEW_STATE.json`。如果上下文窗口满了触发自动 compact，工作流会从状态文件恢复断点继续——无需人工干预

</details>

> ⚙️ MAX_ROUNDS、分数阈值、GPU 限制均可配置——见[自定义](#customization)。

📝 **博客：** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### 工作流 3：论文写作流水线 📝

> "把我的研究报告变成可投稿的 PDF。" 需要本地 LaTeX 环境——见[前置条件](#prerequisites)。

1. 📝 **叙事** — 写 `NARRATIVE_REPORT.md`（声明 / 实验 / 结果 / 图表说明）；模板见 [`templates/NARRATIVE_REPORT_TEMPLATE.md`](templates/NARRATIVE_REPORT_TEMPLATE.md)
2. 🧭 **规划** — `/paper-plan` 生成 claims-evidence 矩阵 + 分节计划
3. 📊 **画图** — `/paper-figure` 从 JSON/CSV 生成数据驱动的图表和对比表
4. ✍️ **写作** — `/paper-write` 逐 section 生成 LaTeX
5. 🔧 **编译** — `/paper-compile` 编 PDF、修错、跑页数验证
6. ✨ **润色** — `/auto-paper-improvement-loop` 跑 2 轮 GPT-5.5 内容审稿 + 终局格式合规检查

<details>
<summary><b>展开工作流 3 的写作流向图与命令清单</b> —— NARRATIVE_REPORT → /paper-plan → /paper-figure → /paper-write → /paper-compile → 润色循环</summary>

```
NARRATIVE_REPORT.md ──► /paper-plan ──► /paper-figure ──► /paper-write ──► /paper-compile
    (研究叙事)          (大纲+矩阵)     (图表+LaTeX)      (逐节LaTeX)      (编译PDF)
```

```
典型流程：
1. 写 NARRATIVE_REPORT.md（来自工作流 2 的结果）
2. /paper-plan — 生成 claims-evidence 矩阵 + 分节计划
3. /paper-figure — 生成对比表、训练曲线等图表
4. /paper-write — 逐 section 生成 LaTeX（含 bib 清理、de-AI 打磨）
5. /paper-compile — 编译 PDF、修复错误、页数验证
6. /auto-paper-improvement-loop — 内容审稿 ×2 + 格式合规检查
```

</details>

**涉及 Skills：** `paper-plan` + `paper-figure` + `paper-write` + `paper-compile` + `auto-paper-improvement-loop` +（投稿后）`paper-poster-html` + `paper-slides`

> **一键调用：** `/paper-writing "NARRATIVE_REPORT.md"` 自动跑完整个工作流 3。

**输入：** 一份 `NARRATIVE_REPORT.md`，描述研究内容：声明、实验、结果、图表。叙事越详细（尤其是图表描述和定量结果），输出越好。

**输出：** 一个可投稿的 `paper/` 目录，含 LaTeX 源码、干净的 `.bib`（仅含实际引用）、编译好的 PDF。

<details>
<summary><b>展开工作流 3 的核心特性细节</b> —— Claims-Evidence 矩阵、bib 清理、figure 模式、ICLR 端到端实测</summary>

**核心特性：**
- 📐 **Claims-Evidence 矩阵** — 每个声明映射到证据，每个实验支撑一个声明
- 📊 **自动图表生成** — 从 JSON 数据生成折线图、柱状图、对比表
- 🧹 **Bib 自动清理** — 过滤未引用条目（实测 948→215 行）。通过 [DBLP](https://dblp.org)/[CrossRef](https://www.crossref.org) 获取真实 BibTeX，替代 LLM 生成
- 📄 **灵活节数** — 5-8 节按论文类型选择（理论论文常需 7 节）
- 🔍 **GPT-5.5 审稿** — 每步可选外部 LLM 审查
- ✂️ **De-AI 打磨** — 去除 AI 写作痕迹（delve、pivotal、landscape…）
- 🎯 **精确页数验证** — 基于 `pdftotext` 定位 Conclusion 结束位置

> ⚠️ **`/paper-figure` 能做什么、不能做什么：** 能自动生成**数据驱动的图表**（训练曲线、柱状图、热力图）和 **LaTeX 对比表**（从 JSON/CSV 数据）。**不能**生成架构图、流程图、模型示意图、生成样本网格——这些需要手动创建（draw.io、Figma、TikZ 等），放到 `figures/` 目录后再跑 `/paper-write`。一篇典型 ML 论文中，约 60% 的图表可自动生成，约 40% 需手动制作。

**端到端实测：** 从一份 NARRATIVE_REPORT.md 生成了一篇 9 页 ICLR 2026 理论论文（7 节、29 条引用、4 张图、2 个对比表）——零编译错误、零 undefined reference。

</details>

#### 论文自动润色循环 ✨

工作流 3 生成论文后，`/auto-paper-improvement-loop` 自动跑 2 轮 GPT-5.5 xhigh 内容审稿 → 修复 → 重编译，外加一轮格式合规检查，将粗稿自动提升到可投稿质量。

<details>
<summary><b>展开论文自动润色 benchmark</b> —— 实测 ICLR 2026 理论论文分数轨迹（4/10 → 8.5/10）+ Round 1/2/3 详细修复清单</summary>

**分数变化（实测 — ICLR 2026 理论论文）：**

| 轮次 | 分数 | 关键改动 |
|------|------|---------|
| Round 0 | 4/10（内容） | 基线生成论文 |
| Round 1 | 6/10（内容） | 修复假设、软化声明、重命名符号 |
| Round 2 | 7/10（内容） | 添加合成验证、强化局限性 |
| Round 3 | 5→8.5/10（格式） | 移除多余图、拆附录、压缩结论、修 overfull hbox |

**最终：正文 8 页（ICLR 限 9 页），0 个 overfull hbox，格式合规。** 3 轮共涨 4.5 分。

<details>
<summary>Round 1 修复细节（6 项）</summary>

1. **CRITICAL — 假设与模型矛盾**：有界性假设与模型的分布族不一致。改为与尾部兼容的假设，并添加正式截断桥接。
2. **CRITICAL — 理论-实验 gap**：理论假设理想化编码器，实验用学习的非线性编码器。软化 "validate" → "demonstrate practical relevance"，添加明确声明。
3. **MAJOR — 缺定量指标**：添加参数量对比表（latent vs total），诚实计入系统总开销。
4. **MAJOR — 定理不自包含**：添加 "Interpretation" 段落，显式列出所有依赖。
5. **MAJOR — 新颖性声明过宽**：将宽泛的 "首个收敛保证" 精确限定到具体成立条件。
6. **MAJOR — 符号冲突**：重命名一个与另一关键变量冲突的符号。添加 Notation 段。

</details>

<details>
<summary>Round 2 修复细节（4 项）</summary>

1. **MAJOR — 缺理论验证实验**：添加合成验证子节，在受控条件下直接测试两个核心理论预测。
2. **MAJOR — 声明仍然过强**：将强等价声明替换为适当的 hedge 语言，全文统一。
3. **MAJOR — 非正式理论论证**：将非正式论证正式化为一个命题，给出显式误差界。
4. **MINOR — 局限性不足**：扩展为显式列出所有假设，承认缺少标准评估指标。

</details>

<details>
<summary>Round 3 格式修复（8 项）</summary>

1. 移除多余的 hero figure（省 ~0.7 页）
2. 压缩结论 15→9 行
3. 合成验证移至附录 A
4. 对比表格移至附录 B
5. 修复 overfull hbox (85pt)，用 `\resizebox`
6. 添加紧凑 float spacing（`\captionsetup`、`\textfloatsep`）
7. Introduction 中行内化居中问题块
8. 收紧 `itemize` 环境间距

</details>

</details>

### 工作流 4：Rebuttal 📝（安全应对审稿意见）

> **"审稿意见来了。帮我写一份有根据、不夸大的 rebuttal。"**

`/rebuttal` 解析审稿意见，制定策略，起草符合 venue 规则（字数限制、纯文本等）的回复：

1. 📋 **解析** —— 规范化 review 文本，校验 venue 规则（字符限制、纯文本约束等）
2. 🔍 **原子化** —— 把每条 review 拆成 issue 卡片（类型、严重度、reviewer 立场）
3. 🗺️ **策略制定** —— 全局主题、per-reviewer 优先级、字符预算、被禁 claim
4. 🧪 **证据补跑**（可选）—— 如果 `auto experiment: true`，通过 `/experiment-bridge` 自动跑补充实验
5. ✍️ **起草** —— 全局开场 + per-reviewer 编号回复 + meta-reviewer 收尾
6. 🛡️ **安全检查** —— 6 道 lint：覆盖率、出处可追、承诺受控、语气、内部一致性、字符限制
7. 🔬 **GPT-5.5 压力测试** —— 内部怀疑式终审 draft
8. 📄 **定稿** —— 两份产物：`PASTE_READY.txt`（精确字数，直接粘贴投递）+ `REBUTTAL_DRAFT_rich.md`（扩展版用于人工编辑）
9. 🔄 **Follow-up 回合** —— reviewer 追问场景的 delta 回复，技术细节逐轮升级

<details>
<summary><b>展开工作流 4 的 rebuttal 流程图</b> —— 解析意见 → 策略 → 可选证据补跑 → 起草 → GPT-5.5 压测 → 双版本定稿 → follow-up 回合</summary>

```
┌─────────────────────────────────────────────────────────────────┐
│                   工作流 4：Rebuttal                              │
│                                                                  │
│   审稿意见到达                                                    │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ 解析 +    │────▶│ 策略     │────▶│ 证据     │               │
│   │ 原子化    │     │ 规划     │     │ 补跑     │               │
│   │ 审稿意见  │     │          │     │（可选）  │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ 定稿     │◀────│ GPT-5.5  │◀────│ 起草     │               │
│   │ 双版本    │     │ 压力测试 │     │ rebuttal │               │
│   │          │     │          │     │          │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│         │                                                        │
│         ▼                                                        │
│   PASTE_READY.txt（严格字数）+ RICH.md（扩展版）                │
│         │                                                        │
│         ▼                                                        │
│   Follow-up 回合（delta 回复，per-reviewer threads）            │
└─────────────────────────────────────────────────────────────────┘
```

</details>

**涉及 skill：** `rebuttal`

> 💡 **Quick mode：** `/rebuttal — quick mode: true` 跑完解析 + 策略（Phase 0-3）就停。先看 reviewer 想要什么，再决定要不要起草完整 draft。

> ⚙️ `VENUE`、`AUTO_EXPERIMENT`、`QUICK_MODE`、`MAX_STRESS_TEST_ROUNDS` 都可配置 —— 见 [自定义](#customization)。

**三道安全门 —— 任何一项不过 rebuttal 不定稿：**
- 🔒 **出处可追** —— 每条 claim 都能追溯到 paper / review / 用户确认结果。不允许编造。
- 🔒 **承诺受控** —— 每个承诺都由用户批准。不允许过度承诺。
- 🔒 **完整覆盖** —— 每个 reviewer 关切都被记录。不允许遗漏。

### 工作流 5:Resubmit Pipeline 🔁(跨 venue 移植论文,纯文本)

把打磨好的论文从 venue A → B,带**不可覆盖的硬约束** —— 不加新实验 · 不改 bib · 不改框架 · 永不覆盖旧投稿 —— 物理隔离 + 5 层匿名检查 + soft-only 审计 + 白名单微编辑 + `/kill-argument` 对抗门。**完整流程 + 约束 → [docs/RESUBMIT_AND_TALK_CN.md](docs/RESUBMIT_AND_TALK_CN.md)**

### 工作流 6:Conference Talk Pipeline 🎤(论文 → slides → polish → audits)

`/paper-talk` 把录用论文做成报告:提纲 → `/paper-slides`(Beamer + PPTX + 备注 + Q&A)→ `/slides-polish`(逐页 Codex 视觉审)→ 可选 conference-ready 审计门。是 `/paper-writing` / `/paper-poster-html` 的姊妹流程。**完整流程 → [docs/RESUBMIT_AND_TALK_CN.md](docs/RESUBMIT_AND_TALK_CN.md)**

<a id="-research-wiki--persistent-research-memory"></a>

### 📚 Research Wiki — 持久化研究记忆

> **"不要每次重新推导。让知识复合增长。"** — 灵感来自 [Karpathy 的 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

没有 wiki 时，ARIS 是无状态的——每次 `/idea-discovery` 从零开始。有了 wiki，ARIS 跨研究全生命周期积累：读过的论文、试过的 idea、跑过的实验、验证过的 claim。

**核心洞察：** 失败的 idea 是最宝贵的记忆。知道什么不行的研究者，比从零开始的研究者更强。

**启用：**
```
> /research-wiki init     # 一次性初始化，在项目中创建 research-wiki/
```

**就这样。** 初始化后自动工作。

<details>
<summary><b>展开自动触发的 wiki hooks</b> —— /research-lit、/idea-creator、/result-to-claim 各自触发什么，以及重新构思提示</summary>

| 时机 | 发生了什么 | Wiki 操作 |
|------|-----------|----------|
| `/research-lit` 找到论文 | 论文自动入库 | 创建 `papers/<slug>.md`，添加关系边 |
| `/idea-creator` 运行 | 先读 wiki | 失败 idea = 禁止列表，gap = 搜索种子 |
| `/idea-creator` 完成 | 所有 idea 写回 | 推荐的 + 被淘汰的都写 → `ideas/<id>.md` |
| `/result-to-claim` 判定 | 结果写回 | 实验页面，claim 状态更新（支持/否定） |
| 3+ idea 失败 | 建议重新构思 | "💡 wiki 已经知道什么不行了，考虑重新 ideate" |

</details>

<details>
<summary><b>展开 Research Wiki 的数据模型、螺旋上升示例和手动子命令</b> —— 四种实体、3 轮"失败 idea → 更好 idea"演化、ingest/query/lint/stats</summary>

**四种实体：** 📄 论文、💡 想法、🧪 实验、📋 声明

**螺旋上升：**
```
第 1 轮：读 15 篇论文 → idea A → 实验 → 失败 → wiki 记住"A 因为 OOM 失败"
第 2 轮：wiki 知道 A 不行 → idea D（避开 A 的坑）→ 部分成功 → wiki 记住
第 3 轮：综合 A 失败 + D 部分成功 → idea F → 成功 🎉
```

**子命令：**
```
/research-wiki init                               # 初始化
/research-wiki ingest "论文标题" — arxiv: xxx       # 手动添加论文
/research-wiki query "主题"                        # 重建 query_pack.md
/research-wiki lint                                # 健康检查
/research-wiki stats                               # 统计概览
```

</details>

> 🔒 **安全设计：** 所有 hook 都有 `if wiki 存在` 守卫。没初始化 = 零影响。纯 Python 标准库，无依赖。

---

<a id="workflow-m-meta-optimize--aris-optimizes-itself"></a>

### 工作流 M：Meta-Optimize 🧬（ARIS 优化自己）

> **"分析我的使用模式，改进你自己的技能。"**

与工作流 1–4 优化*研究产物*（论文、代码、实验）不同，工作流 M 优化的是 *harness 本身*——SKILL.md 指令、默认参数和收敛规则。灵感来自 [Meta-Harness](https://arxiv.org/abs/2603.28052)（Lee et al., 2026）。

<details>
<summary><b>展开工作流 M 的一次性设置与使用命令</b> —— Claude Code hook 安装、/meta-optimize 各变体（项目 / 单 skill / --global / apply）</summary>

**设置（一次性，在普通终端）：**
```bash
mkdir -p .claude .aris/meta tools/meta_opt
cp Auto-claude-code-research-in-sleep/templates/claude-hooks/meta_logging.json .claude/settings.json
cp Auto-claude-code-research-in-sleep/tools/meta_opt/*.sh tools/meta_opt/
chmod +x tools/meta_opt/*.sh
claude   # hooks 立即生效
```

**使用（累积 5 次以上工作流运行后）：**
```
> /meta-optimize                        # 分析当前项目
> /meta-optimize "auto-review-loop"     # 聚焦单个技能
> /meta-optimize --global               # 分析跨项目的使用趋势
> /meta-optimize apply 1                # 应用推荐的修改 #1
```

</details>

**工作原理：**

1. 📊 **被动记录** — hooks 静默记录每次技能调用、工具执行、失败、参数覆盖。事件同时写入**项目级**（`.aris/meta/events.jsonl`）和**全局**（`~/.aris/meta/events.jsonl`，带 `"project"` 标签）两份日志
2. 🔍 **模式分析** — 识别高频覆盖参数（默认值不好）、重复失败（缺少错误处理）、分数停滞（收敛规则需调整）
3. 🩹 **生成 Patch** — 对目标 SKILL.md 生成最小修改 + 数据支撑的理由
4. 🔬 **Reviewer 审核** — GPT-5.5 xhigh 评估每个 patch 是否安全
5. ✅ **用户批准** — 从不自动应用，用户说了算

<details>
<summary><b>展开工作流 M 的流程图与"优化对象"列表</b> —— 事件日志 → SKILL.md patch → GPT-5.5 审核 → 用户批准；prompt / 默认参数 / 收敛规则 / 错误处理</summary>

```
┌─────────────────────────────────────────────────────────────────┐
│                  工作流 M：Meta-Optimize                         │
│                                                                  │
│   正常 ARIS 使用（W1-W4）                                        │
│         │ （hooks 被动记录事件）                                   │
│         ▼                                                        │
│   .aris/meta/events.jsonl                                        │
│         │                                                        │
│         ▼                                                        │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ 分析模式  │────▶│ 提出      │────▶│ GPT-5.5  │               │
│   │          │     │ SKILL.md │     │ 审核      │               │
│   │          │     │ 修改      │     │ patch    │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│                                          │                       │
│                                          ▼                       │
│                                    用户批准？                     │
│                                     是 → 应用                    │
│                                     否 → 跳过                    │
└─────────────────────────────────────────────────────────────────┘
```

**优化对象（harness 组件）：** 技能 prompt、默认参数（`difficulty`、`MAX_ROUNDS`、`threshold`）、收敛规则、错误处理模式。

</details>

**不优化：** 研究产物（论文、代码、实验）——那是 W1–W4 的工作。

> 💡 这是**维护工作流**，不属于 W1→W1.5→W2→W3→W4 研究流水线。像 `git gc` 一样定期运行。

---

### ⚡ Effort Levels

每个 skill 都接受 `— effort: lite | balanced | max | beast` —— 调节广度/深度(论文 · idea · pilot · 轮次 · seed · 审计深度)从 ~0.4× 到 ~5–8×;**默认 `balanced`**(老用户零变化)。任何档位都**不变**:Codex reasoning 永远 `xhigh`、DBLP 引用永远开、reviewer 独立性永远开、实验诚实度永远开。**📖 完整规范 + 各 skill 计数 → [`effort-contract.md`](skills/shared-references/effort-contract.md)**

<a id="-optional-gpt-54-pro-via-oracle"></a>

### 🧿 可选：GPT-5.5 Pro via Oracle

给任意 reviewer-aware skill(`/proof-checker`、`/research-review`、`/experiment-audit`、`/rebuttal`…)加 `— reviewer: oracle-pro`,把审稿走 **GPT-5.5 Pro** —— 最强推理,适合深度证明 / 代码 / 实验设计审。默认永远 Codex xhigh;Oracle 未装 ⇒ 优雅降级 + 警告(零影响)。**📖 安装 + 各 skill 示例 → [`reviewer-routing.md`](skills/shared-references/reviewer-routing.md)**

---

<a id="setup"></a>
<a id="-setup"></a>

## 9. ⚙️ 安装

> 📖 **第一次用 ARIS？** [`SETUP_GUIDE_CN.md`](SETUP_GUIDE_CN.md) ([English](SETUP_GUIDE.md)) 给你一个 6 步 prescriptive 走法：macOS 本地 + 远程 Linux GPU 服务器 + Claude Code + Codex MCP，推荐路径。下面这一节是快速参考；更深的 GPU / 自定义 / 模型组合配置见链接里的 docs。

<a id="prerequisites"></a>

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. （仅 review 类 skill 需要）安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. （仅工作流 3：论文写作需要）**LaTeX** 环境，含 `latexmk` 和 `pdfinfo`：
   ```bash
   # macOS
   brew install --cask mactex    # 或: brew install basictex
   brew install poppler          # 提供 pdfinfo

   # Ubuntu/Debian
   sudo apt install texlive-full latexmk poppler-utils

   # 验证
   latexmk --version && pdfinfo -v
   ```
   > 如果只用工作流 1 和 2（找 idea + 自动 review），不需要安装 LaTeX。

<a id="install-skills"></a>

### 安装 Skills

> 💡 **推荐：项目级扁平 symlink 安装**（2026-04-20 起）。每个 ARIS skill 独立 symlink 到 `.claude/skills/<skill-name>`，让 Claude Code 的 slash command 自动补全能直接发现。manifest 在 `.aris/installed-skills.txt` 跟踪 ARIS 装了什么——uninstall 和 reconcile 只动 manifest 里的条目，绝不碰你自己的 skill。
>
> 🤖 **Codex mirror 路线：** Claude 主线继续使用 `install_aris.sh` / `smart_update.sh`。Codex 原生项目安装请用 `install_aris_codex.sh`，Codex copy 安装更新请用 `smart_update_codex.sh`。

```bash
# 1. 克隆 ARIS 一次到稳定位置
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo

# 2. 在每个使用 ARIS 的项目里 attach：
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh
# → 每个 skill 一个 symlink: .claude/skills/<skill> → ~/aris_repo/skills/<skill>
# → 写 manifest .aris/installed-skills.txt（追踪 ARIS 装的每条）
# → 更新 CLAUDE.md ARIS 管理块（best-effort + compare-and-swap，不会覆盖用户改动）
# → 可重入：再跑一次会自动 reconcile 上游的新增/删除

# 3. 已有 skill 的内容更新：直接 git pull（symlink 指向上游，自动跟随）
cd ~/aris_repo && git pull

# 3a. 上游新增 / 删除 skill 时，重跑安装器（一次的事）：
bash ~/aris_repo/tools/install_aris.sh ~/your-paper-project

# 其他常用：
bash ~/aris_repo/tools/install_aris.sh --dry-run        # 看计划，不写盘
bash ~/aris_repo/tools/install_aris.sh --uninstall      # 按 manifest 卸载（不动你自己的 skill）
bash ~/aris_repo/tools/install_aris.sh --from-old       # 从老的 .claude/skills/aris/ 嵌套布局迁移

# Windows（PowerShell，需要管理员权限或开发者模式以创建 junction）：
.\tools\install_aris.ps1 C:\path\to\your-paper-project
```

**为什么 git pull 不能完全代替重跑安装器：** 扁平布局是每个 skill 一个 symlink，所以上游**新增/删除** skill 时，project 里要新增/移除对应的 symlink——这一步只能由安装器做。这个代价换来了 Claude Code 的自动 slash command 发现（CC 只扫一层目录）。

<details>
<summary><b>从老的嵌套布局迁移（2026-04-20 之前的安装）</b></summary>

如果你之前用的是 `install_aris.sh`（创建 `.claude/skills/aris/` 嵌套 symlink）或 `smart_update.sh --target-subdir .claude/skills/aris`（嵌套 copy），那你的 slash command 大概率没被 Claude Code 自动发现。迁移到扁平布局：

```bash
# Symlink 老安装：
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old

# Copy 老安装（可能有本地编辑——需要显式选策略）：
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old --migrate-copy keep-user
#   → 保留嵌套 .claude/skills/aris/ 不动，扁平 symlink 装在旁边
bash ~/aris_repo/tools/install_aris.sh ~/your-project --from-old --migrate-copy prefer-upstream
#   → 把嵌套副本归档到 .aris/legacy-copy-backup-<timestamp>/，再扁平化
```

</details>

<details>
<summary><b>其他安装方式（进阶）</b></summary>

**项目级 copy（不要 symlink，适合需要为单个项目定制 skill 内容）：**
```bash
mkdir -p ~/your-project/.claude/skills
bash ~/aris_repo/tools/smart_update.sh --project ~/your-project --apply
# 默认 --target-subdir 是 .claude/skills（扁平），这是 Claude Code 期望的布局。
# （老的 --target-subdir .claude/skills/aris 已弃用，见上面的迁移段。）
```

**全局安装（一份 copy 在 home 目录，所有项目可用）：**
```bash
mkdir -p ~/.claude/skills
cp -r ~/aris_repo/skills/* ~/.claude/skills/
# 更新：bash tools/smart_update.sh --apply
```

> 全局安装会增加和其他全局 skill 包名字冲突的风险。只在不混装 ARIS 与 Superpowers / OpenHands 等的情况下使用——否则用上面的项目级安装。

</details>

<a id="optional-codex-plugin-for-code-review"></a>

<details>
<summary><b>可选：用于代码审查的 Codex Plugin</b></summary>

[codex-plugin-cc](https://github.com/openai/codex-plugin-cc) 会提供额外的 Codex 能力；安装后 ARIS 会自动检测并使用：

```bash
# 在 Claude Code 中：
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

**ARIS 会在这些地方使用 plugin：**

| Skill | 所属流程 | 作用 |
|-------|---------|------|
| `/codex:review` | Workflow 1.5 | GPU 部署前审查实验代码 |
| `/codex:adversarial-review` | Workflow 1.5 | 对抗式代码审查（寻找边界情况和 bug） |
| `/codex:rescue` | Workflow 1.5 + 3 | **自动调试救援**：当实验或 LaTeX 编译连续失败 2 次后，Codex 会在下一次重试前独立诊断根因 |

所有 plugin 功能都是**可选的**；如果没有安装，ARIS 会回退到 Claude 自己的诊断。这个 plugin 只是多加一双眼睛。

> 注意：ARIS 的核心跨模型审稿（论文评分、idea 评估、rebuttal 压力测试）仍然使用 Codex MCP，因为它支持自定义 prompt。plugin 不能替代这部分能力。

</details>

### 更新 Skills

```bash
cd Auto-claude-code-research-in-sleep
git pull

# 方案 A：全量更新（用最新版覆盖所有 skill）
cp -r skills/* ~/.claude/skills/

# 方案 B：安全更新（只加新 skill，保留你的定制）
cp -rn skills/* ~/.claude/skills/

# 方案 C：只更新指定 skill
cp -r skills/experiment-bridge ~/.claude/skills/
```

> 💡 **选哪个？** 没改过 skill 用 **A**。改过用 **B**（新 skill 会加进来，你的改动保留——但改过的文件不会收到上游 bug fix）。**C** 精确更新。

### 🌙 过夜自动运行的免确认配置（可选）

<details>
<summary>过夜跑免点权限弹窗 —— 往 <code>.claude/settings.local.json</code> 加一段</summary>

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

</details>

<a id="gpu-server-setup"></a>

### 🖥️ 自动跑实验的 GPU(可选)

审稿人说"补个消融实验"时,Claude Code 会自动写脚本并跑到你的 GPU 上 —— 你只需在 `CLAUDE.md` 里声明服务器。三种模式(**远程 SSH** · **本地 GPU** · **Vast.ai 按需**):配置片段 + 教程见 **[docs/GPU_SETUP_CN.md](docs/GPU_SETUP_CN.md)**(Vast.ai 详解 → **[Vast.ai 指南](docs/integrations/VAST_GPU_GUIDE_CN.md)**)。没 GPU?Review / 改写照常,跑实验的修复会标记"需人工跟进"。

### 🔌 集成(可选)

把文献库 / 笔记库 / 通知接进 ARIS —— 没配置就静默跳过:

- **[Zotero](docs/integrations/ZOTERO_CN.md)** —— `/research-lit` 里搜 collections + 标注 + BibTeX(联网搜索之前)。
- **[Obsidian + arXiv](docs/integrations/OBSIDIAN_CN.md)** —— 搜你的 vault 笔记;arXiv 内置免配置。
- **[飞书 / Lark](docs/integrations/FEISHU_CN.md)** —— 手机推送 + 双向审批,适合过夜跑。

<a id="customization"></a>
<a id="-customization"></a>

## 10. 🎛️ 自定义

Skills 都是纯 Markdown,fork 了随便改。各 skill 的环境变量(GPU 目标、代码审查、reviewer 路由、人工检查点、论文写作开关)和参数透传详见 **[docs/CUSTOMIZATION_CN.md](docs/CUSTOMIZATION_CN.md)**。

<a id="alternative-model-combinations"></a>

## 11. 🔀 替代模型组合

<a id="alt-a-glm--gpt"></a>

没有 Claude / OpenAI API?换别的 provider —— 同样的跨模型架构。ARIS 内置 **10 条替代路线**(Z.ai GLM、阿里 Kimi/Qwen/MiniMax、ModelScope 免费 DeepSeek-V3.1、OpenRouter 一 Key 多模型审稿后端、Codex 当 executor 配 Claude/Gemini reviewer、Google Antigravity)。完整路由表 + 各路线配置见 **[docs/MODEL_COMBINATIONS_CN.md](docs/MODEL_COMBINATIONS_CN.md)**。

<a id="community"></a>

## 12. 💬 交流群

**欢迎贡献领域专用 skill！** 核心 skills 覆盖通用科研工作流，但每个领域都有自己的工具和范式。欢迎提交 PR 为你的领域添加新 skill——EDA、生物信息学、机器人、HPC 等等。只需添加一个 `skills/your-skill/SKILL.md` 并开 PR 即可。参考 [`dse-loop`](skills/dse-loop/SKILL.md) 作为示例。

欢迎加入微信群，交流 Claude Code + AI 科研工作流：

<img src="docs/wechat_group.jpg" alt="微信交流群二维码" width="300">

<a id="citation"></a>

## 13. 📖 引用

如果 ARIS 对你的研究有帮助，请引用：

```bibtex
@article{yang2026aris,
  title={ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration},
  author={Yang, Ruofeng and Li, Yongcan and Li, Shuai},
  journal={arXiv preprint arXiv:2605.03042},
  year={2026}
}
```

<a id="star-history"></a>

## 14. ⭐ Star History

![GitHub stars](https://img.shields.io/github/stars/wanshuiyin/Auto-claude-code-research-in-sleep?style=social)

[![Star History Chart](https://api.star-history.com/svg?repos=wanshuiyin/Auto-claude-code-research-in-sleep&type=Date&v=20260328)](https://star-history.com/#wanshuiyin/Auto-claude-code-research-in-sleep&Date)

<a id="acknowledgements"></a>

## 15. 🙏 致谢

**灵感来自** — 🧪 [AI Scientist](https://github.com/SakanaAI/AI-Scientist)（Sakana）· 📖 [AutoResearch](https://github.com/karpathy/autoresearch)（Karpathy）· 🔭 [FARS](https://analemma.ai/blog/introducing-fars/)（Analemma）· 🎨 [PaperBanana](https://github.com/dwzhu-pku/PaperBanana)（PKU）。

**核心基础设施** — [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（执行层骨干）· [Codex CLI](https://github.com/openai/codex)（通过 MCP 实现跨模型审稿）。

**集成** — **Zotero**（[指南](docs/integrations/ZOTERO_CN.md)）：[zotero-mcp](https://github.com/54yyyu/zotero-mcp)、[Zotero](https://www.zotero.org/)。**Obsidian**（[指南](docs/integrations/OBSIDIAN_CN.md)）：[mcpvault](https://github.com/bitbonsai/mcpvault)、[obsidian-skills](https://github.com/kepano/obsidian-skills)（Obsidian CEO [Steph Ango](https://github.com/kepano) 维护）。**飞书/Lark**（[指南](docs/integrations/FEISHU_CN.md)）：[feishu-claude-code](https://github.com/joewongjc/feishu-claude-code)、[clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu)、[cc-connect](https://github.com/chenhg5/cc-connect)、[lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp)。

**论文写作灵感** — [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) · [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) · [baoyu-skills](https://github.com/jimliu/baoyu-skills)。**社区** — [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills)（已收录）。

**平台适配** — 🤖 [@Falling-Flower](https://github.com/Falling-Flower)（Codex CLI 适配 via `spawn_agent`）· 🔧 [@No-518](https://github.com/No-518)（Codex skill 维护）· 🖱️ [@YecanLee](https://github.com/YecanLee)（[Cursor 适配指南](docs/CURSOR_ADAPTATION.md) + 本地 GPU 文档）· 🏆 [@DefanXue](https://github.com/DefanXue) & [@Monglitay](https://github.com/Monglitay)（首个 ARIS 全流程社区论文，CS 会议评分 8/10）。

**架构与愿景** — 💡 [@JingxuanKang](https://github.com/JingxuanKang)：不止于代码贡献（training-check、result-to-claim、ablation-planner、watchdog、模板、session 恢复），更深度参与 ARIS 架构讨论——compact 模式、工作流状态管理、自主科研愿景——今天很多核心功能（结构化项目文件、context-aware session 恢复）都源自这些对话。

<a id="license"></a>

## 16. License

MIT
