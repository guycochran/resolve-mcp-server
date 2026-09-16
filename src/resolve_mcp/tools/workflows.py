"""Editorial tasks built from documented Resolve operations."""
import math
from pathlib import Path

from ..services.resolve_connection import get_project, get_timeline, get_media_pool
from ..services.lookup import walk_folders, find_media, validate_track, item_info
from ..services.replacement import source_range, backup_timeline
from ..services.results import structured
from ..services.timecode import to_frame, fps_value, playhead_offset
from .analysis import COLORS


def add_chapters(timeline, chapters, color):
    if color not in COLORS:
        raise ValueError("Unknown marker color.")
    if not chapters or len(chapters) > 500:
        raise ValueError("Provide between 1 and 500 chapter entries.")
    duration = timeline.GetEndFrame() - timeline.GetStartFrame()
    occupied = timeline.GetMarkers() or {}
    plan = []
    for chapter in chapters:
        frame = chapter.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or not 0 <= frame < duration:
            raise ValueError("Chapter frame must be a timeline-relative integer within its duration.")
        if frame in occupied or str(frame) in occupied or any(x["frame"] == frame for x in plan):
            raise ValueError(f"A marker already exists or is duplicated at frame {frame}.")
        name, note = chapter.get("name", ""), chapter.get("note", "")
        if not isinstance(name, str) or not name.strip() or not isinstance(note, str):
            raise ValueError("Each chapter needs a nonempty string name and optional string note.")
        plan.append({"frame": frame, "name": name, "note": note})
    created = []
    for chapter in plan:
        if not timeline.AddMarker(chapter["frame"], color, chapter["name"], chapter["note"], 1):
            return {"success": False, "created": created, "failed": chapter,
                    "error": "Resolve refused this marker; earlier markers remain."}
        created.append(chapter)
    return {"success": True, "created": created}


def register(mcp):
    @mcp.tool()
    @structured
    def resolve_find_media_clip(query: str = "", metadata: dict[str, str] | None = None,
                                limit: int = 50) -> dict:
        """Find shots by case-insensitive name and/or metadata substrings across all bins.
        Returns exact names, media IDs and folder paths for unambiguous editing. Not visual search."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be 1–500.")
        results = []
        for path, folder in walk_folders(get_media_pool().GetRootFolder()):
            for clip in folder.GetClipList() or []:
                tags = clip.GetMetadata() or {}
                if query.casefold() in clip.GetName().casefold() and all(
                        value.casefold() in str(tags.get(key, "")).casefold() for key, value in (metadata or {}).items()):
                    results.append({"name": clip.GetName(), "id": clip.GetMediaId(), "folder": path, "metadata": tags})
        return {"success": True, "matches": results[:limit], "total": len(results), "truncated": len(results) > limit}

    @mcp.tool()
    @structured
    def resolve_find_timeline_clip(query: str = "", timecode: str = "", seconds: float | None = None,
                                   track_type: str = "video", track_index: int = 0) -> dict:
        """Find clips by name and/or position. timecode is absolute HH:MM:SS:FF;
        seconds is elapsed since timeline start (13:22 = 802 seconds). End frame is exclusive.
        track_index 0 searches all tracks of the selected type."""
        timeline = get_timeline()
        if track_type not in ("video", "audio", "subtitle") or track_index < 0:
            raise ValueError("Invalid track type/index.")
        if timecode and seconds is not None:
            raise ValueError("Use either timecode or seconds.")
        fps = timeline.GetSetting("timelineFrameRate")
        frame = to_frame(timecode, fps) if timecode else None
        if seconds is not None:
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError("seconds must be finite and nonnegative.")
            frame = timeline.GetStartFrame() + round(seconds * fps_value(fps))
        indices = [track_index] if track_index else range(1, timeline.GetTrackCount(track_type) + 1)
        matches = []
        for index in indices:
            validate_track(timeline, track_type, index)
            for clip_index, clip in enumerate(timeline.GetItemListInTrack(track_type, index) or [], 1):
                if query.casefold() in clip.GetName().casefold() and (
                        frame is None or clip.GetStart() <= frame < clip.GetEnd()):
                    matches.append(dict(item_info(clip), track_type=track_type, track_index=index, clip_index=clip_index))
        return {"success": True, "matches": matches, "record_frame": frame}

    @mcp.tool()
    @structured
    def resolve_insert_broll(clip_name: str, record_frame: int, duration_frames: int,
                             track_index: int = 2, source_start_frame: int = 0,
                             media_id: str = "", dry_run: bool = True) -> dict:
        """Insert video-only B-roll into an EMPTY interval on an existing video track.
        Absolute record frame; defaults to dry-run. Rejects overlap, locked tracks and FPS mismatch.
        Creates a recovery copy before an actual insertion."""
        project, timeline, pool = get_project(), get_timeline(), get_media_pool()
        validate_track(timeline, "video", track_index, writable=True)
        if record_frame < timeline.GetStartFrame():
            raise ValueError("record_frame is before timeline start.")
        media = find_media(clip_name, media_id)
        source_in, source_out_exclusive = source_range(media, timeline, source_start_frame, duration_frames)
        for item in timeline.GetItemListInTrack("video", track_index) or []:
            if record_frame < item.GetEnd() and record_frame + duration_frames > item.GetStart():
                raise ValueError(f"Destination overlaps {item.GetName()!r}. Use replace_clip for an occupied interval.")
        plan = {"success": True, "dry_run": dry_run, "clip": media.GetName(), "record_frame": record_frame,
                "duration_frames": duration_frames, "track_index": track_index, "media_type": "video only"}
        if dry_run:
            return plan
        backup = backup_timeline(project, timeline)
        try:
            inserted = pool.AppendToTimeline([{"mediaPoolItem": media, "startFrame": source_in,
                                              "endFrame": source_out_exclusive,
                                              "recordFrame": record_frame, "trackIndex": track_index, "mediaType": 1}]) or []
            if (len(inserted) != 1 or inserted[0].GetStart() != record_frame
                    or inserted[0].GetEnd() != record_frame + duration_frames):
                raise RuntimeError("Resolve did not create the requested B-roll interval.")
            return dict(plan, inserted=item_info(inserted[0]), recovery_timeline=backup.GetName())
        except Exception as exc:
            return dict(plan, success=False, error=str(exc), recovery_timeline=backup.GetName(),
                        backup_selected=bool(project.SetCurrentTimeline(backup)))

    @mcp.tool()
    @structured
    def resolve_build_rough_cut(name: str, clip_names: list[str], dry_run: bool = True) -> dict:
        """Assemble complete media clips in supplied order into a NEW timeline.
        Rejects ambiguous media and existing timeline names. Defaults to planning only.
        This is an ordered assembly; it does not infer cuts from a transcript."""
        project, pool = get_project(), get_media_pool()
        if not name.strip() or not 1 <= len(clip_names) <= 500:
            raise ValueError("Provide a timeline name and 1–500 exact clip names.")
        if any(project.GetTimelineByIndex(i).GetName() == name for i in range(1, project.GetTimelineCount() + 1)):
            raise ValueError("A timeline with this name already exists.")
        items = [find_media(clip) for clip in clip_names]
        if dry_run:
            return {"success": True, "dry_run": True, "timeline": name, "clips": clip_names}
        previous = project.GetCurrentTimeline()
        created = pool.CreateTimelineFromClips(name, items)
        restored = bool(project.SetCurrentTimeline(previous)) if previous is not None else None
        return {"success": bool(created), "timeline": name, "clips": clip_names,
                "previous_timeline_reselected": restored, "created_timeline_retained": bool(created)}

    @mcp.tool()
    @structured
    def resolve_add_marker_at_playhead(name: str, note: str = "", color: str = "Blue") -> dict:
        """Add a marker at the exact current playhead, including drop-frame timecode support."""
        timeline = get_timeline()
        return add_chapters(timeline, [{"frame": playhead_offset(timeline), "name": name, "note": note}], color)

    @mcp.tool()
    @structured
    def resolve_create_chapter_markers(chapters: list[dict], color: str = "Blue") -> dict:
        """Create markers from supplied chapter/speaker boundaries.
        Each entry: {frame: timeline-relative integer, name: string, note: optional string}.
        Validates the complete batch before writing. Does not extract transcripts or infer speaker times."""
        return add_chapters(get_timeline(), chapters, color)

    @mcp.tool()
    @structured
    def resolve_render_for_youtube(output_dir: str, filename: str, preset: str = "YouTube") -> dict:
        """Render locally with an installed Quick Export preset; explicitly disables uploading to YouTube.
        Requires an existing absolute output directory and a filename. Returns Resolve's actual status."""
        if not Path(output_dir).is_absolute() or not Path(output_dir).is_dir() or not filename.strip():
            raise ValueError("Provide an existing absolute output directory and a filename.")
        project = get_project()
        if preset not in (project.GetQuickExportRenderPresets() or []):
            raise ValueError("Preset is not installed. Read resolve://render/presets for available names.")
        if project.IsRenderingInProgress():
            raise ValueError("Resolve is already rendering.")
        result = project.RenderWithQuickExport(preset, {"TargetDir": output_dir, "CustomName": filename,
                                                        "EnableUpload": False})
        status = str(result.get("Status", "")).lower() if isinstance(result, dict) else ""
        success = (status in ("complete", "completed", "success")) if status else None
        if not result or isinstance(result, str) or (isinstance(result, dict) and result.get("Error")):
            success = False
        return {"success": success, "native_status": result, "upload_enabled": False, "preset": preset}
