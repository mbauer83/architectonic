"""A staged root answers directory discovery the way the live root does.

The staging tree is copy-on-write: files materialize only when something writes one, and
`overlay_paths` serves callers that enumerate files under a directory they already know. Nothing
served the callers that *discover* which directories to look in — `all_model_roots` asks
`exists()` and `iterdir()`, gets an empty staged root, and returns no model roots at all. The index
scan then runs over nothing and every lookup against a staged index answers `None`.

That is what broke `artifact_bulk_delete(auto_sync_diagrams=True)`: reconciling a scope-bound C4
diagram asks the staged index for the diagram's scope entity, was told the repository does not
contain it, and the whole batch failed with `scope entity ... not found` — so no connection any C4
component diagram drew could be deleted at all.

Directories are mirrored by the operation that needs a full index, not by creating the staging tree:
staging is O(1) by design and a fitness test holds it there. Files stay copy-on-write either way.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repo_path_helpers import all_model_roots
from src.infrastructure.write.artifact_write.staged_workspace import (
    StagedWorkspace,
    materialize_directory_skeleton,
)


def _live_repo(root: Path) -> Path:
    """A repository skeleton with the two directory shapes discovery depends on."""
    (root / "projects" / "platform-core" / "model" / "application").mkdir(parents=True)
    (root / "projects" / "assurance" / "model" / "business").mkdir(parents=True)
    (root / "docs" / "adr").mkdir(parents=True)
    (root / ".git" / "objects").mkdir(parents=True)
    (root / ".arch-repo" / "transactions").mkdir(parents=True)
    (root / "projects" / "platform-core" / "model" / "application" / "APP@1.a.thing.md").write_text(
        "---\nartifact-id: APP@1.a.thing\n---\n"
    )
    return root


def test_staged_root_mirrors_directories_but_not_files(tmp_path: Path) -> None:
    live = _live_repo(tmp_path / "live")
    staged = tmp_path / "staged"
    workspace = StagedWorkspace(live_root=live, staged_root=staged)
    workspace.create_mirror()
    workspace.activate()
    try:
        materialize_directory_skeleton(staged)
    finally:
        workspace.deactivate()

    assert (staged / "projects" / "platform-core" / "model" / "application").is_dir()
    assert (staged / "docs" / "adr").is_dir()
    # Content stays lazy: the file is not copied until something writes it.
    assert not (staged / "projects" / "platform-core" / "model" / "application" / "APP@1.a.thing.md").exists()


def test_staged_root_excludes_git_and_the_transactions_tree(tmp_path: Path) -> None:
    """Mirroring `.arch-repo` would walk the staging tree being created; `.git` is not ours."""
    live = _live_repo(tmp_path / "live")
    staged = tmp_path / "staged"
    workspace = StagedWorkspace(live_root=live, staged_root=staged)
    workspace.create_mirror()
    workspace.activate()
    try:
        materialize_directory_skeleton(staged)
    finally:
        workspace.deactivate()

    assert not (staged / ".git").exists()
    assert not (staged / ".arch-repo").exists()


def test_model_roots_are_discoverable_under_a_staged_root(tmp_path: Path) -> None:
    """The regression itself: without the skeleton this returns [] and the index scans nothing."""
    live = _live_repo(tmp_path / "live")
    staged = tmp_path / "staged"
    workspace = StagedWorkspace(live_root=live, staged_root=staged)
    workspace.create_mirror()
    workspace.activate()
    try:
        materialize_directory_skeleton(staged)
    finally:
        workspace.deactivate()

    discovered = {p.relative_to(staged) for p in all_model_roots(staged)}
    assert discovered == {
        Path("projects/platform-core/model"),
        Path("projects/assurance/model"),
    }


def test_repository_configuration_is_readable_under_a_staged_root(tmp_path: Path) -> None:
    """Configuration is found by listing and by `exists()`, which a lazy tree answers with nothing."""
    live = _live_repo(tmp_path / "live")
    (live / ".arch-repo" / "documents").mkdir()
    (live / ".arch-repo" / "documents" / "adr.json").write_text("{}")
    (live / ".arch-repo" / "groups.yaml").write_text("model-projects: []\n")
    staged = tmp_path / "staged"
    workspace = StagedWorkspace(live_root=live, staged_root=staged)
    workspace.create_mirror()
    workspace.activate()
    try:
        assert [p.name for p in (staged / ".arch-repo" / "documents").glob("*.json")] == ["adr.json"]
        assert (staged / ".arch-repo" / "groups.yaml").read_text() == "model-projects: []\n"
        assert not (staged / ".arch-repo" / "transactions").exists()

        # A write to staged configuration is the batch's own: it never reaches the live file.
        (staged / ".arch-repo" / "groups.yaml").write_text("staged\n")
        (staged / ".arch-repo" / "documents" / "spec.json").write_text("{}")
    finally:
        workspace.deactivate()

    assert (live / ".arch-repo" / "groups.yaml").read_text() == "model-projects: []\n"
    assert not (live / ".arch-repo" / "documents" / "spec.json").exists()
