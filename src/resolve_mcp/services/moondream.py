"""
Moondream Vision API client.

Provides scene description, object detection, and visual Q&A
for DaVinci Resolve frame grabs.
"""

import base64
import os
import tempfile
from pathlib import Path

import httpx
from PIL import Image

API_BASE = "https://api.moondream.ai/v1"
_api_key: str | None = None


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        _api_key = os.environ.get("MOONDREAM_API_KEY", "")
    if not _api_key:
        raise RuntimeError(
            "MOONDREAM_API_KEY not set. Get a free key at https://console.moondream.ai "
            "and set it in your environment or .env file."
        )
    return _api_key


def _prepare_image(image_path: str) -> str:
    """Convert image to JPEG and return as base64 data URL.

    Resolve exports large PNGs (6MB+). Moondream expects reasonably-sized
    images, so we convert to JPEG and cap the resolution at 1920px wide.
    """
    img = Image.open(image_path)

    # Resize if wider than 1920
    max_width = 1920
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    # Convert to RGB if needed (e.g., RGBA PNGs)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Save as JPEG to a temp file
    tmp_path = os.path.join(tempfile.gettempdir(), "resolve-mcp-frames", "moondream_input.jpg")
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    img.save(tmp_path, "JPEG", quality=85)

    data = Path(tmp_path).read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


async def caption(image_path: str, length: str = "normal") -> str:
    """Generate a natural language description of an image.

    Args:
        image_path: Path to the image file.
        length: "short" or "normal" (default).

    Returns:
        Caption string describing the image.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}/caption",
            headers={"X-Moondream-Auth": _get_api_key()},
            json={
                "image_url": _prepare_image(image_path),
                "length": length,
            },
        )
        resp.raise_for_status()
        return resp.json().get("caption", "")


async def detect(image_path: str, object_description: str) -> list[dict]:
    """Detect objects matching a text description in an image.

    Args:
        image_path: Path to the image file.
        object_description: What to look for (e.g., "person", "microphone").

    Returns:
        List of detection dicts with bounding box coordinates.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}/detect",
            headers={"X-Moondream-Auth": _get_api_key()},
            json={
                "image_url": _prepare_image(image_path),
                "object": object_description,
            },
        )
        resp.raise_for_status()
        return resp.json().get("objects", [])


async def query(image_path: str, question: str) -> str:
    """Ask a question about the contents of an image.

    Args:
        image_path: Path to the image file.
        question: Natural language question about the image.

    Returns:
        Answer string.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}/query",
            headers={"X-Moondream-Auth": _get_api_key()},
            json={
                "image_url": _prepare_image(image_path),
                "question": question,
            },
        )
        resp.raise_for_status()
        return resp.json().get("answer", "")


async def point(image_path: str, object_description: str) -> list[dict]:
    """Get point coordinates for objects matching a description.

    Args:
        image_path: Path to the image file.
        object_description: What to find (e.g., "speaker's face").

    Returns:
        List of point coordinate dicts.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}/point",
            headers={"X-Moondream-Auth": _get_api_key()},
            json={
                "image_url": _prepare_image(image_path),
                "object": object_description,
            },
        )
        resp.raise_for_status()
        return resp.json().get("points", [])


def is_available() -> bool:
    """Check if Moondream API key is configured."""
    try:
        _get_api_key()
        return True
    except RuntimeError:
        return False
