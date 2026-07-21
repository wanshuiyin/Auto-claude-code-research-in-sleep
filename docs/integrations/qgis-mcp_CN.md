# QGIS-MCP 集成指南

[QGIS-MCP](https://github.com/jjsantos01/qgis_mcp) 通过模型上下文协议（MCP）将 **QGIS Desktop**（开源 GIS 桌面应用）与 Claude Code 连接起来。它让大语言模型能够驱动地理空间分析：加载 GIS 数据、运行处理算法、渲染地图和执行 PyQGIS 代码——全部在研究流水线中完成。

## 架构

```
Claude Code（MCP 主机）
     ↕ stdio（JSON-RPC，通过 FastMCP）
mcp-servers/qgis/server.py     ← ARIS 自带的 MCP 服务器
     ↕ TCP socket（localhost:9876）
QGIS MCP 插件（QGIS 内部）    ← 单独安装
     ↕ PyQGIS API
QGIS Desktop
```

**QGIS 插件**（来自 qgis_mcp 仓库）在 QGIS 内部运行，启动一个 socket 服务器。**ARIS MCP 服务器**（`mcp-servers/qgis/server.py`）连接到该 socket，将 MCP 工具调用转换成 QGIS 命令。

## 前提条件

1. **QGIS Desktop** 3.x — [下载地址](https://qgis.org/download/)
2. **Python 3.12+** 和 **uv**（macOS 上执行 `brew install uv`）
3. **QGIS MCP 插件** — 见下方[安装步骤](#安装)

## 安装

### 1. 安装 QGIS 插件

克隆 QGIS-MCP 仓库，将插件软链接到你的 QGIS 配置目录：

```bash
git clone git@github.com:jjsantos01/qgis_mcp.git /path/to/qgis_mcp

# macOS
ln -s /path/to/qgis_mcp/qgis_mcp_plugin \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp

# Windows PowerShell
# New-Item -ItemType SymbolicLink -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp" -Target "C:\path\to\qgis_mcp\qgis_mcp_plugin"
```

重启 QGIS，然后通过 **插件 → 管理并安装插件 → QGIS MCP** 启用该插件。

### 2. 在 QGIS 中启动服务器

打开 QGIS MCP 面板（**插件 → QGIS MCP → QGIS MCP**），确认端口（默认 9876），然后点击 **Start Server**。状态应显示 "Server: Running on port 9876"。

### 3. 向 Claude Code 注册 MCP 服务器

将 QGIS MCP 服务器注册到 Claude Code，这样技能（如 `/qgis-mcp`）就能使用其工具：

```bash
claude mcp add qgis -s project -- \
  uv --directory /path/to/aris/mcp-servers/qgis run server.py
```

将 `/path/to/aris` 替换为 ARIS 仓库的绝对路径（例如 `~/aris_repo`）。

> **注意：** 运行此命令前，你必须先安装 QGIS 插件并在 QGIS 中启动服务器（见上方[步骤 1](#1-安装-qgis-插件)和[步骤 2](#2-在-qgis-中启动服务器)）。

### 4. 验证

在 Claude Code 中输入 `/qgis-mcp` 并执行 `ping`。如果 QGIS 正在运行且插件服务器已启动，你应该会看到成功的响应。

## 暴露的工具

| 工具 | 功能 |
|---|---|
| `ping` | 检查与 QGIS 插件的连接 |
| `get_qgis_info` | 返回 QGIS 版本和环境信息 |
| `load_project` | 从路径加载 .qgz / .qgs 项目 |
| `create_new_project` | 创建并保存一个新的空项目 |
| `get_project_info` | 当前项目元数据（CRS、图层等） |
| `add_vector_layer` | 添加 shapefile / GeoPackage / GeoJSON 等矢量图层 |
| `add_raster_layer` | 添加 GeoTIFF 等栅格图层 |
| `get_layers` | 列出项目中所有图层 |
| `remove_layer` | 按 ID 移除图层 |
| `zoom_to_layer` | 将画布缩放到某图层范围 |
| `get_layer_features` | 查询要素（属性 + WKT 几何） |
| `execute_processing` | 运行任意 QGIS 处理工具箱算法 |
| `save_project` | 保存当前项目 |
| `render_map` | 将画布渲染为 PNG 图像 |
| `execute_code` | 执行任意 PyQGIS 代码（⚠ 谨慎使用） |

## 在研究流水线中的使用

`/qgis-mcp` 技能（见 `skills/qgis-mcp/`）将 QGIS 集成到 ARIS 工作流中：

- **空间数据发现** — 加载、检查和查询地理空间数据集
- **自动化地图制作** — 以编程方式渲染出版级地图
- **地理空间 ML 预处理** — 将 QGIS 处理算法用作特征工程步骤
- **结果可视化** — 在底图上叠加研究输出

与 `/research-pipeline` 结合使用可实现端到端地理空间 ML 研究：

```
/research-pipeline "基于深度学习的滑坡易发性制图" -- qgis-mcp: true
```

## 故障排除

| 症状 | 检查 |
|---|---|
| `Could not connect to QGIS` | QGIS 是否正在运行？插件服务器是否已启动？ |
| `Connection refused` | 端口不匹配——插件和服务器的默认端口都是 9876 |
| 工具返回空数据 | 是否已加载项目？QGIS 中的图层是否可见？ |
| `uv` 未找到 | 安装 uv：`brew install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh | sh` |

## 相关文件

| 路径 | 用途 |
|---|---|
| `mcp-servers/qgis/server.py` | MCP 服务器（stdio 传输，socket 客户端） |
| `mcp-servers/qgis/requirements.txt` | Python 依赖 |
| `skills/qgis-mcp/SKILL.md` | ARIS 的 QGIS 工作流技能 |
| `.env`（项目根目录） | `QGIS_MCP_HOST`、`QGIS_MCP_PORT` |
