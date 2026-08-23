"""A container deployed on several hosts is drawn inside whichever of them the view draws.

`contained_by` was built with `sorted(host_set)[:1]` — one home per container, chosen by id order —
so a container hosted by two nodes was placed under one and every other host was drawn holding
nothing. On the shipped model the Artifact File Store is hosted by both the Developer Workstation and
the Repository Data Volume, and the workstation sorts first, so the volume rendered as an empty node:
a picture asserting that the volume a deployment mounts for repository data holds nothing.

Truncating is not obviously wrong, and that is what made it survive. `_nest` resolves containment as
a tree, because PUML declares an alias in exactly one place, so one child genuinely has one parent.
What the truncation threw away was not the second placement — that was never drawable — but the
*choice* of which one to draw, before the view knew which hosts it was keeping.

So the projection now reports every placement and the resolver picks among the ones it is drawing.
That is what makes a deployment view narrowed to one topology correct: with the workstation filtered
out by `_excluded_entity_ids`, the file store's remaining host is the volume, and it belongs inside
it. Truncated first, the file store lost its only surviving parent and floated to the top level.

Order is still deterministic where several hosts survive — first by id, as before — so an unfiltered
view is unchanged, and `_undrawn_host_report` is what says the other placement exists.
"""

from __future__ import annotations

from src.diagram_types.c4._resolve import _ResolvedItem
from src.diagram_types.c4._resolve_nesting import _nest


def _item(local_id: str) -> _ResolvedItem:
    return _ResolvedItem(
        alias=f"A_{local_id}", local_id=local_id, label=local_id, item_type="container",
        description="", technology="", external=False,
    )


def _tree(items: list[_ResolvedItem], pairs: tuple[tuple[str, str], ...]):
    """The nesting, as a map of parent local_id -> the local_ids drawn inside it."""
    nested = _nest(items, pairs)
    return {top.local_id: sorted(child.local_id for child in top.children) for top in nested}


class TestAContainerWithTwoHosts:
    def test_it_is_drawn_in_the_host_that_survives_the_view(self) -> None:
        """The case two deployment scenarios need: one host filtered out of the view entirely."""
        items = [_item("volume"), _item("store")]

        assert _tree(items, (("store", "workstation"), ("store", "volume"))) == {
            "volume": ["store"],
        }

    def test_it_is_drawn_once_when_both_hosts_survive(self) -> None:
        """PUML declares an alias in one place, so two drawings are not available — and the choice
        stays what it was, the first host by id."""
        items = [_item("volume"), _item("workstation"), _item("store")]

        assert _tree(items, (("store", "volume"), ("store", "workstation"))) == {
            "volume": ["store"], "workstation": [],
        }

    def test_the_choice_does_not_depend_on_the_order_the_pairs_arrive_in(self) -> None:
        items = [_item("volume"), _item("workstation"), _item("store")]
        forward = _tree(items, (("store", "volume"), ("store", "workstation")))
        reversed_pairs = _tree(items, (("store", "workstation"), ("store", "volume")))

        assert forward == reversed_pairs

    def test_a_host_that_is_not_drawn_does_not_swallow_the_container(self) -> None:
        """The defect the truncation caused: the only recorded parent was absent from the view, so
        the container had nowhere to go and was drawn at the top level beside its own host."""
        items = [_item("volume"), _item("store")]

        assert _tree(items, (("store", "workstation"),)) == {"volume": [], "store": []}


class TestWhatDidNotChange:
    def test_a_single_placement_still_nests(self) -> None:
        items = [_item("host"), _item("store")]

        assert _tree(items, (("store", "host"),)) == {"host": ["store"]}

    def test_a_chain_of_three_still_nests_bottom_up(self) -> None:
        items = [_item("machine"), _item("runtime"), _item("app")]

        nested = _nest(items, (("app", "runtime"), ("runtime", "machine")))

        assert [i.local_id for i in nested] == ["machine"]
        assert [c.local_id for c in nested[0].children] == ["runtime"]
        assert [c.local_id for c in nested[0].children[0].children] == ["app"]

    def test_no_containment_leaves_the_list_alone(self) -> None:
        items = [_item("a"), _item("b")]

        assert [i.local_id for i in _nest(items, ())] == ["a", "b"]

    def test_a_cycle_still_terminates(self) -> None:
        items = [_item("a"), _item("b")]

        nested = _nest(items, (("a", "b"), ("b", "a")))

        assert nested is not None
