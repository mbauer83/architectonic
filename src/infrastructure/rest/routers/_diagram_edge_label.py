"""Edge-label override endpoint for the diagram GUI router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import TAG_DIAGRAMS, WRITE_RESPONSES, WriteResultResponse

router = APIRouter()


class SetEdgeLabelBody(BaseModel):
    """The label itself, and nothing that names the edge — both are path identity now.

    ``edge_key`` is ``"{src_alias}:{tgt_alias}"`` from the rendered PUML, which contains no slash, so
    it is a path segment like any other id."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    dry_run: bool = True


@router.put("/api/diagrams/{artifact_id}/edges/{edge_key}/label", tags=[TAG_DIAGRAMS],
    summary="Set a per-diagram edge label override", response_model=WriteResultResponse,
    responses=WRITE_RESPONSES)
def set_edge_label_gui(artifact_id: str, edge_key: str, body: SetEdgeLabelBody) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label

    repo_root, _, verifier = s.get_write_deps()
    try:
        result = s.authorized_write(
            "diagrams_set_diagram_edge_label", 
            set_diagram_edge_label,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            edge_key=edge_key,
            label=body.label,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)
