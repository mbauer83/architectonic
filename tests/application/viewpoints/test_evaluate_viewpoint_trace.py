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
