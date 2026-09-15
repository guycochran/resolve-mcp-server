"""Title & text tools — insert Fusion titles, modify text content."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_resolve, get_timeline


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_insert_title(
        text: str,
        font_size: float = 0.05,
        position_x: float = 0.5,
        position_y: float = 0.5,
    ) -> str:
        """Insert a Fusion Text+ title into the timeline at the playhead.

        Args:
            text: The text content to display.
            font_size: Font size (0.01 to 0.3, default: 0.05). Relative to frame height.
            position_x: Horizontal position (0.0 = left, 0.5 = center, 1.0 = right).
            position_y: Vertical position (0.0 = bottom, 0.5 = center, 1.0 = top).
        """
        resolve = get_resolve()
        if resolve.GetCurrentPage() != "edit":
            resolve.OpenPage("edit")

        tl = get_timeline()
        title_item = tl.InsertFusionTitleIntoTimeline("Text+")
        if title_item is None:
            return "Failed to insert Fusion title. Make sure you're on the Edit page."

        # Access the Fusion composition to set text properties
        fusion_comp = title_item.GetFusionCompByIndex(1)
        if fusion_comp:
            tools = fusion_comp.GetToolList()
            for idx, tool in (tools or {}).items():
                try:
                    if tool.GetAttrs("TOOLS_RegID") == "TextPlus":
                        tool.SetInput("StyledText", text)
                        tool.SetInput("Size", font_size)
                        tool.SetInput("Center", {1: position_x, 2: position_y})
                        break
                except Exception:
                    pass

        return f"Inserted Text+ title: '{text}'"

    @mcp.tool()
    def resolve_modify_title_text(
        new_text: str,
        track_index: int = 0,
        clip_index: int = 0,
    ) -> str:
        """Change the text content of an existing Fusion title on the timeline.

        Targets the clip at the playhead by default.

        Args:
            new_text: The new text content.
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.
        """
        tl = get_timeline()

        if track_index > 0 and clip_index > 0:
            items = tl.GetItemListInTrack("video", track_index)
            if not items or clip_index > len(items):
                return "Clip not found at specified position."
            item = items[clip_index - 1]
        else:
            item = tl.GetCurrentVideoItem()
            if item is None:
                return "No clip at the current playhead."

        comp_count = item.GetFusionCompCount()
        if not comp_count or comp_count == 0:
            return f"'{item.GetName()}' has no Fusion compositions. It may not be a Fusion title."

        fusion_comp = item.GetFusionCompByIndex(1)
        if fusion_comp is None:
            return "Cannot access Fusion composition."

        tools = fusion_comp.GetToolList()
        modified = False
        for idx, tool in (tools or {}).items():
            try:
                if tool.GetAttrs("TOOLS_RegID") == "TextPlus":
                    tool.SetInput("StyledText", new_text)
                    modified = True
                    break
            except Exception:
                pass

        if modified:
            return f"Updated text on '{item.GetName()}' to: '{new_text}'"
        return "No TextPlus tool found in this clip's Fusion composition."
