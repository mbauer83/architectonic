"""A change set and the bulk items it amounts to are two spellings of one thing — tested as a pair.

Both directions, over what each vocabulary permits rather than over a handful of examples: every
set the generator can build goes to items and comes back, and every field the *decoder* accepts on
an item goes to operations and comes back. The second half is derived from `KNOWN_ITEM_FIELDS`, so a
field the bulk write learns to accept is covered here the moment it is added — or fails here, which
is the point.

What the two cannot say to each other is refused in a sentence, and each refusal is pinned below.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from hypothesis import given

from src.application.change_sets.base import Base, BaseRevision, BaseValue
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    Operation,
    OperationKey,
    RemoveConnection,
    RemoveEntity,
    sort_key,
)
from src.application.modeling.edit_field_catalogue import ADDRESSING, KEYED, PROSE
from src.infrastructure.mcp.artifact_mcp.bulk.change_set_item_reading import from_bulk_items
from src.infrastructure.mcp.artifact_mcp.bulk.change_set_items import Untranslatable, to_bulk_items
from src.infrastructure.mcp.artifact_mcp.bulk.common import (
    KNOWN_DELETE_OPS,
    KNOWN_ITEM_FIELDS,
    KNOWN_OPS,
    unknown_item_fields,
)
from tests.support.change_sets import GROUP, change_set, change_sets, create, edit, edit_connection, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"
_TRIPLE = {"source_entity": _A, "connection_type": "serving", "target_entity": _B}

#: The envelope, the mode selector and the address: what an item carries that is not a change.
_NOT_A_CHANGE = frozenset({"op", "_ref", "operation"}) | ADDRESSING["entity"] | ADDRESSING["connection"]


def _slug_of(group_id: str) -> str:
    return f"slug-of-{group_id}"


def _id_of(slug: str) -> str:
    return slug.removeprefix("slug-of-")


def _a_base(key: OperationKey) -> Base:
    """A base in the form the key calls for, for items that never recorded one."""
    whole_artifact = not key.field
    return _REVISION if whole_artifact or key.field in PROSE[key.kind] else BaseValue(None)


def _back(write: Any, delete: Any = ()) -> tuple[Operation, ...]:
    return from_bulk_items(write, delete, id_of_group=_id_of, base_of=_a_base)


def _arranged(operations: Any) -> list[Operation]:
    return sorted(operations, key=sort_key)


class TestASetSurvivesTheTripThroughItems:
    @given(change_sets())
    def test_every_operation_comes_back_with_the_base_the_caller_supplies(self, generated: ChangeSet) -> None:
        """Notes are the one thing an item has no place for; everything else returns."""
        items = to_bulk_items(generated, slug_of_group=_slug_of)

        returned = from_bulk_items(
            items.write, items.delete, id_of_group=_id_of,
            base_of=lambda key: generated.by_claim[key].base,  # type: ignore[union-attr]
        )

        assert _arranged(returned) == [replace(op, note="") for op in generated.operations]

    @given(change_sets())
    def test_every_item_written_is_one_the_decoder_accepts(self, generated: ChangeSet) -> None:
        items = to_bulk_items(generated, slug_of_group=_slug_of)

        assert {item["op"] for item in items.write} <= KNOWN_OPS
        assert {item["op"] for item in items.delete} <= KNOWN_DELETE_OPS
        assert [unknown_item_fields(item) for item in items.write] == [()] * len(items.write)

    def test_edits_of_one_entity_fold_into_one_item_with_keys_gathered(self) -> None:
        folded = to_bulk_items(
            change_set(
                edit(_A, "name", "Invoicing"),
                edit(_A, "properties", "gold", key="tier"),
                edit(_A, "properties", None, key="region"),
                edit(_B, "status", "active"),
            ),
            slug_of_group=_slug_of,
        )
        assert folded.write == (
            {"op": "edit_entity", "artifact_id": _A, "name": "Invoicing",
             "properties": {"region": None, "tier": "gold"}},
            {"op": "edit_entity", "artifact_id": _B, "status": "active"},
        )

    def test_a_group_is_an_id_in_the_set_and_a_slug_in_the_item(self) -> None:
        items = to_bulk_items(change_set(create("queue"), edit(_A, "group", GROUP)), slug_of_group=_slug_of)
        assert [item["group"] for item in items.write] == [_slug_of(GROUP)] * 2
        assert {op.claim: op for op in _back(items.write)}[OperationKey("entity", _A, "group")].value == GROUP  # type: ignore[union-attr]

    def test_creates_come_before_the_connections_that_join_them(self) -> None:
        link = AddConnection(joins("$ref:worker", "$ref:queue"), {})
        items = to_bulk_items(change_set(link, create("queue"), create("worker")), slug_of_group=_slug_of)
        assert [item["op"] for item in items.write] == ["create_entity", "create_entity", "add_connection"]
        assert items.write[2]["source_entity"] == "$ref:worker"

    def test_removals_go_to_the_tool_that_can_perform_them(self) -> None:
        """A connection removal is a bulk write; an entity removal only the bulk delete can do."""
        items = to_bulk_items(
            change_set(RemoveEntity(_A, _REVISION), RemoveConnection(joins(_A, _B), _REVISION)),
            slug_of_group=_slug_of,
        )
        assert items.write == ({"op": "edit_connection", **_TRIPLE, "operation": "remove"},)
        assert items.delete == ({"op": "delete_entity", "artifact_id": _A},)


def _fields_of(op: str) -> list[str]:
    return sorted(KNOWN_ITEM_FIELDS[op] - _NOT_A_CHANGE)


def _value_for(kind: str, field: str) -> Any:
    if field in KEYED[kind]:  # type: ignore[index]
        return {"set": ["a", 1, True], "removed": None}
    return _slug_of(GROUP) if field == "group" else {"probe": ["value"]}


class TestAnItemSurvivesTheTripThroughOperations:
    """Over every field the decoder accepts, one at a time and all at once."""

    @pytest.mark.parametrize("field", _fields_of("edit_entity"))
    def test_every_field_of_an_entity_edit(self, field: str) -> None:
        item = {"op": "edit_entity", "artifact_id": _A, field: _value_for("entity", field)}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    @pytest.mark.parametrize("field", _fields_of("edit_connection"))
    def test_every_field_of_a_connection_edit(self, field: str) -> None:
        item = {"op": "edit_connection", **_TRIPLE, field: _value_for("connection", field)}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    @pytest.mark.parametrize("op", ["edit_entity", "edit_connection"])
    def test_every_field_of_an_edit_at_once(self, op: str) -> None:
        kind = op.removeprefix("edit_")
        address = _TRIPLE if kind == "connection" else {"artifact_id": _A}
        item = {"op": op, **address, **{f: _value_for(kind, f) for f in _fields_of(op)}}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    def test_a_create_with_everything_it_may_state(self) -> None:
        stated = {field: _value_for("entity", field) for field in _fields_of("create_entity")}
        item = {"op": "create_entity", "_ref": "queue", "artifact_id": "NEW@1.q", **stated, "name": "Queue",
                "artifact_type": "node"}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    def test_a_new_connection_with_everything_it_may_state(self) -> None:
        stated = {field: _value_for("connection", field) for field in _fields_of("add_connection")}
        item = {"op": "add_connection", **_TRIPLE, **stated}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    def test_a_connection_removal(self) -> None:
        item = {"op": "edit_connection", **_TRIPLE, "operation": "remove"}
        assert to_bulk_items(change_set(*_back([item])), slug_of_group=_slug_of).write == (item,)

    def test_an_entity_delete(self) -> None:
        item = {"op": "delete_entity", "artifact_id": _A}
        assert to_bulk_items(change_set(*_back([], [item])), slug_of_group=_slug_of).delete == (item,)

    def test_a_connection_delete_returns_as_the_bulk_writes_removal(self) -> None:
        """The one place the trip normalises: two tools spell this removal, and a set has one."""
        items = to_bulk_items(change_set(*_back([], [{"op": "delete_connection", **_TRIPLE}])), slug_of_group=_slug_of)
        assert items.write == ({"op": "edit_connection", **_TRIPLE, "operation": "remove"},)
        assert items.delete == ()

    def test_the_fields_covered_are_the_decoders_and_not_an_empty_list(self) -> None:
        assert len(_fields_of("edit_entity")) > 5
        assert len(_fields_of("edit_connection")) > 3

    def test_a_create_without_a_group_is_filed_where_the_bulk_write_files_it(self) -> None:
        (created,) = _back([{"op": "create_entity", "_ref": "q", "name": "Q", "artifact_type": "node"}])
        assert created.fields["group"] == "uncategorized"  # type: ignore[union-attr]


#: A write item that says something a change set cannot hold, and the part of the refusal naming it.
_UNTRANSLATABLE: dict[str, tuple[dict[str, Any], str]] = {
    "document": (
        {"op": "create_document", "doc_type": "adr", "title": "t"}, "no operation for create_document",
    ),
    "unknown-op": ({"op": "upsert_entity"}, "not a bulk operation"),
    "create-without-alias": (
        {"op": "create_entity", "name": "Q", "artifact_type": "node"}, "needs a _ref",
    ),
    "unknown-field": ({"op": "edit_entity", "artifact_id": _A, "colour": "red"}, "does not take"),
    "empty-edit": ({"op": "edit_entity", "artifact_id": _A}, "changes nothing"),
    "edit-without-subject": ({"op": "edit_entity", "name": "x"}, "names its artifact_id"),
    "keyed-field-cleared-whole": (
        {"op": "edit_entity", "artifact_id": _A, "properties": None}, "one operation per named key",
    ),
    "metadata-cleared-whole": (
        {"op": "edit_connection", **_TRIPLE, "metadata": None}, "one operation per named key",
    ),
    "remove-and-set": (
        {"op": "edit_connection", **_TRIPLE, "operation": "remove", "description": "x"}, "cannot do both",
    ),
    "unknown-mode": ({"op": "edit_connection", **_TRIPLE, "operation": "delete"}, "update or remove"),
    "connection-without-type": (
        {"op": "add_connection", "source_entity": _A, "target_entity": _B}, "names its connection_type",
    ),
}


class TestWhatDoesNotTranslateIsRefused:
    @pytest.mark.parametrize(("item", "fault"), _UNTRANSLATABLE.values(), ids=list(_UNTRANSLATABLE))
    def test_a_write_item(self, item: dict[str, Any], fault: str) -> None:
        with pytest.raises(Untranslatable, match=fault):
            _back([item])

    @pytest.mark.parametrize("op", ["delete_document", "delete_diagram"])
    def test_a_delete_of_something_a_set_does_not_change(self, op: str) -> None:
        with pytest.raises(Untranslatable, match=f"no operation for {op}"):
            _back([], [{"op": op, "artifact_id": "ADR@1.a"}])

    def test_a_removal_given_a_value_for_its_base(self) -> None:
        with pytest.raises(Untranslatable, match="revision of the record"):
            from_bulk_items(
                [], [{"op": "delete_entity", "artifact_id": _A}],
                id_of_group=_id_of, base_of=lambda _key: BaseValue({"name": "a"}),
            )

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(edit("$ref:queue", "name", "Queue 2"), id="edit"),
            pytest.param(RemoveEntity("$ref:queue", _REVISION), id="removal"),
            pytest.param(edit_connection(joins(_A, "$ref:queue"), "description", "x"), id="connection-edit"),
            pytest.param(AddConnection(joins(_A, "$ref:queue"), {}), id="connection-to-the-lower-sets"),
        ],
    )
    def test_a_provisional_reference_the_bulk_write_would_not_resolve(self, operation: Operation) -> None:
        """The bulk write resolves `$ref:` only where a batch adds a connection to its own create."""
        lower = change_set(create("queue"))
        upper = change_set(operation)

        with pytest.raises(Untranslatable, match="has no id yet"):
            to_bulk_items(upper, slug_of_group=_slug_of, beneath=lower)

        items = to_bulk_items(upper, slug_of_group=_slug_of, beneath=lower, resolved={"queue": "APP@9.q"})
        assert "APP@9.q" in str([*items.write, *items.delete])
        assert "$ref:" not in str([*items.write, *items.delete])
