"""A read that shows scratchpad-derived content is revalidated by something a scratchpad save moves.

A conditional read answers `304` whenever the client's `If-None-Match` equals a tag derived from the
read model's version and the URL. That version was the model's generation alone, and a scratchpad
save deliberately does not move it: a scratchpad is not model content, and a canvas that saves about
once a second would otherwise invalidate every model read in the product.

Two kinds of read show scratchpad-derived content all the same. An entity's page lists the
scratchpads whose notes reference the entity, and a search returns scratchpads and their notes. Both
were told `304` over a body that had changed — a page that went on linking a deleted pad, a search
that did not find the note just written.

Each now carries a validator of its own (`ReadDependence`), and the property has two sides, both
asserted here: it moves when the body would read differently, and — for the entity page — it does
*not* move when someone is merely typing into a canvas.

Through the ASGI stack with the real scratchpad write path, because the property only exists where
the middleware, the route and the index's change broadcast meet.
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
from src.infrastructure.rest.routers.connections.router import router as connections_router
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
    with TestClient(build_api_app(entities_router, connections_router, scratchpad_router.router)) as test_client:
        test_client.repo_root = root  # type: ignore[attr-defined]
        yield test_client


_BOUND_NOTE = {
    "id": "bound",
    "title": "Already in the model",
    "destination": "element",
    "element-type": "requirement",
    "model-ref": {"artifact-id": ENTITY_ID, "kind": "bound"},
}


def _create_a_pad(client: TestClient, name: str = "Q3 thinking") -> dict:
    created = client.post("/api/scratchpads", json={"name": name, "group": "p"})
    assert created.status_code == 201, created.text
    return created.json()


def _save(client: TestClient, pad: dict, *, notes: list[dict], name: str | None = None) -> dict:
    """Replace the pad's notes (and optionally its name) through the scratchpad route."""
    document = {key: value for key, value in pad.items() if key != "group"}
    document["notes"] = notes
    document["name"] = name or pad["name"]
    document.setdefault("layout", {})["notes"] = {note["id"]: [40, 60 + 80 * i] for i, note in enumerate(notes)}
    saved = client.put(
        f"/api/scratchpads/{pad['artifact-id']}",
        json={"version": pad["version"], "group": pad["group"], "scratchpad": document},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _bind_a_note(client: TestClient) -> dict:
    return _save(client, _create_a_pad(client), notes=[_BOUND_NOTE])


def _a_thought(text: str) -> dict:
    return {"id": "thought", "title": text}


def _pads(body: dict) -> list[str]:
    entity = body.get("entity", body)
    return [row["name"] for row in entity["referenced_in_scratchpads"]]


def _revalidate(client: TestClient, url: str, held) -> object:  # type: ignore[no-untyped-def]
    return client.get(url, headers={"If-None-Match": held.headers["etag"]})


class TestAnEntityPageFollowsTheScratchpadsThatReferenceIt:
    @pytest.mark.parametrize("url", REFERENCE_READS)
    def test_binding_a_note_sends_the_new_list(self, client: TestClient, url: str) -> None:
        held = client.get(url)
        assert held.status_code == 200 and _pads(held.json()) == []

        _bind_a_note(client)
        revalidated = _revalidate(client, url, held)

        assert revalidated.status_code == 200, "a 304 here tells the client its empty list is current"
        assert _pads(revalidated.json()) == ["Q3 thinking"]

    @pytest.mark.parametrize("url", REFERENCE_READS)
    def test_deleting_the_scratchpad_stops_it_being_shown(self, client: TestClient, url: str) -> None:
        pad = _bind_a_note(client)
        held = client.get(url)
        assert _pads(held.json()) == ["Q3 thinking"]

        deleted = client.delete(f"/api/scratchpads/{pad['artifact-id']}", params={"dry_run": "false"})
        assert deleted.status_code == 204, deleted.text
        revalidated = _revalidate(client, url, held)

        assert revalidated.status_code == 200, "a 304 here keeps a link to a scratchpad that is gone"
        assert _pads(revalidated.json()) == []

    def test_releasing_the_binding_stops_it_being_shown(self, client: TestClient) -> None:
        pad = _bind_a_note(client)
        held = client.get(ENTITY_URL)

        _save(client, pad, notes=[])
        revalidated = _revalidate(client, ENTITY_URL, held)

        assert revalidated.status_code == 200 and _pads(revalidated.json()) == []

    def test_renaming_the_scratchpad_renames_its_row(self, client: TestClient) -> None:
        """The row shows the pad's name, so the name is part of what the list says."""
        pad = _bind_a_note(client)
        held = client.get(ENTITY_URL)

        _save(client, pad, notes=[_BOUND_NOTE], name="Q4 thinking")
        revalidated = _revalidate(client, ENTITY_URL, held)

        assert revalidated.status_code == 200 and _pads(revalidated.json()) == ["Q4 thinking"]


class TestTypingIntoACanvasDoesNotDisturbTheModelsReads:
    """The reason the model generation is not simply bumped: a canvas saves constantly."""

    def test_a_save_that_changes_no_reference_leaves_the_entity_page_valid(self, client: TestClient) -> None:
        pad = _bind_a_note(client)
        held = client.get(ENTITY_URL)

        pad = _save(client, pad, notes=[_BOUND_NOTE, _a_thought("First draft of a thought")])
        pad = _save(client, pad, notes=[_BOUND_NOTE, _a_thought("Second draft of the same thought")])

        assert _revalidate(client, ENTITY_URL, held).status_code == 304

    def test_a_pad_that_references_nothing_never_touches_it(self, client: TestClient) -> None:
        held = client.get(ENTITY_URL)

        pad = _create_a_pad(client, "Unrelated thinking")
        _save(client, pad, notes=[_a_thought("Nothing to do with the model")], name="Renamed thinking")

        assert _revalidate(client, ENTITY_URL, held).status_code == 304

    def test_no_scratchpad_change_at_all_moves_a_read_of_the_model_alone(self, client: TestClient) -> None:
        """Binding, the one change that moves the entity page, still leaves the entity *list* valid:
        the list shows no references, so it is validated by the model's generation and nothing else."""
        held = client.get(ENTITY_LIST_URL)
        assert held.status_code == 200

        _bind_a_note(client)

        assert _revalidate(client, ENTITY_LIST_URL, held).status_code == 304


class TestASearchFollowsTheScratchpadsItReturns:
    def test_a_note_just_written_is_found_on_revalidation(self, client: TestClient) -> None:
        url = "/api/search?q=quokka"
        held = client.get(url)
        assert held.status_code == 200 and held.json()["hits"] == []

        _save(client, _create_a_pad(client), notes=[_a_thought("Quokka habitat mapping")])
        revalidated = _revalidate(client, url, held)

        assert revalidated.status_code == 200, "a 304 here hides the note that was just saved"
        assert [hit["record_type"] for hit in revalidated.json()["hits"]] == ["scratchpad-note"]


class TestTheModelStillMovesEverything:
    @pytest.mark.parametrize("url", [*REFERENCE_READS, ENTITY_LIST_URL, "/api/search?q=bound"])
    def test_a_diagram_drawing_the_entity_moves_every_validator(self, client: TestClient, url: str) -> None:
        """The control across kinds, and the guarantee the two new validators inherit: each moves
        whenever the model's does, so neither can be staler than the one it replaced."""
        held = client.get(url)
        assert held.status_code == 200

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

        assert _revalidate(client, url, held).status_code == 200

    def test_the_entity_page_then_lists_the_diagram(self, client: TestClient) -> None:
        assert client.get(ENTITY_URL).json()["referenced_in_diagrams"] == []


class TestTheMemoisedToolsAreStampedTheSameWay:
    """MCP has no conditional GET, so the same judgement is a stamp on a memoised result. The two
    transports classify a read once, so the stamp has to move exactly when the ETag does."""

    def _stamp(self, client: TestClient, tool: str) -> str:
        from src.application.read_model_purity import dependence_of_mcp_tool

        index = shared_artifact_index([client.repo_root])  # type: ignore[attr-defined]
        return index.read_model_version().validator(dependence_of_mcp_tool(tool))

    def test_reading_an_artifact_is_restamped_when_a_scratchpad_binds_it(self, client: TestClient) -> None:
        before = self._stamp(client, "artifact_query_read_artifact")

        pad = _bind_a_note(client)

        bound = self._stamp(client, "artifact_query_read_artifact")
        assert bound != before
        _save(client, pad, notes=[_BOUND_NOTE, _a_thought("Typing does not restamp it")])
        assert self._stamp(client, "artifact_query_read_artifact") == bound

    def test_a_search_is_restamped_by_any_scratchpad_save(self, client: TestClient) -> None:
        pad = _create_a_pad(client)
        before = self._stamp(client, "artifact_query_search_artifacts")

        _save(client, pad, notes=[_a_thought("Quokka habitat mapping")])

        assert self._stamp(client, "artifact_query_search_artifacts") != before

    def test_a_read_of_the_model_alone_is_never_restamped_by_a_scratchpad(self, client: TestClient) -> None:
        before = self._stamp(client, "artifact_query_list_artifacts")

        _bind_a_note(client)

        assert self._stamp(client, "artifact_query_list_artifacts") == before
