"""Marker tools — add, get, delete markers on timelines and clips."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_timeline


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_add_marker(
        color: str = "Blue",
        name: str = "",
        note: str = "",
        duration: int = 1,
        frame: int = 0,
    ) -> str:
        """Add a marker to the current timeline.

        Args:
            color: Marker color — Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream.
            name: Marker name/title.
            note: Marker note/description.
            duration: Marker duration in frames (default: 1).
            frame: Frame number to place marker. 0 = current playhead position.
        """
        tl = get_timeline()
        if frame == 0:
            tc = tl.GetCurrentTimecode()
            # Convert timecode to frame offset from timeline start
            frame = int(tl.GetStartFrame())
            # Use a relative offset approach — get all current markers to find playhead frame
            # For simplicity, we calculate from the start frame
            # The API uses frame IDs relative to timeline start
            start = tl.GetStartFrame()
            end = tl.GetEndFrame()
            # Place at current position using timecode
            # Actually the marker frame is relative to start, so we use the current video item
            current_item = tl.GetCurrentVideoItem()
            if current_item:
                frame = current_item.GetStart() - start
            else:
                frame = 0

        if tl.AddMarker(frame, color, name, note, duration):
            return f"Added {color} marker '{name}' at frame {frame}"
        return "Failed to add marker. Check the frame position and color name."

    @mcp.tool()
    def resolve_get_markers() -> str:
        """Get all markers on the current timeline.

        Returns JSON dict of markers keyed by frame number, with color, name, note, and duration."""
        tl = get_timeline()
        markers = tl.GetMarkers()
        if not markers:
            return json.dumps({"markers": {}, "count": 0})

        result = {}
        for frame_id, info in markers.items():
            result[str(frame_id)] = {
                "color": info.get("color", ""),
                "name": info.get("name", ""),
                "note": info.get("note", ""),
                "duration": info.get("duration", 1),
                "customData": info.get("customData", ""),
            }
        return json.dumps({"markers": result, "count": len(result)}, indent=2)

    @mcp.tool()
    def resolve_delete_markers(color: str = "", frame: int = 0) -> str:
        """Delete markers from the current timeline.

        Args:
            color: Delete all markers of this color. Use "All" to delete all markers. Leave empty to use frame instead.
            frame: Delete the marker at this specific frame. Ignored if color is specified.
        """
        tl = get_timeline()
        if color:
            if tl.DeleteMarkersByColor(color):
                label = "all markers" if color == "All" else f"all {color} markers"
                return f"Deleted {label}."
            return f"No {color} markers found (or deletion failed)."
        elif frame > 0:
            if tl.DeleteMarkerAtFrame(frame):
                return f"Deleted marker at frame {frame}."
            return f"No marker found at frame {frame}."
        return "Specify either a color or a frame number."
