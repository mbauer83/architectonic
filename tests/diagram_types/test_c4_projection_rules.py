"""C4 projection edge & membership rules.

Covers:
  - serving direction reversal (provider→consumer becomes consumer --uses--> provider)
  - association role rule (symmetric edge oriented consumer --uses--> system side)
  - additive validated inclusion (_included_entity_ids adds graph-justified entities)
  - bounded roll-up (system-context uses multi-hop descendants for neighbour discovery;
    internal entities remap to scope root in rendering)
  - data-object surfaced as internal component in c4-component views
  - grouping as valid scope / internal type
  - duplicate connections deduplicated; self-loops removed
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import src.diagram_types.c4._projection  # noqa: F401 — triggers strategy registration
from src.diagram_types.c4._projection import _rollup_conns, project_c4
from src.diagram_types.c4._resolve import resolve_c4_state
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_COMMON_CTX = dict(
    scope_entity_type="software-system",
    internal_c4_type="container",
    person_archimate_types=frozenset({"business-actor", "role"}),
)
_COMMON_COMP = dict(
    scope_entity_type="container",
    internal_c4_type="component",
    person_archimate_types=frozenset({"business-actor", "role"}),
)

_FAKE_ROOT = Path("/fake")
_CTX_CONFIG = {
    "c4": {
        "scope_entity_type": "software-system",
        "scope_render_mode": "node",
        "internal_entity_types": [],
    }
}


def _resolve(query: FakeQuery, scope_id: str, diagram_entities: dict | None = None) -> object:
    """Call resolve_c4_state with a patched artifact index returning the given query."""
    de = {"_scope_entity_id": scope_id, **(diagram_entities or {})}
    with patch("src.infrastructure.artifact_index.shared_artifact_index", return_value=query):
        return resolve_c4_state(_CTX_CONFIG, "c4-system-context", _FAKE_ROOT, de, [], frozenset())


# ---------------------------------------------------------------------------
# serving direction reversal
# ---------------------------------------------------------------------------


def test_serving_direction_reversed_consumer_is_src() -> None:
    """SYSTEM --serving--> CONSUMER: after P2.1, consumer is src, provider is tgt."""
    root = _entity("SYSTEM", "application-component")
    consumer = _entity("CONSUMER", "application-component")
    conn = _connection("S---C@@serving", "SYSTEM", "CONSUMER", "archimate-serving")
    query = FakeQuery([root, consumer], [conn])

    state = _resolve(query, "SYSTEM")

    assert len(state.connections) == 1
    c = state.connections[0]
    # Consumer alias should be src; provider (scope root) alias should be tgt
    assert state.scope_item.alias == c.tgt_alias, "Provider (scope root) should be connection target"
    consumer_item = next(i for i in state.outside_items if i.local_id == "CONSUMER")
    assert consumer_item.alias == c.src_alias, "Consumer should be connection source"


def test_serving_reversal_label_is_uses() -> None:
    """Default label for reversed serving connection is 'uses'."""
    root = _entity("SYS", "application-component")
    ext = _entity("EXT", "application-component")
    conn = _connection("SYS---EXT@@serving", "SYS", "EXT", "archimate-serving")
    query = FakeQuery([root, ext], [conn])

    state = _resolve(query, "SYS")

    assert any(c.label == "uses" for c in state.connections)


def test_non_serving_connection_direction_preserved() -> None:
    """archimate-flow direction is NOT reversed (source remains source)."""
    root = _entity("SYS", "application-component")
    ext = _entity("EXT", "application-component")
    conn = _connection("SYS---EXT@@flow", "SYS", "EXT", "archimate-flow")
    query = FakeQuery([root, ext], [conn])

    state = _resolve(query, "SYS")

    assert len(state.connections) == 1
    c = state.connections[0]
    # Flow is NOT reversed; SYS (scope root) is src
    assert c.src_alias == state.scope_item.alias


def test_association_oriented_consumer_to_system_regardless_of_authoring() -> None:
    """Symmetric association is oriented consumer --uses--> system side by the role
    rule, even when the model authored it provider→consumer."""
    root = _entity("SYS", "application-component")
    comp = _entity("COMP", "application-component")
    actor = _entity("ACTOR", "business-actor")
    agg = _connection("SYS---COMP@@agg", "SYS", "COMP", "archimate-aggregation")
    # Authored COMP(system side) → ACTOR(consumer): the "wrong" orientation for a C4 "uses".
    assoc = _connection("COMP---ACTOR@@assoc", "COMP", "ACTOR", "archimate-association")
    query = FakeQuery([root, comp, actor], [agg, assoc])

    state = _resolve(query, "SYS")

    actor_item = next(i for i in state.outside_items if i.local_id == "ACTOR")
    edge = next(c for c in state.connections if actor_item.alias in (c.src_alias, c.tgt_alias))
    assert edge.label == "uses"
    assert edge.src_alias == actor_item.alias, "consumer (actor) must be the source"
    assert edge.tgt_alias == state.scope_item.alias, "system side (scope) must be the target"


# ---------------------------------------------------------------------------
# bounded roll-up: system-context multi-hop neighbour discovery
# ---------------------------------------------------------------------------


def test_system_context_rollup_discovers_nested_neighbor() -> None:
    """System-context discovers external neighbours via structural descendants (not only root)."""
    root = _entity("ROOT", "application-component")
    child = _entity("CHILD", "application-component")
    ext = _entity("EXT", "application-component")
    agg = _connection("ROOT---CHILD@@aggregation", "ROOT", "CHILD", "archimate-aggregation")
    dep = _connection("CHILD---EXT@@serving", "CHILD", "EXT", "archimate-serving")
    query = FakeQuery([root, child, ext], [agg, dep])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    eids = {i.entity_id for i in result.items}
    assert "EXT" in eids, "Roll-up must surface EXT via CHILD even though ROOT has no direct serving"
    assert "CHILD" not in eids, "CHILD is internal; must not appear in system-context"


def test_system_context_rollup_deep_nesting() -> None:
    """Roll-up works for 2+ nesting levels."""
    root = _entity("ROOT", "application-component")
    mid = _entity("MID", "application-component")
    leaf = _entity("LEAF", "application-component")
    ext = _entity("EXT", "application-component")
    agg1 = _connection("ROOT---MID@@agg", "ROOT", "MID", "archimate-aggregation")
    agg2 = _connection("MID---LEAF@@agg2", "MID", "LEAF", "archimate-aggregation")
    dep = _connection("EXT---LEAF@@serving", "EXT", "LEAF", "archimate-serving")
    query = FakeQuery([root, mid, leaf, ext], [agg1, agg2, dep])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    eids = {i.entity_id for i in result.items}
    assert "EXT" in eids
    assert "MID" not in eids
    assert "LEAF" not in eids


def test_system_context_assignment_chain_discovers_actor() -> None:
    """Interface assigned to bridge (archimate-assignment in NESTING) surfaces actor via association."""
    root = _entity("ROOT", "application-component")
    bridge = _entity("BRIDGE", "application-component")
    iface = _entity("IFACE", "application-interface")
    actor = _entity("ACTOR", "business-actor")
    agg = _connection("ROOT---BRIDGE@@agg", "ROOT", "BRIDGE", "archimate-aggregation")
    asgn = _connection("BRIDGE---IFACE@@asgn", "BRIDGE", "IFACE", "archimate-assignment")
    assoc = _connection("IFACE---ACTOR@@assoc", "IFACE", "ACTOR", "archimate-association")
    query = FakeQuery([root, bridge, iface, actor], [agg, asgn, assoc])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    eids = {i.entity_id for i in result.items}
    assert "ACTOR" in eids, "Actor must be discovered via interface assignment chain"
    assert "IFACE" not in eids


def test_system_context_root_association_suppressed() -> None:
    """Root-level association (navigation-only link) does NOT create a neighbour."""
    root = _entity("ROOT", "application-component")
    peer = _entity("PEER", "application-component")
    assoc = _connection("ROOT---PEER@@assoc", "ROOT", "PEER", "archimate-association")
    query = FakeQuery([root, peer], [assoc])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    eids = {i.entity_id for i in result.items}
    assert "PEER" not in eids, "Root-level association must be suppressed"


def test_system_context_rollup_connection_ids_include_nested_connection() -> None:
    """Roll-up collects connection IDs from internal descendant to external neighbour."""
    root = _entity("ROOT", "application-component")
    child = _entity("CHILD", "application-component")
    ext = _entity("EXT", "application-component")
    agg = _connection("ROOT---CHILD@@agg", "ROOT", "CHILD", "archimate-aggregation")
    dep = _connection("CHILD---EXT@@dep", "CHILD", "EXT", "archimate-serving")
    query = FakeQuery([root, child, ext], [agg, dep])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    assert "CHILD---EXT@@dep" in result.connection_ids


def test_system_context_rollup_rendering_maps_internal_to_scope_root() -> None:
    """In system-context rendering, internal entity is remapped to scope root alias."""
    root = _entity("ROOT", "application-component")
    child = _entity("CHILD", "application-component")
    ext = _entity("EXT", "application-component")
    agg = _connection("R---C@@agg", "ROOT", "CHILD", "archimate-aggregation")
    # EXT serves CHILD (EXT is provider, CHILD is consumer)
    dep = _connection("EXT---CHILD@@dep", "EXT", "CHILD", "archimate-serving")
    query = FakeQuery([root, child, ext], [agg, dep])

    state = _resolve(query, "ROOT")

    # After serving reversal: CHILD (internal→scope root) --uses--> EXT
    root_alias = state.scope_item.alias
    all_aliases = {c.src_alias for c in state.connections} | {c.tgt_alias for c in state.connections}
    assert root_alias in all_aliases, "Scope root must appear in connections after roll-up remapping"


# ---------------------------------------------------------------------------
# self-loop removal
# ---------------------------------------------------------------------------


def test_self_loop_removed_after_rollup() -> None:
    """Connection that produces src==tgt after roll-up remapping is dropped."""
    root = _entity("ROOT", "application-component")
    child = _entity("CHILD", "application-component")
    # Connection within all_internal only (no external entity): ROOT--serves--CHILD
    # After roll-up ROOT(src=ROOT alias) --serves-- CHILD(internal→ROOT alias) = self-loop
    agg = _connection("ROOT---CHILD@@agg", "ROOT", "CHILD", "archimate-aggregation")
    dep = _connection("ROOT---CHILD@@dep", "ROOT", "CHILD", "archimate-serving")
    query = FakeQuery([root, child], [agg, dep])

    state = _resolve(query, "ROOT")

    for c in state.connections:
        assert c.src_alias != c.tgt_alias, "Self-loop must be removed"


# ---------------------------------------------------------------------------
# deduplication
# ---------------------------------------------------------------------------


def test_duplicate_rollup_connections_deduplicated() -> None:
    """Two connections producing the same (src_alias, tgt_alias) appear only once."""
    root = _entity("ROOT", "application-component")
    c1 = _entity("C1", "application-component")
    c2 = _entity("C2", "application-component")
    ext = _entity("EXT", "application-component")
    agg1 = _connection("ROOT---C1@@agg1", "ROOT", "C1", "archimate-aggregation")
    agg2 = _connection("ROOT---C2@@agg2", "ROOT", "C2", "archimate-aggregation")
    # C1 and C2 both consumed by EXT (EXT is provider) — after reversal both → ROOT as consumer
    dep1 = _connection("C1---EXT@@dep1", "EXT", "C1", "archimate-serving")
    dep2 = _connection("C2---EXT@@dep2", "EXT", "C2", "archimate-serving")
    query = FakeQuery([root, c1, c2, ext], [agg1, agg2, dep1, dep2])

    state = _resolve(query, "ROOT")

    pairs = [(c.src_alias, c.tgt_alias) for c in state.connections]
    assert len(pairs) == len(set(pairs)), "Duplicate (src_alias, tgt_alias) pairs must be removed"


# ---------------------------------------------------------------------------
# data-object in component views
# ---------------------------------------------------------------------------


def test_component_data_object_shown_as_internal() -> None:
    """data-object aggregated by scope is surfaced as internal in c4-component."""
    root = _entity("ROOT", "application-component")
    store = _entity("STORE", "data-object")
    agg = _connection("ROOT---STORE@@agg", "ROOT", "STORE", "archimate-aggregation")
    query = FakeQuery([root, store], [agg])

    result = project_c4("c4-component", "ROOT", query, **_COMMON_COMP)

    internal_ids = {i.entity_id for i in result.items if i.role == "internal"}
    assert "STORE" in internal_ids


def test_component_accessed_data_object_shown_as_external() -> None:
    """data-object accessed (not aggregated) by a component surfaces as external neighbour."""
    root = _entity("ROOT", "application-component")
    comp = _entity("COMP", "application-component")
    store = _entity("STORE", "data-object")
    agg = _connection("ROOT---COMP@@agg", "ROOT", "COMP", "archimate-aggregation")
    acc = _connection("COMP---STORE@@acc", "COMP", "STORE", "archimate-access")
    query = FakeQuery([root, comp, store], [agg, acc])

    result = project_c4("c4-component", "ROOT", query, **_COMMON_COMP)

    external_ids = {i.entity_id for i in result.items if i.role == "external"}
    assert "STORE" in external_ids, "accessed data-object should be an external neighbour"


# ---------------------------------------------------------------------------
# grouping as valid scope / internal type
# ---------------------------------------------------------------------------


def test_grouping_scope_in_component_projection() -> None:
    """grouping entity can act as root in c4-component projection."""
    root = _entity("GRP", "grouping")
    child = _entity("CHILD", "application-component")
    agg = _connection("GRP---CHILD@@agg", "GRP", "CHILD", "archimate-aggregation")
    query = FakeQuery([root, child], [agg])

    result = project_c4("c4-component", "GRP", query, **_COMMON_COMP)

    internal_ids = {i.entity_id for i in result.items if i.role == "internal"}
    assert "CHILD" in internal_ids


def test_grouping_discovered_as_context_neighbour() -> None:
    """grouping is a valid external-neighbour type in system-context."""
    root = _entity("ROOT", "application-component")
    grp = _entity("GRP", "grouping")
    dep = _connection("ROOT---GRP@@serving", "ROOT", "GRP", "archimate-serving")
    query = FakeQuery([root, grp], [dep])

    result = project_c4("c4-system-context", "ROOT", query, **_COMMON_CTX)

    eids = {i.entity_id for i in result.items}
    assert "GRP" in eids


# ---------------------------------------------------------------------------
# additive validated inclusion
# ---------------------------------------------------------------------------


def test_additive_inclusion_adds_graph_justified_entity() -> None:
    """Entity in _included_entity_ids but not in projection is added if graph-connected."""
    root = _entity("ROOT", "application-component")
    connected = _entity("CONN", "application-component")
    isolated = _entity("ISO", "application-component")
    dep = _connection("CONN---ROOT@@serving", "ROOT", "CONN", "archimate-serving")
    query = FakeQuery([root, connected, isolated], [dep])

    state = _resolve(query, "ROOT", {"_included_entity_ids": ["CONN", "ISO"]})

    displayed = {i.local_id for i in [state.scope_item] + state.internal_items + state.outside_items}
    assert "CONN" in displayed, "CONN is graph-connected and should be added"
    assert "ISO" not in displayed, "ISO has no connections and must not be added"


def test_additive_inclusion_filter_still_applies_for_projected_entities() -> None:
    """_included_entity_ids still filters projected entities not in the list."""
    root = _entity("ROOT", "application-component")
    ext1 = _entity("EXT1", "application-component")
    ext2 = _entity("EXT2", "application-component")
    dep1 = _connection("ROOT---EXT1@@serving", "ROOT", "EXT1", "archimate-serving")
    dep2 = _connection("ROOT---EXT2@@serving", "ROOT", "EXT2", "archimate-serving")
    query = FakeQuery([root, ext1, ext2], [dep1, dep2])

    state = _resolve(query, "ROOT", {"_included_entity_ids": ["EXT1"]})

    displayed = {i.local_id for i in state.outside_items}
    assert "EXT1" in displayed
    assert "EXT2" not in displayed


# ---------------------------------------------------------------------------
# _rollup_conns helper
# ---------------------------------------------------------------------------


def test_rollup_conns_finds_serving_from_internal_to_external() -> None:
    ext = _entity("EXT", "application-component")
    internal = _entity("INT", "application-component")
    dep = _connection("INT---EXT@@serving", "INT", "EXT", "archimate-serving")
    query = FakeQuery([ext, internal], [dep])

    result = _rollup_conns({"INT"}, {"EXT"}, query)

    assert "INT---EXT@@serving" in result


def test_rollup_conns_excludes_internal_to_internal() -> None:
    a = _entity("A", "application-component")
    b = _entity("B", "application-component")
    dep = _connection("A---B@@serving", "A", "B", "archimate-serving")
    query = FakeQuery([a, b], [dep])

    result = _rollup_conns({"A", "B"}, {"EXT"}, query)

    assert len(result) == 0
