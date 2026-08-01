"""Filesystem adapters implementing the `RepoUpgradeView`/`RepoUpgradeWriter` ports."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.atomic_file import write_atomic
from src.infrastructure.repository_upgrade.config_store import (
    read_applied_steps,
    read_format_contract_version,
    stamp_repo,
)


@lru_cache(maxsize=1)
def _known_entity_type_names() -> frozenset[str]:

    return process_runtime_catalogs().ontology.all_entity_type_names()


@dataclass(frozen=True)
class FilesystemRepoUpgradeView:
    root: Path

    def read_text(self, relative_path: str) -> str | None:
        path = self.root / relative_path
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def list_files(self, relative_glob: str) -> list[str]:
        return sorted(
            str(p.relative_to(self.root).as_posix())
            for p in self.root.glob(relative_glob)
            if p.is_file()
        )

    @property
    def applied_step_ids(self) -> frozenset[str]:
        return read_applied_steps(self.root)

    @property
    def recorded_format_contract_version(self) -> str | None:
        return read_format_contract_version(self.root)

    @property
    def known_entity_type_names(self) -> frozenset[str]:
        return _known_entity_type_names()


@dataclass(frozen=True)
class FilesystemRepoUpgradeWriter:
    root: Path

    def write_text(self, relative_path: str, content: str) -> None:
        write_atomic(self.root / relative_path, content)

    def rebuild_index(self) -> None:
        from src.infrastructure.artifact_index.service import ArtifactIndex  # noqa: PLC0415

        ArtifactIndex(self.root).refresh()

    def stamp_applied_steps(self, step_ids: frozenset[str], *, format_contract_version: str) -> None:
        stamp_repo(self.root, format_contract_version=format_contract_version, applied_step_ids=step_ids)
