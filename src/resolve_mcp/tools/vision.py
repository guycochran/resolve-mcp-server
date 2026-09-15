"""Vision / Moondream tools — frame analysis, scene description, object detection."""

import json
import os
import tempfile
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_project, get_timeline
from ..services import moondream


def _grab_current_frame() -> str:
    """Export the current frame as a still image and return the file path."""
    project = get_project()
    tmp_dir = os.path.join(tempfile.gettempdir(), "resolve-mcp-frames")
    os.makedirs(tmp_dir, exist_ok=True)
    output_path = os.path.join(tmp_dir, "current_frame.png")

    if project.ExportCurrentFrameAsStill(output_path):
        return output_path

    # Fallback: try grabbing via timeline
    tl = get_timeline()
    thumb = tl.GetCurrentClipThumbnailImage()
    if thumb and thumb.get("data"):
        import base64
        data = base64.b64decode(thumb["data"])
        with open(output_path, "wb") as f:
            f.write(data)
        return output_path

    raise RuntimeError(
        "Failed to grab current frame. Make sure you're on the Color or Edit page "
        "with a clip under the playhead."
    )


def register(mcp: FastMCP):

    @mcp.tool()
    async def resolve_describe_frame(detail: str = "normal") -> str:
        """Describe what's visible in the current frame using AI vision.

        Grabs the frame at the current playhead and sends it to Moondream for
        natural language description. Great for logging, accessibility, or
        understanding scene content.

        Args:
            detail: "short" for a brief caption, "normal" for a detailed description.
        """
        if not moondream.is_available():
            return "Moondream API key not configured. Set MOONDREAM_API_KEY in your environment."

        frame_path = _grab_current_frame()
        tl = get_timeline()
        timecode = tl.GetCurrentTimecode()

        caption = await moondream.caption(frame_path, length=detail)

        return json.dumps({
            "timecode": timecode,
            "description": caption,
        }, indent=2)

    @mcp.tool()
    async def resolve_detect_in_frame(object_description: str) -> str:
        """Detect objects matching a description in the current frame.

        Uses AI vision to find and locate objects. Returns bounding boxes
        for each detection.

        Args:
            object_description: What to look for (e.g., "person", "microphone", "laptop", "text overlay").
        """
        if not moondream.is_available():
            return "Moondream API key not configured. Set MOONDREAM_API_KEY in your environment."

        frame_path = _grab_current_frame()
        tl = get_timeline()
        timecode = tl.GetCurrentTimecode()

        detections = await moondream.detect(frame_path, object_description)

        return json.dumps({
            "timecode": timecode,
            "query": object_description,
            "detections": detections,
            "count": len(detections),
        }, indent=2)

    @mcp.tool()
    async def resolve_ask_about_frame(question: str) -> str:
        """Ask a question about the current frame using AI vision.

        Can answer questions like:
        - "How many people are in this shot?"
        - "What color is the background?"
        - "Is there a lower third visible?"
        - "What emotion does the person appear to express?"

        Args:
            question: Natural language question about the frame content.
        """
        if not moondream.is_available():
            return "Moondream API key not configured. Set MOONDREAM_API_KEY in your environment."

        frame_path = _grab_current_frame()
        tl = get_timeline()
        timecode = tl.GetCurrentTimecode()

        answer = await moondream.query(frame_path, question)

        return json.dumps({
            "timecode": timecode,
            "question": question,
            "answer": answer,
        }, indent=2)
