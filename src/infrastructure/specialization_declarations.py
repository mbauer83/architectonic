"""Load repo-local specialization declarations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    specialization_catalog_from_mapping,
)

SPECIALIZATIONS_FILENAME = "specializations.yaml"


def specialization_declarations_path(repo_root: Path) -> Path:
    return repo_root / ".arch-repo" / SPECIALIZATIONS_FILENAME


def load_specialization_catalog_file(repo_root: Path, module_alias: str) -> SpecializationCatalog:
    path = specialization_declarations_path(repo_root)
    if not path.exists():
        return SpecializationCatalog.empty()
    try:
        loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid specialization declarations in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid specialization declarations in {path}: top-level YAML value must be a mapping")
    return specialization_catalog_from_mapping(cast(dict[str, Any], loaded), module_alias=module_alias)


def load_specialization_catalog_for_repos(
    module_alias: str,
    *,
    enterprise_root: Path | None,
    engagement_root: Path | None,
) -> SpecializationCatalog:
    enterprise = SpecializationCatalog.empty()
    if enterprise_root is not None:
        enterprise = load_specialization_catalog_file(enterprise_root, module_alias)
    engagement = SpecializationCatalog.empty()
    if engagement_root is not None:
        engagement = load_specialization_catalog_file(engagement_root, module_alias)
    return enterprise | engagement
