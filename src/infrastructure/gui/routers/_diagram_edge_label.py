"""Edge-label override endpoint for the diagram GUI router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import TAG_DIAGRAMS, WRITE_RESPONSES, OpenMapResponse

router = APIRouter()


class SetEdgeLabelBody(BaseModel):
    artifact_id: str
    edge_key: str
    label: str | None = None
    dry_run: bool = True


@router.put("/api/diagram/edge-label", tags=[TAG_DIAGRAMS], summary="Set a per-diagram edge label override",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def set_edge_label_gui(body: SetEdgeLabelBody) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label

    repo_root, _, verifier = s.get_write_deps()
    try:
        result = s.authorized_write(("PUT", "/api/diagram/edge-label"), 
            set_diagram_edge_label,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            edge_key=body.edge_key,
            label=body.label,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)
