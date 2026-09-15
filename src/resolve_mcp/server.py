"""FastMCP composition and both supported transport entry points."""
import argparse
import asyncio
import inspect
import json
import os
import sys
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__, resources
from .config import Config
from .security import BearerAuth
from .services.resolve_connection import status
from .tools import connection, project, timeline, media, editing, color, markers, titles, render, fusion, vision, analysis


class ResolveMCP(FastMCP):
    """Serialize tools and resources: Resolve has shared mutable selection state."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.operation_lock = asyncio.Lock()

    def _serialized(self, function):
        @wraps(function)
        async def call(*args, **kwargs):
            async with self.operation_lock:
                result = function(*args, **kwargs)
                return await result if inspect.isawaitable(result) else result
        return call

    def tool(self, *args, **kwargs):
        decorate = super().tool(*args, **kwargs)
        return lambda function: decorate(self._serialized(function))

    def resource(self, *args, **kwargs):
        decorate = super().resource(*args, **kwargs)
        return lambda function: decorate(self._serialized(function))


def create_server(config: Config | None = None) -> ResolveMCP:
    config = config or Config.from_env()
    hosts = ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    origins = ["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"]
    if config.host not in ("0.0.0.0", "::", "localhost", "127.0.0.1", "::1"):
        hosts.append(f"{config.host}:{config.port}")
    if config.public_url:
        hosts.append(urlsplit(config.public_url).netloc)
        origins.append(config.public_url)
    instance = ResolveMCP("resolve-mcp-server", json_response=True, host=config.host, port=config.port,
                          transport_security=TransportSecuritySettings(
                              enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins))
    for module in (connection, project, timeline, media, editing, color, markers, titles, render,
                   fusion, vision, analysis):
        module.register(instance)
    resources.register(instance)
    # Imported here to keep workflow helpers independent of server construction.
    from .tools import workflows
    workflows.register(instance)
    return instance


def http_app(instance, config):
    app = instance.streamable_http_app()
    return BearerAuth(app, config.token) if config.token else app


# Only a repository-local .env, or an explicitly selected file, is loaded.
_default_env = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(os.environ.get("RESOLVE_MCP_ENV_FILE", str(_default_env)), override=False)
mcp = create_server(Config())


def main():
    parser = argparse.ArgumentParser(description="AI-native editing for DaVinci Resolve")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--doctor", action="store_true", help="Read-only Resolve connection diagnostics")
    args = parser.parse_args()
    if args.doctor:
        print(json.dumps(status(), indent=2))
        return
    try:
        config = Config.from_env()
    except ValueError as exc:
        parser.error(str(exc))
    instance = create_server(config)
    print(f"[resolve-mcp] {__version__} | {config.transport}", file=sys.stderr)
    if config.transport == "stdio":
        instance.run(transport="stdio")
    else:
        import uvicorn
        uvicorn.run(http_app(instance, config), host=config.host, port=config.port, access_log=False)


if __name__ == "__main__":
    main()
