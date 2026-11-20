"""An entity's page follows the scratchpads that reference it, even for a client that revalidates.

A conditional read answers `304` whenever the client's `If-None-Match` equals a tag derived from the
model's generation and the URL. A scratchpad save deliberately does not move that generation: a
scratchpad is not model content, and a canvas that saves about once a second would otherwise
invalidate every model read in the product.

The entity read and the entity context read both list where the entity is referenced, the
scratchpads among the places. So both were told `304` over a body that had changed — a page that
went on linking a deleted scratchpad, and did not show the one that had just bound the entity.

Neither is a conditional read any more: with no validator that describes their bodies, they are
answered in full every time. Asserted as the behaviour a client sees rather than as the absence of
a header, so that a validator which *does* describe those bodies can replace this without the tests
changing — and the last test is the other half of that bargain: reads of the model alone keep theirs.

Through the ASGI stack with the real scratchpad write path, because the property only exists where
the middleware, the route and the index's change broadcast meet.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.rest.routers import scratchpads as scratchpad_router
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

ENTITY_ID = "REQ@1000000901.ScrRef.bound-by-a-scratchpad"
ENTITY_URL = f"/api/entities/{ENTITY_ID}"
CONTEXT_URL = f"{ENTITY_URL}/context"
ENTITY_LIST_URL = "/api/entities"
DIAGRAM_ID = "DIA@1000000902.ScrRef.draws-the-entity"

#: The two reads whose bodies list where the entity is referenced.
REFERENCE_READS = [ENTITY_URL, CONTEXT_URL]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    root = tmp_path / "engagements" / "ENG-SCRREF" / "architecture-repository"
    _write(
        root / "projects" / "p" / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md",
        f"""---
artifact-id: {ENTITY_ID}
artifact-type: requirement
name: "Bound By A Scratchpad"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Bound By A Scratchpad

A requirement a scratchpad note is about to be bound to.
""",
    )
    gui_state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    # The write queue and gate are not what this is about; the operation, the repository it writes
    # through and the index broadcast it makes are the product's own.
    monkeypatch.setattr(
        gui_state, "authorized_write", lambda _operation_id, fn, *args, **kwargs: fn(*args, **kwargs)
    )
    with TestClient(build_api_app(entities_router, scratchpad_router.router)) as test_client:
        test_client.repo_root = root  # type: ignore[attr-defined]
        yield test_client


_BOUND_NOTE = {
    "id": "bound",
    "title": "Already in the model",
    "destination": "element",
    "element-type": "requirement",
    "model-ref": {"artifact-id": ENTITY_ID, "kind": "bound"},
}


def _save(client: TestClient, pad: dict, *, notes: list[dict], name: str | None = None) -> dict:
    """Replace the pad's notes (and optionally its name) through the scratchpad route."""
    document = {key: value for key, value in pad.items() if key != "group"}
    document["notes"] = notes
    document["name"] = name or pad["name"]
    document.setdefault("layout", {})["notes"] = {note["id"]: [40, 60] for note in notes}
    saved = client.put(
        f"/api/scratchpads/{pad['artifact-id']}",
        json={"version": pad["version"], "group": pad["group"], "scratchpad": document},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _bind_a_note(client: TestClient) -> dict:
    created = client.post("/api/scratchpads", json={"name": "Q3 thinking", "group": "p"})
    assert created.status_code == 201, created.text
    return _save(client, created.json(), notes=[_BOUND_NOTE])


def _pads(body: dict) -> list[str]:
    entity = body.get("entity", body)
    return [row["name"] for row in entity["referenced_in_scratchpads"]]


def _revalidate(client: TestClient, url: str, held: Response) -> Response:
    """Ask again as a browser does: with whatever validator the first answer carried, if any."""
    tag = held.headers.get("etag")
    return client.get(url, headers={"If-None-Match": tag} if tag else {})


@pytest.mark.parametrize("url", REFERENCE_READS)
def test_binding_a_note_sends_the_new_list(client: TestClient, url: str) -> None:
    held = client.get(url)
    assert held.status_code == 200 and _pads(held.json()) == []

    _bind_a_note(client)
    revalidated = _revalidate(client, url, held)

    assert revalidated.status_code == 200, "a 304 here tells the client its empty list is current"
    assert _pads(revalidated.json()) == ["Q3 thinking"]


@pytest.mark.parametrize("url", REFERENCE_READS)
def test_deleting_the_scratchpad_stops_it_being_shown(client: TestClient, url: str) -> None:
    pad = _bind_a_note(client)
    held = client.get(url)
    assert _pads(held.json()) == ["Q3 thinking"]

    deleted = client.delete(f"/api/scratchpads/{pad['artifact-id']}", params={"dry_run": "false"})
    assert deleted.status_code == 204, deleted.text
    revalidated = _revalidate(client, url, held)

    assert revalidated.status_code == 200, "a 304 here keeps a link to a scratchpad that is gone"
    assert _pads(revalidated.json()) == []


@pytest.mark.parametrize("url", REFERENCE_READS)
def test_renaming_the_scratchpad_renames_its_row(client: TestClient, url: str) -> None:
    """The row shows the pad's name, so the name is part of what the list says."""
    pad = _bind_a_note(client)
    held = client.get(url)

    _save(client, pad, notes=[_BOUND_NOTE], name="Q4 thinking")
    revalidated = _revalidate(client, url, held)

    assert revalidated.status_code == 200 and _pads(revalidated.json()) == ["Q4 thinking"]


def test_a_diagram_drawing_the_entity_is_listed_too(client: TestClient) -> None:
    """The list beside it, which the model generation did describe, is served as fresh as before."""
    held = client.get(ENTITY_URL)
    assert held.json()["referenced_in_diagrams"] == []

    diagram = client.repo_root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml"  # type: ignore[attr-defined]
    _write(
        diagram,
        "---\n"
        f"artifact-id: {DIAGRAM_ID}\n"
        "artifact-type: diagram\n"
        "diagram-type: c4-container\n"
        "name: Draws The Entity\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "entity-ids-used:\n"
        f"  - {ENTITY_ID}\n"
        "---\n"
        "@startuml\n@enduml\n",
    )
    notify_paths_changed([diagram])
    revalidated = _revalidate(client, ENTITY_URL, held)

    assert revalidated.status_code == 200
    assert [row["name"] for row in revalidated.json()["referenced_in_diagrams"]] == ["Draws The Entity"]


def test_a_read_of_the_model_alone_is_still_told_it_is_current(client: TestClient) -> None:
    """What the scratchpad save must *not* cost: the entity list shows no references, so it keeps
    its validator, and a scratchpad binding an entity leaves a client holding the list told so."""
    held = client.get(ENTITY_LIST_URL)
    assert held.status_code == 200 and held.headers.get("etag")

    _bind_a_note(client)

    assert _revalidate(client, ENTITY_LIST_URL, held).status_code == 304
