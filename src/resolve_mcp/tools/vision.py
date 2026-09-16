"""Moondream VLM analysis: frames leave the workstation only on these requests."""
import base64
import json
import os
import tempfile
from pathlib import Path

from PIL import Image
from ..services.resolve_connection import get_project, get_timeline, get_resolve
from ..services import moondream
from ..services.lookup import validate_track
from ..services.timecode import from_frame


def _grab_current_frame() -> str:
    """Unique file per request; callers delete it in finally."""
    fd, output_path = tempfile.mkstemp(prefix="resolve-mcp-", suffix=".png")
    os.close(fd)
    try:
        if get_project().ExportCurrentFrameAsStill(output_path):
            return output_path
        thumb = get_timeline().GetCurrentClipThumbnailImage()
        if thumb and thumb.get("data"):
            data = base64.b64decode(thumb["data"])
            # Resolve documents raw RGB bytes, not a PNG-encoded payload.
            Image.frombytes("RGB", (int(thumb["width"]), int(thumb["height"])), data).save(output_path)
            return output_path
        raise RuntimeError("Cannot grab frame. Use the Color/Edit page with a clip under the playhead.")
    except Exception:
        Path(output_path).unlink(missing_ok=True)
        raise


async def analyze_current(operation, argument):
    if not moondream.is_available():
        raise RuntimeError("Set MOONDREAM_API_KEY before requesting cloud frame analysis.")
    path = _grab_current_frame()
    try:
        timecode = get_timeline().GetCurrentTimecode()
        result = await operation(path, argument)
        return timecode, result
    finally:
        Path(path).unlink(missing_ok=True)


def register(mcp):
    @mcp.tool()
    async def resolve_describe_frame(detail: str = "normal") -> str:
        """Send the current frame to Moondream for a caption. detail: short or normal."""
        if detail not in ("short", "normal"):
            raise ValueError("detail must be short or normal.")
        timecode, result = await analyze_current(moondream.caption, detail)
        return json.dumps({"timecode": timecode, "description": result})

    @mcp.tool()
    async def resolve_detect_in_frame(object_description: str) -> str:
        """Send the current frame to Moondream to detect described objects and return bounding boxes."""
        timecode, result = await analyze_current(moondream.detect, object_description)
        return json.dumps({"timecode": timecode, "query": object_description, "detections": result, "count": len(result)})

    @mcp.tool()
    async def resolve_ask_about_frame(question: str) -> str:
        """Send the current frame to Moondream for visual question answering."""
        timecode, result = await analyze_current(moondream.query, question)
        return json.dumps({"timecode": timecode, "question": question, "answer": result})

    @mcp.tool()
    async def resolve_find_shots_by_visual_description(object_description: str, track_index: int = 1,
                                                       max_clips: int = 10) -> dict:
        """Look for objects such as an airplane in timeline shots using Moondream.
        Sends ONE midpoint timeline frame per clip (up to 50) to the cloud; may miss objects elsewhere.
        Analyzes the visible composite, including overlays/upper tracks. Temporarily moves playhead/page.
        Reports sampled clip indices, matches and restoration status; not exhaustive source-media search."""
        if not object_description.strip() or not 1 <= max_clips <= 50:
            raise ValueError("Provide a description and max_clips between 1 and 50.")
        if not moondream.is_available():
            raise RuntimeError("Set MOONDREAM_API_KEY before requesting cloud frame analysis.")
        timeline, resolve = get_timeline(), get_resolve()
        validate_track(timeline, "video", track_index)
        all_items = timeline.GetItemListInTrack("video", track_index) or []
        old_timecode, old_page = timeline.GetCurrentTimecode(), resolve.GetCurrentPage()
        fps = timeline.GetSetting("timelineFrameRate")
        result = {"success": True, "samples": [], "scope": "one visible composite frame per timeline clip",
                  "total_clips": len(all_items), "truncated": len(all_items) > max_clips}
        try:
            if not resolve.OpenPage("edit"):
                raise RuntimeError("Could not open Edit page for frame capture.")
            for index, item in enumerate(all_items[:max_clips], 1):
                frame = int((item.GetStart() + item.GetEnd() - 1) // 2)
                tc = from_frame(frame, fps, ";" in old_timecode)
                if not timeline.SetCurrentTimecode(tc):
                    raise RuntimeError(f"Could not seek to {tc}.")
                actual_tc, detections = await analyze_current(moondream.detect, object_description)
                result["samples"].append({"clip": item.GetName(), "clip_index": index, "track_index": track_index,
                                          "timecode": actual_tc, "matched": bool(detections), "detections": detections})
        except Exception as exc:
            result.update(success=False, error=str(exc))
        finally:
            restored = {}
            for name, operation, value in (("playhead", timeline.SetCurrentTimecode, old_timecode),
                                           ("page", resolve.OpenPage, old_page)):
                try:
                    restored[name] = bool(operation(value))
                except Exception as exc:
                    restored[name] = str(exc)
            result["restored"] = restored
        return result
