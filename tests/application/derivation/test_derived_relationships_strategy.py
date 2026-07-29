"""Tests for the ``derived_relationships`` view-derivation strategy: candidate-set shape
over the B6-verified worked-example fixtures (reusing their known outcomes rather than
hand-deriving new expectations), certain/potential acceptance defaults, and a real
generate-review-refresh cycle including staleness after a parameter change."""

from __future__ import annotations

from pathlib import Path

from src.application.derivation.derived_relationships import SPEC, default_selection, evaluate_candidates
from src.application.derivation.refresh import compute_derivation_diff
from src.application.derivation.strategy_registry import DerivationStrategyCatalogBuilder
from src.domain.viewpoints.view_derivations import SourceModelSnapshot, ViewDerivation
from tests.fixtures.viewpoints.derivation_examples import catalog, financial_application, hosting_suite

_CATALOG = catalog()
_DEFAULT_HOPS = 4
_MAX_RELATIONSHIPS = 100


def _candidates(params: dict[str, object], graph):
    return evaluate_candidates(
        params, read_access=graph, catalog=_CATALOG, default_max_hops=_DEFAULT_HOPS,
        max_relationships=_MAX_RELATIONSHIPS,
    )


def _selection(params: dict[str, object], graph):
    return default_selection(
        params, read_access=graph, catalog=_CATALOG, default_max_hops=_DEFAULT_HOPS,
        max_relationships=_MAX_RELATIONSHIPS,
    )


class TestCandidateSetShape:
    def test_reachable_entities_include_every_witness_chain_hop(self) -> None:
        graph = financial_application()
        candidates = _candidates(
            {"root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 3}, graph
        )
        # The B-3 worked example: assignment + aggregation compose into an
        # indirect assignment, and the full chain composes into a realization —
        # payment-function is an intermediate witness-chain hop, not a derived
        # relationship endpoint, but must still be reachable for the connections to
        # be displayable at all.
        assert candidates.entity_ids == {
            "financial-application", "payment-function", "payment-subfunction", "payment-service",
        }
        assert candidates.connection_ids == {"assigns-function", "aggregates-subfunction", "realizes-service"}

    def test_derived_relationships_flow_through_as_witness_paths_never_as_ids(self) -> None:
        graph = financial_application()
        candidates = _candidates(
            {"root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 3}, graph
        )
        assert all(not cid.startswith("derived::") for cid in candidates.connection_ids)
        assert len(candidates.paths) == 2  # the indirect assignment and the realization


class TestAcceptanceDefaults:
    def test_potential_candidates_excluded_until_accepted(self) -> None:
        graph = hosting_suite()
        params: dict[str, object] = {
            "root_entity_ids": ["database-hosting", "website-hosting"],
            "direction": "outgoing",
            "include_potential": True,
            "max_hops": 2,
        }
        selection = _selection(params, graph)
        # The B-12 worked example: all four serving candidates are potential —
        # none certain — so every one must start pre-excluded.
        assert selection.included_paths == ()
        assert len(selection.excluded_paths) == 4

    def test_certain_candidates_pre_included(self) -> None:
        graph = financial_application()
        params: dict[str, object] = {
            "root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 3,
        }
        selection = _selection(params, graph)
        assert len(selection.included_paths) == 2
        assert selection.excluded_paths == ()
        for path_key in selection.included_paths:
            assert selection.path_provenance[path_key].certainty == "certain"


class TestGenerateReviewRefreshCycle:
    def _diagram_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "diagram.puml"
        path.write_text("@startuml\n@enduml\n", encoding="utf-8")
        return path

    def _strategy_catalog(self, graph):
        builder = DerivationStrategyCatalogBuilder()
        builder.register(SPEC, lambda params, snapshot, query: _candidates(params, graph))
        return builder.build()

    def test_fully_accepted_selection_yields_empty_refresh_diff(self, tmp_path: Path) -> None:
        graph = financial_application()
        params: dict[str, object] = {
            "root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 3,
        }
        selection = _selection(params, graph)
        vd = ViewDerivation(
            id="d1", strategy="derived_relationships", strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"), parameters=params, selection=selection,
        )
        diff = compute_derivation_diff(self._diagram_path(tmp_path), {}, vd, graph, self._strategy_catalog(graph))
        assert diff.is_empty is True

    def test_narrowing_max_hops_after_seeding_yields_non_empty_diff(self, tmp_path: Path) -> None:
        graph = financial_application()
        wide_params: dict[str, object] = {
            "root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 3,
        }
        selection = _selection(wide_params, graph)
        vd = ViewDerivation(
            id="d1", strategy="derived_relationships", strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"), parameters=wide_params,
            selection=selection,
        )
        diagram_path = self._diagram_path(tmp_path)
        diff = compute_derivation_diff(diagram_path, {}, vd, graph, self._strategy_catalog(graph))
        assert diff.is_empty is True

        # A narrower re-generation (standing in for a definition/parameter change) no
        # longer reaches the realization two hops away — refresh reports it gone.
        narrow_params: dict[str, object] = {
            "root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": 1,
        }
        narrow_vd = ViewDerivation(
            id="d1", strategy="derived_relationships", strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"),
            parameters=narrow_params,
            selection=selection,
        )
        stale_diff = compute_derivation_diff(diagram_path, {}, narrow_vd, graph, self._strategy_catalog(graph))
        assert stale_diff.is_empty is False
        assert "payment-service" in stale_diff.gone_entity_ids
