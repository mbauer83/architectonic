"""A candidate is sketched on its own picture, which needs no stored diagram.

The editor's reads — the picture, its context, a session's drawing over it, resized shapes — are served with
the candidate as the subject. A candidate that reads over nothing opens on the empty picture; one that reads
over model elements opens on the view generated from them; one drawn on a stored diagram opens on that
diagram, exactly as the diagram's own editor reads it. Nothing is written by any of them.
"""

from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import candidate_picture, candidates, state
from src.infrastructure.rest.routers.diagrams import router as diagrams
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

_SOURCE = Path(__file__).resolve().parents[2] / "engagements/ENG-ARCH-REPO/architecture-repository"
_DIAGRAM = "ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements"
_SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    for filename in (f"{_DIAGRAM}.puml", f"{_SERVICE}.md"):
        original = next(_SOURCE.rglob(filename))
        target = root / original.relative_to(_SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(original, target)
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, candidate_picture.router, diagrams.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _candidate(client: TestClient, **record: object) -> str:
    created = client.post("/api/candidates", json={"record": {"name": "Naive", **record}})
    assert created.status_code == 200, created.text
    return str(created.json()["record"]["id"])


def _files(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file() and "candidate-architectures" not in path.parts}


def test_a_candidate_that_reads_over_nothing_opens_on_the_empty_picture(client: TestClient) -> None:
    ref = _candidate(client)

    picture = client.get(f"/api/candidates/{ref}/picture")
    context = client.get(f"/api/candidates/{ref}/picture/context")

    assert picture.status_code == 200, picture.text
    assert (picture.json()["elements"], picture.json()["relations"]) == ([], [])
    assert picture.json()["canvas"]["right"] > 0
    assert context.status_code == 200, context.text
    assert context.json()["diagram"]["artifact_id"] == ""
    assert context.json()["entities"] == []


def test_a_session_draws_what_it_proposes_over_the_empty_picture_and_writes_nothing(client: TestClient) -> None:
    root = client.root  # type: ignore[attr-defined]
    ref = _candidate(client)
    before = _files(root)
    proposed = "APP@1795000000.aBcDeFg.ledger"

    drawn = client.post(f"/api/candidates/{ref}/picture/preview", json={
        "diagram_type": "archimate-layered", "name": "Naive", "entity_ids": [], "connection_ids": [],
        "proposed_elements": [{"artifact_id": proposed, "name": "Ledger"}],
    })
    nothing = client.post(f"/api/candidates/{ref}/picture/preview", json={
        "diagram_type": "archimate-layered", "name": "Naive", "entity_ids": [], "connection_ids": [],
    })

    assert drawn.status_code == 200, drawn.text
    assert [stable_id(element["key"]) for element in drawn.json()["elements"]] == [stable_id(proposed)]
    assert nothing.status_code == 200 and nothing.json()["elements"] == []
    assert _files(root) == before


def test_a_candidate_reading_over_model_elements_opens_on_their_generated_view(client: TestClient) -> None:
    ref = _candidate(client, scope=[_SERVICE])

    picture = client.get(f"/api/candidates/{ref}/picture").json()
    context = client.get(f"/api/candidates/{ref}/picture/context").json()
    added = client.post(f"/api/candidates/{ref}/picture/preview", json={
        "diagram_type": "archimate-layered", "name": "Naive", "entity_ids": [_SERVICE], "connection_ids": [],
    })

    assert [stable_id(element["key"]) for element in picture["elements"]] == [stable_id(_SERVICE)]
    assert [stable_id(one) for one in context["diagram"]["entity_ids_used"]] == [stable_id(_SERVICE)]
    assert [stable_id(entity["artifact_id"]) for entity in context["entities"]] == [stable_id(_SERVICE)]
    assert added.status_code == 200, added.text


def test_a_candidate_drawn_on_a_stored_diagram_opens_on_it_as_the_diagram_editor_does(client: TestClient) -> None:
    ref = _candidate(client, diagram=_DIAGRAM)

    picture = client.get(f"/api/candidates/{ref}/picture").json()
    stored = client.get(f"/api/diagrams/{_DIAGRAM}/layout/geometry").json()
    context = client.get(f"/api/candidates/{ref}/picture/context").json()
    diagram_context = client.get(f"/api/diagrams/{_DIAGRAM}/context").json()

    assert picture["artifact_id"] == _DIAGRAM
    assert {e["key"] for e in picture["elements"]} == {e["key"] for e in stored["elements"]}
    assert context["diagram"]["artifact_id"] == _DIAGRAM
    assert context["entities"] == diagram_context["entities"]
    assert context["connections"] == diagram_context["connections"]


def test_resized_shapes_are_drawn_for_a_stored_candidate_and_refused_for_none(client: TestClient) -> None:
    ref = _candidate(client, diagram=_DIAGRAM)
    element = client.get(f"/api/candidates/{ref}/picture").json()["elements"][0]
    drawn_at = element["extent"]
    shape = {"drawing": element["drawing"], "box": False, "drawn": drawn_at,
             "to": {**drawn_at, "right": drawn_at["right"] + 60}}

    drawn = client.post(f"/api/candidates/{ref}/picture/shapes/preview", json={"shapes": [shape]})
    missing = client.post("/api/candidates/CAND@1.nope/picture/shapes/preview", json={"shapes": [shape]})

    assert drawn.status_code == 200, drawn.text
    assert len(drawn.json()["drawings"]) == 1
    assert missing.status_code == 404


def test_a_stored_diagram_that_cannot_be_read_is_refused_with_why(client: TestClient) -> None:
    """Regression: an unreadable diagram file was read as an empty body, and its context served as empty."""
    root = client.root  # type: ignore[attr-defined]
    ref = _candidate(client, diagram=_DIAGRAM)
    stored = next(root.rglob(f"{_DIAGRAM}.puml"))
    stored.chmod(0)
    try:
        context = client.get(f"/api/candidates/{ref}/picture/context")
    finally:
        stored.chmod(0o644)

    assert context.status_code == 404, context.text
    assert "cannot be read" in context.json()["detail"]["message"]
