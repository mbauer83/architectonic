"""A scratchpad on disk round-trips, and stays reviewable.

"Reviewable" is a real requirement rather than a nicety: the whole argument for keeping scratchpads
in the git-versioned repository (ADR@1780761609) rests on a human being able to read the diff. Two
properties carry that, and neither is enforced by the aggregate — both are serialisation, so both
are asserted here: collections written in stable id order, and geometry in one block at the end, on
the grid.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from src.application.scratchpad.document import from_document, to_document
from src.application.scratchpad.ports import ScratchpadNotFoundError, ScratchpadVersionConflictError
from src.domain.scratchpad import (
    Area,
    Group,
    Layout,
    Link,
    ModelRef,
    Note,
    Point,
    Rect,
    Scratchpad,
    scratchpad_from_parts,
)
from src.infrastructure.scratchpad.yaml_repository import SUFFIX, YamlScratchpadRepository


def _pad(**overrides: object):
    defaults: dict[str, object] = {
        "artifact_id": "SCR@1786300000.a7Kd2p.q3-portfolio-thinking",
        "name": "Q3 portfolio thinking",
        "description": "Where the mid-market question is being worked out.",
        "areas": [Area(id="strategy", label="Vision & strategy", permitted_element_types=("goal", "driver"))],
        "notes": [
            Note(id="n2", title="Self-serve onboarding", destination="element",
                 element_type="capability",
                 model_ref=ModelRef(artifact_id="CAP@1.a.onboarding", kind="bound")),
            Note(id="n1", title="Grow into mid-market"),
        ],
        "links": [Link(id="l1", source="n1", target="n2")],
        "layout": Layout(
            areas={"strategy": Rect(0, 0, 1200, 600)},
            notes={"n1": Point(40, 60), "n2": Point(320, 60)},
        ),
    }
    return scratchpad_from_parts(**{**defaults, **overrides})  # type: ignore[arg-type]


def _renamed(scratchpad: Scratchpad, name: str) -> Scratchpad:
    """A change to content, so a save is a write rather than a no-op."""
    return replace(scratchpad, name=name)


@pytest.fixture
def repo(tmp_path: Path) -> YamlScratchpadRepository:
    return YamlScratchpadRepository(tmp_path)


class TestRoundTrip:
    def test_everything_authored_survives_a_save_and_load(self, repo: YamlScratchpadRepository) -> None:
        saved = repo.save(_pad(), group="strategy-and-value")

        loaded = repo.load(saved.artifact_id)

        assert loaded.name == "Q3 portfolio thinking"
        assert loaded.description.startswith("Where the mid-market")
        assert {note.id for note in loaded.notes} == {"n1", "n2"}
        assert loaded.note("n2").model_ref == ModelRef(artifact_id="CAP@1.a.onboarding", kind="bound")
        assert loaded.links[0].source == "n1"
        assert loaded.area("strategy").permitted_element_types == ("goal", "driver")
        assert loaded.layout.notes["n1"] == Point(40, 60)
        assert loaded.area_of("n1") == "strategy"

    def test_it_is_found_by_its_short_id_too(self, repo: YamlScratchpadRepository) -> None:
        """The rest of the repository addresses artifacts by the rename-stable short form."""
        saved = repo.save(_pad(), group="strategy-and-value")

        assert repo.load("SCR@1786300000.a7Kd2p").artifact_id == saved.artifact_id

    def test_a_missing_scratchpad_is_a_lookup_failure_not_a_crash(self, repo: YamlScratchpadRepository) -> None:
        with pytest.raises(ScratchpadNotFoundError):
            repo.load("SCR@9.z.nothing")


class TestTheFileStaysReviewable:
    def _document(self, repo: YamlScratchpadRepository, tmp_path: Path) -> dict:
        repo.save(_pad(), group="strategy-and-value")
        path = next((tmp_path / "scratchpads").rglob(f"*{SUFFIX}"))
        return yaml.safe_load(path.read_text())

    def test_collections_are_written_in_stable_id_order(
        self, repo: YamlScratchpadRepository, tmp_path: Path
    ) -> None:
        """Authored n2-then-n1; stored n1-then-n2, so re-serialising never reorders."""
        document = self._document(repo, tmp_path)

        assert [note["id"] for note in document["notes"]] == ["n1", "n2"]

    def test_geometry_is_one_block_at_the_end_and_nowhere_else(
        self, repo: YamlScratchpadRepository, tmp_path: Path
    ) -> None:
        document = self._document(repo, tmp_path)

        assert list(document)[-1] == "layout"
        for note in document["notes"]:
            assert not {"x", "y", "position", "geometry"} & set(note)

    def test_re_saving_an_unchanged_scratchpad_produces_no_diff_at_all(
        self, repo: YamlScratchpadRepository, tmp_path: Path
    ) -> None:
        """The property the whole ordering rule exists for: no diff from a no-op save.

        Including the version. A save that stores what is already stored is not a write, so it
        leaves no modified file in git and invalidates nobody else's token.
        """
        first = repo.save(_pad(), group="strategy-and-value")
        path = next((tmp_path / "scratchpads").rglob(f"*{SUFFIX}"))
        before = path.read_text()

        again = repo.save(first, group="strategy-and-value", expected_version=first.version)

        assert path.read_text() == before
        assert again.version == first.version

    def test_a_sub_grid_drag_stores_nothing_because_it_snaps_to_where_it_was(
        self, repo: YamlScratchpadRepository, tmp_path: Path
    ) -> None:
        """The reported case: a drag too small to leave the grid cell reaches the file as nothing."""
        first = repo.save(_pad(), group="strategy-and-value")
        path = next((tmp_path / "scratchpads").rglob(f"*{SUFFIX}"))
        before = path.read_text()

        nudged = repo.save(
            first.moved("n1", Point(41.4, 58.9)),
            group="strategy-and-value",
            expected_version=first.version,
        )

        assert path.read_text() == before
        assert nudged.version == first.version

    def test_a_sub_pixel_drag_does_not_reach_the_file(self, repo: YamlScratchpadRepository) -> None:
        saved = repo.save(
            _pad(layout=Layout(notes={"n1": Point(41.4, 58.9), "n2": Point(320, 60)})),
            group="strategy-and-value",
        )

        assert saved.layout.notes["n1"] == Point(40, 60)

    def test_nothing_uninformative_is_written(self, repo: YamlScratchpadRepository, tmp_path: Path) -> None:
        """A file of `null`s reads as a file of decisions; an untyped note should look untyped."""
        document = self._document(repo, tmp_path)
        untyped = next(note for note in document["notes"] if note["id"] == "n1")

        assert set(untyped) == {"id", "title"}


class TestConcurrency:
    def test_a_second_writer_working_from_a_stale_version_is_refused(
        self, repo: YamlScratchpadRepository
    ) -> None:
        first = repo.save(_pad(), group="strategy-and-value")
        second = repo.save(
            _renamed(first, "Renamed once"), group="strategy-and-value",
            expected_version=first.version,
        )

        assert second.version != first.version
        with pytest.raises(ScratchpadVersionConflictError, match="has moved on"):
            repo.save(
                _renamed(first, "Renamed twice"), group="strategy-and-value",
                expected_version=first.version,
            )

    def test_creating_over_an_existing_id_is_refused_rather_than_silently_replacing(
        self, repo: YamlScratchpadRepository
    ) -> None:
        saved = repo.save(_pad(), group="strategy-and-value")

        with pytest.raises(ScratchpadVersionConflictError):
            repo.save(saved, group="strategy-and-value", expected_version=None)

    def test_the_version_moves_on_every_write_that_changes_something(
        self, repo: YamlScratchpadRepository
    ) -> None:
        first = repo.save(_pad(), group="strategy-and-value")
        second = repo.save(
            _renamed(first, "Renamed"), group="strategy-and-value", expected_version=first.version
        )

        assert (first.version, second.version) == ("0.1.1", "0.1.2")


class TestTheStoreOwnsTheVersion:
    """The stored version is derived from what the store holds, never from the caller's document.

    The wire contract calls the in-document `version` "read back and ignored here", and the token
    travels beside the document. Bumping the caller's copy instead of the store's is what let a
    client that omits it drive the stored version *backwards*, after which every writer's token
    validates forever and the conflict check protects nobody.
    """

    def _stored_at(self, repo: YamlScratchpadRepository, version: str):
        """A stored scratchpad whose version is `version`, reached by writing until it gets there."""
        stored = repo.save(_pad(), group="strategy-and-value")
        while stored.version != version:
            stored = repo.save(
                _renamed(stored, f"Pass {stored.version}"), group="strategy-and-value",
                expected_version=stored.version,
            )
        return stored

    def test_a_document_carrying_an_older_version_cannot_drive_the_store_backwards(
        self, repo: YamlScratchpadRepository
    ) -> None:
        stored = self._stored_at(repo, "0.1.4")

        after = repo.save(
            _renamed(replace(stored, version="0.1.1"), "Edited by a stale document"),
            group="strategy-and-value", expected_version=stored.version,
        )

        assert after.version == "0.1.5"

    def test_a_document_omitting_the_version_cannot_reset_the_store_to_its_first(
        self, repo: YamlScratchpadRepository
    ) -> None:
        """A client that omits `version` gets the aggregate default, which is not a claim."""
        stored = self._stored_at(repo, "0.1.3")
        omitted = from_document({**to_document(_renamed(stored, "Version omitted")), "version": None})

        after = repo.save(omitted, group="strategy-and-value", expected_version=stored.version)

        assert after.version == "0.1.4"

    def test_a_document_claiming_a_later_version_cannot_advance_the_store_to_it(
        self, repo: YamlScratchpadRepository
    ) -> None:
        stored = repo.save(_pad(), group="strategy-and-value")

        after = repo.save(
            _renamed(replace(stored, version="9.9.9"), "Edited by an inventive client"),
            group="strategy-and-value", expected_version=stored.version,
        )

        assert after.version == "0.1.2"


class TestListingAndPlacement:
    def test_listing_reports_the_group_the_file_sits_in(self, repo: YamlScratchpadRepository) -> None:
        repo.save(_pad(), group="strategy-and-value")

        listed = repo.list_scratchpads()

        assert [(summary.group, summary.note_count) for summary in listed] == [("strategy-and-value", 2)]

    def test_listing_filters_by_group_and_status(self, repo: YamlScratchpadRepository) -> None:
        repo.save(_pad(), group="strategy-and-value")
        repo.save(_pad(artifact_id="SCR@2.b.other", name="Other", status="active"), group="platform-core")

        assert [s.artifact_id for s in repo.list_scratchpads(group="platform-core")] == ["SCR@2.b.other"]
        assert [s.artifact_id for s in repo.list_scratchpads(status="active")] == ["SCR@2.b.other"]

    def test_listing_an_empty_repository_is_empty_rather_than_an_error(
        self, repo: YamlScratchpadRepository
    ) -> None:
        assert repo.list_scratchpads() == []

    def test_re_homing_moves_the_file_rather_than_copying_it(
        self, repo: YamlScratchpadRepository, tmp_path: Path
    ) -> None:
        """Two files answering to one id would each be edited as though they were the scratchpad."""
        first = repo.save(_pad(), group="strategy-and-value")

        repo.save(first, group="platform-core", expected_version=first.version)

        remaining = sorted(p.parent.name for p in (tmp_path / "scratchpads").rglob(f"*{SUFFIX}"))
        assert remaining == ["platform-core"]

    def test_delete_removes_the_file(self, repo: YamlScratchpadRepository, tmp_path: Path) -> None:
        saved = repo.save(_pad(), group="strategy-and-value")

        repo.delete(saved.artifact_id)

        assert list((tmp_path / "scratchpads").rglob(f"*{SUFFIX}")) == []
        with pytest.raises(ScratchpadNotFoundError):
            repo.delete(saved.artifact_id)


class TestGroupsAndAreasSurvive:
    def test_a_group_round_trips_with_its_members(self, repo: YamlScratchpadRepository) -> None:
        saved = repo.save(
            _pad(groups=[Group(id="g1", label="Onboarding cluster", members=("n2", "n1"))]),
            group="strategy-and-value",
        )

        loaded = repo.load(saved.artifact_id)

        assert loaded.groups[0].label == "Onboarding cluster"
        assert sorted(loaded.groups[0].members) == ["n1", "n2"]
