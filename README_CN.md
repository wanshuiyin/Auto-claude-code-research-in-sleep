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
[![Downloads](https://img.shields.io/github/downloads/wanshuiyin/Auto-claude-code-research-in-sleep/total?style=flat-square&color=brightgreen)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20|%20Linux%20|%20Windows-black?style=flat-square)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)


## 📰 最新动态

> **v0.4.21** (2026-06-28) — **bug-fix 补丁**(Codex 对抗式猎杀挖出的 5 个新真用户 bug —— 全部磁盘核实、与 v0.4.20 不重叠;设计 + 实现两道跨模型审)。**🐛 头条**:OpenAI-compatible 流式把跨网络 chunk 切断的多字节 UTF-8(中文 / emoji)解成 `�` —— 每个 HTTP chunk 单独 `from_utf8_lossy`,于是一个 3 字节中文字或 4 字节 emoji 落在 chunk 边界上就两边都坏(对中文用户 + 国产 OpenAI-compatible provider —— Kimi/GLM/MiniMax/DeepSeek/Qwen/豆包 —— 是高频命中)。流式缓冲改为原始字节,只解码完整 SSE 行。**还修**:saved 的 OpenAI/custom executor 配置不再覆盖 shell 设的 `EXECUTOR_PROVIDER`(启动"shell 优先"路径有一处没加 gate → 走错 executor / model not found);Anthropic 流在有内容但无终止信号时 clean-EOF 现在硬报错(`premature_eof`)而非把半截回答存成完整 turn(与 OpenAI `#249` guard 对称;stop_reason-only 兼容路径保留,且 `ARIS_ALLOW_EOF_WITHOUT_STOP=1` 让"合法地从不发终止信号"的代理回到旧行为);`grep_search` 的 `multiline: true` 在 content 模式真能跨行匹配了(此前静默返回空);只装在 `structuredContent` 里的 MCP 工具结果不再被丢弃。测试(CI 模式):api 35 / runtime 212 / tools 67 / aris-cli 181 / commands 5(+21,含 2 个流级集成测试)全绿。Codex MCP(gpt-5.5 xhigh):设计审(NO-GO → 修掉一个 off-by-one 后 GO)→ 实现审(NO-GO → 补流级集成测试后 GO)。(两个潜在候选 —— Anthropic block-`index` 路由、OpenAI 多行 SSE —— 仍留硬化 pass。)
>
> **v0.4.20** (2026-06-19) — **bug-fix 补丁**(Codex 对抗式 bug 猎杀挖出的 7 个真用户 bug,每个过 3 审轮)。**🐛 头条([#299](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/299))**:短 REPL 回复只显示 "✔ Done" —— spinner 的清行把短单行回复擦掉了;现在保留回复(只清 spinner 尾巴)。**还修**:流式多段回复不再粘连("para1para2")—— markdown 流式渲染保留段分隔,流式输出 == 一次性全量渲染;含 **CJK/全角**的 markdown 表格列对齐正确(宽度数显示 cell 非 char);**`aris "prompt"` / `--print`** 现在尊重 `aris setup` 保存的 executor model(此前只 REPL 用,配了 OpenAI/custom 的 executor 会被发 Anthropic 默认 → model not found);**Esc** 现在真能关补全 dropdown;`glob_search` 截断时报**总**匹配数(而非截断的 100,此前让模型以为 1000 个匹配只有 100);`/model` custom 菜单读 executor 实际用的 **effective env** 而非旧磁盘 config。测试(CI 模式):api 32 / runtime 205 / tools 67 / aris-cli 172 / commands 5 全绿。Codex MCP(gpt-5.5 xhigh):猎杀 → 3 审轮(NO-GO → NO-GO → GO)。(两个潜在候选 —— Anthropic block-`index` 路由、OpenAI 多行 SSE —— 当前无触发,留硬化 pass。)

> **v0.4.19** (2026-06-14) — **honesty / guardrails 打磨版**(主题由 Codex fresh-eyes 审计提出;健康配置零行为变化)。**🔴 MCP protocolVersion 协商 guard** —— 修的真 bug:stdio 握手请求 `2025-03-26` 却**从不读服务器协商回的版本**,于是 server 协商到一个 ARIS 不会说的版本会被静默接受,后面 `tools/list` / `tools/call` 在不兼容协议上跑、报错极不透明。现在校验协商版本对照支持集(`2025-11-25` / `2025-06-18` / `2025-03-26` / `2024-11-05`),不支持就**终止连接 + 该 server 降级**并给清晰原因(`aris doctor` 可见)—— 正是 MCP lifecycle spec 要求的行为。请求版本保持 `2025-03-26`,所以**健康 server 不受影响**(已验证:真实 Codex MCP server 照常 spawn + initialize)。**🧹 长尾**:OpenAI 系子代理 fail-loud 文案去掉过期的"lands in v0.4.18"(改版本无关 + 可操作);OpenAI 上游错误体现在**截断 + 凭证脱敏**(`sk-…` / `Bearer …`,含代理可能反射的紧凑 JSON 形状)而非原样拼接;system prompt 的 hook 摘要现在只数 runtime 真正会执行的 hook。测试(CI 模式):api 32 / runtime 204 / tools 67 / aris-cli 167 / commands 5 全绿。Codex MCP(gpt-5.5 xhigh):设计 GO → 实现 NO-GO(紧凑 secret 漏 + command-string 严格性)→ 修后 GO。

> **v0.4.18** (2026-06-14) — **默认模型 → Claude Opus 4.8**,配上正确定价和一张安全网。**🆕 默认 4.8**:模型选择器、`opus` 别名、`aris setup`、子代理全部升到 `claude-opus-4-8` —— 并带**可用性 fallback**:如果你的账号没有 4.8 权限(API 返回 `404 not_found_error`),ARIS 本会话自动回落到 `claude-opus-4-7`、**重建 system prompt 的模型身份保持一致**(绝不在跑 4.7 时还告诉模型它是 4.8)、警告一次、然后重试 —— 主会话(text + JSON)和子代理都覆盖。它只在那个精确的 404 上触发(绝不对 400 / 限流 / 鉴权误触),latch 防循环,且 text 路径从 pre-turn 快照重建,重试绝不重复发你的消息;**有** 4.8 权限的账号和纯 bump 字节级一致。**💰 定价修正**(此前高估 3–5×):当前 Opus 4.5–4.8 = `$5/$25`(已弃用的 Opus 4/4.1 保留 `$15/$75`,用 word-boundary 分档,未来的 `opus-4-10` 不会被误判);Sonnet 4.x = `$3/$15`(Haiku 本来就对)。**🧹 长尾**:`aris setup` 选项 10 把 Codex MCP reviewer pin 到 `model_reasoning_effort="xhigh"`(新 setup 确定性生效,不依赖 `~/.codex/config.toml`);启动期 + `aris doctor` 的**误配提示**([#259](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/259)),针对被静默忽略或放错位的 config(畸形 JSON,或放错的 `~/.aris/config.yaml`);system prompt 的 hook 摘要现在把"解析了但永不触发"的事件标成 **"PARSED ONLY … will NOT run"**,不再误导模型以为死 hook 会跑(完整事件展开另议)。测试(CI 模式):api 32 / runtime 202 / tools 67 / aris-cli 166 / commands 5 全绿;真机冒烟返回 `model=claude-opus-4-8` 端到端。Codex MCP(gpt-5.5 xhigh)审了设计 + 两批实现(REWORK→GO、NO-GO→GO、GO)。

> **v0.4.17** (2026-06-10) — **MCP release**：settings.json 里的 `mcpServers` 终于驱动**真实工具分发**。**🆕 MCP 接线（M1/M2）**：启动时 spawn 配置的 stdio server,工具以 `mcp__<server>__<tool>` 进入模型目录（Anthropic + OpenAI-family 两条 provider 路径都广告）,调用端到端分发;单个 server 失败软降级（健康的照常工作）;`aris doctor` 显示逐 server 真实状态。未受信 MCP 工具**即使 danger-full-access 也会弹确认**（它们是 sandbox 管不到的外部进程）—— `mcpServers.<name>.trust: true` 或会话级"本 server 不再问"可跳过;`--allowedTools` 接受 `mcp__` 名。**🔴 NDJSON 帧修复**：我们的 stdio transport 说的是 LSP 式 `Content-Length:` 帧,而 MCP spec（和 `codex mcp-server`）用的是 newline-delimited JSON-RPC —— 对真实 server 发现阶段静默超时（fake-server 测试全绿是因为 fake 说同一种错误方言,只有真机 e2e 抓到）。现在写侧纯 NDJSON,读侧自动识别双方言,已对 codex 真机端到端验证。顺带:补发 spec 强制的 `notifications/initialized`,写读并发（大 payload 不再管道死锁,即 [#286](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/286) 的失败模式）。**🆕 `aris setup` 选项 10 —— Codex MCP reviewer,零 API key**：一步引导:检测 codex CLI、幂等写入 `mcpServers.codex`（原子 + 备份,绝不覆盖已有条目）、显式同意后写 `trust: true`、可选配一个 API reviewer 作 **fallback**（新 `reviewer_fallback_provider` 字段,MCP 保持 primary）。用 ChatGPT 订阅跑跨模型对抗审 —— 不需要 OpenAI API key。**🆕 Hooks**：object-style schema 保真（matcher/timeout/async 不再被丢弃）;anchored regex matcher 过滤;⚠️ hook 现在**默认 30 秒超时被 kill**（以前永远等;per-hook `timeout` 字段 1–600 秒覆盖;超时只警告不阻断）。**🧹 长尾**：`ARIS_DISABLE_KEYCHAIN` 逃生口（api 测试本地首次全绿,自 v0.4.15 以来）、Anthropic `stop_reason` clean-EOF 对称（CL2）、OpenAI tool-call id-fallback（OE6）、slash 命令进历史。测试（CI 模式）:runtime 199 / aris-cli 165 / tools 67 / api 30 / commands 5 全绿。Codex MCP（gpt-5.5 xhigh）逐 phase 审:16 轮（R1–R16）、7 次 NO-GO 全部修复。推 v0.4.18:P8 完整 OpenAI subagent 路由、hook async 执行、protocolVersion 升级。

> **v0.4.16** (2026-05-30) — **REPL 体验 + provider 加固**，全程零回归纪律:先写 64 个 characterization（golden）测试锁住**当前**的 provider 路由 / pricing / reviewer / subagent / REPL 行为，之后每步改动都保持它们绿。**🆕 命令历史（[#274](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/274)）**：提交的 prompt 现在持久化到 `~/.config/aris/history`（0600），启动时重新加载（退出不再丢）；`ARIS_NO_HISTORY` kill-switch；**只作用于磁盘**的 secret-skip 拒绝写像凭据的行（这些行仍进 session 内存历史，↑/↓ 不变）。**🆕 Ctrl+R 反向搜索**（`(reverse-i-search)` bash 风格；CJK 宽字符感知的单行渲染；零新依赖；不改任何现有按键）。**🔒 OpenAI-family subagent 明确报错**：OpenAI-family 主会话（Kimi/GLM/Gemini/MiniMax/…）spawn 子代理时，此前会**静默盗刷你的 Anthropic OAuth/Keychain 凭据**计费；现在改返回明确错误（不含任何凭据名）—— Anthropic-family executor 完全不受影响。完整 OpenAI 子代理**路由**是跨 crate 改动，推 v0.4.17；本版先关掉盗刷窗口。**🧱 Provider 地基（零行为变化）**：3 个逐字相同的 word-boundary 匹配器合并成 1 个 canonical `runtime::word_match`（调用点转发，真值不变）；新增纯分类器 `runtime::ProviderFamily`（未接入路由）。测试（CI 模式）：runtime 164 / aris-cli 128 / tools 49 / commands 5 全绿（含 64 golden）；危险代码（config env-writing、顺序敏感 pricing 链、reviewer 路由、`provider_match`、`push_history`、每个按键）逐字未动。Codex MCP（gpt-5.5 xhigh）逐 phase + 整合 review。推 v0.4.17：完整 OpenAI subagent 路由、hook-schema + MCP 接入、`api` test 隔离。

> **v0.4.15** (2026-05-29) — **OpenAI-兼容流式健壮性** hotfix。关闭 [#249](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/issues/249)：MiniMax（及其他 OpenAI-compatible provider / 代理）实际不可用,因为 clean-EOF 完成判定把 `data: [DONE]` 哨兵当成**唯一**权威完成信号。**🔴 #249**：非空 `choices[].finish_reason` 才是 Chat Completions spec 定义的终止帧标志,`[DONE]` 只是部分 compat provider 不发的 transport 约定（MiniMax 发 `finish_reason: "stop"` 然后直接关连接、不发 `[DONE]`）。clean-EOF 判定现在抽成可单测的纯函数 `stream_eof_action(...)`,见到 `[DONE]` **或** 非空 `finish_reason` 任一即算完成;**不**在 finish_reason 处提前停读（include_usage 模式下尾随的 usage-only chunk 仍被消费,/cost 不受影响）;真截断仍硬报错,出输出前的 proxy abort 仍走重试。**OE7**：finish_reason 移到 `delta` guard 之前读,只带 finish_reason 无 delta 的终止 choice 也能识别。**OE2**：任何非空 finish_reason（`length`/`content_filter`/`max_output`/`sensitive`）都 flush pending tool,保留 in-stream 顺序 + 逐 tool 渲染。**OE4**：mid-stream error 信封（顶层非 null `error`、无 `choices`）现在硬报错,不再被 choices guard 静默吞（闭合"finish_reason 后又来 error chunk 被误判成功"的 regression 窗口）。**OE3**：SSE `data:` 解析容忍冒号后无空格（`data:{...}`,W3C 合法,部分 compat provider 这么发）。+5 单测（77→82）把此前零覆盖的 SSE 完成逻辑抽成纯函数。Anthropic SSE 路径未动。Codex MCP（gpt-5.5 xhigh）3 轮 review（GO-WITH-NITS → GO-WITH-NITS → **GO**）;推 v0.4.16：CL2（Anthropic stop_reason 对称）、OE6/OE5/OE8、ProviderFamily (P7) + Subagent parity (P8)。

> **v0.4.14** (2026-05-25) — **安全 + 文档卫生 release**，关闭 v0.4.13 codex audit（gpt-5.5 xhigh，6/10 NEEDS-REWORK）最关键的几项。**🔴 S9 (P0)：system prompt 配置脱敏** — v0.4.14 之前 `render_config_section()` 把合并后的 `settings.json` 原样塞进发给 LLM provider 的 system prompt，会泄漏 `env` 映射、`mcpServers.<name>.headers.Authorization` Bearer token、hook command env、签名 URL 的 query 参数、`apiKey` 等字段。新渲染器：白名单顶层字段（`model`/`permissionMode`/`theme`/`outputStyle`/`permissions`/`sandbox`，子树仍走递归 redact）原样输出；敏感 key（`apikey`/`token`/`secret`/`password`/`authorization`/`headers`/`env`/`_KEY`/`_SECRET`/`_TOKEN`）递归替换成 `[REDACTED]`；`mcpServers.<name>.command` 替换成 `<configured>` / `<empty>` / `<unrecognized shape>` 占位符；`mcpServers.<name>.url` 仅保留 `<scheme://host[:port]>` origin（scheme 仅允许 `http`/`https`/`ws`/`wss`，host 仅 ASCII，port 仅数字，IPv6 走 `[...]`）；hook command 字符串完全不输出，只显示 event + hook 计数。Regression test 覆盖 9 处 leak 面。**🟡 P9 (P1)：DeepSeek help 行** — `aris --help` 现在指向 `aris setup` option 7（真正的 `anthropic-compat` 菜单项），不再印那条 resolver 根本不认的 `EXECUTOR_PROVIDER=anthropic-compat` env-var 路径。**🟡 M1/M2 (P1) 文档**：`aris doctor` 在 `mcpServers.len() > 0` 时打黄色实验性 warning，因为 `McpServerManager` 还没接入 `CliToolExecutor` 工具分发（v0.4.16 落地）；README + README_CN 加同样 callout。**🟢 C11 (P2) 流式 idle timeout** — Anthropic `MessageStream` 和 OpenAI SSE loop 都在 `response.chunk().await` 外面包 `tokio::time::timeout`（`ARIS_STREAM_IDLE_TIMEOUT_SECS`，默认 120，clamp `[10, 1800]`，设 0 / 负数关闭）；超时走和 mid-body abort 同一条 retry 路径。关闭"aris 永远卡死无输出"症状（上游 HTTPS proxy 不发 keepalive 时）。**🟢 H11 (P2)**：`tools/sync_main_skills.sh` 版本提示从 v0.4.11 升到 v0.4.13。Codex MCP（gpt-5.5 xhigh）4 轮 review（NO-GO + 4 finding → GO-WITH-NITS + 3 → NO-GO + 1 port smuggling → **GO**）。

> **v0.4.13** (2026-05-25) — **收尾 release**，关闭从 v0.4.10 到 v0.4.12 累积的所有 codex audit P1 + 补长尾 regression test。**🟡 v0.4.10 P1.D per-server MCP timeout** — `mcpServers.<name>.requestTimeoutSecs` override > `MCP_REQUEST_TIMEOUT_SECS` env > 300s default（clamp 1..=1800），让 codex MCP 可以 5 分钟而 fs MCP 5 秒 timeout 共存。**🟡 v0.4.10 known limitation 关闭** — `McpStdioProcess::request()` 跳过 JSON-RPC notification (id 缺失/null) 继续读直到 response，`notifications/log` / `notifications/progress` 不再杀连接。**🟢 meta_opt hook 通过 `aris init` 部署** — `tools/meta_opt/{log_event,check_ready}.sh` 嵌入 binary，`aris init` 写 ARIS-namespaced **`aris-meta-opt-log-event.sh`** / **`aris-meta-opt-check-ready.sh`** 到 `~/.claude/hooks/`（codex round-1 #1：永远不覆盖用户已有的同名 hook）；settings.json 合并 idempotent + backup 强保证 + tempfile + rename 原子写。**🧪 9 个 v0.4.12 targeted regression test** 覆盖 sandbox.strictMode (3) + parse strictMode + provider_match pricing + has_word o-series + stream_options 400 + meaningful-content classification + premature-EOF retry truth table（codex round-1 #3 — `should_retry_on_premature_eof()` 提成纯函数，7 行真值表测试）。**📦 Bundle**：76 skills，**54 helpers**（之前 52；+2 meta_opt 脚本）。**📦 main 分支 Gemini 源头修复** (`fedf361`)：`gemini-search` / `research-lit` 的 `auto-gemini-3` alias 现在在 main，下次 sync 不再 drift。Codex MCP（gpt-5.5 xhigh）3 轮 review（NO-GO + 3 个 hook/atomic/test finding → NO-GO + release metadata 没 bump → GO）。

> **v0.4.12** (2026-05-22) — **Bug-fix + 小功能 release**。**🚨 #238 `sandbox.strictMode` 配置** — `SandboxConfig` 加 `strict_mode: Option<bool>`（`settings.json` 里读 `sandbox.strictMode`）；为 `true` 时 **所有** LLM tool-call override 都被忽略，关掉 `dangerouslyDisableSandbox: true` 静默绕过用户严格 sandbox 配置的漏洞。`aris doctor` 显示当前生效 sandbox 状态；bash tool schema 文档化 strict-mode 行为。**#232 DeepSeek 弃用同步** — `auto-review-loop-llm` SKILL.md + setup UI 从老的 `deepseek-chat` / `deepseek-reasoner` 改成 `deepseek-v4-flash` / `deepseek-v4-pro`（老 alias 2026-07-24 弃用；reasoner 模型 reject `tool_choice`）。**v0.4.10 codex audit 4 个 P1 follow-up**：P1.A Anthropic 流式 retry 改成基于 `has_emitted_meaningful_content`（不是裸 `events_emitted`），只发了 `MessageStart` 就 EOF 也可 retry；P1.B `supports_reasoning_effort` 用 word-boundary 匹配让 `openai/o3-mini` / `proxy:o4` provider-prefixed 名字也走 reasoning-effort 路径（reviewer 镜像 `tools/lib.rs` 同步改）；P1.C `stream_options.include_usage` proxy fallback —— 真的 400 报 `stream_options` 是 unknown field 时 retry 一次去掉这个字段；P2 pricing 用新 `provider_match` helper 让 `qwen3.6-plus` / `kimi-k2.5` / `glm-4-plus` 走对 tier，同时拒绝 `my-kimi-clone` 这种 mid-word 误判。**Skills 追新**：嵌入 `/interview-cheatsheet` + `/render-html`（共 76 skills，52 helpers；`build.rs` `ALLOWED_EXTS` 加 `html` 让 render-html templates 能嵌入）。**v0.4.11 follow-up**：`EXCLUDED_SKILL_PREFIXES` exact list → `starts_with("skills-codex")`；CI workflow `fetch-depth: 0` 让 drift-test ancestor check 真生效。全程 Codex MCP（gpt-5.5 xhigh）4 轮 review（GO-WITH-CAUTION + 8 个 finding → GO-WITH-CAUTION + 3 个精度 finding → NO-GO + 5 个 blocker → 修完 GO）。

> **v0.4.11** (2026-05-18) — **Skills 包刷新 / research workflow 同步 release**。Binary runtime 行为相对 v0.4.10 基本不变；嵌入的 skill 集合追上 `main` 当前状态。**新嵌入 10 个 skill**：`/citation-audit`（第四层文献审计：存在性 + metadata + 引用 context 覆盖）+ `/experiment-queue`（SSH 多 seed 任务队列，含 OOM retry + 残留 screen 清理）+ `/kill-argument`（理论论文双线对抗审）+ `/resubmit-pipeline`（W5：纯文本换会议投稿，含 kill-argument 门）+ `/paper-talk`（端到端 conference talk pipeline）+ `/slides-polish`（逐页 Codex 排版审）+ `/overleaf-sync`（通过 Git bridge 双向同步 Overleaf，token 走 Keychain）+ `/gemini-search` + `/openalex`（更广文献源）+ `/qzcli`（启智平台 GPU 任务管理）。**46 个已有 SKILL.md 刷新** —— 最重要的是 canonical resolver chain 全面铺开（修复真实用户事故：research-wiki 因硬编码 `tools/research_wiki.py` 空了一周）+ submission assurance gate + external verifier 上线（paper-writing Phase 6 现在能跑通）+ proof-checker `--restatement-check` / `--deep-fix` opt-in flag。**Helpers**：tools/ 9 → 18 个；`research_wiki.py` 从 315 行刷到 767 行（含 canonical `ingest_paper` API；否则 SKILL.md 调的 API 在 bundle 里不存在）。**Sync 基础设施**：`tools/sync_main_skills.sh` 自动化 main → bundle rsync（含 symlink 前置检测 + codex-mirror prune + `SKILLS_SOURCE_COMMIT` 钉版本）；3 个新 CI drift test 覆盖全部 4 个 resolver layer pattern。**Gemini MCP** 在 `/research-lit` 改成 `model: 'auto-gemini-3'`。全程 Codex MCP（gpt-5.5 xhigh）4 轮交叉评审。

> **v0.4.10** (2026-05-17) — **流式 + MCP 可靠性 release**。**C6**（关闭 `#228` 那条 "error decoding response body" 中流报错循环）：Anthropic `MessageStream` 和 OpenAI SSE 循环均支持 chunk decode 失败 / 早 EOF 时整段重启请求（`ARIS_STREAM_RETRY`，默认 2，clamp 0..=5，只在尚未输出任何内容时触发，输出不会撕裂）。**M3**（关闭 `#151` / `#172` "Calling codex..." 卡死）：MCP stdio `request()` 加 300s 默认超时同时覆盖 send + read（env `MCP_REQUEST_TIMEOUT_SECS` 覆盖，clamp 1..=1800）；`response.id ↔ request.id` 关联校验；`ensure_server_ready()` 用 `try_wait()` 检测进程死亡并透明 respawn；任何失败路径都 `kill().await` 回收子进程让下次调用从干净状态开始。新增 3 个 MCP regression test。**C8/P4**：OpenAI 流式请求体加 `stream_options.include_usage: true`，解析 `prompt_tokens_details.cached_tokens` → `cache_read_input_tokens`；Anthropic `MessageStart.usage`（含 input + cache 两半）和 `MessageDelta.usage`（含 output）合并，让 post-compaction cache 命中率显示真实数字。**C9** 多 provider 计费：GPT-5.5/5.4/o1/o3/o4（cache_read = input × 0.1，OpenAI 实际 prefix-cache 折扣——此前 generic 50% 高估了 5 倍）、Gemini 2.5/2.0、DeepSeek V3/V4/R1（区分 cache_hit / cache_miss）、GLM、MiniMax、Kimi/Moonshot、MiMo、Qwen、Doubao；`has_word()` 边界匹配让 `openai/o3-mini` / `provider/<model>` 正确路由 tier。**清理**：9 个 dead-code warning 修复，`aris setup` help 文案 + doctor 字符串与实际行为同步，对 v0.4.10 触及的 7 个文件跑 `cargo fmt`。全程 Codex MCP（gpt-5.5 xhigh）交叉评审。

> **v0.4.9** (2026-05-17) — **关闭 Codex v0.4.7 audit 残留 (L1+L3+L4)** + skill-helper 子系统收尾。**L1**：`tools` crate 也切到 `native-tls`，三个 reqwest 消费者 TLS 统一（DashScope 类 endpoint 走 LlmReview reviewer path 也能用了，不只是主 executor）。Linux CI 装 OpenSSL dev headers。**L3**：ApiClient trait 加 `on_session_compacted()`；OpenAI message-index-keyed reasoning_cache 在 auto-compaction 后清空，post-compaction replay 不再 aim 错误 index。**L4**：拆 `supports_reasoning_content_replay` predicate（超集含 Kimi/Moonshot/Xiaomi-MiMo/DeepSeek-R1 — 这些 emit reasoning_content 但不接受 reasoning_effort）+ 32K char 单 turn cap + 128K char 总 cache cap（oldest-eviction）。另：2 个新 skill 嵌入（`/figure-spec` + `/paper-illustration-image2` 含 `scripts/` 子目录，新 resolver Layer 0b = `$ARIS_CACHE_DIR/skills/<name>/scripts/`）；`research_wiki.py` 从 skill-local 提升到 shared `tools/`（9+ 调用方）；5 个 SKILL.md 迁移到 fallback chain（`exa-search`, `semantic-scholar`, `arxiv`, `idea-creator`）；inventory cargo test + smoke shell 脚本防 H6 regression。

> **v0.4.8** (2026-05-17) — **Skill helper 子系统重写** + **两个社区 bug 修复**。Bundled helper 现在 startup 时提取到 `~/.config/aris/cache/<version>/`（而不是 cwd）；每次 Skill 调用都会输出 `helperReport`（含 cache dir + 4 层 resolver preamble）。`/skills export` 一并导出 helper。新 `integration-contract.md` 定义 6 个失败策略（A gate / B side-effect / C forensic / D1 cascade / D2 multi-source / E diagnostic）。8 个 shared helper（arxiv/deepxiv/exa/S2/openalex fetcher + save_trace + verify_papers + verify_paper_audits）嵌入二进制。`/research-lit` + `/deepxiv` SKILL.md 迁移到 fallback chain。修复：(a) `gpt-5.5 + tools` 在 OpenAI 400 错误（gpt-5.5/o3/o4 + tools 时剥离 `reasoning_effort`），(b) Custom reviewer 每次启动变 gpt-5.5（`/setup` 菜单选项 9 vs 8 bug + `LlmReview` 不再为 Custom fallback gpt-5.5）。

> **v0.4.7** (2026-05-16) — **DashScope Coding Plan 405 修复**（#159）通过 `native-tls` 切换 — 贡献者 [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#225) | **所有 reasoning model 的 `reasoning_content` replay**（OpenAI o1/o3/o4、DeepSeek-R1 等），不再只是 Kimi — 配合 v0.4.5 `reasoning_effort='xhigh'` 让多轮 reasoning 对话连贯 — 贡献者 [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#226) | 清理：删除 600+ 行 `rusty-claude-cli` 原型死代码（`app.rs` / `args.rs` / `runtime/sse.rs`）+ 未使用的 `rustyline` 依赖 + 用户面 "Claw Code" → "ARIS-Code" 品牌统一。

> **v0.4.6** (2026-05-14) — **🚨 两个长期静默 bug 修复**：(1) `PermissionMode::Prompt` 因 derived-`Ord` 顺序错误**一直在静默放过所有 tool 调用**（用户选"问我"实际等同直接 allow），现在正确路由到 prompter；(2) system prompt 写死 `current_date = "2026-03-31"`，导致 model 把 2026-03 之后所有真实数据（包括用户自己的 arXiv 论文）都判为"未来 / prompt injection"——现在用 `runtime::today_iso()` 真实系统时间。另外 **Custom OpenAI 兼容 provider**（`/setup` 选项 11，reviewer 选项 9）+ dynamic `/models` 自动发现 — 贡献者 [@Anduin9527](https://github.com/Anduin9527) (#221 + #222)。

> **v0.4.5** (2026-05-13) — **推理模型一等公民支持** — `reasoning_effort='xhigh'` 真正发到请求体（GPT-5.5 / o1 / o3 / o4 / DeepSeek-thinking）| **Thinking content blocks** 全链路打通（修 #161 unknown variant + 400 Bad Request）| **多 tool result 合并** 修复（`tool_use_ids_without_tool_result` 并发 tool 错）| **DeepSeek V4 Pro** + **Xiaomi MiMo** + **Qwen 3.6** + **Doubao** 加入 `/setup`（选项 7-10）| **Claude Code 对象式 hooks** 解析器 | 默认模型升级到 **Claude Opus 4.7 + GPT-5.5** | REPL 输入加固：折行不再无限复制 / Cmd+V 多行粘贴不再每行 auto-submit / CJK 字符在折行边界正确渲染 | 新增 CI workflow | 贡献者: [@GO-player-hhy](https://github.com/GO-player-hhy) (#186), [@Jxy-yxJ](https://github.com/Jxy-yxJ) (#171), [@GetIT-Sunday](https://github.com/GetIT-Sunday) (#216 部分)

> **v0.4.4** (2026-04-20) — **`/setup` 配 Claude 中转站不再强制走 Bearer**(修 ModelScope / newcli.com 等只认 x-api-key 的代理) | `/setup` 加入常用第三方代理 URL 提示(OpenRouter / DeepSeek / DashScope / ModelScope 等) | Provider 切换时清干净残留 state | 自定义 base URL 不再被 `/setup` 二次覆盖 | LlmReview executor 猜错 model 时自动 fallback 到配置的 reviewer | 修复 #158 / #162

> **v0.4.3** (2026-04-17) — **第三方 Anthropic-compat 代理(Bedrock 等)支持** — 跳过代理不认的 beta flag | `anthropic` provider 也正确传播自定义 base URL(之前只有 `anthropic-compat`) | 贡献者 [@screw-44](https://github.com/screw-44)

> **v0.4.2** (2026-04-17) — **Auto-compaction 崩溃修复**(skill 跑完后的空响应问题) | OpenAI-compat executor 下 compaction 摘要不再丢失 | 自定义 executor base URL 启动 setup 后生效 | shell 预设 API key 不再被清掉 | `EXECUTOR_BASE_URL` trim + 空值处理

> **v0.4.1** (2026-04-15) — Reviewer/Executor 自动重试 (429/5xx/网络抖动) | Ctrl+C 后标志污染修复 | 每次 reviewer 请求新 HTTP client(绕过坏连接池) | 详细错误链
>
> **v0.4.0** (2026-04-15) — **Plan 模式** (`/plan`) | Ctrl+C 协作式中断(不再直接退出) | API 错误不再退出 REPL | 工具输出折叠 | 同步 62 个 skills
>
> <details><summary>历史版本</summary>
>
> **v0.3.9** (2026-04-11) — 代理/自定义 base URL | 本地模型 (LM Studio/Ollama) | Research Wiki | 自进化 Meta-Optimize | Session 原子写入 | Bash 安全校验 | Windows (experimental)
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

## 🔌 MCP servers

> ✅ **v0.4.17 起正式可用**：`settings.json` 中配置的 stdio MCP server
> 会在启动时被 spawn,其工具以 `mcp__<server>__<tool>` 广告给模型,
> 调用端到端分发 —— Anthropic 与 OpenAI-family executor 两条路径都支持。

```jsonc
// <config_home>/settings.json（config_home = $CLAUDE_CONFIG_HOME 或 ~/.claude）
{
  "mcpServers": {
    "codex": {
      "type": "stdio",
      "command": "codex",
      "args": ["mcp-server"],
      "trust": true,              // 可选:跳过逐次确认
      "requestTimeoutSecs": 240   // 可选:per-server 超时
    }
  }
}
```

最简单的配置方式是 `aris setup` → reviewer 选项 10(Codex MCP),
它会自动写好这个条目。注意:

- MCP server 是 **sandbox 管不到的外部进程** —— 未受信的 MCP 工具每次
  调用都会弹确认(即使 `danger-full-access`),直到你设 `trust: true`
  或在会话内选"本 server 不再问"。
- 启动失败的 server 会被跳过并警告,其余照常工作;`aris doctor` 显示
  逐 server 状态(spawn / initialize / 工具数 / 失败原因 / trust)。
- 传输层是 MCP spec 规定的 newline-delimited JSON-RPC;读侧仍兼容
  legacy `Content-Length:` 帧的 server。
- 新增 server 需要重启 `aris` 才会 spawn + 发现(适用时 ARIS 会提示)。
  本版 subagent 不携带 MCP 工具。

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

