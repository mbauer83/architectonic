"""A group rename moves the files, not only the registry entry — on every axis.

A document collection is backed by one directory per doc-type: `docs/adr/<slug>`,
`docs/arc42/<slug>`, and so on. The rename derived its destination from "the first *existing*
directory with the new slug", which for a slug nothing is filed under yet is nothing at all — so the
rename returned having moved no files while the registry took the new name. The verifier reports the
result as a group holding documents while not being declared a collection (W046), which is how this
was found: by renaming a real group and reading what the verifier said afterwards.

The single-directory axes were never broken, and are here so the fix is shown not to have moved them.
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


class TestTheSingleDirectoryAxes:
    @pytest.mark.parametrize(
        ("axis", "parent"),
        [("model-project", "projects"), ("diagram-collection", "diagram-catalog/diagrams")],
    )
    def test_the_directory_still_moves(self, repo: Path, axis, parent) -> None:
        """These were never broken; the fix derives their destination differently, so they are pinned."""
        group_create(repo, axis=axis, slug="old-name", name="Old Name")
        (repo / parent / "old-name").mkdir(parents=True, exist_ok=True)
        (repo / parent / "old-name" / "a.md").write_text("x\n", encoding="utf-8")
        _commit(repo)

        group_rename(repo, axis=axis, slug="old-name", new_slug="new-name")

        assert (repo / parent / "new-name" / "a.md").exists()
        assert not (repo / parent / "old-name").exists()


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
