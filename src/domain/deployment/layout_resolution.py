"""The two-stage deployment-layout resolver (pure).

Stage 1 selects the governing settings document (first hit wins, exact order).
Stage 2 resolves every operational path from the normative source table: explicit
sources (CLI, settings key, env) must agree — differing canonical values are a
`DeploymentLayoutConflict` — and defaults never conflict with explicit values.

Canonicalization is injected so infrastructure can resolve symlinks while unit
tests stay filesystem-independent (lexical normalization by default).
"""

from __future__ import annotations

import os.path
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from src.domain.deployment.layout import (
    ASSURANCE_DIRNAME,
    ASSURANCE_STORE_FILENAME,
    ENV_ASSURANCE_DB_PATH,
    ENV_SETTINGS_PATH,
    ENV_SIGNALS_DB_PATH,
    GUIDANCE_CACHE_DIRNAME,
    SIGNALS_DB_FILENAME,
    ArchiveIdentity,
    CliSelectors,
    DeploymentLayoutConflict,
    DeploymentManifest,
    FieldSource,
    ProvenanceEntry,
    ResolvedPathField,
    SettingsDocumentSelection,
    SettingsValues,
)

Canonicalize = Callable[[Path], Path]


def lexical_canonicalize(path: Path) -> Path:
    """Absolute + normalized, without touching the filesystem (test default)."""
    return Path(os.path.normpath(path)) if path.is_absolute() else Path(os.path.normpath(path.absolute()))


@dataclass(frozen=True)
class LayoutInputs:
    """Everything stage 2 needs, gathered by the impure shell."""

    cli: CliSelectors
    env: Mapping[str, str]
    settings: SettingsValues
    settings_dir: Path
    deployment_root: Path | None
    source_tree_root: Path
    home: Path
    cwd: Path
    canonicalize: Canonicalize = lexical_canonicalize


def select_settings_document(
    *,
    cli_settings: str | None,
    deployment_root: Path | None,
    env: Mapping[str, str],
    source_tree_settings: Path,
    cwd: Path,
    canonicalize: Canonicalize = lexical_canonicalize,
) -> SettingsDocumentSelection:
    """Stage 1 — exact order, first hit wins."""
    if cli_settings is not None:
        return SettingsDocumentSelection(canonicalize(cwd / cli_settings), "cli")
    if deployment_root is not None:
        return SettingsDocumentSelection(canonicalize(deployment_root / "settings.yaml"), "deployment_root_default")
    env_path = env.get(ENV_SETTINGS_PATH)
    if env_path:
        return SettingsDocumentSelection(canonicalize(cwd / Path(env_path).expanduser()), "env")
    return SettingsDocumentSelection(canonicalize(source_tree_settings), "source_tree_default")


def _canonical(inputs: LayoutInputs, base: Path, raw: str) -> Path:
    expanded = Path(raw).expanduser()
    return inputs.canonicalize(expanded if expanded.is_absolute() else base / expanded)


def _resolve_field(
    inputs: LayoutInputs,
    field_name: str,
    *,
    cli_value: str | None,
    settings_value: str | None,
    env_key: str | None,
    deployment_root_default: Path | None,
    compat_default: Path | None,
) -> ResolvedPathField | None:
    """One row of the normative source table.

    Explicit bases: CLI values resolve against the CWD, settings values against
    the settings directory, env values against the CWD.
    """
    env_value = inputs.env.get(env_key) if env_key else None
    explicit: list[tuple[FieldSource, str, Path]] = []
    if cli_value is not None:
        explicit.append(("cli", cli_value, inputs.cwd))
    if settings_value is not None:
        explicit.append(("settings", settings_value, inputs.settings_dir))
    if env_value:
        explicit.append(("env", env_value, inputs.cwd))

    if explicit:
        canonical = [(source, raw, _canonical(inputs, base, raw)) for source, raw, base in explicit]
        distinct = {str(path) for _, _, path in canonical}
        if len(distinct) > 1:
            raise DeploymentLayoutConflict(field_name, tuple((s, raw) for s, raw, _ in canonical))
        winner_source, _, winner_path = canonical[0]
        provenance = tuple(ProvenanceEntry(source, raw) for source, raw, _ in canonical)
        return ResolvedPathField(winner_path, winner_source, provenance)

    if inputs.deployment_root is not None and deployment_root_default is not None:
        path = inputs.canonicalize(deployment_root_default)
        provenance = ProvenanceEntry("deployment_root_default", str(path))
        return ResolvedPathField(path, "deployment_root_default", (provenance,))
    if compat_default is not None:
        path = inputs.canonicalize(compat_default)
        return ResolvedPathField(path, "compat_default", (ProvenanceEntry("compat_default", str(path)),))
    return None


def _archive_identity(inputs: LayoutInputs) -> tuple[ArchiveIdentity | None, tuple[str, ...]]:
    backend = inputs.settings.archive_backend
    settings_archive = inputs.settings.archive

    def value(settings_key: str, env_key: str, default: str = "") -> tuple[str, FieldSource]:
        from_settings = settings_archive.get(settings_key)
        if from_settings:
            return from_settings, "settings"
        from_env = inputs.env.get(env_key, "")
        return (from_env, "env") if from_env else (default, "compat_default")

    if backend == "s3-worm":
        bucket, bucket_source = value("s3_bucket", "ARCH_S3_BUCKET")
        prefix, _ = value("s3_prefix", "ARCH_S3_PREFIX", "arch-assurance/")
        region, _ = value("s3_region", "ARCH_S3_REGION")
        if not bucket:
            return None, ("s3-worm archive identity incomplete: no bucket configured (settings or ARCH_S3_BUCKET)",)
        reportable = {"bucket": bucket, "prefix": prefix} | ({"region": region} if region else {})
        return ArchiveIdentity(backend, (bucket, prefix), reportable, bucket_source), ()
    if backend == "azure-blob-worm":
        account, account_source = value("azure_storage_account", "ARCH_AZURE_STORAGE_ACCOUNT")
        container, _ = value("azure_container", "ARCH_AZURE_CONTAINER")
        state_container, _ = value("azure_state_container", "ARCH_AZURE_STATE_CONTAINER")
        if not account or not container:
            return None, (
                "azure-blob-worm archive identity incomplete: storage account and container required "
                "(settings or ARCH_AZURE_STORAGE_ACCOUNT/ARCH_AZURE_CONTAINER)",
            )
        reportable = {"storage_account": account, "container": container, "state_container": state_container}
        return ArchiveIdentity(backend, (account, container, state_container), reportable, account_source), ()
    # standard | worm: the assurance DB itself is the archive — never a second path.
    return None, ()


def resolve_deployment_layout(
    inputs: LayoutInputs, settings_document: SettingsDocumentSelection
) -> DeploymentManifest:
    """Stage 2 — per-field resolution, transcribed from the normative table."""
    root = inputs.deployment_root
    workspace = _resolve_field(
        inputs,
        "workspace_root",
        cli_value=inputs.cli.workspace,
        settings_value=inputs.settings.deployment_workspace_root,
        env_key=None,
        deployment_root_default=(root / "workspace") if root else None,
        compat_default=None,
    )
    assurance_db = _resolve_field(
        inputs,
        "assurance_db_path",
        cli_value=inputs.cli.assurance_store,
        settings_value=inputs.settings.deployment_assurance_db_path,
        env_key=ENV_ASSURANCE_DB_PATH,
        deployment_root_default=(root / ASSURANCE_DIRNAME / ASSURANCE_STORE_FILENAME) if root else None,
        compat_default=inputs.source_tree_root / ASSURANCE_DIRNAME / ASSURANCE_STORE_FILENAME,
    )
    signals_db = _resolve_field(
        inputs,
        "signals_db_path",
        cli_value=inputs.cli.signals_db,
        settings_value=inputs.settings.deployment_signals_db_path,
        env_key=ENV_SIGNALS_DB_PATH,
        deployment_root_default=(root / ASSURANCE_DIRNAME / SIGNALS_DB_FILENAME) if root else None,
        compat_default=inputs.source_tree_root / ASSURANCE_DIRNAME / SIGNALS_DB_FILENAME,
    )
    guidance_cache = _resolve_field(
        inputs,
        "guidance_cache_root",
        cli_value=inputs.cli.guidance_cache,
        settings_value=inputs.settings.deployment_guidance_cache_root,
        env_key=None,
        deployment_root_default=(root / GUIDANCE_CACHE_DIRNAME) if root else None,
        compat_default=inputs.home / ".config" / "arch-repo" / GUIDANCE_CACHE_DIRNAME,
    )
    if assurance_db is None or signals_db is None or guidance_cache is None:  # pragma: no cover
        raise AssertionError("fields with compat defaults always resolve")
    archive_identity, archive_notes = _archive_identity(inputs)
    return DeploymentManifest(
        settings_document=settings_document,
        workspace_root=workspace,
        assurance_db_path=assurance_db,
        signals_db_path=signals_db,
        guidance_cache_root=guidance_cache,
        store_backend=inputs.settings.store_backend,
        signals_backend=inputs.settings.signals_backend,
        archive_backend=inputs.settings.archive_backend,
        assurance_enabled=inputs.settings.assurance_enabled,
        archive_identity=archive_identity,
        archive_notes=archive_notes,
    )
