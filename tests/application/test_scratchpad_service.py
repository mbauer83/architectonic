"""The service both surfaces drive.

The convenience methods matter more than they look: an agent has no canvas, so it needs to say "add
this note" without reconstructing the document, while the canvas mutates in memory and saves whole.
Both must reach storage the same way, or one surface acquires a path the other lacks and parity
becomes a claim rather than a property.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.scratchpad.ports import ScratchpadVersionConflictError
from src.application.scratchpad.service import DEFAULT_AREAS, ScratchpadService
from src.domain.scratchpad import Point, ScratchpadError
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository


@pytest.fixture
def service(tmp_path: Path) -> ScratchpadService:
    return ScratchpadService(YamlScratchpadRepository(tmp_path))


def _new(service: ScratchpadService, **overrides: object):
    defaults: dict[str, object] = {
        "artifact_id": "SCR@1.a.pad", "name": "Thinking", "group": "strategy-and-value",
    }
    return service.create(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestCreate:
    def test_a_new_scratchpad_is_seeded_with_the_four_areas(self, service: ScratchpadService) -> None:
        """An empty canvas answers none of 'what goes where'."""
        created = _new(service)

        assert {area.id for area in created.areas} == {area_id for area_id, _ in DEFAULT_AREAS}

    def test_the_seeded_frames_are_placed_so_they_do_not_overlap(self, service: ScratchpadService) -> None:
        """Overlapping frames would make every seeded note's area depend on declaration order."""
        rects = sorted(_new(service).layout.areas.values(), key=lambda rect: rect.y)

        for upper, lower in zip(rects, rects[1:], strict=False):
            assert upper.y + upper.height <= lower.y

    def test_seeding_can_be_declined(self, service: ScratchpadService) -> None:
        assert _new(service, seed_areas=False).areas == ()

    def test_creating_over_an_existing_id_is_refused(self, service: ScratchpadService) -> None:
        _new(service)

        with pytest.raises(ScratchpadVersionConflictError):
            _new(service)


class TestTheAgentPathAndTheCanvasPathAgree:
    def test_a_note_added_one_at_a_time_lands_where_the_canvas_would_put_it(
        self, service: ScratchpadService
    ) -> None:
        created = _new(service)

        after = service.add_note(created.artifact_id, note_id="n1", title="Grow into mid-market", at=Point(40, 60))

        assert after.note("n1").title == "Grow into mid-market"
        assert after.layout.notes["n1"] == Point(40, 60)
        assert after.area_of("n1") == "strategy"

    def test_an_edit_saves_back_into_the_collection_it_came_from(self, service: ScratchpadService) -> None:
        """Regression: the group was inferred rather than asked for, so every edit re-homed the
        scratchpad to a default collection. The port declares `group_of` for exactly this."""
        created = _new(service, group="platform-core")

        service.add_note(created.artifact_id, note_id="n1", title="A")

        assert service.list_scratchpads()[0].group == "platform-core"

    def test_each_convenience_write_moves_the_version_on(self, service: ScratchpadService) -> None:
        created = _new(service)

        after = service.add_note(created.artifact_id, note_id="n1", title="A")

        assert after.version != created.version

    def test_adding_a_note_that_exists_is_refused_rather_than_silently_replacing(
        self, service: ScratchpadService
    ) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A")

        with pytest.raises(ScratchpadError, match="already exists"):
            service.add_note(created.artifact_id, note_id="n1", title="B")

    def test_moving_a_note_changes_which_area_it_is_in(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A", at=Point(40, 60))
        portfolio_rect = service.read(created.artifact_id).layout.areas["portfolio"]

        after = service.move_note(
            created.artifact_id, note_id="n1", to=Point(portfolio_rect.x + 40, portfolio_rect.y + 40)
        )

        assert after.area_of("n1") == "portfolio"

    def test_a_link_needs_both_its_notes(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A")

        with pytest.raises(ScratchpadError, match="not a note in this scratchpad"):
            service.add_link(created.artifact_id, link_id="l1", source="n1", target="ghost")

    def test_removing_a_note_removes_its_links(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A")
        service.add_note(created.artifact_id, note_id="n2", title="B")
        service.add_link(created.artifact_id, link_id="l1", source="n1", target="n2")

        after = service.remove_note(created.artifact_id, note_id="n1")

        assert after.links == ()

    def test_renaming_keeps_everything_else_about_the_note(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A", at=Point(40, 60), body="why")

        after = service.rename_note(created.artifact_id, note_id="n1", title="A, sharpened")

        assert after.note("n1").body == "why"
        assert after.layout.notes["n1"] == Point(40, 60)


class TestReplaceIsWholeAndVersioned:
    def test_a_write_against_a_stale_version_is_refused(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A")

        with pytest.raises(ScratchpadVersionConflictError):
            service.replace(created, group="strategy-and-value", expected_version=created.version)

    def test_an_invalid_aggregate_never_reaches_storage(self, service: ScratchpadService) -> None:
        from dataclasses import replace as dataclass_replace

        from src.domain.scratchpad import Link

        created = _new(service)
        broken = dataclass_replace(created, links=(Link(id="l1", source="ghost", target="other"),))

        with pytest.raises(ScratchpadError):
            service.replace(broken, group="strategy-and-value", expected_version=created.version)
        assert service.read(created.artifact_id).links == ()


class TestListAndDelete:
    def test_listing_summarises_without_the_notes(self, service: ScratchpadService) -> None:
        created = _new(service)
        service.add_note(created.artifact_id, note_id="n1", title="A")

        summary = service.list_scratchpads()[0]

        assert (summary.name, summary.note_count) == ("Thinking", 1)
        assert not hasattr(summary, "notes")

    def test_delete_removes_it_from_the_listing(self, service: ScratchpadService) -> None:
        created = _new(service)

        service.delete(created.artifact_id)

        assert service.list_scratchpads() == []
