"""SPA-aware static serving: history-fallback to index.html for client-side routes."""

from __future__ import annotations

from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

#: Suffixes that mark a request as a static asset rather than a client-side route.
#:
#: A closed set, checked against the final segment's extension, rather than "the segment contains a
#: dot". Every artifact id contains dots — ``ADR@1780761591._mseZr.adopt-archimate-next-ontology``
#: — so the dot test rejected every artifact deep link, and `/documents/<id>` 404ed on direct
#: navigation, reload, or a bookmark. The set stays the guard against masking a missing bundle with
#: HTML, which is what that test was for.
ASSET_SUFFIXES = frozenset({
    "css", "js", "mjs", "cjs", "map", "json", "wasm",
    "png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "bmp",
    "woff", "woff2", "ttf", "otf", "eot",
    "txt", "xml", "webmanifest", "pdf", "zip", "gz", "br", "mp4", "webm",
})


def _looks_like_asset(last_segment: str) -> bool:
    """True when the final path segment names a file the browser expects verbatim.

    Keyed on a known suffix, so a route segment that merely contains dots (an artifact id, a
    version string) is not mistaken for one.
    """
    _, dot, suffix = last_segment.rpartition(".")
    return bool(dot) and suffix.lower() in ASSET_SUFFIXES


class SPAStaticFiles(StaticFiles):
    """StaticFiles that serves index.html for unmatched client-side routes.

    A single-page app routes on the client, so a deep link such as ``/entities/groups`` or
    ``/documents/ADR@1780761591._mseZr.adopt-archimate-next-ontology`` has no file on disk; plain
    ``StaticFiles`` 404s it. This subclass falls back to ``index.html`` for such paths so the SPA
    boots and resolves the route itself (and direct navigation / refresh / bookmarks work on any
    route). Guards keep the fallback narrow:

    - ``api/`` and ``mcp/`` paths are never rewritten — they are matched by their own routes
      before this mount, and if an unknown one reaches here it still 404s.
    - Paths naming a static asset by its suffix (a missing ``assets/old.js``) 404 normally rather
      than being masked by HTML. See ``ASSET_SUFFIXES``.
    """

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            last_segment = path.rsplit("/", 1)[-1]
            if (
                exc.status_code == 404
                and not path.startswith(("api/", "mcp/"))
                and not _looks_like_asset(last_segment)
            ):
                return await super().get_response("index.html", scope)
            raise
