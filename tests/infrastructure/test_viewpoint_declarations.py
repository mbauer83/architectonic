from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.viewpoint_declarations import (
    load_module_viewpoint_catalog,
    load_viewpoint_catalog_file,
    load_viewpoint_catalog_for_repos,
    write_viewpoint_catalog_file,
)


def _write_viewpoints(repo_root: Path, body: str) -> None:
    arch_repo = repo_root / ".arch-repo"
    arch_repo.mkdir(parents=True, exist_ok=True)
    (arch_repo / "viewpoints.yaml").write_text(body, encoding="utf-8")


class TestLoadViewpointCatalogFile:
    def test_absent_file_returns_empty_catalog(self, tmp_path: Path) -> None:
        assert load_viewpoint_catalog_file(tmp_path).entries == ()

    def test_present_file_parses_catalog(self, tmp_path: Path) -> None:
        _write_viewpoints(
            tmp_path,
            """
            viewpoints:
              - slug: custom
                version: 1
                name: Custom
            """,
        )
        catalog = load_viewpoint_catalog_file(tmp_path)
        definition = catalog.get("custom")
        assert definition is not None
        assert definition.name == "Custom"

    def test_invalid_top_level_fails_loudly(self, tmp_path: Path) -> None:
        _write_viewpoints(tmp_path, "- not\n- a\n- mapping\n")
        with pytest.raises(ValueError, match="top-level YAML value must be a mapping"):
            load_viewpoint_catalog_file(tmp_path)


class TestLoadViewpointCatalogForRepos:
    def test_enterprise_and_engagement_entries_merge(self, tmp_path: Path) -> None:
        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        _write_viewpoints(
            enterprise_root, "viewpoints:\n  - slug: enterprise-vp\n    version: 1\n    name: Enterprise VP\n"
        )
        _write_viewpoints(
            engagement_root, "viewpoints:\n  - slug: engagement-vp\n    version: 1\n    name: Engagement VP\n"
        )

        catalog = load_viewpoint_catalog_for_repos(enterprise_root=enterprise_root, engagement_root=engagement_root)

        assert catalog.get("enterprise-vp") is not None
        assert catalog.get("engagement-vp") is not None

    def test_duplicate_between_tiers_is_rejected(self, tmp_path: Path) -> None:
        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        body = "viewpoints:\n  - slug: shared-vp\n    version: 1\n    name: Shared VP\n"
        _write_viewpoints(enterprise_root, body)
        _write_viewpoints(engagement_root, body)

        with pytest.raises(ValueError, match="Duplicate viewpoint slug"):
            load_viewpoint_catalog_for_repos(enterprise_root=enterprise_root, engagement_root=engagement_root)

    def test_app_bootstrap_loads_viewpoints_from_workspace_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure import app_bootstrap

        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        _write_viewpoints(
            enterprise_root, "viewpoints:\n  - slug: enterprise-vp\n    version: 1\n    name: Enterprise VP\n"
        )
        monkeypatch.setattr(
            app_bootstrap,
            "resolve_workspace_repo_roots",
            lambda: (engagement_root, enterprise_root),
        )

        catalog = app_bootstrap._load_viewpoints()

        assert catalog.get("enterprise-vp") is not None
        # The module-shipped starter library is always merged in alongside repo overrides.
        assert catalog.get("motivation") is not None


class TestLoadModuleViewpointCatalog:
    def test_loads_archimate_starter_library(self) -> None:
        from src.ontologies.archimate_4._loader import _PACKAGE_DIR

        catalog = load_module_viewpoint_catalog(_PACKAGE_DIR)
        assert catalog.get("motivation") is not None
        assert catalog.get("application-structure") is not None
        assert catalog.get("layered") is not None
        assert catalog.get("technology-usage") is not None

    def test_absent_file_returns_empty_catalog(self, tmp_path: Path) -> None:
        assert load_module_viewpoint_catalog(tmp_path).entries == ()


class TestWriteViewpointCatalogFile:
    def test_write_then_load_round_trips(self, tmp_path: Path) -> None:
        _write_viewpoints(tmp_path, "viewpoints:\n  - slug: original\n    version: 1\n    name: Original\n")
        catalog = load_viewpoint_catalog_file(tmp_path)

        write_viewpoint_catalog_file(tmp_path, catalog)
        reloaded = load_viewpoint_catalog_file(tmp_path)

        definition = reloaded.get("original")
        assert definition is not None
        assert definition.name == "Original"

    def test_write_creates_arch_repo_directory(self, tmp_path: Path) -> None:
        from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition

        catalog = ViewpointCatalog((ViewpointDefinition(slug="fresh", version=1, name="Fresh"),))
        write_viewpoint_catalog_file(tmp_path, catalog)

        assert (tmp_path / ".arch-repo" / "viewpoints.yaml").exists()
        assert load_viewpoint_catalog_file(tmp_path).get("fresh") is not None
