from unittest.mock import Mock
import pytest
from resolve_mcp.tools import analysis, workflows


@pytest.fixture
def ai(monkeypatch, registry):
    resolve, project, folder, pool, clip = [Mock() for _ in range(5)]
    resolve.GetVersion.return_value = [21, 0, 4]
    folder.GetName.return_value = "Interviews"
    folder.GetClipList.return_value = [clip]
    clip.GetName.return_value = "Interview"
    clip.GetMediaId.return_value = "clip-id"
    pool.GetCurrentFolder.return_value = folder
    monkeypatch.setattr(analysis, "get_resolve", lambda: resolve)
    monkeypatch.setattr(analysis, "get_project", lambda: project)
    monkeypatch.setattr(analysis, "get_media_pool", lambda: pool)
    analysis.register(registry)
    return Mock(resolve=resolve, project=project, folder=folder, clip=clip, tools=registry.tools)


def test_speaker_detection_flag(ai):
    ai.clip.TranscribeAudio.return_value = True
    assert ai.tools["resolve_transcribe_audio"]("Interview", True)["success"]
    ai.clip.TranscribeAudio.assert_called_once_with(True)


def test_older_resolve_fails_without_analysis(ai):
    ai.resolve.GetVersion.return_value = [20, 3]
    assert not ai.tools["resolve_classify_audio"]()["success"]
    ai.folder.PerformAudioClassification.assert_not_called()


def test_ambiguous_clip_refused(ai):
    ai.folder.GetClipList.return_value = [ai.clip, ai.clip]
    assert not ai.tools["resolve_transcribe_audio"]("Interview")["success"]
    ai.clip.TranscribeAudio.assert_not_called()


def test_slate_uses_resolve_enum(ai):
    ai.resolve.MARKER_GREEN = 3
    ai.clip.AnalyzeForSlate.return_value = True
    assert ai.tools["resolve_analyze_slate"]("Interview")["success"]
    ai.clip.AnalyzeForSlate.assert_called_once_with(3)


def test_background_none_return_is_not_failure(ai):
    ai.resolve.DisableBackgroundTasksForCurrentResolveSession.return_value = None
    assert ai.tools["resolve_disable_background_tasks"]()["success"]


def test_reset_is_project_scoped(ai):
    ai.project.ResetIntellisearchAnalysis.return_value = True
    assert ai.tools["resolve_reset_intellisearch"]()["scope"] == "entire current project"
    ai.project.ResetIntellisearchAnalysis.assert_called_once()


def test_speech_does_not_touch_timeline(ai):
    ai.project.GenerateSpeech.return_value = ai.clip
    assert ai.tools["resolve_generate_speech"]("Hello", "narration")["success"]
    settings, tc = ai.project.GenerateSpeech.call_args.args
    assert settings["TextInput"] == "Hello"
    assert settings["AddToTimeline"] is False
    assert tc == ""
    ai.project.GetCurrentTimeline.assert_not_called()


def test_speech_rejects_long_input(ai):
    assert not ai.tools["resolve_generate_speech"]("a" * 351, "voice")["success"]
    ai.project.GenerateSpeech.assert_not_called()


def test_api_false_is_failure(ai):
    ai.folder.PerformAudioClassification.return_value = False
    assert not ai.tools["resolve_classify_audio"]()["success"]


def test_deblur_creates_new_media(ai):
    ai.clip.RemoveMotionBlur.return_value = ai.clip
    assert ai.tools["resolve_remove_motion_blur"]("Interview", "deblur")["media_id"] == "clip-id"


def test_marker_batch_validated_before_mutation(scene):
    scene.timeline.GetMarkers.return_value = {}
    with pytest.raises(ValueError):
        workflows.add_chapters(scene.timeline, [{"frame": 5, "name": "A"}, {"frame": 500, "name": "B"}], "Blue")
    scene.timeline.AddMarker.assert_not_called()


def test_marker_partial_failure_is_explicit(scene):
    scene.timeline.GetMarkers.return_value = {}
    scene.timeline.AddMarker.side_effect = [True, False]
    result = workflows.add_chapters(scene.timeline, [{"frame": 5, "name": "A"}, {"frame": 6, "name": "B"}], "Blue")
    assert not result["success"]
    assert result["created"] == [{"frame": 5, "name": "A", "note": ""}]


def test_broll_overlap_refused_without_edit(scene, monkeypatch, registry):
    for name, value in (("get_project", scene.project), ("get_timeline", scene.timeline),
                        ("get_media_pool", scene.pool)):
        monkeypatch.setattr(workflows, name, lambda v=value: v)
    monkeypatch.setattr(workflows, "find_media", lambda *a: scene.media)
    workflows.register(registry)
    result = registry.tools["resolve_insert_broll"]("New", 86405, 30, dry_run=False)
    assert not result["success"]
    scene.pool.AppendToTimeline.assert_not_called()


def test_broll_uses_exclusive_source_end_at_media_boundary(scene, monkeypatch, registry):
    for name, value in (("get_project", scene.project), ("get_timeline", scene.timeline),
                        ("get_media_pool", scene.pool)):
        monkeypatch.setattr(workflows, name, lambda v=value: v)
    monkeypatch.setattr(workflows, "find_media", lambda *a: scene.media)
    scene.timeline.GetItemListInTrack.return_value = []
    scene.media.GetClipProperty.return_value = {"Frames": "192", "FPS": "24"}

    def append(infos):
        info = infos[0]
        scene.new.GetStart.return_value = info["recordFrame"]
        scene.new.GetEnd.return_value = info["recordFrame"] + info["endFrame"] - info["startFrame"]
        return [scene.new]

    scene.pool.AppendToTimeline.side_effect = append
    workflows.register(registry)
    result = registry.tools["resolve_insert_broll"]("New", 86400, 192, track_index=1, dry_run=False)
    assert result["success"]
    info = scene.pool.AppendToTimeline.call_args.args[0][0]
    assert (info["startFrame"], info["endFrame"]) == (0, 192)


def test_timeline_clip_lookup_uses_exclusive_end(scene, monkeypatch, registry):
    monkeypatch.setattr(workflows, "get_timeline", lambda: scene.timeline)
    workflows.register(registry)
    assert len(registry.tools["resolve_find_timeline_clip"](seconds=0, track_index=1)["matches"]) == 1
    assert len(registry.tools["resolve_find_timeline_clip"](seconds=5, track_index=1)["matches"]) == 0


def test_broll_bad_insert_is_removed(scene, monkeypatch, registry):
    for name, value in (("get_project", scene.project), ("get_timeline", scene.timeline),
                        ("get_media_pool", scene.pool)):
        monkeypatch.setattr(workflows, name, lambda v=value: v)
    monkeypatch.setattr(workflows, "find_media", lambda *a: scene.media)
    scene.timeline.GetItemListInTrack.return_value = []
    scene.new.GetStart.return_value = 86400
    scene.new.GetEnd.return_value = 86429  # one frame short of the requested 30
    workflows.register(registry)
    result = registry.tools["resolve_insert_broll"]("New", 86400, 30, dry_run=False)
    assert result["success"] is False
    assert result["original_repair"]["bad_insert_removed"] is True
    scene.timeline.DeleteClips.assert_any_call([scene.new], False)
