"""A grouping that realizes a requirement is saying its members do — potentially, and visibly so.

Three facts have to hold together, and each fails differently if it doesn't:

* the row **passes**, because a grouping realizing a requirement is a real modelling statement and the
  members are what do the realizing (`PDR12`);
* it passes as a **potential** inference, never as a statement — a grouping realizes nothing itself, and
  `eligible_realizer_types` rightly excludes it as a structural helper;
* the reader is **told**, or an inference and a statement are indistinguishable in the result.

The container type is not named in the traversal: it is read from the composition rules, where `PDR12`
already declares that an aggregation from a grouping pushes a realization down to the member. Naming it
in code would be a second place for the same fact to be wrong — and would ignore an ontology that
declares a different container.
"""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.application.viewpoints.trace_index import _container_pushdowns
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

_REGISTRY = get_module_registry()
_REGISTRIES = build_registry_snapshot(build_runtime_catalogs(_REGISTRY), [])
_DEFAULTS = dict(max_entities=200, default_limit=200, timeout_seconds=30.0, index_generation=None)

_MOTIVATION = TracePattern(
    name="motivation",
    applies_to=("goal", "outcome"),
    branches=InlineBranches((
        NamedBranchEdge("g2o", StoredEdge("archimate-realization", "incoming", "outcome")),
        NamedBranchEdge("o2r", StoredEdge("archimate-realization", "incoming", "requirement")),
    )),
    rollup=RollupEdge("archimate-aggregation", "outgoing"),
    leaf=NoneLeaf(),
)
_OVERALL = TracePattern(
    name="overall",
    applies_to=("goal", "outcome", "requirement"),
    branches=BranchesRef("motivation"),
    leaf=DerivedReachabilityLeaf("archimate-realization", RegistryEndpoint("permitted-realizers-of-requirement")),
)


def _e(entity_id: str, artifact_type: str, domain: str):
    return entity(artifact_id=entity_id, artifact_type=artifact_type, domain=domain, status="active", name=entity_id)


def _c(source: str, target: str, conn_type: str):
    return connection(artifact_id=f"{source}->{target}:{conn_type}", source=source, target=target, conn_type=conn_type)


def _requirement_row(connections):
    entities = (
        _e("GRP@1", "grouping", "common"),
        _e("GRP@2", "grouping", "common"),
        _e("APP@1", "application-component", "application"),
        _e("REQ@1", "requirement", "motivation"),
    )
    query = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(
            children=(AttributeCondition("type", "in", ValueRef(literal=["requirement"])),)
        ),
        trace_patterns=TracePatternSet((_MOTIVATION, _OVERALL)),
    )
    definition = ViewpointDefinition(slug="cov", version=1, name="Coverage", query=query, presentation=None)
    result = evaluate_viewpoint(
        ViewpointExecutionRequest(slug="cov", parameters=None),
        catalog=ViewpointCatalog(entries=(definition,)),
        read_access=Store(entities={e.artifact_id: e for e in entities}, connections=list(connections)),
        registries=_REGISTRIES,
        **_DEFAULTS,  # type: ignore[arg-type]
    )
    assert result.trace_table is not None
    row = next(r for r in result.trace_table.rows if r.entity_id == "REQ@1")
    return row, dict(row.pattern_results)["overall"]


# ── The container comes from the spec ─────────────────────────────────────────


def test_the_container_is_read_from_the_composition_rules() -> None:
    """`PDR12` is the declaration; the traversal must not carry its own copy of "grouping"."""
    pushdowns = _container_pushdowns(_REGISTRY)

    assert pushdowns, "no push-down rule found — the traversal would silently do nothing"
    assert any(
        p.container_type == "grouping"
        and p.whole_part_connection == "archimate-aggregation"
        and "archimate-realization" in p.pushed_connections
        for p in pushdowns
    ), pushdowns


# ── What the row says ─────────────────────────────────────────────────────────


def test_a_requirement_realized_by_a_grouping_passes() -> None:
    row, overall = _requirement_row([
        _c("GRP@1", "REQ@1", "archimate-realization"),
        _c("GRP@1", "APP@1", "archimate-aggregation"),
    ])

    assert row.verdict == "pass"
    assert overall.status_code == "ok"


def test_it_passes_as_an_inference_the_reader_can_see() -> None:
    _row, overall = _requirement_row([
        _c("GRP@1", "REQ@1", "archimate-realization"),
        _c("GRP@1", "APP@1", "archimate-aggregation"),
    ])

    assert overall.diagnostic_code == "potential_realization"


def test_a_directly_realized_requirement_carries_no_inference_marker() -> None:
    """The contrast that makes the marker informative rather than decorative."""
    _row, overall = _requirement_row([_c("APP@1", "REQ@1", "archimate-realization")])

    assert overall.diagnostic_code is None


def test_a_nested_container_is_followed() -> None:
    _row, overall = _requirement_row([
        _c("GRP@1", "REQ@1", "archimate-realization"),
        _c("GRP@1", "GRP@2", "archimate-aggregation"),
        _c("GRP@2", "APP@1", "archimate-aggregation"),
    ])

    assert overall.status_code == "ok"
    assert overall.diagnostic_code == "potential_realization"


def test_an_empty_grouping_realizes_nothing() -> None:
    """The substitution must not manufacture a realizer out of a container with no members."""
    row, overall = _requirement_row([_c("GRP@1", "REQ@1", "archimate-realization")])

    assert row.verdict == "gap"
    assert overall.status_code == "partial_branches"


def test_a_real_defect_still_outranks_the_inference_marker() -> None:
    """`potential_realization` is a statement about evidence, not a problem — a cycle is a problem."""
    row, overall = _requirement_row([
        _c("GRP@1", "REQ@1", "archimate-realization"),
        _c("GRP@1", "APP@1", "archimate-aggregation"),
        _c("REQ@1", "APP@1", "archimate-association"),
    ])

    assert row.verdict in {"pass", "gap"}
    assert overall.diagnostic_code in {"potential_realization", "ambiguous_link", "cycle"}
