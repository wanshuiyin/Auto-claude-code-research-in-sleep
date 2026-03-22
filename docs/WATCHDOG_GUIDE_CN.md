# Watchdog 监控指南

[English](WATCHDOG_GUIDE.md) | 中文版

> 服务器端持续监控 ARIS 实验 — 自动检测死掉的 session、停滞的下载和空闲的 GPU，无需手动轮询。

## 问题

ARIS 实验在远程 screen/tmux session 中运行。当前的监控（`/monitor-experiment`）是**按需的** — 你必须主动问"实验怎么样了"。在两次检查之间：

- 训练 session 可能静默崩溃（screen 死了、OOM kill）
- 下载可能卡住（网络超时、认证失败）
- GPU 可能空闲（训练结束或崩溃但 session 还在）

这些问题直到下次手动检查才会被发现，浪费数小时 GPU 时间。

## 方案：watchdog.py

一个轻量级 Python 守护进程，运行在每台 GPU 服务器上，持续监控所有注册的任务。零依赖（只需 Python 3 标准库 + `nvidia-smi`）。

**监控内容：**

| 任务类型 | 检查项 | 异常状态 |
|----------|--------|----------|
| `training` | Session 存活 + GPU 利用率 | `DEAD`（session 没了）、`IDLE`（GPU <5%） |
| `download` | Session 存活 + 文件大小增长 + 速度 | `DEAD`、`STALLED`（不增长）、`SLOW`（<1MB/s） |

**输出结构：**

```
/tmp/aris-watchdog/
├── watchdog.pid              # 守护进程 PID
├── tasks.json                # 注册的任务
├── alerts.log                # 异常日志（跨 session 恢复时读取）
└── status/
    ├── exp01.json            # 每个任务的状态
    ├── dl01.json
    └── summary.txt           # 每行一个任务的汇总
```

## 安装

### 1. 复制到服务器

```bash
scp tools/watchdog.py your-server:/path/to/project/tools/
```

或者在用 rsync 同步代码时（如 `/run-experiment`），把 `tools/` 目录一起同步。

### 2. 启动守护进程

```bash
# 在服务器上的 screen/tmux 中启动（持久化运行）
screen -dmS watchdog python3 tools/watchdog.py
# 或
tmux new-session -d -s watchdog "python3 tools/watchdog.py"
```

可选参数：
```bash
python3 tools/watchdog.py --base-dir /tmp/my-monitor --interval 30
```

### 3. 注册任务

启动实验后注册：

```bash
# 训练任务（screen session，指定 GPU）
python3 tools/watchdog.py --register '{
  "name": "exp01",
  "type": "training",
  "session": "exp01",
  "session_type": "screen",
  "gpus": [0, 1, 2, 3]
}'

# 下载任务（tmux session，追踪文件大小）
python3 tools/watchdog.py --register '{
  "name": "dl-imagenet",
  "type": "download",
  "session": "dl01",
  "session_type": "tmux",
  "target_path": "/data/imagenet"
}'
```

**必填字段：**
- `name` — 唯一任务标识
- `type` — `"training"` 或 `"download"`
- `session` — screen/tmux session 名

**可选字段：**
- `session_type` — `"screen"`（默认）或 `"tmux"`
- `gpus` — 要监控的 GPU 编号列表（仅训练）
- `target_path` — 追踪大小增长的文件/目录（仅下载）

### 4. 从本地机器监控

**一次性检查：**
```bash
ssh your-server "python3 /path/to/tools/watchdog.py --status"
# 或
ssh your-server "cat /tmp/aris-watchdog/status/summary.txt"
```

**示例输出：**
```
exp01(training): OK
exp02(training): IDLE gpu={'0': 0, '1': 0, '2': 0, '3': 2}
dl01(download): SLOW speed=0.45MB/s
```

**使用 CronCreate 自动轮询（Claude Code）：**
```
CronCreate: 每 15 分钟
  ssh your-server "cat /tmp/aris-watchdog/status/summary.txt"
  → 全部 OK → 不做任何事
  → 有 DEAD/STALLED/SLOW/IDLE → 调查处理
```

> **每台服务器只设一个 cron**，不是每个任务一个 — summary.txt 已经汇总了所有任务。

### 5. 注销已完成的任务

```bash
python3 tools/watchdog.py --unregister exp01
```

## 状态码

| 状态 | 含义 | 建议操作 |
|------|------|----------|
| `OK` | 任务正常运行 | 无需操作 |
| `DEAD` | Session 已不存在 | 检查训练是否完成或崩溃，必要时重启 |
| `IDLE` | GPU 利用率 <5% | 训练可能已完成、崩溃或卡在数据加载 |
| `STALLED` | 下载文件大小不增长 | 检查网络、磁盘空间、认证 token |
| `SLOW` | 下载速度 <1 MB/s | 可能被限速，检查网络或下载源 |
| `ERROR` | Watchdog 检查任务时出错 | 检查 watchdog 日志 |

## 与 ARIS 工作流集成

### 配合 `/run-experiment`

用 `/run-experiment` 部署实验后，注册到 watchdog：

```bash
# /run-experiment 启动 screen session "exp01"
# 然后注册：
python3 tools/watchdog.py --register '{"name":"exp01","type":"training","session":"exp01","gpus":[0,1]}'
```

### 配合 `/monitor-experiment`

`/monitor-experiment` 做深度检查（日志解析、W&B 指标、结果收集）。Watchdog 做持续的表面健康检查。互补关系：

- **Watchdog** — "它活着吗？GPU 在用吗？"（7×24 运行，低开销）
- **`/monitor-experiment`** — "实际结果怎么样？"（按需、详细）

### 配合会话恢复

开新 session 时，检查 `alerts.log` 查看你不在时发生的异常：

```bash
ssh your-server "tail -20 /tmp/aris-watchdog/alerts.log"
```

配合 [会话恢复指南](SESSION_RECOVERY_GUIDE_CN.md) 使用效果更佳 — 在恢复流程中加入 watchdog 告警检查。

## 自定义

| 参数 | 默认值 | 修改方式 |
|------|--------|----------|
| 工作目录 | `/tmp/aris-watchdog` | `--base-dir /your/path` |
| 检查间隔 | 60 秒 | `--interval 30` |
| GPU 空闲阈值 | 5% | 修改脚本中 `GPU_IDLE_THRESHOLD` |
| 下载慢速阈值 | 1 MB/s | 修改脚本中 `SLOW_SPEED_THRESHOLD` |

## 常见问题

**Q：需要 root 权限吗？**
A：不需要。只要 Python 3 和 `nvidia-smi`（仅训练任务需要）。

**Q：一台服务器能跑多个 watchdog 吗？**
A：可以，用不同的 `--base-dir`。但通常一台服务器一个实例就够了——它支持多任务。

**Q：watchdog 自身崩溃了怎么办？**
A：检查 `watchdog.pid` — 如果 PID 已失效，重启即可。守护进程能优雅处理 SIGTERM/SIGINT。

**Q：没有 nvidia-smi 能用吗？**
A：下载任务可以。训练任务会报 OK（无 GPU 数据）但无法检测 IDLE 状态。
