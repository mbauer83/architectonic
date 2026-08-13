"""Tests for the GUI connections router.

Covers: GET /api/connections, /api/entities/{artifact_id}/neighbors, /api/search,
/api/ontology/classification, /api/ontology/pairs,
/api/write-help; POST /api/connections (dry_run), and the connection detail routes —
PATCH/DELETE by composite id, plus its associated-entities sub-resource.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.connections.router import _check_multiplicity
from src.infrastructure.rest.routers.connections.router import router as connections_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")


# ── shared helpers ────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
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

Test entity for connections router.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{slug}
```
"""


def _outgoing_md(source: str, *targets: str, conn_type: str = "archimate-association") -> str:
    sections = "\n".join(
        f"""\
### {conn_type} → {target}

```yaml
polarity: positive
weight: 2
```

Description.
"""
        for target in targets
    )
    return f"""\
---
source-entity: {source}
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §connections -->

{sections}"""


# ── fixtures ──────────────────────────────────────────────────────────────────

SRC_ID = "REQ@1000000010.SrcCon.source-conn"
TGT_ID = "REQ@1000000011.TgtCon.target-conn"
FAR_ID = "REQ@1000000012.FarCon.far-conn"


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    """A triangle: the source reaches two entities, and those two also reach each other.

    Three entities rather than two, because the edge between the two *neighbours* is the one the
    induced-subgraph read exists for — it is incident to neither endpoint a star query names, so a
    fixture without it cannot tell a complete answer from a path-dependent one.
    """
    root = tmp_path / "engagements" / "ENG-CONN" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "requirement"
    _write(model_dir / f"{SRC_ID}.md", _entity_md(SRC_ID, "Source Conn"))
    _write(model_dir / f"{TGT_ID}.md", _entity_md(TGT_ID, "Target Conn"))
    _write(model_dir / f"{FAR_ID}.md", _entity_md(FAR_ID, "Far Conn"))
    _write(model_dir / f"{SRC_ID}.outgoing.md", _outgoing_md(SRC_ID, TGT_ID, FAR_ID))
    _write(model_dir / f"{TGT_ID}.outgoing.md", _outgoing_md(TGT_ID, FAR_ID))
    return root


@pytest.fixture()
def client(populated_root: Path):
    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = build_api_app(connections_router)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            return c

    import asyncio
    return asyncio.run(_create_client(app))


async def _create_client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# Simpler synchronous approach using Starlette TestClient
@pytest.fixture()
def sync_client(populated_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = build_api_app(connections_router)
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    return TestClient(app)


# ── _check_multiplicity ────────────────────────────────────────────────────────


class TestCheckMultiplicity:
    def test_none_accepted(self) -> None:
        assert _check_multiplicity(None) is None

    def test_empty_string_accepted(self) -> None:
        assert _check_multiplicity("") == ""

    def test_digit_accepted(self) -> None:
        assert _check_multiplicity("1") == "1"

    def test_range_accepted(self) -> None:
        assert _check_multiplicity("1..5") == "1..5"

    def test_open_range_accepted(self) -> None:
        assert _check_multiplicity("0..*") == "0..*"

    def test_wildcard_accepted(self) -> None:
        assert _check_multiplicity("*") == "*"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid multiplicity"):
            _check_multiplicity("bad")


# ── GET endpoints ─────────────────────────────────────────────────────────────


class TestGetConnections:
    def test_returns_list(self, sync_client) -> None:
        """An object with ``items``, not a bare array: a top-level array leaves nowhere to add a
        total or a cursor without a second breaking change."""
        r = sync_client.get(f"/api/connections?entity_id={SRC_ID}")
        assert r.status_code == 200
        items = r.json()["items"]
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_outbound_direction(self, sync_client) -> None:
        r = sync_client.get(f"/api/connections?entity_id={SRC_ID}&direction=outbound")
        assert r.status_code == 200

    def test_inbound_direction(self, sync_client) -> None:
        r = sync_client.get(f"/api/connections?entity_id={TGT_ID}&direction=inbound")
        assert r.status_code == 200

    def test_with_conn_type_filter(self, sync_client) -> None:
        r = sync_client.get(f"/api/connections?entity_id={SRC_ID}&conn_type=archimate-association")
        assert r.status_code == 200

    def test_returns_typed_relationship_metadata(self, sync_client) -> None:
        response = sync_client.get(f"/api/connections?entity_id={SRC_ID}&direction=outbound")
        connection = response.json()["items"][0]
        assert connection["metadata"] == {"polarity": "positive", "weight": 2}

    def test_empty_entity(self, sync_client) -> None:
        r = sync_client.get("/api/connections?entity_id=REQ@9.ZZZ.no-such-entity")
        assert r.status_code == 200
        assert r.json()["items"] == []


class TestGetConnectionsAmong:
    """The induced subgraph over a set of entities: complete over what is drawn, and the same
    answer whichever node the caller arrived by."""

    def _ids(self, response) -> set[str]:
        return {item["artifact_id"] for item in response.json()["items"]}

    def _pairs(self, response) -> set[tuple[str, str]]:
        return {(item["source"], item["target"]) for item in response.json()["items"]}

    def test_it_returns_the_edge_between_two_neighbours_that_no_star_query_names(
        self, sync_client
    ) -> None:
        """The defect this read exists for: expanding the source draws all three nodes, and the
        edge between its two neighbours is incident to neither endpoint the star asked about."""
        star = self._pairs(sync_client.get(f"/api/connections?entity_id={SRC_ID}"))
        among = self._pairs(
            sync_client.get(f"/api/connections/among?entity_ids={SRC_ID},{TGT_ID},{FAR_ID}")
        )

        assert among - star == {(TGT_ID, FAR_ID)}

    def test_it_leaves_out_a_connection_with_an_endpoint_outside_the_set(self, sync_client) -> None:
        """A connection with one end outside the set has nothing to attach to."""
        among = self._pairs(sync_client.get(f"/api/connections/among?entity_ids={SRC_ID},{TGT_ID}"))

        assert among == {(SRC_ID, TGT_ID)}

    def test_the_answer_does_not_depend_on_the_order_the_set_is_named_in(self, sync_client) -> None:
        forwards = f"{SRC_ID},{TGT_ID},{FAR_ID}"
        backwards = f"{FAR_ID},{TGT_ID},{SRC_ID}"

        assert self._ids(sync_client.get(f"/api/connections/among?entity_ids={forwards}")) == self._ids(
            sync_client.get(f"/api/connections/among?entity_ids={backwards}")
        )

    def test_an_id_the_model_does_not_have_matches_nothing_rather_than_404s(
        self, sync_client
    ) -> None:
        """The caller names a set to look within, not a resource that must exist."""
        response = sync_client.get(f"/api/connections/among?entity_ids={SRC_ID},REQ@9.ZZZ.nothing")

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_an_empty_set_has_no_connections_among_it(self, sync_client) -> None:
        response = sync_client.get("/api/connections/among?entity_ids=")

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_each_row_carries_what_a_graph_draws_without_a_second_read(self, sync_client) -> None:
        """Type, endpoints and both endpoint names, so a canvas renders an edge from one answer."""
        row = next(
            item
            for item in sync_client.get(
                f"/api/connections/among?entity_ids={SRC_ID},{TGT_ID}"
            ).json()["items"]
        )

        assert row["conn_type"] == "archimate-association"
        assert (row["source"], row["target"]) == (SRC_ID, TGT_ID)
        assert (row["source_name"], row["target_name"]) == ("Source Conn", "Target Conn")


class TestGetNeighbors:
    def test_basic(self, sync_client) -> None:
        r = sync_client.get(f"/api/entities/{SRC_ID}/neighbors")
        assert r.status_code == 200
        data = r.json()
        # Tagged by traversal, so a client can tell a hop map from a witnessed relationship list.
        assert data["traversal"] == "direct"
        assert isinstance(data["hops"], dict)

    def test_max_hops_two(self, sync_client) -> None:
        r = sync_client.get(f"/api/entities/{SRC_ID}/neighbors?max_hops=2")
        assert r.status_code == 200


class TestSearch:
    def test_returns_hits(self, sync_client) -> None:
        r = sync_client.get("/api/search?q=Source")
        assert r.status_code == 200
        data = r.json()
        assert "hits" in data
        assert "query" in data

    def test_entity_hit_has_domain(self, sync_client) -> None:
        r = sync_client.get("/api/search?q=Source")
        assert r.status_code == 200
        hits = r.json()["hits"]
        entity_hits = [h for h in hits if h["record_type"] == "entity"]
        for h in entity_hits:
            assert "domain" in h

    def test_empty_query(self, sync_client) -> None:
        r = sync_client.get("/api/search?q=xyzzy_no_match_abc")
        assert r.status_code == 200
        assert "hits" in r.json()


class TestGetOntology:
    def test_source_type_only(self, sync_client) -> None:
        r = sync_client.get("/api/ontology/classification?source_type=requirement")
        assert r.status_code == 200
        data = r.json()
        assert "source_type" in data

    def test_source_and_target_type(self, sync_client) -> None:
        r = sync_client.get("/api/ontology/pairs?source_type=requirement&target_type=requirement")
        assert r.status_code == 200
        data = r.json()
        assert "connection_types" in data
        assert "symmetric" in data


class TestGetWriteHelp:
    def test_returns_dict(self, sync_client) -> None:
        r = sync_client.get("/api/write-help")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ── POST endpoints (dry_run) ──────────────────────────────────────────────────


def _connection_id(source: str, target: str, conn_type: str = "archimate-association") -> str:
    """The single-segment composite the read surface emits as a connection's ``artifact_id``."""
    return f"{source}---{target}@@{conn_type}"


class TestAddConnection:
    def test_dry_run_new_connection(self, sync_client) -> None:
        # Use reverse direction — no outgoing file for TGT_ID, so this is new.
        payload = {
            "source_entity": TGT_ID,
            "connection_type": "archimate-association",
            "target_entity": SRC_ID,
            "dry_run": True,
        }
        r = sync_client.post("/api/connections", json=payload)
        # A dry run created nothing, so it reports a plan with 200 rather than a 201.
        assert r.status_code == 200
        data = r.json()
        assert "wrote" in data

    def test_invalid_multiplicity_rejected(self, sync_client) -> None:
        payload = {
            "source_entity": TGT_ID,
            "connection_type": "archimate-association",
            "target_entity": SRC_ID,
            "src_multiplicity": "bad-value",
            "dry_run": True,
        }
        r = sync_client.post("/api/connections", json=payload)
        assert r.status_code == 422

    def test_specialization_field_accepted_and_passed_through(self, sync_client) -> None:
        # archimate-association carries no specialization catalog entries for the
        # requirement/requirement fixture pair — this proves the field round-trips through
        # the REST schema without erroring, not that any particular slug is legal here
        # (application-level specialization validity is covered by
        # tests/tools/test_specialization_persistence.py and
        # test_specialization_verifier_rules.py against real permitted-pair fixtures).
        payload = {
            "source_entity": TGT_ID,
            "connection_type": "archimate-association",
            "target_entity": SRC_ID,
            "specializations": [],
            "dry_run": True,
        }
        r = sync_client.post("/api/connections", json=payload)
        assert r.status_code == 200
        assert "wrote" in r.json()


class TestEditConnection:
    def test_dry_run(self, sync_client) -> None:
        r = sync_client.patch(
            f"/api/connections/{_connection_id(SRC_ID, TGT_ID)}",
            json={"description": "Updated description", "dry_run": True},
        )
        assert r.status_code == 200
        assert "wrote" in r.json()

    def test_specialization_field_accepted_and_passed_through(self, sync_client) -> None:
        r = sync_client.patch(
            f"/api/connections/{_connection_id(SRC_ID, TGT_ID)}",
            json={"specializations": [], "dry_run": True},
        )
        assert r.status_code == 200
        assert "wrote" in r.json()

    def test_typed_metadata_is_accepted_without_clearing_description(self, sync_client) -> None:
        response = sync_client.patch(
            f"/api/connections/{_connection_id(SRC_ID, TGT_ID)}",
            json={"metadata": {"weight": 3, "enabled": True}, "dry_run": True},
        )
        assert response.status_code == 200
        preview = response.json()["content"]
        assert "weight: 3" in preview
        assert "enabled: true" in preview
        assert "Description." in preview


class TestRemoveConnection:
    def test_dry_run(self, sync_client) -> None:
        r = sync_client.delete(
            f"/api/connections/{_connection_id(SRC_ID, TGT_ID)}?dry_run=true"
        )
        # A dry run has a plan to report, so it answers 200; a committed removal answers 204.
        assert r.status_code == 200
        assert "wrote" in r.json()


class TestAssociateConnection:
    def test_dry_run_add(self, sync_client) -> None:
        r = sync_client.patch(
            f"/api/connections/{_connection_id(SRC_ID, TGT_ID)}/associated-entities",
            json={"add_entities": [TGT_ID], "dry_run": True},
        )
        assert r.status_code == 200
        assert "wrote" in r.json()
