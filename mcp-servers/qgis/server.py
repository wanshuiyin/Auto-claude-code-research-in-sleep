#!/usr/bin/env python3
"""
QGIS MCP Server — bridges Claude Code with QGIS via the QGIS MCP plugin.

Architecture:
  Claude Code (MCP host)
       ↕ stdio (JSON-RPC via FastMCP)
  qgis_mcp_server.py    ← this file
       ↕ TCP socket (localhost:9876)
  QGIS MCP Plugin       ← runs inside QGIS, exposes PyQGIS API

Prerequisites:
  1. Install the qgis_mcp_plugin into QGIS (see docs/integrations/qgis-mcp.md).
  2. Start QGIS and click "Start Server" in the QGIS MCP plugin toolbar.
  3. (Re)start Claude Code.

Environment Variables (in .env):
  QGIS_MCP_HOST   — default: localhost
  QGIS_MCP_PORT   — default: 9876
"""

import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP, Context

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("QgisMCP")

# ---------------------------------------------------------------------------
# Socket client (same pattern as upstream qgis_mcp)
# ---------------------------------------------------------------------------

QGIS_HOST = os.environ.get("QGIS_MCP_HOST", "localhost")
QGIS_PORT = int(os.environ.get("QGIS_MCP_PORT", "9876"))


class QgisSocketClient:
    """Thin socket client that talks to the QGIS MCP plugin."""

    def __init__(self, host: str = QGIS_HOST, port: int = QGIS_PORT) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def connect(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(10)
            self._sock.connect((self.host, self.port))
            return True
        except OSError as exc:
            logger.warning("Cannot connect to QGIS plugin at %s:%s — %s",
                           self.host, self.port, exc)
            return False

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send(self, cmd_type: str, params: dict | None = None) -> dict | None:
        if not self._sock:
            return None
        payload = json.dumps({"type": cmd_type, "params": params or {}})
        try:
            self._sock.sendall(payload.encode("utf-8"))
        except OSError as exc:
            logger.error("Send failed: %s", exc)
            return None

        # Read until we have a complete JSON object
        raw = b""
        while True:
            try:
                chunk = self._sock.recv(4096)
            except OSError as exc:
                logger.error("Recv failed: %s", exc)
                return None
            if not chunk:
                break
            raw += chunk
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                continue
        return None


# ---------------------------------------------------------------------------
# Global connection (lazy, persistent)
# ---------------------------------------------------------------------------

_qgis: QgisSocketClient | None = None


def _get_qgis() -> QgisSocketClient:
    global _qgis
    if _qgis is None:
        _qgis = QgisSocketClient()
        if not _qgis.connect():
            _qgis = None
            raise RuntimeError(
                "Could not connect to QGIS. "
                "Make sure QGIS is running with the QGIS MCP plugin enabled "
                "and the server started (click 'Start Server' in the plugin toolbar)."
            )
        logger.info("Connected to QGIS plugin at %s:%s", QGIS_HOST, QGIS_PORT)
    return _qgis


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    logger.info("QGIS MCP server starting up")
    try:
        _get_qgis()
    except RuntimeError as exc:
        logger.warning("QGIS not available at startup: %s", exc)
        logger.warning("Tools will report errors until QGIS is running.")
    try:
        yield {}
    finally:
        global _qgis
        if _qgis:
            _qgis.disconnect()
            _qgis = None
        logger.info("QGIS MCP server shut down")


mcp = FastMCP(
    "QgisMCP",
    description="QGIS integration through the Model Context Protocol",
    lifespan=server_lifespan,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _call(cmd: str, **params: Any) -> str:
    q = _get_qgis()
    result = q.send(cmd, params or None)
    if result is None:
        return json.dumps({"status": "error", "message": "No response from QGIS plugin"})
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def ping(ctx: Context) -> str:
    """Check connectivity with the QGIS plugin."""
    return _call("ping")


@mcp.tool()
def get_qgis_info(ctx: Context) -> str:
    """Return QGIS version and environment information."""
    return _call("get_qgis_info")


@mcp.tool()
def load_project(ctx: Context, path: str) -> str:
    """Load a QGIS project (.qgz / .qgs) from *path*."""
    return _call("load_project", path=path)


@mcp.tool()
def create_new_project(ctx: Context, path: str) -> str:
    """Create and save a new (empty) QGIS project at *path*."""
    return _call("create_new_project", path=path)


@mcp.tool()
def get_project_info(ctx: Context) -> str:
    """Return metadata about the currently open project (CRS, layers, …)."""
    return _call("get_project_info")


@mcp.tool()
def add_vector_layer(
    ctx: Context,
    path: str,
    provider: str = "ogr",
    name: str | None = None,
) -> str:
    """Add a vector layer (shapefile, GeoPackage, GeoJSON, …) to the project."""
    return _call("add_vector_layer", path=path, provider=provider, name=name)


@mcp.tool()
def add_raster_layer(
    ctx: Context,
    path: str,
    provider: str = "gdal",
    name: str | None = None,
) -> str:
    """Add a raster layer (GeoTIFF, …) to the project."""
    return _call("add_raster_layer", path=path, provider=provider, name=name)


@mcp.tool()
def get_layers(ctx: Context) -> str:
    """List all layers in the current project."""
    return _call("get_layers")


@mcp.tool()
def remove_layer(ctx: Context, layer_id: str) -> str:
    """Remove a layer from the project by its *layer_id*."""
    return _call("remove_layer", layer_id=layer_id)


@mcp.tool()
def zoom_to_layer(ctx: Context, layer_id: str) -> str:
    """Zoom the map canvas to the extent of the layer identified by *layer_id*."""
    return _call("zoom_to_layer", layer_id=layer_id)


@mcp.tool()
def get_layer_features(ctx: Context, layer_id: str, limit: int = 10) -> str:
    """Return features (attributes + geometry) from a vector *layer_id* (max *limit*)."""
    return _call("get_layer_features", layer_id=layer_id, limit=limit)


@mcp.tool()
def execute_processing(ctx: Context, algorithm: str, parameters: dict) -> str:
    """Run a QGIS Processing algorithm by *algorithm* id with *parameters* dict."""
    return _call("execute_processing", algorithm=algorithm, parameters=parameters)


@mcp.tool()
def save_project(ctx: Context, path: str | None = None) -> str:
    """Save the current project. If *path* is omitted, saves in-place."""
    return _call("save_project", path=path)


@mcp.tool()
def render_map(
    ctx: Context,
    path: str,
    width: int = 800,
    height: int = 600,
) -> str:
    """Render the current map canvas to a PNG image at *path* (default 800×600)."""
    return _call("render_map", path=path, width=width, height=height)


@mcp.tool()
def execute_code(ctx: Context, code: str) -> str:
    """Execute arbitrary PyQGIS code inside QGIS (use with extreme caution)."""
    return _call("execute_code", code=code)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
