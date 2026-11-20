"""Inside a batch, an artifact the batch wrote is read as the batch wrote it.

The candidate store overlays what a batch has staged on the live index. For every file the batch
touched it sets the live record aside — the staged file is now the truth — and that set is also how
a deletion is known. A getter that consulted it before the staged records therefore answered "absent"
for exactly the artifacts the batch had just written: an entity it created, a document it edited.

Each kind is asked the same three questions: written and present, deleted and absent, untouched and
unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk.candidate_state import CandidateStore, candidate_store
from src.infrastructure.write.artifact_write.batch_transaction import create_staging_repo
from src.infrastructure.write.artifact_write.staged_workspace import stage_live_path

_DIAGRAM = """\
---
artifact-id: hand-written
artifact-type: diagram
diagram-type: archimate-application
name: "Hand written"
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
@enduml
"""


class _Batch:
    """A staging tree over a live repository, and the paths a batch has touched in it."""

    def __init__(self, live: Path, staged: Path) -> None:
        self.live, self.staged = live, staged
        self.touched: set[Path] = set()

    def staged_path(self, live_path: Path) -> Path:
        return self.staged / live_path.resolve().relative_to(self.live.resolve())

    def rewrite(self, live_path: Path, old: str, new: str) -> None:
        path = stage_live_path(self.staged_path(live_path), live_path)
        text = path.read_text(encoding="utf-8")
        assert old in text, text
        path.write_text(text.replace(old, new), encoding="utf-8")
        self.touched.add(path)

    def delete(self, live_path: Path) -> None:
        path = stage_live_path(self.staged_path(live_path), live_path)
        path.unlink()
        self.touched.add(path)

    def store(self) -> CandidateStore:
        return candidate_store(live_root=self.live, staged_root=self.staged, touched_paths=self.touched)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams" / "hand-written.puml").write_text(_DIAGRAM, encoding="utf-8")
    schemata = root / ".arch-repo" / "documents"
    schemata.mkdir(parents=True)
    (schemata / "adr.json").write_text('{"abbreviation": "ADR", "required_sections": ["Context"]}', encoding="utf-8")
    return root


@pytest.fixture()
def batch(repo: Path) -> Iterator[_Batch]:
    staging, staged_root = create_staging_repo(repo)
    try:
        yield _Batch(repo, staged_root)
    finally:
        staging.cleanup()


def _entity(repo: Path, name: str) -> dict[str, object]:
    created = mcp.artifact_create_entity(artifact_type="requirement", name=name, dry_run=False, repo_root=str(repo))
    assert created["wrote"], created
    return created


def _connection(repo: Path) -> tuple[str, Path]:
    source, target = _entity(repo, "Source"), _entity(repo, "Target")
    added = mcp.artifact_add_connection(
        source_entity=str(source["artifact_id"]), connection_type="archimate-association",
        target_entity=str(target["artifact_id"]), dry_run=False, repo_root=str(repo),
    )
    assert added["wrote"], added
    return str(added["artifact_id"]), Path(str(added["path"]))


def _document(repo: Path) -> dict[str, object]:
    created = mcp.artifact_create_document(
        doc_type="adr", title="Decided", body="## Context\n\nWhy.\n", dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    return created


class TestAnEntity:
    def test_rewritten_in_the_batch_is_read_as_rewritten(self, repo: Path, batch: _Batch) -> None:
        held = _entity(repo, "Before")
        batch.rewrite(Path(str(held["path"])), "Before", "After")

        record = batch.store().get_entity(str(held["artifact_id"]))

        assert record is not None and record.name == "After"

    def test_deleted_in_the_batch_is_absent(self, repo: Path, batch: _Batch) -> None:
        held = _entity(repo, "Before")
        batch.delete(Path(str(held["path"])))

        assert batch.store().get_entity(str(held["artifact_id"])) is None

    def test_untouched_is_read_from_the_live_repository(self, repo: Path, batch: _Batch) -> None:
        held = _entity(repo, "Before")

        record = batch.store().get_entity(str(held["artifact_id"]))

        assert record is not None and record.name == "Before"


class TestAConnection:
    def test_rewritten_in_the_batch_is_read_as_rewritten(self, repo: Path, batch: _Batch) -> None:
        connection_id, outgoing = _connection(repo)
        batch.rewrite(outgoing, "status: draft", "status: active")

        record = batch.store().get_connection(connection_id)

        assert record is not None and record.status == "active"

    def test_deleted_in_the_batch_is_absent(self, repo: Path, batch: _Batch) -> None:
        connection_id, outgoing = _connection(repo)
        batch.delete(outgoing)

        assert batch.store().get_connection(connection_id) is None


class TestADiagram:
    def test_rewritten_in_the_batch_is_read_as_rewritten(self, repo: Path, batch: _Batch) -> None:
        _entity(repo, "Anything")  # the index is built over a repository that holds the diagram
        batch.rewrite(repo / "diagram-catalog" / "diagrams" / "hand-written.puml", "Hand written", "Redrawn")

        record = batch.store().get_diagram("hand-written")

        assert record is not None and record.name == "Redrawn"

    def test_deleted_in_the_batch_is_absent(self, repo: Path, batch: _Batch) -> None:
        _entity(repo, "Anything")
        batch.delete(repo / "diagram-catalog" / "diagrams" / "hand-written.puml")

        assert batch.store().get_diagram("hand-written") is None


class TestADocument:
    def test_rewritten_in_the_batch_is_read_as_rewritten(self, repo: Path, batch: _Batch) -> None:
        held = _document(repo)
        batch.rewrite(Path(str(held["path"])), "title: Decided", "title: Reconsidered")

        record = batch.store().get_document(str(held["artifact_id"]))

        assert record is not None and record.title == "Reconsidered"

    def test_deleted_in_the_batch_is_absent(self, repo: Path, batch: _Batch) -> None:
        held = _document(repo)
        batch.delete(Path(str(held["path"])))

        assert batch.store().get_document(str(held["artifact_id"])) is None


class TestAPathTheOverlayKeepsNoRecordsOf:
    """What a batch touched and the overlay does not stage is passed over only where the kind table
    says a bulk write does not verify it. The `match` this replaced had no arm for an icon and fell
    through it in silence, which no one had decided."""

    def _touch(self, batch: _Batch, relative: str) -> None:
        path = batch.staged / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        batch.touched.add(path)

    @pytest.mark.parametrize(
        "relative", ["scratchpads/core/SCR@1.a.x.scratchpad.yaml", "README.md", ".arch-repo/config.yaml"]
    )
    def test_an_unverified_kind_or_no_kind_at_all_is_passed_over(
        self, repo: Path, batch: _Batch, relative: str
    ) -> None:
        held = _entity(repo, "Before")
        self._touch(batch, relative)

        record = batch.store().get_entity(str(held["artifact_id"]))

        assert record is not None and record.name == "Before"

    def test_a_verified_kind_it_cannot_stage_is_refused_by_name(self, batch: _Batch) -> None:
        self._touch(batch, "diagram-catalog/icons/ICO@1.a.x.md")

        with pytest.raises(ValueError, match="a file of the icon kind. The staging overlay keeps no icon records"):
            batch.store()
