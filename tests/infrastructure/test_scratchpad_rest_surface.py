"""The scratchpad REST surface, exercised through the ASGI stack.

HTTP-level rather than unit tests of the handlers, because what can break here is the *wiring*: a
router that is not mounted, a body model that rejects the shape the client sends, an operation id
that does not match its manifest row. A unit test of each function would pass through all three.

The 409 gets its own coverage because it is the one thing that protects an afternoon of somebody
else's work, and it is only reachable when two writers hold the same version.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.rest.routers import scratchpads as scratchpad_router
from src.infrastructure.rest.routers import state as s
from tests.support.api_app import build_api_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    repo_root = tmp_path / "architecture-repository"
    repo_root.mkdir()
    monkeypatch.setattr(s, "maybe_engagement_root", lambda: repo_root)
    # The mutation executor is the write queue and gate; this suite is about the HTTP contract, so
    # the operation runs directly and the authorization identity is asserted separately by the
    # architecture fitness functions that compare the manifest with the served surface.
    monkeypatch.setattr(s, "authorized_write", lambda _operation_id, fn, *args, **kwargs: fn(*args, **kwargs))
    # The shared helper, not a bare app: a router on a bare `FastAPI()` carries none of the
    # product's response contracts, so a test against one asserts a shape no client receives.
    with TestClient(build_api_app(scratchpad_router.router)) as test_client:
        yield test_client


def _create(client: TestClient, name: str = "Q3 thinking", group: str = "strategy-and-value") -> dict:
    response = client.post("/api/scratchpads", json={"name": name, "group": group})
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateAndRead:
    def test_a_create_returns_the_seeded_aggregate_and_its_address(self, client: TestClient) -> None:
        created = _create(client)

        assert created["artifact-id"].startswith("SCR@")
        assert {area["id"] for area in created["areas"]} == {"strategy", "portfolio", "project", "enabling"}
        assert created["group"] == "strategy-and-value"

    def test_the_location_header_addresses_what_was_made(self, client: TestClient) -> None:
        response = client.post("/api/scratchpads", json={"name": "Named", "group": "platform-core"})

        assert response.headers["Location"] == f"/api/scratchpads/{response.json()['artifact-id']}"
        assert client.get(response.headers["Location"]).status_code == 200

    def test_a_read_returns_the_whole_aggregate(self, client: TestClient) -> None:
        created = _create(client)

        read = client.get(f"/api/scratchpads/{created['artifact-id']}").json()

        assert read["artifact-type"] == "scratchpad"
        assert read["meta-ontology"] == "archimate-4"
        assert "layout" in read

    def test_an_unknown_scratchpad_is_a_404(self, client: TestClient) -> None:
        assert client.get("/api/scratchpads/SCR@9.z.nothing").status_code == 404

    def test_a_body_field_the_server_does_not_know_is_refused(self, client: TestClient) -> None:
        """Closed bodies: an ignored field is a client believing something that is not happening."""
        response = client.post(
            "/api/scratchpads", json={"name": "X", "group": "g", "colour": "blue"}
        )

        assert response.status_code == 422


class TestListing:
    def test_it_lists_summaries_and_filters_by_group(self, client: TestClient) -> None:
        _create(client, "One", group="strategy-and-value")
        _create(client, "Two", group="platform-core")

        everything = client.get("/api/scratchpads").json()["scratchpads"]
        filtered = client.get("/api/scratchpads", params={"group": "platform-core"}).json()["scratchpads"]

        assert len(everything) == 2
        assert [summary["name"] for summary in filtered] == ["Two"]

    def test_a_summary_carries_no_notes(self, client: TestClient) -> None:
        _create(client)

        summary = client.get("/api/scratchpads").json()["scratchpads"][0]

        assert "notes" not in summary
        assert summary["note-count"] == 0


class TestReplace:
    def _replace(self, client: TestClient, created: dict, document: dict, version: str | None = None):
        return client.put(
            f"/api/scratchpads/{created['artifact-id']}",
            json={
                "version": version or created["version"],
                "group": created["group"],
                "scratchpad": document,
            },
        )

    def _with_note(self, created: dict) -> dict:
        document = {key: value for key, value in created.items() if key != "group"}
        document["notes"] = [{"id": "n1", "title": "Grow into mid-market"}]
        document.setdefault("layout", {})["notes"] = {"n1": [40, 60]}
        return document

    def test_a_replace_stores_the_whole_aggregate(self, client: TestClient) -> None:
        created = _create(client)

        response = self._replace(client, created, self._with_note(created))

        assert response.status_code == 200, response.text
        assert [note["title"] for note in response.json()["notes"]] == ["Grow into mid-market"]

    def test_the_derived_area_is_served_so_no_client_recomputes_it(self, client: TestClient) -> None:
        created = _create(client)

        stored = self._replace(client, created, self._with_note(created)).json()

        assert stored["notes"][0]["area"] == "strategy"

    def test_a_second_writer_on_a_stale_version_gets_a_409(self, client: TestClient) -> None:
        created = _create(client)
        self._replace(client, created, self._with_note(created))

        conflicted = self._replace(client, created, self._with_note(created))

        assert conflicted.status_code == 409
        assert "moved on" in conflicted.text

    def test_an_aggregate_that_breaks_an_invariant_is_a_400_naming_it(self, client: TestClient) -> None:
        created = _create(client)
        document = self._with_note(created)
        document["links"] = [{"id": "l1", "source": "n1", "target": "ghost"}]

        response = self._replace(client, created, document)

        assert response.status_code == 400
        assert "ghost" in response.text

    def test_the_url_names_the_scratchpad_even_if_the_body_disagrees(self, client: TestClient) -> None:
        """A body carrying a different id is a client bug, not a rename request."""
        created = _create(client)
        document = self._with_note(created)
        document["artifact-id"] = "SCR@9.z.somewhere-else"

        stored = self._replace(client, created, document).json()

        assert stored["artifact-id"] == created["artifact-id"]


class TestDelete:
    def test_a_delete_removes_it_and_answers_no_content(self, client: TestClient) -> None:
        created = _create(client)

        response = client.delete(f"/api/scratchpads/{created['artifact-id']}?dry_run=false")

        assert response.status_code == 204
        assert response.content == b""
        assert client.get(f"/api/scratchpads/{created['artifact-id']}").status_code == 404

    def test_it_plans_unless_told_otherwise(self, client: TestClient) -> None:
        """Every write on this surface plans by default; a delete that committed on a bare call is
        how a cleanup routine removes something nobody asked it to."""
        created = _create(client)

        planned = client.delete(f"/api/scratchpads/{created['artifact-id']}")

        assert planned.status_code == 200
        assert planned.json()["would_delete"] == created["artifact-id"]
        assert client.get(f"/api/scratchpads/{created['artifact-id']}").status_code == 200

    def test_deleting_what_is_not_there_is_a_404(self, client: TestClient) -> None:
        assert client.delete("/api/scratchpads/SCR@9.z.nothing?dry_run=false").status_code == 404


class TestLift:
    """The preflight over HTTP. Execution is covered where the plan is decided, and by the write
    path's own suite — what can only break here is the wiring: the route, the body model, the
    operation id its manifest row names, and the shape a client is handed."""

    def _typed_pad(self, client: TestClient) -> dict:
        created = _create(client)
        document = {key: value for key, value in created.items() if key != "group"}
        document["notes"] = [
            {"id": "n1", "title": "Grow into mid-market", "destination": "element",
             "element-type": "goal"},
            {"id": "n2", "title": "Still thinking"},
        ]
        response = client.put(
            f"/api/scratchpads/{created['artifact-id']}",
            json={"version": created["version"], "group": created["group"], "scratchpad": document},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _lift(self, client: TestClient, pad: dict, **body: object) -> dict:
        response = client.post(
            f"/api/scratchpads/{pad['artifact-id']}/lift",
            json={"version": pad["version"], "selection": ["n1"], **body},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_a_preflight_reports_what_would_be_created_without_writing(self, client: TestClient) -> None:
        pad = self._typed_pad(client)

        plan = self._lift(client, pad)

        created = [item for item in plan["items"] if item["outcome"] == "create"]
        assert [item["id"] for item in created] == ["n1"]
        assert plan["dry-run"] is True and plan["committed"] is False
        # The scratchpad is untouched: nothing was realized, so nothing was written back to it.
        stored = client.get(f"/api/scratchpads/{pad['artifact-id']}").json()
        assert all("model-ref" not in note for note in stored["notes"])

    def test_an_undecided_note_in_the_selection_blocks_the_lift_and_says_why(self, client: TestClient) -> None:
        pad = self._typed_pad(client)

        plan = self._lift(client, pad, selection=["n1", "n2"])

        refused = [item for item in plan["items"] if item["outcome"] == "refuse"]
        assert plan["blocks"] is True
        assert [item["id"] for item in refused] == ["n2"]

    def test_an_empty_selection_is_refused_as_the_lift_rather_than_as_an_item(self, client: TestClient) -> None:
        pad = self._typed_pad(client)

        plan = self._lift(client, pad, selection=[])

        assert plan["blocks"] is True
        assert "Nothing is selected" in plan["refusal"]
        assert plan["items"] == []

    def test_lifting_a_scratchpad_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/scratchpads/SCR@9.z.nothing/lift",
            json={"version": "0.1.0", "selection": ["n1"]},
        )

        assert response.status_code == 404

    def test_a_field_the_server_does_not_know_is_refused_rather_than_ignored(self, client: TestClient) -> None:
        pad = self._typed_pad(client)

        response = client.post(
            f"/api/scratchpads/{pad['artifact-id']}/lift",
            json={"version": pad["version"], "selection": ["n1"], "targts": {}},
        )

        assert response.status_code == 422
