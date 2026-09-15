"""Timeline markers using timeline-relative frames."""
import json
from ..services.resolve_connection import get_timeline
from ..services.timecode import playhead_offset
from .analysis import COLORS


def register(mcp):
    @mcp.tool()
    def resolve_add_marker(color: str = "Blue", name: str = "", note: str = "",
                           duration: int = 1, frame: int = 0) -> str:
        """Add timeline marker. Legacy frame=0 selects playhead; other values are timeline-relative.
        Use create_chapter_markers to explicitly address frame zero."""
        timeline = get_timeline()
        frame = playhead_offset(timeline) if frame == 0 else frame
        if color not in COLORS or duration < 1 or frame < 0 or frame + duration > timeline.GetEndFrame()-timeline.GetStartFrame():
            raise ValueError("Invalid marker color, position, or duration.")
        result = timeline.AddMarker(frame, color, name, note, duration)
        return json.dumps({"success": bool(result), "frame": frame, "name": name, "color": color, "duration": duration})

    @mcp.tool()
    def resolve_get_markers() -> str:
        """Read timeline markers keyed by timeline-relative frame."""
        markers = get_timeline().GetMarkers() or {}
        return json.dumps({"markers": markers, "count": len(markers)})

    @mcp.tool()
    def resolve_delete_markers(color: str = "", frame: int | None = None) -> str:
        """Delete markers by explicit color, All, or exact timeline-relative frame (including zero).
        No arguments make no changes. Returns the removed marker records for restoration."""
        timeline = get_timeline()
        markers = timeline.GetMarkers() or {}
        if color:
            if color not in (*COLORS, "All"):
                raise ValueError("Invalid marker color.")
            selected = {f: m for f, m in markers.items() if color == "All" or m.get("color") == color}
            result = timeline.DeleteMarkersByColor(color)
        elif frame is not None and frame >= 0:
            selected = {f: m for f, m in markers.items() if float(f) == frame}
            result = timeline.DeleteMarkerAtFrame(frame)
        else:
            raise ValueError("Provide a marker color or frame.")
        return json.dumps({"success": bool(result), "removed": selected if result else {},
                           "requested_color": color, "requested_frame": frame})