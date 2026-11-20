"""Re-homing one artifact keeps every link true: the ones it makes and the ones made to it.

A link in prose is a relative path, so it is a statement about two locations — where it is written
and what it addresses. A move changes one of them, and both directions have to follow:

* the moved artifact's **own** links, when its new directory sits at a different depth — a document
  taken from `docs/adr/` into `docs/adr/<collection>/` read every `../../projects/…` link one level
  short, and the dry run said so with W155 while the write went ahead;
* links **to** it, from every source that links by path — documents and matrix diagrams — and to
  every file that moves with it, which for a diagram includes its rendered image.

All content here is the test's own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.document_links import references_from, relocated_links
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write._entity_rename import rewrite_document_links_for_moved_artifact

_ADR_BODY = "## Context\n\n{context}\n\n## Decision\n\nY\n\n## Consequences\n\nZ\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    _write(
        root / ".arch-repo" / "documents" / "adr.json",
        '{\n  "abbreviation": "ADR",\n  "required_sections": ["Context", "Decision", "Consequences"]\n}\n',
    )
    return root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(repo: Path, artifact_id: str) -> Path:
    path = repo / "projects" / "core" / "model" / "motivation" / "requirement" / f"{artifact_id}.md"
    _write(
        path,
        f"---\nartifact-id: {artifact_id}\nartifact-type: requirement\nname: Scenery\nversion: 0.1.0\n"
        "status: active\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n## Scenery\n\nScenery.\n",
    )
    return path


def _adr(repo: Path, artifact_id: str, context: str, group: str | None = None) -> Path:
    result = mcp.artifact_create_document(
        doc_type="adr", title="A Decision", body=_ADR_BODY.format(context=context),
        artifact_id=artifact_id, group=group, dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return Path(result["path"])


def _codes(verification: dict[str, object]) -> list[str]:
    issues = verification["issues"]
    assert isinstance(issues, list)
    return [str(issue["code"]) for issue in issues]


def _unresolved(path: Path) -> list[str]:
    """The links *path* makes that address nothing — what W155 reports, asked of the file directly."""
    return [
        reference.href
        for reference in references_from(path.read_text(encoding="utf-8"), directory=path.parent)
        if not reference.target.exists()
    ]


# ---------------------------------------------------------------------------
# The one reading of "this text is now read from somewhere else"
# ---------------------------------------------------------------------------


class TestRelocatedLinks:
    def test_a_link_is_re_expressed_from_the_new_directory(self, tmp_path: Path) -> None:
        text = "See [req](../../projects/core/REQ@1.a.x.md) and [peer](ADR@2.b.y.md).\n"

        moved = relocated_links(
            text, read_from=tmp_path / "docs" / "adr", written_to=tmp_path / "docs" / "adr" / "core", moves={},
        )

        assert moved == "See [req](../../../projects/core/REQ@1.a.x.md) and [peer](../ADR@2.b.y.md).\n"

    def test_a_section_anchor_survives_and_does_not_hide_the_link(self, tmp_path: Path) -> None:
        old, new = tmp_path / "model" / "REQ@1.a.x.md", tmp_path / "projects" / "g" / "REQ@1.a.x.md"

        moved = relocated_links(
            "[props](../model/REQ@1.a.x.md#properties)\n",
            read_from=tmp_path / "docs", written_to=tmp_path / "docs", moves={old: new},
        )

        assert moved == "[props](../projects/g/REQ@1.a.x.md#properties)\n"

    def test_what_addresses_no_relative_file_is_left_as_written(self, tmp_path: Path) -> None:
        text = "[web](https://example.com/a.md) [here](#decision) [abs](/etc/a.md) [mail](mailto:a@b.c)\n"

        assert relocated_links(text, read_from=tmp_path / "a", written_to=tmp_path / "a" / "b", moves={}) == text

    def test_nothing_is_respelled_when_nothing_moved(self, tmp_path: Path) -> None:
        """A link that still addresses the same file from the same place keeps its author's spelling."""
        text = "[odd](./sub/../REQ@1.a.x.md)\n"
        elsewhere = {tmp_path / "other.md": tmp_path / "moved.md"}

        assert relocated_links(text, read_from=tmp_path, written_to=tmp_path, moves=elsewhere) == text


# ---------------------------------------------------------------------------
# A document re-homed to a collection at a different depth
# ---------------------------------------------------------------------------


class TestADocumentMovedToAnotherCollection:
    def test_its_own_links_still_resolve(self, repo: Path) -> None:
        entity = _entity(repo, "REQ@1779100001.aaaa.scenery")
        peer = _adr(repo, "ADR@1779100002.aaaa.peer", "Nothing.")
        link = f"../../{entity.relative_to(repo).as_posix()}"
        old_path = _adr(
            repo, "ADR@1779100003.aaaa.moving",
            f"See [req]({link}), [its properties]({link}#properties) and [peer]({peer.name}).",
        )
        assert _unresolved(old_path) == []

        result = mcp.artifact_edit_document(
            artifact_id="ADR@1779100003.aaaa.moving", group="decisions", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        new_path = Path(result["path"])
        assert new_path.parent == old_path.parent / "decisions"
        assert _unresolved(new_path) == []
        assert "W155" not in _codes(result["verification"])
        assert f"(../{link}#properties)" in new_path.read_text(encoding="utf-8")

    def test_the_dry_run_reports_what_the_write_would_do(self, repo: Path) -> None:
        entity = _entity(repo, "REQ@1779100011.bbbb.scenery")
        link = f"../../{entity.relative_to(repo).as_posix()}"
        _adr(repo, "ADR@1779100012.bbbb.moving", f"See [req]({link}).")

        result = mcp.artifact_edit_document(
            artifact_id="ADR@1779100012.bbbb.moving", group="decisions", dry_run=True, repo_root=str(repo),
        )

        assert not result["wrote"]
        assert "W155" not in _codes(result["verification"])
        assert f"(../{link})" in result["content"]

    def test_a_body_sent_with_the_move_is_read_from_where_the_document_was(self, repo: Path) -> None:
        """The GUI saves body and home together, and the body it sends was read at the old home."""
        entity = _entity(repo, "REQ@1779100021.cccc.scenery")
        link = f"../../{entity.relative_to(repo).as_posix()}"
        _adr(repo, "ADR@1779100022.cccc.moving", "Nothing yet.")

        result = mcp.artifact_edit_document(
            artifact_id="ADR@1779100022.cccc.moving", group="decisions",
            body=_ADR_BODY.format(context=f"Now see [req]({link})."), dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _unresolved(Path(result["path"])) == []

    def test_moving_back_out_of_a_collection_shortens_them_again(self, repo: Path) -> None:
        entity = _entity(repo, "REQ@1779100031.dddd.scenery")
        link = f"../../../{entity.relative_to(repo).as_posix()}"
        _adr(repo, "ADR@1779100032.dddd.moving", f"See [req]({link}).", group="decisions")

        result = mcp.artifact_edit_document(
            artifact_id="ADR@1779100032.dddd.moving", group="uncategorized", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _unresolved(Path(result["path"])) == []

    def test_a_document_citing_it_still_resolves(self, repo: Path) -> None:
        moving = _adr(repo, "ADR@1779100041.eeee.moving", "Nothing.")
        citing = _adr(
            repo, "ADR@1779100042.eeee.citing",
            f"See [the decision]({moving.name}) and [what it decides]({moving.name}#decision).",
        )

        result = mcp.artifact_edit_document(
            artifact_id="ADR@1779100041.eeee.moving", group="decisions", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _unresolved(citing) == []
        assert f"(decisions/{moving.name}#decision)" in citing.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Every source that links by path follows a move — a matrix as much as a document
# ---------------------------------------------------------------------------


class TestAMatrixLinksByPathToo:
    def test_a_matrix_citing_a_moved_artifact_is_rewritten(self, repo: Path) -> None:
        old_path = repo / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
        new_path = repo / "projects" / "g" / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
        matrix = repo / "diagram-catalog" / "diagrams" / "MAT@1.a.m.md"
        _write(matrix, "| [X](../../model/motivation/requirement/REQ@1.a.x.md) | 1 |\n")

        changed = rewrite_document_links_for_moved_artifact(repo_root=repo, old_path=old_path, new_path=new_path)

        assert changed == [matrix]
        assert "(../../projects/g/model/motivation/requirement/REQ@1.a.x.md)" in matrix.read_text(encoding="utf-8")

    def test_rendered_output_is_not_a_source(self, repo: Path) -> None:
        old_path, new_path = repo / "model" / "REQ@1.a.x.md", repo / "projects" / "g" / "REQ@1.a.x.md"
        rendered = repo / "diagram-catalog" / "rendered" / "MAT@1.a.m.md"
        _write(rendered, "[X](../../model/REQ@1.a.x.md)\n")

        assert rewrite_document_links_for_moved_artifact(repo_root=repo, old_path=old_path, new_path=new_path) == []

    def test_re_homing_an_entity_keeps_a_matrix_link_to_it(self, repo: Path) -> None:
        created = mcp.artifact_create_entity(
            artifact_type="requirement", name="Probe", dry_run=False, repo_root=str(repo),
        )
        entity_path = Path(created["path"])
        matrix = _matrix(repo, "MAT@1779100051.ffff.citing", f"../../{entity_path.relative_to(repo).as_posix()}")
        assert _unresolved(matrix) == []

        result = mcp.artifact_edit_entity(
            artifact_id=created["artifact_id"], group="my-group", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _unresolved(matrix) == []


def _matrix(repo: Path, artifact_id: str, href: str) -> Path:
    result = mcp.artifact_create_matrix(
        name="Matrix", matrix_markdown=f"| A | B |\n|---|---|\n| [Thing]({href}) | 2 |\n",
        artifact_id=artifact_id, infer_entity_ids=False, auto_link_entity_ids=False,
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return Path(result["path"])


# ---------------------------------------------------------------------------
# A diagram re-homed to another collection
# ---------------------------------------------------------------------------


class TestADiagramMovedToAnotherCollection:
    def test_a_matrix_keeps_its_own_links(self, repo: Path) -> None:
        entity = _entity(repo, "REQ@1779100061.gggg.scenery")
        matrix = _matrix(repo, "MAT@1779100062.gggg.moving", f"../../{entity.relative_to(repo).as_posix()}")
        assert _unresolved(matrix) == []

        result = mcp.artifact_edit_diagram(
            artifact_id="MAT@1779100062.gggg.moving", group="landing-zone", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        new_path = Path(result["path"])
        assert new_path.parent == matrix.parent / "landing-zone"
        assert _unresolved(new_path) == []

    def test_a_document_showing_its_rendered_image_still_shows_it(self, repo: Path) -> None:
        artifact_id = "DIA@1779100071.hhhh.moving"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml",
            f"---\nartifact-id: {artifact_id}\nartifact-type: diagram\ndiagram-type: c4-container\n"
            'name: "Moving"\nversion: 0.1.0\nstatus: draft\nlast-updated: \'2026-01-01\'\n'
            "entity-ids-used: []\nconnection-ids-used: []\ndiagram-entities:\n  software-system:\n"
            "  - id: sys\n    label: MySystem\n---\n@startuml moving\ntitle Moving\n@enduml\n",
        )
        _write(repo / "diagram-catalog" / "rendered" / f"{artifact_id}.svg", "<svg/>")
        citing = _adr(
            repo, "ADR@1779100072.hhhh.citing",
            f"![picture](../../diagram-catalog/rendered/{artifact_id}.svg) of "
            f"[the diagram](../../diagram-catalog/diagrams/{artifact_id}.puml).",
        )

        result = mcp.artifact_edit_diagram(
            artifact_id=artifact_id, group="landing-zone", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        text = citing.read_text(encoding="utf-8")
        assert f"(../../diagram-catalog/diagrams/landing-zone/{artifact_id}.puml)" in text
        assert f"(../../diagram-catalog/rendered/landing-zone/{artifact_id}.svg)" in text
