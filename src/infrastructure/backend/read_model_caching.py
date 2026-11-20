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

**Only model-derived operations may opt in.** A response that also depends on git state, the
confidential store, or the clock is not a function of the model generation, so an ETag
derived from it would be a promise the server cannot keep — a stale 304 is invisible to the
client and indistinguishable from correct data.

Which operations qualify is decided in the route-policy manifest (``conditional_read="etag"``),
not here. This module used to hold its own exact-string list, and an exact string cannot express
`/api/entities/{artifact_id}` at all — nor survive a rename, which dropped the ETag silently.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from src.application.read_model_purity import dependence_of_rest_template
from src.application.read_models import ReadDependence
from src.infrastructure.rest.route_policy import SERVED_CONDITIONAL_READ_TEMPLATES, template_matcher

#: Route templates whose body is a pure function of the indexed model and the URL, compiled once.
#:
#: **Templates, not exact paths.** It was exact-string membership, and identity has moved into the
#: path: `/api/entities/{artifact_id}` cannot be listed as a literal, and renaming a listed path
#: silently dropped its ETag with nothing failing. The set comes from the route-policy manifest,
#: which is where cache eligibility is decided, so the registry is no longer a second copy of that
#: decision that someone has to remember to edit.
#:
#: Eligibility remains an **allowlist**, never a denylist: a new endpoint is uncached until someone
#: establishes that its body is a function of the model generation. The manifest's docstrings record
#: the deliberate exclusions — viewpoint definitions live outside the index and are reloaded per
#: request; schemata are repo data outside the indexed artifact set; anything under `/api/sync/` or
#: `/api/assurance/` moves with git state or the confidential store, independently of the model.
#:
#: Each carries **what its body depends on**, which is the purity table's to say and decides which of
#: the read model's validators answers for it. Nearly all depend on the model alone. An entity's page
#: also lists the scratchpads that reference the entity, and a search returns scratchpads themselves;
#: a scratchpad save does not move the model's generation, so those two were told `304` over a body
#: that had changed.
_CACHEABLE_TEMPLATES: tuple[tuple[re.Pattern[str], ReadDependence], ...] = tuple(
    (template_matcher(template), dependence_of_rest_template(template))
    for template in sorted(SERVED_CONDITIONAL_READ_TEMPLATES)
)


def _is_cacheable(path: str) -> bool:
    return _dependence_of(path) is not None


def _dependence_of(path: str) -> ReadDependence | None:
    """What the read at *path* depends on, or None when it is not a conditional read at all."""
    return next((dependence for pattern, dependence in _CACHEABLE_TEMPLATES if pattern.match(path)), None)


def _entity_tag(model_etag: str, request: Request) -> str:
    """Model generation plus the exact URL — same model and same question, same answer."""
    digest = hashlib.blake2b(
        f"{model_etag}\n{request.url.path}?{request.url.query}".encode(), digest_size=16
    ).hexdigest()
    return f'W/"{digest}"'


def _current_validator(dependence: ReadDependence) -> str | None:
    """The read model's tag for a body with this dependence, or None when no repository is
    initialized yet."""
    from src.infrastructure.rest.routers import state as s  # noqa: PLC0415

    try:
        return s.get_repo().read_model_version().validator(dependence)
    except Exception:  # noqa: BLE001 — never let caching break a request
        return None


async def conditional_read_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    dependence = _dependence_of(request.url.path) if request.method == "GET" else None
    if dependence is None:
        return await call_next(request)

    model_etag = _current_validator(dependence)
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
