"""What a candidate's stack creates is named by the id its create chose, at every level and in every answer.

Regression (umbrella planning, 2026-11-26): a naive candidate created its elements by artifact id, recorded
over MCP and never placed on a canvas. The composed view keyed them by an internal `$ref:` handle, which then
leaked into the incidence hits, the coupling pairs, `coverage.untouched`, the diff and the record; an
adaptation stacked on the naive could edit such an element only by that handle, and a connection to it by
artifact id was stored, then read as joining nothing.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as model
from src.infrastructure.rest.routers import candidates, documents, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

EXTRACTOR = "APP@1795687000.aTx0001"
TEXT = "DOB@1795687000.dMp0007"
HANDLE = "$ref:"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    (root / "diagram-catalog/diagrams").mkdir(parents=True)  # where the scope is drawn when the diff is read
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, documents.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _recorded(client: TestClient, candidate: dict[str, Any], *operations: dict[str, Any]) -> dict[str, Any]:
    path = f"/api/candidates/{candidate['record']['id']}/operations"
    answer = client.post(path, json={"based_on": candidate["version"], "operations": list(operations)})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _create(artifact_id: str, artifact_type: str, name: str) -> dict[str, Any]:
    return {"op": "create_entity", "artifact_id": artifact_id,
            "fields": {"artifact_type": artifact_type, "name": name, "group": "uncategorized"}}


def _naive(client: TestClient) -> tuple[str, dict[str, Any], str]:
    """An analysis whose naive reads over one model element and creates two more, never drawn."""
    scoped = stable_id(model.artifact_create_entity(
        artifact_type="application-component", name="Reader", dry_run=False,
        repo_root=str(client.root),  # type: ignore[attr-defined]
    )["artifact_id"])
    started = client.post("/api/stress-analyses", json={
        "title": "Stress analysis — ids", "naive": {"name": "Naive", "scope": [scoped]}})
    assert started.status_code == 200, started.text
    body = started.json()
    naive = _recorded(
        client, body["naive_candidate"],
        _create(EXTRACTOR, "application-component", "Text Extractor"), _create(TEXT, "data-object", "Extracted Text"),
        {"op": "add_connection", "source_entity": EXTRACTOR, "connection_type": "archimate-access",
         "target_entity": TEXT},
        {"op": "add_connection", "source_entity": EXTRACTOR, "connection_type": "archimate-serving",
         "target_entity": scoped},
    )
    return body["document"], naive, scoped


def _ticked(client: TestClient, document: str, *components: str) -> None:
    for table, rows in (
        ("stressors", [{"op": "add", "cells": {"stressor": "Scanned drawings arrive", "set": "design"}}]),
        ("incidence", [{"op": "add", "cells": {"stressor": "S1", "component": one, "note": "reads"}}
                       for one in components]),
    ):
        written = client.patch(f"/api/documents/{document}/tables/{table}", json={"rows": rows, "dry_run": False})
        assert written.status_code == 200, written.text


def test_incidence_coupling_and_coverage_name_a_created_element_by_its_id(client: TestClient) -> None:
    document, _naive_answer, scoped = _naive(client)
    _ticked(client, document, EXTRACTOR, f"{scoped}")

    incidence = client.get(f"/api/documents/{document}/incidence").json()
    progress = client.get(f"/api/documents/{document}/progress").json()

    stressor = incidence["stressors"][0]
    assert stressor["missing_elements"] == []
    assert stressor["hits"] == sorted([EXTRACTOR, scoped])
    assert incidence["coupling"] == [{"left": EXTRACTOR, "right": scoped, "count": 1}]
    assert [one["id"] for one in progress["coverage"]["untouched"]] == [TEXT]
    assert HANDLE not in json.dumps(incidence) + json.dumps(progress)


def test_an_adaptation_row_names_its_candidate_as_it_is_stored_and_refuses_one_nothing_stores(
    client: TestClient,
) -> None:
    """Through the write path, whose verification reads a temporary tree beside the repository: the
    candidate an adaptation names is found there, in either spelling, and stored by its full id."""
    document, naive, _scoped = _naive(client)
    adaptation = client.post("/api/candidates", json={"record": {"name": "Adapt", "parent": naive["record"]["id"]}})
    full = adaptation.json()["record"]["id"]
    path = f"/api/documents/{document}/tables"
    client.patch(f"{path}/end-states", json={"rows": [{"op": "add", "cells": {"end_state": "Reads offline"}}],
                                             "dry_run": False}).raise_for_status()

    written = client.patch(f"{path}/adaptations", json={"dry_run": False, "rows": [
        {"op": "add", "cells": {"end_states": ["E1"], "candidate_architecture": stable_id(full)}}]})
    refused = client.patch(f"{path}/adaptations", json={"dry_run": False, "rows": [
        {"op": "add", "cells": {"end_states": ["E1"], "candidate_architecture": "CAND@1700000000.Nope000"}}]})

    assert written.status_code == 200, written.text
    rows = client.get(path).json()
    (adapted,) = next(table for table in rows["tables"] if table["name"] == "adaptations")["rows"]
    assert adapted["values"]["candidate_architecture"] == full
    assert refused.status_code == 400 and "no candidate-architecture CAND@1700000000.Nope000" in refused.text


def test_a_stacked_candidate_edits_connects_and_drops_a_parent_created_element_by_its_id(client: TestClient) -> None:
    _document, naive, scoped = _naive(client)
    adaptation = client.post("/api/candidates", json={"record": {"name": "Adapt", "parent": naive["record"]["id"]}})
    assert adaptation.status_code == 200, adaptation.text

    renamed = _recorded(client, adaptation.json(),
                        {"op": "edit_entity", "artifact_id": f"{TEXT}.extracted-text", "field": "name",
                         "value": "Recognised Text"},
                        {"op": "add_connection", "source_entity": scoped, "connection_type": "archimate-serving",
                         "target_entity": EXTRACTOR})
    answered = client.get(f"/api/candidates/{renamed['record']['id']}/diff")
    assert answered.status_code == 200, answered.text
    diff = answered.json()

    entities = {one["id"]: one["fields"] for one in diff["view"]["entities"]}
    assert entities[TEXT]["name"] == "Recognised Text"
    assert {(one["source_entity"], one["target_entity"]) for one in diff["view"]["connections"]} >= {
        (scoped, EXTRACTOR), (EXTRACTOR, TEXT)}
    assert {item["standing"] for item in diff["standing"]} == {"applies"}
    assert HANDLE not in json.dumps(renamed) + json.dumps(diff)

    dropped = _recorded(client, renamed, {"op": "drop", "artifact_id": TEXT})
    assert [op["op"] for op in dropped["record"]["changes"]["operations"]] == ["add_connection"]
