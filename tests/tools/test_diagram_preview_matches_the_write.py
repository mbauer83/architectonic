"""A preview shows the diagram the write would make, field for field.

Preview, create and replace each assembled the renderer's arguments themselves, and drifted twice
over. `authored_groupings` reached the two writes and never the preview, so a diagram's custom boxes
were invisible until it was saved. And the writes stripped connection *bindings* before rendering
while preview did not, so the two were not even rendering the same input.

Neither was caught, because every test drove one surface at a time and asked whether *that* surface
worked. What no test asked is the thing a preview is for: that it agrees with the write. This asks it
directly, over the composition the three now share, so a field added to one and not the others fails
here rather than in front of someone authoring a diagram.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

FIRST = "GOL@1000000030.PrevAa.first-goal"
SECOND = "GOL@1000000030.PrevBb.second-goal"


def _entity_md(artifact_id: str, name: str) -> str:
    random_key = artifact_id.split(".")[1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: goal
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Goal
label: "{name}"
alias: GOL_{random_key}
```
"""


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    root = tmp_path / "engagements" / "ENG-PREV" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "goal"
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    for artifact_id, name in ((FIRST, "First Goal"), (SECOND, "Second Goal")):
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / f"{artifact_id}.md").write_text(_entity_md(artifact_id, name), encoding="utf-8")

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = build_api_app(diagrams_router)
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    with TestClient(app) as test_client:
        yield test_client


def _composition(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "diagram_type": "archimate-motivation",
        "name": "Preview Parity",
        "entity_ids": [FIRST, SECOND],
        "connection_ids": [],
    }
    body.update(overrides)
    return body


class TestThePreviewIsTheWritesOwnPicture:
    def test_a_grouping_reaches_the_preview(self, client) -> None:
        """The defect: boxes appeared only once the diagram was written."""
        body = _composition(
            authored_groupings=[{"label": "The Goals", "entity-ids": [FIRST, SECOND]}]
        )

        response = client.post("/api/diagrams/preview", json=body)

        assert response.status_code == 200, response.text
        assert '"The Goals"' in response.json()["puml"]

    def test_preview_and_create_render_the_same_puml(self, client) -> None:
        """The invariant behind it: whatever a composition says, both surfaces draw it the same."""
        body = _composition(
            authored_groupings=[{"label": "The Goals", "entity-ids": [FIRST, SECOND]}]
        )

        previewed = client.post("/api/diagrams/preview", json=body)
        created = client.post("/api/diagrams", json={**body, "dry_run": True})

        assert previewed.status_code == 200, previewed.text
        assert created.status_code in (200, 201), created.text
        preview_puml = previewed.json()["puml"]
        written_puml = created.json().get("content") or ""
        assert '"The Goals"' in preview_puml
        assert '"The Goals"' in written_puml, "the write dropped what the preview drew"

    def test_a_preview_without_groupings_draws_no_box(self, client) -> None:
        """So the assertion above cannot pass by the label appearing for some other reason."""
        response = client.post("/api/diagrams/preview", json=_composition())

        assert response.status_code == 200, response.text
        assert '"The Goals"' not in response.json()["puml"]

    def test_every_composition_field_is_shared_by_all_three_surfaces(self) -> None:
        """The structural guard: the three bodies must not drift apart again.

        They each declared the composition themselves once, which is how preview came to lack a
        field the writes had. Inheriting one declaration is what makes that impossible; this fails if
        someone re-declares the fields on one body instead of adding them to the shared one.
        """
        from src.infrastructure.rest.routers.diagrams._write_bodies import (
            CreateDiagramGuiBody,
            DiagramComposition,
            DiagramPreviewBody,
            EditDiagramGuiBody,
        )

        composition_fields = set(DiagramComposition.model_fields)
        assert composition_fields, "the shared composition declares nothing"
        for body in (DiagramPreviewBody, CreateDiagramGuiBody, EditDiagramGuiBody):
            assert issubclass(body, DiagramComposition), f"{body.__name__} does not share the composition"
            assert composition_fields <= set(body.model_fields)
