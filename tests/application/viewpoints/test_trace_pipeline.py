"""Post-projection pipeline: row-verdict composition (worst of motivation +
overall_realization), not-applicable exclusion, gaps_only filter, gaps-first global sort, and
limit-after-materialization (a gap beyond the page limit still counts in total_rows)."""

from __future__ import annotations

from src.application.viewpoints.trace_index import build_trace_graph_index
from src.application.viewpoints.trace_pipeline import evaluate_trace_table
from src.application.viewpoints.trace_realizers import eligible_realizer_types
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.domain.viewpoints.viewpoint_trace_patterns import (
    BranchesRef,
    DerivedReachabilityLeaf,
    InlineBranches,
    NamedBranchEdge,
    NoneLeaf,
    RegistryEndpoint,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REF = frozenset({"archimate-realization"})
_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=2.0)

_MOTIVATION = TracePattern(
    name="motivation", applies_to=("goal", "outcome"),
    branches=InlineBranches((
        NamedBranchEdge("g2o", StoredEdge("archimate-realization", "incoming", "outcome")),
        NamedBranchEdge("o2r", StoredEdge("archimate-realization", "incoming", "requirement")),
    )),
    leaf=NoneLeaf(),
)
_OVERALL = TracePattern(
    name="overall_realization", applies_to=("goal", "outcome", "requirement"), branches=BranchesRef("motivation"),
    leaf=DerivedReachabilityLeaf("archimate-realization", RegistryEndpoint("permitted-realizers-of-requirement")),
)
_PATTERNS = TracePatternSet((_MOTIVATION, _OVERALL))
_TYPE = {"GOL": "goal", "OUT": "outcome", "REQ": "requirement", "APP": "application-component"}


def _e(eid: str, name: str | None = None):
    kind = _TYPE[eid.split("@")[0]]
    domain = "application" if kind == "application-component" else "motivation"
    return entity(artifact_id=eid, artifact_type=kind, domain=domain, status="active", name=name or eid)


def _rz(cid: str, source: str, target: str):
    return connection(artifact_id=cid, source=source, target=target, conn_type="archimate-realization")


def _table(entities, connections, row_ids, **kw):
    store = Store(entities={e.artifact_id: e for e in entities}, connections=connections)
    index = build_trace_graph_index(
        store, get_module_registry(), referenced_connection_types=_REF, requirement_type="requirement", bounds=_BOUNDS
    )
    return evaluate_trace_table(
        tuple(row_ids), patterns=_PATTERNS, index=index,
        eligible=eligible_realizer_types(get_module_registry()), **kw,
    )


def _complete():
    # GOL@1 fully realized (pass); GOL@2 missing outcome (gap).
    entities = [_e("GOL@1", "Alpha"), _e("OUT@1"), _e("REQ@1"), _e("APP@1"), _e("GOL@2", "Beta")]
    connections = [_rz("r1", "OUT@1", "GOL@1"), _rz("r2", "REQ@1", "OUT@1"), _rz("r3", "APP@1", "REQ@1")]
    return entities, connections


class TestRowVerdictAndFiltering:
    def test_gap_and_pass_rows_present_without_filter(self) -> None:
        entities, connections = _complete()
        table = _table(entities, connections, ["GOL@1", "GOL@2"])
        verdicts = {row.entity_id: row.verdict for row in table.rows}
        assert verdicts == {"GOL@1": "pass", "GOL@2": "gap"}

    def test_gaps_only_keeps_only_gaps(self) -> None:
        entities, connections = _complete()
        table = _table(entities, connections, ["GOL@1", "GOL@2"], gaps_only=True)
        assert [row.entity_id for row in table.rows] == ["GOL@2"]

    def test_not_applicable_rows_excluded(self) -> None:
        # A lone application-component matches no pattern's applies_to → not_applicable → dropped.
        entities, connections = _complete()
        table = _table(entities, connections, ["GOL@1", "APP@1"])
        assert [row.entity_id for row in table.rows] == ["GOL@1"]
        assert table.total_rows == 1


class TestSortAndLimit:
    def test_gaps_sort_before_passes(self) -> None:
        entities, connections = _complete()
        table = _table(entities, connections, ["GOL@1", "GOL@2"])
        assert [row.verdict for row in table.rows] == ["gap", "pass"]

    def test_tie_broken_by_type_then_name(self) -> None:
        # Two gap goals; sorted by name (Alpha before Beta) since verdict + type tie.
        entities = [_e("GOL@1", "Beta"), _e("GOL@2", "Alpha")]
        table = _table(entities, [], ["GOL@1", "GOL@2"])
        assert [row.name for row in table.rows] == ["Alpha", "Beta"]

    def test_limit_after_materialization_counts_all_in_total(self) -> None:
        entities = [_e("GOL@1", "A"), _e("GOL@2", "B"), _e("GOL@3", "C")]
        table = _table(entities, [], ["GOL@1", "GOL@2", "GOL@3"], gaps_only=True, limit=2)
        assert table.returned_rows == 2
        assert table.total_rows == 3  # the third gap still counted despite the page limit
        assert table.truncated is True
