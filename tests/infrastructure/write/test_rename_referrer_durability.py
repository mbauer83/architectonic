"""A rename and its referrer rewrites are one fact, and drift heals rather than sticking.

The slug tail of an artifact id is a human-readable hint; identity is the
``PREFIX@epoch.random`` stem. That leniency is deliberate — every resolver accepts a stale
slug — but it means a referrer left naming an old slug still resolves, so nothing downstream
complains and the drift accumulates unseen. Two properties keep it from doing so:

* renaming rewrites every referrer in the same transaction as the rename, so the two cannot
  come apart;
* the search keys on the stem, not on the id being renamed *from*, so a referrer holding any
  older slug is found and healed rather than being permanently unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write._entity_rename import plan_referrer_rewrites


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-RENAME" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, conn_type: str = "archimate-realization") -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=conn_type,
        description="Realizes it.", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result


def _rename(repo: Path, artifact_id: str, new_name: str) -> str:
    result = mcp.artifact_edit_entity(
        artifact_id=artifact_id, name=new_name, dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _referrer_text(repo: Path, source_id: str) -> str:
    path = next(repo.rglob(f"{source_id}.outgoing.md"))
    return path.read_text(encoding="utf-8")


class TestRenameRewritesReferrers:
    def test_a_referrer_names_the_new_slug(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Source Requirement")
        target = _entity(repo, "outcome", "Original Target Name")
        _connect(repo, source, target)

        renamed = _rename(repo, target, "Renamed Target")

        text = _referrer_text(repo, source)
        assert renamed in text
        assert target not in text

    def test_the_rewrite_is_committed_with_the_rename(self, repo: Path) -> None:
        """Returned paths are the transaction's, so the referrer is part of the commit."""
        source = _entity(repo, "requirement", "Committed Source")
        target = _entity(repo, "outcome", "Committed Target")
        _connect(repo, source, target)
        referrer = next(repo.rglob(f"{source}.outgoing.md"))

        result = mcp.artifact_edit_entity(
            artifact_id=target, name="Committed Renamed", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"] is True
        assert referrer.exists()
        assert str(result["artifact_id"]) in referrer.read_text(encoding="utf-8")

    def test_several_referrers_are_all_rewritten(self, repo: Path) -> None:
        target = _entity(repo, "outcome", "Shared Target")
        sources = [_entity(repo, "requirement", f"Referrer {n}") for n in range(3)]
        for source in sources:
            _connect(repo, source, target)

        renamed = _rename(repo, target, "Shared Target Renamed")

        for source in sources:
            assert renamed in _referrer_text(repo, source)


class TestDriftHealsRatherThanSticking:
    def test_a_referrer_holding_an_older_slug_is_still_found(self, repo: Path) -> None:
        """Keying the search on the id being renamed *from* would miss this one forever."""
        source = _entity(repo, "requirement", "Healing Source")
        target = _entity(repo, "outcome", "First Name")
        _connect(repo, source, target)

        # Simulate a referrer that a previous rename failed to rewrite: it names the entity
        # by a slug that is neither the current one nor the one the next rename starts from.
        referrer = next(repo.rglob(f"{source}.outgoing.md"))
        stem = target.rsplit(".", 1)[0]
        referrer.write_text(
            referrer.read_text(encoding="utf-8").replace(target, f"{stem}.some-ancient-slug"),
            encoding="utf-8",
        )

        renamed = _rename(repo, target, "Second Name")

        text = referrer.read_text(encoding="utf-8")
        assert renamed in text
        assert "some-ancient-slug" not in text

    def test_the_plan_matches_any_slug_for_the_same_entity(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Plan Source")
        target = _entity(repo, "outcome", "Plan Target")
        _connect(repo, source, target)
        referrer = next(repo.rglob(f"{source}.outgoing.md"))
        stem = target.rsplit(".", 1)[0]
        referrer.write_text(
            referrer.read_text(encoding="utf-8").replace(target, f"{stem}.whatever-it-used-to-be"),
            encoding="utf-8",
        )

        plan = plan_referrer_rewrites(repo_root=repo, new_artifact_id=target)

        assert referrer in plan
        assert target in plan[referrer]
        assert "whatever-it-used-to-be" not in plan[referrer]

    def test_a_repo_already_consistent_plans_no_rewrites(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Consistent Source")
        target = _entity(repo, "outcome", "Consistent Target")
        _connect(repo, source, target)

        assert plan_referrer_rewrites(repo_root=repo, new_artifact_id=target) == {}


class TestTheRewriteKeepsWhatItDoesNotChange:
    """A rewrite of the reference, not of the connection.

    The only alternative available before this cascade existed was remove-and-re-add, which loses
    everything the declaration carried but its endpoints — first of all the description, which is the
    part a human wrote. A substitution of the id in place keeps it, and that is worth holding: a
    "repair" that silently drops authored prose is worse than the drift it repairs.
    """

    def test_a_connection_description_survives_the_rename(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Describing Source")
        target = _entity(repo, "outcome", "Described Target")
        _connect(repo, source, target)

        _rename(repo, target, "Described Target Renamed")

        assert "Realizes it." in _referrer_text(repo, source)

    def test_the_other_connections_in_the_file_are_untouched(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Multi Source")
        renamed_target = _entity(repo, "outcome", "Moving Target")
        stable_target = _entity(repo, "outcome", "Staying Target")
        _connect(repo, source, renamed_target)
        _connect(repo, source, stable_target)

        _rename(repo, renamed_target, "Moved Target")

        assert stable_target in _referrer_text(repo, source)


class TestDiagramSourcesAreReferrersToo:
    """A diagram names entities in `entity-ids-used` and inside composite connection ids.

    Both resolve leniently, so a stale slug there is invisible at read time — and a diagram is the
    surface a reader is most likely to be looking at when the name misleads them.
    """

    def test_a_diagram_naming_the_entity_is_rewritten(self, repo: Path) -> None:
        target = _entity(repo, "outcome", "Diagrammed Target")
        source = _entity(repo, "requirement", "Diagrammed Source")
        _connect(repo, source, target)
        diagram = mcp.artifact_create_diagram(
            name="Rename Coverage View",
            diagram_type="archimate-motivation",
            entity_ids=[source, target],
            dry_run=False,
            repo_root=str(repo),
        )
        assert diagram["wrote"], diagram
        diagram_path = Path(str(diagram["path"]))

        # A name that is not an extension of the old one, so "the old id is gone" is checkable:
        # renaming to "… Renamed" leaves the old id present as a prefix of the new one.
        renamed = _rename(repo, target, "Second Subject")

        text = diagram_path.read_text(encoding="utf-8")
        assert renamed in text
        assert target not in text


class TestNothingLandsHalfway:
    """The rename and its rewrites are one commit, so a refused rename leaves no trace of itself."""

    def test_a_refused_rename_leaves_every_referrer_as_it_was(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Atomic Source")
        target = _entity(repo, "outcome", "Atomic Target")
        _connect(repo, source, target)
        occupant = _entity(repo, "outcome", "Taken Name")
        before = _referrer_text(repo, source)

        with pytest.raises(ValueError, match="already exists|slug"):
            mcp.artifact_edit_entity(
                artifact_id=target, name="Taken Name", dry_run=False, repo_root=str(repo),
            )

        assert _referrer_text(repo, source) == before
        assert target in before and occupant not in before


class TestABatchedRenameCascadesToo:
    """The reported failure: a rename inside `artifact_bulk_write` left every referrer stale.

    A batch writes into a copy-on-write staging tree that holds *only what has been written* — reads
    of a named path fall through to the live repository, but a directory listing had nothing to fall
    through to. So an operation that enumerates instead of naming its paths saw an empty repository:
    "every outgoing file that references this entity" found none, and "every document linking to this
    file" found none. The entity was renamed, the referrers were not, and nothing reported a problem
    because a stale slug still resolves.

    Enumeration now goes through the overlay (`staged_workspace.overlay_paths`), which lists the union
    of staged and live entries, symlinks each listed entry in so it can be read, and honours the
    deletions the transaction has already made.
    """

    def _batch(self, repo: Path, items: list[dict]) -> dict:
        from src.infrastructure.mcp.artifact_mcp.bulk.write import artifact_bulk_write  # noqa: PLC0415

        return artifact_bulk_write(items=items, dry_run=False, repo_root=str(repo))

    def test_a_referrer_is_rewritten_by_a_batched_rename(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Batch Source")
        target = _entity(repo, "outcome", "First Subject")
        _connect(repo, source, target)

        result = self._batch(repo, [{"op": "edit_entity", "artifact_id": target, "name": "Second Subject"}])

        assert result["committed"] is True, result
        text = _referrer_text(repo, source)
        assert "second-subject" in text
        assert target not in text

    def test_the_batched_rename_keeps_the_connection_description(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Batch Describing Source")
        target = _entity(repo, "outcome", "Third Subject")
        _connect(repo, source, target)

        self._batch(repo, [{"op": "edit_entity", "artifact_id": target, "name": "Fourth Subject"}])

        assert "Realizes it." in _referrer_text(repo, source)

    def test_a_document_link_is_rewritten_inside_a_staged_transaction(self, repo: Path) -> None:
        """Documents link by *path*, so a rename moves the file out from under every link to it.

        Driven at the rewrite's own seam under a staged workspace, which is what the overlay changed:
        enumerating documents inside a transaction, and comparing link paths lexically rather than
        through `Path.resolve()` — which followed the staging tree's symlink to the live file and so
        matched nothing.
        """
        from src.infrastructure.write.artifact_write._entity_rename import (  # noqa: PLC0415
            rewrite_document_links_for_moved_artifact,
        )
        from src.infrastructure.write.artifact_write.batch_transaction import (  # noqa: PLC0415
            create_staging_repo,
        )

        doc_dir = repo / "docs" / "adr"
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc = doc_dir / "note.md"
        doc.write_text("See [the outcome](../../model/motivation/outcome/OUT@1.Ab.old-name.md).\n", encoding="utf-8")
        staging, staged_root = create_staging_repo(repo)
        try:
            changed = rewrite_document_links_for_moved_artifact(
                repo_root=staged_root,
                old_path=staged_root / "model" / "motivation" / "outcome" / "OUT@1.Ab.old-name.md",
                new_path=staged_root / "model" / "motivation" / "outcome" / "OUT@1.Ab.new-name.md",
            )
            staged_doc = staged_root / "docs" / "adr" / "note.md"
            assert changed == [staged_doc]
            assert "new-name" in staged_doc.read_text(encoding="utf-8")
            assert "old-name" in doc.read_text(encoding="utf-8"), "the live document must not be touched"
        finally:
            staging.cleanup()

    def test_several_referrers_survive_one_batch(self, repo: Path) -> None:
        target = _entity(repo, "outcome", "Seventh Subject")
        sources = [_entity(repo, "requirement", f"Batch Referrer {n}") for n in range(3)]
        for source in sources:
            _connect(repo, source, target)

        self._batch(repo, [{"op": "edit_entity", "artifact_id": target, "name": "Eighth Subject"}])

        for source in sources:
            assert "eighth-subject" in _referrer_text(repo, source)
