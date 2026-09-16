"""Shared bearer-token access for clients that support custom HTTP headers.

This is not an OAuth authorization server. Use an OAuth-capable gateway for
clients requiring interactive login, and TLS for every remote deployment.
"""
import hmac
from starlette.responses import JSONResponse


class BearerAuth:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = [v for k, v in scope["headers"] if k.lower() == b"authorization"]
            valid = False
            if len(headers) == 1:
                scheme, _, candidate = headers[0].partition(b" ")
                valid = scheme.lower() == b"bearer" and hmac.compare_digest(candidate, self.token)
            if not valid:
                response = JSONResponse({"error": "Unauthorized"}, status_code=401,
                                        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)