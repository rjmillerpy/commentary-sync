"""Security headers on every response.

The API serves JSON to apps, never pages to a browser, so its Content-Security
-Policy allows nothing at all: if a response were ever rendered as a page, it
could load no script, style or frame. The interactive docs (/docs, /redoc)
are pages that load Swagger UI from a CDN, so they get no CSP; a deployed API
turns them off (COMMENTARY_API_DOCS=false).

Strict-Transport-Security is sent only when the API is served over HTTPS
(COMMENTARY_HSTS_SECONDS > 0): on plain HTTP it would be meaningless, and a
browser that saw it for localhost would refuse plain HTTP there for a year.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})
ALWAYS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts_seconds: int = 0) -> None:
        self.app = app
        self.headers = dict(ALWAYS)
        if hsts_seconds > 0:
            self.headers["Strict-Transport-Security"] = f"max-age={hsts_seconds}; includeSubDomains"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"] in DOCS_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", API_CSP)
            await send(message)

        await self.app(scope, receive, send_with_headers)
