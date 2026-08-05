"""End-to-end bridge: a viewpoint whose query declares trace_patterns produces a TraceTable on
the execution result; an ordinary viewpoint does not. Exercises the real evaluate_viewpoint
use case with a full registry snapshot (derivation catalog + budget)."""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_trace_patterns import (
    BranchesRef,
    DerivedReachabilityLeaf,
    InlineBranches,
    NamedBranchEdge,
    NoneLeaf,
    RegistryEndpoint,
    RollupEdge,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointCatalog, ViewpointDefinition
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REGISTRIES = build_registry_snapshot(build_runtime_catalogs(get_module_registry()), [])
_DEFAULTS: dict[str, object] = dict(max_entities=500, default_limit=500, timeout_seconds=30.0, index_generation=None)

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
_TYPE = {"GOL": "goal", "OUT": "outcome", "REQ": "requirement", "APP": "application-component"}


def _e(eid: str):
    kind = _TYPE[eid.split("@")[0]]
    domain = "application" if kind == "application-component" else "motivation"
    return entity(artifact_id=eid, artifact_type=kind, domain=domain, status="active", name=eid)


def _rz(cid: str, source: str, target: str):
    return connection(artifact_id=cid, source=source, target=target, conn_type="archimate-realization")


def _store() -> Store:
    entities = {e.artifact_id: e for e in (_e("GOL@1"), _e("GOL@2"), _e("OUT@1"), _e("REQ@1"), _e("APP@1"))}
    connections = [_rz("r1", "OUT@1", "GOL@1"), _rz("r2", "REQ@1", "OUT@1"), _rz("r3", "APP@1", "REQ@1")]
    return Store(entities=entities, connections=connections)


def _query(**over: object) -> ExecutableViewpointQuery:
    defaults: dict[str, object] = dict(
        entity_criteria=EntityCriteriaGroup(
            children=(AttributeCondition("type", "in", ValueRef(literal=["goal", "outcome", "requirement"])),)
        ),
    )
    defaults.update(over)
    return ExecutableViewpointQuery(**defaults)  # type: ignore[arg-type]


def _run(query: ExecutableViewpointQuery, **params: object):
    definition = ViewpointDefinition(slug="cov", version=1, name="Coverage", query=query, presentation=None)
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug="cov", parameters=params or None),
        catalog=ViewpointCatalog(entries=(definition,)), read_access=_store(), registries=_REGISTRIES, **_DEFAULTS,
    )


class TestTraceBridge:
    def test_trace_patterns_produce_a_trace_table(self) -> None:
        result = _run(_query(trace_patterns=TracePatternSet((_MOTIVATION, _OVERALL))))
        assert result.trace_table is not None
        verdicts = {row.entity_id: row.verdict for row in result.trace_table.rows}
        assert verdicts["GOL@1"] == "pass"
        assert verdicts["GOL@2"] == "gap"

    def test_ordinary_viewpoint_has_no_trace_table(self) -> None:
        assert _run(_query()).trace_table is None

    def test_gaps_only_parameter_filters_rows(self) -> None:
        query = _query(
            trace_patterns=TracePatternSet((_MOTIVATION, _OVERALL)),
            parameters=(QueryParameter("gaps_only", "boolean", required=False, default=False),),
        )
        result = _run(query, gaps_only=True)
        assert result.trace_table is not None
        assert [row.entity_id for row in result.trace_table.rows] == ["GOL@2"]

    def test_gaps_first_ordering(self) -> None:
        result = _run(_query(trace_patterns=TracePatternSet((_MOTIVATION, _OVERALL))))
        assert result.trace_table is not None
        assert result.trace_table.rows[0].verdict == "gap"


#: The same chain with the whole-part edge the shipped `motivation-coverage` viewpoint declares.
_MOTIVATION_WITH_ROLLUP = TracePattern(
    name="motivation", applies_to=("goal", "outcome"),
    branches=InlineBranches((
        NamedBranchEdge("g2o", StoredEdge("archimate-realization", "incoming", "outcome")),
        NamedBranchEdge("o2r", StoredEdge("archimate-realization", "incoming", "requirement")),
    )),
    rollup=RollupEdge("archimate-aggregation", "outgoing"),
    leaf=NoneLeaf(),
)


def _aggregate_store() -> Store:
    """An apex aggregating one covered goal and one bare one — the reported structure."""
    entities = {
        e.artifact_id: e
        for e in (_e("GOL@apex"), _e("GOL@covered"), _e("GOL@bare"), _e("OUT@1"), _e("REQ@1"), _e("APP@1"))
    }
    connections = [
        _rz("r1", "OUT@1", "GOL@covered"),
        _rz("r2", "REQ@1", "OUT@1"),
        # The leaf pattern needs a permitted realizer for the requirement, as `_store` gives it one.
        _rz("r2a", "APP@1", "REQ@1"),
        connection(artifact_id="a1", source="GOL@apex", target="GOL@covered",
                   conn_type="archimate-aggregation"),
        connection(artifact_id="a2", source="GOL@apex", target="GOL@bare",
                   conn_type="archimate-aggregation"),
    ]
    return Store(entities=entities, connections=connections)


def _run_against(store: Store, query: ExecutableViewpointQuery, **params: object):
    definition = ViewpointDefinition(slug="cov", version=1, name="Coverage", query=query, presentation=None)
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug="cov", parameters=params or None),
        catalog=ViewpointCatalog(entries=(definition,)), read_access=store, registries=_REGISTRIES, **_DEFAULTS,
    )


class TestRollupReachesTheIndex:
    """The rollup has to survive the whole path — YAML, index adjacency, enumeration.

    It did not, the first time: `_referenced_connection_types` built the index over branch, shortcut
    and leaf connections only, so `archimate-aggregation` had no adjacency, every constituent lookup
    answered empty, and the construct did nothing at all. Nothing failed — the unit tests each built
    their own index with aggregation in it, and against the real model the apex passed for an
    unrelated reason (a direct realization edge). These execute the real use case instead.
    """

    def test_an_aggregate_is_a_gap_when_a_constituent_is_bare(self) -> None:
        result = _run_against(
            _aggregate_store(), _query(trace_patterns=TracePatternSet((_MOTIVATION_WITH_ROLLUP, _OVERALL)))
        )

        assert result.trace_table is not None
        verdicts = {row.entity_id: row.verdict for row in result.trace_table.rows}
        assert verdicts["GOL@apex"] == "gap", "the bare constituent has to reach the apex"
        assert verdicts["GOL@covered"] == "pass"

    def test_an_aggregate_passes_once_every_constituent_is_covered(self) -> None:
        store = _aggregate_store()
        # Give the bare constituent its own outcome and requirement.
        store.entities["OUT@2"] = _e("OUT@2")
        store.entities["REQ@2"] = _e("REQ@2")
        store.entities["APP@2"] = _e("APP@2")
        store.connections.extend([
            _rz("r3", "OUT@2", "GOL@bare"),
            _rz("r4", "REQ@2", "OUT@2"),
            _rz("r4a", "APP@2", "REQ@2"),
        ])

        result = _run_against(store, _query(trace_patterns=TracePatternSet((_MOTIVATION_WITH_ROLLUP, _OVERALL))))

        assert result.trace_table is not None
        verdicts = {row.entity_id: row.verdict for row in result.trace_table.rows}
        assert verdicts["GOL@apex"] == "pass"

    def test_without_the_rollup_the_same_apex_is_a_missing_outcome_gap(self) -> None:
        """The control: the declaration is what changes the verdict, not the fixture."""
        result = _run_against(
            _aggregate_store(), _query(trace_patterns=TracePatternSet((_MOTIVATION, _OVERALL)))
        )

        assert result.trace_table is not None
        apex = next(row for row in result.trace_table.rows if row.entity_id == "GOL@apex")
        motivation = dict(apex.pattern_results)["motivation"]
        assert apex.verdict == "gap"
        assert [type(o).__name__ for o in motivation.failing_obligations] == ["MissingOutcomeObligation"]


class TestRollupHoldsAtEveryLevel:
    """`realization flows through aggregation at any level` — the leaf side of the same rule.

    An aggregate requirement whose constituents are realized is realized. ArchiMate's derivation
    rules cannot supply it (the aggregation and the realization both point at the part, composing
    along no path), so before the rollup reached this level the row reported `partial_branches`
    against a model that was correct.
    """

    def test_an_aggregate_requirement_passes_on_its_constituents_realizers(self) -> None:
        store = Store(
            entities={x.artifact_id: x for x in (_e("REQ@whole"), _e("REQ@part"), _e("APP@1"))},
            connections=[
                connection(artifact_id="agg", source="REQ@whole", target="REQ@part",
                           conn_type="archimate-aggregation"),
                _rz("rz", "APP@1", "REQ@part"),
            ],
        )
        query = _query(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition("type", "in", ValueRef(literal=["requirement"])),)
            ),
            trace_patterns=TracePatternSet((_MOTIVATION_WITH_ROLLUP, _OVERALL)),
        )

        result = _run_against(store, query)

        assert result.trace_table is not None
        verdicts = {row.entity_id: row.verdict for row in result.trace_table.rows}
        assert verdicts["REQ@whole"] == "pass"
        assert verdicts["REQ@part"] == "pass"

    def test_an_aggregate_requirement_is_a_gap_when_a_constituent_has_no_realizer(self) -> None:
        store = Store(
            entities={x.artifact_id: x for x in (_e("REQ@whole"), _e("REQ@part"), _e("REQ@bare"), _e("APP@1"))},
            connections=[
                connection(artifact_id="agg1", source="REQ@whole", target="REQ@part",
                           conn_type="archimate-aggregation"),
                connection(artifact_id="agg2", source="REQ@whole", target="REQ@bare",
                           conn_type="archimate-aggregation"),
                _rz("rz", "APP@1", "REQ@part"),
            ],
        )
        query = _query(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition("type", "in", ValueRef(literal=["requirement"])),)
            ),
            trace_patterns=TracePatternSet((_MOTIVATION_WITH_ROLLUP, _OVERALL)),
        )

        result = _run_against(store, query)

        assert result.trace_table is not None
        verdicts = {row.entity_id: row.verdict for row in result.trace_table.rows}
        assert verdicts["REQ@whole"] == "gap"
