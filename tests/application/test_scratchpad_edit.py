"""Editing a scratchpad by delta, rather than by sending it back whole.

`replace` priced the smallest edit at the size of the canvas: an agent removing one note had to read
a hundred and send them all back. This is the same write at a payload proportional to the change —
so the properties worth pinning are that it is *the same write* (same invariants, same version
token, same cascade) and that its one deliberate difference from `replace` behaves as documented:
under `replace` omission is removal, and here omission means "leave it alone".
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.application.scratchpad.edit import ScratchpadEdit, apply_edit
from src.application.scratchpad.ports import ScratchpadVersionConflictError
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import Link, ModelRef, Note, Point, Scratchpad, ScratchpadError
from src.infrastructure.scratchpad.bulk_write_lift import BulkWriteLiftWriter
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository


@pytest.fixture
def service(tmp_path: Path) -> ScratchpadService:
    return ScratchpadService(
        YamlScratchpadRepository(tmp_path), None, BulkWriteLiftWriter(tmp_path),  # type: ignore[arg-type]
    )


@pytest.fixture
def stored(service: ScratchpadService) -> Scratchpad:
    """Two notes, one typed, joined by a link — the smallest canvas with something to lose."""
    created = service.create(artifact_id="SCR@1.a.pad", name="Thinking", group="strategy-and-value")
    both = created.with_note(Note(id="n1", title="One"), at=Point(40, 60)).with_note(
        Note(id="n2", title="Two"), at=Point(300, 60)
    )
    typed = both.typed("n1", element_type="outcome")
    return service.replace(
        typed.with_link(Link(id="l1", source="n1", target="n2")),
        group="strategy-and-value",
        expected_version=created.version,
    )


def _edit(service: ScratchpadService, stored: Scratchpad, **fields: object) -> Scratchpad:
    return service.edit(
        stored.artifact_id,
        edit=ScratchpadEdit(**fields),  # type: ignore[arg-type]
        expected_version=stored.version,
    )


class TestRemoval:
    def test_a_link_goes_without_taking_its_notes(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        after = _edit(service, stored, remove={"links": ["l1"]})

        assert after.links == ()
        assert {note.id for note in after.notes} == {"n1", "n2"}

    def test_a_note_takes_its_links_and_its_placement_with_it(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        """The cascade is the aggregate's, not restated here — otherwise "remove a note" would mean
        two different things depending on which surface asked."""
        after = _edit(service, stored, remove={"notes": ["n1"]})

        assert {note.id for note in after.notes} == {"n2"}
        assert after.links == ()
        assert "n1" not in after.layout.notes

    def test_removing_something_that_is_not_there_is_refused(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        with pytest.raises(ScratchpadError, match="no note 'nope'"):
            _edit(service, stored, remove={"notes": ["nope"]})


class TestUpsert:
    def test_a_key_left_out_of_a_patch_keeps_its_stored_value(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        """The one deliberate difference from `replace`, where omission *is* removal."""
        after = _edit(service, stored, upsert={"notes": [{"id": "n1", "body": "Now with a body"}]})

        assert after.note("n1").body == "Now with a body"
        assert after.note("n1").element_type == "outcome"
        assert after.note("n1").title == "One"

    def test_a_key_set_to_null_clears_it(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        after = _edit(
            service,
            stored,
            upsert={"notes": [{"id": "n1", "element-type": None, "destination": None}]},
        )

        assert after.note("n1").element_type is None
        assert after.note("n1").destination == "undecided"

    def test_an_unknown_id_creates_the_row(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        """How a note is added without sending the canvas — the reason this exists at all."""
        after = _edit(service, stored, upsert={"notes": [{"id": "n3", "title": "Third"}]})

        assert after.note("n3").title == "Third"
        assert len(after.notes) == 3

    def test_a_patch_with_no_id_is_refused(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        with pytest.raises(ScratchpadError, match="needs an `id`"):
            _edit(service, stored, upsert={"notes": [{"title": "Nameless"}]})


class TestPlacement:
    def test_a_note_is_moved_by_coordinates_alone(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        portfolio = stored.layout.areas["portfolio"]

        after = _edit(
            service, stored,
            layout={"notes": {"n1": [portfolio.x + 40, portfolio.y + 40]}},
        )

        # Area membership is where a note *is*, so a placement is what changes it.
        assert after.area_of("n1") == "portfolio"


class TestItIsTheSameWrite:
    def test_the_aggregate_still_refuses_what_it_always_refused(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        with pytest.raises(ScratchpadError, match="not a note in this scratchpad"):
            _edit(service, stored, upsert={"links": [{"id": "l2", "source": "n1", "target": "ghost"}]})

    def test_a_stale_version_is_refused_exactly_as_a_replace_is(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        _edit(service, stored, remove={"links": ["l1"]})

        with pytest.raises(ScratchpadVersionConflictError):
            _edit(service, stored, remove={"notes": ["n2"]})

    def test_it_moves_the_version_on(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        after = _edit(service, stored, remove={"links": ["l1"]})

        assert after.version != stored.version


class TestARefusalRatherThanASilentNoOp:
    def test_an_edit_that_changes_nothing_is_refused(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        with pytest.raises(ScratchpadError, match="changes nothing"):
            _edit(service, stored)

    def test_a_collection_a_scratchpad_does_not_have_is_refused(
        self, service: ScratchpadService, stored: Scratchpad
    ) -> None:
        """A typo would otherwise be a write that reports success and changes nothing, which is the
        worst answer available."""
        with pytest.raises(ScratchpadError, match="no such collection"):
            _edit(service, stored, remove={"nodes": ["n1"]})


def test_a_realized_note_can_be_removed_and_its_entity_is_untouched(stored: Scratchpad) -> None:
    """Invariant 6, seen from the new surface. The scratchpad never retracts model content, so
    removing a realized note removes the *thinking* — the entity a lift created outlives it, exactly
    as an entity created any other way would. Nothing here reaches the model to check, and that is
    the point: no path from this delta touches it."""
    realized = stored.with_note(
        replace(
            stored.note("n1"),  # type: ignore[arg-type]
            model_ref=ModelRef(artifact_id="OUT@1.aa.one", kind="realized"),
        )
    )
    assert realized.note("n1").model_ref is not None  # type: ignore[union-attr]

    after = apply_edit(realized, ScratchpadEdit(remove={"notes": ["n1"]}))

    assert after.note("n1") is None
    assert after.links == ()
