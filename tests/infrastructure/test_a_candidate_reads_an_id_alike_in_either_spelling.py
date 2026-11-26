"""Every id the candidate and analysis surfaces take is one identity in either of its spellings.

An artifact id is written short (`PREFIX@epoch.random`) or with its slug; the two are one identity
(`canonical_entity_key`, the id form's owner). These surfaces compared the strings, so each read
below answered something else for the short form than for the slugged one: a 404, an overlap check
that saw nothing, a connection to an entity the candidate creates refused as joining nothing, an
incidence hit reported as missing, a residuality nobody had judged, and an occurrence stored but never
drawn. Each case is stated over both spellings, so the pair is what is tested, not one of them.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.diagram_occurrences import occurrence_entities
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as model
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, documents, state, stress_evaluation
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

SPELLINGS = pytest.mark.parametrize("spelled", [stable_id, lambda full: full], ids=["short", "slugged"])


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, documents.router, stress_evaluation.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _root(client: TestClient) -> Path:
    return client.root  # type: ignore[attr-defined,no-any-return]


def _entity(client: TestClient, name: str) -> str:
    made = model.artifact_create_entity(
        artifact_type="application-component", name=name, dry_run=False, repo_root=str(_root(client)),
    )
    assert made["wrote"], made
    return str(made["artifact_id"])


def _created(client: TestClient, record: dict[str, Any]) -> dict[str, Any]:
    created = client.post("/api/candidates", json={"record": record})
    assert created.status_code == 200, created.text
    return dict(created.json())


def _record(client: TestClient, ref: str, operation: dict[str, Any]) -> dict[str, Any]:
    version = client.get(f"/api/candidates/{ref}").json()["version"]
    recorded = client.post(f"/api/candidates/{ref}/operations", json={"based_on": version, "operations": [operation]})
    assert recorded.status_code == 200, recorded.text
    return dict(recorded.json())


def _offer(client: TestClient, ref: str) -> None:
    version = client.get(f"/api/candidates/{ref}").json()["version"]
    offered = client.patch(f"/api/candidates/{ref}", json={"based_on": version, "patch": {"state": "candidate"}})
    assert offered.status_code == 200, offered.text


@SPELLINGS
def test_a_candidate_is_read_by_either_spelling_of_its_id_on_both_surfaces(client: TestClient, spelled) -> None:
    full = _created(client, {"name": "Read me"})["record"]["id"]

    read = client.get(f"/api/candidates/{spelled(full)}")
    standing = client.get(f"/api/candidates/{spelled(full)}/standing")

    assert read.status_code == 200, read.text
    assert read.json()["record"]["id"] == full
    assert standing.json()["candidate"] == full
    assert mcp.candidate_read(spelled(full), repo_root=str(_root(client)))["record"]["id"] == full


@SPELLINGS
def test_two_candidates_naming_one_entity_in_two_spellings_overlap(client: TestClient, spelled) -> None:
    entity = _entity(client, "Module Catalog")
    first = _created(client, {"name": "Rename one way"})["record"]["id"]
    second = _created(client, {"name": "Rename the other"})["record"]["id"]
    _record(client, first, {"op": "edit_entity", "artifact_id": entity, "field": "name", "value": "Registry"})
    _record(client, second, {"op": "edit_entity", "artifact_id": spelled(entity), "field": "name", "value": "Index"})
    _offer(client, first)
    _offer(client, second)

    checked = client.post("/api/candidate-checks", json={"candidates": [first, second]})

    assert checked.status_code == 200, checked.text
    assert [overlap["kind"] for overlap in checked.json()["overlaps"]] == ["same-key"]


@SPELLINGS
def test_a_connection_to_an_entity_the_candidate_creates_finds_it_in_either_spelling(
    client: TestClient, spelled,
) -> None:
    source = _entity(client, "Module Catalog")
    ref = _created(client, {"name": "Add a cache"})["record"]["id"]
    chosen = "APP@1795600000.abcdEF.catalog-cache"
    _record(client, ref, {"op": "create_entity", "artifact_id": chosen, "fields": {
        "name": "Catalog Cache", "artifact_type": "application-component", "group": "uncategorized"}})
    _record(client, ref, {"op": "add_connection", "source_entity": source,
                          "connection_type": "archimate-serving", "target_entity": spelled(chosen)})

    standing = client.get(f"/api/candidates/{ref}/standing").json()["standing"]

    assert {item["standing"] for item in standing} == {"applies"}, standing


@SPELLINGS
def test_an_incidence_hit_and_a_verdict_name_one_element_and_one_candidate_in_either_spelling(
    client: TestClient, spelled,
) -> None:
    entity = _entity(client, "PlantUML Renderer")
    started = client.post("/api/stress-analyses", json={"title": "Either spelling", "naive": {
        "name": "Naive", "scope": [entity]}})
    assert started.status_code == 200, started.text
    document = started.json()["document"]
    naive = started.json()["naive_candidate"]["record"]["id"]
    adapted = _created(client, {"name": "Bundled renderer", "parent": naive})["record"]["id"]

    def rows(table: str, cells: list[dict[str, object]]) -> None:
        written = client.patch(f"/api/documents/{document}/tables/{table}", json={
            "rows": [{"op": "add", "cells": one} for one in cells], "dry_run": False})
        assert written.status_code == 200, written.text

    rows("stressors", [{"stressor": "Jar missing", "set": "design"}, {"stressor": "Jar gone", "set": "test"}])
    rows("incidence", [{"stressor": "S1", "component": spelled(entity), "note": "renders nothing"}])
    rows("survival", [
        {"stressor": "S2", "architecture": "naive", "verdict": "fails", "usable": True},
        {"stressor": "S2", "architecture": spelled(adapted), "verdict": "survives", "usable": True},
    ])

    incidence = client.get(f"/api/stress-analyses/{document}/incidence").json()
    residuality = client.get(f"/api/candidates/{stable_id(adapted)}/residuality").json()
    test_set = client.get(f"/api/stress-analyses/{document}/test-set").json()
    judged = [one["architecture"] for one in test_set["architectures"]]

    assert incidence["stressors"][0]["missing_elements"] == []
    assert incidence["stressors"][0]["hits"] == [stable_id(entity)]
    assert judged == ["naive", adapted]
    assert [one["residuality"] for one in residuality["analyses"]] == [1.0]


@SPELLINGS
def test_an_occurrence_draws_its_backing_entity_named_in_either_spelling(spelled) -> None:
    full = "APP@1777293136.yaxrWl.plantuml-renderer"
    entity = EntityRecord(
        artifact_id=full, artifact_type="application-component", name="PlantUML Renderer", version="0.1.0",
        status="active", domain="application", subdomain="application-component", path=Path("x.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label="", display_alias="APP_yaxrWl",
    )

    drawn = occurrence_entities({"occurrence": [{"id": "again", "backing_entity_id": spelled(full)}]}, {full: entity})

    assert [(one.display_alias, one.host_diagram_id) for one in drawn] == [("APP_yaxrWl__2", "again")]
