"""Every artifact write is atomic; multi-file writes are additionally all-or-nothing.

The rule, by blast radius:

* one file  → temp + ``os.replace``. A reader never observes a truncated file. Cheap enough
  to pay on every write.
* many files → an M4 manifest. The changes land together or not at all.

The multi-file half is the one that matters and the easy one to lose. A group move that
writes the new file and then fails to unlink the old, or a rename that moves an entity and
then fails to rewrite its referrers, leaves a repository that still parses and whose ids all
still resolve — so nothing downstream reports it. That is precisely how slug drift
accumulated unnoticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp

_WRITERS = (
    Path("src/infrastructure/write/artifact_write/entity.py"),
    Path("src/infrastructure/write/artifact_write/connection.py"),
    Path("src/infrastructure/write/artifact_write/document.py"),
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-DURABLE" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


class TestSingleFileWritesAreAtomic:
    @pytest.mark.parametrize("writer", _WRITERS, ids=lambda p: p.name)
    def test_no_artifact_writer_replaces_a_file_in_place(self, writer: Path) -> None:
        """``write_text`` on a live artifact path is the torn-file case this rule removes."""
        source = writer.read_text(encoding="utf-8")

        offenders = [
            line.strip()
            for line in source.splitlines()
            if re.search(r"\bpath\.write_text\(|_path\.write_text\(", line)
        ]

        assert offenders == [], (
            f"{writer} writes an artifact file in place; route it through write_atomic:\n  "
            + "\n  ".join(offenders)
        )

    def test_an_edit_leaves_no_temp_file_behind(self, repo: Path) -> None:
        created = mcp.artifact_create_entity(
            artifact_type="requirement", name="Atomic Subject", summary="Summary.",
            dry_run=False, repo_root=str(repo),
        )
        mcp.artifact_edit_entity(
            artifact_id=str(created["artifact_id"]), summary="Edited summary.",
            dry_run=False, repo_root=str(repo),
        )

        assert list(repo.rglob("*.tmp-*")) == []


class TestMultiFileWritesLandTogether:
    def test_a_rename_moves_the_entity_and_its_referrer_in_one_commit(self, repo: Path) -> None:
        source = mcp.artifact_create_entity(
            artifact_type="requirement", name="Together Source", summary="S.",
            dry_run=False, repo_root=str(repo),
        )["artifact_id"]
        target = mcp.artifact_create_entity(
            artifact_type="outcome", name="Together Target", summary="S.",
            dry_run=False, repo_root=str(repo),
        )["artifact_id"]
        mcp.artifact_add_connection(
            source_entity=str(source), target_entity=str(target),
            connection_type="archimate-realization", description="Realizes.",
            dry_run=False, repo_root=str(repo),
        )

        renamed = str(mcp.artifact_edit_entity(
            artifact_id=str(target), name="Together Renamed",
            dry_run=False, repo_root=str(repo),
        )["artifact_id"])

        # The entity moved, the old file is gone, and the referrer names the new id — all
        # three are consequences of the same manifest.
        assert list(repo.rglob(f"{target}.md")) == []
        assert list(repo.rglob(f"{renamed}.md"))
        assert renamed in next(repo.rglob(f"{source}.outgoing.md")).read_text(encoding="utf-8")

    def test_no_transaction_residue_remains_after_a_rename(self, repo: Path) -> None:
        created = mcp.artifact_create_entity(
            artifact_type="requirement", name="Residue Subject", summary="S.",
            dry_run=False, repo_root=str(repo),
        )
        mcp.artifact_edit_entity(
            artifact_id=str(created["artifact_id"]), name="Residue Renamed",
            dry_run=False, repo_root=str(repo),
        )

        leftovers = [p for p in repo.rglob("*") if p.is_file() and ".transactions" in p.parts]
        assert leftovers == [], f"transaction residue: {leftovers}"
