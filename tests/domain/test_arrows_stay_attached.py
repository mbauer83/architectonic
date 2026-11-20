"""Arrows stay attached: what a route keeps when an element moves (I1–I4), and what is only reported (I5).

Each rule stated on a route small enough to read, beside the same route where the rule has nothing
to do. The four hundred random moves that fuzz them together need the router for I5 and live with it,
in `tests/rendering/test_relations_are_routed_around_elements.py`.
"""

from __future__ import annotations

from src.domain.diagrams.layout.attachment import (
    Breach,
    breaches_of,
    ends_conflict,
    formed_afresh,
    keep_attached,
    reattached,
)
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import LabelAnchor, Port, Route, Side

_A = Extent(0, 0, 100, 60)
_B = Extent(300, 200, 420, 260)
_C = Extent(150, 90, 250, 150)
#: Out of A's right side, down at x=160, into B's left side.
_ROUTE = Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((160, 30), (160, 230)), LabelAnchor(0.4, 6, -8))


def _moved(extent: Extent, dx: float, dy: float) -> Extent:
    return Extent(extent.left + dx, extent.top + dy, extent.right + dx, extent.bottom + dy)


class TestFollowing:
    """I3: the bend next to a moved end follows the port, and the arrow keeps its shape."""

    def test_the_bend_next_to_the_moved_end_follows_on_the_axis_that_keeps_its_run_straight(self) -> None:
        kept = reattached(_ROUTE, _moved(_A, 0, 40), _B)

        assert kept.via == ((160, 70), (160, 230))
        assert (kept.source, kept.target, kept.label) == (_ROUTE.source, _ROUTE.target, _ROUTE.label)
        assert breaches_of(kept, _moved(_A, 0, 40), _B) == ()

    def test_a_move_along_the_run_only_lengthens_it(self) -> None:
        assert reattached(_ROUTE, _moved(_A, -80, 0), _B) == _ROUTE

    def test_a_resize_moves_the_port_with_its_side_and_the_bend_with_the_port(self) -> None:
        taller = Extent(0, 0, 100, 120)

        assert reattached(_ROUTE, taller, _B).via == ((160, 60), (160, 230))

    def test_a_route_that_is_still_sound_is_returned_as_it_was(self) -> None:
        assert reattached(_ROUTE, _A, _B) == _ROUTE


class TestRepair:
    """I4: only where following is not enough — turn the end, else drop its bend, else form the arrow afresh."""

    def test_an_end_moved_past_its_bend_turns_to_the_side_the_route_lies_beyond(self) -> None:
        beyond = _moved(_A, 200, 0)
        kept = reattached(_ROUTE, beyond, _B)

        assert kept.source is not None
        assert kept.source.side is Side.LEFT
        assert len(kept.via) == len(_ROUTE.via)
        assert breaches_of(kept, beyond, _B) == ()

    def test_a_bend_the_element_now_covers_goes(self) -> None:
        tight = Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((130, 30), (130, 230)))
        over_it = Extent(60, 0, 160, 60)
        kept = reattached(tight, over_it, _B)

        assert len(kept.via) < len(tight.via)
        assert breaches_of(kept, over_it, _B) == ()

    def test_where_nothing_settles_the_arrow_is_formed_afresh_and_keeps_its_label(self) -> None:
        source, target = Extent(250, 200, 350, 260), Extent(140, 330, 260, 390)
        kept = reattached(_ROUTE, source, target)

        assert kept == formed_afresh(_ROUTE, source, target)
        assert (kept.via, kept.label) == ((), _ROUTE.label)
        assert breaches_of(kept, source, target) == ()

    def test_a_route_the_router_decides_is_not_touched(self) -> None:
        undecided = Route(via=((160, 30),))

        assert reattached(undecided, _moved(_A, 0, 40), _B) == undecided


class TestWhatNoRouteSatisfies:
    def test_two_connected_elements_closer_than_a_stub_are_a_conflict(self) -> None:
        assert ends_conflict(_A, Extent(111, 0, 211, 60))
        assert not ends_conflict(_A, Extent(112, 0, 212, 60))

    def test_a_conflict_is_reported_and_its_route_still_answered(self) -> None:
        over = Extent(60, 20, 160, 80)
        result = keep_attached({"r": _ROUTE}, ends={"r": ("a", "b")}, extents={"a": _A, "b": over}, changed=["b"])

        assert result.conflicts == ("r",)
        assert "r" in result.routes


class TestKeepingEveryArrowAttached:
    _ENDS = {"ab": ("a", "b"), "cb": ("c", "b")}
    _ROUTES = {"ab": _ROUTE, "cb": Route(Port(Side.RIGHT, 0.5), Port(Side.TOP, 0.5))}

    def test_only_the_arrows_of_what_moved_are_touched(self) -> None:
        extents = {"a": _moved(_A, 0, 40), "b": _B, "c": _C}
        result = keep_attached(self._ROUTES, ends=self._ENDS, extents=extents, changed=["a"])

        assert result.routes["cb"] is self._ROUTES["cb"]
        assert result.routes["ab"] != _ROUTE

    def test_an_arrow_a_move_made_cross_another_element_is_named_for_the_router(self) -> None:
        """I5 is found here and repaired by the router: this side only says which arrow and what it crosses."""
        in_the_way = {"a": _A, "b": _B, "c": Extent(120, 100, 220, 160)}
        result = keep_attached(self._ROUTES, ends=self._ENDS, extents=in_the_way, changed=["a"])

        assert result.crossing == {"ab": ("c",)}

    def test_an_end_drawn_inside_its_whole_does_not_cross_it(self) -> None:
        whole = {"a": _A, "b": _B, "whole": Extent(-20, -20, 200, 100)}
        result = keep_attached({"ab": _ROUTE}, ends={"ab": ("a", "b")}, extents=whole, changed=["a"])

        assert result.crossing == {}

    def test_an_arrow_whose_element_has_no_known_extent_is_left_as_it_is(self) -> None:
        result = keep_attached({"ab": _ROUTE}, ends={"ab": ("a", "b")}, extents={"a": _A}, changed=["a"])

        assert result.routes == {"ab": _ROUTE}


def test_arriving_from_behind_breaks_both_rules_at_that_end() -> None:
    behind = Route(Port(Side.RIGHT, 0.5), Port(Side.RIGHT, 0.5))

    assert set(breaches_of(behind, _A, Extent(300, 0, 400, 60))) == {Breach.TARGET_NOT_OUTWARD, Breach.THROUGH_TARGET}
