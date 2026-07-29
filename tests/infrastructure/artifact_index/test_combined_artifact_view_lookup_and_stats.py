"""Parity tests for CombinedArtifactView's ArtifactLookup fallback methods and stats()."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

from ._combined_fixtures import ENG_B, ENT_A, build_two_repo_fixture


def test_get_entity_falls_back_from_engagement_to_enterprise(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    eng_entity = combined.get_entity(ENG_B)
    ent_entity = combined.get_entity(ENT_A)
    assert eng_entity is not None and eng_entity.name == "Engagement Beta"
    assert ent_entity is not None and ent_entity.name == "Enterprise Alpha"
    assert combined.get_entity("REQ@9.nope.nope") is None


def test_get_connection_get_diagram_get_document_fall_back(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    eng_conn_id = eng_only.list_connections()[0].artifact_id
    ent_conn_id = ent_only.list_connections()[0].artifact_id
    assert combined.get_connection(eng_conn_id) == eng_only.get_connection(eng_conn_id)
    assert combined.get_connection(ent_conn_id) == ent_only.get_connection(ent_conn_id)

    eng_diag_id = eng_only.list_diagrams()[0].artifact_id
    ent_diag_id = ent_only.list_diagrams()[0].artifact_id
    assert combined.get_diagram(eng_diag_id) == eng_only.get_diagram(eng_diag_id)
    assert combined.get_diagram(ent_diag_id) == ent_only.get_diagram(ent_diag_id)

    eng_doc_id = eng_only.list_documents()[0].artifact_id
    ent_doc_id = ent_only.list_documents()[0].artifact_id
    assert combined.get_document(eng_doc_id) == eng_only.get_document(eng_doc_id)
    assert combined.get_document(ent_doc_id) == ent_only.get_document(ent_doc_id)


def test_read_artifact_summarize_artifact_find_file_by_id_fall_back(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert combined.read_artifact(ENG_B) is not None
    assert combined.read_artifact(ENT_A) is not None
    assert combined.read_artifact("REQ@9.nope.nope") is None

    assert combined.summarize_artifact(ENG_B) is not None
    assert combined.summarize_artifact(ENT_A) is not None

    assert combined.find_file_by_id(ENG_B) == engagement / "model" / "motivation" / "requirement" / f"{ENG_B}.md"
    assert combined.find_file_by_id(ENT_A) == enterprise / "model" / "motivation" / "requirement" / f"{ENT_A}.md"
    assert combined.find_file_by_id("REQ@9.nope.nope") is None


def test_stats_sums_counts_and_merges_by_kind_dicts(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    eng_stats, ent_stats, merged = eng_only.stats(), ent_only.stats(), combined.stats()

    assert merged["entities"] == eng_stats["entities"] + ent_stats["entities"]
    assert merged["connections"] == eng_stats["connections"] + ent_stats["connections"]
    assert merged["diagrams"] == eng_stats["diagrams"] + ent_stats["diagrams"]
    assert merged["documents"] == eng_stats["documents"] + ent_stats["documents"]
    assert merged["entities_by_domain"]["motivation"] == (
        eng_stats["entities_by_domain"]["motivation"] + ent_stats["entities_by_domain"]["motivation"]
    )
    # "common" (the GRF proxy) only exists on the engagement side — must survive the merge
    # untouched, not be dropped or overwritten by the enterprise side's absent key.
    assert merged["entities_by_domain"]["common"] == eng_stats["entities_by_domain"]["common"]
