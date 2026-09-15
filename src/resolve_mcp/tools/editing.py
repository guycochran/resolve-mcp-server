"""Editing / clip property tools — transform, speed, enable/disable, compound clips, replace."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_timeline, get_project


def _get_clip_at_playhead():
    """Get the timeline item at the current playhead position."""
    tl = get_timeline()
    item = tl.GetCurrentVideoItem()
    if item is None:
        raise RuntimeError("No video clip at the current playhead position.")
    return item


def _get_clip_by_index(track_index: int, clip_index: int):
    """Get a specific clip by track and clip index."""
    tl = get_timeline()
    items = tl.GetItemListInTrack("video", track_index)
    if not items or clip_index < 1 or clip_index > len(items):
        raise RuntimeError(f"No clip at video track {track_index}, clip index {clip_index}.")
    return items[clip_index - 1]


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_set_clip_transform(
        pan: float | None = None,
        tilt: float | None = None,
        zoom_x: float | None = None,
        zoom_y: float | None = None,
        rotation: float | None = None,
        opacity: float | None = None,
        track_index: int = 0,
        clip_index: int = 0,
    ) -> str:
        """Set transform properties on a timeline clip. Targets clip at playhead by default.

        Args:
            pan: Horizontal position (negative = left, positive = right).
            tilt: Vertical position (negative = down, positive = up).
            zoom_x: Horizontal scale (1.0 = 100%, 2.0 = 200%).
            zoom_y: Vertical scale (1.0 = 100%). Omit to match zoom_x.
            rotation: Rotation in degrees (-360 to 360).
            opacity: Opacity (0.0 to 100.0).
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.
        """
        if track_index > 0 and clip_index > 0:
            item = _get_clip_by_index(track_index, clip_index)
        else:
            item = _get_clip_at_playhead()

        changes = []
        if pan is not None:
            item.SetProperty("Pan", pan)
            changes.append(f"Pan={pan}")
        if tilt is not None:
            item.SetProperty("Tilt", tilt)
            changes.append(f"Tilt={tilt}")
        if zoom_x is not None:
            item.SetProperty("ZoomX", zoom_x)
            changes.append(f"ZoomX={zoom_x}")
            if zoom_y is None:
                item.SetProperty("ZoomY", zoom_x)
        if zoom_y is not None:
            item.SetProperty("ZoomY", zoom_y)
            changes.append(f"ZoomY={zoom_y}")
        if rotation is not None:
            item.SetProperty("RotationAngle", rotation)
            changes.append(f"Rotation={rotation}")
        if opacity is not None:
            item.SetProperty("Opacity", opacity)
            changes.append(f"Opacity={opacity}")

        if changes:
            return f"Set on '{item.GetName()}': {', '.join(changes)}"
        return "No properties specified to change."

    @mcp.tool()
    def resolve_get_clip_transform(track_index: int = 0, clip_index: int = 0) -> str:
        """Get current transform values of a timeline clip. Targets clip at playhead by default.

        Args:
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.

        Returns JSON with Pan, Tilt, Zoom, Rotation, Opacity values."""
        if track_index > 0 and clip_index > 0:
            item = _get_clip_by_index(track_index, clip_index)
        else:
            item = _get_clip_at_playhead()

        props = {}
        for key in ["Pan", "Tilt", "ZoomX", "ZoomY", "RotationAngle", "Opacity",
                     "CropLeft", "CropRight", "CropTop", "CropBottom"]:
            val = item.GetProperty(key)
            if val is not None:
                props[key] = val

        props["name"] = item.GetName()
        return json.dumps(props, indent=2)

    @mcp.tool()
    def resolve_set_clip_speed(speed: float, track_index: int = 0, clip_index: int = 0) -> str:
        """Change the playback speed of a clip.

        Args:
            speed: Speed percentage (100 = normal, 200 = 2x, 50 = half speed).
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.
        """
        if track_index > 0 and clip_index > 0:
            item = _get_clip_by_index(track_index, clip_index)
        else:
            item = _get_clip_at_playhead()

        mpi = item.GetMediaPoolItem()
        if mpi and mpi.SetClipProperty("Speed", str(speed)):
            return f"Set speed to {speed}% on '{item.GetName()}'"
        return f"Failed to set speed. Try using the Retime controls in the Edit page."

    @mcp.tool()
    def resolve_set_clip_enabled(
        enabled: bool,
        track_index: int = 0,
        clip_index: int = 0,
    ) -> str:
        """Enable or disable a clip on the timeline.

        Args:
            enabled: True to enable, False to disable.
            track_index: Video track (1-based). 0 = use playhead.
            clip_index: Clip position on track (1-based). 0 = use playhead.
        """
        if track_index > 0 and clip_index > 0:
            item = _get_clip_by_index(track_index, clip_index)
        else:
            item = _get_clip_at_playhead()

        item.SetClipEnabled(enabled)
        state = "enabled" if enabled else "disabled"
        return f"Clip '{item.GetName()}' {state}."

    @mcp.tool()
    def resolve_create_compound_clip(
        track_index: int = 1,
        start_clip: int = 1,
        end_clip: int = 0,
        name: str = "Compound Clip",
    ) -> str:
        """Create a compound clip from a range of clips on a track.

        Args:
            track_index: Video track (1-based, default: 1).
            start_clip: First clip index (1-based, default: 1).
            end_clip: Last clip index (1-based, default: all remaining).
            name: Name for the compound clip.
        """
        tl = get_timeline()
        items = tl.GetItemListInTrack("video", track_index)
        if not items:
            return "No clips on the specified track."

        if end_clip <= 0:
            end_clip = len(items)

        selection = items[start_clip - 1:end_clip]
        if not selection:
            return "No clips in the specified range."

        result = tl.CreateCompoundClip(selection, {"name": name})
        if result:
            return f"Created compound clip '{name}' from {len(selection)} clips."
        return "Failed to create compound clip."

    def _find_media_pool_clip(name: str):
        """Find a media pool item by name, searching all folders."""
        pool = get_project().GetMediaPool()

        def search_folder(folder):
            for clip in folder.GetClipList():
                if clip.GetName() == name:
                    return clip
            for sub in folder.GetSubFolderList():
                result = search_folder(sub)
                if result:
                    return result
            return None

        return search_folder(pool.GetRootFolder())

    @mcp.tool()
    def resolve_delete_clip(
        track_type: str = "video",
        track_index: int = 2,
        clip_index: int = 1,
        ripple: bool = False,
    ) -> str:
        """Delete a clip from the timeline.

        Args:
            track_type: "video" or "audio" (default: "video").
            track_index: Track number (1-based, default: 2).
            clip_index: Clip position on track (1-based, default: 1).
            ripple: If True, ripple delete (close the gap). Default: False.
        """
        tl = get_timeline()
        items = tl.GetItemListInTrack(track_type, track_index)
        if not items or clip_index < 1 or clip_index > len(items):
            return f"No clip at {track_type} track {track_index}, index {clip_index}."

        clip = items[clip_index - 1]
        name = clip.GetName()
        start = clip.GetStart()
        end = clip.GetEnd()

        result = tl.DeleteClips([clip], ripple)
        if result:
            return json.dumps({
                "deleted": name,
                "record_start": start,
                "record_end": end,
                "duration_frames": end - start,
                "ripple": ripple,
            }, indent=2)
        return f"Failed to delete clip '{name}'."

    @mcp.tool()
    def resolve_replace_clip(
        track_index: int,
        clip_index: int,
        new_clip_name: str,
        source_start_frame: int = 0,
        source_end_frame: int = 0,
        media_type: int = 1,
    ) -> str:
        """Replace a clip on the timeline with a different media pool clip.

        Equivalent to a three-point overwrite edit: deletes the old clip and
        inserts the new clip at the same timeline position. Source in/out points
        control which portion of the new clip is used.

        Args:
            track_index: Video track number (1-based, e.g., 2 for V2).
            clip_index: Clip position on that track (1-based).
            new_clip_name: Name of the replacement clip in the media pool.
            source_start_frame: Source in point (frame number within the clip, 0 = beginning).
            source_end_frame: Source out point (0 = auto-match the original duration).
            media_type: 1 = video only (default), 2 = audio only. Omit for both.

        Returns: JSON with the old clip info, new clip info, and timeline position.
        """
        tl = get_timeline()
        pool = get_project().GetMediaPool()

        # 1. Get the existing clip's position
        items = tl.GetItemListInTrack("video", track_index)
        if not items or clip_index < 1 or clip_index > len(items):
            return f"No clip at video track {track_index}, index {clip_index}."

        old_clip = items[clip_index - 1]
        old_name = old_clip.GetName()
        record_start = old_clip.GetStart()
        record_end = old_clip.GetEnd()
        old_duration = record_end - record_start

        # 2. Find the replacement clip in media pool
        new_mp_item = _find_media_pool_clip(new_clip_name)
        if not new_mp_item:
            return f"Could not find '{new_clip_name}' in the media pool."

        # 3. Calculate source end if not specified (match original duration)
        if source_end_frame <= 0:
            source_end_frame = source_start_frame + old_duration

        # 4. Delete the old clip (no ripple — keep the gap)
        delete_result = tl.DeleteClips([old_clip], False)
        if not delete_result:
            return f"Failed to delete old clip '{old_name}'. Replace aborted."

        # 5. Insert replacement at the same record position
        clip_info = {
            "mediaPoolItem": new_mp_item,
            "trackIndex": track_index,
            "recordFrame": record_start,
            "startFrame": source_start_frame,
            "endFrame": source_end_frame,
            "mediaType": media_type,
        }
        new_items = pool.AppendToTimeline([clip_info])

        if new_items:
            return json.dumps({
                "replaced": old_name,
                "with": new_clip_name,
                "track": track_index,
                "record_position": record_start,
                "source_in": source_start_frame,
                "source_out": source_end_frame,
                "duration_frames": source_end_frame - source_start_frame,
                "media_type": "video only" if media_type == 1 else "audio only" if media_type == 2 else "video+audio",
            }, indent=2)
        return f"Deleted '{old_name}' but failed to insert '{new_clip_name}'. You may need to undo (Cmd+Z)."
