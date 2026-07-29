"""Text-file operational targets: the deployment settings document and the
guidance cache. Writes are staged and land atomically (temp + rename) on
commit — one unit of work per target, never a partial rewrite."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.atomic_file import write_atomic


@dataclass
class TextTargetUnitOfWork:
    """Staged atomic text writes for one file or directory target."""

    base: Path
    single_file: bool
    _staged: dict[str, str] = field(default_factory=dict)

    def write_text(self, relative_path: str, content: str) -> None:
        self._staged[relative_path] = content

    def execute_sql(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        raise NotImplementedError("text-file targets have no SQL surface")

    def commit(self) -> None:
        for relative, content in self._staged.items():
            path = self.base if self.single_file and not relative else self.base / relative
            write_atomic(path, content)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


@dataclass(frozen=True)
class _TextTargetView:
    target: UpgradeTarget
    base: Path
    single_file: bool

    def read_text(self, relative_path: str = "") -> str | None:
        path = self.base if self.single_file and not relative_path else self.base / relative_path
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def list_files(self, relative_glob: str) -> list[str]:
        if self.single_file or not self.base.is_dir():
            return []
        return sorted(
            str(p.relative_to(self.base).as_posix())
            for p in self.base.glob(relative_glob)
            if p.is_file()
        )

    def query_scalar(self, sql: str, parameters: tuple[object, ...] = ()) -> object | None:
        raise NotImplementedError("text-file targets have no SQL surface")


@dataclass(frozen=True)
class SettingsDocumentHandle:
    """The operator-owned deployment settings document as a versioned atomic
    text-file target. The source-tree compatibility default is never handed to
    this handle — it is read-only by contract."""

    target: UpgradeTarget
    path: Path

    @property
    def inspectable(self) -> bool:
        return True

    def view(self) -> _TextTargetView:
        return _TextTargetView(self.target, self.path, single_file=True)

    def begin(self) -> TextTargetUnitOfWork:
        return TextTargetUnitOfWork(self.path, single_file=True)


@dataclass(frozen=True)
class GuidanceCacheHandle:
    """The deployment guidance-cache directory as one target."""

    target: UpgradeTarget
    root: Path

    @property
    def inspectable(self) -> bool:
        return True

    def view(self) -> _TextTargetView:
        return _TextTargetView(self.target, self.root, single_file=False)

    def begin(self) -> TextTargetUnitOfWork:
        return TextTargetUnitOfWork(self.root, single_file=False)


def guidance_cache_version(root: Path) -> int | None:
    """The lowest `guidance_format` across cached documents; None when a document
    is unreadable (never assumed current)."""
    versions: list[int] = []
    for doc in sorted(root.glob("*.guidance.yaml")):
        try:
            data: object = yaml.safe_load(doc.read_text(encoding="utf-8")) or {}
            version = data.get("guidance_format") if isinstance(data, dict) else None
        except yaml.YAMLError:
            return None
        if not isinstance(version, int):
            return None
        versions.append(version)
    return min(versions) if versions else None
