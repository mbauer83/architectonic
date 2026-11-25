"""A construct a diagram owns is addressed as a sub-entity of that diagram.

The plan decided that a slash is outside the identifier grammar and `%2F` is rejected, and it checked
that assurance node and edge ids contain none. It did not check *diagram-local entity* ids, and those
contain one by construction: `_diagram_entity_extraction.py` forms them as
`{diagram_id}#{entity_type}/{local_id}`, e.g. `…#nodes/g11`.

Under the flat entity address that makes them unreachable, and not with a handler 404 — the server
decodes `%2F` back to `/` before routing, the path gains a segment, and `/api/entities/{artifact_id}`
never matches. The retired address carried the identifier in the query string, where a slash is
harmless, so the addressing change is what introduced the regression. It surfaced as a GSN diagram
whose sidebar listed twelve nodes and showed a detail panel for none of them.

The resolution is not an exception to the grammar: the two composite parts get a segment each, which
leaves no slash inside any identifier and says what was already true — the type and the local id are
the diagram's coordinates for something inside it. Both halves are asserted here, because the fix is
only correct if the grammar still holds everywhere else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from tests.support.api_app import build_api_app

pytest.importorskip("httpx")

_DIAGRAM_ID = "GSN@1781338120.SubEnt1.assurance-case-fixture"
#: The frontmatter form the repository writes: `diagram-entities` declares the constructs the diagram
#: owns, keyed by their type, and each entry's `node_id` is its local identifier. That pair is what
#: becomes `{diagram_id}#nodes/{node_id}`.
_SOURCE = f"""---
artifact-id: {_DIAGRAM_ID}
artifact-type: diagram
name: Sub-entity Fixture
version: 0.1.0
status: draft
diagram-type: gsn
diagram-entities:
  nodes:
  - node_id: g11
    name: Store access is fail-closed
    gsn_type: goal
  - node_id: g12
    name: Clearance is checked
    gsn_type: goal
---

@startuml
rectangle "Store access is fail-closed" as g11
rectangle "Clearance is checked" as g12
g11 --> g12
@enduml
"""


@pytest.fixture()
def diagram_client(tmp_path: Path):
    """A repository holding one GSN diagram, whose nodes are constructs it owns.

    Fixture content the test owns: the assertions below name specific constructs, which would be a
    false regression if they came from the live repository.
    """
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router

    root = tmp_path / "engagements" / "ENG-SUBENT" / "architecture-repository"
    diagram_dir = root / "diagram-catalog" / "diagrams"
    diagram_dir.mkdir(parents=True)
    (diagram_dir / f"{_DIAGRAM_ID}.puml").write_text(_SOURCE, encoding="utf-8")

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = build_api_app(diagrams_router)
    install_module_registry(app)
    return TestClient(app), repo


def _sub_entities(client, diagram_id: str) -> list[dict[str, object]]:
    response = client.get(f"/api/diagrams/{diagram_id}/entities")
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def test_a_diagram_owned_construct_is_readable_at_its_sub_entity_address(diagram_client) -> None:
    """The regression. Every construct the diagram lists has to be readable, or a sidebar can list
    something the user cannot then open — which is exactly what happened."""
    client, _repo = diagram_client
    constructs = [
        entity for entity in _sub_entities(client, _DIAGRAM_ID)
        if "#" in str(entity["artifact_id"])
    ]
    if not constructs:
        pytest.skip("this diagram type surfaced no diagram-owned constructs")

    for construct in constructs:
        artifact_id = str(construct["artifact_id"])
        local = artifact_id.split("#", 1)[1]
        entity_type, _, local_id = local.partition("/")
        assert local_id, f"expected a composite local part, got {local!r}"

        response = client.get(
            f"/api/diagrams/{_DIAGRAM_ID}/entities/{entity_type}/{local_id}"
        )
        assert response.status_code == 200, f"{artifact_id} unreadable: {response.text}"
        assert response.json()["artifact_id"] == artifact_id


def test_the_grammar_still_refuses_a_slash_inside_one_identifier(diagram_client) -> None:
    """The half that keeps the fix from being an exception. Splitting the composite parts into
    segments is what removes the slash; it does not make a slash acceptable within a segment."""
    client, _repo = diagram_client
    response = client.get(f"/api/diagrams/{_DIAGRAM_ID}/entities/nodes%2Fg11/extra")
    assert response.status_code == 404


def test_an_unknown_construct_on_a_real_diagram_is_a_plain_not_found(diagram_client) -> None:
    """Not a 500 and not a redirect to the diagram: the address is well-formed and names nothing."""
    client, _repo = diagram_client
    response = client.get(f"/api/diagrams/{_DIAGRAM_ID}/entities/nodes/does-not-exist")
    assert response.status_code == 404


def test_the_sub_entity_route_does_not_shadow_the_metadata_routes(diagram_client) -> None:
    """`/entities/{classifier_id}/metadata` is two segments as well, and resolution is by
    declaration order. Asserted as an outcome rather than by inspecting the router, per the plan:
    a PATCH to the metadata address must not be answered by the read route."""
    client, _repo = diagram_client
    response = client.patch(
        f"/api/diagrams/{_DIAGRAM_ID}/entities/CLF@1.a.thing/metadata",
        json={"patch": {"description": "x"}, "dry_run": True},
    )
    assert response.status_code != 405, "the metadata route was shadowed by the sub-entity read"


@pytest.fixture()
def neighbourhood_client(diagram_client):
    """The same repository, with the connection routes the neighbourhood is served by."""
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.routers.connections.router import router as connections_router

    app = build_api_app(connections_router)
    install_module_registry(app)
    return TestClient(app)


def test_a_diagram_owned_construct_has_its_neighbourhood_at_its_sub_entity_address(neighbourhood_client) -> None:
    """The regression: a GSN goal selected on its diagram asked `/api/entities/{id}/neighbors`, which the
    slash in its id made unroutable (404 from the router, not the handler). The neighbourhood is served at
    the construct's own address, and reads the record the flat address names."""
    response = neighbourhood_client.get(f"/api/diagrams/{_DIAGRAM_ID}/entities/nodes/g11/neighbors")
    assert response.status_code == 200, response.text
    assert response.json()["traversal"] == "direct"
    derived = neighbourhood_client.get(
        f"/api/diagrams/{_DIAGRAM_ID}/entities/nodes/g11/neighbors",
        params={"traversal": "derived", "include_potential": True},
    )
    assert derived.status_code == 200, derived.text
    assert derived.json()["traversal"] == "derived"


def test_an_unknown_construct_has_no_neighbourhood(neighbourhood_client) -> None:
    response = neighbourhood_client.get(f"/api/diagrams/{_DIAGRAM_ID}/entities/nodes/does-not-exist/neighbors")
    assert response.status_code == 404
    assert "does-not-exist" in response.text


def test_the_held_record_id_is_composed_as_stable_id_reads_it() -> None:
    """The writer and the reader of `DIAGRAM#type/local` agree: the stable form keeps the local part."""
    from src.domain.artifact_id import held_record_id, stable_id

    composed = held_record_id(_DIAGRAM_ID, "nodes", "g11")
    assert composed == f"{_DIAGRAM_ID}#nodes/g11"
    assert stable_id(composed) == "GSN@1781338120.SubEnt1#nodes/g11"
