"""A layout intent compiles to the patch that states it, each entry checked against the stored layout."""

from __future__ import annotations

import pytest

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, read_layout
from src.domain.diagrams.layout.layout_intents import compiled_patch, read_intents
from src.domain.diagrams.layout.layout_patch import LayoutConflict, patched, read_layout_patch

A, B, C = "APP@1712870400.aaaaaa", "APP@1712870401.bbbbbb", "APP@1712870402.cccccc"
LINE = "APP@1712870400.aaaaaa---APP@1712870401.bbbbbb@@serving"
DRAWN = {A: Extent(0, 0, 100, 40), B: Extent(0, 0, 60, 40), C: Extent(0, 0, 80, 40)}


def _stored() -> Layout:
    return read_layout({
        "elements": {A: {"x": 10, "y": 0}, B: {"x": 200, "y": 50}, C: {"x": 500, "y": 90}},
        "boxes": {"rule:domain=business": {"x": 0, "y": 0}},
        "relations": {LINE: {"from": {"side": "right", "at": 0.5}, "via": [[150, 20], [150, 70]]}},
    })


def _apply(raw: list[dict[str, object]], stored: Layout, base: Layout | None = None) -> Layout:
    base = stored if base is None else base
    patch = compiled_patch(read_intents(raw), base=base, stored=stored, drawn=DRAWN)
    return patched(base, read_layout_patch(patch), stored=stored)


def test_align_moves_each_element_to_the_shared_edge_and_keeps_the_other_axis() -> None:
    result = _apply([{"intent": "align", "keys": [A, B, C], "edge": "left"}], _stored())
    assert [(result.elements[k].x, result.elements[k].y) for k in (A, B, C)] == [(10, 0), (10, 50), (10, 90)]
    right = _apply([{"intent": "align", "keys": [A, B], "edge": "right"}], _stored())
    assert right.elements[A].x + 100 == right.elements[B].x + 60 == 260


def test_distribute_leaves_equal_gaps_and_keeps_both_ends() -> None:
    result = _apply([{"intent": "distribute", "keys": [C, A, B], "axis": "x"}], _stored())
    a, b, c = (result.elements[k].x for k in (A, B, C))
    assert (a, c) == (10, 500)
    assert b - (a + 100) == c - (b + 60)


def test_straighten_drops_the_bends_and_keeps_the_ports() -> None:
    route = _apply([{"intent": "straighten", "relations": [LINE]}], _stored()).relations[LINE]
    assert route.via == () and route.source is not None and route.source.side.value == "right"


def test_return_to_automatic_removes_named_entries_or_everything() -> None:
    one = _apply([{"intent": "return_to_automatic", "keys": [B, LINE]}], _stored())
    assert B not in one.elements and LINE not in one.relations and A in one.elements
    assert _apply([{"intent": "return_to_automatic"}], _stored()).states_nothing()


def test_only_what_changed_is_in_the_patch_and_each_entry_is_checked() -> None:
    stored = _stored()
    patch = compiled_patch(read_intents([{"intent": "align", "keys": [A, B], "edge": "left"}]),
                           base=stored, stored=stored, drawn=DRAWN)
    assert set(patch) == {"elements"} and set(patch["elements"]) == {B}
    assert patch["elements"][B] == {"value": {"x": 10, "y": 50}, "based_on": {"x": 200, "y": 50}}


def test_a_patch_compiled_against_a_moved_layout_is_a_conflict() -> None:
    read = _stored()
    patch = compiled_patch(read_intents([{"intent": "align", "keys": [A, B], "edge": "top"}]),
                           base=read, stored=read, drawn=DRAWN)
    moved = read_layout({"elements": {A: {"x": 10, "y": 0}, B: {"x": 999, "y": 50}, C: {"x": 500, "y": 90}}})
    with pytest.raises(LayoutConflict):
        patched(moved, read_layout_patch(patch), stored=moved)


def test_a_diagram_without_a_layout_is_patched_over_its_first_layout() -> None:
    first = _stored()
    result = _apply([{"intent": "align", "keys": [A, B], "edge": "left"}], stored=Layout(), base=first)
    assert result.elements[B].x == 10 and result.elements[C] == first.elements[C]


@pytest.mark.parametrize(("raw", "says"), [
    ([], "non-empty list"),
    ([{"intent": "rotate"}], "expected one of"),
    ([{"intent": "align", "keys": [A], "edge": "left"}], "at least 2"),
    ([{"intent": "distribute", "keys": [A, B], "axis": "x"}], "at least 3"),
    ([{"intent": "align", "keys": [A, B], "edge": "middle"}], "edge"),
    ([{"intent": "straighten", "relations": [LINE], "keys": [A]}], "does not take"),
])
def test_a_malformed_intent_is_refused_saying_why(raw: list[dict[str, object]], says: str) -> None:
    with pytest.raises(MalformedLayout, match=says):
        read_intents(raw)


def test_a_box_is_not_aligned_without_its_members() -> None:
    with pytest.raises(MalformedLayout, match="boxes move with their members"):
        _apply([{"intent": "align", "keys": [A, "rule:domain=business"], "edge": "left"}], _stored())
