"""Result consistency, recovery-policy visibility, and safe export defaults."""
import json
from unittest.mock import Mock

from resolve_mcp.services.results import render_succeeded
from resolve_mcp.tools import editing, markers, render, workflows


def _editing_tools(scene, monkeypatch, registry):
    monkeypatch.setattr(editing, "get_timeline", lambda: scene.timeline)
    monkeypatch.setattr(editing, "get_project", lambda: scene.project)
    editing.register(registry)
    return registry.tools


def test_legacy_replace_rejection_is_structured_json(scene, monkeypatch, registry):
    tools = _editing_tools(scene, monkeypatch, registry)
    scene.media.GetClipProperty.return_value = {"Frames": "72", "FPS": "24"}
    result = json.loads(tools["resolve_replace_clip"](2, 1, "New"))
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_request"
    scene.timeline.DeleteClips.assert_not_called()


def test_legacy_marker_rejection_is_structured_json(monkeypatch, registry):
    timeline = Mock()
    monkeypatch.setattr(markers, "get_timeline", lambda: timeline)
    markers.register(registry)
    result = json.loads(registry.tools["resolve_add_marker"](color="Plaid", frame=5))
    assert result == {"success": False, "error": {"code": "invalid_request",
                                                  "message": "Invalid marker color, position, or duration."}}
    timeline.AddMarker.assert_not_called()


def test_replacement_dry_run_shows_recovery_policy(scene):
    from resolve_mcp.services import replacement as rep
    plan = rep.replace_clip(2, 1, "New", dry_run=True)
    assert "backup" in plan["recovery_policy"] and "cleanup" in plan["recovery_policy"]
    scene.timeline.DuplicateTimeline.assert_not_called()


def test_refused_delete_without_links_reports_original_untouched(scene):
    from resolve_mcp.services import replacement as rep
    scene.timeline.DeleteClips.return_value = False
    result = rep.replace_clip(2, 1, "New")
    assert result["recovery"]["original_timeline_may_be_modified"] is False


def test_failed_insert_after_delete_reports_original_modified(scene):
    from resolve_mcp.services import replacement as rep
    scene.pool.AppendToTimeline.return_value = []
    result = rep.replace_clip(2, 1, "New")
    assert result["recovery"]["original_timeline_may_be_modified"] is True


def _broll(scene, monkeypatch, registry):
    for name, value in (("get_project", scene.project), ("get_timeline", scene.timeline),
                        ("get_media_pool", scene.pool)):
        monkeypatch.setattr(workflows, name, lambda v=value: v)
    monkeypatch.setattr(workflows, "find_media", lambda *a: scene.media)
    scene.timeline.GetItemListInTrack.return_value = []
    workflows.register(registry)
    return registry.tools["resolve_insert_broll"]


def test_broll_dry_run_shows_recovery_policy(scene, monkeypatch, registry):
    plan = _broll(scene, monkeypatch, registry)("New", 86400, 30)
    assert plan["dry_run"] and "recovery_policy" in plan
    scene.timeline.DuplicateTimeline.assert_not_called()


def test_broll_failure_uses_standard_error_envelope(scene, monkeypatch, registry):
    insert = _broll(scene, monkeypatch, registry)
    scene.new.GetEnd.return_value = 86429
    result = insert("New", 86400, 30, dry_run=False)
    assert result["error"]["code"] == "broll_failed"
    assert result["recovery"]["original_timeline"] == "Main"
    assert result["recovery"]["timeline"] == "Recovery"
    assert result["recovery"]["original_timeline_may_be_modified"] is False
    assert result["original_repair"]["bad_insert_removed"] is True


def test_quick_export_never_enables_upload(monkeypatch, registry):
    project = Mock()
    project.RenderWithQuickExport.return_value = {"CompletionPercentage": 100, "JobStatus": "Render Complete"}
    monkeypatch.setattr(render, "get_project", lambda: project)
    render.register(registry)
    result = json.loads(registry.tools["resolve_quick_export"]("YouTube", "/tmp/out", "clip"))
    params = project.RenderWithQuickExport.call_args.args[1]
    assert params["EnableUpload"] is False
    assert result["success"] is True and result["upload_enabled"] is False


def test_render_status_interpretation():
    assert render_succeeded({"JobStatus": "Render Complete"}) is True
    assert render_succeeded({"Status": "Failed"}) is False
    assert render_succeeded({"Error": "No timeline"}) is False
    assert render_succeeded({"CompletionPercentage": 0}) is None
    assert render_succeeded(False) is False


def test_transcription_false_is_marked_retryable(monkeypatch, registry):
    from resolve_mcp.tools import analysis
    resolve, pool, folder, clip = Mock(), Mock(), Mock(), Mock()
    resolve.GetVersion.return_value = [21, 1]
    resolve.GetProductName.return_value = "DaVinci Resolve Studio"
    clip.GetName.return_value = "Speech"
    clip.TranscribeAudio.return_value = False
    folder.GetClipList.return_value = [clip]
    pool.GetCurrentFolder.return_value = folder
    monkeypatch.setattr(analysis, "get_resolve", lambda: resolve)
    monkeypatch.setattr(analysis, "get_media_pool", lambda: pool)
    analysis.register(registry)
    result = registry.tools["resolve_transcribe_audio"]("Speech")
    assert result["success"] is False and result["retryable"] is True
    assert "retry" in result["hint"]
    clip.ClearTranscription.return_value = False
    assert "retryable" not in registry.tools["resolve_clear_transcription"]("Speech")
