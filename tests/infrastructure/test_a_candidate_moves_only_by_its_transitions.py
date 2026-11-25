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
from src.infrastructure.candidate_wire import CandidatePatch
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
        mcp.change_set_edit(ref, version, CandidatePatch(state="integrated"), str(client.root))  # type: ignore[attr-defined]


def test_a_new_candidate_cannot_be_born_integrated(client: TestClient) -> None:
    refused = client.post("/api/change-sets", json={"record": {"name": "Born late", "state": "integrated"}})

    # The request schema admits draft or candidate only; the store refuses it too, for any other caller.
    assert refused.status_code == 422, refused.text
    assert refused_transition(None, "integrated") is not None


def test_offered_withdrawn_and_set_aside_are_edits_and_a_set_aside_one_stays(client: TestClient) -> None:
    ref = _create(client)
    for becomes in ("candidate", "draft", "candidate", "rejected"):
        moved = _set_state(client, ref, becomes)
        assert moved.status_code == 200, (becomes, moved.text)

    assert _set_state(client, ref, "draft").status_code == 409


def test_recording_or_rebasing_an_offered_candidate_is_a_409_that_says_to_return_it_to_draft(
    client: TestClient,
) -> None:
    """Regression: rebasing an offered candidate answered 422 with a sentence about recording."""
    ref = _create(client)
    assert _set_state(client, ref, "candidate").status_code == 200
    version = client.get(f"/api/change-sets/{ref}").json()["version"]

    rebased = client.post(f"/api/change-sets/{ref}/rebase", json={"based_on": version})
    recorded = client.post(f"/api/change-sets/{ref}/operations", json={"based_on": version, "operations": [
        {"op": "remove_entity", "artifact_id": "APP@1.x"}]})

    for refused in (rebased, recorded):
        assert refused.status_code == 409, refused.text
        assert "Return it to draft" in refused.json()["detail"]["message"]


def test_applying_is_the_way_in_to_integrated(client: TestClient) -> None:
    root = client.root  # type: ignore[attr-defined]
    made = model.artifact_create_entity(
        artifact_type="application-component", name="Catalog", dry_run=False, repo_root=str(root),
    )
    ref = _create(client)
    version = client.get(f"/api/change-sets/{ref}").json()["version"]
    recorded = client.post(f"/api/change-sets/{ref}/operations", json={"based_on": version, "operations": [{
        "op": "edit_entity", "artifact_id": made["artifact_id"], "field": "name", "value": "Registry"}]})
    assert recorded.status_code == 200, recorded.text

    applied = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})

    assert applied.status_code == 200, applied.text
    assert client.get(f"/api/change-sets/{ref}").json()["record"]["state"] == "integrated"


def test_a_rename_during_an_apply_does_not_turn_a_committed_write_into_a_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the integrated mark was saved over the version read before the write, so a header edit
    made while the write ran answered 409 "the candidate changed" for a write that had committed."""
    from src.infrastructure.candidates import service as candidate_service  # noqa: PLC0415

    root = client.root  # type: ignore[attr-defined]
    made = model.artifact_create_entity(
        artifact_type="application-component", name="Catalog", dry_run=False, repo_root=str(root),
    )
    ref = _create(client)
    version = client.get(f"/api/change-sets/{ref}").json()["version"]
    client.post(f"/api/change-sets/{ref}/operations", json={"based_on": version, "operations": [{
        "op": "edit_entity", "artifact_id": made["artifact_id"], "field": "name", "value": "Registry"}]})
    write = candidate_service.write_operations

    def write_then_rename(*args: Any, **kwargs: Any) -> Any:
        # Another writer (a second process, say) renames it while the write runs, past this one's queue.
        written = write(*args, **kwargs)
        other = candidate_service.CandidateService(root)
        current = other.read(ref)
        other.edit(ref, current["version"], {"name": "Renamed"})
        return written

    monkeypatch.setattr(candidate_service, "write_operations", write_then_rename)

    applied = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})

    assert applied.status_code == 200, applied.text
    assert applied.json()["integrated"] is True
    record = client.get(f"/api/change-sets/{ref}").json()["record"]
    assert (record["state"], record["name"]) == ("integrated", "Renamed")


def test_a_very_long_name_is_given_a_bounded_slug_rather_than_a_500(client: TestClient) -> None:
    """Regression: a 5000-character name became a file name the file system refused."""
    created = client.post("/api/change-sets", json={"record": {"name": "very long name " * 400}})

    assert created.status_code == 200, created.text
    assert len(created.json()["record"]["id"]) < 120


def test_a_draft_is_checked_for_overlaps_as_it_may_be_applied(client: TestClient) -> None:
    drafts = [_create(client, name=f"Draft {n}") for n in (1, 2)]

    checked = client.post("/api/change-set-checks", json={"candidates": drafts})

    assert checked.status_code == 200, checked.text
    assert checked.json()["candidates"] == drafts
