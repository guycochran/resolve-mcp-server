"""Fusion title operations; failures report whether a title was already created."""
import json
import math
from ..services.resolve_connection import get_resolve, get_timeline
from .editing import _selected


def text_tool(item):
    comp = item.GetFusionCompByIndex(1)
    if comp is None:
        raise RuntimeError("No accessible Fusion composition.")
    for tool in (comp.GetToolList() or {}).values():
        if tool.GetAttrs("TOOLS_RegID") == "TextPlus":
            return tool
    raise RuntimeError("No TextPlus tool found in the composition.")


def register(mcp):
    @mcp.tool()
    def resolve_insert_title(text: str, font_size: float = 0.05,
                             position_x: float = 0.5, position_y: float = 0.5) -> str:
        """Insert Text+ at playhead. Validates size/position and reports partial failures after creation."""
        if not all(math.isfinite(x) for x in (font_size, position_x, position_y)):
            raise ValueError("Title size and coordinates must be finite.")
        if not 0.01 <= font_size <= 0.3 or not 0 <= position_x <= 1 or not 0 <= position_y <= 1:
            raise ValueError("Title size must be 0.01–0.3; positions must be 0–1.")
        resolve = get_resolve()
        if resolve.GetCurrentPage() != "edit" and not resolve.OpenPage("edit"):
            raise RuntimeError("Cannot open Edit page.")
        item = get_timeline().InsertFusionTitleIntoTimeline("Text+")
        if item is None:
            return json.dumps({"success": False, "created": False, "error": "Resolve refused title insertion."})
        try:
            tool = text_tool(item)
            for key, value in (("StyledText", text), ("Size", font_size), ("Center", {1: position_x, 2: position_y})):
                if tool.SetInput(key, value) is False:
                    raise RuntimeError(f"Fusion refused {key}.")
            return json.dumps({"success": True, "created": True, "text": text})
        except Exception as exc:
            return json.dumps({"success": False, "created": True, "error": str(exc),
                               "instruction": "The inserted title remains; inspect or remove it."})

    @mcp.tool()
    def resolve_modify_title_text(new_text: str, track_index: int = 0, clip_index: int = 0) -> str:
        """Modify Text+ on the playhead clip or explicit 1-based video track/clip indices."""
        item = _selected(track_index, clip_index, writable=True)
        tool = text_tool(item)
        result = tool.SetInput("StyledText", new_text)
        return json.dumps({"success": result is not False, "clip": item.GetName(), "requested_text": new_text})