"""Application-owned port contracts for the artifact verifier's I/O concerns.

These Protocols define what the verifier orchestration needs from its
environment; concrete adapters in src/infrastructure/verification/ provide
the implementations.  Tests substitute lightweight fakes without touching
the filesystem, subprocess, or thread pools.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from src.application.verification.artifact_verifier_incremental import FileInventory
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    Issue,
    VerificationResult,
)


class PumlSyntaxPort(Protocol):
    """Execute PlantUML/Java syntax checks against diagram files."""

    def check_one(self, path: Path, loc: str) -> list[Issue]: ...

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]: ...


class VerifierScheduler(Protocol):
    """Schedule parallel file verification work."""

    def run(
        self,
        fn: Callable[[Path], VerificationResult],
        paths: list[Path],
        *,
        max_workers: int | None = None,
    ) -> list[VerificationResult]: ...


class FileInventoryPort(Protocol):
    """Build and query the file inventory for a model repository."""

    def build(self, repo_path: Path, *, include_diagrams: bool) -> FileInventory: ...

    def list_doc_files(self, repo_path: Path) -> list[Path]: ...

    def filter_doc_files(self, repo_path: Path, candidates: list[Path]) -> list[Path]: ...


class IncrementalStatePort(Protocol):
    """Persist and retrieve incremental verifier state."""

    def state_path(self, repo_path: Path, *, include_diagrams: bool) -> Path: ...

    def load(self, state_path: Path) -> IncrementalState | None: ...

    def save(self, state_path: Path, state: IncrementalState) -> None: ...

    def git_head(self, repo_path: Path) -> str | None: ...

    def engine_signature(self) -> str: ...
