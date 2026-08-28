"""Tests for group_ops.py and _group_fs.py.

Covers: create/rename/archive/unarchive/delete/update lifecycle operations across
all three group axes (model-project, diagram-collection, document-collection), the
group_op dispatch, and the helper utilities in _group_fs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.group_registry import load_group_registry
from src.infrastructure.write.artifact_write._group_fs import (
    _collection_dirs,
    _collection_files,
    _group_dir,
    _safe_rmdir,
    _update_axis,
)
from src.infrastructure.write.artifact_write.group_ops import (
    GroupOpError,
    group_archive,
    group_create,
    group_delete_collection,
    group_op,
    group_rename,
    group_unarchive,
    group_update,
)

# ---------------------------------------------------------------------------
# Git-repo fixture
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# group_create
# ---------------------------------------------------------------------------


class TestGroupCreate:
    @pytest.mark.verifies("REQ@1780505955.MdtfC3")
    def test_creates_model_project(self, repo: Path) -> None:
        result = group_create(repo, axis="model-project", slug="alpha", name="Alpha Project")
        assert result["action"] == "created"
        assert result["slug"] == "alpha"
        assert result["axis"] == "model-project"
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "alpha")
        assert entry is not None
        assert entry.name == "Alpha Project"

    @pytest.mark.verifies("REQ@1780505955.MdtfC3")
    def test_creates_diagram_collection(self, repo: Path) -> None:
        result = group_create(
            repo,
            axis="diagram-collection",
            slug="dc-alpha",
            name="Diagram Alpha",
            type_filter=("archimate",),
        )
        assert result["action"] == "created"
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc-alpha")
        assert entry is not None
        assert entry.type_filter == ("archimate",)
        # model-project ignores type_filter
        assert entry.meta_ontology == ""

    @pytest.mark.verifies("REQ@1780505955.MdtfC3")
    def test_creates_document_collection(self, repo: Path) -> None:
        group_create(repo, axis="document-collection", slug="docs-main", name="Docs Main")
        registry = load_group_registry(repo)
        assert registry.find("document-collection", "docs-main") is not None

    def test_duplicate_slug_raises(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="beta", name="Beta")
        with pytest.raises(GroupOpError, match="already exists"):
            group_create(repo, axis="model-project", slug="beta", name="Beta 2")

    def test_model_project_ignores_type_filter(self, repo: Path) -> None:
        group_create(
            repo, axis="model-project", slug="mp1", name="MP1",
            type_filter=("archimate", "c4"),
        )
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "mp1")
        assert entry is not None
        assert entry.type_filter == ()

    def test_model_project_stores_meta_ontology(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="mp2", name="MP2", meta_ontology="archimate-4")
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "mp2")
        assert entry is not None
        assert entry.meta_ontology == "archimate-4"

    def test_collection_ignores_meta_ontology(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc2", name="DC2", meta_ontology="archimate-4")
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc2")
        assert entry is not None
        assert entry.meta_ontology == ""


# ---------------------------------------------------------------------------
# group_rename
# ---------------------------------------------------------------------------


class TestGroupRename:
    def test_rename_display_name_only(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="proj-a", name="Old Name")
        result = group_rename(repo, axis="model-project", slug="proj-a", new_name="New Name")
        assert result["action"] == "renamed"
        assert result["slug"] == "proj-a"
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "proj-a")
        assert entry is not None
        assert entry.name == "New Name"

    def test_rename_slug_no_existing_dir(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="old-slug", name="Old")
        result = group_rename(
            repo, axis="model-project", slug="old-slug",
            new_slug="new-slug", new_name="New",
        )
        assert result["action"] == "renamed"
        assert result["slug"] == "new-slug"
        assert result["old_slug"] == "old-slug"
        registry = load_group_registry(repo)
        assert registry.find("model-project", "old-slug") is None
        assert registry.find("model-project", "new-slug") is not None

    def test_rename_slug_same_as_current_does_not_move(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="same", name="Same")
        result = group_rename(repo, axis="model-project", slug="same", new_slug="same", new_name="Same Updated")
        assert result["slug"] == "same"
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "same")
        assert entry is not None
        assert entry.name == "Same Updated"

    def test_rename_slug_with_existing_dir(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="src-slug", name="Source")
        old_dir = repo / "projects" / "src-slug"
        old_dir.mkdir(parents=True)
        (old_dir / "entity.md").write_text("# test")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add dir"], cwd=repo, capture_output=True)
        result = group_rename(repo, axis="model-project", slug="src-slug", new_slug="dst-slug")
        assert result["slug"] == "dst-slug"
        assert (repo / "projects" / "dst-slug").exists()

    def test_rename_to_existing_slug_raises(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="first", name="First")
        group_create(repo, axis="model-project", slug="second", name="Second")
        with pytest.raises(GroupOpError, match="already exists"):
            group_rename(repo, axis="model-project", slug="first", new_slug="second")

    def test_rename_unknown_slug_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="not found"):
            group_rename(repo, axis="model-project", slug="no-such", new_name="X")


# ---------------------------------------------------------------------------
# group_archive / group_unarchive
# ---------------------------------------------------------------------------


class TestGroupArchive:
    def test_archive_empty_group(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-empty", name="DC Empty")
        result = group_archive(repo, axis="diagram-collection", slug="dc-empty", confirm=None)
        assert result["action"] == "archived"
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc-empty")
        assert entry is not None
        assert entry.archived is True

    def test_archive_nonempty_requires_confirm(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-full", name="DC Full")
        coll_dir = repo / "diagram-catalog" / "diagrams" / "dc-full"
        coll_dir.mkdir(parents=True)
        (coll_dir / "diagram.puml").write_text("@startuml\n@enduml\n")
        with pytest.raises(GroupOpError, match="Pass confirm"):
            group_archive(repo, axis="diagram-collection", slug="dc-full", confirm=None)

    def test_archive_nonempty_with_confirm(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-conf", name="DC Conf")
        coll_dir = repo / "diagram-catalog" / "diagrams" / "dc-conf"
        coll_dir.mkdir(parents=True)
        (coll_dir / "diagram.puml").write_text("@startuml\n@enduml\n")
        result = group_archive(repo, axis="diagram-collection", slug="dc-conf", confirm="dc-conf")
        assert result["action"] == "archived"

    def test_archive_uncategorized_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="uncategorized"):
            group_archive(repo, axis="model-project", slug="uncategorized", confirm=None)

    def test_unarchive(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="arc-mp", name="Arc MP")
        group_archive(repo, axis="model-project", slug="arc-mp", confirm=None)
        result = group_unarchive(repo, axis="model-project", slug="arc-mp")
        assert result["action"] == "unarchived"
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "arc-mp")
        assert entry is not None
        assert entry.archived is False

    def test_archive_unknown_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="not found"):
            group_archive(repo, axis="model-project", slug="ghost", confirm=None)


# ---------------------------------------------------------------------------
# group_delete_collection
# ---------------------------------------------------------------------------


class TestGroupDeleteCollection:
    def test_delete_empty_diagram_collection(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-del", name="Del")
        result = group_delete_collection(repo, axis="diagram-collection", slug="dc-del", confirm="dc-del")
        assert result["action"] == "deleted"
        assert result["files_removed"] == 0
        registry = load_group_registry(repo)
        assert registry.find("diagram-collection", "dc-del") is None

    def test_delete_collection_no_confirm_when_empty(self, repo: Path) -> None:
        group_create(repo, axis="document-collection", slug="doc-empty", name="DocEmpty")
        result = group_delete_collection(repo, axis="document-collection", slug="doc-empty", confirm=None)
        assert result["action"] == "deleted"

    def test_delete_nonempty_requires_confirm(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-nonempty", name="Non-empty")
        coll_dir = repo / "diagram-catalog" / "diagrams" / "dc-nonempty"
        coll_dir.mkdir(parents=True)
        (coll_dir / "diag.puml").write_text("@startuml\n@enduml\n")
        with pytest.raises(GroupOpError, match="Pass confirm"):
            group_delete_collection(repo, axis="diagram-collection", slug="dc-nonempty", confirm=None)

    def test_delete_uncategorized_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="uncategorized"):
            group_delete_collection(
                repo, axis="diagram-collection", slug="uncategorized", confirm="uncategorized"
            )

    def test_delete_nonempty_with_confirm_removes_files(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-files", name="Files")
        coll_dir = repo / "diagram-catalog" / "diagrams" / "dc-files"
        coll_dir.mkdir(parents=True)
        f = coll_dir / "diag.puml"
        f.write_text("@startuml\n@enduml\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add diag"], cwd=repo, capture_output=True)
        result = group_delete_collection(repo, axis="diagram-collection", slug="dc-files", confirm="dc-files")
        assert result["files_removed"] == 1
        assert not f.exists()

    def test_delete_model_project_dry_run(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="mp-del", name="MP Del")
        result = group_delete_collection(
            repo, axis="model-project", slug="mp-del", confirm="mp-del", dry_run=True
        )
        assert result["dry_run"] is True
        assert result["project"] == "mp-del"

    def test_delete_model_project_confirm_mismatch_raises(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="mp-x", name="MP X")
        with pytest.raises(GroupOpError):
            group_delete_collection(repo, axis="model-project", slug="mp-x", confirm="wrong", dry_run=False)


# ---------------------------------------------------------------------------
# group_update
# ---------------------------------------------------------------------------


class TestGroupUpdate:
    def test_update_display_name(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="upd-mp", name="Original")
        result = group_update(repo, axis="model-project", slug="upd-mp", name="Updated")
        assert result["action"] == "updated"
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "upd-mp")
        assert entry is not None
        assert entry.name == "Updated"

    def test_update_description(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-upd", name="DC Upd")
        group_update(repo, axis="diagram-collection", slug="dc-upd", description="New desc")
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc-upd")
        assert entry is not None
        assert entry.description == "New desc"

    def test_update_type_filter_on_collection(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="dc-tf", name="DC TF")
        group_update(repo, axis="diagram-collection", slug="dc-tf", type_filter=["archimate", "c4"])
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc-tf")
        assert entry is not None
        assert entry.type_filter == ("archimate", "c4")

    def test_update_type_filter_ignored_on_model_project(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="mp-tf", name="MP TF")
        group_update(repo, axis="model-project", slug="mp-tf", type_filter=["archimate"])
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "mp-tf")
        assert entry is not None
        assert entry.type_filter == ()

    def test_update_meta_ontology_on_model_project(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="mp-mo", name="MP MO")
        group_update(repo, axis="model-project", slug="mp-mo", meta_ontology="togaf")
        registry = load_group_registry(repo)
        entry = registry.find("model-project", "mp-mo")
        assert entry is not None
        assert entry.meta_ontology == "togaf"

    def test_update_unknown_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="not found"):
            group_update(repo, axis="model-project", slug="no-such", name="X")


# ---------------------------------------------------------------------------
# group_op dispatch
# ---------------------------------------------------------------------------


class TestGroupOp:
    def test_dispatch_create(self, repo: Path) -> None:
        result = group_op(repo, axis="model-project", action="create", target="op-mp", name="OP MP")
        assert result["action"] == "created"

    def test_dispatch_rename(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="ren-src", name="Ren Src")
        result = group_op(repo, axis="model-project", action="rename", target="ren-src", name="Ren Dst")
        assert result["action"] == "renamed"

    def test_dispatch_archive(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="arch-op", name="Archive Op")
        result = group_op(repo, axis="model-project", action="archive", target="arch-op")
        assert result["action"] == "archived"

    def test_dispatch_unarchive(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="unarc-op", name="Unarchive Op")
        group_op(repo, axis="model-project", action="archive", target="unarc-op")
        result = group_op(repo, axis="model-project", action="unarchive", target="unarc-op")
        assert result["action"] == "unarchived"

    def test_dispatch_delete(self, repo: Path) -> None:
        group_create(repo, axis="diagram-collection", slug="del-op", name="Del Op")
        result = group_op(
            repo, axis="diagram-collection", action="delete", target="del-op", confirm="del-op"
        )
        assert result["action"] == "deleted"

    def test_dispatch_update(self, repo: Path) -> None:
        group_create(repo, axis="model-project", slug="upd-op", name="Upd Op")
        result = group_op(
            repo, axis="model-project", action="update", target="upd-op", name="Updated Op"
        )
        assert result["action"] == "updated"

    def test_dispatch_unknown_action_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="Unknown action"):
            group_op(repo, axis="model-project", action="frobnicate", target="any")  # type: ignore[arg-type]

    def test_dispatch_missing_target_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="target"):
            group_op(repo, axis="model-project", action="create", target=None)

    def test_dispatch_empty_target_raises(self, repo: Path) -> None:
        with pytest.raises(GroupOpError, match="target"):
            group_op(repo, axis="model-project", action="rename", target="")

    def test_dispatch_with_type_filter(self, repo: Path) -> None:
        result = group_op(
            repo, axis="diagram-collection", action="create", target="dc-op",
            name="DC Op", type_filter=["archimate"],
        )
        assert result["action"] == "created"
        registry = load_group_registry(repo)
        entry = registry.find("diagram-collection", "dc-op")
        assert entry is not None
        assert entry.type_filter == ("archimate",)


# ---------------------------------------------------------------------------
# _group_fs helpers
# ---------------------------------------------------------------------------


class TestGroupFsHelpers:
    def test_update_axis_model_project(self, repo: Path) -> None:
        from src.domain.repository.groups import GroupEntry, GroupRegistry

        reg = GroupRegistry()
        entry = GroupEntry(slug="x", id="GRP@1.x", name="X")
        updated = _update_axis(reg, "model-project", [entry])
        assert updated.model_projects == (entry,)

    def test_update_axis_diagram_collection(self, repo: Path) -> None:
        from src.domain.repository.groups import GroupEntry, GroupRegistry

        reg = GroupRegistry()
        entry = GroupEntry(slug="dc", id="GRP@1.dc", name="DC")
        updated = _update_axis(reg, "diagram-collection", [entry])
        assert updated.diagram_collections == (entry,)

    def test_update_axis_document_collection(self, repo: Path) -> None:
        from src.domain.repository.groups import GroupEntry, GroupRegistry

        reg = GroupRegistry()
        entry = GroupEntry(slug="doc", id="GRP@1.doc", name="Doc")
        updated = _update_axis(reg, "document-collection", [entry])
        assert updated.document_collections == (entry,)

    def test_group_dir_model_project(self, repo: Path) -> None:
        d = _group_dir(repo, "model-project", "my-proj")
        assert d == repo / "projects" / "my-proj"

    def test_group_dir_diagram_collection(self, repo: Path) -> None:
        d = _group_dir(repo, "diagram-collection", "dc-slug")
        assert d is not None
        assert d.name == "dc-slug"

    def test_group_dir_document_collection_no_dirs(self, repo: Path) -> None:
        d = _group_dir(repo, "document-collection", "nonexistent")
        assert d is None

    def test_group_dir_document_collection_with_dir(self, repo: Path) -> None:
        slug = "my-docs"
        docs_dir = repo / "docs" / "specification" / slug
        docs_dir.mkdir(parents=True)
        d = _group_dir(repo, "document-collection", slug)
        assert d == docs_dir

    def test_collection_dirs_empty(self, repo: Path) -> None:
        dirs = _collection_dirs(repo, "diagram-collection", "missing")
        assert dirs == []

    def test_collection_dirs_existing(self, repo: Path) -> None:
        slug = "dc-present"
        coll_dir = repo / "diagram-catalog" / "diagrams" / slug
        coll_dir.mkdir(parents=True)
        dirs = _collection_dirs(repo, "diagram-collection", slug)
        assert len(dirs) == 1
        assert dirs[0] == coll_dir

    def test_collection_dirs_document_multiple(self, repo: Path) -> None:
        slug = "multi-doc"
        for doc_type in ("spec", "adr"):
            (repo / "docs" / doc_type / slug).mkdir(parents=True)
        dirs = _collection_dirs(repo, "document-collection", slug)
        assert len(dirs) == 2

    def test_collection_files_empty_dir(self, repo: Path) -> None:
        slug = "dc-empty-files"
        coll_dir = repo / "diagram-catalog" / "diagrams" / slug
        coll_dir.mkdir(parents=True)
        files = _collection_files(repo, "diagram-collection", slug)
        assert files == []

    def test_collection_files_with_files(self, repo: Path) -> None:
        slug = "dc-with-files"
        coll_dir = repo / "diagram-catalog" / "diagrams" / slug
        coll_dir.mkdir(parents=True)
        (coll_dir / "a.puml").write_text("")
        (coll_dir / "b.puml").write_text("")
        files = _collection_files(repo, "diagram-collection", slug)
        assert len(files) == 2

    def test_safe_rmdir_success(self, repo: Path) -> None:
        d = repo / "tmpdir"
        d.mkdir()
        _safe_rmdir(d)
        assert not d.exists()

    def test_safe_rmdir_nonempty_silently_ignored(self, repo: Path) -> None:
        d = repo / "nonempty"
        d.mkdir()
        (d / "file.txt").write_text("x")
        _safe_rmdir(d)
        assert d.exists()  # rmdir on non-empty dir raises OSError, which is swallowed


class TestADescriptionCanBeSetAfterCreation:
    """`update` is the action that sets display metadata in place, and MCP could not reach it.

    `group_ops` has always had it and REST has always called it, but the MCP tool's action list
    omitted it — so an agent authoring a collection could give it a description at create and never
    afterwards. Six diagram collections in the reference repository have none for that reason.
    `rename` changes the name and the slug and has never stored a description; accepting one and
    ignoring it is what made the gap invisible.
    """

    def _description(self, repo: Path, slug: str) -> str | None:
        import yaml

        registry = yaml.safe_load((repo / ".arch-repo" / "groups.yaml").read_text(encoding="utf-8"))
        for entries in (registry or {}).values():
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict) and entry.get("slug") == slug:
                    return entry.get("description")
        return None

    def test_update_is_reachable_through_the_mcp_tool(self, tmp_path: Path) -> None:
        from src.infrastructure.mcp.artifact_mcp.write.group import artifact_group
        from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        (repo / "model").mkdir(parents=True)
        (repo / "diagram-catalog" / "diagrams").mkdir(parents=True)
        ensure_arch_repo_defaults(repo)
        artifact_group(kind="diagram-collection", action="create", target="views", name="Views",
                       dry_run=False, repo_root=str(repo))
        assert self._description(repo, "views") in (None, "")

        result = artifact_group(kind="diagram-collection", action="update", target="views",
                                description="Every view of the platform",
                                dry_run=False, repo_root=str(repo))

        assert result["wrote"] is True
        assert self._description(repo, "views") == "Every view of the platform"

    def test_rename_refuses_a_description_and_names_the_action_that_stores_one(
        self, tmp_path: Path
    ) -> None:
        from src.infrastructure.mcp.artifact_mcp.write.group import artifact_group
        from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        (repo / "model").mkdir(parents=True)
        (repo / "diagram-catalog" / "diagrams").mkdir(parents=True)
        ensure_arch_repo_defaults(repo)
        artifact_group(kind="diagram-collection", action="create", target="views", name="Views",
                       dry_run=False, repo_root=str(repo))

        result = artifact_group(kind="diagram-collection", action="rename", target="views",
                                name="All Views", description="silently dropped before",
                                dry_run=False, repo_root=str(repo))

        assert "update" in str(result.get("error", "")), result
        # and the rename did not half-happen
        assert self._description(repo, "views") in (None, "")
        registry = __import__("yaml").safe_load(
            (repo / ".arch-repo" / "groups.yaml").read_text(encoding="utf-8")
        )
        names = [
            entry.get("name")
            for entries in (registry or {}).values() if isinstance(entries, list)
            for entry in entries if isinstance(entry, dict)
        ]
        assert names == ["Views"], f"the refused rename still changed the name: {names}"
