"""Response declarations the diagram and matrix write routers share.

Split out so both routers state their statuses the same way, and so neither file has to carry the
declarations twice. Every status a handler can return is declared here: one the document does not
mention is a contract no client can rely on.

A dry run reports the same closed write result as the committed write — it differs in *status*, not in
shape. Declaring it as an open map said otherwise, and that is what kept these operations counted as
untyped while returning exactly what the manifest already named.
"""

from __future__ import annotations

from typing import Any

from fastapi import Response, status

from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    WRITE_RESPONSES,
    WriteResultResponse,
)

#: A create answers 201 and names the resource in ``Location``; a dry run created nothing, so it
#: answers 200 with its plan. Both are declared, because a status a handler can return that the
#: document does not mention is a contract no client can rely on.
CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was created"},
}

#: A detail route can also answer 404: an absent id names no resource.
DETAIL_RESPONSES: dict[int | str, Any] = {**WRITE_RESPONSES, **READ_RESPONSES}

DELETE_RESPONSES: dict[int | str, Any] = {
    **DETAIL_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was removed"},
}


class SyncDiagramToModelResponse(WriteResultResponse):
    """What a sync wrote, plus what reconciling against the model pruned from the diagram.

    A plain closed subtype of the write result, not a mixed success/failure body: ``warnings`` are
    advisory, ``verification`` is a validity report, and a real failure raises — ``ValueError`` becomes
    a 400 and the authorization refusal its own status. So there is no partial outcome here to declare.

    ``deleted_diagram`` is the refresh-never-deletes contract reporting on itself. Every construction
    site in ``artifact_write/diagram_sync.py`` sets it ``False``, including the one where every
    referenced entity has gone stale (``:256``) — that case preserves the diagram deliberately, because
    silent deletion is the failure the flag exists to rule out. The handler built this body without it,
    so the guarantee was one the response could not state; ``tests/tools/test_scope_bound_refresh.py``
    had to settle for asserting the key was *not* ``True``.
    """

    removed_entity_ids: list[str]
    removed_connection_ids: list[str]
    deleted_diagram: bool


def created(result: Any, response: Response, location: str) -> None:
    """201 with ``Location`` when it wrote; 200 when it was a dry run.

    A dry run created nothing, so naming a resource that does not exist would be a claim the client
    has no way to check.
    """
    if result.wrote:
        response.headers["Location"] = location
    else:
        response.status_code = status.HTTP_200_OK
