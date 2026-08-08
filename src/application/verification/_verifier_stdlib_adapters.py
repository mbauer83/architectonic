"""Application-layer adapters for verifier ports using only stdlib + application imports.

These adapters implement the verifier ports defined in verifier_ports.py using only
stdlib (threading, pathlib, concurrent.futures) and application-layer modules.
Infrastructure-specific adapters (e.g. DefaultPumlSyntaxAdapter using subprocess/Java)
remain in src/infrastructure/verification/adapters.py.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.application.verification._verifier_inventory import FileInventory, inventory_files
from src.application.verification.artifact_verifier_incremental import (
    git_head as _git_head,
)
from src.application.verification.artifact_verifier_incremental import (
    load_incremental_state,
    load_runtime_config,
    save_incremental_state,
    state_file_path,
    verifier_engine_signature,
)
from src.application.verification.artifact_verifier_syntax import resolve_worker_count
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    Issue,
    VerificationResult,
)
from src.domain.repository.repo_layout import DOCS


class _NullPumlSyntax:
    """No-op PumlSyntaxPort: used when check_puml_syntax is disabled or no port provided."""

    def check_one(self, path: Path, loc: str) -> list[Issue]:
        return []

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]:
        return {}


class ThreadPoolVerifierScheduler:
    """Runs file verification work on a ThreadPoolExecutor."""

    def run(
        self,
        fn: Callable[[Path], VerificationResult],
        paths: list[Path],
        *,
        max_workers: int | None = None,
    ) -> list[VerificationResult]:
        if not paths:
            return []
        workers = resolve_worker_count()
        if max_workers is not None:
            workers = min(workers, max_workers)
        if workers <= 1:
            return [fn(p) for p in paths]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(fn, paths))


class FilesystemInventoryAdapter:
    """Builds FileInventory by walking the repository filesystem."""

    def build(self, repo_path: Path, *, include_diagrams: bool) -> FileInventory:
        return inventory_files(repo_path, include_diagrams=include_diagrams)

    def list_doc_files(self, repo_path: Path) -> list[Path]:
        docs_root = repo_path / DOCS
        if not docs_root.exists():
            return []
        return sorted(docs_root.rglob("*.md"))

    def filter_doc_files(self, repo_path: Path, candidates: list[Path]) -> list[Path]:
        docs_root = repo_path / DOCS
        if not docs_root.exists():
            return []
        return [
            p for p in candidates
            if p.suffix == ".md" and p.exists() and docs_root in p.resolve().parents
        ]


class DefaultIncrementalStateAdapter:
    """Persists incremental state to a JSON file and reads git HEAD."""

    def state_path(self, repo_path: Path, *, include_diagrams: bool) -> Path:
        cfg = load_runtime_config()
        return state_file_path(repo_path, include_diagrams=include_diagrams, state_dir=cfg.state_dir)

    def load(self, state_path: Path) -> IncrementalState | None:
        return load_incremental_state(state_path)

    def save(self, state_path: Path, state: IncrementalState) -> None:
        save_incremental_state(state_path, state)

    def git_head(self, repo_path: Path) -> str | None:
        return _git_head(repo_path)

    def engine_signature(self) -> str:
        return verifier_engine_signature()
