"""An entity read embeds the scratchpads that reference it, so its validator must move when they do.

`GET /api/entities/{id}` is cache-eligible: the conditional-read middleware answers `304` whenever the
client's `If-None-Match` equals a tag derived from the read model's generation and the URL. The body it
stands for carries three "referenced in" lists — documents, diagrams and scratchpads. A document or a
diagram write bumps the generation; a scratchpad write deliberately does not
(`ArtifactIndex.apply_file_changes`: "a change no model reader can observe"). The third list is the
model reader that observes it.

Through the ASGI stack with the real scratchpad write path, because the property only exists where the
middleware, the route and the index's change broadcast meet.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.rest.routers import scratchpads as scratchpad_router
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

ENTITY_ID = "REQ@1000000901.ScrRef.bound-by-a-scratchpad"
ENTITY_URL = f"/api/entities/{ENTITY_ID}"
DIAGRAM_ID = "DIA@1000000902.ScrRef.draws-the-entity"


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


def _bind_a_note(client: TestClient) -> dict:
    """Create a pad and save one note bound to the entity, through the scratchpad routes."""
    created = client.post("/api/scratchpads", json={"name": "Q3 thinking", "group": "p"})
    assert created.status_code == 201, created.text
    pad = created.json()
    document = {key: value for key, value in pad.items() if key != "group"}
    document["notes"] = [{
        "id": "n1",
        "title": "Already in the model",
        "destination": "element",
        "element-type": "requirement",
        "model-ref": {"artifact-id": ENTITY_ID, "kind": "bound"},
    }]
    document.setdefault("layout", {})["notes"] = {"n1": [40, 60]}
    saved = client.put(
        f"/api/scratchpads/{pad['artifact-id']}",
        json={"version": pad["version"], "group": pad["group"], "scratchpad": document},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _pads(body: dict) -> list[str]:
    return [row["name"] for row in body["referenced_in_scratchpads"]]


def test_the_index_itself_answers_with_the_new_scratchpad(client: TestClient) -> None:
    """The control for the test below: nothing is stale *behind* the validator.

    An unconditional read derives the body afresh, and it names the pad. So what the conditional read
    gets wrong is the validator alone — the reverse index is current the moment the save returns."""
    assert _pads(client.get(ENTITY_URL).json()) == []

    _bind_a_note(client)

    assert _pads(client.get(ENTITY_URL).json()) == ["Q3 thinking"]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "the entity read's ETag is the model generation, which a scratchpad save does not move "
        "(ArtifactIndex.apply_file_changes), although the body embeds referenced_in_scratchpads: "
        "a revalidating client is answered 304 and keeps a list the server no longer serves"
    ),
)
def test_a_client_revalidating_after_a_scratchpad_bound_the_entity_is_sent_the_new_list(
    client: TestClient,
) -> None:
    first = client.get(ENTITY_URL)
    assert first.status_code == 200 and _pads(first.json()) == []

    _bind_a_note(client)

    revalidated = client.get(ENTITY_URL, headers={"If-None-Match": first.headers["etag"]})

    assert revalidated.status_code == 200, "a 304 here tells the client its empty list is current"
    assert _pads(revalidated.json()) == ["Q3 thinking"]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "the same validator in the other direction: deleting the scratchpad that references the "
        "entity leaves the ETag where it was, so the page keeps offering a link to a deleted pad"
    ),
)
def test_a_client_revalidating_after_the_scratchpad_was_deleted_stops_being_shown_it(
    client: TestClient,
) -> None:
    pad = _bind_a_note(client)
    held = client.get(ENTITY_URL)
    assert _pads(held.json()) == ["Q3 thinking"]

    deleted = client.delete(f"/api/scratchpads/{pad['artifact-id']}", params={"dry_run": "false"})
    assert deleted.status_code == 204, deleted.text

    revalidated = client.get(ENTITY_URL, headers={"If-None-Match": held.headers["etag"]})

    assert revalidated.status_code == 200, "a 304 here keeps a link to a scratchpad that is gone"
    assert _pads(revalidated.json()) == []


def test_a_diagram_drawing_the_entity_does_move_the_validator(client: TestClient) -> None:
    """The control across kinds: the diagram list beside it is served fresh on revalidation.

    Same read, same middleware, same broadcast (`notify_paths_changed`, which every write path ends
    in) — so the difference between this passing and the two above failing is the one branch that
    exempts a scratchpad from bumping the generation."""
    first = client.get(ENTITY_URL)
    assert first.json()["referenced_in_diagrams"] == []

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

    revalidated = client.get(ENTITY_URL, headers={"If-None-Match": first.headers["etag"]})

    assert revalidated.status_code == 200
    assert [row["name"] for row in revalidated.json()["referenced_in_diagrams"]] == ["Draws The Entity"]
