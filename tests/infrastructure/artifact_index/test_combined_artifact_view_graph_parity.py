"""Parity tests for CombinedArtifactView's RelationshipGraph methods.

Every method here operates on connections, which per the GRF guarantee never span
repos — so the "semantically correct" result is always the plain concat/merge/sum of
each canonical instance's own (independently computed, not reused from production
merge helpers) result.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

from ._combined_fixtures import ENG_B, ENG_D, ENT_A, build_two_repo_fixture


def test_candidate_connections_and_list_connections_by_types(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    types = frozenset({"archimate-association"})
    expected_by_types = sorted(
        [*eng_only.list_connections_by_types(types), *ent_only.list_connections_by_types(types)],
        key=lambda r: r.artifact_id,
    )
    assert combined.list_connections_by_types(types) == expected_by_types

    expected_for_engB = sorted(
        [
            *eng_only.list_connections_by_types_for_entities(types, [ENG_B]),
            *ent_only.list_connections_by_types_for_entities(types, [ENG_B]),
        ],
        key=lambda r: r.artifact_id,
    )
    assert combined.list_connections_by_types_for_entities(types, [ENG_B]) == expected_for_engB

    expected_candidates = sorted(
        [
            *eng_only.candidate_connections_for_entities([ENG_B, ENG_D]),
            *ent_only.candidate_connections_for_entities([ENG_B, ENG_D]),
        ],
        key=lambda r: r["artifact_id"],
    )
    assert combined.candidate_connections_for_entities([ENG_B, ENG_D]) == expected_candidates


def test_connection_counts_variants_sum_across_repos(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    eng_counts, ent_counts = eng_only.connection_counts(), ent_only.connection_counts()
    expected_counts = dict(eng_counts)
    for entity_id, counts in ent_counts.items():
        prior = expected_counts.get(entity_id, (0, 0, 0))
        expected_counts[entity_id] = tuple(a + b for a, b in zip(prior, counts))
    assert combined.connection_counts() == expected_counts

    # No overlap between engagement and enterprise entity ids in this fixture, so the
    # combined per-entity count is exactly whichever side actually owns that entity.
    assert combined.connection_counts_for(ENG_B) == eng_only.connection_counts_for(ENG_B)
    assert combined.connection_counts_for(ENT_A) == ent_only.connection_counts_for(ENT_A)

    expected_for_entities = dict(eng_only.connection_counts_for_entities([ENG_B, ENT_A]))
    expected_for_entities.update(ent_only.connection_counts_for_entities([ENG_B, ENT_A]))
    assert combined.connection_counts_for_entities([ENG_B, ENT_A]) == expected_for_entities


def test_find_connections_for_and_find_neighbors(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert combined.find_connections_for(ENG_B) == eng_only.find_connections_for(ENG_B)
    assert combined.find_connections_for(ENT_A) == ent_only.find_connections_for(ENT_A)

    eng_neighbors = eng_only.find_neighbors(ENG_B, max_hops=1)
    ent_neighbors = ent_only.find_neighbors(ENG_B, max_hops=1)
    expected_neighbors = {key: set(value) for key, value in eng_neighbors.items()}
    for key, value in ent_neighbors.items():
        expected_neighbors.setdefault(key, set()).update(value)
    assert combined.find_neighbors(ENG_B, max_hops=1) == expected_neighbors


def test_diagrams_referencing_artifact_and_grf_references_to_entity(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    # ENT_A is referenced by an enterprise diagram *and* has an engagement-side GRF proxy —
    # exercises both merge directions with genuinely non-empty results on each side.
    expected_diagrams = sorted(
        [*eng_only.diagrams_referencing_artifact(ENT_A), *ent_only.diagrams_referencing_artifact(ENT_A)],
        key=lambda r: r.artifact_id,
    )
    assert combined.diagrams_referencing_artifact(ENT_A) == expected_diagrams

    expected_grf = sorted(
        [*eng_only.grf_references_to_entity(ENT_A), *ent_only.grf_references_to_entity(ENT_A)],
        key=lambda r: r.artifact_id,
    )
    assert combined.grf_references_to_entity(ENT_A) == expected_grf
    assert [r.artifact_id for r in combined.grf_references_to_entity(ENT_A)] == ["GRF@1.proxy.proxy"]
