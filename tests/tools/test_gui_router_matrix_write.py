"""The matrix write surface, through the served app: preview, create, replace, read back.

`POST /api/matrices/preview` answered **500 for every caller**. It declared
``response_model=WriteResultResponse`` — the six-key mutation envelope — and returned
``{"markdown": …}``, so FastAPI's response validation raised on every call and the client got a body
that deliberately carries no diagnostic. The Preview button on both matrix views had never worked
through the running server, which is exactly what `NEVER_REQUESTED_OPERATIONS` recorded: three of the
four operations below had never once answered 2xx.

Nothing caught it because nothing asked. The matrix tests that exist call
``artifact_create_matrix`` and ``build_matrix_markdown`` directly — the "assert what I injected"
shape — and no test posted to the route. A dry run is not a mutation and does not share its
envelope, so the fix is a DTO of its own; this holds the whole surface against the served app so the
next wrong ``response_model`` here is a red test rather than a 500 in the browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

SRC_ID = "REQ@1000000090.MtxSrc.matrix-source-requirement"
TGT_ID = "REQ@1000000091.MtxTgt.matrix-target-requirement"


def _requirement_md(artifact_id: str, name: str) -> str:
    alias = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

A requirement the matrix write tests place on an axis.

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{alias}
```
"""


#: The relationship the matrix draws. A matrix with no connection between its axes renders an empty
#: body by design, so a fixture without one could only ever exercise the empty case — which is the
#: case the defect happened to be in, and would have left the populated one untested.
CONN_TYPE = "archimate-association"


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    from src.infrastructure.mcp import mcp_artifact_server as mcp

    root = tmp_path / "engagements" / "ENG-MTX" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "requirement"
    model_dir.mkdir(parents=True)
    (model_dir / f"{SRC_ID}.md").write_text(_requirement_md(SRC_ID, "Matrix Source"), encoding="utf-8")
    (model_dir / f"{TGT_ID}.md").write_text(_requirement_md(TGT_ID, "Matrix Target"), encoding="utf-8")
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    result = mcp.artifact_add_connection(
        source_entity=SRC_ID,
        connection_type=CONN_TYPE,
        target_entity=TGT_ID,
        dry_run=False,
        repo_root=str(root),
    )
    assert result["wrote"], result
    return root


@pytest.fixture()
def client(populated_root: Path) -> Any:
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    return TestClient(build_api_app(diagrams_router))


def _axes() -> dict[str, Any]:
    return {
        "entity_ids": [SRC_ID, TGT_ID],
        "conn_type_configs": [{"conn_type": CONN_TYPE, "active": True}],
        "combined": True,
    }


class TestPreview:
    def test_a_preview_answers_the_rendered_body_and_nothing_else(self, client: Any) -> None:
        response = client.post("/api/matrices/preview", json=_axes())
        assert response.status_code == 200, response.text
        body = response.json()
        # The whole of the contract: a dry run wrote nothing, so it has no `wrote`, no `path` and no
        # `artifact_id` to report — declaring the mutation envelope here is what raised.
        assert list(body) == ["markdown"]
        assert isinstance(body["markdown"], str)

    def test_the_rendered_body_places_both_axis_entities(self, client: Any) -> None:
        body = client.post("/api/matrices/preview", json=_axes()).json()
        assert "Matrix Source" in body["markdown"]
        assert "Matrix Target" in body["markdown"]

    def test_an_asymmetric_preview_renders_the_two_axes_it_was_given(self, client: Any) -> None:
        response = client.post(
            "/api/matrices/preview",
            json={
                "entity_ids": [SRC_ID],
                "conn_type_configs": [{"conn_type": CONN_TYPE, "active": True}],
                "combined": True,
                "from_entity_ids": [SRC_ID],
                "to_entity_ids": [TGT_ID],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["markdown"] != ""

    def test_an_empty_population_is_a_body_rather_than_a_failure(self, client: Any) -> None:
        # `{"markdown": ""}` was the input that raised, so the empty case is the regression's own
        # shape: a matrix with nothing on its axes renders nothing and still answers 200.
        response = client.post(
            "/api/matrices/preview", json={"entity_ids": [], "conn_type_configs": [], "combined": True}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"markdown": ""}


class TestCreateAndReplace:
    def _create(self, client: Any) -> str:
        response = client.post(
            "/api/matrices", json={"name": "Requirement Coverage", **_axes(), "dry_run": False}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["wrote"], body
        return str(body["artifact_id"])

    def test_a_create_reports_the_mutation_envelope(self, client: Any) -> None:
        response = client.post(
            "/api/matrices", json={"name": "Requirement Coverage", **_axes(), "dry_run": True}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # A dry-run create *is* a mutation's envelope, unlike the preview: it reports what the write
        # would have produced, including the verification of it. That asymmetry is the reason the two
        # cannot share one DTO.
        assert body["wrote"] is False
        assert set(body) == {"wrote", "path", "artifact_id", "content", "warnings", "verification"}

    def test_a_created_matrix_reads_back_its_configuration(self, client: Any) -> None:
        artifact_id = self._create(client)
        response = client.get(f"/api/matrices/{artifact_id}/config")
        assert response.status_code == 200, response.text
        config = response.json()
        assert config["artifact_id"] == artifact_id
        assert sorted(config["entity_ids"]) == sorted([SRC_ID, TGT_ID])
        # Square, so neither axis was authored separately — present and null, not absent.
        assert config["from_entity_ids"] is None
        assert config["to_entity_ids"] is None
        assert config["matrix_body"] != ""

    def test_a_replacement_states_what_the_matrix_becomes(self, client: Any) -> None:
        artifact_id = self._create(client)
        response = client.put(
            f"/api/matrices/{artifact_id}",
            json={
                "name": "Requirement Coverage",
                "entity_ids": [SRC_ID],
                "conn_type_configs": [{"conn_type": CONN_TYPE, "active": True}],
                "combined": True,
                "dry_run": False,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["wrote"], response.text
        config = client.get(f"/api/matrices/{artifact_id}/config").json()
        assert config["entity_ids"] == [SRC_ID]
