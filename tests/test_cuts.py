import copy
import itertools
import shutil
import subprocess
import pytest
from resolve_mcp.services import audio, variant
from resolve_mcp.tools import cuts

_ids = itertools.count(1)


class Media:
    def __init__(self, ident, frames=2400, fps="24", path="/media/x.mov", start_tc="00:00:00:00"):
        self.ident = ident
        self.props = {"Frames": str(frames), "FPS": fps, "File Path": path, "Start TC": start_tc}

    def GetMediaId(self):
        return self.ident

    def GetClipProperty(self):
        return dict(self.props)


class Item:
    def __init__(self, media, start, end, src_in=0, name="Take", span=None):
        self.media, self.start, self.end, self.src_in, self.name = media, start, end, src_in, name
        self.span = (end - start - 1) if span is None else span
        self.uid = f"item-{next(_ids)}"
        self.linked = []

    def GetUniqueId(self):
        return self.uid

    def GetName(self):
        return self.name

    def GetMediaPoolItem(self):
        return self.media

    def GetStart(self):
        return self.start

    def GetEnd(self):
        return self.end

    def GetSourceStartFrame(self):
        return self.src_in

    def GetSourceEndFrame(self):
        return self.src_in + self.span

    def GetLinkedItems(self):
        return list(self.linked)


def link(*items):
    for item in items:
        item.linked = [other for other in items if other is not item]


class Timeline:
    def __init__(self, name, start=86400, fps="24"):
        self.name, self.start, self.fps = name, start, fps
        self.tracks = {"video": [[]], "audio": [[]], "subtitle": []}
        self.locked, self.disabled = set(), set()
        self.markers = {}
        self.edited = False
        self.fail_link = False
        self.links_made = []

    def GetName(self):
        return self.name

    def GetSetting(self, key):
        return self.fps

    def GetStartFrame(self):
        return self.start

    def GetTrackCount(self, kind):
        return len(self.tracks[kind])

    def GetItemListInTrack(self, kind, index):
        return list(self.tracks[kind][index - 1])

    def GetIsTrackEnabled(self, kind, index):
        return (kind, index) not in self.disabled

    def GetIsTrackLocked(self, kind, index):
        return (kind, index) in self.locked

    def SetTrackLock(self, kind, index, value):
        (self.locked.add if value else self.locked.discard)((kind, index))
        return True

    def DeleteClips(self, items, ripple=False):
        self.edited = True
        for kind, tracks in self.tracks.items():
            for index, track in enumerate(tracks, 1):
                if any(i in track for i in items) and (kind, index) in self.locked:
                    return False
        for tracks in self.tracks.values():
            for track in tracks:
                track[:] = [i for i in track if i not in items]
        return True

    def SetClipsLinked(self, items, value):
        if self.fail_link:
            return False
        self.links_made.append(sorted(i.uid for i in items))
        link(*items)
        return True

    def GetMarkers(self):
        return dict(self.markers)

    def AddMarker(self, frame, color, name, note, duration, custom=""):
        self.edited = True
        self.markers[float(frame)] = {"color": color, "name": name, "note": note, "duration": duration,
                                      "customData": custom}
        return True

    def DeleteMarkersByColor(self, color):
        self.edited = True
        self.markers.clear()
        return True

    def DuplicateTimeline(self, name):
        dup = Timeline(name, self.start, self.fps)
        dup.tracks = {k: [list(t) for t in v] for k, v in self.tracks.items()}
        dup.locked, dup.disabled = set(self.locked), set(self.disabled)
        dup.markers = copy.deepcopy(self.markers)
        dup.fail_link = self.fail_link
        self.project.timelines.append(dup)
        dup.project = self.project
        return dup


class Project:
    def __init__(self, *timelines):
        self.timelines, self.current = list(timelines), timelines[0]
        for tl in timelines:
            tl.project = self

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, i):
        return self.timelines[i - 1]

    def SetCurrentTimeline(self, tl):
        self.current = tl
        return True


class Pool:
    def __init__(self, project, short_by=0):
        self.project, self.short_by, self.calls = project, short_by, []

    def AppendToTimeline(self, infos):
        self.calls.append(infos)
        tl, out = self.project.current, []
        for info in infos:
            kind = {1: "video", 2: "audio"}[info["mediaType"]]
            length = info["endFrame"] - info["startFrame"] - self.short_by
            item = Item(info["mediaPoolItem"], info["recordFrame"], info["recordFrame"] + length, src_in=info["startFrame"])
            tl.tracks[kind][info["trackIndex"] - 1].append(item)
            out.append(item)
        return out


@pytest.fixture
def show(monkeypatch, registry):
    cam = Media("cam")
    source = Timeline("Episode 12")
    video = Item(cam, 86400, 87600, name="Cam A")
    scratch = Item(cam, 86400, 87600, name="Cam A")
    link(video, scratch)
    source.tracks["video"][0].append(video)
    source.tracks["audio"][0].append(scratch)
    project = Project(source)
    pool = Pool(project)
    monkeypatch.setattr(cuts, "get_timeline", lambda: source)
    monkeypatch.setattr(cuts, "get_project", lambda: project)
    monkeypatch.setattr(cuts, "get_media_pool", lambda: pool)
    cuts.register(registry)

    def snapshot(tl):
        return {k: [[(i.uid, i.start, i.end) for i in t] for t in v] for k, v in tl.tracks.items()}

    return type("Show", (), dict(cam=cam, source=source, project=project, pool=pool, tools=registry.tools,
                                 video=video, scratch=scratch, snapshot=snapshot,
                                 base=snapshot(source)))


def add_mics(show):
    host, guest = Media("host", path="/media/host.wav"), Media("guest", path="/media/guest.wav")
    show.source.tracks["audio"] += [[Item(host, 86400, 87600, name="Host")],
                                    [Item(guest, 86400, 87000, name="Guest"), Item(guest, 87000, 87600, src_in=600, name="Guest")]]
    show.base = show.snapshot(show.source)


def test_interval_helpers():
    assert variant.merge([(5, 8), (1, 3), (2, 4), (8, 9)]) == [(1, 4), (5, 9)]
    assert variant.intersect([(0, 10), (20, 30)], [(5, 25)]) == [(5, 10), (20, 25)]
    keeps, dropped = variant.keep_intervals((0, 100), [(10, 20), (22, 50)], 5)
    assert keeps == [(0, 10), (50, 100)] and dropped == 2


def test_plan_keeps_all_tracks_in_sync(show):
    add_mics(show)
    fps, tracks, skipped = variant.collect(show.source)
    planned = variant.plan(show.source, tracks, fps, [(86448, 86496), (86990, 87010)], 0)
    by_track = {}
    for step in planned["appends"]:
        by_track.setdefault((step["kind"], step["track"]), []).append((step["offset"], step["frames"], step["source_in"]))
    assert by_track[("video", 1)] == [(0, 48, 0), (48, 494, 96), (542, 590, 610)]
    assert by_track[("audio", 2)] == by_track[("video", 1)]
    assert by_track[("audio", 3)] == [(0, 48, 0), (48, 494, 96), (542, 590, 610)]
    assert planned["summary"]["kept_frames"] == 1132 and planned["summary"]["tracks_carried"] == 4
    assert skipped == []


def test_dry_run_builds_nothing(show):
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 2, "end_seconds": 4}])
    assert result["success"] and result["dry_run"] and result["summary"]["removed_seconds"] == 2.0
    assert len(show.project.timelines) == 1 and not show.pool.calls and not show.source.edited


def test_multitrack_variant(show):
    add_mics(show)
    show.source.locked.add(("audio", 3))
    show.source.markers = {24.0: {"color": "Blue", "name": "Intro", "note": "", "duration": 1, "customData": "c1"},
                           60.0: {"color": "Red", "name": "Cut me", "note": "", "duration": 1, "customData": ""},
                           300.0: {"color": "Green", "name": "Topic", "note": "n", "duration": 500, "customData": ""}}
    result = show.tools["resolve_build_cut_variant"](
        [{"start_seconds": 2, "end_seconds": 4}, {"start_seconds": 10, "end_seconds": 11.5}],
        new_timeline_name="Ep12 cut", dry_run=False)
    assert result["success"], result
    tl = show.project.timelines[1]
    spans = [(0, 48), (48, 192), (192, 1116)]
    for kind, index in (("video", 1), ("audio", 1), ("audio", 2)):
        assert [(i.start - 86400, i.end - 86400) for i in tl.GetItemListInTrack(kind, index)] == spans, (kind, index)
    guest = [(i.start - 86400, i.end - 86400, i.src_in) for i in tl.GetItemListInTrack("audio", 3)]
    assert guest == [(0, 48, 0), (48, 192, 96), (192, 516, 276), (516, 1116, 600)]
    assert ("audio", 3) in tl.locked, "lock restored on the variant"
    assert result["link_groups_restored"] == 3 and len(show.pool.calls) == 4
    assert all(info["mediaType"] in (1, 2) for call in show.pool.calls for info in call)
    assert tl.markers == {24.0: {"color": "Blue", "name": "Intro", "note": "", "duration": 1, "customData": "c1"},
                          216.0: {"color": "Green", "name": "Topic", "note": "n", "duration": 500, "customData": ""}}
    assert any("inside removed time" in n for n in result["notes"])
    assert show.snapshot(show.source) == show.base and not show.source.edited
    assert show.project.current is tl


def test_marker_duration_clipped_to_kept_span():
    moved = variant.remap_markers({90.0: {"duration": 100}}, [(86400, 86500), (86600, 86700)], 86400)
    assert moved == [{"frame": 90, "info": {"duration": 10}}]


def test_spine_scope_carries_only_spine(show):
    add_mics(show)
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], tracks="spine",
                                                     dry_run=False)
    assert result["success"], result
    tl = show.project.timelines[1]
    assert tl.GetItemListInTrack("video", 1) == [] and len(tl.GetItemListInTrack("audio", 1)) == 2
    assert tl.GetItemListInTrack("audio", 2) == [] and result["not_carried_over_count"] == 4


def test_problem_clips_off_spine_are_skipped_and_listed(show):
    title = Item(None, 86500, 86600, name="Lower third")
    retimed = Item(Media("broll"), 86600, 86700, name="Slomo", span=40)
    other_fps = Item(Media("drone", fps="30"), 86700, 86800, name="Drone")
    show.source.tracks["video"].append([title, retimed, other_fps])
    show.source.tracks["subtitle"].append([Item(None, 86400, 86448, name="Hi")])
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    assert result["success"], result
    notes = result["not_carried_over"]
    assert any("Lower third" in n and "not a media clip" in n for n in notes)
    assert any("Slomo" in n and "retimed" in n for n in notes)
    assert any("Drone" in n and "frame rate" in n for n in notes)
    assert any(n.startswith("subtitle 1: 1 caption cues") for n in notes)
    tl = show.project.timelines[1]
    assert tl.GetItemListInTrack("video", 2) == [] and tl.GetItemListInTrack("subtitle", 1) == []


def test_bad_spine_is_an_error(show):
    show.scratch.span = 600
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])
    assert not result["success"] and "retimed" in result["error"]["message"]
    show.scratch.span = 1199
    show.cam.props["File Path"] = ""
    assert "no source file" in show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])["error"]["message"]


def test_short_insert_fails_and_reselects_source(show):
    show.pool.short_by = 1
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    assert not result["success"] and result["error"]["code"] == "variant_failed"
    assert show.project.current is show.source and result["source_reselected"]
    assert show.snapshot(show.source) == show.base


def test_link_failure_is_a_note_not_a_failure(show):
    show.source.fail_link = True
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    assert result["success"] and any("relinked" in n for n in result["notes"])


def test_existing_name_rejected(show):
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}],
                                                     new_timeline_name="Episode 12", dry_run=False)
    assert not result["success"] and "already exists" in result["error"]["message"]
    assert len(show.project.timelines) == 1


@pytest.mark.parametrize("bad", [[], [{"start_seconds": 3, "end_seconds": 2}], [{"start": 1}],
                                 [{"start_seconds": float("nan"), "end_seconds": 2}]])
def test_bad_ranges_rejected(show, bad):
    assert not show.tools["resolve_build_cut_variant"](bad)["success"]


def test_timecode_based_source_frames(show):
    show.cam.props["Start TC"] = "01:00:00:00"
    show.scratch.src_in = 86400 + 100
    _, tracks, _ = variant.collect(show.source)
    audio_track = [t for t in tracks if t["kind"] == "audio"][0]
    assert audio_track["pieces"][0]["source_in"] == 100


def test_silence_must_be_shared_by_every_mic(show, monkeypatch):
    add_mics(show)
    quiet = {"/media/x.mov": [(0, 50)], "/media/host.wav": [(2, 5), (10, 14), (30, 50)],
             "/media/guest.wav": [(0, 3), (9, 13), (4, 10)]}

    def fake_detect(path, start, duration, threshold, minimum, stream=0):
        return [(max(0, a - start), min(duration, b - start)) for a, b in quiet[path] if b > start and a < start + duration]
    monkeypatch.setattr(audio, "detect_silence", fake_detect)
    monkeypatch.setattr(audio, "calibrate_threshold", lambda *a, **k: {"threshold_db": -40, "method": "calibrated"})
    both = show.tools["resolve_detect_silence"](min_silence_seconds=0.7)
    assert [(s["start_seconds"], s["end_seconds"]) for s in both["silences"]] == [(2.0, 3.0), (4.0, 5.0), (10.0, 13.0)]
    assert both["analyzed_tracks"] == ["audio 1", "audio 2", "audio 3"]
    host_only = show.tools["resolve_detect_silence"](detect_on="spine")
    assert host_only["analyzed_tracks"] == ["audio 1"]
    show.source.disabled.add(("audio", 1))
    assert show.tools["resolve_detect_silence"]()["analyzed_tracks"] == ["audio 2", "audio 3"]


def test_ffmpeg_missing_is_clear(show, monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    monkeypatch.delenv("RESOLVE_MCP_FFMPEG", raising=False)
    show.cam.props["File Path"] = __file__
    result = show.tools["resolve_tighten_silence"]()
    assert not result["success"] and "ffmpeg" in result["error"]["message"]


def _tone(path, seconds, mute_expr):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=220:d={seconds},volume=0.3",
                    "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:a=0.002", "-filter_complex",
                    f"[0]volume='if({mute_expr},0,1)':eval=frame[s];[s][1]amix=inputs=2:normalize=0",
                    "-ar", "48000", str(path)], check=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_tighten_real_audio_two_mics(show, tmp_path):
    host, guest = tmp_path / "host.wav", tmp_path / "guest.wav"
    # host talks 0-10 and 30-50; guest talks 14-30. Shared silence: 10-14 only.
    _tone(host, 50, "between(t,10,30)")
    _tone(guest, 50, "lt(t,14)+gt(t,30)")
    show.cam.props["File Path"] = str(host)
    show.source.tracks["audio"].append([Item(Media("g", path=str(guest)), 86400, 87600, name="Guest")])
    host_only = show.tools["resolve_detect_silence"](detect_on="spine")
    assert [(round(s["start_seconds"]), round(s["end_seconds"])) for s in host_only["silences"]] == [(10, 30)]
    both = show.tools["resolve_detect_silence"]()
    assert [(round(s["start_seconds"]), round(s["end_seconds"])) for s in both["silences"]] == [(10, 14)]
    built = show.tools["resolve_tighten_silence"](dry_run=False, new_timeline_name="tight")
    assert built["success"], built
    assert abs(built["summary"]["removed_seconds"] - 3.5) < 0.15
    tl = show.project.timelines[1]
    assert len(tl.GetItemListInTrack("audio", 2)) == 2 and len(tl.GetItemListInTrack("video", 1)) == 2


def test_wav_without_frames_uses_duration(show):
    # Exact shape Resolve Studio 21.0.4.5 returned for an imported WAV.
    wav = Media("mic", path="/media/mic.wav")
    wav.props.update({"Frames": "", "FPS": 24.0, "Duration": "00:00:50:00", "Start TC": "00:00:00:00",
                      "End TC": "00:00:50:00", "Type": "Audio"})
    assert variant.frame_count(wav.props) == 1200
    show.source.tracks["audio"].append([Item(wav, 86400, 87600, name="Mic")])
    _, tracks, skipped = variant.collect(show.source)
    assert skipped == [] and len(tracks[-1]["pieces"]) == 1
    wav.props.pop("Duration")
    assert variant.frame_count(wav.props) == 1200
    wav.props["End TC"] = ""
    with pytest.raises(ValueError):
        variant.frame_count(wav.props)


def test_unreadable_mic_blocks_shared_silence(show, monkeypatch):
    broken = Media("mic", path="/media/mic.wav")
    broken.props.update({"Frames": "", "Duration": "", "End TC": ""})
    show.source.tracks["audio"].append([Item(broken, 86400, 87600, name="Guest mic")])
    monkeypatch.setattr(audio, "detect_silence", lambda *a, **k: [])
    monkeypatch.setattr(audio, "calibrate_threshold", lambda *a, **k: {"threshold_db": -40, "method": "x"})
    result = show.tools["resolve_detect_silence"]()
    assert not result["success"] and "Guest mic" in result["error"]["message"]
    assert not show.tools["resolve_tighten_silence"]()["success"]
    assert show.tools["resolve_detect_silence"](detect_on="spine")["success"]
    show.source.disabled.add(("audio", 2))
    assert show.tools["resolve_detect_silence"]()["success"]


def test_source_lock_restored_when_resolve_shares_it(show):
    """Resolve 21.0.4.5 cleared the SOURCE lock when the duplicate's track was unlocked."""
    add_mics(show)
    show.source.locked.add(("audio", 3))
    original_dup = Timeline.DuplicateTimeline

    def shared_lock_dup(self, name):
        dup = original_dup(self, name)
        source = self

        def set_lock(kind, index, value):
            Timeline.SetTrackLock(dup, kind, index, value)
            if not value:  # observed: the unlock leaked to the source; the relock did not
                source.locked.discard((kind, index))
            return True
        dup.SetTrackLock = set_lock
        return dup

    def source_set_lock(kind, index, value):
        # observed: SetTrackLock only works on the current timeline
        if show.project.current is show.source:
            Timeline.SetTrackLock(show.source, kind, index, value)
        return True
    show.source.SetTrackLock = source_set_lock
    Timeline.DuplicateTimeline = shared_lock_dup
    try:
        result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    finally:
        Timeline.DuplicateTimeline = original_dup
    assert result["success"], result
    assert ("audio", 3) in show.source.locked
    assert any("lock on audio 3" in n and "restored" in n for n in result["notes"])
    assert show.project.current.GetName() != "Episode 12", "variant reselected after the restore"
