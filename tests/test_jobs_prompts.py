import asyncio
from unittest.mock import Mock
import pytest
from resolve_mcp.server import create_server
from resolve_mcp.tools import jobs


@pytest.fixture
def render(monkeypatch, registry, tmp_path):
    project = Mock()
    out = tmp_path / "ep.mp4"
    out.write_bytes(b"x" * 10)
    project.GetRenderJobList.return_value = [{"JobId": "j1", "TargetDir": str(tmp_path), "OutputFilename": "ep.mp4"}]
    monkeypatch.setattr(jobs, "get_project", lambda: project)

    async def no_sleep(seconds):
        return None
    monkeypatch.setattr(jobs.asyncio, "sleep", no_sleep)
    jobs.register(registry)
    return project, registry.tools["resolve_wait_for_render"]


def test_waits_until_complete(render):
    project, wait = render
    project.GetRenderJobStatus.side_effect = [{"JobStatus": "Rendering", "CompletionPercentage": 40},
                                              {"JobStatus": "Complete", "CompletionPercentage": 100}]
    project.IsRenderingInProgress.side_effect = [True, False]
    result = asyncio.run(wait("j1"))
    assert result["success"] and result["status"]["CompletionPercentage"] == 100
    assert result["output"]["exists_on_server"] and result["output"]["bytes"] == 10


def test_failed_job_is_not_success(render):
    project, wait = render
    project.GetRenderJobStatus.return_value = {"JobStatus": "Failed", "Error": "disk full"}
    project.IsRenderingInProgress.return_value = False
    result = asyncio.run(wait("j1"))
    assert not result["success"] and result["status"]["Error"] == "disk full"


def test_timeout_can_stop_render(render, monkeypatch):
    project, wait = render
    project.GetRenderJobStatus.return_value = {"JobStatus": "Rendering"}
    project.IsRenderingInProgress.return_value = True
    clock = iter(range(0, 10000, 5))
    monkeypatch.setattr(jobs.time, "monotonic", lambda: next(clock))
    result = asyncio.run(wait("j1", timeout_seconds=10, stop_on_timeout=True))
    assert result["timed_out"] and result["rendering_stopped"] and result["error"]["retryable"]
    project.StopRendering.assert_called_once()


def test_unknown_job_and_bad_limits(render):
    _, wait = render
    assert not asyncio.run(wait("nope"))["success"]
    assert not asyncio.run(wait("j1", timeout_seconds=0))["success"]


def test_queued_job_never_started_returns(render):
    project, wait = render
    project.GetRenderJobStatus.return_value = {"JobStatus": "Ready"}
    project.IsRenderingInProgress.return_value = False
    result = asyncio.run(wait("j1"))
    assert not result["success"] and result["status"]["JobStatus"] == "Ready"


def test_server_exposes_new_tools_and_prompts():
    server = create_server()
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert {"resolve_create_captions", "resolve_get_transcript", "resolve_detect_silence",
            "resolve_tighten_silence", "resolve_build_cut_variant", "resolve_wait_for_render"} <= tools
    prompts = {p.name for p in asyncio.run(server.list_prompts())}
    assert prompts == {"podcast_episode_edit", "tighten_recording", "captions_and_transcript",
                       "safe_shot_replacement", "youtube_delivery"}
    text = asyncio.run(server.get_prompt("tighten_recording", {"max_pause_seconds": "1.2"}))
    assert "min_silence_seconds=1.2" in text.messages[0].content.text
