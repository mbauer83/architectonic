from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.specialization_declarations import (
    load_specialization_catalog_file,
    load_specialization_catalog_for_repos,
)
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, META_ONTOLOGY_ALIAS, load_archimate_4_module


def _write_specializations(repo_root: Path, body: str) -> None:
    arch_repo = repo_root / ".arch-repo"
    arch_repo.mkdir(parents=True, exist_ok=True)
    (arch_repo / "specializations.yaml").write_text(body, encoding="utf-8")


class TestLoadSpecializationCatalogFile:
    def test_absent_file_returns_empty_catalog(self, tmp_path: Path) -> None:
        assert load_specialization_catalog_file(tmp_path, META_ONTOLOGY_ALIAS).entries == ()

    def test_present_file_parses_catalog(self, tmp_path: Path) -> None:
        _write_specializations(
            tmp_path,
            """
            specializations:
              entity:
                service:
                  - slug: managed-service
                    name: Managed Service
            """,
        )

        catalog = load_specialization_catalog_file(tmp_path, META_ONTOLOGY_ALIAS)

        spec = catalog.get("entity", "service", "managed-service", module_alias=META_ONTOLOGY_ALIAS)
        assert spec is not None
        assert spec.name == "Managed Service"

    def test_invalid_top_level_fails_loudly(self, tmp_path: Path) -> None:
        _write_specializations(tmp_path, "- not\n- a\n- mapping\n")

        with pytest.raises(ValueError, match="top-level YAML value must be a mapping"):
            load_specialization_catalog_file(tmp_path, META_ONTOLOGY_ALIAS)


class TestLoadSpecializationCatalogForRepos:
    def test_enterprise_and_engagement_entries_merge_as_extension(self, tmp_path: Path) -> None:
        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        _write_specializations(
            enterprise_root,
            """
            specializations:
              entity:
                service:
                  - slug: enterprise-managed-service
                    name: Enterprise Managed Service
            """,
        )
        _write_specializations(
            engagement_root,
            """
            specializations:
              entity:
                process:
                  - slug: engagement-process
                    name: Engagement Process
            """,
        )

        repo_catalog = load_specialization_catalog_for_repos(
            META_ONTOLOGY_ALIAS,
            enterprise_root=enterprise_root,
            engagement_root=engagement_root,
        )
        module = load_archimate_4_module(_PACKAGE_DIR, specializations=repo_catalog)
        catalog = module.specialization_catalog

        assert catalog.get("entity", "service", "business-service", module_alias=META_ONTOLOGY_ALIAS) is not None
        assert (
            catalog.get("entity", "service", "enterprise-managed-service", module_alias=META_ONTOLOGY_ALIAS)
            is not None
        )
        assert catalog.get("entity", "process", "engagement-process", module_alias=META_ONTOLOGY_ALIAS) is not None

    def test_app_bootstrap_loads_specializations_from_workspace_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure import app_bootstrap

        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        _write_specializations(
            enterprise_root,
            """
            specializations:
              entity:
                service:
                  - slug: enterprise-managed-service
                    name: Enterprise Managed Service
            """,
        )
        _write_specializations(
            engagement_root,
            """
            specializations:
              connection:
                archimate-flow:
                  - slug: engagement-flow
                    name: Engagement Flow
            """,
        )
        monkeypatch.setattr(
            app_bootstrap,
            "resolve_workspace_repo_roots",
            lambda: (engagement_root, enterprise_root),
        )

        catalog = app_bootstrap._load_archimate_specializations()

        assert (
            catalog.get("entity", "service", "enterprise-managed-service", module_alias=META_ONTOLOGY_ALIAS)
            is not None
        )
        assert (
            catalog.get("connection", "archimate-flow", "engagement-flow", module_alias=META_ONTOLOGY_ALIAS)
            is not None
        )

    def test_duplicate_between_tiers_is_rejected(self, tmp_path: Path) -> None:
        enterprise_root = tmp_path / "enterprise"
        engagement_root = tmp_path / "engagement"
        body = """
            specializations:
              entity:
                service:
                  - slug: managed-service
                    name: Managed Service
            """
        _write_specializations(enterprise_root, body)
        _write_specializations(engagement_root, body)

        with pytest.raises(ValueError, match="Duplicate specialization"):
            load_specialization_catalog_for_repos(
                META_ONTOLOGY_ALIAS,
                enterprise_root=enterprise_root,
                engagement_root=engagement_root,
            )
