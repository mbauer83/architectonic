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

from src.application.scratchpad.document import to_document
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write
from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
    scratchpad_create,
    scratchpad_edit,
    scratchpad_lift,
)
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository

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


    def test_it_records_a_reference_to_an_entity_the_same_batch_creates(self, repo: Path) -> None:
        answer = _write(
            repo,
            [
                {"op": "create_entity", "_ref": "goal", "artifact_type": "goal", "name": "Grow"},
                {**self._ITEM, "entity_refs": ["$ref:goal"]},
            ],
            dry_run=False,
        )

        assert answer["committed"], answer
        (document,) = _documents(repo)
        text = document.read_text(encoding="utf-8")
        assert "## References" in text
        assert f"{answer['refs']['goal']}.md)" in text


_DOCUMENT_NOTE: dict[str, Any] = {
    "id": "d1", "title": "Stage lazily", "destination": "document", "document-type": "adr", "body": _ADR_BODY,
}
_ELEMENT_NOTE: dict[str, Any] = {"id": "n1", "title": "Grow", "destination": "element", "element-type": "goal"}


def _pad(repo: Path, **upsert: list[dict[str, Any]]) -> dict[str, Any]:
    created = scratchpad_create(name="Q3 thinking", repo_root=str(repo))
    assert created["ok"], created
    pad = created["scratchpad"]
    stored = scratchpad_edit(
        artifact_id=pad["artifact-id"], version=pad["version"],
        upsert=upsert,  # type: ignore[arg-type]
        repo_root=str(repo),
    )
    assert stored["ok"], stored
    return stored["scratchpad"]


def _lift(repo: Path, pad: dict[str, Any], selection: list[str]) -> dict[str, Any]:
    return scratchpad_lift(
        artifact_id=pad["artifact-id"], selection=selection, version=pad["version"],
        dry_run=False, repo_root=str(repo),
    )


def _reread(repo: Path, pad: dict[str, Any]) -> dict[str, Any]:
    """The scratchpad as its file now holds it, so what is asserted has been through the round trip."""
    return to_document(YamlScratchpadRepository(repo).load(pad["artifact-id"]))


def _entities(repo: Path) -> list[Path]:
    return sorted(path for path in (repo / "model").rglob("*.md") if not path.name.endswith(".outgoing.md"))


class TestLiftingANoteIntoADocument:
    def test_it_commits_and_the_note_says_which_document_it_became(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_DOCUMENT_NOTE])

        answer = _lift(repo, pad, ["d1"])

        assert answer["ok"] and answer["lift"]["committed"], answer
        assert not answer["lift"]["errors"], answer
        (document,) = _documents(repo)
        assert "title: Stage lazily" in document.read_text(encoding="utf-8")
        (note,) = _reread(repo, pad)["notes"]
        assert note["model-ref"] == {"artifact-id": document.stem, "kind": "realized"}
        assert note["destination"] == "document" and note["document-type"] == "adr"

    def test_a_second_lift_skips_it_and_writes_nothing(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_DOCUMENT_NOTE])
        _lift(repo, pad, ["d1"])
        (document,) = _documents(repo)

        second = _lift(repo, _reread(repo, pad), ["d1"])

        assert second["ok"], second
        (item,) = second["lift"]["items"]
        assert (item["kind"], item["outcome"], item["artifact-id"]) == ("document", "skip", document.stem)
        assert _documents(repo) == [document]


class TestLiftingADocumentTheElementItRefersToAndTheLinkBetweenThem:
    _LINK: dict[str, Any] = {"id": "l1", "source": "d1", "target": "n1"}

    def test_the_document_records_a_reference_to_the_entity_created_beside_it(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_ELEMENT_NOTE, _DOCUMENT_NOTE], links=[self._LINK])

        answer = _lift(repo, pad, ["n1", "d1"])

        assert answer["ok"] and answer["lift"]["committed"], answer
        assert not answer["lift"]["errors"], answer
        (entity,) = _entities(repo)
        (document,) = _documents(repo)
        text = document.read_text(encoding="utf-8")
        assert "## References" in text
        assert f"{entity.stem}.md)" in text

    def test_each_note_and_the_link_say_what_they_became(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_ELEMENT_NOTE, _DOCUMENT_NOTE], links=[self._LINK])

        _lift(repo, pad, ["n1", "d1"])

        (entity,) = _entities(repo)
        (document,) = _documents(repo)
        after = _reread(repo, pad)
        became = {note["id"]: note["model-ref"]["artifact-id"] for note in after["notes"]}
        assert became == {"n1": entity.stem, "d1": document.stem}
        # A reference is recorded on its document, so that is what the link became part of.
        (link,) = after["links"]
        assert link["model-ref"] == {"artifact-id": document.stem, "kind": "realized"}

    def test_a_second_lift_creates_nothing(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_ELEMENT_NOTE, _DOCUMENT_NOTE], links=[self._LINK])
        _lift(repo, pad, ["n1", "d1"])
        written = (_entities(repo), _documents(repo))

        second = _lift(repo, _reread(repo, pad), ["n1", "d1"])

        assert second["ok"], second
        assert {item["outcome"] for item in second["lift"]["items"]} == {"skip"}
        assert (_entities(repo), _documents(repo)) == written

    def test_a_link_drawn_to_a_document_that_already_exists_is_reported_and_not_planned(self, repo: Path) -> None:
        pad = _pad(repo, notes=[_ELEMENT_NOTE, _DOCUMENT_NOTE])
        _lift(repo, pad, ["n1", "d1"])
        current = _reread(repo, pad)
        drawn = scratchpad_edit(
            artifact_id=pad["artifact-id"], version=current["version"],
            upsert={"links": [self._LINK]},  # type: ignore[arg-type]
            repo_root=str(repo),
        )
        assert drawn["ok"], drawn
        (document,) = _documents(repo)
        before = document.read_text(encoding="utf-8")

        again = _lift(repo, drawn["scratchpad"], ["n1", "d1"])

        assert again["ok"], again
        reference = next(item for item in again["lift"]["items"] if item["kind"] == "reference")
        assert reference["outcome"] == "skip" and "already exists" in reference["reason"]
        assert document.read_text(encoding="utf-8") == before
