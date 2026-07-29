"""Deployment identity: value objects for the two-stage layout resolution.

One pure resolver (`layout_resolution`, beside this module) decides which settings
document governs a deployment (stage 1) and where every operational path lives
(stage 2), so `arch-repair upgrade`, Docker startup, and runtime composition
can never disagree about which physical stores belong to a deployment. Every
resolved value carries its source; explicit sources that disagree are a hard
error before any store is opened or created.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SettingsDocumentSource = Literal["cli", "deployment_root_default", "env", "source_tree_default"]
FieldSource = Literal["cli", "settings", "env", "deployment_root_default", "compat_default", "derived"]

ENV_SETTINGS_PATH = "ARCH_SETTINGS_PATH"
"""Process-level settings-document selector (stage 1). Deliberately distinct from
`ARCH_SETTINGS_FILE`, which is a host-side Compose bind-mount SOURCE and is never
read by this process."""

ENV_ASSURANCE_DB_PATH = "ARCH_ASSURANCE_DB_PATH"
ENV_SIGNALS_DB_PATH = "ARCH_SECURITY_SIGNALS_DB_PATH"

ASSURANCE_DIRNAME = ".arch-assurance"
ASSURANCE_STORE_FILENAME = "store.db"
SIGNALS_DB_FILENAME = "security-signals.db"
GUIDANCE_CACHE_DIRNAME = "guidance-cache"


@dataclass(frozen=True)
class SettingsDocumentSelection:
    """Stage-1 outcome: the one settings document governing this deployment."""

    path: Path
    source: SettingsDocumentSource

    @property
    def operator_owned(self) -> bool:
        """The source-tree compatibility default is package/VCS-owned and read-only —
        never a migration target."""
        return self.source != "source_tree_default"


@dataclass(frozen=True)
class ProvenanceEntry:
    source: FieldSource
    raw_value: str


@dataclass(frozen=True)
class ResolvedPathField:
    """One stage-2 field: canonical path + winning source + full provenance."""

    path: Path
    source: FieldSource
    provenance: tuple[ProvenanceEntry, ...]


class DeploymentLayoutConflict(ValueError):
    """Two explicit authoritative selectors named different canonical values."""

    def __init__(self, field_name: str, entries: tuple[tuple[FieldSource, str], ...]) -> None:
        self.field_name = field_name
        self.entries = entries
        detail = "; ".join(f"{source}={raw!r}" for source, raw in entries)
        super().__init__(
            f"Conflicting explicit values for deployment field {field_name!r}: {detail}. "
            "Remove or align the selectors — the deployment identity must be unambiguous."
        )


@dataclass(frozen=True)
class CliSelectors:
    """Explicit command-line selectors (all optional)."""

    settings: str | None = None
    deployment_root: str | None = None
    workspace: str | None = None
    assurance_store: str | None = None
    signals_db: str | None = None
    guidance_cache: str | None = None


@dataclass(frozen=True)
class SettingsValues:
    """The layout-relevant values parsed from the SELECTED settings document."""

    deployment_workspace_root: str | None = None
    deployment_assurance_db_path: str | None = None
    deployment_signals_db_path: str | None = None
    deployment_guidance_cache_root: str | None = None
    store_backend: str = "sqlcipher"
    signals_backend: str = "sqlcipher-colocated"
    archive_backend: str = "standard"
    assurance_enabled: bool = True
    archive: Mapping[str, str] = field(default_factory=dict)
    """Cloud archive fields by settings key suffix (e.g. ``s3_bucket``,
    ``azure_storage_account``). Env fallbacks are applied by the resolver."""


@dataclass(frozen=True)
class ArchiveIdentity:
    """Canonical archive identity tuple (preflight-checked, not migrated in v1)."""

    backend: str
    identity: tuple[str, ...]
    reportable: Mapping[str, str]
    source: FieldSource


@dataclass(frozen=True)
class DeploymentManifest:
    """Stage-2 outcome: every operational location with provenance.

    Runtime and Docker accept this manifest rather than re-resolving; upgrade
    discovery derives its operational targets from it. ``workspace_root`` is
    ``None`` when no selector named one — callers keep their existing
    CWD/arch-init behavior (the compatibility default of that field).
    """

    settings_document: SettingsDocumentSelection
    workspace_root: ResolvedPathField | None
    assurance_db_path: ResolvedPathField
    signals_db_path: ResolvedPathField
    guidance_cache_root: ResolvedPathField
    store_backend: str
    signals_backend: str
    archive_backend: str
    assurance_enabled: bool
    archive_identity: ArchiveIdentity | None
    archive_notes: tuple[str, ...] = ()
    """Unresolved/incomplete cloud-archive identity notes for preflight reporting."""
