# Manual Review MCP Server

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## What it does

A human-in-the-loop MCP server for ARIS cross-model review. Instead of calling Codex/GPT API automatically, it opens a browser page where you copy the review prompt to a **different** model family and paste the response back.

**Zero API cost. Works with any text model.**

## When to use

- You don't have a Codex/GPT Plus subscription
- You want to use free models (ChatGPT free tier, DeepSeek, Kimi, Gemini, etc.)
- You prefer to choose which model reviews each time
- You're on a budget but still want cross-model review quality

## Installation

```bash
# Register with Claude Code
claude mcp add manual-review -s user -- python3 /path/to/mcp-servers/manual-review/server.py

# Then use in any skill:
/auto-review-loop "topic" — reviewer: manual
/research-review "paper/" — reviewer: manual
```

## Modes

### Browser mode (default)

Opens a local web page. Works on Windows, macOS, and Linux with a desktop environment.

### File mode (headless Linux)

For SSH/headless environments without a browser:

```bash
export MANUAL_REVIEW_MODE=file
```

The server writes the prompt to a per-thread directory with a **cross-model warning** at the top of `prompt.md`. Read `.aris/pending_review/pending_review.json` — the `prompt_file` field tells you where to read the prompt, the `response_file` field tells you where to write the model's response. The file must be non-empty and stable (unchanged across two reads) before it's accepted.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MANUAL_REVIEW_SERVER_NAME` | `manual-review` | MCP server name |
| `MANUAL_REVIEW_TIMEOUT_SEC` | `86400` (24h) | Max wait time for response |
| `MANUAL_REVIEW_MODE` | `browser` | `browser` or `file` |
| `MANUAL_REVIEW_AUTO_OPEN` | `true` | Auto-open browser on review |
| `MANUAL_REVIEW_PORT` | `17900` | Fixed HTTP port (increments if occupied) |
| `MANUAL_REVIEW_PENDING_DIR` | `.aris/pending_review` | Directory for state/prompt/response files |
| `MANUAL_REVIEW_DEBUG_LOG` | (empty) | Debug log file path |

## Recovery

If you accidentally close the browser tab, open `.aris/pending_review/pending_review.json` and reopen the exact `url` value. It includes a one-session token — copy it in full (e.g., `http://127.0.0.1:17900?token=abc123`). Do not type the bare `http://127.0.0.1:17900` as it will return 403.

## Future Work

- Image generation support (manual alternative to `codex-image2`)
- Image review loop for paper illustrations

---

<a id="中文"></a>

## 功能说明

ARIS 跨模型评审的人工中转 MCP 服务器。不自动调用 Codex/GPT API，而是打开浏览器页面，让你将评审提示词复制到**不同**模型家族，再将回复粘贴回来。

**零 API 成本。支持任何文本模型。**

## 适用场景

- 没有 Codex/GPT Plus 订阅
- 想使用免费模型（ChatGPT 免费版、DeepSeek、Kimi、Gemini 等）
- 希望每次自行选择评审模型
- 预算有限但仍想获得跨模型评审质量

## 安装

```bash
# 注册到 Claude Code
claude mcp add manual-review -s user -- python3 /path/to/mcp-servers/manual-review/server.py

# 在任意技能中使用：
/auto-review-loop "topic" — reviewer: manual
/research-review "paper/" — reviewer: manual
```

## 模式

### 浏览器模式（默认）

打开本地网页。适用于 Windows、macOS 和有桌面环境的 Linux。

### 文件模式（无桌面 Linux）

适用于 SSH/无桌面环境：

```bash
export MANUAL_REVIEW_MODE=file
```

服务器将提示词写入按线程隔离的子目录，`prompt.md` 顶部包含**跨模型警告**。读取 `.aris/pending_review/pending_review.json` — `prompt_file` 字段指向提示词文件，`response_file` 字段指向你应写入回复的位置。文件必须非空且稳定（两次读取内容不变）才会被接受。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MANUAL_REVIEW_SERVER_NAME` | `manual-review` | MCP 服务器名称 |
| `MANUAL_REVIEW_TIMEOUT_SEC` | `86400`（24h） | 最大等待时间 |
| `MANUAL_REVIEW_MODE` | `browser` | `browser` 或 `file` |
| `MANUAL_REVIEW_AUTO_OPEN` | `true` | 是否自动打开浏览器 |
| `MANUAL_REVIEW_PORT` | `17900` | 固定 HTTP 端口（被占用时递增） |
| `MANUAL_REVIEW_PENDING_DIR` | `.aris/pending_review` | 状态/提示词/回复文件目录 |
| `MANUAL_REVIEW_DEBUG_LOG` | （空） | 调试日志文件路径 |

## 恢复

如果不小心关闭了浏览器标签，打开 `.aris/pending_review/pending_review.json`，复制完整的 `url` 值（包含一次性 token，如 `http://127.0.0.1:17900?token=abc123`）重新打开。不要手动输入裸地址 `http://127.0.0.1:17900`，会返回 403。

## 后续计划

- 图片生成支持（`codex-image2` 的手动替代方案）
- 论文插图的图片评审循环
