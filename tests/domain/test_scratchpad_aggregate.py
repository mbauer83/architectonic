"""The scratchpad aggregate holds its invariants, and is permissive about everything else.

The permissiveness is the point and is asserted as deliberately as the refusals: the feature exists
because the typed model asks for a type before anything has been decided, so an aggregate that
demanded one would reproduce the wall it removes.
"""

from __future__ import annotations

import pytest

from src.domain.scratchpad import (
    UNFILED,
    Area,
    Group,
    Layout,
    Link,
    ModelRef,
    Note,
    Point,
    Rect,
    Scratchpad,
    ScratchpadError,
    scratchpad_from_parts,
)


def _pad(**overrides: object) -> Scratchpad:
    defaults: dict[str, object] = {"artifact_id": "SCR@1.a.pad", "name": "Pad"}
    return scratchpad_from_parts(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestANoteNeedsOnlyATitle:
    def test_a_bare_title_is_a_complete_note(self) -> None:
        pad = _pad(notes=[Note(id="n1", title="Grow into mid-market")])

        assert pad.note("n1") is not None
        assert pad.note("n1").destination == "undecided"

    def test_an_untitled_note_is_refused(self) -> None:
        with pytest.raises(ScratchpadError, match="no title"):
            _pad(notes=[Note(id="n1", title="   ")])

    def test_ids_are_unique_within_the_scratchpad(self) -> None:
        with pytest.raises(ScratchpadError, match="duplicate note id"):
            _pad(notes=[Note(id="n1", title="A"), Note(id="n1", title="B")])


class TestLinksJoinNotesOfThisScratchpad:
    def test_an_endpoint_outside_the_scratchpad_is_refused(self) -> None:
        with pytest.raises(ScratchpadError, match="target 'ghost' that is not a note"):
            _pad(notes=[Note(id="n1", title="A")], links=[Link(id="l1", source="n1", target="ghost")])

    def test_a_self_link_is_refused(self) -> None:
        with pytest.raises(ScratchpadError, match="to itself"):
            _pad(notes=[Note(id="n1", title="A")], links=[Link(id="l1", source="n1", target="n1")])

    def test_deleting_a_note_deletes_its_links(self) -> None:
        pad = _pad(
            notes=[Note(id="n1", title="A"), Note(id="n2", title="B")],
            links=[Link(id="l1", source="n1", target="n2")],
        )

        assert pad.without_note("n1").links == ()

    def test_deleting_a_realized_note_leaves_the_model_alone(self) -> None:
        """Invariant 6: what a lift put into the model is not the scratchpad's to retract."""
        pad = _pad(notes=[Note(
            id="n1", title="A", destination="element",
            model_ref=ModelRef(artifact_id="CAP@1.a.thing", kind="realized"),
        )])

        after = pad.without_note("n1")

        assert after.notes == ()
        # Nothing in the aggregate records a retraction, because none is performed.
        assert not hasattr(after, "retracted")


class TestAreaMembershipIsSpatial:
    def _framed(self) -> Scratchpad:
        return _pad(
            areas=[Area(id="strategy", label="Vision & strategy"), Area(id="portfolio", label="Portfolio")],
            notes=[Note(id="n1", title="A")],
            layout=Layout(
                areas={"strategy": Rect(0, 0, 1200, 600), "portfolio": Rect(0, 640, 1200, 600)},
                notes={"n1": Point(40, 60)},
            ),
        )

    def test_a_note_belongs_to_the_frame_that_contains_it(self) -> None:
        assert self._framed().area_of("n1") == "strategy"

    def test_dragging_it_into_another_frame_is_what_refiles_it(self) -> None:
        moved = self._framed().moved("n1", Point(320, 700))

        assert moved.area_of("n1") == "portfolio"
        assert moved.notes_in("portfolio") == (moved.note("n1"),)

    def test_a_note_in_no_frame_is_unfiled_rather_than_an_error(self) -> None:
        """Thinking starts in the margin; unfiled is a legitimate place to be."""
        assert self._framed().moved("n1", Point(5000, 5000)).area_of("n1") == UNFILED

    def test_a_note_with_no_position_at_all_is_unfiled(self) -> None:
        assert _pad(notes=[Note(id="n1", title="A")]).area_of("n1") == UNFILED

    def test_overlapping_frames_resolve_to_the_smallest_containing_one(self) -> None:
        """What a person means by dropping a note into a small frame sitting on a large one."""
        pad = _pad(
            areas=[Area(id="big", label="Big"), Area(id="small", label="Small")],
            notes=[Note(id="n1", title="A")],
            layout=Layout(
                areas={"big": Rect(0, 0, 500, 500), "small": Rect(100, 100, 300, 300)},
                notes={"n1": Point(150, 150)},
            ),
        )

        assert pad.area_of("n1") == "small"

    def test_containment_does_not_depend_on_the_order_areas_happen_to_be_in(self) -> None:
        """Regression: it read z-order off declaration order, and the file is written in stable id
        order — so saving a scratchpad could silently move a note into a different frame."""
        layout = Layout(
            areas={"big": Rect(0, 0, 500, 500), "small": Rect(100, 100, 300, 300)},
            notes={"n1": Point(150, 150)},
        )
        one_way = _pad(
            areas=[Area(id="big", label="Big"), Area(id="small", label="Small")],
            notes=[Note(id="n1", title="A")], layout=layout,
        )
        other_way = _pad(
            areas=[Area(id="small", label="Small"), Area(id="big", label="Big")],
            notes=[Note(id="n1", title="A")], layout=layout,
        )

        assert one_way.area_of("n1") == other_way.area_of("n1") == "small"


class TestGroups:
    def _two_areas(self, **layout_overrides: object) -> Scratchpad:
        return _pad(
            areas=[Area(id="a", label="A"), Area(id="b", label="B")],
            notes=[Note(id="n1", title="One"), Note(id="n2", title="Two")],
            groups=[Group(id="g1", label="Cluster", members=("n1", "n2"))],
            layout=Layout(
                areas={"a": Rect(0, 0, 500, 500), "b": Rect(0, 600, 500, 500)},
                **layout_overrides,  # type: ignore[arg-type]
            ),
        )

    def test_a_group_whose_members_share_an_area_is_fine(self) -> None:
        assert self._two_areas(notes={"n1": Point(10, 10), "n2": Point(20, 20)}).groups[0].members == ("n1", "n2")

    def test_a_group_spanning_two_areas_is_refused(self) -> None:
        with pytest.raises(ScratchpadError, match="spans areas"):
            self._two_areas(notes={"n1": Point(10, 10), "n2": Point(10, 650)})

    def test_a_note_belongs_to_at_most_one_group(self) -> None:
        with pytest.raises(ScratchpadError, match="belongs to at most one"):
            _pad(
                notes=[Note(id="n1", title="One")],
                groups=[Group(id="g1", label="A", members=("n1",)), Group(id="g2", label="B", members=("n1",))],
            )

    def test_deleting_a_note_removes_it_from_its_group(self) -> None:
        pad = self._two_areas(notes={"n1": Point(10, 10), "n2": Point(20, 20)})

        assert pad.without_note("n1").groups[0].members == ("n2",)


class TestTheMetaOntologyFreezes:
    def test_it_may_change_while_nothing_is_typed(self) -> None:
        pad = _pad(notes=[Note(id="n1", title="A")])

        assert pad.with_meta_ontology("sysml-v2-min").meta_ontology == "sysml-v2-min"

    def test_it_may_not_change_once_a_note_is_typed(self) -> None:
        pad = _pad(notes=[Note(id="n1", title="A", destination="element", element_type="goal")])

        with pytest.raises(ScratchpadError, match="while notes are typed"):
            pad.with_meta_ontology("sysml-v2-min")

    def test_setting_it_to_what_it_already_is_is_not_a_change(self) -> None:
        """Otherwise a round-trip through save would fail on a scratchpad that types anything."""
        pad = _pad(notes=[Note(id="n1", title="A", destination="element", element_type="goal")])

        assert pad.with_meta_ontology(pad.meta_ontology) == pad


class TestGeometryIsWrittenOnTheGrid:
    def test_a_placement_snaps(self) -> None:
        """A sub-pixel pointer position must not become a line in a diff."""
        pad = _pad(notes=[Note(id="n1", title="A")]).moved("n1", Point(41.4, 58.9))

        assert pad.layout.notes["n1"] == Point(40, 60)

    def test_construction_snaps_too(self) -> None:
        pad = _pad(
            areas=[Area(id="a", label="A")],
            notes=[Note(id="n1", title="A")],
            layout=Layout(areas={"a": Rect(1.2, 2.9, 99.4, 99.4)}, notes={"n1": Point(3.3, 4.1)}),
        )

        assert pad.layout.notes["n1"] == Point(5, 5)
        assert pad.layout.areas["a"] == Rect(0, 5, 100, 100)


class TestMutationsReturnAValidatedAggregate:
    def test_a_mutation_that_would_break_an_invariant_raises_and_changes_nothing(self) -> None:
        pad = _pad(notes=[Note(id="n1", title="A")])

        with pytest.raises(ScratchpadError):
            pad.with_link(Link(id="l1", source="n1", target="ghost"))
        assert pad.links == ()

    def test_removing_something_that_is_not_there_says_so(self) -> None:
        pad = _pad()

        with pytest.raises(ScratchpadError, match="no note 'ghost'"):
            pad.without_note("ghost")
        with pytest.raises(ScratchpadError, match="no link 'ghost'"):
            pad.without_link("ghost")
