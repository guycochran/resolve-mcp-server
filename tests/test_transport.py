import asyncio
import os
import sys
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from resolve_mcp.config import Config
from resolve_mcp.server import create_server, http_app

TOKEN = "test-only-token-0123456789abcdef0123456789"


def test_safe_defaults():
    cfg = Config.from_env({})
    assert cfg.host == "127.0.0.1" and cfg.transport == "stdio"
    assert Config.from_env({"TRANSPORT": "http"}).transport == "streamable-http"


def test_all_53_original_tools_preserved():
    expected = set(json.loads((Path(__file__).parent / "legacy_tools.json").read_text()))
    current = {tool.name for tool in asyncio.run(create_server().list_tools())}
    assert len(expected) == 53
    assert expected <= current


@pytest.mark.parametrize("env", [
    {"TRANSPORT": "typo"}, {"PORT": "0"}, {"PORT": "65536"},
    {"TRANSPORT": "http", "HOST": "0.0.0.0"},
    {"TRANSPORT": "http", "HOST": "::"},
    {"TRANSPORT": "http", "HOST": "192.168.1.10"},
    {"MCP_AUTH_TOKEN": "short"},
    {"MCP_PUBLIC_URL": "http://example.com"},
    {"MCP_PUBLIC_URL": "https://example.com/path"},
    {"TRANSPORT": "http", "MCP_PUBLIC_URL": "https://example.com"},
])
def test_dangerous_or_invalid_configuration_rejected(env):
    with pytest.raises(ValueError):
        Config.from_env(env)


def test_external_binding_requires_auth_and_token_is_redacted():
    config = Config.from_env({"TRANSPORT": "http", "HOST": "0.0.0.0", "MCP_AUTH_TOKEN": TOKEN})
    assert TOKEN not in repr(config)


@pytest.fixture
def http_client():
    config = Config.from_env({"TRANSPORT": "http", "MCP_AUTH_TOKEN": TOKEN})
    server = create_server(config)
    with TestClient(http_app(server, config), base_url="http://localhost:3001") as client:
        yield client


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_http_requires_token_on_every_method(http_client, method):
    result = http_client.request(method, "/mcp")
    assert result.status_code == 401
    assert TOKEN not in result.text


def test_bad_token_rejected(http_client):
    assert http_client.post("/mcp", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_authenticated_http_initializes(http_client):
    response = http_client.post("/mcp", headers={"Authorization": f"Bearer {TOKEN}",
                                "Accept": "application/json, text/event-stream"},
                                json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                 "clientInfo": {"name": "test", "version": "1"}}})
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "resolve-mcp-server"


def test_host_rebinding_blocked(http_client):
    response = http_client.post("/mcp", headers={"Authorization": f"Bearer {TOKEN}", "Host": "evil.example",
                                "Accept": "application/json, text/event-stream"}, json={})
    assert response.status_code == 421


def test_untrusted_origin_blocked(http_client):
    response = http_client.post("/mcp", headers={"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example",
                                "Accept": "application/json, text/event-stream"}, json={})
    assert response.status_code == 403


def test_tools_serialized():
    async def run():
        server = create_server()
        sequence = []
        @server.tool()
        async def probe(number: int) -> dict:
            sequence.append(("start", number))
            await asyncio.sleep(0.01)
            sequence.append(("end", number))
            return {"number": number}
        await asyncio.gather(server.call_tool("probe", {"number": 1}), server.call_tool("probe", {"number": 2}))
        assert sequence == [("start", 1), ("end", 1), ("start", 2), ("end", 2)]
    asyncio.run(run())


def test_stdio_startup_and_resource_read():
    # Anonymous pipes also work in restricted Windows sessions where asyncio's
    # named-pipe subprocess transport is unavailable. Exercise real JSON-RPC.
    env = dict(os.environ, TRANSPORT="stdio", PYTHONPATH_RESOLVE=str(Path(__file__).parent / "nonexistent-api"))
    env.pop("MCP_AUTH_TOKEN", None)
    env.pop("MCP_PUBLIC_URL", None)
    with tempfile.TemporaryFile(mode="w+") as errors, ThreadPoolExecutor(max_workers=1) as reader:
        process = subprocess.Popen([sys.executable, "-m", "resolve_mcp"], env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding="utf-8")
        try:
            def request(number, method, params=None):
                process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": number, "method": method,
                                                "params": params or {}}) + "\n")
                process.stdin.flush()
                line = reader.submit(process.stdout.readline).result(timeout=15)
                return json.loads(line)["result"]
            initialized = request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                   "clientInfo": {"name": "test", "version": "1"}})
            assert initialized["serverInfo"]["name"] == "resolve-mcp-server"
            process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            process.stdin.flush()
            names = {t["name"] for t in request(2, "tools/list")["tools"]}
            assert {"resolve_replace_clip", "resolve_describe_frame", "resolve_transcribe_audio",
                    "resolve_build_rough_cut"}.issubset(names)
            assert len(request(3, "resources/list")["resources"]) == 16
            assert "connected" in request(4, "resources/read", {"uri": "resolve://system/status"})["contents"][0]["text"]
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
