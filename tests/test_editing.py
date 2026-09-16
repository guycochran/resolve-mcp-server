import json
import pytest
from unittest.mock import Mock
from resolve_mcp.services import replacement as rep
from resolve_mcp.services.transforms import set_transform
from resolve_mcp.services.lookup import timeline_clip, find_media
from resolve_mcp.services import lookup
from resolve_mcp.services.timecode import to_frame, from_frame


def test_exact_non_ripple_replace_and_exclusive_end(scene):
    result = rep.replace_clip(2, 1, "New")
    assert result["success"]
    scene.timeline.DeleteClips.assert_called_once_with([scene.old], False)
    clip_info = scene.pool.AppendToTimeline.call_args.args[0][0]
    assert clip_info["recordFrame"] == 86400
    assert clip_info["endFrame"] == 120
    assert clip_info["mediaType"] == 1
    assert result["recovery_timeline"] == "Recovery"


def test_one_frame_replacement(scene):
    scene.old.GetEnd.return_value = 86401
    scene.new.GetEnd.return_value = 86401
    assert rep.replace_clip(1, 1, "New")["success"]
    assert scene.pool.AppendToTimeline.call_args.args[0][0]["endFrame"] == 1


def test_dry_run_has_no_mutations(scene):
    result = rep.replace_clip(2, 1, "New", dry_run=True)
    assert result["dry_run"]
    assert result["source_out_exclusive"] == 120
    assert result["original"]["source_in_native"] == 10
    assert result["original"]["source_out_native"] == 129
    assert "source_out_inclusive" not in result
    scene.timeline.DuplicateTimeline.assert_not_called()
    scene.timeline.DeleteClips.assert_not_called()
    scene.pool.AppendToTimeline.assert_not_called()


@pytest.mark.parametrize("start,end", [(-1, 0), (450, 0), (0, 119), (5, 1), (380, 501)])
def test_invalid_bounds_do_not_delete(scene, start, end):
    with pytest.raises(ValueError):
        rep.replace_clip(2, 1, "New", start, end)
    scene.timeline.DeleteClips.assert_not_called()


@pytest.mark.parametrize("start,duration,end_exclusive", [
    (0, 192, 0), (0, 192, 192), (191, 1, 0), (191, 1, 192), (12, 180, 192),
])
def test_source_range_allows_exact_media_end(scene, start, duration, end_exclusive):
    scene.media.GetClipProperty.return_value = {"Frames": "192", "FPS": "24"}
    assert rep.source_range(scene.media, scene.timeline, start, duration, end_exclusive) == (start, 192)


@pytest.mark.parametrize("start,duration,end_exclusive", [(0, 192, 191), (1, 192, 0), (192, 1, 0)])
def test_source_range_rejects_short_range_and_media_overrun(scene, start, duration, end_exclusive):
    scene.media.GetClipProperty.return_value = {"Frames": "192", "FPS": "24"}
    with pytest.raises(ValueError):
        rep.source_range(scene.media, scene.timeline, start, duration, end_exclusive)


def test_replacement_192_frames_uses_exclusive_append_bound(scene):
    scene.old.GetEnd.return_value = 86592
    scene.media.GetClipProperty.return_value = {"Frames": "192", "FPS": "24"}

    def append(infos):
        info = infos[0]
        # Model the measured native behavior, independently of the range helper.
        scene.new.GetStart.return_value = info["recordFrame"]
        scene.new.GetEnd.return_value = info["recordFrame"] + info["endFrame"] - info["startFrame"]
        scene.new.GetDuration.return_value = info["endFrame"] - info["startFrame"]
        return [scene.new]

    scene.pool.AppendToTimeline.side_effect = append
    result = rep.replace_clip(1, 1, "New")
    assert result["success"]
    assert result["inserted"]["duration"] == 192
    assert result["inserted"]["end"] == 86592


def test_fps_mismatch_rejected_before_delete(scene):
    scene.media.GetClipProperty.return_value = {"Frames": "500", "FPS": "30"}
    with pytest.raises(ValueError, match="frame rates differ"):
        rep.replace_clip(2, 1, "New")
    scene.timeline.DeleteClips.assert_not_called()


def test_locked_track_does_not_delete(scene):
    scene.timeline.GetIsTrackLocked.return_value = True
    with pytest.raises(ValueError, match="locked"):
        rep.replace_clip(2, 1, "New")
    scene.timeline.DeleteClips.assert_not_called()


def test_missing_media_does_not_delete(scene, monkeypatch):
    monkeypatch.setattr(rep, "find_media", Mock(side_effect=ValueError("not found")))
    with pytest.raises(ValueError):
        rep.replace_clip(2, 1, "Missing")
    scene.timeline.DeleteClips.assert_not_called()


def test_backup_failure_prevents_delete(scene):
    scene.timeline.DuplicateTimeline.return_value = None
    with pytest.raises(RuntimeError):
        rep.replace_clip(2, 1, "New")
    scene.timeline.DeleteClips.assert_not_called()


@pytest.mark.parametrize("failure", [[], RuntimeError("native failure")])
def test_insert_failure_selects_full_backup(scene, failure):
    if isinstance(failure, Exception):
        scene.pool.AppendToTimeline.side_effect = failure
    else:
        scene.pool.AppendToTimeline.return_value = failure
    result = rep.replace_clip(2, 1, "New")
    assert result["success"] is False
    assert result["deleted_original"] is True
    assert result["recovery"]["backup_selected"]
    scene.project.SetCurrentTimeline.assert_called_with(scene.backup)


def test_wrong_insert_duration_selects_backup(scene):
    scene.new.GetEnd.return_value = 86521
    assert not rep.replace_clip(2, 1, "New")["success"]
    scene.project.SetCurrentTimeline.assert_called_with(scene.backup)


def test_delete_refusal_does_not_append(scene):
    scene.timeline.DeleteClips.return_value = False
    result = rep.replace_clip(2, 1, "New")
    assert not result["success"]
    scene.pool.AppendToTimeline.assert_not_called()


def test_linked_audio_is_not_deleted(scene):
    audio = Mock()
    audio.GetName.return_value = "Interview"
    scene.old.GetLinkedItems.return_value = [audio]
    assert rep.replace_clip(2, 1, "New")["success"]
    scene.timeline.SetClipsLinked.assert_any_call([scene.old, audio], False)
    scene.timeline.SetClipsLinked.assert_any_call([scene.new, audio], True)
    scene.timeline.DeleteClips.assert_called_once_with([scene.old], False)


def test_audio_replacement_selects_audio_track(scene):
    assert rep.replace_clip(1, 1, "New", media_type=2)["success"]
    scene.timeline.GetItemListInTrack.assert_called_with("audio", 1)
    assert scene.pool.AppendToTimeline.call_args.args[0][0]["mediaType"] == 2


@pytest.mark.parametrize("values", [{"ZoomX": -1}, {"Opacity": 101}, {"RotationAngle": float("nan")},
                                    {"ZoomY": float("inf")}])
def test_transform_invalid_input_never_writes(values):
    item, timeline = Mock(), Mock()
    with pytest.raises(ValueError):
        set_transform(item, timeline, values)
    item.SetProperty.assert_not_called()


def test_transform_failure_reports_partial_changes():
    item, timeline = Mock(), Mock()
    item.GetName.return_value = "Clip"
    item.SetProperty.side_effect = [True, False]
    result = set_transform(item, timeline, {"ZoomX": 2, "ZoomY": 2})
    assert result["changed"] == {"ZoomX": 2}
    assert result["failed_property"] == "ZoomY"


def test_lookup_rejects_zero_and_negative_indices(scene):
    for index in (0, -1, 2):
        with pytest.raises(ValueError):
            timeline_clip(scene.timeline, "video", 1, index)


def test_lookup_rejects_duplicate_media_and_accepts_id(monkeypatch):
    a, b, folder, pool = Mock(), Mock(), Mock(), Mock()
    a.GetName.return_value = b.GetName.return_value = "Same"
    a.GetMediaId.return_value, b.GetMediaId.return_value = "a", "b"
    folder.GetClipList.return_value = [a, b]
    folder.GetSubFolderList.return_value = []
    folder.GetName.return_value = "Root"
    pool.GetRootFolder.return_value = folder
    monkeypatch.setattr(lookup, "get_media_pool", lambda: pool)
    with pytest.raises(ValueError, match="found 2"):
        find_media("Same")
    assert find_media(media_id="b") is b


@pytest.mark.parametrize("fps,tc", [(24, "01:00:13:22"), (29.97, "01:00:00;00"),
                                   (29.97, "00:01:00;02"), (59.94, "00:01:00;04"),
                                   (29.97, "00:10:00;00")])
def test_timecode_roundtrip(fps, tc):
    assert from_frame(to_frame(tc, fps), fps, ";" in tc) == tc


def test_skipped_drop_frame_label_rejected():
    with pytest.raises(ValueError):
        to_frame("00:01:00;00", 29.97)


def test_delete_refusal_relinks_peers(scene):
    audio = Mock()
    audio.GetName.return_value = "Interview"
    scene.old.GetLinkedItems.return_value = [audio]
    scene.timeline.DeleteClips.return_value = False
    result = rep.replace_clip(2, 1, "New")
    assert result["success"] is False
    assert result["recovery"]["original_repair"]["links_restored"] is True
    scene.timeline.SetClipsLinked.assert_any_call([scene.old, audio], True)


def test_wrong_insert_extent_removes_bad_insert(scene):
    scene.new.GetEnd.return_value = 86521
    result = rep.replace_clip(2, 1, "New")
    assert result["success"] is False
    assert result["recovery"]["original_repair"]["bad_insert_removed"] is True
    scene.timeline.DeleteClips.assert_any_call([scene.new], False)


def test_insert_vanished_with_links_reports_unrestorable(scene):
    audio = Mock()
    scene.old.GetLinkedItems.return_value = [audio]
    scene.pool.AppendToTimeline.return_value = []
    result = rep.replace_clip(2, 1, "New")
    assert result["success"] is False
    assert result["recovery"]["original_repair"]["links_restored"] is False


def test_link_restore_failure_keeps_verified_insert(scene):
    audio = Mock()
    scene.old.GetLinkedItems.return_value = [audio]
    scene.timeline.SetClipsLinked.side_effect = [True, False]
    result = rep.replace_clip(2, 1, "New")
    assert result["success"] is False
    assert [scene.new] not in [c.args[0] for c in scene.timeline.DeleteClips.call_args_list]


def test_delete_clip_failure_relinks_peers(scene, registry, monkeypatch):
    from resolve_mcp.tools import editing
    audio = Mock()
    scene.old.GetLinkedItems.return_value = [audio]
    scene.timeline.DeleteClips.return_value = False
    monkeypatch.setattr(editing, "get_timeline", lambda: scene.timeline)
    monkeypatch.setattr(editing, "get_project", lambda: scene.project)
    monkeypatch.setattr(editing, "timeline_clip", lambda *a, **k: scene.old)
    editing.register(registry)
    result = json.loads(registry.tools["resolve_delete_clip"]("video", 2, 1))
    assert result["success"] is False
    assert result["original_repair"]["links_restored"] is True
    scene.timeline.SetClipsLinked.assert_any_call([scene.old, audio], True)
