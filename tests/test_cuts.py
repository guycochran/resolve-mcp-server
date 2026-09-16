import shutil
import subprocess
import pytest
from resolve_mcp.services import audio, variant
from resolve_mcp.tools import cuts


class Media:
    def __init__(self, ident, frames=2400, fps="24", path="", start_tc="00:00:00:00"):
        self.ident, self.props = ident, {"Frames": str(frames), "FPS": fps, "File Path": path, "Start TC": start_tc}

    def GetMediaId(self):
        return self.ident

    def GetClipProperty(self):
        return dict(self.props)


class Item:
    def __init__(self, media, start, end, src_in=0, kind="audio", name="Take 1", span=None):
        self.media, self.start, self.end, self.src_in, self.kind, self.name = media, start, end, src_in, kind, name
        self.span = (end - start - 1) if span is None else span
        self.linked = []

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
        return self.linked

    def GetTrackTypeAndIndex(self):
        return [self.kind, 1]


class Timeline:
    def __init__(self, name, start=86400, fps="24"):
        self.name, self.start, self.fps = name, start, fps
        self.tracks = {"video": [[]], "audio": [[]], "subtitle": []}
        self.start_tc = "01:00:00:00"
        self.edited = False

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

    def GetStartTimecode(self):
        return self.start_tc

    def SetStartTimecode(self, tc):
        self.start_tc = tc
        return True

    def DeleteClips(self, *a):
        self.edited = True


class Project:
    def __init__(self, *timelines):
        self.timelines, self.current = list(timelines), timelines[0]

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

    def CreateEmptyTimeline(self, name):
        tl = Timeline(name)
        self.project.timelines.append(tl)
        return tl

    def AppendToTimeline(self, infos):
        self.calls.append(infos)
        tl, out = self.project.current, []
        for info in infos:
            length = info["endFrame"] - info["startFrame"] - self.short_by
            kinds = {1: ["video"], 2: ["audio"]}.get(info.get("mediaType"), ["video", "audio"])
            for kind in kinds:
                item = Item(info["mediaPoolItem"], info["recordFrame"], info["recordFrame"] + length, kind=kind)
                tl.tracks[kind][0].append(item)
                out.append(item)
        return out


@pytest.fixture
def show(monkeypatch, registry):
    media = Media("m1")
    source = Timeline("Episode 12")
    video = Item(media, 86400, 87600, kind="video")
    dialog = Item(media, 86400, 87600, kind="audio")
    video.linked, dialog.linked = [dialog], [video]
    source.tracks["video"][0].append(video)
    source.tracks["audio"][0].append(dialog)
    project = Project(source)
    pool = Pool(project)
    monkeypatch.setattr(cuts, "get_timeline", lambda: source)
    monkeypatch.setattr(cuts, "get_project", lambda: project)
    monkeypatch.setattr(cuts, "get_media_pool", lambda: pool)
    cuts.register(registry)
    return type("Show", (), dict(media=media, source=source, project=project, pool=pool,
                                 tools=registry.tools, dialog=dialog, video=video))


def test_merge_and_plan_math(show):
    fps, pieces = variant.spine(show.source)
    keeps, summary, preview = variant.plan(show.source, pieces, fps,
                                           [(86448, 86472), (86460, 86496), (87000, 87010)], 0)
    assert [(k["source_in"], k["source_out_exclusive"]) for k in keeps] == [(0, 48), (96, 600), (610, 1200)]
    assert summary["removed_frames"] == 58 and summary["kept_frames"] == 1142
    assert preview[1] == {"from_seconds": 4.0, "to_seconds": 25.0, "clip": "Take 1"}


def test_min_keep_drops_slivers(show):
    fps, pieces = variant.spine(show.source)
    keeps, summary, _ = variant.plan(show.source, pieces, fps, [(86400, 86500), (86505, 87600)], 24)
    assert keeps == [] and summary["short_pieces_dropped_frames"] == 5


def test_dry_run_builds_nothing(show):
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 2, "end_seconds": 4}])
    assert result["success"] and result["dry_run"] and result["summary"]["removed_seconds"] == 2.0
    assert len(show.project.timelines) == 1 and not show.pool.calls


def test_variant_is_gapless_and_source_untouched(show):
    result = show.tools["resolve_build_cut_variant"](
        [{"start_seconds": 2, "end_seconds": 4}, {"start_seconds": 10, "end_seconds": 11.5}],
        new_timeline_name="Ep12 cut", dry_run=False)
    assert result["success"], result
    variant_tl = show.project.timelines[1]
    spans = [(i.GetStart(), i.GetEnd()) for i in variant_tl.GetItemListInTrack("video", 1)]
    assert spans == [(86400, 86448), (86448, 86592), (86592, 87516)]
    assert [(i.GetStart(), i.GetEnd()) for i in variant_tl.GetItemListInTrack("audio", 1)] == spans
    info = show.pool.calls[0][1]
    assert (info["startFrame"], info["endFrame"], "mediaType" not in info) == (96, 240, True)
    assert not show.source.edited and show.source.GetItemListInTrack("audio", 1) == [show.dialog]
    assert variant_tl.start_tc == "01:00:00:00" and show.project.current is variant_tl


def test_audio_only_spine_appends_audio_only(show):
    show.source.tracks["video"][0].clear()
    show.dialog.linked = []
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    assert result["success"] and all(info["mediaType"] == 2 for info in show.pool.calls[0])
    assert show.project.timelines[1].GetItemListInTrack("video", 1) == []


def test_short_insert_fails_and_reselects_source(show):
    show.pool.short_by = 1
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}], dry_run=False)
    assert not result["success"] and result["error"]["code"] == "variant_failed"
    assert show.project.current is show.source and result["source_reselected"]
    assert not show.source.edited


def test_existing_name_rejected(show):
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}],
                                                     new_timeline_name="Episode 12", dry_run=False)
    assert not result["success"] and "already exists" in result["error"]["message"]
    assert len(show.project.timelines) == 1


@pytest.mark.parametrize("bad", [[], [{"start_seconds": 3, "end_seconds": 2}], [{"start": 1}],
                                 [{"start_seconds": float("nan"), "end_seconds": 2}]])
def test_bad_ranges_rejected(show, bad):
    assert not show.tools["resolve_build_cut_variant"](bad)["success"]


def test_retimed_and_foreign_rejected(show):
    show.dialog.span = 600
    assert "retimed" in show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])["error"]["message"]
    show.dialog.span = 1199
    show.media.props["FPS"] = "30"
    assert "frame rate" in show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])["error"]["message"]


def test_timecode_based_source_frames(show):
    show.media.props["Start TC"] = "01:00:00:00"
    show.dialog.src_in = 86400 + 100
    fps, pieces = variant.spine(show.source)
    assert pieces[0]["source_in"] == 100


def test_other_media_reported(show):
    broll = Item(Media("m2"), 86500, 86600, kind="video", name="Drone")
    show.source.tracks["video"].append([broll])
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])
    assert result["not_carried_over"] == ["video 2: 'Drone'"]
    show.source.tracks["subtitle"].append([Item(None, 86400, 86448, name="Hi"), Item(None, 86448, 86496, name="there")])
    result = show.tools["resolve_build_cut_variant"]([{"start_seconds": 1, "end_seconds": 2}])
    assert result["not_carried_over"][-1].startswith("subtitle 1: 2 caption cues")


def test_ffmpeg_missing_is_clear(show, monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    monkeypatch.delenv("RESOLVE_MCP_FFMPEG", raising=False)
    show.media.props["File Path"] = __file__
    result = show.tools["resolve_tighten_silence"]()
    assert not result["success"] and "ffmpeg" in result["error"]["message"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_tighten_real_audio(show, tmp_path):
    wav = tmp_path / "talk.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=50,volume=0.3",
                    "-f", "lavfi", "-i", "anoisesrc=d=50:a=0.002", "-filter_complex",
                    "[0]volume='if(between(t,10,14)+between(t,30,31),0,1)':eval=frame[s];"
                    "[s][1]amix=inputs=2:normalize=0", "-ar", "48000", str(wav)], check=True)
    show.media.props["File Path"] = str(wav)
    detected = show.tools["resolve_detect_silence"]()
    assert [(round(s["start_seconds"]), round(s["end_seconds"])) for s in detected["silences"]] == [(10, 14), (30, 31)]
    planned = show.tools["resolve_tighten_silence"](min_silence_seconds=0.7, keep_pause_seconds=0.25)
    assert planned["silences_cut"] == 2
    assert abs(planned["summary"]["removed_seconds"] - (4 - 0.5 + 1 - 0.5)) < 0.15
    built = show.tools["resolve_tighten_silence"](dry_run=False, new_timeline_name="tight")
    assert built["success"] and len(show.project.timelines[1].GetItemListInTrack("audio", 1)) == 3


def test_audio_only_media_without_frame_count(show):
    # Resolve 21.1 reports Frames="" for WAV clips; Duration still gives the length.
    show.media.props.update({"Frames": "", "Duration": "00:00:50:00"})
    fps, pieces = variant.spine(show.source)
    assert pieces[0]["source_in"] == 0
    show.media.props["Duration"] = ""
    with pytest.raises(ValueError, match="frame count"):
        variant.spine(show.source)
