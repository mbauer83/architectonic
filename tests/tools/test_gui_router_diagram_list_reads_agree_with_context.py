"""One producer, one shape: the diagram list reads answer exactly what the context read answers.

``/api/diagrams/{id}/entities`` and ``/api/diagrams/{id}/connections`` return, verbatim, the
``entities`` and ``connections`` of ``diagram_context_payload`` — the same function, the same values.
They nonetheless declared a pair of open three-field placeholders (``DiagramEntityItem``,
``DiagramConnectionItem``) and skipped ``response_model_exclude_none``, while the context read
declared the real DTOs and omitted its unset optionals. So one value had two contracts, and the pair
without ``exclude_none`` put ``"last_updated": null`` on the wire.

The client decodes both with the context read's schema — ``DiagramContextEntitySchema``, whose
``last_updated`` is ``optional(String)`` because the *document* said the key is absent when unset.
So the entity list threw in the decoder before a row was drawn: the FMEA defect's exact shape, one
release later, on a route no browser spec happens to read. Nothing saw it because both sides had
tests and both sides passed — each against a fixture it wrote itself.

What is asserted here is the agreement, not a field list. A field list would be one more copy of the
contract to drift; the agreement is the invariant, and it holds however the DTOs grow.
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

SRC_ID = "REQ@1000000094.DlrSrc.diagram-list-read-source"
TGT_ID = "REQ@1000000095.DlrTgt.diagram-list-read-target"
DIAG_ID = "DIAG@1000000096.DlrDia.diagram-list-read-diagram"
CONN_TYPE = "archimate-association"


def _requirement_md(artifact_id: str, name: str, alias: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {alias}
```
"""


def _diagram_puml() -> str:
    return f"""\
---
artifact-id: {DIAG_ID}
artifact-type: diagram
diagram-type: archimate-motivation
name: "Diagram List Read"
version: 0.1.0
status: draft
---
@startuml
Requirement(DLR_SRC, "Diagram List Read Source")
Requirement(DLR_TGT, "Diagram List Read Target")
Rel_Association(DLR_SRC, DLR_TGT, "")
@enduml
"""


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    from src.infrastructure.mcp import mcp_artifact_server as mcp

    root = tmp_path / "engagements" / "ENG-DLR" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "requirement"
    model_dir.mkdir(parents=True)
    (model_dir / f"{SRC_ID}.md").write_text(
        _requirement_md(SRC_ID, "Diagram List Read Source", "DLR_SRC"), encoding="utf-8"
    )
    (model_dir / f"{TGT_ID}.md").write_text(
        _requirement_md(TGT_ID, "Diagram List Read Target", "DLR_TGT"), encoding="utf-8"
    )
    diagram_dir = root / "diagram-catalog" / "diagrams"
    diagram_dir.mkdir(parents=True)
    (diagram_dir / f"{DIAG_ID}.puml").write_text(_diagram_puml(), encoding="utf-8")
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


def _nulls(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({key for row in rows for key, value in row.items() if value is None})


class TestTheTwoReadsAgree:
    def test_the_entity_list_is_the_context_reads_entities(self, client: Any) -> None:
        listed = client.get(f"/api/diagrams/{DIAG_ID}/entities")
        context = client.get(f"/api/diagrams/{DIAG_ID}/context")
        assert listed.status_code == 200, listed.text
        assert context.status_code == 200, context.text
        assert listed.json()["items"] == context.json()["entities"]

    def test_the_connection_list_is_the_context_reads_connections(self, client: Any) -> None:
        listed = client.get(f"/api/diagrams/{DIAG_ID}/connections")
        context = client.get(f"/api/diagrams/{DIAG_ID}/context")
        assert listed.status_code == 200, listed.text
        assert context.status_code == 200, context.text
        assert listed.json()["items"] == context.json()["connections"]


class TestNoUnsetOptionalReachesTheWire:
    """The half the agreement alone would not catch: both reads could agree *and* both send null.

    The client's decoders distinguish absent from null, and the published document — which those
    decoders are type-checked against — says these keys are absent when unset. A null is then a
    decode failure, the row is dropped, and the list renders empty with nothing logged.
    """

    def test_no_entity_row_carries_a_null(self, client: Any) -> None:
        rows = client.get(f"/api/diagrams/{DIAG_ID}/entities").json()["items"]
        assert rows, "the fixture places two entities, so an empty list means the read is broken"
        assert _nulls(rows) == []

    def test_no_connection_row_carries_a_null(self, client: Any) -> None:
        rows = client.get(f"/api/diagrams/{DIAG_ID}/connections").json()["items"]
        assert rows, "the fixture draws one connection, so an empty list means the read is broken"
        assert _nulls(rows) == []

    def test_the_context_read_agrees_and_always_did(self, client: Any) -> None:
        # It declared `exclude_none` from the start, so this is the control: without it the two
        # assertions above could be satisfied by making *every* read send nulls.
        context = client.get(f"/api/diagrams/{DIAG_ID}/context").json()
        assert _nulls(context["entities"]) == []
        assert _nulls(context["connections"]) == []
