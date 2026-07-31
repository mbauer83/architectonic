"""Response declarations the diagram and matrix write routers share.

Split out so both routers state their statuses the same way, and so neither file has to carry the
declarations twice. Every status a handler can return is declared here: one the document does not
mention is a contract no client can rely on.
"""

from __future__ import annotations

from typing import Any

from fastapi import Response, status

from src.infrastructure.gui.routers._openapi import (
    READ_RESPONSES,
    WRITE_RESPONSES,
    OpenMapResponse,
)

#: A create answers 201 and names the resource in ``Location``; a dry run created nothing, so it
#: answers 200 with its plan. Both are declared, because a status a handler can return that the
#: document does not mention is a contract no client can rely on.
CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": OpenMapResponse, "description": "Dry-run plan; nothing was created"},
}

#: A detail route can also answer 404: an absent id names no resource.
DETAIL_RESPONSES: dict[int | str, Any] = {**WRITE_RESPONSES, **READ_RESPONSES}

DELETE_RESPONSES: dict[int | str, Any] = {
    **DETAIL_RESPONSES,
    200: {"model": OpenMapResponse, "description": "Dry-run plan; nothing was removed"},
}


def created(result: Any, response: Response, location: str) -> None:
    """201 with ``Location`` when it wrote; 200 when it was a dry run.

    A dry run created nothing, so naming a resource that does not exist would be a claim the client
    has no way to check.
    """
    if result.wrote:
        response.headers["Location"] = location
    else:
        response.status_code = status.HTTP_200_OK
