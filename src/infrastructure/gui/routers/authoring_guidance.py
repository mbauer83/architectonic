"""Read-only REST access to entity/diagram-type authoring guidance.

Exposes the same ``create_when``/``never_create_when``/permitted-connection/pair-legality
guidance MCP's ``artifact_authoring_guidance`` returns (``get_type_guidance``), for
REST-only frontend consumers (the guided modeling wizard) that have no MCP client.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.contracts.authoring_guidance import AuthoringGuidanceResponse
from src.infrastructure.gui.contracts.errors import ApiError, FieldError, ValidationErrorDetails
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._entity_filter import parse_csv_filter
from src.infrastructure.gui.routers._openapi import TAG_TAXONOMY
from src.infrastructure.write import artifact_write_ops

router = APIRouter()


@router.get("/api/authoring-guidance", tags=[TAG_TAXONOMY], summary="Authoring guidance for types",
    response_model=AuthoringGuidanceResponse, response_model_exclude_none=True)
def read_authoring_guidance(
    entity_type: str | None = None,
    domain: str | None = None,
    diagram_type: str | None = None,
    target: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    terms = parse_csv_filter(entity_type) | parse_csv_filter(domain)
    guidance = artifact_write_ops.get_type_guidance(
        filter=sorted(terms) if terms else None,
        diagram_type=diagram_type,
        target=target,
        catalogs=catalogs,
        # Connection metadata schemata are per-repo files; without the root the payload
        # could only carry guidance, and the connection editor would have no schema to
        # render (the entity side gets its own from /api/entity-schemata/{artifact_type}).
        repo_root=s.maybe_engagement_root(),
    )
    # A rejected request is a 422, not a 200 carrying an `error` string. The use case is shared with
    # MCP, where a dict payload *is* the contract, so the translation happens here rather than there —
    # and it reads the field the use case named rather than matching on the message.
    _reject_if_error(guidance, default_field="filter")
    # The pair check rejects the same way one level down. An unknown `target` reached a client as a
    # 200 whose `pair_guidance` carried an `error` and a list of known types — which is the shape
    # this release exists to remove, and it was invisible because only the top level was checked.
    pair = guidance.get("pair_guidance")
    if isinstance(pair, dict):
        _reject_if_error(pair, default_field="target")
    return guidance


def _reject_if_error(payload: dict[str, Any], *, default_field: str) -> None:
    """Turn the use case's rejection mapping into the typed 422 the surface promises."""
    if "error" not in payload:
        return
    message = str(payload["error"])
    raise ApiError(
        422, "validation_error", message,
        ValidationErrorDetails(field_errors=[
            FieldError(field=str(payload.get("field", default_field)), message=message)
        ]),
    )
