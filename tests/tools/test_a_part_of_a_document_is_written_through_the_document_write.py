"""A section, a text or rows of a typed table are written through the one document write.

`edit_document` takes a part edit beside the fields it always took. What that buys is asserted here
against a stored file: the bytes the edit did not address are the bytes that were there, the write
is judged by the same verification and the same gate as any other document write, a row another
writer changed first is refused and a row nobody else touched is not, and a link written with an
artifact id is stored as the path every reader resolves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.document_part_edits import (
    DocumentEditRefused,
    PartEdit,
    RowAddition,
    RowChange,
    RowChangedSinceRead,
    RowRemoval,
    SectionReplacement,
    TableRowEdits,
    TextReplacement,
)
from src.application.artifacts.document_schema import DocumentSchema
from src.application.artifacts.document_table_edits import row_values
from src.application.artifacts.document_table_rows import read_document_tables
from src.application.document_links import UnresolvedArtifactLink
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write import document as document_write
from src.infrastructure.write.artifact_write.document import create_document, edit_document
from src.infrastructure.write.artifact_write.types import WriteResult
from tests.support.typed_table_documents import (
    STRESS_ANALYSIS,
    document_path,
    document_text,
    document_type,
    entity_in,
    link_to,
    repository_in,
    runtime_catalogs,
    table_of,
    table_text,
)

_STAMP = "2026-11-20T10:00:00Z"
_FRONTMATTER_AS_AN_AUTHOR_LEFT_IT = (
    "---\n# kept as written\ndoc-type:   stress-analysis\nartifact-type: document\n"
    'title: "Checkout under stress"\nartifact-id: DOC@1000000003.Doc.doc\nstatus: draft\n'
    "last-updated: '2026-01-01T00:00:00Z'  # stamped by the write\n---\n"
)


class _Repository:
    """An engagement repository holding one stress analysis and the artifacts it may link."""

    def __init__(self, tmp_path: Path, *, line_ending: str = "\n") -> None:
        self.root = repository_in(tmp_path, STRESS_ANALYSIS)
        self.schema: DocumentSchema = document_type(STRESS_ANALYSIS)
        self.doc = document_path(self.root, self.schema)
        self.requirement = entity_in(self.root, "requirement", "survive-a-provider-outage")
        self.goal = entity_in(self.root, "goal", "keep-selling")
        rows = {
            "stressors": [
                {"stressor": "The provider is down", "set": "design"},
                {"stressor": "The provider doubles its fees", "set": "test"},
            ],
            "end-states": [{"end_state": "Orders cannot be paid"}],
        }
        tables = {name: table_text(table_of(self.schema, name), held) for name, held in rows.items()}
        body = document_text(self.schema, tables).split("\n---\n", 1)[1]
        body = body.replace("## Naive Architecture\n", "## Naive Architecture\n\nThe shop calls the provider inline.\n")
        self.doc.parent.mkdir(parents=True, exist_ok=True)
        self.doc.write_bytes((_FRONTMATTER_AS_AN_AUTHOR_LEFT_IT + body).replace("\n", line_ending).encode("utf-8"))
        self.registry = ArtifactRegistry(shared_artifact_index(self.root))

    def stored(self) -> str:
        return self.doc.read_bytes().decode("utf-8")

    def edit(self, part: PartEdit | None, *, dry_run: bool = False, **fields: str | None) -> WriteResult:
        given: dict[str, str | None] = {"title": None, "body": None, "status": None, "version": None} | fields
        return edit_document(
            assert_write_root=lambda _: None,
            repo_root=self.root,
            verifier=ArtifactVerifier(self.registry, catalogs=runtime_catalogs()),
            clear_repo_caches=lambda _: None,
            artifact_id=self.doc.stem,
            keywords=None,
            extra_frontmatter=None,
            last_updated=_STAMP,
            registry=self.registry,
            part=part,
            dry_run=dry_run,
            **given,
        )

    def row(self, table: str, row_id: str) -> dict[str, object]:
        row = read_document_tables(self.doc, self.stored(), self.schema).row(table, row_id)
        assert row is not None
        return dict(row_values(row))

    def rows(self, table: str, *edits: RowAddition | RowChange | RowRemoval) -> TableRowEdits:
        return TableRowEdits(table, edits)


@pytest.fixture
def repo(tmp_path: Path) -> _Repository:
    return _Repository(tmp_path)


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    was, now = before.split("\n"), after.split("\n")
    assert len(was) == len(now)
    return [(old, new) for old, new in zip(was, now, strict=True) if old != new]


_STAMPED = (
    "last-updated: '2026-01-01T00:00:00Z'  # stamped by the write",
    f"last-updated: '{_STAMP}'  # stamped by the write",
)


class TestEveryOtherByteIsTheByteThatWasThere:
    def test_a_row_edit_changes_the_rows_line_and_the_stamp(self, repo: _Repository) -> None:
        before = repo.stored()

        written = repo.edit(repo.rows("stressors", RowChange("S2", repo.row("stressors", "S2"), {"set": "design"})))

        assert written.wrote
        assert _changed_lines(before, repo.stored()) == [
            _STAMPED,
            (
                "| S2 | The provider doubles its fees | | | | test | |",
                "| S2 | The provider doubles its fees | | | | design | |",
            ),
        ]

    def test_a_section_edit_changes_the_section_and_the_stamp(self, repo: _Repository) -> None:
        before = repo.stored()

        assert repo.edit(SectionReplacement(("Naive Architecture",), "The shop queues the payment.")).wrote

        assert _changed_lines(before, repo.stored()) == [
            _STAMPED,
            ("The shop calls the provider inline.", "The shop queues the payment."),
        ]

    def test_a_text_edit_changes_the_text_and_the_stamp(self, repo: _Repository) -> None:
        before = repo.stored()

        assert repo.edit(TextReplacement("doubles its fees", "triples its fees")).wrote

        assert repo.stored() == before.replace("doubles its fees", "triples its fees").replace(*_STAMPED)

    def test_a_document_of_carriage_returns_keeps_every_one(self, tmp_path: Path) -> None:
        repo = _Repository(tmp_path, line_ending="\r\n")
        before = repo.stored()

        assert repo.edit(repo.rows("stressors", RowAddition({"stressor": "A third", "set": "test"}))).wrote

        after = repo.stored()
        assert "\n" not in after.replace("\r\n", "")
        assert after.replace("| S3 | A third | | | | test | |\r\n", "") == before.replace(*_STAMPED)

    def test_a_field_stated_beside_a_part_rewrites_the_frontmatter_and_leaves_the_body(self, repo: _Repository) -> None:
        body_before = repo.stored().split("\n---\n", 1)[1]

        assert repo.edit(TextReplacement("doubles its fees", "triples its fees"), status="accepted").wrote

        head, body = repo.stored().split("\n---\n", 1)
        assert "status: accepted" in head and "# kept as written" not in head
        assert body == body_before.replace("doubles its fees", "triples its fees")

    def test_a_dry_run_writes_nothing_and_answers_the_content_it_would(self, repo: _Repository) -> None:
        before = repo.stored()

        planned = repo.edit(repo.rows("stressors", RowAddition({"stressor": "A third", "set": "test"})), dry_run=True)

        assert not planned.wrote and repo.stored() == before
        assert planned.content is not None and "| S3 | A third | | | | test | |" in planned.content
        assert getattr(planned, "added_row_ids", None) == ["S3"]


class TestAPartEditIsJudgedAsEveryDocumentWriteIs:
    def test_a_row_still_being_filled_in_is_written_and_warned_about(self, repo: _Repository) -> None:
        written = repo.edit(repo.rows("stressors", RowAddition({"kind": "market"})))

        assert written.wrote and written.verification is not None
        assert sorted(issue["code"] for issue in written.verification["issues"]) == ["W165", "W165"]

    def test_a_cell_that_cannot_be_read_is_refused_with_the_cell_named(self, repo: _Repository) -> None:
        before = repo.stored()

        unreadable = RowAddition({"stressor": "x", "set": "test", "plausible": "likely"})
        refused = repo.edit(repo.rows("stressors", unreadable))

        assert not refused.wrote and repo.stored() == before
        assert refused.error_messages == [
            "Table 'stressors' row S3 column 'Plausible': Cannot decode 'likely' as boolean; "
            "expected literal 'true' or 'false'"
        ]

    def test_a_link_to_nothing_is_refused_in_a_section_as_it_is_in_a_body(self, repo: _Repository) -> None:
        before = repo.stored()
        dangling = "See [the model](../../model/goal/ENT@1.gone.gone.md)."

        in_a_section = repo.edit(SectionReplacement(("Naive Architecture",), dangling))
        body = before.split("\n---\n", 1)[1].replace("The shop calls", dangling + " The shop calls")
        in_a_body = repo.edit(None, body=body)

        assert (in_a_section.wrote, in_a_body.wrote) == (False, False) and repo.stored() == before
        assert in_a_section.verification is not None and in_a_body.verification is not None
        assert [issue["code"] for issue in in_a_section.verification["issues"]] == ["W155"]
        assert [issue["code"] for issue in in_a_body.verification["issues"]] == ["W155"]

    def test_which_findings_refuse_is_decided_in_one_place(
        self, repo: _Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every document write asks `document_write_allowed`; a part edit is not a second gate."""
        monkeypatch.setattr(document_write, "document_write_allowed", lambda _result: True)

        dangling = "See [it](../../model/goal/ENT@1.gone.gone.md)."
        written = repo.edit(SectionReplacement(("Naive Architecture",), dangling))

        assert written.wrote

    def test_a_part_and_a_whole_body_in_one_edit_is_refused(self, repo: _Repository) -> None:
        with pytest.raises(DocumentEditRefused, match="states a whole body and a part of it"):
            repo.edit(TextReplacement("a", "b"), body="## Naive Architecture\n")


class TestTwoWritersOfOneDocument:
    def test_changes_to_different_rows_both_land(self, repo: _Repository) -> None:
        read_by_one, read_by_the_other = repo.row("stressors", "S1"), repo.row("stressors", "S2")

        first = repo.edit(repo.rows("stressors", RowChange("S1", read_by_one, {"kind": "outage"})))
        second = repo.edit(repo.rows("stressors", RowChange("S2", read_by_the_other, {"kind": "market"})))

        assert (first.wrote, second.wrote) == (True, True)
        assert (repo.row("stressors", "S1")["kind"], repo.row("stressors", "S2")["kind"]) == ("outage", "market")

    def test_the_second_change_to_one_row_is_refused_and_writes_nothing(self, repo: _Repository) -> None:
        read_by_both = repo.row("stressors", "S1")
        assert repo.edit(repo.rows("stressors", RowChange("S1", read_by_both, {"set": "test"}))).wrote
        after_the_first = repo.stored()

        with pytest.raises(RowChangedSinceRead) as refused:
            repo.edit(repo.rows("stressors", RowChange("S1", read_by_both, {"kind": "outage"})))

        assert str(refused.value) == (
            "Table 'stressors' row S1 has changed since it was read: 'set' was \"design\" and is now \"test\". "
            "Read the row again and make the edit on what it holds now."
        )
        assert repo.stored() == after_the_first

    def test_a_row_added_while_another_changes_takes_the_next_id(self, repo: _Repository) -> None:
        read = repo.row("stressors", "S1")
        added = repo.edit(repo.rows("stressors", RowAddition({"stressor": "A third", "set": "test"})))

        changed = repo.edit(repo.rows("stressors", RowChange("S1", read, {"kind": "outage"})))

        assert getattr(added, "added_row_ids", None) == ["S3"] and changed.wrote
        assert repo.row("stressors", "S3")["stressor"] == "A third"


class TestALinkWrittenWithAnIdIsStoredAsAPath:
    def test_in_a_sections_text(self, repo: _Repository) -> None:
        text = f"It must [survive]({repo.requirement.stem}#properties) and [](ENT@1000000001.keep-s)."

        assert repo.edit(SectionReplacement(("Naive Architecture",), text)).wrote

        assert (
            f"It must [survive]({link_to(repo.requirement, written_in=repo.doc)[5:-1]}#properties) "
            f"and [keep-selling]({link_to(repo.goal, written_in=repo.doc)[5:-1]}).\n"
        ) in repo.stored()

    def test_in_a_reference_cell_stated_as_the_id_alone(self, repo: _Repository) -> None:
        based_on = repo.row("end-states", "E1")

        written = repo.edit(
            repo.rows("end-states", RowChange("E1", based_on, {"required_behaviour": repo.requirement.stem,
                                                                 "affects": [repo.goal.stem]}))
        )

        assert written.wrote and written.verification is not None and written.verification["issues"] == []
        assert repo.row("end-states", "E1") == based_on | {
            "required_behaviour": repo.requirement.stem, "affects": [repo.goal.stem]
        }
        assert f"[survive-a-provider-outage]({link_to(repo.requirement, written_in=repo.doc)[5:-1]})" in repo.stored()

    def test_in_a_replacement_text_and_in_a_whole_body(self, repo: _Repository) -> None:
        assert repo.edit(TextReplacement("inline", f"[inline]({repo.goal.stem})")).wrote
        body = repo.stored().split("\n---\n", 1)[1].replace("The shop", f"[The shop]({repo.requirement.stem})")
        assert repo.edit(None, body=body).wrote

        stored = repo.stored()
        assert f"[inline]({link_to(repo.goal, written_in=repo.doc)[5:-1]})" in stored
        assert f"[The shop]({link_to(repo.requirement, written_in=repo.doc)[5:-1]})" in stored

    def test_in_a_created_documents_body(self, repo: _Repository) -> None:
        body = repo.stored().split("\n---\n", 1)[1].replace("The shop", f"[The shop]({repo.goal.stem})")

        created = create_document(
            repo_root=repo.root, verifier=ArtifactVerifier(repo.registry, catalogs=runtime_catalogs()),
            clear_repo_caches=lambda _: None, doc_type=STRESS_ANALYSIS, title="Another", body=body, keywords=None,
            extra_frontmatter=None, artifact_id=None, version="0.1.0", status="draft", last_updated=_STAMP,
            dry_run=True,
        )

        assert created.content is not None
        assert f"[The shop]({link_to(repo.goal, written_in=repo.doc)[5:-1]})" in created.content

    def test_an_id_that_names_nothing_is_refused_and_nothing_is_written(self, repo: _Repository) -> None:
        before = repo.stored()

        with pytest.raises(UnresolvedArtifactLink, match=r"REQ@1\.gone: no artifact of this repository has that id"):
            repo.edit(SectionReplacement(("Naive Architecture",), "See [it](REQ@1.gone)."))

        assert repo.stored() == before

    def test_a_link_in_a_part_the_edit_does_not_address_keeps_its_spelling(self, repo: _Repository) -> None:
        by_hand = repo.stored().replace("The shop calls", f"[The shop]({repo.goal.stem}) calls")
        repo.doc.write_bytes(by_hand.encode("utf-8"))

        assert repo.edit(repo.rows("stressors", RowRemoval("S2", repo.row("stressors", "S2")))).wrote

        assert f"[The shop]({repo.goal.stem}) calls" in repo.stored()
