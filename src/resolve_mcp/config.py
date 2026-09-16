"""Validated configuration; secrets never appear in repr or logs."""
import ipaddress
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 3001
    token: str = field(default="", repr=False)
    public_url: str = ""

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        transport = env.get("TRANSPORT", "stdio").lower()
        if transport == "http":
            transport = "streamable-http"
        if transport not in ("stdio", "streamable-http"):
            raise ValueError("TRANSPORT must be stdio, http, or streamable-http.")
        host = env.get("HOST", "127.0.0.1")
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            raise ValueError("HOST must be localhost or a numeric IP address.") from None
        port = int(env.get("PORT", "3001"))
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be between 1 and 65535.")
        token = env.get("MCP_AUTH_TOKEN", "")
        if token and (len(token) < 32 or any(c.isspace() for c in token)):
            raise ValueError("MCP_AUTH_TOKEN must have at least 32 characters and no whitespace.")
        if transport != "stdio" and not local and not token:
            raise ValueError("External HTTP binding requires MCP_AUTH_TOKEN and a TLS access gateway.")
        public_url = env.get("MCP_PUBLIC_URL", "").rstrip("/")
        if public_url:
            parsed = urlsplit(public_url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
                raise ValueError("MCP_PUBLIC_URL must be an HTTPS origin, e.g. https://resolve.example.com.")
            if transport != "stdio" and not token:
                raise ValueError("MCP_PUBLIC_URL requires MCP_AUTH_TOKEN.")
        return cls(transport, host, port, token, public_url)