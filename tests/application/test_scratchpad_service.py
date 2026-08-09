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
from src.infrastructure.scratchpad.bulk_write_lift import BulkWriteLiftWriter
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository


@pytest.fixture
def service(tmp_path: Path) -> ScratchpadService:
    # The registry is only reached to build link verdicts for a lift, and nothing here lifts; the
    # lift path has its own suite, where the writer is a recorder rather than a repository.
    return ScratchpadService(
        YamlScratchpadRepository(tmp_path), None, BulkWriteLiftWriter(tmp_path),  # type: ignore[arg-type]
    )


def _new(service: ScratchpadService, **overrides: object):
    defaults: dict[str, object] = {
        "artifact_id": "SCR@1.a.pad", "name": "Thinking", "group": "strategy-and-value",
    }
    return service.create(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestCreate:
    def test_a_new_scratchpad_is_seeded_with_the_four_areas(self, service: ScratchpadService) -> None:
        """An empty canvas answers none of 'what goes where'."""
        created = _new(service)

        assert {area.id for area in created.areas} == {area_id for area_id, *_ in DEFAULT_AREAS}

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


class TestEveryEditIsAWholeAggregateReplace:
    """There is no per-item write, on either surface.

    A read-modify-replace is what the canvas does and what an agent does, so neither has a path
    into storage the other lacks — which is what makes the parity requirement a property of the
    design rather than something to police tool by tool.
    """

    def _with_note(self, service: ScratchpadService, created, note_id: str, at: Point | None = None):
        from src.domain.scratchpad import Note

        return service.replace(
            created.with_note(Note(id=note_id, title=f"Note {note_id}"), at=at),
            group=service.group_of(created.artifact_id),
            expected_version=created.version,
        )

    def test_a_note_added_this_way_lands_where_it_was_put(self, service: ScratchpadService) -> None:
        created = _new(service)

        after = self._with_note(service, created, "n1", at=Point(40, 60))

        assert after.note("n1").title == "Note n1"
        assert after.layout.notes["n1"] == Point(40, 60)
        assert after.area_of("n1") == "strategy"

    def test_an_edit_saves_back_into_the_collection_it_came_from(self, service: ScratchpadService) -> None:
        """Regression: the group was inferred rather than asked for, so every edit re-homed the
        scratchpad to a default collection. The port declares `group_of` for exactly this."""
        created = _new(service, group="platform-core")

        self._with_note(service, created, "n1")

        assert service.list_scratchpads()[0].group == "platform-core"

    def test_each_write_moves_the_version_on(self, service: ScratchpadService) -> None:
        created = _new(service)

        after = self._with_note(service, created, "n1")

        assert after.version != created.version

    def test_moving_a_note_changes_which_area_it_is_in(self, service: ScratchpadService) -> None:
        created = _new(service)
        with_note = self._with_note(service, created, "n1", at=Point(40, 60))
        portfolio = with_note.layout.areas["portfolio"]

        after = service.replace(
            with_note.moved("n1", Point(portfolio.x + 40, portfolio.y + 40)),
            group="strategy-and-value", expected_version=with_note.version,
        )

        assert after.area_of("n1") == "portfolio"


class TestReplaceIsWholeAndVersioned:
    def test_a_write_against_a_stale_version_is_refused(self, service: ScratchpadService) -> None:
        from src.domain.scratchpad import Note

        created = _new(service)
        service.replace(created.with_note(Note(id="n1", title="A")),
                        group="strategy-and-value", expected_version=created.version)

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
        from src.domain.scratchpad import Note

        created = _new(service)
        service.replace(created.with_note(Note(id="n1", title="A")),
                        group="strategy-and-value", expected_version=created.version)

        summary = service.list_scratchpads()[0]

        assert (summary.name, summary.note_count) == ("Thinking", 1)
        assert not hasattr(summary, "notes")

    def test_delete_removes_it_from_the_listing(self, service: ScratchpadService) -> None:
        created = _new(service)

        service.delete(created.artifact_id)

        assert service.list_scratchpads() == []
