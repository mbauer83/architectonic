"""Parity tests for CombinedArtifactView's ArtifactSearch listing/scope methods."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

from ._combined_fixtures import ENG_B, ENT_A, build_two_repo_fixture


def test_list_connections_diagrams_documents_artifacts_are_globally_sorted(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    expected_connections = sorted(
        [*eng_only.list_connections(), *ent_only.list_connections()], key=lambda r: r.artifact_id
    )
    assert combined.list_connections() == expected_connections

    expected_diagrams = sorted([*eng_only.list_diagrams(), *ent_only.list_diagrams()], key=lambda r: r.artifact_id)
    assert combined.list_diagrams() == expected_diagrams

    expected_documents = sorted([*eng_only.list_documents(), *ent_only.list_documents()], key=lambda r: r.artifact_id)
    assert combined.list_documents() == expected_documents

    kwargs = {
        "include_entities": True,
        "include_connections": True,
        "include_diagrams": True,
        "include_documents": True,
    }
    expected_artifacts = sorted(
        [*eng_only.list_artifacts(**kwargs), *ent_only.list_artifacts(**kwargs)], key=lambda r: r.artifact_id
    )
    assert combined.list_artifacts(**kwargs) == expected_artifacts


def test_find_entity_by_workspace_id_respects_engagement_and_enterprise_scope(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    eng_hit = combined.find_entity_by_workspace_id(ENG_B, scope="engagement")
    assert eng_hit is not None and eng_hit.artifact_id == ENG_B
    assert combined.find_entity_by_workspace_id(ENT_A, scope="engagement") is None

    ent_hit = combined.find_entity_by_workspace_id(ENT_A, scope="enterprise")
    assert ent_hit is not None and ent_hit.artifact_id == ENT_A
    assert combined.find_entity_by_workspace_id(ENG_B, scope="enterprise") is None

    both_eng = combined.find_entity_by_workspace_id(ENG_B, scope="both")
    both_ent = combined.find_entity_by_workspace_id(ENT_A, scope="both")
    assert both_eng is not None and both_eng.artifact_id == ENG_B
    assert both_ent is not None and both_ent.artifact_id == ENT_A


def test_scope_for_path_and_scope_of_entity_and_connection(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert combined.scope_of_entity(ENG_B) == "engagement"
    assert combined.scope_of_entity(ENT_A) == "enterprise"
    assert combined.scope_of_entity("REQ@9.nope.nope") == "unknown"

    eng_conn_id = eng_only.list_connections()[0].artifact_id
    ent_conn_id = ent_only.list_connections()[0].artifact_id
    assert combined.scope_of_connection(eng_conn_id) == "engagement"
    assert combined.scope_of_connection(ent_conn_id) == "enterprise"

    eng_entity_path = engagement / "model" / "motivation" / "requirement" / f"{ENG_B}.md"
    ent_entity_path = enterprise / "model" / "motivation" / "requirement" / f"{ENT_A}.md"
    assert combined.scope_for_path(eng_entity_path) == "engagement"
    assert combined.scope_for_path(ent_entity_path) == "enterprise"


def test_entity_and_connection_status_and_id_sets(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert combined.entity_status(ENG_B) == "draft"
    assert combined.entity_status(ENT_A) == "draft"
    assert combined.entity_status("REQ@9.nope.nope") is None

    eng_conn_id = eng_only.list_connections()[0].artifact_id
    assert combined.connection_status(eng_conn_id) == "draft"

    assert combined.entity_statuses() == {**ent_only.entity_statuses(), **eng_only.entity_statuses()}

    assert combined.entity_ids() == eng_only.entity_ids() | ent_only.entity_ids()
    assert combined.connection_ids() == eng_only.connection_ids() | ent_only.connection_ids()
    assert combined.engagement_entity_ids() == eng_only.entity_ids()
    assert combined.enterprise_entity_ids() == ent_only.entity_ids()
    assert combined.engagement_connection_ids() == eng_only.connection_ids()
    assert combined.enterprise_connection_ids() == ent_only.connection_ids()
    assert combined.enterprise_document_ids() == ent_only.enterprise_document_ids()
    assert combined.enterprise_diagram_ids() == ent_only.enterprise_diagram_ids()
