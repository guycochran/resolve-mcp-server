"""Media pool tools — list clips, import, create bins, append to timeline."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_media_pool, get_media_storage


def _folder_to_dict(folder) -> dict:
    """Convert a Folder object to a serializable dict."""
    clips = folder.GetClipList() or []
    clip_list = []
    for clip in clips:
        props = clip.GetClipProperty() or {}
        clip_list.append({
            "name": clip.GetName(),
            "duration": props.get("Duration", ""),
            "type": props.get("Type", ""),
            "resolution": props.get("Resolution", ""),
            "fps": props.get("FPS", ""),
            "codec": props.get("Video Codec", ""),
        })
    subfolders = [sf.GetName() for sf in (folder.GetSubFolderList() or [])]
    return {
        "name": folder.GetName(),
        "clips": clip_list,
        "subfolders": subfolders,
    }


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_list_media(folder_path: str = "") -> str:
        """List clips in the media pool. Shows the current bin by default.

        Args:
            folder_path: Optional subfolder name to navigate to (e.g., "B-Roll"). Leave empty for current folder.

        Returns JSON with folder name, clips (with metadata), and subfolders."""
        mp = get_media_pool()
        if folder_path:
            root = mp.GetRootFolder()
            target = None
            for sf in (root.GetSubFolderList() or []):
                if sf.GetName() == folder_path:
                    target = sf
                    break
            if target is None:
                return json.dumps({"error": f"Folder '{folder_path}' not found in root."})
            return json.dumps(_folder_to_dict(target), indent=2)
        else:
            folder = mp.GetCurrentFolder()
            return json.dumps(_folder_to_dict(folder), indent=2)

    @mcp.tool()
    def resolve_import_media(file_paths: list[str]) -> str:
        """Import media files into the current media pool bin.

        Args:
            file_paths: List of absolute file paths to import (e.g., ["/Users/guy/video.mov"]).

        Returns names of successfully imported clips."""
        mp = get_media_pool()
        items = mp.ImportMedia(file_paths)
        if items:
            names = [item.GetName() for item in items]
            return json.dumps({"imported": names, "count": len(names)})
        return json.dumps({"error": "Failed to import media. Check file paths."})

    @mcp.tool()
    def resolve_create_bin(name: str) -> str:
        """Create a new bin (subfolder) in the media pool.

        Args:
            name: Name for the new bin.
        """
        mp = get_media_pool()
        root = mp.GetRootFolder()
        folder = mp.AddSubFolder(root, name)
        if folder:
            return f"Created bin: {name}"
        return f"Failed to create bin '{name}'."

    @mcp.tool()
    def resolve_append_to_timeline(
        clip_name: str,
        track_index: int = 1,
        media_type: int = 0,
    ) -> str:
        """Add a clip from the media pool to the current timeline.

        Args:
            clip_name: Name of the clip in the media pool.
            track_index: Target video track (1-based, default: 1).
            media_type: 0 = video+audio (default), 1 = video only, 2 = audio only.
                        Use 1 for b-roll to preserve interview audio.
        """
        mp = get_media_pool()
        folder = mp.GetCurrentFolder()
        clips = folder.GetClipList() or []

        target_clip = None
        for clip in clips:
            if clip.GetName() == clip_name:
                target_clip = clip
                break

        if target_clip is None:
            # Search root folder
            root = mp.GetRootFolder()
            for clip in (root.GetClipList() or []):
                if clip.GetName() == clip_name:
                    target_clip = clip
                    break

        if target_clip is None:
            return f"Clip '{clip_name}' not found in media pool."

        clip_info = {"mediaPoolItem": target_clip, "trackIndex": track_index}
        if media_type > 0:
            clip_info["mediaType"] = media_type

        result = mp.AppendToTimeline([clip_info])
        if result:
            return f"Added '{clip_name}' to track {track_index}"
        return f"Failed to add '{clip_name}' to timeline."

    @mcp.tool()
    def resolve_get_clip_properties(clip_name: str) -> str:
        """Get detailed properties of a media pool clip.

        Args:
            clip_name: Name of the clip in the media pool.

        Returns JSON with all clip properties (duration, resolution, codec, fps, etc.)."""
        mp = get_media_pool()
        folder = mp.GetCurrentFolder()
        clips = folder.GetClipList() or []

        for clip in clips:
            if clip.GetName() == clip_name:
                props = clip.GetClipProperty() or {}
                props["name"] = clip.GetName()
                return json.dumps(props, indent=2)

        return json.dumps({"error": f"Clip '{clip_name}' not found in current bin."})
