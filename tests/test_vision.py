import asyncio
import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from PIL import Image
from resolve_mcp.tools import vision
from resolve_mcp.services.moondream import _prepare_image


def test_raw_rgb_thumbnail_is_encoded_as_png(monkeypatch, tmp_path):
    project, timeline = Mock(), Mock()
    project.ExportCurrentFrameAsStill.return_value = False
    timeline.GetCurrentClipThumbnailImage.return_value = {
        "width": 1, "height": 1, "format": "RGB", "data": base64.b64encode(bytes([255, 0, 0])).decode()}
    monkeypatch.setattr(vision, "get_project", lambda: project)
    monkeypatch.setattr(vision, "get_timeline", lambda: timeline)
    path = vision._grab_current_frame()
    try:
        with Image.open(path) as image:
            assert image.getpixel((0, 0)) == (255, 0, 0)
    finally:
        Path(path).unlink()


def test_grayscale_image_prepared_in_memory(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("L", (2000, 500), 128).save(path)
    result = _prepare_image(str(path))
    with Image.open(BytesIO(base64.b64decode(result.split(",")[1]))) as image:
        assert image.mode == "RGB"
        assert image.width <= 1920
    assert len(list(tmp_path.iterdir())) == 1


def test_frame_cleanup_after_api_failure(monkeypatch, tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"fake")
    timeline = Mock()
    timeline.GetCurrentTimecode.return_value = "01:00:00:00"
    monkeypatch.setattr(vision.moondream, "is_available", lambda: True)
    monkeypatch.setattr(vision, "_grab_current_frame", lambda: str(path))
    monkeypatch.setattr(vision, "get_timeline", lambda: timeline)
    operation = AsyncMock(side_effect=RuntimeError("cloud failure"))
    try:
        asyncio.run(vision.analyze_current(operation, "test"))
    except RuntimeError:
        pass
    assert not path.exists()


def test_frame_cleanup_if_timeline_disappears(monkeypatch, tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"fake")
    monkeypatch.setattr(vision.moondream, "is_available", lambda: True)
    monkeypatch.setattr(vision, "_grab_current_frame", lambda: str(path))
    monkeypatch.setattr(vision, "get_timeline", Mock(side_effect=RuntimeError("timeline closed")))
    try:
        asyncio.run(vision.analyze_current(AsyncMock(), "test"))
    except RuntimeError:
        pass
    assert not path.exists()
