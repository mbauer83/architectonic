"""Load and persist viewpoint declarations: module-shipped starter library + repo-local
``.arch-repo/viewpoints.yaml`` (two-tier, enterprise/engagement — like specializations).

The write side (``write_viewpoint_catalog_file``) is the primitive a GUI save flow or an
MCP tool uses to persist an authored/edited definition — this file is not a static,
hand-edited-only artifact.

Only structural parsing runs here (``viewpoint_catalog_from_mapping`` — enum values and the
query_schema tag). Registry-aware validation (unknown types/specializations/strategies/
attributes — ``viewpoint_validation.validate_viewpoint_definition``) needs the fully-built
runtime catalogs and is invoked by the caller once those are available, not by this loader.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_catalog_to_mapping
from src.domain.viewpoints.viewpoints import ViewpointCatalog

if TYPE_CHECKING:
    from src.application.runtime_catalogs import RuntimeCatalogs

VIEWPOINTS_FILENAME = "viewpoints.yaml"


def viewpoint_declarations_path(repo_root: Path) -> Path:
    return repo_root / ".arch-repo" / VIEWPOINTS_FILENAME


def _load_viewpoint_catalog(path: Path) -> ViewpointCatalog:
    if not path.exists():
        return ViewpointCatalog.empty()
    try:
        loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid viewpoint declarations in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid viewpoint declarations in {path}: top-level YAML value must be a mapping")
    return viewpoint_catalog_from_mapping(loaded)


def load_viewpoint_catalog_file(repo_root: Path) -> ViewpointCatalog:
    return _load_viewpoint_catalog(viewpoint_declarations_path(repo_root))


def load_module_viewpoint_catalog(package_dir: Path) -> ViewpointCatalog:
    """Load the module-shipped starter library (e.g. ``archimate_4/viewpoints.yaml``)."""
    return _load_viewpoint_catalog(package_dir / VIEWPOINTS_FILENAME)


def load_viewpoint_catalog_for_repos(
    *,
    enterprise_root: Path | None,
    engagement_root: Path | None,
) -> ViewpointCatalog:
    enterprise = ViewpointCatalog.empty()
    if enterprise_root is not None:
        enterprise = load_viewpoint_catalog_file(enterprise_root)
    engagement = ViewpointCatalog.empty()
    if engagement_root is not None:
        engagement = load_viewpoint_catalog_file(engagement_root)
    return enterprise | engagement


def load_effective_viewpoint_catalog(roots: Sequence[Path]) -> ViewpointCatalog:
    """Module-shipped starter library merged with whichever repo roots the caller resolved
    (an MCP request's ``repo_scope``/``repo_root``) — mirrors ``app_bootstrap._load_viewpoints``'s
    module-⊕-repo-tier merge, but scoped to the caller's own roots instead of the fixed
    workspace roots, so per-request repo selection and the merged viewpoint catalog can
    never disagree (WU-E6a/E7a: the write tool's slug-uniqueness/read-only checks and the
    read tool's ``list``/``execute`` must see the same catalog a given ``repo_root`` implies).
    """
    from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCH_PACKAGE_DIR  # noqa: PLC0415

    module_catalog = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR)
    repo_catalog = ViewpointCatalog.empty()
    for root in roots:
        repo_catalog = repo_catalog | load_viewpoint_catalog_file(root)
    return module_catalog | repo_catalog


def with_effective_viewpoints(catalogs: "RuntimeCatalogs", roots: Sequence[Path]) -> "RuntimeCatalogs":
    """``catalogs`` with only its viewpoint catalog reloaded for ``roots``.

    The other catalogs — module registry, ontology, specializations — are expensive to rebuild and
    change only when code or a module does, which a restart is the right moment for. A viewpoint
    definition is ordinary repository data a user may have written seconds ago, and every surface
    that resolves a slug has to see it.

    One function because both surfaces need the same answer and had different ones. Reads went
    through a request-scoped dependency that did this; writes took ``process_runtime_catalogs()``,
    whose viewpoint catalog is the module-shipped starter library and nothing else. So a diagram or
    matrix applying a repo-authored viewpoint failed verification with ``E180 Unknown viewpoint
    slug`` — not merely until a restart, but always, because the process catalog never reads a repo.
    """
    from dataclasses import replace  # noqa: PLC0415

    return replace(catalogs, viewpoints=load_effective_viewpoint_catalog(roots))


def write_viewpoint_catalog_file(repo_root: Path, catalog: ViewpointCatalog) -> None:
    """Persist one repo's viewpoint definitions, overwriting its ``viewpoints.yaml``.

    Used by an authoring surface (GUI save flow or MCP tool) that already holds the
    complete, validated catalog for that repo — not a partial merge or append.
    """
    path = viewpoint_declarations_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = str(yaml.safe_dump(viewpoint_catalog_to_mapping(catalog), sort_keys=False))
    path.write_text(text, encoding="utf-8")
