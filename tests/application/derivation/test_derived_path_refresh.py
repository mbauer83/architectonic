"""Reconstruction-based staleness for accepted witness paths: broken (a chain link is
deleted), no-longer-derives (a rule change breaks composition), and certainty/type drift
(the chain still derives, but differently than what was accepted) — each reported as a
distinct, actionable stale-selection entry, never silently redrawn or dropped."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.application.derivation.derived_relationships import SPEC, default_selection, evaluate_candidates
from src.application.derivation.path_staleness import classify_accepted_path_staleness
from src.application.derivation.refresh import compute_derivation_diff
from src.application.derivation.strategy_registry import DerivationStrategyCatalogBuilder
from src.domain.viewpoints.view_derivations import (
    DerivationSelection,
    PathProvenance,
    SourceModelSnapshot,
    ViewDerivation,
)
from tests.fixtures.viewpoints.derivation_examples import (
    ExampleGraph,
    catalog,
    connection,
    entity,
    financial_application,
)

_CATALOG = catalog()
_HOPS = 3
_MAX_RELATIONSHIPS = 100
_PARAMS: dict[str, object] = {
    "root_entity_ids": ["financial-application"], "direction": "outgoing", "max_hops": _HOPS,
}


def _selection():
    graph = financial_application()
    return default_selection(
        _PARAMS, read_access=graph, catalog=_CATALOG, default_max_hops=_HOPS, max_relationships=_MAX_RELATIONSHIPS
    )


class TestClassifyAcceptedPathStaleness:
    def test_no_selection_yields_empty_report(self) -> None:
        report = classify_accepted_path_staleness(None, read_access=financial_application(), catalog=_CATALOG)
        assert report.stale_paths == frozenset()

    def test_matching_reconstruction_reports_nothing(self) -> None:
        report = classify_accepted_path_staleness(_selection(), read_access=financial_application(), catalog=_CATALOG)
        assert report.stale_paths == frozenset()

    def test_deleted_connection_is_broken(self) -> None:
        graph = financial_application()
        graph.connections = [c for c in graph.connections if c.artifact_id != "assigns-function"]
        report = classify_accepted_path_staleness(_selection(), read_access=graph, catalog=_CATALOG)
        assert report.broken_paths
        assert report.drifted_paths == ()
        assert report.no_longer_derives_paths == ()

    def test_rule_incompatible_type_change_is_no_longer_derives(self) -> None:
        graph = ExampleGraph(
            entities={"a": entity("a", "function"), "b": entity("b", "function"), "c": entity("c", "function")},
            connections=[
                connection("c1", "a", "b", "archimate-association"),
                connection("c2", "b", "c", "archimate-triggering"),
            ],
        )
        selection_with_provenance = _selection_for_path(
            "c1@fwd|c2@fwd", PathProvenance(certainty="certain", connection_type="archimate-triggering")
        )
        report = classify_accepted_path_staleness(selection_with_provenance, read_access=graph, catalog=_CATALOG)
        assert "c1@fwd|c2@fwd" in report.no_longer_derives_paths
        assert report.broken_paths == ()
        assert report.drifted_paths == ()

    def test_certainty_or_type_mismatch_against_provenance_is_drift(self) -> None:
        real_selection = _selection()
        path_key = next(iter(real_selection.included_paths))
        wrong_provenance = replace(
            real_selection,
            path_provenance={
                **real_selection.path_provenance,
                path_key: PathProvenance(certainty="certain", connection_type="archimate-serving"),
            },
        )
        report = classify_accepted_path_staleness(
            wrong_provenance, read_access=financial_application(), catalog=_CATALOG
        )
        assert path_key in report.drifted_paths
        assert report.broken_paths == ()
        assert report.no_longer_derives_paths == ()


def _selection_for_path(path_key: str, provenance: PathProvenance) -> DerivationSelection:
    return DerivationSelection(included_paths=(path_key,), path_provenance={path_key: provenance})


class TestRefreshReportsStalePaths:
    def _strategy_catalog(self, graph):
        builder = DerivationStrategyCatalogBuilder()
        builder.register(
            SPEC,
            lambda params, snapshot, query: evaluate_candidates(
                params, read_access=graph, catalog=_CATALOG, default_max_hops=_HOPS,
                max_relationships=_MAX_RELATIONSHIPS,
            ),
        )
        return builder.build()

    def _diagram_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "diagram.puml"
        path.write_text("@startuml\n@enduml\n", encoding="utf-8")
        return path

    def test_deleting_a_chain_link_makes_refresh_report_the_stale_path(self, tmp_path: Path) -> None:
        selection = _selection()
        graph = financial_application()
        graph.connections = [c for c in graph.connections if c.artifact_id != "assigns-function"]
        vd = ViewDerivation(
            id="d1", strategy="derived_relationships", strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"), parameters=_PARAMS, selection=selection,
        )
        diff = compute_derivation_diff(
            self._diagram_path(tmp_path), {}, vd, graph, self._strategy_catalog(graph), ontology_catalog=_CATALOG
        )
        assert diff.is_empty is False
        assert diff.broken_paths
        assert set(diff.broken_paths) <= set(diff.gone_paths)

    def test_matching_model_yields_empty_diff_via_reconstruction(self, tmp_path: Path) -> None:
        selection = _selection()
        graph = financial_application()
        vd = ViewDerivation(
            id="d1", strategy="derived_relationships", strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"), parameters=_PARAMS, selection=selection,
        )
        diff = compute_derivation_diff(
            self._diagram_path(tmp_path), {}, vd, graph, self._strategy_catalog(graph), ontology_catalog=_CATALOG
        )
        assert diff.is_empty is True
