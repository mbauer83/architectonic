"""Tests for model watch tools fingerprinting.

Updated for ArchiMate 4.0 conventions:
- model/ directory (not model-entities/)
- .outgoing.md connections (not connections/ directory)
"""

import os
from pathlib import Path

from src.infrastructure.mcp.artifact_mcp.watch_tools import _repo_state_snapshot, _roots_state_snapshot


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _set_mtime_ns(path: Path, value: int) -> None:
    os.utime(path, ns=(value, value))


def test_roots_fingerprint_detects_non_max_repo_change(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"

    file_a = repo_a / "model" / "application" / "application-component" / "APP@1712870400.kRZYOA.event-store.md"
    file_b = repo_b / "model" / "motivation" / "driver" / "DRV@1712870400.Qw7Er1.codegen-velocity.outgoing.md"

    _write(file_a, "a")
    _write(file_b, "b")

    _set_mtime_ns(file_a, 2_000_000_000)
    _set_mtime_ns(file_b, 1_000_000_000)

    before = _roots_state_snapshot([repo_a, repo_b])

    file_b.write_text("bb", encoding="utf-8")
    _set_mtime_ns(file_b, 1_500_000_000)

    after = _roots_state_snapshot([repo_a, repo_b])

    assert before != after


def test_repo_fingerprint_detects_same_size_content_touch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    file_path = repo / "diagram-catalog" / "diagrams" / "DIA@1712870400.DFgOaO.test-diagram.puml"

    _write(file_path, "abc")
    _set_mtime_ns(file_path, 1_000_000_000)
    before = _repo_state_snapshot(repo)

    file_path.write_text("xyz", encoding="utf-8")
    _set_mtime_ns(file_path, 2_000_000_000)
    after = _repo_state_snapshot(repo)

    assert before != after
