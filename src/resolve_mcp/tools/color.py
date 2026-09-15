"""Color grading tools — LUTs, color versions, grade management."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_resolve, get_project, get_timeline


def _get_current_clip():
    """Get the timeline item at the current playhead."""
    tl = get_timeline()
    item = tl.GetCurrentVideoItem()
    if item is None:
        raise RuntimeError("No video clip at the current playhead position.")
    return item


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_apply_lut(
        lut_path: str,
        node_index: int = 1,
    ) -> str:
        """Apply a LUT to a clip's node graph. Targets the clip at the playhead.

        Must be on the Color page. Common built-in LUTs:
        - "Film Looks/Rec709 Kodak 2383 D65.cube"
        - "Film Looks/Rec709 Fujifilm 3513DI D65.cube"

        Args:
            lut_path: LUT file path (relative to Resolve's LUT directory or absolute).
            node_index: Node to apply LUT to (1-based, default: 1).
        """
        resolve = get_resolve()
        project = get_project()
        project.RefreshLUTList()

        current_page = resolve.GetCurrentPage()
        if current_page != "color":
            resolve.OpenPage("color")

        item = _get_current_clip()
        graph = item.GetNodeGraph()
        if graph is None:
            return "Cannot access node graph. Make sure you're on the Color page with a clip selected."

        if graph.SetLUT(node_index, lut_path):
            return f"Applied LUT '{lut_path}' to node {node_index} on '{item.GetName()}'"
        return f"Failed to apply LUT. Check the path: {lut_path}"

    @mcp.tool()
    def resolve_get_lut(node_index: int = 1) -> str:
        """Get the LUT currently applied to a node on the clip at the playhead.

        Args:
            node_index: Node index (1-based, default: 1).
        """
        item = _get_current_clip()
        graph = item.GetNodeGraph()
        if graph is None:
            return "Cannot access node graph."

        lut = graph.GetLUT(node_index)
        if lut:
            return json.dumps({"clip": item.GetName(), "node": node_index, "lut": lut})
        return json.dumps({"clip": item.GetName(), "node": node_index, "lut": None})

    @mcp.tool()
    def resolve_create_color_version(name: str, version_type: int = 0) -> str:
        """Create a new color version on the clip at the playhead.

        Args:
            name: Name for the color version.
            version_type: 0 = local (default), 1 = remote.
        """
        item = _get_current_clip()
        if item.AddVersion(name, version_type):
            vtype = "local" if version_type == 0 else "remote"
            return f"Created {vtype} color version '{name}' on '{item.GetName()}'"
        return "Failed to create color version."

    @mcp.tool()
    def resolve_load_color_version(name: str, version_type: int = 0) -> str:
        """Switch to a color version by name on the clip at the playhead.

        Args:
            name: Color version name.
            version_type: 0 = local (default), 1 = remote.
        """
        item = _get_current_clip()
        if item.LoadVersionByName(name, version_type):
            return f"Loaded color version '{name}' on '{item.GetName()}'"
        return f"Failed to load color version '{name}'. Check the name."

    @mcp.tool()
    def resolve_list_color_versions(version_type: int = 0) -> str:
        """List all color versions on the clip at the playhead.

        Args:
            version_type: 0 = local versions (default), 1 = remote versions.

        Returns JSON with version names and current version."""
        item = _get_current_clip()
        versions = item.GetVersionNameList(version_type)
        current = item.GetCurrentVersion()
        return json.dumps({
            "clip": item.GetName(),
            "type": "local" if version_type == 0 else "remote",
            "versions": versions or [],
            "current": current,
        }, indent=2)

    @mcp.tool()
    def resolve_export_lut(
        output_path: str,
        export_type: str = "33pt",
    ) -> str:
        """Export a LUT from the current clip's grade.

        Args:
            output_path: Absolute path for the output .cube file.
            export_type: "17pt", "33pt" (default), or "65pt".
        """
        resolve = get_resolve()
        item = _get_current_clip()

        type_map = {
            "17pt": 0,  # EXPORT_LUT_17PTCUBE
            "33pt": 1,  # EXPORT_LUT_33PTCUBE
            "65pt": 2,  # EXPORT_LUT_65PTCUBE
        }
        lut_type = type_map.get(export_type, 1)

        if item.ExportLUT(lut_type, output_path):
            return f"Exported {export_type} LUT to {output_path}"
        return "Failed to export LUT. Make sure the clip has a grade applied."
