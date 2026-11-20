"""What a stated layout's geometry decides: four things no route and no stacking repairs.

Stated over small layouts built here, each wrong in exactly one way, beside the same layout put
right — so a rule that reported everything, or nothing, fails as surely as one that is off by a stub.
"""

from __future__ import annotations

import pytest

from src.domain.diagrams.authored_groupings import RuleKey
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Layout, Placed, Port, Route, Side, read_layout
from src.domain.diagrams.layout.layout_checks import (
    STUB,
    DiagramIdentities,
    LayoutDefect,
    check_layout_geometry,
    entries_naming_nothing,
    placed_extent,
    port_point,
    pruned_to,
)

_A, _B, _C = "APP@1.aaaaaa", "APP@2.bbbbbb", "APP@3.cccccc"
_AB = f"{_A}---{_B}@@archimate-serving"
_BOX = "g-Front1"
#: Two elements side by side with room between them, and a third below the first.
_EXTENTS = {_A: Extent(0, 0, 100, 60), _B: Extent(300, 0, 400, 60), _C: Extent(0, 200, 100, 260)}
_RELATIONS = {_AB: (_A, _B)}


def _found(layout: Layout, *, extents=_EXTENTS, relations=_RELATIONS, members=None) -> list[tuple[LayoutDefect, tuple]]:
    findings = check_layout_geometry(layout, extents=extents, relations=relations, members_of_box=members or {})
    return [(finding.defect, finding.subjects) for finding in findings]


def _routed(**route: object) -> Layout:
    return Layout(relations={_AB: Route(**route)})  # type: ignore[arg-type]


class TestWhereAPortLies:
    @pytest.mark.parametrize(
        ("side", "at", "point"),
        [
            (Side.TOP, 0.0, Point(0, 0)), (Side.TOP, 0.5, Point(50, 0)), (Side.BOTTOM, 1.0, Point(100, 60)),
            (Side.LEFT, 0.5, Point(0, 30)), (Side.RIGHT, 0.25, Point(100, 15)),
        ],
    )
    def test_a_port_is_a_point_on_its_side_s_border(self, side: Side, at: float, point: Point) -> None:
        """A side and a fraction, so a port off the border cannot be stated at all."""
        assert port_point(_EXTENTS[_A], Port(side, at)) == point

    def test_an_element_placed_but_not_sized_has_no_extent_until_somebody_says_what_was_drawn(self) -> None:
        assert placed_extent(Placed(10, 20)) is None
        assert placed_extent(Placed(10, 20), drawn_size=(160.0, 60.0)) == Extent(10, 20, 170, 80)
        assert placed_extent(Placed(10, 20, 100, 40), drawn_size=(160.0, 60.0)) == Extent(10, 20, 110, 60)


class TestLeavingOutward:
    """I1: each end leaves its element perpendicular to the side and outward, by at least one stub."""

    def test_a_straight_run_between_facing_sides_is_sound(self) -> None:
        assert _found(_routed(source=Port(Side.RIGHT, 0.5), target=Port(Side.LEFT, 0.5))) == []

    def test_a_first_bend_one_stub_out_is_sound_and_one_short_of_it_is_not(self) -> None:
        sound = _routed(source=Port(Side.RIGHT, 0.5), via=((100 + int(STUB), 30), (100 + int(STUB), 120)))
        short = _routed(source=Port(Side.RIGHT, 0.5), via=((100 + int(STUB) - 1, 30), (111, 120)))

        assert _found(sound) == []
        assert _found(short) == [(LayoutDefect.END_NOT_LEAVING_OUTWARD, (_AB, _A))]

    def test_leaving_along_the_border_is_not_leaving(self) -> None:
        sideways = _routed(source=Port(Side.RIGHT, 0.5), via=((100, 120),))

        assert (LayoutDefect.END_NOT_LEAVING_OUTWARD, (_AB, _A)) in _found(sideways)

    def test_leaving_at_a_slant_is_not_leaving_perpendicular(self) -> None:
        slanted = _routed(source=Port(Side.RIGHT, 0.5), via=((160, 45),))

        assert _found(slanted) == [(LayoutDefect.END_NOT_LEAVING_OUTWARD, (_AB, _A))]

    def test_the_target_end_is_asked_the_same_question(self) -> None:
        arriving_from_above = _routed(target=Port(Side.LEFT, 0.5), via=((300, -80),))

        assert (LayoutDefect.END_NOT_LEAVING_OUTWARD, (_AB, _B)) in _found(arriving_from_above)

    def test_an_end_with_no_stated_port_is_the_router_s_and_is_not_judged(self) -> None:
        assert _found(_routed(via=((200, 30),))) == []


class TestThroughItsOwnEnds:
    """I2: no segment of a relation passes through either of the elements it joins."""

    def test_a_route_doubling_back_through_its_source_is_found(self) -> None:
        back_through = _routed(source=Port(Side.RIGHT, 0.5), via=((160, 30), (160, 100), (50, 100), (50, 10)))

        assert (LayoutDefect.ROUTE_THROUGH_OWN_END, (_AB, _A)) in _found(back_through)

    def test_a_route_running_on_through_its_target_is_found(self) -> None:
        through = _routed(source=Port(Side.RIGHT, 0.5), via=((450, 30),))

        assert (LayoutDefect.ROUTE_THROUGH_OWN_END, (_AB, _B)) in _found(through)

    def test_ending_on_a_border_is_not_passing_through(self) -> None:
        assert _found(_routed(source=Port(Side.RIGHT, 0.5), target=Port(Side.LEFT, 0.5))) == []


class TestConnectedElementsOverEachOther:
    def test_two_connected_elements_that_overlap_are_a_conflict_no_route_satisfies(self) -> None:
        overlapping = {**_EXTENTS, _B: Extent(60, 20, 160, 80)}

        assert _found(Layout(), extents=overlapping) == [(LayoutDefect.CONNECTED_ELEMENTS_OVERLAP, (_AB, _A, _B))]

    def test_two_that_overlap_and_are_not_connected_are_not_this_rule_s(self) -> None:
        overlapping = {**_EXTENTS, _C: Extent(60, 20, 160, 80)}

        assert _found(Layout(), extents=overlapping) == []

    def test_an_element_drawn_inside_the_one_that_holds_it_is_not_a_conflict(self) -> None:
        nested = {**_EXTENTS, _A: Extent(0, 0, 500, 300), _B: Extent(40, 40, 140, 100)}

        assert _found(Layout(), extents=nested) == []

    def test_sharing_a_border_is_not_overlapping(self) -> None:
        touching = {**_EXTENTS, _B: Extent(100, 0, 200, 60)}

        assert _found(Layout(), extents=touching) == []


class TestABoxOverAnElementOutsideIt:
    _OVER_B = Layout(boxes={_BOX: Placed(-20, -20, 360, 120)})

    def test_a_box_over_an_element_that_is_not_its_member_hides_it(self) -> None:
        found = _found(self._OVER_B, members={_BOX: frozenset({_A})})

        assert found == [(LayoutDefect.BOX_HIDES_ELEMENT, (_BOX, _B))]

    def test_its_members_are_inside_it_not_under_it(self) -> None:
        assert _found(self._OVER_B, members={_BOX: frozenset({_A, _B})}) == []

    def test_an_element_stacked_above_the_box_is_not_hidden(self) -> None:
        stacked = Layout(boxes=self._OVER_B.boxes, z={_B: 1})

        assert _found(stacked, members={_BOX: frozenset({_A})}) == []
        assert _found(Layout(boxes=self._OVER_B.boxes, z={_B: 1, _BOX: 1}), members={_BOX: frozenset({_A})}) != []

    def test_a_part_drawn_inside_a_member_is_inside_the_box_with_it(self) -> None:
        holder_and_part = {_A: Extent(0, 0, 300, 100), _B: Extent(20, 20, 120, 80)}

        assert _found(self._OVER_B, extents=holder_and_part, relations={}, members={_BOX: frozenset({_A})}) == []

    def test_a_box_the_layout_does_not_size_hides_nothing(self) -> None:
        unsized = Layout(boxes={_BOX: Placed(-20, -20)})

        assert _found(unsized, members={_BOX: frozenset({_A})}) == []


def _business_only(key: RuleKey) -> bool:
    return "business" in key.text


def _known(**overrides: object) -> DiagramIdentities:
    stated: dict[str, object] = {
        "instances": frozenset({_A, _B, "occ-1"}), "grouping_ids": frozenset({_BOX}),
        "relations": {_AB: (_A, _B)}, "rule_admits": _business_only,
    }
    return DiagramIdentities(**{**stated, **overrides})  # type: ignore[arg-type]


class TestNamingNothing:
    _LAYOUT = read_layout({
        "elements": {_A: {"x": 0, "y": 0}, "occ-1": {"x": 0, "y": 0}, _C: {"x": 0, "y": 0}},
        "boxes": {
            _BOX: {"x": 0, "y": 0}, "g-Gone01": {"x": 0, "y": 0},
            "rule:domain=business": {"x": 0, "y": 0}, "rule:domain=strategy": {"x": 0, "y": 0},
        },
        "relations": {_AB: {}, f"{_A}---{_C}@@archimate-flow": {}, f"{_AB}@occ-9>{_B}": {}},
        "z": {_A: 1, _C: 1, _BOX: 1, "g-Gone01": 1, "rule:domain=strategy": 1},
    })

    def test_each_section_s_keys_are_asked_of_what_that_section_names(self) -> None:
        dangling = entries_naming_nothing(self._LAYOUT, _known())

        assert dangling.elements == (_C,)
        assert dangling.boxes == ("g-Gone01",)
        assert dangling.rules == ("rule:domain=strategy",)
        assert dangling.relations == (f"{_A}---{_C}@@archimate-flow", f"{_AB}@occ-9>{_B}")
        assert set(dangling.stacked) == {_C, "g-Gone01"}

    def test_pruning_drops_what_names_nothing_and_keeps_a_rule_key(self) -> None:
        kept, dangling = pruned_to(self._LAYOUT, _known())

        assert set(kept.elements) == {_A, "occ-1"}
        assert set(kept.boxes) == {_BOX, "rule:domain=business", "rule:domain=strategy"}
        assert set(kept.relations) == {_AB}
        assert set(kept.z) == {_A, _BOX, "rule:domain=strategy"}
        assert dangling.any()
        assert not entries_naming_nothing(kept, _known(rule_admits=lambda _key: True)).any()

    def test_a_layout_that_names_only_what_the_diagram_holds_is_left_as_it_is(self) -> None:
        sound = read_layout({"elements": {_A: {"x": 1, "y": 2}}, "relations": {_AB: {}}, "z": {_BOX: 3}})

        kept, dangling = pruned_to(sound, _known())

        assert kept == sound and not dangling.any()
