# Grok CLI → MCP 桥接

这个桥接沿用相邻 `codex-exec/server.py` 的 stdio、进度通知、取消和会话记录设计，改用 Grok CLI 的 headless 模式。提供 `grok` 和 `grok-reply`，返回结构保留 `threadId` / `content`。Python 3.9+，无需第三方 Python 依赖。

默认模型为 `grok-4.7`、推理强度为 `xhigh`。在 Grok CLI 1.0.46 上实测，服务返回的模型名是 `grok-4.7-build`，首次调用和续接的会话摘要均记录 `reasoning_effort: xhigh`。CLI 显示名、请求名和服务返回名可能不同，因此返回值分别记录请求值与实际值。

## 注册

先安装 Grok CLI 并完成 `grok login`。桥接使用 CLI 已有的登录状态，不复制认证 token，也不需要另外填 API key。

Claude Code（将路径换成自己的 ARIS 仓库绝对路径）：

```bash
claude mcp add grok -s user -- python3 /absolute/path/to/aris/mcp-servers/grok-exec/server.py
```

Codex：

```bash
codex mcp add grok --env GROK_BIN=/absolute/path/to/grok -- python3 /absolute/path/to/aris/mcp-servers/grok-exec/server.py
```

在 Codex 的 `~/.codex/config.toml` 中给已有的 `[mcp_servers.grok]` 表补上 `tool_timeout_sec = 3660`。桥接自身默认 3600 秒超时，宿主需要留出取消与清理时间；进度通知不保证延长宿主期限。[Codex MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。其他客户端也应设置相应的工具调用超时。

重新启动 MCP 客户端后检查工具列表。这个独立服务不自动修改 ARIS skills 的 reviewer 路由；需要使用 Grok 时显式调用它。一次连通性测试不等于一次研究评审通过。

## 调用

首次调用：

```json
{
  "name": "grok",
  "arguments": {
    "prompt": "请读取指定文件并审阅，指出有证据支持的问题。",
    "cwd": "/absolute/path/to/project",
    "model": "grok-4.7",
    "effort": "xhigh"
  }
}
```

续接同一会话：

```json
{
  "name": "grok-reply",
  "arguments": {
    "threadId": "首次调用返回的 UUID",
    "prompt": "我修改了这些文件，请继续检查。"
  }
}
```

`grok-reply` 使用 Grok 的原生 `--resume`，并显式重传首次调用的模型、effort、cwd、sandbox、工具集合和轮次上限。桥接重启后仍从保存的会话设置恢复；续接调用不能改这些参数。未知会话 ID 会报错，需要新建会话。

| 参数 | 默认值 | 含义 |
|---|---|---|
| `model` | `grok-4.7` | Grok CLI 接受的模型名 |
| `effort` | `xhigh` | `low` / `medium` / `high` / `xhigh` |
| `cwd` | MCP 服务启动目录 | 建议明确指定实际项目目录 |
| `sandbox` | `read-only` | Grok 原生 `read-only` / `workspace` / `strict` / `off` |
| `tools` | `read_file,grep,list_dir` | Grok 原生工具 ID；空字符串禁用内置工具 |
| `max_turns` | `50` | 单次调用允许的最大轮数 |

默认是文件审阅用途：内置工具只开读取、搜索、列目录；关闭子代理、网页搜索和计划模式，禁止 MCP meta-tools。权限模式为 `dontAsk`，无需等待交互确认。sandbox 由 Grok CLI 实施，其操作系统支持和网络限制以 CLI 文档为准；不能把这个参数视为所有平台都具备同等强度的隔离保证。

成功结果的 `structuredContent` 包含：

```json
{
  "threadId": "...",
  "content": "最终回复",
  "model": "grok-4.7-build",
  "effort": "xhigh",
  "stopReason": "end_turn",
  "requestedModel": "grok-4.7",
  "requestedEffort": "xhigh"
}
```

`effort` 从该 Grok 会话的 `summary.json` 读取；摘要不可用时返回 `null`，不会拿请求值冒充实际值。实际 effort 与请求不一致时，调用标为错误。`model` 取 CLI 返回的模型信息。

## 执行与失败处理

- 长提示词通过权限为 `0600` 的临时文件传入，调用结束后删除；不经过 shell 插值。
- 转发原生事件为 `grok/event`。客户端提供 progress token 时，默认每 15 秒发送心跳；等待模型期间仍可响应 ping 和取消。
- CLI 失败、结果截断、轮次用完、缺失最终结果或非零退出码均返回 `isError: true`，不把半截回答当成正常审阅。
- 超时、客户端取消或 stdin 关闭时，回收子进程；POSIX 上清理进程组。取消后仍不退出的子进程会被强制终止。
- 桥接不自动重新发起工具调用。底层 Grok CLI 可能进行内部网络重试（已观察到最多15次）；连通性探测建议用 `GROK_EXEC_TIMEOUT_SEC=75` 限制时长。会话设置记录与 Grok 原生会话共同用于续接。
- 每个服务进程顺序执行调用。排队期间收到取消通知的请求不会启动 Grok。此版本只验证了单会话首轮、续接及故障处理，未做高并发或长时间配额测试。

环境变量：

| 变量 | 默认值 |
|---|---|
| `GROK_BIN` | PATH 中的 `grok` |
| `GROK_EXEC_MODEL` | `grok-4.7` |
| `GROK_EXEC_EFFORT` | `xhigh` |
| `GROK_EXEC_TIMEOUT_SEC` | `3600` |
| `GROK_EXEC_PROGRESS_INTERVAL_SEC` | `15` |
| `GROK_EXEC_STATE_DIR` | `~/.codex/state/grok-exec` |
| `GROK_EXEC_DEBUG_LOG` | 不启用 |

桥接沿用 CLI 的 `GROK_HOME` 来定位会话摘要；未设置时是 `~/.grok`。调试日志记录 RPC 方法与命令参数，不记录提示词正文；原生 Grok 会话仍按 CLI 自己的策略落盘。

## 验证

无需网络或 Grok 账号的协议回归测试：

```bash
python3 -m unittest discover -s tests -p 'test_grok_exec_bridge.py' -v
```

2026-10-05 在 macOS、Grok CLI 1.0.46 上完成真实验证：直接 headless 调用成功；通过 MCP 读取合成文件，再用 `grok-reply` 回忆其中随机 token 成功，两个回合实际均为 `grok-4.7-build` / `xhigh`，两轮合计约 21 秒。没有据此宣称 headless 已启用 500k 上下文，或已验证复杂研究审阅质量。

## 排查模型列表获取失败

2026-10-05 另一次调用出现 `unknown model id`，当时只列出 `grok-4.6` / `grok-4.5`。本机 CLI 日志同时记录 `had_real_catalog=false`、`model_count=2` 和 `model catalog refresh failed`；之后模型目录刷新成功，恢复4项（包含4.7），同一桥接再次返回真实的 `grok-4.7-build` / `xhigh` 回复。

因此，这种报错需要先核对 `grok models`、`~/.grok/models_cache.json` 的更新时间、`~/.grok/logs/unified.jsonl` 中的目录刷新结果，以及 CLI 路径、`GROK_HOME` 和宿主网络权限。后续同机对照确认，旧 MCP 子进程没有继承代理变量，直接连接报 `No route to host`，经本机已有代理可到达服务；这解释了该机器上的主要连接失败。遵循宿主审批流程取得所需访问，不关闭权限保护；不静默改用其他模型，不自动重试推理请求。日志与配置排查时不输出认证 token。

### MCP 启动环境与代理

从应用启动的 MCP 服务不一定继承终端登录 shell 的代理。2026-10-05 的故障通过给本机 Codex 注册项显式补入 `http_proxy` / `https_proxy` 修复；清除 shell 继承代理、只使用注册 env 的首轮与续接均返回 `grok-4.7-build` / `xhigh`。如果你的网络依赖代理，在 `[mcp_servers.grok.env]` 使用你实际可达的代理地址，并重启 MCP 服务；不要把本机地址硬编码到共享桥接源码。

另一个受限会话连本地代理也被阻断，且宿主拒绝提权/停止进程。配置代理不能解除宿主沙箱限制，应按宿主权限流程处理；不能通过关闭隔离或换模型绕过。探测设置短超时；清理时核对准确的 session ID 与独立进程组，不误杀用户的 Grok 交互窗口。
