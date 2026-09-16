from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from resolve_mcp.services import transcript as tx
from resolve_mcp.tools import analysis, transcript


def cue(text, start, end):
    item = Mock()
    item.GetName.return_value = text
    item.GetStart.return_value = start
    item.GetEnd.return_value = end
    return item


class FakeTimeline:
    def __init__(self, tracks=None):
        self.tracks = tracks or []
        self.created = None

    def GetName(self):
        return "Episode"

    def GetTrackCount(self, kind):
        return len(self.tracks) if kind == "subtitle" else 1

    def GetItemListInTrack(self, kind, index):
        return self.tracks[index - 1]

    def GetSetting(self, key):
        return "24"

    def GetStartFrame(self):
        return 86400

    def CreateSubtitlesFromAudio(self, settings):
        self.created = settings
        return self.on_create(self)


RESOLVE_CONSTANTS = dict(
    SUBTITLE_LANGUAGE="K_LANG", SUBTITLE_CAPTION_PRESET="K_PRESET", SUBTITLE_LINE_BREAK="K_BREAK",
    SUBTITLE_GAP="K_GAP", SUBTITLE_CHARS_PER_LINE="K_CHARS", AUTO_CAPTION_AUTO=100, AUTO_CAPTION_ENGLISH=101,
    AUTO_CAPTION_SUBTITLE_DEFAULT=200, AUTO_CAPTION_NETFLIX=201, AUTO_CAPTION_TELETEXT=202,
    AUTO_CAPTION_LINE_SINGLE=300, AUTO_CAPTION_LINE_DOUBLE=301)


@pytest.fixture
def env(monkeypatch, registry):
    resolve = Mock(**RESOLVE_CONSTANTS)
    resolve.GetVersion.return_value = [21, 0, 4]
    resolve.GetProductName.return_value = "DaVinci Resolve Studio"
    timeline = FakeTimeline()
    monkeypatch.setattr(analysis, "get_resolve", lambda: resolve)
    monkeypatch.setattr(transcript, "get_timeline", lambda: timeline)
    transcript.register(registry)
    return SimpleNamespace(resolve=resolve, timeline=timeline, tools=registry.tools)


def test_settings_use_resolve_enums():
    resolve = SimpleNamespace(**RESOLVE_CONSTANTS)
    settings = tx.caption_settings(resolve, "english", "netflix", 32, "double", 2)
    assert settings == {"K_LANG": 101, "K_PRESET": 201, "K_BREAK": 301, "K_GAP": 2, "K_CHARS": 32}
    assert "K_CHARS" not in tx.caption_settings(resolve)


def test_settings_reject_missing_constant_and_bad_values():
    with pytest.raises(RuntimeError):
        tx.caption_settings(SimpleNamespace())
    resolve = SimpleNamespace(**RESOLVE_CONSTANTS)
    for kwargs in ({"language": "klingon"}, {"preset": "x"}, {"chars_per_line": 61}, {"gap": 11}):
        with pytest.raises(ValueError):
            tx.caption_settings(resolve, **kwargs)


def test_free_edition_never_calls_captioning(env):
    env.resolve.GetProductName.return_value = "DaVinci Resolve"
    env.timeline.on_create = Mock()
    result = env.tools["resolve_create_captions"]()
    assert not result["success"] and "Studio" in result["error"]["message"]
    env.timeline.on_create.assert_not_called()


def test_captions_verified_by_readback(env):
    def create(timeline):
        timeline.tracks.append([cue("Hello there.", 86400, 86448), cue("General Kenobi.", 86448, 86496)])
        return True
    env.timeline.on_create = create
    result = env.tools["resolve_create_captions"](language="english")
    assert result["success"] and result["new_track"] == 1 and result["cues_after"] == 2
    assert result["preview"] == ["Hello there.", "General Kenobi."]
    assert env.timeline.created["K_LANG"] == 101


def test_native_true_without_cues_is_failure(env):
    env.timeline.on_create = lambda timeline: True
    result = env.tools["resolve_create_captions"]()
    assert not result["success"] and result["native_result"] and result["error"]["retryable"]


def test_dry_run_does_not_caption(env):
    env.timeline.on_create = Mock()
    assert env.tools["resolve_create_captions"](dry_run=True)["dry_run"]
    env.timeline.on_create.assert_not_called()


def test_transcript_from_captions_json_and_srt(env, tmp_path):
    env.timeline.tracks.append([cue("Second", 86448, 86472), cue("First", 86400, 86424)])
    result = env.tools["resolve_get_transcript"]()
    assert [e["text"] for e in result["entries"]] == ["First", "Second"]
    assert result["entries"][1]["start_seconds"] == 2.0 and result["entries"][1]["start_frame"] == 86448
    srt = env.tools["resolve_get_transcript"](format="srt")["text"]
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,000\nFirst\n")
    assert "2\n00:00:02,000 --> 00:00:03,000\nSecond" in srt
    out = tmp_path / "ep.vtt"
    written = env.tools["resolve_get_transcript"](format="vtt", output_path=str(out))
    assert written["success"] and out.read_text().startswith("WEBVTT\n")
    again = env.tools["resolve_get_transcript"](format="vtt", output_path=str(out))
    assert not again["success"] and "exists" in again["error"]["message"]


def test_transcript_requires_cues(env):
    result = env.tools["resolve_get_transcript"]()
    assert not result["success"] and "resolve_create_captions" in result["error"]["message"]


def test_clip_transcript_needs_21_1(env, monkeypatch):
    media = Mock(spec=["GetName", "GetClipProperty", "GetMediaId"])
    monkeypatch.setattr(transcript, "find_media", lambda *a: media)
    result = env.tools["resolve_get_transcript"](source="clip", clip_name="Interview")
    assert not result["success"] and "21.1" in result["error"]["message"]


def test_clip_transcript_maps_timecodes(env, monkeypatch):
    media = Mock()
    media.GetName.return_value = "Interview"
    media.GetClipProperty.return_value = {"FPS": "24", "Start TC": "01:00:00:00"}
    media.GetTranscription.return_value = {"language": "en", "segments": [
        {"start": "01:00:01:12", "end": "01:00:03:00", "text": " Hi ", "speaker": "Speaker 1",
         "words": [{"start": "01:00:01:12", "end": "01:00:02:00", "text": "Hi"}]}]}
    monkeypatch.setattr(transcript, "find_media", lambda *a: media)
    result = env.tools["resolve_get_transcript"](source="clip", clip_name="Interview")
    entry = result["entries"][0]
    assert entry == {"text": "Hi", "start_seconds": 1.5, "end_seconds": 3.0, "speaker": "Speaker 1",
                     "words": [{"text": "Hi", "start_seconds": 1.5, "end_seconds": 2.0}]}
    text = env.tools["resolve_get_transcript"](source="clip", clip_name="Interview", format="text")["text"]
    assert text == "Speaker 1: Hi\n"
    media.GetTranscription.assert_called_with(False)
