"""Tests for path-projection/v1 strategy and path key helpers."""

from __future__ import annotations

from src.application.derivation.path_projection import SPEC, _path_key, derive
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_SNAP = SourceModelSnapshot(repo_scope="both")


def _params(
    sources: list[str],
    targets: list[str] | None = None,
    max_hops: int = 3,
    direction: str = "outbound",
    policy: str = "shortest",
    conn_types: list[str] | None = None,
) -> dict[str, object]:
    p: dict[str, object] = {
        "source_entity_ids": sources,
        "max_path_length": max_hops,
        "path_policy": policy,
        "pre_filters": {"direction": direction},
    }
    if targets is not None:
        p["target_entity_ids"] = targets
    if conn_types is not None:
        p["pre_filters"] = {"direction": direction, "connection_types": conn_types}
    return p


def test_path_key_format() -> None:
    assert _path_key([("A---B@@serving", False), ("B---C@@flow", True)]) == "A---B@@serving@fwd|B---C@@flow@rev"


def test_path_key_empty() -> None:
    assert _path_key([]) == ""


def test_simple_chain_shortest() -> None:
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")
    ab = _connection("A---B@@serving", "A", "B", "serving")
    bc = _connection("B---C@@serving", "B", "C", "serving")
    query = FakeQuery([a, b, c], [ab, bc])

    result = derive(_params(["A"], ["C"]), _SNAP, query)

    assert len(result.paths) == 1
    pk = next(iter(result.paths))
    assert "A---B@@serving@fwd" in pk
    assert "B---C@@serving@fwd" in pk
    assert result.connection_ids == frozenset({"A---B@@serving", "B---C@@serving"})


def test_no_path_when_target_unreachable() -> None:
    a = _entity("A")
    b = _entity("B")
    ab = _connection("A---B@@serving", "A", "B", "serving")
    query = FakeQuery([a, b], [ab])

    result = derive(_params(["A"], ["X"]), _SNAP, query)
    assert result.paths == frozenset()
    assert result.connection_ids == frozenset()


def test_max_hops_respected() -> None:
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")
    d = _entity("D")
    ab = _connection("A---B@@serving", "A", "B")
    bc = _connection("B---C@@serving", "B", "C")
    cd = _connection("C---D@@serving", "C", "D")
    query = FakeQuery([a, b, c, d], [ab, bc, cd])

    # max_hops=2 should not reach D (3 hops away)
    result = derive(_params(["A"], ["D"], max_hops=2), _SNAP, query)
    assert result.paths == frozenset()


def test_all_simple_finds_all_paths() -> None:
    # A→B→C and A→C (direct)
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")
    ab = _connection("A---B@@serving", "A", "B")
    bc = _connection("B---C@@serving", "B", "C")
    ac = _connection("A---C@@flow", "A", "C", "flow")
    query = FakeQuery([a, b, c], [ab, bc, ac])

    result = derive(_params(["A"], ["C"], max_hops=3, policy="all-simple"), _SNAP, query)
    assert len(result.paths) == 2


def test_deterministic_tie_break() -> None:
    """Identical runs must produce identical path key ordering."""
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")
    ab = _connection("A---B@@serving", "A", "B")
    bc = _connection("B---C@@serving", "B", "C")
    ac = _connection("A---C@@flow", "A", "C", "flow")
    query = FakeQuery([a, b, c], [ab, bc, ac])

    result1 = derive(_params(["A"], ["C"], policy="all-simple"), _SNAP, query)
    result2 = derive(_params(["A"], ["C"], policy="all-simple"), _SNAP, query)
    assert result1.paths == result2.paths


def test_reversed_direction_inbound() -> None:
    a = _entity("A")
    b = _entity("B")
    ba = _connection("B---A@@serving", "B", "A")
    query = FakeQuery([a, b], [ba])

    result = derive(_params(["A"], ["B"], direction="inbound"), _SNAP, query)
    assert len(result.paths) == 1
    pk = next(iter(result.paths))
    assert "@rev" in pk


def test_connection_type_filter() -> None:
    a = _entity("A")
    b = _entity("B")
    ab_serving = _connection("A---B@@serving", "A", "B", "serving")
    ab_flow = _connection("A---B@@flow", "A", "B", "flow")
    query = FakeQuery([a, b], [ab_serving, ab_flow])

    result = derive(_params(["A"], ["B"], conn_types=["serving"]), _SNAP, query)
    # Only the serving connection should form a path
    assert all("serving" in pk for pk in result.paths)


def test_empty_sources() -> None:
    query = FakeQuery([], [])
    result = derive(_params([]), _SNAP, query)
    assert result.paths == frozenset()
    assert result.connection_ids == frozenset()


def test_path_projection_spec() -> None:
    assert SPEC.name == "path-projection"
    assert "connection_types" in SPEC.supported_filters
    assert "max_path_length" in SPEC.supported_filters
