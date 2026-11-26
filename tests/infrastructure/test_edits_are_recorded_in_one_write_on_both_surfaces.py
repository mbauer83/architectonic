"""A candidate's edits are recorded several to a write, on REST and MCP alike, and one can be taken back.

Before: one edit per call, each needing the version the last answered; MCP had no way to record an edit
at all (only a wholesale `changes` patch whose bases the agent had to compute); a create had to bring an
id the caller minted; and a recorded create or connection could only be removed by rewriting the list.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.candidate_wire import CandidateHeader, RecordedEdit
from src.infrastructure.mcp import mcp_artifact_server as model
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

EDITS = TypeAdapter(list[RecordedEdit])


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


def _edits(client: TestClient) -> list[dict[str, Any]]:
    source = model.artifact_create_entity(
        artifact_type="application-component", name="Catalog", dry_run=False,
        repo_root=str(client.root),  # type: ignore[attr-defined]
    )["artifact_id"]
    return [
        {"op": "create_entity", "fields": {"artifact_type": "application-component", "name": "Catalog Cache",
                                           "group": "uncategorized"}},
        {"op": "edit_entity", "artifact_id": source, "field": "name", "value": "Module Registry"},
    ]


def test_several_edits_are_one_write_and_a_create_is_given_its_id(client: TestClient) -> None:
    created = client.post("/api/candidates", json={"record": {"name": "Cache"}}).json()
    ref = created["record"]["id"]

    recorded = client.post(f"/api/candidates/{ref}/operations", json={
        "based_on": created["version"], "operations": _edits(client)})

    assert recorded.status_code == 200, recorded.text
    operations = recorded.json()["record"]["changes"]["operations"]
    assert [one["op"] for one in operations] == ["create_entity", "edit_entity"]
    minted = next(one["artifact_id"] for one in operations if one["op"] == "create_entity")
    assert minted.startswith("APP@") and minted.endswith(".catalog-cache")
    standing = client.get(f"/api/candidates/{ref}/standing").json()["standing"]
    assert {item["standing"] for item in standing} == {"applies"}


def test_a_refused_edit_in_a_list_records_none_of_it(client: TestClient) -> None:
    created = client.post("/api/candidates", json={"record": {"name": "Cache"}}).json()
    ref = created["record"]["id"]
    edits = [*_edits(client), {"op": "edit_entity", "artifact_id": "APP@1.nothere", "field": "name", "value": "x"}]

    body = {"based_on": created["version"], "operations": edits}
    refused = client.post(f"/api/candidates/{ref}/operations", json=body)

    assert refused.status_code == 422, refused.text
    assert client.get(f"/api/candidates/{ref}").json()["version"] == created["version"]


def test_drop_takes_back_a_create_and_what_names_it(client: TestClient) -> None:
    source = model.artifact_create_entity(
        artifact_type="application-component", name="Catalog", dry_run=False,
        repo_root=str(client.root),  # type: ignore[attr-defined]
    )["artifact_id"]
    chosen = "APP@1795600000.abcdEF.catalog-cache"
    created = client.post("/api/candidates", json={"record": {"name": "Cache"}, "operations": [
        {"op": "create_entity", "artifact_id": chosen, "fields": {
            "artifact_type": "application-component", "name": "Catalog Cache", "group": "uncategorized"}},
        {"op": "add_connection", "source_entity": source, "connection_type": "archimate-serving",
         "target_entity": chosen},
        {"op": "edit_entity", "artifact_id": source, "field": "name", "value": "Registry"},
    ]}).json()
    ref = created["record"]["id"]
    assert len(created["record"]["changes"]["operations"]) == 3

    dropped = client.post(f"/api/candidates/{ref}/operations", json={
        "based_on": created["version"], "operations": [{"op": "drop", "artifact_id": "APP@1795600000.abcdEF"}]})
    nothing = client.post(f"/api/candidates/{ref}/operations", json={
        "based_on": dropped.json()["version"], "operations": [{"op": "drop", "artifact_id": chosen}]})

    assert dropped.status_code == 200, dropped.text
    assert [one["op"] for one in dropped.json()["record"]["changes"]["operations"]] == ["edit_entity"]
    assert nothing.status_code == 422 and "nothing to drop" in nothing.json()["detail"]["message"]


def test_mcp_records_edits_as_rest_does_and_reads_by_one_tool_each(client: TestClient) -> None:
    root = str(client.root)  # type: ignore[attr-defined]
    created = mcp.candidate_create(CandidateHeader(name="Over MCP"), repo_root=root)
    ref = created["record"]["id"]

    recorded = mcp.candidate_record(ref, created["version"], EDITS.validate_python(_edits(client)), repo_root=root)

    assert [one["op"] for one in recorded["record"]["changes"]["operations"]] == ["create_entity", "edit_entity"]
    assert mcp.candidate_read(ref, repo_root=root) == client.get(f"/api/candidates/{ref}").json()
    assert mcp.candidate_standing(ref, repo_root=root) == client.get(f"/api/candidates/{ref}/standing").json()
    assert mcp.candidate_compare(ref, repo_root=root) == client.get(f"/api/candidates/{ref}/diff").json()
    assert mcp.analysis_residuality(ref, repo_root=root) == {"candidate": ref, "analyses": []}


def _with_keywords(client: TestClient) -> str:
    entity = model.artifact_create_entity(
        artifact_type="application-component", name="Indexer", keywords=["search", "metadata"], dry_run=False,
        repo_root=str(client.root),  # type: ignore[attr-defined]
    )
    return str(entity["artifact_id"])


def test_an_edit_of_a_list_field_is_answered_as_it_is_read_back_on_rest(client: TestClient) -> None:
    """A list field's base is read off a record as a tuple; answered as held, the write happened and its answer
    was a 500 (`base.value` not JSON), on the create and on the record alike."""
    edit = {"op": "edit_entity", "artifact_id": _with_keywords(client), "field": "keywords", "value": ["probe"]}

    created = client.post("/api/candidates", json={"record": {"name": "Keywords"}, "operations": [edit]})
    assert created.status_code == 200, created.text
    ref = created.json()["record"]["id"]
    assert created.json() == client.get(f"/api/candidates/{ref}").json()
    assert created.json()["record"]["changes"]["operations"][0]["base"] == {"value": ["search", "metadata"]}

    other = client.post("/api/candidates", json={"record": {"name": "Keywords later"}}).json()
    later = other["record"]["id"]
    recorded = client.post(f"/api/candidates/{later}/operations", json={
        "based_on": other["version"], "operations": [edit]})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json() == client.get(f"/api/candidates/{later}").json()


def test_an_edit_of_a_list_field_is_answered_as_it_is_read_back_on_mcp(client: TestClient) -> None:
    root = str(client.root)  # type: ignore[attr-defined]
    edit = {"op": "edit_entity", "artifact_id": _with_keywords(client), "field": "keywords", "value": ["probe"]}
    created = mcp.candidate_create(CandidateHeader(name="Over MCP"), repo_root=root)

    recorded = mcp.candidate_record(
        created["record"]["id"], created["version"], EDITS.validate_python([edit]), repo_root=root)

    assert recorded == mcp.candidate_read(created["record"]["id"], repo_root=root)
