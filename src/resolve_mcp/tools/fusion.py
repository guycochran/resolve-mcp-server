"""Fusion tools — comp management, tool listing."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_timeline


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_get_fusion_comps(track_index: int = 0, clip_index: int = 0) -> str:
        """List Fusion compositions on a timeline clip. Targets clip at playhead by default.

        Args:
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.

        Returns JSON with comp names and count."""
        tl = get_timeline()

        if track_index > 0 and clip_index > 0:
            items = tl.GetItemListInTrack("video", track_index)
            if not items or clip_index > len(items):
                return json.dumps({"error": "Clip not found."})
            item = items[clip_index - 1]
        else:
            item = tl.GetCurrentVideoItem()
            if item is None:
                return json.dumps({"error": "No clip at playhead."})

        count = item.GetFusionCompCount() or 0
        names = item.GetFusionCompNameList() or []

        return json.dumps({
            "clip": item.GetName(),
            "fusionCompCount": count,
            "fusionCompNames": names,
        }, indent=2)

    @mcp.tool()
    def resolve_add_fusion_comp() -> str:
        """Add a new Fusion composition to the clip at the playhead."""
        tl = get_timeline()
        item = tl.GetCurrentVideoItem()
        if item is None:
            return "No clip at the current playhead."

        comp = item.AddFusionComp()
        if comp:
            return f"Added Fusion composition to '{item.GetName()}'"
        return "Failed to add Fusion composition."

    @mcp.tool()
    def resolve_get_fusion_tools(comp_index: int = 1) -> str:
        """List all tools in a Fusion composition on the clip at the playhead.

        Args:
            comp_index: Fusion comp index (1-based, default: 1).

        Returns JSON array of tools with their type and name."""
        tl = get_timeline()
        item = tl.GetCurrentVideoItem()
        if item is None:
            return json.dumps({"error": "No clip at playhead."})

        comp = item.GetFusionCompByIndex(comp_index)
        if comp is None:
            return json.dumps({"error": f"No Fusion comp at index {comp_index}."})

        tools_dict = comp.GetToolList() or {}
        tool_list = []
        for idx, tool in tools_dict.items():
            try:
                tool_list.append({
                    "index": idx,
                    "id": tool.GetAttrs("TOOLS_RegID"),
                    "name": tool.GetAttrs("TOOLS_Name"),
                })
            except Exception:
                tool_list.append({"index": idx, "id": "unknown", "name": "unknown"})

        return json.dumps({
            "clip": item.GetName(),
            "compIndex": comp_index,
            "tools": tool_list,
        }, indent=2)
