"""Tests for cascade_delete.py and _cascade_helpers.py.

Covers: preflight scanning (owned/foreign/blocking), apply with rollback-on-failure,
apply_blocked_by guard, confirm mismatch, and all pure helper functions in
_cascade_helpers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write._cascade_helpers import (
    conn_row_touches,
    conn_touches,
    find_broken_links,
    read_connection_targets,
    read_diagram_frontmatter,
    read_frontmatter_id_name,
    read_source_entity_id,
    remove_from_groups_yaml,
    rollback_cascade,
)
from src.infrastructure.write.artifact_write.cascade_delete import (
    _cascade_preflight,
    _scan_blocking_docs,
    _scan_foreign_connections,
    _scan_foreign_diagrams,
    _scan_owned,
    cascade_delete_model_project,
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


def _entity_md(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: capability
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

## {name}
"""


def _outgoing_md(source_id: str, target_id: str, conn_type: str = "association") -> str:
    return f"""\
---
source-entity: {source_id}
---

### {conn_type} → {target_id}

Description.
"""


# ---------------------------------------------------------------------------
# _cascade_helpers: pure helpers
# ---------------------------------------------------------------------------


class TestReadFrontmatterIdName:
    def test_returns_id_and_name(self, tmp_path: Path) -> None:
        f = tmp_path / "entity.md"
        # regex matches the raw YAML value including any surrounding quotes
        f.write_text("---\nartifact-id: ENT@1.foo\nname: Foo Entity\n---\n")
        result = read_frontmatter_id_name(f)
        assert result == ("ENT@1.foo", "Foo Entity")

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "entity.md"
        f.write_text("No frontmatter here.\n")
        assert read_frontmatter_id_name(f) is None

    def test_missing_id_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "entity.md"
        f.write_text("---\nname: \"Only Name\"\n---\n")
        assert read_frontmatter_id_name(f) is None

    def test_missing_name_uses_stem(self, tmp_path: Path) -> None:
        f = tmp_path / "my-stem.md"
        f.write_text("---\nartifact-id: ENT@2.bar\n---\n")
        result = read_frontmatter_id_name(f)
        assert result == ("ENT@2.bar", "my-stem")

    def test_os_error_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.md"
        assert read_frontmatter_id_name(f) is None


class TestReadSourceEntityId:
    def test_returns_source_id(self, tmp_path: Path) -> None:
        f = tmp_path / "conn.md"
        f.write_text("---\nsource-entity: ENT@1.src\n---\n")
        assert read_source_entity_id(f) == "ENT@1.src"

    def test_no_source_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "conn.md"
        f.write_text("---\nartifact-id: X\n---\n")
        assert read_source_entity_id(f) is None

    def test_os_error_returns_none(self, tmp_path: Path) -> None:
        assert read_source_entity_id(Path("/no/such/file.md")) is None


class TestReadConnectionTargets:
    def test_returns_target_ids(self, tmp_path: Path) -> None:
        f = tmp_path / "conn.md"
        f.write_text("### association → ENT@1.tgt\n\n### composition → ENT@2.tgt\n")
        targets = read_connection_targets(f)
        assert "ENT@1.tgt" in targets
        assert "ENT@2.tgt" in targets

    def test_no_targets_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "conn.md"
        f.write_text("No connection headers here.\n")
        assert read_connection_targets(f) == []

    def test_os_error_returns_empty(self, tmp_path: Path) -> None:
        assert read_connection_targets(Path("/no/such/file.md")) == []


class TestReadDiagramFrontmatter:
    def test_returns_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "diag.puml"
        f.write_text("---\nartifact-id: DIA@1.foo\nname: \"Foo Diag\"\n---\n@startuml\n@enduml\n")
        result = read_diagram_frontmatter(f)
        assert result is not None
        assert result["artifact-id"] == "DIA@1.foo"

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "diag.puml"
        f.write_text("@startuml\n@enduml\n")
        assert read_diagram_frontmatter(f) is None

    def test_bad_yaml_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "diag.puml"
        f.write_text("---\n: bad: yaml: [\n---\n@startuml\n@enduml\n")
        assert read_diagram_frontmatter(f) is None

    def test_os_error_returns_none(self, tmp_path: Path) -> None:
        assert read_diagram_frontmatter(Path("/no/such/file.puml")) is None

    def test_empty_yaml_returns_empty_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "diag.puml"
        f.write_text("---\n---\n@startuml\n@enduml\n")
        result = read_diagram_frontmatter(f)
        assert result == {}


class TestConnTouches:
    def test_touches_when_id_contains_entity(self) -> None:
        assert conn_touches("ENT@1.abc--association--ENT@2.def", {"ENT@1.abc"})

    def test_does_not_touch_unrelated(self) -> None:
        assert not conn_touches("ENT@3.xyz--association--ENT@4.ghi", {"ENT@1.abc"})


class TestConnRowTouches:
    def test_touches_source(self) -> None:
        assert conn_row_touches({"source": "ENT@1.abc", "target": "ENT@2.def"}, {"ENT@1.abc"})

    def test_touches_target(self) -> None:
        assert conn_row_touches({"source": "ENT@3.xyz", "target": "ENT@1.abc"}, {"ENT@1.abc"})

    def test_does_not_touch_unrelated(self) -> None:
        assert not conn_row_touches({"source": "ENT@3.xyz", "target": "ENT@4.ghi"}, {"ENT@1.abc"})

    def test_non_dict_returns_false(self) -> None:
        assert not conn_row_touches("not-a-dict", {"ENT@1.abc"})

    def test_empty_entity_ids(self) -> None:
        assert not conn_row_touches({"source": "ENT@1.abc", "target": "ENT@2.def"}, set())


class TestFindBrokenLinks:
    def test_finds_link_to_owned_path(self, tmp_path: Path) -> None:
        owned = tmp_path / "projects" / "mp" / "model" / "entity.md"
        owned.parent.mkdir(parents=True)
        owned.write_text("# entity")
        doc = tmp_path / "docs" / "spec" / "doc.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(f"[Entity]({owned})\n")
        broken = find_broken_links(doc, {owned}, tmp_path)
        assert len(broken) == 1

    def test_no_broken_links_when_not_owned(self, tmp_path: Path) -> None:
        other = tmp_path / "other.md"
        other.write_text("# other")
        doc = tmp_path / "doc.md"
        doc.write_text("[Other](other.md)\n")
        broken = find_broken_links(doc, set(), tmp_path)
        assert broken == []

    def test_os_error_returns_empty(self, tmp_path: Path) -> None:
        assert find_broken_links(Path("/no/such/file.md"), set(), tmp_path) == []


class TestRemoveFromGroupsYaml:
    def test_removes_project_from_registry(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="to-remove", name="To Remove")
        remove_from_groups_yaml(repo, "to-remove")
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        registry = load_group_registry(repo)
        assert registry.find("model-project", "to-remove") is None

    def test_noop_when_slug_absent(self, repo: Path) -> None:
        remove_from_groups_yaml(repo, "nonexistent")
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        registry = load_group_registry(repo)
        assert registry is not None


class TestRollbackCascade:
    def test_restores_file(self, tmp_path: Path) -> None:
        repo = tmp_path
        f = repo / "entity.md"
        original = b"original content"
        f.write_bytes(original)
        backups = [(f, original)]
        f.write_bytes(b"modified content")
        rollback_cascade(backups, repo)
        assert f.read_bytes() == original

    def test_deletes_file_when_original_none(self, tmp_path: Path) -> None:
        repo = tmp_path
        f = repo / "newfile.md"
        f.write_text("new")
        backups = [(f, None)]
        rollback_cascade(backups, repo)
        assert not f.exists()

    def test_handles_os_error_gracefully(self, tmp_path: Path) -> None:
        # A path that cannot be written back should not raise
        f = Path("/nonexistent/path/file.md")
        backups = [(f, b"content")]
        rollback_cascade(backups, tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# cascade_delete: scan functions
# ---------------------------------------------------------------------------


class TestScanOwned:
    def test_empty_project_dir(self, repo: Path) -> None:
        entities, conns, ids, paths = _scan_owned(repo / "projects" / "empty" / "model", repo)
        assert entities == []
        assert conns == []
        assert ids == set()
        assert paths == set()

    def test_scans_entity_files(self, repo: Path) -> None:
        proj_dir = repo / "projects" / "mp" / "model"
        proj_dir.mkdir(parents=True)
        f = proj_dir / "ENT@1.abc.md"
        f.write_text(_entity_md("ENT@1.abc", "My Entity"))
        entities, conns, ids, paths = _scan_owned(proj_dir, repo)
        assert len(entities) == 1
        assert entities[0]["id"] == "ENT@1.abc"
        assert "ENT@1.abc" in ids
        assert f in paths

    def test_scans_outgoing_files(self, repo: Path) -> None:
        proj_dir = repo / "projects" / "mp" / "model"
        proj_dir.mkdir(parents=True)
        (proj_dir / "ENT@1.abc.outgoing.md").write_text(_outgoing_md("ENT@1.abc", "ENT@2.def"))
        entities, conns, ids, paths = _scan_owned(proj_dir, repo)
        assert len(conns) == 1
        assert entities == []

    def test_skips_files_without_frontmatter(self, repo: Path) -> None:
        proj_dir = repo / "projects" / "mp" / "model"
        proj_dir.mkdir(parents=True)
        (proj_dir / "README.md").write_text("# No frontmatter\n")
        entities, conns, ids, paths = _scan_owned(proj_dir, repo)
        assert entities == []


class TestScanForeignConnections:
    def test_finds_foreign_connection_targeting_owned_entity(self, repo: Path) -> None:
        owned_id = "ENT@1.owned"
        foreign_id = "ENT@2.foreign"
        # foreign entity with outgoing connection targeting owned
        foreign_proj = repo / "projects" / "foreign" / "model"
        foreign_proj.mkdir(parents=True)
        f = foreign_proj / f"{foreign_id}.outgoing.md"
        f.write_text(_outgoing_md(foreign_id, owned_id))
        foreign_conns = _scan_foreign_connections(repo, {owned_id})
        assert len(foreign_conns) == 1
        assert foreign_conns[0]["target"] == owned_id

    def test_no_foreign_connections_when_no_outgoing_files(self, repo: Path) -> None:
        foreign_conns = _scan_foreign_connections(repo, {"ENT@1.owned"})
        assert foreign_conns == []

    def test_skips_connections_owned_by_project(self, repo: Path) -> None:
        owned_id = "ENT@1.owned"
        proj_dir = repo / "projects" / "mp" / "model"
        proj_dir.mkdir(parents=True)
        f = proj_dir / f"{owned_id}.outgoing.md"
        f.write_text(_outgoing_md(owned_id, "ENT@2.other"))
        # The source is also owned — should be skipped
        foreign_conns = _scan_foreign_connections(repo, {owned_id})
        assert foreign_conns == []


class TestScanForeignDiagrams:
    def test_no_diagrams_when_no_src_root(self, repo: Path) -> None:
        result = _scan_foreign_diagrams(repo, {"ENT@1.x"})
        assert result == []

    def test_finds_diagrams_using_owned_entities(self, repo: Path) -> None:
        owned_id = "ENT@1.owned"
        diag_dir = repo / "diagram-catalog" / "diagrams"
        diag_dir.mkdir(parents=True)
        diag_file = diag_dir / "diag.puml"
        diag_file.write_text(
            f"---\nartifact-id: DIA@1.foo\nname: Foo\nentity-ids-used:\n  - {owned_id}\n---\n@startuml\n@enduml\n"
        )
        result = _scan_foreign_diagrams(repo, {owned_id})
        assert len(result) == 1
        assert owned_id in result[0]["entities_removed"]


class TestScanBlockingDocs:
    def test_no_blocking_when_no_docs_dir(self, repo: Path) -> None:
        result = _scan_blocking_docs(repo, set())
        assert result == []

    def test_finds_blocking_doc(self, repo: Path) -> None:
        entity_path = repo / "projects" / "mp" / "model" / "entity.md"
        entity_path.parent.mkdir(parents=True)
        entity_path.write_text("# entity")
        docs_dir = repo / "docs" / "spec"
        docs_dir.mkdir(parents=True)
        doc = docs_dir / "doc.md"
        doc.write_text(f"[Link]({entity_path})\n")
        result = _scan_blocking_docs(repo, {entity_path})
        assert len(result) == 1


# ---------------------------------------------------------------------------
# cascade_delete_model_project: entry-point
# ---------------------------------------------------------------------------


class TestCascadeDeleteModelProject:
    def test_confirm_mismatch_raises(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-conf", name="MP")
        with pytest.raises(ValueError, match="confirm"):
            cascade_delete_model_project(repo, "mp-conf", "wrong-slug", dry_run=True)

    def test_dry_run_returns_preflight(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-dry", name="MP Dry")
        result = cascade_delete_model_project(repo, "mp-dry", "mp-dry", dry_run=True)
        assert result["dry_run"] is True
        assert result["project"] == "mp-dry"
        assert "owned" in result
        assert "foreign" in result

    def test_dry_run_empty_project_no_owned(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-empty", name="Empty")
        result = cascade_delete_model_project(repo, "mp-empty", "mp-empty", dry_run=True)
        assert result["owned"]["entities"] == []
        assert result["owned"]["connections"] == []
        assert result["apply_blocked_by"] == []

    def test_apply_empty_project(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-apply", name="Apply")
        result = cascade_delete_model_project(repo, "mp-apply", "mp-apply", dry_run=False)
        assert result["dry_run"] is False
        assert result.get("applied") is True

    def test_apply_blocked_when_docs_reference_entities(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-blocked", name="Blocked")
        proj_dir = repo / "projects" / "mp-blocked" / "model"
        proj_dir.mkdir(parents=True)
        entity = proj_dir / "ENT@1.block.md"
        entity.write_text(_entity_md("ENT@1.block", "Blocked Entity"))
        docs_dir = repo / "docs" / "spec"
        docs_dir.mkdir(parents=True)
        doc = docs_dir / "doc.md"
        doc.write_text(f"---\nartifact-id: DOC@1.d\nname: Doc\n---\n[Entity]({entity})\n")
        result = cascade_delete_model_project(repo, "mp-blocked", "mp-blocked", dry_run=False)
        assert result.get("applied") is False
        assert len(result.get("errors", [])) > 0

    def test_apply_with_owned_entities_deletes_them(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="mp-del-ents", name="Del Ents")
        proj_dir = repo / "projects" / "mp-del-ents" / "model"
        proj_dir.mkdir(parents=True)
        entity = proj_dir / "ENT@1.owned.md"
        entity.write_text(_entity_md("ENT@1.owned", "Owned Entity"))
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add entity"], cwd=repo, capture_output=True)
        result = cascade_delete_model_project(repo, "mp-del-ents", "mp-del-ents", dry_run=False)
        assert result.get("applied") is True
        assert result.get("owned_deleted", 0) >= 1


# ---------------------------------------------------------------------------
# _cascade_preflight directly
# ---------------------------------------------------------------------------


class TestCascadePreflight:
    def test_preflight_structure(self, repo: Path) -> None:
        result = _cascade_preflight(repo, "nonexistent-project")
        assert result["dry_run"] is True
        assert "owned" in result
        assert "foreign" in result
        assert "apply_blocked_by" in result

    def test_preflight_finds_owned_entities(self, repo: Path) -> None:
        proj_dir = repo / "projects" / "my-proj" / "model"
        proj_dir.mkdir(parents=True)
        (proj_dir / "ENT@9.abc.md").write_text(_entity_md("ENT@9.abc", "ABC"))
        result = _cascade_preflight(repo, "my-proj")
        assert len(result["owned"]["entities"]) == 1
