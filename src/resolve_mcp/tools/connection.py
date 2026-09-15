"""Connection & navigation tools — status, page switching, reconnect."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import (
    get_resolve, get_project, get_timeline, is_connected, reconnect,
)


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_get_status() -> str:
        """Get current DaVinci Resolve status including version, current project, timeline, and page.

        Returns JSON with product name, version, current page, project name,
        timeline name, and connection state."""
        if not is_connected():
            return json.dumps({"connected": False, "error": "Not connected to DaVinci Resolve. Is it running?"})

        resolve = get_resolve()
        status = {
            "connected": True,
            "product": resolve.GetProductName(),
            "version": resolve.GetVersionString(),
            "page": resolve.GetCurrentPage(),
        }

        try:
            project = get_project()
            status["project"] = project.GetName()
            status["projectSettings"] = {
                "frameRate": project.GetSetting("timelineFrameRate"),
                "resolution": f'{project.GetSetting("timelineResolutionWidth")}x{project.GetSetting("timelineResolutionHeight")}',
            }
        except RuntimeError:
            status["project"] = None

        try:
            tl = get_timeline()
            status["timeline"] = {
                "name": tl.GetName(),
                "timecode": tl.GetCurrentTimecode(),
                "videoTracks": tl.GetTrackCount("video"),
                "audioTracks": tl.GetTrackCount("audio"),
            }
        except RuntimeError:
            status["timeline"] = None

        return json.dumps(status, indent=2)

    @mcp.tool()
    def resolve_open_page(page: str) -> str:
        """Switch DaVinci Resolve to a specific page.

        Args:
            page: Page name — "media", "cut", "edit", "fusion", "color", "fairlight", or "deliver"
        """
        valid = ["media", "cut", "edit", "fusion", "color", "fairlight", "deliver"]
        if page not in valid:
            return f"Invalid page '{page}'. Must be one of: {', '.join(valid)}"

        resolve = get_resolve()
        success = resolve.OpenPage(page)
        if success:
            return f"Switched to {page} page."
        return f"Failed to switch to {page} page."

    @mcp.tool()
    def resolve_get_current_page() -> str:
        """Get the currently active DaVinci Resolve page.

        Returns the page name: media, cut, edit, fusion, color, fairlight, or deliver."""
        resolve = get_resolve()
        page = resolve.GetCurrentPage()
        return page or "unknown"

    @mcp.tool()
    def resolve_reconnect() -> str:
        """Force reconnection to DaVinci Resolve. Use if Resolve was restarted."""
        if reconnect():
            resolve = get_resolve()
            return f"Reconnected to {resolve.GetProductName()} {resolve.GetVersionString()}"
        return "Failed to connect to DaVinci Resolve. Make sure it is running."
