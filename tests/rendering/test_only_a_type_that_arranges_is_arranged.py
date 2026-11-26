"""A diagram is arranged on the canvas only where its type says it is (`arranges_on_canvas`).

The GUI decided "the canvas arranges this" by the `archimate` prefix of a type's name, and the layout writes
decided nothing. The diagram-type catalogue now states it, `/api/diagram-types` serves it, and the layout
patch and the arrangement — over REST and MCP alike — refuse a diagram of a type that says no, naming the
types that arrange.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.diagram_layout_wire import LayoutPatch
from src.infrastructure.mcp.artifact_mcp.layout_tools import artifact_arrange_diagram
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from src.infrastructure.rest.routers.diagrams.types import list_diagram_types
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


def test_the_type_list_says_which_types_are_arranged_on_the_canvas() -> None:
    listed = {row["key"]: row for row in list_diagram_types(process_runtime_catalogs())}
    assert listed["archimate-layered"]["arranges_on_canvas"] is True
    assert listed["c4-container"]["arranges_on_canvas"] is False


@pytest.fixture
def retyped(tmp_path: Path) -> tuple[RenderedModel, Path]:
    """One of the rendered ArchiMate diagrams, restated as a type the canvas does not arrange."""
    model = build_rendered_model(tmp_path)
    path = Path(model.scenes["top-to-bottom"].path)
    text = path.read_text(encoding="utf-8")
    assert "diagram-type: archimate-layered" in text
    path.write_text(text.replace("diagram-type: archimate-layered", "diagram-type: c4-container"), encoding="utf-8")
    return model, path


@pytest.fixture
def client(retyped: tuple[RenderedModel, Path]) -> Iterator[TestClient]:
    model, _ = retyped
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as served:
            yield served
    finally:
        reset_state_for_test()


def test_a_layout_write_refuses_a_type_that_is_not_arranged_and_names_those_that_are(
    retyped: tuple[RenderedModel, Path], client: TestClient,
) -> None:
    model, path = retyped
    before = path.read_text(encoding="utf-8")

    over_rest = client.patch(f"/api/diagrams/{path.stem}/layout", json={"patch": {}, "dry_run": False})
    with pytest.raises(ValueError, match="not arranged on the canvas") as over_mcp:
        artifact_arrange_diagram(artifact_id=path.stem, patch=LayoutPatch(), dry_run=False, repo_root=str(model.repo))

    assert over_rest.status_code == 400, over_rest.text
    for refusal in (over_rest.text, str(over_mcp.value)):
        assert "c4-container" in refusal and "archimate-layered" in refusal
    assert path.read_text(encoding="utf-8") == before
