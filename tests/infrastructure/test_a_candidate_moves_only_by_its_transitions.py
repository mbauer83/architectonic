"""A candidate's state moves by a closed table, and into `integrated` only by being applied.

An edit could set any state, so `{"state": "integrated"}` on an empty draft answered 200: the record
said it had been applied when nothing had been written, and the test-set read counted it as an
integration. And the overlap check refused a draft that apply would write, so the check was the one
step of the two that could be skipped.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.change_sets.candidate_architecture import (
    CANDIDATE_STATES,
    EDITABLE_TRANSITIONS,
    refused_transition,
)
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as model
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _create(client: TestClient, **record: Any) -> str:
    created = client.post("/api/change-sets", json={"record": {"name": "Candidate", **record}})
    assert created.status_code == 200, created.text
    return str(created.json()["record"]["id"])


def _set_state(client: TestClient, ref: str, becomes: str) -> Any:
    version = client.get(f"/api/change-sets/{ref}").json()["version"]
    return client.patch(f"/api/change-sets/{ref}", json={"based_on": version, "patch": {"state": becomes}})


def test_the_table_never_lets_an_edit_integrate_and_terminal_states_move_nowhere() -> None:
    for was in CANDIDATE_STATES:
        assert refused_transition(was, "integrated") is not None or was == "integrated"
        if was in {"integrated", "rejected", "superseded"}:
            assert EDITABLE_TRANSITIONS[was] == frozenset()
    assert refused_transition("candidate", "integrated", applied=True) is None
    assert refused_transition(None, "integrated") is not None
    assert refused_transition(None, "draft") is None


def test_an_edit_to_integrated_is_refused_naming_apply_on_both_surfaces(client: TestClient) -> None:
    ref = _create(client)

    refused = _set_state(client, ref, "integrated")

    assert refused.status_code == 409, refused.text
    assert "apply" in refused.json()["detail"]["message"]
    assert client.get(f"/api/change-sets/{ref}").json()["record"]["state"] == "draft"
    version = mcp.change_set_read(ref, repo_root=str(client.root))["version"]  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="apply"):
        mcp.change_set_edit(ref, version, {"state": "integrated"}, str(client.root))  # type: ignore[attr-defined]


def test_a_new_candidate_cannot_be_born_integrated(client: TestClient) -> None:
    refused = client.post("/api/change-sets", json={"record": {"name": "Born late", "state": "integrated"}})

    assert refused.status_code == 409, refused.text


def test_offered_withdrawn_and_set_aside_are_edits_and_a_set_aside_one_stays(client: TestClient) -> None:
    ref = _create(client)
    for becomes in ("candidate", "draft", "candidate", "rejected"):
        moved = _set_state(client, ref, becomes)
        assert moved.status_code == 200, (becomes, moved.text)

    assert _set_state(client, ref, "draft").status_code == 409


def test_applying_is_the_way_in_to_integrated(client: TestClient) -> None:
    root = client.root  # type: ignore[attr-defined]
    made = model.artifact_create_entity(
        artifact_type="application-component", name="Catalog", dry_run=False, repo_root=str(root),
    )
    ref = _create(client)
    version = client.get(f"/api/change-sets/{ref}").json()["version"]
    recorded = client.post(f"/api/change-sets/{ref}/operations", json={"based_on": version, "operation": {
        "op": "edit_entity", "artifact_id": made["artifact_id"], "field": "name", "value": "Registry"}})
    assert recorded.status_code == 200, recorded.text

    applied = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})

    assert applied.status_code == 200, applied.text
    assert client.get(f"/api/change-sets/{ref}").json()["record"]["state"] == "integrated"


def test_a_draft_is_checked_for_overlaps_as_it_may_be_applied(client: TestClient) -> None:
    drafts = [_create(client, name=f"Draft {n}") for n in (1, 2)]

    checked = client.post("/api/change-set-checks", json={"candidates": drafts})

    assert checked.status_code == 200, checked.text
    assert checked.json()["candidates"] == drafts
