# ARIS on DeepSeek Harness

[English](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/dsh-aris#readme) | 中文

> 这是 `dsh-aris` 发行分支。完整的 ARIS 项目——全部工作流、文档、其他宿主的适配——在 [`main`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 上。

在 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 里跑 ARIS 研究工作流：82 个技能全部进入原生技能目录，审稿仍由 Codex 跨模型独立执行。

技能文件零改动。这个 bundle 只是一层配置加一个简短适配器——不打补丁改 Harness 代码，也不 fork。

## 安装

```sh
dsh plugin --profile web add dsh-aris
```

装完重启 profile。插件代码在启动时加载，只刷新页面不够。

`dsh plugin` 会调用 **pnpm**，而 Harness 不自带它。PATH 上没有 pnpm，安装会直接退出、什么都不做。

## 前置条件

**已安装并登录的 Codex CLI。** 它就是那位独立审稿人。本 bundle 启动 `codex mcp-server`，且从不覆盖它的模型和推理档位——**`~/.codex/config.toml` 就是审稿人姿态契约**。ARIS 要求非 DeepSeek 家族、xhigh 档：

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
```

Codex 起不来时，Harness 直接启动失败，而不是跑一个没有审稿人的组合。这是刻意的：**没有独立审稿人的 ARIS 不是 ARIS**。

**一个 DeepSeek API key**，通过 Harness 的 Models 页面或 `DEEPSEEK_API_KEY` 提供。

**走 HTTP 代理时**，启动 Harness 要带 `NODE_USE_ENV_PROXY=1`。否则 Node 的 fetch 不认 `http_proxy`，模型请求会以 `TRANSPORT` 失败。这个变量必须在 Node 启动时就存在，配置层补不回来。

**可选——把执行者也管住。** ARIS 的审稿人自带作用域限制：那段禁止提议哈希、禁止防御性脚手架、禁止 corner-case 加固、禁止把判断过度机械化的文本，**内嵌在会产出审查 prompt 的技能里，零配置生效**。但没有任何东西以同样方式约束**执行者**。补上有两条路，而且它们不是一回事：

- **ARIS 自己的红线，一个开关。** `aris-scope-limits` 这一行随包提供但默认关闭；在你 profile 的 patch 里写 `disabled: false` 就把同一段文本应用到执行者。它在加载时读取包内的 `skills/shared-references/review-scope-limits.md`，所以**审阅者那条路和执行者这条路不可能漂移**。默认关闭是因为它在每个请求上都花 token。
- **完整的 [HERO](https://github.com/wanshuiyin/HERO-Anti-OverDefense) 契约。** 把它的规范块粘进项目的 `AGENTS.md` 或 `CLAUDE.md`，或粘进 `$DSH_HOME/AGENTS.md` 覆盖所有 dsh 项目——Harness 自己会加载这些文件。本 bundle **不 vendor HERO 的文本**，它的正典在 HERO 自己的 `RULES.md` 里。

## 验证

```sh
dsh --profile web --dump-config | grep -A2 aris-
```

然后在会话里敲 `/`，技能菜单会列出 ARIS 技能。要验最关键的那一环：让模型用一个简单 prompt 调 `mcp__codex__codex`，报出它看到的 `threadId`，再用 `mcp__codex__codex-reply` 续接一次。**能看见 `threadId`，多轮审稿才成立。**

## ARIS 标签页

Web UI 的会话里会在「对话」「轨迹」旁边多出一个 **ARIS** 标签页。它是只读的：只呈现审稿人和循环自身产物说了什么，**不写入、不推进轮次、不把分数转成完成判断**。

它读的是会话工作区里的 `review-stage/REVIEW_STATE.json`，所以在该目录跑完第一轮 `auto-review-loop` 之前是空的。

最上面那一栏就是这个标签页存在的理由：**这一轮是谁审的**，以及 ARIS 能否确认审稿人与执行者属于不同的模型家族。走 Codex 后端时这一项**按设计就是 `unverified`**——Codex 能报告自己是谁，但没有任何东西独立证明执行者是谁，所以 ARIS 记为 `identity_assurance: caller_declared`。读作"路由一致，但未获认证"。

标签页里还常驻两条诚实边界，值得在此重复：状态是**每轮结束时写入**、不是持续更新，所以长轮次期间显示的是上一轮；`completed` 只表示**循环结束**——正面结论**或**跑满轮次——**绝不表示工作已通过**。

## 这一层改了什么

| 配置行 | 作用 |
|---|---|
| `agent-default-model` | 执行者换成 `deepseek-v4-pro` |
| `aris-skills` | 挂载 82 个技能、发布 `ARIS_REPO`、补回 Codex 的 `threadId`、提供 ARIS 标签页 |
| `aris-codex` | 经 MCP 接入 `codex mcp-server`，单次调用预算 20 分钟，工作目录钉死在稳定位置 |

技能语料挂在 bundled 档（最低优先级），所以项目级或用户级的同名技能永远优先。执行者模型是部署默认值而非锁定值：已保存的模型设置或会话内选择都会覆盖它。

## 基于 clone 开发

```sh
ARIS_REPO=/absolute/path/to/aris NODE_USE_ENV_PROXY=1 \
  dsh --profile web --patch /absolute/path/to/aris/dsh/checkout.patch.yml
```

改技能即时生效，不用重启。`ARIS_REPO` 是必需的，没设会以指名该变量的报错终止加载。

这个 overlay **不等价于**已安装的 bundle：它补不回 Codex 的 `threadId`，所以多轮 `codex-reply`（因而 hard 档的 Debate Protocol）只有装包才可用。两者互斥：对已装 bundle 的 profile 再叠这个 overlay，会因为配置行 id 重复而失败——去掉其中一个。

## 已知限制

- **跟随某一个 Harness 版本。** DeepSeek Harness 处于技术预览；本 bundle 已针对 `0.1.0-rc.8` 验证。它用到的每一个接口面从 rc.5 到 rc.8 都未变，但这不构成对下一个版本的承诺。
- **不把任何 dsh 包声明为 npm 依赖。** 内置包由宿主提供，通过 profile 的模块回退从 Harness 安装目录解析。Harness 自己的规约就要求 `@deepseek-ai/dsh-*` 不进 `dependencies`；而且这些子包与 CLI **锁步发版**，本 bundle 无论钉哪个范围，都会和用户已装的版本打架。
- **`web_fetch` 关闭。** 原版 dsh 默认关闭它，本 bundle 也不打开——打开就意味着依赖一个 provider 包。需要联网的技能改用 `web_search`，或用 `bash` 跑 `curl`。
- **审稿线程连续性是进程内的。** Harness 重启、或任何一次 MCP 重连替换了 Codex 子进程，已保存的 `threadId` 都会失效，之后的轮次从新线程开始；无论如何 `review-stage/REVIEWER_MEMORY.md` 都是持久记录。
- **Codex 自己的推理过程不进 Harness 日志。** 返回的只有判词。调用参数和判词都会落日志，审稿人的中间工作留在 Codex 那侧。
- **超过 50 KB 的判词会被落盘**，上下文里只留预览。审稿普遍很长的话，调高 `spill-policy` 行的 `maxInlineBytes`。
