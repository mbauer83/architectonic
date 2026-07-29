"""Unit tests for PermittedRelationshipSet."""

from __future__ import annotations

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.relationships.permitted_relationships import PermittedRelationship, PermittedRelationshipSet

_A = EntityTypeName("type-a")
_B = EntityTypeName("type-b")
_C = EntityTypeName("type-c")
_X = ConnectionTypeName("conn-x")
_Y = ConnectionTypeName("conn-y")


def _make(*triples: tuple[str, str, str]) -> PermittedRelationshipSet:
    return PermittedRelationshipSet(
        frozenset(
            PermittedRelationship(EntityTypeName(s), EntityTypeName(t), ConnectionTypeName(c)) for s, t, c in triples
        )
    )


class TestPermits:
    def test_permits_known_triple(self) -> None:
        rs = _make((_A, _B, _X))
        assert rs.permits(_A, _B, _X) is True

    def test_rejects_unknown_triple(self) -> None:
        rs = _make((_A, _B, _X))
        assert rs.permits(_A, _B, _Y) is False
        assert rs.permits(_B, _A, _X) is False

    def test_empty_permits_nothing(self) -> None:
        assert PermittedRelationshipSet.empty().permits(_A, _B, _X) is False


class TestPermittedConnectionTypes:
    def test_returns_all_types_for_pair(self) -> None:
        rs = _make((_A, _B, _X), (_A, _B, _Y))
        result = rs.permitted_connection_types(_A, _B)
        assert result == frozenset({_X, _Y})

    def test_returns_empty_for_unknown_pair(self) -> None:
        rs = _make((_A, _B, _X))
        assert rs.permitted_connection_types(_B, _A) == frozenset()


class TestFilterTo:
    def test_filter_keeps_matching_rules(self) -> None:
        rs = _make((_A, _B, _X), (_A, _C, _Y), (_B, _C, _X))
        filtered = rs.filter_to(frozenset({_A, _B}), frozenset({_X}))
        assert filtered.permits(_A, _B, _X) is True
        assert filtered.permits(_A, _C, _Y) is False  # C excluded
        assert filtered.permits(_B, _C, _X) is False  # C excluded

    def test_filter_empty_entity_set_gives_empty(self) -> None:
        rs = _make((_A, _B, _X))
        result = rs.filter_to(frozenset(), frozenset({_X}))
        assert result.permits(_A, _B, _X) is False

    def test_filter_empty_conn_set_gives_empty(self) -> None:
        rs = _make((_A, _B, _X))
        result = rs.filter_to(frozenset({_A, _B}), frozenset())
        assert result.permits(_A, _B, _X) is False


class TestUnion:
    def test_union_merges_rules(self) -> None:
        r1 = _make((_A, _B, _X))
        r2 = _make((_A, _C, _Y))
        merged = r1 | r2
        assert merged.permits(_A, _B, _X) is True
        assert merged.permits(_A, _C, _Y) is True

    def test_union_with_empty_is_identity(self) -> None:
        rs = _make((_A, _B, _X))
        assert (rs | PermittedRelationshipSet.empty()).permits(_A, _B, _X) is True
        assert (PermittedRelationshipSet.empty() | rs).permits(_A, _B, _X) is True

    def test_union_is_commutative_on_permits(self) -> None:
        r1 = _make((_A, _B, _X))
        r2 = _make((_B, _C, _Y))
        left = r1 | r2
        right = r2 | r1
        assert left.permits(_A, _B, _X) == right.permits(_A, _B, _X)
        assert left.permits(_B, _C, _Y) == right.permits(_B, _C, _Y)


class TestBySource:
    def test_groups_by_source(self) -> None:
        rs = _make((_A, _B, _X), (_A, _C, _Y))
        by_src = rs.by_source()
        assert _A in by_src
        assert len(by_src[_A]) == 2
        targets = {t for t, _ in by_src[_A]}
        assert targets == {_B, _C}
