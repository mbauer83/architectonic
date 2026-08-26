"""A search asked for `limit` rows returns `limit` rows, and none of them is invisible.

Global search decided visibility twice, on two different keys, and the second decider ran *after* the
window had been allocated:

* the use case excluded entity types by **declared diagram-only type name**, which is what
  `hidden_diagram_entity_types` answers from the module catalogue;
* the route then dropped every hit whose record carried a **`host_diagram_id`**, whatever its type.

Those are not the same set. `gsn`, `bowtie` and `control_structure` declare no `diagram_only_types` at
all, so their nodes were invisible to the first key and caught by the second — after they had already
consumed slots in the ranked window. Measured on the real repository before this test existed:
`GET /api/search?q=assurance&limit=20` returned **16** hits, and the four it lost were the four
highest-scoring entity hits in the window. `limit=50` returned 43.

The route's own comment asserted the opposite — that the late filter "drops nothing to speak of,
because the same exclusion is already applied upstream". It dropped a fifth of the window.

**These are HTTP-level tests on purpose.** A short window is a property of how the route *composes*
the use case with its filter, so a unit test of `search_artifacts` cannot see it: at that layer the
window is full and simply contains rows the reader will never receive. Written against a fixture store
that owns its content, because a count taken from the real repository is not this test's to assert.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts._search import search_artifacts
from src.domain.ontology_representation.artifact_types import EntityRecord, SearchResult
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.connections.read_routes import register_connection_read_routes
from tests.support.api_app import build_api_app

#: The container key a diagram-owned node actually carries. `gsn`, `bowtie` and `control_structure`
#: all use it, which is why a type-name key could never tell one family's nodes from another's:
#: opting one family in would opt in all of them.
_DIAGRAM_NODE_TYPE = "nodes"


def _entity(n: int, *, artifact_type: str = "application-component", host: str | None = None) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}",
        artifact_type=artifact_type,
        name=f"assurance component {n}",
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra={},
        content_text="assurance",
        display_blocks={},
        display_label=f"assurance component {n}",
        display_alias=f"APP{n}",
        host_diagram_id=host,
    )


def _diagram_owned(n: int) -> EntityRecord:
    """A diagram-owned node of a type whose module declares no `diagram_only_types`.

    This is the shape `hidden_diagram_entity_types` cannot name and the late filter used to catch —
    the record class the measured four hits belonged to.
    """
    return _entity(n, artifact_type=_DIAGRAM_NODE_TYPE, host=f"GSN@{n}")


class _Store:
    """The slice of `ReadableArtifactStore` the scored search path uses, over a fixture population.

    FTS is off, so every kind falls through to the scored supplement — the branch a fixture can drive
    without a database. The *use case* is the real one: this stands in for the store, not for the
    policy, so the predicate under test actually runs.
    """

    def __init__(self, entities: list[EntityRecord]) -> None:
        self._entities = {rec.artifact_id: rec for rec in entities}

    def search_fts(self, query, **kwargs):  # noqa: ANN001, ANN003, ARG002
        return []

    def list_entities(self) -> list[EntityRecord]:
        return list(self._entities.values())

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def entity_ids(self) -> list[str]:
        return list(self._entities)

    def list_connections(self):
        return []

    def list_diagrams(self):
        return []

    def list_documents(self):
        return []

    def list_scratchpad_notes(self):
        return []


    def list_scratchpads_indexed(self, **kwargs):  # noqa: ANN003, ARG002
        return []

    def get_scratchpad(self, artifact_id: str):  # noqa: ANN001, ARG002
        return None
    def get_connection(self, artifact_id: str):
        return None

    def get_diagram(self, artifact_id: str):
        return None

    def get_document(self, artifact_id: str):
        return None

    def get_scratchpad_note(self, artifact_id: str):
        return None


class _Repo:
    """The facade the route calls, delegating to the real search use case over a fixture store."""

    def __init__(self, entities: list[EntityRecord]) -> None:
        self._store = _Store(entities)

    def search_artifacts(self, query: str, **kwargs: object) -> SearchResult:
        return search_artifacts(self._store, None, query, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from fastapi import APIRouter

    router = APIRouter()
    register_connection_read_routes(router)

    def _install(entities: list[EntityRecord]) -> None:
        monkeypatch.setattr(s, "get_repo", lambda: _Repo(entities))

    with TestClient(build_api_app(router)) as test_client:
        test_client.install = _install  # type: ignore[attr-defined]
        yield test_client


def _search(client: TestClient, entities: list[EntityRecord], limit: int) -> list[dict]:
    client.install(entities)  # type: ignore[attr-defined]
    response = client.get("/api/search", params={"q": "assurance", "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()["hits"]


class TestTheWindowIsFull:
    def test_a_window_is_filled_when_enough_visible_hits_exist(self, client: TestClient) -> None:
        hits = _search(client, [_entity(n) for n in range(40)], 20)

        assert len(hits) == 20

    def test_invisible_hits_do_not_consume_the_window(self, client: TestClient) -> None:
        """The measured defect: invisible rows ranked, then dropped, leaving a short answer.

        Four diagram-owned records score above twenty visible ones. Before the fix the answer was
        sixteen rows; the four slots were spent on records the reader never receives.
        """
        population = [_diagram_owned(n) for n in range(100, 104)] + [_entity(n) for n in range(20)]

        hits = _search(client, population, 20)

        assert len(hits) == 20


class TestNothingInvisibleIsReturned:
    def test_a_diagram_owned_entity_of_an_undeclared_type_is_absent(self, client: TestClient) -> None:
        population = [_diagram_owned(n) for n in range(100, 104)] + [_entity(n) for n in range(5)]

        hits = _search(client, population, 20)

        assert [h["artifact_id"] for h in hits if h.get("host_diagram_id")] == []

    def test_a_model_entity_is_never_hidden_by_the_same_rule(self, client: TestClient) -> None:
        """The guard on the guard: the rule keys on being diagram-owned, not on the type name.

        Without this, a rule that hid `artifact_type == "nodes"` outright would satisfy every test
        above and quietly hide a model entity that happened to carry that type.
        """
        hits = _search(client, [_entity(1, artifact_type=_DIAGRAM_NODE_TYPE, host=None)], 20)

        assert [h["artifact_id"] for h in hits] == ["APP@1"]


@pytest.mark.parametrize("limit", [1, 3, 10, 20, 50])
def test_the_window_is_full_at_every_size_the_corpus_can_fill(client: TestClient, limit: int) -> None:
    population = [_diagram_owned(n) for n in range(100, 110)] + [_entity(n) for n in range(60)]

    hits = _search(client, population, limit)

    assert len(hits) == limit
