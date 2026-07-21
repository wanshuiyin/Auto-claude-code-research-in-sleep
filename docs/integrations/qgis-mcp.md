# QGIS-MCP Integration

[QGIS-MCP](https://github.com/jjsantos01/qgis_mcp) bridges **QGIS Desktop** (the open-source GIS
application) with Claude Code via the Model Context Protocol. It allows LLM-driven geospatial
analysis: loading GIS data, running processing algorithms, rendering maps, and executing PyQGIS
code — all from a research pipeline.

## Architecture

```
Claude Code (MCP host)
     ↕ stdio (JSON-RPC via FastMCP)
mcp-servers/qgis/server.py     ← ARIS-bundled MCP server
     ↕ TCP socket (localhost:9876)
QGIS MCP Plugin (inside QGIS)  ← installed separately
     ↕ PyQGIS API
QGIS Desktop
```

The **QGIS plugin** (from the qgis_mcp repo) runs inside QGIS and opens a socket server. The
**ARIS MCP server** (`mcp-servers/qgis/server.py`) connects to that socket and translates MCP
tool calls into QGIS commands.

## Prerequisites

1. **QGIS Desktop** 3.x — [Download](https://qgis.org/download/)
2. **Python 3.12+** and **uv** (`brew install uv` on macOS)
3. **QGIS MCP Plugin** — see [Installation](#installation) below

## Installation

### 1. Install the QGIS Plugin

Clone the QGIS-MCP repo and symlink the plugin into your QGIS profile:

```bash
git clone git@github.com:jjsantos01/qgis_mcp.git /path/to/qgis_mcp

# macOS
ln -s /path/to/qgis_mcp/qgis_mcp_plugin \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp

# Windows PowerShell
# New-Item -ItemType SymbolicLink -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp" -Target "C:\path\to\qgis_mcp\qgis_mcp_plugin"
```

Restart QGIS, then enable the plugin via **Plugins → Manage and Install Plugins → QGIS MCP**.

### 2. Start the Server in QGIS

Open the QGIS MCP dock widget (**Plugins → QGIS MCP → QGIS MCP**), confirm the port (default
9876), and click **Start Server**. The status should show "Server: Running on port 9876".

### 3. Register the MCP Server with Claude Code

Register the QGIS MCP server with Claude Code so that its tools are available
to skills (like `/qgis-mcp`):

```bash
claude mcp add qgis -s project -- \
  uv --directory /path/to/aris/mcp-servers/qgis run server.py
```

Replace `/path/to/aris` with the absolute path to the ARIS repository (e.g.,
`~/aris_repo`).

> **Note:** You must also have the QGIS plugin installed and the server running
> inside QGIS (see [Step 1](#1-install-the-qgis-plugin) and
> [Step 2](#2-start-the-server-in-qgis) above).

### 4. Verify

In Claude Code, type `/qgis-mcp` and run `ping`. If QGIS is running with the plugin started,
you should see a successful response.

## Exposed Tools

| Tool | Description |
|---|---|
| `ping` | Check connectivity with the QGIS plugin |
| `get_qgis_info` | Return QGIS version and environment info |
| `load_project` | Load a .qgz / .qgs project from path |
| `create_new_project` | Create and save a new empty project |
| `get_project_info` | Current project metadata (CRS, layers, …) |
| `add_vector_layer` | Add shapefile / GeoPackage / GeoJSON etc. |
| `add_raster_layer` | Add GeoTIFF / other raster layer |
| `get_layers` | List all layers in the project |
| `remove_layer` | Remove a layer by ID |
| `zoom_to_layer` | Zoom canvas to a layer's extent |
| `get_layer_features` | Query features (attributes + WKT geometry) |
| `execute_processing` | Run any Processing Toolbox algorithm |
| `save_project` | Save the current project |
| `render_map` | Render canvas to a PNG image |
| `execute_code` | Run arbitrary PyQGIS code (⚠ cautious) |

## Usage in Research Pipelines

The `/qgis-mcp` skill (see `skills/qgis-mcp/`) integrates QGIS into ARIS workflows:

- **Spatial data discovery** — load, inspect, and query geospatial datasets
- **Automated map production** — render publication-quality maps programmatically
- **Geo-ML preprocessing** — use QGIS Processing algorithms as feature-engineering steps
- **Result visualization** — overlay research outputs on base maps

Combine with `/research-pipeline` for end-to-end geo-spatial ML research:
`/research-pipeline "landslide susceptibility mapping using deep learning" -- qgis-mcp: true`

## Troubleshooting

| Symptom | Check |
|---|---|
| `Could not connect to QGIS` | Is QGIS running? Is the plugin server started? |
| `Connection refused` | Port mismatch — default is 9876 in both plugin and server |
| Tools return empty data | Is a project loaded? Are layers visible in QGIS? |
| `uv` not found | Install uv: `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh` |

## Files

| Path | Purpose |
|---|---|
| `mcp-servers/qgis/server.py` | MCP server (stdio transport, socket client) |
| `mcp-servers/qgis/requirements.txt` | Python dependencies |
| `skills/qgis-mcp/SKILL.md` | ARIS skill for QGIS workflows |
| `.env` (project root) | `QGIS_MCP_HOST`, `QGIS_MCP_PORT` |
