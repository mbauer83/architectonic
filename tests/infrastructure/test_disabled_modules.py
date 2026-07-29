"""Integration coverage for runtime-disabled ontology modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers.modules import list_modules
from src.infrastructure.write.artifact_write.entity import create_entity


def _clear_runtime_registry_caches() -> None:
    from src.infrastructure import app_bootstrap
    from src.infrastructure.write.artifact_write import type_guidance

    app_bootstrap.get_module_registry.cache_clear()
    type_guidance._registry.cache_clear()


def _patch_sysml_disabled_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.config.settings.load_settings",
        lambda: {
            "modules": {"sysml_v2_min": {"enabled": False}},
            "validation": {"datatype_type_references_blocking": True},
        },
    )


def _sysml_entity(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
---
artifact-id: PDF@1783400000.AbCdEf.disabled-sysml
artifact-type: part-definition
name: Disabled SysML Entity
version: 0.1.0
status: draft
last-updated: '2026-07-07'
---

<!-- §content -->

## Disabled SysML Entity

<!-- §display -->

### sysml

```yaml
label: Disabled SysML Entity
alias: PDF_AbCdEf
```
""",
        encoding="utf-8",
    )


def test_settings_yaml_disables_sysml_v2_min() -> None:
    from src.config.settings import module_overrides

    assert module_overrides().get("sysml_v2_min") == {"enabled": False}


def test_sysml_v2_min_disabled_at_runtime_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.mcp.artifact_mcp.write.entity import artifact_authoring_guidance

    _patch_sysml_disabled_settings(monkeypatch)
    _clear_runtime_registry_caches()

    try:
        repo = tmp_path / "architecture-repository"
        registry = build_module_registry()
        catalogs = build_runtime_catalogs(registry)

        assert registry.find_ontology("sysml_v2_min") is None
        assert "part-definition" not in {str(t) for t in registry.all_entity_types()}

        module_names = {str(entry["name"]) for entry in list_modules(catalogs=catalogs)}
        assert "sysml_v2_min" not in module_names

        guidance = artifact_authoring_guidance(filter=["part-definition"])
        assert "error" in guidance
        assert guidance["unknown"] == ["part-definition"]

        entity_path = repo / "model" / "sysml" / "part-definition" / "PDF@1783400000.AbCdEf.disabled-sysml.md"
        _sysml_entity(entity_path)
        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=catalogs)
        result = verifier.verify_entity_file(entity_path)
        assert any(
            issue.code == "E102" and "not a recognised entity type" in issue.message for issue in result.issues
        )

        with pytest.raises(ValueError, match="Unknown entity artifact_type: 'part-definition'"):
            create_entity(
                repo_root=repo,
                verifier=verifier,
                clear_repo_caches=lambda _: None,
                artifact_type="part-definition",
                name="Disabled SysML Entity",
                summary=None,
                properties=None,
                notes=None,
                artifact_id=None,
                version="0.1.0",
                status="draft",
                last_updated="2026-07-07",
                dry_run=True,
            )
    finally:
        _clear_runtime_registry_caches()


def test_registered_meta_ontology_values_follow_active_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.app_bootstrap import registered_meta_ontology_values

    _patch_sysml_disabled_settings(monkeypatch)
    _clear_runtime_registry_caches()

    try:
        active_registry = build_module_registry()
        full_registry = build_module_registry(complete_vocabulary=True)

        assert registered_meta_ontology_values(active_registry) == frozenset({"archimate-4"})
        assert registered_meta_ontology_values(full_registry) == frozenset({"archimate-4", "sysml-v2"})
    finally:
        _clear_runtime_registry_caches()


def test_resolve_meta_ontology_module_returns_the_backing_ontology() -> None:
    from src.infrastructure.app_bootstrap import resolve_meta_ontology_module

    registry = build_module_registry()
    module = resolve_meta_ontology_module("archimate-4", registry)

    assert module is not None
    assert module.name == "archimate-4-0"
    assert "stakeholder" in module.entity_types


def test_resolve_meta_ontology_module_returns_none_for_unknown_alias() -> None:
    from src.infrastructure.app_bootstrap import resolve_meta_ontology_module

    registry = build_module_registry()
    assert resolve_meta_ontology_module("no-such-alias", registry) is None


def test_resolve_meta_ontology_module_falls_back_to_literal_module_name() -> None:
    """"assurance" is not in _META_ONTOLOGY_ALIASES (it isn't a selectable architecture-
    framework meta-ontology), but it can still carry its own guidance, so the alias must
    resolve directly against the registered module name."""
    from src.infrastructure.app_bootstrap import resolve_meta_ontology_module

    registry = build_module_registry(complete_vocabulary=True)
    module = resolve_meta_ontology_module("assurance", registry)

    assert module is not None
    assert module.name == "assurance"


def test_resolve_meta_ontology_module_returns_none_when_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.app_bootstrap import resolve_meta_ontology_module

    _patch_sysml_disabled_settings(monkeypatch)
    _clear_runtime_registry_caches()

    try:
        active_registry = build_module_registry()
        assert resolve_meta_ontology_module("sysml-v2", active_registry) is None
    finally:
        _clear_runtime_registry_caches()


def test_c4_manifest_tolerates_disabled_sysml_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.diagram_types.c4._projection import MANIFEST

    _patch_sysml_disabled_settings(monkeypatch)
    _clear_runtime_registry_caches()

    try:
        registry = build_module_registry()
        assert registry.find_ontology("sysml_v2_min") is None
        assert registry.find_diagram_type("c4-container") is not None
        assert "sysml_v2_min" in MANIFEST.compatible_ontologies
    finally:
        _clear_runtime_registry_caches()
