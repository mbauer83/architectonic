"""Tests for the analysis-collection (4th) grouping axis."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.group_registry import load_group_registry, registry_to_yaml
from src.domain.repository.groups import GroupAxis, GroupEntry, GroupRegistry


def test_groupaxis_includes_analysis_collection() -> None:
    from typing import get_args

    axes = get_args(GroupAxis)
    assert "analysis-collection" in axes


def test_group_registry_has_analysis_collections_field() -> None:
    reg = GroupRegistry()
    assert hasattr(reg, "analysis_collections")
    assert isinstance(reg.analysis_collections, tuple)


def test_list_axis_analysis_collection() -> None:
    entry = GroupEntry(slug="stpa-vehicle", id="GRP@1.abc", name="STPA Vehicle Analysis")
    reg = GroupRegistry(analysis_collections=(entry,))
    result = reg.list_axis("analysis-collection")
    assert len(result) == 1
    assert result[0].slug == "stpa-vehicle"


def test_find_analysis_collection() -> None:
    entry = GroupEntry(slug="stpa-vehicle", id="GRP@1.abc", name="STPA Vehicle Analysis")
    reg = GroupRegistry(analysis_collections=(entry,))
    found = reg.find("analysis-collection", "stpa-vehicle")
    assert found is not None
    assert found.id == "GRP@1.abc"


def test_registry_to_yaml_includes_analysis_collections() -> None:
    entry = GroupEntry(slug="stpa-vehicle", id="GRP@1.abc", name="STPA Vehicle Analysis")
    reg = GroupRegistry(analysis_collections=(entry,))
    dumped = registry_to_yaml(reg)
    data = yaml.safe_load(dumped)
    assert "analysis-collections" in data
    assert data["analysis-collections"][0]["slug"] == "stpa-vehicle"


def test_load_group_registry_analysis_collections(tmp_path: Path) -> None:

    arch_repo = tmp_path / ".arch-repo"
    arch_repo.mkdir()
    groups_yaml = arch_repo / "groups.yaml"
    groups_yaml.write_text(
        "analysis-collections:\n"
        "  - slug: stpa-critical\n"
        "    id: GRP@9.xyz\n"
        "    name: STPA Critical Systems\n"
    )
    reg = load_group_registry(tmp_path)
    ac = reg.list_axis("analysis-collection")
    slugs = [e.slug for e in ac]
    assert "stpa-critical" in slugs


def test_load_group_registry_uncategorized_synthesis(tmp_path: Path) -> None:
    """analysis-collection always has an uncategorized entry."""

    reg = load_group_registry(tmp_path)
    ac = reg.list_axis("analysis-collection")
    slugs = [e.slug for e in ac]
    assert "uncategorized" in slugs
