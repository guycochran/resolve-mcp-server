#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server

Exposes DaVinci Resolve's scripting API as MCP tools for AI assistants.
Supports both stdio (Claude Desktop) and HTTP (remote/mobile) transports.

Usage:
    # stdio (default — for Claude Desktop)
    python src/server.py

    # HTTP (for remote access via Cloudflare tunnel)
    TRANSPORT=http PORT=3001 python src/server.py
"""

# Log explicitly to stderr; stdout belongs to the MCP stdio transport.
import sys
import os


# Add the src directory to Python path for relative imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# Load .env file if present (for MOONDREAM_API_KEY, etc.)
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from mcp.server.fastmcp import FastMCP

# Read port early so it's available for both constructor and main()
_port = int(os.environ.get("PORT", "3001"))

# Create the MCP server
mcp = FastMCP(
    "resolve-mcp-server",
    json_response=True,
    host=os.environ.get("HOST", "127.0.0.1"),
    port=_port,
)

# Register all tool modules
from src.tools import connection, project, timeline, media, editing, color, markers, titles, render, fusion, vision

connection.register(mcp)
project.register(mcp)
timeline.register(mcp)
media.register(mcp)
editing.register(mcp)
color.register(mcp)
markers.register(mcp)
titles.register(mcp)
render.register(mcp)
fusion.register(mcp)
vision.register(mcp)

from src.tools import analysis
from src import resources
analysis.register(mcp)
resources.register(mcp)


def main():
    transport = os.environ.get("TRANSPORT", "stdio")

    if transport == "http":
        print(f"[resolve-mcp] v1.1.0 | Starting HTTP transport on port {_port}", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        print("[resolve-mcp] v1.1.0 | Starting stdio transport", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
