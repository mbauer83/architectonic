"""Impure shell for the deployment-layout resolver.

Gathers CLI selectors, the process environment, and the selected settings
document, then delegates to the pure two-stage resolver. Runtime bootstrap,
Docker startup, and `arch-repair upgrade` all resolve through this one shell,
so they open byte-identical canonical paths from one manifest.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.domain.deployment.layout import (
    CliSelectors,
    DeploymentManifest,
    SettingsDocumentSelection,
    SettingsValues,
)
from src.domain.deployment.layout_resolution import (
    LayoutInputs,
    resolve_deployment_layout,
    select_settings_document,
)


def source_tree_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _canonicalize(path: Path) -> Path:
    return path.expanduser().resolve()


def _section(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    raw = data.get(key)
    return raw if isinstance(raw, dict) else {}


def _optional_str(section: Mapping[str, object], key: str) -> str | None:
    value = section.get(key)
    return value if isinstance(value, str) and value else None


def load_settings_values(document: Path) -> SettingsValues:
    """Parse the layout-relevant values out of one settings document."""
    if not document.exists():
        return SettingsValues()
    data_raw: object = yaml.safe_load(document.read_text(encoding="utf-8")) or {}
    data: Mapping[str, object] = data_raw if isinstance(data_raw, dict) else {}
    deployment = _section(data, "deployment")
    archive_section = _section(deployment, "archive")
    storage_assurance = _section(_section(data, "storage"), "assurance")
    modules_assurance = _section(_section(data, "modules"), "assurance")
    enabled_raw = modules_assurance.get("enabled")
    return SettingsValues(
        deployment_workspace_root=_optional_str(deployment, "workspace_root"),
        deployment_assurance_db_path=_optional_str(deployment, "assurance_db_path"),
        deployment_signals_db_path=_optional_str(deployment, "signals_db_path"),
        deployment_guidance_cache_root=_optional_str(deployment, "guidance_cache_root"),
        store_backend=str(storage_assurance.get("store_backend", "sqlcipher")),
        signals_backend=str(storage_assurance.get("signals_backend", "sqlcipher-colocated")),
        archive_backend=str(storage_assurance.get("archive_backend", "standard")),
        assurance_enabled=bool(enabled_raw) if isinstance(enabled_raw, bool) else True,
        archive={k: str(v) for k, v in archive_section.items() if isinstance(v, (str, int))},
    )


def resolve_settings_selection(
    cli: CliSelectors, env: Mapping[str, str] | None = None
) -> SettingsDocumentSelection:
    """Stage 1 with production canonicalization (symlinks resolved)."""
    environment = os.environ if env is None else env
    deployment_root = (
        _canonicalize(Path(cli.deployment_root)) if cli.deployment_root is not None else None
    )
    return select_settings_document(
        cli_settings=cli.settings,
        deployment_root=deployment_root,
        env=environment,
        source_tree_settings=source_tree_root() / "config" / "settings.yaml",
        cwd=Path.cwd(),
        canonicalize=_canonicalize,
    )


def resolve_manifest(
    cli: CliSelectors | None = None, env: Mapping[str, str] | None = None
) -> DeploymentManifest:
    """The one manifest runtime, Docker, and upgrade discovery share."""
    selectors = cli if cli is not None else CliSelectors()
    environment = os.environ if env is None else env
    selection = resolve_settings_selection(selectors, environment)
    deployment_root = (
        _canonicalize(Path(selectors.deployment_root))
        if selectors.deployment_root is not None
        else None
    )
    inputs = LayoutInputs(
        cli=selectors,
        env=environment,
        settings=load_settings_values(selection.path),
        settings_dir=selection.path.parent,
        deployment_root=deployment_root,
        source_tree_root=source_tree_root(),
        home=Path.home(),
        cwd=Path.cwd(),
        canonicalize=_canonicalize,
    )
    return resolve_deployment_layout(inputs, selection)
