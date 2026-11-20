"""The order an applier needs is read off the operations, and a set that has none is refused."""

from __future__ import annotations

import pytest
from hypothesis import given

from src.application.change_sets.base import BaseRevision
from src.application.change_sets.operations import (
    AddConnection,
    MalformedChangeSet,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.ordering import (
    application_order,
    dependencies,
    ordered,
)
from tests.support.change_sets import change_set, change_sets, create, edit, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"


def _position(order: tuple[Operation, ...], operation: Operation) -> int:
    return order.index(operation)


class TestWhatComesBeforeWhat:
    def test_a_connection_comes_after_the_entities_it_joins(self) -> None:
        queue, worker = create("queue"), create("worker")
        link = AddConnection(joins("$ref:worker", "$ref:queue"), {})

        order = application_order(change_set(link, worker, queue))

        assert _position(order, link) > max(_position(order, queue), _position(order, worker))

    def test_an_entity_goes_after_the_connections_removed_from_it(self) -> None:
        entity = RemoveEntity(_A, _REVISION)
        outgoing = RemoveConnection(joins(_A, _B), _REVISION)
        incoming = RemoveConnection(joins(_B, _A), _REVISION)

        order = application_order(change_set(entity, outgoing, incoming))

        assert _position(order, entity) == 2

    def test_unrelated_operations_need_nothing(self) -> None:
        needs = dependencies(change_set(edit(_A, "name", "x"), edit(_B, "name", "y")))
        assert set(needs.values()) == {frozenset()}

    def test_the_order_does_not_depend_on_how_the_set_was_assembled(self) -> None:
        operations = (
            create("queue"), AddConnection(joins(_A, "$ref:queue"), {}), edit(_B, "name", "x"),
            RemoveConnection(joins(_A, _B), _REVISION),
        )
        assert application_order(change_set(*operations)) == application_order(
            change_set(*reversed(operations))
        )

    @given(change_sets())
    def test_every_operation_follows_everything_it_needs(self, generated) -> None:  # noqa: ANN001
        order = application_order(generated)
        seen: set[object] = set()
        for operation in order:
            assert dependencies(generated)[operation.claim] <= seen
            seen.add(operation.claim)
        assert len(order) == len(generated.operations)


class TestWhatHasNoOrder:
    def test_a_circle_is_refused_naming_it(self) -> None:
        """No set this value admits has one — which is why the refusal is tested on the sorter."""
        first, second = edit(_A, "name", "x"), edit(_B, "name", "y")
        by_claim = {first.claim: first, second.claim: second}
        circular = {first.claim: frozenset({second.claim}), second.claim: frozenset({first.claim})}

        with pytest.raises(MalformedChangeSet, match="in a circle"):
            ordered(by_claim, circular)

    def test_a_reference_nothing_creates_is_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match=r"\$ref:queue, which neither"):
            application_order(change_set(AddConnection(joins(_A, "$ref:queue"), {})))

    def test_a_reference_the_set_beneath_does_not_create_is_refused_too(self) -> None:
        lower = change_set(create("queue"))
        upper = change_set(AddConnection(joins(_A, "$ref:cache"), {}))

        with pytest.raises(MalformedChangeSet, match=r"\$ref:cache, which neither"):
            application_order(upper, beneath=lower)

    def test_a_reference_the_set_beneath_creates_resolves(self) -> None:
        lower = change_set(create("queue"))
        link = AddConnection(joins(_A, "$ref:queue"), {})
        upper = change_set(link, edit("$ref:queue", "name", "Queue 2"))

        assert link in application_order(upper, beneath=lower)

    def test_the_lower_sets_operations_are_not_in_the_upper_sets_order(self) -> None:
        lower = change_set(create("queue"))
        upper = change_set(AddConnection(joins(_A, "$ref:queue"), {}))
        assert len(application_order(upper, beneath=lower)) == 1
