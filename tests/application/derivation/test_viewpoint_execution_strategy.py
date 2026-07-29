"""Tests for the ``viewpoint_execution`` view-derivation strategy: candidate-set shape
(modeled connections by id, derived connections as witness paths, never as synthetic
ids), certain/potential acceptance defaults, and a real generate-review-refresh cycle
including staleness after a definition version bump."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.application.derivation.viewpoint_execution as ve
from src.application.derivation.refresh import compute_derivation_diff
from src.application.derivation.strategy_registry import DerivationStrategyCatalogBuilder
from src.application.viewpoints.execution_result import (
    ConnectionItemSummary,
    EntityItemSummary,
    ViewpointExecutionResult,
)
from src.domain.viewpoints.view_derivations import DerivationSelection, SourceModelSnapshot, ViewDerivation
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoints import ViewpointCatalog

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset(),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={},
)


class _NullReadAccess:
    def get_entity(self, artifact_id: str):
        return None

    def get_connection(self, artifact_id: str):
        return None

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return []

    def entity_ids(self) -> set[str]:
        return set()

    def enterprise_entity_ids(self) -> set[str]:
        return set()

    def engagement_entity_ids(self) -> set[str]:
        return set()

    def connection_ids(self) -> set[str]:
        return set()

    def enterprise_connection_ids(self) -> set[str]:
        return set()

    def engagement_connection_ids(self) -> set[str]:
        return set()


def _entity_summary(entity_id: str) -> EntityItemSummary:
    return EntityItemSummary(
        id=entity_id, name=entity_id, type="application-component", specialization_slugs=(),
        domain="application", group="uncategorized", membership="primary",
    )


def _modeled_connection(conn_id: str, source: str, target: str) -> ConnectionItemSummary:
    return ConnectionItemSummary(id=conn_id, type="archimate-serving", source=source, target=target)


def _derived_connection(path_key: str, source: str, target: str, *, certainty: str) -> ConnectionItemSummary:
    return ConnectionItemSummary(
        id=f"derived::archimate-realization::{path_key}",
        type="archimate-realization",
        source=source,
        target=target,
        certainty=certainty,  # type: ignore[arg-type]
        hops=2,
        via_connection_ids=tuple(part.split("@")[0] for part in path_key.split("|")),
    )


def _result(entities: tuple[EntityItemSummary, ...], connections: tuple[ConnectionItemSummary, ...]):
    return ViewpointExecutionResult(
        slug="impact",
        version=1,
        query_schema=1,
        repo_scope="both",
        executed_at="2026-07-13T00:00:00Z",
        index_generation=None,
        entity_ids=tuple(e.id for e in entities),
        connection_ids=tuple(c.id for c in connections),
        entities=entities,
        connections=connections,
        total_entity_count=len(entities),
        returned_entity_count=len(entities),
        total_connection_count=len(connections),
        returned_connection_count=len(connections),
        truncated=False,
        entity_limit=1000,
        matrix_axes=None,
        warnings=(),
        duration_ms=1.0,
        query_summary="test",
    )


def _evaluate_candidates(params: dict[str, object]) -> ve.CandidateSet:
    return ve.evaluate_candidates(
        params,
        catalog=ViewpointCatalog.empty(),
        read_access=_NullReadAccess(),
        registries=_REGISTRIES,
        max_entities=1000,
        default_limit=100,
        timeout_seconds=5.0,
    )


def _default_selection(params: dict[str, object]) -> DerivationSelection:
    return ve.default_selection(
        params,
        catalog=ViewpointCatalog.empty(),
        read_access=_NullReadAccess(),
        registries=_REGISTRIES,
        max_entities=1000,
        default_limit=100,
        timeout_seconds=5.0,
    )


def _call_evaluate_candidates_and_default_selection(monkeypatch: pytest.MonkeyPatch, result: ViewpointExecutionResult):
    monkeypatch.setattr(ve, "evaluate_viewpoint", lambda *a, **kw: result)
    params: dict[str, object] = {"slug": "impact"}
    return _evaluate_candidates(params), _default_selection(params)


class TestCandidateSetShape:
    def test_modeled_connections_flow_through_by_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entities = (_entity_summary("E1"), _entity_summary("E2"))
        connections = (_modeled_connection("C1", "E1", "E2"),)
        candidates, _ = _call_evaluate_candidates_and_default_selection(monkeypatch, _result(entities, connections))
        assert candidates.entity_ids == {"E1", "E2"}
        assert candidates.connection_ids == {"C1"}
        assert candidates.paths == frozenset()

    def test_derived_connections_flow_through_as_witness_paths_never_as_ids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entities = (_entity_summary("E1"), _entity_summary("E2"))
        connections = (_derived_connection("C1@fwd|C2@fwd", "E1", "E2", certainty="certain"),)
        candidates, _ = _call_evaluate_candidates_and_default_selection(monkeypatch, _result(entities, connections))
        assert candidates.connection_ids == frozenset()
        assert candidates.paths == {"C1@fwd|C2@fwd"}
        assert all(not cid.startswith("derived::") for cid in candidates.connection_ids)


class TestAcceptanceDefaults:
    def test_certain_pre_included_potential_pre_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entities = (_entity_summary("E1"), _entity_summary("E2"), _entity_summary("E3"))
        connections = (
            _modeled_connection("C1", "E1", "E2"),
            _derived_connection("C1@fwd|C2@fwd", "E1", "E2", certainty="certain"),
            _derived_connection("C3@fwd", "E1", "E3", certainty="potential"),
        )
        _, selection = _call_evaluate_candidates_and_default_selection(monkeypatch, _result(entities, connections))
        assert selection.included_entity_ids == ("E1", "E2", "E3")
        assert selection.included_connection_ids == ("C1",)
        assert selection.included_paths == ("C1@fwd|C2@fwd",)
        assert selection.excluded_paths == ("C3@fwd",)
        assert selection.path_provenance["C1@fwd|C2@fwd"].certainty == "certain"
        assert selection.path_provenance["C1@fwd|C2@fwd"].connection_type == "archimate-realization"
        assert selection.path_provenance["C3@fwd"].certainty == "potential"


class TestGenerateReviewRefreshCycle:
    """A real strategy-catalog + compute_derivation_diff cycle: seeding a ViewDerivation's
    selection from ``default_selection`` yields an empty refresh diff (idempotence), and
    a subsequent parameter change (standing in for a definition version bump) yields a
    non-empty diff — staleness reported by the existing refresh flow."""

    def _diagram_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "diagram.puml"
        path.write_text("@startuml\n@enduml\n", encoding="utf-8")
        return path

    def test_fully_accepted_selection_yields_empty_refresh_diff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entities = (_entity_summary("E1"), _entity_summary("E2"))
        connections = (
            _modeled_connection("C1", "E1", "E2"),
            _derived_connection("C1@fwd|C2@fwd", "E1", "E2", certainty="certain"),
        )
        result = _result(entities, connections)
        monkeypatch.setattr(ve, "evaluate_viewpoint", lambda *a, **kw: result)

        builder = DerivationStrategyCatalogBuilder()
        builder.register(ve.SPEC, lambda params, snapshot, query: _evaluate_candidates(params))
        strategy_catalog = builder.build()

        selection = _default_selection({"slug": "impact"})
        vd = ViewDerivation(
            id="d1",
            strategy="viewpoint_execution",
            strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"),
            parameters={"slug": "impact"},
            selection=selection,
        )
        diff = compute_derivation_diff(self._diagram_path(tmp_path), {}, vd, _NullReadAccess(), strategy_catalog)
        assert diff.is_empty is True

    def test_definition_change_after_seeding_yields_non_empty_diff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = _result((_entity_summary("E1"),), ())
        monkeypatch.setattr(ve, "evaluate_viewpoint", lambda *a, **kw: original)

        builder = DerivationStrategyCatalogBuilder()
        builder.register(ve.SPEC, lambda params, snapshot, query: _evaluate_candidates(params))
        strategy_catalog = builder.build()

        selection = DerivationSelection(included_entity_ids=("E1",))
        vd = ViewDerivation(
            id="d1",
            strategy="viewpoint_execution",
            strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"),
            parameters={"slug": "impact"},
            selection=selection,
        )
        diagram_path = self._diagram_path(tmp_path)
        diff = compute_derivation_diff(diagram_path, {}, vd, _NullReadAccess(), strategy_catalog)
        assert diff.is_empty is True

        # A definition version bump changes what the same slug now evaluates to.
        bumped = _result((_entity_summary("E1"), _entity_summary("E2")), ())
        monkeypatch.setattr(ve, "evaluate_viewpoint", lambda *a, **kw: bumped)
        stale_diff = compute_derivation_diff(diagram_path, {}, vd, _NullReadAccess(), strategy_catalog)
        assert stale_diff.is_empty is False
        assert stale_diff.new_entity_ids == ["E2"]
