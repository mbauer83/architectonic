"""A link written with an artifact id is stored as a path, and read back as that artifact.

The pair is `id_links_expanded`, which writes the stored form, and the link owner's own readers —
`references_from` and `resolve_artifact_links` — which is what the verifier, the cascade preflight
and the typed-table reading all use. Stated over what a link may be: either id form, a `#section`,
a label with a pipe or none at all, several on a line, a document deeper or shallower than its
target, and the hrefs that are not ids and must keep their spelling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.document_links import (
    UnresolvedArtifactLink,
    as_link,
    id_links_expanded,
    references_from,
    resolve_artifact_links,
)

_REQUIREMENT = "REQ@1777135513.nn_s-a.write-composable-code"
_ADR = "ADR@1783406789.aBcDeF.one-way-references"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    files = {
        f"model/motivation/requirement/{_REQUIREMENT}.md": (
            f"---\nartifact-id: {_REQUIREMENT}\nartifact-type: requirement\nname: Write composable code\n---\n"
        ),
        f"docs/adr/platform/{_ADR}.md": (
            f"---\nartifact-id: {_ADR}\nartifact-type: document\ndoc-type: adr\ntitle: One-way references\n---\n"
        ),
    }
    for relative, content in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(content, encoding="utf-8")
    return tmp_path


def _path_of(repo: Path):  # noqa: ANN202 — the lookup the index gives, over the two files above
    by_id = {path.stem: path for path in repo.rglob("*@*.md")}
    by_short_id = {stem.rsplit(".", 1)[0]: path for stem, path in by_id.items()}
    return lambda artifact_id: by_id.get(artifact_id) or by_short_id.get(artifact_id)


_DOCUMENT_DIRECTORIES = ("docs/standard", "docs/adr/platform", "docs/a/b/c", "model/motivation/requirement")


@pytest.mark.parametrize("directory", _DOCUMENT_DIRECTORIES)
@pytest.mark.parametrize("artifact_id", [_REQUIREMENT, _REQUIREMENT.rsplit(".", 1)[0], _ADR, _ADR.rsplit(".", 1)[0]])
@pytest.mark.parametrize("anchor", ["", "#properties"])
@pytest.mark.parametrize("label", ["the requirement", "a|b", "", "with `code`"])
def test_the_stored_link_is_read_as_the_artifact_the_id_names(
    repo: Path, directory: str, artifact_id: str, anchor: str, label: str
) -> None:
    doc = repo / directory / "DOC@1.a.doc.md"
    doc.parent.mkdir(parents=True, exist_ok=True)

    stored = id_links_expanded(
        f"See [{label}]({artifact_id}{anchor}) here.", written_to=doc.parent, path_of=_path_of(repo)
    )

    (reference,) = references_from(stored, directory=doc.parent)
    (resolved,) = resolve_artifact_links(doc, stored)
    full_id = _REQUIREMENT if artifact_id.startswith("REQ") else _ADR
    assert reference.target.stem == full_id and reference.target.is_file()
    assert resolved.artifact_id == full_id
    assert reference.href.endswith(f".md{anchor}") and not reference.href.startswith("/")
    assert reference.label == (label or resolved.name)


def test_several_links_on_a_line_are_each_stored(repo: Path) -> None:
    doc = repo / "docs/standard/DOC@1.a.doc.md"

    stored = id_links_expanded(
        f"[a]({_REQUIREMENT}), [b]({_ADR}#decision) and ![c]({_ADR}).", written_to=doc.parent, path_of=_path_of(repo)
    )

    assert stored == (
        f"[a](../../model/motivation/requirement/{_REQUIREMENT}.md), [b](../adr/platform/{_ADR}.md#decision) "
        f"and ![c](../adr/platform/{_ADR}.md)."
    )


@pytest.mark.parametrize(
    "kept",
    [
        f"[a](../../model/motivation/requirement/{_REQUIREMENT}.md)",
        "[a](https://example.org/REQ@1.x)",
        "[a](#REQ@1.x)",
        "[a](mailto:REQ@1.x)",
        "[a](notes.md) and a bare REQ@1.x in prose",
        "`[a](REQ@1.x` is not a link",
    ],
)
def test_an_href_that_is_not_an_id_keeps_its_spelling(repo: Path, kept: str) -> None:
    assert id_links_expanded(kept, written_to=repo / "docs/standard", path_of=_path_of(repo)) == kept


def test_a_file_beside_the_document_is_a_path_whatever_it_is_called(repo: Path) -> None:
    """`ADR@1.x.md` is spelled as a short id with the slug `md`; beside the document it is a file."""
    beside = repo / "docs/standard/ADR@1.x.md"
    beside.parent.mkdir(parents=True, exist_ok=True)
    beside.write_text("---\nartifact-id: ADR@1.x\n---\n", encoding="utf-8")

    assert id_links_expanded("[a](ADR@1.x.md)", written_to=beside.parent, path_of=lambda _: None) == "[a](ADR@1.x.md)"


def test_every_id_that_names_nothing_is_named_in_one_refusal(repo: Path) -> None:
    with pytest.raises(UnresolvedArtifactLink) as refused:
        id_links_expanded(
            f"[a](REQ@1.gone) [b]({_ADR}) [c](GOL@2.also-gone.slug#x) [d](REQ@1.gone)",
            written_to=repo / "docs/standard", path_of=_path_of(repo),
        )

    assert str(refused.value).startswith("GOL@2.also-gone.slug, REQ@1.gone: no artifact of this repository has these")


@pytest.mark.parametrize(
    ("stated", "link"),
    [("REQ@1.x", "[](REQ@1.x)"), (" REQ@1.x ", "[](REQ@1.x)"), ("[the one](REQ@1.x)", "[the one](REQ@1.x)")],
)
def test_a_reference_stated_as_an_id_alone_is_a_link_with_no_label(stated: str, link: str) -> None:
    assert as_link(stated) == link
