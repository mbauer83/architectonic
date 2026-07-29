"""Tests for _promote_groups.py: group-mapping helpers for promotion workflow.

Covers: GroupMappingEntry construction, remap_entity_rel, update_enterprise_groups.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write._promote_groups import (
    GroupMappingEntry,
    compute_group_mapping,
    remap_entity_rel,
    update_enterprise_groups,
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
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# GroupMappingEntry
# ---------------------------------------------------------------------------


class _StubRegistry:
    def __init__(self, paths: dict[str, Path]) -> None:
        self._paths = paths

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return self._paths.get(artifact_id)


class TestComputeGroupMapping:
    """Regression coverage for the engagement-qualified default enterprise slug.

    Root scenario: two engagements independently name a model-project group
    "assurance". Without qualification, promoting both would collide on the
    bare slug in the shared enterprise namespace. compute_group_mapping's
    "new" branch now defaults to "{engagement-label}-{slug}" instead.
    """

    def test_new_group_gets_engagement_qualified_default_slug(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        entity_path = engagement_root / "projects" / "assurance" / "model" / "requirement" / "REQ@1.a.x.md"
        entity_path.parent.mkdir(parents=True)
        entity_path.write_text("---\nartifact-id: REQ@1.a.x\n---\n", encoding="utf-8")
        registry = _StubRegistry({"REQ@1.a.x": entity_path})

        mapping, _ = compute_group_mapping(["REQ@1.a.x"], registry, engagement_root, enterprise_root)

        assert len(mapping) == 1
        entry = mapping[0]
        assert entry.match_status == "new"
        assert entry.engagement_slug == "assurance"
        assert entry.enterprise_slug == "eng-t-assurance"
        assert entry.enterprise_group_id is None

    def test_uncategorized_stays_unqualified(self, engagement_root: Path, enterprise_root: Path) -> None:
        entity_path = engagement_root / "model" / "requirement" / "REQ@1.a.y.md"
        entity_path.parent.mkdir(parents=True)
        entity_path.write_text("---\nartifact-id: REQ@1.a.y\n---\n", encoding="utf-8")
        registry = _StubRegistry({"REQ@1.a.y": entity_path})

        mapping, _ = compute_group_mapping(["REQ@1.a.y"], registry, engagement_root, enterprise_root)

        assert len(mapping) == 1
        assert mapping[0].enterprise_slug == "uncategorized"

    def test_matched_by_id_is_not_requalified(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.application.group_registry import registry_to_yaml
        from src.domain.repository.groups import GroupEntry, GroupRegistry
        from src.domain.repository.repo_layout import ARCH_REPO

        shared_id = "GRP@1.shared"
        registry = GroupRegistry(model_projects=(GroupEntry(slug="assurance", id=shared_id, name="Assurance"),))
        for root in (engagement_root, enterprise_root):
            groups_dir = root / ARCH_REPO
            groups_dir.mkdir(parents=True, exist_ok=True)
            (groups_dir / "groups.yaml").write_text(registry_to_yaml(registry), encoding="utf-8")
        entity_path = engagement_root / "projects" / "assurance" / "model" / "requirement" / "REQ@1.a.z.md"
        entity_path.parent.mkdir(parents=True)
        entity_path.write_text("---\nartifact-id: REQ@1.a.z\n---\n", encoding="utf-8")
        registry = _StubRegistry({"REQ@1.a.z": entity_path})

        mapping, _ = compute_group_mapping(["REQ@1.a.z"], registry, engagement_root, enterprise_root)

        assert len(mapping) == 1
        assert mapping[0].match_status == "matched_by_id"
        assert mapping[0].enterprise_slug == "assurance"


class TestGroupMappingEntry:
    def test_construction_matched_by_id(self) -> None:
        entry = GroupMappingEntry(
            engagement_slug="proj-a",
            engagement_group_id="GRP@1.abc",
            match_status="matched_by_id",
            enterprise_slug="proj-a",
            enterprise_group_id="GRP@1.abc",
        )
        assert entry.engagement_slug == "proj-a"
        assert entry.match_status == "matched_by_id"
        assert entry.enterprise_group_id == "GRP@1.abc"

    def test_construction_new_entry(self) -> None:
        entry = GroupMappingEntry(
            engagement_slug="new-proj",
            engagement_group_id="GRP@2.xyz",
            match_status="new",
            enterprise_slug="new-proj",
            enterprise_group_id=None,
        )
        assert entry.match_status == "new"
        assert entry.enterprise_group_id is None

    def test_construction_conflict(self) -> None:
        entry = GroupMappingEntry(
            engagement_slug="conflict-proj",
            engagement_group_id="GRP@3.abc",
            match_status="conflict",
            enterprise_slug="conflict-proj",
            enterprise_group_id="GRP@99.xyz",
        )
        assert entry.match_status == "conflict"


# ---------------------------------------------------------------------------
# remap_entity_rel
# ---------------------------------------------------------------------------


class TestRemapEntityRel:
    def test_remaps_project_path(self) -> None:
        rel = Path("projects/old-slug/model/entity.md")
        result = remap_entity_rel(rel, {"old-slug": "new-slug"})
        assert result == Path("projects/new-slug/model/entity.md")

    def test_no_remap_when_not_in_projects(self) -> None:
        rel = Path("model/some/entity.md")
        result = remap_entity_rel(rel, {"model": "other"})
        assert result == rel

    def test_no_remap_when_slug_not_in_map(self) -> None:
        rel = Path("projects/other-slug/model/entity.md")
        result = remap_entity_rel(rel, {"different-slug": "new-slug"})
        assert result == rel

    def test_no_remap_when_path_too_short(self) -> None:
        rel = Path("projects")
        result = remap_entity_rel(rel, {"projects": "other"})
        assert result == rel

    def test_remap_preserves_deep_path(self) -> None:
        rel = Path("projects/src-slug/model/Motivation/capability/ENT@1.abc.md")
        result = remap_entity_rel(rel, {"src-slug": "dst-slug"})
        assert result == Path("projects/dst-slug/model/Motivation/capability/ENT@1.abc.md")

    def test_empty_remap_dict_returns_unchanged(self) -> None:
        rel = Path("projects/proj/model/entity.md")
        result = remap_entity_rel(rel, {})
        assert result == rel


# ---------------------------------------------------------------------------
# update_enterprise_groups
# ---------------------------------------------------------------------------


class TestUpdateEnterpriseGroups:
    def test_adds_new_group_to_enterprise(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(engagement_root, axis="model-project", slug="new-proj", name="New Project")
        entry = GroupMappingEntry(
            engagement_slug="new-proj",
            engagement_group_id="GRP@1.newproj",
            match_status="new",
            enterprise_slug="new-proj",
            enterprise_group_id=None,
        )
        update_enterprise_groups(enterprise_root, engagement_root, [entry], {})
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        ent_reg = load_group_registry(enterprise_root)
        result = ent_reg.find("model-project", "new-proj")
        assert result is not None
        assert result.name == "New Project"

    def test_preserves_existing_enterprise_group(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(enterprise_root, axis="model-project", slug="existing", name="Existing")
        entry = GroupMappingEntry(
            engagement_slug="existing",
            engagement_group_id="GRP@1.ex",
            match_status="matched_by_id",
            enterprise_slug="existing",
            enterprise_group_id="GRP@1.ex",
        )
        update_enterprise_groups(enterprise_root, engagement_root, [entry], {})
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        ent_reg = load_group_registry(enterprise_root)
        existing = [e for e in ent_reg.model_projects if e.slug == "existing"]
        assert len(existing) == 1

    def test_noop_when_all_groups_exist(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(enterprise_root, axis="model-project", slug="already-there", name="Already")
        entry = GroupMappingEntry(
            engagement_slug="already-there",
            engagement_group_id="GRP@5.at",
            match_status="conflict",
            enterprise_slug="already-there",
            enterprise_group_id="GRP@99.at",
        )
        update_enterprise_groups(enterprise_root, engagement_root, [entry], {})
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        ent_reg = load_group_registry(enterprise_root)
        matches = [e for e in ent_reg.model_projects if e.slug == "already-there"]
        assert len(matches) == 1

    def test_resolution_remaps_slug(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(engagement_root, axis="model-project", slug="eng-slug", name="Eng Proj")
        entry = GroupMappingEntry(
            engagement_slug="eng-slug",
            engagement_group_id="GRP@6.es",
            match_status="new",
            enterprise_slug="eng-slug",
            enterprise_group_id=None,
        )
        update_enterprise_groups(enterprise_root, engagement_root, [entry], {"eng-slug": "ent-slug"})
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        ent_reg = load_group_registry(enterprise_root)
        assert ent_reg.find("model-project", "ent-slug") is not None
        assert ent_reg.find("model-project", "eng-slug") is None

    def test_empty_mapping_is_noop(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        update_enterprise_groups(enterprise_root, engagement_root, [], {})
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        ent_reg = load_group_registry(enterprise_root)
        assert ent_reg is not None
