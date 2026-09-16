from unittest.mock import Mock
import pytest


class Registry:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self, *args, **kwargs):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register

    def resource(self, uri, **kwargs):
        def register(function):
            self.resources[uri] = function
            return function
        return register


@pytest.fixture
def registry():
    return Registry()


@pytest.fixture
def scene(monkeypatch):
    from resolve_mcp.services import replacement as rep
    old, new, media, timeline, project, pool, backup = [Mock() for _ in range(7)]
    for item, name, ident in ((old, "Old", "old-id"), (new, "New", "new-id")):
        item.GetName.return_value = name
        item.GetUniqueId.return_value = ident
        item.GetStart.return_value = 86400
        item.GetEnd.return_value = 86520
        item.GetDuration.return_value = 120
    old.GetLinkedItems.return_value = []
    old.GetSourceStartFrame.return_value = 10
    old.GetSourceEndFrame.return_value = 129
    old.GetProperty.return_value = {"ZoomX": 1.2}
    old.GetMarkers.return_value = {}
    media.GetName.return_value = "New"
    media.GetMediaId.return_value = "media-new"
    media.GetClipProperty.return_value = {"Frames": "500", "FPS": "24"}
    timeline.GetTrackCount.return_value = 2
    timeline.GetIsTrackLocked.return_value = False
    timeline.GetItemListInTrack.return_value = [old]
    timeline.GetStartFrame.return_value = 86400
    timeline.GetEndFrame.return_value = 86520
    timeline.GetSetting.return_value = "24"
    timeline.GetName.return_value = "Main"
    timeline.DuplicateTimeline.return_value = backup
    timeline.DeleteClips.return_value = True
    timeline.SetClipsLinked.return_value = True
    backup.GetName.return_value = "Recovery"
    project.SetCurrentTimeline.return_value = True
    pool.AppendToTimeline.return_value = [new]
    monkeypatch.setattr(rep, "get_project", lambda: project)
    monkeypatch.setattr(rep, "get_timeline", lambda: timeline)
    monkeypatch.setattr(rep, "get_media_pool", lambda: pool)
    monkeypatch.setattr(rep, "find_media", lambda *args: media)
    return Mock(old=old, new=new, media=media, timeline=timeline, project=project, pool=pool, backup=backup)