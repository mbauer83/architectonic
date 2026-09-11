"""A group rename moves the files, not only the registry entry — on every axis.

A document collection is backed by one directory per doc-type: `docs/adr/<slug>`,
`docs/arc42/<slug>`, and so on. The rename derived its destination from "the first *existing*
directory with the new slug", which for a slug nothing is filed under yet is nothing at all — so the
rename returned having moved no files while the registry took the new name. The verifier reports the
result as a group holding documents while not being declared a collection (W046), which is how this
was found: by renaming a real group and reading what the verifier said afterwards.

A diagram collection is backed by up to three: `diagrams/<slug>`, `diagrams/confidential/<slug>`,
and `rendered/<slug>`, which holds the PNG and SVG a diagram keeps on disk. The rename knew only the
first, so the sources moved and their rendered output stayed behind under the old slug. Nothing
reported it — the SVG route re-derives on read and kept answering 200 — until a PNG download in the
renamed collection answered `404 PNG not yet rendered — save the diagram first`, months later, while
re-shooting the documentation media. Measured in this repository, on `promotion-and-tiering`.

A model-project is the one axis backed by a single directory, and is here so the fix is shown not to
have moved it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.group_ops import group_create, group_rename


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "architecture-repository"
    for sub in ("projects", "diagram-catalog/diagrams", "docs/adr", "docs/arc42", ".arch-repo"):
        (root / sub).mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    return root


def _commit(repo: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)


class TestADocumentCollection:
    def test_every_doc_type_directory_moves(self, repo: Path) -> None:
        """The regression: only the first would have moved, and in practice none did."""
        group_create(repo, axis="document-collection", slug="old-name", name="Old Name")
        for doc_type in ("adr", "arc42"):
            (repo / "docs" / doc_type / "old-name").mkdir(parents=True)
            (repo / "docs" / doc_type / "old-name" / "a.md").write_text("x\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="document-collection", slug="old-name", new_slug="new-name")

        for doc_type in ("adr", "arc42"):
            assert (repo / "docs" / doc_type / "new-name" / "a.md").exists(), doc_type
            assert not (repo / "docs" / doc_type / "old-name").exists(), doc_type

    def test_the_registry_and_the_files_agree_afterwards(self, repo: Path) -> None:
        """The state the verifier complains about is exactly the two disagreeing."""
        from src.application.group_registry import load_group_registry

        group_create(repo, axis="document-collection", slug="old-name", name="Old Name")
        (repo / "docs" / "adr" / "old-name").mkdir(parents=True)
        (repo / "docs" / "adr" / "old-name" / "a.md").write_text("x\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="document-collection", slug="old-name", new_slug="new-name")

        slugs = {e.slug for e in load_group_registry(repo).document_collections}
        assert "new-name" in slugs and "old-name" not in slugs
        assert (repo / "docs" / "adr" / "new-name").exists()

    def test_a_collection_with_no_files_yet_renames_cleanly(self, repo: Path) -> None:
        """Nothing to move is not a failure — the registry entry still takes the new name."""
        group_create(repo, axis="document-collection", slug="empty-one", name="Empty One")
        _commit(repo)

        result = group_rename(repo, axis="document-collection", slug="empty-one", new_slug="renamed-one")

        assert result["slug"] == "renamed-one"


class TestADiagramCollection:
    """Sources and rendered output are filed under the same slug, so both follow the rename."""

    def test_the_rendered_output_moves_with_its_sources(self, repo: Path) -> None:
        """The regression: the PUML moved, the PNG and SVG did not, and the download 404ed."""
        group_create(repo, axis="diagram-collection", slug="old-name", name="Old Name")
        catalog = repo / "diagram-catalog"
        (catalog / "diagrams" / "old-name").mkdir(parents=True, exist_ok=True)
        source = catalog / "diagrams" / "old-name" / "ARC@1.abc.a-diagram.puml"
        source.write_text("@startuml\n@enduml\n", encoding="utf-8")
        (catalog / "rendered" / "old-name").mkdir(parents=True, exist_ok=True)
        for suffix in (".png", ".svg"):
            (catalog / "rendered" / "old-name" / f"ARC@1.abc.a-diagram{suffix}").write_bytes(b"x")
        _commit(repo)

        group_rename(repo, axis="diagram-collection", slug="old-name", new_slug="new-name")

        assert (catalog / "diagrams" / "new-name" / "ARC@1.abc.a-diagram.puml").exists()
        for suffix in (".png", ".svg"):
            assert (catalog / "rendered" / "new-name" / f"ARC@1.abc.a-diagram{suffix}").exists(), suffix
        assert not (catalog / "rendered" / "old-name").exists()

    def test_confidential_sources_move_too(self, repo: Path) -> None:
        """A second source root, under the same slug, and just as easy to leave behind."""
        group_create(repo, axis="diagram-collection", slug="old-name", name="Old Name")
        confidential = repo / "diagram-catalog" / "diagrams" / "confidential" / "old-name"
        confidential.mkdir(parents=True, exist_ok=True)
        (confidential / "ARC@1.abc.secret.puml").write_text("@startuml\n@enduml\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="diagram-collection", slug="old-name", new_slug="new-name")

        moved = repo / "diagram-catalog" / "diagrams" / "confidential" / "new-name"
        assert (moved / "ARC@1.abc.secret.puml").exists()
        assert not confidential.exists()

    def test_a_collection_with_sources_and_no_rendering_yet_renames_cleanly(self, repo: Path) -> None:
        """A diagram saved but never rendered has no rendered/<slug>; that is not a failure."""
        group_create(repo, axis="diagram-collection", slug="old-name", name="Old Name")
        (repo / "diagram-catalog" / "diagrams" / "old-name").mkdir(parents=True, exist_ok=True)
        (repo / "diagram-catalog" / "diagrams" / "old-name" / "a.puml").write_text("x\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="diagram-collection", slug="old-name", new_slug="new-name")

        assert (repo / "diagram-catalog" / "diagrams" / "new-name" / "a.puml").exists()


class TestTheSingleDirectoryAxis:
    def test_the_directory_still_moves(self, repo: Path) -> None:
        """A model-project was never broken; the fix derives its destination differently, so it is pinned."""
        group_create(repo, axis="model-project", slug="old-name", name="Old Name")
        (repo / "projects" / "old-name").mkdir(parents=True, exist_ok=True)
        (repo / "projects" / "old-name" / "a.md").write_text("x\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="model-project", slug="old-name", new_slug="new-name")

        assert (repo / "projects" / "new-name" / "a.md").exists()
        assert not (repo / "projects" / "old-name").exists()


class TestTheLinksIntoARenamedGroup:
    """A rename moves the files; the links naming them have to follow, or every citation breaks.

    Healed by the same function that heals a link when any artifact moves — its docstring already
    names a group re-home as one of those moves. A second reader matching directory segments would
    have been a second answer to "how does a link name a moved artifact", and a worse one: it could
    only fix links *into* the group, while path recomputation handles a document that moved too.
    """

    def test_a_document_citing_a_moved_artifact_is_rewritten(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="old-name", name="Old Name")
        artifact = repo / "projects" / "old-name" / "model" / "common" / "function"
        artifact.mkdir(parents=True)
        (artifact / "FNC@1.abc.thing.md").write_text("---\nartifact-id: FNC@1.abc.thing\n---\n", encoding="utf-8")
        doc_dir = repo / "docs" / "adr" / "somewhere"
        doc_dir.mkdir(parents=True)
        citing = doc_dir / "ADR@1.xyz.a-decision.md"
        citing.write_text(
            "See [Thing](../../../projects/old-name/model/common/function/FNC@1.abc.thing.md).\n",
            encoding="utf-8",
        )
        _commit(repo)

        group_rename(repo, axis="model-project", slug="old-name", new_slug="new-name")

        rewritten = citing.read_text(encoding="utf-8")
        assert "projects/new-name/" in rewritten
        assert "projects/old-name/" not in rewritten

    def test_a_link_the_rename_does_not_affect_is_left_alone(self, repo: Path) -> None:
        """The rewrite is keyed on the paths that actually moved, not on the slug as a word."""
        group_create(repo, axis="model-project", slug="old-name", name="Old Name")
        (repo / "projects" / "old-name").mkdir(parents=True, exist_ok=True)
        (repo / "projects" / "old-name" / "a.md").write_text("x\n", encoding="utf-8")
        other = repo / "projects" / "untouched"
        other.mkdir(parents=True)
        (other / "b.md").write_text("y\n", encoding="utf-8")
        doc_dir = repo / "docs" / "adr" / "somewhere"
        doc_dir.mkdir(parents=True)
        citing = doc_dir / "ADR@1.xyz.a-decision.md"
        citing.write_text("See [Other](../../../projects/untouched/b.md).\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis="model-project", slug="old-name", new_slug="new-name")

        assert "projects/untouched/b.md" in citing.read_text(encoding="utf-8")


def test_a_display_name_change_moves_nothing(repo: Path) -> None:
    """Renaming only the display name is a registry edit; the files must stay where they are."""
    group_create(repo, axis="model-project", slug="keep-slug", name="Old Name")
    (repo / "projects" / "keep-slug").mkdir(parents=True, exist_ok=True)
    (repo / "projects" / "keep-slug" / "a.md").write_text("x\n", encoding="utf-8")
    _commit(repo)

    group_rename(repo, axis="model-project", slug="keep-slug", new_name="New Name")

    assert (repo / "projects" / "keep-slug" / "a.md").exists()
