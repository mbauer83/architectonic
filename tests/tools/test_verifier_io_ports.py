"""Unit tests proving verifier I/O concerns are behind injectable ports.

WU-11: ArtifactVerifier orchestration now delegates filesystem inventory,
PUML syntax execution, worker scheduling, and incremental-state persistence
through application-owned Protocol ports — not via direct calls to
subprocess, ThreadPoolExecutor, or Path I/O.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_incremental import FileInventory
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    Issue,
    VerificationResult,
    VerifierRuntimeConfig,
)


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_inventory(repo_path: Path) -> FileInventory:
    return FileInventory(repo_path=repo_path, include_diagrams=True)


class _FakeInventoryPort:
    def __init__(self, repo_path: Path, entity_file: Path | None = None) -> None:
        inv = _empty_inventory(repo_path)
        if entity_file is not None:
            rel = str(entity_file.relative_to(repo_path))
            inv.rel_to_path[rel] = entity_file
            inv.path_to_rel[entity_file] = rel
            inv.entity_relpaths.append(rel)
            inv.ordered_paths.append(rel)
        self._inventory = inv
        self.build_calls: list[dict] = []
        self.list_doc_calls: list[Path] = []
        self.filter_doc_calls: list[tuple[Path, list[Path]]] = []

    def build(self, repo_path: Path, *, include_diagrams: bool) -> FileInventory:
        self.build_calls.append({"repo_path": repo_path, "include_diagrams": include_diagrams})
        return self._inventory

    def list_doc_files(self, repo_path: Path) -> list[Path]:
        self.list_doc_calls.append(repo_path)
        return []

    def filter_doc_files(self, repo_path: Path, candidates: list[Path]) -> list[Path]:
        self.filter_doc_calls.append((repo_path, candidates))
        return []


class _FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, list[Path]]] = []

    def run(self, fn: Any, paths: list[Path], *, max_workers: int | None = None) -> list[VerificationResult]:
        self.calls.append((fn, list(paths)))
        return [fn(p) for p in paths]


class _FakePumlSyntaxPort:
    def __init__(self) -> None:
        self.check_one_calls: list[tuple[Path, str]] = []
        self.check_batch_calls: list[list[Path]] = []

    def check_one(self, path: Path, loc: str) -> list[Issue]:
        self.check_one_calls.append((path, loc))
        return []

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]:
        self.check_batch_calls.append(list(paths))
        return {p: [] for p in paths}


class _FakeIncrementalPort:
    def __init__(self, repo_path: Path) -> None:
        self._state_path = repo_path / ".state.json"
        self.state_path_calls: list[dict] = []
        self.load_calls: list[Path] = []
        self.save_calls: list[tuple[Path, IncrementalState]] = []
        self.git_head_calls: list[Path] = []
        self.engine_sig_calls: int = 0

    def state_path(self, repo_path: Path, *, include_diagrams: bool) -> Path:
        self.state_path_calls.append({"repo_path": repo_path, "include_diagrams": include_diagrams})
        return self._state_path

    def load(self, state_path: Path) -> IncrementalState | None:
        self.load_calls.append(state_path)
        return None

    def save(self, state_path: Path, state: IncrementalState) -> None:
        self.save_calls.append((state_path, state))

    def git_head(self, repo_path: Path) -> str | None:
        self.git_head_calls.append(repo_path)
        return "abc123"

    def engine_signature(self) -> str:
        self.engine_sig_calls += 1
        return "sig0001"


# ---------------------------------------------------------------------------
# Tests: FileInventoryPort
# ---------------------------------------------------------------------------


def test_verify_all_full_calls_inventory_build(tmp_path: Path) -> None:
    inventory = _FakeInventoryPort(tmp_path)
    scheduler = _FakeScheduler()
    verifier = ArtifactVerifier(
        check_puml_syntax=False,
        file_inventory=inventory,
        scheduler=scheduler,
        catalogs=_catalogs(),
    )
    verifier.verify_all(tmp_path)
    assert len(inventory.build_calls) >= 1
    assert all(c["repo_path"] == tmp_path for c in inventory.build_calls)


def test_verify_all_full_calls_list_doc_files(tmp_path: Path) -> None:
    inventory = _FakeInventoryPort(tmp_path)
    scheduler = _FakeScheduler()
    verifier = ArtifactVerifier(
        check_puml_syntax=False,
        file_inventory=inventory,
        scheduler=scheduler,
        catalogs=_catalogs(),
    )
    verifier.verify_all(tmp_path)
    assert tmp_path in inventory.list_doc_calls


def test_verify_paths_calls_filter_doc_files(tmp_path: Path) -> None:
    entity_file = tmp_path / "entity.md"
    entity_file.touch()
    inventory = _FakeInventoryPort(tmp_path, entity_file=entity_file)
    scheduler = _FakeScheduler()
    verifier = ArtifactVerifier(
        check_puml_syntax=False,
        file_inventory=inventory,
        scheduler=scheduler,
        catalogs=_catalogs(),
    )
    verifier.verify_paths(tmp_path, changed_paths=[entity_file], verification_scope="changed")
    assert len(inventory.filter_doc_calls) == 1
    assert inventory.filter_doc_calls[0][0] == tmp_path


# ---------------------------------------------------------------------------
# Tests: VerifierScheduler
# ---------------------------------------------------------------------------


def test_verify_all_full_uses_scheduler(tmp_path: Path) -> None:
    inventory = _FakeInventoryPort(tmp_path)
    scheduler = _FakeScheduler()
    verifier = ArtifactVerifier(
        check_puml_syntax=False,
        file_inventory=inventory,
        scheduler=scheduler,
        catalogs=_catalogs(),
    )
    verifier.verify_all(tmp_path)
    assert len(scheduler.calls) >= 1


# ---------------------------------------------------------------------------
# Tests: PumlSyntaxPort
# ---------------------------------------------------------------------------


def test_verify_diagram_file_uses_puml_port(tmp_path: Path) -> None:
    puml_port = _FakePumlSyntaxPort()
    verifier = ArtifactVerifier(check_puml_syntax=True, puml_syntax=puml_port, catalogs=_catalogs())
    path = tmp_path / "test.puml"
    path.write_text("---\nartifact-type: diagram\nstatus: draft\n---\n@startuml\nA -> B\n@enduml\n")
    verifier.verify_diagram_file(path)
    assert len(puml_port.check_one_calls) == 1
    assert puml_port.check_one_calls[0][0] == path


def test_verify_diagram_file_skips_puml_port_when_check_disabled(tmp_path: Path) -> None:
    puml_port = _FakePumlSyntaxPort()
    verifier = ArtifactVerifier(check_puml_syntax=False, puml_syntax=puml_port, catalogs=_catalogs())
    path = tmp_path / "test.puml"
    path.write_text("@startuml\nA -> B\n@enduml\n")
    verifier.verify_diagram_file(path)
    assert puml_port.check_one_calls == []


# ---------------------------------------------------------------------------
# Tests: IncrementalStatePort
# ---------------------------------------------------------------------------


def test_verify_all_incremental_uses_state_port(tmp_path: Path, monkeypatch) -> None:
    inventory = _FakeInventoryPort(tmp_path)
    scheduler = _FakeScheduler()
    incremental = _FakeIncrementalPort(tmp_path)

    def _full_mode_config() -> VerifierRuntimeConfig:
        from src.application.verification.artifact_verifier_types import VerifierRuntimeConfig
        return VerifierRuntimeConfig(
            mode="incremental",
            state_dir=tmp_path,
            changed_ratio_threshold=0.3,
            changed_count_threshold=200,
            log_mode=False,
        )

    monkeypatch.setattr(
        "src.application.verification.artifact_verifier.load_runtime_config",
        _full_mode_config,
    )

    verifier = ArtifactVerifier(
        check_puml_syntax=False,
        file_inventory=inventory,
        scheduler=scheduler,
        incremental_state=incremental,
        catalogs=_catalogs(),
    )
    verifier.verify_all(tmp_path)

    assert len(incremental.state_path_calls) == 1
    assert len(incremental.load_calls) == 1
    assert len(incremental.git_head_calls) == 1
    assert incremental.engine_sig_calls == 1
    assert len(incremental.save_calls) == 1
