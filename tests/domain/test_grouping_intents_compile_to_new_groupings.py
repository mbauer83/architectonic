"""Grouping intents compile to the diagram's new groupings and to the layout change that keeps matching them.

Membership is content: a nest, unnest, create or delete changes ``authored-groupings``. The layout loses the
box entries that no longer fit — a removed grouping's, and those of the boxes whose members changed and
every box around them — so they are fitted round their members again. A listed grouping holds an
instance exclusively; a ruled one gains and loses no member by listing.
"""

from __future__ import annotations

import pytest

from src.domain.diagrams.authored_groupings import MalformedGroupings, check_groupings, grouping_ids
from src.domain.diagrams.grouping_intents import CreateGrouping, DeleteGrouping, Nest, Unnest, regrouped
from src.domain.diagrams.layout.arrange_intents import arranged, arranges, read_intents, regroups
from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, read_layout

A, B, C = "APP@1712870400.aaaaaa", "APP@1712870401.bbbbbb", "APP@1712870402.cccccc"
DIAGRAM = "ADG@1712870400.dddddd"


def _groupings() -> list[dict[str, object]]:
    return [
        {"id": "g-outer1", "label": "Outer", "entity-ids": [A], "groups": [
            {"id": "g-inner1", "label": "Inner", "entity-ids": [B]},
        ]},
        {"id": "g-other1", "label": "Other", "entity-ids": [f"{C}.with-slug"]},
        {"id": "g-ruled1", "label": "Business", "rule": {"domain": "business"}},
    ]


def _members(groupings: object, grouping_id: str) -> list[str]:
    from src.domain.diagrams.authored_groupings import walk_groupings  # noqa: PLC0415

    entry = next(entry for _trail, entry in walk_groupings(groupings) if entry.get("id") == grouping_id)
    return list(entry.get("entity-ids", []))  # type: ignore[call-overload]


def test_nest_moves_an_instance_out_of_every_other_listed_grouping() -> None:
    result = regrouped(Nest((C,), "g-inner1"), _groupings(), diagram_id=DIAGRAM)
    assert _members(result.groupings, "g-inner1") == [B, C]
    # Its only member left, so the box it left draws nothing and goes, as pruning does.
    assert "g-other1" not in grouping_ids(result.groupings) and result.removed == {"g-other1"}
    assert result.refit == {"g-inner1", "g-outer1"}
    assert not check_groupings(result.groupings)


def test_nest_matches_a_member_however_its_id_is_spelled_and_leaves_the_input_alone() -> None:
    before = _groupings()
    result = regrouped(Nest((C,), "g-outer1"), before, diagram_id=DIAGRAM)
    assert _members(result.groupings, "g-outer1") == [A, C]
    assert before == _groupings()


def test_unnest_moves_to_the_parent_or_the_canvas() -> None:
    inner = regrouped(Unnest((B,)), _groupings(), diagram_id=DIAGRAM)
    assert _members(inner.groupings, "g-outer1") == [A, B]
    assert "g-inner1" in inner.removed and inner.refit == {"g-outer1"}
    top = regrouped(Unnest((A,)), _groupings(), diagram_id=DIAGRAM)
    assert _members(top.groupings, "g-outer1") == []
    assert "g-outer1" in grouping_ids(top.groupings), "a box that still nests another is not empty"


def test_create_grouping_mints_an_id_and_takes_its_members_exclusively() -> None:
    result = regrouped(CreateGrouping("New", (A,), parent="g-outer1"), _groupings(), diagram_id=DIAGRAM)
    created = set(grouping_ids(result.groupings)) - set(grouping_ids(_groupings()))
    assert len(created) == 1
    (new_id,) = created
    assert _members(result.groupings, new_id) == [A] and _members(result.groupings, "g-outer1") == []
    assert result.refit == {new_id, "g-outer1"}
    assert not check_groupings(result.groupings)
    again = regrouped(CreateGrouping("New", (A,), parent="g-outer1"), _groupings(), diagram_id=DIAGRAM)
    assert set(grouping_ids(again.groupings)) - set(grouping_ids(_groupings())) == created, "minted, not drawn"


def test_create_grouping_at_the_top_is_appended() -> None:
    result = regrouped(CreateGrouping("Top", (B,)), _groupings(), diagram_id=DIAGRAM)
    assert result.groupings[-1]["label"] == "Top" and result.groupings[-1]["entity-ids"] == [B]


def test_delete_grouping_hands_its_members_and_subgroups_to_its_parent() -> None:
    inner = regrouped(DeleteGrouping("g-inner1"), _groupings(), diagram_id=DIAGRAM)
    assert _members(inner.groupings, "g-outer1") == [A, B] and inner.removed == {"g-inner1"}
    outer = regrouped(DeleteGrouping("g-outer1"), _groupings(), diagram_id=DIAGRAM)
    assert [entry["id"] for entry in outer.groupings] == ["g-inner1", "g-other1", "g-ruled1"]
    assert outer.removed == {"g-outer1"} and not outer.refit


@pytest.mark.parametrize(("intent", "says"), [
    (Nest((A,), "g-ruled1"), "selects its members by its rule"),
    (Unnest((C + "x",)), "in no listed grouping"),
    (Nest((A,), "g-nothere"), "no grouping 'g-nothere'"),
    (DeleteGrouping("g-nothere"), "no grouping 'g-nothere'"),
    (CreateGrouping("x", (A,), parent="g-nothere"), "no grouping 'g-nothere'"),
])
def test_an_intent_that_cannot_apply_is_refused_saying_why(intent: object, says: str) -> None:
    with pytest.raises(MalformedGroupings, match=says):
        regrouped(intent, _groupings(), diagram_id=DIAGRAM)  # type: ignore[arg-type]


def test_a_subgroup_of_a_ruled_grouping_cannot_hand_its_members_up_to_it() -> None:
    groupings = [{"id": "g-ruled1", "rule": {"domain": "business"}, "groups": [
        {"id": "g-listed", "label": "Listed", "entity-ids": [A]},
    ]}]
    with pytest.raises(MalformedGroupings, match="cannot gain members by listing"):
        regrouped(Unnest((A,)), groupings, diagram_id=DIAGRAM)
    with pytest.raises(MalformedGroupings, match="cannot gain members by listing"):
        regrouped(DeleteGrouping("g-listed"), groupings, diagram_id=DIAGRAM)


def test_mixed_intents_apply_in_order_and_drop_the_box_entries_that_no_longer_fit() -> None:
    layout = read_layout({
        "elements": {A: {"x": 0, "y": 0}, B: {"x": 200, "y": 0}},
        "boxes": {"g-outer1": {"x": 0, "y": 0}, "g-inner1": {"x": 180, "y": 0}, "g-other1": {"x": 500, "y": 0}},
        "z": {"g-other1": 2},
    })
    intents = read_intents([
        {"intent": "nest", "keys": [C], "grouping": "g-outer1"},
        {"intent": "return_to_automatic", "keys": [B]},
    ])
    assert regroups(intents) and arranges(intents)
    result = arranged(intents, groupings=_groupings(), diagram_id=DIAGRAM, layout=layout, drawn={})
    assert result.groupings is not None and _members(result.groupings, "g-outer1") == [A, C]
    assert set(result.layout.boxes) == {"g-inner1"} and not result.layout.z
    assert set(result.layout.elements) == {A}


def test_grouping_intents_alone_state_no_geometry() -> None:
    intents = read_intents([{"intent": "delete_grouping", "grouping": "g-inner1"}])
    assert regroups(intents) and not arranges(intents)
    assert arranged(intents, groupings=_groupings(), diagram_id=DIAGRAM, layout=Layout(), drawn={}).layout == Layout()


def test_layout_intents_alone_state_no_groupings() -> None:
    intents = read_intents([{"intent": "return_to_automatic"}])
    assert arranged(intents, groupings=_groupings(), diagram_id=DIAGRAM, layout=Layout(), drawn={}).groupings is None


@pytest.mark.parametrize(("raw", "says"), [
    ([{"intent": "nest", "keys": [A]}], "grouping is None"),
    ([{"intent": "nest", "keys": [], "grouping": "g-outer1"}], "at least 1"),
    ([{"intent": "create_grouping", "keys": [A]}], "label is None"),
    ([{"intent": "create_grouping", "label": " ", "keys": [A]}], "non-empty string"),
    ([{"intent": "delete_grouping", "grouping": "g-outer1", "keys": [A]}], "does not take"),
    ([{"intent": "unnest", "grouping": "g-outer1", "keys": [A]}], "does not take"),
])
def test_a_malformed_grouping_intent_is_refused_saying_why(raw: list[dict[str, object]], says: str) -> None:
    with pytest.raises(MalformedLayout, match=says):
        read_intents(raw)
