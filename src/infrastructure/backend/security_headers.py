"""The response headers that tell a browser what this backend's pages may do.

Every response carries them, whichever surface produced it, so a page is never served without the
policy that confines it. The application's own pages — the GUI — get the strict policy: scripts only
from this origin and never inline, nothing may frame them, and nothing is fetched from elsewhere. The
GUI renders repository content as HTML (markdown, diagrams), and while every such sink sanitises
first, the policy is what holds if one ever does not.

Two relaxations, each with its reason:

* **Styles may be inline.** Rendered diagrams are SVG documents whose shapes carry `style`
  attributes and `<style>` elements; refusing them would draw every diagram unstyled. Inline style
  cannot run code.
* **The interactive API documentation** (`/docs`, `/redoc`, `/docs/<section>`) is the framework's
  page, which loads its viewer from a CDN and starts it with an inline script. Those pages show the
  generated API description and no repository content; they get a policy admitting exactly that.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _policy(*directives: str) -> str:
    return "; ".join(directives)


#: The GUI's policy, and every response's but the documentation pages'.
APPLICATION_POLICY = _policy(
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)

_DOCUMENTATION_CDN = "https://cdn.jsdelivr.net"

#: The framework's documentation pages: their viewer from the CDN, started by an inline script.
DOCUMENTATION_POLICY = _policy(
    "default-src 'self'",
    f"script-src 'self' 'unsafe-inline' {_DOCUMENTATION_CDN}",
    f"style-src 'self' 'unsafe-inline' {_DOCUMENTATION_CDN} https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)

#: Headers every response carries, whatever its policy.
_COMMON_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"x-frame-options", b"DENY"),
)


class SecurityHeaders:
    """ASGI middleware adding the content security policy and its companions to every response."""

    def __init__(self, app: ASGIApp, *, is_documentation: Callable[[str], bool]) -> None:
        self.app = app
        self._is_documentation = is_documentation

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        policy = DOCUMENTATION_POLICY if self._is_documentation(scope["path"]) else APPLICATION_POLICY
        added = ((b"content-security-policy", policy.encode("latin-1")), *_COMMON_HEADERS)

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = [
                    *message.get("headers", []),
                    *(header for header in added if header[0] not in present),
                ]
            await send(message)

        await self.app(scope, receive, with_headers)
