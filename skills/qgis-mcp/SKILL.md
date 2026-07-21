---
name: qgis-mcp
description: Geospatial analysis via QGIS-MCP — load GIS data, run processing algorithms, render maps, and execute PyQGIS code from a research pipeline.
argument-hint: "[task description]"
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit
---

# QGIS-MCP: Geospatial Analysis via QGIS

{{ARGUMENTS}}

## Prerequisites

Before using this skill, the QGIS-MCP server must be registered and QGIS must
be running with the QGIS MCP plugin started. See `docs/integrations/qgis-mcp.md`
for setup.

Quick verification:
```bash
claude mcp list | grep qgis
# If not listed, register (replace /path/to/aris with the actual path):
claude mcp add qgis -s project -- uv --directory /path/to/aris/mcp-servers/qgis run server.py
```

**QGIS must be running** with the plugin server started (Plugins → QGIS MCP →
Start Server). Otherwise every tool call returns a connection error.

## Workflow

### Step 1: Understand the Task

Identify the geospatial task and the data available:
- What data do we need (vector layers, raster layers)?
- What analysis should be performed (spatial query, processing algorithm, map rendering)?
- What is the expected output (a rendered map, analysis results, code)?

### Data Source Priority

When the task requires geospatial data (base maps, DEM, imagery, administrative
boundaries, POIs, road networks, etc.), prefer sources in this order:

1. **中国官方/国内源（Chinese domestic sources）** — 天地图（Tianditu,
   https://www.tianditu.gov.cn/）、国家基础地理信息中心、各省市地理信息
   公共服务平台、中国科学院资源环境科学与数据中心（https://www.resdc.cn/）、
   全国地理信息资源目录服务系统（https://www.webmap.cn/）等。
   - 天地图提供 WMTS 瓦片、行政区划、地名地址、POI 等 API
   - 许多国内源无需翻墙，延迟低，数据适合中国区域
2. **大型国际开放平台** — OpenStreetMap（https://www.openstreetmap.org/，
   通过 QGIS OSM 插件或 QuickOSM）、Natural Earth（https://www.naturalearthdata.com/）、
   USGS EarthExplorer、ESA Copernicus、Google Earth Engine（如有权限）等
3. **科研及专业数据源** — 所在项目或实验室已有的数据集、导师/合作者
   提供的专有数据、论文附带的数据集仓库

> **注意：** 如果任务只需要处理用户已有数据（本地的 .shp / .gpkg / .tif
> 等文件），直接从 Step 2 开始即可。优先使用国内源的指引主要适用于
> **需要获取底图或外部辅助数据**的场景。

### Step 2: Connect and Verify

Use `ping` to verify the connection:
```
<FunctionCall>ping</FunctionCall>
```

Then gather context with `get_qgis_info` and (if a project is loaded)
`get_project_info`.

### Step 3: Execute Geospatial Task

Available tools (callable by name — the MCP host dispatches them):

| Tool | When to Use |
|---|---|
| `load_project` / `create_new_project` | Open existing or create new QGIS project |
| `add_vector_layer` / `add_raster_layer` | Load GIS data from disk |
| `get_layers` / `get_layer_features` | Inspect data contents and attributes |
| `zoom_to_layer` / `render_map` | Visualize data and export map images |
| `execute_processing` | Run QGIS native/GDAL/GRASS algorithms |
| `execute_code` | Run arbitrary PyQGIS for custom analysis |
| `save_project` | Persist project state |

### Step 4: Return Results

Summarize what was accomplished, including:
- Layers loaded or created
- Processing algorithms run and their outputs
- Map images rendered (note the file path)
- Any data extracts or analysis results

Combine with `/analyze-results` or other ARIS skills as needed for
research workflows.

## Example Usage

```
/qgis-mcp "Load Thailand election data from ~/data/thailand_2007.qgz, inspect the layers, and render a map to ~/output/map.png"
```

Or as part of a broader research pipeline:

```
/research-pipeline "landslide susceptibility mapping using deep learning" -- qgis-mcp: true
```
