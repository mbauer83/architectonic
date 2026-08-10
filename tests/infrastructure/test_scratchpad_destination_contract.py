"""One field's enum, enforced at both ends rather than only on the way out.

A note carrying `destination: up2parts-autocam` — an agent reading the field name as "which project
this lands in" — was accepted, persisted, and version-bumped by `PATCH`, which then answered **500**
because the response contract's pydantic `Literal` rejected what the domain had just stored. Every
subsequent `GET` answered 500 too, so the scratchpad was unreadable for good: the GUI showed only
"This scratchpad could not be loaded", and the id of the offending note could not be discovered from
the GUI at all, because discovering it requires the read that fails.

Three properties, each of which was false:

* a caller's bad value is **refused**, before anything is written;
* a file that already holds one still **loads**, degraded rather than fatal, because the read is the
  only route back to a canvas that has one;
* a refused write leaves the file and the version **untouched** — the 500 committed, so a caller
  told the write had failed then got a 409 on a correct retry.

`tests/architecture/test_no_literal_is_laundered_into_the_domain.py` holds the fingerprint that
made it possible.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.rest.routers import scratchpads as scratchpad_router
from src.infrastructure.rest.routers import state as s
from tests.support.api_app import build_api_app

_ILLEGAL = "up2parts-autocam"


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "architecture-repository"
    root.mkdir()
    return root


@pytest.fixture
def client(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(s, "maybe_engagement_root", lambda: repo_root)
    monkeypatch.setattr(
        s, "authorized_write", lambda _operation_id, fn, *args, **kwargs: fn(*args, **kwargs)
    )
    with TestClient(build_api_app(scratchpad_router.router)) as test_client:
        yield test_client


def _create(client: TestClient) -> dict:
    response = client.post("/api/scratchpads", json={"name": "Q3 thinking", "group": "platform-core"})
    assert response.status_code == 201, response.text
    return response.json()


def _stored_file(repo_root: Path) -> Path:
    files = sorted(repo_root.rglob("*.scratchpad.yaml"))
    assert len(files) == 1, files
    return files[0]


class TestACallerIsRefused:
    def test_a_patch_naming_a_destination_that_does_not_exist_is_refused(
        self, client: TestClient, repo_root: Path
    ) -> None:
        created = _create(client)
        artifact_id = created["artifact-id"]

        response = client.patch(
            f"/api/scratchpads/{artifact_id}",
            json={
                "version": created["version"],
                "upsert": {"notes": [{"id": "n1", "title": "A thought", "destination": _ILLEGAL}]},
            },
        )

        assert response.status_code == 400, response.text
        # The message is what an agent acts on, so it names the legal values and the field that was
        # actually wanted — the confusion that produced this was `destination` vs `targets`.
        detail = response.json()["detail"] if "detail" in response.json() else response.text
        assert _ILLEGAL in str(detail)
        assert "undecided" in str(detail) and "element" in str(detail)
        assert "targets" in str(detail)

    def test_the_refused_write_changed_nothing_at_all(
        self, client: TestClient, repo_root: Path
    ) -> None:
        """The half that made it dangerous: the 500 had already committed and bumped the version,
        so a caller who believed the write failed was then refused its retry with a 409."""
        created = _create(client)
        artifact_id = created["artifact-id"]
        before = _stored_file(repo_root).read_bytes()

        client.patch(
            f"/api/scratchpads/{artifact_id}",
            json={
                "version": created["version"],
                "upsert": {"notes": [{"id": "n1", "title": "A thought", "destination": _ILLEGAL}]},
            },
        )

        assert _stored_file(repo_root).read_bytes() == before
        again = client.get(f"/api/scratchpads/{artifact_id}")
        assert again.status_code == 200, again.text
        assert again.json()["version"] == created["version"]

    def test_a_whole_document_put_is_refused_on_the_same_grounds(
        self, client: TestClient, repo_root: Path
    ) -> None:
        """`PUT` and `PATCH` are one write in two shapes, so they refuse the same input."""
        created = _create(client)
        artifact_id = created["artifact-id"]
        document = dict(created)
        document["notes"] = [{"id": "n1", "title": "A thought", "destination": _ILLEGAL}]

        response = client.put(
            f"/api/scratchpads/{artifact_id}",
            json={"version": created["version"], "group": "platform-core", "scratchpad": document},
        )

        assert response.status_code == 400, response.text
        assert _stored_file(repo_root).read_bytes() != b"", "the file must still be there"
        assert client.get(f"/api/scratchpads/{artifact_id}").status_code == 200

    @pytest.mark.parametrize("legal", ["undecided", "element", "document", "none"])
    def test_every_legal_destination_is_still_accepted(
        self, client: TestClient, legal: str
    ) -> None:
        """The refusal must not have narrowed the field to the values this test file happens to use."""
        created = _create(client)

        response = client.patch(
            f"/api/scratchpads/{created['artifact-id']}",
            json={
                "version": created["version"],
                "upsert": {"notes": [{"id": "n1", "title": "A thought", "destination": legal}]},
            },
        )

        assert response.status_code == 200, response.text


class TestAFileThatAlreadyHoldsOne:
    def test_it_loads_degraded_rather_than_not_at_all(
        self, client: TestClient, repo_root: Path
    ) -> None:
        """The self-healing half. Refusing on load would be correct and useless: it would move the
        brick from 500 to 400 while leaving the canvas exactly as unreachable."""
        created = _create(client)
        artifact_id = created["artifact-id"]
        client.patch(
            f"/api/scratchpads/{artifact_id}",
            json={
                "version": created["version"],
                "upsert": {"notes": [{"id": "n1", "title": "A thought", "destination": "element"}]},
            },
        )
        # What the old write path put on disk, reproduced exactly rather than described.
        stored = _stored_file(repo_root)
        stored.write_text(
            stored.read_text(encoding="utf-8").replace(
                "destination: element", f"destination: {_ILLEGAL}"
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/scratchpads/{artifact_id}")

        assert response.status_code == 200, response.text
        note = next(row for row in response.json()["notes"] if row["id"] == "n1")
        assert note["destination"] == "undecided"

    def test_and_can_then_be_edited_back_into_shape(
        self, client: TestClient, repo_root: Path
    ) -> None:
        """The recovery path has to work, or the refusal above would only defend the brick."""
        created = _create(client)
        artifact_id = created["artifact-id"]
        client.patch(
            f"/api/scratchpads/{artifact_id}",
            json={
                "version": created["version"],
                "upsert": {"notes": [{"id": "n1", "title": "A thought", "destination": "element"}]},
            },
        )
        stored = _stored_file(repo_root)
        stored.write_text(
            stored.read_text(encoding="utf-8").replace(
                "destination: element", f"destination: {_ILLEGAL}"
            ),
            encoding="utf-8",
        )
        current = client.get(f"/api/scratchpads/{artifact_id}").json()

        repaired = client.patch(
            f"/api/scratchpads/{artifact_id}",
            json={
                "version": current["version"],
                "upsert": {"notes": [{"id": "n1", "destination": "document"}]},
            },
        )

        assert repaired.status_code == 200, repaired.text
        note = next(row for row in repaired.json()["notes"] if row["id"] == "n1")
        assert note["destination"] == "document"
