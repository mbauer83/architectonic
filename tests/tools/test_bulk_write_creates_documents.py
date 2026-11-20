"""A batch creates a document of a type the repository declares.

A document type is repository configuration: a schema under `.arch-repo/documents/`. A batch writes
into a staging tree that holds only what the batch has written, so configuration it has not written
has to be read through to the live repository — as a named model file is. These drive the real bulk
write and the real scratchpad lift on a repository the test creates, because the property is about
what reaches disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write
from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
    scratchpad_create,
    scratchpad_edit,
    scratchpad_lift,
)

_ADR_SCHEMA = """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "required_sections": ["Context", "Decision"]
}
"""
_ADR_BODY = "## Context\n\nWhy.\n\n## Decision\n\nWhat.\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    schemata = root / ".arch-repo" / "documents"
    schemata.mkdir(parents=True)
    (schemata / "adr.json").write_text(_ADR_SCHEMA, encoding="utf-8")
    return root


def _documents(repo: Path) -> list[Path]:
    return sorted((repo / "docs").rglob("*.md")) if (repo / "docs").exists() else []


def _write(repo: Path, items: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    return artifact_bulk_write(items=items, dry_run=dry_run, repo_root=str(repo), return_mode="full")


class TestABatchCreatingADocument:
    _ITEM: dict[str, Any] = {"op": "create_document", "doc_type": "adr", "title": "Stage lazily", "body": _ADR_BODY}

    def test_a_dry_run_accepts_it_and_writes_nothing(self, repo: Path) -> None:
        answer = _write(repo, [self._ITEM], dry_run=True)

        assert "error" not in answer["items"][0], answer
        assert answer["batch_verification"]["valid"], answer
        assert _documents(repo) == []

    def test_a_real_write_puts_a_verified_document_on_disk(self, repo: Path) -> None:
        answer = _write(repo, [self._ITEM], dry_run=False)

        assert answer["committed"], answer
        assert answer["batch_verification"]["valid"], answer
        (document,) = _documents(repo)
        assert document.name == f"{answer['items'][0]['artifact_id']}.md"
        assert "doc-type: adr" in document.read_text(encoding="utf-8")

    def test_a_type_the_repository_does_not_declare_is_still_refused(self, repo: Path) -> None:
        answer = _write(repo, [{**self._ITEM, "doc_type": "vision"}], dry_run=False)

        assert "Unknown doc-type" in str(answer["items"][0]["error"]), answer
        assert not answer["committed"]
        assert _documents(repo) == []

    def test_it_records_a_reference_to_an_entity_the_repository_holds(self, repo: Path) -> None:
        held = mcp.artifact_create_entity(artifact_type="goal", name="Grow", dry_run=False, repo_root=str(repo))
        assert held["wrote"], held

        answer = _write(repo, [{**self._ITEM, "entity_refs": [held["artifact_id"]]}], dry_run=False)

        assert answer["committed"], answer
        (document,) = _documents(repo)
        text = document.read_text(encoding="utf-8")
        assert "## References" in text
        assert f"{held['artifact_id']}.md)" in text


class TestLiftingANoteIntoADocument:
    def test_the_document_exists_afterwards(self, repo: Path) -> None:
        created = scratchpad_create(name="Q3 thinking", repo_root=str(repo))
        assert created["ok"], created
        pad = created["scratchpad"]
        stored = scratchpad_edit(
            artifact_id=pad["artifact-id"], version=pad["version"],
            upsert={"notes": [{  # type: ignore[arg-type]
                "id": "n1", "title": "Stage lazily", "destination": "document",
                "document-type": "adr", "body": _ADR_BODY,
            }]},
            repo_root=str(repo),
        )
        assert stored["ok"], stored

        scratchpad_lift(
            artifact_id=pad["artifact-id"], selection=["n1"], version=stored["scratchpad"]["version"],
            dry_run=False, repo_root=str(repo),
        )

        (document,) = _documents(repo)
        assert "title: Stage lazily" in document.read_text(encoding="utf-8")
