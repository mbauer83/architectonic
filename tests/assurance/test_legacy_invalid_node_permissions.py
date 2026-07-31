"""A node awaiting provenance repair is repair-only — the plan's mandatory acceptance tests.

There were 26 nodes in the live store with no recorded author, and they are kept: deleting evidence
of past work to satisfy a new rule would be worse than the gap. But if such a node stayed fully
writable, new work would keep accumulating against a record that cannot say who produced it, and the
backlog would never shrink because nothing stopped it growing.

So each of the four mutations is shown twice: refused while the node is unattributed, and accepted
once its provenance is assigned. Both halves matter — a guard that refused everything forever would
pass the first half and make the repair path useless.

Exercised over HTTP rather than against the use cases, because the refusal a client acts on is the
one the delivery layer produces, and the code and the permitted operation have to reach them.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_WRITE_CTX = "src.infrastructure.gui.routers._assurance_write.get_assurance_context"
_GROUPING_CTX = "src.infrastructure.gui.routers._assurance_http.get_assurance_context"
_FMEA_CTX = "src.infrastructure.gui.routers._assurance_fmea_routes.get_assurance_context"
_READ_CTX = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"

_LEGACY = "node_legacy_invalid"


class _Context:
    """The assurance context, with the archive the audited paths append to."""

    def __init__(self, store: Any, archive: Any) -> None:
        self.store = store
        self.archive = archive
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        return bool(self.store.is_unlocked())


class _Archive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, op: str, **_kwargs: object) -> None:
        self.ops.append(op)


@pytest.fixture()
def store(tmp_path: Any) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "legacy-invalid.db"
    init_store(db_path)
    unlocked = SQLCipherAssuranceStore(db_path)
    unlocked.unlock()
    yield unlocked
    unlocked.lock()


@pytest.fixture()
def client(store: Any, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    ctx = _Context(store, _Archive())
    for path in (_WRITE_CTX, _GROUPING_CTX, _FMEA_CTX, _READ_CTX):
        monkeypatch.setattr(path, lambda: ctx)
    return TestClient(build_api_app(router), raise_server_exceptions=False)


@pytest.fixture()
def fixture_ids(store: Any) -> dict[str, str]:
    """A legacy-invalid node, an analysis to repair it into, and neighbours to relate it to.

    The unattributed node is written straight to the store, which is the only way to produce one now
    — every write path refuses to create one, which is the point.
    """
    analysis_id = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
    other_analysis_id = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
    orphan = str(store.create_node("hazard", "Unattributed hazard"))
    attributed = str(store.create_node("loss", "Loss", analysis_id=analysis_id))
    failure_mode = str(store.create_node("failure-mode", "Orphan failure mode"))
    return {
        "analysis": analysis_id,
        "other_analysis": other_analysis_id,
        "orphan": orphan,
        "attributed": attributed,
        "failure_mode": failure_mode,
    }


def _assign(client: TestClient, node_id: str, analysis_id: str) -> None:
    response = client.put(
        f"/api/assurance/nodes/{node_id}/provenance", json={"analysis_id": analysis_id}
    )
    assert response.status_code == 204, response.text


def _refusal(response: Any) -> dict[str, Any]:
    """The refusal, asserted as a client sees it: a 409 naming the permitted operation."""
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == _LEGACY
    assert detail["details"]["permitted_operation"] == "assign_provenance"
    return detail


class TestAnOrdinaryEdit:
    def test_is_refused_while_the_node_is_unattributed(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        response = client.patch(
            f"/api/assurance/nodes/{fixture_ids['orphan']}", json={"name": "Renamed"}
        )

        _refusal(response)
        assert store.get_node(fixture_ids["orphan"])["name"] == "Unattributed hazard"

    def test_succeeds_once_provenance_is_assigned(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        _assign(client, fixture_ids["orphan"], fixture_ids["analysis"])

        response = client.patch(
            f"/api/assurance/nodes/{fixture_ids['orphan']}", json={"name": "Renamed"}
        )

        assert response.status_code == 200, response.text
        assert store.get_node(fixture_ids["orphan"])["name"] == "Renamed"


class TestParticipation:
    def test_is_refused_while_the_node_is_unattributed(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        response = client.put(
            f"/api/assurance/analyses/{fixture_ids['other_analysis']}"
            f"/participating-nodes/{fixture_ids['orphan']}"
        )

        _refusal(response)
        assert store.list_analysis_members(fixture_ids["other_analysis"]) == []

    def test_succeeds_once_provenance_is_assigned(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        _assign(client, fixture_ids["orphan"], fixture_ids["analysis"])

        response = client.put(
            f"/api/assurance/analyses/{fixture_ids['other_analysis']}"
            f"/participating-nodes/{fixture_ids['orphan']}"
        )

        assert response.status_code == 204, response.text
        assert fixture_ids["orphan"] in store.list_analysis_members(fixture_ids["other_analysis"])


class TestEdgeCreation:
    def _body(self, ids: dict[str, str]) -> dict[str, str]:
        return {
            "source_id": ids["orphan"], "target_id": ids["attributed"], "conn_type": "leads-to",
        }

    def test_is_refused_while_an_endpoint_is_unattributed(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        response = client.post("/api/assurance/edges", json=self._body(fixture_ids))

        _refusal(response)
        assert store.list_edges(source_id=fixture_ids["orphan"]) == []

    def test_succeeds_once_provenance_is_assigned(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        _assign(client, fixture_ids["orphan"], fixture_ids["analysis"])

        response = client.post("/api/assurance/edges", json=self._body(fixture_ids))

        assert response.status_code == 200, response.text
        assert store.list_edges(source_id=fixture_ids["orphan"]) != []


class TestFactorAssessment:
    def _body(self) -> dict[str, str]:
        return {
            "factor": "occurrence",
            "value": "possible",
            "justification": "judged against the facts",
            "author": "analyst",
            "basis_digest": "basis-1",
        }

    def test_is_refused_while_the_failure_mode_is_unattributed(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        response = client.post(
            f"/api/assurance/nodes/{fixture_ids['failure_mode']}/factor-assessments",
            json=self._body(),
        )

        _refusal(response)
        assert store.read_fmea_assessments([fixture_ids["failure_mode"]]) == {}

    def test_succeeds_once_provenance_is_assigned(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        _assign(client, fixture_ids["failure_mode"], fixture_ids["analysis"])

        response = client.post(
            f"/api/assurance/nodes/{fixture_ids['failure_mode']}/factor-assessments",
            json=self._body(),
        )

        assert response.status_code == 200, response.text
        assert store.read_fmea_assessments([fixture_ids["failure_mode"]]) != {}


class TestTheNodeStaysReadable:
    def test_an_unattributed_node_is_readable_with_its_relations_intact(
        self, client: TestClient, fixture_ids: dict[str, str], store: Any,
    ) -> None:
        """Repair-only is not invisible. The node has to be findable to be repaired, and pre-existing
        relations are evidence of past work rather than something the new rule may discard."""
        store.add_analysis_member(fixture_ids["other_analysis"], fixture_ids["orphan"])

        response = client.get(f"/api/assurance/nodes/{fixture_ids['orphan']}")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["node"]["node_id"] == fixture_ids["orphan"]
        assert body["authored_by"] is None
        assert [a["analysis_id"] for a in body["participates_in"]] == [
            fixture_ids["other_analysis"]
        ]
