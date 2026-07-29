"""Ports for the `arch-repair upgrade` framework.

`RepoUpgradeView` gives a step's pure `detect()` read access to one repo root.
`RepoUpgradeWriter` is the only way `apply()` may mutate that repo, so every step's write
surface goes through the same adapter (filesystem in production, in-memory in tests).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding


class RepoUpgradeView(Protocol):
    """Read-only access to one repo root, for a step's `detect()`."""

    @property
    def root(self) -> Path: ...

    def read_text(self, relative_path: str) -> str | None:
        """Return file contents, or None if the file does not exist."""
        ...

    def list_files(self, relative_glob: str) -> list[str]:
        """Return relative paths (POSIX-style, sorted) matching *relative_glob* under root."""
        ...

    @property
    def applied_step_ids(self) -> frozenset[str]:
        """Step ids already stamped as applied in this repo's `.arch-repo/config.yaml`."""
        ...

    @property
    def recorded_format_contract_version(self) -> str | None:
        """`format_contract_version` already stamped in `.arch-repo/config.yaml`, if any."""
        ...

    @property
    def known_entity_type_names(self) -> frozenset[str]:
        """Entity type names the currently-registered ontology modules recognize."""
        ...


class RepoUpgradeWriter(Protocol):
    """The only mutation surface a step's `apply()` may use."""

    def write_text(self, relative_path: str, content: str) -> None: ...

    def rebuild_index(self) -> None:
        """Rebuild the disk-backed index after all steps have applied their rewrites."""
        ...

    def stamp_applied_steps(self, step_ids: frozenset[str], *, format_contract_version: str) -> None:
        """Record `format_contract_version` + applied step ids in `.arch-repo/config.yaml`."""
        ...


class UpgradeStep(Protocol):
    id: str
    version: int
    description: str
    scanned_surface: ScannedSurface

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        """Pure: no I/O beyond reading through *view*, no mutation."""
        ...

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        """Rewrite every finding through *writer*; idempotent.

        The framework (`apply_repository`) filters out non-auto-migratable findings before
        calling this — every finding in *findings* is guaranteed `auto_migratable=True`, so
        a step never needs to check that flag itself. A step whose `detect()` only ever
        produces manual (`auto_migratable=False`) findings — e.g. a diagnostic-only
        catch-all — will simply never have this method invoked; implement it to return `[]`.
        """
        ...
