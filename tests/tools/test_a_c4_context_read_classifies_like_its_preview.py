"""A model-backed C4 diagram's context read classifies its derived entities as its preview does (B80).

The C4 panel grouped derived entities by its own reading of the type table — each ArchiMate type under
the *first* C4 type that permits it — while the projection classifies by structure, so a component
diagram listed its components under "Software Systems". The projection's answer was served only by
the preview. The context read now serves the same rows, from the same function, so an editor can
group as the picture draws before it has previewed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")


def _component(root: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="application-component", name=name, summary=f"Summary for {name}", dry_run=False,
        repo_root=str(root),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


@pytest.fixture()
def scoped(tmp_path: Path) -> tuple[Any, str]:
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-C4C" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    backend = _component(root, "Backend")
    for part in ("Write Path", "Read Path"):
        added = mcp.artifact_add_connection(
            source_entity=backend, connection_type="archimate-composition", target_entity=_component(root, part),
            dry_run=False, repo_root=str(root),
        )
        assert added["wrote"], added
    created = mcp.artifact_create_diagram(
        diagram_type="c4-component", name="Backend components", dry_run=False, repo_root=str(root),
        diagram_entities={"_scope_entity_id": backend},
    )
    assert created["wrote"], created

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    return TestClient(build_api_app(diagrams_router)), str(created["artifact_id"])


def test_the_context_read_serves_the_rows_the_preview_does(scoped: tuple[Any, str]) -> None:
    client, diagram_id = scoped
    context = client.get(f"/api/diagrams/{diagram_id}/context")
    assert context.status_code == 200, context.text
    body = context.json()
    served = body["derived_entities"]

    preview = client.post("/api/diagrams/preview", json={
        "diagram_type": "c4-component", "name": "Backend components", "entity_ids": [], "connection_ids": [],
        "diagram_entities": body["diagram"]["diagram_entities"],
    })
    assert preview.status_code == 200, preview.text

    assert served, "a model-backed diagram derives its scope's parts"
    assert served == preview.json()["derived_entities"]
    drawn_as = {row["name"]: row["item_type"] for row in served}
    assert drawn_as["Write Path"] == drawn_as["Read Path"] == "component", drawn_as
