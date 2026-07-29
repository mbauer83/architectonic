"""Conditional GET for reads that are a pure function of the read model.

A body derived only from the indexed model and the request URL cannot change while the
model's generation does not. That is exactly what an ETag expresses, and the read model
already publishes one — ``ReadModelVersion.etag``, bumped on every index generation. Serving
it lets a client that already holds the current answer be told so, instead of the server
re-deriving, re-validating and re-serializing a response the client will discard.

That matters most where many clients poll the same small set of URLs, which is the shape of
this product's load: a GUI refreshing its lists, and agents re-reading the same entities.
Measured on this repository, the application work behind a list is ~0.25 ms while the served
request costs ~15 ms; a 304 skips essentially all of the difference.

Applied as middleware rather than per handler so it reaches every model-derived read at once
and cannot be forgotten by the next one added.

**Only model-derived paths may opt in.** A response that also depends on git state, the
confidential store, or the clock is not a function of the model generation, so an ETag
derived from it would be a promise the server cannot keep — a stale 304 is invisible to the
client and indistinguishable from correct data. The prefix list is therefore an allowlist,
never a denylist: a new endpoint is uncached until someone establishes that it qualifies.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

#: Read paths whose body is a pure function of the indexed model and the URL.
#:
#: EXACT paths, never prefixes. A prefix silently adopts every route added beneath it later,
#: which is the one way a resource that reads outside the index could start being cached
#: without anyone deciding that it should. Adding an entry here is a claim that
#: `tests/infrastructure/test_read_model_caching_coverage.py` then has to demonstrate: write
#: something of that kind, and the validator must change.
#:
#: Deliberately absent, because the read-model generation does not track them:
#:   * `/api/viewpoints` — definitions live in `.arch-repo/` and are reloaded per request by
#:     `fresh_viewpoints_runtime_catalogs_dependency`, precisely because the index does not
#:     see them; an index-derived validator would pin a catalog the user just edited.
#:   * `/api/entity-schemata`, `/api/entity-taxonomy` — schemata are repo data outside the
#:     indexed artifact set.
#:   * anything under `/api/sync/`, `/api/assurance/` — git state and the confidential store
#:     move independently of the model generation.
_MODEL_DERIVED_PATHS: frozenset[str] = frozenset({
    "/api/entities",
    "/api/entity",
    "/api/entity-context",
    "/api/connections",
    "/api/diagrams",
    "/api/diagram-entities",
    "/api/documents",
    "/api/stats",
})


def _is_cacheable(path: str) -> bool:
    return path in _MODEL_DERIVED_PATHS


def _entity_tag(model_etag: str, request: Request) -> str:
    """Model generation plus the exact URL — same model and same question, same answer."""
    digest = hashlib.blake2b(
        f"{model_etag}\n{request.url.path}?{request.url.query}".encode(), digest_size=16
    ).hexdigest()
    return f'W/"{digest}"'


def _current_model_etag() -> str | None:
    """The read model's own version tag, or None when no repository is initialized yet."""
    from src.infrastructure.gui.routers import state as s  # noqa: PLC0415

    try:
        return str(s.get_repo().read_model_version().etag)
    except Exception:  # noqa: BLE001 — never let caching break a request
        return None


async def conditional_read_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    if request.method != "GET" or not _is_cacheable(request.url.path):
        return await call_next(request)

    model_etag = _current_model_etag()
    if model_etag is None:
        return await call_next(request)

    tag = _entity_tag(model_etag, request)
    if request.headers.get("if-none-match") == tag:
        # No body, and deliberately no re-derivation: the client already holds this answer.
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "no-cache"})

    response = await call_next(request)
    if response.status_code == 200:
        response.headers["ETag"] = tag
        # `no-cache` means "revalidate", not "do not store": the client keeps the body and
        # asks whether it is still current, which is the exchange this whole mechanism is for.
        response.headers["Cache-Control"] = "no-cache"
    return response
