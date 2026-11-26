# Antigravity CLI → MCP

使用已有 `agy` 登录，把 Gemini 3.8 Flash 接为独立 MCP。沿用同仓库 `codex-exec` / `grok-exec` 的 NDJSON、进度、取消和会话保存设计，Python 3.9+，无需第三方库。

默认模型 `gemini-3.8-flash-high`，effort `high`。提供 `antigravity` 和 `antigravity-reply`，作为独立工具使用，不修改 ARIS skills 的 reviewer 路由。

现有 [`gemini-review`](../gemini-review/README.md) 已有 API、Gemini CLI 和 `agy` 后端，提供 `review*` 工具供正式评审流程使用。本桥接提供显式 model/effort 与 CLI 原生 conversation 续接；工具名和会话契约不同。`— reviewer: agy` 和 Codex 的 Gemini overlay 仍走现有 `gemini-review`，不会因安装本桥接而切换。

## 安装

1. 安装 Antigravity CLI，运行 `agy` 登录；`agy models` 应包含目标模型。
2. 把同目录 `aris-antigravity-review.md` 复制到 `~/.gemini/config/agents/`。这是专供 MCP 选择的审阅 agent，不改变交互会话的默认 agent。
3. 注册 MCP，绝对路径替换为自己的安装位置：

```bash
codex mcp add antigravity --env AGY_BIN=/absolute/path/to/agy -- python3 /absolute/path/to/aris/mcp-servers/antigravity-exec/server.py
```

在 Codex `config.toml` 的 `[mcp_servers.antigravity]` 中设置 `tool_timeout_sec = 3660`。若本机网络需要代理，在该服务的 `env` 中显式配置实际可达的 `http_proxy` / `https_proxy`；不要依赖 GUI 启动时继承终端环境。

Claude Code 可另行注册：

```bash
claude mcp add antigravity -s user -- python3 /absolute/path/to/aris/mcp-servers/antigravity-exec/server.py
```

重启对应客户端后使用新工具。常驻 MCP 与 shell 内启动的独立探测具有不同的宿主权限；受限 shell 不能写 CLI 状态目录或连接代理，不代表常驻服务也失败，应使用宿主的正常审批流程处理。

## 调用

首轮：

```json
{"prompt":"请读取指定文件，回答这个问题。","cwd":"/absolute/path/to/project","model":"gemini-3.8-flash-high","effort":"high"}
```

续接 `antigravity-reply`：

```json
{"threadId":"首轮返回的 UUID","prompt":"请接着解释第二点。"}
```

续接只接受这两个字段，沿用首轮 model、effort、cwd 和审阅 agent。桥接重启后仍可恢复自己创建的会话；不用 `--continue`，避免串到其他交互会话。`threadId` 同时放在文本和 `structuredContent` 中。

返回的 `model` 来自 CLI 的 init 事件，`selectedModelLabel` 来自本轮 CLI 解析模型的日志；`effort` 从该实际选择的变体标签解析，注明 `effortSource=cli_selected_model_variant`。缺少记录时返回 null，不把请求值冒充实测值；这也不是独立的服务端型号证明。不支持的模型或 effort 交由 CLI 明确报错，不自动降级。

<a id="outbound-text-review"></a>

### 可选示例：发布前检查一段文字

例如，准备发布更新公告时，可以请 Gemini 找出读者容易误解的地方。先在调用方删去内部路径、账号等私有信息，只送允许发给外部模型并保存在会话记录里的片段。用新会话，把文案直接放进 `prompt`。为这次调用新建一个仅自己可访问的空目录作为 `cwd`（macOS/Linux 可运行 `mktemp -d /tmp/aris-review.XXXXXXXX`），将返回的路径填入下面的示例：

```json
{
  "cwd": "<刚创建的空目录的绝对路径>",
  "prompt": "请只检查下面这段文字，指出具体哪句话容易让读者误解，并给出改法。公告：新版从周五开始分批开放。周五起所有用户都可以使用。"
}
```

空目录让这次文字复核无需打开项目文件；文件访问权限仍由 CLI 控制。桥接会将完整提示写入临时文件 `prompt.jsonl`，正常结束时清理；CLI 自身可保留会话记录。结束会话后可用 `rmdir` 移除空目录。

这次复核只判断文案是否清楚。若需核实公告中的数字，仍按原任务读取证据。调用失败时记为 `REVIEW_UNAVAILABLE`；是否发布取决于原任务的授权和必需检查。

## 权限与执行

- 选择专用审阅 agent，其提示和工具声明限定文件读取与搜索；保留 CLI 原生权限检查，启用 `--sandbox`，不传跳过权限参数。CLI 1.2.17 的 init 仍列出完整工具目录，因此这里不宣称已验证所有写入被硬隔离。使用者应按现有 CLI 权限管理敏感工作区。
- 用一条 NDJSON stdin 传提示，避免长提示进入命令行；关闭 stdin 后 CLI 完成本轮并退出。临时输入与本轮日志留在私有目录，调用结束清除；CLI 自己的会话仍按原生方式保存。
- 接受完整 `SUCCESS`、非空回答和进程退出码0；ERROR、WAITING、取消、非零退出或缺失终态都返回 `isError`。
- 等待模型时响应 ping、进度与取消；超时或宿主断开会回收本次 CLI 进程组。桥接不自动重试模型调用。
- 每个服务进程顺序执行。排队期间收到取消通知的请求不会启动 Antigravity。CLI 的 `num_turns` 是累计用户回合，不是 Grok/Claude 的工具轮次上限；本桥接没有编造同名限制参数。

| 环境变量 | 默认值 |
|---|---|
| `AGY_BIN` | `agy` |
| `AGY_EXEC_MODEL` | `gemini-3.8-flash-high` |
| `AGY_EXEC_EFFORT` | `high` |
| `AGY_EXEC_TIMEOUT_SEC` | `3600` |
| `AGY_EXEC_PROGRESS_INTERVAL_SEC` | `15` |
| `AGY_EXEC_STATE_DIR` | `~/.codex/state/antigravity-exec` |
| `AGY_EXEC_DEBUG_LOG` | 不启用 |

探测用短超时，例如 `AGY_EXEC_TIMEOUT_SEC=90`；正常审阅保留较长超时。

## 验证

2026-10-05，macOS、Antigravity CLI 1.2.17：直接 headless 首轮与续接成功；真实 MCP 用 `view_file` 读取测试文件，重启桥接后用同一会话正确复述随机字符串，两轮约40秒，CLI 两轮均选择 `Gemini 3.8 Flash (High)`。该验证覆盖调用与续接，不代表复杂审阅质量或并发额度测试。

离线协议测试：

```bash
python3 -m unittest discover -s tests -p 'test_antigravity_exec_bridge.py' -v
```

8项用例覆盖协议、长输入、跨进程续接、错误终态、元数据缺失、取消和超时。Ruff、格式与 ty 检查通过。

接口依据：[Google headless 文档](https://www.antigravity.google/docs/cli/headless/)、[自定义 agent](https://www.antigravity.google/docs/subagents)、[Codex MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。
