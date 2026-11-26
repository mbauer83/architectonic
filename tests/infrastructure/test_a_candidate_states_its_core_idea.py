"""A candidate states its core idea in a sentence or two, apart from its rationale, on both surfaces.

A candidate had only `rationale`, the longer argument, and no reader showed it: the stress workspace named an
adaptation by its name and its operations, so a reader choosing which adaptations to integrate had nothing
short to compare. `description` is that statement — written with the header, changed by an edit, and answered
by a read and by the list on REST and MCP alike. It is optional, so a candidate stored before it reads as
having none.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.change_sets.candidate_architecture import DESCRIPTION_LIMIT
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.candidate_wire import CandidateHeader, CandidatePatch
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

_IDEA = "Rules move out of the code into a versioned, tested rule set."


@pytest.fixture
def root(tmp_path: Path) -> Iterator[Path]:
    made = repository_in(tmp_path)
    state.init_state(ArtifactRepository(shared_artifact_index([made])), made, None)
    try:
        yield made
    finally:
        reset_state_for_test()


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    with TestClient(build_api_app(candidates.router)) as served:
        yield served


def _listed(client: TestClient, ref: str) -> dict[str, Any]:
    return next(one for one in client.get("/api/candidates").json()["candidates"] if one["id"] == ref)


def test_a_description_written_with_the_header_is_read_and_listed_apart_from_the_rationale(client: TestClient) -> None:
    rationale = "The rules change weekly; the code does not."
    created = client.post("/api/candidates", json={
        "record": {"name": "Rule set", "description": _IDEA, "rationale": rationale},
    })
    assert created.status_code == 200, created.text
    ref = created.json()["record"]["id"]

    record = client.get(f"/api/candidates/{ref}").json()["record"]
    assert (record["description"], record["rationale"]) == (_IDEA, rationale)
    assert _listed(client, ref)["description"] == _IDEA


def test_an_edit_changes_the_description_and_an_empty_one_takes_it_away(client: TestClient) -> None:
    ref = client.post("/api/candidates", json={"record": {"name": "Rule set"}}).json()["record"]["id"]
    assert _listed(client, ref)["description"] == ""

    version = client.get(f"/api/candidates/{ref}").json()["version"]
    edited = client.patch(f"/api/candidates/{ref}", json={"based_on": version, "patch": {"description": _IDEA}})
    assert edited.status_code == 200, edited.text
    assert _listed(client, ref)["description"] == _IDEA

    cleared = client.patch(f"/api/candidates/{ref}", json={"based_on": edited.json()["version"],
                                                              "patch": {"description": ""}})
    assert cleared.status_code == 200, cleared.text
    assert "description" not in client.get(f"/api/candidates/{ref}").json()["record"]
    assert _listed(client, ref)["description"] == ""


def test_a_description_longer_than_a_sentence_or_two_is_refused_on_both_surfaces(
    client: TestClient, root: Path,
) -> None:
    too_long = "x" * (DESCRIPTION_LIMIT + 1)
    refused = client.post("/api/candidates", json={"record": {"name": "Wordy", "description": too_long}})
    assert refused.status_code == 422, refused.text
    with pytest.raises(ValueError, match=str(DESCRIPTION_LIMIT)):
        CandidateHeader(name="Wordy", description=too_long)
    with pytest.raises(ValueError, match=str(DESCRIPTION_LIMIT)):
        CandidatePatch(description=too_long)


def test_mcp_writes_reads_and_lists_the_description_as_rest_does(root: Path) -> None:
    created = mcp.candidate_create(CandidateHeader(name="Rule set", description=_IDEA), repo_root=str(root))
    ref = created["record"]["id"]
    assert mcp.candidate_read(ref, repo_root=str(root))["record"]["description"] == _IDEA

    mcp.candidate_edit(ref, created["version"], CandidatePatch(description="Rules as data."), str(root))

    listed = next(one for one in mcp.candidate_list(repo_root=str(root))["candidates"] if one["id"] == ref)
    assert listed["description"] == "Rules as data."
