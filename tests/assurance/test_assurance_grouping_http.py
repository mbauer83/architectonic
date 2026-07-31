"""HTTP contract for filing analyses and recording participation, over a real store.

A real SQLCipher store rather than a fake, because what the routes have to get right is exposure,
and exposure is a property of the data: a fake that returns whatever the test seeded cannot show
that an above-ceiling analysis is unreachable, only that the code calls the filter.

The exposure claims asserted here:

* an above-ceiling analysis is 404 on every one of these routes, read and write alike — filing
  something a reader cannot see would confirm it exists;
* a member list omits nodes above the ceiling, and a node's `participates_in` omits analyses
  above it, so neither becomes a side channel around a direct read's 404;
* an above-ceiling node cannot be drawn into a visible analysis.

And the behaviours that make the model usable: filing is reversible, deleting a group unfiles
rather than deletes, and a borrowed node reports its author and its borrowers separately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_HTTP_CTX = "src.infrastructure.gui.routers._assurance_http.get_assurance_context"
_READ_CTX = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"


class _RecordingArchive:
    """Records the operations a write emitted. The audit chain itself is tested elsewhere; what
    matters here is that a filing decision is audited at all."""

    def __init__(self) -> None:
        self.ops: list[tuple[str, dict[str, Any]]] = []

    def append(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ops.append((operation, payload or {}))
        return {"operation": operation}

    def list_baselines(self) -> list[dict[str, Any]]:
        return []


class _RealContext:
    def __init__(self, store: Any, ceiling: str) -> None:
        self.store = store
        self.archive = _RecordingArchive()
        self.max_classification = ceiling

    def is_available(self) -> bool:
        return bool(self.store.is_unlocked())


@pytest.fixture
def seeded(tmp_path: Path):  # type: ignore[no-untyped-def]
    """An STPA whose control-structure node an FMEA borrows, plus a TLP:RED analysis and node.

    The RED pair exists so every route can be asked what it does with content above a reader's
    ceiling; the WHITE pair is what a restricted reader is allowed to see.
    """
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "grouping.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    ids: dict[str, str] = {
        "stpa": store.create_analysis("Key availability", "STPA"),
        "fmea": store.create_analysis("Credential backend", "FMEA"),
        "secret_analysis": store.create_analysis("Embargoed review", "GRC", tlp="TLP:RED"),
    }
    ids["component"] = store.create_node(
        "control-structure-node", "Credential backend", analysis_id=ids["stpa"]
    )
    ids["secret_node"] = store.create_node(
        "hazard", "EMBARGOED HAZARD NAME", tlp="TLP:RED", analysis_id=ids["stpa"]
    )
    yield store, ids
    store.lock()


def _client(store: Any, ceiling: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    ctx = _RealContext(store, ceiling)
    app = build_api_app(router)
    monkeypatch.setattr(_HTTP_CTX, lambda: ctx)
    monkeypatch.setattr(_READ_CTX, lambda: ctx)
    client = TestClient(app, raise_server_exceptions=False)
    client.archive = ctx.archive  # type: ignore[attr-defined]
    return client


# ── Groups ─────────────────────────────────────────────────────────────────────


class TestGroupRoutes:
    def test_a_created_group_appears_in_the_listing(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, _ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)

        created = client.post(
            "/api/assurance/groups", json={"name": "Platform safety", "description": "The platform"}
        )
        assert created.status_code == 200
        group_id = created.json()["group_id"]

        listed = client.get("/api/assurance/groups")
        assert listed.status_code == 200
        assert group_id in {g["group_id"] for g in listed.json()["groups"]}
        assert [op for op, _ in client.archive.ops] == ["CREATE_GROUP"]  # type: ignore[attr-defined]

    def test_a_group_needs_a_name(self, seeded, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        store, _ids = seeded
        resp = _client(store, "TLP:RED", monkeypatch).post(
            "/api/assurance/groups", json={"name": "   "}
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "missing_name"

    def test_deleting_an_absent_group_is_404(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, _ids = seeded
        resp = _client(store, "TLP:RED", monkeypatch).delete(
            "/api/assurance/groups/GRP@nothing.here.000000"
        )
        assert resp.status_code == 404

    def test_deleting_a_group_unfiles_its_analyses_and_keeps_them(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)
        group_id = client.post("/api/assurance/groups", json={"name": "Platform safety"}).json()[
            "group_id"
        ]
        client.put(
            f"/api/assurance/analyses/{ids['stpa']}/group", json={"group_id": group_id}
        )

        deleted = client.delete(f"/api/assurance/groups/{group_id}")
        assert deleted.status_code == 200
        assert deleted.json()["unfiled_analyses"] == [ids["stpa"]]

        survivor = client.get(f"/api/assurance/analyses/{ids['stpa']}")
        assert survivor.status_code == 200
        assert not survivor.json()["analysis"]["group_id"]


# ── Filing ─────────────────────────────────────────────────────────────────────


class TestFilingRoutes:
    def test_filing_is_reversible(self, seeded, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)
        group_id = client.post("/api/assurance/groups", json={"name": "Platform safety"}).json()[
            "group_id"
        ]

        filed = client.put(
            f"/api/assurance/analyses/{ids['stpa']}/group", json={"group_id": group_id}
        )
        assert filed.status_code == 200
        assert filed.json()["group_id"] == group_id

        unfiled = client.put(
            f"/api/assurance/analyses/{ids['stpa']}/group", json={"group_id": None}
        )
        assert unfiled.status_code == 200
        assert not unfiled.json()["group_id"]

    def test_filing_into_a_group_that_does_not_exist_is_refused(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """An analysis filed under an id nothing answers to is invisible in every view keyed by
        group — worse than unfiled, which at least has a home."""
        store, ids = seeded
        resp = _client(store, "TLP:RED", monkeypatch).put(
            f"/api/assurance/analyses/{ids['stpa']}/group",
            json={"group_id": "GRP@nothing.here.000000"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "group_not_found"

    def test_filing_an_absent_analysis_is_404(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, _ids = seeded
        resp = _client(store, "TLP:RED", monkeypatch).put(
            "/api/assurance/analyses/STPA@nothing.here.000000/group", json={"group_id": None}
        )
        assert resp.status_code == 404

    def test_filing_an_above_ceiling_analysis_is_404(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:GREEN", monkeypatch)
        resp = client.put(
            f"/api/assurance/analyses/{ids['secret_analysis']}/group", json={"group_id": None}
        )
        assert resp.status_code == 404


# ── Participation ──────────────────────────────────────────────────────────────


class TestParticipationRoutes:
    def test_a_node_can_be_drawn_into_another_analysis(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)

        added = client.put(
            f"/api/assurance/analyses/{ids['fmea']}/participating-nodes/{ids['component']}"
        )
        assert added.status_code == 204
        assert added.content == b""

        listed = client.get(f"/api/assurance/analyses/{ids['fmea']}/participating-nodes")
        assert listed.status_code == 200
        assert listed.json()["participating_node_ids"] == [ids["component"]]

    def test_asserting_the_same_participation_twice_is_indistinguishable(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """PUT on the relation: it either holds or it does not, so the second assertion is the
        first one's outcome and must not produce a second row."""
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)
        url = f"/api/assurance/analyses/{ids['fmea']}/participating-nodes/{ids['component']}"

        assert client.put(url).status_code == 204
        assert client.put(url).status_code == 204

        listed = client.get(f"/api/assurance/analyses/{ids['fmea']}/participating-nodes").json()
        assert listed["participating_node_ids"] == [ids["component"]]
        assert listed["count"] == 1

    def test_participation_leaves_authorship_alone(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """The FMEA reasons over the STPA's component; it does not acquire or copy it."""
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)
        client.put(
            f"/api/assurance/analyses/{ids['fmea']}/participating-nodes/{ids['component']}"
        )

        detail = client.get(f"/api/assurance/nodes/{ids['component']}").json()
        assert detail["authored_by"]["analysis_id"] == ids["stpa"]
        assert [a["analysis_id"] for a in detail["participates_in"]] == [ids["fmea"]]
        assert detail["node"]["analysis_id"] == ids["stpa"]

    def test_a_node_cannot_participate_in_the_analysis_that_authored_it(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """Refused, not deduplicated. Authorship already draws the node in; a participation row
        beside it would double-count it in the working set and let a later removal look like a
        detachment that authorship does not permit."""
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)

        resp = client.put(
            f"/api/assurance/analyses/{ids['stpa']}/participating-nodes/{ids['component']}"
        )

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "invalid_participation"
        assert detail["details"] == {
            "node_id": ids["component"], "analysis_id": ids["stpa"],
        }
        assert client.get(f"/api/assurance/nodes/{ids['component']}").json()["participates_in"] == []

    def test_removing_a_member_is_idempotent_over_http(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)
        url = f"/api/assurance/analyses/{ids['fmea']}/participating-nodes/{ids['component']}"

        assert client.delete(url).status_code == 204
        assert client.delete(url).status_code == 204

    def test_an_above_ceiling_node_cannot_be_drawn_in(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        resp = _client(store, "TLP:GREEN", monkeypatch).put(
            f"/api/assurance/analyses/{ids['fmea']}/participating-nodes/{ids['secret_node']}"
        )
        assert resp.status_code == 404

    def test_a_member_list_omits_above_ceiling_nodes(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """Membership as stored names rows a restricted reader has no business knowing about."""
        store, ids = seeded
        store.add_analysis_member(ids["fmea"], ids["component"])
        store.add_analysis_member(ids["fmea"], ids["secret_node"])

        body = _client(store, "TLP:GREEN", monkeypatch).get(
            f"/api/assurance/analyses/{ids['fmea']}/participating-nodes"
        ).json()
        assert body["participating_node_ids"] == [ids["component"]]

    def test_participation_in_an_above_ceiling_analysis_is_not_reported(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """Otherwise `participates_in` discloses by the back door what a direct read 404s on."""
        store, ids = seeded
        store.add_analysis_member(ids["secret_analysis"], ids["component"])
        store.add_analysis_member(ids["fmea"], ids["component"])

        detail = _client(store, "TLP:GREEN", monkeypatch).get(
            f"/api/assurance/nodes/{ids['component']}"
        ).json()
        assert [a["analysis_id"] for a in detail["participates_in"]] == [ids["fmea"]]

    def test_members_of_an_above_ceiling_analysis_are_404(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        resp = _client(store, "TLP:GREEN", monkeypatch).get(
            f"/api/assurance/analyses/{ids['secret_analysis']}/participating-nodes"
        )
        assert resp.status_code == 404


# ── Search candidates (what an edge picker ranges over) ────────────────────────


class TestSearchCarriesProvenanceAndCrossesAnalyses:
    """The analysis method constrains what may be *authored*, never what may be *referenced*.

    An FMEA proposes failure modes and the hazard each one leads to belongs to the STPA that
    identified it. A search narrowed to the current analysis would make that edge unauthorable and
    leave copying the STPA's nodes as the only way through — which is the drift the three-relation
    model exists to prevent. So the search reaches everything visible, and says whose each result
    is.
    """

    def test_search_reaches_another_analysis_work(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)

        hits = client.get("/api/assurance/search?q=Credential").json()["hits"]

        assert ids["component"] in {hit["artifact_id"] for hit in hits}

    def test_a_hit_names_the_analysis_that_authored_it(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """Without this the picker offers bare names and the author cannot tell whose work they
        are reaching for."""
        store, ids = seeded
        client = _client(store, "TLP:RED", monkeypatch)

        hits = client.get("/api/assurance/search?q=Credential").json()["hits"]
        hit = next(h for h in hits if h["artifact_id"] == ids["component"])

        assert hit["analysis"]["analysis_id"] == ids["stpa"]
        assert hit["analysis"]["method"] == "STPA"

    def test_an_above_ceiling_analysis_is_not_named_on_a_visible_hit(
        self, seeded, monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        """A visible node authored by a classified analysis reports no analysis rather than its id
        — naming it would disclose by the back door what a direct read answers 404 to."""
        store, ids = seeded
        visible_node = store.create_node(
            "hazard", "Rotation stalls", tlp="TLP:WHITE", analysis_id=ids["secret_analysis"]
        )
        client = _client(store, "TLP:GREEN", monkeypatch)

        hits = client.get("/api/assurance/search?q=Rotation").json()["hits"]
        hit = next(h for h in hits if h["artifact_id"] == visible_node)

        assert hit["analysis"] is None
