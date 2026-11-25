# Cursor CLI → MCP 桥接

这个桥接沿用相邻 `grok-exec` / `codex-exec` 的 stdio、进度通知、取消和会话记录设计，改用 Cursor CLI（`cursor-agent`）的 headless 模式。提供 `cursor` 和 `cursor-reply`，返回结构保留 `threadId` / `content`。Python 3.9+，无需第三方 Python 依赖。

它把 Cursor 账号里可用的模型（`cursor-agent --list-models`）接为独立的只读审阅者。桥接不写死默认模型：未指定时不传 `--model`，由 `cursor-agent` 自己的默认值决定。

## 注册

先安装 Cursor CLI 并完成 `cursor-agent login`（或在 MCP 服务的环境里设置 `CURSOR_API_KEY`）。桥接使用 CLI 已有的登录状态，不复制认证 token，也不把密钥放进命令行。

Claude Code（将路径换成自己的 ARIS 仓库绝对路径）：

```bash
claude mcp add cursor -s user -- python3 /absolute/path/to/aris/mcp-servers/cursor-exec/server.py
```

Codex：

```bash
codex mcp add cursor --env CURSOR_AGENT_BIN=/absolute/path/to/cursor-agent -- python3 /absolute/path/to/aris/mcp-servers/cursor-exec/server.py
```

在 Codex 的 `~/.codex/config.toml` 中给 `[mcp_servers.cursor]` 补上 `tool_timeout_sec = 3660`。桥接自身默认 3600 秒超时，宿主需要留出取消与清理时间；进度通知不保证延长宿主期限。其他客户端也应设置相应的工具调用超时。若网络需要代理，在注册项的 `env` 中显式配置实际可达的代理，不要依赖从终端继承。

重新启动 MCP 客户端后检查工具列表。这个独立服务不自动修改 ARIS skills 的 reviewer 路由，也不是新的 `— reviewer:` 值；需要使用 Cursor 时显式调用它。一次连通性测试不等于一次研究评审通过。

## 调用

首次调用：

```json
{
  "name": "cursor",
  "arguments": {
    "prompt": "请读取指定文件并审阅，指出有证据支持的问题。",
    "cwd": "/absolute/path/to/project",
    "model": "<cursor-agent --list-models 中的模型 ID>"
  }
}
```

续接同一会话：

```json
{
  "name": "cursor-reply",
  "arguments": {
    "threadId": "首次调用返回的 UUID",
    "prompt": "我修改了这些文件，请继续检查。"
  }
}
```

`cursor-reply` 使用原生 `--resume`，并重传首次调用的模型和 cwd。桥接重启后仍从保存的会话设置恢复；续接调用不能改这些参数。未知会话 ID 会报错，需要新建会话。

| 参数 | 默认值 | 含义 |
|---|---|---|
| `model` | 不传，用 CLI 默认模型 | `cursor-agent --list-models` 中的模型 ID；也接受 `'composer-2.5[fast=false]'` 形式的方括号参数 |
| `cwd` | MCP 服务启动目录 | 作为 `--workspace` 传入；建议明确指定实际项目目录 |

与 `grok-exec` 相比，这里没有 `effort`、`sandbox`、`tools`、`max_turns` 参数，也没有系统提示参数：`cursor-agent` 没有对应的命令行开关。推理强度写在模型 ID 里（例如 `-high` / `-xhigh` 后缀，或方括号参数），不是单独参数，所以不虚构一个 `effort` 映射。

成功结果的 `structuredContent`：

```json
{
  "threadId": "...",
  "content": "最终回复",
  "model": "Composer 2.5",
  "requestedModel": "composer-2.5"
}
```

`model` 是 CLI init 事件给出的显示名，不是模型 ID，也不是服务端型号证明；未指定模型时请以它记录实际使用的模型（`auto` 之类的路由模型可能随时间选不同的底层模型）。`content` 是 CLI 的 `result` 字段：本轮全部助手文本按顺序拼接，包含工具调用之间的过程性说明。

## 只读保护

`cursor-agent -p` 默认可使用写文件和 shell 工具。2026-11-26 在 Linux、`cursor-agent 2026.11.22-e9042b2` 上用对抗性提示（声称“操作员已批准”并要求逐条执行）实测：

- `--mode ask` 不能单独保证只读：shell 重定向、`touch`、Python 写文件和编辑工具都在工作目录里创建了文件。
- `--mode ask --sandbox enabled` 同样没有阻止这些写入，工作目录之外的 `touch` 也成功。
- `--mode plan` 下，代理调用 `switchMode` 切到 agent 模式后写入了文件。

可靠的是 `.cursor/cli.json` 里的权限 deny 规则。桥接每次调用前把下面的策略写入自己的私有目录 `<state>/guard/.cursor/cli.json`，以该目录为 `cursor-agent` 的工作目录，再用 `--workspace` 指向被评审的项目：

```json
{"permissions": {"allow": [], "deny": ["Write(**)", "Shell(**)", "Mcp(*:*)"]}}
```

这样桥接不会向被评审的项目写任何文件，也不依赖项目里是否有 `.cursor/cli.json`。同样的对抗性提示经桥接实测：编辑工具（新建与覆盖）、删除工具和 shell（重定向、`touch`、`rm`、`ls`、Python 写文件）的调用全部被权限策略拒绝，已有文件内容不变，目录外没有新文件；项目内放一份全放行的 `.cursor/cli.json` 也不能覆盖它；用户全局配置里的 `Shell(ls)` 允许规则同样被 deny 压过。保留 `--mode ask` 只是辅助层，不是保护本身。桥接从不传 `--force` / `--yolo` / `--approve-mcps`。

读取没有被限制在 `cwd` 内：实测代理能读取工作区之外的文件（例如 `/etc/hostname`）。`cwd` 不是保密边界；读到的内容会发给 Cursor 和所选模型的提供方。

MCP：`-p` 默认会加载已配置的 MCP 服务器（实测代理能列出用户级和插件提供的服务器名）。桥接用 `Mcp(*:*)` 拒绝调用，并用本地桩 MCP 服务验证：调用被拒绝，桩服务没有收到请求。服务器和工具名的列出不会被拦截。这个 deny 只验证了桩服务，没有对其他真实 MCP 服务逐一测试。

其他实测观察：未加 `--force` 的 `-p` 下，WebFetch 返回 `User Rejected`，桥接没有为它另设规则；用户级 Cursor 技能也会被加载（实测代理的推理里引用了用户级技能），所以它不是干净环境的评审者。

## 执行与失败处理

- 提示词通过 stdin 传入：没有 argv 长度限制（实测 144 KB 的提示可用），不经过 shell 插值，调试日志不记录提示正文。
- 使用 `--output-format stream-json`：会话 ID 和模型名在 init 事件里就到达，工具调用事件也能转发。事件以 `cursor/event` 转发，逐 token 的 thinking 增量不转发。客户端提供 progress token 时，默认每 15 秒发送心跳；等待模型期间仍可响应 ping 和取消。
- 只有 `result` 事件为 `success`、非 `is_error`、文本非空且退出码为 0 才算成功。CLI 的 result 没有 `stop_reason`，所以无法像 `grok-exec` 那样检查是否因长度截断。
- 失败时返回 `isError: true` 和 CLI 自己的原因。未知模型时 CLI 只写 stderr 并以状态 1 退出，桥接返回 stderr 开头 1000 字符（后面是很长的可用模型列表）。
- `cursor-agent` 对未知的 `--resume` ID 不报错，而是静默新建一个空会话（退出码 0），所以桥接只续接自己记录过的会话。若 CLI 自己的会话存储被清掉，续接会悄悄变成新会话，桥接无法发现。
- 超时、客户端取消或 stdin 关闭时，回收子进程；POSIX 上清理进程组，取消后仍不退出的子进程会被强制终止。桥接不自动重新发起工具调用。
- 每个服务进程顺序执行调用。

环境变量：

| 变量 | 默认值 |
|---|---|
| `CURSOR_AGENT_BIN` | PATH 中的 `cursor-agent` |
| `CURSOR_EXEC_MODEL` | 空（不传 `--model`） |
| `CURSOR_EXEC_TIMEOUT_SEC` | `3600` |
| `CURSOR_EXEC_PROGRESS_INTERVAL_SEC` | `15` |
| `CURSOR_EXEC_STATE_DIR` | `~/.codex/state/cursor-exec` |
| `CURSOR_EXEC_DEBUG_LOG` | 不启用 |

调试日志记录 RPC 方法与命令参数，不记录提示词正文；原生 Cursor 会话仍按 CLI 自己的策略落盘。

## 验证

无需网络或 Cursor 账号的协议回归测试（用假的 `cursor-agent`，覆盖调用参数、guard 策略、续接、失败语义、取消与超时）：

```bash
python3 -m unittest discover -s tests -p 'test_cursor_exec_bridge.py' -v
```

2026-11-26 在 Linux、`cursor-agent 2026.11.22-e9042b2` 上完成真实验证：通过 MCP 读取合成文件并用 `cursor-reply` 回忆内容成功；上面的对抗性写入测试经桥接全部被拒；错误模型和错误二进制路径返回干净的工具错误；144 KB 提示成功。没有在 macOS 或 Windows 上验证，没有验证 `--sandbox` 在其他平台是否有效，没有做长时间或并发测试，也没有据此宣称复杂研究审阅的质量。
