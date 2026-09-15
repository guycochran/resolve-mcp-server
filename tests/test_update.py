"""Connection lifecycle and all requested state resources."""
import json
from unittest.mock import Mock
import pytest
from resolve_mcp.services import resolve_connection as conn
from resolve_mcp import resources


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(conn, "_resolve", None)
    monkeypatch.setattr(conn, "_last_checked", float("-inf"))
    monkeypatch.setattr(conn, "_last_attempt", float("-inf"))


def test_platform_discovery_and_overrides():
    assert "ProgramData" in conn.scripting_paths("win32", {})
    assert conn.scripting_paths("darwin", {}).startswith("/Library/")
    assert conn.scripting_paths("win32", {"PYTHONPATH_RESOLVE": "custom"}) == "custom"
    assert conn.scripting_paths("darwin", {"RESOLVE_SCRIPT_API": "/custom"}).replace("\\", "/") == "/custom/Modules"


def test_cached_connection_does_not_reconnect(monkeypatch):
    resolve = Mock()
    monkeypatch.setattr(conn, "_resolve", resolve)
    monkeypatch.setattr(conn, "_last_checked", conn.time.monotonic())
    connect = Mock()
    monkeypatch.setattr(conn, "_connect", connect)
    assert conn.get_resolve() is resolve
    connect.assert_not_called()
    resolve.GetProductName.assert_not_called()


def test_stale_connection_recovers(monkeypatch):
    stale, fresh = Mock(), Mock()
    stale.GetProductName.return_value = None
    fresh.GetProductName.return_value = "DaVinci Resolve Studio"
    monkeypatch.setattr(conn, "_resolve", stale)
    loader = Mock(return_value=Mock(scriptapp=Mock(return_value=fresh)))
    monkeypatch.setattr(conn.importlib, "import_module", loader)
    assert conn.get_resolve() is fresh
    loader.assert_called_once()


def test_failure_cooldown_and_forced_reconnect(monkeypatch):
    loader = Mock(side_effect=ImportError("missing native module"))
    monkeypatch.setattr(conn.importlib, "import_module", loader)
    assert not conn.is_connected()
    assert not conn.is_connected()
    assert loader.call_count == 1
    assert not conn.reconnect()
    assert loader.call_count == 2
    with pytest.raises(RuntimeError, match="Scripting modules"):
        conn.get_resolve()
    assert "missing native module" in conn.status()["error"]


@pytest.mark.parametrize("name", resources.RESOURCE_URIS)
def test_resources_fail_gracefully_when_disconnected(monkeypatch, name):
    monkeypatch.setattr(conn, "status", lambda: {"connected": False, "error": "offline"})
    for fn in ("get_project", "get_project_manager"):
        monkeypatch.setattr(conn, fn, Mock(side_effect=RuntimeError("offline")))
    result = json.loads(resources.read_snapshot(name))
    if name == "system/status":
        assert result["data"]["connected"] is False
    else:
        assert result["success"] is False
        assert result["error"]["message"] == "offline"


def test_resources_registered_and_no_project_error(monkeypatch, registry):
    resources.register(registry)
    assert len(registry.resources) == 16
    monkeypatch.setattr(conn, "get_project", Mock(side_effect=RuntimeError("No project")))
    assert json.loads(registry.resources["resolve://project/current"]())["success"] is False


def test_no_timeline_error(monkeypatch):
    monkeypatch.setattr(conn, "get_project", Mock())
    monkeypatch.setattr(conn, "get_timeline", Mock(side_effect=RuntimeError("No timeline")))
    assert json.loads(resources.read_snapshot("timeline/items"))["error"]["message"] == "No timeline"


def test_tracks_include_audio_video_subtitles_without_mutation(monkeypatch):
    timeline, project = Mock(), Mock()
    timeline.GetTrackCount.return_value = 1
    timeline.GetTrackName.return_value = "Track"
    timeline.GetIsTrackEnabled.return_value = True
    timeline.GetIsTrackLocked.return_value = False
    timeline.GetItemListInTrack.return_value = []
    monkeypatch.setattr(conn, "get_project", lambda: project)
    monkeypatch.setattr(conn, "get_timeline", lambda: timeline)
    value = json.loads(resources.read_snapshot("timeline/items"))
    assert [t["type"] for t in value["data"]] == ["video", "audio", "subtitle"]
    assert not any(call[0].startswith(("Set", "Delete", "Create", "Add")) for call in timeline.mock_calls)